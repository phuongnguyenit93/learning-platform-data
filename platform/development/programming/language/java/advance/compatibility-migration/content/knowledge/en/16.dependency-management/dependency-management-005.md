# Resolving Version Conflicts and Duplicate Classes on the Class Path

During **Java Advance Compatibility Migration**, an application may compile successfully on a new JDK but encounter `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`, or framework startup failures at runtime. A common cause is an **inconsistent dependency graph**: multiple components require different versions of the same library, or multiple JARs package a class with the same fully qualified name (*fully qualified class name*, FQCN).

For example, an application uses the API of `example-util` version 2 at compile time, but the production classpath loads `example-util` version 1. The bytecode has recorded a reference to a new method that does not exist in the version 1 class; the result is a linkage error at runtime. Another situation: two independent libraries both contain `com.example.common.JsonHelper`; when the JVM chooses one copy to load, code from the other side may receive unexpected behavior.

**Version conflicts** and **duplicate classes on the class path** are related but not identical. Just because there are multiple dependency paths to the same library does not mean runtime always has two JAR copies; Maven and Gradle have version selection mechanisms. Conversely, the same class can be packaged in two artifacts with different coordinates, so normal version conflict resolution tools will not detect it.

This lesson explains how conflicts form, how the JVM loads classes, how to inspect Maven/Gradle, dependency exclusion techniques, centralized version management, shading/relocation, and a safe migration process.

## 1. Foundational Concepts

### 1.1. Direct and transitive dependencies

A **direct dependency** is a library that the application declares directly. A **transitive dependency** is a library pulled in by another dependency.

For example:

```text
checkout-app
├── payment-sdk:2.0
│   └── common-utils:2.5
└── report-sdk:1.8
    └── common-utils:1.9
```

Two branches request `common-utils` at two different versions. The build tool needs to decide which version is selected for a configuration or dependency graph.

Differences to remember:

- **Declared version:** the version written in the POM, build script, or metadata.
- **Requested version:** the version/constraint requested by a dependency branch.
- **Resolved version:** the version actually selected after the resolution process.
- **Packaged version:** the version actually placed into the WAR, executable JAR, container, or `lib` directory.
- **Loaded class:** the class that a classloader actually defines or finds when the application runs.

These five values can differ, especially when there is a BOM, dependency management, packaging plugins, or an application server.

### 1.2. What is the classpath?

The classpath is the set of locations containing classes and resources that a classloader can search, typically consisting of class directories and JARs:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

On Windows, the path separator is usually `;`:

```powershell
java -cp "app.jar;lib/*" com.example.Main
```

In environments using a launcher, application server, or framework boot loader, the actual classpath may be generated dynamically; it does not necessarily match a command line built manually by a developer.

### 1.3. Two JARs containing the same class name

Suppose:

```text
lib/legacy-utils.jar
  com/example/common/JsonHelper.class

lib/modern-utils.jar
  com/example/common/JsonHelper.class
```

Both classes have the **same binary name** `com.example.common.JsonHelper`. Within the scope of the same classloader, the classloader will load/define a suitable version according to its search rules; the JVM does not automatically merge methods and fields from both class files.

This is different from having two classes with the same name loaded by **two different classloaders**: at runtime, Java type identity involves both the class name and the defining classloader. Therefore, two classes with the same FQCN but different defining classloaders can be two incompatible types.

### 1.4. Version conflict vs. duplicate class

| Issue | Symptom | Primary Investigation Point |
|---|---|---|
| Version conflict | Multiple branches require different versions of the same module/library | Dependency resolution and selected version |
| Duplicate class | Multiple artifacts actually contain the same FQCN | JAR contents and classloader search path |
| Missing dependency | Class is not present at runtime | Dependency scope, packaging, module/class path |
| Binary incompatibility | Method/field descriptor at runtime differs from compile time | Compile/runtime versions and ABI |
| Classloader conflict | Same class name is defined by different loaders | Loader hierarchy and isolation policy |
| JPMS split package | Overlapping package between named modules | Module graph, package ownership |

A project may encounter multiple issues at the same time. You need to choose fixes based on the real root cause, not only on the first exception that appears.

## 2. Why Does Upgrading the JDK Often Expose Existing Conflicts?

Dependency conflicts sometimes already existed before migration and only cause errors when a condition changes:

1. **Upgrading the framework:** the new framework requires a higher library version, while an old SDK pulls in a lower version.
2. **Changing build tools or plugins:** resolution rules, variant selection, and packaging change.
3. **Changing the JDK:** older libraries use encapsulated internal APIs or incompatible bytecode.
4. **Moving to containers:** the classpath differs from the old application server, losing libraries previously provided by the server.
5. **Changing executable packaging:** shade/repackage plugins copy classes using a different mechanism.
6. **Changing classloaders:** servlet containers, plugin platforms, or module layers have different loading orders.
7. **Upgrading a dependency in one module:** remaining modules are out of sync in APIs and release versions.
8. **Enabling dependency locking/verification:** detecting for the first time artifacts that were previously resolved inconsistently.

For example: an application compiles with JDK 17 and uses a new framework already compiled with `library-x:3`, while the container still has `library-x:1` copied from an old installation bundle. Upgrading the JDK does not directly change method descriptors; it merely exposes inconsistencies in the build/deploy process.

## 3. Runtime Symptoms of Conflicts

### 3.1. `NoSuchMethodError`

Suppose `ApiClient` is compiled against the library:

```java
// common-utils version 2
public class Ids {
    public static String normalize(String id) {
        return id.trim().toLowerCase();
    }
}
```

But runtime loads version 1:

```java
// common-utils version 1
public class Ids {
    public static String trim(String id) {
        return id.trim();
    }
}
```

The consumer compiled the call:

```java
String normalized = Ids.normalize(" A01 ");
```

The class file contains a symbolic reference to method `normalize(Ljava/lang/String;)Ljava/lang/String;`. When runtime uses a version without that method, it may receive:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.common.Ids.normalize(java.lang.String)'
```

Having a method with the same name but a different **parameter or return descriptor** can also cause `NoSuchMethodError`. The JVM does not look up only by method name.

### 3.2. `NoClassDefFoundError`

A library may reference a class from a dependency that is missing at runtime:

```text
java.lang.NoClassDefFoundError:
  com/example/json/JsonMapper
```

Possible causes:

- The dependency was declared with a compile-only scope.
- The WAR/container does not contain the JAR.
- The dependency was excluded too broadly.
- The class moved to a different package between versions.
- The module or classloader does not have visibility to the class.

`NoClassDefFoundError` can also appear after a class initialization failure, not only when a file is missing. You need to inspect `Caused by` and class initialization state.

### 3.3. `IncompatibleClassChangeError`, `NoSuchFieldError`

A method changing from instance to static, a class changing kind, or a field being removed/having its descriptor changed can lead to linkage errors:

```text
java.lang.IncompatibleClassChangeError
java.lang.NoSuchFieldError
```

This is a clear signal of a binary contract mismatch between compiled and loaded artifacts. Do not randomly change JAR order before identifying the actual class.

### 3.4. `ClassCastException` when class names look identical

For example:

```text
java.lang.ClassCastException:
  class com.example.Plugin cannot be cast to class com.example.Plugin
```

The message may display the same FQCN accompanied by two different classloaders. Runtime distinguishes classes by **(binary name, defining classloader)**, not only by the printed name.

The issue can come from plugin isolation, servlet application classloaders, or the same API JAR being embedded separately inside each plugin.

### 3.5. Other errors that only appear on rare execution paths

Some conflicts do not cause errors at startup:

- `ServiceLoader` loads a provider after a feature is triggered.
- A framework uses reflection to call a new method when handling a specific request.
- A serializer encounters an annotation class of a different version.
- A JDBC/HTTP library has an API only invoked in retry or fallback mode.
- A batch job loads classes from a plugin directory after running for many hours.

Therefore, a smoke test that merely opens the homepage is not enough to prove the dependency graph is correct.

## 4. How Does the JVM Decide Which Class Is Loaded?

### 4.1. Classloaders do not "merge" two versions of a class

A JVM may have bootstrap, platform, and application classloaders, along with loaders created by frameworks/containers. Under the common delegation model, a loader asks its parent first and then searches its own classpath region, though some containers/plugins have child-first policies or custom isolation.

Within a single classloader and a single class name, the runtime does not construct a composite class from multiple JARs. It uses the class found/loaded according to the loader's rules.

**There is no universal rule for every Java runtime that "the first JAR in the `lib` listing definitely wins."** The outcome also depends on how the launcher expands wildcards, classpath order, parent delegation, and specialized classloaders.

### 4.2. Wildcard classpaths do not guarantee stable ordering

For example:

```bash
java -cp "lib/*:app.jar" com.example.Main
```

The launcher supports wildcards to include JARs from the `lib` directory, but **wildcard expansion order should not be treated as a stable contract**. Therefore, if two JARs contain the same class, changing the filesystem/build/deployment may yield different results.

The right solution is to exclude or reorganize duplicate classes, rather than trying to rely on an unguaranteed order.

### 4.3. Class identity and loader isolation

Two plugins can each load their own copy of a library:

```text
Application ClassLoader
        |
        +-- PluginLoader A -> common-api.jar
        |
        +-- PluginLoader B -> common-api.jar
```

Even if the class files are identical, if each loader defines `com.example.api.Event` independently, an object from Plugin A cannot simply be cast to Plugin B's `Event` type.

A safer plugin design is usually to place shared API types in a parent/shared loader and let each plugin isolate its implementation dependencies. However, this also depends on the contract of the actual framework/plugin system.

### 4.4. Resources can also collide

Duplication does not happen only with `.class` files. The following resources can be overwritten or have only one copy read:

```text
META-INF/services/com.example.spi.Parser
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
log4j2.xml
application.properties
```

A shading/fat-JAR task that copies two resources with the same name without merging them properly can lose providers or auto-configuration settings. Therefore, resolving duplicate classes must be accompanied by **resource collision** handling and **service descriptor merging**.

## 5. How Maven Resolves Version Conflicts

### 5.1. Dependency mediation: nearest definition

Maven generally uses the **nearest definition** rule when multiple paths request different versions of the same artifact: the dependency at the shorter depth in the graph takes precedence. If two paths are at the same depth, declaration order can affect the outcome.

For example:

```text
app
├── payment-sdk:2.0
│   └── common-utils:2.5
└── report-sdk:1.8
    └── common-utils:1.9
```

Both requests for `common-utils` are at the same depth. The mediation result may depend on the direct declaration order of the SDKs in the POM.

Key point: **Maven does not simply always choose the newest version.** This rule differs from the default behavior commonly seen in Gradle.

A build can run with `common-utils:1.9` even though `payment-sdk:2.0` needs APIs only present in 2.5. Therefore, "Maven build succeeds" does not automatically guarantee binary/runtime compatibility.

### 5.2. Inspecting the dependency tree

In Maven:

```bash
mvn dependency:tree
```

Focus on a specific artifact:

```bash
mvn dependency:tree -Dincludes=com.example:common-utils
```

You can specify the plugin version to produce reproducible output:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree \
  -Dincludes=com.example:common-utils
```

Depending on the plugin version, the output can show dependencies omitted for conflict or duplicate. You need to inspect the **resolved tree**, not just the initially declared POM.

If the project uses profiles or a multi-module reactor, run with the exact Maven profile, module, and scope used by the production pipeline.

### 5.3. Declaring a unified version directly

One solution is to put the shared dependency into the application's POM with the approved version:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>common-utils</artifactId>
        <version>2.5.0</version>
    </dependency>
</dependencies>
```

A direct dependency typically has higher mediation priority than a transitively requested dependency, but **that does not mean the selected version is guaranteed to be compatible with every consumer**. You must verify libraries sharing the API and run tests.

### 5.4. `dependencyManagement` and BOM

For multi-module projects, prefer centralized version management:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>common-utils</artifactId>
            <version>2.5.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`dependencyManagement` sets version management rules; by itself, it **does not automatically add a new dependency** to the classpath if a module does not declare the corresponding dependency.

A BOM can provide a compatible set of versions:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>3.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

When upgrading a framework or platform BOM, review all changed versions rather than only the single library causing an error.

### 5.5. Excluding transitively requested dependencies

If an SDK pulls in an older library that the application wants to replace with a newer version:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-report-sdk</artifactId>
    <version>1.8.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>common-utils</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Then declare the appropriate `common-utils` version in the direct dependencies section or dependency management.

**Do not exclude just to make the dependency tree look "clean".** An SDK may require critical APIs of the excluded artifact; if the replacement version is incompatible, the failure shifts to runtime.

An exclusion in Maven is tied to the declared dependency path. If the same artifact is pulled through another branch, you must inspect the entire graph to see whether it is still resolved.

### 5.6. Maven Enforcer for early detection

Maven Enforcer provides useful rules:

- `dependencyConvergence`: detects transitive paths that do not converge on the same version as required by the rule.
- `requireUpperBoundDeps`: detects some cases where the resolved version is lower than a transitively requested version.
- `bannedDependencies`: forbids artifacts/versions on a disallowed list.

Conceptual configuration example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependencies</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence />
                    <requireUpperBoundDeps />
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

This rule fails the build early when the graph does not satisfy the policy, though it does not yet detect all duplicate `.class` files located in artifacts with different coordinates.

## 6. How Gradle Resolves Version Conflicts

### 6.1. Default behavior differs from Maven

When multiple dependencies request different versions of the same module, Gradle generally applies conflict resolution to **select the highest acceptable version**, influenced by constraints, metadata, capabilities, component selection, and resolution configuration.

For example:

```text
checkout-app
├── payment-sdk -> common-utils:2.5
└── report-sdk  -> common-utils:1.9
```

Gradle may resolve `common-utils:2.5` in `runtimeClasspath` instead of 1.9. That does not prove 2.5 remains compatible with `report-sdk`.

Do not oversimplify this as "Gradle always picks the latest release on the Internet"; it resolves strictly according to the graph, version selectors, and actual rules.

### 6.2. Inspecting the graph per configuration

Gradle has multiple configurations such as `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, or custom variants:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Inspect the reason a version was selected for an artifact:

```bash
./gradlew dependencyInsight \
  --dependency common-utils \
  --configuration runtimeClasspath
```

`dependencyInsight` shows the paths pulling in the dependency and why the version was chosen, such as conflict resolution, constraint, or force.

If an error occurs in integration tests, inspect the configuration containing test runtime; if the error is in production, focus on `runtimeClasspath` and the packaged artifact.

### 6.3. Setting versions with constraints

In Gradle Groovy DSL:

```groovy
dependencies {
    constraints {
        implementation('com.example:common-utils:2.5.0') {
            because 'Platform API version used by payment SDK'
        }
    }
}
```

A constraint influences resolution when that module is present in the graph; it is not a direct dependency adding a new library in every case.

For multi-module systems, you can use the Java Platform plugin or version catalogs to manage the list of versions, while distinguishing:

- Version catalogs help centralize version **declarations**.
- Platform/constraints directly affect the version **resolution process**.
- Dependency locking fixes the **resolution result** for build reproducibility.

### 6.4. Failing fast on version conflicts

Gradle can be configured not to silently pick a version when a conflict exists:

```groovy
configurations.configureEach {
    resolutionStrategy.failOnVersionConflict()
}
```

This rule exposes conflicts instead of just picking a version by default. On large projects, it should be rolled out in a controlled manner because graphs that already contain differing version requirements may begin failing.

The resolution approach is to align dependency constraints/versions and verify compatibility, not to disable the rule as soon as many errors appear.

### 6.5. Exclude and force

Exclude in Gradle:

```groovy
dependencies {
    implementation('com.example:report-sdk:1.8.0') {
        exclude group: 'com.example', module: 'common-utils'
    }
    implementation('com.example:common-utils:2.5.0')
}
```

Some projects use `resolutionStrategy.force` to pin versions. This is a heavy-handed measure and can mask dependency incompatibility, so use it only after confirming the reason, scope, and plan to replace it with constraints/platform or library upgrades.

Force does not automatically fix binary compatibility, does not eliminate duplicate classes across artifacts with different coordinates, and does not fix resource collisions.

### 6.6. Dependency locking and verification

Once a compatible graph is chosen, dependency locking keeps the resolution result stable for supported configurations instead of changing unexpectedly with dynamic versions or metadata.

Dependency verification adds integrity/provenance checks on artifacts according to Gradle's mechanism. The two features serve different goals:

- Locking: which artifact/version is resolved.
- Verification: whether the downloaded artifact has the expected contents/signature verification.

They do not by themselves replace integration tests and binary compatibility checks.

## 7. Why Do Duplicate Classes Still Exist After Version Conflicts Are Resolved?

Build tools primarily resolve dependencies by **component identity** such as group/module/version. Two different artifacts can package the same class.

For example:

```text
lib/json-core-2.0.jar
  com/acme/json/Reader.class

lib/legacy-all-in-one-1.0.jar
  com/acme/json/Reader.class
  com/acme/http/Client.class
```

Version resolution does not treat these two artifacts as two versions of the same `group:artifact` if their coordinates differ. Both JARs may remain on the runtime classpath and create a class collision.

Common sources of duplicate classes:

1. An Uber JAR or SDK fat JAR that embedded dependencies.
2. An older JAR that copied classes verbatim from a third-party library without relocating them.
3. Two internal modules compiling the same package/class.
4. Source-generated code having the same FQCN as another library.
5. A WAR containing classes in `WEB-INF/classes` and another JAR in `WEB-INF/lib`.
6. An application server having shared libraries while the application also bundles the same packages.
7. One artifact copied twice under different filenames.
8. A shading/assembly task merging two dependencies without controlling duplicates.

**Resolving version conflicts does not equal resolving duplicate classes**. Both the list of JARs and their contents must be inspected.

## 8. Detecting Duplicate Classes in JARs

### 8.1. Listing the contents of a JAR

The JDK provides `jar`:

```bash
jar tf lib/common-utils-2.5.jar
```

Search for a specific class in the output:

```bash
jar tf lib/common-utils-2.5.jar | grep 'com/example/common/Ids.class'
```

On Windows PowerShell:

```powershell
jar tf lib/common-utils-2.5.jar |
    Select-String 'com/example/common/Ids.class'
```

If duplicate classes are suspected, search for that FQCN across **every JAR on the runtime classpath**, not only direct dependencies.

### 8.2. Scanning multiple JARs with PowerShell

Example inspecting a distribution directory on Windows. The command only reads JARs and prints artifact names containing a class:

```powershell
$relativeClass = 'com/example/common/Ids.class'

Get-ChildItem -LiteralPath 'dist/lib' -Filter '*.jar' -File |
    ForEach-Object {
        $jar = $_.FullName
        $entries = & jar tf $jar
        if ($entries -contains $relativeClass) {
            Write-Output $jar
        }
    }
```

This is a targeted check; for many large JARs or dynamic classloaders, use more efficient scanning tools and collect the exact artifact set matching the real runtime.

### 8.3. Difference from multi-release JARs

A multi-release JAR may contain:

```text
com/example/Codec.class
META-INF/versions/11/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
```

This is **not automatically a duplicate-class bug**. If the manifest has `Multi-Release: true`, the JVM supports selecting implementations per release. Do not delete classes inside `META-INF/versions` merely because a basic scanner sees logical name overlap.

Conversely, two different artifacts containing the same binary name in the same context is the risk that needs investigation.

### 8.4. Inspecting bytecode and descriptors

If the error mentions a method/field:

```bash
javap -classpath lib/common-utils-2.5.jar \
  -s com.example.common.Ids
```

Compare with the older version:

```bash
javap -classpath lib/common-utils-1.9.jar \
  -s com.example.common.Ids
```

`javap -s` lets you inspect method descriptors, while `javap -v` can display detailed class file information. This serves as evidence to distinguish an API change from an error caused by loading the wrong version of a class.

## 9. Identifying Where the JVM Actually Loads a Class From

### 9.1. Printing the source of a class in Java

A simple diagnostic snippet:

```java
import java.net.URL;

public final class ClassOrigin {
    public static void main(String[] args) {
        Class<?> type = com.example.common.Ids.class;

        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());

        URL location = type.getProtectionDomain() == null
                || type.getProtectionDomain().getCodeSource() == null
                ? null
                : type.getProtectionDomain().getCodeSource().getLocation();

        System.out.println("Code source: " + location);
    }
}
```

`CodeSource` is a useful signal, though it may be absent or may not directly reflect a JAR file when the class is created by a custom loader, in-memory instrumentation, or container specifics. Combine it with class loading logs.

### 9.2. Class loading logs from JDK 9 onward

Example on a JVM supporting unified logging:

```bash
java -Xlog:class+load=info -cp "app.jar:lib/*" com.example.Main
```

The output can show loaded classes and their associated sources. On JDK 8, you may see historical diagnostic options such as `-verbose:class`. Options and log format depend on the JDK; always confirm against the target runtime.

If the application uses a Spring Boot launcher, WAR container, or plugin framework, run the **actual launcher** rather than manually constructing an approximate classpath.

### 9.3. Checking multiple classloaders

When class identity is in doubt:

```java
Class<?> a = pluginAClassLoader.loadClass("com.example.api.Event");
Class<?> b = pluginBClassLoader.loadClass("com.example.api.Event");

System.out.println(a == b);
System.out.println(a.getClassLoader());
System.out.println(b.getClassLoader());
```

A result of `false` shows two distinct `Class` objects despite having the same binary name. However, differing loaders are not always wrong: plugin isolation may be intentional. It becomes an error when objects/APIs must be exchanged across a unified type contract while the sides use different defining loaders.

## 10. Fixing by Aligning the Dependency Graph

A controlled handling workflow:

1. Identify the failing method/class and the artifacts containing it.
2. Check the version at compile time and runtime.
3. Inspect the dependency tree or `dependencyInsight`.
4. Choose a version compatible with **all consumers**.
5. Upgrade SDKs/frameworks requesting older versions if possible.
6. Use a BOM/platform/constraint to align versions.
7. Exclude redundant dependencies on the appropriate branches.
8. Produce a clean artifact and verify the JARs actually packaged.
9. Run consumer integration tests on the target runtime.

### 10.1. Why not pick the highest version by default?

Semantic versioning is not a technical guarantee that a library always preserves binary compatibility. A major version may remove methods, change return descriptors, or rename packages.

Conversely, forcing an older version to stay pinned can break a new framework that requires a new API. You must check compatibility matrices, release notes, and tests across the actual components.

### 10.2. BOMs and constraints are not enough if packaging is wrong

Suppose Maven/Gradle correctly resolves `common-utils:2.5`, but the Dockerfile copies a `common-utils-1.9.jar` from an old directory into `/app/lib`.

The build's dependency graph may be perfect, yet the production runtime classpath still fails. Therefore, the **final artifact** and how the launcher loads classes must be verified as a separate step.

## 11. Fixing Duplicate Classes by Exclusion or Changing Packaging

If two JARs contain the same FQCN, determine the purpose of each copy:

- One copy is completely redundant: remove the unneeded one from runtime.
- One artifact embedded the other artifact's dependency: use the "thin" edition if the publisher provides one.
- An SDK requires its own library but the build re-added the same classes: adjust packaging/exclusions.
- Two implementations must coexist: consider shading with package relocation or classloader isolation with clear contracts.
- Internal code copied classes from a third-party library: remove the copy and depend on the official artifact.

Do not delete a JAR solely because it contains a duplicate class; it may also hold many other classes or resources needed by the application.

### 11.1. Shading and relocation

A library can package a dependency under its own namespace to avoid collisions:

```text
Before:
com.vendor.json.Parser

After relocation:
com.example.repackaged.vendor.json.Parser
```

Example Maven Shade Plugin configuration fragment:

```xml
<relocations>
    <relocation>
        <pattern>com.vendor.json</pattern>
        <shadedPattern>com.example.internal.shaded.json</shadedPattern>
    </relocation>
</relocations>
```

This is a fragment inside `maven-shade-plugin`, not a complete POM. Relocation must be applied deliberately, because reflection by class name, serialization, resource lookups, annotation metadata, and service provider files may still reference the old package.

**Merely merging two JARs into a fat JAR without relocation does not resolve collisions**; merging may simply hide one copy of a class behind the other.

### 11.2. Resource transformers and service files

If a shaded artifact contains multiple providers:

```text
META-INF/services/com.example.spi.Parser
```

service descriptors must be merged properly. Maven Shade provides resource transformers for this kind of resource; Gradle Shadow also has corresponding mechanisms depending on the plugin/version.

Without proper merging, `ServiceLoader` may find only one provider even though all implementation classes remain in the JAR.

### 11.3. Risks of relocating public APIs

Do not arbitrarily relocate types appearing in a library's **public API**, for example a method returning `com.vendor.json.Node`. If type names change without consumers being adjusted, source/binary compatibility can break.

Relocation is better suited for dependencies that are an **implementation detail**, not exposed through a public contract or serialization format.

## 12. JPMS Is Not Like the Traditional Classpath

When moving from classpath to module path:

- Each named module has a name and a module descriptor/metadata.
- Overlapping packages across named modules can violate module resolution/readability rules.
- `requires`, `exports`, `opens`, and service declarations affect accessibility.
- A JAR lacking `module-info.class` may be recognized as an automatic module on the module path.

### 12.1. Split packages

For example, two modules both contain a package:

```text
module com.example.api
  com.example.shared.Customer

module com.example.impl
  com.example.shared.CustomerMapper
```

JPMS can reject configurations where two modules provide the same package within the module graph, even when FQCNs do not overlap. This is the **split-package problem**, distinct from duplicate classes on the classpath.

Adding `Automatic-Module-Name` or changing JAR order does not solve split packages. You need to reorganize package/module boundaries or change how packaging is done.

### 12.2. Duplicate module names

Two automatic modules can derive the same name from filenames, or declare the same `Automatic-Module-Name`. When placed on the module path, the JVM/build tool may report duplicate module names, even when classes do not overlap.

This is another form of conflict: **module identity**, not just dependency versions or FQCNs.

### 12.3. Do not confuse `--add-opens` with fixing dependencies

`--add-opens` only opens packages for deep reflection in JPMS; it does not make missing classes/methods appear and does not select the right library version.

If the error is `NoSuchMethodError`, adding `--add-opens` generally does not address the cause. Distinguish encapsulation from binary linkage.

## 13. Classpaths of Application Servers and Framework Launchers

### 13.1. WAR and servlet containers

A WAR application typically has:

```text
WEB-INF/classes/
WEB-INF/lib/*.jar
```

Meanwhile, the servlet container may provide shared libraries in a separate location. If both the WAR and the container contain the same API/implementation, the container's classloader policy determines the behavior.

A dependency with `provided` scope in Maven may not be included in the WAR. This scope is only valid if the container actually supplies a compatible dependency.

When upgrading an application server, verify the library versions provided by the server instead of inspecting only `WEB-INF/lib`.

### 13.2. Spring Boot executable JAR

A Spring Boot-style executable JAR typically has its own structure and launcher; nested dependency JARs do not behave identically to a flat classpath listing JARs with wildcards.

Do not assume `java -cp "lib/*"` reproduces the exact behavior of `java -jar app.jar`. Inspect the packaged Boot artifact, the `BOOT-INF/lib` listing, actual versions, and the launcher being used.

### 13.3. OSGi or plugin frameworks

Some platforms isolate dependencies per bundle/plugin. Errors may come from classloader visibility rather than a single JVM-wide version conflict.

In these environments, forcing a version in the root dependency graph may not reach a plugin's isolated classpath. Identify the bundle/plugin classloader and type-exchange contracts before fixing.

## 14. Compile, Test, and Production Scopes Can Differ

| Scope | What to Check |
|---|---|
| Compile classpath | Which version's API does the compiler see? |
| Test runtime classpath | Do test frameworks or mock dependencies pull in a different copy? |
| Application runtime classpath | Which artifacts are actually loaded in the production process? |
| Build plugin classpath | Do Gradle/Maven plugins have their own internal dependencies? |
| Application server shared classpath | Which dependencies/versions does the server provide? |
| Plugin classloader | Does each plugin have its own library copy or share a common API? |
| JPMS module path | Are module names, readability, and split packages consistent? |

For example, tests may pass when run with Gradle's `testRuntimeClasspath`, yet the production artifact built by a custom packaging task includes an old JAR. Therefore, run at least one test against the **actual released artifact**.

## 15. Dependency Alignment Across Multiple Internal Modules

Suppose the system has:

```text
platform-api:3.0
platform-domain:3.0
platform-service:3.0
```

If `platform-service:3.0` uses a new method in `platform-domain:3.0` while the application carries only `platform-domain:2.4`, runtime may throw `NoSuchMethodError`.

For library groups commonly released together, you can apply:

- A BOM (Maven) or platform constraints (Gradle).
- Release train / compatibility matrix rules.
- Dependency locking to reproduce the graph.
- Testing consumers against supported version sets.
- A policy disallowing mixed versions outside the validated matrix.

However, **aligning version numbers does not automatically align binary contracts**. If a group releases the same version number while changing an API incompatibly, tests or API comparison tools are still required.

## 16. Tools for Rapid Analysis

### 16.1. `jdeps`

`jdeps` analyzes static dependencies in bytecode:

```bash
jdeps --recursive \
  --class-path "lib/*" \
  app.jar
```

It helps uncover which classes/modules reference which libraries and missing dependencies in the analysis. However, `jdeps` does not always detect reflection, service loading, or dynamically generated classes, and it does not replace classpath inspection.

### 16.2. `javap`

To compare method descriptors:

```bash
javap -classpath old-library.jar -s com.example.common.Ids
javap -classpath new-library.jar -s com.example.common.Ids
```

This provides evidence showing that a method signature/descriptor changed. When diagnosing linkage errors, also compare where the class is loaded from.

### 16.3. Maven Dependency Plugin / Gradle dependencyInsight

Maven:

```bash
mvn dependency:tree -Dincludes=com.example:common-utils
```

Gradle:

```bash
./gradlew dependencyInsight \
  --dependency common-utils \
  --configuration runtimeClasspath
```

These tools answer **why a version was selected**; they do not by themselves prove that the class at production is loaded from that exact artifact.

### 16.4. API and duplicate class analysis tools

You can use japicmp or Revapi to check breaking changes between two library versions. Certain Maven/Gradle plugins or custom verification tasks can scan for duplicate `.class` entries across the runtime artifact set.

When choosing a tool, check whether it distinguishes multi-release JARs, resource duplicates, relocated classes, and classloader scopes.

## 17. Step-by-Step Troubleshooting Workflow

### Step 1 — Record the full error

Save the exact exception, nested cause, stack trace, and environment. Identify the **failing class/method/field**, not just the first line of the exception.

### Step 2 — Identify the runtime versions

Record the JDK vendor/update, launcher, process arguments, container image, and JAR/WAR/deployment artifact. If there are multiple classloaders, record the loading context.

### Step 3 — Find artifacts containing the class

Inspect every JAR on the runtime classpath, not only dependencies declared via the build tool. If the same FQCN appears in multiple JARs, note each artifact and its origin.

### Step 4 — Inspect the dependency graph

Use Maven dependency tree or Gradle `dependencyInsight` on the right configuration and module. Identify the requested versions, selected version, and dependency paths leading to that choice.

### Step 5 — Inspect the bytecode

Use `javap -s` to compare method/field descriptors between the compile-time and runtime versions. If it is a class identity issue, inspect the defining classloaders.

### Step 6 — Choose the appropriate change

- Version conflict: upgrade SDKs and manage versions centrally.
- Duplicate classes: remove redundant JARs, pick thin artifacts, or apply controlled shading/relocation.
- Missing dependency: fix scope/packaging.
- Container shared library: align classloader policies or adjust container-provided libraries.
- Plugin isolation: align the shared API loader or maintain clear classloader boundaries.
- JPMS split package: reorganize package/module boundaries.

### Step 7 — Rebuild a clean artifact

Clean build, resolve dependencies, and repackage. Avoid relying on caches or leftover `lib` directories from previous versions.

### Step 8 — Test with the final artifact

Run the application in a production-like environment, verify the class loading source, and exercise the actual business paths that previously failed.

### Step 9 — Pin and monitor

Store the resolved dependency graph, lockfiles/BOM, artifact hashes, and duplicate class detection rules. Add regression tests so the error does not return on the next upgrade.

## 18. Comprehensive Example: Maven Selects the Lower Library Version by Mistake

Suppose:

```text
checkout-app
├── reporting-sdk:1.0 -> common-utils:1.5
└── payment-sdk:3.0   -> common-utils:2.2
```

In a specific Maven configuration, version 1.5 is selected due to mediation. However, `payment-sdk:3.0` was compiled against a method only available in 2.2. Result:

```text
java.lang.NoSuchMethodError:
 com.example.common.Ids.normalize(...)
```

Investigation:

1. `mvn dependency:tree` to see why 1.5 was selected.
2. `javap -classpath ... -s` to confirm 1.5 is missing the method.
3. Verify whether `reporting-sdk:1.0` is compatible with 2.2.
4. If yes, manage version 2.2 via a BOM or direct dependency.
5. If no, upgrade `reporting-sdk` to a compatible version or split the application along clear boundaries.
6. Clean package, verify version 1.5 is no longer present in the WAR/JAR/container.
7. Re-test on the real runtime.

If runtime still loads 1.5 even after the dependency graph selected 2.2, investigate the packaging/classloader mechanism instead of continuing to edit the POM blindly.

## 19. Comprehensive Example: Fat JAR Carrying Duplicate Classes

Suppose:

```text
checkout-app.jar
  BOOT-INF/lib/json-core-2.0.jar
  BOOT-INF/lib/legacy-client-1.0.jar
```

`legacy-client-1.0.jar` embedded an old, unrelocated copy of `com.vendor.json.Reader`, while `json-core-2.0.jar` has a class with the same name. At this point:

- Maven/Gradle may not report a version conflict because the two artifacts have different coordinates.
- Depending on the loader and packaging, one copy of the class may be loaded first.
- `legacy-client` may require the old implementation, whereas new code needs the 2.0 API.

Preferred handling approach:

1. Find a newer version of `legacy-client` that does not embed the dependency or has moved to a compatible version.
2. If a thin edition exists, use it and manage `json-core` at the application level.
3. If keeping both implementations is unavoidable, consider relocation **inside the SDK** for the internal dependency.
4. Check resources/service descriptors, reflection, and serialization after relocation.
5. Run tests on the final Boot artifact itself.

Do not merely reorder JAR filenames or rename file extensions to hide the error.

## 20. Checklist Before Finishing Migration

- [ ] Distinguished version conflict, duplicate FQCN, missing class, classloader issue, and JPMS split package.
- [ ] Recorded the exact JDK, application launcher, and runtime artifact.
- [ ] Inspected the Maven/Gradle resolved dependency graph on the right configuration.
- [ ] Identified the direct and transitive paths causing the conflict.
- [ ] Checked whether compile-time and runtime versions differ.
- [ ] Scanned for duplicate classes across the JARs actually deployed.
- [ ] Verified the class source and defining classloader at runtime.
- [ ] Compared method/field descriptors when linkage errors appeared.
- [ ] Inspected the classpath of WARs, executable JARs, containers, and server shared libraries.
- [ ] Evaluated resource/service descriptor collisions.
- [ ] Chose aligned versions via BOM, dependency management, or Gradle constraints.
- [ ] Avoided using exclusions/force to mask compatibility errors.
- [ ] If using shading, handled relocation and related resources/reflection.
- [ ] If using JPMS, resolved split packages and duplicate module names.
- [ ] Tested consumers with the final artifact and critical execution paths.
- [ ] Saved dependency locks/graphs, artifact checksums, and regression checks.

## 21. Conclusion

Version conflicts and duplicate classes on the classpath are two distinct groups of risks in Java Compatibility Migration. Maven/Gradle select versions according to their own resolution mechanisms, whereas the JVM loads classes according to actual classloaders and runtime artifacts. A correct dependency tree does not guarantee the right JARs are deployed; a class file with the same name does not guarantee the same binary contract or the same defining classloader.

The sustainable approach is to **trace from the exception to the class actually loaded, inspect the dependency graph, align versions using centralized management policies, eliminate unnecessary duplicate classes, and test on the final artifact**. Do not rely on accidental JAR order or force an unverified version. When dependencies, packaging, and classloading are all under control, JDK and library upgrades will produce far fewer hard-to-reproduce linkage errors.
