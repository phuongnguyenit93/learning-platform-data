# Observing lambdas and method references in Java bytecode

## 1. Observation goal: what is the concise syntax compiled into?

Lambdas and method references are two ways to create values of a **functional interface** (an interface with exactly one abstract method according to functional interface rules). For example, both `x -> x + 1` and `SomeType::someMethod` can provide an implementation for a Single Abstract Method (SAM) target. However, source code looking like an anonymous class does not mean `javac` always generates a `SomeClass$1.class` file for each lambda.

With modern `javac` on Java 17+, the common compilation approach is:

1. The compiler determines the *target type* of the lambda/method reference and the SAM signature.
2. It emits an **`invokedynamic` call site** to create/obtain an instance of the functional interface when the expression is evaluated.
3. The call site references a **bootstrap method** in `java.lang.invoke.LambdaMetafactory` (usually `metafactory`, in some cases `altMetafactory`) via the class file's `BootstrapMethods` attribute.
4. For a lambda with an expression/statement body, `javac` typically generates an implementation method of the form `lambda$...` inside the enclosing class. For a method reference, the bootstrap can point directly to the referenced method/constructor, so a `lambda$...` method is not necessarily present.
5. At runtime, the JVM links `invokedynamic` to the appropriate factory/implementation. How the lambda object is realized is a runtime detail and may vary across JDK versions.

**Two moments must be kept distinct:** the lambda/method reference expression is evaluated to create the **functional object**; calling `apply`, `get`, `run`, or the corresponding SAM on that object is what executes the behavior. The `invokedynamic` instruction creating the lambda does not mean automatically running the lambda body.

The learning goal is to read the structure **source → class file → bootstrap linkage → SAM invocation**, rather than memorizing constant pool indices that can change.

## 2. Functional interfaces and target typing

A lambda/method reference needs a **target functional interface** so the compiler knows the parameter types, return type, and expected behavior. They typically appear in assignments, method arguments, return expressions, or casts with an appropriate target type.

~~~java
// Standalone expression-level illustrative examples, not a runnable file.
java.util.function.IntUnaryOperator f = x -> x + 1;
java.util.function.Function<String, String> trim = String::trim;
java.util.function.Supplier<StringBuilder> make = StringBuilder::new;
~~~

Here:

- `IntUnaryOperator` has SAM `int applyAsInt(int operand)`. The lambda `x -> x + 1` takes `int` and returns `int`, avoiding boxing.
- `Function<String,String>` has SAM `R apply(T t)`. With `String::trim`, the `String` argument becomes the *receiver* of the instance method `trim()`.
- `Supplier<StringBuilder>` has SAM `StringBuilder get()`. The constructor reference `StringBuilder::new` creates the object when `get()` is called, not at the time the reference is assigned.

For example, `x -> x + 1` is not a standalone declared Java method with a fixed "lambda type"; the type of the expression is determined from context. The same lambda form can be compatible with multiple different functional interfaces. Method references also require checking compatible signatures, overload resolution, and access control before they can compile.

A functional interface can have multiple default/static methods, as long as it has exactly one relevant abstract method according to SAM rules. Public methods from `Object` do not by themselves make an interface non-functional.

## 3. Complete Java 17+ program for practice

Create the file `src/lesson/LambdaBytecodeDemo.java` with the following contents:

~~~java
package lesson;

import java.util.Locale;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;

public final class LambdaBytecodeDemo {
    private final String prefix;

    public LambdaBytecodeDemo(String prefix) {
        this.prefix = prefix;
    }

    private String decorate(String text) {
        return prefix + text;
    }

    public static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        int offset = 3;

        IntUnaryOperator capturedLambda = x -> x + offset;
        Function<String, String> staticReference = LambdaBytecodeDemo::upper;
        Function<String, String> unboundReference = String::trim;

        LambdaBytecodeDemo demo = new LambdaBytecodeDemo(">");
        Function<String, String> boundReference = demo::decorate;
        Supplier<StringBuilder> constructorReference = StringBuilder::new;

        System.out.println(capturedLambda.applyAsInt(7));
        System.out.println(staticReference.apply("java"));
        System.out.println("[" + unboundReference.apply("  hi  ") + "]");
        System.out.println(boundReference.apply("ok"));
        System.out.println(constructorReference.get().length());
    }
}
~~~

The expressions are chosen to compare **five cases**:

| Expression | Kind | SAM | Data bound when creating the object |
| --- | --- | --- | --- |
| `x -> x + offset` | Lambda capturing local variable | `IntUnaryOperator.applyAsInt(int)` | Value of `offset` |
| `LambdaBytecodeDemo::upper` | Static method reference | `Function.apply(Object)` after type erasure | No receiver |
| `String::trim` | Unbound instance method reference | `Function.apply(Object)` | Receiver is the SAM parameter at call time |
| `demo::decorate` | Bound instance method reference | `Function.apply(Object)` | Object `demo` is evaluated and held as receiver |
| `StringBuilder::new` | Constructor reference | `Supplier.get()` | Does not create `StringBuilder` before calling `get()` |

Compile and run from the directory containing `src/` using JDK 17 or later:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -g -d out src/lesson/LambdaBytecodeDemo.java
java -cp out lesson.LambdaBytecodeDemo
~~~

Full stdout:

~~~text
10
JAVA
[hi]
>ok
0
~~~

`--release 17` forces the compiler to adhere to Java 17 for language rules, class file target, and available Java SE APIs. It does not mean every build of every `javac` version will have identical constant pool numbering, bytecode offsets, or identical bytecode implementations. `-g` adds debug information to help read line/variable info when supported by tools, without determining the lambda mechanism.

On Windows PowerShell, if Bash is unavailable, create the output folder using `New-Item -ItemType Directory -Force out`; the remaining `javac` and `java` commands stay the same because the classpath has only one directory.

## 4. Reading bytecode with javap

After compiling:

~~~bash
javap -classpath out -c -p lesson.LambdaBytecodeDemo
javap -classpath out -c -p -v lesson.LambdaBytecodeDemo
~~~

Role of the options:

- `-classpath out`: locate compiled classes, not source files.
- `-c`: display instructions and bytecode of methods.
- `-p`: display private methods as well. Necessary because the compiler may generate `private static synthetic lambda$main$0(...)`.
- `-v`: display detailed class file information, including the constant pool, attributes, `BootstrapMethods`, `InnerClasses`, and MethodHandle/MethodType when present.

Start reading at the `main` method, then search for keywords:

~~~text
invokedynamic
BootstrapMethods
LambdaMetafactory
lambda$main$
MethodHandle
MethodType
~~~

The keywords above are **search markers**, not a complete dump. A class may contain `invokedynamic` from other Java features. In this very example, string concatenation `"[" + ... + "]"` or `prefix + text` may also be compiled using the `StringConcatFactory.makeConcatWithConstants` bootstrap. Therefore, **do not count all `invokedynamic` instructions and conclude the number of lambdas**; inspect the bootstrap of each call site.

### 4.1. How to interpret a snippet of main bytecode

An **illustrative snippet omitting constant-pool indices, offsets, and auxiliary code** has the form:

~~~text
iload ...                             // Push captured offset onto the stack
invokedynamic ... applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
astore ...                            // Store the functional object

...                                   // Other reference expressions
invokedynamic ... apply:()Ljava/util/function/Function;
invokedynamic ... apply:()Ljava/util/function/Function;

aload ...                             // Push receiver demo onto the stack
invokedynamic ... apply:(Llesson/LambdaBytecodeDemo;)Ljava/util/function/Function;

invokedynamic ... get:()Ljava/util/function/Supplier;
~~~

This is a **signature diagram**, not literal `javap` output. The compiler may insert instructions for bound receiver null checks, casts, local variables, object creation, and string concatenation handling. Constant pool ordering/indices depend on the JDK.

Key meanings:

- The parenthesized part of the descriptor `(I)Ljava/util/function/IntUnaryOperator;` is the **parameter captured when creating the functional object**: an `int` (offset). It is **not** the full parameter list of the SAM.
- The descriptor `()Ljava/util/function/Function;` has no captured arguments in the static and unbound method references of the example.
- The descriptor `(Llesson/LambdaBytecodeDemo;)Ljava/util/function/Function;` represents the bound receiver passed to the factory creating the functional object.
- The instructions `invokeinterface Function.apply`, `invokeinterface IntUnaryOperator.applyAsInt`, and `invokeinterface Supplier.get` appear at the **point where the behavior is actually invoked** through the SAM.

Distinguish `invokedynamic` when creating the functional interface object from `invokeinterface` when program code invokes the SAM. The implementation linked by the JVM for the call site determines how the final call occurs; do not infer from the name `apply` that Java is directly invoking method `upper` inside the `invokedynamic` instruction itself.

## 5. BootstrapMethods and LambdaMetafactory

In a class file with `invokedynamic`, the constant pool contains entries such as `CONSTANT_InvokeDynamic`, `CONSTANT_MethodHandle`, and `CONSTANT_MethodType`; the `BootstrapMethods` attribute stores the bootstrap method and static arguments. Each `invokedynamic` instruction can reference a bootstrap entry with the same or a different name.

For typical lambdas/method references, the bootstrap is usually:

~~~text
java/lang/invoke/LambdaMetafactory.metafactory
~~~

Conceptually, the bootstrap typically combines three foundational pieces of information:

1. **SAM method type**: the erased type of the functional interface method that the object will implement, e.g. `(Ljava/lang/Object;)Ljava/lang/Object;` for `Function.apply`.
2. **Implementation method handle**: the actual method that will execute, e.g. a compiler-generated helper or `LambdaBytecodeDemo.upper`, `String.trim`, `LambdaBytecodeDemo.decorate`, or constructor `StringBuilder.<init>`.
3. **Instantiated method type**: the target signature after type inference/concrete instantiation, e.g. `(Ljava/lang/String;)Ljava/lang/String;` for `Function<String,String>`.

The bootstrap may add bridge methods/flags or handle serializable/marker interfaces via `altMetafactory`. One should not claim every lambda on every compiler uses the exact same `metafactory` form or has the exact same static arguments list.

**Three type layers easily confused:**

~~~text
invokedynamic factory descriptor    : captured parameters → functional-interface instance
SAM signature (erased)               : Object → Object, e.g. Function.apply
Instantiated SAM signature           : String → String, after type inference
Implementation method                : linked static/instance/constructor/helper
~~~

For example, `Function<String,String> f = String::trim` has erased SAM `Object apply(Object)`, whereas the implementation handle is `String.trim():String`. The runtime may need casts/adapters to match the two signatures. There is not necessarily a Java bridge method visible in source.

### 5.1. Why is the helper often named lambda$...?

For the lambda `x -> x + offset`, the compiler needs to represent the addition body as an executable method. Typically `javap -p -c` can show a **private static synthetic** method named like `lambda$main$0` with equivalent logic:

~~~text
iload_0           // captured int offset
iload_1           // int x from SAM
iadd              // offset + x
ireturn
~~~

This snippet is **only a logic illustration**, without guaranteeing exact opcode offsets, local slot layout, or method name across all `javac` versions. The compiler may order parameters according to its own design and optimize code differently. The takeaway is that a handle in the bootstrap points to the lambda's implementation logic.

**Do not call `lambda$main$0` directly from Java code.** It is an implementation detail whose name can change; accessibility at the bytecode level can be handled by the JVM through the lookup provided by the bootstrap.

Method reference `LambdaBytecodeDemo::upper` can usually link directly to the `upper` method (static), `String::trim` to the instance method, and `StringBuilder::new` to the constructor. **Do not force finding a `lambda$...` helper for every reference.** The compiler may still generate an adapter in some cases (signature conversion, varargs, access, or corner cases), so conclusions must be based on the actual dump.

## 6. Both are instance method references, yet bound and unbound differ

The two expressions:

~~~java
Function<String, String> unbound = String::trim;
Function<String, String> bound = demo::decorate;
~~~

both provide an instance method but determine the receiver very differently.

**Unbound `String::trim`:** there is no specific `String` object when creating the functional object. When running `unbound.apply(" hi ")`, the `" hi "` argument itself is the receiver, equivalent to `" hi ".trim()`.

**Bound `demo::decorate`:** the expression `demo` is evaluated **once at the time the method reference is created**. The reference holds that receiver; when running `bound.apply("ok")`, it uses the bound receiver, equivalent to `demo.decorate("ok")`. If the receiver is null, a bound instance method reference can throw `NullPointerException` **when the method reference is created**, before `apply` is called.

This explains why the factory descriptor of a bound reference has a captured receiver parameter, while the unbound reference in the example typically needs no captured receiver. `Object::toString` taking its receiver from its SAM parameter is a similar unbound example when the target type fits.

### 6.1. Captured local variables and effectively final

In the example, `offset` has value `3` and is not reassigned; it is *effectively final*. Java requires local variables captured by a lambda (or anonymous/local inner class under related rules) to be final or effectively final.

The following snippet is intentionally invalid:

~~~java
// Not a standalone program; if inside the same method:
int offset = 3;
IntUnaryOperator add = x -> x + offset;
offset = 4;  // Compile error: offset is no longer effectively final.
~~~

If state needs to change over time, design an intentional state object or manage external state properly. Do not arbitrarily use a single-element array or static variable just to bypass a compile error while hiding concurrency issues.

**Capturing a local value does not mean "keeping a local variable alive on the stack" after the method ends.** For a primitive like `int offset`, the value at lambda creation time can be passed as a captured argument. For a captured object reference, the reference value is retained; the internal state of the object can still change if the object is mutable. Similarly, a bound method reference retains the receiver object evaluated at reference creation time.

## 7. Static references, constructor references, and equivalent rewritten lambdas

Compare the forms below in terms of behavior within an appropriate context:

| Form | Equivalent lambda syntax | Bytecode trait to look for |
| --- | --- | --- |
| `LambdaBytecodeDemo::upper` | `s -> LambdaBytecodeDemo.upper(s)` | Implementation method handle usually points directly to the static method |
| `String::trim` | `s -> s.trim()` | Handle to the instance method; receiver comes from the SAM parameter |
| `demo::decorate` | `s -> demo.decorate(s)` | Receiver `demo` is captured |
| `StringBuilder::new` | `() -> new StringBuilder()` | Handle to the constructor |
| `x -> x + offset` | Keeps lambda body as is | Has compiler-generated logic to add the two values |

These are examples **equivalent in result within the example context**, not a guarantee of identical bytecode or identical evaluation timing in every expression. In particular, a bound method reference evaluates the receiver immediately upon creation; a lambda `s -> demo.decorate(s)` may only dereference the receiver when the lambda is called. When the receiver is null or the expression producing the receiver has side effects, the two forms can differ in when errors or side effects occur.

The constructor reference `StringBuilder::new` does not instantiate an object on the `Supplier` assignment line. It provides instantiation logic, triggered when `get()` is called. In the class file, the implementation handle for the constructor may be a method handle of kind `REF_newInvokeSpecial`, instead of an `invokestatic` like a static method reference.

## 8. Why don't we see a new .class file for each lambda?

Before Java 8, an anonymous inner class typically resulted in a separate class file such as `Outer$1.class`. For comparison, create a **standalone** file `src/lesson/AnonymousContrast.java`:

~~~java
package lesson;

public final class AnonymousContrast {
    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };

        Runnable lambda = () -> System.out.println("lambda");

        anonymous.run();
        lambda.run();
    }
}
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/lesson/AnonymousContrast.java
java -cp out lesson.AnonymousContrast
~~~

Stdout:

~~~text
anonymous
lambda
~~~

With standard `javac`, an anonymous class is represented by a separate class file (e.g. `AnonymousContrast$1.class`). A lambda uses `invokedynamic` and bootstrap linkage; at compile time there does not have to be a class file on disk corresponding to the lambda name. When observing at runtime, the JVM may dynamically generate an implementation class. On HotSpot in modern Java releases, the lambda implementation may use **hidden classes**; that is a runtime detail, and one should not infer that `javac` always generates a public or stable class file per lambda.

Do not depend on `lambda.getClass().getName()`, the object class name, the number of generated classes, singleton caching for non-capturing lambdas, or identity of lambda objects to make language assumptions. Reliable rules lie in **functional interfaces**, capture, expression evaluation, and SAM behavior. The runtime reserves the right to change implementation strategies.

### 8.1. Differences in this and shadowing

In a lambda, `this` and `super` retain their meaning from the **enclosing context**; a lambda does not introduce a new lexical `this` like an anonymous inner class. In an anonymous class, `this` points to the anonymous class object. This explains several differences when converting an anonymous class to a lambda even though both implement `Runnable`.

The lambda mechanism can also restrict local variable shadowing compared to other class scopes; code must obey Java scoping rules. Do not automatically convert an anonymous class to a lambda based solely on having the same SAM signature if the implementation depends on `this` identity or member accessibility.

## 9. invokedynamic in Java is not only for lambdas

Since Java 9, `javac` commonly uses `invokedynamic` for **string concatenation**, such as `"[" + s + "]"`, with the bootstrap `java.lang.invoke.StringConcatFactory.makeConcatWithConstants`. Java also has other features using bootstraps (for example dynamic constants via `ConstantDynamic`, depending on context).

Therefore, when reading `javap -v` output:

1. Find `invokedynamic` in the method being analyzed.
2. Locate the corresponding `BootstrapMethods` entry via the bootstrap index (do not use "the nearest-looking line number").
3. Identify whether the bootstrap is `LambdaMetafactory` or `StringConcatFactory`.
4. Read the descriptor of the factory call site and the method handle arguments.
5. Cross-check with `invokeinterface` where the SAM is invoked and with compiler-generated `lambda$...` methods.

You can use shell filtering commands depending on your environment, but **do not only grep `invokedynamic` and miss `BootstrapMethods`**. Read both sections completely or note the linking indices between them; auto-numbered constant pool entries can differ across JDK versions.

## 10. Erasure, adapters, and bridge methods in bytecode

`Function<String,String>` is generic at the source level, but the class file invocation of `Function.apply` essentially uses the erased descriptor:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Therefore, code calling `Function.apply` may have `checkcast java/lang/String` afterward. The lambda's bootstrap may specify the instantiated signature `(Ljava/lang/String;)Ljava/lang/String;`, while the implementation method handle has the concrete signature `String -> String`.

Markers to recognize:

- **Erased SAM signature** belongs to the JVM-level method descriptor of the interface.
- **Instantiated method type** describes how the target functional interface is specialized in the current conversion.
- **Bridge/adaptation** makes signatures match according to linkage rules; do not assume every call must have a separately visible `lambda$...` adapter method.
- For primitive-specialized functional interfaces such as `IntUnaryOperator`, the SAM `applyAsInt(int)` uses the primitive descriptor `(I)I`, avoiding the boxing/unboxing that `Function<Integer,Integer>` can incur.
- Overload resolution and generic type inference are compile-time work; the JVM does not retain full generic type arguments as new runtime types for each instantiation.

The validity of a method reference also depends on accessibility and type compatibility: for example, a private method can only be referenced from code with appropriate access rights; a target SAM with the wrong parameter count/types will be rejected by `javac` before the JVM ever runs `invokedynamic`.

## 11. Performance differences between capture and SAM invocation

When observing bytecode, one should not draw rigid conclusions such as "every loop iteration creates exactly one object," "method references are faster than lambdas," or "invokedynamic is slower than regular calls."

- A **non-capturing** lambda or method reference may have its instance reused by the runtime, but programs must not rely on object identity or a specific caching mechanism.
- A **capturing** lambda must carry captured data semantically; the actual number of allocated objects also depends on the runtime, JIT escape analysis, and other optimizations.
- `invokedynamic` initially performs linkage work; afterward the call site can be optimized/inlined by the JIT. Execution cost cannot be inferred merely from the presence of the instruction.
- String concatenation, boxing, allocations inside the lambda body, or I/O operations can dominate runtime cost far more than the difference between the two syntaxes.
- Benchmarks intended for comparison must use an appropriate tool like JMH, include warm-up, avoid dead-code elimination, and specify JDK/VM/flags. A few calls to `System.nanoTime` are not enough to draw conclusions.

Use `javap` to **explain mechanisms**, and a profiler or proper microbenchmark to **measure performance**. The two activities answer two different questions.

## 12. Common mistakes when analyzing lambda bytecode

| Claim/symptom | Why wrong or insufficient | Proper way to verify |
| --- | --- | --- |
| "A lambda is always a `$1.class` class file." | Confuses lambdas with anonymous classes; lambdas usually link via `invokedynamic` | Compare `javap -c -p -v` and the list of class files |
| "Every `invokedynamic` is a lambda." | String concatenation can also use `invokedynamic` | Look up the `BootstrapMethods` entry for the call site |
| "Seeing `invokedynamic` means the lambda body executes immediately." | The factory creates the object; behavior runs when the SAM is called | Find `invokeinterface apply/get/run` |
| "Every method reference generates a `lambda$...` method." | Can use a direct method handle; adapter only when needed | Read the implementation handle in the bootstrap |
| "String::trim and demo::decorate capture the same way." | Unbound gets the receiver from the SAM argument; bound captures the receiver upon creation | Compare factory descriptors with/without a receiver |
| "A lambda-captured local variable can be mutated freely." | Local variables must be final/effectively final | Check assignments after capture time |
| "The runtime class name/address of a lambda is a stable API." | Runtime may use hidden classes, caching, or change implementation | Rely on the SAM and Java semantics |
| "With `--release 17`, `javap` output is identical on every JDK." | Toolchain/version can change constant pool numbering/implementation details | Compare bootstrap semantics, descriptors, and captures |
| "Method references always avoid allocation." | Object/capture allocation may still occur; JVM optimizes situationally | Measure with a benchmark/profiler |
| "Function<String,String> has a direct String → String SAM descriptor." | Erasure produces `apply(Object)` at the JVM level | Read both erased and instantiated method types |

## 13. Workflow for analyzing a new lambda yourself

For an expression `target = expression`, proceed in order:

1. **Identify the target functional interface** and its SAM signature at the source level, e.g. `Function<String,String>`.
2. **Classify the expression**: is it a lambda with a body or a method reference; if a reference, is it static, bound instance, unbound instance, array constructor, or class constructor?
3. **List captured variables/receiver** at expression creation time. Captured locals must be effectively final; a bound receiver is evaluated immediately.
4. **Compile a small standalone program**, using `javac --release 17 -g -d out ...`, then check stdout to confirm semantics.
5. **Read the bytecode** with `javap -classpath out -c -p -v ...`. Find the `invokedynamic` entry creating the functional interface and `invokeinterface` at the SAM call site.
6. **Read BootstrapMethods**, locating `LambdaMetafactory`, SAM type, implementation handle, and instantiated method type; explain captured arguments via the factory descriptor.
7. **Inspect `lambda$...` helper methods** if present, comparing logic with source. If absent, check which method/constructor the handle points to directly.
8. **Separate JDK/VM specifics** (constant pool indices, helper names, runtime hidden classes, optimizations) from the language contract (target typing, capture, behavior).

### Extended practice exercises

Starting from `LambdaBytecodeDemo`, change only **one** expression at a time, then recompile and re-inspect:

- Change `x -> x + offset` to `x -> x * 2`. Compare the factory descriptor when the lambda captures nothing; predict stdout of `applyAsInt(7)` is `14`.
- Change the static method reference to lambda `s -> LambdaBytecodeDemo.upper(s)`. Observe that the implementation handle may shift from a direct static method to a `lambda$...` helper in the specific dump.
- Keep `demo::decorate` and try `Function<String,String> f = ((LambdaBytecodeDemo) null)::decorate;` in a separate test file: observe the moment `NullPointerException` occurs when evaluating the bound receiver.
- Change `String::trim` to `String::strip` with JDK 17+; explain the difference in Unicode whitespace handling and identify `REF_invokeVirtual` or its equivalent in the bootstrap.
- Run again on another JDK version if available. Compare **bootstrap name, method types, and behavior**; do not expect identical constant pool index numbers or implementation classes.

The most important knowledge is connecting the four layers: **Java expression with target type → `invokedynamic` factory in bytecode → `LambdaMetafactory` with implementation method handle → execution via SAM at runtime**. Understanding these four layers helps you accurately read lambdas, method references, and the difference between concise source code and the code the JVM actually executes.