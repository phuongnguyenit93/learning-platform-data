# 11.6 Target Type Checking and the Relationship Between CallSite and the invokedynamic Instruction

In the JVM, the **`invokedynamic`** instruction does not hardcode a target method the way `invokestatic` or `invokevirtual` typically does. Instead, it carries a **fixed name and method descriptor in the class file**, and relies on a **bootstrap method** to link the call site to a `java.lang.invoke.CallSite` object. The `CallSite` holds a `MethodHandle` called the **target**. Once linkage succeeds, the JVM dispatches subsequent invocations to that call site's target.

The most important type condition:

> **`callSite.getTarget().type()` must be exactly equal to the `MethodType` of the descriptor recorded at the `invokedynamic` instruction.** A `CallSite` is allowed to change its target if it is mutable, but it cannot change the **type** of its target throughout its lifetime.

After completing this section, you will be able to distinguish **call site type**, **target type**, and **bootstrap method type**, know when the JVM throws `BootstrapMethodError`, when `setTarget` throws `WrongMethodTypeException`, and why `dynamicInvoker()` is not the same as holding onto an old `getTarget()`.

## 1. Vocabulary: instruction, bootstrap, CallSite, and target

| Component | Role | Fixed / Mutable |
| --- | --- | --- |
| `invokedynamic` instruction | Dynamic call site in bytecode; points to a call site specifier consisting of a bootstrap method, name, and descriptor | Name/descriptor fixed in the class file |
| `MethodType` of the call site | JVM signature `(parameters...)return_type`; this is the contract that the values on the operand stack must satisfy | Fixed for the `invokedynamic` site |
| Bootstrap method (BSM) | Runs during linkage, receiving the caller's context, name, `MethodType`, and static arguments if any; returns `CallSite` | Runs when resolution is needed; not the body invoked every time |
| `CallSite` | Holds the target `MethodHandle` and guarantees the target type does not change | The linked site's identity is fixed; the target can change depending on the subclass |
| `CallSite.getTarget()` | Gets the current target handle at the time of reading | Can return a different handle after retargeting |
| `CallSite.dynamicInvoker()` | Gets a handle that executes **through the site**, following the current target | Fixed type, behavior follows the current target |
| `ConstantCallSite` | A site whose target cannot be changed | Fixed target |
| `MutableCallSite` | A site that allows changing the target with ordinary variable semantics | Target can change; requires multi-threaded visibility coordination |
| `VolatileCallSite` | A site whose target has volatile semantics | Target can change; updates are observed according to volatile rules |

A `CallSite` can be linked by the JVM to an `invokedynamic` instruction, but it can also exist **independently** (*free-floating*), not attached to any instruction. Writing `new MutableCallSite(...)` yourself in Java **does not automatically generate** an `invokedynamic` instruction. You can still invoke the site via `dynamicInvoker()` to test the same routing model.

### Two different call paths

~~~text
Path A — a REAL invokedynamic instruction in the class file

  bytecode invokedynamic (name, descriptor, bootstrap reference, static args)
                        |
        JVM first-time linkage: calls bootstrap
                        |
          bootstrap returns CallSite
                        |
        JVM verifies target.type() == descriptor
                        |
            this call and subsequent calls
                        |
                CallSite target
                        |
                   method body


Path B — a CallSite created in Java source

  new MutableCallSite(target)
                        |
        callSite.dynamicInvoker()
                        |
                CallSite target
                        |
                   method body

Path B simulates the dynamic target mechanism, but does NOT generate invokedynamic bytecode itself.
~~~

## 2. The type at invokedynamic is a static contract, not the “bootstrap's type”

Suppose the class file contains an instruction named `transform` and JVM descriptor:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

Represented using the Java API:

~~~java
MethodType siteType = MethodType.methodType(
        String.class, String.class);
System.out.println(siteType);                    // (String)String
System.out.println(siteType.toMethodDescriptorString());
// (Ljava/lang/String;)Ljava/lang/String;
~~~

The snippet above consists of illustrative statements inside a method that imports `java.lang.invoke.MethodType`. This `(String)String` signature means the instruction takes exactly one `String` parameter and returns `String`. That argument is not necessarily the receiver of an instance method; `invokedynamic` does not inherently require a receiver and can be linked to all kinds of handles adapted to match the descriptor.

Meanwhile, a common bootstrap method has a **completely different** signature:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType) throws Throwable
~~~

- `caller`: a `Lookup` representing the class **containing the `invokedynamic` instruction**, used for resolution and access checks.
- `invokedName`: the symbolic name at the call site specifier.
- `invokedType`: the `MethodType` from the **instruction's** descriptor, for example `(String)String`.
- Additional static bootstrap arguments (if any) are passed by the JVM after the three standard arguments; they come from class file metadata, not the instruction's runtime arguments.
- The bootstrap returns **`CallSite`**, not a `MethodHandle` directly. The JVM observes the target held by the `CallSite` and checks the target's type.

If the bootstrap has the type `(Lookup,String,MethodType)CallSite`, that is the **signature for calling the bootstrap**, not the type that the target must carry. These two signatures solve two separate functions.

A linkage model:

~~~text
invokedynamic transform : (String)String
           |
           | calls BSM with (Lookup, "transform", MethodType(String,String))
           v
bootstrap(...) -> new ConstantCallSite(target)
                                    |
                            target.type()=(String)String
                                    |
                           JVM type match check: PASS
                                    |
                              links instruction
~~~

**`MethodType.equals` is the standard comparison.** `(String)String` is different from `(Object)Object` even though Java can cast between the two reference types. `(int)int` is different from `(Integer)Integer`, and `(long)long` is different from `(int)int`. The JVM does not automatically insert an adapter to rescue a bootstrap that returns a target with the wrong descriptor.

## 3. Linkage flow of an instruction according to the JVMS

At a conceptual level, the JVM processes it as follows:

1. An `invokedynamic` instruction is initially **unlinked** to a target. The constant pool and `BootstrapMethods` attribute provide the bootstrap specifier, name, descriptor, and static arguments.
2. Before the instruction is executed for the first time, the JVM resolves the necessary entries and prepares the caller's `Lookup`, name, `MethodType`, and static arguments; it then invokes the bootstrap with semantics similar to `MethodHandle.invoke`.
3. The bootstrap computes or looks up the needed `MethodHandle` and returns a `CallSite` (typically `ConstantCallSite`, `MutableCallSite`, or `VolatileCallSite`).
4. The JVM **checks that the bootstrap result is non-null, is a `CallSite`, and that `CallSite.type()` equals the instruction's descriptor**. Because `CallSite` maintains the type invariant, checking `getTarget().type()` is contractually equivalent.
5. If valid, the instruction is **linked to the CallSite**. Subsequent executions use the site's target without having to call the bootstrap again just to dispatch.
6. If linkage fails, the JVM reports a linkage error. Retrying the **same instruction** does not cause the bootstrap to run again after that resolution has failed; the resolution error is recorded for the instruction.

**Concurrency subtlety:** when multiple threads simultaneously reach an unlinked instruction, the JVM may invoke the bootstrap multiple times during the race; one valid site result is chosen to be installed for the instruction, and the other results may be discarded. Therefore, do not assume “the bootstrap method is guaranteed to run only once per process,” even though an instruction after linkage does not re-bootstrap on every invocation. If the bootstrap has side effects, that race must be accounted for.

**CallSite identity does not mean target identity.** With a mutable/volatile site, the JVM keeps the link to the **site**, while the site can reference a new target. Replacing the target **does not modify the opcode or descriptor**, and does not mean re-bootstrapping is required.

## 4. Type invariant: `CallSite.type()` and `getTarget().type()`

According to the `CallSite` API:

~~~java
MethodType signature = callSite.type();
MethodHandle current = callSite.getTarget();
boolean same = signature.equals(current.type());  // true for a valid CallSite
~~~

The illustrative snippet assumes the variable `callSite` already exists. `type()` returns the **permanent type** of the site. `getTarget().type()` must equal that type. A site can change its target, but **cannot change its type** to a different `MethodType`.

Valid example:

~~~text
site.type()                = (String)String
firstTarget.type()         = (String)String
secondTarget.type()        = (String)String
setTarget(secondTarget)    = OK (for MutableCallSite / VolatileCallSite)
~~~

Invalid example:

~~~text
site.type()                = (String)String
wrongTarget.type()         = (String)int
setTarget(wrongTarget)     = WrongMethodTypeException
~~~

Important point: `CallSite` requires an **exact type match** when changing the target. There is no “`int` can be boxed to `Integer`” or “`String` is an `Object` so it is accepted”: if `MethodType.equals` returns `false`, `setTarget` rejects it. When you want to convert safely, you must create an **adapter handle** whose `type()` is exactly equal to the site type before installing it.

~~~java
MethodHandle generic = lookup.findStatic(
        SomeClass.class, "fromObject",
        MethodType.methodType(Object.class, Object.class));
MethodHandle adapted = generic.asType(
        MethodType.methodType(String.class, String.class));
// adapted.type() = (String)String, if the conversion is supported
~~~

This is an **illustrative** snippet, requiring class `SomeClass` to have `public/static Object fromObject(Object)` or appropriate lookup access. `asType` can insert reference casts and conversions allowed by the Java MethodHandle API; it does **not** perform every arbitrary data conversion. For example, an adapter from `(Object)Object` to `(String)String` will convert the `String` argument to an `Object` reference on the call, then cast the returned result to `String`. If the actual result is not a `String`, you may get a `ClassCastException` **at runtime**, even though the two `MethodType`s at the junction matched.

### Table distinguishing three checks

| Check location | Rule | Error when wrong |
| --- | --- | --- |
| **Linking `invokedynamic`** with bootstrap result | `callSite.type().equals(invokedynamicDescriptor)` | `BootstrapMethodError` |
| **`MutableCallSite`/`VolatileCallSite.setTarget`** | `newTarget.type().equals(callSite.type())` | `WrongMethodTypeException` |
| **`MethodHandle.invokeExact`** from Java code | Argument types **and return** type at the Java call-site must equal `handle.type()` | `WrongMethodTypeException` |

These three errors occur at **three different layers**. Do not lump them all together into “an invokedynamic with the wrong type always throws `WrongMethodTypeException`.” An `invokedynamic` that has been successfully linked carries a descriptor matching the target type by design; a type mismatch at the bootstrap step is a **linkage error**. The target method can still actively throw its own exceptions, including other runtime exceptions.

## 5. ConstantCallSite, MutableCallSite, VolatileCallSite

### `ConstantCallSite`

~~~java
CallSite site = new ConstantCallSite(target);
~~~

- Permanent target. Both `getTarget()` and `dynamicInvoker()` lead to that exact target; `ConstantCallSite.dynamicInvoker()` returns the permanent target.
- `setTarget(...)` always throws `UnsupportedOperationException`, even if the new handle has the same type.
- Used when linkage does not need rerouting, for example many call sites of lambda metafactory or compiler-generated string concatenation.

### `MutableCallSite`

~~~java
MutableCallSite site = new MutableCallSite(firstTarget);
MethodHandle dispatcher = site.dynamicInvoker();
site.setTarget(secondTarget);                 // type must equal firstTarget.type()
MutableCallSite.syncAll(new MutableCallSite[] { site });
~~~

- `getTarget()` reads the target like an ordinary variable; the target value can change.
- `dynamicInvoker()` is a handle **bound to the CallSite**, not a snapshot of the target at the time the dispatcher was obtained. When the target changes, the dispatcher can invoke the new target.
- If multiple threads call concurrently, writing `setTarget` **does not automatically guarantee** that other threads see the update immediately. `syncAll(...)` is used to force threads to discard stale cached targets according to the memory visibility contract described in the Javadoc.
- `syncAll` does not reverse an invocation that has already started with the old target; it has a cost, so changes are usually batched. Synchronization among writers also needs to be designed properly.

A `MutableCallSite(MethodType)` can create a **site without a business target yet**. In that case, the default target is a handle of the same type that will throw `IllegalStateException` if invoked; call `setTarget` before putting the site into use.

### `VolatileCallSite`

~~~java
VolatileCallSite site = new VolatileCallSite(firstTarget);
MethodHandle dispatcher = site.dynamicInvoker();
site.setTarget(secondTarget);
~~~

- The target has read/write semantics like a `volatile` variable. Threads reading afterward will observe updates according to volatile memory consistency rules.
- Does not need the `syncAll` API (and there is no `VolatileCallSite.syncAll`).
- May have synchronization overhead compared to a mutable call site depending on the workload. Use when updates are frequent and cross-thread visibility is an explicit requirement.

### Answering the question “`getTarget()` or `dynamicInvoker()`?”

If you call:

~~~java
MethodHandle savedTarget = mutable.getTarget();
MethodHandle live = mutable.dynamicInvoker();
mutable.setTarget(next);
~~~

afterward `savedTarget.invokeExact(...)` still calls the **old handle that you kept**, whereas `live.invokeExact(...)` executes through the site and can observe the **new** target according to the subclass's synchronization policy. There is no need to recreate `live` every time the target changes.

## 6. Bootstrap method: returning a `CallSite` of the right type

A simple bootstrap for a hypothetical instruction `transform:(String)String`:

~~~java
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException {
    MethodHandle target = caller.findStatic(
            MyLinker.class, name, type);
    return new ConstantCallSite(target);
}
~~~

This snippet is **illustrative inside class `MyLinker`**, assuming `MyLinker` has a static method with matching name/signature and the lookup has access permission. If `name="transform"` and `type=(String)String`, `target.type()` is also `(String)String`, satisfying the contract. If the method does not exist or is inaccessible, `findStatic` throws an error; when the JVM actually uses the bootstrap to link `invokedynamic`, a non-`Error` failure from the bootstrap is typically wrapped in `BootstrapMethodError`.

A real-world bootstrap can construct a handle using `findVirtual`, `filterArguments`, `guardWithTest`, `asType`, `bindTo`, or cache by schema/caller. What must be preserved is:

~~~java
if (!target.type().equals(type)) {
    throw new IllegalArgumentException(
            "target " + target.type() + " differs from invokedynamic " + type);
}
return new ConstantCallSite(target);
~~~

This is an **illustrative** check, not a standalone method. If the bootstrap chooses to reject and throw `IllegalArgumentException` during linkage, the JVM will report a bootstrap error (`BootstrapMethodError` due to the non-`Error` exception), rather than waiting for the JVM to receive a `CallSite` of the wrong type. In case you want to **intentionally adapt**:

~~~java
MethodHandle adjusted = target.asType(type);
return new ConstantCallSite(adjusted);
~~~

`asType` is only valid if the adapter conversion is supported. It can throw `WrongMethodTypeException` during the bootstrap phase; if this error occurs during actual linkage, the JVM may wrap it in `BootstrapMethodError`. Do not infer that “`asType` can always fix every mismatch.”

### A bootstrap is not free to return just anything

| Bootstrap returns | When actually linking an `invokedynamic` | Why |
| --- | --- | --- |
| `new ConstantCallSite(target of right type)` | Linkage succeeds | Target type equals descriptor |
| `new MutableCallSite(target of right type)` | Linkage succeeds | Type matches; target is allowed to change later |
| `new VolatileCallSite(target of right type)` | Linkage succeeds | Type matches; updates have volatile semantics |
| `null` | `BootstrapMethodError` | Missing CallSite |
| An object that is not a `CallSite` | `BootstrapMethodError` (after bootstrap result conversion/check) | Wrong result kind |
| `CallSite` with a type **different** from the descriptor | `BootstrapMethodError` | Mismatch at **JVM linkage**, not because the `CallSite` itself is invalid |
| Bootstrap throws a checked exception or runtime exception | Usually `BootstrapMethodError` wrapping the cause if not an `Error` | Linkage did not complete |
| Bootstrap throws an `Error` | JVM rules may propagate that `Error` directly | Not every error is always wrapped |

**Important distinction:** it is completely valid for Java code itself to call `new ConstantCallSite(wrongTypedHandle)` — the constructor only knows the type of **that handle itself**. It does not know the descriptor of any other instruction. `BootstrapMethodError` only occurs when the JVM tries to link that `CallSite` to **an instruction with an incompatible descriptor**.

## 7. Complete Java 17+ example: type matching, retargeting, and a real invokedynamic

Create the file **`IndyCallSiteDemo.java`**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.function.UnaryOperator;

public class IndyCallSiteDemo {
    private static String first(String value) { return "v1:" + value; }
    private static String second(String value) { return "v2:" + value; }
    private static int length(String value) { return value.length(); }
    private static Object throughObject(Object value) { return "object:" + value; }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name, MethodType type)
            throws NoSuchMethodException, IllegalAccessException {
        MethodHandle target = caller.findStatic(IndyCallSiteDemo.class, name, type);
        return new ConstantCallSite(target);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType siteType = MethodType.methodType(String.class, String.class);
        MethodHandle a = lookup.findStatic(IndyCallSiteDemo.class, "first", siteType);
        MethodHandle b = lookup.findStatic(IndyCallSiteDemo.class, "second", siteType);
        MethodHandle wrong = lookup.findStatic(IndyCallSiteDemo.class, "length",
                MethodType.methodType(int.class, String.class));

        System.out.println("descriptor = " + siteType.toMethodDescriptorString());
        ConstantCallSite constant = new ConstantCallSite(a);
        System.out.println("constant type = " + constant.type());
        System.out.println("constant invoke = " + (String) constant.dynamicInvoker().invokeExact("x"));
        try {
            constant.setTarget(b);
        } catch (UnsupportedOperationException expected) {
            System.out.println("constant relink = " + expected.getClass().getSimpleName());
        }

        MutableCallSite mutable = new MutableCallSite(a);
        MethodHandle dynamic = mutable.dynamicInvoker();
        MethodHandle snapshot = mutable.getTarget();
        System.out.println("mutable before = " + (String) dynamic.invokeExact("x"));
        mutable.setTarget(b);
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("mutable after = " + (String) dynamic.invokeExact("x"));
        System.out.println("saved target = " + (String) snapshot.invokeExact("x"));
        try {
            mutable.setTarget(wrong);
        } catch (WrongMethodTypeException expected) {
            System.out.println("incompatible relink = " + expected.getClass().getSimpleName());
        }
        MethodHandle generic = lookup.findStatic(IndyCallSiteDemo.class, "throughObject",
                MethodType.methodType(Object.class, Object.class));
        MethodHandle adapted = generic.asType(siteType);
        mutable.setTarget(adapted);
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("adapted target = " + (String) dynamic.invokeExact("x"));
        System.out.println("type invariant = " + mutable.type().equals(mutable.getTarget().type()));

        VolatileCallSite volatileSite = new VolatileCallSite(a);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        System.out.println("volatile before = " + (String) volatileInvoker.invokeExact("x"));
        volatileSite.setTarget(b);
        System.out.println("volatile after = " + (String) volatileInvoker.invokeExact("x"));

        CallSite manual = bootstrap(lookup, "first", siteType);
        System.out.println("bootstrap manual = " + (String) manual.dynamicInvoker().invokeExact("x"));
        CallSite independentlyWrong = new ConstantCallSite(wrong);
        System.out.println("wrong descriptor = " + !siteType.equals(independentlyWrong.type()));

        // javac emits an invokedynamic instruction for this lambda metafactory call site.
        UnaryOperator<String> trim = String::trim;
        System.out.println("lambda = [" + trim.apply(" x ") + "]");
    }
}
~~~

Compile and run from the directory containing the file, using **JDK 17 or higher**:

~~~bash
javac --release 17 IndyCallSiteDemo.java
java IndyCallSiteDemo
~~~

**Exact `stdout`:**

~~~text
descriptor = (Ljava/lang/String;)Ljava/lang/String;
constant type = (String)String
constant invoke = v1:x
constant relink = UnsupportedOperationException
mutable before = v1:x
mutable after = v2:x
saved target = v1:x
incompatible relink = WrongMethodTypeException
adapted target = object:x
type invariant = true
volatile before = v1:x
volatile after = v2:x
bootstrap manual = v1:x
wrong descriptor = true
lambda = [x]
~~~

This program was compiled with `javac --release 17` and executed on JDK 21; all 15 lines of output above were verified. It **does not deliberately create an invokedynamic instruction with a broken bootstrap** (which requires class file manipulation), but instead illustrates the difference between a standalone call-site object and a real instruction through a method reference emitted by `javac`.

### 7.1. Explaining the key printed lines

1. `descriptor` is the JVM form of `(String)String`. That is the type the site in the example expects.
2. `constant` is created from the handle `first:(String)String` so it has type `(String)String`. `constant.setTarget(b)` throws `UnsupportedOperationException` because the target is immutable.
3. `mutable.dynamicInvoker()` returns a handle that calls through the site. The first time it returns `v1:x`; after `mutable.setTarget(b)`, the dispatcher is still the same handle object but returns `v2:x`.
4. `snapshot = mutable.getTarget()` was saved **before changing the target** so it still calls `first` and returns `v1:x`. This is the difference between a **saved target** and a **dynamic invoker**.
5. `wrong` has type `(String)int`, not equal to `(String)String`; `mutable.setTarget(wrong)` immediately throws `WrongMethodTypeException`. This error occurs in the **Java API**, with no `invokedynamic` instruction mislinked at all.
6. `generic` has type `(Object)Object`. `generic.asType(siteType)` creates an adapter with type `(String)String`; because the method returns `"object:"+value` which is an actual `String`, the return cast succeeds.
7. `VolatileCallSite` returns `v1:x` then `v2:x` after the update; `syncAll` is not used because the target has volatile semantics.
8. `bootstrap(lookup,"first",siteType)` is called **manually from Java code**, returning a matching `ConstantCallSite`. A manual call **does not prove** that the Java source attached this method as the bootstrap of an `invokedynamic` instruction.
9. `independentlyWrong` is a separate `CallSite` with type `(String)int`, so `wrong descriptor = true`; this constructor **does not** throw `BootstrapMethodError`. A BME only applies if the JVM actually attempts to link that wrongly typed `CallSite` to an instruction requiring `(String)String`.
10. `String::trim` is a method reference. The Java 17 compiler emits an `invokedynamic` using lambda metafactory to obtain a `UnaryOperator`; when calling `trim.apply(" x ")`, the result is `"x"`. This is the **real `invokedynamic` instruction** inside the program's class file.

## 8. Inspecting bytecode yourself: what does `javap` prove?

Run next (in the directory containing `IndyCallSiteDemo.class`):

~~~bash
javap -c -p IndyCallSiteDemo
javap -v -p IndyCallSiteDemo
~~~

With `javac --release 17`, in the `-c` output you will see `invokedynamic` instructions. String concatenation lines may go through `StringConcatFactory`; more notably, the `String::trim` expression generates an instruction corresponding to the functional interface's factory. A typical line looks like (the constant-pool index varies by compiler):

~~~text
invokedynamic #...,  0  // InvokeDynamic #...:apply:()Ljava/util/function/UnaryOperator;
~~~

In the `-v` output, the `BootstrapMethods` section contains an entry referencing `java/lang/invoke/LambdaMetafactory.metafactory` with static arguments supplied by the compiler. That is the **real bootstrap method of the lambda call site**, not the `IndyCallSiteDemo.bootstrap` method that the example called manually. Plain Java source **has no direct syntax** to write an `invokedynamic` instruction with an arbitrary bootstrap; to use your own bootstrap, you must generate/edit a valid class file using an appropriate bytecode tool.

### A `MethodType` trap in the lambda example

The instruction that produces the `UnaryOperator` has a descriptor roughly like:

~~~text
()Ljava/util/function/UnaryOperator;
~~~

That is, **the `invokedynamic` instruction at the method reference returns the functional interface object**, not necessarily having the `(String)String` descriptor of the `String.trim` method or the `UnaryOperator.apply` call. Calling `trim.apply(...)` afterward is a separate invocation, typically `invokeinterface` with the generic-erased descriptor `(Object)Object`.

Therefore, when reading `javap`:

- Take the descriptor **directly at each `invokedynamic` instruction** as the type to compare against the `CallSite` created by the bootstrap for that instruction.
- Do not substitute the descriptor of the implementation method (here `String.trim()`) or the SAM interface method (here `UnaryOperator.apply(Object):Object`).
- `LambdaMetafactory` uses the static bootstrap arguments, such as the SAM method type, implementation method handle, and instantiated method type, to link a factory target whose type matches the instruction's descriptor.

This point is very important: the same program can have **multiple `invokedynamic` instructions** (lambdas, method references, string concatenation...), each with its own bootstrap specifier and descriptor. You must not apply a `MethodType` from site A to site B just because both use `MethodHandle`.

## 9. Distinguishing `BootstrapMethodError` and ordinary MethodHandle errors

| Case | Expected error | Explanation |
| --- | --- | --- |
| Bootstrap returns `null` for `invokedynamic` | `BootstrapMethodError` | JVM did not receive a CallSite |
| Bootstrap returns CallSite of type `(String)int` for instruction `(String)String` | `BootstrapMethodError` | Type mismatch at **instruction linkage** |
| Bootstrap needs to look up a method, but `findStatic` throws `NoSuchMethodException` | Usually `BootstrapMethodError` wrapping the cause | Non-`Error` exception while bootstrap runs |
| Bootstrap itself throws an `Error` | May propagate that `Error` directly | Per linkage error rules, not every `Error` is wrapped by default |
| `MutableCallSite.setTarget` with a method type not equal to the site type | `WrongMethodTypeException` | Site type invariant is violated |
| `ConstantCallSite.setTarget` regardless of type | `UnsupportedOperationException` | Target is permanent |
| `MethodHandle.invokeExact` from Java code with a descriptor different from the handle type | `WrongMethodTypeException` | Error at the handle call site |
| `asType` has no valid conversion | `WrongMethodTypeException` (possibly at the adapter creation step) | Cannot create an adapter matching the contract |
| Target handle executes its body and throws `IllegalArgumentException` | `IllegalArgumentException` from the target | Not the same as a linkage type-checking error |
| `new MutableCallSite(methodType)` is called before setting a business target | `IllegalStateException` | Default target has not been initialized to do useful work |

It is necessary to understand the two error layers accurately:

**Layer 1: bootstrap/linkage.** If the JVM cannot install a site matching the contract, it reports `BootstrapMethodError` or a linkage error per JVMS rules. That error cannot be fixed by repeatedly calling the same instruction hoping the bootstrap will run again.

**Layer 2: post-linkage invocation.** After valid linkage, the target can still throw business logic exceptions or errors from an adapter/handle deep inside. You must not infer that every exception when executing the instruction is a bootstrap error. Specifically, the instruction's descriptor and the target type have already been verified as compatible by the JVM with respect to linkage.

## 10. Safe target switching: type adapters, visibility, and versioning

A dynamic dispatcher may need to switch from handler `v1` to `v2` at runtime. The proper process:

1. Obtain the `MethodType` from the **site's contract** and verify that the new target has the right return type and list of parameter types.
2. If they do not match but can be converted safely, use `asType(site.type())` or appropriate combinators to create a handle of the **exact right type**, avoiding trying to change the site's `MethodType`.
3. Test the adapter with edge-case data; `asType` may accept a conversion where an actual runtime value fails to cast.
4. Call `setTarget(adapted)` on `MutableCallSite` or `VolatileCallSite`, not on `ConstantCallSite`.
5. If using `MutableCallSite` across multiple threads, coordinate writes and `syncAll` according to the documentation; if target updates need to be visible like volatile, use `VolatileCallSite`.
6. Do not expose a site still in use to a wrong-typed target or an unready target to callers. If switching to new logic requires additional inputs, adapt it back to the old descriptor via bind/filter/defaulting, **do not** turn `(String)String` into `(String,int)String` at an already-linked site.

For example: if the new target needs an extra `prefix` configuration, you can use `insertArguments(targetWithPrefix, position, prefix)` to bind a fixed value, producing a handle that accepts the same old parameter list. This is the pattern of changing the **implementation** while keeping the **call site ABI**.

### Class loaders, modules, and access permissions

`MethodType` contains actual `Class<?>` objects, not just printed type names. Two classes with the same binary name coming from two different class loaders are **two different runtime types**, so two `MethodType`s may not be equal even if their string representations look identical. At plugin/class loader boundaries, do not compare types by `toString()` alone.

`MethodHandles.Lookup` also restricts target resolution by accessibility/JPMS; just because a bootstrap receives a `Lookup` does not mean it can call every private method of any class. Use the caller's lookup properly, validate static bootstrap arguments, and restrict targets against untrusted input. A private handle can become a capability and should not be leaked arbitrarily.

### Caching and performance

`invokedynamic` is especially useful when linked once and called many times. With `ConstantCallSite`, a stable target gives the JVM optimization opportunities. With `MutableCallSite`/`VolatileCallSite`, the JVM must respect relink semantics and memory visibility. Do not conclude that every `invokedynamic` is faster than `invokevirtual` or reflection: performance depends on call-site stability, inlining, adapter chains, JIT, and workload. Benchmark with JMH when genuinely needed.

## 11. Checklist when writing a bootstrap method or dispatcher yourself

- **Where does the descriptor come from?** For a bootstrap, use the `MethodType type` parameter passed in by the JVM; do not guess from the implementation method.
- **Does the BSM return a CallSite?** The result must be a non-null `CallSite`, not just a `MethodHandle`.
- **Has the target been adapted?** Check `target.type().equals(type)` before returning the site; for a mutable site, the invariant must also be maintained after every update.
- **Are you using the right error to debug?** `BootstrapMethodError` = linkage/BSM, `WrongMethodTypeException` on `setTarget` or `invokeExact` = mismatch in the API, `UnsupportedOperationException` = relinking a constant site.
- **Do you distinguish a snapshot from a live invoker?** `getTarget()` gets the handle at the time of reading; `dynamicInvoker()` follows the current site.
- **Have you handled multi-threading?** `MutableCallSite.syncAll(...)` or `VolatileCallSite` depending on the visibility contract.
- **Have you inspected the real bytecode?** Use `javap -c -v -p` and find the exact descriptor of the `invokedynamic` instruction, without confusing it with the SAM or implementation.
- **Have you distinguished Java source tests from JVM bootstrap tests?** Testing a standalone `CallSite` is useful, but it does not replace running an `invokedynamic` instruction with a real bootstrap in a class file.
- **Have you checked overloads/type erasure?** Primitive/reference types, return type, and type loaders are all part of `MethodType.equals`.
- **Have you tested intentional errors?** Mismatches on `setTarget`, invalid adapters, uninitialized `MutableCallSite`, and wrong bootstrap results in an environment with appropriate bytecode tests.

## 12. Self-check questions

**1.** An instruction has descriptor `(String)String`. The bootstrap returns a `ConstantCallSite` with target `(Object)Object`; both references are reasonable. Will linkage succeed?

**Answer:** No. The JVM requires **equal `MethodType`s**, not just castable types. The bootstrap must create an adapter target of exact type `(String)String` before returning the site.

**2.** To return a `CallSite`, is the bootstrap required to have return type `MethodHandle`?

**Answer:** No. The bootstrap returns `CallSite`; the target resides inside the `CallSite`. The bootstrap's signature is not the instruction's descriptor.

**3.** Does `CallSite.type()` change to match the new target when calling `MutableCallSite.setTarget(...)`?

**Answer:** No. The site's type is fixed. `setTarget` only accepts a new handle whose `MethodType` is equal to the old type.

**4.** You hold `old=site.getTarget()` and `dispatcher=site.dynamicInvoker()` before changing the target. Will both handles always invoke the new body after the update?

**Answer:** No. `old` still points directly to the old target. `dispatcher` invokes through the site and follows the new target with appropriate visibility.

**5.** Are returning a `CallSite` with the wrong descriptor from an `invokedynamic` bootstrap and calling `site.setTarget(wrongHandle)` the same kind of error?

**Answer:** No. A bootstrap returning the wrong descriptor causes `BootstrapMethodError`; `setTarget` with the wrong type on a mutable/volatile site throws `WrongMethodTypeException`.

**6.** Why can `new ConstantCallSite(wrongHandle)` in Java code succeed even when `wrongHandle.type()` does not equal a descriptor you have in mind?

**Answer:** The constructor simply binds the target's own type as the site's type; it **does not link** to any instruction. The JVM only detects a descriptor mismatch when linking it to a real instruction.

**7.** Given `String::trim`, is the descriptor of the `invokedynamic` instruction creating the lambda necessarily `(String)String`?

**Answer:** No. With Java 17, the `invokedynamic` for this method reference is typically a factory returning `UnaryOperator`, for example `()UnaryOperator`. Calling `apply` is a separate step.

**8.** When two threads simultaneously encounter the same unlinked instruction, is the bootstrap guaranteed to run only once?

**Answer:** Not necessarily. The JVM may perform racing bootstrap invocations and then pick one result; after the instruction is linked, subsequent calls do not re-bootstrap on each invoke.

**9.** When using `VolatileCallSite`, is it necessary to call `MutableCallSite.syncAll`?

**Answer:** No. `VolatileCallSite` uses volatile semantics for its target; `syncAll` is an API of `MutableCallSite`.

**10.** If the inner target logic throws `IllegalStateException` after linkage succeeds, is the JVM required to convert that error into `BootstrapMethodError`?

**Answer:** No. `BootstrapMethodError` is related to linkage/bootstrapping. Exceptions from the body after linkage are propagated according to the handle/target invocation mechanism, not automatically turned into a bootstrap error.

## Official reference documentation

- [Java SE 21 — `CallSite`: type invariant, target, and dynamic invoker](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 21 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/ConstantCallSite.html)
- [Java SE 21 — `MutableCallSite` and `syncAll`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java SE 21 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [Java SE 21 — `MethodType`, `MethodHandle.asType`, and `invokeExact`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — `java.lang.invoke` package: dynamic call site linkage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html)
- [JVMS SE 21 — `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS SE 21 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic)