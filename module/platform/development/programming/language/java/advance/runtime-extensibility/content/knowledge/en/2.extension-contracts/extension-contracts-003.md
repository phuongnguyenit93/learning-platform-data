# Designing Identity, Capabilities, and Version Information for Extension Contracts in Java

## 1. Why Does an Extension Contract Need These Three Groups of Information?

A Java application can be extended through plugins, `ServiceLoader` providers, adapters, or third-party implementations. Knowing only the implementation class name is not enough for the host to decide whether to accept an extension. The host needs to answer three independent questions:

1. **Identity:** Which extension is this, which extension point does it belong to, and does it collide with an already-registered extension?
2. **Capabilities:** Which tasks or contract variants does the extension genuinely promise to support?
3. **Version information:** Which interface version was the extension built for, which runtime environment does it require, and which release is the implementation itself at?

For example, consider a search system that allows attaching multiple providers. Two providers may both display the name "Search" and implement the `SearchProvider` interface, yet have different IDs; one provider supports only text search, while the other also supports prefix search. Both may also have different product versions while being compatible with the same host API.

| Axis | Example | Used to decide | Should not be used as a substitute |
| --- | --- | --- | --- |
| Identity | `vn.demo.search.basic` | Distinguishing, registering, referencing, detecting duplicates | Display name, class name, or JAR path |
| Capabilities | `search.text`, `search.prefix` | Selecting a suitable provider for a specific request | Higher/lower version or guessing from the name |
| API version | `2.1` | Checking the communication contract with the host | Plugin release version |
| Implementation version | `1.4.2` | Tracking releases, incidents, upgrades | Proof that the plugin is compatible |
| Metadata/environment version | `schemaVersion=1`, `minJavaFeature=17` | Parsing the descriptor and checking runtime prerequisites | Extension point API version |

These three axes **must be modeled separately**. A plugin released as version `1.5.0` does not automatically support API `1.5`; a plugin advertising `search.vector` does not automatically have data-access permissions or runtime readiness at invocation time.

## 2. Designing Stable Identity

### 2.1. Distinguishing ID Types

- **Extension point ID:** identifies the contract exposed by the host, e.g. `vn.demo.search.provider`. It answers "what is being extended?".
- **Extension/provider ID:** stable identifier of an implementation, e.g. `vn.demo.search.basic`. It answers "who provides this implementation?".
- **Instance ID:** identifier of a specific provider configuration or activation, e.g. `tenant-a/search-primary`. Multiple instances can share one provider ID with different configurations.
- **Display name:** human-readable name, e.g. "Basic Search". This name can be localized or changed for clarity and should not be used as a technical key.

An operationally friendly policy is to use lowercase namespaced string IDs, such as `vn.demo.search.basic`, `vn.demo.search.lucene`. Reverse-domain or organization namespaces reduce collisions; this is a **system-defined convention**, not an ID format enforced by Java itself. Publish clear rules for valid characters, normalization, comparison, and uniqueness scope (host-wide or per extension point).

Key properties:

1. **Stable across releases:** refactoring code, changing packages, or bumping `implementationVersion` does not change the provider ID. If an ID changes, a mapping/migration mechanism is needed for stored configurations, caches, and data.
2. **Unique per registry policy:** the same registration key must not silently overwrite another. Duplicate IDs must fail with a clear error including plugin source details.
3. **Independent of display name or class name:** refactoring Java packages or renaming UI labels does not break references.
4. **Do not embed version in the stable ID:** `vn.demo.search.basic.v2` often creates an unintended separate entity. Use a different ID only when it is genuinely a different provider.
5. **Namespace ownership:** a self-declared `vn.example.*` name does not prove a trustworthy publisher. Verifying publisher/signatures or ID allocation policy is separate from syntax validation.

If the system must run two implementation versions of the same provider simultaneously, explicitly define the registry key—such as `(providerId, instanceId)` or `(providerId, deploymentSlot)`. Do not arbitrarily fold the version into `providerId` and break saved references.

### 2.2. Boundary Between ID and Java Implementation Name

`ServiceLoader` identifies a service by its interface/abstract class type and discovers providers declared via `META-INF/services` or the module descriptor `provides ... with ...`. It **does not automatically provide** a business ID, capability set, or per-provider version. If the host needs those three pieces of information, it must define its own descriptor/contract and validate them.

Nor should you infer IDs from class names, `Class.getName()`, JPMS module names, or JAR filenames: those names serve build/deployment and can change independently of extension identity.

## 3. Modeling Capabilities

An interface often describes the general operation level, while implementations may support different optional features. Define **capability keys** with stable, documented semantics, for example:

- `search.text`: search text by query according to the published contract.
- `search.prefix`: prefix search, with explicit matching and normalization rules.
- `search.vector`: vector search, with vector dimensions and distance metrics defined by a supplementary contract.

Do not use vague labels like `advanced` or `fast` to decide compatibility; "fast" is a measurement-dependent performance attribute, not a guaranteed operation.

### 3.1. Sets to Distinguish

- **Provided capabilities:** capabilities the plugin *provides*, e.g. `{search.text, search.prefix}`.
- **Required plugin capabilities:** capabilities the host/task *requires the provider to have*, e.g. `{search.text}`.
- **Required host capabilities:** host services the plugin *needs* (if the architecture has this dependency direction), e.g. `{host.events.v1}`.
- **Enabled/available capabilities:** capabilities currently enabled and usable after accounting for configuration, licensing, resources, backend, and connection state. This may be a subset of provided capabilities.

Simple set-check definition:

```text
requiredPluginCapabilities ⊆ provider.providedCapabilities
provider.requiredHostCapabilities ⊆ host.providedCapabilities
```

After passing static compatibility checks, if a capability can become temporarily unavailable due to runtime conditions, the host still needs to check **availability status** before invoking it. An advertised capability does not mean "the service is always healthy".

### 3.2. Designing Contracts for Optional Capabilities

- Use namespaced names with the same format across documentation, descriptors, and source code. Each key's documentation must state inputs, outputs, behavior when unsupported, data constraints, and side effects.
- Clearly state **required capabilities** to implement the extension point versus **optional capabilities**. If `search.text` is required, a provider advertising only `search.vector` is invalid for tasks requiring text search.
- When adding capabilities, preserve backward compatibility if promised by the contract. If semantics change significantly, introduce a new key/contract or bump the major API version per policy rather than silently altering the behavior of an existing key.
- Do not silently "emulate" a missing capability: return a structured `UNSUPPORTED_CAPABILITY` error, or choose another provider according to a pre-declared, agreed-upon fallback.
- A capability **is not an access permission**. A plugin claiming it supports file writing does not mean the host must grant file write permissions; authorization/sandboxing remains controlled by the host.

The registry should check static capabilities when admitting a plugin, and call sites should request concrete capabilities rather than selecting by name string or version number.

## 4. Separating Version Types

Keep at least the following concepts in distinct fields:

| Field | Meaning | Usage |
| --- | --- | --- |
| `implementationVersion` | Release version of the plugin/adapter, e.g. `1.4.2` | Deployment tracking, logs, issue triage, rollout |
| `apiVersion` or `apiRange` | API/SPI contract version the plugin was compiled and tested against | Matching against contracts supported by the host |
| `schemaVersion` | Descriptor/manifest structure version | Selecting the appropriate metadata parser/validator |
| `minJavaFeature` | Minimum Java feature release, e.g. `17` | Rejecting artifacts early that cannot run on the current runtime |
| `minHostVersion` / host version range (if needed) | Dependency condition on the host product | Checking differences outside the API/SPI |

**Do not compare versions as lexicographical strings:** `"2.10"` is greater than `"2.9"` numerically, whereas standard string comparison can give the opposite result. Parse numeric components or use an appropriate SemVer library. If using Semantic Versioning, explicitly define major/minor/patch, pre-release, build metadata, and compatibility ranges; do not force those rules onto fields that do not follow SemVer.

An illustrative policy for `apiVersion=MAJOR.MINOR`:

- Major must be in the list of majors the host declares it supports. For example, if the host only supports API major 2, a provider requiring API major 3 is rejected.
- Within the **same major**, if the host supports up to minor 2.2, a plugin requiring 2.1 can be accepted while a plugin requiring 2.3 is rejected, **only if** the contract guarantees newer minors do not break old behavior and the host implements all features of earlier minors.
- Patch or implementation versions must not be used in place of compatibility testing. A plugin with `implementationVersion=7.0.0` can still target API 2.1.

In Java, changing a method signature, removing a method, changing types, altering checked exceptions, or adding an abstract method to an interface can break compiled/deployed code even across a minor bump. Behavioral changes can also cause failures even when binary linkage remains valid. Thus, "same major means compatible" is a **commitment maintained through design and testing**, not an automatic JVM feature. For optional features, consider separate interfaces or default methods with clear semantics, while still testing older binaries.

`Package.getImplementationVersion()` can retrieve metadata from a package's manifest when packaged appropriately, and `ModuleDescriptor.version()` can hold a module's version information. Those values are **optional**, do not replace a host-defined compatibility descriptor, and do not prove a plugin is trustworthy.

## 5. Example Machine-Checkable Descriptor

A host can specify a manifest independent of Java classes as follows (this is an **application-defined illustrative schema**, not a file read automatically by `ServiceLoader`):

```json
{
  "schemaVersion": 1,
  "extensionPointId": "vn.demo.search.provider",
  "id": "vn.demo.search.basic",
  "displayName": "Basic Search",
  "implementationVersion": "1.4.2",
  "apiVersion": "2.1",
  "minJavaFeature": 17,
  "providedCapabilities": [
    "search.text",
    "search.prefix"
  ],
  "requiredHostCapabilities": []
}
```

When reading the descriptor, the host should validate required fields, ID format, field types, version values, capability names, duplicates, and valid version ranges. If metadata is invalid, report a specific error; never silently fix it or treat unknown values as "compatible". You can build the registry with states `DISCOVERED → VALIDATED → COMPATIBLE → ENABLED` to distinguish discovering a plugin, validating metadata, accepting the contract, and actually enabling it.

If the descriptor resides inside a JAR, the host should check conditions readable from metadata **before attempting to load and instantiate plugin classes**. Checking `minJavaFeature` only after loading bytecode is too late when the JAR contains classes compiled for a newer Java version, because `UnsupportedClassVersionError` may occur before the check runs. Metadata and publisher origin must be verified according to the host's trust policy.

## 6. Java 17+ Example: Registration and Compatibility Checks

The example below simulates the **descriptor + host policy checks**, not a complete JAR loader or `ServiceLoader` implementation. Chosen policy: unique IDs in the registry; API must share the same major and plugin minor must not exceed what the host supports; Java environment and required capabilities must be satisfied.

Create the file `ExtensionContractDemo.java`:

```java
import java.util.*;

public class ExtensionContractDemo {
    record ApiVersion(int major, int minor) {
        ApiVersion {
            if (major < 1 || minor < 0) {
                throw new IllegalArgumentException("Invalid API version");
            }
        }
        @Override public String toString() {
            return major + "." + minor;
        }
    }

    record ExtensionDescriptor(
            String extensionPointId,
            String id,
            String displayName,
            String implementationVersion,
            ApiVersion apiVersion,
            int minJavaFeature,
            Set<String> providedCapabilities) {
        ExtensionDescriptor {
            if (!validId(extensionPointId) || !validId(id)) {
                throw new IllegalArgumentException("Invalid extension ID");
            }
            Objects.requireNonNull(displayName);
            Objects.requireNonNull(implementationVersion);
            Objects.requireNonNull(apiVersion);
            Objects.requireNonNull(providedCapabilities);
            if (minJavaFeature < 1) {
                throw new IllegalArgumentException("Invalid Java version");
            }
            providedCapabilities = Set.copyOf(providedCapabilities);
        }
    }

    record HostPolicy(
            String extensionPointId,
            ApiVersion supportedApi,
            Set<String> requiredCapabilities) {
        HostPolicy {
            if (!validId(extensionPointId)) {
                throw new IllegalArgumentException("Invalid extension point");
            }
            Objects.requireNonNull(supportedApi);
            requiredCapabilities = Set.copyOf(requiredCapabilities);
        }
    }

    static boolean validId(String id) {
        return id != null
                && id.matches("[a-z][a-z0-9]*(\\.[a-z][a-z0-9-]*)+");
    }

    static void ensureUniqueIds(List<ExtensionDescriptor> plugins) {
        Set<String> ids = new HashSet<>();
        for (ExtensionDescriptor plugin : plugins) {
            if (!ids.add(plugin.id())) {
                throw new IllegalArgumentException(
                        "Duplicate plugin ID: " + plugin.id());
            }
        }
    }

    static String check(ExtensionDescriptor plugin, HostPolicy host) {
        if (!plugin.extensionPointId().equals(host.extensionPointId())) {
            return "SAI_EXTENSION_POINT";
        }
        if (plugin.apiVersion().major() != host.supportedApi().major()) {
            return "SAI_API_MAJOR";
        }
        if (plugin.apiVersion().minor() > host.supportedApi().minor()) {
            return "API_MINOR_QUA_MOI";
        }
        if (plugin.minJavaFeature() > Runtime.version().feature()) {
            return "JAVA_CHUA_DAP_UNG";
        }
        if (!plugin.providedCapabilities()
                .containsAll(host.requiredCapabilities())) {
            return "THIEU_CAPABILITY";
        }
        return "OK";
    }

    public static void main(String[] args) {
        HostPolicy host = new HostPolicy(
                "vn.demo.search.provider", new ApiVersion(2, 2),
                Set.of("search.text"));

        List<ExtensionDescriptor> plugins = List.of(
                new ExtensionDescriptor(
                        "vn.demo.search.provider", "vn.demo.search.basic",
                        "Basic Search", "1.4.2", new ApiVersion(2, 1), 17,
                        Set.of("search.text", "search.prefix")),
                new ExtensionDescriptor(
                        "vn.demo.search.provider", "vn.demo.search.future",
                        "Future Search", "2.0.0", new ApiVersion(2, 3), 17,
                        Set.of("search.text")),
                new ExtensionDescriptor(
                        "vn.demo.search.provider", "vn.demo.search.vector",
                        "Vector Search", "1.1.0", new ApiVersion(2, 1), 17,
                        Set.of("search.vector")));

        ensureUniqueIds(plugins);
        for (ExtensionDescriptor plugin : plugins) {
            System.out.println(plugin.id() + " => " + check(plugin, host));
        }
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac --release 17 ExtensionContractDemo.java
java ExtensionContractDemo
```

Output:

```text
vn.demo.search.basic => OK
vn.demo.search.future => API_MINOR_QUA_MOI
vn.demo.search.vector => THIEU_CAPABILITY
```

Explanation:

- `basic` has API 2.1 compatible with the API 2.2 policy, requires Java 17, and provides `search.text`, so it is accepted.
- `future` provides the required capability but needs API 2.3, higher than the host's 2.2; `implementationVersion=2.0.0` must not be used to bypass this check.
- `vector` has a matching API but does not provide `search.text`; the host must reject it for tasks requiring that capability.

`Set.copyOf` captures an immutable set copy to prevent callers from modifying the capability list after the descriptor is constructed; `ensureUniqueIds` rejects ID collisions rather than letting a later provider overwrite an earlier one. Output order is deterministic because `List.of` preserves declaration order; the code does not rely on `Set` iteration order.

The example shows only **one-way capabilities** (the host requiring capabilities from the plugin). If plugins also require services from the host, add `requiredHostCapabilities` to `ExtensionDescriptor` and verify the reverse direction. Real systems also need schema parsing/validation, trust-source checks, activation policies, runtime availability status, and compatibility tests; this small `check` method should not be treated as a full plugin manager.

## 7. Safe, Observable Extension Admission Pipeline

1. **Discover metadata:** locate descriptors published by extensions, identifying the source clearly without instantiating the plugin yet.
2. **Validate:** check schema, ID/namespace, field types, versions, and capability keys; detect duplicates. Preserve rejection reasons.
3. **Check compatibility:** compare extension point, API/range, Java runtime, bidirectional capability requirements, and published host constraints.
4. **Authorize and enable:** apply trust and permission policies before instantiating the provider; then check readiness/availability if a capability depends on runtime state.
5. **Publish registry:** expose records containing ID, versions, capabilities, status, and rejection reasons for provider selection, logging, metrics, operations, and upgrade support.

A useful registry record can store `id`, `extensionPointId`, `implementationVersion`, `apiVersion`, `declaredCapabilities`, `availableCapabilities`, `status`, and `reasonCode`. For operational data, avoid using `displayName` as a query key because display names can change; use the stable ID and record versions separately to distinguish deployments.

At the request-handling layer, select extensions based on **extension point + required capabilities + availability status**; if multiple providers match, apply a clearly configured priority policy. If no provider matches, fail with "no compatible implementation" and diagnostic reasons instead of silently calling a roughly similar provider.

## 8. Common Design Mistakes and How to Avoid Them

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Using class/JAR name as ID | Refactoring, shading, or repackaging breaks old config | Put a stable ID in the descriptor |
| Embedding version numbers in the ID | Every update creates a new key, hard to migrate | Keep version as a separate field; change ID only when identity genuinely changes |
| Accepting duplicate IDs by load order | Behavior depends on classpath/discovery order | Reject duplicates or apply an explicit multi-instance policy |
| Using `implementationVersion` to check API compatibility | New plugins may still target an old or incompatible contract | Compare the API version/range field independently |
| Comparing versions as strings | Misorders `2.10` and `2.9` | Parse numerically/with SemVer rules |
| Inferring capabilities from implementing an interface | Invokes unsupported features | Declare and check capabilities at point of use |
| Equating capabilities with permissions or readiness | Failed calls, bypassed access policies | Distinguish provided, enabled/available, and authorization |
| Trusting metadata or SemVer without testing | Binary linkage failures or behavioral regressions | Contract/API test suite across declared supported versions |
| Loading classes before checking Java requirements | May hit `UnsupportedClassVersionError` prematurely | Read descriptor and check environment requirements before loading |
| Silently falling back when a feature is missing | Results violate expected semantics | Fail clearly or use a caller-approved fallback |

## 9. Contract Design Checklist

A sufficiently clear extension contract should answer:

- Do the extension point and provider have stable, unique IDs, namespace ownership, and migration rules when an ID changes?
- Do capability keys have consistent semantics, activation conditions, required/optional lists, and unsupported-reporting behavior?
- Are API version, implementation version, metadata schema version, and Java/host requirements independent and comparable via explicit rules?
- Can the host reject incompatible plugins before instantiating them, and does it preserve rejection reasons for troubleshooting?
- Are there tests for duplicate IDs, missing capabilities, differing API major/minor versions, insufficient Java runtime, version changes, and upgrading older plugins?

**Core principle:** ID resolves *which extension*, capabilities resolve *what the extension can do*, and version information resolves *which contracts and environments can work together*. Separating these three questions helps the registry choose the right provider, upgrade safely, and diagnose compatibility failures consistently.