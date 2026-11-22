# Limits of Casting from NumberFormat to DecimalFormat in Java

`java.text.NumberFormat` is an abstract class for **locale-aware number formatting and parsing**. `java.text.DecimalFormat` is a concrete subclass adding patterns, decimal/grouping symbol sets, `BigDecimal` parsing support, prefixes/suffixes, and many dedicated configurations. When obtaining a `NumberFormat` from a factory, developers often want to cast it to `DecimalFormat` to use those features. Yet **not every `NumberFormat` is a `DecimalFormat`**, and Java **does not promise** all factories return that subclass.

The golden rule: **only cast when the object is genuinely a `DecimalFormat`**, verified with `instanceof`; if the needed functionality already exists on `NumberFormat`, **do not cast at all**. If an application strictly requires patterns and `DecimalFormat`-specific methods, you can **instantiate `DecimalFormat` explicitly with matching `DecimalFormatSymbols`**, while understanding how it differs from a factory-chosen formatter.

This lesson targets **Java 17+**, demonstrating compile errors, `ClassCastException`, pattern matching for `instanceof`, the `CompactNumberFormat` case, locale provider dependencies, and safe design choices.

## 1. Inheritance does not mean casting is always valid

Hierarchy of related classes:

```text
java.lang.Object
    └── java.text.Format
           └── java.text.NumberFormat (abstract)
                  ├── java.text.DecimalFormat
                  ├── java.text.CompactNumberFormat
                  └── java.text.ChoiceFormat
                       (+ other subclasses/providers)
```

There are two directions:

- **Upcast** (subclass → superclass): `NumberFormat f = new DecimalFormat();`, allowed by Java and safe. The actual object remains a `DecimalFormat`, only the reference variable has a broader type.
- **Downcast** (superclass → subclass): `DecimalFormat d = (DecimalFormat) f;`, succeeds only when the actual object inside `f` is a `DecimalFormat` or a subclass of it. Otherwise, the JVM throws `ClassCastException`.

You cannot deduce the actual object type solely from a `NumberFormat` variable declaration. A reference of the same type may point in turn to a `DecimalFormat`, a `CompactNumberFormat`, a `ChoiceFormat`, or a subclass implemented by a service provider.

**Distinguishing declared type from runtime type:**

```java
// Illustrative snippet; requires importing java.text.*.
NumberFormat number = new DecimalFormat("0.00"); // upcast
boolean ok = number instanceof DecimalFormat;   // true

NumberFormat choice = new ChoiceFormat(
        new double[] {0, 1},
        new String[] {"zero", "one or more"});
boolean notDecimal = choice instanceof DecimalFormat; // false
```

`number` and `choice` both have declared type `NumberFormat`. Yet they belong to **two different subclasses**. Java does not "convert" one formatter into another when you cast: casting only **checks the runtime type** and returns a narrower-typed reference if the check passes.

## 2. Why NumberFormat factories do not guarantee DecimalFormat

Common factories:

```java
NumberFormat number = NumberFormat.getNumberInstance(locale);
NumberFormat general = NumberFormat.getInstance(locale);
NumberFormat currency = NumberFormat.getCurrencyInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
NumberFormat integer = NumberFormat.getIntegerInstance(locale);
NumberFormat compact = NumberFormat.getCompactNumberInstance(
        locale, NumberFormat.Style.SHORT);
```

This is a **fragment**: the `locale` variable must be a declared `Locale`, and `import java.text.NumberFormat;` is required.

These methods have a **declared return type of `NumberFormat`**, allowing the JDK to choose an appropriate implementation based on formatting style, locale, locale data, and service providers (`NumberFormatProvider`). On many standard JDK builds, regular number/currency/percent factories often return `DecimalFormat`. However, that is **not a contract an application should rely on unconditionally**.

Notably, since Java 12 there is `getCompactNumberInstance(...)` for compact forms such as thousands/millions. Its standard implementation uses `CompactNumberFormat` — a **different subclass** of `NumberFormat` that **does not extend `DecimalFormat`**. Furthermore, locale service providers may return other suitable subclasses.

Oracle's `DecimalFormat` documentation advises checking the type before using its specialized features. Hence, the advice "just cast it, with Locale.US it's definitely fine" is not a portable coding principle.

### Three layers to remember

| Layer | What we know for sure | What not to assume |
| --- | --- | --- |
| **Compile-time** | Factory declares return type `NumberFormat` | No implicit assignment to `DecimalFormat` |
| **Runtime** | `instanceof` and cast check the object's real class | Not every `NumberFormat` object is a `DecimalFormat` |
| **Implementation/locale** | Factory finds a formatter fitting the environment | A specific class cannot be guaranteed across all JDKs/providers |

**`getClass().getName()`** can be used to diagnose the runtime class, but never compare class names to decide casting: `instanceof DecimalFormat` is what is type-system sound, including for subclasses of `DecimalFormat`.

## 3. Compile-time errors vs. runtime errors

The following **does not compile**:

```java
// INVALID: the factory's return type is NumberFormat.
DecimalFormat bad = NumberFormat.getNumberInstance(Locale.US);
```

The compiler is not allowed to implicitly assign a value of parent type `NumberFormat` into a variable of child type `DecimalFormat`. Adding a cast:

```java
// Compiles; runtime still depends on the actual class.
DecimalFormat maybe =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
```

merely **defers checking to runtime**. When the factory returns a different subclass, this statement throws `ClassCastException`.

The risk rises when environments use different locale providers, different JDKs/vendors, or later code switches from `getNumberInstance` to `getCompactNumberInstance` while leaving the old cast intact.

### Example guaranteed to produce ClassCastException without provider dependence

Save **`CastFailureDemo.java`**:

```java
import java.text.ChoiceFormat;
import java.text.DecimalFormat;
import java.text.NumberFormat;

public class CastFailureDemo {
    public static void main(String[] args) {
        NumberFormat number = new ChoiceFormat(
                new double[] {0, 1},
                new String[] {"zero", "one or more"});

        System.out.println("NumberFormat: "
                + (number instanceof NumberFormat));
        System.out.println("DecimalFormat: "
                + (number instanceof DecimalFormat));

        try {
            DecimalFormat decimal = (DecimalFormat) number;
            System.out.println(decimal.format(2));
        } catch (ClassCastException exception) {
            System.out.println("Cast failed: ClassCastException");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CastFailureDemo.java
java CastFailureDemo
```

Stdout:

```text
NumberFormat: true
DecimalFormat: false
Cast failed: ClassCastException
```

This example **intentionally creates a non-DecimalFormat formatter**, without needing to guess which provider is installed. `ChoiceFormat` is still a `NumberFormat`, yet casting across to a sibling class (`DecimalFormat`) is invalid. Catching `ClassCastException` illustrates the error; it is **not** a recommendation to use exceptions for control flow in ordinary code.

## 4. Safest approach: instanceof with Java 17 pattern matching

Since Java 16, **pattern matching for `instanceof`** can declare a type-checked variable inside the `if` branch. Java 17 supports this syntax natively:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.US);

if (formatter instanceof DecimalFormat decimal) {
    decimal.setDecimalSeparatorAlwaysShown(true);
    System.out.println(decimal.format(100));
} else {
    System.out.println(formatter.format(100));
}
```

This is a **fragment inside a method**, requiring `import java.text.NumberFormat;`, `DecimalFormat;`, and `java.util.Locale;`. No fixed stdout is asserted for this snippet as a whole: if the object is a `DecimalFormat`, the decimal separator is forced to appear; otherwise, the code uses `NumberFormat`'s common capabilities.

Equivalent pre-Java 16 syntax:

```java
if (formatter instanceof DecimalFormat) {
    DecimalFormat decimal = (DecimalFormat) formatter;
    decimal.setDecimalSeparatorAlwaysShown(true);
}
```

The `if` branch proves that the cast inside the branch operates on **the exact same object** that was checked. Calling the factory a second time and casting the new object gives no guarantee from the earlier check:

```java
// Do not check one object and then cast a new object.
if (formatter instanceof DecimalFormat) {
    // Do not assume the following factory result is guaranteed to have the same subtype:
    // DecimalFormat other = (DecimalFormat)
    //         NumberFormat.getNumberInstance(Locale.US);
}
```

Keep the formatter in one variable, check once, and operate on that same object.

### Complete program: supporting both branches

Save **`SafeFactoryDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class SafeFactoryDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);

        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        if (formatter instanceof DecimalFormat decimal) {
            decimal.setDecimalSeparatorAlwaysShown(true);
            System.out.println("Decimal-specific settings applied");
        } else {
            System.out.println("Using NumberFormat fallback");
        }

        System.out.println("Formatted value: "
                + formatter.format(1234.5));
    }
}
```

```bash
javac -encoding UTF-8 SafeFactoryDemo.java
java SafeFactoryDemo
```

The program always prints two lines, though there is **no single invariant stdout** across all JDKs/providers. With the standard `DecimalFormat` implementation for `Locale.US`, the two lines are typically:

```text
Decimal-specific settings applied
Formatted value: 1,234.50
```

If the factory returns another subclass, the `else` branch still runs and formats the number via `NumberFormat`; the string follows that provider's rules. Never use `formatter.getClass() == DecimalFormat.class`: a class **extending `DecimalFormat`** can also be validly cast, yet exact class equality rejects it.

## 5. When only NumberFormat features are needed, do not cast

`NumberFormat` already provides many methods for common tasks:

| Need | API available on NumberFormat |
| --- | --- |
| Format numbers | `format(long)`, `format(double)`, `format(Object)` |
| Parse numbers from strings | `parse(String)` |
| Toggle thousands grouping | `setGroupingUsed(boolean)` |
| Min/max integer digits | `setMinimumIntegerDigits(int)`, `setMaximumIntegerDigits(int)` |
| Min/max fractional digits | `setMinimumFractionDigits(int)`, `setMaximumFractionDigits(int)` |
| Limit parsing to integer part | `setParseIntegerOnly(boolean)` |
| Currency unit (if supported by implementation) | `setCurrency(Currency)` |
| Rounding mode (if supported by implementation) | `setRoundingMode(RoundingMode)` |

Write code against the required capability interface rather than coupling to a concrete class.

**Important note on support:** just because a method is *declared* on `NumberFormat` does not mean every subclass implements it. For instance, `NumberFormat.setRoundingMode` in the base class throws `UnsupportedOperationException`; subclasses supporting rounding modes must override it. Likewise, `setCurrency` in the base class may not be supported by default. Thus, "no cast needed" does not mean "every setting is guaranteed by every provider." If a feature is critical, verify the implementation's behavior/capabilities or select a known concrete object.

**Standalone runnable program — `BaseApiDemo.java`**:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class BaseApiDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);

        formatter.setGroupingUsed(false);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        System.out.println("Min fraction: "
                + formatter.getMinimumFractionDigits());
        System.out.println("Max fraction: "
                + formatter.getMaximumFractionDigits());
        System.out.println("Value: "
                + formatter.format(12.5));
    }
}
```

```bash
javac -encoding UTF-8 BaseApiDemo.java
java BaseApiDemo
```

With the JDK's standard number implementation for `Locale.US`, the output is:

```text
Min fraction: 2
Max fraction: 2
Value: 12.50
```

The advantage is that code continues using shared capabilities even if a factory changes subtypes. If you only need up to two decimal places and grouping, **do not cast just to call setters already present on `NumberFormat`**.

## 6. DecimalFormat-only features that require checking the subtype

`DecimalFormat` provides methods absent from `NumberFormat`:

| Advanced need | DecimalFormat API | Note |
| --- | --- | --- |
| Apply non-localized pattern | `applyPattern("#,##0.00")` | Standard `.`/`,` pattern syntax; display symbols come from symbols/locale |
| Export current pattern | `toPattern()` | Do not use as a stable ID or business rule |
| Apply localized pattern | `applyLocalizedPattern(...)` | Pattern symbols must match current symbols |
| Adjust separators and digits | `getDecimalFormatSymbols()`, `setDecimalFormatSymbols(...)` | Be aware of impact on grouping, currency, negatives |
| Always print decimal separator | `setDecimalSeparatorAlwaysShown(true)` | E.g., an integer can become `100.` |
| Grouping size | `setGroupingSize(int)` | DecimalFormat-specific detail |
| Prefix/suffix | `setPositivePrefix(...)`, `setNegativeSuffix(...)` | Can change how negative signs are indicated |
| Opt into BigDecimal parsing | `setParseBigDecimal(true)` | Useful for decimal parsing with decimal precision |
| Multiplier | `setMultiplier(int)` | Can change numeric meaning (like percent) |

If you only want `setParseBigDecimal(true)`, never write:

```java
// DOES NOT COMPILE because NumberFormat does not declare setParseBigDecimal.
NumberFormat nf = NumberFormat.getNumberInstance(Locale.US);
nf.setParseBigDecimal(true);
```

To use it, you must have a variable the compiler knows is `DecimalFormat`, via `instanceof` or `new DecimalFormat(...)`.

### Type-checked example: configuring BigDecimal parsing

```java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
if (number instanceof DecimalFormat decimal) {
    decimal.setParseBigDecimal(true);
    // From here use decimal.parse(...) according to the input validation policy.
} else {
    // Another subclass: do not assume it shares the same BigDecimal parsing mechanism.
}
```

This is a **fragment**, not a full program. In real usage, `DecimalFormat.parse(String)` may not consume the entire input string. When validation is needed, use `ParsePosition` and confirm `pos.getIndex() == input.length()` along with appropriate `pos.getErrorIndex()`, in addition to range and scale checks.

## 7. The CompactNumberFormat case: a real subclass that is not DecimalFormat

`CompactNumberFormat` is used for locale-aware compact formatting. It is a **subclass of `NumberFormat`**, not a subclass of `DecimalFormat`. The factory `NumberFormat.getCompactNumberInstance(locale, style)` is designed for compact forms.

Program **`CompactTypeDemo.java`**:

```java
import java.text.CompactNumberFormat;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class CompactTypeDemo {
    public static void main(String[] args) {
        NumberFormat compact =
                NumberFormat.getCompactNumberInstance(
                        Locale.US, NumberFormat.Style.SHORT);

        if (compact instanceof DecimalFormat) {
            System.out.println("DecimalFormat implementation");
        } else if (compact instanceof CompactNumberFormat) {
            System.out.println("CompactNumberFormat implementation");
        } else {
            System.out.println("Another NumberFormat implementation");
        }

        System.out.println("Assignable to NumberFormat: "
                + (compact instanceof NumberFormat));
    }
}
```

```bash
javac -encoding UTF-8 CompactTypeDemo.java
java CompactTypeDemo
```

On JDK 17/21 using the standard compact implementation, the classification line is typically `CompactNumberFormat implementation`, followed by:

```text
Assignable to NumberFormat: true
```

The first line can vary if an environment uses a different implementation, so the stdout snippet above quotes only **the second line that always holds**, rather than the full consecutive stdout. This demonstrates why **compact formatters must not be cast to `DecimalFormat`** to call `applyPattern`. Choose specialized APIs of the actual subtype (if needed and appropriate), or use common `NumberFormat` operations.

If a library accepts only `DecimalFormat`, do not try to fake a compact formatter with a cast. Either change the library's interface to accept `NumberFormat`/`Format` if business rules permit, or supply a separately configured `DecimalFormat` while accepting that it is **not equivalent** to compact formatting.

## 8. When you truly need DecimalFormat: instantiate explicitly

If `"#,##0.00"` patterns or `setParseBigDecimal` are mandatory, you can construct the required class directly:

```java
Locale locale = Locale.forLanguageTag("en-US");
DecimalFormat decimal = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(locale));
```

This is a **fragment** requiring `import java.text.DecimalFormat;`, `DecimalFormatSymbols;`, `java.util.Locale;`. No cast is involved. The two-argument constructor lets you control the **pattern** and **locale-specific symbols**.

**Standalone runnable example — `ExplicitDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ExplicitDecimalDemo {
    public static void main(String[] args) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);

        System.out.println(format.format(
                new BigDecimal("12345.678")));
        System.out.println(format.format(
                new BigDecimal("12.5")));
        System.out.println("Parse as BigDecimal: "
                + format.isParseBigDecimal());
        System.out.println("Pattern: " + format.toPattern());
    }
}
```

```bash
javac -encoding UTF-8 ExplicitDecimalDemo.java
java ExplicitDecimalDemo
```

Stdout:

```text
12,345.68
12.50
Parse as BigDecimal: true
Pattern: #,##0.00
```

These results are governed by the **specific pattern**, `Locale.US` `DecimalFormatSymbols`, and `HALF_UP`. Using the explicit constructor is the right choice when you must guarantee the **`DecimalFormat` subtype**, though it will not always preserve every rule provided by locale factories.

### Trade-offs against factories

| Criterion | Factory `NumberFormat.getNumberInstance(locale)` | `new DecimalFormat(pattern, symbols)` |
| --- | --- | --- |
| Declared/return type | `NumberFormat` | Guaranteed `DecimalFormat` |
| Auto-selects locale/provider format style | Yes | No — you choose pattern/digits |
| Can cast to DecimalFormat | Only after `instanceof` | No cast needed |
| Supports DecimalFormat patterns | If subtype matches | Yes |
| Controls symbol rules | By locale/provider | Via `DecimalFormatSymbols` |
| Suitability for locale-standard currency | Usually better from currency factory | Requires configuring pattern/currency and reviewing rules manually |

If you want a **standard localized number format first** and only minor adjustments, prefer the factory and check the subtype. If you want a **mandatory pattern** and do not need to retain every provider formatting choice, instantiate `DecimalFormat` directly with locale symbols. For monetary values, add the business currency code and rounding policy; never assume pattern `"#,##0.00"` renders currency properly in every country.

## 9. A design pattern with an explicit fallback

In production code, if subtype-specific customization is **optional**, keep the provider's formatter:

```java
// Fragment inside a method with NumberFormat, DecimalFormat, Locale imported.
NumberFormat format = NumberFormat.getNumberInstance(locale);
format.setMinimumFractionDigits(2);
format.setMaximumFractionDigits(2);

if (format instanceof DecimalFormat decimal) {
    decimal.setDecimalSeparatorAlwaysShown(true);
}
// Continue formatting via NumberFormat; do not swap in another object just because the cast skipped.
```

If a pattern is **contractually mandatory for display**, there are two deliberate choices:

1. **Need to keep the factory formatter:** require the `DecimalFormat` subtype and throw a meaningful configuration error if unmet; suitable when the app accepts only a controlled set of runtimes/providers.
2. **Allowed to dictate the pattern yourself:** instantiate `new DecimalFormat(pattern, DecimalFormatSymbols.getInstance(locale))`. The app then no longer uses all default formatting rules selected by the factory/provider.

Example builder enforcing the subtype only when mandatory:

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class FormatterFactoryGuard {
    public static DecimalFormat requireDecimal(Locale locale) {
        NumberFormat candidate =
                NumberFormat.getNumberInstance(locale);
        if (candidate instanceof DecimalFormat decimal) {
            return decimal;
        }
        throw new IllegalStateException(
                "DecimalFormat required, got "
                + candidate.getClass().getName());
    }

    public static void main(String[] args) {
        Locale locale = Locale.US;
        NumberFormat format =
                NumberFormat.getNumberInstance(locale);
        System.out.println("NumberFormat available: "
                + (format != null));
        // When the application strictly requires DecimalFormat:
        // DecimalFormat decimal = requireDecimal(locale);
    }
}
```

Save **`FormatterFactoryGuard.java`** and run:

```bash
javac -encoding UTF-8 FormatterFactoryGuard.java
java FormatterFactoryGuard
```

Stdout of `main`:

```text
NumberFormat available: true
```

`requireDecimal` compiles and can be called from other code; `main` intentionally avoids calling the subtype-enforcing method to keep stdout stable across providers. If `requireDecimal` is called and a provider does not return `DecimalFormat`, it throws `IllegalStateException` **with diagnostic details**, rather than letting a cryptic `ClassCastException` emerge from a blind cast. Where the subtype is optional, **do not throw**; simply use the original formatter and common functionality.

## 10. Locale, pattern, and symbol sets: do not conflate them

`DecimalFormatSymbols.getInstance(locale)` supplies symbols such as decimal separator, grouping separator, digits, and minus sign for a locale. With `DecimalFormat("#,##0.00", symbols)`, the pattern uses **non-localized standard syntax symbols**; actual output characters follow `symbols`.

For instance, `"#,##0.00"` with en-US symbols typically yields `1,234.50`; with de-DE it can yield `1.234,50`. Do not write `"#.##0,00"` for de-DE into `applyPattern(...)` assuming Java automatically treats it as German syntax: `applyPattern` accepts **standard convention** patterns. If genuinely processing a **localized pattern**, use `applyLocalizedPattern(...)` and manage `DecimalFormatSymbols` accordingly.

**Especially for currency:** `getCurrencyInstance(locale)` does not merely swap in a `$` sign; it can also pick patterns, grouping, negative signs, and currency conventions. A `new DecimalFormat("#,##0.00", symbols)` does not automatically preserve the factory's currency choices. When monetary formatting is needed, prefer obtaining a currency formatter from the factory, use the common API where sufficient, and customize `DecimalFormat` only after `instanceof`.

**Especially for BigDecimal:** `DecimalFormat` supports formatting and parsing decimals within its capabilities. `NumberFormat` has a general contract, while subclasses can handle `Number` differently; do not assume every subclass preserves `BigDecimal` precision when calling `format(Object)`. Exact monetary calculations belong in the `BigDecimal` business layer; formatters are responsible only for presentation.

## 11. Parsing numbers is not always BigDecimal parsing

`NumberFormat.parse(String)` returns `Number`, without guaranteeing a specific type like `BigDecimal`. Even when the actual object is a `DecimalFormat`, unless `setParseBigDecimal(true)` was called, the parsed value can be `Long` or `Double` depending on content and configuration.

**Standalone runnable example — `ParseBigDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseBigDecimalDemo {
    public static void main(String[] args) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        parser.setParseBigDecimal(true);

        String input = "1,234.50";
        ParsePosition position = new ParsePosition(0);
        Number result = parser.parse(input, position);

        if (result instanceof BigDecimal amount
                && position.getIndex() == input.length()) {
            System.out.println("Parsed: "
                    + amount.toPlainString());
            System.out.println("Type: BigDecimal");
        } else {
            System.out.println("Invalid or incomplete number");
        }
    }
}
```

```bash
javac -encoding UTF-8 ParseBigDecimalDemo.java
java ParseBigDecimalDemo
```

Stdout:

```text
Parsed: 1234.50
Type: BigDecimal
```

The example uses `ParsePosition` to reject trailing characters after the number; depending on input policy, you may also need to validate separators, grouping layout, whitespace, negatives, value range, scale, and Unicode characters. `setParseBigDecimal` only controls `DecimalFormat`'s **parsed value type**; it does not replace validation.

If you only have a `NumberFormat` that is not a `DecimalFormat`, do not force-cast it to `DecimalFormat` just to get `BigDecimal`. Either adopt an explicitly chosen parser, or use the common `parse` API and control conversion per precision policy rather than calling `new BigDecimal(parsed.doubleValue())` carelessly.

## 12. What happens when cloning and passing across layers?

Suppose a service accepts a `NumberFormat` parameter while the caller creates a `DecimalFormat`. Passing it into a method with a `NumberFormat` parameter **does not erase the object's runtime type**; you can still use `instanceof` on the receiving side.

```java
// Fragment inside a Java class (not a standalone file):
static void render(NumberFormat format) {
    if (format instanceof DecimalFormat decimal) {
        decimal.setGroupingSize(3);
    }
    System.out.println(format.format(1234));
}
```

However, mutating **the caller's** formatter inside `render` can cause side effects, especially when the formatter is reused. `NumberFormat`/`DecimalFormat` are **mutable** objects and are not guaranteed thread-safe if shared across concurrent requests. To avoid this, consider passing immutable configuration, creating a fresh formatter per operation, or performing controlled `clone()`/copy before mutating.

That `clone()` on a formatter normally preserves its runtime type is a property of cloning, **not proof** that the original object was a `DecimalFormat`. Do not cast a clone without knowing the actual subtype, and never share mutable formatters across multiple threads without proper synchronization.

For long-term architecture, let the UI layer depend on a narrow interface such as `Function<Number, String>` or `NumberFormat` when sufficient, rather than requiring every service to accept `DecimalFormat`. Only code that genuinely needs `applyPattern` should depend on the concrete class and explicitly handle unsupported branches.

## 13. Design choices by scenario

| Scenario | Recommended approach | Reason |
| --- | --- | --- |
| Display locale numbers, max two fractional digits | Use `NumberFormat.getNumberInstance(locale)`, common setters | No subtype needed |
| Force decimal point on integers | `instanceof DecimalFormat` then `setDecimalSeparatorAlwaysShown(true)`, with fallback | DecimalFormat-specific feature |
| Enforce an exact standard pattern for reports | `new DecimalFormat(pattern, DecimalFormatSymbols.getInstance(locale))` | Guarantees object and pattern |
| Format compact numbers (`1K`, `2M`...) | `getCompactNumberInstance(...)` | Not equivalent to ordinary DecimalFormat |
| Parser must produce `BigDecimal` | Choose `DecimalFormat` with `setParseBigDecimal(true)`, check full input | Avoids guessing returned Number type |
| Receiving formatter from uncontrolled library/provider | Use `instanceof`, never blind cast | Implementation changes will not crash randomly |
| Business currency formatter | Currency factory + separate currency code and rounding control | Do not replace currency with a simple pattern |
| Multi-threaded server processing | Dedicated formatter per render/request or synchronization | Formatters are mutable, not thread-safe |
| Your API only needs `format` | Accept `NumberFormat`/`Format` instead of `DecimalFormat` | Reduces coupling |

### Quick triage checklist

Before casting, ask yourself:

1. **Do I truly need a method exclusive to `DecimalFormat`?** If not, stick with `NumberFormat`.
2. **Do I know where the object came from?** If from a factory/provider, check the subtype; if your own code called `new DecimalFormat`, the type is already known.
3. **If it is not `DecimalFormat`, what should the app do?** Skip customization, use a common fallback, instantiate a separate `DecimalFormat`, or report a configuration error? Decide up front.
4. **Does this feature depend on locale/currency/provider?** Creating a new formatter from a pattern can override conventions chosen by the factory.
5. **Is it shared across threads/requests?** Even if a cast succeeds, mutating the object can still introduce concurrency bugs.

## 14. Practice exercises

**Exercise 1 — Predicting ClassCastException.** Given `NumberFormat first = new DecimalFormat("0.00");` and `NumberFormat second = new ChoiceFormat(new double[]{0,1}, new String[]{"zero","one+"});`, predict `instanceof DecimalFormat` for each variable. Try downcasting both; explain why only one case is valid.

**Exercise 2 — Inspecting factories.** Run `SafeFactoryDemo` with `Locale.US` and then switch to `Locale.GERMANY`. Print `formatter.getClass().getName()` as well to observe the runtime class; use `instanceof` rather than relying on class names. If another provider were active, which branch would execute? Would the program still format numbers?

**Exercise 3 — Compact format.** Create `NumberFormat.getCompactNumberInstance(Locale.US, NumberFormat.Style.SHORT)`. Check `instanceof DecimalFormat` and `instanceof CompactNumberFormat`; do not downcast to `DecimalFormat` if the condition is false. Compare the purpose of compact formatting with the `"#,##0.00"` pattern.

**Exercise 4 — Mandatory pattern.** Write a builder creating `DecimalFormat("#,##0.000", DecimalFormatSymbols.getInstance(Locale.US))` and set `RoundingMode.HALF_UP`. Format `new BigDecimal("12.3456")`, explain why the output has three fractional digits, and explain why the source `BigDecimal` remains unchanged.

**Exercise 5 — Exact parser.** Take the `ParseBigDecimalDemo` example and pass `"1,234.50xyz"`. Confirm the trailing portion is not consumed, causing validation to reject it. Then try `"1,234.50"` and verify the `BigDecimal` type; explain why an arbitrary cast from `NumberFormat` does not solve input validation.

## 15. Common mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| `DecimalFormat d = NumberFormat.getInstance(locale)` | Incompatible types at compile time | Keep `NumberFormat` or check and cast |
| `(DecimalFormat) NumberFormat.getCompactNumberInstance(...)` | Standard compact formatter is a different subtype | Use `NumberFormat`/`CompactNumberFormat` appropriately |
| Casting factory result without checking | Depends on provider/JDK and can throw `ClassCastException` | `instanceof DecimalFormat` |
| Comparing `getClass() == DecimalFormat.class` | Excludes valid subclasses of `DecimalFormat` | `instanceof` |
| Thinking a cast converts the formatter | Casting changes neither runtime type nor formatting behavior | Instantiate a new formatter if different behavior is needed |
| Casting just to set fractional digits | Setters already exist on `NumberFormat` | Use the common interface |
| Assuming `setRoundingMode` works on every `NumberFormat` | Base implementation can throw `UnsupportedOperationException` | Verify implementation support |
| Using `new DecimalFormat(pattern)` assuming it follows user locale | Single-arg constructor uses default FORMAT locale for symbols | Pass `DecimalFormatSymbols.getInstance(locale)` |
| Using `applyPattern` with localized pattern symbols | This API expects standard pattern syntax | Use `applyLocalizedPattern` when appropriate |
| Using plain constructor instead of currency formatter without checking rules | Can lose provider pattern/currency conventions | Use currency factory or configure completely |
| `parse` followed by blind cast to `BigDecimal` | `NumberFormat.parse` returns polymorphic `Number` | Check parser subtype + `setParseBigDecimal` |
| Sharing mutable formatter across multiple requests | Race conditions, settings leaking between users | Create formatter per request or synchronize |
| Testing only on dev machine | Other providers/JDKs may return other subtypes | Test fallback branches and supported runtimes |

## 16. Official documentation

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): factory methods, superclass API, subtype limits, and optionally unsupported methods.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): `instanceof`, constructors, patterns, `DecimalFormatSymbols`, `BigDecimal` parsing.
- [Java SE 21 — CompactNumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/CompactNumberFormat.html): distinct `NumberFormat` subclass and compact formatting.
- [Java SE 21 — NumberFormatProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/spi/NumberFormatProvider.html): provider capability for supplying locale-specific number formats.

## 17. Key takeaways

**`NumberFormat` is not synonymous with `DecimalFormat`.** Factories declare a `NumberFormat` return type and may supply other subclasses depending on format kind, locale, or provider. **Downcast only after checking `instanceof`**, or construct a `DecimalFormat` directly if the product truly needs that class's patterns/features. Settings like fractional digit counts or grouping already live on `NumberFormat` and require no cast.

A successful cast is neither a conversion nor a guarantee of locale, currency, precision, or thread-safety rules. Choose the **narrowest abstraction that meets your needs**, include handling when a subtype is unsupported, and use explicit formatters when you want direct pattern control.
