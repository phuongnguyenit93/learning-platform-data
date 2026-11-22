# Why Bytecode Targeting an Old JDK Can Still Call New APIs by Mistake

A Java application can be compiled with a new JDK yet produce class files bearing the bytecode version of an older JDK. That often leads teams to assume the artifact will definitely run on the older runtime. This conclusion lacks sufficient basis: **the bytecode version and the API version referenced by a class file are two different issues**.

For example, the JDK 21 compiler can emit class files with major version 61 (Java 17's bytecode format) if the build sets `-source 17 -target 17`. However, the compiler still sees the classes and methods of JDK 21. Source code can call `Thread.ofVirtual()`, an API introduced only in Java 21, and get compiled into a major 61 class file. A Java 17 JVM can read that class-file format, yet when execution reaches the call to a method absent from Java 17's `java.lang.Thread`, the application may fail with `NoSuchMethodError`.

This issue is commonly referred to as accidentally calling new APIs while targeting an older runtime. The compiler-level solution is using `--release` for the target version—such as `--release 17`—instead of setting source level and bytecode target separately. However, `--release` also has a bounded scope: it controls which Java platform APIs the sources in that compilation may reference, yet does not automatically prove every third-party library, plugin, generated binary, or production runtime is compatible with JDK 17.

## 1. Three Concepts to Separate

### 1.1. Source Language Level

The source level specifies which syntax and language features the compiler accepts. For example, `-source 17` tells `javac` to parse source code under Java 17 language rules. It governs syntactic features such as records, sealed classes, and pattern matching at the level supported for that release.

The source level does not automatically restrict which classes and methods the compiler sees in the running JDK's standard library. If the compiler runs on JDK 21, its default system classpath contains JDK 21 APIs. Consequently, a call to a new method can still be accepted even though source syntax is constrained to Java 17.

### 1.2. Class-File Target

The target level specifies the class-file format version emitted by the compiler. For example, `-target 17` produces class files with major version 61. A Java 17 JVM understands this format.

The target level does not convert a Java 21 API call into a Java 17 API call. The compiler merely records symbolic references to classes, methods, and fields into bytecode. It does not automatically replace a new method with an equivalent older implementation, nor does it fully verify that every reference will be provided by the target runtime.

### 1.3. Platform API Level

The platform API level is the set of Java platform APIs the program is permitted to reference. When the target is running on Java 17, sources must be compiled against the Java 17 API set, even when the compiler runs on JDK 21.

This is the part `--release 17` solves. The `--release` option combines the language level, class-file version, and platform API set corresponding to the chosen release. It prevents sources from inadvertently referencing APIs available only in the JDK executing the compiler.

| Concept | Question answered | Example |
|---|---|---|
| Source level | Which Java syntax is source code allowed to use? | `-source 17` |
| Target bytecode | Which format are class files emitted in? | `-target 17`, major version 61 |
| Platform API level | Which release's Java platform APIs may source code call? | `--release 17` |
| Actual runtime | Which JVM will load and execute the artifact? | Java 17 or Java 21 |

A sound build configuration must align all four concepts with the product's goals. You cannot infer the platform API level solely from the class-file major version.

## 2. Failure Mechanism: Old Class File Referencing a New Method

Suppose the build machine uses JDK 21, while the product must continue running on JDK 17. The following snippet uses the virtual threads API:

```java
public class ApiLevelExample {
    public static void main(String[] args) {
        Thread thread = Thread.ofVirtual().start(() ->
            System.out.println("Hello from a virtual thread")
        );
    }
}
```

`Thread.ofVirtual()` was officially added in Java 21. If compiled with JDK 21 using a configuration that constrains only source and target:

```bash
javac -source 17 -target 17 ApiLevelExample.java
```

the compiler can accept the call because it reads JDK 21's `java.lang.Thread` API. The emitted class file has major version 61, matching Java 17. Inspect with:

```bash
javap -verbose ApiLevelExample
```

The header displays `major version: 61`. This indicates only that the class file uses Java 17's format. It does not prove `Thread.ofVirtual()` exists in Java 17.

When run on JDK 21, the method exists, so the call can work. When running the exact same class file on JDK 17, the JVM can load the class because the major version is valid. At linkage time for the call to the method absent from the runtime, the JVM raises a linkage error, typically:

```text
java.lang.NoSuchMethodError:
  'java.lang.Thread$Builder java.lang.Thread.ofVirtual()'
```

The exact message can vary depending on bytecode, compilation options, and when the JVM resolves the reference. The core point is that the runtime cannot find the method requested by the bytecode.

This is not `UnsupportedClassVersionError`. The two errors represent two different problems:

| Error | Cause | Example |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime is too old to read the class-file format | Major 65 class loaded on Java 17 supporting only up to major 61 |
| `NoSuchMethodError` | Class file is readable, yet referenced method is absent at runtime | Major 61 bytecode calling `Thread.ofVirtual()` on Java 17 |
| `NoClassDefFoundError` / `ClassNotFoundException` | Referenced class is absent at runtime or not found via class loader | Code using `java.util.SequencedCollection` on Java 17 |
| `NoSuchFieldError` | Referenced field does not exist in the actual runtime class | Dependency compiled against a library version different from runtime |
| `IllegalAccessError` | Reference exists yet cannot be accessed per access/module rules | Library accessing an encapsulated or unexported member |

The JVM can resolve certain symbolic references lazily as code paths execute. Consequently, an application can start up normally and fail only when a user invokes the specific endpoint or feature containing the new API. A smoke test checking only startup will miss such cases.

## 3. Why Are `-source` and `-target` Not Enough?

When using:

```bash
javac -source 17 -target 17 App.java
```

the compiler receives two instructions:

- Parse source code according to Java 17 language syntax.
- Emit class files in Java 17 format.

Neither instruction tells the compiler to restrict visible platform APIs to Java 17. Because the compiler runs on JDK 21, it can see classes and methods newly introduced in JDK 21.

This also explains why source code using no new Java syntax can still fail to run on an older runtime. Source syntax and runtime APIs are two independent axes.

For example, Java 17 source can use completely familiar syntax while referencing a Java 21 API:

```java
import java.util.List;

public class CollectionExample {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình");
        System.out.println(names.getFirst());
    }
}
```

`List.getFirst()` belongs to Sequenced Collections added in Java 21. The source code uses no new Java 21 syntax, yet still requires the Java 21 API. If targeting bytecode 17 with `-source` and `-target`, the class file can still reference the new method.

Setting lower source/target values addresses only syntax parsing and class-file format. It is not an API compatibility check.

## 4. How Does `--release` Prevent Calling New APIs by Mistake?

JEP 247 added `--release` to `javac` starting in JDK 9. This option tells the compiler the target platform release. When compiling with JDK 21 while needing Java 17 compatibility:

```bash
javac --release 17 -d out src/main/java/example/App.java
```

The compiler uses Java 17's API signatures instead of all of JDK 21's APIs, while also emitting release 17 bytecode and applying corresponding language rules. Calls to `Thread.ofVirtual()` or `List.getFirst()` will not be found in platform API 17, so compilation fails right at the source rather than surfacing in production.

An example compilation error looks like:

```text
error: cannot find symbol
    Thread.ofVirtual();
          ^
  symbol:   method ofVirtual()
  location: class Thread
```

Historical API signatures are stored in platform data used by the compiler, typically supplied in the JDK via `ct.sym`. Users do not need to manually construct a boot classpath for each version when using `--release`.

Compare the three commands:

```bash
# Restricts only syntax and bytecode; APIs can still come from JDK 21.
javac -source 17 -target 17 App.java

# Consistently restricts language, bytecode, and Java SE APIs at release 17.
javac --release 17 App.java

# Allows using Java 21 language, bytecode, and APIs.
javac --release 21 App.java
```

In modern JDKs, `--release` should not be combined with `-source` or `-target` in the same compilation invocation. `--release` already encompasses those constraints.

### 4.1. Scope of Protection of `--release`

`--release 17` controls direct references in compiled source code to release 17 Java SE platform APIs. It is especially useful when:

- The JDK installed on developer machines or CI is newer than the product's minimum runtime.
- Multiple modules build together on JDK 21, yet some artifacts must continue supporting Java 17.
- A library wants to publish an artifact usable across multiple Java runtimes.
- Sources are generated by annotation processors or generators and must conform to the target API.

When generated sources are fed into the same compilation task, the compiler applies `--release` to them and can reject new APIs. However, if a generator emits class files directly, bundles prebuilt binaries, or runs a separate compilation task without `--release`, references to new APIs can still slip through. Every bytecode-producing task must be checked, not just the familiar `compileJava` task.

### 4.2. What `--release` Does Not Guarantee

`--release 17` does not automatically:

- Inspect bytecode and APIs referenced by third-party dependencies.
- Guarantee runtime dependencies can execute on Java 17.
- Verify Gradle/Maven plugins or annotation processors run on the build JDK.
- Constrain sources compiled by Kotlin, Scala, Groovy, or separate compilers unless those tasks have equivalent configuration.
- Control class files loaded dynamically, emitted directly by bytecode libraries, or fetched from external services.
- Ensure string-based reflection does not reference classes/methods available only on newer JDKs.
- Guarantee production actually runs Java 17.

Therefore, `--release` is an important compiler gate, yet must be paired with dependency analysis, testing on the target runtime, and artifact inspection.

## 5. Reproducing and Confirming the Error by Example

Create `ApiLevelExample.java`:

```java
public class ApiLevelExample {
    public static void main(String[] args) {
        System.out.println(Thread.ofVirtual().name("worker").factory());
    }
}
```

On a machine with JDK 21 installed, confirm the active compiler:

```bash
javac -version
java -version
```

Compile with source/target 17:

```bash
javac -source 17 -target 17 ApiLevelExample.java
javap -verbose ApiLevelExample
```

If the compiler accepts the code, inspect `major version` in the output. The expected value is 61. Then run the class using JDK 21 to confirm the API exists in runtime 21.

Next, use an actual JDK 17 installation to run the generated class file:

```bash
<JDK17_HOME>/bin/java ApiLevelExample
```

The path above is a placeholder and must be replaced with the JDK 17 path on the test machine. When the new method is executed, runtime 17 cannot resolve the method and may throw `NoSuchMethodError`.

Delete the output and recompile using `--release 17`:

```bash
rm -f ApiLevelExample.class
javac --release 17 ApiLevelExample.java
```

This time the compiler must reject `Thread.ofVirtual()` because the method does not exist in the Java 17 API. This is the desired outcome: catching the violation immediately at build time.

To test another new API, replace the call with `List.of("A").getFirst()`. The same rule applies: if the API is absent in Java 17, `--release 17` must reject the source.

Note: this example merely illustrates compiler/runtime mechanics. Do not use this small test file as sole proof of compatibility for a real application.

## 6. Proper Gradle Configuration When Building with JDK 21 Targeting Java 17

Gradle can use one JDK toolchain to run the compiler and a release level to constrain APIs/bytecode. Example with Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

In this configuration:

- The compiler is selected from the JDK 21 toolchain.
- `options.release = 17` passes `javac --release 17`.
- Sources are compiled against Java 17 language/APIs and emit Java 17-compatible class files.

If the true goal is moving the product to Java 21, change release to 21:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

### 6.1. Do Not Configure Only the `compileJava` Task

In multi-module projects or projects with multiple source sets, inspect every `JavaCompile` task, such as:

- `compileJava` for the main source set.
- `compileTestJava` for the test source set.
- Compile tasks for integration tests, functional tests, or custom source sets.
- Tasks created by plugins to compile generated sources.
- Compile tasks of included builds or convention plugins.

Configuring at the root may not affect standalone included builds or modules using separate build logic. Verify each task actually receives `--release` via compiler logs or task inspection rather than merely reading a build script snippet.

### 6.2. Distinguishing Toolchain from Target Release

`java.toolchain.languageVersion = 21` selects the JDK 21 compiler. It does not automatically mean the output must be Java 21. `options.release = 17` is what constrains the platform API and bytecode to 17.

Conversely, setting only `sourceCompatibility = 17` and `targetCompatibility = 17` does not provide the same API protection as `options.release = 17`. When Java 17 compatibility is required, use `options.release` when supported by the compiler.

### 6.3. Kotlin, Groovy, and Other Languages

`options.release` applies only to `JavaCompile` tasks. If a module contains Kotlin, Groovy, Scala, or custom source generators, configure their corresponding compilers and verify each tool's ability to constrain JDK APIs. For example, Kotlin has JVM target options and JDK release options in supporting compiler versions; setting only `jvmTarget` should not be treated as proof that Java 17 APIs were constrained.

Mixed-language modules must be checked across the task graph. A Java class compiled with `--release 17` can still depend on a Kotlin/Groovy class or binary library compiled against a newer JDK.

## 7. Configuring Maven Compiler Plugin

With Maven, use the `maven.compiler.release` property or configure `<release>` in the Maven Compiler Plugin. Example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Or explicitly declare and configure the plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>${maven-compiler-plugin.version}</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

The plugin version property in the example is a placeholder; use an explicit version tested with your Maven and build JDK. Maven Compiler Plugin supports `release` configuration starting in versions supporting JDK 9+; consult the documentation of the exact plugin in use rather than relying on the implicit Maven super POM version.

If running Maven on JDK 21 while compiler release is 17, the compiler constrains source/API/bytecode to Java 17. However, Surefire/Failsafe, annotation processors, and other plugins still execute in their own environments. Confirm the JDK for every forked process and plugin execution.

## 8. Why Can Third-Party Dependencies Still Break the Java 17 Commitment?

This is the most critical limitation to understand once `--release` is configured properly. The compiler checks only sources compiled in that compilation and the Java platform APIs they are allowed to reference. It does not recompile or analyze all binary dependencies to ensure they do not call newer APIs.

### 8.1. Dependencies with Newer Bytecode

If a library was compiled for Java 21, its class files typically have major version 65. The application may compile on JDK 21 because the compiler can read those classes, yet when run on Java 17, the JVM cannot load them and throws `UnsupportedClassVersionError`.

This case is easy to identify via class-file version. It differs from old bytecode referencing new APIs.

### 8.2. Dependencies with Old Bytecode Referencing New APIs

A library might be compiled with JDK 21 using source/target 17 without `--release 17`. The result is major version 61 class files whose constant pool holds symbolic references to APIs present only in Java 21.

Your application can compile completely cleanly with `--release 17`, because the compiler does not inspect internal dependency implementations the way it checks your own project sources. When runtime 17 executes that code path inside the library, a linkage error can occur.

For example, the library `legacy-compatible-client.jar` has major version 61 classes, yet an internal method calls `Thread.ofVirtual()`. Your application does not call the Java 21 API directly; it only calls `client.execute()`. When `execute()` enters the virtual-thread-creation branch on Java 17, the JVM may throw `NoSuchMethodError`.

Hence, checking a dependency's major version alone is insufficient. Check the vendor's published runtime support, release notes, and run integration tests on Java 17 if that is the minimum runtime.

### 8.3. Dependencies Using Reflection or String Class Names

Compilers struggle to catch dynamically constructed references such as:

```java
Class<?> type = Class.forName("java.util.SequencedCollection");
```

The class name is merely a string in source code. `--release 17` cannot deduce that the program will try to load a Java 21 class at runtime. Similarly, methods looked up via reflection, dynamically loaded service providers, scripting engines, or externally loaded plugins can reference new APIs unseen by the compiler.

Areas to review:

- `Class.forName`, `ClassLoader.loadClass`, and name-based reflection.
- `MethodHandles.Lookup` or dynamic proxies.
- ServiceLoader and `META-INF/services` files.
- Plugins/modules loaded from directories outside the artifact.
- Class names configured in YAML, properties, XML, or databases.
- Scripts, expression engines, and code compiled at runtime.

These cases require runtime testing and configuration audits; you cannot rely solely on a compile gate.

### 8.4. Generated Bytecode and Instrumentation Tools

Byte Buddy, ASM, Javassist, CGLIB, agents, or generators can emit bytecode directly without passing through a `javac` task configured with `--release 17`. A plugin might emit major 61 classes referencing new APIs, or unexpectedly emit major 65 classes.

Inventory all bytecode generation paths:

- Standard `javac`/JavaCompile.
- Annotation processors emitting source code subsequently compiled by the compiler.
- Generators emitting `.class` files directly.
- Runtime instrumentation/agents transforming classes.
- Kotlin/Scala/Groovy compilers and custom compiler tasks.
- Build plugins packaging or downloading pre-generated binaries from elsewhere.

If generated sources are compiled in the same `--release 17` task, the compiler checks direct API references. If a generator produces binaries directly or a separate task omits release 17, inspect the output artifact with appropriate tooling and test on runtime 17.

### 8.5. Multi-Release JARs

A JAR can contain different implementations for various Java versions under `META-INF/versions/`. A manifest containing `Multi-Release: true` enables the JVM to pick the class matching the runtime.

Example:

```text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Feature.class
└── META-INF/versions/
    ├── 17/com/example/Feature.class
    └── 21/com/example/Feature.class
```

Java 17 selects the base entry or the highest matching version not exceeding 17; Java 21 can select the implementation in `versions/21`. Thus, the exact same artifact can execute different code across two runtimes. Inspect the manifest and JAR contents and test on every target runtime. Do not assume inspecting a class at the root represents the implementation selected by Java 21.

## 9. How to Check Whether Dependencies Call New APIs

No single simple command proves every binary is Java 17 compatible. Combining multiple layers of evidence is far more reliable.

### 9.1. Checking Class-File Versions

Run `javap -verbose` on representative classes:

```bash
javap -verbose -classpath path/to/library.jar com.example.LibraryClass
```

Inspect `major version`. A dependency with major version greater than 61 cannot be loaded directly by Java 17. Yet major version 61 or lower proves only class-file format compatibility, not API linkage compatibility.

For large JARs, list all classes and use a script/tool to verify major versions across every class, including entries in `META-INF/versions`. Handle multi-release JARs according to the specific runtime under evaluation.

### 9.2. Checking Referenced APIs

Bytecode and API signature analyzers can detect project classes referencing APIs absent in Java 17. For instance, Animal Sniffer provides per-Java-version signatures and Maven/Gradle plugins to check API usage.

When applying it, verify:

- The signature matches Java 17 and the exact profile to support.
- The plugin version is compatible with the active JDK/build tool.
- The checked class scope covers all necessary source sets.
- Generated sources/classes and submodules are included in checks.
- Reports distinguish Java SE APIs from third-party APIs.

Animal Sniffer or an equivalent tool is an additional verification layer. Do not assume it has analyzed every binary dependency in the runtime graph. Third-party artifact verification must match tool capabilities and project policy.

### 9.3. Using jdeps for Its Intended Purpose

`jdeps` analyzes dependencies between classes, packages, and modules while detecting references to internal JDK APIs. Example:

```bash
jdeps --jdk-internals application.jar
jdeps -summary application.jar
```

`jdeps` is useful for locating internal dependencies and module dependencies. However, do not treat `jdeps --jdk-internals` as a comprehensive check for new APIs relative to Java 17. It focuses on internal APIs, not proving every referenced Java SE method exists in release 17.

`jdeprscan` can help locate deprecated APIs in bytecode:

```bash
jdeprscan --release 17 application.jar
```

This is likewise not a full baseline API linkage check. Combine signature checkers, dependency metadata, and runtime tests.

### 9.4. Running the Artifact on the Minimum Runtime

If the product commits to Java 17, running the final artifact on JDK 17 is the strongest evidence that the real combination executes properly. Run:

- Application startup smoke tests.
- Tests for critical endpoints/business flows.
- Integration tests with databases, brokers, and external services.
- Tests covering rarely invoked dependency branches.
- Tests for serializers, reflection, plugin loaders, and dynamic class loading.
- Tests on the exact container image/runtime slated for release.

Checking startup alone is insufficient because linkage errors can surface only when a method/class is first invoked. Establish coverage over critical paths or directly exercise relevant features.

## 10. Locking Down Build Configuration Against Regression

### 10.1. Gradle

Example building with JDK 21 while targeting Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Key takeaways:

- Toolchain picks the compiler JDK.
- `options.release` constrains source/API/bytecode to Java 17.
- Standalone `sourceCompatibility` and `targetCompatibility` do not fully replace `--release`.
- Configure `compileTestJava`, custom source sets, and plugin-created `JavaCompile` tasks as well.
- Included builds and `buildSrc` may have separate builds and do not automatically inherit root config.
- Kotlin/Groovy/Scala require equivalent configuration for their respective compilers.

Verify compiler arguments via task logs or by running:

```bash
./gradlew compileJava --info
```

Do not infer from reading the build script alone; plugins can override compiler options or register new tasks.

### 10.2. Maven

Maven Compiler Plugin example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Or direct configuration:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>${maven-compiler-plugin.version}</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Verify actual plugin versions, parent POMs, profiles, and executions. Ensure the compiler plugin receives release 17 across all modules and source sets. Test JVMs and forked plugin executions still require separate verification.

### 10.3. Locking and Auditing Dependencies

For reproducible builds, manage dependencies using BOMs/platforms, version catalogs, constraints, or intentional dependency management. If using dependency locking, update lock states alongside approved changes. If using dependency verification, update checksums/signatures after validating artifacts.

Do not use `--release` as a substitute for dependency management. A dependency can change version without any source change; when that happens, its APIs or bytecode can change as well.

## 11. Runtime Matrix and Support Policy

If the product must support both Java 17 and Java 21, build an explicit execution matrix:

| Build JDK | Compiler release | Runtime test | Outcome to prove |
|---|---|---|---|
| 21 | 17 | 17 | Artifact runs on minimum runtime |
| 21 | 17 | 21 | Target-17 artifact still runs on new runtime |
| 21 | 21 | 21 | Java 21-only artifact branch if product has that policy |
| 17 | 17 | 17 | Can be retained as baseline or control during transition |

Not every project needs to run all four combinations. The matrix must reflect product commitments, yet every advertised runtime needs at least one periodic verification pipeline.

For shared libraries, test consumer compilation on Java 17 and runtime integration on Java 17. For applications, test the packaged artifact inside a container with the target JRE/JDK. For plugins, test directly on the build JDK and supported Gradle/Maven versions.

## 12. End-to-End Example: Dependency Targeting 17 Calling a Java 21 API

Suppose `order-service` must support Java 17. A library `order-client` was compiled on JDK 21 using `-source 17 -target 17`. The library calls `List.getFirst()` to retrieve the first element.

Detection and resolution workflow:

1. **Check class files:** `javap -verbose` shows `order-client` classes have major version 61. This rules out a class-file format error, yet does not prove Java 17 API compatibility.
2. **Check dependency metadata:** confirm whether the vendor commits to Java 17 runtime support; read release notes and how the artifact is built.
3. **Check API references:** use an API signature checker or bytecode analysis to discover `List.getFirst()` does not exist in Java 17.
4. **Reproduce:** run a test invoking that exact `order-client` method on JDK 17. The failure can surface as `NoSuchMethodError`.
5. **Fix the source:** if possible, replace the API with a Java 17-compatible alternative such as `list.get(0)` after verifying the list is non-empty; or upgrade to a fixed library version claiming Java 17 support.
6. **Fix the library pipeline:** compile `order-client` sources on JDK 21 with `--release 17`, add API signature checks, and run Java 17 runtime tests.
7. **Verify the consumer:** rebuild `order-service` and run unit/integration tests on Java 17 and Java 21 per the support matrix.
8. **Close the issue:** archive artifacts, checksums, commits, and test results, and update the compatibility matrix.

Key point: your application can configure `--release 17` completely properly and still pull in a broken binary dependency. The application's compiler gate cannot replace each library's own compatibility responsibility.

## 13. Common Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Assuming major version 61 proves Java 17 compatibility | Misses references to new APIs | Check API signatures and runtime behavior |
| Setting only `-source 17 -target 17` | Compiler can still see JDK 21 APIs | Use `--release 17` |
| Thinking `--release` checks every dependency | Binary dependencies may call new APIs | Check vendor support, binaries, and runtime tests |
| Running tests only on JDK 21 | Misses failures on minimum runtime 17 | Run artifact on JDK 17 if supported by product |
| Checking only startup | Linkage errors can appear on late paths | Test business endpoints/flows and rarely used dependencies |
| Ignoring processors/generators | Generated classes may ignore release | Inspect source/binary generation tasks and compiler args |
| Configuring only compileJava | Tests/custom source sets still use new APIs | Configure all relevant compile tasks |
| Configuring only JavaCompile | Kotlin/Groovy/Scala tasks may target differently | Use compiler-specific release/API constraints |
| Using jdeps to claim zero new APIs | jdeps is not a complete baseline API checker | Add signature checkers and runtime tests |
| Not inspecting multi-release JARs | Runtimes 17 and 21 may select different classes | Inspect manifest and versioned entries |

## 14. Verification Records and Closure Criteria

A decision that an "artifact targets Java 17" needs the following evidence:

1. **Build configuration:** build JDK, compiler toolchain, `--release 17`, and configuration across all source sets.
2. **Class-file evidence:** major version checks on project-emitted classes and packaged binaries.
3. **API compatibility evidence:** signature checker or bytecode analysis results against Java 17.
4. **Dependency evidence:** list of runtime dependencies, resolved versions, vendor support, and unresolved items.
5. **Generator evidence:** processor/generator versions, inputs/outputs, and corresponding compile tasks.
6. **Runtime evidence:** artifact tests executed on JDK 17 in a representative environment.
7. **Regression evidence:** tests covering lazy linkage, reflection, plugin loading, serialization, and integration flows.
8. **Release evidence:** commit, artifact checksum, runtime image, and rollback policy.

### Pre-Release Checklist

- [ ] Minimum runtime committed by the product identified.
- [ ] Compiler runs on the new JDK while passing `--release` for the minimum runtime.
- [ ] Every Java compile task across modules receives the right release.
- [ ] Other language compilers have separate compatible configurations.
- [ ] Third-party dependencies have evidence supporting the minimum runtime.
- [ ] Class-file major versions do not exceed the minimum runtime level.
- [ ] New API references checked in project-emitted bytecode.
- [ ] Generated sources/binaries, agents, and instrumentation verified.
- [ ] Multi-release JARs verified on each target runtime.
- [ ] Final artifact runs on the minimum runtime, not merely builds cleanly.
- [ ] Critical business branches executed during tests.
- [ ] Logs, checksums, commits, and reports retained for traceability.

Bytecode targeting an old JDK guarantees only class-file format compatibility with the old JVM. To guarantee API compatibility, the compiler must be constrained to the right platform release via `--release`, while binary dependencies, generators, and actual execution paths must be verified separately. Only by combining compiler controls, API analysis, dependency management, and runtime tests on the minimum version can a team make a compatibility commitment backed by evidence.
