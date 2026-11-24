# Distinguishing Missing Classes, Missing Transitive Dependencies, and Library Version Mismatches

> **Context:** Spring Boot Auto Configuration — **Classpath conditions** group. This lesson focuses on how to distinguish classpath symptoms from root causes in the dependency graph and library binary compatibility. Examples use Java 17+.

## 1. Mental Model: Three Related Cases That Are Not Synonymous

The **runtime classpath** is the set of directories/JARs that the JVM and class loader can actually find when the application starts and runs. It can differ from the **compile classpath** used during compilation. Having a class at compile time does not guarantee that class is packaged or loaded in the right version at runtime.

| Case | Root problem | Common symptoms | First verification direction |
| --- | --- | --- | --- |
| **Missing class** | The JVM/class loader cannot find a required class at load or link time | ClassNotFoundException, NoClassDefFoundError | Which JAR actually contains the class? Is that JAR on the **runtime** classpath? |
| **Missing transitive dependency** | Library A is included in the application, yet Library B that A needs at runtime is absent | Usually also NoClassDefFoundError, sometimes ClassNotFoundException | Is A present while B was excluded, given the wrong scope, marked optional, or not packaged? |
| **Incompatible library version** | The class is loaded, yet the actual API/ABI does not match the version compiled against; sometimes a newer version removed the old class | NoSuchMethodError, NoSuchFieldError, AbstractMethodError, IncompatibleClassChangeError; can also be NoClassDefFoundError | Which exact JAR version was selected and loaded? Does a method/field with the **exact signature** exist in that JAR? |

**Core distinction:** “Missing class” is a **symptom at the class-loading level**; a missing transitive dependency is **one cause** that can produce that symptom. A version mismatch can also cause a missing class if a newer release moved/removed a class. Therefore **you cannot conclude solely from the exception name**; you must connect the exception to the failing class, the JAR containing that class, and the runtime dependency graph.

Suppose an application directly depends on SDK A, and A depends on Library B:

~~~text
Application
  └── SDK A                 (direct dependency)
        └── Library B       (transitive dependency)
              └── class B.Helper
~~~

- Missing **SDK A**: a class in A may fail to load.
- Have **A** but missing **B**: a class in B fails to load when A calls into B.
- Have **A** and **B**, yet B was replaced by an incompatible version: class B.Helper may still exist, yet A's method call can trigger NoSuchMethodError.

## 2. Interpreting JVM Error Signals Correctly

### 2.1. ClassNotFoundException and NoClassDefFoundError

- **ClassNotFoundException** is a checked exception usually thrown when code actively looks up a class by name, such as Class.forName("com.example.Plugin") or ClassLoader.loadClass(...), and the loader cannot find it. Possible reasons include a missing JAR, misspelled class name, wrong class loader, or an optional feature not installed.
- **NoClassDefFoundError** is a LinkageError typically occurring when bytecode needs a class that the JVM cannot define/find at execution time, even though the code compiled successfully elsewhere. The class name in the message is a **direct clue** to trace the owning JAR.
- **NoClassDefFoundError: Could not initialize class ...** can be the consequence of an **earlier static initialization failure** (such as ExceptionInInitializerError), not simply a missing JAR. Read the **Caused by** chain and the chronologically first error.
- Errors may be wrapped inside Spring's BeanCreationException, IllegalStateException, or UnsatisfiedDependencyException. Walk down to the root cause in the stack trace instead of reading only the top line.

For example:

~~~text
java.lang.NoClassDefFoundError: com/example/transport/Codec
~~~

This is proof the JVM needed the Codec class and could not use it. It does **not yet** prove whether the app forgot to declare a direct dependency or a transitive dependency: you must locate which library owns Codec and why that library is absent.

### 2.2. Signs of API/ABI Version Skew

- **NoSuchMethodError**: a call was compiled with a specific name, parameter types, and return type, yet the corresponding method does not exist in the actual runtime class.
- **NoSuchFieldError**: a field was referenced at compile time yet does not exist in the expected form at runtime.
- **AbstractMethodError / IncompatibleClassChangeError**: interface/class relationships or binary contracts changed, often involving library versions or mixed versions.
- **UnsupportedClassVersionError**: bytecode was compiled for a newer Java version than the running JVM; check JDK/JRE versions first rather than lumping it under “missing dependency”.
- **ExceptionInInitializerError**: static initialization code threw an error; could be configuration, resources, or a library bug, not automatically a version mismatch.

Having a class with the same fully qualified name (FQCN) is **not enough** to prove compatibility. With NoSuchMethodError, compare **bytecode signatures** (descriptors) including the return type, not merely the method name in documentation.

## 3. Distinguishing via Ordered Diagnostic Questions

1. **Capture the root error:** record the error type, class/method/field name, stack trace, and Caused by chain; identify whether it happens at startup, bean creation, or API invocation.
2. **Identify the owning class/JAR:** find the group/artifact/version containing the reported FQCN; do not guess from starter names or bean names.
3. **Inspect the actual runtime classpath:** was the dependency resolved for runtimeClasspath? Is it inside the executable JAR/container or actual `java -cp` command? Is a custom class loader involved?
4. **If the needed JAR is absent:** is it an undeclared direct dependency, or a transitive dependency of an already-present library? Look for exclusions, optional, compileOnly/provided, Gradle/Maven configs, and packaging bugs.
5. **If the JAR is present:** verify the JAR contains the exact class; if so, use `javap` to compare methods/fields against the compiled version, resolved version, and classpath/class loader order.
6. **Cross-check with the Spring Boot condition report:** `@ConditionalOnClass` not matching can be **normal optional behavior**. If a needed bean is missing or the app actually crashes, investigate further; do not treat every negative match as a bug.
7. **Fix the exact root cause and re-run in the exact environment:** test with the same JDK, profile, packaging method, launch command, and dependency graph that caused the failure.

~~~text
Is there a classpath-related error?
  |
  +-- Only @ConditionalOnClass not matching, and app still runs?
  |     +-- Likely an optional feature skipped by design.
  |
  +-- ClassNotFoundException / NoClassDefFoundError?
  |     +-- Find class -> owning JAR -> present at runtime?
  |           +-- No: check direct vs. transitive dependency,
  |           |       exclusions, scope, packaging, class loader.
  |           +-- Yes: check actual class inside JAR, other dependent classes,
  |                    static initialization errors, and loaded version.
  |
  +-- NoSuchMethodError / NoSuchFieldError / AbstractMethodError?
        +-- Class is present yet ABI mismatches:
              compare compile vs. runtime versions, dependency resolution,
              signatures via javap, and classpath order.
~~~

## 4. Java 17+ Lab: Same Program, Three Different Outcomes

This lab simulates **App → SDK → Helper**. App calls SDK directly; SDK is compiled against Helper v1. Neither Spring Boot nor a build tool is needed to reproduce it, allowing us to observe JVM errors independently of the framework.

Create files with the structure:

~~~text
src/
  helper/v1/demo/Helper.java
  helper/v2/demo/Helper.java
  sdk/demo/Sdk.java
  app/App.java
~~~

**File src/helper/v1/demo/Helper.java**

~~~java
package demo;

public final class Helper {
    public static String text() {
        return "helper-v1";
    }
}
~~~

**File src/helper/v2/demo/Helper.java** — same class name, changed API, removing `text()`:

~~~java
package demo;

public final class Helper {
    public static String renamed() {
        return "helper-v2";
    }
}
~~~

**File src/sdk/demo/Sdk.java** — SDK calling Helper v1's API:

~~~java
package demo;

public final class Sdk {
    public static String call() {
        return Helper.text();
    }
}
~~~

**File src/app/App.java** — application only needs to know SDK:

~~~java
import demo.Sdk;

public class App {
    public static void main(String[] args) {
        System.out.println(Sdk.call());
    }
}
~~~

Use a Bash/Git Bash terminal in the directory containing `src`; requires **JDK 17+**. To clearly see the difference, each output directory serves as a separate classpath entry:

~~~bash
mkdir -p out/helper-v1 out/helper-v2 out/sdk out/app
javac -d out/helper-v1 src/helper/v1/demo/Helper.java
javac -cp out/helper-v1 -d out/sdk src/sdk/demo/Sdk.java
javac -cp out/sdk -d out/app src/app/App.java
javac -d out/helper-v2 src/helper/v2/demo/Helper.java
~~~

**Case 1 — all classes present and right version:** App, SDK, and Helper v1 are all present.

~~~bash
java -cp out/app:out/sdk:out/helper-v1 App
~~~

Exact stdout:

~~~text
helper-v1
~~~

**Case 2 — missing class from direct dependency:** omit `out/sdk`, even though Helper v1 remains.

~~~bash
java -cp out/app:out/helper-v1 App
~~~

The program stops with an error named **NoClassDefFoundError: demo/Sdk** (full stack traces may vary). The SDK's own class is missing from the runtime classpath.

**Case 3 — missing transitive dependency:** keep `out/sdk`, yet omit the Helper that SDK compiled against.

~~~bash
java -cp out/app:out/sdk App
~~~

The program stops with an error named **NoClassDefFoundError: demo/Helper**. The SDK exists, yet the component it needs at execution time is absent. In real builds, the corresponding situation can stem from exclusions, scope, or the SDK's dependency metadata.

**Case 4 — dependency version mismatch:** swap Helper v1 for Helper v2, keeping the SDK compiled against v1.

~~~bash
java -cp out/app:out/sdk:out/helper-v2 App
~~~

The program stops with **NoSuchMethodError** referencing **demo.Helper.text()**. The JVM found demo.Helper, yet the runtime version no longer has the method `Sdk.class` expects. This is **binary incompatibility**, not a missing class.

**On Windows CMD/PowerShell**, the separator between classpath entries is a semicolon **;** instead of a colon **:**, e.g. `java -cp "out/app;out/sdk;out/helper-v1" App`. The `mkdir -p` command above is for Bash/Git Bash; you can create the directories via file manager or PowerShell before running `javac`.

Lesson from the lab: **the exact same `App.class`** yields completely different outcomes depending on the **runtime classpath**. Hence dependency lines declared in source are only a starting point, not a substitute for checking what the JVM actually loads.

## 5. Reading the Dependency Graph with Gradle and Maven

### 5.1. Gradle: Must Inspect the Runtime Configuration

For a hypothetical app module with Gradle tasks, use:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency helper-lib --configuration runtimeClasspath
~~~

On Windows, use `gradlew.bat` instead of `./gradlew`; substitute `:app` and `helper-lib` with actual module/artifact names.

- **dependencies** shows which libraries are resolved into `runtimeClasspath` and their parent–child relationships.
- **dependencyInsight** explains why a module/version was chosen, including dependency paths and conflict resolution rules when present.
- Compare against **compileClasspath** when suspecting compilation succeeds yet runtime lacks a library; do not conclude solely from the dependency tree if the actual launch command or packaging alters the classpath.

Configuration example **solely to illustrate the idea** (`com.example` coordinates below are hypothetical):

~~~groovy
dependencies {
    implementation 'com.example:client-sdk:1.2.0'
}

// If the SDK needs com.example:helper-lib at runtime yet the dependency path is excluded
// or marked with the wrong scope, runtime may lack helper-lib classes.
~~~

Distinguish:
- **implementation**: module dependency present at compile time and normally carried into the app module's runtime.
- **runtimeOnly**: needed when running, not needed to compile direct source.
- **compileOnly**: participates only at compile time; misusing it for a library genuinely needed at runtime leaves runtime lacking it.
- **exclude**: removes a transitive dependency path; if no other path supplies the needed module, the app can crash.
- **api** in the `java-library` plugin: exposes the dependency to consumers in the compile API; when an SDK exposes classes via public API, choose accurately between `api`/`implementation`. Do not overuse `api` just to make runtime errors vanish.

If multiple versions of the same library appear, check the **resolved version**; Gradle has conflict resolution mechanisms and can be governed by constraints, platforms, or `force`. A desired dependency line **does not guarantee** it is the final version used.

### 5.2. Maven: Inspecting the Tree and Scope

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=com.example:helper-lib
~~~

- See which dependency branch brings `helper-lib` into the project, whether it is dropped by exclusion/optional, or overridden by another version.
- **provided** is normally not packaged as a regular runtime library; **test** is not used for production apps; **optional** limits transitivity to consumers.
- Maven's dependency mediation can pick a version by declaration path/nearest-wins; inspect the effective version rather than looking only at the SDK's `pom.xml`.
- With Spring Boot, use compatible version management from the **Spring Boot BOM** as configured in your build, avoiding manually forcing individual versions of Spring Framework, Jackson, Netty, or infrastructure libraries already managed by Boot.

### 5.3. Inspecting the Actual JAR and APIs Inside the JAR

~~~bash
jar tf path/to/library.jar
javap -classpath path/to/library.jar -s -p com.example.Helper
java -version
~~~

- Use **jar tf** to confirm the actual bytecode path (e.g. `com/example/Helper.class`) exists.
- Use **javap -s -p** to inspect actual method/field names and descriptors; compare the compile JAR with the runtime JAR.
- For a **Spring Boot executable JAR**, look at dependencies packaged under `BOOT-INF/lib` and app classes under `BOOT-INF/classes`. When running with `java -jar`, Boot's launcher handles nested JARs; do not assume `java -cp app.jar` automatically loads nested dependencies.
- With Docker/containers, IDEs, plugin frameworks, or multi-classloader apps, inspect the **final artifact and launch command**. A dependency present on a developer machine can still be missing from the deployment image.

## 6. Direct Connection to Spring Boot Auto Configuration

**@ConditionalOnClass** is a condition enabling auto-configuration **when the specified classes are present**. If an optional dependency is not installed, the condition does not match and the configuration can be skipped **by design**. When reading condition reports, distinguish:

| Symptom | Meaning | What to do |
| --- | --- | --- |
| @ConditionalOnClass reports **did not find required class** and app runs normally | Auto-configuration for the optional feature was not applied | Only add the dependency if the app genuinely needs that feature |
| Needed bean does not appear and class is reported missing | A classpath condition blocked the needed configuration | Identify the dependency owning the class; check runtimeClasspath and other conditions |
| Startup throws NoClassDefFoundError while parsing/creating beans | A required class truly cannot be used; may be transitive dependency, premature reference, or init failure | Trace Caused by, inspect classpath/JARs, isolate optional configurations properly |
| @ConditionalOnClass matches yet calling SDK throws NoSuchMethodError | The condition only proves **class presence**, not full API compatibility | Compare API signatures and the actually loaded version |

Example auto-configuration structure with a classpath condition (this is a **component snippet** in a Spring Boot project, not a standalone program compiled with plain `javac`):

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class ClientPresentConfiguration {

        @Bean
        ClientFeature clientFeature() {
            return new ClientFeature();
        }
    }

    public static final class ClientFeature {
    }
}
~~~

Here the condition uses a **string class name**. If `com.vendor.sdk.Client` is absent, the nested configuration class is skipped; the code does not directly reference the `Client` type in an unsafe spot that forces the JVM to link it. When an `@Bean` method uses **return or parameter types from an optional library**, isolate that method inside an `@Configuration` class guarded by a classpath condition to avoid inspecting the method signature too early when the dependency is absent. For a library's auto-configuration to be discovered, the project must register that class via the `AutoConfiguration.imports` mechanism appropriate for the Spring Boot version in use.

**Limits of @ConditionalOnClass:** it does not automatically check transitive dependencies, method signatures, SDK version compatibility, successful bean creation, or specialized runtime class loaders. Therefore a positive match **does not** guarantee no `NoSuchMethodError` or `NoClassDefFoundError` will happen later.

**Viewing the condition report:** run the app with `--debug` or view the condition evaluation report via the **conditions** actuator endpoint when Actuator is installed and the endpoint is enabled/exposed per operational policy. The report shows match/did-not-match reasons; it **does not replace stack traces** once the JVM has thrown an error. Do not expose diagnostic actuator endpoints publicly without access control.

## 7. Three Real-World Investigation Cases in a Spring Boot Application

### Scenario A — SDK Class Is Missing

**Observation:** the app requires an integration bean, yet startup reports `NoClassDefFoundError: com/vendor/sdk/Client`. The condition report may also show the corresponding auto-configuration was skipped.

**Verification:** find the JAR owning `Client`; if the app actually calls the SDK, confirm the direct dependency and runtime JAR are present in `BOOT-INF/lib` or the deployment classpath.

**Fix:** declare the right artifact with the proper scope/runtime configuration, ensuring the artifact is in the deployment package. If the SDK is an optional feature the app does not use, the condition not matching may be the expected outcome.

### Scenario B — SDK Exists, Yet a Library Used by the SDK Is Missing

**Observation:** `com.vendor.sdk.Client` loaded fine; when creating the bean/calling the SDK, `NoClassDefFoundError: com/vendor/transport/Codec` appears.

**Verification:** identify which artifact `Codec` belongs to; read the dependency tree to see if it is a transitive dependency of the SDK. Inspect exclusions, `optional`/`provided`/`compileOnly`, and JAR/container contents. Do not try to work around it by changing `@ConditionalOnClass` to another condition: conditions do not create missing classes.

**Fix:** restore the valid dependency path, remove erroneous exclusions, or declare the required runtime dependency directly with a compatible version. Then retest **the exact behavior** that failed before (bean creation, connection, request handling), not just startup.

### Scenario C — Class Still Exists, Method Is Gone

**Observation:** `NoSuchMethodError: com.vendor.transport.Codec.encode(...)` after upgrading a library or resolving to a different version.

**Verification:** `dependencyInsight`/`dependency:tree` shows the effective version; `jar tf` confirms `Codec.class`; `javap` compares methods and descriptors between the expected SDK version and the loaded transport version. Watch out for same-family dependencies or mixed BOM versions.

**Fix:** choose a verified compatible version set, prefer unified management via BOM/platform, and remove `force`/exclusions causing skew if no longer justified. Do not blindly “upgrade everything to latest”: the latest version is not necessarily compatible with the SDK or the running Spring Boot version.

## 8. Common Misconceptions

1. **“NoClassDefFoundError definitely means a missing direct dependency.”** False: the class may live in a transitive dependency, be omitted from packaging, be loaded by another class loader, or have failed during static initialization.
2. **“Having the JAR is enough.”** False: the JAR can be the wrong version, lack a class, be shadowed by another version at runtime, or have the class yet lack required methods/fields.
3. **“If compilation succeeds, running succeeds too.”** False: `compileClasspath` and `runtimeClasspath` differ; compiled bytecode can encounter a different ABI at runtime.
4. **“Auto-configuration not matching means Spring Boot is broken.”** False: negative matches are normal for optional libraries/features; only investigate when it violates the app's functional requirements.
5. **“Just add the latest dependency version.”** False: that can introduce binary conflicts; you must find a version compatible with the SDK, Boot BOM, and related libraries.
6. **“A BeanCreationException log is just a bean error.”** Incomplete: expand the `Caused by` chain to find the real `ClassNotFoundException`, `NoClassDefFoundError`, or `LinkageError`.
7. **“If it runs in the IDE, the JAR/Docker image is guaranteed to run.”** False: IDEs, tests, executable JARs, and containers may use different classpaths, profiles, or Java runtimes.

## 9. Quick Handling Checklist and Conclusion Criteria

- [ ] Record the **root error**, exact FQCN or signature, timing, and environment where it occurred.
- [ ] Identify the **owning artifact** of the class/method; verify the runtime JAR exists and contains the needed class.
- [ ] Inspect the dependency graph of **runtimeClasspath**, comparing with `compileClasspath` when needed; trace direct/transitive paths, exclusions, and scopes.
- [ ] If the JAR is missing: classify **direct missing** vs. **transitive missing** via dependency relations; if the JAR is present yet a method is wrong: check **version/ABI**.
- [ ] Check the Java runtime, class loader, and actually deployed artifact; verify `BOOT-INF/lib` for a Boot executable JAR.
- [ ] Use the condition report to understand `@ConditionalOnClass` decisions; distinguish an “intentional skip” from a crash or missing required feature.
- [ ] Fix the dependency/scope/version according to the proven cause; rerun the real failing scenario and confirm the root error is gone.

**Self-check:** (1) The SDK is present yet the SDK's helper was not packaged — what is the cause? **Missing transitive dependency**. (2) `Helper.class` is present yet the SDK calls a method existing only in Helper v1 while runtime uses v2 — what is the cause? **Version/ABI mismatch**. (3) `@ConditionalOnClass` does not match for an optional SDK and the app still runs — is it definitely a bug? **No**; that may be intended design behavior. (4) Does `NoClassDefFoundError: Could not initialize class ...` prove a missing JAR? **No**; look for the initial initialization error.

When analyzing classpaths for Spring Boot, base conclusions on **the classes/JARs actually loaded + the runtime dependency graph + ABI signals + auto-configuration conditions**, never solely on the exception name.