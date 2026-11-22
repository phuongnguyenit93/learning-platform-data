# 12.1 CallSite is where the target is held and is bound by a MethodType

**Module:** Java Advance - dynamic-runtime  
**Knowledge Group:** 12. CallSite  
**Practice Environment:** Java 17 and above.

## Learning Objectives

In `java.lang.invoke`, `CallSite` represents the **linkage state of a dynamic call site**. This object holds a `MethodHandle` called the **target**, while also holding a **fixed `MethodType`**. If a `CallSite` allows changing the target, the new target must still have that exact same type; changing the implementation must not change the calling contract of the call site.

After this lesson, you will be able to:

1. Distinguish between **`CallSite`**, **`MethodHandle`**, **`MethodType`**, **`dynamicInvoker()`**, and the **`invokedynamic` instruction**.
2. Explain the invariant `site.type().equals(site.getTarget().type())` along with the checking mechanism of `setTarget(...)`.
3. Recognize the behavior of `ConstantCallSite`, `MutableCallSite`, and `VolatileCallSite`; choose them based on linkage-changing needs and visibility of updates across threads.
4. Know why `getTarget()` creates a snapshot of a target at read time, whereas the handle returned by `dynamicInvoker()` continues to forward to the site's target.
5. Compile on Java 17+, observe target replacement, `WrongMethodTypeException` errors, uninitialized targets, and `MethodHandle.asType(...)` adaptation.
6. Understand the relationship with the `invokedynamic` bootstrap method without confusing **manually creating a `CallSite` in Java code** with **the JVM emitting an `invokedynamic` instruction**.

## 1. Three layers of meaning: call site, target, and type

Imagine a system with a logical call site named `transform`. Initially it converts strings to uppercase; later the router decides to switch to lowercase. **The library wants to change how it works without forcing callers to change the number/types of arguments or the return type.**

~~~text
Caller: passes String, expects String
               |
               v
       CallSite type = (String)String  <----- DOES NOT CHANGE
               |
               | current target (MethodHandle)
               v
        upper(String):String           <-- can change
               |
         after relink
               v
        lower(String):String           <-- same MethodType
~~~

The components:

| Component | Meaning | Example |
| --- | --- | --- |
| `MethodHandle` | An executable, typed reference to a method, constructor, field operation, or adapter chain | Handle pointing to `upper(String)String` |
| `MethodType` | The contract of **return type and ordered parameter type list**; does not contain method name or target identity | `(String)String` |
| `CallSite` | The holder of the target; represents a linkage state with a **fixed type** | A `MutableCallSite` initially pointing to `upper`, later pointing to `lower` |
| `CallSite.getTarget()` | Reads the current handle according to the memory rules of each site type | Before update: `upperHandle` |
| `CallSite.dynamicInvoker()` | Creates a handle with the same type as the site, always forwarding through the **site's current target** | Invoker that maintains the call path through `CallSite` |
| `invokedynamic` | A bytecode instruction that the JVM links to a `CallSite` via a bootstrap method | Call site for a symbolic call point in the constant pool |

**Key point:** `CallSite` is not "a method that can arbitrarily change parameters". It is **a linkage point that is flexible in destination but fixed in type**. `MethodHandle` does not have a mandatory source name; the names `upper`, `lower` just make the example easier to read.

### 1.1. What does `MethodType` include?

~~~java
MethodType contract =
        MethodType.methodType(String.class, String.class);
~~~

This snippet creates **`(String)String`**: the **first argument** of `methodType` is the **return type**, and the subsequent arguments are the **parameter types** of the handle. If there are two arguments:

~~~java
MethodType arithmetic =
        MethodType.methodType(int.class, int.class, int.class);
~~~

then it represents **`(int,int)int`**, not just a single `int` type.

`MethodType` does not contain **method names**, **parameter variable names**, annotations, access permission information, bound receiver objects, or business logic. It represents the **runtime signature** that both caller and target must understand identically.

**For an instance method** like `String.length()`, a handle obtained via `Lookup.findVirtual` usually carries the **receiver** as the first parameter of the `MethodType`, for example `(String)int`. For a static method, there is no implicit target receiver. Therefore, you must get the actual `handle.type()`, not guess from the number of source parameters.

## 2. The most important invariant: `CallSite.type()` does not change

Java 17 specifies:

- `site.type()` returns the `MethodType` of the current target.
- The **type value is semantically immutable** throughout the lifetime of the site.
- If the target's type could change, every call site using an already-linked fixed descriptor would become unsafe. Therefore `setTarget(newTarget)` **rejects** a handle whose type is not equal to the fixed type.

We can express it as:

~~~text
T = site.type()                              // fixed
site.getTarget().type().equals(T) == true  // always holds when site is valid

newTarget.type().equals(T) == true         // condition for setTarget
~~~

This is an **illustrative logical expression**, not a standalone runnable Java file. When the target is successfully changed, the **handle identity** or **internal logic** may differ, but the `MethodType` at the site's interface must be the same.

### 2.1. `equals` is an exact comparison, not "similar"

Suppose the site has type `(String)String`:

| Intended Target | `MethodType` | `setTarget` |
| --- | --- | --- |
| `String upper(String)` | `(String)String` | Valid |
| `String lower(String)` | `(String)String` | Valid |
| `Object wrap(Object)` | `(Object)Object` | Invalid if used directly |
| `String noArg()` | `()String` | Invalid, missing parameter |
| `Object wrap(Object).asType((String)String)` | `(String)String` | Can be valid after creating an adapter |
| Handle of type `(String)Object` | `(String)Object` | Invalid because return type differs |

Even though `String` is a subtype of `Object`, **`(String)String` is not equal to `(Object)Object`**. `CallSite.setTarget` does not automatically widen parameter types, box, or insert casts like an adapter. If needed, you must **adapt the handle first** with `asType` or a suitable combinator before passing it to the site.

On the other hand, having two targets with the same `MethodType` does not mean they have the same semantics, auxiliary permissions, thread safety, or side effects. The type is a **minimal calling contract**, not a security model or a full behavioral specification.

### 2.2. When replacing a target with the wrong type

Sites that allow changing the target, such as `MutableCallSite` and `VolatileCallSite`, throw `WrongMethodTypeException` if `newTarget.type()` does not equal the current type. Passing `null` throws `NullPointerException`. `ConstantCallSite` in particular is immutable regarding its target, so calling `setTarget(...)` always throws `UnsupportedOperationException`, even if you try to set a handle of the same type.

**When the error is detected:** For mutable/volatile sites, a type mismatch is blocked **right at `setTarget`**, instead of waiting until the user calls `dynamicInvoker()` to find out. This keeps all callers already compiled against the old type from having to deal with a completely new signature mid-flight.

## 3. Three CallSite types in Java SE 17

| Type | Can target change? | Visibility semantics | Use case |
| --- | --- | --- | --- |
| `ConstantCallSite` | **No**, fixed from creation time | Target is like a `final` field; `dynamicInvoker()` may directly return the permanent target | Linkage is known, no hot swap needed |
| `MutableCallSite` | **Yes**, if the new target has the same type | Target reads/writes have **normal** field semantics, not automatically forced to be immediately visible to other threads | Optimizing dynamic dispatch; updates are coordinated with `syncAll` when needed |
| `VolatileCallSite` | **Yes**, if same type | Target reads/writes have semantics similar to a **volatile field** | Need earlier and stronger guarantee of observing updates across threads |

`CallSite` itself is an abstract class; in Java 17 the commonly used direct subclasses are the three types above. They solve the **linkage mechanism**, and do not automatically enforce business synchronization, transactions, or authorization requirements.

### 3.1. `ConstantCallSite`: attach once, keep forever

~~~java
ConstantCallSite site = new ConstantCallSite(upperHandle);
MethodHandle invoker = site.dynamicInvoker();
~~~

This is a Java snippet **assuming the variable `upperHandle` already exists**. The constructor takes the fixed type from `upperHandle.type()`. `getTarget()` always points to the same permanent handle, and `dynamicInvoker()` returns the corresponding permanent target. If you try `site.setTarget(lowerHandle)`, it throws `UnsupportedOperationException`.

An application can also use the `protected` constructor `ConstantCallSite(MethodType, MethodHandle createTargetHook)` for cases where creating a complex target in a subclass is needed; it is not necessary to use this special constructor to understand the invariant in this lesson. Key point: **not every site can be relinked**.

### 3.2. `MutableCallSite`: change target without changing type

Two ways to create:

~~~java
MutableCallSite siteA = new MutableCallSite(
        MethodType.methodType(String.class, String.class));
MutableCallSite siteB = new MutableCallSite(upperHandle);
~~~

- `siteA` already has type `(String)String` **right from the constructor**, even though no business target has been assigned yet. Its default target is a handle **with the same type that throws `IllegalStateException` when invoked**.
- `siteB` takes its initial type and target from `upperHandle`.
- Both subsequently only accept `setTarget(...)` with a handle of type `(String)String`.

In a single-threaded application, calling `setTarget` and then `dynamicInvoker` easily sees the new target. In **multithreading**, `MutableCallSite` intentionally behaves like a normal field: other threads may reuse a cached target; immediate visibility of the change must not be assumed. `MutableCallSite.syncAll(new MutableCallSite[]{site})` provides an update synchronization boundary.

**Do not overuse `syncAll`:** it has a cost; synchronize in batches when appropriate, and avoid uncoordinated concurrent updates. It does not roll back calls that have already started on the old target and does not replace locking/coordination for all other application state.

### 3.3. `VolatileCallSite`: stronger visibility of changes

~~~java
VolatileCallSite site = new VolatileCallSite(upperHandle);
site.setTarget(lowerHandle);
~~~

The target of a volatile site follows read/write semantics similar to a **volatile variable**. There is no `VolatileCallSite.syncAll` because target updates already carry appropriate visibility. With a dynamic invoker linked to this site, new calls must observe the target according to volatile rules; there is still no promise that an operation started before the target change will be redirected mid-execution.

Do not conclude that a volatile site is "always faster", "always safe for all shared state", or "replaces `synchronized`" in every workflow. It handles **visibility/ordering of the target variable**, not the atomicity of a business transaction involving multiple variables.

## 4. How `getTarget()` differs from `dynamicInvoker()` at the crucial point

A common misconception: "If I already got a handle from a CallSite, that handle automatically changes along with the site."

Not always.

~~~java
MethodHandle saved = site.getTarget();
MethodHandle viaSite = site.dynamicInvoker();

site.setTarget(anotherTarget);
~~~

This snippet assumes `site` is mutable/volatile and all handles have the same type.

- `saved` is the **MethodHandle read at that moment**. Changing the site's target **does not mutate** the saved handle object; calling `saved` later still executes the call path that `saved` represents.
- `viaSite` is a **MethodHandle that always looks up through the site's current target state**, according to the subclass's memory visibility rules. After relinking, the same `viaSite` object can dispatch to the new target.
- `site.getTarget()` after relinking will return the new handle (under the same visibility rules), but each read is a different operation from maintaining a dynamic invoker.

This is why a system can **give a caller a stable invoker** while swapping the implementation internally without the caller having to recreate the handle.

### 4.1. Do not confuse `MethodHandle` itself with a "mutable method pointer"

`MethodHandle` is a typed call reference. You can build other handles using `asType`, `bindTo`, `filterArguments`..., but you **cannot call `setTarget` on a MethodHandle itself**. Pointing through a changeable target is the responsibility of **`CallSite`**.

### 4.2. What Type does a dynamic invoker have?

`site.dynamicInvoker().type()` equals `site.type()`. If the site is `(String)String`, then the caller of the dynamic invoker must perform a call with a matching type. When using `invokeExact`, the **static types of the arguments and the return type** at the call site must match exactly. If using `invoke`, the JVM may create an adapter when `asType` supports it, but this adaptation **does not change `CallSite.type()`**.

## 5. Java 17+ Practice: fixing the type, replacing the target, checking errors

This practice exercise is a **standalone** program with complete imports and methods. It creates three kinds of CallSite and accurately demonstrates the differences between:

- Creating a site tightly bound to a target.
- Creating a site with a type but without a business execution target yet.
- Invoking via a dynamic invoker and then changing the target twice.
- Taking a snapshot of the old handle with `getTarget()`.
- Attempting to assign a handle with the wrong type and adapting it with `asType` before assigning.
- Trying a volatile site.

**File:** `CallSiteTargetDemo.java`

~~~java
import java.lang.invoke.*;
import java.util.Locale;

public final class CallSiteTargetDemo {
    public static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    public static String lower(String value) {
        return value.toLowerCase(Locale.ROOT);
    }

    public static Object wrap(Object value) {
        return "<" + value + ">";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType contract = MethodType.methodType(String.class, String.class);
        MethodHandle upperHandle = lookup.findStatic(
                CallSiteTargetDemo.class, "upper", contract);
        MethodHandle lowerHandle = lookup.findStatic(
                CallSiteTargetDemo.class, "lower", contract);
        MethodHandle objectHandle = lookup.findStatic(
                CallSiteTargetDemo.class, "wrap",
                MethodType.methodType(Object.class, Object.class));

        ConstantCallSite constant = new ConstantCallSite(upperHandle);
        System.out.println("constantType=" + constant.type());
        System.out.println("constant=" +
                (String) constant.dynamicInvoker().invokeExact("Java"));
        try {
            constant.setTarget(lowerHandle);
        } catch (UnsupportedOperationException expected) {
            System.out.println("constantChange=blocked");
        }

        MutableCallSite mutable = new MutableCallSite(contract);
        MethodHandle invoker = mutable.dynamicInvoker();
        System.out.println("mutableType=" + mutable.type());
        try {
            String ignored = (String) invoker.invokeExact("Java");
            System.out.println("unexpected=" + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("uninitialized=IllegalStateException");
        }

        mutable.setTarget(upperHandle);
        MethodHandle snapshot = mutable.getTarget();
        System.out.println("first=" + (String) invoker.invokeExact("Java"));

        mutable.setTarget(lowerHandle);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("second=" + (String) invoker.invokeExact("Java"));
        System.out.println("snapshot=" + (String) snapshot.invokeExact("Java"));
        System.out.println("sameType=" +
                mutable.type().equals(mutable.getTarget().type()));

        try {
            mutable.setTarget(objectHandle);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongTarget=WrongMethodTypeException");
        }
        System.out.println("afterRejected=" +
                (String) invoker.invokeExact("Java"));

        mutable.setTarget(objectHandle.asType(contract));
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("adaptedTarget=" +
                (String) invoker.invokeExact("Java"));

        VolatileCallSite volatileSite = new VolatileCallSite(upperHandle);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        volatileSite.setTarget(lowerHandle);
        System.out.println("volatile=" +
                (String) volatileInvoker.invokeExact("JaVa"));
        System.out.println("volatileType=" + volatileSite.type());
    }
}
~~~

### 5.1. Compiling and running

Save with the exact file name, using JDK 17 or above. From the directory containing the file:

~~~bash
javac --release 17 -d out CallSiteTargetDemo.java
java -cp out CallSiteTargetDemo
~~~

`javac -d out` can create the output directory if it does not exist yet. Java 17 is the target of the example; the program uses `Locale.ROOT` so that uppercase/lowercase conversion produces results independent of the user's locale.

### 5.2. Verified exact stdout

~~~text
constantType=(String)String
constant=JAVA
constantChange=blocked
mutableType=(String)String
uninitialized=IllegalStateException
first=JAVA
second=java
snapshot=JAVA
sameType=true
wrongTarget=WrongMethodTypeException
afterRejected=java
adaptedTarget=<Java>
volatile=java
volatileType=(String)String
~~~

The source code above has been **compiled with `javac --release 17` and run with `java` successfully**.

### 5.3. Detailed explanation of the results

**`constantType=(String)String`**: `ConstantCallSite` gets its type from `upperHandle`. `constant=JAVA` illustrates the constant site's dynamic invoker executing the immutable target. `constantChange=blocked` confirms `ConstantCallSite.setTarget` is always rejected.

**`mutableType=(String)String`** appears **even when the site does not have a business target yet**. The `MutableCallSite(MethodType)` constructor already created a default target of the same type that throws an error. Therefore `uninitialized=IllegalStateException` is neither a type mismatch nor a `NullPointerException`.

**`first=JAVA` then `second=java`**: before/after `setTarget`, `upperHandle`/`lowerHandle` are used respectively. `invoker` was created **once** but continuously dispatches through the site. The `syncAll` call in the single-threaded demo is included to show the proper API; its essential purpose is **coordinating visibility across threads**, not a prerequisite for the same thread to see the update.

**`snapshot=JAVA`**: `snapshot` holds the target handle from before the change; it **does not go through the site**, so it continues calling uppercase. `sameType=true` shows `site.type()` and `getTarget().type()` remain equal even though the target changed.

**`wrongTarget=WrongMethodTypeException`**: `objectHandle` has type `(Object)Object`, which does not equal `(String)String`. The assignment attempt fails **before replacing the target**, so `afterRejected=java` still calls `lower`.

**`adaptedTarget=<Java>`**: `objectHandle.asType(contract)` creates a **new adapter handle** with type `(String)String`; the wrapper converts valid arguments/results between `String` and `Object`. The adapter calls `wrap` and then casts the `Object` result containing a String back to `String`. The content `<Java>` comes from `wrap`'s logic, unrelated to the previous type error.

**`volatile=java`, `volatileType=(String)String`**: the volatile site can switch from upper to lower without changing its type. This example is single-threaded; **cross-thread update visibility** is governed by Java memory semantics and the API documentation, not inferred solely from the demo's stdout.

## 6. `MethodHandle.asType`: adapting the target while preserving the CallSite contract

When a library has an `(Object)Object` target but wants to expose a `(String)String` call site, it needs to create an adapter:

~~~java
MethodType contract = MethodType.methodType(String.class, String.class);
MethodHandle adapted = objectHandle.asType(contract);
site.setTarget(adapted);
~~~

This is an **illustrative snippet** with existing `objectHandle` and `site`, not a standalone runnable file.

Points to understand:

- `objectHandle.type()` is still `(Object)Object`. Only `adapted.type()` is `(String)String`.
- `asType` only succeeds when the JVM supports the corresponding type conversions (reference casts, certain boxing/unboxing/primitive conversions...). Not all conversions are valid.
- `site.setTarget(adapted)` checks the **MethodType of the adapter**. It does not need to know whether the underlying original method uses `Object` or `String`, as long as it connects through a valid adapter.
- If a **runtime value** cast in the adapter fails, the caller can still encounter a `ClassCastException`, even when `site.type()` is completely valid.
- Changing the public `MethodType` of a site usually means creating a **new site** with the new contract and replacing the linkage at a higher level; you cannot `setTarget` a handle with a different type just to bump an API version.

### 6.1. Do not confuse with `invoke` and `invokeExact`

`MethodHandle.invokeExact` is an invocation that requires the call-site descriptor to **match exactly** the receiving handle's type; `invoke` allows a level of adaptation like `asType` when valid. This is a check **on the handle invocation**.

Whereas `CallSite.setTarget` is a check **on replacing the site's target**. Two different layers:

~~~text
Caller -> (invokeExact) -> dynamicInvoker:(String)String
                              |
                              v
                          CallSite
                          type=(String)String
                              |
                          setTarget only accepts
                          MethodHandle:(String)String
                              |
                              v
                         target logic
~~~

If the caller changes the static type of arguments or the return type of `invokeExact`, a `WrongMethodTypeException` can occur even though `site.target` is completely valid. Conversely, if `setTarget` fails, the caller can still invoke the old target normally.

## 7. How does `CallSite` relate to `invokedynamic`?

### 7.1. Bootstrap method returns a CallSite

In a class file containing `invokedynamic`, each symbolic dynamic call site has a **name**, a **method descriptor**, and a reference to a **bootstrap method** (along with any static arguments). When linking that call site, the JVM calls the bootstrap to obtain a `CallSite`. The bootstrap signature typically has these first three parameters:

~~~text
MethodHandles.Lookup caller
String invokedName
MethodType invokedType
~~~

After those, there may be static bootstrap arguments according to the JVM mechanism. `MethodType invokedType` describes the **contract of the `invokedynamic` instruction being linked**, for example `(String)String`.

The bootstrap result must be a **valid CallSite whose type matches the descriptor exactly**. The JVM links the accepted site to the instruction; when the instruction executes, it invokes the site's current target as an exact invocation matching the verified type.

~~~text
Class-file invokedynamic
 name="transform"
 descriptor=(String)String
 bootstrap=linker(...)
          |
          v
 JVM calls bootstrap(Lookup, "transform", MethodType(String)String, ...)
          |
          v
 CallSite.type() must equal the requested MethodType
          |
          v
 JVM links instruction to CallSite
          |
          +-> ConstantCallSite: always initial target
          |
          +-> Mutable/VolatileCallSite: target can relink
                  (but type always stays the same)
~~~

**Invariant used at the JVM layer:** if an `invokedynamic` has linked successfully, the CallSite's target always has the exact type matching the linked call-site descriptor. Therefore, **a validly linked `invokedynamic` instruction itself will not throw `WrongMethodTypeException` due to a descriptor/target mismatch**. Exceptions from target logic, another adapter, or the bootstrap process can still occur.

### 7.2. A mismatch at bootstrap time is not something that can be ignored

Suppose the JVM requests:

~~~text
invokedType=(String)String
~~~

but the bootstrap returns:

~~~text
site.type()=(Object)Object
~~~

Even though String is an Object, those are not equal signatures. **The `invokedynamic` linkage is invalid** and can end in `BootstrapMethodError` according to JVM resolution rules, rather than the site "guessing" how to convert. It is the bootstrap's responsibility to return a site of the right type, for example choosing a target adapted with `asType(invokedType)` when conversion is valid, and then creating an appropriate `ConstantCallSite` or mutable/volatile site.

An illustrative snippet of a bootstrap **inside a class that has a matching static method**:

~~~java
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name,
                                 MethodType type) throws Throwable {
    MethodHandle target = caller.findStatic(
            caller.lookupClass(), "transformImpl",
            MethodType.methodType(String.class, String.class));
    return new ConstantCallSite(target.asType(type));
}
~~~

This is an **illustrative snippet**, **not a standalone runnable program**: it assumes the class represented by `caller.lookupClass()` has a static method `transformImpl(String)String` and appropriate access permissions. It illustrates the bootstrap using the `type` provided by the JVM; there is no guarantee that `asType` supports every requested type.

### 7.3. Manually creating a site in Java does not emit `invokedynamic`

In the section 5 demo, we wrote:

~~~java
MutableCallSite site = new MutableCallSite(contract);
MethodHandle invoker = site.dynamicInvoker();
String text = (String) invoker.invokeExact("Java");
~~~

**This is just Java code manually creating a "free-floating" CallSite**. No `invokedynamic` is generated merely by `new MutableCallSite(...)` or `dynamicInvoker()`.

Specifically:

- `invoker.invokeExact(...)` is a **`MethodHandle.invokeExact`** call (signature polymorphic), normally compiled to **`invokevirtual`**.
- `invokedynamic` is a **distinct bytecode instruction**, emitted by certain tools/compilers and tied to a bootstrap method from the constant pool.
- A `CallSite` can be linked to **zero instructions** ("free-floating") or used to serve one/or multiple call sites depending on the JVM design. You should not equate a CallSite object itself with a single line of source code.
- Java lambdas or string concatenation may use `invokedynamic` in some classfiles generated by `javac`; however, the exact usage depends on the compiler, runtime, and transformations. To **verify actual instructions**, inspect the bytecode with `javap -v -c` on the corresponding classfile.

### 7.4. Connection to the verb "relink"

After bootstrap links an `invokedynamic`, **the bootstrap does not need to be called on every execution**. If using a Mutable/VolatileCallSite, the coordinator can **change the target of the site itself**; the linked instruction still keeps the old calling type while directing execution to the new target.

Therefore, "relinking dynamic dispatch" in many runtime libraries usually means **updating the target of an existing call site**, rather than modifying source code or the bytecode descriptor at the call site.

Note on bootstrap concurrency: the JVM may have multiple threads participating in resolution and bootstrap execution may happen concurrently in some situations; the JVM selects and installs the appropriate result. Do not assume your Java bootstrap code is guaranteed to run only once in all races — design your bootstrap/registry to be concurrency-safe.

## 8. Multi-thread synchronization: choose `MutableCallSite` or `VolatileCallSite`?

Changing a target on one thread and immediately calling it on the same thread is **not sufficient** to evaluate visibility when the system has multiple worker threads.

### 8.1. Mutable site is a normal field

`MutableCallSite.setTarget` has the write semantics of a normal field. Other threads may not see the update yet due to caching or optimizations permitted by the Java Memory Model; Java does not promise that every call on another thread will see the new target immediately solely from `setTarget`.

When you need to publish updates to callers, you can use:

~~~java
site.setTarget(nextTarget);
MutableCallSite.syncAll(new MutableCallSite[]{site});
~~~

This is an **illustrative snippet**, requiring variables of the right type. `syncAll` performs a synchronization action so that threads must discard cached old target values and accept the published state; `setTarget`/`syncAll` should be coordinated to avoid races between writers.

During a transition moment, some calls that have **already started** may be running the old target; `syncAll` does not roll them back. Additionally, `syncAll` can be expensive; if updating multiple sites, consider batching them and do not use it as a pointless "continuous polling" loop.

### 8.2. Volatile site has immediate visibility on the target variable

`VolatileCallSite` defines its target like a volatile field, providing stronger visibility guarantees across threads without needing `syncAll`. This is suitable for target state that updates frequently or needs clear guarantees on every read.

However:

- Changing the target **does not** guarantee that a transaction spanning multiple different configurations updates atomically.
- Calls that started before a target change can still run the old target.
- Volatile semantics do not replace thread-safe design inside the **target method**.
- Do not choose based on gut feelings about performance; measure if the system has latency/throughput requirements.

### 8.3. Quick comparison

| Scenario | Choice |
| --- | --- |
| Immutable linkage throughout the application lifetime | `ConstantCallSite` |
| Infrequent, batched updates where `syncAll` can be coordinated | `MutableCallSite` |
| Updates needing volatile-style visibility across threads | `VolatileCallSite` |
| Wanting to change the parameter list or return type | **Not possible on the same CallSite**; design another call site/adapter versioning |
| Only need to call a known MethodHandle without dynamic linkage | Can use `MethodHandle` directly; no need to add a CallSite |

## 9. Application design: stable interface, flexible implementation

### 9.1. Plugin router

A plugin router exposes a public API `String transform(String input)`. It can link a `(String)String` site to plugin A, then switch to plugin B:

~~~text
Plugin A: transform(String)String
Plugin B: transform(String)String
                  |
                  v
      CallSite:(String)String
                  |
          dynamicInvoker()
                  |
                Caller
~~~

When selecting a target, **the same signature** is required. If the actual plugin takes `Object` or returns a different type, the router must create a suitable adapter **before `setTarget`** and also verify conversion semantics. You should not mask an incompatible change with blind casts.

A production system also needs:

- Defining plugin lifecycle, `Lookup` access permissions, and class loaders. `CallSite` does not itself resolve `IllegalAccessException` when creating a MethodHandle.
- Fallback rules when a plugin throws an error or a method is not found.
- A policy for in-flight calls if switching plugins mid-flight.
- A resource cleanup plan, controlling memory leaks caused by retaining old class loaders or handles in caches.
- Checking **behavioral** compatibility, not just the same `MethodType`.

### 9.2. Inline cache and dynamic language runtime

In a dynamic runtime, an inline cache may start with a generic dispatch handle, then switch the target to a branch optimized for a common argument type:

~~~text
invoke site type=(Object)Object
    |
    +-- target: genericDispatch
    |
    +-- after observation:
          target: guardedFastPath (still (Object)Object)
~~~

A `guardWithTest`/`asType`/`dropArguments` branch can help preserve the **outer type of the site** while changing how execution works internally. The **mandatory condition** remains that the final handle installed into the site must have **`.type()` equal to `site.type()`**.

If an internal branch relies on a specialized type (e.g., `String`), use an adapter to convert according to the contract and provide a reasonable fallback, rather than changing the site's type based on each input data item.

### 9.3. Public contract cannot change just because implementation changes

The model has two dimensions of evolution:

- **Target evolution**: changing logic, caching, optimization, or provider while keeping the same `MethodType`.
- **API evolution**: changing the number/order/types of parameters or return type. This creates a different contract, which must be versioned/migrated; `setTarget` is not a mechanism for automatically patching old call sites.

Thus, CallSite helps decouple the **dispatch mechanism** from the **signature structure**, without eliminating the need for stable API design.

## 10. Common errors and how to diagnose them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `WrongMethodTypeException` right at `setTarget` | New target has a `MethodType` not equal to the site type | Print `site.type()` and `newTarget.type()`; compare with `equals` |
| `ConstantCallSite.setTarget` throws `UnsupportedOperationException` | Constant site cannot change target | Choose a mutable/volatile site from the design phase |
| `IllegalStateException` when calling a mutable site newly created with `MethodType` | Default target is a handle of the same type that always throws an error | Assign an actual target before letting callers use it |
| `WrongMethodTypeException` at `invokeExact` even though target is valid | Descriptor at the **invoker call site** has wrong parameter/return types | Check direct casts, static types, and `invoker.type()` |
| After changing target, a `savedHandle` variable still calls old logic | Variable obtained from `getTarget()` is a snapshot | Use `dynamicInvoker()` if you want to follow the site |
| Other threads see the old target for a long time | Using `MutableCallSite` without visibility/sync | Coordinate `syncAll` or consider `VolatileCallSite` |
| `ClassCastException` after using `asType` | Conversion is valid at the method type level, but runtime value has wrong type | Verify actual value types and adapter boundary |
| `IllegalAccessException` when creating MethodHandle | `Lookup` lacks access to class/member/JPMS | Check module/package/modifiers; do not alter CallSite.type to bypass permissions |
| Bootstrap error of `invokedynamic` | Bootstrap throws error, returns wrong kind, or site type does not equal requested descriptor | Check `BootstrapMethodError`, `invokedType`, and `site.type()` |
| `NullPointerException` at `setTarget` | Passed null instead of a valid `MethodHandle` | Validate target before installing |
| Result appears to "change type" after relink | Confusing the type of a value inside `Object` with the `MethodType` at the boundary | Print `site.type()`, `getTarget().type()`, check casts |
| Application retains old plugin and cannot release it | Cached invoker/handle holds references to class or loader | Check class loader lifecycle and ownership |

**Minimal debugging workflow:**

1. Print `site.getClass().getName()` to know whether it is constant, mutable, or volatile.
2. Print `site.type()`, `site.getTarget().type()`, and `site.dynamicInvoker().type()`; they must represent the same contract.
3. When relinking, print `newTarget.type()` **before `setTarget`**; check `asType` feasibility if needed.
4. Confirm whether the caller wants a **snapshot** or a **dynamic invoker**.
5. If multiple threads are involved, check visibility, `syncAll`, writer ordering, and other state.
6. If tied to an actual `invokedynamic`, inspect the bootstrap method and constant pool descriptor; separate **linkage errors** from target logic exceptions.
7. If an error comes from the target, log the target cause and resource lifecycle; do not blame every error on `MethodType`.

**Tooling note:** `javap -v -c` shows actual `invokedynamic` instructions and the BootstrapMethods attribute (if the classfile contains them). Demo code that **manually creates a CallSite** does not intentionally emit `invokedynamic` just for the `invoker.invokeExact` call. Do not confuse observing `invokevirtual MethodHandle.invokeExact` in the demo with an `invokedynamic` linked by the JVM via a bootstrap.

## 11. Self-check exercises

**Exercise 1 — Distinguish type and target.** For a `(String)String` site, explain why switching from `upper(String)` to `lower(String)` is valid, while switching directly to `wrap(Object)Object` fails even though both can handle a String.

**Exercise 2 — Snapshot or live routing?** Re-run the demo, moving the `snapshot` creation to **after** `setTarget(lowerHandle)`. Predict how `snapshot` and `second` change. Why does the dynamic invoker still not need to be recreated?

**Exercise 3 — Wrong return type.** Create a handle for `int length(String)` and try `mutable.setTarget(...)` on a `(String)String` site. Predict the exception and explain why differing only in return type is still invalid.

**Exercise 4 — Uninitialized site.** Create `new MutableCallSite(MethodType.methodType(int.class))`, call `dynamicInvoker` before `setTarget`, and explain why the error is not `WrongMethodTypeException` if the caller invokes with the matching descriptor.

**Exercise 5 — Adaptation.** Given an `(Object)Object` target that returns an `Integer`, use `asType((String)String)` and invoke with a String. Identify the type of error that can occur at runtime, even though `site.setTarget` succeeded.

**Exercise 6 — Thread visibility.** Design two router versions: (A) `MutableCallSite` plus batched `syncAll`, (B) `VolatileCallSite`. State the trade-offs regarding linkage freshness, cost, and the possibility of an in-flight call continuing on the old target.

**Exercise 7 — Real `invokedynamic`.** Inspect a classfile containing `invokedynamic` using `javap -v -c`. Identify the bootstrap reference and the instruction's descriptor. Explain why `CallSite.type()` must match that descriptor, yet a mutable target can change later.

**Exercise 8 — Decoupling contract from business semantics.** Two targets both have `(String)String`, but one sends data over the network while the other only converts to uppercase. Why can equal `CallSite.type()` not replace access control checks, auditing, and business compatibility?

## 12. Conclusion

**`CallSite` holds a `MethodHandle` as its `target`, but `CallSite.type()` is immutable throughout the site's lifetime.** With Mutable/VolatileCallSite, `setTarget` can change the execution destination **only when the new target has the same `MethodType`**; wrong types are rejected, while ConstantCallSite does not allow changing the target. `dynamicInvoker()` provides a stable call path that always goes through the site's target, unlike saving a snapshot from `getTarget()`. When a `CallSite` is linked to `invokedynamic`, this type invariant ensures the descriptor of the linked instruction remains valid even if the underlying implementation is relinked.

Remember the one-line model:

~~~text
CallSite = (fixed MethodType) + (target MethodHandle under constant/mutable/volatile policy)
~~~

## Official References (Java 17)

- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html)
- [Java SE 17 — `MutableCallSite` and `syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java SE 17 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [Java SE 17 — `MethodHandle.asType` and `invokeExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [JVM Specification 17 — `5.4.3.6` Dynamic call site resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVM Specification 17 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
