# What Information Module Versions Provide and Why a Separate Versioning Policy Is Needed

## 1. The problem: having a version in a module is not enough to manage compatibility

The Java Platform Module System (JPMS) supports attaching an **optional version** to a module. For example, module \`com.example.plugin.api\` may carry version \`2.1.0\`, and a program can read that information via \`ModuleDescriptor.version()\`.

However, **a module version is only metadata**, not a full dependency management mechanism like Maven or Gradle. The JPMS resolver does not interpret version ranges such as \`[2.0,3.0)\` to locate a compatible release, does not download the latest version from a repository, and does not decide whether upgrading a module is API-compatibility-safe.

In a plugin architecture, distinguish:

- **Module name**: the JPMS module identifier used for \`requires\` and resolution, e.g., \`com.example.plugin.api\`.
- **Module version**: optional version information in the descriptor, e.g., \`2.1.0\`.
- **API compatibility policy**: rules defined by the host and plugin framework deciding which plugins are allowed to connect to which APIs.
- **Artifact/dependency version**: the JAR or library release version managed by the build/deployment system.
- **Runtime requirement**: minimum Java version, module capabilities, class-file version, and execution capabilities.

A reliable host **reads the version, yet does not trust the version alone**: it must verify the supported contract, binary compatibility, dependency graph, required features, and runtime behavior.

## 2. Where is a module version declared?

In JPMS, an explicit module has \`module-info.java\`:

\`\`\`java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
\`\`\`

Java's \`module-info.java\` syntax **has no** \`version\` clause. Versions are attached during compilation/packaging or through supporting tools. For example:

\`\`\`bash
javac -d out/api src/api/module-info.java src/api/com/example/plugin/api/Plugin.java
jar --create --file plugin-api.jar --module-version 2.1.0 -C out/api .
\`\`\`

These commands assume the source files exist at the stated paths. \`--module-version\` adds the version into the generated JAR's module descriptor. This is module metadata, **not** a source directive \`requires com.example.plugin.api >= 2.0\`; JPMS does not support such version-range syntax in \`module-info.java\`.

Modules on the module path may be **explicit**, **automatic**, or **exploded**. How an available version is determined depends on the descriptor/artifact and the tool that built it. Do not infer a reliable version merely from a filename like \`foo-2.1.jar\`; \`ModuleDescriptor.version()\` is the data presented by JPMS, and it can be empty.

## 3. Reading ModuleDescriptor.version()

Key API:

\`\`\`java
ModuleDescriptor descriptor = reference.descriptor();
Optional<ModuleDescriptor.Version> version = descriptor.version();
\`\`\`

\`ModuleDescriptor.Version\` is JPMS's type for representing and comparing versions; it is not strictly synonymous with Semantic Versioning. Version strings are parsed according to JPMS rules, and formatting/ordering may differ from a plugin system's own release policy. If an application follows SemVer, it must use a dedicated SemVer-compliant parser and range rules.

Module versions are optional: \`version()\` may return \`Optional.empty()\`. An application should not silently default to \`0.0.0\` or treat a missing version as the latest release without an explicit policy.

Other metadata fields typically inspected alongside the version:

| Metadata | Meaning | What it does not guarantee by itself |
|---|---|---|
| \`descriptor.name()\` | JPMS module name | Trusted publisher |
| \`descriptor.version()\` | Declared version | Compatibility with the host |
| \`descriptor.requires()\` | Modules needed for linking | Compatible dependency versions |
| \`descriptor.exports()\` | Accessible packages | API semantic stability |
| \`descriptor.uses()\` | Services used by the module | Services are installed |
| \`descriptor.provides()\` | Advertised service providers | Provider is safe or initializes cleanly |

## 4. Java 17+ example: reading the version of a packaged module

This example creates a small module and uses \`ModuleFinder\` to read its descriptor before activating any plugin code.

Layout:

\`\`\`text
project/
├── src/
│   └── demo.plugin/
│       ├── module-info.java
│       └── demo/plugin/Greeter.java
└── InspectModuleVersion.java
\`\`\`

Contents of **\`src/demo.plugin/module-info.java\`**:

\`\`\`java
module demo.plugin {
    exports demo.plugin;
}
\`\`\`

Contents of **\`src/demo.plugin/demo/plugin/Greeter.java\`**:

\`\`\`java
package demo.plugin;

public final class Greeter {
    public static String greet() {
        return "hello";
    }
}
\`\`\`

Contents of **\`InspectModuleVersion.java\`**:

\`\`\`java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Comparator;

public class InspectModuleVersion {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java InspectModuleVersion <jar-or-directory>");
            System.exit(2);
        }

        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        finder.findAll().stream()
                .sorted(Comparator.comparing(r -> r.descriptor().name()))
                .forEach(InspectModuleVersion::print);
    }

    private static void print(ModuleReference reference) {
        ModuleDescriptor d = reference.descriptor();
        System.out.println("module=" + d.name());
        System.out.println("version=" +
                d.version().map(Object::toString).orElse("<none>"));
        System.out.println("automatic=" + d.isAutomatic());
        System.out.println("requires=" +
                d.requires().stream()
                        .map(ModuleDescriptor.Requires::name)
                        .sorted()
                        .toList());
    }
}
\`\`\`

In the \`project\` directory, run on JDK 17+ (POSIX shell):

\`\`\`bash
javac -d mods/demo.plugin \
  src/demo.plugin/module-info.java \
  src/demo.plugin/demo/plugin/Greeter.java

jar --create --file demo.plugin.jar \
  --module-version 2.1.0 \
  -C mods/demo.plugin .

javac InspectModuleVersion.java
java InspectModuleVersion demo.plugin.jar
\`\`\`

Stdout:

\`\`\`text
module=demo.plugin
version=2.1.0
automatic=false
requires=[java.base]
\`\`\`

\`java.base\` is an implicit dependency. If the module is packaged without \`--module-version\`, the \`version\` field may be \`<none>\`.

\`ModuleFinder.of(Path.of(args[0]))\` only reads module metadata from the path; the program never calls \`Greeter\`, creates a \`ModuleLayer\`, or activates the plugin. Bad paths, invalid artifacts, or duplicate/conflicting modules can cause \`FindException\` or related I/O errors, which must be classified in production deployments.

## 5. How does JPMS resolution use versions?

Consider:

\`\`\`java
module com.example.report.plugin {
    requires com.example.plugin.api;
}
\`\`\`

The \`requires\` directive names a **module**, without declaring minimum or maximum versions. The JPMS resolver uses \`ModuleFinder\` and parent configurations to locate modules by name and satisfy dependency/readability rules. It **does not negotiate version ranges** like a build tool's dependency resolver.

This leads to three consequences:

1. If \`com.example.plugin.api\` version \`1.0.0\` is on the module path, \`requires com.example.plugin.api;\` does not automatically reject it simply because the plugin needs a newer API.
2. If multiple JAR versions with the same module name appear in the same search scope, do not expect JPMS to pick the highest version according to SemVer.
3. When a required dependency version is missing, JPMS does not download a newer release from Maven Central or a plugin repository.

Module version is useful metadata for diagnostics and host-level policies, **not a substitute for checking binary, semantic, or provider capability compatibility**.

## 6. Why is a separate versioning policy needed?

A plugin system must answer questions that JPMS does not solve on its own:

- Is plugin \`csv-exporter 3.2.0\` compatible with host API \`2.4.0\`?
- Should a plugin requesting API \`2.x\` be allowed to run on API \`3.0.0\`?
- When two plugins share an ID yet have different versions, which one is selected?
- Is a module without a version allowed to run?
- When the host updates its API, which providers must rebuild or pass integration tests?
- Which features are actually present at runtime, regardless of declared module version?
- During rollback, does the host need to retain multiple plugin versions side by side?

JPMS cannot infer compatibility from version numbers. The host must establish an explicit **policy** and enforce it before loading/activating plugins.

Example simple policy:

\`\`\`text
Host API version: 2.4.0
Supported plugin API major: 2
Plugin requires API major: 2 -> allowed candidate
Plugin requires API major: 3 -> rejected
Unknown API major -> rejected until reviewed
\`\`\`

This is only an **initial compatibility filter**. Sharing the same major version still does not guarantee every method/behavior is compatible if developers broke the contract or used removed APIs. You still need contract tests, checks for present methods/classes, feature negotiation, and runtime testing.

## 7. Distinguishing version types in a plugin ecosystem

| Type | Example | Authority |
|---|---|---|
| JPMS module version | \`com.example.plugin.api@2.4.0\` | Build/packaging metadata |
| Plugin implementation version | \`csv-exporter 1.7.0\` | Plugin publisher |
| Host API version | \`2.4.0\` | Extension contract owner |
| Plugin API requirement | \`>=2.2,<3.0\` | Plugin metadata/descriptor + host policy |
| JVM/runtime requirement | Java 17+ | Build target, bytecode, and used features |
| Artifact dependency version | \`library-x:4.1.2\` | Build/deployment resolution |
| Capability version | \`export.csv.v2\` | Protocol/feature negotiation |

Do not reuse a single version string for everything. A plugin at version \`5.0.0\` may still target host API \`2.x\`; conversely, a plugin at version \`1.0.0\` may require host API \`3.x\`.

If the module descriptor only contains \`version=1.7.0\`, the host still does not know which API the plugin requires. Custom metadata can live in a manifest or plugin descriptor:

\`\`\`text
Plugin-Id: csv-exporter
Plugin-Version: 1.7.0
Plugin-Api-Range: [2.2.0,3.0.0)
Required-Java-Version: 17
\`\`\`

These \`Plugin-*\` fields are application conventions, **not standard JPMS attributes**; ranges work only when the host defines and implements its own parser and policy.

## 8. Semantic Versioning and practical compatibility

Semantic Versioning is typically written \`MAJOR.MINOR.PATCH\` with the meaning:

- **MAJOR** for incompatible API changes.
- **MINOR** when adding backward-compatible functionality.
- **PATCH** for contract-preserving bug fixes.

However, SemVer is **reliable only when a project follows release discipline and clearly defines its public API**. In particular, changes to behavior, serialization formats, threading, or security policies can break compatibility even when method signatures remain intact.

Common version-comparison mistakes:

- Comparing with \`String.compareTo\`: \`"2.10.0"\` sorts differently lexicographically compared to \`"2.9.0"\`.
- Splitting on dots and comparing \`int\`s only: ignores prereleases like \`2.0.0-rc.1\`, build metadata, and SemVer precedence rules.
- Assuming \`ModuleDescriptor.Version\` is always a full SemVer parser/comparator.
- Relying on “same major means completely safe” without contract testing.

Use a trustworthy version-range library or implement a strictly tested parser matching the specification chosen by your plugin system. Define policies for prereleases, snapshots, and missing or invalid versions.

## 9. Pre-activation compatibility verification flow

A practical pre-activation pipeline:

\`\`\`text
Untrusted plugin artifact
        |
        v
Verify source, hash/signature, metadata/schema
        |
        v
Read module descriptor + plugin descriptor
        |
        v
Determine plugin ID/version, API requirement, Java requirement
        |
        v
Check version policy and feature/capability requirements
        |
        v
Check module/dependency graph, duplicate module names
        |
        v
Resolution + layer/class loader
        |
        v
Verify service provider contract + init/health check
        |
        v
Publish plugin active
\`\`\`

**Reject before initialization** if the policy is not met. Do not use \`Class.forName\` to “inspect metadata” of an unapproved plugin, because class loading/initialization can execute static code or cause side effects.

If multiple major APIs must be supported simultaneously, you can ship adapters or separate API modules, yet class identity and compatibility must be designed carefully. You cannot simply place two JARs with the same module name and different versions in the same module graph and expect JPMS to pick the right one per plugin.

## 10. Binary compatibility differs from module version

Two API builds can share the exact same module name while having different classes/methods. For example:

\`\`\`java
// API v1
public interface Exporter {
    byte[] export(String input);
}
\`\`\`

\`\`\`java
// API v2 - signature changed, potentially breaking compatibility
public interface Exporter {
    byte[] export(String input, String format);
}
\`\`\`

If a plugin was built against API v1 yet the runtime host runs API v2, \`NoSuchMethodError\`, \`AbstractMethodError\`, or other linkage errors can arise depending on call sites and how the plugin was compiled/deployed. Looking at the module version alone does not prove compatibility.

Even adding an abstract method to an interface can cause old implementations to fail when the new method is called. Adding a \`default\` method can be friendlier in some cases, yet method conflicts and semantics must still be assessed.

API comparison tools, binary compatibility checks, and integration tests complement version-based policies. For plugin interfaces, design extensible contracts, grouped capabilities, and clear deprecation rules.

## 11. Versioning in ModuleLayer and hot reload

A \`ModuleLayer\` is a runtime configuration built from a resolved module graph. Once a layer exists, replacing a JAR on the filesystem with a newer version **does not update running modules**.

When upgrading a plugin:

1. Select the new versioned artifact per policy; verify integrity and compatibility.
2. Create a new finder/configuration/layer according to the class loader design.
3. Load and verify the new provider.
4. Publish the new registry snapshot so subsequent requests use the new version.
5. Drain old requests, close resources, and drop references to the old loader/layer.
6. Monitor class unloading/Metaspace without assuming GC will reclaim immediately.

For rollback, “reverting to the previous version” may require re-instantiating from the stored artifact, because the old loader/layer may already be closed or object state cannot be reused.

Do not confuse version pinning with class loading isolation: pinning an artifact to the right version is not enough if two plugins rely on incompatible dependencies and are forced into a shared loader.

## 12. Example host/plugin policy

A simple yet explicit policy:

\`\`\`text
Host:
  apiModule: com.example.plugin.api
  apiVersion: 2.4.1
  supportedApiRange: >=2.2.0 <3.0.0
  javaRuntime: 17
  allowPrereleasePlugins: false

Plugin:
  id: csv-exporter
  pluginVersion: 1.7.0
  requiredApiRange: >=2.3.0 <3.0.0
  minJava: 17
  requiredCapabilities: [export.csv.v2]
\`\`\`

This is a conceptual configuration, not standard \`module-info.java\` or \`ModuleDescriptor\` syntax. The host must verify both conditions: the active API lies within the plugin's required range, and host policy allows this plugin/capability. Correctness still depends on actual capabilities and contract test results.

An illustrative decision table:

| Plugin requires | Active host API | Policy outcome |
|---|---|---|
| \`>=2.3,<3.0\` | \`2.4.1\` | Acceptable if contract/capabilities pass |
| \`>=3.0,<4.0\` | \`2.4.1\` | Rejected because outside range |
| \`>=2.0,<2.4\` | \`2.4.1\` | Rejected per plugin's declared range |
| Undeclared | \`2.4.1\` | Rejected or requires migration per policy |

Do not silently “widen” a range declared by a plugin or ignore a missing version without logging a reason. When automated checks run, log every decision with \`pluginId\`, version, API requirement, selected API, and policy revision.

## 13. Common mistakes

- Reading \`ModuleDescriptor.version()\` and assuming JPMS enforces version ranges automatically.
- Putting a version directly inside \`requires\` in \`module-info.java\` like Maven syntax.
- Assuming a JAR filename reliably identifies its module version.
- Using \`ModuleDescriptor.Version\` as a full SemVer policy replacement without checking differences.
- Treating a “higher” version number as always compatible with old plugins.
- Checking only source compatibility while ignoring binary/behavioral compatibility.
- Failing to define how unversioned builds or prereleases are handled.
- Leaving duplicate module names with different versions and expecting JPMS to auto-select the newest.
- Conflating plugin version, API version, JDK version, and dependency versions.
- Failing to verify artifacts, capabilities, and service contracts before activation.

## 14. Practical checklist

Before admitting a module/plugin into runtime:

1. Did you properly read \`ModuleDescriptor.name()\` and \`version()\`, and handle missing versions?
2. Did you separate module version from plugin/API/runtime requirements?
3. Did you define a range parser/policy, prerelease handling, and compatibility rules?
4. Did you check that the active API lies within the range the plugin supports?
5. Did you check the Java version, dependency graph, and required capabilities?
6. Did you compare binary compatibility/contracts and test critical behavior?
7. Did you eliminate duplicate module names and dependency conflicts?
8. Did you verify provenance/integrity before loading code?
9. Do you have policies for rollback, hot reload, draining, and cleanup?
10. Did you log accept/reject decisions with clear reasons?

**Takeaway:** **JPMS module version answers “which version does this module declare for itself?”**, not “will this plugin run safely and compatibly with the current host?”. The second question requires **explicit versioning, dependency, capability, and contract policies** actively designed by the application.
