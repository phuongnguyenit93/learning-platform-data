# Finding Modules in a Plugin Directory with ModuleFinder

## 1. What Problem Does ModuleFinder Solve?

In a Java application that supports plugins, the host may receive additional JARs containing **Java Platform Module System (JPMS)** modules. Before deciding to create a \`ModuleLayer\` and activate a plugin, the host needs to know which modules exist in the plugin directory, their names, their versions, and which dependencies/services they declare.

The Java 9+ \`java.lang.module.ModuleFinder\` API serves the **observable module discovery** step. With \`ModuleFinder.of(Path... entries)\`, the application creates a finder from paths to JARs, exploded modules, or directories containing modules.

Example:

\`\`\`java
Path pluginDir = Path.of("plugins");
ModuleFinder finder = ModuleFinder.of(pluginDir);
\`\`\`

Then \`finder.findAll()\` returns the set of discovered \`ModuleReference\` instances; each reference contains a \`ModuleDescriptor\` and the module location when determinable.

**Important boundary:** \`ModuleFinder\` is only for *discovery*. It does not automatically execute plugin classes, does not build a \`ModuleLayer\`, does not instantiate service providers, and does not create a resolved module graph on its own. Checking dependencies and creating a layer require additional steps with \`Configuration.resolve(...)\` and \`ModuleLayer.defineModulesWithOneLoader(...)\` or an equivalent mechanism.

## 2. What Types of Modules Can ModuleFinder Find?

Types to distinguish:

| Type | Example | Identification/Meaning |
|---|---|---|
| Explicit module | JAR with \`module-info.class\` | Name, \`requires\`, \`exports\`, \`uses\`, \`provides\` declared by the descriptor |
| Exploded module | Directory containing \`module-info.class\` and classes/resources | Can be used during build/development or runtime with a suitable layout |
| Automatic module | Valid JAR without \`module-info.class\` on the module path | Java derives the module name; \`Automatic-Module-Name\` in the manifest can be used to stabilize the name |
| Not a valid module | Corrupted file or naming from which a valid name cannot be derived | Finder/descriptor may reject it with an exception |

**An automatic module is not equivalent to an explicit module.** Java derives its descriptor with special rules, so relying on automatic modules long-term can cause surprises in naming and encapsulation. If designing plugins to run via JPMS, explicit modules usually provide clearer contract/dependency declarations.

Passing \`ModuleFinder.of(pluginDir)\` with a directory containing JARs differs from passing a path to a JAR file itself; both forms are supported by the API. A finder looks for modules at the provided entries—it is not a tool that recursively scans every subdirectory according to the application's wishes. If the packaging convention uses multiple directory levels, the host must build the list of valid paths itself before creating the finder.

## 3. JPMS Plugin Discovery Workflow

An easily verifiable workflow:

\`\`\`text
plugins/ directory
      |
      v
Verify path, permissions, size, artifact source
      |
      v
ModuleFinder.of(pluginDir)
      |
      v
finder.findAll() -> ModuleReference
      |
      v
Read ModuleDescriptor: name, version, requires, uses, provides
      |
      v
Select roots + check allowlist / policy
      |
      v
Configuration.resolve(...) -> dependency graph
      |
      v
ModuleLayer + class loader + ServiceLoader
      |
      v
Initialize / health check / activate plugin
\`\`\`

Do not treat \`findAll()\` as the list of plugins authorized to run: a module may simply be a dependency library, declare no service provider, or fail to satisfy the plugin contract. On the other hand, a module containing a provider may depend on other modules and must be resolved before use.

A \`ModuleReference\` is useful for preflight checks, but its metadata may be self-declared by the publisher. To allow third-party code to run, the host must also verify artifact provenance, integrity/signatures, and trust policies. Class loaders and JPMS exports do not create a security sandbox for untrusted code.

## 4. Java 17+ Example: Listing Modules in the plugins Directory

Create the file **\`ModuleFinderDemo.java\`**:

\`\`\`java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

public class ModuleFinderDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java ModuleFinderDemo <plugin-directory>");
            System.exit(2);
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isDirectory(dir)) {
            System.err.println("Not a directory: " + dir);
            System.exit(2);
        }

        ModuleFinder finder = ModuleFinder.of(dir);
        finder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ModuleFinderDemo::printModule);
    }

    private static void printModule(ModuleReference reference) {
        ModuleDescriptor d = reference.descriptor();
        System.out.println("name=" + d.name());
        System.out.println("version=" +
                d.version().map(Object::toString).orElse("<none>"));
        System.out.println("automatic=" + d.isAutomatic());
        System.out.println("location=" +
                reference.location().map(Object::toString).orElse("<unknown>"));
        System.out.println("requires=" +
                d.requires().stream()
                        .map(ModuleDescriptor.Requires::name)
                        .sorted()
                        .toList());
        System.out.println("provides=" +
                d.provides().stream()
                        .map(ModuleDescriptor.Provides::service)
                        .sorted()
                        .toList());
    }
}
\`\`\`

The program sorts module names and dependency lists to make the output easier to read. It uses standard Java 17 APIs and does not yet load plugin classes or instantiate providers. \`ModuleFinder.of\` or \`findAll\` may throw \`FindException\` when encountering an invalid or conflicting module; a production application should catch it, log accurately, and reject the inspected package.

### Creating a Sample Explicit Module

Create the structure:

\`\`\`text
src/
└── demo.greeting/
    ├── module-info.java
    └── demo/
        └── greeting/
            └── Greeting.java
\`\`\`

Contents of **\`src/demo.greeting/module-info.java\`**:

\`\`\`java
module demo.greeting {
    exports demo.greeting;
}
\`\`\`

Contents of **\`src/demo.greeting/demo/greeting/Greeting.java\`**:

\`\`\`java
package demo.greeting;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Hello from plugin module";
    }
}
\`\`\`

From the project directory, create \`plugins\` and run:

\`\`\`bash
mkdir plugins
javac -d mods/demo.greeting src/demo.greeting/module-info.java src/demo.greeting/demo/greeting/Greeting.java
jar --create --file plugins/demo.greeting.jar --module-version 1.0.0 -C mods/demo.greeting .
javac ModuleFinderDemo.java
java ModuleFinderDemo plugins
\`\`\`

With **only one sample JAR** in the directory, the output looks like:

\`\`\`text
name=demo.greeting
version=1.0.0
automatic=false
location=file:///.../plugins/demo.greeting.jar
requires=[java.base]
provides=[]
\`\`\`

The \`location\` line depends on the actual path on the machine and may display differently depending on the OS. The remaining lines reflect the descriptor of the sample module. In the \`demo.greeting\` module, \`java.base\` is an implicit JPMS dependency.

The \`javac\` command above works when run from the directory containing \`src\`; creating output directories will be handled by the compiler/JAR tool when filesystem conditions permit. With PowerShell or an environment that does not support \`mkdir\` as shown above, create the directory using the corresponding command.

### Automatic Module

If you place a valid Java JAR without \`module-info.class\` into the same \`plugins\` directory, the finder can create an automatic module from it. The module name is determined from \`Automatic-Module-Name\` or derived from the JAR filename according to JPMS rules. Do not pick an arbitrary filename and assume it is the standard module name.

For example, a manifest containing:

\`\`\`text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacyplugin

\`\`\`

Then the derived module has the name \`com.example.legacyplugin\` (if the JAR satisfies identification requirements). Using a fixed name avoids having a JAR rename or adding a version to the filename change the module name and break \`requires\`.

## 5. Reading and Evaluating ModuleDescriptor

\`ModuleDescriptor\` describes JPMS characteristics:

- \`name()\`: module name, which serves as the key for selecting roots for the resolver.
- \`version()\`: optional module version; does not automatically create an upgrade policy or guarantee compatibility.
- \`requires()\`: module dependencies and modifiers such as \`TRANSITIVE\`, \`STATIC\`.
- \`exports()\`: packages exposed to other modules according to JPMS rules.
- \`opens()\`: packages opened for reflective access (when present).
- \`uses()\`: names of services that the module consumes.
- \`provides()\`: services and provider classes supplied by the module.
- \`isAutomatic()\` and \`isOpen()\`: information about the descriptor type.

Example of a provider plugin declaration:

\`\`\`java
module demo.csvplugin {
    requires com.example.plugin.api;
    provides com.example.plugin.api.Exporter
        with demo.csv.CsvExporter;
}
\`\`\`

This is an **illustrative module descriptor** that only compiles when the referenced modules, interfaces, and classes exist. The finder can detect \`provides\` metadata without having to instantiate \`CsvExporter\`. After the resolution and layer-creation steps, \`ServiceLoader.load(layer, Exporter.class)\` can be used to discover service providers in the layer according to the contract.

**Do not equate \`exports\` and \`provides\`:** \`exports\` controls whether other modules can access public types in a package; \`provides\` advertises a service implementation. The package containing the implementation might not need to be exported externally to be used through the service mechanism.

## 6. From ModuleFinder to Dependency Resolution

A list of discovered modules does not necessarily form a valid configuration. Java uses \`Configuration\` and the resolver to build the graph.

Integration example:

\`\`\`java
// Integration snippet; module names, pluginFinder, and parentLayer
// are determined beforehand by the application.
Configuration configuration =
        parentLayer.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("demo.greeting")
        );
\`\`\`

\`resolve\` finds root modules and their dependencies through the finders and parent configuration according to JPMS rules. The result can fail if a required module is missing, there is a conflict, or the graph violates constraints. \`ModuleFinder.of()\` with no arguments creates an empty finder; how before/after finders are used must be based on the host's policy.

After resolving, the application can define a layer:

\`\`\`java
// Integration snippet; configuration and parentLayer are already available.
ModuleLayer layer = parentLayer.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
);
\`\`\`

**Be careful with class loaders:** the call above creates a suitable loader for modules in the layer according to JPMS mechanisms, using the specified parent loader. Do not assume that a module layer equates to a sandbox or that each plugin gets its own class loader. If dependency isolation or plugin version switching is needed, the layer, loader, shared API, and compatible lifecycle must be designed from the start.

A minimal pattern for a multi-plugin workflow:

1. Select roots from the list of modules permitted to be activated.
2. Verify that the plugin module \`requires\` the proper shared API.
3. Resolve against the parent layer and selected finder, handling errors with clear reasons.
4. Create the layer/loader and then discover providers via the service API.
5. Evaluate provider compatibility and instantiate them with a controlled lifecycle.

Do not make every discovered module a root if the directory contains non-plugin dependencies as well. Roots should come from metadata/allowlists or service contracts defined by the host.

## 7. Notes When a Directory Has Multiple JARs and Duplicate Module Names

A plugin directory may contain two releases with the same module name, such as \`demo.greeting-1.0.jar\` and \`demo.greeting-2.0.jar\`. Do not assume \`ModuleFinder\` will choose the “latest version” according to application policy. The finder needs a unique module name mapping to resolve; duplicate or ambiguous modules can cause a \`FindException\` or discovery behavior that does not meet expectations.

The host should build a staging pipeline:

- Inspect artifacts and module names before admitting them to the permitted set.
- Select one valid version per module name according to a clear policy.
- Place the required modules into a snapshot directory/path that is not modified concurrently.
- Create a finder from the normalized set of paths and resolve only against the selected set.
- Report an error when dependencies are missing or versions conflict, instead of picking whichever JAR happens to appear first.

\`ModuleDescriptor.version()\` is optional information. JPMS resolution **does not automatically resolve Maven/Gradle-style version ranges** and does not automatically download missing libraries from repositories. Release selection, compatibility checks, and path layout belong to the application's plugin/build/deployment management system.

## 8. New Plugin Modules Do Not Automatically Appear in a Running Layer

Suppose the host has created a \`ModuleFinder\` from \`plugins/\` and then created a \`ModuleLayer\`. When additional JARs are copied into the directory, **the already-created layer does not update automatically**. You must actively re-discover the directory state, build an appropriate finder/configuration, and create a new layer or use another custom switching mechanism.

Consistency notes:

- Do not delete/overwrite JARs while a class loader is actively using them.
- Avoid TOCTOU between checking the manifest/module descriptor and resolving/loading.
- Do not mix old and new versions within a single request if the contract does not allow it.
- Manage callbacks, threads, service instances, and class loaders to avoid retaining old modules/plugins.
- Depending on the layer model and live references, reclaiming classes/modules depends on garbage collection; there is no simple JPMS command to “unload a module immediately”.

ModuleFinder serves **snapshot discovery**; hot reload is a plugin-system-level feature with its own lifecycle requirements.

## 9. Security and Metadata Trustworthiness

Do not treat a module found in a directory as trustworthy merely because it has a valid \`module-info.class\`. Metadata can declare names, services, or dependencies controlled by the publisher, but it does not verify the publisher.

A safe workflow must combine:

- Trusted artifact sources/allowlists, strict directory write permissions, and policy-based integrity/signature checks.
- Limits on file size, entry count, and JAR parsing resources.
- Checks on module name, packages, dependencies, and expected service provisioning capabilities.
- Protection of paths/file objects against replacement between verification and use.
- Not running unapproved plugin bytecode in the same JVM if trust requirements are not met.

JPMS provides module structure, module readability, and access control at the language/runtime level. It **is not a trust sandbox** for malicious third-party code. When strong privilege isolation is required, consider separate processes/containers and a clear communication protocol.

## 10. Common Mistakes

- Calling \`ModuleFinder.of(dir)\` and assuming modules are already loaded or services are automatically activated.
- Using \`findAll()\` to treat all JARs as plugins without distinguishing dependency modules.
- Treating automatic modules and explicit modules as having the same level of contract declaration.
- Relying on the iteration order of \`Set<ModuleReference>\` to choose plugins/versions.
- Forgetting that the module path does not recursively scan every subdirectory branch.
- Assuming a module descriptor version automatically resolves compatibility ranges.
- Packaging duplicate modules or allowing the plugin directory to change during resolution.
- Failing to check \`provides\` services, API dependencies, or trust metadata before activation.
- Assuming updating files in the directory will update an already-created \`ModuleLayer\`.
- Assuming a separate module layer completely prevents untrusted code from affecting the host.

## 11. Practical Checklist

Before using modules discovered from a plugin directory:

1. **Identify paths:** Does the directory exist and contain modules/JARs in the expected layout?
2. **Discovery:** Do \`ModuleFinder.of(...)\` and \`findAll()\` succeed?
3. **Read descriptors:** Are the name, version, \`requires\`, \`uses\`, and \`provides\` contracts clear?
4. **Select roots:** Which modules are actual plugins, and which are merely dependencies?
5. **Check conflicts:** Duplicate names/versions, missing APIs/modules, automatic modules with unstable names?
6. **Check trust:** Artifact provenance, integrity, access permissions, possibility of file replacement?
7. **Resolve:** Is the configuration created without errors and using the right parent layer/finder?
8. **Define layer:** Are shared loaders/APIs properly arranged to avoid class identity conflicts?
9. **Activate:** Are providers created only after validation, with lifecycle management, logging, and rollback?
10. **Update:** If hot reload is supported, are snapshots, draining, and old service cleanup handled?

**Remember:** \`ModuleFinder\` answers the question **“which modules exist at these paths?”**. \`Configuration.resolve\` answers **“do they form a valid dependency graph?”**. \`ModuleLayer\` and \`ServiceLoader\` are what help the host bring providers into execution according to the chosen architecture.
