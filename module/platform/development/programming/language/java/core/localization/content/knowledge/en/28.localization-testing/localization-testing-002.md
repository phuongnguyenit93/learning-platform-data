# Testing Resource Keys and Pattern Arguments Across Translations

A Java application may run fine with an English `ResourceBundle` yet break when users switch to Vietnamese, French, or Japanese. A mistyped key, a placeholder `{0}` changed to `{1}`, or a message using `{0,date}` instead of `{0,number}` can all cause the UI to display wrong output — sometimes without throwing an exception. Therefore, **testing localization content is part of the contract between code and translators**.

This lesson focuses on three goals: **key sets across translations**, **argument index/type metadata in `MessageFormat`**, and **verification on the actual runtime path**. The Java 17+ examples use `.properties`, `PropertyResourceBundle`, `MessageFormat`, and a standalone test program with no external libraries.

Remember from the start: **`ResourceBundle` has a fallback mechanism**, so a successful `getString` call does not prove a locale file is completely translated. At the same time, **`MessageFormat` uses its own grammar for single quotes, braces, and nested `choice`**, so a regex searching for `{number}` is not a general pattern parser.

## 1. A Bundle Set and the Contract to Preserve

Suppose a project has two files:

**`Messages_en.properties`**

~~~properties
welcome=Hello {0}!
items={0} has {1,number,integer} items.
created=Created on {0,date,medium}.
~~~

**`Messages_vi.properties`**

~~~properties
welcome=Xin chào {0}!
items={0} có {1,number,integer} mặt hàng.
created=Được tạo ngày {0,date,medium}.
~~~

The files share the **same three keys**, though wording and word order may differ. Each message's contract includes:

| Key | Required arguments | Type/meaning |
| --- | --- | --- |
| `welcome` | `{0}` | Person's name |
| `items` | `{0}` and `{1}` | Person's name and item count |
| `created` | `{0}` | Creation date, formatted as a date |

Two translations do not need placeholders in the same sentence position. For instance, a translated sentence can place `{1}` before `{0}` for natural grammar, as long as it preserves the same **argument contract**.

Reliable testing must check **key completeness**, **arguments**, and **actual formatting**, rather than just eyeballing the files.

## 2. Why Fallback Easily Hides a Missing Key

If a project has:

~~~text
Messages.properties
Messages_en.properties
Messages_vi.properties
~~~

and `Messages_vi.properties` is missing `created` while `Messages.properties` still has that key, `ResourceBundle.getBundle("Messages", locale)` can return the value from the parent/root bundle.

The program:

~~~java
ResourceBundle vi = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));

String text = vi.getString("created");
~~~

may still run, yet `text` is the untranslated default message.

**`ResourceBundle.keySet()` includes keys reachable from parent bundles**, not only keys declared in the current file. Thus `en.keySet().equals(vi.keySet())` on fallback-resolved bundles **does not prove** the source files have the same key set.

Solution: for **source parity** tests, load **each translation file independently**, without calling `getBundle` with fallback. Then add runtime tests to verify the actual resource lookup path.

## 3. Testing Raw Keys with `PropertyResourceBundle(Reader)`

You can read a UTF-8 file directly:

~~~java
try (Reader reader = Files.newBufferedReader(
        Path.of("Messages_vi.properties"),
        StandardCharsets.UTF_8)) {

    ResourceBundle bundle = new PropertyResourceBundle(reader);
    Set<String> keys = bundle.keySet();
}
~~~

This is a **snippet** inside a method declaring `throws IOException`, requiring imports for `Reader`, `Files`, `Path`, `StandardCharsets`, `ResourceBundle`, `PropertyResourceBundle`, and `Set`.

An object constructed directly from a file is not assigned a parent locale by the `ResourceBundle.getBundle` algorithm, so `keySet` reflects that file's contents.

Encoding note: `Properties.load(InputStream)` follows traditional ISO-8859-1 rules, whereas `Reader` lets you select UTF-8 explicitly. Use the read path matching your build and actual file contents.

## 4. Test Policy: Exact Parity vs. Allowed Exceptions

There are two options:

**Exact parity:** every released locale must have the exact same key set as the canonical bundle.

~~~text
keys(en) = keys(vi) = keys(fr)
~~~

**Controlled partial coverage:** an experimental locale may contain only a subset.

~~~text
requiredKeys ⊆ keys(locale)
exceptions(locale) have an owner and explicit reason
~~~

For regional locales like `fr_CA`, a project may intentionally store only **override** keys on top of `fr`; applying exact parity to the `fr_CA` file alone would be the wrong policy. Tests must understand **translation layers** and approved fallback policies.

Whichever policy you choose, report clearly:
- **Missing key**: present in canonical, missing in locale.
- **Extra key**: present in locale, missing in canonical.
- **Empty value**: key exists, but its value is blank or fails policy.
- **Duplicate key**: the same key is declared multiple times.
- **Stale key**: no code references the key anymore.

The parsed key set **does not detect duplicate declarations** if the parser simply keeps the last value. To forbid duplicates, you need a source linter that understands line continuations, escapes, and `.properties` structure.

## 5. `MessageFormat` Placeholders

`java.text.MessageFormat` uses **indexed arguments**:

~~~text
{0}
{1,number,integer}
{2,date,medium}
{3,time,short}
{0,choice,0#none|1#one|1<many}
~~~

Runnable example **`MessageArgumentsDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageArgumentsDemo {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "Hello {0}, you have {1,number,integer} files.",
                Locale.US);

        System.out.println(format.format(
                new Object[]{"Lan", 5}));
    }
}
~~~

~~~bash
javac MessageArgumentsDemo.java
java MessageArgumentsDemo
~~~

Output:

~~~text
Hello Lan, you have 5 files.
~~~

`{0}` takes the first argument and `{1}` takes the second. **A translation may reorder their positions**, but must not reassign `{0}` to mean the count if code passes the name there.

## 6. Missing Arguments Do Not Necessarily Throw Errors

Example:

~~~java
MessageFormat f = new MessageFormat(
        "Hi {0} {1,number}", Locale.US);

System.out.println(
        f.format(new Object[]{"Lan"}));
~~~

Output:

~~~text
Hi Lan {1}
~~~

Java can leave an **unprovided placeholder** literally as `{1}` without necessarily throwing an exception. If a test only calls `format` without inspecting the output or index set, bugs can slip through to the UI.

Therefore, **cross-check used indexes against the method signature/fixture**. A high argument index like `{7}` may be accidentally introduced by a translator even though the app passes only two arguments.

## 7. Do Not Compare Order or Occurrence Count

Two versions:

~~~text
English: {0} sent {1,number} messages.
Other:   {1,number} messages were sent by {0}.
~~~

have the same **index set `{0,1}`**, so they are compatible in terms of argument positions. Another translation might repeat `{0}` twice for grammar. Do not treat repeated indexes as an error by default.

Instead, check:
1. The set of indexes used.
2. The data role at each index.
3. Formats compatible with the argument types.
4. Language-specific requirements such as plurals or gender.

Do not use raw string comparison between two locales to check compatibility.

## 8. Same Index, Wrong Formatter Type

Example:

~~~text
en: Created on {0,date,medium}.
vi: Được tạo ngày {0,number,integer}.
~~~

Both use the same index `0`, but different formatters. If `{0}` receives a `Date`, the Vietnamese version may fail when formatting it as a number; if it receives a `Number`, the English version may fail.

**Checking index parity is necessary, not sufficient.** Tests need **fixtures with the actual data types** and—when business rules require it—checks on `number`/`date`/`time`/`choice` for each key.

Runnable example **`FormatTypeDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class FormatTypeDemo {
    public static void main(String[] args) {
        MessageFormat number = new MessageFormat(
                "{0,number,integer}", Locale.US);

        System.out.println(number.format(new Object[]{5}));

        try {
            number.format(new Object[]{"five"});
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong argument type");
        }
    }
}
~~~

~~~bash
javac FormatTypeDemo.java
java FormatTypeDemo
~~~

Output:

~~~text
5
Wrong argument type
~~~

Do not use a dummy `String "X"` as the fixture for every parameter: that produces false errors on perfectly valid `number`/`date` patterns.

## 9. `MessageFormat` Quoting Is Easily Misread by Linters

In `MessageFormat`, the single quote `'` acts as a **literal quote**. Two quotes `''` produce a real apostrophe.

| Pattern | When argument `{0} = "ready"` |
| --- | --- |
| `It''s {0}` | `It's ready` |
| `'{0}'` | `{0}` (literal) |
| `''{0}''` | `'ready'` |

Runnable example **`QuotedArgumentsDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class QuotedArgumentsDemo {
    public static void main(String[] args) {
        Object[] data = {"ready"};

        System.out.println(
                new MessageFormat("It''s {0}", Locale.US)
                        .format(data));
        System.out.println(
                new MessageFormat("'{0}'", Locale.US)
                        .format(data));
        System.out.println(
                new MessageFormat("''{0}''", Locale.US)
                        .format(data));
    }
}
~~~

~~~bash
javac QuotedArgumentsDemo.java
java QuotedArgumentsDemo
~~~

Output:

~~~text
It's ready
{0}
'ready'
~~~

A regex scanning for every `{0}` may count literal placeholders inside `'{0}'`, causing false positives. Conversely, a wrong apostrophe can turn a placeholder meant to be formatted into a literal. Testing must respect the quoting syntax of the real parser.

## 10. Pattern Syntax and Parse-Time Errors

`new MessageFormat(pattern, locale)` parses the pattern syntax. Missing braces, invalid format types, or malformed indexes can throw `IllegalArgumentException`.

An appropriate test check:

~~~java
try {
    new MessageFormat(pattern, locale);
} catch (IllegalArgumentException ex) {
    throw new AssertionError(
            "Invalid pattern: locale=" + locale
                    + ", key=" + key, ex);
}
~~~

This is a **snippet inside a method** assuming `pattern`, `locale`, and `key` are already defined.

**Successful parsing does not prove everything is right**: the parser does not know the code contract requires `{0}` to be a name and `{1}` a number, whether the translation omitted an index, or whether the sentence reads accurately.

## 11. `getFormatsByArgumentIndex` Is Not a Complete Index Enumerator

`MessageFormat.getFormatsByArgumentIndex()` returns a `Format[]` array indexed by argument position, which can be inspected for format info. However, for the pattern:

~~~text
{2} and {0}
~~~

the array can have length **3** because the highest index is 2, even though `{1}` **does not appear**. `null` entries can correspond to arguments without a declared formatter, which is insufficient to distinguish all cases.

If nested `choice` exists, the outer formatter also does not reflect all arguments used inside sub-patterns re-parsed per branch.

Therefore, **do not use array length to claim which arguments are required**, and do not assume regex will handle all `MessageFormat` syntax.

## 12. A Java 17+ Test Suite for Properties Files and Flat Patterns

The following program is solid enough as a starting point for projects with **flat patterns**. It:
- loads `Messages_en.properties` and `Messages_vi.properties` independently as UTF-8;
- compares exact key sets;
- uses `MessageFormat` to validate syntax;
- scans top-level placeholders honoring apostrophe quoting rules;
- compares index sets;
- formats typed fixtures;
- fails with `AssertionError` if an issue is found.

**Scanner limitation:** it intentionally rejects `{...}` nested inside format elements, including nested `choice`. It is not a full `MessageFormat` grammar parser; projects using complex patterns must use a dedicated parser or controlled branch-level tests.

Create **`BundleContractTest.java`**:

~~~java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.MessageFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Map;
import java.util.PropertyResourceBundle;
import java.util.ResourceBundle;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public final class BundleContractTest {
    private static ResourceBundle read(String name)
            throws Exception {
        try (Reader r = Files.newBufferedReader(
                Path.of(name), StandardCharsets.UTF_8)) {
            return new PropertyResourceBundle(r);
        }
    }

    // Only for flat patterns, no nested choice.
    private static Set<Integer> indexes(String pattern) {
        new MessageFormat(pattern, Locale.ROOT);

        SortedSet<Integer> result = new TreeSet<>();
        boolean quoted = false;

        for (int i = 0; i < pattern.length();) {
            char ch = pattern.charAt(i);

            if (ch == '\'') {
                if (i + 1 < pattern.length()
                        && pattern.charAt(i + 1) == '\'') {
                    i += 2;
                } else {
                    quoted = !quoted;
                    i++;
                }
                continue;
            }

            if (!quoted && ch == '{') {
                int start = i + 1;
                int p = start;
                while (p < pattern.length()
                        && pattern.charAt(p) >= '0'
                        && pattern.charAt(p) <= '9') {
                    p++;
                }

                if (start == p || p == pattern.length()
                        || (pattern.charAt(p) != '}'
                            && pattern.charAt(p) != ',')) {
                    throw new IllegalArgumentException(
                            "Bad placeholder at " + i);
                }

                result.add(Integer.parseInt(
                        pattern.substring(start, p)));

                if (pattern.charAt(p) == '}') {
                    i = p + 1;
                    continue;
                }

                ++p;
                while (p < pattern.length()
                        && pattern.charAt(p) != '}') {
                    if (pattern.charAt(p) == '{') {
                        throw new IllegalArgumentException(
                                "Unsupported nested pattern");
                    }
                    p++;
                }

                if (p == pattern.length()) {
                    throw new IllegalArgumentException(
                            "Unclosed placeholder");
                }
                i = p + 1;
            } else {
                i++;
            }
        }

        return result;
    }

    public static void main(String[] args) throws Exception {
        ResourceBundle en = read("Messages_en.properties");
        ResourceBundle vi = read("Messages_vi.properties");

        SortedSet<String> a = new TreeSet<>(en.keySet());
        SortedSet<String> b = new TreeSet<>(vi.keySet());

        if (!a.equals(b)) {
            SortedSet<String> missing = new TreeSet<>(a);
            missing.removeAll(b);
            SortedSet<String> extra = new TreeSet<>(b);
            extra.removeAll(a);
            throw new AssertionError(
                    "vi missing=" + missing + ", extra=" + extra);
        }

        Map<String, Object[]> fixture = Map.of(
                "welcome", new Object[]{"Lan"},
                "items", new Object[]{"Lan", 5},
                "created", new Object[]{new Date(0)}
        );

        for (String key : a) {
            String enPattern = en.getString(key);
            String viPattern = vi.getString(key);
            Set<Integer> enIndexes = indexes(enPattern);
            Set<Integer> viIndexes = indexes(viPattern);

            if (!enIndexes.equals(viIndexes)) {
                throw new AssertionError(
                        key + ": " + enIndexes
                            + " != " + viIndexes);
            }

            Object[] values = fixture.get(key);
            if (values == null) {
                throw new AssertionError(
                        "No fixture for " + key);
            }

            for (int index : enIndexes) {
                if (index >= values.length) {
                    throw new AssertionError(
                            key + ": missing argument " + index);
                }
            }

            new MessageFormat(enPattern, Locale.US)
                    .format(values);
            new MessageFormat(
                    viPattern, Locale.forLanguageTag("vi-VN"))
                    .format(values);
        }

        System.out.printf("PASS keys=%d patterns=%d%n",
                a.size(), 2 * a.size());
    }
}
~~~

In the directory containing the three files, run:

~~~bash
javac -encoding UTF-8 BundleContractTest.java
java BundleContractTest
~~~

With the two properties files from Section 1:

~~~text
PASS keys=3 patterns=6
~~~

**Explicit test scope:** the program checks syntax, indexes, and formatting sample fixtures; it **does not** validate all format types, nested syntax, or translation accuracy. If one version replaces `{0,date}` with `{0}`, both may format without throwing, so that still needs checks via date formatting rules.

## 13. Demonstrating Bugs Caught by the Test

Modify each case in `Messages_vi.properties`:

**Missing key:**

~~~properties
welcome=Xin chào {0}!
items={0} có {1,number,integer} mặt hàng.
~~~

The test reports `created` missing. Note this inspects the raw file, with no fallback.

**Wrong index:**

~~~properties
items={0} có {2,number,integer} mặt hàng.
~~~

The test may report:

~~~text
items: [0, 1] != [0, 2]
~~~

**Runtime type mismatch:**

~~~properties
items={0} có {1,date,medium} mặt hàng.
~~~

The indexes match, but the fixture passes `5` (`Number`) into a date formatter; `IllegalArgumentException` may be thrown.

**Construct unsupported by the scanner:**

~~~properties
items={1,choice,0#không có|1#có một|1<có {1} mục}
~~~

The scanner rejects nested braces. This is **fail-closed** behavior, not proof the translation is invalid: the project needs to validate patterns with a tool suited for `choice` syntax.

## 14. ChoiceFormat and Nested Patterns

`MessageFormat` supports:

~~~text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
~~~

A `ChoiceFormat` branch can be parsed further if it contains `MessageFormat` braces. Consequently, placeholders inside branches are **not necessarily** found by a single top-level scan.

Example **`ChoiceBranchesDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceBranchesDemo {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "{0,choice,0#no files|1#one file"
                        + "|1<{0,number,integer} files}",
                Locale.US);

        System.out.println(format.format(new Object[]{0}));
        System.out.println(format.format(new Object[]{1}));
        System.out.println(format.format(new Object[]{5}));
    }
}
~~~

~~~bash
javac ChoiceBranchesDemo.java
java ChoiceBranchesDemo
~~~

Output:

~~~text
no files
one file
5 files
~~~

To test choice patterns, supply data at **boundaries** (0, 1, 2, large numbers), check **every selectable branch**, and check nested arguments. A translation may use a different number of branches due to grammar; that is not necessarily an index error, though it needs semantic review.

For complex plurals in languages with multiple plural categories, `ChoiceFormat` does not natively represent all CLDR rules. You can use ICU MessageFormat/plural, but **ICU syntax differs from `java.text.MessageFormat`**; choose your parser and test against the product's actual format.

## 15. Simple Regexes Only Suit Simple Conventions

The regex:

~~~java
Pattern.compile("\\{(\\d+)\\}");
~~~

only matches untyped placeholders, easily missing `{1,number}`, `{2,date,medium}`, and `choice`.

A broader regex matching every `{digit` can still:
- falsely count literal placeholders `'{0}'`;
- fail to distinguish nested syntax;
- mishandle apostrophes;
- miss unbalanced braces or out-of-range indexes;
- have no knowledge of an argument's actual data type.

**Do not "fix" this by progressively complicating a regex and treating it as a full parser.** If the project standardizes on a pattern subset, a scanner can enforce that subset and reject everything else; for full syntax, use a proper parser or tested library.

## 16. Testing Type Contracts and Intentional Fixtures

For business messages, maintain a declarative registry:

~~~text
welcome  → {0: String name}
items    → {0: String name, 1: Number count}
created  → {0: Date createdAt}
price    → {0: Number amount, separate currency policy}
~~~

This is a contract description, not `MessageFormat` syntax.

Dynamic checks:
1. Pass `String` for names.
2. Pass `Integer`/`BigDecimal` when the formatter requires `number`.
3. Pass `java.util.Date` or an app-supported adapted type for standard `date/time`.
4. For `choice`, pass `Number` and run multiple boundary values.
5. Verify the args array length covers the **maximum index actually used**.
6. Check that output does not leak missing placeholders, keeping in mind that a valid literal `'{0}'` can also emit the string `{0}` — do not decide by a naive string search alone.

Do not reuse one fixed fixture array for every key if their parameter contracts differ.

## 17. Testing Translations per Locale Without Comparing String Literals

`MessageFormat` creates formatters using `Locale`. For instance, numbers use different separators between `Locale.US` and `Locale.GERMANY`; dates and months also differ in order.

Proper testing:
- Pass the **corresponding locale**.
- Verify the formatter runs with the right argument types.
- Check that critical business components are present.
- Use snapshots only when pinning JDK/CLDR/provider and accounting for Unicode whitespace differences.
- Do not require outputs across different locales to match string-for-string.

If a date/time formatter uses `Date` and the default time zone, snapshots can vary across machines. Pin the time zone in date/time tests or assert time-zone-independent properties when testing compatibility only.

## 18. Empty Values, Duplicate Keys, and Encoding

Identical key sets still do not guarantee quality:

- `welcome=` may be an invalid **empty value** for a screen even though the key exists.
- A key declared twice can be overwritten by a map parser; `keySet` does not report duplicates.
- `.properties` supports line continuation and `\uXXXX` escapes; a simple line-by-line linter must understand that syntax.
- Invalid UTF-8 data may be replaced silently if a decoder uses replacement mode.
- Values containing newlines or HTML markup require validation per display context.
- Strings differing in NFC/NFD are not a key-parity error, yet can affect search and comparison.

Separate **source syntax/encoding** checks from **`MessageFormat` syntax** checks: a file that reads cleanly does not guarantee valid patterns, and a valid pattern does not guarantee an accurate translation.

## 19. Beyond Parity: Checking Keys Used by Code

Some keys appear in every file yet are no longer used anywhere. Conversely, code may look up a key that does not exist.

You can create an enum key registry:

~~~java
enum MessageKey {
    WELCOME("welcome"),
    ITEMS("items"),
    CREATED("created");

    final String value;
    MessageKey(String value) {
        this.value = value;
    }
}
~~~

This is an **enum snippet**, with no `main`. A registry reduces typos, though it does not automatically make `ResourceBundle` type-safe.

If the project builds keys dynamically, such as `"status." + status.name()`, plain-text search tools may miss them. Test all value combinations or maintain a registry for dynamically constructed keys.

## 20. Named Modules and Integration Tests

Java 9+ supports named modules and JPMS resource packaging. Unit tests loading files directly do not prove that `.properties` files were copied properly into the JAR or that the production app can load them.

Include integration tests that:
- run on the module path like the deployment environment;
- test key locales;
- confirm `ResourceBundle.getBundle` locates the bundle;
- verify fallback/parent resolution matches policy;
- confirm keys return expected values at runtime.

The `ResourceBundle.getBundle(..., Control)` overloads are unsupported when called from a named module; do not rely on them by default to "disable fallback" in modular integration tests. To test source file parity, read raw files as shown above; to test runtime resolution, use the appropriate API/module/provider.

## 21. Required Test Matrix

| Case | How to test | Expectation |
| --- | --- | --- |
| Missing key | Remove `created` from `vi` | Reports missing |
| Extra key | Add `unknown` | Reports extra |
| Reordered indexes | `{1}` before `{0}` | Valid if roles are preserved |
| Missing index | Drop `{1}` | Detects mismatch |
| Unexpected index | Change `{1}` → `{2}` | Detects mismatch |
| Literal quote | `'{0}'` | Not counted as real arg |
| Apostrophe | `It''s {0}` | Renders apostrophe properly |
| Wrong number type | Pass `String` to number format | Fails/throws error |
| Nested choice | 0, 1, 2, 5 | Every branch works |
| Date/time | Appropriate fixture | Formats without error |
| Fallback | Key exists only in root | Reports missing locale coverage |
| Duplicate key | Two declarations of same key | Source linter warns |
| Encoding | Vietnamese UTF-8 | No mojibake |
| Module packaging | Runtime module path | Bundle loads successfully |
| Empty value | `key=` | Error/allowed per policy |

## 22. CI Pipeline and Failure Reporting

A sensible pipeline:

~~~text
Pull request modifies translations
    ↓
Read raw resources + validate UTF-8
    ↓
Check duplicate/empty/key naming
    ↓
Compare key sets per policy
    ↓
Parse MessageFormat
    ↓
Compare placeholder indexes/types
    ↓
Format fixtures and choice branches
    ↓
Integration test ResourceBundle at runtime
    ↓
Review translated text/UI when needed
~~~

For required locales, missing keys or mismatched indexes should **fail CI**. For preview locales, they can warn under a time-bounded exception. A clear report:

~~~text
locale=vi key=items
reason=ARGUMENT_INDEX_MISMATCH
expected=[0, 1]
actual=[0, 2]
~~~

This is far more actionable than an `IllegalArgumentException` with no context. Avoid logging sensitive fixture data or real user content.

## 23. Common Mistakes

1. **Testing only `getString`**: fallback can mask missing keys.
2. **Comparing `ResourceBundle.keySet` with a parent present**: inherited keys skew the comparison.
3. **Checking only placeholder count**: `{1}` and `{2}` differ in meaning even though the count is the same.
4. **Comparing placeholder order**: may wrongly reject a valid reordered translation.
5. **Skipping type checking**: matching indexes do not guarantee `number`/`date` formatting works.
6. **Using an all-purpose regex**: quotes, typed formats, and nested `choice` break it.
7. **Trusting the `MessageFormat` constructor to prove arguments match**: without real data, runtime formatting isn't verified.
8. **Not testing plural/choice boundaries**: a single sample value is insufficient.
9. **Comparing exact output strings across locales**: number and date conventions differ.
10. **Letting tests depend on nondeterministic default charset/locale**: results may vary across environments.
11. **Forgetting to test resources after build**: files exist in the source tree yet are missing from the JAR.
12. **Auto-"fixing" translations via regex**: can break grammar.
13. **Not declaring an exact/partial coverage policy**: causes false warnings or misses incomplete translations.
14. **Skipping semantic review of sentences**: technical parity does not guarantee linguistic quality.

## 24. Self-Check Exercises

**Question 1.** Why does `getString("created")` succeeding not prove `Messages_vi.properties` contains key `created`?

**Answer:** The value may have been retrieved from the parent/root bundle via fallback.

**Question 2.** The English version has `{0} {1}`, and the Vietnamese version has `{1} {0}`. Is that an error?

**Answer:** Not necessarily; appearance order can change as long as the argument roles remain the same.

**Question 3.** Both versions use `{0}`, yet one uses `number` and the other uses `date`. Is checking indexes enough?

**Answer:** No, you must check format types and run fixtures of the right data types.

**Question 4.** Does the pattern `'{0}'` actually require argument `0`?

**Answer:** No. In `MessageFormat`, single quotes turn that segment into a literal.

**Question 5.** Does `MessageFormat` always throw an exception when argument `{1}` is missing?

**Answer:** No; it may render `{1}` literally.

**Question 6.** Why does the scanner in the example reject nested `choice`?

**Answer:** Because it only implements a flat grammar; rejecting out-of-scope syntax is safer than reporting a false PASS.

**Question 7.** Can plural grammar correctness be proved by key/index parity?

**Answer:** No; you must test branches, language rules, and potentially use ICU/CLDR.

**Question 8.** When is exact parity inappropriate for a `fr_CA` file?

**Answer:** When the regional file intentionally contains only overrides and inherits from `fr`.

**Question 9.** Why are both unit tests and integration tests needed?

**Answer:** Unit tests verify source files and patterns, while integration tests verify `ResourceBundle` actually loads after build/module packaging.

**Question 10.** What should CI report when a placeholder is missing?

**Answer:** Locale, key, reason, and expected/actual sets, not just a generic stack trace.

## 25. Summary and Application Principles

1. Define **one canonical bundle** and a coverage policy per locale.
2. Inspect **raw locale entries** rather than relying on fallback to prove key completeness.
3. Compare **placeholder index sets**, without enforcing sentence order or repetition count.
4. Add **type/semantic contracts** for `number`, `date`, `time`, `choice`, and business arguments.
5. Use `MessageFormat` to check syntax and format fixtures; for nested patterns, use a dedicated parser or branch-specific tests.
6. Document linter limitations and **fail-closed** on unsupported syntax.
7. Test encoding, duplicate keys, empty values, locale fallback, build packaging, and JPMS.
8. Integrate into **CI**, while keeping **human language reviewers** for plurals, meaning, and UI layout.

**Key takeaway:** Localization testing is more than "having translation files." A reliable translation set must stay synchronized in **resource keys, pattern arguments, type formatting, and runtime behavior**. `ResourceBundle` fallback can hide missing content; `MessageFormat` can leave unformatted placeholders when arguments are missing. Only by combining static checks, typed fixtures, branch tests, and integration tests can a system catch discrepancies across translations early.

**Java SE 17 Documentation:** [ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html), [PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html), [MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html), [ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html).
