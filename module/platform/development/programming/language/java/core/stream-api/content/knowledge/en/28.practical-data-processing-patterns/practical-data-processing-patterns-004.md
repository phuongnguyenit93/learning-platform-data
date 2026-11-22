# Building Word Frequency Tables and Unicode Text Statistics

## 1. Problem: Word Counting in Text Is More Than Splitting on Spaces

In search engines, feedback analytics, log processing, or document evaluation, we often need to know **how many times a word appears**, which words are most common, how many distinct words exist, and how long the text is. With the **Java Stream API**, a pipeline can express this task as a declarative sequence of steps:

```text
Input text
       |
       v
Unicode normalization + case normalization
       |
       v
Extract word-like tokens
       |
       v
flatMap: many lines -> one token stream
       |
       v
groupingBy(token, counting())
       |
       v
Map<String, Long> frequencies
       |
       v
Sort by frequency descending, token ascending
       |
       v
Deterministic report table
```

Suppose two text snippets look identical:

```text
Text A: CÀ phê, cà PHÊ!
Text B: café, café
```

Text A differs in letter case. In Text B, the second `é` can be represented by **two Unicode code points**: the letter `e` and the combining acute accent `U+0301`. If you only call `String.split(" ")` and compare strings, the program can count multiple separate entries even though a reader sees the exact same word.

This lesson belongs to the **Practical Data Processing Patterns** chapter of the `JAVA_STREAM_API` module. We will use `map`, `flatMap`, `filter`, `collect`, `Collectors.groupingBy`, `Collectors.counting`, and `sorted`, while recognizing the limits of Unicode processing with standard APIs.

**After this lesson, you will be able to:**

1. Distinguish UTF-16 `char` units, Unicode code points, and user-perceived characters (*grapheme clusters*).
2. Normalize Unicode forms with `Normalizer`, then handle letter case under an explicit policy.
3. Extract tokens containing letters and combining marks using Unicode regular expressions.
4. Build a word frequency table, sort results with deterministic tie-breaking, and compute text statistics.
5. Read UTF-8 files using `Files.lines` with `try-with-resources`.
6. Recognize cases where regex is insufficient for multi-syllable Vietnamese words, multilingual text, emoji, alphanumeric words, and punctuation.

Standalone examples use **Java 17+**. Most APIs such as `Stream`, `Normalizer`, `Pattern`, and `Collectors.groupingBy` have existed since Java 8.

## 2. Define "Word" Before Writing Code

To make the problem testable, we must specify **which tokens are counted**. A practical baseline policy:

- Take only character sequences starting with a **Unicode letter** (category `\p{L}`).
- After the initial letter, accept additional letters or **combining marks** (category `\p{M}`).
- Spaces, punctuation, digits, and emoji are treated as delimiters or ignored under this policy.
- Convert letters to lowercase and normalize to **NFC** before counting.
- Count by **token occurrence**: each occurrence adds one unit, even when a token repeats on the same line.

Examples:

| Input text | Tokens under lesson policy | Notes |
| --- | --- | --- |
| `"CÀ phê"` | `cà`, `phê` | Two syllables become two tokens; the phrase `cà phê` is not automatically treated as one compound word. |
| `"café"` | `café` | Accented letters are preserved. |
| `"cafe" + combining acute accent` | `café` after NFC | Both encodings normalize to the same canonical form. |
| `"Java-Stream"` | `java`, `stream` | Hyphen acts as a separator. |
| `"A12 B34"` | `a`, `b` | Digits are excluded from tokens under the chosen rule. |
| `"🙂 Java"` | `java` | Emoji is not a letter token. |

**This is an intentional tokenization rule, not a universal linguistic definition of "word".** In Vietnamese, `"học sinh"` or `"cà phê"` may be multi-syllable lexical units; the regex below splits by letter sequence. To count true compound words, use a **word segmentation** engine appropriate for the language and data model.

## 3. Unicode: char, Code Points, and Perceived Characters Differ

Java `String` is encoded using **UTF-16 code units**. A `char` holds one 16-bit code unit, which does not always correspond to a complete Unicode character.

Example:

```java
String greeting = "A🙂";

System.out.println(greeting.length());        // 3 UTF-16 units
System.out.println(greeting.codePointCount(
        0, greeting.length()));               // 2 code points
```

The letter `A` uses one UTF-16 unit; the emoji `🙂` is a code point outside the Basic Multilingual Plane and is encoded as a **surrogate pair**, taking two UTF-16 units.

A letter with a combining mark can also make the code point count differ from the number of characters a reader perceives:

```java
String composed = "é";
String decomposed = "e" + "\u0301"; // e + COMBINING ACUTE ACCENT

System.out.println(composed.length());   // 1
System.out.println(decomposed.length()); // 2
System.out.println(composed.equals(decomposed)); // false before normalization
```

Three concepts:

| Unit | Common Java API | Meaning |
| --- | --- | --- |
| UTF-16 code unit | `String.length()`, `charAt()` | Storage unit of a Java string. |
| Unicode code point | `codePoints()`, `codePointCount()` | Abstract Unicode character value, occupying 1 or 2 `char`s. |
| Grapheme cluster | Text segmentation per display rules | May comprise multiple code points, e.g., letter + combining marks or ZWJ emoji. |

If a report wants to count **code points**, use `codePointCount` or `codePoints`. If it wants to count **user-perceived characters**, you cannot assume `String.length()` or code point count is always accurate; use a grapheme segmentation algorithm matching the Unicode version and display context.

### Traversing Code Points with Primitive Streams

```java
String sample = "A🙂é";

long codePoints = sample.codePoints().count();
long unicodeLetters = sample.codePoints()
        .filter(Character::isLetter)
        .count();

System.out.println(codePoints);     // 3
System.out.println(unicodeLetters); // 2
```

`String.codePoints()` returns an `IntStream` of code points. `Character.isLetter` inspects each code point; unlike iterating `char` by `char` in a loop, it avoids splitting surrogate pairs.

## 4. Unicode Normalization with Normalizer and Locale

Unicode can represent certain accented characters using multiple **canonically equivalent** code point sequences. Normalization form `NFC` performs canonical decomposition followed by canonical composition, unifying equivalent representations.

```java
import java.text.Normalizer;

String composed = "café";
String decomposed = "cafe" + "\u0301";

System.out.println(composed.equals(decomposed)); // false

String a = Normalizer.normalize(
        composed, Normalizer.Form.NFC);
String b = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(a.equals(b)); // true
```

`Normalizer.Form.NFC` is usually the right choice when **you want to preserve distinctions between accented and unaccented letters** while unifying combining-mark representations.

### Handling Letter Case

`String.toLowerCase()` without a locale uses the environment's default locale, which can cause results to differ across machines. In a token-counting system with language-neutral conventions, use `Locale.ROOT`:

```java
import java.util.Locale;

String lower = "CÀ PHÊ".toLowerCase(Locale.ROOT);
System.out.println(lower); // cà phê
```

Illustrative normalization flow:

```java
static String normalizeForCounting(String input) {
    String nfc = Normalizer.normalize(
            input, Normalizer.Form.NFC);
    String lower = nfc.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
```

Why normalize to NFC **after** lowercasing: some case-conversion steps can produce or preserve combining marks; a final normalization ensures canonical keys.

**Important limitation:** lowercasing with `Locale.ROOT` is not fully equivalent to **Unicode case folding** across all languages. If you need locale-specific matching (such as Turkish `I` rules) or strict international search matching, choose the locale and matching mechanism per product requirements. Do not silently apply one global rule everywhere.

### How NFC Differs from NFKC

`NFKC` also normalizes **compatibility** characters, which can merge visually distinct representations carrying different display semantics (such as full-width forms or compatibility symbols). That helps some search systems but may erase distinctions your domain wants to keep.

| Goal | Suggested Approach |
| --- | --- |
| Unify canonically equivalent accented encodings | Usually start with `NFC`. |
| Also fold compatibility character forms | Consider `NFKC` after assessing consequences. |
| Strip Vietnamese diacritics for accent-insensitive search | Requires a dedicated policy, **not a default effect of NFC**. |
| Preserve distinctions like `ma`, `má`, `mà` | Do not strip combining marks during normalization. |

Do not strip diacritics just to count frequencies: Vietnamese words with different tones/diacritics carry different meanings.

## 5. Tokenization with a Unicode Pattern

A regular expression matching the policy in section 2 is:

```regex
\p{L}[\p{L}\p{M}]*
```

Explanation:

- `\p{L}`: a character in the Unicode **Letter** category, required at the start of the token.
- `[\p{L}\p{M}]*`: followed by zero or more **Letter**/**Mark** characters.
- Digits, hyphens, and punctuation are not included as part of a token.
- Because it starts with `\p{L}`, a **lone combining mark without a preceding letter** will not form a token.

In Java string literals, regex backslashes must be **escaped once more**:

```java
import java.util.regex.Pattern;

Pattern WORD = Pattern.compile(
        "\\p{L}[\\p{L}\\p{M}]*"
);
```

A `Pattern` can be reused across many analyses. `Pattern` is immutable in configuration and safe to share; each `Matcher` holds mutable state and **must not be shared concurrently across threads**.

### Creating a Token List from a String

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;

static List<String> tokenize(String input) {
    String normalized = normalizeForCounting(input);
    Matcher matcher = WORD.matcher(normalized);

    List<String> words = new ArrayList<>();
    while (matcher.find()) {
        words.add(matcher.group());
    }
    return words;
}
```

When `WORD`, `normalizeForCounting`, and `tokenize` are placed in the same class:

```java
System.out.println(tokenize("CÀ phê, cà PHÊ!"));
// [cà, phê, cà, phê]

System.out.println(tokenize("café cafe\u0301"));
// [café, café]

System.out.println(tokenize("Java-Stream 2026 🙂"));
// [java, stream]
```

**Note on laziness:** `tokenize` here uses `Matcher.find()` to **build an intermediate List per string** before returning. This is an intentional simplification for the lesson; it is not a fully lazy tokenizer. For huge texts or token-by-token streaming, you can write a `Spliterator` over `Matcher` or use a dedicated tokenization library while respecting resource and state contracts.

## 6. Why Splitting on Whitespace Is Not Enough

A common attempt:

```java
String[] pieces = "CÀ phê, cà PHÊ!".split("\\s+");
```

The resulting pieces like `"phê,"` and `"PHÊ!"` still carry punctuation; if used directly as Map keys, `"phê"` differs from `"phê,"`. Calling `split(" ")` also misses tabs or line breaks.

Even `split("\\W+")` requires caution: the meaning of character classes like `\w` and `\W` depends on `Pattern` flags and rules. When Unicode support is required, explicitly specifying `\p{L}`/`\p{M}` better expresses **the kind of token the problem intends to count**.

| Input | Consequence of naive splitting |
| --- | --- |
| `"phê, phê!"` | Punctuation can become part of the key. |
| `"café cafe" + combining mark` | Two representations may not compare equal without NFC. |
| `"CÀ cà"` | Counted as two entries without case normalization. |
| `"Java\\tStream"` | Splitting on a single space misses tabs. |
| `"🙂 code"` | `char`-based counting can split emoji surrogate pairs. |

No single regex solves text segmentation for every language. Choose a **concrete tokenization contract and write tests for it**.

## 7. Building a Frequency Table with flatMap, groupingBy, and counting

Suppose text is stored as multiple lines:

```java
List<String> lines = List.of(
        "CÀ phê, cà PHÊ!",
        "Trà trà, café cafe\u0301.",
        "Java Stream — JAVA stream JAVA."
);
```

Meaning of `flatMap`: each line expands into **multiple tokens**, and those token streams are flattened into a single stream.

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Long> frequencies = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));
```

Reading the pipeline left to right:

1. `lines.stream()` creates a `Stream<String>` of lines.
2. `flatMap(line -> tokenize(line).stream())` produces a Stream of normalized tokens, **retaining repeated occurrences**.
3. `Function.identity()` uses the token itself as the grouping key.
4. `Collectors.counting()` counts how many times each token lands in its group.
5. The result is a `Map<String, Long>`.

Checking concrete values:

```java
System.out.println(frequencies.get("java"));   // 3
System.out.println(frequencies.get("cà"));     // 2
System.out.println(frequencies.get("phê"));    // 2
System.out.println(frequencies.get("trà"));    // 2
System.out.println(frequencies.get("café"));   // 2
System.out.println(frequencies.get("stream")); // 2
System.out.println(frequencies.size());        // 6 distinct words
```

The total token count is **13**: `java` appears three times, and the remaining five tokens appear twice each. This example exercises Vietnamese diacritics, NFC normalization, and letter case together.

### Can `toMap` Replace `groupingBy`?

Yes, if you specify the right merge function:

```java
Map<String, Long> withMerge = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .collect(Collectors.toMap(
                Function.identity(),
                token -> 1L,
                Long::sum
        ));

System.out.println(withMerge.equals(frequencies)); // true
```

Two-argument `Collectors.toMap` throws `IllegalStateException` on duplicate tokens; only the three-argument overload with `Long::sum` expresses counting accurately. For frequency tables, `groupingBy(identity, counting())` usually reads closer to statistical intent.

## 8. Outputting the Frequency Table in Deterministic Order

By default, `Collectors.groupingBy` does not guarantee iteration order on the returned Map. For a report table, we typically want:

1. Frequency **descending**.
2. On equal frequency, token **ascending** so output stays deterministic.

```java
record WordCount(String word, long count) {}

List<WordCount> ranking = frequencies.entrySet().stream()
        .sorted(
                Comparator.<Map.Entry<String, Long>>comparingLong(
                        entry -> entry.getValue()
                ).reversed().thenComparing(Map.Entry::getKey)
        )
        .map(entry -> new WordCount(
                entry.getKey(), entry.getValue()
        ))
        .toList();

ranking.forEach(System.out::println);
```

Output for the example in section 7:

```text
WordCount[word=java, count=3]
WordCount[word=café, count=2]
WordCount[word=cà, count=2]
WordCount[word=phê, count=2]
WordCount[word=stream, count=2]
WordCount[word=trà, count=2]
```

**Ordering here uses `String.compareTo`** (lexicographical order by UTF-16 code units), **not Vietnamese alphabetical dictionary order**. Comparing accented letters according to Vietnamese conventions requires a `Collator` and an appropriate locale policy. If output must remain strictly identical across environments, pin collator versions/rules or use a well-defined application comparator.

### Taking Only the Top N

```java
int topN = 3;

List<WordCount> top = ranking.stream()
        .limit(topN)
        .toList();

System.out.println(top.size()); // 3
```

`limit` takes a prefix of the **already sorted** list. Do not call `frequencies.entrySet().stream().limit(3)` and expect the three most frequent words.

### Printing Only Words Above a Threshold

```java
List<WordCount> frequent = ranking.stream()
        .filter(item -> item.count() >= 3)
        .toList();

System.out.println(frequent); // [WordCount[word=java, count=3]]
```

If you only need a sorted report rather than an ordered Map, keep the initial Map and build the sorted `List<WordCount>` only when exporting results.

## 9. Text Statistics: Lines, Tokens, Distinct Words, Code Points

The frequency table can also supply summary metrics:

| Metric | Definition in this lesson | How to compute |
| --- | --- | --- |
| **Input line count** | Number of `String` elements in the line list | `lines.size()` |
| **Total token count** | All occurrences, including repeats | Sum of frequency map values |
| **Distinct token count** | Unique keys after normalization | `frequencies.size()` |
| **Code point count** | Unicode code points in original text | `String.codePoints().count()` |
| **Letter code point count** | Code points matching `Character.isLetter` | `codePoints().filter(Character::isLetter).count()` |
| **Average token length** | Mean **code point count** across normalized tokens | `mapToInt(...).average()` |

Example:

```java
long lineCount = lines.size();
long tokenCount = frequencies.values().stream()
        .mapToLong(Long::longValue)
        .sum();
long uniqueCount = frequencies.size();

long sourceCodePoints = lines.stream()
        .mapToLong(line -> line.codePointCount(0, line.length()))
        .sum();

long sourceLetters = lines.stream()
        .mapToLong(line -> line.codePoints()
                .filter(Character::isLetter)
                .count())
        .sum();

double averageTokenCodePoints = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .mapToInt(word -> word.codePointCount(0, word.length()))
        .average()
        .orElse(0.0);

System.out.println(lineCount);               // 3
System.out.println(tokenCount);              // 13
System.out.println(uniqueCount);             // 6
System.out.println(averageTokenCodePoints); // approx. 3.69
```

In this example, the combined length of normalized NFC tokens is **48 code points** across 13 tokens, averaging about **3.69**. `sourceCodePoints` and `sourceLetters` measure the **raw input lines**, so they may include punctuation, digits, and other code points per their definitions.

`IntStream.average()` returns `OptionalDouble` because the Stream may be empty. `orElse(0.0)` is a **reporting policy**, not a mathematical operation: when there are zero tokens, the true average is **undefined**; in systems that must distinguish those states, keep `OptionalDouble` or use a nullable field/flag by design.

### Do Not Confuse Total Frequency with Key Count

`frequencies.size()` is the **distinct word count**, not total occurrences. That is a common bug when transitioning from `List<String>` to `Map<String, Long>`. To obtain total tokens without re-scanning the text, sum the Map's values.

## 10. Filtering Stop Words Without Corrupting Statistics

*Stop words* are frequent tokens that may be excluded for analysis purposes, such as certain function words in a language. This list is **domain-dependent**; do not blindly drop `"không"`, `"có"`, or words critical to sentiment or topic analysis.

In a simple example, suppose we have a set of words to exclude:

```java
Set<String> stopWords = Set.of("và", "là", "của");

Map<String, Long> withoutStopWords = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .filter(word -> !stopWords.contains(word))
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));
```

Normalize stop words **using the exact same policy** as input tokens. If the stop-word list comes from a file or user input, run `normalizeForCounting` (and matching tokenization rules) on it rather than assuming it is already in NFC lowercase.

**Define processing order:** if stop words are filtered before `groupingBy`, both distinct token count and total token count in the report **change**. If you need to report both total tokens and post-filter tokens simultaneously, compute two separate metrics or design an aggregator built for both.

## 11. Real-World Unicode: Punctuation, Digits, Emoji, and Compound Words

The regex `\p{L}[\p{L}\p{M}]*` defines a tokenizer with **clear boundaries**. It does not solve every text format completely:

### Words with Digits, Hashtags, and Email Addresses

```text
Input        Lesson regex policy
Java17       -> java
#Java        -> java
user@mail.io -> user, mail, io
don't        -> don, t
AI-based     -> ai, based
```

This is not necessarily wrong if you only count alphabetic sequences; however, if the product needs to keep `Java17`, hashtag `#Java`, or email addresses as single tokens, **change the tokenization contract**, not just a downstream `filter`. You can use a dedicated `Pattern` for product codes, hashtags, or emails and test each case.

### Vietnamese and Multi-Syllable Compound Words

For `"học sinh"`, this regex emits two tokens: `học` and `sinh`. In many Vietnamese NLP tasks, the whole phrase is one lexical unit. `Collectors.groupingBy` only counts the tokens fed into it and **does not know linguistic word boundaries**.

If you need **Vietnamese word frequencies at the lexical level**, use a dedicated word segmenter and evaluate it on labeled data. The downstream Stream pipeline (filtering, grouping, counting, sorting) can still be reused.

### Scripts Without Word-Separating Spaces

Some writing systems such as Chinese do not separate words with spaces in the same way. The regex here may merge a long run of characters into a single token. Java provides `BreakIterator.getWordInstance(locale)` for locale-based segmentation, though segmentation quality and rule sets vary by implementation and JDK version; for demanding NLP requirements, evaluate specialized libraries or models.

### Emoji and Grapheme Clusters

Emoji such as `🙂` or ZWJ sequences using `U+200D` are excluded from `\p{L}` tokens. If the requirement is to count emoji or "user-perceived characters", that is **a different problem**, requiring grapheme cluster or emoji sequence handling; `String.length()` cannot be used as an emoji count.

## 12. Reading UTF-8 Text with Files.lines and Closing Resources

In production applications, data often arrives from a file. `Files.lines` produces a `Stream<String>` of lines that fits the pipeline naturally:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> countWordsFromFile(Path path)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .flatMap(line -> tokenize(line).stream())
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));
    }
}
```

Key principles:

1. **Specify UTF-8 explicitly**: do not rely on the operating system's default charset.
2. **Use `try-with-resources`**: a Stream from `Files.lines` backs an I/O resource and must be closed when finished.
3. **Keep the terminal operation inside the `try` block**: if you close the Stream before calling `collect`, the underlying source is already closed.
4. **Never reuse a consumed Stream**: to run another report on the same file, reopen the source or design a multi-metric aggregator in a single pass.
5. **Handle errors at the proper boundary**: opening a file can throw `IOException`; read errors during lazy iteration can surface as `UncheckedIOException`. Never swallow errors and report a partial frequency table as success.

For large files, `Files.lines` avoids loading the **entire file into one String**. Even so, `tokenize` as implemented here still creates a token List **per line**, and `groupingBy` retains a Map of all distinct tokens; memory can still grow with the number of unique tokens or maximum line length.

Do not apply `parallel()` to file sources indiscriminately: effectiveness depends on the Spliterator, chunking, regex cost, I/O, and ordering. Always verify correctness before benchmarking performance.

## 13. Per-Line vs. Whole-Document Statistics

Depending on the product, **corpus frequency** differs from **document/line frequency** (number of lines containing a token):

```text
Line 1: java java
Line 2: java stream

Token frequency:
  java   = 3
  stream = 1

Lines containing token:
  java   = 2
  stream = 1
```

To count **how many lines contain** a token, deduplicate **within each line**, not across the whole document:

```java
List<String> sampleLines = List.of(
        "java java",
        "java stream"
);

Map<String, Long> linePresence = sampleLines.stream()
        .flatMap(line -> tokenize(line).stream().distinct())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(linePresence.get("java"));   // 2
System.out.println(linePresence.get("stream")); // 1
```

`distinct()` sits **inside each line's Stream**, so each token contributes at most once per line. Placing `distinct()` after the document-wide `flatMap` would collapse every token to count 1 and yield wrong line counts.

Another metric is **relative frequency**:

```java
long total = frequencies.values().stream()
        .mapToLong(Long::longValue)
        .sum();

double javaShare = total == 0
        ? 0.0
        : (double) frequencies.getOrDefault("java", 0L) / total;

System.out.println(javaShare); // approx. 0.23077 = 3/13
```

When reporting percentages, state clearly whether the denominator is **all tokens** or **tokens after stop-word filtering**. For text with zero tokens, avoid silently reporting `0%` if the report must distinguish "no data".

## 14. Parallel Pipelines: Safety Around State and Ordering

In principle, `groupingBy`/`counting` can run over a parallel source:

```java
Map<String, Long> parallelFrequencies = lines.parallelStream()
        .flatMap(line -> tokenize(line).stream())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(parallelFrequencies.equals(frequencies)); // true
```

This example has favorable properties:

- `lines` is a stable List not mutated during execution.
- `normalizeForCounting` is a pure value transformation with no global mutations.
- Each call to `tokenize` creates its **own** `Matcher` and token list.
- `Pattern` is safely shared because it holds no `Matcher` search state.
- `Collectors.groupingBy(..., counting())` manages intermediate accumulators and combining.

**Do not use** a shared `HashMap` to increment counts:

```java
Map<String, Long> shared = new HashMap<>();

// WRONG: mutating a shared HashMap from parallel tasks.
lines.parallelStream()
        .flatMap(line -> tokenize(line).stream())
        .forEach(word -> shared.merge(word, 1L, Long::sum));
```

`HashMap.merge` does not make the Map thread-safe. Concurrent updates can lose data or throw errors. Using a collector as above is the clean choice.

If ordering is unneeded and datasets are very large, you can **benchmark** `Collectors.groupingByConcurrent`:

```java
ConcurrentMap<String, Long> concurrentFrequencies =
        lines.parallelStream()
                .flatMap(line -> tokenize(line).stream())
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(),
                        Collectors.counting()
                ));
```

`groupingByConcurrent` is a concurrent, unordered collector; it **does not automatically guarantee faster execution**. To produce a deterministically ordered table, **sort entries after counting**, regardless of which collector built the Map.

In particular, **never share a single `Matcher` across threads**. `Matcher` stores mutable cursor and capture-group state updated by `find()`; sharing it corrupts both tokens and counts.

## 15. Complete Java 17+ Example: Unicode Analysis and Ranked Table

The standalone program below normalizes to NFC lowercase, extracts Unicode tokens, builds frequencies, sorts descending by occurrence count, computes statistics, and verifies expected results.

```java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class UnicodeWordFrequencyDemo {
    private static final Pattern WORD =
            Pattern.compile("\\p{L}[\\p{L}\\p{M}]*");

    record WordCount(String word, long count) {}
    record Summary(
            long lines,
            long tokens,
            long distinctTokens,
            long sourceCodePoints,
            double avgTokenCodePoints
    ) {}

    static String normalize(String input) {
        String nfc = Normalizer.normalize(
                input, Normalizer.Form.NFC);
        String lower = nfc.toLowerCase(Locale.ROOT);
        return Normalizer.normalize(lower, Normalizer.Form.NFC);
    }

    static List<String> tokenize(String text) {
        Matcher matcher = WORD.matcher(normalize(text));
        List<String> tokens = new ArrayList<>();
        while (matcher.find()) {
            tokens.add(matcher.group());
        }
        return tokens;
    }

    static Map<String, Long> frequencies(List<String> lines) {
        return lines.stream()
                .flatMap(line -> tokenize(line).stream())
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));
    }

    static List<WordCount> rank(Map<String, Long> frequencies) {
        return frequencies.entrySet().stream()
                .sorted(
                        Comparator.<Map.Entry<String, Long>>comparingLong(
                                entry -> entry.getValue()
                        ).reversed().thenComparing(Map.Entry::getKey)
                )
                .map(entry -> new WordCount(
                        entry.getKey(), entry.getValue()
                ))
                .toList();
    }

    static Summary summarize(
            List<String> lines, Map<String, Long> frequencies) {
        long totalTokens = frequencies.values().stream()
                .mapToLong(Long::longValue)
                .sum();

        long sourceCodePoints = lines.stream()
                .mapToLong(line -> line.codePointCount(
                        0, line.length()
                ))
                .sum();

        double averageLength = lines.stream()
                .flatMap(line -> tokenize(line).stream())
                .mapToInt(token -> token.codePointCount(
                        0, token.length()
                ))
                .average()
                .orElse(0.0);

        return new Summary(
                lines.size(),
                totalTokens,
                frequencies.size(),
                sourceCodePoints,
                averageLength
        );
    }

    public static void main(String[] args) {
        List<String> text = List.of(
                "CÀ phê, cà PHÊ!",
                "Trà trà, café cafe\u0301.",
                "Java Stream — JAVA stream JAVA."
        );

        Map<String, Long> frequencies = frequencies(text);
        List<WordCount> ranking = rank(frequencies);
        Summary summary = summarize(text, frequencies);

        if (summary.tokens() != 13
                || summary.distinctTokens() != 6
                || frequencies.get("java") != 3L
                || frequencies.get("café") != 2L
                || frequencies.get("cà") != 2L) {
            throw new AssertionError("Wrong token count result");
        }

        List<WordCount> expected = List.of(
                new WordCount("java", 3),
                new WordCount("café", 2),
                new WordCount("cà", 2),
                new WordCount("phê", 2),
                new WordCount("stream", 2),
                new WordCount("trà", 2)
        );
        if (!ranking.equals(expected)) {
            throw new AssertionError("Wrong frequency table ordering");
        }

        System.out.println("Word     | Count");
        System.out.println("---------+------");
        ranking.forEach(item -> System.out.printf(
                "%-8s | %d%n", item.word(), item.count()
        ));
        System.out.printf(
                "Lines=%d, tokens=%d, distinct=%d%n",
                summary.lines(), summary.tokens(),
                summary.distinctTokens()
        );
        System.out.printf(
                "Average token length (code points)=%.2f%n",
                summary.avgTokenCodePoints()
        );
        System.out.println("PASS");
    }
}
```

**Expected frequency results:**

```text
java   -> 3
café   -> 2
cà     -> 2
phê    -> 2
stream -> 2
trà    -> 2
Total tokens: 13
Distinct tokens: 6
Average token length: approx. 3.69 code points
```

### Design Explanation

1. `WORD` is a shared `Pattern`, while each `tokenize` call creates its own `Matcher`.
2. `Normalizer.Form.NFC` and `Locale.ROOT` establish an explicit key-unification policy for counting.
3. `flatMap` flattens tokens from multiple lines into one stream.
4. `groupingBy(identity, counting())` builds the frequency Map without manual HashMap mutation outside the pipeline.
5. `rank` sorts by **count descending**, then **token ascending by `String.compareTo`**, providing an explicit tie-breaker.
6. `summarize` tracks total tokens, distinct words, and source code points separately so metrics are not confused.
7. Explicit `if`/`throw` checks fail even when the JVM is launched without `-ea`.

**Example limitations:** this reports **letter-sequence token frequencies**, not multi-syllable Vietnamese word segmentation or full handling of every Unicode edge case. For large datasets, a List-returning tokenizer adds allocation overhead; for complex linguistic rules, use a dedicated tokenizer and matching test suite.

## 16. Practice Exercises

### Exercise 1 — NFC Normalization and Verification

Given:

```java
List<String> data = List.of(
        "Café",
        "cafe" + "\u0301",
        "CAFÉ"
);
```

**Task:** apply this lesson's NFC/lowercase policy to count all three occurrences under one key. Explain why calling `toLowerCase(Locale.ROOT)` alone without `Normalizer` is insufficient.

**Suggested solution:**

```java
Map<String, Long> counts = data.stream()
        .flatMap(item -> tokenize(item).stream())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("café")); // 3
System.out.println(counts.size());      // 1
```

### Exercise 2 — Top-N Table with Tie-Breaking

Given lines:

```java
List<String> logs = List.of(
        "Java Java Stream",
        "Stream API",
        "Java API"
);
```

**Task:** build a frequency table and extract the two most frequent tokens. On equal frequencies, sort tokens ascending by `String.compareTo`.

**Solution:**

```java
Map<String, Long> logCounts = frequencies(logs);

List<WordCount> topTwo = rank(logCounts).stream()
        .limit(2)
        .toList();

System.out.println(topTwo);
// [WordCount[word=java, count=3],
//  WordCount[word=api, count=2]]
```

`stream` also appears twice, but `api` precedes `stream` in the tie-break step.

### Exercise 3 — Counting Lines Containing Each Token

Given:

```java
List<String> comments = List.of(
        "java java",
        "stream java",
        "stream stream"
);
```

**Task:** compute both corpus token frequencies and the number of lines containing each token. Distinguish the two metrics.

**Solution:**

```java
Map<String, Long> occurrences = frequencies(comments);

Map<String, Long> documentFrequency = comments.stream()
        .flatMap(line -> tokenize(line).stream().distinct())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(occurrences.get("java"));       // 3
System.out.println(documentFrequency.get("java")); // 2
System.out.println(occurrences.get("stream"));      // 3
System.out.println(documentFrequency.get("stream")); // 2
```

### Exercise 4 — Emoji and Supplementary Unicode

Given:

```java
String sample = "A🙂é";
```

**Task:** explain why `sample.length() == 4` while `sample.codePointCount(0, sample.length()) == 3`; distinguish code point count, letter-token count, and perceived character count.

**Answer:** `A` and `é` each take one UTF-16 unit in composed form, while emoji `🙂` takes two units; total `length = 4`. There are three Unicode code points. Under this lesson's regex policy, there are two letter tokens (`a` and `é` after normalization); emoji is not counted as a token. Counting grapheme clusters is a separate criterion.

### Exercise 5 — Real File Reading and Resource Checks

**Task:** write a method accepting `Path`, reading UTF-8, counting tokens, and closing the Stream even when an exception occurs. Explain why `Files.lines` must never be called and left unclosed.

**Solution:** refer to `countWordsFromFile` in section 12. Place the entire terminal operation inside `try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8))`. Do not suppress `IOException` or `UncheckedIOException`.

### Exercise 6 — Adjusting the Tokenization Policy

**Extension task:** the product wants `"Java17"` kept as a single token and `#` in hashtags treated as part of a specific token class. Redefine the rules—for example, allowing digits after the initial letter—then test `Java17`, `Java-17`, `#Java`, emails, and accented Unicode data.

**Hint:** you can start from `\p{L}[\p{L}\p{M}\p{N}]*` to permit Unicode digits after the leading letter; hashtags require a different rule. Any change to token definitions **changes statistical outputs**, so update tests and documentation accordingly.

## 17. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `"CÀ"` and `"cà"` become two keys | No case normalization | Apply an explicit locale rule, e.g., `toLowerCase(Locale.ROOT)`. |
| `"café"` and `"cafe" + combining mark` become two keys | Different Unicode encodings | Normalize with `Normalizer.Form.NFC` before grouping. |
| `"phê,"` and `"phê"` counted separately | Punctuation retained in tokens | Tokenize according to the defined Unicode policy. |
| Wrong results on emoji or non-BMP characters | Iterating `char` as full characters | Use `codePoints()` or proper grapheme segmentation. |
| Word count equals `frequencies.size()` and is surprisingly low | Confusing distinct tokens with total occurrences | Sum Map values via `mapToLong(...).sum()`. |
| Frequency table prints in inconsistent order | `groupingBy` makes no Map order guarantee | Sort entries by count and token with tie-breaking. |
| `toMap(key, value)` throws an exception | Duplicate token keys | Use `groupingBy(..., counting())` or `toMap(..., Long::sum)`. |
| Sharing one matcher across threads drops tokens | `Matcher` is mutable and not thread-safe | Create a fresh `Matcher` per tokenizer call. |
| Stop-word filter drops critical words | Missing list/order policy | Define analytical purpose and keep pre-/post-filter metrics. |
| `Files.lines` left unclosed | Stream backs an OS file handle | Use `try-with-resources` with the terminal operation inside `try`. |
| Vietnamese compound words split incorrectly | Regex extracts letter tokens, not lexical words | Use a language-aware tokenizer when needed. |
| Huge files run out of memory | Too many unique words or intermediate token Lists | Size limits, streaming tokenizer, batching, or out-of-core storage. |
| `parallelStream()` is no faster | Splitting overhead, Matcher/List allocations, Map merging | Benchmark in practice; keep transformations free of shared state. |

## 18. Text Analytics Pipeline Handoff Checklist

1. **Token definition:** are digits, hashtags, hyphens, apostrophes, emoji, or multi-syllable compounds included?
2. **Unicode:** are NFC/NFKC, lowercasing, and locale policies explicitly documented?
3. **Length metric:** are statistics measured in UTF-16 code units, code points, or grapheme clusters?
4. **Tokenization:** does `Pattern` accept `\p{M}` and handle combining marks as intended?
5. **Nulls:** can input lines be null? If so, filter or fail before calling `Normalizer`.
6. **Stop words:** has the list been normalized using the exact same rules as tokens?
7. **Counts:** are total token count and distinct token count tracked as separate metrics?
8. **Ranking:** is there a primary sort by frequency and a deterministic tie-breaker?
9. **Empty text:** are empty Maps and `OptionalDouble.empty()` handled according to policy?
10. **Files:** is UTF-8 specified, `Files.lines` closed, and mid-pipeline read errors preserved?
11. **Parallelism:** per-task Matchers, no shared mutable Maps, and sequential vs. parallel equivalence tested?
12. **Language limits:** for Vietnamese, is syllable counting distinguished from compound-word counting?
13. **Performance:** have token counts, unique token counts, maximum line size, and memory been measured?
14. **Testing:** does coverage include NFC/NFD Vietnamese, English, emoji, digits, punctuation, empty text, and stop words?

## Key Takeaways

Building a **word frequency table** is a versatile pattern combining multiple **Java Stream API** techniques: input normalization, `flatMap` to flatten per-line tokens, `groupingBy(Function.identity(), counting())` to count, and `sorted` to produce a deterministic ranking.

For Unicode text, **your token definition and normalization policy determine the result**. `String.length()` counts UTF-16 units rather than always matching perceived characters; `Normalizer.Form.NFC` unifies canonically equivalent diacritic encodings; `\p{L}` and `\p{M}` help regex match letters with combining marks. The illustrative regex still extracts **letter tokens** rather than understanding Vietnamese compound words or every writing system.

Always distinguish total tokens from distinct tokens, sort frequency tables with deterministic tie-breakers, close I/O streams via `try-with-resources`, and avoid updating shared Maps or Matchers inside parallel pipelines. Only after proving correctness on targeted Unicode test cases should you measure and optimize performance.
