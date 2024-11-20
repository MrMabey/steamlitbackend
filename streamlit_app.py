import streamlit as st
import google.generativeai as genai
from datetime import datetime
import json
#Added for google sheets
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import streamlit_authenticator as stauth
import pickle
from pathlib import Path

import yaml
from yaml.loader import SafeLoader

with open('../psswrds.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Pre-hashing all plain text passwords once
# stauth.Hasher.hash_passwords(config['credentials'])

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)


try:
    authenticator.login()
except Exception as e:
    st.error(e)

# Page configuration
st.set_page_config(
    page_title="Project-Based Curriculum Builder",
    page_icon="📝",
    layout="wide"
)

# Establishing a Google Sheets connection
conn = st.connection("gsheets", type=GSheetsConnection)

# Fetch existing vendors data
existing_data = conn.read(worksheet="Sheet1", usecols=list(range(3)), ttl=5)
existing_data = existing_data.dropna(how="all")

st.dataframe(existing_data)

with st.form(key="entry_form"):
    entry_1 = st.text_input(label="Entry 1")
    entry_2 = st.text_input(label="Entry 2")
    test_entry = st.text_input(label="Test Entry")


    submit_button = st.form_submit_button(label="Submit Details")

    # If the submit button is pressed
    if submit_button:
    
            # Create a new row of vendor data
            entry_form = pd.DataFrame(
                [
                    {
                        "Entry 1": entry_1,
                        "Entry 2": entry_2,
                        "Test Entry": test_entry,
                    }
                ]
            )

            # Add the new vendor data to the existing data
            updated_df = pd.concat([existing_data, entry_form], ignore_index=True)

            # Update Google Sheets with the new vendor data
            conn.update(worksheet="Sheet1", data=updated_df)

            st.success("Details successfully submitted!")


# Initialize Gemini client
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialize session state
if "generated_lessons" not in st.session_state:
    st.session_state.generated_lessons = []
if "current_lesson" not in st.session_state:
    st.session_state.current_lesson = None
if "current_view" not in st.session_state:
    st.session_state.current_view = "edit"  # Can be 'edit' or 'view'

# Constants
GRADE_LEVELS = ["K-2", "3-5", "6-8", "9-12"]

SUBJECT_AREAS = {
    "Science": ["Biology", "Chemistry", "Physics", "Environmental Science", "Earth Science"],
    "Technology": ["Computer Science", "Digital Literacy", "Robotics", "Programming", "Data Science"],
    "Engineering": ["Mechanical", "Electrical", "Civil", "Aerospace", "Software"],
    "Mathematics": ["Algebra", "Geometry", "Statistics", "Calculus", "Number Theory"],
    "Social Studies": ["History", "Geography", "Civics", "Economics", "Anthropology"],
    "Language Arts": ["Literature", "Writing", "Reading", "Grammar", "Poetry"],
    "Art": ["Visual Arts", "Music", "Drama", "Dance", "Photography"],
    "Physical Education": ["Sports", "Health", "Fitness", "Wellness", "Nutrition"],
    "Foreign Languages": ["Spanish", "French", "German", "Chinese", "Japanese"],
    "Other": ["Custom Topic"]
}

DELIVERY_OPTIONS = ["Asynchronous", "Multi-Day Project", "One-Off Challenge (1-2 hours)"]

def generate_lesson_plan(grade_level, subject_area, specific_topic, delivery_timeline, objectives, materials_budget):
    """Generate a lesson plan using the Gemini API"""
    prompt = f"""
    Create a detailed project-based lesson plan with the following parameters:
    - Grade Level: {grade_level}
    - Subject Area: {subject_area}
    - Specific Topic: {specific_topic}
    - Delivery Timeline: {delivery_timeline}
    - Learning Objectives: {objectives}
    - Materials Budget: ${materials_budget}

    Please provide a complete lesson plan using the following structure exactly:

    Overview:
    [Write a brief introduction to the lesson, including its purpose and relevance]

    Learning Objectives:
    [List specific, measurable objectives that align with provided objectives]

    Required Materials:
    [List all materials needed with estimated costs, staying within ${materials_budget} budget]

    Preparation Steps:
    [List step-by-step preparation instructions]

    Lesson Procedure:
    [Provide detailed instructions including:
    - Introduction/Hook (5-10 minutes)
    - Main Activity
    - Wrap-up/Assessment]

    Extensions and Modifications:
    [Suggestions for differentiation and extensions]

    Assessment Criteria:
    [Specific criteria for evaluating student learning]

    Safety Considerations:
    [Any relevant safety notes and precautions]

    Take-Home Connection:
    [Ideas for connecting learning to home/real world]

    Make all content grade-appropriate for {grade_level} and specific to {specific_topic}.
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-002')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error generating lesson plan: {e}")
        return None

def regenerate_section(section_name: str, context: dict) -> str:
    """Regenerate a specific section of the lesson plan"""
    prompt = f"""
    For a project-based lesson plan with:
    - Grade Level: {context['grade_level']}
    - Subject Area: {context['subject_area']}
    - Specific Topic: {context['specific_topic']}
    - Delivery Timeline: {context['delivery_timeline']}
    
    Please regenerate only the {section_name} section.
    Make it detailed, grade-appropriate, and specific to the topic.
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-002')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Error regenerating section: {e}")
        return None

def parse_lesson_sections(content):
    """Parse lesson content into sections"""
    sections = {}
    current_section = None
    current_content = []
    
    if not content:
        return sections
        
    for line in content.split('\n'):
        if any(section in line for section in ["Overview:", "Learning Objectives:", "Required Materials:", 
                                             "Preparation Steps:", "Lesson Procedure:", 
                                             "Extensions and Modifications:", "Assessment Criteria:", 
                                             "Safety Considerations:", "Take-Home Connection:"]):
            if current_section:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = line.strip()
            current_content = []
        elif current_section and line.strip():
            current_content.append(line.strip())
    
    # Add the last section
    if current_section and current_content:
        sections[current_section] = '\n'.join(current_content).strip()
    
    return sections

def display_lesson_plan_view(lesson_data):
    """Display the lesson plan in view mode"""
    if not lesson_data:
        st.warning("No lesson plan to display.")
        return
        
    st.header("Lesson Plan View")
    
    # Display metadata in a clean card format
    st.markdown("""
    <style>
    .metadata-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        color: #1f2937;
    }
    .section-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 15px;
        border: 1px solid #e9ecef;
        color: #1f2937;
    }
    .section-title {
        color: #1f2937;
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .section-content {
        color: #374151;
        line-height: 1.6;
    }
    .metadata-card p {
        color: #374151;
        margin: 8px 0;
    }
    .metadata-card h3 {
        color: #1f2937;
        margin-bottom: 15px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Metadata section
    st.markdown(f"""
    <div class="metadata-card">
        <h3>Lesson Details</h3>
        <p><strong>Grade Level:</strong> {lesson_data.get('grade_level', 'N/A')}</p>
        <p><strong>Subject:</strong> {lesson_data.get('subject_area', 'N/A')} - {lesson_data.get('specific_topic', 'N/A')}</p>
        <p><strong>Delivery Timeline:</strong> {lesson_data.get('delivery_timeline', 'N/A')}</p>
        <p><strong>Objectives:</strong> {lesson_data.get('objectives', 'N/A')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Parse and display sections
    sections = parse_lesson_sections(lesson_data.get('content', ''))
    
    for section, content in sections.items():
        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">{section}</div>
            <div class="section-content">{content.replace('\n', '<br>')}</div>
        </div>
        """, unsafe_allow_html=True)

def display_lesson_plan_edit(lesson_data):
    """Display the lesson plan in edit mode with editable sections"""
    if not lesson_data:
        st.warning("No lesson plan to edit.")
        return
        
    st.header("Edit Lesson Plan")
    
    # Display metadata
    st.markdown(f"""
    **Grade Level:** {lesson_data.get('grade_level', 'N/A')}  
    **Subject:** {lesson_data.get('subject_area', 'N/A')} - {lesson_data.get('specific_topic', 'N/A')}  
    **Delivery Timeline:** {lesson_data.get('delivery_timeline', 'N/A')}  
    **Objectives:** {lesson_data.get('objectives', 'N/A')}
    """)

    # Split content into sections and display with edit capabilities
    sections = parse_lesson_sections(lesson_data.get('content', ''))
    
    for section, content in sections.items():
        with st.expander(f"📝 {section}", expanded=True):
            col1, col2 = st.columns([4, 1])
            
            with col1:
                edited_content = st.text_area(
                    f"Edit {section}",
                    value=content,
                    key=f"edit_{section}",
                    height=200
                )
                
                if edited_content != content:
                    sections[section] = edited_content
                    # Update the full content
                    updated_content = []
                    for s, c in sections.items():
                        updated_content.extend([s, c.strip(), ""])
                    lesson_data['content'] = '\n'.join(updated_content)
            
            with col2:
                if st.button("🔄 Regenerate", key=f"regen_{section}"):
                    with st.spinner(f"Regenerating {section}..."):
                        context = {
                            'grade_level': lesson_data.get('grade_level'),
                            'subject_area': lesson_data.get('subject_area'),
                            'specific_topic': lesson_data.get('specific_topic'),
                            'delivery_timeline': lesson_data.get('delivery_timeline')
                        }
                        new_content = regenerate_section(section, context)
                        if new_content:
                            sections[section] = new_content
                            updated_content = []
                            for s, c in sections.items():
                                updated_content.extend([s, c.strip(), ""])
                            lesson_data['content'] = '\n'.join(updated_content)
                            st.success(f"{section} regenerated!")
                            st.experimental_rerun()

def main():
    st.title("📝 Project-Based Curriculum Builder")
    st.write("Generate customized project-based lesson plans aligned with educational standards")
    
    # Sidebar inputs
    with st.sidebar:
        st.header("Lesson Parameters")
        
        # View/Edit mode toggle
        view_mode = st.radio("Display Mode", ["Edit", "View"], key="view_mode")
        st.session_state.current_view = view_mode.lower()
        
        grade_level = st.selectbox("Grade Level", GRADE_LEVELS)
        subject_area = st.selectbox("Subject Area", list(SUBJECT_AREAS.keys()))
        specific_topic = st.selectbox("Specific Topic", SUBJECT_AREAS[subject_area])
        
        # Custom topic input if 'Other' is selected
        if specific_topic == "Custom Topic":
            specific_topic = st.text_input("Enter Specific Topic", value="")
        
        delivery_timeline = st.selectbox("Delivery Timeline", DELIVERY_OPTIONS)
        
        materials_budget = st.number_input(
            "Materials Budget ($)", 
            min_value=0, 
            max_value=1000, 
            value=50
        )
        
        objectives = st.text_area(
            "Learning Objectives",
            placeholder="Enter 2-3 specific learning objectives..."
        )
        
        generate_button = st.button("Generate Lesson Plan", type="primary")
        
        if generate_button:
            if not objectives:
                st.error("Please enter learning objectives before generating the lesson plan.")
            else:
                with st.spinner("Generating your project-based lesson plan..."):
                    lesson_plan = generate_lesson_plan(
                        grade_level,
                        subject_area,
                        specific_topic,
                        delivery_timeline,
                        objectives,
                        materials_budget
                    )
                    
                    if lesson_plan:
                        new_lesson = {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "grade_level": grade_level,
                            "subject_area": subject_area,
                            "specific_topic": specific_topic,
                            "delivery_timeline": delivery_timeline,
                            "objectives": objectives,
                            "materials_budget": materials_budget,
                            "content": lesson_plan
                        }
                        st.session_state.current_lesson = new_lesson
                        st.session_state.generated_lessons.append(new_lesson.copy())
                        st.success("Lesson plan generated successfully!")

    # Main content area
    if st.session_state.current_lesson:
        # Display lesson plan based on current view mode
        if st.session_state.current_view == "edit":
            display_lesson_plan_edit(st.session_state.current_lesson)
        else:
            display_lesson_plan_view(st.session_state.current_lesson)
        
    
# Download button
        st.download_button(
            label="Download Lesson Plan",
            data=json.dumps(st.session_state.current_lesson, indent=2),
            file_name=f"lesson_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
        
        # Lesson history
        if st.session_state.generated_lessons:
            st.sidebar.header("Lesson History")
            for idx, lesson in enumerate(reversed(st.session_state.generated_lessons)):
                if st.sidebar.button(
                    f"{lesson['subject_area']} - {lesson['specific_topic']} ({lesson['timestamp']})",
                    key=f"history_{idx}"
                ):
                    st.session_state.current_lesson = lesson.copy()
                    st.experimental_rerun()

if __name__ == "__main__":
    main()
