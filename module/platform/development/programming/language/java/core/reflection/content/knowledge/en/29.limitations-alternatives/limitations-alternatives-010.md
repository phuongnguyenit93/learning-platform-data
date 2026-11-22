# Comparing Reflection Behavior Across Standard JVM, Restricted Runtimes, and AOT Environments

## 1. Purpose and Scope

Java Reflection enables looking up classes by name, reading annotations, locating constructors/methods/fields, and invoking them at **runtime**. On a standard JVM, this typically relies on class files available on the classpath or module path. However, the exact same program can behave differently when:

- running inside a JPMS **named module**, subject to `exports`, `opens`, and member access rules;
- running inside **GraalVM Native Image**, where most application structure is analyzed and compiled into a binary ahead of time;
- using **Spring AOT** or frameworks that precompute decisions normally inferred via classpath scanning/Reflection;
- running inside a sandbox, custom runtime, or platform with special rules on class loading, bytecode generation, and Reflection permissions.

This lesson compares **causes, symptoms, verification methods, and alternatives**. One key principle: **"ahead-of-time compilation" does not automatically mean "Reflection is unsupported"**. You must identify the exact technology, version, module policies, and kinds of dynamic operations in use.

## 2. Two Independent Questions to Ask Before Calling Reflection

Every Reflection call depends on at least two factors:

1. **What is present at runtime?** Are the class, constructor, method, field, annotation metadata, resource, or proxy class retained and present in the execution environment? This is a question of *reachability* or *availability*.
2. **Who is permitted to access it?** Does the lookup/caller have permission to read the module, use public members, or perform *deep reflection* on private members? This is a question of *accessibility*.

On the HotSpot JVM, `Class.forName("demo.Plugin")` might succeed while `getDeclaredConstructor().newInstance()` fails because the constructor is not accessible. On Native Image, `Class.forName(...)` itself or querying the constructor may lack required metadata **even though both the Java source and build JAR contain that class**.

**Registering reachability metadata is not a mechanism to bypass JPMS `private` encapsulation.** Conversely, opening a package with `--add-opens` does not automatically cause Native Image to retain every dynamically invoked member. Both sets of conditions must be evaluated separately.

## 3. Comparison Table of Common Environments

| Environment / Configuration | Runtime class/member discovery | Main constraints | Practical approach |
| --- | --- | --- | --- |
| Standard JVM, classpath | Can load classes on the path and inspect via Reflection | Classpath, class loader, Java language access | Check classloader, binary names, visibility |
| JVM with JPMS named modules | Reflection works but depends on the module graph | `reads`, `exports`/`opens`, and member permissions | Public APIs, selective `opens`, valid `MethodHandles.Lookup` |
| JVM with `jlink` custom runtime | Reflection works for included classes | Missing required modules in runtime image; JPMS still applies | Include needed modules when building the runtime |
| JVM with CDS/AppCDS | Reflection follows JVM/JPMS rules | Archive primarily optimizes loading and shared metadata | Do not assume Reflection is restricted |
| GraalVM Native Image | Supports Reflection on analyzed/registered elements | *Closed-world* analysis, reachability metadata, native runtime boundaries | Register exact classes/members or refactor statically |
| Spring AOT / native | Generates needed configuration and code at build time | Bean/profile/scan decisions are usually fixed before running | `RuntimeHints`, AOT processors, static bean registration |
| Restricted / custom runtime sandbox | Depends on specific platform/policy | May restrict bytecode loading, dynamic proxies, access rights | Read platform contracts, write integration tests on actual target |

`javac` compiling `.java` into `.class` **does not make Reflection disappear**. `jlink` builds a runtime image of selected modules; CDS caches part of class state for faster startup. Both differ from *closed-world native compilation*.

## 4. Why Does Native Image Need to Know Reflection Ahead of Time?

GraalVM Native Image analyzes the application at **build time** to determine which elements can be used and includes only needed components in the executable. A direct call like:

~~~java
new java.util.ArrayList<String>();
~~~

lets the tool see the needed type. A dynamic call is harder to predict:

~~~java
String className = args[0];
Class<?> type = Class.forName(className);
Object value = type.getDeclaredConstructor().newInstance();
~~~

At build time, `args[0]` may be unknown. The tool cannot by default retain **every class and constructor** of the application and all dependencies; doing so wastes resources and defeats binary-size optimization goals.

For Reflection calls with **constant or inferable** arguments, Native Image can compute needed elements at build time. Uninferable parts require **reachability metadata**. Modern GraalVM supports providing metadata via `reachability-metadata.json`, static analysis, library configs, the tracing agent, or helper APIs.

**You should not assert "whenever you use `Class.forName`, Native Image will fail".** With constant names, or when frameworks supply metadata, calls can work fine. Conversely, never rely on **one input** succeeding to conclude all other dynamic class names were packaged completely.

## 5. Java 17 Example Running on JVM: Selecting Implementations by Class Name

Create file `ReflectionModesDemo.java`:

~~~java
public class ReflectionModesDemo {
    public interface Task {
        String run();
    }

    public static class Alpha implements Task {
        public Alpha() {}

        @Override
        public String run() {
            return "alpha";
        }
    }

    public static class Beta implements Task {
        public Beta() {}

        @Override
        public String run() {
            return "beta";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Pass binary class name");
        }

        Class<? extends Task> type =
                Class.forName(args[0]).asSubclass(Task.class);
        Task task = type.getDeclaredConstructor().newInstance();

        System.out.println("type=" + type.getName());
        System.out.println("result=" + task.run());
    }
}
~~~

This is a **standalone** program containing `Task` and two implementations as member classes inside `ReflectionModesDemo`. Binary names of member classes use `$`, not dotted canonical names.

On a system with JDK 17+, run inside the directory containing the source:

~~~bash
javac --release 17 ReflectionModesDemo.java
java ReflectionModesDemo 'ReflectionModesDemo$Alpha'
java ReflectionModesDemo 'ReflectionModesDemo$Beta'
~~~

On **PowerShell**, use single quotes for arguments containing `$` as shown to prevent the shell from expanding variable names.

Output for Alpha:

~~~text
type=ReflectionModesDemo$Alpha
result=alpha
~~~

Output for Beta:

~~~text
type=ReflectionModesDemo$Beta
result=beta
~~~

**Verified:** the program above was compiled with `javac --release 17` and run for both cases on OpenJDK 21, matching the output exactly. `Class.forName` finds the class, `asSubclass(Task.class)` checks the contract, `getDeclaredConstructor().newInstance()` instantiates the object, and the final call is **ordinary interface dispatch**. Checking with `asSubclass` cannot replace constructor accessibility or Native Image member registration.

## 6. Building a Native Image: What Metadata Is Needed?

The example program receives the class name from a runtime argument, so native compilation must ensure both `Alpha` and `Beta` along with the constructors invoked by Reflection are recorded.

With GraalVM's **modern metadata format**, create file:

`out/META-INF/native-image/demo/reflection/reachability-metadata.json`

~~~json
{
  "reflection": [
    {
      "type": "ReflectionModesDemo$Alpha",
      "allDeclaredConstructors": true
    },
    {
      "type": "ReflectionModesDemo$Beta",
      "allDeclaredConstructors": true
    }
  ]
}
~~~

`allDeclaredConstructors` grants the ability to look up and invoke declared constructors of the corresponding class in the native binary. It **does not elevate Java permissions** for private constructors. In this program, both constructors are public and do not need `setAccessible(true)`. This metadata package does not need to declare reflective invocation for `run()` because `task.run()` goes through an interface known to the compiler ahead of time.

The metadata above is fairly broad regarding constructors; for larger projects, select the exact members actually needed according to the schema and tooling of your GraalVM version. Class names in JSON must be **full binary names**: member classes use `$`; packaged classes include the package prefix.

To build the demo, you need a **GraalVM installation with the `native-image` tool**, an OS-appropriate native toolchain, and a compatible Java version. Inside the source directory, you can run:

~~~bash
mkdir -p out/META-INF/native-image/demo/reflection
javac --release 17 -d out ReflectionModesDemo.java
# Write the JSON above to:
# out/META-INF/native-image/demo/reflection/reachability-metadata.json
native-image -cp out ReflectionModesDemo reflection-modes-demo
./reflection-modes-demo 'ReflectionModesDemo$Alpha'
./reflection-modes-demo 'ReflectionModesDemo$Beta'
~~~

`mkdir -p` is for Unix shells. On PowerShell, create the directory with:

~~~powershell
New-Item -ItemType Directory -Force out\META-INF\native-image\demo\reflection | Out-Null
~~~

After writing the JSON and compiling Java with the same flags, native build commands can use:

~~~powershell
native-image -cp out ReflectionModesDemo reflection-modes-demo
.\reflection-modes-demo.exe 'ReflectionModesDemo$Alpha'
.\reflection-modes-demo.exe 'ReflectionModesDemo$Beta'
~~~

**Expected results** of both native runs match the JVM `type=...` and `result=...` output in Section 5. This is a **proposed verification scenario; the native build was not executed in this lesson**. Existing GraalVM versions or packaging setups may use a different metadata schema: older versions commonly used `reflect-config.json` structured as an array with a `name` field; **do not mix the two formats arbitrarily**. Always verify documentation for your exact tool version and ensure metadata is actually included on the classpath at build time.

## 7. How Do Failures Manifest When Metadata Is Missing?

If required information is absent and Native Image cannot infer the access from code:

- `Class.forName(runtimeName)` may fail because the class was not retained or not registered for that kind of access.
- `getDeclaredConstructor`, `getDeclaredMethod`, `getDeclaredField`, or `newInstance` may fail because the member is not allowed to be queried/invoked via Reflection.
- Depending on version and checking mode, you may see `ClassNotFoundException`, `NoSuchMethodException`, `MissingReflectionRegistrationError`, or other diagnostics. **No single exception type is guaranteed for every missing-metadata case.**
- Code with `catch (Exception)` can hide part of the symptoms. Some missing-registration errors are `Error` rather than `Exception`; do not catch `Throwable` broadly and silently continue.

Also check **non-metadata causes**: wrong binary name, missing dependencies during native build, inaccessible private APIs, library version mismatches, or failed static class initialization.

On supported GraalVM versions, `--exact-reachability-metadata` enables stricter reporting of missing registrations. When running the native binary, `-XX:MissingRegistrationReportingMode=Warn` or `Exit` can help locate unregistered accesses. These flags are **version-dependent**; check the actual runtime documentation before adding them to CI.

## 8. Tracing Agent: Collecting Reflection That Actually Occurs

In the GraalVM ecosystem, the tracing agent can observe a run **on the JVM** and record metadata for Reflection, resources, proxies, JNI, and related dynamic features. A typical command form (requiring a GraalVM/JDK with a compatible agent):

~~~bash
java -agentlib:native-image-agent=config-output-dir=generated-config \
  ReflectionModesDemo 'ReflectionModesDemo$Alpha'
~~~

The agent records configuration for operations it **observes**. If you run only Alpha, there is no guarantee metadata for Beta is also collected. Design a **test matrix covering every dynamic path**, including configurable plugins, data types, error branches, and environment variants.

A better workflow is:

1. Collect metadata across representative test runs.
2. Review generated files; prune redundant entries and add uncovered branches.
3. Merge metadata into version-controlled build inputs.
4. Build the native binary and run tests against that binary itself.
5. Re-run whenever upgrading frameworks, libraries, or GraalVM versions.

The agent is a **discovery tool**, not automatic proof that every runtime configuration the system might encounter has been covered.

## 9. Reflection Is Not the Only Dynamic Feature

A system may get past reading annotations yet still fail when using something else. Compare needs:

| Dynamic feature | Standard JVM | Native Image / AOT considerations |
| --- | --- | --- |
| `Class.forName` from input | Finds classes on classpath visible to loader | Is the class retained/registered? |
| `Method.invoke` / constructor Reflection | Looks up and checks Java access | Does the member have query/invoke metadata? |
| `getDeclaredAnnotations` and reading values | Annotation metadata if `RetentionPolicy.RUNTIME` | Are annotation metadata and related types retained? |
| `Proxy.newProxyInstance` | Generates JDK proxy per runtime interfaces | Is the interface/proxy combination supported/registered? |
| Generating new bytecode via libraries | JVM can load new classes when tools/permissions allow | Native Image lacks open JVM classloading; needs pre-generation or special support |
| Loading resources by name | Reads resources present on classpath | Is the resource packaged/registered? |
| Reflection-based serialization | Often accesses hidden constructors/fields | Serialization and corresponding reflection metadata |
| JNI or native access | Many classes/members looked up from native code | JNI metadata and native linking capability |

For **dynamic proxies**, do not focus only on the handler class: **the interface list and order** also matter. For resources, Reflection metadata **does not substitute** for resource metadata. For `ServiceLoader`, verify providers are properly discovered and packaged on the native target. Each mechanism has its own registration domain; do not configure `allDeclaredMethods` across the entire application as a blanket workaround.

## 10. Another Boundary: JPMS and Deep Reflection

Even when running on the **full HotSpot JVM**, named modules enforce encapsulation boundaries.

Suppose:

~~~java
// module-info.java of the library
module data.core {
    exports demo.api;
}
~~~

`exports demo.api;` allows code in modules reading `data.core` to use **public APIs** in that package. It **does not grant permission** for another module to access private fields/methods via `setAccessible(true)`.

If a framework in module `data.client` needs deep reflection into `demo.api`, the owning module can open selectively:

~~~java
module data.core {
    exports demo.api;
    opens demo.api to data.client;
}
~~~

Or at JVM launch, when there is a valid security and operational rationale:

~~~bash
java --add-opens data.core/demo.api=data.client \
  --module-path mods -m data.client/demo.client.Main
~~~

In PowerShell, write the same command on one line:

~~~powershell
java --add-opens data.core/demo.api=data.client --module-path mods -m data.client/demo.client.Main
~~~

Notes:

- `exports` grants public API usage; `opens` allows deep reflection into the opened package.
- Whether the calling module **reads the target module** still matters for working with the corresponding types/APIs.
- `--add-opens` is a package-opening flag, not a Native Image reachability registration mechanism.
- `trySetAccessible()` reports whether enabling access succeeded; `setAccessible(true)` can throw `InaccessibleObjectException`.
- `MethodHandles.privateLookupIn(...)` has its own lookup-mode and module-permission requirements, not a way to ignore `opens` entirely.

**Diagnosing by error:** `InaccessibleObjectException` usually hints at JPMS access restriction; missing-metadata errors on native binaries usually hint at reachability configuration; `ClassNotFoundException` can also come from class paths/wrong names and needs tracing.

## 11. Spring AOT: Configuration Decided Before Runtime

Spring offers **Ahead-of-Time processing** to analyze `ApplicationContext`, generate bean instantiation code, and emit `RuntimeHints` for required dynamic operations. Things previously decided by classpath scanning or runtime introspection now need **sufficient information at build time**.

For example, under Spring AOT:

- the classpath and bean set are analyzed from the build-time environment; adding a new JAR at runtime does not necessarily make the AOT context discover new beans;
- conditions such as `@Profile` and `@Conditional` may be resolved during AOT processing; changing runtime config does not always alter the bean set the way a standard JVM run does;
- AOT code can use direct constructor/factory calls instead of Reflection;
- if custom libraries still must access members via Reflection, contribute **`RuntimeHints`** for the exact types/members.

Example registrar class in a Spring Framework project supporting AOT:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class TaskHints implements RuntimeHintsRegistrar {
    public static class PluginTask {
        public PluginTask() {}
    }

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                PluginTask.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS);
    }
}
~~~

This is **a Java file using Spring Framework**, not part of the pure JDK example in Section 5; it requires Spring AOT dependencies on the classpath. To inform the engine about the registrar, annotate an appropriate bean/config with `@ImportRuntimeHints(TaskHints.class)` or register via `META-INF/spring/aot.factories` as supported by Spring documentation. The goal is to declare which constructor will be invoked dynamically.

Spring automatically generates many hints for framework components the engine can analyze; **do not manually duplicate registrations for every bean**. Focus on plugins, conversions, library reflection, or data types not inferred by the engine from the bean graph. `RuntimeHintsPredicates` and Spring's Runtime Hints test utilities help verify registrations.

## 12. Behavioral Comparison Scenarios to Run in CI

Keep **the same input/output contract** and test across each environment; do not merely verify whether the application starts up.

| Test case | JVM classpath | Restricted JVM JPMS | Native Image with metadata |
| --- | --- | --- | --- |
| Select `Alpha` by binary name | Expect `alpha` | Expected if class/module accessible | Expect `alpha` if registered |
| Select `Beta` (other branch) | Expect `beta` | Depends on module | Must have metadata for Beta |
| Look up public constructor | Usually succeeds if class exists and accessible | Needs proper module access | Member must be retained/registered |
| Access private field from another module | May be denied | Likely `InaccessibleObjectException` without `opens` | Needs both metadata registration and appropriate permissions |
| Load new class/JAR after process startup | Possible via class loader | Additional module/loader limits apply | Do not assume brand-new bytecode can be loaded |
| Read dynamic resource | If resource is present | If present and permitted | Must be packaged/registered |
| Dynamic proxy from config | JVM can generate proxy class | May need interface module permissions | Needs matching proxy config/support |

**Minimum test suite:**

1. Run on a standard JVM classpath across all selectable class names.
2. If the project uses JPMS, run on the module path and test `opens` permissions, both allowed and denied cases.
3. Build the Native Image **from the exact commit, dependencies, and metadata** to be released; run the binary with at least two independent dynamic-input branches.
4. If using Spring AOT, verify build-time profiles/conditions, dynamic beans, and custom Runtime Hints.
5. Compare error types, causes, stdout/return values, and side effects; save logs containing binary names, classloaders/modules, and `native-image` version.

Core point: **passing JVM tests does not prove Native Image compatibility**. Conversely, failures on native are not automatically Java Reflection bugs: they may stem from missing metadata or wrong assumptions about decisions shifted to build time.

## 13. When Should You Replace Reflection with Static Design?

Reflection brings extensibility, yet AOT systems analyze code much more easily when execution types/metadata are explicitly specified.

Options worth considering:

- **Interface + explicit factory:** select known implementations and instantiate in code; compilers/AOT easily trace the call graph.
- **Constructor injection:** supply dependencies via constructors instead of scanning and mutating private fields.
- **`ServiceLoader` with predetermined providers:** fits when provider rules of the target runtime and build plugins are verified; do not treat it as an automatic guarantee for JARs loaded post-build.
- **Build-time generated registry:** an annotation processor or AOT step emits a name → factory map instead of runtime classpath scanning.
- **`MethodHandle`/`VarHandle`:** useful for optimizing call paths once permissions and handles are obtained; **does not guarantee bypassing Native Image metadata or JPMS**.
- **Reflection + hints** when flexibility is genuinely required: register exact classes/members and test the native binary in CI.

Example replacing dynamic class lookup with an explicit factory:

~~~java
import java.util.Map;
import java.util.function.Supplier;

public class StaticTaskFactoryDemo {
    interface Task { String run(); }
    static class Alpha implements Task {
        public String run() { return "alpha"; }
    }
    static class Beta implements Task {
        public String run() { return "beta"; }
    }

    public static void main(String[] args) {
        Map<String, Supplier<Task>> factories = Map.of(
                "alpha", Alpha::new,
                "beta", Beta::new);
        String key = args.length == 0 ? "alpha" : args[0];
        Supplier<Task> factory = factories.get(key);
        if (factory == null) {
            throw new IllegalArgumentException("Unknown task: " + key);
        }
        System.out.println(factory.get().run());
    }
}
~~~

Run:

~~~bash
javac --release 17 StaticTaskFactoryDemo.java
java StaticTaskFactoryDemo alpha
java StaticTaskFactoryDemo beta
~~~

Output for each invocation respectively:

~~~text
alpha
~~~

~~~text
beta
~~~

Here the compiler sees `Alpha::new` and `Beta::new` directly and needs neither `Class.forName` nor reflective constructor invocation. The trade-off is that brand-new implementations cannot be added simply by changing a config string; supporting a new type requires regenerating the registry or rebuilding the binary.

## 14. Common Diagnostic Errors

| Symptom | What to distinguish | Practical resolution |
| --- | --- | --- |
| `ClassNotFoundException` | Wrong name, missing classpath/module, or class absent from Native Image | Verify binary name, build classpath, metadata |
| `NoSuchMethodException` | Wrong signature, member stripped in native, or API version change | Check descriptor, method/constructor registration |
| `InaccessibleObjectException` | JPMS closes package to deep reflection | Public API or `opens` on the right package/module |
| `IllegalAccessException` | Access check failed | Check visibility/module/lookup context |
| `MissingReflectionRegistrationError` | Native Image lacks requested element | Add appropriate hints/metadata and run native tests |
| Proxy throws errors | Interface combination or AOT proxy metadata not inferred | Check interface list/order and proxy registration |
| Resource present on JVM, missing in native | Resource not included in image | Resource metadata or appropriate build plugin |
| Bean present on JVM, absent in Spring AOT | Build-time graph/conditions differ from runtime assumptions | Check AOT logs, profiles/conditions, explicit bean definitions |
| Native compile succeeds yet fails at runtime | Build pass did not cover all dynamic paths | Test full inputs/configs and exact registration diagnostics |

Catch exceptions at the right scope and log root causes. Do not fix issues by opening all JDK packages, retaining every class/method, or swallowing every exception; those approaches mask bugs and enlarge the application's size and attack surface.

## 15. Notes on Performance and Safety

Native Image typically targets **faster startup and smaller footprint**, trading off some flexibility in which elements may appear at runtime. However, `Method.invoke` call speed is not automatically faster simply from compiling natively; fair comparisons must measure warmup, throughput, peak RSS, startup, and real workloads.

- Broad Reflection registrations (such as `allDeclaredMethods` across large numbers of classes) can bloat binary size and retain unneeded metadata.
- Do not treat metadata as a permission check. If code is permitted private access by Java access rules and metadata allows it, it can become a sensitive manipulation channel.
- When using class names from untrusted input, constrain allowed implementations. Neither the JVM nor Native Image makes `Class.forName(userInput)` automatically safe.
- Applications configuring dynamic plugins must evaluate **the ability to add new logic post-build**. Native binaries have a *closed-world assumption* unlike the full JVM.
- If access does not require dynamic dispatch, favoring explicit code makes auditing and optimization easier.

## 16. Self-Check Questions

1. Does `javac` compiling `.java` before execution prevent `Class.forName` from working? **No.** The JVM still has the classpath/module path and runtime class loading.
2. Why does Native Image often need reachability metadata? Because build-time analysis cannot fully know which classes/members will be chosen from arbitrary runtime inputs.
3. Does `Class.forName("java.lang.String")` always require separate JSON metadata? **No.** Many calls with constant inputs can be inferred by Native Image.
4. If you have `--add-opens`, do you no longer need to declare reflection metadata? **False.** `opens` governs module permissions; metadata governs presence/reflectability in the image.
5. If the tracing agent runs only Alpha, does that prove Beta is covered? **No.** You must run every branch or declare additions.
6. How does `new Alpha()` differ from `Class.forName(name).getDeclaredConstructor().newInstance()` for AOT? Class/constructor selection in the first expression is **static**; the second can depend on runtime data.
7. When Spring AOT cannot infer Reflection access in custom code, what do you use? **`RuntimeHintsRegistrar` and `RuntimeHints`** (or appropriate hints/AOT processor integration).
8. If JVM tests pass while the native binary reports a missing member, what is the next step? Confirm the actual class/member/path, version-matched metadata, then rebuild and retest the binary itself.
9. A named module `exports` a public API without `opens`; can `setAccessible(true)` access a private field from another module? **Not guaranteed**; normally the package must be opened to the calling module.
10. Which approach fits better if there are only two tasks Alpha/Beta and no requirement to add arbitrary plugins? **Interface + static factory/registry** can be simpler, safer, and more AOT-friendly.

## 17. Official References for Version Cross-Checking

- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/) (structure of `reachability-metadata.json`, reflection, and diagnostic options).
- [GraalVM Native Image — Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/) (collecting metadata per run; match documentation paths to your actual release).
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) (build-time graph limits, `RuntimeHints`, `@ImportRuntimeHints`, testing).
- [Java SE 17 — Class.forName and Reflection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403).

**Key takeaway:** To compare Reflection across environments, check separately **whether the class/member exists at runtime**, **whether access permissions suffice**, and **whether behavior is fixed at build time**. On Native Image, add exact metadata and test the binary itself; on JPMS, clarify `reads`/`exports`/`opens`; and whenever possible, use static registries/factories to avoid unnecessary reflection needs.