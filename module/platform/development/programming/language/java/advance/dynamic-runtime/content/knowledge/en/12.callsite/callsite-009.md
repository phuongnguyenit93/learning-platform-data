# 12.9 Distinguishing target replacement from re-linking an already-linked `invokedynamic` instruction

**An `invokedynamic` instruction that has already been linked to a `CallSite` object does not return to an unlinked state just because the `CallSite`'s target changes.** With `MutableCallSite` or `VolatileCallSite`, you can replace the target `MethodHandle` using `setTarget(...)`; subsequent calls go through that same linked call site and use the new target according to the update-visibility rules of the call site type. The JVM **does not re-invoke the bootstrap method** to perform a `setTarget` action.

This lesson clarifies the boundary between **`invokedynamic` instruction linkage** (connecting an instruction site to a `CallSite`) and **`CallSite` target replacement** (retargeting, replacing a `MethodHandle` inside the call site). These are two different mechanisms, even though in the documentation of some dynamic-language runtimes, target replacement may be called “relink” in the sense of **application logic**.

> **Environment:** Java 17+. The four standalone Java programs at the end of the hands-on sections were tested with `javac --release 17` and executed successfully; in particular, the advanced example generates a class file containing an **actual `invokedynamic` opcode**, not just calling `CallSite.dynamicInvoker()`. Target update scenarios in the sample code are run sequentially for deterministic output. When deploying in a multithreaded environment, appropriate memory visibility rules must be added.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish **a single linkage of an `invokedynamic` instruction site** from **multiple changes of `CallSite.target`** on the same linked site.
- Explain the roles of `CONSTANT_InvokeDynamic`, `BootstrapMethods`, `Lookup`, `invokedName`, `MethodType`, and `CallSite` in the lifecycle of a dynamic call site.
- Know when the JVM runs the bootstrap method and why calling the same instruction site again after it has been linked **does not** trigger the bootstrap again.
- Compare `ConstantCallSite`, `MutableCallSite`, and `VolatileCallSite`; explain the meaning of `MutableCallSite.syncAll(...)` and update visibility across threads.
- Distinguish `site.getTarget()` (obtaining a specific handle at the time of reading) from `site.dynamicInvoker()` (a handle that can invoke according to the **current target**).
- Avoid misinterpreting `setTarget`, `syncAll`, `SwitchPoint.invalidateAll`, and the term “relink” in frameworks.
- Identify `MethodType` constraints, `WrongMethodTypeException` errors, in-flight invocations, and scenarios where bootstrap is executed concurrently during initial linkage.
- Read the output from a self-generated class file to see that **the bootstrap count does not increase** even though the `invokedynamic` opcode continues to invoke the new target.

## 2. Two distinct axes: `CallSite` identity and target value

Imagine the state of an instruction site:

```text
Class file: a specific invokedynamic instruction
    |
    | constant pool: invokedName + method descriptor
    | BootstrapMethods: bootstrap handle + static arguments
    |
    v
UNLINKED
    |
    | JVM resolves metadata, invokes bootstrap, receives CallSite
    v
LINKED -----> CallSite S  (S's identity is bound to the instruction site)
                type = (String)String   [fixed]
                target = T0            [mutable depending on subclass]
                    |
                    | S.setTarget(T1)  (if mutable/volatile)
                    v
                target = T1
                    |
                    | S.setTarget(T2)
                    v
                target = T2

Instruction site: still LINKED to the exact same S; does not run bootstrap again.
```

Distinguish clearly:

1. **Instruction linkage:** The JVM links an **`invokedynamic` bytecode site** to **a `CallSite` object** returned by the bootstrap. After successful linkage, this association is fixed according to the JVMS contract.
2. **Target value inside `CallSite`:** is a `MethodHandle` with the same `MethodType` as the call site. Some `CallSite` types allow replacing this handle.
3. **Execution behavior:** when the call site runs, the invocation is dispatched to the target according to the call site's state and the consistency semantics of the call site type. The target method executed can change even though the class file structure, opcode location, and call site identity remain unchanged.

**Key takeaway:** “a permanently linked instruction” does not mean “the method implementation executed at that instruction must permanently be the same `MethodHandle`” if the bootstrap returned a `MutableCallSite` or `VolatileCallSite`.

### 2.1. Do not equate “linked” with “immutable target”

Examples of accurate phrasing:

- “The `invokedynamic` instruction remains linked to `MutableCallSite S`, but `S` now points to a new target.”
- “The target changes after `setTarget`; the bootstrap method does not run again.”
- “A `ConstantCallSite` does not allow changing the target, but that is the policy of the **call site type**.”
- “`syncAll` publishes target updates across threads; it does not reset the bytecode linkage state.”

Phrasing that easily causes misunderstanding:

- “`setTarget` causes the JVM to unlink and invoke the bootstrap again.”
- “After the first time, `invokedynamic` always calls the same original method in all cases.”
- “`VolatileCallSite` relinks continuously because it has to read the target every time.”
- “Creating a `CallSite` with a Java constructor immediately creates an `invokedynamic` opcode.”

## 3. Lifecycle of linking an `invokedynamic` instruction

At the class file level, the operand of `invokedynamic` points to a `CONSTANT_InvokeDynamic_info` in the constant pool. This entry contains an index into a `BootstrapMethods` entry and a `NameAndType` reference having the **call site name** and **JVM method descriptor**.

Conceptual flow:

```text
Before first execution:
  invokedynamic instruction -> UNLINKED

When execution is needed:
  1. Resolve symbolic name and method type from the constant pool.
  2. Resolve bootstrap method handle and static arguments.
  3. Invoke bootstrap(caller Lookup, invokedName, invokedType, ...staticArgs).
  4. Bootstrap returns CallSite S whose type matches invokedType.
  5. JVM locks the linkage instruction site -> S.
  6. Use S's target to complete the invocation.

Subsequent executions:
  invokedynamic instruction -> S -> current target according to CallSite type
  [does not repeat steps 1-5]
```

The bootstrap is **not** called with the runtime arguments of the target method like a normal method invocation. It receives metadata `Lookup`, `String invokedName`, `MethodType invokedType`, and static arguments from `BootstrapMethods` to **set up the call site**. Runtime arguments are passed later to the call site's target.

### 3.1. Linkage is tied to the instruction site, not just the constant-pool entry

Multiple `invokedynamic` opcodes can share a single constant-pool entry, but according to the JVMS, each **instruction site** has its own linkage state. Therefore:

- **One instruction site** that has already linked successfully does not automatically relink on the second execution.
- **Two different instruction sites** may each require their own bootstrap, even with the same constant pool index.
- Two bootstrap invocations may also intentionally return **the same `CallSite` object**; in that case, multiple instruction sites link to the same object and are all affected by its target changes.
- Conversely, each site can link to **a separate `CallSite`**, independent of other sites.

Saying “one bootstrap per class” or “one bootstrap per constant-pool entry” is inaccurate.

### 3.2. When multiple threads hit an unlinked site simultaneously

During the **initial linkage phase**, if multiple threads race to execute the same unlinked `invokedynamic` instruction, the JVMS allows the bootstrap **to be executed concurrently multiple times**. The JVM selects one suitable bootstrap result to install for the instruction site; the other results are discarded.

Therefore, one must distinguish:

- **True:** After successful linkage completes, there is no normal API to return **that exact instruction site** to UNLINKED and invoke the bootstrap again.
- **Not true under all races:** “The bootstrap method is guaranteed to execute exactly once in the entire lifecycle.” It can run multiple times **in a race before installing the linkage result**, even though only one result is used.
- **Design responsibility:** A bootstrap with side effects (registering listeners, allocating resources, incrementing counters...) must account for concurrent linkage.

In **hands-on example 4**, all calls are on the same thread with no race; the bootstrap counter is 1 after the first call and **remains 1** after all retargets.

### 3.3. Linkage failure is not automatically retried as a “relink”

If the bootstrap fails, the JVM applies linkage error rules (which may throw `BootstrapMethodError`, depending on the cause). For an `invokedynamic` site that failed resolution, the error is recorded according to the JVMS rather than using `setTarget` to fix an error on a `CallSite` that was never installed. A bootstrap returning a properly typed `CallSite` and completing successfully is different from the target inside it throwing an exception at runtime.

Do not conflate the two types of errors:

- **Linkage error:** the bootstrap fails to resolve symbolic metadata, returns null/wrong type, or throws an error; the JVM has not established a successful linkage.
- **Error when invoking the target after linkage:** the current target throws an exception, updating the target has an issue, or the caller passes the wrong type; the opcode's linkage is not automatically cancelled because of this.

## 4. Three `CallSite` types and target mutability

| Type | `setTarget(newTarget)` | When opcode is linked | Multithreaded update visibility |
| --- | --- | --- | --- |
| `ConstantCallSite` | **Always rejects** with `UnsupportedOperationException` | Always uses the fixed target | No target updates to synchronize |
| `MutableCallSite` | **Allows** when type matches | Uses the current target of the linked object | Like normal variable read/write; needs `syncAll` or proper synchronization to ensure publication to readers |
| `VolatileCallSite` | **Allows** when type matches | Uses the current target of the linked object | `setTarget`/`getTarget` like `volatile` read/write; updates are observed according to volatile semantics |

All three are `java.lang.invoke.CallSite`. They are not three bytecode opcode variants: **an `invokedynamic` opcode can link to any of them** if the bootstrap returns an object satisfying the type contract.

### 4.1. `ConstantCallSite`: fixed target, not “multiple linkages”

`new ConstantCallSite(target)` holds the target permanently. `getTarget()` and `dynamicInvoker()` return the fixed handle. Calling `setTarget(...)` on a constant site throws `UnsupportedOperationException`, even if you propose a new target with the **exact same type**.

This is suitable for bootstraps that create behavior needing no updates. “No retargeting” is due to **choosing `ConstantCallSite`**; one should not infer that all `CallSite`s are fixed like this.

### 4.2. `MutableCallSite`: target state changes like a normal variable

`MutableCallSite` is designed for sites whose target changes after linkage. `setTarget(newTarget)` updates a target field with the semantics of a normal Java variable (no volatile visibility by default).

Within the **same thread**, you can see the new target immediately on the next call. But **across threads**:

- Another thread may keep/cache the old target if there is insufficient synchronization.
- A standalone `setTarget` **does not guarantee** that all running threads immediately see the new target.
- `MutableCallSite.syncAll(new MutableCallSite[]{site})` is a specialized synchronization operation that helps readers on other threads accept the new target.
- `syncAll` can be expensive; it is usually better to batch sites needing publication into a single array rather than calling it repeatedly for each small change.
- `syncAll` **does not recall or roll back** invocations that have already started using the old target.

According to the Java documentation, when designing updates for multiple sites, `setTarget` and `syncAll` should be coordinated with an appropriate mutual exclusion mechanism to avoid racing updates.

**Do not call `syncAll` a bootstrap.** It only performs a synchronization/visibility operation for the targets of existing `MutableCallSite`s; it may cause the runtime/compiler to adjust caches/optimizations, but it does not replace the `CONSTANT_InvokeDynamic` structure or install a new `CallSite` for the opcode.

### 4.3. `VolatileCallSite`: updates like a `volatile` variable

`VolatileCallSite` has `getTarget`/`setTarget` following volatile memory semantics. Each observation of the target is required to recognize new target writes according to volatile rules; there is no `VolatileCallSite.syncAll(...)` API because operations on the target itself already use volatile semantics.

This is useful if the target is updated frequently and multiple threads need to reliably observe changes. In return, reading the target with volatile requirements may be more expensive than `MutableCallSite` in some optimization configurations.

**Warning:** “Seeing the new update” does not mean any in-flight invocation must switch to the new target mid-method body. An invocation that has already started on the old target can complete on the old target, similar to many other pointer/function update designs.

### 4.4. The definition of `CallSite.type()` is immutable

All three site types have an immutable `MethodType`: number, order, and types of parameters, plus return type. `site.setTarget(targetB)` is only valid if:

```java
// Fragment: site is a valid MutableCallSite or VolatileCallSite.
site.type().equals(targetB.type());
```

The snippet above illustrates the check condition, not a standalone program.

If the new target has the wrong type, `setTarget` throws `WrongMethodTypeException`. There is no automatic conversion from `(Object)String` to `(String)String` in `setTarget`. If the contract allows conversion, an adapter `newTarget.asType(site.type())` can be created before replacing:

```java
// Fragment: conversions must be valid, not assumed to always succeed.
MethodHandle adapted = candidate.asType(site.type());
site.setTarget(adapted);
```

Conversions must be chosen carefully; reference casts can cause `ClassCastException` at runtime. It is precisely the immutability of `CallSite.type()` that allows bytecode to keep the same descriptor even though the target can change.

## 5. `getTarget()` and `dynamicInvoker()`: snapshot or live call path?

This is the most important practical distinction.

```text
MutableCallSite site:  target = T0

MethodHandle snapshot = site.getTarget();     // gets T0
MethodHandle live     = site.dynamicInvoker(); // always goes through site

After site.setTarget(T1):

snapshot.invokeExact(...) -> T0
live.invokeExact(...)     -> T1 (according to visibility)
```

`getTarget()` returns a **specific `MethodHandle` value** at the time of reading the target; when kept in a `snapshot` variable, that variable does not automatically update to the new handle. It may represent a method that still accesses external mutable data, but the **reference to the target handle** itself that was retrieved does not automatically change with `site.setTarget`.

`dynamicInvoker()` returns a method handle whose invocation mechanism goes **through the site**; for mutable/volatile sites, subsequent calls use the target observed at invocation time. According to the Javadoc, it is equivalent to an `invokedynamic` linked to that call site.

**Important note:** Calling `site.dynamicInvoker()` in Java source **does not automatically generate** an `invokedynamic` instruction in the caller's bytecode. It lets you test equivalent behavior on an existing `CallSite` object. If you want to **prove bootstrap and actual bytecode linkage**, you need a real `invokedynamic` instruction, as in example 4.

For `ConstantCallSite`, `dynamicInvoker()` can directly return the permanent target since it never changes; the two confusing cases in mutable/volatile do not arise in a constant site.

## 6. Hands-on 1: changing `MutableCallSite` target does not change `CallSite.type()`

Create file **`MutableTargetDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.WrongMethodTypeException;

public final class MutableTargetDemo {
    static String oldRoute(String value) {
        return "old:" + value;
    }

    static String newRoute(String value) {
        return "new:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(
                String.class, String.class);
        MethodHandle oldTarget = lookup.findStatic(
                MutableTargetDemo.class, "oldRoute", signature);
        MethodHandle newTarget = lookup.findStatic(
                MutableTargetDemo.class, "newRoute", signature);

        MutableCallSite site = new MutableCallSite(oldTarget);
        MethodHandle live = site.dynamicInvoker();
        MethodHandle snapshot = site.getTarget();

        System.out.println("site type: " + site.type());
        System.out.println("before: " + (String) live.invokeExact("A"));
        site.setTarget(newTarget);
        MutableCallSite.syncAll(new MutableCallSite[]{site});
        System.out.println("after: " + (String) live.invokeExact("B"));
        System.out.println("snapshot: " + (String) snapshot.invokeExact("C"));
        System.out.println("type unchanged: " + site.type().equals(signature));

        try {
            site.setTarget(MethodHandles.constant(String.class, "wrong type"));
        } catch (WrongMethodTypeException error) {
            System.out.println("type mismatch: "
                    + error.getClass().getSimpleName());
        }
        System.out.println("still new: " + (String) live.invokeExact("D"));
    }
}
```

Java 17+ commands:

```bash
javac --release 17 MutableTargetDemo.java
java MutableTargetDemo
```

**Verified stdout:**

```text
site type: (String)String
before: old:A
after: new:B
snapshot: old:C
type unchanged: true
type mismatch: WrongMethodTypeException
still new: new:D
```

Line-by-line explanation:

1. `new MutableCallSite(oldTarget)` creates a site with type `(String)String` and target `oldRoute`.
2. `live.invokeExact("A")` goes through the site to `oldRoute`, returning `old:A`.
3. `site.setTarget(newTarget)` replaces the target pointer, **without creating a new site**. `syncAll` performs synchronization; in a single-threaded example, this operation is not meant to demonstrate a multithreaded race.
4. `live.invokeExact("B")` goes through the current site, calling `newRoute` to return `new:B`.
5. `snapshot` had obtained `oldTarget` via `getTarget()` before the change, so when invoked it still returns `old:C`.
6. `site.type()` is still `(String)String`. A `()String` handle from `MethodHandles.constant(...)` is incompatible, so `setTarget` throws `WrongMethodTypeException`; the current target remains `newRoute`.

This example **demonstrates CallSite retargeting** but does not yet have a custom `invokedynamic` opcode. It intentionally uses `dynamicInvoker()` to simulate the invocation of a linked instruction.

## 7. Hands-on 2: `VolatileCallSite` keeps a live target and needs no `syncAll`

Create file **`VolatileTargetDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VolatileCallSite;

public final class VolatileTargetDemo {
    static int addOne(int value) {
        return value + 1;
    }

    static int addHundred(int value) {
        return value + 100;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(int.class, int.class);
        MethodHandle first = lookup.findStatic(
                VolatileTargetDemo.class, "addOne", signature);
        MethodHandle second = lookup.findStatic(
                VolatileTargetDemo.class, "addHundred", signature);

        VolatileCallSite site = new VolatileCallSite(first);
        MethodHandle live = site.dynamicInvoker();
        MethodHandle snapshot = site.getTarget();

        System.out.println("site type: " + site.type());
        System.out.println("before: " + (int) live.invokeExact(5));
        site.setTarget(second);
        System.out.println("after: " + (int) live.invokeExact(5));
        System.out.println("snapshot: " + (int) snapshot.invokeExact(5));
        System.out.println("current target: " + (int) site.getTarget().invokeExact(5));
    }
}
```

```bash
javac --release 17 VolatileTargetDemo.java
java VolatileTargetDemo
```

**Verified stdout:**

```text
site type: (int)int
before: 6
after: 105
snapshot: 6
current target: 105
```

- Both `addOne` and `addHundred` have type `(int)int`, so `setTarget` is valid.
- `live` invokes the new target after the update, while `snapshot` still invokes the previously retrieved target.
- `site.getTarget()` at the later point reads the `addHundred` target. According to the API, target reads/writes on `VolatileCallSite` have the semantics of a `volatile` field.
- The single-threaded demo has deterministic output, but does not by itself prove all two-thread interleavings. The volatile difference must be understood through the Java Memory Model/Javadoc, and cannot be inferred solely from output.

## 8. Hands-on 3: `ConstantCallSite` and “not yet ready” initial target

Create file **`ConstantAndBlankDemo.java`**:

```java
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;

public final class ConstantAndBlankDemo {
    static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle fixed = MethodHandles.constant(String.class, "fixed");
        ConstantCallSite constant = new ConstantCallSite(fixed);
        System.out.println("constant: " + (String) constant.dynamicInvoker().invokeExact());
        try {
            constant.setTarget(MethodHandles.constant(String.class, "other"));
        } catch (UnsupportedOperationException error) {
            System.out.println("constant retarget: "
                    + error.getClass().getSimpleName());
        }
        System.out.println("still constant: "
                + (String) constant.dynamicInvoker().invokeExact());

        MethodType signature = MethodType.methodType(int.class, int.class);
        MutableCallSite blank = new MutableCallSite(signature);
        MethodHandle live = blank.dynamicInvoker();
        System.out.println("blank type: " + blank.type());
        try {
            int result = (int) live.invokeExact(4);
            System.out.println(result);
        } catch (IllegalStateException error) {
            System.out.println("blank invoke: " + error.getClass().getSimpleName());
        }
        MethodHandle actual = MethodHandles.lookup().findStatic(
                ConstantAndBlankDemo.class, "twice", signature);
        blank.setTarget(actual);
        System.out.println("initialized invoke: " + (int) live.invokeExact(4));
    }
}
```

```bash
javac --release 17 ConstantAndBlankDemo.java
java ConstantAndBlankDemo
```

**Verified stdout:**

```text
constant: fixed
constant retarget: UnsupportedOperationException
still constant: fixed
blank type: (int)int
blank invoke: IllegalStateException
initialized invoke: 8
```

Two points easily overlooked:

- `ConstantCallSite.setTarget` **always** rejects, regardless of the proposed target's type. `dynamicInvoker` on a constant site returns the permanent target.
- `new MutableCallSite(signature)` creates an **existing `CallSite` object** with type `(int)int`, but the initial target is a handle that **throws `IllegalStateException` when invoked**. Calling `blank.setTarget(actual)` afterward replaces the target for normal use.

Do not call this initial throwing-handle target the **UNLINKED state of an `invokedynamic` instruction**. A bootstrap can return such a `MutableCallSite` to link an opcode; once the JVM receives it, the opcode **is already linked** even though the initial target does not yet do useful work. Thus “target not ready” is not the same as “opcode unlinked”.

## 9. Hands-on 4: a real `invokedynamic` opcode, countable bootstrap

The previous three demos tested the `CallSite` API via `dynamicInvoker()`. This demo goes one step further: **manually generating a valid class file in memory in Java 17**, defining it with `MethodHandles.Lookup.defineClass`, and executing a method containing an `invokedynamic` opcode. The bootstrap provided by the program itself increments a counter each time the JVM calls it.

Everything is in **one Java file**, requiring no ASM, Byte Buddy dependency, or `--add-exports` flag. The program does not write the generated class's `.class` to disk; the bytecode is constructed with `DataOutputStream`, then loaded in memory. This is an advanced example to verify **linkage lifecycle**, not a recommended pattern for hand-writing bytecode in regular applications.

### 9.1. Diagram of the generated class

```text
GeneratedIndyW15
  public static String call(String s)
      aload_0
      invokedynamic #18, 0
      areturn

Constant pool:
  #18 = InvokeDynamic bootstrap_method_attr_index=0
                       name_and_type_index=17
  #17 = NameAndType "route" : (Ljava/lang/String;)Ljava/lang/String;
  #15 = MethodHandle REF_invokeStatic
                      RealIndyRetargetDemo.bootstrap

BootstrapMethods:
  [0] bootstrap_method_ref=#15, bootstrap_arguments=[]

When JVM encounters invokedynamic for the first time:
  bootstrap(Lookup for GeneratedIndyW15, "route", (String)String)
      -> MutableCallSite S with target oldRoute

First / second time: S -> oldRoute
After S.setTarget(newRoute); syncAll([S]):
  this same invokedynamic #18 -> S -> newRoute
  DOES NOT re-invoke bootstrap
```

The indices above are **indices fixed by the generator code below itself**; they are not speculative examples from another `javac`.

### 9.2. Complete `RealIndyRetargetDemo.java`

Create file **`RealIndyRetargetDemo.java`** with the following content:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.reflect.Method;

public final class RealIndyRetargetDemo {
    private static int bootstrapCalls;
    private static MutableCallSite linkedSite;

    public static String oldRoute(String s) {
        return "old:" + s;
    }

    public static String newRoute(String s) {
        return "new:" + s;
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name,
                                     MethodType type) throws Throwable {
        bootstrapCalls++;
        System.out.println("bootstrap caller: " + caller.lookupClass().getSimpleName());
        System.out.println("bootstrap name: " + name);
        System.out.println("bootstrap type: " + type);
        MethodHandle target = MethodHandles.lookup().findStatic(
                RealIndyRetargetDemo.class, "oldRoute", type);
        linkedSite = new MutableCallSite(target);
        return linkedSite;
    }

    private static void utf(DataOutputStream out, String s) throws Exception {
        out.writeByte(1);
        out.writeUTF(s);
    }

    private static void cpClass(DataOutputStream out, int name) throws Exception {
        out.writeByte(7);
        out.writeShort(name);
    }

    private static void cpNameType(DataOutputStream out, int name, int type)
            throws Exception {
        out.writeByte(12);
        out.writeShort(name);
        out.writeShort(type);
    }

    private static byte[] makeClass() throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(61);          // Java 17
        out.writeShort(19);          // 18 entries, 1-based
        utf(out, "GeneratedIndyW15");      // #1
        cpClass(out, 1);                   // #2
        utf(out, "java/lang/Object");      // #3
        cpClass(out, 3);                   // #4
        utf(out, "Code");                  // #5
        utf(out, "call");                  // #6
        utf(out, "(Ljava/lang/String;)Ljava/lang/String;"); // #7
        utf(out, "BootstrapMethods");      // #8
        utf(out, "bootstrap");             // #9
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/invoke/MethodType;)"
                + "Ljava/lang/invoke/CallSite;");          // #10
        utf(out, "RealIndyRetargetDemo");  // #11
        cpClass(out, 11);                  // #12
        cpNameType(out, 9, 10);            // #13
        out.writeByte(10);                 // #14 Methodref
        out.writeShort(12);
        out.writeShort(13);
        out.writeByte(15);                 // #15 MethodHandle
        out.writeByte(6);                  // REF_invokeStatic
        out.writeShort(14);
        utf(out, "route");                 // #16
        cpNameType(out, 16, 7);            // #17
        out.writeByte(18);                 // #18 InvokeDynamic
        out.writeShort(0);                 // BootstrapMethods[0]
        out.writeShort(17);                // NameAndType #17

        out.writeShort(0x0021);            // public, super
        out.writeShort(2);                 // this_class
        out.writeShort(4);                 // super_class
        out.writeShort(0);                 // interfaces
        out.writeShort(0);                 // fields
        out.writeShort(1);                 // methods

        out.writeShort(0x0009);            // public static call
        out.writeShort(6);                 // name "call"
        out.writeShort(7);                 // descriptor
        out.writeShort(1);                 // one method attribute
        out.writeShort(5);                 // "Code"
        out.writeInt(19);                  // code attribute length
        out.writeShort(1);                 // max_stack
        out.writeShort(1);                 // max_locals
        out.writeInt(7);                   // code_length
        out.writeByte(0x2A);               // aload_0
        out.writeByte(0xBA);               // invokedynamic
        out.writeShort(18);                // CP #18
        out.writeShort(0);                 // mandatory zero bytes
        out.writeByte(0xB0);               // areturn
        out.writeShort(0);                 // exception table length
        out.writeShort(0);                 // Code subattributes

        out.writeShort(1);                 // class attributes
        out.writeShort(8);                 // BootstrapMethods
        out.writeInt(6);                   // attribute length
        out.writeShort(1);                 // one bootstrap entry
        out.writeShort(15);                // MethodHandle #15
        out.writeShort(0);                 // zero bootstrap arguments
        out.flush();
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        Class<?> generated = MethodHandles.lookup().defineClass(makeClass());
        Method method = generated.getMethod("call", String.class);

        System.out.println("before first: " + bootstrapCalls);
        System.out.println("first: " + method.invoke(null, "A"));
        System.out.println("after first: " + bootstrapCalls);
        System.out.println("second: " + method.invoke(null, "B"));
        System.out.println("after second: " + bootstrapCalls);

        MethodType sameType = MethodType.methodType(String.class, String.class);
        linkedSite.setTarget(MethodHandles.lookup().findStatic(
                RealIndyRetargetDemo.class, "newRoute", sameType));
        MutableCallSite.syncAll(new MutableCallSite[]{linkedSite});
        System.out.println("after target change: " + method.invoke(null, "C"));
        System.out.println("after change bootstrap count: " + bootstrapCalls);
    }
}
```

Run:

```bash
javac --release 17 RealIndyRetargetDemo.java
java RealIndyRetargetDemo
```

**Exact stdout verified on the JDK:**

```text
before first: 0
bootstrap caller: GeneratedIndyW15
bootstrap name: route
bootstrap type: (String)String
first: old:A
after first: 1
second: old:B
after second: 1
after target change: new:C
after change bootstrap count: 1
```

### 9.3. Why is this direct evidence?

1. `makeClass()` creates a Java 17 class file (major version `61`), with method `call(String)String` consisting of `aload_0`, `invokedynamic`, and `areturn`. There is no instruction directly calling `oldRoute` or `newRoute` in the generated method's bytecode.
2. `CONSTANT_InvokeDynamic` at entry `#18` points to bootstrap record `0`; the bootstrap handle in that record references `RealIndyRetargetDemo.bootstrap`. Therefore, **the JVM actually invokes the bootstrap**, rather than `main` calling that method itself.
3. `bootstrap(...)` prints the caller class, site name, and type passed in by the JVM; then returns a `MutableCallSite` currently pointing to `oldRoute`.
4. Before the first call, the counter is `0`. The first call increments it to `1` and returns `old:A`.
5. The next call runs **the same method, the same opcode site**, and returns `old:B`; the bootstrap count remains `1`.
6. `linkedSite.setTarget(newRoute)` updates the target of the **`CallSite` previously linked by the JVM**. `syncAll` publishes the target change, without changing bootstrap metadata.
7. The third call to the same method `GeneratedIndyW15.call("C")` returns `new:C`, while `bootstrapCalls` **remains 1**. The instruction site remains linked to the same `linkedSite`.

The example runs single-threaded, so a simple `int` counter suffices for illustration. In an example where multiple threads race to *first linkage*, a thread-safe counter must be used if you want to record every bootstrap execution, and you should not expect the count to always be 1.

**Security/engineering note:** Hand-crafting a class file is an educational technique. In production systems, use an appropriate compiler/bytecode library, and control `Lookup.defineClass` permissions and class loaders. Do not modify bytecode of running classes or arbitrarily use `--add-opens` to bypass module policies just to retarget a call site.

## 10. “Relink” in dynamic-language frameworks: terminology or JVM operation?

In a dynamic language runtime, you may encounter names like `relinkCallSite`, `linkAndGetTarget`, or “relink fallback”. These names usually refer to **framework-level** operations:

```text
A linked invokedynamic -> MutableCallSite S
                               |
                               v
                          target T0
                               |
                       a guard fails
                               |
                               v
                     fallback / resolver
                               |
                      computes target T1
                               |
                               v
                       S.setTarget(T1)
                               |
                         syncAll if needed
                               |
                               v
                         continues via T1
```

That is **re-running the framework's target-selection algorithm** and **replacing the target**; there is not necessarily a second `invokedynamic` linkage at the JVMS level. In technical reports, state clearly:

- “Framework relink: computed a new target and called `MutableCallSite.setTarget`.”
- “JVMS invokedynamic linkage: unchanged; the instruction stays associated with the original CallSite.”

If implementing observability tools, place **two separate counters**: the number of times the JVM invokes the BSM (initial linkage attempts), and the number of times the framework recomputes/installs a target. Do not combine both metrics into “link count”.

### 10.1. Invalidating a guard is not equivalent to resetting the bootstrap

`SwitchPoint` allows guarded `MethodHandle`s to choose one branch before/after being invalidated. `SwitchPoint.invalidateAll(...)` can cause a call path to fall back to a fallback, and the fallback can create/install a new target. However, invalidating a switch point **does not** return the `invokedynamic` opcode to UNLINKED; the `instruction -> CallSite` linkage remains intact.

Similarly:

- `MutableCallSite.syncAll(...)` publishes the new target to readers.
- `VolatileCallSite.setTarget(...)` replaces the target with volatile semantics.
- `MethodHandle.asType(...)` creates an adapter.
- `MethodHandles.guardWithTest(...)` creates a dispatching handle.

None of these operations turns into “re-execute bootstrap for an already-linked instruction”.

### 10.2. What about class redefinition or a new class loader?

Loading **a new class** with a different class loader can create **new `invokedynamic` sites** with their own linkage lifecycles. That is not an undo of the old instruction site's linkage.

Instrumentation/hot-swap/class redefinition mechanisms sit at a different VM/tooling layer; they should not be used as evidence that `setTarget` relinks by itself or that the JVM promises to re-run the old site's BSM. When debugging, clearly separate “whether we are talking about the same instruction site belonging to the same class version”.

## 11. When does a callback see the old target, the new target, or an error?

### 11.1. Calls that started before the update

Suppose thread A starts executing target `T0`, and thread B then executes `site.setTarget(T1)`:

- Installing `T1` **does not** cancel the in-progress invocation of `T0`.
- Calls **after the update is observed** will be able to run `T1`.
- When using `MutableCallSite`, without synchronization, a thread may continue observing `T0` longer than expected.
- When using `VolatileCallSite`, reading the target has volatile semantics, avoiding the issue of forever seeing the old target due to unsynchronized caching; however, there is no guarantee that “an in-flight call must jump mid-execution”.

### 11.2. Comparing call paths with different targets

| Call way | Who does it reference? | After target change |
| --- | --- | --- |
| `site.getTarget()` initially, stored in variable `snapshot` | Specific `MethodHandle T0` | `snapshot` is still `T0` |
| `site.dynamicInvoker()` stored in variable `live` | Call path through `site` | Uses current target per site semantics |
| `invokedynamic` opcode linked to `site` | The same installed `CallSite` | Uses current target per site semantics |
| `ConstantCallSite.dynamicInvoker()` | Permanent target | Cannot be retargeted |
| Direct Java method call `oldRoute("x")` | Static method `oldRoute` | Not redirected to another method by `setTarget` |

This is why the program can print “`new:B`” via `live` and “`old:C`” via `snapshot` in demo 1 and be completely valid.

### 11.3. Type conditions when replacing the target

`setTarget` does not pick another overload by name and does not re-run the BSM to find a new type. It only accepts a `MethodHandle` whose `MethodType` **equals** `site.type()`. For example:

```text
site.type()  = (String)String

target A:     (String)String   -> valid
target B:     (Object)String   -> not equal, must adapt validly
target C:     (String)Object   -> not equal, must adapt validly
target D:     ()String         -> not equal
```

With `MethodHandles.Lookup`, an application can look up another overloaded method and use `asType(site.type())` when the conversion is valid; in that case, retargeting installs **an adapter with the exact type**, without changing the `invokedynamic` descriptor.

### 11.4. Bootstrap can return the same CallSite for multiple sites

According to the `java.lang.invoke` package Javadoc, a `CallSite` can be bound to multiple `invokedynamic` instructions. When sharing a site:

- Those linked sites all go through **the same object**.
- `setTarget` on the shared object changes the behavior of **all sites that observe the new target**.
- Sharing does not mean “the sites only link once in total”; each site still has its own linkage lifecycle, and the bootstrap can decide to return the same object.

If you do not want simultaneous changes, the bootstrap should create a separate site for each linkage request according to the runtime's goals.

## 12. The `syncAll` story: visibility, not re-linkage

A commonly seen snippet:

```java
site.setTarget(newHandle);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

This is a **fragment**, assuming `site` is a `MutableCallSite` and `newHandle.type().equals(site.type())`. The two lines mean:

1. `setTarget`: replace the target value in an existing site.
2. `syncAll`: help other threads observe the new target according to `MutableCallSite`'s JMM contract.

**There is no secret third step “re-invoke BSM”.** If logs show “bootstrap ran again”, check whether there is **another instruction site**, **another class/class loader**, **a race during initial linkage**, or **the framework itself calling a method named bootstrap/relink**; never immediately blame `syncAll`.

### 12.1. When to choose `MutableCallSite`, when to choose `VolatileCallSite`?

- **Target rarely changes, hot-path speed needed:** `ConstantCallSite` if the contract is truly fixed.
- **Target changes on configuration events or re-optimization, updates infrequent:** `MutableCallSite` with a coordinated `setTarget`/`syncAll` workflow.
- **Target changes frequently and readers on multiple threads need volatile-style visibility:** `VolatileCallSite`; accept possible volatile observation overhead.

This is a design guideline, not an absolute benchmark; performance depends on the JVM implementation and call/update frequency. Do not use a single-threaded benchmark to draw conclusions about memory ordering in a multithreaded application.

### 12.2. Consistency across multiple CallSites

`MutableCallSite.syncAll(new MutableCallSite[]{siteA, siteB})` performs synchronization over a set of sites. However, this **does not turn target changes at two sites into an atomically visible transaction as a unified block** for all readers, especially with concurrent writers. If cross-site invariants are needed, the application must design its own versioning/transaction/synchronization coordination mechanism.

Similarly, two `VolatileCallSite`s updated with two `setTarget` calls do not automatically form a transaction. Each target has volatile semantics, not atomic multi-object updates.

## 13. Common mistakes and how to debug

| Misconception / symptom | Actual cause | Check |
| --- | --- | --- |
| “After retarget, bootstrap must run again” | Confusing linkage with target mutation | Put counters in BSM and at `setTarget`; compare on **the same opcode** |
| “`syncAll` relinks the instruction” | Confusing memory synchronization with bootstrap resolution | Read `MutableCallSite.syncAll` Javadoc and `CallSite` identity |
| “`getTarget()` returns a live object that updates automatically” | Holding onto the old `MethodHandle` in a snapshot variable | Invoke via `dynamicInvoker()` when a live target is needed |
| “`MutableCallSite.setTarget` is always immediately visible on all threads” | Normal-field visibility is not guaranteed | `syncAll` or proper synchronization; consider `VolatileCallSite` |
| “`VolatileCallSite` forces in-flight invocations to switch code” | Confusing volatile read with cancelling/restarting a method | Distinguish target selection at invocation from executing code |
| `WrongMethodTypeException` in `setTarget` | New target type does not equal `site.type()` | Check `MethodType.equals`; adapt intentionally if allowed |
| `UnsupportedOperationException` on `ConstantCallSite.setTarget` | Site is fixed by design | Choose the appropriate CallSite type from bootstrap, do not hack target |
| `IllegalStateException` when invoking blank site | `new MutableCallSite(MethodType)` has a throwing target at initialization | `setTarget` to a useful handle before invoking |
| “There were two BSM calls, JVM must be relinking one site” | Two different opcodes, different class loaders, or initial race | Check bytecode location, caller class, loader, bootstrap counter, and concurrency |
| “`SwitchPoint.invalidateAll` resets the CP entry” | Invalidates guard handle, not CP/site linkage | Inspect MethodHandle/guard graph, distinguish from bootstrap |
| “Target type is allowed to change after linkage” | `CallSite.type()` is permanently immutable | Adapt with `asType` conditionally, do not modify descriptor |
| “Changing one site must affect all sites with the same CP entry” | Instructions can link to different objects | Check identity of CallSite returned from each linkage |
| “SetTarget affects direct Java calls” | Only call paths **through the site** use the dynamic target | Distinguish `live.invokeExact` from direct/snapshot calls |
| “BSM always runs exactly once even under race” | JVM can run bootstrap in parallel before installing result | Write concurrency-safe bootstrap; do not rely on single-execution side effects |

### 13.1. Practical diagnostic checklist

For a dynamic dispatch system exhibiting “target changed but output is still old”, ask in order:

1. **Is this truly the same linked `invokedynamic` instruction site?** Same class loader and class version?
2. **Which `CallSite` type did the bootstrap actually return?** `ConstantCallSite` may disallow retargeting; `MutableCallSite` and `VolatileCallSite` allow it.
3. **Am I holding the exact reference to the linked `CallSite`?** Creating a new `MutableCallSite` with the same type **does not** replace the old object the opcode is bound to.
4. **Does the new target have a type equal to `site.type()`?** If not, `setTarget` fails and will not update.
5. **Is the caller going through `dynamicInvoker` or the linked instruction, or calling a previously saved `getTarget()` snapshot?**
6. **Are there multiple threads?** If using `MutableCallSite`, has publication been done via `syncAll` or valid synchronization?
7. **Did any invocation start before the update?** In-flight execution on the old target is not cancelled.
8. **Is there a fallback/guard or `SwitchPoint` still choosing the old branch?** Inspect the adapter handle graph instead of assuming the BSM re-ran.
9. **Why did the bootstrap counter increase?** Identify each opcode site, races during initial linkage, and other classes/loaders; do not rely solely on method name.
10. **Is the requirement specifically “target update” or “bytecode/class replacement”?** Those are two different operational systems.

## 14. Self-check questions

**Q1.** Why is “permanently linked `invokedynamic` instruction” still compatible with `MutableCallSite` changing targets multiple times?

**Q2.** When executing `site.setTarget(newTarget)`, which components remain unchanged: `CallSite` identity, site's `MethodType`, CP entry, `BootstrapMethods`, and opcode site?

**Q3.** What does `MutableCallSite.syncAll(...)` do? Does it re-invoke the bootstrap method or regenerate the `CallSite`?

**Q4.** How does `VolatileCallSite` differ from `MutableCallSite` in target visibility across threads? Is `VolatileCallSite.syncAll` needed?

**Q5.** In demo 1, why does `live` return `new:B` while `snapshot` returns `old:C` after the same `setTarget`?

**Q6.** In demo 3, the initial target of `new MutableCallSite(MethodType)` throws `IllegalStateException`. Does this mean the instruction is UNLINKED?

**Q7.** If you call `ConstantCallSite.setTarget` with a `MethodHandle` that has the exact `MethodType`, what is the result?

**Q8.** A call site has type `(String)String`, but the candidate target is `(Object)String`. Can `setTarget` be called directly? Is there a standard way to attempt adaptation?

**Q9.** Why is the bootstrap counter in `RealIndyRetargetDemo` equal to 1 after calling the opcode three times and changing the target?

**Q10.** If two `invokedynamic` bytecodes point to the same constant-pool entry, is the JVM required to use the same `CallSite`?

**Q11.** During an initial linkage race, can the bootstrap be called more than once? How many linkage results does the JVM use?

**Q12.** Does `SwitchPoint.invalidateAll` automatically return an `invokedynamic` instruction to UNLINKED?

**Q13.** Does `MutableCallSite.setTarget` guarantee that invocations already started on the old target are re-executed on the new target?

**Q14.** A framework says “relink fallback” after a guard fails. What do you need to ask to distinguish “framework relink” from “JVMS bootstrap linkage”?

### Suggested answers

1. The `instruction -> CallSite` identity is fixed; `CallSite.target` is a separate field that can change when the site type allows.
2. All listed items remain unchanged; only the target value changes (when the update is valid).
3. Synchronizes/publishes the target for `MutableCallSite` readers; does not invoke the BSM, does not reinstall the site.
4. Volatile has `volatile`-like get/set target, does not need/support `Mutable`-style `syncAll`.
5. `live` goes through the site; `snapshot` holds the `oldRoute` handle retrieved before the update.
6. No; that is a `CallSite` whose target is a throwing handle, different from an opcode's unlinked state.
7. Throws `UnsupportedOperationException`; the target is fixed.
8. No; the types must be equal. You can try `candidate.asType(site.type())` when the conversion is valid, then set it.
9. One site, one thread: the bootstrap runs when the instruction first links; subsequent calls and `setTarget` do not re-run it.
10. No; each instruction site links separately, and the BSM can return separate sites or the same site.
11. Yes, under contention; the JVM selects **one result** to bind to an instruction site.
12. No; it only invalidates guard behavior according to the `SwitchPoint` mechanism.
13. No; in-flight invocations can continue on the old target.
14. Are they calling `setTarget`/replacing a guard on the old site, or actually creating/running a new instruction? Check site identity and BSM call count.

## 15. Standard references

- [Java SE 21 API — `CallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html): `target` model, fixed type, relationship of one `CallSite` to one or more instructions, meaning of `dynamicInvoker()`.
- [Java SE 21 API — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): permanent target, `setTarget` throws `UnsupportedOperationException`.
- [Java SE 21 API — `MutableCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html): `setTarget` as normal variable, `dynamicInvoker`, `syncAll`, and Java Memory Model.
- [Java SE 21 API — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target with volatile semantics, cross-thread update visibility, no `syncAll`.
- [Java SE 21 API — `java.lang.invoke` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html): bootstrap, linking an `invokedynamic` instruction to a `CallSite`, contention during initial linkage.
- [JVMS Java SE 21 — `5.4.3.6 Dynamic Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6): resolution lifecycle, errors, and concurrent bootstrap execution.
- [JVMS Java SE 21 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic): operand structure and instruction rules.
- [JVMS Java SE 21 — `4.4.10 CONSTANT_Dynamic_info and CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.10): CP entry selecting bootstrap record and name/descriptor.
- [Java SE 21 API — `SwitchPoint`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/SwitchPoint.html): guard invalidation mechanism, distinct from JVM linkage.

**Conclusion:** `invokedynamic` can **lock linkage once in terms of result** to a `CallSite` yet **change behavior many times** thanks to mutable/volatile targets. `setTarget` replaces the invoked method handle; `syncAll` publishes the change; `VolatileCallSite` uses volatile semantics. None of these operations returns **an already-linked instruction site** to the unlinked state or re-invokes the bootstrap method.