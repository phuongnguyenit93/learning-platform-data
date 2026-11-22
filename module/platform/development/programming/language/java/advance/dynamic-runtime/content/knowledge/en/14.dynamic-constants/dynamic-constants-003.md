# 14.3 Resolution via `ldc`, Caching the Selected Value, and Handling Resolution Errors

## 1. Objective: Understanding How a Dynamic Constant Is "Computed Once"

A **dynamic constant** (*dynamically computed constant*, often written **condy**) is a value in the **run-time constant pool** of the Java Virtual Machine (JVM), determined by running a **bootstrap method (BSM)** when a symbolic reference to the constant needs to be resolved. This mechanism is represented by a **`CONSTANT_Dynamic`** entry in the class file (supported since class-file version 55, Java 11).

It differs from literal constants like `"hello"` or `42` pre-written by the compiler: a `CONSTANT_Dynamic` describes **how to compute or obtain the value**, while the actual value is produced by the bootstrap during resolution.

The focus of section **14.3** includes:

1. How `ldc`, `ldc_w`, and `ldc2_w` **read a dynamic constant**, and when the JVM needs to invoke the BSM.
2. When multiple bytecode instructions reference the **same `CONSTANT_Dynamic`**, at what scope the JVM **caches the selected value**; whether changes to external Java state cause the BSM to run again.
3. How the JVM reacts if the BSM throws an exception, returns the **wrong type**, or returns `null`; the difference between a **reference** constant and a **primitive** constant.
4. Whether **retrying use after a resolution error** automatically "retries" the bootstrap; whether using a new class loader changes anything.
5. Distinguishing the caching of **`CONSTANT_Dynamic`** from the **lexical instruction** linking rule of `invokedynamic`, avoiding mixing the two mechanisms.

This lesson uses **a Java 17+ program that generates a real class file containing `CONSTANT_Dynamic`**, tested with `javac`/`java`, and uses `javap -v -c` to inspect `ldc` and `ldc_w` opcodes. No external bytecode library is needed.

> **Most important point:** For a resolved dynamic constant, other `ldc` instructions referencing the **same run-time constant pool entry** will receive the **same selected value** without calling the BSM again. If resolution has failed, subsequent uses of the **same symbolic reference** also continue to fail without automatically retrying the bootstrap. In a situation where multiple threads resolve for the first time concurrently, the BSM may run concurrently; the JVM picks one result to publish.

## 2. What Does `CONSTANT_Dynamic` Contain?

A `CONSTANT_Dynamic_info` entry in the class file has the structure:

```text
CONSTANT_Dynamic_info {
    u1 tag;                           // value 17
    u2 bootstrap_method_attr_index;   // index into BootstrapMethods
    u2 name_and_type_index;           // CONSTANT_NameAndType
}
```

`CONSTANT_NameAndType` contains the **constant name** and a **field descriptor** — for example `Ljava/lang/String;`, `I`, `J` — not a method descriptor.

**Quick comparison:**

| Property | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- |
| Tag in constant pool | `17` | `18` |
| NameAndType descriptor | **Field descriptor** such as `Ljava/lang/String;`, `I` | **Method descriptor** such as `()Ljava/lang/String;` |
| BSM result | Value of the constant, compatible with declared type | `CallSite` whose `type()` matches method descriptor |
| Instructions using it | `ldc`, `ldc_w`, `ldc2_w`; can also be a bootstrap argument of another constant/call site | `invokedynamic` |
| Resolution scope | One **symbolic reference / constant-pool entry** in the class being defined | Per individual **lexical `invokedynamic` instruction** |
| Normal BSM invocations after resolution | Not called again for the same entry | Not called again for the same instruction |

Example `CONSTANT_Dynamic` describing a `String` named `CHOSEN`:

```text
#20 = Dynamic #0:#19   // #0:CHOSEN:Ljava/lang/String;
                        // bootstrap index 0; NameAndType #19
```

This line is a **`javap` excerpt**. Entry `#20` does not contain the characters `"choice-A"` or `"choice-B"`; it contains a **symbolic recipe** consisting of the BSM index and name/type. The JVM will call the BSM and validate the result, then retain the selected value for subsequent uses.

### 2.1. The Three Context Parameters of the Bootstrap

A BSM typically has a signature close to:

```java
public static Object bootstrap(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type) {
    // Create or obtain a constant value whose type matches type.
}
```

This is an **illustrative snippet** (not a standalone program yet):

- `caller`: `Lookup` of the class where the constant-pool entry is being resolved, supporting access control rules.
- `name`: the symbolic name of the constant, such as `"CHOSEN"`; **not** an actual Java field required to exist.
- `type`: the `Class<?>` object corresponding to the **field descriptor** of `CONSTANT_Dynamic`, such as `String.class` or `int.class`.

The BSM can receive additional **static bootstrap arguments** after the three context parameters. The JVM decodes the arguments from the `BootstrapMethods` attribute before calling the bootstrap. The actual BSM signature must be compatible with that call; it is not mandatory for the BSM to return `Object` in every case if method-handle invocation conversions are valid.

**Do not confuse `Class<?> type` of condy with `MethodType type` of `invokedynamic`.** A `String` constant declares value type `String.class`; a `()String` call site declares method type `MethodType.methodType(String.class)`.

### 2.2. When Does a Dynamic Constant Differ from a Java `static final` Constant?

`static final` is a **field** with its own class initialization rules. A dynamic constant is **a symbolic entry in the constant pool**: the `ldc` instruction can obtain its resolved value without the application declaring a Java field of the same name. In the example below, there is no `CHOSEN` field on the `CondyGenerated` class.

Even though `CONSTANT_Dynamic` has the word **constant** in its name, if the selected value is a reference to a mutable object, that object can be mutated internally according to its API contract. What the JVM stores is the **resolution result / selected reference**, not automatically creating a deep copy or guaranteeing the object is immutable.

## 3. How Do `ldc`, `ldc_w`, and `ldc2_w` Use Dynamic Constants?

A dynamic constant is loaded onto the **operand stack** by the `ldc` instruction family. The phrase "load constant" here **does not mean the BSM runs every time**.

| Instruction | Opcode | Operand | With `CONSTANT_Dynamic` |
| --- | --- | --- | --- |
| `ldc` | `0x12` | **1-byte** constant-pool index | Loads a constant of type **other than `long`/`double`** onto the operand stack |
| `ldc_w` | `0x13` | **2-byte** constant-pool index | Same as `ldc`, but supports larger indices |
| `ldc2_w` | `0x14` | **2-byte** constant-pool index | Loads a `long` or `double` constant, including `CONSTANT_Dynamic` with descriptor `J` or `D` |

Bytecode example (`javap -c` format):

```text
0: ldc    #20      // Dynamic #0:CHOSEN:Ljava/lang/String;
2: areturn

0: ldc_w  #20      // Dynamic #0:CHOSEN:Ljava/lang/String;
3: areturn
```

Both instructions above **reference the same entry `#20`** despite having different opcode sizes. When `#20` is resolved to a reference, both instructions receive **that same reference** within the scope of the corresponding class/run-time constant pool.

For an `int` constant, after `ldc`/`ldc_w`, the JVM pushes the `int` value, and the method can return via `ireturn`. For `long` or `double`, `ldc2_w` and returns like `lreturn`/`dreturn` are needed.

**Do not use `ldc_w` just because it is a dynamic constant.** Choosing `ldc` or `ldc_w` is mainly due to the width of the constant-pool index; `ldc2_w` is due to **category 2 types** (`long`/`double`). Both `ldc` and `ldc_w` can validly reference a `CONSTANT_Dynamic` of type `String` or `int`.

### 3.1. When Does the JVM Resolve?

To execute `ldc`, the value of the symbolic reference is needed; if the entry is not yet resolved, the JVM performs resolution according to JVMS `5.4.3` and `5.4.3.6`. In many experiments, the BSM is observed when the corresponding `ldc` instruction is first reached. However, the JVM specification allows some **eager resolution** strategies; therefore, application logic should not depend absolutely on "the BSM can only start at the exact first `ldc` line".

What can be relied upon is the **contract after resolution is chosen**: subsequent resolutions of the same entry return the same result (or the same error state) without re-invoking the BSM just because the code loads the constant again.

### 3.2. A Constant-Pool Entry Is Not a "Factory Call"

If source/bytecode has ten `ldc #20` instructions:

```text
ldc #20
ldc #20
...
ldc #20
```

that **does not** mean the JVM is forced to create ten objects. Resolution belongs to the entry. For a reference constant selected from a BSM, subsequent uses can observe **reference identity** via `==`. In the Java example, the BSM deliberately uses `new String(...)` to avoid confusing the result with an interned string literal; two different methods will obtain the exact same object of the resolved entry.

## 4. The Resolution Process: Obtaining BSM, Invoking BSM, Validating Value

According to JVMS `5.4.3.6`, resolving a dynamically computed constant consists of three stages:

1. **Prepare bootstrap:** resolve the `CONSTANT_MethodHandle` of the BSM; resolve the field descriptor into `Class<?> type`; resolve static bootstrap arguments if any.
2. **Invoke bootstrap method handle:** the JVM provides the caller's `Lookup`, the constant name, `Class<?>` constant type, and static arguments.
3. **Validate result and convert to the constant's type:** the bootstrap result must be convertible to the type `T` declared by the descriptor. If successful, the JVM retains the **selected value** as the resolution result.

Diagram:

```text
ldc/ldc_w/ldc2_w -> symbolic CONSTANT_Dynamic
           |
           v
  Read BSM + name + field descriptor + static args
           |
           v
  Invoke BSM(Lookup, String, Class<?>, ...)
           |
           +-- BSM throws error -----------> resolution FAILED
           |
           v
  Check / convert result to type T
           |
           +-- NPE/CCE during conversion --> BootstrapMethodError, FAILED
           |
           v
  Select and retain value T in the run-time constant pool
           |
           v
  Push T onto stack on each ldc; do not re-run BSM
```

### 4.1. The Bootstrap Result Must Be Compatible with the Descriptor

Example:

```java
// Bootstrap snippet; condy descriptor is Ljava/lang/String;.
return new String("choice-A"); // Valid: String is of the required type.
```

If the BSM returns:

```java
return Integer.valueOf(7); // WRONG if condy requires String.
```

then the JVM performs a conversion equivalent to converting the `Object` result to `String`. Because `Integer` is not a `String`, the conversion raises `ClassCastException`, and resolution fails with **`BootstrapMethodError`**.

This is **different** from a `ClassCastException` occurring when application code itself casts an object successfully loaded from `ldc` to another type. When the descriptor is not satisfied during the bootstrap process itself, the error is at **linkage/resolution**.

### 4.2. A Reference Constant Can Accept `null`

If the condy's field descriptor is a **reference type**, such as `Ljava/lang/String;`, the BSM **can return `null`**. `null` is a valid result of converting to a reference type and is cached as the **selected value**.

```java
// Snippet: condy has descriptor Ljava/lang/String;.
return null; // Valid; subsequent ldc instructions receive the selected null.
```

Afterward, if the application calls a method on the null value, the `NullPointerException` in the application is a **value-usage error**, not a bootstrap-resolution failure.

### 4.3. A Primitive Constant Cannot Accept `null`

If the descriptor is `I` (an `int` constant), the BSM needs to return a value that conversion can turn into `int`, for example `Integer.valueOf(42)`. Returning `null` cannot be unboxed to a primitive; conversion throws `NullPointerException`, and the JVM turns this situation into **`BootstrapMethodError`**.

```java
// Snippet: condy has descriptor I.
return Integer.valueOf(42); // Valid, JVM obtains int 42.
// return null;              // Invalid, conversion to int fails.
```

One should not conclude "a BSM returning null always fails" or "a BSM returning null always becomes a Java null". The outcome **depends on the field descriptor**.

### 4.4. Using a BSM with Static Arguments

A BSM can be used with static metadata, for example:

```java
// Illustrative signature, not a standalone program.
public static Object bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String prefix,
        int version) {
    return prefix + "-" + version;
}
```

The class file must have valid entries in `BootstrapMethods` for the static arguments, and the Method Handle invocation must be compatible. These arguments are **inputs to resolution**, not something that by default causes the BSM to run on every `ldc`. For numeric bootstrap arguments, the specification has appropriate adaptation rules when invoking the bootstrap handle; when writing bytecode manually, the full `5.4.3.6` contract must be followed.

## 5. Caching the Selected Result: Scope, Identity, and External State

### 5.1. Caching Success per Run-Time Constant Pool Entry

Suppose a class loaded by loader `L1` has entry `#20` describing the `String` constant `CHOSEN`. In the experiment:

```text
CondyGenerated.first(): ldc   #20
CondyGenerated.again(): ldc_w #20
```

The BSM returns **`new String("choice-A")`**. Then the code changes the source state to `setting="B"` and calls `again()`. The result is still `choice-A` because `#20` is already resolved. The two results from `first()` and `again()` are the exact same reference, meaning `a == b` evaluates to `true`.

**Do not confuse with Java `String.intern()`:** The BSM creates an independent `new String(...)`, yet the runtime constant pool stores the selected reference. This is **caching by resolution**, not evidence of the String literal pool intervening.

### 5.2. Mutating a Cached Object

If the BSM returns a mutable `List`, the dynamic constant has a compatible descriptor and the JVM caches the **reference to the List**. A caller can modify the contents of the List through that reference if the API allows. Subsequent `ldc` instructions still use the **same reference**, but callers may observe that the List has been modified.

That is an important difference between **"the constant pool value is selected once"** and **"the object is guaranteed immutable"**. In BSM design, it is usually advisable to choose immutable objects for predictable behavior.

### 5.3. Caching per Entry, Not per `ldc` Instruction

This is a point to carefully distinguish from `invokedynamic`:

- With **`CONSTANT_Dynamic`**, once the entry is resolved, different instructions referencing that same entry all get the same result.
- With **`CONSTANT_InvokeDynamic`**, call site resolution is scoped **per individual lexical `invokedynamic` instruction**; two instructions pointing to the same CP entry can still create two independent CallSites.

Topic **14.3** is about **dynamic constants**. Do not mechanically apply the "per individual instruction" rule of `invokedynamic` to `ldc CONSTANT_Dynamic`.

### 5.4. Does a New Class Loader Create a New Value?

Yes, when the same class file bytes are **defined as a new class identity** by a different defining class loader, the new class has its **own run-time constant pool**, and `CONSTANT_Dynamic` needs separate resolution.

That does not mean calling an old `ldc` again resets the cache. In the example, the same class name `CondyGenerated` is loaded by two different `Definer` instances; the second time can select the new value `choice-B`.

### 5.5. A Note on Concurrent Resolutions

If multiple threads touch an unresolved dynamic constant simultaneously, the JVM **may** invoke the bootstrap method handle concurrently; the JVM selects the result of **one execution** and publishes it to the threads. Results of the other bootstrap invocations are discarded. Therefore:

- **Do not rely on the BSM execution count being strictly one in a race situation.**
- Avoid non-idempotent side effects in the bootstrap.
- If the bootstrap accesses shared state, appropriate thread-safety is required.
- What matters is that **one resolution result is published**, not that every thread stores a different value for the same entry.

The following experiment runs **sequentially** so that counts can be accurately verified.

## 6. Resolution Errors: `BootstrapMethodError`, Error Caching, and Other Exceptions

### 6.1. What Does `BootstrapMethodError` Mean?

`BootstrapMethodError` is a subtype of `LinkageError`, under the `Error` branch:

```text
Throwable
 └── Error
      └── LinkageError
           └── BootstrapMethodError
```

This error can appear when the bootstrap or resolving bootstrap arguments fails, or when the BSM returns a result that **cannot be converted to the declared type** of the dynamic constant.

Not every `RuntimeException` arising at an `ldc` instruction is a `BootstrapMethodError`. It is necessary to determine whether the error comes from **resolution/BSM** or from **code using the value after `ldc` has succeeded**.

### 6.2. Bootstrap Throws a Non-`Error` Exception

If the BSM throws:

```java
throw new IllegalStateException("not ready");
```

then the JVMS specifies that resolution fails with `BootstrapMethodError` whose `cause` is the original `IllegalStateException`.

Conversely, if the BSM directly throws an `Error` instance (such as `AssertionError`), the rules do not necessarily wrap it in `BootstrapMethodError`: that `Error` itself can be the resolution error. If **resolving the BSM method handle** or static argument fails even before entering the BSM body, the observed error also depends on the exact resolution stage.

### 6.3. Constant Returning Wrong Type or Primitive Null

Two important errors:

| Requested constant | BSM returns | Result |
| --- | --- | --- |
| `String` | `new String("abc")` | Success, caches reference |
| `String` | `null` | Success, caches `null` |
| `String` | `Integer.valueOf(7)` | `BootstrapMethodError` because conversion hits `ClassCastException` |
| `int` | `Integer.valueOf(42)` | Success, caches value `int 42` |
| `int` | `null` | `BootstrapMethodError` because conversion hits `NullPointerException` |
| `int` | An object that cannot be unboxed/cast appropriately | Conversion failure can lead to `BootstrapMethodError` |

The specific `cause` values in the test program have been verified. When doing general diagnostics, prioritize reading the cause chain rather than assuming every BME must have the same message.

### 6.4. Is There Automatic Retry After Resolution Fails?

**No, for the same symbolic reference that failed.** According to JVMS `5.4.3`:

- Subsequent resolutions of that entry continue to fail with the recorded resolution error.
- The bootstrap method is **not executed again** just because the caller `catch`es the error and tries `ldc` again.
- A flag such as `failReady` changing from `false` to `true` after the failure **cannot rescue the already-failed entry**.
- **Another method** `ldc`-ing the same entry also suffers the cached error; it is not "new method = new constant".

This is a major difference from ordinary business retry mechanisms. Writing a loop:

```java
// WRONG snippet about condy retry strategy.
for (int i = 0; i < 3; i++) {
    try {
        return readDynamicConstant(); // Same CP entry that already failed.
    } catch (BootstrapMethodError ex) {
        // There is no guarantee that BSM will be re-run.
    }
}
```

does not create three bootstrap attempts. If the entry failed on the first pass, subsequent passes only receive the error again. The code above is also only a **Java pseudocode fragment**, not a complete method.

### 6.5. Circular Dependency Error Between Dynamic Constants

`CONSTANT_Dynamic` can appear as a static bootstrap argument of another dynamic constant. A class file can represent a cycle such as:

```text
A: CONSTANT_Dynamic, BSM argument references B
B: CONSTANT_Dynamic, BSM argument references A
```

The JVMS does not allow resolving a dynamically-computed constant that **depends on itself**, directly or indirectly via static bootstrap arguments. When needing to resolve an entry in the cycle again, resolution fails with **`StackOverflowError`**. Do not write a bytecode generator that creates a dependency cycle and expect the JVM to pick a temporary value like `null`.

This differs from valid acyclic dependency graphs; condy-typed static BSM arguments will be resolved according to the rules before the BSM receives the values.

### 6.6. Distinguishing Error Layers

| Symptom | Possible error layer | Inspection hint |
| --- | --- | --- |
| `BootstrapMethodError`, cause `IllegalStateException` | BSM logic threw exception | BSM code, state/config at first resolution |
| `BootstrapMethodError`, cause `ClassCastException` | BSM returned value with wrong reference descriptor | `CONSTANT_NameAndType` field descriptor, type of returned object |
| `BootstrapMethodError`, cause `NullPointerException` | Primitive constant bootstrapped to return null | Descriptor `I`/`J`/... and boxing/unboxing |
| `NoClassDefFoundError` / `IllegalAccessError` | Resolving class, method handle, or module access control | Dependencies, class loader, JPMS, visibility |
| `ClassFormatError` / `VerifyError` | Invalid class file / bytecode | Major version, constant-pool tag/index, Code attribute |
| `StackOverflowError` on cyclic condy dependency | Recursive constant resolution | Static BSM arguments and dependency graph |
| `NullPointerException` from code after loading null reference | **Using the value** that resolved successfully | Is there a null check before calling a method? |
| `InvocationTargetException` when calling generated method via Reflection | Reflection wrapper | `getCause()` to see the `ldc`/application error |

A resolution error does not mean all application errors are "cached forever". Exceptions **occurring after `ldc` has successfully pushed the value** belong to the value-using logic; the `ldc` instruction will continue returning the selected constant next time.

## 7. Self-Generated Class File Experiment: `ldc`, `ldc_w`, and Cached Results

### 7.1. Experiment Description

We will generate a runtime class named **`CondyGenerated`** from a `byte[]` with **classfile major version 55**. This class needs no corresponding Java source, and has ten public static methods:

| Method | Dynamic constant used | Purpose |
| --- | --- | --- |
| `first()` | `CHOSEN`, `ldc` | Selects `choice-A` the first time |
| `again()` | **same `CHOSEN`**, `ldc_w` | Receives the same reference even though `setting` changed |
| `fail()` | `FAIL` | BSM throws `IllegalStateException` |
| `failAgain()` | **same `FAIL`** | Proves the error is cached across two methods |
| `nullable()` | `NULL` of type `String` | BSM validly selects `null` |
| `nullAgain()` | **same `NULL`** | `null` remains cached even though BSM could return another value later |
| `wrong()` | `WRONG` of type `String` | BSM returns `Integer`, causing conversion error |
| `number()` | `INT` of type `int` | BSM returns wrapper `Integer(42)`, converted to primitive |
| `numberAgain()` | **same `INT`** | Proves caching of primitive |
| `nullNumber()` | `NULL_INT` of type `int` | Returns null for primitive, causing `BootstrapMethodError` |

Each constant-pool entry has its own name or is intentionally shared. Different modes are selected by the `name` parameter of the same BSM to easily track and measure **the number of times the bootstrap runs**.

### 7.2. Complete Java 17+ Code

Create the file **`CondyResolutionLab.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class CondyResolutionLab {
    private static String setting = "A";
    private static boolean failReady;
    private static boolean nullAllowed = true;
    private static int chosenRuns, failRuns, nullRuns, wrongRuns, intRuns, nullIntRuns;

    public static Object bootstrap(MethodHandles.Lookup caller,
                                   String name, Class<?> type) {
        return switch (name) {
            case "CHOSEN" -> {
                chosenRuns++;
                yield new String("choice-" + setting);
            }
            case "FAIL" -> {
                failRuns++;
                if (!failReady) throw new IllegalStateException("not ready");
                yield "recovered";
            }
            case "NULL" -> {
                nullRuns++;
                yield nullAllowed ? null : "later-value";
            }
            case "WRONG" -> {
                wrongRuns++;
                yield Integer.valueOf(7); // Required: String, actual: Integer
            }
            case "INT" -> {
                intRuns++;
                yield Integer.valueOf(42);
            }
            case "NULL_INT" -> {
                nullIntRuns++;
                yield null; // primitive int cannot be null
            }
            default -> throw new IllegalArgumentException(name);
        };
    }

    static final class Pool {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private final DataOutputStream out = new DataOutputStream(bytes);
        private int nextIndex = 1;

        int utf(String value) throws IOException {
            int i = nextIndex++;
            out.writeByte(1);
            out.writeUTF(value);
            return i;
        }

        int clazz(int name) throws IOException {
            int i = nextIndex++;
            out.writeByte(7);
            out.writeShort(name);
            return i;
        }

        int nat(int name, int descriptor) throws IOException {
            int i = nextIndex++;
            out.writeByte(12);
            out.writeShort(name);
            out.writeShort(descriptor);
            return i;
        }

        int methodRef(int owner, int nat) throws IOException {
            int i = nextIndex++;
            out.writeByte(10);
            out.writeShort(owner);
            out.writeShort(nat);
            return i;
        }

        int methodHandle(int refKind, int ref) throws IOException {
            int i = nextIndex++;
            out.writeByte(15);
            out.writeByte(refKind);
            out.writeShort(ref);
            return i;
        }

        int dynamic(int bsmIndex, int nameAndType) throws IOException {
            int i = nextIndex++;
            out.writeByte(17);
            out.writeShort(bsmIndex);
            out.writeShort(nameAndType);
            return i;
        }

        void writeTo(DataOutputStream target) throws IOException {
            target.writeShort(nextIndex);
            target.write(bytes.toByteArray());
        }
    }

    record GeneratedMethod(int name, int descriptor, int constant,
                           boolean wide, int returnOpcode) {}

    static final class Definer extends ClassLoader {
        Definer() {
            super(CondyResolutionLab.class.getClassLoader());
        }

        Class<?> define(byte[] bytes) {
            return defineClass("CondyGenerated", bytes, 0, bytes.length);
        }
    }

    private static byte[] generate() throws IOException {
        Pool cp = new Pool();

        int thisClass = cp.clazz(cp.utf("CondyGenerated"));
        int superClass = cp.clazz(cp.utf("java/lang/Object"));
        int code = cp.utf("Code");
        int bootstrapMethods = cp.utf("BootstrapMethods");
        int host = cp.clazz(cp.utf("CondyResolutionLab"));
        int bootstrapName = cp.utf("bootstrap");
        int bootstrapDesc = cp.utf(
                "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;");
        int ref = cp.methodRef(host, cp.nat(bootstrapName, bootstrapDesc));
        int bsmHandle = cp.methodHandle(6, ref); // REF_invokeStatic

        int stringDesc = cp.utf("Ljava/lang/String;");
        int intDesc = cp.utf("I");
        int stringMethod = cp.utf("()Ljava/lang/String;");
        int intMethod = cp.utf("()I");

        int chosen = cp.dynamic(0, cp.nat(cp.utf("CHOSEN"), stringDesc));
        int fail = cp.dynamic(0, cp.nat(cp.utf("FAIL"), stringDesc));
        int nullable = cp.dynamic(0, cp.nat(cp.utf("NULL"), stringDesc));
        int wrong = cp.dynamic(0, cp.nat(cp.utf("WRONG"), stringDesc));
        int primitive = cp.dynamic(0, cp.nat(cp.utf("INT"), intDesc));
        int nullPrimitive = cp.dynamic(
                0, cp.nat(cp.utf("NULL_INT"), intDesc));

        List<GeneratedMethod> methods = List.of(
            new GeneratedMethod(
                    cp.utf("first"), stringMethod, chosen, false, 0xb0),
            new GeneratedMethod(
                    cp.utf("again"), stringMethod, chosen, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("fail"), stringMethod, fail, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("failAgain"), stringMethod, fail, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("nullable"), stringMethod, nullable, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("nullAgain"), stringMethod, nullable, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("wrong"), stringMethod, wrong, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("number"), intMethod, primitive, true, 0xac),
            new GeneratedMethod(
                    cp.utf("numberAgain"), intMethod, primitive, true, 0xac),
            new GeneratedMethod(
                    cp.utf("nullNumber"), intMethod, nullPrimitive, true, 0xac)
        );

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(55); // Java 11+, CONSTANT_Dynamic supported
        cp.writeTo(out);
        out.writeShort(0x0021); // public | super
        out.writeShort(thisClass);
        out.writeShort(superClass);
        out.writeShort(0); // interfaces
        out.writeShort(0); // fields
        out.writeShort(methods.size());

        for (GeneratedMethod m : methods) {
            out.writeShort(0x0009); // public static
            out.writeShort(m.name());
            out.writeShort(m.descriptor());
            out.writeShort(1); // one Code attribute
            out.writeShort(code);
            int length = m.wide() ? 4 : 3;
            out.writeInt(12 + length);
            out.writeShort(1); // maxStack
            out.writeShort(0); // maxLocals
            out.writeInt(length);
            out.writeByte(m.wide() ? 0x13 : 0x12); // ldc_w / ldc
            if (m.wide()) out.writeShort(m.constant());
            else out.writeByte(m.constant());
            out.writeByte(m.returnOpcode());
            out.writeShort(0); // exception table
            out.writeShort(0); // nested code attributes
        }

        out.writeShort(1); // class attributes
        out.writeShort(bootstrapMethods);
        out.writeInt(6);
        out.writeShort(1); // one bootstrap entry
        out.writeShort(bsmHandle);
        out.writeShort(0); // no static arguments
        out.flush();
        return bytes.toByteArray();
    }

    private static Object call(Class<?> owner, String method) throws Throwable {
        Method m = owner.getMethod(method);
        try {
            return m.invoke(null);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = generate();
        Files.write(Path.of("CondyGenerated.class"), bytes);
        Class<?> c1 = new Definer().define(bytes);

        Object a = call(c1, "first");
        System.out.println("first=" + a);
        setting = "B";
        Object b = call(c1, "again");
        System.out.println("again=" + b);
        System.out.println("same identity=" + (a == b));
        System.out.println("chosen calls=" + chosenRuns);

        try {
            call(c1, "fail");
        } catch (BootstrapMethodError ex) {
            System.out.println("fail=" + ex.getClass().getSimpleName());
            System.out.println("fail cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        failReady = true;
        try {
            call(c1, "failAgain");
        } catch (BootstrapMethodError ex) {
            System.out.println("retry=" + ex.getClass().getSimpleName());
        }
        System.out.println("failed bootstrap calls=" + failRuns);

        System.out.println("nullable first=" + call(c1, "nullable"));
        nullAllowed = false;
        System.out.println("nullable again=" + call(c1, "nullAgain"));
        System.out.println("null bootstrap calls=" + nullRuns);

        try {
            call(c1, "wrong");
        } catch (BootstrapMethodError ex) {
            System.out.println("wrong=" + ex.getClass().getSimpleName());
            System.out.println("wrong cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("wrong bootstrap calls=" + wrongRuns);

        System.out.println("number=" + call(c1, "number"));
        System.out.println("number again=" + call(c1, "numberAgain"));
        System.out.println("integer bootstrap calls=" + intRuns);

        try {
            call(c1, "nullNumber");
        } catch (BootstrapMethodError ex) {
            System.out.println("null int=" + ex.getClass().getSimpleName());
            System.out.println("null int cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("null int bootstrap calls=" + nullIntRuns);

        Class<?> c2 = new Definer().define(bytes);
        System.out.println("new loader=" + call(c2, "first"));
        System.out.println("chosen calls after reload=" + chosenRuns);
    }
}
```

**Explanation of the code parts:**

- `Pool` writes constant-pool entries with tags matching the JVM format: UTF8 (`1`), Class (`7`), NameAndType (`12`), Methodref (`10`), MethodHandle (`15`), Dynamic (`17`).
- `Pool.dynamic(...)` writes the bootstrap-table index and name-and-type index, **not** containing the resolved value.
- `methodHandle(6, ref)` uses reference kind `REF_invokeStatic` to point to the BSM.
- `generate()` creates a **major 55** classfile, sufficient to support `CONSTANT_Dynamic`, with `BootstrapMethods` pointing to the BSM.
- `GeneratedMethod` simply describes a very short method: `ldc` or `ldc_w` followed by `areturn`/`ireturn`. There are no conditional branches or exception handlers in the generated bytecode.
- `call(...)` uses Reflection to invoke methods on the generated class; `InvocationTargetException` is unwrapped so the lesson can print the **actual JVM error**.
- `Definer` creates a separate class identity for each defining class loader; this is the tool for observing each class's own cache.

The example is a **complete program**, not pseudocode. It can be run with `javac`/`java` from **JDK 17 or later** without needing `--add-opens`/`--add-exports`.

### 7.3. Compiling and Running

From the directory containing `CondyResolutionLab.java`:

```bash
javac CondyResolutionLab.java
java CondyResolutionLab
```

The program also writes `CondyGenerated.class` to the working directory so you can inspect it yourself with `javap`.

**Exact stdout verified by an actual run:**

```text
first=choice-A
again=choice-A
same identity=true
chosen calls=1
fail=BootstrapMethodError
fail cause=IllegalStateException
retry=BootstrapMethodError
failed bootstrap calls=1
nullable first=null
nullable again=null
null bootstrap calls=1
wrong=BootstrapMethodError
wrong cause=ClassCastException
wrong bootstrap calls=1
number=42
number again=42
integer bootstrap calls=1
null int=BootstrapMethodError
null int cause=NullPointerException
null int bootstrap calls=1
new loader=choice-B
chosen calls after reload=2
```

**Conditions for the result:** the program intentionally runs **sequentially** and on the tested JDK. If a JVM performs eager resolution or executes concurrently in another environment, bootstrap timing may differ; the JVM resolution rules remain the standard to follow. In the run performed, the 22 lines of stdout above are deterministic and contain no random class loader names.

### 7.4. Using `javap` to Inspect That the Class File Actually Has Condy

Run next:

```bash
javap -v -c CondyGenerated.class
```

In the output, look for:

```text
major version: 55
#20 = Dynamic  #0:#19  // CHOSEN:Ljava/lang/String;
#23 = Dynamic  #0:#22  // FAIL:Ljava/lang/String;
#26 = Dynamic  #0:#25  // NULL:Ljava/lang/String;
#29 = Dynamic  #0:#28  // WRONG:Ljava/lang/String;
#32 = Dynamic  #0:#31  // INT:I
#35 = Dynamic  #0:#34  // NULL_INT:I

first():      ldc    #20
again():      ldc_w  #20
fail():       ldc_w  #23
failAgain():  ldc_w  #23
nullable():   ldc_w  #26
nullAgain():  ldc_w  #26
wrong():      ldc_w  #29
number():     ldc_w  #32
numberAgain():ldc_w  #32
nullNumber(): ldc_w  #35
```

This is an **excerpt from `javap`**, not verbatim every line: the actual output also has method declarations, flags, constant-pool descriptions, and the `BootstrapMethods` attribute. The indices `#20`, `#23`, `#26`, `#29`, `#32`, `#35` are confirmed from the classfile of this experiment's code.

In particular, `first` and `again` use the same `#20`; `fail` and `failAgain` use the same `#23`. That is bytecode-level evidence of **two different methods referencing the same dynamic constant pool entry**.

## 8. Explaining the Results: Why Didn't the BSM Run Again?

### 8.1. `CHOSEN`: Same Selected Reference

`first()` loads `#20` when `setting="A"`; the BSM runs once and creates `new String("choice-A")`. `again()` uses the same `#20` after `setting="B"`:

```text
first=choice-A
again=choice-A
same identity=true
chosen calls=1
```

The result is not `choice-B` because the BSM was not called again. `same identity=true` also proves the JVM retained **the exact reference** that was selected, not just a new string with equal content.

### 8.2. `FAIL`: Error Is Stored per Entry, Even Across Another Method

`fail()` uses `#23` when `failReady=false`. The BSM increments the counter and throws `IllegalStateException("not ready")`. The JVM reports `BootstrapMethodError`.

Then `failReady=true`, yet `failAgain()`, a **different** method using the same `#23`, still receives the resolution error:

```text
fail=BootstrapMethodError
fail cause=IllegalStateException
retry=BootstrapMethodError
failed bootstrap calls=1
```

Key distinction: **the error is recorded for the `CONSTANT_Dynamic` entry**. There is no "separate BSM per `ldc` bytecode" when two `ldc` instructions reference that same entry.

If you need to retry the bootstrap after fixing configuration, one way to verify is to create a **new class identity** or run a **new JVM**; do not treat `catch` and repeating the method as a solution.

### 8.3. `NULL`: Null Reference Is a Cached Value

Entry `#26` has descriptor `String`. The BSM returns null the first time; `nullAllowed` then switches to false, but calling via `nullAgain()` still retrieves the cached null:

```text
nullable first=null
nullable again=null
null bootstrap calls=1
```

This is a **successful resolution**, not a failed state. `null` is valid for a reference type. Depending on business logic, the caller receiving null may then need to check for null before using it.

### 8.4. `WRONG`: Returning the Wrong Type Is Caught at the Resolution Stage

`wrong()` loads entry `#29`, descriptor `String`; the BSM returns `Integer.valueOf(7)`. Conversion to `String` fails:

```text
wrong=BootstrapMethodError
wrong cause=ClassCastException
wrong bootstrap calls=1
```

The application never receives an `Integer` from `ldc` and only then casts it itself. The JVM checked the bootstrap result **before the load-constant instruction could complete**.

### 8.5. `INT`: Cached Primitive Constant

Entry `#32` declares type `int`, and the BSM returns `Integer.valueOf(42)`. The JVM converts it to the primitive value and stores the result:

```text
number=42
number again=42
integer bootstrap calls=1
```

Unlike the `String` reference, the test here observes the **same `int` value** and **bootstrap counter** rather than using `==` on boxed Integer to prove identity (Java's Integer caching could be misleading).

### 8.6. `NULL_INT`: Primitive Null Leads to `BootstrapMethodError`

Entry `#35` has field descriptor `I`. The BSM returns null; conversion cannot unbox to primitive:

```text
null int=BootstrapMethodError
null int cause=NullPointerException
null int bootstrap calls=1
```

This is an error of **invalid bootstrap value for the declared type**, not a caller error accessing a null object after a successful `ldc`.

### 8.7. New Defining Loader: New Constant Pool

The final part creates a new `Definer`, redefining the **same bytecode** under a different class identity. `setting` is still `"B"`:

```text
new loader=choice-B
chosen calls after reload=2
```

The `CHOSEN` constant of the **new** class is resolved to the new value. That **does not clear or change the `choice-A` value** cached in the old class. If you continue calling `first()` on `c1`, it still returns the original value, without re-selecting `choice-B`.

## 9. Distinguishing Condy from `invokedynamic` to Avoid Misunderstanding Caching

Both mechanisms use a bootstrap and the constant pool; however, **what the JVM remembers after resolution differs**:

| Property | Dynamic constant (`condy`) | `invokedynamic` |
| --- | --- | --- |
| CP entry | `CONSTANT_Dynamic`, tag `17` | `CONSTANT_InvokeDynamic`, tag `18` |
| Descriptor | Field descriptor `String`/`int`/`long`... | Method descriptor such as `(String)int` |
| "type" kind received by BSM | `Class<?>` | `MethodType` |
| BSM must return | **Value** compatible with type | **CallSite** matching method type |
| Bytecode | `ldc`, `ldc_w`, `ldc2_w` | `invokedynamic` |
| Cache scope | One symbolic reference in the **run-time constant pool** | **Per lexical instruction** |
| Two opcodes same CP entry | Share the condy result | Can have independently linked CallSites |
| BSM returns null | Can be valid for reference constant | Not a valid CallSite |
| After failure | Does not automatically re-invoke BSM for the same entry | Does not automatically re-invoke BSM for the same instruction |

A common mistake is seeing two `invokedynamic` instructions pointing to the same constant-pool entry being able to link differently, and applying that conclusion to `ldc #20`. **Incorrect.** Two `ldc` instructions of the same class pointing to one `CONSTANT_Dynamic #20` share the resolution result, like `first()/again()` in the example.

Conversely, do not assume every use of a lambda (often involving `invokedynamic`) will return the same lambda object just because the call site is cached; the call site can be a **factory target** invoked multiple times. With condy, **the value itself** is selected and stored in the constant pool. This is the contract difference between the two kinds of bootstraps.

## 10. Edge Cases When Writing Classfiles or Bootstraps

### 10.1. `ldc2_w` for `long` and `double`

If `CONSTANT_Dynamic` has field descriptor `J` or `D`, emit **`ldc2_w`** instead of `ldc` or `ldc_w`. Illustrative example in disassembly form:

```text
#60 = Dynamic #0:#59 // COMPUTED_LONG:J

0: ldc2_w #60
3: lreturn
```

Line `#60` is a **standalone hypothetical example**, not in the classfile of the program in section 7. A BSM returning `Long.valueOf(123456789L)` compatible with descriptor `J` can supply the `long` value for `ldc2_w` to push onto the operand stack.

Note: `ldc_w` has a 2-byte index but still **does not** substitute for `ldc2_w` when the constant type is `long`/`double`. "Wide" index and "category 2 value" are **two different concepts**.

### 10.2. Wrong Version, Tag, or Descriptor

`CONSTANT_Dynamic` requires classfile support from Java 11 (major version **55**). If a generator uses a classfile version that is too old yet writes tag `17`, the JVM may report `ClassFormatError` or the corresponding classfile error **before the BSM has a chance to run**.

Check:

```bash
javap -v -c CondyGenerated.class
```

Look for major version, `Dynamic`, `BootstrapMethods`, and `ldc` instructions. If `javap` cannot parse the file, check the constant-pool entry count, `Code.attribute_length`, method descriptors, and u1/u2 fields; do not assume the error comes from bootstrap logic.

### 10.3. Mutually Dependent Bootstrap Arguments

A static bootstrap argument can be another condy; it must be resolved according to the rules before the outer BSM receives the value. If the dependency does not exist, has the wrong type, or forms a cycle, the outer BSM may fail to run.

When debugging a BSM where "no logs appear", do not inspect only the BSM body. The JVM may be failing **during argument / bootstrap method handle resolution** before entering the code.

### 10.4. Which Object Is the Reference Result?

A BSM can return:

- An immutable object (usually easiest to use).
- A Class mirror, MethodHandle, VarHandle, or objects matching the field descriptor.
- A mutable object (callers can observe internal mutations, but the cached reference remains the selected reference).
- Null for a reference descriptor.

There is **one selected resolution value** per entry. That does not mean all references to content of the same name across different classes/different loaders are interned into a global singleton.

### 10.5. A BSM Is Not a Per-Use Constructor

If you need **a new object every time a caller invokes a method**, do not use condy to call `new` via bootstrap and expect `ldc` to do that repeatedly. One bootstrap creates one object and caches it; subsequent `ldc` instructions **reuse the reference**. For a per-call factory need, use a regular method/factory call or an appropriate `MethodHandle`/`invokedynamic` target.

### 10.6. Do Not Rely on Retrying a Transient Bootstrap Error

A BSM is not suited for transient errors that could recover at the same entry via automatic retry. For example, if a BSM reads the network and throws an I/O exception on the first resolution, the entry can become "frozen" in error. If business logic must recover, design the BSM to **return a stable valid result** (e.g., an immutable handle to a service) and place retry logic at the usage layer; or redesign where initialization happens.

Having the BSM fall back to a dummy value also carries risk: the dummy value could be **cached long-term** as the official result. Do not hide serious configuration errors just to avoid `BootstrapMethodError`.

## 11. Diagnostic Workflow for `BootstrapMethodError` on `ldc`

When encountering a runtime error related to condy, go through the checklist:

1. **Record class identity and Java version.** Which class contains `ldc`? Which loader defined it? Is there a custom loader/agent/bytecode transformer?
2. **Inspect actual bytecode with `javap -v -c`.** Confirm there is `CONSTANT_Dynamic` tag `17`, correct field descriptor, bootstrap method handle index, and matching `BootstrapMethods`.
3. **Read the cause chain accurately.** `BootstrapMethodError.getCause()` may reveal `IllegalStateException`, `ClassCastException`, `NullPointerException`. If invoked via Reflection, `InvocationTargetException` is a wrapper at another layer.
4. **Determine whether the BSM has run.** The error may come from resolving the method handle, class descriptor, or static arguments before the BSM body.
5. **Check return type and null.** Reference can be null; primitive cannot. Does the returned object match `Class<?> type`?
6. **Distinguish first-time resolution from reuse.** A BSM counter staying still after an error is not a logger issue; it may be the cached failed resolution state.
7. **If the root cause is fixed, test in a new class/JVM.** Do not use the same failed entry to conclude the fix does not work.
8. **Check concurrency.** Multiple BSM executions on a contested first access are permitted by JVMS; test sequentially before analyzing races.
9. **Do not confuse with `invokedynamic`.** With condy, the result is cached per entry, not per `ldc` opcode.
10. **Only change code at the right layer.** If the classfile is invalid, fix the generator; if the BSM has the wrong type, fix the BSM; if the target application misuses null, fix the caller; if the class loader causes incompatibility, fix the runtime graph.

### 11.1. Symptoms and Quick Fixes

| Observation | Interpretation | Fix |
| --- | --- | --- |
| `first()` and `again()` always return the same String even when config changes | Same dynamic CP entry already resolved | If it needs to change over time, do not represent it as a condy cached value |
| `failAgain()` still throws BME after `failReady=true` | Failed resolution is cached | Use a new class/JVM identity when verifying; fix the BSM for the initial link |
| String constant from BSM has value null | Valid reference-null resolution | Caller handles null itself; this is not inherently a linkage failure |
| int constant returning null leads to BME | Primitive conversion does not accept null | BSM must return a valid unboxable value |
| `ClassCastException` is in BME's cause | Object returned by BSM has wrong declared type | Check `NameAndType` descriptor and bootstrap result |
| No log seen from BSM | May have failed during BSM/argument resolution | Inspect classfile, cause, access control |
| `StackOverflowError` during resolution | Cyclic condy dependency | Make static arguments acyclic |
| Loading the same class with a new loader gives a different result | Pool of the new class identity | Do not mistake this for a retry in the old class |
| `ldc_w` emitted for descriptor `J` | Wrong instruction category | Use `ldc2_w` |
| A method wants a new object each time but receives the same object | `ldc` is using condy cached reference | Use a factory/method call instead of condy |

## 12. Designing Safe, Deterministic, and Testable Bootstraps

A high-quality BSM should:

- **Validate `name` and `type` early.** Do not ignore the field descriptor and return an arbitrary object. You can proactively throw an exception describing a bad config, while understanding that error will affect resolution and subsequent uses.
- **Minimize side effects:** startup metrics, file writes, network, or mutating global state inside a BSM are harder to predict because the JVM may resolve eagerly, or run multiple concurrent invocations.
- **Return immutable values when appropriate** so that caching the result does not carry unintended mutable state.
- **Avoid transient dependencies:** if a service/config is not ready yet, consider separating actual initialization into an API with retry, rather than letting condy resolution fail.
- **Check access permissions** when using `MethodHandles.Lookup` from the caller. A BSM does not automatically open modules/private members.
- **Do not ignore error causes:** when logging BME, record `getCause()`, class loader, and matching NameAndType, avoiding losing track of type/loading mismatches.
- **Test both cached success and cached failure:** use two methods sharing the same CP entry, change state after resolution, and measure BSM call counts.
- **Test new class identity:** if a test needs to reset linkage state, use a new loader within a safe scope or launch a new JVM; do not look for a nonexistent "clear cache".

### 12.1. A Design Question Before Using Condy

Ask yourself: **"Should this value be chosen once per defining class/run-time constant pool, or recomputed on every use?"**

- If **chosen once**, condy fits the goal of representing constant resolution.
- If **recomputed from runtime data**, a method/factory call or a target with dynamic logic is more suitable.
- If **chosen once but can fail transiently**, the failure policy and initialization timing must be designed very carefully, because failed resolution does not automatically retry.

## 13. Self-Check Exercises and Solutions

**Question 1.** A class has two `ldc #20` instructions referencing the same `CONSTANT_Dynamic`. The first time, the BSM returns `new String("A")`. Must both instructions run the BSM separately?  
**Answer:** No. Once the entry has resolved successfully, other uses of the same run-time constant-pool reference receive the same selected value.

**Question 2.** If a global variable is changed from `A` to `B` after `#20` resolves, what does the next `ldc #20` receive?  
**Answer:** Still the selected value `A` because the BSM does not automatically re-run; condy caching does not track global variable changes.

**Question 3.** Do `ldc #20` and `ldc_w #20` have different resolution scopes?  
**Answer:** No. They only differ in the width of the constant-pool index in the instruction; referencing the same `#20` means using the same resolved result.

**Question 4.** A condy has descriptor `Ljava/lang/String;`, and the BSM returns null. Does linking fail?  
**Answer:** No. Null can be a valid reference constant, and it is cached.

**Question 5.** A condy has descriptor `I`, and the BSM returns null. What does the JVM report?  
**Answer:** Conversion to primitive `int` causes `NullPointerException`; resolution reports `BootstrapMethodError`. The experimental example confirms the cause is NPE.

**Question 6.** A `String` condy receives `Integer.valueOf(7)` from the BSM. Does `ldc` return Integer and let the caller cast it?  
**Answer:** No. The bootstrap result does not satisfy the field descriptor, so conversion hits `ClassCastException` and the JVM reports `BootstrapMethodError` at resolution.

**Question 7.** The BSM throws `IllegalStateException` the first time; the caller flips a flag and calls another method that also uses the same `CONSTANT_Dynamic`. Does the BSM run again?  
**Answer:** No. Failed resolution of the same entry is retained. `fail` and `failAgain` in the experiment share one CP entry.

**Question 8.** A bootstrap returns a mutable `StringBuilder`. Do subsequent `ldc` instructions receive a new StringBuilder?  
**Answer:** No, due to caching of the same entry. Callers can observe mutated internal state if the object is mutable and shared.

**Question 9.** The same classfile is defined by a new loader. Can it receive a new bootstrap value?  
**Answer:** Yes. A different class identity has its own run-time constant pool. This is not resetting the old class's cache.

**Question 10.** Can the BSM run twice concurrently when two threads simultaneously resolve an entry that does not yet have a value?  
**Answer:** Yes. The JVMS allows concurrent bootstrap invocations and picks only one result to publish, so BSM side effects must be thread-safe/idempotent when needed.

**Question 11.** Should a `long`-typed `CONSTANT_Dynamic` use `ldc_w` or `ldc2_w`?  
**Answer:** `ldc2_w` with descriptor `J`; the different opcode is not just about large/small indices.

**Question 12.** Condy A uses B as a static BSM argument, and B depends on A. How does the JVMS handle this?  
**Answer:** Resolution does not support dependency cycles; needing to re-resolve a constant currently being resolved leads to `StackOverflowError`.

**Question 13.** Why can't the `invokedynamic` rule of "two instructions with the same constant-pool entry still link separately" be applied to `ldc`?  
**Answer:** Because `invokedynamic` caches CallSites separately per lexical instruction, whereas `CONSTANT_Dynamic` caches the value per run-time constant-pool symbolic reference.

**Question 14.** A BSM throws `AssertionError`. Is it guaranteed that `BootstrapMethodError`'s `getCause()` will be `AssertionError`?  
**Answer:** No. According to the JVMS, an `Error` thrown directly from a BSM can become the resolution error without necessarily being wrapped in `BootstrapMethodError`.

## 14. Summary and References

A concise way to remember:

```text
CONSTANT_Dynamic (field descriptor) + BootstrapMethods
                   |
                   v
      Resolve BSM + static arguments
                   |
                   v
      BSM(Lookup, name, Class<?>, ...)
                   |
                   v
      Convert result to declared type
          /                         \
      success                     failure
          |                         |
      cache VALUE               cache ERROR
          |                         |
ldc/ldc_w/ldc2_w              reusing again
all get VALUE                 does not retry BSM
```

**Key points to remember:**

- `CONSTANT_Dynamic` contains a **symbolic recipe**, not the actual result before resolution.
- `ldc`/`ldc_w` load constants other than `long`/`double`; `ldc2_w` is used for `long`/`double`, including corresponding condy entries.
- Success: the JVM **caches the selected value** per run-time constant-pool entry and does not re-invoke the bootstrap for subsequent uses.
- Failure: the JVM retains the **resolution error**; retrying the same entry does not run the bootstrap again.
- `null` is valid for reference types but invalid for primitive types.
- A BSM returning an object that does not match the field descriptor causes `BootstrapMethodError` in the conversion step.
- A **new class loader** creates a new class identity/constant pool; **concurrency** can cause multiple concurrent bootstrap executions on initial resolution.
- Do not confuse condy's **per-entry** caching with `invokedynamic`'s **per-lexical-instruction** caching.

**Official references (Java 17):**

- [JVMS `5.4.3 Resolution and `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): bootstrap algorithm, conversion, success/failure caching, concurrency, and dependency cycles.
- [JVMS `4.4.10 `CONSTANT_Dynamic_info` and `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile format, tags `17`/`18`, and field/method descriptors.
- [JVMS `6 `ldc`, `ldc_w`, `ldc2_w`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): operand widths, constant types, and linking exceptions.
- [Oracle Java SE 17 — `BootstrapMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html): meaning of bootstrap errors for dynamic constants and `invokedynamic`.
- [Oracle Java SE 17 — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): built-in bootstrap methods for dynamic constants and standard use cases.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): using `-c` to view bytecode and `-v` to view the constant pool/BootstrapMethods.
