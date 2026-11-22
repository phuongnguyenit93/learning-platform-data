# Differences Between Pattern Matching and Manual Casting in Java

## 1. Same Need, Two Ways to Write It

When a variable has a broad declared type such as `Object`, a program sometimes needs to check what type the actual object belongs to and then use members specific to that type. In Java, two common approaches are:

- **Type check followed by manual cast:** use `instanceof` to check, then write the cast `(Type) value` and assign the result to a variable with a specific type.
- **Pattern matching for `instanceof`:** use `value instanceof Type name` to check the type and declare a variable with the specific type right in the same expression.

For example, with `Object value` which may hold a `String`:

```java
// Old way: checking and casting are two separate operations.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}

// Pattern matching: check and bind the text variable at the same time.
if (value instanceof String text) {
    System.out.println(text.length());
}
```

These are two **illustrative code snippets placed inside a method that has a `value` variable**. When the condition is true, both use the same `String` object; pattern matching does not copy or convert the string content. The main differences lie in the syntax, the relationship between the type check and the variable used, and how the compiler manages variable scope.

## 2. Complete Java 17 Example: Equivalent Results

Save the following program in the file `PatternVsManualCast.java`:

```java
public class PatternVsManualCast {
    static String manual(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "String: " + text.toUpperCase();
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "Integer: " + (number + 1);
        }
        return "Other";
    }

    static String pattern(Object value) {
        if (value instanceof String text) {
            return "String: " + text.toUpperCase();
        }
        if (value instanceof Integer number) {
            return "Integer: " + (number + 1);
        }
        return "Other";
    }

    public static void main(String[] args) {
        Object[] inputs = {"java", 41, null, 3.5};
        for (Object input : inputs) {
            System.out.println(manual(input) + " | " + pattern(input));
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac PatternVsManualCast.java
java PatternVsManualCast
```

Standard output (stdout):

```text
String: JAVA | String: JAVA
Integer: 42 | Integer: 42
Other | Other
Other | Other
```

Explanation of each case:

- `"java"` is a `String`: both branches call `toUpperCase()` and get `"JAVA"`.
- `41` is autoboxed to `Integer` when placed into the `Object[]` array: both approaches add 1 and produce `42`.
- `null`: all `instanceof` checks above evaluate to `false`, so `"Other"` is returned; pattern matching does not automatically handle `null` as a `String`.
- `3.5` is a `Double`: it does not match `String` or `Integer`, so `"Other"` is returned.

The takeaway here is that **pattern matching simplifies type-checking code**, rather than automatically changing branching rules or business results.

## 3. Aspect-by-Aspect Comparison

| Aspect | `instanceof` + manual cast | Pattern matching for `instanceof` |
| --- | --- | --- |
| Syntax | `if (x instanceof T) { T t = (T) x; ... }` | `if (x instanceof T t) { ... }` |
| Runtime type check | `instanceof` checks first; the explicit cast appears separately | `instanceof T t` checks and binds `t` only when it matches |
| Cast-related errors | Possible to mistype the type/variable in the cast or omit the check | No need to rewrite the cast after the pattern has matched |
| Static type of the variable used | Variable `t` receives type `T` from the declaration and cast | Pattern variable `t` has type `T` immediately upon matching |
| Variable scope | Local variable follows normal block scoping | Pattern variable has **flow-dependent scope** (flow scoping) |
| `null` | `null instanceof T` is `false` | `null instanceof T t` is also `false` |
| Main purpose | Useful in legacy code or places where an explicit cast is truly needed | Reduces repetition and expresses type-checking intent more clearly |
| Performance | Depends on the code and JVM | No guarantee of always being faster; should not be chosen solely expecting a speedup |

**Note on safety:** an explicit cast *after an `instanceof` check of the right type* is still safe in the corresponding branch. It should not be said that all manual casting is wrong, or that pattern matching prevents every `ClassCastException` in a program. Pattern matching eliminates an error-prone spot right at this check-and-use site.

## 4. Flow Scoping: A Difference More Important Than Brevity

In `if (value instanceof String text)`, `text` can only be used on paths where the compiler proves the pattern has matched.

### Using with `&&`

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.length());
}
```

This snippet is valid inside a method with `Object value`. The `&&` operator evaluates from left to right and short-circuits when the left-hand side is false. Therefore, if the JVM needs to evaluate `!text.isBlank()`, `value` has definitely matched `String text`.

Conversely, the following snippet **does not compile**:

```java
if (value instanceof String text || text.isBlank()) {
    System.out.println("invalid");
}
```

When the left-hand side of `||` is false, the right-hand side still has to run, but at that point `text` has not been assigned a value. The compiler does not allow using the pattern variable in this position.

### Using the variable after a negated check if the non-matching branch completes

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

The method above is valid in Java 17: after the `if`, the only remaining path is the one where `value` has matched `String`. By contrast, with `if (value instanceof String text) { ... } else { ... }`, `text` cannot be used in the `else` branch of the positive check.

**The original declared type does not change automatically:** if `value` is declared as `Object`, it still has the static type `Object`; the `text` variable is the reference with type `String` used to directly call methods such as `length()` or `isBlank()`.

## 5. Common Mistakes and Misconceptions

### Casting directly without an appropriate check

```java
Object value = Integer.valueOf(7);
String text = (String) value; // ClassCastException at runtime
```

This code compiles because `value` has the static type `Object`, but the actual object is an `Integer`, so casting to `String` fails. Using `if (value instanceof String text)` to execute logic only when the type matches avoids this error in that branch.

### Confusing pattern matching with value conversion

`instanceof Integer number` does not convert the string `"42"` into the number `42`. If you need to convert data, that is a different task—for example, `Integer.parseInt("42")`. Pattern matching checks the runtime type of a reference; it does not parse or convert data.

### Using generic types that cannot be fully checked at runtime

Because of **type erasure**, you cannot use `instanceof java.util.List<String> list` to verify the `String` type argument at runtime. When you need to recognize a list, you can write:

```java
if (value instanceof java.util.List<?> items) {
    System.out.println("Size: " + items.size());
}
```

This syntax confirms that `value` is a `List`, but it **does not** guarantee that every element is a `String`. If you want to check the elements, you must check them individually or design an API with strict types from the start.

### Overusing `instanceof` for every problem

If the API already provides the right static type, there is no need to re-check the type or cast. If you need different behavior per class in an object-oriented system, consider polymorphism (method overriding) or generics before building long `if/else if instanceof` chains. Pattern matching makes type-checking branches easier to read, but it does not replace proper data type design.

### Confusing Java versions

**Pattern matching for `instanceof` was finalized in Java 16**, so the examples in this article work directly on Java 17 without needing `--enable-preview`. Pattern matching for `switch` is a separate feature, finalized in Java 21; do not copy new `switch` pattern syntax into a Java 17 project and expect it to work like the `instanceof` syntax in this article.

## 6. Which Approach to Choose in Practice?

Prefer `if (x instanceof Type name)` when you need to check a runtime type and immediately use the object as that specific type: the expression is concise, avoids repeating casts, and the compiler manages the variable along the matched path.

You may still encounter explicit casts in legacy code, when interacting with APIs that return `Object`, or at call sites where the program contract already guarantees the type and the author intentionally uses a cast. In those cases, you must understand that a wrong cast will throw `ClassCastException`; if the type is not yet certain, checking beforehand or redesigning the data types is usually more maintainable.

**Self-check:** with `Object x = "abc";`, the expression `x instanceof String s && s.length() == 3` evaluates to `true` and `s` can be used on the right-hand side; with `Object x = null;`, the condition evaluates to `false` and the right-hand side is not evaluated. This simultaneously illustrates type checking, variable binding, and short-circuit evaluation.

**Conclusion:** manual casting forces you to connect the check and the cast yourself; pattern matching combines them in a single expression and adds flow scoping. When checking and handling the same types properly, both approaches can produce the exact same result.
