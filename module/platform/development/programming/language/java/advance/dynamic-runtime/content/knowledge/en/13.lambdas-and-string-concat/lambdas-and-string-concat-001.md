# 13.1 From lambda or method reference to an object implementing a functional interface

When writing Java:

~~~java
Runnable task = () -> System.out.println("Hello");
~~~

the expression `() -> ...` **is not a standalone method**; it is converted into a **reference value to an object implementing a functional interface**. When `task.run()` is called, this object executes the behavior represented by the lambda. Similarly, a *method reference* such as `String::trim` can be converted into an object compatible with `Function<String,String>`.

Three layers must be distinguished:

1. **Java language layer:** the compiler checks that the **target type** is a functional interface, infers the *single abstract method* (SAM) signature, and ensures the lambda/method reference body is compatible.
2. **Value-creation layer:** at runtime, evaluating a lambda/method reference yields a **reference to an instance implementing the functional interface**. The implementation is allowed to reuse instances; there is no guarantee that "each evaluation always `new`s an object".
3. **Typical JVM layer:** `javac` on Java 17 typically emits `invokedynamic` linked via `LambdaMetafactory` to create or obtain an object implementing the interface. Details about hidden classes, object caches, and specific bytecode are **implementation details**, not conditions for a lambda to be valid under the Java Language Specification.

The goal of this lesson is to trace the full path **expression → target type/SAM → linkage and factory → interface object → SAM invocation**, including non-capturing lambdas, capturing lambdas, static/bound/unbound/constructor method references, and misconceptions about identity, invocation timing, and string concatenation.

## 1. What is a functional interface?

A functional interface is an interface that has **exactly one abstract method that needs to be implemented** after applying Java's rules (ignoring methods corresponding to `public` methods of `Object` when determining the SAM). It can have `default` methods, `static` methods, and compatible inheritance; the key point remains a single valid functional contract.

~~~java
@FunctionalInterface
interface TextTransform {
    String apply(String input);

    default String describe() {
        return "text transformation";
    }

    static TextTransform identity() {
        return s -> s;
    }
}
~~~

This is an **illustrative interface declaration** and needs to be placed in a valid Java file or inside an appropriate class. `@FunctionalInterface` is not semantically required, but it helps the compiler report an error if we accidentally make the interface lose its "functional" nature (for example, adding an independent abstract method).

Here the SAM is `String apply(String input)`; `describe()` and `identity()` do not add another abstract method to implement. Therefore we can create a value:

~~~java
TextTransform t = s -> s.strip();
String output = t.apply("  Ada  "); // "Ada"
~~~

Important point: the lambda expression is **target-typed** by `TextTransform`. There is no independent "lambda type" for the compiler to identify on its own and then arbitrarily assign to any interface; whether a lambda is valid depends on the target interface and the context.

Some standard interfaces:

| Interface | SAM | Example using lambda or method reference |
| --- | --- | --- |
| `Runnable` | `void run()` | `() -> doWork()` |
| `Supplier<T>` | `T get()` | `() -> create()` or `Type::new` when signature matches |
| `Consumer<T>` | `void accept(T)` | `System.out::println` |
| `Function<T,R>` | `R apply(T)` | `String::trim` |
| `Predicate<T>` | `boolean test(T)` | `s -> s.isEmpty()` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | `Type::instanceMethod` when receiver is in the first parameter |
| `Comparator<T>` | `int compare(T,T)` | `(a,b) -> Integer.compare(a.length(),b.length())` |

In Java Generics, the SAM signature can also involve **type erasure**, boxing/unboxing, covariance, and bridge methods. Therefore a lambda object can implement a generic interface whose SAM's runtime descriptor has been erased to `Object`; the compiler/JVM provides the necessary adaptation according to the contract, not because every lambda itself has `Object apply(Object)` in source.

## 2. From target type to lambda expression

Consider:

~~~java
java.util.function.Function<String, Integer> length =
        text -> text.length();
~~~

The compiler knows the SAM `Function.apply(T)` with `T=String` and `R=Integer` in this context. Thus `text` is inferred as `String`; `text.length()` returns primitive `int`, which can be **boxed** into `Integer` to satisfy the functional interface's return type.

With another target type:

~~~java
java.util.function.ToIntFunction<String> lengthAsInt =
        text -> text.length();
~~~

The SAM is now `int applyAsInt(String)`. The lambda has similar logic, but a different target type and a return type of `int`. One cannot deduce that these two values necessarily have the same runtime class or the same adapter mechanism from the expression body alone.

**A lambda is a poly expression:** the compiler needs a target type from an assignment, method argument, return statement, cast, or appropriate context. For example:

~~~java
java.util.function.Function<String, String> clean =
        String::trim;
~~~

is valid; however, merely writing `var clean = String::trim;` is invalid because `var` in a local variable declaration does not provide a target type for a method reference. The same applies to lambdas: `var f = x -> x;` does not infer a unique interface on its own.

An explicit cast can provide the target type:

~~~java
var clean = (java.util.function.UnaryOperator<String>) String::trim;
~~~

When an overloaded method accepts multiple functional interfaces, overload resolution and lambda compatibility can become more complex. If the compiler reports an *ambiguous method call*, specify the type using an intermediate variable or cast to the desired functional interface.

### What does the SAM signature mean?

For `Function<String,String>`, we can understand it at the source level as `(String)String`. However, when inspecting the class file of `Function`, the original method has the erased signature `(Object)Object`. The runtime may need bridges or adaptation to connect these two views. What matters in a Java program is **the invocation type-checked against the target type and Java rules**, not assuming the implementation carries a method with one single fixed bytecode form.

## 3. Diagram from lambda/method reference to object

~~~text
Source code:
  Function<String,String> f = s -> "[" + s + "]";
              │
              ▼
Compiler (target typing + SAM analysis)
  SAM abstract contract: Function.apply(T)
  instantiated input/output: (String)String
              │
              ▼
Javac/JVM Java 17 typically uses invokedynamic
  Bootstrap: LambdaMetafactory.metafactory
  Static bootstrap data: SAM method type,
                         implementation method handle,
                         instantiated method type
              │
              ▼
Runtime links factory call site
  CallSite target creates / provides Function instance
              │
              ▼
f ──> object implements Function
              │
              ▼
f.apply("Ada")  ──> runs lambda implementation ──> "[Ada]"
~~~

**Separating the two invocations:** the lambda expression is **evaluated to obtain an object** at the declaration/assignment site; afterward, `f.apply(...)` is a separate SAM invocation. Do not confuse *creating the object implementing the interface* with *running the lambda body*.

In the example `s -> "[" + s + "]"`, when assigning `f`, the body **has not been executed yet** for `"Ada"`. The body only executes when `f.apply("Ada")` is called. Even if the compiler/JVM optimizes instance creation, Java semantics must still be preserved.

If the body contains string concatenation with `+`, Java 17 `javac` can also use **another `invokedynamic`** linked via `StringConcatFactory` inside the code executing the lambda. **`LambdaMetafactory` creates interface behavior; `StringConcatFactory` handles string concatenation**. Having the same opcode name does not mean the two operations are one call site.

## 4. Role of LambdaMetafactory

`java.lang.invoke.LambdaMetafactory` is the JVM library mechanism that supports linking call sites for lambda expressions and method references. A bootstrap typically receives:

~~~java
LambdaMetafactory.metafactory(
        lookup,
        invokedName,
        invokedType,
        samMethodType,
        implMethod,
        instantiatedMethodType);
~~~

This is an **illustrative API call form**, not a standalone code snippet: the variables must have appropriate values and exceptions must be handled.

The six parameters come from two sources:

- `lookup: MethodHandles.Lookup`: the JVM provides the context and access privileges of the code containing the call site.
- `invokedName: String`: the name of the SAM that the object will implement, such as `"apply"` or `"run"`.
- `invokedType: MethodType`: the signature of the **factory** invoked by `invokedynamic`. The return type is the functional interface; the parameter types are the **captured arguments** that must be passed when creating the lambda value.
- `samMethodType: MethodType`: the signature of the functional method in the erased form of the SAM, e.g., `(Object)Object` for `Function`.
- `implMethod: MethodHandle`: handle to the actual implementation, which may be a static method, virtual method, constructor, or compiler-generated synthetic method.
- `instantiatedMethodType: MethodType`: the signature of the SAM after accounting for the generic target/concrete types, e.g., `(String)String`.

The first three parameters are supplied by the JVM during `invokedynamic` linkage; the last three are typical **bootstrap static arguments** in `BootstrapMethods`. The BSM returns a `CallSite`, with a target of type `invokedType` (the factory type). When the opcode executes, the factory returns an object compatible with the functional interface.

### Distinguishing three signatures that should not be conflated

Example of a lambda capturing `prefix`:

~~~java
String prefix = "Hi ";
java.util.function.Function<String, String> greet =
        name -> prefix + name;
~~~

Each signature in a common compilation strategy:

~~~text
Functional interface SAM after erasure:
  (Object)Object

Instantiated SAM:
  (String)String

Implementation method (conceptual):
  (String capturedPrefix, String name)String

invokedynamic factory type:
  (String capturedPrefix)Function

Call on resulting object:
  Function.apply(name) -> String according to the type used at source
~~~

`prefix` is a **runtime argument of the invokedynamic factory** when the lambda expression is evaluated; `name` is an **argument of the SAM invocation** after the object already exists. `prefix` does not become a static bootstrap argument just because it is later retained by the object.

The implementation method signature is not required to always have captured values first in exact source order; the compiler can generate a suitable adapter and `LambdaMetafactory` applies adaptation rules. The diagram is a **common mental model**, not a fixed template for every compiler-generated method shape.

## 5. Complete example 1: lambda and four forms of method reference

Create the file **LambdaToSamDemo.java**:

~~~java
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Function;

public class LambdaToSamDemo {
    @FunctionalInterface
    interface Converter {
        String convert(String text);
    }

    static class Prefixer {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String add(String text) {
            return prefix + text;
        }
    }

    static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Converter lambda = text -> "[" + text + "]";
        Converter staticMethod = LambdaToSamDemo::upper;

        String code = "ID:";
        Converter capturedLambda = text -> code + text;

        Prefixer hello = new Prefixer("Hello ");
        Converter boundReceiver = hello::add;

        BiFunction<Prefixer, String, String> unboundReceiver =
                Prefixer::add;
        Function<String, Prefixer> constructorReference =
                Prefixer::new;

        Prefixer made = constructorReference.apply("Dear ");

        System.out.println("lambda: " + lambda.convert("An"));
        System.out.println("static: " + staticMethod.convert("ha"));
        System.out.println("capture: " + capturedLambda.convert("42"));
        System.out.println("bound: " + boundReceiver.convert("Lan"));
        System.out.println("unbound: " +
                unboundReceiver.apply(made, "Minh"));
        System.out.println("constructor: " + made.add("Vy"));
        System.out.println("interface: " +
                (capturedLambda instanceof Converter));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac LambdaToSamDemo.java
java LambdaToSamDemo
~~~

Stdout:

~~~text
lambda: [An]
static: HA
capture: ID:42
bound: Hello Lan
unbound: Dear Minh
constructor: Dear Vy
interface: true
~~~

### Explanation of each expression

**`text -> "[" + text + "]"`:** the compiler checks that the target is `Converter`, SAM `String convert(String)`; the returned object implements the behavior of creating a bracketed string. The body runs when `convert("An")` is called, not at the assignment statement.

**`LambdaToSamDemo::upper`:** **static** method reference, pointing to an implementation method taking `String` and returning `String`. `Converter.convert` is compatible, so the caller calling `staticMethod.convert("ha")` receives `"HA"`.

**`text -> code + text`:** the lambda **captures** the reference value `code` from the enclosing scope. The local variable `code` is *effectively final*: it cannot be reassigned afterward if it is to be captured. After the lambda object is created, the captured value is used in subsequent `convert` calls.

**`hello::add`:** **bound receiver** method reference. The expression `hello` is evaluated when the method reference is created, and the receiver object is stored for use by subsequent `Converter.convert` calls. Therefore the SAM only has one parameter `text`, while the receiver is already fixed.

**`Prefixer::add`:** **unbound instance method** reference. It needs a receiver as the first argument of the functional interface. `BiFunction<Prefixer,String,String>` takes `(Prefixer receiver,String text)`; calling `apply(made,"Minh")` is equivalent in effect to `made.add("Minh")`.

**`Prefixer::new`:** constructor reference. `Function<String,Prefixer>` takes a `String` and returns a new `Prefixer` when `apply(...)` runs. **Evaluating the method reference does not invoke the constructor itself**; the SAM call `apply("Dear ")` is what creates the `Prefixer` instance.

**`instanceof Converter`:** the expression produces an object compatible with the functional interface. This does **not** prove it is an anonymous inner class or a class with a fixed name. The runtime representation can differ across JDKs, compilers, classloaders, and executions.

### Why do the target types differ?

A method reference has no independent "object shape" before receiving a target type:

| Expression | Target functional interface | What does the SAM take? | How the implementation is called |
| --- | --- | --- | --- |
| `LambdaToSamDemo::upper` | `Converter` | `String` | static `upper(String)` |
| `hello::add` | `Converter` | `String` | `hello.add(String)` |
| `Prefixer::add` | `BiFunction<Prefixer,String,String>` | `Prefixer, String` | `receiver.add(String)` |
| `Prefixer::new` | `Function<String,Prefixer>` | `String` | creates `new Prefixer(String)` |
| `text -> code + text` | `Converter` | `String` | synthetic/captured implementation |
| `text -> "[" + text + "]"` | `Converter` | `String` | lambda implementation body |

Note that **signature compatibility** is more important than the method name. One method reference can be used for multiple target types if overload/generic adaptation permits, though not every target is valid.

## 6. A method reference is an implementation choice; SAM remains the public call path

One can view a method reference as a way to select the implementation of a functional interface:

~~~text
Static reference:
  Type::staticMethod   => SAM(args) calls Type.staticMethod(args)

Bound instance reference:
  receiver::method     => SAM(args) calls receiver.method(args)

Unbound instance reference:
  Type::instanceMethod => SAM(receiver, args)
                             calls receiver.instanceMethod(args)

Constructor reference:
  Type::new            => SAM(args) creates new Type(args)
~~~

This is a semantic diagram, **not** a guarantee about the number of adapter methods or the shape of compiler-generated classes. In particular, an expression `Type::instanceMethod` can participate in complex overload resolution/generic inference; having the receiver at the first position is an important mental rule when the target signature fits.

### Easily confused example: String::length

~~~java
java.util.function.ToIntFunction<String> length =
        String::length;
int result = length.applyAsInt("Java"); // 4
~~~

`String::length` is an unbound instance method reference. The SAM takes a `String` as the receiver and returns `int`; no `String` object is bound at the time the method reference is created. The equivalent reading is `s -> s.length()`.

Conversely:

~~~java
String word = "Java";
java.util.function.IntSupplier boundLength = word::length;
int result = boundLength.getAsInt(); // 4
~~~

`word::length` has already bound the receiver `word`, so the SAM of `IntSupplier` needs no parameters. If one tries to assign `word::length` to `ToIntFunction<String>` in this situation, the signatures do not match because the target SAM expects a `String` whereas the method reference already has a bound receiver.

### Bound reference and null

For an expression `receiver::method`, Java requires evaluating the receiver expression at the time **the method reference is evaluated**; if the result is `null`, a `NullPointerException` is thrown right there, without waiting for the SAM invocation. With the `Type::instanceMethod` form, no receiver object is evaluated when creating the reference; if `null` is later passed as the receiver in the SAM invocation, a `NullPointerException` can be thrown at invocation time.

This is a difference in **when the error occurs** that is valuable when reviewing dynamic pipelines.

## 7. Capture: what is effectively final?

A lambda can use local variables from the enclosing scope if that variable is `final` or **effectively final** (after being assigned a value, it is not reassigned according to the compiler's checking rules).

~~~java
String prefix = "Hi ";
java.util.function.Function<String,String> fn =
        name -> prefix + name;
~~~

Valid because `prefix` is not reassigned. However, the following snippet **does not compile**:

~~~java
String prefix = "Hi ";
java.util.function.Function<String,String> fn =
        name -> prefix + name;
prefix = "Bye "; // error: prefix is no longer effectively final
~~~

This is an **intentional compile-error example**, not a runnable program. The reason is that a lambda captures **the value of the local variable** at the time the expression is evaluated; it does not guarantee reflecting later reassignments to the local variable. The effectively final rule makes semantics clear and avoids many bugs when code runs after the stack frame containing the local variable has ended.

### Capturing a reference does not mean freezing object state

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.function.IntSupplier size = names::size;
names.add("An");
int first = size.getAsInt(); // 1
names.add("Binh");
int second = size.getAsInt(); // 2
~~~

`names` (the receiver of the bound method reference `names::size`) is not reassigned. However, **the ArrayList object** still changes. When the SAM is called, the target reads the current state and thus returns different results.

Therefore:

- A **captured local variable** must not be reassigned if used in a lambda/method reference.
- The **referenced object** can be mutable; capturing does not create a deep snapshot.
- **Thread safety** does not appear automatically just because a lambda is used. If a mutable receiver is shared across multiple threads, synchronization or appropriate data structures are needed.
- A lambda object storing a captured reference can extend the lifetime of the captured object; long-lived callback caches need to consider memory retention.

### Cases that do not capture a local variable

A lambda can access a field of its enclosing object via `this`, or a static field, without capturing a local variable like in the `prefix` example. Inside a lambda, `this` is the `this` of the enclosing lexical context, **unlike** an anonymous class, where `this` inside the anonymous class body is that anonymous class instance itself.

A lambda that does not use variables from the enclosing scope is logically **non-capturing**, though the implementation may have various ways to create or reuse the corresponding object.

## 8. Object creation time, body execution time, and identity

Consider:

~~~java
java.util.function.Supplier<String> supplier =
        () -> "ready";
~~~

The assignment statement evaluates the lambda and obtains a `Supplier<String>` object. **No `"ready"` needs to be returned at lambda creation time**; `supplier.get()` is what evaluates the body to return the string.

The question "does every lambda creation `new` an object?" has no always-true answer. Java allows the implementation to **reuse** compatible lambda objects (especially for non-capturing lambdas), but it can also create different instances. Therefore:

~~~java
java.util.function.Supplier<Integer> a = () -> 42;
java.util.function.Supplier<Integer> b = () -> 42;
~~~

One should not write unit tests asserting `a == b` or `a != b` based on two lambdas having the same body. At the same time, an object can have identity when observed with reference equality, but **do not use identity as business meaning** of a lambda or method reference unless the application explicitly manages a stored reference.

**Do not rely on class names** via `getClass().getName()`: names such as those with `$$Lambda$...` suffixes are runtime details that can change. On modern JDKs, lambda implementations may use hidden classes; do not assume the JVM always generates a "visible" anonymous class for each expression.

**Do not use `new Runnable() { ... }` as a mechanical definition of a lambda.** An anonymous class is a different feature with respect to the scope of `this`, identity, and certain naming/scoping rules, even though both can create objects implementing an interface.

## 9. Complete example 2: reference capture, state mutation, and null error timing

Create the file **CaptureReceiverDemo.java**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;

public class CaptureReceiverDemo {
    static class Prefixer {
        private String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String add(String text) {
            return prefix + text;
        }

        void changePrefix(String updated) {
            prefix = updated;
        }
    }

    public static void main(String[] args) {
        Prefixer target = new Prefixer("A:");
        Function<String, String> bound = target::add;
        Function<String, String> lambda = text -> target.add(text);
        BiFunction<Prefixer, String, String> unbound = Prefixer::add;

        System.out.println("before: " + bound.apply("one"));

        target.changePrefix("B:");
        System.out.println("bound after state change: " +
                bound.apply("two"));
        System.out.println("lambda after state change: " +
                lambda.apply("three"));
        System.out.println("unbound: " +
                unbound.apply(target, "four"));

        Prefixer absent = null;
        try {
            Function<String, String> bad = absent::add;
            System.out.println("unexpected: " + bad.apply("x"));
        } catch (NullPointerException expected) {
            System.out.println("bound null: NullPointerException");
        }

        try {
            unbound.apply(null, "x");
        } catch (NullPointerException expected) {
            System.out.println("unbound null call: NullPointerException");
        }
    }
}
~~~

Run on Java 17+:

~~~bash
javac CaptureReceiverDemo.java
java CaptureReceiverDemo
~~~

Stdout:

~~~text
before: A:one
bound after state change: B:two
lambda after state change: B:three
unbound: B:four
bound null: NullPointerException
unbound null call: NullPointerException
~~~

Analysis:

1. `target::add` evaluates and **binds the receiver `target`** at the time the method reference is created; the SAM `Function.apply(String)` still has only one `String` input.
2. `text -> target.add(text)` captures the same `target` reference, without copying `Prefixer`'s state. After `changePrefix("B:")`, both callbacks see the new prefix.
3. `Prefixer::add` is an unbound reference, so `BiFunction.apply` receives the receiver explicitly in the first position.
4. `absent::add` throws `NullPointerException` **immediately when evaluating the method reference**; the program catches the error before having a chance to call `bad.apply`.
5. `unbound.apply(null,"x")` creates a valid unbound reference beforehand, but when invoking the SAM with a `null` receiver, it throws `NullPointerException` at **invocation time**.

When designing callbacks with short-lived receivers, object capture needs to be considered in terms of lifecycle: the longer a callback holds a reference, the longer the receiver may be kept alive by the garbage collector.

## 10. Looking under Java 17 bytecode: invokedynamic creates a factory

`javac` typically compiles lambda expressions/method references to an `invokedynamic` call site. To observe on a machine with JDK 17+, run:

~~~bash
javac LambdaToSamDemo.java
javap -p -c -v LambdaToSamDemo
~~~

Read the following areas:

1. In `main`, look for `invokedynamic` instructions associated with creating `Converter`, `BiFunction`, `Function`. Expressions with capture will have bytecode loading the captured reference/string before the opcode; non-capturing lambdas may have no factory argument operands.
2. In the `BootstrapMethods` section, find the entry with `REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory`. Typically the bootstrap arguments include a SAM method type, a method handle for the implementation, and an instantiated method type.
3. For a lambda body like `text -> "[" + text + "]"`, `javac` may generate a synthetic implementation method such as `lambda$main$0`. A static method reference like `LambdaToSamDemo::upper` may point directly to the declared method rather than an intermediate synthetic method.
4. When code calls `converter.convert("An")`, the SAM call is usually compiled to `invokeinterface`. **This is not the `invokedynamic` opcode that created the converter earlier.**
5. Inside a lambda implementation method that performs string concatenation, another `invokedynamic` pointing to `StringConcatFactory.makeConcatWithConstants` may appear. Follow each opcode's own bootstrap index.

Conceptual diagram of a capturing case:

~~~text
// Conceptual excerpt, NOT verbatim javap stdout:
aload <local holding captured String>
invokedynamic ... // factory (String)Converter
astore <local holding Converter>

// Later:
aload <local holding Converter>
ldc "42"
invokeinterface ... // Converter.convert:(String)String
~~~

Signature information at the JVM level may use internal class descriptors such as `Lpkg/Outer$Converter;` and `Ljava/lang/String;`. Do not rely on fixed constant-pool `#n` numbers, synthetic method names, or bytecode offsets; instead read **the relationship between factory type, SAM type, and implementation handle**.

### BSM static arguments vs captured arguments

For a lambda capturing `prefix`:

~~~text
BootstrapMethods (fixed configuration in class file):
  LambdaMetafactory.metafactory
  SAM MethodType
  Implementation MethodHandle
  Instantiated MethodType

Runtime when the lambda expression is evaluated:
  load prefix
  invokedynamic [factory] (String)Converter
       └── receives prefix on operand stack
       └── returns a Converter object

Runtime when using the object:
  converter.convert(value)
       └── value is the SAM invocation argument
~~~

`prefix` is a **runtime operand of the invokedynamic factory**, not a fixed bootstrap argument element just because the object may retain `prefix` long-term. And `value` is the argument of **a later call** to the SAM method; one should not call all three groups of data the same kind of "lambda parameter".

## 11. Complete example 3: calling LambdaMetafactory manually to see the factory type

At the `java.lang.invoke` API level, we can explicitly call `LambdaMetafactory.metafactory` to see the **CallSite** whose target is the factory that creates objects implementing the functional interface.

**Scope note:** This program **calls the metafactory API using ordinary Java**; it **does not itself emit an `invokedynamic` opcode for the factory via ordinary source syntax**. It illustrates the same factory/capture structure that the compiler/JVM can use, whereas the `javap` example above shows the actual bytecode generated by the compiler.

Create the file **ManualLambdaFactoryDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ManualLambdaFactoryDemo {
    @FunctionalInterface
    public interface TextOp {
        String apply(String value);
    }

    private static String decorate(String prefix, String value) {
        return prefix + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle implementation = lookup.findStatic(
                ManualLambdaFactoryDemo.class,
                "decorate",
                MethodType.methodType(
                        String.class, String.class, String.class));

        // SAM of TextOp: (String)String
        MethodType samType =
                MethodType.methodType(String.class, String.class);

        // Factory takes String capturedPrefix, returns TextOp object.
        MethodType factoryType =
                MethodType.methodType(TextOp.class, String.class);

        CallSite site = LambdaMetafactory.metafactory(
                lookup,
                "apply",
                factoryType,
                samType,
                implementation,
                samType);

        MethodHandle factory = site.getTarget();
        System.out.println("factory parameters: " +
                factory.type().parameterCount());
        System.out.println("returns TextOp: " +
                (factory.type().returnType() == TextOp.class));

        TextOp hello = (TextOp) factory.invokeExact("Hello ");
        TextOp goodbye = (TextOp) factory.invokeExact("Bye ");

        System.out.println("first: " + hello.apply("An"));
        System.out.println("second: " + goodbye.apply("Binh"));
        System.out.println("reuse object: " + hello.apply("Minh"));
    }
}
~~~

Run commands:

~~~bash
javac ManualLambdaFactoryDemo.java
java ManualLambdaFactoryDemo
~~~

Expected stdout:

~~~text
factory parameters: 1
returns TextOp: true
first: Hello An
second: Bye Binh
reuse object: Hello Minh
~~~

### Dissecting the four signatures

In this program:

| Component | MethodType | Meaning |
| --- | --- | --- |
| `implementation` | `(String,String)String` | Method `decorate(prefix,value)` |
| `samType` | `(String)String` | SAM `TextOp.apply(value)` |
| `factoryType` | `(String)TextOp` | Factory needs captured prefix to create `TextOp` |
| `factory.type()` | `(String)TextOp` | Target handle of the CallSite creating the object |
| When calling `hello.apply(...)` | `(String)String` | SAM takes current input, uses captured prefix |

The values `"Hello "` and `"Bye "` are passed to the **factory handle**, producing `TextOp` objects with different captured behaviors. When calling `hello.apply("An")`, the implementation target receives both the captured prefix and the SAM argument and returns `"Hello An"`. Therefore `factory.type()` must not be equated with `samType`: one is the signature for **creating the object**, the other is the signature for **invoking behavior on the object**.

`invokeExact` has strict call-site signature rules. The cast in `TextOp hello = (TextOp) factory.invokeExact("Hello ");` specifies the return type `TextOp`; if assigned directly to `Object` with `invokeExact` without an adapter, one may encounter `WrongMethodTypeException` because the call site does not match the handle's return type.

**Do not infer instance counts from the number of factory invocations.** The code creates two variables pointing to two `TextOp` values with two different captured prefixes; this does not allow generalizing that all non-capturing lambdas always create new objects or are always cached.

## 12. How do lambdas and method references differ from anonymous classes?

Some easily confused points:

| Criterion | Lambda/method reference | Anonymous class |
| --- | --- | --- |
| Primary role | Represents a behavioral value according to a target functional interface | Declares an unnamed class and creates an instance |
| Target type | Requires a compatible functional interface | Can implement an interface or extend a suitable class |
| `this` in body | `this` of the enclosing lexical scope for lambdas | `this` is the anonymous class instance |
| Target-type capability | Target-typed/poly expression | Object-creation expression with a concrete declared type |
| Runtime representation | Implementation is not required to have a stable named class | Has an anonymous class per class-declaration semantics |
| Identity across evaluations | Does not guarantee each lambda evaluation is a new object | Each `new ... { ... }` creates a new instance |
| Method body | Lambda has an expression/block body; method reference selects a callable | Body is written inside the anonymous class definition |
| Local capture | Variable must be final/effectively final | Captured local variables must also be final/effectively final |

Example:

~~~java
Runnable viaLambda = () -> System.out.println(this);
Runnable viaAnonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this);
    }
};
~~~

This is an **illustrative** snippet, valid only inside an **instance method or instance initializer** of the enclosing class (not static `main`). For the lambda, `this` refers to the instance of the class containing the expression. For the anonymous class, `this` refers to the anonymous `Runnable` object. The example intentionally shows the difference in `this`; one should not copy it verbatim into a static context and conclude that lambdas are "broken".

A lambda is not a "shorthand anonymous class" in the sense of sharing all characteristics. Using `LambdaMetafactory` and `invokedynamic` is an implementation path that decouples the call site from a specific implementation class.

## 13. When to use a lambda, when to use a method reference?

A **method reference** is a good choice if an existing method/constructor already has the exact behavior to pass and the signature matches the target type:

~~~java
java.util.function.Function<String, String> normalize =
        String::strip;
~~~

A **lambda** is clearer when you need to combine expressions, rename parameters, or add logic:

~~~java
java.util.function.Function<String, String> normalize =
        input -> "[" + input.strip() + "]";
~~~

There is no rule that "method references are always faster than lambdas". The compiler can generate similar adapters; performance depends on the target, JIT, escape analysis capability, captured objects, boxing, and call-path stability. Prioritize readability and contract checking first; if performance matters, benchmark the actual application.

### Some practical choices

- Use `User::getId` instead of `user -> user.getId()` if the receiver is passed from the SAM and it is a direct mapping without obscuring meaning.
- Use `repository::save` if a repository instance is already selected and the callback needs to be invoked on that instance.
- Use `type -> new Service(type, config)` if the constructor reference `Service::new` cannot represent the configuration value.
- Use a lambda when there are null checks, exception translation, or multiple operations that cannot be expressed by a single method reference.
- Use a custom functional interface when the SAM name and parameter types need to express a clearer business contract than the overly general `Function<A,B>`.

It is not necessary to turn every method into a lambda just to run through `invokedynamic`. Direct Java method calls remain appropriate when there is no need to pass behavior as a value.

## 14. What can be inspected when observing a lambda instance?

Given:

~~~java
java.util.function.Predicate<String> nonEmpty =
        s -> !s.isEmpty();
~~~

You can check:

- `nonEmpty instanceof Predicate` is true, because the object must implement the target interface.
- `nonEmpty.test("A")` returns `true`; `nonEmpty.test("")` returns `false`.
- `nonEmpty.getClass()` exists like on any object, but **the class name must not be treated as a stable API**.
- `nonEmpty == someOtherLambda` is meaningless for verifying logical equivalence between two lambdas with identical bodies.

When testing a callback, call the SAM with concrete inputs and assert outputs, side effects, or exceptions. If testing capture, mutate the state of a valid captured object and observe the result; **do not** test synthetic method names, loaded class counts, or reference addresses.

### Is serialization enabled by default?

No. A lambda object is **not automatically serializable** just because it has a SAM. Serializability depends on the target functional interface and related conditions, such as having the `java.io.Serializable` marker in the target type used. Even when creating a serializable lambda, the serialized representation of lambdas and method references is subject to version and implementation constraints; it should not be treated as a stable schema for long-term storage.

For applications that need to persist tasks across process restarts, it is usually better to store **data describing the job** (operation id, parameters, version) and reconstruct the behavior in-process, rather than storing the lambda object directly and depending on internal JVM classes.

## 15. Common errors when converting lambdas/references to functional interfaces

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `incompatible types: ... is not a functional interface` | Interface has multiple independent abstract methods | Design a valid SAM, consider `@FunctionalInterface` |
| `var f = x -> x` does not compile | Lambda lacks a target type to infer the interface | Declare `Function<T,R>` or cast explicitly |
| Incompatible method reference | Wrong parameter count, return type, or bound/unbound receiver | Write the SAM signature and referenced method side by side |
| Assigning `Prefixer::add` to `Function<String,String>` fails | Unbound reference needs a `Prefixer` receiver as the first parameter | Use `BiFunction<Prefixer,String,String>` or `instance::add` |
| `instance::method` throws NPE on creation | Receiver expression evaluates to null | Ensure receiver is non-null **before** creating the bound reference |
| Lambda reading a mutable field gives different results | Capture holds a reference, does not snapshot all fields | Clarify the contract on when state is read |
| `local variables referenced ... must be final or effectively final` | Reassigning a captured local variable | Do not reassign; use controlled object state if mutability is truly needed |
| `this` does not point to the callback object | Lambda uses lexical `this` | Do not use `this` as in an anonymous class |
| Test `a == b` flakes across JDKs | Lambda identity/caching is not guaranteed | Test behavior through the SAM instead of reference identity |
| `$$Lambda...`-style names leak into logs and get hardcoded | Depending on internal implementation class names | Log the functional interface/call site name or business identifier |
| Confusing `LambdaMetafactory` and `StringConcatFactory` | Same class has multiple `invokedynamic` instructions | Follow each bootstrap index and implementation method |
| `WrongMethodTypeException` when calling factory handle manually | `invokeExact` call-site type differs from `factory.type()` | Check both parameters and return type, use appropriate cast or adapter |
| `LambdaConversionException` when using metafactory manually | Invalid SAM type, instantiated type, implMethod, or captured args | Check the relationship among the 3 signatures and `Lookup` access privileges |
| Lambda throws a disallowed checked exception | SAM does not declare that checked exception type | Choose a suitable interface or handle/map the exception intentionally |
| Callback retains objects longer than intended | Capturing receiver/context in the callback object | Review ownership and callback lifecycle, avoid uncontrolled global caches |
| Poor performance due to boxing | Choosing generic `Function<String,Integer>` instead of primitive-specialized interface | Consider `ToIntFunction<String>`, benchmark after correctness |

### Checking a method reference bound to the wrong receiver

When writing `obj::method`, the receiver is already bound. When writing `Type::method` for an instance method, the receiver is usually the first parameter of the functional interface. Changing `obj` to `Type` can shift from `Function<String,String>` to `BiFunction<Type,String,String>`. Do not merely compare matching method names.

### Avoiding inferring runtime classes from source code

The compiler/JVM has the right to choose different implementation structures to satisfy the same Java contract. When debugging, what is reliable is **the SAM, captured arguments, and behavior on invocation**, not class names or the number of objects allocated in memory. Implementation changes between JDKs should not break business tests.

## 16. Self-check (with answers)

**Question 1.** Why can `() -> System.out.println("x")` be assigned to `Runnable`?  
**Answer:** Because `Runnable` is a functional interface with SAM `void run()`; the lambda has no parameters and has a body compatible with a void-returning method.

**Question 2.** When assigning `Function<String,String> f = s -> s.trim();`, has `trim()` run yet?  
**Answer:** Not yet. The lambda expression is evaluated into an object implementing `Function`; the body runs when `f.apply(...)` is called.

**Question 3.** Where is the receiver when `String::length` is used with `ToIntFunction<String>`?  
**Answer:** The receiver is the `String` passed as the SAM parameter `applyAsInt(String)`; it is an unbound reference.

**Question 4.** Does `someString::length` used with `IntSupplier` need a SAM parameter?  
**Answer:** No; the receiver was already bound when the method reference was created, and the SAM `getAsInt()` takes no parameters.

**Question 5.** Has `Prefixer::new` run the constructor when creating the reference?  
**Answer:** Not yet. Only when the factory function's SAM is called with the appropriate argument does the constructor run.

**Question 6.** Can we write `var f = x -> x;`?  
**Answer:** No; a lambda is a poly expression requiring a concrete functional-interface target type. One can use `var f = (Function<String,String>) (x -> x);`.

**Question 7.** Can a local variable `prefix` used by a lambda be reassigned afterward?  
**Answer:** No, if doing so violates `final`/`effectively final`. However, if an object is captured, the object's state can change.

**Question 8.** What kind of value does a `LambdaMetafactory` factory handle return?  
**Answer:** An object compatible with the functional interface; the factory signature can take captured arguments and return the interface type.

**Question 9.** Does a factory signature `(String)TextOp` mean the SAM is `(String)TextOp`?  
**Answer:** No. That is the signature for **creating the object** with a captured `String`. The SAM itself can be `(String)String`.

**Question 10.** Do the bootstrap static arguments `samMethodType`, `implMethod`, and `instantiatedMethodType` contain the specific captured prefix `"Hi "`?  
**Answer:** Typically no; the captured prefix is a runtime argument passed to the `invokedynamic` factory when the lambda expression is evaluated.

**Question 11.** If two lambdas have identical bodies, can we compare them with `==` to know whether they are equivalent?  
**Answer:** No. Java does not guarantee instance creation/caching behavior or object identity based on body; test behavior through the SAM.

**Question 12.** When does `obj::method` with `obj == null` fail?  
**Answer:** Immediately when evaluating the bound method reference. With unbound `Type::method`, a null receiver passed to the SAM causes the error at invocation time.

**Question 13.** Why might two different kinds of `invokedynamic` appear in one class?  
**Answer:** `javac` can use `LambdaMetafactory` to link lambda factories and `StringConcatFactory` to perform string concatenation; they serve two different call sites.

**Question 14.** Does Java require a lambda to be an anonymous class?  
**Answer:** No. Java defines expression behavior and functional-interface objects, without requiring an anonymous class of a specific name or shape.

**Question 15.** When evaluating capture in a multithreaded environment, where can bugs arise?  
**Answer:** A captured object can be mutable and shared, so data races can occur if state is not protected. The effectively final rule for local variables does not make the object thread-safe on its own.

## 17. Code and bytecode reading checklist

- [ ] Identify the **functional interface target type** from assignment, method parameter, return, or cast.
- [ ] Find the **SAM** and the actual input/output signature needed under generic instantiation.
- [ ] Distinguish a lambda body from a method reference selecting static/bound instance/unbound instance/constructor.
- [ ] Note **captured values** if the lambda/reference uses data from the enclosing scope.
- [ ] Distinguish **when the expression is evaluated to obtain an object** from **when the SAM is called to run behavior**.
- [ ] If using `javap`, locate `invokedynamic` at the lambda-creation call site, `LambdaMetafactory` in `BootstrapMethods`, and `invokeinterface` when calling the SAM.
- [ ] Read `invokedType` of the **factory**, `samMethodType`, `implMethod`, and `instantiatedMethodType` separately; do not conflate them into one.
- [ ] If the lambda body concatenates strings, recognize `StringConcatFactory` as a separate bootstrap.
- [ ] Do not depend on the identity/class name/synthetic method name of the lambda object.
- [ ] Test behavior and exceptions through the SAM, including capture and mutation cases when needed.
- [ ] Choose primitive-specialized interfaces when avoiding boxing is meaningful, but prioritize correctness first and benchmark afterward.
- [ ] Review receiver/context lifecycles when callbacks are stored long-term or passed across threads.

## 18. Conclusion

Lambdas and method references are **expressions that produce behavioral values whose target type is a functional interface**. The compiler uses the SAM to check signatures; the runtime creates or provides an object implementing the interface; callers use the interface's method to execute behavior. With Java 17 `javac`, the typical implementation path is `invokedynamic` linked via `LambdaMetafactory`, where the call site's target is responsible for creating/providing the functional object and can accept **captured runtime arguments**.

To read a lambda accurately, ask yourself in order: **which interface? which SAM? when is the object created/obtained? what is captured? when is the SAM invoked?** For a method reference, add the question **is the receiver already bound or is it a SAM parameter?** Answering those six questions helps you understand both ordinary Java syntax and the underlying `java.lang.invoke` mechanism without relying on class names or tricks specific to a single JVM.
