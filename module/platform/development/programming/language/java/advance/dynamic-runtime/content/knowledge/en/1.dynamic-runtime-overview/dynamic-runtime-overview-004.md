# 1.4 Map of Class, reflection, MethodHandle, VarHandle, Proxy, and CallSite

Java has many “dynamic” mechanisms, but they solve **different questions**: knowing what a type is, discovering and invoking members at runtime, creating a call with an explicit type signature, accessing variables with memory semantics, intercepting calls through an interface, or binding a call site to a mutable target. Confusing these roles easily leads to access errors, type errors, and wrong assumptions about performance.

After this lesson, you can draw the relationships among the six mechanisms, choose the appropriate API based on practical requirements, read handle signatures, and explain the limitations regarding modules, exceptions, thread safety, and `invokedynamic`.

## 1. Overall Map

| Mechanism | Main object | Question / task solved | Key points to remember |
| --- | --- | --- | --- |
| **Class** | `Class<?>` | “What type is this? What superclass, interfaces, annotations, and members does it have?” | Representation of a type loaded by the JVM; by itself it is not a method call. |
| **Reflection** | `Method`, `Field`, `Constructor<?>` | “I know the name/signature at runtime; how do I discover, invoke, read, or write members?” | Metadata-based manipulation API; `Method.invoke` boxes results/arguments as `Object`. |
| **MethodHandle** | `MethodHandle`, `MethodType`, `MethodHandles.Lookup` | “How do I hold a resolved call operation as a typed reference?” | A handle carries a specific signature and can be transformed/composed; `invokeExact` requires an exact type match. |
| **VarHandle** | `VarHandle` | “How do I read/write a field or array element, including volatile, acquire/release, CAS?” | Variable access and memory ordering; not a method invocation mechanism. |
| **Proxy** | `Proxy`, `InvocationHandler` | “How do I create an object that implements an interface and forwards calls to a handler?” | JDK dynamic proxy is based on **interfaces**; the handler decides the result on each call. |
| **CallSite** | `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite` | “At a dynamic call site, how is the target MethodHandle bound and updated?” | Holds `target: MethodHandle`; important in `invokedynamic` linking. |

Relationship diagram (arrows represent **usage relationships**, not inheritance relationships):

~~~text
Object / class name
    └─> Class<?> ──> look up Method / Field / Constructor ──> reflection
                  └─> know type and signature to create Lookup/MethodType
Lookup + name + MethodType ──> MethodHandle ──> invoke / transform call
Lookup + field / array element ──> VarHandle ──> get / set / CAS
Interface[] + InvocationHandler ──> Proxy instance ──> handler.invoke(...)
Bootstrap / dynamic linker ──> CallSite ──> target: MethodHandle
                                       └─> dynamicInvoker() invokes current target
~~~

These mechanisms can work together: a framework uses `Class<?>` to find annotations, reflection to read methods, `MethodHandle` to hold the resolved call operation, `Proxy` to wrap an interface, and then `CallSite` when building dynamic linking. No single API replaces all the others.

## 2. Class: the starting point for type identification and discovery

`Class<?>` is the object representing a Java type at runtime, including classes, interfaces, primitives, arrays, and some special type forms. A `Class` is tied to a **type identity in the JVM**, including the class loader that defined it: two classes with the same name defined by two different loaders can be two incompatible types.

Three common ways:

~~~java
Class<String> literal = String.class;
Class<?> actual = "hello".getClass();
Class<?> byName = Class.forName("java.lang.String");

System.out.println(literal == actual); // true
System.out.println(actual == byName);   // true
~~~

The snippet above illustrates three ways to obtain a `Class`; when placed inside `main`, the statements will print two `true` lines. `SomeType.class` is suitable when the type is known at compile time; `obj.getClass()` gets the actual type of the object; `Class.forName(name)` uses the type name at runtime and by default may trigger class initialization. Use `Class.forName(name, false, loader)` when you need to load/retrieve information without wanting to trigger class initialization immediately.

Distinguish the discovery APIs:

- `getMethods()`: visible `public` methods, including inherited methods.
- `getDeclaredMethods()`: methods **declared directly** in the type, including `private`, but does not automatically include inherited methods.
- `getMethod(name, types...)` and `getDeclaredMethod(name, types...)`: look up a method by **name and parameter types**; the return type is not passed into the lookup.
- `isAssignableFrom`, `getInterfaces`, `getSuperclass`, `getAnnotations`: inspect type relationships and metadata.

`Class<?>` helps you *know what exists*. To invoke a method or read/write a field via metadata, switch to reflection; to represent a resolved operation as a typed call, use a method/variable handle.

## 3. Reflection: discovering and performing operations at runtime

Reflection in `java.lang.reflect` provides `Method`, `Field`, and `Constructor`. For example, if the method name is provided by configuration:

~~~java
Method method = String.class.getMethod("substring", int.class);
Object result = method.invoke("dynamic", 3);
System.out.println(result); // amic
~~~

This is an illustrative snippet of statements (placed in `main` with `import java.lang.reflect.Method;`), not a standalone Java file. The sequence consists of: looking up `Method` by name/signature; providing the **receiver** as the first argument of `invoke` for an instance method; providing the method arguments; receiving the result as `Object`. A `static` method takes a `null` receiver. Reflection automatically handles appropriate boxing/unboxing and performs access checks.

Important limitations:

1. `getDeclaredMethod` seeing a `private` member does not mean you are allowed to invoke it. `setAccessible(true)` or `trySetAccessible()` is still subject to the Java Platform Module System (JPMS) and runtime access permissions.
2. If the invoked method throws an exception itself, `Method.invoke` wraps the target exception in `InvocationTargetException`; retrieve `getCause()` to handle the actual cause.
3. A wrong name/signature leads to `NoSuchMethodException`; a wrong target object/argument can lead to `IllegalArgumentException`; missing access permissions can lead to `IllegalAccessException` or `InaccessibleObjectException` when attempting to open access invalidly.
4. Reflection is useful for serializers, DI containers, test tooling, and plugin discovery. For repeated calls with a known signature, consider `MethodHandle`; performance decisions must be measured on a real workload.

## 4. MethodHandle: a typed, composable call operation

`MethodHandle` belongs to `java.lang.invoke` and represents a method/constructor invocation operation or certain member access operations. `MethodType` describes the **return type and parameter type sequence** of a handle. `MethodHandles.Lookup` is the object used to find handles within the access scope of the code creating the lookup.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle length = lookup.findVirtual(
        String.class, "length", MethodType.methodType(int.class));
int n = (int) length.invokeExact("abc");
System.out.println(n); // 3
~~~

Place this illustrative snippet in `main` with `import java.lang.invoke.*;` and a `throws Throwable` declaration. The actual signature of `length` is `(String)int`: the method receiver becomes the first parameter of the handle. The compile-time call site of `invokeExact` must also have a **`String` parameter and `int` return type**; the `(int)` cast in the code expresses the return type recorded by the compiler. A signature mismatch causes `WrongMethodTypeException`.

- `invokeExact(...)`: a call whose signature must match `MethodType` exactly, including the result type expected by the compiler.
- `invoke(...)`: can perform certain compatible type conversions equivalent to `asType`; it is not a mechanism for “converting any object to any type”.
- `asType`, `bindTo`, `insertArguments`, `filterArguments`, `guardWithTest`: adjust signatures, bind arguments, chain transformation steps, or select a target conditionally. Each transformation has its own type rules.
- `findStatic`, `findVirtual`, `findConstructor`: obtain different kinds of operations. A resolved MethodHandle does not automatically bypass access restrictions.

Unlike `Method.invoke`, a call through a handle generally throws the target's exception directly (without automatically wrapping it in `InvocationTargetException`). Handles can be optimized by the JVM in certain call patterns, but there is no guarantee that every `MethodHandle` call is faster than reflection. Creating lookups, type conversions, chaining adaptors, and call frequency all affect the outcome.

## 5. VarHandle: variable access with memory semantics

`VarHandle` is a handle to a **variable** such as an instance field, static field, or array element. It carries the value type and “coordinate types” to locate the variable; it does not contain business method invocation behavior. For example, `findVarHandle(Counter.class, "value", int.class)` creates a handle to access the `int value` field using coordinate `Counter`.

Commonly used access modes:

| Mode | Main meaning | When to consider |
| --- | --- | --- |
| `get` / `set` | Plain access | No cross-thread ordering is needed on this access itself. |
| `getOpaque` / `setOpaque` | Opaque access, weak ordering | Very specialized algorithms designed according to the Java Memory Model. |
| `getAcquire` / `setRelease` | Acquire/read and release/write | Publish–consume patterns with proper happens-before analysis. |
| `getVolatile` / `setVolatile` | Volatile semantics | Volatile-style visibility/ordering is needed. |
| `compareAndSet` / `compareAndExchange` | Atomic compare and update | Implementing contended state transitions across threads. |
| `getAndAdd` / `getAndSet` | Atomic update, if supported by mode/type | Counters/state when the method is supported. |

For example, `compareAndSet(counter, 10, 11)` changes `value` from 10 to 11 only if the current value is still 10; it returns `boolean`. `getVolatile(counter)` reads with volatile semantics. `VarHandle` does not make compound operations automatically atomic: a `get` followed by a `set` in two separate calls can still be interleaved by another thread. Not every access mode is supported for every variable kind (for example, updates are invalid for `final`); an unsupported mode may throw `UnsupportedOperationException`.

For ordinary data structures, prefer fields, `volatile`, `synchronized`, or classes in `java.util.concurrent.atomic` when they express the intent accurately; `VarHandle` is needed when infrastructure libraries truly require lower-level access control.

## 6. Proxy: creating an object for interfaces and forwarding calls

JDK dynamic proxy creates an object implementing one or more **interfaces** and dispatches interface calls to `InvocationHandler.invoke(proxy, method, args)`. The handler can log, control access, cache, select an implementation, or delegate to a real object.

~~~java
interface Greeting {
    String hello(String name);
}
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[] { Greeting.class },
        (instance, method, args) -> "Chào " + args[0]);
System.out.println(proxy.hello("An")); // Chào An
~~~

The snippet above illustrates declarations within an appropriate scope; `import java.lang.reflect.Proxy;` is required. Use JDK dynamic proxy to intercept **interface methods**; it does not create a subclass of an arbitrary concrete class. The proxy remains a normal object to the caller, while the handler receives the `Method` and arguments on every call.

Three things often overlooked: `equals`, `hashCode`, and `toString` also go through the handler, so consistent semantics are needed; the handler can use `InvocationHandler.invokeDefault` to call an interface's default method when appropriate (Java 16+); checked exceptions not declared on the interface may be wrapped in `UndeclaredThrowableException`. Avoid delegating back to the proxy itself, which causes infinite recursion.

## 7. CallSite: target at a dynamic call site

`CallSite` is a holder for a `MethodHandle target`. With the `invokedynamic` bytecode, a bootstrap method links a call site to a `CallSite`; subsequent calls execute the corresponding target. This is the underlying mechanism for certain runtime features and dynamic language implementations, and is **not synonymous** with invoking reflection by name on every execution.

The three types differ in target mutability and cross-thread visibility:

- **`ConstantCallSite`**: fixed target; `setTarget` does not allow changes. Used when the linkage does not change.
- **`MutableCallSite`**: allows `setTarget`, but other threads are not guaranteed to see the new target from assignment alone; `MutableCallSite.syncAll(...)` is used to synchronize visibility of updated targets.
- **`VolatileCallSite`**: the target has volatile semantics; threads observe updates under volatile rules without calling `syncAll`, potentially at higher synchronization cost.

Even when the target can be changed, **the `MethodType` of the new target must equal the old MethodType**; you cannot silently change the number/types of parameters or the return type. `site.dynamicInvoker()` returns a `MethodHandle` that always forwards to the current target. Manually creating a `CallSite` and calling `dynamicInvoker()` is a way to simulate this mechanism; that operation itself **does not emit a new `invokedynamic` instruction into bytecode**.

## 8. Java 17+ Example: all six APIs in one program

Create the file `DynamicRuntimeMapDemo.java`:

~~~java
import java.lang.invoke.*;
import java.lang.reflect.*;

public class DynamicRuntimeMapDemo {
    public static class Counter {
        public volatile int value;

        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    public interface Greeter {
        String greet(String name);
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter();

        // Class: type identification
        Class<?> type = counter.getClass();
        System.out.println("Class: " + type.getSimpleName());

        // Reflection: look up Method by name then invoke
        Method method = type.getMethod("greet", String.class);
        System.out.println("Reflection: " + method.invoke(counter, "Lan"));

        // MethodHandle: signature (Counter, String)String
        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Counter.class, "greet",
                MethodType.methodType(String.class, String.class));
        String invoked = (String) handle.invokeExact(counter, "Minh");
        System.out.println("MethodHandle: " + invoked);

        // VarHandle: access int field with volatile mode and CAS
        VarHandle variable = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class);
        variable.setVolatile(counter, 10);
        boolean swapped = (boolean) variable.compareAndSet(counter, 10, 11);
        System.out.println("VarHandle CAS: " + swapped);
        System.out.println("VarHandle value: " + (int) variable.getVolatile(counter));

        // Proxy: interface calls forwarded to InvocationHandler
        Greeter proxy = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] { Greeter.class },
                (instance, called, values) -> {
                    if (called.getDeclaringClass() == Object.class) {
                        return switch (called.getName()) {
                            case "toString" -> "GreeterProxy";
                            case "hashCode" -> System.identityHashCode(instance);
                            case "equals" -> instance == values[0];
                            default -> throw new UnsupportedOperationException();
                        };
                    }
                    return "Hi, " + values[0];
                });
        System.out.println("Proxy: " + proxy.greet("Hoa"));

        // CallSite: fixed target
        CallSite site = new ConstantCallSite(
                MethodHandles.constant(String.class, "v1"));
        String result = (String) site.dynamicInvoker().invokeExact();
        System.out.println("CallSite constant: " + result);

        // CallSite: target can be replaced, but signature ()String stays the same
        MutableCallSite mutable = new MutableCallSite(
                MethodHandles.constant(String.class, "v1"));
        MethodHandle dynamic = mutable.dynamicInvoker();
        System.out.println("CallSite mutable before: " + (String) dynamic.invokeExact());
        mutable.setTarget(MethodHandles.constant(String.class, "v2"));
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("CallSite mutable after: " + (String) dynamic.invokeExact());
    }
}
~~~

Compile and run from the directory containing the file (Java 17 or later):

~~~bash
javac DynamicRuntimeMapDemo.java
java DynamicRuntimeMapDemo
~~~

Expected `stdout`:

~~~text
Class: Counter
Reflection: Hello, Lan
MethodHandle: Hello, Minh
VarHandle CAS: true
VarHandle value: 11
Proxy: Hi, Hoa
CallSite constant: v1
CallSite mutable before: v1
CallSite mutable after: v2
~~~

How to read the output: `Class` provides metadata of `Counter`; `Method.invoke` executes via metadata; `MethodHandle.invokeExact` executes the resolved method with an explicit signature; `VarHandle` updates the field using CAS; `Proxy` provides behavior for the `Greeter` interface; `CallSite` holds a fixed target or allows controlled target replacement. This example runs `dynamicInvoker` directly to illustrate linking; it does not itself emit an `invokedynamic` opcode.

## 9. Choosing a mechanism based on practical requirements

| Requirement | Suitable starting point | Why |
| --- | --- | --- |
| Inspect annotations, superclass, interfaces, class loader | `Class<?>` | A metadata and type identification problem. |
| Plugin framework receiving method names from a config file | Reflection (`Method` / `Constructor`) | Discovering and executing members via metadata when unknown at compile time. |
| Dynamic dispatcher repeatedly invoking an operation with a known signature | `MethodHandle` | Describes a typed call, can be bound/adapted/combined. |
| Concurrent library needing CAS or acquire/release for fields/arrays | `VarHandle` | Has explicit access modes and memory ordering. |
| Adding logging/authorization to a service interface | `Proxy` + `InvocationHandler` | Creates an object implementing the interface and intercepts each method call. |
| Dynamic linker wanting to change the target of a call site | `CallSite` + `MethodHandle` | Decouples the call site from the current target while keeping the signature invariant. |

Example pipeline in a framework: use `Class.forName` to load an implementation by name; inspect annotations using `Class`/reflection; create a `MethodHandle` for the selected method; wrap the interface with `Proxy` when interception is needed; if performing dynamic language linking, `CallSite` can hold the target MethodHandle. This pipeline is **one possible architecture**, not a mandatory sequence of operations.

## 10. Access permissions, JPMS, type errors, and performance

**Access permissions:** `MethodHandles.lookup()` carries the permissions of the context that created the lookup. `privateLookupIn(target, lookup)` only works when access and module conditions are satisfied; it is not a way to bypass JPMS. For named modules, `exports` is generally for public APIs; `opens` grants deep reflection access to a package within the declared scope. `--add-opens` can be useful when running tooling that needs to open a package, but only use it when you truly understand and accept the access scope. Never assume `setAccessible(true)` always succeeds.

**Common errors and how to diagnose them:**

1. `NoSuchMethodException` during reflection lookup: check the name, parameter types, static/instance, public vs. declared; the same name with different parameters is not the same method.
2. `InvocationTargetException` from `Method.invoke`: check `getCause()`; an inner business error is different from an outer reflection error.
3. `WrongMethodTypeException` at `invokeExact` or when changing a `CallSite` target: print `handle.type()` and compare it with the argument/return types at the call site; do not forget the receiver instance as the first parameter.
4. `IllegalAccessException` / `InaccessibleObjectException`: check visibility, Lookup context, `exports` / `opens`, and caller module.
5. `UnsupportedOperationException` on `VarHandle`: check `isAccessModeSupported(...)`, field type, and `final`ness; do not assume every atomic operation is valid.
6. Proxy returns the wrong type, lacks `Object` method behavior, or delegates in a loop back to the proxy: check the interface contract, `equals`/`hashCode`/`toString`, and the handler's call flow.
7. After updating `MutableCallSite`, another thread still sees the old target: analyze visibility and use `syncAll` or `VolatileCallSite` as required; do not extrapolate from single-threaded run results.

**Performance and safety:** cache lookup/resolution results when appropriate, avoid accepting untrusted method/class names and granting overly broad access permissions, validate inputs, and control class loaders. Do not conclude that reflection is always slow, handles are always fast, or proxies always incur significant overhead: measure with JMH, with warm-up, on the right call path, with realistic data types and load. For ordinary application code, direct Java calls remain the simplest and easiest-to-verify choice when types are known at compile time.

## 11. Self-check

- Need to read all annotations of a class, with the object known at runtime: what to use? → `obj.getClass()` and `Class` metadata APIs (or `AnnotatedElement`).
- Found a `MethodHandle` with type `(String)int`; does an `(Object)int` call via `invokeExact` match? → No; it must match exactly or adapt the handle/call type validly.
- Want to update an `int` using CAS across threads: use `MethodHandle` or `VarHandle`? → `VarHandle` (or appropriate atomic abstractions).
- Want to intercept methods of an interface without changing the interface: what to use? → JDK `Proxy` with `InvocationHandler`.
- Why is `MutableCallSite.setTarget` not enough for all threads to see the new target immediately? → Because it does not provide visibility guarantees equivalent to volatile; see `syncAll` or `VolatileCallSite`.
- Can the target of a `MutableCallSite` be changed from `(String)int` to `(String)String`? → No; the `MethodType` of the new target must remain the same.

## Standard API References (Java SE 21)

- [Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Reflection: Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [VarHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Proxy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html) and [InvocationHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [CallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html), [MutableCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html) and [VolatileCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
