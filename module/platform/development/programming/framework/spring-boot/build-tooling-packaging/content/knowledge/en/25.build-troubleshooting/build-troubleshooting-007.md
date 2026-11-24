# Diagnosing ClassNotFoundException, NoClassDefFoundError, and NoSuchMethodError

## Goal and Scope

A Spring Boot application can **compile and pass tests** yet still fail on startup, when Spring creates beans, when a request hits a rarely used code path, or only when running from an executable JAR/container. Three errors commonly lumped together as “missing library” are:

- `ClassNotFoundException` — an operation asks to load a class by its string name, and the classloader cannot find its definition.
- `NoClassDefFoundError` — the JVM/classloader needs a class definition during linking or execution, yet cannot find the class referenced by bytecode; sometimes this appears after a prior class initialization failure.
- `NoSuchMethodError` — the class is found, but the version loaded at runtime lacks the method the caller was compiled against.

All three relate to class loading/linking, yet they point to **three distinct kinds of mismatch**. Choosing the right investigation path avoids adding duplicate dependencies, upgrading versions randomly, or wiping caches without fixing the cause.

After this lesson, you will be able to:

1. Distinguish checked exceptions from linkage errors and read the first exception in a stack trace.
2. Explain compile classpath, runtime classpath, transitive dependencies, classloaders, and binary compatibility.
3. Independently reproduce all three errors with Java 17+.
4. Use Gradle `dependencies`/`dependencyInsight` and Maven `dependency:tree` to locate the actually selected dependency.
5. Inspect executable Spring Boot JARs, `BOOT-INF/classes`, `BOOT-INF/lib`, manifests, and classpath ordering.
6. Identify issues caused by missing artifacts, dependency scopes, version skew, duplicate classes, reflection, ServiceLoader, static initializers, or classloader isolation.
7. Verify fixes using the exact artifact, JRE, command, and container matching the deployment environment.
8. Establish dependency alignment, locks/constraints, CI smoke tests, and release workflows to prevent recurrence.

**Context:** Java 17+, Spring Boot 3.x (examples compatible with the 3.3 line), Gradle 8.x, or Maven 3.x. Commands assume JDK 17 with `java`, `javac`, `jar`, `javap`, and `jdeps`; substitute paths and module names per your actual project.

---

## 1. Class Loading and Linking Map

### 1.1 From Source to Runtime

When compiling an application, the compiler must find classes referenced by source code. At runtime, the JVM must find the corresponding classes and methods from **the files actually present on the runtime classpath/module path**.

```text
Java source
    |
    v
Compile classpath
  JDK + compile dependencies
    |
    v
.class bytecode
    |
    v
Package artifact
  plain JAR / Spring Boot executable JAR / WAR
    |
    v
Runtime classpath or module path
  application classes + runtime dependencies
    |
    v
ClassLoader: load -> link -> initialize
    |
    v
Method invocation / object creation / reflection
```

A successful build only proves the compiler saw the required types on the compile classpath. It **does not prove** those dependencies were packaged into the runtime artifact, nor does it prove the runtime loads the right version.

For example: a project declares a library as `compileOnly`, compiles code calling the library cleanly, yet the executable JAR does not carry that library. Or the app compiles against API v2 while the container loads API v1. These two scenarios produce different errors.

### 1.2 Three Easily Confused Stages

- **Loading:** finding bytecode and creating a `Class` object for a class name via a classloader.
- **Linking:** verifying bytecode, preparing runtime data, and resolving symbolic references to classes, fields, and methods.
- **Initialization:** executing static field initializers and static initializer blocks of the class.

The JVM may defer certain resolution operations until the code is actually reached. Thus, an application can start up and only throw `NoClassDefFoundError` or `NoSuchMethodError` on a specific request.

### 1.3 Classpath Is Not Just the Dependency List in the Build File

A build file may contain:

- Direct dependencies declared by the team.
- Transitive dependencies pulled in by other libraries.
- Compile-only dependencies.
- Test-only dependencies.
- Dependencies provided by an external container.
- Multiple versions or multiple artifacts containing the same class name.

What must be investigated is the **resolved runtime graph** and the **final packaged artifact**, not just direct dependency lines in source.

---

## 2. Comparing the Three Errors

| Error | Nature | Usually Occurs When | First Signal to Inspect |
| --- | --- | --- | --- |
| `ClassNotFoundException` | Checked exception, extends `ReflectiveOperationException` | `Class.forName`, `ClassLoader.loadClass`, or loading a class by name | Requested class name and which classloader is searching |
| `NoClassDefFoundError` | `Error`, extends `LinkageError` | JVM needs a class definition when instantiating/calling code or resolving a reference | Which class is missing; whether message says “Could not initialize class” |
| `NoSuchMethodError` | `Error`, extends `IncompatibleClassChangeError` | Compiled bytecode invokes a method absent from the loaded runtime class | Method signature, actually loaded class, and JAR version |

### 2.1 `ClassNotFoundException`

The Java API defines this exception as thrown when an application tries to load a class by **String name** via `Class.forName`, `ClassLoader.findSystemClass`, or `ClassLoader.loadClass`, and no matching definition is found.

It is a checked exception. Code using reflection can catch it and handle an absent plugin gracefully:

```java
try {
    Class<?> pluginType = Class.forName("com.example.plugins.CsvPlugin");
    System.out.println("loaded=" + pluginType.getName());
} catch (ClassNotFoundException ex) {
    System.err.println("Plugin class is unavailable: " + ex.getMessage());
}
```

Common causes:

- Fully-qualified name has wrong package, casing, or typo.
- Plugin JAR has not been added to the classpath.
- Class exists on the compile classpath but not on the runtime classpath.
- Code uses the wrong classloader (e.g., system classloader in an app with nested JARs).
- Module/plugin is deployed in a location different from where the loader searches.
- Class name is loaded from config, database, or service registry with a stale value.

### 2.2 `NoClassDefFoundError`

This is a `LinkageError`. The JVM or a classloader needs to load a class definition while executing a method call, creating an instance, or resolving a reference, and cannot find the class definition. Typically, the class existed when the caller was compiled, but is absent at runtime.

Example message:

```text
java.lang.NoClassDefFoundError: com/vendor/payment/PaymentClient
```

Do not search only for the class on the first line. A class may exist while **a dependency that class itself requires** is missing. Inspect the entire cause chain and stack trace to find where the JVM first attempted to load the type.

A special case:

```text
java.lang.NoClassDefFoundError: Could not initialize class com.example.config.DatabaseSettings
```

The class was found, yet a previous initialization failed inside its static initializer. The first error is usually an `ExceptionInInitializerError` with the real cause (e.g., reading config, missing environment variable, parse error, or an exception in a static block). The JVM marks that class uninitializable in the current classloader; subsequent uses report `NoClassDefFoundError`. Find the **first initialization failure**, rather than blindly editing the classpath.

### 2.3 `NoSuchMethodError`

This is a `LinkageError` occurring when a caller invokes a method that the runtime class no longer defines. The compiler normally catches this if all sources compile against the same API. It surfaces at runtime when **the binary was compiled against a different version of a class** than the one loaded.

Example:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.vendor.Client.execute(java.lang.String, int)'
```

The caller may have been compiled against `vendor-client 2.x`, while runtime loads `vendor-client 1.x` lacking the `execute(String, int)` overload. Or the dependency tree picked an older transitive version, a shaded JAR containing older classes precedes the newer JAR, or the app deployed with a different library version than CI used.

In bytecode, a method signature comprises its name and descriptor (parameter types, return type). Changing parameters, changing the return type, or deleting a method can break binary compatibility. Changing static/instance can trigger another `IncompatibleClassChangeError` subtype; do not assume every mismatch manifests strictly as `NoSuchMethodError`.

### 2.4 Do Not Confuse with Similarly Named Errors

| Error | Different Meaning |
| --- | --- |
| `NoSuchMethodException` | Checked exception when reflection looks up a method via APIs like `Class.getMethod`; not `NoSuchMethodError` |
| `NoSuchFieldError` | Bytecode references a field absent from the runtime class |
| `IncompatibleClassChangeError` | Binary structure incompatibility, e.g., static/instance or class/interface change |
| `UnsupportedClassVersionError` | JVM is too old for the class file version |
| `ClassCastException` | Can happen when the same class name is loaded by two different classloaders; not necessarily a missing JAR |
| `ExceptionInInitializerError` | Initial static initialization failed; can lead to NCDFE on later accesses |

Do not apply the wrong fix. For instance, `--add-opens` relates to JPMS reflection access permissions; it does not restore missing classes or removed methods.

---

## 3. Why Can Errors Appear Only at Runtime?

### 3.1 Compile Classpath vs. Runtime Classpath

A library can be declared for the compiler without being packaged at runtime. Understand each scope/configuration:

| Gradle configuration | App compile | Typical app runtime | Test runtime |
| --- | --- | --- | --- |
| `implementation` | Yes | Yes | Yes |
| `api` (in Java Library) | Yes, and part of component API | Yes | Yes |
| `runtimeOnly` | Not needed to compile source | Yes | Yes |
| `compileOnly` | Yes | Not automatically present | Not automatically present |
| `testImplementation` | Test only | No | Yes |
| `testRuntimeOnly` | No | No | Yes |
| `developmentOnly` | Plugin/config dependent | For development, not a default production dependency | Per build configuration |

With Maven, understand `compile`, `runtime`, `provided`, and `test` scopes. `provided` dependencies are expected from the deployment environment; when running a standalone executable JAR without that dependency packaged, runtime may miss classes.

**Common mistake:** an application imports classes from a library yet declares Gradle `compileOnly` because “it compiles without errors.” If the runtime has no container/platform supplying that library, instantiating objects or calling methods throws `NoClassDefFoundError`.

### 3.2 Direct Dependencies Do Not Guarantee the Final Version

The application declares:

```groovy
dependencies {
    implementation 'org.example:client-api:2.4.0'
}
```

Yet another dependency may pull in a different version of the related module. Gradle and Maven apply version selection/mediation rules; inspect resolution output to know which version won and why.

### 3.3 Tests Do Not Always Match Production

Common differences:

- Test classpath includes `testImplementation`/`testRuntimeOnly` absent from production.
- The IDE injects modules or libraries into its run configuration.
- Gradle `bootRun` runs from the project classpath; production runs the executable JAR.
- A container supplies a library via a parent classloader absent locally, or vice versa.
- Production uses a different Java version, image, profile, launcher, or environment.
- A method is only reached on rare code paths (scheduled jobs, message consumers, error paths), so linkage is deferred past startup.

Test with the **exact same artifact and launch command** before concluding production fails “mysteriously.”

---

## 4. Ordered Investigation Workflow

### 4.1 Start from the First Exception

1. Save the full stack trace, including nested causes and `Caused by` lines.
2. Identify the first exception, the named class/method, and the first frame in application code.
3. Record when it happens: build, test, startup, bean creation, request, background job, or shutdown.
4. Identify the exact launch command: IDE, `bootRun`, `java -jar`, servlet container, or container image.
5. Record the JDK/JRE version and artifact name/digest running.

Do not copy only the last line of the log or search solely by keyword in the message. The first error often explains why subsequent steps cascade into other errors.

### 4.2 Inspect the Dependency Graph for the Right Configuration

- For `NoClassDefFoundError`, focus on `runtimeClasspath` (or Maven runtime tree).
- For test-only failures, inspect `testRuntimeClasspath`.
- For `NoSuchMethodError`, identify the exact artifact containing the named class and trace every dependency path bringing it in.
- If using Gradle plugins, separate `buildEnvironment` (plugin/buildscript classpath) from the application's runtime classpath.

### 4.3 Inspect the Final Artifact

Verify:

- Application classes are inside the archive.
- Library JARs are inside the runtime package.
- Manifest specifies the right launcher/start class.
- The running artifact is the freshly built/published file, not a stale copy from another directory.
- The container image uses the right digest/tag.
- You are not running a plain JAR instead of the Spring Boot executable JAR.

### 4.4 Identify Where the Classloader Loaded the Class From

When suspecting duplicate JARs or an older version, enable class-loading logging for that exact process. Check the class name and source/location reported by the JVM. If the same class exists in multiple artifacts, determine which artifact wins by classpath order.

### 4.5 Fix Only After Gathering Evidence

A solid fix can point out:

- Which class/method was missing.
- Which artifact was supposed to provide it.
- Which artifact/version the runtime graph selected.
- Which artifact or classloader actually supplied the class.
- Why compile/tests missed it.
- The minimal change and smoke test proving the error is gone.

---

## 5. Gradle: Inspecting Dependency Trees and Version Selection

### 5.1 View the Runtime Dependency Graph

In a Gradle project:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

To compare compile and test:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

The `:app` project path is an example. For single-project builds, omit this prefix. Outputs mark conflict resolution, dependency constraints, unresolved dependencies, and transitive paths.

### 5.2 Use `dependencyInsight` for a Module

Example looking up Spring Core:

```bash
./gradlew :app:dependencyInsight \
  --dependency spring-core \
  --configuration runtimeClasspath
```

Or looking up Jackson:

```bash
./gradlew :app:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

This command answers:

- Which modules request the dependency?
- How many transitive paths exist?
- Which version was selected?
- Why was that version selected (conflict resolution, constraint, forced version, platform/BOM…)?

For `NoSuchMethodError`, this is often the most crucial step: locate the class named in the error, identify the artifact containing it, and check which version is selected at runtime.

### 5.3 Check Buildscript/Plugin Dependencies Separately

If an error happens while running a Gradle plugin/task, run:

```bash
./gradlew buildEnvironment
```

`buildEnvironment` displays buildscript/plugin dependencies. It does not replace the application's `runtimeClasspath`. Do not use this output to conclude the Spring Boot app packaged all required libraries.

### 5.4 Platform/BOM to Align Versions

With Spring Boot, rely on dependency management provided by the Boot plugin/parent/BOM and avoid individually pinning Spring Framework or Jackson modules to incompatible versions.

Gradle example using a platform:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

If the project already uses the Spring Boot Gradle plugin with proper dependency management, do not re-import the BOM redundantly just because of this example. Maintain a single unified source of version management.

### 5.5 Dependency Constraints and Locking

When ensuring a stable dependency graph across CI and developers:

- Use dependency constraints/platforms to define version policies.
- Enable dependency locking for configurations requiring reproducibility.
- Review lockfiles when upgrading dependencies.
- Run integration/smoke tests after changing the graph.
- Do not force a version merely to silence an error if that version breaks another consumer.

Locking freezes already-resolved dependency selections; it does not fix an incompatible version set. Determine compatible versions before recording lock state.

---

## 6. Maven: Dependency Tree and Effective POM

### 6.1 View the Dependency Tree

Run from the module directory:

```bash
./mvnw dependency:tree
```

Focus on runtime scope:

```bash
./mvnw dependency:tree -Dscope=runtime -Dverbose
```

Filter for a specific artifact:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework:spring-core
```

`dependency:tree` shows the dependency hierarchy Maven resolved. `-Dverbose` helps reveal nodes omitted due to conflicts/version mediation.

### 6.2 Inspect the Effective POM

```bash
./mvnw help:effective-pom
```

Use when versions are managed through a parent POM, `dependencyManagement`, profiles, or imported BOMs. A module's `pom.xml` may not declare the final version directly; effective POM shows the configuration after inheritance and profile activation.

### 6.3 Generate Runtime Classpath for Inspection

```bash
./mvnw dependency:build-classpath \
  -DincludeScope=runtime \
  -Dmdep.outputFile=target/runtime-classpath.txt
```

Inspect the output file to see which JARs are present. This is the Maven project's classpath per plugin configuration, and does not by itself prove the executable Spring Boot JAR packaged those files properly; still inspect the artifact.

### 6.4 Maven Dependency Management

When multiple Spring Boot modules share the same dependency ecosystem, use the Spring Boot parent or import the right BOM version. Avoid declaring individual modules from the same release train at separate versions without verified compatibility reasons.

If the organization uses Maven Enforcer, consider dependency convergence or ban-duplicate-classes rules per policy. Convergence rules catch certain version conflicts; they cannot prove that two artifacts with different coordinates share no duplicate class names.

---

## 7. Spring Boot Executable JAR: Inspecting the Actual Package

### 7.1 Boot JAR Structure

A Spring Boot executable JAR is not a plain JAR with only application classes. It uses a launcher and nested JAR layout:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   └── com/example/Application.class
    ├── lib/
    │   ├── spring-core-....jar
    │   ├── spring-context-....jar
    │   └── dependency-....jar
    ├── classpath.idx
    └── layers.idx
```

Application classes live under `BOOT-INF/classes`; dependencies live inside nested JARs under `BOOT-INF/lib`. The Spring Boot launcher sets up the classloader to load them.

### 7.2 `bootJar` vs. Plain `jar`

The Gradle Spring Boot plugin typically generates:

- `bootJar`: executable archive containing the Boot loader and nested runtime dependencies.
- `jar`: plain Java JAR; in many plugin configurations, the plain JAR gets the `plain` classifier.

If `*-plain.jar` is accidentally deployed with `java -jar`, that file may lack the Boot loader and dependencies. Filenames alone are insufficient proof; inspect the manifest and entries.

### 7.3 Inspecting the Archive

List entries:

```bash
jar tf build/libs/app-1.0.0.jar
```

Filter application classes and nested libraries on Linux/macOS:

```bash
jar tf build/libs/app-1.0.0.jar | grep -E 'BOOT-INF/classes|BOOT-INF/lib'
```

PowerShell:

```powershell
jar tf build/libs/app-1.0.0.jar |
    Select-String 'BOOT-INF/classes|BOOT-INF/lib'
```

Inspect manifest:

```bash
unzip -p build/libs/app-1.0.0.jar META-INF/MANIFEST.MF
```

An executable JAR's manifest needs the appropriate launcher in `Main-Class` and the application entry point in `Start-Class`. Exact launcher names depend on the Spring Boot version.

### 7.4 Do Not Run a Boot Fat JAR via Standard Classpath

The command:

```bash
java -jar build/libs/app-1.0.0.jar
```

lets the Boot launcher handle nested dependencies.

The command:

```bash
java -cp build/libs/app-1.0.0.jar com.example.Application
```

does not automatically unpack JARs inside `BOOT-INF/lib` as classpath entries. Standard Java classpaths do not understand nested JARs. Use the proper launch mode for the artifact.

### 7.5 Comparing `bootRun` and `java -jar`

If `bootRun` works yet the executable JAR fails:

1. Verify the `bootJar` task ran and the output file is right.
2. Check runtime dependencies inside `BOOT-INF/lib`.
3. Check `compileOnly`, `runtimeOnly`, `developmentOnly`, and exclusions.
4. Check the manifest and Boot loader.
5. Run the exact JAR file with the exact Java version.
6. If only classpath ordering differs, inspect `BOOT-INF/classpath.idx`.

The Spring Boot classpath index (if present) is used when running the JAR/WAR via `java -jar`; it is not used when running in an IDE or via `bootRun`. Consequently, identical source code can load a different copy of a class if the two environments have different classpath orders.

### 7.6 Checking Dependencies Missing Due to Scope

In a Spring Boot application, required runtime dependencies must belong to the packaged runtime graph. A `compileOnly` dependency does not enter `BOOT-INF/lib` automatically. A `runtimeOnly` dependency gets packaged even when source code does not import its classes directly.

For WARs deployed to external servlet containers, `provided`/`providedRuntime` may be intentional. When running standalone, know which environment is responsible for supplying that dependency.

---

## 8. Classloaders and Spring Boot Nested JARs

### 8.1 Parent Delegation and Class Identity

A classloader does not only locate files; it also defines a class's identity. Two classes with the same fully-qualified name defined by two different classloaders are two distinct runtime types.

This can lead to a `ClassCastException` such as:

```text
com.example.Plugin cannot be cast to com.example.Plugin
```

The names look identical, yet the classloaders differ. This occurs in plugin systems, application servers, DevTools restart classloaders, or libraries packaged twice in multiple places.

### 8.2 Thread Context ClassLoader

Many SPIs/frameworks use the Thread Context ClassLoader (TCCL) to look up providers or plugins. In a Spring Boot executable JAR, dependencies are loaded by the Boot launcher classloader.

Spring Boot recommends:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> plugin = Class.forName(
        "com.example.plugins.CsvPlugin",
        true,
        loader
);
```

When an explicit classloader is needed, pass the appropriate loader rather than defaulting to `ClassLoader.getSystemClassLoader()`. With nested JARs, the system classloader cannot see nested dependencies the way it sees normal JARs on the system classpath.

### 8.3 `ServiceLoader`

An SPI example:

```java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class);
```

`ServiceLoader.load(service)` typically relies on the TCCL to discover providers. Check:

- Is the provider class in the runtime package?
- Is `META-INF/services/com.example.PaymentProvider` present in the artifact?
- Does the file contain the exact fully-qualified provider name?
- If using a shaded/uber JAR, were service descriptor files merged properly?
- Is the provider missing any transitive dependencies?

SPI failures are sometimes wrapped in `ServiceConfigurationError` whose cause is CNFE, NCDFE, or an initialization exception. Read the cause chain.

### 8.4 Spring Boot DevTools

DevTools restart uses a separate classloader to reload development code. A class appearing in both the base classloader and the restart classloader can cause duplicate identity or cast/serialization errors. If an error occurs only when DevTools is enabled:

- Try running with DevTools disabled to confirm the scope.
- Check which libraries sit in the restart classloader.
- Configure restart include/exclude rules per DevTools documentation.
- Never include DevTools in production artifacts as a regular runtime dependency.

Do not use disabling DevTools as a “fix” for production if the runtime package itself is still broken.

### 8.5 Nested JARs and Libraries Requiring Physical Files

Some libraries assume dependency JARs exist as standalone files, trying to reopen the JAR themselves or using native integrations. A nested JAR is not always a regular filesystem path. Spring Boot supports `requiresUnpack` for special dependencies that must be unpacked before use. Configure this only when the library genuinely requires it; it is not a universal fix for CNFE.

---

## 9. Spring Boot 3 Specific Case: `javax` and `jakarta`

Spring Boot 3 migrated to the Jakarta EE ecosystem for many web/persistence APIs. Examples:

| Old API | New API |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |

This does not mean “all `javax` packages were removed”: many Java SE packages like `javax.sql` remain part of the JDK. Only Java EE APIs that changed namespaces need version analysis.

If an older library was compiled against `javax.servlet.Servlet` while a Spring Boot 3 app supplies only `jakarta.servlet.Servlet`, the older class can throw CNFE/NCDFE when loaded or linked. Adding both APIs arbitrarily can mask mismatches and create an unpredictable system.

How to resolve:

1. Identify which class/method references which namespace using the stack trace and `javap`.
2. Check whether a version of the library supports Jakarta/Spring Boot 3.
3. Upgrade to a compatible release or follow a vendor-supported bridge/migration path.
4. Do not manually rename packages in bytecode or add legacy APIs just to get past startup.
5. Run integration tests on the exact Boot major version and runtime container.

---

## 10. Diagnosing `ClassNotFoundException`

### 10.1 Read the Requested Class Name

The message usually states the fully-qualified class name. Check:

- Are the package name and letter casing accurate?
- Is the proper binary name used for nested classes (`$` separator)?
- Does the class actually exist inside the expected JAR?
- Is that JAR on the runtime classpath of the failing process?
- Does the active loader have visibility into that location?

Class names in reflection are binary names, such as `com.example.Outer$Inner`, not source syntax `com.example.Outer.Inner` in all cases.

### 10.2 Class Exists in Source, Missing from Artifact

Check compiled output:

```bash
find build/classes/java/main -type f
```

PowerShell:

```powershell
Get-ChildItem build/classes/java/main -Recurse -Filter *.class
```

Then check the JAR:

```bash
jar tf build/libs/app.jar | grep 'BOOT-INF/classes/com/example'
```

If the class exists in `build/classes` yet is missing from the executable JAR, check source sets, module packaging, custom `bootJar` configuration, and task outputs.

### 10.3 Reflection Using the Wrong Name

Example:

```java
String className = "com.example.plugins.CsvPlugin";
Class<?> type = Class.forName(className);
```

Check the source supplying `className`: properties, database, environment, remote configuration, or plugin manifest. With profile-specific configs, staging and production might point to two different class names.

### 10.4 Choosing the Right Classloader

If a plugin sits in the application classloader or Boot nested JARs, use the appropriate loader:

```java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "com.example.plugins.CsvPlugin",
        false,
        contextLoader
);
```

The `false` argument requests not initializing the class immediately on load. This helps separate “class not found” from static initializer errors. When initialization is truly needed, the JVM initializes per standard rules.

### 10.5 Do Not Swallow the Cause

If CNFE is wrapped in another exception, log the cause and classloader identity. Do not log only `ex.getMessage()` and drop the stack trace; doing so loses crucial location and cause details.

---

## 11. Diagnosing `NoClassDefFoundError`

### 11.1 Locate the Artifact Providing the Class

Example message:

```text
NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Find the artifact expected to hold this class, inspect the dependency tree, and verify whether the artifact is in the runtime package. For a Spring Boot JAR, check `BOOT-INF/lib`.

Do not conclude “commons-lang3 is missing” solely because the class name resembles the artifact. Verify whether the class actually resides inside the JAR using `jar tf`.

### 11.2 Check Scopes and Exclusions

Common causes:

- Dependency declared as `compileOnly`.
- Maven dependency has `provided` scope yet standalone app does not supply it.
- Dependency was excluded in a parent module.
- Optional dependency was not declared by the consumer.
- Custom build script manually packages a subset of JARs and omits transitive dependencies.
- A runtime profile/conditional configuration loads the class only in production.

When a library exposes a dependency type in its public API, the producer must declare the proper dependency contract so consumers can resolve it. Do not rely on the library “happening” to have the JAR on a developer's machine.

### 11.3 Distinguish Missing Class from Static Initialization Failure

If the message is `Could not initialize class ...`:

1. Search earlier logs in the same process.
2. Find the first `ExceptionInInitializerError`.
3. Read its cause (e.g., `IllegalStateException`, `NullPointerException`, missing config, native library load failure).
4. Fix the static initialization cause.
5. Restart the process/classloader after fixing; the class is marked erroneous in the current loader.

Anti-pattern example:

```java
public final class LegacyConfig {
    static {
        // Read file or connect to network as soon as the class loads.
        // If it fails, the class cannot initialize.
    }
}
```

Avoid network I/O, reading secrets, or complex system initialization inside static initializers when it can be moved to a managed lifecycle (Spring bean initialization, factory, or explicit startup component).

### 11.4 Check Dependencies of Dependencies

A JAR may be present while a type it needs is absent. For instance, the app finds `com.vendor.Client`, yet when the JVM verifies/links its methods, it needs `com.vendor.internal.Transport` which was not packaged.

Therefore, when fixing NCDFE:

- Check the full dependency tree, not just direct dependencies.
- Inspect exclusions/optional scopes.
- Verify the actual JAR contains the named class.
- Verify the classloader can see that transitive dependency.
- Check classes loaded after a static initializer failure.

### 11.5 Native Libraries Are a Different Case

If the class exists yet a `native` method lacks a native implementation, the error is usually `UnsatisfiedLinkError`. Check OS/architecture, native library paths, and ABI versions. Do not confuse it with a missing Java class.

---

## 12. Diagnosing `NoSuchMethodError`

### 12.1 Identify the Method Signature in the Error

Read in full:

- Target class.
- Method name.
- Parameter types.
- Return type if displayed in the message/descriptor.
- First caller frame in the stack trace.

Do not compare only method names in source. Two methods with the same name but different parameter/return descriptors are two distinct binary methods.

### 12.2 Caller and Callee Compiled Against Different Versions

Classic scenario:

1. `orders-service` compiles against `payment-client 2.0`.
2. Method `authorize(String, Duration)` exists in version 2.0.
3. Production runtime resolves `payment-client 1.5`.
4. Caller bytecode still references the version 2.0 method.
5. The JVM fails to find the matching method and throws `NoSuchMethodError`.

Recompiling only the app while the runtime dependency remains 1.5 will not solve it. Align the versions or compile/test against the exact version deployed.

### 12.3 Transitive Version Conflict

One starter/framework may pull in a newer version while another library pulls in an older version. Use `dependencyInsight`/`dependency:tree` to inspect the selected version and paths.

For the Spring ecosystem:

- Use the Spring Boot BOM/parent to manage Spring module versions.
- Avoid overriding `spring-core`, `spring-beans`, `spring-context`, or `spring-web` individually.
- Check Jackson, Hibernate, logging, and integration libraries against the version matrix.
- Upgrade a compatible starter/library instead of bumping a single sub-JAR.
- Run integration tests after alignment.

### 12.4 Duplicate Classes Across Multiple Artifacts

Version resolution resolves conflicts for the same module coordinates. Yet two artifacts with different GAVs can still contain the same fully-qualified class. In that case, the dependency tree may report no “version conflict” even though runtime has duplicate classes.

Use class-load logging to see which JAR loaded the class. If a shaded JAR embeds a copy of a library, `dependencyInsight` might not reveal that duplicate class.

### 12.5 Method Signatures and Binary Compatibility

API changes that can break older compiled binaries:

- Deleting a method or constructor already used by compiled callers.
- Changing parameter types or adding/removing parameters.
- Changing return type.
- Altering generic erasure so descriptors differ.
- Changing class hierarchy so method lookup changes.
- Switching static/instance can trigger `IncompatibleClassChangeError`.

When publishing shared libraries across multiple services, treat API and binary compatibility as a contract. Use semantic versioning, compatibility tests, or API checks per release policy.

### 12.6 Do Not Force Versions Arbitrarily

Forcing a module version may silence an error for one caller while breaking another consumer requiring the newer API. Determine a version compatible across all dependency paths, then use a BOM/constraint/platform and test the resolved graph.

---

## 13. JVM and Bytecode Diagnostic Commands

### 13.1 See Where a Class Was Loaded From

Java 17 unified logging:

```bash
java -Xlog:class+load=info -jar build/libs/app.jar
```

Output can be large. Filter by class name on Linux/macOS:

```bash
java -Xlog:class+load=info -jar build/libs/app.jar 2>&1 |
  grep 'com.vendor.Client'
```

PowerShell:

```powershell
java -Xlog:class+load=info -jar build/libs/app.jar 2>&1 |
    Select-String 'com.vendor.Client'
```

Log lines show the loaded class and the source/location recorded by the JVM. This is strong evidence when suspecting an old class was loaded from an unexpected JAR.

### 13.2 Inspect Actual Methods in the Runtime JAR

`javap` inspects/disassembles class files:

```bash
javap -classpath path/to/vendor-client.jar \
  -p -s com.vendor.Client
```

- `-p` shows private members as well.
- `-s` prints internal type descriptors.
- `-c` prints bytecode instructions.
- `-verbose` prints constant pool and detailed class info.

Compare the compile-time JAR output with the runtime JAR output. Ensure `javap` points to the exact file, not a classpath containing multiple versions.

### 13.3 Inspect Static Dependency References

```bash
jdeps --multi-release 17 -verbose:class \
  -classpath "lib-a.jar;lib-b.jar" \
  app.jar
```

On Linux/macOS, separate classpaths with `:`; on Windows, use `;`. `jdeps` analyzes package/class-level bytecode dependencies. With Spring Boot nested JARs, run it against extracted dependency JARs or the appropriately unpacked archive; do not treat `jdeps` output on the outer executable JAR as complete proof for every nested dependency.

`jdeps` analyzes static references and does not replace runtime testing for reflection, ServiceLoader, generated classes, or classes loaded solely by string name.

### 13.4 Check Java Runtime

```bash
java -version
javac -version
jar --version
```

If built with JDK 21 yet production uses Java 17, also check `UnsupportedClassVersionError`. That is a class-file version error, distinct from the three main errors in this lesson.

---

## 14. Lab 1: Reproducing `ClassNotFoundException`

Create `Lookup.java`:

```java
public class Lookup {

    public static void main(String[] args) {
        String className = args.length == 0
                ? "demo.Plugin"
                : args[0];

        try {
            Class<?> type = Class.forName(className);
            System.out.println("LOADED=" + type.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("CLASS_NOT_FOUND=" + ex.getMessage());
        }
    }
}
```

Compile and run with a non-existent class name:

```bash
javac Lookup.java
java Lookup demo.Plugin
```

Exact stdout:

```text
CLASS_NOT_FOUND=demo.Plugin
```

Add `demo.Plugin` to the classpath or fix the class name so the program loads it successfully. Try passing a wrong package name to see that the failure stems from the lookup string rather than a compiler dependency.

**Conclusion:** `Class.forName` requests a class by name and throws a checked exception when the loader cannot find it. In real apps, inspect plugin config, class names, and the loader passed in.

---

## 15. Lab 2: Reproducing `NoClassDefFoundError`

Create two source files:

`src/helper/demo/OptionalFeature.java`:

```java
package demo;

public final class OptionalFeature {

    private OptionalFeature() {
    }

    public static String value() {
        return "feature-present";
    }
}
```

`src/app/demo/UsesFeature.java`:

```java
package demo;

public class UsesFeature {

    public static void main(String[] args) {
        System.out.println(OptionalFeature.value());
    }
}
```

Compile the helper first, then compile the application with helper classes on the compile classpath:

```bash
javac -d helper-classes src/helper/demo/OptionalFeature.java
javac -cp helper-classes -d app-classes src/app/demo/UsesFeature.java
```

Run **only** app classes, intentionally omitting the helper from the runtime classpath:

```bash
java -cp app-classes demo.UsesFeature
```

The JVM throws `NoClassDefFoundError` for `demo.OptionalFeature` (with a cause indicating class lookup failed). This is a runtime failure: compilation saw the class, yet the runtime classpath lacked it.

Re-run with helper classes:

```bash
java -cp "app-classes:helper-classes" demo.UsesFeature
```

Exact stdout on Linux/macOS:

```text
feature-present
```

On Windows, the classpath separator is a semicolon:

```powershell
java -cp "app-classes;helper-classes" demo.UsesFeature
```

**Spring Boot connection:** if the class is a dependency, ensure the dependency is in the runtime configuration and packaged into `BOOT-INF/lib`. If it is application code, ensure it exists in `BOOT-INF/classes`.

---

## 16. Lab 3: Reproducing `NoSuchMethodError` Due to Version Skew

### 16.1 Create Library Version 1

`src/lib-v1/demo/Greeter.java`:

```java
package demo;

public class Greeter {

    public String greet(String name) {
        return "Hello " + name;
    }
}
```

### 16.2 Create Library Version 2

`src/lib-v2/demo/Greeter.java`:

```java
package demo;

public class Greeter {

    public String greet(String name) {
        return "Hello " + name;
    }

    public String greet(String name, String prefix) {
        return prefix + " " + name;
    }
}
```

### 16.3 Compile Caller Against Version 2

`src/app/demo/App.java`:

```java
package demo;

public class App {

    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Linh", "Welcome"));
    }
}
```

Build both JARs:

```bash
javac -d lib-v1-classes src/lib-v1/demo/Greeter.java
jar --create --file greeter-v1.jar -C lib-v1-classes .

javac -d lib-v2-classes src/lib-v2/demo/Greeter.java
jar --create --file greeter-v2.jar -C lib-v2-classes .
```

Compile caller against v2:

```bash
javac -cp greeter-v2.jar -d app-classes src/app/demo/App.java
```

### 16.4 Run Caller with Version 1

Linux/macOS:

```bash
java -cp "app-classes:greeter-v1.jar" demo.App
```

Windows:

```powershell
java -cp "app-classes;greeter-v1.jar" demo.App
```

The JVM throws `NoSuchMethodError` for `Greeter.greet(String, String)` because `App`'s bytecode compiled against v2 while runtime loaded v1.

Run with v2:

```bash
java -cp "app-classes:greeter-v2.jar" demo.App
```

Exact stdout:

```text
Welcome Linh
```

### 16.5 Inspect Bytecode

```bash
javap -classpath app-classes -c -p demo.App
javap -classpath greeter-v1.jar -p -s demo.Greeter
javap -classpath greeter-v2.jar -p -s demo.Greeter
```

Compare method descriptors: v2 has the overload referenced by the caller; v1 does not. This is proof of a binary mismatch, not a missing `Greeter` class.

---

## 17. Spring Boot Case Study: Works Locally, Fails in Production

Suppose a service uses `com.vendor:payment-client`. The developer runs `bootRun` and tests pass. The production container reports:

```text
java.lang.NoSuchMethodError:
  'com.vendor.Result com.vendor.PaymentClient.authorize(
      java.lang.String, java.time.Duration)'
```

Workflow:

1. Record the image digest and the actual JAR inside the image.
2. Run `java -version` inside the exact container runtime.
3. Run `./gradlew :app:dependencyInsight --dependency payment-client --configuration runtimeClasspath`.
4. Check `BOOT-INF/lib/payment-client-*.jar` in the executable JAR.
5. Use `javap -classpath` to inspect the method inside the runtime JAR.
6. Compare the version and checksum of the JAR used at compile time against the JAR in the artifact.
7. Check whether a starter/transitive library is pulling an older version.
8. Use a BOM/constraint to select a compatible version, rebuild the image, and run the smoke test.
9. Promote that exact verified image digest.

If the error occurs only with `java -jar` and not with `bootRun`, compare the runtime graph and `BOOT-INF/classpath.idx`. If class-load logging shows the class loaded from an unexpected JAR, investigate classpath order/duplicate classes.

Another scenario: production reports `NoClassDefFoundError: jakarta/servlet/Servlet`. Check whether the app runs embedded or as a deployed WAR, whether the Servlet API is supplied by the environment, and whether dependency scopes excluded it from the executable package. If the error mentions `javax.servlet.Servlet` on Boot 3, look for an older library not yet migrated to Jakarta.

---

## 18. Symptom and Resolution Matrix

| Symptom | Likely Cause | Evidence to Collect | Fix Direction |
| --- | --- | --- | --- |
| CNFE from `Class.forName` | Wrong class name or loader cannot see plugin | String name, loader identity, runtime graph | Fix FQCN/loader or add plugin JAR |
| CNFE only in production | Runtime config/loader differs from local | Actual config, class-load log | Sync config and classloader |
| NCDFE naming a dependency class | Dependency absent at runtime | Gradle/Maven runtime tree, archive entries | Change scope or add proper dependency |
| NCDFE naming an app class | Class was not packaged | `jar tf` and output classes | Fix source set/packaging |
| NCDFE only with plain JAR | Plain JAR lacks Boot loader/nested dependencies | Manifest, `BOOT-INF/lib` | Deploy `bootJar`/executable WAR properly |
| NCDFE “Could not initialize class” | Static initializer failed earlier | First `ExceptionInInitializerError` | Fix cause, start fresh process/classloader |
| NCDFE for a transitive type | Library's dependency is missing | Full dependency tree | Add contract/runtime dependency |
| `NoSuchMethodError` in Spring class | Spring modules from mixed release trains | `dependencyInsight`/tree, class-load source | Use Boot BOM/compatible versions |
| `NoSuchMethodError` in vendor SDK | Caller and runtime SDK version skew | `javap` on caller and runtime JAR | Align SDK version, rebuild, and test |
| `NoSuchMethodError` only in container | Image contains stale artifact/JAR or duplicate | Digest, archive contents, load log | Rebuild/pin artifact, remove duplicate |
| Error only when plugin runs | Classloader isolation/TCCL/SPI | Loader identity, service descriptor | Use right loader, fix SPI packaging |
| `ClassCastException` with same class name | Two classloaders defined the same class | `getClassLoader()` of both objects | Fix classloader boundary/duplicates |
| `NoSuchMethodException` via reflection | Method missing or wrong visibility/signature | `getDeclaredMethods`/reflection config | Fix reflection lookup; don't treat as linkage |
| `UnsupportedClassVersionError` | Runtime JDK too old | `java -version` and class file target | Use matching JRE or compatible build target |

---

## 19. Fix and Verification Checklist

### 19.1 Before Changing Dependencies

- [ ] Saved the full stack trace and identified the first exception.
- [ ] Identified the exact class/method in the message.
- [ ] Identified whether the error occurs at compile, test, startup, request, or background task.
- [ ] Recorded JDK, launch command, artifact name, and image digest.
- [ ] Distinguished the runtime graph from the compile/test graph.
- [ ] Identified which JAR actually provides the class/method.

### 19.2 While Fixing

- [ ] Change scope/exclusion/coordinates targeting the root cause.
- [ ] Align modules from the same release train using BOM/platform.
- [ ] Remove duplicate classes/JARs when evidenced.
- [ ] Use the proper Boot executable archive task and launch mode.
- [ ] Do not embed test/dev dependencies in production.
- [ ] Do not hardcode manual classpaths when the build tool manages the graph.
- [ ] Do not catch `Error` and keep running in a corrupted classloader state.
- [ ] Do not wipe the entire Gradle/Maven cache before verifying version selection.

### 19.3 After Fixing

- [ ] Run unit/integration tests.
- [ ] Build the executable JAR/WAR from a clean build.
- [ ] Inspect manifest and archive entries.
- [ ] Inspect the runtime dependency graph.
- [ ] Run the exact artifact with the exact Java command.
- [ ] Smoke-test inside the exact container base image/runtime.
- [ ] Verify class-load source if duplicate/version skew was involved.
- [ ] Record image digest/artifact checksum and promote the exact tested artifact.
- [ ] Have a rollback plan if dependency upgrades impact other services.

---

## 20. Prevention in Build and Release Pipelines

### 20.1 Reproducible Dependency Graph

- Use a reviewed Gradle Wrapper/Maven Wrapper.
- Pin plugin and dependency versions per policy.
- Use BOM/platforms for ecosystems requiring version alignment.
- Use dependency locking/verification when reproducibility is needed.
- Review dependency tree diffs in pull requests.
- Restrict dynamic versions and snapshots in production.

### 20.2 Inspecting the Actual Artifact

A useful pipeline:

```text
Resolve dependencies
      |
      v
Compile + unit tests
      |
      v
Integration tests
      |
      v
Build executable JAR/WAR
      |
      v
Inspect manifest + runtime libraries
      |
      v
Run java -jar smoke test
      |
      v
Build container from this artifact
      |
      v
Run container smoke test
      |
      v
Record digest + promote same image
```

Building/testing source alone is not enough. Smoke tests should run the **exact executable artifact** and the **exact container image** production will run.

### 20.3 API/Binary Compatibility for Internal Libraries

If the team publishes shared Java libraries:

- Do not delete/alter public methods used by compiled consumers without a major-version migration.
- Maintain API compatibility tests or a binary compatibility checker.
- Publish new versions under a clear policy.
- Test sample consumers against the newly published artifact.
- Never republish a different binary under the same release GAV.
- Document method/API changes in release notes.

### 20.4 Observability and Incident Records

When an incident occurs, record:

```text
Exception class + full message:
First cause:
First application frame:
Class or method named:
Runtime Java version:
Launch command:
Artifact filename + checksum:
Container image digest:
Gradle/Maven runtime dependency tree:
Resolved artifact version:
Class-load source:
Fix:
Regression test:
Verification environment:
```

Do not put credentials, tokens, or secrets into diagnostic logs. If sharing dependency trees or image metadata, redact internal details per policy.

---

## 21. Comprehensive Practice Exercises

### A. Classify the Exception

For each scenario, predict the error and explain why:

1. `Class.forName("com.example.Plugin")` when the plugin JAR is absent from the classpath.
2. App compiles against `PaymentClient`, yet the runtime JAR lacks that class.
3. Caller compiles against `Client.send(String, int)`, runtime version only has `send(String)`.
4. A static initializer throws an exception on first access; the next access reports “Could not initialize class”.
5. Reflection calls `getMethod` with a non-existent signature.
6. Two classes with the same name are loaded by two different classloaders and cast across a boundary.

### B. Gradle Dependency Diagnosis

1. Run `dependencies --configuration runtimeClasspath`.
2. Run `dependencyInsight` for the class/library appearing in the stack trace.
3. Compare `compileClasspath` and `runtimeClasspath`.
4. Trace the dependency path introducing the unwanted version.
5. Fix using the appropriate platform/constraint/exclusion.
6. Run tests and re-check the resolved graph.

### C. Maven Dependency Diagnosis

1. Run `dependency:tree -Dscope=runtime -Dverbose`.
2. Filter the artifact with `-Dincludes`.
3. Inspect effective POM for parent/BOM/profiles.
4. Check scopes and dependency mediation.
5. Build the executable artifact and verify the library is inside the package.
6. Run consumer/smoke tests from the new artifact.

### D. Spring Boot Packaging

1. Build both the plain JAR and executable JAR.
2. Use `jar tf` to compare entries.
3. Inspect `META-INF/MANIFEST.MF`.
4. Run the executable JAR with `java -jar`.
5. Try class-load logging to locate a class's source.
6. Explain why `java -cp app.jar` does not automatically load nested JARs.
7. Compare `bootRun` with `java -jar` and explain the role of the classpath index.

### E. Binary Compatibility Lab

1. Complete the version 1/version 2 lab in section 16.
2. Run the caller against v1 and v2.
3. Use `javap -c -s` to inspect bytecode/descriptors.
4. Fix the runtime JAR to a compatible version.
5. Add a regression test or consumer compatibility check to CI.
6. Explain why merely recompiling the application with the same old dependency does not fix the error.

### F. Write an Incident Report

Use the template in section 20.4 to document a real or lab error. Distinguish **hypotheses** from **collected evidence**. Do not mark “fixed” right after changing a version without running the exact executable artifact/container.

---

## 22. Official References

- Java SE 17 API — `ClassNotFoundException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html
- Java SE 17 API — `NoClassDefFoundError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html
- Java SE 17 API — `NoSuchMethodError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html
- Java SE 17 API — `LinkageError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- Java Language Specification — Chapter 13, Binary Compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- Oracle JDK 17 — `javap` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle JDK 17 — `jdeps` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Gradle User Manual — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle User Manual — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Apache Maven Dependency Plugin — `dependency:tree`: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Spring Boot — Nested JARs and executable JAR structure: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot — Executable JAR restrictions and classloader guidance: https://docs.spring.io/spring-boot/specification/executable-jar/restrictions.html
- Spring Boot 3.3 — Efficient Deployments and unpacking executable JAR: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Spring Boot — Build and packaging how-to: https://docs.spring.io/spring-boot/how-to/build.html

**Remember:** `ClassNotFoundException` is typically a lookup by String name; `NoClassDefFoundError` indicates the JVM could not find a needed class definition or the class failed initialization; `NoSuchMethodError` usually signals a binary/API version mismatch. Investigate the **runtime dependency graph, actual artifact, classloader, and method descriptors**, then verify the fix with the exact executable JAR and container that will run in production.