# Pattern Coverage, Unreachable Labels, and Exhaustiveness Requirements in Java

> **Java core — language-basics / Type Patterns**  
> **Goal:** Understand relationships between type patterns, why a later `case` label can be shadowed (*dominated*), and how a `switch` using patterns covers all possible values (*exhaustive*).  
> **Version:** `instanceof T x` is a final feature in Java 17. **Pattern matching for `switch` is still preview in JDK 17 (JEP 406)**; the example program below uses the proper preview flags. Since Java 21, pattern matching for switch has become a final feature.

## 1. Distinguishing Three Concepts

| Concept | Question to Answer | Illustration |
| --- | --- | --- |
| Pattern match | Does the runtime value belong to the tested type? | A `String` matches `String` and `CharSequence` |
| Shadowed label (*dominated*) | Does an earlier label catch every value the later label intends to catch? | `case CharSequence` before `case String` |
| Exhaustiveness | Does every valid selector value have a handling path? | `case String` and `default` on `Object` |

With multiple `case` labels, order **can be very important**. Unlike a free-form `if` chain that can test the same value multiple times, pattern switch is checked by the compiler to prevent unreachable labels.

A `switch expression` must have a matching branch for all selector values that Java requires to be covered. If any are missing, the program fails at **compile time**, rather than waiting for a user to pass an unhandled value.

## 2. Dominated Labels: A Broad Type Placed Before a Narrow Type

`String` implements the `CharSequence` interface. Therefore, every `String` object matches `CharSequence`, whereas a `StringBuilder` also matches `CharSequence` without being a `String`.

~~~java
Object value = "Java";
System.out.println(value instanceof CharSequence); // true
System.out.println(value instanceof String);       // true
~~~

In a pattern switch, the following arrangement is **invalid**:

~~~java
// DOES NOT COMPILE (Java 17 preview / Java 21+):
// return switch (value) {
//     case CharSequence seq -> "SEQUENCE";
//     case String text -> "TEXT"; // Shadowed by case CharSequence.
//     default -> "OTHER";
// };
~~~

When the input is a `String`, the earlier `CharSequence` branch already catches it. Thus, the later `case String` **can never be selected** (*dominated case label*).

**Fix using specific → general order:**

~~~java
static String label(Object value) {
    return switch (value) {
        case String text -> "STRING:" + text.length();
        case CharSequence seq -> "SEQUENCE:" + seq.length();
        default -> "OTHER";
    };
}
~~~

With input `"Java"`, the result is `"STRING:4"`; with `new StringBuilder("abc")`, the result is `"SEQUENCE:3"`; with `Integer.valueOf(7)`, the result is `"OTHER"`.

Subtype-before-supertype order is simply the usual mnemonic. The core rule is that **an earlier label must not completely dominate a later label**. If complex conditions need to be combined, both the type and the pattern guard must be evaluated according to the Java version in use.

## 3. Catch-All Pattern Labels and `default`

On a selector of type `Object`, the label `case Object any` is a *total type pattern*: it covers every object type that can serve as a value of this selector.

~~~java
static String broad(Object value) {
    return switch (value) {
        case String s -> "STRING";
        case Object any -> "OBJECT";
    };
}
~~~

There is no need to add `default` because the `Object` label at the end already covers the remaining types. Do not put `case Object any` **before** `case String s`: doing so dominates String.

At the same time, **do not** place both a total pattern and `default` in the same switch: they are two catch-all (*match-all*) labels and conflict under switch rules.

~~~java
// DOES NOT COMPILE:
// return switch (value) {
//     case Object any -> "ANY";
//     default -> "OTHER"; // Two match-all labels.
// };
~~~

A more intuitive approach for beginners is using `default` when no variable binding is needed:

~~~java
static String fallback(Object value) {
    return switch (value) {
        case String s -> "STRING:" + s;
        case Integer n -> "INT:" + n;
        default -> "OTHER";
    };
}
~~~

**Note on null and versions:** Pattern switch changed details of `null` handling across preview releases. To keep programs unambiguous on Java 17 and 21, if you want to classify null as its own result, write `case null -> ...` explicitly (see Section 6). A regular `default` **should not be understood** as a dedicated label for null.

## 4. Exhaustiveness of `switch expression`

Example that fails to cover the full `Object` selector:

~~~java
// DOES NOT COMPILE: missing path for Integer, Double, etc.
// String result = switch (value) {
//     case String s -> "TEXT";
//     case Integer i -> "INTEGER";
// };
~~~

Even if the code is only expected to pass String and Integer, the static type of `value` is still `Object`. The compiler must account for other possible types. This can be fixed with `default` or an appropriate total pattern:

~~~java
String result = switch (value) {
    case String s -> "TEXT";
    case Integer i -> "INTEGER";
    default -> "OTHER";
};
~~~

Exhaustive coverage **does not mean every branch executes**: during a single evaluation, the switch chooses one matching branch. Nor does it mean every branch must return a value normally—a branch can intentionally `throw`.

With `case ... ->` switch expressions, block branches require `yield expression;` to supply a result upon normal completion; use `throw` when that case must be rejected.

## 5. Exhaustively Covering a `sealed` Hierarchy Without `default`

Java 17 already supports `sealed class/interface` as a final feature. When the selector type is a sealed interface, the compiler knows the permitted direct implementations and can check whether the patterns cover all of them.

~~~java
sealed interface Job permits PrintJob, SaveJob {}
record PrintJob(String message) implements Job {}
record SaveJob(int id) implements Job {}

static String describe(Job job) {
    return switch (job) {
        case PrintJob p -> "PRINT:" + p.message();
        case SaveJob s -> "SAVE:" + s.id();
    };
}
~~~

`Job` has only two permitted direct implementations in this example; both `case` labels are present, so the switch expression is **exhaustive without `default`**.

If you add a new permitted implementation, such as `SendJob`, and recompile, the compiler will require updating coverage or adding the corresponding label. This is a major maintainability benefit compared to placing a `default` that silently hides every new case.

| Selector Type | Example of Exhaustive Coverage |
| --- | --- |
| `Object` | Specific labels followed by `default` or an appropriate total pattern |
| `String` | Appropriate string labels along with `default` |
| `enum` | Listing all enum constants, or using `default` |
| Sealed interface | Patterns covering all branches in the sealed hierarchy, or an appropriate covering label |

Do not confuse **type coverage** with **data integrity validation**: the `message` field can still be empty/null even though the object is a `PrintJob`. Content rules must be validated separately.

## 6. `null` Is a Case That Must Be Designed Explicitly

With ordinary `instanceof`, null produces false:

~~~java
Object value = null;
boolean result = value instanceof String; // false
~~~

However, a pattern `switch` should not be viewed as a standalone `instanceof` chain. In Java 17 preview, `null` can be given an explicit label:

~~~java
static String nullable(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "STRING:" + s.toUpperCase(java.util.Locale.ROOT);
        default -> "OTHER";
    };
}
~~~

`nullable(null)` returns `"NULL"`; `nullable("ok")` returns `"STRING:OK"`; an `Integer` falls into `"OTHER"`. In Java 17 with preview pattern switch, **without a null label or a general pattern handling null**, a null selector typically results in `NullPointerException`. Therefore, test null explicitly instead of assuming `default` accurately expresses null-handling requirements.

Write `case null` explicitly if null is a supported input; if null is a business error, you can check for it and throw a descriptive exception before the switch.

## 7. Standalone Java 17+ Program

Create a file **PatternCoverageDemo.java**:

~~~java
import java.util.Locale;

public final class PatternCoverageDemo {
    sealed interface Job permits PrintJob, SaveJob {}
    record PrintJob(String message) implements Job {}
    record SaveJob(int id) implements Job {}

    private static String label(Object value) {
        return switch (value) {
            case String s -> "STRING:" + s.length();
            case CharSequence seq -> "SEQUENCE:" + seq.length();
            default -> "OTHER";
        };
    }

    private static String broad(Object value) {
        return switch (value) {
            case String s -> "STRING";
            case Object any -> "OBJECT";
        };
    }

    private static String fallback(Object value) {
        return switch (value) {
            case String s -> "TEXT";
            case Integer n -> "INTEGER";
            default -> "OTHER";
        };
    }

    private static String describe(Job job) {
        return switch (job) {
            case PrintJob p -> "PRINT:" + p.message();
            case SaveJob s -> "SAVE:" + s.id();
        };
    }

    private static String nullable(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s -> "STRING:" + s.toUpperCase(Locale.ROOT);
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("labelText=" + label("Java"));
        System.out.println("labelBuilder="
                + label(new StringBuilder("abc")));
        System.out.println("labelInteger=" + label(Integer.valueOf(7)));

        System.out.println("broadString=" + broad("x"));
        System.out.println("broadObject=" + broad(new Object()));

        System.out.println("fallbackText=" + fallback("a"));
        System.out.println("fallbackNumber=" + fallback(3));
        System.out.println("fallbackOther=" + fallback(2.5));

        System.out.println("sealedPrint="
                + describe(new PrintJob("HELLO")));
        System.out.println("sealedSave=" + describe(new SaveJob(42)));

        System.out.println("nullableNull=" + nullable(null));
        System.out.println("nullableText=" + nullable("ok"));
        System.out.println("nullableOther=" + nullable(Integer.valueOf(9)));

        Object missing = null;
        System.out.println("instanceofNull="
                + (missing instanceof String));
    }
}
~~~

**Compile/run on JDK 17** (preview required):

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PatternCoverageDemo.java
java --enable-preview PatternCoverageDemo
~~~

The JDK 17 compiler may print preview notices to **stderr**, which is not part of the program's stdout. If using **JDK 21+**, the syntax in this file is a final feature and can be run with standard commands:

~~~bash
javac -encoding UTF-8 PatternCoverageDemo.java
java PatternCoverageDemo
~~~

**Exact expected stdout:**

~~~text
labelText=STRING:4
labelBuilder=SEQUENCE:3
labelInteger=OTHER
broadString=STRING
broadObject=OBJECT
fallbackText=TEXT
fallbackNumber=INTEGER
fallbackOther=OTHER
sealedPrint=PRINT:HELLO
sealedSave=SAVE:42
nullableNull=NULL
nullableText=STRING:OK
nullableOther=OTHER
instanceofNull=false
~~~

The program illustrates three ideas: specific labels must precede broader ones; a total pattern or `default` label covers remaining cases; and a sealed interface is handled across both branches without needing `default`. For `null`, the program has an explicit label instead of relying on a fallback.

## 8. Common Mistakes and Exercises

| Symptom | Cause / Fix |
| --- | --- |
| `case CharSequence` before `case String` | `case String` is shadowed; move the String label earlier |
| `case Object` before all narrow labels | Later narrow labels are shadowed; place the total pattern last |
| Both a total pattern and `default` | Two match-all labels; keep only one |
| Switch expression lacks handling for inputs | Not exhaustive; add `default` or a valid covering pattern |
| Sealed type gains a new subtype and switch is not updated | Expand the corresponding branch and recompile |
| Assuming null automatically goes into `default` like other values | Handle `case null` or check before the switch |
| Writing pattern switch on JDK 17 without preview enabled | Use `javac --enable-preview --release 17` and `java --enable-preview` |

**Exercise 1.** Swap the order of `case String` and `case CharSequence` in `label`; predict the compile error and explain it using type relationships.

**Exercise 2.** Remove `default` from `fallback`. Which type values does the compiler report as uncovered?

**Exercise 3.** In `broad`, move `case Object` before `case String`. Which label is shadowed? Can it be fixed merely by adding `break`?

**Exercise 4.** Add a new permitted type to the sealed interface `Job` and update the `describe` switch expression so it remains exhaustive.

**Exercise 5.** Test `null` with `instanceof String` and `nullable(null)`; explain why one evaluates to false while the other enters the `case null` branch.

### Key Takeaway

**Dominance**: placing a broad pattern first can make a narrower label unreachable, causing a compile error. **Exhaustiveness**: a switch expression must cover all possibilities; you can use `default`, a total pattern, or all branches of a `sealed` hierarchy. **Null** must be designed explicitly. When studying with **JDK 17**, pattern switch requires enabling **preview**; starting in Java 21, this is a final feature.
