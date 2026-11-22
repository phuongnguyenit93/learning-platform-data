# Upgrading the JDK Without Moving the Entire Application to JPMS

Upgrading the JDK and moving an application to the Java Platform Module System (JPMS) are **two related tasks that do not have to be performed at the same time**. Starting in Java 9, the JDK introduced a module system, `module-info.java` files, and stronger encapsulation mechanisms. However, most traditional Java applications can still be compiled, packaged, and run on the **classpath** as before, without immediately turning every JAR into a *named module*.

That does not mean upgrading the JDK will not affect an unmodularized application. Older libraries may access JDK internal APIs, use reflection into closed packages, depend on APIs that were removed from the JDK, or be affected by how the JDK loads classes. Therefore, a sensible approach is to **keep the classpath architecture when needed, while proactively addressing changes introduced by the JDK and JPMS**.

This article guides you through identifying the boundary between a runtime upgrade and modularization, running a legacy application on the classpath, understanding the errors that can arise, and following a verification process before deciding whether a full migration to JPMS is needed.

## 1. JPMS Does Not Mean Every Application Must Have module-info.java

JPMS was introduced in Java 9 with the goal of organizing applications into named modules, declaring dependencies explicitly, controlling which packages are exported or opened, and enabling runtime images to be built with an appropriate set of modules.

An explicitly declared module can contain a descriptor:

~~~java
module com.example.orders {
    requires java.sql;

    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Here:

- `module com.example.orders` names the module.
- `requires java.sql` declares a readable dependency.
- `exports` allows other modules to access public types in the exported package.
- `opens` allows deep reflection into the opened package according to JPMS rules.

If the current application does not yet have `module-info.java`, we are **not required** to add this file just to move from JDK 8 to JDK 11, 17, or 21. The application can still use the classpath:

~~~bash
java -cp "app.jar:lib/*" com.example.orders.Main
~~~

The example command uses `:` as the classpath separator following Linux/macOS conventions. On Windows, use `;`:

~~~powershell
java -cp "app.jar;lib/*" com.example.orders.Main
~~~

Note that the `lib/*` wildcard syntax is a capability of the Java launcher to select JARs directly inside the directory; it does not recursively traverse subdirectories. Framework executable/fat JAR packaging may use its own launcher mechanism, so run the project's actual artifact format.

Key point: **running on the classpath remains a supported execution mode in modern Java**. What needs to be verified is whether the entire runtime and the application's dependencies are compatible with the new JDK.

## 2. Distinguishing Classpath, Module Path, and Module Types

When using a JDK with JPMS, the path containing libraries is no longer a single concept. You need to distinguish how the JVM sees JARs.

| Concept | Meaning | Characteristics |
|---|---|---|
| Classpath | List of class directories/JARs under the traditional Java mechanism | Does not require `module-info.java`; classes belong to the unnamed module of the corresponding class loader |
| Unnamed module | An unnamed module containing classes loaded from a class loader's classpath | Has no descriptor declaring `requires`, `exports`, or `opens` |
| Module path | Location containing modules used by JPMS for resolution | Used with `--module-path` or `-p` |
| Explicit named module | A module with a `module-info.class` descriptor | Has a name, dependencies, exports/opens, and readability rules |
| Automatic module | A JAR without a descriptor placed on the module path | The JVM assigns a module name from metadata/JAR name and applies automatic module mechanics |
| JDK system module | Foundational modules and modules bundled with the runtime | For example, `java.base`, `java.sql`, `java.xml`, `java.net.http` |

A legacy JAR placed on the **classpath** does not automatically become an automatic module. If that same JAR is moved to the **module path**, it can become an automatic module if it lacks a descriptor. Therefore, moving libraries from `-cp` to `--module-path` is a significant behavioral change, not merely renaming an option.

### 2.1. Unnamed Modules and Accessibility

Classes on the classpath belong to the unnamed module associated with the class loader loading them. For code on the classpath, many access rules between application classes remain similar to the traditional Java mechanism. The application does not need to declare `requires` for each JAR on the classpath.

However, access to **named JDK modules** is still subject to JPMS encapsulation. An unnamed module can read resolved modules, but **being able to read a module does not mean having access to every package**. Only packages exported to the caller allow valid access to public types; deep reflection additionally requires the package to be opened.

### 2.2. Automatic Modules Are Not the Default Solution

Automatic modules help bridge some legacy libraries when building a modular application. However, they carry additional consequences:

- The module name may depend on `Automatic-Module-Name` or the JAR file name.
- Split package issues can appear when multiple modules contain the same package.
- The module graph and package visibility may change.
- A named module cannot arbitrarily depend on the classpath like legacy code.

If the immediate goal is simply a **safe JDK upgrade**, do not mechanically move all dependencies onto the module path. Keeping the classpath reduces the number of changing variables within the same migration wave.

## 3. Practical Goals of Upgrading the JDK Without Modularizing

Suppose the system has the architecture:

~~~text
Order Application
  ├── app.jar
  ├── lib/spring-*.jar
  ├── lib/jackson-*.jar
  ├── lib/database-driver.jar
  └── lib/internal-common.jar

Current runtime: JDK 8
Target runtime: JDK 17
Application does not yet have module-info.java
~~~

The goals of the initial phase can be:

1. The application builds with a compiler and build tools compatible with the new JDK.
2. The final artifact uses the selected API and class-file target.
3. The new runtime loads classes and dependencies properly.
4. The application context, reflection, serializers, ORM, and drivers operate properly.
5. Core business flows and data preserve their semantics.
6. No errors occur due to JDK module encapsulation or removed APIs.
7. The system meets basic operational requirements on the new JDK.

**Not having `module-info.java` is not an error** if the product has no modularization requirement. Separating JPMS into a separate initiative reduces the scope of change and clarifies root causes when issues occur.

On the other hand, if the project uses native image, a plugin framework, or a specialized packaged runtime, further evaluation is needed based on how those tools work. Classpath mode does not automatically solve all ecosystem compatibility issues.

## 4. Changes in Newer JDKs That Still Affect the Classpath

An application that does not use named modules can still face significant changes when upgrading the JDK.

### 4.1. Encapsulation of JDK Internals

Internal JDK packages such as certain packages under `sun.*` or `com.sun.*` are not Java SE APIs guaranteed to be stable. JPMS makes the boundary between modules and exported packages explicit; many accesses previously performed by legacy libraries may no longer be permitted.

For example, a library uses reflection to access a private field of `java.lang.String`. Even though the library is on the classpath, the `java.lang` package of the `java.base` module is not open by default for deep reflection from an unnamed module on newer Java versions.

### 4.2. Some Previously Built-In Modules/APIs Have Been Removed

When moving from JDK 8 to JDK 11 or later, many projects run into the Java EE/CORBA technologies that previously shipped with JDK 8. For example, JAXB, JAX-WS, and related APIs are no longer included in JDK 11 as before. Applications may encounter `ClassNotFoundException` or `NoClassDefFoundError` if the corresponding dependencies are not added.

Other ecosystem changes include JavaFX no longer being distributed as a default component of OpenJDK starting in Java 11, and the Nashorn JavaScript engine being removed in JDK 15. Not all applications use those components; an inventory of actual dependencies is needed.

### 4.3. Frameworks and Libraries Also Change

Upgrading the JDK may require upgrading frameworks, ORMs, servlet containers, bytecode manipulation libraries, compiler plugins, or agents. When upgrading libraries, even without modularizing, an application may still experience changes in APIs, annotation namespaces, configurations, or serialization behavior.

Do not attribute every error appearing after a JDK upgrade to JPMS. Categorize errors into: class-file version, removed APIs, reflection access, dependency conflicts, class loaders, framework behavior, and runtime configuration.

## 5. Strong Encapsulation: Common Errors Even When Still Running on the Classpath

### 5.1. Normal Reflection and Deep Reflection

Reflection is used by applications in many areas: dependency injection, ORM, serializers, proxies, bean introspection, and testing. **Not all reflection is blocked by JPMS.**

For example, a class `com.example.orders.Order` on the same classpath can still be inspected by a framework on the classpath through appropriate reflection APIs. The prominent obstacle appears when a library attempts to access **non-public members belonging to a package in a non-open named module**, especially internal or foundational JDK packages.

Illustrative example:

~~~java
import java.lang.reflect.Field;

public class DeepReflectionExample {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");
        value.setAccessible(true);
    }
}
~~~

On JDKs with strong encapsulation, calling `setAccessible(true)` on `java.lang.String` from an unnamed module can throw `InaccessibleObjectException`, with a message stating that module `java.base` does not open package `java.lang` to the caller. This is an example of a reflection boundary; applications should not rely on the private layout of `String`.

### 5.2. Related Errors to Distinguish

| Error/symptom | Common meaning |
|---|---|
| `InaccessibleObjectException` | Deep reflection is prohibited by module boundaries or access permissions |
| `IllegalAccessException` | Reflection is not permitted to access the member in that specific context |
| `IllegalAccessError` | Bytecode linkage violates access permissions at runtime |
| `NoSuchFieldError`, `NoSuchMethodError` | Runtime field/method signature does not match what the code was compiled against |
| `ClassNotFoundException` | The class lookup mechanism cannot find the requested class |
| `NoClassDefFoundError` | The JVM cannot use the required class, possibly due to a missing dependency or a prior initialization failure |
| `UnsupportedClassVersionError` | The JVM does not support the loaded class-file version |

A message containing a module name, package, and the phrase “does not open” is a strong clue about deep reflection. A “does not export” message usually relates to package accessibility. Read the stack trace down to the root cause rather than looking only at the outer exception wrapped by a framework.

### 5.3. Milestones from JDK 9 to JDK 17

Early JPMS releases had a mechanism relaxing reflective access to certain JDK internals to ease migration, typically emitting illegal reflective access warnings. Across versions, the policy was tightened; starting in JDK 17, strong encapsulation of JDK internals is enforced more broadly under JEP 403, except for supported surfaces or those explicitly opened.

Do not rely on `--illegal-access=permit` as a sustainable solution: this option no longer relaxes access on JDK 17 and later. Find replacement libraries or new configurations, and only use specific overrides when there is a clear rationale.

## 6. Using --add-opens and --add-exports in the Right Context

When an older library does not yet have an update, the JVM provides options to selectively open module boundaries. These are **controlled compatibility measures**, not a mandatory step for every legacy application.

### 6.1. --add-opens for Deep Reflection

Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "app.jar:lib/*" \
     com.example.orders.Main
~~~

Meaning:

- `java.base` is the source module name.
- `java.lang` is the opened package.
- `ALL-UNNAMED` allows all unnamed modules to perform deep reflection into this package under the JVM's reflective access rules.

This option is broader than what many applications actually need. Do not add it by default to every JVM. Use it only when a stack trace shows a library needs specific access, after considering upgrading the library or fixing the code.

### 6.2. --add-exports for Accessing Non-Exported APIs

An example illustrating a case of depending on a JDK internal API:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
     -cp "app.jar:lib/*" \
     com.example.orders.Main
~~~

`--add-exports` opens access to public types in a named module's package for the specified target. It is **not equivalent** to `--add-opens` for accessing private members via deep reflection.

If a library requires `--add-exports` to `sun.nio.ch`, treat this as technical debt that needs to be eliminated in the long term. Internal APIs can disappear or change even when access has been opened.

### 6.3. Distinguishing the Options

| Option | Purpose | When to consider |
|---|---|---|
| `--add-opens` | Allow deep reflection into a module's package | A framework/library needs specific reflective access |
| `--add-exports` | Export a package to a target module/unnamed module | There is a dependency on public types in an unexported package |
| `--add-modules` | Add root modules to the resolution process | A module exists but is not resolved by default |
| `--add-reads` | Add a readability edge between modules | Bridging scenarios with a complex module graph |
| `--module-path` / `-p` | Declare the module path | Running named/automatic modules |
| `--class-path` / `-cp` | Declare the classpath | Running legacy or classpath-based applications |

Do not use `--add-modules` to “restore” a module that has been **removed from the JDK**. If JAXB/JAX-WS are no longer provided by the JDK, add the appropriate dependencies instead of adding a nonexistent module name.

When using these flags, store them in environment configurations/launch scripts and test thoroughly. Do not leave manual flags in an IDE on one developer machine while CI and production lack them.

## 7. Classpath and Module Path Have Different Constraints

### 7.1. Do Not Move All JARs to the Module Path at Once

When moving a legacy JAR from the classpath to the module path, it is no longer simply a JAR in an unnamed module. Without `module-info.class`, it usually becomes an automatic module. Changing this placement can expose errors:

- Two modules containing overlapping packages (*split package*).
- A module requiring a dependency that is not resolved.
- An automatic module name changing according to the JAR file name.
- A named module attempting to access classes in an unnamed module outside the normal module graph.
- A Java agent or class loader framework whose class lookup logic is tied to the classpath.

If the JDK upgrade is already complex enough, it is best to keep the classpath stable, resolve all runtime errors first, and only attempt modularization afterward.

### 7.2. Split Packages and Duplicate Classes

The classpath can contain multiple JARs with the same package, and the JVM typically picks classes according to the class-loader search order, causing unpredictable errors that do not necessarily appear right at startup. JPMS enforces additional package constraints in the module graph, making split package errors surface explicitly when switching to the module path.

Do not assume a “green classpath build” means clean dependencies. Inspect duplicate classes, conflicting versions, and shaded or repackaged libraries. This is an inherent risk of the classpath, not solely of JPMS.

### 7.3. Module Readability Is Not the Same as Class Visibility

A module needs **readability** to read another module, and the referenced package must be properly **exported** to access public APIs. For reflection on non-public members, the package must also be **opened** to the caller.

Module example:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.internal to com.fasterxml.jackson.databind;
}
~~~

This example only illustrates when a library has been modularized and the target module has the exact name. If the entire application remains on the classpath, there is no need to create the descriptor above solely to declare `exports`. The differences in module visibility become important as part of the project gradually transitions to named modules.

## 8. Removed Java Modules: Add Dependencies Instead of Trying to Call Old Modules

A common scenario during migration is code using JAXB:

~~~java
import javax.xml.bind.JAXBContext;

public final class XmlSupport {
    public static JAXBContext create() throws Exception {
        return JAXBContext.newInstance(OrderXml.class);
    }
}
~~~

With JDK 8, JAXB APIs were built into the JDK. Starting in JDK 11, Java EE/CORBA modules were removed from the JDK, so the source no longer compiles automatically unless the corresponding libraries are added.

Resolution approach:

1. Identify the API/implementation used by the application.
2. Add dependencies compatible with the framework and target JDK.
3. Check the `javax.xml.bind` or `jakarta.xml.bind` namespace depending on the library/framework version.
4. Ensure the runtime has the required implementation/service provider, not just the API JAR.
5. Test actual marshaling/unmarshaling.
6. Record whether the dependency is packaged with the app or provided by the application server.

Do not automatically replace all `javax.*` imports with `jakarta.*`. That is an API change tied to library and framework versions, not a renaming rule applied to every `javax` package in the JDK. For instance, Java SE APIs such as `javax.net` or `javax.crypto` do not become Jakarta simply because the JDK is upgraded.

Other components such as Nashorn or JavaFX also require dedicated plans if the application depends on them. Running on the classpath does not prevent removed APIs from being absent from the runtime.

## 9. ServiceLoader and Plugin Architecture Without JPMS

Many systems use Java SPI:

~~~java
package com.example.spi;

public interface PaymentProvider {
    String name();
}
~~~

A provider:

~~~java
package com.example.card;

import com.example.spi.PaymentProvider;

public final class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }
}
~~~

In the classpath model, providers are typically declared via the file:

~~~text
META-INF/services/com.example.spi.PaymentProvider
~~~

Content:

~~~text
com.example.card.CardPaymentProvider
~~~

The application can load it:

~~~java
ServiceLoader<PaymentProvider> loader =
        ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : loader) {
    System.out.println(provider.name());
}
~~~

This mechanism remains useful on the classpath after upgrading the JDK. While not yet converted to named modules, declaring `uses` or `provides ... with` in `module-info.java` is not required.

However, service loading can fail if:

- `META-INF/services` resources are lost when building a fat JAR.
- The plugin JAR is not on the runtime classpath.
- The class loader used to locate providers cannot see the JAR.
- A plugin depends on a JDK internal API or a library that has changed.
- A library was moved to the module path without compatible SPI configuration.

When converting providers into true named modules, the `provides ... with` and `uses` mechanism becomes important. That is a separate scope requiring testing and does not have to be done in the same release as the JDK upgrade.

## 10. Context Class Loader, Application Servers, and Frameworks

A Java system does not always have just a single class loader. Servlet containers, application servers, plugin hosts, testing frameworks, and many other tools use hierarchies or separate class loaders to isolate applications.

Several issues tend to appear during migration:

- `Class.forName(...)` uses a class loader that cannot see the dependency.
- The thread context class loader (TCCL) differs from the loader that loaded the calling code.
- A serializer or SPI plugin is loaded via TCCL and misses resources.
- The same class has multiple copies loaded by different class loaders, leading to `ClassCastException`.
- The container provides a runtime library version different from the build version.
- A Java agent transforms bytecode, but the agent does not yet support the new JDK's class-file version.

Example:

~~~java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

Class<?> providerType =
        Class.forName("com.example.card.CardPaymentProvider",
                      true,
                      contextLoader);
~~~

This is an example illustrating a lookup dependent on a class loader; it is not advice to use reflection instead of `ServiceLoader`. When a framework has its own plugin architecture, follow that framework's contract.

You do not need to modularize the application to fix TCCL or dependency resolution bugs. You need to understand the class loading mechanism in use and verify both the packaging configuration and the actual runtime.

## 11. Building an Unmodularized Application with Gradle

A traditional Java application can keep `src/main/java` as is without creating `module-info.java`. In Gradle, select the appropriate JDK toolchain and target Java release:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

application {
    mainClass = 'com.example.orders.Main'
}
~~~

Meaning:

- Toolchain selects the compiler/JDK for tasks that support Java toolchains.
- `options.release = 17` constrains the source syntax, class-file target, and target Java SE API for the compiled code.
- Without `module-info.java`, the application still uses the classpath model.
- `mainClass` specifies the entry point without turning the application into a named module.

For code running on JDK 17, the Gradle wrapper and plugin versions in use must support JDK 17. Check the JDK used by the Gradle daemon, compiler toolchain, and test runtime; these values can differ depending on configuration.

A library with class files requiring Java 21 can still cause an application running on Java 17 to fail despite `options.release = 17`; this option does not automatically downgrade external dependencies to class-file target 17.

### 11.1. Inspecting the Dependency Graph

Reference commands:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Pay special attention to checking reflection, ORM, bytecode, logging, servlet, XML, serialization libraries, and database drivers. If there are differences between the compile and runtime classpaths, fix the dependency configuration before blaming JPMS.

## 12. Building with Maven Can Still Use the Classpath

With Maven, configure the compiler release without being forced to write a module descriptor:

~~~xml
<project>
    <!-- Other project configuration sections omitted -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

This is an illustrative configuration snippet, not a complete `pom.xml`. The Maven Compiler Plugin and the JDK compiler must support the corresponding release option.

If using plugins for testing, packaging, shading, bytecode weaving, or code generation, verify the compatibility of each plugin with the target JDK. For example, an outdated test runner plugin may fail to discover tests or fail to start the forked JVM; that is a toolchain error, not necessarily caused by the module system.

When the build output is an executable JAR or WAR, check the actual deployment runtime and how dependencies are provided. `java -jar` selects its entry point and classpath differently from running `java -cp ... Main` depending on the manifest/launcher; do not change the launch style at the same time as upgrading the JDK unless necessary.

## 13. Using jdeps to Survey Before Deciding on Modularization

`jdeps` is a useful static dependency analysis tool when surveying a Java system. It helps detect dependencies between packages/modules and certain accesses to JDK internal APIs.

Example:

~~~bash
jdeps --jdk-internals app.jar
~~~

If you also want to analyze library dependencies:

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

To inspect dependencies at the Java module level:

~~~bash
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Options must match the actual artifact format. If the JAR uses a multi-release structure, `--multi-release` with the appropriate release version may be needed to analyze the corresponding classes.

It is important to understand the limitations:

- `jdeps` does not fully detect class names constructed dynamically from strings.
- Reflection without static references can be missed.
- Resources/configs, service providers, and JNI/native dependencies are not fully modeled.
- Analyzing a single JAR does not prove the entire runtime classpath is correct.
- Analysis output does not replace integration tests on the target JDK.

If `jdeps` points out a `JDK internal API`, identify which library uses it, find replacement APIs and newer dependency versions instead of adding `--add-exports` en masse.

### 13.1. Other Supporting Tools

| Tool/command | Purpose |
|---|---|
| `java -version` | Check which JVM is actually running |
| `javac -version` | Check the compiler when needed |
| `java --list-modules` | List the modules provided by the runtime |
| `jar --describe-module --file lib.jar` | View module information of a JAR when applicable |
| `javap -verbose SomeClass` | Inspect the major version of a class file |
| `jdeprscan app.jar` | Find certain deprecated APIs in bytecode |
| `jdeps --jdk-internals app.jar` | Analyze certain dependencies on JDK internal APIs |

Do not treat `java --list-modules` as the list of modules being resolved for the application. It reports the modules available in the runtime image, whereas module resolution for a given run depends on the entry point and arguments.

## 14. Planning a Phased JDK Upgrade Without Forcing Modularization

A practical plan should minimize the number of changing variables in each step.

### Phase A — Capture a Baseline

Record:

- JDK vendor/version and JVM flags.
- Source code, commit, compiler release, and class-file target.
- Gradle/Maven wrapper, plugin versions, and dependency graph.
- Artifact structure, classpath, and deployment command.
- Critical functionalities, startup time, latency, and resource metrics.
- Any existing illegal reflective access or JDK internal API warnings.

If using JDK 8, you cannot obtain “JPMS warnings” from the old runtime because JPMS did not yet exist. Use static analysis, dependency release notes, and test runs on the new JDK to identify issues.

### Phase B — Upgrade Build Tools and Required Dependencies

Before or alongside the JDK migration, identify versions of frameworks, test runners, bytecode libraries, annotation processors, and drivers that support the new runtime. For outdated libraries, prioritize updates with official compatibility.

Document clearly when a dependency update alters application behavior, rather than mistaking every regression for a direct JDK impact.

### Phase C — Run on the Classpath on the New JDK

Keep the execution model:

~~~bash
java -cp "app.jar:lib/*" com.example.orders.Main
~~~

Verify startup, health, framework initialization, business flows, serialization, databases, message brokers, and external services. If using Spring Boot or a specialized launcher, keep the artifact's proper launcher instead of switching to the classpath command above just to “try JPMS”.

### Phase D — Handle Errors by Category

For each error, determine whether it arises from:

1. An API/class removed from the JDK.
2. Blocked reflection.
3. Bytecode too new for the JVM.
4. Incompatible library or dependency conflict.
5. Class loader, service provider, or resources.
6. Build/test plugin lacking JDK support.
7. Configuration and semantics changes in the framework/JDK.

Prioritize long-term compatibility solutions: upgrade libraries, replace internal APIs with public APIs, and add missing dependencies. Only use JVM module overrides selectively when a definitive fix is not yet possible.

### Phase E — Verify Stability

Run unit tests, integration tests, smoke tests, and a workload equivalent to the baseline. Inspect error logs and GC/resource metrics, and check for memory leaks, connection pools, and startup. Do not rely solely on the build exit code.

### Phase F — Evaluate JPMS Separately

Once the new runtime is stable, evaluate the practical benefits of named modules: API boundaries, application-level strong encapsulation, plugin architecture, `jlink`, or deployment requirements. Modularize only if the benefits and costs are justified.

## 15. Diagnostic Examples: Three Issues Easily Confused with Each Other

### Case 1: InaccessibleObjectException

Log:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Investigation direction: which library is performing deep reflection into `java.lang`? Does that version support the new JDK? Can the library be changed or a public API be used? If not yet, an `--add-opens` targeting the exact package can serve as a temporary workaround, and the risk and removal plan must be logged.

### Case 2: ClassNotFoundException with JAXB

Abbreviated log:

~~~text
java.lang.ClassNotFoundException: javax.xml.bind.JAXBContext
~~~

Investigation direction: does the application depend on JAXB previously provided by JDK 8? On JDK 11+, the corresponding API and implementation dependencies are required. `--add-opens` does not create a missing class. Also do not use `--add-modules java.xml.bind` if that module has already been removed from the current JDK.

### Case 3: UnsupportedClassVersionError

Log:

~~~text
java.lang.UnsupportedClassVersionError:
class file version 65.0; runtime recognizes versions up to 61.0
~~~

This is a Java 21 class file being loaded by Java 17. Investigation direction: which artifact or dependency was compiled with target 21; is the production runtime using the right target JDK; is it necessary to lower the compiler target or upgrade the runtime. This is not a JPMS package visibility error.

## 16. Decision Table: Using Flags, Changing Dependencies, or Modularizing

| Observation | Preferred action | What not to do |
|---|---|---|
| Legacy framework calls `sun.*` | Upgrade the framework or switch to a public API | Add `--add-exports` for all packages |
| Deep reflection error into the JDK | Upgrade the library, limit reflection; use a scoped `--add-opens` workaround if needed | Open entire modules unconditionally |
| JAXB/JAX-WS disappeared | Add compatible API/implementation dependencies | Use `--add-modules` for a module that no longer exists |
| Bytecode newer than runtime | Align target/toolchain/runtime/dependencies | Change package access flags |
| Service provider error | Check `META-INF/services`, TCCL, packaging | Force creating module-info.java |
| Split package on module path | Keep the classpath in the initial phase, then adjust dependencies/packages when modularizing | Move all JARs to the module path at once |
| Need modular runtime packaging | Analyze the module graph and evaluate `jlink` separately | Assume every fat JAR is a module |
| No module errors after JDK upgrade | Keep the current architecture if it meets requirements | Modularize just because the new JDK supports JPMS |

JVM flags remain a significant deployment change. If used, document the reason, error source, configuration location, applicable environments, and removal criteria. Flags passed to the JVM across CI, IDE, containers, launchers, and production must be consistent.

## 17. Compatibility Testing Without module-info.java

A test matrix can independently track these evidence layers:

| Test layer | Question | Evidence |
|---|---|---|
| Build tool | Do Gradle/Maven and plugins support the new JDK? | Build logs and tool versions |
| Compiler | Are source and API targets correct? | `--release`, compile report |
| Bytecode | Are classes/JARs compatible with the runtime? | `javap`, dependency metadata |
| Startup | Does the runtime load and initialize the application? | Startup logs, health checks |
| Reflection | Do frameworks/ORM/serializers work? | Integration tests, no inaccessible access |
| Class loading | Are SPIs/plugins/resources found? | ServiceLoader tests, package/dependency report |
| Functional | Do outputs and data preserve semantics? | Test cases, data reconciliation |
| Performance | Are there significant regressions? | Latency, throughput, CPU, memory baseline |
| Deployment | Do images/scripts use the right JDK and flags? | Deployment manifest, `java -version` |

If running the application on multiple JDKs during a transition period, test each declared supported JDK. Building an application with a newer JDK does not prove it runs on every older JDK unless source, bytecode, Java SE APIs, and dependencies are all compatible.

You must also verify that tests are running on the exact target JVM. The Gradle compile toolchain and test launcher can be different JVMs if configuration is inconsistent.

## 18. Limitations of the “Just Keep the Classpath” Approach

Keeping the classpath reduces modularization work, but does not automatically solve the following issues:

- Dependency conflicts and duplicate classes.
- Class loader leaks, classpath ordering, and resource collisions.
- Reflection permissions into JDK internals.
- Removed APIs or changed semantics.
- Plugins/test runners lacking support for newer Java.
- Building an optimized runtime image based on the module graph.
- The ability to declare strong encapsulation between application packages.

If there is a need to strictly control dependencies and public APIs at the module level, named modules are an architectural option worth considering. However, a safe migration can complete the **JDK upgrade** phase first and plan the **transition to JPMS** afterward.

If the application uses only the classpath and a few libraries require module overrides, verify the runtime of each service individually rather than applying a shared set of flags across the entire system. This reduces the exposed permission surface and improves traceability.

## 19. When Should You Plan a Full Migration to JPMS?

Modularization can bring benefits when a system:

- Wants a clear dependency graph and API boundaries.
- Has internal libraries that need to expose stable interfaces.
- Needs to package a custom runtime image via the module system.
- Is newly designed around module boundaries.
- Has a team capable of handling the module path, split packages, and compatible dependencies.

Practical costs include:

- Creating and maintaining `module-info.java` for modules.
- Defining `requires`, `exports`, `opens`, and `uses/provides`.
- Handling unmodularized dependencies or unstable automatic module names.
- Resolving split packages and package-private access across modules.
- Testing reflection, serializers, DI, ORM, service loaders, and test frameworks.
- Adjusting packaging, IDE, CI, and deployment commands.

If the team decides to modularize, do so one well-bounded module at a time, run the test suite, and change only one part of the architecture per phase. Not all libraries and application services need to become named modules immediately.

## 20. Migration Log Template Without JPMS Transition

A short report may record:

~~~yaml
system: orders-service
before:
  jdk: "8"
  launchMode: classpath
  namedApplicationModules: false
after:
  jdk: "17"
  launchMode: classpath
  namedApplicationModules: false
build:
  compilerRelease: 17
  dependencyReview: completed
compatibility:
  jdkInternalsScan: completed
  removedApisReview: completed
  reflectiveAccessTests: completed
  startupTests: passed
  businessFlows: passed
  performanceBaselineCompared: true
temporaryJvmOverrides: []
decision:
  jpmsMigration: deferred
  rationale: "JDK migration completed separately; no current module boundary requirement"
~~~

This is a **structural template**, not actual test data. Values such as `passed` or `completed` should only be recorded when the team has actually executed the corresponding step. If an `--add-opens` workaround is needed, record the package, root cause, environment scope, and removal ticket under `temporaryJvmOverrides`.

## 21. Concluding Principles

- Upgrading the JDK and moving the entire application to JPMS are not the same task.
- Traditional applications can still run on the classpath after Java 9 without `module-info.java`.
- Classpath code resides in unnamed modules yet must still obey the package boundaries of JDK named modules.
- `--add-opens` supports deep reflection; `--add-exports` supports accessing public APIs in unexported packages. Do not use them indiscriminately or treat them as long-term solutions.
- Removed APIs/JDK modules cannot be restored merely via module flags; dependencies or replacement mechanisms are required.
- Do not inadvertently move JARs from the classpath to the module path during the same JDK upgrade step without a plan to handle the module graph.
- Class loaders, ServiceLoader, reflection, and dependencies must still be tested on the target runtime.
- `jdeps` and static tools are very helpful, but they cannot replace startup/integration tests.
- The roadmap can be split into two milestones: **runtime upgrade first**, **modularization later** if there is a real need.

A Java Compatibility Migration can succeed while the application still does not use named modules. The goal of the JDK upgrade phase is to ensure that source code, dependencies, bytecode, frameworks, and runtime behavior are compatible with the new JDK. Once this scope is stabilized with complete test evidence, the team can decide whether to move all or part of the application to JPMS or continue operating on the classpath according to product requirements.