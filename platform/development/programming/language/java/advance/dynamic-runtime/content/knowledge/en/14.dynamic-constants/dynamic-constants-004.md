# 14.4. ConstantBootstraps for null, enum, static final, and VarHandle

## Learning Objectives

After this lesson, you can:

1. Understand **dynamic constants** (often called **condy**) in the JVM, the purpose of `CONSTANT_Dynamic_info`, and the role of the **bootstrap method** when linking a constant.
2. Distinguish between the **dynamic constant result** and the **bootstrap method used to compute the result**; understand why calling a regular `ConstantBootstraps` method does **not** automatically create a constant-pool entry.
3. Correctly use `java.lang.invoke.ConstantBootstraps.nullConstant` to represent a `null` constant with a **reference type**, and recognize the error when using a primitive type.
4. Use `enumConstant` to obtain the right enum element from a constant name and `Class<E>`.
5. Use both overloads of `getStaticFinal` to read the value of a `static final` field, distinguishing **field type**, **field declaring class**, and the case where the short overload can infer the declaring class.
6. Use `fieldVarHandle`, `staticFieldVarHandle`, and `arrayVarHandle` to link a `VarHandle` describing an instance field, static field, or array element.
7. Relate the bootstraps above to `java.lang.constant.ConstantDescs`, `DynamicConstantDesc`, and `resolveConstantDesc` (how to simulate resolution in Java code), without confusing it with an actual `ldc`.
8. Handle type mismatch, access, missing field/enum errors, the immutability of a dynamic constant's result, and the **mutability of the variable pointed to by a VarHandle**.

**Context:** In chapter **14. Dynamic Constants** of Java Advance – dynamic-runtime, Java 11 added the ability for a constant pool entry to receive a value computed by a **bootstrap method** when resolved. The JDK provides `ConstantBootstraps` out of the box so you do not have to write your own bootstrap for common scenarios: typed `null`, enum constant, `static final` field, and `VarHandle`.

## 1. What is a dynamic constant in the JVM?

At the class file level, `CONSTANT_Dynamic_info` records a **symbolic reference** to a constant whose value will be computed during **resolution**, instead of storing that entire value as an ordinary literal in the class file.

A dynamic constant descriptor essentially needs:

- **Constant name** (*name*): the name string passed to the bootstrap, which may carry domain meaning (enum name, field name) or be unused.
- **Constant type** (*type*): a JVM-level field descriptor, converted to a `Class<?>` object when the bootstrap runs.
- **Bootstrap method handle**: points to the method invoked by the JVM to compute the value.
- **Static bootstrap arguments**: additional data, if needed by the bootstrap (e.g., the `Class` of the field's declaring class and the `Class` of the field's type).
- **Lookup context**: the JVM provides a `MethodHandles.Lookup` reflecting the resolution context and access permissions of the class owning the reference.

Conceptual view:

```text
Class file:
  CONSTANT_Dynamic_info {
      name: "FAST"
      type: Lcom/example/Mode;
      bootstrap: ConstantBootstraps.enumConstant
      staticArgs: []
  }

When the symbol is resolved:
  JVM creates Lookup + name + type + staticArgs
      -> invokes bootstrap method
      -> checks that the result matches the constant type
      -> publishes the resolved value for subsequent uses
```

The example above is only a **diagram**, not Java syntax or an exact dump of a class file. In actual bytecode, the entry also references the `BootstrapMethods` attribute and indices in the constant pool. `ldc`, `ldc_w`, or `ldc2_w` can request the resolution of a dynamic constant.

### 1.1. `CONSTANT_Dynamic_info` vs. `CONSTANT_InvokeDynamic_info`

| Aspect | Dynamic constant (`condy`) | Dynamic call site (`invokedynamic`) |
| --- | --- | --- |
| Data produced by bootstrap | **Constant value** matching the field type | **`CallSite`** with a matching `MethodType` |
| Descriptor type in entry | **Field descriptor** such as `Ljava/lang/String;`, `I`, `Ljava/lang/invoke/VarHandle;` | **Method descriptor** such as `(Ljava/lang/Object;)Ljava/lang/String;` |
| Typical scenarios | `null` constant, enum, `static final` field, variable access handle | Linking a dynamic call |
| Usage in bytecode | Usually from `ldc` or as a bootstrap argument | From `invokedynamic` |
| Must bootstrap return `CallSite`? | **No**; returns the constant's value | **Yes** |

Do not confuse `ConstantBootstraps.` with `LambdaMetafactory` or bootstraps that return `CallSite`: `ConstantBootstraps` focuses on **dynamic constants**, not creating a new call site by default.

### 1.2. When does the bootstrap run? Is it cached?

When a symbolic reference to a dynamic constant **is successfully resolved**, subsequent resolutions of **that same reference in the run-time constant pool** use the same value without invoking the bootstrap again. If resolution fails, the JVM records the failure result according to resolution error rules.

However, keep two limitations in mind:

1. **Concurrent bootstrap invocations may occur.** If multiple threads attempt to resolve an unlinked reference simultaneously, the JVM may run the bootstrap concurrently more than once, then choose one result to publish; do not write a bootstrap with side effects and assume it will definitely run only once under every interleaving.
2. **JVM caching applies to symbol resolution in the constant pool, not to every ordinary Java call.** If code explicitly calls `ConstantBootstraps.getStaticFinal(...)` twice, those are two normal method calls. If code calls `DynamicConstantDesc.resolveConstantDesc(...)` twice, this API **does not cache** the simulated resolution result.

Also, do not interpret "resolved constant" as meaning every object the constant points to is immutable. A constant can be a reference to a `VarHandle` or a mutable object; the **reference** may be fixed in the pool, while the **state of the target object/variable** still changes.

## 2. General signature of standard bootstraps

`ConstantBootstraps` is a `final` class containing **static methods**. In general, the first three parameters of a dynamic constant bootstrap mean:

```text
(MethodHandles.Lookup lookup, String name, Class<?> type, ...staticArgs)
```

Where:
- `lookup`: the context of the class performing linkage, used when the bootstrap needs to check permissions.
- `name`: the name of the constant-pool entry; e.g., enum/field name.
- `type`: **the type of the constant value to produce**, *not* the type of the class containing the bootstrap.
- `...staticArgs`: method-specific data, e.g., `declaringClass`, `fieldType`, `arrayClass`.

Different bootstraps **do not use every parameter**. `nullConstant` does not use `lookup`/`name`; `arrayVarHandle` does not use `name`, whereas `enumConstant` and `getStaticFinal` require a meaningful name.

### 2.1. Main API table for this lesson

| Bootstrap | Meaning | Information determining the result |
| --- | --- | --- |
| `nullConstant(lookup, name, type)` | A `null` constant of a **reference type** | `type` is a reference type |
| `enumConstant(lookup, name, type)` | Obtain an enum constant | Exact `name` and `type` is an enum class |
| `getStaticFinal(lookup, name, type, declaringClass)` | Value of a `static final` field | Name, field type, declaring class, and access permissions |
| `getStaticFinal(lookup, name, type)` | Short variant | Infers declaring class from `type`, or wrapper class if the field is primitive |
| `fieldVarHandle(lookup, name, VarHandle.class, declaringClass, fieldType)` | Handle to an instance field | Field name, owner, field type, and permissions |
| `staticFieldVarHandle(lookup, name, VarHandle.class, declaringClass, fieldType)` | Handle to a static field | Field name, owner, field type, and permissions |
| `arrayVarHandle(lookup, name, VarHandle.class, arrayClass)` | Handle to an array element | `arrayClass`, component type, and permissions |

`ConstantBootstraps` also has `primitiveClass`, `explicitCast`, and `invoke`; those are other supporting bootstraps and are not the focus of this lesson.

## 3. `nullConstant` — typed null constant

Signature:

```java
public static Object nullConstant(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type)
```

This is an **illustrative signature** of an API that already exists in the JDK, not code you need to declare yourself.

The method returns `null` if `type` is a **reference type**, for example:
- `String.class`;
- `Object.class`;
- `Integer.class`;
- `int[].class` (arrays are also reference types).

Direct usage example:

```java
Object result = ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "unused", String.class);
System.out.println(result == null); // true
```

This is a small example placed inside a method that imports `ConstantBootstraps` and `MethodHandles`. The result is the **null value**, not a newly created `String` object. When a dynamic constant has field descriptor `Ljava/lang/String;`, the null bootstrap can provide the exact constant value for that reference type.

### 3.1. Why are primitive types invalid?

`null` cannot represent `int`, `long`, `boolean`, or `void`. Therefore:

```java
ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "unused", int.class);
```

This call throws **`IllegalArgumentException`**, rather than returning `0` or a boxed `Integer` value. `void.class` also does not produce a valid null constant.

Do not confuse it with `Void.class`: that is a **reference class**, so `nullConstant(..., Void.class)` can return `null`, whereas `void.class` is not a reference type.

### 3.2. When is it useful?

A source language running on the JVM may need a constant carrying a **specific reference type** in the constant pool whose value is `null`. The `nullConstant` bootstrap provides a standardized way to do this at the JVM level. In ordinary Java code, you do not need `ConstantBootstraps` just to assign `String s = null;`; the learning value lies in the **dynamic constant linkage mechanism**.

## 4. `enumConstant` — linking an enum element by name

General signature:

```java
public static <E extends Enum<E>> E enumConstant(
        MethodHandles.Lookup lookup, String name, Class<E> type)
```

Here:
- `name` must match the exact **enum constant name**, case-sensitive;
- `type` must be the `Class<E>` of an **actual enum**, not the generic `Enum.class` or a class name as a string;
- `lookup` determines access permissions during linkage.

Example:

```java
enum Mode { FAST, SLOW }

Mode mode = ConstantBootstraps.enumConstant(
        MethodHandles.lookup(), "FAST", Mode.class);
System.out.println(mode); // FAST
```

This is a **non-standalone illustrative snippet**; the `enum` declaration needs to be placed in a valid Java context, such as inside the class in the complete program section. The result is the **actual enum singleton `Mode.FAST`**, not a `new Mode(...)` instance.

### 4.1. Typical errors

| Input | Result |
| --- | --- |
| `name = "FAST"`, `type = Mode.class` | Returns `Mode.FAST` |
| `name = "fast"` | `IllegalArgumentException` if the enum has no constant with that exact name |
| `name = "MISSING"` | `IllegalArgumentException` |
| `type` is not an enum class | `IllegalArgumentException` (for calls that can bypass compile-time generic checks) |
| Enum or field is not accessible by lookup | May throw `IllegalAccessError` |

Semantically, it is related to `Enum.valueOf(type, name)`, but it **should not be mechanically replaced** by a `valueOf` call: the bootstrap uses the proper access context and JVM linkage contract.

### 4.2. Why does the constant name matter?

`enumConstant` reads the **name of the dynamic constant** to decide which enum constant will be selected. If a bytecode generator sets the wrong name, the bootstrap **does not guess** aliases or fall back to a default enum constant. When building a DSL/runtime compiler, you should validate the catalog of enum names before emitting bytecode, while still handling linkage failures if the enum library changes after build time.

## 5. `getStaticFinal` — getting the value of a static final field

There are **two overloads**:

```java
Object getStaticFinal(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        Class<?> declaringClass);

Object getStaticFinal(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type);
```

The signatures above are written for **reference**, not to be implemented yourself.

### 5.1. Four-parameter overload: explicitly specifying the owner

Example class:

```java
static final class Settings {
    static final String LABEL = "ready";
    static final int LIMIT = 17;
}
```

This is an illustrative nested class. `Settings` needs to be located where `lookup` has access rights.

Usage:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

Object label = ConstantBootstraps.getStaticFinal(
        lookup, "LABEL", String.class, Settings.class);
Object limit = ConstantBootstraps.getStaticFinal(
        lookup, "LIMIT", int.class, Settings.class);
```

Note:
- `"LABEL"` or `"LIMIT"` is the **field name**, not the class name.
- `String.class` and `int.class` are the **actual types of the fields**, not `Object.class` just because the bootstrap method is declared to return `Object`.
- `Settings.class` is the **class declaring the field**.
- An `int` value passing through an API with return type `Object` will appear as a boxed value, such as `Integer.valueOf(17)`, when called directly from Java.

### 5.2. Three-parameter overload: owner inferred from type

```java
Object zero = ConstantBootstraps.getStaticFinal(
        MethodHandles.lookup(), "ZERO", java.math.BigInteger.class);
```

`BigInteger.ZERO` is a static final field of type `BigInteger` and is declared in `BigInteger` itself. Therefore, the short overload infers the owner as `BigInteger.class`.

For **primitive** fields, the short overload infers the owner as the **wrapper class** of that primitive; for example, `int.class` infers the owner as `Integer.class` (so appropriate fields like `Integer.MAX_VALUE` can be used).

**Do not misunderstand:** `getStaticFinal(lookup,"LABEL",String.class)` does **not** search the entire classpath for a `LABEL` field of type String. It only looks at the class associated with `type`; since `LABEL` is in `Settings`, you must use the **four-parameter** overload to specify the owner explicitly.

### 5.3. Field conditions and linkage errors

| Scenario | Typical result |
| --- | --- |
| Field exists, has the right type, is `static final`, and access is valid | Returns the field value |
| Field name does not exist or cannot be resolved with the requested type | `NoSuchFieldError` |
| Field has matching name/type but is **not final** | `IncompatibleClassChangeError` |
| Owner/field is not accessible with `lookup` | `IllegalAccessError` |
| Class initialization fails along the access path | May encounter an initialization-related error, such as `ExceptionInInitializerError` |

At the `ConstantBootstraps` API level, these errors can be **`Error`s belonging to linkage**, and should not be caught and retried by default like a network error. If used in **dynamic constant resolution**, the JVM may record the failure result for that symbolic reference; fixing runtime state afterward does not guarantee that a failed reference will automatically re-resolve.

### 5.4. `static final` does not mean an immutable object

For example, `static final List<String> ITEMS = new ArrayList<>();`: the field reference is `final`, but the `ArrayList` object is still mutable. If that value is placed into a dynamic constant, a **constant reference** does not mean the list is frozen. Furthermore, the Java compiler may inline `static final` compile-time constants in ordinary Java source; linking via `getStaticFinal` is a different path, so do not confuse it with direct source-level constant inlining.

## 6. The trio of VarHandle bootstraps

`VarHandle` is an API for accessing a variable by **coordinates** and **access mode**. `ConstantBootstraps` has three methods that produce constants returning a **VarHandle**, rather than returning the value currently stored in the variable.

### 6.1. `fieldVarHandle` — instance field

Signature:

```java
VarHandle fieldVarHandle(
        MethodHandles.Lookup lookup,
        String name,
        Class<VarHandle> type,
        Class<?> declaringClass,
        Class<?> fieldType);
```

Meaning:
- `name`: instance field name (e.g., `"count"`).
- `type`: **the type of the resulting dynamic constant**, which must be `VarHandle.class`.
- `declaringClass`: the class where the field is declared.
- `fieldType`: the actual type of the variable (e.g., `int.class`).

With:

```java
static final class Counter {
    volatile int count;
}

VarHandle vh = ConstantBootstraps.fieldVarHandle(
        MethodHandles.lookup(), "count",
        VarHandle.class, Counter.class, int.class);

Counter c = new Counter();
vh.setVolatile(c, 3);
int current = (int) vh.getVolatile(c);
```

This is an **illustrative snippet**; the class declaration and statements must be placed in a valid Java context. Because it is an instance field, access modes like `getVolatile`, `setVolatile`, or `compareAndSet` require a `Counter` **receiver** as the first coordinate. You cannot call `vh.getVolatile()` without passing a receiver.

### 6.2. `staticFieldVarHandle` — static field

Signature:

```java
VarHandle staticFieldVarHandle(
        MethodHandles.Lookup lookup,
        String name,
        Class<VarHandle> type,
        Class<?> declaringClass,
        Class<?> fieldType);
```

With `static volatile long total;` in class `Counter`:

```java
VarHandle totalVH = ConstantBootstraps.staticFieldVarHandle(
        MethodHandles.lookup(), "total",
        VarHandle.class, Counter.class, long.class);
totalVH.setVolatile(9L);
long total = (long) totalVH.getVolatile();
```

This is an illustrative snippet, assuming `Counter` has an appropriate static field `total`. Because it is a **static field**, no receiver is needed; the coordinate list is empty. An incorrect number/type of arguments when calling a `VarHandle` access mode may throw `WrongMethodTypeException`.

### 6.3. `arrayVarHandle` — array element

Signature:

```java
VarHandle arrayVarHandle(
        MethodHandles.Lookup lookup,
        String name,
        Class<VarHandle> type,
        Class<?> arrayClass);
```

Here `name` is **not used** to select an index or field. `arrayClass` must describe an array class such as `int[].class` or `String[].class`.

```java
VarHandle element = ConstantBootstraps.arrayVarHandle(
        MethodHandles.lookup(), "unused", VarHandle.class, int[].class);
int[] numbers = {2, 3};
element.setVolatile(numbers, 1, 8);
int value = (int) element.getVolatile(numbers, 1);
```

This is an illustrative snippet, run inside a method that has imported the necessary APIs. The coordinates of an array element are:
1. a reference to the **array**;
2. the **index**;
3. followed by the new value if setting/CASing.

`arrayVarHandle` describes the **element access rule** rather than fixing a single array object or a single index. The same VarHandle can be used for different instances of `int[]`.

### 6.4. Comparing the three handle types

| Variable type | Field/array example | Access mode coordinates | How to call `getVolatile` |
| --- | --- | --- | --- |
| Instance field | `Counter.count` | `(Counter receiver)` | `(int) vh.getVolatile(counter)` |
| Static field | `Counter.total` | No receiver coordinate | `(long) vh.getVolatile()` |
| Array element | `int[]` | `(int[] array, int index)` | `(int) vh.getVolatile(array, i)` |

**Distinguishing `VarHandle.class` and `fieldType`:** The `type` argument in all three bootstraps is `VarHandle.class` because **the produced constant value is a VarHandle**. The `fieldType` argument only appears in field/static field bootstraps to specify **the type of the variable being accessed**. Do not mistakenly pass `int.class` as `type`.

### 6.5. Can a VarHandle be linked to a final field?

You can obtain a VarHandle capable of **reading** a final field, but **write** modes (and some update modes) are not supported for final fields. `VarHandle.isAccessModeSupported(...)` helps check this. Calling an unsupported access mode may throw `UnsupportedOperationException`.

Having a bootstrap produce a VarHandle **does not grant permission to bypass finality or the Java Memory Model**. If you need the value of a `static final` field as a constant, `getStaticFinal` usually expresses the intent more clearly; if you need an **access handle**, use a VarHandle bootstrap while still obeying the field's semantics.

## 7. From direct bootstraps to describing dynamic constants with `DynamicConstantDesc`

Java 17 has the `java.lang.constant` package providing an API for **describing constants** at a nominal level, useful for class file analysis/generation tools.

Key classes/entities:
- `ClassDesc`: describes a class type in the constant pool.
- `ConstantDescs`: contains prebuilt descriptors for bootstraps, such as `BSM_NULL_CONSTANT`, `BSM_ENUM_CONSTANT`, `BSM_GET_STATIC_FINAL`, `BSM_VARHANDLE_FIELD`, `BSM_VARHANDLE_STATIC_FIELD`, `BSM_VARHANDLE_ARRAY`.
- `DynamicConstantDesc<?>`: describes the **bootstrap method + name + constant type + static arguments** of a dynamic constant.
- `resolveConstantDesc(lookup)`: **simulates resolution using reflection** in the provided context; **does not cache** the result like a symbolic reference in the JVM run-time constant pool.

### 7.1. Describing a null constant

```java
DynamicConstantDesc<?> desc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_NULL_CONSTANT,
        ConstantDescs.DEFAULT_NAME,
        ConstantDescs.CD_String);

Object value = desc.resolveConstantDesc(MethodHandles.lookup());
// value == null
```

This is an illustrative snippet requiring imports for `DynamicConstantDesc`, `ConstantDescs`, `MethodHandles`, and handling the checked exception from `resolveConstantDesc`. `DEFAULT_NAME` is appropriate because `nullConstant` **does not use name**.

### 7.2. Describing an enum constant

```java
DynamicConstantDesc<?> enumDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_ENUM_CONSTANT,
        "MONDAY",
        ClassDesc.of("java.time.DayOfWeek"));

Object monday = enumDesc.resolveConstantDesc(MethodHandles.lookup());
// monday == java.time.DayOfWeek.MONDAY
```

`name` is `"MONDAY"`, while `constantType` is described by a `ClassDesc` pointing to the enum class. The descriptor does not need any static arg for the `enumConstant` bootstrap.

### 7.3. Describing a static final field: **mandatory owner static arg**

```java
DynamicConstantDesc<?> finalDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_GET_STATIC_FINAL,
        "ZERO",
        ClassDesc.of("java.math.BigInteger"),
        ClassDesc.of("java.math.BigInteger"));

Object zero = finalDesc.resolveConstantDesc(MethodHandles.lookup());
// zero == BigInteger.ZERO (compared by identity in this case)
```

Here the **first ClassDesc** is the **type of the constant** (`BigInteger`). The **second ClassDesc** is the **static bootstrap argument describing the owner** (`BigInteger`). Both are required.

**Very common pitfall:** `ConstantBootstraps.getStaticFinal(lookup, name, type)` **has a direct three-parameter overload**, but the prebuilt descriptor `ConstantDescs.BSM_GET_STATIC_FINAL` describes the **overload with declaringClass**. When using `DynamicConstantDesc.ofNamed` with this descriptor, **you must not omit the owner static arg**; if missing, resolution fails because the bootstrap method handle receives the wrong number of arguments, commonly seen as `BootstrapMethodError`.

### 7.4. Describing an array VarHandle

```java
DynamicConstantDesc<?> arrayDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_VARHANDLE_ARRAY,
        ConstantDescs.DEFAULT_NAME,
        ConstantDescs.CD_VarHandle,
        ConstantDescs.CD_int.arrayType());

VarHandle element = (VarHandle)
        arrayDesc.resolveConstantDesc(MethodHandles.lookup());
```

Here:
- `CD_VarHandle` is the **type of the constant result**;
- `CD_int.arrayType()` is the **array class `int[]` static arg**;
- the `arrayVarHandle` bootstrap ignores name.

### 7.5. Describing an instance-field VarHandle

```java
DynamicConstantDesc<?> fieldDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_VARHANDLE_FIELD,
        "count",
        ConstantDescs.CD_VarHandle,
        ClassDesc.of("ConstantBootstrapsGuide$State"),
        ConstantDescs.CD_int);
```

This is an illustrative snippet for the nested class `State` in the program below. The order of static arguments is **declaring class** then **field type**. `ClassDesc.of("ConstantBootstrapsGuide$State")` describes the **binary name** of the nested class; the `$` character here is part of the binary name, not Java syntax for member access.

In systems with complex modules and class loaders, the descriptor must be resolved in an appropriate `Lookup`. Classes with the same string name loaded by two different class loaders do not have the same `Class` identity.

### 7.6. A descriptor is not bytecode `ldc`

The four `DynamicConstantDesc` examples above **do not automatically create a `CONSTANT_Dynamic_info` in the class file** of the demo program. Calling `resolveConstantDesc` computes the value via a reflection-based API for testing or tooling. To have an actual dynamic constant loaded via `ldc`, the class file must contain a **properly structured constant-pool entry** with `BootstrapMethods` and an appropriate instruction/usage path; only a bytecode generation library or class-file tooling can emit that structure.

**Important difference:** The JVM caches resolution per symbolic reference; `DynamicConstantDesc.resolveConstantDesc` explicitly documents that it **does not cache** the returned value. If you use the simulation API to benchmark "condy cached at runtime", the result will measure the wrong thing.

## 8. Complete, verified Java 17+ program

The following program demonstrates all four feature families: `nullConstant`, `enumConstant`, `getStaticFinal`, the three VarHandle bootstraps, and the corresponding **nominal descriptors**. Error cases are also included to show the contract.

Save the file **`ConstantBootstrapsGuide.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.math.BigInteger;

public class ConstantBootstrapsGuide {
    enum Mode { FAST, SLOW }

    static final class State {
        static final String LABEL = "ready";
        static final int LIMIT = 17;
        static int editable = 5;
        static volatile long global;
        volatile int count;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Object nil = ConstantBootstraps.nullConstant(lookup, "unused", String.class);
        System.out.println("null=" + (nil == null));
        try {
            ConstantBootstraps.nullConstant(lookup, "unused", int.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("nullPrimitive=" + expected.getClass().getSimpleName());
        }

        Mode enumValue = ConstantBootstraps.enumConstant(lookup, "FAST", Mode.class);
        System.out.println("enum=" + enumValue);
        try {
            ConstantBootstraps.enumConstant(lookup, "MISSING", Mode.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("enumMissing=" + expected.getClass().getSimpleName());
        }

        Object label = ConstantBootstraps.getStaticFinal(
                lookup, "LABEL", String.class, State.class);
        Object limit = ConstantBootstraps.getStaticFinal(
                lookup, "LIMIT", int.class, State.class);
        Object zero = ConstantBootstraps.getStaticFinal(
                lookup, "ZERO", BigInteger.class);
        System.out.println("staticLabel=" + label);
        System.out.println("staticLimit=" + limit);
        System.out.println("shortFinal=" + zero);

        try {
            ConstantBootstraps.getStaticFinal(
                    lookup, "editable", int.class, State.class);
        } catch (IncompatibleClassChangeError expected) {
            System.out.println("nonFinal=" + expected.getClass().getSimpleName());
        }

        State state = new State();
        VarHandle field = ConstantBootstraps.fieldVarHandle(
                lookup, "count", VarHandle.class, State.class, int.class);
        field.setVolatile(state, 4);
        boolean changed = field.compareAndSet(state, 4, 5);
        System.out.println("instanceCAS=" + changed);
        System.out.println("instance=" + (int) field.getVolatile(state));

        VarHandle stat = ConstantBootstraps.staticFieldVarHandle(
                lookup, "global", VarHandle.class, State.class, long.class);
        stat.setVolatile(9L);
        System.out.println("staticVar=" + (long) stat.getVolatile());

        VarHandle array = ConstantBootstraps.arrayVarHandle(
                lookup, "unused", VarHandle.class, int[].class);
        int[] numbers = {2, 3};
        array.setVolatile(numbers, 1, 8);
        System.out.println("array=" + (int) array.getVolatile(numbers, 1));

        DynamicConstantDesc<?> nullDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_NULL_CONSTANT,
                ConstantDescs.DEFAULT_NAME,
                ConstantDescs.CD_String);
        System.out.println("descNull=" + (nullDesc.resolveConstantDesc(lookup) == null));

        DynamicConstantDesc<?> enumDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_ENUM_CONSTANT,
                "MONDAY",
                ClassDesc.of("java.time.DayOfWeek"));
        System.out.println("descEnum=" + enumDesc.resolveConstantDesc(lookup));

        DynamicConstantDesc<?> finalDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_GET_STATIC_FINAL,
                "ZERO",
                ClassDesc.of("java.math.BigInteger"),
                ClassDesc.of("java.math.BigInteger"));
        System.out.println("descFinal=" + finalDesc.resolveConstantDesc(lookup));

        DynamicConstantDesc<?> arrayDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_VARHANDLE_ARRAY,
                ConstantDescs.DEFAULT_NAME,
                ConstantDescs.CD_VarHandle,
                ConstantDescs.CD_int.arrayType());
        VarHandle descArrayVH = (VarHandle) arrayDesc.resolveConstantDesc(lookup);
        System.out.println("descArray=" + (int) descArrayVH.getVolatile(numbers, 1));

        DynamicConstantDesc<?> fieldDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_VARHANDLE_FIELD,
                "count",
                ConstantDescs.CD_VarHandle,
                ClassDesc.of("ConstantBootstrapsGuide$State"),
                ConstantDescs.CD_int);
        VarHandle descFieldVH = (VarHandle) fieldDesc.resolveConstantDesc(lookup);
        System.out.println("descField=" + (int) descFieldVH.getVolatile(state));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 ConstantBootstrapsGuide.java
java ConstantBootstrapsGuide
```

**Verified stdout on a Java 17-compatible runtime:**

```text
null=true
nullPrimitive=IllegalArgumentException
enum=FAST
enumMissing=IllegalArgumentException
staticLabel=ready
staticLimit=17
shortFinal=0
nonFinal=IncompatibleClassChangeError
instanceCAS=true
instance=5
staticVar=9
array=8
descNull=true
descEnum=MONDAY
descFinal=0
descArray=8
descField=5
```

### 8.1. Explaining the null/enum group

- `null=true` proves the bootstrap returns a `null` reference for `String.class`.
- `nullPrimitive=IllegalArgumentException` proves primitive `int.class` is not an allowed type.
- `enum=FAST` is the enum value selected by **exact name**.
- `enumMissing=IllegalArgumentException` demonstrates there is no element named `MISSING`; the bootstrap does not pick a default automatically.

### 8.2. Explaining the static final group

- `staticLabel=ready` comes from `State.LABEL` via the overload with an explicit owner.
- `staticLimit=17` comes from the `int LIMIT` field; the bootstrap method returns `Object`, so the result is boxed when returned through the Java API.
- `shortFinal=0` uses the **three-parameter** overload to get `BigInteger.ZERO`, because the owner and field type are both `BigInteger`.
- `nonFinal=IncompatibleClassChangeError` shows that the `editable` field is not `final`. The program intentionally catches this `Error` type **only for demonstration**, not as advice to swallow linkage errors in production applications.

### 8.3. Explaining the VarHandle group

- `instanceCAS=true`: the VarHandle for instance field `count` performs a CAS from `4` to `5`.
- `instance=5`: the same handle reads the new value via the `state` receiver.
- `staticVar=9`: the VarHandle for static field `global` **requires no receiver**.
- `array=8`: the array VarHandle writes the second element of `int[]`; requires array and index.

These operations update **the variable pointed to by the VarHandle**, rather than changing the dynamic constant's value once a VarHandle has been linked as a constant. The constant holds the handle object; the handle can still perform accesses on changing state.

### 8.4. Explaining the DynamicConstantDesc group

- `descNull=true`: `BSM_NULL_CONSTANT` simulates resolution and returns `null`.
- `descEnum=MONDAY`: `BSM_ENUM_CONSTANT` uses the name and enum class descriptor.
- `descFinal=0`: `BSM_GET_STATIC_FINAL` takes the **owner ClassDesc as a static arg** as required.
- `descArray=8`: the array VarHandle descriptor is resolved to a VarHandle, then reads the updated array.
- `descField=5`: the field VarHandle descriptor is resolved, then reads the `count` instance field of `state`.

**Note on exception declaration:** `main throws ReflectiveOperationException` is only to keep the example focused on resolution. In real tools, you should properly handle access/lookup/descriptor errors and `LinkageError`, instead of treating them all as ordinary data errors.

## 9. Why are "the constant value" and "the variable pointed to by a VarHandle" very different?

A dynamic constant can resolve to:

1. `null` for a reference type.
2. An **enum singleton**.
3. The **current value** taken from a `static final` field at resolution time.
4. A `VarHandle` object representing a **variable access rule**.

Case (4) is completely different from (3):

```text
CONSTANT_Dynamic -> bootstrap fieldVarHandle
                 -> VarHandle object (treated as the constant value)
                 -> accesses current Counter.count via receiver
                 -> count value can change over time
```

Just because a VarHandle is provided via the constant pool does not turn the field into `final` or freeze the variable. With a `VarHandle` to `volatile int count`, each `getVolatile(receiver)` call still performs a volatile access according to the `VarHandle` contract. The constant pool caches the `VarHandle` object, not the result of each `getVolatile` call.

Conversely, a dynamic constant resolving to the **value** of a `static final` field does not become a "live observer" of the field. This is especially easy to confuse when tests mutate state using non-standard techniques; Java does not promise that `static final` fields can be arbitrarily modified after initialization.

## 10. Access permissions and errors when bootstraps run

### 10.1. `Lookup` is a security context, not a wildcard

`MethodHandles.Lookup` represents the permissions of the calling class in the appropriate context. Bootstraps operating on fields/enums must still obey access checks, class loader identity, and module boundaries.

In the full example, `State` and `Mode` are nested types inside `ConstantBootstrapsGuide`, and `MethodHandles.lookup()` is created in the outer class. They belong to the same **nest** in modern Java, allowing the example to access the fields properly. If you replace `State` with a class in another module that does not export the package or does not grant access, resolution may fail.

Do not use `privateLookupIn`, `setAccessible(true)`, or a full-power lookup as a general "security bypass" solution. Only construct a lookup with the permissions permitted by the contract. A malicious class file must not be able to use a bootstrap to read private fields of a class that has not granted access.

### 10.2. Common errors

| API or phase | Invalid example | Important error type |
| --- | --- | --- |
| `nullConstant` | `type=int.class` or `void.class` | `IllegalArgumentException` |
| `enumConstant` | Non-existent enum name or non-enum type | `IllegalArgumentException` |
| `getStaticFinal` | Wrong name/field signature | `NoSuchFieldError` |
| `getStaticFinal` | Field has a value but is not `final` | `IncompatibleClassChangeError` |
| `getStaticFinal` / field bootstrap | Missing access to owner/field | `IllegalAccessError` |
| `fieldVarHandle` | Mismatched field name/type | `NoSuchFieldError` |
| `staticFieldVarHandle` | Cannot resolve matching static field | `NoSuchFieldError` or appropriate linkage error |
| `arrayVarHandle` | Passing a non-array class | Invalid input error, usually `IllegalArgumentException` |
| One of the three VarHandle bootstraps | `type` is not `VarHandle.class` | `IllegalArgumentException` |
| Calling a VarHandle access mode | Wrong number/type of coordinates or value | Usually `WrongMethodTypeException` |
| Calling an unsupported access mode | Attempting to set a final field | `UnsupportedOperationException` |
| `DynamicConstantDesc.resolveConstantDesc` | Missing required bootstrap argument | May throw `BootstrapMethodError`/`WrongMethodTypeException` depending on resolution path |
| Actual JVM condy resolution | Bootstrap throws a checked/unchecked exception other than `Error` | `BootstrapMethodError` wrapping the cause |
| Actual JVM condy resolution | Bootstrap itself throws an `Error` | The JVM may propagate that `Error` directly per the specification |

**Distinguishing the two error groups:**
- **Direct Java call** to `ConstantBootstraps`: the caller receives errors according to the **method's direct contract**.
- **JVM resolution of a dynamic constant**: the JVM applies additional **`CONSTANT_Dynamic_info` linkage/validation rules**; non-`Error` exceptions from invoking the bootstrap are wrapped in `BootstrapMethodError`, and result type errors may become `BootstrapMethodError`.

Do not try to "retry forever" on a failed symbolic reference because the JVM may cache the resolution failure result. If the error is due to configuration/deployment, fix the cause and redeploy the appropriate class/version rather than expecting the constant pool to re-link itself.

### 10.3. Bootstrap result must match the constant type

If a dynamic constant declares field type `String`, the bootstrap must produce a `String`-compatible reference value or `null`. If the type is `int`, the bootstrap result must be converted according to JVM rules to `int`; `null` is not a valid result and can cause `BootstrapMethodError` during validation.

Do not just look at the declared `Object` return type of `getStaticFinal` and conclude the constant always has type `Object`: the actual constant type is dictated by the **descriptor**. The bootstrap is merely the code that computes the value; the JVM must validate the result.

## 11. Safe condy design workflow in bytecode/runtime tools

A class file generation tool can follow this workflow:

1. **Choose the right goal:** do you want a **constant value** or a **handle to access a variable**? If you need to access a changing field, choose a VarHandle bootstrap.
2. **Choose a standard bootstrap:** null/enum/static-final/field/static-field/array, instead of creating unnecessary custom bootstraps.
3. **Determine constant name and field descriptor:** `enumConstant`/field bootstraps require exact names; `nullConstant`/`arrayVarHandle` do not use name.
4. **Determine static args:** for `BSM_GET_STATIC_FINAL` and `BSM_VARHANDLE_FIELD`, pass the **owner class** and type descriptors in the right order.
5. **Validate class loader and access:** each owner/component type must be resolvable and have valid permissions.
6. **Check return type:** the value computed by the bootstrap must match the field descriptor; specifically, VarHandle bootstraps have constant type `VarHandle`.
7. **Do not place non-idempotent side effects in bootstraps:** concurrent resolution may invoke the bootstrap more than once before the JVM selects one result.
8. **Test directly and via simulation:** test the `ConstantBootstraps` API and `DynamicConstantDesc.resolveConstantDesc` on the target JDK to catch args/type errors.
9. **Test with real class files:** if an actual generator emits `CONSTANT_Dynamic_info`, use a class file inspection tool and an integration test that **executes `ldc`** to verify linkage and caching.
10. **Observe errors at the right layer:** log the constant name, descriptor, owner, bootstrap method, static args, and cause; do not "guess" an error is an application exception when it is actually a linkage failure.

### 11.1. Why are two kinds of tests needed?

A test calling `getStaticFinal(...)` directly helps confirm that the name/type/owner are valid. However, it **does not verify**:
- that the class file contains `CONSTANT_Dynamic_info` and `BootstrapMethods` with the right index;
- that the compiler/generator wrote the right field descriptor;
- that the JVM handles resolution caching/failure caching;
- that bytecode `ldc` actually references the right symbolic reference.

Therefore, for a class file generation project, you need both bootstrap API unit tests and classfile/JVM resolution integration tests. The pure Java example in section 8 intentionally **does not claim** it emitted an actual condy.

### 11.2. Choosing between equivalent APIs

| Need | Reasonable API |
| --- | --- |
| Using `null` in ordinary Java code | `null` literal, no bootstrap needed |
| Getting an enum constant from a string in application logic | `Enum.valueOf(...)` if appropriate |
| Reading a `static final` field in Java source | Ordinary field access with appropriate permissions |
| Creating a `VarHandle` in runtime code | `MethodHandles.Lookup.findVarHandle/findStaticVarHandle` or `arrayElementVarHandle` |
| Describing condy in tooling | `ConstantDescs` + `DynamicConstantDesc` |
| Bootstrapping a `CONSTANT_Dynamic_info` in a class file | Standard `ConstantBootstraps` with the right descriptors/static args |

Direct APIs like `Lookup.findVarHandle` may report **`NoSuchFieldException` / `IllegalAccessException`** at lookup time, whereas `ConstantBootstraps.fieldVarHandle` has a **linkage errors** contract such as `NoSuchFieldError` / `IllegalAccessError`. Choose the API based on context, and do not assume they share the same default exception hierarchy.

## 12. Common misconceptions

1. **"Calling `ConstantBootstraps.nullConstant` in Java means you have used `CONSTANT_Dynamic_info`."** False. That may just be an ordinary method call.
2. **"`DynamicConstantDesc.resolveConstantDesc` caches automatically like JVM condy."** False. This method simulates resolution **without caching**.
3. **"Each condy's bootstrap is guaranteed to run only once under any race."** Not necessarily; the JVM may allow multiple threads to run the bootstrap concurrently before selecting a result.
4. **"A null constant can use `int.class` and be turned into 0."** False. `nullConstant` only accepts reference types.
5. **"`enumConstant` ignores name because Enum.class is already known."** False. `name` determines the enum constant.
6. **"The short `getStaticFinal` overload searches for the field in the caller's class."** False. The owner is inferred from `type`/wrapper class.
7. **"`getStaticFinal` takes fieldType Object.class because the method returns Object."** False. `type` must reflect the actual field type.
8. **"`BSM_GET_STATIC_FINAL` in `ConstantDescs` is always satisfied with three implicit parameters."** False. The prebuilt descriptor requires the **declaring class static arg**.
9. **"`fieldVarHandle` has `type=int.class` because the field is int."** False. The constant type must be `VarHandle.class`; `fieldType=int.class` is a separate parameter.
10. **"An array VarHandle is created for a specific array instance/index."** False. It describes the array class and takes the array/index at access time.
11. **"A static VarHandle requires passing a receiver on get/set."** False. A static field has no receiver coordinate.
12. **"A VarHandle constant means the field it points to is also immutable."** False. The field has its own semantics; access modes can read/write according to policy.
13. **"A VarHandle to a final field can set it if the bootstrap runs from privileged code."** False. Write access modes for final fields are still unsupported.
14. **"When condy fails to resolve, the next `ldc` automatically retries the bootstrap."** False. The JVM maintains the failure result of the symbolic reference according to resolution rules.
15. **"If simulating the descriptor works, the class file is guaranteed to be valid."** False. You must test the actual classfile structure, bootstrap method handle, static args, and bytecode.
16. **"You can use any Lookup's permissions to read private fields of another module."** False. Access checks must still be satisfied.
17. **"Dynamic constants are like invokedynamic; the bootstrap returns CallSite."** False. Condy returns a value matching the field type; indy returns CallSite.

## 13. Exercises and answers

### Exercise 1 — Distinguishing null types

Determine which cases are valid:

```java
ConstantBootstraps.nullConstant(lookup, "x", String.class);
ConstantBootstraps.nullConstant(lookup, "x", int.class);
ConstantBootstraps.nullConstant(lookup, "x", Void.class);
ConstantBootstraps.nullConstant(lookup, "x", void.class);
```

This is an illustrative snippet with `lookup` already initialized in a method.

**Answer:** `String.class` and `Void.class` are reference types, so they are valid and return `null`. `int.class` and `void.class` are invalid and throw `IllegalArgumentException`.

### Exercise 2 — Finding the right static final overload

Given:

```java
class Config {
    static final String REGION = "APAC";
}
```

To obtain `Config.REGION` via `ConstantBootstraps` when `lookup` has access, which overload should be used?

**Answer:** Use the **four-parameter** overload:

```java
Object region = ConstantBootstraps.getStaticFinal(
        lookup, "REGION", String.class, Config.class);
```

Do not use the short overload because `String.class` is not the owner of `Config.REGION`.

### Exercise 3 — Inferring VarHandle return type

What object does `ConstantBootstraps.fieldVarHandle(lookup,"count",VarHandle.class,Counter.class,int.class)` return? Which coordinates are needed when calling `getVolatile`?

**Answer:** Returns a **`VarHandle`** to the instance field `Counter.count` of type `int`. Requires a `Counter` receiver, e.g., `(int) vh.getVolatile(counter)`. It does not return an `int` value immediately upon linking.

### Exercise 4 — Static argument of BSM_GET_STATIC_FINAL

Given the descriptor:

```java
DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_GET_STATIC_FINAL,
        "ZERO",
        ClassDesc.of("java.math.BigInteger"));
```

What is missing?

**Answer:** Add the **static bootstrap argument** `ClassDesc.of("java.math.BigInteger")` for the **declaring class**. The prebuilt `BSM_GET_STATIC_FINAL` references the overload requiring an owner; omitting it can cause a bootstrap method type/arity error.

### Exercise 5 — Constant pool and mutable state

A `CONSTANT_Dynamic_info` resolves to a `VarHandle` for `State.global`. Then another thread updates the field using `setVolatile`. When calling `getVolatile` via the resolved VarHandle, will the new value be observed?

**Answer:** A VarHandle is a **handle to the variable**, not a copy of the field's value. Subsequent accesses still follow access-mode memory semantics and can observe updates according to the appropriate memory ordering guarantees. The constant pool does not "freeze" the field value.

### Exercise 6 — Identifying a wrong test target

A test calls `desc.resolveConstantDesc(lookup)` twice, sees the bootstrap run twice, and concludes that JVM condy does not cache. Is that conclusion correct?

**Answer:** No. `resolveConstantDesc` **does not cache** when simulating resolution. To test caching of the **JVM run-time constant pool**, you must use a class file with an actual `CONSTANT_Dynamic_info` and have the JVM resolve that entry itself.

### Exercise 7 — Error when updating a final field

A generator creates a VarHandle constant to `static final int LIMIT` and tries `setVolatile(10)`. Why is that wrong?

**Answer:** A VarHandle can support reading a final field, but write access modes are unsupported; creating a handle does not bypass `final`. You should use `getStaticFinal` if the goal is reading a constant, or use a field with an appropriate mutable design if updates are needed.

## Official Documentation

- [Java SE 17 API — ConstantBootstraps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): signatures, conditions, and errors for `nullConstant`, `enumConstant`, `getStaticFinal`, and VarHandle bootstraps.
- [Java SE 17 API — ConstantDescs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDescs.html): prebuilt bootstrap method descriptors.
- [Java SE 17 API — DynamicConstantDesc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): `ofNamed` and `resolveConstantDesc`, including the **no-caching** rule during simulation.
- [Java SE 17 API — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): coordinates, access modes, memory semantics.
- [JVMS 17 — `4.4.10, CONSTANT_Dynamic_info and CONSTANT_InvokeDynamic_info](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10): pool entry structure.
- [JVMS 17 — `5.4.3.6, Dynamic Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): how bootstraps are invoked, caching, concurrency, and result validation.

## Conclusion

`ConstantBootstraps` provides standard bootstraps for producing **dynamic constants**: `nullConstant` returns `null` for a reference type, `enumConstant` selects an enum by name, `getStaticFinal` reads the value of a `static final` field, and `fieldVarHandle` / `staticFieldVarHandle` / `arrayVarHandle` return a **VarHandle** to access variables by coordinates. When creating descriptors, you must clearly distinguish the **constant's type**, the **owner**, and the **static bootstrap arguments** — especially `BSM_GET_STATIC_FINAL`, which requires an owner arg. `DynamicConstantDesc.resolveConstantDesc` helps with simulation, but does not replace testing a **`CONSTANT_Dynamic_info` resolved by the JVM through real bytecode**. Understanding this boundary helps you design runtime/bytecode generators with the right types, permissions, and error semantics, and avoid confusing constant-value caching with freezing object state.