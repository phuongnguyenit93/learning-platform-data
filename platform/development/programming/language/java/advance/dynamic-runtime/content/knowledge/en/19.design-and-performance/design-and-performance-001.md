# 19.1. Choosing direct calls, functional interfaces, reflection, method handles, or proxies by need

## 1. The design problem: no single invocation mechanism is always best

A Java system has multiple ways to trigger the same behavior:

- **Direct call** to a method through a variable with a statically known type, which may be a call on a concrete class or through an interface.
- **Functional interface** accepting a lambda/method reference, such as `Runnable`, `Function<T,R>`, `IntUnaryOperator`, or a custom-defined interface.
- **Core Reflection** using `java.lang.reflect.Method`, `Constructor`, `Field` to discover and manipulate members from runtime metadata.
- **`MethodHandle`** using `java.lang.invoke.MethodHandles.Lookup`, `MethodType`, and `MethodHandle.invokeExact`/`invoke` to create and use strongly typed invocations that can be composed into adapters.
- **JDK dynamic proxy** using `Proxy.newProxyInstance` + `InvocationHandler` to intercept and delegate calls through an **interface** without writing a manual wrapper for each method.

All five can lead to the **same business method**, but they differ in **when the target is decided**, **metadata discovery capability**, **signatures and type conversion**, **call interception scope**, **access permissions**, **errors**, **tooling/JIT optimization capability**, **initialization cost**, and **maintainability**.

**Governing rule:** choose the **simplest mechanism that satisfies the exact contract and actual point of variation**, then measure performance in a real workload when needed. Do not automatically replace every normal call with `MethodHandle` just because it sounds "close to the JVM", nor use reflection or proxy when a simple public method/interface already solves the requirement.

Learning objectives:

1. Distinguish "dynamic" in **call target** from "dynamic" in **name/signature/member metadata**.
2. Determine when **direct/interface** or **functional interface** is sufficient.
3. Determine when Reflection is actually needed for discovery, and when to transition from metadata to a cached `MethodHandle`.
4. Understand `MethodType`, `invokeExact`, receiver, boxing/unboxing, exceptions, and JPMS access.
5. Know when a proxy provides interception/cross-cutting benefits and the important limitations of JDK proxy.
6. Know how to **measure performance reliably** with benchmarks/JMH or profiling, without inferring a fixed ranking from a single `nanoTime`.
7. Use a Java 17+ example that **compiles and actually runs** to verify the mechanisms on the same business logic.

## 2. Quick decision by business question

Before choosing an API, answer the questions in order:

```text
Are the method and types known at coding time?
  |
  +-- Yes
  |     |
  |     +-- Only need to execute business logic?
  |     |      -> Direct call / via interface
  |     |
  |     +-- Want to pass a typed behavior/callback?
  |     |      -> Functional interface + lambda/method reference
  |     |
  |     +-- Want to intercept multiple methods of an interface
  |            with logging, auth, metrics, transaction ...?
  |            -> Manual decorator or JDK dynamic proxy
  |
  +-- No
        |
        +-- Need to inspect annotations, names, signatures, fields,
        |      or plugin types known at runtime?
        |      -> Core Reflection for discovery
        |
        +-- Need to invoke the discovered target many times, bind parameters,
               adapt types, or compose dynamic adapters?
               -> Normalized and reused Lookup + MethodHandle
```

**Note:** an architecture can use **multiple mechanisms in sequence**: reflection to discover members once, `MethodHandle` for the repeated call path, functional interface as the public API, and proxy for audit/authorization at the service boundary. These are not five mutually exclusive technologies.

### Architecture-level selection table

| Real problem | Initial choice | Why |
| --- | --- | --- |
| Calling `service.calculate(x)` known from source | Direct or interface dispatch | Clear contract, compiler type-checking, minimal code |
| Swapping an algorithm with a single callback or strategy | Functional interface | Behavior is a typed value; easy injection/testing |
| Finding a method by name/annotation at runtime | Reflection | Direct and comprehensive metadata API |
| Calling a discovered member on a hot path or composing call adapters | MethodHandle | Invocation has `MethodType`, easy to cache/compose |
| Adding logging/metrics/auth around every call of an interface | Decorator or JDK proxy | Provides a centralized interception point |
| Intercepting calls to a concrete class **without an interface** | Do not use JDK dynamic proxy as a direct solution | JDK `Proxy` creates implementations of interfaces, does not arbitrarily subclass classes |
| A stable public API whose backend changes | Interface + dependency injection; proxy only when cross-cutting is needed | The simpler approach remains clear |
| Plugins with completely unknown members beforehand | Reflection discovery, then consider handles | Metadata is only available at runtime |
| The goal is just "run faster" | Keep the current structure, measure/profile first | Avoid optimizing before there is a bottleneck |

## 3. Direct calls and interface calls: the default to prefer

Example:

```java
int direct = real.compute(3);

Operation service = real;
int throughInterface = service.compute(3);
```

This is an **illustrative snippet** in the program in section 10, with `RealOperation real` and `Operation` already declared.

- `real.compute(3)` has static receiver type `RealOperation`; bytecode may use `invokevirtual` with a class method reference.
- `service.compute(3)` has static receiver type `Operation`; bytecode typically uses `invokeinterface`.
- **Both still use dynamic dispatch for instance virtual/interface methods**: the runtime selects the implementation corresponding to the receiver. "Direct call" here means **the programmer knows the target contract and calls it with normal Java syntax**, not "the JVM always skips virtual dispatch".
- `javac` and the JVM check the method, parameters, and types according to normal Java rules.
- The JIT can inline, devirtualize, use type profiling, or optimize through interface dispatch if it sees sufficient stability. **There is no rule that an interface call is guaranteed to be slower than a concrete call** in all situations.

**Advantages:** readable syntax, clear stack traces/IDE refactoring, compile-time type checking, minimal setup, no need to manually handle `MethodType`, `InvocationTargetException`, or handlers.

**Limitations:** unsuitable if **member names and signatures are only known from runtime configuration** and there is no stable interface. Using a large number of `if/else` branches by method name may indicate a missing polymorphism model or the need for a registry/lookup.

### Calling a concrete class or an interface?

If the goal is long-term maintainability, many systems should **declare dependencies as interfaces** to swap implementations during testing or deployment, even though a call site may be a few nanoseconds slower or faster depending on the JIT. This is a **design choice**, not a fixed performance claim.

Do not create an interface for **every** class just for "architectural beauty". Use an interface when there is a meaningful contract: multiple implementations, plugin boundary, test seam, public SPI, or dependency separation. For purely internal and stable helpers, a normal concrete class/method may be simpler.

## 4. Functional interface: passing typed behavior instead of method names

A **functional interface** has exactly one abstract method according to Java rules (it may have `default`/`static` methods, and `Object` methods do not count in the usual way). A lambda/method reference can implement that contract:

```java
IntUnaryOperator operation = real::compute;
int result = operation.applyAsInt(3);
```

This is a **snippet in the context of the example in section 10**.

A functional interface is suitable when:

- The receiver only needs **one specific behavior**, such as a callback, predicate, transformer, strategy, or retry callback.
- The name/signature of the operation is **known at compile time**.
- You want to avoid exposing `Method`, `MethodHandle`, or `InvocationHandler` as an overly technical public contract.
- You want testability using a lambda `x -> x + 1` or method reference `service::compute`.
- You can use primitive-specialized interfaces to avoid boxing: `IntUnaryOperator`, `IntPredicate`, `ToIntFunction<T>`, `IntConsumer`, ...

Example in a pipeline:

```java
static int applyTwice(IntUnaryOperator operation, int value) {
    return operation.applyAsInt(operation.applyAsInt(value));
}
```

This is a **standalone illustrative method** if `import java.util.function.IntUnaryOperator;` is present.

**Advantages:** preserves a type-safe contract, minimal boilerplate; the implementation can be a lambda, method reference, or class. The programmer does not need to know whether the implementation is a generated lambda object or a wrapper.

**Limitations:**

- Cannot automatically discover an arbitrary method purely from a string name taken from config.
- Does not provide a list of all methods/fields/annotations of the receiver.
- For many operations or multiple cross-cutting concerns, a multi-method interface/service API and decorator/proxy may be more suitable than a collection of scattered callbacks.
- Generic `Function<Integer,Integer>` can incur boxing; use primitive specializations when the number of calls/allocations matters enough.
- Lambda captures can hold references to the receiver or other objects and extend their lifetimes; do not accidentally store callbacks in a global registry.

**Regarding performance:** the compiler may emit `invokedynamic` for the expression creating the lambda/method reference and the JVM can optimize it very well, but that does not mean **every `applyAsInt` call is an `invokedynamic` instruction**. In the Java 17 example below, the functional method call uses `invokeinterface`; `invokedynamic` appears when creating the method-reference object. Do not infer a fast/slow ranking from a single opcode.

## 5. Core Reflection: choose when you must understand and manipulate runtime metadata

If the name/signature or class structure only appears at runtime, Reflection is the most direct tool:

```java
Method method = Operation.class.getMethod("compute", int.class);
Object value = method.invoke(real, 3);
```

This is an **illustrative snippet**; it requires `import java.lang.reflect.Method;` and properly scoped variables.

`Method` allows reading `getName()`, `getParameterTypes()`, `getReturnType()`, annotations, modifiers, declaring class, generic type metadata... These APIs are especially useful for:

- Dependency injection/container scans.
- Serialization/ORM binding.
- Plugin discovery with types unknown at compile time.
- Annotation-based validation and reflective introspection.
- CLI/RPC/command dispatchers mapping configuration or metadata to a method.

Reflection **does not mean every member is accessible**. `getMethod` finds public members according to the contract; `getDeclaredMethod` finds directly declared members (including private ones), but **finding a Method object does not mean `Method.invoke` is permitted to be called**. Java access control and JPMS module exports/opens still apply. `setAccessible(true)` is not an absolute bypass when strong encapsulation forbids deep reflection.

### Costs to account for

- **Discovery**: finding methods, scanning annotations, checking signatures, handling errors; can incur significant cost if repeated on every request.
- **Invocation**: `Method.invoke(target,args)` uses varargs `Object...`; primitive arguments may be boxed and primitive results are typically boxed to be returned as `Object`.
- **Error handling**: exceptions thrown by the target method are wrapped in `InvocationTargetException`, requiring unwrapping to preserve the original error.
- **Access check**: normal Reflection checks permissions against the caller on invoke, except in cases where access checks have been validly suppressed according to the API.
- **JIT**: performance varies by JDK version, method stability, escape analysis, inlining, and code organization; there is no fixed overhead level.

**Principle:** perform `getMethod`/annotation discovery during the **setup phase**, storing the `Method`/schema mapping for subsequent uses. However, caching alone does not automatically solve boxing, exception, or access issues.

Do not write:

```java
for (...) {
    Method m = target.getClass().getMethod("compute", int.class);
    m.invoke(target, value);
}
```

on a hot path just because it is easy to code, if the method is actually stable. This is an **anti-pattern snippet**; the loop lacks concrete variables and is not a standalone Java program.

## 6. `MethodHandle`: when invocation needs typed adapters and dynamic composition

`MethodHandle` is a **created invocation reference object**, with an exact type `MethodType`. You typically use `Lookup` to obtain a handle:

```java
MethodHandle handle = MethodHandles.lookup().findVirtual(
        Operation.class,
        "compute",
        MethodType.methodType(int.class, int.class));
```

This is an **illustrative snippet** within the same class that has access to `Operation`.

For the instance method `int Operation.compute(int)`, the actual handle has type:

```text
(Operation,int)int
```

The **receiver** is the first parameter of the `MethodHandle` even though in the original Java method it is written before the dot. For example:

```java
int result = (int) handle.invokeExact((Operation) real, 3);
```

`invokeExact` requires the **static types of the arguments and return type at the call site to match `handle.type()` exactly**. In this example, the cast `(Operation) real` is necessary so the caller signature has a receiver of type `Operation`, and the cast `(int)` on the result specifies the return type as primitive `int`.

If `(Object) real` is passed into `invokeExact` itself, the Java source may still compile due to the signature-polymorphic method, but at runtime it will throw **`WrongMethodTypeException`** because the call-site type `(Object,int)int` does not equal `(Operation,int)int`.

### When to use?

- A member is resolved from runtime metadata but is called **very many times** after being found.
- A framework needs to compose adapters: `bindTo`, `asType`, `filterArguments`, `foldArguments`, `guardWithTest`, `dropArguments`, `insertArguments`, ...
- An explicit type signature is needed when building dynamic dispatch or a runtime DSL.
- You want to narrowly grant a **capability** to invoke a private member that an authorized `Lookup` created, instead of sharing the entire full-privilege `Lookup`.
- You need to integrate with other `java.lang.invoke` mechanisms, such as `CallSite`/`invokedynamic`; **however, simply calling `invokeExact` still does not mean the `invokedynamic` opcode**.

### Costs and limitations

- `Lookup.findVirtual`, `MethodType` construction, and adapter creation have a **setup cost**; do not repeat them every time on a hot path.
- `invokeExact` requires **exact types**; if `invoke` is used, conversions according to `asType` may occur. `invokeWithArguments(Object...)` is convenient for truly dynamic argument counts/types, but may incur varargs allocation, boxing, and adaptation.
- `findVirtual` can throw `NoSuchMethodException`/`IllegalAccessException`; Java module boundaries and lookup modes must still be respected.
- Validly created method handles can be invoked by a recipient even if they cannot access the private member themselves. **Do not inadvertently share a private handle or full `Lookup` with untrusted code.**
- Typed handles **do not replace Reflection metadata APIs** when you need to enumerate annotations, fields, or constructors; you can use Reflection to discover and then create a handle once.

### `bindTo` when you want to remove the receiver from the call site

```java
MethodHandle bound = handle.bindTo(real);
int result = (int) bound.invokeExact(3);
```

This is an **illustrative snippet** in the example; for a target handle `(Operation,int)int`, the bound handle will have type `(int)int`. Holding `bound` retains a reference to `real`; memory/caching must be considered if the receiver is a short-lived object or belongs to a plugin class loader that needs to be unloaded.

**Do not claim `MethodHandle` is always faster than `Method.invoke`.** Java 17 differs from later JDKs in implementation details; HotSpot can optimize direct, lambda, reflective, and handle paths depending on the call site. You must measure with the corresponding version, type stability, and workload.

## 7. Dynamic proxy: when you need to intercept calls to an interface

A JDK dynamic proxy is an object implementing one or more interfaces passed to `Proxy.newProxyInstance`. It forwards interface method calls to an `InvocationHandler`:

```java
Operation proxy = (Operation) Proxy.newProxyInstance(
        Operation.class.getClassLoader(),
        new Class<?>[] { Operation.class },
        (p, method, args) -> method.invoke(real, args));
```

This is an **illustrative snippet**, without handling `InvocationTargetException`, Object methods, or policy yet. The full runnable example in section 10 includes those additions.

Use when:

- You need logging, metrics, tracing, retry, authorization, or transaction boundaries **for multiple methods belonging to an interface**.
- You want the interception code in a single handler rather than writing a separate wrapper for each signature.
- The application's public contract is already interface-based.
- A framework or integration point accepts an interface object that you provide.

### Understanding the receiver properly

- `proxy` in `InvocationHandler.invoke(proxy, method, args)` is the **proxy object** that the client just called.
- `real`/`target` is the **real implementation**.
- When delegating, use `method.invoke(real,args)`, **not** `method.invoke(proxy,args)`, because calling on the proxy re-enters the same handler and can cause **infinite recursion**.
- For exceptions thrown by the target method, `Method.invoke` wraps them in `InvocationTargetException`. The handler can unwrap it so the caller receives the **original exception** if compatible with the contract.

**Self-invocation bypass:** if the target executes `this.anotherMethod()` from inside `real.compute(...)`, that internal call does not automatically go through the proxy, because `this` is the target. This is very important if the proxy is responsible for authorization, transactions, or metrics.

### Special methods/limitations

- JDK proxy **only implements interfaces**; it does not automatically subclass a concrete class just because that class has public methods.
- `equals(Object)`, `hashCode()`, and `toString()` also go through the handler. If the handler logs by concatenating `proxy` into a string (triggering `toString`), it may inadvertently re-enter.
- Default interface methods require an explicit choice: delegate on the target or use `InvocationHandler.invokeDefault(...)` to call the default implementation on the proxy (Java 16+). The two strategies may differ regarding nested interception.
- The handler receives `Object[] args` (which may be `null` if the method has no arguments), incurring boxing/varargs overhead in many cases.
- Checked exceptions not declared by the interface may be wrapped by JDK proxy into `UndeclaredThrowableException`; do not carelessly use `catch(Exception)` to erase the cause.
- You must control the class loader, module, interface visibility, and lifecycle of the proxy/handler/target.
- Handler state shared across threads must adhere to thread safety when the proxy is called concurrently.

### Proxy or manual decorator?

If there are only a few stable methods and clear type safety, a **manual decorator** is often easier to read and debug. Dynamic proxy is more suitable when many interfaces/methods share the same interceptor policy, or when a framework generates wrappers in bulk from metadata.

You do not have to use dynamic proxy just because you need logging; sometimes logging directly in the application service or using a static decorator is sufficient and more transparent.

## 8. Comparison table by cost, types, adaptability, and risks

| Criterion | Direct/interface | Functional interface | Reflection | MethodHandle | JDK dynamic proxy |
| --- | --- | --- | --- | --- | --- |
| Target/contract known at compile time | Usually yes | Yes for the callback signature | Not required | Not required | Interface must be known/visible |
| Type-safe API at call site | **Yes** | **Yes** | Args/return via `Object[]`/`Object` | Yes if types are exact and `invokeExact` is accurate | Yes at client interface; dynamic inside handler |
| Discovering methods/annotations | Not its purpose | Not its purpose | **Strong** | Does not replace Reflection metadata discovery | Handler receives `Method` on each interception |
| Runtime signature composition/adaptation | Plain Java code | Lambda composition by interface | Not a strength | **Strong** (`asType`, `filter*`, `guardWithTest`...) | Changes intercept logic, not interface signature |
| Initialization cost | Very small | May create/hold functional object | Finding `Method`, access setup | `Lookup`, handle/adapters | Creating proxy class/instance and handler |
| Per-call cost | Depends on JIT/dispatch | Depends on capture, JIT, and interface | Reflection + conversions | Depends on handle graph, adaptation, and JIT | Interception + handler + delegation |
| Primitive boxing | Can be avoided | Can be avoided with primitive-specialized interfaces | Often boxes at API boundary | `invokeExact` can preserve primitives | Handler `Object[]` may box |
| Target exception handling | Normal Java | Java interface contract | `InvocationTargetException` wrapper | Target exception propagates as-is | Handler can unwrap; checked exception constraints |
| Access control | Java/JPMS compile/link | Java/JPMS at lambda/callback creation | Reflection access & `setAccessible` restrictions | Lookup access at handle creation | Only intercepts methods of visible interfaces |
| Cross-cutting across many methods | Write wrapper/decorator | Separate per behavior | Framework can dispatch via reflection | Build adapter graph | **Main strength** |
| Ease of debugging/refactoring | Usually easiest | Easy if contract is concise | String names/signatures fail at runtime | Must understand `MethodType` | Stack traces and reentrancy are more complex |
| Needed when external config selects member by string | Does not handle itself | Does not handle itself | **Yes** | After discovery/lookup | Does not solve metadata discovery alone |

**The cost entries above are a qualitative model, not a benchmark ranking table.** The JIT can inline or hoist setup, and runtime context can make differences much smaller or larger than intuition suggests; actual data decides.

## 9. Designing a fair test: one method, multiple call paths

We need to keep the **same business target**:

```java
int compute(int value) {
    if (value < 0) throw new IllegalArgumentException("negative");
    return value * 2 + 2;
}
```

This is an **illustrative snippet**; the full runnable implementation is in the next section.

If each strategy called a different method, a benchmark/correctness test would not be comparing the same work. Therefore, the example below uses **one `RealOperation`** and goes through multiple mechanisms to observe:

- All return the same result for `3`.
- Reflection and the proxy handler have an `InvocationTargetException` path.
- MethodHandle has a typed receiver and demonstrates `WrongMethodTypeException`.
- Proxy intercepts exactly once for a successful call; no recursion occurs.
- `bindTo` removes the receiver from the handle's type.
- The number of real method executions remains countable.
- `Proxy` handles `equals` and `toString` without self-reentrancy.

**This example tests correctness/semantics, NOT speed.** Read the output lines to distinguish the mechanisms rather than inferring nanosecond timings.

## 10. Standalone runnable Java 17+ program: six call paths to the same business logic

Save the file with the exact name **`DispatchChoiceDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntUnaryOperator;

public final class DispatchChoiceDemo {
    interface Operation {
        int compute(int value);
    }

    static final class RealOperation implements Operation {
        int calls;

        @Override
        public int compute(int value) {
            calls++;
            if (value < 0) {
                throw new IllegalArgumentException("negative");
            }
            return value * 2 + 2;
        }
    }

    public static void main(String[] args) throws Throwable {
        RealOperation real = new RealOperation();
        Operation asInterface = real;
        IntUnaryOperator function = real::compute;

        Method method = Operation.class.getMethod("compute", int.class);

        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Operation.class, "compute",
                MethodType.methodType(int.class, int.class));
        MethodHandle bound = handle.bindTo(real);

        AtomicInteger intercepted = new AtomicInteger();
        Operation proxy = (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] { Operation.class },
                (p, m, params) -> {
                    if (m.getDeclaringClass() == Object.class) {
                        return switch (m.getName()) {
                            case "equals" -> p == params[0];
                            case "hashCode" -> System.identityHashCode(p);
                            case "toString" -> "OperationProxy";
                            default -> throw new UnsupportedOperationException(
                                    m.getName());
                        };
                    }

                    intercepted.incrementAndGet();

                    try {
                        // CORRECT: target is real, NOT p (proxy).
                        return m.invoke(real, params);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });

        System.out.println("direct=" + real.compute(3));
        System.out.println("interface=" + asInterface.compute(3));
        System.out.println("functional=" + function.applyAsInt(3));
        System.out.println("reflection="
                + ((Integer) method.invoke(real, 3)).intValue());
        System.out.println("handle="
                + (int) handle.invokeExact((Operation) real, 3));
        System.out.println("boundHandle="
                + (int) bound.invokeExact(3));
        System.out.println("proxy=" + proxy.compute(3));

        System.out.println("realCalls=" + real.calls);
        System.out.println("intercepted=" + intercepted.get());
        System.out.println("handleTypeMatches="
                + handle.type().equals(MethodType.methodType(
                        int.class, Operation.class, int.class)));
        System.out.println("boundTypeMatches="
                + bound.type().equals(MethodType.methodType(
                        int.class, int.class)));
        System.out.println("proxyEqualsSelf=" + proxy.equals(proxy));
        System.out.println("proxyToString=" + proxy.toString());

        try {
            method.invoke(real, -1);
        } catch (InvocationTargetException ex) {
            System.out.println("reflectionException="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            proxy.compute(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("proxyException="
                    + ex.getClass().getSimpleName());
        }

        try {
            int ignored =
                    (int) handle.invokeExact((Operation) real, -1);
            System.out.println(ignored);
        } catch (IllegalArgumentException ex) {
            System.out.println("handleException="
                    + ex.getClass().getSimpleName());
        }

        try {
            int ignored =
                    (int) handle.invokeExact((Object) real, 3);
            System.out.println(ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongHandleType=detected");
        }

        System.out.println("realCallsFinal=" + real.calls);
        System.out.println("interceptedFinal=" + intercepted.get());
    }
}
```

### 10.1. Compiling and running

Using **JDK 17+**, from the directory containing the file:

```bash
javac --release 17 DispatchChoiceDemo.java
java DispatchChoiceDemo
```

**Verified exact stdout:**

```text
direct=8
interface=8
functional=8
reflection=8
handle=8
boundHandle=8
proxy=8
realCalls=7
intercepted=1
handleTypeMatches=true
boundTypeMatches=true
proxyEqualsSelf=true
proxyToString=OperationProxy
reflectionException=IllegalArgumentException
proxyException=IllegalArgumentException
handleException=IllegalArgumentException
wrongHandleType=detected
realCallsFinal=10
interceptedFinal=2
```

The example compiled successfully with `javac --release 17` and ran with Java; no external libraries are required.

### 10.2. Why do all the first lines return `8`?

All call paths reach `RealOperation.compute(3)`. With the expression `3 * 2 + 2`, the result is `8`:

- `direct`: Java call on a concrete `RealOperation` variable.
- `interface`: Java call on `Operation`.
- `functional`: `IntUnaryOperator` holding the method reference `real::compute`.
- `reflection`: `Method` representing `Operation.compute`, invoked on `real`; the primitive `int` result is boxed to `Integer`.
- `handle`: `MethodHandle` to the interface method, with receiver `(Operation)real`.
- `boundHandle`: `bindTo(real)` has bound the receiver; the caller only passes `int`.
- `proxy`: the handler receives an interface call, then `Method.invoke(real,params)` runs the same real method.

Because there are **seven successful calls** to the target (counting `boundHandle` separately), `realCalls=7`. The proxy only participates in **one** call up to this point, so `intercepted=1`.

### 10.3. Why is `handleTypeMatches=true`?

`Operation.compute(int)` is an instance method. `MethodHandles.lookup().findVirtual(Operation.class, "compute", MethodType.methodType(int.class,int.class))` looks up the member signature `(int)int`, but the returned handle has the **receiver** prepended, becoming `(Operation,int)int`.

`bindTo(real)` fixes the receiver parameter, so `bound.type()` becomes `(int)int`.

If you want to use a handle in a generic framework, record the **actual `MethodType`** rather than only the declared Java method signature.

### 10.4. Why does Reflection wrap exceptions, while proxy and handle do not?

When calling `compute(-1)`, the real method throws `IllegalArgumentException("negative")`:

- `Method.invoke(real,-1)` reflects the executed method, so it wraps the target exception in `InvocationTargetException`. The demo catches the wrapper and prints **the class name of the cause**.
- The proxy handler catches the wrapper thrown by `m.invoke(real,params)` itself and **rethrows the cause**, so the caller sees the original `IllegalArgumentException`.
- `MethodHandle.invokeExact` propagates exceptions thrown by the target without automatically wrapping them in `InvocationTargetException`.

None of the three mechanisms **makes the business exception disappear**. The difference lies in the wrapping path and the API contract.

### 10.5. Why does `(Object)real` throw `WrongMethodTypeException`?

The line:

```java
(int) handle.invokeExact((Object) real, 3)
```

gives the call site a receiver of type `Object`, whereas the handle expects receiver `Operation`. `invokeExact` requires an **exact match** and does not automatically cast `Object` to `Operation`, even though the actual runtime object is a `RealOperation`.

`wrongHandleType=detected` proves the type check happens **before** the business method is called, so `realCallsFinal=10` instead of 11: the three `compute(-1)` calls incremented the counter from 7 to 10; the wrong-type call did not execute the target.

### 10.6. Proxy does not intercept all calls to the real object

`interceptedFinal=2` because the proxy handler only received two `proxy.compute(...)` calls: one successful (`3`), and one throwing an error (`-1`). Calls via `real`, `asInterface`, lambda, reflection, and method handle **do not automatically go through the proxy**.

This is an important fact if the proxy is enforcing security or creating a transaction boundary: **anyone holding a reference to the real target can call it directly outside the proxy**. To have a reliable policy, you must design object ownership, API boundaries, and avoid inadvertently leaking the raw target to places that require interception.

`proxy.equals(proxy)` and `proxy.toString()` also enter the handler, but the demo chooses a separate **identity policy** and does not increment the business counter. This avoids confusing Object methods with `compute` and avoids recursion caused by `toString` in logging.

## 11. Inspecting bytecode: "API name" does not simply determine the opcode

After compiling, run:

```bash
javap -c -p DispatchChoiceDemo
```

In a compilation with Java 17, the disassembly shows different categories:

| Source expression | Observable opcode/operation |
| --- | --- |
| `real.compute(3)` | `invokevirtual` to `RealOperation.compute` |
| `asInterface.compute(3)` | `invokeinterface` to `Operation.compute` |
| `function.applyAsInt(3)` | `invokeinterface` to `IntUnaryOperator.applyAsInt` |
| `method.invoke(real,3)` | `invokevirtual` to `java.lang.reflect.Method.invoke` |
| `handle.invokeExact(...)` | Signature-polymorphic `invokevirtual` to `MethodHandle.invokeExact` |
| `proxy.compute(3)` | Client call to interface is typically `invokeinterface`; generated proxy/handler performs interception |
| Expression `real::compute` | Compiler may emit **`invokedynamic`** to create the functional object |
| Lambda expression for `InvocationHandler` | Compiler may emit `invokedynamic` to create the handler |
| Runtime string concatenation in logging | Java 17 `javac` typically emits `invokedynamic` via `StringConcatFactory` |

**Do not infer:** seeing `invokedynamic` in the disassembly **does not prove** that `MethodHandle.invokeExact` calls use the `invokedynamic` opcode. `invokeExact` is a signature-polymorphic method, but calls from Java source still use `invokevirtual`, per the Java SE 17 API.

**Nor conclude "direct is always faster than interface" from two opcodes.** The JIT can devirtualize and inline the same target; initial bytecode is not the final optimized machine code. Bytecode is useful for understanding mechanisms and spotting adapter/object allocation paths, but it is not a benchmark.

## 12. Comparing **setup** cost and **per-call** cost

A rough model, for thinking purposes only:

\[
T_{\text{total}} \approx T_{\text{setup}} + N \times T_{\text{call path}} + T_{\text{business}} + T_{\text{memory/GC/I/O}}
\]

This is a **qualitative model**, not an exact measurement formula for every workload. In practice, JIT compilation, code layout, branches, allocations, contention, and GC change costs over time.

| Mechanism | One-time setup | Things that may happen per call |
| --- | --- | --- |
| Direct/interface | Normal object creation or dependency injection | JVM dispatch; may be inlined |
| Functional interface | Create method reference/lambda; may capture receiver | Invoke SAM method; may be inlined; boxing if using generic wrappers |
| Reflection | `getMethod`/`getDeclaredMethod`, configure access | Varargs `Object[]`, boxing/unboxing, access/invocation machinery, wrapper for target exceptions |
| MethodHandle | `Lookup.find*`, `MethodType`, create/bind/adapt handle | Exact invoke or conversion/adapter graph; may be inlined if handle/call site is stable enough |
| JDK proxy | Generate proxy class (when needed), instance, handler | Proxy method → handler → policy → delegate; `Method`/`Object[]`/boxing depending on case |

When **N is very small**, setup overhead can dominate: using reflection lookup or creating a proxy per request can be worse than a simple direct call. When **N is very large**, setup is amortized; what matters more is call path cost, target stability, boxing, cache misses, allocation, and JIT.

### Examples comparing choices by frequency

- **A CLI tool calling a method from config once**: Reflection after validating metadata can be completely reasonable; building an entire handle graph framework may not pay off.
- **A serializer processing millions of fields**: discover annotations/field mappings once, cache the schema, and test accessors with appropriate performance; MethodHandle/VarHandle may be worth trying.
- **An API service with 10 ms DB/network requests**: dispatch overhead measured in ns or µs may not determine p99 latency; do not optimize the wrong layer.
- **A parser/interpreter executing hundreds of millions of steps in a CPU loop**: typed call sites, primitive specializations, and adapter structure can become a bottleneck worth measuring.
- **A logging/metrics system needing to intercept hundreds of service methods**: dynamic proxy helps reduce boilerplate, though complexity and workload still need evaluation.

## 13. Why benchmarking with `System.nanoTime()` easily leads to wrong conclusions

A short timing loop like:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    target.compute(i);
}
long elapsed = System.nanoTime() - start;
```

This is an **illustrative snippet insufficient for benchmark conclusions**. The Java code above can be optimized by the JIT differently from production paths; if the result is unused, dead-code elimination can alter the executed work.

Common biases:

- **Cold vs warmed JVM**: JIT has not compiled or type profiles are not yet stable at the start; running multiple times changes results.
- **Dead-code elimination**: unused results allow the JVM to eliminate pure computations entirely.
- **Constant folding**: fixed inputs allow the compiler/JIT to precompute results.
- **Escape analysis**: allocations may be eliminated, or reappear when a new wrapper/context is added.
- **Branch prediction**: a branch taken 100% of the time differs from real input distributions.
- **Benchmark method too small**: harness/timer overhead and OS scheduling dominate.
- **Dynamic targets**: a monomorphic call site differs from polymorphic/megamorphic ones.
- **GC/allocations**: proxy and reflection may create temporary objects depending on version/call shape; looking only at `ns/op` ignores `B/op`.
- **Locking/threads**: singleton handlers or shared caches can create contention invisible to a single-threaded benchmark.
- **Tiered compilation, inlining, CPU frequency, JDK flags, and container limits**: not equivalent across dev/prod machines.
- **Benchmarks that add logging and `println` inside the loop**: I/O dominates dispatch overhead; results no longer reflect invocation cost.

**Do not publish a table like "direct = 1 ns, lambda = 2 ns, reflection = 20 ns, handle = 3 ns, proxy = 50 ns" without benchmark source, configuration, and workload.** Those numbers are not fixed properties of Java APIs.

## 14. Using JMH and measuring throughput, allocation, and realistic scenarios

**JMH (Java Microbenchmark Harness)** developed by OpenJDK is the standard tool for building microbenchmarks on the JVM, featuring warmup, measurement, forks, state management, and avoidance of several optimization traps. When a decision depends on small differences between reflection/handle/proxy, prefer JMH over manual loops.

Measurement process:

1. Create a dedicated benchmark, configured with the exact production Java version.
2. Use **the same target behavior and same data** for all variants.
3. **Separate setup** (`Method` lookup, `MethodHandle` creation, proxy construction) from the **call-path benchmark** if comparing steady-state costs.
4. Create a separate **setup cost** benchmark group if objects are created per request.
5. Avoid constant folding: vary inputs reasonably, consume outputs or return results that JMH handles.
6. Measure p50/p95/p99 in an integration workload as well if the goal involves latency, along with **allocation rate** and GC/CPU.
7. Include warmup/measurement iterations and multiple forks to reduce effects from JIT/class loading/previous runs.
8. Verify output and exception behavior **before** measuring speed.
9. Compare overhead against actual work; if DB/I/O or business logic consumes most of the latency, choose the maintainable design first.
10. Document the full environment: JDK build, JVM flags, hardware, OS, container CPU/memory, thread count, data distribution, and margin of error.

### Annotated JMH skeleton — requires external libraries

The following code is an **illustrative skeleton** showing how to separate setup from the measured path. It **does not run with only the JDK**, as it requires the `jmh-core` dependency, `jmh-generator-annprocess` annotation processor, and a properly built/packaged JMH project. A runnable example with no external library dependencies is already in section 10.

```java
package demo.bench;

import java.util.concurrent.TimeUnit;
import java.util.function.IntUnaryOperator;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class DispatchBench {
    interface Op { int compute(int x); }

    static final class Target implements Op {
        public int compute(int x) { return x * 3 + 1; }
    }

    final Target target = new Target();
    final Op viaInterface = target;
    final IntUnaryOperator function = target::compute;

    Method reflective;
    MethodHandle handle;
    Op proxy;
    int sequence;

    @Setup(Level.Trial)
    public void prepare() throws Throwable {
        reflective = Op.class.getMethod("compute", int.class);
        handle = MethodHandles.lookup().findVirtual(
                Op.class, "compute",
                MethodType.methodType(int.class, int.class));
        proxy = (Op) Proxy.newProxyInstance(
                Op.class.getClassLoader(),
                new Class<?>[] { Op.class },
                (p, method, args) -> method.invoke(target, args));
    }

    private int next() { return sequence++ & 1023; }

    @Benchmark public int direct() {
        return target.compute(next());
    }

    @Benchmark public int viaInterface() {
        return viaInterface.compute(next());
    }

    @Benchmark public int functional() {
        return function.applyAsInt(next());
    }

    @Benchmark public int reflection() throws Throwable {
        return ((Integer) reflective.invoke(target, next())).intValue();
    }

    @Benchmark public int handle() throws Throwable {
        return (int) handle.invokeExact((Op) target, next());
    }

    @Benchmark public int proxy() {
        return proxy.compute(next());
    }
}
```

This is a **benchmark skeleton**; if you want to actually run it, create a project using the archetype/configuration guided in [OpenJDK JMH](https://github.com/openjdk/jmh), declare dependencies/annotation processing, and place package `demo.bench` at the right path. Do not attach fake stdout or scores because this snippet **has not been run with JMH** in this article.

**Comparison limitations of the skeleton:** each method has a different call site, type stability, and inlining; `next()` varies the input, yet the target is still very small arithmetic. JMH results, if any, only apply to **this model**, and do not prove overhead in a full-stack framework or when reflection performs parsing/lookup per request.

To measure **cold startup** or **proxy creation**, write a separate setup benchmark; do not infer setup cost from steady-state call numbers. You can use `-prof gc` to observe allocations in a properly packaged benchmark.

## 15. Deciding based on profiler and contract, not just microbenchmarks

Before optimizing dispatch, examine the application-level profile:

- Where is CPU time spent? Business logic, regex/parsing, JSON, database client, encryption, or invocation?
- Are there millions of repeated method lookups?
- Is there heavy boxing/allocation of object arrays at the Reflection/proxy boundary?
- Are too many generated proxy classes/handlers increasing class loading or metaspace?
- Is low-latency processing under load and multiple threads required?
- Does the call path have a stable target or constantly changing ones?
- Is the exception path frequent? Throwing exceptions is more expensive than a normal successful call and can generate stack traces.
- Is there memory retention caused by caching `Method`, `MethodHandle`, bound handles, or `InvocationHandler` holding onto class loaders/plugin classes?

**Improvements often more beneficial than switching APIs:**

- Move Reflection metadata scanning out of loops.
- Cache schema/method mappings with keys matching class/class loader identity.
- Use `IntUnaryOperator` instead of `Function<Integer,Integer>` on genuinely primitive hot paths.
- Reduce the number of interceptions/logs on critical paths.
- Avoid creating new proxies/handles per request if the contract and target are the same.
- Improve algorithms or eliminate network/DB round trips before shaving ns-level dispatch.
- Reduce contention in shared interceptors/caches.

Switching `Method.invoke` to `MethodHandle.invokeExact` may improve, stay the same, or worsen performance depending on how you create/adapt handles, inlining capability, and the JDK. If benchmarks do not prove a significant benefit, do not change code just for a "newer API".

## 16. Reflection discovery then converting to a handle: a reasonable pipeline

A framework can have two phases:

```text
Setup/registration phase:
  scan class / annotation / config
       |
       v
  Method / member metadata
       |
       v
  verify signature, permissions, plugin policy
       |
       v
  MethodHandles.Lookup.unreflect(method) or find*
       |
       v
  optional asType, bindTo, filterArguments, ...
       |
       v
  cache an invoker with a standard contract
       |
       v
Hot path phase:
  validate input -> invoke invoker -> business result
```

**`Lookup.unreflect(method)` is not a tool to automatically bypass all private permissions**: handle creation must still satisfy the access rules of the Lookup/reflective object, including JPMS/module openness where applicable.

You must choose the **right cache key**. If an application has multiple class loaders, two classes with the same binary name **do not necessarily have the same class identity**. Caching solely by `"com.example.Plugin"` can invoke the wrong class/loader, retain references too long, or cause type/reflective access errors. `Class<?>` identity and module/loader context must be considered.

Caches also need **eviction** if plugins unload/reload: `Method`, `MethodHandle`, and `Lookup` can hold references to the declaring class and class loader, preventing old code from unloading. For dynamic runtime systems, memory/metaspace cost can be more important than a tiny improvement in call latency.

It is **not mandatory** to convert every `Method` into a handle. If a plugin action executes rarely, Reflection with cached metadata and clear error handling can be a reasonable, easy-to-debug solution.

## 17. Checking signatures: from `Object` to `MethodType` without losing the contract

With Reflection:

```java
Method m = Operation.class.getMethod("compute", int.class);
Object out = m.invoke(real, 3);
int result = ((Integer) out).intValue();
```

With MethodHandle:

```java
MethodHandle mh = MethodHandles.lookup().findVirtual(
        Operation.class, "compute",
        MethodType.methodType(int.class, int.class));
int result = (int) mh.invokeExact((Operation) real, 3);
```

Both snippets are **standalone illustrative code**, requiring imports and definitions as in section 10.

Reflection provides a generic `Object` return, which may box primitives. With MethodHandle, the signature **has explicit primitive `int` and receiver `Operation` types**; `invokeExact` will not auto-box or widen arguments. `invoke` allows conversions supported by `asType`, though that does not mean every type can be converted.

### If the system uses a generic adapter

A framework receiving `Object receiver` and `Object[] args` may want to normalize the handle to a generic contract instead of using `invokeExact` directly with runtime types unknown at compile time. You can consider `asType`, `asSpreader`, `asCollector`, `invokeWithArguments`, or a functional interface wrapper.

However, **each layer of conversion/adaptation** can add cost and make debugging harder; if you end up boxing everything into Object arrays and converting on every call, the advantage you expected from primitive `MethodHandle` may be negated.

Another option is to **generate code/adapters with explicit static types** during setup so consumers call normally through an interface. Thus, MethodHandles and functional interfaces **can complement each other**, rather than completely replacing one another.

## 18. Access permissions and module boundaries matter more than a few nanoseconds

### 18.1. Direct/interface

Java source compiles according to visibility/method signature. When running in JPMS, module readability and `exports` still determine whether public APIs are accessible. Do not fix design issues by indiscriminately opening private packages just to call a method.

### 18.2. Reflection

`getDeclaredMethod` can find private metadata, but `Method.invoke` is subject to access checks unless checks are validly suppressed. `setAccessible(true)`/`trySetAccessible()` are constrained by module access/open packages; code must not assume every private field/method is open.

### 18.3. MethodHandles.Lookup

`MethodHandles.lookup()` is bound to **the actual class calling lookup**. `findVirtual`/`findStatic` perform access checks when **creating the handle**. Once a valid handle is obtained, the recipient can invoke it even if they do not have sufficient permissions to create a similar handle themselves. Therefore, a private MethodHandle is a **capability**, while a full-privilege `Lookup` can grant permission to create further handles within its allowed scope.

**Do not expose a full lookup through a public API just to call one method.** Provide a public interface or a controlled handle instead. You must check `reads`, `exports`, `opens`, and `privateLookupIn` conditions when crossing module boundaries; do not "patch" with `--add-opens` flags in production without a design reason.

### 18.4. Proxy

A proxy can check permissions at the **entrypoint**:

```java
if (!authorization.canCall(principal, method)) {
    throw new SecurityException("Denied");
}
return method.invoke(target, args);
```

This is **illustrative code**; `principal`, `method`, `target`, and `authorization` must be available. It does not by itself create a solid security boundary if other code still holds the raw `target` or the target calls internal methods on itself via `this`.

**Proxy does not replace authorization at the service/domain boundary** when other access paths exist. If security decisions change per request, ensure every path needing protection actually runs through the check, rather than relying on a cache/handle/callback that bypassed the policy.

## 19. Comparing exceptions and diagnosability

| Mechanism | Wrong member/insufficient access | Target throws exception | Wrong call-site type |
| --- | --- | --- | --- |
| Direct/interface | Compile errors or linkage/access errors depending on situation | Original exception | Mostly detected at compile time |
| Functional interface | Target signature mismatch usually fails at compile time | Original exception per SAM contract | Compile-time type checking |
| Reflection | `NoSuchMethodException`, `IllegalAccessException`, or JPMS access restrictions | **`InvocationTargetException`** containing cause | `IllegalArgumentException` for wrong args/receiver, `ClassCastException` when caller casts result |
| MethodHandle | `NoSuchMethodException`/`IllegalAccessException` when Lookup creates handle | Original exception propagates through invocation | **`WrongMethodTypeException`** or conversion-related errors |
| Dynamic proxy | Interface/classloader/proxy creation errors | Handler can unwrap or re-wrap | Client is type-safe by interface; wrong type/return in handler may fail at runtime |

Some practical debugging points:

- Do not catch all `Throwable` and swallow errors just because `MethodHandle.invokeExact` declares `throws Throwable`.
- When Reflection returns `InvocationTargetException`, **inspect `getCause()`** to see the business exception.
- With JDK proxy, if a checked exception is not declared by the interface method, you may receive `UndeclaredThrowableException`; avoid leaking unnecessary wrappers.
- With `WrongMethodTypeException`, check **`handle.type()` and static types at the call site**, not just the actual class of the runtime object.
- With proxy recursion, the stack trace may repeat `InvocationHandler.invoke → Method.invoke → proxy method` continuously; check `proxy` vs `target` receiver.
- With multiple class loaders, a `ClassCastException` despite identical class names may be due to **different class identities**.

Clearly classify **setup/discovery** errors, **invoke/adaptation** errors, and **business execution** errors. Switching invocation tools often changes the kind of wrapper exception the application must handle.

## 20. Cases with multiple overloads or changing signatures

Suppose a class has:

```java
int convert(int input);
int convert(long input);
String convert(String input);
```

These are **three illustrative declarations** inside a class; not a standalone program.

When source code knows static types, `javac` resolves overloads according to Java overload resolution. With Reflection, you must select the **exact list of parameter types** when calling `getMethod`/`getDeclaredMethod`, and handle the expected return type. With MethodHandles, `MethodType.methodType(returnType, parameters...)` is part of the lookup contract; wrong return type or parameter types can cause `findVirtual` to throw `NoSuchMethodException`.

**Avoid calling `getMethods()` and taking the first method with a matching name**: overloads and different declaring classes can cause wrong dispatch. If config/plugin metadata provides a runtime signature, normalize **name + parameter types + return type + access policy**.

A functional interface is suitable if you only want to choose an implementation for **one specific signature**; if plugins allow actions that differ completely in parameter count/types, you need a generic contract or registry adapter at the setup layer.

Proxy automatically receives the `Method` object in the handler for each interface call, so it can distinguish overloads by signature. Do not switch solely on `method.getName()` when methods share the same name with different parameters.

## 21. Common design scenarios

### 21.1. Simple strategy for pricing/validation

**Prefer:** functional interface or strategy interface. A typed callback is sufficient data; no reflection/proxy is needed.

```java
IntPredicate validQuantity = count -> count >= 0;
```

This is an **illustrative snippet** with `import java.util.function.IntPredicate;`. It avoids the boxing of `Predicate<Integer>` on primitive hot paths. If the strategy needs multiple methods or its own state/lifecycle, use a meaningful interface.

### 21.2. Annotation-driven validation/serialization

**Prefer:** reflection discovery at startup, cache mappings. If profiling shows invocation in a hot loop is a bottleneck, create a `MethodHandle`/`VarHandle` or accessor to benchmark. Do not reflection-scan every field for every JSON object.

### 21.3. RPC dispatcher receiving method names from HTTP/gRPC metadata

**Prefer:** a validated registry at startup, explicit allowlist, mapping operation keys to methods/typed handlers. Reflection/handles can be used **internally**, but user requests **must not become arbitrary private method names**. Validate arguments, authorization, and schema before invoking.

### 21.4. Metrics/tracing for many service methods

**Prefer:** wrapper/decorator or JDK proxy if interfaces fit. If the backend is called without going through the proxy, metrics/interceptors will not see those calls. For target self-invocation, it also does not intercept automatically. If you need to intercept concrete classes without interfaces, you may consider bytecode generation/AOP frameworks with their own mechanisms, but understand proxy vs weaving.

### 21.5. Plugin engine loading classes by name from JARs

**Prefer:** interface/SPI contract if possible; reflection when member discovery must be dynamic; cache handles after validating signatures. Select the exact class loader, track references to support unload/reload. Do not store a global strong cache containing `MethodHandle`s pointing to retired plugin loaders.

### 21.6. Interpreter/DSL needing to change call structure at runtime

**Prefer:** typed handle graph and combinators if they genuinely simplify the interpreter and have been measured. `guardWithTest`, `filterArguments`, `foldArguments`, `asType` can be composed, though the code can be harder to maintain than a simple interpreter loop. Profiling decides.

### 21.7. Scheduled reporting job, only a few hundred calls/day

**Prefer:** the easiest-to-understand solution. No need for `MethodHandle` and JMH just to replace a known public method call. Optimizing DB queries, retries, error messages, and maintainability is usually more valuable.

## 22. Anti-patterns that often make systems more complex or slower

### 22.1. Re-running reflection lookup on every request

```java
Method m = target.getClass().getMethod("compute", int.class);
return m.invoke(target, value);
```

This is a **code snippet inside a method with return type `Object` and appropriate exception declarations**, not standalone. If the signature does not change, resolve/cache `Method` during setup instead of repeating discovery.

### 22.2. Creating a new handle and adapter for every element

```java
MethodHandle mh = MethodHandles.lookup().findVirtual(
        Operation.class, "compute",
        MethodType.methodType(int.class, int.class));
return (int) mh.invokeExact((Operation) receiver, value);
```

This snippet is an **illustrative fragment**; it can be valid, but should not by default be repeated inside a hot loop. Cache the handle/adapter when the contract is stable. **Do not** cache bound handles long-term if the receiver is supposed to live only for a single request or tenant.

### 22.3. Using `Function<Integer,Integer>` for primitive hot paths without measuring boxing

```java
Function<Integer, Integer> f = x -> x + 1;
```

This is an **illustrative snippet**. If the data is `int`, using `IntUnaryOperator` can avoid some boxing. However, the JIT can scalar-replace/eliminate allocations in some situations; real benchmarking still matters.

### 22.4. Proxy calling back into itself

```java
InvocationHandler handler = (proxy, method, args) ->
        method.invoke(proxy, args); // WRONG if you want to delegate to target
```

This is an **anti-pattern**, not runnable. It re-enters the handler and can become infinite recursion. Use the real target, unwrap `InvocationTargetException`, and choose a clear policy for Object/default methods.

### 22.5. Using a proxy as a security gate while leaking the raw target

If other code has `real` and is allowed to call `real.compute(...)`, it bypasses the proxy. Do not conclude "all calls have been checked" just because normal callers are given a proxy. Design ownership boundaries and enforce policy right at the critical action path.

### 22.6. Benchmarking once and rewriting the entire project

A random result is not enough to discard the benefits of interface abstraction, testability, and maintainability. Benchmarks must use the same payload, a warmed JVM, enough forks/measurements, avoid dead-code elimination, and be meaningful for real latency/throughput.

## 23. Selection and testing checklist before going to production

1. **Contract:** does the caller know the method/signature at compile time or only from runtime config?
2. **Number of behaviors:** one callback, multiple operations, or every method of an interface needing interception?
3. **Metadata:** are annotations/modifiers/parameters needed to make decisions?
4. **Type:** are primitive/reference types, boxing, overloads, and receiver types correct?
5. **Setup:** are discovery/proxy/handle created once or per request?
6. **Hot path:** number of calls in the application lifecycle; is the call site monomorphic/polymorphic?
7. **Error contract:** how are target exceptions, reflection wrappers, wrong handle types, and checked exceptions handled?
8. **Access:** Java visibility, JPMS module readability/exports/opens, which `Lookup` permissions, any leaked private handles?
9. **Proxy target:** does the handler delegate to the right target; are self-invocation bypass and valid reentrancy accounted for?
10. **Threading:** does the shared handler/registry/engine have mutable state or contention?
11. **Memory:** do callback captures, bound handles, reflective caches, and proxy handlers retain plugin classloaders for too long?
12. **Measurements:** are appropriate JMH/profiler/production load tests used instead of inferring from JDK docs?
13. **Observability:** do stack traces, tracing spans, and metrics distinguish dispatch overhead from target work?
14. **Maintainability:** IDE refactoring, compile-time checks, readability, test fixtures, and debugging experience.
15. **Fallback:** if a dynamic member is missing or module policy changes, are errors actionable and fail-safe?
16. **Evolution:** are changes to method signatures/interface versions easily caught in the build or left for runtime failures?
17. **Security:** can authorization be bypassed via raw target, reflection capability, or issued handles?
18. **Benchmark validity:** have setup vs steady state been separated and allocations/tail latency examined?

**Final decision milestone:** if direct/interface or callback satisfies the contract, start there. Add Reflection, MethodHandles, or proxy **according to real functional needs**; optimize after profiling.

## 24. Self-check questions with answers

1. **The method is known in source and needs no interception; what to choose first?** Direct/interface call.
2. **Want to pass an `int -> int` calculation as a callback; what to choose?** `IntUnaryOperator`/a suitably typed functional interface.
3. **Want to inspect method annotations at runtime; which tool is most natural?** Reflection.
4. **Can a `MethodHandle` directly replace `getDeclaredMethods()` to list annotations?** No; it represents a created invocation, not a metadata registry.
5. **Why does `Method.invoke` easily incur boxing?** The API accepts `Object...` and returns `Object`; primitives must be represented via wrappers at the boundary.
6. **What `MethodType` does the handle for `Operation.compute(int)` have?** `(Operation,int)int`, because the instance receiver is the first parameter.
7. **Is `invokeExact((Object)real,3)` valid for the handle above?** No, because the static receiver type does not match; the demo reports `WrongMethodTypeException`.
8. **What does `bindTo(real)` do?** Binds the receiver, making the handle type `(int)int`.
9. **How does `Method.invoke` handle exceptions thrown by the target?** Wraps them in `InvocationTargetException`; inspect `getCause()`.
10. **Does MethodHandle automatically wrap target exceptions in `InvocationTargetException`?** No.
11. **Does JDK Proxy automatically subclass any concrete class?** No, it creates implementations of interfaces.
12. **Why shouldn't a handler call `method.invoke(proxy,args)` when wanting delegation?** Because it calls back into the proxy and can cause infinite recursion.
13. **Does a proxy see `this.otherMethod()` calls inside the target?** Not automatically; that is self-invocation bypass.
14. **Does a proxy automatically intercept direct calls through the `real` reference?** No.
15. **Does `getEngine...` or a Reflection API replace JMH?** No; runtime metadata/discovery tools are not benchmarking systems.
16. **In the example, why is `realCalls=7`?** There are seven successful business calls: direct, interface, functional, reflection, handle, boundHandle, proxy.
17. **In the example, why is `intercepted=1` then `interceptedFinal=2`?** Only calls actually going through the proxy enter the handler; Object methods are not counted as business calls.
18. **Why is `realCallsFinal=10` instead of 11?** Three `compute(-1)` call paths ran the target; the wrong-type `invokeExact((Object)real,3)` was rejected before the target ran.
19. **Should `Function<Integer,Integer>` be used in every hot primitive pipeline?** Not by default; you can try primitive specializations, but measure before concluding.
20. **Does `invokedynamic` in `real::compute` mean every `applyAsInt` is that opcode?** No; creating the functional object may use indy, while the SAM call is an interface invocation.
21. **Why cache reflection/handles when the signature is stable?** Avoids repeating setup/discovery and increases the chance the JVM sees a stable call path, though it does not guarantee a win in every workload.
22. **Should a full-privilege `Lookup` be given to arbitrary plugins?** No; it can grant permission to create handles to members that the plugin should not be granted access to.
23. **If a backend returns results after 100 ms of I/O, what should be prioritized for optimization?** Consider I/O/DB/network, concurrency, and end-to-end latency before minor invocation costs.
24. **Does JMH guarantee benchmark results are invariant properties of Java APIs?** No; results depend on JDK version, workload, flags, hardware, shape, and runtime environment.
25. **What is a reasonable way to combine Reflection and MethodHandle?** Reflection discovers/validates metadata at setup, and handles are normalized and cached for repeated call paths if measurements justify it.
26. **Why might `Method.invoke` found via `getDeclaredMethod` fail to call a private method?** Access checks/JPMS still apply, and suppressing checks is not always permitted.
27. **When JDK proxy cannot proxy a concrete class lacking an interface, should you force-cast the proxy to the original class?** No; design an interface/decorator or consider another proxying tool.
28. **What criteria matter more than a few ns if the processing path is long-lived company business logic?** Correct contract, safety, maintainability, testability, runtime visibility, and reliable measurement data.

## 25. Official documentation and measurement tools

- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): method handle types, `invokeExact`/`invoke`, invocation checking, access capability, target exceptions.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVirtual`, `findStatic`, access checking, lookup modes, and module boundaries.
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): method descriptor of a handle.
- [Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): Reflection lookup/invocation, arguments, and `InvocationTargetException`.
- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): access checks and limitations of `setAccessible`/`trySetAccessible`.
- [Java SE 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): JDK dynamic proxy, interface restrictions, and Object methods.
- [Java SE 17 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): proxy/method/args parameters, exception rules, and default method invocation.
- [Java SE 17 — `IntUnaryOperator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntUnaryOperator.html): specialized functional interface avoiding boxing for `int -> int`.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): bytecode disassembly for comparing dispatch.
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): how to set up a benchmark project, samples, configuration, and measurement.

**Conclusion:** **Direct/interface is the default choice**, **functional interface is for typed callbacks/strategies**, **Reflection is for runtime metadata discovery**, **MethodHandle is for typed invocation and dynamic composition after setup**, and **dynamic proxy is for interface-based interception**. These mechanisms can be combined into a pipeline, but each added layer must solve a specific need. **Correct contracts, proper access boundaries, and maintainability come first; performance must be measured, not guessed.**