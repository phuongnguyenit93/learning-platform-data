# Compile-Time String Constant Expressions in Java

## 1. The Phenomenon to Understand

The following two ways of writing create **the same string value** `"Java"`:

```java
String a = "Java";
String b = "Ja" + "va";
```

The interesting point: the expression `"Ja" + "va"` **does not need to join two strings while the program is running**. Because both operands are constants, the Java compiler can—and by language semantics does—treat them as a **constant string expression**, having the value `"Java"` already at compile time.

```java
System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

In this example, `a == b` is `true` because strings that are the values of constant expressions are **interned**: strings with the same content share a canonicalized reference in the *string pool*. However, in real-world applications, when you want to check **text content**, always prefer `.equals(...)` instead of relying on `==`.

This lesson explains the conditions for string concatenation to be evaluated at compile time, its relationship to the pool and `intern()`, how to distinguish it from runtime concatenation, and common misconceptions when reading or optimizing Java code.

## 2. What Is a Constant Expression?

A **constant expression** is an expression whose value is determined from components and operations permitted by Java at compile time. The language rules are described in the *Java Language Specification*, section **15.29 – Constant Expressions**.

For strings, simple examples are:

```java
String first = "Java";                   // String literal
String second = "Ja" + "va";             // Concatenating two literals
String version = "Java " + 17;           // String plus integer constant
String calculated = "Result: " + (1 + 2); // Arithmetic constant + string
```

The corresponding values are `"Java"`, `"Java"`, `"Java 17"`, and `"Result: 3"`.

The `+` operator has two related meanings here:

- If both operands are numbers, `+` can be arithmetic addition.
- If one operand is `String`, `+` performs **string concatenation**, converting the other operand to its textual representation according to Java's rules.

When the components of a concatenation satisfy the conditions of a *constant expression*, the resulting content is computed ahead of time, without needing to perform a dynamic concatenation at runtime.

**Distinguishing two points in time:** *Computing string content at compile time* does not mean the compiler has already created a Java `String` object sitting in the heap of a future process. The compiler represents the constant in the class file's data; when the class is used, the JVM resolves string literals/constants according to runtime and pool mechanisms.

## 3. When Is a Variable Considered a Compile-Time Constant?

Putting the `final` keyword on a variable is **not enough** for every use of that variable to become a constant expression.

Java uses the term **constant variable** for a variable that:

1. Has a *primitive* type or `String`.
2. Is declared `final`.
3. Is initialized **with a constant expression** directly in its declaration.

Examples of valid constant variables (placed inside a method):

```java
final String PREFIX = "Ja";
final String WORD = PREFIX + "va";
final int MAJOR = 17;

String a = WORD;              // "Java"
String b = "Java " + MAJOR;    // "Java 17"
```

Because `PREFIX`, `WORD`, and `MAJOR` satisfy all three conditions, the compiler can substitute their constant values when evaluating expressions.

`static final` fields can also be constant variables:

```java
class Constants {
    static final String PREFIX = "Ja";
    static final String WORD = PREFIX + "va";
}
```

Now look at examples that are **not** constant variables:

```java
String prefix = "Ja";                  // Not final
final String fromMethod = getPrefix(); // Runtime method call
final String boxed = new String("Ja"); // Initialized with new
```

Here `getPrefix()` is assumed to be a method defined elsewhere returning `String`; these three lines only illustrate syntax in a context where an appropriate method is declared.

Even if `getPrefix()` always returns `"Ja"`, or `new String("Ja")` always contains the same characters, those expressions still do **not** become constant expressions merely because we can predict the result.

A `final` variable that is **assigned in an initializer block** instead of having an initializer directly in its declaration also does not satisfy the definition of a constant variable:

```java
class Config {
    static final String PREFIX;
    static {
        PREFIX = "Ja";
    }
}
```

Subsequently, `Config.PREFIX + "va"` is a concatenation depending on the variable's value at runtime, not a constant expression under the stated rules.

### Quick comparison

| Expression | Compile-time constant? | Explanation |
|---|---|---|
| `"Ja" + "va"` | Yes | Both operands are literals |
| `"Java " + 17` | Yes | String literal and integer constant |
| `final String x = "Ja";` then `x + "va"` | Yes | `x` is a constant variable |
| `String x = "Ja";` then `x + "va"` | No | `x` is not `final` |
| `final String x = method();` then `x + "va"` | No | Initializer is a method call |
| `final String x = new String("Ja");` then `x + "va"` | No | Initializer is not a constant expression |
| `String.valueOf(17) + "!"` | No | Contains a method call |

In this table, rows containing a variable declaration and a concatenation expression describe separate code snippets, not a single complete program. Do not equate "always evaluates to the same value at runtime" with "recognized by the JLS as a constant expression."

## 4. Relationship Between Constant Expressions, the String Pool, and `intern()`

### How does the String pool work?

The *String pool* is the JVM mechanism that maintains a canonicalized reference for strings with the same content. String literals and `String` values that are **values of constant expressions** are interned so that equivalent constant values reference the same canonicalized string object.

Therefore:

```java
String literal = "Java";
String folded = "Ja" + "va";

System.out.println(literal == folded); // true
```

The content `"Ja" + "va"` is treated as the constant `"Java"`, and two constant expressions with equivalent content share the canonicalized reference.

### Runtime concatenation is a different situation

```java
String prefix = "Ja";
String joined = prefix + "va";

System.out.println("Java".equals(joined)); // true
System.out.println("Java" == joined);       // false
```

`prefix` is not a constant variable. The expression `prefix + "va"` must read the variable's value at runtime; it is a dynamic concatenation, producing a result object distinct from the interned object referenced by the literal `"Java"`. Equal content still does not mean equal reference.

### What role does `intern()` play?

`String.intern()` returns the canonicalized reference in the pool for a string with the same content. If no corresponding string exists in the pool yet, the interning mechanism establishes that canonicalized reference according to the API contract.

```java
String prefix = "Ja";
String joined = prefix + "va";

System.out.println(joined == "Java");          // false
System.out.println(joined.intern() == "Java"); // true
```

Calling `intern()` **does not turn runtime concatenation into compile-time concatenation**. It is a runtime action to obtain the canonicalized reference. Nor does it alter the content of `joined`: `String` is immutable.

A note on terminology: the **constant pool in a class file** is a data structure storing many kinds of constants and symbolic references for compiled code; the **string pool** is the runtime mechanism for sharing `String` objects. The two concepts are related, but they are not a single storage location and should not be treated as synonymous.

## 5. Complete Java 17+ Example and Verification Output

Create the file **`StringConstantExpressionDemo.java`**:

```java
public class StringConstantExpressionDemo {
    private static final String STATIC_PREFIX = "Ja";

    private static final String LATE_PREFIX;
    static {
        LATE_PREFIX = "Ja";
    }

    private static String getPrefix() {
        return "Ja";
    }

    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";

        final String localPrefix = "Ja";
        String fromLocalConstant = localPrefix + "va";
        String fromStaticConstant = STATIC_PREFIX + "va";

        String mutablePrefix = "Ja";
        String runtimeConcat = mutablePrefix + "va";

        final String methodPrefix = getPrefix();
        String fromMethod = methodPrefix + "va";
        String fromLateFinal = LATE_PREFIX + "va";

        String explicitNew = new String("Java");

        System.out.println("literal == folded: "
                + (literal == folded));
        System.out.println("literal == local constant: "
                + (literal == fromLocalConstant));
        System.out.println("literal == static constant: "
                + (literal == fromStaticConstant));
        System.out.println("literal == runtime concat: "
                + (literal == runtimeConcat));
        System.out.println("literal == method result: "
                + (literal == fromMethod));
        System.out.println("literal == late final: "
                + (literal == fromLateFinal));
        System.out.println("literal == new String: "
                + (literal == explicitNew));
        System.out.println("literal == interned runtime: "
                + (literal == runtimeConcat.intern()));
        System.out.println("literal.equals(runtime): "
                + literal.equals(runtimeConcat));
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac -encoding UTF-8 StringConstantExpressionDemo.java
java StringConstantExpressionDemo
```

**Stdout:**

```text
literal == folded: true
literal == local constant: true
literal == static constant: true
literal == runtime concat: false
literal == method result: false
literal == late final: false
literal == new String: false
literal == interned runtime: true
literal.equals(runtime): true
```

**Reading the output:**

1. `folded`, `fromLocalConstant`, and `fromStaticConstant` have content determined by constant expressions. They point to the same interned `"Java"` value as the literal.
2. `runtimeConcat`, `fromMethod`, and `fromLateFinal` involve runtime concatenation, so their content is still `"Java"`, but the resulting object is not the object referenced by the literal `"Java"`.
3. `new String("Java")` requests creating a distinct `String` object; therefore its reference differs from the literal even though the content is the same.
4. `runtimeConcat.intern()` obtains the canonicalized reference for `"Java"`, and comparing it with `==` against the literal evaluates to `true`.
5. `literal.equals(runtimeConcat)` is `true`, confirming that content comparison does not depend on whether two variables point to the same object.

The example carefully controls the origin of each string to illustrate the rules. In ordinary programs, **do not use `==` between `String` values to infer when data was computed**; if the goal is text comparison, use `equals`.

## 6. Recognizing Constant Folding via Bytecode

For the source snippet:

```java
String result = "Ja" + "va";
```

The compiler can place the content `"Java"` directly into the class file instead of code that concatenates two separate operands. This is *constant folding*: reducing constant expressions before the program executes.

You can inspect the class file generated in section 5 using:

```bash
javap -c -p StringConstantExpressionDemo
```

The `javap` output depends on the compiler and JDK version, but you can look for instructions loading string constants such as `ldc ... // String Java` where constant expressions are used. For runtime concatenation, `javac` bytecode on modern JDKs typically uses `invokedynamic` and the JVM's string concatenation mechanism; bytecode generation details may vary across JDK releases.

**You do not need to rely on a specific opcode to understand the rule.** The core point is: concatenating constant expressions produces a value determined beforehand under the JLS; concatenation depending on a non-constant variable must use runtime data.

You should also avoid the misconception that an expression optimized by the JIT at runtime automatically becomes a **constant expression of the Java language**. These are two different layers: constantness under the JLS is determined from source code/compilation, whereas the JIT is an execution-time optimization.

## 7. Common Misconceptions

### Mistake 1: "If it has `final`, the compiler computes everything"

Incorrect. Compare:

```java
final String a = "Ja";             // Constant variable
final String b = "J".concat("a");  // Not a constant variable
```

`b` is `final`, but calling `concat(...)` is not a constant expression as defined by the JLS. `b + "va"` is still not a compile-time constant concatenation.

### Mistake 2: "Using `==` to compare two strings is faster and therefore safe"

`==` compares **object identity**. Interned constant strings can coincidentally make `==` appear to work like content comparison, but strings from user input, file reading, APIs, or dynamic concatenation generally have no such guarantee.

Use:

```java
"Java".equals(candidate)
```

When `candidate` might be `null`, this style avoids a `NullPointerException` on the receiver. Or use `java.util.Objects.equals(a, b)` when both variables can be `null`.

### Mistake 3: "Concatenating two values that are always the same must be constant concatenation"

For example, `getPrefix() + "va"` is still runtime concatenation, even if `getPrefix()` always returns `"Ja"`. The rule examines **expression structure** and the components allowed by the JLS, not whether a human knows the result in advance.

### Mistake 4: "Once the compiler computes the string, the program uses no memory at all for `String`"

False. The compiler determines the **constant content**, while the JVM still has `String` objects used at runtime. Interning helps reuse references for constants with the same content; it does not eliminate the concept of string objects.

### Mistake 5: "Calling `intern()` makes all string processing faster"

There is no such universal rule. `intern()` adds the work of managing canonicalized references; it should only be used when you genuinely understand the reference sharing/canonicalization requirement and data characteristics. Normal content comparison remains `.equals(...)`; you do not need to intern every string in order to compare it.

## 8. When Is This Knowledge Useful?

- **Interpreting unexpected `==` results:** explaining why `"a" + "b" == "ab"` can be true in constant expressions, whereas concatenating with a variable that yields the same content behaves differently.
- **Understanding the compiler:** recognizing the boundary between compile-time constantness and runtime concatenation.
- **Reading bytecode:** understanding why source code uses the `+` operator while the class file only needs to load a single string constant.
- **Designing shared constants:** a `static final String` initialized by a constant expression can have its value inlined into consuming classes at compile time. Therefore, if you change a public constant's value in a library, previously compiled classes may retain the old value until recompiled. Do not rely on compile-time constant fields to supply configuration that needs to change without recompiling clients.
- **Avoiding misguided optimizations:** choosing among `==`, `.equals(...)`, and `intern()` based on the **semantics** required, not merely because two strings appear to have the same content.

## 9. Self-Check

**Question 1.** What does the following snippet print?

```java
String x = "ab";
String y = "a" + "b";
System.out.println(x == y);
```

**Answer:** `true`, because `"a" + "b"` is a constant expression with the interned value `"ab"`.

**Question 2.** Does adding `final` to the variable change the result?

```java
String a = "a";
String x = a + "b";
System.out.println(x == "ab");
```

**Answer:** The code as written prints `false`. If you change the declaration to `final String a = "a";`, `a` becomes a constant variable; the concatenation `a + "b"` is a constant expression, and the comparison prints `true`.

**Question 3.** Why does this example still concatenate at runtime?

```java
final String a = new String("a");
String x = a + "b";
```

**Answer:** `a` is not a constant variable because its initializer uses `new`, which is not a constant expression.

**Question 4.** For `String t = dynamic + "ab";`, should you use `t.intern() == "someValue"` to check content?

**Answer:** No need. When you want to check text, use `"someValue".equals(t)`. `intern()` serves reference canonicalization, not routine content comparison.

**Question 5.** Do "computed at compile time" and "interned at runtime" contradict each other?

**Answer:** No. The compiler determines the **constant value of the expression**, while the JVM uses its **runtime canonical string mechanism** to represent and share the corresponding `String` object.

## 10. Key Takeaways

A string concatenation expression is considered a **constant expression** only when its components strictly follow the rules of the Java language; literals and **constant variables** are the common cases. The `String` value of a constant expression is interned, so constant strings with the same content share a canonicalized reference. Concatenation using non-constant variables or method calls is runtime concatenation, even if the final content looks identical. Use knowledge of the string pool to understand Java, and use `.equals(...)` when you need to check text content.