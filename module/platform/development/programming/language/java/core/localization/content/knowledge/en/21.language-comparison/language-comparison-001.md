# Why String.compareTo Is Not Equivalent to Locale Dictionary Order

When building multilingual Java applications, a list sorted with **String.compareTo** can produce an order that surprises users: uppercase names appear before lowercase names; accented words are pushed far away from unaccented words; and **file10** appears before **file2**. It is not because Java sorts incorrectly. The issue is that **String.compareTo** performs a technical comparison by **UTF-16** code units, whereas **dictionary order** is a set of language/region rules that can account for base letters, accents, case, and other variants.

To sort names, labels, titles, or user-visible content, Java Core provides **java.text.Collator**. This object uses a **Locale** and the runtime's collation rule set to decide whether one string comes before or after another. This lesson explains the nature of both approaches, Collator strength levels, Unicode normalization, impacts on SortedSet/SortedMap, CollationKey, performance, consistency between server and database, along with Java 17+ examples.

## 1. "String Comparison" Can Mean Many Different Requirements

Consider the strings:

~~~text
An
an
Ánh
Anh
Đào
dũng
Zebra
file2
file10
~~~

Completely different requirements can be stated:

| Purpose | Desired ordering relation | Approach |
| --- | --- | --- |
| Establish a fixed technical order for Strings | Compare UTF-16 code units | String.compareTo |
| Sort a directory according to the viewer's language | Locale-based collation | Collator.getInstance(locale) |
| Compare two encodings of the same accented letter | Canonical Unicode equivalence | Normalizer NFC/NFD per contract |
| Sort filenames containing numbers like file2, file10 | Natural/numeric-aware sorting | Specialized Comparator |
| Compare IDs, protocol key names | Per identifier/protocol rules | Exact equality or specified normalization |
| Fuzzy search, case/accent-insensitive | Matching operation, not necessarily sorting | Search key or search engine |
| Multi-field sorting | Locale-ordered name with ID as tie-breaker | Composed Comparator |

**Do not use the same comparator for every role.** An order suitable for a user menu is not necessarily right for a unique key, signature, technical filename, or database pagination.

## 2. How Does String.compareTo Compare UTF-16?

Under the Java 17 contract, **String.compareTo(String anotherString)** compares two strings lexicographically by **char** values (UTF-16 units), from left to right.

- At the first position where two chars differ, the result is based on the difference of their values.
- If one string is an exact prefix of the other, the shorter string comes first.
- A return value **less than 0**, **equal to 0**, or **greater than 0** indicates before, equal, or after.
- The method does not consult **Locale**, does not automatically lowercase, is not language-aware, and does not normalize Unicode.
- For characters outside the BMP, a single code point can consist of **two surrogate chars**, so UTF-16 order is not necessarily the same as numerical Unicode code point order.

Example:

~~~text
'Z' = U+005A = 90
'a' = U+0061 = 97

"Z".compareTo("a") = 90 - 97 = -7
~~~

That result is correct according to technical rules. However, in a dictionary, readers usually expect A and a to be grouped near each other rather than having all uppercase letters separated from all lowercase letters.

### 2.1. Program with Exact Stdout

**File RawCompareDemo.java**

~~~java
import java.text.Normalizer;

public class RawCompareDemo {
    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Z-before-a="
                + ("Z".compareTo("a") < 0));

        System.out.println("file10-before-file2="
                + ("file10".compareTo("file2") < 0));

        System.out.println("raw-equal="
                + precomposed.equals(decomposed));

        String n1 = Normalizer.normalize(
                precomposed, Normalizer.Form.NFC);
        String n2 = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC-equal=" + n1.equals(n2));
        System.out.println("Z-vs-a=" + "Z".compareTo("a"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RawCompareDemo.java
java RawCompareDemo
~~~

Stdout:

~~~text
Z-before-a=true
file10-before-file2=true
raw-equal=false
NFC-equal=true
Z-vs-a=-7
~~~

**Explanation:** the number 10 starts with the character **1**, which is less than **2**, so String.compareTo places file10 before file2. The precomposed **é** string and the **e + combining acute accent** string have different code units, so equals returns false. NFC normalization brings them to a canonical equivalent form. However, **NFC still does not define dictionary order**; it only resolves differences at the Unicode representation level.

### 2.2. compareTo Does Not Compare by Unicode Code Point in All Cases

String uses UTF-16, so a code point such as U+1F600 requires a surrogate pair. Meanwhile, U+E000 is a BMP code point represented by a single char. Numerical code point order would place U+E000 before U+1F600, but the high surrogate value U+D83D is less than U+E000, so String.compareTo's char-based comparison can give the opposite order.

This reminds us that **compareTo ordering is a specific definition on UTF-16**, not a general rule over all Unicode characters. Do not oversimplify it as "comparing by Unicode code," especially with emoji and non-BMP scripts.

## 3. What Does Locale Dictionary Order Require?

A language system can sort by multiple weight levels, not just code units:

1. **Base letters:** the order of letters in the language's alphabet.
2. **Accents and variants:** how accented characters or language-specific letter forms are ordered.
3. **Uppercase/lowercase:** may be a lower-priority difference than base letters.
4. **Letter combinations:** some languages have rules for comparing character sequences.
5. **Punctuation and whitespace:** how apostrophes, hyphens, and word separators are ordered.
6. **Equivalent Unicode forms:** precomposed characters and combining marks.
7. **Locale and rule version:** the same letter can be weighted differently across languages or providers.

For Vietnamese, letters such as **ă, â, đ, ê, ô, ơ, ư** and tone marks cannot be handled merely by taking the value of a single char. For other languages, letters like **ä**, **å**, **ö** also have their own sorting traditions.

**There is no single "international alphabetical order" that applies accurately to every language.** When an interface promises "A–Z", the application must know whose language choice A–Z is interpreted under.

## 4. java.text.Collator Solves the Language Differences

**Collator** is Java's base class for comparing strings according to localized rules.

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);

int result = collator.compare(first, second);
~~~

This is an illustrative snippet inside a method; it requires importing **java.text.Collator**, **java.util.Locale**, and having variables **String first**, **String second**.

**Collator.getInstance(locale)** selects a comparator matching the Locale and data provided by the JDK/provider. The comparison return value is still negative/0/positive, but the relationship is no longer determined by the first differing UTF-16 code unit.

**Key differences:**

| String.compareTo | Collator.compare |
| --- | --- |
| Directly compares UTF-16 chars | Based on collation weights |
| Does not take a Locale | Takes the selected Locale |
| Unaware of language-specific letters and accents | Can distinguish multiple linguistic levels |
| Suitable for technical ordering | Suitable for display lists |
| Order independent of CLDR data | May change across JDK/provider versions |
| Returns 0 when Strings have the same content under compareTo | Can return 0 for two different Strings at the configured strength level |
| Does not automatically sort numbered files naturally | Also does not guarantee numeric natural sort |

**Collator is not a replacement for all language-processing software.** It does not translate text, fix spelling, automatically parse numbers in names, or guarantee prevention of visually spoofing characters.

## 5. Example Sorting Names with vi-VN Collator

**File LocalizedNames.java**

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class LocalizedNames {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        Collator collator = Collator.getInstance(locale);

        List<String> names = new ArrayList<>(List.of(
                "Dung", "đào", "Anh", "Ánh", "an", "Zebra"));

        names.sort(collator::compare);

        names.forEach(System.out::println);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocalizedNames.java
java LocalizedNames
~~~

The program prints the six names sorted according to the vi-VN collation provided by the runtime. **Do not prescribe a single stdout across all Java versions**, because locale rules, fallback behavior, and CLDR/provider data can change. The goal is to use the proper language rule set rather than silently falling back to UTF-16 order.

With Java 17, the expression **collator::compare** can be used wherever a String comparator is accepted. If the list contains non-String elements or nulls, data types and null policies must be handled properly.

### 5.1. Using the User's Resolved Locale

An application can receive a language from a profile, UI preference, or the Accept-Language header. If the header contains multiple entries, it must be parsed, prioritized, and matched against a **list of supported Locales**, rather than treating the raw header as a single language tag.

Example:

~~~java
Locale displayLocale =
        Locale.forLanguageTag("vi-VN");

Collator collator =
        Collator.getInstance(displayLocale);
~~~

Do not use **Locale.setDefault(...)** on the server to switch language per request: it is JVM-wide state and can affect concurrent requests. Passing Locale explicitly is much more predictable.

A list shared across multiple users may require a fixed Locale decided by the organization. In that case, the order might not match every individual's expectation, yet it remains consistent if that is the product contract.

## 6. Strength: Collator Distinction Levels

Collator lets you choose which level of difference is considered significant:

| Level | General meaning |
| --- | --- |
| **Collator.PRIMARY** | Compares fundamental differences in letters/strings per collation |
| **Collator.SECONDARY** | Considers secondary differences, typically including certain accents |
| **Collator.TERTIARY** | Considers tertiary differences, typically including case/variants |
| **Collator.IDENTICAL** | Distinguishes further when all previous levels are equal |

Do not interpret PRIMARY as "strips accents in every language" or TERTIARY as "guaranteed to differ for any two strings with different code points." Specific weight assignments depend on the **locale and data/rule set**.

In common US English, at PRIMARY the letters **A** and **a** are generally treated as equivalent, whereas at TERTIARY they can be distinguished. The pair **cafe** and **café** usually exhibits a secondary difference, though this should be verified for the target locale.

### 6.1. Example Observing Strength Levels

**File CollatorStrengthDemo.java**

~~~java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    private static String relation(
            Collator c, String left, String right) {
        int order = c.compare(left, right);
        if (order == 0) return "equal";
        return order < 0 ? "before" : "after";
    }

    public static void main(String[] args) {
        Collator c = Collator.getInstance(Locale.US);
        c.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        c.setStrength(Collator.PRIMARY);
        System.out.println("PRIMARY A/a="
                + relation(c, "A", "a"));

        c.setStrength(Collator.SECONDARY);
        System.out.println("SECONDARY A/a="
                + relation(c, "A", "a"));

        c.setStrength(Collator.TERTIARY);
        System.out.println("TERTIARY A/a="
                + relation(c, "A", "a"));

        System.out.println("raw A/a="
                + "A".compareTo("a"));
    }
}
~~~

Run:

~~~bash
javac CollatorStrengthDemo.java
java CollatorStrengthDemo
~~~

The last line is always **raw A/a=-32** by UTF-16 value. The first three lines **intentionally report the relation decided by the current collation set**, typically equal at PRIMARY/SECONDARY, and distinct at TERTIARY. If an exact verbatim snapshot is needed, pin the target JDK and provider.

**Never write conditions checking for Collator results equal to -1 or +1**. Only check negative, 0, and positive. A valid comparator may return other negative/positive integers.

### 6.2. Strength Also Affects Comparator Equality

If **compare(a,b) == 0**, Collator treats the two values as equal at the active configuration level. That does not mean **a.equals(b)** is true. The two checks serve different contracts.

Therefore, do not use low strength as a mechanism to assert that two user profiles are the same; some accent/case differences may be collapsed intentionally for sorting.

## 7. Decomposition: Dictionary Order and Unicode Representation

The letter **é** can be written in two forms:

~~~text
U+00E9        precomposed é
U+0065 U+0301 e + COMBINING ACUTE ACCENT
~~~

Two Strings can look identical, yet **String.equals** and **String.compareTo** do not automatically treat them as identical. This is **canonical equivalence**, which is distinct from dictionary order.

Collator has three decomposition options:

| Mode | Role |
| --- | --- |
| **Collator.NO_DECOMPOSITION** | Performs no decomposition step prior to comparison |
| **Collator.CANONICAL_DECOMPOSITION** | Performs canonical decomposition per Unicode rules during collation |
| **Collator.FULL_DECOMPOSITION** | Allows broader compatibility decomposition |

Configuration example:

~~~java
Collator collator = Collator.getInstance(locale);
collator.setStrength(Collator.TERTIARY);
collator.setDecomposition(
        Collator.CANONICAL_DECOMPOSITION);
~~~

The snippet above uses an existing locale variable. **Strength** is the collation distinction level; **decomposition** is how Unicode representations are handled. They are not two names for the same option.

### 7.1. Normalizer Does Not Replace Collator

**Normalizer.normalize(s, Form.NFC)** transforms a string to its canonical composed form, so two equivalent encodings can be compared using equals after normalization.

**Collator.compare(s,t)** applies linguistic weights according to the Locale and configuration. A PRIMARY Collator may consider two non-canonically-equivalent strings equal in order; NFC cannot do that.

~~~java
String a = "\u00E9";
String b = "e\u0301";

boolean equalAfterNFC =
        Normalizer.normalize(
                a, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(
                b, Normalizer.Form.NFC));
~~~

This is an illustrative snippet requiring import of **java.text.Normalizer**, placed inside a method. **equalAfterNFC** is true. However, this conclusion only speaks to Unicode canonical equivalence, not where that letter sits in a Vietnamese or French dictionary.

**FULL_DECOMPOSITION is not the best default option for all data.** Compatibility decomposition can collapse character forms that carry presentation or semantic differences, such as certain ligatures and fullwidth characters. Determine requirements before using it.

## 8. Vietnamese Accented Letters Expose compareTo Limitations

Vietnamese has letters and mark combinations such as **ă, â, đ, ê, ô, ơ, ư** and tone marks. Some characters are independent letters in the alphabet, while others are combinations of multiple code points depending on encoding.

If comparing only UTF-16 values:

- Precomposed and decomposed forms may sort differently.
- Uppercase and lowercase letters may be split into two large groups.
- Accented letters are not guaranteed to be placed next to base letters according to dictionary rules.
- Names differing by multiple characters may have their order decided at a Unicode code point completely unrelated to semantics.

A test dataset should include:

~~~text
An
Anh
Ánh
ân
ăn
Đào
Dung
Dũng
Thu
Thúy
Tú
Từ
~~~

This is **input** data, not a pre-asserted dictionary ordering table. Run the vi-VN Collator on your supported JDK and cross-check against your product's actual conventions.

Specialized applications such as libraries, linguistic databases, or academic dictionaries may need custom collation tailoring. The JDK's default locale is a good starting point, but it does not automatically guarantee compliance with every domain-specific classification standard.

## 9. compareToIgnoreCase Is Also Not Equivalent to Collation

**String.compareToIgnoreCase** and **String.CASE_INSENSITIVE_ORDER** handle part of uppercase/lowercase differences through Java's case rules. They do **not** automatically apply dictionary ordering for vi-VN, sv-SE, or tr-TR.

Important limitations:

1. No Locale parameter to select a dictionary rule set.
2. Does not map all accents/letter structures to the appropriate weights of each language.
3. Not a full Unicode case folding operation for all strings.
4. Does not automatically perform canonical Unicode normalization.
5. Does not sort numbers inside labels by numeric value.

Calling **toLowerCase(Locale.ROOT)** before comparing can be part of a *search key* under a specific contract, but it does not automatically turn the result into proper collation. Lowercasing also has language-specific behaviors, such as the **I/i** letters in Turkish.

**Sorting**, **fuzzy searching**, and **identity comparison** must be designed separately.

## 10. CollationKey for Repeated Comparisons

**java.text.CollationKey** represents a key for comparing strings under a specific Collator. If a large list needs to be sorted with many repeated comparisons, precomputing keys can be helpful.

~~~java
Collator collator = Collator.getInstance(locale);

CollationKey firstKey =
        collator.getCollationKey(first);
CollationKey secondKey =
        collator.getCollationKey(second);

int result = firstKey.compareTo(secondKey);
~~~

This illustrative snippet requires importing **Collator**, **CollationKey**, **Locale**, along with variables **locale**, **first**, **second**. Only compare keys created with the **same rule set/configuration**: Locale, strength, decomposition, and related provider.

### 10.1. Example Sorting with CollationKey

**File CollationKeyDemo.java**

~~~java
import java.text.CollationKey;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CollationKeyDemo {
    record Item(String text, CollationKey key) {}

    public static void main(String[] args) {
        Collator col = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        col.setStrength(Collator.TERTIARY);
        col.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        List<String> names = List.of(
                "Dung", "Dũng", "Ánh", "Anh", "Đào");

        List<Item> items = new ArrayList<>();
        for (String name : names) {
            items.add(new Item(
                    name, col.getCollationKey(name)));
        }

        items.sort(Comparator
                .comparing(Item::key)
                .thenComparing(Item::text));

        items.forEach(item ->
                System.out.println(item.text()));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CollationKeyDemo.java
java CollationKeyDemo
~~~

The program prints the five names ordered by the keys of the available vi-VN collation set. **thenComparing(Item::text)** is used to determine secondary order by raw String if two collation keys are equal. Because name ordering depends on the JDK's locale data, no fixed stdout is specified across all environments.

**Do not store CollationKeys permanently in a database and assume they remain valid after JDK/CLDR upgrades.** If physical keys are used for an index, there must be a proper versioning and rebuild policy. Nor should keys generated under two different Locales/strengths be mixed.

## 11. TreeSet, TreeMap, and the Risk of Comparator Returning 0

This is a very important practical consequence. **TreeSet** and **TreeMap** rely on **comparator equality**, not solely on String.equals.

~~~java
import java.text.Collator;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class CollatedSetExample {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);

        Set<String> names =
                new TreeSet<>(collator::compare);

        names.add("A");
        names.add("a");

        System.out.println(
                "rawEqual=" + "A".equals("a"));
        System.out.println(
                "collationEqual=" +
                (collator.compare("A", "a") == 0));
        System.out.println("size=" + names.size());
    }
}
~~~

Save **CollatedSetExample.java**, compile with **javac CollatedSetExample.java**, and run with **java CollatedSetExample**. With a typical en-US rule set at PRIMARY, **rawEqual=false**, **collationEqual=true**, and **size=1**. This illustrates the difference between **data identity** and **comparator equality**, not a recommendation to use a PRIMARY TreeSet to deduplicate user data.

**When using TreeMap**, inserting a new key whose compare == 0 with an existing key can update the value of the same entry. If the code treats two names differing in case or accent as two distinct entities, data may be lost or overwritten unintentionally.

To preserve every entity:

- Use a separate **business ID** as the identity key.
- Sort display names with Collator for presentation purposes.
- For a TreeSet containing distinct Strings, use a comparator with a **tie-breaker** that returns 0 only when raw Strings are genuinely equivalent per policy.
- Do not change the comparator's strength after a SortedSet/SortedMap already contains data, because the ordering relation could change.

## 12. Tie-Breaker and Stable Total Ordering

In a UI, two strings can be equal under Collator at the active strength. Some sorts like **List.sort** are **stable sorts**, so comparator-equal elements preserve their initial relative order. However, if data comes from a database, paginated API, or multiple sources, input order is not always stable.

A two-level comparator:

~~~java
Comparator<String> order = (left, right) -> {
    int localized = collator.compare(left, right);
    if (localized != 0) {
        return localized;
    }
    return left.compareTo(right);
};
~~~

This illustrative snippet sits inside a method, requiring import of **Comparator** and a configured Collator variable. The first level uses locale collation; the second level resolves only collation-equivalent cases using UTF-16 order.

**Pros:** avoids completely different Strings being treated as the same key simply due to low strength; produces a predictable secondary order.

**Cons:** the secondary order is non-linguistic; this is acceptable if it only applies to items already equal under linguistic rules. If business logic wants two names to be treated as the same key, do not add a tie-breaker and inadvertently alter the equality policy.

For a list of objects, use an **immutable ID** as the secondary order:

~~~java
records.sort(Comparator
        .comparing(Record::getDisplayName, collator::compare)
        .thenComparing(Record::getId));
~~~

This is **illustrative code**, not a standalone program: it requires a project-defined Record class with getDisplayName/getId, along with variables records and collator. Do not copy it without the corresponding types and methods.

## 13. Natural Sorting Is Not Implicit in Collator

In a file list:

~~~text
file1
file2
file10
file20
~~~

users usually want **file2** before **file10** because numerically 2 is less than 10. Yet String.compareTo puts **file10** before **file2**, because at the first differing position the character **1** is less than **2**.

**Locale collation does not mean natural/numeric sorting.** Java Core's java.text.Collator API has no global contract guaranteeing recognition of arbitrary digit sequences in names to compare them by numeric value.

If the product needs numeric ordering:

1. Define how letters and digits are tokenized.
2. Handle numbers with leading zeros: **file2** vs **file02**.
3. Handle numbers too large to fit in int/long.
4. Specify which Unicode digit characters are accepted.
5. Handle labels with multiple numeric segments, dots, versions, and suffixes.
6. Test transitivity and consistency of the custom comparator.

Do not try to solve this by calling **Integer.parseInt** on the whole filename; it cannot handle mixed data. For versions **1.10** vs **1.2**, the rules differ again and may require a dedicated version parser.

## 14. Collation, Search, and Normalization Are Three Different Decisions

The needs:

- "Which name comes first?" is **sorting**.
- "Does typing anh find Ánh?" is **matching/search**.
- "Do e+acute and é have the same Unicode content?" is **canonical equivalence**.
- "Do two names represent the same account identifier?" is **identity/uniqueness**.

All of these can involve Locale/Unicode, but do not use the same function and assume they are equivalent.

For example, a PRIMARY Collator may treat certain secondary-level accents as insignificant. However, one must not claim "PRIMARY strips all accents in every language." Letters like **đ** or other letter forms may be treated as distinct letters by language rules.

For search requiring accent-insensitivity, you may need to build a separate search key or use a language-aware search engine. **Do not overwrite translated originals or personal names** just for flexible searching.

## 15. Collator, JDK Versions, and CLDR Data

**Collator.getInstance(locale)** relies on data and rules supported by the runtime. Therefore:

- Results may change when updating the JDK or provider.
- Partially supported locales may fall back via the runtime's fallback mechanism.
- Strength and decomposition alter comparison rules even when the two strings do not change.
- Rules for Vietnamese or other languages may include special tailoring.
- A specialized ordering (library, academic dictionary, legal records) may require a versioned sorting standard different from default rules.

**Do not write snapshot tests asserting an absolute locale order without specifying the JDK/provider.** You can test API properties and run the locale dataset on the runtimes actually deployed. If an organization requires an order invariant over many years, specify the version of the collation rule set, not just the Locale.

### 15.1. Backend, Database, and Client May Sort Differently

A database has its own collation, such as the engine's ORDER BY rules. Java Collator and database collation may not agree. If the backend paginates under one order and the client re-sorts each page with a different Collator, the list is no longer globally sorted:

~~~text
Database sorts all records and splits into pages
       |
       v
Client only re-sorts within each page
       |
       v
No guarantee the whole list matches the client's desired order
~~~

The solution is to pick one source that determines the order of **the entire dataset** before pagination, or use rule sets verified to be compatible on both sides. When names tie at the collation level, use an ID tie-breaker so pagination stays consistent.

Do not store/copy a Java CollationKey into a database and assume another engine will understand the same rules.

## 16. Nulls, Empty Strings, Punctuation, and Emoji

When data can contain null, define whether null comes first or last. Do not leave it to Collator:

~~~java
Comparator<String> order =
        Comparator.nullsLast(collator::compare);
~~~

This illustrative snippet uses an import of **Comparator** and a collator variable. For lists containing empty Strings or names starting with hyphens, apostrophes, spaces, or emoji, sorting rules can vary by locale.

Some notes:

- Normalizer does not automatically strip control characters and is not a tool for detecting all invisible characters.
- Visually identical strings can be different code points belonging to different scripts.
- A Comparator is not responsible for validating whether input is safe.
- Do not arbitrarily mutate original data with trim/replace/lowercase just to sort.
- With multi-script mixed data, test actual names from the product.

If the UI needs nullsFirst, use **Comparator.nullsFirst(...)**. Choose a clear policy rather than relying on exceptions or defaults of data classes.

## 17. Performance and Concurrency Safety

**String.compareTo** is usually cheap because it compares code units directly. **Collator** may need to look up multiple linguistic weights; **CollationKey** can help when a large list requires many repeated comparisons.

However, creating CollationKeys, storing keys, and building intermediate lists all consume memory/CPU. Before optimizing, measure timings on realistic data. For small lists, clear code is usually more important than caching techniques.

**Collator is a mutable stateful object**, holding strength and decomposition. Do not share a single instance and call setters on it while other requests are comparing. One strategy is to create a Collator per request/operation or make a separate copy per thread (cloning a template configuration when appropriate and tested).

**Do not modify a Comparator mid-sort or while a TreeMap already holds data.** A Comparator must maintain consistent ordering and transitivity; if strength changes during comparisons, algorithms may behave unexpectedly or fail.

## 18. Suitable Test Suite for Java 17+

Recommended checks:

| Scenario | What to verify |
| --- | --- |
| Z and a | compareTo depends on UTF-16 codes, not dictionary order |
| file10 and file2 | Lexicographic differs from natural sort |
| Precomposed é and e+acute | Raw equality differs from canonical equivalence |
| A/a under Collator PRIMARY/TERTIARY | Strength changes relation per rule set |
| Names with ă, â, đ, ê, ô, ơ, ư | vi-VN rules on the target JDK |
| Locale.US vs vi-VN | Locale is passed explicitly, not implicitly using default |
| Collator decomposition | Canonical forms have an explicit policy |
| TreeSet and TreeMap | No unintended key loss |
| CollationKey | Only compare keys with matching configuration |
| ID tie-breaker | Preserves order when names tie under collation |
| Names with null, punctuation, emoji | Explicit policy exists |
| JDK/CLDR upgrade | Detect when collation rule sets change |
| Backend and database | Full list and pagination remain consistent |

### 18.1. Testing Comparator Properties

For custom comparators:

1. **Antisymmetry of sign:** if a comes before b, then b comes after a.
2. **Transitivity:** if a before b and b before c, then a before c.
3. **Consistency when returning 0:** a and b are treated as equivalent when compared against c.
4. **No configuration change during comparisons:** the same input pair yields one relation within a sort pass.
5. **Intentional tie-breaker:** collation-equal names do not drop distinct entities.
6. **No side effects:** comparator does not mutate names or global Locale.

Especially when writing a natural comparator, test many combinations of long numbers, leading zeros, and multiple alphanumeric segments; a non-transitive comparator can cause hard-to-diagnose sort failures.

### 18.2. Avoid Unnecessary Verbatim Assertions

Pure Java properties such as **"Z".compareTo("a") == -7** are stable. However, the order of a long Vietnamese list under Collator can be subject to differing locale data. Distinguish which tests verify the Java API and which tests verify the rule set chosen by the product.

If exact per-result matching is required in CI, specify the JDK/provider version—for example, running on the same runtime packaged for production.

## 19. Common Mistakes

### Mistake 1: Using Collections.sort(names) for UI Lists

Omitting a comparator means sorting Strings with compareTo, with no locale collation at all. Switch to a locale-appropriate Collator if the product requires localized dictionary ordering.

### Mistake 2: Using compareToIgnoreCase and Calling It Done

Ignoring case does not replace rules for accents, digraphs, and language-specific letter order. An appropriate Collator is needed.

### Mistake 3: Using Zero-Arg Collator.getInstance() on the Server

The JVM's default locale may differ from the user's language. Pass the locale explicitly.

### Mistake 4: Using PRIMARY for Data Identity

Two distinct strings may return compare == 0 under a locale; do not use a UI comparator as a uniqueness criterion without an explicit policy.

### Mistake 5: Assuming Collator Returning 0 Means String.equals Is Also True

Collation equality and UTF-16 equality are two different relations. TreeSet/TreeMap will rely on the comparator.

### Mistake 6: Mixing CollationKeys Across Locales

Keys should only be compared when generated under the same Collator configuration. Do not use keys from two different rule systems to build a combined order.

### Mistake 7: Persisting CollationKeys Forever

Keys can lose meaning when changing JDK/provider. If persisted, versioning and rebuilding are required.

### Mistake 8: Expecting file2 Before file10 Using Only Collator

Natural/numeric ordering is an additional requirement; it must be handled explicitly.

### Mistake 9: Using NFC as a Replacement for Dictionary Order

Normalizer unifies Unicode representation; it does not determine dictionary position. Nor do NFD/NFC strip accents automatically.

### Mistake 10: Using Raw compareTo for All Scripts

UTF-16 order has no dictionary knowledge of individual languages, especially when content contains accents, non-BMP characters, or multiple scripts.

### Mistake 11: Sorting Each Page Separately in the UI

If the server paginates by another rule, client-side sorting per page cannot produce a correct global order. Sort at the layer that determines pagination.

### Mistake 12: Changing Strength After a SortedSet Is Built

Changing the comparator's ordering can break lookup and add/remove behavior in the existing structure. Configure the comparator before populating the collection.

### Mistake 13: Sharing a Mutable Collator and Mutating It per Request

Different requests can interfere with each other's configuration. Create separate instances or isolate them.

### Mistake 14: Assuming Collator Rules Are Immutable Across All JDK Releases

Language data can be updated. For a fixed sorting contract, control the rule set version or thoroughly test changes.

## 20. Production Checklist

- [ ] Determine whether the requirement is technical order, locale-aware sort, or natural/numeric sort.
- [ ] Do not assume String.compareTo is the user's dictionary order.
- [ ] Resolve Locale from a supported list; do not implicitly take the JVM default.
- [ ] Use Collator.getInstance(locale) when sorting names/language text.
- [ ] Understand PRIMARY, SECONDARY, TERTIARY, and IDENTICAL.
- [ ] Understand NO_DECOMPOSITION, CANONICAL_DECOMPOSITION, and FULL_DECOMPOSITION.
- [ ] Separate canonical normalization from collation and search matching.
- [ ] Determine whether comparator equality is appropriate for TreeSet/TreeMap.
- [ ] Add a String or ID tie-breaker when an explicit total order is needed.
- [ ] Do not compare CollationKeys from different configurations.
- [ ] Do not share/mutate a mutable Collator across threads without protection.
- [ ] Test Vietnamese names with full tone marks and special letters.
- [ ] Test precomposed characters and combining marks.
- [ ] Test numbers in labels, nulls, emoji, punctuation, and multi-script data.
- [ ] Align sorting rules across Java, database, backend, and client when paginating.
- [ ] Check JDK/provider/CLDR on upgrades to catch collation differences.
- [ ] Preserve the original text and use a business ID instead of treating displayName as an identity key.

## 21. Summary

**String.compareTo is not equivalent to locale dictionary order** because it directly compares **UTF-16 char** units without considering language, letter weights, accents, case, or locale-specific sorting traditions. It is suitable for technical ordering, but should not be the default choice for user-facing lists of names and labels.

For language-aware sorting, use **Collator.getInstance(locale)**, choose strength and decomposition deliberately, test on the target JDK/provider, and add a tie-breaker when needed. **Normalizer** handles Unicode representation equivalence, **CollationKey** can help optimize repeated comparisons, while **natural sorting** is a separate problem. A sound design separates display order, search, identity checking, and pagination sorting.