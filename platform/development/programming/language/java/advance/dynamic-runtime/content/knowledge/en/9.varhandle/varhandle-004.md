# 9.4. Variable type, coordinate types, and accessModeType of each operation

> **Context:** This is a Knowledge lesson in the **9. VarHandle** group of the **Java Advance – dynamic-runtime** module. A `VarHandle` does not just "point to a field": it represents *a variable or a family of variables* by its **value type** (`varType()`), **list of coordinate types** (`coordinateTypes()`), and **signature of each access mode** (`accessModeType(...)`). Understanding these three components properly is the foundation for calling `get`, `set`, CAS, atomic updates, and diagnosing `WrongMethodTypeException` on Java 21.

## 1. Objectives and scope

After this lesson, you should be able to:

1. Define `T = vh.varType()`, `CT = vh.coordinateTypes()`, and know when `CT` is empty, has one element, or has multiple elements.
2. Identify `T` and coordinates for an instance field, static field, array element, multidimensional array, and `byte[]`/`ByteBuffer` view.
3. Deduce the return type and parameter order of **all access mode groups** from a `(T, CT)` pair, then verify with `vh.accessModeType(AccessMode.X)`.
4. Distinguish between **a signature existing** and **a mode being supported** (`isAccessModeSupported`), especially with `final`, reference, boolean, numeric types, and memory views.
5. Understand the difference between *plain/opaque/acquire/release/volatile* in memory semantics even when modes may use the **same MethodType**.
6. Invoke `VarHandle` and `toMethodHandle` with the correct receiver/array index position, value type, and return cast; identify the causes of `WrongMethodTypeException` and `UnsupportedOperationException`.
7. Write a pure JDK 21 program to self-check signatures and behavior, without needing frameworks or `sun.*`/`jdk.internal.*`.

**Prerequisites:** `static`/instance fields, arrays, `Class<?>`, `MethodType`, `MethodHandle`, visibility/access control, and awareness-level knowledge of the Java Memory Model. The labs use `java.lang.invoke` from Java 21.

## 2. Core model: a VarHandle has T and CT

A `VarHandle` is associated with:

- **Variable type `T`**: the type of the value being read, written, or updated. Java API: `Class<?> varType()`.
- **Coordinate types `CT1..CTn`**: an ordered list of types used to **identify a specific variable**. Java API: `List<Class<?>> coordinateTypes()`.
- **Access modes**: ways of operating on the identified variable; each mode has its own **`MethodType`** describing *parameters* and *return*.

Inference diagram:

```text
VarHandle
├── varType()            = T
├── coordinateTypes()    = [CT1, CT2, ... CTn]
└── accessModeType(mode) = MethodType(
       return type by mode,
       CT1, CT2, ... CTn, [value parameters by mode]
    )

Example: int[] values
  T  = int
  CT = [int[], int]
  GET             = (int[], int)int
  SET             = (int[], int, int)void
  COMPARE_AND_SET = (int[], int, int, int)boolean
```

**Coordinates are not data parameters to be written.** For an `int[]` array, the two coordinates are the *specific array* and the *index*. For a `set` call, the final `int` argument is the value to be written. For compare-and-set, after the coordinates there are **two** arguments: `expected` and `newValue`.

`coordinateTypes()` returns an **unmodifiable** list per the API contract; do not rely on the list's implementation class. Each element is a `Class<?>`, which can be a primitive `int.class`, an array type `int[].class`, or an object type `Box.class`.

### 2.1. General formula

Let `C = (CT1, ..., CTn)` and `T = variable type`:

| Operation group | Access-mode type |
| --- | --- |
| Read | `(C)T` |
| Write | `(C, T newValue)void` |
| Compare-and-set / weak CAS | `(C, T expectedValue, T newValue)boolean` |
| Compare-and-exchange | `(C, T expectedValue, T newValue)T` |
| Get-and-set | `(C, T newValue)T` |
| Get-and-add | `(C, T delta)T` |
| Get-and-bitwise | `(C, T mask)T` |

`C` is the **parameter list portion** to be expanded, not a parameter object named C. With `C=[]`, `(C)T` becomes `()T`. With `C=[Box.class]`, `(C,T)void` becomes `(Box,T)void`. With `C=[int[].class,int.class]`, adding the `int` value makes it `(int[],int,int)void`.

## 3. Creating a VarHandle and deducing coordinates from variable storage

### 3.1. Instance field

```java
// Illustrative declaration and lookup in a class within the same access scope.
class Counter { int value; }
VarHandle vh = MethodHandles.lookup()
        .findVarHandle(Counter.class, "value", int.class);
```

`T = int.class` and `CT = [Counter.class]`. The coordinate is the **Counter object** (receiver). `get(counter)` has the signature `(Counter)int`; `set(counter, 7)` has the signature `(Counter,int)void`.

Do not confuse `T` with the class type containing the field. `Counter` is the **coordinate type**, while `int` is the **variable type**. `Lookup.findVarHandle` checks permissions and requires the exact field name/field type. For a protected field accessed through a subclass in a different package, the receiver type in the handle may be narrowed according to access control rules; do not assume generally that every handle uses the original declaring class as its coordinate.

### 3.2. Static field

```java
// Illustrative snippet, located in a class with access to Counter.
class Counter { static String label; }
VarHandle vh = MethodHandles.lookup()
        .findStaticVarHandle(Counter.class, "label", String.class);
```

`T = String.class` and `CT = []` (no receiver). `get()` has type `()String` and `set("ready")` has type `(String)void`. The class used to **lookup the field** does not automatically appear as a coordinate.

When operating a static field `VarHandle`, the JVM may need to initialize the declaring class according to the corresponding rules. This does not change the number of coordinate types.

### 3.3. Array element

```java
// Illustrative snippet:
VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);
int[] values = {2, 4, 6};
int old = (int) vh.getAndAdd(values, 1, 5);
```

`T = int.class`, `CT = [int[].class, int.class]`. The first coordinate is the **array**, and the second coordinate is the **element index**. `getAndAdd(values,1,5)` has type `(int[],int,int)int`. If starting with `values[1]=4`, `old=4` and that element becomes `9`.

With `MethodHandles.arrayElementVarHandle(String[][].class)`, **each referenced variable is an element of the outer array**; therefore `T = String[].class` and `CT = [String[][].class, int.class]`. The API **does not automatically add a second int coordinate** just because the component is an array. To point further to a `String` inside the inner array, use a second array access step or another handle for `String[].class`.

### 3.4. Byte-array and ByteBuffer views

`MethodHandles.byteArrayViewVarHandle(int[].class, ByteOrder.nativeOrder())` has `T = int.class`, `CT = [byte[].class, int.class]`. `MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.nativeOrder())` has `CT = [ByteBuffer.class, int.class]`. Here, the last `int` parameter of the **coordinates** is the **byte offset**, not the index of a physical `int[]`. How the bytes are decoded depends on the `ByteOrder` chosen when creating the view.

With an `int` view, a single read uses four bytes from the appropriate position. Support for atomic modes also depends on **alignment**, accessibility, and for `ByteBuffer`, its read-only state. Do not assume that having a valid type signature means every address supports CAS; unaligned access may throw `IllegalStateException`, out-of-bounds regions throw an index error, and writing to a read-only buffer throws `ReadOnlyBufferException`.

### 3.5. Comparison table

| Handle source | `T = varType()` | `CT = coordinateTypes()` | GET type | SET type |
| --- | --- | --- | --- | --- |
| Instance `Box.count: int` | `int` | `[Box]` | `(Box)int` | `(Box,int)void` |
| Static `Box.banner: String` | `String` | `[]` | `()String` | `(String)void` |
| `arrayElementVarHandle(int[].class)` | `int` | `[int[], int]` | `(int[],int)int` | `(int[],int,int)void` |
| `arrayElementVarHandle(String[][].class)` | `String[]` | `[String[][], int]` | `(String[][],int)String[]` | `(String[][],int,String[])void` |
| `byteArrayViewVarHandle(int[].class, ...)` | `int` | `[byte[], int]` | `(byte[],int)int` | `(byte[],int,int)void` |
| `byteBufferViewVarHandle(int[].class, ...)` | `int` | `[ByteBuffer, int]` | `(ByteBuffer,int)int` | `(ByteBuffer,int,int)void` |

This table is a **signature pattern**, not a guarantee that all access modes are supported at every address or on `final` fields.

## 4. What does `accessModeType(AccessMode)` return?

`vh.accessModeType(mode)` returns a `java.lang.invoke.MethodType` having:

1. **Parameter prefix**: exactly the `CT1..CTn` of `vh.coordinateTypes()`, **preserving order**.
2. **Parameter suffix**: 0, 1, or 2 parameters of type `T` depending on the operation.
3. **Return type**: `T`, `void.class`, or `boolean.class` depending on the group.

You can read `MethodType.parameterCount()`, `parameterType(i)`, `returnType()`, or print `MethodType.toString()` directly to inspect. For example, `(Box,int,int)boolean` is the **type of the access mode method**, not necessarily a method declared directly in class `Box`.

**Crucial point:** `accessModeType(...)` still provides a type for an **unsupported** mode. To know whether that mode can be executed, check **`isAccessModeSupported(mode)`**. If the result is false, calling that mode will throw `UnsupportedOperationException`. `accessModeType` returning a type only proves the JVM knows the **call shape**, not that the operation is permitted.

### 4.1. Exhaustive mapping of access mode groups

Every `VarHandle.AccessMode` enum constant in Java 21 falls into the groups below. The Acquire/Release/Volatile/Opaque suffixes change the **memory semantics** or strength of the operation, without changing the listed *shape*.

| AccessMode enum | Corresponding method | `accessModeType` |
| --- | --- | --- |
| `GET`, `GET_OPAQUE`, `GET_ACQUIRE`, `GET_VOLATILE` | `get`, `getOpaque`, `getAcquire`, `getVolatile` | `(C)T` |
| `SET`, `SET_OPAQUE`, `SET_RELEASE`, `SET_VOLATILE` | `set`, `setOpaque`, `setRelease`, `setVolatile` | `(C,T)void` |
| `COMPARE_AND_SET` | `compareAndSet` | `(C,T,T)boolean` |
| `WEAK_COMPARE_AND_SET_PLAIN`, `WEAK_COMPARE_AND_SET`, `WEAK_COMPARE_AND_SET_ACQUIRE`, `WEAK_COMPARE_AND_SET_RELEASE` | `weakCompareAndSetPlain`, `weakCompareAndSet`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease` | `(C,T,T)boolean` |
| `COMPARE_AND_EXCHANGE`, `COMPARE_AND_EXCHANGE_ACQUIRE`, `COMPARE_AND_EXCHANGE_RELEASE` | `compareAndExchange`, `compareAndExchangeAcquire`, `compareAndExchangeRelease` | `(C,T,T)T` |
| `GET_AND_SET`, `GET_AND_SET_ACQUIRE`, `GET_AND_SET_RELEASE` | `getAndSet`, `getAndSetAcquire`, `getAndSetRelease` | `(C,T)T` |
| `GET_AND_ADD`, `GET_AND_ADD_ACQUIRE`, `GET_AND_ADD_RELEASE` | `getAndAdd`, `getAndAddAcquire`, `getAndAddRelease` | `(C,T)T` |
| `GET_AND_BITWISE_OR`, `GET_AND_BITWISE_OR_ACQUIRE`, `GET_AND_BITWISE_OR_RELEASE` | `getAndBitwiseOr`, `getAndBitwiseOrAcquire`, `getAndBitwiseOrRelease` | `(C,T)T` |
| `GET_AND_BITWISE_AND`, `GET_AND_BITWISE_AND_ACQUIRE`, `GET_AND_BITWISE_AND_RELEASE` | `getAndBitwiseAnd`, `getAndBitwiseAndAcquire`, `getAndBitwiseAndRelease` | `(C,T)T` |
| `GET_AND_BITWISE_XOR`, `GET_AND_BITWISE_XOR_ACQUIRE`, `GET_AND_BITWISE_XOR_RELEASE` | `getAndBitwiseXor`, `getAndBitwiseXorAcquire`, `getAndBitwiseXorRelease` | `(C,T)T` |

Enum names use **UPPER_SNAKE_CASE**, while method names use **camelCase**; `mode.methodName()` returns the corresponding method name. Both `GET_AND_ADD` and `GET_AND_ADD_ACQUIRE` have the same number and types of parameters, but different memory ordering.

### 4.2. Meaning of return values

- **`get*`**: returns the read `T` value.
- **`set*`**: returns `void`, write only.
- **`compareAndSet` and `weakCompareAndSet*`**: returns `boolean`; true means the update succeeded according to the mode's rules. *Weak CAS* can **fail spuriously** even when the current value equals expected; a retry loop is needed if required.
- **`compareAndExchange*`**: returns `T`, which is the **witness value observed before the operation**. It does not return a boolean; compare the witness with expected to deduce the success condition according to the type's comparison rules.
- **`getAndSet*`**: returns the old `T` value and replaces it with the new value.
- **`getAndAdd*`**: returns the old `T` value, updates by adding delta.
- **`getAndBitwiseOr/And/Xor*`**: returns the old `T` value, updates by applying the bitwise operation with mask.

The `(C, expected, newValue)` order of CAS cannot be swapped. For reference types, CAS uses identity/value comparison according to VarHandle's compare rules, without calling the object's `equals()` to check content equality. For `float`/`double`, compare operations use the bitwise representation of the number; NaN and `-0.0`/`+0.0` require attention, differing from ordinary arithmetic comparison.

## 5. Lab 1 — printing varType, coordinateTypes, and accessModeType

Create **`VarHandleShapeLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.util.Arrays;

public class VarHandleShapeLab {
    static class Box {
        volatile int count = 7;
        static String banner = "hello";
        final long id = 42L;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle field = lookup.findVarHandle(Box.class, "count", int.class);
        VarHandle statik = lookup.findStaticVarHandle(Box.class, "banner", String.class);
        VarHandle array = MethodHandles.arrayElementVarHandle(int[].class);
        VarHandle readOnly = lookup.findVarHandle(Box.class, "id", long.class);

        System.out.println("field.variable=" + field.varType().getTypeName());
        System.out.println("field.coordinates=" + field.coordinateTypes());
        System.out.println("field.GET=" + field.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("field.SET=" + field.accessModeType(VarHandle.AccessMode.SET));
        System.out.println("field.CAS=" + field.accessModeType(VarHandle.AccessMode.COMPARE_AND_SET));
        System.out.println("field.CAE=" + field.accessModeType(VarHandle.AccessMode.COMPARE_AND_EXCHANGE));
        System.out.println("field.ADD=" + field.accessModeType(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("field.OR=" + field.accessModeType(VarHandle.AccessMode.GET_AND_BITWISE_OR));

        System.out.println("static.variable=" + statik.varType().getTypeName());
        System.out.println("static.coordinates=" + statik.coordinateTypes());
        System.out.println("static.GET=" + statik.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("static.SET=" + statik.accessModeType(VarHandle.AccessMode.SET));

        System.out.println("array.variable=" + array.varType().getTypeName());
        System.out.println("array.coordinates=" + array.coordinateTypes());
        System.out.println("array.GET=" + array.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("array.CAS=" + array.accessModeType(VarHandle.AccessMode.COMPARE_AND_SET));

        System.out.println("readonly.SET.supported=" +
                readOnly.isAccessModeSupported(VarHandle.AccessMode.SET));
        System.out.println("readonly.GET=" + readOnly.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("readonly.SET=" + readOnly.accessModeType(VarHandle.AccessMode.SET));

        System.out.println("string.ADD.supported=" +
                statik.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("string.OR.supported=" +
                statik.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("int.ADD.supported=" +
                field.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("int.OR.supported=" +
                field.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));

        System.out.println("GET_VOLATILE.sameType=" +
                field.accessModeType(VarHandle.AccessMode.GET)
                        .equals(field.accessModeType(VarHandle.AccessMode.GET_VOLATILE)));
        System.out.println("SET_RELEASE.sameType=" +
                field.accessModeType(VarHandle.AccessMode.SET)
                        .equals(field.accessModeType(VarHandle.AccessMode.SET_RELEASE)));
        System.out.println("methodHandle.type.equals=" +
                field.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD).type()
                        .equals(field.accessModeType(VarHandle.AccessMode.GET_AND_ADD)));
    }
}
```

Compile and run in the same directory containing the file:

```sh
javac --release 21 -Xlint:all VarHandleShapeLab.java
java VarHandleShapeLab
```

**Meaningful stdout (`MethodType.toString()` and `Class.toString()` format):**

```text
field.variable=int
field.coordinates=[class VarHandleShapeLab$Box]
field.GET=(Box)int
field.SET=(Box,int)void
field.CAS=(Box,int,int)boolean
field.CAE=(Box,int,int)int
field.ADD=(Box,int)int
field.OR=(Box,int)int
static.variable=java.lang.String
static.coordinates=[]
static.GET=()String
static.SET=(String)void
array.variable=int
array.coordinates=[class [I, int]
array.GET=(int[],int)int
array.CAS=(int[],int,int,int)boolean
readonly.SET.supported=false
readonly.GET=(Box)long
readonly.SET=(Box,long)void
string.ADD.supported=false
string.OR.supported=false
int.ADD.supported=true
int.OR.supported=true
GET_VOLATILE.sameType=true
SET_RELEASE.sameType=true
methodHandle.type.equals=true
```

### 5.1. Analysis of each result group

1. **Instance field**: `field.varType()` is `int`, and the coordinate list has only `Box`. CAS needs `Box` + expected `int` + new `int` and returns `boolean`.
2. **Static field**: `banner` has `String` variable type, **no coordinates**. `GET` takes 0 parameters and returns `String`.
3. **Array**: `varType=int` does not mean passing only an `int`. You must provide `int[]` and the index before the value to write.
4. **`final` field**: `SET` has a defined `MethodType`, but `isAccessModeSupported(SET)` is `false`. There is no contradiction: one is the *signature*, the other is *executability*.
5. **Reference type `String`**: numeric atomic updates and bitwise atomic updates are not supported; comparing `String` with CAS or `getAndSet` can still be available when the field is non-final.
6. **Same type, different memory semantics**: `GET` and `GET_VOLATILE` are both `(Box)int`; `SET` and `SET_RELEASE` are both `(Box,int)void`.
7. **Converting to MethodHandle**: `toMethodHandle(GET_AND_ADD)` returns a handle **bound to the VarHandle**, with a type equal to `accessModeType(GET_AND_ADD)`. It does not automatically add a `VarHandle` parameter to the bound handle's type.

Some ways of printing `Class<?>` in a list will use the array's binary/JVM name (`class [I`) instead of `int[]`. For friendly display, iterate over the list and use `Class.getTypeName()`; do not parse `Class.toString()` with regex.

## 6. Per-mode support: what does the variable's type determine?

You cannot deduce `isAccessModeSupported` from the signature form alone. VarHandles created via the JDK's field/array factories follow these foundational rules:

| Variable type `T` / storage | Read (`get*`) | Write (`set*`) / CAS / getAndSet | `getAndAdd*` | `getAndBitwise*` |
| --- | --- | --- | --- | --- |
| Non-final `int` field | Yes | Yes | Yes | Yes |
| Non-final `long` field | Yes | Yes | Yes | Yes |
| Non-final `float`/`double` field | Yes | Yes | Yes | **No** |
| Non-final `boolean` field | Yes | Yes | **No** | Yes |
| Non-final `String`/reference field | Yes | Yes | **No** | **No** |
| `final long` field | Yes | **No** | **No** | **No** |
| `int[]` element | Yes | Yes | Yes | Yes |
| `String[]` element | Yes | Yes | **No** | **No** |
| `ByteBuffer` view `int` | Yes | Depends on mode, alignment, and buffer read-only state | Depends on view type, alignment | Depends on view type, alignment |

For standard instance/static fields and array-element VarHandles:

- Numeric atomic updates `GET_AND_ADD*` are supported for `byte`, `short`, `char`, `int`, `long`, `float`, `double`; **not supported for boolean or reference**.
- Bitwise atomic updates `GET_AND_BITWISE_{OR,AND,XOR}*` support `boolean`, `byte`, `short`, `char`, `int`, `long`; **not supported for float/double/reference**.
- Compare-and-set, compare-and-exchange, and get-and-set are supported for updatable variable types when the factory/memory system provides that operation.
- A `final` field creates a read-only VarHandle: all write/atomic updates are unsupported; `get` is always supported.
- Byte-array/ByteBuffer view factories have **their own restrictions** based on primitive view type and alignment, and cannot be substituted by the table for regular fields/arrays.

`isAccessModeSupported` is a necessary check when selecting modes dynamically; however, a `true` result does not rule out runtime errors caused by invalid coordinates, out-of-bounds array indices, or misalignment. Especially with `ByteBuffer`, the **read-only** state of the buffer is a property of the **coordinate object at usage time**, which cannot be fully reflected by a `MethodType` signature.

### 6.1. `get` API is always supported, while other modes need checking

Per the `VarHandle` contract, `get` is supported for every VarHandle. `set` or update operations may be unsupported because of `final`, because the variable does not have an appropriate type for numeric/bitwise operations, or because of factory characteristics.

Even when `vh.accessModeType(SET)` is `(Box,long)void` for `final long id`, calling `vh.set(box, 1L)` still throws `UnsupportedOperationException`. Check `isAccessModeSupported` before exposing an API for a user-selectable mode; at the same time, still catch appropriate runtime errors.

## 7. Lab 2 — running operations and reading return types

Create file **`VarHandleCallsLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleCallsLab {
    static class Box {
        volatile int count = 7;
        final long id = 42;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle counter = lookup.findVarHandle(Box.class, "count", int.class);
        VarHandle id = lookup.findVarHandle(Box.class, "id", long.class);
        Box box = new Box();

        int initial = (int) counter.get(box);
        counter.setRelease(box, 10);
        int afterRelease = (int) counter.getAcquire(box);
        int oldAdd = (int) counter.getAndAdd(box, 5);
        boolean cas = counter.compareAndSet(box, 15, 18);
        int witness = (int) counter.compareAndExchange(box, 18, 30);
        int oldXor = (int) counter.getAndBitwiseXor(box, 3);
        MethodHandle bound = counter.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD);
        int previous = (int) bound.invokeExact(box, 4);

        System.out.println("initial=" + initial);
        System.out.println("afterRelease=" + afterRelease);
        System.out.println("oldAdd=" + oldAdd);
        System.out.println("cas=" + cas);
        System.out.println("witness=" + witness);
        System.out.println("oldXor=" + oldXor);
        System.out.println("handlePrevious=" + previous);
        System.out.println("finalCount=" + (int) counter.getVolatile(box));

        try {
            id.set(box, 1L);
            System.out.println("readonly=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readonly=UnsupportedOperationException");
        }

        VarHandle exact = counter.withInvokeExactBehavior();
        try {
            Object ignored = exact.get(box);
            System.out.println("exact=unexpected " + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact=WrongMethodTypeException");
        }
    }
}
```

Commands:

```sh
javac --release 21 -Xlint:all VarHandleCallsLab.java
java VarHandleCallsLab
```

**Stdout:**

```text
initial=7
afterRelease=10
oldAdd=10
cas=true
witness=18
oldXor=30
handlePrevious=29
finalCount=33
readonly=UnsupportedOperationException
exact=WrongMethodTypeException
```

### 7.1. Each value-modifying operation

- Initially `count=7`. `setRelease(box,10)` writes 10, `getAcquire(box)` reads back 10.
- `getAndAdd(box,5)` returns **10** (the old value), then updates `count=15`.
- `compareAndSet(box,15,18)` returns `true`, then updates `count=18`.
- `compareAndExchange(box,18,30)` returns witness **18**, then updates `count=30`.
- `getAndBitwiseXor(box,3)` returns **30**, then updates `30 ^ 3 = 29`.
- The bound handle `toMethodHandle(GET_AND_ADD)` takes `(Box,int)int`. `invokeExact(box,4)` returns **29**, then updates `count=33`.
- The final `getVolatile` reads 33. This is a **single-thread** example to recognize signatures/return values, not proof of correctness for any multithreaded protocol.

### 7.2. Two errors that cannot be merged into one

- `UnsupportedOperationException`: the call is structurally valid, but **the mode is unsupported**, for example attempting to `set` a `final` field.
- `WrongMethodTypeException`: the call does not match the **expected MethodType** (number/types of coordinates, value, or return type according to the invocation behavior being used). In the lab, `withInvokeExactBehavior()` requires an exact call-site type; the target variable `Object ignored` causes the expected return type at the call site to be `Object`, whereas `GET` on an `int` VarHandle requires a primitive `int` return.

`withInvokeExactBehavior()` has existed since Java versions prior to 21 and adjusts how signature checking is performed on access-mode calls, without changing `varType()`/`coordinateTypes()`. By default, VarHandle can behave like `MethodHandle.invoke` with certain valid conversions; do not assume every mismatch produces the exact same exception type without knowing the invocation mode. Printing `accessModeType` before calling is a better debugging approach than guessing.

## 8. Lab 3 — array element and limitations of reference arrays

Create **`ArrayModeLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class ArrayModeLab {
    public static void main(String[] args) {
        VarHandle ints = MethodHandles.arrayElementVarHandle(int[].class);
        int[] values = {3, 4};

        int old = (int) ints.getAndAdd(values, 1, 6);
        int now = (int) ints.get(values, 1);
        boolean changed = ints.compareAndSet(values, 0, 3, 9);
        VarHandle strings = MethodHandles.arrayElementVarHandle(String[].class);

        System.out.println("array.old=" + old);
        System.out.println("array.now=" + now);
        System.out.println("array.cas=" + changed);
        System.out.println("array.first=" + values[0]);
        System.out.println("string.variable=" + strings.varType().getTypeName());
        System.out.println("string.coordinates=" + strings.coordinateTypes());
        System.out.println("string.GET=" + strings.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("string.ADD.supported=" +
                strings.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("string.BITWISE.supported=" +
                strings.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
    }
}
```

```sh
javac --release 21 -Xlint:all ArrayModeLab.java
java ArrayModeLab
```

**Stdout:**

```text
array.old=4
array.now=10
array.cas=true
array.first=9
string.variable=java.lang.String
string.coordinates=[class [Ljava.lang.String;, int]
string.GET=(String[],int)String
string.ADD.supported=false
string.BITWISE.supported=false
```

`arrayElementVarHandle(String[].class)` has exactly two coordinates, **`String[]` and `int`**; the variable type is `String`. It can support CAS with references, but cannot perform numeric addition or bitwise operations on `String`. This example shows that the **variable's type** determines the arithmetic update group, while **coordinates** only identify the data slot to act upon.

### 8.1. Invalid coordinates when accessing arrays

`get(values,-1)` cannot be valid just because accessModeType is `(int[],int)int`. The JVM still checks **concrete coordinates** and throws `ArrayIndexOutOfBoundsException` for an invalid index; a `null` array can throw `NullPointerException`. `MethodType` describes the shape, not the range constraints of the index value.

## 9. Lab 4 — multidimensional arrays, ByteBuffer views, and erasure

Create **`VarHandleEdgeLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;
import java.util.List;

public class VarHandleEdgeLab {
    static class GenericBox {
        List<String> words;
    }

    static final class Box {
        final int constant = 5;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        VarHandle twoD = MethodHandles.arrayElementVarHandle(String[][].class);
        VarHandle bytes = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.nativeOrder());
        VarHandle buffer = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.nativeOrder());
        VarHandle generic = MethodHandles.lookup().findVarHandle(
                GenericBox.class, "words", List.class);
        VarHandle bools = MethodHandles.arrayElementVarHandle(boolean[].class);
        VarHandle doubles = MethodHandles.arrayElementVarHandle(double[].class);
        VarHandle readOnly = MethodHandles.lookup().findVarHandle(
                Box.class, "constant", int.class);

        System.out.println("2D.varType=" + twoD.varType().getTypeName());
        System.out.println("2D.coordinates=" + twoD.coordinateTypes());
        System.out.println("byteView.varType=" + bytes.varType().getTypeName());
        System.out.println("byteView.coordinates=" + bytes.coordinateTypes());
        System.out.println("bufferView.varType=" + buffer.varType().getTypeName());
        System.out.println("bufferView.coordinates=" + buffer.coordinateTypes());
        System.out.println("generic.varType=" + generic.varType().getTypeName());
        System.out.println("bool.ADD=" +
                bools.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("bool.BITWISE=" +
                bools.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("double.ADD=" +
                doubles.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("double.BITWISE=" +
                doubles.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("readonly.modeType=" +
                readOnly.accessModeType(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("getMode.name=" + VarHandle.AccessMode.GET.methodName());
    }
}
```

```sh
javac --release 21 -Xlint:all VarHandleEdgeLab.java
java VarHandleEdgeLab
```

**Stdout:**

```text
2D.varType=java.lang.String[]
2D.coordinates=[class [[Ljava.lang.String;, int]
byteView.varType=int
byteView.coordinates=[class [B, int]
bufferView.varType=int
bufferView.coordinates=[class java.nio.ByteBuffer, int]
generic.varType=java.util.List
bool.ADD=false
bool.BITWISE=true
double.ADD=true
double.BITWISE=false
readonly.modeType=(Box,int)int
getMode.name=get
```

**Analysis:**

1. `String[][]`: the element seen by VarHandle is a `String[]`; the single index identifies **an inner array**.
2. `byte[]`/`ByteBuffer` views: `T` is still `int`, the first coordinate changes according to where the bytes are stored; the same `(C,int)` suffix, but a different first parameter type and additional alignment/endianness constraints.
3. `GenericBox.words` is declared as `List<String>`, but `varType()` is **`List.class`** after type erasure. `VarHandle` does not retain the `String` type argument as a separate runtime variable type. If generic metadata is needed, read `Field.getGenericType()` from the declaration using Reflection.
4. `boolean` supports bitwise updates but not numeric add; `double` supports numeric add but not bitwise updates on regular fields/array elements.
5. `readOnly.accessModeType(GET_AND_ADD)` still returns **`(Box,int)int`**, even though the field is `final` and numeric update modes are unsupported. This demonstrates that **signature ≠ support**.

## 10. Different memory modes with the same signature

For the same `VarHandle` with fixed `T` and `CT`:

- `get`: plain read, with few cross-thread ordering constraints.
- `getOpaque`: opaque read, providing coherence/order specifically for the same variable per JMM rules; stronger than plain in that aspect.
- `getAcquire`: acquire read, used in protocols with a matching release write.
- `getVolatile`: volatile read, with stronger volatile semantics.
- `set`: plain write; `setOpaque`: opaque write; `setRelease`: release write; `setVolatile`: volatile write.
- Atomic update modes with `Acquire`/`Release` suffixes differ in memory effects; not all guarantee the same ordering as the plain-named version or the volatile version.
- `compareAndSet` has atomic update semantics per contract; `weakCompareAndSet*` may fail spuriously; `compareAndExchange*` returns the witness before the update.

**Yet all read modes are still `(C)T`**, and all write modes are still `(C,T)void`. You cannot look at `MethodType` to determine **memory ordering**. To know the ordering, you must also retain the chosen **AccessMode enum**.

Note that plain `get`/`set` on `long`/`double` have certain atomicity guarantees depending on platform and factory; `getVolatile` and other atomic modes have their own rules. Do not use signature similarity to assert that modes share the same threading properties.

### 10.1. When choosing acquire/release

A `setRelease` and `getAcquire` pair can be useful for a publish/consume protocol properly designed with the necessary synchronization/ordering; a **single thread** in Lab 2 only verifies the resulting value, not visibility across threads. Invariants, retry conditions, and published data must be designed carefully. If the problem only needs an atomic counter, use `getAndAdd`/CAS as required, or consider `AtomicInteger`/`AtomicLong`, which are often easier to read.

## 11. `MethodType`, signature-polymorphic invocation, and toMethodHandle

`VarHandle` access-mode methods are **signature-polymorphic**. Declarations in reflection may look as if they accept `Object...`, but the bytecode at the call site represents the **actual types** of the coordinates/values and return type. The compiler relies on the argument types/cast at the call site; at runtime, the JVM compares against the handle's `accessModeType`.

### 11.1. Why do many examples need a cast on the result?

```java
// Illustration within a scope having Counter counter and Box box.
int oldValue = (int) counter.getAndAdd(box, 1);
boolean changed = counter.compareAndSet(box, 1, 2);
counter.set(box, 3);
```

- `(int)` causes the call site to expect a primitive `int` return, matching the `GET_AND_ADD` mode on an `int` variable.
- `compareAndSet` returns a primitive `boolean`, so assigning to `boolean` is an appropriate form.
- `set` has a `void` return, typically called as a statement. Using it as an expression with a return type incompatible with the API mode will fail.
- Wrong number of coordinates, wrong receiver type, wrong number of value arguments, or wrong return type in exact mode can lead to `WrongMethodTypeException`.

Do not just read the signature shown by `Class.getDeclaredMethods()` and conclude that modes always take a real `Object[]`. Reflection sees the placeholder methods of signature polymorphism; calling a placeholder via `Method.invoke` does not perform a valid VarHandle access. Use the access modes directly, `accessModeType`, `toMethodHandle`, or VarHandle-specific invokers.

### 11.2. Bound MethodHandle and unbound invoker

`vh.toMethodHandle(mode)` returns a **MethodHandle bound to `vh`**. Because it already has the VarHandle receiver inside, this handle has the same `MethodType` as `vh.accessModeType(mode)`. It takes the coordinates and value arguments just like the corresponding mode.

Conversely, `MethodHandles.varHandleInvoker(mode, type)` or `varHandleExactInvoker(mode, type)` creates an **unbound invoker**; they require an extra `VarHandle` parameter at the beginning when invoked. Do not mistakenly apply this formula to `toMethodHandle`.

If `vh.withInvokeExactBehavior()` is used, mode calls on the new VarHandle require the call-site signature to match `accessModeType` exactly. `vh.withInvokeBehavior()` selects invocation behavior with conversions corresponding to `MethodHandle.invoke`. Neither method changes the variable/coordinate definition; they are choices of **how call types are checked and adapted**, which should align with API design.

### 11.3. Exception types and causes

| Exception | Common symptom | Investigation |
| --- | --- | --- |
| `WrongMethodTypeException` | Call-site type incompatible with access mode type, especially under exact behavior | Print `accessModeType`, check coordinate prefix, value suffix, return cast. |
| `UnsupportedOperationException` | Mode not supported, e.g., writing to `final` or getAndAdd with reference | Check `isAccessModeSupported(mode)`, variable type, and factory. |
| `ClassCastException` | May occur when casting a reference after a valid conversion, but the object is the wrong type | Check runtime type, cast, and where the VarHandle is held. |
| `NullPointerException` | Null receiver/array coordinate | Check object/array before accessing. |
| `ArrayIndexOutOfBoundsException` | Negative/out-of-bounds array index | Check index against array length. |
| `IndexOutOfBoundsException` | ByteBuffer view offset out of bounds | Check buffer limit and byte size of the view type. |
| `IllegalStateException` | Byte view access has unsuitable alignment for modes stronger than get/set | Align offset, check alignment and factory. |
| `ReadOnlyBufferException` | Writing to a read-only `ByteBuffer` | Check `isReadOnly()` and data design. |
| `NoSuchFieldException` / `IllegalAccessException` | Creating VarHandle via Lookup with incorrect name/type/access | Check declaring class, field type, access modifier, module permissions. |

`WrongMethodTypeException` is a **signature contract** error, while `UnsupportedOperationException` is a **mode support** error. Both occur in similar API areas but require completely different fixes.

## 12. How to systematically check Type and support

When receiving a `VarHandle` from a plugin, mapper, or metadata, check in this exact order:

```text
[1] Is the VarHandle valid and permitted for use?
     |
[2] varType(): Which primitive/reference/array is T?
     |
[3] coordinateTypes(): How many elements in CT, and in what order?
     |
[4] Choose AccessMode: GET/SET/CAS/GET_AND_ADD/...
     |
[5] accessModeType(mode): Expected MethodType
     |
[6] isAccessModeSupported(mode): Is it supported?
     |
[7] Check actual coordinate values: null, index, alignment...
     |
[8] Invoke with the right signature, observe return & exceptions
```

Do not infer support from the mode name or from the fact that a call compiles. Look at `accessModeType` to build an accurately typed adapter, then check `isAccessModeSupported` before execution if the mode is chosen dynamically.

Code snippet to iterate over **all enum modes** in a program that already has `VarHandle vh` (this is an **illustrative helper**, not a standalone Java program):

```java
for (VarHandle.AccessMode mode : VarHandle.AccessMode.values()) {
    System.out.printf(
            "%-34s %-12s %s%n",
            mode,
            vh.isAccessModeSupported(mode),
            vh.accessModeType(mode)
    );
}
```

This snippet is useful for building a lookup table during debugging. However, a `true` result does not replace **coordinate value** validation logic (for example, ByteBuffer alignment at a specific index). For memory-ordering modes, record the mode name alongside the method type to avoid confusing `GET` with `GET_VOLATILE`.

### 12.1. Using the formula to deduce signatures yourself

Suppose a `VarHandle` for `long[]`:

- `T = long`, `C = (long[], int)`.
- `GET`: `(long[],int)long`.
- `SET_RELEASE`: `(long[],int,long)void`.
- `COMPARE_AND_SET`: `(long[],int,long,long)boolean`.
- `COMPARE_AND_EXCHANGE_ACQUIRE`: `(long[],int,long,long)long`.
- `GET_AND_ADD_RELEASE`: `(long[],int,long)long`.
- `GET_AND_BITWISE_OR`: `(long[],int,long)long`.

Suppose a `VarHandle` for a static `String` field:

- `T = String`, `C = ()`.
- `GET_OPAQUE`: `()String`.
- `SET_VOLATILE`: `(String)void`.
- `COMPARE_AND_SET`: `(String,String)boolean`.
- `GET_AND_SET`: `(String)String`.
- `GET_AND_ADD`: **still has the shape** `(String)String`, but is normally **unsupported**. This is an example where `isAccessModeSupported` must also be used.

## 13. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| `varType()` is the class type containing the field | An `int` field of `Box` has variable type `int` | `Box` is the coordinate, `int` is the value. |
| A static field needs a receiver object | A static field belongs to the class and needs no instance coordinate | `coordinateTypes()` is an empty list. |
| A 2D array automatically has two int coordinates | Array-element VarHandle accesses **one element of the outer array** | `String[][]` gives variable `String[]` and coordinates `(String[][],int)`. |
| `accessModeType` tells whether a mode is usable | The type only describes the signature | Use `isAccessModeSupported` and check actual coordinate values. |
| `GET` and `GET_VOLATILE` have different MethodTypes | Same CT prefix, return T | Different memory semantics, not different signatures. |
| Compare-and-exchange returns boolean like CAS | The return type of exchange is `T` | Returns the witness, which can be compared against expected. |
| `getAndAdd` returns the new value | The get-and-update group returns the old value | The new value is stored in the variable. |
| A `String` field can use `getAndAdd` | Not a numeric type | The type exists, but the mode is unsupported. |
| `boolean` has no bitwise updates because it is not a number | Boolean supports bitwise on fields/array elements | Numeric add is unsupported. |
| `ByteBuffer` view index is the `int` element ordinal | View index is a byte offset | Check alignment and available bytes. |
| `List<String>` has its own varType | Generic type arguments are erased | `varType()` is raw `List.class`; use Reflection to read the declared generic signature. |
| Taking `toMethodHandle` requires passing `VarHandle` as an argument | The bound handle already holds vh | Only pass coordinates + value. |
| Looking at `Class.toString()` safely identifies all types | Class names do not encode generic arguments or runtime rules | Use `Class<?>` identity and actual `MethodType`. |

A subtle limitation: once a VarHandle is successfully created, **field access permissions** were already checked at creation time. A VarHandle is a *capability* that can be passed to other callers; if you distribute it, recipients can use it according to the supported access modes. Therefore, avoid exposing handles to private/sensitive mutable state to untrusted plugins.

## 14. Practice exercises and verification criteria

**Exercise 1 – Decomposing instance/static/array.** Create three handles for an `int` instance field, a `static long` field, and a `String[]` element. Write down `T`, `CT`, and deduce `GET`, `SET`, `COMPARE_AND_SET` yourself before printing `accessModeType`. Explain why a static field has no receiver.

**Exercise 2 – Complete mode table.** Use the `AccessMode.values()` helper in section 12 to print all modes for an `int` field; group equal method types. Why does `GET_ACQUIRE` have the same signature as `GET_VOLATILE`, yet cannot be substituted arbitrarily in a multithreaded protocol?

**Exercise 3 – Do not confuse with support.** Create a `final int x`, read `accessModeType(SET)`, then check `isAccessModeSupported(SET)`. State what you expect from `set` if called anyway. Repeat with `String[]` and `GET_AND_ADD`.

**Exercise 4 – Atomic return.** In Lab 2, before each call, write down the value of `count` and the expected output. Change the CAS expected value to be wrong, e.g., `compareAndSet(box,999,18)`; explain why the boolean is false and the variable is unchanged. Contrast with `compareAndExchange` since it returns a witness.

**Exercise 5 – Array index.** With `arrayElementVarHandle(long[].class)`, deduce the `getAndAdd` type `(long[],int,long)long`. Try accessing an out-of-bounds index and read the exception; separate signature errors from coordinate errors.

**Exercise 6 – Multidimensional array.** With `String[][]`, predict the variable type and coordinate list. Fetch a `String[]` at an outer index, then use another VarHandle to access a `String` element in the inner array. Why does the initial VarHandle not need `(String[][],int,int)String`?

**Exercise 7 – Byte views.** Compare `byteArrayViewVarHandle(int[].class, order)` with `arrayElementVarHandle(int[].class)`. Print `varType()` and `coordinateTypes()`; explain why they share the same T while having different coordinate containers, and why the view must handle byte order/alignment.

**Exercise 8 – Invoke-exact.** In Lab 2, replace `Object ignored = exact.get(box)` with `int value = (int) exact.get(box)` and compare the results. Explain the role of the return type at the call site. Do not remove `withInvokeExactBehavior` from the experiment because it determines the reason for failure.

**Exercise 9 – Multi-mode adapter.** Write a helper taking a `VarHandle` and a mode enum, returning a description containing `varType`, `coordinateTypes`, `accessModeType`, `isAccessModeSupported`. Each record must retain the mode name so as not to conflate memory semantics that share the same signature.

### Self-assessment checklist

- [ ] Distinguish between **T** (value type) and **CT** (coordinates to locate the variable).
- [ ] Deduce the MethodType for read/write/CAS/exchange/get-and-update without reversing parameter order.
- [ ] Explain why `getAndAdd` and `compareAndExchange` return the **pre-update value**, unlike boolean CAS.
- [ ] Know why the same signature does not mean the same memory ordering.
- [ ] Prove via lab that `accessModeType` exists even for unsupported modes.
- [ ] Run all four labs, verify stdout, and classify runtime errors by their true cause.
- [ ] Recognize multidimensional arrays, ByteBuffer byte-offsets, and type erasure of generic fields.

## 15. Official Java 21 reference documentation

- [Java SE 21 – VarHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html): `varType()`, `coordinateTypes()`, `accessModeType()`, `isAccessModeSupported()`, access mode methods, and memory semantics.
- [Java SE 21 – VarHandle.AccessMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html): enum names, `methodName()`, and modes available in the JDK.
- [Java SE 21 – MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `arrayElementVarHandle`, `byteArrayViewVarHandle`, `byteBufferViewVarHandle`, varHandle invokers.
- [Java SE 21 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle`, `findStaticVarHandle`, and access control.
- [Java SE 21 – MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): representation of return/parameter types.
- [Java SE 21 – WrongMethodTypeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): distinguishing signature errors from unsupported mode errors.

**Key takeaway:** `VarHandle` answers three independent yet tightly linked questions: **What type is the value?** (`varType`), **Where is the variable located?** (`coordinateTypes`), **What parameters and return type does this mode require?** (`accessModeType`). Only after checking that **the mode is supported** and **the actual coordinates are valid** do you have enough information to use the handle properly in an application.
