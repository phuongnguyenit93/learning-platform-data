# Distinguishing Compatibility Remediation from Restoring Outdated Security Configurations

When upgrading Java, an application may fail to start, fail to connect to an older service, or lose access to an internal component. A commonly suggested quick fix is to "turn the old configuration back on": open every package for reflection, accept all TLS certificates, re-enable disabled cryptographic protocols, or restore permission mechanisms that are no longer supported. This approach may make a quick test pass, but it can also **undo the very security improvements that the JDK upgrade provides**.

In **Java Advance Compatibility Migration**, two objectives must be clearly distinguished:

1. **Compatibility remediation:** restore the application's expected behavior and communications using supported APIs, protocols, access permissions, and configurations while maintaining an appropriate level of protection.
2. **Legacy security rollback:** relaxing or disabling a security control to preserve old behavior—for example, skipping server identity verification, allowing disabled protocols, or overly broadening internal access permissions.

These two actions are not synonymous. Scope-limited, managed transitional measures may be necessary during a migration, but "no longer failing" must never be assumed to prove that a solution is secure or sustainable.

This lesson focuses on classifying issues, identifying root causes, choosing appropriate fixes, and recording evidence so that security is not traded away for short-term compatibility.

## 1. Compatibility and Security Are Both Required

A compatible system means supported consumers continue to fulfill the published contract: the application starts up, APIs work, data is processed properly, and external communications meet requirements.

A secure system must also maintain controls such as:

- Verifying server identity and trust chains on TLS connections.
- Using protocols, ciphers, and algorithms permitted by security policy.
- Restricting access permissions for processes, modules, and service accounts.
- Protecting secrets, credentials, keys, and certificates.
- Controlling class loading, handling of untrusted data, and execution of external code.
- Logging, access control, and monitoring without leaking sensitive data.

A change can solve the compatibility aspect while degrading security. For example, disabling all certificate checks allows the client to connect even to servers with invalid certificates; that does not prove it connected to the right destination.

There are also cases where applying new security defaults exposes longstanding defects in an older system. When the JDK rejects weak ciphers or reflection into private fields, "fixing the error" does not necessarily mean reverting the runtime to its previous behavior. Often the dependent system must be fixed or the integration approach replaced.

## 2. Distinguishing Three Types of Outcomes When Handling Failures

| Outcome | Description | Example |
|---|---|---|
| Root-cause compatibility fix | Replace API, dependency, or configuration to satisfy requirements on the new JDK while preserving security controls | Upgrade the HTTP library and fix the certificate chain so the TLS handshake succeeds |
| Controlled transitional measure | Relax a narrowly scoped permission for a defined duration with an owner and removal plan | Open a single package to a single named module while upgrading a framework |
| Restoring insecure behavior | Disable or indefinitely broaden controls solely to bypass an error | Trust-all TLS, skipping hostname verification, accepting protocols banned by policy |

Not every workaround carries the same level of risk. To decide to accept a temporary measure, you must clearly state boundaries, affected data, conditions of application, compensating controls, and a replacement plan. If it cannot be demonstrated that the residual risk aligns with organizational policy, redesign rather than restoring old defaults.

## 3. Why Can a JDK Upgrade Expose Security Issues?

Changes do not come solely from the Java language or bytecode. Different layers can be impacted:

1. **JSSE/TLS:** protocols, algorithms, certificate validation, hostname verification, and truststores.
2. **Security providers:** provider selection, algorithm support, key formats, and cipher modes.
3. **Certificate path validation:** signature algorithms, key sizes, CA chains, validity periods, and path-checking policies.
4. **JPMS strong encapsulation:** which modules may access public APIs, and which packages are open for deep reflection.
5. **JDK API lifecycle:** legacy mechanisms that are deprecated, disabled, or removed.
6. **Java deserialization:** filters for deserialized classes and resource limits.
7. **JVM options:** flags that are renamed, become obsolete, or are no longer supported.
8. **Runtime packaging:** custom images missing required providers, certificates, modules, or components.
9. **Operating system and container:** truststores, file permissions, DNS, proxies, native libraries, and service account setup.

A JDK security update within the **same feature release** can also alter enforced limits or policies. Therefore, do not write "Java 17 has a TLS bug" without specifying the update/build, vendor, operating system, and actual endpoint.

## 4. Start by Classifying the Error Instead of Trying to Disable Security

An error message is usually a starting point, not the sole conclusion.

| Symptom | Causes to investigate | What not to do immediately |
|---|---|---|
| `SSLHandshakeException: PKIX path building failed` | Trust chain, CA, intermediate certificates, loaded truststore | Install a TrustManager that accepts every certificate |
| `No subject alternative names matching` | Mismatch between hostname and server certificate | Disable hostname verification |
| `handshake_failure` or `protocol_version` | Protocol/cipher, key exchange, proxy, TLS appliance, certificate | Re-enable all weak TLS settings |
| `InaccessibleObjectException` | Reflection into an unopened package of a module | Open JDK packages wholesale |
| `IllegalAccessError` | Module export permissions or binary access | Use unspecified permission-granting flags |
| `AccessControlException` on older JDKs | SecurityManager/policy and blocked operation | Grant `AllPermission` to all code |
| `InvalidKeyException`, `NoSuchAlgorithmException` | Key format/size, algorithm, provider, policy | Fall back to a weaker algorithm just to "make it run" |
| `ClassNotFoundException` during deserialization | Missing class, version mismatch, allowlist/filter, class loader | Disable all deserialization filters |
| Cannot read secret/certificate file | File path, ownership, POSIX/Windows ACLs, mounts, and container UID | Grant overly broad read permissions or copy secrets into the image |

Collect the stack trace, root cause, JVM version, and relevant configurations before making changes. A "handshake_failure" error can have many causes; do not infer a missing protocol solely from a single message string.

## 5. Typical Example: TLS Fails to Connect After a JDK Upgrade

Suppose an application moves from an older JDK to a newer JDK, and HTTPS connections to an internal service subsequently fail. The team finds an old guide suggesting creating an `X509TrustManager` that skips certificate checks to "fix SSL".

If implemented that way, the connection may bypass the verification error, but the client no longer verifies whether the server has the right identity. This can allow connections to an impersonating server or a man-in-the-middle, especially if hostname verification is also disabled.

The right approach is to determine **why verification failed**:

- Has the server certificate expired or is it not yet valid?
- Is the DNS name used by the client present in the certificate's Subject Alternative Name (SAN)?
- Does the server send the full set of intermediate certificates?
- Is the issuing CA trusted by the right environment's truststore?
- Which truststore is the client using: the JDK default, a custom configuration, or the container's?
- Does a proxy/gateway terminate TLS and present a different certificate?
- Is there a discrepancy in system clock, SNI, or hostname?
- Have the certificate signature algorithm, key size, or protocol been restricted by a new policy?

Once the cause is identified, fix the trust chain, certificate, endpoint name, or client configuration accordingly. If an internal CA must be added to the truststore, verify the CA's origin and authority—do not import an unverified certificate merely to bypass the error.

### 5.1. Use a Supported HTTP Client and Keep TLS Verification

Java 11+ example using the Java HTTP Client:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HealthClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.org/health"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status = " + response.statusCode());
    }
}
~~~

This is an example of using the standard API without customizing it to skip certificate or hostname verification. The domain is a placeholder. In a real system, the client also needs to handle network errors, authentication, payload size limits, and timeouts according to service requirements.

Do not write an "accept-all" custom trust manager or a hostname verifier that always returns true. Such code treats the symptom by eliminating identity verification.

### 5.2. Appropriate Diagnostic Checks

Inspect the runtime's Java Security configuration:

~~~java
import java.security.Security;

public final class SecurityDiagnostics {
    public static void main(String[] args) {
        System.out.println(
                "TLS disabled algorithms: " +
                Security.getProperty("jdk.tls.disabledAlgorithms"));

        System.out.println(
                "Cert path disabled algorithms: " +
                Security.getProperty("jdk.certpath.disabledAlgorithms"));
    }
}
~~~

These properties are one piece of diagnostic information; exact values depend on the JDK and policy. Do not override them to re-enable prohibited algorithms without a security review.

You can temporarily enable TLS debugging in a controlled environment:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar application.jar
~~~

Handshake logs may contain certificate details, hostnames, and infrastructure information. Restrict access to logs and do not keep verbose debugging enabled long-term in production without proper procedures.

### 5.3. Fixing the Truststore Differs from Disabling Verification

A properly managed truststore stores the CAs or certificates the organization has decided to trust. When adding an internal CA, verify the certificate chain, system name, lifecycle, rotation process, and trust scope.

Java typically supports specifying a truststore through appropriate system properties, for example:

~~~text
-Djavax.net.ssl.trustStore=/secure/path/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

This is a sample configuration, not an instruction to import arbitrary certificates. Never place passwords directly in source code or readable scripts; manage secrets via an appropriate mechanism. Specifying a custom truststore may replace the default CA bundle depending on configuration, so confirm other endpoints still work.

## 6. TLS Protocols and Ciphers: Upgrade the Peer Instead of Re-enabling Weak Modes

A newer JDK may disable weak protocols or algorithms according to security policy. When an old system only supports protocols/ciphers that are no longer allowed, the application may fail the TLS handshake.

A misguided "fix" is lowering the client's protection level for all connections. That widens the risk to endpoints that did not even require changes.

Instead:

1. Check which TLS versions and cipher suites are actually supported by both sides.
2. Identify where it is blocked: JDK client, server, reverse proxy, or load balancer.
3. Prioritize upgrading the server or intermediary device to support modern protocols and ciphers.
4. Define the TLS configuration according to the organization's and environment's security standards.
5. Test with the target client/runtime, including compatibility for other consumers.
6. If a transition phase must be designed, limit its scope, duration, network segment, and mitigations, and obtain approval via the security process.

Whether TLS 1.2 or TLS 1.3 is available also depends on the JDK, provider, and configuration on both sides. Do not apply a fixed protocol list without checking the actual systems.

A tightened security setting is not a regression merely because the application used to connect on an older JDK. The migration goal is to preserve business functionality without reverting to protection levels deprecated by policy.

## 7. Certificate Validation Is Not Application Authorization

A successful TLS connection only proves the properties verified by the TLS mechanism, such as the certificate chain and configured endpoint identity. It does not by itself grant authorization to access a business API.

Distinguish between:

- **Authentication:** who is communicating?
- **Authorization:** which actions is that identity permitted to perform?
- **Confidentiality/integrity:** is the transmitted data protected by the chosen mechanism?
- **Trust configuration:** which CAs/endpoints does the client trust, and under what policy?

For example, fixing a certificate chain error must not lead to granting all API permissions to a service account. A system may need role/permission updates due to service account changes, but that is a separate security decision, not an inevitable consequence of upgrading the JDK.

## 8. JPMS Example: Open Reflection Permissions or Fix API Usage?

Starting in Java 9, JPMS introduced module boundaries. In modern JDKs, strong encapsulation causes many legacy libraries to fail when reflecting into private JDK members.

Example:

~~~java
import java.lang.reflect.Field;

Field field = String.class.getDeclaredField("value");
field.setAccessible(true);
~~~

On the target JDK, the call above may throw:

~~~text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang" to unnamed module
~~~

The message typically identifies the source module, package, and target module. This is a **deep reflection across module boundaries** issue; it does not mean the `String` API was removed.

### 8.1. `exports` and `opens`

| Mechanism | Purpose |
|---|---|
| `exports some.package` | Exposes public types and members according to module rules |
| `opens some.package` | Allows deep reflection into that package at runtime |
| `opens some.package to target.module` | Opens the package only to a specific module |
| `--add-exports` | Grants access to the public API of an unexported package |
| `--add-opens` | Grants deep reflection access to a package at runtime |

If the package belongs to an **application module owned by the team**, a narrowly scoped declaration may be appropriate:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    opens com.example.customer.dto to com.example.serializer;
}
~~~

The serializer module name is only an example. In a real project, use the framework's exact module name; do not assume the Maven artifact name is the JPMS module name.

If reflection targets **internal private JDK fields**, the long-term direction should be using public APIs or upgrading the library/framework to stop relying on implementation details.

### 8.2. `--add-opens` Can Be a Transitional Measure, Not a New Contract

Syntax example:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

This option can help verify a classpath application whose reflective access to a specific package is being blocked. However, it broadens access for components within the target scope and still depends on private JDK implementation details.

If temporary use is unavoidable, clearly record:

- The source module and package verified from the error.
- The target module or unnamed module group requiring access.
- Which framework/dependency causes the reflection requirement.
- Why upgrading or replacing the API is not yet possible.
- The specific JVM where the flag is applied: test worker, service, agent, or container.
- Owner, review deadline, and removal criteria.
- Evidence that other controls remain enforced.

Do not copy a long string of `--add-opens` flags from another project or open every package without justification. JPMS encapsulation is not a full security sandbox mechanism, yet removing internal access controls still creates coupling and widens interaction with implementation details.

## 9. Legacy SecurityManager: Difference Between Fixing the Application and Restoring an Outdated Sandbox

In earlier Java versions, `SecurityManager` and policy files were used to control certain permissions within the same JVM process. This mechanism was placed on a deprecation/removal path and changed significantly in modern JDKs.

JEP 411 marked SecurityManager as deprecated for removal starting in Java 17. JEP 486 further ended support for re-enabling SecurityManager as the legacy sandbox mechanism in JDK 24. When planning a JDK upgrade, check the status for the exact target release and the legacy APIs the project uses.

A project that previously configured:

~~~text
grant {
    permission java.security.AllPermission;
};
~~~

may have granted broad permissions in the SecurityManager policy to avoid permission errors. Copying this kind of setup into a new architecture or trying to restore an outdated sandbox is not a sustainable migration path.

### 9.1. Why Should You Not "Grant All Permissions"?

`AllPermission` essentially erases many permission boundaries in the old SecurityManager model. It does not help determine which permissions are genuinely needed and does not resolve security architecture on newer JDKs.

If the application previously relied on SecurityManager to isolate plugins or untrusted code, do not replace it with an allow-all flag or policy. Re-examine the **trust boundaries** of the system:

- Process and container isolation.
- OS filesystem permissions and dedicated service accounts.
- Network policies or firewalls.
- Access permissions for secrets and credentials.
- Identity-based authorization, API tokens, or OAuth/RBAC depending on the architecture.
- Separating untrusted plugins into dedicated services/processes.
- Resource limits and observability mechanisms.

A separate class loader or separate JPMS module does not by itself create a sufficient security sandbox for executing untrusted code. If isolating independent code is required, choose an isolation model truly suited to the risk level.

### 9.2. Signs That Redesign Is Needed

If the application uses `System.setSecurityManager`, `AccessController.doPrivileged`, custom policies, or legacy permission checks, inventory those code paths and their actual roles. Do not simply delete the code to get past a compile error if it served as an intentional layer of protection.

The migration plan must answer:

1. Which resources did the old SecurityManager protect?
2. What is the source of untrusted data/code?
3. Is the new boundary a process, container, service, or identity?
4. Who manages the new policies and permission checks?
5. Which tests prove that prohibited cases are still denied?
6. What happens if a plugin or dependency is compromised?

Functional compatibility and resource protection must be addressed together.

## 10. Crypto Providers and Legacy Algorithms

An application may request an algorithm by name or depend on a specific provider:

~~~java
import javax.crypto.Cipher;

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

The example above selects a standard transformation, yet real encryption code must also properly manage keys, nonces/IVs, tags, ciphertext, and nonce reuse policies. A single `getInstance` call should not be treated as a complete cryptographic design.

During migration, `NoSuchAlgorithmException` or `NoSuchPaddingException` may occur when:

- The algorithm or transformation is absent from the currently selected provider.
- A vendor-specific algorithm name is no longer provided.
- A provider is missing from a custom runtime image.
- Provider ordering or security policy configuration changed.
- Keys/certificates do not meet the limits of the target JDK.

The fix is to determine the algorithms required by the system, historical data formats, and providers that can safely support them. Do not switch to a weaker algorithm to "regain compatibility", or ignore signature/verification failures.

### 10.1. Do Not Confuse Ability to Read Old Data with Ability to Create New Data

A system may need to **read historical documents** protected by an old algorithm while disallowing that algorithm for creating new data. These two requirements may need separate workflows:

- Evaluate policies and access permissions for historical data.
- If permitted, isolate the conversion step in a controlled environment.
- Migrate data to an approved format and algorithm.
- Verify integrity and recoverability.
- Stop creating new data with the old mechanism.
- Document the scope, owner, and sunset timeline for the conversion component.

Not every legacy algorithm is allowed for decryption, verification, or data migration. Follow applicable security policies and regulations rather than assuming "read-only is always safe".

## 11. Deserialization and Untrusted Data

Some older applications use Java native serialization. When moving to a new JDK or updating libraries, the system may start enforcing filters or restrictions on deserializable classes. If the data or classes do not match expectations, deserialization can fail.

Unconditionally allowing every class is not a safe compatibility solution. Deserializing untrusted data can introduce severe risks when combined with dangerous classes and behaviors.

Instead:

- Identify where the data comes from and whether it is trustworthy.
- Document the list of valid types and limits on size, depth, and reference count as needed.
- Use `ObjectInputFilter` or an appropriate runtime/framework mechanism to restrict deserialized classes.
- Consider migrating to a data format with explicit schema, versioning, and validation.
- Test both valid historical data and malformed/rejected data.
- Do not remove all filters merely because one legacy object was not recognized.

Conceptual filter example:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=1000;java.base/*;com.example.dto.*;!*");
~~~

This is only an example of applying limits; real patterns must be designed around the actual set of classes and data graph, and tested on the exact target API/runtime. Do not use this pattern as a default allowlist for every application. Attach the filter to the ObjectInputStream flow as designed and verify actual behavior.

The migration goal is to let **supported valid data** continue working without opening the door to arbitrary object graphs.

## 12. Controlling File Permissions, Secrets, and Runtime Images

Some errors commonly referred to as "security compatibility" actually stem from the container or operating system:

- The application runs under a UID lacking permission to read a private key.
- Truststore/certificates are not mounted into the new container.
- A minimal Docker image is missing a needed module or provider.
- File paths previously relied on the JDK 8 installation layout.
- The new container has a read-only filesystem, preventing writes to temporary directories.
- Service accounts or roles changed when upgrading the platform.

The fix is to define the **minimum permissions genuinely required**, rather than granting system-wide permissions.

For example, if the application must read a certificate file, check owner/group/ACLs, mounts, and permissions on the exact directory. Do not run `chmod 777` or copy a private key to a broadly readable location to clear an error. If the application needs temporary writes, provision a dedicated writable area with proper permissions rather than making the entire filesystem writable.

Distinguish JVM permissions from OS/container permissions. A Java flag cannot replace operating system access controls, and changing OS ACLs does not bypass JPMS encapsulation.

## 13. Decision Table: Compatibility Fix or Reopen Old Configuration?

| Scenario | Supported fix | Workaround to consider | Should not be treated as final outcome |
|---|---|---|---|
| Missing certificate chain | Fix chain, truststore, approved CA | Dedicated managed truststore | Trust-all certificates |
| Wrong hostname/SAN | Fix DNS, endpoint, or reissue certificate with correct SAN | Switch to an endpoint with a valid certificate | Disabling hostname verification |
| Server supports only weak TLS | Upgrade server/proxy and compatible client | Approved time-bounded transition period | Enabling weak protocols globally |
| Framework reflects into private JDK | Upgrade framework, use public API | Narrow `--add-opens` with owner and expiration | Opening JDK packages wholesale long-term |
| Named module DTO not yet opened | Qualified `opens` to the needed framework | Scoped runtime open during rollout | Using `open module` indiscriminately without analysis |
| App relies on SecurityManager sandbox | Redesign process/container/identity boundaries | Controlled parallel operation phase | Restoring `AllPermission` or outdated sandbox |
| Legacy provider/algorithm missing | Choose supported provider/algorithm, migrate data | Approved historical data migration tool | Lowering entire crypto policy |
| Deserialization rejected | Fix schema/class mapping and proper filter | Narrow, controlled allowlist exception set | Removing all filters |
| Cannot read secret file | Fix mounts, owner, ACLs, and process permissions | Specific permissions on the needed path | Granting full filesystem permissions |

This table is a decision aid, not a replacement for a security review. A workaround is valid only when organizational policy permits it and risks have been identified.

## 14. Workflow for Handling Security-Related Compatibility Issues

### Step 1: Identify Exact Versions and Actual State

Collect the Java version, JDK distribution, update/build, Gradle/Maven runtime, OS, container, classpath/module path, and relevant security configurations. Do not just write "upgrading from Java 8 to Java 17".

Example:

~~~bash
java -version
javac -version
~~~

With Gradle builds, the JVM running the daemon, the compilation toolchain, and the JVM running tests may differ. If an error occurs in the test worker, the Gradle daemon's JVM configuration is not automatically the worker's configuration.

### Step 2: Capture the Original Error

Save the full stack trace, root cause, triggering operation, and involved endpoint or member. For TLS, you can capture temporary handshake debug output; for JPMS, preserve the exact `does not "opens"` message; for crypto, record the algorithm and provider.

When collecting security logs, mask secrets, tokens, private keys, and personal data. Share logs only with authorized teams.

### Step 3: Compare Old and New Configurations

Compare the effective policy, not just configuration files:

- JVM system properties and security properties.
- Actually loaded truststores/certificates.
- TLS protocols/ciphers supported by client/server.
- Module exports/opens and classpath/module path placement.
- Security providers and algorithm constraints.
- Service account and container permissions.
- Deserialization filters and framework libraries.

A `java.security` file in old and new environments may differ, but runtime differences also come from security updates, providers, and OS settings. Do not reconcile differences by copying the entire old file into the new JDK.

### Step 4: Classify Solutions

For each proposal, record:

- What root issue is being addressed?
- Does it rely on unsupported APIs or configurations?
- What is the scope of permission/security relaxation?
- Is there an option to fix the peer or upgrade dependencies?
- Who owns the risk and is responsible for removing the workaround?
- Which tests will prove functionality remains correct and security controls still work?

Do not select a solution based solely on application startup or a single successful request.

### Step 5: Attempt Sustainable Fixes First

Prioritize upgrading dependencies, using official APIs, reissuing valid certificates, configuring controlled truststores, upgrading TLS endpoints, and adjusting actual access permissions.

For plugins or libraries not yet upgraded, consider supported fixes. If the vendor has not provided one, manage the exception and establish a replacement plan.

### Step 6: Verify Functionality and Security

Run both positive tests and negative tests: the system must handle valid requests **and continue rejecting unauthorized requests**.

### Step 7: Perform a Controlled Rollout

Use staging/canary on the target environment with clear rollback criteria. Monitor TLS failures, authorization denials, reflection errors, exception types, latency, and related business metrics.

### Step 8: Record Evidence and Exceptions

Record versions, command lines, logs, test reports, decisions, and owners. If retaining a temporary configuration, include termination conditions; do not allow a workaround to become the default baseline for subsequent JDKs.

## 15. Two-Way Testing: Valid Behavior and Proper Rejection

A "compatibility fixed" conclusion is insufficient if only the happy path is tested.

| Check | Cases that must succeed | Cases that must be rejected |
|---|---|---|
| HTTPS/TLS | Endpoint with matching hostname and valid certificate chain | Wrong-name, expired, or untrusted certificate |
| Authentication | Valid credentials/tokens | Invalid credentials or expired tokens |
| Authorization | User/role with valid permissions | Unauthorized role |
| Reflection | Framework accesses DTOs opened by contract | Arbitrary access to JDK internal/private members outside scope |
| Deserialization | Objects matching valid schema/allowlist | Disallowed classes or object graphs exceeding limits |
| Filesystem | Process reads required config files and secrets | Other processes/roles cannot read secrets |
| Crypto | Valid data created/read per policy | Disallowed algorithms/keys are rejected |
| Deployment | Container runs on target JDK | System-wide permissions are not opened to bypass errors |

Negative tests should be designed and executed safely, not by attempting to exploit vulnerabilities in production. The goal is to prove controls remain effective within an authorized testing scope.

### 15.1. Example of Testing Access Control Logic

Suppose a business API has the interface:

~~~java
public interface ReportService {
    Report readReport(UserContext user, String reportId);
}
~~~

A contract test suite can verify:

~~~java
@Test
void authorizedUserCanReadReport() {
    Report result = service.readReport(
            userWithReportReadPermission(),
            "R-42");

    assertNotNull(result);
}

@Test
void unauthorizedUserIsRejected() {
    assertThrows(
            AccessDeniedException.class,
            () -> service.readReport(
                    userWithoutReportReadPermission(),
                    "R-42"));
}
~~~

This is JUnit-style illustrative code; `UserContext`, `AccessDeniedException`, and fixtures represent hypothetical application types. A migration that only achieves functional compatibility—where the first test passes while the second fails—is not safe.

## 16. Secure Configurations Should Not Be Mixed Across Environments

There are groups of flags and configurations with distinct roles:

- JVM system properties and security properties.
- `module-info.java`, `--add-opens`, `--add-exports`.
- Truststore, keystore, certificate chain.
- Container permissions, secret mounts, network policies.
- Build tool daemon args, test JVM args, and application JVM args.
- Framework security configuration, authentication, and authorization rules.

They may reside in different processes or infrastructure layers.

For example, configuring `--add-opens` for a Gradle test task:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

only affects the JVM of the configured test task; it does not mean the production Docker container received the same argument. Conversely, adding a truststore to a production server does not automatically fix a CI test worker.

Tie each configuration change to the process where the error occurs. During migration, prefer keeping environments consistent through explicit configuration and documentation rather than copying broad permissions everywhere.

## 17. Notes on Handling Security Updates Within the Same JDK

Security compatibility issues do not arise only when changing feature releases from Java 11 to 17 or from 17 to 21. A JDK update on the same branch may introduce patches, changes to restricted algorithms, CAs, time-zone data, or security-related behaviors.

Therefore, records should capture:

| Information | Example to record |
|---|---|
| Feature release | Java 17 |
| Update/build | Full version string from `java -version` |
| Vendor/distribution | Actual JDK provider |
| OS/architecture | Linux x64, Windows x64, or corresponding environment |
| TLS endpoint | Hostname and port; do not record secrets |
| Trust configuration | Selected truststore/CA, managed path |
| Dependency | HTTP client, provider, framework versions |
| Runtime arguments | Only relevant flags, protecting sensitive information |
| Evidence | Logs, test reports, certificate chain validation |
| Decision | Secure fix, temporary exception, or blocked |

If the organization uses multiple JDK distributions, each target build should be verified as needed. Do not assume patches and truststores across distributions are identical merely because they share the same Java feature version.

## 18. Distinguishing Acceptable Workarounds from Unmaintainable Configurations

A temporary measure may be considered if it satisfies these conditions:

1. Diagnosis has identified the root cause and bounded the impact.
2. No immediate root-cause fix is feasible within the rollout timeframe.
3. The scope of relaxed permissions is strictly bounded.
4. The risk is assessed and approved by an authorized person.
5. Compensating controls, monitoring, and a rollback mechanism are in place.
6. An owner and deadline exist to upgrade dependencies/fix the architecture.
7. Negative tests prove that critical controls remain active.
8. The workaround is tracked as technical debt and does not become an uncontrolled default configuration.

An example decision:

~~~yaml
migrationException:
  id: "REFLECTION-01"
  affectedComponent: "legacy-serializer"
  targetJdk: "17"
  cause: "deep reflection to a JDK package"
  temporaryMeasure: "narrowly scoped --add-opens"
  status: "APPROVAL_REQUIRED"
  owner: "platform-team"
  exitCriteria:
    - "upgrade serializer to a supported version"
    - "remove JVM argument"
    - "pass integration tests without the exception"
~~~

This is an exception management template, not an actual approval. Cases involving weak TLS, trust-all, or bypassing authorization checks may be unacceptable even with a deadline; follow security policy rather than self-approving simply because a ticket exists.

## 19. Common Misconceptions

**"The application runs after disabling certificate validation, which means TLS is fixed."** No. It merely drops an identity verification step. Fix the actual certificate, chain, trust, or endpoint.

**"Re-enabling all old ciphers is the only way to keep compatibility."** Usually the peer/proxy needs to be evaluated and upgraded. Relaxing policy runtime-wide can affect other connections.

**"Using `--add-opens` is a security fix."** It is a JPMS deep reflection permission change, useful within limits, but it does not replace removing dependencies on private internals.

**"Seeing `InaccessibleObjectException` means Java removed the class."** The class/member may still exist; the issue is usually that the package is not open to the calling module.

**"Just grant `AllPermission` like the old SecurityManager."** Granting unlimited permissions does not create an isolation model suitable for newer JDKs.

**"Replacing Java SecurityManager with a custom class loader creates an equivalent sandbox."** A class loader does not by itself provide the security isolation needed for untrusted code.

**"Allowing deserialization of every class restores compatibility."** It removes limits on dangerous input data. Address schemas, classes, and filters per contract.

**"An SSL handshake failure is definitely caused by a disabled legacy protocol."** A handshake can fail due to certificates, hostname, CA, keys, ciphers, proxies, or other configurations.

**"If test config is fixed, production is automatically fixed."** Test runners, build daemons, and production services may be different JVMs/processes.

**"A JDK patch does not change compatibility."** A security update can change algorithm policies, certificates, or behaviors significantly for older systems.

**"No more warnings means the system is secure."** Absence of warnings is not proof that all verifications, authorizations, and policies remain enforced.

## 20. Checklist Before Finalizing the Migration Plan

- [ ] Accurately identified source JDK, target JDK, update/build, and vendor.
- [ ] Recorded original stack traces/logs and failing code paths.
- [ ] Distinguished compile, linkage, runtime, configuration, and security failures.
- [ ] Identified which security control is involved and why it rejected the operation.
- [ ] Prioritized fixing APIs, dependencies, certificates, truststores, or peers.
- [ ] Avoided using trust-all, skipping hostname verification, or granting unlimited permissions as default solutions.
- [ ] Distinguished `--add-opens` and `--add-exports` when handling modules.
- [ ] Inventoried dependencies on SecurityManager, policies, or legacy sandboxes if any.
- [ ] Checked crypto providers, algorithm constraints, and related historical data.
- [ ] Checked deserialization filters and filesystem/secret access permissions where affected.
- [ ] Ran positive tests proving valid functionality works.
- [ ] Ran negative tests proving invalid access is still rejected.
- [ ] Verified test workers, production JVMs, containers, and supported environments.
- [ ] Temporary workarounds have an owner, scope, approval, monitoring, and exit criteria.
- [ ] Saved evidence, test limitations, decisions, and rollback plan.

## Conclusion

**Compatibility remediation is not synonymous with restoring outdated security configurations.** Upgrading the JDK can cause legacy dependencies on weak TLS, invalid certificates, private JDK internals, SecurityManager, or overly broad access permissions to stop working. Instead of turning off controls to get past errors, identify the cause, use supported APIs and configurations, upgrade dependencies/endpoints when needed, and test both valid cases and cases that must be rejected.

A successful migration proves not only that the application starts up and serves requests, but also that critical security boundaries remain intact. If a workaround must be used, accept it only within an assessed scope with an owner and a removal plan. This approach preserves **verified compatibility** without turning a Java upgrade issue into a long-lasting security weakness.
