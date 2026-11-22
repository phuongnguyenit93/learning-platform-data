# 17.7. Nashorn Has Been Removed from the JDK: Explicitly Declare an External Engine When Building Examples

## Learning Objectives

After this lesson, you can:

1. Identify the exact milestone when **Nashorn was deprecated for removal in JDK 11 and removed from the JDK starting in JDK 15**, while the standard `javax.script` API / `java.scripting` module **was not removed** by that decision.
2. Understand why `new ScriptEngineManager().getEngineByName("JavaScript")` or `getEngineByName("nashorn")` **can return `null` on Java 17+** and why being able to run the JVM does not prove a JavaScript engine is present.
3. Distinguish between the **JSR 223 API** and **a specific engine implementation**; describe the `ScriptEngineFactory`, `ServiceLoader`, alias name, class loader, and module path mechanisms.
4. Write a Java 17+ example with an **explicitly declared dependency**: `org.openjdk.nashorn:nashorn-core:15.7`, without pretending it is a default component of JDK 17.
5. Run the same program with and without an external engine; check the `engine == null` condition, pass `Bindings`, and call `eval` and `Invocable` properly.
6. Recognize other options such as **GraalJS** (an external dependency, which can use `ScriptEngine` or `org.graalvm.polyglot.Context`) and syntax/API compatibility limits when switching engines.
7. Design examples/tests suited to the deployment environment, module graph, and security issues when running untrusted scripts.

**Scope:** This topic is in chapter **17. Embedding Scenarios**, focusing on the ability to provide a **script engine** and how to declare dependencies for examples. Do not treat a modern JDK as an environment with a built-in JavaScript engine. The main illustrative example uses **Nashorn standalone outside the JDK**, not the removed built-in Nashorn.

## 1. Important Correction: The JDK's Nashorn Has Been Removed

Nashorn used to be a JavaScript engine bundled in the JDK, introduced in Java 8. It provided:
- an implementation of **`javax.script.ScriptEngine`** to run JavaScript;
- specific APIs belonging to `jdk.nashorn.api.scripting` and Nashorn packages;
- the `jjs` tool to run scripts from the command line.

History to remember:

| Java Version | Status of Nashorn Bundled in the JDK |
| --- | --- |
| JDK 8–10 | Built-in Nashorn in JDK builds that include this feature. |
| JDK 11–14 | Built-in Nashorn was **deprecated for removal** per JEP 335; using it meant depending on an engine about to disappear. |
| **JDK 15 onward** | **JEP 372 removed** the built-in engine, Nashorn-specific APIs, and `jjs` from the JDK. |
| Java 17+ | **Must not assume** Nashorn or a default JavaScript `ScriptEngine` is present; to run JavaScript, an appropriate engine must be provided externally. |

**JEP 372 did not remove `javax.script`.** JSR 223 is a general API for embedding **multiple scripting languages**, not just JavaScript. The `java.scripting` module and standard interfaces remain present in JDK/runtime images that contain that module; what was removed is the Nashorn implementation **shipped with the JDK**.

Diagram:

```text
Before JDK 15 (a JDK with built-in Nashorn):
  java.scripting / javax.script API
          |
          +-- ScriptEngineManager
                  |
                  +-- Nashorn JDK provider -> runs JavaScript

JDK 17+ without added engine:
  java.scripting / javax.script API
          |
          +-- ScriptEngineManager
                  |
                  +-- No JavaScript provider found -> returns null

JDK 17+ with external engine dependency:
  java.scripting / javax.script API
          |
          +-- ScriptEngineManager
                  |
                  +-- Standalone Nashorn / GraalJS provider -> runs script
```

Note: A **custom runtime image** created by `jlink` may even lack the `java.scripting` module itself. In that case, a program directly referencing `javax.script` may fail to start/load. This is a **different** state from "the API is present, but no JavaScript engine is found."

### 1.1. False Claims to Avoid in the Lesson

Wrong:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
Object result = engine.eval("1 + 2"); // Possible NullPointerException.
```

This is a **counterexample**, assuming `javax.script.*` is imported and executed inside a method that handles `ScriptException`. No JavaScript engine is declared or installed; the code can compile but fails at runtime because `engine == null`.

Wrong:
- "JDK 17 has Nashorn by default, no dependency needed."
- "`javax.script` still exists, so JavaScript will definitely run."
- "Just adding `requires java.scripting` gives you Nashorn."
- "Every ScriptEngine is a JavaScript engine."
- "Having the `java` command means the system has the `jjs` engine."

Right: **Explicitly declare the specific engine**, its version, how to place it on the runtime classpath/module path, how to look up the exact engine name, and how to handle a missing provider.

## 2. API and Implementation Are Two Separate Layers

JSR 223 resides in the `javax.script` package, belonging to the `java.scripting` module:

| Component | Role |
| --- | --- |
| `ScriptEngineManager` | Discovers factories, registers aliases, creates a ScriptEngine by name/extension/MIME type. |
| `ScriptEngineFactory` | Describes the engine name, aliases, language name/version, and how to instantiate the engine. |
| `ScriptEngine` | Common interface to `eval` source and work with `Bindings`/`ScriptContext`. |
| `Bindings` | Map of values from the Java host passed into the script scope. |
| `ScriptException` | Errors from evaluating a script or engine errors reported through JSR 223. |
| `Invocable` | Engine-optional capability for Java to invoke functions/methods defined by the script. |
| `Compilable` | Engine-optional capability to pre-compile a script, if supported by the provider. |
| `CompiledScript` | Representation of a compiled script per `Compilable`, reused when appropriate. |

**None of the classes in the table is a JavaScript engine implementation.** `ScriptEngineManager` does not interpret JavaScript syntax itself; it must find a `ScriptEngineFactory` that provides an implementation from the runtime.

### 2.1. How Is an Engine Found?

Creating a manager:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("nashorn");
```

This is an illustrative snippet inside a method with `javax.script.ScriptEngineManager` and `javax.script.ScriptEngine` imported.

According to the Java SE 17 API:
- `ScriptEngineManager` uses the **service provider mechanism** (based on `ServiceLoader`) to discover `ScriptEngineFactory` instances visible through the appropriate class loader.
- The no-arg constructor is equivalent to using the **thread context class loader** of the current thread. Therefore, class loaders in plugin/container applications affect discovery results.
- `getEngineByName(shortName)` matches the name against aliases declared by the factory and can return **`null` when no matching factory is found**.
- `getEngineByExtension("js")` and `getEngineByMimeType("application/javascript")` are alternative selection methods, but **can also be null**.
- `getEngineFactories()` returns the list of discovered factories, useful when debugging classpath/module path.

Do not assume the string `"JavaScript"` or `"js"` always points to the same implementation. When multiple providers exist, aliases may collide; choose an explicit provider name or configure/instantiate a specific factory if strict consistency is required.

### 2.2. Diagnosing Providers Before Evaluating Scripts

```java
ScriptEngineManager manager = new ScriptEngineManager();

for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName());
    System.out.println(factory.getEngineVersion());
    System.out.println(factory.getLanguageName());
    System.out.println(factory.getNames());
}

ScriptEngine engine = manager.getEngineByName("nashorn");
if (engine == null) {
    throw new IllegalStateException(
            "External Nashorn engine missing from runtime classpath/module path");
}
```

This is an **illustrative snippet** inside a method, requiring imports for `ScriptEngineFactory`, `ScriptEngineManager`, `ScriptEngine`. There is no fixed stdout for iterating over factories: the output depends on the **providers actually present in the process**, the JDK, dependencies, and class loader.

Finding a `ScriptEngineFactory` does not prove that the engine supports all JavaScript syntax, `Invocable`, `Compilable`, or the host interoperability policy the application needs. Actual features must be tested.

### 2.3. A Build-Time Maven Dependency Is Not Enough If Excluded at Runtime

Maven/Gradle can compile code using `javax.script` even without a provider. If the runtime artifact is omitted from the deployment package, `ScriptEngineManager` can return `null` again.

Check:
1. `pom.xml` or Gradle dependencies include the **engine artifact** (not just the API).
2. Maven scopes are not accidentally `test` or `provided` if production needs the engine.
3. The deployed artifact/runtime classpath actually includes the engine and its **transitive dependencies**.
4. If using the JPMS module path, the provider module is **resolved** in the module graph.
5. The thread context class loader can see the service provider, or the manager is created with a loader that can see the provider.
6. Run a small script on the **actual final runtime image/container**, not only in the IDE.

## 3. Option for Java 17+: Standalone Nashorn Outside the JDK

OpenJDK maintains **standalone Nashorn** at the `openjdk/nashorn` project. This is an **external library** usable on Java 11 onward and published via Maven Central.

The example in this lesson pins the dependency:

```xml
<dependency>
    <groupId>org.openjdk.nashorn</groupId>
    <artifactId>nashorn-core</artifactId>
    <version>15.7</version>
</dependency>
```

This is the **explicit dependency** used and tested in the example below. It does **not** turn Nashorn back into a built-in JDK 17 module; the application is responsible for packaging, updating, and checking the security/compatibility of this dependency.

### 3.1. Do Not Confuse the Standalone Package with the Old JDK

Built-in Nashorn before JDK 15 used packages such as `jdk.nashorn.api.scripting`. When code relies on Nashorn-specific APIs and migrates to standalone, the corresponding specific package uses the **`org.openjdk.nashorn.api.scripting`** namespace. If you only use `javax.script` for a basic example, you may not need to import any engine-specific package.

Using `javax.script` benefits design:
- part of the code can run with different providers;
- a missing engine can be detected via `null`;
- implementations can be swapped with fewer changes if the script uses compatible syntax.

However, **do not claim** that every Nashorn script will run unmodified on GraalJS or vice versa. Java host interop, global variables, proprietary APIs, ECMAScript support levels, and security defaults can differ.

### 3.2. Standalone Nashorn Is Not a Full Modern JavaScript Engine

Nashorn originated from ECMAScript 5.1 and supports some parts of ES6. If an example needs many newer ECMAScript features, evaluate **GraalJS** or another engine with a compatible version, rather than adding Nashorn and assuming it supports all modern syntax.

Standalone Nashorn is a useful option to **illustrate replacing a removed dependency**, especially when a legacy application already used Nashorn. It does not mean it is the best choice for a new JavaScript runtime requiring full modern ECMAScript.

### 3.3. JPMS and Transitive Dependencies

Standalone Nashorn is distributed as a **JPMS module**, with dependencies such as **ASM**. When running on the classpath via Maven, standard dependency management pulls in the required JARs. If you manually copy a single `nashorn-core-15.7.jar` file and omit the ASM libraries, the engine may fail class loading or not be discovered.

If using `--module-path`, ensure the Nashorn module and its dependencies are included and properly resolved. In some cases `--add-modules org.openjdk.nashorn` may be needed depending on how it is launched. Do not edit `module-info.java` with a module name that does not actually exist in the deployed image.

## 4. Runnable Example: One Java Class, Two Environments

Goal: Using **the same Java 17 file**, run:
- **Without an external JavaScript provider:** print `engine=UNAVAILABLE` and exit cleanly.
- **With Maven dependency `nashorn-core:15.7`:** find the provider, run simple JavaScript code, pass host data via `Bindings`, and call a script function via `Invocable`.

The example avoids Nashorn-specific JavaScript APIs to focus on JSR 223. This is **trusted demo code**, not accepting arbitrary user-submitted source.

### 4.1. Directory Structure

```text
external-script-engine-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ExternalEngineDemo.java
```

The Maven dependency uses the exact file name `ExternalEngineDemo.java` and public class `ExternalEngineDemo`.

### 4.2. Complete pom.xml File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>external-script-engine-demo</artifactId>
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
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>ExternalEngineDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Why declare explicitly?**
- `nashorn-core:15.7` is the **JavaScript provider outside the JDK**. Without it, the Java code in the next section still compiles, but does not automatically have the Nashorn engine on JDK 17+.
- `maven.compiler.release=17` sets the Java 17 language/platform target for the host program.
- Maven compiler and exec plugins pin versions to avoid ambiguous reliance on build environment defaults.
- Maven resolves `nashorn-core` dependencies per the POM, instead of requiring manual copying of each ASM JAR.

This configuration was verified with Maven 3.9.x and OpenJDK 24 when compiling with target `--release 17`. In environments without Maven or where Maven Central is blocked, artifacts must be supplied via a trusted internal repository with checksums and usage permissions checked according to organizational policy.

### 4.3. Complete ExternalEngineDemo.java File

```java
import javax.script.Bindings;
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class ExternalEngineDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("nashorn");
        if (engine == null) {
            System.out.println("engine=UNAVAILABLE");
            return;
        }

        System.out.println("engine=AVAILABLE");
        Bindings bindings = engine.createBindings();
        bindings.put("name", "Java");
        System.out.println("greeting=" + engine.eval("'Hello, ' + name", bindings));
        System.out.println("answer=" + ((Number) engine.eval("6 * 7")).intValue());

        if (!(engine instanceof Invocable invocable)) {
            throw new IllegalStateException("Invocable not supported");
        }
        engine.eval("function add(a,b) { return a + b; }");
        System.out.println("add="
                + ((Number) invocable.invokeFunction("add", 2, 3)).intValue());
    }
}
```

**Step-by-step explanation:**

1. `new ScriptEngineManager()` searches for script-engine factories visible to the thread's context class loader.
2. `getEngineByName("nashorn")` requests a provider with the `nashorn` alias; if missing, `null` is the normal result. The code **does not call `eval` on `null`**.
3. If the engine is available, `Bindings` holds the key `"name"` and value `"Java"` for the script to reference. String concatenation `'Hello, ' + name` produces `"Hello, Java"`.
4. `eval("6 * 7")` returns an `Object`; the numeric result is handled via the `Number` interface and `intValue()`, avoiding assumptions about the exact wrapper class of every JavaScript engine.
5. `Invocable` is an engine-optional capability. The code checks `instanceof` before calling `invokeFunction`.
6. The script function `add(a,b)` is defined via `engine.eval`, then Java invokes it via `invocable.invokeFunction("add",2,3)`. The result `5` is displayed.

**Intentional limitation:** `main throws Exception` keeps the demo concise. In production, catch `ScriptException`, `NoSuchMethodException`, provider/discovery errors, and data contract errors specifically, and translate them into appropriate domain errors. The code does not use `org.openjdk.nashorn.*` directly, so the Java host part compiles only against standard `java.scripting`; the engine implementation is added at runtime by Maven.

### 4.4. Running Without an External Engine

To observe "JDK 17+ does not include Nashorn by itself," run **only with the compiled class**, without placing engine dependencies on the classpath:

```bash
javac --release 17 ExternalEngineDemo.java
java -cp . ExternalEngineDemo
```

With a clean JDK having no other JavaScript provider, **stdout**:

```text
engine=UNAVAILABLE
```

This result was verified on JDK 24 when running only the Java host class, with no external JSR 223 engine on the classpath.

**Do not use this output to claim that every JDK 17+ returns null for all engine names:** an application that declares GraalJS, standalone Nashorn, or another provider can still discover an engine. What is true is that **JDK 17+ itself does not bundle Nashorn by default**, and `getEngineByName` must be treated as a lookup that can fail.

### 4.5. Running With an Explicit Nashorn Dependency

From the directory containing `pom.xml` and `src/main/java/ExternalEngineDemo.java`:

```bash
mvn -B -q -DskipTests compile exec:java
```

**Stdout printed by the program (verified):**

```text
engine=AVAILABLE
greeting=Hello, Java
answer=42
add=5
```

In some environments Maven may print logs, warnings, or build information to the terminal; the block above shows **the lines printed by the demo**, not a promise that the entire console output of the Maven tool is exactly four lines.

This demonstrates that **the exact same Java host code**, simply by changing how **the provider is packaged**, can:
- safely return `UNAVAILABLE` when the engine is missing;
- or find the external engine and evaluate JavaScript when the provider is fully distributed.

### 4.6. Why Not Call the Nashorn Factory Directly in the Demo?

You could use an engine-specific class like `org.openjdk.nashorn.api.scripting.NashornScriptEngineFactory` for tighter control over the implementation, but doing so creates a **compile-time dependency** on Nashorn. This lesson keeps the host code on `javax.script` to emphasize the SPI mechanism and missing-provider failure, while the POM defines the actual engine.

If a production service **must** use the exact specific Nashorn implementation, add a step to validate `engine.getFactory()` (name, version, factory class, provider origin) or instantiate the factory directly with a pinned dependency. Relying only on the generic `"JavaScript"` alias when multiple providers exist is not reliable enough.

## 5. How to Identify the Actual Engine at Deployment

If the demo runs in the IDE but deployment returns `null`, inspect the parameters **of the deployed process itself**:

```java
ScriptEngineManager manager = new ScriptEngineManager();
System.out.println("engineFactories=" + manager.getEngineFactories().size());
for (ScriptEngineFactory f : manager.getEngineFactories()) {
    System.out.println("engine=" + f.getEngineName());
    System.out.println("aliases=" + f.getNames());
    System.out.println("language=" + f.getLanguageName());
}
```

This is an illustrative snippet with the required `javax.script` imports, **with no fixed stdout**. `getEngineFactories()` is for debugging providers, not a way to count how many script languages the JVM is required to support.

Check the layers:

| Layer | Question | Common Mistake |
| --- | --- | --- |
| Dependency | Is the engine artifact declared with the right group/version? | Only `java.scripting` API or an interface artifact is present. |
| Dependency scope | Does the artifact make it into the actual runtime? | `test`/`provided` scope excluded from production. |
| Transitive libraries | Are the related ASM/JARs packaged? | Only copying a single Nashorn jar while dependencies are missing. |
| Classpath | Is the provider JAR on the classpath of the running process? | IDE classpath differs from executable jar/container. |
| Module path | Is the provider module in the resolved graph? | Module JAR is on the path but not resolved. |
| Class loader | Which context loader is the manager using? | App-server/plugin loader differs from the loader holding the engine. |
| Alias | Does the factory's `getNames()` include `"nashorn"`? | Using a name not registered by the provider or an alias that changed. |
| Engine API | Does the engine support `Invocable`, `Compilable`? | Casting directly causes `ClassCastException`. |
| Runtime capability | Does the engine support actual syntax/interop? | Nashorn-specific scripts fail on another engine. |
| JVM image | Is `java.scripting` packaged and resolved? | Custom `jlink` image lacks the API, causing module/class loading errors. |

**Pitfall:** `ScriptEngineManager.getEngineByName("JavaScript")` can succeed thanks to **another engine**, not Nashorn. If a lesson intends to demonstrate standalone Nashorn, keep `"nashorn"` and the `nashorn-core` dependency; do not change the alias and then call every JavaScript engine "Nashorn."

### 5.1. Recognizing the java.scripting Module

`ScriptEngineManager` is an API in the `java.scripting` module, not `java.base`. For a **named module** using `javax.script`, the minimal module descriptor can declare:

```java
module example.script.host {
    requires java.scripting;
}
```

This is an **illustrative `module-info.java` file**, not part of the Maven project running on the classpath in section 4. If the runtime image lacks `java.scripting`, a named module with `requires java.scripting` may **fail to start** due to module resolution failure. Adding the standalone Nashorn dependency cannot substitute for packaging the required **API module**.

If placing the provider on the **module path**, ensure the JSR 223 service provider is actually resolved or properly configured. For standalone Nashorn, the OpenJDK project notes that the provider and ASM dependencies must be on the module path/module layer or configured appropriately. Do not conclude "Maven downloaded the jar" is sufficient in every JPMS deployment.

### 5.2. Class Loaders in Containers and Plugin Systems

`ScriptEngineManager()` uses the thread context class loader. When an application runs inside a framework or app server:
- a plugin may use a child loader containing the engine;
- a request thread may have a context loader that only sees host classes;
- a manager created before the engine is loaded may have discovered a different set of factories.

You can create the manager with an explicit loader:

```java
ClassLoader loader = plugin.getClass().getClassLoader();
ScriptEngineManager manager = new ScriptEngineManager(loader);
```

This is an **illustrative snippet** with a framework `plugin` variable; it is not a standalone program. Ensure the loader actually has visibility to `ScriptEngineFactory` and its dependencies. Avoid arbitrarily mutating the thread pool's global context class loader for every request; use an appropriate loader lifecycle and cleanup pattern.

### 5.3. Do Not Use `registerEngineName` to "Create" an Engine Out of Thin Air

`ScriptEngineManager.registerEngineName(name, factory)` can register **an existing factory** under a desired name. It does not download a JavaScript engine or automatically add a compiler/runtime implementation. If there is no valid `ScriptEngineFactory`, there is nothing to register.

## 6. GraalJS: Another External Option, Requiring Its Own Declaration

If a project needs more modern JavaScript or tighter control over host access, consider **GraalJS**. In modern GraalVM releases, do not assume a `ScriptEngine` is bundled in the distribution: **GraalJS ScriptEngine must also be added as a separate dependency**, and has specific Java/GraalVM compatibility requirements.

For the JSR 223 approach, GraalJS documentation describes:
- provider JAR **`org.graalvm.js:js-scriptengine`**;
- language implementation/dependencies via **`org.graalvm.polyglot:js`** or the corresponding artifact, managed under the same version set;
- commonly using the alias **`"graal.js"`**.

A Maven example for a project that has confirmed **JDK/GraalJS version compatibility** can use the specific coordinates below:

```xml
<dependency>
    <groupId>org.graalvm.js</groupId>
    <artifactId>js-scriptengine</artifactId>
    <version>25.0.3</version>
</dependency>
<dependency>
    <groupId>org.graalvm.polyglot</groupId>
    <artifactId>js</artifactId>
    <version>25.0.3</version>
    <type>pom</type>
</dependency>
```

This is an **example configuration for an alternative option**, **not** the POM of the Java 17 program run in section 4. For modern GraalJS lines, you must verify **supported JDKs** (current documentation targets newer JDKs), exact dependencies, license policies, and synchronized versions before use; do not claim GraalJS 25.x in this configuration runs on every JDK 17.

Using GraalJS via JSR 223:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("graal.js");
if (engine == null) {
    throw new IllegalStateException("GraalJS ScriptEngine provider missing");
}
```

This is an illustrative snippet with `javax.script` imports. It **does not work on its own** when the provider/language runtime dependency is missing. If you need to customize Java host interoperability permissions and isolation, GraalVM documentation **recommends `org.graalvm.polyglot.Context`** rather than treating legacy `ScriptEngine` as the preferred API for new projects.

### 6.1. Migration Does Not Mean Replacing the Engine Name String

Do not replace:

```java
manager.getEngineByName("nashorn");
```

with:

```java
manager.getEngineByName("graal.js");
```

and assume all old scripts have the same behavior. A migration checklist needs to evaluate:
- Supported ECMAScript version and syntax.
- How JavaScript sees Java objects/classes and `Java.type`/host access policy.
- Data returned from `eval`: `Number`, boolean, strings, collections, and polyglot values may differ.
- Nashorn-specific globals and packages/APIs such as `Java.extend`, `Java.to`, `Java.from`, object mirroring, or class filters.
- Thread-safety, concurrency, and how engines/contexts are created.
- Sandbox, filesystem/network access, dependencies, and runtime packaging.

If you only need to **read JSON**, use a reliable Java JSON parser instead of spinning up a full JavaScript engine; JSON and JavaScript execution are two different needs.

## 7. Error Handling: Distinguish Missing Provider from Script Errors

There are at least four distinct error classes.

| Phase | Example | How to Handle |
| --- | --- | --- |
| Discovery | `manager.getEngineByName("nashorn") == null` | Report missing dependency/provider clearly, do not `eval` |
| Provider loading | Missing transitive JAR, module/class loading error, `ServiceConfigurationError` | Check packaging/loader/module graph, do not fix by changing script |
| Script evaluation | Invalid script syntax, runtime error from script | Catch `ScriptException`, log location/line/source appropriately |
| Host/script function invocation | Function does not exist or `Invocable` not supported | Check capability, handle `NoSuchMethodException`/`ScriptException` |

### 7.1. A Simple and Clear API Boundary

```java
static Object evaluateConfiguredScript(String source)
        throws javax.script.ScriptException {
    ScriptEngine engine = new ScriptEngineManager()
            .getEngineByName("nashorn");
    if (engine == null) {
        throw new IllegalStateException(
                "Nashorn provider unavailable: add nashorn-core at runtime");
    }
    return engine.eval(source);
}
```

This is an **illustrative method**, placed in a class with `javax.script.ScriptEngine`, `javax.script.ScriptEngineManager` imported. It classifies:
- `IllegalStateException`: deployment/capability error (no provider);
- `ScriptException`: an engine is present, but evaluating the script reported an error.

**Do not pass untrusted source** into this method without proper architectural isolation. The pattern only illustrates error separation, not a safe API for remote code execution.

### 7.2. ScriptException Contains Source Location

```java
try {
    engine.eval("function (");
} catch (ScriptException ex) {
    System.err.println("script failed: " + ex.getMessage());
    System.err.println("line: " + ex.getLineNumber());
    System.err.println("column: " + ex.getColumnNumber());
}
```

This is an illustrative snippet inside a method with a non-null `engine` variable. `getLineNumber()`/`getColumnNumber()` may not know the location; do not assume every provider supplies full details. Do not log user source verbatim if the source contains secrets; logging systems should attach a script ID/correlation ID and redaction.

### 7.3. Do Not Swallow ServiceConfigurationError

If service provider metadata is corrupted or a class is missing, `ServiceConfigurationError`/`LinkageError` can occur during loading. A manager may fail to discover the provider, and Java logs may indicate why. Do not always lump **every Throwable** into "no script engine"; that hides broken packaging and serious `Error`s. Log the cause reasonably, and fail-fast if this is a required capability.

## 8. Important APIs When Embedding Scripts

### 8.1. Bindings and ScriptContext

`Bindings` is a map from variable names to Java objects that the engine can see according to its rules:

```java
Bindings input = engine.createBindings();
input.put("name", "Java");
Object value = engine.eval("'Hello, ' + name", input);
```

This is an illustrative snippet with an existing `engine`. Avoid using user data to concatenate code strings like:

```java
String script = "lookup('" + userInput + "')";
engine.eval(script);
```

This is a **counterexample** if `userInput` is untrusted data: it can lead to script injection. Use `Bindings` or an interface with explicit parameters instead of concatenating source code whenever possible; host object access must still be controlled because a script can call methods on exposed objects.

### 8.2. Invocable Is Optional

```java
if (engine instanceof Invocable invocable) {
    engine.eval("function add(a,b) { return a+b; }");
    Object sum = invocable.invokeFunction("add", 2, 3);
}
```

`Invocable` is not guaranteed by every engine. If the script does not define the function `add`, invocation can throw `NoSuchMethodException`. Do not trigger `ClassCastException` by casting directly `(Invocable) engine` and assuming JSR 223 requires every provider to support it.

### 8.3. Compilable Is Optional

```java
if (engine instanceof Compilable compilable) {
    CompiledScript compiled = compilable.compile("6 * 7");
    Object value = compiled.eval();
}
```

This is an illustrative snippet requiring `javax.script.Compilable`, `CompiledScript` imports and `ScriptException` handling. When evaluating the same script many times, some engines can benefit from pre-compilation. However:
- not all providers implement `Compilable`;
- caching compiled scripts must match the engine/context lifecycle;
- **do not share a script engine across multiple threads** unless factory/provider documentation confirms safe semantics.

### 8.4. Thread Safety Is Not Generally Guaranteed

A `ScriptEngineFactory` may provide `getParameter("THREADING")` to describe threading support per JSR 223 convention. An absent parameter or `null` value cannot be interpreted as "thread-safe" by default.

For a multi-request production service:
- consider a separate engine/context per task/thread, controlled pooling, or a vendor-supported structure;
- avoid having multiple requests concurrently mutate `ENGINE_SCOPE`/global bindings on a shared engine without synchronization;
- do not give user code unrestricted access to injected Java objects.

## 9. Security: A Script Engine Is Not a Sandbox

This is especially important when migrating from built-in Nashorn to an external engine. Pinning a dependency **does not by itself protect** against running arbitrary scripts.

A JavaScript engine embedded in the JVM can have many ways to interact with the Java host, for example accessing Java classes/methods through host interoperability mechanisms. Improper configuration can allow a script to:
- read files, access the network, or invoke OS commands if the host grants permission;
- read sensitive information placed in bindings/global scope;
- cause CPU/memory exhaustion or infinite loops;
- affect the state of the application itself.

### 9.1. Safer Usage

- Only run **trusted/reviewed** scripts in learning demos.
- For user-supplied code, consider a **separate process/container sandbox**, timeouts, memory/CPU limits, filesystem/network policy, and restricted OS account privileges.
- Do not expose arbitrary Java objects, class loaders, `ProcessBuilder`, or filesystem APIs to scripts unnecessarily.
- Apply the specific engine's host class access policy per provider documentation; GraalVM `Context` offers clearer policy options than generic JSR 223 alone.
- Limit script size, cache, and concurrency; maintain an audit trail, scan dependencies, and apply patches.
- Do not treat SecurityManager (restricted/deprecated and changed in newer JDKs) as a default sandbox solution.

In particular, do not move scripts from an old JavaScript engine to a new engine and just change the alias without reviewing **host access permissions**. Defaults are not necessarily equivalent.

### 9.2. Do Not Mix JSON Parsing with JavaScript eval

If the requirement is only to parse a JSON payload, use an appropriate JSON parser library. `engine.eval(jsonString)` is not a standard/safe way to process JSON because it can turn input into executable code or alter semantics. Removing Nashorn should not force a system to spin up a JavaScript runtime just to decode data.

## 10. Ensuring Build and Deployment

### 10.1. Classpath, Fat JAR, Shaded JAR

Maven `exec:java` in this lesson uses the runtime classpath set up by Maven. When packaging for production:
- If using a "thin JAR," all transitive dependency JARs must be deployed and the classpath declared properly.
- If using a fat/shaded JAR, pay attention to the service provider metadata `META-INF/services/javax.script.ScriptEngineFactory`. Shading without merging service descriptors can cause `ScriptEngineManager` **not to see the provider** even though the implementation class is in the JAR.
- If using a custom class loader, check service resources and loader visibility.
- If using the JPMS module path, keep the provider module and dependencies consistent.

**Operational consequence:** Do not test only with `mvn exec:java` and conclude that a runnable JAR in Docker will definitely find the engine. You must run discovery + smoke eval on the **packaged artifact**.

### 10.2. The java.scripting Module in the Runtime Image

Example of a configuration check:

```bash
java --list-modules
java -version
```

`java --list-modules` shows the modules present in the runtime image of the invoked binary. If `java.scripting` does not exist in a custom image, Java host code with a direct `javax.script` dependency may fail class/module loading. If the module is present without a standalone engine, the manager may run normally but return `null`.

**Flag limitations:** `--add-modules java.scripting` cannot install a module that was stripped from the image. `--add-modules org.openjdk.nashorn` also does not download the Nashorn JAR from Maven Central; the provider JAR and its dependencies must actually be supplied.

### 10.3. Controlling Versions

In production, pin versions and test compatibility for:
- Java language/runtime target;
- engine/provider artifact and transitives;
- Maven/Gradle plugin/toolchain;
- JDK/JVM implementation;
- JavaScript syntax level and host-interoperability policy.

The main example pins `nashorn-core:15.7` and Java `--release 17`. If an application chooses GraalJS, it must pin **GraalJS/GraalVM modules of the same version set** compatible with the actual runtime. Avoid uncontrolled dependency ranges when script behavior is business-critical.

## 11. Recommended Test Matrix

| Scenario | Test Configuration | Expected Result |
| --- | --- | --- |
| No external engine | Run only `ExternalEngineDemo.class` on a clean JDK 17+ | `engine=UNAVAILABLE`, no NPE |
| Complete Nashorn provider | Maven POM with `nashorn-core:15.7` and transitives | `engine=AVAILABLE`, `answer=42`, `add=5` |
| Wrong alias | Look up an engine name not in `factory.getNames()` | Returns `null` for that alias |
| Missing Nashorn transitives | Omit an ASM dependency when packaging manually | Provider does not work properly; packaging must be restored |
| JPMS image missing `java.scripting` | Custom runtime module graph lacking the API | Module/class loading failure to be diagnosed separately |
| Engine discovered but syntax unsupported | Use syntax beyond the ECMAScript level supported by the engine | `ScriptException`/provider-specific failure |
| Engine present but lacks `Invocable` | Provider does not implement the optional interface | Code actively rejects the capability, does not cast |
| Wrong function name | Call `invokeFunction` with a non-existent name | `NoSuchMethodException` if the engine supports `Invocable` |
| Script throws error | JS error inside `eval` | `ScriptException` with diagnostics if provided by the engine |
| Shaded JAR loses SPI service descriptor | Provider JAR has class but `ServiceLoader` does not see factory | Restore/merge service metadata, test packaged artifact |
| Multiple engines with same alias | Two providers sharing the generic `"JavaScript"` name | Select provider explicitly, inspect actual factory |
| Untrusted script | Input with infinite loop or Java host access | Do not run in an unisolated process |

For the Maven demo, the minimum check is **two independent conditions**:
1. `javac --release 17` and `java -cp ...` **without external Nashorn** → controlled-unavailable result.
2. `mvn -B -q -DskipTests compile exec:java` in the project with the Nashorn dependency → JavaScript executes properly.

If case (2) has not been run in a real environment, do not write in the README "tested with Nashorn on Java 17" merely because the Java code compiles: the Java host compiler does not need a provider to compile.

## 12. Exercises and Answers

### Exercise 1 — Nashorn and Java 17

A student writes:

```java
ScriptEngine js =
        new ScriptEngineManager().getEngineByName("JavaScript");
System.out.println(js.eval("40 + 2"));
```

Why can this example not be presented as "runs on plain JDK 17, no dependencies needed"?

**Answer:** JEP 372 removed built-in Nashorn starting in JDK 15. `java.scripting` only provides the API, not a default JavaScript implementation. `getEngineByName` can return `null`, causing an NPE. You must **declare an external engine** and check the lookup before calling `eval`.

### Exercise 2 — Two Different ToolProvider / Manager Classes

Do `javax.tools.ToolProvider` and `javax.script.ScriptEngineManager` serve the same function?

**Answer:** No. `javax.tools.ToolProvider.getSystemJavaCompiler()` finds the Java compiler implementation (Java source → bytecode). `ScriptEngineManager` finds a script-engine factory to evaluate code in an embedded language, such as JavaScript. Having a Java compiler does not create Nashorn. The two APIs solve two different problems.

### Exercise 3 — Build Dependency and Runtime Classpath

The POM has `nashorn-core`, but the Docker image only copies the application JAR and omits transitive JARs. `getEngineByName("nashorn")` must still succeed because the source imports `javax.script`, true or false?

**Answer:** False. Script-engine discovery requires **the provider implementation at runtime**, its ASM/transitive dependencies, service registration, and class loader/module visibility. Importing the API does not create a provider.

### Exercise 4 — Fallback Design

An application has an optional feature allowing scripts to be run for testing. If no engine is present, what is a reasonable policy?

**Answer:** Disable the feature in a controlled manner and return a `SCRIPT_ENGINE_UNAVAILABLE` status or a message requesting dependency configuration. **Do not** mock `eval` results and do not invoke on `null`. If the feature is required, fail fast during service initialization.

### Exercise 5 — Engine Migration

A development team replaces the `"nashorn"` alias with `"graal.js"`. Why is testing still required?

**Answer:** The new engine may have differences in ECMAScript syntax, global variables, Java interop, return values, threading, and security defaults. You need to add the GraalJS dependency, choose a compatible version/JDK, and verify actual script behavior.

### Exercise 6 — Safety Policy

Can we accept arbitrary scripts from an API and execute `engine.eval(source)` directly in a Java web server because "it's just scripting"?

**Answer:** No. A script can consume unbounded CPU/memory or interact with the Java host if the engine grants access. Auth, resource limits, host access policy, isolation/sandboxing, and input validation rules are required. Depending on the specific engine, generic `ScriptEngine` is not enough to guarantee safety.

### Exercise 7 — Independent Verification

State the two expected stdouts when running the `ExternalEngineDemo` program properly:
1. Using only the compiled class, **without an external provider**.
2. Running via the Maven project with `nashorn-core:15.7`.

**Answer:** Case 1 prints `engine=UNAVAILABLE`. Case 2 prints `engine=AVAILABLE`, `greeting=Hello, Java`, `answer=42`, `add=5`. Both states were verified using Java 17-compatible host code on JDK 24.

## References

- [JEP 335 — Deprecate the Nashorn JavaScript Engine](https://openjdk.org/jeps/335): deprecated for removal milestone in JDK 11.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): removed in JDK 15; **`javax.script` was unaffected**.
- [Java SE 17 — ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): `ServiceLoader` mechanism, class loader, `getEngineByName` returning `null`, `getEngineFactories`.
- [Java SE 17 — ScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, `Bindings`, and scopes.
- [Java SE 17 — ScriptEngineFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): names/aliases, versions, and provider capabilities.
- [Standalone OpenJDK Nashorn project](https://github.com/openjdk/nashorn): Nashorn outside the JDK, supporting Java 11+ and JPMS/ASM dependencies.
- [Maven Central — nashorn-core 15.7](https://central.sonatype.com/artifact/org.openjdk.nashorn/nashorn-core/15.7): specific artifact used in the runnable program.
- [GraalJS documentation](https://www.graalvm.org/javascript/docs/): embedding options via Java/JVM.
- [GraalVM ScriptEngine documentation](https://www.graalvm.org/jdk22/reference-manual/js/ScriptEngine/): `js-scriptengine` provider as a separate dependency; recommends `Context` when fine-grained security is needed.
- [Maven Central — GraalJS js-scriptengine 25.0.3](https://central.sonatype.com/artifact/org.graalvm.js/js-scriptengine/25.0.3): reference coordinates example for an alternative engine, must confirm JDK compatibility.

## Conclusion

**Nashorn has been removed from the JDK since JDK 15**, so Java 17+ examples must not assume `ScriptEngineManager.getEngineByName("JavaScript")` will always succeed. **`javax.script` still exists as a general API**; the engine implementation must be supplied **explicitly**. For the illustrative lesson using Nashorn, the POM declares `org.openjdk.nashorn:nashorn-core:15.7` and the program checks `engine == null` before calling `eval`. For GraalJS or another provider, a separate dependency/version and security policy are also required. Always test **both with and without the provider** on the actual deployed runtime, check the classpath/module path/SPI, and avoid using an in-process script engine to run untrusted code without isolation.