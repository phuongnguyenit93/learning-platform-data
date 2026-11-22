# Mapping lambdas and string concatenation to bytecode by compiler version

The same Java source can generate **different bytecode** depending on the `javac` version, `--release`, build tools, and compiler strategy. Two very typical examples are **lambda/method reference** expressions and **string concatenation using the `+` operator**. They illustrate the difference between:

1. **Java source semantics**: what result the code must produce according to the Java Language Specification (JLS).
2. **How the compiler lowers source to bytecode** (*lowering/desugaring*): which instructions are used, and whether synthetic methods or `StringBuilder` are generated.
3. **Runtime linkage**: `invokedynamic` together with a bootstrap method linking the call site.
4. **JVM/JIT optimization implementation**: it may generate/hide classes, inline, cache, or generate machine code in its own way while still preserving the guaranteed semantics.

Goal: be able to read `javap -c -v -p`, analyze `CONSTANT_InvokeDynamic_info` and `BootstrapMethods`, explain capture and functional interfaces, compare Java 8 with Java 9+/17 for string concatenation, and avoid inferring a single bytecode pattern as a mandatory rule for all compilers.

## 1. Version framework: compiler, target class file, and runtime are three different things

| Version / option | Lambda/method reference | String concatenation `"a" + value` | Things to note |
| --- | --- | --- | --- |
| Java 7 and earlier | No Java 8 lambda syntax yet | Compiler usually uses `StringBuilder` (or another compatible strategy) | JVM `invokedynamic` was added in Java 7; having the opcode does not mean Java source already had lambdas |
| `javac` Java 8 | Usually uses `invokedynamic` + `LambdaMetafactory` for lambdas/method references | Usually uses `new StringBuilder`, `append`, `toString` | Java 8 class files have major version **52** |
| `javac` Java 9+ with a target supporting new features | Can continue to use `invokedynamic` + `LambdaMetafactory` | Java 9 introduces lowering via `invokedynamic` + `StringConcatFactory` (JEP 280) | Strategy, bootstrap arguments, and layout of synthetic methods can change across compilers and builds |
| A modern `javac` running `--release 8` | May still use `invokedynamic` for lambdas like Java 8 | `javac` typically generates a Java 8-compatible `StringBuilder` path | `--release 8` restricts language/API/class file format; **it does not turn a modern compiler into the exact javac 8 binary** |
| Modern `javac` running `--release 17` | Can use `LambdaMetafactory` | Usually generates `StringConcatFactory.makeConcatWithConstants` | Java 17 class files have major version **61**, requiring a runtime that can read the corresponding version |

**Note:** these are **typical behaviors of OpenJDK `javac`**, not a mandate from the JLS that "every compiler must generate this exact opcode". Java source is standardized in terms of **observable semantics**; JVM bytecode also has its own specification, but compilers have many valid representation choices.

When investigating, record all four pieces of information: `javac -version`; the `--release` or `-source`/`-target` option; the `.class` file actually produced; and `java -version` of the executing JVM. Do not use the runtime version to infer with certainty which compiler version created the class.

## 2. Why distinguish the `invoke*` instructions?

| Opcode | Main meaning | Relevance to this topic |
| --- | --- | --- |
| `invokestatic` | Calls a linked static method; no receiver instance | Compiler-generated static helpers for lambdas or factory calls can often use method handles pointing to static methods |
| `invokevirtual` | Calls a class instance method, selecting the implementation based on the runtime receiver | Calls inside a lambda may call instance methods; the `StringBuilder.append` chain is `invokevirtual` |
| `invokeinterface` | Calls a method through an interface reference, selecting the implementation matching the receiver | Calling `IntUnaryOperator.applyAsInt` or `Runnable.run` on a function object |
| `invokespecial` | Constructors, `super`, and special instance calls | `new StringBuilder; invokespecial <init>` in Java 8 lowering |
| **`invokedynamic`** | Links a **call site** via a bootstrap method described in the class file | Central point of lambdas/method references and modern string concat |

Do not equate **`invokedynamic` = "calling a virtual method according to the actual type of the object"**. `invokevirtual`/`invokeinterface` is a different mechanism. `invokedynamic` links a `CallSite` that has a `MethodHandle` target; that target can perform many kinds of operations as decided by the bootstrap.

Each `invokedynamic` instruction in `code[]` references an entry of type `CONSTANT_InvokeDynamic_info` in the constant pool. That entry leads to a `BootstrapMethods` entry at the class file level and a `NameAndType` describing the name/descriptor of the **dynamic call site**.

## 3. Reading `CONSTANT_InvokeDynamic_info` and `BootstrapMethods`

A conceptual structure:

```text
method's code[]
  invokedynamic #N, 0
       |
       v
constant_pool[#N] = CONSTANT_InvokeDynamic_info
  ├── bootstrap_method_attr_index ───────┐
  └── name_and_type_index                │
         ├── call site name              │
         └── call site descriptor        │
                                         v
                   BootstrapMethods[bootstrap_method_attr_index]
                     ├── bootstrap_method_ref
                     │     └── CONSTANT_MethodHandle_info
                     └── bootstrap_arguments[]
                           └── constant pool entries
```

In a class file, `CONSTANT_InvokeDynamic_info` has the fields `bootstrap_method_attr_index` and `name_and_type_index`. The bootstrap index points to the **BootstrapMethods table**, which is different from the **constant pool index** printed right after the opcode. The number `#N` and the number `#0` on the `InvokeDynamic #0:...` line are **not** the same kind of index.

The bootstrap method is called by the JVM during call-site linkage, receiving information such as `MethodHandles.Lookup`, the call-site name, `MethodType`, and static arguments. It returns a `CallSite` with an appropriate target. After linkage, **executing the dynamic call site** uses this target with the **dynamic arguments on the operand stack**.

Distinguish three levels of data:

- **Static bootstrap arguments**: described in the constant pool/`BootstrapMethods`; for example, the method type and implementation method handle of a lambda, or the concat recipe.
- **Dynamic call-site arguments**: actual values on the operand stack when the instruction executes; for a capturing lambda, these may be the captured values; for string concatenation, these are usually the components to concatenate.
- **Arguments of the functional interface call**: arrive **after** the lambda object already exists, for example `fn.applyAsInt(4)`; `4` is not necessarily an argument of the call site that creates the lambda.

This is why two `invokedynamic` instructions can look similar in `javap` yet behave very differently if their bootstrap methods differ.

## 4. Lambda expression: "creating the function object", then "calling the SAM" are two steps

A **functional interface** has one abstract method according to Java rules; this method is often called the **SAM (single abstract method)**. For example, `IntUnaryOperator` has `int applyAsInt(int operand)`.

When the compiler sees:

```java
int offset = 3;
IntUnaryOperator addOffset = x -> x + offset;
int answer = addOffset.applyAsInt(4);
```

This is an **illustrative fragment**, assuming `java.util.function.IntUnaryOperator` is imported and it is inside a method. It can be broken down into:

1. The compiler checks that the lambda is compatible with the target type `IntUnaryOperator`, determining the parameter/return types and captured variables.
2. The compiler generates or references an **implementation method** containing the corresponding body (usually a private static synthetic method named something like `lambda$...`); this is a **`javac` strategy**, not a mandatory name according to the JLS.
3. Bytecode evaluates and pushes the captured variable `offset` onto the operand stack, then executes **`invokedynamic`**; this call site creates/returns an object compatible with `IntUnaryOperator`.
4. After that, `invokeinterface IntUnaryOperator.applyAsInt:(I)I` takes the function object and the argument `4` to execute the behavior provided by the lambda.

**The two stages should not be conflated:** `invokedynamic` at the lambda site usually **creates/obtains the function object**; `invokeinterface` at `applyAsInt(4)` is what **invokes the function**.

### Capturing and non-capturing

- `x -> x * 2` does not need to read an outer local variable: **non-capturing lambda**. The call site that creates the function object usually has a descriptor **taking no capture arguments**, for example `()Ljava/util/function/IntUnaryOperator;`.
- `x -> x + offset` must carry the value of `offset` from the lexical scope: **capturing lambda**. The call site may have the descriptor `(I)Ljava/util/function/IntUnaryOperator;`; `I` is the type of the captured `offset`.
- `IntUnaryOperator f = SomeClass::triple` can be a **non-capturing method reference** pointing to the method handle of `triple`, usually without needing the compiler to generate a separate `lambda$...` helper.
- `instance::method` is a **bound method reference**: the receiver is evaluated at the time the method reference is created and may be captured. With a null receiver, evaluating a bound reference can throw a `NullPointerException` right at creation time.
- With `ClassName::instanceMethod` as an unbound method reference, the receiver becomes a parameter when calling the SAM, rather than pre-capturing a specific object.

**Captured local values must be final or effectively final.** When `offset` is a primitive, the lambda holds the captured value, not "looking back at the caller's local slot" after the caller leaves scope. With a reference to a mutable object, the lambda holds the reference; it can still see the **object's** state change afterward. Do not interpret Java capture as a pointer to a local slot whose lifetime has ended.

### Do not rely on the identity or class name of a lambda object

The specification does not require a lambda to be implemented by an anonymous class with a fixed name or to create a new object on every evaluation of a non-capturing lambda. The JVM may reuse instances, generate hidden classes, or optimize with JIT. Avoid testing `getClass().getName()`, class loaders, synthetic method names, object counts, or `==` to infer the "correctness" of a lambda.

## 5. Role of `LambdaMetafactory`

In typical OpenJDK `javac`, the `BootstrapMethods` entry for a lambda/method reference references:

```text
REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
```

`LambdaMetafactory.metafactory` receives information about the interface/SAM and the implementation method, then creates a call site that can produce a function object. The essentially important parameters:

| Information | Purpose |
| --- | --- |
| `invokedType` (`MethodType` of the call site) | The capture types entering the dynamic call site and the returned functional interface object type |
| `samMethodType` | Method type of the SAM at the erased/descriptor type level |
| `implMethod` (`MethodHandle`) | Implementation method called by the lambda object, such as a synthetic helper or the target method of a method reference |
| `instantiatedMethodType` | Method type after considering the target functional interface/generics for type checking and adaptation |
| SAM name on the call site | For example `applyAsInt`, `run`, `apply` |

Do not confuse `samMethodType` with `instantiatedMethodType`: generic erasure can make the two types different; the implementation may need casts, boxing/unboxing, widening, or bridge adaptation.

Some special cases such as **serializable** lambdas, marker interfaces, or additional bridge methods may use `LambdaMetafactory.altMetafactory`. Do not assume every `invokedynamic` in a class uses `metafactory`: modern string concatenation usually has a **different bootstrap**.

## 6. Runnable Java 17 example: lambda, capture, and method reference

Create the file **`LambdaTranslation.java`**:

```java
import java.util.function.IntUnaryOperator;

public class LambdaTranslation {
    private static IntUnaryOperator plus(int amount) {
        return x -> x + amount;
    }

    private static int triple(int value) {
        return value * 3;
    }

    public static void main(String[] args) {
        int offset = 3;

        IntUnaryOperator capturing = x -> x + offset;
        IntUnaryOperator plain = x -> x * 2;
        IntUnaryOperator methodReference = LambdaTranslation::triple;
        IntUnaryOperator fromFactory = plus(5);

        System.out.println("capture=" + capturing.applyAsInt(4));
        System.out.println("plain=" + plain.applyAsInt(4));
        System.out.println("methodRef=" + methodReference.applyAsInt(4));
        System.out.println("factory=" + fromFactory.applyAsInt(4));
    }
}
```

Run with **JDK 17+** whose compiler supports `--release 17`:

```bash
javac --release 17 LambdaTranslation.java
java LambdaTranslation
javap -c -v -p LambdaTranslation
```

**Stdout of `java LambdaTranslation` alone:**

```text
capture=7
plain=8
methodRef=12
factory=9
```

Explanation:

- `capturing` takes `offset = 3` and argument `4`, resulting in `7`.
- `plain` uses no capture and multiplies `4 * 2 = 8`.
- `methodReference` points to the static method `triple`, resulting in `4 * 3 = 12`.
- `fromFactory` captures the parameter `amount = 5` in method `plus`, so `4 + 5 = 9`.

### Common traces in `javap`

Reading method `main` will show **`invokedynamic`** call sites to create the function objects, then **`invokeinterface`** invocations to `IntUnaryOperator.applyAsInt:(I)I` when performing the computation.

A **schematic** example, not verbatim output with fixed indexes:

```text
iload_1
invokedynamic #A, 0    // InvokeDynamic: applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
astore_2

invokedynamic #B, 0    // InvokeDynamic: applyAsInt:()Ljava/util/function/IntUnaryOperator;
astore_3

...                    // load lambda object and int 4
invokeinterface #C, 2 // IntUnaryOperator.applyAsInt:(I)I
```

In the schematic, `iload_1` represents the local holding `offset`, while `#A`/`#B`/`#C` are placeholders for actual constant pool indices. Specific local/offset slots depend on the compiler; focus on the descriptor with **one capture argument** versus the descriptor **with no capture**.

Under `BootstrapMethods`, you can see `REF_invokeStatic LambdaMetafactory.metafactory`, `MethodType (I)I`, and `REF_invokeStatic` pointing to implementation methods such as `lambda$main$...` or `triple`.

`javap -p` displays private/synthetic helpers; `javap -v` can display `ACC_SYNTHETIC` flags. Helper names, lambda numbering, and the order of bootstrap entries **are not stable like a public API**.

### Why does the lambda example also have `StringConcatFactory` when compiled with `--release 17`?

The four statements `System.out.println("capture=" + ...)` also contain string concatenation with a dynamic `int` value. Therefore, **the same class** can contain:

- `invokedynamic` using `LambdaMetafactory` to create a lambda/method-reference object.
- `invokeinterface` to call the SAM.
- `invokedynamic` using `StringConcatFactory` to concatenate the label with the numeric result.
- `invokevirtual` to call `PrintStream.println`.

Do not count all `invokedynamic` instructions and conclude there are that many lambdas. **Always trace each bootstrap entry**.

## 7. String concatenation before Java 9: lowering usually used `StringBuilder`

Consider the source:

```java
String result = "name=" + name + ", count=" + count;
```

This is an **illustrative snippet inside a method**. On `javac` Java 8 or a modern `javac` compiling with `--release 8`, typical bytecode may include:

```text
new java/lang/StringBuilder
dup
invokespecial java/lang/StringBuilder."<init>":()V
ldc "name="
invokevirtual java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
aload_0
invokevirtual java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
ldc ", count="
invokevirtual java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
iload_1
invokevirtual java/lang/StringBuilder.append:(I)Ljava/lang/StringBuilder;
invokevirtual java/lang/StringBuilder.toString:()Ljava/lang/String;
areturn
```

This is a **simulated opcode sequence without offsets or constant pool indexes**, not asserting that `javac` must generate the exact same sequence or append order across all versions. The idea: build a mutable builder, append the components according to Java semantics, and then obtain the resulting String.

The limitation of this compilation approach is that **the concatenation strategy is "baked" into the bytecode**: the class file has specific `StringBuilder.append` calls. The JVM/JIT can still optimize builders/escape analysis, but the compiler already decided the bytecode shape at build time.

JEP 280 changed this strategy so the runtime has more freedom to choose how to concatenate strings without needing to change source; it **did not** add a new string concatenation operator to the Java language.

## 8. Since Java 9: `StringConcatFactory` and concat call sites via `invokedynamic`

With `javac` Java 9+ and an appropriate target, the compiler usually loads the dynamic components onto the operand stack and executes **a single `invokedynamic`** for the concat expression. The bootstrap can be:

- `StringConcatFactory.makeConcat`: concatenates dynamic arguments according to the method type.
- `StringConcatFactory.makeConcatWithConstants`: additionally uses a **recipe** and constants from `BootstrapMethods`; this is the very common choice in class files generated by Java 17 `javac`.

Schematic form for the example `"name=" + name + ", count=" + count`:

```text
aload_0
iload_1
invokedynamic #N, 0
  // InvokeDynamic: makeConcatWithConstants:
  // (Ljava/lang/String;I)Ljava/lang/String;
areturn
```

If the recipe is "`name=<arg>, count=<arg>`" in a descriptive sense, the runtime uses it to assemble the two dynamic arguments. The exact encoding in the `StringConcatFactory` API:

| Recipe component | Meaning |
| --- | --- |
| Character **U+0001** | Placeholder for a **dynamic argument** passed to the call site |
| Character **U+0002** | Placeholder for a **static constant** passed via bootstrap arguments |
| Other ordinary characters | Literal text inserted verbatim into the result |

For example, the recipe can be represented **in human-readable notation** as `name=[U+0001], count=[U+0001]`. When viewing actual `javap -v`, the placeholders may be displayed as escape sequences, **not** the bracketed character string `[U+0001]`. Do not infer that each `+` sign in source corresponds to one recipe entry or a separate `invokedynamic`.

**Core difference from lambdas:**

- A lambda bootstrap returns a call site whose target **creates a function object**; then the SAM is called separately.
- A string-concat bootstrap returns a call site whose target **computes the resulting String directly from the arguments** of that concatenation.
- Same `invokedynamic` opcode, but **bootstrap, call-site descriptor, target, and output product** are different.

`StringConcatFactory` appeared in Java 9. Java 8 classes cannot depend on this API on a Java 8 runtime; that is why building for `--release 8` needs compatible lowering instead of calling `StringConcatFactory`.

## 9. Java 17 program to compare the two compilation approaches

Create the standalone file **`StringConcatTranslation.java`**:

```java
public class StringConcatTranslation {
    static String message(String name, int count) {
        return "name=" + name + ", count=" + count;
    }

    static String sum(int a, int b) {
        return "sum=" + (a + b);
    }

    static String maybeNull(Object value) {
        return "item=" + value;
    }

    static String folded() {
        return "constant=" + "A" + 1 + 2;
    }

    public static void main(String[] args) {
        System.out.println(message("Lan", 7));
        System.out.println(sum(2, 3));
        System.out.println(maybeNull(null));
        System.out.println(folded());
    }
}
```

**Output of `java StringConcatTranslation`** is the same for classes compiled for Java 8 or Java 17, when run on a compatible runtime:

```text
name=Lan, count=7
sum=5
item=null
constant=A12
```

- `"name=" + name + ", count=" + count` performs string conversion for dynamic parameters, while the compiler decides the bytecode sequence to achieve the result.
- `"sum=" + (a + b)` computes `int` arithmetic before concatenating; writing `"sum=" + a + b` would concatenate sequentially from left to right, giving `sum=23` for inputs 2 and 3.
- `"item=" + value` with `value == null` produces the character string `null`, without automatically throwing `NullPointerException` just from concatenating a null reference.
- `"constant=" + "A" + 1 + 2` is an eligible constant expression; the compiler can fold it into `"constant=A12"` and return it via `ldc`, **without needing** `StringBuilder` or `invokedynamic` for method `folded` itself.

### Hands-on on a modern JDK supporting both target releases

Using **the same `javac`** (for example JDK 17 or 21), compile sequentially and save the disassembly after each build:

```bash
javac -version

javac --release 8 StringConcatTranslation.java
javap -c -v -p StringConcatTranslation > concat-release8.txt
java StringConcatTranslation

javac --release 17 StringConcatTranslation.java
javap -c -v -p StringConcatTranslation > concat-release17.txt
java StringConcatTranslation
```

**Reading the saved `javap` output:**

1. For target 8, inspect method `message`: class file major **52**; common `javac` versions show the `new StringBuilder`, `append`, and `toString` sequence.
2. For target 17, class file major **61**; `message` usually contains `invokedynamic makeConcatWithConstants` and has a `BootstrapMethods` entry pointing to `StringConcatFactory`.
3. `sum` in both builds still needs to compute `a + b` into an `int` value before concat; the instructions may show `iadd` followed by builder or indy.
4. `maybeNull` still must produce the string `item=null`; the details of calling `String.valueOf`/`StringBuilder.append` or the concat target are up to the compiler/runtime.
5. `folded` may only need `ldc "constant=A12"` and then `areturn` in both builds, due to constant folding.
6. The diff between the two outputs is not only due to program logic: there are also **constant pool indexes, `BootstrapMethods`, class-file version, line tables**, and compiler-specific decisions.

**Note on the command:** `--release` is an option of modern `javac`, not present in JDK 8 `javac`. When using an actual JDK 8, the compiler does not accept `--release 8`; you just compile normally or use the flags that compiler supports. A newer JDK may gradually drop support for very old targets, so check `javac --help` for the version in use.

### Comparing "same compiler, different --release" and "different compiler"

The two experiments answer two **different** questions:

- Keeping JDK 17 `javac` fixed and changing `--release 8` to `--release 17`: investigates **code generation rules by target platform** supported by that compiler.
- Keeping `--release 17` and replacing JDK 17 `javac` with a newer `javac` version: investigates **implementation/compiler evolution** for the same target platform.

`--release 17` **does not emulate byte-for-byte** the output of JDK 17 `javac` when run by another JDK; it mainly restricts the language, platform APIs, and class-file target. If a bytecode analysis tool needs the exact shape, lock and record the **compiler version/build** as well.

## 10. Deep dive: distinguishing `BootstrapMethods` of lambdas and string concatenation

Use:

```bash
javap -v -p LambdaTranslation
javap -v -p StringConcatTranslation
```

Look for entries in the constant pool:

```text
#N = InvokeDynamic    #bootstrapIndex:#nameAndTypeIndex
#X = MethodHandle     REF_invokeStatic ...
#Y = MethodType       ...
#Z = NameAndType      ...
```

This is a **schematic**, actual indices vary. In `BootstrapMethods` of `LambdaTranslation`:

- A bootstrap usually points to `LambdaMetafactory.metafactory`; arguments include the SAM method type, implementation method handle, and instantiated method type.
- A capture parameter **does not necessarily appear as a static bootstrap constant**; it can be a dynamic argument loaded onto the stack when `invokedynamic` is executed.
- For the method reference `LambdaTranslation::triple`, the implementation method handle usually points directly to `triple:(I)I`; for a lambda with the expression `x + offset`, it may point to a synthetic helper method.
- The same file may also have `StringConcatFactory` bootstraps for the printed result strings, which must be distinguished by the bootstrap owner.

In `StringConcatTranslation` compiled for target 17:

- The bootstrap of `message` is usually `StringConcatFactory.makeConcatWithConstants`, with a recipe having placeholders for `name` and `count`.
- The call-site type can have two dynamic parameters `(Ljava/lang/String;I)Ljava/lang/String;`.
- `folded` may have no dynamic call site at all because it is constant-folded.
- Not every String literal in the recipe is a `StringBuilder.append` call or a dynamic argument; the compiler can embed literals into the recipe.

### About when the bootstrap is invoked

Resolution/linkage of `invokedynamic` can be performed by the VM at a time conforming to the specification, usually when a call site is used for the first time. **Linking the call site** does not mean the bootstrap method must run **on every execution** of the instruction. After linkage, the target is established for the call site according to the appropriate rules.

If the bootstrap method fails, a linkage error such as `BootstrapMethodError` may appear. This is different from an exception thrown by the **lambda body** after the user calls the SAM, or an exception raised by `toString()` on a dynamic object during string concatenation.

## 11. Method references and target types determine adapters

Besides ordinary lambdas, a method reference is also a **poly expression**: its type depends on the **functional interface target** at the use site.

Example:

```java
import java.util.function.Function;
import java.util.function.Supplier;

Function<String, Integer> length = String::length;
Supplier<String> greeting = " hello "::trim;
```

This is an **illustrative fragment**, not a standalone program. With `String::length` here, the receiver is the **argument** of `Function.apply`. With `" hello "::trim`, the specific receiver is **captured when the method reference is evaluated**, and `Supplier.get()` later uses that receiver.

When a method reference has a SAM type like `Function<String,Integer>`, linkage may require boxing/unboxing or method-type adaptation between `String.length:()I` and the interface `Function.apply:(Ljava/lang/Object;)Ljava/lang/Object;`. `javap` may show bridge/adapter info through metafactory metadata; do not infer from generic types in source that bytecode has a single method descriptor matching the source verbatim.

A reading tip: identify the **erased SAM descriptor**, **implementation MethodHandle**, and **instantiated method type**. Those three pieces of information explain how the lambda object provides a method matching the interface.

## 12. A lambda object is not an anonymous inner class written in source

Two Java snippets can have the same intent:

```java
Runnable lambda = () -> System.out.println("run");

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
```

This is an **illustrative fragment**. When using typical OpenJDK `javac`:

- A lambda is usually lowered into an `invokedynamic` linked with `LambdaMetafactory`; the compiler may generate a helper method for the body.
- An anonymous class is a real **class declaration** in Java source, usually generating an additional class file such as `Outer$1.class`, with a constructor and a `run()` method.
- In a lambda, the `this` keyword follows lexical scope and refers to the **enclosing object** (if any); in an anonymous class, `this` refers to the **anonymous class instance**. This is a **semantic** difference, which cannot be decided solely from both implementing `Runnable`.
- A non-capturing lambda may have its object reused when evaluated multiple times; one should not impose allocation counts from a benchmark or heap dump onto the JLS contract.
- The compiler is allowed to choose other representations for lambdas as long as semantics are preserved; therefore, do not build tools on the assumption that there is always a class file with a name like `$$Lambda$...`.

The right way to compare bytecode is to observe **the method containing the expression**, **`BootstrapMethods`**, and **the generated class files** in the exact build being analyzed, rather than equating every function object with an anonymous class.

## 13. What belongs to JLS guarantees, and what is a compiler/runtime detail?

| Statement | Classification | How to rely on it |
| --- | --- | --- |
| Lambda must be compatible with functional-interface target type and effectively final rules | **JLS contract** | Can be used as rules for checking source validity |
| `applyAsInt(4)` must provide the correct result of the lambda implementation | **Language/API contract** | Can write tests for results and errors |
| `javac` generates a method named `lambda$main$0` | **Code generation detail** | Only rely on it when testing a locked compiler/build |
| Every evaluation of a lambda creates a new object | **Not guaranteed in general** | Do not depend on object identity |
| `invokedynamic` has constant pool and bootstrap method rules | **JVMS contract** | Use for checking class file validity |
| Java 8 `javac` uses a `StringBuilder.append` chain | **Compiler pattern by version** | Use for comparing class files of that compiler |
| Java 9+ `javac` uses `StringConcatFactory` per JEP 280 | **Common code generation choice** | Verify with `javap` on the actual build |
| A constant expression can be folded in advance by the compiler | **Java rule on constant expressions + codegen choice** | Do not count opcodes by the number of `+` operators |
| Which class caches/implements the bootstrap call site | **Runtime detail** | Do not treat as a stable API |
| String concat with `null` yields the literal `null` | **Java string conversion semantics** | Can write tests based on the result value |

A valid class file can run with the same result on multiple JVMs yet have different performance, object counts, or machine code. Conversely, two class files that differ completely in `StringBuilder`/`invokedynamic` can still both obey Java source semantics.

## 14. Practical bugs when upgrading JDKs and bytecode analysis tools

**1. Instrumentation looks for `StringBuilder.append` and then "loses track" of string concatenation.** When switching compiler target 8 → 17, concat can become `invokedynamic`. Bytecode analysis tools must support both patterns or track dynamic meaning via bootstrap, instead of assuming the number of `append` instructions stays unchanged.

**2. Tool only looks at the `invokedynamic` opcode without reading the bootstrap.** It can confuse a lambda factory with string concat; it must inspect `CONSTANT_InvokeDynamic_info`, `NameAndType`, `BootstrapMethods`, and owners like `LambdaMetafactory` or `StringConcatFactory`.

**3. Newer compiler generates a class-file version not supported by an older runtime.** For example, Java 17 class-file major 61 does not run directly on a Java 8 JVM; `UnsupportedClassVersionError` is a runtime/classfile version issue, not a "broken lambda".

**4. Trying to run a class referencing `StringConcatFactory` on Java 8.** This API only exists since Java 9; a class file or tool-generated code referencing it cannot expect linkage on a Java 8 runtime. Use the right target and run tests on a supported runtime.

**5. Using `-source 8 -target 8` and thinking the API is already restricted.** When building with a newer `javac`, these two flags do not completely replace `--release 8` for platform API checking. Where supported, `--release` is more appropriate for cross-compilation.

**6. Believing Java 17 source must always contain `StringConcatFactory` in the class file.** If the concat expression is a constant expression, the compiler can fold it; if the code explicitly writes `new StringBuilder()`, the compiler is not forced to replace that source with concat indy.

**7. Seeing a `lambda$...` method and calling it directly from another library.** It is a compiler detail (usually private/synthetic), not a stable public API; names/signatures can change upon recompilation.

**8. Catching errors from running code and confusing them with `BootstrapMethodError`.** If a lambda body throws `IllegalArgumentException` after calling the SAM, that is not by default a bootstrap error; distinguish **call-site linkage** from **target execution**.

**9. Inferring the number of lambda objects from the number of indy instructions.** A call site can be executed multiple times and the runtime has the right to reuse instances in appropriate cases; allocation/lifetime cannot be inferred directly from instruction count.

**10. Reading `javap` while ignoring compiler flags.** Compiler options, debug info, optimization, vendor, and target release can change bytecode offsets, synthetic members, constant-pool indices, or bootstrap entries. Save toolchain information along with the analyzed artifact.

## 15. Procedure for inspecting a class file with lambdas and string concat

1. **Record the environment:** `javac -version`, `java -version`, `--release`, build version, `gradle/maven` toolchain, and executed JAR.
2. **Confirm class major:** `javap -v ClassName`; for example Java 8 → 52, Java 17 → 61.
3. **Find call sites:** `javap -c -v -p ClassName`; filter each `invokedynamic` by the **method containing the instruction**.
4. **Look up the constant pool:** at index `#N`, check the `InvokeDynamic` type and `NameAndType` descriptor.
5. **Trace to `BootstrapMethods`:** record the bootstrap owner/method, method types, implementation handles, recipes, constants.
6. **For lambdas:** inspect capture arguments before `invokedynamic`; inspect the helper body or method reference target; find `invokeinterface` where the SAM is called.
7. **For string concat:** find dynamic components pushed onto the stack, U+0001/U+0002 recipe or builder chain, check constant folding and evaluation order.
8. **Compare two builds:** ensure using the right class file after each compilation, not mistakenly looking at cached build output; diff disassembly by meaning rather than only by `#index`.
9. **Run behavioral tests:** results, exceptions, and side effects per JLS/API matter more than bytecode looking as expected.
10. **Cross-check the right version specification:** only elevate a behavior from "compiler observation" to a general rule if it is actually guaranteed by JLS/JVMS/API.

### Self-check question checklist

- Does `invokedynamic` at the lambda site create a **function object** or perform a **string concatenation**?
- Does the method reference capture a receiver? Does the lambda capture effectively final variables?
- Which SAM type, implementation handle, and instantiated type does `LambdaMetafactory` receive?
- Which call-site argument types, recipe, and static constants does `StringConcatFactory` receive?
- Can the string concatenation expression be constant-folded? Do parentheses change arithmetic addition into early string concatenation?
- Is the target Java 8 or Java 17? Does `--release` restrict APIs/classfile appropriately?
- Is the bytecode snippet I extracted mandatory by JVMS or a choice of the compiler used at build time?
- Do bytecode tools/agents understand `BootstrapMethods`, `invokedynamic`, and the class-file major version?

## References

- [JLS Java SE 17 `15.27` — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): target typing, lambda semantics, capture.
- [JLS Java SE 17 `15.13` — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): bound/unbound method references and runtime evaluation.
- [JLS Java SE 17 `15.18.1` — String Concatenation Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1): string conversion and `+` operator semantics.
- [JVMS Java SE 17 `4.4.10` — `CONSTANT_Dynamic_info` and `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10): constant pool structure for dynamic call sites.
- [JVMS Java SE 17 `4.7.23` — `BootstrapMethods` attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23): bootstrap method handles and static arguments.
- [JVMS Java SE 17 `5.4.3.6` — Dynamically-Computed Call Site and Constant Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): bootstrap linkage.
- [JVMS Java SE 17 `6.5` — `invokedynamic` instruction](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic): operand stack and instruction semantics.
- [`LambdaMetafactory` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): metafactory and altMetafactory for lambdas/method references.
- [`StringConcatFactory` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html): makeConcat, makeConcatWithConstants, and U+0001/U+0002 recipes.
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280): rationale for switching bytecode generation strategy to invokedynamic since Java 9.
- [`javac` and `javap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) / [`javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `--release` and how to inspect class files.

**Takeaway:** Lambdas in modern `javac` usually create a **function object via `invokedynamic + LambdaMetafactory`**, and then the caller invokes the SAM; String `+` on Java 9+ targets usually computes the **resulting String via `invokedynamic + StringConcatFactory`**, instead of the typical builder chain on Java 8 targets. **The bootstrap method and descriptor tell you what the call site does; the compiler/version tells you why a source produces that bytecode shape.**
