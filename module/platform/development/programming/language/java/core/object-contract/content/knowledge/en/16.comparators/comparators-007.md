# Choosing String Comparison Rules Based on Business Requirements with Comparator in Java

## 1. Why Does a String Have Multiple Correct Ways to Sort?

An application may need to sort personal names in Vietnamese, product codes by numeric sequence, labels alphabetically ignoring case, or technical keys in a stable byte/Unicode order. Those rules are **different**. No single `Comparator<String>` can be right for every case.

For example, with the four strings `"A"`, `"a"`, `"B"`, `"b"`:
- `String.compareTo` follows the lexicographical order of UTF-16 code units: `A, B, a, b`.
- `String.CASE_INSENSITIVE_ORDER` treats `"A"` and `"a"` as equal in order; when sorting a `List` stably, the relative order of these two elements is preserved.
- A rule that is *case-insensitive first, then uses natural order as a tie-breaker* produces `A, a, B, b`, giving a deterministic order even among case variants.

With `"item2"` and `"item10"`, standard lexicographical order places `"item10"` before `"item2"`, because it compares the character `'1'` against `'2'`. If business requirements want codes with numeric suffixes in ascending numeric order, a different rule must be defined.

In the context of **Java core – Object Contract / Comparator**, this lesson guides you in choosing rules based on business semantics, building contract-compliant comparators, checking consequences with `TreeSet`/`TreeMap`, and distinguishing technical comparison from linguistic comparison.

## 2. Before Writing Code: Specifying Data and Rules

Clarify six questions:

1. **What is being sorted?** Technical codes, personal names, UI labels, alphanumeric item codes, or free-form input strings?
2. **Is there a locale?** Vietnamese name lists typically need Vietnamese linguistic rules; technical keys instead need locale-independent stable results.
3. **Do case and accents matter?** Should `"A"` vs `"a"` or `"ma"` vs `"má"` be treated at the same priority level?
4. **Do whitespace, punctuation, and Unicode representation matter?** Should normalization occur before comparing; you must distinguish display normalization from changing true identity.
5. **Is there a numeric part?** Should `"SKU-2"` and `"SKU-10"` be compared numerically; are `"SKU-02"` and `"SKU-2"` treated as the same group or two different codes?
6. **What does `compare(a,b)==0` mean?** Merely sharing a rank for sorting a list, or must they be treated as duplicate keys in `TreeSet`/`TreeMap`?

Example decision matrix:

| Need | Starting rule | Point to decide |
|---|---|---|
| Machine keys, case-sensitive codes | `Comparator.naturalOrder()` | Order is UTF-16; not human reading order |
| Grouping/sorting ignoring case | `String.CASE_INSENSITIVE_ORDER` | Compares as 0 for some strings that differ by `String.equals` |
| Alphabetizing case-insensitively while keeping all variants | Case-insensitive then tie-break with natural order | Preserves distinction between `"A"` and `"a"` in a sorted set |
| Vietnamese display names/labels | `Collator` with `Locale.forLanguageTag("vi-VN")` | Must choose strength, accent sensitivity, and tie-break |
| Codes with a numeric suffix | Split, validate, then compare numerically; then tie-break | Are numbers 2 and 02 equivalent? |
| Values containing `null` | `nullsFirst` or `nullsLast` | Agree on whether `null` is valid data or an error |
| Multi-criteria sorting | `comparing`, `thenComparing` | What is the priority order and duplicate handling? |

A good concrete requirement is: "List of product names displayed to vi-VN users; use Vietnamese linguistic order, preserve accent distinctions, do not drop products just because names are similar; when the collator treats them as equal, compare the original strings so results repeat consistently."

## 3. Preserving the `Comparator<T>` Contract

The string comparison policy does not only determine which comes first; it also determines which two strings belong to the same group when `compare(a,b)==0`. Under any rule (natural, case-insensitive, `Collator`, or numeric-part comparison), sign symmetry, transitivity, and consistent comparison signs for tied elements must still hold.

For example, `String.CASE_INSENSITIVE_ORDER.compare("A","a")==0` while `"A".equals("a")` is `false`. This is a valid comparator for display, yet `TreeSet` may merge those two keys. Add `thenComparing(Comparator.naturalOrder())` if you need to keep every distinct String variant; **do not add a tie-breaker** if business logic truly wants case-insensitive identity.

For accented strings or numeric codes, determine normalization, locale, case policy, leading zeros, and identity keys before choosing a tie-breaking strategy. A comparator must not depend on randomness, time, a `Collator` configuration being mutated, or external sources changing during sorting. For numeric criteria, use standard factories (`comparingInt/Long`) instead of overflow-prone subtraction. When comparing in `TreeSet/TreeMap`, check both directions of the `compare==0` and `equals` relationship with representative data.
## 4. Option One: Technical Order of `String`

`String.compareTo` compares UTF-16 code units from left to right, which differs from using the natural alphabetical rules of any specific locale. For accented strings or surrogate pairs, do not infer that UTF-16 comparison equals linguistic "user-perceived character" comparison.

```java
Comparator<String> technical = Comparator.naturalOrder();
List<String> labels = new ArrayList<>(List.of("b", "A", "a", "B"));
labels.sort(technical);
System.out.println(labels); // [A, B, a, b]
```

This is an illustrative snippet inside a method with `import java.util.*` or equivalent imports. This order suits technical codes with a fixed schema if the requirement specifically calls for String comparison order. It is **not** the standard way to display Vietnamese names to humans.

### Unicode normalization and representing the same character

Two visually identical strings can use different Unicode sequences: a precomposed accented character, or a base character plus a combining diacritic mark. `String.equals` and `compareTo` inspect code unit sequences and thus may give different results. If the business domain treats canonically equivalent Unicode representations as the same data, normalize to NFC upon ingesting data:

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(raw, Normalizer.Form.NFC);
```

This excerpt assumes an already declared `raw` variable. Do not blindly normalize all fields such as passwords, tokens, signature codes, or external IDs: normalization can alter identity-bearing data. Be consistent across input, storage, lookup, and comparison.

## 5. Option Two: Case-Insensitive Comparison

`String.CASE_INSENSITIVE_ORDER` and `String.compareToIgnoreCase` perform case-insensitive comparison based on Java's character case mappings, **not a locale-aware linguistic collator**. They are not synonymous with `Collator`, and do not automatically handle all Unicode variants, accents, or language-specific ligatures.

```java
Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;
Comparator<String> ignoreCaseThenNatural =
        ignoreCase.thenComparing(Comparator.naturalOrder());
```

With `List.of("b", "A", "a", "B")`:
- Sorting with `ignoreCase` via `List.sort` (stable) yields `[A, a, b, B]`. Two values indistinguishable by the comparator retain their relative input order in the list.
- Sorting with `ignoreCaseThenNatural` yields `[A, a, B, b]`. The secondary criterion uses `String.compareTo` to separate `A/a` and `B/b`.
- Adding all four strings to `TreeSet<>(ignoreCase)` yields only **two elements**, because `compare==0` is treated as duplicate.

**Crucial business question:** do you want to group `"A"` and `"a"` as the same name, or only place them next to each other while remaining two separate keys? The answer determines whether to use a tie-breaker.

### Do not misuse `toLowerCase()`

You may see code like `Comparator.comparing(s -> s.toLowerCase())`. This approach:
- Depends on the default locale if no `Locale` is passed.
- May allocate new strings repeatedly during sorting.
- Can behave differently from `compareToIgnoreCase` because Unicode case conversion is locale-dependent and can change string length.
- Does not by itself solve accent rules, Unicode canonical forms, or consistency with database keys.

If a locale-independent canonical key is genuinely needed, pick and document a policy such as `toLowerCase(Locale.ROOT)`, consider Unicode normalization, test relevant languages, and handle tie-breaking. `Locale.ROOT` does not mean "correct for every language"; it is better suited for certain technical transformations not aimed at one country's display rules.

## 6. Option Three: Linguistic Comparison with `Collator`

For personal names, place names, or display labels, locale-based **collation** is often required. Java provides `java.text.Collator`:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vietnamese);
collator.setStrength(Collator.TERTIARY);

Comparator<String> vietnameseOrder = collator::compare;
Comparator<String> vietnameseWithTieBreaker =
        vietnameseOrder.thenComparing(Comparator.naturalOrder());
```

Here:
- Choose the locale **explicitly** (`vi-VN`) instead of relying on the host machine's default.
- `Collator` provides linguistic ordering for the chosen locale, which is more suitable than `String.compareTo` when sorting Vietnamese names.
- `setStrength` specifies the level of differences considered: `PRIMARY` mainly distinguishes base letters; `SECONDARY` adds secondary differences such as many accent marks; `TERTIARY` adds finer differences such as some case distinctions. Exact sorting depends on the rules and locale data provided by the JDK.
- `thenComparing(Comparator.naturalOrder())` breaks ties when the collator returns `0`, ensuring strings that differ under `String.equals` are not collapsed into one in a `TreeSet`.
- Do not assert that Vietnamese tone marks always belong to a single fixed strength across every provider and data version; test real cases against the deployed JDK, locale data, and product policy.

### Choosing strength according to requirements

| Strength | Suitable when | What to check |
|---|---|---|
| `Collator.PRIMARY` | Wanting to group minor variants by base letter | May treat different names as tied |
| `Collator.SECONDARY` | Needing to distinguish accent/secondary variants per collation | Locale-specific distinction rules |
| `Collator.TERTIARY` | Wanting finer distinctions, potentially including case | Not automatically identical to `String.equals` |
| `Collator.IDENTICAL` | Needing the highest distinction level supported by the collator | Still must define rules for Unicode forms, provider, and tie-breaking |

`Collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION)` may be needed to consistently handle strings differing between precomposed characters and base character + combining marks. Processing cost and output must be tested against real requirements. Do not substitute a collator flag for defining a proper data normalization policy without evaluation.

**Do not assume that the order of `"Hà"`, `"Hoa"`, `"Hòa"` will be identical across every JDK version and every collation provider configuration.** Locale data can vary between JDK/CLDR releases. If an order must be strictly stable across systems or persisted into a DB/index, define a managed versioned collation rule.

### `Collator` is a stateful configurable object

Calls like `setStrength` and `setDecomposition` mutate how comparisons behave. Avoid sharing and mutating the same `Collator` across threads or while a collection is already using that comparator. If concurrent processing is needed, use separate instances or clones per worker/thread as appropriate; never alter comparator policy while a `TreeSet`/`TreeMap` already holds data.

## 7. Option Four: Codes Containing Numeric Parts

For `item1`, `item2`, `item10`, sorting by `String.compareTo` produces `item1, item10, item2` due to character-by-character comparison. If valid codes always have the prefix `item` and a sequence of ASCII digits, comparing the **numeric value of the suffix** produces `item1, item2, item10`.

Clear rules:
1. Validate the code syntax before or inside the number extraction function: `item[0-9]+`.
2. Parse the part after `item` with `BigInteger` if you do not want length limits or `int`/`long` overflow.
3. Compare numeric value first.
4. Decide on `item02` vs `item2`: two codes with the same numeric value but different representations; if you want to keep both as distinct keys, add a natural-order tie-breaker.
5. For codes with multiple heterogeneous numeric/alphabetic segments, build a dedicated parser/tokenizer; do not hardcode slicing at the fifth character for every domain.

```java
static BigInteger itemNumber(String code) {
    if (!code.matches("item[0-9]+")) {
        throw new IllegalArgumentException("Not item + digits: " + code);
    }
    return new BigInteger(code.substring(4));
}

Comparator<String> byNumber = Comparator.comparing(
        StringComparatorDemo::itemNumber)
        .thenComparing(Comparator.naturalOrder());
```

This excerpt belongs to the `StringComparatorDemo` class in the complete example below. For `item02` and `item2`, both numbers are 2, yet the secondary criterion distinguishes the original strings. Do **not** handle numbers via `return Integer.parseInt(aSuffix) - Integer.parseInt(bSuffix)` because subtraction can overflow and long numbers can exceed range limits.

An alternative policy might want numeric codes `02` and `2` to be **the same identifier**. In that case, normalize the key upon writing or deliberately return `0`; weigh the impact on `TreeSet`/`TreeMap` and data uniqueness.

## 8. Option Five: Null, Whitespace, Multiple Criteria

### Null

`Comparator.naturalOrder()` and many other comparators do not accept `null`; if data permits `null`, define its placement:

```java
Comparator<String> nullLast =
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER
                .thenComparing(Comparator.naturalOrder()));
```

If `null` must come first, use `Comparator.nullsFirst(...)`. For lists containing `null`, avoid `List.of(...)` since that factory rejects null; use `Arrays.asList(...)` or a mutable list as needed. If null is invalid data, failing fast at the input boundary is better than silently sorting nulls to the end.

### Whitespace and secondary criteria

If the requirement is "ignore leading/trailing whitespace when sorting while still distinguishing original strings," you can write:

```java
Comparator<String> trimThenNatural =
        Comparator.comparing(String::strip)
                .thenComparing(Comparator.naturalOrder());
```

`String.strip` is based on Unicode whitespace per `Character.isWhitespace` and differs from `String.trim`. Some characters may not be handled as users expect, so test with real data. The comparator above **does not modify the original strings themselves**; it only uses the transformed value for comparison, then compares the original strings on ties.

If a policy like "case-insensitive; ascending length; finally original text" is needed, write the precedence order explicitly. Check cases where two comparators differ in equivalence semantics to avoid unintended key collapsing.

## 9. Complete Java 17 Example with Verifiable Output

The following **`StringComparatorDemo.java`** file runs standalone with JDK 17+. It demonstrates deterministic results for natural order, case-insensitive, tie-breaker, numeric suffix, and null. The `Collator` section does not print the sorted list because Vietnamese letter order can depend on locale data version; the program still configures and runs the actual comparator.

```java
import java.math.BigInteger;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

public class StringComparatorDemo {
    static List<String> sorted(List<String> source, Comparator<String> order) {
        List<String> copy = new ArrayList<>(source);
        copy.sort(order);
        return copy;
    }

    static BigInteger itemNumber(String code) {
        if (!code.matches("item[0-9]+")) {
            throw new IllegalArgumentException("Not item + digits: " + code);
        }
        return new BigInteger(code.substring(4));
    }

    public static void main(String[] args) {
        List<String> labels = List.of("b", "A", "a", "B");
        System.out.println("natural: "
                + sorted(labels, Comparator.naturalOrder()));
        System.out.println("ignore case: "
                + sorted(labels, String.CASE_INSENSITIVE_ORDER));

        Comparator<String> totalCaseOrder = String.CASE_INSENSITIVE_ORDER
                .thenComparing(Comparator.naturalOrder());
        System.out.println("tie breaker: "
                + sorted(labels, totalCaseOrder));

        TreeSet<String> ignoreCaseSet =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCaseSet.addAll(labels);
        System.out.println("set ignoring case size: "
                + ignoreCaseSet.size());

        List<String> ids = List.of("item10", "item2", "item1", "item02");
        Comparator<String> byNumber = Comparator.comparing(
                StringComparatorDemo::itemNumber)
                .thenComparing(Comparator.naturalOrder());
        System.out.println("IDs natural: "
                + sorted(ids, Comparator.naturalOrder()));
        System.out.println("IDs numeric: " + sorted(ids, byNumber));

        Comparator<String> nullLast =
                Comparator.nullsLast(totalCaseOrder);
        System.out.println("null last: " + sorted(
                java.util.Arrays.asList(null, "b", "A"), nullLast));

        Collator vi = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        vi.setStrength(Collator.TERTIARY);
        Comparator<String> viOrder = vi::compare;
        List<String> names = sorted(
                List.of("Hòa", "Hoa", "Hà", "Anh"),
                viOrder.thenComparing(Comparator.naturalOrder()));
        System.out.println("vi collator configured: "
                + (vi.getStrength() == Collator.TERTIARY));
        System.out.println("vi names count: " + names.size());
    }
}
```

Run in the directory where the file is saved:

```bash
javac --release 17 StringComparatorDemo.java
java StringComparatorDemo
```

Exact output for the printed lines below:

```text
natural: [A, B, a, b]
ignore case: [A, a, b, B]
tie breaker: [A, a, B, b]
set ignoring case size: 2
IDs natural: [item02, item1, item10, item2]
IDs numeric: [item1, item02, item2, item10]
null last: [A, b, null]
vi collator configured: true
vi names count: 4
```

This example has been verified to compile and run with `javac --release 17`. Detailed explanation:

- `natural`: uppercase `A`/`B` come before `a`/`b` under UTF-16 rules.
- `ignore case`: `List.sort` is stable, so within equal-comparison groups (`A/a` and `b/B`) it preserves initial relative order.
- `tie breaker`: the natural-order secondary criterion distinguishes uppercase/lowercase, giving distinct values a deterministic order.
- `TreeSet` drops elements when the comparator returns `0` for strings differing under `String.equals`.
- `IDs natural`: pure string comparison puts `item02` before `item1` and `item10` before `item2`.
- `IDs numeric`: parses the numeric suffix, then natural order breaks the `item02`/`item2` tie.
- `null last`: the comparator specifies the placement of `null`.
- `vi collator`: checks that a `Collator` instance for the Vietnamese locale is configured and used to sort 4 names. The program deliberately prints only the **element count** so it does not depend on the linguistic order supplied by each JDK.

## 10. Tie-Breakers When Sorting Objects with Names

When working with object data, compare by the chosen field and append an immutable key to distinguish records if business logic requires a total order:

```java
record Customer(long id, String displayName) {}

Comparator<Customer> byDisplayNameThenId =
        Comparator.comparing(
                Customer::displayName,
                String.CASE_INSENSITIVE_ORDER)
        .thenComparingLong(Customer::id);
```

The above is an illustrative example, not included in the runnable file in section 9. If two different customers share the same case-insensitive name, ID serves as the secondary criterion. The condition is that ID represents a unique and stable identifier. If multiple distinct records can still share the same ID in the list, re-examine the model.

For Vietnamese display, you can replace `String.CASE_INSENSITIVE_ORDER` with a comparator based on a configured `Collator`. However, you must decide whether accent differences or ties where collation returns `0` should be broken by ID or by the original string to match business rules.

### When a tie-breaker is unintended

If the system treats two account names `"ADMIN"` and `"admin"` as the same case-insensitive identifier, a comparator returning `0` may be right for that *uniqueness relation*. Adding `thenComparing(naturalOrder())` would turn them into two separate keys in a `TreeMap`. Thus **a tie-breaker is a business decision**, not a mechanical rule.

In particular, check consistency between the application and the database: if the database uses a different collation or unique index ignoring case/accents differently from the Java comparator, the application may allow a key that the database rejects, or vice versa.

## 11. Performance and Stability in Systems

A comparator is invoked many times during a sort, roughly `O(n log n)` times for typical comparison-based sorting algorithms. Therefore:

- Do not make HTTP/database calls inside `compare`.
- Do not parse complex codes or normalize strings thousands of times if sort keys can be prepared once per element. For large datasets, the data model should pre-store normalized keys or use an appropriate sort key with version control.
- Do not mutate a `Collator` currently used by a `TreeSet`/`TreeMap` after the collection already contains elements.
- Do not use a comparator relying on time, randomness, or volatile state changing mid-sort.
- With multiple threads, each thread should have its own configured `Collator` or proper cloning/instance management; avoid mutating a shared instance.
- Verify sort results when upgrading the JDK, changing locale providers/CLDR, or migrating to a database with a different collation. If ordering is a data contract or affects pagination, explicitly manage versions and stable tie-breakers.
- Sorting in the DB requires matching `ORDER BY` and a unique tie-breaker for stable pagination; a Java comparator only sorts data already loaded into memory and cannot guarantee DB-side page ordering.

If the goal is solely displaying names, depending on JDK collation data may be acceptable. If the goal is identity, deduplication, or signatures/canonicalization, use a custom rule that is **fixed and testable**.

## 12. Testing Comparators Against Business Rules

Do not test only a single happy-path list. Build a test suite covering:

| Case category | Example | What to verify |
|---|---|---|
| Case | `A`, `a`, `B`, `b` | Whether merged or distinguished, how tie-breaking works |
| Vietnamese accents | `ma`, `má`, `mà`, `MÁ` | Order matches rule, locale, and strength |
| Unicode forms | Precomposed char vs base char + mark | Consistent NFC/NFD policy and collation |
| Numbers in codes | `item2`, `item10`, `item02` | Numeric parsing, leading zeros, tie-breaking |
| Whitespace | `" An"`, `"An"`, `"An "` | Whether stripped/trimmed or preserved |
| Null | `null`, `""`, `"a"` | Placed first/last or rejected as invalid data |
| Empty string | `""` | Accepted or fails validation |
| Mixed characters | Letters, digits, emoji, non-BMP chars | Never assume UTF-16 matches collation |
| Multiple objects with same name | Two customers with different IDs | Whether elements are dropped in `TreeSet` |

Beyond expected ordering, test the **mathematical contract** of the comparator:
1. For every `a,b`: the sign of `compare(a,b)` is the opposite of the sign of `compare(b,a)`.
2. For `a,b,c`: if `a<=b` and `b<=c`, then `a<=c`.
3. When `compare(a,b)==0`, comparing `a` and `b` against every other `c` must yield equivalent signs.
4. When the comparator serves as `TreeSet`/`TreeMap` keys, check whether pairs differing by `equals` get unexpectedly merged.
5. Check that repeated sorting yields the exact same output under the same dataset, rules, and locale configuration.

You can write a unit test with the target comparator, run `Collections.sort` or `List.sort`, and assert the exact resulting list. With `Collator`, test on the JDK/provider/locale data of the supported environment, and record the version if ordering must be reproducible.

## 13. Common Mistakes

**1. Using `String.compareTo` for every language.** This is technical UTF-16 order and does not fully handle Vietnamese collation.

**2. Using `compareToIgnoreCase` and assuming all spellings are equivalent.** It is neither full Unicode case folding nor collation, and does not strip accents.

**3. Calling `Collator.getInstance()` without passing a locale.** Results can depend on the JVM environment; choose the locale based on the feature.

**4. Having the comparator return `0` for all "similar" names and putting them into a `TreeSet`.** Multiple distinct elements can be treated as one. If the goal is only sorting, a tie-breaker is needed.

**5. Adding a tie-breaker to a case-insensitive uniqueness rule.** This can accidentally allow two keys that business logic considers duplicates.

**6. Comparing numbers via string comparison or subtraction.** `item10` precedes `item2` lexicographically; numeric subtraction can overflow.

**7. Uncontrolled data normalization.** `strip`/`toLowerCase`/NFC may make sense for one group of fields while corrupting tokens or external keys.

**8. A comparator depending on mutable state.** Changing key information while inside a `TreeMap`/`TreeSet` can break tree structure, similar to hash collection issues when a key changes its hash.

**9. Testing on one JDK release and claiming locale order is immutable.** For display names, verify both locale data and the deployment environment.

## 14. Practice Exercises with Clear Criteria

### Exercise 1 — Sorting UI names in Vietnamese

Create the list `["Hoa", "Hòa", "Hà", "Anh"]`. Compare using `String.compareTo` and a `vi-VN` locale `Collator` at different strength levels. Record actual results in your environment; explain why UTF-16 comparison differs from linguistic comparison. Evaluate whether case, accents, and an original-string tie-breaker need to be preserved.

### Exercise 2 — From list to set

Use `["Admin", "admin", "ADMIN"]` in an `ArrayList` and a `TreeSet` with `String.CASE_INSENSITIVE_ORDER`. Compare element counts and explain why. Try `thenComparing(Comparator.naturalOrder())`. Decide the right approach for a display list versus case-insensitive account keys.

### Exercise 3 — Sorting product codes with numbers

Input `item1`, `item02`, `item2`, `item10`. Write a comparator comparing the BigInteger suffix then tie-breaking by the original representation. Add validation rejecting `item-2` and `itemX`. Test numbers longer than `long` limits.

### Exercise 4 — Names with whitespace

Design a comparator sorting `" An"`, `"An"`, and `"An "` by their `strip`ped strings, then by original strings. State reasons for or against normalizing data upon input.

### Exercise 5 — Three criteria for objects

Given record `Customer(id, displayName, priority)`, write a comparator: priority ascending, name by a chosen rule, ID ascending to break ties. Verify no records are lost when inserted into a `TreeSet` if ID is unique and immutable.

### Exercise 6 — Contract test

Generate a set of strings containing ASCII, accented letters, emoji, and empty strings; check sign symmetry and transitivity across every triple in the finite set. When encountering a case where `compare==0` for two strings differing under `equals`, decide whether that is an intentional grouping rule or a bug to fix.

## 15. End-of-Lesson Decision Checklist

- Clarified whether data consists of technical codes, names/natural language, or alphanumeric codes.
- Chosen policies for locale, case, accents, Unicode normalization, and whitespace.
- Correctly explained the business meaning of `compare(a,b)==0`.
- Distinguished **sorting** requirements from **uniqueness** requirements in `TreeSet`/`TreeMap`.
- Included a stable tie-breaker when wanting to preserve all distinct records.
- Properly handled `null`, malformed input, and numbers with leading zeros.
- Comparator preserves sign symmetry, transitivity, and consistent results on unchanged data.
- Verified locale/provider/JDK when stable linguistic ordering is needed.
- Checked compatibility with database collation if comparison happens in both places.
- Successfully ran `StringComparatorDemo.java`, able to explain each stdout line and the trade-offs of each comparator.

**Conclusion:** Choosing a `Comparator<String>` starts from the **business meaning of ordering and equivalence**, and only then picking the API. `String.compareTo` suits technical ordering, `CASE_INSENSITIVE_ORDER` suits case-insensitive grouping, `Collator` suits linguistic rules, and number-splitting comparators suit alphanumeric codes. Use tie-breakers deliberately to avoid losing keys in sorted collections; always test Unicode, locale, and real ID cases.