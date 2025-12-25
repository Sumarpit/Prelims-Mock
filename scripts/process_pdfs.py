import os
import json
import re
import PyPDF2
from datetime import datetime

# Directories
UPLOAD_DIR = 'uploads'
TESTS_DIR = 'tests'
MANIFEST_FILE = 'tests/test_manifest.json'

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return text

def parse_questions(text):
    questions = []
    
    # 1. Split text into Question Blocks
    # Looks for "Q.1)", "Q. 1)", "1.", etc. at the start of a line
    raw_blocks = re.split(r'(?:\n|^)(?:Q\.|Q\s|Question\s)?\d+[\.\)]\s+', text)

    for block in raw_blocks:
        if not block.strip():
            continue

        # 2. Extract Question Text
        # Stop capturing when we hit options (a) or (A) or A.
        q_text_match = re.search(r'(.*?)(?=\n\s*[\(]?[a-zA-Z][\)\.]\s)', block, re.DOTALL)
        
        # Fallback: Look for "Ans)" or "Exp)" if options are malformed
        if not q_text_match:
            q_text_match = re.search(r'(.*?)(?=\n\s*(?:Ans|Exp))', block, re.DOTALL | re.IGNORECASE)

        q_text = q_text_match.group(1).strip() if q_text_match else block.split('\n')[0]

        # 3. Extract Options
        options = []
        option_pattern = re.compile(r'(?:^|\n)\s*[\(]?([a-dA-D])[\)\.]\s+(.*?)(?=\n\s*[\(]?[a-dA-D][\)\.]|\n\s*(?:Ans|Explanation|Exp)|$)', re.DOTALL)
        found_options = option_pattern.findall(block)
        
        for label, opt_text in found_options:
            options.append(opt_text.strip())

        # 4. Extract Answer
        # Looks for "Ans) c" or "Answer: c"
        ans_match = re.search(r'(?:Ans|Answer)\w*[\s:\-\.]+\(?([a-dA-D])\)?', block, re.IGNORECASE)
        correct_option = ans_match.group(1).lower() if ans_match else None
        
        correct_idx = -1
        if correct_option:
            mapping = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
            correct_idx = mapping.get(correct_option, -1)

        # 5. Extract Explanation
        # Accepts "Exp)", "Explanation:", "Solution:"
        explanation = ""
        exp_match = re.search(r'(?:Explanation|Solution|Ans\s+Detail|Exp)[\s:\-\.\)]+(.*)', block, re.DOTALL | re.IGNORECASE)
        if exp_match:
            explanation = exp_match.group(1).strip()
        
        # Only add valid questions
        if len(options) >= 2:
            q_obj = {
                "id": len(questions) + 1,
                "text": q_text,
                "options": options,
                "correctAnswer": correct_idx,
                "explanation": explanation,
                "topic": "General Studies" # Default topic
            }
            questions.append(q_obj)

    return questions

def update_manifest(json_filename, test_name):
    manifest = []
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            manifest = []

    # Check duplicates
    if not any(item['file'] == json_filename for item in manifest):
        new_entry = {
            "name": test_name,
            "filename": json_filename,
            "qCount": 0
        }
        manifest.append(new_entry)
        
        with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

def main():
    if not os.path.exists(UPLOAD_DIR):
        print(f"Directory {UPLOAD_DIR} not found.")
        return

    if not os.path.exists(TESTS_DIR):
        os.makedirs(TESTS_DIR)

    files_processed = 0
    
    for filename in os.listdir(UPLOAD_DIR):
        if filename.lower().endswith('.pdf'):
            filepath = os.path.join(UPLOAD_DIR, filename)
            print(f"Processing: {filename}")
            
            raw_text = extract_text_from_pdf(filepath)
            new_questions = parse_questions(raw_text)
            
            if new_questions:
                json_filename = os.path.splitext(filename)[0] + '.json'
                json_path = os.path.join(TESTS_DIR, json_filename)
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(new_questions, f, indent=2)
                
                print(f"Created: {json_path} ({len(new_questions)} questions)")
                
                test_title = os.path.splitext(filename)[0].replace('-', ' ').replace('_', ' ')
                update_manifest(json_filename, test_title)
                files_processed += 1
            
            os.remove(filepath) # Cleanup PDF
            print(f"Deleted PDF: {filename}")

    if files_processed == 0:
        print("No new valid questions found.")

if __name__ == "__main__":
    main()
  
