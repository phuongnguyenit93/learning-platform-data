# Removing a Transformer Does Not Automatically Restore Transformed Classes

> **Key rule:** `Instrumentation.removeTransformer(transformer)` **unregisters a transformer so that the JVM stops sending new class transformation requests to that registration in the future**. It **does not automatically reload classes, does not revert bytecode already defined by the JVM, does not roll back previous calls, and does not unload the entire Java agent**. Therefore, `removeTransformer(...) == true` can completely coexist with existing objects — and newly created objects from **the same already-defined class** — continuing to run the instrumented code.

This lesson clarifies the class-file transformation chain in Java Instrumentation, when bytecode becomes the running definition, the exact meaning of `removeTransformer`, how to verify it using Java 17+, and limited recovery options when a class definition truly needs to be changed.

## 1. A Transformer Is Not a "Filter" Keeping Bytecode Live Continuously

A `ClassFileTransformer` is an object that an agent **registers** with the JVM. While the JVM processes a class definition or a class redefinition/retransformation, the JVM calls `transform(...)` to obtain the output bytecode from each transformer in the chain.

~~~text
Input class bytes
       |
       v
Transformer A.transform(...) -- returns bytes A or null
       |
       v
Transformer B.transform(...) -- returns bytes B or null
       |
       v
Transformer C.transform(...) -- returns bytes C or null
       |
       v
JVM verifies and defines/applies the class from the final result
       |
       v
Methods execute according to the applied class definition
~~~

In this chain:

- **`return null`** from a transformer means **that transformer requests no changes** to the input bytes on that invocation. It does not ask the JVM to "restore the original", nor does it erase changes produced by an earlier transformer.
- **`return byte[]`** asks the JVM to use the new class bytes as input for the next transformer or to define the class. The returned array must represent a valid class with the right name and within the allowed change constraints.
- Once the JVM has defined `Greeting` with method `text()` returning `"INSTRUMENTED"`, that code becomes the **running definition** of the class. The JVM does not need to call the transformer again each time `text()` is invoked.
- **Unregistering** only modifies the callback list that the JVM consults on subsequent transformation operations. The JVM does not maintain an automatic "undo stack" specifically for `removeTransformer`.

For example, an agent transforms the `calculate()` method to add logging at the beginning of the method. After the class is defined, calls to `calculate()` run the version with logging added. Removing the transformer from the callback list **does not remove the log statement already present in that definition**.

## 2. Exact Contract of `removeTransformer`

The method in Java 17+:

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

This is an **illustrative snippet**, assuming `inst` is the `Instrumentation` instance passed by the JVM into `premain` or `agentmain`; `transformer` is the exact object previously registered via `inst.addTransformer(...)`.

| Observation / action | API contract | What should not be inferred |
| --- | --- | --- |
| `removeTransformer(t) == true` | A matching registration for `t` was found and removed | Classes previously transformed by `t` have reverted to their old bytes |
| `removeTransformer(t) == false` | No matching registration was found to remove | Previously loaded classes were definitely not instrumented |
| Calling `removeTransformer(null)` | Throws `NullPointerException` | `null` is a way to remove all transformers |
| Same instance `t` registered multiple times | One call removes **the most recent matching registration** | One call automatically removes all duplicate registrations |
| One thread is defining a class while another thread just called remove | Callbacks **may still occur after the remove point** due to concurrency | Remove acts as a barrier that instantly halts all callbacks |
| The agent created threads, loggers, exporters, or other hooks | They **do not stop automatically** just because the transformer was removed | The agent has been unloaded from the JVM |

According to the Javadoc, `removeTransformer` is used to **unregister**. It does not accept a target `Class<?>`, does not accept original bytes, does not ask the JVM to retransform/redefine, and does not return information about which classes were previously transformed.

**Note on multiple calls:** The JVM allows registering the same transformer multiple times, though this is discouraged. Avoid creating duplicate registrations; keep clear ownership of each instance. If duplicate registrations were made and you want to remove all of them, you must handle the remaining registrations rather than relying on a single `true` return value.

**Note on concurrent callbacks:** In systems with concurrent class loading, the return of `removeTransformer` does not prove that no callback is currently executing or already scheduled. Transformer code should be safe enough to handle late callbacks and should not use the `removed` boolean as an absolute assumption that it will never be called again.

## 3. Three Class Groups After Removal

Separate **the time when the JVM defined the class** from **the time when the agent unregistered**.

| Class / scenario | Before removal | After removal without other special operations |
| --- | --- | --- |
| `A` was already defined through the transformer, method bytes replaced | `A` runs the transformed version | **`A` continues to run that version**; old objects and new objects use the same definition |
| `B` had not been defined yet when the transformer was removed | No `Class<?>` for `B` yet | When defining `B`, **the removed transformer does not participate**; still-registered transformers can still participate |
| `C` was already defined before the agent registered | Class `C` runs the old definition | Remove does not change `C`; it also does not trigger a retroactive transformation |
| `A` is later requested via `retransformClasses` or `redefineClasses` | An instrumented class already exists | **The definition can change** due to the new request; the result depends on base bytes, capabilities, and remaining active transformers |

Timeline diagram:

~~~text
T0: agent.addTransformer(T)
T1: JVM loads A -> T transforms bytes -> A is defined with instrumentation
T2: JVM runs A.method() -> instrumentation is active
T3: agent.removeTransformer(T) -> T's callback registration is removed
T4: JVM runs A.method() -> instrumentation in A is still active
T5: JVM loads B -> removed T is not called for B
T6: [optional] controlled redefine/retransform of A -> A can change its definition
~~~

Creating a Java object with `new A()` **does not cause the JVM to redefine class `A`** each time. That is why creating a new instance after removal **does not** make the effect of bytecode transformation disappear. Likewise, calling a method again is not a call to `ClassFileTransformer.transform(...)`.

## 4. Java 17+ Experiment: Removing the Transformer While Old Bytecode Persists

The example below **actually replaces class bytes**: the agent replaces the definition bytes of `Greeting` with another version that has the same class name and structure, but whose `text()` method returns a different string. The agent can also transform `LaterGreeting`; we only load this class **after removing the transformer**, so it retains its original behavior.

Afterward, the program **explicitly** calls **`redefineClasses`** with the original bytes of `Greeting`. This separate step shows a case where a method can be restored **when proactively requested** — not as an automatic result of removal.

The experiment requires a JDK 17+ with `javac`, `jar`, and `java`, using the standard tools included in the JDK. No external bytecode libraries are needed. The JVM must support `redefineClasses` to run the **final restoration step**; standard HotSpot/OpenJDK supports it when the agent declares the corresponding capability.

### 4.1. Create `SwapTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.Map;

public final class SwapTransformer implements ClassFileTransformer {
    private final Map<String, byte[]> replacements;

    public SwapTransformer(Map<String, byte[]> replacements) {
        this.replacements = replacements;
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
        byte[] replacement = replacements.get(className);
        if (replacement == null) {
            return null;
        }
        System.out.println("transform=" + className);
        return replacement.clone();
    }
}
~~~

This transformer is intentionally simple: it only replaces bytes for the two class names `Greeting` and `LaterGreeting` (in the default package). For real projects with packages, `className` uses the JVM internal name, for example `demo/Greeting`, not `demo.Greeting`.

`replacements` are pre-compiled class files, **not** bytecode generated at runtime. `clone()` creates a separate returned array, avoiding accidental modification of the byte buffer retained for other uses. The transformer returns `null` for classes outside its scope.

**Limitations of the example:** Both class versions have the same name and structure; only the method body differs. Do not apply a "replace the entire `byte[]`" approach to any production class without validating the class file, class loader, dependencies, structure, security, and compatibility with other transformers.

### 4.2. Create `SwapAgent.java`

~~~java
import java.io.IOException;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public final class SwapAgent {
    private static Instrumentation instrumentation;
    private static SwapTransformer transformer;

    public static void premain(String args, Instrumentation inst) throws IOException {
        Map<String, byte[]> replacements = Map.of(
            "Greeting", Files.readAllBytes(Path.of("variant/Greeting.class")),
            "LaterGreeting", Files.readAllBytes(Path.of("variant/LaterGreeting.class"))
        );
        instrumentation = inst;
        transformer = new SwapTransformer(replacements);
        inst.addTransformer(transformer);
        System.out.println("agent=registered");
    }

    public static void remove() {
        System.out.println("remove=" + instrumentation.removeTransformer(transformer));
        System.out.println("remove-again=" + instrumentation.removeTransformer(transformer));
    }

    public static void restore(Class<?> type, Path original) throws Exception {
        if (!instrumentation.isRedefineClassesSupported()
                || !instrumentation.isModifiableClass(type)) {
            throw new IllegalStateException("Class redefinition unsupported");
        }
        instrumentation.redefineClasses(
                new ClassDefinition(type, Files.readAllBytes(original)));
        System.out.println("explicit-redefine=complete");
    }
}
~~~

Four essential points of this agent:

1. `premain` reads the **replacement bytes** before registering, so the callback only performs a map lookup and does not read files on every class load.
2. `addTransformer(transformer)` is equivalent to registering with `canRetransform=false`; that capability is **not required** for initial class loads.
3. `remove()` calls the method twice with **the same instance** to demonstrate `true` on the first call and `false` when the registration is no longer present.
4. `restore(...)` **is a separate operation**, using `redefineClasses` after checking support and class modifiability. It is not called automatically by `removeTransformer`.

The agent does not delete or unload the library/agent JAR; it only removes its own transformer registration. `Instrumentation` can still be used for operations supported by the JVM.

### 4.3. Two Original Classes

**`Greeting.java`** in the root directory:

~~~java
public final class Greeting {
    public String text() {
        return "ORIGINAL";
    }
}
~~~

**`LaterGreeting.java`** in the root directory:

~~~java
public final class LaterGreeting {
    public String text() {
        return "LATER_ORIGINAL";
    }
}
~~~

Both follow the same pattern: a Java method `text()` returning a constant string. They are used to produce the initial classes that the application will load from the classpath.

### 4.4. Two Replacement Classes, Same Names but Different Method Bodies

**`variant/Greeting.java`** in the `variant` subdirectory:

~~~java
public final class Greeting {
    public String text() {
        return "INSTRUMENTED";
    }
}
~~~

**`variant/LaterGreeting.java`** in the `variant` subdirectory:

~~~java
public final class LaterGreeting {
    public String text() {
        return "LATER_INSTRUMENTED";
    }
}
~~~

The repeated class names are **intentional**. We will compile the two variant files into a separate directory and only read the `.class` bytes there from the agent. **Do not** place both versions of `Greeting.class` in the same classpath location or package the variant as an application class.

`LaterGreeting` has a pre-prepared transformation variant, so when the application prints `LATER_ORIGINAL` after removal, it is clear proof that the transformer did not participate in this later class definition.

### 4.5. Lifecycle-Driving Application

**`DemoApp.java`**:

~~~java
import java.nio.file.Path;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        Greeting first = new Greeting();
        System.out.println("first=" + first.text());

        SwapAgent.remove();
        System.out.println("same-instance=" + first.text());
        System.out.println("new-instance=" + new Greeting().text());

        System.out.println("later=" + new LaterGreeting().text());

        SwapAgent.restore(Greeting.class, Path.of("Greeting.class"));
        System.out.println("after-explicit-redefine=" + first.text());
    }
}
~~~

This order matters:

- Create `Greeting` **before** removal, forcing the JVM to define the class for the first time while the transformer is still registered.
- Remove the transformer, then call the method on **both the old instance and a new instance** to verify that the class definition persists.
- The first use of `LaterGreeting` happens **after** removal.
- Finally, supply the original class-file bytes to `redefineClasses` to perform an **explicit** restoration.

### 4.6. Agent Startup Manifest

**`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: SwapAgent
Can-Redefine-Classes: true
~~~

Save the manifest file with a trailing newline (you can add a blank line). `Premain-Class` tells the JVM to invoke `SwapAgent.premain` at startup via `-javaagent`.

`Can-Redefine-Classes: true` is only needed for the lesson's **restore via `redefineClasses`** step; it is not required for `addTransformer`/`removeTransformer`. Declaring `true` still requires actual JVM support, so the code checks `isRedefineClassesSupported()`.

### 4.7. Compile, Package, and Run

From the root directory containing `SwapTransformer.java`, `SwapAgent.java`, `Greeting.java`, `LaterGreeting.java`, `DemoApp.java`, `agent.mf`, and the `variant` subdirectory containing the two variant sources, run:

~~~bash
javac --release 17 SwapAgent.java SwapTransformer.java Greeting.java LaterGreeting.java DemoApp.java

javac --release 17 -d variant variant/Greeting.java variant/LaterGreeting.java

jar --create --file swap-agent.jar --manifest agent.mf SwapAgent.class SwapTransformer.class

java -javaagent:swap-agent.jar -cp . DemoApp
~~~

Use JDK 17 or newer to compile with `--release 17`. The commands in the example use standard JDK syntax and run from the exercise directory in Bash/CMD/PowerShell. `variant/Greeting.class` and `variant/LaterGreeting.class` are only read by the agent as data. The agent JAR contains **both `SwapAgent.class` and `SwapTransformer.class`**, avoiding missing-dependency errors.

**Stdout of the example above on a JVM supporting redefine:**

~~~text
agent=registered
transform=Greeting
first=INSTRUMENTED
remove=true
remove-again=false
same-instance=INSTRUMENTED
new-instance=INSTRUMENTED
later=LATER_ORIGINAL
explicit-redefine=complete
after-explicit-redefine=ORIGINAL
~~~

The output was verified with `javac --release 17` and run on OpenJDK 21. Depending on the JVM/JDK, the final redefine step might not be supported; in that case the code throws `IllegalStateException` with a clear message, and **the proof of removal in the preceding lines remains valid**.

### 4.8. Reading the Output by Event

| Stdout line | Evidence |
| --- | --- |
| `agent=registered` | The transformer was registered in `premain` |
| `transform=Greeting` | On the JVM's first definition of `Greeting`, the transformer returned replacement bytes |
| `first=INSTRUMENTED` | The class is running with code from `variant/Greeting.class` |
| `remove=true` | The transformer registration was found and removed |
| `remove-again=false` | On the second remove call, that registration was no longer present |
| `same-instance=INSTRUMENTED` | **Unregistering does not restore the definition of an already-loaded class** |
| `new-instance=INSTRUMENTED` | `new Greeting()` does not redefine the class; the new object uses the replaced method |
| `later=LATER_ORIGINAL` | `LaterGreeting` was defined after removal, so it was not replaced with the variant by the old transformer |
| `explicit-redefine=complete` | The application proactively requested a separate redefine with the original bytes |
| `after-explicit-redefine=ORIGINAL` | Only **after the explicit redefine** does `Greeting`'s method return to the original body in the example |

The core distinction lies between the two lines `remove=true` and `after-explicit-redefine=ORIGINAL`. **The remove call and the restore call are two different operations**, both in intent and in JVM mechanics.

## 5. Why `removeTransformer` Is Not an "Undo" Operation

When the JVM defines a class, it has a **final class-file result** after the transformers have been called. The method bytecode from this result is what the JVM uses for execution. The transformer list serves **subsequent class-processing operations**; it is not a mapping table from every executed instruction back to a transformer to be rolled back when it is removed.

Picture the following steps:

~~~text
Input A.class:     original bytecode
     |
     v
Transformer A:     adds timing measurement
     |
     v
Transformer B:     adds logging
     |
     v
JVM defines A:     timing + logging bytecode
     |
     v
removeTransformer(A)
     |
     v
JVM still has:     timing + logging bytecode
~~~

Removing `Transformer A` does not provide enough information to know **which instructions** were produced by it, which were produced by `Transformer B` or the compiler, or how to strip them out while keeping the class valid. Similarly, removing `Transformer B` does not mean you can keep part A and cleanly delete part B with a single remove call.

When multiple transformers are involved, the result also depends on registration order and on classes being loaded at different times. There is no guarantee that the JVM state after removal is equivalent to a JVM where that transformer was never installed.

**Distinguish three concepts:**

- **Unregister:** `removeTransformer` modifies the callback list registered with `Instrumentation`.
- **Replace definition:** `redefineClasses` supplies different class-file bytes for an already-defined class; the JVM and any still-registered transformers participate in processing according to the contract.
- **Rerun transformation:** `retransformClasses` reprocesses the class from its base bytes, reapplies the results of transformers that do not support retransformation, and invokes those that do. This is also a **proactive request**, not an automatic step after removal.

## 6. If You Truly Need to Restore Behavior, What Options Exist?

### 6.1. Stopping Instrumentation via a Toggle Flag in the Injected Bytecode

If the goal is to **stop logging/metrics without strictly requiring identical original bytes**, an agent can inject a wrapper that reads a configuration flag:

~~~java
// Illustrates the method body AFTER instrumentation.
// Not a standalone runnable Java class because flags and businessLogic() definitions are omitted.
public Result execute(Request req) {
    if (!FeatureFlags.isInstrumentationEnabled()) {
        return businessLogic(req);
    }
    long start = System.nanoTime();
    try {
        return businessLogic(req);
    } finally {
        Metrics.record(System.nanoTime() - start);
    }
}
~~~

This approach must be designed **at instrumentation time**: turning the flag off makes the injected method a no-op for the measurement part, though the wrapper bytecode remains and there is still the cost of checking the flag. Ensure that the application's class loader can see the class containing the flag and that updates are thread-safe.

### 6.2. Redefining with Appropriate Class-File Bytes

The `SwapAgent.restore` example illustrates:

~~~java
if (inst.isRedefineClassesSupported() && inst.isModifiableClass(targetClass)) {
    inst.redefineClasses(new ClassDefinition(targetClass, originalBytes));
}
~~~

This is only an **API code snippet** inside an agent that has `Instrumentation inst`, `Class<?> targetClass`, and `byte[] originalBytes`; it is not a standalone Java file. When the class structure remains compatible and no other transformer modifies the bytes again, redefine can restore the method body as in the exercise.

However, in production there are limitations:

- **You must have trustworthy original bytes.** Do not arbitrarily grab the newest `.class` file on disk and assume it is definitely equivalent to the defined class: class loaders, class versions, shading, builds, modules, and prior redefinitions may differ.
- **You cannot make arbitrary structural changes.** Redefine/retransform has restrictions on adding/removing fields or methods, changing signatures, and altering inheritance hierarchies. If the initial instrumentation added methods/fields, reverting to a class file without them may be rejected by the JVM.
- **Still-registered transformers may transform the bytes again.** Input bytes for redefine pass through the corresponding transformer chain. If you want to roll back a specific effect, you must control **the entire chain**, not just your own transformer.
- **The class might not be modifiable.** Check `isRedefineClassesSupported()` and `isModifiableClass(clazz)`; handle the appropriate error types such as `UnmodifiableClassException`, `UnsupportedOperationException`, or `ClassFormatError`.
- **Running objects and threads are not "rewound".** Existing instances remain as they are; active stack frames may continue executing the old bytecode, while new invocations use the new definition. Static initializers do not rerun automatically and runtime data is not automatically reverted.

Therefore, the claim **"redefine always restores the exact original state"** is false. In the exercise, it succeeded because only the body of one method changed, the exact original bytes were used, and no other transformer continued modifying the class after removal.

### 6.3. Retransforming Based on Capabilities and Actual Chain State

`retransformClasses(Class<?>...)` is another option if the agent declares `Can-Retransform-Classes: true`, the JVM supports it, and the class is modifiable. The difference from redefine: the JVM rebuilds the chain from the **base class-file bytes** of the initial definition or the most recent redefine; it does not require the caller to supply an arbitrary classfile.

However, the outcome still depends on:

- Transformers registered with `canRetransform=false` may still **have their old output reapplied** during a retransform; their callbacks are not invoked again. Therefore, **seeing no callback does not prove that the bytecode effect is gone**.
- Transformers registered with `canRetransform=true` are invoked again; they may add or omit instrumentation depending on current configuration.
- If a transformer has already been removed, a proactive retransform may produce a different definition, but **there is no contract that it "automatically restores all previous changes"**. Other transformers, base bytes, and prior redefinitions can still preserve instrumented behavior.
- Adding or removing methods/fields during retransformation is also subject to structural change restrictions; do not treat retransform as a guaranteed rollback mechanism for every kind of transformation.

Do not call `retransformClasses` just to guess the outcome in production: design tests, check capabilities, check class modifiability, roll out on a small set of classes, and verify post-change semantics.

### 6.4. Restarting the JVM Without the Agent

When you need to return to a **clean** runtime state and cannot prove the correctness of a runtime rollback, restarting the application without the corresponding `-javaagent` is often a more controllable operational choice. A fresh JVM then redefines the classes from the selected artifacts without the removed transformer participating, provided no other agent/configuration with a similar effect remains.

**Restarting is a deployment procedure**, not a feature of `removeTransformer`; you must weigh availability, session data, system state, and an appropriate rollback path.

## 7. Common Technical Errors and Diagnostics

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| `removeTransformer(t) == true` but measurement logs still appear | Logging was already injected **into the bytecode of the loaded class** | Inspect the state of the running class; distinguish callback-time logs from method-execution logs |
| Creating new objects still shows instrumentation | New objects use the same already-defined `Class<?>` | Check the loader, class name, and time of first definition |
| `removeTransformer(t) == false` | Already removed, never added, or wrong instance passed | Keep a single transformer reference; track registrations/unregistrations |
| `transform` callbacks still appear after removal | A call started before/concurrently with removal; or the instance was registered multiple times | Check concurrent class loading and the most recent registration; avoid concluding the JVM violated its contract |
| New classes after removal are still transformed | Another transformer is still registered, or a duplicate registration of the same instance was not removed | List agent/transformer ownership and the active chain |
| Redefine with original bytes fails | Class bytes have wrong name/version, incompatible structure, JVM/class disallows modification, or another transformer causes an error | Check `isRedefineClassesSupported`, `isModifiableClass`, the root cause error, and the actual classfile |
| Retransform shows no callback for `canRetransform=false` | The JVM reuses the incapable transformer's result without calling its callback | Cross-check the `addTransformer(..., false)` API and retransform rules |
| Exporter stopped, yet the application still logs through a wrapper | Instrumentation remains in the class or another hook is still active | Distinguish resource cleanup, callback registration, and executing bytecode |

**How to gather clear evidence:** log `addTransformer`/`removeTransformer` events along with the instance identifier, `ClassLoader`/transformed class name, class definition timestamp, and redefine/retransform requests. Do not equate a "transformer removed" log with a "class definition restored" log.

In multi-agent systems, a `redefineClasses` request can pass through **all remaining transformers as well**, making the output differ from the original. Additionally, if a transformer injected calls to agent helper classes, removing the transformer does not remove the helpers: attempting to unload those helpers or their class loader while bytecode is still calling them can cause `NoClassDefFoundError` or linkage errors.

## 8. Designing a Safe Disable/Cleanup Mechanism

A production agent should distinguish three operational levels:

1. **Stop receiving new callbacks:** call `removeTransformer(t)`; handle the return value and concurrently running callbacks.
2. **Stop resources created by the agent:** shut down background workers/schedulers, flush telemetry queues with bounded limits, close exporters, and remove custom listeners/hooks where appropriate. `removeTransformer` does not do any of these.
3. **Change the behavior of already-instrumented classes:** toggle pre-designed measurement branches, or use `redefineClasses`/`retransformClasses` once compatibility is verified, or deploy a fresh JVM without the agent.

If your transformer maintains a `volatile boolean active` flag to stop new callback logic, that **does not make already-installed bytecode disappear**. It only causes future callbacks to decide not to return additional bytes; the JVM itself continues using existing class definitions until another class-modification request occurs.

### Testing Rules When Disabling an Agent

- Prepare two classes with the same structure as in the exercise: one class **loaded before removal**, and one class **loaded after removal**.
- Verify that the first class still exhibits the transformed behavior after removal, while the second class is not transformed by the removed transformer.
- Test repeated `removeTransformer` calls returning `false`; test passing the wrong instance and duplicate registrations if your project has that risk.
- Test concurrency: have multiple threads load classes or trigger class loading during removal, ensuring callbacks handle late arrivals safely.
- If there is a runtime "restore", test with **the exact JDK, class loaders, modules, and full transformer chain**, not just a single sample class.
- Test failure modes: missing/invalid original bytes, unsupported redefine/retransform, non-modifiable classes, and incomplete rollback.
- Measure overhead and inspect telemetry data in the disabled state. "No more callbacks" does not mean "no more wrapper overhead".

## 9. Comprehension Check Questions

**Question 1.** A transformer adds `System.out.println("trace")` to `OrderService.submit()` at class definition time. Later, `removeTransformer` returns `true`. Will the next call to `submit()` still print `trace`?

**Answer:** It can still print, because the call executes the modified method bytecode. Removing the transformer registration does not automatically replace the method body.

**Question 2.** After removal, does `new OrderService()` automatically pick up the original bytecode?

**Answer:** No. As long as it is **the same `Class<?>`**, the new object uses the current definition of the class rather than redefining it.

**Question 3.** Why can `removeTransformer` return `true` and yet another callback still appear right afterward?

**Answer:** Because class loading/transformation can run concurrently; the Javadoc allows callbacks that were already running or associated with an in-progress operation to arrive late. Also, if the same instance was registered multiple times, another registration will still remain.

**Question 4.** In the demo, at what point does `Greeting.text()` return to `"ORIGINAL"`?

**Answer:** After **`SwapAgent.restore(...)`**, when an explicit `redefineClasses` call applies the original bytes. Not when `removeTransformer` returns `true`.

**Question 5.** Does `retransformClasses` always restore a class to its pre-agent original state?

**Answer:** No. It rebuilds from the base bytes and the transformer rules, including reapplying results from still-registered incapable transformers. The byte source, redefine history, other transformers, and structural limits can produce a different result.

### Reference Documentation

- [Java SE 17 — `Instrumentation.removeTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#removeTransformer(java.lang.instrument.ClassFileTransformer)): return value, removing the most recent matching registration, and concurrent callbacks.
- [Java SE 17 — `Instrumentation.retransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)): base bytes, capable/incapable transformers, and definition-change limits.
- [Java SE 17 — `Instrumentation.redefineClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): supplying replacement class-file bytes, class modifiability, and effects on frames/instances.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer chaining, `null`/`byte[]` results, and when the JVM invokes the callback.
