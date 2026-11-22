# Building a Java String API Decision Table and Self-Assessment Scenarios

## 1. Practice goal

In Java, the same text-processing task can be performed using multiple APIs: `String`, `StringBuilder`, `StringBuffer`, `CharSequence`, `String.split`, `Pattern`/`Matcher`, `String.lines`, `Stream`, `Charset`, `Normalizer`, `Comparator`, and more. Picking the right API depends on **real requirements**, not just writing fewer lines of code.

After this lesson, you should be able to:

1. Turn a string-processing requirement into criteria: whether regex is used, whether empty data must be preserved, which Unicode level is required, whether repeated mutation/concatenation occurs, whether values serve as keys, and whether values are stored long-term or shared across threads.
2. Use a **decision table** to select the right API and explain why other options could fail.
3. Independently solve scenarios covering splitting, find/replace, text construction, Unicode, equality checks, sorting, line reading, and encoding.
4. Run a Java 17+ program with real assertions, then self-grade using the answers and rubric.

This is a comprehensive synthesis lesson in the **Java Core — String** context. Short snippets inside the tables are expressions or code fragments placed within a Java method; the complete runnable program is in Section 5.

## 2. Before choosing: define the processing contract

Answer these questions before picking an API:

- **Literal search or pattern search?** For example, is a dot in the data a literal period or a regex wildcard?
- **Read-only, or building new results repeatedly?** A single `replace` returning a new `String` may suffice; appending many pieces in a loop suits `StringBuilder`.
- **Is the object mutable?** A `CharSequence` can be a `StringBuilder` or a `CharBuffer` view; to store a stable value, define a snapshot.
- **What counts as "one character"?** UTF-16 code unit, Unicode code point, or display grapheme cluster? `String.length()` is not always the user-visible character count.
- **Are empty strings, `null`, whitespace, and newlines meaningful?** For example, simplified CSV needing trailing empty fields uses `split(delimiter, -1)`.
- **Do equality and ordering share the same rules?** `equals` is case-sensitive, whereas `CASE_INSENSITIVE_ORDER` can treat two distinct strings as the same key in a `TreeSet`.
- **What are the charset and locale?** Byte encoding requires specifying a `Charset`; language-specific comparison/formatting may need `Locale` and `Collator`.

When a prompt leaves an important condition unspecified, **state explicit assumptions** or ask the requirements author. For instance, "split CSV data" is not enough to conclude `split(",")` works, because full CSV supports double quotes, commas inside fields, and escaping rules.

## 3. Task-based API decision table

| Specific need | API to consider | Conditions and common pitfalls |
| --- | --- | --- |
| Hold a stable text value | `String` | Immutable; suitable for returns, caches, map keys; `StringBuilder`/`CharSequence` are not automatically immutable |
| Join many fragments on **one thread** | `StringBuilder.append(...)`, `toString()` | Avoids creating repeated intermediate strings; mutable builder, not thread-safe |
| Concatenate on an object with individually synchronized methods | `StringBuffer` | Synchronizes individual methods; does not replace synchronization across multi-step algorithms |
| Read-only API accepting text from multiple implementations | `CharSequence` | Does not guarantee immutability or content-based `equals`; snapshot with `toString()` before storing long-term |
| Exact equality of two `String`s | `equals`, `Objects.equals` when nullable | Case-sensitive; `Objects.equals` does not turn arbitrary `CharSequence`s into content equality |
| Compare a `String` with a `CharSequence` | `String.contentEquals(...)` | Suitable for comparing current characters, still mind concurrent mutations |
| Case-insensitive `String` comparison | `equalsIgnoreCase`, `compareToIgnoreCase` | Not locale-aware collation for every language; does not change `String.equals` |
| Case-insensitive sorting | `String.CASE_INSENSITIVE_ORDER` | `compare == 0` can occur when `equals == false`; `TreeSet`/`TreeMap` treat them as the same key |
| Case-insensitive sorting **while keeping every distinct `String`** | `String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` | Tie-breaker keeps the comparator consistent with `String.equals` |
| Language-specific comparison | `Collator.getInstance(locale)` | Must configure sensitivity strength for accents/case and test with the target language |
| Literal substring lookup | `contains`, `indexOf`, `startsWith`, `endsWith` | Does not interpret regex; `indexOf` returns `-1` when absent |
| Slice a range using UTF-16 indices | `substring(start, end)` | `start` inclusive, `end` exclusive; verify bounds |
| Literal text replacement | `String.replace(target, replacement)` | No need to escape `.`, `$`, or `\` for regex/replacement syntax |
| Intentional regex replacement | `replaceAll(regex, replacement)`, `replaceFirst(...)` | Regex and replacement have **different syntaxes**; `$1` can refer to capture groups |
| Using `replaceAll` when both sides are literal text | `Pattern.quote(target)` and `Matcher.quoteReplacement(value)` | Quote **both sides**; quoting only the regex does not protect a replacement containing `$` or `\` |
| Reuse a regex across many inputs | `Pattern.compile(regex)`, `pattern.matcher(text)` | `Pattern` is reusable; `Matcher` is stateful, do not share carelessly across threads |
| Simple regex splitting | `split(regex)` or `split(regex, limit)` | `limit=0` drops trailing empty tokens; `-1` keeps them; regex can match zero-width |
| Parse **full CSV** | Dedicated CSV library | `split(",")` cannot handle commas inside quoted fields, escaped quotes, or embedded newlines |
| Join parts with a separator | `String.join(separator, ...)`, `Collectors.joining(...)` | `joining` is convenient inside an existing stream; verify null handling per contract |
| Split text into lines | `String.lines()` | Recognizes `\n`, `\r`, `\r\n`; does not emit a trailing empty line merely for a final line terminator |
| Strip boundary whitespace | `strip()`, `stripLeading()`, `stripTrailing()` | Based on `Character.isWhitespace`; differs from `trim()` (code units ≤ U+0020) |
| Check whitespace-only text | `isBlank()` | Differs from `isEmpty()`: a string of spaces is not empty yet is blank |
| Iterate UTF-16 code units | `chars()`, `charAt(...)` | Surrogate pairs appear as two separate `char`s |
| Iterate Unicode code points | `codePoints()`, `codePointAt(...)` | A code point can take two code units; rebuild via `StringBuilder.appendCodePoint(...)` |
| Normalize Unicode representations | `Normalizer.normalize(s, Form.NFC)` | Visually identical strings may differ in code points; does not replace linguistic collation |
| Convert between bytes and `String` | `getBytes(StandardCharsets.UTF_8)`, `new String(bytes, StandardCharsets.UTF_8)` | Specify charset on both sides; never rely on the default charset for data exchange |
| Parameterized formatting | `String.format(Locale,...)` or `"..." .formatted(...)` | Consider locale for numbers/dates; for simple concatenation `StringBuilder`/`join` can be clearer |

This table does not mean each API serves only one task; what matters is matching **the contract to real data**. For instance, `replaceAll` works fine for replacing literal dots if the regex is properly escaped, yet when regex is unnecessary, `replace` is shorter and less error-prone.

## 4. Scenario table for choosing APIs yourself

Before checking the answers in Section 6, write down **the API, rationale, and risks/tests** for each scenario. Difficulty increases gradually.

| ID | Scenario | Questions to answer yourself |
| --- | --- | --- |
| T1 | Given `"a.b.c"`, you want to replace every **literal dot** with `/`. | Which method do you pick? Why is `replaceAll(".", "/")` wrong? |
| T2 | A user searches for a keyword containing `[` or `$` and replaces it with a string containing `$1` and backslashes, all literal text. The system forces using `replaceAll`. | Which functions must quote the search side and the replacement side? |
| T3 | Data string `"a,b,,"` represents 4 fields, where the last two are empty. | Which `limit` do you pass to `split`? Should this serve as a full CSV parser? |
| T4 | Remove the 🚀 emoji from `"A🚀B"` without corrupting surrogate pairs. | Use `chars()` or `codePoints()`? How do you rebuild the `String`? |
| T5 | Concatenate thousands of text fragments inside a loop on one thread. | Use cumulative `+` or `StringBuilder`? Why? |
| T6 | An API accepts a `CharSequence` to store as a title in a cache. The caller might pass a `StringBuilder` and mutate it later. | Keep the reference or take a `String` snapshot? |
| T7 | Compare `"Java"` and `"java"` as the same keyword in one place, while another system distinguishes the two keys via `equals`. | When to use `equalsIgnoreCase`, and when to use `String.equals`? |
| T8 | Use a `TreeSet` for case-insensitive ordering while keeping both `"Java"` and `"java"`. | What secondary comparator is needed? |
| T9 | Receive `"é"` and `"e"` + combining acute accent; normalize storage form before exact comparison. | Which tool do you choose? Is calling `toLowerCase()` alone sufficient? |
| T10 | Send Vietnamese text over the network so both sides decode identically. | Which APIs must specify a `Charset`? |
| T11 | Split multiple lines that may use CRLF or LF, stripping line terminators. | Is `lines()` or `split("\n")` clearer? |
| T12 | Check whether an input field containing only spaces/tabs/newlines has no meaningful data. | Choose `isEmpty()` or `isBlank()`? |
| T13 | Sort personal names according to Vietnamese rules or a specific locale. | Is `CASE_INSENSITIVE_ORDER` enough? |
| T14 | Input from the user really is a regex with a capturing group to replace `42` with `[42]`. | When must you **preserve** `(\\d+)` and `$1` instead of quoting them? |

**How to work through it:** write your answers independently first, then compare with Section 6. For every scenario, state both the choice **and the condition making it right**. For example, T3 must mention "preserving trailing empty fields" rather than only writing `split(",")`.

## 5. Standalone runnable Java 17+ test program

Save as **`StringApiDecisionPractice.java`**. This checks core choices without needing JUnit or external libraries. `same` and `check` throw `AssertionError` if results fail; do not rely on Java's `assert` statement, which is disabled unless `-ea` is passed.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class StringApiDecisionPractice {
    private static int passed = 0;

    static void same(String caseName, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(caseName + ": expected <" + expected
                    + "> but got <" + actual + ">");
        }
        passed++;
    }

    static void check(String caseName, boolean condition) {
        if (!condition) throw new AssertionError(caseName);
        passed++;
    }

    public static void main(String[] args) {
        same("strip", "Java", " \tJava \n".strip());
        check("isBlank", " \t\n".isBlank());

        same("literal replace", "a/b/c", "a.b.c".replace(".", "/"));
        same("quoted regex and replacement", "a$1\\tmpb",
                "a.b".replaceAll(Pattern.quote("."),
                        Matcher.quoteReplacement("$1\\tmp")));

        check("split preserving empties",
                Arrays.equals(new String[]{"a", "b", "", ""},
                        "a,b,,".split(",", -1)));
        check("split dropping trailing empties",
                Arrays.equals(new String[]{"a", "b"},
                        "a,b,,".split(",")));

        same("join", "a-b-c", String.join("-", List.of("a", "b", "c")));
        same("lines", List.of("one", "two"), "one\ntwo\n".lines().toList());

        StringBuilder builder = new StringBuilder();
        "A\uD83D\uDE80B".codePoints()
                .filter(cp -> cp != 0x1F680)
                .forEach(builder::appendCodePoint);
        same("code point filter", "AB", builder.toString());

        String message = "C\u00E0 ph\u00EA";
        byte[] encoded = message.getBytes(StandardCharsets.UTF_8);
        same("UTF-8 round trip", message,
                new String(encoded, StandardCharsets.UTF_8));

        same("Unicode NFC", "\u00E9",
                Normalizer.normalize("e\u0301", Normalizer.Form.NFC));

        check("equalsIgnoreCase", "Java".equalsIgnoreCase("java"));
        check("String.equals case sensitive", !"Java".equals("java"));

        TreeSet<String> folded = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        folded.add("Java");
        folded.add("java");
        same("TreeSet collapses keys", 1, folded.size());

        StringBuilder mutable = new StringBuilder("x");
        CharSequence reference = mutable;
        String snapshot = mutable.toString();
        mutable.append("y");
        same("immutable snapshot", "x", snapshot);
        same("mutable CharSequence reference", "xy", reference.toString());

        check("contentEquals", "cat".contentEquals(new StringBuilder("cat")));
        same("regex capture", "id=[42]", "id=42".replaceAll("(\\d+)", "[$1]"));
        same("indexOf literal", 2, "a.b.c".indexOf("b"));
        same("substring bounds", "b.c", "a.b.c".substring(2, 5));

        System.out.println("splitCount=" + "a,b,,".split(",", -1).length);
        System.out.println("treeSetSize=" + folded.size());
        System.out.println("codePointsFiltered=" + builder);
        System.out.println("utf8RoundTrip=" + message.equals(
                new String(encoded, StandardCharsets.UTF_8)));
        System.out.println("snapshot=" + snapshot);
        System.out.println("PASS: " + passed + " checks");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StringApiDecisionPractice.java
java StringApiDecisionPractice
~~~

Exact stdout when all 20 checks pass:

~~~text
splitCount=4
treeSetSize=1
codePointsFiltered=AB
utf8RoundTrip=true
snapshot=x
PASS: 20 checks
~~~

These checks verify key decisions beyond merely running without crashes: `split(",", -1)` actually preserves 4 fields; `Pattern.quote` combined with `Matcher.quoteReplacement` keeps both `$` and `\` literal; `codePoints()` filters the whole emoji; `UTF-8` round-trips cleanly; `TreeSet` identifies equivalent keys via its comparator; and the `String` snapshot preserves the old value when the builder mutates.

## 6. Answers and explanations for each scenario

| Scenario | Recommended answer / API | Brief explanation |
| --- | --- | --- |
| **T1** | `"a.b.c".replace(".", "/")` | `.` in `replaceAll` is a regex wildcard, whereas `replace` matches literal text. Result: `a/b/c`. |
| **T2** | `text.replaceAll(Pattern.quote(target), Matcher.quoteReplacement(value))` | Target and replacement have **two independent syntaxes**. Omitting replacement quoting lets `$1` be parsed as a group reference. |
| **T3** | `"a,b,,".split(",", -1)` | Result `["a", "b", "", ""]`. Default `split(",")` discards trailing empty tokens. Full CSV requires a dedicated parser. |
| **T4** | `text.codePoints().filter(cp -> cp != 0x1F680).forEach(builder::appendCodePoint)` | A supplementary emoji is one code point yet two UTF-16 code units; processing via `chars()` risks splitting surrogate pairs. |
| **T5** | `StringBuilder.append(...)` then `toString()` | A mutable buffer reduces intermediate `String` creation across many loop iterations; do not pass the same builder into `parallel()` for concurrent appends. |
| **T6** | `String snapshot = Objects.requireNonNull(input).toString()` | `CharSequence` may be mutable. Taking a snapshot keeps content stable after returning; synchronize if the source can be mutated concurrently. |
| **T7** | `equalsIgnoreCase` for case-insensitive matching; `equals` for exact keys | These two rules do not substitute for each other; `HashMap`/`HashSet` use `equals` and `hashCode`. |
| **T8** | `String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` | The secondary comparison breaks ties when case-insensitive comparison returns 0; two strings unequal by `equals` stay distinct keys. |
| **T9** | `Normalizer.normalize(s, Normalizer.Form.NFC)` then compare per contract | Two Unicode representations can differ in code points. `toLowerCase` is not Unicode NFC normalization. |
| **T10** | `text.getBytes(StandardCharsets.UTF_8)` and `new String(bytes, StandardCharsets.UTF_8)` | Both sides use the same charset; the protocol must agree on UTF-8. |
| **T11** | `String.lines()` | Directly expresses line iteration and handles common line terminators; naive `split("\n")` can leave `\r` behind on CRLF. |
| **T12** | `isBlank()` | `" \t\n".isEmpty()` is false while `isBlank()` is true. `isBlank` relies on `Character.isWhitespace`, so not every visually space-like Unicode character counts as whitespace. |
| **T13** | Consider `Collator.getInstance(locale)` and test with real locale data | `CASE_INSENSITIVE_ORDER` is case-ignoring `String` comparison, not linguistic sorting. |
| **T14** | `"id=42".replaceAll("(\\d+)", "[$1]")` | Here regex and group reference are **intentional**; do not quote regex or replacement when capture-group functionality is needed. Result: `id=[42]`. |

For **T4**, the code example is a pipeline fragment inside a method given a `text` variable and a `StringBuilder builder`; the emoji removal and `AB` result are verified in the complete program.

For **T13**, a `Collator` may treat strings that differ under `String.equals` as equal depending on sensitivity strength. If used as the comparator of a `TreeMap`/`TreeSet`, you must still decide whether `compare(a,b)==0` is allowed to merge keys.

## 7. Self-assessment rubric and review guide

Each scenario from T1 to T14 scores up to **2 points**:

- **1 point**: choosing the right API (or an equivalent valid approach) with an example matching the requirement.
- **1 point**: explaining the **underlying mechanism or risk**, such as zero-width regex, trailing empty tokens, UTF-16 width, mutable snapshots, comparators inconsistent with `equals`, or unquoted replacement errors.

Maximum total **28 points**. This is a study self-check rubric, not a formal certification:

| Score | Suggested interpretation | Next action |
| --- | --- | --- |
| 0–13 | Need to reinforce core concepts and API syntax | Re-practice earlier examples, run the code, and predict output before checking |
| 14–21 | Picked most APIs correctly but missed edge-condition explanations | Review missed categories and write more tests instead of memorizing method names |
| 22–26 | Solid grasp of common scenarios | Try variants with Unicode data, `null`, special regexes, collections, and charsets |
| 27–28 | Fully able to justify this decision table | Propose APIs for a small feature, state the contract, and design tests yourself |

### Self-directed follow-up exercises

1. Replace `"a,b,,"` with `",,a,"`. Predict `split(",", 0)`, `split(",", -1)`, and `split(",", 2)`; compare against the actual arrays.
2. Replace the dot with `|` or `[` in the target, and the replacement with `$1\log`. Try both `replace` and quoting both sides in `replaceAll`; verify equality with `equals`.
3. Switch the `TreeSet` from `CASE_INSENSITIVE_ORDER` to the tie-breaker comparator; check element count and ordering for `"JAVA"`, `"Java"`, `"java"`.
4. Replace 🚀 with another supplementary-plane emoji; check `length()`, `codePoints().count()`, and filtering/rebuilding with `appendCodePoint`.
5. Test an input `CharSequence` backed by a mutable `StringBuilder`: store the reference vs taking a `String` snapshot, then mutate the builder; describe the difference.
6. Test text mixing `\r\n`, `\n`, and `\r` with `lines()`. Explicitly check leading and trailing blank-line cases.
7. Normalize an accented Vietnamese string to NFC; predict how `equals` can differ before and after normalization.

Record each extension as **input → chosen API → expected output → actual output → reason**. That confirms the API choice fits the contract, not merely a method name.

## 8. Traps that lead to wrong API choices

- **Conflating literal text with regex:** `replace`/`contains` search literally, while `replaceAll`/`split` take regex. Characters like `.` or `|` can completely change meaning.
- **Forgetting `split`'s `limit` parameter:** `split(regex)` equals `split(regex, 0)`, dropping trailing empty fields. Furthermore, a zero-width regex match at the start of a string does not emit a leading empty token, unlike a positive-width match.
- **Treating `String.length()` as visible character count:** Java uses UTF-16; code points differ from grapheme clusters. Even `codePoints()` does not group joined emoji sequences or letters with combining marks.
- **Assuming every `CharSequence` implements content-based `equals`:** `StringBuilder` does not override `equals` like `String`, and `CharBuffer` has view state; define snapshots and comparisons explicitly.
- **Using a case-insensitive comparator for `TreeSet` without intending key merging:** `compare == 0` can drop case variants.
- **Using `toLowerCase()` as universal normalization across languages:** locale effects, Unicode normalization, and case folding are distinct concerns.
- **Converting bytes without specifying a charset:** accented data can corrupt if two sides use different encodings. Specify `UTF-8` at encoding boundaries.
- **Checking output only by eye:** empty strings, backslashes, Unicode combining marks, and comparator equivalence need explicit assertions and size checks.

## 9. Practice conclusion

No single `String` API is optimal for every scenario. API selection must begin with the **data contract**: literal text or regex; mutable or snapshot; UTF-16 code units or code points; content equality or comparator ordering; preserving empty values or not; and which charset/locale applies. After choosing, test at least one normal case and one **edge case capable of breaking assumptions**. When you can explain both the choice and its risks, you are ready to use this table to self-review and design verifiable Java string-processing code.