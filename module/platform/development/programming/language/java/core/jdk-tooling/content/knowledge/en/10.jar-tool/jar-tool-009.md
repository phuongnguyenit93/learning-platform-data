# Multi-release JAR in Java

Multi-release JAR (MR-JAR) is a JAR format that allows a library or application to package multiple versions of the same class or resource so that the JVM selects the appropriate content for the running Java version. As a result, a single artifact can maintain a base implementation compatible with older Java versions while providing implementations that leverage newer APIs on Java 9, 11, 17, or newer releases.

This mechanism was introduced in Java 9 alongside the Java Platform Module System. An MR-JAR is still a standard JAR file, but it includes versioned directories under `META-INF/versions` and a required manifest attribute:

~~~text
Multi-Release: true
~~~

For example, a JAR might contain:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/RuntimeInfo.class
│       └── 17/
│           └── com/example/RuntimeInfo.class
└── com/
    └── example/
        └── RuntimeInfo.class
~~~

A Java 8 JVM uses the class in the root directory. A Java 11 JVM selects the version in `META-INF/versions/9`. Java 17 or newer selects the version in `META-INF/versions/17` if present; otherwise, it uses the highest version that does not exceed the current runtime. The essential requirement is that the manifest must declare `Multi-Release: true`.

## 1. Structure and Version Selection Rules

An MR-JAR has two types of content:

- **Base entries:** classes and resources located at the JAR root like a traditional JAR. This is the baseline content for older runtimes and serves as a fallback when no matching versioned entry exists.
- **Versioned entries:** content located under `META-INF/versions/N/`, where `N` is a Java release number of 9 or higher.

For example, a class with the fully qualified name `com.example.RuntimeInfo` has the base path:

~~~text
com/example/RuntimeInfo.class
~~~

The version for Java 9 is located at:

~~~text
META-INF/versions/9/com/example/RuntimeInfo.class
~~~

The version for Java 17 is located at:

~~~text
META-INF/versions/17/com/example/RuntimeInfo.class
~~~

When the class loader looks up a class in an MR-JAR, the runtime performs selection based on the feature version of the running Java:

1. Determine the current Java version.
2. Find the versioned entry with the highest version number that does not exceed the runtime version.
3. If found, use that entry.
4. If no matching versioned entry exists, use the entry at the JAR root.

For example:

| Runtime | Selected Entry |
|---|---|
| Java 8 | Base entry at the JAR root |
| Java 9 | META-INF/versions/9 |
| Java 11 | META-INF/versions/9 if no version 11 entry exists |
| Java 17 | META-INF/versions/17 if present; otherwise, version 9 |
| Java 21 | Version 21 if present; otherwise, the highest version not exceeding 21 |

Version directories are not an independent classpath mechanism. The JVM recognizes them as part of the same JAR when the manifest enables multi-release. If the attribute is missing or its value is not `true`, the runtime treats the JAR normally and ignores the entries under `META-INF/versions`.

Version directory names must be valid release numbers from 9 onward. Do not use arbitrary names such as `latest`, `java17`, or `current`.

## 2. The Multi-Release Manifest

A JAR only behaves according to multi-release rules when the main manifest contains the attribute:

~~~text
Multi-Release: true
~~~

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Multi-Release: true

~~~

The trailing blank line in the manifest terminates the main attributes section. The `Multi-Release` attribute must be in the main section of the manifest; do not place it in a per-entry section.

Manifest attribute names are case-insensitive according to manifest rules, but you should use the standard spelling `Multi-Release` for readability and tool compatibility.

If you use the `jar` tool with the `--release` option to create versioned entries, inspect the output manifest to ensure `Multi-Release: true` is set. In the hands-on example below, the manifest is created explicitly so the result is easy to control.

You can inspect the manifest inside a JAR with:

~~~bash
jar --extract --file build/mr-demo.jar META-INF/MANIFEST.MF
~~~

Then read the `META-INF/MANIFEST.MF` file. You can use `jar --list` to verify that the manifest and versioned entries have been packaged.

## 3. Why Use a Multi-release JAR?

A library may want to support multiple Java versions while still taking advantage of newer APIs when the runtime supports them.

For example, the base implementation can use older standard APIs:

~~~java
public final class RuntimeInfo {
    public static String message() {
        return "Base implementation";
    }
}
~~~

The Java 9+ implementation can use newer APIs, such as `ProcessHandle`:

~~~java
public final class RuntimeInfo {
    public static String message() {
        return "Process id: " + ProcessHandle.current().pid();
    }
}
~~~

If you put a class using `ProcessHandle` in the JAR root, Java 8 cannot load it because the API does not exist in Java 8. An MR-JAR lets you keep the compatible base class in the root and place the new implementation under `META-INF/versions/9`.

Common use cases:

- Using newer JDK APIs in the implementation while maintaining an older Java baseline.
- Optimizing implementations per runtime, such as using newer APIs or algorithms.
- Providing a separate implementation for a release with performance or behavioral changes.
- Packaging a module descriptor for Java 9+ while preserving usability as a JAR on older classpaths.
- Replacing resources or internal implementations based on the Java version.

MR-JARs are most useful for libraries that expose the same public API across multiple runtimes. Applications deployed on a fixed Java version typically do not need multiple versions of a class in the same artifact.

## 4. Compatibility Rules Between Versions

Versions of the same type should maintain a binary-compatible public API. A program compiled against the base class must be able to link against the implementation chosen by the runtime.

For example, if the base version provides:

~~~java
public static String message()
~~~

then the version in `META-INF/versions/9` should continue to provide a method with the same name, appropriate modifiers, return type, and compatible descriptor. If a versioned class removes a method or changes its descriptor, compiled programs may encounter `NoSuchMethodError`, `IllegalAccessError`, or other linkage errors when running on a newer runtime.

You can change the internal implementation while preserving the API:

- Use newer JDK APIs in the method body.
- Change internal algorithms.
- Optimize storage or processing.
- Call helper implementations that only exist in the versioned tree, provided those helpers are not referenced by base code.

Do not assume every class in versioned directories is replaced the same way if package structures or dependencies are inconsistent. Clearly identify which classes are replacement points and which classes exist only on newer runtimes.

If you add a new class only to the versioned tree without placing it in the base, that class can only be used on runtimes that have the corresponding versioned entry. Base source code or bytecode must not depend on classes that exist only in newer versions if it needs to run on older Java.

## 5. Compiling Base and Versioned Classes

A common layout separates sources by release:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/
│   └── java9/
│       └── java/
└── build/
    ├── base/
    └── java9/
~~~

The base source is compiled with the lowest release the library supports. The Java 9 source is compiled with `--release 9` and a classpath containing the base output if it needs to reference shared APIs.

For example:

~~~bash
javac --release 8 -d build/base src/main/java/com/example/RuntimeInfo.java
javac --release 9 -cp build/base -d build/java9 src/java9/java/com/example/RuntimeInfo.java
~~~

The `--release` option controls the language level, platform APIs, and class file target for the specified release. This helps prevent accidentally using newer APIs in the base implementation.

Do not use `-source 8 -target 8` as the default choice for new builds when `--release` is available. Specifying source and target separately does not restrict which JDK APIs the source code is allowed to call.

If the base target is Java 8, the versioned implementation for Java 9 must be compiled against Java 9 or newer APIs. A versioned class in `META-INF/versions/17` should be compiled with `--release 17` or an equivalent environment; never place a class file with a higher version inside a lower-version directory.

Each versioned source typically keeps the same package and binary name as the base class it replaces. This allows the runtime to select an implementation under the same class name that calling code was compiled against.

## 6. Packaging with `jar --release`

The JDK `jar` tool supports the `--release VERSION` option when creating or updating an MR-JAR. This option places subsequent files into the `META-INF/versions/VERSION` directory in the archive.

Illustrative syntax:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/java9 .
~~~

In this example:

- Content from `build/base` is placed at the JAR root.
- Files after `--release 9` are placed under `META-INF/versions/9`.
- The package directory tree is preserved within each region.

You can add multiple releases:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/java9 . \
    --release 17 -C build/java17 .
~~~

When packaging multiple releases, each output directory must contain only the classes/resources intended for the corresponding release. Do not arbitrarily dump the entire source tree or build directory into the archive.

If you build a JAR using a zip tool or another packaging utility, you must ensure the `META-INF/versions/N` structure and `Multi-Release: true` manifest are properly formatted yourself. Using the `jar` tool reduces the risk of misplaced entries.

## 7. Complete Example: A JAR Running on Java 8 and Java 9+

This example creates a program with a Java 8-compatible base implementation and a separate implementation for Java 9 and later. Both expose the same `message()` method.

Project structure:

~~~text
mr-demo/
├── src/
│   ├── base/
│   │   └── com/example/runtime/
│   │       ├── Main.java
│   │       └── RuntimeInfo.java
│   └── java9/
│       └── com/example/runtime/
│           └── RuntimeInfo.java
└── build/
~~~

### Step 1: Base Implementation

Create `src/base/com/example/runtime/RuntimeInfo.java`:

~~~java
package com.example.runtime;

public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static String message() {
        return "Base implementation";
    }
}
~~~

This class uses only syntax and APIs available in Java 8.

Create `src/base/com/example/runtime/Main.java`:

~~~java
package com.example.runtime;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(RuntimeInfo.message());
    }
}
~~~

`Main` only calls the shared API defined in the base class. Therefore, the same `Main.class` can run with whichever `RuntimeInfo.class` is selected from the root or from a versioned directory.

### Step 2: Implementation for Java 9+

Create `src/java9/com/example/runtime/RuntimeInfo.java`:

~~~java
package com.example.runtime;

public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static String message() {
        long pid = ProcessHandle.current().pid();
        return "Java 9+ implementation, pid=" + pid;
    }
}
~~~

`ProcessHandle` was added in Java 9. If this class were placed in the root, Java 8 could not load it. Placing it in a separate source tree and packaging it under `META-INF/versions/9` allows Java 8 to continue using the base implementation.

### Step 3: Compile Both Versions

From the `mr-demo` root directory, create the output directories:

~~~bash
mkdir -p build/base build/java9
~~~

Compile the base for Java 8:

~~~bash
javac --release 8 -d build/base \
    src/base/com/example/runtime/RuntimeInfo.java \
    src/base/com/example/runtime/Main.java
~~~

Compile the Java 9 implementation:

~~~bash
javac --release 9 -cp build/base -d build/java9 \
    src/java9/com/example/runtime/RuntimeInfo.java
~~~

This step produces:

~~~text
build/
├── base/
│   └── com/example/runtime/
│       ├── Main.class
│       └── RuntimeInfo.class
└── java9/
    └── com/example/runtime/
        └── RuntimeInfo.class
~~~

### Step 4: Create the Manifest

Create `build/manifest.mf`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.runtime.Main
Multi-Release: true

~~~

The manifest must end with a blank line. `Multi-Release: true` enables versioned entry selection. `Main-Class` allows running the JAR with `java -jar`.

### Step 5: Package the MR-JAR

Create the archive:

~~~bash
jar --create --file build/mr-demo.jar \
    --manifest build/manifest.mf \
    -C build/base . \
    --release 9 -C build/java9 .
~~~

The archive should contain:

~~~text
META-INF/MANIFEST.MF
com/example/runtime/Main.class
com/example/runtime/RuntimeInfo.class
META-INF/versions/9/com/example/runtime/RuntimeInfo.class
~~~

The base `RuntimeInfo.class` is at the root. The Java 9 version is under `META-INF/versions/9`.

### Step 6: Inspect the JAR Structure

List the archive:

~~~bash
jar --list --file build/mr-demo.jar
~~~

Verify that both entries exist:

~~~text
com/example/runtime/RuntimeInfo.class
META-INF/versions/9/com/example/runtime/RuntimeInfo.class
~~~

Read the manifest:

~~~bash
jar --extract --file build/mr-demo.jar META-INF/MANIFEST.MF
~~~

Check that the manifest file contains `Multi-Release: true`.

Newer JDKs also provide an MR-JAR validation mode:

~~~bash
jar --validate --file build/mr-demo.jar
~~~

This command helps validate the multi-release contents according to the rules known to the `jar` tool. It does not replace testing on each target runtime.

### Step 7: Run on the Runtimes

On Java 8:

~~~bash
java -jar build/mr-demo.jar
~~~

Output:

~~~text
Base implementation
~~~

Java 8 does not apply multi-release rules, so it uses the class at the JAR root.

On Java 9 and later:

~~~bash
java -jar build/mr-demo.jar
~~~

Output looks like:

~~~text
Java 9+ implementation, pid=12345
~~~

The PID value varies by actual process. On Java 17 or Java 21, the runtime still selects version 9 if the JAR does not have a matching higher versioned entry.

This is the exact same JAR file. The difference comes from which entry the runtime selects when loading `com.example.runtime.RuntimeInfo`.

## 8. Inspecting Each Version with `javap`

You can use `javap` to inspect the class that an MR-JAR provides for a specific release.

Inspect the base version:

~~~bash
javap --multi-release base -classpath build/mr-demo.jar -c com.example.runtime.RuntimeInfo
~~~

Inspect version 9:

~~~bash
javap --multi-release 9 -classpath build/mr-demo.jar -c com.example.runtime.RuntimeInfo
~~~

The `--multi-release` option lets you select the base view or a specific release when reading classes from a multi-release archive. Use `-c` to inspect the bytecode and confirm which implementation is selected.

If you want to inspect descriptors or detailed flags:

~~~bash
javap --multi-release 9 -classpath build/mr-demo.jar -v com.example.runtime.RuntimeInfo
~~~

Do not run `javap` on an extracted class file and assume that is the version the runtime will load. Specify `--multi-release` when your goal is to inspect how `javap` resolves entries from an MR-JAR.

## 9. Multi-release JARs and `module-info.class`

An MR-JAR can provide a module descriptor for Java 9+ while keeping class contents usable on Java 8. A common approach is placing `module-info.class` under:

~~~text
META-INF/versions/9/module-info.class
~~~

A Java 8 JVM does not understand JPMS, so it ignores the descriptor in the versioned directory and still uses the classes at the JAR root like a regular library.

A Java 9+ JVM can read the versioned descriptor to treat the JAR as a named module when placed on the module path. The descriptor must accurately declare the module name, `requires`, `exports`, `opens`, `uses`, and `provides`.

You can inspect the module descriptor in the archive with:

~~~bash
javap --multi-release 9 -v -classpath build/library.jar module-info
~~~

Or use:

~~~bash
jar --describe-module --file build/library.jar
~~~

The `jar --describe-module` command produces a human-readable module description. `javap` allows inspecting the class file and `Module` attribute in greater detail.

If a module descriptor is only present in version 9, the JAR can still work as a regular JAR on Java 8. This is a major benefit when a library needs to support both older classpaths and the newer module path.

## 10. Versioned Resources

An MR-JAR can also contain versioned resources, not just class files. For example, a resource might be located at:

~~~text
config/defaults.properties
META-INF/versions/11/config/defaults.properties
~~~

When accessing a resource through a multi-release-aware JAR or class loader mechanism, the runtime can select the version matching the Java release. This is useful when resource content depends on the runtime or when default configurations need to change based on platform APIs.

Do not confuse versioned resources with separate configuration files that an application selects manually by checking `java.version`. If you want the JVM to apply MR-JAR rules automatically, the resource must be in the right location and the manifest must enable `Multi-Release`.

Test how your library reads resources on the target runtimes, especially if using custom resource APIs, frameworks, or packaging tools with their own JAR handling.

## 11. Organizing Sources and Builds in Real Projects

A project can organize sources by baseline and target releases:

~~~text
library/
├── src/
│   ├── main/
│   │   └── java/
│   ├── java9/
│   │   └── java/
│   └── java17/
│       └── java/
├── build/
│   ├── classes/
│   │   ├── base/
│   │   ├── java9/
│   │   └── java17/
│   └── libs/
└── build.gradle
~~~

The build pipeline needs to:

1. Compile the base source with the lowest supported release.
2. Compile each versioned source set with its corresponding release.
3. Place class outputs into separate directories.
4. Verify binary names and APIs across replacement versions.
5. Generate a manifest containing `Multi-Release: true`.
6. Package base entries and versioned entries into the same archive.
7. Inspect the archive entry list and manifest.
8. Run tests on each target JDK.

### Gradle

The Gradle Java plugin can use separate source sets or configure dedicated compile tasks per release. A practical configuration must ensure that the output of the Java 9 source set is placed in the versioned path during packaging.

Conceptual model:

~~~groovy
tasks.jar {
    manifest {
        attributes("Multi-Release": "true")
    }

    into("META-INF/versions/9") {
        from(sourceSets.java9.output)
    }
}
~~~

This is an illustrative packaging snippet. The project needs to define `sourceSets.java9` and its corresponding compile task, set release 9, and configure the appropriate dependency classpath. If using a convention plugin or a dedicated MR-JAR plugin, check the configuration for that exact plugin version.

### Maven

With Maven, you can configure separate compiler executions or profiles for the base and each release, then use the JAR plugin to place versioned outputs into `META-INF/versions/N`. The exact configuration depends on the Maven Compiler Plugin and Maven JAR Plugin versions.

Do not simply change `maven.compiler.release` once for the entire project if multiple implementations are required. Each source set must be compiled with its own target release and packaged into the proper versioned directory.

Whether using Gradle, Maven, or `javac`/`jar` scripts, the final result must follow the same JAR structure and manifest attribute.

## 12. Common Limitations and Pitfalls

### Missing `Multi-Release: true`

If the manifest lacks this attribute, the JVM will not select entries under `META-INF/versions`. It will use the classes at the root like a standard JAR.

Inspect the actual packaged manifest rather than just the input manifest file. Some build tasks may overwrite or merge manifests unexpectedly.

### Incorrect Versioned Directory Paths

Paths must follow the format:

~~~text
META-INF/versions/9/com/example/RuntimeInfo.class
~~~

Paths such as `versions/9`, `META-INF/version/9`, or `META-INF/versions/java17` are invalid under MR-JAR conventions.

### Placing Newer Class Files in Lower-Release Directories

A class placed under `META-INF/versions/9` must be compatible with release 9. If compiled with a newer JDK without restricting the release, the class file may require a newer JVM and cause `UnsupportedClassVersionError` when selected on Java 9 or 11.

Use `javac --release N` for each source set and verify the class file major version.

### Versioned Implementation Breaking API Compatibility

If the base class has a method that the versioned class omits, compiled code may fail with linkage errors on newer runtimes. Keep descriptors and the public contract compatible, and only change the internal implementation.

### Forgetting Shared Compilation Dependencies

Versioned sources often need to reference base classes or shared annotations/interfaces. Include the base output on the classpath when compiling versioned sources.

### Packaging at the Wrong Directory Level

When creating the JAR, use `-C` to include the contents of the output directory into the archive. If you include the `build/java9` directory itself rather than its contents, entries may be nested an extra level deep and the JVM will not find the versioned path.

### Assuming Java 8 Can Read New Implementations

Java 8 does not apply MR-JAR rules. It uses base entries. Therefore, every class referenced by base code must exist in the root JAR and be compatible with Java 8.

### Testing on Only One JDK

An MR-JAR is designed to run across multiple runtimes. Testing on a single JDK does not prove that the base version runs on older Java or that the versioned implementation works on newer Java. You need a test matrix covering the baseline and every release with source overrides.

### Modifying the JAR After Signing

If a JAR has already been signed, changing its contents or manifest can invalidate the signature. Finalize all base/versioned entries and the manifest before signing the final artifact.

## 13. Testing and Diagnosing MR-JARs

A useful checklist:

- Confirm the manifest has `Multi-Release: true` in the main section.
- Confirm base classes are at the JAR root.
- Confirm versioned classes are under `META-INF/versions/N`.
- Confirm `N` is 9 or higher.
- Check that class file versions match their directory's release.
- Use `javap --multi-release base` and `javap --multi-release N` to compare.
- Run on the older Java baseline to verify the base implementation.
- Run on each newer runtime to verify the versioned implementations.
- Verify API and binary compatibility across versions.
- Use `jar --validate` when supported by your JDK.
- Inspect the manifest and archive listing after building.
- Run tests for resource loading and module path if the JAR provides those.

When troubleshooting, first determine which entry the runtime selected. If a class is not being replaced, check the manifest and paths. If you encounter `UnsupportedClassVersionError`, check the release used to compile the class. If you encounter `NoSuchMethodError` or `AbstractMethodError`, compare the API between the base and versioned classes.

Do not inspect only the source tree. Inspect the actual released JAR, because issues often occur during packaging, manifest merging, or output directory assembly.

## 14. When Should You Use a Multi-release JAR?

Consider an MR-JAR when:

- A library must maintain an older Java baseline while wanting to leverage newer APIs.
- There are clear, release-specific replacement implementations.
- The same public contract can be maintained across versions.
- The build pipeline can compile and test each source set.
- The artifact needs to be distributed under a single name and version.

Do not use it just to package multiple copies of classes without a specific runtime reason. Each versioned source increases build, testing, debugging, and release complexity. If you only support a single Java version, a single implementation is usually much easier to maintain.

Multi-release JARs help a single artifact adapt to multiple runtimes by selecting classes or resources based on the feature version. To use them properly, you need a compatible base implementation, properly pathed versioned entries, a `Multi-Release: true` manifest, consistent APIs, and testing across target JDKs.
