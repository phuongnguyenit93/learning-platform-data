# JDK structure after version 8 and the changes to rt.jar or tools.jar

When upgrading from Java 8 to Java 11, 17, 21, or newer, errors can appear directly in scripts/builds: a plugin looks for `lib/tools.jar`, an IDE opens `jre/lib/rt.jar`, or a Dockerfile copies the `jre/` directory inside the JDK. Those paths existed on JDK 8 but are no longer valid starting in JDK 9.

**JEP 220 – Modular Run-Time Images** and **JPMS (Java Platform Module System)** change how platform components are organized. Java SE classes and the compiler still exist in appropriate JDKs, but are no longer packaged as `rt.jar` and `tools.jar`. Instead, there are modular runtime images, modules such as `java.base` and `jdk.compiler`, and resource access via `jrt:`.

This lesson distinguishes layouts before and after JDK 8, the roles of `lib/modules`, `jmods`, `jimage`, and `jlink`; guides updating Maven/Gradle/Dockerfiles, choosing the Java Compiler API, diagnosing class loaders, and verifying the runtime environment during Java Advance Compatibility Migration.

## 1. JDK, JRE, and runtime image are not synonymous

- **JDK:** a distribution containing a Java runtime and development tools, such as `java`, `javac`, `jar`, and `javadoc`.
- **JRE:** an environment capable of running Java programs; it does not necessarily include the compiler/tooling.
- **Runtime image:** the files, native libraries, module data, and launcher that form a specific execution environment, whether provided by the JDK or customized with `jlink`.

A JDK can contain a runtime **without having a subdirectory named `jre`**. When upgrading from JDK 8, what needs checking is the actual Java executable, module availability, and version, rather than requiring a path like `jdk/jre/lib/rt.jar`.

## 2. Typical JDK 8 structure

```text
jdk8/
├── bin/
│   ├── java
│   ├── javac
│   └── jar
├── include/
├── lib/
│   ├── tools.jar
│   └── dt.jar
└── jre/
    ├── bin/java
    └── lib/
        ├── rt.jar
        ├── resources.jar
        ├── charsets.jar
        ├── ext/
        └── security/
```

Conceptual diagram; vendor distributions and operating systems may vary in native libraries and additional files.

| File/directory | Traditional role |
|---|---|
| `jre/lib/rt.jar` | Holds many Java SE runtime classes/resources. |
| `lib/tools.jar` | Holds many implementation classes for JDK tools, especially the compiler. |
| `jre/lib/ext/` | Legacy extension mechanism allowing extensions to be loaded from a special location. |
| `lib/endorsed/` | Endorsed standards override mechanism prior to Java 9. |
| `jre/lib/security/` | Security configuration and data files. |
| `bin/java`, `bin/javac` | Launcher and compiler. |

Legacy scripts often check:

```bash
test -f "${JAVA_HOME}/jre/lib/rt.jar"
test -f "${JAVA_HOME}/lib/tools.jar"
```

These are physical file checks specific to JDK 8, **not a way to determine whether a modern JDK supports Java or includes a compiler**.

## 3. How was rt.jar historically used?

On JDK 8, many Java SE classes lived in `rt.jar`. Example:

```java
import java.net.URL;

public class LocatePlatformClass {
    public static void main(String[] args) {
        URL location = ClassLoader.getSystemResource(
                "java/lang/Class.class");
        System.out.println(location);
    }
}
```

Typical output on JDK 8:

```text
jar:file:/opt/jdk8/jre/lib/rt.jar!/java/lang/Class.class
```

Some legacy tools relied on this path to:
- Browse platform classes with `JarFile` or `ZipFile`.
- Copy `rt.jar` into application artifacts.
- Build source/API indexes for IDEs.
- Infer the JDK location from the resource URL.
- Add `rt.jar` to classpath/bootclasspath for compilation.

These approaches depend on **packaging details**. Typical applications do not need to declare `rt.jar` to use `java.lang`, `java.util`, or supported Java SE APIs.

## 4. tools.jar and legacy Maven configurations

A commonly seen legacy configuration:

```xml
<dependency>
    <groupId>jdk.tools</groupId>
    <artifactId>jdk.tools</artifactId>
    <version>1.8</version>
    <scope>system</scope>
    <systemPath>${java.home}/../lib/tools.jar</systemPath>
</dependency>
```

On JDK 8, a process running within a JDK could have `java.home` pointing to `jdk8/jre`, so `../lib/tools.jar` happened to resolve. From JDK 9+, `java.home` typically points to the root of the runtime image and `tools.jar` no longer exists. Builds can fail even though `javac` still works.

Do not solve this by copying an old `tools.jar` or creating a dummy artifact named `jdk.tools`. Determine precisely whether the plugin/code needs the compiler API or implementation internals, then migrate to a supported mechanism.

## 5. JDK 9 adopts modular run-time images

JEP 220 changes the runtime layout starting in Java 9:

- Platform classes/resources are stored in a **module image**, without legacy internal JARs such as `rt.jar`, `tools.jar`, and `dt.jar`.
- In many OpenJDK builds, module data resides in `lib/modules`; this is an implementation-specific format, **not a ZIP/JAR**.
- The `jrt:` URI and JRT filesystem allow accessing classes/resources in the image without opening physical JAR files.
- Operator-editable configuration is organized more clearly under `conf/`.
- Tools and APIs are partitioned into appropriate modules such as `jdk.compiler` and `jdk.jlink`.

Mistakes to avoid:

```text
rt.jar -> java.base.jar        (not a conversion rule)
tools.jar -> jdk.compiler.jar (does not exist as a fixed replacement JAR)
```

Do not open `lib/modules` with `JarFile` or add it to the classpath as a dependency.

## 6. JDK 9–10 vs. JDK 11 and later

| Era | Runtime packaging | Key points to remember |
|---|---|---|
| Java 8 and earlier | JDK typically contained a nested JRE at `jdk/jre/`; JRE could also be downloaded separately. | `rt.jar` in JRE, `tools.jar` in JDK. |
| JDK 9–10 | Oracle distributed separate JDK/JRE modular images, no longer nesting a JRE inside the JDK in the old layout. | Shared `bin/`, `conf/`, `lib/` directory pattern. |
| JDK 11+ | Oracle JDK no longer offers a separate standalone JRE download in the old form, yet the JDK still contains the runtime; custom images can be built. | Do not hardcode `jdk/jre`, `rt.jar`, or `tools.jar`. |
| Other distributions | Vendors may publish their own runtime packages/custom images. | Verify each actual vendor/version and license. |

Saying "JDK 11 has no JRE" is inaccurate if taken to mean **Java cannot run**. Accurate statement: there is no longer a standalone JRE distribution in the legacy Oracle model, yet the runtime remains inside the JDK or a custom image.

## 7. Typical modern JDK structure

```text
jdk-21/
├── bin/
│   ├── java
│   ├── javac
│   ├── jar
│   ├── jdeps
│   ├── jlink
│   ├── jmod
│   └── jimage
├── conf/
│   └── security/
│       └── java.security
├── include/
├── jmods/
│   ├── java.base.jmod
│   ├── java.logging.jmod
│   └── jdk.compiler.jmod
├── legal/
└── lib/
    ├── modules
    ├── src.zip
    └── ...
```

This illustrates a full JDK; custom runtimes may omit `javac`, `jmods/`, or `src.zip`.

| Path | Role | Limitations |
|---|---|---|
| `bin/` | Executables included in the image. | Never assume every tool exists in a jlink image. |
| `conf/` | Configuration files editable by operators. | Do not infer truststore paths from legacy layouts. |
| `lib/modules` | Linked module data used by the runtime. | Not a JAR or classpath entry. |
| `jmods/` | JMOD inputs for linker/tools. | Not for use as runtime JARs. |
| `include/` | Native/JNI headers. | Not necessarily present in minimal runtimes. |
| `lib/src.zip` | Source code for reading/debugging when supplied by the distribution. | Not required to run applications. |
| `legal/` | Notices/licenses. | Important when redistributing images. |

## 8. Which modules hold what used to live in internal JARs?

| Role | Typical module | Example |
|---|---|---|
| Core foundation | `java.base` | `java.lang`, `java.util`, I/O. |
| Logging | `java.logging` | `java.util.logging`. |
| JDBC | `java.sql` | `java.sql.Connection`. |
| XML | `java.xml` | DOM, SAX, JAXP. |
| Standard Compiler API | `java.compiler` | `javax.tools.JavaCompiler`. |
| Compiler implementation | `jdk.compiler` | `javac` and implementation classes. |
| Javadoc | `jdk.javadoc` | `javadoc`. |
| Dependency analysis | `jdk.jdeps` | `jdeps`. |
| Runtime image tools | `jdk.jlink` | `jlink`, `jmod`, `jimage`. |
| Attach tools | `jdk.attach` | `com.sun.tools.attach.VirtualMachine`. |

**Package names do not match module names.** For example, `javax.tools` remains the Java SE Compiler API, not a Jakarta package; never bulk-replace `javax.*`.

## 9. Checking modules present in a JDK/image

```bash
java --list-modules
java --describe-module java.base
java --describe-module jdk.compiler
```

Sample excerpt from `--list-modules` on JDK 21:

```text
java.base@21
java.compiler@21
java.logging@21
java.sql@21
jdk.compiler@21
jdk.jlink@21
```

The list depends on the image; a custom runtime may contain fewer modules. If a needed module is absent, creating a custom `rt.jar` cannot fix it.

## 10. jrt: instead of jar:file: when inspecting platform classes

With this program:

```java
System.out.println(
    ClassLoader.getSystemResource("java/lang/Class.class"));
```

JDK 8 may return:

```text
jar:file:/opt/jdk8/jre/lib/rt.jar!/java/lang/Class.class
```

JDK 9+ may return:

```text
jrt:/java.base/java/lang/Class.class
```

Casting to `JarURLConnection` like:

```java
URL location = ClassLoader.getSystemResource(
    "java/lang/Class.class");
java.net.JarURLConnection jar =
    (java.net.JarURLConnection) location.openConnection();
```

can fail on JDK 9+, because the URL no longer uses `jar:`. Fixes:
- To read a resource: use `getResourceAsStream` or open the URL stream.
- To find the module containing a class: use `Class.getModule()`.
- To browse platform classes: use the JRT filesystem.
- To inspect supported Java SE APIs: use the compiler/Javadoc rather than scanning physical JARs.

## 11. JRT filesystem via java.nio.file

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;

public class JrtReader {
    public static void main(String[] args) throws Exception {
        FileSystem fs = FileSystems.getFileSystem(
            URI.create("jrt:/"));
        Path classFile = fs.getPath(
            "/modules/java.base/java/lang/Object.class");
        System.out.println(Files.exists(classFile));
        System.out.println(Files.size(classFile));
    }
}
```

On JDK 9+, the path `/modules/java.base/...` is a **logical path inside the JRT filesystem**, not an actual directory `${JAVA_HOME}/modules/java.base`.

Do not confuse:
- Resource URI `jrt:/java.base/java/lang/Object.class`.
- NIO JRT path `/modules/java.base/java/lang/Object.class`.

Business applications rarely need to scan the entire platform; this approach is primarily for IDEs or class-analysis tools.

## 12. jimage, jmods, and lib/modules

On a full JDK, inspect an image:

```bash
jimage list "$JAVA_HOME/lib/modules"
```

On Windows PowerShell, this can be run in one line:

```powershell
& "$env:JAVA_HOME\bin\jimage.exe" list "$env:JAVA_HOME\lib\modules"
```

Inspect a JMOD:

```bash
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
```

| Component | Purpose |
|---|---|
| `lib/modules` | Runtime module data used by the JVM. |
| `jmods/*.jmod` | Artifacts typically used as inputs to `jlink`. |
| `app.jar` | Application JAR; `java -jar` remains supported. |

A JMOD is not a JAR to add to `-cp`. Nor are `jimage`/`jmod` required in a stripped-down image used solely to run applications.
## 13. Replacing tools.jar with the supported Java Compiler API

If an application must compile Java source at runtime, do not add `tools.jar` manually. The standard API is `javax.tools` in the `java.compiler` module:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class EmbeddedCompiler {
    public static void main(String[] args) {
        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                "No system Java compiler in this runtime");
        }

        int result = compiler.run(
            null, System.out, System.err, "Hello.java");

        if (result != 0) {
            throw new IllegalStateException(
                "javac exited with " + result);
        }
    }
}
```

This example assumes `Hello.java` exists in the working directory. The program must run on a runtime image that includes the compiler implementation.

On JDK 9+:
- `java.compiler` provides the standard API for application code.
- `jdk.compiler` provides the compiler implementation in the JDK.
- A custom runtime image containing only `java.base` can cause `ToolProvider.getSystemJavaCompiler()` to return `null`.

Therefore, having `bin/java` does not automatically mean a compiler is present. If the application generates Java source at runtime, intentionally include the compiler module/toolchain in the deployment or move the compilation step to a build service.

### 13.1. Do not confuse the compiler API with compiler internals

Code using `com.sun.tools.javac.*` can fail starting in Java 9 even when `jdk.compiler` is present, because many implementation packages are not publicly exported (`exports`). Other APIs such as the Attach API reside in their own module, `jdk.attach`.

There is no rule stating "if you imported a class from `tools.jar`, just add `requires jdk.compiler`". Check each class and its support status. Prefer official APIs, upgrade plugins/annotation processors, and avoid keeping `--add-exports` as a long-term workaround.

## 14. java.home differs from JAVA_HOME

Two values are frequently confused:
- `JAVA_HOME` is an environment variable managed by the user, shell, CI, or build tool.
- `java.home` is a JVM system property describing the Java runtime image of the running process.

Check directly:

```java
public class RuntimeHome {
    public static void main(String[] args) {
        System.out.println("JAVA_HOME = "
            + System.getenv("JAVA_HOME"));
        System.out.println("java.home = "
            + System.getProperty("java.home"));
        System.out.println("java.version = "
            + System.getProperty("java.version"));
    }
}
```

On JDK 8, `java.home` for a process launched from the JDK often points to the nested JRE. On JDK 9+, it usually points to the root of the runtime image. Meanwhile, `JAVA_HOME` might point to a **different JDK** than the JVM actually running.

Do not use `java.home + "/../lib/tools.jar"` to locate the compiler. Use `ToolProvider.getSystemJavaCompiler()` or explicit toolchain/JDK executable configuration.

## 15. Class loader changes after JPMS

JDK 9+ alters class loader implementations:
- The application/system class loader is no longer guaranteed to be a `URLClassLoader`.
- The JDK 8 extension class loader was replaced by the **platform class loader**.
- Never assume every Java SE class is defined by the bootstrap class loader.
- Class/module resolution and `exports`/`opens` access rules become critical.

Legacy code:

```java
import java.net.URLClassLoader;

public class CastSystemLoader {
    public static void main(String[] args) {
        URLClassLoader loader = (URLClassLoader)
            ClassLoader.getSystemClassLoader();
        System.out.println(loader.getURLs().length);
    }
}
```

can throw `ClassCastException` on JDK 9+. Never treat the concrete implementation type of the system class loader as a contract.

From Java 9+, an API exists:

```java
ClassLoader platform =
    ClassLoader.getPlatformClassLoader();
```

However, do not assume all platform classes are defined by that loader. If you need to load external plugin JARs, the application can create and manage **its own** `URLClassLoader` instead of casting the system loader.

## 16. Retrieving the module containing a class

Instead of inferring from `rt.jar`:

```java
public class ClassModules {
    public static void main(String[] args) {
        System.out.println(String.class.getModule().getName());
        System.out.println(
            java.sql.Connection.class.getModule().getName());
    }
}
```

On JDK 9+, this can print:

```text
java.base
java.sql
```

`Class.getModule()` is a Java 9+ API. If Java 8 compile compatibility is still needed, design a separate code path or use reflection only where truly necessary.

## 17. The classpath still runs normally

Having JPMS does not force every application to become a named module.

Traditional applications:

```bash
java -cp "app.jar:libs/*" com.example.Main
```

On Windows, the classpath typically uses semicolons:

```powershell
java -cp "app.jar;libs/*" com.example.Main
```

Classes on the classpath belong to the **unnamed module**. Java still supplies the appropriate Java SE modules according to resolution rules. There is no need to add `rt.jar` or `tools.jar` to the classpath.

Modular applications:

```bash
java --module-path mods \
  --module com.example.app/com.example.Main
```

Named modules, automatic modules, and the classpath can coexist in some architectures, yet package/module conflicts and the module graph must be managed. Moving to the module path is not a drop-in swap for every legacy classpath entry.

## 18. Extension mechanism and endorsed standards were removed

On Java 8, `jre/lib/ext/`, `java.ext.dirs`, `lib/endorsed/`, and `java.endorsed.dirs` could load JARs or override APIs via legacy mechanisms.

From JDK 9 onward, these mechanisms are removed. In documented releases, if the directory or corresponding system property still exists, the launcher/compiler may refuse to start or report errors.

Remediation:
1. Identify which JARs previously lived in `ext/`.
2. Move them into explicit dependencies on the classpath/module path.
3. Remove legacy directories and properties from images and startup scripts.
4. If endorsed overrides were used, evaluate upgradeable modules or API replacements suited to the target runtime.
5. Test classloader and API compatibility afterward.

Do not use `-Xbootclasspath/p` to add platform classes from JDK 8 into a newer JDK. Legacy bootclasspath-prepend mechanisms are no longer supported as before. The flags `--patch-module`, `--add-opens`, and `--add-exports` serve specific purposes rather than acting as general replacements for the extension mechanism.

## 19. Security configuration and conf/

Some JDK 8 scripts used paths like:

```text
${JAVA_HOME}/jre/lib/security/java.security
${JAVA_HOME}/jre/lib/security/java.policy
```

With modular images, user-editable configuration files typically live under:

```text
${JAVA_HOME}/conf/security/java.security
${JAVA_HOME}/conf/security/java.policy
```

This does not mean every file in `lib/security/` moved to `conf/security/`. Truststores, certificate data, and security resources vary by JDK/version/vendor. When a custom truststore is required, use supported JVM/application configuration and manage it as an artifact with its own lifecycle.

Why caution is required:
- Editing security properties can affect TLS, certificate path validation, or allowed algorithms.
- Copying `java.security` from JDK 8 onto a newer JDK can overwrite modern security policies.
- For `jlink`-built images, configurations and security providers must be verified inside that exact image.

## 20. Choosing javac and distinguishing compiler target from runtime

Even though `tools.jar` is gone, a full JDK still includes `javac`. Check:

```bash
java -version
javac -version
```

The two commands can resolve to different JDKs when a machine has multiple Java installations. Maven/Gradle can also use Toolchains to select a different compiler from the JVM running the build.

A real incident:
- CI runs Maven/Gradle on JDK 21.
- Java source compiles targeting 17.
- Unit tests run on JDK 21.
- Production runs JDK 17.

If zero tests execute on Java 17, claiming "verified Java 17 compatible" lacks sufficient evidence.

### 20.1. Stop using rt.jar as bootclasspath

An old command:

```bash
javac -source 8 -target 8 \
  -bootclasspath /opt/jdk8/jre/lib/rt.jar \
  -d out src/com/example/Main.java
```

should be replaced on a modern `javac` supporting the target release:

```bash
javac --release 8 \
  -d out src/com/example/Main.java
```

For target Java 17:

```bash
javac --release 17 \
  -d out src/com/example/Main.java
```

`--release` controls the source level, class file target, and accessible platform APIs for that release. It **does not**:
- Change the JVM executing unit tests.
- Downgrade dependencies already compiled on a newer Java release.
- Bring back `rt.jar` from an older JDK.
- Allow arbitrary releases; the compiler supports a defined release range.

Check `javac --help` and dependency compatibility.

## 21. Maven: removing tools.jar systemPath

If a POM declares:

```xml
<dependency>
    <groupId>jdk.tools</groupId>
    <artifactId>jdk.tools</artifactId>
    <version>1.8</version>
    <scope>system</scope>
    <systemPath>${java.home}/../lib/tools.jar</systemPath>
</dependency>
```

locate the call sites/plugins actually needing it and remove the JDK-layout assumption.

If the goal is compiling source targeting Java 17:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

When a specific compiler JDK different from Maven's JVM is needed, use Maven Toolchains if plugins support it. Never add `jdk.compiler.jmod` to Maven dependencies as a substitute for `tools.jar`.

If an annotation processor/plugin accesses `com.sun.tools.javac.*` directly, upgrade it to a JDK-compatible release. Some tools may temporarily need module export options, yet scope these narrowly with a removal plan.

## 22. Gradle: Java Toolchains replace hardcoded paths

Example `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

The test runtime can be selected independently:

```kotlin
tasks.test {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
```

These settings do not rely on internal JDK JAR filenames. Still, you need a Gradle version supporting the daemon JVM and target toolchain JDK; specifying a `JavaLanguageVersion` does not automatically guarantee the host/runner has that JDK installed.

## 23. Strong encapsulation is not a missing rt.jar error

On modern JDKs, you may encounter:

```text
java.lang.reflect.InaccessibleObjectException:
  module java.base does not "opens java.lang" ...
```

Here, the class **still exists**. The failure occurs because the module does not allow deep reflection. Changes under JEP 396/403 enforce and tighten access to JDK internals.

Distinguish causes:

| Symptom | Likely cause | Resolution |
|---|---|---|
| Cannot find file `rt.jar` | Layout changed starting in JDK 9. | Drop file assumptions, use JRT/APIs. |
| Cannot find `tools.jar` | Tooling moved into modules. | Use `javax.tools`/Toolchains. |
| `InaccessibleObjectException` | JPMS blocks reflection. | Upgrade libraries, use public APIs; narrow workaround if needed. |
| `ClassNotFoundException` | Missing or unresolved dependency/module. | Inspect runtime module graph/classpath. |
| `NoSuchMethodError` | API/binary mismatch. | Check resolved dependency versions. |

`--add-opens` can relax reflection temporarily, yet **never restores `rt.jar`** and does not replace fixing dependencies on internals.

## 24. Tools scanning platform classes must be updated

Before JDK 9, an IDE or bytecode analyzer might do:

```text
Read java.home
   -> find jre/lib/rt.jar
   -> open JarFile
   -> iterate *.class
```

This fails on modular images. Replace it with:
- JRT filesystem to iterate image classes/resources.
- `Class.getModule()` to identify a class's module.
- `ClassLoader.getResourceAsStream` for known resources.
- `jdeps` to analyze dependencies.
- `javac --release`/Javadoc to inspect public APIs.
- Bytecode libraries supporting the target JDK's class file format.

Libraries like ASM, Byte Buddy, Javassist, or older framework scanners may still fail on newer class file major versions even after fixing `rt.jar` paths. Upgrade them against the target JDK's support matrix.
## 25. jlink: building a runtime image instead of copying an old JRE

From JDK 9 onward, `jlink` builds a runtime image tailored to the required Java modules. Example:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging \
  --output runtime-image
```

Then:

```bash
./runtime-image/bin/java --list-modules
```

A runtime image usually includes `bin/java` and `lib/modules` while omitting `javac`, `jmods`, `jlink`, or Javadoc. It is built to **run** software, not necessarily serve as a full development JDK.

The example above **is insufficient for every application**. If a program needs JDBC, XML, crypto providers, extra locales, JMX, native/JNI libraries, or dynamic plugins, adjust the module graph and test accordingly.

### 25.1. Using jdeps to identify static modules

```bash
jdeps --print-module-deps \
  --class-path "libs/*" \
  app.jar
```

Illustrative output:

```text
java.base,java.logging,java.sql
```

From verified modules, build an image:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging,java.sql \
  --output runtime-app
```

`jdeps` primarily inspects **static references**. It is not guaranteed to detect every dependency loaded via reflection, `ServiceLoader`, JDBC drivers, crypto providers, plugins, or external service configs. Add modules required by actual functionality and run integration tests on **the final image**, not solely on the build JDK.

### 25.2. Service providers and runtime data

Depending on the application, you may need:
- `jdk.crypto.ec` for certain cryptographic algorithms/protocols.
- `jdk.localedata` for extended locale data.
- `jdk.charsets` for additional charsets.
- `jdk.unsupported` if some libraries still rely on APIs retained there.

These are examples to **verify**, not a mandatory list for every project. `jlink --bind-services` can pull in extra service providers and enlarge the image. An image missing a provider might boot cleanly yet fail only during a TLS handshake, rare encoding handling, or plugin invocation.

### 25.3. An image is a lifecycle-managed artifact

Custom runtimes must be:
- Built from the exact JDK vendor/version/build.
- Built for the exact OS/CPU architecture.
- Verified with native libraries and system dependencies.
- Recorded with checksums/provenance.
- Rebuilt when JDK security patches arrive.
- Tested alongside new application artifacts.

Shrinking image size does not automatically create a secure system if the image sits unpatched.

## 26. Dockerfile and CI: dropping the jdk/jre assumption

A legacy Dockerfile might contain:

```dockerfile
# Legacy pattern unsuitable for JDK 11+
COPY --from=builder /opt/java/jre /opt/java/jre
ENV JAVA_HOME=/opt/java/jre
ENTRYPOINT ["/opt/java/jre/bin/java", "-jar", "/app/app.jar"]
```

If the builder uses JDK 17/21, `/opt/java/jre` will not necessarily exist.

Two common approaches:

1. Use a vendor-supported runtime base image receiving security updates.
2. Use a full JDK in the build stage, generate a `jlink` runtime, and copy **the entire runtime image** into a runtime stage with compatible OS/native dependencies.

Conceptual flow:

```text
JDK build stage
      |
      +--> compile/package app.jar
      |
      +--> jdeps -> select required modules
      |
      +--> jlink -> /opt/runtime
                         |
                         v
                Runtime container
                /opt/runtime/bin/java
                /app/app.jar
```

Pitfalls to avoid:
- Building a runtime on Windows and copying it to Linux.
- Copying a runtime linked for a different CPU architecture.
- Retaining stale base images after upgrading the JDK/libraries.
- Stripping CA certificates/TLS providers, breaking HTTPS.
- Missing timezone, locale, or native libraries.
- Relying on `javac` at runtime in a `java`-only image.
- Assuming container base images differ only in size without affecting glibc, fonts, or security policies.

If using `jlink` for a non-modularized application, it can still run on the classpath provided the runtime image contains the necessary Java modules. `module-info.java` is not mandatory in every application JAR just to adopt a trimmed runtime.

## 27. Java launcher and java.home: verifying the exact process

A CI agent may have several JDKs installed, so:

```bash
java -version
javac -version
```

may not point to the same installation. In Maven/Gradle, the compiler toolchain and the test-running JVM can also differ.

Print runtime details **directly from the application/test process**:

```java
import java.nio.charset.Charset;

public class RuntimeProbe {
    public static void main(String[] args) {
        System.out.println("Version: "
            + Runtime.version());
        System.out.println("Vendor: "
            + System.getProperty("java.vendor"));
        System.out.println("java.home: "
            + System.getProperty("java.home"));
        System.out.println("JAVA_HOME: "
            + System.getenv("JAVA_HOME"));
        System.out.println("Default charset: "
            + Charset.defaultCharset());
    }
}
```

This sample uses `Runtime.version()`, which requires JDK 9+. On JDK 8, replace it with `System.getProperty("java.version")`.

Never concatenate `java.home` with `../lib/tools.jar`, because `java.home` interpretation changed after JDK 8 and custom images may omit compiler tools.

## 28. Classpath and module path: choosing by objective

Non-modular applications can still run:

```bash
java -cp "app.jar:libs/*" com.example.Main
```

On Windows, use the matching classpath separator:

```powershell
java -cp "app.jar;libs/*" com.example.Main
```

In classpath mode, application classes live in the **unnamed module**; neither `rt.jar` nor `tools.jar` is needed.

Named-module applications:

```bash
java --module-path mods \
  --module com.example.app/com.example.Main
```

Putting a JAR on the module path alters module resolution and package accessibility. Avoid placing JDK JMODs on the runtime classpath/module path as application artifacts. Java platform modules already reside in the runtime image and are resolved by the JVM's module system.

An application using only public Java SE APIs can upgrade the JDK without immediately modularizing its entire codebase. However, if it relies on JDK internals, JPMS encapsulation can still affect classpath code.

## 29. Symptom and remediation table

| Symptom | Likely cause | Approach |
|---|---|---|
| Cannot find `tools.jar` via Maven `systemPath` | Depends on JDK 8 layout. | Drop dummy dependency, upgrade plugin, use Toolchains/`javax.tools`. |
| Script reports `jdk-21/jre/bin/java` missing | Newer JDK has no nested JRE. | Point to `bin/java` of the proper runtime image. |
| `jar tf lib/modules` fails | `lib/modules` is not a JAR. | Use `jimage` or the JRT filesystem. |
| `JarURLConnection` cast error | Platform class resource URL switched from `jar:` to `jrt:`. | Use streams, module APIs, or JRT FS. |
| `URLClassLoader` cast error | System loader implementation changed. | Use public APIs or self-managed custom loaders. |
| `java.ext.dirs` startup error | Extension mechanism removed. | Put JARs onto classpath/module path cleanly. |
| `InaccessibleObjectException` | Module encapsulation blocks reflection. | Upgrade dependency; use public API, narrow workaround if needed. |
| `NoClassDefFoundError` in jlink image | Module/dependency missing or unresolved. | Run `jdeps`, add runtime modules, test dynamic loading. |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime image lacks compiler implementation. | Use a JDK or image containing the compiler module. |
| Annotation processor `com.sun.tools.javac` failure | Depends on compiler internals or old version. | Upgrade plugin/processor, adjust API usage. |
| TLS fails only on custom image | Different crypto providers/truststore/modules or native libs. | Inspect image, add required providers, test handshakes. |

Not every issue surfacing when switching from JDK 8 to 17 relates to `rt.jar`. Other causes can include library binary compatibility, removed JAXB/Java EE modules, Nashorn, GC, reflection, or charset changes.

## 30. Step-by-step migration workflow

### Step 1 — Inventory assumptions about JDK structure

Search Java sources, POMs, Gradle scripts, Dockerfiles, shell/batch scripts, and CI configs for:

```text
rt.jar
tools.jar
dt.jar
jre/bin/java
jre/lib
lib/ext
lib/endorsed
java.ext.dirs
java.endorsed.dirs
sun.boot.class.path
JarURLConnection
URLClassLoader
com.sun.tools.javac
```

Some keywords may appear in tests/documentation without runtime usage; confirm active call sites before changing code.

### Step 2 — Identify target JDK and runtime image

Document version/build/vendor/OS/CPU architecture, and whether full JDK or custom runtime is used. Run:

```bash
java -version
javac -version
java --list-modules
```

On a custom runtime, an absent `javac` is not an error if the image does not need to compile code.

### Step 3 — Classify the needs behind legacy files

| Legacy dependency | Actual need | Modern solution |
|---|---|---|
| `rt.jar` added to classpath | Use Java SE APIs | Remove redundant dependency; runtime supplies modules. |
| `rt.jar` for reading bytecode | Inspect platform classes | JRT filesystem/`jimage`/compatible tooling. |
| `tools.jar` to invoke compiler | Compile Java source | `javax.tools` or `javac` toolchain. |
| `tools.jar` for internal access | Hook into compiler internals | Upgrade/refactor plugin, cut internal coupling. |
| `jdk/jre` for deployment | Provide Java runtime | Use runtime base image or `jlink` image. |
| `lib/ext` | Load extension JARs | Explicit classpath/module path declarations. |

### Step 4 — Upgrade toolchains and class-scanning libraries

Ensure Maven/Gradle, IDEs, bytecode libraries, annotation processors, and build plugins support the new JDK. An old plugin may scan `rt.jar` directly even when app source does not.

### Step 5 — Update compile target

Use `javac --release` or matching Maven/Gradle configuration. Confirm unit/integration tests run on the minimum runtime supported by the product.

### Step 6 — Update packaging/containers

Remove `jre/` copy steps, choose an OS/arch-matching runtime image, and configure `conf/` plus security providers. Pin image versions/checksums to avoid stale artifacts.

### Step 7 — Test the actual runtime

Run the app on **the exact release image** and verify startup, class loading, JDBC, TLS, JSON/XML, service providers, locales, timezones, JNI/native code, and monitoring agents. Never treat `java -version` alone as sufficient proof.

### Step 8 — Deploy with rollback capability

Record JDK builds, module lists, artifact checksums, container tags, and rollback steps. If an issue stems from the runtime image, rollback may require reverting **the entire image**, not just the app JAR.

## 31. Mistakes to avoid

**"No rt.jar means Java SE APIs were removed."** False. Most platform APIs live in modules; check release notes to see whether any specific API still exists or was removed.

**"Swap tools.jar for jdk.compiler.jmod on the classpath."** False. A JMOD is not a runtime replacement JAR.

**"JDK 11 has no JRE, so it cannot run Java."** False. The JDK still ships the Java runtime and supports custom images.

**"Just add lib/modules via java -cp."** False. `lib/modules` is runtime image data, not a classpath JAR.

**"ClassLoader is always URLClassLoader."** False since loader implementations changed in Java 9.

**"Adding --add-opens fixes missing rt.jar."** False. `--add-opens` adjusts reflection access; it does not create internal JARs.

**"A jlink image running Hello World covers every service."** False. Dynamic dependencies and service providers may still be missing.

**"--release 17 proves production Java 17 compatibility."** Insufficient. Dependency versions, runtime modules, class loading, reflection, and integration tests on Java 17 also matter.

## 32. Final checklist

- [ ] No hardcoded `jre/lib/rt.jar`, `lib/tools.jar`, or `dt.jar` references remain.
- [ ] No Maven `scope=system` dependencies point to JDK internals.
- [ ] Equivalent APIs/tools identified for compilation and bytecode inspection.
- [ ] Neither `lib/modules` nor `*.jmod` is added to the classpath as a JAR.
- [ ] Platform class scanners support `jrt:` or the JRT filesystem.
- [ ] No casts of system/platform class loaders to `URLClassLoader`.
- [ ] `lib/ext`, `lib/endorsed`, and legacy properties handled.
- [ ] Updated configuration paths under `conf/` identified where needed.
- [ ] `java.home`/Java version verified inside the actual test/process runtime.
- [ ] `javac --release` or Toolchains aligned with the target baseline.
- [ ] Maven/Gradle/IDEs/annotation processors support the target JDK.
- [ ] If using `jlink`, linked modules and dynamic dependencies verified.
- [ ] TLS, truststores, timezones, locales, charsets, and JNI tested where applicable.
- [ ] Docker/CI scripts no longer copy `jdk/jre` assuming a JDK 8 layout.
- [ ] Runtime image matches target OS/architecture and carries security updates.
- [ ] Evidence exists of integration tests passing on the final runtime image.
- [ ] Provenance and rollback strategy documented for runtime image/JDK versions.

## 33. Practice questions

**Question 1:** Maven fails looking for `jdk.tools:jdk.tools:1.8` on JDK 17. Should `tools.jar` be copied from JDK 8 into the JDK 17 directory?

**Hint:** No. Remove the layout dependency, upgrade the plugin/compiler integration, or use `javax.tools` and toolchains.

**Question 2:** Why does `ClassLoader.getSystemResource("java/lang/Class.class")` return `jrt:/java.base/...` on Java 21 instead of `jar:file:...rt.jar!...`?

**Hint:** Java 9+ stores Java SE classes in modular runtime images; `jrt:` provides the proper resource interface without relying on physical JAR paths.

**Question 3:** A legacy Dockerfile copies `jdk/jre/`, and the builder moves to JDK 21. What should be done?

**Hint:** Choose a supported runtime distribution or build a `jlink` image in the build stage and copy the complete platform-matching image.

**Question 4:** A `jlink` image runs basic application code but fails opening HTTPS connections. Could missing `rt.jar` be the only cause?

**Hint:** No. Inspect TLS providers, truststores, JDK modules, native dependencies, and the image's security configuration.

**Question 5:** If an app already compiles with `javac --release 17`, is testing on Java 17 still necessary?

**Hint:** Yes. Dependency JARs, native libraries, reflection, and runtime behavior are not verified solely by target bytecode compilation.

## 34. References

- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): packaging changes for images starting in JDK 9.
- [JEP 200 — The Modular JDK](https://openjdk.org/jeps/200): modular design of the JDK.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module path, and class loaders.
- [Oracle JDK Migration Guide — JDK 8 to Later](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): layout changes, rt.jar/tools.jar, jrt URLs, ext/endorsed.
- [Oracle JDK 9 Migration Guide](https://docs.oracle.com/javase/9/migrate/): impact of changes introduced in Java 9.
- [JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): JDK path and config changes.
- [JDK 21 jdk.jlink Module](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jlink/module-summary.html): jlink, jmod, and jimage.
- [JDK 21 jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): building runtime images.
- [JDK 21 jimage](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jimage.html): inspecting image contents.
- [JDK 21 jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): analyzing class/module dependencies.
- [JDK 21 javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): using `--release`.
- [Java Compiler API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/package-summary.html): `javax.tools` API.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396) and [JEP 403](https://openjdk.org/jeps/403): access rules for implementation internals.

## Conclusion

From JDK 9 onward, `rt.jar` and `tools.jar` no longer exist in the Java runtime/JDK layout because the platform adopted **modular runtime images**. This does not mean losing Java SE APIs or the compiler: functionality is organized into modules, alongside supported tools/APIs such as `javax.tools`, `jrt:/`, `jdeps`, `jimage`, and `jlink`. For a durable migration, eliminate hardcoded JDK 8 paths, distinguish the Java compiler from the runtime image, update IDEs and build plugins, verify JPMS/class loaders, and package images for the exact target platform. Final testing must execute on the actual deployed runtime, never solely on the build machine's JDK.

