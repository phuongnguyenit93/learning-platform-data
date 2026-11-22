# Pattern Target and Target Static Type

> **Scope:** Java Core Pattern Matching → Pattern syntax. `instanceof` examples use Java 17+; `switch` and record pattern sections use Java 21+ (no preview required).

## Objectives

After this lesson, you will be able to identify what the **pattern target** value is, find the **static type** of the expression that provides that value, distinguish it from the **runtime type**, and predict when a pattern is accepted by the compiler, when a match succeeds, and what type the pattern variable has.

## 1. What Is a Pattern Target?

A **pattern** describes the condition for a value to match a desired structure/type, while also being able to extract components of that value. The **pattern target** is the **value being matched against the pattern**. In source code, we usually point to the **expression that provides the target**.

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Here:

- `value` (the left-hand operand of `instanceof`) is the **target expression**; its current value is the string object `"Java"`.
- `String text` (on the right of `instanceof`) is a **type pattern**: it checks whether it is a `String` and, if it matches, assigns that object to the variable `text`.
- The **static type of the target expression** `value` is `Object` because the variable is declared as `Object value`.
- The **runtime type** (actual type) of the object at runtime is `String`.
- The **type of the pattern variable** `text` is `String`, inferred from the pattern, not from the declared type of `value`.

You can visualize the flow:

~~~text
Target expression: value
    | Static type: Object ──[compiler checks: is the pattern applicable?]
    | Runtime value: "Java", String object
    v
Pattern: String text ────[runtime checks: does the object match String?]
    | true
    v
Variable text: String, initialized from target
~~~

**Terminology note:** “pattern target” here refers to the value undergoing matching. Do not confuse it with “target type” in *target typing* for lambda/poly expressions: that is a different concept in the Java type system.

## 2. Static Type and Runtime Type Play Different Roles

The **static type** of an expression is determined at compile time based on variable declarations, method return types, casts, or type inference rules. The **runtime type** (actual type) is the class of the object that the expression references at runtime; it may be a subclass or implementing class of the static type.

~~~java
Object a = "hello";         // Expression a has static type Object.
CharSequence b = "hello";   // Expression b has static type CharSequence.
String c = "hello";         // Expression c has static type String.
~~~

All three variables point to a `String` object, yet the compiler **does not treat `a`, `b`, and `c` as expressions with the same static type**. Therefore, the set of operations that can be called directly also differs: `a.length()` does not compile, while `b.length()` and `c.length()` do; meanwhile, `a instanceof String s` and `b instanceof String s` are valid type checks in Java 17.

| Target expression | Static type | Runtime value | Pattern tested | Result |
| --- | --- | --- | --- | --- |
| `Object x = "abc"; x` | `Object` | `String` | `String s` | Match succeeds |
| `CharSequence x = "abc"; x` | `CharSequence` | `String` | `String s` | Match succeeds |
| `Number n = Integer.valueOf(7); n` | `Number` | `Integer` | `Integer i` | Match succeeds |
| `Number n = Double.valueOf(7.5); n` | `Number` | `Double` | `Integer i` | Does not match |
| `Object x = null; x` | `Object` | `null` | `String s` | Does not match with `instanceof` |
| `Integer x = 7; x` | `Integer` | `Integer` | `String s` | Compile error: incompatible types |

The table shows **two independent questions**:

1. **Compile time:** Given the known static type, is the pattern check type-valid?
2. **Runtime:** If the check is valid, does the current target value actually match the pattern?

You cannot skip question (1) just because you “know for sure” what type the object has at runtime.

## 3. How Does the Compiler Check Pattern Applicability?

For a **type pattern** with reference type `U` (such as `String s`), Java checks whether the target's static reference type `T` can undergo a **checked cast** to `U` according to the language rules. If not, an error occurs at compile time. This is the core meaning of being **applicable at type T** in the JLS.

### 3.1. Possible Subtype: Valid, Match Depends on the Object

~~~java
Number number = Integer.valueOf(42);
if (number instanceof Integer i) {
    System.out.println(i + 1); // 43
}
~~~

`Number` is the static type, and `Integer` is the type to test. A `Number` value can actually be an `Integer`, so the test is valid. When the match succeeds, `i` has type `Integer` and can be used inside the `if` block.

### 3.2. Types That Cannot Be Converted by the Rules: Compile Error

The following snippet **intentionally does not compile**:

~~~java
Integer number = 42;
if (number instanceof String text) {  // ERROR: Integer cannot be a String
    System.out.println(text);
}
~~~

Both `Integer` and `String` are classes with no valid cast relationship here. The compiler does not need to wait until runtime to detect a meaningless test. Changing the numeric value cannot “fix” this error; you must revisit the type design or choose an appropriate pattern.

If the target is `Object`, the compiler allows checking for `String` because an `Object` can reference a `String`:

~~~java
Object value = Integer.valueOf(42);
System.out.println(value instanceof String); // false, but valid
~~~

### 3.3. Already-Specific Static Type and Version Differences

In **Java 17**, the following snippet is also a compile error because the type pattern test is unnecessary: the static type of `text` is already a subtype of the pattern type `String`.

~~~java
String text = "hello";
if (text instanceof String s) { // ERROR in Java 17
    System.out.println(s);
}
~~~

Here, use `text` directly. **The rules for unconditional patterns changed in later Java versions**, so do not apply the conclusion “every JDK rejects this” to modern code. When studying or compiling this lesson on Java 17, clearly distinguish this case from `Object x` needing a runtime check for `String`.

### 3.4. The Target Expression Does Not Have to Be a Variable

~~~java
static Object load() {
    return "ready";
}

if (load() instanceof String state) {
    System.out.println(state.toUpperCase());
}
~~~

The target expression is the call `load()`; its **static type** is its **declared return type** `Object`, not `String` just because the method body returns a string. The expression is evaluated, and then the returned value is matched. For dynamic input data, this rule is especially important.

`var` does not change this principle either:

~~~java
var first = "Java";          // first is inferred as String.
var second = (Object) "Java"; // second is inferred as Object.
~~~

The static type of `var` is inferred **at compile time** from the initializer, and does not keep changing according to objects assigned later.

## 4. Java 17 Example: Same Static Type, Multiple Runtime Outcomes

Save the following code to **`PatternTargetDemo.java`**:

~~~java
public class PatternTargetDemo {
    static void describe(Object target) {
        if (target instanceof String text) {
            System.out.println("String: " + text + ", length=" + text.length());
        } else if (target instanceof Integer number) {
            System.out.println("Integer: " + (number * 2));
        } else if (target == null) {
            System.out.println("null");
        } else {
            System.out.println("Other: " + target.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        describe("Java");
        describe(Integer.valueOf(21));
        describe(Double.valueOf(2.5));
        describe(null);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 PatternTargetDemo.java
java PatternTargetDemo
~~~

**Exact stdout:**

~~~text
String: Java, length=4
Integer: 42
Other: Double
null
~~~

On each call, the target expression inside `describe` still has static type **`Object`** because the parameter is declared that way. However, the runtime values are `String`, `Integer`, `Double`, and `null` respectively. The branch is selected based on the runtime value, after the compiler has confirmed that each test is valid for type `Object`.

**No manual cast needed:** Once `target instanceof String text` succeeds, `text` already has type `String`. There is no need to write `(String) target`.

## 5. Pattern Variable Type and Scope

A pattern variable has the type declared in the pattern and is only definitely in scope on branches where the compiler proves the pattern has matched (also known as **flow scoping**).

~~~java
static int nonBlankLength(Object target) {
    if (target instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
~~~

With the `&&` operator, the right-hand operand is only evaluated when `target instanceof String text` is `true`; therefore, `text` is initialized before `text.isBlank()` is called. Outside the branch where the match is guaranteed, you cannot arbitrarily access `text`. The following example **intentionally does not compile**:

~~~java
if (target instanceof String text) {
    System.out.println(text.length());
}
System.out.println(text); // ERROR: not within the guaranteed match scope
~~~

Do not confuse the type of the **target** (such as `Object`) with the type of the **pattern variable** (`String`). A pattern variable does not change the declared type of the target variable; it simply gives you a new name with the checked type.

## 6. Static Types and Generics: Do Not Assume Type Arguments at Runtime

Due to **type erasure**, you cannot arbitrarily test an `Object` using a type pattern with concrete non-reifiable type arguments. Example that **intentionally fails to compile**:

~~~java
Object target = java.util.List.of("a", "b");
if (target instanceof java.util.List<String> strings) { // ERROR
    System.out.println(strings.get(0));
}
~~~

A valid check when you only need to know that the target is a list:

~~~java
Object target = java.util.List.of("a", "b");
if (target instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
~~~

`List<?>` does not guarantee that elements are `String`. When you need to process elements, retrieve each value with a safe static type (`Object`) and check further, for example `item instanceof String s`. Some generic cases can be proven safe by the compiler from the **specific static type of the target**, so evaluate the actual checked cast rules instead of mechanically memorizing that “all generic patterns are forbidden”.

## 7. Target in `switch` and Record Patterns (Java 21+)

In a pattern `switch`, the **selector expression** of the `switch` provides the target. The compiler uses the selector's static type to check the `case` patterns; at runtime, the selector's value determines which pattern matches. With a **record pattern**, a target can also be deconstructed into **sub-targets** corresponding to the record components. The declared type of each record component determines the applicability of nested patterns.

Save the following code to **`PatternTargetSwitchDemo.java`** and run it with **JDK 21+**:

~~~java
public class PatternTargetSwitchDemo {
    record Point(int x, int y) {}

    static String describe(Object target) {
        return switch (target) {
            case null -> "null";
            case String s when s.isEmpty() -> "empty String";
            case String s -> "String length=" + s.length();
            case Point(int x, int y) -> "Point=" + x + "," + y;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("abc"));
        System.out.println(describe(""));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(Integer.valueOf(9)));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 21 PatternTargetSwitchDemo.java
java PatternTargetSwitchDemo
~~~

**Exact stdout:**

~~~text
String length=3
empty String
Point=2,5
other
null
~~~

Analysis:

- The selector `target` has **static type `Object`**, so both `case String s` and `case Point(int x, int y)` are applicable.
- When the runtime value is a `Point`, the record pattern checks that the target is a `Point` and reads its two components; the **static type of each component is `int`**, so `x` and `y` are pattern variables of type `int`.
- `case String s when s.isEmpty()` is a guarded pattern: first it must match `String`, and then the `isEmpty()` condition must be true. The following `case String s` handles the remaining strings.
- `null` does not match ordinary type patterns. `case null` is declared explicitly; without `null` handling, passing `null` into an ordinary pattern `switch` can throw a `NullPointerException` even when `default` is present.
- `switch` has **dominance** rules. If you place `case CharSequence cs` before `case String s` on an `Object` selector, the subsequent `String` branch is dominated and the compiler reports an error because it can never be selected.

Nested structure example illustrating only the sub-target rule (Java 21+; place inside an appropriate class/method):

~~~java
record Envelope(Object payload) {}
Object target = new Envelope("ok");
if (target instanceof Envelope(String contents)) {
    System.out.println(contents.toUpperCase()); // OK
}
~~~

In the outer pattern, the target has static type `Object`; after matching `Envelope`, the `payload` value becomes the target for the inner pattern `String contents`. Because the record declares `payload` as `Object`, the compiler allows testing for `String`. If a record declares a component with a type incompatible with the corresponding pattern, the code is rejected at compile time.

## 8. How to Analyze a Pattern Expression Yourself

When encountering a piece of pattern matching code, follow this order:

1. **Identify the target expression:** on the left of `instanceof` or inside `switch (...)`. For record patterns, also identify each extracted component.
2. **Determine the static type:** check the variable declaration, method signature, inferred type of `var`, or record component type. Do not use `getClass()` as a substitute for this step.
3. **Read the pattern's type:** for example `String s`, `Integer n`, or `Point(int x, int y)`. Check checked cast / applicability, generic restrictions, and for `switch` check dominance and exhaustiveness of the branches.
4. **Consider the runtime value:** `null` or a specific object? A syntactically valid pattern may still fail to match.
5. **Identify created variables and scope:** pattern variables can only be used where the match is guaranteed; with guards / `&&`, consider the execution path.

### Common Mistakes

- **“If the runtime target is a String, the compiler always accepts a String pattern.”** False: static type and applicability rules must be checked first; for example, `Integer n instanceof String s` is rejected.
- **“The pattern variable has the same type as the target expression.”** False: `Object obj instanceof String s` gives `s` the type `String`.
- **“A valid match always returns true.”** False: `Number n` can point to a `Double`, so `n instanceof Integer i` returns `false`.
- **“Having default means switch already catches null.”** Not true for ordinary Java 21 pattern `switch`; handle `null` according to your business requirements.
- **“List<String> can always be verified with instanceof.”** No: type erasure and reifiability / checked cast rules restrict which tests can be written.
- **“A pattern variable can be used anywhere after if.”** False: scope depends on the branch where the match is proven.

## 9. Self-Check

**Question 1.** Given `Object value = "42";`, in `if (value instanceof String s)`, identify the target's static type, runtime type, and the type of `s`.

**Question 2.** Given `Number n = Double.valueOf(3.5);`, is `n instanceof Integer i` a compile error or valid returning `false`? What if `n` is changed to `Integer.valueOf(3)`?

**Question 3.** Explain why `Integer x = 1; x instanceof String s` is a compile error, whereas `Object x = 1; x instanceof String s` compiles but returns `false`.

**Question 4 (Java 21).** In `switch (Object target)`, why does placing `case CharSequence cs` before `case String s` make the second branch invalid? When `target == null`, does `default` handle it automatically?

**Answers:** (1) `Object` / `String` / `String`. (2) Valid, `false` for `Double` and `true` for `Integer`. (3) Static type `Integer` has no valid checked cast conversion to `String`, whereas `Object` can hold a `String` so the compiler allows the runtime check. (4) `CharSequence` covers every `String`, causing the later branch to be dominated; `null` requires explicit handling (such as `case null`).

## References

- [Java Language Specification 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, applicability at static types, runtime matching, dominance.
- [Java Language Specification 21, `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): pattern testing and target type checking.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): selector type, guard, null, dominance.
- [Java Language Specification 17, `15.20.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): Java 17 `instanceof` rules and cases where the pattern type is too broad for the static type.
