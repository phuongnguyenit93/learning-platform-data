# Controlling JAR Origin, Integrity, and Allowed Dependencies

A Java application can load bytecode from a JAR via `URLClassLoader`, a plugin framework, `ServiceLoader`, or `ModuleLayer`. However, **“being able to load a class” does not mean “the JAR is trusted and permitted to execute”**. Before allowing external code to run in the JVM, you must simultaneously control **the publishing origin**, **artifact identity and version**, **byte integrity**, **the dependency chain**, and **runtime execution permissions**.

This is a **security boundary and software supply chain** problem. A JAR with a correct checksum can still contain malicious code or CVEs; a validly signed JAR can still be signed by someone not approved by the organization; an allowed JAR that brings along dependencies outside the allowlist can still cause the JVM to execute unintended code.

**Core principle:** Build an **artifact verification gate** before class loading; only create a loader/define a module from **the exact approved bytes**. If a condition cannot be verified, **fail closed**; do not fall back to another repository or loading path just to “make it run”.

## 1. Three Control Layers That Must Be Kept Separate

| Question | Required Data | What It Does Not Prove by Itself |
| --- | --- | --- |
| **Is the JAR source approved?** | Publisher, repository, artifact coordinates, version, release policy | Whether the contents are intact |
| **Is the artifact the exact approved copy?** | SHA-256 pin from a trusted policy, signature and signer trust when required | That the code contains no bugs or malicious behavior |
| **Are these dependencies allowed?** | Full resolved dependency graph, versions, hashes, scopes, runtime allowlist | That the code does not use reflection, native libraries, or download anything else |

These three layers form a control pipeline:

~~~text
Trusted publisher / CI build
            |
            v
    Allowed repository
            |
            v
   JAR + release metadata
            |
            v
        POLICY GATE
        /    |      \
       v     v       v
   Origin   SHA-256  Dependency graph
       \     |       /
        \    |      /
         v   v     v
      Protected staging
              |
              v
     ClassLoader / ModuleLayer
              |
              v
      Runtime isolation + audit
~~~

Do not collapse the three questions into a single `isTrusted=true` flag of unclear origin. If a JAR passes through multiple layers (CI, artifact registry, deployment cache, host plugin manager), each layer must know **who is the source of truth** for digest/identity/approval and who has permission to update them.

### Risks to Cover

- **Tampering:** a JAR file is modified after build time or after approval.
- **Publisher compromise:** a publishing account or CI is compromised, producing a build that looks valid in name and version.
- **Dependency confusion:** an artifact belonging to an internal namespace is resolved from a public repository due to name collision or incorrect mapping.
- **Typosquatting:** an artifact has a name closely resembling a legitimate library.
- **Unintended transitive dependencies:** a direct dependency pulls in a new, unapproved package.
- **Version drift/downgrade:** the version or bytes change due to ranges, snapshots, mirrors, caches, or missing locks.
- **Runtime graph drift:** `Class-Path` in the manifest, adding URLs to a loader, service providers, native libraries, or a downloader introduces additional code into the process.
- **Vulnerabilities in an intact artifact:** the JAR has the right hash, but that version inherently has a CVE, backdoor, license risk, or permissions exceeding what is necessary.

HTTPS/TLS and an internal repository mitigate many risks, but **do not by themselves verify that the publisher/artifact code is safe**. An endpoint with valid TLS can still host a poisoned release.

## 2. Origin Policy (Origin/Identity Allowlist)

A JAR acceptance mechanism should not merely check the `.jar` file extension or directory name. For Maven-style artifacts, **coordinates and origin** must be recorded:

~~~yaml
# Illustrates a custom-designed policy, NOT a Maven/Gradle schema.
artifact: com.acme.plugins:greeter:1.0.0
repository: internal-approved-registry
publisher: approved-release-identity
sha256: "digest-64-hex-được-lấy-từ-trusted-policy"
runtime_dependencies:
  - com.acme.api:plugin-contract:2.3.0
  - org.example:safe-parser:4.2.1
manifest_class_path: deny
native_libraries: deny
network_code_downloads: deny
~~~

This is only **configuration pseudocode**; the `sha256` string illustrates the placeholder for an approved digest, not a real digest. A real policy needs a concrete schema and validator, versioning, approvers, and a trustworthy update process.

**At a minimum, lock down:**

1. **Group/artifact/version/classifier** (if present); do not accept a JAR with a nice name that lacks a publishing identity.
2. **Allowed registries/repositories**, explicit internal namespace mappings, and least-privilege credentials and publish permissions.
3. **Signer or provenance identity**, with an independent source of evidence strong enough to bind the digest to the right release.
4. **SHA-256 of each artifact** in the deployed build, not just package metadata.
5. **An allowlist for the entire dependency graph**, including direct, transitive, runtime, and any embedded components.
6. **Version and policy revocation**, so that a previously accepted release can be revoked when a compromise or critical CVE is discovered.
7. **Audit evidence**: who approved it, when, the inspected manifest, the final digest, and which loader/plugin consumed it.

### Do Not Compare Paths as Raw Strings

Incorrect in principle:

~~~java
// Incorrect fragment: "/approved-evil/x.jar" also starts with "/approved".
if (jarPath.toString().startsWith("/approved")) {
    allow();
}
~~~

This is a **counterexample fragment**, not a standalone program. In Java, you should check the canonicalized path using `Path.toRealPath()` and `Path.startsWith(Path)`, taking into account symlinks, filesystem permissions, and writable directories.

**However, a valid path does not mean the file cannot change:** Between computing the checksum and `URLClassLoader` opening the file, **TOCTOU (time-of-check/time-of-use)** can occur. Production environments require **immutable/read-only staging controlled by a trusted party**, ensuring the loader reads the exact bytes that were just verified, and preventing an uncontrolled writer from replacing the file between the two steps.

## 3. Integrity Verification with SHA-256

For the JAR `greeter-1.0.jar`, compute the digest over the **entire JAR bytes**:

~~~text
SHA256(actual-final-JAR-bytes) == trustedExpectedDigest
~~~

Another build might contain equivalent bytecode but differ in ZIP metadata, timestamps, or entry order, causing the **full-JAR hash to differ**. This is not necessarily an attack, but a **pinned final artifact** must match across all bytes.

On Windows PowerShell:

~~~powershell
Get-FileHash .\approved\greeter-1.0.jar -Algorithm SHA256
~~~

On Linux:

~~~bash
sha256sum approved/greeter-1.0.jar
~~~

On macOS, you can use `shasum -a 256`. These commands **only compute** the current digest; by themselves, they do not determine whether that hash is trustworthy.

### Where Must the Expected Hash Come From?

This is the most critical checksum pitfall: if an attacker controls the distribution endpoint and serves both `plugin.jar` and `plugin.jar.sha256`, then the two files matching **proves nothing about the publisher**. The attacker simply replaces **both**.

The expected value must be obtained from an independent policy, such as:

- A trusted build/release manifest generated and signed by an approved pipeline, bound to the artifact coordinates.
- A signed attestation with a trust root and builder/publisher identity verified by the organization.
- A deployment database with strict write/approval permissions that stores only digests reviewed through a trusted workflow.
- A pinned value delivered out-of-band over an authenticated administrative channel.

**A hash is not a signature.** SHA-256 answers “do the bytes match the pin?”, not “who published it?” if the pin lacks provenance. `String.hashCode()`, CRC32, or a legacy MD5 file cannot replace SHA-256 for modern adversarial integrity checks.

### Compare Against the Final Artifact

If a JAR is repacked, shaded, re-signed, stripped, or transformed after hashing, you must approve the digest of **the exact artifact passed to the loader**. Do not rely on the checksum of the pre-transformation source JAR to claim that the new fat JAR is verified.

If dependencies span multiple JARs, **each JAR must have its own artifact identity and digest**. Hashing a single plugin file does not automatically control the external libraries it will load.

## 4. JAR Signatures: Cryptographically Valid Is Not Yet “Trusted”

The Java JDK provides `jarsigner` for signing and verifying JARs. For a **digitally signed** JAR, you can inspect it with:

~~~bash
jarsigner -verify -strict -verbose -certs approved/greeter-1.0.jar
~~~

This is a reference command for signed JARs with a real trust policy; the example JAR in section 7 is **unsigned** by default.

You must check **multiple conditions**, not just look at a single line of output:

- **Signature integrity:** the data and digests of signed entries have not been altered; the signature block verifies cryptographically.
- **Coverage:** have all entries requiring protection been signed? Are there entries added after signing or left unsigned?
- **Signer identity:** does the certificate/public key belong to an authorized publisher organization? Is there an appropriate trust anchor/key pin?
- **Trust chain and validity period:** do the certificate chain, algorithm policy, key strength, timestamp, and related warnings satisfy the rules?
- **Artifact binding:** did the signer sign the exact accepted version/digest and release channel?
- **Revocation/review:** are there any revocation notices or incidents associated with the signer/artifact?

`-strict` can cause severe warnings to affect the exit status, but the verification command and trust policy must be explicitly designed. An **unsigned** JAR is not automatically approved simply because the tool does not print an outright error. Conversely, a signature produced by an arbitrary certificate is **not** enough to grant execution permission.

**Do not mistake `new JarFile(file, true)` for a comprehensive verifier.** `JarFile` supports verifying signatures of signed entries when they are read. It does not automatically read all entries or enforce enterprise signer/trust policies. If you want to authenticate the signer, you must have an independent, thorough, fail-closed step.

| Mechanism | Capability | Limitation |
| --- | --- | --- |
| SHA-256 + trusted pin | Matches the exact approved bytes | Does not prove the code has no CVEs; does not confirm origin if the pin is untrusted |
| JAR signature + trust policy | Binds signature/entries to an approved signer | Does not cover external dependencies or runtime permissions |
| Signed provenance | Verified evidence of the builder/source/release workflow | Does not prove all code behavior is safe |
| SBOM + SCA | Inventories dependencies and detects known vulnerabilities | May miss shaded/dynamic components; does not replace checksums |
| Isolation/least privilege | Limits impact when code executes | Does not by itself prove the artifact is intact |

## 5. Controlling All Allowed Dependencies

A plugin may have a graph:

~~~text
com.acme:greeter-plugin:1.0.0
 ├─ com.acme:plugin-api:2.3.0
 ├─ org.example:parser:4.2.1
 │    └─ org.example:codec-core:1.8.0
 └─ org.example:logging:3.1.0
~~~

If you only approve `greeter-plugin` and `parser`, the transitive `codec-core` version may still be resolved and executed. **The policy must cover the final resolved result**, not just direct dependency declarations.

Dependency sources that must be managed:

1. **Build-time:** Maven/Gradle resolving POMs, BOMs, dependency substitutions, conflict resolutions, and the transitive graph.
2. **Runtime:** the actual classpath/module path when the process runs, including injected JARs outside the build output.
3. **Manifest:** a JAR's `Class-Path` attribute can expand the class/resource search path of a `URLClassLoader`.
4. **Dynamic loaders:** `URLClassLoader.addURL`, custom loaders, plugin resolvers, `ModuleFinder`/`ModuleLayer`.
5. **Discovery:** `META-INF/services`, `ServiceLoader`, or framework reflection instantiating provider implementations.
6. **Embedded and native code:** shaded/fat JARs, nested JARs, JNI, `System.load`/`System.loadLibrary`, or downloaders fetching code at runtime.

**A JAR filename is not sufficient as a dependency identity.** You need the version, coordinates, digest, source, and corresponding scope. Shaded libraries may no longer exist as standalone JARs, yet you still need an inventory of the components actually packaged inside the artifact.

### Shared API Between Host and Plugin

The host and plugin exchange objects through shared interface/DTO/exception types. For a class or interface, **type identity = (binary name, defining class loader)**. If a plugin packages and defines its own copy of `com.acme.api.Task` instead of using the host's API definition, the host may encounter a `ClassCastException` or an invalid provider despite having the same name.

A class loading policy typically looks like:

~~~text
java.* / platform modules         → runtime/platform loaders
com.acme.api.*                    → host-controlled shared/parent loader
plugin.impl.*                     → approved plugin loader
approved private dependencies     → plugin loader per policy version
unknown packages/JAR providers    → reject or controlled lookup
~~~

This is an **architectural model**, not automatic Java behavior. When child-first is needed for implementations, you must still ensure parent-first for the shared API. Supply chain boundaries and type identity complement each other: a JAR with the right hash that loads the API in the wrong loader can still break communication.

### Manifest Class-Path and Dynamic Lookup

`URLClassLoader` supports JAR URLs, directories, and class/resource lookup mechanisms. A manifest containing:

~~~text
Class-Path: lib/extra.jar
~~~

can add extra dependencies into the loader's search path according to Java's manifest handling. If the plugin system does not support this type of extension, **reject JARs containing the `Class-Path` attribute**; if it does support it, resolve URLs safely and verify **each auxiliary artifact** before loading. Do not assume that passing only one URL to the constructor means the entire class loading graph consists of a single file.

## 6. Approval Pipeline from Build to Runtime

~~~text
Reviewed source + dependency policy
        |
        v
Controlled CI/toolchain/runner
        |
        v
Resolve from allowed repository
        |
        +-- pin direct/transitive versions
        +-- check hashes/signers
        +-- SCA / license policy
        +-- SBOM / provenance metadata
        |
        v
Build final artifact
        |
        v
Promotion/approval, signed release manifest
        |
        v
Immutable artifact cache/staging
        |
        v
Check digest/signature + dependency closure
        |
        v
Instantiate ClassLoader / ModuleLayer
        |
        v
Runtime restrictions + audit + revocation
~~~

Key factors:

- **Reproducible builds** help compare outputs from source and toolchain, but you still must control build scripts and dependency artifacts.
- **An SBOM** should include direct, transitive, shaded, or bundled libraries according to build and runtime analysis capabilities. It may not see dynamically loaded dependencies.
- **SCA** should continuously check advisories/CVEs and usage policies; a newly discovered vulnerability can require an already-approved artifact to be revoked.
- **Provenance/attestation** requires verifying the trust root, builder/publisher identity, and artifact digest; do not trust it merely because a file named `provenance.json` exists.
- **Runtime approval** must verify against the exact bytes placed into production, not merely a claim that CI once checked a similar build.

When the gate rejects a JAR, do not silently search for another version in a public registry. That is a common path leading to **dependency confusion** or downgrade.

## 7. Java 17 Runnable: Checking a JAR Before URLClassLoader

This learning example has specific policies:

- Accept only the file `greeter-1.0.jar` inside the `approved` directory.
- Canonicalize the path and verify its exact location.
- Stream the entire file to compute SHA-256 and compare it against a 64-character hex pin provided by the caller.
- Reject manifests that contain `Class-Path`.
- Only when all of the above conditions pass, create `URLClassLoader` and invoke the `plugin.Greeter` class.
- There are no dependencies outside `java.base`, so using `ClassLoader.getPlatformClassLoader()` as the parent is sufficient for the demo's goal.

**Limitations:** This program does not verify certificates/trusted signers, does not validate a transitive graph, and does not defend against TOCTOU if the directory has an untrusted writer. It does **not** create a sandbox or protect against an already malicious plugin. This is an example of **the check ordering before loading classes**, not a complete production supply-chain manager.

File structure:

~~~text
jar-gate-demo/
├── JarGate.java
├── src/
│   └── plugin/
│       └── Greeter.java
├── classes/                     (output directory)
└── approved/
    └── greeter-1.0.jar          (JAR created in the build step)
~~~

### File 1: src/plugin/Greeter.java

~~~java
package plugin;

public final class Greeter {
    public static String message() {
        return "hello from pinned JAR";
    }
}
~~~

### File 2: JarGate.java

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class JarGate {
    private static final String APPROVED_FILE = "greeter-1.0.jar";

    private static byte[] sha256(Path file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return digest.digest();
    }

    private static void checkManifest(Path jar) throws Exception {
        try (JarFile file = new JarFile(jar.toFile())) {
            Manifest manifest = file.getManifest();
            if (manifest != null && manifest.getMainAttributes()
                    .getValue(Attributes.Name.CLASS_PATH) != null) {
                throw new SecurityException("manifest Class-Path not allowed");
            }
        }
    }

    private static void run(Path approvedDir, Path input,
                            String expectedHex) throws Exception {
        if (!expectedHex.matches("[0-9a-fA-F]{64}")) {
            throw new SecurityException("invalid pinned SHA-256");
        }

        Path root = approvedDir.toRealPath();
        Path jar = input.toRealPath();

        if (!Files.isRegularFile(jar, LinkOption.NOFOLLOW_LINKS)
                || !jar.startsWith(root)
                || !jar.getFileName().toString().equals(APPROVED_FILE)) {
            throw new SecurityException("source not allowlisted");
        }

        byte[] pinned = HexFormat.of().parseHex(expectedHex);
        byte[] actual = sha256(jar);
        if (!MessageDigest.isEqual(actual, pinned)) {
            throw new SecurityException("SHA-256 mismatch");
        }

        checkManifest(jar);
        System.out.println("Approved source: true");
        System.out.println("SHA-256 matches: true");
        System.out.println("Manifest Class-Path absent: true");

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { jar.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> plugin = Class.forName(
                    "plugin.Greeter", true, pluginLoader);

            System.out.println("Plugin result: "
                    + plugin.getMethod("message").invoke(null));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.out.println("Usage: java JarGate <dir> <jar> <sha256>");
            return;
        }

        try {
            run(Path.of(args[0]), Path.of(args[1]), args[2]);
        } catch (SecurityException denied) {
            System.out.println("DENIED: " + denied.getMessage());
        }
    }
}
~~~

**The program was tested** on OpenJDK with the `--release 17` flag: a valid JAR is accepted, whereas an incorrect hash pin is rejected. Below is how to run it yourself.

### Build the Project

Create the output directories first:

~~~bash
mkdir -p classes approved
javac --release 17 -d classes src/plugin/Greeter.java
jar --create --file approved/greeter-1.0.jar -C classes .
javac --release 17 JarGate.java
~~~

The block above is for Bash/Linux/macOS. On Windows PowerShell, create the directories with the equivalent command:

~~~powershell
New-Item -ItemType Directory -Force classes, approved | Out-Null
javac --release 17 -d classes src/plugin/Greeter.java
jar --create --file approved/greeter-1.0.jar -C classes .
javac --release 17 JarGate.java
~~~

### Accepted Case

**For the local demo only**, compute the pin from the JAR you just built:

~~~powershell
$expected = (Get-FileHash .\approved\greeter-1.0.jar -Algorithm SHA256).Hash
java JarGate approved approved/greeter-1.0.jar $expected
~~~

Or on Bash:

~~~bash
expected=$(sha256sum approved/greeter-1.0.jar | cut -d' ' -f1)
java JarGate approved approved/greeter-1.0.jar "$expected"
~~~

**Stdout of the Java command:**

~~~text
Approved source: true
SHA-256 matches: true
Manifest Class-Path absent: true
Plugin result: hello from pinned JAR
~~~

**Warning:** The step computing `$expected` or `expected=$(sha256sum ...)` is **only suitable for this hands-on exercise** when you build it yourself from trusted source. In production, you must never obtain the expected hash from **the untrusted artifact itself** and then declare the artifact verified. The `expectedHex` value must come from an independent trusted release manifest / signed policy / pinned configuration.

### SHA-256 Mismatch Case

On PowerShell:

~~~powershell
$wrong = '0' * 64
java JarGate approved approved/greeter-1.0.jar $wrong
~~~

**Stdout:**

~~~text
DENIED: SHA-256 mismatch
~~~

No `URLClassLoader` is created in that rejected branch. If the input belongs to an invalid root or the JAR filename is not on the allowlist, the program prints `DENIED: source not allowlisted` after the path resolves successfully.

### Why Does the Example Check Before Class.forName?

`Class.forName("plugin.Greeter", true, pluginLoader)` requests **loading and initializing** the class. The plugin code's static initializer (if any) can execute code. Therefore, the gate must succeed **before creating/looking up the plugin class and before triggering initialization**, rather than “loading it first to see if it is safe” and hashing afterward.

### Reading the Code by Control Layer

1. `Path.toRealPath` and `Path.startsWith(Path)` confirm the canonical location within the approved directory. The JAR filename is compared using exact equality.
2. `sha256` uses `InputStream` and `MessageDigest` in chunks so it does not have to load the entire JAR into a byte array just to hash it.
3. `HexFormat.of().parseHex` (Java 17) converts the 64-character hex pin into 32 bytes.
4. `MessageDigest.isEqual` compares the actual digest against the expected pin.
5. `JarFile` inspects the manifest. If `Class-Path` is present, it rejects it to block a path for expanding URL dependencies **in this demo design**.
6. `URLClassLoader` receives only one approved JAR URL. `getPlatformClassLoader` is an appropriate parent for a standalone plugin example; a real plugin host may require a different **shared API parent loader**.
7. `Class.forName` causes the JAR's class to be loaded/initialized after the gate. The `message()` method returns a fixed result.
8. `try-with-resources` closes URLClassLoader after use. This does not guarantee all classes are unloaded immediately.

**Do not overgeneralize:** A filename allowlist and SHA-256 of the JAR alone are not enough to control all dependencies, because the code can still access classes defined by the parent, or interact with files, the network, native libraries, or other loaders. That is the boundary of this example.

## 8. The TOCTOU Problem and Artifact Staging

A subtle design flaw:

~~~text
T1: verifier opens /approved/greeter.jar, hash matches
T2: another process replaces /approved/greeter.jar
T3: URLClassLoader opens the file by path
T4: JVM loads bytes different from the copy the verifier checked
~~~

`toRealPath()` does not prevent file replacement. A file with the correct digest at check time can still be replaced afterward by a writer with permissions.

Measures typically required in real systems:

- Allow only a trusted pipeline/artifact manager to **write** to the staged artifact directory; the runtime should only **read**.
- Store files at paths keyed by **content digest** and protect modification/write permissions, rather than using a generic JAR name that can be overwritten.
- Download to a temporary file under controlled permissions, verify thoroughly, and then **promote** to a read-only release store using an atomic operation and an appropriate ownership policy.
- Ensure the class loader reads the exact verified staged file rather than re-fetching it from another URL at runtime.
- Re-verify at deployment/startup according to the threat model; do not use an unprotected allowlist.
- Audit the digest of the actual copy loaded and execute the revocation procedure if an invalid copy is detected.

No **single Java Path API call** provides end-to-end assurance on its own if an attacker still has permission to modify files or alter the artifact repository.

## 9. Maven: Direct and Transitive Dependencies

With Maven, `pom.xml` has dependencies and `dependencyManagement`/BOM; Maven resolves the graph based on profiles, scopes, repositories, and policies. You should:

1. Pin versions via a release manifest and avoid version ranges or uncontrolled SNAPSHOTs in production.
2. Manage artifacts through a mirror/internal registry with namespace mapping and explicit publish permissions.
3. Inspect the entire resolved graph:

~~~bash
mvn dependency:tree
~~~

The command above requires a Maven environment and the corresponding Maven Dependency Plugin; output depends on the project, so there is no fixed stdout.

4. Apply policies such as Maven Enforcer `bannedDependencies`, `dependencyConvergence`, or `requireUpperBoundDeps` where appropriate to prevent conflicting or banned coordinates/versions.
5. Publish the resolved artifact list along with versions, source repositories, and hashes as part of a signed/approved release manifest.
6. Run SCA and license policy checks continuously, and review dependency changes via pull requests.

**A BOM is not by itself a hash lockfile for the entire artifact graph.** A BOM helps manage versions but does not guarantee that every dependency has been pinned, verified by digest, and sourced from the right origin. The deployed build must be checked against the **actual graph** and the final artifact bytes.

Also, do not confuse the Maven graph with the entire runtime if the application uses server-injected libraries, dynamically loaded `ModuleLayer` instances, or a plugin manager that adds JARs after build time.

## 10. Gradle: Locking Versions Differs from Verifying Bytes

Gradle provides two distinct feature sets:

- **Dependency locking:** locks resolved versions to prevent uncontrolled changes.
- **Dependency verification:** compares artifact checksums/signatures against managed verification metadata.
- **Repository content filters/exclusive content:** restricts which repositories specific artifact coordinates can come from.

An example Kotlin DSL fragment:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

This is an **illustrative configuration**, not a complete Gradle build file. To actually enforce locking, you must generate and review the lock state, keep lockfiles under version control, and apply the appropriate configurations.

Inspect a relevant resolved runtime graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Configuration names may vary depending on the plugin (Android, multi-project, custom runtime), so you must choose the exact graph being deployed. Enabling locking without managing the actual runtime configuration does not protect all artifacts loaded later.

**Verification metadata must be reviewed**, especially when generated initially or when dependencies change. If you let the tool automatically add hashes of artifacts downloaded from a poisoned source without an independent publisher/provenance verification step, the system simply locks **malicious bytes**.

~~~text
Repository policy   → where is the artifact fetched from?
Lockfile            → which version is resolved?
Verification        → which bytes/signatures are accepted?
SCA/SBOM            → which components and which known risks?
Runtime loader gate → which final artifact is actually loaded?
~~~

Each question must have its own answer and test evidence.

## 11. SCA, SBOM, Provenance, and Revocation

**An SBOM (Software Bill of Materials)** provides a list of components in a release. It is useful for inventory, CVE response, and tracing transitive dependencies. When fat JARs/shading are used, you must ensure embedded components are still recorded; when the runtime loads other JARs outside the build, you must supplement it with a runtime inventory source.

**SCA (Software Composition Analysis)** compares the dependency list against advisory databases, affected versions, and organizational policies. Scans can have false positives/false negatives, and new CVEs emerge after release; therefore, continuous monitoring is required, not just a one-time scan.

**Provenance/attestation** can verify claims about source, toolchain, builder, workflow, and artifact digest. However, the validator must check the **trust root, signer/builder identity, claim constraints, and digest**, not merely parse a JSON named `provenance`.

**Revocation:** An artifact that previously passed SHA-256 and signature checks can still be revoked after an incident or vulnerability discovery. The allowlist must have an update and audit mechanism: who removed the pin, why, which deployments are affected, and how to roll back/patch.

A strong policy will automatically reject a revoked release, even when its bytes still match an old pin — because **“correct bytes” does not mean “permitted today”**.

## 12. Do ClassLoader, ServiceLoader, and ModuleLayer Verify Trust?

**URLClassLoader** searches for classes/resources by URLs and parent delegation. It knows nothing about enterprise policies regarding JAR origin, signers, or artifact versions. Nor does `loader.getURLs()` represent all classes that could be received from its parent or other dynamic code sources.

**ServiceLoader** discovers providers registered in `META-INF/services` or `provides ... with ...` in a named module. That metadata can cause the framework to instantiate provider code. You must confirm that the service contract belongs to an approved API, that the provider class comes from an approved artifact/loader, and that the TCCL does not accidentally point to an old plugin.

**ModuleLayer** allows defining dynamic named modules according to a module graph. `ModuleFinder`, `Configuration.resolve`, and `defineModules...` perform module resolution/definition; they **do not automatically enforce publisher allowlists, integrity pins, or a security sandbox**.

**CodeSource/ProtectionDomain** can help debug which URL a class was loaded from:

~~~java
Class<?> type = /* an existing Class<?> */;
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "(unknown)"
        : source.getLocation());
~~~

This is a **fragment**, not a standalone program. `CodeSource` is useful for observability, not as a certificate of trust; a custom loader can assign metadata that does not reflect the full supply chain history. Bootstrap classes and dynamically generated classes may lack a clear physical URL.

**Do not use ClassLoader as a security sandbox.** A class loader organizes namespaces, type identity, and lookups. Plugins considered untrusted should run in an **isolated process/container** if you need to prevent access to secrets, the filesystem, the network, native code, or OS resources. OS permissions, network policies, resource limits, and monitoring are separate layers.

## 13. Anti-Patterns to Avoid

**“The JAR downloaded successfully over HTTPS, so it is trusted.”** Not necessarily. TLS protects the connection; it does not verify that the build/publisher has not been compromised.

**“The JAR's hash matches the hash in the file next to it, so it is safe.”** Not necessarily. If both come from a controlled source, an attacker can replace both.

**“jarsigner verify succeeded, so the signer is authorized.”** Not sufficient. You must validate signer/trust/coverage and policy; a valid signature does not by itself guarantee the code is non-malicious.

**“A SHA-256 match means there are no CVEs.”** False. A digest only binds the bytes to the pinned copy.

**“Only direct dependencies need to be allowlisted.”** False. You must review the **full closure**, including transitive, shaded, and runtime JARs and any related dynamic loading mechanisms.

**“A URLClassLoader with one URL will only use one JAR.”** Not guaranteed, because of the parent, manifest `Class-Path`, module/service lookup, and other runtime loading.

**“Having a Maven BOM means all bytes are locked.”** False. A BOM manages versions; it does not automatically pin all binary artifacts and publishing origins.

**“I can fix the error by falling back to another public repository on a SHA mismatch.”** False. Doing so breaks fail-closed behavior and creates opportunities for dependency confusion/downgrade.

**“An approved JAR is safe to run directly inside the host process.”** No. An artifact from the right origin can still have bugs, excessive permissions, or be exploited; runtime isolation/monitoring according to the threat model is needed.

**“Merely canonicalizing the path prevents file modification after the check.”** No. TOCTOU still exists if an untrusted writer can replace the bytes before the loader reads them.

## 14. Checklist Before Loading a Plugin JAR

1. Define the **threat model**: is the plugin as trusted as the host? If not, isolation beyond the class loader is required.
2. Allowlist **publisher/repository/group/artifact/version** and block namespace confusion.
3. Have a **signed/approved** release manifest binding the digest and dependency graph.
4. Compute SHA-256 over the **final artifact copy** and compare it against an **independent/trusted pin**.
5. If the policy requires a signer, validate the signature, trust chain, identity, and entry coverage.
6. Review **direct, transitive, runtime, shaded, and native** dependencies along with their versions/digests/sources.
7. Run **SCA** scans, compare the SBOM, and handle vulnerability/license policies.
8. Control manifest `Class-Path`, loader URL expansion, TCCL/SPI, and dynamic module loading.
9. Stage artifacts as **immutable/read-only**, with appropriate filesystem permissions and ownership; prevent TOCTOU.
10. Only then create the loader/module layer and run the plugin; preserve shared API class identity.
11. Log audit records for artifact ID, digest, origin, signer, policy version, allow/deny decision, and timestamp.
12. Have a plan for updates/revocation/rollback, shutting down plugin threads, and cleaning up TCCL and loader references.

## 15. Self-Check Questions

**Question 1.** A server serves both `plugin.jar` and `plugin.jar.sha256`, and the two files match. Does that prove the publisher origin is legitimate?

**Answer:** Not yet. Both could have been replaced at the same time. The hash pin must come from an independent trusted source/signed metadata.

**Question 2.** Why must transitive dependencies be allowlisted rather than only direct ones?

**Answer:** The runtime can load code from the entire resolved graph. An unapproved transitive artifact can still be executed.

**Question 3.** A JAR has a valid digital signature, but the signer is not in the policy. Should it be allowed to run?

**Answer:** No. A valid cryptographic signature does not automatically mean the publisher is authorized.

**Question 4.** A JAR has the right hash, yet contains `Class-Path: lib/extra.jar`. Is it guaranteed that only the first JAR will be used?

**Answer:** No. The manifest can expand the class/resource search path. You must either approve the auxiliary JAR or reject the Class-Path mechanism.

**Question 5.** Does checking `Path.toRealPath` before `URLClassLoader` prevent the file from being replaced before the loader reads it?

**Answer:** No. Immutable staging and controlled write permissions are needed to address TOCTOU.

**Question 6.** Can a plugin that passed the gate load a native library or call network APIs?

**Answer:** If the process has permissions, yes. A class loader is not a sandbox; OS/process isolation and network restrictions are required.

**Question 7.** Does a Maven BOM/Gradle lockfile guarantee that every artifact has a SHA-256 matching the policy?

**Answer:** Not automatically. Version locking and hash/signature verification are distinct control layers.

**Question 8.** Why must revocation be maintained even when the JAR digest has not changed?

**Answer:** Previously approved bytes may later be discovered to have a backdoor/CVE or a publisher compromise. “Matching the pin” does not mean it still remains permitted.

## Key Takeaways

**A valid origin, bytes matching the pin, and an allowed dependency graph are three independent conditions.** Before `URLClassLoader`/`ServiceLoader`/dynamic `ModuleLayer`, verify that the artifact comes from an approved repository/publisher, check SHA-256 against trusted metadata, check the signer when required, and verify all transitive/runtime dependencies and the final staged bytes. **Do not self-pin a hash from the untrusted JAR itself**, do not treat a signature as proof that the code is harmless, and do not treat a class loader as a sandbox. When in doubt, **fail closed**, audit, and use appropriate runtime isolation.

**Official documentation and reference guides:**

- Java SE 17 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `JarFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- JDK `jarsigner`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Java SE 17 API, `MessageDigest` and `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- OWASP Software Supply Chain Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html
- Gradle Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Maven Enforcer: https://maven.apache.org/enforcer/maven-enforcer-plugin/
