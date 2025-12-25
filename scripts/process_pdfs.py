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
                # Basic extraction
                page_text = page.extract_text()
                
                # Remove Page Numbers strictly (e.g., [24], --- PAGE 2 ---)
                page_text = re.sub(r'\[\d+\]', '', page_text)
                page_text = re.sub(r'---\s*PAGE\s*\d+\s*---', '', page_text)
                
                text += page_text + "\n"
    except Exception as e:
        print(f"❌ Error reading {pdf_path}: {e}")
    return text

def clean_garbage_text(text):
    """
    Removes specific Forum IAS headers, footers, and address blocks.
    """
    # 1. HARDCODED ADDRESS BLOCK REMOVAL
    # We turn the user's provided text into a regex that accepts flexible whitespace (\s+) 
    # to account for PDF line-break weirdness.
    address_parts = [
        r"Forum Learning Centre : Delhi - Plot No\. 36, 4th Floor \(Above Kalyan Jewellers\), Pusa Road, Karol Bagh, New Delhi - 110005",
        r"Patna - 2nd floor, AG Palace, E Boring\s*Canal Road, Patna, Bihar 800001",
        r"Hyderabad - 1st & 2nd Floor, SM Plaza, RTC X Rd, Indira Park Road, Jawahar Nagar, Hyderabad, Telangana 500020",
        r"9311740400, 9311740900",
        r"https://academy\.forumias\.com",
        r"admissions@forumias\.academy",
        r"helpdesk@forumias\.academy"
    ]
    # Join parts with flexible separator matching " | " or newlines
    address_regex = r'.*?'.join(address_parts)
    text = re.sub(address_regex, '', text, flags=re.DOTALL | re.IGNORECASE)

    # 2. REMOVE LINES STARTING WITH "SFG 2026"
    # Matches any line start (^) followed by "SFG 2026" and the rest of the line
    text = re.sub(r'(?m)^SFG 2026.*$', '', text)

    # 3. CLEANUP EXCESS WHITESPACE
    # Collapse multiple newlines created by removals
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text

def format_explanation(text):
    """Inserts HTML formatting for better readability."""
    if not text: return "No explanation provided."

    # Bold Keywords (Statement I, Hence, etc.)
    keywords = [
        "Statement I is correct", "Statement II is correct", 
        "Statement 1 is correct", "Statement 2 is correct",
        "Statement I is incorrect", "Statement II is incorrect",
        "Statement 1 is incorrect", "Statement 2 is incorrect",
        "Hence option .*? is correct", "Thus,", "Therefore,"
    ]
    for kw in keywords:
        text = re.sub(f"(?i)({kw})", r'<br><br><b>\1</b>', text)

    # Handle numbered lists (1. Text... 2. Text...)
    text = re.sub(r'\n\s*(\d+\.)\s+', r'<br><b>\1</b> ', text)

    return text.replace('<br><br><br>', '<br><br>').strip()

def parse_forum_ias(text):
    # Step 1: Clean the document
    text = clean_garbage_text(text)
    
    questions = []
    
    # Step 2: Split into Question Blocks
    blocks = re.split(r'\nQ\.\s*\d+[\)\.]', text)
    if len(blocks) > 0: blocks = blocks[1:] # Skip preamble

    for idx, block in enumerate(blocks):
        try:
            block = block.strip()
            
            # --- 1. EXTRACT EXPLANATION FIRST ---
            # We do this first because the answer might be hidden inside the first line of Exp
            exp_match = re.search(r'(?:Exp|Explanation)[\)\:]\s*(.*)', block, re.DOTALL | re.IGNORECASE)
            explanation = exp_match.group(1).strip() if exp_match else ""

            # --- 2. EXTRACT ANSWER ---
            correct_idx = -1
            
            # Strategy A: Look in "Exp: Option c is the correct answer" (Priority as per request)
            # Regex looks for "Exp... Option X" or just "Option X is the correct answer" at start of Exp
            exp_ans_match = re.match(r'(?:Option\s*)?([a-dA-D])\s+is\s+the\s+correct\s+answer', explanation, re.IGNORECASE)
            
            if exp_ans_match:
                correct_char = exp_ans_match.group(1).lower()
            else:
                # Strategy B: Fallback to standard "Ans) c" tag in the block
                ans_match = re.search(r'(?:Ans|Answer)[\)\:]\s*([a-dA-D])', block, re.IGNORECASE)
                correct_char = ans_match.group(1).lower() if ans_match else None

            if correct_char:
                mapping = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
                correct_idx = mapping.get(correct_char, -1)

            # --- 3. METADATA & CLEANING ---
            subj_match = re.search(r'Subject:\)\s*(.*)', block)
            subject = subj_match.group(1).strip() if subj_match else "General"

            topic_match = re.search(r'Topic:\)\s*(.*)', block)
            topic = topic_match.group(1).strip() if topic_match else "GS"
            
            # Remove Metadata from Explanation
            explanation = re.sub(r'(Subject:\)|Topic:\)|Source:\)).*', '', explanation, flags=re.DOTALL).strip()
            
            # Optional: Remove the "Option c is correct" sentence from the display text if you want it cleaner
            # explanation = re.sub(r'^Option\s+[a-dA-D]\s+is\s+the\s+correct\s+answer[\.\s]*', '', explanation, flags=re.IGNORECASE)

            explanation = format_explanation(explanation)

            # --- 4. EXTRACT QUESTION TEXT & OPTIONS ---
            # Locate start of options (looking for "a)")
            opt_start = re.search(r'\n\s*a[\)\.]', block)
            
            q_text = ""
            options = []
            
            if opt_start:
                q_text = block[:opt_start.start()].strip()
                
                # Limit options search to before the "Ans" or "Exp" starts
                marker_search = re.search(r'\n\s*(?:Ans|Exp)', block[opt_start.start():], re.IGNORECASE)
                end_of_opts = (opt_start.start() + marker_search.start()) if marker_search else len(block)
                
                opts_block = block[opt_start.start():end_of_opts]
                
                # Extract specific options a) b) c) d)
                opt_matches = list(re.finditer(r'(?:^|\n)\s*([a-dA-D])[\)\.]', opts_block))
                for i in range(len(opt_matches)):
                    start = opt_matches[i].end()
                    end = opt_matches[i+1].start() if i + 1 < len(opt_matches) else len(opts_block)
                    options.append(opts_block[start:end].strip())
            else:
                q_text = "Error parsing question text."
                options = ["Parse Error", "Parse Error", "Parse Error", "Parse Error"]

            # Final check to ensure options aren't empty
            if len(options) < 4:
                # Fallback pad if parsing failed
                while len(options) < 4: options.append("-")

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

    files_processed = 0
    for f in os.listdir(UPLOAD_DIR):
        if f.endswith('.pdf'):
            print(f"Processing {f}...")
            text = extract_text_from_pdf(os.path.join(UPLOAD_DIR, f))
            questions = parse_forum_ias(text)
            
            if questions:
                out_name = f.replace('.pdf', '.json')
                with open(os.path.join(TESTS_DIR, out_name), 'w') as out_f:
                    json.dump(questions, out_f, indent=2)
                
                # Make title cleaner
                test_title = f.replace('.pdf', '').replace('-', ' ').replace('_', ' ')
                update_manifest(out_name, test_title)
                print(f"✅ Generated {out_name} ({len(questions)} Qs)")
                
                # Clean up upload
                os.remove(os.path.join(UPLOAD_DIR, f))
                files_processed += 1

    if files_processed == 0:
        print("No PDF files found in uploads/ folder.")

if __name__ == "__main__":
    main()
