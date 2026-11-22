# instanceof Pattern with a null Target in Java

## 1. Concept and Most Important Rule

In the expression `target instanceof String text`, `target` is the **left-hand operand** — the value being tested; `String text` is the **type pattern** — the pattern that tests the type and declares a pattern variable if it succeeds.

“Null target” here means **the left-hand expression evaluates to the `null` reference at runtime**. This is not an object “with type null”: `null` does not refer to any instance.

**Rule in Java 17 and Java 21:** if the value of the left-hand operand is `null`, the `instanceof` expression evaluates to **`false`**. This rule applies to both traditional type-comparison `instanceof` and `instanceof` with a pattern. No pattern variable is initialized.

~~~java
Object target = null;

System.out.println(target instanceof String text); // false
System.out.println(target instanceof Object obj);   // false
~~~

Even the `Object obj` pattern does not match, because declaring the `target` variable with type `Object` only indicates the **static type of the variable**, not that the variable points to an existing object.

## 2. Two Forms of instanceof and Two Checking Phases

Two syntactic forms:

~~~java
target instanceof String          // Traditional type comparison
target instanceof String text     // Pattern match, with pattern variable text
~~~

With a `null` target, both return `false`. With a target pointing to an actual `String`, both return `true`; the pattern form also initializes the `text` variable for use in locations where it is in scope.

| Actual value of target | `instanceof String` | `instanceof String text` |
| --- | --- | --- |
| `null` | false | false, `text` is not initialized |
| `"Java"` | true | true, `text` is `"Java"` |
| `Integer.valueOf(7)` | false | false, `text` is not initialized |

It is important to distinguish:

1. **At compile time:** the static type of the left-hand expression must be compatible with testing the pattern on the right-hand side (*pattern applicability*). The fact that an input might be null does not make an incompatible pattern valid.
2. **At runtime:** Java evaluates the left-hand expression. If the result is the null reference, `instanceof` returns false immediately. If it is non-null, Java attempts to match the value against the type/pattern; only when it matches is the pattern variable assigned.

For example, `Object value = null; value instanceof String s` is valid at compile time and returns false at runtime. Conversely, `String value = null; value instanceof Integer n` is still invalid because the two class types are incompatible; a null value does not “bypass” static type checking.

With the null literal, the following expression also returns false in Java 17/21:

~~~java
System.out.println(null instanceof String s); // false
~~~

However, `value instanceof null` is a syntax error: `null` is not a type pattern or reference type to place after the operator.

## 3. Standalone Program: null Never Matches a Type Pattern

Save as **`NullInstanceofDemo.java`**, run with JDK 17 or later:

~~~java
import java.util.List;

public class NullInstanceofDemo {

    static String describe(Object value) {
        if (value instanceof String s) {
            return "String length=" + s.length();
        }
        if (value instanceof Integer n) {
            return "Integer x2=" + (n * 2);
        }
        return value == null ? "NULL" : "OTHER";
    }

    static String nonBlank(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "TEXT=" + s.strip();
        }
        return "NO_TEXT";
    }

    static String requireText(Object value) {
        if (!(value instanceof String s)) {
            return value == null ? "MISSING" : "WRONG_TYPE";
        }
        return "VALID=" + s;
    }

    public static void main(String[] args) {
        Object value = null;

        System.out.println("string=" + (value instanceof String s));
        System.out.println("object=" + (value instanceof Object any));
        System.out.println("list=" + (value instanceof List<?> items));

        System.out.println(describe(null));
        System.out.println(describe("Java"));
        System.out.println(describe(7));
        System.out.println(describe(new Object()));

        System.out.println(nonBlank(null));
        System.out.println(nonBlank("  Java  "));
        System.out.println(nonBlank("   "));

        System.out.println(requireText(null));
        System.out.println(requireText("OK"));
    }
}
~~~

Compile/run:

~~~bash
javac NullInstanceofDemo.java
java NullInstanceofDemo
~~~

Output:

~~~text
string=false
object=false
list=false
NULL
String length=4
Integer x2=14
OTHER
NO_TEXT
TEXT=Java
NO_TEXT
MISSING
VALID=OK
~~~

**Why?**

- `value` at the start of the program holds null, so the `String`, `Object`, and `List<?>` tests are all false. A generic wildcard does not turn null into a list.
- `describe(null)` passes through both `instanceof` branches and only distinguishes null at the end using `== null`.
- `describe("Java")` matches `String s` and safely accesses `s.length()`.
- `nonBlank(null)` returns `NO_TEXT`; the right-hand side of `&&` does not execute when the pattern fails.
- `requireText(null)` returns `MISSING` thanks to the separate null check in the non-matching branch; `requireText("OK")` uses the `s` variable on the matched path.

This is an example of **language-specified behavior**, not dependent on HotSpot, a library, or a specific JVM version.

## 4. A false Result Does Not Indicate the Reason

A false `instanceof` test has at least two common causes:

~~~java
Object first = null;
Object second = Integer.valueOf(100);

boolean a = first instanceof String s1;  // false because of null
boolean b = second instanceof String s2; // false because of different type
~~~

You cannot tell from a false result alone that the target is null. If business logic needs to distinguish “no data” from “data present but wrong type”, check explicitly:

~~~java
static String classify(Object value) {
    if (value == null) {
        return "Thiếu dữ liệu";
    }
    if (value instanceof String text) {
        return "Chuỗi: " + text;
    }
    return "Không phải chuỗi";
}
~~~

This is an **illustrative method** to place inside a Java 17+ class. Calling `classify(null)` returns `"Thiếu dữ liệu"`; calling `classify(7)` returns `"Không phải chuỗi"`.

If both cases share the same handling, you may only need:

~~~java
static int lengthIfString(Object value) {
    return value instanceof String text ? text.length() : 0;
}
~~~

This method returns `0` for both null and wrong type. Choose based on the **API contract**, rather than always splitting null into a separate branch.

## 5. The Pattern Variable Is Not Assigned null When instanceof Is false

The pattern `String text` declares a **pattern variable**. This variable is initialized **only when the test returns true**. When the target is null, Java does not create a `text` variable with a default null value for use in another branch.

Intentionally invalid code:

~~~java
static void invalid(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println(text.length()); // COMPILE ERROR
    }
}
~~~

This is an **error-demonstration snippet**, not a standalone runnable program. Even though the `else` branch can execute with null, the `text` variable is not in *scope* in that branch. Java uses **flow scoping** to determine where a pattern is guaranteed to have matched.

Negating the condition moves the pattern variable into the `else` branch:

~~~java
static String render(Object value) {
    if (!(value instanceof String text)) {
        return "null hoặc không phải String";
    } else {
        return "Chuỗi: " + text;
    }
}
~~~

In the `else` branch, the negated expression being false means `value instanceof String text` is true; therefore `text` has been assigned and cannot be null due to this match itself. If `value == null`, the `if` branch runs.

A *guard clause* also preserves scope:

~~~java
static int safeLength(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // Valid: the continuing path has matched
}
~~~

When the target is null, the method returns 0 before using `text`.

## 6. Adding Extra Conditions with && and ||

With short-circuit `&&`, the pattern variable on the right-hand side is only used after `instanceof` has returned true:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

If `value == null`, the left-hand side is false and Java **does not call `text.isBlank()`**. If the overall condition is true, the `text` variable is guaranteed to exist and hold a real String.

You can also write a negated condition with `||`:

~~~java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Không có chuỗi hợp lệ");
} else {
    System.out.println(text.strip());
}
~~~

Here, the right-hand side of `||` only executes when the left-hand side is false, meaning the String pattern has matched. When entering `else`, both sides are false; `text` is guaranteed to have matched and is not blank.

Conversely, the following snippet **does not compile**:

~~~java
// INTENTIONALLY WRONG: text is not guaranteed to exist on the right-hand side of ||
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
~~~

Because the right-hand side of `||` may need to run when `value instanceof String text` is false, `text` is not in scope there. The fact that the target can be null makes the non-matching scenario even clearer, but this is primarily a Java control-flow rule.

There is no need to write `value != null && value instanceof String text` just to protect `text` from null. If you do not need to distinguish null, `value instanceof String text` alone is already safe.

## 7. Why instanceof Is Safe Yet an Expression Containing It Can Still Throw NPE

The exact statement is:

> **If evaluating the left-hand operand completes and produces the null reference, `instanceof` returns false.**

Java still has to **evaluate the left-hand operand first**. If that evaluation throws an exception, the `instanceof` operator has not been executed yet.

Safe code:

~~~java
Object value = null;
boolean matched = value instanceof String text; // false
~~~

Code that can throw NPE:

~~~java
Object[] values = null;
boolean matched = values[0] instanceof String text;
~~~

In the second case, accessing `values[0]` causes a `NullPointerException` because `values` is null; the error occurs **before** the type check. Similarly, calling a method on a null receiver to produce the left-hand value can throw NPE before reaching `instanceof`.

Do not assume that every expression in a snippet is null-safe just because it contains `instanceof`. `instanceof` only handles **the value it receives**, not the entire computation that produces that value.

## 8. Null, Explicit Casting, and Method Calls

Comparing operations when `Object value = null`:

| Operation | Behavior |
| --- | --- |
| `value instanceof String s` | false; does not initialize `s` |
| `value instanceof String` | false |
| `value instanceof Object obj` | false |
| `value == null` | true |
| `String s = (String) value` | Valid cast, `s` remains null |
| `((String) value).length()` | Throws `NullPointerException` |
| `Objects.requireNonNull(value)` | Intentionally throws `NullPointerException` |

A successful cast does not mean the target is an object. Casting null to a valid reference type still yields null:

~~~java
Object value = null;
String casted = (String) value; // casted == null
boolean matched = value instanceof String text; // false
~~~

`instanceof` requires an **actual object matching the pattern**, whereas casting a null reference simply preserves null.

If you want to *enforce* non-null, use `Objects.requireNonNull` or `if (value == null) throw ...` as an explicit API design decision; `instanceof` does not treat null as an error by itself.

## 9. Null with Generics, Interfaces, Arrays, and Object

There are no special exceptions for any category of reference types:

~~~java
Object target = null;

boolean a = target instanceof CharSequence cs;
boolean b = target instanceof java.util.List<?> list;
boolean c = target instanceof int[] numbers;
boolean d = target instanceof Runnable task;
boolean e = target instanceof Object obj;
~~~

Place these declarations in a Java 17+ method or block. All five results are false.

- **Generics:** `List<?>` can be used to test whether an object is a List, but it does not make null match. `List<String>` with a source of static type `Object` is often not even a valid pattern because a generic cast requires an *unchecked* check.
- **Arrays:** an empty array `new int[0]` is **an object**, so it matches `int[]`; a reference `int[] array = null` does not point to an array, so it does not match.
- **Interfaces:** a non-null object can implement `Runnable`, but null does not.
- **Object:** a variable's declared type being `Object` does not mean there is an object. `null instanceof Object` is still false.

## 10. Java 21: A null Target Differs from a Record Containing a null Component

When using **record patterns**, distinguish between:

- **Outermost target is null:** there is no record object to match. `target instanceof Box(var value)` is always false.
- **Record object exists but an inner component is null:** the outer record pattern can match, and certain component patterns can match null according to their own rules.

Standalone example using **Java 21**, saved as `NullRecordDemo.java`:

~~~java
public class NullRecordDemo {
    record Box(Object payload) {}

    static String inspect(Object target) {
        if (target instanceof Box(String text)) {
            return "TEXT:" + text;
        }
        if (target instanceof Box(var payload)) {
            return payload == null
                    ? "BOX_NULL_CONTENT"
                    : "BOX_OTHER_CONTENT";
        }
        return target == null ? "TARGET_NULL" : "NOT_A_BOX";
    }

    static String fromSwitch(Object value) {
        return switch (value) {
            case null -> "SWITCH_NULL";
            case String s -> "SWITCH_STRING=" + s;
            default -> "SWITCH_OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(null));
        System.out.println(inspect(new Box(null)));
        System.out.println(inspect(new Box("Java")));
        System.out.println(inspect(new Box(42)));
        System.out.println(inspect("Java"));

        System.out.println(fromSwitch(null));
        System.out.println(fromSwitch("Java"));
        System.out.println(fromSwitch(42));
    }
}
~~~

Commands:

~~~bash
javac NullRecordDemo.java
java NullRecordDemo
~~~

Output:

~~~text
TARGET_NULL
BOX_NULL_CONTENT
TEXT:Java
BOX_OTHER_CONTENT
NOT_A_BOX
SWITCH_NULL
SWITCH_STRING=Java
SWITCH_OTHER
~~~

Explanation:

1. `inspect(null)`: both `instanceof Box(...)` checks are false because the target itself is null.
2. `inspect(new Box(null))`: the Box **exists**. `Box(String text)` does not match because the `Object`-typed component is null and does not match the String pattern there. `Box(var payload)` matches, and `payload` can be null.
3. `inspect(new Box("Java"))`: the String component matches the first branch.
4. `inspect(new Box(42))`: the Box record matches, but the component is not a String, so it falls through to the `Box(var payload)` branch.

JLS 21 defines *null-matching component patterns* for record deconstruction. A type pattern that is **unconditional at the component type** can accept null in this case. This **does not change the rule**: if the entire left-hand operand of `instanceof` is null, the result is still false.

**Version boundary:** the `NullInstanceofDemo` example uses features finalized in Java 17; `NullRecordDemo` requires Java 21 because record patterns became a standard feature in Java 21.

## 11. Java 21 switch with case null: Different from instanceof

The `fromSwitch` method in the example above uses:

~~~java
return switch (value) {
    case null -> "SWITCH_NULL";
    case String s -> "SWITCH_STRING=" + s;
    default -> "SWITCH_OTHER";
};
~~~

`case null` is a special `switch` label, **not an `instanceof` type pattern**. In Java 21:

| Construct | With null input |
| --- | --- |
| `value instanceof String s` | Returns false |
| `if (value == null)` | Condition is true |
| `switch (value)` with `case null` | Executes the `case null` branch |
| `switch (value)` without `case null` | Throws `NullPointerException`, even if `default` is present |

Do not assume that `default` in a `switch` catches null like `else` after an `instanceof` chain. To handle null in a Java 21 switch, you need `case null`; you can also check for null before the switch.

In Java 21, `case null, String s -> ...` is invalid because you cannot combine a null label with a type pattern like that. You can use `case null, default -> ...` if you want both cases to share the same handling.

## 12. Choosing Behavior Based on the API Contract

**Approach A — Null is missing data, with a fallback:**

~~~java
static String displayName(Object value) {
    if (value == null) {
        return "(chưa có)";
    }
    if (value instanceof String name && !name.isBlank()) {
        return name;
    }
    return "(không hợp lệ)";
}
~~~

**Approach B — Null is an error to detect:**

~~~java
static int requiredStringLength(Object value) {
    java.util.Objects.requireNonNull(value, "value");
    if (value instanceof String text) {
        return text.length();
    }
    throw new IllegalArgumentException("value phải là String");
}
~~~

**Approach C — Only care about String:**

~~~java
static int lengthIfString(Object value) {
    return value instanceof String text ? text.length() : 0;
}
~~~

These are **illustrative methods**, placed in a Java 17+ class when run. Approach A distinguishes null from wrong type; Approach B actively reports an error; Approach C groups null and wrong type into the same fallback. Choose the approach that fits your contract and the message you want to convey to callers.

## 13. Common Mistakes and Misconceptions

| Misconception / mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| `null instanceof Object obj` is true | Null is not any instance | Check for null with `== null` |
| Pattern variable `s` has value null if the pattern is false | A pattern variable is only initialized on a match | Use `s` in a branch guaranteed to match |
| Using `s` in the `else` of `if (v instanceof String s)` | Else may correspond to null or another type | Handle `v` or restructure the condition |
| `instanceof` protects every dereference in the left-hand operand | An error can occur before the pattern test | Check the receiver or array when needed |
| `instanceof` false ⇒ target is null | An object of another type also yields false | Separate `== null` if you need to distinguish |
| Writing `v instanceof null` | Null is not a type pattern | Use `v == null` |
| In a Java 21 switch, `default` will catch null | Without `case null`, a null selector causes NPE | Add `case null` |
| `new Box(null)` is equivalent to `null` | The Box is real; only its component is null | Treat outer null and component null separately |
| `(String) null` succeeds ⇒ `null instanceof String s` is true | Casting null preserves null without creating an instance | Distinguish casting from pattern matching |

## 14. Self-Check

**Question 1.** Given `Object o = null;`, what do `o instanceof String s`, `o instanceof Number n`, and `o instanceof Object x` evaluate to?

**Answer:** All three evaluate to false; no pattern variable is initialized.

**Question 2.** Why does `if (o instanceof String s && s.length() > 3)` not throw NPE when `o == null`?

**Answer:** `instanceof` returns false and `&&` short-circuits the right-hand side. `s.length()` is only evaluated after the pattern matches.

**Question 3.** Is `String s = (String) null;` valid? Does it make `null instanceof String t` true?

**Answer:** The cast is valid, but `s` remains null; `instanceof` is still false.

**Question 4.** Do `target = null` and `target = new Box(null)` produce the same result for `target instanceof Box(var p)` in Java 21?

**Answer:** No. An outer null target makes `instanceof` false; an actual Box containing a null component can match the pattern and bind `p = null`.

**Question 5.** How does a Java 21 `switch` with `default` but without `case null` handle a null selector?

**Answer:** It throws `NullPointerException`; `default` does not catch null.

## 15. Official References

- [Java Language Specification 21, Section 15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): compile-time conditions, behavior when the left-hand operand is null, when pattern variables are initialized.
- [JLS 21, Section 14.30.2 — Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2): matching of type/record patterns and null-matching component pattern rules.
- [JLS 21, Section 6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): flow scoping of pattern variables.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): `case null` and behavior of a null selector.

**Conclusion:** `instanceof` with a **null outermost target always returns false**; no pattern variable is initialized. To distinguish null from a wrong type, check `== null`; to handle null in a Java 21 `switch`, use `case null`. Only when a record actually exists do the null rules for component patterns come into play.
