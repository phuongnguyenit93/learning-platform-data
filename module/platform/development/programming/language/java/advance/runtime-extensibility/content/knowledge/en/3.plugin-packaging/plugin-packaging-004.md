# Reading Manifests, Versions, and Plugin Descriptors Before Activation

## 1. Why Must Metadata Be Read Before Running a Plugin?

In a runtime-extensible architecture, a **plugin** is typically packaged as a JAR or a distribution directory containing JARs and resources. Before invoking any plugin code, the host needs to know what the package is, which API version it uses, whether it is compatible with the host, where the initialization component resides, and whether the publisher is trusted. A **pre-activation validation** step enables the host to reject invalid packages before creating a dedicated class loader, instantiating the plugin, registering services, or dispatching requests to it.

There are three easily confused concepts:

- **JAR manifest**: the standard \`META-INF/MANIFEST.MF\` file inside a JAR archive, containing attributes such as \`Manifest-Version\`, \`Main-Class\`, or custom attributes like \`Plugin-Id\` and \`Plugin-Version\`. Java provides \`java.util.jar.Manifest\` and \`JarFile.getManifest()\` to read it.
- **Plugin descriptor**: descriptive metadata following a plugin system's convention, such as \`plugin.properties\`, JSON, or YAML inside the JAR. A host may use the manifest, a separate descriptor, or a combination of both.
- **Trusted metadata**: information whose syntax, policy, compatibility, and provenance have been verified. Merely reading a value from a manifest **does not prove that value is accurate or safe**.

For example, a JAR may declare \`Plugin-Id: report-csv\`, \`Plugin-Version: 1.4.0\`, \`Plugin-Api-Version: 2\`, \`Plugin-Class: com.example.CsvPlugin\`. These are claims from the supplier; the host must verify them against its policies before activation.

## 2. Example Plugin Package Structure

A valid JAR file may have this structure:

\`\`\`text
report-csv-plugin.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/plugins/
    └── CsvPlugin.class
\`\`\`

Illustrative manifest content:

\`\`\`text
Manifest-Version: 1.0
Plugin-Id: report-csv
Plugin-Version: 1.4.0
Plugin-Api-Version: 2
Plugin-Class: com.example.plugins.CsvPlugin
Plugin-Description: Exports reports as CSV
\`\`\`

The \`Plugin-*\` fields **are not mandatory attributes of the JAR specification**. They are a custom contract between the host and plugin developers. The JAR specification does not automatically verify that the class in \`Plugin-Class\` exists, implements the proper interface, or can run safely.

Metadata design choices must clearly answer:

| Field | Purpose | Example Validation Rule |
|---|---|---|
| \`Plugin-Id\` | Stable identifier for registration | Required, unique, lowercase letters/digits/hyphens |
| \`Plugin-Version\` | Version of the plugin itself | Required, follows the published versioning convention |
| \`Plugin-Api-Version\` | Host contract version required by the plugin | Must belong to the set of versions supported by the host |
| \`Plugin-Class\` | Expected entry point | Non-blank; loaded only after passing initial checks |
| \`Plugin-Description\` | Display and operational support | Optional; length-limited and output-sanitized |
| \`Plugin-Requires\` | Dependencies on other plugins (if any) | Parse, check dependency versions, and detect dependency cycles |

With a Java manifest, attribute names must follow manifest formatting rules and line lengths are limited by byte count. Build/JAR tools normally handle line wrapping and continuations. You should not arbitrarily concatenate raw manifest strings for long values. Richly structured descriptions, complex dependencies, or multilingual text are usually better suited to a JSON/YAML descriptor with a well-defined schema and size limits.

## 3. Distinguishing Plugin Version, API Version, and Java Version

Three kinds of versions serve different purposes:

1. **Plugin version**, e.g., \`1.4.0\`, is used to manage releases, updates, and rollbacks. Compatibility with the host cannot be inferred from this number alone.
2. **Plugin API version**, e.g., \`2\`, expresses the contract that the host and plugin use to communicate. The host needs an explicit compatibility policy, such as supporting only API \`2\`.
3. **Java/runtime version**, e.g., classes compiled for Java 21 while the host runs on Java 17, which can cause \`UnsupportedClassVersionError\` when the JVM defines the class. JVM support must be checked via trusted metadata or by inspecting bytecode before the loading step.

**Semantic Versioning** (\`MAJOR.MINOR.PATCH\`) is a helpful convention, but Java has no built-in SemVer comparator in \`java.util.jar\`. If the host uses SemVer, clearly define policies for prereleases, build metadata, and ranges; use a battle-tested library or a complete parser. Do not compare versions lexicographically as strings: \`"2.10.0"\` cannot be compared properly against \`"2.9.0"\` using \`String.compareTo\`.

To avoid confusion, the runnable example below uses an integer \`Plugin-Api-Version\` and checks for an exact single API version. This is an illustrative policy; production systems may support multiple versions or a compatibility range.

## 4. Pre-Activation Validation Workflow

A controlled pipeline should proceed in order:

\`\`\`text
Untrusted JAR
    |
    v
Check source, permissions, and file size
    |
    v
Open JAR, read manifest/descriptor (without loading entry-point class)
    |
    v
Parse + validate required fields, formats, limits
    |
    v
Check duplicate ID, version, API, JVM, dependencies, trust policy
    |
    +-- Failed --> REJECT + log cause
    |
    v
Prepare class loader and plugin environment
    |
    v
Validate entry point, instantiate, health check, register
    |
    v
ACTIVATE to accept work
\`\`\`

Do not treat \`new JarFile(...)\` or \`getManifest()\` as executing the entry point. They serve to read archive/metadata. Nevertheless, the data inside remains untrusted input and may contain resource-exhausting archives; enforce limits on file size, entry count, processing cost, and read resources. Avoid extracting arbitrary contents onto the filesystem unnecessarily.

The following conditions should be checked prior to class loading:

- The file originates from an allowed location; the path is normalized, preventing file replacement between validation and activation.
- The manifest exists, is readable, and every required field matches its data type and size limits.
- The plugin ID is not already claimed by another plugin; upgrade/version-change rules are explicit.
- The required API version and Java version are compatible with the host.
- Required dependencies are available, free of dependency cycles, and conflict-free.
- The artifact passes integrity and publisher/signature verification according to system policy.
- Declared permissions or capabilities do not exceed what the host allows.

**Note:** metadata validation is only the first layer. Class loading can encounter \`ClassNotFoundException\`, \`NoClassDefFoundError\`, or \`LinkageError\`; constructors or static initializers can execute code and cause side effects. Deciding whether to permit plugin execution must rely on an appropriate security policy and isolation model.

## 5. Java 17+ Example: Reading and Validating a Manifest Without Activating the Plugin

The following program reads a JAR specified on the command line, validates four required fields, and prints normalized metadata. It does not call \`Class.forName\`, does not instantiate the plugin, and does not add the JAR to the classpath.

Create **\`PluginManifestInspector.java\`**:

\`\`\`java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;
import java.util.regex.Pattern;

public final class PluginManifestInspector {
    private static final Pattern ID = Pattern.compile("[a-z][a-z0-9-]{0,63}");
    private static final Pattern VERSION =
            Pattern.compile("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)");
    private static final Pattern CLASS_NAME =
            Pattern.compile("[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)+");
    private static final int SUPPORTED_API_VERSION = 2;
    private static final long MAX_JAR_BYTES = 20L * 1024 * 1024;

    record PluginMetadata(String id, String version, int apiVersion,
                          String entryClass, String description) {}

    private static String required(Attributes attrs, String name) {
        String value = attrs.getValue(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value.trim();
    }

    private static PluginMetadata inspect(Path path) throws IOException {
        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException("Not a regular file");
        }
        long size = Files.size(path);
        if (size > MAX_JAR_BYTES) {
            throw new IllegalArgumentException("JAR exceeds size limit");
        }

        try (JarFile jar = new JarFile(path.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalArgumentException("Missing manifest");
            }
            Attributes a = manifest.getMainAttributes();

            String id = required(a, "Plugin-Id");
            if (!ID.matcher(id).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Id");
            }

            String version = required(a, "Plugin-Version");
            if (!VERSION.matcher(version).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Version");
            }

            String apiText = required(a, "Plugin-Api-Version");
            int api;
            try {
                api = Integer.parseInt(apiText);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid Plugin-Api-Version", e);
            }
            if (api != SUPPORTED_API_VERSION) {
                throw new IllegalArgumentException("Unsupported plugin API: " + api);
            }

            String entry = required(a, "Plugin-Class");
            if (!CLASS_NAME.matcher(entry).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Class");
            }

            String description = a.getValue("Plugin-Description");
            if (description == null) description = "";
            if (description.length() > 500) {
                throw new IllegalArgumentException("Description too long");
            }

            return new PluginMetadata(id, version, api, entry, description);
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java PluginManifestInspector <plugin.jar>");
            System.exit(2);
        }
        try {
            PluginMetadata m = inspect(Path.of(args[0]));
            System.out.println("VALID: " + m.id() + "@" + m.version());
            System.out.println("API: " + m.apiVersion());
            System.out.println("Entry: " + m.entryClass());
            System.out.println("Description: " + m.description());
        } catch (IllegalArgumentException e) {
            System.err.println("REJECTED: " + e.getMessage());
            System.exit(1);
        }
    }
}
\`\`\`

To create a sample JAR without actual plugin code, first create **\`plugin.mf\`** with the following content, ending with a blank line:

\`\`\`text
Manifest-Version: 1.0
Plugin-Id: report-csv
Plugin-Version: 1.4.0
Plugin-Api-Version: 2
Plugin-Class: com.example.plugins.CsvPlugin
Plugin-Description: Exports reports as CSV

\`\`\`

Run in an environment with JDK 17+:

\`\`\`bash
javac PluginManifestInspector.java
jar --create --file sample-plugin.jar --manifest plugin.mf
java PluginManifestInspector sample-plugin.jar
\`\`\`

Expected output:

\`\`\`text
VALID: report-csv@1.4.0
API: 2
Entry: com.example.plugins.CsvPlugin
Description: Exports reports as CSV
\`\`\`

The sample JAR is only for testing metadata: **it does not contain \`CsvPlugin.class\`**, so it will fail if the host proceeds to actually load that class. This is intentional to illustrate that **metadata validation** and **entry-point validation** are two distinct gates.

Changing \`Plugin-Api-Version: 2\` to \`Plugin-Api-Version: 3\`, recreating the JAR, and running again returns an error:

\`\`\`text
REJECTED: Unsupported plugin API: 3
\`\`\`

This message is written to stderr and the process exits with code 1. The program catches only \`IllegalArgumentException\` validation errors; I/O errors or unreadable archives follow a separate error path. In a real system, convert all errors into classified validation results rather than letting a plugin-handling request crash the application.

### Intentional Limitations of the Example

The version regex only accepts \`MAJOR.MINOR.PATCH\` without prerelease/build metadata; it is a subset of SemVer, not a full SemVer parser. The class name regex performs a preliminary check on common binary-name syntax, without guaranteeing the class exists or implements the right interface. The example also does not check signatures, dependencies, modules, min-Java-version, registry state, JAR entry count, file-modification races, or runtime configuration. Therefore, the program is an **initial metadata filter**, not a production plugin manager.

## 6. Standard Manifest vs. Custom Descriptor: Which Should You Choose?

**Use the JAR manifest** when metadata is small, key-value based, and directly tied to the JAR bundle. Advantage: \`JarFile.getManifest()\` is built in, requiring no external parser; well suited for plugin ID, version, entry-point class name, and a few simple flags.

**Use a custom descriptor** when metadata includes dependency lists, version ranges, capabilities, configuration, permission constraints, multiple entry points, or structured descriptions. For JSON/YAML, define a schema, schema version, size limits, duplicate-key policy, required/optional fields, encoding, and handling of unrecognized values. Never load a config parser from an untrusted plugin itself to read its descriptor.

**Use both** when the manifest holds minimal bootstrap keys and points to a structured descriptor. In that case, define which source is authoritative if the two declare conflicting values. For example: take \`Plugin-Id\` and \`Plugin-Version\` solely from the manifest; let the descriptor supply only dependencies/configuration. Do not allow the two sources to arbitrarily override each other.

## 7. Verifying Publisher, Integrity, and TOCTOU Risks

A manifest that self-declares an ID, version, or publisher name **does not establish a trusted identity**. Different assurance levels exist:

- **Checksum/SHA-256** verifies whether the artifact's bytes match an accepted checksum; a checksum obtained from the same untrusted source does not authenticate the publisher.
- **Digital signature** verifies whether the artifact was signed by a trusted key and whether the signed content remains intact, provided the verification process covers the entire relevant payload and trust/key rotation policies are sound.
- **JAR signing** has rules for signed entries and verification when entry contents are read. Merely opening the manifest with \`JarFile\` does not mean the entire JAR signature has been verified; an appropriate signature-verification step and a policy checking all critical entries are required.
- **Allowlists** by publisher, artifact source, and capabilities control which plugins are permitted to run even when their descriptive metadata is valid.

**Time-of-check to time-of-use (TOCTOU)** risk arises when the host checks a file at path A, but before loading, file A is replaced. One mitigation is to copy the artifact into a read-only/tamper-protected staging area, compute hashes and verify against that exact copy, and then have the class loader load solely from the approved copy. Apply this consistently to accompanying dependencies as well.

## 8. Activating After Passing Validation

Only after metadata passes all checks should the host prepare steps capable of executing code:

1. Finalize compatibility policy and registry state by ID/version.
2. Configure the class loader or \`ModuleLayer\` according to the isolation and dependency model.
3. Load/validate the entry point against the contract, e.g., a \`Plugin\` interface; catch and classify class-loading or linkage errors.
4. Instantiate in an allowed environment, supply configuration/capabilities, and invoke \`initialize\` lifecycle/health checks.
5. Only after initialization succeeds, publish the plugin in the registry for new requests.
6. On failure, roll back temporary registration and close opened resources; persist the validation result for operational tracing.

For untrusted plugins, running in the same JVM poses major risks: a separate class loader **is not a secure sandbox**. You may need to isolate the plugin in a separate process/container with restricted permissions and an explicit communication protocol.

If the host supports hot updates, add transition rules between old and new plugins: in-flight requests, version pinning, draining, shutdown, and rollback. Manifest validation does not replace this lifecycle management.

## 9. Common Mistakes and Validation Checklist

Common mistakes:

- Checking only that the manifest exists and immediately calling \`Class.forName\` on the \`Plugin-Class\` value.
- Trusting \`Plugin-Version\` without checking the API version and runtime compatibility.
- Using \`String.compareTo\` for SemVer.
- Assuming \`Plugin-Class\` is a standard Java/JAR field, or that the class truly exists because the manifest declares it.
- Equating a checksum with a publisher signature, or assuming \`JarFile.getManifest()\` validates signatures across the whole archive.
- Allowing the JAR file to be replaced in the gap between validation and loading.
- Failing to bound input sizes or block duplicate IDs/versions.
- Writing raw \`Plugin-Description\` from external sources into HTML or logs without handling output context or control characters.
- Instantiating the plugin to "read metadata," giving unapproved code a chance to execute.

Checklist before **activation**: read the exact artifact; metadata parses cleanly; required fields and schema are valid; API/JVM/dependencies are compatible; ID/version do not conflict; source and integrity satisfy policy; entry point/lifecycle can be checked in the appropriate environment; registry publishes only after successful initialization; rejection logging and rollback capability are in place.

**Conclusion:** manifests and descriptors allow the host to make decisions **before running a plugin**. The core principle is cleanly separating three stages: **read metadata → validate/authorize → load and activate**, while verifying provenance and enforcing lifecycle controls according to real operational requirements.
