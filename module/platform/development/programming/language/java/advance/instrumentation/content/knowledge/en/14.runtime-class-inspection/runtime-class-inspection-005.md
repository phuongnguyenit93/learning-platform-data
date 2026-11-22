# Filtering Class Sets for Transformation Planning and Recording Skipped Classes

In Java Instrumentation, knowing **which classes are currently loaded by the JVM** is only the first step. A safe agent needs to answer three separate questions: **Which classes are within the scope to be instrumented? Which classes are actually eligible for transformation? Why are unselected or untransformable classes skipped?**

This is the goal of the lesson **“Filtering Class Sets for Transformation Planning and Recording Skipped Classes”** in the **Runtime Class Inspection** topic. Instead of taking the entire result of `Instrumentation.getAllLoadedClasses()` and calling `retransformClasses(...)` on all of them, we create **an explainable transformation plan**: for each candidate, record `READY` or a specific **skip reason**, and include only the classes that pass the checks in the execution list.

A standard workflow has four phases:

~~~text
SURVEY
  Instrumentation.getAllLoadedClasses()
       |
       v
SCOPE FILTERING
  class name, loader/module, package, denylist/allowlist
       |
       v
TECHNICAL EVALUATION
  array/primitive, policy, capability, isModifiableClass
       |
       v
AUDITABLE PLAN
  READY: target Class<?>
  SKIP: Class<?> + clear reason
       |
       +--> DRY_RUN: report only
       |
       +--> APPLY: re-verify, register transformer,
                   retransform the exact READY set
~~~

**Core principle:** *“Being loaded” does not mean “should be transformed”; “modifiable” does not mean “all bytecode is valid”; “skipping” must have an explainable and measurable reason.* This lesson focuses on how to create an auditable plan. A complete Java 17+ example with both `DRY_RUN` and an `--apply` command illustrates intentional execution.

## 1. Why Not Instrument All Loaded Classes?

A JVM typically contains classes from many different sources: JDK, frameworks, applications, agents, test runners, dynamic proxies, runtime-generated classes, and classes coming from custom class loaders. Just because a class appears in the survey set does not mean your instrumentation is meant for it.

If you pass the entire array directly to `retransformClasses`, you may encounter:

- **Array classes and primitive classes**: the API specifies that they are **never modifiable**.
- **JDK or agent classes**: risk interfering with class loading, runtime, logging, or the agent's own helpers.
- **Classes outside the business scope**: increase overhead without yielding useful data.
- **Classes defined by different loaders**: two classes can share the same binary name yet have different runtime identities.
- **Implementation-specific classes**: the JVM may report them as unmodifiable.
- **Classes containing bytecode that the transformer cannot yet handle**: `isModifiableClass(...) == true` does not guarantee that the output will be valid.
- **Excessive volume**: scanning or modifying thousands of classes can cause CPU, memory, safepoint, and latency pressure.
- **Hard-to-trace errors**: without recording `SKIP_*`, it is difficult to tell whether a method was not measured because of policy, capability, or because it had not been loaded yet.

The solution is to separate three decision layers:

| Layer | Question | Example |
| --- | --- | --- |
| **Discovery** | Has the class appeared in the JVM yet? | `getAllLoadedClasses()` |
| **Policy** | Does it belong to the measurement scope? | `demo.app.WorkService` is allowed; `java.lang.String` is out of scope |
| **Eligibility** | Can the JVM/agent retransform it? | `isRetransformClassesSupported()` and `isModifiableClass(type)` |

The result should be **a list of candidates with statuses**, not just a list of class names printed to a log.

## 2. Surveying with Instrumentation.getAllLoadedClasses()

Core API:

~~~java
Class<?>[] snapshot = instrumentation.getAllLoadedClasses();
~~~

This is an **illustrative code snippet**, requiring an `Instrumentation instrumentation` instance obtained from `premain` or `agentmain`.

According to the Java SE 21 Javadoc, `getAllLoadedClasses()` returns an array containing the classes/interfaces currently loaded by the JVM, **including hidden classes/interfaces and array classes**. This is a result **at the time the snapshot is taken**, not a continuously updated list.

### 2.1. A Snapshot Is a Point-in-Time Capture, Not a JVM-Wide Lock

A class may be loaded **after** you obtain the array; a class loader may be garbage-collected when it is no longer referenced. Holding `Class<?>` references in a plan for too long can also **prevent a class loader from being unloaded** due to strong references in the agent.

Operational implications:

1. **Collect** the snapshot.
2. **Filter** quickly and create decision records.
3. **Release** unnecessary references; keep `Class<?>` only for the operation about to be executed.
4. If a long time elapses between survey and execution, **re-survey/re-verify**.
5. To track classes loaded *later*, use a `ClassFileTransformer` for load-time events; a single snapshot does not replace continuous monitoring.

Do **not** infer that `snapshot.length` is the number of “instrumentable” classes. It includes classes that policy or the JVM will exclude.

### 2.2. Distinguishing getAllLoadedClasses and getInitiatedClasses

Two related APIs have different meanings:

| API | Returns |
| --- | --- |
| `getAllLoadedClasses()` | The set of classes/interfaces currently loaded across the entire JVM, including array/hidden classes |
| `getInitiatedClasses(loader)` | Those classes for which `loader` is recorded as an **initiating loader**, i.e., a loader that can find them by name according to the contract |

**An initiating loader is not synonymous with a defining loader.** A parent may actually define the class, yet a child loader is still recorded as an initiating loader for references to that class. Therefore, do not use `getInitiatedClasses(loader)` as the sole proof of **where a class was defined**.

If you need to distinguish identity, take the actual `Class<?>` and inspect `type.getClassLoader()` and `type.getModule()`. `loader == null` is typically the bootstrap loader; that is contextual information, not an error.

### 2.3. Do Not Call Class.forName to “Survey Further”

An agent reading `getAllLoadedClasses()` does **not** need to call `Class.forName(name)` for each discovered class name. Doing so can trigger unintended class loading or initialization, skew class loader identity, and alter the very set of classes we are trying to observe.

If you already have `Class<?> type` from the snapshot, **inspect the metadata** of that object; do not reload it. When `ClassFileTransformer.transform(...)` is being called for a class, this rule is even more important: analyze the `className` and `classfileBuffer` already provided by the JVM, and do not ask the loader to reload the very target currently being defined.

## 3. Designing the Output of a Filter

A useful decision record should answer:

- **Which class?** Name, class loader identity, module (when needed).
- **Outcome?** `READY` or `SKIP`.
- **If SKIP, why?** A stable and descriptive reason code.
- **Which policy?** Allowlist/denylist, policy version.
- **Which capability was checked?** Retransform, redefine, or load-time only.
- **When?** Timestamp of the snapshot/planning pass; do not confuse with the time of actual apply.
- **Execution or preview?** `DRY_RUN` differs from `APPLY`; do not label a class as “transformed” just because it is in the plan.

Example in table form:

| Class | Decision | Explanation |
| --- | --- | --- |
| `demo.app.WorkService` | `READY` | In allowlist, loaded, modifiable, and capability present |
| `demo.app.ReportService` | `READY` | Meets the same conditions above |
| `demo.app.internal.InternalHelper` | `SKIP_EXCLUDED_PACKAGE` | Policy protects infrastructure classes |
| `java.lang.String` | `SKIP_OUTSIDE_SCOPE` | Not part of the business target |
| `int[]` | `SKIP_ARRAY` | Array classes are not modifiable |
| `int` | `SKIP_PRIMITIVE` | Primitive classes are not modifiable |

The last two rows are **policy-demonstration candidates**. A program can include them in a separate test set to demonstrate skip reasons, regardless of whether they appear in a particular snapshot.

## 4. Filtering Order for Low Cost and Stable Reasons

A sound policy should apply conditions **from cheap and definitive to expensive/JVM-dependent**:

~~~text
Class<?> type
  |
  +-- null? -----------------------> SKIP_INVALID_CANDIDATE
  +-- primitive? ------------------> SKIP_PRIMITIVE
  +-- array? ---------------------> SKIP_ARRAY
  +-- hidden by policy? ----------> SKIP_HIDDEN_POLICY
  +-- not in snapshot? -----------> SKIP_NOT_IN_SNAPSHOT
  +-- agent/helper package? ------> SKIP_EXCLUDED_PACKAGE
  +-- does not match allowlist? --> SKIP_OUTSIDE_SCOPE
  +-- capability missing? --------> SKIP_NO_RETRANSFORM_CAPABILITY
  +-- not modifiable? ------------> SKIP_NOT_MODIFIABLE
  |
  +-------------------------------> READY
~~~

This is **an order chosen by the agent**, not an order mandated by the JVM. Its meaning: each class is recorded with **one reproducible primary reason**. **Multiple secondary reasons** can be recorded if auditing requires it, but *primary reason* must be distinguished from *all applicable reasons*.

For example, `java.lang.String` is a JDK class, which may belong to the group the JVM allows modifying in a specific environment. We still choose `SKIP_OUTSIDE_SCOPE` if the policy does not instrument the JDK. One should not try to check whether it is modifiable and then record `SKIP_NOT_MODIFIABLE`, inadvertently obscuring **the real reason: the agent does not want to touch this class**.

### 4.1. Why Check Primitive and Array First?

The Javadoc guarantees that `isModifiableClass(primitiveType)` and `isModifiableClass(arrayType)` return `false`; you can directly classify them using `type.isPrimitive()` and `type.isArray()`, saving some instrumentation calls and clarifying the technical reason.

Do not infer from `type.isFinal()` (no such API exists) or from `java.lang.reflect.Modifier.isFinal(type.getModifiers())` that a `final` class cannot be retransformed. **A final class is not synonymous with an unmodifiable class**.

### 4.2. Hidden, Proxy, and Generated Classes

`Class.isHidden()` has existed since Java 15. A safe policy may exclude hidden classes to avoid instrumenting runtime-generated classes, but it must accurately record `SKIP_HIDDEN_POLICY`: **that is a policy choice**. Do not use reason codes as if all hidden/proxy/record/enum/interface classes were prohibited by the JVM under all conditions.

Similarly, excluding classes whose names contain `$$Lambda`, `$Proxy`, `CGLIB`, or specific generated names is only a **heuristic**, which can fail on other frameworks/versions. When deploying to production, use an allowlist and real testing rather than filtering blindly by name patterns alone.

### 4.3. Class Loader and Module

Two `Class<?>` objects can share the same name `com.example.Service` while being defined by **two different defining loaders**; they are two distinct runtime classes. If a policy wants to instrument only a single application loader, it must use **the loader's identity**, not just `type.getName()`.

Modules also matter in JPMS: you may want to select only a specific `type.getModule().getName()`. However, `module == null` or a `null` module name can occur in valid situations; handle them in a null-safe manner. A class being modifiable does not automatically make the agent's helpers readable or accessible to the target module.

## 5. Capability and Modifiability: Two Independent Conditions

If the plan intends to use **retransformation**, check:

~~~java
boolean capable = instrumentation.isRetransformClassesSupported();
boolean modifiable = instrumentation.isModifiableClass(target);
~~~

This is a **code snippet**: `instrumentation` is provided by the JVM and `target` is a non-null `Class<?>`.

- `isRetransformClassesSupported()` reflects the capability of the JVM/agent configuration. To support it, the agent JAR must have `Can-Retransform-Classes: true` in its manifest and the JVM must also allow it.
- `isModifiableClass(target)` checks the specific class. Its result **does not depend** on whether retransform capability is enabled.
- Both must be satisfied for a class to be retransformed, yet **they are not sufficient to guarantee that the final bytecode is valid**.

In a plan using `redefineClasses(...)`, the corresponding capability condition is `isRedefineClassesSupported()` and the manifest attribute `Can-Redefine-Classes: true`. Do not confuse the two capabilities.

### Failure Can Still Occur After READY

`READY` means the class is **preliminarily eligible** at planning time, not “guaranteed to transform successfully”. The JVM may reject it because:

- Bytecode returned by the transformer is malformed or the verifier detects an error.
- Unsupported class structure changes (adding/removing fields, changing signatures, inheritance hierarchy, etc.).
- The class or environment changed between snapshot and apply.
- Another transformer in the chain produces invalid output.
- The agent encounters a linkage/class loader/module error during execution.

Therefore, distinguish states such as **PLANNED_READY**, **APPLY_ATTEMPTED**, **APPLIED**, and **APPLY_FAILED** instead of treating `READY` as already modified.

## 6. Categorizing Skip Reasons by Group

A real-world system can organize reason codes into a **taxonomy** so dashboards and audits are easy to understand:

| Group | Example Code | Meaning |
| --- | --- | --- |
| Scope | `SKIP_OUTSIDE_SCOPE` | Not in the class/module/loader allowlist |
| Scope | `SKIP_EXCLUDED_PACKAGE` | Agent/helper/logger or protected namespace |
| Scope | `SKIP_HIDDEN_POLICY` | Policy does not touch hidden classes |
| Class kind | `SKIP_PRIMITIVE` | Class representing a primitive; not modifiable |
| Class kind | `SKIP_ARRAY` | Array class; not modifiable |
| Snapshot | `SKIP_NOT_IN_SNAPSHOT` | Candidate does not appear in the snapshot under consideration |
| Capability | `SKIP_NO_RETRANSFORM_CAPABILITY` | Agent/JVM does not have retransformation enabled |
| Eligibility | `SKIP_NOT_MODIFIABLE` | `isModifiableClass(type) == false` |
| Readiness | `SKIP_NOT_YET_LOADED` | Target class is not yet loaded, if an expected list exists from configuration |
| Compatibility | `SKIP_UNSUPPORTED_TARGET_VERSION` | Byte-processing rules do not yet support that class-file version, determined by a parser |
| State | `SKIP_ALREADY_INSTRUMENTED` | Policy to avoid duplicate injection; requires a verifiable marker/metadata |
| Operations | `SKIP_BUDGET_LIMIT` | Class count or processing time budget/limit exhausted |

The codes above are **application design**, not predefined constants from Java Instrumentation. The demo code below uses a subset. If a class has multiple reasons, define a stable priority order and/or store the full list so reports are not misleading.

**Do not record an apply failure as a skip** if `retransformClasses(...)` was actually called and the operation failed. `SKIP` is a **pre-apply** decision; after attempting apply, there must be a clear `APPLY_FAILED + error category`.

## 7. Dry-Run Mode and Intentional Execution

**Dry-run** is very useful in production instrumentation: it can answer “which classes *will* the agent modify?” without feeding any bytes into the JVM. Workflow:

1. Take a snapshot.
2. Apply filters and policy.
3. Build the `READY` and `SKIP(code)` lists.
4. Print/record counts by reason.
5. Do **not** call `retransformClasses` or `redefineClasses`.
6. Allow the operator to review the plan, and only then execute if explicitly requested.

When **applying**, you should:

1. Check capability and modifiability close to the time of the operation.
2. Ensure the transformer is registered with the appropriate capability.
3. Build the array of exact `Class<?>` objects that passed checks; do not convert to names and call `Class.forName` again.
4. Call `retransformClasses(readyArray)`.
5. Record **execution results** separately from plan results.
6. Remove the transformer when appropriate, and release references/buffers.
7. If the operation fails, log the error and do not claim success.

Note that even if a transformer **returns `null`** (making no byte changes in its own step), calling `retransformClasses` is still **an actual retransformation operation**; other transformers may be invoked again. Therefore, “applying with an observer-only transformer” is **not strictly equivalent to a dry-run** in a JVM with other agents.

## 8. Complete JDK 17+ Java Agent: Creating a Plan and Recording Skip Reasons

This demo runs on JDK 17+ and has two modes:

- **Default**: only surveys/records decisions, prints `mode=DRY_RUN`, and does **not** call retransform.
- **`--apply`**: uses the `READY` set to call `retransformClasses`, registering an observer transformer that returns `null` to record callbacks. It does not intentionally alter method bodies.

To keep stdout reproducible, the example creates **a fixed list of six candidates**, while using **a real snapshot from `getAllLoadedClasses()` to confirm that the application classes are loaded**. This is an example of **a filter over a selected candidate set**, without pretending to print all thousands of JVM classes. In real operations, you can extend it to iterate over every `Class<?>` in the snapshot before applying policy.

### 8.1. Directory Layout

~~~text
survey-plan-demo/
├── agent-src/
│   └── demo/agent/SurveyAgent.java
├── app-src/
│   └── demo/app/
│       ├── WorkService.java
│       ├── ReportService.java
│       ├── RunSurvey.java
│       └── internal/InternalHelper.java
└── agent.mf
~~~

The two output directories `agent-bin/` and `app-bin/` are generated during compilation; `survey-agent.jar` is the agent JAR. Separating the agent from the app helps illustrate that `Instrumentation` is provided to the **agent**, not created by the app itself.

### 8.2. agent-src/demo/agent/SurveyAgent.java

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class SurveyAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agentReady=true");
    }

    public static void plan(boolean apply, Class<?>... samples) throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Use -javaagent:survey-agent.jar");
        }
        Set<Class<?>> loaded = Collections.newSetFromMap(new IdentityHashMap<>());
        for (Class<?> loadedType : inst.getAllLoadedClasses()) {
            loaded.add(loadedType);
        }
        boolean capable = inst.isRetransformClassesSupported();
        System.out.println("retransformSupported=" + capable);

        List<Class<?>> ready = new ArrayList<>();
        int skipped = 0;
        for (Class<?> type : samples) {
            String reason = classify(inst, loaded, capable, type);
            System.out.println(reason + " " + type.getTypeName());
            if ("READY".equals(reason)) {
                ready.add(type);
            } else {
                skipped++;
            }
        }
        System.out.println("ready=" + ready.size() + " skipped=" + skipped);
        if (!apply) {
            System.out.println("mode=DRY_RUN");
            return;
        }
        System.out.println("mode=APPLY");
        ClassFileTransformer observer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain domain, byte[] bytes) {
                if ("demo/app/WorkService".equals(className)
                        || "demo/app/ReportService".equals(className)) {
                    System.out.println("transformed=" + className);
                }
                return null;
            }
        };
        inst.addTransformer(observer, true);
        try {
            inst.retransformClasses(ready.toArray(new Class<?>[0]));
            System.out.println("applyCount=" + ready.size());
        } finally {
            inst.removeTransformer(observer);
        }
    }

    private static String classify(Instrumentation inst, Set<Class<?>> loaded,
            boolean capable, Class<?> type) {
        if (type.isPrimitive()) return "SKIP_PRIMITIVE";
        if (type.isArray()) return "SKIP_ARRAY";
        if (type.isHidden()) return "SKIP_HIDDEN_POLICY";
        if (!loaded.contains(type)) return "SKIP_NOT_IN_SNAPSHOT";
        if (type.getName().startsWith("demo.app.internal."))
            return "SKIP_EXCLUDED_PACKAGE";
        if (!type.getName().equals("demo.app.WorkService")
                && !type.getName().equals("demo.app.ReportService"))
            return "SKIP_OUTSIDE_SCOPE";
        if (!capable) return "SKIP_NO_RETRANSFORM_CAPABILITY";
        if (!inst.isModifiableClass(type)) return "SKIP_NOT_MODIFIABLE";
        return "READY";
    }
}
~~~

#### Reading the Code in Four Layers

**Layer 1 — Snapshot:** `getAllLoadedClasses()` provides the set of loaded classes. `IdentityHashMap` builds the set by `Class<?>` reference identity, avoiding confusion between two classes with the same name defined by two different class loaders.

**Layer 2 — Plan:** `classify(...)` returns **a single status code**. Primitive/array checks happen before snapshot membership, so those types are still accurately recorded as `SKIP_PRIMITIVE`/`SKIP_ARRAY` even if they do not appear in a particular snapshot.

**Layer 3 — Preview:** If `apply == false`, the method only prints the totals and `mode=DRY_RUN`, then returns. There is no `addTransformer` or `retransformClasses` in this branch.

**Layer 4 — Apply:** The agent calls `retransformClasses(...)` only with the `ready` list and registers an observer with `canRetransform=true`. Inside the callback, `className` uses the internal name with `/` separators; `return null` indicates the observer intentionally does not modify class bytes. At the end of the operation, the transformer is removed in `finally`. Due to class loading concurrency, `removeTransformer` does not strictly guarantee that no callback is still running at the exact moment of removal.

**Limitations of the demo:** `plan(...)` accepts a candidate list passed by the app to produce deterministic stdout; it is **not** a general discovery tool with a file-backed policy. Allowed names are hardcoded in `classify`; they must be replaced with tested configuration for production use. It also does not catch/encode every apply error into a status record; production code must add a stateful execution layer and appropriate logging.

### 8.3. app-src/demo/app/WorkService.java

~~~java
package demo.app;

public final class WorkService {
    public int execute() {
        return 7;
    }
}
~~~

This is an application class **allowed** by the demo's allowlist. No special annotation is required for `Instrumentation.isModifiableClass(...)` to work.

### 8.4. app-src/demo/app/ReportService.java

~~~java
package demo.app;

public final class ReportService {
    public String report() {
        return "ok";
    }
}
~~~

This class is also in the allowlist and is expected to be `READY` if the JVM/agent supports retransformation and the class is modifiable. This is **the result on the example environment**, not a promise that every JVM allows modifying all application classes.

### 8.5. app-src/demo/app/internal/InternalHelper.java

~~~java
package demo.app.internal;

public final class InternalHelper {
    public void help() {
    }
}
~~~

This class is intentionally placed in the `demo.app.internal` package to demonstrate **policy exclusion**. It may be modifiable by the JVM, but it should not be included in the application's instrumentation plan.

### 8.6. app-src/demo/app/RunSurvey.java

~~~java
package demo.app;

import demo.agent.SurveyAgent;
import demo.app.internal.InternalHelper;

public final class RunSurvey {
    public static void main(String[] args) throws Exception {
        new WorkService().execute();
        new ReportService().report();
        new InternalHelper().help();
        SurveyAgent.plan(args.length > 0 && "--apply".equals(args[0]),
                WorkService.class,
                ReportService.class,
                InternalHelper.class,
                String.class,
                int[].class,
                int.class);
    }
}
~~~

The initial `new ...` calls ensure that the three application classes have been used before the agent takes the snapshot. The `SurveyAgent.plan(...)` call passes exactly six candidates:

- Two application classes in the allowlist.
- One helper excluded by policy.
- One JDK class outside scope.
- One array class and one primitive class to illustrate unmodifiable cases.

The `new ...` statements here are part of the **test driver**. In a production agent, you should not instantiate application classes en masse just to survey them, as that can alter the application and trigger unintended `<clinit>` execution. When doing real discovery, read from `getAllLoadedClasses()` instead of forcing classes into the snapshot.

### 8.7. The agent.mf File

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SurveyAgent
Can-Retransform-Classes: true
~~~

**The manifest must have a trailing blank line.** The `Can-Retransform-Classes: true` entry allows the agent to **request** retransformation if the JVM supports it. Because the demo has an `--apply` mode, this attribute is required. When running only `DRY_RUN`, the task does not execute retransform, though it can still read the capability.

### 8.8. Compiling, Packaging the JAR, and Running

The following commands use JDK **17+**, run from the `survey-plan-demo/` root directory.

Bash:

~~~bash
mkdir -p agent-bin app-bin

javac --release 17 -d agent-bin agent-src/demo/agent/SurveyAgent.java

javac --release 17 -cp agent-bin -d app-bin \
  app-src/demo/app/WorkService.java \
  app-src/demo/app/ReportService.java \
  app-src/demo/app/internal/InternalHelper.java \
  app-src/demo/app/RunSurvey.java

jar --create --file survey-agent.jar --manifest agent.mf -C agent-bin .

java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey
java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey --apply
~~~

Windows PowerShell (avoiding the `\` line-continuation characters used in the Bash example):

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin | Out-Null
javac --release 17 -d agent-bin agent-src/demo/agent/SurveyAgent.java
javac --release 17 -cp agent-bin -d app-bin app-src/demo/app/WorkService.java app-src/demo/app/ReportService.java app-src/demo/app/internal/InternalHelper.java app-src/demo/app/RunSurvey.java
jar --create --file survey-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey
java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey --apply
~~~

In the `javac app` step, `-cp agent-bin` lets the compiler find the `SurveyAgent` type. At runtime, the agent JAR is loaded by the JVM via `-javaagent`; in this test environment, the agent class is found by the system class loader so the application can call `SurveyAgent.plan(...)`. With isolated class loaders or separate module systems, an explicit agent/application communication bridge must be designed.

### 8.9. Verified Dry-Run Output

**Stdout when running on Zulu OpenJDK 24, compiled with `--release 17`:**

~~~text
agentReady=true
retransformSupported=true
READY demo.app.WorkService
READY demo.app.ReportService
SKIP_EXCLUDED_PACKAGE demo.app.internal.InternalHelper
SKIP_OUTSIDE_SCOPE java.lang.String
SKIP_ARRAY int[]
SKIP_PRIMITIVE int
ready=2 skipped=4
mode=DRY_RUN
~~~

In this mode, the agent does not call `retransformClasses`. There is only **the plan**: two candidates are marked `READY` and four candidates have specific skip reasons.

Notable points:

- `SKIP_EXCLUDED_PACKAGE` is a **policy decision**, not necessarily a JVM modifiability failure.
- `SKIP_OUTSIDE_SCOPE` for `java.lang.String` does not mean `String.class` is necessarily unmodifiable; the agent simply **did not select** it.
- `SKIP_ARRAY`/`SKIP_PRIMITIVE` reflect class kinds that the API specifies cannot be modified.
- `retransformSupported=true` **depends on the test runtime environment**; it must not be hardcoded as true for every JVM/manifest.

### 8.10. Verified --apply Output

The second command runs **a new JVM**, not a continuation inside the previous dry-run JVM.

**Stdout:**

~~~text
agentReady=true
retransformSupported=true
READY demo.app.WorkService
READY demo.app.ReportService
SKIP_EXCLUDED_PACKAGE demo.app.internal.InternalHelper
SKIP_OUTSIDE_SCOPE java.lang.String
SKIP_ARRAY int[]
SKIP_PRIMITIVE int
ready=2 skipped=4
mode=APPLY
transformed=demo/app/WorkService
transformed=demo/app/ReportService
applyCount=2
~~~

The output shows that the observer transformer actually received callbacks for the two selected classes when `retransformClasses(...)` was called. The skipped classes were **not included in the demo's retransform array**.

**Caution about log naming:** `transformed=...` in the callback only proves that **the callback ran**. The observer returns `null`, so it **did not modify bytes**. This is not evidence that instrumentation was injected into methods. For accurate production monitoring, naming it `transformCallback=...` or `retransformObserved=...` is clearer and avoids confusing it with bytecode replacement success.

In addition, do not infer that **the processing order between two classes in the same batch** is always guaranteed to match the test stdout. Guarantees about the order of transformers **in a chain for each class** are a separate matter, specified by `ClassFileTransformer`.

## 9. Scaling from Six Candidates to a JVM-Wide Survey

The demo passes a sample list for testing convenience, but real agents usually want to discover **all loaded classes** that satisfy a policy. One way to scale:

~~~java
Class<?>[] all = instrumentation.getAllLoadedClasses();

for (Class<?> type : all) {
    if (type == null || type.isPrimitive() || type.isArray()) {
        continue;
    }

    String name = type.getName();
    if (!name.startsWith("com.acme.service.")) {
        continue;
    }

    // Continue checking loader/module, exclusions, capability,
    // isModifiableClass(type), then record READY or SKIP with a reason.
}
~~~

This is an **illustrative code snippet**, not a standalone program; `com.acme.service.` is an example package scope of a hypothetical application. No class is passed to `Class.forName` inside the loop; only `Class<?>` objects already in the snapshot are used.

**Note on complete reporting:** If you use `continue` immediately when a package does not match, classes skipped early **will not appear in the audit**. If the business requirement is “record skipped classes”, decide clearly:

- **Full-snapshot audit**: record `SKIP_OUTSIDE_SCOPE` for every excluded element, which may produce a huge number of records.
- **In-scope audit**: record skip reasons only after a preliminary package/loader filter and clearly report the total count excluded by the prefilter.
- **Target-list audit**: use a moderately sized candidate allowlist, like the demo, so each candidate has a detailed outcome.

All three can be valid if **the reporting scope and statistical denominator** are transparently described.

### Do Not Retain the allLoadedClasses Array Long-Term

In dynamic application systems such as plugin architectures, a snapshot stored in an agent singleton can hold strong references to many `Class<?>` objects, thereby retaining their class loaders. This can block class unloading and cause leaks. A generally better approach is to **process and then release the snapshot**, store audit results as metadata that holds no live references, and retain `Class<?>` references only for the classes to be applied within a short window.

## 10. Recording Skip Reasons So They Are Operationally Useful

A log saying “skipped” is not enough. There should be **structured records**, or at least a line containing a reason code and class identifier.

Illustrative JSON Lines example:

~~~json
{"runId":"survey-001","className":"demo.app.internal.InternalHelper","outcome":"SKIP","reason":"SKIP_EXCLUDED_PACKAGE","phase":"PLAN"}
{"runId":"survey-001","className":"demo.app.WorkService","outcome":"READY","reason":null,"phase":"PLAN"}
{"runId":"survey-001","className":"demo.app.ReportService","outcome":"APPLIED","reason":null,"phase":"APPLY"}
~~~

This is **example data**, not actual output from the Java program above. In production, add loader/module identifiers sufficient to distinguish classes with the same name. If recording time, use a timezone-aware timestamp; if recording metrics, use actually collected numbers rather than fabricating percentages.

One design can use two separate tables:

| Plan Table | Execution Table |
| --- | --- |
| `planRunId`, `classKey`, `decision`, `skipReason`, `policyVersion` | `executionRunId`, `planRunId`, `classKey`, `attemptedAt`, `result`, `errorType` |
| Created **before apply** | Created **after actually attempting apply** |
| `READY` does not mean modified | `APPLIED` only when the operation succeeded according to defined criteria |

If you do not need to store all millions of out-of-scope classes, you can **count by reason** and sample a few records. However, you must state clearly whether the dashboard represents **all surveyed classes** or only **post-prefilter candidates**.

### Counting Reasons and Ensuring Consistency

With a policy of **exactly one outcome per candidate**, maintain these invariants:

~~~text
evaluated = ready + skipped
skipped   = sum(count by primary skip reason)
attempted <= ready
applied + failed = attempted     (if each attempt has one final outcome)
~~~

In the demo: `evaluated=6`, `ready=2`, `skipped=4`. Because dry-run mode does not apply, `attempted=0`. In apply mode succeeding in the test environment, `attempted=2`, `applied=2` in terms of **retransform operations**, not 2 method body replacements.

If a class appears multiple times in the candidate list, you must choose explicitly: record two separate evaluations or **deduplicate by `Class<?>` identity** before counting. Do not deduplicate by name alone when multiple class loaders are present.

## 11. Selecting Scope by Class Loader, Module, and Class Name

Simple package selection is useful, but for large applications, combine multiple conditions:

~~~text
selectionPolicy(type):
    targetPrefix = com.acme.order.
    definingLoader ∈ approvedApplicationLoaders
    module ∈ allowedModules (if running JPMS)
    className not in excludedAgentOrFrameworkPrefixes
    class not in incident denylist
    parser supports class-file version
~~~

This is a **policy model**, not direct API syntax. A class may carry a name with the application prefix yet come from **an out-of-scope plugin's custom loader**. If you only use the prefix, the agent might mistakenly instrument classes operated by another tenant or plugin.

An example of a loader condition when you already hold the expected class loader:

~~~java
if (type.getClassLoader() != approvedLoader) {
    return "SKIP_UNAPPROVED_LOADER";
}
~~~

This is a **code snippet**, requiring two variables and placed inside a classifier returning a reason string. Do not write `type.getClassLoader().equals(approvedLoader)` because the bootstrap loader can be `null`. Comparing with `==` properly expresses identity.

For modules:

~~~java
Module module = type.getModule();
String moduleName = module == null ? null : module.getName();
~~~

The module name can be `null` for an unnamed module. Do not record “null module = invalid class”. In a JPMS environment, class loader visibility and module readability/exports/opens are two different layers; a helper successfully loaded by the agent may still not be accessible to the target module.

## 12. When You Need to Log Skipped Classes During Load-Time Transformation

Surveying `getAllLoadedClasses()` only examines classes currently loaded. A transformer registered at the right time can monitor **future class definitions**:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (className == null || !className.startsWith("com/acme/order/")) {
        return null;
    }

    // Controlled filtering inside the callback:
    // process bytes only, do not ask the loader to reload the target itself.
    return null;
}
~~~

This is an **illustrative code snippet** inside a `ClassFileTransformer` implementation. At load-time, `classBeingRedefined` is usually `null`: you **do not yet have** a target `Class<?>` object to call `isModifiableClass(target)` in the way used when planning for loaded classes. Therefore:

- **Loaded-class survey:** use `Class<?>` from the snapshot and evaluate modifiability for the retransform plan.
- **Load-time transformer:** use `className` (internal name), `loader`, `module`, and `classfileBuffer`; policy skip reasons can be recorded directly in the callback.
- Do not mechanically apply a classifier requiring `Class<?>` inside a load-time callback and call `Class.forName(target)` to create the missing object.

An agent combining both can unify **reason code names**, but must distinguish the phases and input data.

## 13. Re-Verifying the Plan Before Apply

Do not turn a plan saved an hour ago into an unconditional retransform command. Before applying:

1. Confirm **the right JVM/process** and the right class loader namespace.
2. Confirm the policy/version has not changed; if it has, regenerate the plan.
3. For each retained `Class<?>`, confirm capability and `isModifiableClass`.
4. Include only classes that are currently still valid in the batch.
5. If possible, run with a small group first, then expand gradually.
6. Save results **during execution** and distinguish per-batch failures.
7. Do not automatically retry a failed batch infinitely.
8. If the transformer generates bytecode, verify/test on the corresponding JDK and environment.

### One Batch or Multiple Batches?

`retransformClasses(Class<?>... classes)` allows passing multiple classes in one call, helping apply related changes together. If the final bytes are invalid or the operation fails, the contract specifies that **no class in that call is successfully retransformed**. That differs from calling each class individually, where an earlier successful call may have already taken effect when a later call fails.

Choose **batching together** when changes are logically related or require a consistent unit; choose **small batches** when you need to control blast radius and isolate errors. Do not assume smaller splits are always better, nor send all JVM classes in one giant batch.

### State Note When Other Transformers Exist

When retransformation occurs, `ClassFileTransformer` instances with `canRetransform=true` are invoked again; previous results from transformers without that capability are reapplied in the specified order. Therefore, even the demo's observer returning `null` can still cause **other transformers** to run again. If you want a step with zero side effects, stay in **dry-run** and do not call retransform.

## 14. Performance and Safety When Surveying

### 14.1. Reducing Cost

- Call `getAllLoadedClasses()` on **administrative events or a reasonable interval**, not on every HTTP request.
- Filter name/loader/module early to avoid parsing bytecode or calling expensive APIs.
- Avoid `Class.forName`, deep reflection, class initialization, or calling business methods during a survey.
- Do not log every JDK class to a synchronous logger if the target is only an application package.
- Cap the number of audit events, use bounded buffers, sampling, or aggregate counts when needed.
- Do not build a map that retains references to all classes/loaders indefinitely.

### 14.2. Avoiding Risks in the Application Lifecycle

- **Startup:** class loader callbacks can be sensitive to loading additional logging/helper classes. Keep agent code lightweight.
- **Multi-thread:** multiple threads can load/unload classes; a snapshot is data at the moment of the call, not an absolutely immutable scene.
- **Multi-loader:** identical class names do not mean identical `Class<?>`.
- **JPMS:** module access can affect helpers injected into code later.
- **Hidden classes:** appear in `getAllLoadedClasses()`, but policy and modification support may differ; do not force modification just because they appear in the list.
- **Long-running agents:** memory retention of `Class<?>`/ClassLoader and code caches must be controlled.

## 15. Common Mistakes When Creating a Plan

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Taking all classes from the snapshot and retransforming immediately | Touches JDK, arrays, helpers, unmodifiable classes | Build a plan, filter, and dry-run first |
| Not recording skip reasons | Hard to distinguish policy from JVM errors | Use meaningful, stable reason codes |
| Recording `SKIP_NOT_MODIFIABLE` for everything out of scope | Misreports the cause | Classify by policy before technical checks |
| Confusing `getInitiatedClasses` with the defining loader | Selects the wrong class under parent delegation | Use the real `Class<?>` and `getClassLoader()` |
| Deduplicating by `getName()` | Merges classes from multiple loaders by mistake | Deduplicate by `Class<?>` identity |
| Assuming `final` classes cannot be retransformed | Skips modifiable classes | Use `isModifiableClass`, do not rely on `final` |
| Assuming `isModifiableClass=true` guarantees success | Verifier/schema errors on apply | Verify output and handle exceptions |
| Forgetting manifest capability | `isRetransformClassesSupported=false` | Use `Can-Retransform-Classes: true` and check the JVM |
| Calling `Class.forName` during survey | Unintentionally loads/initializes new classes | Work with snapshot `Class<?>` objects |
| Using same-name lookup to re-find the target in transform callback | Reentrant loading or wrong class identity | Use `className` + `classfileBuffer` |
| Keeping `Class<?>[]` forever in the agent | May block class unloading | Store metadata and release references |
| Confusing plan READY with actual APPLIED | False success reporting | Separate PLAN and APPLY outcomes |
| Using sampling while claiming it is “the whole JVM” | Wrong denominator/metrics | State scope and denominator clearly |
| Infinitely re-running failed batches | Increases latency, repeated transformations, or error loops | Backoff/circuit breaker, categorize errors |
| Using callback code to load heavy libraries | Deadlock/reentrancy or startup regression | Prepare helpers, filter fast, minimize dependencies |

## 16. Pre-Deployment Checklist

1. **Clear objective:** which packages/methods to measure; why already-loaded classes need retransformation instead of load-time only.
2. **Right class source:** `getAllLoadedClasses()` snapshot or an intentional candidate list.
3. **Deterministic filters:** allowlist, exclude agent/JDK/bootstrap or other packages, loader/module policy.
4. **Special class kinds:** primitive/array are always unmodifiable; hidden/proxy handled per appropriate policy.
5. **Capability:** `isRetransformClassesSupported()` and manifest; if using redefine, check the corresponding capability.
6. **Modifiability:** `isModifiableClass(type)` on actual candidate classes.
7. **Every decision has a reason:** `READY` or a clear `SKIP_*`.
8. **Dry-run:** review the list before execution.
9. **Plan and execution separated:** apply success/failure states are not mixed with skip reasons.
10. **Preserve class identity:** do not recreate class objects by name in another loader.
11. **No unintended load/unload effects:** do not retain the entire snapshot long-term or force class init to survey.
12. **Apply errors handled:** do not infer success merely because the transformer callback was invoked.
13. **Volume limits:** budget for class count, logging, timeouts, and concurrency.
14. **QA:** test on the target JVM and multiple loaders/modules if the application actually uses them.

## 17. Self-Check Exercises

**Question 1.** `getAllLoadedClasses()` returns an array containing many thousands of classes, including `java.lang.String`. Does that mean the agent needs to instrument `String`?

**Question 2.** In a plan, `java.lang.String` is excluded because its package is not in the allowlist. Should `SKIP_OUTSIDE_SCOPE` or `SKIP_NOT_MODIFIABLE` be recorded?

**Question 3.** Can `int[].class` go into the `retransformClasses` array simply because it appears in the snapshot?

**Question 4.** One class is loaded by plugin loader A and another class with the same binary name by plugin loader B. Should they be treated as the same candidate if planning by name?

**Question 5.** `isModifiableClass(type)` returns true, but `isRetransformClassesSupported()` returns false. Can it be marked `READY` for retransform?

**Question 6.** A `final` class in a valid package is reported by the JVM as modifiable. Should we assign `SKIP_FINAL_CLASS` just because it is `final`?

**Question 7.** A plan was generated yesterday and is applied today on a plugin application whose class loader was hot-reloaded. Should the old references/names be used as-is?

**Question 8.** The demo's dry-run returns `READY=2`, `SKIP=4`. Can we claim “two classes were instrumented” right after the dry-run?

**Question 9.** The observer transformer in apply mode returns `null` and prints `transformed=...`. Does this prove the bytecode was modified?

**Question 10.** A class gets `SKIP_HIDDEN_POLICY`. Is this a JVM unmodifiability reason or an agent policy?

**Question 11.** Why should `Class<?>[] snapshot` not be kept in an agent static field for the lifetime of the JVM if the application uses dynamic plugin loaders?

**Question 12.** A scan loop uses `continue` immediately when a class is not in the target package. If the dashboard claims it recorded skip reasons for **every surveyed class**, is that report true or false?

**Question 13.** Inside `ClassFileTransformer.transform(...)` for a new class, `classBeingRedefined` is usually null. Should `Class.forName(className)` be called to reapply a `Class<?>`-based classifier?

**Question 14.** Does `getInitiatedClasses(loader)` necessarily contain only classes **defined by that loader itself**?

### Answers

1. **No.** Being loaded is only a discovery fact; separate policy and technical conditions are required.
2. **SKIP_OUTSIDE_SCOPE** per the stated policy; do not attribute modifiability without checking.
3. **No.** Array classes are not modifiable according to the API.
4. **No.** Their runtime identities differ; use `Class<?>` along with defining loader/module context.
5. **No.** Capability and modifiability are two independent conditions, and both must be satisfied.
6. **No.** `final` is not an unmodifiability criterion; use actual API/policy results.
7. **No.** Re-survey and ensure the right class identity, loader, and capability.
8. **No.** Only a plan exists; no retransform call was made.
9. **No.** The observer only received the callback and returned `null`; it did not change class bytes.
10. It is a **policy** in the example; do not infer that hidden classes are prohibited in every JVM or for every kind of operation.
11. Strong references to Class objects can retain the ClassLoader, preventing unloading.
12. **False** unless the prefilter is stated clearly. Classes hit by `continue` have no detailed skip record.
13. **No.** The class currently being processed by the callback may not have finished defining; use `className` and `classfileBuffer`.
14. **No.** The initiating loader can differ from the defining loader due to the delegation mechanism.

## 18. Conclusion

To instrument loaded classes in a controlled manner, you need to **survey with `getAllLoadedClasses()`, filter by scope, check capability/modifiability, and record skip reasons**. The `READY` list is a plan of preliminary eligibility, not proof that classes have had their bytecode replaced. Dry-run helps assess impact before performing retransformation, while apply results must be tracked separately.

**A good plan can explain both “why this class was selected” and “why that class was not selected”**, preserves class loader identity, avoids special classes, reduces the risk of interfering with the JVM, and enables reliable auditing.

## 19. Official References

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, `isRetransformClassesSupported`, `retransformClasses`, and operation atomicity rules.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): filtering in callbacks, transformer ordering, meaning of `className`, `return null`, and responsibility not to mutate the input array.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `getTypeName`, `getClassLoader`, `isPrimitive`, `isArray`, `isHidden`.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loader, delegation, and class-loading locks.
- [Java SE 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `agentmain`, manifest `Can-Retransform-Classes`, and Java agent mechanisms.
