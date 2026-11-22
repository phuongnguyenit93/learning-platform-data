# Choosing an Alternative Feature or Skipping with Reporting When an Instrumentation Capability Is Unsupported

A Java agent may run well on one JVM yet fail to perform the same operation on another JVM. For example, registering a `ClassFileTransformer` to handle **future-loaded classes** does not mean the JVM allows `retransformClasses` for **already-loaded classes**. Similarly, having retransform permission does not mean every class can be modified, and having redefine permission does not mean valid replacement bytecode is available.

Good agent design must clearly answer four questions before touching an optional feature:

1. **What outcome does the user need?** For instance, “trace already-loaded methods” differs from “trace classes loaded from now on.”
2. **What do the JVM, agent, and target class support?** Check both JVM-wide capabilities and target-specific conditions.
3. **Is there an alternative feature that truly meets the requirement?** Only choose a fallback after determining its scope and semantic differences.
4. **If it cannot be done, what should be reported?** Return the status, reason, and impact; avoid continuing as if instrumentation had succeeded.

This article presents the workflow **check capability → choose approach → execute → verify result → report**, applicable to Java 17+ and the `java.lang.instrument.Instrumentation` API.

## 1. Distinguish “Having the API” from “Supported by the Current JVM”

The existence of a method in the Java API only means the program **can compile**. Several Instrumentation features are **optional capabilities**: the JVM may not support them, or the agent may not have requested those capabilities in its manifest.

Key checks:

| What you want to do | Check | Related conditions | If not met |
|---|---|---|---|
| Transform an **already-loaded** class by re-running the transformer chain | `isRetransformClassesSupported()` **and** `isModifiableClass(target)` | `Can-Retransform-Classes: true` and JVM support | Consider redefine if sufficient data is available, load-time for new classes, or skip with a reason |
| Replace bytecode of an **already-loaded** class with prepared class bytes | `isRedefineClassesSupported()` **and** `isModifiableClass(target)` | `Can-Redefine-Classes: true`, valid bytes, and modification allowed | Fall back only if an approach meets the same requirement; otherwise, skip |
| Set a prefix for native method wrappers | `isNativeMethodPrefixSupported()` | `Can-Set-Native-Method-Prefix: true` and JVM support | Do not call `setNativeMethodPrefix`; check whether the feature must be dropped or redesigned |
| Adjust module reads, exports, or opens | `isModifiableModule(module)` | `redefineModule` must match the module and parameters | Leave the module unchanged; consider startup configuration for the next run |
| Observe **future** class definitions | Register `addTransformer(transformer)` | Valid `Instrumentation` and transformer | This is the baseline approach; it does **not** handle already-loaded classes |
| Modify only a specific class | `isModifiableClass(type)` | Class is considered modifiable by the JVM | Do not attempt `retransformClasses(type)`/`redefineClasses(type)` on that class |

### 1.1. Checking JVM-wide capability and target capability are two independent steps

`isRetransformClassesSupported() == true` is not enough to conclude that `SomeClass.class` can be retransformed. You must check further:

```java
boolean canRetransform = inst.isRetransformClassesSupported();
boolean canModifyTarget = inst.isModifiableClass(SomeClass.class);

if (canRetransform && canModifyTarget) {
    // Can attempt retransform; the final result must still be verified.
}
```

This is an **illustrative code snippet**: `inst` is the `Instrumentation` instance the agent received via `premain` or `agentmain`, and `SomeClass` is a real target class.

Conversely, `isModifiableClass(SomeClass.class) == true` also **does not prove** that retransform/redefine is enabled. By API contract, the result of `isModifiableClass` is independent of the two JVM-wide capability flags. Primitive classes such as `int.class` and array classes such as `String[].class` are unmodifiable.

For modules, `isModifiableModule(module)` checks whether module relationships may be altered using `redefineModule`, **not** whether classes inside the module can be retransformed. For an unnamed module, `isModifiableModule` may return true, but `redefineModule` on an unnamed module is a no-op. Distinguish these before reporting success.

### 1.2. The manifest can disable a capability from the start

Example agent manifest requesting optional capabilities:

```text
Manifest-Version: 1.0
Premain-Class: CapabilityAgent
Agent-Class: CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
Can-Set-Native-Method-Prefix: true

```

This is only an **illustrative manifest sample**; to support both entry points, both `premain` and `agentmain` must be implemented. The `Can-*` lines only **request** capabilities. The JVM may still return false if it does not support them. When an attribute is absent or not `true`, the corresponding capability is not requested; you cannot just look at the Java version and conclude that everything is enabled.

Therefore, do not hard-code calls like:

```java
inst.addTransformer(transformer, true); // may throw UnsupportedOperationException
inst.retransformClasses(target);        // may throw UnsupportedOperationException
```

without checking capabilities. However, **prechecks do not replace error handling**: an operation can still fail due to an unmodifiable class, invalid bytecode changes, deployment conditions, or runtime errors.

## 2. Before Choosing a Fallback, Define the “Feature” at the Behavioral Level

A common mistake is stating the goal by API name: “prefer `retransformClasses`; if unavailable, use `redefineClasses`.” The two APIs **differ in input contract and semantics**:

- `retransformClasses(Class<?>...)` asks the JVM to rebuild the class definition from the underlying bytecode and the transformer chain. Only transformers registered with `addTransformer(transformer, true)` are invoked again during retransform; non-retransform-capable transformers have their previous transformation results reapplied according to JVM rules.
- `redefineClasses(ClassDefinition...)` takes **replacement bytecode supplied by the caller**. It does not invoke a tool to generate class bytes equivalent to a retransform target, and it does not fix structural changes that the JVM forbids.
- `addTransformer(transformer)` (equivalent to `addTransformer(transformer, false)`) allows handling **new class definitions**; it does not immediately re-run callbacks on an already-loaded class.

The requirement should be defined at one of the following levels:

| Feature goal | Primary approach | Acceptable fallback | When SKIP is mandatory |
|---|---|---|---|
| Collect data when a **new class is loaded** | Load-time transformer | Log/emit events directly from the application or existing hook points, if sufficient data is available | No valid way to observe the required event |
| Apply a probe to an **already-loaded class** | Retransformation | Redefinition if verified replacement bytecode exists and the target allows it; or switch to observing **future loads** with a reduced-scope notice | Immediate instrumentation of the current class is required and neither mechanism is available |
| Replace an already-loaded method body with a new build | Redefinition with appropriate bytecode | Retransformation only if the transformer can produce the exact equivalent change | No valid replacement bytes, class is unmodifiable, or schema changes are forbidden |
| Wrap a native method via native prefix | `setNativeMethodPrefix` | Application-level wrapper / redesign in a later deployment, if acceptable | No runtime-equivalent alternative |
| Open a module so a probe can access a package | `redefineModule` when the module is modifiable | Restart with appropriate module settings, e.g., `--add-opens` when permitted and scope is approved | Changing module relationships at runtime is not allowed |
| Change superclass / add fields to an already-loaded class | Standard HotSwap should not be treated as a solution | Transform before class loading, rebuild/redeploy, or design an appropriate class loader | Cannot guarantee the contract of existing instances |

**Key point:** “Another API exists” does not make it a fallback. You must evaluate whether it preserves **observation scope, effective timing, data, safety, and user expectations**.

### Example: fallback from retransform to load-time

An agent is attached to an application that has been running for 3 hours. It needs to add a probe to `OrderService`, which is actively serving requests.

- If the JVM does not support retransform, registering `addTransformer(t)` does **not** instrument the already-loaded `OrderService`.
- That transformer can still handle classes **defined in the future**, but this is a **scope reduction**, not a fulfillment of the requirement for the current `OrderService`.
- The accurate report must be “`OrderService`: SKIPPED, reason=RETRANSFORM_UNSUPPORTED; future-load observation: ACTIVE (if registration succeeded).”
- If business safety requirements demand that the probe be present immediately, future-only observation must not be treated as an acceptable replacement; an error must be reported or a restart/redeploy requested according to policy.

### Example: redefine as a conditional fallback

Suppose capability checks return `retransform=false` and `redefine=true`, and the target class is modifiable. That is **not enough** to call:

```java
inst.redefineClasses(
    new ClassDefinition(target, replacementBytes)
);
```

The snippet above **is only illustrative code**, not a standalone program. You must prove that `replacementBytes` actually contains bytecode with the right class/binary name/loader, a supported class-file version, a structure within redefine limits, valid dependencies, and that other probes are not broken. Do not feed an arbitrary byte array from a source file on disk into a running runtime. If no trustworthy replacement bytes exist, the right decision is **SKIPPED** even though `redefine=true`.

## 3. Build an Explicit Decision Matrix

A practical design can follow this order:

```text
Receive feature request and target scope
                  |
                  v
Check whether Instrumentation is ready
        | no                     | yes
        v                        v
SKIPPED/FAILED            Capture capability + target facts
AGENT_UNAVAILABLE                |
                                 v
                      Distinguish required/optional feature
                                 |
                                 v
                    Is the primary approach supported?
                   /                         \
                 Yes                          No
                  |                            |
        Check class/module          Is a fallback defined with
        and bytecode conditions     sufficient data and right semantics?
                  |                    /             \
                  v                  Yes              No
            Attempt execution         |                |
                  |            Choose fallback         |
                  v                   |             SKIPPED
          Verify postconditions <-----/             + reason
                  |
                  v
      Report APPLIED/DEGRADED/FAILED
      with actual scope and evidence
```

### Recommended priority order for an already-loaded class

1. **Identify the kind of change**: callback observation only, inserting a method-body probe, replacing a method body with prepared bytecode, or modifying class structure.
2. **Check `isModifiableClass(target)`** and the right defining class loader. If false, do not attempt retransform/redefine on that class.
3. **Prefer the API that truly matches the contract**: retransform if transformers must be re-run; redefine if a valid replacement definition already exists.
4. **Use the other API only** when you have proven it can produce an **equivalent result**, not merely based on a capability boolean.
5. **If neither is suitable**, consider load-time-only for future classes or a restart/redeploy strategy, and accurately reflect which already-loaded classes still lack the probe.
6. **Every branch must report**; there should be no silent `return;` branch for a user-expected feature.

Example table for the requirement *apply a probe immediately to an already-loaded class*:

| Retransform | Redefine | Class modifiable | Valid replacement bytes meeting the same goal? | Decision |
|---|---|---|---|---|
| true | any | true | Not needed | Use retransform, then verify |
| false | true | true | Yes | May use redefine per policy |
| false | true | true | No | **SKIPPED** on old class; consider load-time for new classes |
| false | false | true | Any | **SKIPPED**: missing both capabilities |
| true/false | true/false | false | Any | **SKIPPED**: class unmodifiable |
| true | any | true | Not needed, but transformed bytecode is invalid | **FAILED** at execution; do not pretend it was applied |

Read the table according to the actual requirement: if a **retransform callback** is needed rather than just “equivalent bytecode,” redefine is not necessarily a fallback. If the goal is to change class structure, both branches may be invalid depending on the JVM implementation.

## 4. Reporting Status: Separate the Decision from the Execution Result

A usable capability report should have consistent statuses. You can design four main statuses:

- **APPLIED**: the chosen path executed successfully and the postconditions of the **defined feature** are proven.
- **DEGRADED**: an alternative feature is active, but lacks part of the scope or precision; the lost portion must be disclosed.
- **SKIPPED**: the feature was not executed on this target because preconditions were unmet or no approved fallback existed; this can be an expected outcome for an optional feature.
- **FAILED**: the operation or verification step was attempted and encountered an error, or a required feature failed to meet its conditions. The error and subsequent operational decision must be described.

An already-loaded class may have status **SKIPPED**, while the same agent successfully activates a load-time transformer for other classes. Do not merge those two outcomes into a single line saying “instrumentation enabled.”

### A structured decision record

```json
{
  "feature": "loaded-class-method-probe",
  "targetClass": "com.example.OrderService",
  "classLoader": "app-loader",
  "requestedMode": "RETRANSFORM",
  "capabilities": {
    "retransform": false,
    "redefine": true,
    "classModifiable": true
  },
  "chosenMode": "SKIP_EXISTING_CLASS",
  "fallback": "LOAD_TIME_ONLY_FOR_FUTURE_CLASSES",
  "status": "DEGRADED",
  "existingClassStatus": "SKIPPED",
  "reason": "NO_APPROVED_REPLACEMENT_BYTES",
  "scope": "future_class_definitions_only",
  "effectVerified": false
}
```

This is an **illustrative log sample**, not output from a specific JVM. A real system can add agent version, JDK/VM vendor, feature ID, request ID, timestamp, a reliable class-loader identity, and counts of succeeded/unsucceeded classes. Avoid logging sensitive data from method arguments or inflating metric cardinality with per-instance/class-loader names.

Reason codes should be stable and searchable:

| Reason | Meaning |
|---|---|
| `AGENT_NOT_INITIALIZED` | No `Instrumentation` instance available to operate on |
| `RETRANSFORM_UNSUPPORTED` | JVM/agent config does not support retransform |
| `REDEFINE_UNSUPPORTED` | JVM/agent config does not support redefine |
| `NATIVE_PREFIX_UNSUPPORTED` | Setting native method prefix is not permitted |
| `CLASS_UNMODIFIABLE` | Target class cannot be redefined/retransformed |
| `MODULE_UNMODIFIABLE` | Module does not allow changes via `redefineModule` |
| `REPLACEMENT_BYTES_MISSING` | No eligible replacement definition for redefine |
| `FALLBACK_SCOPE_REDUCED` | Fallback only applies to new classes or a narrower scope |
| `BYTECODE_REJECTED` | JVM rejected the transformed class bytes |
| `POSTCONDITION_NOT_VERIFIED` | Operation ran, but evidence that the feature met its goal is insufficient |
| `POLICY_BLOCKED` | Operational policy forbids the change |
| `TRANSFORMER_NOT_REGISTERED` | Failed to register a transformer with the right capability |

### Do not equate “API call returned” with “probe is working”

`inst.retransformClasses(target)` returning without throwing an exception shows that the retransform request was processed successfully at the API level. However, if the transformer returns `null` or fails to transform the right class, you **have not proven** that the desired probe is present. You can report `operation=RETRANSFORM status=COMPLETED effect=NO_CHANGE/UNVERIFIED`, and then report `feature=APPLIED` only after verifying the behavior/bytecode.

Conversely, a transformer that throws an exception may be treated by the JVM as making no transformation; subsequent transformers still run. Therefore, do not design error reporting solely by throwing an exception inside `ClassFileTransformer.transform` and expecting the entire class load to fail automatically. Record transformation errors through a controlled channel and verify targets at the orchestration layer.

## 5. Runnable Java 17+ Example: Auto-Select Retransform or SKIP While Still Observing New Classes

The following example only **observes JVM callbacks**. `transform` always returns `null`, meaning **no bytecode is modified**; this keeps the experiment focused on capability selection and reporting rather than depending on a third-party bytecode library.

Create 4 files in the same directory: `CapabilityAgent.java`, `ObserveTransformer.java`, `Demo.java`, and `agent.mf`.

### 5.1. `ObserveTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ObserveTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if ("ExistingClass".equals(className)
                || "FutureClass".equals(className)) {
            String phase = classBeingRedefined == null
                    ? "LOAD"
                    : "RETRANSFORM_OR_REDEFINE";
            System.out.println(
                    "EVENT class=" + className + " phase=" + phase);
        }
        return null; // Observe only; do not modify class bytes.
    }
}
```

`className` uses the JVM internal name format; for the two classes in the **default package** in this example, it is `ExistingClass` and `FutureClass`. If moved to package `demo`, the filter must use `demo/ExistingClass`, not `demo.ExistingClass`. `classBeingRedefined != null` distinguishes callbacks when the JVM is redefining or retransforming; from that field alone, you cannot tell **which API triggered the callback**.

### 5.2. `CapabilityAgent.java`

```java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class CapabilityAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile boolean canRetransform;

    public static void premain(
            String agentArgs, Instrumentation inst) {

        instrumentation = inst;
        canRetransform = inst.isRetransformClassesSupported();

        System.out.println("CAP retransform=" + canRetransform);

        // Always able to observe classes loaded after the transformer is registered.
        // If retransform is unsupported, registering with false is valid.
        inst.addTransformer(new ObserveTransformer(), canRetransform);

        System.out.println(
                "REPORT status=ACTIVE feature=LOAD_TIME_FUTURE");
    }

    public static void inspectAlreadyLoaded(Class<?> target) {
        if (instrumentation == null) {
            System.out.println(
                    "REPORT status=SKIPPED feature=RETRANSFORM"
                    + " reason=AGENT_NOT_INITIALIZED");
            return;
        }

        if (!instrumentation.isModifiableClass(target)) {
            System.out.println(
                    "REPORT status=SKIPPED feature=RETRANSFORM"
                    + " reason=CLASS_UNMODIFIABLE");
            return;
        }

        if (!canRetransform) {
            System.out.println(
                    "REPORT status=SKIPPED feature=RETRANSFORM"
                    + " reason=RETRANSFORM_UNSUPPORTED");
            return;
        }

        try {
            instrumentation.retransformClasses(target);
            System.out.println(
                    "REPORT status=COMPLETED feature=RETRANSFORM"
                    + " effect=NO_BYTECODE_CHANGE");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException e) {
            System.out.println(
                    "REPORT status=FAILED feature=RETRANSFORM"
                    + " cause=" + e.getClass().getSimpleName());
        }
    }
}
```

Because `canRetransform` comes from `isRetransformClassesSupported()`, the call `addTransformer(transformer, canRetransform)` only passes `true` when the JVM/manifest supports it. If `false`, the transformer still processes classes **loaded later** but will not receive callbacks for retransform. `inspectAlreadyLoaded` clearly distinguishes an unmodifiable class from an unsupported retransform capability.

To keep the example short, `catch` only illustrates two expected capability-layer exceptions. In a real agent, class file, verifier, module, linkage, or transformer bugs must be recorded and handled according to specific policies; do not hide them behind a `catch(Throwable)` and report SKIPPED.

### 5.3. `Demo.java`

```java
public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("APP_START");

        Class<?> existing = Class.forName("ExistingClass");
        CapabilityAgent.inspectAlreadyLoaded(existing);

        Class.forName("FutureClass");
        System.out.println("APP_DONE");
    }
}

final class ExistingClass {
}

final class FutureClass {
}
```

Having two non-`public` classes in the same `Demo.java` file is valid. `Class.forName("ExistingClass")` causes `ExistingClass` to be loaded after the agent has registered the transformer. Next, `inspectAlreadyLoaded` attempts to retransform **that already-loaded `Class<?>` object**. Finally, `FutureClass` is loaded after the decision and must still pass through the transformer.

### 5.4. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: CapabilityAgent
Can-Retransform-Classes: true

```

This is a startup agent, so it only needs `Premain-Class`. The attribute `Can-Retransform-Classes: true` lets the agent request the capability; it does **not force** every JVM to support it. The example omits `Can-Redefine-Classes` because it does not call redefine, and does not need `Can-Set-Native-Method-Prefix`.

### 5.5. Compile, package, and run

On JDK 17+ with `javac`, `jar`, and `java`:

```shell
javac CapabilityAgent.java ObserveTransformer.java Demo.java
jar cfm capability-agent.jar agent.mf CapabilityAgent.class ObserveTransformer.class
java -javaagent:capability-agent.jar -cp . Demo
```

All files are compiled in the same directory. `ExistingClass.class` and `FutureClass.class` generated by `javac Demo.java` remain on the classpath `.`. The agent JAR contains both classes used by the agent. The `jar cfm` command reads the external manifest into `META-INF/MANIFEST.MF`.

**Typical output on HotSpot JDK 17/21 supporting retransformation:**

```text
CAP retransform=true
REPORT status=ACTIVE feature=LOAD_TIME_FUTURE
APP_START
EVENT class=ExistingClass phase=LOAD
EVENT class=ExistingClass phase=RETRANSFORM_OR_REDEFINE
REPORT status=COMPLETED feature=RETRANSFORM effect=NO_BYTECODE_CHANGE
EVENT class=FutureClass phase=LOAD
APP_DONE
```

**If the JVM/agent does not support retransformation** but allows a transformer for new classes, the corresponding branch prints:

```text
CAP retransform=false
REPORT status=ACTIVE feature=LOAD_TIME_FUTURE
APP_START
EVENT class=ExistingClass phase=LOAD
REPORT status=SKIPPED feature=RETRANSFORM reason=RETRANSFORM_UNSUPPORTED
EVENT class=FutureClass phase=LOAD
APP_DONE
```

These are **two capability-dependent outcomes**, not two outputs that must appear in a single run. Another JVM might also mark the class as unmodifiable, in which case the `CLASS_UNMODIFIABLE` branch appears.

### 5.6. Reading the output correctly

- `EVENT class=ExistingClass phase=LOAD`: callback occurs the first time the JVM defines the class.
- `EVENT ... phase=RETRANSFORM_OR_REDEFINE`: in this experiment it comes from `retransformClasses`, because the code does not call `redefineClasses`. The string “OR_REDEFINE” only reflects the information available in the callback.
- `status=COMPLETED ... effect=NO_BYTECODE_CHANGE`: the retransform operation completed, **not** proof that a probe was installed; the transformer returned `null`.
- `status=SKIPPED feature=RETRANSFORM` when the capability is unsupported: the retransform request was not executed; no error is hidden and no API is called blindly.
- `status=ACTIVE feature=LOAD_TIME_FUTURE` and `EVENT class=FutureClass phase=LOAD`: a path to observe new classes remains available even when old classes cannot be retransformed.

If you want to experiment with missing-capability mode on a normal JVM, you can rebuild the manifest with `Can-Retransform-Classes: false` and repackage the JAR; this **changes the agent's capability configuration**, rather than faking results. Then `isRetransformClassesSupported()` will return false per the Java agent contract. Do not edit the manifest of a JAR currently in use by a running JVM and expect the loaded agent to change capabilities; you must start a new JVM for the test run.

## 6. From Observation Example to Real Agent: Postcondition Verification

In a real product, a transformer may generate bytecode containing timing probes or trace recording. In that case, the check sequence should be:

1. **Before the operation:** record feature ID, class binary name, defining class loader, module, capabilities, fallback policy, and current status.
2. **During the operation:** ensure the transformer targets the right class; catch and store errors specific to the transformation logic. Do not mutate `classfileBuffer` directly; return `null` if unchanged, or return a valid new byte array.
3. **After the operation:** verify the callback/resulting bytecode/probe behavior depending on the goal (for example, the probe appears on a new request with a verified event). A callback invocation alone is not enough to prove instrumentation succeeded.
4. **Report:** which classes are `APPLIED`, which are `SKIPPED` and why, whether `DEGRADED` occurred due to load-time-only support, and whether `FAILED` occurred due to rejected bytecode.

A useful invariant is:

```text
reported APPLIED
    => capability and target conditions were met
    => API returned successfully
    => feature postcondition is proven

reported SKIPPED
    => no claim that the feature is active on that target
    => concrete reason provided
    => no unauthorized approach silently invoked

reported DEGRADED
    => fallback is active within the stated scope
    => lost scope is reported separately
```

If postcondition verification is expensive, the system may choose an intermediate status such as `OPERATION_COMPLETED_EFFECT_UNVERIFIED`. Do not “upgrade” that status to `APPLIED` just to make logs look good.

## 7. Skipping with Reporting Does Not Mean Skipping Responsibility

Distinguish **optional features** from **required features**:

- **Optional:** the agent provides supplementary metrics. If the JVM lacks retransform, the application can keep running; the agent reports `SKIPPED/DEGRADED`, displays actual coverage percentage, and provides an alternative collection path if verified.
- **Required:** a core function requires probes or enforcement on all target classes. When the capability is missing, a fallback that only monitors new classes must not be treated as sufficient. Halt feature activation or deny “ready” status per existing policy and state the reason, instead of pretending enforcement is active.
- **High-impact:** `redefineClasses` or opening modules can alter behavior/access relationships. A fallback must not automatically widen permissions or swap class bytes just to avoid reporting SKIPPED.

A typical operational report:

```text
feature=latency-probe
requested=loaded-class-and-future-class
class=com.example.OrderService
canRetransform=false
canRedefine=true
isModifiableClass=true
replacementBytesVerified=false
existingClass=SKIPPED reason=REPLACEMENT_BYTES_MISSING
futureClasses=ACTIVE mode=LOAD_TIME_ONLY
overall=DEGRADED
action=RESTART_WITH_STARTUP_AGENT_IF_FULL_COVERAGE_REQUIRED
```

This is an illustrative record, not API execution output. It clearly states **which part of the feature is usable, which part is missing, and what to do if full coverage is needed**.

### How can results be aggregated across many classes?

A JVM can have thousands of classes and multiple class loaders. Do not use a single boolean `agentEnabled=true` to represent success across all targets. Count instead:

```text
requestedTargets = 30
appliedTargets   = 24
skippedTargets   = 4
failedTargets    = 2

reportedCoverage = 24 / 30 = 80%
```

These numbers are only examples. The coverage formula must clearly define the denominator: **requested targets**, not all JVM classes. If a class has multiple definitions across defining loaders, statistics must be tracked per selected target definition. For metrics systems, use counters by `feature/status/reason`; detailed class names should go into structured logs or cardinality-bounded reports.

## 8. Error Handling After Prechecks: `true` Capability Can Still Fail

Even when `isRetransformClassesSupported() == true` and `isModifiableClass(target) == true`, `retransformClasses` can still fail:

- `UnmodifiableClassException`: the class does not allow modification.
- `UnsupportedOperationException`: configuration does not support the operation or the transformation violates limits for already-loaded classes (e.g., unsupported structural changes).
- `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError`, `ClassCircularityError`, or `LinkageError`: the new bytecode is invalid or incompatible with the corresponding JVM constraints.
- A `transform` may throw an exception while the JVM continues the transformer chain; if the transformation is not applied, postcondition verification is required to avoid false success reports.

`redefineClasses` can encounter similar errors, and the operation also requires a `ClassDefinition` containing the corresponding bytes. For `setNativeMethodPrefix`, besides `UnsupportedOperationException` when capability is missing, `IllegalArgumentException` may occur if the transformer is not registered. For `redefineModule`, `UnmodifiableModuleException` applies to unmodifiable modules.

**Error policy should be categorized:**

| Category | Example | Handling approach |
|---|---|---|
| Unsupported before execution | `isRetransformClassesSupported=false` | Do not call the API; choose a valid fallback or `SKIPPED` |
| Ineligible target | `isModifiableClass=false` | `SKIPPED target`; record class and reason |
| Insufficient fallback data | Missing valid class bytes for redefine | `SKIPPED` or request another deployment; do not fabricate invalid bytes |
| API rejected at runtime | `UnsupportedOperationException`, `UnmodifiableClassException` | `FAILED` with cause; only try fallback if compatible and policy is explicit |
| Faulty bytecode/transformer | `ClassFormatError`, `VerifyError`, internal transformer bug | `FAILED`, preserve evidence/version; do not claim probe is installed |
| Postcondition mismatch | API completed but required event/behavior is absent | `UNVERIFIED/FAILED` per requirement; do not announce `APPLIED` |
| Required feature | All fallbacks lack effect on current classes | Mark as not ready; require restart/redeploy/config fix |

Do not catch every exception and print “instrumentation disabled” generically; information about **unsupported**, **ineligible**, **execution error**, and **missing postcondition** affects remediation differently. At the same time, do not swallow `VirtualMachineError` or other severe errors to force the application to continue normally without a strong enough policy.

## 9. How Should Three Real-World Scenarios Be Decided?

### Scenario A — agent attaches to a running JVM, needs tracing for an already-loaded class

Problem statement: “Trace all new calls to `PaymentService` immediately.”

- If `retransform=true`, the class is modifiable, and the transformer produces valid bytecode, use retransform, then verify the probe actually records traces.
- If `retransform=false` but `redefine=true`, use redefine only when **verified equivalent replacement bytecode** is available and the impact is approved.
- If neither is available, enabling a load-time transformer for later-loaded classes is only a **scope reduction**. Report `PaymentService=SKIPPED`; do not call it “tracing enabled.”
- If the requirement is mandatory, recommend running a startup agent on the next deployment or changing the application's observability design.

### Scenario B — profiler wants to support native method prefix across multiple JVMs

Problem statement: “Wrap native methods to observe call chains via Instrumentation's prefix mechanism.”

- Check `isNativeMethodPrefixSupported()` and the manifest's `Can-Set-Native-Method-Prefix`.
- When supported, register the transformer before calling `setNativeMethodPrefix` and verify instrumentation results.
- When unsupported, do not try calling it and ignoring the exception. Metrics may be recorded at a Java-layer wrapper if that meets the requirement, but you must report that the scope differs from JNI-level wrapping. If insufficient, `SKIPPED reason=NATIVE_PREFIX_UNSUPPORTED`.

### Scenario C — agent needs to open a package in a module to call a helper

Problem statement: “The agent needs deep reflection into a package of a named module.”

- Check `isModifiableModule(targetModule)` and the validity of the target package/module.
- If permitted, `redefineModule` can **add** appropriate opens/exports/reads; it does not remove existing relationships.
- If not permitted, do not open another module on your own or treat applying `--add-opens` to a running JVM as the same operation; startup configuration may need to be changed for the next run.
- Even if the module is modifiable, you must still prove the helper's actual access permissions and stay within application security policy.

## 10. Design Mistakes to Avoid

1. **Relying solely on JDK version:** the same Java 21 runtime can have different agent manifests and capabilities/configurations; always query the current `Instrumentation`.
2. **Checking only JVM-wide capability:** an individual class can be unmodifiable; you must also check `isModifiableClass`.
3. **Calling `addTransformer(t, true)` without retransform:** throws `UnsupportedOperationException`; choose `true/false` from the capability.
4. **Switching to `redefineClasses` without proper bytes:** this is a class-definition replacement operation, not a renamed version of retransform.
5. **Treating a load-time transformer as updating old classes:** having a registered transformer does not mean already-loaded classes are instrumented.
6. **Failing to distinguish statuses:** optional `SKIPPED` differs from runtime `FAILED`; `DEGRADED` must explicitly state which functionality was lost.
7. **Logging generic “agent started”:** you cannot infer the percentage of instrumented classes from the agent process status.
8. **Skipping postcondition verification:** the callback ran / `retransformClasses` returned, yet the transformer might have returned `null`.
9. **Catching and hiding unrecoverable errors:** swallowing verifier/linkage errors can cause tooling to proceed under false assumptions.
10. **Expanding fallback scope on your own:** do not switch to modifying modules/native methods or changing class loaders just because the initial path lacked a capability.
11. **Forgetting class loaders:** two classes with the same binary name defined by two different defining class loaders are two distinct targets; statistics and changes must bind to the exact `Class<?>`.
12. **Retrying blindly:** when a capability is unsupported, repeated retries do not create capability; retransformation/redefinition support status is fixed within a JVM instance per the API.
13. **Having no success criteria:** APPLIED should be accompanied by concrete evidence, such as a probe event, matching class hash/bytecode version, or measurement path verification.

## 11. Self-Check Questions

1. **`isModifiableClass(target)=true` but `isRetransformClassesSupported=false`. Can retransform be called?** No. The two conditions are independent; retransforming requires both.
2. **Can an agent that does not support retransform use `addTransformer(t)`?** Yes, for new class definitions (and callbacks in other contract-defined situations); it does not automatically alter already-loaded classes.
3. **Is `isRedefineClassesSupported=true` enough to replace retransform?** No. Compatible replacement bytecode is required, along with proof that the result meets the goal.
4. **The transformer returns `null` after a callback; can we report that the probe was installed?** No. `null` means no class bytes were changed in that callback; other evidence is needed to report the feature as applied.
5. **One already-loaded class is unmodifiable while other classes are modifiable. Should the entire agent stop?** Depends on feature policy; you can `SKIP` that class and continue with other targets while clearly recording the missing coverage.
6. **Does `isModifiableModule=true` mean classes in the module can be redefined?** No. That is the precondition for `redefineModule`, not `redefineClasses`.
7. **Can a fallback that only works for future-loaded classes report “100% coverage” for already-loaded classes?** No. Actual scope and the count of skipped targets must be recorded.
8. **Capability is true, but the JVM rejects the bytecode after retransform; what is the status?** `FAILED` for that operation; do not force `APPLIED`. Record the exception and cause for remediation.
9. **Why are stable reason codes needed?** To compare across JDKs, JVM vendors, and agent versions, detect recurring failures, and decide whether the manifest or transformation code needs fixing.
10. **For a mandatory protection feature, is it acceptable to use a non-equivalent fallback to let the application report ready?** No. Readiness conditions must be upheld according to the feature's contract.

## 12. Official References

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isRetransformClassesSupported`, `isRedefineClassesSupported`, `isNativeMethodPrefixSupported`, `isModifiableClass`, `isModifiableModule`, exceptions, and API limits.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks for class load/redefine/retransform, the `canRetransform` parameter, and `null` return semantics.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`/`agentmain` entry points and `Can-*` manifest attributes.
- [Java SE 21 — ClassDefinition](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): replacement bytecode used with `redefineClasses`.

**Takeaway:** Detect capabilities first, check the target and semantics before choosing a fallback, and **accurately report the scope achieved**. When no equivalent approach exists, `SKIPPED` with a reason is a valid outcome for an optional feature; reporting “succeeded” when the target was never instrumented is the real bug.
