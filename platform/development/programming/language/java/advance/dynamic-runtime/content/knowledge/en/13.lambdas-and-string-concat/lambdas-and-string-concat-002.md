# 13.2 The Three Phases of Linkage, Capture, and Invocation of `LambdaMetafactory`

A Java lambda expression looks very short, such as `x -> base + x`, but the runtime must resolve three different questions: **how to create an object implementing the functional interface**, **which values that object holds from the lambda creation environment**, and **what happens when calling the object's method**. The Java SE 17 documentation for `java.lang.invoke.LambdaMetafactory` calls these three phases:

1. **Linkage:** select how to implement the functional interface and create a `CallSite` whose target acts as a **factory creating function objects**.
2. **Capture:** invoke the `CallSite`'s target with the current environment values; receive the object implementing the interface and carrying the necessary values.
3. **Invocation:** call the **abstract method (SAM)** on the function object; at this point the implementation method receives both the captured values and the new arguments of the call.

These are three **distinct** logical milestones, not three names for the same operation. An `invokedynamic` call site can be linked once, executed to create function objects many times, and each function object can continue to be invoked many times.

This article uses **Java 17+**, `LambdaMetafactory`, `MethodHandle`, `CallSite`, and lambda/method reference examples compiled by `javac`.

## 1. A running example: `base` is a captured argument, `x` is an invocation argument

Consider the method:

~~~java
static java.util.function.IntUnaryOperator makeAdder(int base) {
    return x -> base + x;
}
~~~

This is an **illustrative** method, not a standalone Java file. `IntUnaryOperator` is a functional interface with exactly one abstract method:

~~~java
int applyAsInt(int operand);
~~~

Read each value:

- `base` is available when the program **evaluates the lambda expression** inside `makeAdder(base)`. The lambda **captures the value** `base`.
- `x` does not exist at the time the function object is created; it only appears when the caller invokes `function.applyAsInt(x)`.
- The addition `base + x` belongs to **invocation**, and does not occur when merely creating the function object.

Meaning example:

~~~text
makeAdder(10)  -> function object holds base=10
makeAdder(20)  -> function object holds base=20

function10.applyAsInt(2)  -> 10 + 2 -> 12
function10.applyAsInt(4)  -> 10 + 4 -> 14
function20.applyAsInt(2)  -> 20 + 2 -> 22
~~~

Even though `makeAdder` is called multiple times, the bytecode for the same lambda expression may contain **a single `invokedynamic` location**. Linkage belongs to that bytecode location, while the values `10`, `20` appear in different **capture** calls. Do not equate the number of times a function object is created/received with the number of times the bootstrap is run.

## 2. Diagram of the three phases and two argument sources

~~~text
                CLASS FILE / BOOTSTRAP METADATA
            (SAM type, implementation handle,
             instantiated SAM type, call-site type)
                              │
                              ▼
   ┌────────────────────────────────────────────────────┐
   │ 1. LINKAGE: LambdaMetafactory.metafactory(...)    │
   │    -> CallSite selected for invokedynamic          │
   │    -> the site's target is FACTORY                 │
   └────────────────────────────────────────────────────┘
                              │
                      factory has type:
                   (int)IntUnaryOperator
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   ┌─────────────────────┐          ┌─────────────────────┐
   │ 2. CAPTURE: base=10 │          │ 2. CAPTURE: base=20 │
   │ factory.invoke(10)  │          │ factory.invoke(20)  │
   │ -> function A       │          │ -> function B       │
   └─────────────────────┘          └─────────────────────┘
             │                                 │
       function A holds 10               function B holds 20
             │                                 │
             ▼                                 ▼
   ┌─────────────────────┐          ┌─────────────────────┐
   │ 3. INVOCATION       │          │ 3. INVOCATION       │
   │ A.applyAsInt(2)     │          │ B.applyAsInt(2)     │
   │ impl(10,2) -> 12    │          │ impl(20,2) -> 22    │
   └─────────────────────┘          └─────────────────────┘
~~~

In the diagram, function A/B represent **behavior and captured values**. The JVM **does not guarantee** always allocating a new instance on every capture. Do not infer `functionA != functionB` merely from the lambda expression being evaluated twice.

There are two independent argument lists:

| List | When does it appear? | Example |
| --- | --- | --- |
| **Static/bootstrap arguments** | Stored in class file metadata, used for linkage | `samMethodType`, `implMethod`, `instantiatedMethodType` |
| **Dynamic/captured arguments** | On the operand stack when running the factory target at `invokedynamic` | Value `base=10` or `base=20` |
| **Invocation arguments** | When the caller invokes the SAM on the function object | Value `x=2`, `x=4` |

**Do not** put the value `base=10` into the bootstrap's static arguments list for the `makeAdder` example. The BSM needs to know the **types and count** of variables to be captured, not **each call's value** in advance.

## 3. Phase 1 — Linkage: from metadata to `CallSite`

On Java 17, `javac` typically lowers a lambda expression/method reference into an `invokedynamic` instruction. The class file has:

- A `CONSTANT_InvokeDynamic_info` entry carrying the **name of the interface method to implement** (usually the SAM name such as `applyAsInt`) and the **call-site descriptor**.
- A corresponding entry in the `BootstrapMethods` attribute, referencing a BSM such as `LambdaMetafactory.metafactory` and the static arguments.
- An implementation method represented by a **direct `MethodHandle`**. For a lambda with a body, the compiler may generate a synthetic method named like `lambda$...` in the class containing the expression. For a method reference, the handle may point directly to the target method/constructor.

The BSM typically has the Java SE 17 signature:

~~~java
public static CallSite metafactory(
        MethodHandles.Lookup caller,
        String interfaceMethodName,
        MethodType factoryType,
        MethodType interfaceMethodType,
        MethodHandle implementation,
        MethodType dynamicMethodType)
        throws LambdaConversionException;
~~~

The parameter names in the current JavaDoc correspond to many examples using `invokedType`/`samMethodType`/`implMethod`/`instantiatedMethodType`:

| Parameter | Source/meaning |
| --- | --- |
| `caller` | `Lookup` representing the **class containing the call site** and required access rights; provided by the JVM when executing the bootstrap |
| `interfaceMethodName` | Name of the SAM to implement, e.g. `applyAsInt` |
| `factoryType` / `invokedType` | **Type of the `CallSite` target**, consisting of the list of types of captured arguments and **return type being the functional interface** |
| `interfaceMethodType` / `samMethodType` | SAM method type in implemented form, e.g. `(int)int` |
| `implementation` / `implMethod` | Direct handle to the method performing the logic, e.g. `(int,int)int` |
| `dynamicMethodType` / `instantiatedMethodType` | Instantiated type used for checking/converting when **calling the SAM**; may differ from the erased SAM type due to generic specialization |

**The first three arguments** are prepared by the JVM from the `invokedynamic` context. The next three arguments are typically the static bootstrap arguments recorded in the class file. They describe the shape of the function; they are **not** three arguments of each lambda call.

For `makeAdder(int base)`, we have the type model:

~~~text
factoryType / invokedType:       (int)IntUnaryOperator
interfaceMethodType / SAM type:  (int)int
implementation MethodHandle:    (int,int)int
dynamic/instantiated SAM type:   (int)int

Captured parameter count K = 1  (base)
SAM parameter count      N = 1  (x)
Implementation arity     M = 2  (base, x)
                       K + N = M
~~~

`(int)IntUnaryOperator` belongs to the **factory**, while `(int)int` belongs to the **function called later**. This is the most common point of confusion when reading `javap`.

### 3.1. Type contract at linkage

`LambdaMetafactory` checks several conditions, including:

- The return type of `factoryType` must be an interface for which a suitable function object can be created.
- `implementation` must be a valid **direct MethodHandle** to a method or constructor, not an arbitrary chain of adapters.
- For the standard form, the number of implementation parameters equals the number of captured arguments plus the number of SAM arguments: **`K + N = M`**.
- The captured parameter types must match the corresponding parameters at the start of the implementation; the SAM types, instantiated type, and result must satisfy the metafactory's adaptation rules.
- `caller` must have a lookup context with sufficient privileges according to the API contract.

Do not arbitrarily apply Java conversion rules to "fix" every mismatch. A structure violating the rules may throw `LambdaConversionException` when calling the metafactory directly, or cause a linkage error if the JVM is invoking the metafactory as a bootstrap.

### 3.2. The JVM selects a site and remembers linkage

When the JVM uses the bootstrap for **a specific `invokedynamic` instruction**, it accepts a `CallSite` whose type matches the descriptor and attaches the selected site to the instruction. It then runs the site's factory target, rather than **calling the metafactory again for every function object**.

In case multiple threads reach an unlinked instruction concurrently, bootstrap attempts may race, and the JVM selects one result to link. Therefore, do not rely on there being exactly **one physical execution** of the BSM as a unique side effect. Even if the JVM optimizes differently, the observable behavior must conform to the linkage rules.

`LambdaMetafactory` may generate/load an implementation class, possibly using hidden classes or an appropriate JVM mechanism. **Do not depend** on class names, package names, the number of generated classes, or the allocation order of function objects.

## 4. Phase 2 — Capture: the factory receives environment values

After linkage, `CallSite.getTarget()` is a `MethodHandle` acting as a **factory**. In the example:

~~~text
factory.type() == (int)IntUnaryOperator
~~~

When executing `factory(base)`, the runtime takes the value of `base` at **the current evaluation of the lambda expression** and returns an `IntUnaryOperator` that can be used later.

At capture time:

- The arguments passed to the factory are **captured values**, not the arguments of `IntUnaryOperator.applyAsInt`.
- Primitive values like `int base` are retained by value. When the caller later passes a new `x`, the captured base still holds the value from the creation time.
- If what is captured is an **object reference**, the function holds a reference to **the same object**, without deep-copying the object's state. Valid mutations on the object can be observed later.
- Capture **does not execute the logic inside the lambda body**. For `x -> base + x`, the addition only executes when `applyAsInt(x)` is called.
- The function object produced at capture may be a new object or an existing one. Identity is not a stable contract; do not use `==`, `System.identityHashCode`, or an intrinsic lock on a lambda object as the basis for business logic.

### 4.1. "Captured variables" and effectively final

In Java, **a local variable or parameter accessed by a lambda must be final or effectively final**. Valid example:

~~~java
int base = 10;
java.util.function.IntUnaryOperator op = x -> base + x;
// Do not reassign base after it is used by the lambda.
~~~

This is **illustrative code within a method scope**, not a standalone file. If you add `base = 11;` in the same scope after the lambda references `base`, the compiler reports an error because `base` is no longer effectively final.

The effectively final condition concerns the **local variable/parameter**, and does not mean the referenced object is immutable. Example:

~~~java
java.util.concurrent.atomic.AtomicInteger box =
        new java.util.concurrent.atomic.AtomicInteger(5);
java.util.function.IntSupplier read = box::get;
System.out.println(read.getAsInt()); // 5
box.set(8);
System.out.println(read.getAsInt()); // 8
~~~

Here the lambda/method reference holds the **reference `box`**, while `box` itself changes state. `AtomicInteger` makes the example clear; with ordinary mutable objects, sharing across multiple threads still requires proper synchronization rules.

### 4.2. Captured receiver in a method reference

In the expression `box::get`, the receiver `box` is obtained at the time of **evaluating the method reference**. Later, calling `IntSupplier.getAsInt()` uses that same receiver. Because there are no SAM arguments, the implementation handle type can be pictured as:

~~~text
captured receiver:  AtomicInteger box
SAM arguments:      (none)
implementation:     AtomicInteger.get() -> int
factory:            (AtomicInteger)IntSupplier
SAM:                ()int
~~~

With a **bound instance method reference** (like `box::get`), a null receiver is typically rejected immediately when evaluating the method reference per Java rules, rather than waiting until the SAM call. With `x -> x.method()`, `x` is a **SAM argument**, not a captured receiver; a null error, if any, typically occurs at invocation.

### 4.3. Capture does not mean always creating a new object

A lambda that **captures nothing**, such as `() -> 42`, has factory type `()Supplier`: it needs no data from the environment. The JVM is allowed to reuse the function object across evaluations. Even with capture, the API does not guarantee identity in the simple sense of "one object per evaluation".

If you need **distinct identity state** or an explicit lifecycle per request, create your own class/object with a stable identity contract, instead of assuming uniqueness of the lambda object.

## 5. Phase 3 — Invocation: calling the SAM runs the work

Once you have the function object:

~~~java
int value = op.applyAsInt(2);
~~~

This is a call to the **SAM method** on the object `op`. For `IntUnaryOperator`, the SAM is `applyAsInt(int)int`. The lambda/metafactory ensures the implementation method will invoke the behavior of the `implementation MethodHandle` with two groups of values:

~~~text
arguments to implementation =
    captured arguments (retained at capture)
    + invocation arguments (passed when calling SAM)

Example:
  captured base = 10
  invocation x  = 2
  implementation(base, x) -> 12
~~~

A single function object can be called multiple times with different inputs:

~~~text
capture once: base=10
  ├─ applyAsInt(2) -> 12
  ├─ applyAsInt(4) -> 14
  └─ applyAsInt(9) -> 19
~~~

The BSM does not run again, nor is there any need to "re-capture" `base` for each `applyAsInt` call.

In Java bytecode, `invokedynamic` in `makeAdder` creates the **function object**; calling `op.applyAsInt(...)` on a variable of type `IntUnaryOperator` is typically `invokeinterface`. These two instructions serve **two different roles**. Overlooking this distinction easily leads readers to think every execution of the lambda body triggers the bootstrap.

## 6. Complete Java 17 program: manually creating a metafactory and observing the three phases

The following program has **two intentionally distinct parts**:

1. Calling `LambdaMetafactory.metafactory` **directly** in Java so you can clearly see the `CallSite`, factory type, and capture/invocation timing. This direct call **does not itself generate an `invokedynamic` instruction linked to a bootstrap**.
2. Declaring a real lambda `input -> base + input` and method reference `box::get` so that `javac --release 17` emits `invokedynamic` in bytecode. Inspect with `javap` in the next section.

Create the file **`LambdaLifecycleDemo.java`**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntSupplier;
import java.util.function.IntUnaryOperator;

public final class LambdaLifecycleDemo {
    private static int implementation(int captured, int input) {
        System.out.println("  implementation(captured=" + captured + ", input=" + input + ")");
        return captured + input;
    }

    static IntUnaryOperator compiledLambda(int base) {
        return input -> base + input;
    }

    static IntSupplier referenceCapture(AtomicInteger box) {
        return box::get;
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("phase 1: linkage");
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle impl = lookup.findStatic(
                LambdaLifecycleDemo.class,
                "implementation",
                MethodType.methodType(int.class, int.class, int.class));
        CallSite site = LambdaMetafactory.metafactory(
                lookup,
                "applyAsInt",
                MethodType.methodType(IntUnaryOperator.class, int.class),
                MethodType.methodType(int.class, int.class),
                impl,
                MethodType.methodType(int.class, int.class));
        System.out.println("factory type: " + site.type());

        System.out.println("phase 2: capture");
        MethodHandle factory = site.getTarget();
        IntUnaryOperator add10 = (IntUnaryOperator) factory.invokeExact(10);
        IntUnaryOperator add20 = (IntUnaryOperator) factory.invokeExact(20);

        System.out.println("phase 3: invocation");
        System.out.println("add10(2): " + add10.applyAsInt(2));
        System.out.println("add10(4): " + add10.applyAsInt(4));
        System.out.println("add20(2): " + add20.applyAsInt(2));

        IntUnaryOperator compiled = compiledLambda(7);
        System.out.println("javac lambda(3): " + compiled.applyAsInt(3));

        AtomicInteger box = new AtomicInteger(5);
        IntSupplier reader = referenceCapture(box);
        System.out.println("reference before: " + reader.getAsInt());
        box.set(8);
        System.out.println("reference after: " + reader.getAsInt());
    }
}
~~~

Compile/run from the directory containing the file:

~~~bash
javac --release 17 LambdaLifecycleDemo.java
java LambdaLifecycleDemo
~~~

**Exact stdout (verified with OpenJDK 21, source compiled at Java 17 level):**

~~~text
phase 1: linkage
factory type: (int)IntUnaryOperator
phase 2: capture
phase 3: invocation
  implementation(captured=10, input=2)
add10(2): 12
  implementation(captured=10, input=4)
add10(4): 14
  implementation(captured=20, input=2)
add20(2): 22
javac lambda(3): 10
reference before: 5
reference after: 8
~~~

How to read the output:

- `phase 1: linkage` appears before the factory type: the metafactory call **created the `CallSite`**, whose target has type `(int)IntUnaryOperator`.
- In `phase 2: capture`, calling the same factory twice with `10` and `20` produces two function values with corresponding behavior. No `implementation(...)` line appears yet; that is because the body **has not run yet**.
- The line `implementation(captured=10, input=2)` only appears **after** `phase 3: invocation` when `add10.applyAsInt(2)` is called. At that point, the implementation receives both the captured value `10` and the invocation argument `2`.
- `add10` is called again with input `4` while its captured value remains `10`. `add20` produces a different result because it was created with captured value `20`.
- `compiledLambda(7)` illustrates the same behavior, except **the compiler generates `invokedynamic` automatically**, not via the hand-written `metafactory` call in `main`.
- `reference before/after` shows the function holds a reference to the same `AtomicInteger` and can observe the updated state.

**Do not** conclude from `main` that "the compiler's lambda BSM ran exactly once": the logging across the three phases is printed by the program itself when **calling metafactory directly**. Only `compiledLambda`/`referenceCapture` actually use `invokedynamic` bytecode generated by `javac`.

## 7. Reading `javap` to connect Java source knowledge with bytecode

After compiling the file above, run:

~~~bash
javap -c -p LambdaLifecycleDemo
javap -v -p LambdaLifecycleDemo
~~~

Find the `compiledLambda` method specifically in the `javap -c -p` output. The structure observed when compiling for Java 17 is:

~~~text
static java.util.function.IntUnaryOperator compiledLambda(int);
  Code:
     0: iload_0
     1: invokedynamic ... // applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
     6: areturn
~~~

The `...` replaces the **constant-pool index and specific display metadata**, which may differ across `javac` versions; this is not a requirement to match the entire `javap` stdout byte-for-byte.

Connect the three bytecode lines with the lifecycle:

- `iload_0` pushes the **value of `base`** onto the operand stack.
- `invokedynamic ... applyAsInt:(I)L...IntUnaryOperator;` is the **factory call site**: it takes one `int` (the captured value) and returns an `IntUnaryOperator`.
- `areturn` returns the function object to the caller. There is no `applyAsInt` call in this method yet.

In `javap -v -p`, inspect `Constant pool` and `BootstrapMethods`. With the Java 17 compiler in the example, the entry for `compiledLambda` references `LambdaMetafactory.metafactory` with three static arguments meaning:

~~~text
SAM method type:         (I)I
Implementation handle:   REF_invokeStatic
                         LambdaLifecycleDemo.lambda$compiledLambda$...(II)I
Instantiated method type:(I)I
~~~

`lambda$compiledLambda$...` is an illustrative name of a synthetic method generated by the compiler; the suffix/index part **is not a stable API**. In particular, the BSM static args contain the **MethodHandle describing the implementation**, **not** the value `base=7` of a specific run.

In the bytecode of `referenceCapture`, the call-site descriptor may carry the receiver type:

~~~text
(AtomicInteger)IntSupplier
~~~

The method handle may point to `AtomicInteger.get()`. The receiver object is supplied during **capture**; it is not a parameter of `IntSupplier.getAsInt()` at invocation.

**Note when using `javap`:** the example class also uses string concatenation in `System.out.println`, so the class file may contain bootstrap entries for **`StringConcatFactory`**. Do not assume every `invokedynamic` in the class belongs to `LambdaMetafactory`: check the exact bootstrap name and the call site you are studying.

## 8. How does `samMethodType` differ from `instantiatedMethodType`?

In the `IntUnaryOperator` example without generics, both are `(int)int`. However, with generic functional interfaces, the distinction is very useful.

Example:

~~~java
java.util.function.Function<String, Integer> f =
        text -> text.length();
Integer n = f.apply("hello"); // 5
~~~

This is an **illustrative Java snippet inside a method**, not a standalone runnable program.

After **type erasure**, the `Function.apply` method at the JVM level has the reference signature `(Object)Object`. When the compiler specializes the lambda for `Function<String,Integer>`, the instantiated SAM type may be `(String)Integer` (the level of boxing/implementation types depends on how the compiler generates the implementation).

Therefore, the metadata values have distinct roles:

- **`samMethodType`:** describes the erased interface method signature that the generated function object must implement, e.g. `(Object)Object`.
- **`instantiatedMethodType`:** describes the type constraints to check/convert at invocation, e.g. `(String)Integer`.
- **`implMethod`:** the actual method processing the data, whose type may differ (but must be validly adaptable); it may return a primitive `int` and then box it.
- **`invokedType`:** the factory signature; for a non-capturing lambda, this may be `()Function`. **Do not confuse** the factory type with the generic type of the SAM.

With incompatible input at runtime (e.g. `String` is expected, but a caller invokes through a raw `Function` and passes a different object), the generated adapter/cast may throw `ClassCastException` at invocation. This is not a "re-running linkage" error; linkage already fixed the type structure, while runtime values are checked upon invocation.

Adaptations in `LambdaMetafactory` have specific rules: not every Java conversion is supported, and generic type parameters do not exist intact in bytecode. If writing metafactory calls directly, check the **Javadoc for each type constraint** rather than inferring from source syntax.

## 9. When does capture mean holding a copy, holding a reference, or holding a receiver?

| Expression | Capture in phase 2 | What happens at invocation |
| --- | --- | --- |
| `x -> x + 1` | No captured arguments from the environment | Receives a new `x` then adds 1 |
| `x -> base + x` | Holds **primitive value** `base` | Receives `x` then adds it to the held `base` |
| `() -> box.get()` | Holds **reference** `box` | Reads the **current state** of the object |
| `box::get` | Holds **receiver `box`** of the bound method reference | Calls method `get` on the held object |
| `this::process` | Holds receiver reference `this` | Calls `process` on that object |
| `SomeClass::staticMethod` | Usually no receiver capture needed | Arguments are supplied at invocation |
| `SomeClass::instanceMethod` (unbound) | Does not capture a specific receiver | Receiver is passed as the first SAM argument |

The two expressions `box::get` and `() -> box.get()` may behave very similarly in reading state, but the evaluation and null-check rules of a **bound method reference** do not completely coincide with a lambda body. Do not substitute them mechanically when you need to preserve exact semantics regarding `null` or side effects of the expression to the left of `::`.

**Local variable rule:** when a lambda captures a local variable `int base`, there is no "always-up-to-date pointer" to that local slot. If you want an updatable value, you must capture an object holding the state, and manage synchronization/thread-safety if multiple threads can access it.

## 10. Misconceptions about performance, identity, and lifecycle

**"Every lambda call runs the bootstrap."** False. The BSM links the **`invokedynamic` location**, not each `applyAsInt` call. If the same lambda expression is evaluated multiple times, the target factory may be called multiple times to create or retrieve a function object.

**"Capture definitely creates a new instance."** False. The `LambdaMetafactory` Javadoc does not guarantee identity or fresh allocation. For non-capturing lambdas, reuse is very natural; but even in other cases, you should not build business rules on `==` of function objects.

**"Capturing an object means snapshotting the entire object state."** False. A captured reference only holds the reference; the object can mutate. If you need a snapshot, extract the required values into an immutable value object at lambda creation time.

**"`() -> sideEffect()` executes `sideEffect` when creating the lambda."** False. That is the lambda body; `sideEffect` only runs upon SAM invocation. However, **expressions evaluated to produce captured receivers/arguments** can have side effects right when creating the method reference or preparing captured values. Distinguish between the two.

**"A lambda has full generics in the JVM."** False. Bytecode uses the erased SAM signature and instantiated type metadata to set up valid casts/adapters; you should not infer from `Function<String,Integer>` that the runtime creates a class retaining full generic parameters like a reified object type.

**"JIT optimizations are an API obligation."** False. The JVM may inline, use hidden classes, or optimize the function factory, but it does not guarantee generated class names, object counts, or machine instruction sequences. Rely only on the contract of `CallSite` and the functional interface.

**"Lambdas are always serializable."** False. `LambdaMetafactory.altMetafactory` supports flags such as `FLAG_SERIALIZABLE`, `FLAG_MARKERS`, and `FLAG_BRIDGES` when marker interfaces or bridge methods are needed, but not every lambda can be serialized and one should not implicitly rely on implementation details. Deserializing a lambda requires supporting mechanisms from the capturing class.

## 11. Classifying errors by phase

| Phase | Symptom | Check |
| --- | --- | --- |
| **Linkage** | `LambdaConversionException` when calling metafactory directly | Does `Lookup` have permission? Does `factoryType` return an interface? Is `implMethod` a direct handle? Does `K + N = M` hold and do the types match? |
| **Linkage via JVM** | `BootstrapMethodError` or corresponding resolution error | Are the BSM reference and static args valid? Does `CallSite` match the `invokedynamic` descriptor? |
| **Capture** | `WrongMethodTypeException` when calling `factory.invokeExact` with the wrong descriptor (in manual code) | Compare `site.type()` with the **captured parameters** and factory return type |
| **Capture** | `NullPointerException` with a `null` bound instance receiver | Check the receiver evaluated/passed at capture |
| **Invocation** | `ClassCastException` when the generic SAM adapter checks a value of the wrong type | Identify the erased SAM type, instantiated type, and the actual value's type |
| **Invocation** | `NullPointerException` or exception thrown by the implementation method itself | Check input data, captured object state, and the body's stack trace |

A `ClassCastException` or `NullPointerException` **does not by itself prove** it is a `LambdaMetafactory` error; the implementation method itself may throw them. Check the stack trace and origin location.

Diagnose accurately in order:

1. Find the **`invokedynamic` instruction** in `javap -c -p` and the bootstrap entry in `javap -v -p`.
2. Note `factoryType`, `samMethodType`, `implMethod.type()`, and `instantiatedMethodType`.
3. Compare the number of captured arguments `K` with the arity difference between the implementation and the SAM.
4. Distinguish static args of the bootstrap from dynamic captured values on the operand stack.
5. Ask whether the error occurred **during linking**, **when creating the function object**, or **when calling the SAM**.
6. For a captured reference, check current state, nullability, and thread-safety.
7. Do not use BSM invocation counts or generated class names to infer object counts or invocation counts.

## 12. Self-check on understanding the three phases

**Question 1.** With `makeAdder(10)` and `makeAdder(20)`, must there be two separate bootstrap linkages? Do they have the same captured value?  
**Answer:** The same **`invokedynamic` location** in `makeAdder` typically only needs to be linked once after succeeding; the capture calls carry **two different values**, `10` and `20`.

**Question 2.** Does the BSM receive the `base=10` value of the `makeAdder(10)` call via the `samMethodType` parameter?  
**Answer:** No. `samMethodType` is static metadata about the SAM signature; the `base` value goes to the **target factory** at capture.

**Question 3.** Implementation handle `(int,int)int`, SAM type `(int)int`, factory type `(int)IntUnaryOperator`. How many captured parameters are there?  
**Answer:** `M=2`, `N=1`, so `K=1`. The first `int` parameter of the implementation is the captured value, and the second `int` parameter is the invocation argument.

**Question 4.** After creating a function object with `base=10`, does calling `applyAsInt(3)` three times require re-running capture?  
**Answer:** No. The same function value reuses the captured `10` and receives a new invocation argument on each call (here all are `3`).

**Question 5.** `box::get` is holding `AtomicInteger(5)`. If `box.set(8)` is called later, must the function continue returning 5?  
**Answer:** No. It holds a **reference to the object**, so calling `getAsInt()` can see the current state `8` (in the verified program, it prints 8).

**Question 6.** Why might `javap` show `invokedynamic` in `compiledLambda`, whereas a call `compiled.applyAsInt(3)` is typically `invokeinterface`?  
**Answer:** `invokedynamic` serves factory/capture; `invokeinterface` invokes the SAM on the obtained function object.

**Question 7.** Should `lambdaA == lambdaB` be used to determine whether a user is in the same session?  
**Answer:** No. Lambda object identity is not a guaranteed contract; use an explicitly managed business identifier.

## Java 17 Standard References

- [`LambdaMetafactory`: Linkage, Capture, Invocation and `metafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html)
- [`MethodHandle` and `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [`CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [JVMS 17 — `invokedynamic` instruction](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
- [JVMS 17 — resolution of dynamically-computed call sites](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JLS 17 — Lambda Expressions, `15.27`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27)
