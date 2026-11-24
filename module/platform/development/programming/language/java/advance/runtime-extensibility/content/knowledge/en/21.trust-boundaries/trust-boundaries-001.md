# Evaluating the Provenance of JARs, Java Code, and Scripts Before Execution

## 1. Trust Boundaries of a Runtime Extensibility System

Plugin JARs, dynamically compiled Java source, and scripts can all introduce **third-party-supplied code** into a host application. The danger is that the gap between "discoverable" and "executable" is often just a single call to `ServiceLoader`, `Class.forName`, `JavaCompiler`, `JShell.eval`, or `ScriptEngine.eval`. The mere fact that a file appears in the plugin directory does not prove it is safe, authentic, or authorized to run.

Three questions must be separated:

1. **Provenance:** Who published the artifact, through which channel did it arrive, and does it belong to a publisher authorized by the organization?
2. **Integrity:** Do the received bytes match the approved version, or were they modified in transit, in the repository, or on disk?
3. **Authorization/Execution policy:** Even for an authentic and unaltered artifact, is this code allowed to run in a specific environment, and with what version, capabilities, and permissions?

**A signature or checksum does not prove that code is harmless.** An artifact may be signed by a trusted publisher yet still contain vulnerabilities, malicious code from a compromised publishing account, or behavior that violates host policy. Ensuring safety requires multiple layers of control before and during execution.

## 2. Three Types of Inputs That Require Different Evaluations

| Input | What to verify first | Specific risks |
|---|---|---|
| **Plugin JAR** | Publisher identity, hash/signature, dependency tree, class/module metadata, version | Class initialization, `ServiceLoader` provider constructors, native libs, class loader leaks |
| **Java source** | Submission source, commit/review, import/dependency policy, compiler options, build output | Annotation processors, generated sources, static initializers on class load, code that compiles cleanly but causes side effects at runtime |
| **Script** | Author, format, engine/version, input schema, host object permissions, API allowlist | `eval` accessing system resources, overload/proxy reflection, infinite loops, excessive resource consumption |

Do not assume text files are automatically harmless. `javac` can run annotation processors when enabled; JShell/script execution can invoke Java APIs or perform I/O depending on the permissions of the process and engine.

## 3. Control Pipeline from Artifact Receipt to Activation

```text
Receive artifact (quarantine, not yet loaded)
  -> Authenticate channel and publisher identity
  -> Compute hash / verify signature, provenance statement
  -> Check allowlist, version, dependencies, SBOM
  -> Scan for malware/SCA, apply risk-appropriate policy & review
  -> Immutable staging, restricted access permissions
  -> Pre-activation validation (metadata, API compatibility)
  -> Execution isolation and resource limits
  -> Observability, audit, revoke/rollback
```

All **non-code-executing** checks must complete before instantiating a plugin, triggering static initializers, or evaluating a script. For example, `Class.forName(name, true, loader)` can trigger class initialization; invoking a provider constructor is explicitly code execution. During the evaluation flow, even reading manifest/ZIP metadata alone must avoid arbitrary extraction or writing to uncontrolled paths.

### 3.1. Quarantine and Preventing Modification Between Verification and Loading

Store new artifacts in a staging area that cannot be read by the application class loader and whose contents cannot be modified by untrusted actors. After hashing/approval, **load the exact bytes that were verified**: copy them into an immutable artifact store or a versioned directory with appropriate ownership/permissions. If you verify file A and then load from a path that can be replaced, a race condition (TOCTOU) arises.

Do not accept a user-supplied path and pass it directly as a `URLClassLoader` input before validating the path, canonical location, symlinks, file type, and access permissions.

## 4. Verifying Integrity with SHA-256

SHA-256 is a cryptographic hash suitable for comparing contents against an **expected digest obtained from a trusted source**. If an attacker can replace both the JAR and the checksum file alongside it, the checksum provides no origin authentication. Therefore, the checksum must be tied to a release manifest, registry/artifact metadata, or an independent authenticated channel.

### Standalone Java 17+ Example

Create a file `VerifyJar.java`:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class VerifyJar {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java VerifyJar <file.jar> <expected-sha256>");
            System.exit(2);
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Not a regular file: " + jar);
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(jar)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        String actual = HexFormat.of().formatHex(digest.digest());
        String expected = args[1].toLowerCase(java.util.Locale.ROOT);
        if (!expected.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Expected SHA-256 must be 64 hex characters");
        }

        byte[] expectedBytes = HexFormat.of().parseHex(expected);
        byte[] actualBytes = HexFormat.of().parseHex(actual);
        boolean matches = MessageDigest.isEqual(expectedBytes, actualBytes);
        System.out.println("sha256: " + actual);
        System.out.println("verified: " + matches);
        if (!matches) System.exit(1);
    }
}
```

Compile and create a simple JAR with JDK 17+, running in a POSIX shell:

```bash
javac VerifyJar.java
mkdir -p demo-classes
printf 'hello\n' > demo-classes/README.txt
jar --create --file demo.jar -C demo-classes .
sha256sum demo.jar
```

Suppose `sha256sum` prints the actual digest `<DIGEST>` (64 hex digits); pass the **exact value from the command above**:

```bash
java VerifyJar demo.jar <DIGEST>
```

The output has the format:

```text
sha256: <DIGEST>
verified: true
```

`<DIGEST>` is a placeholder for the actual observed hash value, not literal fixed stdout. If you want to test a mismatch, pass a 64-character hex string that differs from the real hash; the program prints `verified: false` and exits with code 1. On Windows, you can compute the hash with `Get-FileHash demo.jar -Algorithm SHA256` and pass the result to the program.

**Limitation:** This example only verifies the file's bytes at the time of reading. It does not verify the signer, scan for malware, check certificates, or prevent TOCTOU if the loader later opens a file that could be replaced. In production, you should deploy an immutable store and prevent modifications to approved files.

## 5. JAR Signatures and Trust Policy

JARs can be signed using the JAR signing mechanism. Common JDK tools include `jarsigner` and `keytool`:

```bash
jarsigner -verify -verbose -certs plugin.jar
```

A JAR signature detects modifications to signed entries and provides signer information according to the Java JAR signing mechanism. However, verifying a technical signature is **different** from evaluating whether a publisher is trustworthy and still authorized.

The host needs clear policies:

- Accept only approved signers/public keys or certificate chains according to the trust policy.
- Check certificate validity, revocation, weak algorithms, and signing timestamps where applicable.
- Handle unsigned JARs, partially unsigned entries, multiple signers, and anomalous manifest files according to defined rules.
- Have procedures for key rotation, publisher revocation, and handling artifacts released before a key was compromised.
- Do not allow a valid signature to bypass version, dependency, and execution permission checks.

Do not mistake a single `jarsigner -verify` command for a complete supply-chain security system. In more mature pipelines, artifacts can be linked to build attestations/provenance, SBOMs, commits, CI identities, and immutable registries. That evidence must also be authenticated using trusted keys/identity policies.

## 6. Dependencies, Transitive Risk, and Provenance

A plugin may contain only a few custom classes while pulling in dozens of dependency JARs. You must inspect not only the main plugin, but **all dependencies loaded at runtime**:

- Artifact coordinates, version locks, and origin registries.
- Checksums/signatures for dependencies, including transitive dependencies.
- SBOM or actual dependency inventory (the link between components and build artifacts).
- Version-matched CVEs/advisories; scan results are a risk signal, not proof that code is clean.
- Licenses, provenance of build tools/plugins, and organizational policy.
- Dependencies shaded/bundled inside fat JARs, native binaries, and extracted resources.

Even with an isolated plugin loader, a dependency replaced with a different version can still introduce vulnerabilities while keeping the API contract unchanged. When using Maven/Gradle, lock versions, verify artifacts, and control repository mirrors in CI/CD. Avoid downloading arbitrary dependencies at runtime from URLs specified by a plugin without passing through verification gates.

## 7. Evaluating Java Source Before Compiling or Loading

Java source can be read and statically analyzed to detect suspicious imports or usages, but static checks are insufficient to prove safety. Reflection, dynamic class loading, native calls, and dependencies can make actual runtime behavior differ from what the source visibly shows.

Checklist for a runtime compilation system:

1. Receive source through an authenticated channel, attaching submitter/project ID, commit/hash, and language/API policy.
2. Validate paths, file count, size, encoding, symlinks, and allowed package namespaces.
3. Compile in an isolated environment with OS-level permissions and limits on CPU, RAM, time, disk, and network.
4. Specify the contract API class path/module path exclusively from approved artifacts.
5. Do not automatically allow annotation processors from source dependencies; if not needed, pass `-proc:none`.
6. Collect `Diagnostic` messages without exposing internal paths or secrets to the source submitter.
7. Approve the output bytecode/JAR under policy and store it in a versioned artifact store before activation.

Example `JavaCompiler` options:

```java
var options = java.util.List.of(
    "--release", "17",
    "-proc:none",
    "-encoding", "UTF-8"
);
```

This snippet is only a **configuration fragment**, not a standalone program. `-proc:none` disables annotation processing in compilers that honor this option; it does not make compiled code safe to execute. Compilation may also require compiler plugins or other build tools; every tool participating in the pipeline must be controlled.

## 8. Evaluating Scripts Before `eval`

A JSR 223 script engine can allow scripts to access host APIs, Java objects in bindings, files/networks, and native functionality depending on the engine. Even if a script is only a few lines long, `eval` can have severe side effects.

The host should:

- Authenticate script provenance: author, revision, checksum/signature, review status, and engine/version.
- Define a language/engine allowlist; reject engines not permitted by policy.
- Enforce schemas for inputs/outputs, and never place privileged objects (`ClassLoader`, `Runtime`, DB admin clients, credential stores) into bindings.
- Check permission/capability policies per tenant or plugin group.
- Use isolated processes/containers for untrusted scripts, restricting filesystem, network, CPU, memory, execution time, and OS user.
- Ensure logging/auditing does not leak sensitive content or script secrets.

### Pre-Evaluation Gate Example

```java
static Object evaluateApproved(
        javax.script.ScriptEngine engine,
        String script,
        java.util.Set<String> approvedHashes) throws Exception {
    java.security.MessageDigest digest =
        java.security.MessageDigest.getInstance("SHA-256");
    byte[] bytes = script.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    String hash = java.util.HexFormat.of().formatHex(digest.digest(bytes));
    if (!approvedHashes.contains(hash)) {
        throw new SecurityException("Script not approved");
    }
    return engine.eval(script);
}
```

This is an **illustrative snippet** inside a Java class that already has a live engine; it does not run standalone. It performs a hash check but does not isolate the script, and `approvedHashes` must be managed from a trusted source. Strings with identical visible content but different encodings/normalization can produce different hashes; the pipeline must standardize byte representation before signing/approving.

## 9. ClassLoader, ModuleLayer, and Boundaries That Are Not Sandboxes

A plugin may be loaded using `URLClassLoader`, `ServiceLoader`, or `ModuleLayer`. These tools organize dependencies and class identity; **they do not create OS permission boundaries**.

- A custom class loader can isolate library versions, but the plugin still runs inside the host JVM process with the same privileges unless another mechanism is present.
- JPMS `exports`/`opens` restrict module API/reflection access according to JVM rules, but they are not a mechanism for safely running arbitrary hostile code.
- The Java Security Manager has been deprecated for removal since Java 17 and should not be treated as the default sandbox layer for modern plugin systems.
- If untrusted code must be executed, use a subprocess/container/VM with OS permissions, seccomp/cgroup/namespaces, or equivalent platform mechanisms, and communicate over a capability-restricted protocol.

Distinguish between **isolation to avoid dependency conflicts** and **isolation to limit the impact of adversarial code**. A Java process running with the same host privileges can open files, establish network connections, or hog CPU even if its class loader is independent.

## 10. Decision Policies by Trust Level

| Scenario | Recommended policy |
|---|---|
| Internal plugin built from verified CI | Pin artifact, verify digest/signature, scan dependencies, test, and control release |
| Approved vendor plugin | Verify publisher identity, attestation if available, compatibility, capability allowlist, resource limits |
| Unreviewed community plugin | Do not execute in host JVM; require review and process isolation |
| User-uploaded Java source | Compile in an isolated worker, disable processors, inspect outputs, do not auto-activate |
| Script from untrusted tenant | Sandboxed process with minimal APIs/bindings, timeouts, and quotas |

Do not use a bare `trusted=true` boolean flag without provenance or expiration. A trust policy should have a version, approver, scope, expiration time, and revocation mechanism. In multi-tenant systems, a plugin's permissions must also be bound to the tenant context of the specific request.

## 11. Logging, Auditing, and Responding to a Compromised Source

Every activation should record at least: artifact ID/hash, signer/publisher ID, version, download source, policy decision, environment, dependency set, and startup outcome. Do not log private keys, secrets, or raw sensitive script inputs.

When a compromised key or malicious plugin is detected:

1. Revoke the ability to load/activate that version and all related artifacts.
2. Stop routing new requests to the plugin, clean up resources, and terminate worker processes as appropriate.
3. Preserve necessary evidence (hashes, logs, artifact metadata) per incident policy.
4. Determine the blast radius: data access, network activity, credentials, downstream systems.
5. Rotate credentials and roll back/redeploy from verified artifacts.

An effective revocation process must block **new activations**, not merely delete files from a registry. Running plugins may still retain code and state in memory; for adversarial code, isolating/stopping a separate process is far more reliable than merely closing a class loader.

## 12. Common Mistakes

| Mistake | Why it is dangerous | How to fix |
|---|---|---|
| Trusting a file because it is in `plugins/` | The directory could be written to by an attacker or a faulty pipeline | Quarantine, file ownership, artifact policy |
| Comparing SHA-256 against an unauthenticated `.sha256` beside the JAR | An attacker can replace both | Use digests from an authenticated registry/manifest |
| Running immediately if signed | The signer may not be allowlisted or the signed release may contain bugs | Verify signer trust, version, and policy |
| Scanning only the main JAR | Malicious dependencies go undetected | Scan/capture the entire dependency closure |
| Compiling source with uncontrolled processors | Processors can execute code during the build | `-proc:none` or processor allowlist in an isolated worker |
| Calling `Class.forName(..., true, ...)` before checking | Triggers static initializers of unapproved code | Validate the artifact before class initialization |
| Using a class loader as a sandbox | Does not restrict OS privileges | Process/container isolation |
| Failing to lock the artifact after verification | TOCTOU: loaded bytes differ from verified bytes | Immutable staged artifact, strict permissions |

## 13. Minimum Pre-Production Checklist

- [ ] Every JAR/source/script has a recorded artifact ID, origin, and hash.
- [ ] Hashes/signatures are verified against a trusted source and an allowlisted publisher.
- [ ] Dependencies and transitive artifacts are inspected, and versions are locked.
- [ ] No code is executed before policy checks complete, including class initialization, processors, and constructors.
- [ ] Verified artifacts are stored immutably to prevent TOCTOU.
- [ ] Class path/module path and API versions are controlled.
- [ ] Isolation and resource limits match the trust level.
- [ ] Audit logging, revoke/rollback, and compromise response plans are in place.

**Conclusion:** Evaluating code provenance before execution is more than checking a checksum. The host must prove that the artifact comes from an authorized source, the bytes have not been altered, dependencies/versions comply with policy, and the execution environment has appropriate boundaries. In particular, Java class loaders, module layers, `ServiceLoader`, and script APIs support runtime extensibility, but do not by themselves provide a sandbox for untrusted code.
