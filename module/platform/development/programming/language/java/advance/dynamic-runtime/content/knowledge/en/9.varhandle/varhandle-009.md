# 9.9 withInvokeExactBehavior, withInvokeBehavior and Converting to MethodHandle

## 1. Overview and Objectives

`VarHandle` in `java.lang.invoke` is a strongly typed reference object to **a variable** or **a family of variables**: an instance field, a static field, an array element, or a memory region created by an appropriate factory. Unlike a regular method, VarHandle has multiple **access modes**: `get`, `set`, `getVolatile`, `setRelease`, `compareAndSet`, `getAndAdd`… Each mode has its own runtime signature.

This lesson dives deep into three APIs:

- **`withInvokeExactBehavior()`:** creates a VarHandle referencing the same variables as the original but requires **the invocation signature to match the access-mode type exactly**.
- **`withInvokeBehavior()`:** creates a VarHandle targeting the same variable but allows **compatible type conversions** according to `MethodHandle.invoke` semantics.
- **`toMethodHandle(VarHandle.AccessMode)`:** converts an access mode operation into a **VarHandle-bound MethodHandle**, suitable for composing into dynamic pipelines.

The `withInvokeExactBehavior`, `withInvokeBehavior`, and `hasInvokeExactBehavior` APIs were added in **Java 16** and work on **Java 17+**. `VarHandle` along with the `toMethodHandle` method appeared in Java 9.

After this lesson, you will be able to accurately explain `WrongMethodTypeException`, distinguish access permissions from signature errors, determine the `MethodType` for GET/SET/CAS of instance/static/array, convert a VarHandle to a MethodHandle properly, and avoid the misconception that exact behavior increases memory synchronization levels.

## 2. Nature of Signatures: Variable Type, Coordinate Types, and Access Mode

VarHandle not only points to the data type `T` but also defines the **coordinates** that must be passed to select the exact target variable:

- `vh.varType()`: the variable type `T`; for example `int.class`.
- `vh.coordinateTypes()`: the parameter types that locate the variable; for example `Counter.class` for an instance field, or `int[].class` and `int.class` for an array element.
- `vh.accessModeType(mode)`: the `MethodType` describing **the signature of the operation** `mode`, consisting of coordinates, additional values, and the return type.
- `vh.isAccessModeSupported(mode)`: indicates whether a specific operation is supported on that variable.

If a variable of type `T` has coordinates `CT1,...,CTn`, then:

```text
AccessMode.GET:             (CT1,...,CTn)T
AccessMode.SET:             (CT1,...,CTn,T)void
AccessMode.GET_AND_ADD:     (CT1,...,CTn,T)T         [if supported]
AccessMode.COMPARE_AND_SET: (CT1,...,CTn,T,T)boolean [if supported]
```

Example with a variable of type `int`:

| VarHandle Source | `coordinateTypes()` | GET Type | SET Type | COMPARE_AND_SET Type |
| --- | --- | --- | --- | --- |
| Instance field `Counter.value` | `[Counter]` | `(Counter)int` | `(Counter,int)void` | `(Counter,int,int)boolean` |
| Static field `total` | `[]` | `()int` | `(int)void` | `(int,int)boolean` |
| `int[]` element | `[int[], int]` | `(int[],int)int` | `(int[],int,int)void` | `(int[],int,int,int)boolean` |

**Key takeaway:** the receiver instance object is a **coordinate**, not a different VarHandle. A static field needs no receiver; an array element needs **the array and index**. Parameter order and return type are part of the contract.

Access-mode methods such as `get(Object... args)` or `set(Object... args)` have **signature-polymorphic** signatures. The compiler records the actual argument types and result type at the **call site**; the JVM matches the compiled descriptor against the access-mode type. Therefore, `(int) vh.get(counter)` and `(long) vh.get(counter)` have two different return descriptors even though both read an int field.

## 3. `withInvokeBehavior()`: Compatible Type Conversion

Syntax:

```java
VarHandle flexible = original.withInvokeBehavior();
boolean exact = flexible.hasInvokeExactBehavior(); // false
```

The snippet above illustrates the case where `original` is a valid VarHandle and `java.lang.invoke.VarHandle` is imported. The API returns a view using **the same target variable**, with type-checking mechanics like `MethodHandle.invoke`: the call-site descriptor is **adapted** to the access-mode type when the conversion conforms to `asType` rules.

Example with a variable of type `int`:

- Passing `short` on SET can convert `short → int`.
- Reading `int` at a call site expecting `long` can convert `int → long`.
- Passing `long` to write an `int` does **not** implicitly narrow the type, because primitive narrowing is not a safe automatic conversion allowed by `asType`.
- Reference cast/unbox/box may be supported when compatible, but can still throw `ClassCastException` or `NullPointerException` depending on the value.
- This mode does **not** eliminate coordinates or accept an arbitrary wrong number of arguments; `WrongMethodTypeException` still occurs when adaptation is not possible.

According to the Java 17 specification, VarHandle access-mode invocation **by default** has invoke behavior. Calling `withInvokeBehavior()` lets you explicitly declare the semantics and guarantee `hasInvokeExactBehavior() == false`. If the current VarHandle already has invoke behavior, the method returns that same VarHandle.

This is a conversion mechanism **at the call boundary**, not changing the field's storage type or turning `SET` into an atomic update.

## 4. `withInvokeExactBehavior()`: Strict Signature Matching

Syntax:

```java
VarHandle exact = original.withInvokeExactBehavior();
boolean strict = exact.hasInvokeExactBehavior(); // true
```

When invoking an access mode on `exact`, the descriptor at the call site **must match** `exact.accessModeType(mode)`. For example, `Counter.value` is an int instance field with the signatures:

```text
GET -> (Counter)int
SET -> (Counter,int)void
```

Therefore:

```java
// Snippet inside a method that already has Counter c and VarHandle exact:
exact.set(c, 8);                   // (Counter,int)void: valid
int n = (int) exact.get(c);        // (Counter)int: valid
// exact.set(c, (short) 8);        // (Counter,short)void: invalid
// long wrong = (long) exact.get(c);  // (Counter)long: invalid
```

The two commented-out statements can throw `WrongMethodTypeException` **at invocation time**, not when creating the VarHandle. Even though `short` can widen to int in Java, invoke-exact **does not perform** that conversion. The return descriptor must also match: `int → long` must happen **outside the call**, for example:

```java
int x = (int) exact.get(c);
long widened = x; // Java widening after the exact call has succeeded
```

**Note on return value:** when the GET access mode returns int, calling `exact.get(c)` as a statement without capturing the result can cause the call site to have return type `void`, which does not match `int`. Use a cast/assignment that expresses the exact return type.

Comparison table:

| Property | `withInvokeBehavior()` | `withInvokeExactBehavior()` |
| --- | --- | --- |
| `hasInvokeExactBehavior()` | `false` | `true` |
| Writing `short` to `int` | Can widen to int | Mismatch, throws `WrongMethodTypeException` |
| Reading `int` as `long` | Can widen the result | Return descriptor mismatch |
| Number of coordinates | Still must be complete/in the right position | Still must be complete/in the right position |
| Atomic operations/memory ordering | Unchanged | Unchanged |
| Field access permissions | None granted additionally | None granted additionally |
| Use when | Dynamic API needs valid type conversions | Fixed-signature pipeline, fail early on contract violation |

The variants are **views over the same set of variables**, not copying data themselves. VarHandle does not allow users to mutate the observable behavioral state of the original object; creating an exact view does not turn a previous flexible view into exact.

## 5. Java 17 Example 1 — Comparing Flexible and Exact Invocation

Save file **`VarHandleBehaviorDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleBehaviorDemo {
    static final class Counter {
        int value;
    }

    public static void main(String[] args) throws Throwable {
        VarHandle base = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        VarHandle flexible = base.withInvokeBehavior();
        VarHandle exact = base.withInvokeExactBehavior();

        Counter c = new Counter();

        System.out.println("flexible exact? "
                + flexible.hasInvokeExactBehavior());
        System.out.println("exact exact? "
                + exact.hasInvokeExactBehavior());
        System.out.println("same variable type: "
                + (exact.varType() == flexible.varType()));
        System.out.println("get type: "
                + exact.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("set type: "
                + exact.accessModeType(VarHandle.AccessMode.SET));

        flexible.set(c, (short) 7);
        System.out.println("flexible short set: "
                + (int) flexible.get(c));

        long widened = (long) flexible.get(c);
        System.out.println("flexible long get: " + widened);

        try {
            exact.set(c, (short) 8);
            System.out.println("unexpected success");
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact short set: rejected");
        }

        exact.set(c, 8);
        System.out.println("exact int set: "
                + (int) exact.get(c));

        try {
            long unexpected = (long) exact.get(c);
            System.out.println("unexpected long: " + unexpected);
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact long get: rejected");
        }

        System.out.println("base unchanged mode: "
                + base.hasInvokeExactBehavior());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 VarHandleBehaviorDemo.java
java VarHandleBehaviorDemo
```

Stdout:

```text
flexible exact? false
exact exact? true
same variable type: true
get type: (Counter)int
set type: (Counter,int)void
flexible short set: 7
flexible long get: 7
exact short set: rejected
exact int set: 8
exact long get: rejected
base unchanged mode: false
```

Explanation:

1. `findVarHandle` finds the right field and checks permissions at creation time; behavior mode does **not** determine whether the field exists.
2. `flexible.set(c, (short) 7)` uses call site `(Counter,short)void`, which is widened to `(Counter,int)void`. `(long) flexible.get(c)` also has its return type widened.
3. `exact.set(c, (short) 8)` and `(long) exact.get(c)` do not match the exact descriptor and are rejected.
4. `exact.set(c, 8)` and `(int) exact.get(c)` succeed, modifying/reading the exact same field that flexible references.
5. `base.hasInvokeExactBehavior()` is not changed by creating the `exact` view.

Because the program runs on a single thread, the output is deterministic. In multithreaded code, choosing exact does not alter the inherent memory semantics of the GET/SET access modes.

## 6. `toMethodHandle(AccessMode)`: Converting an Operation to a Bound MethodHandle

Syntax:

```java
MethodHandle read = vh.toMethodHandle(VarHandle.AccessMode.GET);
```

The API creates a `MethodHandle` **bound to the VarHandle `vh` itself and the GET mode**. Behaviorally, it is equivalent to creating an exact invoker for `vh.accessModeType(GET)` and then binding the first VarHandle argument; implementations may optimize differently.

**The resulting signature equals `vh.accessModeType(mode)`**, with no extra VarHandle parameter:

| Variable Source | `GET` handle | `SET` handle | `COMPARE_AND_SET` handle |
| --- | --- | --- | --- |
| Instance field `int Counter.value` | `(Counter)int` | `(Counter,int)void` | `(Counter,int,int)boolean` |
| Static field `int total` | `()int` | `(int)void` | `(int,int)boolean` |
| Array element `int[]` | `(int[],int)int` | `(int[],int,int)void` | `(int[],int,int,int)boolean` |

Example with an array:

```java
VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);
MethodHandle get = vh.toMethodHandle(VarHandle.AccessMode.GET);
boolean same = get.type().equals(
        vh.accessModeType(VarHandle.AccessMode.GET)); // true
```

The snippet above is an illustration inside a method that has imported `MethodHandles`, `VarHandle`, and `MethodHandle`. The `int[]` VarHandle uses coordinate types `(int[],int)`, so the GET handle has type `(int[],int)int`.

### 6.1. After Conversion: The Two MethodHandle Invoke Methods Remain Independent

**This is the most important point when combining the two APIs:**

- `withInvokeBehavior()` / `withInvokeExactBehavior()` governs **direct access-mode method calls on the VarHandle** such as `vh.get(...)`, `vh.set(...)`.
- `MethodHandle.invoke(...)` performs compatible conversions according to the MethodHandle contract.
- `MethodHandle.invokeExact(...)` **is always exact** with respect to `mh.type()`, even if `mh` was created from a flexible VarHandle.

For example, `mh = vh.withInvokeBehavior().toMethodHandle(GET)` has type `(int[],int)int`. Calling `mh.invoke(data, (short) 1)` can widen the index from short to int. However, `mh.invokeExact(data, (short) 1)` **does not match** and still throws `WrongMethodTypeException`.

Similarly, obtaining `mh` from `vh.withInvokeExactBehavior()` does not make `mh.invoke(...)` lose its own type-conversion capability. A VarHandle's exact behavior **does not change the signature or semantics of the invoke/invokeExact APIs on MethodHandle**.

### 6.2. Do Not Pass the VarHandle Again After Binding

Wrong:

```java
// WRONG illustrative code when get is already from vh.toMethodHandle(GET):
// int x = (int) get.invokeExact(vh, data, 1);
```

Right:

```java
// RIGHT illustrative code when get.type() is (int[],int)int:
int x = (int) get.invokeExact(data, 1);
```

Although `get` accesses the variable through a VarHandle, the VarHandle object itself has already been **bound inside** the method handle. Only the variable's coordinate types remain in the signature. The code above is a snippet requiring the `get` variable and `data` array to be already declared.

## 7. Java 17 Example 2 — Converting GET, SET, GET_AND_ADD, COMPARE_AND_SET

Save file **`VarHandleBridgeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleBridgeDemo {
    public static void main(String[] args) throws Throwable {
        int[] data = {10, 20};
        VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);

        MethodHandle get =
                vh.toMethodHandle(VarHandle.AccessMode.GET);
        MethodHandle set =
                vh.toMethodHandle(VarHandle.AccessMode.SET);
        MethodHandle add =
                vh.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD);
        MethodHandle cas =
                vh.toMethodHandle(VarHandle.AccessMode.COMPARE_AND_SET);

        System.out.println("coords: " + vh.coordinateTypes());
        System.out.println("get type: " + get.type());
        System.out.println("set type: " + set.type());
        System.out.println("add type: " + add.type());
        System.out.println("cas type: " + cas.type());
        System.out.println("accessModeType agrees: "
                + get.type().equals(
                        vh.accessModeType(VarHandle.AccessMode.GET)));

        System.out.println("get exact: "
                + (int) get.invokeExact(data, 1));
        set.invokeExact(data, 1, 25);
        System.out.println("set exact: " + data[1]);

        System.out.println("get invoke short index: "
                + (int) get.invoke(data, (short) 1));

        try {
            int ignored = (int) get.invokeExact(data, (short) 1);
            System.out.println("unexpected: " + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("mh invokeExact short index: rejected");
        }

        System.out.println("getAndAdd previous: "
                + (int) add.invokeExact(data, 1, 5));
        System.out.println("compareAndSet success: "
                + (boolean) cas.invokeExact(data, 1, 30, 31));
        System.out.println("final value: " + data[1]);

        VarHandle exactVH = vh.withInvokeExactBehavior();
        MethodHandle exactGet =
                exactVH.toMethodHandle(VarHandle.AccessMode.GET);
        System.out.println("same mh type after exact: "
                + exactGet.type().equals(get.type()));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 VarHandleBridgeDemo.java
java VarHandleBridgeDemo
```

Stdout:

```text
coords: [class [I, int]
get type: (int[],int)int
set type: (int[],int,int)void
add type: (int[],int,int)int
cas type: (int[],int,int,int)boolean
accessModeType agrees: true
get exact: 20
set exact: 25
get invoke short index: 25
mh invokeExact short index: rejected
getAndAdd previous: 25
compareAndSet success: true
final value: 31
same mh type after exact: true
```

**Output analysis:**

- `coords: [class [I, int]` is how `Class.toString()` represents `int[].class` (JVM notation `[I`) and `int.class`. These are the **array + index** coordinates, not specific array element values.
- The GET handle reads element at index 1: 20. The SET handle writes 25 to the same position.
- `get.invoke(data, (short) 1)` succeeds thanks to **MethodHandle.invoke** conversion; `get.invokeExact(data, (short) 1)` is rejected because the index must be int.
- `GET_AND_ADD` increments the element from 25 to 30, returning the previous value **25**. CAS expects 30, changes it to 31, and returns true.
- `exactVH.toMethodHandle(GET)` has the same type as `vh.toMethodHandle(GET)`; the VarHandle's behavior does not change the signature of the created MethodHandle.

When using `invokeExact`, the return type must also match: `(int) get.invokeExact(...)` for int GET, `(boolean) cas.invokeExact(...)` for CAS; SET returns void so it is called as a statement.

## 8. Java 17 Example 3 — Static Field and Read-Only Final Field

`toMethodHandle` does not automatically turn an unsupported mode into a valid operation. `VarHandle.isAccessModeSupported(mode)` must be checked separately: for a `final` field, GET is allowed but write/atomic-update modes such as SET are not supported.

Create file **`VarHandleBoundaryDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleBoundaryDemo {
    static int total = 4;

    static final class Record {
        final int code = 42;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle totalVH = lookup.findStaticVarHandle(
                VarHandleBoundaryDemo.class, "total", int.class);
        MethodHandle load =
                totalVH.toMethodHandle(VarHandle.AccessMode.GET);
        MethodHandle update =
                totalVH.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD);

        System.out.println("static coordinates: "
                + totalVH.coordinateTypes().size());
        System.out.println("static get type: " + load.type());
        System.out.println("static add type: " + update.type());
        System.out.println("static before: " + (int) load.invokeExact());
        System.out.println("static previous: "
                + (int) update.invokeExact(3));
        System.out.println("static after: " + (int) load.invokeExact());

        VarHandle finalVH = lookup.findVarHandle(
                Record.class, "code", int.class);
        System.out.println("final GET supported: "
                + finalVH.isAccessModeSupported(VarHandle.AccessMode.GET));
        System.out.println("final SET supported: "
                + finalVH.isAccessModeSupported(VarHandle.AccessMode.SET));

        MethodHandle readFinal =
                finalVH.toMethodHandle(VarHandle.AccessMode.GET);
        System.out.println("final code: "
                + (int) readFinal.invokeExact(new Record()));

        try {
            MethodHandle writeFinal =
                    finalVH.toMethodHandle(VarHandle.AccessMode.SET);
            writeFinal.invokeExact(new Record(), 9);
            System.out.println("unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("final write: unsupported");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 VarHandleBoundaryDemo.java
java VarHandleBoundaryDemo
```

Stdout:

```text
static coordinates: 0
static get type: ()int
static add type: (int)int
static before: 4
static previous: 4
static after: 7
final GET supported: true
final SET supported: false
final code: 42
final write: unsupported
```

**Explanation:**

- Static field `total` needs no receiver, so the GET handle is `()int` and the GET_AND_ADD handle is `(int)int`; the single parameter of GET_AND_ADD is the **delta**. It returns the old value 4, and then total is 7.
- For `Record.code`, GET still has signature `(Record)int` because a receiver is needed; the `final` field is read normally.
- Even though a syntactically valid SET type `(Record,int)void` can be described, the SET mode is not supported for a final field. Invoking it throws `UnsupportedOperationException`, **not** `WrongMethodTypeException` for a signature mismatch.

Do not use `withInvokeBehavior` or `withInvokeExactBehavior` to try to bypass final rules. Those views do not unlock forbidden access or turn a read-only field into a writable one.

## 9. Comparison with `varHandleInvoker` and `varHandleExactInvoker`

Besides `toMethodHandle`, there are two factories in the `MethodHandles` class:

- `varHandleExactInvoker(mode, methodType)` creates a MethodHandle that dispatches the access mode with an **exact signature**.
- `varHandleInvoker(mode, methodType)` creates a MethodHandle that dispatches with **invoke behavior**, capable of adapting signatures according to API rules.

The key difference is **binding**:

| API | Binds a specific VarHandle? | First parameter of the handle |
| --- | --- | --- |
| `vh.toMethodHandle(GET)` | Yes | The first coordinate, if any |
| `MethodHandles.varHandleExactInvoker(GET, type)` | No | `VarHandle`, followed by coordinates |
| `MethodHandles.varHandleInvoker(GET, type)` | No | `VarHandle`, followed by coordinates |

For example, `vh` for an `int[]` element has GET type `(int[],int)int`. `vh.toMethodHandle(GET)` produces a handle taking **2 parameters** (array, index); an unbound invoker takes **3 parameters** (VarHandle, array, index).

Behaviorally, `toMethodHandle(mode)` is equivalent to an exact invoker for `vh.accessModeType(mode)` already bound to `vh` (which the JVM may optimize differently). It is convenient when a pipeline needs to invoke **a specific chosen variable/data source**. Unbound invokers fit when a generic dispatcher needs to accept multiple VarHandles with compatible signatures.

**Do not confuse the two API layers:** `withInvokeExactBehavior` changes the semantics of **VarHandle access-mode invocation**, whereas `MethodHandle.invokeExact` is a rule of **MethodHandle** itself. Both share the concept of "exact" but apply to two different kinds of calls.

### 9.1. Why Not Use Reflection `Method.invoke` on `VarHandle.get`?

Access-mode methods are represented specially in bytecode. If you reflect `VarHandle.class.getDeclaredMethod("get", Object[].class)` and try `Method.invoke`, that is **not** equivalent to the signature-polymorphic syntax `vh.get(...)`. The Javadoc describes reflecting access-mode methods as placeholder methods for presentation purposes; invoking them via Reflection typically results in `UnsupportedOperationException`.

To use VarHandle in dynamic systems, either call the access-mode method directly or obtain a `MethodHandle` via `toMethodHandle` or the corresponding invoker. Do not use Reflection on the `get` method of the `VarHandle` class itself as a workaround.

## 10. Composing MethodHandles After Conversion

Once you have a handle from a VarHandle, you can use combinators:

- `insertArguments` to **bind coordinates**, such as array and index;
- `filterArguments` to transform inputs before entering a SET operation;
- `filterReturnValue` to transform the result of a GET;
- `guardWithTest` to select a read/write branch or fallback;
- `asType` to make acceptable conversions explicit at a pipeline boundary.

**Illustrative snippet** example, assuming `read` is the `(int[],int)int` MethodHandle from section 7 and `data` is an `int[]`:

```java
MethodHandle getIndexZero = MethodHandles.insertArguments(
        read, 0, data, 0);
// getIndexZero.type() is ()int
int first = (int) getIndexZero.invokeExact();
```

`insertArguments` bound **the array reference and index 0**, not the element's value. If the element at index 0 changes, a subsequent call to `getIndexZero` can read the new value according to the memory semantics of the GET mode. The final signature becomes `()int`.

**Do not confuse** binding coordinates with copying a data snapshot. The MethodHandle retains the capability to access the bound array; the array object can still be mutated and requires concurrency management when shared across threads.

## 11. Exact Behavior Is Not a Memory Synchronization Mode

VarHandle has access modes with their own memory semantics:

- `GET`/`SET`: plain read/write.
- `GET_OPAQUE`/`SET_OPAQUE`: opaque access with corresponding guarantees.
- `GET_ACQUIRE`/`SET_RELEASE`: acquire/release ordering.
- `GET_VOLATILE`/`SET_VOLATILE`: volatile semantics.
- `COMPARE_AND_SET`/`GET_AND_ADD`: atomic updates when supported by the variable.

**`withInvokeExactBehavior` does not turn `GET` into `GET_VOLATILE`**, and `toMethodHandle(GET)` does not create an atomic read-modify-write. To get a volatile read as a MethodHandle, choose **`toMethodHandle(AccessMode.GET_VOLATILE)`**.

Attaching adapters to a `MethodHandle` also does not automatically upgrade memory ordering. If a concurrency algorithm requires release/acquire or CAS, choose the right mode and test across multiple threads under the Java Memory Model.

Conversely, exact type checking can help catch **signature errors**, but it does not guard against **data races**, index errors, null receivers, or unsupported access modes. Those are different kinds of contracts.

## 12. Distinguishing Errors: Type, Mode Support, and Access Permissions

| Error or Symptom | Cause | Appropriate Fix |
| --- | --- | --- |
| `WrongMethodTypeException` on `exact.set(c, (short) 7)` | Exact mode does not accept a descriptor with short instead of int. | Use the exact int type or choose invoke behavior when conversion is valid. |
| `WrongMethodTypeException` when reading long from int GET in exact | Return descriptor mismatch. | Receive int first then widen outside the call, or use invoke behavior. |
| `WrongMethodTypeException` on `mh.invokeExact(data, (short)1)` | MethodHandle requires an int index. | Use int; or `mh.invoke` with compatible conversion. |
| `ClassCastException` on reference conversion | Call site requests a cast to a type incompatible with the runtime value. | Check data and types before calling. |
| `UnsupportedOperationException` when writing a final field | SET mode is not supported on final fields. | Check `isAccessModeSupported`; choose an appropriate mechanism. |
| `NoSuchFieldException` during `findVarHandle` | Field name or type is incorrect. | Check the declaration and field type. |
| `IllegalAccessException` during `findVarHandle` | Lookup lacks permission per Java access checks / JPMS. | Use a legitimate Lookup; `opens`/public API when appropriate. |
| `NullPointerException` or `ArrayIndexOutOfBoundsException` | Null receiver/array or invalid index. | Validate coordinates and business logic. |
| Adding a VarHandle argument after `toMethodHandle` | VarHandle is already bound, causing a signature mismatch. | Pass only coordinates/values according to `mh.type()`. |
| Correct types on read/write but wrong results across threads | Mode lacks required memory ordering or data race exists. | Choose the right access mode and synchronization model. |

**An effective diagnostic tip:** print `vh.varType()`, `vh.coordinateTypes()`, `vh.accessModeType(mode)`, and `mh.type()` before assembling the graph. For a specific mode, check `isAccessModeSupported(mode)`. For errors at VarHandle creation time, handle `NoSuchFieldException`/`IllegalAccessException`; for errors at invocation time, distinguish `WrongMethodTypeException` and `UnsupportedOperationException`.

## 13. Pipeline Design and Capability Protection

VarHandles are created from `MethodHandles.Lookup.findVarHandle`, `findStaticVarHandle`, or an appropriate factory, and member access permissions are checked **at creation time**. Once you have a valid VarHandle referencing a private field, sharing that VarHandle or a MethodHandle converted from it with other code can grant actual read/write capability to that field.

Therefore:

1. Do not hand out private `VarHandle`s or MethodHandles to sensitive data to untrusted plugins.
2. If the recipient only needs GET, consider providing **a narrow read-only API** or `toMethodHandle(GET)` instead of the full VarHandle with SET/CAS.
3. Do not treat invoke-exact behavior as a sandbox; it only enforces stricter type checking, not restricting data access permissions.
4. Check mode support when building the graph, rather than letting UnsupportedOperationException happen on the hot path.
5. Cache handles when pipelines are stable to reduce recreation overhead; benchmark performance with real workloads rather than assuming exact is always faster than invoke.
6. If passing a VarHandle across module boundaries, JPMS lookup conditions must be resolved **at handle creation time**, and cannot be bypassed via toMethodHandle.

**Application example:** a dynamic serializer can use `toMethodHandle(GET)` followed by `filterReturnValue` to normalize data; a counter can use `toMethodHandle(GET_AND_ADD)` to create an atomic increment node. In both, signatures and memory modes must be modeled explicitly before composition.

## 14. Practice Exercises and Test Suggestions

**Exercise A — safe type conversion while staying exact:** For an `int` instance field, use `exact.get(receiver)` to read as int first, then convert to long in Java:

```java
int x = (int) exact.get(receiver);
long y = x;
```

This is an illustration where `exact` has access-mode type `(Receiver)int` and `receiver` has the exact coordinate type. Do not replace it with `long y = (long) exact.get(receiver)` because then the descriptor of the access-mode invocation itself is `(Receiver)long` and may throw `WrongMethodTypeException`.

**Exercise B — arrays and adapters:** Obtain a GET MethodHandle from `arrayElementVarHandle(int[].class)`. Verify `mh.type()` is `(int[],int)int`, bind the array/index with `insertArguments`, check that the type becomes `()int`, and read again after mutating the element.

**Exercise C — final field:** Find a VarHandle to `final int code`. Verify GET is supported and SET is unsupported. Use `toMethodHandle(GET)` to read; explain why behavior mode does not change writability.

**Exercise D — switching from exact to flexible:** Use `exact.withInvokeBehavior()` and then try `set(c, (short)7)`. Prove that the behavior returns `false` via `hasInvokeExactBehavior()`, while the original exact VarHandle still retains `true`.

The test suite should at least cover: instance/static/array coordinates, GET/SET/CAS descriptors, short→int and int→long under invoke, mismatch under exact, `mh.invoke` vs `mh.invokeExact`, unsupported final field, and a GET_VOLATILE access mode to ensure the mode is preserved after conversion.

## 15. Self-Check Questions

**1. Does `withInvokeExactBehavior` create a new variable?**

No. It creates a VarHandle view over the same set of variables but checks the call-site descriptor against the exact access-mode type.

**2. Why can `flexible.set(c, (short)7)` run while `exact.set(c, (short)7)` fails for an int field?**

Invoke behavior can widen short→int; exact behavior requires the exact int parameter and throws `WrongMethodTypeException` if the caller passes short.

**3. Does `toMethodHandle(GET)` take a VarHandle argument when invoked?**

No. The VarHandle is already bound. The MethodHandle only takes coordinates; for int[] those are the array and index.

**4. Does creating a MethodHandle from a flexible VarHandle make `MethodHandle.invokeExact` perform type conversions?**

No. `MethodHandle.invokeExact` always requires the exact `mh.type()`. Only `MethodHandle.invoke` applies compatible conversions.

**5. What is `toMethodHandle(GET).type()` for a static int field?**

`()int`, because a static field needs no receiver coordinate. For an instance int field it will be `(Receiver)int`.

**6. Does `withInvokeExactBehavior` make GET stronger than GET_VOLATILE in memory ordering?**

No. Exact only governs signature checking. GET_VOLATILE is a separate access mode with volatile semantics.

**7. Why can a `final` field still be read while SET throws `UnsupportedOperationException`?**

Because the VarHandle for a final field only supports reading and disallows write/update access modes; it has nothing to do with call-site conversions.

## 16. Key Takeaways

- **Invoke behavior:** can convert types on an access-mode call according to compatibility rules like `MethodHandle.invoke`.
- **Invoke-exact behavior:** the access-mode invocation descriptor must **match `accessModeType(mode)` exactly**.
- **`toMethodHandle(mode)`:** returns a MethodHandle bound to the VarHandle and mode, with type equal to `accessModeType(mode)`; do not add a VarHandle parameter.
- **Two independent type-checking axes:** a VarHandle's behavior on direct calls is separate from choosing `invoke` / `invokeExact` on a MethodHandle.
- **Check modes and memory semantics:** exact does not increase atomicity; GET/GET_VOLATILE/CAS have different semantics.
- **Keep permissions safe:** views do not elevate permissions, but an already-granted VarHandle/MethodHandle capability can be shared; grant only the necessary permissions.

### Official Java SE 17 Documentation

- [VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html) — `withInvokeExactBehavior`, `withInvokeBehavior`, `hasInvokeExactBehavior`, `accessModeType`, `toMethodHandle`, `isAccessModeSupported`.
- [MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html) — `arrayElementVarHandle`, `Lookup.findVarHandle`, `varHandleExactInvoker`, and `varHandleInvoker`.
- [MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) — `invoke`, `invokeExact`, `asType`, call-site signatures.
- [MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html) — parameter types and return type of a MethodHandle.
