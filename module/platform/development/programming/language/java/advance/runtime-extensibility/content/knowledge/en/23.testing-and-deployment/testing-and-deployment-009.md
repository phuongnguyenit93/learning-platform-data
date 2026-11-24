# Releasing Versioned Plugins, Validating Packages, and Keeping a Rollback Path

## 1. Goal of the Plugin Release Process

In a Java system that supports runtime extensibility, releasing a plugin is not as simple as compiling a JAR and copying it into a `plugins/` directory. A plugin is executable code running inside (or alongside) the host, typically with its own API contract, dependencies, configuration, permissions, and independent lifecycle. A release should only be activated when **the artifact has the right version, is valid, is compatible, and can be recovered** if something goes wrong.

Three goals must be met simultaneously:

1. **Identifiable and reproducible releases**: every version has an identifier, source revision, build settings, checksum/signature, and immutable artifact.
2. **Pre-execution package validation**: verify manifest/descriptor, JAR contents, dependencies, contracts, class-file version, configuration, and integrity.
3. **A verified rollback path**: the previous version is retained with compatible configuration; redirecting requests and cleaning up lifecycle do not lose state or close a plugin that is still handling traffic.

```text
Source + tests
      |
      v
Build immutable artifact (pluginId, version)
      |
      v
Validate: hash/signature, descriptor, API/JVM, dependencies
      |
      v
Stage + smoke test + health check
      |
      v
Publish active registry (atomic switch)
      |
      +-- OK --> observe + drain old version
      |
      +-- FAILURE --> rollback to safe release
                           |
                           v
                    observe + incident report
```

Note two distinct concepts: **deploy** means preparing a runnable release; **activate** means routing live requests to that version. Separating the two steps provides room for validation and rollback before impacting users.

## 2. Identification and Versioning Policy

A plugin should carry explicit metadata, at minimum:

| Field | Example | Purpose |
|---|---|---|
| `pluginId` | `csv-exporter` | Stable identifier of the plugin |
| `pluginVersion` | `1.8.2` | Release identifier |
| `requiredApiRange` | `[2.2.0,3.0.0)` | Supported host API range |
| `minimumJava` | `17` | Minimum Java runtime |
| `entryPoint` / `service` | `com.example.spi.Exporter` | Extension point to locate |
| `artifactSha256` | Separately verified SHA-256 | Uniquely identifies artifact bytes |
| `dependencies` | Module/JAR + version | Defines runtime closure |
| `permissions` | Allowed capabilities | Controls access privileges |
| `buildRevision` | Commit/build ID | Traceability to release source |

These fields may live in a JAR manifest, a JSON/YAML descriptor, or a protected release metadata record. They are **conventions of the plugin system**, not mandatory standard JPMS fields.

With Semantic Versioning (`MAJOR.MINOR.PATCH`), increment `MAJOR` when breaking compatibility contracts, `MINOR` for backward-compatible features, and `PATCH` for bug-fix changes under the project's contract. However, version digits alone do not prove compatibility: a change in behavior, concurrency, serialization, or permissions can break functionality even if method signatures stay identical.

**Never overwrite an artifact bearing the same plugin ID + version with different bytes.** Reusing versions makes rollback, caching, and traceability unreliable. If `1.8.2` needs a fix, release `1.8.3` or a new release identifier per policy.

## 3. Immutable Artifact Packaging

An illustrative release layout:

```text
releases/
└── csv-exporter/
    ├── 1.8.1/
    │   ├── csv-exporter.jar
    │   ├── release.json
    │   └── SHA256SUMS
    └── 1.8.2/
        ├── csv-exporter.jar
        ├── release.json
        └── SHA256SUMS
```

A version directory is **immutable** once approved. If the repository/artifact store supports content-addressable storage, keying by digest makes verification even clearer.

Example JAR manifest defined by host convention:

```text
Manifest-Version: 1.0
Plugin-Id: csv-exporter
Plugin-Version: 1.8.2
Plugin-Api-Version: 2
Plugin-Class: com.example.csv.CsvExportPlugin
```

These `Plugin-*` attributes are not mandatory JAR standards. The host defines how to parse and compare them. In JPMS, `module-info.class` and `ModuleDescriptor.version()` can carry module version metadata, but JPMS does not automatically resolve semantic version ranges or pick the newest version.

During builds, pin the toolchain, dependencies, and configuration; generate SBOM/provenance when organizational processes require it. **Reproducible builds** let you compare artifacts from identical inputs, though a differing digest does not by itself prove tampering and a matching digest does not replace publisher verification.

## 4. What Must Be Validated in a Plugin Package

Split validation into explicit gates.

### Gate A — Artifact and Provenance

- Does the file exist, stay within size limits, and parse as a readable JAR/ZIP?
- Is the path canonicalized, not escaping allowed directories via symlinks or traversal?
- Does the SHA-256 match the digest obtained from a **trusted source**?
- Does the digital signature/publisher identity satisfy policy and trust lists?
- Are **TOCTOU** protections in place: are the validated bytes the exact bytes later loaded?
- Are the archive's entry count, uncompressed size, and processing resources within bounds?

Reading metadata is not executing plugin code, yet a JAR is still untrusted input. For stronger safety, copy the artifact to an immutable staging location after validation and load only from that approved copy.

### Gate B — Metadata and Compatibility

- Are `pluginId`, version, entry point, API range, and minimum Java version valid?
- Does the ID collide with another plugin or does the version violate policy?
- Is the host API within the range the plugin supports, and are required capabilities present?
- Is the class-file major version supported by the runtime? Java 17 uses major 61, Java 21 uses major 65.
- Is the dependency closure complete, with version conflicts and split-package/duplicate module names handled?
- Does the shared API preserve class identity via the parent loader/layer?
- Does the provider match the service contract, with `provides` / `META-INF/services` properly configured?

**A module version is not a compatibility policy.** Having module `2.1.0` does not prove a plugin can use API v2.1 or that every binary method remains valid.

### Gate C — Verification in a Staging Environment

- Create the class loader or `ModuleLayer` matching the host's exact architecture.
- Discover providers; distinguish zero/one/many/broken providers.
- Instantiate and invoke lifecycle `start` or `initialize`.
- Execute smoke tests and mandatory contract methods.
- Check health, config, resource quotas, timeouts, and security policy.
- On failure, do not publish the plugin; clean up all initialized resources.

**Note:** running constructors, static initializers, or `ServiceLoader.Provider.get()` can execute plugin code. Do not load untrusted code into the same JVM to "test it out" when security policy requires strong isolation.

## 5. Java 17+ Example: Checking Manifest and Digest Before Activation

Create **`PluginPackageInspector.java`**. The program validates basic manifest fields, an illustrative version format, and the SHA-256 of the JAR itself; it does not load the entry-point class. The digest is **printed for comparison** against a trusted distribution source and does not by itself prove the artifact is safe.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;
import java.util.regex.Pattern;

public final class PluginPackageInspector {
    private static final Pattern ID =
            Pattern.compile("[a-z][a-z0-9-]{0,63}");
    private static final Pattern VERSION =
            Pattern.compile("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)");
    private static final int SUPPORTED_API = 2;

    private static String require(Attributes attributes, String key) {
        String value = attributes.getValue(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return value.trim();
    }

    private static void inspect(Path file) throws Exception {
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException("Not a regular file");
        }
        try (JarFile jar = new JarFile(file.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalArgumentException("Missing JAR manifest");
            }
            Attributes a = manifest.getMainAttributes();
            String id = require(a, "Plugin-Id");
            String version = require(a, "Plugin-Version");
            String apiText = require(a, "Plugin-Api-Version");

            if (!ID.matcher(id).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Id");
            }
            if (!VERSION.matcher(version).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Version");
            }
            int api;
            try {
                api = Integer.parseInt(apiText);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid API version", e);
            }
            if (api != SUPPORTED_API) {
                throw new IllegalArgumentException("Unsupported API " + api);
            }

            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) >= 0) {
                    if (count > 0) sha256.update(buffer, 0, count);
                }
            }
            System.out.println("VALID " + id + "@" + version);
            System.out.println("API " + api);
            System.out.println("SHA-256 " +
                    HexFormat.of().formatHex(sha256.digest()));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java PluginPackageInspector <jar>");
            System.exit(2);
        }
        try {
            inspect(Path.of(args[0]));
        } catch (IllegalArgumentException e) {
            System.err.println("REJECTED: " + e.getMessage());
            System.exit(1);
        }
    }
}
```

Create a metadata-only sample JAR to test. Save manifest **`plugin.mf`** ending with a blank line:

```text
Manifest-Version: 1.0
Plugin-Id: csv-exporter
Plugin-Version: 1.8.2
Plugin-Api-Version: 2

```

Run on JDK 17+:

```bash
javac PluginPackageInspector.java
jar --create --file sample-plugin.jar --manifest plugin.mf
java PluginPackageInspector sample-plugin.jar
```

Stdout looks like:

```text
VALID csv-exporter@1.8.2
API 2
SHA-256 <64 hex characters of the actual artifact>
```

The SHA-256 line is shown as a placeholder because JAR bytes vary with metadata and build environment. **Never hard-code this digest as a security value.** This illustrative program does not check publisher signatures, archive limits, full class files, dependencies, service declarations, or races between two file opens. In production, enforce an allowlist and verify the immutable copy that gets loaded afterward.

To test the rejection branch, change `Plugin-Api-Version: 2` to `3` and rebuild the JAR; the program prints to stderr:

```text
REJECTED: Unsupported API 3
```

## 6. Controlled Release Pipeline

A practical CI/CD pipeline:

```text
Commit / release tag
    |
    v
Build with locked toolchain & dependencies
    |
    v
Unit tests + compatibility tests
    |
    v
Package JAR + descriptor + checksum + provenance
    |
    v
Artifact validation / signature verification
    |
    v
Publish immutable release (never overwrite version)
    |
    v
Stage in host, resolve dependencies, and run smoke tests
    |
    v
Canary or rollout by request/tenant cohort
    |
    v
Atomic activate + monitoring
    |
    v
Stable / rollback
```

What must be recorded for every release: `pluginId`, version, exact digest, release ID, API requirement, Java requirement, publisher/signature status, dependency list, host deployment ID, timestamp, and human/automated approver per policy.

**Deploy approval and activate approval can be separate.** Splitting the two prevents an artifact uploaded to a repository from immediately running in production before compatibility checks pass.

## 7. Separating Staged, Active, and Previous

A plugin manager should track explicit states:

| State | Meaning | Accepts New Requests? |
|---|---|---|
| `DISCOVERED` | New package appeared, unverified | No |
| `VALIDATED` | Artifact and metadata valid | No |
| `STAGED` | Resolved and initialized in verification environment | No |
| `ACTIVE` | Selected by current active registry | Yes |
| `DRAINING` | Stopped receiving new requests, waiting on existing ones | No |
| `STOPPED` | Resources closed per lifecycle | No |
| `FAILED` / `QUARANTINED` | Violates policy or failed startup | No |

You can maintain a **release manifest** of the rollback-eligible version:

```text
active  -> csv-exporter@1.8.2 (sha256:...)
previous-> csv-exporter@1.8.1 (sha256:...)
```

However, "previous" is not necessarily a still-running object. It may simply preserve the verified artifact, dependency closure, and compatible configuration. If V1 has already been closed or its class loader released, rolling back requires **re-initializing V1**, not merely repointing a reference to an old instance.

If the plugin maintains persistent state, define schema migration and backward compatibility from the start. If V2 has written data using a V2 schema unreadable by V1, switching the JAR back to V1 **does not guarantee business rollback succeeds**.

## 8. Atomic Publication and Not Closing the Old Version Too Early

In read-heavy systems, a writer can prepare a new immutable registry and publish it via `AtomicReference`:

```java
// Integration snippet, not a standalone program.
record Registry(long revision, Map<String, Plugin> plugins) {
    Registry {
        plugins = Map.copyOf(plugins);
    }
}

AtomicReference<Registry> active =
        new AtomicReference<>(new Registry(0, Map.of()));
```

After V2 passes checks, the writer builds a new snapshot and calls `active.set(newRegistry)`. Readers capture a single snapshot and hold it for an entire logical operation to avoid mixing two versions.

However, an atomic swap **does not permit closing V1 immediately**: requests that captured the old snapshot may still be invoking V1.

```text
Reader A already holds V1
      |
Writer publishes V2
      |
New requests use V2
      |
Reader A continues using V1
      |
Drain V1 / wait for leases to end
      |
Close V1
```

You can use lease/reference counting with an acquire protocol that does not race with draining, or a read/write lock protecting lifetime. Simply incrementing a ref-count after reading the snapshot without synchronizing against close is insufficient; it suffers from an acquire-after-close race.

If multiple writers update the registry concurrently, use a single-writer executor, lock, or proper CAS to avoid lost updates. Never put `plugin.start()` inside a CAS retry loop that might re-run.

## 9. Rollback: Switching Versions Is Not Undoing Data

Rollback must define its scope:

- **Traffic rollback:** route new requests back to the stable version.
- **Code/artifact rollback:** reload the binary and dependencies of the prior release.
- **Config rollback:** restore the compatible configuration/feature flags.
- **Data rollback:** handle data/schemas altered by the faulty release.
- **Operational rollback:** stop canary, revoke permissions, close callbacks/tasks, and clean up resources.

Not everything reverts automatically. If V2 has sent emails, recorded payments, or migrated data schemas, switching back to V1 does not undo those side effects. Idempotency, compensation, or tested reverse migrations are required.

### Minimum Rollback Playbook

1. **Identify trigger:** error rate, latency, health checks, compatibility failures, or security incident exceeding policy thresholds.
2. **Freeze rollout:** halt activating V2 on further nodes/tenants.
3. **Verify rollback target release:** confirm the previous artifact digest, dependencies, and config are still available and valid.
4. **Initialize previous version in staging** if the old instance was stopped.
5. **Switch traffic/registry atomically** per policy; drain/cancel in-flight requests safely.
6. **Post-rollback verification:** check health, error rates, data integrity, and essential capabilities.
7. **Clean up V2:** stop tasks/listeners, close resources, and drop references/class loaders per lifecycle.
8. **Record incident:** version, digest, reason, timestamp, outcome, and any remaining data remediation steps.

**Do not auto-rollback indefinitely** if the prior version is also failing or the state schema is no longer compatible. You may need to put the feature into degraded mode and block side-effecting operations.

## 10. Canary and Progressive Rollout

For plugins with major behavioral changes, stage them first and then roll out to controlled cohorts/tenants or traffic percentages. Pay attention to **sticky routing** for multi-step requests: a workflow should not start on V1 and accidentally finish on V2 if the contract requires pinning a version.

Signals to monitor:

| Signal | Detection Hint |
|---|---|
| Startup/health failure | Plugin cannot activate |
| `LinkageError` | Binary/API mismatch or class loader conflict |
| Request error rate | Changed/broken plugin behavior |
| Latency p95/p99 | Slowdowns from dependencies, cache, or resources |
| Resource/Metaspace | Loader, thread, callback, or resource leak |
| Duplicate side effects | Retries/rollbacks repeating business actions |
| Plugin-specific metrics | Export output quality, formatting error rate |

Canaries must run long enough and carry enough representative traffic to expose real failures. A single demo request cannot prove safety for all production traffic.

## 11. Testing Releases and Rollback Before Production

The test suite should cover:

1. Zero providers: host returns a meaningful error.
2. One valid provider: invokes the right implementation.
3. Many providers: applies selection policy and handles duplicates.
4. Misconfigured provider: rejected before activation.
5. Artifact with wrong digest or signature: not loaded.
6. Unsatisfied module/API requirement: rejected with clear reason.
7. Factory/constructor or health check failure: broken snapshot is not published.
8. V2 active while V1 still in-flight: V1 is not closed prematurely.
9. Rollback after V2 publication: new traffic selects verified V1.
10. Persistent data written by V2: can V1 read/handle it per migration policy?
11. Multiple reloads: class loaders, callbacks, threads, and Metaspace do not grow unboundedly.
12. Shutdown mid-rollout or mid-rollback: resources are cleaned up and state is unambiguous.

Use multi-version JAR test fixtures, integration tests with real class loaders/module layers, and controlled failure injection. When testing concurrent publication, use latches/barriers rather than `Thread.sleep` as ordering proof.

## 12. Common Release Mistakes

- Overwriting artifacts with the same version, making checksums and rollback targets untrustworthy.
- Checking only that a JAR exists without verifying signature, dependencies, and compatibility.
- Assuming `ModuleDescriptor.version()` automatically enforces API version ranges.
- Using a mutable JAR on the filesystem as the class-loading source after validation.
- Activating a plugin before verifying constructor/provider and health checks.
- Publishing providers piecemeal instead of a complete registry snapshot.
- Closing V1 immediately after V2 publishes while V1 requests are still running.
- Retaining only a version string without keeping the exact old artifact + digest + config.
- Thinking rolling back a JAR reverses schema migrations and side effects.
- Failing to plan when the rollback target was deleted or no longer runs on a newer JDK.
- Ignoring loader leaks, thread leaks, and resource leaks across repeated deployments.
- Running untrusted plugins in the same JVM without appropriate security boundaries.

## 13. Release and Rollback Checklist

Before enabling a new plugin version:

- Does the artifact have an **immutable** ID/version, matching digest, and provenance?
- Do manifest/descriptors carry valid schema, API requirement, Java requirement, and service entry?
- Has artifact integrity/signature been verified against a trusted source?
- Are dependencies/JARs/modules right, with no duplicate modules/classes causing conflicts?
- Has the plugin passed unit, contract, integration, smoke, and health checks?
- Is the registry published only after all required providers are ready?
- Is there a lease/drain protocol to avoid closing in-flight plugins?
- Are the exact prior release, its config, dependencies, and rollback guide preserved?
- Have migrations/schemas been checked for rollback compatibility?
- Are canary, metrics, stop thresholds, timeouts, and operational owners defined?
- Are resource/class-loader cleanup procedures and release decision logs in place?

**Remember:** safe plugin releasing is **immutable versioned packaging → artifact and contract verification → staging → controlled publication → observability → pre-tested rollback**. Keeping an old JAR is only a necessary condition; a **true rollback path** requires dependencies, configuration, data, lifecycle, and traffic routing all to support it.
