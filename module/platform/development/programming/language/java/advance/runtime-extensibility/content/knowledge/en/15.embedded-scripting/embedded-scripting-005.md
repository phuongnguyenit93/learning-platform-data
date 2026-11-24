# Nashorn Left the JDK in Java 15: Embedding JavaScript Requires Supplying Your Own Engine

Starting with **JDK 15**, Java applications are no longer guaranteed to have the Nashorn JavaScript engine bundled with the JDK. Lines that were familiar on Java 8–14, such as `new ScriptEngineManager().getEngineByName("nashorn")`, may receive **`null`** when moving to Java 15/17/21 or later if the application does not bring its own scripting engine.

This **does not mean Java removed embedded scripting support**. The standard **JSR-223 / `javax.script`** API in the `java.scripting` module is still present. What was removed from the JDK is **the bundled Nashorn implementation, Nashorn-specific APIs, and the `jjs` tool**, not the shared `ScriptEngine` contract. To evaluate JavaScript code inside a Java process, the application must **choose, declare, package, and configure a standalone engine**, and then verify engine discovery at startup.

This article explains the exact change in JDK 15 (JEP 372), how to detect a missing engine, how to add **standalone Nashorn** with Maven, alternative choices, JPMS/module path scenarios, migration risks, and required tests for applications embedding JavaScript.

## 1. Version Milestones and Scope of JEP 372

| Java Version | Nashorn Status in the JDK | Impact on Applications |
| --- | --- | --- |
| **Java 8** | Nashorn integrated into the JDK (JEP 174) | Can usually find the JDK JavaScript engine via `ScriptEngineManager` |
| **Java 9–10** | Nashorn still in the JDK | Engine still exists, but JPMS applications must understand module/service discovery |
| **Java 11** | Nashorn and `jjs` **marked deprecated for removal** under JEP 335 | Warnings appear and replacement must be planned; engine not yet removed in this version |
| **Java 12–14** | Bundled Nashorn still exists, on the removal roadmap | Should not build long-term architecture around the bundled engine |
| **Java 15 and later** | JEP 372 **removes bundled Nashorn from the JDK** | Must supply a separate engine implementation if the application needs to run JavaScript |

**JEP 372 – Remove the Nashorn JavaScript Engine** introduces specific changes:

- Removes the JDK module `jdk.scripting.nashorn`, including legacy Nashorn API packages such as `jdk.nashorn.api.scripting` and `jdk.nashorn.api.tree`.
- Removes the shell module `jdk.scripting.nashorn.shell` and the **`jjs`** command-line tool.
- Does not remove `javax.script`, `ScriptEngineManager`, `ScriptEngine`, `ScriptEngineFactory`, or the **`java.scripting`** module.

**Important distinction:** `jjs` was the shell bundled with Nashorn and was removed; do not infer that every JDK CLI or all Java scripting tools were removed. If a Java tool still provides a way to run scripts via JSR-223, it still needs an engine discoverable at runtime.

Historical takeaway: **“Nashorn left the JDK” is different from “the Nashorn project ceased to exist”**. The OpenJDK team maintains an independent **standalone Nashorn** build that applications can add as a dependency themselves, though it does not appear automatically just because you install a modern JDK.

## 2. Two Layers to Understand: Standard API vs. Engine Implementation

Visualizing the embedded scripting architecture:

~~~text
Java application / host
       |
       | javax.script (module java.scripting)
       v
ScriptEngineManager
       |
       | discovers ScriptEngineFactory via service-provider mechanism
       v
+-------------------------------+
| Third-party engine provider   |
| Nashorn standalone / GraalJS  |
| Rhino / another implementation|
+-------------------------------+
       |
       v
ScriptEngine.eval(...) -> JavaScript result
~~~

Division of roles:

- **`javax.script.ScriptEngine`:** contract for evaluating scripts, managing `Bindings`/`ScriptContext`, and returning corresponding Java results. There is no built-in JavaScript parser/compiler inside this interface.
- **`javax.script.ScriptEngineFactory`:** provides name, aliases, language, version, characteristics, and creates a `ScriptEngine`.
- **`ScriptEngineManager`:** discovers `ScriptEngineFactory` instances visible in the runtime environment via the service provider mechanism, then creates an engine by name/language/file extension/MIME type. The manager **does not download dependencies from Maven or the Internet**.
- **Engine implementation:** the independent library that actually parses and runs JavaScript, which must sit where the JVM/class loader/module graph can discover it.
- **`java.scripting`:** standard JDK module containing JSR-223, continuing to exist on Java 17. When writing an explicit named Java module using `javax.script`, the consumer needs `requires java.scripting;`.

Therefore the following code **still compiles** on Java 17:

~~~java
import javax.script.ScriptEngineManager;
ScriptEngineManager manager = new ScriptEngineManager();
~~~

This is an *illustrative snippet that must be placed inside a class/method*, not a standalone Java file. However, compiling cleanly **does not prove** a `JavaScript` engine is present.

### 2.1. When `getEngineByName` Returns null

~~~java
ScriptEngine engine = new ScriptEngineManager().getEngineByName("nashorn");
~~~

Per the Javadoc, `getEngineByName` returns **`null` if no factory registered under the requested name is found**. Common causes:

1. No JavaScript engine exists in the runtime.
2. The library exists on disk but **is not on the runtime classpath/module path**, or the module has not been resolved.
3. The class loader used to discover providers cannot see the library's `ScriptEngineFactory`.
4. An engine is present, but **did not register the `"nashorn"` alias** the application uses.
5. An error loading the provider/dependencies caused incomplete discovery; inspect related logs/exceptions.

Therefore, do not catch a `NullPointerException` thrown at `engine.eval(...)` and conclude “Java 17 does not support JavaScript”. The initial issue is usually that **engine lookup found no implementation**.

### 2.2. The Name `"JavaScript"` Is Not a Mandatory Engine

Legacy applications may write:

~~~java
manager.getEngineByName("js");
manager.getEngineByName("JavaScript");
manager.getEngineByName("nashorn");
~~~

These aliases depend on `ScriptEngineFactory.getNames()` of the engine actually installed. Not every implementation provides all three names. If one engine has multiple aliases, each alias may locate the same kind of engine; however, there is no rule that “the JDK will automatically pick the best JavaScript engine” when no matching provider exists.

Enumerate `manager.getEngineFactories()`, read `factory.getNames()`, and pick a name supported by the engine. In production, **pin the desired provider/version** and fail-fast when unmet, rather than silently running scripts on another engine with non-equivalent semantics.

## 3. Example 1 — Diagnosing on JDK 17 Without a JS Engine

Standalone `EngineProbe.java` file requiring only JDK 17; **no JavaScript dependency added**:

~~~java
import javax.script.ScriptEngineManager;

public final class EngineProbe {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();
        System.out.println("factoryCount=" + manager.getEngineFactories().size());
        System.out.println("nashornFound=" + (manager.getEngineByName("nashorn") != null));
        System.out.println("javascriptFound=" + (manager.getEngineByName("JavaScript") != null));
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac --release 17 EngineProbe.java
java -cp . EngineProbe
~~~

On a clean **Corretto JDK 17.0.15 with no script engine added**, the verified output is:

~~~text
factoryCount=0
nashornFound=false
javascriptFound=false
~~~

**This is the output of the verified environment, not an immutable stdout for every JDK 17.** If an application has GraalJS, standalone Nashorn, or another provider on the classpath/module path, `factoryCount` can be greater than 0, and one or both aliases may locate an engine. That very difference demonstrates that `javax.script` is a **runtime plugin discovery** mechanism, not a promise that the JDK always ships a JavaScript implementation.

Command to inspect the Java Scripting module:

~~~bash
java --list-modules
~~~

Look for the `java.scripting` module in the list. The presence of this module proves only that the **JSR-223 API** exists, not that a JavaScript engine has been installed.

## 4. Supplying Your Own Engine: Available Options

Depending on your goals, there are three common directions:

| Option | Best Suited When | Points to Verify |
| --- | --- | --- |
| **OpenJDK Nashorn standalone** | Application runs scripts with legacy Nashorn syntax/behavior and needs a low-change migration path | Runtime compatibility, `nashorn-core` and ASM dependencies, legacy JS syntax, Nashorn-specific APIs whose packages changed |
| **GraalJS / GraalVM JavaScript** | Application needs modern JavaScript or a polyglot ecosystem with explicitly configured host access | Must pick the right libraries, versions, and JSR-223 adapter if still using `ScriptEngine`; API/polyglot security differs from Nashorn |
| **Rhino or another JSR-223 engine** | System has specific compatibility/footprint constraints | Whether it actually supplies `ScriptEngineFactory` in the version used; level of ECMAScript and Java interop support |

**There is no “new official JavaScript engine” that automatically replaces Nashorn across all JDKs**. The choice is an application decision: check licenses, security patch cadence, script compatibility, trustworthiness, ability to run on the current JDK, and deployment packaging.

For projects with many legacy Nashorn scripts, standalone Nashorn can serve as a transitional step. For new projects, evaluate an actively maintained engine and the required ECMAScript level, including potentially using a dedicated polyglot API rather than forcing every use case through JSR-223.

## 5. Example 2 — Adding Real Standalone Nashorn with Maven

The OpenJDK project publishes the Maven artifact **`org.openjdk.nashorn:nashorn-core`**, which is separate from the Nashorn module formerly shipped inside the JDK. At the time of writing, the version cross-referenced from the OpenJDK project and Maven Central is **`15.7`**. The version in this example is **explicitly pinned** for reproducible builds; in production, monitor releases and test upgrades according to your project's dependency process.

### 5.1. Project Structure

~~~text
embedded-js/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EmbeddedJs.java
~~~

### 5.2. Complete pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>training.demo</groupId>
    <artifactId>embedded-js</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.openjdk.nashorn</groupId>
            <artifactId>nashorn-core</artifactId>
            <version>15.7</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Why not just download `nashorn-core.jar` and drop a single file onto the classpath? The Nashorn artifact depends on **ASM libraries** for bytecode processing/generation; Maven resolves those transitive dependencies automatically. Bringing only one JAR manually easily leads to `NoClassDefFoundError` or initialization failures. Maven/Gradle packages the entire inspectable dependency graph.

### 5.3. Complete Java File

`src/main/java/demo/EmbeddedJs.java`:

~~~java
package demo;

import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class EmbeddedJs {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("nashorn");
        if (engine == null) {
            throw new IllegalStateException("Nashorn provider is missing");
        }
        System.out.println("nashornAvailable=" + (engine != null));
        Object result = engine.eval("function doubleIt(x) { return x * 2; } doubleIt(21);");
        System.out.println("result=" + ((Number) result).intValue());
    }
}
~~~

**Design explanation:**

- The Java code imports only the **standard `javax.script` API**. By not hard-coding Nashorn internal classes, this Java adapter is easier to swap engines later.
- The Maven dependency brings a `ScriptEngineFactory` implementation into the runtime. `ScriptEngineManager` looks up the name `nashorn` and obtains a `ScriptEngine`.
- If the provider is missing, `IllegalStateException` reports the missing engine immediately at the configuration point instead of causing a null failure later.
- A simple JavaScript script was chosen to run on Nashorn (it does not require modern ECMAScript syntax).
- `eval` returns `Object`. The example uses `Number.intValue()` rather than casting directly to `Integer` to avoid assuming a specific wrapper type.
- This is a **verified script-embedding example**, not a recipe for running JavaScript from untrusted users in production.

### 5.4. Running Maven with Java 17

From the `embedded-js` directory:

~~~bash
mvn -q -DskipTests compile
mvn -q exec:java '-Dexec.mainClass=demo.EmbeddedJs'
~~~

The second command lets Maven construct the runtime classpath including dependencies. In PowerShell, wrapping the entire `-Dexec.mainClass=...` argument in single quotes also prevents shell argument-splitting issues.

Program stdout after Maven launches the application:

~~~text
nashornAvailable=true
result=42
~~~

This example was **compiled and run on Amazon Corretto JDK 17.0.15** with the `nashorn-core:15.7` dependency; the output above matches verbatim. Building requires Maven and artifact access (or dependencies already present in a local cache).

**If writing files with Windows PowerShell 5.1:** `Set-Content -Encoding UTF8` can prepend a UTF-8 BOM to `.java` files, causing `javac` to report an illegal BOM character. Use an IDE/editor that writes UTF-8 without BOM or an appropriate file-writing method; this encoding error **is unrelated to a missing JavaScript engine**.

### 5.5. Why Does the Standalone Build Need Separate Management?

Since Java 15, the JDK is no longer responsible for guaranteeing Nashorn versions, ASM dependencies, or updates. Therefore, operations teams must:

1. Declare the dependency at both build time and runtime, not compile time only.
2. Pin versions, track SBOMs, licenses, and patch-monitoring workflows.
3. Test on the exact JDK/JRE deployed in production; do not infer from `java -version` that an engine will exist.
4. Package all transitive dependencies in the container, fat JAR, or respective distribution.
5. If using JPMS/module path, handle module resolution and ASM dependencies alongside Nashorn's module properly.

## 6. Putting the Engine on the Classpath or Module Path in JPMS?

### 6.1. Applications on the Classpath

The Maven example above is an application running on the classpath. `ScriptEngineManager` uses the service provider mechanism to find `ScriptEngineFactory` implementations visible to the relevant class loader. The runtime classpath built by the Maven plugin includes `nashorn-core` and its transitive dependencies, so provider discovery succeeds.

Do not merely check whether a JAR exists on disk. The existence of a JAR file on disk **is different** from the class loader used for script engine lookup actually seeing the JAR and its service metadata.

If a container system has multiple class loaders, `new ScriptEngineManager()` defaults to the **thread context class loader** to discover factories. When a unit test passes yet an app server/plugin host reports a missing engine, check the context loader, the provider's loader, and the module graph. The `new ScriptEngineManager(ClassLoader)` API lets you supply a specific loader for discovery when appropriate.

### 6.2. Explicit Named Module Applications

A consumer module using `javax.script` declares:

~~~java
module embedded.host {
    requires java.scripting;
}
~~~

This is an **illustrative `module-info.java`**. If the engine module and ASM modules are placed on the module path, they must **be resolved** and the service provider must be visible in the graph. Standalone Nashorn's JPMS module name is **`org.openjdk.nashorn`** (different from the legacy module `jdk.scripting.nashorn`).

According to OpenJDK project guidance, place standalone Nashorn and **its transitive dependencies** on the module path or an appropriate `ModuleLayer`. Depending on launcher configuration, you may need to include the engine module in the root modules list or use appropriate service binding. Illustrative command pattern when distributing on the module path:

~~~bash
java --module-path libs --add-modules org.openjdk.nashorn -m embedded.host/demo.EmbeddedJs
~~~

**This is a command pattern dependent on packaging, not a command run for the Maven classpath project in section 5**: `libs` must contain Nashorn's module/JAR and its dependencies, and `embedded.host` must actually be compiled as a named module on the module path. Do not copy that command onto the classpath project above expecting it to run immediately. The universal method is checking resolved modules, provider factories, and running integration tests in the exact packaged environment.

In a custom runtime image built with `jlink`, the `java.scripting` API must be retained if the host uses it, and the engine plus its dependent modules must be in the image or distributed appropriately. Do not assume `jlink` automatically pulls a scripting engine into the image just because `java.scripting` is included.

### 6.3. Using ScriptEngineFactory in a Plugin System

An engine provider may live in a plugin loader rather than the host's class loader. If the host calls:

~~~java
new ScriptEngineManager().getEngineByName("nashorn");
~~~

yet the context loader cannot see the provider, the result may still be `null`. Changing aliases repeatedly will not fix a visibility issue. How to diagnose:

- Inspect `Thread.currentThread().getContextClassLoader()`.
- List `getEngineFactories()` on a manager using the intended loader.
- Verify provider modules are resolved and no dependencies are missing.
- If the host and engine communicate via interfaces, confirm both share the **same type identity** for `javax.script.ScriptEngineFactory` and SPI types.
- Do not let plugins arbitrarily pick class loaders or execute scripts with host privileges without a trust policy.

## 7. Migrating Applications Using Nashorn-Specific APIs

Reuse `javax.script` as much as possible, but switching engines is more than changing one dependency name.

| Legacy Code Pattern | Issue After JDK 15 | Resolution |
| --- | --- | --- |
| `getEngineByName("nashorn")` assuming an engine always exists | Returns null if no provider is present | Add runtime dependency; verify factory name and fail-fast |
| Importing `jdk.nashorn.api.scripting.*` | JDK's Nashorn-specific API was removed | If using standalone Nashorn, check API migration to `org.openjdk.nashorn.api.scripting`; if changing engines, design a new adapter |
| Using the `jjs` tool to run scripts/builds | `jjs` was removed | Write a custom launcher using the chosen engine or use the new vendor's CLI tool |
| Using `Java.type`, `Java.extend`, `Packages`, or custom Java bridges | Compatibility and host interop controls differ by engine | Audit actual scripts, refactor bridges, configure host access explicitly |
| Using overly modern JavaScript syntax | Standalone Nashorn does not necessarily support all modern ECMAScript | Define a dialect/feature matrix, test every script, or pick a suitable JS runtime |
| Relying on specific `ScriptEngine.eval` return types | Number/object/mapping types may differ across engines | Use an explicit data-conversion contract; avoid blind casting |
| Using custom Nashorn-specific sandbox/filters | Replacement engines have different access-control models | Review security policy from scratch; never assume old settings are equivalent |
| Running scripts across threads on one engine | `ScriptEngine` is not thread-safe by default | Check `ScriptEngineFactory.getParameter("THREADING")` and manage instances/state |

A `javax.script`-compatible API only gives the host a **shared Java contract**. It **does not guarantee** two engines behave identically on JS syntax, value types, Java interoperability, object lifecycle, security policy, encoding, locale/timezone, Promises/async, or serialization results.

### 7.1. Do Not Mask Errors with a Silent Fallback

An anti-pattern to avoid:

~~~java
ScriptEngine engine = manager.getEngineByName("nashorn");
if (engine == null) {
    engine = manager.getEngineByName("JavaScript");
}
// Does not verify which engine was chosen or whether it is compatible.
~~~

This is an **illustrative snippet of a risky practice**, not a standalone runnable program. If the second alias resolves to an engine with semantic differences, business results can silently go wrong without raising an error.

It is better to define an explicit policy: “only support standalone Nashorn 15.7” or “support verified GraalJS version X”, then inspect `getEngineFactories()`, engine name/version, and run a smoke test before accepting requests.

### 7.2. When Using GraalJS

GraalJS has a **JSR-223** adapter distributed separately. Simply installing a GraalVM-branded JDK does not guarantee `ScriptEngineManager.getEngineByName("JavaScript")` works out of the box across every product generation: newer GraalVM releases require adding **`js-scriptengine`** separately when using the adapter. For new applications, GraalJS documentation recommends considering the **`org.graalvm.polyglot.Context`** API for finer control over access permissions and lifecycle. Do not copy Nashorn interop/sandbox configurations onto GraalJS without verifying the new semantics.

## 8. Managing Bindings, State, and Lifecycle When Embedding Scripts

Testing should not stop at “the engine was found and computed `21 * 2`”. When scripts are embedded in a real host, consider:

- **Bindings:** `ScriptEngine` has `ENGINE_SCOPE`/`GLOBAL_SCOPE`; values inserted become visible to the script. `manager.put(...)` sets global scope on the manager for engines it creates. Do not put secrets or high-privilege objects into global bindings casually.
- **Session isolation:** each request/tenant should have separate context/bindings if scripts are permitted to mutate variables. Reuse engines only after understanding the implementation's thread-safety and state-isolation contract.
- **Ownership:** if an engine/factory creates threads, contexts, caches, or native resources, the host must design cleanup per the vendor's actual API. `javax.script.ScriptEngine` has no standard `close()` method.
- **Timeout/cancellation:** `ScriptEngine.eval` does not guarantee a timeout or safe stop mechanism across all engines. Do not rely on `Future.cancel(true)` to reliably abort an infinite-loop script. Choose a runtime/architecture with proper resource limits, or isolate in a separate process if running untrusted code.
- **Exceptions:** `eval` can throw `ScriptException` for syntax/runtime evaluation errors; provider configuration errors usually surface earlier during discovery/initialization. Log **engine missing**, **script failure**, and **resource exhaustion** separately.
- **Results:** the interface returns `Object`; apply explicit value conversion, checking `null`, numeric ranges, encoding, and JSON when data crosses system boundaries.

Example of single-evaluation bindings (illustrative snippet for code that already has `engine`):

~~~java
javax.script.Bindings vars = engine.createBindings();
vars.put("base", 10);
Object result = engine.eval("base + 5", vars);
~~~

Do not share the same mutable `Bindings` across multiple users/tenants. For data and host objects exposed to scripts, ensure only the exact needed capabilities are provided. Script-variable injection **is not** a dependency-injection container and does not automatically isolate dangerous Java objects.

## 9. Security: Do Not Treat Nashorn or JSR-223 as a Sandbox

Running embedded JavaScript **inside the same JVM** can lead to access to objects and capabilities provided by the host. Java interop features of legacy engines can let scripts call Java APIs the application did not anticipate unless blocked by configuration. An engine being removed from the JDK is a dependency/migration issue, **not** a reason to skip security reviews.

For untrusted scripts:

1. **Do not directly execute arbitrary user-supplied script code** inside a JVM handling sensitive business privileges without a threat model, host access policy, and proven runtime limits.
2. Restrict or disable Java host interop according to the chosen engine's capabilities; do not assume a generic `javax.script` setup suffices to lock down an engine.
3. Limit CPU, memory, time, I/O, network, and job count; these limits usually require mechanisms outside `ScriptEngine`.
4. If sharing a process, drop OS privileges of the process and avoid putting credentials/secrets/handles into bindings.
5. For low trust, consider running scripts in an **isolated process/container** with quotas, communicating over IPC/API and accepting the isolation overhead.
6. Keep the engine and ASM/transitive libraries updated via dependency security processes; patching the Java runtime does not guarantee standalone Nashorn is on a secure version.

Even for internal automation with trusted scripts, apply code review, script allowlists, logging, versioning, and resource limits. Running via JSR-223 does not create a “safe zone” merely by switching languages.

## 10. Diagnostic Checklist When Upgrading Java 8/11 to 17+

If a system hits `NullPointerException` at `engine.eval(...)` or logs “Nashorn not found”, check in order:

| Step | What to Observe | Correct Fix |
| --- | --- | --- |
| 1. Java version | Actual process `java -version` | Determine if running Java 15+ and whether it is a minimized image |
| 2. API presence | `java.scripting` module; does `javax.script` code compile | If using a custom `jlink` image, include the required API in the runtime |
| 3. Factory discovery | `new ScriptEngineManager().getEngineFactories()` | If no factory exists, inspect dependencies/class loader/module graph |
| 4. Engine names | `factory.getNames()`, `getEngineName()`, `getEngineVersion()` | Use names the vendor actually advertises; avoid guessing aliases |
| 5. Runtime dependency | Maven dependency tree, packaged JAR, ASM transitives | Ensure the engine **exists at runtime**, not just compile/test time |
| 6. Class loader | TCCL, web container/plugin loader, `ScriptEngineManager(loader)` | Ensure provider metadata is visible from the discovery loader |
| 7. JPMS resolution | module path, service provider module, parent/child layer | Resolve the engine module properly, rather than merely copying the JAR into a directory |
| 8. Script compatibility | syntax, native objects, JS–Java APIs, return values | Run regression suite against the exact pinned engine version |
| 9. Trust and limits | Host access, bindings, concurrency, timeout, data isolation | Design sandboxing/process isolation and lifecycle at the proper level |
| 10. Deployment parity | CI, container, IDE, staging, production | Run engine discovery/eval smoke tests in the final target environment |

In particular, an IDE may put the engine library on the classpath during tests while the production fat JAR/container omits it due to packaging configuration. Every deployment path must run the same integration tests.

### 10.1. What Should a Smoke Test Do?

A meaningful smoke test must verify:

- The desired factory **is discovered**, with name/version inside the approved list.
- `getEngineByName(...)` returns non-null.
- A small script using the actual system's syntax and interop API **executes successfully**.
- Data conversion results (number/string/list/JSON) are correct, not merely exception-free.
- The **engine absent** case fails fast with a clear message.
- Core scripts have regression tests when upgrading JVM/engine versions.
- Failing scripts and long-running scripts are handled according to resource/lifecycle policies.

The smoke test in section 5 prints `nashornAvailable=true` and `result=42`; that test proves Maven packaging delivered the engine to runtime, **not** that all business scripts or security settings are automatically compatible.

### 10.2. Common Errors and How to Distinguish Them

**`getEngineByName(...) == null`:** no factory found for the alias. Check runtime dependencies, class loader, module resolution, and `factory.getNames()`. Do not call `eval` on null.

**`ClassNotFoundException` or `NoClassDefFoundError`:** engine library/transitive dependency is missing from the runtime path or hit a loading conflict. Inspect the Maven dependency tree and packaging, not just `requires java.scripting`.

**`ScriptException`:** the engine was created, but the script has a syntax/evaluation error. Inspect engine dialect, script, bindings, and exception details; do not misattribute it to JEP 372.

**`IllegalAccessException` / `InaccessibleObjectException`:** script or engine attempted reflective access to Java APIs blocked by JPMS encapsulation. Do not blindly apply `--add-opens=ALL-UNNAMED`; open only the exact package/target after evaluating risks and choosing an appropriate engine.

**`ClassCastException` after `eval`:** the returned Java wrapper/vendor object does not have the type the code expected. Check `result.getClass()` and convert per an explicit contract.

**Unable to invoke `jjs`:** the tool left the JDK. This is a different failure from `ScriptEngineManager` not finding an engine; replace CLI/build workflows that still invoke `jjs`.

## 11. Recommended Migration Path for Existing Embedded Applications

Low-risk roadmap:

1. **Inventory** all uses of `ScriptEngineManager`, `ScriptEngine`, `Invocable`, `Compilable`, `jjs`, and `jdk.nashorn.*` APIs; list executed scripts and exchanged data types.
2. **Select an engine** based on compatibility and trust requirements. If using standalone Nashorn, declare the dependency as in section 5; if migrating to GraalJS/Rhino, build a feature matrix and replace host-interop adapters.
3. **Isolate behind an adapter layer** responsible for engine creation, reading factory metadata, fail-fast checks, value conversion, context/bindings management, lifecycle, and error reporting. Do not scatter `new ScriptEngineManager()` and guessed provider names throughout business code.
4. **Pin and test versions** of the engine/dependencies alongside the target JDK (e.g., Java 17); use the corresponding compiler release target.
5. **Test real scripts**: syntax, Unicode, number handling, exceptions, async/timers, Java bridges, reflection, host objects, and serialization.
6. **Configure deployment**: Maven dependency graph, fat JAR/container image, class loader visibility, module path/layers, and `jlink` runtime if applicable.
7. **Test failure paths** when the engine is missing or unresolved; the outcome must be an intelligible configuration error, not an NPE inside business logic.
8. **Review security** before opening scripts to users/tenants or allowing Java bridges. Set resource limits and input/output policies.
9. **Release with observability**: log engine name/version, `ScriptException` rates, script execution times/resource metrics, and keep a rollback plan if a new engine version changes behavior.

Removing Nashorn in JDK 15 is a **platform-responsibility packaging** change: script-embedding applications must explicitly own their dependencies and policies rather than relying on an implicit implementation inside the JDK.

## 12. Quick Summary

~~~text
JDK 8–14:
    java.scripting / javax.script API  +  Nashorn bundled (JDK)
                                            |
                                            +-- getEngineByName("nashorn") usually returns an engine

JDK 15+:
    java.scripting / javax.script API  +  NO bundled Nashorn
                                            |
                                            +-- getEngineByName("nashorn") may be null
                                            |
                                            +-- supply an independent engine at runtime
                                                    |
                                                    +-- Nashorn standalone
                                                    +-- GraalJS adapter
                                                    +-- Rhino / another provider
                                                    |
                                                    +-- test discovery, eval, packaging
~~~

**Closing rule:** from Java 15 onward, **to embed JavaScript an application must ensure a suitable engine implementation is present at runtime**. `javax.script` still exists as an SPI; `ScriptEngineManager` can **locate** a registered engine, but **is not the engine itself**. Declare the dependency, verify visibility and version, fail-fast if missing, test real scripts, and safely manage data/host access.

### Reference Documentation

- [JEP 372 – Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): removal scope and confirmation that the `javax.script` API is unaffected.
- [JEP 335 – Deprecate the Nashorn JavaScript Engine](https://openjdk.org/jeps/335): deprecation-for-removal phase starting in Java 11.
- [Java SE 17 – ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): service-provider discovery, factory names, `getEngineByName`, and missing-engine behavior.
- [OpenJDK Nashorn standalone](https://github.com/openjdk/nashorn): standalone module, dependency graph, Java 11+, and JPMS running instructions.
- [Maven Central – nashorn-core](https://central.sonatype.com/artifact/org.openjdk.nashorn/nashorn-core): dependency coordinates and version 15.7 used in the example.
- [GraalVM JavaScript embedding / ScriptEngine](https://www.graalvm.org/jdk17/reference-manual/js/RhinoMigrationGuide/): migration guide and JSR-223 adapter.
