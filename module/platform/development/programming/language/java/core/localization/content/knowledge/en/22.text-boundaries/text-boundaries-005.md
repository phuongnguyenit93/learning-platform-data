# Why Whitespace Is Not Enough to Split Words for Every Language

In many introductory Java examples, programmers split words with `text.split(" ")` or `text.split("\\s+")`. This approach can be useful if the input data is **explicitly specified as a space-delimited list of items**, but it is **not a multilingual word segmentation algorithm**. A "word" in natural language is not necessarily surrounded by U+0020 SPACE characters.

Cases that must be distinguished:

- **Chinese, Japanese, Thai, and several other scripts** can write strings containing multiple words **without placing spaces between each word**.
- **Vietnamese** usually has spaces between **syllables**, yet a single **lexical word** can consist of multiple syllables such as `"học sinh"` or `"công nghệ thông tin"`. Splitting by spaces is not equivalent to identifying lexical words.
- **Punctuation** can sit directly adjacent to letters, e.g., `Hello,world!`, needing no spaces while still having meaningful boundaries.
- **Apostrophes, hyphens, and abbreviations** are not always word split points: `don't`, `l'amour`, `e-mail`, and `U.S.A.` require specific policies depending on the task.
- **Unicode whitespace** is not limited to U+0020; U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE, and U+3000 IDEOGRAPHIC SPACE serve different purposes.
- **Combining marks, emojis, and surrogate pairs** remind us that code unit, code point, grapheme cluster, and word boundaries are **different layers**.

In Java 17+, `java.text.BreakIterator` provides locale-based **word**, **sentence**, **character**, and **line** boundary iterators. However, `BreakIterator` does not guarantee that every word sequence is split according to the dictionary, semantics, or NLP requirements of every language either. This lesson distinguishes **data-field splitting**, **whitespace splitting**, **word boundary detection**, and **language-specific word segmentation**, and guides you in choosing the right API.

## 1. First, "Word" Can Mean Several Things

In programming, the term "word" is commonly used for at least four different problems:

| Goal | What Actually Needs to Be Split | Example |
| --- | --- | --- |
| Reading a line of space-separated codes | **Data fields** by delimiter | `red blue green` |
| Allowing users to double-click to select | **Text segment with word boundaries** | Selecting `world` in `Hello, world!` |
| Counting lexical words in a sentence | **Linguistic word units** | The phrase `"học sinh"` can be one lexical unit |
| Generating tokens for search/AI | **Tokens per search engine or model rules** | Tokens may be words, n-grams, subwords, or characters |

No single `split(" ")` call solves all four goals at once. A string with three space-separated groups does **not necessarily** have three lexical words. Conversely, an unspaced Chinese sentence can contain many words with **no internal spaces**.

**First design question:** "Am I splitting by a **protocol delimiter**, or trying to identify **words in natural language**?" If it is a protocol with a defined delimiter, `split` per the specification may be right. If it is multilingual natural text, you need a text-boundary solution and possibly a dictionary/language model.

## 2. What Does `String.split(" ")` Actually Do?

`String.split(String regex)` accepts a **regular expression**, not a word-finding algorithm. The string `" "` here is a regex matching a single **U+0020 SPACE** character.

Runnable example **`SpaceOnlyDemo.java`**:

~~~java
import java.util.Arrays;

public class SpaceOnlyDemo {
    public static void main(String[] args) {
        String input = "Hello,world! Java 17.";

        System.out.println(
                Arrays.toString(input.split(" ")));
        System.out.println(
                Arrays.toString("one  two".split(" ")));
    }
}
~~~

~~~bash
javac SpaceOnlyDemo.java
java SpaceOnlyDemo
~~~

Output:

~~~text
[Hello,world!, Java, 17.]
[one, , two]
~~~

Explanation:

- `Hello,world!` remains a single field because the comma and exclamation mark do not match the space regex.
- `Java` and `17.` are split because they lie on opposite sides of U+0020.
- Two consecutive spaces in `one  two` produce **an empty element** in the middle when splitting on each single space.
- `String.split(regex)` drops **trailing empty fields** by default because its split algorithm uses limit 0; it is not equivalent to a CSV parser or text tokenizer.

This is the result of **delimiter-character splitting**, not linguistic analysis. If the application's requirement is processing simple machine-generated commands delimited by U+0020, this may be the right choice; if the input is natural language text, it is not.

## 3. `split("\\s+")` Is Better for Some Whitespace, Still Not Enough

In Java source:

~~~java
String[] parts = input.split("\\s+");
~~~

There are **two syntax layers**:

1. `"\\s+"` is a **Java string literal** containing a real backslash before `s`.
2. The regex engine interprets `\s+` as **one or more whitespace characters under the active regex rules**.

Using `+` avoids creating empty elements between consecutive delimiters. However, in default Java regex, `\s` has a whitespace set that **does not cover all of Unicode `White_Space`**. For instance, non-breaking spaces and ideographic spaces used in multilingual text formatting may not match.

To enable Unicode character classes for regex, Java supports `Pattern.UNICODE_CHARACTER_CLASS` or the inline flag `(?U)`:

~~~java
String[] parts = input.split("(?U)\\s+");
~~~

This handles more kinds of Unicode whitespace, **yet still splits only at whitespace**. It does not know how many words a Chinese sentence has, whether `"học sinh"` should be treated as one token, or the semantics of apostrophes/hyphens.

## 4. Unicode Whitespace Characters and Their Meanings

Unicode has multiple whitespace characters for layout, linguistic, and line-breaking control reasons:

| Code point | Name | Situation |
| --- | --- | --- |
| U+0020 | SPACE | Ordinary space |
| U+0009 | CHARACTER TABULATION | Tab between fields/lines |
| U+000A | LINE FEED | Line break |
| U+00A0 | NO-BREAK SPACE | Keeps components on the same line |
| U+202F | NARROW NO-BREAK SPACE | Narrow non-breaking space; often appears in formatted data |
| U+3000 | IDEOGRAPHIC SPACE | Full-width CJK-style space |
| U+2009 | THIN SPACE | Thin space |
| U+200B | ZERO WIDTH SPACE | Special zero-width character; handle separately, **do not treat as ordinary regex whitespace** |

Do not look at the screen and assume every blank gap is U+0020. In currency data, large numbers, dates/times, and localized text, users can encounter U+00A0 or U+202F, which fonts display almost identically to an ordinary space.

### Example Comparing Default and Unicode Regex

Create **`UnicodeWhitespaceDemo.java`**:

~~~java
import java.util.Arrays;

public class UnicodeWhitespaceDemo {
    public static void main(String[] args) {
        String text = "one" + (char) 0x00A0
                + "two" + (char) 0x202F
                + "three" + (char) 0x3000
                + "four";

        System.out.println(
                Arrays.toString(text.split("\\s+")));
        System.out.println(
                Arrays.toString(text.split("(?U)\\s+")));

        System.out.println(
                Character.isWhitespace(0x00A0));
        System.out.println(
                Character.isSpaceChar(0x00A0));
    }
}
~~~

~~~bash
javac UnicodeWhitespaceDemo.java
java UnicodeWhitespaceDemo
~~~

Result in JDK 17 using Unicode regex as described:

~~~text
[one two three　four]
[one, two, three, four]
false
true
~~~

The first line keeps the Unicode whitespace characters **inside a single element**; they can be hard to tell apart in a console. The second line splits into four fields. The last two lines show that `Character.isWhitespace` and `Character.isSpaceChar` are **not the exact same property set** either; U+00A0 is one example.

**The takeaway of this example is not "always split on every Unicode whitespace".** In grouped numbers like `1 234` or proper-name phrases containing a non-breaking space, splitting there can break meaning meant to stay together. Determine whether whitespace is a **data delimiter** or merely a **formatting character**.

## 5. Languages Can Have Many Words Without Spaces Between Them

Chinese, Japanese, Thai, Lao, Khmer, and several other scripts have **whitespace conventions unlike English sentence writing**. For example, Chinese can write multiple words consecutively in a sentence without placing U+0020 at every word boundary.

In Japanese, combinations of kanji, hiragana, and katakana appear right next to one another; word boundaries can depend on morphological analysis and context.

In Thai, spaces are typically used for larger boundaries rather than between individual words in many text styles, so a long sentence may have no spaces between lexical units. Other scripts have their own combinations of spaces, punctuation, and combining marks.

**Consequence of `split(" ")`:** if a string has no U+0020, the result is simply **a single element**, even though a reader perceives many words.

Standalone illustrative code example **`NoSpaceDemo.java`**:

~~~java
import java.util.Arrays;

public class NoSpaceDemo {
    public static void main(String[] args) {
        String chinese = new String(new int[]{
                0x6211, 0x559C, 0x6B22, 0x7F16, 0x7A0B
        }, 0, 5);

        String[] parts = chinese.split(" ");

        System.out.println(parts.length);
        System.out.println(
                chinese.codePointCount(0, chinese.length()));
    }
}
~~~

~~~bash
javac NoSpaceDemo.java
java NoSpaceDemo
~~~

Output:

~~~text
1
5
~~~

The first line only tells you the text has no U+0020 spaces; it does **not** tell you the sentence has one word. The second line reports **five Unicode code points**, which also does **not** mean five words. A "word" can be one or many code points long depending on language and analysis method.

This is why search engines, input methods, spellcheckers, and natural language processing systems usually require **language-aware segmenters** instead of `split`.

## 6. Vietnamese: Spaces Usually Separate Syllables, Not Necessarily Lexical Words

Vietnamese is a very close example for Vietnamese developers: text normally places spaces between **syllables**, yet a **word** in the lexical sense can consist of multiple syllables.

Examples:
- `"học sinh"`;
- `"sinh viên"`;
- `"công nghệ"`;
- `"công nghệ thông tin"`;
- `"thành phố"`.

If we split `"học sinh"` by U+0020, we get two parts `"học"` and `"sinh"`. Yet in many NLP contexts, `"học sinh"` is treated as a single **lexical unit**.

The issue is not the Unicode alphabet; even after splitting all spaces perfectly, **the task of grouping syllables into words remains unsolved**. Deciding that `"sinh viên"` is one word, or detecting other noun phrases, requires dictionaries/context and sometimes statistical models.

Nor can you claim every sequence of multiple adjacent syllables is one word: **lexical word boundaries are a linguistic problem**, not just counting spaces.

### When Is Splitting by Space Still Valid?

If the task is **counting syllables separated by spaces** in a normalized Vietnamese text format, a split rule can fit. However, the result must be accurately labeled as "number of space-separated segments", not relabeled as "exact lexical word count".

For Vietnamese search, tokenization often needs to handle multi-syllable words, tone marks, Unicode normalization, proper names, and abbreviations.

## 7. Punctuation Creates Boundaries Without Spaces

Consider:

~~~text
Hello,world!Java
~~~

Even without U+0020, readers distinguish `Hello`, the comma, `world`, the exclamation mark, and `Java`.

`split(" ")` returns the whole string intact. `split("\\s+")` does too. **Whitespace is not the only signal of word boundaries.**

Yet "split on every punctuation mark" is also wrong in many contexts:
- `don't`: the apostrophe can be part of a single word.
- `l'amour`: the apostrophe plays a role in French orthography.
- `e-mail` or `COVID-19`: hyphens can lie inside a unit that should stay intact.
- `3.14` and `1,234`: periods/commas lie inside numbers and are not always token boundaries.
- Email addresses and URLs contain plenty of punctuation and should not be split arbitrarily if treated as single data units.

**Word splitting is not simply "split on every non-letter".** Splitting on every character failing `Character.isLetter` can break numbers, combining marks, words with apostrophes, and domain-specific tokens.

## 8. Four Boundary Types to Distinguish

In Unicode processing there are multiple segmentation levels:

| Type | Question | Example API |
| --- | --- | --- |
| UTF-16 code unit | Which `char` position? | `String.charAt` |
| Unicode code point | What is the next Unicode code point? | `String.codePoints` |
| Grapheme/character boundary | What is a character cluster users normally manipulate as one character? | `BreakIterator.getCharacterInstance`, certain grapheme-aware regexes |
| Word boundary | Where are boundaries of segments treated as words in text? | `BreakIterator.getWordInstance` |
| Sentence boundary | Where are sentence boundaries? | `BreakIterator.getSentenceInstance` |
| Line-break opportunity | Where can a line wrap? | `BreakIterator.getLineInstance` |

**One code point is not necessarily one visible character**: a letter may carry combining marks, and an emoji may contain multiple code points and zero-width joiners. **One visible character is not necessarily one word**. **One word is not necessarily one NLP token**.

For example, `é` can be one code point U+00E9 or two code points U+0065 + U+0301. Splitting recklessly between them can detach the combining mark from the letter. That issue belongs to **character/grapheme boundaries**, which differs from word splitting.

Therefore, when moving a cursor, highlighting words, counting words, or slicing strings by quota, choose the appropriate level rather than using one algorithm for every task.

## 9. `java.text.BreakIterator`: Locale-Aware Boundary Finder

Java provides:

~~~java
BreakIterator.getWordInstance(Locale locale);
BreakIterator.getSentenceInstance(Locale locale);
BreakIterator.getCharacterInstance(Locale locale);
BreakIterator.getLineInstance(Locale locale);
~~~

This is a **snippet** requiring imports `java.text.BreakIterator` and `java.util.Locale`.

`BreakIterator` performs **boundary analysis** using the data and rules supported by the JDK/locale provider. It returns **boundary positions** in text, not a pre-built list of "guaranteed accurate lexical words".

With `getWordInstance`, the segments produced by the iterator can include:
- letters or digits;
- punctuation;
- spaces;
- symbols that do not form words.

Thus the number of segments the iterator produces is **not always the word count**. You must decide how to filter/read segments according to your needs, and be especially careful with languages that do not separate words with spaces.

## 10. Java 17+ Example Using `BreakIterator` Instead of `split`

Create **`WordBoundaryDemo.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class WordBoundaryDemo {
    public static void main(String[] args) {
        String text = "Hello, world! Java 17.";

        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.ENGLISH);
        iterator.setText(text);

        int wordLikeSegments = 0;
        StringBuilder reconstruction = new StringBuilder();

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String segment = text.substring(start, end);
            reconstruction.append(segment);

            if (segment.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                wordLikeSegments++;
            }
        }

        System.out.println(
                reconstruction.toString().equals(text));
        System.out.println(wordLikeSegments);
    }
}
~~~

~~~bash
javac WordBoundaryDemo.java
java WordBoundaryDemo
~~~

With standard JDK 17 `Locale.ENGLISH` rules, output:

~~~text
true
4
~~~

Calling `iterator.setText(text)` specifies the string to analyze. `iterator.first()` returns the first boundary; `next()` returns the next boundary; `BreakIterator.DONE` signals the end.

The `anyMatch(Character::isLetterOrDigit)` filter is only an **illustrative policy** to count word-like segments. It does **not** turn `BreakIterator` into a lexical word recognizer for all languages. In the example, the four segments containing letters/digits are `Hello`, `world`, `Java`, and `17`.

**Do not discard the remaining segments when you need to reconstruct the sentence:** `reconstruction` proves that concatenating **all** segments in order reproduces the exact original text, including punctuation and spaces. Taking only letter/digit segments means **filtering tokens**, not preserving the original text.

## 11. A Version Printing Boundaries to Understand the Iterator

Create **`BoundarySegmentsDemo.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundarySegmentsDemo {
    public static void main(String[] args) {
        String input = "Hello, world!";

        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.ENGLISH);
        iterator.setText(input);

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String segment = input.substring(start, end);
            System.out.println("[" + segment + "]");
        }
    }
}
~~~

~~~bash
javac BoundarySegmentsDemo.java
java BoundarySegmentsDemo
~~~

Example output on JDK 17 with standard providers:

~~~text
[Hello]
[,]
[ ]
[world]
[!]
~~~

The output demonstrates that **the iterator also returns punctuation and whitespace**. In real systems, exact boundary details can depend on the provider/locale data, especially for complex scripts, so do not hardcode every rule of one JDK version as a universal multilingual truth.

`BreakIterator` returns **UTF-16 offsets**: `substring(start, end)` is the valid way to extract the exact segment pointed to by the iterator. Do not treat `start`/`end` as code point counts or user-visible character counts.

## 12. Locale Affects Segmentation, Without Solving Every Language

You can obtain an iterator for a specific locale:

~~~java
BreakIterator english =
        BreakIterator.getWordInstance(Locale.ENGLISH);

BreakIterator thai =
        BreakIterator.getWordInstance(
                Locale.forLanguageTag("th-TH"));

BreakIterator japanese =
        BreakIterator.getWordInstance(Locale.JAPANESE);
~~~

This is a **snippet**. Passing a locale lets the runtime apply appropriate segmentation rules/data **when supported**.

However, no `BreakIterator.getWordInstance` contract guarantees that it will always:
- pick dictionary-accurate word boundaries for every language;
- understand every Vietnamese compound word lexically;
- resolve every ambiguity among multiple Chinese/Japanese/Thai segmentations;
- accurately extract proper names, medical terms, or search-engine tokens;
- use the exact same dictionary/model across all JDKs/providers.

Even for the same locale, runtime data or service provider implementations can vary. When **real-world NLP quality** is required, evaluate on your target text corpus and linguistic goals, and consider using a **language-specific tokenizer, dictionary segmenter, or NLP model**.

**Rule:** `BreakIterator` is useful for **boundary analysis**, but does not fully replace **linguistic word segmentation**.

## 13. Why Splitting Only by Letters/Digits Is Also Not Enough

A common hand-rolled tokenizer check looks like:

~~~java
boolean isWordChar(int codePoint) {
    return Character.isLetterOrDigit(codePoint);
}
~~~

This is an **in-class snippet**. It has advantages over ASCII regex because `Character.isLetterOrDigit` knows many Unicode categories. Yet it still has limitations:

1. A standalone **combining mark** is neither a letter nor a digit, even though it belongs to an accented character.
2. Apostrophes/hyphens can be part of a word in certain languages or data domains.
3. URLs/emails and numbers with separators need dedicated parsing.
4. Ideographs in CJK text can span many code points and multiple **adjacent** words; every code point being a letter gives no hint of boundaries.
5. Vietnamese compound words have spaces between syllables, so a letter/digit rule still will not group syllables into words.
6. Emojis, hashtags, and mentions may be application tokens yet fail a simple letter/digit rule.

If the task is simply "filter segments with letters or digits after `BreakIterator`", this heuristic may suffice. If the product needs a **search tokenizer**, **accurate lexical word counting**, or **identifier validation**, you must design additional rules.

## 14. Combining Marks, UTF-16, and the Risk of Slicing Across Boundaries

Java stores `String` in UTF-16 units. Non-BMP characters need **two `char`s**, and grapheme clusters can consist of **multiple code points**.

Example of a string with the letter `e` and combining mark U+0301:

~~~java
String accent = "e" + (char) 0x0301;

System.out.println(accent.length());
System.out.println(accent.codePointCount(
        0, accent.length()));
~~~

This is an **in-method snippet**. Output:

~~~text
2
2
~~~

Two code points, yet typically rendered as one accented character. **Slicing between the two code points** can detach the accent from the letter. For ZWJ emoji sequences, many code points can be perceived by the user as a single symbol.

If you need to **move a cursor or select a displayed character**, consider `BreakIterator.getCharacterInstance(locale)` or a grapheme segmentation mechanism aligned with the supported Unicode version. Java regex `\X` and `\b{g}` also provide constructs for extended grapheme clusters in Java 17.

**Grapheme boundaries differ from word boundaries.** Do not use `String.codePoints().count()` to infer word count, and do not use code unit positions to assert how many characters a user sees.

## 15. Distinguishing Word Boundaries from Sentence Boundaries

`BreakIterator` has separate factories:

- `getWordInstance(locale)`: **word**-related boundaries;
- `getSentenceInstance(locale)`: **sentence** boundaries;
- `getLineInstance(locale)`: positions **where lines may break**;
- `getCharacterInstance(locale)`: **character** boundaries per the provider's algorithm.

For example, a period can:
- end a sentence;
- appear in the abbreviation `Dr.`;
- be a decimal point in `3.14`;
- appear in a URL/domain;
- appear consecutively in `...`.

Thus, `text.split("\\.")` is not a complete sentence splitter; treating every period as a boundary can break numbers, proper names, and abbreviations. `BreakIterator.getSentenceInstance(locale)` performs context-aware boundary analysis, though it still needs evaluation against your product's data and languages.

### Example Segmenting Sentences Without Hardcoding Sentence Count

Create **`SentenceBoundaryDemo.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class SentenceBoundaryDemo {
    public static void main(String[] args) {
        String input = "Dr. Lee paid 3.14. Then left.";

        BreakIterator iterator =
                BreakIterator.getSentenceInstance(Locale.ENGLISH);
        iterator.setText(input);

        StringBuilder restored = new StringBuilder();
        int segments = 0;

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {
            restored.append(input, start, end);
            segments++;
        }

        System.out.println(restored.toString().equals(input));
        System.out.println(segments > 0);
    }
}
~~~

~~~bash
javac SentenceBoundaryDemo.java
java SentenceBoundaryDemo
~~~

Output:

~~~text
true
true
~~~

The program does not assert a fixed sentence count because abbreviation behavior can differ across providers and dictionaries. What is checked is that the iterator returns non-empty segments and concatenating them reconstructs the exact input. To count sentences for business logic, test segmentation quality on abbreviations and real text.

## 16. Regex `\\b` Does Not Replace a Natural-Language Word Tokenizer

In Java regex, `\b` is a **word boundary assertion**, not a linguistic word-splitting command. It determines boundaries purely by regex rules, without understanding Vietnamese compound words or spaceless-script segmentation problems.

Also distinguish **two escape levels**:

~~~java
String regex = "\\b";
~~~

The line above creates a regex containing a backslash + `b`. If you write `"\b"` in a Java string literal, `\b` is Java's **backspace character**, not the regex word boundary token.

`\w`, `\d`, and `\s` also have specific character sets. `Pattern.UNICODE_CHARACTER_CLASS` or the inline flag `(?U)` makes those predefined character classes more Unicode-aware, yet **switching character sets does not solve dictionary-based segmentation**.

For example, `\b` can be useful for finding boundaries of a known string in a simple data domain, but should not be called a "universal tokenizer" for Chinese, Japanese, Thai, or Vietnamese.

## 17. Checking Whitespace with Unicode Properties

If business logic only needs to **split a list of fields delimited by Unicode `White_Space`**, you can use a regex with an explicitly documented policy:

~~~java
String[] fields = input.split("(?U)\\s+");
~~~

Or use the Unicode property supported by Java regex:

~~~java
String[] fields = input.split("\\p{IsWhite_Space}+");
~~~

This is a **snippet** where `input` is an existing `String`. Both approaches handle more Unicode whitespace characters than Java's default `"\\s+"`.

However, before using them:
1. Decide whether **NBSP** should be treated as a delimiter.
2. Decide how to handle **leading/trailing spaces**.
3. Specify whether to keep **empty fields**.
4. Decide how to handle **zero-width spaces** and formatting characters that do not share the same property.
5. Do not apply this operation to claim a natural-text word count when the language does not use whitespace to separate every word.

Increasing regex Unicode coverage only solves **the delimiter set**, not **word semantics**.

## 18. Word Count: What Should Be Reported?

Products often ask for "word count". Yet that term needs definition:

- **Counting whitespace-split groups:** easy to compute and fast, suitable for simple data fields, yet **unfair across languages**.
- **Counting word-like segments returned by `BreakIterator`:** better for certain text-editing features, though results depend on locale/provider and punctuation filtering rules.
- **Counting lexical words via an NLP tokenizer:** requires language-specific models/rules, may change across versions, and does not necessarily match how a human reader counts.
- **Counting grapheme clusters or characters:** a different metric, appropriate for SMS/UI limits rather than word counts.

A translation service provider may price by word count in some languages and by character count in others. You should not enforce the same whitespace-based "100-word" quota across all languages without clearly stating how it is counted.

If an application's input limit actually needs **length**, it is usually better to measure bytes, code points, or graphemes per contract rather than the element count from `split(" ")`.

## 19. Empty Input and Multiple Delimiters

A common split-based counting bug:

~~~java
int count = text.split("\\s+").length;
~~~

This line has several edge cases:
- An empty string can produce an array containing an empty element depending on the `split` overload/semantics.
- A whitespace-only string can yield unexpected results.
- Leading/trailing spaces can affect empty elements; by default **trailing** empty elements are discarded.
- Unicode whitespace not recognized by default regex remains inside an element.
- Spaceless text can be counted as a single "word" despite actually having many words.

If the goal is a **list of whitespace-delimited fields**, define empty-input handling and trimming/stripping separately. With Java's `strip()`, note that it relies on `Character.isWhitespace` and may not remove every Unicode character such as NBSP.

**Do not use a `split` array `length` trick as a linguistic metric.**

## 20. Distinguishing Delimited Data from Natural Text

**Case A — protocols with an explicit delimiter:**

~~~text
CSV, TSV, command-line arguments, ID lists separated by a fixed character
~~~

Here you need a **protocol-compliant parser**. CSV has quoting, escaping, and newline rules; splitting blindly on commas can break too. TSV has different constraints, and command lines have their own quoting.

**Case B — natural text:**

~~~text
A sentence in Vietnamese, Thai, Chinese, Japanese, Arabic...
~~~

Here you need boundary analysis/segmentation tailored to the language and goal. Do not use a CSV parser for natural text or a word tokenizer to split CSV fields.

A user typing `Hello world` uses spaces, whereas an address `user@example.com` contains punctuation and should not be split into multiple "words" if business logic treats an email as one unit.

Choosing the right **data unit** resolves most confusion before even picking a Java API.

## 21. A Java 17+ Helper Extracting Word-Like Segments with Explicit Locale

Create **`WordLikeSegments.java`**:

~~~java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class WordLikeSegments {
    private WordLikeSegments() {}

    public static List<String> extract(
            String input, Locale locale) {

        if (input == null || locale == null) {
            throw new IllegalArgumentException(
                    "input and locale must not be null");
        }

        BreakIterator iterator =
                BreakIterator.getWordInstance(locale);
        iterator.setText(input);

        List<String> result = new ArrayList<>();

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String part = input.substring(start, end);

            if (part.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                result.add(part);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> words = extract(
                "Hello, world! Java 17.",
                Locale.ENGLISH);

        System.out.println(words);
    }
}
~~~

~~~bash
javac WordLikeSegments.java
java WordLikeSegments
~~~

Result with standard JDK 17 English rules:

~~~text
[Hello, world, Java, 17]
~~~

This is **word-like segment extraction**, not an English dictionary and certainly not a universal tokenizer. It also **drops punctuation and whitespace**, so the full text cannot be reconstructed from `result` alone; if you need to preserve positions or the original sentence, store start/end offsets and classify segments separately.

The function creates a `BreakIterator` per call to avoid sharing mutable state across requests. For high throughput, benchmark before optimizing, and keep locale/provider consistent with product policy.

## 22. Upgrading the Helper: Keeping Offsets and Classifying Segments

When a user selects text or the application needs to attach highlights, storing only token strings may be insufficient. Keep **original positions**:

~~~java
public record Segment(int start, int end, String text) {}
~~~

This is a snippet placed in an appropriate Java class or file. `start` and `end` from `BreakIterator` are UTF-16 offsets, matching Java's `String.substring(start, end)`.

Consider storing:
- original text;
- `start`/`end` of each segment;
- segment kind (`word-like`, punctuation, whitespace, symbol...);
- locale and rule version if segmentation must be reproducible.

Do not mix **code point** indexes with **UTF-16** offsets when frontend and backend use different counting models. For example, a non-BMP emoji can occupy two UTF-16 code units; using a code-point offset directly with `substring` easily causes wrong highlights.

When the UI uses another API whose offsets are in UTF-8 bytes or grapheme clusters, convert coordinates explicitly and test surrogate pair / combining mark cases.

## 23. Accented Words, Normalization, and Segment Grouping

Vietnamese text can contain precomposed letters or base letters + combining marks:

~~~text
é
e + U+0301
~~~

`java.text.Normalizer` can convert canonically equivalent representations into a consistent form such as NFC. However, **normalization does not split words**. It only handles Unicode representation forms.

A text-analysis pipeline might look like:

~~~text
Receive Unicode text
    ↓
Determine locale/language and tokenization goal
    ↓
Normalize per policy (if applicable)
    ↓
Segment words with an appropriate BreakIterator/tokenizer
    ↓
Filter/classify/merge tokens per business logic
    ↓
Store positions or mapping back to original string if highlighting is needed
~~~

If normalization changes string length, offsets on the normalized text **do not necessarily match** offsets on the original. Do not apply offsets from the normalized form directly to the original if code unit counts changed.

If the application must display the exact input characters, store both the original text and the normalized text used for search, along with a position-mapping mechanism.

## 24. Search Tokenization and Compound-Word Semantics

For a multilingual search system, a tokenizer needs to consider:

1. **Language and script**: Chinese word segmentation, Japanese morphological segmentation, Thai/Lao/Khmer dictionary-based segmentation, Vietnamese compound-word segmentation.
2. **Normalization**: Unicode NFC/NFKC per policy, Vietnamese diacritics, fullwidth forms, cases where tokens should be preserved or folded.
3. **Case handling**: locale-sensitive case mapping and case folding must not be conflated arbitrarily.
4. **Numbers and units**: `3.14`, `1 234`, measurement units, or currency symbols.
5. **Proper names and abbreviations**: `TP.HCM`, `U.S.A.`, hyphenated brand names.
6. **URLs, emails, hashtags, mentions**: may need to remain single tokens.
7. **Emojis and symbolic characters**: some products need to index symbols, not only letters/digits.
8. **Dictionary/model updates**: when upgrading tokenizer versions, re-test quality and index compatibility.

For instance, `"công nghệ thông tin"` may need to stay a phrase or generate n-grams for search; there is no single tokenization answer for every query.

**Do not confuse splitting a sentence into a token list with understanding sentence meaning.** Tokenization is one step, while part-of-speech tagging, entity extraction, word-sense disambiguation, and semantic search are separate steps.

## 25. Core Java vs. Specialized Libraries

Core Java already has `BreakIterator` and Unicode regex, which suffice for many tasks:
- moving a cursor along boundaries;
- standard rule-level sentence/word segmentation;
- supporting text-editing features;
- filtering word-like segments with a heuristic;
- splitting data fields by a specified delimiter.

If a product requires high quality for Japanese, Chinese, Thai, Vietnamese, or specialized domains, consider a **language-specific segmenter**, NLP dictionaries/models, or an i18n/Unicode library such as ICU4J. Still, evaluate **the exact capabilities, version, and data of the chosen library**; do not assume swapping in a library resolves every linguistic ambiguity.

Do not assert that `BreakIterator.getWordInstance(Locale.forLanguageTag("th-TH"))` always returns dictionary-perfect Thai words. Results can depend on the locale provider and dataset used; test empirically on your target runtime.

## 26. Thread Safety and Locale

`BreakIterator` is a **stateful** iterator: `setText` and advancing via `first`/`next` mutate analysis state. Therefore, do not share an active instance across multiple threads/requests without synchronization.

Anti-pattern example:

~~~java
// Do not share this mutable iterator across multiple requests:
static final BreakIterator SHARED =
        BreakIterator.getWordInstance(Locale.ENGLISH);
~~~

If request A calls `SHARED.setText(textA)` while request B calls `SHARED.setText(textB)`, A's position and text can change mid-processing. Create a separate iterator per operation or use copies / a safe lifecycle-management mechanism.

Similarly, user locale must be explicit. Do not mutate `Locale.setDefault(...)` per request because the default locale is JVM-global state. Pass `Locale` into `getWordInstance(locale)`, and decide whether you need an **analysis language** separate from the **display locale**, especially when the source text and the user belong to different languages.

## 27. How to Test a Multilingual Word Splitter

A serious test suite should include at least:

| Scenario | What to Check |
| --- | --- |
| English with punctuation adjacent to letters | `split(" ")` misses boundaries; does the tokenizer handle them as intended? |
| Consecutive spaces/tabs/newlines | Empty-field and delimiter policy |
| NBSP / NARROW NBSP / IDEOGRAPHIC SPACE | Default regex and Unicode regex behave differently |
| Spaceless Chinese/Japanese | Do not confuse code point count with word count |
| Thai/Lao/Khmer | Evaluate against real-language lexical data |
| Multi-syllable Vietnamese | Phrases like `"học sinh"`, `"công nghệ thông tin"` |
| Apostrophes/hyphens/abbreviations | `don't`, `l'amour`, `e-mail`, `TP.HCM` |
| Decimal numbers and grouped numbers | `3.14`, `1,234`, numbers with NBSP |
| Combining marks and emojis | Do not corrupt code points/graphemes |
| Empty string / whitespace-only | Counting and filtering match the contract |
| Highlighting with offsets | UTF-16 offsets match the original string |
| JDK/provider version change | Token boundaries may change |
| Concurrent requests | Mutable `BreakIterator` is not shared |
| Mixed languages in one sentence | Do not assume one locale handles everything perfectly |

To evaluate NLP segmentation, you need a **gold-standard test corpus** or human/linguist-verified ground truth rather than merely comparing token counts. You can measure boundary precision/recall/F1 if your domain requires it.

## 28. Java Exercise: Comparing "Whitespace Split" and "Word-Like Segments"

Create **`SegmentationCompare.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Arrays;
import java.util.Locale;

public class SegmentationCompare {
    static int countWordLike(String input, Locale locale) {
        BreakIterator iterator =
                BreakIterator.getWordInstance(locale);
        iterator.setText(input);

        int count = 0;
        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String segment = input.substring(start, end);
            if (segment.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        String text = "Hello, world! Java 17.";

        System.out.println(
                Arrays.toString(text.split(" ")));
        System.out.println(countWordLike(text, Locale.ENGLISH));

        String noSpaces = "Hello,world";
        System.out.println(noSpaces.split(" ").length);
    }
}
~~~

~~~bash
javac SegmentationCompare.java
java SegmentationCompare
~~~

Result under standard JDK 17 English rules:

~~~text
[Hello,, world!, Java, 17.]
4
1
~~~

Note how `Arrays.toString` inserts commas to separate array elements; since the first element is `Hello,`, two commas appear side by side (`Hello,,`) as **valid array formatting syntax**, not a parsing bug.

The `noSpaces` string contains no U+0020, so `split(" ").length == 1`, even though there is a comma between `Hello` and `world`. `BreakIterator` recognizes non-space boundaries where appropriate.

## 29. Common Mistakes

1. **"Every space separates one word."** False for many languages and even texts with special punctuation.
2. **"No spaces means only one word."** False for many CJK and Southeast Asian scripts.
3. **"Vietnamese has spaces, so word splitting is already solved."** False: lexical words can span multiple space-separated syllables.
4. **"`split("\\s+")` is Unicode word segmentation."** False: it splits only at regex whitespace.
5. **"`(?U)\\s+` solves every language."** It widens the delimiter set; it does not know word boundaries.
6. **"Punctuation always separates words."** Apostrophes, hyphens, and periods in numbers/URLs serve different roles.
7. **"`BreakIterator` returns only words."** It returns **boundaries**; punctuation/whitespace can be separate segments.
8. **"`BreakIterator` is always dictionary-accurate for every locale."** Quality depends on runtime, data, and goal.
9. **"`Character.isLetterOrDigit` identifies every true token."** It misses multi-word structures, combining marks, and domain tokens.
10. **"One code point is always one visible character."** A grapheme cluster can contain multiple code points.
11. **"BreakIterator offsets are code point counts."** `String`-based APIs work in UTF-16 offsets.
12. **"Stripping all Unicode whitespace never changes meaning."** Non-breaking spaces can hold important groupings together.
13. **"Using `\b` regex instead of `BreakIterator` is equivalent."** Regex word boundaries are not linguistic segmentation.
14. **"An NFC-normalized string automatically splits words properly."** Unicode normalization handles representation, not word boundaries.
15. **"One `BreakIterator` can be shared across all requests."** The iterator has mutable state.
16. **"Word count is an absolute, language-independent quantity."** You must publish the counting method and product goal.

## 30. Self-Check Questions

**Q1.** Why does `"Hello,world".split(" ")` return only one element?

**Answer:** Because the string contains no U+0020; the comma does not match the space delimiter.

**Q2.** Does enabling `(?U)` in Java regex create an accurate Thai word splitter?

**Answer:** No. It makes character classes like `\s` more Unicode-aware, yet still does not determine words using a Thai dictionary.

**Q3.** Why shouldn't `"học sinh"` in Vietnamese automatically be counted as two lexical words?

**Answer:** Spaces in Vietnamese usually separate syllables; `"học sinh"` can be a multi-syllable lexical unit.

**Q4.** What does `BreakIterator.getWordInstance` return?

**Answer:** Boundary positions per locale/provider rules. Segments include punctuation and whitespace as well, not just words.

**Q5.** Why can counting words with `Character.isLetterOrDigit` be wrong?

**Answer:** It only classifies code points; it does not understand hyphens, apostrophes, compound words, or spaceless segmentation.

**Q6.** When highlighting a segment from `BreakIterator` offsets, should you use code point or UTF-16 offsets?

**Answer:** `BreakIterator` uses offsets matching `String.substring`, namely **UTF-16 code-unit indexes**.

**Q7.** What requires attention with U+00A0 and U+202F?

**Answer:** They are non-breaking spaces; they may not match Java's default `\s` regex and carry special formatting semantics.

**Q8.** Does `Normalizer` replace a tokenizer?

**Answer:** No; it normalizes Unicode representation, and does not analyze linguistic word boundaries.

**Q9.** When processing an ID list with a contractually specified `;` delimiter, do you need an NLP tokenizer?

**Answer:** Not necessarily. Use a parser/split matching the data's delimiter, escaping, and empty-field specification.

**Q10.** To count search tokens for specialized Japanese text, can you just use `split(" ")`?

**Answer:** No. You need to select and evaluate a segmenter suited to the language and search goal.

## 31. Solution-Selection Workflow in a Java Project

1. **Define the task**: protocol field splitting, whitespace-chunk counting, UI word boundaries, NLP word segmentation, or search tokenization.
2. **Inspect input structure**: are spaces truly delimiters? Are there quotes, punctuation, NBSP, emojis, or mixed scripts?
3. **Choose an explicit ruleset**: `String.split` for simple delimiters; Unicode regex for whitespace policies; `BreakIterator` for boundary analysis; dictionary/model tokenizers for lexical requirements.
4. **Pass `Locale` explicitly** when using `BreakIterator`; do not mutate the JVM default per request.
5. **Preserve original data if highlighting is needed**: boundaries return offsets on the analyzed string; normalization or text transformations can shift offsets.
6. **Handle code points/graphemes safely** in truncation, cursor movement, and length-limit features.
7. **Name results accurately**: "field count", "word-like segment count", "NLP token count", and "lexical word count" are not inherently equal.
8. **Test with real multilingual text** and edge cases, especially CJK, Thai, Vietnamese, punctuation, and Unicode whitespace.
9. **Document JDK/provider/tokenizer versions** if consistency of word counts or search indexes affects business behavior.

**Key takeaway:** Whitespace is **a character or group of delimiter characters**, whereas a **word** is a linguistic unit written and defined by many rules. `split(" ")` handles only the U+0020 delimiter; regex `\s` handles a whitespace set; `BreakIterator` finds locale-based text boundaries; and many languages/tasks still require **specialized word segmenters**. Do not conflate these layers, to avoid wrong word counts, broken search, and inaccurate Unicode text processing.

**Java SE 17 Documentation:** [BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html), [Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html).
