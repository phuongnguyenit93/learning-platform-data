# 9.2 Creating handles for static fields, instance fields, and array elements

## 1. What is VarHandle and why distinguish three kinds of variables?

`java.lang.invoke.VarHandle` (available since Java 9) is an object representing **access rights to a variable of a specific type**. That variable can be a **field of an object**, a **static field of a class**, or an **element of an array**. Instead of only calling `Field.get`/`Field.set` like traditional Reflection, we create a VarHandle and then use access modes such as `get`, `set`, `getVolatile`, `compareAndSet`, or `getAndAdd` when the variable type and access rights support them.

The focus of lesson **9.2** is **how to create the right handle and understand its parameter shape**:

- `MethodHandles.Lookup.findVarHandle(...)`: finds an **instance field**.
- `MethodHandles.Lookup.findStaticVarHandle(...)`: finds a **static field**.
- `MethodHandles.arrayElementVarHandle(...)`: creates a handle to access **an element of an array**.
- `Lookup.unreflectVarHandle(Field)`: converts known `Field` metadata into a VarHandle, still subject to access control.

After this lesson, you will be able to identify `varType()` and `coordinateTypes()`, invoke a handle with the right number and order of arguments, understand the difference between access checks at handle creation time and value access at invocation time, as well as handle common errors related to final fields, wrong field name/type, invalid array indices, and module boundaries.

> **Core mindset:** A VarHandle defines *the variable to operate on* and *the coordinates that must be supplied to identify a specific storage location*. For an instance field, the coordinate is **the object containing the field**; for a static field, **there are no coordinates**; for an array element, the coordinates are **the array and the index**.

## 2. Two foundational concepts: variable type and coordinate types

A VarHandle is described by two independent parts:

1. **`varType()`**: the type of the value stored in the variable managed by the handle, for example `int.class`, `long.class`, `String.class`. This is **not** the type of the object containing the field.
2. **`coordinateTypes()`**: the list of `Class<?>` of the parameters that must be provided to locate the memory slot/variable. The order of this list is also the order when calling `get`/`set`.

Comparison table:

| Variable kind | How to create | Example `varType()` | Example `coordinateTypes()` | `get` | `set` |
| --- | --- | --- | --- | --- | --- |
| Instance field `State.count` of type `int` | `lookup.findVarHandle(State.class,"count",int.class)` | `int` | `[State]` | `(int) vh.get(state)` | `vh.set(state,5)` |
| Static field `State.total` of type `long` | `lookup.findStaticVarHandle(State.class,"total",long.class)` | `long` | `[]` | `(long) vh.get()` | `vh.set(200L)` |
| Array element of type `int` | `MethodHandles.arrayElementVarHandle(int[].class)` | `int` | `[int[],int]` | `(int) vh.get(numbers,1)` | `vh.set(numbers,1,25)` |

The term "coordinates" here does not mean a raw memory address. They are **typed Java arguments** that VarHandle needs to know the storage location.

For example, `State` can have hundreds of instances. The `count` handle is the same access object, while `stateA` and `stateB` in the calls `countHandle.get(stateA)`/`get(stateB)` are two coordinates pointing to two field slots of two different objects.

Conversely, a `static` field is a variable attached to the class, not to each instance: `get()` takes no receiver. Trying to pass `state` into `get(state)` on a static VarHandle does not have a valid matching call signature.

For arrays, the same handle `arrayElementVarHandle(int[].class)` can be used for **multiple `int[]` arrays**, because each operation supplies the specific array and index; it is not permanently bound to an array passed at creation time.

### 2.1. Method type of each access mode

Methods like `get` and `set` on `VarHandle` are **signature-polymorphic**. The invocation type depends on both **coordinate types** and **varType**. You can query the handle:

```java
MethodType getType = vh.accessModeType(VarHandle.AccessMode.GET);
MethodType setType = vh.accessModeType(VarHandle.AccessMode.SET);
```

If `vh` manages the instance field `int count` of `State`, conceptually:

```text
GET             (State)int
SET             (State,int)void
COMPARE_AND_SET (State,int,int)boolean
GET_AND_ADD     (State,int)int
```

Where each mode takes **the coordinates first**, followed by **the value to write / expected value / delta**.

For the static field `long total`:

```text
GET  ()long
SET  (long)void
```

For an `int[]` element:

```text
GET (int[],int)int
SET (int[],int,int)void
```

Do not construct signatures yourself based on the method name `get`/`set` and guess the number of arguments. Rely on `coordinateTypes()`, `varType()`, and `accessModeType(...)` of the actual handle.

## 3. Creating a VarHandle for an instance field with `findVarHandle`

### 3.1. Syntax and meaning of parameters

```java
VarHandle vh = lookup.findVarHandle(
        State.class,  // declaring/reference class containing the field
        "count",      // field name (string)
        int.class);   // field type must match
```

`lookup` is a `MethodHandles.Lookup` carrying the **access privilege context**. Typically, code inside a class or valid nest starts from `MethodHandles.lookup()`. The factory returns a VarHandle for the **instance field** `count`.

The statement above **does not read the value of `count` immediately**. It creates the access capability; when calling `vh.get(state)`, the coordinate `state` then identifies the variable of a specific instance.

Practical conditions:

- The class and field name must be correct; the third type must be the **exact field type**, not the type of the containing object. For an `int count` field, use `int.class`, not `Integer.class`.
- The field must match the instance mode of the factory and the `Lookup` context must have access permission. A wrong field name, static/instance kind, or access right will cause **lookup to fail**.
- `findVarHandle` may throw `NoSuchFieldException` or `IllegalAccessException`; therefore the enclosing method usually declares `throws ReflectiveOperationException`, or handles these checked exceptions.
- There is no need to create a VarHandle for each `State` object. You can keep **one handle** and provide the appropriate receiver on each `get`/`set` call.

Illustrative example:

```java
State first = new State();
State second = new State();

int before = (int) countHandle.get(first);
countHandle.set(first, 10);
int other = (int) countHandle.get(second);
```

This is a **snippet**, not a standalone program. Assuming both objects initialize `count=1`, then `before=1`; only `first` changes to 10, while `other=1`. Both calls use the same handle but different coordinates.

### 3.2. `private` instance fields and `Lookup` permissions

If `count` is `private`, that does not mean any `MethodHandles.lookup()` from any class is allowed to create a handle. Lookup has permissions based on the call site and module/package visibility. The complete code in section 6 places `State` as a **nested class inside the same top-level class**, so that the example code has private access via Java's nestmates mechanism; there is no permission-bypass trick.

For a private field of a class in another package/module, see section 8 on `privateLookupIn`, `module-info.java`, and `opens` capability. Do not use VarHandle creation methods as a tool to automatically bypass encapsulation.

### 3.3. The receiver must be the right object

For an instance field:

```java
int value = (int) countHandle.get(state);
countHandle.set(state, 5);
```

`state` needs to match the receiver type of the VarHandle. Do not pass `State.class` instead of a `State` object; and do not omit the receiver when calling `get()`. For signature-polymorphic calls, a wrong number or type of arguments can produce `WrongMethodTypeException`, while a null receiver or other runtime checks can lead to other exceptions. Do not equate every error with `IllegalAccessException`: lookup permission errors occur at the **creation phase** and invocation errors occur at the **usage phase**—these are two different classes of problems.

## 4. Creating a VarHandle for a static field with `findStaticVarHandle`

Syntax:

```java
VarHandle totalHandle = lookup.findStaticVarHandle(
        State.class, "total", long.class);
```

With the field:

```java
private static volatile long total = 100L;
```

The VarHandle will have:

- `varType() = long.class`.
- `coordinateTypes() = []`, because there is no receiver or array index.
- `(long) totalHandle.get()` reads `total`.
- `totalHandle.set(200L)` writes `total`.

Before calling, the variable `total` belongs to the class containing the field; this is not a case of one `total` variable per `State`.

**Common pitfall:** `findStaticVarHandle` is not equivalent to `findVarHandle`. If code obtains a handle using the wrong factory for the actual field kind, lookup fails. Do not try to fix it by arbitrarily adding a receiver argument when calling.

### 4.1. Static does not mean final

A `static` field can still be mutated if it is not `final` and the appropriate write mode is supported. Conversely, a `static final` field typically has a **read-only VarHandle**; do not infer that successfully creating a handle guarantees you can call `set`.

In the main example, `total` is `static volatile long` to illustrate both plain operations and accesses with synchronization requirements in real applications. On a VarHandle, the **access mode** (`get`, `getVolatile`, `setVolatile`...) is what determines the corresponding access semantics; the `volatile` keyword on the field declaration **does not automatically turn every `get` call into `getVolatile`** in how the VarHandle API is used.

### 4.2. Handles can be shared, not recreated on every read

An example pattern in a module/class with appropriate permissions:

```java
// Illustrative snippet, not a complete class.
private static final VarHandle TOTAL_HANDLE;

static {
    try {
        TOTAL_HANDLE = MethodHandles.lookup()
                .findStaticVarHandle(State.class, "total", long.class);
    } catch (ReflectiveOperationException ex) {
        throw new ExceptionInInitializerError(ex);
    }
}
```

Creating the handle once and caching it avoids repeating the lookup operation in frequently executed code. Only apply this when the field exists, the class/access-permission relationship is controlled, and initialization errors are handled appropriately. This is a **snippet** assuming `State` and the corresponding `import`s exist.

## 5. Creating a VarHandle for an array element with `arrayElementVarHandle`

This is a fundamentally different factory: **no need to pass a `Lookup` or a field name**.

```java
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
```

It manages **elements of type `int`** inside any matching `int[]` array. The array type is provided at creation time, while the **specific** array is only passed at usage time.

Example:

```java
int[] numbers = {10, 20, 30};
int middle = (int) element.get(numbers, 1);
element.set(numbers, 1, 25);
// middle == 20; numbers after set: {10, 25, 30}
```

The coordinates of an array element handle are:

1. **Reference to the array**: `int[]`.
2. **Index `int`**: 0-based like normal Java array access.

Then, if the access mode is `set`, the third argument is the **element value to write** (`int`).

### 5.1. Distinguishing array type and element type

| Factory call | `varType()` | `coordinateTypes()` |
| --- | --- | --- |
| `arrayElementVarHandle(int[].class)` | `int.class` | `[int[].class, int.class]` |
| `arrayElementVarHandle(String[].class)` | `String.class` | `[String[].class, int.class]` |
| `arrayElementVarHandle(String[][].class)` | `String[].class` | `[String[][].class, int.class]` |
| `arrayElementVarHandle(Object[].class)` | `Object.class` | `[Object[].class, int.class]` |

For a two-dimensional array `String[][]`, a **level-1** element is a `String[]`. Therefore, the VarHandle created by `arrayElementVarHandle(String[][].class)` only locates a row using two coordinates: **the 2D array + the row index**. It **does not automatically generate** a handle taking three coordinates `(matrix,row,column)`. To read a deeper `String` element, get the corresponding row first and then use a handle for `String[].class` or normal array access.

Conceptual example:

```java
// Snippet, assuming import java.lang.invoke.*.
String[][] matrix = {{"A", "B"}, {"C", "D"}};
VarHandle rowHandle =
        MethodHandles.arrayElementVarHandle(String[][].class);
String[] row = (String[]) rowHandle.get(matrix, 1);
// row contains ["C", "D"].
```

### 5.2. Not every object is an array

`arrayElementVarHandle(String.class)` is an **invalid** handle creation call because `String.class` is not an array class; the factory requires a `Class<?>` representing an array type. Use `String[].class` if you want to access each `String` in an array.

In other words, the API does not create handles for `List<E>`, `Map<K,V>`, or an arbitrary object. To manipulate a `List`, use the `List` API or a method handle for its methods; array-element VarHandle is only for **JVM arrays**.

### 5.3. Errors at usage time

- `null` array: the operation needing the element location has no valid array and may throw `NullPointerException`.
- Negative index or `index >= array.length`: `ArrayIndexOutOfBoundsException`.
- The index must have a type matching the `int` coordinate parameter; there is no key-based lookup mechanism like `Map`.
- An array of a type other than `int[]` cannot be used with a handle whose `coordinateTypes() = [int[],int]` just because the elements look similar. `int[]` and `Integer[]` are two distinct array types.
- If performing CAS or other access modes, you must check **which modes are supported for the element type**; do not assume every array element supports every operation.

## 6. Standalone Java 17+ example: creating all three handles and inspecting metadata

This example uses a nested class `State` with an instance field, a static field, and a final field; then it creates a VarHandle for `int[]`. It also checks `unreflectVarHandle`, supported modes, and intentional errors.

Create a file **`VarHandleCreationDemo.java`** containing this exact code:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.Field;
import java.util.Arrays;

public class VarHandleCreationDemo {
    static final class State {
        private volatile int count = 1;
        private static volatile long total = 100L;
        private final String label = "fixed";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Instance field: receiver State + varType int.
        VarHandle instance =
                lookup.findVarHandle(State.class, "count", int.class);

        // Static field: no receiver; varType long.
        VarHandle global =
                lookup.findStaticVarHandle(State.class, "total", long.class);

        // Array element: array int[] + index int.
        VarHandle element =
                MethodHandles.arrayElementVarHandle(int[].class);

        State state = new State();
        int[] numbers = {10, 20, 30};

        System.out.println("instance varType="
                + instance.varType().getSimpleName());
        System.out.println("instance coordinates="
                + instance.coordinateTypes().stream()
                          .map(Class::getSimpleName).toList());
        System.out.println("static varType="
                + global.varType().getSimpleName());
        System.out.println("static coordinates="
                + global.coordinateTypes().size());
        System.out.println("array varType="
                + element.varType().getSimpleName());
        System.out.println("array coordinates="
                + element.coordinateTypes().stream()
                         .map(Class::getSimpleName).toList());

        MethodType getType =
                instance.accessModeType(VarHandle.AccessMode.GET);
        MethodType setType =
                element.accessModeType(VarHandle.AccessMode.SET);
        System.out.println("instance GET type="
                + getType.parameterCount() + "/"
                + getType.returnType().getSimpleName());
        System.out.println("array SET type="
                + setType.parameterCount() + "/"
                + setType.returnType().getSimpleName());

        System.out.println("instance initial=" + (int) instance.get(state));
        instance.set(state, 4);
        System.out.println("instance after set=" + (int) instance.get(state));

        boolean changed = instance.compareAndSet(state, 4, 9);
        System.out.println("instance CAS="
                + changed + "/" + (int) instance.get(state));
        int before = (int) instance.getAndAdd(state, 3);
        System.out.println("instance add="
                + before + "/" + (int) instance.get(state));

        System.out.println("static initial=" + (long) global.get());
        global.set(200L);
        System.out.println("static after set=" + (long) global.get());

        System.out.println("array initial=" + (int) element.get(numbers, 1));
        element.set(numbers, 1, 25);
        System.out.println("array after set="
                + (int) element.get(numbers, 1));
        System.out.println("array CAS="
                + (boolean) element.compareAndSet(numbers, 1, 25, 27));
        System.out.println("array data=" + Arrays.toString(numbers));

        Field f = State.class.getDeclaredField("count");
        VarHandle reflected = lookup.unreflectVarHandle(f);
        System.out.println("unreflect count="
                + (int) reflected.get(state));

        VarHandle finalField =
                lookup.findVarHandle(State.class, "label", String.class);
        System.out.println("final read="
                + (String) finalField.get(state));
        System.out.println("final SET supported="
                + finalField.isAccessModeSupported(VarHandle.AccessMode.SET));
        try {
            finalField.set(state, "other");
            System.out.println("unexpected final write");
        } catch (UnsupportedOperationException ex) {
            System.out.println("final SET=UnsupportedOperationException");
        }

        try {
            int ignored = (int) instance.get();
            System.out.println("unexpected arity=" + ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("missing receiver=WrongMethodTypeException");
        }

        try {
            int ignored = (int) element.get(numbers, 3);
            System.out.println("unexpected index=" + ignored);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("bad index=ArrayIndexOutOfBoundsException");
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac VarHandleCreationDemo.java
java VarHandleCreationDemo
```

**Stdout (verified by compiling and running on a JDK supporting Java 17+):**

```text
instance varType=int
instance coordinates=[State]
static varType=long
static coordinates=0
array varType=int
array coordinates=[int[], int]
instance GET type=1/int
array SET type=3/void
instance initial=1
instance after set=4
instance CAS=true/9
instance add=9/12
static initial=100
static after set=200
array initial=20
array after set=25
array CAS=true
array data=[10, 27, 30]
unreflect count=12
final read=fixed
final SET supported=false
final SET=UnsupportedOperationException
missing receiver=WrongMethodTypeException
bad index=ArrayIndexOutOfBoundsException
```

### 6.1. Explaining each output group

**Group 1 – metadata (lines 1–8).** The instance field needs a `State` receiver. The static field has `0` coordinates. The array element needs `int[]` and an `int` index. Instance `GET` returns `int` and has 1 parameter; array `SET` returns `void` and takes 3 parameters (array, index, value).

**Group 2 – instance (lines 9–12).** `state.count` starts at 1, `set(state,4)` brings it to 4. `compareAndSet(state,4,9)` returns `true` and writes 9 because the expected value matches. `getAndAdd(state,3)` returns the **old value** 9 and then the variable becomes 12. All operations use the same VarHandle while supplying the receiver object.

**Group 3 – static (lines 13–14).** `global.get()` has no arguments; `global.set(200L)` writes the class's long field and does not need any `State`.

**Group 4 – array (lines 15–18).** `element.get(numbers,1)` returns 20; `set(numbers,1,25)` writes to index 1, then CAS updates from 25 to 27. The other elements remain unchanged.

**Group 5 – creating from `Field` and final (lines 19–22).** `lookup.unreflectVarHandle(f)` accesses the exact `count` variable currently equal to 12. The handle for the `final label` field **can be read**, but the `SET` mode reports `false` and attempting to write results in `UnsupportedOperationException`. Do not use valid private access to infer that final fields are writable.

**Group 6 – errors (lines 23–24).** `instance.get()` is missing the receiver, mismatches the signature-polymorphic signature, and leads to `WrongMethodTypeException`. `element.get(numbers,3)` exceeds the index of an array of length 3, leading to `ArrayIndexOutOfBoundsException`.

### 6.2. Why does the example use a nested class?

`State` is a nested class inside the same top-level class `VarHandleCreationDemo`. Java 11+ has the concept of nestmates, allowing members of a nest to access private members with appropriate permissions. Therefore `MethodHandles.lookup()` in `VarHandleCreationDemo.main` finds the private fields `State.count`, `State.total`, and `State.label` validly.

If `State` is moved to another module, keeping the same `MethodHandles.lookup()` snippet may **no longer have sufficient permissions**. `Lookup` permissions are not tied to the `findVarHandle` method name, but to the class obtaining the lookup and module boundaries. Do not assume this private field example will work from any package.

## 7. Access modes after creating a handle

When first learning to create VarHandles, clearly distinguish between **creating a handle successfully** and **every access mode being usable**. `VarHandle.AccessMode` lists modes such as `GET`, `SET`, `GET_VOLATILE`, `SET_VOLATILE`, `COMPARE_AND_SET`, `GET_AND_ADD`, etc.

| Group | Example operations | Short meaning |
| --- | --- | --- |
| Plain read/write | `get`, `set` | Read/write variable with plain semantics |
| Opaque | `getOpaque`, `setOpaque` | Opaque access under the Java Memory Model |
| Acquire/release | `getAcquire`, `setRelease` | Supports acquire/release synchronization patterns |
| Volatile | `getVolatile`, `setVolatile` | Read/write with volatile semantics |
| Atomic compare-update | `compareAndSet`, `compareAndExchange` and variants | Compare expected value, update conditionally |
| Atomic read-modify-write | `getAndSet`, `getAndAdd` and supported variants | Read old value and update atomically |

Modes should be chosen based on **inter-thread synchronization characteristics**. `getAndAdd` has a different meaning from two statements `int old=(int)vh.get(...); vh.set(...,old+1)`: a separate read followed by a write does not automatically become an atomic read-modify-write operation.

However, the scope of this lesson is **factories and coordinates**; you only need to know that a created handle has a set of **supported access modes** depending on the variable kind and data type. For example, `getAndAdd` is not a meaningful addition for arbitrary reference types, and a VarHandle for a `final` field does not support writing.

Before using a mode that might not be supported, check:

```java
// Snippet: finalField was created in the main example.
boolean canWrite =
        finalField.isAccessModeSupported(VarHandle.AccessMode.SET);
if (!canWrite) {
    System.out.println("Final field only supports valid modes.");
}
```

If you attempt to call an unsupported mode, Java may throw `UnsupportedOperationException` **right at the mode invocation**, as in the example we ran. Even a supported mode can still fail due to wrong coordinates, wrong type, null, or index out of bounds.

### 7.1. Typical signature shapes beyond `get`/`set`

For `int count` (instance):

```text
countHandle.compareAndSet(state, expectedInt, newInt) -> boolean
countHandle.getAndAdd(state, deltaInt)                 -> old int
```

For `long total` (static):

```text
totalHandle.compareAndSet(expectedLong, newLong) -> boolean
totalHandle.getAndAdd(deltaLong)                 -> old long
```

For an `int[]` element:

```text
arrayHandle.compareAndSet(array, index, expectedInt, newInt) -> boolean
arrayHandle.getAndAdd(array, index, deltaInt)                -> old int
```

General pattern: **coordinates first, operation arguments second**. Wrong order can lead to `WrongMethodTypeException` or type conversion errors. The forms above illustrate modes commonly supported for writable `int`/`long`; they do not automatically apply to `String` or final fields.

## 8. Other ways to create handles and access control

### 8.1. `Lookup.unreflectVarHandle(Field)`

When a framework already has a `java.lang.reflect.Field` from a metadata scan phase, it can convert it into a VarHandle:

```java
Field field = State.class.getDeclaredField("count");
VarHandle vh = MethodHandles.lookup().unreflectVarHandle(field);
```

In the complete example, this `Field` is private, but the lookup from the same nest has permission; `vh.get(state)` succeeds. `unreflectVarHandle` automatically recognizes whether the field is instance or static and determines the corresponding coordinate types.

Do not think of `unreflectVarHandle` as bypassing all access checks. Access to a private field still relies on appropriate permissions according to `Lookup` and Reflection/module rules. `Field.getDeclaredField` may **find the metadata**, but that does not mean the caller is allowed to perform deep access.

### 8.2. `privateLookupIn` when valid private access is needed

For another class where module/package policy allows private access, you can create a lookup with corresponding permissions using `MethodHandles.privateLookupIn`:

```java
// Snippet: OtherType is a class owned by the application or with valid permissions.
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                OtherType.class, MethodHandles.lookup());

VarHandle secret = privateLookup.findVarHandle(
        OtherType.class, "secret", int.class);
```

This is only an **illustrative snippet**, not a standalone example: you need to declare `OtherType` with an instance field `int secret` and place the code in an environment with permissions. `privateLookupIn` **does not automatically cross module boundaries**; if the source package has not been opened to the calling module or the caller lookup lacks permissions, the call still fails. For Java 17+ experimentation, you can use `opens` in `module-info.java` or `--add-opens=source.module/package=target.module` on the JVM of the right process, if project policy permits. The `--add-opens` flag is only a supplemental permission configuration; it is still best to prefer public APIs.

### 8.3. Differences between `findVarHandle`, `unreflectVarHandle`, and `arrayElementVarHandle`

- `findVarHandle`/`findStaticVarHandle` looks up a field by **class + name + field type**; suitable when the field descriptor is known in advance.
- `unreflectVarHandle` starts from an existing `Field` object; suitable for metadata-scanning frameworks, but does not waive access rights.
- `arrayElementVarHandle` takes an **array class** and has no field name or lookup because an array element is not a field declared in a user class.
- All three kinds of handles still use the same model of access modes and coordinate types. You do not need to write three completely different frameworks; the logic differs mainly in the **factory** and **coordinates**.

### 8.4. Avoid accessing JDK private internals when unnecessary

You should not write production examples by writing to private fields of core `java.base` classes. Experimenting with fields in classes you own is safe, stable, and easy to verify. Even when changing JVM flags to open packages, a private field of the JDK remains an **implementation detail**, not a public contract.

## 9. Common errors: symptoms, causes, and fixes

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `NoSuchFieldException` in `findVarHandle` | Wrong field name, wrong field kind/type, or class lacks that field | Check exact name, `int.class` vs `Integer.class`, and the queried class; verify the field actually exists |
| `IllegalAccessException` during lookup | `Lookup` lacks private/package/protected permission or module blocks it | Check lookup scope, use public API or `privateLookupIn` with appropriate permissions |
| Have handle but `get()` fails on instance field | Missing `State` receiver coordinate | Use `get(state)`; check `coordinateTypes()` |
| Passing receiver for static field | Static coordinate list is empty | Use `global.get()` and `global.set(value)` |
| `WrongMethodTypeException` | Signature-polymorphic call site mismatches in arity/types/return | Check `accessModeType(...)` and cast the return type accurately, especially primitives |
| `ArrayIndexOutOfBoundsException` | Negative or out-of-bounds array index | Check `0 <= index && index < array.length` |
| `NullPointerException` on array/instance operation | Receiver or array is `null` | Validate inputs before calling |
| `UnsupportedOperationException` when writing `final` field | SET mode is not supported | Check `isAccessModeSupported(SET)` and verify whether the field is writable |
| `UnsupportedOperationException` with `getAndAdd` | Variable type or permissions make the access mode unsupported | Choose a supported access mode; do not force addition on arbitrary types |
| `IllegalArgumentException` at `arrayElementVarHandle` | Passing a non-array class, such as `String.class` | Use `String[].class` or a valid array type |
| Works in demo class but fails across modules | Different lookup/module openness | Identify where `Lookup` is created, which module declares the field, and `exports`/`opens` policy |

### 9.1. Why does `Field` existing not mean a VarHandle can be created?

`Class.getDeclaredField(name)` is a metadata query: it finds a field **declared** in the class, regardless of public/private. But creating a VarHandle capable of executing field access requires an appropriate `Lookup`. If a tool can read the field name but cannot create a handle, check access control first rather than automatically blaming the field name.

### 9.2. Do not guess types by boxing

Signature-polymorphic calls require types according to the JVM model:

```java
// int field:
int n = (int) countHandle.get(state);

// long static field:
long sum = (long) totalHandle.get();
```

The above is a **snippet**, requiring the already-created handles. Do not use `Integer.class` to look up an `int` field; and do not assume `(Object)handle.get(...)` is equivalent to `(int)handle.get(...)` in all cases. `VarHandle` may provide appropriate conversion mechanisms in some access modes, but exact types and access-mode types remain the source of truth for diagnosis.

### 9.3. Do not use a field name as an array element "address"

An element `array[index]` does not appear as a field named `"0"` or `"length[1]"` on a class; create an array element handle with `MethodHandles.arrayElementVarHandle`. `array.length` is array size information, not a writable element VarHandle. One array VarHandle can be used with any compatible array when supplied the right runtime coordinates.

### 9.4. Do not confuse VarHandle with MethodHandle

`VarHandle` represents a variable and accesses by **access mode**. `MethodHandle` represents an invocation. You can create a MethodHandle from a VarHandle using `toMethodHandle(VarHandle.AccessMode.GET)` if you truly need to integrate with a method handles pipeline, but that is an **extra conversion step**, not required for creating a VarHandle.

Example:

```java
// Snippet, assuming import java.lang.invoke.*.
MethodHandle getter =
        instance.toMethodHandle(VarHandle.AccessMode.GET);
int n = (int) getter.invokeExact(state);
```

Here `getter` has a type equivalent to `(State)int`; `invokeExact` applies MethodHandle's exact matching rules, which differs from `instance.get(state)`, a VarHandle access-mode invocation. Do not choose `toMethodHandle` just for simple field reads when `get` is sufficient.

## 10. Workflow for choosing a factory in a real application

Suppose a framework receives a field descriptor and wants a fast accessor; the following workflow can be applied:

1. **Identify the variable to operate on**: is it an instance field, static field, or array element? Do not infer solely from the field name; verify the `static` declaration/array type.
2. **Determine the exact type**: get `field.getType()` when a `Field` is available, or use `int.class`, `long.class`, `String.class`... matching exactly.
3. **Choose the factory**:
   - instance → `findVarHandle(declaringClass,name,fieldType)`;
   - static → `findStaticVarHandle(declaringClass,name,fieldType)`;
   - array element → `arrayElementVarHandle(arrayClass)`;
   - `Field` already available → consider `unreflectVarHandle(field)`.
4. **Provide a `Lookup` with the right permissions**. Prefer creating it inside the class/module owning the field. For private fields of other classes, check module access rules and `privateLookupIn` before using flags.
5. **Read the handle's metadata**: `varType()` and `coordinateTypes()`; do not assume a static variable needs a receiver or a 2D array takes two indices in a single VarHandle.
6. **Determine the access mode** to use and check `isAccessModeSupported(...)` when unsure, especially for `final` fields or atomic addition.
7. **Build the call site with the right signature**; check `accessModeType(...)` when encountering errors. Separate coordinates from expected/new value/delta to ensure the right order.
8. **Test edge cases**: null receiver, null array, negative/out-of-bounds index, wrong type, non-existent field, final field, and missing permissions.
9. **Cache valid handles when needed**, but do not assume the same `Lookup` will have permissions in every module/execution point.
10. **Evaluate synchronization needs**: only when the goal is multi-threaded operation should you choose the appropriate memory-ordering or atomic mode; creating a handle by itself does not make plain updates atomic.

An API design principle: store **variable-kind metadata** alongside the handle. For example, a wrapper component that knows `coordinateTypes().size()==0` for static should not force the caller to pass a useless object. For arrays, clearly declare the `(array,index)` coordinates in the API contract. Avoid creating wrappers that do not distinguish variable kinds and then fail at runtime due to missing/extra coordinates.

## 11. Exercises and check questions

**Question 1.** Given a class `Account` containing `private int balance;`. Which factory should be used and what should be passed to `get`?  
**Answer:** With a lookup that has appropriate permissions, `lookup.findVarHandle(Account.class,"balance",int.class)`; read with `(int) vh.get(accountInstance)`. The handle has one coordinate, which is `Account`.

**Question 2.** Given `static long sequence` in `Account`. Why is `vh.get(new Account())` wrong?  
**Answer:** A static handle created via `findStaticVarHandle` has `coordinateTypes()=[]`. Use `(long)vh.get()`; there is no receiver.

**Question 3.** Create `MethodHandles.arrayElementVarHandle(byte[].class)`. What are `varType()` and the coordinates?  
**Answer:** `varType()=byte.class`, and the coordinates are `[byte[].class,int.class]`.

**Question 4.** Want to process the element at index 3 of an array of length 3. Is it necessary to create a new VarHandle?  
**Answer:** No. Valid indices for an array of length 3 are 0, 1, 2; `get(array,3)` will error. Fix the index or array size, do not create another handle.

**Question 5.** `Field.getDeclaredField("secret")` succeeds; does `lookup.unreflectVarHandle(field)` always succeed?  
**Answer:** No. Metadata and access rights are two different things. Lookup must have appropriate permissions for the field and module.

**Question 6.** A handle reading `private final String name` is created successfully. Can `set` be used since private access is valid?  
**Answer:** No. Final fields do not support write access modes like mutable fields; check `isAccessModeSupported(SET)`. The example in section 6 shows `false` and `UnsupportedOperationException`.

**Question 7.** From `String[][] matrix`, use `arrayElementVarHandle(String[][].class)`. Is the element type `String` or `String[]`?  
**Answer:** `String[]` because an outer-level element of a 2D array is a `String[]` row. The handle's coordinates are `(String[][],int)`.

**Question 8.** Does `getAndAdd(state,5)` on an `int` instance field return the value before or after the update?  
**Answer:** It returns the **old value** and performs the atomic addition if the mode is supported. The example showed `9/12` when adding 3 to 9.

**Question 9.** Given only `VarHandle vh` without knowing which variable it points to. How do you know whether to call `get()`, `get(receiver)`, or `get(array,index)`?  
**Answer:** Read `vh.coordinateTypes()` and `vh.varType()`; you can also inspect `vh.accessModeType(GET)`. Do not guess from the handle's name.

**Question 10.** A class is in another module and its private field is not opened to the calling module. Can you just use `MethodHandles.lookup().findVarHandle(...)` to bypass JPMS?  
**Answer:** No. Valid lookup/module permissions are required; consider a public API, `opens`, or `privateLookupIn` within permitted scope. Having the right field name and type does not grant access permission.

## 12. Summary and official documentation

Remember the three formulas:

```text
instance:
  findVarHandle(Owner.class, "field", FieldType.class)
  coordinateTypes = [Owner]
  get(owner), set(owner, value)

static:
  findStaticVarHandle(Owner.class, "field", FieldType.class)
  coordinateTypes = []
  get(), set(value)

array element:
  arrayElementVarHandle(ElementType[].class)
  coordinateTypes = [ElementType[], int]
  get(array, index), set(array, index, value)
```

In real code, `FieldType.class` above is a **descriptive notation** for the field type, not a valid Java literal when `FieldType` is an arbitrary primitive. For example, use `int.class`, `long.class`, or `String.class` respectively. Similarly, `ElementType[].class` represents array type syntax such as `int[].class` and `String[].class`.

**Three most important decisions:**

- **Choose the right factory** to accurately describe instance/static/array.
- **Choose the right coordinates** before invoking an access mode, and only then pass value/expected/delta.
- **Separate Lookup permissions and supported access modes** from the idea that “creating a handle lets you call every operation”. Final, modules, access modifiers, and variable kinds still take effect.

Official documentation:

- [Oracle Java SE 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): `varType()`, `coordinateTypes()`, `accessModeType()`, `isAccessModeSupported()`, and access modes.
- [Oracle Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle()`, `findStaticVarHandle()`, `unreflectVarHandle()`, and lookup permissions.
- [Oracle Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `arrayElementVarHandle()` and `privateLookupIn()`.
- [Oracle Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): parameter/return types of access modes and of MethodHandle.
