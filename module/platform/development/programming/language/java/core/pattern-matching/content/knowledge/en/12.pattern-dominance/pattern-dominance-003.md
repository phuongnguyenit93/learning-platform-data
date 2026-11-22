# Parent Type Pattern Dominating Child Type Pattern in Java

## 1. The problem: why does a type-valid case still fail to compile?

Since **Java 21**, pattern matching for `switch` is a standard feature. You can write branches based on the runtime type of an object:

~~~java
return switch (value) {
    case String s -> "Chuỗi: " + s;
    case CharSequence chars -> "Dãy ký tự";
    default -> "Khác";
};
~~~

Suppose `value` has static type `Object`. This code is **valid** because the `String` branch comes **before** the broader `CharSequence` branch.

If you reverse the order, the compiler rejects it:

~~~java
return switch (value) {
    case CharSequence chars -> "Dãy ký tự";
    case String s -> "Chuỗi: " + s; // COMPILE ERROR: dominated case label
    default -> "Khác";
};
~~~

The reason: every `String` object implements `CharSequence`. When encountering a `String`, the `CharSequence` case **already matches it first**, so the subsequent `String` case **can never be selected**. Java calls this **dominance** (an earlier case label *dominates* or *shadows* a later case label).

> **Quick rule of thumb:** In a `switch` with type patterns, a **broader pattern without a real guard** placed first can dominate a more specific pattern after it. To classify by subtype, prefer **child cases first, parent cases later**.

Note: dominance checking happens **at compile time**, not at runtime. This is not merely a dead-code warning or an arbitrary ordering issue: an invalid program will **not compile**.

## 2. Understanding "parent", "child", and type relationships

In this article:

- **Parent type / broader type:** a type that covers objects of one or more subtypes, such as `CharSequence` compared to `String`, `Number` compared to `Integer`, or `List<?>` compared to `ArrayList<?>`.
- **Child type / narrower type:** a type whose instances are also instances of the parent type, such as `String` being a `CharSequence`.
- **Type pattern:** a `case T variable` label that checks whether the selector matches type `T` and binds the pattern variable if it matches.

The relationship does not have to be a direct `extends` between two **classes**. **Interfaces** and **indirect inheritance** also matter:

~~~text
Object
├── CharSequence (interface)
│   ├── String
│   └── StringBuilder
├── Number
│   ├── Integer
│   └── Double
└── List (interface)
    └── ArrayList
~~~

This diagram only illustrates the relevant relationships, **not** the complete Java inheritance hierarchy: interfaces and classes can participate in multiple relationships at the same time. For example, `String` also implements `Serializable` and other interfaces.

Given a broader type `T` and a narrower type `U`, if every value matching `U` also matches `T`, then an **unguarded** `case T t` label placed earlier typically **dominates** a `case U u` label placed later. The Java Language Specification defines the exact rules, including parameterized types, pattern guards, and other label forms; do not replace the full specification with a "direct superclass only" rule.

### Table of common relationships

| Earlier case (broader) | Later case (narrower) | Result if both are unguarded |
| --- | --- | --- |
| `case CharSequence cs` | `case String s` | String case is dominated |
| `case Number n` | `case Integer i` | Integer case is dominated |
| `case Object o` | `case String s` | String case is dominated |
| `case java.io.Serializable obj` | `case String s` | String case is dominated |
| `case java.util.List<?> list` | `case java.util.ArrayList<?> arrayList` | ArrayList case is dominated |

A parent interface can also shadow a **child class**. With `Serializable` before `String`, Java does not need an `extends` relationship between class names to detect dominance, because every `String` is `Serializable`.

## 3. What does dominance mean for case selection flow?

Consider:

~~~java
Object value = "Java";

String result = switch (value) {
    case CharSequence cs -> "SEQUENCE";
    case String s -> "STRING"; // Does not compile
    default -> "OTHER";
};
~~~

If this order were allowed, the first case would match `"Java"` because `String` is a `CharSequence`. The later case also describes a String, but **never gets a chance** to handle such a value.

Key properties:

1. **Dominance depends on label order.** When reversed to `String` before `CharSequence`, each case can still be selected.
2. **Dominance is based on type relationships and label properties**, not on the dataset you expect at runtime. Even if you currently only pass `Integer` into the switch, `CharSequence` before `String` is still a compile error.
3. **Dominance is distinct from pattern matching.** Pattern matching happens when the switch runs; dominance determines beforehand whether the case order is valid.
4. **Dominance applies to both switch statements and switch expressions** that use patterns, not only when a switch produces a value.

Two labels may both be applicable for a selector of type `Object`, yet **not be allowed** in an order where one dominates the other. Therefore, "the compiler accepts `case String` on its own" does not guarantee you can place that case in any position.

## 4. Java 21 program: correct ordering with classes, interfaces, and generics

Save as **`DominanceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DominanceDemo {

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";

            case String s -> "STRING:" + s;
            case CharSequence cs -> "CHARS:" + cs.length();

            case Integer n -> "INTEGER:" + n;
            case Number n -> "NUMBER:" + n;

            case ArrayList<?> items -> "ARRAYLIST:" + items.size();
            case List<?> items -> "LIST:" + items.size();

            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(new StringBuilder("xy")));
        System.out.println(describe(7));
        System.out.println(describe(2.5));
        System.out.println(describe(
                new ArrayList<>(List.of(1, 2))));
        System.out.println(describe(List.of("x")));
        System.out.println(describe(null));
        System.out.println(describe(new Object()));
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
javac DominanceDemo.java
java DominanceDemo
~~~

Exact output:

~~~text
STRING:Java
CHARS:2
INTEGER:7
NUMBER:2.5
ARRAYLIST:2
LIST:1
NULL
OTHER
~~~

Explanation:

- `"Java"` is a `String` and also a `CharSequence`. Because the `String` case comes first, the result is `STRING:Java`.
- `StringBuilder("xy")` implements `CharSequence` but is not a `String`, so the second case matches and produces `CHARS:2`.
- `Integer(7)` is a `Number`, but the more specific `Integer` case takes precedence.
- `Double(2.5)` is not an Integer but is a Number, so the result is `NUMBER:2.5`.
- `new ArrayList<>(...)` is both an `ArrayList<?>` and a `List<?>`. Placing `ArrayList<?>` first lets it be handled separately.
- `List.of("x")` returns a List that is not an ArrayList, so the `List<?>` case matches it.
- `null` is handled by `case null`; the `new Object()` instance falls into `default`.

This program shows that the same principle applies to **classes**, **interfaces**, **numeric types**, and **wildcard generic collections**: **narrower first, broader later** when those cases are unguarded.

## 5. Snippets that intentionally fail to compile

The examples below are only for observing the errors; **do not add them to `DominanceDemo.java`**.

### 5.1. Number before Integer

~~~java
static String badNumber(Object value) {
    return switch (value) {
        case Number n -> "NUMBER";
        case Integer i -> "INTEGER"; // COMPILE ERROR: dominated
        default -> "OTHER";
    };
}
~~~

Every `Integer` is a `Number`. The compiler does not allow placing an `Integer` case after an unguarded `Number` case. Fix this by swapping the two labels:

~~~java
static String goodNumber(Object value) {
    return switch (value) {
        case Integer i -> "INTEGER";
        case Number n -> "NUMBER";
        default -> "OTHER";
    };
}
~~~

These are **illustrative methods**; place them inside a class and use JDK 21 if you want to test them. The Integer branch does not need to "not be a Number" to exist: it just needs to be evaluated first.

### 5.2. An interface can also dominate String

~~~java
static String badInterface(Object value) {
    return switch (value) {
        case java.io.Serializable ser -> "SERIALIZABLE";
        case String text -> "STRING"; // COMPILE ERROR: dominated
        default -> "OTHER";
    };
}
~~~

`String` implements `Serializable`; the later String case can never receive a String that the earlier Serializable case let through. The correct order is the String case before the Serializable case (if you genuinely need to distinguish between the two).

**Do not mistake "parent" for only a base class.** With type patterns, appropriate interfaces can also create dominance relationships.

### 5.3. List<?> before ArrayList<?>

~~~java
static String badList(Object value) {
    return switch (value) {
        case java.util.List<?> list -> "LIST";
        case java.util.ArrayList<?> arr -> "ARRAYLIST"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

An `ArrayList<?>` is always a `List<?>`. When the List case comes first and is unguarded, the ArrayList case is shadowed. This example helps show that **generics do not erase the subtype relationship** between List and ArrayList.

Another point to note: `case List<String> l` with a selector of type `Object` is generally invalid due to erased generic checking (*unchecked cast*). The **applicability** of a generic pattern is a separate issue from **dominance** between two already-valid patterns. Use `List<?>` in general examples because it is the appropriate pattern for checking for a List at runtime.

## 6. How can a `when` guard change dominance?

In Java 21, a `when` **guard** allows a case to be selected only when the pattern matches **and** the guard expression evaluates to true. If the guard can actually be false, an earlier parent-type case is **not guaranteed** to accept every child-type value.

Valid example:

~~~java
static String classify(Object value) {
    return switch (value) {
        case CharSequence cs when cs.length() >= 4 -> "LONG";
        case String s -> "STRING";
        case CharSequence cs -> "SHORT_SEQUENCE";
        default -> "OTHER";
    };
}
~~~

Walkthrough with values:

- `"abcdef"`: matches `CharSequence` and the guard is true, selecting `LONG`.
- `"abc"`: matches `CharSequence` but the guard is false; the switch **continues evaluating** `case String s` and selects `STRING`.
- `new StringBuilder("xy")`: guard is false, not a `String`, then matches the unguarded `CharSequence` case.
- `new StringBuilder("abcdef")`: guard is true on the very first case, selecting `LONG`.

Because the guard `cs.length() >= 4` is **not always true**, the later String case can still be selected and is therefore not completely shadowed. The rule is not "parent first is always an error", but rather **whether the earlier label actually dominates the later label under the language rules**.

### Runnable program: verifying guards

Save as **`GuardDominanceDemo.java`**:

~~~java
public class GuardDominanceDemo {

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case CharSequence cs when cs.length() >= 4
                    -> "LONG:" + cs.length();
            case String s -> "STRING:" + s;
            case CharSequence cs
                    -> "SHORT_SEQUENCE:" + cs.length();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("abc"));
        System.out.println(classify("abcdef"));
        System.out.println(classify(new StringBuilder("xy")));
        System.out.println(classify(new StringBuilder("abcdef")));
        System.out.println(classify(42));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac GuardDominanceDemo.java
java GuardDominanceDemo
~~~

Output:

~~~text
STRING:abc
LONG:6
SHORT_SEQUENCE:2
LONG:6
OTHER
NULL
~~~

What happens with `"abc"`? The first parent `CharSequence` case **matches the pattern**, but the guard is false, so the child String case still gets a chance to be tried. Note that the `cs` variable in the first case and the `cs` variable in the third case belong to **two different labels**; do not treat this as a single pattern variable shared across cases.

### Special case: `when true` can still cause dominance

Simply adding `when` does not make the compiler skip dominance checking:

~~~java
static String badGuard(Object value) {
    return switch (value) {
        case CharSequence cs when true -> "PARENT";
        case String s -> "CHILD"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

In Java 21, a constant `true` guard **does not eliminate dominance**: the earlier CharSequence case still accepts every String, so the later String case is dominated.

**Usage rule:** use `when` when there is a real business condition to check, not to work around a compiler error. If there is no real condition, change the case order.

## 7. The `Object` type pattern, `default`, and `null`

`Object` is the broadest type in Java's reference type system. On a selector of type `Object`, later cases can be shadowed if you put `case Object o` first:

~~~java
// INTENTIONALLY WRONG
return switch (value) {
    case Object o -> "ANY_OBJECT";
    case String s -> "STRING"; // COMPILE ERROR: dominated
};
~~~

However, there are **two things to distinguish**:

1. `case Object o` is an *unconditional type pattern* on an `Object` selector for matching reference values. It already covers all **non-null objects**, making more specific type patterns after it useless.
2. `case Object o` **does not automatically match a null selector** in Java 21. To handle null, write `case null`. When only `case Object o` is present and the input is null, the switch can throw `NullPointerException`.

Valid example:

~~~java
static String classifyAll(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "STRING";
        case Object o -> "OTHER_NON_NULL";
    };
}
~~~

Here `case String` comes before `case Object` so it is not shadowed; `case null` handles the null selector separately. No `default` is needed: on an `Object` selector, the `Object o` pattern is unconditional for the remaining values.

In practice, the compiler can also reject **combining** `case Object o` and `default` in the same switch because it has both an unconditional pattern and a default label. Therefore, if you want to cover "all remaining types", choose an appropriate label structure rather than automatically adding `default` after `case Object`.

Do not reason that "`Object` is the parent of all reference types, so `case Object` handles null" — **null is not an `Object` instance**.

## 8. Dominance and interfaces: there is not always a total order

Two types can **overlap** without either being a subtype of the other. For example, `CharSequence` and `Serializable` can both apply to `String`, yet not every CharSequence is Serializable and not every Serializable is a CharSequence.

Consider two labels:

~~~java
return switch (value) {
    case CharSequence cs -> "CHAR_SEQUENCE";
    case java.io.Serializable ser -> "SERIALIZABLE";
    default -> "OTHER";
};
~~~

With an `Object` selector, this order can be valid: the second case still has a chance to receive objects that are Serializable but **not** CharSequence. For a `String`, both type conditions hold, so the **first** case is selected.

Conversely, if the Serializable case comes first and `case String s` follows immediately after, then String **is dominated**, because **every String** is Serializable. The key difference is **full inclusion of the later pattern's entire value set**, not merely having a few objects in common between the two types.

Therefore, do not apply rules like "sort all interfaces alphabetically" or "interfaces always before classes". You must examine the actual type relationships and your classification intent.

## 9. Sealed hierarchies: exhaustiveness does not exempt dominance checking

In Java 17+, a `sealed interface` lets you restrict direct subtypes. In Java 21, a switch expression can use type patterns for each subtype to cover the hierarchy.

Self-contained **Java 21** example, save as `SealedDominanceDemo.java`:

~~~java
public class SealedDominanceDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c -> "CIRCLE:" + c.radius();
            case Rectangle r -> "RECT:"
                    + (r.width() * r.height());
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Rectangle(2, 4)));
    }
}
~~~

~~~bash
javac SealedDominanceDemo.java
java SealedDominanceDemo
~~~

Output:

~~~text
CIRCLE:3
RECT:8
~~~

`Circle` and `Rectangle` are the two subtypes declared in the `permits` list. The two labels above can form an **exhaustive switch expression** (for valid values in the hierarchy), without needing `default`.

Yet writing the parent type first is still invalid:

~~~java
static String badShape(Shape shape) {
    return switch (shape) {
        case Shape s -> "SHAPE";
        case Circle c -> "CIRCLE"; // COMPILE ERROR: dominated
    };
}
~~~

This is an **intentionally broken snippet** in the context where `Shape` and `Circle` are already declared. The `Shape` case covers every Circle, so the later `case Circle` is shadowed.

**Two distinct checks:**

- **Dominance:** is there any later label that can never be selected because an earlier label already covers it?
- **Exhaustiveness:** does the entire switch expression cover every selector value that needs to be handled?

An **exhaustive** switch can still be rejected due to dominance; a switch without dominance can still be missing cases and fail exhaustiveness.

In addition, if `shape == null` and there is no `case null`, a switch on a reference type can still throw `NullPointerException`. "Exhaustive over the subtypes" does not mean null is handled implicitly.

## 10. Parent-child type patterns vs. independent `instanceof` conditions

Many developers see this condition as valid:

~~~java
Object value = "Java";

if (value instanceof CharSequence cs) {
    System.out.println("A");
}
if (value instanceof String s) {
    System.out.println("B");
}
~~~

The two `if` statements are **independent**, so both can execute for a String. This is not a switch with mutually exclusive labels; Java does not impose the same dominance rule on independent `if` statements.

Even an `if / else if` chain with the broader condition first can compile:

~~~java
if (value instanceof CharSequence cs) {
    System.out.println("sequence");
} else if (value instanceof String s) {
    System.out.println("string");
}
~~~

The later `else if` branch will not execute when `value` is a String in this example flow, but that is **program logic analysis**, not the same compile-time rejection mechanism as switch pattern `case` labels.

Precisely because switch patterns are designed to select **a single applicable case label**, the compiler has dedicated dominance rules to explicitly catch shadowed labels.

## 11. Dominance is not applicability, matching, or a null error

Before fixing a compile error, identify the exact kind of error.

| Check | What does it ask? | Example |
| --- | --- | --- |
| **Applicability** | Is the pattern valid for the selector's **static type**? | Selector `String` with `case Integer n`: incompatible types |
| **Dominance** | Does an earlier case dominate a later case? | Selector `Object`, `case Number` before `case Integer` |
| **Exhaustiveness** | Does the switch expression have enough cases to produce a value for all applicable inputs? | Switch on `int` with only `case 1`, missing `default` |
| **Runtime matching** | Does the actual object match the pattern and guard? | `"Java"` matches `case String s` |
| **Null handling** | Does a null selector have an appropriate handling label? | `case null` handles null separately |

When the compiler reports "**this case label is dominated by a preceding case label**", adding an arbitrary guard, casting the selector to another type, or deleting `default` will not necessarily fix the issue. You need to look at which earlier label already covers every value that the failing label intends to catch.

A quick debugging method:

1. Identify the selector's static type to rule out applicability errors.
2. List the cases in their exact **order**.
3. For the failing case, ask: "is every value matching this label guaranteed to have already matched an **earlier** label?"
4. If yes, move the more specific case earlier or redesign the guards so the branches have distinct meanings.
5. After fixing dominance, re-check exhaustiveness and null handling.
6. Only after compilation succeeds should you inspect runtime data, case selection order, and expected output.

## 12. Common real-world mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Putting `case Object` first | Covers all non-null objects | Put specific cases first; Object at the end if needed |
| Putting `case Number` before `case Integer` | Integer is always a Number | Reverse the order |
| Putting `case CharSequence` before `case String` | String implements CharSequence | Reverse the order or use a genuinely needed guard |
| Putting `case Serializable` before `case String` | String implements Serializable | Put String before Serializable |
| Putting `case List<?>` before `case ArrayList<?>` | ArrayList is always a List | Put ArrayList before List |
| Using `when true` to dodge dominance | Guard is always true, still dominates child case | Do not use fake guards; reorder cases |
| Believing a parent type is only a direct `extends` class | Interfaces can also create dominance | Check the full type relationships |
| Assuming two patterns with some shared instances means dominance | Requires full inclusion, not mere overlap | Check whether the later case **still has any values it can match** |
| Assuming an exhaustive sealed switch cannot have dominance | Exhaustiveness and dominance are independent | Order child cases properly before parent cases |
| Assuming `case Object` catches null | Null is not an Object instance | Use `case null` |
| Using `default` after an unconditional `case Object` | Can violate switch label rules | Use a single valid coverage structure |
| Switching to `if` after hitting dominance without checking logic | May leave an unreachable branch | Redesign the classification order |

### Checklist when code-reviewing switch patterns

- Is any broad parent/interface label **placed before** a child-type label?
- Does every broad case have a guard that genuinely restricts the value set, or just `when true`?
- For labels of the same type with `when`, are more specific guarded branches placed before general ones?
- Is a generic wildcard/collection hierarchy (List/ArrayList/Collection) ordered incorrectly?
- Is a separate `case null` needed?
- Is the switch expression exhaustive?
- Do the branches actually represent distinct business cases rather than duplicates?

## 13. Self-check exercises

**Exercise 1 — Predict the error.** Given a selector of type `Object`:

~~~java
return switch (value) {
    case Number n -> "N";
    case Double d -> "D";
    default -> "O";
};
~~~

**Answer:** Does not compile. `Double` is a `Number`; the later Double case is dominated. Fix by placing `case Double d` before `case Number n`.

**Exercise 2 — Interface and class.**

~~~java
return switch (value) {
    case java.io.Serializable s -> "SER";
    case String text -> "TEXT";
    default -> "OTHER";
};
~~~

**Answer:** The String case is dominated because every String is Serializable. Move the String case earlier.

**Exercise 3 — Can a guard save the child case?**

~~~java
return switch (value) {
    case CharSequence cs when cs.length() > 5 -> "LONG";
    case String s -> "STRING";
    case CharSequence cs -> "OTHER_SEQ";
    default -> "OTHER";
};
~~~

**Answer:** Valid for a selector of type `Object` in Java 21. The first guard can be false for short Strings, so the later String case still has values it can match. The final unguarded CharSequence branch catches any remaining CharSequence values not yet handled.

**Exercise 4 — What does `when true` do?**

~~~java
return switch (value) {
    case CharSequence cs when true -> "SEQ";
    case String s -> "STR";
    default -> "OTHER";
};
~~~

**Answer:** Still a dominated case label error. A constant `true` guard does not allow the String case to receive any values.

**Exercise 5 — Object and null.** With a selector of type `Object`, structure:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s -> "STRING";
    case Object o -> "OBJECT";
};
~~~

**Answer:** Valid; covers null, String, and all remaining non-null objects. No `default` is needed. If you swap `case Object` before `String`, then `String` is dominated.

**Exercise 6 — Distinguishing two kinds of errors.** A `switch` has `case String` then `case CharSequence` without `default` when the selector has type `Object`.

**Answer:** This order of the two cases **does not cause dominance**, because the narrower String label precedes the broader CharSequence label. However, the switch expression is **not exhaustive** for all other Objects such as Integer; a case/default is needed to cover the rest.

## 14. Official documentation

The rules in this article follow the **Java SE 21** Java Language Specification:

- [JLS 21 — Section 14.11.1, Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): rules for case labels, dominance, and switch requirements.
- [JLS 21 — Section 14.30.3, Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): properties of patterns, including applicability and dominance.
- [JLS 21 — Section 15.28, Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expressions and exhaustiveness.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): pattern labels, `when` guards, dominance, and null cases.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): the feature finalized in Java 21.

**Key takeaway:** An unguarded **parent type pattern** can **dominate** a child type pattern that follows it because it already matches every object of the child type. Place **child cases before parent cases**; when using `when`, ensure the guard has a real condition and is ordered properly. Check dominance separately from applicability, exhaustiveness, and null handling.
