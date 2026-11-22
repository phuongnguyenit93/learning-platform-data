# Java Runtime Security Audit

A **runtime security audit** is the process of inspecting the JDK/JRE running an application, along with its security configuration, dependencies, certificates, network connections, JVM arguments, operating system permissions, and operational evidence. The goal is to identify exploitable weaknesses in a real-world environment, assess their impact, and produce verifiable remediation actions.

A secure Java application does not depend on source code alone. The exact same JAR can carry very different levels of risk depending on the JDK in use, security providers, truststore, TLS configuration, JVM flags, process privileges, secret management, and how it is deployed on a host or container.

This lesson uses tools built into JDK 17 and later, with specific notes on major changes starting in JDK 24. These inspection commands are evidence-gathering steps; they do not replace penetration testing, architecture reviews, or organizational policy reviews.

## 1. Scope of a runtime security audit

An audit should cover both the Java configuration and the environment surrounding the JVM.

| Scope | Questions to answer | Typical evidence |
|---|---|---|
| JDK/runtime | Which vendor, version, and patch level is running? Is it still supported? | java --version, image/package metadata |
| Security properties | Are weak algorithms, legacy protocols, or unwanted providers enabled? | java -XshowSettings:security |
| Dependency | Are there outdated libraries, internal APIs, or dependencies of unknown origin? | SBOM, SCA report, jdeps |
| Artifact | Does the JAR have valid signatures, unsigned entries, or untrusted signers? | jarsigner -verify |
| Certificate/keystore | Are certificates valid, used for the right purpose, and trusted by the chain? | keytool, certificate inventory |
| TLS/network | Which TLS version does the live endpoint use, and are hostname validation and trust configured properly? | JSSE config, endpoint scan, handshake evidence |
| JVM process | Are there agents, debug ports, module overrides, or sensitive system properties? | jcmd, process/service configuration |
| OS/container | Does the process run with least privilege and access only required resources? | OS identity, filesystem/network policy |
| Secrets | Are passwords, tokens, or private keys exposed in args, env, logs, or dumps? | Secret inventory, log review |
| Logging/response | Is there an audit trail and an incident response process? | Log policy, alert, incident runbook |

Define the system scope upfront: production, staging, or development environment; which services, JARs, plugins, native libraries, and runtime images are deployed; the minimum Java version to support; and who is responsible for remediating each finding.

Do not collect unnecessary sensitive data. Outputs such as JVM command lines, system properties, environment variables, heap dumps, and thread dumps can contain secrets or user data. Restrict access and redact sensitive data before attaching it to tickets or reports.

## 2. Inspecting the running JDK and runtime

Start by identifying the exact runtime. Do not just record "Java 17" or "Java 24"; record the vendor, build number, architecture, and installation location.

~~~bash
java --version
javac --version
jcmd -l
~~~

Meaning:

- java --version displays the JDK/JRE invoked by the launcher.
- javac --version confirms the compiler if a full JDK is installed on the machine.
- jcmd -l lists local JVM processes visible to the current account.

A machine can have multiple JDKs installed. The `java` command in `PATH` is not necessarily the runtime used by the production service. Check the service unit, Windows service, container image, startup script, and `JAVA_HOME` variable of the actual process.

### Information to record

- Full JDK vendor and version.
- Build number and release date.
- CPU architecture and operating system.
- Installation source: package manager, container base image, archive, or internal image.
- Date of the most recent security update.
- Vendor end-of-support date.
- Any JDK differences across build, test, staging, and production.

Do not choose a JDK simply because it is the latest available version. Choose a vendor-supported release that meets update policies and has been tested with the application. Also establish a regular security patch schedule and an emergency patching process.

### Inspecting runtime images

If the application runs on a runtime image created with `jlink`, identify which JDK created the image and which modules are packaged inside it. A minimal runtime image reduces unnecessary components, but it does not guarantee security on its own. You still need to update the image when security fixes are released and verify dynamic dependencies, providers, locale data, TLS support, and the components actually required.

## 3. Inspecting security properties and providers

The Java Security Architecture uses security properties to configure providers, algorithms, default keystores, TLS, and other security mechanisms. Actual configurations can vary across vendors, releases, and override files.

### Printing active security settings

JDK 17 and later support the following forms:

~~~bash
java -XshowSettings:security -version
java -XshowSettings:security:properties -version
java -XshowSettings:security:providers -version
java -XshowSettings:security:tls -version
~~~

Specific forms:

- security:properties displays the active security properties.
- security:providers displays the providers and their priority order.
- security:tls displays the TLS configuration of the JSSE provider.
- security prints a combined summary of security information groups.

These are diagnostic commands. Output can be lengthy and varies by JDK/vendor; store the results alongside the runtime version and restrict access.

### Security properties to watch

| Property | Audit purpose |
|---|---|
| jdk.tls.disabledAlgorithms | Protocols, cipher suites, key exchanges, or TLS algorithms disallowed from negotiation |
| jdk.certpath.disabledAlgorithms | Algorithms/key sizes restricted during certificate path validation |
| jdk.jar.disabledAlgorithms | Algorithms rejected when verifying signed JARs |
| jdk.security.legacyAlgorithms | Weak or older algorithms classified as legacy |
| security.provider.n | Cryptographic providers and implementation lookup order |
| keystore.type | Default keystore type |
| ssl.KeyManagerFactory.algorithm | Default KeyManagerFactory algorithm |
| ssl.TrustManagerFactory.algorithm | Default TrustManagerFactory algorithm |
| securerandom.source | Configured entropy source for SecureRandom |
| jdk.tls.keyLimits | Data encryption limits per TLS key set |

Do not just check whether a property exists. Compare the active values against your organization's baseline, the JDK vendor defaults, and compatibility requirements. A property can be altered by a custom configuration file, startup arguments, or another security provider.

### Inspecting configuration files and overrides

On modern JDKs, the master security properties file is typically located at:

~~~text
<java-home>/conf/security/java.security
~~~

Inspect the file belonging to the deployed runtime and any additional files loaded via configuration. Look for startup arguments related to:

~~~text
-Djava.security.properties=...
-Djava.security.properties==...
~~~

The single-equals form loads an additional properties file according to the JDK's configuration rules; the double-equals form replaces the master security properties file. Carefully review every override because it can change providers, algorithm constraints, or TLS behavior. Do not modify the default file directly without configuration management, review, and compatibility testing.

### Inspecting providers

Providers are implementations of cryptographic services such as Signature, MessageDigest, Cipher, KeyStore, SecureRandom, and TLS. The audit should verify that:

- Providers come from approved sources and versions.
- Provider order matches the intended design.
- No unexpected providers are added via startup options or security files.
- Native/HSM/PKCS#11 providers are properly configured and protected.
- Critical algorithms actually have compatible implementations.
- Provider updates follow a testing and rollback process.

Do not automatically remove a provider simply because its name is unfamiliar. Several providers are standard JDK components or serve smart cards, HSMs, LDAP, Kerberos, and TLS.

## 4. Major change in JDK 24: Security Manager is disabled

The Security Manager was previously used to restrict certain Java code operations through permission checks. It was deprecated for removal in JDK 17 and **permanently disabled in JDK 24** under JEP 486.

This has direct implications for audits:

- The Security Manager cannot be enabled at JVM startup in JDK 24 or later.
- A custom Security Manager cannot be installed at runtime.
- Related APIs may return null/false, allow operations to proceed, or throw exceptions depending on JDK changes.
- System/security properties that only served the Security Manager are no longer effective protection mechanisms.
- Security Manager policy files no longer act as an application sandbox in JDK 24.

Do not treat legacy policy configurations as evidence that the application is privilege-restricted. If a system previously relied on the Security Manager to isolate plugins or untrusted code, redesign the security boundary.

### Alternative isolation approaches

Use operating system or infrastructure-level boundaries:

- Run services under dedicated accounts without administrator/root privileges.
- Restrict filesystem read/write permissions and grant access only to required directories.
- Run inside properly configured containers or sandboxes; avoid privileged mode.
- Restrict network ingress/egress to required services and ports.
- Use seccomp, AppArmor, SELinux, or equivalent mechanisms where supported by the platform.
- Isolate plugins or untrusted code into separate processes or containers.
- Limit CPU, memory, file descriptors, process count, and execution time.
- Do not use the module system as a security sandbox for untrusted code.

Module boundaries and encapsulation help organize APIs; they do not replace OS access control. If untrusted code must be executed, design communication over IPC with an isolated, least-privilege process.

## 5. Auditing dependencies and JDK internal APIs

Dependencies are part of the attack surface. A vulnerable library can compromise the application even if the team's own code has no direct bugs.

### Building a dependency inventory

Collect:

- Direct and transitive dependencies.
- Versions, checksums, and repository sources.
- JARs packaged inside the application or plugins.
- Native libraries and libraries loaded at runtime.
- SBOM of the released artifact.
- CVE findings from Software Composition Analysis (SCA) tools.
- Licenses, provenance, and dependency update policies.

`jdeps` analyzes static dependency relationships; it is not a CVE scanner. Combine the dependency inventory with an SCA scanner, vulnerability databases, and a process for tracking vendor advisories.

### Finding dependencies on JDK internal APIs

~~~bash
jdeps --jdk-internals app.jar
~~~

This command finds class-level dependencies on JDK internal APIs. According to `jdeps` help, this option cannot be combined with summary, package filters, or regex filters. Run it as a separate step.

If the application uses internal APIs, prioritize migrating to supported Java SE APIs. Flags such as `--add-exports` or `--add-opens` allow code to access otherwise encapsulated packages; document each case, its owner, justification, and removal plan.

### Finding APIs deprecated for removal

~~~bash
jdeprscan --release 24 --for-removal app.jar
~~~

Select the release matching your target runtime. Run a full scan as well if you need an inventory of all deprecated APIs, since `--for-removal` focuses only on APIs marked for removal.

### Limitations of static analysis

`jdeps` and `jdeprscan` cannot see every dependency created dynamically via reflection, plugins, configuration, or native code. Supplement them with runtime checks, searching for class names in configuration files, reviewing `ServiceLoader`/plugin registries, and testing actual deployment profiles.

## 6. Verifying artifacts and digital signatures

Do not deploy JARs of unknown origin to production just because they can be downloaded from a repository. Artifact audits must verify checksums, download sources, signatures, signer identity, and certificate chains.

### Verifying signed JARs

~~~bash
jarsigner -verify -strict -verbose -certs app.jar
~~~

- verify checks the JAR's signatures and digests.
- verbose displays detailed status per entry.
- certs displays certificate information during verification.
- strict causes severe warnings to affect the exit code.

You must distinguish between a mathematically valid signature and a trusted signer. A JAR signed with a self-signed certificate can have valid digests and signatures while still failing your organization's trust policy.

### Checking checksums and artifact provenance

Compute the SHA-256 hash using OS tools or the build pipeline and compare it against the checksum from a trusted release channel. A checksum does not replace a digital signature; it only verifies the exact bytes of the artifact.

Record:

- Artifact name and version.
- Repository or release source.
- SHA-256 checksum.
- Signer certificate fingerprint.
- Subject, issuer, and validity period.
- `jarsigner` strict verification result.
- JDK/vendor used for verification.
- Findings of unsigned entries or disabled algorithms.

## 7. Auditing keystores, truststores, and certificates

A keystore typically stores private keys, secret keys, or trusted certificates. A truststore contains certificates accepted as trust anchors or used during peer authentication.

### Listing entries in a keystore

~~~bash
keytool -list -v -keystore app-keystore.p12 -storetype PKCS12
~~~

`keytool` prompts interactively for a password if needed. Verbose output can show the alias, entry type, Subject, Issuer, serial number, validity period, fingerprint, and certificate extensions.

Do not confuse entry types:

- PrivateKeyEntry contains a private key and certificate chain.
- SecretKeyEntry contains a symmetric key.
- TrustedCertificateEntry contains a trusted public certificate.

### Inspecting the default truststore

~~~bash
keytool -list -v -cacerts
~~~

This command inspects the runtime's default `cacerts` truststore. If the application configures a custom truststore, inspect that exact file instead of checking only `cacerts`.

### Inspecting a standalone certificate

~~~bash
keytool -printcert -file partner-ca.pem
~~~

Verify the SHA-256 fingerprint against information received through an independent, trusted channel before importing a certificate as a trusted entry.

### Key audit checkpoints

- Aliases have clear names and assigned owners.
- Private keys are protected by minimal file permissions or an HSM/token.
- Certificates are within their validity period and used for their intended purpose.
- Subject Alternative Names match hostnames/services.
- KeyUsage and ExtendedKeyUsage match server/client/code signing roles.
- Certificate chains resolve to an approved trust anchor.
- No stale CAs, expired certificates, or entries of unknown origin remain.
- Renewal, rotation, and revocation schedules are in place.
- Keystore backups are encrypted, access-controlled, and tested for restoration.
- Passwords are not stored in source code, command history, or public config files.

Never export or send private keys as audit evidence. Collect only the necessary metadata and fingerprints.

## 8. Auditing TLS and connection configuration

Java Secure Socket Extension (JSSE) provides TLS/DTLS, encryption, server authentication, message integrity, and optional client authentication.

### Viewing the JDK's TLS configuration

~~~bash
keytool -showinfo -tls
java -XshowSettings:security:tls -version
~~~

Both commands display the protocols and cipher suites enabled in the current configuration/provider. On OpenJDK 24.0.2 tested, the output shows TLSv1.3 and TLSv1.2 enabled. Actual results vary by vendor, version, provider, and security properties.

This output does not prove that the application's endpoints negotiate those exact protocols. An application may use a custom `SSLContext`, `SSLParameters` configuration, a proxy, or TLS termination at a load balancer. Inspect both the live network endpoint and the service configuration.

### TLS-related security properties

- jdk.tls.disabledAlgorithms: protocols/ciphers/key exchanges prohibited in TLS negotiation.
- jdk.certpath.disabledAlgorithms: algorithm restrictions in certificate path validation.
- jdk.tls.legacyAlgorithms: legacy algorithms not preferred during negotiation.
- ssl.TrustManagerFactory.algorithm: default TrustManagerFactory algorithm.
- ssl.KeyManagerFactory.algorithm: default KeyManagerFactory algorithm.

Oracle JSSE documentation explains that disabled algorithms can prevent negotiating a protocol or cipher suite even if the application explicitly tries to enable it.

### TLS checks to perform

1. Endpoints support only policy-approved protocols.
2. SSLv3, TLS 1.0, and TLS 1.1 are disallowed in modern environments.
3. Weak, NULL, anonymous cipher suites, or insecure key exchanges are not used.
4. Certificates have valid SANs matching the hostname and are not expired.
5. Clients verify hostnames and certificate chains.
6. No TrustManager accepts all certificates.
7. Hostname verification is never disabled to work around connection errors.
8. If mutual TLS is used, both client and server certificates are verified.
9. Certificate rotation, revocation policies, and OCSP/CRL are checked where appropriate.
10. TLS termination at reverse proxies/load balancers is audited, not just the backend JVM.

### Avoiding insecure trust configurations

Do not use custom TrustManagers that unconditionally trust everything, do not install truststores containing arbitrary certificates, and do not disable hostname verification. If an internal CA must be added, add only verified trust anchors and limit their blast radius.

Parameters such as `javax.net.ssl.trustStore`, `javax.net.ssl.keyStore`, and store types should be reviewed in startup configurations. Never pass keystore passwords via command-line system properties, as they can be exposed through process inspection or diagnostic output.

## 9. Inspecting JVM arguments and runtime access

Some JVM options can broaden access or enable remote diagnostic interfaces. Audits must inspect the command line of the actual service.

### Listing JVM processes

~~~bash
jcmd -l
~~~

### Inspecting a specific process

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> help
~~~

Replace `<pid>` with the actual process ID. The process `help` command lists the diagnostic commands supported by that JVM.

These commands may require the same user/OS identity as the JVM. `jcmd` is a powerful administrative tool; restrict who can attach and who is permitted to run diagnostic commands.

### Options to review

| Option or option group | Risk to evaluate |
|---|---|
| -agentlib:jdwp | Enables the Java debugger; never leave debug ports open on production networks |
| -javaagent | Agents can instrument and modify bytecode |
| -agentpath | Loads native agents with process-level privileges |
| --add-opens | Opens packages for deep reflection |
| --add-exports | Exports internal packages to other modules |
| --patch-module | Replaces or augments module contents |
| -Djava.security.properties | Modifies security configuration |
| -Djavax.net.ssl.* | Modifies keystore/truststore or TLS behavior |
| -Djava.io.tmpdir | Affects where temporary files are written |
| -XX:+HeapDumpOnOutOfMemoryError | May produce heap dumps containing sensitive data |

Not every option in this table is automatically a vulnerability. Identify the reason, scope, and owner; remove options that are no longer needed and protect diagnostic data.

### Debug ports and JMX

- Do not enable a JDWP listener on public interfaces in production.
- If remote management is required, use authentication, TLS, firewalls, and appropriate network binding.
- Do not enable unauthenticated remote JMX.
- Restrict who can attach using `jcmd` or access local management interfaces.
- Do not expose administrative ports, actuators, or diagnostic endpoints to the Internet.

### System properties and command lines may contain secrets

`VM.command_line` and `VM.system_properties` can print values passed with `-D`. If passwords or tokens are placed there, audit outputs can leak secrets. Do not attach raw outputs to tickets or chat; filter and redact them before saving.

## 10. Auditing JNI, native libraries, and agents

Java applications can invoke native code via JNI, the Foreign Function & Memory API, native agents, or providers backed by native libraries. Native code can access memory and resources at the process level, so it must be reviewed as a high-privilege component.

Check:

- `.dll`, `.so`, `.dylib` files and their download sources.
- JNI methods and FFM usage.
- `java.library.path` and native library loading paths.
- `-agentlib`, `-agentpath`, and `-javaagent`.
- Native providers such as PKCS#11/HSM.
- Versions, checksums, signatures, and CVEs of native dependencies.
- Filesystem permissions on directories containing native libraries.

JDK 24 issues warnings regarding JNI usage in preparation for restricting native code access in future releases. Review these warnings, identify which modules require native access, and grant permissions only as needed according to the target JDK's guidance.

Do not load native libraries from temporary directories, broadly writable user directories, or unverified sources.

## 11. Auditing secrets, filesystem, and process identity

The JVM runs with the privileges of the OS account that launched it. If a service runs as root/Administrator, an application flaw can have a far greater impact.

### Process identity and OS permissions

- Use dedicated service accounts for each application or group of services sharing a trust boundary.
- Do not run as root/Administrator unless strictly required.
- Grant read access only to necessary configuration files, certificates, and application directories.
- Grant write access only to designated data, log, temp, or upload directories.
- Restrict network egress and inbound ports.
- Limit CPU, memory, process count, file descriptors, and execution time.
- Use a read-only filesystem/container root where appropriate.
- Do not run privileged containers or mount broad host filesystems unnecessarily.

The Java Security Manager does not replace these controls in JDK 24.

### Secrets

Do not store passwords, API tokens, private keys, or database credentials in:

- Git repositories and build files.
- JVM arguments or system properties.
- Logs, exception messages, and tracing attributes.
- Docker image layers or released artifacts.
- Unprotected heap dumps, core dumps, or JFR recordings.
- Scripts readable by other users.

Use a secret manager or a secret-delivery mechanism suited to your infrastructure. Restrict access, rotate periodically, and revoke secrets when personnel, services, or environments change.

Environment variables can be more convenient than hard-coding, but they are not automatically a secure secret store. Processes with the same privileges or administrative accounts can read them depending on the OS and deployment model.

### Temporary files and dumps

Identify where the following are written:

- `java.io.tmpdir`.
- Heap dumps and core dumps.
- JFR recordings.
- Logs and audit files.
- Uploads, caches, and extracted native libraries.

Check file permissions, disk quotas, retention, and cleanup procedures. Diagnostic dumps can contain object graphs, tokens, request payloads, or personal data.

## 12. Auditing deserialization, XML, and untrusted input

Several Java APIs carry high risk when receiving untrusted data. Runtime audits should identify data ingestion points and their corresponding parser configurations.

### Java native serialization

Do not deserialize `ObjectInputStream` from untrusted sources without controls. When its use is unavoidable, apply `ObjectInputFilter` to restrict allowed classes, graph depth, reference counts, byte counts, and array sizes according to business needs.

Do not rely on checking the class after deserialization as a sufficient safeguard; the object graph can trigger behavior during reconstruction.

### XML parsers

Verify that parsers enable secure processing and disable external entities/DOCTYPE when not needed. Assess the risk of XXE, local file reads, and unintended network access. Configuration must apply to the exact parser/provider the application actually uses.

### Input and expressions

- Limit request and upload sizes.
- Validate input against expected schemas and data types.
- Avoid passing user data directly into script engines, expression languages, or command lines.
- Use parameterized queries for databases.
- Do not rely on regex alone to validate complex structured data.
- Check recursion, nesting, and processing time limits to mitigate DoS.

## 13. Logging, monitoring, and incident readiness

An audit is incomplete if incidents cannot be detected and investigated.

Logs should cover:

- Failed and successful logins per policy.
- Changes to permissions, configuration, and administrative accounts.
- Issuance, rotation, and revocation of certificates and keys.
- Changes to JDK/runtime images and dependencies.
- Service restarts, TLS errors, and authentication failures.
- JVM management actions, agents, or debug configuration changes.
- Changes to truststores, providers, and security properties.

Do not log raw passwords, access tokens, private keys, session cookies, or sensitive data. Use correlation IDs to link events without logging full payloads.

Set up alerts for expiring certificates, end-of-support JDKs, dependencies with critical CVEs, unusual spikes in TLS handshake failures, unexpected debug ports, and startup option changes.

Incident runbooks should clearly specify how to isolate the service, collect evidence, revoke/rotate credentials, replace artifacts, restore runtime images, and re-verify after remediation.

## 14. Java 17+ example: generating a security configuration snapshot

The following program reads several security properties, provider names, and TLS defaults of the current JVM. It only creates a configuration snapshot; it does not probe remote endpoints or evaluate your organization's trust policy.

Create `RuntimeSecuritySnapshot.java`:

~~~java
import java.security.Provider;
import java.security.Security;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class RuntimeSecuritySnapshot {
    public static void main(String[] args) throws Exception {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));

        String[] properties = {
            "keystore.type",
            "jdk.tls.disabledAlgorithms",
            "jdk.certpath.disabledAlgorithms",
            "jdk.jar.disabledAlgorithms",
            "jdk.security.legacyAlgorithms"
        };

        for (String name : properties) {
            String value = Security.getProperty(name);
            if (value == null) {
                value = "(not set)";
            } else {
                value = value.replaceAll("\\s+", " ").trim();
            }
            System.out.println(name + "=" + value);
        }

        for (Provider provider : Security.getProviders()) {
            System.out.println("provider=" + provider.getName());
        }

        SSLParameters tls =
                SSLContext.getDefault().getDefaultSSLParameters();

        System.out.println("default TLS protocols=" +
                Arrays.toString(tls.getProtocols()));
        System.out.println("default TLS cipher suites=" +
                Arrays.toString(tls.getCipherSuites()));
    }
}
~~~

Compile:

~~~bash
javac --release 17 RuntimeSecuritySnapshot.java
~~~

Run:

~~~bash
java RuntimeSecuritySnapshot
~~~

Output depends on the active JDK vendor/version, providers, and security properties. For example, the lines will look like:

~~~text
java.version=<runtime version>
java.vendor=<runtime vendor>
keystore.type=<default keystore type>
jdk.tls.disabledAlgorithms=<active TLS restrictions>
jdk.certpath.disabledAlgorithms=<active certificate restrictions>
provider=<provider name>
default TLS protocols=[...]
default TLS cipher suites=[...]
~~~

The `<...>` placeholders above indicate environment-dependent values, not literal output. During an actual audit, store the output in a controlled location, compare it against an approved baseline, and redact sensitive details before sharing.

## 15. Phased audit workflow

A repeatable workflow should include the following steps:

### Phase 1: Define scope

- Select services, environments, JARs, plugins, and runtime images.
- Identify target JDKs and operating systems.
- Identify sensitive data and trust boundaries.
- Assign a technical owner and risk acceptor.

### Phase 2: Collect baseline

- Record `java --version` and vendor/build details.
- Collect security properties, providers, and TLS settings.
- Save redacted startup arguments and JVM flags.
- Record process identity, container image, and OS permissions.
- Build an inventory of dependencies, keystores, truststores, and certificates.

### Phase 3: Technical analysis

- Run SCA on direct and transitive dependencies.
- Run `jdeps --jdk-internals`.
- Run `jdeprscan` for the target release.
- Verify signed artifacts.
- Inspect certificates, trust chains, and TLS endpoints.
- Review agents, debug/JMX, module overrides, and native libraries.
- Review serialization, XML parsers, and input boundaries.

### Phase 4: Risk assessment

For each finding, record:

- Affected component and environment.
- Reproducible evidence.
- Exploitation conditions.
- Impact on confidentiality, integrity, and availability.
- Likelihood of exploitation and exposure level.
- Existing mitigations.
- Priority, owner, and deadline.

You can use a Critical/High/Medium/Low scale per your organization's process. Do not rank solely by warning count; factor in exposure, privileges, exploitability, and affected data.

### Phase 5: Remediation and verification

- Upgrade vulnerable JDKs or dependencies.
- Remove internal API usage and unnecessary opening flags.
- Fix TLS, truststores, and certificate lifecycles.
- Protect secrets, keystores, and diagnostic outputs.
- Reduce OS/container privileges and close administrative ports.
- Re-run the same audit commands and business tests.
- Archive before/after evidence, results, and approvers.

### Phase 6: Maintenance

- Automate audits in CI/CD and run them periodically in production.
- Monitor security advisories from JDK vendors and dependency maintainers.
- Re-scan after every JDK upgrade, provider change, or certificate update.
- Track certificate expiration and secret rotation.
- Review accepted risks on a fixed schedule.
- Store baselines per release to detect unexpected configuration drift.

## 16. Finding register template

| ID | Finding | Evidence | Severity | Owner | Action | Status |
|---|---|---|---|---|---|---|
| SEC-001 | Runtime JDK end-of-support | java --version and vendor lifecycle | High | Platform | Upgrade to supported JDK | Open |
| SEC-002 | Debug listener enabled | JVM args/service config | Critical | Operations | Disable or restrict network access | Open |
| SEC-003 | Dependency with CVE | SBOM and SCA report | High | Application | Upgrade version and regression test | Open |
| SEC-004 | TLS policy allows weak protocols | Endpoint scan and JSSE settings | High | Security | Reconfigure TLS and test clients | Open |
| SEC-005 | Truststore contains certificate with unknown owner | keytool inventory | Medium | Platform | Verify, assign owner, or remove | Investigating |
| SEC-006 | Module opens package unnecessarily | JVM startup options | Medium | Application | Remove redundant --add-opens | Planned |

This is an example of how to record findings, not the audit result of a real system. Severity must be determined based on evidence and organizational criteria.

## 17. Common mistakes in Java runtime audits

### Checking only the Java version

The version alone does not tell you the provider configuration, patches, runtime image, or security properties. Inspect the actual runtime process and active configuration files.

### Assuming the Security Manager isolates the application

Starting in JDK 24, the Security Manager is permanently disabled. Use OS/container isolation and process boundaries to restrict privileges.

### Checking only the JDK's TLS settings

TLS endpoints may terminate at a proxy or use a custom `SSLContext`. Check both the application configuration and external handshakes.

### Checking only the default cacerts

Applications may use custom truststores via system properties, code, or framework configuration. Identify the actual truststore for each service.

### Running only jdeps and concluding dependencies are safe

`jdeps` does not find CVEs and can miss dynamic dependencies. Combine SBOM, SCA, and runtime testing.

### Verifying JARs without checking signer trust

Digests can be valid while the signer certificate is untrusted. Check the chain, usage, validity, timestamp, and trust policy.

### Putting passwords in JVM arguments

Process inspection, diagnostic output, or logs can leak secrets. Use a secret manager and appropriate credential-delivery mechanisms.

### Enabling debug/JMX for production troubleshooting and forgetting to disable it

Diagnostic ports can create powerful administrative access paths. Close them after troubleshooting or strictly restrict them via network/authentication policies.

### Storing heap dumps or thread dumps without controls

Dumps can contain sensitive data. Restrict read permissions, retention, encryption, and sharing procedures.

### Auditing only once

The runtime changes whenever the JDK, dependencies, certificates, providers, container images, or startup flags change. Integrate audits into pipelines and operational schedules.

## 18. Runtime security audit checklist

- Identify the exact JDK vendor, version, patch level, and runtime process.
- Confirm the JDK is still supported and receiving security updates.
- Record active security properties and provider order.
- Check TLS/certificate disabled algorithms and legacy algorithms.
- Review security property overrides and startup configurations.
- Do not rely on the Security Manager in JDK 24 or later.
- Isolate processes using OS/container controls and least privilege.
- Generate an SBOM and run SCA for direct/transitive dependencies.
- Run `jdeps --jdk-internals` and `jdeprscan` for the target release.
- Verify artifacts with `jarsigner -verify -strict`.
- Inspect keystores/truststores, certificate chains, SANs, expiry, and fingerprints.
- Check live TLS endpoints, hostname validation, and mTLS if applicable.
- Review `--add-opens`, `--add-exports`, `--patch-module`, and Java agents.
- Close unnecessary JDWP/JMX/management ports.
- Audit JNI, FFM, native libraries, and native providers.
- Protect passwords, tokens, private keys, and diagnostic dumps.
- Review deserialization, XML external entities, and input limits.
- Check filesystem permissions, network egress, and container capabilities.
- Ensure logs capture audit evidence without containing secrets.
- Assign an owner, severity, remediation, and deadline to each finding.
- Re-run the audit after remediation and archive verification results.

## 19. Key terminology

| Term | Meaning |
|---|---|
| Runtime security audit | Security inspection of the JDK/JVM and deployment environment |
| Security property | Security configuration used by the Java Security Architecture |
| Security provider | Implementation of cryptographic or security services |
| JSSE | Java framework supporting TLS/DTLS |
| Truststore | Store of certificates used to authenticate peers or as trust anchors |
| Keystore | Store of private keys, secret keys, and certificates |
| Certificate chain | Sequence of certificates leading from an entity to a CA/trust anchor |
| JDK internal API | Internal API not part of the public compatibility contract |
| SBOM | Inventory of software components in an artifact |
| SCA | Dependency analysis to identify vulnerabilities and license risks |
| JEP 486 | JDK Enhancement Proposal permanently disabling the Security Manager in JDK 24 |
| JDWP | Java Debug Wire Protocol |
| JNI | Java Native Interface for invoking native code |
| JFR | Java Flight Recorder, a runtime diagnostic event recording tool |
| Least privilege | Granting only the minimum permissions necessary |
| Trust anchor | Root point of trust in certificate validation |
| Revocation | Invalidating a certificate before or during its validity period |

A runtime security audit must combine JDK configuration, dependencies, artifact signatures, certificates, TLS, JVM processes, and OS privileges. Archive evidence per release, remediate findings by risk level, and re-run the same workflow to verify that the live environment is more secure.

## References

- Oracle JDK 24 — [Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-developer-guide.html)
- Oracle JDK 24 — [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The keytool Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- Oracle JDK 24 — [The jarsigner Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- Oracle JDK 24 — [The jdeps Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- Oracle JDK 24 — [The jdeprscan Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- Oracle JDK 24 — [Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
- OpenJDK — [JEP 486: Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- OpenJDK — [JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
