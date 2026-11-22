# How Are Classes, Objects, and Existing State Preserved During Redefinition?

**Java Instrumentation** allows replacing **the bytecode definition of a class already loaded by the JVM** using `Instrumentation.redefineClasses(...)`. A common misconception is that "replacing the definition" means the JVM destroys the old class, creates a new class, reinitializes static fields, and recreates every object on the heap.

According to the contract of Java Instrumentation and the JVM Tool Interface (JVMTI), **a successful redefinition preserves existing instances and their field state; it does not automatically rerun the class initializer; and static fields retain their pre-operation values**. At the same time, **new method invocations use the new bytecode version**, while stack frames of a method **currently executing** continue using the old bytecode version. That is why the same object can finish an in-progress call using the old logic and immediately afterward execute another call using the new logic.

This lesson belongs to the **Redefinition** topic and focuses directly on the question: *How do class identity, object identity, instance fields, static state, and active method invocations change or remain preserved?* The lesson includes a runnable JDK 17+ Java agent using **real redefinition**, along with demonstrations of state, identity, `<clinit>`, and active stack frames.

## 1. Seeing the Essence Clearly: Replacing Method Definitions, Not Objects

Before redefinition:

~~~text
Class object:   LiveCounter.class (Class<?> C)
       |
       +-- static shared = 345, initRuns = 1
       |
       +-- method compute(): return value + 1
       |
       +-- instance A: { value = 7  }
       +-- instance B: { value = 12 }

An inFlight() invocation has an active stack frame running old code.
~~~

The JVM receives **new class bytes** for the same class C:

~~~text
Instrumentation.redefineClasses(
    new ClassDefinition(C, replacementBytes)
)
                      |
              JVM verifies the class
                      |
              New method definitions
~~~

After redefinition succeeds:

~~~text
Class object:   still C
       |
       +-- static shared = 345, initRuns = 1    (NOT automatically reset)
       |
       +-- method compute(): return value + 1000 (new invocations)
       |
       +-- instance A: still the exact same object A, { value = 7  }
       +-- instance B: still the exact same object B, { value = 12 }

The inFlight() frame that started earlier -> continues old code.
New compute() invocations on object A/B -> use new code.
~~~

In this example, the value `shared = 345` was deliberately set by the application **before** redefinition. Even though the replacement class file contains initialization code `shared = 999`, the JVM **does not automatically rerun that initialization**. Similarly, constructors are not rerun for existing objects.

**Four points must be kept distinct:**

1. **Class identity**: the target's `Class<?>` object continues to be used; no new class is created merely because of a redefine.
2. **Object identity**: references to existing instances still point to those exact same instances; they are not cloned or recreated.
3. **Heap state**: existing instance/static field values are not reset by the redefine operation.
4. **Executable method versions**: method bodies **can be replaced**, but active stack frames do not automatically switch mid-execution to the new code.

You should not oversimplify this as "redefinition does nothing to a running program." On the contrary, after a successful redefine, **new invocations can markedly change behavior**, and therefore can **mutate state going forward** according to the new logic.

## 2. Class Identity Is Preserved

In the JVM, a binary name such as `com.example.LiveCounter` alone is **not enough** to uniquely identify a class: the class loader that defines it also matters. Within the same class loader, a defined class has a `Class<?>` representing its runtime identity.

Given:

~~~java
Class<?> before = liveCounter.getClass();

// Redefine this same Class object using ClassDefinition(before, newBytes).

Class<?> after = liveCounter.getClass();
boolean sameClass = before == after;
~~~

When the operation succeeds according to the contract, `sameClass` remains `true`. The snippet above is an **illustrative fragment**; it requires a `liveCounter` instance along with a prepared redefine call. Complete runnable code is in Section 7.

### Redefinition Is Not the Same as Loading a Same-Named Class with Another Class Loader

Two different cases:

| Action | Identity outcome |
| --- | --- |
| `redefineClasses(new ClassDefinition(existingClass, bytes))` | The definition of **the exact existing class** is updated; no new class identity is created |
| Creating `new URLClassLoader(...)` and loading a class file with the same binary name | Creates a **different class** if that loader actually defines the class; it may not be castable across the loader boundary |
| Starting another JVM with a new JAR | All classes/instances/state are created for another process; not a redefinition of the old process |
| Using reflection to invoke a method on an old instance after redefine | Still interacts with the **old object**, and the behavior of new method calls follows the current definition |

Therefore, to check class identity, use `before == after` (reference equality), not just `getName()`; two classes in different loaders can still share the same name. Do not use `System.identityHashCode(...)` as the sole proof of being the same object; two distinct objects can theoretically collide in identity hash. Use `==` in a direct verification test.

### Implications for Existing References and Types

A variable already holding a reference to `LiveCounter` **does not need to be updated** to invoke redefined methods. Those references remain valid and the object still has the same runtime type as before. Collections, caches, dependency-injection containers, or object graphs holding old objects are not automatically replaced by redefinition.

This is a major benefit for runtime logic fixes, but it also constrains us: **there is no automatic migration mechanism** to update all existing instances to a completely new field schema.

## 3. Existing Instances Are Not Recreated; Their Fields Retain Their Values

Suppose:

~~~java
LiveCounter a = new LiveCounter(7);
LiveCounter b = new LiveCounter(12);
Object sameReference = a;
~~~

After redefining the class:

~~~java
boolean identityPreserved = (a == sameReference);
int stillSeven = a.getValue();
int stillTwelve = b.getValue();
~~~

This is a **code fragment placed inside a program that has already defined `LiveCounter` and successfully redefined it**. With `getValue()` having an unchanged body as in the demo below, the respective values remain `7` and `12`.

**Why?** The heap already holds the objects with their field slots; replacing method definitions is not a `new`, `clone`, Java serialization/deserialization, or object reinitialization operation. According to JVMTI, instances of the redefined class are unaffected and their fields retain their previous values.

However, two overgeneralizations must be avoided:

- **There is no guarantee that object state will remain identical forever afterward**. A new method may write `this.value = ...` when invoked; in that case the state changes due to **executing new code**, not because redefinition reset the state.
- **There is no guarantee that all business data remains compatible**. If new code interprets the `int status` field differently from old code, the JVM still preserves the old bit-pattern, but application logic may no longer be correct. The JVM does not automatically migrate business data.

### Are Constructors Rerun?

**No.** Existing objects are not passed through a constructor again merely because their class was redefined.

If the constructor body in the new bytes is validly changed, **new object creations** will execute the new constructor version, while existing instances are not recreated. In the demo, the constructor keeps the same body to isolate the redefinition effect of `compute()`.

### Why Can't Arbitrary New Fields Be Added?

Standard redefinition in JVM TI has constraints on **schema/class structure**. You cannot simply add a field `int generation;` and expect the JVM to expand the layout of all existing objects. Changes such as adding/removing/renaming fields, changing method signatures, or altering inheritance relationships are generally **not permitted**; Section 8 presents the specific limits.

If new state is needed for instrumented logic, consider an agent-managed **side table** (with an appropriate lifetime and identity strategy), or releasing an application version with explicit migration, rather than relying on HotSwap as a schema-change mechanism.

## 4. Static Fields Do Not Automatically Reset and Class Initializers Do Not Rerun

This is a common point of confusion when looking at the source of the replacement class.

For example, the original class:

~~~java
public static int initRuns;
public static int shared = 100;

static {
    initRuns++;
    System.out.println("clinit=original");
}
~~~

The replacement class compiled from source has:

~~~java
public static int initRuns;
public static int shared = 999;

static {
    initRuns++;
    System.out.println("clinit=patched");
}
~~~

Both snippets are **excerpts of two versions of the same class**, not two declarations coexisting in one file. At the bytecode level, declarations with initializers belong to the static initialization code `<clinit>`.

If the class has already been initialized earlier, and business code sets:

~~~java
LiveCounter.shared = 345;
~~~

then after a successful redefine:

- `LiveCounter.shared` **remains 345**, not 999.
- `LiveCounter.initRuns` **remains 1**, not automatically becoming 2.
- The log `clinit=patched` does not appear **merely because of the redefine call**.

The reason: the redefinition contract explicitly states that it **does not cause class reinitialization**, aside from the JVM's normal initialization mechanism if an independent reason exists for the class to be initialized. Redefinition is not a state-reset tool.

### What If the New Class File Changes How Static Values Are Computed?

Two types of changes must be distinguished:

| Change in new bytes | What happens |
| --- | --- |
| Changing the value assigned in `<clinit>` from `100` to `999` | For an already-initialized class, **`<clinit>` does not automatically rerun**; the existing static value is kept |
| Changing the body of a static method `total()` from `return shared + 1` to `return shared + 1000` | **New invocations** use the new method body and read the **existing `shared` value** |
| Application explicitly calls `LiveCounter.shared = 0` after redefine | The value changes to 0 because of **a new assignment**, not automatically due to redefine |
| Agent explicitly uses reflection/VarHandle to assign a static field | State can change due to **another action by the agent**; not the default semantics of `redefineClasses` |

For example, if `shared = 345`, a new call to `total()` with the replaced body will return `1345`. New code and old state can **coexist**; that is precisely what must be tested for business compatibility.

### Static Final and Compile-Time Constants

Be careful when a class has a `static final` primitive or `String` that is a **constant variable** per the JLS. Callers already compiled by `javac` may use the **inlined constant value**, instead of reading the field at runtime. Therefore, changing the source of a constant in the replacement class is **not sufficient** to force already-loaded callers to see the new value. Moreover, a redefine operation does not automatically reset static fields.

Do not equate "new method body is invoked" with "every place using a static constant immediately updates." To allow configuration to change at runtime, design an explicit state-reading path (for example, an accessor method reading a mutable field), and test against compiled callers properly.

## 5. New Method Bodies Apply to New Invocations; Running Frames Continue the Old Body

This is the most important distinction when an application has multiple threads or long-running methods.

According to Java Instrumentation:

- When a method is redefined while there are **active stack frames**, those frames continue executing **the bytecode of the original method version**.
- **New invocations** of the method made after redefinition will use **the new method version**.

Diagram:

~~~text
Thread A: enters LiveCounter.inFlight() [bytecode v1]
          |
          | waits on CountDownLatch
          |
Thread B: redefines LiveCounter [v2]
          |
          +----> v2 is installed successfully
          |
Thread A: resumes old inFlight() frame [v1] -> returns v1-result

Thread A/B: NEW inFlight() call          [v2] -> returns v2-result
~~~

There is no "instruction pointer swap between two bodies" inside a running frame. If the old method is partway through a computation, the JVM cannot simply jump it to a new bytecode offset while guaranteeing valid stack/locals and control flow.

### An Old Frame Can Still Call a New Method

If an old frame, upon resuming execution, **calls another method**, that call is a new invocation and follows the rule of using the current method definition. Therefore, **a single stack can contain frames from the old version and frames invoked under the new version**. Do not infer that the entire thread is "locked" onto the old version until the thread terminates.

Similarly, the object operated on by the old frame is still the existing object. Old code and new code can read/write the same state. This is why concurrency-sensitive logic patches require stronger testing than just checking a single `compute()` value after redefinition.

### Is It Necessary to Stop All Threads?

The Java Instrumentation API does not require the caller to manually stop all threads before calling `redefineClasses`. The JVM performs the synchronization/consistency work according to its implementation. However, a business system may still need **application-level quiescence** if a patch changes interaction protocols between methods, transactions, or shared state.

Do not treat redefinition as an automatic transaction mechanism for running business logic. The atomicity of **updating class bytes** is different from every concurrent in-progress request seeing the same business logic version from start to finish.

## 6. API and Prerequisites Before Redefining

Java 17+ API:

~~~java
void Instrumentation.redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException
~~~

And creating a replacement definition:

~~~java
ClassDefinition replacement =
        new ClassDefinition(targetClass, newClassFileBytes);

instrumentation.redefineClasses(replacement);
~~~

This is an **illustrative fragment**, requiring an `Instrumentation instrumentation` provided by the JVM to a Java agent, a `Class<?> targetClass`, and `byte[] newClassFileBytes` with the matching binary name.

### Prerequisites

1. **The Agent JAR** must declare `Can-Redefine-Classes: true` in its manifest.
2. The JVM must actually have the redefinition capability; check `inst.isRedefineClassesSupported()`.
3. The target class must be considered modifiable by the JVM; check `inst.isModifiableClass(targetClass)`.
4. The new bytes must represent **the exact binary name** of the class to be replaced and be a valid class file using a class-file version accepted by the JVM.
5. The changes must fall within the JVM's **redefine limits**, especially avoiding prohibited schema changes.
6. When transformers are registered, the bytes of the redefine call may also pass through `ClassFileTransformer`s per the contract. The final result after transforms must also be valid.

`isRedefineClassesSupported()` and `isModifiableClass(...)` are **two separate checks**. Even if the JVM capability is true, if the class is a primitive/array or belongs to a group marked unmodifiable by the VM, it still cannot be redefined. Conversely, a modifiable class cannot compensate for a JVM/agent lacking the redefinition capability.

### Redefine vs. Retransform

| Question | Redefinition | Retransformation |
| --- | --- | --- |
| API | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
| Source of class bytes | **Caller supplies new bytes** matching the target | JVM starts from appropriate original bytes and reapplies/reruns transformers |
| Capability | `Can-Redefine-Classes` | `Can-Retransform-Classes` |
| Common use case | Hot fix / replacing method implementations from a compiled class file | Reapplying bytecode instrumentation on already-loaded classes |
| Preserves instances, static state, and old frames? | Yes, per the class redefinition contract | Has corresponding semantics regarding state and active frames |
| Automatically reruns constructors or `<clinit>`? | No | No |

**Do not use a new class loader as a shortcut** to recreate the state of an old class: loading a same-named class into a new loader is a different matter and does not update methods of objects already loaded by the old loader.

## 7. Complete Example: Redefining a Class with Existing Objects and Active Frames

The example consists of two versions with **the same binary name `LiveCounter`** compiled into **two separate directories**, an agent `RedefineAgent`, and the program `RedefineStateDemo`. It demonstrates simultaneously:

- The old instance keeps **the same reference**, the same `Class<?>`, and retains its `value` field.
- The static field `shared` and counter `initRuns` do not reset.
- The replacement class file has a different static initializer, yet that initializer **does not rerun**.
- The `inFlight()` method started **before** redefinition still returns a result according to the old body.
- A new call to a method on **the same old instance** uses the new body.
- An instance created **after** redefinition also uses the new body.

Use JDK **17 or later**. The example was compiled and actually run on **Zulu OpenJDK 24.0.2**. It must be run on a JVM that supports redefinition; otherwise, the agent explicitly throws a capability error instead of pretending the patch was applied.

### 7.1. Directory Layout

Create the directories and files:

~~~text
redefine-state-example/
├── old/
│   └── LiveCounter.java
├── new/
│   └── LiveCounter.java
├── app/
│   ├── RedefineAgent.java
│   └── RedefineStateDemo.java
└── agent.mf
~~~

The two `LiveCounter.java` files contain **two different versions of the same class**, **not placed together in a single javac output directory**. Both versions must have the same fields, method names/descriptors, and corresponding flags; only the method bodies and `<clinit>` code are changed for demo purposes.

### 7.2. File old/LiveCounter.java

~~~java
import java.util.concurrent.CountDownLatch;

public final class LiveCounter {
    public static int initRuns;
    public static int shared = 100;

    static {
        initRuns++;
        System.out.println("clinit=original");
    }

    private int value;

    public LiveCounter(int value) {
        this.value = value;
    }

    public int getValue() {
        return value;
    }

    public int compute() {
        return value + 1;
    }

    public int inFlight(CountDownLatch entered, CountDownLatch proceed) {
        entered.countDown();
        try {
            proceed.await();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(interrupted);
        }
        return value + 10;
    }

    public static int total() {
        return shared + 1;
    }
}
~~~

Note that `inFlight()` has two latches:

- `entered.countDown()` signals the main thread that the worker thread **has entered the v1 method**.
- `proceed.await()` keeps the v1 frame active.
- `return value + 10` is **after** the wait point. When the thread resumes after redefinition, per the contract this frame still executes v1 logic.

### 7.3. File new/LiveCounter.java

Keep the class name, fields, signatures, and modifiers unchanged; change **the execution body**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class LiveCounter {
    public static int initRuns;
    public static int shared = 999;

    static {
        initRuns++;
        System.out.println("clinit=patched");
    }

    private int value;

    public LiveCounter(int value) {
        this.value = value;
    }

    public int getValue() {
        return value;
    }

    public int compute() {
        return value + 1000;
    }

    public int inFlight(CountDownLatch entered, CountDownLatch proceed) {
        entered.countDown();
        try {
            proceed.await();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(interrupted);
        }
        return value + 1000;
    }

    public static int total() {
        return shared + 1000;
    }
}
~~~

The differences are `shared = 999`, the `clinit=patched` log, and the bodies of `compute`, `inFlight`, `total`. **Do not mistake** changing `shared = 999` as causing the JVM to automatically reassign the static field to 999. It will not execute `<clinit>` a second time when redefining an already-initialized class.

### 7.4. File app/RedefineAgent.java

This is an agent loaded at startup via `premain`. Only code with `Instrumentation` provided by the JVM can call `redefineClasses`:

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agentReady=true");
    }

    public static void replace(Class<?> target, Path replacementClass)
            throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent:redefine-agent.jar");
        }
        System.out.println("redefineSupported="
                + inst.isRedefineClassesSupported());
        System.out.println("modifiable=" + inst.isModifiableClass(target));
        if (!inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException("Class redefinition is unavailable");
        }
        inst.redefineClasses(new ClassDefinition(
                target, Files.readAllBytes(replacementClass)));
        System.out.println("redefineApplied=true");
    }
}
~~~

The replacement file contents are read via `Files.readAllBytes`. The agent **only** calls `redefineClasses` after checking capability and modifiability. The `redefineApplied=true` log only appears after the call completes without throwing an exception.

In production, you must specifically handle `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, `VerifyError`, and class loading/linkage errors. The example lets exceptions propagate outward to make it easy to distinguish an operation failure from a program that appears to run normally without actually redefining.

### 7.5. File app/RedefineStateDemo.java

~~~java
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class RedefineStateDemo {
    public static void main(String[] args) throws Exception {
        LiveCounter existing = new LiveCounter(7);
        LiveCounter another = new LiveCounter(12);
        Object originalReference = existing;
        Class<?> originalClass = existing.getClass();
        LiveCounter.shared = 345;

        System.out.println("beforeOldMethod=" + existing.compute());
        System.out.println("stateBefore=" + existing.getValue());
        System.out.println("sharedBefore=" + LiveCounter.shared);
        System.out.println("initBefore=" + LiveCounter.initRuns);

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);
        AtomicInteger inFlightResult = new AtomicInteger();
        Thread worker = new Thread(() ->
                inFlightResult.set(existing.inFlight(entered, proceed)));
        worker.start();
        entered.await();
        System.out.println("inFlightEntered=true");

        RedefineAgent.replace(LiveCounter.class, Path.of("new", "LiveCounter.class"));

        System.out.println("sameClass=" + (existing.getClass() == originalClass));
        System.out.println("sameObject=" + (existing == originalReference));
        System.out.println("stateAfter=" + existing.getValue());
        System.out.println("sharedAfter=" + LiveCounter.shared);
        System.out.println("initAfter=" + LiveCounter.initRuns);

        proceed.countDown();
        worker.join();
        System.out.println("inFlightOldFrame=" + inFlightResult.get());
        System.out.println("existingNewMethod=" + existing.compute());
        System.out.println("anotherNewMethod=" + another.compute());
        System.out.println("newObjectNewMethod=" + new LiveCounter(4).compute());
        System.out.println("staticNewMethod=" + LiveCounter.total());
        System.out.println("newInvokeInFlight="
                + existing.inFlight(new CountDownLatch(0), new CountDownLatch(0)));
    }
}
~~~

The sequence is deterministic:

1. Create **two existing objects** from the old version; retain `originalReference` and `originalClass`.
2. Assign `shared = 345`, mutating static state after the class has been initialized.
3. Start the worker into `inFlight(...)` of **v1**. The `entered` latch confirms the worker entered the method before main calls redefine.
4. Perform the redefine using the bytes of the file in the `new/` directory.
5. Verify **identity/state** immediately after redefinition completes.
6. Release the latch so the old frame finishes; observe `inFlightOldFrame=17` (= `7+10`).
7. Invoke again on existing objects and create a new object; observe the new body (= `value+1000`).

Using `CountDownLatch` makes starting the old frame and the timing of redefinition deterministically ordered; it avoids the "sleep 100 ms and hope the worker is running" style of demo that depends on machine speed.

### 7.6. File agent.mf

Create the manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
~~~

The file needs a **trailing blank line** per manifest syntax. This is redefinition, so `Can-Redefine-Classes: true` is used; `Can-Retransform-Classes: true` is not needed for this example.

### 7.7. Compiling and Running

From the root directory `redefine-state-example/`, with **JDK 17+**:

~~~bash
javac -d old old/LiveCounter.java
javac -d new new/LiveCounter.java
javac -cp old -d app app/RedefineAgent.java app/RedefineStateDemo.java
jar --create --file redefine-agent.jar --manifest agent.mf -C app RedefineAgent.class
~~~

Run on **Windows PowerShell**:

~~~powershell
java -javaagent:redefine-agent.jar -cp "old;app" RedefineStateDemo
~~~

Run on **Linux/macOS Bash** (classpath separator is `:`):

~~~bash
java -javaagent:redefine-agent.jar -cp 'old:app' RedefineStateDemo
~~~

**Note on output directories:** `-d old` and `-d new` place the two versions of `LiveCounter.class` into two separate directories. When running, the classpath contains **old** and **app**, **not new**. The JVM loads the original class from `old`; the agent only uses the bytes in `new` to redefine that class. If you put the `new` directory on the classpath first, you will invalidate the test scenario.

### 7.8. Verified Stdout on Zulu OpenJDK 24.0.2

~~~text
agentReady=true
clinit=original
beforeOldMethod=8
stateBefore=7
sharedBefore=345
initBefore=1
inFlightEntered=true
redefineSupported=true
modifiable=true
redefineApplied=true
sameClass=true
sameObject=true
stateAfter=7
sharedAfter=345
initAfter=1
inFlightOldFrame=17
existingNewMethod=1007
anotherNewMethod=1012
newObjectNewMethod=1004
staticNewMethod=1345
newInvokeInFlight=1007
~~~

Explanation of **the key pieces of evidence**, rather than just looking at the three "true" lines:

| Output | What does it prove? |
| --- | --- |
| `clinit=original` printed only once | The original class was initialized once; no `clinit=patched` callback occurred on redefinition |
| `sameClass=true` | The existing object retains the same `Class<?>` object |
| `sameObject=true` | The existing object is still the exact original reference |
| `stateAfter=7` | The `value` field of the old instance was not reset |
| `sharedAfter=345` | Prior static state was not replaced by the new initializer value 999 |
| `initAfter=1` | The class initializer did not rerun |
| `inFlightOldFrame=17` | The `inFlight` frame that started before redefine continued the v1 body, returning `7+10` |
| `existingNewMethod=1007` | A new call on **the same existing object** runs the v2 body, returning `7+1000` |
| `anotherNewMethod=1012` | Another existing object also invokes the v2 body |
| `newObjectNewMethod=1004` | An object newly created after redefine uses the v2 body |
| `staticNewMethod=1345` | The v2 static method runs against the **old** static field with value 345 |
| `newInvokeInFlight=1007` | A new `inFlight` call executes the v2 body; different from the earlier old frame |

The lines `redefineSupported=true` and `modifiable=true` are **environment-dependent**. If the JVM or agent does not support them, the demo proactively reports an error; do not assume those two values are a rule for every JVM.

### 7.9. Proving with Code Rather Than Just Method Names

Reading the two sources `old/LiveCounter.java` and `new/LiveCounter.java` alone does not prove redefinition actually occurred. However, the stdout combining **capability flags**, the **redefineApplied** log, the **Class identity** check, and the **active frame vs. new invocation** divergence forms an independent verification chain: the JVM loaded v1, had a waiting v1 frame, applied v2 bytes, and then invoked v2 on the existing object.

Having `inFlightOldFrame=17` while `newInvokeInFlight=1007` is especially important: it confirms you cannot describe redefinition as an operation where "all code on all threads immediately switches to v2."

## 8. Why Are the Following Class File Modifications Disallowed?

Redefinition per JVM TI is **not** a mechanism to replace the entire schema of a class as during initial loading. Common restrictions in the specification:

- **Cannot add/remove/rename fields**.
- **Cannot add/remove/rename methods**.
- **Cannot change method signatures**.
- **Cannot change class/method modifiers** subject to the constraints stated in JVMTI.
- **Cannot change superclass / interfaces** or inheritance relationships.
- **Cannot change structural attributes** such as `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- The final class file must be valid and have a version/type information accepted by the JVM.

You can replace **method bodies**, the constant pool, and attributes **within permitted limits**. The mere fact that `javac` produces a valid `.class` **does not mean** that file can be used to redefine an existing class. If you add a new field to the replacement source, the compiler still compiles it; the error only surfaces when the JVM checks the redefine.

### Conceptual Examples of Valid and Invalid Changes

| Intent | Assessment in standard redefinition |
| --- | --- |
| Changing `compute()` body from `value+1` to `value+1000` | **Usually valid** if schema and class bytes are valid |
| Changing static method `total()` body | **Usually valid**; existing static state is preserved |
| Changing `<clinit>` code from assigning 100 to 999 | The bytes may differ, but **the initializer does not rerun** |
| Changing constructor body while keeping signature | May be valid if constraints are met; **existing objects do not rerun the constructor** |
| Adding `int newField;` | **Invalid** under standard structural limits |
| Removing `getValue()` or changing its return type | **Invalid** |
| Changing `private int value` to `long value` | Changes field descriptor/structure, **invalid** |
| Changing a `final` class to non-final or adding an interface | Changes modifiers/hierarchy, **invalid** |
| Changing `Record`/`PermittedSubclasses` of an already-loaded class | Restricted per JVMTI |

**Warning**: some specialized JVMs/tools offer extended HotSwap capabilities, but do not treat them as **portable** behavior of `java.lang.instrument.Instrumentation.redefineClasses` on standard JVMs. When full-schema hot reload is needed, evaluate a dedicated solution rather than implicitly relying on standard redefinition.

## 9. Multi-Class Redefine in One Call: Atomicity of the Operation, Not a Business Transaction

`Instrumentation.redefineClasses(ClassDefinition...)` accepts **multiple `ClassDefinition`s** in a single call so that interdependent classes can be replaced together:

~~~java
inst.redefineClasses(
        new ClassDefinition(ServiceA.class, bytesForA),
        new ClassDefinition(ServiceB.class, bytesForB));
~~~

This is **illustrative code**, requiring `Instrumentation inst`, two `Class<?>` instances, and prepared byte arrays. If one final class file is invalid or the operation fails, the contract specifies that **no class in that call is successfully redefined**. That is useful when updating logic spanning multiple classes.

However, do not misunderstand this as a distributed/business transaction:

- Requests already partway through execution before the operation can still hold **old active frames**.
- Data in databases, caches, or the heap **does not roll back** merely because redefinition succeeded or failed.
- Code in transformers, loggers, or agents may already have produced side effects during processing.
- New methods invoked **after** installing the class bytes can mutate state according to the new logic, while old requests still finish under the old logic.

For logic fixes involving multi-step protocols, you may need application-level **quiescence**, versioning, or compatibility windows. The JVM only guarantees the specified semantics for updating class definitions.

## 10. Distinguishing "State Is Preserved" from "State Is Compatible with New Code"

Suppose v1 stores monetary amounts in **dong**, while v2 interprets the same `amount` field as **thousands of dong**. The JVM preserves the field bit-for-bit, but the business meaning has changed. This is a real risk when patching logic on existing objects.

| Type of state | What does the JVM preserve? | What must the application ensure itself? |
| --- | --- | --- |
| Primitive instance fields | Values stored in existing instances | New code interprets old values with the right meaning |
| Reference instance fields | Existing references and object graphs remain intact | Do not assume the graph has been migrated |
| Static mutable fields | Values held at the time of redefine | Synchronization, visibility, and invariants of new state |
| Object locks / active synchronization | Object identity remains the existing object | New code does not break old deadlock/lock-ordering invariants |
| Active method frames | Continue the bytecode version entered | New code is compatible with interactions between old and new frames |
| Constructor side effects | Not rerun for existing objects | Do not assume every object was initialized by the v2 constructor |
| Class initializer side effects | Not rerun merely due to redefine | Do not rely on v2 `<clinit>` to migrate config or register services |

The immutability of **state at the moment of redefine** does not eliminate the effects of the garbage collector, other threads, or normal assignments. For example, if another thread writes to a field concurrently, the resulting state under the Java Memory Model depends on the program; redefinition does not create an atomic snapshot of all fields for application code.

### What About State Outside Fields?

Objects can hold resources outside the JVM heap such as file descriptors, network connections, native handles, or sessions in external systems. Redefinition **does not automatically close/reopen** those resources and does not guarantee they adapt to the v2 algorithm. Nor does it automatically alter the state of databases, message queues, transactions, or schedulers. A safe hot fix must also consider external state if the new method body interacts with it differently.

## 11. When Do You Still See Old Bytecode?

There are three distinct causes that are often conflated:

1. **Active stack frame**: a method entered before redefine continues the old bytecode, per the contract.
2. **Wrong class redefined**: the target `Class<?>` belongs to a different loader than the class you are observing; the class name may match, but the identity differs.
3. **Redefine failed**: missing capability, unmodifiable class, invalid class bytes, or prohibited structural change; the new method body was never installed.

Therefore, you must check precisely:

~~~text
1. Does the JVM/agent support redefine?
2. Is it the exact Class<?> of the class loader in use?
3. Is that class modifiable?
4. Does the replacement .class file have the right binary name and structure?
5. Did redefineClasses(...) return successfully?
6. Is the observed call an old ACTIVE FRAME or a NEW INVOCATION?
7. Did the new code mutate state after the redefine?
~~~

A log saying "redefine requested" or "agent attached" is not enough to prove the bytes were installed. Avoid relying solely on reading source files on disk: the JVM may have loaded a different version, or the class may have been further transformed by other transformers.

## 12. Impact on Reflection, Proxies, Caches, and Class Loaders

Redefinition **is not class unloading/reloading**, so the identity of the target class and existing objects is preserved. However, you must distinguish **what is guaranteed by the contract** from reflection/caching details that a framework implements on its own:

- `obj.getClass() == savedClass` remains true in a standard redefinition of that same class.
- References in `List<LiveCounter>`, other fields, and dependency injection containers still point to the old objects.
- Method handles, reflection objects, compiled call sites, or JIT optimizations may be managed and adapted by the JVM/runtime via its own mechanisms; do not argue that a third-party library's metadata cache is **guaranteed** to be refreshed merely because of a redefine.
- A framework that caches bytecode analysis, annotations, or method bodies may require its own invalidation, depending on its design. Class-file attributes may be updated during redefinition, but caches outside the JVM have no such automatic contract.
- If a plugin attempts to reload the same binary name under another class loader, that is a **new class identity**, not a modification of the old identity; casting/visibility must be analyzed according to class loader boundaries.

When testing instrumentation with multiple class loaders, identify targets by **the actual `Class<?>` object** and its loader, not just by the class name string. Also avoid accidentally redefining a copy of the class from a test loader instead of the production loader serving requests.

## 13. Errors and Diagnostic Workflow

| Error/symptom | Accurate explanation | How to handle |
| --- | --- | --- |
| `isRedefineClassesSupported() == false` | JVM/agent lacks capability | Check the manifest and JVM implementation |
| `isModifiableClass(target) == false` | Target class cannot be redefined/retransformed | Choose another target; do not try to force primitives/arrays |
| `UnmodifiableClassException` | A target cannot be modified | Check each `Class<?>` before calling |
| `UnsupportedOperationException` | May lack capability or have a prohibited schema change | Compare old/new class structures and capability |
| `NoClassDefFoundError` during redefine | Class file name does not match target name | Ensure target binary name/class loader are correct |
| `ClassFormatError` | Invalid class bytes | Check build/transformer output and verification tools |
| `UnsupportedClassVersionError` | Class-file version not supported by the JVM | Compile with the right target release |
| `VerifyError` / `LinkageError` | Bytecode/linkage issue | Check instructions, stack maps, references |
| New method is used, but static value is still old | **Per contract**: static fields do not reset | Migrate state with dedicated application logic if truly needed |
| `clinit=patched` does not appear | **Per contract**: initializer does not rerun | Do not use this log to infer redefine failed |
| One thread still returns old method result | May have an **active frame** of the old version | Distinguish running frames from new invocations |
| Old object is still the same object | **Per contract** | Use `==` to confirm identity |
| New class from another loader cannot be cast | Different runtime class identity | Distinguish redefinition from new class loading |
| App logic changes state after redefinition | The v2 method executes and may assign state | Inspect the new code; do not treat it as an automatic reset |

When encountering errors, **do not retry in an infinite loop** with the same bytes and configuration. Log the capability, binary class name, class loader, class byte size/hash, list of structural changes, and exception cause clearly. Do not log raw application bytecode to production telemetry systems without proper requirements and safeguards.

## 14. Tests You Must Have Before Using Redefinition in Production

A useful checklist for an agent that modifies method bodies at runtime:

1. **Same class identity**: save `Class<?>` before/after and assert `==`.
2. **Same existing object identity**: keep an instance reference and assert `==`.
3. **Instance fields**: assert primitive and reference field values are unchanged **immediately after redefine**.
4. **Static fields**: deliberately assign a value before redefine and assert it remains preserved.
5. **No rerun of initialization**: measure `<clinit>` logs/counters; no second-time side effects appear.
6. **No constructor replay**: existing objects must not rerun constructors or increment constructor counts.
7. **Existing object, new invocation**: call the modified method on an old instance and assert v2 behavior.
8. **New object**: create an instance after redefine; verify new constructor/behavior matches expectations.
9. **Active frame**: use a latch to hold a v1 frame, redefine, then release and confirm it completes as v1.
10. **Multiple threads**: run different methods concurrently to detect invariant violations caused by old/new frame coexistence.
11. **Schema rejection**: intentionally add a field or change a signature in a test environment and confirm the JVM rejects it, rather than mistaking it for success.
12. **Failed redefinition**: supply invalid bytes for one class in a batch; confirm no class in the batch is updated and the system handles the error cleanly.
13. **ClassLoader identity**: if custom loaders exist, verify redefinition applies to the right class object.
14. **Transformer pipeline**: when multiple agents exist, verify the final class bytes are accepted after all transforms.
15. **Business state compatibility**: test new code on instances with specific v1 state, not just newly created objects.

**Important tip:** compare values **immediately after the redefine call returns**, before allowing v2 code to mutate data, to distinguish "the JVM preserved state" from "the application updated state itself via the new method."

## 15. Exercises and Answers

**Question 1.** A `UserSession s` is already stored in a cache before redefine. Does redefining `UserSession` automatically create a new `s` object and replace the reference in the cache?

**Question 2.** `Config.shared` is currently 42. The new class file contains the initializer `shared = 999`. Redefine succeeds after the class has already been initialized. What is the field's value immediately after the operation, assuming no other thread writes to it?

**Question 3.** A thread has entered version v1 of `calculate()` and is waiting on a latch. The JVM successfully redefines `calculate()` to v2. When the thread is woken up, which body does it continue? What about a new `calculate()` call?

**Question 4.** A new `URLClassLoader` loads `com.demo.Account.class` v2 and creates a v2 instance. Does this switch `Account` instances created by the old class loader to the new class?

**Question 5.** In the demo, `existing.getValue()` after redefine still returns 7, whereas `existing.compute()` after redefine returns 1007. Is this a contradiction?

**Question 6.** An agent builds new class bytes with `javac` and adds the field `int retryCount;`. The class file is valid. Does that mean `redefineClasses` must accept it?

**Question 7.** Why is `isModifiableClass(MyClass.class) == true` **not enough** to guarantee a redefine call will succeed?

**Question 8.** Two classes A and B are passed in **one** `redefineClasses(A, B)` call. If B has a prohibited schema change, is the JVM allowed to apply only A and skip B?

**Question 9.** Code v2 replaces `void update()` with a new body containing `value += 100`. After redefine, the `value` field is initially 7; after a new `update()` call, it becomes 107. Does this contradict "instance state is preserved"?

**Question 10.** A method `static int getFlag()` returns a `static final int` that was compile-time inlined in another caller. Does redefining only the class containing the constant guarantee that the old caller reads the new value?

**Question 11.** Why should a test suite use `==` when verifying object identity instead of relying only on `equals()` or `identityHashCode`?

**Question 12.** An active v1 frame calls another method `helper()` after redefinition has completed. Must that `helper()` call necessarily use v1 code?

### Answers

1. **No.** Existing instances are not recreated and the cache still points to the old object.
2. **42**. Redefinition does not automatically rerun `<clinit>` and does not reset existing static state.
3. The active frame continues **v1**; a new invocation uses **v2**.
4. **No.** A new class loader creates a different runtime class identity; that is not a redefinition of the old class.
5. **No.** The field is still 7, while the new method body computes `7+1000`; that is precisely old state paired with new logic.
6. **No.** Adding a field changes the class structure, which is generally prohibited by JVM TI RedefineClasses.
7. You also need `isRedefineClassesSupported()`, the manifest attribute, valid class bytes, the right class identity, and supported structural changes.
8. **No.** Per the contract, if the redefine call fails, no class in the same call is successfully redefined.
9. **No.** The JVM preserves fields **at the time of redefine**, but a **subsequent** v2 method invocation is allowed to modify fields according to its logic.
10. **No.** Compile-time constants may have already been inlined in caller bytecode; moreover, the static initializer does not rerun.
11. `equals()` can return true for two distinct objects; identity hash codes can collide. `==` checks exact reference identity.
12. **No.** The v1 frame is running old code, but a new invocation to `helper()` follows the current method definition; it can use v2.

## 16. Conclusion

Redefinition **replaces executable definitions**, not **class identity or existing objects**. Existing fields retain their values at the time of the operation, static initializers do not rerun, and constructors do not rerun for old objects. An active frame continues the previous version's code, while new invocations use the redefined method code. That is the technical foundation for hot fixes and runtime instrumentation, and it is also why you must test **state compatibility between v1 and v2**, schema limits, and multi-threaded behavior.

To remember this clearly, keep them separate: **class identity does not change; object identity does not change; immediate state is not reset; method bodies for new calls can change; active frames still follow the old body**.

## 17. Official Technical Documentation

- [Java SE 21 — Instrumentation.redefineClasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): rules on instances, static state, initializers, active frames, errors, and atomicity.
- [Java SE 21 — ClassDefinition](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): how class identity is paired with replacement bytes.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest `Can-Redefine-Classes` declaration and Java agent `premain`.
- [Java SE 21 — JVM Tool Interface, Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses): details on active methods, existing instances, static fields, and class structure limits.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): how transformers can transform bytes before they are installed in the JVM.
- [Java Language Specification 21 — §12.4, Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4): timing of class initialization and semantics of static initialization.
