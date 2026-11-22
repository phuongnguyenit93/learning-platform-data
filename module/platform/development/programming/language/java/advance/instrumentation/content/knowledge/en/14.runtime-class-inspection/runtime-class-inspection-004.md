# Distinguishing Listed Classes from Modifiable Classes

> **Objective:** When inspecting a running JVM with a Java agent, know how to interpret the results of `Instrumentation.getAllLoadedClasses()` without **confusing a listed `Class<?>` with a class that can be `retransform`ed or `redefine`d**. Know how to use `isModifiableClass`, check JVM/agent capabilities, distinguish `getInitiatedClasses`, array/primitive/hidden classes, and build a workflow for selecting the right target before any bytecode-modifying operation. This article includes a complete Java 17+ example and **performs inspection only, without modifying any class**.

This is a skill belonging to the **Runtime Class Inspection** group of Java Advanced Instrumentation. An agent can see thousands of classes in memory, but only a subset are suitable for modification. Two different questions need to be answered separately:

1. **Which classes have been loaded by the JVM at the time of inspection?** → `getAllLoadedClasses()`.
2. **Can a specific `Class<?>` be a target for definition modification?** → `isModifiableClass(clazz)`; and after that, the runtime's `retransform`/`redefine` capabilities must also be checked.

The second answer cannot be inferred solely from the first.

## 1. Decision Map

```text
Running JVM
     │
     ▼
Instrumentation.getAllLoadedClasses()
     │       (list of Class<?> loaded at sampling time)
     │
     ├─ Which loader/module/package does the class belong to?
     ├─ Is the class an array/primitive/hidden or special type?
     ├─ Is the class the exact target the agent is allowed to process?
     │
     ▼
Instrumentation.isModifiableClass(clazz)
     │
     ├─ false → DO NOT attempt to redefine/retransform that class
     │
     └─ true
           │
           ├─ Want to retransform?
           │      └─ check isRetransformClassesSupported()
           │
           └─ Want to redefine?
                  └─ check isRedefineClassesSupported()
                         │
                         ▼
              Still must ensure:
              valid bytes, valid schema,
              valid transformer chain,
              class loader/module access,
              and that the JVM accepts the actual operation
```

**A key takeaway:** *Listed* is a property of **discovery**; *modifiable* is the result of a **modifiability check on a single class**; *successfully modified* can only be claimed after the JVM has completed the update request.

Do not print a message saying "instrumented 1,000 classes" just because `getAllLoadedClasses()` returned 1,000 elements. Possibly no class was modified at all; listing by itself does not insert a single instruction or change any bytecode.

## 2. What Does `getAllLoadedClasses()` Actually Return?

Signature in `java.lang.instrument.Instrumentation`:

```java
Class<?>[] loaded = instrumentation.getAllLoadedClasses();
```

Here, `instrumentation` must be passed by the JVM to the Java agent via `premain`/`agentmain`; this code is not a standalone program. The method returns an **array of `Class<?>` currently loaded by the JVM**. The JDK 17 documentation explicitly states that it includes ordinary classes/interfaces, **hidden classes/interfaces**, and **array classes** of various types.

Examples of classes that **may** appear during inspection:

```text
java.lang.String
java.util.ArrayList
com.example.orders.OrderService
com.example.orders.OrderService$State
[Lcom.example.orders.OrderService;
[I
a runtime-generated hidden class
```

These are only **example names**; not every JVM will have loaded all of these classes at the exact snapshot moment. `getAllLoadedClasses()` does not mean "list all `.class` files on the classpath" or "list all classes that will be loaded in the future".

### What the Result **Does** and **Does Not** Mean

| Result | Valid Conclusion | Invalid Inference |
| --- | --- | --- |
| `Class<?>` is in `loaded` | The class was loaded by the JVM during this inspection | That class is modifiable |
| `Class<?>` is not in `loaded` | It was not in the snapshot just taken | It is definitely not on the classpath |
| An array class is in `loaded` | The JVM already has the class representing that array type | Bytecode can be injected into the array class itself |
| A hidden class is in `loaded` | The runtime has an observable hidden class | This class can be looked up by binary name or modified like an ordinary class |
| A class from the bootstrap loader is present | The class was loaded by that loader | All bootstrap classes are unmodifiable |
| A class belonging to a named module is present | The class has module metadata | The module graph already allows any helper/transformer to access it arbitrarily |

A snapshot can change between two calls because other threads are loading classes, using `MethodHandles.Lookup.defineHiddenClass`, generating proxies, or because class loaders/hidden classes are collected when no longer referenced. **Do not use the class count as an immutable ledger.**

### Loaded Is Not Initialized

The JVM separates **loading**, **linking**, and **initialization**. A `Class<?>` appearing in the loaded list does not prove its static initializer has run or that any business method has ever been invoked. Inspection should not proactively "try calling the class" to verify if doing so could trigger side effects.

For example:

```java
Class<?> c = Class.forName("com.example.Target", false, loader);
```

`initialize=false` does not request class initialization, but **can still load the class** if it does not yet exist, altering the very target being inspected. If the goal is only to **obtain the list of already-loaded classes**, prefer reading the `getAllLoadedClasses()` snapshot rather than trying to load every class name from the classpath.

## 3. `getInitiatedClasses(loader)` Is Not the Same as `getAllLoadedClasses()`

Signature:

```java
Class<?>[] classes = instrumentation.getInitiatedClasses(loader);
```

`getInitiatedClasses` returns classes for which `loader` has been recorded as an **initiating loader** — a loader that can locate the class by name through class loading, `Class.forName`, or bytecode linkage. If `loader == null`, it refers to the bootstrap loader.

This is **not synonymous** with "classes where `getClassLoader() == loader`" in all cases. A child loader can **delegate** to a parent loader to find a class, so the initiating loader and the defining loader do not necessarily match.

Important differences:

| API | Scope | Key Notes |
| --- | --- | --- |
| `getAllLoadedClasses()` | Entire JVM at snapshot time | May include hidden classes and array classes |
| `getInitiatedClasses(loader)` | Classes that the loader is recorded as able to find by name | Excludes hidden classes/interfaces and arrays with hidden element types |
| `clazz.getClassLoader()` | **Defining loader** of the class | `null` represents the bootstrap loader |
| `clazz.getModule()` | Module containing the class | Cannot substitute for a modifiability check |
| `clazz.getName()` | Class name for display/preliminary filtering | Can be special for array/hidden classes; insufficient to distinguish class identity |

A class with the same binary name loaded by **two different defining loaders** can be two distinct runtime types. To modify the right class, you must use **the exact `Class<?>` object**, rather than keeping only a string name and guessing the loader later.

### Common Pitfall

You call `getInitiatedClasses(webappLoader)` and see a JDK class. That does **not** prove `webappLoader` defined that JDK class itself; the loader may have delegated to bootstrap. If you want to exclude classes defined by bootstrap, check `clazz.getClassLoader()` instead of relying solely on whether the class appears in the initiated list.

If you are looking for a webapp class to instrument, combine **binary name + defining loader + module + modifiable status**, rather than grabbing the first matching name in the snapshot.

## 4. What Does `isModifiableClass(clazz)` Check?

Signature:

```java
boolean modifiable = instrumentation.isModifiableClass(clazz);
```

According to the JDK 17 Javadoc, the method returns `true` if the class is considered by the JVM to be **modifiable in definition** via redefinition/retransformation, and `false` if the class is not modifiable. It asks about a **specific class**, not about the capability of the entire JVM.

Rules explicitly specified by the JDK:

- **Primitive classes** such as `int.class`, `boolean.class`, `void.class` are **not modifiable**.
- **Array classes** such as `String[].class`, `int[].class`, or `OrderService[][]` are **not modifiable**.
- Certain classes **determined by the JVM implementation** may also be unmodifiable.
- `isModifiableClass(null)` throws `NullPointerException`.
- The return value **is not affected** by whether `isRetransformClassesSupported()` or `isRedefineClassesSupported()` is enabled or disabled; those capabilities must be checked separately.

This is a major source of confusion: a class can return `true` from `isModifiableClass` **even if the current agent does not have permission to call** `retransformClasses` or `redefineClasses`.

### Why Can an Array Class Be Listed Yet Unmodifiable?

The JVM creates classes representing array types through a separate mechanism; they do not have an ordinary `.class` file with application method bodies to replace like regular classes. If the application uses `OrderService[]`, you can instrument the array-handling logic in application methods or use other tooling, but **you cannot pass `OrderService[].class` itself to `retransformClasses`** to inject methods.

```java
// With Instrumentation inst provided to the agent:
System.out.println(inst.isModifiableClass(String[].class)); // false
System.out.println(inst.isModifiableClass(int[].class));    // false
System.out.println(inst.isModifiableClass(int.class));      // false
```

This is an illustrative snippet inside an agent, without a standalone `main`. `String.class` **differs from `String[].class`**; do not infer that the ordinary class `String` is always modifiable or always unmodifiable from the rule for arrays.

### Hidden Classes and Generated Classes

JDK 17 provides `Class.isHidden()`. Hidden classes are typically created via `MethodHandles.Lookup.defineHiddenClass(...)` and may be used in runtime infrastructure or certain lambda/proxy generation strategies. `getAllLoadedClasses()` **may contain them**, whereas `getInitiatedClasses(loader)` **does not contain hidden classes**, because they are not looked up by name through a loader the way ordinary classes are.

In modern HotSpot/JVMTI, hidden classes are not targets eligible for redefinition/retransformation like ordinary classes. Even so, **do not predict solely from the class name**: inspect `isHidden()`, `isArray()`, and the official return value of `isModifiableClass` on the actual object, rather than using a regex excluding "names containing `/0x`" and treating that as an API contract.

When the instrumentation target is a lambda, some classes may be hidden/generated depending on the implementation. Do not assume you can list and modify each lambda class like a business class. Instead, consider instrumenting **the class/method where the lambda is created or invoked** and appropriate hooks for the runtime.

## 5. Three Separate Conditions: Class, Capability, and Change Validity

Breakdown table:

| Question | API/Evidence | What It **Does Not** Guarantee |
| --- | --- | --- |
| Is the class listed? | Present in `getAllLoadedClasses()` | Modifiable, instrumented, initialized |
| Is the class modifiable? | `isModifiableClass(clazz)` | Agent has the capability or valid new bytes |
| Does JVM/agent allow retransform? | `isRetransformClassesSupported()` | Every class is modifiable |
| Does JVM/agent allow redefine? | `isRedefineClassesSupported()` | Valid new class bytes, compatible schema |
| Was the update performed? | API call returns normally, runtime QA | Business logic is correct if untested |
| Did the transformer participate? | `ClassFileTransformer` callback/log | JVM successfully installed the final output |

For **retransformation**:

```java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(target)) {
    instrumentation.retransformClasses(target);
}
```

This snippet is a **conditional pattern**, not a self-running program; you must still ensure `target` is the right class, the transformer chain is valid, and checked exceptions are handled. If a class is listed but `isModifiableClass` is `false`, do not attempt to retransform it just to see whether it throws an exception.

For **redefinition**:

```java
if (instrumentation.isRedefineClassesSupported()
        && instrumentation.isModifiableClass(target)) {
    instrumentation.redefineClasses(
            new java.lang.instrument.ClassDefinition(target, replacement));
}
```

`replacement` must be a `byte[]` containing a **complete, valid, and schema-compatible class file**; it is not defined in this illustrative snippet. `redefineClasses` does not take a path or a patch; it takes a `ClassDefinition` with the existing class and the replacement bytes.

### Manifest and Capabilities

The agent JAR may contain:

```text
Manifest-Version: 1.0
Premain-Class: demo.survey.SurveyAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

These two flags request the JVM to provide the corresponding capabilities **if the JVM supports them**. If a flag is not declared as `true`, that capability is not enabled merely by having an agent. `isModifiableClass` **must not** be used in place of these two capability checks.

The lab in Section 8 uses this manifest to inspect both flags, **but strictly performs no redefinition or retransformation**. On common HotSpot/OpenJDK JDK 17, both are typically `true`; on other runtimes they may be `false`, so results must be read as actually reported.

## 6. Do Not Confuse Modifiable with "Any Bytes Are Allowed"

A class with `isModifiableClass(clazz) == true` must still obey constraints when updating its definition:

- Cannot freely add/remove/rename fields or methods in a standard redefine/retransform.
- Cannot change method descriptors, modifiers, superclass, interfaces, or restricted structural attributes such as `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- Method bodies and certain constant-pool/attribute updates may be allowed **if** the output is valid and the JVM supports it.
- Bytecode must pass the verifier; stack-map frames, branch offsets, and exception tables must be consistent.
- Helper methods injected by the agent must be visible to and accessible by the right class loader/module.
- Another transformer in the chain may alter the final bytes; your agent does not have exclusive control over the output the JVM receives.
- If the update operation fails with an error, no class in the request has its new definition installed per the API contract, even though callbacks may have already logged or updated counters beforehand.

Therefore:

```text
listed = true
modifiable = true
capability = true
```

is only the condition under which **an update attempt can begin**, not proof that **the update is guaranteed to succeed**.

**Do not use `ClassFileTransformer.transform(...)` being called as proof that the class was modified.** The transformer may return `null`; or return invalid bytes; or the JVM may reject the bytes after validation. You must confirm the operation completed successfully and then run runtime tests.

### How Do Redefinition and Retransformation Affect Method Versions?

Upon a successful update, **active stack frames** of the old method may continue executing the old bytecode; new invocations use the new method version. The JVM does not automatically re-run the class initializer or reset static fields due to those operations. Existing instances remain in existence. These constraints relate to runtime behavior and do not affect the initial criterion of whether the class is in the snapshot.

## 7. A Safe Candidate Selection Workflow

Instead of iterating over every `Class<?>` and trying to retransform all of them, apply multiple intentional filtering layers:

```text
1. Load the list from getAllLoadedClasses().
2. Identify the package/class names to observe.
3. Check the defining class loader and module.
4. Exclude array, primitive, and hidden classes not in the plan.
5. Keep only Class<?> with isModifiableClass == true.
6. Verify JVM/agent capability for the intended operation.
7. Check whether the class and version were previously transformed by the agent?
8. Control class count, rate, order, and update scope.
9. Run retransform/redefine in a safe environment when permitted.
10. Verify API results, probe semantics, and runtime cost.
```

These are **verification steps**, not advice to turn an inspection agent into an agent that automatically modifies the entire JVM.

### Filtering by Package Name Alone Is Not Enough

Example inside an agent:

```java
// Illustrative symbols; inst and targetLoader are already declared.
for (Class<?> clazz : inst.getAllLoadedClasses()) {
    if (clazz.isPrimitive() || clazz.isArray() || clazz.isHidden()) {
        continue;
    }
    if (clazz.getClassLoader() != targetLoader) {
        continue;
    }
    if (!clazz.getName().startsWith("com.example.orders.")) {
        continue;
    }
    if (!inst.isModifiableClass(clazz)) {
        continue;
    }
    // Only now is this a candidate; DO NOT call retransform/redefine yet.
}
```

**Why compare loaders by identity?** The same class name in two loaders represents two distinct runtime objects. Do not use `clazz.getName().equals("com.example.Order")` as the sole condition for an operation with side effects.

**Why not filter `java.*` with a blanket "all unmodifiable" rule?** The Javadoc does not say every core Java class is unmodifiable. Some classes the JVM will allow you to modify, but that does not mean you **should** modify them. Use a separate allowlist/denylist policy and risk level, rather than conflating "do not want to modify" with "JVM does not allow modifying".

### Is a `Class<?>` from a Snapshot a Safe Reference?

Between taking the snapshot and processing it, class loaders or runtime policies may change. `Class<?>` is the object representing the class, but holding onto it long-term in the agent (for example, in a static map keyed by `Class<?>`) can inadvertently keep the defining class loader alive across redeploys. Inspection should use **controlled** summary data and avoid holding strong references to thousands of plugin classes unless genuinely necessary.

In addition, `isModifiableClass` and capability checks are **preflight**, not a substitute for error handling when the update API actually runs. A candidate may encounter environment changes, conflicts with another transformer, or byte errors during installation.

## 8. Standalone Java 17+ Lab: Inspect Without Modifying Any Class

This lab uses a startup Java agent that receives `Instrumentation`, after which the application explicitly requests an inspection of **one ordinary class and one array class**. It demonstrates:

1. An ordinary class and an array class **already loaded by the JVM** can both appear in `getAllLoadedClasses`.
2. An array class is **not modifiable**, even when present in the snapshot.
3. Primitive `int.class` is **not modifiable** (without requiring primitives to appear in the snapshot).
4. Modifiability of an ordinary class is checked **separately** and may depend on the JVM.
5. Retransform and redefine capabilities are queried **via two other flags**, not inferred from modifiability.
6. The code **never calls** `retransformClasses` or `redefineClasses`, making this a survey-only agent.

### 8.1. File Structure

```text
loaded-vs-modifiable/
├── agent.mf
├── agent-src/demo/survey/SurveyAgent.java
└── app-src/demo/survey/
    ├── Main.java
    └── Observed.java
```

After building, you will have `out/agent`, `out/app`, `out/survey-agent.jar`. The agent JAR is created from `out/agent` and the app is compiled into `out/app`. No ASM/Byte Buddy is needed, and there are no libraries outside the JDK.

### 8.2. `agent-src/demo/survey/SurveyAgent.java`

```java
package demo.survey;

import java.lang.instrument.Instrumentation;
import java.util.Arrays;

public final class SurveyAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent: ready");
    }

    private static boolean contains(
            Class<?>[] classes, Class<?> target) {
        return Arrays.asList(classes).contains(target);
    }

    public static void survey(
            Class<?> ordinary, Class<?> arrayType) {

        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("No Java agent installed");
        }

        // Take a single snapshot after the app has created both Class objects.
        Class<?>[] loaded = inst.getAllLoadedClasses();

        System.out.println(
                "survey: ordinary-listed=" + contains(loaded, ordinary));
        System.out.println(
                "survey: array-listed=" + contains(loaded, arrayType));

        ClassLoader loader = ordinary.getClassLoader();
        Class<?>[] initiated = inst.getInitiatedClasses(loader);
        System.out.println(
                "survey: ordinary-initiated=" +
                contains(initiated, ordinary));

        boolean ordinaryModifiable = inst.isModifiableClass(ordinary);
        System.out.println(
                "survey: ordinary-modifiable=" + ordinaryModifiable);
        System.out.println(
                "survey: array-modifiable=" +
                inst.isModifiableClass(arrayType));
        System.out.println(
                "survey: primitive-modifiable=" +
                inst.isModifiableClass(int.class));

        boolean canRetransform = inst.isRetransformClassesSupported();
        boolean canRedefine = inst.isRedefineClassesSupported();
        System.out.println(
                "survey: retransform-supported=" + canRetransform);
        System.out.println(
                "survey: redefine-supported=" + canRedefine);

        boolean candidate = ordinaryModifiable && canRetransform;
        System.out.println(
                "survey: retransform-candidate=" + candidate);

        // Intentionally DO NOT call retransformClasses/redefineClasses.
        System.out.println("survey: mutation-performed=false");
    }
}
```

**Detailed explanation:**

- `premain` runs from the agent JAR and stores the `Instrumentation` provided by the JVM. This is not an object you can instantiate yourself with `new Instrumentation()`.
- The app will call `SurveyAgent.survey(...)`; therefore the app needs to see the agent class via the instructed classpath.
- `Arrays.asList(classes).contains(target)` checks **the exact `Class<?>` object**, not just a string name.
- `getAllLoadedClasses` is called **after the app has obtained `Observed.class` and created the array class**, so the lab has evidence that both class types exist.
- `getInitiatedClasses(loader)` is an additional inspection: the ordinary class is looked up by name by the app loader. It is not used as a JVM-wide list.
- `isModifiableClass` is called on the ordinary class, array, and primitive. The latter two evaluate to `false` **by specification**.
- Both capabilities are queried separately. With `Can-Retransform-Classes` and `Can-Redefine-Classes` in the manifest, HotSpot/OpenJDK normally returns `true`; other JVMs may not support them.
- `candidate` means **"eligible for consideration"** for retransform, not "already retransformed".
- No transformer is registered and no bytecode is changed; this lab demonstrates **inspection and classification**, not probe injection.

### 8.3. `app-src/demo/survey/Observed.java`

```java
package demo.survey;

public final class Observed {
    public int value() {
        return 42;
    }
}
```

This is an ordinary application class with a simple instance method. There is no need to initialize or invoke the method to inspect modifiability; referencing `Observed.class` is enough for the JVM to have the class object after load/resolve.

### 8.4. `app-src/demo/survey/Main.java`

```java
package demo.survey;

import java.lang.reflect.Array;

public final class Main {
    public static void main(String[] args) {
        Class<?> ordinary = Observed.class;

        // Ensure the JVM has created the class representing the Observed[] array.
        Class<?> arrayType =
                Array.newInstance(ordinary, 0).getClass();

        SurveyAgent.survey(ordinary, arrayType);
    }
}
```

`Array.newInstance(ordinary, 0)` creates a **zero-length array**; calling `getClass()` obtains the array class. No `Observed` element needs to be allocated. Do not simply assume `Observed[].class` is in the snapshot before the JVM creates the array class; the lab actively triggers that condition.

### 8.5. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.survey.SurveyAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

Both capabilities are declared to **inspect** support status; no command uses them to modify any class. Keep a trailing blank line at the end of the manifest. The JVM has the right to report a capability as `false` if unsupported. Do not attempt to modify classes just because the flag is `true`.

### 8.6. Compile and Run with Bash (Linux/macOS/Git Bash)

In the `loaded-vs-modifiable` directory:

```bash
mkdir -p out/agent out/app

javac -encoding UTF-8 -d out/agent \
    agent-src/demo/survey/SurveyAgent.java

jar --create --file out/survey-agent.jar \
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/agent -d out/app \
    app-src/demo/survey/Observed.java \
    app-src/demo/survey/Main.java

java -javaagent:out/survey-agent.jar \
    -cp out/agent:out/app demo.survey.Main
```

The classpath includes `out/agent` because `Main` calls `SurveyAgent.survey(...)`. This is a simplified lab setup; production agents typically do not let the application call the agent implementation directly, instead providing a dedicated API bridge if needed. On Unix-like systems, multiple classpath entries are separated by `:`.

### 8.7. Compile and Run with PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force `
    -Path out/agent, out/app | Out-Null

javac -encoding UTF-8 -d out/agent `
    agent-src/demo/survey/SurveyAgent.java

jar --create --file out/survey-agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/agent -d out/app `
    app-src/demo/survey/Observed.java `
    app-src/demo/survey/Main.java

java -javaagent:out/survey-agent.jar `
    -cp "out/agent;out/app" demo.survey.Main
```

PowerShell uses backticks for line continuation and separates multiple classpath entries with `;`. The `javac`/`jar`/`java` commands must belong to a compatible JDK 17+. If the agent JAR is missing `Premain-Class`, the JVM cannot invoke `premain` and the lab will fail; check the manifest first.

### 8.8. Expected Stdout and How to Read It Correctly

On **common HotSpot/OpenJDK JDK 17+** with both capabilities supported:

```text
agent: ready
survey: ordinary-listed=true
survey: array-listed=true
survey: ordinary-initiated=true
survey: ordinary-modifiable=true
survey: array-modifiable=false
survey: primitive-modifiable=false
survey: retransform-supported=true
survey: redefine-supported=true
survey: retransform-candidate=true
survey: mutation-performed=false
```

**Values not guaranteed to be identical across all JVMs:** `ordinary-modifiable`, `retransform-supported`, `redefine-supported`, and `retransform-candidate` may be `false` on another runtime. That is not an experiment bug; the differing output is precisely why you must query the JVM rather than infer from a class's appearance. The lines `array-modifiable=false` and `primitive-modifiable=false` are stable API rules.

`ordinary-listed=true` and `array-listed=true` are expected because the code explicitly brings both classes into the loaded state before the snapshot; custom environments may have specific lifecycles, but the lab's logic is clearly designed. `ordinary-initiated=true` holds for the system/application loader in this classpath layout.

**A very important decision line:** `survey: mutation-performed=false`. Even when `retransform-candidate=true`, we have **not yet performed** any modification. Printing `modifiable=true` is not an audit record that a class has been instrumented.

## 9. Control Experiments: Appearing in the List but Excluded

### A. Array Class

Take `String[].class` or `Observed[].class` and call `inst.isModifiableClass(...)`. The value is `false` per the JDK. Do not call `retransformClasses` on an array class to generate unnecessary errors; a direct check is already available.

### B. Primitive Class

`int.class`, `long.class`, `boolean.class`, `void.class` are all unmodifiable. **There is no need** to prove these primitive `Class` objects appear in `getAllLoadedClasses()`. The Javadoc for the loaded list mentions classes/interfaces and arrays; the mere existence of a `Class` representing a primitive is not evidence that all primitives appear in the snapshot.

### C. Hidden Class

If the JVM contains a hidden class from `Lookup.defineHiddenClass`, `getAllLoadedClasses` may list it; `getInitiatedClasses(loader)` does not list this type. Classify using `Class.isHidden()`, then query `isModifiableClass`. On HotSpot/JVMTI, hidden classes cannot be retransformed/redefined like ordinary classes. Do not try to look them up by random suffixed names or hold unbounded strong references just to observe a hidden class.

### D. Ordinary Application Class with Capabilities Disabled

Temporarily create a **separate manifest** omitting `Can-Retransform-Classes: true` and `Can-Redefine-Classes: true`, repackage the agent JAR, and run a **new JVM**. Both `is*Supported()` checks will reflect that the agent did not request those capabilities. `isModifiableClass(Observed.class)` may still report `true`, because the Javadoc states **this value is independent of both flags**. In that case `retransform-candidate` is `false`, even though the class is still listed and modifiable.

This is a great experiment for separating **"class is modifiable by type/VM"** from **"agent currently has permission/capability to modify"**. Do not edit the manifest inside an already-running JVM and expect capabilities to update dynamically.

### E. Same-Named Classes from Multiple Loaders

Suppose two plugin loaders each define `com.example.Plugin`. The snapshot may contain **two distinct `Class<?>` objects** with the same `getName()`. If you select by `name` without checking loader/module, the agent could modify the wrong plugin or corrupt another tenant's data.

To identify accurately, use object identity and log the defining loader and module/layer when needed. Do not just use `Class.forName(name)` without a loader, as it may load/resolve via a **different loader**.

### F. In the Snapshot but Never Passed Through the Agent's Transformer

An agent attached to a JVM after a class has already loaded can see that class in `getAllLoadedClasses`. However, `getAllLoadedClasses` does **not** indicate that the agent's transformer was previously invoked for it. If the transformer was registered **after** load time, it does not automatically receive past class-load events.

You need the appropriate capability and must explicitly call `retransformClasses`/`redefineClasses` if you want to process already-loaded classes, within JVM limits and when permitted. Listing does not automatically trigger callbacks.

## 10. Questions to Answer When Preparing to Modify a Loaded Class

Instead of writing a "for each loaded class, retransform" loop, explicitly document:

- **Goal:** Why does this class need to be transformed? Can non-intrusive JFR/metrics/observation be used instead?
- **Identity:** Binary name, defining loader, module; are there two versions of the class with the same name?
- **Class kind:** Array, primitive, hidden, generated, JDK internals, agent's own classes?
- **Loaded state:** At what point was it in the snapshot?
- **Modifiability:** What does `inst.isModifiableClass(target)` return on the **actual JVM**?
- **Capability:** Do you want to retransform or redefine? Is the corresponding support flag `true`?
- **Policy:** Is the agent allowed to modify this class or only measure it? Are there allowlists/denylists and tenant limits?
- **Bytes:** Does the transformer/bytecode generator produce a valid classfile with the right version/schema?
- **Chain:** Are other Java/JVMTI agents registered on the same class? What are the transformation order and `null` return behavior?
- **Rollback:** If the new logic is wrong, are the old bytes and a valid rollback path available?
- **Behavior:** Have successful return, exception paths, concurrency, static state, stack-map frames, and helper linkage been tested?
- **Operations:** Are there limits on classes per batch, timeouts, memory/log volume, and error monitoring?

If any mandatory condition is not met, keep the status as **candidate-only** and do not call the class-modification API. This workflow allows an agent to discover tens of thousands of classes while intentionally transforming only a small subset.

## 11. Distinguishing "Unmodifiable" from "Not Permitted to Instrument"

The two concepts may overlap in some cases, but they are **not equivalent**:

- `isModifiableClass(clazz) == false`: The JVM indicates this class **cannot have its definition modified** via the corresponding mechanism.
- `isModifiableClass(clazz) == true` but policy is `deny`: Technically modifiable, but **should not / must not be modified** in the current application.
- `isModifiableClass(clazz) == true`, policy allows, but capability is `false`: Insufficient conditions to **call the API**.
- All `true`, but the output class is invalid: The JVM still rejects the update.
- All `true` and the update succeeds: **Business semantics** still need verification.

Example that should not exist in production:

```java
// DANGEROUS PRACTICE — do not run:
for (Class<?> c : inst.getAllLoadedClasses()) {
    if (inst.isModifiableClass(c)) {
        inst.retransformClasses(c);
    }
}
```

The snippet above is strictly a warning, not a runnable lab; `inst` is an undeclared variable. It can trigger thousands of callbacks, slow down the JVM, touch helper classes, increase memory/GC, cause linkage issues for some classes, and alter semantics while the app is running.

**Safe strategy:** filter by owner/module/loader, use small controlled batches, measure overhead in staging, handle errors, and never perform mutation in an operation intended solely for inspection.

## 12. Common Errors in Runtime Surveys

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `getAllLoadedClasses` is huge, few candidates | Arrays, hidden classes, JDK internals, policy filter, or JVM restrictions | Classify by type/loader/module; do not treat as a deficiency |
| `isModifiableClass` returns `false` for arrays | JDK contract | Do not attempt to retransform arrays; instrument methods that use arrays |
| Primitives report unmodifiable | JDK contract | Do not attempt to pass `int.class` to retransform |
| Ordinary class reports `true` but `retransformClasses` fails | Capability `false`, invalid bytes/schema, or another transformer errored | Check global flags and actual stack trace/exception |
| `UnmodifiableClassException` | Target class is not modifiable | Check `isModifiableClass` and class kind |
| `UnsupportedOperationException` | JVM/agent does not support the API or disallowed schema change attempted | Check manifest/capabilities and scope of changes |
| `ClassFormatError` / `VerifyError` | Transformer produced invalid class bytes | Verify bytecode/stackmap/attributes; run tests on target JVM |
| `NoClassDefFoundError` for helper | Target loader/module cannot find helper | Configure helper visibility and module access separately |
| Class not found in initiated list | Confused initiating/defining loader or hidden class | Check the exact loader and API being used |
| New snapshot has more classes | JVM continuously loads classes or the survey itself triggered loading | Attach timestamps; do not interpret two snapshots as an absolute delta |
| Modifiable but not the target class | Similar name from another plugin/tenant | Compare loader identity, module, and allowlist |
| Survey causes heap growth | Strongly caching plugin `Class<?>`/`ClassLoader` references | Limit retention, use weak references, and clean up |
| Loaded count differs before/after attach | The agent and its dependencies loaded additional classes | Record measurement timing; do not compare as absolutes |
| Instrumentation stops due to crash when trying to modify all classes | Mutation scope too broad, not verified per class | Separate survey from modification and test a few classes |

### Why Is Snapshot Count Not a Latency Metric?

A large loaded class count does not directly prove the application is slow or has a heap leak. It can grow due to class loaders, generated proxies, warmup, dynamic code, and frameworks. To conclude a class-loader leak, you must observe loader lifecycles, types surviving across redeploys, retained heap/reference chains, GC, and appropriate profiling tools. **A single `getAllLoadedClasses` call does not prove a leak.**

## 13. Error-Handling Policy When Actually Updating

If after inspection you decide to perform retransform/redefine, explicitly document the strategy:

```text
SURVEY_ONLY
    ↓
TARGET_SELECTED
    ↓
CLASS_MODIFIABLE
    ↓
JVM_CAPABILITY_SUPPORTED
    ↓
TRANSFORMER_POLICY_APPROVED
    ↓
BYTES_VALIDATED (when needed)
    ↓
API_CALLED
    ├─ exception → FAILED / no installed changes
    └─ returns normally → UPDATE_APPLIED / runtime QA
```

The states above are a **workflow model**, not a JDK enum. Separating `TARGET_SELECTED` from `UPDATE_APPLIED` prevents dashboards and audit logs from miscounting the number of modified classes.

**Exception taxonomy:**

- `UnmodifiableClassException`: target is not modifiable.
- `UnsupportedOperationException`: operation not supported by the JVM or disallowed change attempted.
- `ClassFormatError`/`UnsupportedClassVersionError`: new definition class bytes are rejected due to format/version.
- `NoClassDefFoundError` or `LinkageError`: class name/helper/loader/linkage may be broken.
- `NullPointerException`: `null` passed where the API does not accept it.

A single `isModifiableClass` check before the API call does not "immunize" against other exceptions. For a request containing multiple classes, an API-level transaction-like guarantee may apply: if the request fails, none of the classes in the request have new definitions installed. Transformer callbacks may have already run and produced log/metric side effects; those side effects are not automatically rolled back.

## 14. Performance and Safety When Inspecting Large JVMs

**Do not run unbounded scans on every request.** `getAllLoadedClasses` allocates a reference array sized by the number of classes currently loaded in the JVM; scanning too frequently creates overhead. Better practices:

1. Inspect only when needed (startup checkpoint, admin request, diagnostic phase).
2. Filter by prefix/package, defining loader, and module **before** doing heavy logic.
3. Do not log one line for **every** JVM class in production by default.
4. Aggregate counts into stable buckets; avoid dynamic class names/loader identities in metric labels with unbounded cardinality.
5. Do not call `Class.forName` in bulk to look for absent classes if the task is *whether it is already loaded*.
6. Do not hold unbounded strong references to class objects or loaders, especially in JVMs with hot redeploy.
7. Control permissions for using the agent/attach; do not inspect someone else's JVM without authorization.
8. When exact targeting is needed, store stable permitted metadata and re-match the class object at update time.
9. If the JVM is very busy, measure the cost/latency of the inspection itself and avoid disrupting hot paths.
10. Do not expose a dashboard showing "modifiable=true" and interpret it as an invitation to modify every JDK class.

Sometimes a JFR recording, thread dump, or classloader summary is enough to answer a diagnostic question without a Java agent scanning continuously. Choose the least intrusive level suited to the goal.

## 15. Misconceptions to Refute

**1. "Because a class is in `getAllLoadedClasses`, it can definitely be retransformed."**  
False. Arrays and special classes can be listed while `isModifiableClass=false`; capabilities must also be present.

**2. "`isModifiableClass=true` means the current agent has been granted `Can-Retransform-Classes`."**  
False. The two values are independent per the Javadoc. Check `isRetransformClassesSupported()` separately.

**3. "To redefine, checking `isRetransformClassesSupported` alone is enough."**  
False. Use `isRedefineClassesSupported()` for `redefineClasses`.

**4. "`getInitiatedClasses(loader)` is the exact set of classes defined by that loader."**  
False. The initiating loader does not necessarily equal the defining loader; parent delegation makes them differ.

**5. "A class not in the snapshot means the class does not exist in any JAR."**  
False. A `.class` file may exist on the classpath without having been loaded yet.

**6. "`getAllLoadedClasses` only contains ordinary classes, not arrays or hidden classes."**  
False in JDK 17. The API can return both arrays and hidden classes.

**7. "Having the class name is enough to select the right target."**  
False. Class identity also depends on the defining loader; multiple plugins can use the same binary name.

**8. "Loaded means the class initializer has run."**  
False. Loading and initialization are distinct phases.

**9. "`Class.forName` lets you inspect without changing system state."**  
Not always true. It can load/initialize a class depending on the overload and arguments; use caution.

**10. "`public`/`final` modifiers determine whether a class is modifiable."**  
You cannot rely solely on source modifiers. You must query `Instrumentation.isModifiableClass` on the actual JVM.

**11. "Every `java.*` class is unmodifiable."**  
Not a universal JDK rule. Many classes may be modifiable yet should not be automatically modified by an agent.

**12. "A transformer callback log proves the class received the new bytes."**  
False. The callback may have returned `null`, or installation may have failed; you must wait for the API to return successfully.

**13. "Replacing a class body resets static state or creates new instances."**  
False. Redefine/retransform does not automatically re-run initializers; existing objects and static fields persist.

**14. "Hidden classes can be found via `Class.forName` using `getName()`."**  
False. Hidden classes cannot be discovered by name in the ordinary way; do not write suffix-based heuristics.

**15. "A snapshot can be used to definitively conclude a class-loader leak."**  
False. You need to track class/loader lifecycles, GC, and retained references over time.

## 16. Practice Questions

**Q1.** Does `getAllLoadedClasses()` return array classes?  
**A:** Yes. The JDK 17 Javadoc describes array classes as part of the listed scope.

**Q2.** Why is `String[].class` listed yet still unmodifiable?  
**A:** Array classes always have `isModifiableClass=false` by API contract.

**Q3.** Can `int.class` be modified with `redefineClasses`?  
**A:** No. Primitive classes are not modifiable.

**Q4.** If `isModifiableClass(target) == true` but `isRetransformClassesSupported() == false`, should you call `retransformClasses`?  
**A:** No. Capabilities are independent; the operation is not supported.

**Q5.** When `isModifiableClass(target) == true` and the capability is `true`, is a class update guaranteed to succeed?  
**A:** No. The JVM still requires valid bytes/transformer chain and changes within schema limits.

**Q6.** Does `getInitiatedClasses(loader)` include hidden classes?  
**A:** No. Hidden classes cannot be looked up by name through a class loader like ordinary classes.

**Q7.** Are two `Class<?>` objects with the same `getName()` guaranteed to be the same type?  
**A:** No. The defining class loader is part of runtime identity.

**Q8.** Does `getAllLoadedClasses` help find every `.class` file on the classpath that has not been loaded yet?  
**A:** No. It only lists classes already loaded at snapshot time.

**Q9.** How do you avoid accidentally modifying another plugin's class?  
**A:** Verify the class object, defining loader/module, package allowlist, and only select candidates with matching modifiability/capabilities.

**Q10.** Will a class loaded before the agent attached automatically be processed by a newly registered transformer?  
**A:** No. Registering a transformer does not replay past load events; an update mechanism for already-loaded classes is required if supported.

**Q11.** Why does the lab print `mutation-performed=false` even when the ordinary class is modifiable?  
**A:** Because it only performs inspection. No definition-modifying API is called.

**Q12.** Does `Class.isHidden()` replace `isModifiableClass`?  
**A:** No. It only classifies hidden status; the official modifiability query for the specific class must still be used.

**Q13.** Why must `getInitiatedClasses` be distinguished from `clazz.getClassLoader()`?  
**A:** An initiating loader may delegate to a different defining loader; the two concepts serve different purposes.

**Q14.** If a multi-class retransform fails, can each callback invocation be counted as an updated class?  
**A:** No. Callbacks do not confirm installation; an API failure installs no new definitions for the requested set.

**Q15.** Why can inspecting an application's class loaders increase memory usage if the agent permanently stores discovered `Class<?>` objects?  
**A:** Strong references to classes can keep the defining loader and associated classes/objects alive across redeploys, causing a leak.

## 17. Official References and How to Look Them Up

- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): primary source for `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, retransform/redefine capabilities, and API limits.
- [JDK 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): mechanism for receiving `Instrumentation` in `premain`/`agentmain`, manifest capabilities, and Java agent scope.
- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback for transforming class load/redefine/retransform and conditions for returning bytes.
- [JDK 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isArray`, `isPrimitive`, `isHidden`, `getClassLoader`, `getModule`.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loader, delegation, and class lookup.
- [JVM Tool Interface (JVMTI) JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): `GetLoadedClasses`, `IsModifiableClass`, `RetransformClasses`, `RedefineClasses`, and special class restrictions.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/en/specs/jvms/se17/html/jvms-5.html): class identity, loader constraints, and JVM phases.

**Takeaway:** `getAllLoadedClasses()` is a **discovery snapshot**, not a list of classes "safe to modify". `isModifiableClass()` is a **per-class** answer, independent of `isRetransformClassesSupported()`/`isRedefineClassesSupported()`. Only after confirming the exact `Class<?>` by loader/module, checking capabilities, policy, schema, bytes, and runtime QA, can you move from **listed** to a controlled bytecode modification.
