# ClassNotFoundException and NoClassDefFoundError

When upgrading the JDK, framework, or dependencies of a Java system, two errors that are very easy to confuse are `ClassNotFoundException` and `NoClassDefFoundError`. Both can appear when the runtime cannot find or cannot use a class, but **they differ in kind, differ in when they occur, and can have very different root causes**. Misdiagnosis leads to wrong fixes: adding a batch of JARs to the classpath, disabling module encapsulation, or rolling back the JDK when the real issue is merely a dependency that was not packaged.

This lesson belongs to the **Java Advance Compatibility Migration** topic, **Troubleshooting** chapter, focusing on how to read stack traces, understand the JVM's load–link–initialize mechanism, identify classpath/module path errors, distinguish missing classes from class initialization failures, and trace Maven/Gradle, fat JARs, containers, Java EE/Jakarta, and JPMS. The examples go from reproducible code to safe production handling workflows.

## 1. Quick comparison of the two errors

| Criterion | `ClassNotFoundException` | `NoClassDefFoundError` |
|---|---|---|
| Type | **Checked exception** extending `ReflectiveOperationException`. | **Error** extending `LinkageError`. |
| Core meaning | An API asks to find/load a class by name, but the classloader cannot find it. | The JVM or a component using the class cannot complete resolving/defining the required class, or the class is already in a failed initialization state. |
| Common occurrences | `Class.forName(...)`, `ClassLoader.loadClass(...)`. | Bytecode reference to a class at runtime, or reusing a class that previously failed initialization. |
| Timing | When the instruction to load a class by name is executed. | Can happen during loading, linking, resolution, or when initializing/continuing to use a class marked erroneous. |
| Who typically throws it? | The reflection/class loading API reports it directly. | The JVM or related code during linkage/initialization. |
| Code handling | Can `catch (ClassNotFoundException e)` to handle an optional feature. | Should not be treated as a business exception to catch and continue. |
| First investigation step | Name of the class to load, classloader used, classpath/module graph. | Read the full message + `Caused by`, determine whether a definition is missing or initialization failed. |

**Practical rule:** do not infer solely from the error name. `NoClassDefFoundError` does **not always** mean the `.class` file does not exist; the class may be present but have failed initialization in an earlier use.

## 2. Inheritance hierarchy and handling implications

```text
java.lang.Throwable
├── java.lang.Exception
│   └── java.lang.ReflectiveOperationException
│       └── java.lang.ClassNotFoundException
└── java.lang.Error
    └── java.lang.LinkageError
        └── java.lang.NoClassDefFoundError
```

`ClassNotFoundException` is a checked exception. For APIs declaring `throws ClassNotFoundException`, the Java compiler forces you to catch it or declare `throws`.

`NoClassDefFoundError` is an `Error`, belonging to the runtime linkage failure group. The Java compiler does not force you to catch it. Typically, **the environment, dependencies, or initialization error must be fixed**; using `catch (NoClassDefFoundError e)` and ignoring it should not be treated as a migration solution.

Both can exist in a causal chain:

```text
java.lang.NoClassDefFoundError: com/example/codec/Codec
    at com.example.App.main(App.java:15)
Caused by: java.lang.ClassNotFoundException:
    com.example.codec.Codec
    at ...ClassLoader.loadClass(...)
```

In this example, the JVM code needs the `Codec` class, but the underlying classloader called could not find it. `ClassNotFoundException` is the nested underlying cause; `NoClassDefFoundError` is the error manifested at the site where the JVM is resolving the reference.

## 3. How does the JVM load, link, and initialize a class?

Conceptual diagram:

```text
        Class reference / Class.forName / class loading
                              |
                              v
                 LOAD: find/define class
                              |
                              v
        LINK: verify -> prepare -> resolve references*
                              |
                              v
                   INITIALIZE: static fields,
                  static initializers, superclass
                              |
                              v
                          Use class

* Resolution can be performed flexibly; it is not required
  for every symbolic reference to be resolved all at once.
```

Understanding these phases is necessary to see why “able to compile” differs from “able to run”.

### 3.1. Loading

The classloader searches for bytecode or an appropriate module class definition. If an API such as `ClassLoader.loadClass("x.Y")` cannot find it, it can throw `ClassNotFoundException`.

### 3.2. Linking

The JVM verifies bytecode, prepares static fields, and resolves symbolic references according to JVM rules. A class may already be loaded, yet when execution reaches a call needing another dependency, it fails because the definition cannot be found. At that point you may receive `NoClassDefFoundError`.

### 3.3. Initialization

The JVM runs static field initializers and static initializer blocks when a class is initialized for the first time according to active-use rules. If initialization fails:
- The first time may yield `ExceptionInInitializerError` if a non-Error exception escapes from the initializer.
- Subsequent uses may yield `NoClassDefFoundError: Could not initialize class ...` because the class has been marked erroneous in the relevant classloader.

Therefore, with `NoClassDefFoundError`, merely asking “Does the JAR contain the class?” is not enough.

## 4. Example 1: ClassNotFoundException during dynamic loading

An application allows enabling plugins via configuration:

```java
package demo;

public class DynamicPluginLoader {
    public static void main(String[] args) {
        String pluginClass = "demo.plugins.ReportPlugin";

        try {
            Class<?> type = Class.forName(pluginClass);
            System.out.println("Loaded: " + type.getName());
        } catch (ClassNotFoundException e) {
            System.err.println(
                "Plugin class not available: " + pluginClass);
            e.printStackTrace();
        }
    }
}
```

If `demo.plugins.ReportPlugin` is not in the search space of the loader used:

```text
Plugin class not available: demo.plugins.ReportPlugin
java.lang.ClassNotFoundException:
    demo.plugins.ReportPlugin
    at ...
```

Here the code intentionally loads a class by **string name**. `Class.forName` can load and initialize the class; if the goal is only to check presence without initializing, there is an overload:

```java
Class<?> type = Class.forName(
    "demo.plugins.ReportPlugin",
    false,
    Thread.currentThread().getContextClassLoader());
```

The value `false` requests **not initializing** the class as part of this call; it does not guarantee other dependencies will not be linked or that the loader will not encounter other errors. `LinkageError` failures should be handled separately if a plugin boundary truly needs to isolate them, while not hiding production errors.

### 4.1. When should this error be caught?

A **truly optional** plugin can return a clear message and disable that specific feature when the class is absent per contract. However, if `ReportPlugin` is a required component, it is better to **fail fast** at startup, avoiding a system reporting healthy and then failing when a customer uses the feature.

Do not write a `catch (Exception e) { }` or `catch (Throwable t) { }` block that ignores all plugin loading errors. It can mask `ExceptionInInitializerError`, version errors, and serious failures.

## 5. Example 2: NoClassDefFoundError because the class exists at compile time but is missing at runtime

Two Java files:

```text
src/
└── demo/
    ├── App.java
    └── Helper.java
```

`src/demo/Helper.java`:

```java
package demo;

public final class Helper {
    public static String message() {
        return "Helper is present";
    }
}
```

`src/demo/App.java`:

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
```

Compile both:

```bash
mkdir -p build/classes build/runtime/demo
javac -d build/classes src/demo/App.java src/demo/Helper.java
java -cp build/classes demo.App
```

Result when all classes are present:

```text
Helper is present
```

Now simulate a package/runtime missing a dependency: **copy only App.class**, do not copy Helper.class.

```bash
cp build/classes/demo/App.class build/runtime/demo/
java -cp build/runtime demo.App
```

A typical result:

```text
Exception in thread "main" java.lang.NoClassDefFoundError:
    demo/Helper
    at demo.App.main(App.java:5)
Caused by: java.lang.ClassNotFoundException: demo.Helper
    at ...
```

Here `App.class` was compiled with a symbolic reference to `Helper`. When the runtime needs to resolve the reference but cannot find `Helper.class`, the JVM cannot complete linking and produces `NoClassDefFoundError`.

Note:
- The `mkdir`/`cp` commands use Unix/macOS/Git Bash syntax. On Windows PowerShell, use `New-Item -ItemType Directory` and `Copy-Item` respectively.
- If `App.class` is also deleted, the message may be “Could not find or load main class demo.App” with `ClassNotFoundException` as the cause; that is a different situation from **the main class existing while its dependency is missing**.

## 6. Example 3: NoClassDefFoundError after a static initializer fails

This is the most important case that is easily missed during migration. File `InitFailureDemo.java`:

```java
package demo;

public class InitFailureDemo {
    static class Configuration {
        static final int PORT = loadPort();

        private static int loadPort() {
            throw new IllegalStateException(
                "Missing required environment configuration");
        }
    }

    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            System.out.println("Attempt " + i);
            try {
                System.out.println(Configuration.PORT);
            } catch (Throwable failure) {
                failure.printStackTrace(System.out);
            }
        }
    }
}
```

Compile/run:

```bash
javac -d out src/demo/InitFailureDemo.java
java -cp out demo.InitFailureDemo
```

Conceptual output:

```text
Attempt 1
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException:
    Missing required environment configuration

Attempt 2
java.lang.NoClassDefFoundError:
    Could not initialize class demo.InitFailureDemo$Configuration
```

On attempt 1, the `Configuration` class **is present** and was found, yet static initialization failed. The JVM marks the class in a failed initialization state. On attempt 2 in the same classloader, using it leads to `NoClassDefFoundError`.

**The right fix:** find the *first* error when the class was initialized: missing environment, wrong credentials, network call inside static init, missing native library, or a library exception; do not rush to add JARs just because subsequent attempts show `NoClassDefFoundError`.

The example program deliberately uses `catch (Throwable)` to **illustrate two uses in one process**. This is not a production error-handling pattern.

## 7. Which stack trace should you read first?

When encountering:

```text
java.lang.NoClassDefFoundError:
    Could not initialize class com.example.storage.ConnectionHolder
```

Do not just search whether the `ConnectionHolder` class is in the JAR. First:
1. Find the **first** occurrence of the error in the logs per process/instance.
2. Look for an earlier `ExceptionInInitializerError`, `IllegalStateException`, or native linkage error.
3. Read the entire `Caused by:` chain and `Suppressed:` if present.
4. Determine whether the application has been restarted; a classloader in a new process may attempt to initialize again.
5. Inspect the source of the static field initializer/static block and the dependencies called there.

Conversely, if the error is:

```text
java.lang.NoClassDefFoundError: jakarta/servlet/Filter
Caused by: java.lang.ClassNotFoundException:
    jakarta.servlet.Filter
```

that is a strong signal that **runtime classes/modules/dependencies do not yet provide the corresponding Jakarta Servlet API**, such as running a Jakarta library on an older Servlet container.

Prioritize the root error, and do not apply the same fix to two different error chains.

## 8. Reading class names in messages correctly

In the message:

```text
java.lang.NoClassDefFoundError:
    com/example/codec/JsonCodec
```

names using `/` typically reflect the internal/binary name in bytecode. Convert to a Java class name to locate the file:

```text
com.example.codec.JsonCodec
com/example/codec/JsonCodec.class
```

With nested classes:

```java
package demo;

public class Outer {
    public static class Inner { }
}
```

The binary name used for reflection/classloader is:

```text
demo.Outer$Inner
```

Not `demo.Outer.Inner` when calling `Class.forName`. On the other hand, the API `Outer.Inner.class` remains valid source syntax.

Also note that Java package/class names are case-sensitive. An artifact that used to run on a case-insensitive filesystem environment can still fail after moving to a Linux container.

## 9. Distinguishing direct errors from indirect errors

For example, the application only calls:

```java
new com.example.reports.ReportService().render();
```

but the runtime lacks `org.example.json.JsonProvider` located in a **dependency of ReportService**. The message may mention this missing class, not the class on the source line the developer sees.

Diagram:

```text
Application
   |
   v
ReportService.class  (present)
   |
   v
JsonProvider.class   (missing at runtime)
   |
   v
NoClassDefFoundError
```

Investigation must find **which class is actually undefined** and **which artifact is supposed to provide it**, not just look at the application module's direct dependencies.

This is where `mvn dependency:tree`, `gradle dependencies`, and `jdeps` help identify transitive dependencies or incorrect build/package scopes.

## 10. Common cause: missing runtime dependency

Common scenarios:
- The JAR is only on the compile classpath, not on the runtime classpath.
- A Maven dependency uses `provided` while running as a standalone app with no container supplying it.
- A Gradle dependency uses `compileOnly` instead of `implementation` when the runtime actually needs the class.
- The dependency was excluded, or conflict resolution chose a different version than expected.
- The build produces a thin JAR, yet deployment forgot the `lib/` directory.
- The container build only copied the application JAR without copying required dependencies.
- A provider was dropped when creating a shaded/uber JAR.
- The CI test classpath accidentally had a library that production lacks.

Identify all three:
1. **The artifact needing the class** (consumer).
2. **The artifact providing the class** (provider).
3. **The runtime classloader/module graph** that determines whether the provider is visible.

Do not fix by adding all compile and test libraries to production. That can pull in conflicts, increase attack surface, or break dependency management.

## 11. Maven scopes and compile–runtime differences

In Maven:

| Scope | Typical behavior | Migration risk |
|---|---|---|
| `compile` | Present on appropriate compile/runtime classpaths. | Version conflicts or missing transitive artifacts after packaging. |
| `runtime` | Needed when running, not needed directly to compile source. | Can be omitted if only copying the main JAR. |
| `provided` | Used at compile/test time, but expected to be provided by the runtime/container. | Standalone deployment may lack classes. |
| `test` | Only for tests. | Tests pass while production lacks libraries. |
| `system` | Depends on a file at a specific path. | Hard to port, especially old `tools.jar`. |
| `import` | Used for BOMs in dependencyManagement. | Does not automatically add runtime dependencies. |

Example in a WAR deployed on a compatible Jakarta Servlet container:

```xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>VERSION_MATCHING_CONTAINER</version>
  <scope>provided</scope>
</dependency>
```

The version placeholder must be replaced with a version matching the runtime. When running a standalone JAR without a servlet container, you cannot keep the same `provided` assumption and expect the runtime to supply the Servlet API itself.

Diagnostic commands:

```bash
mvn dependency:tree
mvn help:effective-pom
```

With multi-module projects, run in the failing module and verify actual scopes. `effective-pom` helps show inheritance/management; the dependency tree shows resolved dependencies. Inspect the packaged and deployed artifact, not just the POM.

## 12. Gradle configurations and runtimeClasspath

A common mistake:

```kotlin
dependencies {
    compileOnly("com.example:codec-api:1.0")
}
```

If the code actually uses `Codec` at runtime without another container/module providing it, `compileOnly` has the wrong semantics.

Replace with an appropriate dependency:

```kotlin
dependencies {
    implementation("com.example:codec-api:1.0")
}
```

Illustrative version/artifact. For implementation providers loaded via SPI, an additional separate runtime dependency may also be needed.

Commands:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency codec-api \
  --configuration runtimeClasspath
```

In a multi-project build, use the exact task/configuration of the failing subproject. `testRuntimeClasspath` can be larger than `runtimeClasspath`, so passing test results cannot be taken as proof that the production package has all classes.

## 13. Compile classpath, test classpath, and production classpath

A pipeline may use four different classpaths:

```text
javac compileClasspath
         |
         v
   testRuntimeClasspath
         |
         v
   packaged artifact
         |
         v
production runtime classpath
```

For example:
- The Maven Surefire test classpath contains a library because of a test dependency.
- Spring Boot `bootJar` contains the runtime dependencies selected by the plugin.
- Actual deployment uses a thin JAR and forgot to copy the provider.
- Or the application server provides Servlet/JPA classes with a different version than the compiled library.

Therefore, investigate the **classpath/module path of the failing process**. If code runs on the full IDE classpath yet breaks in Docker, the key difference lies in packaging/deployment.
## 14. Inspecting JAR contents and fat JAR structure

A useful diagnostic step is confirming **which class is actually in which artifact**.

Example with an ordinary JAR:

```bash
jar tf build/libs/app.jar
```

Look for class `com/example/codec/JsonCodec.class` in the artifact supposed to provide it. However, distinguish between:

- **Thin JAR:** usually contains the application; dependency JARs must be provided separately on the classpath or by a launcher.
- **Fat/uber JAR:** bundles multiple classes/dependencies according to the build mechanism.
- **Spring Boot executable JAR:** typically has `BOOT-INF/classes/` and nested JARs inside `BOOT-INF/lib/`, handled by Spring Boot's launcher.
- **WAR:** may use `WEB-INF/classes/`, `WEB-INF/lib/`, and certain `provided` APIs from the container.

Example structure of a Spring Boot executable JAR:

```text
app.jar
├── BOOT-INF/
│   ├── classes/
│   │   └── com/example/App.class
│   └── lib/
│       ├── spring-core-....jar
│       └── codec-provider-....jar
└── META-INF/
    └── ...
```

A JAR nested inside `BOOT-INF/lib/` **does not become an ordinary classpath entry simply because you run `java -cp app.jar com.example.App`**. For a Spring Boot executable JAR, use the launch mechanism generated by the plugin, typically:

```bash
java -jar app.jar
```

If `java -jar` works while another launch method cannot find classes, review the entry point/launcher and how the classpath is constructed rather than concluding the JAR is corrupted.

### 14.1. With shaded/uber JARs

If using Maven Shade or Gradle Shadow:
- Check whether filters/exclusions dropped classes.
- Check whether relocation renamed the package name.
- Check whether `META-INF/services` was merged properly.
- Check whether digital signatures/module information were affected.
- Check whether merged dependencies have the expected version/API.

A shaded JAR may contain bytecode for `com.example.Codec` while service provider configuration still points to the old package name; in that case, an error may appear in `ServiceLoader` or downstream reflection.

## 15. JPMS: “class exists in file” does not mean the module can read it

Since Java 9, the module system adds a layer of dependency management. A named module may declare:

```java
module com.example.app {
    requires com.example.codec;
}
```

If module `com.example.codec` cannot be found when resolving the module graph, the launcher may report:

```text
java.lang.module.FindException:
    Module com.example.codec not found,
    required by com.example.app
```

This is **not necessarily** `ClassNotFoundException`/`NoClassDefFoundError`. The error is similar in meaning (“missing component”) but occurs during **module resolution** and has its own type.

Comparison:

| Symptom | Common error type | Main issue |
|---|---|---|
| Required named module is not on the module path/image | `FindException` or `ResolutionException`. | Module graph cannot be resolved. |
| Runtime dependency class is not found by loader | `ClassNotFoundException`/`NoClassDefFoundError`. | Class definition is unavailable in the loader context. |
| Package exists but is not exported to caller | `IllegalAccessError` or corresponding access error. | Module access/readability, not merely a missing class. |
| Reflection into a non-open package | `InaccessibleObjectException`. | JPMS strong encapsulation. |
| Class file needs a higher Java than runtime | `UnsupportedClassVersionError`. | Bytecode version, not merely a missing classpath entry. |

Therefore, do not add `--add-opens` to fix every message containing the words “class not found”. `--add-opens` resolves **deep reflection** permissions in certain contexts; it does not bring a nonexistent JAR/module into the runtime.

### 15.1. Module diagnostic commands

```bash
java --list-modules
java --describe-module java.sql
java --show-module-resolution \
  --module-path mods \
  --module com.example.app/com.example.Main
```

Application module names are examples; use actual module descriptors. `--list-modules` reflects modules present in the runtime image; application modules on `--module-path` do not automatically appear in the image list just because files exist on disk.

For a custom runtime created by `jlink`, verify that required modules were linked into the image. If the image lacks dynamically loaded modules, the full JDK may run while the trimmed image fails.

## 16. Java EE/Jakarta: two namespaces are not interchangeable

Migrating from Java EE to Jakarta EE is a typical cause of errors when class names change.

An older library references:

```java
import javax.servlet.Filter;
```

But the new runtime only has:

```java
import jakarta.servlet.Filter;
```

The two types have very similar names and equivalent roles in their respective API generations, yet **do not share the same Java class identity**.

Example error in a Jakarta Servlet container when an old plugin is added:

```text
java.lang.NoClassDefFoundError: javax/servlet/Filter
Caused by: java.lang.ClassNotFoundException:
    javax.servlet.Filter
```

Conversely, a newer Spring Framework/Jakarta library running on an old Servlet container may report missing `jakarta/servlet/Filter`.

How to handle:
1. Identify the actual Servlet/container namespace and version.
2. Identify which JARs reference `javax.servlet` and which JARs reference `jakarta.servlet`.
3. Upgrade **together as a group** the web framework, filters, Servlet/Jakarta API, and container.
4. Ensure `provided` vs bundled scope matches the deployment style.
5. Run integration tests on the **actual target container**, not only unit tests with mocks.

Do not simply add both API JARs to “fix” the error. A class implementing `javax.servlet.Filter` does **not** become `jakarta.servlet.Filter`; having both definitions can even complicate runtime configuration.

### 16.1. Do not replace every javax.*

Some packages such as `javax.sql`, `javax.naming`, `javax.crypto`, and `javax.tools` still belong to Java SE. When classifying errors, identify the API owner/module and corresponding Jakarta version to avoid mass-editing imports outside Jakarta EE scope.

## 17. JAXB/JAX-WS/Java EE modules removed from JDK 11

JDK 8 previously distributed several Java EE/CORBA modules. Under **JEP 320**, JDK 11 removed the related modules, including JAXB and JAX-WS from the Java EE group.

For example, a legacy application:

```java
import javax.xml.bind.JAXBContext;
```

may have compiled/run previously when relying on the JDK to provide it. When upgrading to Java 11+, without adding an appropriate JAXB API/implementation, you may encounter:

```text
java.lang.NoClassDefFoundError:
    javax/xml/bind/JAXBContext
```

or on a dynamic loading path:

```text
java.lang.ClassNotFoundException:
    javax.xml.bind.JAXBContext
```

How to fix:
1. Determine whether the source uses the **JAXB namespace `javax.xml.bind`** or has moved to `jakarta.xml.bind`.
2. Declare the right JAXB API and **implementation/provider** independent of the JDK.
3. Check Java/Jakarta EE/Spring framework version compatibility.
4. Run marshalling/unmarshalling integration tests and check schemas.
5. Do not randomly mix the `javax.xml.bind` API with an implementation that only supports modern `jakarta.xml.bind`.

**Subtle point:** missing the JAXB API and missing a JAXB provider do not manifest identically. If the API class exists while the implementation provider is not found, an exception belonging to the JAXB API or a service provider error may appear, not necessarily `NoClassDefFoundError`. Read the entire stack trace rather than deciding the cause from only the first line.

## 18. Classloader isolation in application servers and plugin hosts

Even when a JAR exists on disk, the classloader used by the failing code may **not see** it.

Common architectures:
- Application servers have a classloader per WAR/EAR/module.
- Plugin hosts create a separate classloader for each plugin.
- OSGi or custom module systems manage visibility themselves.
- Spring Boot loaders handle nested JARs.
- Test runners and IDEs create multiple classloaders for groups of classes.
- Containers load agents/frameworks in a different classloader area from the application.
- Thread context classloader (TCCL) is used by SPI libraries.

Diagram:

```text
Bootstrap / Platform
          |
          v
Application Loader
     /         \
    v           v
Plugin Loader A  Plugin Loader B
    |                 |
 codec-A.jar       codec-B.jar
```

If code in Loader A requests a class only visible in Loader B, the existence of `codec-B.jar` does not make the class load automatically. Each loader has its own delegation/visibility rules.

### 18.1. Inspecting the loader of a successfully loaded class

```java
public class LoaderDiagnostics {
    public static void print(Class<?> type) {
        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());
        System.out.println("Module: " + type.getModule());
        System.out.println("Code source: " +
            (type.getProtectionDomain().getCodeSource() == null
                ? "<unknown>"
                : type.getProtectionDomain()
                      .getCodeSource().getLocation()));
    }
}
```

The example requires Java 9+ because it uses `getModule()`. A value of `getClassLoader() == null` typically relates to the bootstrap loader; it is not an error.

In a production environment, do not arbitrarily print internal paths/classloader info to responses or public logs. Use in a controlled diagnostic environment.

### 18.2. Context ClassLoader

Some libraries obtain the loader via:

```java
ClassLoader loader =
    Thread.currentThread().getContextClassLoader();
```

The TCCL may differ from the loader that defines the library code. That can explain why `Class.forName(name)` succeeds in one module while `Class.forName(name, true, loader)` or service provider discovery on another thread fails.

When diagnosing, record **which loader was used at the call site**. Do not solve by putting the entire JVM classpath into a directory containing every JAR if the architecture genuinely requires plugin isolation.

## 19. ServiceLoader: provider not found differs from class not found

With Java SPI:

```java
import java.util.ServiceLoader;

ServiceLoader<MyService> loader =
    ServiceLoader.load(MyService.class);

for (MyService service : loader) {
    service.run();
}
```

To locate implementations from the classpath, a file is typically required:

```text
META-INF/services/com.example.spi.MyService
```

with contents:

```text
com.example.spi.DefaultMyService
```

With named modules, corresponding module descriptors may be needed:

```java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.MyService
        with com.example.provider.DefaultMyService;
}
```

A consumer module using `ServiceLoader.load(MyService.class)` may need:

```java
module com.example.consumer {
    requires com.example.spi;
    uses com.example.spi.MyService;
}
```

Snippets are illustrative; package/module names must match the real project.

If the provider is missing:
- You may get an empty list without `ClassNotFoundException`.
- If the provider configuration points to a nonexistent/wrong class, you may get `ServiceConfigurationError`.
- If the provider class has a missing dependency, you may get a `LinkageError` nested inside an SPI error.
- If the module is not resolved/linked, `ServiceLoader` may not see the provider even though the artifact is in the directory.

When moving from classpath to module path or creating a custom runtime, check `META-INF/services`, `uses`/`provides`, `--add-modules`, and `jlink --bind-services` as applicable. Do not treat every provider discovery failure as a `ClassNotFoundException`.

## 20. Classes created by code generators/annotation processors

The missing class is sometimes not hand-written source. Generators can produce:
- JPA metamodels.
- MapStruct mapper implementations.
- QueryDSL classes.
- JAXB classes.
- Protobuf/Avro generated types.
- OpenAPI clients.
- DI/container factory classes.

A local build may have generated classes left over from an earlier compilation, whereas a clean CI build or production package lacks them.

How to handle:
1. Identify which class is produced by the generator.
2. Check whether the annotation processor/plugin runs in the right build phase.
3. Check whether the JDK and generator version support new class files/annotations.
4. Check that generated sources are compiled and generated classes are packaged.
5. Run a clean/reproducible build in CI with the right toolchain to eliminate dependence on stale build outputs.

Do not copy generated classes from a previous build into source as a long-term solution; the next regeneration may produce different names or APIs.

## 21. Static initializer fails due to non-classpath causes

A class may contain:

```java
public final class DatabaseBootstrap {
    static final ConnectionPool POOL = createPool();

    private static ConnectionPool createPool() {
        String url = System.getenv("DB_URL");
        if (url == null) {
            throw new IllegalStateException("DB_URL missing");
        }
        return ConnectionPool.connect(url);
    }
}
```

`ConnectionPool` in the example is a hypothetical library type. If `DB_URL` is missing, static initialization may fail; subsequent calls cause `NoClassDefFoundError: Could not initialize class ...` even though the class file is present.

Common root causes:
- Missing configuration or environment variable.
- Database/TLS/IdP unavailable when the class initializes.
- Wrong credentials or configuration file.
- Static field calling code that throws an exception.
- Native library failing to load.
- Class initializer calling another missing dependency.
- Complex circular initialization leading to an invalid state.

**Investigation order:** find the first initialization failure, fix the actual cause, then restart/reload through a safe mechanism. Within the same classloader, a class that has failed initialization is not simply retried just because the environment changed afterward.

## 22. Native libraries and UnsatisfiedLinkError

Another case:

```java
public class NativeCodec {
    static {
        System.loadLibrary("codec_native");
    }
}
```

If the native library is missing or incompatible with the OS/architecture, the JVM may throw:

```text
java.lang.UnsatisfiedLinkError:
    no codec_native in java.library.path
```

This is **not** `ClassNotFoundException`. However, if the error occurs during static initialization and the class is marked erroneous, subsequent uses may exhibit `NoClassDefFoundError: Could not initialize class NativeCodec`.

Check:
- `java.library.path` and how the native library is loaded.
- OS, CPU architecture, ABI/glibc, and container base image.
- File access permissions and related native dependencies.
- JNI compatibility with JDK and library versions.
- The original error message before `NoClassDefFoundError` appeared.

Do not add JARs to the classpath to fix an `UnsatisfiedLinkError` of a native binary.

## 23. “wrong name” class files and package mismatch

A variant of `NoClassDefFoundError` is:

```text
java.lang.NoClassDefFoundError:
    com/example/OldName
    (wrong name: com/example/NewName)
```

This can happen when the name expected by the classloader/JVM does not match the **binary name declared inside the class file**.

Causes:
- Copying/renaming a `.class` file without recompiling with the right package/class name.
- Incorrect bytecode shading/relocation.
- A custom ClassLoader defining a class with a mismatched name.
- An artifact assembled from multiple inconsistent versions.
- Manual manipulation mistakes when packaging a WAR/JAR.

Renaming a file on disk does not change the binary name compiled into the class file. Rebuild from source and inspect the actual artifact rather than continuing to rename `.class` files to test.

## 24. Do not equate version errors with missing class errors

When an application is compiled on JDK 21 and then run on Java 17, you may receive:

```text
java.lang.UnsupportedClassVersionError:
    ... has been compiled by a more recent version
```

This is a separate class format/linkage error type, **not** a situation where the runtime cannot find the class. Do not look for a missing JAR if the bytecode is already there but the Java version is too old.

Similarly:
- `NoSuchMethodError`: class is present, but runtime method signature does not match.
- `NoSuchFieldError`: class is present, but runtime field differs.
- `AbstractMethodError`: binary API/implementation mismatch.
- `IllegalAccessError`: inappropriate type/member/module access permission.
- `IncompatibleClassChangeError`: incompatible class/interface binary form.
- `ClassFormatError`: invalid class file.

Many of these errors belong to `LinkageError` yet have **different remediation paths**. Always record the exact class, method signature, runtime version, and actually resolved dependency.

## 25. Multi-release JARs and differences per JDK

A multi-release JAR may contain:

```text
META-INF/MANIFEST.MF
com/example/Codec.class
META-INF/versions/9/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
```

Depending on the Java runtime, the class loader may select the class file in the corresponding version-specific directory. Therefore:
- Tests on Java 8 may load a different implementation than Java 17.
- A dependency present only in the Java 17 implementation may be missing in production.
- Different compilers/runtimes may encounter different API issues.
- Older JAR-scanning tools may not understand multi-release entries.

Use `jar tf` to inspect and `jdeps --multi-release <version>` for the version to analyze; then **run tests on the real JDK**. Do not conclude from the class residing at the root of the JAR that every JDK takes the same code path.

## 26. “Works in IDE, fails in Docker” is usually a classpath signal

Compare in exact order:

| Item | IDE/test | Container/prod |
|---|---|---|
| Java version/vendor | IDE's JDK | JDK/runtime inside image |
| Entry point | IDE launcher | `java -jar` or custom main |
| Classpath | Project/test dependencies | Packaged artifact and runtime libs |
| Module path | IDE plugin | Runtime module graph |
| Profiles | Dev/test | Production |
| Environment variables | Local secrets | Container env/secret manager |
| Working directory | Source root | Image working directory |
| Native libraries | Developer OS | Container OS/architecture |

If the JAR contains the class yet the container cannot load it, check the launcher/classloader first. If the error occurs only on Java 17, read `Caused by`: it may be JPMS, bytecode, a provider, or a native library, not necessarily a missing JAR.

In particular, a custom runtime built with `jlink` may not contain modules/providers that the full JDK has. `jdeps` helps analyze static dependencies but does not see all classes loaded via reflection or service loading.
## 27. Step-by-step investigation workflow

A useful playbook when production reports `ClassNotFoundException` or `NoClassDefFoundError`:

```text
Receive full exception + cause chain
               |
               v
Is "Could not initialize class" present?
       /                 \
     Yes                  No
      |                    |
      v                    v
Find first static      Which class name is missing?
init failure             |
      |                  v
      |             Is class in
      |             artifact/runtime?
      |                /       \
      |               No       Yes
      |               |         |
      |               v         v
      |       Build/package  Loader visibility,
      |       scopes/exclude module graph, version
      |               |         |
      +---------------+---------+
                      |
                      v
       Reproduce with exact launcher/JDK/image
                      |
                      v
       Fix root cause, do not blindly add JARs
                      |
                      v
       Test startup + functional paths + CI
                      |
                      v
          Canary, monitoring, release
```

### Step 1 — Preserve investigation data

Record:
- **Full** exception class and message.
- Stack trace from the first line through the entire `Caused by` chain.
- Process, pod/container, module, release/commit, and timestamp.
- JDK version/vendor, command line, and actual launcher.
- Action causing the error and reproducibility level.
- Whether the error appeared at startup, first request, background job, or second call.

Do not screenshot only the last line of the log. `NoClassDefFoundError: Could not initialize class` on the second request often needs the log from the first occurrence to see the real cause.

### Step 2 — Classify by message

- `ClassNotFoundException: com.example.X`: identify the API/loader requesting class X.
- `NoClassDefFoundError: com/example/X`: find the missing class definition/resolution path.
- `NoClassDefFoundError: Could not initialize class X`: prioritize the first initialization error.
- `NoClassDefFoundError: wrong name`: suspect class file/package/binary name mismatch.
- `FindException: Module ... not found`: module graph.
- `UnsupportedClassVersionError`: runtime is too old for the class file.
- `InaccessibleObjectException`: reflective module access.
- `ServiceConfigurationError`: provider discovery/loading.

### Step 3 — Verify which artifact contains the class

Use `jar tf` on the deployed artifact, not just files in the source directory. For a Spring Boot executable JAR, check both `BOOT-INF/classes` and `BOOT-INF/lib`. For a WAR, check `WEB-INF/classes`, `WEB-INF/lib`, and the APIs the container must provide.

### Step 4 — Inspect the dependency graph

Maven: `dependency:tree`, `effective-pom`, scopes, exclusions, BOM.

Gradle: `runtimeClasspath`, `dependencyInsight`, subproject configurations, packaging tasks.

Compare the compile/test graph with the production artifact.

### Step 5 — Inspect JVM/module/classloader

Check `java.version`, `java.home`, command line, classloader/TCCL, module path, JDK image modules, and startup options. If the class exists yet is not visible, adding a JAR to the wrong classloader may not help.

### Step 6 — Reproduce and fix one cause

Create a minimal reproduction, changing one factor at a time: runtime dependency, launcher, classloader, Java version, or initializer config. Re-run the exact business path where the error occurred and also check error paths.

### Step 7 — Test on the target deployment

After fixing, ensure startup, integration, message processing, and rare jobs all have coverage. Evaluate startup memory, classloading, and runtime duration. Do not only check a unit test run with a different classpath from production.

## 28. Commands to inspect which classes are loaded from where

On supporting JDKs:

```bash
java -verbose:class -jar app.jar
```

This option prints class loading information and can generate large logs. Since Java 9, unified logging provides an example:

```bash
java -Xlog:class+load=info -jar app.jar
```

To write to a file:

```bash
java -Xlog:class+load=info:file=classload.log \
  -jar app.jar
```

Typical output shows the class name and corresponding source/module per the JVM. Do not assume from log syntax on one JDK that every other JDK prints identically; check `java -Xlog:help` on the running version.

**Safety note:** JVM/classloading logs can reveal absolute file paths, deployment names, or internal parameters. Only enable in a controlled investigation environment, limit retention, and avoid transferring logs containing secrets to public locations.

### 28.1. The jcmd tool

When permitted to attach to an existing JVM, some useful commands are:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
```

`<pid>` is a process ID placeholder. These commands can only be used when the tool/JDK and process access permissions allow. Command line/system properties info may contain sensitive data and requires control over how it is collected and shared.

Do not enable attach or debugging features in production solely to inspect a class if startup logs and less intrusive tools can be used.

## 29. jar, javap, and jdeps: which tool answers which question?

| Tool | Question answered | Limitations |
|---|---|---|
| `jar tf artifact.jar` | Which entries does the artifact contain? | Does not tell whether the classloader sees them. |
| `javap -classpath ... -verbose X` | What constant pool, fields/methods, and class version does class X contain? | Does not prove the runtime dependency is present. |
| `jdeps` | What are the static class/module dependencies of the artifact? | Does not see all reflection/dynamic plugin paths. |
| `mvn dependency:tree` | Which artifacts/versions/scopes did Maven resolve? | Does not itself confirm which JARs were copied into the image. |
| `gradle dependencies` | How does the Gradle configuration resolve? | Test/runtime configurations may differ. |
| `java --list-modules` | Which modules does the runtime image contain? | Does not list every application JAR on the classpath. |
| `java --show-module-resolution` | How are named modules resolved at launch? | Does not replace classloader diagnostics for every library. |
| JVM class load logs | Which classes were loaded and which sources were observed? | High volume; may miss unexecuted paths. |

Example:

```bash
jar tf app.jar
javap -classpath "app.jar:libs/*" \
  -verbose com.example.App
jdeps --missing-deps --recursive \
  --class-path "libs/*" app.jar
```

On Windows, the classpath separator differs (typically `;`), and `grep`/shell quoting also differs. For module-based applications, use the appropriate module path option for the tool and corresponding JDK version.

When `jdeps` reports missing static dependencies, that is a strong clue but not a complete solution. An artifact may be needed only in the runtime container, or there may be dynamic dependencies that `jdeps` cannot observe.

## 30. Inspecting the actually deployed artifact

A common situation:

```text
CI workspace:
  build/libs/app.jar
  build/libs/dependency.jar

Docker image:
  /app/app.jar  (only copies one file)
```

Tests run with the Gradle/Maven classpath have both JARs, while the container only has `app.jar`. As a result, production fails even though tests succeeded.

Steps:
1. Identify the running image digest/tag.
2. Check the actual launch command and working directory.
3. Check JARs, libs directories, and manifests inside the image.
4. Compare checksums against the artifact produced by CI.
5. Verify the runtime Java version inside the container.
6. Compare the dependency tree with the runtime classpath/package.
7. Fix the Dockerfile/build packaging and test the **new image** itself.

Do not take a running container image and manually add a JAR inside it as a long-term fix; the next deployment will lose the change and lack provenance.

## 31. Spring Boot major version upgrade scenario

Suppose an application moves from Spring Boot 2.x/JDK 8 to Spring Boot 3.x/JDK 17. An internally written library still contains `javax.servlet.*` imports.

After migration, the application may report:

```text
java.lang.NoClassDefFoundError:
    javax/servlet/http/HttpServletRequest
```

Although Spring Boot 3 has web dependencies, the target APIs reside in `jakarta.servlet.*`, not `javax.servlet.*`.

Handling workflow:
1. Inspect the dependency graph and determine which library was compiled against the old Java EE API.
2. Check whether the Servlet container/framework follows the Jakarta target.
3. Upgrade/recompile custom filters/controllers/interceptors to match the target namespace.
4. Upgrade related third-party dependencies, not merely adding the Jakarta Servlet API.
5. Check dependency scopes and API/provider bundling.
6. Run integration tests that actually initialize web contexts/filter chains.

When upgrading Spring Boot 3 → Boot 4 or Spring Security 6 → 7, errors may come from other framework/dependency changes; read the release notes for that exact version rather than assuming every classloading error is due to `javax/jakarta`.

## 32. Logging or JSON library missing when switching builds scenario

Suppose code uses a facade while the runtime lacks an implementation/adapter:
- Compilation succeeds because the API JAR is present.
- The framework reaches a path using the provider.
- The runtime may fail to find the provider or emit logging/JSON initialization messages.

It does not always become `ClassNotFoundException`. There may be a warning about an absent provider, a `ServiceConfigurationError`, or a framework failure. When seeing a class name in the log, confirm **whether the framework is looking for an API, an implementation, or a service provider**.

For example, an API library declares a module while the runtime provider is missing. The solution is adding a supported implementation in the proper runtime configuration, verifying service metadata, and avoiding mixing multiple incompatible implementations in the same classloader.

## 33. Custom classloader loading plugins scenario

A plugin host receives a class name from configuration:

```java
public interface Plugin {
    void execute();
}
```

A simplified loader:

```java
public final class PluginHost {
    public static Object loadPlugin(
            String className, ClassLoader pluginLoader)
            throws ClassNotFoundException,
                   ReflectiveOperationException {
        Class<?> type = Class.forName(
            className, true, pluginLoader);
        return type.getDeclaredConstructor().newInstance();
    }
}
```

The example signature declares both `ClassNotFoundException` and its superclass `ReflectiveOperationException`, so **both do not need to be listed** in real code; `throws ReflectiveOperationException` alone can be used. Additionally, production should use `Plugin.class.isAssignableFrom(type)` and controlled casting to enforce the plugin API rather than returning `Object`.

Possible errors:
- `ClassNotFoundException`: the loader cannot find the implementation class.
- `NoClassDefFoundError`: the plugin class is found, but its dependency is missing.
- `ClassCastException`: the `Plugin` API was loaded from two different classloaders, yielding two incompatible class identities.
- `InvocationTargetException` or initializer/linkage error: constructor/static initialization/provider logic failed.
- `ServiceConfigurationError`: SPI metadata/provider is misconfigured.

A proper fix requires managing classloader delegation, API sharing, dependency isolation, and lifecycle. Do not simply move every JAR to the system classpath, because that can break plugin isolation.

## 34. ClassNotFoundException is not always thrown from Class.forName

APIs that may be involved:
- `Class.forName(String)`.
- `Class.forName(String, boolean, ClassLoader)`.
- `ClassLoader.loadClass(String)`.
- Reflection/framework utilities that load classes by name.
- JDBC driver/plugin code using a driver/provider name from configuration.

Some frameworks catch `ClassNotFoundException` and wrap it:

```text
org.example.ConfigurationException:
    Cannot create datasource provider
Caused by: java.lang.ClassNotFoundException:
    com.vendor.jdbc.Driver
```

Therefore, the top-level exception may not carry the name `ClassNotFoundException`. You must read the cause chain to understand **which class**, **which loader**, and **which code path** led to the error.

On the other hand, calling literals such as `SomeClass.class` or `new SomeClass()` does not mean the compiler forces you to declare `throws ClassNotFoundException`. The JVM will use bytecode resolution mechanisms and corresponding linkage failures.

## 35. Reproducing the error from a clean environment

A reliable reproduction needs to eliminate “works because the developer machine already has the library” factors:

1. Use fresh/clean build outputs and pinned dependencies.
2. Record exact JDK version and vendor.
3. Use the same launcher as production: `java -jar`, classpath, or module path.
4. Run the packaged artifact, not directly from the IDE.
5. Use a matching image for OS/architecture.
6. Provide required config/env without using production secrets.
7. Trigger the exact code path: endpoint, job, SPI provider, or static initialization.
8. Save the full stack trace and artifact version.
9. Compare the failing run against the passing run by **one variable** at a time.
10. Turn the reproduction into an integration/regression test when appropriate.

You do not need to test the entire production system just to find a missing class if a small test simulating the classloader/module path suffices; however, a fix must be verified on the target image/runtime before release.

## 36. How to write integration tests to prevent regressions

Some tests that should be added after fixing:

| Test | Objective |
|---|---|
| Packaged JAR startup | Prove launcher and runtime classpath are valid. |
| WAR/container deployment | Prove API/container/provider compatibility. |
| Plugin discovery | Prove loader/TCCL/SPI metadata are right. |
| JAXB/JSON round trip | Prove runtime API and implementation work. |
| Class initialization | Prove static config/resources are complete. |
| ServiceLoader/provider iteration | Prove providers exist in the runtime image. |
| JDK matrix | Prove running on the committed baseline JDK. |
| Custom jlink image smoke/integration | Prove required Java modules/providers are present. |
| Native code path | Prove binary matches container/OS/architecture. |
| Scheduled/rare job | Prove rarely used classloading paths were executed. |

A test that only checks:

```java
assertNotNull(com.example.App.class);
```

is not enough to guarantee all app dependencies and initializers work. You must execute **behavior** that touches the failing classloading path, especially for optional dependencies or reflection.

## 37. Do not fix errors by catching Throwable and ignoring it

An anti-pattern:

```java
try {
    startApplication();
} catch (Throwable ignored) {
    // continue startup
}
```

This approach can cause the application to report ready while critical components have failed, and even hide serious `Error`s.

There are plugin systems that genuinely need error handling to isolate non-essential plugins. In that case:
- Catch only at the **plugin boundary** designed for isolation.
- Log the full error type and cause into a safe logging system.
- Mark the plugin unavailable; do not report false success.
- Do not continue using a class that failed initialization in the same loader assuming it recovered on its own.
- Do not swallow `OutOfMemoryError`/serious errors and continue normally.
- Clearly define policy for required versus optional plugins.

For core services, **fail fast and rollback/forward-fix** is usually safer.

## 38. Quick decision table when an error occurs

| First/key message | Priority suspicion | What to do first |
|---|---|---|
| `ClassNotFoundException: x.Y` | Loader cannot see class requested by name. | Check name, classloader, classpath, and artifact. |
| `NoClassDefFoundError: x/Y` | Dependency/definition missing during linkage. | Find class provider and runtime packaging. |
| `NoClassDefFoundError: Could not initialize class X` | Class failed initialization. | Find root `ExceptionInInitializerError` or initial `Error`. |
| `NoClassDefFoundError: wrong name` | Binary name/path mismatch. | Rebuild artifact, check shading/renaming. |
| `ClassNotFoundException: javax.xml.bind...` after Java 11 | JAXB is no longer supplied automatically by the JDK. | Declare proper API/provider artifacts. |
| `NoClassDefFoundError: javax/servlet/...` after Jakarta migration | Legacy library uses javax on a jakarta runtime. | Upgrade web/library/container stack together. |
| `NoClassDefFoundError: jakarta/servlet/...` | Runtime/container lacks proper Jakarta API. | Check Servlet runtime and scopes. |
| `FindException: Module ... not found` | Module graph does not resolve. | Check module path/image/module-info. |
| `InaccessibleObjectException` | Reflection blocked by module. | Upgrade library, review scoped `opens`/workarounds. |
| `UnsupportedClassVersionError` | Runtime JDK is lower than class file requires. | Compare major version and release target. |
| `NoSuchMethodError` | Dependency binary API mismatch. | Compare versions/classpath and method descriptor. |
| `UnsatisfiedLinkError` | Native library/ABI/architecture missing. | Check native packaging, OS, and linker. |
| `ServiceConfigurationError` | SPI provider discovery/initialization error. | Inspect service metadata and provider/module visibility. |

The table is **directional**. Messages may be wrapped in other exceptions by frameworks, and a system may experience multiple causes simultaneously.

## 39. Template for recording an incident so others can reproduce it

```yaml
incident: JAVA-COMPAT-CLASSLOAD-001
component: reporting-worker
artifact: reporting-worker.jar
release: "example-release-id"
jdk:
  version: "17"
  vendor: "example-distribution"
runtime:
  launcher: "java -jar reporting-worker.jar"
  packaging: "container"
exception:
  topLevel: "java.lang.NoClassDefFoundError"
  message: "com/example/codec/ReportCodec"
  rootCause: "ClassNotFoundException"
observedAt:
  action: "scheduled report export"
  environment: "staging"
evidence:
  - "full stack trace (secrets redacted)"
  - "runtime dependency tree"
  - "deployed artifact inventory"
suspectedCause:
  kind: "runtime dependency omitted"
resolution:
  type: "build packaging fix"
  tests:
    - "packaged-jar-startup"
    - "report-export-integration"
owner: "reporting-team"
status: "investigating"
```

This is an example diagnostic record, not a mandatory format of the JVM or any tool. Replace placeholders with real data; do not put passwords, tokens, or sensitive information in logs, configs, or public tickets.

## 40. Migration workflow to prevent classloading failures

### Step 1 — Lock baseline and target

Record source/target JDK, minimum supported runtime, framework/BOM/Servlet container, and packaging. For Java EE/Jakarta, clearly define the target API namespace.

### Step 2 — Inventory dependencies by runtime

Compare compile/test/runtime graphs. Distinguish `compileOnly`, `provided`, `runtimeOnly`, optional dependencies, and service providers. Clearly note which JARs are supplied by the container.

### Step 3 — Upgrade tightly coupled libraries

For example, Servlet/REST/CDI/JPA providers, annotation processors, bytecode libraries, and native integrations. Do not merely change imports in the application while keeping old implementations.

### Step 4 — Lock down the execution method

Choose `java -jar`, classpath, or module path appropriate for the artifact. For Spring Boot executable JARs, use the launcher provided by the plugin. For custom jlink images, confirm modules/providers are linked.

### Step 5 — Test dynamic loading paths

Exercise ServiceLoader, reflection, plugin loading, serialization/JAXB, scheduled jobs, and logic with static initialization; ordinary unit tests may not have reached them.

### Step 6 — Verify on the real runtime/image

Run integration tests in a container/server similar to production, not just the IDE. Measure classloading/initialization failures and compare JDK runtime versions.

### Step 7 — Remove workarounds in a controlled manner

If temporary flags, dependency overrides, or old API JARs were added during migration, identify the root cause and removal criteria. Do not keep workarounds forever just because they make the error disappear in one environment.

### Step 8 — Release/rollback and observe

Save artifact checksum, Java version, dependency graph, secret-redacted logs, owner, canary metrics, and rollback plan. A packaging change may require rolling back the entire container image, not just the JAR.

## 41. Misconceptions to avoid

**“ClassNotFoundException and NoClassDefFoundError are the same.”** No. They differ in `Throwable` branch, trigger mechanism, and diagnosis.

**“NoClassDefFoundError is always a missing JAR.”** No. It may be failed class initialization or a wrong binary name.

**“The class file being inside the JAR means the JVM can always load it.”** No. Loader visibility, module resolution/access, and artifact format also matter.

**“A green Maven/Gradle build proves the production classpath is complete.”** No. Test runtime may contain different dependencies from the production package.

**“Seeing ClassNotFoundException in Caused by means just add the JAR.”** Not necessarily. The JAR may be present but in a different loader, module unresolved, or launched improperly.

**“Just put both javax and jakarta APIs on the classpath together.”** Does not fix the difference in Java type identity; you must choose a compatible generation of runtime/framework.

**“Use --add-opens to fix class not found.”** No. This flag is for module reflective access; it does not create missing classes.

**“Clearing all caches/local builds will fix it automatically.”** A clean build can expose the real cause; you need to fix dependencies/packaging, not just clear caches.

**“Just catch Throwable and continue.”** Can hide serious initialization failures and create a falsely healthy application state.

**“Running one endpoint is enough to confirm all classes can load.”** Dynamic dependencies, plugins, scheduled jobs, and exception paths may not have been triggered yet.

## 42. Diagnostic and acceptance checklist

- [ ] Recorded exact exception type, message, stack trace, and full cause chain.
- [ ] Distinguished missing definition from `Could not initialize class`.
- [ ] If initialization failed, found the **first** failure.
- [ ] Identified the binary name and corresponding `.class` file, including nested classes.
- [ ] Identified the class/provider artifact supposed to contain the class.
- [ ] Inspected the **deployed** artifact, not just local build outputs.
- [ ] Checked Maven/Gradle scopes, exclusions, BOM, and runtime graph.
- [ ] Compared test classpath against production runtime classpath.
- [ ] Checked launcher: `java -jar`, classpath, module path, WAR/container.
- [ ] Recorded JDK runtime version, vendor, module list, and container image.
- [ ] Checked classloader/TCCL visibility when plugin/server isolation exists.
- [ ] Distinguished `javax`/`jakarta`, JDK 11 JAXB removals, and Java SE APIs that still retain `javax`.
- [ ] Checked SPI service files, JPMS `uses`/`provides`, and `jlink` if relevant.
- [ ] Checked generated code/annotation processing if the class is produced by a generator.
- [ ] Distinguished binary API/version/native errors from class-absent errors.
- [ ] Used `jar`, `javap`, `jdeps`, and JVM class-load logs where appropriate.
- [ ] Reproduced on an image/launcher close to production.
- [ ] Avoided adding random JARs, unwarranted `--add-opens`, or swallowing `Throwable` to hide errors.
- [ ] Have integration/regression tests hitting the exact classloading path that failed.
- [ ] Recorded owner, evidence, and rollback/forward-fix plan.

## 43. References

- [Java SE API — ClassNotFoundException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassNotFoundException.html): defines the checked exception and class-loading-by-name cases.
- [Java SE API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NoClassDefFoundError.html): defines the error when the definition of a class needed by the JVM/classloader cannot be found.
- [Java SE API — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ExceptionInInitializerError.html): exception occurring during static initialization.
- [Java SE API — LinkageError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LinkageError.html): group of linkage errors in the JVM.
- [Java Virtual Machine Specification, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): loading, linking, initialization, and module/classloader semantics.
- [Java Language Specification — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): conditions triggering class initialization.
- [ClassLoader API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, resource lookup, and classloader behavior.
- [Class API — forName](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): loading a class by name and initialize/classloader options.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module resolution, module path.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): why JAXB/JAX-WS APIs are no longer bundled by JDK 11.
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): runtime image and `rt.jar`/`tools.jar` layout changes.
- [JDK 21 jdeps Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): analyzing class/module dependencies.
- [JDK 21 javap Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): inspecting bytecode and class file metadata.
- [JDK 21 Java Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): classpath, module path, and JVM diagnostics options.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): identifying resolved runtime dependencies.
- [Gradle Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): runtimeClasspath and dependencyInsight.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): API namespace/version to check against when moving from Java EE to Jakarta.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): packaging, executable JARs, and framework/runtime dependency management.

## Conclusion

**ClassNotFoundException** usually indicates that a call to find/load a class by name could not find the class within the scope of the classloader used. **NoClassDefFoundError** is a runtime linkage/initialization error: it can arise when the JVM needs a class definition that is absent, when the binary name does not match, or when the class previously failed initialization and was marked erroneous. Therefore, the two errors can share the cause of a runtime classpath missing a dependency, yet may also require completely different remediation paths.

In Java migration, start with the **entire cause chain**, identify the load–link–initialize phase and the actual process/classloader that failed. Then inspect the deployed artifact, Maven/Gradle runtime graph, classpath/module path, JDK/Jakarta compatibility, ServiceLoader, generated code, and native libraries. Reproduce using the exact launcher/runtime image, fix the root cause instead of recklessly adding JARs or opening modules, and then lock down the result with integration tests and evidence for the next deployment.
