# Fundamentals and Study Sequence for Java Core String

## 1. Goals and Position of the Topic

`String` is the data type used to represent **character strings** in Java. It is a class in the `java.lang` package, which is imported automatically. Learning `String` is not just memorizing methods: you need to understand the difference between **values and references**, **immutability**, how Java represents **Unicode**, and how to process text safely and effectively.

After studying this topic, learners should be able to:

- Create strings, read, and transform content without confusion about immutability.
- Compare strings by content, distinguish `==` from `equals()`, and handle `null` cases.
- Search, slice, join, split, replace, format, and normalize text.
- Explain `String Pool`, `StringBuilder`, character encoding, and common Unicode pitfalls.
- Choose the appropriate API in practical scenarios and verify behavior with runnable Java programs.

**Prerequisites:** prior familiarity with variables, primitive types, operators, `if`, loops, methods, arrays, and basics of classes/objects. The examples target **Java 17+**; several modern APIs such as `strip()`, `isBlank()`, `lines()`, and `repeat()` have been available since Java 11. The roadmap below progresses from fundamentals to applications and then optimization.

## 2. Reading Sequence for the Lessons in This Chapter

The goal of this guide is to **know what to study first, what to practice next, and how to prove understanding**. The dedicated lessons hold the detailed explanations and hands-on code; when you need to look up a specific behavior, revisit that exact lesson rather than trying to memorize the entire API in one sitting.

| Order | Lesson to read | After this lesson, what can you self-check? |
| --- | --- | --- |
| 1 | What is String and its role in representing text in Java | Explain that String is an object used for text and does not automatically determine charset or data safety. |
| 2 | Relationships between String, char[], CharSequence, and Object | Distinguish upcasts, copies, mutable views, and type casts. |
| 3 | Distinguishing string content from a string reference variable | Sketch alias diagrams and explain `==`, `equals()`, and the string pool. |
| 4 | Empty strings, blank strings, null, and the string "null" | Write null-safe conditions without losing any of the four input states. |
| 5 | Why String is a final class and immutable | Explain `final class`, `final` on variables, and immutability with standalone examples. |
| 6 | Operation categories: reading, comparing, searching, transforming, and encoding | Choose `substring`, `indexOf`, `replace`, regex, Unicode, and UTF-8 as required. |
| 7 | Choosing String, StringBuilder, or StringBuffer based on your needs | Know when a mutable buffer is needed and the limits of per-call synchronization. |
| 8 | Fundamentals and study sequence for Java Core String (this lesson) | Plan practice, test edge cases, and complete the mini project. |

**Signs you need to revisit an earlier lesson:** not yet distinguishing `null` from an empty string; confusing `==` with content comparison; thinking `StringBuilder` is a `String`; unable to explain why an emoji has `length() == 2`; or not yet separating byte encoding from string operations. Each case has a dedicated core lesson above.

Before starting a new stage, run at least one `main()` program yourself and test an edge value (such as `null`, an empty string, an emoji, or a trailing delimiter). Record both your predicted result and the actual result to catch false assumptions.

## 3. Recommended Study Sequence: From Foundations to Applications

There is no need to learn every API at once. Each stage should end with a runnable artifact and a self-written set of edge cases.

| Stage | Core concepts | Practice task to pass the stage |
| --- | --- | --- |
| 0. Java basics review | Primitive/reference, `char`, array, `null`, loops, methods, exceptions | Explain why `String` is an object despite having literal syntax |
| 1. Creation and comparison | Literals, `new`, immutable, `equals()`, `==`, pool | Write a program distinguishing same value vs. same reference; test `null` |
| 2. Basic operations | `length()`, `substring()`, searching, `strip()`, replacing | Normalize titles, extract text before/after a delimiter |
| 3. Splitting and building | `split()`, `join()`, basic regex, `StringBuilder` | Process a comma-separated tag list, preserving empty fields when needed |
| 4. Unicode and locale | UTF-16, code points, charsets, normalization, appropriate case folding | Measure lengths of strings with Vietnamese and emojis; test UTF-8 round-trip |
| 5. Application and testing | Input validation, null/blank requirements, edge cases, performance | Build a text-sanitization utility suite with multi-case tests |
| 6. Deep dive as needed | `Pattern`/`Matcher`, `Collator`, `CharsetDecoder`, optimizing with measurements | Solve a practical problem with clear rules and justify API choices |

**How to study each stage:** read the concept → write a 10–30 line example yourself → predict the output → run and explain discrepancies → revise for edge cases → summarize when to use or avoid that API. Only move to the next stage when you can explain the output, not merely when the program runs.

### Suggested exercises by difficulty

**Basic:**

1. Write `isBlankOrNull(String s)` returning `true` when `s == null` or `s.isBlank()`. Test `null`, `""`, `" "`, and `" Java "`.
2. Given `"  java core  "`, produce `"JAVA CORE"` by stripping leading/trailing spaces and converting to uppercase; prove that the original string stays intact.
3. Write a method checking whether a filename ends with `".java"` (case-sensitive), and decide explicitly how to handle `null`.

**Intermediate:**

4. Split `"a, b,,c,"` into fields; preserve the trailing empty field; strip whitespace around each field without losing empty positions.
5. Given a sentence, count occurrences of a word or substring according to **explicitly defined** rules on case sensitivity and word boundaries; test the empty search string case.
6. Generate a simple slug for a title using rules you define yourself: `strip()`, lowercase, replace whitespace runs with `-`; note that slugs for accented Vietnamese require explicit rules rather than assuming accents should always be stripped.

**Advanced:**

7. Count UTF-16 code units, code points, and UTF-8 bytes of `"A😀é"`; explain why the three numbers can differ.
8. Compare `"é"` with `"e\u0301"` before and after `Normalizer.Form.NFC`; explain the difference between *looking identical* and *being equal via equals*.
9. Build a username validation method: state clear requirements for `null`/blank, whether accents are allowed, how Unicode is handled, and which unit measures length. Write at least 6 test cases.

**End-of-topic mini project:** build a small `TextUtils` library (methods `normalizeSpaces`, `safeEquals`, `splitPreservingEmpty`, `utf8ByteLength`). Write JUnit tests if you have learned testing; if not, write a `main()` printing expected/actual. You must state the contract for every method (`null` input, empty string, invalid data, Unicode rules) and test strictly against that contract.

## 4. How to Read Documentation and Self-Verify

- Consult the **Javadoc of `java.lang.String` for your exact JDK version**: signatures, return values, exceptions, `null` behavior, and release versions.
- Use `jshell` for quick experiments, or create a `.java` file with `public static void main(String[] args)` to observe consistent behavior.
- Run `javac -version` and `java -version` to verify compiler/runtime versions; prefer compatible versions. If working with Java 17, avoid using APIs introduced in newer releases.
- When examples depend on locale, charset, or regex, state input assumptions explicitly; avoid drawing conclusions from a simple ASCII string alone.
- When encountering a bug, build a **minimum reproducible example**: shortest input string, expected output, and actual output. Check length, indices, regex, escape characters, and `null` before blaming the JVM.

Standard references to consult: [Java SE 17: String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html), [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html), [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html), and [Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).

## 5. Topic Completion Criteria

Be able to answer the following questions **without running them first**:

1. Why is `"Java" == new String("Java")` `false`, whereas `equals()` is `true`?
2. Why does `text.replace("a", "b");` not change the `text` variable?
3. Which positions does `substring(1, 3)` extract, and what exception occurs if indices are out of bounds?
4. What are the differences among `null`, `""`, `"   "`, `isEmpty()`, and `isBlank()`?
5. Why does `"😀".length()` equal `2`? When do you need `codePoints()`?
6. When should you use `replace()`, when should you use `replaceAll()`, and why do regex patterns need escaping?
7. Why should you pass `StandardCharsets.UTF_8` when converting between `String` and `byte[]`?
8. In what situations is `StringBuilder` more appropriate than `+` concatenation?
9. Why do Unicode normalization or locale-aware comparison require business rules?
10. Which edge cases will you test before using a text-processing method in a real program?

**Genuine completion** means you have written the mini project methods, can explain their output, handle `null`/empty/Unicode properly, and test inputs beyond the sample cases. Only then should you move on to advanced regex, text file I/O, localized formatting, and high-volume data processing APIs.