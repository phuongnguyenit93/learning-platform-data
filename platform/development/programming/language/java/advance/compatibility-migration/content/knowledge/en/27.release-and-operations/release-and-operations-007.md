# Re-Verifying Security Patches on the Selected JDK Version

Selecting a suitable JDK version for a **Java Advance Compatibility Migration** project does not yet mean the system is safe to release. An application can run on Java 17 or Java 21, compile with the right `--release`, and pass all unit tests, yet still run on a **JDK build missing security patches**. This situation is especially dangerous when the development team configures “Java 21” in CI while the production Docker image still uses an old update, or when a runtime image created months ago with `jlink` has not been rebuilt from the new JDK.

Therefore, before releasing the selected Java version to production, you need to **re-verify the actual patch level and the applicability of security advisories**. This process does not stop at reading a CVE or running a scan command: you must confirm the actual vendor, version, build, provenance, and artifact/container; read the vendor's advisories; assess the impact on the application; test security and compatibility; and then deploy, monitor, and update continuously.

This lesson belongs to the **Release and Operations** chapter. Version/cadence information changes over time; examples mentioning 2026 are illustrative as of the time of writing, **not a permanent list of latest patches**. In every release cycle, always cross-check the advisory page and release notes of the exact vendor being used.

## 1. Purpose of Reviewing Security Patches

This process must answer six questions:

1. **Which JDK are we running?** Not just “Java 21,” but the specific vendor/distribution, full update version, build, OS/architecture, and runtime image.
2. **Which patches has the vendor released?** Are there CPU/CSPU releases, out-of-cycle updates, or emergency advisories after the running build?
3. **Which vulnerabilities affect the application?** Consider affected components, exposed attack surface, client/server usage, parser/TLS/serialization, JDK tools, and runtime capabilities.
4. **Does the planned release version already contain the fix?** Is there evidence from release notes/vendor advisories, rather than inferring from the filename?
5. **Does the patch change behavior?** TLS, certificate trust, security properties, cryptography, XML, networking, resource limits, class loading, and native libraries can be affected.
6. **Has every actual instance been replaced with the patched runtime?** Including services, batches, consumers, CI, disaster recovery, container images, and custom runtimes.

If any question lacks evidence, the appropriate status is **unverified**, not automatically “patched”.

## 2. Distinguishing JDK Feature Version, Update Version, and Build

Some common notations:

```text
Java 21
21.0.13
21.0.13+11
21.0.13+11-LTS
OpenJDK Runtime Environment Temurin-21.0.x+build
```

These strings only illustrate how version/build are represented, and do not claim every vendor uses the same suffixes.

| Field | Meaning | Why Is It Important? |
|---|---|---|
| Feature version | For example, 17, 21, 25. | Identifies the Java/API/JVM line. |
| Update/security version | For example, 21.0.x. | Identifies the update within a JDK line. |
| Build number | `+b` suffix or vendor label. | Distinguishes binaries with the same release name. |
| Vendor/distribution | Oracle JDK, Eclipse Temurin, Azul, Amazon Corretto, Red Hat OpenJDK, etc. | Release schedules, support, and backports may differ. |
| OS/architecture | Linux x64/aarch64, Windows, macOS. | Patches and binaries are distributed per platform. |
| Image digest/checksum | Identifies the actual artifact. | Avoids mistaking container tags or downloaded files. |

**Important warning:** a “17.0.x” JDK from vendor A cannot automatically be assumed to have the exact same backport set as a build with the same version string from vendor B. Use the security fixes list/release notes of the exact distribution.

In addition, multiple JDKs can exist in the same pipeline: the JVM running Gradle/Maven, the compiler toolchain, the forked test JVM, the service runtime, and the batch runtime. Checking one JDK does not prove the other JDKs are patched.

## 3. Security Update Schedules Go Beyond Major Releases

JDK feature releases follow their own cadence; patches on a JDK line are maintained according to the vendor's schedule.

Key terms:

- **CPU (Critical Patch Update):** periodic security update cycle by Oracle and related vendors, traditionally in January, April, July, and October.
- **CSPU (Critical Security Patch Update):** security-only/out-of-cycle releases issued between CPUs when needed. More frequent updates appeared in 2026.
- **PSU (Patch Set Update):** a term in the Java/Oracle ecosystem for update branches containing changes broader than security-only under corresponding periods/policies; check release/vendor specifics for release process and notation.
- **Security Alert / emergency update:** out-of-schedule notifications and fixes when a rapid response to a notable vulnerability is needed.
- **Maintenance update:** may include non-security bug fixes; do not assume it contains every CVE merely because it was released later.

According to announcements in 2026, alongside periodic CPUs there have been CSPUs and a move toward higher-frequency security releases. Therefore, the rule “only check once per quarter” is no longer sufficient in all cases.

**Reasonable operational plan:** maintain a periodic check cadence aligned with the vendor's lifecycle **and** a process for handling emergency advisories when out-of-cycle patches arrive. The upstream release date is not necessarily the date vendor binaries are ready on every OS/architecture.

## 4. JDK Patches Are Different from Application Library Patches

A Java application consists of multiple layers:

```text
                   Client / Internet / Partners
                              |
                              v
              API Gateway / Load Balancer / TLS
                              |
                              v
                 Java application/framework
               Spring / Jakarta / libraries
                              |
                              v
                      Java runtime (JDK)
               JSSE, JAXP, java.base, JIT, GC...
                              |
                              v
             Container base image / Native libs
                              |
                              v
                 Operating system / Kernel
```

Therefore, at least four patching groups must be distinguished:

| Group | Example | How to Verify |
|---|---|---|
| **JDK/JVM** | JSSE, JAXP, networking, compiler, class libraries. | Vendor security advisory + JDK build. |
| **Third-party Java dependencies** | Spring, Jackson, Netty, logging, JDBC drivers. | Dependency graph, SCA, vendor advisories. |
| **Container/OS/native** | OpenSSL, zlib, glibc, system packages. | OS package inventory, image scanning, distro advisories. |
| **Infrastructure/managed services** | TLS terminator, IdP, database server, message broker. | Service-provider security bulletins and configuration. |

Upgrading the JDK to the latest patch **does not automatically patch** a vulnerability in a Jackson JAR bundled inside the application. Conversely, upgrading Jackson does not fix a CVE inside the JDK's JSSE. A Docker scanner reporting an OS package CVE does not necessarily belong to the Java runtime, yet still needs to be managed.

## 5. Inventory Scope Must Include Rarely Invoked Runtimes

Do not stop at running web services:

- API/backend services and Java servlet/application servers.
- Message consumers, stream processors, scheduled batch jobs.
- Command-line jobs, data migration tools, reporting.
- CI runners, Maven/Gradle daemons, integration test containers.
- Plugin hosts and Java processes launched indirectly.
- Images for standby/DR zones, hot standby, disaster recovery.
- Serverless/container tasks using a platform-provided Java runtime.
- Desktop/client components if within product scope.
- Custom runtime images built with `jlink`.
- Tools running Java in images separate from the application, such as build scanners or code generators.

A metric like “100% of services upgraded to JDK 21” lacks meaning if the denominator is unclear. For example, **35/35 inventoried workloads, including DR and monthly jobs** is more concrete than “100% Java”.

For managed runtimes where the organization does not directly select the JDK build, obtain evidence from the platform's documentation/support matrix and runtime telemetry; do not claim to be patched solely from the application's `--release` configuration.

## 6. Collecting JDK Identity from the Actual Binary

On the runtime environment's terminal:

```bash
java -version
java --version
```

The `java --version` command exists in JDK 9+, while `java -version` is also useful for Java 8.

An illustrative output:

```text
openjdk version "21.0.x" 2026-xx-xx
OpenJDK Runtime Environment VendorName (build 21.0.x+build)
OpenJDK 64-Bit Server VM VendorName (build 21.0.x+build, mixed mode)
```

The placeholders `x` and `VendorName` are not a real release. When collecting evidence, save the output **verbatim** instead of truncating it to “Java 21”.

You can view additional system properties:

```bash
java -XshowSettings:properties -version
```

Properties worth recording:
- `java.version`.
- `java.vendor`.
- `java.vendor.version` if published by the vendor.
- `java.runtime.version` and `java.vm.version` when present.
- `java.home`.
- `os.name`, `os.arch`.
- `java.version.date` on supported JDKs.

**Security note:** output from `-XshowSettings:properties` may contain sensitive paths or configuration. Store and share it only in controlled systems.

## 7. Verifying Directly Inside the Application Process

A script running `java -version` on the host might not use the same JVM as the container, Gradle test worker, or service process. You should have protected internal diagnostics:

```java
import java.util.Map;
import java.util.LinkedHashMap;

public final class JdkIdentity {
    public static Map<String, String> snapshot() {
        Map<String, String> data = new LinkedHashMap<>();
        data.put("java.version",
                System.getProperty("java.version"));
        data.put("java.runtime.version",
                System.getProperty("java.runtime.version"));
        data.put("java.vendor",
                System.getProperty("java.vendor"));
        data.put("java.vm.version",
                System.getProperty("java.vm.version"));
        data.put("java.home",
                System.getProperty("java.home"));
        data.put("os.arch",
                System.getProperty("os.arch"));
        return data;
    }
}
```

This code is compatible with Java 8+ syntax; some system properties may be null depending on the implementation. For releases, log in a controlled manner or send to an internal inventory; **do not return `java.home`/server paths on a public endpoint**.

On JDK 9+, there is also:

```java
System.out.println(Runtime.version());
```

When needing to inspect a running process with appropriate permissions:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
```

`<pid>` is a placeholder. `jcmd` requires appropriate tools/attach permissions; `VM.command_line` may reveal arguments containing secrets, so redact sensitive data before recording evidence.

## 8. Checking the release File and Checksums

On many JDK distributions, the `release` file at the installation root contains information such as `JAVA_VERSION`, `IMPLEMENTOR`, `OS_ARCH`, and `MODULES`.

Shell example:

```bash
cat "$JAVA_HOME/release"
```

PowerShell:

```powershell
Get-Content -LiteralPath "$env:JAVA_HOME\release"
```

The `release` file is useful as a reference, but **is not the sole proof** of the running runtime. The `JAVA_HOME` variable may differ from the actual executable; custom runtime images/vendors may have different layouts.

When downloading a JDK/JRE binary, save the checksum alongside the release source:

```bash
sha256sum downloaded-jdk-archive.tar.gz
```

PowerShell:

```powershell
Get-FileHash -LiteralPath ".\downloaded-jdk.zip" -Algorithm SHA256
```

Compare the digest/checksum or signature against the vendor's official instructions. A checksum **is useful only if the reference value comes from a trusted source**. Computing a hash yourself and seeing a “valid hash” does not prove the file was not tampered with during distribution.

## 9. Three Sources of Evidence to Combine

Build a chain:

```text
Vendor official advisory/release notes
                   |
                   v
       Official patched artifact
         signature / checksum
                   |
                   v
        Build/container image
            digest / SBOM
                   |
                   v
      JVM running in production
        version / image digest
                   |
                   v
        Security test + rollout
                   |
                   v
             Closure record
```

Having only a CVE link without identifying which binary the process runs is not enough. Having only an image digest without knowing which JDK built the image is also not enough.

For supply-chain assurance, you can also collect attestations, signed release artifacts, SBOM, provenance, and artifact registry metadata using your organization's tooling.

## 10. Choosing the Right Security Information Sources

Prioritize in order:

1. **Security advisories and release notes of the JDK vendor actually being used.**
2. **Oracle Java SE Security Alerts / Critical Patch Update advisories** to understand published components/CVEs, when relevant to the product described.
3. **OpenJDK vulnerability advisories** and issue/fix metadata to track upstream.
4. **Vendor distribution release notes** (Temurin, Corretto, Azul, Red Hat, Microsoft Build of OpenJDK, and others) for actual backports/binaries.
5. **NVD/CVE records, OSV, or auxiliary databases** to cross-check descriptions, scores, and impacts.
6. **Internal scanner/SBOM inventory** to determine which deployments fall within scope.

Do not replace vendor sources with a CVE table from a scanning tool lacking product/build/OS details. “Affected/fixed” status must be checked against **the exact product and build**, especially when a vendor backports a fix while keeping a major/update version string different from upstream.

Timeline example: Oracle published its October 2026 CPU; Adoptium also had out-of-cycle CSPU releases in 2026. This is why the workflow must check **every patch released by the vendor**, not just the list of LTS versions.

## 11. Reading an Advisory to Answer Whether You Are Affected

An advisory row typically has:

| Field | What to Understand |
|---|---|
| CVE ID | Vulnerability identifier, not an artifact version. |
| Product/component | Java SE, JSSE, JAXP, AWT, networking, compiler, JGSS, RMI, etc. |
| Affected versions | Affected product versions within the vendor's published scope. |
| CVSS score/vector | Assessment of impact and exploitation conditions. |
| Attack vector | Network, local, adjacent, or physical depending on the vulnerability. |
| Privileges/user interaction | Conditions required by the attacker. |
| Fixed release/build | Must be taken from official patch or release notes. |
| Notes/mitigations | Assumptions, constraints, or temporary mitigation steps. |

Do not just take the highest CVSS score and apply one conclusion to every JVM. Assess whether the affected component is present and triggerable in the workload. However, “not seeing code use the component” **does not mean unaffected** if a library or provider can be invoked indirectly.

In particular, Oracle notices regarding Java SE, GraalVM, JavaFX, or security components may belong to **different products**. Do not misread a JavaFX row as meaning every Java SE server carries that exact risk.

## 12. Prioritizing Patches by Exploitability and Impact

Assess risk based on at least:

- Severity/CVSS and CVE characteristics.
- Exposure to the Internet, network, or untrusted input.
- Does it require authentication, special privileges, or user interaction?
- Is the component available in the current JDK/runtime image?
- Do execution paths invoke the relevant feature?
- Does the workload process external files/XML/images/archives?
- Does the JDK compiler/tooling run in a CI pipeline receiving untrusted input?
- Is there evidence of active exploitation or an emergency alert?
- Is a vendor patch available for the OS/architecture in use?
- Impact of changed default security settings on customers/partners.

Hypothetical examples:

| Situation | Indicative Priority | Needs Verification |
|---|---|---|
| JSSE/TLS issue on a public API | High | Actual version, TLS termination, JSSE usage, fix availability. |
| XML parser vulnerability when receiving XML from partners | High | Parser config, untrusted input, exploitation path. |
| AWT/image processing issue on a server not processing images | Must evaluate; may lower priority | JDK modules, transitive processing, file conversion jobs. |
| Compiler/JDK tools vulnerability on an isolated app-only runtime | Must distinguish build from runtime | CI access, dynamic compilation, tool presence. |
| Hard-to-exploit internal vulnerability with patch available | Still needs a patching plan | Support policy and avoiding old JDK backlog. |

Reachability assessment is a **prioritization tool**, not a default excuse to skip vendor-recommended security patches.

## 13. Do Not Infer “No CVEs” from the Version Name

Some mistakes:
- “We're on Java 21, so it must be new enough.”
- “This JDK was downloaded this week, so it must contain the latest CPU.”
- “Docker tag `21-jre` automatically updated production.”
- “Vendor A released a similar build to vendor B, so fix coverage must be identical.”
- “The scanner didn't report CVEs because it didn't recognize the embedded JDK.”
- “The runtime doesn't contain `javac`, so all compiler CVEs are irrelevant.”
- “NVD hasn't updated yet, so this build has no issues.”

Every conclusion must identify the product, build, component, binary, and evidence. **Zero findings from a scanning tool do not equate to proof of being patched.**

## 14. Creating a JDK Security Baseline Matrix

Example internal table:

| Workload | Vendor | Current Runtime | Approved Build | Evidence | Status |
|---|---|---|---|---|---|
| order-api | Temurin | 21.0.x+build-A | 21.0.y+build-B | Vendor notes + image digest | Pending rollout. |
| reporting-batch | Corretto | 17.0.x+build-C | 17.0.y+build-D | Vendor release metadata | Pending test. |
| CI generator | Oracle JDK | 21.0.x+build-E | 21.0.y+build-F | Installer checksum | Pending install. |
| DR consumer | Temurin | Unknown | Target-approved build | Runtime inventory missing | Blocked. |

Values like x/y/build-A/B are placeholders; they do not represent real JDKs. In production, do not mark “patched” while any runtime cell remains **Unknown** or lacks vendor evidence.

The matrix should also include OS/architecture, image digest, scan timestamp, application owner, patch SLA, and rollback plan. It is a tracking mechanism and does not replace the enterprise security patch process.
## 15. Finalizing the Target JDK Version per Support Policy

Before downloading patches, decide:
- Which Java line is the baseline the application has tested against: 11, 17, 21, 25, or another version?
- Does the JDK vendor maintain **security updates** for that line for as long as the product needs support?
- Do the distribution and license fit commercial/on-prem/cloud deployment?
- Is a vendor-specific build required due to native runtime, OS, or compliance?
- Are production OS/CPU builds ready?
- Are the same JDK runtimes required across CI, staging, prod, and DR?
- Are there environments using a different JVM vendor, such as a managed service's Java runtime?

**LTS does not automatically mean patched indefinitely.** Each vendor has its own support policy and maintenance schedule; a Java feature release designated as LTS is only useful when the organization actually receives and deploys the corresponding security updates.

A Java branch that has reached end-of-support at the current vendor must be handled through a governed option: migrating to a supported line, purchasing extended support if appropriate, or bounding risk with a concrete decommissioning plan. Do not use “no CVEs reported yet” as a reason to keep an end-of-support runtime indefinitely.

## 16. Confirming a CVE Is Fixed in the Exact Build

An advisory may list affected versions and introduce the patch in another update. Distinguish:

1. **Published issue:** CVE identifier, affected components, and exploitation conditions.
2. **Upstream code fix:** commit/issue ID in OpenJDK or the related ecosystem.
3. **Backport:** the fix brought back to a specific LTS branch.
4. **Vendor build:** the official binary containing the backport.
5. **Application deployment:** the actual image/process running that binary.

Do not automatically infer from (2) to (5).

A triage record:

```yaml
advisoryId: "CVE-YYYY-NNNNN"
product: "Java SE"
component: "JSSE"
vendor: "selected-jdk-vendor"
currentBuild: "21.0.x+oldBuild"
fixedBuild: "21.0.y+approvedBuild"
sourceReferences:
  - "vendor security bulletin URL"
  - "vendor release notes URL"
assessment:
  workload: "order-api"
  exposedSurface: "outbound and inbound TLS"
  affected: "pending-verification"
  priority: "high"
verification:
  runtimeVersionEvidence: "pending"
  binaryChecksumEvidence: "pending"
owner: "platform-team"
status: "triage"
```

This is an **illustrative data template**; do not treat a placeholder CVE as a real advisory. When a vendor publishes a backported fix without bumping the version string like upstream, explicitly record the corresponding vendor evidence.

## 17. When a Scanner Reports a CVE Yet the Vendor Says It Was Backported

Detection errors can occur when a scanner uses simple version-comparison logic:

```text
Scanner:
  JDK major/minor appears vulnerable

Vendor:
  Backported fix in vendor-specific build
```

Do not dismiss the finding automatically. Instead:
1. Identify whether the scanner is detecting the **JDK runtime** or an OS package with a similar name.
2. Record the vendor, full build/version, and binary checksum.
3. Read official release notes/advisories proving the fix is integrated.
4. Check whether the scanner rules/plugin database are up to date.
5. Mark as false positive or fixed-by-backport **with evidence** if company process allows.
6. Monitor in subsequent scans to ensure old images do not reappear.

Conversely, if the scanner fails to detect the JDK due to a stripped image or custom path, do not assume “no vulnerabilities”. Add software inventory/provenance and verify manually against vendor advisories.

## 18. SCA/SBOM Must Cover Both Runtime and Application

**Software Composition Analysis (SCA)** typically focuses on JARs/third-party libraries. A **Software Bill of Materials (SBOM)** records the components of an artifact or image.

In practice, there should be two inventory layers:

```text
Application SBOM
  - JARs / WARs / application libraries
  - dependency versions / hashes
  - framework, drivers, native bindings

Runtime/container inventory
  - JDK distribution / exact build
  - OS packages / native libraries
  - image digest / base image
  - optional jlink module list
```

Scanning depends on the scanner: not every tool sees JDKs in `/opt/java`, `/usr/lib/jvm`, or a `jlink` image at a custom path. Check **the scope and detection capabilities of the tool itself**.

You can use CycloneDX or SPDX SBOMs along with attestations/provenance per the organization's supply-chain practices. However, **an SBOM only tells you “what is present”**; it does not prove that the binary is patched or that security tests passed.

## 19. Integrity of JDK Artifacts and Container Images

When obtaining patches:
- Download from the official site/repository or an audited artifact registry.
- Verify signatures/checksums per vendor instructions.
- Record the source URL, retrieval time, and release metadata.
- Pin the JDK update/build version in the build specification.
- If using container images, record the image digest; tags can change over time.
- Maintain a secure internal cache/mirror for rebuilding when needed.
- Do not download a JDK from an unknown site just because the filename matches the version.
- Do not randomly copy `lib/modules` from another build into a running JDK.

For example, a Dockerfile stating only:

```dockerfile
FROM some-jdk-vendor:21
```

is not sufficient to prove production is running the approved patch, because mutable tags can be republished and running deployments do not automatically restart to pull the new image.

In CI, record:
- Resolved full base image reference/digest.
- JDK build/version inside the image after building.
- Output image digest.
- SBOM/scan artifact.
- Actual deployment digest.

**Example digest-pinning syntax (placeholder value):**

```dockerfile
FROM example.com/approved/jdk@sha256:<verified-digest>
```

This is only a reference-notation template; `<verified-digest>` must be replaced with a real SHA-256 digest from a trusted registry. Do not use the example Dockerfile verbatim for building.

## 20. Host Patches Do Not Automatically Update JVMs in Containers

A common operational mistake:

```text
VM host:        OS patched today
Container:      JDK image from three months ago
Running pod:    old immutable image digest
```

Updating the OS/host/kernel does not automatically replace the Java runtime packaged inside the image. Even when the registry publishes a new tag, running containers still use the old image layer until redeployed.

Workflow:
1. Identify the JDK and digest in the current image.
2. Select the approved patched base image.
3. Rebuild the application image from that base.
4. Run tests, scan, and store provenance.
5. Deploy the new image digest.
6. Verify the JVM version/digest across **all new processes**.
7. Verify no old instances remain in rollout/DR.

For Java runtimes installed directly on hosts, use the vendor's package/installer mechanism and verify processes restarted to load the new runtime. Updating a file on disk does not necessarily change an already-started JVM.

## 21. Images Created with jlink Must Be Re-Linked from the Patched JDK

A team might run:

```bash
jdeps --print-module-deps --class-path "libs/*" app.jar
```

and create a runtime image:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging,java.sql \
  --output runtime-image
```

If the input JDK was replaced by a new patch yet **the old runtime-image was not recreated**, production still uses the old module code. Updating the JDK on the build machine does not automatically change an already-published `jlink` image.

Mandatory steps:
1. Identify the input JDK and provenance.
2. Re-link the image from the JMODs of the **patched JDK build**.
3. Check the binary with `runtime-image/bin/java -version`.
4. List modules from the image itself using `--list-modules`.
5. Check service providers, TLS, locale, charset, and native dependencies.
6. Generate an SBOM/attestation for the new runtime image.
7. Test the application on the **final packaged image**, not only on the full JDK.

Note: a module version list is not enough to prove individual CVE fixes; you must trace the image back to the exact JDK binary/vendor release. Modules such as `jdk.crypto.ec` or `jdk.localedata` may be needed depending on the application; do not apply a sample module list blindly to every service.

## 22. When the JDK Is Installed via an OS Package Manager

Linux distributions may distribute OpenJDK as OS packages, sometimes backporting security fixes and changing release suffixes according to their own policies.

Example inventory commands, **not upgrade commands**:

```bash
java -version
rpm -qa | grep -i openjdk
```

Or on systems using Debian packages:

```bash
dpkg -l | grep -i openjdk
```

Package names/commands depend on OS and distribution. If a JDK was installed manually into `/opt`, RPM/DEB listings may not show it; if multiple JDKs exist, the package manager may show several packages while the process runs a different binary.

When a vendor/distro backports fixes, **do not strictly compare against upstream versions** and conclude the machine is still vulnerable. Read the exact distro's advisory, package changelog, and installed package version, then confirm the actual process runs the patched binary.

## 23. Testing the Patch in a Production-Like Environment

A JDK patch can change:
- JSSE/TLS versions, cipher preferences, signature algorithms.
- Certificate paths/truststore and list of trusted CAs.
- Security properties such as disabledAlgorithms.
- JAXP/XML parser constraints or entity expansion limits.
- Networking, HTTP client, DNS/proxy behavior.
- ImageIO/ZIP/serialization and validation logic.
- Native/JNI APIs, platform libraries, font rendering.
- JIT, GC, memory ergonomics, or concurrency corner cases.
- Default behavior of JDK tools/code generation.

Therefore, before rollout, have a test environment representative of:
- JDK vendor/update/build and OS/CPU.
- Container base image, native packages.
- TLS termination/proxy/identity provider.
- Database, message broker, certificate chains.
- Traffic profile, data formats, and timezone/locale.
- Runtime launch flags and security configuration.

A test run on a developer laptop using a different vendor can catch basic bugs, yet **does not replace** verification on the target binary/image.

## 24. Regression Test Matrix After a JDK Security Update

| Test Area | What to Verify |
|---|---|
| JVM startup/health | No startup errors, proper module/provider resolution. |
| TLS inbound | Valid clients complete handshake; certificate chain and hostname validation work properly. |
| TLS outbound | Calls to IdP, APIs, DB TLS, SMTP, brokers use valid certificates. |
| Cryptography | Sign/verify, encrypt/decrypt, key storage, and algorithm restrictions. |
| XML/JSON/ZIP | Valid data is processed; malformed or malicious data is rejected. |
| Authentication/authorization | JWT/OIDC/SAML/session and access controls are not loosened. |
| HTTP/database/messaging | Business flows, transactions, queue retries, JDBC behavior. |
| File I/O/native | File permissions, JNI/JNA, encoding, timezone. |
| Scheduled jobs | Batch/infrequent jobs must run with representative fixtures. |
| Performance | P95/P99 latency, CPU, GC, memory, throughput. |
| Monitoring/agents | Metrics, tracing, profilers/Java agents have no compatibility errors. |
| Rollback | Recovery path runs cleanly and does not corrupt data. |

Criteria must be written explicitly in CI/release gates. “Passing unit tests” does not prove TLS certificates in partner environments are still accepted, nor does it prove a custom runtime contains all required providers.

## 25. Testing TLS After the JDK Changes Security Policy

A patch may add algorithms to disabled lists, tighten key lengths, or change certificate path validation configuration. This often exposes **existing weak configurations** on partners or servers.

Test:
1. TLS handshakes to critical endpoints.
2. Actual negotiated protocol/cipher suite.
3. Certificate chain, validity, hostname, and SAN.
4. Certificate revocation policy when required.
5. Client certificate/mTLS if applicable.
6. Proper loading of keystore/truststore.
7. Behavior when the server provides a weak, expired, or mismatched-hostname certificate.
8. Mutual compatibility between JDK runtimes during a mixed rollout.

Java code example using the public HTTPS API:

```java
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;

public class TlsSmokeTest {
    public static void main(String[] args) throws Exception {
        URL target = new URL("https://api.example.test/health");
        HttpsURLConnection connection =
                (HttpsURLConnection) target.openConnection();

        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);

        try {
            int code = connection.getResponseCode();
            System.out.println("HTTP status: " + code);
            System.out.println("Cipher suite: "
                    + connection.getCipherSuite());
        } finally {
            connection.disconnect();
        }
    }
}
```

This is an illustrative test for a test endpoint. HTTP status 200 does not by itself prove every policy is right: add negative tests for invalid/expired certificates and verify hostname verification **is not disabled**.

Do not fix `SSLHandshakeException` by installing a trust-all manager or disabling hostname verification in production. Identify the root cause: untrusted CA, incomplete certificate chain, weak algorithm, clock skew, disallowed TLS protocol, or misconfigured server.

## 26. Security Properties and Differences Between Images

JDKs have a security configuration file, usually located at:

```text
<JDK_HOME>/conf/security/java.security
```

Relevant properties may include:
- `jdk.tls.disabledAlgorithms`.
- `jdk.certpath.disabledAlgorithms`.
- `jdk.jar.disabledAlgorithms`.
- Crypto/security provider settings.
- XML parser/JAXP security limits at their corresponding configuration locations.

**You should not copy the entire `java.security` file from an old JDK to a new JDK** to “restore functionality”. Doing so can overwrite the security changes the patch just introduced.

On supported JDKs, you can view an overview of security settings using launcher options such as:

```bash
java -XshowSettings:security -version
```

Exact syntax and availability depend on the JDK; check `java -XshowSettings:help` or the launcher documentation of that exact release.

If overriding a security property is necessary:
1. Prove it is genuinely required.
2. Define a narrow scope.
3. Assess risk, with owner/security approval.
4. Do not use the override to disable the patch.
5. Set an expiration date and a test to remove the override.

## 27. Truststore and Root Certificates Can Change After a Patch

A JDK update sometimes changes CA certificates or trust policy. Applications may connect to:
- Public HTTPS services.
- Enterprise private PKI.
- Database or broker mTLS.
- OAuth/OIDC discovery/JWKS endpoints.
- Third-party payment/service APIs.

Items to cross-check:
- Truststore in use: JDK default or custom?
- Was the truststore file copied from the old image to the new image?
- Are any intermediate certificates missing?
- Does the certificate chain have valid algorithms/key sizes?
- Is the environment's clock/timezone accurate?
- Were any CAs removed or trust anchors updated?

A certificate store inventory command when permitted:

```bash
keytool -list -keystore "path/to/truststore.p12" \
  -storetype PKCS12
```

If a password is required, **do not place plaintext passwords directly on the command line or in documentation**. Use your organization's secure input/secret manager mechanism. The command above is illustrative only; there is no need to open or dump the entire certificate store into a ticket.

### 27.1. Policy for Removed CAs

If a vendor removes an untrusted root CA, re-adding it to the truststore just to temporarily turn TLS “green” can reopen risk. Prioritize:
- Fixing the server/certificate chain.
- Switching to an appropriate, still-trusted CA.
- Coordinating with the partner to replace the certificate.
- If an exception is unavoidable, requiring explicit approval, scope, and expiry.

## 28. Checking JAR Signatures and Disabled Algorithms

A patch may tighten JAR signing algorithm policies. A plugin/distribution JAR previously signed with a weak algorithm may no longer satisfy the security policy as before.

When needing to inspect a signed artifact:

```bash
jarsigner -verify -verbose -certs signed-library.jar
```

Results must be interpreted alongside the current JDK's policy and certificate chain. Do not conclude authenticity/signature safety merely because the command reports no fatal errors; verify the signer, trust, and algorithm policy.

If a signer is found using a disabled algorithm:
1. Request a re-signed release from the library/vendor.
2. Check the original artifact and supply-chain provenance.
3. Do not disable `jdk.jar.disabledAlgorithms` yourself to keep using an untrusted JAR.
4. Record release/owner details and impact on runtime/build plugins.
## 29. Handling Parser, Serialization, and Input Validation Changes

A security update can alter parser limits or how untrusted data is handled. This is often mistaken for “a Java update broke business logic” when code previously relied on permissive behavior.

Areas to watch:
- XML parsers, XSLT, XPath, DOM/SAX, and entity resolution.
- ZIP/JAR processing, decompression, and data sizes.
- Object deserialization and library codecs.
- ImageIO when processing external images.
- Character encoding, Unicode normalization, and malformed input.
- File path validation, canonicalization, and archive extraction.
- Security defaults of JNDI/RMI in legacy systems.

Minimum tests:
1. Valid inputs still process per contract.
2. Historical data remains readable while the product still commits to supporting it.
3. Malformed, oversized, or untrusted inputs are rejected properly.
4. Parsers do not accidentally enable dangerous external entity/resource access.
5. Error handling does not cause timeouts, unbounded resource growth, or secret leaks.
6. If intentional behavior changes occur, internal release notes and contract tests are updated with review.

Do not restore permissive configurations just to make old tests pass. Determine whether **the test expected wrong behavior because old behavior was unsafe** or whether the patch introduced a regression to report to the vendor.

## 30. Testing Combinations of JNI Libraries, Agents, and JDK Tools

A JDK security patch can simultaneously alter how native libraries, JDK tool classes, or compiler/JIT/serviceability parts behave. Commonly under-tested paths:
- JNI/JNA libraries depending on native ABI.
- APM Java agents, instrumentation/bytecode transformation.
- Profiling/debugging/attach tools.
- Annotation processors and dynamic compilation.
- Java management/monitoring agents.
- Native encryption/compression modules.
- Code paths that only run on aarch64 or a specific Linux distribution.

After upgrading the JDK build, run smoke/integration tests on the exact OS/architecture. A vendor may release binaries for different platforms at different times; verify that each image **exists and has been tested** before rollout.

If a profiler/agent is incompatible with the new JDK release, upgrade the agent or change data collection according to the support matrix. Do not block a security patch indefinitely just because an auxiliary tool has not yet been updated; decide on risks and an appropriate temporary plan.

## 31. Security Testing Needs Negative Cases

A security patch can close an exploitation path that the application previously allowed unintentionally. Security tests should specify behaviors that must be **rejected** as well.

| Component | Positive Case | Negative Case |
|---|---|---|
| TLS client | Valid certificate/matching hostname connects. | Wrong-hostname/expired/revoked certificate is rejected. |
| JWT/OIDC | Valid token, right issuer/audience, sufficient scope passes. | Bad-signature, expired, wrong-issuer, or insufficient-scope token is rejected. |
| XML parser | Schema-valid XML is processed. | Payload exceeding limits or attempting unintended entity access is rejected. |
| Deserializer | Valid historical data is read. | Untrusted polymorphic types cannot instantiate dangerous objects. |
| File/archive | Valid archive extracts into allowed directory. | Path traversal and oversized payloads are blocked. |
| Truststore | Partners using valid CA/cert still connect. | Cert from untrusted CA is rejected. |
| JAR signature | Artifact signed per policy is accepted. | Invalid signature/algorithm is not accepted. |

Tests must use safe fixtures in a managed environment; do not perform exploitation against systems outside your ownership. When testing security, do not create a “test exception” by disabling default checks and letting it leak into production config.

## 32. CI/CD: Where to Place the Security Patch Gate?

A recommended pipeline:

```text
                Patch advisory / trigger
                          |
                          v
                Select vendor build
                          |
                          v
             Verify signature/checksum
                          |
                          v
              Pin JDK & image digest
                          |
                          v
                Rebuild application
                 + jlink if used
                          |
                          v
             Generate inventory / SBOM
                          |
                          v
            SCA + runtime security scan
                          |
                          v
               Unit + integration tests
                          |
                          v
             Security/TLS contract tests
                          |
                          v
             Performance smoke/load tests
                          |
                          v
                Canary rollout
                          |
                          v
            Verify running JVM/build/digest
                          |
                          v
                 Release approval
```

Maven projects can use:

```bash
mvn verify
```

Gradle projects can use:

```bash
./gradlew test
```

Commands in this lesson are **usage instructions for applicable projects**, not a requirement to execute them while authoring documentation. For integration tests, use the task/phase defined by the project and a real test environment.

A new patch sometimes does not change source APIs yet impacts integration; do not skip all tests just to shorten security update release time. You can structure a **fast security gate** and a **full regression suite** with clear risk levels, but any decision to shorten testing must be approved.

## 33. GO/NO-GO Decision Gate

Before release, answer:

| Gate | Verifiable Condition | If Not Met |
|---|---|---|
| Binary provenance | JDK binary/digest from approved source. | Block release or request untrusted-source handling. |
| Vendor patch status | Build contains required fixes per advisory. | Select another build or log a blocker. |
| Vulnerability triage | CVEs classified as affected/not affected/mitigated. | Security review and action owner. |
| Test correctness | Critical flows have no regressions. | Fix issue, re-test. |
| Security regression | Negative tests do not loosen permissions/reduce trust. | Block or handle per security policy. |
| Operational readiness | Rollout, observability, and rollback/forward-fix ready. | Prepare additional readiness. |
| Environment parity | CI, staging, prod, DR have corresponding update plans. | Do not mark “system-wide complete”. |
| Evidence | Artifacts, versions, digests, test reports, sign-off stored. | Cannot close out yet. |

An emergency advisory may require faster handling than a standard release, yet does not permit completely bypassing source integrity and security testing. Define a separate **emergency approval path** in advance, instead of breaking the checklist ad hoc when an incident occurs.

## 34. Canary Rollout and Verifying the Patch on Live Processes

A rollout path:

```text
Old runtime image
       |
       v
Patched build in staging
       |
       v
Canary small traffic set
       |
       v
Security & reliability metrics OK?
     /                 \
    No                 Yes
    |                   |
    v                   v
Contain/diagnose     Expand rollout
    |                   |
    v                   v
Mitigate/forward-fix   All instances updated
                        |
                        v
              Verify actual JVM build
                        |
                        v
               Update baseline record
```

Observed metrics:
- Startup failures, crashes/restarts/OOM.
- TLS handshake failures and certificate validation errors.
- HTTP 4xx/5xx, authentication/authorization errors.
- Connection pool health, DB/broker/IdP connectivity.
- CPU, memory, GC, P95/P99 latency.
- Queue lag and scheduled job completion.
- Security detections/scan findings.
- Count of workloads still using the old image digest.

**Simply deploying a new container tag is not enough.** Verify the actual runtime JDK/digest on instances after rollout, including autoscaled workers and disaster recovery zones.

## 35. Rollback After a Security Patch Must Be Evaluated Separately

Rolling back a patch can put a **vulnerable** JDK version back into production. Therefore, two risks must be balanced:

- **Functional risk:** the new patch causes a severe regression.
- **Security risk:** the old version contains an unpatched CVE.

Do not define “safe rollback” as unconditionally returning to the pre-patch JDK. Prepare multiple options:

1. **Forward-fix:** keep the patched JDK and fix the application/config causing the regression if possible.
2. **Switch to another supported patched build:** if the vendor provides a suitable equivalent fix.
3. **Narrow scope/disable affected feature:** isolate the functional path during remediation without opening new vulnerabilities.
4. **Temporary rollback with exception:** only when evaluated, approved, time-bounded, monitored, and paired with risk-limiting controls.
5. **Rollback deployment data/config:** if the patch was inadvertently bundled with application state changes, check data compatibility.

If a vulnerability is under active exploitation, reverting to the old version may be prohibited by security policy. The plan should have a **decision tree prioritizing keeping the patch** rather than treating the old version as “known good” in all cases.

## 36. Handling Emergency or Out-of-Cycle Patches

A rapid-response playbook:

```text
Vendor advisory/security alert
             |
             v
Determine affected JDKs and assets
             |
             v
Rate exposure and exploitability
             |
             v
Is a trusted fixed build available?
           /      \
         Yes       No
          |         |
          v         v
    Rapid build    Vendor mitigation/
    + test         containment plan
          |         |
          +----+----+
               |
               v
       Security approval/release
               |
               v
       Verify deployed builds
               |
               v
        Re-scan and close
```

Define in advance:
- Who monitors advisories?
- Who can identify affected assets?
- Who has authority to approve hotfixes?
- To what degree is test reduction permitted?
- If the vendor lacks binaries for our OS/architecture yet, what is the escalation path?
- If temporary mitigation is needed, who owns the expiry?
- How do we prove no old runtimes remain running?

Do not set an arbitrary promise like “every CVE fixed in 24 hours” without an internal SLO; response deadlines must follow severity, exposure, and organizational policy.

## 37. When No Official Patch Is Available Yet

Situations can occur where:
- Upstream discloses an issue but the vendor build is not ready yet.
- A platform is unsupported or an update must pass vendor verification.
- The Java LTS branch in use has reached end-of-support.
- A fix is released but breaks a required compatibility behavior.

Possible mitigations include:
- Blocking or restricting relevant inputs/exploitation paths.
- Restricting network reachability, authentication, and least privilege.
- Disabling non-mandatory features exposing the vulnerable component.
- Using **official** config mitigations described by the vendor.
- Temporarily isolating workloads, or switching to a patched build from another supported vendor if tested.
- Increasing monitoring and anomaly detection.
- Recording an exception with owner, impact level, expiry, and re-check trigger.

A mitigation **does not automatically equal a patch**. Once the official binary is ready, still complete the update/verification workflow. Do not invent undocumented “disable CVE” flags.

## 38. Organizing a Continuous Patch Tracking Schedule

After a major upgrade, it is easy to fall into “it's stable on Java 21, we'll leave it for a few years.” Yet a JDK release still needs security updates throughout its lifecycle.

An iterative process:
1. Monitor vendor security advisories, release notes, and official announcement channels.
2. Whenever a CPU/CSPU/security alert arrives, evaluate assets in use.
3. Update the approved JDK build baseline.
4. Produce patched artifacts/images and scan/test.
5. Deploy according to priority and risk.
6. Verify the actual runtime across all workloads.
7. Store evidence, close issues/tickets, and update inventory.
8. Re-check open exceptions/mitigations.

Periodic reporting can be automated: unpatched image count, assets with unknown JDK builds, untriaged CVEs, overdue exceptions, canary results. However, **applicability/rollback decisions** for critical CVEs still require evaluation by domain-expert owners.

## 39. Release Patch Record Template

Example:

```yaml
patchCampaign:
  id: "JAVA-SECURITY-UPDATE-EXAMPLE"
  description: "Verify approved JDK security patch level"
  advisoryWindow: "2026-10"
  owner: "platform-security"
  status: "in-progress"

targetRuntime:
  featureVersion: "21"
  vendor: "approved-distribution"
  approvedBuild: "21.0.x+approvedBuild"
  source: "official-vendor-release-notes"
  artifactDigest: "sha256:replace-with-verified-digest"

scope:
  applications:
    - "order-api"
    - "order-worker"
    - "monthly-report"
  environments:
    - "ci"
    - "staging"
    - "production"
    - "disaster-recovery"

securityAssessment:
  advisoriesReviewed: true
  affectedCves:
    - id: "CVE-YYYY-NNNNN"
      status: "pending-verify"
      component: "JSSE"
  approvedExceptions: []

validation:
  integrity: "pending"
  runtimeVersion: "pending"
  smokeTests: "pending"
  tlsContracts: "pending"
  integrationTests: "pending"
  imageScan: "pending"
  rollout: "pending"

evidence:
  vendorAdvisory: "vendor-url"
  jdkReleaseNotes: "vendor-url"
  ciRun: "ci-link"
  imageDigest: "registry-digest"
  testReport: "report-link"
  deploymentVerification: "runtime-inventory-link"

approvals:
  security: "pending"
  serviceOwner: "pending"
  operations: "pending"
```

This is a workflow tracking template, not a JVM configuration file. `pending` values and placeholders must be replaced with real evidence before closing the issue; do not mark `advisoriesReviewed: true` just because a link was opened.

## 40. Before-and-After Patch Comparison Report Template

| Item | Before | After | Evidence |
|---|---|---|---|
| JDK vendor | Vendor A | Vendor A | `java -version` on process. |
| JDK build | 21.0.x+old | 21.0.y+new | Runtime inventory. |
| Image digest | Old digest | Approved digest | Container registry/deployment. |
| CVE status | Open/pending | Fixed/mitigated with basis | Advisory + vendor notes. |
| TLS handshake | Baseline | Pass/fail per contract | Integration test. |
| Security tests | Baseline | Pass | CI report. |
| SLO | Baseline | Within budget | Canary dashboard. |
| Old instances | N instances | 0 in scope | Deployment inventory. |
| DR/runtime | Not upgraded | Upgraded/verified | DR verification. |

You do not need to try updating every environment simultaneously in a single deployment if the rollout strategy does not permit it, yet only mark complete once the **approved scope** has been reached or exceptions have been formally declared.

## 41. Common Mistakes

**“We're on Java LTS so we don't need to track CVEs.”** LTS is only useful when continuing to receive and deploy security updates.

**“Java 21 is the latest patch.”** The major number does not express patch level; full update/build is needed.

**“Oracle has a CPU, so every vendor has binaries the same day.”** Upstream release schedules and vendor binary build/test schedules can differ; confirm actual releases.

**“A green scanner means the JDK is safe.”** Scanners may miss embedded/custom runtimes or vendor backports.

**“If the scanner reports a CVE, it definitely still exists.”** Rules may not know about backports; release-notes/vendor evidence and a false-positive handling policy are needed.

**“The host was updated, so container JVMs are patched too.”** Old immutable images still contain the old runtime until rebuilt/redeployed.

**“The build machine JDK was updated, so jlink images are automatically updated.”** Custom runtimes must be re-linked and re-released.

**“The patch is only security-related, no regression tests needed.”** Security defaults, certificate trust, and parser behavior can change.

**“If TLS isn't working, disable hostname verification to be fast.”** Introduces a severe security flaw, not a safe migration.

**“Rolling back to the old JDK is always the safe option.”** The old release may contain an actively exploited vulnerability; assess risk and prioritize a patched forward-fix.

**“Only main production needs patching.”** DR, batch, sidecars, CI tools, and rare jobs are still at-risk assets.

**“Mark fixed just because a new image was built.”** Verify the binary inside running processes and the actual version/digest.

## 42. Checklist Before Approving the Selected JDK Version

- [ ] Finalized JDK feature version, update version, build, and vendor/distribution.
- [ ] Have compatibility/support matrix for OS/architecture and target JDK line.
- [ ] Cross-checked latest vendor security advisories and release notes as of the review date.
- [ ] Did not rely solely on quarterly CPU schedules; accounted for out-of-cycle CSPUs/alerts.
- [ ] Classified affected/not affected/fixed/mitigated for in-scope CVEs.
- [ ] Obtained backport evidence if the version string might cause false positives.
- [ ] Verified checksum/signature/provenance of downloaded binaries.
- [ ] Have inventory/runtime evidence for all apps, batches, workers, CI, and DR in scope.
- [ ] Verified the actual JDK inside processes, not just `JAVA_HOME` on the host.
- [ ] Rebuilt Docker images and recorded digests; did not merely swap tags.
- [ ] Recreated custom `jlink` images from the patched JDK.
- [ ] Have an SBOM or software inventory for runtime and application dependencies.
- [ ] Have security scan results and explained findings/unrecognized components.
- [ ] Ran appropriate smoke, unit, integration, and negative security tests.
- [ ] Checked TLS/PKIX, certificate trust, crypto providers, and JAR signatures if applicable.
- [ ] Checked XML/JSON/ZIP/file parsing and untrusted input restrictions.
- [ ] Verified JDBC/messaging/authentication and external integrations.
- [ ] Measured performance/GC/memory and critical SLOs.
- [ ] Have canary rollout, monitoring, and approved forward-fix/rollback paths.
- [ ] Did not use trust-all TLS, disabled security policies, or uncontrolled workarounds.
- [ ] Confirmed all in-scope instances/deployments run the exact build/digest.
- [ ] Open exceptions have owners, due dates, and mitigations.
- [ ] Stored advisory links, build outputs, image digests, test evidence, and sign-off.
- [ ] Have a process to re-verify patch levels for future updates.

## 43. References

- [Oracle Security Alerts, Critical Patch Updates and Security Bulletins](https://www.oracle.com/security-alerts/): official advisory source.
- [Oracle Critical Patch Update Advisory — October 2026](https://www.oracle.com/security-alerts/cpuoct2026.html): example of how to read the Java SE risk matrix, affected products/versions, and CVE metadata.
- [Oracle Java Security Update Cadence (September 2026)](https://blogs.oracle.com/java/transitioning-java-to-more-frequent-security-updates): information on shifting toward more frequent patch releases than a quarterly cadence.
- [Eclipse Temurin Support and Release Roadmap](https://adoptium.net/support/): release schedule, lifecycle, and differences between upstream timing and Temurin binaries.
- [Adoptium Secure Software Development Practices](https://adoptium.net/docs/secure-software): the distribution's provenance and SBOM practices.
- [OpenJDK Vulnerability Group](https://openjdk.org/groups/vulnerability/): upstream vulnerability work and advisory information.
- [OpenJDK JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): basis of runtime images and the need to re-link when patching.
- [Java SE 21 System Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): `java.version`, `java.vendor`, and `java.home` details.
- [Java SE 21 java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-version`, `-XshowSettings`, and diagnostic options.
- [JDK 21 jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): inspecting JVM processes.
- [JDK 21 jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): creating modular runtime images.
- [JDK 21 keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): inspecting keystores/truststores.
- [JDK 21 jarsigner](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): checking JAR signatures.
- [CycloneDX](https://cyclonedx.org/) and [SPDX](https://spdx.dev/): SBOM formats.
- [NIST National Vulnerability Database](https://nvd.nist.gov/): supplemental CVE/CVSS information source; does not replace vendor advisories.
- [CVE Program](https://www.cve.org/): CVE identifier and record information.

## Conclusion

**Re-verifying security patches on the selected JDK version** is a mandatory step between the Java platform decision and release/operations decisions. A product using Java 17 or Java 21 can still be vulnerable if it runs an **old update build**, lacks trusted binary provenance, or runs a container/jlink image not rebuilt after a new patch.

A verifiable approach is: identify the **exact vendor + full version/build + image digest**, read vendor advisories and CPU/CSPU schedules, evaluate CVEs by component/risk, confirm the fix is inside the binary, and run security/compatibility tests on the runtime to be deployed. After canary, verify that **running processes** actually use the approved build, while storing evidence, owners, exceptions, and the next update plan. JDK patching is not a “one-time migration activity”; it is an ongoing operational process to keep Java systems compatible and secure after the upgrade project concludes.




