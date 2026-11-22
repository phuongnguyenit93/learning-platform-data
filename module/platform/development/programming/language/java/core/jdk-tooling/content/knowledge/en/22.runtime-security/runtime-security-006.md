# Disabled Algorithms in Java Security

**Disabled algorithms** are a JDK security policy mechanism used to reject an algorithm, protocol, cipher suite, or key that no longer meets security requirements. These restrictions are enforced at specific processing points such as TLS negotiation, certificate chain validation, and JAR signature verification.

In Java, there is no single list applied uniformly to every cryptographic operation. The JDK divides policies by intended use. Therefore, when a TLS connection, certificate, or JAR is rejected due to an algorithm, you need to identify the exact security property governing that operation before making adjustments.

## 1. Why are disabled algorithms needed?

An algorithm that was once acceptable can become weak due to advances in cryptanalysis, increased hardware power, or newly discovered vulnerabilities. For example, MD2, MD5, RC4, and older SSL/TLS protocol versions are no longer suitable for many modern environments.

The JDK uses disabled algorithm lists to prevent applications from accidentally using choices that have been removed from the security policy. Policies can restrict:

- Algorithm names, such as MD5 or RC4.
- Signature algorithms, such as MD5withRSA.
- Key sizes, such as RSA keys smaller than a bit threshold.
- Protocol versions, such as TLSv1 or SSLv3.
- Cipher suites or elliptic curve groups.
- Algorithm usage in a specific context, such as a certificate chain used for a TLS server or a JAR signature.

A disabled algorithm is a policy decision made at the time a security component checks the algorithm. It does not remove the algorithm from every provider and does not necessarily prevent developers from instantiating algorithm objects across all APIs. An operation might still create a signature or key, yet be rejected when a certificate path is validated, when a JAR is verified, or when TLS negotiates a connection.

## 2. Important security properties

The JDK uses different security properties for each domain:

| Security property | Primary scope |
|---|---|
| `jdk.tls.disabledAlgorithms` | SSL/TLS/DTLS: protocol versions, cipher suites, named groups, signature schemes, key exchange, and peer authentication. |
| `jdk.certpath.disabledAlgorithms` | Certificate path building and validation, including algorithms in certificates, CRLs, and OCSP signatures. |
| `jdk.jar.disabledAlgorithms` | Algorithms and key sizes permitted when verifying JAR signatures. |
| `jdk.security.legacyAlgorithms` | Weak or older algorithms that tools like keytool and jarsigner may warn about when used. |
| `jdk.tls.legacyAlgorithms` | TLS algorithms that are still supported but have lower priority than better alternatives. |
| `jdk.disabled.namedCurves` | List of named curves that can be brought into disabled algorithm lists using the include syntax. |

These properties do not substitute for one another. For example, adding RC4 to `jdk.tls.disabledAlgorithms` affects TLS negotiation; adding MD5 to `jdk.jar.disabledAlgorithms` affects JAR signature verification.

`jdk.security.legacyAlgorithms` and `jdk.tls.legacyAlgorithms` are not synonymous with disabled. A legacy algorithm may still be used in certain situations; a disabled algorithm is rejected within the applicable policy scope.

Do not assume every third-party provider reads these properties. The JDK 24.0.2 documentation explicitly notes that some policies are used by the JDK Reference Implementation and are not guaranteed to be applied in the same way by other providers or implementations.

## 3. TLS disabled algorithms

`jdk.tls.disabledAlgorithms` controls choices in SSL, TLS, and DTLS. It is used during negotiation for:

- Protocol versions.
- Cipher suites.
- Named groups and elliptic curves.
- Signature schemes.
- Peer authentication.
- Key exchange mechanisms.

Example configuration from the installed JDK 24.0.2:

~~~properties
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, ECDH, TLS_RSA_*
~~~

Actual values may vary by vendor, JDK update, and organizational policy.

What some of these entries mean:

- `SSLv3`, `TLSv1`, and `TLSv1.1`: prevent negotiating these older protocols.
- `RC4`, `DES`, and `3DES_EDE_CBC`: exclude encryption algorithms that are no longer recommended.
- `MD5withRSA`: restricts signatures using the MD5 and RSA combination.
- `DH keySize < 1024`: rejects Diffie-Hellman keys smaller than 1024 bits.
- `EC keySize < 224`: rejects elliptic curve keys smaller than 224 bits.
- `TLS_RSA_*`: wildcard that excludes cipher suites whose names start with `TLS_RSA_`.

The JDK checks these restrictions even if the application explicitly enables a protocol or cipher suite in configuration. Therefore, calling `SSLParameters.setProtocols` or `setCipherSuites` cannot turn a disabled algorithm back into a valid option.

For peer authentication and PKI-based key exchange, TLS restrictions are also checked during certificate path building/validation and against algorithms in certificates, CRLs, or OCSP signatures. They are applied in addition to `jdk.certpath.disabledAlgorithms`.

## 4. Certificate path disabled algorithms

`jdk.certpath.disabledAlgorithms` applies when the JDK builds and validates a certificate chain. It can restrict:

- Signature algorithms in certificates.
- Public key sizes.
- Algorithms used to sign CRLs.
- Signatures of OCSP responses.
- Algorithms restricted within a specific usage context.

Example JDK 24.0.2 configuration:

~~~properties
jdk.certpath.disabledAlgorithms=MD2, MD5, SHA1 jdkCA & usage TLSServer, RSA keySize < 1024, DSA keySize < 1024, EC keySize < 224, SHA1 usage SignedJAR & denyAfter 2019-01-01
~~~

A certificate chain can be rejected even if the certificates are still within their validity period. The cause may be a signature using a prohibited algorithm, a key that is too short, or a certificate being used in a restricted context.

Based on the inspected configuration and implementation, these restrictions do not apply to trust anchors or self-signed certificates. Distinguish end-entity certificates from trust anchors: a certificate used as a trust anchor does not necessarily undergo the same checks as an intermediate certificate in the path.

CertPath policies also depend on the provider implementing PKIX. Do not generalize the behavior of the JDK Reference Implementation to every custom provider.

## 5. Disabled algorithms for JAR signatures

`jdk.jar.disabledAlgorithms` controls the algorithms and key sizes used to verify signed JARs.

Example on JDK 24.0.2:

~~~properties
jdk.jar.disabledAlgorithms=MD2, MD5, RSA keySize < 1024, DSA keySize < 1024, SHA1 denyAfter 2019-01-01
~~~

A JAR signed with a prohibited algorithm or key size may be treated as an unsigned JAR. This directly affects applications that rely on code signing to verify the origin and integrity of libraries.

The `denyAfter` option allows date-based restrictions. For JAR policies, a JAR signed and timestamped before the cutoff date may be exempt from that restriction. The timestamp must be verified and processed according to JDK rules; you cannot rely solely on the file modification date or the user's local system clock.

When a JAR is treated as unsigned, the application may no longer receive guarantees or permissions based on the signer. Check the manifest, certificate chain, timestamp, and signature policy before concluding that the JAR file is corrupted.

## 6. Legacy algorithms vs. disabled algorithms

The JDK has two concepts that should be distinguished:

**Disabled:** the algorithm is not permitted within the policy scope. Enabling it in application configuration does not bypass that restriction.

**Legacy:** the algorithm is still supported but is not preferred. In TLS, legacy algorithms are typically negotiated only when no better suitable option is available. If an algorithm is also listed in `jdk.tls.disabledAlgorithms` or blocked by `AlgorithmConstraints`, it is completely disabled.

Example:

~~~properties
jdk.tls.legacyAlgorithms=NULL, anon, RC4, DES, 3DES_EDE_CBC
~~~

These entries are legacy options in JSSE. They do not have the same meaning as the disabled list; however, an algorithm like RC4 also appears in the TLS disabled list in the JDK 24.0.2 configuration, so it is excluded.

Another property:

~~~properties
jdk.security.legacyAlgorithms=SHA1, RSA keySize < 2048, DSA keySize < 2048, DES, DESede, MD5, RC2, ARCFOUR
~~~

Tools such as `keytool` and `jarsigner` may emit warnings when using legacy algorithms. This warning does not automatically mean that every API using that algorithm will fail. Read the relevant property and tool output carefully.

## 7. Disabled algorithms list syntax

Disabled algorithm properties generally take a comma-separated list of entries. Each entry consists of an algorithm name and optionally one or more constraints.

General structure:

~~~text
DisabledAlgorithms:
    AlgorithmName [Constraint] { '&' Constraint }
    or IncludeProperty
~~~

Common constraint forms:

| Constraint | Meaning |
|---|---|
| `keySize < 2048` | Restricts keys shorter than 2048 bits. |
| `jdkCA` | Applies when the certificate chain terminates at a JDK-marked trust anchor. |
| `denyAfter 2028-01-01` | Rejects after the specified date, according to the property's rules. |
| `usage TLSServer` | Applies only in the TLS server context. |
| `usage TLSClient` | Applies only in the TLS client context. |
| `usage SignedJAR` | Applies only in the signed JAR context. |
| `include jdk.disabled.namedCurves` | Includes the named curve list from the specified property into the policy. |

### keySize

`keySize` compares key lengths in bits and supports these operators:

~~~text
<  <=  ==  !=  >=  >
~~~

Examples:

~~~properties
RSA keySize < 2048
EC keySize <= 224
DSA keySize < 2048
~~~

These expressions restrict RSA, EC, or DSA keys whose sizes satisfy the condition. Use thresholds appropriate for cryptographic standards and system compatibility.

Expression order can affect the result. When specifying multiple thresholds for the same algorithm, constraints with smaller key sizes must be placed before larger thresholds. For example:

~~~properties
RSA keySize < 1024 & jdkCA, RSA keySize < 2048
~~~

### jdkCA

`jdkCA` limits a rule to certificate chains that terminate at a trust anchor marked by the JDK in the default CA store. Omitting this constraint can restrict the algorithm across all chains within the property's scope.

Example:

~~~properties
SHA1 jdkCA & usage TLSServer
~~~

This expression requires both the trust anchor condition and the TLS server context.

### usage

`usage` limits a rule by intended use:

~~~properties
SHA1 usage TLSServer TLSClient
SHA1 usage SignedJAR
~~~

Multiple usages after the keyword can be separated by spaces. This is how to apply context-specific policies when banning an algorithm across all cases would cause unnecessary impact.

### denyAfter

`denyAfter` uses a date in `YYYY-MM-DD` format:

~~~properties
SHA1 denyAfter 2028-01-01
~~~

The date is evaluated in UTC. This rule allows a policy to change over time without waiting for certificates to expire. For timestamped JARs, follow the exceptions and timestamp rules defined by the JDK for signed JARs.

### Combining constraints with &

The `&` operator requires all constraints in the same expression to be satisfied together before the entry applies.

Examples:

~~~properties
RSA keySize < 2048 & jdkCA
SHA1 jdkCA & usage TLSServer
~~~

Read the expression as a combined condition. Comma-separated entries are separate policy entries.

## 8. Algorithm names and matching

Algorithm names are matched case-insensitively and against subcomponents of the algorithm name.

For example, the entry `SHA1` can match the signature name `SHA1withRSA` because SHA1 is a component of that name. The entry `DSA` can restrict DSA-based signature algorithms, but it is not synonymous with ECDSA.

Do not infer algorithm names solely from Java class names or provider names. Use standard names from the Java Security Standard Algorithm Names Specification and check how the specific component interprets those names.

For TLS cipher suites, `jdk.tls.disabledAlgorithms` also supports the `*` wildcard in cipher suite names starting with `TLS_`. Example:

~~~properties
TLS_RSA_*
~~~

This rule restricts all cipher suites matching that prefix. Wildcards are not a general syntax for all algorithm names in other properties.

## 9. Named curves and include properties

`jdk.disabled.namedCurves` is a property containing a list of disabled named elliptic curves. Properties such as TLS, CertPath, or JAR can pull that list in using the include syntax:

~~~properties
jdk.tls.disabledAlgorithms=..., include jdk.disabled.namedCurves
~~~

The `include` keyword references another security property. It allows sharing a single restriction list across multiple domains, avoiding duplicating each curve name in multiple places.

In JDK 24.0.2 used to verify this article, the line defining `jdk.disabled.namedCurves` in the default configuration file is commented out, so `Security.getProperty("jdk.disabled.namedCurves")` returns `null`. Another JDK distribution or custom deployment policy may define this value.

Do not add an include to an undefined property and assume the curve list is active. Verify the effective value in the actual running JVM.

## 10. The java.security configuration file

Default security properties are typically located at:

~~~text
JAVA_HOME/conf/security/java.security
~~~

This file differs from `application.properties` or regular system properties. Entries in it are loaded by the Java Security infrastructure.

Examples of some properties in JDK 24.0.2:

~~~properties
jdk.certpath.disabledAlgorithms=...
jdk.tls.disabledAlgorithms=...
jdk.jar.disabledAlgorithms=...
jdk.security.legacyAlgorithms=...
jdk.tls.legacyAlgorithms=...
~~~

Do not edit the JDK's default file arbitrarily. Changes there can affect every application using the same JDK, get overwritten during JDK updates, or create hard-to-reproduce differences between developer machines and production.

For application-specific deployments, you can use a supplemental security properties file via the JVM option `-Djava.security.properties`. Store supplemental files in managed, version-controlled configuration rather than modifying the locally installed JDK.

## 11. Loading supplemental security properties

You can launch the JVM with a supplemental security properties file:

~~~bash
java -Djava.security.properties=file:/opt/app/security/extra.security -jar app.jar
~~~

With a single equals sign in `-Djava.security.properties=`, the supplemental file is loaded alongside the master file. Properties not declared in the supplemental file still come from the master file.

**Very important point:** if the supplemental file redeclares an existing property, the new value replaces the entire previous value of that property. Comma-separated algorithm lists are not automatically appended.

Example supplemental file:

~~~properties
jdk.certpath.disabledAlgorithms=MD2
~~~

After loading, the effective value of this property is only `MD2`. Default entries such as MD5, usage-scoped SHA1, RSA key size, and EC key size have been replaced from that property. This can unintentionally weaken the security policy.

When adding a constraint, retain all default entries the organization wants to keep enforcing, then append the new constraint to the same value. Verify the effective value before deployment.

The option with two equals signs:

~~~bash
java -Djava.security.properties==file:/opt/app/security/complete.security -jar app.jar
~~~

has a different meaning: the specified file completely replaces the master security properties file. Do not use this approach unless you have provided every required property and understand the impact on the entire Java Security configuration.

## 12. Example: adding a restriction while keeping defaults

Suppose an organization's policy wants to reject RSA keys smaller than 2048 bits in TLS. The supplemental file must keep the active default TLS entries and then add the constraint:

~~~properties
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, ECDH, TLS_RSA_*, RSA keySize < 2048
~~~

Load the file at startup:

~~~bash
java -Djava.security.properties=file:/opt/app/security/extra.security -jar app.jar
~~~

This example illustrates how to preserve existing entries and add a constraint. A 2048-bit RSA threshold can affect certificates, legacy servers, and dependencies; test in a staging environment before applying to production.

Do not copy default values verbatim from another JDK without comparing. Vendors or updates may change the list, so take the master values from the target JDK itself.

## 13. Reading effective properties in Java

Use `java.security.Security.getProperty` to read security properties:

~~~java
import java.security.Security;
import java.util.List;

public class DisabledAlgorithmsDemo {
    public static void main(String[] args) {
        List<String> names = List.of(
                "jdk.certpath.disabledAlgorithms",
                "jdk.tls.disabledAlgorithms",
                "jdk.jar.disabledAlgorithms",
                "jdk.security.legacyAlgorithms",
                "jdk.tls.legacyAlgorithms",
                "jdk.disabled.namedCurves"
        );

        for (String name : names) {
            String value = Security.getProperty(name);
            System.out.println(
                    name + "=" + (value == null ? "<not set>" : value)
            );
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac DisabledAlgorithmsDemo.java
java DisabledAlgorithmsDemo
~~~

With Azul OpenJDK 24.0.2 used for testing, the output is:

~~~text
jdk.certpath.disabledAlgorithms=MD2, MD5, SHA1 jdkCA & usage TLSServer, RSA keySize < 1024, DSA keySize < 1024, EC keySize < 224, SHA1 usage SignedJAR & denyAfter 2019-01-01
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, ECDH, TLS_RSA_*
jdk.jar.disabledAlgorithms=MD2, MD5, RSA keySize < 1024, DSA keySize < 1024, SHA1 denyAfter 2019-01-01
jdk.security.legacyAlgorithms=SHA1, RSA keySize < 2048, DSA keySize < 2048, DES, DESede, MD5, RC2, ARCFOUR
jdk.tls.legacyAlgorithms=NULL, anon, RC4, DES, 3DES_EDE_CBC
jdk.disabled.namedCurves=<not set>
~~~

The output above is a sample from one specific JDK build, not a fixed value for all machines. Use `Security.getProperty` to inspect the actual JVM running the application.

Do not use `System.getProperty("jdk.tls.disabledAlgorithms")` to read security properties. `System.getProperty` reads system properties; `Security.getProperty` reads Java security properties.

## 14. Application-level AlgorithmConstraints

In addition to JVM-wide policies, Java provides the `java.security.AlgorithmConstraints` interface so an application or provider can check algorithms as needed.

For TLS, `javax.net.ssl.SSLParameters` has the `setAlgorithmConstraints` method:

~~~java
SSLParameters parameters = new SSLParameters();
parameters.setAlgorithmConstraints(applicationConstraints);
~~~

`applicationConstraints` is an implementation provided by the application. It can restrict algorithms allowed on a specific connection or TLS configuration.

This is an additional application-level control layer. It is not a way to bypass `jdk.tls.disabledAlgorithms`. An algorithm marked disabled by the JDK still will not be negotiated just because the application provides an AlgorithmConstraints that permits it.

When writing a custom `AlgorithmConstraints`, evaluate the algorithm name, key, parameters, and `CryptoPrimitive` thoroughly. An overly permissive implementation or one that always returns true can defeat the purpose of the additional policy.

## 15. Application impact and common errors

When disabled algorithms are enforced, messages can appear at various stages:

| Symptom | Area to check |
|---|---|
| TLS handshake fails or no suitable protocol/cipher is found | `jdk.tls.disabledAlgorithms`, TLS configuration, and peer capabilities. |
| Certificate path validation fails | `jdk.certpath.disabledAlgorithms`, `jdk.tls.disabledAlgorithms`, certificate chain, CRL, and OCSP. |
| Signed JAR is treated as unsigned | `jdk.jar.disabledAlgorithms`, signing algorithm, certificate, and timestamp. |
| keytool or jarsigner emits weak algorithm warnings | `jdk.security.legacyAlgorithms` and tool configuration. |
| Algorithm is listed in the provider but cannot be used in a context | Check the security property applicable to that context and the implementing provider. |

Some messages may contain phrases such as `Algorithm constraints check failed`, `No appropriate protocol`, or PKIX errors. Exact wording varies by provider, JDK, and failure stage.

### TLS handshake has no common options left

If the client and server only support protocols/ciphers that have been disabled, there is no common option left to negotiate. Check both ends of the connection, not just the client configuration.

### Certificate is still valid by date but rejected

A valid certificate validity period does not guarantee the signing algorithm and key size are still accepted. Check every certificate in the chain, the CA, intended usage, and CRL/OCSP signatures.

### JAR reports missing signature

If the signing algorithm is prohibited, the JDK may treat the JAR as unsigned. Verify the signer, certificate chain, timestamp, and JAR policy before changing properties.

### Legacy warnings mistaken for errors

Legacy warnings from keytool or jarsigner do not mean disabled. Identify the source property and test the actual operation before deciding to make changes.

## 16. Safe diagnostic and change workflow

When an application encounters an algorithm-related error:

1. Record the JDK vendor, version, and cryptographic providers in use.
2. Identify the failing operation: TLS handshake, CertPath, JAR verification, or tool command.
3. Read the full error message and identify the algorithm name, key size, protocol, or cipher suite.
4. Use `Security.getProperty` to inspect the effective property in the exact JVM.
5. Check `JAVA_HOME/conf/security/java.security` and any supplemental file if the JVM was launched with `-Djava.security.properties`.
6. Check contextual constraints such as `jdkCA`, `usage`, and `denyAfter`.
7. Prioritize upgrading certificates, keys, servers, libraries, or algorithms to secure alternatives.
8. If a policy change is necessary, preserve default restrictions and add only evaluated constraints.
9. Test TLS, certificate validation, and JAR verification on staging.
10. Deploy with monitoring, document the configuration, and prepare a rollback plan.

Do not remove an algorithm from the list just to make an error disappear. First find the root cause and determine whether the certificate, server configuration, or dependency can be replaced.

## 17. Testing and deployment in CI

Disabled algorithm policies should be tested on the exact JDK used in production.

A pipeline can:

- Print the JDK vendor and version.
- Print key security properties using a small check program.
- Run TLS client/server tests with realistic certificates.
- Verify signed JARs and timestamps.
- Run CertPath tests with chains representative of the environment.
- Store supplemental security properties files alongside deployment configuration.
- Compare effective properties against an approved baseline.

Do not check only the configuration file. A supplemental file might fail to load due to an incorrect path, or a property value might have been replaced entirely instead of appended. Verify from inside the application's actual JVM.

When upgrading the JDK, compare default lists between versions. A JDK update can add prohibited algorithms or change thresholds; that is a security change that can affect compatibility.

## 18. Disabled algorithms management checklist

- Identified the right security property for TLS, CertPath, JAR, or tools.
- Distinguished disabled from legacy.
- Checked JDK vendor, version, and providers.
- Understood `keySize`, `jdkCA`, `usage`, `denyAfter`, and `include` constraints.
- Read effective values using `Security.getProperty`.
- Supplemental file does not accidentally overwrite default restrictions that must remain active.
- Did not use double equals `==` unless intentionally replacing all master security properties.
- Tested TLS, certificate chains, and signed JARs on staging.
- Prioritized replacing weak certificates/keys/algorithms over removing restrictions.
- Have version-controlled configuration, monitoring, and a rollback plan.

Disabled algorithms help the JDK enforce consistent cryptographic policies across critical security operations. To adjust them properly, know which property governs the failing operation, understand how constraints are interpreted, and verify the actual values in the JVM. Keeping default restrictions intact, testing changes in a production-equivalent environment, and prioritizing upgrades of weak components is the safer way to manage policy.
