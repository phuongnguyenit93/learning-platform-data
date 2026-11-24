# Effects of Class-Path, Package Sealing, and Multi-Release JARs

## Purpose

When packaging a Java plugin as a JAR, compiling source code successfully does not guarantee the plugin will load or behave properly at runtime. Three mechanisms directly affect that behavior:

1. **Class path** determines where the JVM and class loaders look for classes, resources, and service descriptors.
2. **Package sealing** requires that all classes in the same package originate from the same code source (typically the same JAR) when defined within the same class loader.
3. **Multi-release JAR (MR-JAR)** allows a single JAR to contain different implementations depending on the Java Runtime version.

These mechanisms address different problems. Class path does not provide plugin isolation by itself, sealing is not a security sandbox, and MR-JAR does not select versions by application or framework: it selects by Java Runtime version.

## 1. How Does Class Path Affect Plugins?

### 1.1. Locating Classes and Resources

In a simple model using the application class loader, the command:

\`\`\`bash
java -cp "app.jar:plugin.jar:api.jar" demo.host.Main
\`\`\`

allows classes and resources to be found across the three JARs on the class path. On Windows, the entry separator is \`;\`, for example:

\`\`\`powershell
java -cp "app.jar;plugin.jar;api.jar" demo.host.Main
\`\`\`

\`-cp\` and \`-classpath\` are equivalent. Normally the JVM obtains the class path from \`-cp\`, \`--class-path\`, or the \`CLASSPATH\` environment variable when no corresponding command-line option is given. The class to load must belong to the proper package, have a corresponding \`.class\` file at that path inside the JAR, and have all required dependencies visible from the class loader.

For example, the class \`demo.plugin.UppercasePlugin\` must reside at:

\`\`\`text
plugin.jar
└── demo/plugin/UppercasePlugin.class
\`\`\`

If the plugin is discovered via Java SPI, the JAR must also contain:

\`\`\`text
META-INF/services/demo.api.MessagePlugin
\`\`\`

and this file's contents must list the fully qualified provider name, such as \`demo.plugin.UppercasePlugin\`. \`ServiceLoader\` reads descriptors through the class loader being used; a JAR present on disk but not on the class path or in an appropriate class loader will not be discovered automatically.

### 1.2. Class Path Ordering, Duplicate Versions, and Dependencies

If two JARs contain the same binary name, e.g., both contain \`demo.util.Helper\`, behavior depends on the class loader and lookup order. With a typical application class loader, the class found earlier on the class path may be loaded; other class loaders or specialized launchers may follow different policies. You should not rely on JAR ordering as a plugin version-selection mechanism.

A common failure scenario:

\`\`\`text
host.jar       → uses util library version 2
plugin-old.jar → bundles util version 1 in the same package
\`\`\`

If both versions are placed together in one class loader, the version the JVM loads may not match the version used at compile time. Common symptoms are \`NoSuchMethodError\`, \`NoClassDefFoundError\`, or subtle behavioral changes.

Mitigations:

- Define the shared API in **one contract JAR** used by both host and plugins, avoiding duplicate packaging of the contract under different class loaders.
- Declare and test each plugin's runtime dependencies. Standard JARs do not automatically bundle external dependencies.
- For systems requiring multiple versions of the same library, consider per-plugin class loaders, module layers, or controlled namespace renaming via shading; carefully evaluate shared interfaces and resources.
- Verify with \`jar --list --file plugin.jar\`, the build tool's dependency tree, and class-loading logs when diagnosing failures (\`-Xlog:class+load=info\` on modern HotSpot).

### 1.3. Class-Path in MANIFEST.MF

Besides the command-line class path, a JAR's manifest can contain the **\`Class-Path\`** attribute to reference other JARs/paths according to the JAR manifest specification. For example:

\`\`\`text
Manifest-Version: 1.0
Main-Class: demo.host.Main
Class-Path: lib/api.jar lib/helper.jar
\`\`\`

With the executable JAR in the \`dist/\` directory, the layout may look like:

\`\`\`text
dist/
├── host.jar
└── lib/
    ├── api.jar
    └── helper.jar
\`\`\`

Run:

\`\`\`bash
java -jar dist/host.jar
\`\`\`

For the \`java -jar\` launcher, the manifest's \`Main-Class\` determines the entry point; a user-supplied \`-cp\` option does not replace the application's class path when running in \`-jar\` mode. The manifest \`Class-Path\` helps the JAR reference supporting libraries placed in the right locations; it declares listed dependencies, rather than instructing the JVM to scan an entire plugin directory.

**Note:** the manifest \`Class-Path\` takes a space-separated list of relative URLs, not \`:\` or \`;\` like \`-cp\`. Relative paths are resolved against the location of the JAR containing the manifest; JAR specification constraints and validity rules apply. If you simply need to run an application quickly with supporting libraries, using \`java -cp\` or a controlled launcher is often clearer.

### 1.4. Wildcard Class Path

\`\`\`bash
java -cp "dist/host.jar:dist/lib/*" demo.host.Main
\`\`\`

\`dist/lib/*\` adds the JARs in that directory to the class path via the Java launcher's wildcard expansion. It does not recursively scan subdirectories; the order in which JARs are listed should not be assumed stable. Wildcards are convenient for simple environments, but do not solve dependency conflicts, version pinning, or runtime plugin updates after the JVM starts.

## 2. What Is Package Sealing?

### 2.1. Mechanism and Purpose

In a JAR manifest, the \`Sealed: true\` attribute marks packages as **sealed**. When a class loader defines a package from that JAR, any additional classes in the same package within that same class loader must originate from the same permitted code source according to sealing checks. This prevents splitting a sealed package across multiple source JARs.

An anti-pattern to avoid:

\`\`\`text
plugin-core.jar
└── com/example/plugin/core/Engine.class
    (package com.example.plugin.core is sealed)

plugin-extension.jar
└── com/example/plugin/core/Helper.class
    (same package, but from a different JAR)
\`\`\`

When the same class loader attempts to define both classes, a \`SecurityException: sealing violation\` can occur. Sealing restricts the code source defining classes in a package; it does not prevent a plugin from calling dangerous APIs, reading files, or executing code with the process's privileges.

### 2.2. JAR-Wide and Per-Package Manifests

A manifest can seal packages in a JAR by default:

\`\`\`text
Manifest-Version: 1.0
Sealed: true
\`\`\`

Or seal only a specific package, using a named section whose package path ends with \`/\`:

\`\`\`text
Manifest-Version: 1.0

Name: com/example/plugin/internal/
Sealed: true
\`\`\`

Blank lines in a manifest separate the main attributes from named sections, so they are syntactically significant. Section names use \`/\` path separators rather than \`.\`. The manifest is packaged at \`META-INF/MANIFEST.MF\`.

Example creating a JAR from compiled classes with a custom manifest:

\`\`\`bash
jar --create --file plugin.jar --manifest MANIFEST.MF -C build/classes .
\`\`\`

Do not arbitrarily overwrite \`META-INF/MANIFEST.MF\` after building; packaging tools may generate additional manifest attributes and sections.

### 2.3. Practical Effects When Splitting Plugins

- A plugin's internal packages should have a dedicated namespace, such as \`com.acme.plugin.csv.internal\`, avoiding sharing internal packages with the host or other plugins.
- If you intentionally split a package across multiple JARs inside the **same class loader**, sealing can cause that design to fail. Consider consolidating classes of a sealed package into a single artifact or renaming the package.
- Two class loaders can independently define packages with the same name; sealing is checked within the package-definition scope of each loader. However, classes loaded from different loaders may be type-incompatible even with identical names.
- Once a package has been defined as sealed, another JAR declaring unsealed does not make it compatible; sealing and code-source consistency must hold across the class-loading layout.
- JPMS named modules have their own package/module rules and split-package restrictions; manifest sealing should not be treated as a replacement for module rules.

### 2.4. Minimal Example Verifying Sealing

Create the source tree:

\`\`\`text
src-a/demo/shared/A.java
src-b/demo/shared/B.java
\`\`\`

Contents of \`src-a/demo/shared/A.java\`:

\`\`\`java
package demo.shared;
public class A {
    public static String name() { return "A"; }
}
\`\`\`

Contents of \`src-b/demo/shared/B.java\`:

\`\`\`java
package demo.shared;
public class B {
    public static String name() { return "B"; }
}
\`\`\`

Compile two separate JARs and seal JAR A:

\`\`\`bash
mkdir -p build/a build/b
javac -d build/a src-a/demo/shared/A.java
javac -d build/b src-b/demo/shared/B.java
printf 'Manifest-Version: 1.0\nSealed: true\n' > seal.mf
jar --create --file a.jar --manifest seal.mf -C build/a .
jar --create --file b.jar -C build/b .
\`\`\`

File \`TestSealing.java\`:

\`\`\`java
public class TestSealing {
    public static void main(String[] args) throws Exception {
        Class.forName("demo.shared.A");
        Class.forName("demo.shared.B");
    }
}
\`\`\`

Run (Linux/macOS):

\`\`\`bash
javac TestSealing.java
java -cp ".:a.jar:b.jar" TestSealing
\`\`\`

When the same loader loads \`A\` first (defining the sealed package from source \`a.jar\`) and then attempts to define \`B\` from \`b.jar\`, the program fails with a \`SecurityException\` due to a sealing violation. Do not rely on the exact error message text or stack trace, as these vary by runtime. Removing sealing or moving the classes into different packages eliminates this sealing conflict.

On Windows, create \`seal.mf\` with an editor supporting UTF-8 and standard newlines, then run \`java -cp ".;a.jar;b.jar" TestSealing\`. The shell example above uses POSIX \`printf\`.

## 3. Multi-Release JAR: Same API, Runtime-Dependent Implementation

### 3.1. Structure and Class Selection

Multi-release JARs (JEP 238, since Java 9) allow default code at the root and alternative classes under \`META-INF/versions/<N>/\`, where \`N\` is a Java version of at least 9. The manifest must include:

\`\`\`text
Manifest-Version: 1.0
Multi-Release: true
\`\`\`

Typical structure:

\`\`\`text
library.jar
├── META-INF/MANIFEST.MF
├── demo/feature/RuntimeFeature.class
└── META-INF/versions/
    ├── 11/demo/feature/RuntimeFeature.class
    └── 17/demo/feature/RuntimeFeature.class
\`\`\`

On Java 8, the JVM uses the root class. On Java 11, an MR-JAR-aware runtime selects the version 11 implementation if present; Java 17 prefers the version 17 implementation. On newer runtimes, the class loader picks the highest version **not exceeding** the current Java version. If no matching override class exists, it falls back to a lower version or the root. This applies to Java's standard MR-JAR reader; custom ZIP-processing tools or custom loaders must be verified for MR-JAR support.

\`META-INF/versions/\` does not create independent packages at runtime: selected classes share the same binary name. The public/protected API of versioned classes must remain contract-compatible with the base class so the same JAR does not exhibit unpredictable behavior to callers.

### 3.2. When to Use MR-JARs in Plugins?

Suppose a plugin supports multiple runtimes while optimizing execution on newer Java releases:

- The root implementation uses older Java APIs to maintain baseline runtime compatibility.
- Versioned implementations use optimized APIs or utilities from Java 11/17.
- The host calls a stable contract without writing \`if (javaVersion >= 17)\` class-switching logic itself.
- A single JAR can be distributed across environments, reducing the number of artifacts to manage.

An MR-JAR only swaps classes/resources according to platform rules. It does not allow bytecode compiled for target Java 17 to run on Java 11 if the Java 17 class was mistakenly placed at the root, nor does it replace contract API versioning.

### 3.3. Runnable MR-JAR Example on Java 17

Create two versions of the same class \`demo.feature.Message\`:

\`\`\`text
src/base/demo/feature/Message.java
src/java17/demo/feature/Message.java
\`\`\`

Base:

\`\`\`java
package demo.feature;
public class Message {
    public static String text() {
        return "base";
    }
}
\`\`\`

Java 17:

\`\`\`java
package demo.feature;
public class Message {
    public static String text() {
        return "java17";
    }
}
\`\`\`

File \`Main.java\`:

\`\`\`java
import demo.feature.Message;
public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
\`\`\`

From the example's root directory, run with JDK 17+:

\`\`\`bash
mkdir -p build/base build/v17 build/main
javac --release 8 -d build/base src/base/demo/feature/Message.java
javac --release 17 -d build/v17 src/java17/demo/feature/Message.java
jar --create --file feature.jar -C build/base . \
  --release 17 -C build/v17 .
javac --release 8 -cp feature.jar -d build/main Main.java
java -cp "build/main:feature.jar" Main
\`\`\`

Output on Java 17:

\`\`\`text
java17
\`\`\`

The JDK's \`jar --release 17\` option creates the versioned entry and configures \`Multi-Release: true\` in the manifest accordingly. \`javac --release 8\` compiles the root with Java 8-compatible APIs and bytecode. A Java 8 runtime can execute the base class, provided the app uses no newer Java APIs and the runtime can read that JAR; on Java 11 (with no version 11 override), the output is \`base\`. You cannot verify Java 8/11 behavior on a machine with only JDK 17 installed; you must run on the target runtimes.

To inspect entries and manifest:

\`\`\`bash
jar --list --file feature.jar
jar --describe-module --file feature.jar
\`\`\`

The first command should show \`demo/feature/Message.class\`, \`META-INF/versions/17/demo/feature/Message.class\`, and the manifest. \`jar --describe-module\` is useful when inspecting module metadata, but does not replace checking the manifest or running on each supported JVM.

### 3.4. Implications for APIs, Testing, and Analysis

- Compilers, IDEs, bytecode scanners, code coverage tools, shading, obfuscation, and build tools must understand versioned entries; otherwise they may mis-scan, miss, or corrupt MR-JAR structures.
- Root and versioned variants must maintain a stable API contract; test on **every declared supported Java version**, not just the build JDK.
- If the plugin is loaded by a custom class loader, verify that the loader accesses JARs in an MR-JAR-aware manner. Reading the ZIP file directly may expose multiple physical entries instead of the single class selected for the current JVM.
- Do not place service descriptors in versioned areas expecting SPI to switch providers by runtime: service resource discovery must be verified separately; normally keep \`META-INF/services\` in the standard location and vary the implementation via versioned binary classes.
- Beware of versioned class bytes depending on classes unavailable on that runtime or missing runtime dependencies, causing the plugin to fail despite a valid manifest.

## 4. How Do the Three Mechanisms Interact?

| Scenario | Governing Mechanism | Practical Consequence |
|---|---|---|
| Plugin JAR sits outside class path / class loader | Class path / ClassLoader | Host cannot find classes or service providers |
| Two plugins have identically named classes in a shared loader | Class path lookup and class-defining authority | Wrong implementation/version may load; avoid class collisions |
| Same package in two JARs, one package is sealed | Package sealing | May throw \`SecurityException\` due to code-source violation |
| An MR-JAR has a root class + version 17 | Multi-release lookup | Java 17 selects the version 17 class; older runtimes pick an appropriate version |
| MR-JAR released without \`Multi-Release: true\` | Manifest / JAR processing | Versioned classes are not used as standard overrides |
| Plugin uses Java 17 dependencies while host runs Java 11 | Runtime compatibility | May fail with \`UnsupportedClassVersionError\` or missing API errors |
| Host and plugin load contract via two different loaders | Class identity | Identically named interfaces may fail to cast |

A pragmatic approach is keeping the shared API JAR small, specifying version and class loader boundaries, giving each plugin a distinct package namespace, and enabling sealing or MR-JAR only when architecture truly requires it. The more packaging policies you combine, the more thorough your test matrix must be.

## 5. Diagnostic Workflow for Packaging Errors

1. **Verify bytecode and JAR contents.** Use \`jar --list --file <jar>\` to verify classes are at the right paths, along with the manifest, provider descriptors, and \`META-INF/versions/\`.
2. **Verify runtime and launcher.** Check \`java -version\`, inspect \`-jar\` vs. \`-cp\` invocation; verify OS-specific class path separators and locations of dependent JARs.
3. **Observe class loading.** On HotSpot, use \`-Xlog:class+load=info\` to see where classes load from; in diagnostic code, \`SomeClass.class.getClassLoader()\` reveals the defining loader.
4. **Check package sealing.** Read \`META-INF/MANIFEST.MF\` for \`Sealed\` in the main section or named package sections; check for packages split across multiple JARs and code sources.
5. **Check MR-JAR.** Verify \`Multi-Release: true\`, versioned paths, and class file versions; run real tests on supported Java Runtimes.
6. **Check compatibility and linkage errors.** Cross-check dependency versions; \`ClassNotFoundException\` usually means a class lookup by name failed, \`NoClassDefFoundError\` can indicate a required class was unavailable at runtime or failed initialization, \`NoSuchMethodError\` usually signals a binary API mismatch, and \`UnsupportedClassVersionError\` indicates a class file newer than the JVM can handle.

## 6. Plugin JAR Release Checklist

- [ ] Host, contract, and plugin JARs are compiled with the appropriate \`--release\` level; runtime dependencies are explicitly supplied.
- [ ] No duplicate contract copy is embedded to cause class-identity conflicts across loaders.
- [ ] \`Class-Path\` manifest attribute (if used) points to dependencies actually distributed and valid at the installation path.
- [ ] Wildcard JAR ordering is not relied upon to resolve duplicate versions.
- [ ] Sealing is applied only to packages with clear code-source boundaries, without accidentally sealing a package split across JARs.
- [ ] MR-JAR has the proper manifest and versioned entries; the root still runs on the supported baseline Java version.
- [ ] Tests cover plugin discovery, missing dependencies, multiple providers, sealing errors, and target JVM versions.
- [ ] Deployment documentation specifies Java Runtime requirements, API compatibility, class loader model, and install/uninstall steps.

**Remember:** Class path governs **where classes are searched**, package sealing governs **whether classes of the same package may come from another source**, and MR-JAR governs **which class variant is chosen for the Java Runtime**. When combining them in a plugin system, test all three at runtime rather than relying solely on a successful build.
