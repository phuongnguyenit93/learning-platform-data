# 11.3 Do Not Put Secret Keys in Source Code, Packages, or Logs

**Secret keys must not appear as directly usable values in source code, compiled code, deployment packages, or logs.** This is a foundational principle of the **key lifecycle**: keys must be generated, provisioned, used, rotated, and revoked through a control channel separate from application code.

This rule covers symmetric encryption keys (AES, HMAC), private keys of asymmetric key pairs, JWT signing keys, API tokens, database passwords, cloud credentials, webhook secrets, session keys, and other authentication secrets. A value named `password` or `key` is not necessarily a secret; conversely, an innocuous string granting production access is still a secret even if named `configValue`.

This lesson focuses on three commonly underestimated leak surfaces:

1. **Source code and version control history:** hard-coded literals, configs, fixtures, and commits.
2. **Packages and build pipelines:** `.class`, JAR/WAR, resources, container images/layers, CI/CD artifacts.
3. **Logs and observability systems:** logs, traces, dumps, requests/responses, exceptions, metrics, and support tools.

The goal is not merely “deleting a line containing a key,” but **designing so the exact same artifact can deploy to multiple environments without containing any environment's secrets**, while allowing keys to be revoked/rotated whenever needed.

## 1. Concepts: Secrets vs. Key References, Public Keys, and Metadata

| Item | Usually a Secret? | Recommended Handling |
| --- | --- | --- |
| **AES key / HMAC key / JWT signing secret** | **Yes.** | Keep in KMS/HSM or an appropriate secret manager; restrict usage permissions; never serialize to logs. |
| **Private key** | **Yes.** | Prefer non-exportable private keys when an HSM/KMS supports it; grant only required sign/decrypt permissions. |
| **API key / bearer token / DB password** | **Yes.** | Issue dynamically or fetch from a secret store; narrow scope, short lifetime, traceable and revocable. |
| **Password-hashing pepper** | **Yes.** | Store outside the password-verifier database, typically in a secret manager/HSM. |
| **Public key / public certificate** | Usually **no**. | Can be distributed publicly, but must verify trusted source, correctness, and lifecycle. |
| **Password hashing salt / AES-GCM IV** | Usually **no**. | Can be stored alongside the corresponding data; must still obey algorithm rules (such as nonce uniqueness). |
| **Key ID / version / alias** | Usually **no**, though it may be business-sensitive metadata. | Log only if policy allows; never confuse an ID with the actual secret. |
| **Path to a mounted secret** | Not the secret's content, yet may reveal system layout. | Keep in deployment configuration; never embed key values into paths or filenames. |

**Encoding does not make a secret safe.** Base64, hex, URL encoding, string concatenation, character reversal, or XORing with a constant and decoding at runtime only obscures it from casual human reading. If an artifact contains all the material needed to reconstruct the key, anyone holding the artifact can reconstruct it too.

**A hash of a secret is not automatically harmless.** For high-entropy random tokens, storing a digest can be an appropriate verifier. For low-entropy passwords, a fast hash does not replace a password KDF. A hash can still enable record correlation, identification, or offline attacks depending on context. Never log a hash/digest of a secret just to “prove it was masked.”

## 2. Threat Model: Three Places Secrets Can Be Copied

~~~text
Developer / secret management system
          |
          +-- SOURCE REPO ---------------------+
          |   Java literals, YAML, .properties, .env,
          |   test fixtures, Git history, pull requests,
          |   forks, clones, code reviews, caches
          |
          +-- BUILD / PACKAGE -----------------+
          |   .class, JAR/WAR, resources, fat JAR,
          |   Docker images/layers, build arguments,
          |   CI logs, artifacts, SBOM metadata
          |
          +-- RUNTIME / OBSERVABILITY ---------+
              System.out, SLF4J/JUL, HTTP debug,
              APM spans, crash/heap dumps, traces,
              exception messages, request snapshots

Copies in these places can persist long after source code is fixed.
~~~

Do not inspect only `src/main/java` and conclude the application is safe. Risk lives in **every place the secret passed through**, not just where the developer is currently looking.

### 2.1. Why Is a Private Repository Still Not a Secret Vault?

A private repository limits access to some people, yet does not replace secret management because:

- Many developers, CI runners, bots, analysis tools, forks, and local clones can read its history.
- Pull requests, diffs, notifications, or review tools may retain separate copies.
- Someone authorized to read code **is not necessarily** authorized to use production API keys.
- Once a secret is committed, deleting it in a later commit **does not erase the earlier commit**; history, tags, branches, clones, and artifacts may still contain it.
- If the repository was ever public or a token was sent over an external channel, assume the secret may have been exploited.

Treat any real secret appearing in Git as a **secret exposure incident requiring assessment and rotation/revocation**, not merely a code-style issue.

## 3. Do Not Hard-Code Keys in Java Source Code

### 3.1. Anti-Pattern: Secret Literals in Code

**Bad example — using placeholder strings only, no real credentials:**

~~~java
// ANTI-PATTERN: do not implement like this.
private static final String DB_PASSWORD = "DEMO_NOT_A_REAL_PASSWORD";
private static final String API_TOKEN = "DEMO_NOT_A_REAL_TOKEN";

// No safer: secret assembled at runtime.
String token = "DEMO_" + "NOT_A_REAL_TOKEN";
~~~

In real code, such constants can live in source, Git history, and `.class` bytecode. Visibility `private`, `static final`, or packaging in an internal library **provides no cryptographic protection**.

Variants that remain wrong:
- Storing secrets in source as Base64 and calling `decode` at startup.
- Splitting a secret into fragments across classes and concatenating them.
- “Encrypting” a secret inside resources while placing the **decryption key** in the same artifact.
- Hiding passwords inside annotations, enums, unit tests, test resources, or SQL migrations.
- Leaving a fallback production secret in code when the secret store is unreachable.
- Committing an `application.properties` or `application.yml` containing real keys, even if used only in one environment.
- Using environment variables while **assigning real values inside committed Dockerfiles, startup scripts, or pipeline YAML**.

A repository may contain **configuration names, key references, structural schemas, and dummy example values**. It should not contain live secrets.

### 3.2. Distinguishing Reference Configuration from Secret Values

**Example config containing identifiers only, no secrets:**

~~~yaml
security:
  crypto-key-ref: payments/data-key/current
  token-secret-ref: payments/api-token/current
  key-policy: AES-GCM-128
~~~

`payments/data-key/current` is a **mock alias/reference** for illustration. In a real system, the application uses its granted identity to call the KMS/secret manager, obtain a short-lived secret, or request the service to execute cryptographic operations **without exporting raw keys**.

The difference:

~~~text
Wrong:
  application.yml contains raw AES key or API token
  code reads YAML and uses raw secret

Right direction:
  application.yml contains reference, algorithm policy, key version
  workload identity -> KMS/secret manager -> appropriate permissions
  app receives secret only when genuinely required, never logs the value
~~~

Do not put **credentials for accessing the secret manager** into the same source; doing so only shifts hard-coding down one layer. Use workload identity, managed identity, environment-scoped service accounts, or verified trust/bootstrap mechanisms.

### 3.3. `.gitignore` Is Not a Solution for Already-Committed Secrets

`.gitignore` only tells Git **not to automatically track untracked files** matching a pattern; it does not make an already-tracked file disappear from history. Nor does it control files copied into JARs, ZIPs, or Docker images.

A sensible usage pattern:

~~~gitignore
# Example policy to ignore local configs containing secrets
.env
.env.*
!.env.example
local-secrets/
*.local.properties
~~~

Still, you must **audit build configurations**: a file outside Git can still be swept into a package by `processResources`, Docker `COPY . .`, or other artifact assembly steps. `.env.example` should contain **variable names and descriptions**, never active secrets. Never use real production data as test fixtures.

Safe configuration files must go through code review/scanning. Avoid the heuristic “it is under `test/` so it is fine”; CI artifacts and test reports can also be downloaded.

## 4. Secrets Can Leak in `.class`, JAR/WAR, and Container Images

### 4.1. Compiled Java Remains Inspectable

When code contains a string literal, the compiler may place that string in the constant pool or other bytecode structures. Anyone possessing the `.class`, JAR, or runnable app can use inspection/decompilation tools to recover unprotected values.

- JAR/WAR archives are packaged formats whose entries and resources can be listed and extracted.
- `application.properties` in `src/main/resources` normally becomes an artifact resource unless excluded by the build.
- `static final` makes a field immutable at the Java language level, not an analysis-resistant secret vault.
- Obfuscation, minification, shading, or building a “fat JAR” is no substitute for key management.
- JAR signing/code signing proves integrity/publisher origin under a trust model; it **does not encrypt** JAR contents.

Artifact inspection commands you can run on **builds owned by your team**:

~~~bash
jar tf application.jar
javap -verbose -classpath application.jar com.example.AppConfig
~~~

`jar tf` lists JAR entries; `javap -verbose` inspects bytecode/constant pools in the target class. They cannot prove all secrets are absent: secrets can hide in resources, native libraries, image layers, other artifacts, or dynamic construction. Use proper secret scanning systems rather than manual visual checks alone.

### 4.2. Docker Image Layers, Dockerfiles, and Build Arguments

**Anti-pattern:**

~~~dockerfile
# WRONG: do not replace these with real credentials.
ARG APP_SECRET=DEMO_NOT_A_REAL_SECRET
ENV APP_SECRET=DEMO_NOT_A_REAL_SECRET
COPY local-secrets/ /app/secrets/
~~~

Consequence: the value or file may persist in build definitions, image configuration/metadata, filesystem layers, or build caches. Deleting a file in a later `RUN` instruction or layer **does not guarantee** removal from earlier layers, caches, or registries.

Better practices:
1. Built images **contain no environment secrets**.
2. Mount/provision secrets **only at runtime** via platform secret stores, protected volumes, or SDKs.
3. If a build genuinely requires a secret, use **dedicated build secret mounts** (e.g., BuildKit secret mounts) and verify the command does not copy or log the secret into output layers, caches, or build artifacts.
4. Do not pass secrets via Docker `ARG`/`ENV` in image definitions for build convenience.
5. Inspect image layers, base images, artifacts pushed to registries, and pipeline logs.
6. Restrict secret read access to the exact workload; a mounted secret is still at risk if the container/service is compromised.

**Putting encrypted secrets into an image** only makes sense when decryption/key management is properly designed and the decryption key **does not reside in the same image**. For most applications, there is no reason to place secrets in artifacts at all.

### 4.3. CI/CD and Secondary Leak Channels

- Pipeline YAML, deployment scripts, command lines, and shell histories can retain secrets. Passing credentials via command arguments such as `-Ddb.password=...` can expose them in process lists/diagnostics/logs; avoid whenever safer provisioning exists.
- CI/CD logs can surface `echo`, `set -x`, stack traces, third-party command error messages, or environment dumps.
- CI secret masking is a **secondary defense**: encoded/transformed/split secrets, multiline formats, and misconfigurations can bypass masking.
- Debug artifacts, test reports, screenshots, coverage uploads, crash dumps, build caches, and SBOM metadata can all contain unintended data.
- Workflows triggered from untrusted PRs/forks must never receive production secrets without strict isolation and approval policies.
- Never share the same high-privilege credential across all pipelines, dev/staging/prod environments, or every microservice.

Secrets issued to pipelines should have **narrow scope, short TTL**, appear only in jobs that need them, be audited, and be revocable. For cloud integrations, prefer **federated workload identity / short-lived credentials** over hard-coded long-lived tokens in CI whenever supported.

## 5. Do Not Log Secret Keys or Write Them to Observability Systems

Logs are replicated widely: container stdout, log aggregators, shipper agents, SIEM, APM, distributed tracing, alerts, attached tickets, and backups. People authorized to read logs **are not necessarily** authorized to read private keys or production tokens.

### 5.1. Java Anti-Patterns

~~~java
// WRONG: illustrative examples only; never put in production.
logger.info("apiToken={}", apiToken);
logger.debug("AES key={}", Arrays.toString(keyBytes));
logger.info("Auth header={}", request.getHeader("Authorization"));
logger.error("Connection string: {}", connectionUrlWithPassword);
System.out.println(secretKey.getEncoded());
~~~

There are also **indirect risks**:

- `logger.debug("request={}", request)` when the object's `toString()` includes the Authorization header, password, or body.
- Logging full HTTP requests/responses in filters/interceptors, reverse proxies, or HTTP client wire debugging.
- Serializing config objects to JSON into logs, trace span attributes, or MDC/ThreadContext.
- Logging `Throwable.getMessage()` or library stack traces containing `user:password@host` URLs, connection strings, or token values.
- Logging failed OAuth callbacks, password reset URLs, or query strings carrying credentials.
- `printStackTrace()`, crash dumps, heap dumps, and profilers can capture in-memory copies of secrets; restrict access, retention, and storage locations.
- Logging a digest/partial secret in a way that enables linking sensitive data or lets outsiders identify which credential is in use.
- Logging full HTTP request bodies on validation errors, including requests containing passwords, OTPs, or bearer tokens.

Never print raw keys even when “just running locally once.” Local consoles can be captured by IDEs, terminal logs, screen sharing, CI, and system logs.

### 5.2. Replace Value Logging with Allowlisted Event Logging

A useful event for monitoring the key lifecycle might contain:

| Field to Consider | Purpose | Notes |
| --- | --- | --- |
| `event=key_use` | Distinguish secret access, rotation, denial, revocation. | Do not include raw keys. |
| `request_id` / correlation ID | Correlate traces across services. | Must be generated independently; never embed tokens. |
| `key_ref` or approved key version | Identify which alias/version had issues. | Include only if permitted by metadata policy. |
| `operation=encrypt/decrypt/sign` | Observe operation type. | Never log plaintext or content being signed. |
| `outcome=success/denied/error` | Analyze failures and anomalies. | Do not rely on printing exceptions containing secrets. |
| Standardized `error_code` | Diagnose without exposing internals. | Avoid uncontrolled free-form library messages. |

Rule: **log only pre-approved fields (allowlist)** instead of serializing whole objects and trying to strip sensitive fields (denylist). Identifiers must also be validated/normalized to prevent log injection and avoid embedding attacker-controlled data.

**Never treat redaction as absolute.** Secrets can appear inside encoded strings, nested JSON, multiline messages, or undefined fields. Minimal logging at the source is far more reliable than masking after logs have spread.

### 5.3. Java 17+: Safe Auditing Without Printing Secrets

The file **`AllowlistAuditDemo.java`** generates a random byte array **solely to illustrate an in-memory secret**. The program outputs an event with selected fields and never passes the secret array into the formatter. This is not a secret-manager SDK and does not demonstrate a full authentication workflow.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

public class AllowlistAuditDemo {
    static String safeEvent(
            String requestId, String keyReference, String outcome) {
        return "event=key_use request_id=" + requestId
                + " key_ref=" + keyReference + " outcome=" + outcome;
    }

    public static void main(String[] args) {
        byte[] demonstrationOnly = new byte[32];
        new SecureRandom().nextBytes(demonstrationOnly);
        try {
            if (demonstrationOnly.length != 32) {
                throw new IllegalStateException("Invalid demonstration material");
            }

            System.out.println(
                    safeEvent("req-001", "demo-key-v1", "success"));
        } finally {
            Arrays.fill(demonstrationOnly, (byte) 0);
            System.out.println("Buffer cleared: "
                    + Arrays.equals(demonstrationOnly, new byte[32]));
        }
    }
}
~~~

~~~bash
javac AllowlistAuditDemo.java
java AllowlistAuditDemo
~~~

Exact stdout:

~~~text
event=key_use request_id=req-001 key_ref=demo-key-v1 outcome=success
Buffer cleared: true
~~~

**Explanation:** `demo-key-v1` is only a mock reference and the fields are explicitly allowlisted. The program never prints the 32-byte secret; `Arrays.fill` actively overwrites **the application-controlled byte array**, which does not mean every copy of a secret in the JVM, native memory, swap, or other libraries has been erased. There is no general Java mechanism guaranteeing every secret has been wiped from all memory locations.

A real system should validate the length, structure, and safety of `requestId`, `keyReference`, and `outcome` before logging so attackers cannot inject newlines or sensitive content into those fields.

## 6. Proper Secret Provisioning Architecture: Separate Packaging from Environment

Recommended practice model:

~~~text
[Git repository]                  [CI/CD build]
  code, schema, key references ---> compile/test/package
  no raw secrets                      |
                                      v
                              [Secret-free Image/JAR]
                                      |
                                      v
                      [Runtime: workload identity/service account]
                                      |
                                      v
                         [Secret Manager / KMS / HSM]
                          IAM, version, audit, TTL, rotate
                                      |
                         +------------+------------+
                         |                         |
           key handle / encrypt operation    runtime short-lived secret
             non-exportable private key       issued only when needed
                         |                         |
                         +------------+------------+
                                      |
                                [Application]
                   only permitted operations; never log secrets
~~~

A system does not necessarily have to **load raw AES/private keys into the JVM**. With an HSM/KMS, the application can call **sign/decrypt/encrypt/wrap** APIs so private/master keys never leave hardware or the service. If the system needs a data key in memory for local encryption, it must govern lifetime, issuance permissions, nonces, memory handling, rotation, and wiping erasable copies per policy.

### 6.1. Secret Provisioning Options

| Option | Advantages | Limitations / Risks |
| --- | --- | --- |
| **KMS/HSM key handle** | Limits key export, centralizes audit and policy; app invokes operations rather than receiving raw keys when supported. | Provider/latency/quota dependency; requires IAM and key version/recovery management. |
| **Secret manager via SDK** | Delivers secrets per identity, version, TTL, and audit; centralized rotate/revoke. | Raw secrets may still enter process memory; protect caches, logs, retries, and exceptions. |
| **Runtime secret volume/file mount** | Avoids baking secrets into JARs/images; works across many frameworks. | Needs ACLs, namespaces, volume policies, and rotation/mount refresh handling. Files remain readable if the workload is compromised. |
| **Runtime-injected environment variable** | Easy to configure across platforms; avoids hard-coding in source. | Values can appear in process environments, diagnostics, dumps, child processes, and logs; not the safest default channel for every secret. |
| **External encrypted config** | Useful when decryption keys and permissions are managed separately. | If the same artifact contains ciphertext **and** the decryption key, protection is nearly meaningless. |
| **Startup-generated ephemeral key** | Suitable for session/ephemeral keys needing no persistence; avoids long-term key storage. | Unsuitable for data that must be decrypted after restart without proper key storage/retrieval. |

Choose based on your threat model and compliance requirements. **Environment variables are better than hard-coding in source** for separating configuration from artifacts, yet they are not automatically equivalent to a secret manager/HSM; prefer SDK/workload identity or controlled secret mounts whenever possible.

### 6.2. Do Not Hard-Code Credentials Used to Fetch Secrets

Common bootstrap mistake:

~~~text
App wants to fetch DB password from secret manager
  -> hard-code SECRET_MANAGER_ADMIN_TOKEN in source
  -> call secret manager using that token

Result: production secret is still embedded, merely moved to another layer.
~~~

The right approach is using a **workload identity** issued by the runtime environment and verified by the platform. Permissions must be restricted by secret name, version, operation, environment, and tenant where appropriate. Never reuse the same secret-store admin credential across every service.

### 6.3. Secret Rotation Is More Than Restarting the App

- **Static secrets** typically require creating a new version, updating consumers, and disabling the old version in a safe sequence.
- **Dynamic credentials** expire by lease; refresh them on time and stop access automatically if a lease is revoked.
- Restarting only makes a process pick up a new secret **if the app is designed to do so**; it does not invalidate an exposed old key or clear all copies/cached artifacts.
- For encryption keys, manage **key ID/version**, allow legacy data to be decrypted during the transition window, plan re-encryption, and enforce retention of old keys. Never delete an old key while recoverable data still depends on it without a migration plan.
- For exposed API tokens or passwords, generally **revoke/rotate as soon as feasible** and update dependent systems per incident procedure.

## 7. Java 17: Obtaining Secrets at Runtime Without Putting Them in Source

### 7.1. No Universal Java API Exists for Every Secret Manager

Standard Java provides `KeyStore`, `KeyGenerator`, `Cipher`, `SecureRandom`, and related APIs, yet **no single JDK call** queries every cloud secret manager. Applications use vendor SDKs/plugins or configured JCA/JCE/PKCS#11 providers.

Integration mindset:

~~~text
Non-secret config: keyRef, algorithm, tenant, policy
      |
Workload identity (no embedded API key)
      |
Secret manager / KMS / HSM SDK or JCA provider
      |
Secret lease / key handle / permitted sign-encrypt action
      |
Use -> audit metadata -> release/expire
~~~

**Architectural pseudocode**, not real SDK classes:

~~~text
keyRef = config.getApprovedKeyReference()
identity = runtime.getWorkloadIdentity()
handle = keyService.openKey(identity, keyRef, allowedOperation="encrypt")
ciphertext = handle.encrypt(plaintext, authenticatedMetadata)
audit(event="key_use", keyRef=keyRef, outcome="success")
close handle/lease; never print raw keys to any log
~~~

If using an HSM provider to create `SecretKey`/`PrivateKey`, the key object may be an **opaque handle** and `getEncoded()` may return `null`. Never force calling `getEncoded()` to log, serialize, or clone a key; some providers protect keys precisely by forbidding export.

### 7.2. When Receiving Secrets as Bytes/Chars Is Unavoidable

- Avoid converting secrets into `String` if the API supports short-lived `byte[]` or `char[]`. `String` is immutable and GC reclamation does not guarantee immediate memory clearing.
- Use `try/finally` or `AutoCloseable` to overwrite temporary arrays with `Arrays.fill` after use; however, **do not claim absolute zeroization**, as copies can remain in providers, native memory, dumps, and the JVM.
- Never call `new String(secretBytes)` just for logging or debugging.
- Never convert secrets to Base64 to store in configs or stdout: Base64 is **encoding**, not encryption.
- For runtime-mounted secret files, restrict read permissions to the intended principal; protect file/volume permissions, enforce input size bounds, and handle missing files by **failing closed**, never falling back to embedded values.
- Never pass passwords in command-line parameters because process lists and shell histories can capture them; avoid unsafe shell passthroughs.

A method reading a runtime-provisioned file might look like this; it is an **integration snippet**, not a standalone program, and does not replace secret-manager authentication/authorization:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

static void withMountedSecret(Path mountedFile) throws IOException {
    byte[] secret = Files.readAllBytes(mountedFile);
    try {
        if (secret.length == 0) {
            throw new IllegalStateException("Required secret is empty");
        }
        // Real application uses the secret inside its configured SDK.
        // Do not print the secret or promote it to a global config variable.
    } finally {
        Arrays.fill(secret, (byte) 0);
    }
}
~~~

This snippet only illustrates **receiving a secret and wiping the buffer afterward**; production usage must also add size limits, path validation, ACLs, format checks, and real operations. Never create secret files inside the repo to “simulate a runtime mount.” The file path should be configured separately and never taken directly from user input.

### 7.3. Environment Variables: Practical Limitations

~~~java
String secret = System.getenv("SERVICE_API_TOKEN");
if (secret == null || secret.isBlank()) {
    throw new IllegalStateException("Service credential is not configured");
}
// Use through configured client; never log, never return in errors.
~~~

This is an **illustrative snippet** containing no secrets or client implementation. `System.getenv` returns a `String`, meaning you cannot actively wipe its value from every JVM location. Environment values can also leak via platform config UIs, crash dumps, process debugging, or careless logging.

Do not allow:

~~~java
// WRONG: hard-coded fallback secret (string below is a mock placeholder).
String token = System.getenv().getOrDefault(
        "SERVICE_API_TOKEN", "DEMO_NOT_A_REAL_TOKEN");
~~~

If a mandatory secret source is unavailable, **refuse startup or reject the operation** by design; never fall back to static credentials.

### 7.4. Does `KeyStore` Solve Everything?

`KeyStore` helps manage key/certificate objects according to store type and provider, but **it does not make a file paired with a hard-coded password secure**. If an application JAR bundles both an exportable keystore and its unlock password, anyone holding the artifact can extract the secrets.

An HSM/PKCS#11 provider can represent keys via non-exportable handles; real protection depends on how keys are generated, key policy, PIN/session handling, hardware, provider, and workload permissions. Distinguish `KeyStore` as an API/abstraction from a **complete secret management system**.

## 8. Java 17+: Generating Ephemeral Keys Without Embedding or Logging Key Values

The example **`InMemoryKeyDemo.java`** demonstrates an AES key randomly generated at runtime solely to encrypt/decrypt immediately within the process. The program uses no hard-coded key bytes, never calls `key.getEncoded()` to print the key, and logs only non-secret metadata.

**This is an ephemeral key for learning.** Data that must be decrypted after a restart requires proper key storage/management in a KMS/keystore or key wrapping; never substitute hard-coded keys in source code.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class InMemoryKeyDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey ephemeralKey = generator.generateKey();

        byte[] iv = new byte[12];
        random.nextBytes(iv);

        byte[] message = "example".getBytes(StandardCharsets.UTF_8);
        Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
        enc.init(Cipher.ENCRYPT_MODE, ephemeralKey,
                 new GCMParameterSpec(128, iv));
        byte[] ciphertextAndTag = enc.doFinal(message);

        Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
        dec.init(Cipher.DECRYPT_MODE, ephemeralKey,
                 new GCMParameterSpec(128, iv));
        byte[] restored = dec.doFinal(ciphertextAndTag);

        System.out.println("Algorithm: "
                + ephemeralKey.getAlgorithm());
        System.out.println("IV bytes: " + iv.length);
        System.out.println("Ciphertext+tag bytes: "
                + ciphertextAndTag.length);
        System.out.println("Round-trip OK: "
                + Arrays.equals(message, restored));
    }
}
~~~

~~~bash
javac InMemoryKeyDemo.java
java InMemoryKeyDemo
~~~

Verified stdout:

~~~text
Algorithm: AES
IV bytes: 12
Ciphertext+tag bytes: 23
Round-trip OK: true
~~~

Explanation:
- `KeyGenerator.getInstance("AES")` creates **fresh key material from a CSPRNG**, with no literal AES key in source.
- `generator.init(128, random)` specifies a 128-bit AES key; that is **not** the IV size.
- `IV` is 12 bytes generated from `SecureRandom`. This lesson performs only one encryption; in real systems, AES-GCM **must never repeat a (key, IV) pair** across any encryptions under the same key, including across nodes and restarts.
- `doFinal(message)` produces 7 bytes of ciphertext + 16 bytes of authentication tag (tLen=128 bits), totaling 23 bytes; no plaintext or actual key is printed beyond the non-sensitive demo string.
- `key.getAlgorithm()` returns the algorithm name (metadata); this does not verify access rights or keystore security.
- The program **does not persist the key**, so it cannot keep ciphertext decryptable after the process exits. For long-lived keys, proper KMS/HSM/keystore configuration and version/rotation management are mandatory.

### Why Not Log `SecretKey.getEncoded()`?

For exportable keys, `getEncoded()` typically returns raw secret bytes; printing `Base64.getEncoder().encodeToString(key.getEncoded())` to the console **exposes the key**. For non-exportable keys, `getEncoded()` may return `null`, so forcing byte extraction or assuming keys are always exportable is wrong. Never arbitrarily log `SecretKey` objects either, as a provider may include unwanted metadata or representations in `toString()`.

## 9. Development, Build, Test, Operations: Which Controls Apply at Each Stage?

| Stage | Risk | Appropriate Controls |
| --- | --- | --- |
| **Design** | Broadly shared secrets, excessive lifetimes, no owner | Owner/purpose/scope inventory, least privilege, rotation/revocation policy. |
| **Coding** | Hard-coded credentials in Java/config/tests/fixtures | Secret references, harmless dummy fixtures, code review, linters + pre-commit scanning. |
| **Git push / pull request** | Secrets entering history and snapshots/forks | Server-side push protection/secret scanning, branch policy, bots that do not expose credentials. |
| **CI build** | Pipeline printing variables, artifacts containing secrets, over-privileged jobs | Short-lived identities, runner isolation, additional masking, artifact scanning, avoiding secret-bearing commands. |
| **Package/JAR** | Secrets slipping into `.class`, resources, manifests, fat JARs | Audit dependencies/resources, reproducible builds needing no prod secrets, package scanning. |
| **Container image** | Dockerfile ENV/ARG, improper secret mounts, layers/caches | Runtime injection, dedicated BuildKit secret mounts if needed at build time, inspect layers/registries/caches. |
| **Runtime** | Secrets in dumps, process env, world-readable files | Workload identity, KMS/HSM, ACL-protected runtime mounts, restricted dumps/debug and process permissions. |
| **Observability** | Printing full requests, Authorization headers, SDK exceptions, traces | Allowlist logging, redaction, disabling sensitive wire debug, log retention and ACLs. |
| **Rotation** | Old keys stay active, rollbacks use old versions | Versioned secrets, TTL, revocation, migration plans, tracking consumer adoption. |
| **Incident** | Deleting secret from code only while credential remains valid | Revoke/rotate, scope investigation, controlled cleanup of copies/artifacts, audit & alerting. |

### 9.1. What Secret Scanning Can and Cannot Do

Scanners can detect API key patterns, private-key blocks, credential literals, anomalous entropy, and sensitive filenames. Run them at multiple points: pre-commit, PR/CI, source history, artifact/image scanning, and log monitoring where policy permits.

However:
- **False negatives**: Base64/hex-encoded secrets, split fragments, dynamically constructed values, custom formats, or copies outside scan scope.
- **False positives**: test/dummy strings or high-entropy non-secret data.
- A scanner finding a secret does not automatically **revoke** it. Real hits must trigger an incident workflow.
- Never print the discovered raw secret into **scanner reports** or issues/tickets.
- Compute/display only safely designed fingerprints when deduplication is needed; do not assume every hash is harmless.

A common practice is **blocking merges/commits when secrets are detected**, adding periodic artifact scans, and assigning clear owners per credential class.

### 9.2. Access Control and Multi-Environment Isolation

Never share one production key across dev/staging, QA, and CI. A neutral build artifact can run in every environment by receiving **distinct runtime identities and secret references**. If staging has a vulnerability, that breach must not automatically grant access to production.

Apply least privilege: services should only `read` scoped secrets or `encrypt/sign` using assigned key handles; never grant `list/all`, `delete`, `rotate`, or `export` across all keys by default. Build runners also do not need permission to decrypt production data just because they package code.

## 10. If an Exposed Key Is Discovered: Order of Operations

**Scenario:** a developer once committed an API token or AES key, then deleted that line on the branch and made a new commit. The deleted line does not guarantee the secret was never copied.

### Practical Incident Response Workflow

1. **Triage and notify per internal procedure.** Identify what the secret is, owner, permission scope, environment, creation date, and all potential exposure surfaces (repo, artifacts, logs, CI caches, tickets, dumps).
2. **Isolate/revoke or rotate as soon as feasible.** For tokens/API keys, revoke/replace so the old secret can no longer be used. For private/signing/encryption keys, plan key replacement, adjust trust/certificates, and re-sign/re-encrypt data if needed; watch out for losing ability to decrypt legacy data.
3. **Inspect access logs and usage history** to determine if unauthorized use occurred; do not re-fetch or log the raw secret during investigation.
4. **Update consumers in a controlled rollout**, confirming every service uses the new version and no longer depends on the old credential; prevent silent fallback to the exposed key.
5. **Clean up leak traces** in source history, PRs, artifacts, Docker registries/caches, logs, backups, and copies according to an approved plan. Rewriting Git history can break commit references and requires coordinating all clones; **it does not replace revocation**.
6. **Post-incident monitoring**: alert on attempts to use the old credential, unusual failures, old key version access, resource abuse, or authorization bypasses.
7. **Prevent recurrence**: strengthen scanners/branch policies, remove secrets from builds, audit loggers, tighten IAM, shorten TTLs/automate rotation, and educate developers.

Do not unilaterally delete logs/audit records before satisfying investigative or legal requirements; coordinate with security/incident response to isolate, restrict access, and purge sensitive copies while preserving necessary evidence.

### When Does Rotate Differ from Revoke?

- **Rotate**: issue a new secret, migrate consumers to the new version, then disable/restrict the old version per policy.
- **Revoke**: invalidate the old secret immediately or within system propagation bounds. During an exposure incident, revocation may need priority if active exploitation is plausible.
- **Expire**: a value automatically ends by TTL/lease; this does not mean an incident is resolved while the secret remains valid.
- **Re-encrypt/re-wrap**: when an encryption key is compromised, simply replacing an API token does not protect data encrypted under the old key; assess the full blast radius.

Never promise “deleting a secret from Git makes it 100% safe”: when you cannot control every copy, **render the old secret useless** and mitigate remaining risks.

## 11. Comparison Table: Wrong Practices and Proper Replacements

| Wrong Practice | Security Problem | Replace With |
| --- | --- | --- |
| `static final String AES_KEY = "...";` | Key embedded in source/bytecode. | Provision keys via KMS/HSM or secret manager/runtime key handles. |
| Storing Base64 secret in properties | Anyone reading properties can decode it. | Keep secrets out of artifacts; use controlled runtime injection. |
| Bundling keystore + keystore password in same JAR | Artifact holds everything needed to unlock keys. | Keep keystore outside artifacts, use key-handle/HSM, separate password/identity. |
| Adding `.gitignore` after committing | Does not remove secret from history/clones. | Revoke/rotate and handle copies per incident plan; add ignore/scanning. |
| Docker `ARG`/`ENV` holding raw secrets at build time | Secrets may remain in image metadata/layers/caches. | Dedicated build secrets only if strictly required and verify output; prefer runtime injection. |
| `logger.debug("config={}", config)` | May serialize full passwords and tokens. | Log allowlisted event fields; never log sensitive objects. |
| Enabling HTTP wire logging in production | Authorization headers/bodies may be broadcast. | Keep logging minimal, redact, and disable sensitive wire logs. |
| Catching errors and printing raw `exception.getMessage()` | SDK error messages may include requests/URLs/secrets. | Standardized error codes, controlled logging, trace IDs, log protection. |
| Passing credentials via `-Dtoken=...` to JVM | Exposed via process lists, shell histories/diagnostics. | Safer runtime injection, file mounts, or SDKs. |
| Sharing the same secret across dev and prod | Lower-environment breach spreads to prod. | Isolate identities, secret scopes, rotation, and permissions per environment. |
| Falling back to embedded key when KMS fails | Fail-open using hard-to-manage/exposed keys. | Fail-closed with alerts; zero fallback secrets in code. |
| Only deleting the hard-coded line after discovery | Old secret remains valid and may live in history/artifacts/logs. | Revoke/rotate, audit all leak surfaces, and monitor post-incident. |
| Printing a partial API key for debugging | Can leak useful info and link logs to secrets. | Use policy-approved key references/versions or separate correlation IDs. |
| Password-protected KeyStore = “already secure” | Password/key may sit in same artifact, overly broad read access, or exposed backups. | Audit all storage and consumption points; use proper HSM/KMS/ACLs. |

## 12. Pre-Release PR/CI Checklist

### Developer Checks

- [ ] No **live secrets** in Java source, Kotlin, properties, YAML, JSON, SQL migrations, test fixtures, or READMEs.
- [ ] `.env` and local secret configs are untracked, while understanding ignoring **does not fix history**.
- [ ] No secrets in command lines, Gradle/Maven tasks, Dockerfile `ARG`/`ENV`, or script outputs.
- [ ] All production secrets come from identity/secret manager/runtime injection, **with no hard-coded fallbacks**.
- [ ] No `println`/`logger`/`toString`/JSON serialization/exception messages leaking keys, passwords, Authorization headers, or tokens.
- [ ] Never log raw `SecretKey`, `PrivateKey` objects, or `getEncoded()`.
- [ ] All tests use **invalid dummy credentials**; test data is never reused in production.
- [ ] Key aliases/versions, rotation, read/operation permissions, and ownership are defined.

### Build / Security / Ops Checks

- [ ] Pre-commit/PR scanning and CI checks block exposed credentials; findings are triaged without re-broadcasting secret contents.
- [ ] JAR/WAR/resources/image layers/artifacts are inspected and contain no environment secrets.
- [ ] Pipelines have least-privilege access; secrets are issued only to jobs that genuinely need them, never to untrusted PRs/forks.
- [ ] Dev/staging/prod use isolated secrets and identities; key inventory, owners, expiry, and rotation runbooks exist.
- [ ] KMS/secret store auditing is properly enabled; log aggregation/tracing retains no raw secrets.
- [ ] Runtime secret files have ACLs, owners, rotation, and backup/mount protection.
- [ ] Runbooks exist for exposed tokens/keys covering revocation, consumer migration, history/artifact/log checks, and investigation.
- [ ] Failure paths such as KMS outages, expired secrets, or permission denied are tested: the system **never falls back to static credentials**.

## 13. Scenario Exercises (with Answers)

**Question 1.** A class has `private static final String SERVICE_TOKEN = "..."`, and the code is pushed to a private repository. Is it secure?

**Answer:** No. The token remains in source and Git history and can appear in bytecode, artifacts, and clones. Never hard-code secrets regardless of whether the repo is private or public.

**Question 2.** A developer moves the secret from a Java literal into `src/main/resources/application.properties` and builds a fat JAR. Is the problem solved?

**Answer:** No. Resources are typically packaged into the JAR and can still be extracted. Separate secrets from artifacts and provision them at runtime.

**Question 3.** Is converting the token to Base64 and storing `BASE64_TOKEN` in code secure enough?

**Answer:** No. Base64 only changes representation; anyone with the binary and decoding logic can recover it. Obfuscation does not create real secrecy.

**Question 4.** A Dockerfile uses `ARG API_TOKEN`, then deletes a file containing the token in a later layer. Is the image guaranteed clean?

**Answer:** No. The token may persist in build metadata, history, layers, or caches, and scripts using the token may log it. Never pass raw secrets via ARG/ENV; use dedicated build secret mounts when needed and verify nothing persists in output.

**Question 5.** Java code calls `logger.debug("headers={}", request.getHeaders())`, but debug logging is enabled only in DEV. Is there risk?

**Answer:** Yes. Headers can carry Authorization/session tokens, and DEV/CI logs still have readers, backups, and APM. Use allowlisted fields and consistent logging policies across environments.

**Question 6.** Is `System.getenv("DB_PASSWORD")` better than hard-coding? Is it completely secure?

**Answer:** It is better for **separating config from artifacts** if injected at runtime, yet environment variables can leak via process metadata, dumps, child processes, platform UIs, or logs. Prefer workload identity/secret managers or protected runtime mounts with minimal scope/TTL.

**Question 7.** The secret was deleted from the current branch and added to `.gitignore`. Is rotation still required?

**Answer:** If a real secret may have been exposed, **you must assess and usually revoke/rotate**. History and copies do not vanish on their own; ignoring a file does not revoke a credential.

**Question 8.** A KMS key is non-exportable, yet the app logs `keyId`. Is that the same severity as logging a raw AES key?

**Answer:** Not necessarily. `keyId` is usually auditable metadata whereas a raw key is a secret; still, keyIds/aliases must comply with policy and never embed sensitive data.

**Question 9.** When the secret manager fails, the app falls back to an embedded credential to keep serving requests. Why is this dangerous?

**Answer:** Fallbacks keep hard-to-manage secrets inside artifacts, bypass access controls and rotation, and may keep using compromised keys. Fail closed, alert, and design availability properly upfront.

**Question 10.** Is logging `key.getEncoded()` and encrypting the log files afterward as safe as not logging it at all?

**Answer:** No. The secret already traversed collectors, agents, and buffers and could be read before encryption, copied elsewhere, or retained in backups. Best practice is **never logging raw keys in the first place**.

**Question 11.** An AES key was exposed, so new data uses a new key while old data remains encrypted with the old key. Is remediation finished?

**Answer:** Not necessarily. You must evaluate risk to old ciphertext, key versions still enabled for decryption, re-encryption/re-wrapping options, scope, and revocation timing based on data recovery needs. Encryption key rotation involves more steps than replacing an API token.

**Question 12.** A code scanner reports zero findings; can you conclude the image and logs contain no secrets?

**Answer:** No. Scanners have false negatives and only check configured scopes. Inspect source history, packages/resources, image layers, CI artifacts, and logging paths, alongside runtime monitoring.

## 14. References

- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): managing generation, authorization, storage, provisioning, rotation, expiration, revocation, and risks of environment variables.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): types of data to exclude from logs, including access tokens, authentication passwords, connection strings, and encryption keys.
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html): avoiding hard-coding in pipelines, artifact/container image risks, and least privilege.
- [MITRE CWE-798 — Use of Hard-coded Credentials](https://cwe.mitre.org/data/definitions/798): issues with credentials fixed in code/packages.
- [MITRE CWE-532 — Insertion of Sensitive Information into Log File](https://cwe.mitre.org/data/definitions/532.html): secret leakage through logs and confidentiality consequences.
- [Java SE 17 — KeyGenerator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): generating symmetric keys via providers.
- [Java SE 17 — SecretKey API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKey.html): secret key interface.
- [Java SE 17 — Cipher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): AES/GCM and working with ciphertext/tags.
- [Java SE 17 — SecureRandom API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): randomness source for security applications.
- [Java SE 17 — KeyStore API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): storing/loading keys and certificates by keystore/provider.
