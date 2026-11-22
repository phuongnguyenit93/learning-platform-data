# 9.8 Checking `isAccessModeSupported` and Read-Only Variable Limits

`java.lang.invoke.VarHandle` provides a mechanism to access variables across multiple **access modes**: plain reads, reads/writes with different memory semantics, compare-and-set (CAS), value exchange, or atomic updates. However, **not every mode is supported by every VarHandle**. A `final` field is a prime example: it can be read via a VarHandle, but a VarHandle cannot be used to write or CAS to that field itself.

The central method is:

```java
boolean supported = handle.isAccessModeSupported(
        VarHandle.AccessMode.COMPARE_AND_SET);
```

This is an illustrative fragment: the variable `handle` is assumed to be a `VarHandle` that has already been looked up or created, and `java.lang.invoke.VarHandle` has been imported.

A result of `true` means **the mode is supported by the VarHandle at the level of the variable kind/handle provider**; it is not a guarantee that **every call** with **every specific object** will succeed. A notable example: a VarHandle viewing a `ByteBuffer` as an `int` array may report that `SET` is supported, but when passing **a buffer currently in read-only mode**, writing will throw `ReadOnlyBufferException`.

> **Practice environment:** Java 17 or higher; the four standalone programs below compile with `javac --release 17`. All outputs are verified against actual execution results. This lesson focuses on **mode limits and read-only variables**, and is not intended to replace a full lesson on the Java Memory Model.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what `VarHandle.isAccessModeSupported(AccessMode)` returns and when to check it.
- Distinguish `GET`, `SET`, `GET_VOLATILE`, `COMPARE_AND_SET`, `GET_AND_ADD`, and `GET_AND_BITWISE_OR` by operation group.
- Understand why `final` instance fields and `static final` fields **can only be read via VarHandle**, even when code has lookup access.
- Avoid confusing a **`final` reference to an array** with **the elements of the array being immutable**.
- Distinguish **unsupported mode** (`UnsupportedOperationException`) from **supported mode where the current receiver forbids writing** (`ReadOnlyBufferException`).
- Read `varType()`, `coordinateTypes()`, and `accessModeType(...)` to accurately locate the variable and call signature.
- Design safe fallback branches without accidentally replacing an atomic operation with a non-atomic read–write sequence.

## 2. `VarHandle` Describes a Variable and Coordinates, Not a Fixed Value

A `VarHandle` does not simply hold a value; it is a strongly typed reference to **a variable** or **a family of variables**. Depending on how the handle is created, it can access:

| Target | Common factory/lookup | Coordinates (coordinate types) |
| --- | --- | --- |
| Instance field `int counter` | `lookup.findVarHandle(Owner.class, "counter", int.class)` | `(Owner)` |
| Field `static int limit` | `lookup.findStaticVarHandle(Owner.class, "limit", int.class)` | No coordinates |
| Element of `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | `(int[], int)` |
| Data slot in `ByteBuffer` with `int` view | `MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.LITTLE_ENDIAN)` | `(ByteBuffer, int)` |

Here, "coordinates" are the arguments that identify **the location of the variable**: the object containing the field, the array and index, or the buffer and byte index. After the coordinates, some access modes also require a new value, an expected value for CAS, an addition delta, or a bitwise mask.

Inspection API:

```java
Class<?> type = handle.varType();
java.util.List<Class<?>> coords = handle.coordinateTypes();
java.lang.invoke.MethodType signature =
        handle.accessModeType(VarHandle.AccessMode.GET);
```

This is a non-standalone fragment; `handle` is assumed to be initialized. For an instance `int` field of `Owner`, `varType()` is `int.class`, and `coordinateTypes()` is a list containing `Owner.class`. For a static field, the coordinate list is empty. This information is useful when debugging mismatches in argument count or types.

**Important:** `accessModeType(mode)` only describes **the type signature of that mode**; it does not mean that mode is supported. Use `isAccessModeSupported(mode)` to check capability before calling the access mode with the right coordinates/types.

## 3. `AccessMode` Groups and Semantics

`VarHandle.AccessMode` is an enum whose names correspond to `VarHandle` methods. Some representatives:

| Group | Example modes | Call form / meaning |
| --- | --- | --- |
| Read | `GET`, `GET_OPAQUE`, `GET_ACQUIRE`, `GET_VOLATILE` | Retrieves the value according to the corresponding memory ordering constraint level |
| Write | `SET`, `SET_OPAQUE`, `SET_RELEASE`, `SET_VOLATILE` | Assigns a new value according to the corresponding memory ordering constraint level |
| Atomic compare-and-update | `COMPARE_AND_SET`, `COMPARE_AND_EXCHANGE`, `WEAK_COMPARE_AND_SET` and variants | Compares the current value with the expected value, and conditionally replaces the value |
| Atomic exchange | `GET_AND_SET` and variants | Writes a new value, returns the previous value |
| Atomic addition | `GET_AND_ADD` and variants | Adds delta, returns the old value |
| Atomic bitwise | `GET_AND_BITWISE_OR`, `GET_AND_BITWISE_AND`, `GET_AND_BITWISE_XOR` and variants | Modifies bits according to the corresponding operation, returns the previous value |

Suffixes such as `Acquire`, `Release`, `Volatile`, and `Opaque` relate to **memory ordering and synchronization between threads**. They do not by themselves make a final variable writable. Using a specific access mode requires an appropriate synchronization contract; it is not a "privilege escalation" or a way to force writes to a read-only variable.

### 3.1. Groups Do Not Always Support the Same Data Types

Do not conclude that because `SET` is supported, `GET_AND_ADD` is also supported. For regular fields:

- Type `int` can support `GET_AND_ADD` and bitwise modes.
- Reference type `String` can support `COMPARE_AND_SET` or `GET_AND_SET`, but not `GET_AND_ADD` or `GET_AND_BITWISE_OR`.
- Numeric atomic update operations only apply to compatible primitive numeric types; bitwise atomic update operations only apply to integral/boolean types specified by the factory documentation.
- If the variable is `final`, **write and update** modes are all unsupported, even if the field type is `int`, which supports atomic addition when non-final.

Therefore, capability is determined by **how the VarHandle is created + variable kind + variable type + factory constraints**. There is no single table saying "every VarHandle supports all modes".

### 3.2. Checking Modes by Enum, Not by String Name

Use the provided enum:

```java
import java.lang.invoke.VarHandle;

boolean canRead = handle.isAccessModeSupported(
        VarHandle.AccessMode.GET);
boolean canWrite = handle.isAccessModeSupported(
        VarHandle.AccessMode.SET);
boolean canCas = handle.isAccessModeSupported(
        VarHandle.AccessMode.COMPARE_AND_SET);
```

This is an illustrative fragment. Do not construct the string `"COMPARE_AND_SET"` and assume that name automatically enables a capability; the overload taking `AccessMode` performs the check.

## 4. Contract of `isAccessModeSupported`

Practical definition:

- Returns `true`: the VarHandle has a valid implementation to perform the queried mode **for the kind of variable the handle represents**.
- Returns `false`: calling the corresponding access mode method will throw **`UnsupportedOperationException`**.
- The `GET` mode is supported by **every VarHandle**, so `GET` does not throw `UnsupportedOperationException` (but can still throw other errors when coordinates/objects are invalid).
- The result does not pre-check **the receiver value passed in later**, such as whether a buffer is read-only, whether an index is within bounds, whether a class is initialized, or whether the call-site method has the right type.
- The result does not indicate Reflection/lookup permissions or module permissions. Access checks to **obtain the VarHandle** are handled at the separate lookup step.

The last point is crucial. A VarHandle may support `SET` at the "ByteBuffer variable family" level, yet a specific `ByteBuffer` is still read-only. Runtime conditions can cause the call to fail after the capability check has returned `true`.

### 4.1. Checking Mode Before Designing the Call

A simple approach:

```java
// Fragment: counter is a VarHandle on an int field and state is a receiver of the right type.
if (counter.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)) {
    int old = (int) counter.getAndAdd(state, 1);
    System.out.println("old=" + old);
} else {
    throw new UnsupportedOperationException(
            "This VarHandle does not support atomic addition");
}
```

This is not a standalone program; the logic assumes the variables already exist. The error branch does not choose `counter.set(state, (int) counter.get(state) + 1)` as a replacement because read–compute–write is **no longer atomic**. If atomicity is required, a fallback must have a proper synchronization contract, such as an appropriate lock, or switch to a different data design.

If only reading is needed, `get(...)` can be used without checking support beforehand, though the coordinates and call-site return type must still be prepared correctly.

## 5. `final` Variables: Readable, Not Writable via VarHandle

According to the VarHandle and Lookup specification:

- `final int id` (instance field): the VarHandle has the owning object as its coordinate; read modes can be used. **`SET`, `SET_VOLATILE`, CAS, and atomic updates are not supported.**
- `static final int LIMIT`: the VarHandle has empty coordinates and still only supports read modes; no receiver object is passed to `get()`.
- `final` is a restriction on **the variable referenced by the VarHandle itself**. Even if code has permission to find a handle to a private final field, that lookup permission **does not turn the field into a mutable one**.
- `volatile` is not like `final`. A non-final `volatile int counter` can support `SET`, `COMPARE_AND_SET`, `GET_AND_ADD`; the choice of mode still determines the actual memory ordering.

Summary table of typical modes for an instance `final int` field:

| Access mode | Supported? | Explanation |
| --- | --- | --- |
| `GET` | Yes | Plain read |
| `GET_OPAQUE`, `GET_ACQUIRE`, `GET_VOLATILE` | Yes for this field's VarHandle | Read forms with corresponding memory semantics |
| `SET`, `SET_RELEASE`, `SET_VOLATILE` | No | A final field cannot be reassigned via VarHandle |
| `COMPARE_AND_SET`, `COMPARE_AND_EXCHANGE` | No | CAS is also an update, not just a read |
| `GET_AND_SET`, `GET_AND_ADD`, `GET_AND_BITWISE_OR` | No | These operations have write capability |

If you attempt to call an unsupported mode with valid arguments, the result is `UnsupportedOperationException`, not a silent modification of the field. This is a limitation **of the VarHandle API**, independent of the caller's wish of "running in the same class".

### 5.1. Why `final` Does Not Equal `immutable object`

`final` protects against **reassigning the field variable** after initialization under the language contract; it does not automatically make the object the field references immutable.

For example:

```java
final int[] values = {1, 2};
```

This is a **local variable fragment**. You cannot assign `values = otherArray` after the final assignment, but you can still execute `values[0] = 9`. The same principle applies to `final int[] values` as a field: the VarHandle of the **array reference field** only allows reading, whereas another VarHandle pointing to **array elements** can allow writing or atomic updates.

**Similarly**, a `final List<T>` field does not automatically forbid operations that add/remove/modify the **contents** of the List. VarHandle restricts reassigning the field itself; deep immutability of an object is a separate design contract.

### 5.2. `static final` and Compile-Time Constants

`static final int LIMIT = 11` may be a **compile-time constant**. Other Java code may have inlined that value into bytecode at compile time. This does not grant extra update permissions via VarHandle; `SET` on a final field remains unsupported. Do not try to use VarHandle to "change a constant application-wide", because both write restrictions and inlining work against that expectation.

## 6. Practice 1 — Checking Modes on Final Instance/Static Fields

Create the file **`FinalFieldModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;

public class FinalFieldModesDemo {
    static class State {
        final int id = 7;
        volatile int counter = 1;
        static final int LIMIT = 11;
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle id = lookup.findVarHandle(State.class, "id", int.class);
        VarHandle counter = lookup.findVarHandle(State.class, "counter", int.class);
        VarHandle limit = lookup.findStaticVarHandle(State.class, "LIMIT", int.class);
        State state = new State();

        System.out.println("id variable type: " + id.varType().getSimpleName());
        System.out.println("id coordinates: " + id.coordinateTypes());
        System.out.println("limit coordinates: " + limit.coordinateTypes());
        System.out.println("id GET: " + id.isAccessModeSupported(AccessMode.GET));
        System.out.println("id GET_VOLATILE: " + id.isAccessModeSupported(AccessMode.GET_VOLATILE));
        System.out.println("id SET: " + id.isAccessModeSupported(AccessMode.SET));
        System.out.println("id COMPARE_AND_SET: " + id.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("id GET_AND_ADD: " + id.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("counter SET: " + counter.isAccessModeSupported(AccessMode.SET));
        System.out.println("counter COMPARE_AND_SET: " + counter.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("limit SET: " + limit.isAccessModeSupported(AccessMode.SET));
        System.out.println("id read: " + (int) id.get(state));
        System.out.println("limit read: " + (int) limit.get());

        try {
            id.set(state, 12);
            System.out.println("unreachable");
        } catch (UnsupportedOperationException ex) {
            System.out.println("id set exception: " + ex.getClass().getSimpleName());
        }

        counter.set(state, 8);
        boolean changed = counter.compareAndSet(state, 8, 9);
        System.out.println("counter changed: " + changed);
        System.out.println("counter read: " + (int) counter.getVolatile(state));
    }
}
```

Commands:

```bash
javac --release 17 FinalFieldModesDemo.java
java FinalFieldModesDemo
```

**Exact stdout on JDK 17+:**

```text
id variable type: int
id coordinates: [class FinalFieldModesDemo$State]
limit coordinates: []
id GET: true
id GET_VOLATILE: true
id SET: false
id COMPARE_AND_SET: false
id GET_AND_ADD: false
counter SET: true
counter COMPARE_AND_SET: true
limit SET: false
id read: 7
limit read: 11
id set exception: UnsupportedOperationException
counter changed: true
counter read: 9
```

How to read it:

1. `id.varType() == int.class`, while `id.coordinateTypes()` has exactly one class `State` because `id` is an instance field. `LIMIT` is a static field, so `limit.coordinateTypes()` is empty.
2. `id` is final: **GET** and **GET_VOLATILE** modes are supported, whereas `SET`, `COMPARE_AND_SET`, and `GET_AND_ADD` are rejected.
3. `id.get(state)` returns `7`; `limit.get()` returns `11`, with no receiver passed for the static field.
4. The `id.set(state, 12)` snippet is wrapped in `try/catch` to demonstrate intentional failure: it throws `UnsupportedOperationException`.
5. `counter` is a `volatile` but non-final field: `SET` and CAS are supported. `compareAndSet(state, 8, 9)` succeeds, and the final value is `9`.

> The program belongs to the same outer class as `State`, so the lookup has permission to access the members used in the example. In multi-module applications, looking up private or non-public fields is also subject to `Lookup` permission checks, which is a separate issue from access mode support.

## 7. Distinguishing a Reference Field VarHandle from an Element VarHandle

The following two handles describe **two different kinds of variables**:

```text
class Box {
    final int[] values = {1, 2};
}

reference = lookup.findVarHandle(Box.class, "values", int[].class)
   varType: int[]
   coordinates: (Box)
   access: final reference => readable, cannot be reassigned via SET/CAS

element = MethodHandles.arrayElementVarHandle(int[].class)
   varType: int
   coordinates: (int[], int)
   access: array element => can SET, CAS, GET_AND_ADD...
```

This is an illustrative description, not a standalone program. `reference` and `element` are completely non-interchangeable: `reference.get(box)` returns an `int[]`; `element.set(array, index, value)` updates an `int` element.

### 7.1. Practice 2 — A Final Array Reference Still Allows Modifying Elements

Create the file **`FinalArrayVsElementDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;

public class FinalArrayVsElementDemo {
    static class Box {
        final int[] values = {1, 2};
    }

    public static void main(String[] args) throws Exception {
        VarHandle reference = MethodHandles.lookup().findVarHandle(
                Box.class, "values", int[].class);
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
        Box box = new Box();
        int[] array = (int[]) reference.get(box);

        System.out.println("reference SET: " + reference.isAccessModeSupported(AccessMode.SET));
        System.out.println("reference CAS: " + reference.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("element coordinates: " + element.coordinateTypes());
        System.out.println("element SET: " + element.isAccessModeSupported(AccessMode.SET));
        System.out.println("element GET_AND_ADD: " + element.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("before: " + (int) element.get(array, 0));
        element.set(array, 0, 9);
        int old = (int) element.getAndAdd(array, 1, 5);
        System.out.println("element[0]: " + (int) element.get(array, 0));
        System.out.println("element[1] old: " + old);
        System.out.println("element[1] now: " + array[1]);
    }
}
```

```bash
javac --release 17 FinalArrayVsElementDemo.java
java FinalArrayVsElementDemo
```

**Stdout:**

```text
reference SET: false
reference CAS: false
element coordinates: [class [I, int]
element SET: true
element GET_AND_ADD: true
before: 1
element[0]: 9
element[1] old: 2
element[1] now: 7
```

Why?

- The `reference` VarHandle only sees **the `values` field variable** and rejects `SET`/CAS because the field has `final`.
- The `element` VarHandle sees **the `int` array element** at coordinates `(array,index)`, and does not see the `final` modifier of the field holding the reference to the array.
- `element.set(array, 0, 9)` writes the first element.
- `element.getAndAdd(array, 1, 5)` returns **the old value `2`** and updates the second element to `7`.

Do not infer that every array element VarHandle supports **every** numeric/bitwise mode: support also depends on the component type (`int` in the example supports addition and bitwise operations). And even when a mode is supported, an out-of-bounds index can still throw `ArrayIndexOutOfBoundsException`.

## 8. "Read-Only" Variables Are Not a Single Concept

There are at least three different situations in practice:

| Source of restriction | Example | `isAccessModeSupported(SET)` | What happens if you try to write? |
| --- | --- | --- | --- |
| The variable itself is declared final | `final int id` or `static final int LIMIT` | `false` | `UnsupportedOperationException` if `set` is called with the right signature |
| The **specific** receiver object forbids writing | `ByteBuffer.asReadOnlyBuffer()` with a view VarHandle | Can be `true` for the VarHandle family | `ReadOnlyBufferException` at the call on the read-only buffer |
| Final only applies to the **reference field**, not the referenced object | `final int[] values` and an array-element VarHandle | Field VH: `false`; element VH: `true` | The field cannot be reassigned, elements can still be updated |

This difference explains why you cannot write a simple `isReadOnly(VarHandle)` function and expect it to express every case. **`VarHandle` does not have a general API to ask whether a specific receiver currently allows writing**. When the receiver is a ByteBuffer, you must also check `buffer.isReadOnly()` and accept that an access can still encounter other runtime exceptions.

### 8.1. Buffer View VarHandle and Byte Index

`MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.LITTLE_ENDIAN)` returns a VarHandle viewing a byte region of a `ByteBuffer` as `int` values. It has:

- `varType() == int.class`;
- two coordinates `(ByteBuffer.class, int.class)`;
- the `int` coordinate is the **byte index** where the value region starts, not an arbitrary "int element index";
- the byte order rule declared when creating the view;
- additional constraints on bounds, alignment, and read-only status when performing a specific operation.

If a buffer was just converted to read-only via `asReadOnlyBuffer()`, that same VarHandle still describes a **ByteBuffer variable family** that is writable when the buffer is writable. Therefore, `isAccessModeSupported(SET)` can return `true`; when actually passing the read-only buffer, `set` is rejected.

### 8.2. Practice 3 — `SET` Mode Supported, but Receiver Is Read-Only

Create the file **`ReadOnlyBufferDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;

public class ReadOnlyBufferDemo {
    public static void main(String[] args) {
        ByteBuffer writable = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN);
        writable.putInt(0, 0x01020304);
        ByteBuffer readOnly = writable.asReadOnlyBuffer();
        VarHandle view = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.LITTLE_ENDIAN);

        System.out.println("buffer read-only: " + readOnly.isReadOnly());
        System.out.println("view coordinates: " + view.coordinateTypes());
        System.out.println("view SET supported: " + view.isAccessModeSupported(AccessMode.SET));
        System.out.println("view GET supported: " + view.isAccessModeSupported(AccessMode.GET));
        System.out.println("read-only GET: " + (int) view.get(readOnly, 0));
        try {
            view.set(readOnly, 0, 99);
            System.out.println("unreachable");
        } catch (ReadOnlyBufferException ex) {
            System.out.println("read-only SET exception: " + ex.getClass().getSimpleName());
        }
        view.set(writable, 0, 42);
        System.out.println("writable GET: " + (int) view.get(writable, 0));
    }
}
```

```bash
javac --release 17 ReadOnlyBufferDemo.java
java ReadOnlyBufferDemo
```

**Stdout:**

```text
buffer read-only: true
view coordinates: [class java.nio.ByteBuffer, int]
view SET supported: true
view GET supported: true
read-only GET: 16909060
read-only SET exception: ReadOnlyBufferException
writable GET: 42
```

Interpretation:

1. `writable` holds an `int` of `0x01020304`; decimal value `16909060`. The VarHandle view uses `ByteOrder.LITTLE_ENDIAN` matching how the data was written.
2. `readOnly.isReadOnly()` is `true`. Yet `view.isAccessModeSupported(SET)` is still `true` because at the **VarHandle** level, the mode is supported for this kind of view.
3. `view.get(readOnly, 0)` reads successfully. `view.set(readOnly, 0, 99)` throws **`ReadOnlyBufferException`** even though capability returns true.
4. `view.set(writable, 0, 42)` succeeds with another writable buffer, proving the handle itself is not "read-only".
5. `asReadOnlyBuffer()` creates a read-only buffer **sharing storage** with the original buffer. If other code continues writing through `writable`, the data observed from `readOnly` can change. A "read-only view" does not mean an "immutable snapshot".

> For ByteBuffer views, modes with atomic/volatile requirements may also require **alignment** to the data size; unaligned or out-of-bounds accesses can throw separate errors. `isAccessModeSupported(...)` does not replace checking coordinates and receiver state.

## 9. Limits Determined by Variable Type

Even when a field is non-final and the receiver is writable, the variable type still restricts certain modes.

### 9.1. CAS on a Reference and Addition on a Primitive Are Two Different Things

A `String` field can allow CAS (since it is a reassignable reference variable), but there is no atomic addition `GET_AND_ADD` for `String`. An `int` field typically has atomic addition and bitwise modes.

**Note on CAS on references:** CAS expected-value comparison is based on **reference identity** (semantically equivalent to `==` for references), not calling `String.equals(...)` or `Object.equals(...)`. Therefore, if you want to CAS the current reference value, use the exact expected object reference; two `String`s with the same content that are different objects are not automatically treated as the same expected value.

### 9.2. Practice 4 — Confirming Capabilities for `int` and `String` Types

Create the file **`VarHandleCapabilityDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;

public class VarHandleCapabilityDemo {
    static class Record {
        int points = 5;
        String name = "old";
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle points = lookup.findVarHandle(Record.class, "points", int.class);
        VarHandle name = lookup.findVarHandle(Record.class, "name", String.class);
        Record record = new Record();

        System.out.println("points ADD: " + points.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("points BITWISE_OR: " + points.isAccessModeSupported(AccessMode.GET_AND_BITWISE_OR));
        System.out.println("name CAS: " + name.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("name ADD: " + name.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("name BITWISE_OR: " + name.isAccessModeSupported(AccessMode.GET_AND_BITWISE_OR));
        if (points.isAccessModeSupported(AccessMode.GET_AND_ADD)) {
            int before = (int) points.getAndAdd(record, 3);
            System.out.println("points before add: " + before);
            System.out.println("points after add: " + (int) points.get(record));
        }
        System.out.println("name compareAndSet: "
                + name.compareAndSet(record, "old", "new"));
        System.out.println("name read: " + (String) name.get(record));
    }
}
```

```bash
javac --release 17 VarHandleCapabilityDemo.java
java VarHandleCapabilityDemo
```

**Stdout:**

```text
points ADD: true
points BITWISE_OR: true
name CAS: true
name ADD: false
name BITWISE_OR: false
points before add: 5
points after add: 8
name compareAndSet: true
name read: new
```

Meaning:

- `points` is a non-final `int`: atomic addition and bitwise OR are supported. `getAndAdd(record, 3)` returns the old value `5`, updating it to `8`.
- `name` is a non-final `String`: CAS is supported; numeric/bitwise atomic updates are inapplicable so they return `false`.
- In this example, `name` initially receives the literal `"old"`, and the expected `"old"` is also the same interned string reference; CAS succeeds. **Do not generalize** that CAS uses `equals` for String objects from different sources.
- Mode support lets you decide logic at the configuration/initialization step; at call time you still must pass the right receiver, argument types, and context.

## 10. Access Permission Limits Differ from Access Mode Limits

`MethodHandles.Lookup.findVarHandle` and `findStaticVarHandle` perform **access checking** when looking up a field. If permissions are insufficient for the class/private field/module, lookup can fail with `IllegalAccessException`; if the field does not exist or has the wrong type/staticness, it can fail with `NoSuchFieldException`.

Once you **already have** a VarHandle:

- `isAccessModeSupported(SET) == false` on a `final` field remains false even if the handle was created using a lookup with private access.
- `privateLookupIn`, in permitted situations, can help find a private field, but **does not waive the final rule**.
- `varType()` and `coordinateTypes()` help identify types; they do not determine read/write permissions of a specific receiver.
- For `static final`, referencing the field via VarHandle for reading does not grant permission to change its value.
- There is no `setAccessible(true)` operation on VarHandle to "enable" `SET` for a final field.

Analyze properly along three independent questions:

```text
1. Can a VarHandle be obtained?
   -> Lookup permissions, field name and type

2. Does the handle support the needed mode?
   -> isAccessModeSupported(mode)

3. Is the specific access valid?
   -> receiver, coordinates, read-only buffer, bounds/alignment,
      call-site type, class/runtime state
```

By separating these three layers, tooling can report errors more accurately instead of lumping every case together as "this variable is read-only".

## 11. Building a Safe Fallback Policy

A helper used in multi-configuration runtime code can follow this sequence:

1. Obtain the right VarHandle and know clearly **which field or element/view** it accesses.
2. Identify the minimal mode that satisfies the requirement: `GET` for reading, `COMPARE_AND_SET` for CAS, `GET_AND_ADD` for atomic addition; do not pick a stronger mode if unnecessary.
3. Check `isAccessModeSupported(mode)` **before** wiring the mode into a code path required to work.
4. If unsupported, choose a different contract (such as disallowing updates to a final field); if atomicity is needed, do not fall back to `get` then `set`.
5. If the mode is supported, verify the exact `coordinateTypes()` and specific receiver state. For ByteBuffer, check `buffer.isReadOnly()` when intending to write.
6. Handle runtime exceptions appropriately: invalid index, read-only buffer, type mismatch, and conditions defined by the VarHandle provider.
7. If processing concurrently, maintain consistent memory ordering rules and synchronization mechanisms across the entire pipeline.

### 11.1. Simple Check Pattern for Writing

```java
// Fragment: fieldHandle is an existing VarHandle and state is a receiver of the right type.
if (!fieldHandle.isAccessModeSupported(VarHandle.AccessMode.SET)) {
    throw new UnsupportedOperationException("This variable is not writable");
}
fieldHandle.set(state, 42);
```

This is a non-standalone fragment. If `fieldHandle` accesses an `int` instance field, the call above has the right call-site shape. However, for a **ByteBuffer view**, you also need to check receiver read-only/bounds. For `GET_AND_ADD` or CAS, you also need to be sure the mode genuinely supports the required atomicity.

### 11.2. Do Not Use a Fallback Branch That Loses Atomicity

A **wrong approach in concurrent applications**:

```java
// Anti-pattern, DO NOT use as an atomic increment:
int old = (int) counter.get(state);
counter.set(state, old + 1);
```

Two threads can simultaneously read the same `old` and both write `old+1`, losing an update. `getAndAdd` has a single atomic point by the semantics of the operation; separate read–write does not.

If `GET_AND_ADD` is unsupported because the field is final, the right solution is usually **not to update that field**. If the mode is unsupported due to variable type or variable source, you need a different synchronization design/data type, rather than using a plain addition as an equivalent replacement.

### 11.3. For Read-Only Buffers

You can check beforehand:

```java
// Fragment: buffer is a java.nio.ByteBuffer, view is a VarHandle int view.
if (buffer.isReadOnly()) {
    throw new java.nio.ReadOnlyBufferException();
}
if (!view.isAccessModeSupported(VarHandle.AccessMode.SET)) {
    throw new UnsupportedOperationException("SET not supported");
}
view.set(buffer, 0, 123);
```

This is only a **guard in the case where the buffer does not concurrently change state and the coordinates are valid**; it does not replace all possible error handling. Similarly, `buffer.isReadOnly()` does not guarantee the buffer has sufficient capacity or that a volatile operation does not violate alignment.

## 12. Easily Confused Exceptions

| Exception | When commonly encountered | Meaning |
| --- | --- | --- |
| `UnsupportedOperationException` | Calling an access mode where `isAccessModeSupported(...) == false` | The mode has no valid implementation for that VarHandle, e.g. `SET` on a final field |
| `ReadOnlyBufferException` | Calling a write access mode on a read-only buffer | The mode may be supported at the VarHandle level, but the **specific receiver** forbids writing |
| `WrongMethodTypeException` | Call-site signature does not match the access mode type | Wrong coordinate type/count, new value type, or cast result type at the call |
| `ClassCastException` | A reference at the call-site cannot be cast as required | Wrong runtime object/reference type |
| `NullPointerException` | Passing null for a required instance receiver, array, or buffer | A null coordinate does not point to a valid variable |
| `ArrayIndexOutOfBoundsException` | Invalid array element index | Invalid coordinate for `arrayElementVarHandle` |
| `IndexOutOfBoundsException` | Invalid ByteBuffer index/range | Invalid byte region of the view |
| `IllegalStateException` | Some buffer view access modes have unsatisfied alignment requirements | Mode is supported, but address/index lacks sufficient alignment |
| `IllegalAccessException` | During `Lookup` when lacking permission | Failed to obtain the VarHandle, not a result of `isAccessModeSupported` |
| `NoSuchFieldException` | During `Lookup` with wrong field name/type | No handle obtained yet to check modes |

Specific causes vary by factory. For example, a type mismatch can cause an error at the call-site linking step before reaching update logic. **Do not use `catch(Exception)` to treat every failure as "read-only"**: that equates program bugs with data policy.

### 12.1. `GET` Is Always Supported, but Does Not Guarantee Every Read Succeeds

For example:

```java
// Fragment: id is a VarHandle on an int instance field of State.
int value = (int) id.get(state);
```

Even though `id.isAccessModeSupported(GET)` returns `true`, if `state == null` there is no object containing the field; if you call with the wrong static type at the call-site, a mismatch can occur. `GET` being supported only means **you will not encounter UnsupportedOperationException due to an unsupported mode**.

### 12.2. Synchronization and `final` Are Two Different Axes

`VarHandle.getVolatile` has volatile-like read semantics, but has no ability to turn a `final` field into a writable variable. `SET_RELEASE`, `SET_VOLATILE`, or CAS are still **writes/updates**. At the same time, a field declared `volatile` can be accessed using `get` (plain), `getOpaque`, `getAcquire`, or `getVolatile`; the chosen access mode has its own memory ordering rules, so you must not assume `volatile` on the declaration forces every access via VarHandle to have the same memory semantics.

The examples in this lesson run single-threaded to show capabilities/exceptions; multi-threaded applications must reason under the Java Memory Model and choose the right mode for all relevant read/write paths.

## 13. Quick Decision Table

| Situation | Which handle to choose? | What to check? | Expectation |
| --- | --- | --- | --- |
| Read `final int id` | `findVarHandle` of field `id` | `GET` (always supported) and object coordinate | Readable if permissions are sufficient and receiver is valid |
| Want to `set` on `final int id` | Same field handle | `SET` | `false`; cannot write via VarHandle |
| Want CAS on non-final `volatile int count` | Field handle of `count` | `COMPARE_AND_SET`; type/receiver | Usually supported; handle expected value properly |
| Increment `int` via get-and-add | Appropriate field/array-element handle | `GET_AND_ADD` | Non-final `int` type is usually supported |
| Write `final int[] values` via field handle | Field handle of `values` | `SET` | `false`; field reference cannot be reassigned |
| Modify `values[0]` | `arrayElementVarHandle(int[].class)` | `SET`; array/index | Can write element even though reference is final |
| Write via a view of a read-only buffer | `byteBufferViewVarHandle` | Both support and `buffer.isReadOnly()` | Mode may be true, but write call throws `ReadOnlyBufferException` |
| CAS on `String` field | Field handle of non-final `String` | `COMPARE_AND_SET` | Possible; compares reference instead of `equals` |
| Add to `String` via `GET_AND_ADD` | Field handle of `String` | `GET_AND_ADD` | `false` |
| Look up a private field to read | Lookup with appropriate access | Lookup access, then mode support | Cannot bypass access checks just by having the AccessMode enum |

## 14. Design Mistakes and Habits to Avoid

1. **Calling `set` first and asking `isAccessModeSupported` later.** If a mode is required to run properly, check capability first and fail early with a clear message.
2. **Treating `isAccessModeSupported(SET)==true` as meaning every instance is writable.** False for a ByteBuffer view on an `asReadOnlyBuffer()` receiver.
3. **Assuming `final` forbids any variable inside the object/array from changing.** `final` does not automatically deep-freeze the state of the referenced object.
4. **Assuming CAS is a read-only operation.** CAS can write, so final fields do not support it.
5. **Assuming numeric/bitwise atomic modes are available for every reference field.** A `String` field can be CAS'd, but not get-and-added.
6. **Confusing the `int[]` field type with the `int` element type.** Field handles and array-element handles have different `varType()` and coordinates.
7. **Using `get()+set()` instead of CAS/get-and-add without synchronization.** This loses atomicity.
8. **Assuming private lookup turns final into mutable.** Lookup access permissions and mode support are two separate layers.
9. **Passing wrong coordinates to signature-polymorphic methods.** Static fields need no receiver; instance fields need a receiver; array elements need an array and an index.
10. **Treating `volatile` as synonymous with final or always having the same memory semantics across all modes.** Each access mode has its own rules.
11. **Ignoring appropriate checked/unchecked exceptions.** `ReadOnlyBufferException` differs from `UnsupportedOperationException`; invalid index or invalid call-site also differs.
12. **Checking only the mode and assuming the program has no other errors.** Bounds, alignment, receiver, class loader/module, and lifecycle are still runtime conditions.
13. **Using a literal string as the expected value to simulate CAS on any object.** Reference CAS compares identity, so you must know the actual object currently held.
14. **Thinking a read-only ByteBuffer is an immutable snapshot.** It only forbids writing through that view; another writer can still change the shared data region if the architecture permits.

## 15. Self-Check Knowledge

**Question 1.** On an instance `final int id`, what do `isAccessModeSupported(GET)`, `isAccessModeSupported(SET)`, and `isAccessModeSupported(COMPARE_AND_SET)` typically return? Why?

**Question 2.** If a static final field has a VarHandle, do you need to pass an instance object to `get(...)`?

**Question 3.** `final int[] values` cannot be reassigned, so why can `arrayElementVarHandle(int[].class).set(values, 0, 9)` succeed?

**Question 4.** Why can a VarHandle created by `byteBufferViewVarHandle` report `SET` as supported, yet `set(readOnlyBuffer, ...)` throws `ReadOnlyBufferException`?

**Question 5.** Should you use `int old=(int) vh.get(...); vh.set(..., old+1);` as a fallback for `GET_AND_ADD` in multi-threaded code?

**Question 6.** `isAccessModeSupported(GET)` is always true. Does that mean `get(...)` never throws an exception?

**Question 7.** Why can a non-final `String` field support `COMPARE_AND_SET` but not `GET_AND_ADD`?

**Question 8.** In CAS on references, are two objects with `equals(...) == true` guaranteed to be treated as the same expected value?

**Question 9.** Distinguish the three check levels: VarHandle creation permission, mode support capability, and conditions of a specific access.

**Question 10.** If a `volatile int count` field is read using `get` and `getVolatile`, do they necessarily have the same memory ordering meaning?

**Suggested Answers:**

1. `GET=true`, `SET=false`, `COMPARE_AND_SET=false`; final allows reading but not updating.
2. No, a static field handle has **0 coordinates**; use `get()`.
3. `final` restricts reassigning the **field reference**, whereas array elements are separate variables accessed via another handle.
4. Capability reflects the **kind of VarHandle**; read-only status belongs to the specific buffer receiver, checked at call time.
5. No if atomicity is needed; separate read–write can lose updates.
6. No; coordinate, call-site type, null, and other runtime errors can still occur.
7. CAS can compare/reassign references, whereas atomic addition does not apply to `String`.
8. No; reference CAS compares **identity**, not `equals`.
9. Lookup checks whether the handle can be obtained; `isAccessModeSupported` checks the mode; actual access checks receiver/index/bounds/alignment/type.
10. No; the invoked mode determines VarHandle access semantics, not just the source modifier.

## 16. Official References

- [Java SE 21 — `VarHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html): access mode groups, `isAccessModeSupported`, readability, error semantics when a mode is unsupported, and coordinate types.
- [Java SE 21 — `VarHandle.AccessMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html): enum constants `GET`, `SET`, `COMPARE_AND_SET`, `GET_AND_ADD`, and variants.
- [Java SE 21 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle`, `findStaticVarHandle`, access permissions, and restricted modes on final fields.
- [Java SE 21 — `MethodHandles`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `arrayElementVarHandle`, `byteBufferViewVarHandle`, and related factories.
- [Java SE 21 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): read-only buffers, views sharing storage, offsets, and byte order.
- [Java SE 21 — `ReadOnlyBufferException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ReadOnlyBufferException.html): error when attempting to modify a read-only buffer.
- [Java Language Specification 21 — `4.12.4 final Variables`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): meaning of final variables and reassignment restrictions.

**Conclusion:** Distinguish **whether a mode is supported by the VarHandle** from **whether the actual variable/receiver allows the operation on this call**. `isAccessModeSupported` answers the first question; `final` fields make update modes unsupported, while a read-only `ByteBuffer` can reject `set` even though the mode is supported at the view level. Also check variable types, coordinates, receiver state, and atomic contracts to avoid turning a capability check into a false assumption about writability.