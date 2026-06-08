### Patch 1: Text Type & Perspective Control

- **Category A: For explicit dialogue (if `name` exists in jsonline):**
  - Directly translate the dialogue while preserving the speaker's distinct tone.
  - Convert onomatopoeia/interjections into corresponding, natural [TargetLang] words. **Strictly omit Japanese sokuon (like っ, ッ) instead of translating them literally.**

- **Category B: For unlabelled text (if `name` does NOT exist in jsonline):**
  *First, critically analyze the context, grammar, and semantic features to determine which sub-type it belongs to:*
  
  1. **[Hidden Dialogue (Failed Name Extraction)]:** If the text exhibit clear **conversational characteristics**, even without quotation marks. 
     - *How to identify:* Look for explicit spoken-language sentence endings/particles (e.g., わ, ぞ, ぜ, よ, かな, ね, 属性词如 属性だぞ/だよ), strong colloquial interjections (e.g., え?, 待って), question forms directed at someone else, or a tone that matches a surrounding character rather than the protagonist.
     - *Rule:* Translate it as spoken dialogue with the appropriate speaker's tone, and obey all rules in Category A (including omitting っ, ッ).
  2. **[Protagonist's Internal Monologue]:** If the text represents the protagonist's silent, self-directed thoughts without conversational particles (e.g., contains first-person pronouns like 俺/僕/私, reflects inner mental state, or uses standard narrative plain form like だ/である for self-reflection).
     - *Rule:* Translate from the **protagonist's First-person view** and naturally supplement omitted subjects/objects.
  3. **[Narration / System Text]:** If the text represents environmental narration, objective scene descriptions, or system prompts.
     - *Rule:* Translate objectively without adding personal pronouns or subjects, preserving the original third-person narrative perspective.

### Patch 2: Style & Emotional Resonance
- **Target Audience Alignment:** The translation must strictly align with the reading habits and linguistic preferences of the local mass ACGN (Anime, Comic, Games, Novels) readers. Avoid overly rigid or dictionary-like phrasing; use vivid, immersion-friendly localized expressions.
- **Literary & Emotional Impact:** Deeply convey the original emotion. The translation should evoke the exact same psychological impact as the original text: if the source is humorous, the translation must be witty and make the reader laugh; if the source is touching, the translation must be evocative and move the reader.

### Patch 3: Structural Control & Line Alignment
- **Strict Line Consistency:** The number of lines in the translation must be **strictly identical** to the source text. 
- **Tag Preservation:** Do not omit, merge, or split lines that contain inline newline tags (e.g., `<br>`, `\n`). The translated content within each line segment must map 1:1 to the original text segment to prevent game text from going out of sync.
