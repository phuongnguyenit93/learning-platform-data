# Pattern Matching for `switch` in Java 21

**Pattern matching for switch** has been a standard feature since **Java 21 (JEP 441)**: instead of only comparing `case` against constants, Java can check the **actual type** of an object, bind the object to a **pattern variable**, and use an additional `when` condition.

~~~java
Object value = "Java";

String result = switch (value) {
    case String s -> "String: " + s.toUpperCase();
    case Integer n -> "Number: " + n;
    case null -> "Missing data";
    default -> "Other type";
};
~~~

If `value` is `"Java"`, the result is `"String: JAVA"`. When the label `case String s` matches, `s` has static type `String`, so you do not need to write `(String) value`. **The pattern `case String s` is not equivalent to `case "String"`**: one checks a type, while the other is a string constant label.

**Version note:** `instanceof String s` has been a standard feature since Java 16 and works on JDK 17. However, **pattern matching in `switch` is a standard feature starting in JDK 21**. The `case String s ->` example below **does not compile with standard JDK 17 `javac`**. Section 3 provides an equivalent approach that runs on JDK 17 without preview.

## 1. Type Patterns, `when`, `null`, and `default`

Example:

~~~java
return switch (value) {
    case null -> "missing";
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s;
    case Integer n when n >= 0 -> "nonnegative:" + n;
    case Integer n -> "negative:" + n;
    default -> "other";
};
~~~

Rules:

- `case String s`: matches when the object has a compatible `String` type; binds it to `s`, which is in scope only within the corresponding branch.
- `case String s when s.isBlank()`: must first match the `String` type, and then evaluates the `when` condition. If the guard is false, Java continues checking subsequent labels.
- `case null`: **handles a null selector**. This is a notable difference from the traditional Java 17 switch.
- `default`: handles cases where no label matches. **`default` alone does not catch `null`**; if `case null` is missing, a null selector normally throws `NullPointerException`.
- `case ... ->`: executes only the selected branch, **with no fall-through** to later labels.

| Selector | Label Selected in the Example Above | Result |
| --- | --- | --- |
| `null` | `case null` | `missing` |
| `"   "` | `String s when s.isBlank()` | `blank` |
| `"Java"` | `String s` | `text:Java` |
| `12` (Integer) | `Integer n when n >= 0` | `nonnegative:12` |
| `-2` (Integer) | `Integer n` | `negative:-2` |
| `2.5` (Double) | `default` | `other` |

### Label Order and Dominance

If an unguarded `case String s` appears before `case String s when s.isBlank()`, the second label is covered by the first and causes a **dominated case** compile error. Therefore, place **narrower/guarded** patterns before **broader/unguarded** patterns.

Do not use `when` after a constant label as if it were a general `if`; guarded pattern syntax is designed to accompany a **pattern label**.

## 2. Complete Example Running on JDK 21

Create a UTF-8 file **`PatternSwitch21Demo.java`**:

~~~java
import java.util.Locale;

public class PatternSwitch21Demo {
    sealed interface Action permits Start, Stop {}
    record Start(String task) implements Action {}
    record Stop() implements Action {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "missing";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s.toUpperCase(Locale.ROOT);
            case Integer n when n >= 0 -> "nonnegative:" + n;
            case Integer n -> "negative:" + n;
            case Start s -> "start:" + s.task();
            case Stop s -> "stop";
            default -> "other";
        };
    }

    static String action(Action action) {
        return switch (action) {
            case Start s -> "start:" + s.task();
            case Stop s -> "stop";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", "java", 12, -2,
            new Start("build"), new Stop(), 2.5
        };
        for (Object input : inputs) {
            System.out.println(describe(input));
        }
        System.out.println("sealed=" + action(new Start("deploy")));
    }
}
~~~

Use **JDK 21 or later** in the directory containing the file (PowerShell or Bash):

~~~bash
java -version
javac -version
javac -encoding UTF-8 PatternSwitch21Demo.java
java PatternSwitch21Demo
~~~

**Exact expected stdout** of `java PatternSwitch21Demo` alone:

~~~text
missing
blank
text:JAVA
nonnegative:12
negative:-2
start:build
stop
other
sealed=start:deploy
~~~

`--enable-preview` is not needed on JDK 21. The output of `java -version` and `javac -version` depends on the installed JDK, so it is not included in the fixed stdout.

### Exhaustiveness with `sealed`

`Action` is a **sealed interface** that permits only `Start` and `Stop` to implement it directly. The compiler knows the permitted set of subtypes, so the following switch expression can **omit `default`**:

~~~java
static String action(Action action) {
    return switch (action) {
        case Start s -> "start:" + s.task();
        case Stop s -> "stop";
    };
}
~~~

A `switch` expression must **exhaustively cover** all values of the selector type according to compiler rules; if a new permitted subtype is added without updating the branches, the compiler can require a fix. A `switch` statement with patterns also has appropriate coverage/label rules, though it should not be confused with a traditional switch statement that only uses constants.

**The null case:** listing all subtypes `Start` and `Stop` does not mean null is handled. If `action == null`, this switch throws `NullPointerException` at runtime.

## 3. Java 17 Compatible Approach: `instanceof` Type Patterns

If you only have JDK 17, use `if` chains with `instanceof Type name` and guards. This expresses the same logic without using Java 21 pattern-switch.

Create a UTF-8 file **`PatternSwitch17Compat.java`**:

~~~java
import java.util.Locale;

public class PatternSwitch17Compat {
    sealed interface Action permits Start, Stop {}
    record Start(String task) implements Action {}
    record Stop() implements Action {}

    static String describe(Object value) {
        if (value == null) {
            return "missing";
        }
        if (value instanceof String s) {
            if (s.isBlank()) {
                return "blank";
            }
            return "text:" + s.toUpperCase(Locale.ROOT);
        }
        if (value instanceof Integer n) {
            return n >= 0 ? "nonnegative:" + n : "negative:" + n;
        }
        if (value instanceof Start s) {
            return "start:" + s.task();
        }
        if (value instanceof Stop) {
            return "stop";
        }
        return "other";
    }

    static String action(Action action) {
        if (action instanceof Start s) {
            return "start:" + s.task();
        }
        if (action instanceof Stop) {
            return "stop";
        }
        throw new IllegalArgumentException("unsupported action");
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", "java", 12, -2,
            new Start("build"), new Stop(), 2.5
        };
        for (Object input : inputs) {
            System.out.println(describe(input));
        }
        System.out.println("sealed=" + action(new Start("deploy")));
    }
}
~~~

Run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 PatternSwitch17Compat.java
java PatternSwitch17Compat
~~~

**Exact expected stdout** of `java PatternSwitch17Compat`:

~~~text
missing
blank
text:JAVA
nonnegative:12
negative:-2
start:build
stop
other
sealed=start:deploy
~~~

Both programs produce the same illustrative output. However, the Java 17 approach uses sequential `instanceof` checks and therefore **does not have the same exhaustiveness checking of a switch expression over a sealed type**: the `action` method in this version uses a fallback `throw`.

## 4. Pattern Switch, `switch expression`, and `yield`

Pattern matching can appear in both switch statements and switch expressions. In the JDK 21 program, `describe` uses a **switch expression** returning a `String` directly from each branch.

If a branch needs multiple statements, use a block and `yield` to produce a value:

~~~java
String result = switch (value) {
    case String s -> {
        String cleaned = s.trim();
        yield "length:" + cleaned.length();
    }
    case null -> "missing";
    default -> "other";
};
~~~

`yield` returns a value **from the switch expression**, rather than exiting the entire method like `return`. With a single-expression `case ... ->`, you just write the result expression without `yield`.

**The result type** is determined at compile time from the branches/target context; it does not dynamically change type at runtime depending on which pattern matches. The pattern variable `s` has static type `String`, while the outer variable `value` still has static type `Object`.

## 5. Important Limitations and Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| "Java 17 supports `case String s ->` like Java 21." | Java 17 only has pattern-switch as preview, not as standard syntax without preview enabled |
| "`case String s` creates a new String object." | It only binds a reference when the type matches |
| "`case String s` and `case "String"` are the same." | One is a **type pattern**, the other is a string constant |
| "`case String s` should come before `case String s when ...`." | A broad pattern can dominate a narrow pattern and cause a compile error |
| "`default` automatically handles `null`." | You need `case null`, or null can throw NPE |
| "`when` runs before checking the type." | A guard is evaluated only after the pattern matches |
| "The `case ->` form falls through to the next branch." | There is no fall-through |
| "Listing all sealed subtypes also catches null." | Null must be handled separately if needed |
| "`case List<String> list` can always check the generic argument." | Type erasure restricts checking parameterized generic types; usually use `List<?>` and validate elements |

In Java 21, record patterns are also standardized and can be combined with pattern-switch, but that is a technique for **deconstructing record structure**, different from the basic type patterns in this lesson. Record patterns are not needed for the examples above.

## 6. Self-Check Exercises

1. In `switch(value) { case String s -> ...; default -> ...; }`, when `value` is `"abc"`, which branch runs?  
   *Answer:* `String s`.
2. If `value == null` and there is no `case null`, does `default` run?  
   *Answer:* No; it normally throws `NullPointerException`.
3. Can `case String s when s.isBlank()` be placed after `case String s`?  
   *Answer:* No; the earlier pattern dominates the later one and causes a dominated-case compile error.
4. At which step is `when` evaluated?  
   *Answer:* After the pattern type has matched, before selecting that branch.
5. Can standard Java 17 use the `instanceof String s` syntax?  
   *Answer:* Yes, since Java 16.
6. Why can `switch(action)` on `sealed Action` omit `default`?  
   *Answer:* The compiler knows all permitted subtypes and the patterns already cover them.
7. What is used to return a value from a block inside a switch expression?  
   *Answer:* `yield`.

## Checklist

- [ ] Distinguish **`instanceof` type patterns standard in Java 17** from **pattern matching for switch standard in Java 21**.
- [ ] Understand that `case Type variable` both checks the type and binds a properly typed variable.
- [ ] Use `when` for additional conditions and place narrower patterns before broader ones.
- [ ] Handle `null` explicitly with `case null` when needed; do not confuse it with `default`.
- [ ] Use `->` to avoid fall-through, and `yield` when a switch expression branch is a block.
- [ ] Understand exhaustiveness rules, especially with sealed hierarchies.
- [ ] Know how to write a Java 17 alternative using `if` and `instanceof` if the environment has not upgraded to JDK 21.

**Conclusion:** Java 21 brings type checking directly into `switch`, letting you select branches by object type, combine `when` guards, handle `null`, and verify exhaustiveness. When a project still uses Java 17, use `instanceof` type patterns with `if` to achieve equivalent behavior without relying on preview.
