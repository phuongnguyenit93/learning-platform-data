# String Concatenation Compilation Details May Vary Across JDKs

## 1. Core idea: the same `+` operator, potentially different implementations

In Java, the `+` operator is used for **string concatenation** when at least one operand has type `String`. For example:

```java
String name = "Lan";
int score = 9;
String message = "Name: " + name + ", score: " + score;
```

The resulting `message` is `"Name: Lan, score: 9"`. The meaning of this concatenation is defined by the **Java language**; an application must observe the correct content regardless of which internal strategy the compiler or JVM uses.

However, the source code does not dictate which class the JVM must use to assemble characters, which intermediate buffers it allocates, or which bytecode instructions it emits. Different JDKs and compilers may emit different bytecode, and the JVM may choose different execution/optimization strategies, provided Java semantics are preserved. Therefore, the claim **“`+` is always turned by the compiler into `new StringBuilder().append(...).toString()`”** does not hold across all versions.

Distinguish three layers:

1. **Java source code:** the `+` operation, expression order, and rules for converting values to text.
2. **`.class` file bytecode:** e.g., a sequence of `StringBuilder` instructions or an `invokedynamic` call.
3. **Actual execution in the JVM/JIT:** may further optimize allocations, inlining, or other techniques not directly described in bytecode.

Do not treat the bytecode emitted by one JDK as the language “definition” of the string concatenation operator.

## 2. Language rules that must remain invariant

**Fixed contract:** `+` operations at the same precedence level are left-associative; when there is a `String` operand, Java performs string conversion (including converting a `null` reference to `"null"`). The compiler and JVM must preserve evaluation order along with any observable side effects or exceptions.

For **non-constant-expression** concatenation, the result is a `String` under runtime semantics without modifying input strings; the compiler and JIT are free to optimize intermediate objects as long as behavior does not change. Example:

```java
String original = "Java";
String alias = original;
original = original + " 17";
System.out.println(alias); // Java
```

This is the foundation for comparing Java 8 bytecode with Java 9+ `invokedynamic`, without re-teaching all numeric addition/string rules.

## 3. Compile-time constant concatenation: constant folding

Before discussing Java 8 vs. Java 9+ differences, note that some concatenations **do not need runtime assembly**.

```java
String direct = "Hello World";
String folded = "Hello" + " " + "World";

System.out.println(direct.equals(folded)); // true
System.out.println(direct == folded);      // true
```

`"Hello" + " " + "World"` is a **constant expression** under the Java Language Specification. The compiler can store the result in the `.class` constant pool; constant string values are interned, so `direct` and `folded` share the same reference.

A `final` variable can participate in a constant expression if the variable itself is a **constant variable** (primitive or `String` type, `final`, initialized with a constant expression):

```java
final String prefix = "Hello";
String folded = prefix + " World";

System.out.println(folded == "Hello World"); // true
```

However, `final` alone is not enough:

```java
final String prefix = new String("Hello");
String result = prefix + " World";

System.out.println(result.equals("Hello World")); // true
System.out.println(result == "Hello World");       // false
```

`new String(...)` is not a constant expression. Here concatenation happens at runtime and is not automatically interned as a literal. **Do not assume every statement containing `+` emits `invokedynamic` or `StringBuilder`:** the compiler may already have folded constant expressions beforehand.

## 4. Java 8: typical example using `StringBuilder`

In JDK 8's `javac`, **non-constant** string concatenation was typically lowered into a sequence of `StringBuilder` calls: creating a builder, calling `append` for the parts, and calling `toString`.

Illustrative source code:

```java
static String label(String name, int age) {
    return "Name=" + name + ", age=" + age;
}
```

A simplified bytecode pattern commonly seen in Java 8 (illustrating structure, not a verbatim `javap` dump):

```text
new           java/lang/StringBuilder
dup
invokespecial java/lang/StringBuilder.<init>
ldc           "Name="
invokevirtual java/lang/StringBuilder.append
aload         ...
invokevirtual java/lang/StringBuilder.append
ldc           ", age="
invokevirtual java/lang/StringBuilder.append
iload         ...
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.toString
areturn
```

This model is **useful for historical understanding**, yet it is not a guarantee that every `+` is always one `append()`, that every execution always allocates exactly one builder, or that the JIT cannot eliminate the allocation. Compilers and runtimes have their own optimization opportunities; a chain of multiple operands in one expression can be handled collectively by the compiler.

From this came the familiar explanation: “concatenating `String` with `+` implicitly uses `StringBuilder`”. For modern Java, that mental model must be updated.

## 5. Since Java 9: `invokedynamic` and `StringConcatFactory`

Java 9 introduced **JEP 280 — Indify String Concatenation**, shifting the default mechanism of modern `javac` for many non-constant concatenations to emitting `invokedynamic` bytecode. The bytecode describes a **concatenation call site** that can be linked via bootstrap methods of `java.lang.invoke.StringConcatFactory`, rather than hardcoding a `new StringBuilder` instruction sequence into user bytecode.

For the example `"Name=" + name + ", age=" + age`, bytecode generated by modern `javac` typically contains one `invokedynamic` instruction for the concatenation:

```text
aload         ...
iload         ...
invokedynamic ... // makeConcatWithConstants or an equivalent strategy
areturn
```

This is an **illustrative** outline; exact instruction order, method descriptors, recipes, and bootstrap names in a concrete `javap -v` output depend on the compiler, compilation target, and optimizations of the JDK in use.

### Bootstrap methods and execution

`StringConcatFactory` is the API supporting `invokedynamic` linkage for string concatenation. Two notable bootstrap methods are:

- `StringConcatFactory.makeConcat(...)`: accepts dynamic arguments to concatenate.
- `StringConcatFactory.makeConcatWithConstants(...)`: can carry a **recipe** and constant components, describing how to combine dynamic arguments with constant text.

When a call site is linked, a `CallSite` supplies an appropriate `MethodHandle` to perform concatenation when invoked. The JVM can select, optimize, or evolve the underlying implementation without requiring all bytecode that performs concatenation to be recompiled the same way.

For example, the recipe of `makeConcatWithConstants` may use special markers for dynamic arguments and constants. **The recipe is a linkage detail**, not syntax you must write by hand when using ordinary `+`.

Key point: **`invokedynamic` is a bytecode mechanism**, while `StringConcatFactory` is a runtime-support library mechanism. Using `+` in Java code does not mean programmers are supposed to call the factory manually.

### Goal of JEP 280

The new mechanism enables improving string concatenation strategies in the library/runtime without requiring application code to continually change source or recompile just to receive those improvements. However, having `invokedynamic` **does not guarantee any specific benchmark will run faster**, nor does it mean concatenation allocates zero objects.

Official references: [JEP 280](https://openjdk.org/jeps/280) and [Java SE 21 — StringConcatFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html).

## 6. One source file, multiple bytecodes: how to verify yourself

Save the file `ConcatVersionDemo.java` below. The program is Java 8+ compatible, and of course can be run with JDK 17+.

```java
public class ConcatVersionDemo {
    static String label(String name, int age) {
        return "Name=" + name + ", age=" + age;
    }

    public static void main(String[] args) {
        String name = "Lan";
        int age = 20;

        System.out.println(label(name, age));

        String literal = "Java";
        String folded = "Ja" + "va";
        final String constantPrefix = "Ja";
        String foldedWithFinal = constantPrefix + "va";

        String dynamicPrefix = "Ja";
        String runtime = dynamicPrefix + "va";

        System.out.println("folded == literal: " + (folded == literal));
        System.out.println("final folded == literal: "
                + (foldedWithFinal == literal));
        System.out.println("runtime equals literal: "
                + runtime.equals(literal));
        System.out.println("runtime == literal: " + (runtime == literal));

        System.out.println(1 + 2 + " apples");
        System.out.println("apples: " + 1 + 2);
        System.out.println("name=" + (String) null);
    }
}
```

Use the exact filename `ConcatVersionDemo.java`. Run with JDK 17+:

```bash
javac ConcatVersionDemo.java
java ConcatVersionDemo
```

Exact output:

```text
Name=Lan, age=20
folded == literal: true
final folded == literal: true
runtime equals literal: true
runtime == literal: false
3 apples
apples: 12
name=null
```

This is the result according to Java semantics, independent of whether the JDK version emits `StringBuilder` or `invokedynamic` for runtime concatenation.

### Inspecting bytecode with `javap`

`javap` is the tool bundled with the JDK for inspecting `.class` file structure and bytecode:

```bash
javac -version
java -version
javac --release 8 ConcatVersionDemo.java
javap -c -p ConcatVersionDemo
javap -v ConcatVersionDemo
```

Inspect the bytecode of `label` and `main`. With modern `javac` targeting `--release 8`, you will typically see `new StringBuilder`, `append`, and `toString` sequences for runtime concatenation. Depending on the example, **constant expressions** have already been folded by the compiler and simply load the constant string.

Now recompile the same source file targeting Java 17:

```bash
javac --release 17 ConcatVersionDemo.java
javap -c -p ConcatVersionDemo
javap -v ConcatVersionDemo
```

With a modern JDK's `javac`, runtime concatenations typically appear as `invokedynamic`, and in the `BootstrapMethods` section of `javap -v` you may see `StringConcatFactory.makeConcatWithConstants`. **Inspect actual output** rather than trusting a fixed bytecode snippet in documentation.

**Execution prerequisites:** The `--release 8` and `--release 17` commands above assume a JDK that supports both targets, such as JDK 17 or JDK 21/24. On JDK 8 there is no `--release` option; in that case use the JDK 8 compiler and flags. If a project uses Maven/Gradle or another compiler, verify the actual toolchain/target settings before comparing.

**Note:** Two consecutive `javac` runs overwrite `ConcatVersionDemo.class` in the same directory. Therefore, **inspect `javap` immediately after each compilation**, or compile into two separate output directories when comparing side by side. The command `java ConcatVersionDemo` executes whichever class file currently exists at invocation time, without re-running the compiler.

### Distinguishing three aspects

| Aspect | What are you checking? |
| --- | --- |
| `javac -version` | Version of the **compiler** currently running |
| `javac --release N` | API, syntax, and class-file target the compiler is instructed to emit |
| `java -version` | Version of the **runtime/JVM** used to run |
| `javap -c -v ...` | Bytecode **actually generated** in the `.class` file |
| Runtime performance | Combined outcome of program, data, JVM/JIT, GC, and system |

For example, using `javac` from JDK 24 to compile with `--release 8` **does not turn the compiler into JDK 8's `javac`**. It instructs the compiler to emit Java 8-compatible code/APIs; internal implementation details still depend on the compiler being used. Likewise, a class file targeting Java 17 normally cannot run on a Java 8 runtime due to class-file version and platform library differences.

## 7. What changes and what does not?

| Aspect | Guarantee / appropriate observation |
| --- | --- |
| Result content of `"A" + "B"` | Equals `"AB"` |
| Order and results of operations like `1 + 2 + "x"` | Defined by Java semantics, independent of internal concatenation recipe |
| Are input `String` objects modified? | No; `String` is immutable |
| Can constant expressions be folded at compile time? | Yes, per constant expression rules |
| Must every concatenation use `StringBuilder`? | No |
| Must every concatenation use `invokedynamic`? | No |
| Can Java 8 and Java 17 `javac` emit different bytecode? | Yes |
| Can two JVMs running the same bytecode optimize differently? | Yes, while preserving semantics |
| Does `javap` reflect every runtime JIT optimization? | No; it displays bytecode in the class file |
| Can you accurately predict object counts just from `+` signs? | Unreliable if ignoring folding, intermediate objects, and runtime optimizations |

**Do not confuse the class file constant pool with the String pool.** The constant pool in `.class` is a table of entries representing constants, names, references, and linkage data needed by bytecode. The String pool is the runtime mechanism managing interned strings. They both relate to literals, but are not two names for the same structure.

## 8. When should you use `+`, `StringBuilder`, or other APIs?

Differences in bytecode do **not** change API selection guidance: `+` is clear enough for a short expression; `StringBuilder` is generally appropriate when accumulating across multiple loop iterations; `String.join`/`StringJoiner` are convenient for delimiters. See the lesson **Concatenation in a single expression vs. accumulation across loops** for a full analysis of those scenarios.

## 9. Measuring performance properly and avoiding reliance on JDK details

`invokedynamic` bytecode does not directly prove concatenation is faster or allocation-free: JIT, warm-up, escape analysis, GC, string length, and input data all affect results. If you need to compare JDKs/compilers, check `javac -version`, `java -version`, `--release`, and `javap` first, then run a representative benchmark such as JMH.

Do not build application logic around recipe shape, object counts guessed from `javap`, or internal compiler flags.

## 10. Common mistakes

1. **Claiming the compiler always converts `+` into `StringBuilder`.** This commonly describes Java 8 `javac`, not Java 9+ or all compiler variants.
2. **Claiming every `+` in Java 17 uses `invokedynamic`.** Constant expressions may already be folded at compile time; the rest depend on compiler and target.
3. **Using `java -version` to infer the compiler version.** Runtime and compiler tools can differ; check both `javac -version` and `--release`.
4. **Assuming `--release 8` runs an actual JDK 8 compiler.** No: it requests compatible code/API target generation when supported by the compiler.
5. **Reading `javap` output as a list of objects actually allocated at runtime.** The JIT can optimize during execution; `javap` only shows bytecode written into the class file.
6. **Assuming `invokedynamic` means concatenation behaves differently from old `+`.** Regardless of mechanism, a valid program must obey Java semantics.
7. **Writing `a + b + c` and assuming everything is numeric addition.** Once a `String` appears, subsequent operands concatenate as text; use parentheses to clarify intent.
8. **Writing `StringBuilder` inside a loop while still creating a new builder on every iteration.** When accumulating, create and reuse the builder in the appropriate scope.
9. **Benchmarking `+` vs. builder without controlling JDK, data, and warm-up.** Performance conclusions can be wrong; use proper measurement tools.
10. **Conflating the class-file constant pool with the runtime String pool.** The two concepts serve different purposes.

## 11. Self-check

Given the following code:

```java
final String a = "he";
String b = "he";
String x = a + "llo";
String y = b + "llo";

System.out.println(x == "hello");
System.out.println(y.equals("hello"));
System.out.println(y == "hello");
```

Result under Java semantics:

```text
true
true
false
```

`a` is a constant variable, so `a + "llo"` is a constant expression and is interned. `b` is not a constant variable, so `b + "llo"` is concatenated at runtime and has content equal to `"hello"`, though it is not the same literal object. Changing the JDK or compilation flags may make **the bytecode concatenating `y` look different**, yet it cannot alter the results of the three checks contrary to the specification.

**Takeaway:** The semantics of `String` and the `+` operator belong to the **Java language**; how the compiler lowers concatenation into `StringBuilder` or `invokedynamic` and how the runtime optimizes it belong to the **JDK/JVM implementation**. Write code based on language semantics, inspect actual output with `javap` when investigating, and measure performance in the target environment.

### References

- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280)
- [Java SE 21 — StringConcatFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)
- [Java Language Specification — `15.18.1`, String Concatenation Operator `+`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18.1)
