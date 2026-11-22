# Type Patterns and Declared Variables

## 1. What is a type pattern?

In Java, a **type pattern** checks whether a value belongs to a specific reference type; if it matches, it **declares and initializes a variable** of the tested type. That variable is called a *pattern variable*. As a result, we can directly call methods of the matched type without manual casting.

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

The construct `value instanceof String text` has three parts: `value` is the expression to test; `instanceof` performs the runtime type test; `String text` is a **type pattern** consisting of the type `String` and the variable name `text`. If `value` holds a `String` object, the expression evaluates to `true` and `text` references **that exact object**, without creating a copy. If it does not match, the variable `text` is not available in the failure branch.

The static type of `text` is `String`; the compiler allows calling `text.length()`, `text.isEmpty()`, or `text.toUpperCase()` just like any `String` variable. Pattern matching for `instanceof` has been a standard feature since **Java 16** and works normally in **Java 17+**.

## 2. Pattern variable declaration vs. the old approach

Before type patterns, you typically had to test and then explicitly cast:

```java
Object value = "  hello  ";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.trim());
}
```

Using a type pattern:

```java
Object value = "  hello  ";
if (value instanceof String text) {
    System.out.println(text.trim());
}
```

Both snippets print `hello`. The new approach reduces type name repetition and eliminates the cast statement where the wrong variable could accidentally be written. `String text` in `instanceof` acts as both a type test and a variable declaration initialized when the test succeeds. It is not an unconditionally executed local declaration.

**Matching condition:** the value must be non-`null` and the object must be compatible with the `String` type. `null instanceof String text` returns `false`, so there is no value to assign to `text` in the true branch.

## 3. Flow-sensitive variable scoping (flow scoping)

A pattern variable does not have scope determined solely by the nearest pair of `{}` braces. Java uses the **definitely matched** rule: it only allows referencing the variable at points where every execution path reaching that point guarantees the pattern test has succeeded.

### 3.1. The true and false branches of `if`

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Valid
    } else {
        System.out.println("Không phải chuỗi");
        // text.length(); // COMPILE ERROR: text is not in scope
    }
    // text.length(); // ERROR: may not have matched after exiting if
}
```

The variable `text` is usable in the true (`then`) branch. In `else` and after a regular `if`, the program may have taken the non-matching path, so that variable cannot be used.

### 3.2. `&&` allows using the variable in the subsequent condition

```java
static boolean hasLongName(Object value) {
    return value instanceof String name && name.length() >= 5;
}
```

`&&` evaluates the right-hand side **only when the left-hand side is true**. Therefore, `name` is guaranteed to be initialized when `name.length()` runs. If `value` is `null` or of another type, the left-hand side is `false` and the method returns `false` without accessing `name`.

Conversely, this is **code that does not compile**:

```java
// Invalid: the right-hand side may be evaluated when instanceof fails.
if (value instanceof String name || name.isEmpty()) {
    System.out.println("...");
}
```

`||` only evaluates the right-hand side when the left-hand side is false; at that point `name` is not guaranteed to be initialized. To filter empty strings, write:

```java
if (value instanceof String name && name.isEmpty()) {
    System.out.println("Chuỗi rỗng");
}
```

### 3.3. Negation and early exit

A pattern variable can be used **after `if`** if the non-matching branch ends with `return` or `throw`:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length(); // Valid: reaching here means instanceof must be true
}
```

Inside the negated `if` branch, `text` is not available. However, because this branch executes `return`, every execution path reaching `return text.length()` must have passed the match result. If you remove `return` and let the failure branch fall through, `text` can no longer be safely used below.

| Location | Can `s` be used? | Reason |
| --- | --- | --- |
| Inside `if (x instanceof String s) { ... }` | Yes | Already matched |
| Inside `else` of the above test | No | The test failed |
| Right-hand side of `x instanceof String s && s.length() > 0` | Yes | `&&` only proceeds on a match |
| Right-hand side of `x instanceof String s || s.isEmpty()` | No | `||` proceeds on a non-match |
| After `if (!(x instanceof String s)) return;` | Yes | The non-matching path has terminated |

Self-check rule: **Is there any execution path reaching the use of `s` where the test has not succeeded?** If so, the compiler will not allow using that pattern variable.

## 4. Complete Java 17+ program

Save with the exact filename `TypePatternDemo.java`:

```java
public class TypePatternDemo {
    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text.toUpperCase()
                    + " (" + text.length() + ")";
        }
        if (value instanceof Integer number) {
            return "Integer doubled: " + (number * 2);
        }
        if (value == null) {
            return "null";
        }
        return "Other or blank string";
    }

    static String firstLetter(Object value) {
        if (!(value instanceof String text)) {
            return "Not a string";
        }
        if (text.isEmpty()) {
            return "Empty string";
        }
        return "First character: " + text.charAt(0);
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(21));
        System.out.println(describe(null));
        System.out.println(describe(""));
        System.out.println(firstLetter("abc"));
        System.out.println(firstLetter(42));
    }
}
```

Run with JDK 17 or later:

```bash
javac TypePatternDemo.java
java TypePatternDemo
```

Output:

```text
String: JAVA (4)
Integer doubled: 42
null
Other or blank string
First character: a
Not a string
```

Explanation:

1. `"java"` matches `String text`; `!text.isBlank()` is `true`; `toUpperCase()` returns `JAVA` and the length is 4.
2. `21` is passed as `Object` but is actually an `Integer`, so `Integer number` matches. `number * 2` uses unboxing and produces 42.
3. `null` does not match either type pattern and is handled separately.
4. `""` is a `String` but `isBlank()` is `true`, so the first branch does not return and the program uses the fallback message.
5. In `firstLetter`, the `!(value instanceof String text)` branch returns immediately if it fails; therefore `text` is usable after `if`.

This is a standalone program with `main`, requiring no external libraries. The two methods use the same pattern variable name `text` because each declaration is within its own method scope.

## 5. Type limitations to know

### Static types can make the test redundant

Java 17 rejects an `instanceof` type pattern when the expression's static type is already a subtype of the tested type, because that type test is redundant:

```java
String text = "Java";
// if (text instanceof String s) { } // COMPILE ERROR
Object value = text;
if (value instanceof String s) {      // Valid
    System.out.println(s.length());   // 4
}
```

### Reference types and generics

Type patterns `String s`, `Number n`, `CharSequence cs`, `Integer i`, and `List<?> items` work when the expression's type is appropriate. In Java 17, `int n` is not a valid type pattern in `instanceof`; for boxed integers in an `Object`, test for `Integer n`.

You cannot test for `List<String>` in `instanceof` because generic type argument information is not fully preserved at runtime (*type erasure*). Use a type that can be tested:

```java
Object value = java.util.List.of("A", "B");
if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
```

From `List<?>` you only know it is a list; **do not assume all elements are `String`**. Check each element individually if your application needs to know the specific type.

### Naming and reassignability

A pattern variable is a local variable whose scope is determined by control flow. Choose meaningful names such as `text`, `number`, `items`; do not declare a name that conflicts with an existing variable in the same scope. Since Java 16, pattern variables are **not `final` by default**, so in Java 17 they can be reassigned when variable declaration rules allow; even so, avoid changing the variable's meaning right after matching to keep the code easy to understand.

You cannot write `value instanceof var x` in Java 17: `var` cannot replace a concrete type in a type pattern. A regular local declaration `var x = ...` also does not perform a runtime type check on its own.

## 6. Type patterns in `switch` (Java 21 and later)

Java 21 officially supports pattern matching for `switch`. Each `case String s` or `case Integer n` label initializes a variable for the matching branch. The variable can also be used in a `when` guard on the same label, but it is not in scope in other `case` labels.

The following example is for **JDK 21+**; save as `SwitchPatternDemo.java`:

```java
public class SwitchPatternDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "Chuỗi trống";
            case String s -> "Chuỗi dài " + s.length();
            case Integer n -> "Số " + n;
            default -> "Loại khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(""));
        System.out.println(describe("Java"));
        System.out.println(describe(8));
        System.out.println(describe(null));
    }
}
```

Run:

```bash
javac SwitchPatternDemo.java
java SwitchPatternDemo
```

Output:

```text
Chuỗi trống
Chuỗi dài 4
Số 8
null
```

`when s.isBlank()` runs after `String s` matches; the next `case String s` branch handles the remaining strings. Both labels can declare the same name `s` thanks to separate scopes. `case null` handles `null` values explicitly. **Do not run this `switch` example as-is on Java 17 in standard compilation mode:** `switch` patterns were not yet a standard feature then.

## 7. Common mistakes

- Using `s` in `else` or after `if` when the non-matching flow can still continue → scope error.
- Writing `instanceof String s || s.isEmpty()` → invalid because `||` evaluates the right-hand side when the pattern fails; replace with `&&` or restructure the condition.
- Assuming `null instanceof String s` matches → wrong, `instanceof` returns `false`.
- Casting `(String) value` again inside a branch that already has `String s` → redundant and makes the code less clear.
- Using `List<String>` in `instanceof` → cannot check that generic type argument at runtime; consider `List<?>`.
- Confusing a pattern variable with a `var` declaration or assuming it is always in scope until the end of the block → misunderstanding the **definitely matched** rule.
- Copying Java 21 `switch` type pattern syntax into a project compiled with Java 17 → wrong version.

## 8. Practice exercises

1. Write `static int size(Object value)` that returns `cs.length()` if `value instanceof CharSequence cs`; otherwise returns `-1`. Test with `"abc"`, `new StringBuilder("xy")`, `12`, and `null`.
2. Explain every execution path of `x instanceof String s && s.length() >= 3`; why does changing `&&` to `||` make using `s` invalid?
3. Create a guard clause `if (!(obj instanceof Number n)) return;` in a `void` method, then call `n.doubleValue()` after the `if`. Explain why the variable is guaranteed to be initialized.
4. If you have JDK 21+, add a `case Long n` branch to the `switch` example and compare the scope of variable `n` between the two different `case` branches.

**Remember:** A type pattern is a **type + variable name** pair; a pattern variable can only be used where Java proves the value has matched. In `instanceof`, `&&` and early-exit branches are the two most practical ways to leverage flow scoping safely.

## References

- [Oracle Java 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
