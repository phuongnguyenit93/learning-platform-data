# String Concatenation via `StringConcatFactory` and `invokedynamic`

## 1. Big picture

Java lets you concatenate strings naturally using the `+` operator:

```java
String name = "Java";
int version = 17;
String description = "Language: " + name + ", version=" + version;
```

This is an illustrative snippet inside a method body. The final value is `Language: Java, version=17`. The `+` syntax is part of the **Java language**, whereas how the compiler emits bytecode to execute the concatenation is an implementation choice.

Starting in **Java 9**, following **JEP 280 (Indify String Concatenation)**, the `javac` compiler typically emits dynamic `String` concatenation using the **`invokedynamic`** bytecode instruction. When linking that call site, the JVM uses a bootstrap method in **`java.lang.invoke.StringConcatFactory`** to construct a concatenation strategy suited to the argument types and constant segments.

Concepts to keep separate:

- `String` remains **immutable**: a concatenation expression produces a resulting string value according to language semantics.
- `+` remains standard Java syntax; developers do not call `StringConcatFactory` directly.
- `invokedynamic` is a **bytecode instruction** that links a call site via a bootstrap method, not a new Java statement or a reflective method-name lookup on every execution.
- `StringConcatFactory` is **runtime infrastructure** for building concatenation call sites; it is not a data format or a string storage repository.

When an expression consists solely of string constants, `javac` can fold the value at compile time and does not need `invokedynamic` for that concatenation itself. Therefore, inspect the bytecode of the **specific case** rather than asserting that every `+` becomes `invokedynamic`.

## 2. Before Java 9: concatenation typically compiled to `StringBuilder`

A simple example:

```java
public class Contrast {
    public static String render(String name, int n) {
        return "Name=" + name + ", count=" + n;
    }
}
```

When compiled with `javac --release 8`, the bytecode can contain a sequence of operations equivalent to:

```text
new           java/lang/StringBuilder
invokespecial java/lang/StringBuilder.<init>
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.toString
```

In actual output, the bytecode also includes argument-loading instructions and selects specific overloads such as `append(String)` and `append(int)`. The listing above is an **abbreviated summary of the main operations**, not a verbatim disassembly.

This older approach concatenated more efficiently than allocating a separate string for each pair of operands. However, it baked the concatenation strategy directly into compiler-emitted bytecode. To change the overall strategy, the JVM/JIT had to recognize and optimize the corresponding `StringBuilder` bytecode pattern.

## 3. Since Java 9: `invokedynamic` separates concatenation semantics from execution strategy

With the same `Contrast` class above, when compiled with `javac --release 17`, `javap -c` shows an instruction of the form:

```text
invokedynamic #... // makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
```

This is a **schematic excerpt of the output format**; the constant-pool index depends on the compiled class file. The `String` and `int` parameters in the descriptor show that the call handles dynamic values of those types, while fixed parts such as `Name=` and `, count=` can be placed into a recipe as constants. Observing this instruction does not mean Java abandoned `String` immutability or moved dynamic concatenation to compile time: it only changes **how the concatenation logic is linked and invoked at runtime**.

High-level flow:

```text
Java code: "Name=" + name + ", count=" + n
          |
          v
javac (target Java 9+)
          |
          v
Class file: invokedynamic + BootstrapMethods + recipe/metadata
          |
          v
JVM links invokedynamic with StringConcatFactory
          |
          v
CallSite / MethodHandle with matching type
          |
          v
Runtime executes concatenation with current arguments
          |
          v
Resulting String
```

**The JVM can optimize and the JIT can inline** the linked call site. From a single `invokedynamic` instruction in a class file, you cannot conclude exactly how many objects are created, how many byte arrays are allocated, or how many machine instructions run on each call: that belongs to the specific JVM's runtime optimizations.

## 4. Bootstrap methods and call-site linking

An `invokedynamic` instruction references a constant-pool entry describing the invocation name, function type (parameter and return types), and **bootstrap method** info. When the JVM needs to link the instruction, the bootstrap method is invoked with the lookup context and associated static constants, returning a `CallSite` with an appropriate target.

For string concatenation generated by `javac`, the common bootstrap methods are:

- `StringConcatFactory.makeConcat(...)`: provides a concatenation form based purely on the dynamic arguments.
- `StringConcatFactory.makeConcatWithConstants(...)`: additionally accepts a **recipe** and bootstrap constants, allowing fixed text to be interleaved with dynamic values.

These methods belong to the `java.lang.invoke` API. `javac` commonly selects `makeConcatWithConstants` in modern JDK releases; exact details can vary by compiler version, release target, code shape, and optimizations.

In the `makeConcatWithConstants` form, a **recipe** can contain two control markers:

| Marker in recipe | Meaning |
| --- | --- |
| `\u0001` | Inserts a value from the dynamic arguments of the concatenation call |
| `\u0002` | Inserts a constant from the static bootstrap constants |
| Any other character | Fixed text inserted directly into the output |

For example, a recipe printed by `javap -v` looking like `Hello \u0001 \u0001 / \u0001` describes a concatenation template with three dynamic values at three positions. The `\u0001` marker in disassembly denotes **a single control character**, not six literal characters in user output. Do not manually construct recipes by pasting arbitrary strings together and expect every implementation to share the same strategy.

**Linking a call site** does not mean "re-parsing the `+` expression from source code on every execution." The JVM links the instruction to a target; subsequent executions invoke that target via the JVM's dispatch mechanism, and the runtime compiler can optimize it further. Linking usually happens when the site is first executed, though application code should rely on **Java semantics**, not on a rigid linking schedule.

## 5. Runnable Java 17+ example

Create `ConcatIndyDemo.java`:

```java
public class ConcatIndyDemo {
    static String mark(String name, String value) {
        System.out.println("eval " + name);
        return value;
    }

    public static void main(String[] args) {
        String who = "Java";
        int version = 17;
        Object absent = null;
        String message = "Hello " + who + " " + version + " / " + absent;
        System.out.println("message = " + message);

        String order = mark("left", "A") + mark("right", "B") + 7;
        System.out.println("order = " + order);

        String folded = "foo" + "bar";
        System.out.println("folded = " + folded);

        String explicit = new StringBuilder()
                .append(who)
                .append("!")
                .toString();
        System.out.println("builder = " + explicit);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ConcatIndyDemo.java
java ConcatIndyDemo
```

Verified standard output from running the program:

```text
message = Hello Java 17 / null
eval left
eval right
order = AB7
folded = foobar
builder = Java!
```

Explanation of notable details:

1. A `null` value in a concatenation expression is converted to the text `"null"` according to Java's string conversion rules. Do not equate `+` concatenation with calling `someString.concat(null)` directly, because `concat` throws `NullPointerException` when passed `null`.
2. Both `mark` calls are evaluated **from left to right**, once each. Changing the bytecode strategy to `invokedynamic` is not allowed to reorder operand side effects. Thus the console prints `eval left` followed by `eval right`.
3. `mark("left", "A") + mark("right", "B") + 7` yields `AB7` because once addition is in string-concatenation mode, the number `7` is converted to text according to concatenation rules. The numeric literal `7` may be folded by the compiler into the recipe rather than passed as a separate dynamic argument.
4. `"foo" + "bar"` is a **constant expression**; `javac` folds it into `"foobar"` directly in the class file. The statement printing `"folded = " + folded` in the example can still be a separate `invokedynamic` site because `folded` is an ordinary local variable, not a compile-time constant variable declared `final`.
5. `new StringBuilder(...).append(...).toString()` is explicit string building. It remains completely valid in modern Java; the compiler does not require programmers to write it for a normal `+` expression.

## 6. Using `javap` to inspect bytecode evidence yourself

After compiling, run:

```bash
javap -c -v ConcatIndyDemo
```

In the output, focus on three places:

**A. Instruction in the `Code` section:** An instruction of the form:

```text
invokedynamic #... // makeConcatWithConstants:(Ljava/lang/String;ILjava/lang/String;)Ljava/lang/String;
```

This is the concatenation for `message` in the example, taking dynamic arguments of types `String`, `int`, `String` (`javac` may convert `Object absent` to `String` before invoking the site). The fixed string `Hello` and the separators can live inside the recipe.

**B. The `BootstrapMethods` section:** In `javap -v`, you can see a bootstrap handle pointing to:

```text
REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
```

along with method arguments such as the recipe, e.g. `Hello \u0001 \u0001 / \u0001`. Exact ordering and constant-pool indices are determined by the JVM/class file and may differ if you change the code or compiler.

**C. Constant expression:** For `String folded = "foo" + "bar";`, `javap` can display:

```text
ldc #... // String foobar
```

`ldc` loads a constant from the constant pool. This is evidence that concatenating *two string constants* was resolved at compile time; there is no separate concatenation call site for that expression. If you see `invokedynamic` on the line printing `folded`, that is the other concatenation: `"folded = " + folded`.

To clearly compare the old and new mechanisms, create `Contrast.java` from section 2 and compile it into **two different output directories**:

```bash
javac --release 8 -d out8 Contrast.java
javac --release 17 -d out17 Contrast.java
javap -classpath out8 -c Contrast
javap -classpath out17 -c Contrast
```

Create the `out8` and `out17` directories beforehand if your build environment requires it. With the tested `javac` compiler, target 8 uses `StringBuilder.append`, whereas target 17 uses `invokedynamic`. The `--release 8` flag compiles a class targeting Java 8 API/bytecode compatibility; it does not require actually installing JDK 8 to observe the output, as long as your current JDK supports that release target.

**Important:** `javap` shows the strategy emitted by the compiler into the class file. It is **not a runtime performance measurement** and does not display the final machine code chosen by the JIT once the program warms up.

## 7. The semantics of the `+` expression stay unchanged

Regardless of how bytecode is generated, a Java program must preserve the semantics of the `+` operator:

### Distinguishing numeric addition from string concatenation

```java
String a = 1 + 2 + "x";    // "3x"
String b = "x" + 1 + 2;    // "x12"
String c = "x" + (1 + 2);  // "x3"
```

The `+` operator is left-associative. Before a `String` operand appears, `1 + 2` is numeric addition. Once in string concatenation mode, subsequent values are converted to text. Use parentheses to prevent logic bugs rather than relying on bytecode optimization details.

### Operand evaluation order and exceptions

```java
String s = first() + second() + third();
```

The three calls (assuming compatible return types) must be evaluated in the order specified by Java; observable side effects and exceptions cannot be altered just because the compiler uses `invokedynamic`. A compiler cannot "optimize away" a call that has side effects.

### Constants fold early; runtime handles only what is needed

```java
String compileTime = "ab" + "cd"; // "abcd"
String runtime = prefix + "cd";   // depends on prefix
```

For an all-constant expression, the compiler can fold the strings. When `prefix` is a variable with a runtime value, concatenation must occur at runtime (via `invokedynamic` or another compiler strategy).

### `null` and conversion to String

When concatenating an object (including `null`), Java applies string conversion, whose resulting text is normally equivalent to `String.valueOf(value)`. For non-null objects, the object's `toString()` may be called; that method can contain logic or side effects. The result and evaluation order remain governed by Java semantics; do not assume every object is already converted to a `String` at compile time.

## 8. Performance: when to use `+`, when to use `StringBuilder`

**For a single clear concatenation expression**, writing:

```java
String line = "user=" + user + ", count=" + count;
```

is usually the cleanest choice. On modern Java, `javac` and the JVM can build and optimize the whole concatenation, so **there is no need to manually replace every `+` with `StringBuilder`** out of a belief that it is guaranteed to be faster. Exact optimization depends on the compiler, JVM, input data, and how hot the code path is.

**For accumulating strings across many loop iterations**, each `+=` on a `String` can produce a new intermediate string, causing repeated copying and heavy cost as data grows. Consider this example:

```java
String output = "";
for (String item : items) {
    output += item;
}
```

When combining many elements, a clearer, purpose-built solution is typically:

```java
StringBuilder builder = new StringBuilder();
for (String item : items) {
    builder.append(item);
}
String output = builder.toString();
```

These are **two illustrative snippets inside a method body**, assuming an `items` variable of type `Iterable<String>` or an appropriate collection. You cannot claim every `+=` loop is equally slow because the JVM can optimize some cases. Still, `StringBuilder` directly expresses incremental accumulation and avoids depending on whether the compiler/JIT recognizes an optimization across loop iterations.

If you need to benchmark, measure in a representative environment using a microbenchmarking tool like JMH; avoid taking a single `System.nanoTime()` measurement and extrapolating overall performance. JIT warm-up, dead-code elimination, escape analysis, GC, and result formatting can all skew numbers.

**Do not assume `invokedynamic` never allocates.** Runtime helpers like `StringConcatFactory` allow the JVM to select efficient strategies, yet allocation/compact-string/JIT behavior is not a fixed guarantee of the `+` syntax.

## 9. Common misconceptions

1. **"Every string concatenation calls `StringBuilder`":** this is no longer true by default with `javac` on Java 9+. Inspect the bytecode when needed.
2. **"Every `+` becomes `invokedynamic`":** constant expressions can be folded at compile time; arithmetic `+` is numeric addition; compilers may use other mechanisms.
3. **"`invokedynamic` means calling reflection every time":** it is a bytecode instruction backed by a linked `CallSite`, not searching for method names in source code on each concatenation.
4. **"`StringConcatFactory` makes `String` mutable":** the resulting string still has immutable `String` semantics.
5. **"Replacing `+` with `StringBuilder` is guaranteed to be faster":** depends on context, compiler, JVM, and workload; a single simple concatenation should normally favor readability.
6. **"`StringBuilder` is obsolete":** it remains the right tool for incremental string building, especially inside loops.
7. **"`invokedynamic` bytecode proves the runtime does zero allocations":** bytecode and JIT-optimized machine code are two different layers.
8. **"Operand evaluation order can be reordered for optimization":** Java requires preserving exact evaluation order, side effects, and exceptions.
9. **"`null` in `+` is the same as calling `String.concat(null)`":** `+` applies string conversion, whereas `concat` passed `null` throws an exception.
10. **"Reading one `javap` output is enough to assert behavior across all JDKs":** output depends on compiler version, release target, and expression shape. Always state the test environment.

## 10. Checklist for verifying a string concatenation yourself

1. Determine what the Java expression means: is it numeric addition or string concatenation, are there `null` values, side-effecting methods, or constant parts?
2. Compile with the release target you actually care about, such as `javac --release 17`.
3. Run `javap -c -v` to look for `invokedynamic`, `BootstrapMethods` entries, the bootstrap handle, and the recipe. If you see `ldc` with an already-folded string, that is likely constant folding.
4. Execute the program and verify **result content, side-effect order, and `null` handling**; do not look solely at bytecode instructions.
5. If your goal is performance tuning, measure real work and benchmark rigorously before restructuring code.

**Key takeaway:** `+` is language-level string concatenation syntax. Since Java 9, `javac` commonly compiles dynamic concatenation into `invokedynamic`; the JVM uses `StringConcatFactory` as a bootstrap to link an optimizable call site. The internal mechanism changed, while **immutable string semantics, evaluation order, and concatenation results must remain unchanged**.
