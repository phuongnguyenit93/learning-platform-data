# Comparing Direct Calls, Method.invoke, and MethodHandle in Java

In Java, the same method can be invoked in multiple ways: **direct call** using ordinary Java syntax, **reflective call** via `java.lang.reflect.Method.invoke(...)`, or **typed dynamic call** via `java.lang.invoke.MethodHandle`. All three can lead to the same business behavior, yet they differ in type-checking timing, method lookup, primitive value handling, access control, exceptions, and optimization opportunities.

This is a practice lesson in Java Core – Reflection. The goal is not to conclude that one API is always fastest, but to **understand when each approach fits and accurately observe behavior on Java 17+**.

## 1. Three Mechanisms at a Glance

Suppose we have a class:

```java
class Calculator {
    int add(int a, int b) {
        return a + b;
    }
}
```

This is an illustrative snippet, not a complete program.

### A. Direct call

```java
Calculator calculator = new Calculator();
int result = calculator.add(3, 4);
```

The compiler knows `Calculator`, the method name, and the argument count and types. If the method name changes or incompatible arguments are passed, errors are normally caught upon recompilation. For instance methods with dynamic dispatch, the JVM still chooses the appropriate overridden implementation at runtime; "direct call" **does not mean** every call is statically bound at compile time.

### B. Reflection via Method.invoke

```java
Method method = Calculator.class.getDeclaredMethod(
        "add", int.class, int.class);
Object result = method.invoke(new Calculator(), 3, 4);
```

This snippet assumes `java.lang.reflect.Method` is imported, the method is accessible, and checked exceptions are handled. `getDeclaredMethod(...)` uses the **name as a string** and exact parameter types to fetch metadata. Only afterward does `invoke(...)` actually run the method. The `int` return value is **boxed** into `Integer` because `Method.invoke` returns `Object`.

### C. MethodHandle

```java
MethodHandle handle = MethodHandles.lookup().findVirtual(
        Calculator.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
int result = (int) handle.invokeExact(new Calculator(), 3, 4);
```

This snippet requires importing `java.lang.invoke.*` and handling `Throwable`. `findVirtual` looks up an instance method with **return type `int`** and **two `int` parameters**. The `MethodHandle` has no bound receiver yet, so at invocation time `Calculator` is the first argument. `invokeExact` requires the static type at the call site to match the handle's type exactly; the result is `int`, without going through an API-returned `Object` result like `Method.invoke`.

Note: `MethodHandle` can also look up constructors, getters/setters, static methods, default methods, and compose call pipelines via handle adaptations. The examples here focus on common method calls.

## 2. Detailed Comparison

| Criterion | Direct call | `Method.invoke` | `MethodHandle` |
|---|---|---|---|
| Method identification | Java symbol in source code | Look up `Method` object, usually by string name | Look up or adapt into a handle with `MethodType` |
| Type checking | Compiler checks the call | `invoke` checks receiver and arguments at runtime | `invokeExact` requires exact call-site signature match; `invoke` can adapt |
| Return type | Declared by the method, e.g. `int` | `Object`, primitives are boxed, `void` is `null` | Return type in `MethodType`, e.g. `int` |
| Receiver instance | Written as `receiver.method(...)` | First argument of `Method.invoke` | Can be the first arg of a `findVirtual` handle or pre-bound |
| Signature | From source, with overload resolution | Usually `getMethod(name, paramTypes...)` | `MethodType` with return type and parameter types |
| Exception from target method | Thrown via normal Java flow | Wrapped in `InvocationTargetException` | `MethodHandle` invocation normally throws the target exception directly |
| Access control | Per Java rules in source and runtime | Reflection checks access/modules; has APIs to attempt opening access | `Lookup` carries permissions per lookup class/module; access checked on handle creation |
| Renaming the method | Compiler usually catches stale source usages | Old strings can fail at runtime | Strings used in lookup can also fail at runtime |
| Argument conversion | Java compiler rules apply to source calls | Valid Reflection boxing/unboxing and primitive widening, no arbitrary narrowing | `invokeExact` does not auto-convert; `invoke`/adapters support valid conversions |
| Best suited for | Ordinary application logic | Frameworks needing metadata, introspection, flexible invocation | Frameworks/runtimes needing typed dynamic calls, combinators, and optimization |

**Key point:** `MethodHandle` does not "remove the dynamism" of Reflection. When using `findVirtual(Class, String, MethodType)`, you still pass a method name as a string and can still hit lookup errors after refactoring. Its primary advantage is a **strongly typed invocation model and composability/adaptation**, not eliminating every runtime linking risk.

## 3. The Path from Lookup to Invocation

Distinguish two independent steps:

```text
                  SELECT METHOD                       EXECUTE
Direct call:    symbol/compiler                -> invokevirtual/invokestatic...
Reflection:     Class.getMethod(...)           -> Method.invoke(...)
MethodHandle:   Lookup.findVirtual/findStatic  -> invokeExact/invoke/...
                    |                                  |
               member metadata                   run actual logic
```

APIs like `Class.getMethod(...)` or `Lookup.findVirtual(...)` locate a member; they **do not invoke the business method**. Only the invocation step runs the target logic. Class loading/resolution or permission checks during lookup can still throw errors and trigger other JVM activity; do not assume lookup is completely side-effect-free in all environments.

### `Method.invoke` is a method on a metadata object

A `Method` is metadata for a declared method. To call an instance method:

```java
Object value = method.invoke(receiver, arg1, arg2);
```

- `receiver` must be an instance compatible with the method's declaring class.
- For static methods, the receiver parameter is ignored per the API; passing `null` is customary for clarity.
- For zero-parameter methods, you can pass no arguments or an appropriate array argument.
- `Method.invoke` declares `Object` as its return type; cast/unbox when you need a concrete type.
- If the invoked method throws an exception, `invoke` throws `InvocationTargetException` containing the original error in `getCause()`.

**Varargs warning:** `Method.invoke(Object, Object...)` is itself a Java varargs API. When passing an array as **a single parameter of the target method**, prepare a proper `Object[]` containing one element so the compiler does not mistakenly spread the array as `invoke`'s argument list. This is a Reflection call-layer concern, not a change to the target's signature.

### `MethodHandle` is a typed invocation point

`MethodHandle.type()` returns a `MethodType` holding the return type and parameter list **of the handle itself**. For instance method `int add(int,int)`, an unbound `findVirtual` result has the form:

```text
(Calculator,int,int)int
```

The first argument is the receiver; the remaining two arguments are the target method's Java parameters. Calling `bindTo(calculator)` turns that handle into:

```text
(int,int)int
```

The caller then no longer passes the receiver. Binding changes **the handle's signature**, without modifying the class or creating a new method in the target class.

Also distinguish:

- `findVirtual(...)`: looks up a virtual instance method; the handle requires a receiver and performs appropriate virtual dispatch.
- `findStatic(...)`: looks up a static method; the handle **has no receiver**.
- `findConstructor(...)`: a handle representing object creation; the handle's return type is the newly constructed class.
- `Lookup.unreflect(Method)`: can create a `MethodHandle` from a `Method`, still subject to appropriate access checks.
- `invokeExact(...)`: the call site must match `handle.type()`'s parameter types **and return type** exactly.
- `invoke(...)`: can apply `asType`-style type adaptations among supported conversions; do not assume it converts arbitrary types.
- `invokeWithArguments(...)`: flexible interface taking arguments as `Object`s; handy for utilities/frameworks, yet should not be used to infer `invokeExact` performance.
- Combinators such as `asType`, `bindTo`, `filterArguments`, and `insertArguments` let you construct tailored call pipelines without writing ordinary wrapper methods for every case.

## 4. Complete Java 17+ Example with Verified Output

The program below uses a `Calculator` with an instance method, a static method, and a method that intentionally throws an error. It compares results across direct calls, Reflection, unbound/bound `MethodHandle`, and `invokeWithArguments`, while testing **two distinct error categories**.

Save as **`InvocationComparisonDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationComparisonDemo {
    public static class Calculator {
        private final int offset;
        public Calculator(int offset) { this.offset = offset; }
        public int add(int left, int right) { return offset + left + right; }
        public int risky(int denominator) {
            if (denominator == 0) throw new IllegalArgumentException("zero");
            return offset / denominator;
        }
        public static String describe(String label, int value) {
            return label + "=" + value;
        }
    }

    public static void main(String[] args) throws Throwable {
        Calculator calculator = new Calculator(10);
        System.out.println("direct: " + calculator.add(3, 4));

        Method method = Calculator.class.getMethod("add", int.class, int.class);
        Object reflected = method.invoke(calculator, 3, 4);
        System.out.println("reflection: " + reflected + " ("
                + reflected.getClass().getSimpleName() + ")");

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle virtual = lookup.findVirtual(
                Calculator.class, "add",
                MethodType.methodType(int.class, int.class, int.class));
        int exact = (int) virtual.invokeExact(calculator, 3, 4);
        System.out.println("handle exact: " + exact);
        System.out.println("unbound type: " + virtual.type());

        MethodHandle bound = virtual.bindTo(calculator);
        System.out.println("bound type: " + bound.type());
        int boundValue = (int) bound.invokeExact(3, 4);
        System.out.println("handle bound: " + boundValue);
        Object generic = bound.invokeWithArguments(3, 4);
        System.out.println("handle generic: " + generic);

        MethodHandle staticHandle = lookup.findStatic(
                Calculator.class, "describe",
                MethodType.methodType(String.class, String.class, int.class));
        String label = (String) staticHandle.invokeExact("sum", 17);
        System.out.println("static handle: " + label);

        try {
            method.invoke(calculator, "3", 4);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "reflection wrong argument: IllegalArgumentException");
        }
        try {
            long wrong = (long) bound.invokeExact(3, 4);
            System.out.println("unreachable: " + wrong);
        } catch (WrongMethodTypeException e) {
            System.out.println(
                    "handle wrong signature: WrongMethodTypeException");
        }

        Method risky = Calculator.class.getMethod("risky", int.class);
        try {
            risky.invoke(calculator, 0);
        } catch (InvocationTargetException e) {
            System.out.println("reflection target error: "
                    + e.getCause().getClass().getSimpleName());
        }
        MethodHandle riskyHandle = lookup.findVirtual(
                Calculator.class, "risky",
                MethodType.methodType(int.class, int.class));
        try {
            int unused = (int) riskyHandle.invokeExact(calculator, 0);
            System.out.println("unreachable: " + unused);
        } catch (IllegalArgumentException e) {
            System.out.println("handle target error: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile/run commands:

```bash
javac --release 17 -encoding UTF-8 InvocationComparisonDemo.java
java InvocationComparisonDemo
```

**Actual stdout of the program above:**

```text
direct: 17
reflection: 17 (Integer)
handle exact: 17
unbound type: (Calculator,int,int)int
bound type: (int,int)int
handle bound: 17
handle generic: 17
static handle: sum=17
reflection wrong argument: IllegalArgumentException
handle wrong signature: WrongMethodTypeException
reflection target error: IllegalArgumentException
handle target error: IllegalArgumentException
```

The example was compiled with `javac --release 17` and run to verify stdout; no dependencies outside the JDK are required.

### Reading Each Result

1. `Calculator(10).add(3, 4)` returns `10 + 3 + 4 = 17` across all three valid invocation paths.
2. Reflection returns an `Object` holding the runtime value `Integer(17)`. In Java source, `invoke` receives primitive arguments through `Object...` varargs, so boxing happens when packing arguments.
3. The unbound handle has signature `(Calculator,int,int)int`. `invokeExact(calculator, 3, 4)` requires the receiver and two `int`s.
4. `bindTo(calculator)` fixes the receiver; the signature becomes `(int,int)int`.
5. `invokeWithArguments(3, 4)` accepts flexible argument passing and returns the value as `Object`, so the example receives `17` via `Object generic`.
6. `findStatic` has signature `(String,int)String` and does not take `Calculator` as a receiver.
7. Passing the string `"3"` to a Reflection method expecting `int` is rejected with `IllegalArgumentException`. Reflection does not automatically parse text into integers.
8. The line `long wrong = (long) bound.invokeExact(3, 4)` intentionally uses a **call-site return type of `long`**, whereas the handle returns `int`. That triggers `WrongMethodTypeException`, even though both `int` arguments match.
9. `risky(0)` actually throws `IllegalArgumentException`. Via `Method.invoke`, the target error is wrapped in `InvocationTargetException`. Via `MethodHandle`, the target error passes straight out in this case. Both lines print `IllegalArgumentException` because the code prints **the actual cause or exception**, not Reflection's wrapper class.

## 5. Distinguishing invokeExact, invoke, and invokeWithArguments

These three `MethodHandle` invocation forms cannot be swapped arbitrarily.

### invokeExact: strict static typing at the call site

```java
MethodHandle h = MethodHandles.lookup().findStatic(
        Integer.class, "sum",
        MethodType.methodType(int.class, int.class, int.class));
int value = (int) h.invokeExact(2, 3);
```

This is a separate illustrative snippet requiring `Throwable` handling, and `Integer.sum(int,int)` is a static method. The Java compiler gives the call site a signature of two `int`s returning `int`. If you write `Object value = h.invokeExact(2, 3)`, the call-site return type becomes `Object`, which **does not match** a handle returning `int`, causing `WrongMethodTypeException` at runtime. The `(int)` cast in source code genuinely defines the static type recorded at the call site; it is not a decorative cast.

### invoke: adapts types, yet still has limits

```java
int value = (int) h.invoke(2, 3);
```

`invoke` does not enforce exact matching like `invokeExact` and can apply `MethodHandle` conversion rules where applicable. However, not every mismatch is supported, and cost/success depends on the conversion kind. You can use `h.asType(desiredMethodType)` when you need an adapter with an explicit target signature.

### invokeWithArguments: convenient for runtime argument lists

```java
Object value = h.invokeWithArguments(2, 3);
```

This is handy for frameworks holding argument lists as `Object[]` or `List<?>`. It generally performs more adaptation/boxing work than a statically typed `invokeExact` call, so its timings should not be used to infer the peak performance of `MethodHandle`.

All three snippets assume `h` is in scope with the relevant imports and exception handling. A complete program is already provided in Section 4.

## 6. Boxing, Primitives, and Overloads Are Common Bug Sources

### Method.invoke

Suppose the target method has signature `int sum(int,int)`:

- `Method.invoke(target, 2, 3)` lets primitive arguments be boxed before passing through `Object...`; Reflection performs compatible conversions to invoke the target method.
- Returning `int` is boxed into `Integer` in the `Object` result slot.
- If the target method returns `void`, the result of `Method.invoke` is `null`.
- Passing `null` to a primitive parameter is invalid.
- Passing `Integer` when the parameter expects `long` can be unboxed and primitive-widened per Reflection rules; passing `Long` when `int` is expected will not auto-narrow. Passing `String` will not auto-parse into a number.

### getMethod lookup must match parameter types

```java
Method m = Calculator.class.getMethod("add", int.class, int.class);
```

`getMethod("add", Integer.class, Integer.class)` **is not equivalent**, even though Java source has autoboxing. Lookup via `getMethod` does not perform flexible overload resolution like the compiler. `MethodHandle` lookup also includes the **return type** in `MethodType`.

### Generics and arrays note

Java generics are largely erased in bytecode (type erasure), so Reflection and `MethodHandle` lookup operate on erased runtime types, not type arguments like `List<String>` as standalone symbols. `MethodHandle` provides combinators for array spreading/collecting; when a method takes `int[]` or `Object[]`, check the handle signature and varargs passing carefully so you do not confuse an array of arguments with a single array argument.

## 7. Access Control, Lookup Errors, and Exceptions

### Access rules do not vanish when using Reflection

- Direct calls obey access rules from source, package, module, and runtime validity.
- `Class.getDeclaredMethod` **can find** a private method, yet that does not mean `Method.invoke` is allowed to call it.
- `Method.setAccessible(true)` / `trySetAccessible()` can enable deep reflection **only when module/package rules allow**. Indiscriminate use may be denied or make the design hard to govern.
- `MethodHandles.lookup()` creates a `Lookup` carrying permissions bound to the calling class. `findVirtual`, `findStatic`, and `unreflect` check the corresponding access conditions.
- For private members, `MethodHandles.privateLookupIn(...)` is an option with proper permission checks and open-package requirements, not a way to bypass all module encapsulation.

**Never treat Reflection or MethodHandle as a privilege-escalation mechanism.** They are code-invocation mechanisms operating within runtime and module boundaries. When designing a plugin/tool runner, which methods may be invoked still requires application-level allowlists and authorization.

### Lookup errors and invocation errors are two distinct groups

| Situation | Reflection | MethodHandle |
|---|---|---|
| Wrong method name | `NoSuchMethodException` at `getMethod`/`getDeclaredMethod` | `NoSuchMethodException` at `Lookup.find...` |
| Inaccessible | `IllegalAccessException` / `InaccessibleObjectException` depending on step | `IllegalAccessException` at lookup or handle conversion |
| Wrong receiver | Typically `IllegalArgumentException` at `Method.invoke` | Type/receiver mismatch error depending on invoke form |
| Mismatched arguments | `IllegalArgumentException` at `Method.invoke` | `WrongMethodTypeException` at an incompatible call site or conversion-related exception |
| Target method throws | `InvocationTargetException` wrapping original error | Normally throws target's original error directly |
| Target class initialization fails | May surface `ExceptionInInitializerError`/related error | May also encounter initialization errors when target method is invoked |

Do not catch every `Exception` and report "method does not exist". Distinguish lookup/permission/type mismatch from target business errors. When logging exceptions from `Method.invoke`, inspect `InvocationTargetException.getCause()` while still retaining wrapper/context information for diagnosis.

## 8. Performance: Measure Properly, Avoid Absolute Claims

The rule of thumb "direct call is faster than MethodHandle which is faster than Reflection" is sometimes common lore, **not an absolute law across all JDKs and scenarios**.

Factors to examine:

1. **JIT and inlining:** the compiler can optimize direct calls heavily when targets are known; `MethodHandle` with stable handles also has strong optimization opportunities. Reflection in modern JDKs has improved substantially as well, so you cannot rely indefinitely on old benchmarks.
2. **Lookup cost:** if you fetch a fresh `Method`/`MethodHandle` on **every loop iteration**, you are measuring both discovery and invocation, not call overhead alone.
3. **Argument types and boxing:** Reflection goes through an `Object...` interface; `invokeWithArguments` also incurs adaptation/boxing. A benchmark returning `Object` and a benchmark returning `int` may not be doing equal work.
4. **Monomorphic vs. megamorphic call sites:** the number of target types and whether the JVM can statically know the handle strongly affect optimization.
5. **Real workload:** when the target method performs I/O, database queries, heavy computation, or network calls, dispatch overhead may be tiny compared to the actual work.
6. **JDK/runtime version and warmup:** the JVM requires warmup; results can differ across Java 17, 21, or future JDKs and across implementations.
7. **Benchmark dead-code elimination:** if the result goes unused, the JIT may eliminate the work, making measurements meaningless.

A serious benchmark should use **JMH (Java Microbenchmark Harness)**, with warmup, multiple iterations, JVM forks, and blackholes/return values to keep work observable. Use identical implementations and data, **cache** methods and handles if that reflects real application behavior, and measure lookup separately. Only then compare latency/throughput alongside the JDK and JVM flags.

When evaluating architectural choices, do not benchmark `Method.invoke` on a target doing I/O against direct addition of two numbers. Nor should you advise rewriting all code to `MethodHandle` based on a single microbenchmark. Code maintainability and clarity usually matter far more than a few nanoseconds in ordinary business logic.

## 9. When to Choose Which Approach?

| Need | Recommendation |
|---|---|
| Calling a method known statically at compile time | **Direct call**, preferring clear interfaces/method references |
| Framework needing to list annotations, methods, generic metadata | **Reflection metadata**; invoke via `Method.invoke` if flexibility is needed |
| Runtime building dynamic call chains needing typed adapters/combinators | **MethodHandle** |
| Running the same dynamic method repeatedly with stable structure | Consider **caching `MethodHandle`** and evaluating with real benchmarks |
| Input is class/method names from configuration | Both Reflection and Lookup require **allowlist, schema, and permission validation** |
| Code using proxies, serializers, DI, or RPC | Choose the tool based on framework and API contract, not speed lore alone |
| Ordinary logic with a stable API | Do not add Reflection/MethodHandle when direct calls are already simple and suitable |

A good practice is separating **discovery** (reading `Method`/annotations or resolving a `MethodHandle`) from **execution** (actually invoking). Metadata discovery should never execute business logic on its own. Only after checking schemas and permissions should the executor invoke.

## 10. Common Learner Mistakes

- **Confusing Reflection with MethodHandle:** `Method` is a metadata object with an `invoke(Object,Object...)` API; `MethodHandle` is a callable with a `MethodType` that can be bound, adapted, and combined. They are not the same abstraction.
- **Forgetting `findVirtual`'s receiver:** the initial handle usually takes the receiver as its first argument. `bindTo` fixes that object.
- **Assuming `invokeExact` auto-widens `int` to `long`:** No; the call site's return type must match as well.
- **Assuming `Method.invoke` returns `int`:** the API always returns `Object`; primitives are boxed.
- **Forgetting `InvocationTargetException`:** Reflection's wrapper hides the real cause if not unwrapped.
- **Looking up with wrapper types instead of primitives:** `int.class` differs from `Integer.class` during lookup.
- **Ignoring access/module rules:** finding a private method does not mean having permission to execute it.
- **Creating a new method/handle on every call and benchmarking speed:** the numbers mix lookup cost with invocation cost.
- **Believing handles are always faster:** test empirically on the target JDK and realistic workload.
- **Renaming a method while forgetting runtime strings:** both `getMethod("oldName",...)` and `findVirtual(...,"oldName",...)` can break after refactoring if strings are not updated.

## 11. Self-Check

**Question 1.** `Method.invoke(calculator, 3, 4)` invokes a method returning `int`. What type does the receiving `Object` variable hold?

An `Integer` boxing the `int` value, assuming the method executes successfully.

**Question 2.** Why does `findVirtual(Calculator.class, "add", methodType(int.class,int.class,int.class))` produce a handle of type `(Calculator,int,int)int`?

Because a virtual method requires the **receiver** first at the handle's call site, ahead of the original method's two parameters. The `MethodType` passed to `findVirtual` describes the method's Java signature **excluding the receiver**, while the returned handle includes the receiver.

**Question 3.** Does obtaining a `Method` from `getMethod` mean the method has already run?

No. Lookup returns metadata; `Method.invoke` triggers execution.

**Question 4.** Why does `long x = (long) bound.invokeExact(3,4)` fail even though an `int` can be converted to `long` in normal Java?

Because `invokeExact` requires the **call site's return type to be `int`** to match the handle's type. Declaring/casting to `long` directly at the call site changes the requested signature and throws `WrongMethodTypeException`. To convert, receive `int` first and widen in Java: `int tmp = (int) bound.invokeExact(3,4); long x = tmp;`, or use an appropriate adapter.

**Question 5.** When the target method throws `IllegalArgumentException`, what is the key difference between Reflection and MethodHandle?

`Method.invoke` wraps the target exception in `InvocationTargetException`, whereas `MethodHandle` invocation normally throws the target's exception directly. Execution errors must be distinguished from lookup/signature errors.

**Question 6.** Which approach is always fastest?

There is no single fixed answer across all JDKs and applications. For statically known methods, direct calls are usually preferred for clarity and compile-time type checking; when dynamism is required, try Reflection/MethodHandle according to functionality and benchmark with JMH on the target environment.

## References

- Java SE 17 API: [`java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) — metadata, `invoke`, access, `InvocationTargetException`.
- Java SE 17 API: [`java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) — `invokeExact`, `invoke`, adapters.
- Java SE 17 API: [`java.lang.invoke.MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) — `findVirtual`, `findStatic`, `unreflect`, access checks.
- Java SE 17 API: [`java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html) — handle type signatures.
- [OpenJDK JMH](https://github.com/openjdk/jmh) — microbenchmarking for the JVM; measure realistic workloads and configurations.
- Java Language Specification §15.12 (method invocation), JVM Specification §6.5 (invoke instructions), §5 (loading/linking/initialization).

**Key takeaway:** **Direct calls** offer clean syntax and compile-time type checking; **`Method.invoke`** invokes dynamically via metadata with an `Object` argument/return interface and wraps target exceptions; **`MethodHandle`** carries a `MethodType` signature supporting strict typed calls, binding, and adaptation. Choose based on requirements and actual behavior before optimizing performance.