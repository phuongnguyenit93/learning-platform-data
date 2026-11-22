# Detecting Duplicate, Missing, Extra Keys, and Unintended Whitespace in Java Resource Files

## 1. Why audit resource file quality?

Java applications commonly store localized text in `.properties` files so `ResourceBundle` can select them by language and region, such as `messages.properties`, `messages_vi.properties`, and `messages_en.properties`. As the number of languages and keys grows, four issues easily creep in:

1. **Duplicate keys:** the same key is declared two or more times in one file. When loaded with `Properties.load`, later occurrences overwrite earlier ones, usually with no error by default.
2. **Missing keys:** a translation lacks an expected key from the canonical key catalog. When run through `ResourceBundle`, the application can inherit the value from a parent bundle, making the omission hard to notice.
3. **Extra keys:** a translation contains keys no longer in the canonical catalog or simply misspelled. Keys can linger indefinitely and never be used.
4. **Unintended whitespace:** spaces or tabs at the start/end of **actual values**, in keys, or at the end of physical lines. These can skew UI layout, break equality checks, and mask line-continuation bugs.

A file loading without exceptions **does not mean the resource is correct**. Auditing must rely on both **values after parser processing** and **raw source text**. Neither can completely replace the other.

A common mistaken example:

~~~properties
button.save=Lưu
button.save=Lưu ngay
~~~

Reading with `Properties.load(...)` produces the final result `button.save = Lưu ngay`. You need a pre-build/pre-deploy check whenever silent overrides are unacceptable.

## 2. Understanding .properties syntax before writing a linter

A `.properties` file is not just `key=value` lines. Java supports:

- Key–value separators: `=`, `:`, or unescaped whitespace.
- Blank lines, and comment lines starting with `#` or `!` after leading whitespace.
- Escapes such as `\ ` (space), `\=`, ``, `\n`, `\t`, and `\uXXXX`.
- Line continuations when a logical line ends with an odd number of consecutive `` characters.
- Different ways of writing keys that resolve to the **same logical key** after unescaping.

Example:

~~~properties
button.save=Save
button\.save=Save again
status : ready
welcome.message = Hello
~~~

Do the first two lines create **two distinct keys** because `button\.save` does not need a dot escape and still becomes `button.save`? **No:** under `Properties` semantics, escaping `.` is not a special escape sequence, yet the `` is stripped, so the result is still the key `button.save`; therefore, it must be treated as a *duplicate key* after parsing. This case highlights how comparing raw text to the left of `=` can miss duplicates.

Safe authoring for that example relies on understanding parser effects: `status : ready` yields `status = ready`, and `welcome.message = Hello` yields the value `Hello` (whitespace right after the delimiter is discarded by default).

Several easily confused whitespace rules:

| Source form | Result when read by `Properties` | QA conclusion |
| --- | --- | --- |
| `label = Hello` | `Hello` | Spaces around the delimiter are valid syntax, not automatically an error |
| `label=Hello   ` | `Hello   ` | Trailing spaces in the **value** may be a bug |
| `label=Hello\u0020` | `Hello ` | Unicode escape creates a real trailing space in the value |
| `label=  Hello` | `Hello` | Whitespace after delimiter is ignored; a value linter will not see it |
| `message=Hello\ World` | `Hello World` | Space inside content is intentional |
| `key\ name=value` | Logical key `key name` | Keys with spaces are syntactically valid, though usually discouraged by naming conventions |
| `welcome.message = Hello` | Key `welcome.message`, value `Hello` | Normal whitespace around the delimiter |

Spaces between words are necessary in translations: **never strip all whitespace blindly**. Whitespace detection should flag **suspicious locations** for translators to decide which cases are intentional.

**Encoding note:** `Properties.load(InputStream)` reads bytes as ISO-8859-1; to inspect UTF-8 resources, use `Properties.load(Reader)` with `Files.newBufferedReader(path, StandardCharsets.UTF_8)`. With `ResourceBundle` on Java 17, `PropertyResourceBundle` tries UTF-8 by default (with an ISO-8859-1 fallback for invalid UTF-8 data). Mixing reading modes can cause audits to produce different results. Lock down the project's encoding and use it consistently.

## 3. Duplicate keys: detect them within a single file

`java.util.Properties` is a key → value `Map`; when `load` encounters an existing key, the later value replaces the earlier one. Thus:

~~~java
Properties props = new Properties();
props.load(reader);
System.out.println(props.getProperty("button.save"));
~~~

The snippet above sees only **the final value**; `Properties` no longer retains the list of occurrences. To detect duplicates after syntax normalization, track each key insertion during parsing or use a dedicated checker.

In Java 17, `Properties.load` inserts parsed entries via `put`. We can subclass it to record repeated keys:

~~~java
static final class CheckedProperties extends Properties {
    final Set<String> duplicates = new TreeSet<>();

    @Override
    public synchronized Object put(Object key, Object value) {
        if (containsKey(key)) {
            duplicates.add((String) key);
        }
        return super.put(key, value);
    }
}
~~~

This is **part of the complete program in section 6**, not a standalone compilable file. It catches declarations that differ in separators or escaping whenever the parser resolves them to the same **logical key**. For example:

~~~properties
title=Title
title:Another title
title = Third title
~~~

The resulting `Properties` holds one `title` key, while `duplicates` records `title`. This example checker records only duplicate key names, **not line numbers**; if exact line numbers are needed, you need a parser/lexer that tracks physical and logical line metadata according to `.properties` rules.

Do not check for duplicates by counting lines containing `=`: that fails for `:` and whitespace separators, comments, escapes, and line continuations.

## 4. Missing keys: compare against the canonical key set, not just runtime fallback

Suppose `messages.properties` is the **canonical key catalog**:

~~~properties
title=Orders
button.save=Save
button.cancel=Cancel
status.new=New
greeting=Hello
~~~

`messages_vi.properties` contains only:

~~~properties
title=Đơn hàng
button.save=Lưu
button.cancel=Hủy
~~~

The set of keys missing in the Vietnamese translation is:

~~~text
[greeting, status.new]
~~~

Computing via set difference:

~~~java
Set<String> missing = new TreeSet<>(base.stringPropertyNames());
missing.removeAll(translated.stringPropertyNames());
~~~

This is an **illustrative snippet**, requiring `base` and `translated` as two separately loaded `Properties` instances, along with `java.util.Set` and `java.util.TreeSet` imports.

An important point: `ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))` can return a child bundle linked to its parent, and `bundle.containsKey("greeting")` still returns `true` due to inheritance. Therefore, **never use a child bundle's `ResourceBundle.keySet()` to claim the direct translation file has all keys**. Inspect individual source files or per-bundle metadata separately.

Is a missing key always a bug? That depends on the localization contract:

- If every language must translate **100% of required keys**, missing keys are a build/CI error.
- If the system allows regional overrides (`messages_vi_VN.properties`) to specify only differences from general Vietnamese (`messages_vi.properties`), missing keys are **intentional inheritance**.
- If certain messages belong only to optional features, the canonical catalog should explicitly mark optional/feature-specific groups instead of judging with a naive set difference.

You must specify **which file is the baseline** and **which files are allowed to inherit** before concluding a translation is "incomplete."

## 5. Extra keys and unintended whitespace

### 5.1. Detecting extra keys

Extra key set:

~~~java
Set<String> extra = new TreeSet<>(translated.stringPropertyNames());
extra.removeAll(base.stringPropertyNames());
~~~

For example, if the Vietnamese file also contains `obsolete.key` while the base file does not, the check returns:

~~~text
[obsolete.key]
~~~

These are **candidates for review**, not automatically items to delete: a specialized file might be designed to hold region- or feature-specific keys. Conversely, a misspelled key (`button.svae`) typically produces both **one missing key** (`button.save`) and **one extra key** (`button.svae`), which is a strong signal to fix.

### 5.2. Whitespace in values after parsing

After `Properties.load(Reader)`, check leading/trailing whitespace in values with `String.strip()`:

~~~java
String value = props.getProperty(key);
if (!value.equals(value.strip())) {
    System.out.println("Suspicious outer whitespace: " + key);
}
~~~

This is an **illustrative snippet**; `props` is a `Properties` variable and `key` is a `String` from the key set. Do not automatically `strip()` when writing resources back or auto-fixing translations: some messages intentionally include trailing spaces or newlines, and auto-stripping can alter presentation meaning. `strip()` relies on `Character.isWhitespace`; it does not catch every Unicode space character such as no-break space (NBSP). If your project needs to detect `U+00A0`, non-breaking spaces, or invisible characters, add explicit Unicode checks.

### 5.3. Whitespace in raw physical lines

The `.properties` parser skips whitespace after delimiters, processes line continuations, and interprets escapes. Thus checking parsed values alone **cannot see** every style issue in the source file.

A simple, low-controversy check is flagging **trailing spaces or tabs at the end of physical lines** in the source file. Lines ending with spaces or tabs can mask a line-continuation `` or introduce unintended whitespace in values. You can iterate over `Files.readAllLines` and check the last character of each line.

**Do not automatically strip trailing whitespace from files before checking continuation syntax:** if a line ends with `` followed by a space, removing that space can turn two independent logical lines into one continued line, changing keys and values. Report it and fix it under test coverage.

Regarding **leading whitespace on lines**, properties syntax allows indentation and skips whitespace before keys. So never flag every indented line as an error; instead, agree on a style convention and use a continuation-aware linter.

## 6. Complete Java 17 program: auditing a pair of files

Place the following three files in the same directory. The sample data intentionally includes: one duplicate key in the translation file; two missing keys; one extra key; and one trailing space in a value created via `\u0020`. Escaping is chosen instead of a literal trailing space so readers can clearly see the sample data.

**File `messages.properties`**:

~~~properties
title=Orders
button.save=Save
button.cancel=Cancel
status.new=New
greeting=Hello
~~~

**File `messages_vi.properties`**:

~~~properties
title=Đơn hàng
button.save=Lưu
button.save=Lưu ngay
button.cancel=Hủy\u0020
obsolete.key=Cũ
~~~

**File `ResourceFileAudit.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import java.util.TreeSet;

public class ResourceFileAudit {
    static final class CheckedProperties extends Properties {
        final Set<String> duplicates = new TreeSet<>();

        @Override
        public synchronized Object put(Object key, Object value) {
            if (containsKey(key)) {
                duplicates.add((String) key);
            }
            return super.put(key, value);
        }
    }

    static CheckedProperties read(Path path) throws IOException {
        CheckedProperties result = new CheckedProperties();
        try (var reader = Files.newBufferedReader(
                path, StandardCharsets.UTF_8)) {
            result.load(reader);
        }
        return result;
    }

    static Set<String> difference(Set<String> left, Set<String> right) {
        Set<String> result = new TreeSet<>(left);
        result.removeAll(right);
        return result;
    }

    static Set<String> outerWhitespaceKeys(CheckedProperties props) {
        Set<String> result = new TreeSet<>();
        for (String key : props.stringPropertyNames()) {
            if (!key.equals(key.strip())) {
                result.add(key);
            }
        }
        return result;
    }

    static Set<String> outerWhitespaceValues(CheckedProperties props) {
        Set<String> result = new TreeSet<>();
        for (String key : props.stringPropertyNames()) {
            String value = props.getProperty(key);
            if (!value.equals(value.strip())) {
                result.add(key);
            }
        }
        return result;
    }

    static List<Integer> physicalTrailingWhitespace(Path path)
            throws IOException {
        List<String> lines =
                Files.readAllLines(path, StandardCharsets.UTF_8);
        List<Integer> result = new ArrayList<>();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line.endsWith(" ") || line.endsWith("\t")) {
                result.add(i + 1); // Line numbers in the file are 1-based.
            }
        }
        return result;
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java ResourceFileAudit base.properties translation.properties");
            System.exit(2);
        }

        Path basePath = Path.of(args[0]);
        Path translationPath = Path.of(args[1]);
        CheckedProperties base = read(basePath);
        CheckedProperties translated = read(translationPath);

        Set<String> baseKeys = base.stringPropertyNames();
        Set<String> translatedKeys = translated.stringPropertyNames();

        System.out.println("base duplicates: " + base.duplicates);
        System.out.println("translation duplicates: "
                + translated.duplicates);
        System.out.println("missing in translation: "
                + difference(baseKeys, translatedKeys));
        System.out.println("extra in translation: "
                + difference(translatedKeys, baseKeys));
        System.out.println("translation outer whitespace keys: "
                + outerWhitespaceKeys(translated));
        System.out.println("translation outer whitespace values: "
                + outerWhitespaceValues(translated));
        System.out.println("translation physical trailing lines: "
                + physicalTrailingWhitespace(translationPath));
    }
}
~~~

Run from the directory containing all three files with **JDK 17+**:

~~~bash
javac -encoding UTF-8 ResourceFileAudit.java
java ResourceFileAudit messages.properties messages_vi.properties
~~~

**Expected stdout** (sets use `TreeSet`, so order is deterministic):

~~~text
base duplicates: []
translation duplicates: [button.save]
missing in translation: [greeting, status.new]
extra in translation: [obsolete.key]
translation outer whitespace keys: []
translation outer whitespace values: [button.cancel]
translation physical trailing lines: []
~~~

Explanation: the duplicate `button.save` lines are collapsed by the parser into one key, yet `CheckedProperties.put` records the repeated declaration; `greeting` and `status.new` are missing; `obsolete.key` is absent from the base catalog; the `\u0020` escape creates a trailing space in `button.cancel`'s value; however, in the source file that line ends with the character `0`, so **there is no physical trailing space on the line**.

This program is a **minimal runnable checker**, not a parser reporting line numbers for each duplicate key. Nor does it decide by policy whether missing/extra keys are build errors: that policy must be configured according to each application's localization goals.

## 7. Practical auditing in a multi-locale project

When you have `messages.properties`, `messages_vi.properties`, `messages_vi_VN.properties`, `messages_en.properties`, and so on, you should not compare every file against the root with the exact same rule:

| File kind | Suggested policy | Why |
| --- | --- | --- |
| Root `messages.properties` | Defines canonical key catalog, no duplicates, no whitespace errors | Serves as the comparison baseline |
| Language bundle `messages_vi.properties` | Require complete key coverage if the product commits to full translation | Prevents missing translations from being masked by fallback |
| Regional bundle `messages_vi_VN.properties` | Only overriding keys required; full match with root not mandatory | Fits child–parent inheritance model |
| Feature-specific bundle | Compare against that feature's dedicated key catalog | Avoids flagging feature keys as extra |
| Bundle generated by a translation platform | Run QA after export, before packaging | Prevents escape/Unicode errors from shipping |

For a real project, define a configuration such as:

~~~yaml
base: messages.properties
complete:
  - messages_vi.properties
  - messages_en.properties
overrides:
  - messages_vi_VN.properties
required:
  - title
  - button.save
  - button.cancel
~~~

This is **an example QA policy in YAML format**, not a configuration automatically understood by Java or `ResourceBundle`. Build/CI tooling must be programmed to enforce this policy. For **override bundles**, check only unknown keys and duplicates; missing keys can be normal.

You should also check placeholders (`{0}`, `{1}`, ...), `MessageFormat` quotes, empty translations, encoding, and unusually long strings. Those checks differ from the four defect categories of this lesson, yet are commonly combined in pre-release resource validation.

## 8. Edge cases to watch out for

### Keys altered by escapes or Unicode characters

Two keys that look different in an editor can resolve to the same **logical key** after `Properties.load`, such as `title` and `ti\u0074le`. Conversely, visually identical Unicode characters can have different code points (combining vs. precomposed forms). `Properties` does not automatically apply Unicode NFC normalization for translators, so if your naming standard requires ASCII-only or NFC-normalized keys, add an explicit policy check.

### Continuation lines

Example:

~~~properties
long.message=Hello \
    world
~~~

Two physical lines form one logical value, and leading whitespace on the continued line is discarded by the parser. A naive line-by-line linter might mistake this for two keys. Our example tool uses `Properties.load(Reader)` so it compares **logical keys/values** per Java syntax; the physical-line scan only flags trailing spaces/tabs and does not guess keys.

### Duplicate keys after parsing

Example:

~~~properties
button.save=Save
button.save:Save again
~~~

`Properties` keeps `Save again`. To block duplicates reliably, run checks in the pipeline against **source files**; inspecting only `ResourceBundle` after loading leaves no record of how many times a key was declared.

### Legitimate vs. unintended whitespace

A message like `indent=\\u0020\\u0020Name` intentionally starts with two spaces; a `strip()` linter will warn on it. Do not treat every warning as a bug. In particular, NBSP, thin spaces, tabs, or newlines may need to be preserved. Maintain per-key allowlists, translator notes, and UI tests to confirm intent.

### ResourceBundle caching and parent fallback

`ResourceBundle.getBundle` caches bundles and inherits parent resources. If files on disk change while the JVM is running, re-reading a bundle may not immediately reflect new content. Source-file QA should run during build/CI or in a clean test environment rather than inferring key sets directly from cached bundle objects.

### Same key across two languages is not a "duplicate key"

Having `button.save` in both `messages.properties` and `messages_vi.properties` is **valid and necessary**: the child bundle overrides the parent. The **duplicate** to detect is **the same key appearing multiple times within a single file/bundle**, not a key appearing across multiple locales.

## 9. Automated checking workflow and testing

A straightforward workflow to integrate into CI:

1. **Define the canonical catalog:** root or application manifest, with explicit rules for optional and override keys.
2. **Read each file individually with a consistent charset:** prefer UTF-8, catching invalid files and malformed escapes.
3. **Catch duplicate keys before information is lost:** hook into parsing, such as `CheckedProperties.put`.
4. **Compute missing/extra keys per policy:** full translation files against root; regional overrides under override rules.
5. **Scan whitespace:** distinguish semantic values, logical keys, physical source lines, and invisible Unicode characters.
6. **Produce actionable reports:** file, issue type, key, and line number if the parser tracks metadata; for warnings, state the criterion and reason.
7. **Fail the build on critical errors:** duplicates, missing required keys, disallowed extra keys; whitespace warnings can require translator confirmation.
8. **Run runtime checks:** verify resource bundles load cleanly, override/fallback works as intended, and the UI does not mix languages due to missing keys.

Test cases you should create yourself: duplicate keys using `=` and `:`, keys with escapes, comments containing `=`, keys on continuation lines, intentional empty values, UTF-8 files, CRLF files, root-plus-regional-override setups, trailing spaces in values, trailing tabs on lines, no-break spaces, and files with non-standard locale names.

To avoid false positives, test against **configured rules**: regional files are allowed to omit keys due to inheritance, whereas full-language files are not; certain messages are allowed intentional whitespace.

## 10. Common mistakes and how to handle them

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Calling `Properties.load` and checking only the final key count | Duplicate keys were overwritten and are invisible in the final count | Track declaration count inside the parser |
| Using `split("=")` to count keys | Misses `:`, escapes, continuations, and comments | Use a Java-compatible properties parser |
| Using `ResourceBundle.keySet()` to measure direct key completeness | Keys inherited from parents still appear | Compare individual source files according to bundle policy |
| Treating every missing key as an error | Regional bundles intentionally override only a subset | Classify complete vs. override bundles |
| Automatically deleting every extra key | Some keys are locale- or feature-specific | Verify against the manifest and feature scope |
| Calling `trim()` and overwriting all translations | Can alter valid content; `trim` is incomplete for Unicode | Warn, review, and fix with verification |
| Treating whitespace around delimiters as part of the value | The parser strips syntactic delimiter whitespace | Check logical values and source lines separately |
| Reading UTF-8 with `load(InputStream)` | Accented text can be decoded wrongly | Use a UTF-8 `Reader` or the appropriate `ResourceBundle` mechanism |
| Forgetting that resource files are cached | Tests read stale data | Run QA on built files and control cache/reload |
| Seeing `button.save` in two locales and reporting a duplicate | That is normal overriding | Flag duplicates **only within a single resource** |

## 11. Practice exercises

Starting from the two sample files in section 6, try step by step:

1. Remove one of the two `button.save` lines in `messages_vi.properties`: the duplicate list must become empty, while missing/extra remain unchanged.
2. Add `greeting=Xin chào` to the translation file: missing leaves only `status.new`.
3. Remove `obsolete.key`: extra must become empty.
4. Change `button.cancel=Hủy\u0020` to `button.cancel=Hủy`: the outer-whitespace warning on the value disappears.
5. Add a space at the **end of a physical line** (not an escape sequence): `physicalTrailingWhitespace` will list that line number.
6. Use `button.save:Lưu ngay` instead of `=` on the duplicate line: the duplicate is still detected because both separator styles resolve to the same logical key.
7. Treat the translation file as a regional locale override that allows inheriting all undeclared keys: change the audit policy without changing the parser.
8. Put `button.save` and `button\.save` in the same file: observe whether the parser resolves both keys to the same name; this is why you should not rely on naive regex to prove uniqueness.

Each exercise separates **data defects**, **parser behavior**, and **translation policy**. Once you understand those boundaries, you will know when to fail the build, when to warn, and when a missing key is intentional inheritance.

## 12. Summary

For Java resource files, inspect **source syntax before loading**, **logical keys/values after loading**, and then **compare key sets according to each bundle kind's rules**. Duplicates are masked by overwriting; missing keys can be masked by parent fallback; extra keys may be typos or valid specialized keys; whitespace may be discarded by the parser or become part of the actual value.

A controlled QA step run before build/deploy ensures resource bundles not only load without exceptions, but also contain trustworthy content without breaking intentional whitespace or overrides.

**References:**

- Java SE 17 `Properties`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html
- Java SE 17 `ResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17 `PropertyResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html
