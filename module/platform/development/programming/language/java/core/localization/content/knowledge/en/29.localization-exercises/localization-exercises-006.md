# Sorting Vietnamese Names with Collator in Java

## 1. Practical Scenario and Objectives

A student, HR, or customer management application holds a list of names: **Nguyễn Văn An**, **Trần Thị Ánh**, **Phạm Bảo Ân**, **Đặng Thu Đào**, **Đỗ Gia Dũng**, **Võ Quốc Đức**. Users expect the list to be sorted sensibly in Vietnamese. If you use `String.compareTo()`, strings are compared by UTF-16 code units, **not by the language's alphabetic collation rules**. Accented letters, the letter `Đ`, base vowels, tone marks, upper/lower casing, and compound names can produce confusing ordering.

Core Java provides `java.text.Collator` to compare strings **according to a locale**, such as `vi-VN`. However, simply swapping `compareTo` for `Collator.compare` is not enough for a complete directory feature: you must first decide **whether to sort by given name or family name**, how to store family/middle/given name components, how to handle multiple records that collate as equivalent, and how to keep the results testable.

**This hands-on guide** walks through creating a `Collator`, writing a `Comparator` for structured data, running on Java 17+, interpreting the output, handling Unicode data pitfalls, and testing in production.

### What Will You Be Able to Do After This Lesson?

1. Create a `Collator` with `Locale.forLanguageTag("vi-VN")` and explain how it differs from `String.compareTo`.
2. Choose `Collator.PRIMARY`/`SECONDARY`/`TERTIARY`/`IDENTICAL` and `CANONICAL_DECOMPOSITION` to match your requirements.
3. Sort a list by **given name**, then family name, middle name, and ID — or switch the policy to sort **by family name**.
4. Write a standalone Java 17+ program with compilation commands and verifiable output.
5. Distinguish **Collator equivalence** from `String.equals` and person identity in a database.
6. Avoid dropping people or overwriting entries when using `TreeSet`/`TreeMap` with a comparator inconsistent with `equals`.
7. Recognize Unicode normalization issues (precomposed vs. decomposed), whitespace, compound names, comparison strengths, and source data edge cases.
8. Design a test suite covering all Vietnamese name categories and manage changes across JDK/CLDR upgrades.

## 2. "Sorting Vietnamese Names" Is a Business Requirement to Specify

There is no single `sort` that is universally right for every Vietnamese directory. At minimum, you must explicitly pick one of two approaches:

- **Sort by family name, then middle name, then given name:** useful for certain record directories or printouts grouped by surname. For example, names with family names Bùi, Đặng, Đỗ, Hồ, Lê, Nguyễn, Phạm, Trần, Võ are grouped by family name and collation order.
- **Sort by given name, then resolve ties:** common in Vietnamese class rosters or contact lists, where "An", "Anh", "Ánh", "Bình", "Dung", "Dũng", "Đào", "Đức" are looked up by given name. Even so, sorting by the given-name field is a **product convention**, not something `Collator` automatically infers from a full name string.

An explicit data policy might look like:

```text
Sort by:
  1. givenName (with vi-VN Collator)
  2. familyName (with vi-VN Collator)
  3. middleName (with vi-VN Collator)
  4. immutable person ID (numeric order, for deterministic results)
```

If the product needs family-name grouping first, reorder the comparison keys. Crucially, **never guess the rule** merely from the presence of Vietnamese diacritics.

### Full Names Cannot Always Be Split by the Last Word

`"Nguyễn Thị Minh Anh"` may have the compound given name `"Minh Anh"`. Names like `"Thị Hồng"` or special naming structures, international names, single-word names, and entries missing a middle name also need a clear policy. Therefore, never default to:

```java
String givenName =
        fullName.substring(fullName.lastIndexOf(' ') + 1);
```

This is an **intentionally error-prone anti-pattern**, not a reliable Vietnamese name parser. It always extracts the **last token**, which is not necessarily the user-confirmed given-name field.

**Better design:** collect and store `familyName`, `middleName`, `givenName` fields or a business-normalized name structure. You can also store `displayName` to preserve exact user-preferred rendering and `sortName` confirmed by the user or HR when directories are complex.

## 3. What Is Collator and How Does It Differ from String.compareTo?

`java.text.Collator` is a `Comparator<Object>` capable of comparing text according to linguistic rules and locale data. For `String`, use:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vietnamese);

int result = collator.compare("Dung", "Đung");
```

This snippet lives inside a Java method and requires importing `java.text.Collator` and `java.util.Locale`. Negative/0/positive results indicate relative ordering under the runtime's configured `Collator`.

Compare with:

```java
int natural = "Dung".compareTo("Đung");
```

`String.compareTo` compares UTF-16 code units; it has no knowledge of Vietnamese alphabet order, tone marks, or linguistic weight levels. Just because one character has a higher code point does not mean it belongs after all other letters when sorting for Vietnamese readers.

**Note:** `Collator` behavior can depend on the JDK version, locale data source, and provider configuration. Specific orderings for accented pairs must be tested on the deployed Java version; never hardcode manual rules like "acute tone always comes after grave tone" and claim that is an API guarantee.

### Explicit Locale Initialization

Write:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vi);
```

instead of `Collator.getInstance()` when sorting Vietnamese data. The no-arg factory uses the JVM default locale, which can differ across developer machines, CI, and production servers.

Never call `Locale.setDefault(...)` per request just to sort. That mutates global state affecting other threads. Pass the locale explicitly and keep the comparator's scope clear.

### Collator Does Not Modify Names

`collator.compare(a, b)` returns a comparison integer; it does not return a "normalized" string and does not mutate `a` or `b` in the database. Operations like case folding, NFC normalization, collapsing extra whitespace, or splitting name parts belong to **separate data policies**, not side effects of `compare`.

## 4. Choosing Strength: Which Differences Affect Ordering?

`Collator` supports four strength levels:

| Level | General Meaning | When to Consider |
| --- | --- | --- |
| `Collator.PRIMARY` | Distinguishes primary base weights; many casing or tone differences may be ignored depending on locale. | Very loose search grouping; **never assume this defines identity**. |
| `Collator.SECONDARY` | Considers secondary differences, typically diacritics/character variants. | When more accented forms must be distinguished than `PRIMARY`. |
| `Collator.TERTIARY` | Considers tertiary differences, typically letter case. | Common choice for display sorting with finer distinction; still test thoroughly. |
| `Collator.IDENTICAL` | Strongest level of distinction in the implementation. | When deeper collation distinction is needed, though still not guaranteed identical to `String.equals`. |

The exact mapping from Vietnamese diacritics to collation weight levels **depends on collation data**. Some marks form distinct base letters at the primary level, while tone marks may occupy another weight level. Never claim all Vietnamese diacritics always fall at the exact same weight level across every JDK/provider.

### Choice for This Practice

The example uses:

```java
Collator vi = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
vi.setStrength(Collator.TERTIARY);
vi.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

`TERTIARY` demonstrates sorting that distinguishes case and diacritics per runtime data; `CANONICAL_DECOMPOSITION` aligns precomposed and decomposed Unicode forms under canonical equivalence rules.

If your product needs a "case-insensitive, diacritic-insensitive" search box, use a separate comparator or dedicated search index, **rather than reusing the same comparator to define record identity**.

### Testing Strength Levels Directly

```java
Collator primary = (Collator) vi.clone();
primary.setStrength(Collator.PRIMARY);

int p = primary.compare("An", "an");
int t = vi.compare("An", "an");
```

On the runtime used to verify this lesson, `p == 0` while `t != 0`. Always test on your target JDK rather than treating one pair as proof for the entire Vietnamese alphabet.

### Do Not Mutate a Collator Already Used in a Tree Collection

`Collator` is mutable via `setStrength` and `setDecomposition`. Once you pass it to a `TreeSet`/`TreeMap` holding entries, **never change its comparison rules mid-flight**, because the tree structure will not rebuild itself to match the new ordering. Create or clone a new `Collator` and build a new collection from source data when changing policies.

## 5. Precomposed Unicode vs. Combining Marks

Many Vietnamese characters can be represented by different code-point sequences. For example, `á`:

```text
Precomposed form: U+00E1
Decomposed form:  U+0061 U+0301
```

In Java:

```java
String precomposed = "\u00E1";
String decomposed = "a\u0301";

System.out.println(precomposed.equals(decomposed));
// false: different UTF-16 sequences.
```

Two strings can look identical while `String.equals` compares UTF-16 code units. When using `Collator` with `CANONICAL_DECOMPOSITION`, this lesson's Java example yields `compare(precomposed, decomposed) == 0` on the tested runtime.

**Do not confuse two distinct operations:**

- `Collator` compares two strings under a chosen collation relation.
- `Normalizer.normalize(text, Normalizer.Form.NFC)` transforms the representation of **a single string** into normalized form where appropriate.

An application may normalize names upon ingestion for easier lookup, but must clearly decide whether to preserve original spelling, how to migrate legacy data, and whether audit trails are required. **NFC does not strip diacritics**; it never turns `Nguyễn` into `Nguyen`.

### Risks When Comparing Names Across Different Unicode Forms

When data arrives from multiple platforms, a name may contain:

- Precomposed Unicode or combining marks.
- Non-breaking spaces or special whitespace characters.
- Inconsistent upper/lower casing.
- Punctuation in names, hyphens, or apostrophes.
- Zero-width characters or invisible control characters.
- Characters from other scripts such as Latin extensions, Han, or Arabic.

Never run `replaceAll("[^a-zA-Z]", "")` to "clean" Vietnamese names—that deletes or corrupts valid characters. If you need whitespace normalization or unexpected-character checks, write dedicated validation/tests, communicate clearly to users, and avoid silently discarding information.

## 6. Data Model: Storing Family, Middle, Given Name, and ID Separately

Using a Java 17 `record` for the example:

```java
record Person(int id, String family,
              String middle, String given) {}
```

Here:

- `id` identifies a person in the sample dataset and stays constant even if their name changes.
- `family` is the family name such as `Nguyễn`, `Trần`, `Lê`, `Đặng`.
- `middle` is the validated middle-name component.
- `given` is the validated given name; it may contain multiple words if the contract allows.
- The storage order of fields does not dictate the UI sort order.

**A `record` does not parse names automatically.** Each field must come cleanly from a form or trusted data source rather than being guessed by splitting on spaces.

If business logic needs a full name:

```java
String fullName = String.join(
        " ", person.family(), person.middle(), person.given());
```

This is merely an in-method example when all three fields hold appropriate values. Production products need rules for empty middle names, other countries, capitalization/honorifics, and locale-specific display conventions. **Sort keys and display names serve two different needs.**

### Why Include the ID in the Comparator?

When two people both have `given="An"` and similar family/middle names, sorting by name alone can return `0`. To keep list ordering **deterministic** even when names collide under `Collator`, append the ID as a final tie-breaker.

However, a record's `equals` depends on **all components**. A name + ID comparator **does not automatically prove consistency with `record.equals`** for all possible instances if two records shared an ID while having distinct names that collate equally. That is why this program uses the comparator for **`List.sort`**, not as the identity comparator of a `TreeSet<Person>`.

In production, maintain identity in a `Map<Integer, Person>` keyed by ID (or a table with a primary key), and use a `List<Person>` copy for sorted display.

## 7. Comparators for Two Common Sort Orders

### 7.1. Given Name First

```java
Comparator<String> viText = collator::compare;

Comparator<Person> byGiven =
        Comparator.comparing(Person::given, viText)
                .thenComparing(Person::family, viText)
                .thenComparing(Person::middle, viText)
                .thenComparingInt(Person::id);
```

This Java snippet resides in a method with an initialized `collator` and the `Person` record defined.

Comparison flow:

1. Compare `given` using Vietnamese collation rules.
2. If collation-equivalent, compare `family`.
3. If still equivalent, compare `middle`.
4. If still equivalent, compare integer `id`.

No complex manual `if/else` chain is needed, and full-name `compareTo` is never used as the sole key.

### 7.2. Family Name First

```java
Comparator<Person> byFamily =
        Comparator.comparing(Person::family, viText)
                .thenComparing(Person::middle, viText)
                .thenComparing(Person::given, viText)
                .thenComparingInt(Person::id);
```

Merely reordering the fields produces a **different sorting convention**. Both comparators use the exact same Vietnamese collation data yet yield different lists. This clearly demonstrates that **`Collator` does not decide "sort by family name or given name."**

### 7.3. Comparison with Natural String Order

```java
Comparator<Person> byUnicode =
        Comparator.comparing(Person::given)
                .thenComparingInt(Person::id);
```

This uses `String.compareTo`, not locale-specific collation. It is useful as a test baseline, but natural Unicode order must never be mistaken for Vietnamese alphabetical order.

### 7.4. Use List.sort Instead of Turning a Directory into a TreeSet

`List.sort(comparator)` **only reorders elements**; it never drops elements when the comparator returns `0`. `TreeSet` and `TreeMap`, by contrast, treat `compare == 0` as duplicate keys and can drop records.

Example of names colliding under a loose `Collator`:

```java
Collator primary = (Collator) collator.clone();
primary.setStrength(Collator.PRIMARY);

TreeSet<String> names = new TreeSet<>(primary);
names.add("An");
names.add("an");
// Only one element may remain if compare("An", "an") == 0.
```

In the verified runtime demo, this `TreeSet` has size `1`, whereas `HashSet<String>` retains both names (size `2`) because `String.equals` is case-sensitive. When every person must be preserved, key identity by ID and sort a `List`.

## 8. Standalone Java 17+ Program: Sorting 12 Vietnamese Names

Create **`VietnameseNameSortDemo.java`** encoded in UTF-8. The example intentionally **prints ID lists** rather than printing accented characters directly in verification stdout, avoiding confusion between terminal font/encoding issues and sorting bugs. The `family`, `middle`, and `given` fields remain real Vietnamese strings in code.

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

public class VietnameseNameSortDemo {

    record Person(int id, String family,
                  String middle, String given) {}

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Collator language = Collator.getInstance(vi);
        language.setStrength(Collator.TERTIARY);
        language.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        Comparator<String> viText = language::compare;

        List<Person> people = List.of(
                new Person(101, "Nguyễn", "Văn", "An"),
                new Person(102, "Trần", "Thị", "Ánh"),
                new Person(103, "Lê", "Minh", "Anh"),
                new Person(104, "Phạm", "Bảo", "Ân"),
                new Person(105, "Đặng", "Thu", "Đào"),
                new Person(106, "Đỗ", "Gia", "Dũng"),
                new Person(107, "Nguyễn", "Ngọc", "Dung"),
                new Person(108, "Hồ", "Thị", "Hòa"),
                new Person(109, "Bùi", "Minh", "Bình"),
                new Person(110, "Võ", "Quốc", "Đức"),
                new Person(111, "Nguyễn", "Thị", "Anh"),
                new Person(112, "Nguyễn", "Thị", "An")
        );

        Comparator<Person> byGiven =
                Comparator.comparing(Person::given, viText)
                        .thenComparing(Person::family, viText)
                        .thenComparing(Person::middle, viText)
                        .thenComparingInt(Person::id);

        List<Person> givenSorted = new ArrayList<>(people);
        givenSorted.sort(byGiven);
        System.out.println("givenIds="
                + givenSorted.stream().map(Person::id).toList());

        Comparator<Person> byFamily =
                Comparator.comparing(Person::family, viText)
                        .thenComparing(Person::middle, viText)
                        .thenComparing(Person::given, viText)
                        .thenComparingInt(Person::id);

        List<Person> familySorted = new ArrayList<>(people);
        familySorted.sort(byFamily);
        System.out.println("familyIds="
                + familySorted.stream().map(Person::id).toList());

        List<Person> natural = new ArrayList<>(people);
        natural.sort(Comparator.comparing(Person::given)
                .thenComparingInt(Person::id));
        System.out.println("naturalIds="
                + natural.stream().map(Person::id).toList());

        String composed = "\u00E1";
        String decomposed = "a\u0301";
        System.out.println("utf16Equals="
                + composed.equals(decomposed));
        System.out.println("collatorEquivalent="
                + (language.compare(composed, decomposed) == 0));

        Collator primary = (Collator) language.clone();
        primary.setStrength(Collator.PRIMARY);

        System.out.println("primaryCaseEquivalent="
                + (primary.compare("An", "an") == 0));
        System.out.println("tertiaryDistinguishesCase="
                + (language.compare("An", "an") != 0));

        TreeSet<String> tree = new TreeSet<>(primary);
        tree.add("An");
        tree.add("an");

        System.out.println("treePrimarySize=" + tree.size());
        System.out.println("hashSetSize="
                + new HashSet<>(
                        List.of("An", "an")).size());
    }
}
```

Compile and run with JDK 17 or later in the file's directory:

```bash
javac -encoding UTF-8 VietnameseNameSortDemo.java
java VietnameseNameSortDemo
```

**Stdout verified with JShell on the available OpenJDK environment with the configured Collator:**

```text
givenIds=[112, 101, 103, 111, 102, 104, 109, 107, 106, 105, 110, 108]
familyIds=[109, 105, 106, 108, 103, 107, 112, 111, 101, 104, 102, 110]
naturalIds=[101, 112, 103, 111, 109, 107, 106, 108, 102, 104, 105, 110]
utf16Equals=false
collatorEquivalent=true
primaryCaseEquivalent=true
tertiaryDistinguishesCase=true
treePrimarySize=1
hashSetSize=2
```

**Scope of stdout:** the three ID lists are empirical results from a Java environment with matching locale data. The ordering of accented names can vary across JDK/vendor/locale providers and bundled collation algorithms. The code runs on Java 17+, and if exact ID-list snapshot tests are required on another JDK, verify the collation data and build/deploy environment. Fundamental invariants—such as `List.sort` never dropping records, or `String.equals` returning `false` for distinct Unicode encodings—hold more independently of runtime version.

### ID Lookup Table for Reading Results

| ID | Family | Middle | Given |
| ---: | --- | --- | --- |
| 101 | Nguyễn | Văn | An |
| 102 | Trần | Thị | Ánh |
| 103 | Lê | Minh | Anh |
| 104 | Phạm | Bảo | Ân |
| 105 | Đặng | Thu | Đào |
| 106 | Đỗ | Gia | Dũng |
| 107 | Nguyễn | Ngọc | Dung |
| 108 | Hồ | Thị | Hòa |
| 109 | Bùi | Minh | Bình |
| 110 | Võ | Quốc | Đức |
| 111 | Nguyễn | Thị | Anh |
| 112 | Nguyễn | Thị | An |

### Line-by-Line Explanation of Output

- `givenIds`: sorts by **given name first**, breaking ties by family, middle, and ID. The two entries named `An` (101 and 112) are resolved by family/middle name rather than keeping insertion order.
- `familyIds`: uses the same `Collator` but sorts by **family name first**, producing substantially different grouping and order.
- `naturalIds`: uses `String.compareTo` on given names, giving a different order because it compares UTF-16 code units rather than Vietnamese collation.
- `utf16Equals=false`: precomposed `á` and `a` + combining acute accent are two distinct UTF-16 strings.
- `collatorEquivalent=true`: with `CANONICAL_DECOMPOSITION`, the runtime's `Collator` treats both forms as equivalent.
- `primaryCaseEquivalent=true` and `tertiaryDistinguishesCase=true`: different strength levels produce different comparison relations between `An` and `an` on the tested runtime.
- `treePrimarySize=1`: a `TreeSet` at `PRIMARY` merges both spellings under its comparator; `hashSetSize=2`: `HashSet` retains both under `String.equals`.

**The example does not mutate the JVM default locale, read external files, make network calls, or write to a database.** It makes two separate copies so one sort never alters the input of the next.

## 9. How to Display Names Instead of IDs

In a real application, you can display the sorted list in a method:

```java
for (Person p : givenSorted) {
    System.out.println(
            p.family() + " " + p.middle() + " " + p.given());
}
```

This is an **in-method code snippet** assuming `givenSorted` exists; it is not a standalone program. When the terminal uses UTF-8 and a supporting font, Vietnamese names render properly. If output turns into question marks or boxes, check **console encoding, byte streams, and fonts** before blaming `Collator`.

To preserve data integrity:

- Source files must be saved as UTF-8; `javac -encoding UTF-8` declares source file charset.
- `System.out` and the terminal must be properly configured to render glyphs.
- Log and CSV writers need explicit encodings and compatible fonts/readers.
- `Collator` performs **comparison**, not encoding repair or automatic Unicode normalization on Strings.

Never strip diacritics during export merely to dodge console issues; that **destroys proper-noun data**.

## 10. Avoiding Lost Records in TreeSet/TreeMap

Equivalence under `Collator.compare(a, b) == 0` **does not necessarily match `String.equals`**. In `TreeSet`/`TreeMap`, the comparator alone decides which keys are duplicates.

Example:

```java
Collator primary = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
primary.setStrength(Collator.PRIMARY);

TreeSet<String> set = new TreeSet<>(primary);
set.add("An");
set.add("an");
```

If the primary comparator treats both strings as equal, `set.size()` is only 1 even though `"An".equals("an")` is `false`.

This is **expected behavior per `TreeSet`'s contract**, not a runtime bug. However, if both names belong to two distinct people, using `TreeSet` as the single source of truth will drop one person.

### Separating Responsibilities Clearly

- **Source of truth:** `Map<Integer, Person>` or database keyed by ID.
- **UI sorting:** `List<Person>` + `sort`.
- **Fuzzy name search:** search index or `Collator` configured for search requirements.
- **Identity:** ID or domain entity equality rules, never display names.
- **Deterministic order:** comparator with a proper tie-breaker.

If you genuinely need a `TreeSet<String>` that both sorts linguistically and retains every spelling distinct under `String.equals`, add a natural-order tie-breaker:

```java
Comparator<String> safeOrder =
        ((Comparator<String>) primary::compare)
                .thenComparing(Comparator.naturalOrder());

TreeSet<String> distinct = new TreeSet<>(safeOrder);
```

When `Collator` returns `0`, `String.compareTo` separates distinct strings; this creates a comparator consistent with `String.equals` when components obey the contract and remain immutable. However, this solves only **`String` identity**. For `Person`, you must consider the object's `equals` definition; an ID tie-breaker works in `List.sort` but is still insufficient for a `TreeSet` holding records whose `equals` inspects all four fields.

### Never Mutate a Comparator After Inserting into a Tree

`Collator` is mutable. Changing `setStrength` from `TERTIARY` to `PRIMARY` after a `TreeSet` holds elements breaks the tree's ordering invariant. Never mutate a `Collator` used as the comparator of a populated collection; create a new instance and rebuild the collection from source data when changing policy.

## 11. Optimizing Sorts: CollationKey for Repeated Comparisons

`Collator.compare(a, b)` may recompute collation weights on every comparison. When sorting large name lists or comparing the same strings repeatedly, `CollationKey` avoids redundant work:

```java
Collator vi = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
vi.setStrength(Collator.TERTIARY);
vi.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

CollationKey a = vi.getCollationKey("Nguyễn");
CollationKey b = vi.getCollationKey("Trần");
int comparison = a.compareTo(b);
```

This Java snippet resides inside a method and requires importing `java.text.CollationKey` and `java.text.Collator`. Keys are generated under **the same `Collator` and configuration** for comparison. They are neither a universal Unicode ID nor a durable storage key across JDK versions.

### Sensible Caching Strategy

If lists are large and re-sorted frequently:

1. Fix locale, strength, and decomposition **before** generating keys.
2. Generate `CollationKey` for each sortable field when loading or building the view model.
3. Cache under a key capturing **both the name data version and comparator configuration**.
4. Whenever names or locale/config change, invalidate the cache and regenerate keys.
5. Compare only keys generated by a `Collator` with identical settings; never treat `toByteArray()` bytes as a durable cross-JDK/CLDR protocol.

`CollationKey` is an optimization that warrants benchmarking. For dozens or hundreds of names, a direct `Collator` comparator is simpler and fast enough. Do not prematurely optimize and introduce stale caches on frequently updated name lists.

## 12. Nulls, Empty Strings, Compound Names, and Punctuation

Real-world data is messier than twelve sample records. Before using a `Comparator`, decide on:

### 12.1. Null Names

`Collator.compare` is not designed to accept `null` as a valid name. Two clear options exist:

- Input-layer validation: require non-null, non-empty name fields per business rules.
- If the domain permits missing names, wrap with an explicit null-handling comparator such as `Comparator.nullsLast(viText)`, while testing and deciding how "unnamed" entries display.

Illustrative example:

```java
Comparator<String> optionalName =
        Comparator.nullsLast(viText);
```

This syntax is valid when `viText` is an already-created `String` comparator. **Never silently coerce `null` into an empty string** and treat it as a real name if the product must distinguish those two states.

### 12.2. Empty Strings and Whitespace

`""`, `" "`, `"Nguyễn  Văn"`, and `"Nguyễn\u00A0Văn"` can originate from different input sources. If the product wants to collapse redundant whitespace, do so in a **documented validation/normalization step**, rather than expecting `Collator` to handle every kind of Unicode whitespace.

`String.trim()`, `strip()`, and regex `\\s+` differ in which whitespace classes they match and do not treat all Unicode spacing identically. If strict control is required, define a code-point-based policy and test NBSP/thin spaces; above all, **never silently lose original name characters** in legally binding records.

### 12.3. Compound Names

A person may go by a two-word given name such as `"Minh Anh"`. When `given` holds two words, `Collator` compares the full phrase. Never slice off only the final word and alter the user's confirmed given name. If a product specifically wants sorting by the final token, treat that as a **separate documented policy**, not something `Collator` implies.

### 12.4. Numbers and Codes Embedded in Names

Labels such as `"Lớp 2"` and `"Lớp 10"` are not necessarily ordered numerically by a general text `Collator`. When numeric suffixes carry business ordering, extract the numeric field and use a numeric comparator. Do not arbitrarily split digits out of personal names unless the schema defines it.

### 12.5. Do Not Strip Đ or Tone Marks

Ad-hoc "Vietnamese normalization" via `toLowerCase(Locale.ROOT)` plus accent stripping can merge `D`/`Đ` or distinct vowels in ways users find wrong. **Never replace `Collator` rules with a manual accent-stripping table** without cultural/business documentation, comprehensive tests, and a clear compatibility policy.

## 13. Testing Locale Providers and JDK Versions

`Collator.getInstance(Locale.forLanguageTag("vi-VN"))` returns an instance from the runtime's locale services. You can check listed availability via:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
boolean listed = java.util.Arrays.stream(
        Collator.getAvailableLocales())
        .anyMatch(vi::equals);
```

This snippet belongs inside a method (import `java.util.Arrays` if using the short name). `getAvailableLocales()` reports locales exposed by the runtime API—**it does not certify that all Vietnamese collation data matches your product's exact expectations**.

If a locale lacks dedicated data, Java may apply fallback; never assume the factory throws an exception for "unsupported" locales. During QA, test the Vietnamese name pairs your product cares about and record the Java vendor and version.

### java.locale.providers

Locale provider order can be configured at JVM startup, for example:

```bash
java -Djava.locale.providers=CLDR VietnameseNameSortDemo
```

Depending on the JDK and services, `Collator` may use implementations/data independent of `NumberFormat` or `DateFormat` providers. Some collation rules differ between CLDR and legacy providers; do not claim setting `CLDR` forces every API onto one identical algorithm. Moreover, JDK locale data evolves across releases.

**Operational rule:** when sort order carries legal weight or reports demand strict long-term reproducibility, pin runtime versions, document comparison policies, and run regression tests—never store binary collation keys assuming eternal compatibility across upgrades.

### Multilingual Testing

If a list mixes Vietnamese and international names, define policies for:

- Names with non-Vietnamese Latin extensions or unfamiliar diacritics.
- Chinese, Japanese, Korean, Arabic, or other scripts.
- Multi-part names, mononyms, or culturally reversed name orders.
- Users viewing an English UI while browsing Vietnamese name data — **content locale and UI locale need not match**.

You may choose `vi-VN` to sort a directory known to contain Vietnamese names even when the UI is in English, or allow sorting according to the viewer's locale. Document the choice explicitly, since two viewers could see different orders if the product intentionally sorts per viewer locale.

## 14. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Wrong | Proper Approach |
| --- | --- | --- |
| Using `String.compareTo` assuming Vietnamese alphabetical order | Compares UTF-16 code units. | Use a `vi-VN` `Collator` and test on the target locale. |
| Calling `Collator.getInstance()` | Depends on JVM default locale. | Pass `Locale.forLanguageTag("vi-VN")`. |
| Sorting full names when business requires given-name order | Strings start with family name; `Collator` does not split names. | Store `given`/`family`/`middle` fields and sort on the right key. |
| Taking the last word as everyone's given name | Mishandles compound names and multicultural data. | Collect/validate name components per domain. |
| Stripping accents to simplify sorting | Alters or destroys name identity. | Use collation; separate sorting from normalization. |
| Calling `setStrength` on a `Collator` active in a `TreeSet` | Tree does not rebuild to match new ordering. | Create a new comparator/collection. |
| Using `TreeSet` as a unique person directory via `Collator` | `compare == 0` can merge distinct people. | Key storage by ID; sort a `List`. |
| Breaking ties with a non-unique field | Distinct records can still yield `compare == 0`. | Append a stable ID for deterministic `List` order; define `equals` properly for `Set`. |
| Using `PRIMARY` strength for all purposes | Collapses case/diacritics that may need distinction. | Choose separate strengths for sort vs. search. |
| Neglecting decomposed Unicode in tests | Identical-looking names fail `String.equals`. | Test normalization and `CANONICAL_DECOMPOSITION`. |
| Mutating `Locale.setDefault` per request | Corrupts concurrent threads. | Pass `Locale` explicitly. |
| Seeing garbled Vietnamese in terminal and blaming sort logic | Likely console encoding/font issue. | Print IDs/code points to isolate concerns. |
| Caching `CollationKey` bytes across JDK versions | Collation data/algorithms can change. | Version caches and invalidate explicitly. |
| Assuming all JDKs return identical name orderings | Locale providers and JDK data differ. | Run regression tests on the deployment runtime. |
| Mutating sort keys inside a `TreeMap` | Breaks tree ordering invariants. | Never mutate keys in sorted collections. |

## 15. Test Matrix for Vietnamese Directories

| Test Category | Sample Inputs | What to Verify |
| --- | --- | --- |
| Distinct letters | `An`, `Bình`, `Dung`, `Đức` | Sensible ordering under app sort rules. |
| `Đ` and `D` | `Dung`, `Đung` | How the runtime `Collator` orders them. |
| Accented vowels | `An`, `Ân`, `Ăn`, `Án` | Strength levels and `vi-VN` data behavior. |
| Tone marks | `Hà`, `Há`, `Hả`, `Hã`, `Hạ` | Ordering when base letters match. |
| Upper/lower case | `An`, `an`, `AN` | `PRIMARY` vs. `TERTIARY`; search policy. |
| Unicode normalization | `á` and `a + U+0301` | `Collator` decomposition and equality rules. |
| Duplicate names | Different IDs, identical given/family | Both remain in `List`; deterministic tie-break. |
| Compound given names | `Minh Anh`, `Hồng Nhung` | Not mis-split on the last word. |
| Similar family names | `Đặng`, `Đỗ`, `Dương` | Sorted by family name when requested, not given comparator. |
| Missing data | `null`, empty string, spaces | Validator or explicit null policy. |
| Special whitespace | `U+0020`, `U+00A0`, `U+202F` | Normalization policy without mutating source data. |
| International names | Other Latin characters or scripts | Support/fallback and user experience. |
| Large datasets | 10,000–100,000 test records | Performance, stability, `CollationKey` evaluation. |
| Multiple JDKs | JDK 17, 21, 23+ per target | Snapshot/fallback/provider changes if applicable. |

### Testing the Comparator Contract

Beyond verifying expected sort orders, check the mathematical contract:

```text
compare(a, a) == 0

sign(compare(a, b)) == -sign(compare(b, a))

If compare(a,b) > 0 and compare(b,c) > 0
then compare(a,c) > 0.

If compare(a,b) == 0 then sign(compare(a,z))
must equal sign(compare(b,z)) for all z.
```

This is **test pseudocode**, not literal Java syntax. For `Person` comparators, also assert:

- If IDs are unique in the source, two records with distinct IDs must never return `0` after the tie-breaker.
- An input list of `N` people must retain all `N` elements after `List.sort`.
- Order must not depend on map/hash iteration order once ties are broken by ID.
- Neither `Collator` nor key fields may be mutated while sorting is in progress.
- Invalid/`null` names must be rejected or placed deterministically before invoking `Collator`.

**Important:** comparing display sort order and comparing business identity are two separate tests.

## 16. Design Recommendations for Real Applications

A reasonably safe pipeline looks like:

```text
UI/Form/Input
    |
    v
Validation (does the name have all domain-required parts?)
    |
    v
Data model (ID, family, middle, given, displayName)
    |
    +----> Storage by ID (collation-independent)
    |
    +----> Search index (explicit diacritic/case policy)
    |
    +----> UI sorting: Collator(vi-VN) + Comparator fields + ID
                 |
                 v
            Sorted List<Person>
                 |
                 v
       Render name via displayName, preserving original Unicode
```

Decisions to document clearly:

1. Does the default UI sort by **given** or **family** name? Can users switch modes?
2. If `given` has multiple words, is the entire phrase used or a user-specified sort key?
3. Same given name, different family name: sort by family then middle, or another order?
4. Two people with identical name fields: which ID breaks ties?
5. Editable names: must sort caches or search indexes be invalidated?
6. Is Unicode NFC normalization applied at ingestion? How is the raw `displayName` preserved?
7. Does accent-insensitive search use the same equivalence relation as sorting? If not, how does the UI communicate it?
8. Locale/JDK upgrades: are lists persisted in a fixed order, and when are caches rebuilt?
9. Do Excel/CSV/API exports preserve original Unicode and UTF-8 encoding?
10. Should sorting follow the viewer's locale/residence rather than a fixed Vietnamese locale?

Never force sorting, searching, identity validation, and storage onto one shared comparator just because all of them "involve names."

## 17. Practice Exercises

**Exercise 1 — Run the sample:** compile and run `VietnameseNameSortDemo.java` on JDK 17+. Use the ID table to decode `givenIds` and `familyIds`. Explain why they differ and record your JDK version.

**Exercise 2 — Compare with `String.compareTo`:** add names `An`, `Án`, `Ăn`, `Ân`, `Anh` and sort with both `String.compareTo` and `vi-VN` `Collator`. Do not guess results from Unicode charts; print IDs/code points to compare.

**Exercise 3 — Strength levels:** clone the `Collator`, set `PRIMARY`, `SECONDARY`, `TERTIARY`, and `IDENTICAL` in turn; compare `An`/`an`, `An`/`Án`, `Dung`/`Đung`. Record which pairs return `compare == 0` and explain when each strength applies.

**Exercise 4 — Compound given names:** replace one record with given name `Minh Anh` and add another with `given="Anh"`. Sort by the stored full `given` field. Explain why slicing the last token of `fullName` produces wrong results for the data requirements.

**Exercise 5 — Two Unicode encodings of `á`:** construct `"\u00E1"` and `"a\u0301"`. Compare `String.equals` against `Collator` with `CANONICAL_DECOMPOSITION`. Try `Normalizer.Form.NFC` if the product requires normalized storage.

**Exercise 6 — Never drop people:** insert two `Person` records with different IDs but identical names into a `List`, sort, and confirm both IDs remain. Compare with a name-only `TreeSet`, then redesign using a `Map` by ID plus a sorted `List`.

**Exercise 7 — Null and whitespace:** prepare names with `null`, empty strings, NBSP, and extra spaces. Write a validator/canonicalizer with an explicit policy without silently collapsing semantically distinct values.

**Exercise 8 — Performance:** generate 50,000 records from expanded sample data, benchmark a direct comparator against a `CollationKey` cache, and test checksum/order equivalence, memory footprint, and cache invalidation.

**Exercise 9 — API contract:** design an endpoint returning people by ID and raw name fields, letting the UI choose `given` or `family` sorting. Never send reversed name strings, stripped accents, or collation keys as IDs.

**Exercise 10 — Multi-version regression:** run the same sample across all JDKs/vendors your product targets. Compare orderings, annotate differences, and identify critical name pairs if the application requires custom rules.

### Final Checklist

- [ ] Instantiate `Collator` explicitly for `vi-VN`.
- [ ] Understand how locale-aware `Collator` differs from UTF-16 `String.compareTo`.
- [ ] Distinguish sorting by given name vs. family name as a business decision.
- [ ] Model `ID`, `family`, `middle`, and `given` without assuming the last token is always the given name.
- [ ] Choose appropriate strength and decomposition, and test Unicode forms.
- [ ] Build comparators on `given`/`family`/`middle`/`ID` and sort a `List` without losing records.
- [ ] Know that `TreeSet`/`TreeMap` rely on `compare == 0` and can merge distinct names.
- [ ] Preserve original Unicode; never strip diacritics to work around console issues or confuse encoding with collation.
- [ ] Test nulls, diacritics, casing, compound names, duplicate names, and large datasets.
- [ ] Never mutate a `Collator` inside a sorted collection or blindly cache `CollationKey` across versions.
- [ ] Verify on the deployment JDK/provider when strict reproducibility of name order is required.

## 18. References

- Java 17 `Collator` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html
- Java 17 `CollationKey` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html
- Java 17 `Comparator` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html
- Java 17 `TreeSet` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html
- Java 17 `Normalizer` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html

**Conclusion:** To **sort Vietnamese names with `Collator`**, combine two layers: **`vi-VN` `Collator`** determines linguistic string ordering by locale, while a **`Comparator` over `family`/`middle`/`given`/`ID`** encodes business sort preference and tie-breaking. Store names in logical Unicode with independent identities, sort a `List` for display, and test strength, decomposition, and target runtimes. Never delegate name parsing, accent stripping, or person identity to `Collator`—it only compares strings, never replacing a proper data model.
