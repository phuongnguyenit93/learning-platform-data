# VarHandle for Fields or Array Elements in Java

## 1. What Problem Does VarHandle Solve?

When working with Java Reflection, you can read and modify field values via `java.lang.reflect.Field`. In concurrent code, you also need to specify **how memory is read/written** and sometimes perform **atomic** operations such as incrementing a counter or swapping a value only if it still equals an expected value. Since Java 9, `java.lang.invoke.VarHandle` provides strongly typed variable access with multiple access modes.

A `VarHandle` represents a **variable storage location**: an instance field, static field, array element, or view over memory supported by corresponding factories. This lesson focuses on **fields and array elements**. Unlike `MethodHandle`, which represents an invocation operation, `VarHandle` represents **the accessed variable** together with the set of valid operations on that variable.

Points to distinguish:

- **Which variable?** A specific field or an element of an array type.
- **How is the variable located?** An instance field needs a receiver object; a static field needs no receiver; an array element needs an array object and an index.
- **Which operation?** Plain read/write (`get`/`set`), read/write with memory-ordering rules (`getVolatile`/`setVolatile`, `getAcquire`/`setRelease`, etc.), or atomic operations like `compareAndSet` and `getAndAdd`.
- **Is access permitted?** Field lookup still obeys Java/module access controls. Having a handle is not a license to mutate every field: unsupported access modes can still be rejected.

## 2. Variable Type and Coordinate Types Model

A `VarHandle` has two defining properties:

1. `varType()`: the data type of the accessed variable, such as `int.class` or `String.class`.
2. `coordinateTypes()`: the list of types used to **locate** the variable. This is not an ordinary Java method parameter list.

| Variable Location | How to Obtain Handle | `varType()` | `coordinateTypes()` | Read Example |
| --- | --- | --- | --- | --- |
| Instance field `Counter.value: int` | `lookup.findVarHandle(Counter.class, "value", int.class)` | `int` | `[Counter]` | `(int) vh.get(counter)` |
| Static field `Config.level: int` | `lookup.findStaticVarHandle(Config.class, "level", int.class)` | `int` | `[]` | `(int) vh.get()` |
| `int[]` element | `MethodHandles.arrayElementVarHandle(int[].class)` | `int` | `[int[], int]` | `(int) vh.get(numbers, index)` |

The calls on the right are illustrated assuming `vh` is the handle matching that row. With `arrayElementVarHandle`, the handle represents **accessing elements of that array type**, not bound to any specific array or index: pass the array and index on each call.

How arguments are determined for an access mode:

```text
instance field:  get(receiver)                     set(receiver, value)
static field:    get()                             set(value)
array element:   get(array, index)                 set(array, index, value)

compareAndSet:   compareAndSet(coordinates..., expected, update)
getAndAdd:       getAndAdd(coordinates..., delta)
```

`coordinates...` are all coordinates matching the handle kind. For `get`, the result has type `varType`; for `set`, the call produces no result; for `compareAndSet`, the result type is `boolean`; for `getAndAdd`, the result is the value **before** adding.

## 3. Creating a VarHandle for an Instance Field

Use `MethodHandles.Lookup.findVarHandle`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
VarHandle valueHandle = lookup.findVarHandle(
    Counter.class,
    "value",
    int.class
);
```

In this example, `Counter` has an instance field named `value` of type `int`. The field is **not** static. During lookup, `int.class` must match the field's declared type; when accessing, a valid `Counter` receiver is required.

If the field is declared `private`, the lookup must hold corresponding private permissions. `MethodHandles.lookup()` is bound to the class where it is called; moving the lookup code to another class can alter permissions. `MethodHandles.publicLookup()` does not grant private access by itself. Package and Java module rules also apply; `privateLookupIn` works only when required access conditions are met.

Example operations on the same handle:

```java
valueHandle.set(counter, 10);                            // Plain write.
int current = (int) valueHandle.get(counter);             // Plain read.
int old = (int) valueHandle.getAndAdd(counter, 5);        // Atomic add, returns old value.
boolean changed = (boolean) valueHandle.compareAndSet(
    counter, 15, 20                                      // Swap 15 -> 20 only if still 15.
);
```

This is an **illustrative snippet** using `valueHandle` and `counter` created elsewhere; a standalone runnable program appears in section 7. Note that `get` and `set` are plain accesses and should not be relied upon in place of cross-thread synchronization rules.

## 4. VarHandle for a Static Field

For a `static` field, you must use `findStaticVarHandle`:

```java
VarHandle sharedHandle = lookup.findStaticVarHandle(
    Config.class,
    "level",
    int.class
);

sharedHandle.setVolatile(7);
int level = (int) sharedHandle.getVolatile();
```

The first line assumes `Config` has a static field `level` of type `int` and the lookup has access permission; this snippet illustrates within a context holding `lookup`. Unlike an instance field, `sharedHandle.coordinateTypes()` is empty, so **do not** pass a `Config` object to `getVolatile` or `setVolatile`.

Do not swap `findVarHandle` with `findStaticVarHandle`: the two APIs look up two different kinds of fields. The field name, declaring class, and field type must be exact. This is a difference in **locating the variable**, while supported access modes still depend on field kind and value type.

## 5. VarHandle for an Array Element

Use the factory:

```java
VarHandle elementHandle = MethodHandles.arrayElementVarHandle(int[].class);
int[] scores = {10, 20, 30};

int first = (int) elementHandle.get(scores, 0);      // 10
elementHandle.set(scores, 1, 25);                    // scores[1] = 25
int old = (int) elementHandle.getAndAdd(scores, 2, 5); // old = 30; scores[2] = 35
```

This snippet is a standalone syntax illustration when placed in a method with the corresponding imports. One handle created from `int[].class` can operate on many different `int[]` instances; every call must pass **the array** and **the index**.

Notes:

- `arrayElementVarHandle` accepts an **array class**, such as `int[].class` or `String[].class`, not an array instance as the factory parameter.
- For `int[]`, `varType()` is `int.class`; `coordinateTypes()` contains the array type `int[].class` and `int.class` for the index.
- An out-of-bounds index throws `ArrayIndexOutOfBoundsException`; a `null` array receiver throws `NullPointerException`.
- Operations like `getAndAdd` are meaningful only for data types supported by that access mode. Do not assume addition applies to `String[]`.
- For reference arrays, Java's element type compatibility rules remain in force, including array store checks at runtime.

## 6. Locating a Variable vs Choosing an Access Mode
Once a `VarHandle` is created for the right location, each operation also has its own **access rules**. `get`/`set` have plain semantics, `getVolatile`/`setVolatile` have volatile semantics, `getAcquire`/`setRelease` are used in publish/consume protocols, and `compareAndSet` and `getAndAdd` are atomic update operations when supported. You must use `isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` if dynamic tooling does not know the variable type in advance.

Two separate calls `get` then `set` remain two distinct operations, so they cannot replace `getAndAdd` when multiple threads increment a variable concurrently. Likewise, plain `get` or `set` is insufficient to establish happens-before relationships between threads on its own. When studying concurrency, you must identify the right access mode and data-sharing protocol; the lesson on memory ordering in this same chapter analyzes these conditions thoroughly.

## 7. Complete Program: Instance Field, Static Field, and Array

Save all the code below as `VarHandleDemo.java`, using JDK 17+.

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.Arrays;

public class VarHandleDemo {
    private static class Counter {
        private volatile int value;
    }

    private static volatile int shared;

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle field = lookup.findVarHandle(Counter.class, "value", int.class);
        VarHandle staticField = lookup.findStaticVarHandle(
            VarHandleDemo.class, "shared", int.class
        );
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);

        Counter counter = new Counter();
        field.setVolatile(counter, 10);
        System.out.println("field initial = " + (int) field.getVolatile(counter));
        System.out.println("field old = " + (int) field.getAndAdd(counter, 5));
        System.out.println("field CAS = "
                + (boolean) field.compareAndSet(counter, 15, 21));
        System.out.println("field final = " + (int) field.getVolatile(counter));

        staticField.setVolatile(7);
        System.out.println("static = " + (int) staticField.getVolatile());

        int[] numbers = {3, 4, 5};
        element.set(numbers, 1, 40);
        System.out.println("array old = " + (int) element.getAndAdd(numbers, 1, 2));
        System.out.println("array CAS = "
                + (boolean) element.compareAndSet(numbers, 2, 5, 50));
        System.out.println("array = " + Arrays.toString(numbers));

        System.out.println("field coordinates = " + field.coordinateTypes().size());
        System.out.println("static coordinates = " + staticField.coordinateTypes().size());
        System.out.println("array coordinates = " + element.coordinateTypes().size());
        System.out.println("variable type = " + field.varType().getSimpleName());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 VarHandleDemo.java
java VarHandleDemo
```

**Deterministic output** (verified on JDK 21):

```text
field initial = 10
field old = 10
field CAS = true
field final = 21
static = 7
array old = 40
array CAS = true
array = [3, 42, 50]
field coordinates = 1
static coordinates = 0
array coordinates = 2
variable type = int
```

Group-by-group analysis:

1. `field.setVolatile(counter, 10)` sets the initial value. `getAndAdd(counter, 5)` returns **10** and changes the value to **15**; `compareAndSet(counter, 15, 21)` succeeds and brings the value to **21**.
2. `staticField` needs no receiver: `setVolatile(7)` and `getVolatile()` access the static field directly.
3. `element.set(numbers, 1, 40)` updates the second element. `getAndAdd(numbers, 1, 2)` returns **40** and updates the element to **42**. CAS swaps index 2 from **5** to **50**.
4. The three coordinate counts are **1**, **0**, **2**, matching instance field, static field, and array element; all have `varType` equal to `int` in the example.

`Counter` is a nested class of `VarHandleDemo` and both share a *nest*, so the lookup in the outer class has permission to access `Counter`'s private field. When moving code into other classes/modules, re-evaluate access rights instead of copying the lookup syntax verbatim and assuming it will still succeed.

## 8. Common Errors and Diagnosis

| Error / Symptom | Common Cause | Fix |
| --- | --- | --- |
| `NoSuchFieldException` on lookup | Wrong field name, declared type, or instance/static choice | Inspect the actual field; distinguish `findVarHandle` from `findStaticVarHandle` |
| `IllegalAccessException` on lookup | Lookup lacks access to field or module/package | Create lookup in an appropriately privileged class; check modifiers and `exports`/`opens`; do not open modules arbitrarily |
| `WrongMethodTypeException` on invocation | Missing receiver, missing index, wrong data type, or wrong return type at call site | Check `varType()`, `coordinateTypes()`, and result casts |
| `ClassCastException` or other runtime error | Incompatible receiver object or runtime value | Check object type and actual variable type |
| `ArrayIndexOutOfBoundsException` / `NullPointerException` | Invalid index / null array or receiver | Validate array, receiver, and index before calling |
| `UnsupportedOperationException` | Unsupported mode, e.g. writing via a `final` field handle or arithmetic on an unsupported type | Use `isAccessModeSupported(...)`; choose another mode/data type |
| Wrong count under multi-threaded updates | Using a `get` then `set` pair leading to lost updates | Use an atomic operation such as `getAndAdd` or an appropriate synchronization solution |
| Misunderstood cross-thread data visibility | Using plain access while expecting volatile effects | Choose the right access mode and synchronization protocol per the Java Memory Model |

Do not treat `VarHandle` as a way to bypass all access rules. It provides dynamic variable operations and memory ordering, but does not exempt code from Java permissions, data types, or concurrent algorithm correctness.

## 9. Practice Exercises

1. Write a `Book` class containing `private int copies`. Create a valid `VarHandle` for the field, read and update the copy count. State the handle's `coordinateTypes()`.
2. Create a `String[] names` array and an array-element handle. Why is `getAndAdd(names, 0, ...)` not an appropriate operation?
3. If `Config.active` is `static boolean`, which factory must be used, and how many coordinates are there?
4. When two threads both run `x = get(x) + 1; set(x)`, why can the final result be smaller than the total number of increments? Which API should replace it?
5. For `compareAndSet`, identify expected/update and explain the return value. If the field is `final`, which operations must be avoided?
6. Try calling `isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` on a handle whose variable type does not support addition, and explain the result.

**Completion goal:** learners can determine the variable type and coordinates for instance/static fields and array elements; create the right handle; invoke `get`, `set`, `getAndAdd`, and `compareAndSet` properly; choose access modes based on concurrency requirements; and recognize access limitations.