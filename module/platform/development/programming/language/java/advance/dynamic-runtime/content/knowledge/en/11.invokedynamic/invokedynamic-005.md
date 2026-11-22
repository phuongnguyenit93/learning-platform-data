# 11.5 Lifecycle from an Unlinked Call Site to the Chosen `CallSite`

An `invokedynamic` bytecode instruction is not pre-bound to a fixed target method the way we usually think of `invokestatic` or `invokevirtual`. It starts in an **unlinked** state. Before its first execution, the JVM must resolve the symbolic information of the call site, invoke a **bootstrap method (BSM)**, and select a valid `java.lang.invoke.CallSite` object. Once selected, that instruction is **bound to that exact `CallSite`**; subsequent executions use the target provided by the `CallSite`.

This is the foundational model of the dynamic Java runtime: lambdas, method references, string concatenation, and dynamic language compilers can let the JVM decide the execution mechanism at **linkage** time.

**Points to distinguish immediately:**

- **Link**: selecting which **`CallSite`** is bound to a specific `invokedynamic` instruction. For each instruction, the transition from *unlinked* to *linked* happens only once if successful.
- **Dispatch (invoke)**: on each execution of the linked instruction, obtaining the behavior from the `CallSite`'s **target `MethodHandle`** and invoking it with the runtime arguments.
- **Relink target**: `MutableCallSite`/`VolatileCallSite` can **change its target** without **re-running the bootstrap or selecting a new `CallSite`** for that instruction.

This article uses **Java 17** and follows the terminology of the Java Virtual Machine Specification (JVMS). Snippets labeled as pseudocode are not Java syntax that can be written directly with `javac`.

## 1. Before linking: what does the class file already know?

When compiled, a class file may contain an `invokedynamic` instruction with an **index into the constant pool**. The `CONSTANT_InvokeDynamic_info` entry describes the call site using:

1. **`bootstrap_method_attr_index`**: selects an entry in the class-level `BootstrapMethods` attribute. This entry points to the *bootstrap method handle* and the list of **static arguments** (if any).
2. **`name_and_type_index`**: points to `CONSTANT_NameAndType_info`, containing the **name of the call site** and the **method descriptor**: the parameter type list along with the return type.

Example in **diagram** form, not actual bytecode with fixed indices:

~~~text
Method bytecode:
    invokedynamic #17, 0

Constant pool:
    #17 = InvokeDynamic #0 : applyAsInt:()Ljava/util/function/IntUnaryOperator;

BootstrapMethods:
    0: REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
       arguments: ... (method type, implementation handle, ...)

Meaning at the call site above:
  name       = applyAsInt
  descriptor = ()IntUnaryOperator
  BSM        = LambdaMetafactory.metafactory
  static args = information recorded in the class file
~~~

The number `#17`, the bootstrap entry number, and the auto-generated method name are **only illustrative examples**; `javac` may generate different indices. The command `javap -v -p` will show the actual index numbers on your machine.

**Important:** The descriptor `()IntUnaryOperator` in the lambda example is **the type of the call site itself that creates the function object**: it takes no parameters and returns `IntUnaryOperator`. It is **different** from the signature of the abstract method inside the interface, such as `applyAsInt(int) -> int`. When reading disassembly, do not confuse the type of the *call site factory* with the SAM type configured by the bootstrap.

In the unlinked state, the JVM has the metadata to perform linkage, but **there is not yet a `CallSite` selected for the instruction**; it does not yet have a final target to execute that call site.

## 2. Two kinds of arguments: static bootstrap arguments and runtime arguments

A common misconception is that the bootstrap must receive the **business data of each invocation**. In reality, there are two separate streams:

| Data kind | Source | When is it used? | What is it used for? |
| --- | --- | --- | --- |
| **Linkage metadata** | Caller's Lookup, call-site name, `MethodType`, and static args in the class file | During linking | Used by BSM to **choose/construct the target** |
| **Runtime arguments** | Operand stack before each `invokedynamic` instruction | **Every time** the instruction runs after linking | Passed to the **`CallSite`'s target** |

Common bootstrap signature in Java:

~~~java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType,
        Object... staticArguments) throws Throwable {
    // Select and return a CallSite with type() == invokedType.
}
~~~

This is an **illustrative signature**, not a complete method. For a BSM with 0 static arguments, the `Object...` parameter can be omitted; for static arguments with known types, explicit parameter types can be used.

Explanation of the four kinds of information:

- `caller` is the `MethodHandles.Lookup` for the **class containing the call site**; it provides the access context for the bootstrap to look up valid methods/fields. It does not mean "the class of the first runtime argument".
- `invokedName` is the **symbolic name** assigned to the call site by the compiler/generator. It is not required to be the name of an existing Java method on the target class.
- `invokedType` is the **full** type of the call site, including **parameters and return type**. The final target must have the exact semantically equivalent type.
- `staticArguments` is metadata declared by the class file, such as `MethodType`, `MethodHandle`, and strings or other constants, **not** new data from the caller on each execution.

According to the JVMS, the JVM prepares the logical array `[caller, invokedName, invokedType, staticArg0, ...]`, and then invokes the bootstrap handle with the semantics of `MethodHandle.invokeWithArguments`. Therefore, the parameter types of the BSM can be more flexible than the suggested signature above; the compiler does not necessarily have to find a Java method with the exact signature `(Lookup,String,MethodType,Object[])CallSite`.

**Distinguishing `CONSTANT_Dynamic`:** a dynamic constant also has a bootstrap, but it is for **computing the value of a constant**. With `invokedynamic`, the bootstrap must provide a **`CallSite`**. In the case of a constant bootstrap, the third parameter is a `Class<?>` representing the field type, not the `MethodType` of the call site.

## 3. Lifecycle diagram of an `invokedynamic` instruction

~~~text
[Class file containing invokedynamic + symbolic reference]
                         │
                         ▼
                [UNLINKED CALL SITE]
                         │
             prepare for first execution
                         │
                         ▼
        [Resolve BSM handle + call-site MethodType
                    + static args]
                         │
                         ▼
             [Invoke bootstrap method]
                         │
                 returns an object
                         │
                         ▼
        [Validate: non-null CallSite,
           CallSite.type() == descriptor?]
                 │                 │
               Valid            Invalid
                 │                 │
                 ▼                 ▼
        [JVM picks 1 CallSite]  [Linkage failure]
                 │             (e.g. BME)
                 ▼
      [Bind CallSite to THIS instruction]
                 │
                 ▼
      [Read current target MethodHandle]
                 │
                 ▼
        [Invoke target with runtime args]
                 │
                 ▼
     [Subsequent runs: skip bootstrap,
      use the bound CallSite and its
       current target]
~~~

This is the logical model according to the specification, **not** a promise of a fixed sequence of machine instructions. The JVM may optimize, inline, or store link state using other internal mechanisms, as long as observable behavior is preserved.

### Phase A — resolve metadata

The JVM resolves the bootstrap `MethodHandle`, the call-site type from the method descriptor, and the static arguments. Resolution may entail loading classes, checking access permissions, resolving method types/method handles, or initializing classes needed to invoke the bootstrap.

The processing order of static args is determined by the class file. If a method/type reference fails to resolve, the linkage process can fail **before** the BSM's method body actually runs.

### Phase B — run the bootstrap

The BSM receives the **static** information and produces a `CallSite`. A BSM typically works by:

1. Using `caller.findStatic`/`findVirtual` or `MethodHandles` APIs to obtain an initial target.
2. If needed, composing adapters using `asType`, `bindTo`, `filterArguments`, `guardWithTest`, or other combinators.
3. Returning an appropriate `CallSite` kind: `ConstantCallSite`, `MutableCallSite`, or `VolatileCallSite`.

A BSM **can execute arbitrary code** and may have side effects; it should not be assumed to be automatically pure or free. However, business logic that needs to run on *every call* must not be placed in the BSM, because after normal linkage the BSM is not called again for that instruction.

### Phase C — validate and select the `CallSite`

A result is accepted only when:

- It is non-`null`.
- It is an instance of `java.lang.invoke.CallSite` (or a subclass).
- `CallSite.type()` **equals the call site's method descriptor** under JVM type semantics. In other words, the target has the exact parameter list and return type. There is no arbitrary automatic type "adaptation" *after* choosing the site.

If the bootstrap returns `null`, returns a non-`CallSite` object, or returns a site whose type differs from the descriptor, linkage fails, typically with `BootstrapMethodError`. A `(String)String` method cannot serve as the target for an `(int)int` call site merely because the names match.

### Phase D — binding and execution

The JVM binds **the specific `invokedynamic` instruction** to the chosen `CallSite`. Then, the runtime arguments according to the call-site descriptor are passed to the **target `MethodHandle`** as an `invokeExact`-style call.

If the target is a long adapter chain, it may perform many transformations before or after the destination method; those steps are **target behavior**, not the JVM re-running the BSM.

**An important boundary:** the initial target can be chosen to be mutable; the **`CallSite` object bound to the instruction** is not replaced by the instruction itself after it has been successfully linked.

## 4. "The bootstrap is called only once" must be understood accurately

The shorthand "the BSM runs only once" is useful in single-threaded examples, but it is **not** a guarantee that the total number of BSM invocations across the entire program is always strictly one.

### 4.1. Linkage belongs to an **instruction site**

Two `invokedynamic` instructions in the same class can point to **the same constant pool entry**; linkage still must be resolved for **each instruction**. If the BSM itself returns the same `CallSite` object for both locations, they can share that object; **the JVM does not merge two locations into a single linkage by default**.

Consequences:

- A method containing an `invokedynamic` instruction can be called many times; after successful linkage, that instruction **is not re-linked** just because the method runs again.
- Two separate call locations can lead to **two separate linkage processes**, even if the BSM is the same.
- Two classes with identical bytecode loaded by different class loaders have separate linkage states. Do not infer the number of linkages from **the number of generated lambda classes** or **the number of created function objects**.

### 4.2. Multiple threads racing on the first run

According to the Java 17 JVMS, when multiple threads simultaneously attempt to enter an unlinked instruction:

- The bootstrap **may** be invoked **concurrently multiple times** for the same call site.
- The JVM selects **one** valid result to **install and publish** for all threads.
- The remaining BSM results are allowed to complete, but are **not selected** as the final binding.

Therefore, a BSM with side effects (incrementing a counter, logging, opening resources, registering handlers) needs to be designed to be **race-safe**, and "counting how many times the BSM ran" should not be treated as a reliable measure of "how many CallSites were installed".

Diagram:

~~~text
Thread T1 ─┐
           ├──> BSM(...) --> CallSite A ──┐
Thread T2 ─┘                              ├── JVM selects exactly 1 binding
               BSM(...) --> CallSite B ──┘

Afterward: every execution of the instruction uses the chosen CallSite,
without re-running the BSM to "draw lots" again.
~~~

### 4.3. Caching both success and failure

For **a specific instruction**, after successful linkage, subsequent resolutions return **the same bound object** without calling the BSM again.

If resolution of that instruction **fails**, subsequent attempts by **that same instruction** continue to fail with **the same resolution error**; the bootstrap is not re-run as an automatic retry mechanism. A **different** `invokedynamic` instruction (even if pointing to the same constant pool entry) can still be resolved independently.

`invokedynamic` should not be used as a "retry loop" for a bootstrap that throws errors due to configuration or transient connections. If you need to change strategy after linking, design an appropriate target inside `MutableCallSite`/`VolatileCallSite`, or actively implement retry logic at the business layer.

## 5. A chosen site does not mean the target is always immutable

A `CallSite` holds a target `MethodHandle`, and the three Java 17 variants have different rules:

| Variant | Can the target change after linking? | Effect |
| --- | --- | --- |
| `ConstantCallSite` | **No** | Fixed target; suited for stable call paths, optimal efficiency |
| `MutableCallSite` | **Yes** via `setTarget` | Target has normal-field semantics; for other threads to observe updates consistently, use an appropriate synchronization mechanism such as `MutableCallSite.syncAll` |
| `VolatileCallSite` | **Yes** via `setTarget` | Target has `volatile` variable semantics; other threads see changes according to volatile rules, which may incur higher synchronization cost |

These site types have a fixed `type()` after creation. If you change the target from `(int)int` to `(String)String`, `setTarget` throws `WrongMethodTypeException`; to swap in different logic, you must supply a **`MethodHandle` of the same type**, for example after creating a compatible adapter yourself.

`CallSite.dynamicInvoker()` returns a handle that **invokes the site's current target**, behaving equivalently to a call site bound to that site. For mutable/volatile sites, this handle observes target changes according to the corresponding semantics. **However, calling `dynamicInvoker()` directly in Java does not create a new `invokedynamic` instruction and does not trigger a bootstrap**.

Distinguish the two concepts clearly:

~~~text
Binding:
    invokedynamic instruction ──> chosen CallSite  [unchanging]

Dispatch:
    chosen CallSite ──> current MethodHandle target [changeable]
                                │
                                ▼
                            execution
~~~

Thus, "relinking the target" is a way of speaking about **replacing the target inside an already-bound site**, not "the JVM returning to the unlinked state and re-running the BSM".

## 6. Complete Java 17 example: real `invokedynamic` and a site with a changeable target

To have an example **runnable using only Java source**, we use a lambda: `javac` on Java 17 emits `invokedynamic` to build the object implementing the functional interface. Then we **manually create `CallSite`s** to observe target state. The two parts are **deliberately separated**:

- **Lambda part:** has a real `invokedynamic` in bytecode, generated by the compiler; the BSM is `LambdaMetafactory.metafactory` in the standard configuration.
- **Manually created `CallSite` part:** illustrates fixed and changeable targets, **not** the JVM linking a new `invokedynamic` instruction. Calls through `dynamicInvoker()` are ordinary `MethodHandle` invocations.

Create the file **`IndyLifecycleDemo.java`**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.function.IntUnaryOperator;

public final class IndyLifecycleDemo {
    static IntUnaryOperator factory() {
        return x -> x + 1;
    }

    static int plusTen(int x) { return x + 10; }
    static int timesTen(int x) { return x * 10; }

    public static void main(String[] args) throws Throwable {
        IntUnaryOperator a = factory();
        IntUnaryOperator b = factory();
        System.out.println("lambda a(3): " + a.applyAsInt(3));
        System.out.println("lambda b(5): " + b.applyAsInt(5));

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(int.class, int.class);
        MethodHandle first = lookup.findStatic(IndyLifecycleDemo.class, "plusTen", type);
        MethodHandle second = lookup.findStatic(IndyLifecycleDemo.class, "timesTen", type);

        CallSite constant = new ConstantCallSite(first);
        System.out.println("constant site type: " + constant.type());
        System.out.println("constant invoker(2): " + (int) constant.dynamicInvoker().invokeExact(2));

        MutableCallSite mutable = new MutableCallSite(first);
        MethodHandle dynamic = mutable.dynamicInvoker();
        System.out.println("mutable before(2): " + (int) dynamic.invokeExact(2));
        mutable.setTarget(second);
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("mutable after(2): " + (int) dynamic.invokeExact(2));

        VolatileCallSite volatileSite = new VolatileCallSite(first);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        System.out.println("volatile before(2): " + (int) volatileInvoker.invokeExact(2));
        volatileSite.setTarget(second);
        System.out.println("volatile after(2): " + (int) volatileInvoker.invokeExact(2));

        try {
            mutable.setTarget(MethodHandles.constant(String.class, "wrong"));
        } catch (WrongMethodTypeException expected) {
            System.out.println("bad target type: " + expected.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 IndyLifecycleDemo.java
java IndyLifecycleDemo
~~~

**Exact stdout:**

~~~text
lambda a(3): 4
lambda b(5): 6
constant site type: (int)int
constant invoker(2): 12
mutable before(2): 12
mutable after(2): 20
volatile before(2): 12
volatile after(2): 20
bad target type: WrongMethodTypeException
~~~

Meaning of each part:

1. `factory()` has **one `invokedynamic` site** to produce an `IntUnaryOperator`. We call `factory` twice, but we do not conclude that the BSM ran twice; the linking process belongs to **the bytecode location**, not to each `IntUnaryOperator` object.
2. `ConstantCallSite(first)` keeps the `plusTen(int)` target fixed, so `2 → 12`. This snippet is not part of the actual lambda bootstrap.
3. `MutableCallSite(first)` initially executes `plusTen`. After `setTarget(second)` and `syncAll`, the very same `dynamic` handle obtained earlier executes `timesTen`, so `2 → 20`. **The site did not change**, only the target changed.
4. `VolatileCallSite` allows changing the target with `volatile` memory semantics without calling `syncAll`.
5. A target of type `()String` created by `MethodHandles.constant(String.class, "wrong")` is incompatible with a site of type `(int)int`. `WrongMethodTypeException` is thrown **immediately when calling `setTarget`**.

Here, **no custom BSM** is demonstrated to avoid confusing learners into mistaking `new ConstantCallSite(...)` for the JVM resolving an instruction. To see the real BSM chosen by the compiler, use `javap` in the next step.

## 7. Using `javap` to inspect the *unlinked descriptor* and bootstrap metadata

After compiling, run:

~~~bash
javap -c -p IndyLifecycleDemo
javap -v -p IndyLifecycleDemo
~~~

In the output of `javap -c -p`, find the `factory` method. With `javac --release 17`, the method has the following structure (index numbers omitted; do not treat this as complete bytecode stdout):

~~~text
static java.util.function.IntUnaryOperator factory();
  Code:
     0: invokedynamic ... // applyAsInt:()Ljava/util/function/IntUnaryOperator;
     5: areturn
~~~

In `javap -v -p`, inspect two separate sections:

1. **`Constant pool`** has an `InvokeDynamic` entry for the call site `applyAsInt:()Ljava/util/function/IntUnaryOperator;`.
2. **`BootstrapMethods`** shows the BSM referencing `java/lang/invoke/LambdaMetafactory.metafactory` and the lambda's static args (SAM method type, implementation method handle, instantiated method type).

The same class may contain multiple other `InvokeDynamic` entries because Java 17 also uses `StringConcatFactory.makeConcatWithConstants` for string concatenation expressions in `println`. Do **not** use the total number of `InvokeDynamic` entries in a class to infer "how many times the lambda's bootstrap was called".

Reading pattern:

~~~text
Java source:
    return x -> x + 1;

javap -c:
    invokedynamic ... applyAsInt:()IntUnaryOperator

javap -v:
    BootstrapMethods[N] = LambdaMetafactory.metafactory(...)
    static args         = SAM type, implementation method, instantiated SAM type

Runtime:
    JVM resolves the invokedynamic site and chooses a CallSite when needed
    the site's target creates/attaches the appropriate function object
    function.applyAsInt(x) is what actually executes the +1 operation
~~~

A subtle point: the `applyAsInt(3)` call on the object in the example is typically `invokeinterface`, **not** another execution of the `invokedynamic` instruction that created the object. `factory`'s `invokedynamic` serves **the process of building the function instance**, while calling the SAM on the instance is a different method invocation. That explains why we must distinguish *bootstrap*, *factory target*, and *lambda body*.

The `javap` command only inspects the class file; `javap` itself **does not execute the BSM** and **does not tell you how many times the BSM ran at runtime**. It shows the metadata so the JVM can link the call site.

## 8. A custom bootstrap pattern (contract illustration only)

If you generate `invokedynamic` bytecode yourself using a bytecode generator, you can reference a BSM with the following common form:

~~~java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType siteType,
        int factor) throws ReflectiveOperationException {

    MethodHandle raw = caller.findStatic(
            Example.class,
            "multiply",
            MethodType.methodType(int.class, int.class, int.class));

    MethodHandle bound = MethodHandles.insertArguments(raw, 1, factor);
    return new ConstantCallSite(bound.asType(siteType));
}

static int multiply(int value, int factor) {
    return value * factor;
}
~~~

This is an **API simulation snippet, not a standalone Java program**: `Example.class` represents the class containing the method; for the JVM to automatically invoke the bootstrap, you need an **actual class file containing `CONSTANT_InvokeDynamic_info` and a `BootstrapMethods` entry pointing to this bootstrap**. Merely declaring a `bootstrap` method in Java source **does not automatically generate an `invokedynamic` calling that method**.

Suppose the bytecode describes a call site with `siteType = (int)int` and static argument `factor = 3`: the BSM obtains the handle `multiply(int,int)int`, binds `factor` to the second argument to get an `(int)int` handle, and returns a `ConstantCallSite`. When the call site runs with `4`, the target returns `12`.

Things to check in a real implementation:

- `caller.findStatic` must have access permission to the target method; `Lookup` depends on the class containing the call site. In the sample BSM, `Example.class` must identify the right class object.
- `bound.type()` must be compatible so that `asType(siteType)` is valid; the final result must **match the exact type** of the call site.
- The number/types of static args must be adaptable to the bootstrap signature referenced by the class file.
- Returning a fixed `ConstantCallSite` is different from returning a `MutableCallSite` that allows changing the target later.

Note: `name` in the example is not used for routing; in a real bootstrap, it can be used to decide the target, but there is no rule requiring `name` to match the name `multiply`.

## 9. Where do errors occur in the lifecycle?

| Stage | Symptom / exception | What to check |
| --- | --- | --- |
| Resolving bootstrap method handle or static args | `LinkageError`, class/method/access resolution error depending on the situation | `BootstrapMethods`, class loader, module/package access, method handle kind, descriptor |
| BSM executes and throws an exception **that is not a subclass of `Error`** | `BootstrapMethodError` with the original exception as cause | BSM body, `Lookup` permissions, missing target, adapter construction logic |
| BSM executes and throws an `Error` | That `Error` may propagate directly per the JVMS | Do not assume every error is wrapped in `BootstrapMethodError` |
| BSM returns `null`, does not return a `CallSite`, or site type mismatches descriptor | `BootstrapMethodError` | `CallSite.type()` compared against the call-site descriptor in the class file |
| Link succeeded, but **target** throws an exception when invoked | Exception thrown by the target/adapter according to its contract | Business code, runtime data types, logic bugs; do not automatically attribute as bootstrap failure |
| `MutableCallSite.setTarget` with wrong-typed handle | `WrongMethodTypeException` at `setTarget` | Fixed type of the site vs `newTarget.type()` |
| Creating an empty site with `new MutableCallSite(MethodType)` and invoking before setting a valid target | `IllegalStateException` from the default target | Initialize a useful target before publishing the site |

**Distinguishing link errors from target errors:** Once **the `invokedynamic` instruction itself** has linked successfully, the JVM guarantees the target is non-`null` and has the type matching the descriptor; therefore, the *dispatch* performed by the instruction itself does not raise `WrongMethodTypeException` merely from a descriptor mismatch already checked by the JVM. However, **target code** can itself throw `WrongMethodTypeException`, `NullPointerException`, or any valid exception. Do not ignore the stack trace.

For a resolution error recorded for **the same instruction**, invoking the instruction again does not retry the BSM. To change behavior after a successful link, update the target of an appropriate site rather than assuming a link error will self-recover.

## 10. Distinguishing levels of "fixedness" in the dynamic system

| Component | What is fixed? | What can change afterward? |
| --- | --- | --- |
| `invokedynamic` in the class file | Bytecode location and metadata (name, descriptor, BSM ref, static args) | Cannot directly modify the running class file via `setTarget` |
| `CallSite` chosen by the JVM for the instruction | **Binding** for the instruction location after linkage | The instruction does not pick another site on its own |
| `CallSite.type()` | Parameter + return types | **Cannot** change for the site itself |
| Target `MethodHandle` of `ConstantCallSite` | Target | **Cannot** change |
| Target of `MutableCallSite` | Target type | Can change to a method handle **of the same type**; must pay attention to cross-thread visibility |
| Target of `VolatileCallSite` | Target type | Can change to a handle of the same type, under volatile semantics |
| Data passed on dispatch | Runtime values on the operand stack | Can differ on every invocation |

For example, at a call site linked to a `MutableCallSite` of type `(Object)Object`, the initial target might check the input type and use a slow path; after observing the data, the runtime can `setTarget` to an optimized `guardWithTest` chain, as long as the overall type remains `(Object)Object`. That is a dynamic runtime implementation technique, **without needing to make the BSM run again**.

Do not confuse "JIT recompiling/re-inlining machine code" with "JVM re-resolving `invokedynamic`". These are mechanisms at different levels, and optimization details are not a public API contract.

## 11. Checklist when reading errors or analyzing performance

1. **Pinpoint the exact bytecode location**: which class/method, which `invokedynamic` instruction? Do not just search for a generic bootstrap name.
2. **Read `javap -v -p`**: `CONSTANT_InvokeDynamic_info`, name/type, `BootstrapMethods` entry, and static args. Note the **call-site descriptor**, not confusing it with the type of an inner target method.
3. **Identify what the BSM actually receives**: `Lookup`, name, `MethodType`, resolved static args. Check class loaders and required access permissions.
4. **Compare types before returning**: `CallSite.type()` must match the descriptor; set a useful target before returning the site, especially for sites constructed with only `MethodType`.
5. **Distinguish one link from many dispatches**: a Java method running 100 times does not mean the BSM of an instruction ran 100 times.
6. **Is there concurrency?** Bootstraps can be executed concurrently; avoid side effects that depend on "running physically once".
7. **Is the target changed?** With `MutableCallSite`, use `syncAll` or an appropriate synchronization relationship; with `VolatileCallSite`, consider the cost of volatile.
8. **Classify exceptions**: resolution/BSM/validation errors differ from target exceptions at execution time. Once linking fails, do not expect the next call to be a retry.
9. **Avoid guessing generated class names**: lambda implementation and target optimizations are JVM details; prioritize checking descriptors, handle types, and guaranteed APIs.
10. **Separate observation levels**: `javap` inspects static metadata; BSM logs (if you control it) measure bootstrap execution; target telemetry measures invocations. One observation source does not automatically imply another.

## 12. Self-check questions

**1.** A method contains one `invokedynamic`; the method is called 1,000 times on a single thread. Must the BSM run 1,000 times?  
**Answer:** No. Once that location links successfully, subsequent calls use the chosen site. In a normal single-threaded execution, the BSM only needs to run during the initial link.

**2.** Two `invokedynamic` instructions reference the same constant-pool entry. The first instruction has linked; has the second instruction linked yet?  
**Answer:** Not necessarily. According to the JVMS, resolution of a dynamic call site is tracked **per instruction**, not automatically applied to the other instruction.

**3.** Two threads enter an unlinked location concurrently. Is it possible to observe the BSM called twice while only one site is chosen?  
**Answer:** Yes. The JVM is permitted to run the bootstrap concurrently, then select one result and discard the other.

**4.** A BSM returns `new ConstantCallSite(MethodHandles.constant(String.class,"x"))`, while the call site's descriptor is `(int)int`. Can it link?  
**Answer:** No. The site has type `()String`, which does not match `(int)int`; validation fails with `BootstrapMethodError`.

**5.** An `invokedynamic` is bound to a `MutableCallSite`. You change `target` via `setTarget` and `syncAll`. Does the BSM run again?  
**Answer:** No. The binding to the `CallSite` remains intact; only the target inside the site changes.

**6.** For `factory()` in section 6, does the call `a.applyAsInt(3)` necessarily re-run `invokedynamic` to create the lambda?  
**Answer:** No. `factory()` already created the function object via the dynamic call site; `applyAsInt` is a method call on that object.

**7.** A bootstrap fails during linking and later the infrastructure is fixed. Does the same call site automatically re-invoke the bootstrap again?  
**Answer:** No. The resolution failure is recorded for that instruction itself. Do not rely on "bootstrap retry" for recovery.

## Official Java 17 documentation

- [JVMS 17 `5.4.3: Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3)
- [JVMS 17 `5.4.3.6: Dynamically-Computed Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS 17 `6.5: `invokedynamic` instruction](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
- [Java SE 17 `java.lang.invoke` package: call-site linkage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html)
- [Java SE 17 `CallSite`, `ConstantCallSite`, `MutableCallSite` and `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 `MutableCallSite.syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)