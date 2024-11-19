import streamlit as st
import os
import random
import time
from groq import Groq
from googlesearch import search
from typing import List, Dict, Any, Tuple
import streamlit.components.v1 as components
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse
import re
import streamlit.components.v1 as components

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SearchResult:
    def __init__(self, content: str, url: str, title: str = ""):
        self.content = content
        self.url = url
        self.title = title
        self.timestamp = datetime.now()

def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    # Remove special characters
    text = re.sub(r'[^\w\s.,!?-]', '', text)
    return text

def extract_numbers_and_stats(text: str) -> List[str]:
    """Extract numerical facts and statistics from text."""
    # Match percentages, numbers with units, and other numerical patterns
    patterns = [
        r'\d+(?:\.\d+)?%',  # Percentages
        r'\$\d+(?:,\d{3})*(?:\.\d+)?',  # Money
        r'\d+(?:,\d{3})*(?:\.\d+)?\s*(?:million|billion|trillion)',  # Large numbers
        r'\d+(?:,\d{3})*(?:\.\d+)?\s*[A-Za-z]+',  # Numbers with units
    ]
    
    stats = []
    for pattern in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            # Get some context around the number
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            context = text[start:end].strip()
            stats.append(context)
    
    return stats

def search_topic(query: str, num_results: int = 3) -> Tuple[List[SearchResult], List[str], str]:
    """
    Search for information about the topic and return processed results with error handling.
    Returns: (search_results, stats, error_message)
    """
    search_results = []
    all_stats = []
    error_message = ""

    try:
        for url in search(query + " statistics facts research",start=0,stop =3 ): #, num_results=num_results
            try:
                # Parse domain for source attribution
                domain = urlparse(url).netloc
                
                # Fetch webpage with timeout
                response = requests.get(url, timeout=5, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                response.raise_for_status()
                
                # Parse content
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try to get title
                title = soup.title.string if soup.title else domain
                
                # Extract main content
                # Remove scripts, styles, and nav elements
                for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()
                
                # Get paragraphs
                paragraphs = soup.find_all('p')[:3]  # First 3 paragraphs
                content = ' '.join([p.text for p in paragraphs])
                content = clean_text(content)
                
                if content:
                    # Extract statistics and numerical facts
                    stats = extract_numbers_and_stats(content)
                    all_stats.extend(stats)
                    
                    # Create search result object
                    result = SearchResult(
                        # content=content[:500] + "..." if len(content) > 500 else content,
                        content =  content,
                        url=url,
                        title=title
                    )
                    search_results.append(result)
                    logger.info(f"Successfully processed URL: {url}")
                
            except requests.RequestException as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                continue
                
        if not search_results:
            error_message = "No search results could be processed successfully."
            logger.warning(error_message)
            
    except Exception as e:
        error_message = f"Error performing search: {str(e)}"
        logger.error(error_message)
    
    return search_results, all_stats, error_message

def format_search_results(results: List[SearchResult], stats: List[str], error_msg: str) -> str:
    """Format search results and statistics into a readable format."""
    if error_msg:
        return f"Note: {error_msg}\n\n"
    
    formatted = "Relevant Information:\n\n"
    
    # Add key statistics if available
    if stats:
        formatted += "Key Facts & Figures:\n"
        for stat in list(set(stats))[:5]:  # Top 5 unique stats
            formatted += f"• {stat}\n"
        formatted += "\n"
    
    # Add source summaries
    formatted += "Sources:\n"
    for result in results:
        formatted += f"• {result.title}\n"
        formatted += f"  Summary: {result.content[:200]}...\n"
        formatted += f"  Source: {result.url}\n\n"
    
    return formatted
# Utility class for model participants
class ModelParticipant:
    def __init__(self, model_id: str, style: str, stance: str, expertise: List[str], position: Dict[str, float]):
        self.model_id = model_id
        self.style = style
        self.stance = stance
        self.expertise = expertise
        self.last_spoke = 0
        self.points_made = set()
        self.position = position



def generate_prompt_for_stance(participant: ModelParticipant, topic: str, round_num: int, discussion_context: str, search_results: str) -> str:
    """Generate an appropriate prompt based on the model's stance and style, now including search results."""
    
    if participant.stance == "positive":
        stance_guide = """
        - Express enthusiasm about the potential benefits
        - Use the provided statistics and research to support your points
        - Share specific examples and data to back your positive stance
        - Cite sources when mentioning statistics"""
    elif participant.stance == "negative":
        stance_guide = """
        - Point out potential risks or challenges using data
        - Share specific concerns backed by research
        - Use statistics to illustrate your concerns
        - Cite sources for any numbers or research mentioned"""
    else:  # neutral
        stance_guide = """
        - Consider both advantages and disadvantages using data
        - Offer a balanced perspective supported by research
        - Present statistics from both sides
        - Cite sources for balanced analysis"""

    return f"""You are in Round {round_num} of a group discussion about '{topic}'.
Keep your response focused (3-4 sentences) and {participant.style}.

Research and Statistics Available:
{search_results}

Given your {participant.stance} stance on this topic:
{stance_guide}

Previous discussion context:
{discussion_context}

Format your response to include:
1. Your main point
2. Supporting statistics with source attribution
3. A brief conclusion

Your response:"""


def get_custom_css():
    return """
    <style>
    .discussion-container {
        display: flex;
        flex-direction: column;
        gap: 20px;
        padding: 20px;
        max-width: 1200px;
        margin: 0 auto;
    }
    
    .round-table {
        position: relative;
        width: 800px; /* Adjust width for a rectangle */
        height: 400px; /* Adjust height for a rectangle */
        margin: 20px auto;
        background: #f0f2f6; /* Background color */
        border: 2px solid #464646; /* Border styling */
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2); /* Optional shadow for better aesthetics */
    }
        
    .model-avatar {
        position: absolute;
        width: 80px;
        height: 80px;
        border-radius: 50%;
        background: #2d4059;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .model-avatar.speaking {
        background: #ea5455;
        transform: scale(1.1);
        box-shadow: 0 0 20px rgba(234, 84, 85, 0.5);
    }
    
    .speech-bubble {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        border-radius: 10px;
        padding: 15px;
        max-width: 500px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        z-index: 100;
    }
    
    /* History Popup Styles */
    .history-popup {
        display: none;
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 80%;
        max-width: 800px;
        max-height: 80vh;
        background: white;
        border-radius: 15px;
        box-shadow: 0 5px 30px rgba(0,0,0,0.3);
        z-index: 1000;
        overflow-y: auto;
        padding: 20px;
    }
    
    .history-popup.show {
        display: block;
    }
    
    .popup-overlay {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 999;
    }
    
    .popup-overlay.show {
        display: block;
    }
    
    .close-popup {
        position: absolute;
        top: 10px;
        right: 10px;
        font-size: 24px;
        cursor: pointer;
        color: #666;
    }
    
    .chat-message {
        margin: 10px 0;
        padding: 15px;
        border-radius: 8px;
        background: #f8f9fa;
    }
    
    .source-link {
        color: #0066cc;
        text-decoration: underline;
        font-size: 0.9em;
        margin-left: 10px;
    }
    
    .stats-box {
        background: #f0f8ff;
        border-left: 4px solid #0066cc;
        padding: 10px;
        margin: 5px 0;
        font-size: 0.9em;
    }
    
    .stance-positive { border-left: 4px solid #28a745; }
    .stance-negative { border-left: 4px solid #dc3545; }
    .stance-neutral { border-left: 4px solid #ffc107; }
    
    .view-history-btn {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: #2d4059;
        color: white;
        padding: 10px 20px;
        border-radius: 20px;
        cursor: pointer;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    </style>
    
    <script>
    function toggleHistory() {
        document.querySelector('.history-popup').classList.toggle('show');
        document.querySelector('.popup-overlay').classList.toggle('show');
    }
    </script>
    """

def get_discussion_html(participants: Dict[str, ModelParticipant], current_speaker: str, current_message: str, discussion_history: list):
    html = get_custom_css()
    
    # Main discussion container
    html += '<div class="discussion-container">'
    
    # Round table
    html += '<div class="round-table">'
    for model_id, participant in participants.items():
        x = participant.position['x']
        y = participant.position['y']

        bubble_x = x + (80 - 250) / 2  # Center horizontally (assuming bubble width is 250px)
        bubble_y = y + (80 - 100) / 2  # Center vertically (assuming bubble height is 100px)

        speaking_class = "speaking" if model_id == current_speaker else ""
        
        html += f"""
        <div class="model-avatar {speaking_class}"
             style="left: {x}px; top: {y}px;"
             id="{model_id}-avatar">
            {model_id.split('-')[0].upper()}
        </div>
        """

        
        if model_id == current_speaker:
            #     html += f"""
            # <div class="speech-bubble"
            #     style="left: {bubble_x}px; top: {bubble_y}px;">
            #     {current_message}
            # </div>
            # """
                html += f"""
                        <div class="speech-bubble">
                            {current_message}
                        </div>
                        """
    html += '</div>'
    
    # Popup History
    html += """
    <div class="popup-overlay" onclick="toggleHistory()"></div>
    <div class="history-popup">
        <div class="close-popup" onclick="toggleHistory()">&times;</div>
        <h2>Discussion History</h2>
    """
    
    for entry in discussion_history:
        html += f"""
        <div class="chat-message stance-{entry['stance']}">
            <strong>{entry['timestamp']} - {entry['model']}</strong>
            <div class="message-content">
                {entry['message']}
            </div>
            """
        if 'sources' in entry:
            html += '<div class="stats-box">'
            for stat in entry['stats']:
                html += f'<div>{stat}</div>'
            html += '</div>'
            for source in entry['sources']:
                html += f'<a href="{source}" class="source-link" target="_blank">Source</a>'
        html += '</div>'
    
    html += '</div>'
    
    # View History Button
    html += '<div class="view-history-btn" onclick="toggleHistory()">View Discussion History</div>'
    
    html += '</div>'
    return html



def init_session_state():
    if 'discussion_history' not in st.session_state:
        st.session_state.discussion_history = []
    if 'current_speaker' not in st.session_state:
        st.session_state.current_speaker = None
    if 'current_message' not in st.session_state:
        st.session_state.current_message = ""
    if 'view_container' not in st.session_state:
        st.session_state.view_container = st.empty()

def main():
    st.set_page_config(layout="wide", page_title="AI Group Discussion")
    # init_session_state()
    view_container = st.empty()
    


    available_models = {
        "llama-3.1-70b-versatile": {
            "expertise": ["technology", "data analysis"],
            "position": {"x": 0, "y": 0}  # Top edge
        },
        "gemma2-9b-it": {
            "expertise": ["future trends", "innovation"],
            "position": {"x": 720, "y": 0}  # Right edge
        },
        "gemma-7b-it": {
            "expertise": ["practical applications", "risk assessment"],
            "position": {"x": 0, "y": 320}  # Bottom edge
        },
        "llama-3.1-8b-instant": {
            "expertise": ["biology", "politics"],
            "position": {"x": 716, "y": 316}  # Left edge
        }
    }
        
    # Sidebar configuration
    st.sidebar.title("Discussion Configuration")
    
    # API Key configuration
    api_key = st.sidebar.text_input("Enter Groq API Key", type="password")
    if not api_key:
        st.warning("Please enter your Groq API Key to continue.")
        return
    
    # Initialize Groq client
    client = Groq(api_key=api_key)
    
    # Topic input
    topic = st.sidebar.text_input("Enter Discussion Topic", "Impact of AI on Society")
    

    # Model selection and stance configuration
    selected_models = []
    model_stances = {}
    
    st.sidebar.subheader("Select Models and Their Stances")
    for model_id in available_models.keys():
        if st.sidebar.checkbox(f"Include {model_id}", True):
            selected_models.append(model_id)
            stance = st.sidebar.radio(
                f"Stance for {model_id}",
                ["positive", "neutral", "negative"],
                key=f"stance_{model_id}"
            )
            model_stances[model_id] = stance
    
    if st.sidebar.button("Start Discussion"):
        if not selected_models:
            st.error("Please select at least one model.")
            return
            
        # Initialize participants...
        participants = {
            model_id: ModelParticipant(
                model_id=model_id,
                style="analytical",
                stance=model_stances[model_id],
                expertise=available_models[model_id]["expertise"],
                position=available_models[model_id]["position"]
            )
            for model_id in selected_models
        }
        
        st.title("AI Group Discussion")
        st.subheader(f"Topic: {topic}")
        
        discussion_context = f"Topic: {topic}"
        discussion_history = []
        
        # Simulate discussion
        for round_num in range(3):
            for model_id in selected_models:
                participant = participants[model_id]
                
                try:

                    # Get relevant search results for the topic
                    search_results, stats, _ = search_topic(f"{topic} research statistics {participant.stance}")
                    search_context = format_search_results(search_results, stats, "")


                    # Generate response using Groq...
                    prompt = generate_prompt_for_stance(
                        participant,
                        topic,
                        round_num + 1,
                        discussion_context,
                        search_context
                    )
                    
                    response = client.chat.completions.create(
                        model=model_id,
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": "Your response:"}
                        ],
                        max_tokens=100,
                        temperature=0.7
                    )
                    
                    message = response.choices[0].message.content.strip()
                    current_speaker = model_id
                    current_message = message
                    
                    # Update discussion context
                    discussion_context += f"\n{model_id}: {message}"
                    
                    # Update discussion history
                    discussion_history.append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "model": model_id,
                        "stance": participant.stance,
                        "message": message,
                        "stats": stats[:3] if stats else [],
                        "sources": [result.url for result in search_results[:2]] if search_results else []
                    })
                    
                    # Update the single view container
                    html_content = get_discussion_html(
                        participants,
                        current_speaker,
                        current_message,
                        discussion_history
                    )
                    
                    with view_container:
                        components.html(html_content, height=1000)
                    # Use the same container for updates
                    # view_container.html(html_content, height=1000)
                    
                    time.sleep(2)  # Pause between responses
                
                except Exception as e:
                    st.error(f"Error with model {model_id}: {str(e)}")

if __name__ == "__main__":
    main()