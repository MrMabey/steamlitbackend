import streamlit as st
import google.generativeai as genai
import json
import re
from bs4 import BeautifulSoup
from typing import Optional

# Streamlit configuration
st.set_page_config(page_title="AI Teacher Tools", layout="wide")

# Initialize Gemini client
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialize session states
if "question_type" not in st.session_state:
    st.session_state.question_type = None
if "question_prompt" not in st.session_state:
    st.session_state.question_prompt = ""
if "generated_questions" not in st.session_state:
    st.session_state.generated_questions = []
if "current_score" not in st.session_state:
    st.session_state.current_score = 0
if "total_questions" not in st.session_state:
    st.session_state.total_questions = 0
if "answered_questions" not in st.session_state:
    st.session_state.answered_questions = set()
if "lesson_plan_content" not in st.session_state:
    st.session_state.lesson_plan_content = None
if "section_questions" not in st.session_state:
    st.session_state.section_questions = {}

def parse_notion_html(html_content: str) -> Optional[dict]:
    """Parse Notion-exported HTML into structured content"""
    if not html_content:
        return None
        
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title and metadata
        title = soup.find('h1', {'class': 'page-title'})
        title = title.text if title else "Lesson Plan"
        
        # Extract grade levels and subjects
        grade_levels = []
        subjects = []
        for select in soup.find_all(class_='select-value-color-red'):
            text = select.text.strip()
            if any(grade in text.lower() for grade in ['th', 'grade']):
                grade_levels.append(text)
            else:
                subjects.append(text)
                
        # Parse content sections
        sections = []
        current_section = None
        
        for elem in soup.select('.page-body > *'):
            # Handle headers
            if elem.name in ['h1', 'h2', 'h3']:
                if current_section:
                    sections.append(current_section)
                current_section = {
                    'title': elem.text.strip(),
                    'level': int(elem.name[1]),
                    'content': []
                }
            # Handle content
            elif current_section is not None:
                if elem.name == 'p':
                    current_section['content'].append({
                        'type': 'text',
                        'content': elem.text.strip()
                    })
                elif elem.name in ['ul', 'ol']:
                    items = [li.text.strip() for li in elem.find_all('li')]
                    current_section['content'].append({
                        'type': 'list',
                        'items': items,
                        'ordered': elem.name == 'ol'
                    })
                elif elem.name == 'figure':
                    img = elem.find('img')
                    if img and img.get('src'):
                        current_section['content'].append({
                            'type': 'image',
                            'src': img['src'],
                            'alt': img.get('alt', '')
                        })
        
        if current_section:
            sections.append(current_section)
            
        return {
            'title': title,
            'grade_levels': grade_levels,
            'subjects': subjects,
            'sections': sections
        }
        
    except Exception as e:
        st.error(f"Error parsing lesson plan: {e}")
        return None

def render_lesson_plan(content: dict):
    """Render lesson plan content using Streamlit components with question insertion capabilities"""
    if not content:
        return
        
    # Custom CSS
    st.markdown("""
        <style>
        .notion-title {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 0.5em;
        }
        .notion-metadata {
            display: flex;
            gap: 1em;
            margin-bottom: 2em;
        }
        .notion-tag {
            background: #f0f0f0;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .notion-section {
            margin: 2em 0;
        }
        .notion-content {
            margin-left: 1.5em;
        }
        .question-insert-area {
            border-left: 3px solid #f63366;
            padding-left: 1em;
            margin: 1em 0;
            background-color: #f7f7f7;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Title and metadata
    st.markdown(f'<h1 class="notion-title">{content["title"]}</h1>', unsafe_allow_html=True)
    
    # Metadata
    meta_col1, meta_col2 = st.columns(2)
    with meta_col1:
        st.markdown("**Grade Levels**")
        for grade in content['grade_levels']:
            st.markdown(f'<span class="notion-tag">{grade}</span>', unsafe_allow_html=True)
    with meta_col2:
        st.markdown("**Subjects**")
        for subject in content['subjects']:
            st.markdown(f'<span class="notion-tag">{subject}</span>', unsafe_allow_html=True)
    
    # Render sections
    for section_idx, section in enumerate(content['sections']):
        with st.container():
            # Section header
            if section['level'] == 2:
                st.markdown(f"## {section['title']}")
            elif section['level'] == 3:
                st.markdown(f"### {section['title']}")
            else:
                st.markdown(f"#### {section['title']}")
            
            # Add question insertion area before content
            with st.expander("➕ Add Question/Prompt Here", expanded=False):
                section_key = f"section_{section_idx}"
                
                # Question type selection
                question_type = st.selectbox(
                    "Question Type",
                    ["Multiple Choice", "True/False", "Short Answer", "Open Ended"],
                    key=f"type_{section_key}"
                )
                
                # Question prompt input
                prompt = st.text_area(
                    "Enter your question or prompt",
                    key=f"prompt_{section_key}"
                )
                
                # Generate button
                if st.button("Generate Question", key=f"gen_{section_key}"):
                    if prompt:
                        try:
                            generated_question = generate_single_question(
                                question_type,
                                prompt,
                                section['title']
                            )
                            if section_key not in st.session_state.section_questions:
                                st.session_state.section_questions[section_key] = []
                            st.session_state.section_questions[section_key].append({
                                'question': generated_question,
                                'type': question_type
                            })
                            st.success("Question generated successfully!")
                        except Exception as e:
                            st.error(f"Error generating question: {e}")
                    else:
                        st.warning("Please enter a prompt before generating.")
            
            # Display existing questions for this section
            if section_key in st.session_state.section_questions:
                for q_idx, question_data in enumerate(st.session_state.section_questions[section_key]):
                    with st.container():
                        st.markdown("---")
                        display_question(
                            question_data['question'],
                            question_data['type'],
                            f"{section_key}_{q_idx}"
                        )
            
            # Section content
            with st.container():
                for item in section['content']:
                    if item['type'] == 'text':
                        st.markdown(item['content'])
                    elif item['type'] == 'list':
                        if item['ordered']:
                            for i, li in enumerate(item['items'], 1):
                                st.markdown(f"{i}. {li}")
                        else:
                            for li in item['items']:
                                st.markdown(f"* {li}")
                    elif item['type'] == 'image':
                        st.image(item['src'], caption=item['alt'])

def generate_single_question(question_type: str, prompt: str, section_title: str) -> dict:
    """Generate a single question using the AI model"""
    prompt_template = f"""
    Generate 1 {question_type} question about: {prompt}
    This question is for the section: {section_title}
    
    Format requirements:
    - For Multiple Choice: Include options a), b), c), d). Mark correct answer with *.
    - For True/False: Clearly state Answer: True/False
    - For Short Answer: Include a brief acceptable answer
    - For Open Ended: Include a sample response
    """
    
    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro-002",
        generation_config=generation_config,
    )
    
    response = model.generate_content(prompt_template)
    questions = parse_generated_questions(response.text, question_type)
    return questions[0] if questions else None

def display_question(question: dict, question_type: str, key_prefix: str):
    """Display an individual question with appropriate input controls"""
    st.write(question['question'])
    
    if question_type == 'multiple_choice':
        answer = st.radio(
            "Select your answer:",
            question['options'],
            key=f"answer_{key_prefix}"
        )
        if st.button("Check Answer", key=f"check_{key_prefix}"):
            if answer == question['correct_answer']:
                st.success("Correct!")
            else:
                st.error(f"Incorrect. The correct answer is: {question['correct_answer']}")
    
    elif question_type == 'true_false':
        answer = st.radio(
            "Select your answer:",
            ["True", "False"],
            key=f"answer_{key_prefix}"
        )
        if st.button("Check Answer", key=f"check_{key_prefix}"):
            if str(answer).lower() == str(question['correct_answer']).lower():
                st.success("Correct!")
            else:
                st.error(f"Incorrect. The correct answer is: {question['correct_answer']}")
    
    else:  # Short Answer and Open Ended
        answer = st.text_area(
            "Your answer:",
            key=f"answer_{key_prefix}"
        )
        if st.button("Show Sample Answer", key=f"show_{key_prefix}"):
            st.info(f"Sample Answer:\n{question['sample_answer']}")

def read_html_file(uploaded_file):
    """Read and parse HTML file content"""
    if uploaded_file is not None:
        content = uploaded_file.read().decode('utf-8')
        return parse_notion_html(content)
    return None

# Sidebar for page navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Select a Page", ["Home", "Lesson Plan", "Questions"])

async def regenerate_single_question(question_type, topic_prompt, index):
    """Regenerate a single question"""
    try:
        prompt_template = f"""
        Generate 1 {question_type} question about: {topic_prompt}
        
        Format requirements:
        - For Multiple Choice: Include options a), b), c), d). Mark correct answer with *.
        - For True/False: Clearly state Answer: True/False
        - For Short Answer: Include a brief acceptable answer
        - For Open Ended: Include a sample response
        """
        
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
        
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro-002",
            generation_config=generation_config,
        )
        
        response = model.generate_content(prompt_template)
        new_questions = parse_generated_questions(response.text, question_type)
        
        if new_questions:
            st.session_state.generated_questions[index] = new_questions[0]
            if index in st.session_state.answered_questions:
                st.session_state.answered_questions.remove(index)
            return True
    except Exception as e:
        st.error(f"Error regenerating question: {e}")
        return False

# Function to clear questions and reset states
def clear_questions():
    st.session_state.generated_questions = []
    st.session_state.current_score = 0
    st.session_state.total_questions = 0
    st.session_state.answered_questions = set()
    st.session_state.question_prompt = ""

def parse_generated_questions(text, question_type):
    """Parse the AI generated text into structured question data"""
    questions = []
    
    if question_type == "Multiple Choice":
        # Split into individual questions
        question_blocks = re.split(r'\n\d+\.|Question \d+:', text)
        for block in question_blocks:
            if not block.strip():
                continue
            
            # Extract question and options
            lines = block.strip().split('\n')
            question = lines[0].strip()
            options = []
            correct_answer = None
            
            for line in lines[1:]:
                if line.strip().startswith(('a)', 'b)', 'c)', 'd)', 'A)', 'B)', 'C)', 'D)')):
                    option = line.strip()[2:].strip()
                    if '*' in option or 'correct' in option.lower():
                        correct_answer = option.replace('*', '').replace('(correct)', '').strip()
                    options.append(option.replace('*', '').replace('(correct)', '').strip())
            
            if question and options and correct_answer:
                questions.append({
                    'question': question,
                    'options': options,
                    'correct_answer': correct_answer,
                    'type': 'multiple_choice'
                })
    
    elif question_type == "True/False":
        # Split into individual questions
        question_blocks = re.split(r'\n\d+\.|Question \d+:', text)
        for block in question_blocks:
            if not block.strip():
                continue
            
            lines = block.strip().split('\n')
            question = lines[0].strip()
            correct_answer = None
            
            for line in lines:
                if 'Answer:' in line or 'Correct:' in line:
                    correct_answer = 'True' if 'true' in line.lower() else 'False'
            
            if question and correct_answer:
                questions.append({
                    'question': question,
                    'correct_answer': correct_answer,
                    'type': 'true_false'
                })
    
    elif question_type in ["Short Answer", "Open Ended"]:
        question_blocks = re.split(r'\n\d+\.|Question \d+:', text)
        for block in question_blocks:
            if not block.strip():
                continue
            
            lines = block.strip().split('\n')
            question = lines[0].strip()
            sample_answer = '\n'.join(lines[1:]).strip()
            
            if question:
                questions.append({
                    'question': question,
                    'sample_answer': sample_answer,
                    'type': 'open_ended' if question_type == "Open Ended" else 'short_answer'
                })
    
    return questions

def check_answer(question, user_answer):
    """Check if the user's answer is correct"""
    if question['type'] == 'multiple_choice':
        return user_answer == question['correct_answer']
    elif question['type'] == 'true_false':
        return str(user_answer).lower() == str(question['correct_answer']).lower()
    else:
        # For short answer and open-ended, we'll use manual checking
        return None

# Load lesson plan content
with open('lesson_plan_1.txt', 'r') as file:
    lesson_plan = file.read()

# Page: Home
if page == "Home":
    st.title("🎓 AI Teacher Tools")
    st.header("Welcome to Your Teaching Assistant")

    # Main features explanation
    st.subheader("What You Can Do:")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📚 Lesson Plan")
        st.write("""
        - Access the complete Arcade Machine Game Design lesson plan
        - View learning objectives and materials needed
        - Follow step-by-step teaching instructions
        - Get activity suggestions and timing
        """)
        
        st.markdown("### ❓ Question Generator")
        st.write("""
        - Generate different types of questions:
          * Multiple Choice
          * True/False
          * Short Answer
          * Open Ended
        - Customize questions based on your topic
        - Get instant feedback and scoring
        - Download questions for later use
        """)

    with col2:
        st.markdown("### 💡 Quick Tips")
        st.write("""
        1. Start with the Lesson Plan to familiarize yourself with the content
        2. Use the Questions page to:
           - Generate practice questions
           - Create quiz materials
           - Test questions interactively
        3. Clear questions anytime to start fresh
        4. Download generated questions for your records
        """)

# Page: Lesson Plan
elif page == "Lesson Plan":
    # Move file upload to sidebar
    st.sidebar.markdown("### Lesson Plan Controls")
    uploaded_file = st.sidebar.file_uploader("Upload lesson plan (HTML)", type=['html'])
    
    if uploaded_file is not None:
        # Read and store the HTML content
        st.session_state.lesson_plan_content = read_html_file(uploaded_file)
        st.sidebar.success("✅ Lesson plan uploaded successfully!")
    
    # Add clear button to sidebar
    if st.session_state.lesson_plan_content and st.sidebar.button("Clear Lesson Plan ❌"):
        st.session_state.lesson_plan_content = None
        st.rerun()
    
    # Display the lesson plan if available
    if st.session_state.lesson_plan_content:
        render_lesson_plan(st.session_state.lesson_plan_content)
    else:
        # Show placeholder when no lesson plan is uploaded
        st.info("👈 Please use the sidebar to upload a Notion-exported HTML lesson plan.")
        
# Page: Questions
elif page == "Questions":
    st.title("Interactive Questions Generator")
    
    # Question Type Selection in Sidebar
    st.sidebar.title("Question Controls")
    
    # Question type selection
    question_type = st.sidebar.radio(
        "Select Question Type:",
        ["Multiple Choice", "True/False", "Short Answer", "Open Ended"]
    )
    
    # Topic/prompt input
    topic_prompt = st.sidebar.text_area(
        "Enter topic or specific instructions:",
        help="Provide context or specific requirements for your questions"
    )
    
    # Number of questions slider
    num_questions = st.sidebar.slider("Number of questions:", 1, 10, 5)

    # Model selection
    model_option = st.sidebar.selectbox(
        "Select Model:",
        ["gemini-1.5-flash-002", "gemini-1.5-pro-002"]
    )
    
    # Generate button
    if st.sidebar.button("Generate Questions 🎯"):
        if topic_prompt:
            try:
                # Prepare the prompt based on question type and include lesson plan
                prompt_template = f"""
                System Instructions: You are a teaching assistant creating educational questions. Here is the lesson plan content to base your questions on:

                {lesson_plan}

                Please generate {num_questions} {question_type} questions about: {topic_prompt}
                
                Format requirements:
                - For Multiple Choice: Number each question and include options a), b), c), d). Mark correct answer with *.
                - For True/False: Number each question and clearly state Answer: True/False
                - For Short Answer: Number each question and include a brief acceptable answer
                - For Open Ended: Number each question and include a sample response
                
                Make questions clear and educational, using specific content from the lesson plan.
                """
                
                # Configure Gemini
                generation_config = {
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }
                
                model = genai.GenerativeModel(
                    model_name=model_option,
                    generation_config=generation_config,
                )
                
                # Generate response
                response = model.generate_content(prompt_template)
                
                # Parse and store questions
                st.session_state.generated_questions = parse_generated_questions(response.text, question_type)
                st.session_state.current_score = 0
                st.session_state.total_questions = len(st.session_state.generated_questions)
                st.session_state.answered_questions = set()
                
            except Exception as e:
                st.error(f"An error occurred: {e}")
        else:
            st.warning("Please enter a topic or instructions before generating questions.")
    
    # Clear Questions button
    if st.sidebar.button("Clear Questions ❌"):
        clear_questions()
        st.sidebar.success("Questions cleared!")
    
    # Display interactive questions
    if st.session_state.generated_questions:
        st.markdown("### Interactive Questions")
        
        # Score display
        score_col1, score_col2 = st.columns([1, 3])
        with score_col1:
            st.metric("Current Score", f"{st.session_state.current_score}/{st.session_state.total_questions}")
        
        # Display questions
        for i, question in enumerate(st.session_state.generated_questions):
            with st.expander(f"Question {i + 1}", expanded=True):
                col1, col2 = st.columns([10, 1])
                with col1:
                    st.write(question['question'])
                with col2:
                    if st.button("🔄", key=f"refresh_{i}", help="Regenerate this question"):
                        try:
                            # Prepare the prompt for single question regeneration
                            prompt_template = f"""
                            System Instructions: You are a teaching assistant creating an educational question. Here is the lesson plan content to base your question on:

                            {lesson_plan}

                            Please generate 1 {question_type} question about: {topic_prompt}
                            
                            Format requirements:
                            - For Multiple Choice: Include options a), b), c), d). Mark correct answer with *.
                            - For True/False: Clearly state Answer: True/False
                            - For Short Answer: Include a brief acceptable answer
                            - For Open Ended: Include a sample response
                            
                            Make the question clear and educational, using specific content from the lesson plan.
                            """
                            
                            # Generate new question
                            response = model.generate_content(prompt_template)
                            new_questions = parse_generated_questions(response.text, question_type)
                            
                            if new_questions:
                                # Replace the specific question
                                st.session_state.generated_questions[i] = new_questions[0]
                                # Remove from answered questions if it was answered
                                if i in st.session_state.answered_questions:
                                    st.session_state.answered_questions.remove(i)
                                    # Adjust score if necessary
                                    st.session_state.current_score = max(0, st.session_state.current_score - 1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error regenerating question: {e}")
                
                # Different input types based on question type
                if question['type'] == 'multiple_choice':
                    user_answer = st.radio(
                        "Select your answer:",
                        question['options'],
                        key=f"q_{i}",
                        disabled=i in st.session_state.answered_questions
                    )
                    
                    if st.button("Submit", key=f"submit_{i}", disabled=i in st.session_state.answered_questions):
                        is_correct = check_answer(question, user_answer)
                        if is_correct:
                            st.success("Correct!")
                            if i not in st.session_state.answered_questions:
                                st.session_state.current_score += 1
                        else:
                            st.error(f"Incorrect. The correct answer is: {question['correct_answer']}")
                        st.session_state.answered_questions.add(i)
                
                elif question['type'] == 'true_false':
                    user_answer = st.radio(
                        "Select your answer:",
                        ["True", "False"],
                        key=f"q_{i}",
                        disabled=i in st.session_state.answered_questions
                    )
                    
                    if st.button("Submit", key=f"submit_{i}", disabled=i in st.session_state.answered_questions):
                        is_correct = check_answer(question, user_answer)
                        if is_correct:
                            st.success("Correct!")
                            if i not in st.session_state.answered_questions:
                                st.session_state.current_score += 1
                        else:
                            st.error(f"Incorrect. The correct answer is: {question['correct_answer']}")
                        st.session_state.answered_questions.add(i)
                
                else:  # Short Answer and Open Ended
                    user_answer = st.text_area(
                        "Your answer:",
                        key=f"q_{i}",
                        disabled=i in st.session_state.answered_questions
                    )
                    
                    if st.button("Show Sample Answer", key=f"show_{i}"):
                        st.info(f"Sample Answer:\n{question['sample_answer']}")
                        st.session_state.answered_questions.add(i)
        
        # Download button for questions
        if st.button("Download Questions (and Answers Soon 🚧)"):
            questions_json = json.dumps(st.session_state.generated_questions, indent=2)
            st.download_button(
                label="Download JSON",
                data=questions_json,
                file_name="questions.json",
                mime="application/json"
            )

# Add appropriate styling
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)
