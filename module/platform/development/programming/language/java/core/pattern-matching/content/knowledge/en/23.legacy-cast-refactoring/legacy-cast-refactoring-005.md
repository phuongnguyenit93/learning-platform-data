# Refactoring Null Checks with Type Checks in Java Pattern Matching

When maintaining legacy Java code, a common pattern is **checking for `null`, checking the type with `instanceof`, and then casting to use the object**. Since Java 16, *pattern matching for `instanceof`* lets you combine the type check and typed variable declaration, thereby simplifying many redundant `null` checks. When refactoring, the goal is to **preserve behavior for all inputs**, especially distinguishing between `null`, an incompatible type, and an object of the right type whose content is invalid.

This lesson focuses on legacy code containing `if`, `instanceof`, and casts. The main example uses **Java 17** (and also runs on Java 21+); `instanceof` type patterns have been a standard feature since Java 16 (JEP 394), requiring no preview flags.

## 1. From Three Operations to a Single Check

Legacy code:

```java
Object input = "  Java  ";

if (input != null && input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip()); // Java
}
```

Refactored code:

```java
if (input instanceof String text) {
    System.out.println(text.strip()); // Java
}
```

How to read `input instanceof String text`:

1. Checks whether the value of `input` is a `String` object.
2. If it succeeds, creates a pattern variable `text` with static type `String` pointing to the same object.
3. The variable `text` is usable inside the `if` branch when the compiler proves the pattern has definitely matched.
4. If it does not match, the `if` branch does not execute; no cast is needed.

**Why can `input != null` be removed?** By the semantics of `instanceof` in Java, a `null` value **does not match** a type pattern. The expression `null instanceof String text` evaluates to `false`. Therefore:

```java
input != null && input instanceof String
```

and:

```java
input instanceof String text
```

make the same decision on **whether to enter the branch** when the goal is simply checking for `String`. The latter version also provides the pre-type-checked variable `text`.

**Important limitation:** this equivalence applies when the `null` check only guards the type check/cast. If the legacy code handles `null` separately to log, return a different error, or throw a different exception, you must keep that branch when refactoring.

## 2. Behavior Table of instanceof with null

Consider `Object input` and the condition `input instanceof String text`:

| Value of `input` | `instanceof` result | Does the true branch run? |
| --- | --- | --- |
| `null` | `false` | No |
| `"Java"` | `true` | Yes, `text = "Java"` |
| `""` (empty string) | `true` | Yes, `text = ""` |
| `"   "` (whitespace only) | `true` | Yes, `text` contains whitespace |
| `Integer.valueOf(7)` | `false` | No |

An **`instanceof` result does not mean data validation**. An empty string is still a `String`; only add a separate condition when you need to reject empty or blank strings.

Common conditions:

```java
input != null && input instanceof String  // Can be replaced with a type pattern.
input instanceof String                    // false if input == null.
input instanceof String text              // false if input == null; provides variable text when matched.
```

Do not confuse this with calling `input.getClass()`, `input.toString()`, or casting and accessing a property: method calls on `null` can throw `NullPointerException`, whereas a standalone `instanceof` check does not.

## 3. Refactoring Null Check + Type Check + Business Condition

A legacy example checking for a non-blank string:

```java
static String legacyLabel(Object input) {
    if (input != null && input instanceof String) {
        String text = (String) input;
        if (!text.isBlank()) {
            return "text=" + text.strip();
        }
    }
    return "unavailable";
}
```

Pattern matching version:

```java
static String modernLabel(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return "text=" + text.strip();
    }
    return "unavailable";
}
```

In the new version:

- `input instanceof String text` both checks the type and binds `text`.
- The `&&` operator uses **short-circuit evaluation**: `!text.isBlank()` is only called when the left-hand side is true, so `text` is non-null.
- The "not blank" business condition is preserved; the new code does not accidentally accept `"   "`.
- `String.isBlank()` and `String.strip()` have been supported since Java 11; this example runs on Java 17.
- `strip()` may return a new string but does not modify the original `String` value.

Comparing cases: for `null`, an integer, or a whitespace-only string, both methods return `"unavailable"`. For `"  Java  "`, both return `"text=Java"`.

If a length constraint is needed, write it the same way:

```java
if (input instanceof String text
        && !text.isBlank()
        && text.length() <= 20) {
    System.out.println(text.strip());
}
```

The second and third operands only execute when `text` is already bound, so there is no need to repeat `text != null`. However, you may still need to check **inner reference fields** of an object if they can be `null`.

## 4. Refactoring Guard Clauses: Check Invalid Then Return

Legacy code often rejects invalid-type inputs before casting:

```java
static int legacyLength(Object input) {
    if (input == null || !(input instanceof String)) {
        return -1;
    }
    String text = (String) input;
    return text.length();
}
```

This can be rewritten as:

```java
static int modernLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Why is `text` usable **after** the `if`?

1. `input instanceof String text` is `true` only when the input matches `String`.
2. The negation `!(...)` is true when it does not match, in which case the method immediately executes `return -1`.
3. Every execution path reaching `return text.length()` has already matched the `instanceof` expression.
4. The compiler allows using `text` here thanks to **flow scoping / definite matching**.

Both `modernLength(null)` and `modernLength(42)` return `-1`; `modernLength("abc")` returns `3`. `String text = (String) input;` is no longer needed.

A similar pattern with `throw`:

```java
static String requireString(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text;
}
```

The example above intentionally combines `null` and invalid types into **the same** error, matching the negated condition. If the legacy code throws a different exception for `null`, you must preserve that distinction.

## 5. Combining Negation with || to Reject Empty Data

For a failed-check condition, Java still allows using the pattern variable on the right-hand side of `||` if the negated left-hand side **is only false when the match succeeds**:

```java
static String validate(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "invalid";
    }
    return "valid=" + text.strip();
}
```

How it works:

- When `input` is `null` or not a `String`, `!(input instanceof String text)` is true; `||` skips `text.isBlank()` and returns `"invalid"`.
- When the input is a `String`, the negation is false, so `text` is definitely bound; only then is `text.isBlank()` called.
- If `text` is not blank, the entire condition is false and execution proceeds to `return "valid=" + text.strip()`.

Results: `validate("  ")` returns `invalid`; `validate(" ABC ")` returns `valid=ABC`; `validate(null)` returns `invalid`.

**Avoid a common mistake with `||`:**

```java
// WRONG — does not compile because the right-hand side may run when s has not matched.
// if (input instanceof String s || s.isEmpty()) {
//     System.out.println(s.length());
// }
```

With `a || b`, `b` is only evaluated if `a` is false. Thus the pattern `String s` is **not** guaranteed at `s.isEmpty()` in the broken snippet. Conversely, `!(input instanceof String s) || s.isEmpty()` is valid because the negated left-hand side being false means the inner pattern succeeded.

## 6. When null Must Have Distinct Behavior: Do Not Remove the Branch

Not every null check is redundant. Suppose the system requires distinguishing three cases:

- `null` means the data is **missing**.
- A `String` is valid-type data.
- A value of another type indicates **wrong type** data.

Correct refactored pattern:

```java
static String distinguishNull(Object input) {
    if (input == null) {
        return "missing";
    }
    if (input instanceof String text) {
        return "string=" + text;
    }
    return "other type";
}
```

If you remove `if (input == null)` and only use `input instanceof String text`, `null` will fall into the `"other type"` branch, **breaking the contract**.

In particular, keep a separate branch when the legacy code:

- Throws `NullPointerException` or `IllegalArgumentException` with a specific message for `null`.
- Logs/records different metrics between "no data" and "wrong data type".
- Returns a distinct error code / API response for a missing value.
- Uses a default value or runs separate business logic when `null`.

Only remove a null check if the **observable behavior** after refactoring remains the same as before.

## 7. Combining Multiple Type Checks in if / else if

From legacy code:

```java
static String oldClassify(Object input) {
    if (input != null && input instanceof String) {
        String text = (String) input;
        if (!text.isEmpty()) {
            return "string length=" + text.length();
        }
    } else if (input != null && input instanceof Integer) {
        Integer n = (Integer) input;
        if (n > 0) {
            return "positive integer=" + n;
        }
    }
    return "other";
}
```

Can be converted to:

```java
static String classify(Object input) {
    if (input instanceof String text && !text.isEmpty()) {
        return "string length=" + text.length();
    } else if (input instanceof Integer n && n > 0) {
        return "positive integer=" + n;
    }
    return "other";
}
```

The two branches have their own pattern variables: `text` of type `String`, and `n` of type `Integer`. Redundant casts and null checks are eliminated in both branches.

**Watch out when refactoring:** if the legacy code has complex conditions, an `else if` branch might only be considered in certain cases. For example, `if (obj instanceof String) { ... } else if (...)` and `if (obj instanceof String && extraCondition) { ... } else if (...)` **differ** when `obj` is a `String` but `extraCondition` is false. Do not merge conditions or move `else` intuitively without verifying equivalence.

## 8. Type Patterns Do Not Replace Every Kind of Type Check

When automating refactoring, you must check the **meaning of the original type check**.

### instanceof and getClass() are not always equivalent

`instanceof` accepts objects of subclasses or implementations of the corresponding interface. Conversely, `obj.getClass() == Base.class` requires the **exact runtime class** `Base`. Replacing `getClass() == Base.class` with `instanceof Base b` can change how subclasses are handled, and calling `getClass()` on `null` can also throw `NullPointerException`. If the exact runtime class is required, preserve the corresponding logic.

### Some generic types cannot be used directly with instanceof

You cannot write `input instanceof java.util.List<String> xs` because `List<String>` is a parameterized type that is not reifiable in this context. When needed, you can use `input instanceof java.util.List<?> xs` and then check elements per business requirements; do not assume all elements are `String`.

### Operators and expressions with side effects

If legacy code calls a method multiple times, such as `getValue() != null && getValue() instanceof String`, each call may yield a different result or have side effects. A safe refactor usually starts by storing the value once in a local variable:

```java
Object value = getValue(); // Assumes getValue() exists in the enclosing class.
if (value instanceof String text) {
    System.out.println(text);
}
```

The snippet above illustrates the approach and **is not a standalone Java program**, because `getValue()` is not defined. Before changing it, decide whether the number of calls to `getValue()` is an important part of the behavior; changing the call count of a method with side effects is not necessarily equivalent.

## 9. Null in a Record Component Is a Different Case (Java 21+)

When using **record patterns** from Java 21, you must distinguish null for the **outer object** from null inside a **record component**:

```java
record Box(String label) {}

Object a = null;
Object b = new Box(null);

if (a instanceof Box(var label)) {
    // Does not run: object a is null.
}
if (b instanceof Box(var label)) {
    System.out.println(label == null); // true
}
```

`Box(var label)` does not match a `null` `Box` object. However, because `var label` is an unconditional **component pattern** with inferred type `String`, it can match a component where `label == null`. After the pattern matches, `label.length()` will still throw `NullPointerException` if `label` is not checked first.

When refactoring code that uses record patterns, do not infer that "the pattern matched" means **all reference components are non-null**. This section is an extension for Java 21; the main program in section 11 only requires Java 17.

## 10. Behavior-Preserving Refactoring Workflow

Follow this sequence to minimize errors:

1. **Identify the value being type-checked.** Is it a local variable or the result of a method call that could change? If it is a call with side effects, determine the call-count requirement.
2. **Locate the null checks.** Mark checks that only guard `instanceof`/cast versus checks that have their own business-logic branch.
3. **Convert `instanceof Type` + cast to `instanceof Type variable`.** Choose a clear new name that does not conflict with existing variables in scope.
4. **Remove redundant null checks** when they carry no separate behavior. `instanceof` already returns `false` for null.
5. **Preserve business conditions.** For example, length, `isBlank()`, positive numbers, permissions, or error messages, and ensure evaluation order is preserved.
6. **Verify flow scoping.** Use the pattern variable in the matching branch, on the right-hand side of an appropriate `&&`, or after a negated guard with `return`/`throw`. With `||`, check the condition direction carefully.
7. **Test boundary inputs.** Test at least `null`, wrong-type objects, right-type empty values, and right-type valid data. Also test subclasses/generics and exceptions if relevant to the legacy code.
8. **Compile and run behavioral tests.** Compare output and exceptions before and after before removing casts or legacy logic.

## 11. Complete Java 17 Program

Save the entire code below into **`NullTypeRefactorDemo.java`**. It demonstrates both the legacy and refactored code to verify the results:

```java
public class NullTypeRefactorDemo {
    static String legacyLabel(Object input) {
        if (input != null && input instanceof String) {
            String text = (String) input;
            if (!text.isBlank()) {
                return "text=" + text.strip();
            }
        }
        return "unavailable";
    }

    static String modernLabel(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "text=" + text.strip();
        }
        return "unavailable";
    }

    static int legacyLength(Object input) {
        if (input == null || !(input instanceof String)) {
            return -1;
        }
        String text = (String) input;
        return text.length();
    }

    static int modernLength(Object input) {
        if (!(input instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    static String validate(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "invalid";
        }
        return "valid=" + text.strip();
    }

    static String distinguishNull(Object input) {
        if (input == null) {
            return "missing";
        }
        if (input instanceof String text) {
            return "string=" + text;
        }
        return "other type";
    }

    static String classify(Object input) {
        if (input instanceof String text && !text.isEmpty()) {
            return "string length=" + text.length();
        } else if (input instanceof Integer n && n > 0) {
            return "positive integer=" + n;
        }
        return "other";
    }

    public static void main(String[] args) {
        Object[] inputs = {null, "  Java  ", "   ", "ok", 42};
        for (Object input : inputs) {
            String before = legacyLabel(input);
            String after = modernLabel(input);
            System.out.println("same=" + before.equals(after) + ", " + after);
        }

        System.out.println("length(null)=" + modernLength(null));
        System.out.println("length(abc)=" + modernLength("abc"));
        System.out.println("length(42)=" + modernLength(42));
        System.out.println("legacy and modern length agree="
                + (legacyLength("abc") == modernLength("abc")));

        System.out.println("validate(blank)=" + validate("  "));
        System.out.println("validate(text)=" + validate(" ABC "));
        System.out.println("validate(null)=" + validate(null));

        System.out.println("null branch=" + distinguishNull(null));
        System.out.println("non-string branch=" + distinguishNull(42));
        System.out.println("classify(number)=" + classify(5));
        System.out.println("classify(text)=" + classify("Go"));
    }
}
```

Compile and run (JDK 17 or higher):

```bash
javac --release 17 -encoding UTF-8 NullTypeRefactorDemo.java
java NullTypeRefactorDemo
```

**Verified stdout output:**

```text
same=true, unavailable
same=true, text=Java
same=true, unavailable
same=true, text=ok
same=true, unavailable
length(null)=-1
length(abc)=3
length(42)=-1
legacy and modern length agree=true
validate(blank)=invalid
validate(text)=valid=ABC
validate(null)=invalid
null branch=missing
non-string branch=other type
classify(number)=positive integer=5
classify(text)=string length=2
```

The first five lines compare `legacyLabel` and `modernLabel` on `null`, a string with leading/trailing whitespace, a blank string, a short string, and another type. All print `same=true`. The rest confirms that the negated guard, the `||` expression, and the separate `null` branch work properly. Checking the output on these samples is a useful verification step; in a real project, you should still run the test suite against your system's business scenarios.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong or risky | How to fix |
| --- | --- | --- |
| Keeping `obj != null` before `obj instanceof String s` with no separate behavior | Redundant check, makes condition harder to read | Use `obj instanceof String s` |
| Keeping `(String) obj` cast in a branch that already has `String s` | Repeats check/cast, misses the benefit of the pattern | Use `s` directly |
| Removing an `if (obj == null)` branch that has a distinct result | Changes `null` behavior, error, or message | Keep the `null` branch before the type pattern |
| Using `s` on the right-hand side of `obj instanceof String s || ...` | The right-hand side can run when the pattern has not matched | Use `&&` or appropriate negation with `||` |
| Using `s` outside `if` without an early-exit guard | Compiler cannot guarantee definite matching | Keep logic in the true branch or use early return |
| Assuming `obj instanceof String s` also rejects empty strings | `instanceof` only checks type, not content | Add `!s.isBlank()` or the appropriate data rule |
| Changing `getClass() == T.class` to `instanceof T t` | The two checks can differ for subclasses | Keep exact class check if that is the contract |
| Accessing a nullable component after a record pattern | A bound component variable can still hold null | Check the variable before calling methods |
| Refactoring repeated method calls with side effects | May change execution order or call count | Analyze behavior, consider snapshotting the value |
| Naming a pattern variable the same as a variable in a conflicting scope | Compiler may report a duplicate declaration | Rename the pattern variable clearly |

## 13. Practice Exercises

**Exercise 1.** Refactor the following snippet while keeping the `false` result for `null`:

```java
boolean isPositive(Object value) {
    if (value != null && value instanceof Integer) {
        Integer n = (Integer) value;
        return n > 0;
    }
    return false;
}
```

*Suggested answer:*

```java
boolean isPositive(Object value) {
    return value instanceof Integer n && n > 0;
}
```

`null` does not match `Integer n`, so the entire expression still returns `false`.

**Exercise 2.** You need to return `"missing"` if `value == null`, `"ok"` if it is a `String`, and `"bad type"` otherwise. Can you remove the null check just because `instanceof` returns false on its own?

*Answer:* No. Removing the null check would cause `null` to fall into `"bad type"`, changing the business requirement. Keep three separate branches.

**Exercise 3.** Can `if (value instanceof String s && !s.isBlank())` cause a `NullPointerException` at `s.isBlank()` when `value == null`?

*Answer:* No. When `value == null`, `instanceof` is `false`, and the right-hand side of `&&` is not evaluated.

**Exercise 4.** Why does `if (!(value instanceof String s)) return;` allow using `s` immediately after this statement (if placed in a `void` method)?

*Answer:* The non-matching path ends with `return`. Every path that can continue is guaranteed to have matched `String s`.

**Exercise 5.** Why shouldn't you automatically change `value.getClass() == Base.class` to `value instanceof Base b`?

*Answer:* `getClass() == Base.class` checks for the exact runtime class, whereas `instanceof Base` also accepts subclasses; `null` handling also differs if there was no prior null guard.

**Official references:** [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Oracle Java – Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html), [JLS 17 – `15.20.2 Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2), [JLS 17 – `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440).
