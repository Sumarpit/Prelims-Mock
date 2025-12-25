import os
import json
import re
import PyPDF2

# DIRECTORIES
UPLOAD_DIR = 'uploads'
TESTS_DIR = 'tests'
MANIFEST_FILE = 'tests/test_manifest.json'

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                # Remove Page Numbers
                page_text = re.sub(r'\[\d+\]', '', page_text)
                page_text = re.sub(r'---\s*PAGE\s*\d+\s*---', '', page_text)
                text += page_text + "\n"
    except Exception as e:
        print(f"❌ Error reading {pdf_path}: {e}")
    return text

def clean_garbage_text(text):
    """
    Removes Forum IAS specific headers/footers to prevent leaking into questions.
    """
    # 1. REMOVE LINES STARTING WITH "SFG 2026"
    text = re.sub(r'(?m)^SFG 2026.*$', '', text)

    # 2. HARDCODED FOOTER REMOVAL (Aggressive Block Removal)
    # Matches from "Forum Learning Centre" down to "helpdesk@forumias.academy"
    footer_pattern = r'Forum\s+Learning\s+Centre\s*:.*?helpdesk@forumias\.academy'
    text = re.sub(footer_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # 3. Specific Strings cleanup (Safety net)
    garbage_strings = [
        "9311740400, 9311740900", "https://academy.forumias.com",
        "admissions@forumias.academy", "helpdesk@forumias.academy",
        "Plot No. 36, 4th Floor", "Hyderabad - 1st & 2nd Floor, SM Plaza",
        "Subtopic:)"
    ]
    for junk in garbage_strings:
        text = text.replace(junk, '')

    # 4. Collapse extra newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def format_text_structure(text):
    """
    Formats Question Text and Explanation to have proper line breaks 
    for Statements (I, II) and Lists (1, 2).
    """
    if not text: return ""

    # 1. Format "Statement I:", "Statement 1:"
    # Adds a double break before and bold tags
    patterns = [
        r"(Statement\s+[IVX]+[:\.]?)",  # Statement I
        r"(Statement\s+\d+[:\.]?)"      # Statement 1
    ]
    for pat in patterns:
        text = re.sub(pat, r'<br><br><b>\1</b>', text, flags=re.IGNORECASE)

    # 2. Format Numbered Lists "1. ", "2. ", "I. ", "II. "
    # Looks for Newline -> Number/Roman -> Dot/Paren
    list_patterns = [
        r'(?:\n|^)\s*(\d+[\.\)])\s+',       # 1. or 1)
        r'(?:\n|^)\s*([IVX]+[\.\)])\s+',    # I. or I)
        r'(?:\n|^)\s*([a-z][\.\)])\s+'      # a. or a) (rare in q-text but possible)
    ]
    for pat in list_patterns:
        text = re.sub(pat, r'<br><b>\1</b> ', text)

    # 3. Clean up messy breaks
    text = text.replace('<br><br><br>', '<br><br>')
    if text.startswith('<br>'): text = text[4:]
    
    return text.strip()

def parse_forum_ias(text):
    text = clean_garbage_text(text)
    questions = []
    
    # Split blocks by "Q.<number>)"
    blocks = re.split(r'\nQ\.\s*\d+[\)\.]', text)
    if len(blocks) > 0: blocks = blocks[1:]

    for idx, block in enumerate(blocks):
        try:
            block = block.strip()
            if not block: continue

            # --- 1. EXTRACT EXPLANATION ---
            exp_match = re.search(r'(?:Exp|Explanation)[\)\:]\s*(.*)', block, re.DOTALL | re.IGNORECASE)
            explanation = exp_match.group(1).strip() if exp_match else ""

            # --- 2. EXTRACT ANSWER (Robust) ---
            correct_idx = -1
            
            # Priority: Look inside Explanation first
            exp_ans_match = re.search(r'(?:Option\s*)?([a-dA-D])\s+is\s+the\s+correct\s+answer', explanation, re.IGNORECASE)
            
            if exp_ans_match:
                correct_char = exp_ans_match.group(1).lower()
            else:
                # Fallback: Look for "Ans) c" tag
                ans_match = re.search(r'(?:Ans|Answer)[\)\:]\s*([a-dA-D])', block, re.IGNORECASE)
                correct_char = ans_match.group(1).lower() if ans_match else None

            if correct_char:
                mapping = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
                correct_idx = mapping.get(correct_char, -1)

            # --- 3. CLEAN & FORMAT EXPLANATION ---
            # Remove the "Option c is correct" sentence from display
            explanation = re.sub(r'(?:Option\s*)?[a-dA-D]\s+is\s+the\s+correct\s+answer[\.\s]*', '', explanation, flags=re.IGNORECASE)
            # Remove Metadata tags
            explanation = re.sub(r'(Subject:\)|Topic:\)|Source:\)).*', '', explanation, flags=re.DOTALL).strip()
            # Apply formatting
            explanation = format_text_structure(explanation)

            # --- 4. EXTRACT METADATA ---
            subj_match = re.search(r'Subject:\)\s*(.*)', block)
            subject = subj_match.group(1).strip() if subj_match else "General"
            topic_match = re.search(r'Topic:\)\s*(.*)', block)
            topic = topic_match.group(1).strip() if topic_match else "GS"

            # --- 5. EXTRACT QUESTION TEXT & OPTIONS ---
            # Search for start of options (a) ... or A) ...)
            opt_start = re.search(r'\n\s*a[\)\.]', block)
            
            q_text = ""
            options = []
            
            if opt_start:
                # Question Text is everything before options
                raw_q_text = block[:opt_start.start()].strip()
                q_text = format_text_structure(raw_q_text)

                # Limit options block
                marker_search = re.search(r'\n\s*(?:Ans|Exp)', block[opt_start.start():], re.IGNORECASE)
                end_of_opts = (opt_start.start() + marker_search.start()) if marker_search else len(block)
                opts_block = block[opt_start.start():end_of_opts]
                
                # Regex for Options
                opt_matches = list(re.finditer(r'(?:^|\n)\s*([a-dA-D])[\)\.]', opts_block))
                for i in range(len(opt_matches)):
                    start = opt_matches[i].end()
                    end = opt_matches[i+1].start() if i + 1 < len(opt_matches) else len(opts_block)
                    options.append(opts_block[start:end].strip())
            else:
                q_text = "Error parsing question."
                options = ["Parse Error", "Parse Error", "Parse Error", "Parse Error"]

            # Ensure 4 options exist to prevent "undefined"
            while len(options) < 4: options.append("Option Missing in PDF")

            q_obj = {
                "id": idx + 1,
                "text": q_text,
                "options": options,
                "correctAnswer": correct_idx,
                "explanation": explanation,
                "subject": subject,
                "topic": topic
            }
            questions.append(q_obj)

        except Exception as e:
            print(f"Error parsing Q{idx+1}: {e}")

    return questions

def update_manifest(filename, test_name):
    manifest = []
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, 'r') as f:
                manifest = json.load(f)
        except:
            manifest = []

    found = False
    for entry in manifest:
        if entry['filename'] == filename:
            entry['name'] = test_name
            found = True
            break
    
    if not found:
        manifest.append({"name": test_name, "filename": filename})

    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)

def main():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        return
    if not os.path.exists(TESTS_DIR):
        os.makedirs(TESTS_DIR)

    for f in os.listdir(UPLOAD_DIR):
        if f.endswith('.pdf'):
            print(f"Processing {f}...")
            text = extract_text_from_pdf(os.path.join(UPLOAD_DIR, f))
            questions = parse_forum_ias(text)
            
            if questions:
                out_name = f.replace('.pdf', '.json')
                with open(os.path.join(TESTS_DIR, out_name), 'w') as out_f:
                    json.dump(questions, out_f, indent=2)
                
                test_title = f.replace('.pdf', '').replace('-', ' ').replace('_', ' ')
                update_manifest(out_name, test_title)
                print(f"✅ Generated {out_name} ({len(questions)} Qs)")
                os.remove(os.path.join(UPLOAD_DIR, f))

if __name__ == "__main__":
    main()
