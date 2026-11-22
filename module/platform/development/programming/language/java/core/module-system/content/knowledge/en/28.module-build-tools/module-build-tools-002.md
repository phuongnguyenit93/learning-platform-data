# Module path in Gradle Java Plugin

## 1. Gradle and JPMS address two different dependency layers

The Gradle Java Plugin orchestrates compiling, testing, and packaging Java applications. The Java Platform Module System (JPMS), by contrast, defines how **named modules** read one another, which packages are exported, which packages are opened for reflection, and which modules are resolved when the program runs.

Therefore, in a Gradle project using JPMS, two complementary ways of describing dependencies exist:

1. **Gradle dependencies**: declared with implementation, api, compileOnly, runtimeOnly, or project(...), helping Gradle fetch artifacts and place them into the appropriate configurations.
2. **JPMS dependencies**: declared in module-info.java with requires, requires transitive, exports, opens, uses, and provides, helping javac/JVM construct the module graph and verify access permissions.

Gradle does not automatically generate requires simply because you wrote implementation. Conversely, writing requires in module-info.java does not cause Gradle to automatically download dependencies from a Maven repository if the required dependency has not been declared.

The goal of this lesson is to understand how the Gradle Java Plugin determines the **module path**, how to organize a modular project, and how to troubleshoot errors that arise when dependencies are mistakenly placed on the classpath.

## 2. How does the module path differ from the classpath?

On the traditional classpath, the compiler and JVM locate classes from directories or JARs. Code on the classpath belongs to the **unnamed module** of the corresponding class loader, has no module-info.java, and does not use requires to describe dependencies.

With the module path, the compiler and JVM can locate named modules:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

A named module has an explicit name and a descriptor describing its relationships with other modules:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

For app to import public types from catalog, not only must it read catalog via requires, but catalog must also export the package containing those types.

In Gradle, both the classpath and the module path can be constructed from dependency configurations. **What decides is which arguments Gradle passes the artifacts as to javac or the JVM**, not merely the fact that developers name configurations compileClasspath or runtimeClasspath.

## 3. Source structure of a named module in a Gradle project

The Gradle Java Plugin reads main sources from src/main/java and test sources from src/test/java by default. For a named module, place module-info.java at the root of the main source set:

~~~text
catalog/
  build.gradle
  src/
    main/
      java/
        module-info.java
        com/acme/catalog/api/Catalog.java
    test/
      java/
        com/acme/catalog/api/CatalogTest.java
~~~

Example descriptor:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

And public API:

~~~java
package com.acme.catalog.api;

public final class Catalog {
    private Catalog() {
    }

    public static String title() {
        return "Java Modules";
    }
}
~~~

Another application wanting to use Catalog must read com.acme.catalog and must have access to the package com.acme.catalog.api. The Gradle project name, JAR filename, and JPMS module name can differ; **the module name is the name declared after the module keyword** in module-info.java.

## 4. Enabling module-path inference in Gradle

Gradle supports inferring which dependencies belong on the module path via the Java plugin extension:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}
~~~

In modern Gradle versions, module-path inference is usually enabled by default for the Java Plugin; declaring it explicitly makes the build intent clear.

When a source set contains module-info.java and inference is enabled, Gradle can configure javac to compile it as a named module. For JAR dependencies, Gradle relies on module metadata evidence to select the module path, specifically:

- JAR with module-info.class: **explicit named module**.
- JAR with Automatic-Module-Name in MANIFEST.MF: has a stable automatic module name and can be recognized by Gradle for the module path.
- JAR with neither indicator: Gradle may keep it on the classpath, even though the JVM could derive an automatic module name if the JAR were intentionally placed on the module path.

The difference between **the JVM being able to treat a JAR as an automatic module** and **Gradle automatically deciding to put the JAR on the module path** is the easiest point to misunderstand. Do not assume every implementation library automatically appears in the module graph.

If an application encounters module not found, check the JAR metadata and how Gradle classifies the artifact first. Do not resolve it by randomly copying JARs into source folders.

## 5. Practical example: Gradle multi-project with two JPMS modules

We create a build consisting of:

- Gradle project :catalog, producing named module com.acme.catalog.
- Gradle project :app, producing named module com.acme.app.
- Module app reads catalog and calls catalog's public API.

Structure:

~~~text
demo/
  settings.gradle
  catalog/
    build.gradle
    src/main/java/
      module-info.java
      com/acme/catalog/api/Catalog.java
  app/
    build.gradle
    src/main/java/
      module-info.java
      com/acme/app/Main.java
  gradlew
  gradlew.bat
~~~

In settings.gradle:

~~~groovy
rootProject.name = 'jpms-gradle-demo'
include 'catalog', 'app'
~~~

Gradle project paths :catalog and :app are identifiers within the build. JPMS does not require using those exact two names as module names.

## 6. Configuring a library module with java-library

File catalog/build.gradle:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}
~~~

The java-library plugin extends the Java Plugin and adds the api configuration, used when a library has dependencies that appear in the library's own public API.

File catalog/src/main/java/module-info.java:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

File Catalog.java:

~~~java
package com.acme.catalog.api;

public final class Catalog {
    private Catalog() {
    }

    public static String title() {
        return "Java Modules";
    }
}
~~~

Gradle compiles the Java source and module descriptor, producing module-info.class in the output. When packaged with the jar task, the descriptor is placed in the modular JAR along with the other classes.

A module does not need to write requires java.base: every named module has implicit readability to java.base.

## 7. Configuring an application with the Application Plugin

File app/build.gradle:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

dependencies {
    implementation project(':catalog')
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

The Application Plugin applies the Java Plugin and provides the run task along with launcher configuration. When mainModule and mainClass are defined, Gradle has the information to run the modular application appropriately.

File app/src/main/java/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

File app/src/main/java/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.catalog.api.Catalog;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Catalog.title());
    }
}
~~~

Here is the key point to remember:

- implementation project(':catalog') tells **Gradle** that app needs the artifact from the catalog project.
- requires com.acme.catalog tells **JPMS** that module app reads the named module catalog.
- exports com.acme.catalog.api allows app to use public types in catalog's API package.

Missing any one of these key conditions can cause compilation to fail. Gradle's dependency configurations do not replace the module descriptor.

## 8. Compiling and running the modular application

In the demo directory, run:

~~~bash
./gradlew clean :app:compileJava
./gradlew :app:run
~~~

On Windows:

~~~powershell
.\gradlew.bat clean :app:compileJava
.\gradlew.bat :app:run
~~~

Expected application output:

~~~text
Java Modules
~~~

You can build everything:

~~~bash
./gradlew build
~~~

Or package individual modules:

~~~bash
./gradlew :catalog:jar :app:jar
~~~

Output typically includes:

~~~text
catalog/build/classes/java/main/module-info.class
catalog/build/classes/java/main/com/acme/catalog/api/Catalog.class
catalog/build/libs/...

app/build/classes/java/main/module-info.class
app/build/classes/java/main/com/acme/app/Main.class
app/build/libs/...
~~~

The final JAR name may include the project name, version, or archive configuration. Inspect the exact actual artifact; do not guess the JAR name based solely on the module name.

The Application Plugin can also provide installDist and distZip tasks to create a distribution. Run and verify the actual startup script of the distribution because that is how the program will launch outside Gradle.

## 9. Gradle infers the module path, but does not auto-fix descriptors

Module-path inference helps Gradle decide where dependencies go when passing them to the compiler/runtime. It does not automatically:

- Write requires into module-info.java.
- Export packages you did not declare.
- Open packages for deep reflection.
- Turn legacy JAR dependencies into explicit modules.
- Register service providers in place of uses and provides.
- Resolve dependency cycles or split packages.
- Turn a JAR on the classpath into a named module if Gradle does not recognize module metadata.

If app contains:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

but app/build.gradle does not declare a dependency on catalog, Gradle will not necessarily include catalog in the compile task.

Conversely, if build.gradle has implementation project(':catalog') but module-info.java lacks requires com.acme.catalog, the compiler can still report that module app does not read module catalog.

**Treat Gradle dependency declarations and JPMS dependency declarations as two maps that must stay consistent.**

## 10. api, implementation, and requires transitive

In a library module, dependency types should be distinguished by their API role.

For example, module com.acme.reports has a public method returning a type belonging to module com.acme.models:

~~~java
package com.acme.reports.api;

import com.acme.models.api.ReportModel;

public interface ReportService {
    ReportModel generate();
}
~~~

If consumers read reports and use ReportModel in the public signature, the descriptor can use:

~~~java
module com.acme.reports {
    requires transitive com.acme.models;
    exports com.acme.reports.api;
}
~~~

In the Gradle build for reports, use java-library:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':models')
}
~~~

The two declarations play related but non-identical roles:

- api tells Gradle that the dependency is part of the library's API surface and must be exposed to Gradle consumers.
- requires transitive tells JPMS that modules reading reports are also granted readability to models.

If a dependency is only used inside the implementation, typically choose implementation in Gradle and regular requires in module-info.java:

~~~groovy
dependencies {
    implementation project(':internal-helpers')
}
~~~

~~~java
module com.acme.reports {
    requires com.acme.internal.helpers;
    exports com.acme.reports.api;
}
~~~

Do not automatically replace every implementation with api or every requires with requires transitive. Check which types actually appear in the public contract.

## 11. Distinguishing compileClasspath and runtimeClasspath from the module path

Gradle has familiar configurations:

| Configuration | Typical role |
|---|---|
| implementation | Dependency needed to compile the module and usually present at runtime |
| api | Dependency exposed through the library's API when using java-library |
| compileOnly | Needed only at compile time, not automatically carried to runtime |
| runtimeOnly | Not needed for direct compilation, but required at runtime |
| testImplementation | Dependency for test compilation/execution |
| testRuntimeOnly | Dependency needed only when running tests |

The names compileClasspath or runtimeClasspath in Gradle remain **dependency configuration** concepts. They do not mean all artifacts in them will be passed verbatim to the --class-path flag of javac/java.

When module-path inference is active, Gradle separates dependencies recognized as modules from libraries that remain on the classpath. Thus, a Gradle command may print a compileClasspath that still includes dependencies that are organized onto the module path when invoking javac.

To inspect dependency resolution from Gradle's perspective:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

To find out why a specific version of a dependency was selected:

~~~bash
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency some-library
~~~

These commands help locate artifacts and versions. However, to know which classpath/module path the compiler received, you still need to inspect the compile task and module metadata.

## 12. Automatic modules and unmodularized JAR libraries

A JAR without module-info.class can still become an automatic module if placed on the module path. The JVM can derive a module name from the JAR filename, whereas Gradle will not necessarily choose to place it on the module path if the JAR lacks stable identifying metadata.

Some libraries support the manifest entry:

~~~text
Automatic-Module-Name: com.acme.legacy
~~~

This entry provides a stable module name when the JAR is used on the module path, but **does not turn the JAR into an explicit module**.

To inspect artifact metadata:

~~~bash
jar --describe-module --file libs/legacy.jar
~~~

For external libraries, prefer:

1. A newer version with an appropriate module-info.class.
2. A version with a stable Automatic-Module-Name if a transition phase is needed.
3. Replacing the library or adjusting architecture if it cannot be used safely on the module path.

Do not randomly rename JARs just to make a module name temporarily match requires, because upgrading the artifact can break the configuration. Do not assume Gradle will move a classpath JAR to the module path just because you added a guessed name in requires in the descriptor.

## 13. Why can't a named module automatically read libraries on the classpath?

A common migration issue:

- app is an explicit named module with module-info.java.
- lib-old.jar has no module metadata, so Gradle keeps it on the classpath.
- app tries to requires a module name guessed from the name lib-old.jar.

At compile time, javac may report module not found because the dependency is not on the module path under that name. If app directly references a class belonging to the unnamed module, standard JPMS module readability also does not allow a named module to depend on the unnamed module as a valid named dependency.

The solution is not adding classpath paths into module-info.java. You can:

- Upgrade the dependency to a modular version or one with stable module metadata.
- Keep the unready part of the application on the classpath until dependencies are standardized.
- Separate an adapter or process boundary to reduce direct dependencies.
- Use controlled manual module-path configuration in a short-term migration step, backed by real tests.

Converting a legacy library into an automatic module does not automatically solve all of its issues: split packages, reflection, resources, and service discovery must still be verified.

## 14. Evaluating split packages and dependency cycles

The classpath allows multiple JARs to own classes in the same package. With JPMS, when the module graph creates a package conflict between modules in a readability relationship, compilation or resolution can fail.

Example:

~~~text
library-a.jar: com/acme/shared/Alpha.class
library-b.jar: com/acme/shared/Beta.class
~~~

If these are two independent modules sharing the package com.acme.shared, consider:

- Merging classes that genuinely belong to one logical module.
- Separating packages according to each module's responsibility.
- Upgrading to a library version where the vendor fixed the split package.
- Inspecting shaded JARs because build tools can inadvertently create new split packages.

If two modules requires each other in a cycle, the module graph is also invalid by JPMS design. Break the cycle by extracting an API interface, inverting the dependency direction, or merging modules along proper boundaries.

Gradle can order compile tasks according to project dependencies, but **Gradle's task graph does not make a JPMS requires cycle valid**.

## 15. Inspecting the JavaCompile task and compiler arguments

When encountering module not found or package not visible errors, you need to see how Gradle invokes javac.

A first step:

~~~bash
./gradlew :app:compileJava --info
~~~

For more detailed logs, you can use:

~~~bash
./gradlew :app:compileJava --debug
~~~

Output from different Gradle/toolchain versions may vary, and may not necessarily print every compiler argument on a single easily readable line. If specific inspection is needed, use build diagnostics or project-scoped logging to inspect compiler options and files classified onto the module path.

Points to confirm:

- module-info.java exists in the source set actually being compiled.
- modularity.inferModulePath is enabled.
- The right JDK/toolchain is used for JavaCompile.
- Dependencies have module-info.class or Automatic-Module-Name when Gradle needs to recognize them.
- The source module name in requires matches the dependency's module name.
- The required package is exported by the dependency.

If the compiler cannot find a module, do not add --add-exports before confirming the artifact is present on the module path. Exporting only resolves package access, not missing modules.

## 16. Java Toolchains and --release

Use a toolchain to pin the compile JDK:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}
~~~

If you need to produce Java 17-compatible bytecode while compiling on a JDK supporting that target:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

The toolchain selects the JDK used to run the compiler; --release specifies the language level, class-file format, and platform APIs matching the target release. They are not the same setting.

If running CI or the application runtime on Java 17, verify that dependencies are compiled compatibly and the module descriptor does not require APIs introduced only in newer Java versions.

Using module-info.java requires Java 9 or later. You cannot use --release 8 with a source module descriptor under normal JPMS compilation.

## 17. Configuring application execution by module identity

With the Application Plugin:

~~~groovy
application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

You can run:

~~~bash
./gradlew :app:run
~~~

And build a distribution:

~~~bash
./gradlew :app:installDist
~~~

After building, if you want to verify manually with the Java launcher, use only the actual generated JARs and verify the module names:

~~~bash
jar --describe-module --file catalog/build/libs/catalog.jar
jar --describe-module --file app/build/libs/app.jar
~~~

If the actual JAR files have a version suffix, replace the paths above with the exact filenames in build/libs. Then use the module path with the corresponding JARs:

~~~bash
java --module-path "catalog/build/libs:app/build/libs" \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

On Windows, replace the path separator with a semicolon and use shell-appropriate command formatting.

The --show-module-resolution output helps inspect which modules were resolved; however, by itself it does not prove that every provider or dynamically loaded class has been discovered.

## 18. Testing on the module path requires separate attention

A modular application may compile main sources successfully while tests fail due to different test structuring:

- Test classes sit on the classpath rather than in the same named module as production classes.
- Frameworks use deep reflection to instantiate test objects or access private members.
- Tests need to access unexported implementation packages.
- Some test frameworks have automatic module names or module metadata different from expectations.

Gradle test configuration cannot be mechanically inferred solely from the main source set. For integration tests, verify whether the test JVM actually uses the module path or classpath and which module the test code is loaded into.

For example, when a test framework needs deep reflection, you may have to configure intentional JVM args:

~~~groovy
tasks.named('test', Test) {
    jvmArgs '--add-opens=com.acme.catalog/com.acme.catalog.internal=ALL-UNNAMED'
}
~~~

This is only an example of a situation that might be used during migration; it only works if the package and module actually exist, are present in the graph, and the test code is in the unnamed module. Do not add broad opens without knowing which caller needs it. When tests are in a named module, the target of opens can be the test framework module name or another appropriate module.

## 19. Reflection, resources, and ServiceLoader

When moving dependencies onto the module path, runtime access can differ from the old classpath.

**Reflection:** A package exported for regular code access is not automatically opened for deep reflection. Serialization/ORM frameworks may need qualified opens:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.fasterxml.jackson.databind;
}
~~~

The name com.fasterxml.jackson.databind must match the library's actual module identity. If using a different library version or an unmodularized JAR, re-verify before writing the descriptor.

**Resources:** ClassLoader.getResource and Class.getResource can yield different results when resources live in encapsulated packages. Test with the exact packaging and class loader used in production.

**ServiceLoader:** The consumer declares uses; the provider declares provides ... with ...:

~~~java
module com.acme.app {
    requires com.acme.catalog;
    uses com.acme.catalog.api.CatalogProvider;
}
~~~

Provider module:

~~~java
module com.acme.catalog.provider {
    requires com.acme.catalog;
    provides com.acme.catalog.api.CatalogProvider
        with com.acme.catalog.provider.DefaultCatalogProvider;
}
~~~

Merely adding a runtimeOnly dependency does not guarantee that a service provider is resolved and loaded in every configuration. Verify that the provider module is included in the runtime graph or appropriate service binding is configured, and test ServiceLoader with the real release artifacts.

## 20. Annotation processing and code generation

The Gradle Java Plugin has the annotationProcessor configuration for processor libraries:

~~~groovy
dependencies {
    annotationProcessor 'com.example:some-processor:1.0'
}
~~~

This is a configuration for running annotation processors during compilation; it is not by default a module dependency of the application code.

If a processor is a named module, the Java compiler also has dedicated module path mechanisms for processors. However, how Gradle provides the processor path and module path depends on toolchain/plugin configuration. Do not simply add requires to the processor module just to trigger annotation processing.

When code generation creates classes in a package of a named module, verify that generated sources are compiled in the right module, without inadvertently creating split packages or mis-mapped source paths.

Projects using Lombok, MapStruct, or custom processors should test the compiler task on the real module path rather than relying solely on IDE results.

## 21. jlink and Gradle's module path are not the same thing

Module-path inference helps Gradle compile and run named modules. It **does not automatically mean** the Java Plugin has created a custom runtime image.

If you want to use jlink, you typically need to:

1. Build explicit modular JARs for the application and linkable dependencies.
2. Provide JDK jmods and application modules on jlink's module path.
3. Select roots with --add-modules.
4. Consider --bind-services if service providers are needed.
5. Verify the final image with image/bin/java --list-modules and run integration tests.

An automatic module can be used as a bridge on the module path during migration, but it is not a suitable explicit-module input for direct linking as an application module with jlink.

If the build needs to automate jlink, use dedicated workflows/tasks/plugins and test on the target environment. Do not expect the jar or build tasks of the Java Plugin to automatically create a runtime image.

## 22. Symptoms and diagnostic guide

| Symptom | Common cause | Where to check |
|---|---|---|
| module not found: X | Dependency is not on the module path or module name mismatches | Check jar --describe-module, Gradle dependencies, and compiler args |
| package ... is not visible | Missing requires/readability or package not exported | Check module-info.java of consumer and provider |
| Cannot read unnamed module | Named module depends on code still on the classpath | Review library modularity and Gradle inference |
| Split package conflict | Multiple modules use the same package | Audit JARs, rename/merge packages, or upgrade dependencies |
| Tests throw InaccessibleObjectException | Deep reflection into an unopened package | Check opens and actual target module |
| Code runs in IDE but fails in Gradle | IDE and Gradle select different classpath/module path or JDK | Run Gradle wrapper, check toolchain and compile task |
| Compiles but throws NoClassDefFoundError at runtime | Missing runtime dependency/module, or different class loader | Check runtimeClasspath, module resolution, artifacts |
| ServiceLoader finds no provider | Provider module not resolved or registration missing | Check uses/provides, runtime graph, module metadata |
| Resource returns null after migration | Resource lookup differs by module/class loader | Check resource packaging and module encapsulation |
| Build succeeds but jlink fails | Dependency is not an explicit module yet or JMOD/module missing | Check jlink's separate module graph |

Do not try to solve all symptoms with --add-exports or --add-opens. Those flags only alter partial access permissions; they do not fix missing dependencies, wrong module names, or package ownership.

## 23. Process for migrating a Gradle project to the module path

An effective practical sequence:

1. **Establish a baseline:** build and test the working classpath project, pinning the JDK and Gradle Wrapper.
2. **Audit dependencies:** run dependencies, dependencyInsight, and use jdeps to identify JDK modules and internal APIs.
3. **Evaluate JARs:** check for explicit module-info.class, Automatic-Module-Name, and actual module names.
4. **Design module boundaries:** separate API packages from implementations, eliminating split packages and dependency cycles.
5. **Start with a small module:** add module-info.java to a library with few dependencies.
6. **Enable inference explicitly:** configure modularity.inferModulePath for the project or source set being migrated.
7. **Synchronize declarations:** Gradle dependencies for artifacts and requires/exports in the descriptor.
8. **Build via wrapper:** run compileJava, test, jar, and check the module-info.class output.
9. **Migrate the main application:** set mainModule and mainClass in the Application Plugin.
10. **Verify runtime:** run Gradle run, the distribution startup script, and the Java launcher with --show-module-resolution.
11. **Handle dynamic access:** test reflection, resources, ServiceLoader, annotation processors, and class loaders.
12. **Release incrementally:** document temporary migration flags, test on the target JDK, and keep a rollback plan.

You do not need to move every dependency to the module path immediately if they are not ready. Clear module boundaries, minimal temporary flags, and a stable build are usually more valuable than moving many JARs at once.

## 24. Checklist before packaging and release

- [ ] JDK toolchain and Gradle Wrapper are pinned.
- [ ] Main source has module-info.java in the right location.
- [ ] modularity.inferModulePath is intentionally configured.
- [ ] Gradle dependencies align with requires in the module descriptor.
- [ ] Actual module names of key JARs have been verified.
- [ ] Public APIs reside in appropriately exported packages.
- [ ] No unresolved split packages or requires cycles remain.
- [ ] Unmodularized dependencies are categorized with a migration plan.
- [ ] Application Plugin uses the right mainModule and mainClass.
- [ ] Test tasks run under a JPMS-compatible configuration.
- [ ] Reflection and resource access have been tested in a real runtime environment.
- [ ] ServiceLoader discovers providers as expected.
- [ ] Final JAR artifacts contain module-info.class and required dependencies.
- [ ] Startup scripts/distributions use the correct module graph.
- [ ] If creating a runtime image, the graph for jlink was verified separately.
- [ ] Tested on the target JDK and OS, not only passing inside the IDE.

## Conclusion

**The module path in the Gradle Java Plugin** is the result of Gradle inferring or configuring where dependencies are placed when the compiler and JVM process a JPMS application. Having module-info.java and enabling modularity.inferModulePath helps Gradle handle named modules better, but Gradle cannot construct a valid module graph on its own if dependency descriptors, package visibility, or module metadata are misaligned.

In a stable modular build, Gradle supplies the right artifacts, the JPMS descriptor declares the right readability and package access, and the Application Plugin launches using the right module name. Verify those three layers together—especially with automatic modules, test frameworks, ServiceLoader, and legacy libraries—to migrate from the classpath to the module path under full control.
