# Selector Expression of Pattern Switch in Java 21+

## 1. What Is a Selector Expression?

In a `switch` statement or expression, the **selector expression** is the expression inside the parentheses immediately following the `switch` keyword:

```java
Object value = "Java";

String result = switch (value) {
    case String text -> "text:" + text;
    case Integer number -> "number:" + number;
    default -> "other";
};
```

In this example, **`value` is the selector expression**; the object it evaluates to is the **selector value**. The `case` branches below are **case labels**. A pattern switch uses the selector value to attempt matching patterns, such as `String text` or `Integer number`, and then executes the matching branch.

Three components should not be confused:

- **Selector expression**: the part evaluated once to obtain the value passed into `switch`, such as `value`, `loadInput()`, or `request.payload()`.
- **Selector type**: the static type of that expression at compile time, such as `Object`, `Shape`, or `String`.
- **Case label/pattern**: the branch selection condition, such as `case String text`, `case null`, `case Circle(double r)`, or `default`.

In the code above, `value` has the static type `Object`, while its runtime value is a `String`. The pattern `String text` matches; the variable `text` is treated by the compiler as a `String` within that branch. The `switch` expression returns `"text:Java"`.

**Version requirement:** pattern matching for `switch` was standardized in **Java 21 (JEP 441)**, without needing `--enable-preview`. The demonstration programs below use Java 21+. Traditional `switch` has existed since early Java, but `switch` with type/record patterns introduces newer rules regarding selector types, `null`, and exhaustiveness.

## 2. What Kinds of Expressions Can a Selector Be?

A selector can be a variable, a method call result, a field/property access, the result of a conditional expression, or another Java expression with a **valid type** for `switch`. A selector does not have to be a variable name.

```java
Object input = "Java";

String a = switch (input) {
    case String s -> s;
    default -> "?";
};

String b = switch (getInput()) {
    case String s -> s;
    default -> "?";
};

String c = switch (condition ? valueA : valueB) {
    case Integer n -> "int:" + n;
    case String s -> "str:" + s;
    default -> "other";
};
```

This snippet is **illustrative syntax**: appropriate declarations for `getInput()`, `condition`, `valueA`, and `valueB` are required in a real context.

Important rules:

1. Java evaluates the **entire selector expression once** when starting `switch` execution, then uses the result to select a branch. It does not re-evaluate the expression each time a `case` is tested.
2. If the selector contains a method call with side effects, those side effects occur when the selector is evaluated. The evaluation order still follows Java's normal expression evaluation rules.
3. If evaluating the selector throws an exception, `case` selection does not take place; the exception propagates according to Java's exception mechanism.
4. Once the selector value is obtained, Java matches the applicable labels in order according to `switch` rules, including `when` conditions if present.

Prefer readable selectors with minimal side effects. When a complex computation is needed in multiple places, you can store it in a variable first and then `switch` on that variable; this makes the code easier to read and debug.

## 3. The Static Type of the Selector Determines Which Patterns Are Valid

The runtime value determines **which branch matches**, while the static type of the selector helps the compiler determine **which `case` labels can apply** and **whether the branches cover all cases**.

### When the Selector Has Type `Object`

```java
Object input = 42;

String description = switch (input) {
    case String s -> "string:" + s;
    case Integer n -> "integer:" + n;
    case Number n -> "number:" + n;
    default -> "other";
};
```

This is a valid example on Java 21: `Object` is broad enough to reference a `String`, `Integer`, or `Number`. The value `42` is autoboxed to `Integer` when assigned to `Object`, so the `Integer n` branch matches and the expression returns `"integer:42"`.

Place `case Integer n` **before** `case Number n`, because `Integer extends Number`. If `case Number n` were placed first, the `Number` pattern would cover every `Integer`, and the subsequent `Integer` branch could never be selected; the compiler detects a dominance error.

### When the Selector Already Has a Narrow Type

```java
String input = "abc";

String result = switch (input) {
    case String text -> text.toUpperCase();
};
```

In this case, every non-`null` `String` value matches the `String text` pattern. The compiler can treat that pattern as sufficiently covering all non-`null` values of the selector. If `input == null` and there is no `case null` branch, a `NullPointerException` can still occur.

You cannot arbitrarily put `case Integer n` into a switch on `String`: the type relationship between the selector and the pattern must allow matching. Similarly, a selector with a `sealed` type enables the compiler to compute the subtypes that must be covered (see Section 8).

Key takeaway: **the selector type defines the feasible selection scope at compile time; the selector value determines the branch executed at runtime.** A pattern variable like `text` or `n` has the static type declared by the pattern, and does not change the declared type of the original selector variable.

## 4. Selector Types Supported by Java 21

In traditional `switch`, the familiar selector types are `byte`, `short`, `char`, `int` (and their corresponding wrappers), `String`, and `enum`. Java 21's pattern switch extends support to **reference types** such as `Object`, interfaces, records, classes, arrays, or a `sealed` type as the selector.

Example of a custom interface used as a selector:

```java
sealed interface Message permits TextMessage, ErrorMessage {}

record TextMessage(String text) implements Message {}
record ErrorMessage(int code) implements Message {}

static String describeMessage(Message msg) {
    return switch (msg) {
        case TextMessage(String text) -> text;
        case ErrorMessage(int code) -> "error:" + code;
    };
}
```

This is an **illustrative snippet** and must be placed inside a class or context containing valid declarations. Because `Message` is `sealed`, the two patterns above cover the permitted implementations (for non-`null` selector values), so `default` is not required.

**Version limitation:** in standard Java 21, `long`, `float`, `double`, and `boolean` are not supported primitive selector types like `int`. Switch enhancements for primitives appear in newer/preview versions; do not include them in stable Java 21 practice exercises. If you need to handle `long` with a Java 21 pattern switch, you can place a `Long` object in an `Object` selector and match `case Long n`, but that is a switch on a **reference**, not a direct switch on the primitive `long`.

Example:

```java
Object amount = 12L;
String kind = switch (amount) {
    case Long n -> "long:" + n;
    default -> "other";
};
```

Here the result is `"long:12"`; the selector `amount` has type **`Object`**, and the runtime value is **`Long`**. Distinguish `switch (amount)` from `switch (primitiveLong)` when reading version-specific rules.

## 5. Pattern Processing Order: Type Matching, Guard, Then Branch Selection

Suppose the selector has type `Object`:

```java
static String classify(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text when text.isBlank() -> "blank";
        case String text -> "text:" + text;
        case Integer n -> "int:" + n;
        default -> "other";
    };
}
```

This is an illustrative method that runs in Java 21+.

- First, Java obtains the result of the selector `input`.
- If the result is `null`, the `case null` branch is handled.
- For a `String` value, the compiler and runtime allow `String text` to match, then evaluate the guard `text.isBlank()` in the branch with `when`.
- If the string is not blank, the first guard returns `false`; Java continues checking the unguarded `case String text` branch.
- For an `Integer` value, the `case Integer n` branch matches.
- For any remaining type, `default` is used.

The variable `text` has type `String` and is only in scope where the corresponding pattern is guaranteed to have matched. A `when` guard **does not change the selector value** and does not re-evaluate the selector expression. It only adds a condition to a branch whose pattern has already matched.

**Dominance:** an overly general branch placed earlier can shadow a specific branch and cause a compilation error. For example:

```java
// Incorrect: the Number pattern covers Integer as well, so Integer below is dominated.
// return switch (input) {
//     case Number n -> "number";
//     case Integer i -> "integer"; // dominated
//     default -> "other";
// };
```

If you need to prioritize `Integer`, place that case before `Number`. When `when` is used, ordering also depends on the guard condition. Always ensure intentionally specialized branches appear in the appropriate position.

## 6. Complete Program: Selector, Pattern, Guard, and Null

Save the following code to **SelectorExpressionDemo.java**. The program runs on **JDK 21 and later** using stable Java 21 syntax.

```java
public class SelectorExpressionDemo {
    sealed interface Shape permits Circle, Rectangle {}
    record Circle(double radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static int selectorCalls;

    static Object readOnce() {
        selectorCalls++;
        return " Java ";
    }

    static String fromSelectorExpression() {
        return switch (readOnce()) {
            case String text -> "text:" + text.trim();
            default -> "other";
        };
    }

    static String describe(Object selector) {
        return switch (selector) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.trim();
            case Integer count -> "int:" + count;
            case Circle(double radius) -> "circle:" + radius;
            case Rectangle(int width, int height) ->
                    "rectangle:" + width + "x" + height;
            default -> "other";
        };
    }

    static String describeShape(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> "circle";
            case Rectangle(int w, int h) -> "rectangle";
        };
    }

    static String noNullCase(Object value) {
        return switch (value) {
            case String text -> "string";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(fromSelectorExpression());
        System.out.println("selectorCalls:" + selectorCalls);
        System.out.println(describe("   "));
        System.out.println(describe(5));
        System.out.println(describe(new Rectangle(3, 4)));
        System.out.println(describe(new Circle(2.5)));
        System.out.println(describe(null));
        System.out.println(describe(new Object()));
        System.out.println(describeShape(new Circle(1)));

        try {
            noNullCase(null);
        } catch (NullPointerException expected) {
            System.out.println("nullWithoutCase:NPE");
        }
    }
}
```

Compile and run:

```bash
javac SelectorExpressionDemo.java
java SelectorExpressionDemo
```

Exact output:

```text
text:Java
selectorCalls:1
blank
int:5
rectangle:3x4
circle:2.5
null
other
circle
nullWithoutCase:NPE
```

Part-by-part explanation:

- `switch (readOnce())` is an example of a **method call** selector. `readOnce()` increments the counter and returns a string. The first two lines confirm that the selector is evaluated once in this invocation.
- `describe("   ")` encounters a `String` and satisfies the `isBlank()` guard, so it returns `"blank"`; only non-blank strings reach the subsequent `String text` case.
- `describe(5)` passes a boxed `Integer` object through the `Object` parameter and matches `case Integer count`.
- `Rectangle(int width, int height)` and `Circle(double radius)` are **record patterns**: they extract the components of the selector value when the record matches.
- `describe(null)` executes the `case null` branch; `describe(new Object())` executes `default`.
- `describeShape(new Circle(1))` works with a selector of static type `Shape` and does not need `default` because the sealed interface's subtype list is fully covered.
- `noNullCase(null)` demonstrates that without `case null`, `default` does **not** automatically catch `null`; the `NullPointerException` is caught by the caller so the program continues running.

## 7. Null Is a Special Case of the Selector

With Java 21 pattern switches, `null` handling must be understood right at the selector:

```java
static String format(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> s.toUpperCase();
        default -> value.toString();
    };
}
```

- `case null` is the label that matches a selector value equal to `null`.
- Ordinary type/record patterns such as `String s` or `Point(int x, int y)` do not replace `null` handling at the selector level.
- **`default` does not catch `null`** under Java 21 reference-type `switch` rules. If `case null` is omitted and the selector evaluates to `null`, `switch` throws `NullPointerException` before reaching the `default` branch.
- Even if a switch has patterns covering every **non-`null`** value, that does not mean `null` is handled.
- You can use the special combined label `case null, default -> ...` in appropriate situations to handle both groups; however, separating `case null` is often more readable when missing data needs to be distinguished.

If a selector can be `null` because a method may return it, decide explicitly whether the business logic should **handle `null` in its own branch** or treat it as an error. Do not simply add `default` and assume the risk of `NullPointerException` has been eliminated.

A nested record pattern requires an additional distinction: the selector may be a non-`null` record whose inner component is `null`. When that component is matched with a nested record pattern, the match may fail and fall through to a later branch; this is different from the selector **itself** being `null`.

## 8. Sealed Selectors and Exhaustiveness

The static type of the selector is especially important with `sealed interface`/`sealed class`.

```java
sealed interface Result permits Success, Failure {}
record Success(String data) implements Result {}
record Failure(int code) implements Result {}

static String display(Result input) {
    return switch (input) {
        case Success(String data) -> data;
        case Failure(int code) -> "error:" + code;
    };
}
```

In this illustration, `Result` permits only `Success` and `Failure` to directly implement it; both patterns are written, so the compiler proves the exhaustiveness of the switch over all non-`null` values of type `Result`. No `default` is needed for a **switch expression** to compile.

If a new valid subtype is added to the sealed interface without updating the switch branches to cover it, the code may require adding a branch at compile time. This is an advantage when modeling a finite set of cases with a sealed hierarchy.

**Two things to remember:**

1. The compiler checks exhaustiveness based on the selector's static type, the patterns, and the branches that can cover them; it does not test every object at runtime to guess.
2. Type exhaustiveness **does not automatically include `null`**: calling `display(null)` still causes a `NullPointerException` if there is no `case null`.

Conditional `when` guards are not considered always true for all values of a type; if you only have guarded branches and omit the rest, the switch may not be exhaustive.

## 9. Selector in Switch Expressions vs. Switch Statements

Both forms have a selector expression, but their purposes differ:

A **switch expression** produces a value:

```java
Object input = 10;
String result = switch (input) {
    case Integer n -> "int:" + n;
    default -> "other";
};
```

A **switch statement** performs an action:

```java
static void printKind(Object input) {
    switch (input) {
        case String s -> System.out.println(s);
        case Number n -> System.out.println(n);
        default -> System.out.println("other");
    }
}
```

For a switch expression, every valid path must yield a value (or complete abruptly, such as by throwing an exception); the compiler requires **exhaustiveness**. For a switch statement with patterns (an enhanced switch statement in Java 21), the compiler also requires full coverage of all non-`null` selector values. For example, having only `case String s` when the selector has type `Object`, with no other branch, is rejected because it does not cover all cases.

Arrow branches (`->`) avoid fall-through into the next branch. The classic `case ...:` form still exists, but has its own restrictions when combined with pattern variables to prevent control-flow paths from using unmatched variables. For pattern switch exercises, `->` is easier to follow.

What they share is that **the selector expression is evaluated first**, and only then is a matching branch selected. Choosing a statement or an expression does not change the meaning of the selector.

## 10. Common Mistakes When Writing Selector Expressions

| Misconception | Correct understanding and fix |
| --- | --- |
| Thinking `case String s` is the selector. | The selector is the expression after `switch`; `case String s` is a pattern label matched against the selector value. |
| Assuming the selector is re-evaluated for each `case`. | The selector expression is evaluated once per switch execution; guards may run afterward, but they do not re-invoke the selector. |
| Thinking `Object value` cannot be used as a selector. | Java 21 pattern switch supports reference-type selectors like `Object`, allowing multiple type patterns to be tested. |
| Thinking the runtime value changes the selector's static type. | The static type is used to check labels at compile time; the runtime value determines which pattern matches. |
| Placing `case Number n` before `case Integer i`. | The general `Number` branch covers `Integer`, causing dominance over the later branch; place specialized branches first. |
| Believing `default` will receive a `null` selector. | `default` does not replace `case null` in Java 21 pattern switches; an NPE can occur. |
| Writing only `case String s` for an `Object` selector. | An enhanced switch still has non-`String` value cases; add other cases or `default` for exhaustiveness. |
| Using primitive `long`/`boolean` selectors like `int` in Java 21. | Stable Java 21 does not support these primitive selectors in standard switch; newer preview versions introduce separate extensions. |
| Calling a method with side effects in the selector and expecting it to run at each branch. | Selector side effects occur only when the initial expression is evaluated; do not rely on repeated evaluation. |
| Confusing pattern matching with `==` equality comparison. | Type/record patterns check type, structure, and guard conditions; they do not merely compare an object to a constant. |

One notable design mistake is trying to cram too much business logic into an overly complex selector:

```java
// Illustrative syntax; these methods must be declared in a real program.
return switch (load().transform().getValue()) {
    case String s -> s;
    default -> "other";
};
```

If there are multiple steps that can throw errors or produce side effects, consider extracting them:

```java
// Illustrative syntax; the type of input must be an appropriate reference type.
Object input = loadValue();
return switch (input) {
    case String s -> s;
    default -> "other";
};
```

Extracting a variable makes it easier to set breakpoints, add controlled logging, and distinguish selector evaluation errors from branch-handling errors.

## 11. Self-Check Exercises

### Exercise 1 — Which Selector Is Evaluated?

```java
static int calls;
static Object next() {
    calls++;
    return 7;
}

static String classify() {
    return switch (next()) {
        case String s -> "text";
        case Integer n -> "number:" + n;
        default -> "other";
    };
}
```

If initially `calls = 0`, what does calling `classify()` once return, and what is `calls`?

**Answer:** it returns `"number:7"`; `calls == 1`. The entire selector `next()` is evaluated once. The `Integer n` branch matches because `next()` returns an `Integer` autoboxed from `7`.

### Exercise 2 — Handling Null

```java
static String format(Object data) {
    return switch (data) {
        case String s -> s;
        default -> "other";
    };
}
```

Does calling `format(null)` return `"other"`?

**Answer:** no. Under Java 21, a `null` selector in this switch causes a `NullPointerException`. To return `"missing"`, add the branch `case null -> "missing";`.

### Exercise 3 — How Static Type Affects Cases

Why can a switch on `Object` have `case String s` and `case Integer n`, whereas you cannot arbitrarily place `case Integer n` in a switch whose selector has static type `String`?

**Answer:** an `Object` selector can reference many different classes; a static type `String` cannot be an `Integer` under Java's type hierarchy. The compiler checks compatibility at compile time, before any runtime value exists.

### Exercise 4 — Exhaustiveness with a Sealed Hierarchy

Given:

```java
sealed interface Action permits Create, Delete {}
record Create(String id) implements Action {}
record Delete(String id) implements Action {}
```

Write a switch expression that takes `Action action` and returns `"create:<id>"` or `"delete:<id>"`.

**Solution** (in a context containing the record declarations):

```java
static String describeAction(Action action) {
    return switch (action) {
        case Create(String id) -> "create:" + id;
        case Delete(String id) -> "delete:" + id;
    };
}
```

The two record patterns cover all direct subtypes permitted by the sealed interface. For `action == null`, the switch still throws `NullPointerException` unless `case null` is added.

## 12. Key Takeaways

**The selector expression is the expression inside `switch (...)`; it is evaluated once to obtain the value used to select a branch.** The static type of the selector determines which patterns are valid and affects compile-time exhaustiveness checking; the runtime value and guards determine the executed branch.

In Java 21, pattern switch supports broad reference-type selectors such as `Object`, interfaces, records, and sealed hierarchies. Handle `null` intentionally with `case null` when business logic allows it. Order specific patterns properly to avoid dominance, and ensure the branches cover all selector values.

References:
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
