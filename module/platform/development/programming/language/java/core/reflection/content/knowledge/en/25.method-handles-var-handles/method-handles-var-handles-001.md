# Distinguishing Core Reflection from `java.lang.invoke`

## 1. Two APIs Working with Java Elements at Runtime with Different Roles

**Core reflection** is the set of APIs primarily in `java.lang.Class` and `java.lang.reflect` (`Method`, `Constructor`, `Field`, `Parameter`, `Modifier`, `RecordComponent`...). It is suitable when a program needs to **discover metadata** of a type: finding methods, fields, constructors, annotations, parameters, modifiers, and generic types; and then invoking methods, creating objects, or reading/writing fields through those metadata objects.

**`java.lang.invoke`** provides typed operation objects such as `MethodHandle` and `VarHandle`, along with `MethodHandles.Lookup`, `MethodType`, `CallSite`, and handle combinator tools. It is suitable when you have already determined the operation to perform and want to **represent a call or access as a handle with a specific signature**, easy to compose/adapt for dynamic invocation; `VarHandle` also supports memory access modes and atomic operations.

They have some overlap, but they are not complete replacements for each other: `MethodHandle` does not provide a store of annotation/generic metadata like `Method`, and `Method` does not replace the access modes and compare-and-set of `VarHandle`. Both still obey the access controls of the language and the module system.

| Question | Core reflection | `java.lang.invoke` |
| --- | --- | --- |
| Primary objects | `Class<?>`, `Method`, `Constructor<?>`, `Field` | `MethodHandle`, `VarHandle`, `MethodType`, `MethodHandles.Lookup` |
| Finding members | `getMethod`, `getDeclaredMethods`, `getDeclaredField`… | `Lookup.findVirtual`, `findStatic`, `findConstructor`, `findVarHandle`… |
| Discovering annotations/generics/parameters | Strong and direct through metadata | Not its primary role; typically uses reflection if needed |
| Invoking a method | `Method.invoke(receiver, Object...)` | `handle.invokeExact(...)`, `handle.invoke(...)`, `invokeWithArguments(...)` |
| Creating an instance | `Constructor.newInstance(Object...)` | Constructor `MethodHandle` with type signature `(args)Instance` |
| Fields | `Field.get/set` and primitive variants | `VarHandle.get/set`, CAS, atomic updates, memory ordering |
| Types at the call site | Parameters/return value pass through `Object`, with boxing/unboxing | `MethodType` and call-site signature, especially strict with `invokeExact` |
| Exceptions thrown by target method | `Method.invoke` wraps in `InvocationTargetException` | `MethodHandle` propagates the target's exception directly |
| Access permissions | Java access checks, `setAccessible` within module boundaries | Permissions reside in `Lookup`; looking up a handle must pass access checks |

## 2. Core Reflection: Discover First, Invoke Through Metadata Objects

Example code snippet placed inside a method (not a standalone program):

```java
Method method = String.class.getMethod("substring", int.class);
Object answer = method.invoke("java", 2);
System.out.println(answer); // va
```

`getMethod` finds a public method by **name and parameter types**, and `Method.invoke` requires a receiver for instance methods. The result has compile-time type `Object` even though `substring` is declared to return `String`; the primitive argument `2` is boxed in the varargs call. For `static` methods, the receiver passed to `Method.invoke` can be `null`.

Reflection is useful when the type structure is unknown at compile time. For example, a framework inspecting annotations to map HTTP routes, a serialization tool needing to read fields/generic types, a test runner scanning for annotated methods, or a class explorer listing constructors and modifiers. `getMethods()` only retrieves public methods (including inherited ones), whereas `getDeclaredMethods()` retrieves methods declared directly in the class regardless of modifier, without inherited methods. Finding a private member **does not mean you have permission to invoke it**.

Constraints to keep in mind:

- `Method.invoke` can perform conversions permitted by reflection, such as unboxing and certain primitive widenings; it does not cast arbitrarily.
- `Method.invoke` wraps exceptions thrown by target code in `InvocationTargetException`; call `getCause()` to see the underlying error. Lookup errors and access errors occur along different exception paths.
- `Field.getInt`/`setInt` operate on `int` fields without manually casting `Object`; however, `Field` itself does not provide atomic compare-and-set or the access modes of `VarHandle`.
- `setAccessible(true)` does not always succeed: strong encapsulation in the Java Platform Module System still imposes boundaries.

## 3. `MethodHandle`: Call Reference with an Explicit Signature

A `MethodHandle` represents a typed invocation. `MethodType` describes the exact parameter list and return type of the handle; `handle.type()` tells you the signature **after the handle is created**, which is not necessarily identical to the method's original declared signature.

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle substring = lookup.findVirtual(
        String.class, "substring", MethodType.methodType(String.class, int.class));
System.out.println(substring.type()); // (String,int)String
String answer = (String) substring.invokeExact("java", 2);
System.out.println(answer); // va
```

This is a fragment that must be placed inside a method declaring `throws Throwable` (or catching exceptions) and importing `java.lang.invoke.*`. For `findVirtual`, `MethodType.methodType(String.class, int.class)` describes the **target method** `substring(int) -> String`; the resulting handle has the `String` receiver added in the first position, so its actual type is `(String,int)String`.

Common ways to create handles:

| `Lookup` method | Resulting operation |
| --- | --- |
| `findVirtual(Owner.class, name, methodType)` | Instance method; receiver comes first in the handle's parameters |
| `findStatic(Owner.class, name, methodType)` | Static method; no receiver |
| `findConstructor(Owner.class, methodType(void.class, ...))` | Constructor call; handle returns an `Owner` instance |
| `findGetter` / `findSetter` | Handle operating on the corresponding field, subject to lookup permissions |
| `unreflect(Method)` / `unreflectConstructor(Constructor)` | Converts a reflection object into a handle if required permissions are held |
| `findSpecial(...)` | Call with `invokespecial` semantics, requiring special context and permissions |

Combinator methods such as `bindTo(receiver)`, `asType(newType)`, `filterArguments`, or `guardWithTest` can create new handles from existing ones. This is useful in dynamic call dispatchers when you want to prepare a call path once and reuse it.

**`invokeExact` and `invoke` differ in signature matching:**

- `invokeExact`: the signature at the call site—including receiver, parameter count, parameter types, **and return type**—must match `handle.type()` exactly; a mismatch throws `WrongMethodTypeException`. Because of this, you typically need to cast the result, for example `int n = (int) handle.invokeExact(obj, 3);`.
- `invoke`: allows conversions according to `asType` rules when compatible, such as boxing/unboxing and valid reference casts. It still checks types and does not turn any `Object` into an arbitrary type.
- `invokeWithArguments`: accepts a dynamic argument list via `Object`/`List`, convenient when there is no static signature yet, though it adds overhead and conversions; it should not always be used.

For example, `MethodHandle` handles target exceptions directly without wrapping them in `InvocationTargetException` like `Method.invoke`. When designing a public API, you do not necessarily need to propagate `throws Throwable` across the entire application; you can catch/map errors at the adapter layer.

## 4. `VarHandle`: Variable Access with Memory/Atomic Semantics

`VarHandle` describes access to a **variable**: an instance field, a static field, or an array element. Unlike `Field`, it has access mode groups and can participate in lock-free synchronization algorithms when the variable type and access mode support them. A handle has a value type (`varType()`) and a list of coordinate types (`coordinateTypes()`); for example, the instance field `Counter.value` has value type `int` and coordinate `Counter`, whereas an `int[]` element has coordinates `int[]` and index `int`.

| Access mode group | Examples | Primary meaning |
| --- | --- | --- |
| Plain | `get`, `set` | Ordinary access, requiring no additional ordering for cross-thread synchronization |
| Opaque | `getOpaque`, `setOpaque` | Weaker ordering than acquire/release, but with the consistency guarantees specific to opaque access |
| Acquire / Release | `getAcquire`, `setRelease` | Publishes/receives data with acquire/release ordering when properly paired |
| Volatile | `getVolatile`, `setVolatile` | Volatile access semantics under the Java Memory Model |
| Atomic | `compareAndSet`, `compareAndExchange`, `getAndSet`, `getAndAdd` | Atomic read-modify-write operations with specific ordering semantics per access mode |

**Not every mode is supported for every variable.** For example, `getAndAdd` does not make sense for all reference types; use `isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` if you need to check dynamically. For `final` fields, write or atomic update modes are not supported. Do not assume that plain `get` or `set` guarantees cross-thread synchronization; choose modes and design happens-before relationships appropriately.

For arrays, you can create a handle without a field:

```java
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
int[] values = {4, 8};
boolean swapped = element.compareAndSet(values, 1, 8, 9);
System.out.println(swapped + ", " + values[1]); // true, 9
```

This is a fragment requiring `import java.lang.invoke.*;`; `compareAndSet` takes the coordinates `(array, index)` followed by the expected/new value. In concurrency problems, avoid assuming that a single CAS guarantees all invariants of a multi-field data structure: you still need to analyze contention, visibility, retry loops, and ABA issues if any.

## 5. Complete Java 17+ Example: One Class, Three Ways to Interact

Save the following code as **`ReflectionInvokeDemo.java`**. The example uses a nested class `Counter` with a constructor, instance method, static method, and private field. Because the code is in the same nest, the lookup has permission to access the private field in this example; for classes in different modules/packages, access control must be re-evaluated.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionInvokeDemo {
    public static final class Counter {
        private int value;

        public Counter(int initial) { this.value = initial; }

        public int add(int delta) {
            value += delta;
            return value;
        }

        public static String format(String label, int value) {
            return label + "=" + value;
        }
    }

    public static void main(String[] args) throws Throwable {
        // Core reflection: discover metadata, then invoke/read/write.
        Constructor<Counter> constructor = Counter.class.getConstructor(int.class);
        Counter a = constructor.newInstance(5);
        Method method = Counter.class.getMethod("add", int.class);
        Object reflectResult = method.invoke(a, 2);
        Field field = Counter.class.getDeclaredField("value");
        field.setAccessible(true);
        field.setInt(a, 9);
        System.out.println("reflect invoke: " + reflectResult);
        System.out.println("reflect field: " + field.getInt(a));

        // MethodHandle: create handles with explicit signatures, then invoke.
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle mhCtor = lookup.findConstructor(
                Counter.class, MethodType.methodType(void.class, int.class));
        Counter b = (Counter) mhCtor.invokeExact(10);
        MethodHandle mhAdd = lookup.findVirtual(
                Counter.class, "add", MethodType.methodType(int.class, int.class));
        int result = (int) mhAdd.invokeExact(b, 3);
        MethodHandle mhStatic = lookup.findStatic(
                Counter.class, "format",
                MethodType.methodType(String.class, String.class, int.class));
        String description = (String) mhStatic.invokeExact("counter", result);
        System.out.println("handle invokeExact: " + result);
        System.out.println("static handle: " + description);

        // VarHandle: access field and perform atomic updates.
        VarHandle var = lookup.findVarHandle(Counter.class, "value", int.class);
        int before = (int) var.get(b);
        var.set(b, 20);
        boolean changed = var.compareAndSet(b, 20, 25);
        int previous = (int) var.getAndAdd(b, 5);
        System.out.println("var before: " + before);
        System.out.println("var CAS: " + changed);
        System.out.println("var getAndAdd previous: " + previous);
        System.out.println("var volatile read: " + (int) var.getVolatile(b));
    }
}
```

Compile and run:

```bash
javac --release 17 ReflectionInvokeDemo.java
java ReflectionInvokeDemo
```

Stdout:

```text
reflect invoke: 7
reflect field: 9
handle invokeExact: 13
static handle: counter=13
var before: 13
var CAS: true
var getAndAdd previous: 25
var volatile read: 30
```

Explanation: variable `a` increases from `5` to `7` via reflection and is then set to `9`. Variable `b` is created through the constructor handle with `10` and incremented to `13` via the instance method handle. `VarHandle` reads `13`, sets `20`, conditionally swaps `20 -> 25`, and then adds `25 -> 30`; `getAndAdd` returns the **previous value `25`**. The operations run sequentially to illustrate the contract; the example does not claim to prove correctness of a multi-threaded algorithm.

## 6. Common Mistakes and Self-Check Questions

- Calling `getDeclaredMethod` and assuming you are already allowed to invoke a private member: **false**; finding metadata and having permission to execute are two separate steps.
- Putting all arguments into an `Object[]` when calling `invokeExact` and expecting automatic adaptation: **false**; the call-site types must match the handle, or you must deliberately use `asType`/`invoke`/`invokeWithArguments` as appropriate.
- Thinking the `MethodType` passed to `findVirtual` already includes the receiver: **false**; the receiver appears in the resulting handle's type, whereas the `MethodType` passed in describes the target method.
- Treating plain `VarHandle.set` and `setVolatile` as having the same memory semantics: **false**; ordering is part of the contract.
- Ignoring `Lookup`/JPMS or viewing `privateLookupIn` as an automatic backdoor: **false**; permission checks still apply.

Self-check:

1. If you want to get the annotations of a method whose name is unknown at compile time, do you use `Method` or `MethodHandle`? **`Method`** via core reflection.
2. For `findVirtual` on the method `int inc(int x)`, does the handle need a receiver parameter? **Yes**, the receiver comes before `int x`.
3. If you want to atomically and conditionally update an `int` field, do you use `Field.setInt` or `VarHandle.compareAndSet`? **`VarHandle.compareAndSet`**.
4. The target throws `IOException`: do `Method.invoke` and `invokeExact` behave identically? **No**; reflection wraps the target exception in `InvocationTargetException`, whereas a method handle forwards the exception directly.
5. What does `VarHandle.getAndAdd(receiver, 5)` return? **The value before the addition**, when that mode is supported.

Further reading: [Javadoc `java.lang.reflect.Method` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [Javadoc `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html), [Javadoc `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html), [Javadoc `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html), [JEP 416](https://openjdk.org/jeps/416).