# Distinguishing Constant String Concatenation from Runtime Value Concatenation in Java

The `+` operator can concatenate `String` values into a new string, but **not every string concatenation expression is evaluated at the same time**. Java distinguishes:

- **Compile-time constant expression string concatenation**: the compiler can compute the entire result ahead of time. `"Java" + "Core"` is treated like the string literal `"JavaCore"` and the constant result is **interned**.
- **Runtime concatenation**: at least one operand does not form a constant expression under the language rules. The string value is assembled at execution time, even if at that moment it has the same content as an existing literal.

This distinction matters when learning **the String Pool, `intern()`, `final` semantics, `==` and `equals()` comparisons**, as well as when reading bytecode and evaluating concatenation cost.

## 1. The Boundary Between Constant and Runtime Concatenation

**Constant concatenation** occurs only when the entire expression satisfies Java's definition of a *constant expression*: the compiler determines the value before the program runs. **Runtime concatenation** needs to read non-constant-expression values during execution; the result may have the same content as a literal, yet it is not automatically interned.

~~~java
String literal = "Java";
String folded = "Ja" + "va";       // Compile-time constant
final String constant = "Ja";
String foldedFinal = constant + "va";
String variable = "Ja";
String runtime = variable + "va";   // Runtime concatenation
~~~

`folded == literal` and `foldedFinal == literal` are `true`, whereas `runtime == literal` is `false`; `runtime.equals(literal)` is still `true`. A `final String` becomes a **constant variable** only when declared with an initializer that is a constant expression; `final String s = new String("Ja")` does not qualify. The lesson on constant expressions already covered the exceptions, how the compiler inlines constants, and the impact on APIs.

The focus next is concatenation **at runtime**, the evaluation order of `+`, bytecode, and techniques for joining multiple parts.

## 2. Relationship to the String Pool and Comparisons

The **String Pool** is the mechanism Java uses to maintain a *canonical representation* for interned strings. String literals and strings resulting from constant expressions of type `String` are interned according to language semantics. Two constant expressions with the same content can therefore reference the same `String` object.

With runtime concatenation, the content can be identical to a string in the pool, but **that alone does not make the concatenation automatically use the pooled reference**.

Let's compile the following full class with Java 17+.

Save the file `ConcatIdentityDemo.java`:

```java
public class ConcatIdentityDemo {
    public static void main(String[] args) {
        String pooled = "JavaCore";

        // Two ways to write constant expressions
        String folded = "Java" + "Core";
        final String constantPrefix = "Java";
        final String constantSuffix = "Core";
        String foldedFinals = constantPrefix + constantSuffix;

        // Two ways to perform runtime concatenation
        String variablePrefix = "Java";
        String runtime = variablePrefix + "Core";

        final String notConstantPrefix = new String("Java");
        String runtimeFinal = notConstantPrefix + "Core";

        System.out.println(folded == pooled);
        System.out.println(foldedFinals == pooled);
        System.out.println(runtime == pooled);
        System.out.println(runtime.equals(pooled));
        System.out.println(runtimeFinal == pooled);
        System.out.println(runtimeFinal.intern() == pooled);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConcatIdentityDemo.java
java ConcatIdentityDemo
```

Output:

```text
true
true
false
true
false
true
```

Line-by-line explanation:

1. `folded == pooled` is `true` because `"Java" + "Core"` is folded into the constant string `"JavaCore"` and uses the interned reference.
2. `foldedFinals == pooled` is `true` because both `final` variables receive literal initializers, making them constant variables; `constantPrefix + constantSuffix` is also a constant expression.
3. `runtime == pooled` is `false`: `variablePrefix` is not a constant variable, concatenation occurs at runtime, and the result is not automatically the interned `"JavaCore"` object.
4. `runtime.equals(pooled)` is `true`: the two strings contain **the same content**.
5. `runtimeFinal == pooled` is `false`: `new String("Java")` is evaluated at runtime; having `final` does not make the concatenation expression a compile-time constant.
6. `runtimeFinal.intern() == pooled` is `true`: `intern()` returns the canonical reference in the pool corresponding to the content `"JavaCore"`.

**Do not use `==` to compare string content.** `==` compares object references, so two `String` objects with identical text can give different results depending on how they were created. `equals()` compares content; for two values that may be `null`, use `Objects.equals(a, b)` when you want a safe boolean result.

## 3. Numeric Addition and Evaluation Order in String Concatenation

`+` can be **arithmetic addition** or **string concatenation** depending on operand types. Java evaluates expressions in order, and parentheses can change the outcome.

Standalone example in `ConcatOrderDemo.java`:

```java
public class ConcatOrderDemo {
    public static void main(String[] args) {
        System.out.println("A" + 1 + 2);
        System.out.println(1 + 2 + "A");
        System.out.println("A" + (1 + 2));

        final int constantNumber = 2;
        int variableNumber = 2;

        System.out.println(("v" + constantNumber) == "v2");
        System.out.println(("v" + variableNumber) == "v2");
        System.out.println(("v" + variableNumber).equals("v2"));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 ConcatOrderDemo.java
java ConcatOrderDemo
```

Output:

```text
A12
3A
A3
true
false
true
```

- `"A" + 1 + 2` concatenates from left to right, becoming `"A1"` and then `"A12"`.
- `1 + 2 + "A"` adds the two numbers to get `3` first, then concatenates `"A"`, yielding `"3A"`.
- `"A" + (1 + 2)` forces addition inside parentheses, yielding `"A3"`.
- `constantNumber` is a constant variable (type `int`, `final`, initialized with a literal), so `"v" + constantNumber` is a constant expression and is already interned.
- `variableNumber` is not a constant variable, so `"v" + variableNumber` is performed at runtime; content comparison with `equals()` still yields `true`.

An expression can produce the exact same content yet execute at runtime. **"The expression produces a fixed string during this run"** does not mean **"a constant expression under the JLS."**

## 4. Looking at Compilation and Bytecode

At the Java language level, the key distinction is **when the result is a constant expression**; how the compiler and JVM execute runtime concatenation is an implementation detail.

With modern `javac` on Java 17+, the command:

```bash
javap -c -p ConcatIdentityDemo
```

lets you inspect the bytecode of the compiled class. Common signs:

- For `"Java" + "Core"`, you can see code loading the already-folded literal `"JavaCore"`, such as an `ldc` instruction; no runtime concatenation is needed to form this result.
- For `variablePrefix + "Core"`, modern `javac` typically emits `invokedynamic`, bootstrapped via `java.lang.invoke.StringConcatFactory`. The concatenation recipe and arguments are used when the program runs.
- Older compilers or Java versions may emit `StringBuilder.append(...)` for runtime concatenation. Java 9+ introduced the `invokedynamic`-based strategy via JEP 280; therefore **you should not claim that every runtime concatenation compiles to `new StringBuilder()` in bytecode**.
- The JIT/JVM can optimize allocations and string assembly at runtime without changing program semantics. Do not infer the actual number of allocations solely from a source snippet or a `==` check.

Mental model:

```text
"Java" + "Core"
    -> entirely a constant expression
    -> compiler computes "JavaCore"
    -> reference points to the interned constant result

variablePrefix + "Core"
    -> has an operand that is not a compile-time constant
    -> runtime concatenation
    -> creates new content from the current value
    -> does NOT automatically receive a String Pool reference
```

The two paths can yield **the same character sequence**, but how the concatenation time is determined and how the reference relates to the pool differ.

## 5. Interaction with `+=`, Loops, and StringBuilder

On `String`, `+=` is equivalent in concatenation semantics to taking the current value, appending the new part, and reassigning the variable.

```java
String value = "a";
value += "b"; // current value + "b", evaluated at runtime
```

`value` is an ordinary variable, not a constant variable. Even though after the statement `value` has the content `"ab"`, **you must not rely on its reference** when comparing against the literal `"ab"`.

For fixed, short concatenations, the `+` operator is easy to read and `javac`/the JVM optimize it. However, when repeatedly concatenating many parts into an accumulator variable, consider `StringBuilder` to avoid repeatedly creating intermediate strings:

```java
import java.util.List;

public class JoinPartsDemo {
    public static void main(String[] args) {
        List<String> parts = List.of("Java", " ", "Core");

        StringBuilder builder = new StringBuilder();
        for (String part : parts) {
            builder.append(part);
        }

        String result = builder.toString();
        System.out.println(result);
        System.out.println(result.equals("Java Core"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 JoinPartsDemo.java
java JoinPartsDemo
```

Output:

```text
Java Core
true
```

`StringBuilder` collects mutable parts in a buffer, making it well suited for multi-iteration loops; `toString()` returns the resulting `String`. When combining strings with a delimiter, `String.join(...)` or `Collectors.joining(...)` can express intent more clearly. Do not use isolated microbenchmarks or guesses about `+` to draw definitive performance conclusions; measure under realistic workloads when optimization is required.

## 6. Checklist for Exercises and Practice

When you encounter a string concatenation, ask yourself in order:

1. **Do all operands participate in a constant expression?** Distinguish literals, allowed constant operations, and constant variables from data coming from non-constant variables or methods.
2. **Is the result computed at compile time or must it wait until runtime?** If the whole expression is a constant expression of type `String`, it is folded and interned according to Java rules; otherwise, it is runtime concatenation.
3. **Are you checking content or reference?** Use `equals()` for content; use `==` only if the goal is genuinely object identity or studying interning.
4. **Are you joining a short expression or a long loop?** Write `+` for simple code, and `StringBuilder`/joining utilities when there are many parts or continuous accumulation.
5. **Do you need to verify the compiler/JVM strategy?** Inspect bytecode with `javap` and test on the target JDK; do not turn an observation from one version into a universal rule for all Java releases.

### Self-check

| Expression | Constant expression? | Reason |
| --- | --- | --- |
| `"a" + "b"` | Yes | Consists solely of literals |
| `"n=" + (2 * 3)` | Yes | Arithmetic operation is constant |
| `final String a = "a"; a + "b"` | Yes | `a` is a constant variable |
| `String a = "a"; a + "b"` | No | `a` is not `final` |
| `final String a = new String("a"); a + "b"` | No | Initializer of `a` is evaluated at runtime |
| `"a" + args.length` | No | `args.length` is only known at runtime |
| `String.valueOf(1) + "a"` | No | Contains a method call |
| `"v" + 1` | Yes | `String` literal + primitive literal |

The rows containing variable declarations in the table are **illustrative snippets placed within the same scope**; they are not standalone Java expressions that you can copy verbatim from the table into a `.java` file.

**Remember:** Constant concatenation occurs when the compiler determines the entire content from a *constant expression* and the result is interned. Runtime concatenation uses actual execution-time values and does not automatically share an object in the String Pool. Comparing two `String` values should rely on **`equals()`**, not on the coincidence of `==`.