# 9.1 Role of `VarHandle` and Differences from `Field` or `MethodHandle`

In Java 9+, `java.lang.invoke.VarHandle` is an object that describes **how to access a variable of a specific type**, such as an instance field, static field, array element, or data location in supported structures. It not only allows `get`/`set`, but also provides explicit **access modes**: plain, opaque, acquire, release, volatile, and atomic update operations such as compare-and-set or get-and-add.

`VarHandle` is particularly useful when writing libraries, runtimes, concurrent data structures, framework engines, or tools that need dynamic variable access while still adhering to the **Java Memory Model (JMM)**. However, it is not a default replacement for every getter/setter, nor is it "faster Reflection" with unrestricted access.

**Brief distinction:**

- **`java.lang.reflect.Field`:** metadata and read/write operations for **a reflected field**, along with modifier, annotation, and declaring class information; convenient for inspecting class structure.
- **`java.lang.invoke.MethodHandle`:** a typed reference to **a callable operation**: method, constructor, field getter/setter, adapter, or a composition of operations. It describes an action via `MethodType`, without inherently providing the full set of memory access modes.
- **`java.lang.invoke.VarHandle`:** a typed reference to **a variable or family of variable locations**. The same handle can be invoked with multiple **access modes** such as `getAcquire`, `setRelease`, `compareAndSet`, `getAndAdd`, if that variable and mode are supported.

This lesson explains the role, creation and usage mechanisms of `VarHandle`, compares it with `Field`/`MethodHandle`, covers choosing the right tool, access control limits, and common mistakes. Examples are compatible with **Java 17+**, and the complete programs below include compile/run commands along with verified stdout.

## 1. Why does Java have VarHandle?

Suppose a class has a variable:

```java
class Counter {
    int value;
}
```

If working only within a normal class, Java source can read/write directly: `counter.value`, `counter.value = 5`. With a variable shared between threads, the requirement is different: one must distinguish a plain read from a volatile read, or modify `value` with an **atomic** operation to avoid lost updates.

To update `value` concurrently, code of the following form is **not** sufficient:

```java
// Illustrating within a place that has access to the field:
counter.value = counter.value + 1;
```

It consists of **read, compute, then write**. Two threads can read the same old value and write the same new value. Declaring the variable `volatile` also does not automatically turn the addition above into an atomic read-modify-write.

`VarHandle` allows expressing the intent clearly:

```java
// Illustrative snippet: VALUE is a VarHandle pointing to the int value field of Counter.
int previous = (int) VALUE.getAndAdd(counter, 1);
```

`getAndAdd` performs an atomic update with the memory semantics defined by the API and returns the **value before adding**. That same `VALUE` can be used for `get`, `set`, `getVolatile`, `setRelease`, `compareAndSet`, depending on the supported `AccessMode`.

**Key takeaway:** VarHandle combines the **logical address of a variable** with **access methods that have different memory semantics**; it does not force you to create a new wrapper object for each instance field.

## 2. Variable model: variable type and coordinate types

A `VarHandle` has two important components:

1. **Variable type (`T`)** — the type of value stored, for example `int`, `long`, `String`, `Object`.
2. **Coordinate types (`CT1...CTn`)** — the arguments that identify **which specific variable** is being accessed. They are not the new value to be written; they are the "coordinates" of the data location.

Read metadata using:

```java
Class<?> variableType = handle.varType();
java.util.List<Class<?>> coordinates = handle.coordinateTypes();
```

This is an **illustrative snippet** with a variable `handle` of type `VarHandle` already created.

| Target variable | Typical creation | `varType()` | `coordinateTypes()` | How to invoke |
| --- | --- | --- | --- | --- |
| Instance field `int Cell.value` | `lookup.findVarHandle(Cell.class, "value", int.class)` | `int` | `[Cell.class]` | `(int) vh.get(cell)` |
| Static field `int Config.level` | `lookup.findStaticVarHandle(Config.class, "level", int.class)` | `int` | `[]` | `(int) vh.get()` |
| `int[]` element | `MethodHandles.arrayElementVarHandle(int[].class)` | `int` | `[int[].class, int.class]` | `(int) vh.get(array, index)` |
| Byte-array/ByteBuffer view (valid numeric type) | `byteArrayViewVarHandle` / `byteBufferViewVarHandle` | Component type of the view | Array/buffer and access position | Subject to byte order and alignment constraints |

Instance field example: `vh.get(cell1)` and `vh.get(cell2)` both use **one handle**, while the coordinate `cell1`/`cell2` selects two different variables. For arrays: `vh.get(numbers, 0)` and `vh.get(numbers, 1)` select two different elements. For static fields, there is no receiver so there is **no coordinate argument**.

Do not think of `VarHandle` as a `Field` holding a pre-bound object instance. It typically describes a location **parameterized by coordinates**, and on each access the caller supplies the receiver or index.

### 2.1. MethodType of an access mode

Each access mode has its own signature; `VarHandle.accessModeType(VarHandle.AccessMode.GET)` returns the `MethodType` for the `get` mode of that handle. For `int Cell.value`:

| Access mode | Arguments | Result type | Example signature |
| --- | --- | --- | --- |
| `get` | `Cell` | `int` | `(Cell)int` |
| `set` | `Cell, int newValue` | `void` | `(Cell,int)void` |
| `getVolatile` | `Cell` | `int` | `(Cell)int` |
| `compareAndSet` | `Cell, int expected, int replacement` | `boolean` | `(Cell,int,int)boolean` |
| `compareAndExchange` | `Cell, int expected, int replacement` | `int` (witness) | `(Cell,int,int)int` |
| `getAndAdd` | `Cell, int delta` | `int` (previous value) | `(Cell,int)int` |

The methods on `VarHandle` are declared in the Java API as **signature polymorphic**: the signature at the *call site* is checked dynamically based on the handle and access mode. For primitive types, write an explicit result cast so the caller expresses the expected type, for example `(int) vh.get(cell)`; do not assume that because the API declaration looks like `Object get(Object...)`, the actual result is always `Object`.

**Important detail of Java 17:** A newly created `VarHandle` normally has **invoke behavior** that allows compatible conversions like `MethodHandle.invoke`. Calling `vh.withInvokeExactBehavior()` creates a handle referencing the same variable but requiring an **exact match** of the access-mode `MethodType` in the spirit of `MethodHandle.invokeExact`. Do not claim that every `VarHandle.get(...)` forbids all conversions by default; this depends on invocation behavior.

## 3. Creating VarHandle properly

Commonly used factory APIs:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

// Instance field of a class:
VarHandle instanceField =
        lookup.findVarHandle(Example.class, "count", int.class);

// Static field of a class:
VarHandle staticField =
        lookup.findStaticVarHandle(Example.class, "global", int.class);

// Array element:
VarHandle arrayElement =
        MethodHandles.arrayElementVarHandle(int[].class);
```

**Illustrative code snippet**, assuming `Example` has those exact fields of type `int`, the corresponding static modifiers, and the caller has lookup permissions; `java.lang.invoke.*` or individual classes must be imported, and `NoSuchFieldException`/`IllegalAccessException` handled.

`findVarHandle` takes the **exact field type**, not a convenient type to convert automatically. If the field is declared `long` and you pass `int.class`, the lookup can report `NoSuchFieldException`. Similarly, `findStaticVarHandle` does not substitute for `findVarHandle` if the actual field is non-static.

One way to keep a handle stable is to create it in a static initializer, where the lookup happens **once**:

```java
private static final VarHandle VALUE;

static {
    try {
        VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
    } catch (ReflectiveOperationException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

This is a **declaration snippet inside a class** that has the field `Counter.value`, not a standalone program. Using `static final` for the VarHandle reference prevents accidentally replacing the handle elsewhere in the code; it does **not** make the target variable `final`, nor does it automatically give all operations on the target variable volatile memory semantics.

### 3.1. Access permissions at handle creation

`MethodHandles.Lookup` carries the caller's permissions. To find a private field, the caller needs actual access permission according to Java/JPMS. Code in the declaring class itself or in the same nest can usually use `MethodHandles.lookup()`; code in another class/module may need `MethodHandles.privateLookupIn(targetClass, lookup)`, but only when module/access conditions are met.

- Core Reflection's `getDeclaredField(...)` finds metadata without proving read/write permission yet.
- `lookup.findVarHandle(...)` checks permissions **when creating the handle** and can throw `IllegalAccessException`.
- Once a handle to a private field has been validly created, anyone who **receives that handle** can use the corresponding capability without going through the private-field access check again like `Field.get`. Therefore **do not leak VarHandles to untrusted code**.
- `privateLookupIn` does not bypass JPMS: a package of another module may need `opens` to the caller module; do not automatically pass `--add-opens` or request blanket access.

Contrary to the notion that "Reflection can read anything", both Core Reflection and Method Handles are governed by Java access control and module boundaries.

## 4. Complete example 1: instance field and atomic updates

Create **`VarHandleIntroDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleIntroDemo {
    private static final class Cell {
        private int value = 5;
    }

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Cell.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) {
        Cell cell = new Cell();
        System.out.println("variable type: " + VALUE.varType().getSimpleName());
        System.out.println("coordinate count: " + VALUE.coordinateTypes().size());
        System.out.println("get access type: "
                + VALUE.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("initial: " + (int) VALUE.get(cell));
        VALUE.set(cell, 8);
        System.out.println("after set: " + (int) VALUE.get(cell));

        boolean first = VALUE.compareAndSet(cell, 8, 13);
        boolean second = VALUE.compareAndSet(cell, 8, 99);
        System.out.println("CAS first: " + first);
        System.out.println("CAS second: " + second);

        int old = (int) VALUE.getAndAdd(cell, 4);
        System.out.println("getAndAdd old: " + old);
        System.out.println("final: " + (int) VALUE.getVolatile(cell));
        System.out.println("CAS supported: "
                + VALUE.isAccessModeSupported(VarHandle.AccessMode.COMPARE_AND_SET));
    }
}
```

Java 17+ run commands:

```bash
javac --release 17 VarHandleIntroDemo.java
java VarHandleIntroDemo
```

**Stdout verified by compiling and running:**

```text
variable type: int
coordinate count: 1
get access type: (Cell)int
initial: 5
after set: 8
CAS first: true
CAS second: false
getAndAdd old: 13
final: 17
CAS supported: true
```

Analysis:

1. `Cell.value` is a private instance field of type `int`; the static initializer looks up the handle within the **nest** containing `VarHandleIntroDemo` and the nested class `Cell`, so the lookup has permission.
2. `varType()` is `int`; `coordinateTypes().size()` is `1` because a `Cell` instance must be passed.
3. `get(cell)` reads `5`. `set(cell,8)` writes `8`; in a single-threaded program, these are two valid operations.
4. `compareAndSet(cell,8,13)` updates because the current value is indeed `8`, returning `true`.
5. The subsequent `compareAndSet(cell,8,99)` sees that the current value is already `13`, so it returns `false` without changing the variable.
6. `getAndAdd(cell,4)` atomically increments from `13` to `17` and returns the **value before adding**, which is `13`.
7. `getVolatile(cell)` reads in volatile mode; the program can choose this semantics right at the access site even though the source field is not declared `volatile`.
8. `isAccessModeSupported(COMPARE_AND_SET)` returns `true` for the writable `int` field in the example.

`compareAndSet` is an atomic read-modify-write operation, not equivalent to `if (get() == expected) set(newValue)`. The split form can be interleaved by another thread between the two operations.

## 5. General comparison: `Field`, `MethodHandle`, `VarHandle`

| Criterion | `Field` | `MethodHandle` | `VarHandle` |
| --- | --- | --- | --- |
| Nature | Metadata of a specific field | Typed handle for **a callable operation** | Typed handle for **a variable location / family of locations** |
| API package | `java.lang.reflect` | `java.lang.invoke` | `java.lang.invoke` |
| How to obtain | `Class.getField/getDeclaredField` | `Lookup.findStatic/findVirtual/findGetter/findSetter/...` | `Lookup.findVarHandle/findStaticVarHandle`, array/view factories |
| Type inspection / description | `getType()`, `getGenericType()`, annotations, modifiers | `type(): MethodType` | `varType()`, `coordinateTypes()`, `accessModeType(...)` |
| Primary operations | `get/getInt/set/setInt`, metadata inspection | `invokeExact/invoke`, adapter composition | `get/set/getVolatile/getAcquire/setRelease/CAS/getAndAdd/...` |
| Target argument | Receiver object for instance fields, `null` for static | Arguments per `MethodType`, may include receiver | Coordinate arguments per variable location: receiver/index/none |
| Memory ordering | Tied to field access semantics and modifiers; no per-call mode list | Depends on the target operation the handle represents | **Choose access mode per call**, if supported |
| Atomic compare-and-set | No direct CAS API on `Field` | Can wrap/call another CAS operation if a handle is created to it | **Defined directly** via `compareAndSet` and related modes |
| Access exception handling | May throw `IllegalAccessException` on read/write; `setAccessible` subject to module limits | Lookup may throw `IllegalAccessException`; invokes target via MethodHandle per created signature | Lookup may throw `IllegalAccessException`; access modes check type/mode support |
| Annotation/modifier inspection | **Very well suited** | Not the primary purpose | Not the primary purpose |
| Typical use cases | Serializer schema discovery, inspection, tooling | Dynamic method invocation, adapters, runtime dispatch | State access, coordination, atomics, concurrency primitives |

**Two misconceptions to avoid:**

1. `MethodHandle` **can also represent a field getter/setter**: `Lookup.findGetter`, `findSetter`, or `VarHandle.toMethodHandle(AccessMode.GET)` returns a corresponding MethodHandle. Thus it is inaccurate to say MethodHandle "only calls methods, cannot touch fields". The difference is that `VarHandle` associates **multiple memory access modes with the same variable**.
2. `Field.get/set` still has Java Memory Model semantics appropriate for a field declared `volatile`; do not claim Reflection "has no volatile". The difference is that Core Reflection **does not let you choose plain/opaque/acquire/release/volatile individually on the same Field API call** like VarHandle does.

`Field` is usually easy to use when you need to discover metadata and then read/write simple configuration or object mappings. `MethodHandle` fits a dynamic call with a specific signature and adapters. `VarHandle` is the right tool when the **variable** and **variable access semantics** are the focus.

### 5.1. Performance is not an absolute guarantee

Do not claim `VarHandle` is always faster than `Field`/`MethodHandle` in every case. Performance depends on the JDK/JIT, call-site stability, lookup/caching, access modes, CPU topology, contention, and how the benchmark is written.

In particular, `getVolatile` or `getAndAdd` has stronger semantics than a plain read, so one cannot fairly benchmark them against `Field.get` while ignoring synchronization differences. When choosing an API, first ensure **semantic correctness**, then measure in a realistic workload with a proper benchmark such as JMH.

## 6. Complete example 2: the same field through three APIs

The following example intentionally uses **two top-level classes** in the same file to demonstrate that `Field` and `VarHandle` have different access-control models. The class `HiddenState` is not in the same nest as `FieldAndMethodHandleDemo`, though both run in the unnamed module on the classpath.

Create **`FieldAndMethodHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;

class HiddenState {
    private int score = 10;
}

public class FieldAndMethodHandleDemo {
    public static void main(String[] args) throws Throwable {
        HiddenState state = new HiddenState();

        Field field = HiddenState.class.getDeclaredField("score");
        System.out.println("Field canAccess: " + field.canAccess(state));
        System.out.println("Field trySetAccessible: " + field.trySetAccessible());
        System.out.println("Field getInt: " + field.getInt(state));

        MethodHandles.Lookup privateLookup =
                MethodHandles.privateLookupIn(HiddenState.class,
                        MethodHandles.lookup());
        VarHandle score = privateLookup.findVarHandle(
                HiddenState.class, "score", int.class);
        System.out.println("VarHandle get: " + (int) score.get(state));
        score.set(state, 20);
        System.out.println("VarHandle after set: " + (int) score.get(state));

        MethodHandle getter =
                score.toMethodHandle(VarHandle.AccessMode.GET);
        System.out.println("MethodHandle type: " + getter.type());
        System.out.println("MethodHandle result: "
                + (int) getter.invokeExact(state));
    }
}
```

Run commands:

```bash
javac --release 17 FieldAndMethodHandleDemo.java
java FieldAndMethodHandleDemo
```

Verified stdout:

```text
Field canAccess: false
Field trySetAccessible: true
Field getInt: 10
VarHandle get: 10
VarHandle after set: 20
MethodHandle type: (HiddenState)int
MethodHandle result: 20
```

Clear explanation of the boundaries:

- `Field` uses `getDeclaredField("score")` to find private metadata. Because the caller is a different top-level class, `canAccess(state)` initially returns `false`. On the classpath/unnamed module with no additional restrictions, `trySetAccessible()` returns `true`, and then `getInt(state)` reads `10`.
- `MethodHandles.privateLookupIn(HiddenState.class, MethodHandles.lookup())` obtains a lookup with private access suitable for the test environment. `findVarHandle` locates the `score` field.
- `score.get(state)` reads `10`, `score.set(state,20)` writes `20`.
- `score.toMethodHandle(VarHandle.AccessMode.GET)` creates **a MethodHandle specifically for the GET access mode**. That handle has `type() == (HiddenState)int` and is invoked via `(int) getter.invokeExact(state)`.
- After VarHandle has written `20`, the getter MethodHandle reads the same field and returns `20`.

**Do not draw the wrong conclusion:** `privateLookupIn` is not a mechanism that automatically breaks module encapsulation. If `HiddenState` were in another named module whose package is not `opens` to the caller, obtaining a private lookup could be rejected. The program demonstrates valid access **within the same unnamed module**, not permission outside that scope.

### 6.1. What is `toMethodHandle` used for?

Each `VarHandle.AccessMode` corresponds to a specific invocation signature. `toMethodHandle(mode)` lets you convert an access mode into a MethodHandle that can be passed into Method Handles combinator APIs or invoked when a single callable handle is needed.

Example:

```java
MethodHandle get = vh.toMethodHandle(VarHandle.AccessMode.GET);
MethodHandle cas = vh.toMethodHandle(VarHandle.AccessMode.COMPARE_AND_SET);
```

This is an **illustrative snippet** with a previously created variable `vh`. `get.type()` and `cas.type()` have different signatures. They **do not replace** the original VarHandle with a MethodHandle that has all access modes; you have selected **one specific operation**.

Some systems use `MethodHandles.varHandleInvoker(...)` or `varHandleExactInvoker(...)` when they need to build an invoker that takes a VarHandle as an argument. Only use this complex form when dynamic composition is truly needed; for a fixed field and mode, calling `vh.get(...)`/`vh.compareAndSet(...)` directly is easier to understand.

## 7. Access modes: plain, opaque, acquire/release, volatile, atomic

The Java Memory Model cares not only about values, but also about **observable ordering between threads**. For the same field, `VarHandle` lets you choose read/write semantics:

| Group | Corresponding read / write | Summary meaning |
| --- | --- | --- |
| **Plain** | `get`, `set` | Similar to non-volatile field read/write; **provides no ordering guarantees between threads** |
| **Opaque** | `getOpaque`, `setOpaque` | Guarantees atomicity/coherence per variable in this mode, but weak inter-thread ordering |
| **Acquire / Release** | `getAcquire`, `setRelease` | When properly paired, guarantees ordering for data read after acquire and written before release |
| **Volatile** | `getVolatile`, `setVolatile` | Has strong volatile semantics, participates in JMM volatile order |
| **Atomic update** | `compareAndSet`, `compareAndExchange`, `getAndSet` | Atomic update operations; each variant has defined ordering |
| **Atomic numeric/bitwise** | `getAndAdd`, `getAndBitwiseOr`, `getAndBitwiseAnd`, `getAndBitwiseXor` | Atomic value modification for supported types |

**Warning:** "atomicity" of **a single access** does not mean an entire sequence of multiple instructions is atomic. `getVolatile` followed by `setVolatile` still does not automatically become an atomic addition. Only `getAndAdd` is a supported atomic read–modify–write operation.

### 7.1. Plain is not enough for inter-thread coordination

`get`/`set` are designed with semantics like non-volatile fields. If thread A writes several fields and sets a flag with a plain write, thread B spinning with a plain read **does not have a valid data publication protocol**. The JMM can allow behavior that is counterintuitive from source code order; do not rely on "it seemed to work on my machine".

Atomicity guarantees of plain read/write also have limits based on size and platform; for example `long`/`double` on some 32-bit platforms are not guaranteed to be bitwise atomic in plain mode. `getVolatile` and stronger modes have different guarantees, per the JDK API.

### 7.2. Acquire/Release for data publication

A communication pattern consists of the producer writing data first, then **release-writing** a flag; the consumer **acquire-reads** the flag successfully before reading the published data:

```java
// Illustrative model: FlagBox has int payload and boolean ready;
// READY is a VarHandle pointing to boolean ready on FlagBox.

// Producer thread:
box.payload = 42;
READY.setRelease(box, true);

// Consumer thread:
while (!(boolean) READY.getAcquire(box)) {
    Thread.onSpinWait();
}
int publishedValue = box.payload;
```

**These are only two snippets belonging to two threads, not a standalone program**: the class, handle, thread lifecycle, and termination condition are not declared. An acquire read observing a matching release on the same variable establishes ordering for data written before the release. In real applications, you need a termination/cancellation mechanism and should avoid unbounded spinning.

Using `getAcquire` while the producer still uses a plain `set`, or placing the `payload` write after `setRelease`, will not properly establish this data publication pattern.

### 7.3. Volatile is ordering, not "atomic addition"

`getVolatile` and `setVolatile` provide semantics equivalent to the respective volatile accesses, yet the code:

```java
// Illustrative: COUNT is a VarHandle to the int value field.
int current = (int) COUNT.getVolatile(counter);
COUNT.setVolatile(counter, current + 1);
```

still has a race: two threads can read the same `current`. If the goal is an accurate counter, use `getAndAdd` or an appropriate CAS loop. If multiple fields must be coordinated under a shared invariant, sometimes `synchronized`/`Lock` is simpler and more correct.

### 7.4. A `volatile` declaration does not force every VarHandle mode to be volatile

A field declared `volatile int value` can still be accessed with `vh.get(obj)`, i.e. **plain mode**, if the API supports that mode. `VarHandle` uses the semantics of the chosen access mode, **overriding the memory ordering effect from the declaration** for that specific operation. Mixing plain and volatile accesses on the same variable without a clear JMM design easily creates subtle bugs.

Do not interpret "VarHandle is for concurrency" as "every `vh.get()` is thread-safe". You must choose the mode appropriate for the actual protocol.

### 7.5. CAS, exchange, and success conditions

- `compareAndSet(coordinates..., expected, next)` returns **`boolean`**: `true` when the current value equals expected according to the operation's comparison and the update succeeds, otherwise `false`.
- `compareAndExchange(coordinates..., expected, next)` returns the **witness / value observed before the operation**; to know whether it changed, compare the witness with expected according to that type's semantics.
- `getAndSet(coordinates..., next)` replaces the value and returns the **previous value**.
- `getAndAdd(coordinates..., delta)` atomically adds to a suitable numeric type and returns the **previous value**.
- The `weakCompareAndSet...` variants can **fail spuriously** even when the current value equals expected; the program must be properly designed to retry when using these variants.

For **reference values**, compare-and-set compares **reference identity** (`==`), without calling `.equals()`. A different object with equal contents will not automatically match as the expected reference.

Atomic update does not mean never having to retry: `compareAndSet` can return `false` when another thread changes the value first; that is a normal contention path. Using CAS in a loop must account for fairness, contention, and handling of business exceptions.

## 8. Complete example 3: array elements via VarHandle

A `VarHandle` created with `MethodHandles.arrayElementVarHandle(int[].class)` is not tied to **one** fixed index; it describes a **family of elements** of type `int`, with coordinates `(int[] array, int index)`.

Create **`ArrayVarHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class ArrayVarHandleDemo {
    public static void main(String[] args) {
        int[] numbers = {3, 5};
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);

        System.out.println("var type: " + element.varType().getSimpleName());
        System.out.println("coordinate count: " + element.coordinateTypes().size());
        System.out.println("initial index 1: " + (int) element.get(numbers, 1));

        element.set(numbers, 1, 7);
        boolean changed = element.compareAndSet(numbers, 1, 7, 10);
        System.out.println("CAS: " + changed);
        System.out.println("old: " + (int) element.getAndAdd(numbers, 1, 3));
        System.out.println("array[1]: " + numbers[1]);

        try {
            int ignored = (int) element.get(numbers, 99);
            System.out.println(ignored);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("invalid index: ArrayIndexOutOfBoundsException");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 ArrayVarHandleDemo.java
java ArrayVarHandleDemo
```

Verified stdout:

```text
var type: int
coordinate count: 2
initial index 1: 5
CAS: true
old: 10
array[1]: 13
invalid index: ArrayIndexOutOfBoundsException
```

Explanation: `element.set(numbers,1,7)` writes `7`; CAS sees `7` so it updates to `10`; `getAndAdd(numbers,1,3)` returns `10` and changes the element to `13`. Index `99` is not within the 2-element array, so it throws `ArrayIndexOutOfBoundsException`.

When you need to control access semantics on individual elements, `VarHandle` is especially suitable. It does **not** resize arrays, does not allow skipping bounds checking, and does not turn an array element into an object described by Reflection `Field` as an individual field.

### 8.1. Byte-array/ByteBuffer views are not simply array elements

Beyond `T[]` arrays, Java has factories for byte array/ByteBuffer views by component type and byte order, for example `MethodHandles.byteBufferViewVarHandle(int[].class, java.nio.ByteOrder.BIG_ENDIAN)`.

These views have **alignment, position, and component-type constraints**. Certain access modes are invalid when the address is unaligned, and read-only buffer regions do not accept write modes. Do not generalize CAS succeeding on `int[]` in the previous example to every ByteBuffer view and every offset.

## 9. Complete example 4: multi-threaded atomic counter

An appropriate `getAndAdd` on an `int` field allows multiple threads to increment a shared counter without losing increments due to read–modify–write races. This program creates 4 threads, each incrementing 5,000 times, then calls `join()` to confirm they have finished.

Create **`AtomicVarHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class AtomicVarHandleDemo {
    private static final class Counter {
        volatile int value;
    }

    private static final VarHandle VALUE;
    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        int workerCount = 4;
        int iterations = 5_000;
        Thread[] threads = new Thread[workerCount];

        for (int i = 0; i < workerCount; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < iterations; j++) {
                    int previous = (int) VALUE.getAndAdd(counter, 1);
                }
            });
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("expected: " + workerCount * iterations);
        System.out.println("actual: " + (int) VALUE.getVolatile(counter));
    }
}
```

Commands:

```bash
javac --release 17 AtomicVarHandleDemo.java
java AtomicVarHandleDemo
```

Verified stdout:

```text
expected: 20000
actual: 20000
```

In this example:

- Each `getAndAdd(counter,1)` atomically updates and returns the previous value. The local variable `previous` in the example is not used further; it is present to express the exact `int` return type for the signature-polymorphic call site.
- `Thread.join()` ensures `main` only reads the result after the workers have finished.
- `getVolatile` reads the final value with volatile semantics. Do not use plain `get` as the basis for designing communication between running threads.
- After 4 × 5,000 atomic updates, the expected result is `20.000` with no lost updates. In a real application, one also needs to consider integer overflow, counter lifetime, and throughput under high contention.

**Design note:** If you only need a standalone counter, `AtomicInteger` is usually easier to read and sufficient. `VarHandle` shines when you need to update **an existing field in an object** or array elements, want to choose memory modes, and avoid changing data layout with separate wrapper objects. For counters under very high contention, `LongAdder` may be more suitable depending on total-read and consistency requirements, though it does not replace all cases that require CAS on the same variable.

## 10. Complete example 5: static field and final field

A static field needs no receiver; a final field is treated by VarHandle as a **read-only** variable with respect to write/atomic update modes.

Create **`StaticAndFinalVarHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class StaticAndFinalVarHandleDemo {
    private static int global = 3;

    private static final class Immutable {
        private final int amount = 7;
    }

    private static final VarHandle GLOBAL;
    private static final VarHandle AMOUNT;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            GLOBAL = lookup.findStaticVarHandle(
                    StaticAndFinalVarHandleDemo.class, "global", int.class);
            AMOUNT = lookup.findVarHandle(
                    Immutable.class, "amount", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) {
        System.out.println("static coordinates: " + GLOBAL.coordinateTypes().size());
        System.out.println("static before: " + (int) GLOBAL.get());
        GLOBAL.set(5);
        System.out.println("static after: " + (int) GLOBAL.get());

        Immutable immutable = new Immutable();
        System.out.println("final read: " + (int) AMOUNT.get(immutable));
        System.out.println("final set supported: "
                + AMOUNT.isAccessModeSupported(VarHandle.AccessMode.SET));
        try {
            AMOUNT.set(immutable, 9);
        } catch (UnsupportedOperationException e) {
            System.out.println("final set: UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 StaticAndFinalVarHandleDemo.java
java StaticAndFinalVarHandleDemo
```

Verified stdout:

```text
static coordinates: 0
static before: 3
static after: 5
final read: 7
final set supported: false
final set: UnsupportedOperationException
```

`GLOBAL` has **zero coordinate types** because a static field is a shared location of the class; `GLOBAL.get()` passes no receiver. `AMOUNT` has one coordinate of type `Immutable`, so `AMOUNT.get(immutable)` requires an instance.

Because `amount` is final, `AMOUNT.isAccessModeSupported(SET)` returns `false`. Calling `AMOUNT.set(immutable,9)` does not "unlock final" — it throws `UnsupportedOperationException`. Likewise, atomic update modes that modify a final field are also unsupported. Do not treat `VarHandle` as a tool to bypass immutability.

## 11. VarHandle access modes have invoke behavior and invoke-exact behavior

This is a technical difference easily overlooked when comparing with `MethodHandle`:

- **`MethodHandle.invokeExact`:** requires the call-site `MethodType` to match the handle's `type()` **exactly**, including parameter and return types; no automatic conversion.
- **Normally created `VarHandle`:** default access-mode invocation typically has **invoke behavior**, allowing valid conversions similar to `MethodHandle.invoke` via `asType`.
- **`VarHandle.withInvokeExactBehavior()`:** returns a handle accessing the same variable but requiring an exact call-site access-mode type; use `hasInvokeExactBehavior()` to check which mode the handle is in.
- **`VarHandle.withInvokeBehavior()`:** returns a handle with invoke behavior when flexible conversion rules are desired again.

The following complete example shows the same `int` field, but the caller uses a receiver of type `Object` and expects a `long` return; the default can adapt, whereas exact mode rejects the return mismatch.

Create **`VarHandleModeDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleModeDemo {
    private static class Cell {
        int count = 42;
    }
    public static void main(String[] args) throws ReflectiveOperationException {
        Cell c = new Cell();
        VarHandle flexible = MethodHandles.lookup().findVarHandle(
                Cell.class, "count", int.class);
        VarHandle strict = flexible.withInvokeExactBehavior();
        Object broaderReceiver = c;
        long adapted = (long) flexible.get(broaderReceiver);
        System.out.println("flexible: " + adapted);
        System.out.println("strict: " + strict.hasInvokeExactBehavior());
        try {
            long wrong = (long) strict.get(c);
            System.out.println(wrong);
        } catch (WrongMethodTypeException e) {
            System.out.println("strict wrong: WrongMethodTypeException");
        }
        int right = (int) strict.get(c);
        System.out.println("strict right: " + right);
    }
}
```

Run:

```bash
javac --release 17 VarHandleModeDemo.java
java VarHandleModeDemo
```

Verified stdout:

```text
flexible: 42
strict: true
strict wrong: WrongMethodTypeException
strict right: 42
```

Explanation:

1. `flexible.get(broaderReceiver)` uses a receiver with static type `Object` that actually holds a `Cell`, while casting the result to `long` when the variable is `int`. With default invoke behavior, valid reference casts and primitive widenings are applied, returning `42`.
2. `strict` comes from `withInvokeExactBehavior()`, having `hasInvokeExactBehavior() == true`.
3. `(long) strict.get(c)` requests a `long` return at the call site whereas the access-mode type returns `int`, so it throws `WrongMethodTypeException`.
4. `(int) strict.get(c)` creates a call site matching both receiver `Cell` and return `int`, so it succeeds.

This does not turn `VarHandle` into a `MethodHandle`: it still represents a **variable** and its access modes. "Invoke" / "invoke-exact" in VarHandle refers to **type-checking/conversion behavior when calling access-mode methods**, not calling arbitrary methods like `MethodHandle`.

**Do not use conversions to mask design errors:** If the caller intends to access a field of another class, verify the coordinates up front instead of passing everything as `Object` and waiting for a runtime cast.

## 12. Which access modes are supported? Do not guess

Not every `VarHandle` supports every mode. Support depends on:

- Variable type: for example, numeric atomic add fits supported numeric types; not every reference/primitive allows `getAndAdd`.
- Mutability: a `final` field is read-only and does not support set/CAS/add/bitwise updates.
- How the handle was created: instance fields, arrays, and byte-array/ByteBuffer views can have different constraints.
- Runtime conditions: read-only buffers, alignment, out-of-bounds indices, or a null receiver can cause corresponding exceptions at execution time.

To check beforehand:

```java
if (handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)) {
    // Only this branch is allowed to call the appropriate getAndAdd.
}
```

This is an **illustrative snippet**, not a standalone program. If `isAccessModeSupported` returns `false`, executing that mode will throw `UnsupportedOperationException`; it does not "downgrade" to a weaker mode. You must choose an alternative path according to business requirements.

The final-field example already proved that `SET` is unsupported. For types without addition such as `Object` or `String`, do not assume `getAndAdd` is available; if conditional reference updates are needed, consider `compareAndSet` with identity semantics.

### 12.1. Target memory region and coordinate errors

A valid handle can still be invoked with invalid coordinates:

- An instance field with a `null` receiver can throw `NullPointerException`.
- A receiver of an incompatible type can lead to `ClassCastException` or a type mismatch depending on invoke behavior.
- An array element with an out-of-bounds index throws `ArrayIndexOutOfBoundsException`.
- A ByteBuffer/byte-array view can encounter bounds, read-only, and alignment errors when a mode requires atomicity.
- An incompatible call-site `MethodType`, especially in exact mode, can throw `WrongMethodTypeException`.

Do not catch all of these errors and return a meaningless default value. Report the **handle, access mode, coordinates, and expected contract**, while preserving the root cause for diagnostics.

## 13. Common mistakes when choosing an API

### 13.1. "VarHandle is Field with a faster way to read"

Inaccurate. `Field` is a metadata object for **a single field**, whereas `VarHandle` is a typed capability to **a variable / family of variables** with access modes. A `VarHandle` to `int[]` handles array elements via `(array,index)`, which cannot be simply described as a reflected `Field`.

### 13.2. "VarHandle replaces all MethodHandles"

False. `MethodHandle` can represent methods, constructors, getters/setters, or compositions of transformations. `VarHandle` does not replace arbitrary method invocation or general adapter graphs. If you need dynamic dispatch to a method `calculate(x,y)`, `MethodHandle` is usually more natural.

### 13.3. "MethodHandle cannot access fields"

False. `Lookup.findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter` create MethodHandles for field access; `VarHandle.toMethodHandle(mode)` can also convert a mode into a callable handle. The core difference is that **VarHandle lets you choose multiple access modes on the same logical variable**.

### 13.4. "Field has no volatile semantics"

False. Core Reflection accesses a `volatile` field with semantics appropriate for that field. `VarHandle`'s advantage is specifying semantics **directly at the call site**, even when the declaration does not have `volatile`.

### 13.5. "Using `getVolatile` and `setVolatile` will not lose increments"

False, because a read–compute–write sequence does not become atomic. Use `getAndAdd`, a proper `compareAndSet` loop, or locks if an invariant requires updating multiple variables together.

### 13.6. "`compareAndSet` compares references using `equals`"

False. For reference variables, comparison uses identity `==`. Two different `String` objects with the same content do not automatically guarantee CAS matches the expected reference.

### 13.7. "VarHandle to a private field is a way to bypass Java modules"

False. Handle creation uses `Lookup` and must have corresponding permissions. `privateLookupIn` has JPMS constraints; if the package is not opened to the caller module when a private lookup is needed, it can throw `IllegalAccessException`.

### 13.8. "`final` can be `set` once a VarHandle is created"

False. A read-only variable does not support write/update modes and throws `UnsupportedOperationException`. Core Reflection's `setAccessible(true)` is also not a general-purpose means to safely mutate any final field.

### 13.9. "Every VarHandle is exact like `invokeExact`"

False for default-created VarHandles in Java 17: access-mode calls have **invoke behavior**. Only when using `withInvokeExactBehavior()` is exact matching required under that mechanism. Distinguish this behavior when troubleshooting `WrongMethodTypeException`.

### 13.10. "Atomic means every processing block is lock-free and faster"

Not guaranteed. Operation atomicity is a semantic property; libraries/JVM/hardware may have different implementations. Performance can vary with contention and access mode; measure on the specific workload. Atomicity on **one variable** also does not automatically preserve invariants involving **multiple variables**.

## 14. How to choose the tool in real-world projects

Scenario 1 — **Serializer reading schemas and annotations**: needs field name, generic type, annotations, modifiers, declaring class. Choose `Field` to discover metadata; when reading/writing, obey access rules. If the framework needs many atomic update operations on a field, it can switch to `VarHandle` after handling lookup properly.

Scenario 2 — **Invoking a method identified at runtime by class/name**: choose `MethodHandle` for a method/constructor with a specific `MethodType`. Leverage `bindTo`, `asType`, and combinators when dynamic call chains are needed.

Scenario 3 — **A counter variable already residing in each object**: choose `VarHandle` if you need atomic increment/CAS without turning the domain model into many wrapper objects. If you only need a standalone atomic value, `AtomicInteger` can be more readable.

Scenario 4 — **State publication flag between threads**: design a clear Java Memory Model protocol; you can use `volatile`, `synchronized`, concurrency libraries, or `VarHandle.setRelease/getAcquire` when you understand the required ordering. Choose the weakest mode only when there is a sound reason and it has been verified.

Scenario 5 — **Updating array elements via CAS**: `arrayElementVarHandle` provides coordinates `(array,index)` and atomic updates on suitable elements, whereas `Field` does not represent individual elements as fields.

Scenario 6 — **Opening private state of another module**: first consider a public API. If it is genuinely a valid framework needing deep access, grant targeted permission on the module/package (e.g., appropriate `opens`). Do not assume replacing `Field` with `VarHandle` bypasses access errors.

### 14.1. Design principles when introducing VarHandle into a codebase

- Create handles in an appropriate place, typically at class/component initialization; **do not look up by field name on every hot-path operation**.
- Keep handles with private access within trusted scope, as they are a **capability** whose permission was verified at creation time.
- Document the access mode corresponding to the concurrency protocol; avoid mixing plain and volatile unintentionally.
- Check `varType`, `coordinateTypes`, and `accessModeType` when building dynamic frameworks.
- Check `isAccessModeSupported` when a mode is not obviously supported, especially on final fields and data views.
- Keep tests for lookup failures, module access, read-only, receiver/index mismatch, unsupported mode, and concurrency correctness.
- For simple data types with minimal concurrency requirements, prefer plain Java code over an unnecessary layer of dynamic access.

## 15. Quick diagnostic table

| Error / symptom | Phase | Common cause | How to handle |
| --- | --- | --- | --- |
| `NoSuchFieldException` from `findVarHandle` | Lookup | Wrong name, wrong declared type, static/instance mix-up | Check the actual declaration; use the right factory/field type |
| `IllegalAccessException` from lookup | Handle creation | `Lookup` lacks permission or JPMS blocks private lookup | Fix public API design / appropriate module `opens`; do not bypass |
| `WrongMethodTypeException` at access mode | Invoke | Call-site parameter/return incompatible with access-mode type; strict exact behavior | Print `accessModeType`, check coordinates, primitive/reference types, return |
| `ClassCastException` | Conversion/receiver | Runtime object does not have the type required by conversion | Check object type and adapter policy |
| `UnsupportedOperationException` | Invoke access mode | Variable does not support mode, e.g., write to final | Use `isAccessModeSupported`; choose appropriate mode/factory |
| `NullPointerException` | Locating instance variable | Receiver/array has no object | Check coordinates and input |
| `ArrayIndexOutOfBoundsException` | Array access | Index not within array | Check index; do not treat as access-control error |
| Counter result smaller than expected | Concurrency logic | Split read–write, race/lost update | Use atomic RMW or locking; test multi-threaded |
| A thread does not see published data | Memory ordering | Missing acquire/release/volatile synchronization | Design proper happens-before per JMM |
| `Field.canAccess` false yet `VarHandle` works in other code | Different access models | Field checks access at call; VarHandle capability is granted upon valid lookup | Check caller/module and where handle was created, do not treat as bypass |

When diagnosing, start with **whether the target is a variable or a method call**, followed by **the required mode and type signature of the operation**. Do not change visibility, concurrency mode, or API merely because of a generic error message.

## 16. Self-check questions

**Question 1.** What is the difference in purpose between `Field` and `VarHandle`?

**Answer:** `Field` provides metadata and field read/write APIs; `VarHandle` is a typed reference to a variable/family of variables with multiple access modes including plain, volatile, and atomic updates. Both remain subject to Java access control and module boundaries.

**Question 2.** What are the variable type and coordinate types of instance field `int Box.count`?

**Answer:** `varType() == int.class`, `coordinateTypes() == [Box.class]`. `get` needs a Box receiver; `compareAndSet` also needs expected and replacement values.

**Question 3.** Why does a static field handle have `coordinateTypes().size() == 0`?

**Answer:** A static field is not tied to an object instance. A class has one corresponding static field location in the runtime/class loader context; the access call passes no receiver.

**Question 4.** How does `compareAndSet(box,5,8)` differ from `if (get(box)==5) set(box,8)`?

**Answer:** CAS is an atomic read–compare–write operation when the mode is supported; two separate calls can be interleaved by another thread.

**Question 5.** If two threads both increment `volatile int count` using `count++`, is the exact increment count guaranteed?

**Answer:** No. `volatile` does not turn the three steps read–add–write into an atomic operation. Use `getAndAdd`, a CAS loop, or appropriate synchronization.

**Question 6.** Why can `VarHandle` read a final field while `set` throws `UnsupportedOperationException`?

**Answer:** A final field is treated as a read-only variable for VarHandle; write/update modes are not supported. Check `isAccessModeSupported(SET)` first.

**Question 7.** How does a MethodHandle created from `vh.toMethodHandle(GET)` differ from the VarHandle itself?

**Answer:** The MethodHandle only represents the selected GET operation with its corresponding `MethodType`. The original VarHandle still provides the entire set of modes for the same variable (if supported).

**Question 8.** If you need to access a private field located in another module, does `findVarHandle` always bypass JPMS protection?

**Answer:** No. Lookup checks permissions when creating the handle; a private lookup may require the package to be opened to the caller module. You must handle it properly via a public API or intentional `opens`.

**Question 9.** Is a default-created VarHandle in Java 17 completely identical to `MethodHandle.invokeExact` regarding conversions?

**Answer:** No. Default VarHandle access-mode calls have invoke behavior, which can adapt valid conversions; only `withInvokeExactBehavior()` switches to exact behavior.

**Question 10.** Does `getAndAdd(box,1)` return the value after adding or before adding?

**Answer:** The value **before** adding. The variable is updated atomically; the caller can read it again with an appropriate mode if the new value is needed.

**Question 11.** What coordinates must a `VarHandle` to `int[]` pass to `get`?

**Answer:** The `int[]` array and the `int` index. `varType()` is `int`; an invalid index throws a bounds exception.

**Question 12.** When should you choose `AtomicInteger` instead of `VarHandle`?

**Answer:** For a standalone atomic variable that does not need to access an existing field or custom memory modes, `AtomicInteger` is usually simpler. `VarHandle` is suited for fields/array elements and specialized access-mode protocols.

## 17. Official references

- **Java SE 17 `VarHandle` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html — variable/coordinate types, access modes, invocation behavior, memory ordering, `isAccessModeSupported`.
- **Java SE 17 `VarHandle.AccessMode` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html — name and role of each mode.
- **Java SE 17 `MethodHandles` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — `arrayElementVarHandle`, buffer views, invokers.
- **Java SE 17 `MethodHandles.Lookup` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — `findVarHandle`, `findStaticVarHandle`, lookup permissions.
- **Java SE 17 `MethodHandle` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — typed invocations, `invokeExact`, `invoke`, adapters.
- **Java SE 17 `Field` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html — metadata, `get`/`set`, modifiers.
- **JEP 193 — Variable Handles:** https://openjdk.org/jeps/193 — rationale behind VarHandle design and access modes.
- **Java Language Specification 17 — Memory Model:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4 — synchronization and happens-before.

**Conclusion:** `VarHandle` solves the problem of **accessing a variable with memory semantics specified at each operation**. `Field` serves field discovery and manipulation via Reflection; `MethodHandle` serves typed invocations. Choose the right tool based on **access intent, concurrency control, module permissions, and data contracts**, rather than merely comparing API names or guessing performance.