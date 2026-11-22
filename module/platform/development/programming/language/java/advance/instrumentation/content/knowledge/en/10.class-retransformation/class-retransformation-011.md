# Static fields, existing objects, and class initializers are not re-initialized

**When using `Instrumentation.retransformClasses(...)`, the JVM can change the bytecode of an already loaded class without automatically restarting that class.** `static` fields that already have values retain their current values; existing instances are not recreated or have their constructors re-run; and the class initializer `<clinit>` of an already initialized class **is not invoked again merely because of retransformation**.

Conversely, **new method invocations can run the new bytecode directly on old objects**. These two facts must be understood together: retransformation primarily updates the **code definition**, and does not automatically migrate **runtime data**. If a V2 method assumes that static caches and instance fields have already been set up by V2 initializers, that method may behave incorrectly on data created by V1 even though the JVM accepted the bytecode.

This Knowledge article belongs to the **Retransformation** topic in Java Instrumentation, explaining the difference between replacing code and resetting state, static/constructor/`<clinit>` semantics, active stack frames, class schema limitations, and a Java 17+ program to verify these statements via output.

## 1. Rules according to the Java Instrumentation API

The Javadoc of `java.lang.instrument.Instrumentation.retransformClasses` states clearly:

- Retransformation re-processes class bytes through the matching transformer chain and attempts to install a new valid definition.
- **Initializers are not run merely because the definition is replaced**. The only exception is the normal initialization process already required by JVM semantics; `retransformClasses` itself is not a "reset class" trigger.
- **Values of static variables are preserved as they were before the call**, unless other code actively modifies them in the meantime.
- **Existing instances are not reconstructed and their fields are not automatically reset**.
- When a method has an **active stack frame**, that frame continues executing the old bytecode; **new invokes** will use the new method definition.
- If `retransformClasses` throws an exception, no class in the requested group of classes is re-installed according to the API contract.

Do not misinterpret the statement "instances of the retransformed class are not affected" as "old instances forever run only the old code". It refers to **object identity and the object's data**; new calls on that exact same object can execute the updated body.

### Before and after results table

| Component | After successful retransformation | Meaning |
|---|---|---|
| Class identity, defining class loader | Does not automatically create another class with a new identity | Still the same loaded class |
| `static int counter` | Retains current value | Does not re-run the assignment in `<clinit>` |
| `static final Config CONFIG` | Reference to the existing object does not automatically change | Does not rebuild singleton/cache |
| `static final String VERSION = "V1"` | Not reset/reinitialized according to V2 source | May also have been inlined in callers |
| `<clinit>` of an initialized class | Does not run again | V2 static initializer is not executed just by retransforming |
| Existing instance | Same object and instance-field values | Not reallocated/reinitialized |
| Constructor/instance initializer of old object | Does not run again | No automatic migration |
| Object **newly created** after retransform | Runs constructor of the current class definition | May carry instance values according to V2 |
| **New** method call | Can run V2 body | Old object still receives new behavior |
| Method currently in progress | Active frame continues V1 body | In-flight/overlapping requests may see both V1 and V2 |

**Caveat:** The table describes the automatic effect of the **retransformation operation**. An application thread can still mutate fields normally; a V2 method can later actively update static state or object fields. There is no guarantee of "freezing data forever".

## 2. Do not confuse loading, linking, initialization, and retransformation

The JVM has related but distinct steps:

```text
Class bytes --> Loading / defining class
                    |
                    v
             Linking (verify, prepare, resolve according to rules)
                    |
                    v
              Initialization when a normal trigger occurs
              - static field initializers
              - static initializer blocks
              - class initialization routine / <clinit>
                    |
                    v
             Class is initialized and active
             static fields + object graph + active threads
                    |
                    v
        Instrumentation.retransformClasses(...)
              re-runs matching transformer steps
              JVM checks and installs new class definition
                    |
                    v
       New methods can use new body
       static state + old objects + old <clinit>: NOT RESET
```

According to the Java Language Specification, class initialization occurs on triggers such as creating an instance, calling a static method, assigning a static field, or reading a static field that is not a constant variable; there are also certain reflection operations. Loading a class does not necessarily initialize it immediately. `Class.forName(name, false, loader)` illustrates the case where a class can be loaded without being initialized yet.

### What does `<clinit>` do?

Example:

```java
public final class Registry {
    static int starts = 0;
    static String label;

    static {
        starts++;
        label = "INITIAL";
    }
}
```

For a class initialized from this source, `starts == 1` and `label == "INITIAL"`. The compiler represents static initialization according to the JVM's class initialization mechanism (typically via the special method `<clinit>()V`). A V2 class version with a new static block will not cause `starts` to increment again just because the old class was retransformed.

**Case where a class was only loaded but not yet initialized:** Retransformation does not automatically invoke the initializer in place of a normal trigger. When the class is later used in a way that requires initialization, the JVM performs initialization according to normal semantics. Therefore, do not equate "not *re-initializing* an already initialized class" with "every loaded class is already initialized".

### Constructor `<init>` differs from `<clinit>`

- `<clinit>` relates to class initialization and static variables.
- `<init>` is the constructor path when creating an instance; instance field initializers/instance initializer blocks are typically placed into constructor code by the compiler.
- Retransformation does not perform `new` on old objects, nor does it re-run `<init>` on them.
- **New** objects created after installing the V2 body can run the V2 constructor body and receive new instance data.

An initializer not running again does **not** mean the method's contents were kept unchanged: the new body can be installed into the definition without being automatically invoked by the JVM at retransform time.

## 3. Reasoning example: V2 code, V1 data

Suppose V1 initializes a cache and a session:

```text
static CACHE -> map#A { "user-1": profileV1 }
static SEQUENCE = 91

session#S:
  attempts = 4
  status = "READY"
  client -> client#C
```

After retransforming `SessionService` to add tracing to `handle()`:

```text
static CACHE -> still map#A
static SEQUENCE -> still 91 if no thread updated it
session#S -> still the same object
  attempts = 4
  status = "READY"
  client -> client#C

handle() method body -> V2 for new calls
```

If `handle()` V2 only adds probes and reuses V1 fields, the change may be safe. However, if `handle()` V2 expects `CACHE` to have a V2 schema created by a new static initializer, that assumption is wrong.

**No automatic operation in `retransformClasses` does the following:**
- call `CACHE.clear()`;
- recreate singletons, worker pools, or DB connections;
- run constructors on all existing instances;
- rewrite fields of old objects;
- recompile other classes that already inlined constants.

If you want to do those things, you need a separate state management/deployment path and must consider concurrency/rollback.

## 4. Preserving static fields: two special cases

### 4.1. Mutable static and shared references

```java
// Illustrative snippet, not a standalone program:
static long requests = 12_345L;
static final java.util.Map<String, Integer> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Suppose the class is already initialized and the cache has data. Retransforming to change the body of a method accessing `requests`/`CACHE` does not automatically revert `requests` back to 12_345 if it has already incremented to 20_000; nor does it automatically create a new `ConcurrentHashMap`. **`static final` here prevents reassigning the variable under normal Java rules, and does not prevent the underlying map object from being mutated via method calls.**

In a multi-threaded application, a field can change right during retransformation by another thread. Two unequal before/after snapshots are not proof that the JVM re-ran `<clinit>`. To prove the invariant, use a sequential test with isolated counters and state.

### 4.2. Compile-time constants and inlining

```java
public static final String MODE = "V1"; // constant variable
public static final int LIMIT = 10;     // constant variable
```

These are constant variables under Java rules if they satisfy the type and constant-expression initializer requirements. `javac` can embed the literal `"V1"` or `10` directly into the bytecode of the **caller**, so the caller does not necessarily read the field at runtime anymore. Retransforming the class declaring `MODE` does not automatically update the literal in every already-compiled client.

Furthermore, changing initializer code does not automatically change live static values. Therefore, if you want to hot-update a configuration, **do not** design it as a compile-time constant and expect retransforming the declaring class to update the entire system. Use an explicit runtime accessor/configuration with proper memory visibility and mutation policy.

### 4.3. Static final objects are not re-initialized

```java
// Semantic example, Config and load() are not defined:
static final Config CONFIG = Config.load();
```

If `CONFIG` is pointing to a V1 configuration object, retransforming a class that uses it does not cause `Config.load()` to run again. Changing a method body from V1 to V2 without paying attention to `CONFIG` can create a data or endpoint mismatch. This is a lifecycle design issue, not a bytecode verifier error.

## 5. Schema limitations: cannot automatically add fields to migrate objects

`Instrumentation.retransformClasses` allows transforming method bodies, constant pools, and attributes within JVM TI constraints. Under the standard mechanism, you cannot arbitrarily add/remove/rename fields/methods, change method signatures, or change inheritance and expect retransformation to succeed.

| Desired change | Is it a normal retransform? | Notes |
|---|---|---|
| Insert timing bytecode into a method | Possible | Must keep bytecode valid and preserve semantics |
| Replace method body while keeping name/descriptor | Possible | New method must be compatible with V1 state |
| Change constructor logic (same descriptor) | Possible within valid body limits | Only affects subsequent constructor invocations |
| Replace `<clinit>` code | Does not make the old class's initializer run again | Do not use to reset static state |
| Add a new instance field | Not a normally supported schema change | No mechanism to create fields for old objects |
| Change superclass/interfaces | No | Violates class schema limits |
| Change signature or delete method | No | May throw `UnsupportedOperationException` |
| Migrate all instances via retransform | No | Requires separate state design |

A Java agent using `ClassFileTransformer` also needs to be compatible with other transformers. Returning a new class bytes array from a separate compilation can succeed in a controlled demo, but it is not a production recipe if multiple agents are inserting probes or if class loading/loader context is complex.

## 6. Runnable example on Java 17+: retransforming V1 into V2

We use a **startup Java agent** via `-javaagent` to obtain the `Instrumentation` object; the test program itself calls `retransformClasses`. This approach skips the Attach API/PID requirement, while still using the exact **retransformation** mechanism to be studied.

Plan:

1. Compile **V1** and **V2** of the same binary class `StateTarget` into two different directories.
2. V1 static block increments `initRuns` once and assigns `label="INIT_V1"`; V2 static block is intentionally different (`+100` and `"INIT_V2"`).
3. Create an old object with `value=7`.
4. The agent registers a transformer with **canRetransform=true**; when `StateTarget` is retransformed, it returns V2 class bytes with the same schema.
5. Print the old object after retransform: the method body is V2, the field is still 7, and the static label is still INIT_V1.
6. Create a new object after retransform: the V2 constructor assigns `value=107`, and the V2 static initializer still **does not run again**.

### 6.1. Directory layout

```text
demo/
  v1/
    StateTarget.java
  v2/
    StateTarget.java
  SwapAgent.java
  StateDemo.java
  agent.mf
```

The two `StateTarget.java` sources have the same class name but **are not compiled into the same output directory**. This is crucial: the goal is to have V2 class bytes for the transformer to use, not to put two classes with the same name on the runtime classpath.

### 6.2. `v1/StateTarget.java`

```java
public final class StateTarget {
    public static int initRuns;
    public static String label;
    public int value;

    static {
        initRuns++;
        label = "INIT_V1";
    }

    public StateTarget(int input) {
        value = input;
    }

    public String describe() {
        return "V1:" + value + ":" + label;
    }
}
```

V1 has exactly three fields (two static, one instance), one constructor `(I)V`, and the method `describe()Ljava/lang/String;`. Executing `new StateTarget(7)` will initialize the class before creating the instance: `initRuns=1`, `label="INIT_V1"`, instance field `value=7`.

### 6.3. `v2/StateTarget.java`

```java
public final class StateTarget {
    public static int initRuns;
    public static String label;
    public int value;

    static {
        initRuns += 100;
        label = "INIT_V2";
    }

    public StateTarget(int input) {
        value = input + 100;
    }

    public String describe() {
        return "V2:" + value + ":" + label;
    }
}
```

V2 intentionally **keeps the same class name, field names/types, constructor/method descriptors, superclass, and access modifiers**. The changes lie in the method bodies and the related constant pool. If V2 were loaded as a new class in a new JVM, its static block would differ from V1; but when used as a new definition for an **already initialized V1 class**, the V2 static block **is not automatically invoked**.

### 6.4. `SwapAgent.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class SwapAgent {
    private static volatile Instrumentation instrumentation;

    private SwapAgent() {
    }

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
    }

    public static boolean apply(byte[] replacement)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent unavailable");
        }

        if (!inst.isRetransformClassesSupported()) {
            System.out.println("SKIPPED: RETRANSFORM_UNSUPPORTED");
            return false;
        }
        if (!inst.isModifiableClass(StateTarget.class)) {
            System.out.println("SKIPPED: CLASS_UNMODIFIABLE");
            return false;
        }

        ClassFileTransformer transformer =
                new ReplacementTransformer(replacement);
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(StateTarget.class);
        } finally {
            inst.removeTransformer(transformer);
        }
        return true;
    }
}

final class ReplacementTransformer implements ClassFileTransformer {
    private final byte[] replacement;

    ReplacementTransformer(byte[] bytes) {
        this.replacement = bytes.clone();
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] input) {

        if ("StateTarget".equals(className)
                && classBeingRedefined == StateTarget.class) {
            return replacement.clone();
        }
        return null;
    }
}
```

`SwapAgent` and `ReplacementTransformer` in the same source file is valid because only `SwapAgent` is `public`. The JDK generates `SwapAgent.class` and `ReplacementTransformer.class`. The transformer only returns V2 bytes when it sees the exact target class in a retransform/redefine callback, without modifying `input` directly.

With the Java 9+ overload that adds a `Module` parameter, if you do not override the six-parameter version, the default implementation delegates to the five-parameter overload written here. Therefore, the code above still applies on Java 17+.

In a real product, replacing the entire classfile bytes with another build artifact requires verifying the compiler version, schema, active transformers, and the byte source corresponding to the class loader. The demo picks a deterministic target and data to clarify semantics, and does not recommend arbitrarily copying whole class files into a production application.

### 6.5. `StateDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class StateDemo {
    private static void show(String stage, StateTarget target) {
        System.out.println(
                stage
                + " body=" + target.describe()
                + " initRuns=" + StateTarget.initRuns
                + " field=" + target.value);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: StateDemo <v2-class-file-path>");
            System.exit(2);
        }

        StateTarget existing = new StateTarget(7);
        show("BEFORE", existing);

        byte[] v2 = Files.readAllBytes(Path.of(args[0]));
        if (!SwapAgent.apply(v2)) {
            return; // Do not falsely report success when capability is unavailable.
        }

        System.out.println("SWAP_OK");
        show("AFTER", existing);

        StateTarget newer = new StateTarget(7);
        show("NEW", newer);
    }
}
```

Lifecycle:

- `existing` is constructed by V1 before retransformation.
- `show("AFTER", existing)` **does not** recreate the instance, but `target.describe()` is a **new method call**, so it can use V2.
- `newer` is constructed after V2 has been installed; the V2 constructor body sets `value=107`.
- Static `label` remains at `INIT_V1` and `initRuns` remains `1`; the retransform operation itself does not run the V2 static initializer.

### 6.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: SwapAgent
Can-Retransform-Classes: true

```

The manifest requires a trailing blank line. `Can-Retransform-Classes: true` requests the agent capability, and does not force every JVM to provide that capability. The code still checks `inst.isRetransformClassesSupported()` and `inst.isModifiableClass(StateTarget.class)` before attempting.

This is a startup agent launched via `-javaagent`, not a dynamically loaded agent via `VirtualMachine.loadAgent`. Neither `Agent-Class` nor `agentmain` is needed in the example's manifest.

### 6.7. Build and run commands

Use **JDK 17 or later**. On Bash/macOS/Linux, from the `demo` directory:

```shell
mkdir -p build/v1 build/v2
javac -d build/v1 v1/StateTarget.java
javac -d build/v2 v2/StateTarget.java
javac -cp build/v1 -d build/v1 SwapAgent.java StateDemo.java

jar cfm swap-agent.jar agent.mf \
  -C build/v1 SwapAgent.class \
  -C build/v1 ReplacementTransformer.class

java -Xverify:all -javaagent:swap-agent.jar \
  -cp build/v1 StateDemo build/v2/StateTarget.class
```

With **Windows PowerShell**, you can create directories as follows, then use commands without `\` line continuations:

```powershell
New-Item -ItemType Directory -Force build/v1, build/v2 | Out-Null
javac -d build/v1 v1/StateTarget.java
javac -d build/v2 v2/StateTarget.java
javac -cp build/v1 -d build/v1 SwapAgent.java StateDemo.java
jar cfm swap-agent.jar agent.mf -C build/v1 SwapAgent.class -C build/v1 ReplacementTransformer.class
java -Xverify:all -javaagent:swap-agent.jar -cp build/v1 StateDemo build/v2/StateTarget.class
```

**Classpath note:** only `build/v1` is on the runtime `-cp`. The V2 file must be passed as a **bytes file** via the `StateDemo` argument, not by putting `build/v2` on the classpath so the JVM picks V2 from the start. If you do that, the result no longer demonstrates retransformation.

### 6.8. Expected stdout when the JVM supports retransform

```text
BEFORE body=V1:7:INIT_V1 initRuns=1 field=7
SWAP_OK
AFTER body=V2:7:INIT_V1 initRuns=1 field=7
NEW body=V2:107:INIT_V1 initRuns=1 field=107
```

- The **BEFORE** line confirms V1, one static initialization, and the old object storing 7.
- **SWAP_OK** is only printed after `retransformClasses` returns successfully.
- The **AFTER** line: the new method returns the V2 prefix, **the same old object** still has value=7, and static state is still INIT_V1.
- The **NEW** line: the new constructor sets value=107; V2 `<clinit>` is not called again, so static state remains unchanged.

This is the expected stdout on HotSpot JDK 17/21 supporting the capability, not a guaranteed output for every JVM implementation/configuration. On a JVM without support, the code prints `SKIPPED: RETRANSFORM_UNSUPPORTED`; if the class is unmodifiable, it prints `SKIPPED: CLASS_UNMODIFIABLE`. If the V2 bytes are invalid under HotSwap restrictions, the API throws an exception and does not print `SWAP_OK`. Do not remove the check branches to force the result.

### 6.9. Checking the schema with `javap`

```shell
javap -p -s -classpath build/v1 StateTarget
javap -p -s -classpath build/v2 StateTarget
javap -c -p -classpath build/v1 StateTarget
javap -c -p -classpath build/v2 StateTarget
```

Both versions must have matching field/method descriptors, even though the instructions of `<init>`, `<clinit>`, and `describe` differ. `javap` helps confirm the compiler generated the expected bytecode; running the application test with `-Xverify:all` proves the JVM accepts the class bytes and that new calls behave according to the scenario.

## 7. Active stack frames: V1 and V2 can coexist

Suppose thread A has already **entered** `calculate()` V1 and is processing a long-running request, while thread B retransforms the class to replace `calculate()` with V2:

```text
Thread A                                Thread B
--------                                --------
enter calculate() V1
  frame F(V1) is running                retransformClasses(Target.class)
                                        install body V2
continue F(V1)                         new invoke calculate() -> V2
return result using V1 code
```

The Javadoc specifies that an active frame **continues the old bytecode**. It does not automatically jump to the start of the V2 method, does not change the program counter to a new offset, and does not automatically re-run code. Only when there is a **new invocation** is the V2 body used according to the contract.

Consequences:

- For a brief period, there may simultaneously be requests going through V1 and new requests going through V2.
- Both can access **the same static fields** and the same object graph. There is no separate state snapshot per method version.
- Retransform does not provide a transaction mechanism to synchronize all requests, reset caches, or switch in-progress operations to the new code.
- If a hotfix requires a strong consistency boundary, you need to quiesce/drain traffic or use a versioned routing strategy at the application layer.

**Do not misinfer:** An active frame using V1 bytecode does not mean the old object is "permanently bound" to V1. That same object on a new call after retransform will still use V2.

## 8. Differences between retransformation, redefinition, new class loader, and restart

| Mechanism | Replaces body of loaded class? | Re-runs `<clinit>` of initialized class? | Resets old static/instances? |
|---|---|---|---|
| `retransformClasses` | Possible, via matching transformers | No | No |
| `redefineClasses` | Possible, via caller-provided `ClassDefinition` | No | No |
| `addTransformer(t)` for future loads | Does not automatically modify loaded classes | Does not apply to old classes | No |
| Intentionally calling application `reset`/`refreshConfig` | Does not necessarily change bytecode | No | **Can** actively change state |
| Defining same-named class with a **different** class loader | Creates a different class by JVM identity | New class initializes by its own rules | Old class and old objects are not reset |
| Restarting JVM or redeploying fresh instance | Reloads class in a new runtime | New class initializes by normal rules | No automatic migration from old JVM |

`redefineClasses` and `retransformClasses` share many similarities regarding state preservation, but **their input contracts differ**: redefine takes replacement bytes in `ClassDefinition`; retransform re-runs the transformation process from the baseline class bytes according to JVM rules. Do not treat them as completely equivalent APIs.

A class with the same binary name in a different loader is a **different** class. If that class runs `<clinit>`, it cannot be taken as proof that the old class was retransformed and re-initialized.

## 9. Common design mistakes

### 9.1. Changing a method while assuming the static cache already has the V2 schema

V1 cache stores key `"user:123"`, while the V2 method lookup needs `"tenant/user:123"`. Retransforming to replace code does not automatically convert V1 cache data. The JVM may verify the V2 bytecode, yet the application still returns wrong results or encounters exceptions.

**Solution:** Make V2 able to read both old and new state, or have a dedicated migration with locking/versioning/rollback, or restart/redeploy. Do not force a serializer/transformer to directly traverse all objects while the JVM is processing a class definition.

### 9.2. Changing the V2 constructor while expecting old objects to have the new default

The V2 constructor sets `timeout=30`, while existing V1 objects contain `timeout=0`. A new method assuming all objects have a positive timeout will fail on old objects. Retransformation does not re-invoke constructors to "patch" fields.

### 9.3. Treating `static final` as hot-reload configuration

`static final Config CONFIG = Config.load()` does not automatically re-run `Config.load()`. Compile-time primitive/String constants may also be inlined at callers. You need a runtime accessor/config service if you want to change configuration dynamically.

### 9.4. Rolling back code while forgetting to roll back data

The V2 method writes a new data version into the cache/database. Later, the agent retransforms back to V1. The V1 method body returns, but data already modified by V2 **is not automatically reverted**. A rollback plan must separately handle state transitions and compatibility.

### 9.5. Reading a static counter before/after and concluding `<clinit>` ran again

Another thread can increment the counter normally. Use sequential tests, clearly identify application operations, and read controlled logs/counters. Do not treat every state change around retransform time as caused by a VM reset.

### 9.6. Failing to check class loader/capability

Two classes with the same name loaded by two different defining loaders are **two different targets**. You must use the exact `Class<?>` object and check `isRetransformClassesSupported()` and `isModifiableClass(target)` before calling the API.

## 10. Diagnostic checklist and API errors

### 10.1. Checks before retransform

```java
// Sample snippet inside an agent; inst and target must be validly obtained by the agent:
if (!inst.isRetransformClassesSupported()) {
    // report SKIPPED: capability unsupported
} else if (!inst.isModifiableClass(target)) {
    // report SKIPPED: target unmodifiable
} else {
    inst.retransformClasses(target);
}
```

The snippet above is **illustrative only**, not a standalone Java program because `inst` and `target` are undeclared. The experiment in section 6 already provides a complete program.

Errors that can occur even when prechecks succeed:

- `UnmodifiableClassException`: target cannot be modified.
- `UnsupportedOperationException`: capability or form of change is not supported.
- `ClassFormatError`, `UnsupportedClassVersionError`: invalid/incompatible class bytes.
- `NoClassDefFoundError`, `ClassCircularityError`, `LinkageError`: definition, dependency, or linkage errors.
- A transformer can return `null` (no change) or throw an exception treated by the JVM as `null` at the transform step; `retransformClasses` not throwing does not necessarily prove a specific probe was inserted.

Do not use `catch(Throwable)` to swallow all JVM errors and report success. Distinguish **OPERATION_COMPLETED** (the API returned) from **EFFECT_VERIFIED** (the method actually changed as intended) and **STATE_MIGRATED** (if there is an independent migration).

### 10.2. Symptom table

| Symptom | Explanation | Check |
|---|---|---|
| `static` after retransform is still the V1 value | Expected behavior | No initializer reset |
| V2 `<clinit>` logs nothing | Expected behavior for an initialized class | No new class init |
| Old object still carries V1 field | Expected behavior | Object is not recreated |
| Old object calling method produces V2 result | New method invocation uses new body | Inspect callbacks and installed bytes |
| New object uses V2 constructor | New `<init>` is called when creating a new object | Check constructor output |
| In-progress method still has V1 result | Active frame continues old bytecode | Try a new invocation after retransform |
| JVM rejects V2 bytes | Problem with class schema/version/verification | `javap`, manifest, exception |
| Compile-time constant at caller does not change | Literal was inlined | Inspect caller bytecode |
| Cache/singleton is not refreshed | No automatic state migration | Check explicit refresh path |
| Transformer removed but method is still V2 | Removing does not roll back an already installed definition | To revert, another valid operation is needed |

## 11. Safe migration and testing during hot instrumentation

If V2 code strictly requires a new state schema, you must solve that at the **application design layer**:

1. **Write backward-compatible V2:** able to read V1 object/static state and transition to the new state in a controlled manner.
2. **Decouple runtime configuration from `<clinit>`:** provide a refresh API/immutable config snapshot with appropriate memory visibility.
3. **Version your data:** distinguish V1/V2 state instead of inferring from code version.
4. **Quiesce traffic when needed:** drain in-flight requests before migration to reduce V1/V2 concurrency.
5. **Separate code rollback and state rollback:** do not expect reverse retransformation to restore cache/database.
6. **Track metrics by version:** a counter surviving from V1 to V2 can mix semantics; use appropriate labels/versioning policy.
7. **Verify with a real JVM:** valid bytecode does not equate to business invariants holding for objects created before retransformation.

A worthwhile test suite:

- [ ] Static counter retains pre-retransform value when no other thread modifies it.
- [ ] Static initializer of an initialized class does not run again.
- [ ] Reference to an old object remains the same reference and old instance fields are preserved.
- [ ] Old object invoking a new method exhibits the defined V2 behavior.
- [ ] New object runs constructor/instance initialization according to current bytecode.
- [ ] Running active frames continue V1 behavior per contract.
- [ ] Inlined compile-time constants are properly handled in the code change plan.
- [ ] Schema changes beyond capability report an error instead of overwriting.
- [ ] A migration/rollback plan exists if the data schema also changes.
- [ ] Transformer does not strip instrumentation from other transformers.

## 12. Self-check questions

1. **Does retransforming an already initialized class automatically re-run `<clinit>`?** No.
2. **After retransform, does a static counter revert to the value declared in V2?** Not merely from the retransform operation; it keeps its current value if nothing else modifies it.
3. **Does an old object have its constructor re-run?** No.
4. **Can an old object run the new method body?** Yes, on a new invocation after V2 is successfully installed.
5. **Which constructor does a new object created after retransform run?** The constructor body in the current definition.
6. **Does an active method frame switch mid-execution to V2?** No, an active frame continues the old bytecode.
7. **Does changing the V2 static initializer to assign a new label update the V1 singleton?** No.
8. **Why might a final String constant remain in a caller?** The compiler can inline the constant-expression value.
9. **Can you add a new field via normal retransform and automatically populate it for old objects?** No, such schema changes are not supported.
10. **If a class is not yet initialized, is retransform equivalent to initializing the class?** No. Initialization still follows normal JVM triggers.
11. **Does rolling back a V2 method to V1 roll back data already written by V2?** No.
12. **Why is AFTER `V2:7:INIT_V1` in the demo?** The method uses the V2 body, but the old object still has value=7 and static label INIT_V1.
13. **Why is NEW `V2:107:INIT_V1`?** The V2 constructor runs on the new instance, but the V2 class initializer does not automatically re-run.
14. **Are `retransformClasses` and `redefineClasses` completely identical?** No, their inputs and processing pipelines differ; both preserve state/initializers per API rules.
15. **If the JVM accepts the bytes yet the V2 method still fails, what could be the cause?** V2 code is incompatible with V1 state even though the bytecode is type-correct.
16. **What conditions must be checked before retransforming?** JVM-wide capability and modifiability of the exact Class object.
17. **Why does a class with the same name in a different class loader have its own `<clinit>`?** Because class identity includes name and defining loader; it is a different class.
18. **Does removeTransformer restore the V1 body?** No. It does not automatically roll back an already installed definition.

## 13. Official references

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `retransformClasses`, active frames, static values, instances, and initializers not re-running.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capabilities, `isModifiableClass`, `redefineClasses`, limitations, and exceptions.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform chain, returning `byte[]` or `null`, retransformation-capable transformers.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, manifest `Can-Retransform-Classes`.
- [Java Language Specification SE 21 — Initialization, `12.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4): class initialization triggers and process.
- [Java Language Specification SE 21 — Field Initialization, `8.3.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.2): static field initializers and constant variables.
- [JVM TI — RetransformClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): structural change limitations and updating class definitions.

**Conclusion:** `retransformClasses` replaces **code**, and does not automatically reset **state**. Static fields, singleton references, and existing objects are preserved; `<clinit>` does not re-run for an already initialized class; active method frames continue executing the old bytecode. Because V2 methods can run on V1 data, design for backward compatibility or controlled migration instead of relying on automatic "re-initialization".