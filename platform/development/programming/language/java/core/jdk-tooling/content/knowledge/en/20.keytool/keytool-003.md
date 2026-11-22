# Truststore in Java

A **truststore** is a certificate store that a Java application uses to determine which Certificate Authorities (CAs) or peer certificates are trusted. In a TLS/HTTPS connection, the client receives a certificate chain from the server and needs to verify that the chain leads to a trust anchor present in the truststore. Java performs this check through JSSE's TrustManager.

A truststore typically contains trusted certificate entries, such as root CA certificates or internal CA certificates. It usually does not contain the application's private key. The private key and certificate chain used to prove the application's own identity are typically stored in a keystore and used by a KeyManager.

A truststore and a keystore can use the same file format, such as PKCS12 or JKS, but they serve different roles. Technically, a keystore file can contain multiple types of entries; the term truststore describes how an application uses a KeyStore to store the certificates it trusts.

## 1. How does a truststore work in TLS?

When a Java client connects to an HTTPS server, the TLS handshake typically proceeds in the following general sequence:

1. The client opens a connection to the server.
2. The server sends its certificate and any required intermediate certificates.
3. The client builds and validates the certificate path from the server certificate to a trust anchor.
4. The TrustManager verifies signatures, validity periods, algorithm policies, and certificate chain constraints.
5. TLS proceeds if validation succeeds and other checks, including hostname verification, also pass.

Example of a certificate chain:

~~~text
api.example.com
      |
      | signed by
      v
Example Issuing CA
      |
      | signed by
      v
Example Root CA
      |
      | present in truststore
      v
Trusted certificate entry
~~~

The truststore helps Java identify the root CA or certificate configured as a trust anchor. It does not mean that simply placing a certificate file into the truststore makes every connection to that server valid. The certificate must still satisfy all other validation requirements.

### A truststore does not replace hostname verification

A certificate chain may be signed by a trusted CA, yet the connection must still fail if the certificate is not valid for the hostname being accessed.

For example, the application connects to api.example.com, but the Subject Alternative Name (SAN) in the certificate only contains internal.example.com. The TrustManager can build a trust path, but hostname verification still detects the name mismatch.

Independent checks include:

- **Trust path**: does the certificate chain lead to a trusted trust anchor?
- **Validity**: has the certificate expired or is it not yet valid?
- **Hostname**: does the SAN match the server's hostname?
- **Usage and constraints**: is the certificate suitable for TLS usage and algorithm policies?

Do not disable hostname verification to work around truststore errors. Fix the certificate, hostname, or CA configuration properly.

## 2. Distinguishing between truststore and keystore

Both stores can share the same KeyStore API and file formats, but they are used for different purposes.

| Criterion | Truststore | Keystore |
|---|---|---|
| Purpose | Store trusted certificates | Store the application's identity and keys |
| Common contents | Root CA, intermediate CA, or trusted peer certificates | Private key, subject certificate, and certificate chain |
| Common entry | trustedCertEntry | PrivateKeyEntry |
| Component used in JSSE | TrustManager | KeyManager |
| Question answered | Which peer certificates do I trust? | Which key do I use to prove my identity? |
| Example | Client trusts the CA that signed the server's certificate | Server presents its certificate and private key |

### Standard HTTPS client

A client accessing a public HTTPS server typically needs a truststore to verify the server's certificate. It does not necessarily need a keystore because the client does not have to present a certificate for client-certificate authentication.

### Mutual TLS

In mutual TLS (mTLS), both sides authenticate certificates:

- The client uses a truststore to verify the server's certificate.
- The client uses a keystore to hold the client's own private key and certificate chain.
- The server uses a truststore to verify the certificate sent by the client.
- The server uses a keystore to present the server's certificate and private key.

The truststore and keystore can reside in two separate files for independent permissions and lifecycle management.

## 3. Truststore formats: PKCS12 and JKS

A truststore is a KeyStore object persisted in a specific format. The JDK supports multiple keystore types through security providers.

| Format | Characteristics | When to use |
|---|---|---|
| PKCS12 | Standard format, cross-platform compatible | Recommended default choice for new projects |
| JKS | Java-proprietary keystore format | Compatibility with legacy systems |
| JCEKS | Legacy Java format supporting secret-key entries | Use only when systems have specific compatibility requirements |

Since JDK 9, the default keystore type is **PKCS12**. If no store type option is passed, keytool and the KeyStore API use the value of the keystore.type security property. In modern standard JDK configurations, this value is pkcs12.

You should explicitly specify the store type in deployment scripts to avoid depending on the build or runtime machine configuration:

~~~bash
keytool -list -keystore app-truststore.p12 -storetype PKCS12
~~~

Some modern JDK versions emit warnings about JKS and JCEKS because these formats are considered legacy. For new systems, prefer PKCS12; for legacy systems, verify compatibility before migrating.

### Extending and converting JKS to PKCS12

If you have an existing legacy JKS truststore:

~~~bash
keytool -importkeystore \
  -srckeystore legacy-truststore.jks \
  -srcstoretype JKS \
  -destkeystore app-truststore.p12 \
  -deststoretype PKCS12
~~~

keytool will prompt for the source password and destination password if not provided. After conversion, verify the entry count, aliases, fingerprints, and certificate chains:

~~~bash
keytool -list -v -keystore app-truststore.p12 -storetype PKCS12
~~~

Do not delete the old file immediately after conversion. Test the application and deployment pipeline with the new file before replacing the one in use.

## 4. The JDK's default truststore: cacerts

The JDK ships with a default CA store named **cacerts**. This store contains a curated set of root CAs for the Java ecosystem. It is typically located in the security directory of Java home:

~~~text
JAVA_HOME/
  lib/
    security/
      cacerts
~~~

You can view the certificates in the default store:

~~~bash
keytool -list -cacerts
~~~

View details:

~~~bash
keytool -list -v -cacerts
~~~

You can look up a specific alias:

~~~bash
keytool -list -cacerts -alias example-root-ca
~~~

### cacerts is not a list of every CA in the world

cacerts only contains the set of root certificates packaged and managed according to the JDK distribution's policy. An internal CA, enterprise CA, or newly established CA may not be present in this store.

Do not assume every certificate is trusted just because Java is installed. If a server uses a private PKI, the application may need a dedicated truststore containing the corresponding CA.

### jssecacerts and truststore lookup order

For the JSSE reference implementation, when the javax.net.ssl.trustStore system property is not configured, the default SSLContext searches for a truststore in the following order:

1. The jssecacerts file in the Java home security directory.
2. The cacerts file in the same directory if jssecacerts does not exist.
3. If neither is found, the TrustManager uses an empty truststore.

If the javax.net.ssl.trustStore property is specified, that file is used as the truststore. If the property is set but the path points to a nonexistent file, the JSSE reference implementation does not fall back to cacerts; this results in no specified truststore being used.

This is why you must verify the exact path when deploying a custom truststore.

## 5. Creating a custom truststore with keytool

A common approach is to create a dedicated truststore for the application and import the CA certificates that the application needs to trust.

Suppose an internal CA provides the file:

~~~text
certificates/
  company-root-ca.pem
~~~

### Step 1: Inspect the certificate before importing

~~~bash
keytool -printcert -file certificates/company-root-ca.pem
~~~

This command displays details such as subject, issuer, validity period, and SHA-256 fingerprint.

Do not trust a certificate simply because the file was emailed or downloaded from a server. Compare the SHA-256 fingerprint against the value provided by the CA or administrator through an independent, trusted channel.

### Step 2: Import the certificate

~~~bash
keytool -importcert \
  -alias company-root-ca \
  -file certificates/company-root-ca.pem \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

keytool will prompt for a password if it needs to create or open the truststore, then display the certificate details and ask whether you trust the certificate.

Confirm the import only after verifying the fingerprint and the CA's identity.

If the alias already exists in the truststore as a trusted certificate entry, keytool reports an error instead of automatically overwriting that entry. Check the alias before deciding to replace it.

### Step 3: Verify the entry was added

~~~bash
keytool -list -v \
  -keystore app-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

Check that:

- The alias matches the chosen name.
- The entry type is trustedCertEntry.
- The subject and issuer match the expected CA.
- The validity dates are valid.
- The SHA-256 fingerprint matches the verified value.

Example abbreviated output for illustration:

~~~text
Alias name: company-root-ca
Entry type: trustedCertEntry

Owner: CN=Company Root CA, O=Example Corp
Issuer: CN=Company Root CA, O=Example Corp
Valid from: ...
Certificate fingerprints:
         SHA256: ...
~~~

Actual dates and fingerprint values depend on the imported certificate.

## 6. Importing certificate chains and choosing the right CA

A server usually sends its leaf certificate along with intermediate certificates. The root CA might not be sent by the server during the handshake because the client is expected to already have that trust anchor.

Example:

~~~text
api.internal.example
       |
       v
Example TLS Issuing CA
       |
       v
Example Root CA
~~~

If the application needs to trust an internal CA hierarchy, you should normally import the organization-approved root CA. In some PKI models, an organization may designate an intermediate CA as the trust anchor; this decision must follow PKI policy.

Do not import every certificate sent by the server into the truststore without understanding the role of each certificate. A leaf certificate can be imported as a trusted certificate entry, but doing so ties trust directly to that specific certificate and makes renewal or certificate replacement more difficult.

### Inspecting the certificate chain from a server

keytool can display the certificates presented by a server:

~~~bash
keytool -printcert -sslserver api.internal.example:443
~~~

This command is useful for observing the certificate chain sent by the server. It does not by itself prove that the certificate is trustworthy. You must still verify the fingerprint and CA identity through an independent source.

### Importing certificates from PEM or DER files

keytool supports X.509 certificates in binary DER or printable Base64/PEM format. A PEM file typically has the structure:

~~~text
-----BEGIN CERTIFICATE-----
Base64 encoded certificate data
-----END CERTIFICATE-----
~~~

keytool also supports certificate chains in PKCS#7 format or sequences of X.509 certificates in the documented format.

If a file contains multiple certificates, determine the order and role of each certificate before importing. Do not use a bundle file of unknown origin as a trust anchor.

## 7. Using a truststore with a Java application via JSSE

The JSSE reference implementation supports system properties to configure the default truststore.

| System property | Purpose |
|---|---|
| javax.net.ssl.trustStore | Path to the truststore |
| javax.net.ssl.trustStoreType | Truststore format, e.g., PKCS12 |
| javax.net.ssl.trustStorePassword | Password to open the truststore |
| javax.net.ssl.keyStore | Path to the keystore containing the local identity |
| javax.net.ssl.keyStoreType | Keystore format |
| javax.net.ssl.keyStorePassword | Keystore password |

Example of launching an application with a custom truststore:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/etc/acme/app-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

If the truststore is protected with a non-empty password, the application needs to supply the javax.net.ssl.trustStorePassword property through the deployment environment's secure configuration.

Do not hardcode real passwords in source code, committed configuration files, build commands, or logs. Prefer a secret manager or the deployment platform's secret protection mechanism. When using keytool in scripts, JDK 26 supports reading passwords from environment variables or files via the corresponding password modifier forms.

### When does JSSE read these properties?

These system properties are read when the default SSLContext and its corresponding TrustManager are initialized. Set the configuration before the application creates a TLS client or initializes the default SSLContext.

If a library has already created and cached the SSLContext before the properties are set, changing the properties afterward may not affect the active context.

### Custom SSLContext

If the application creates its own SSLContext or TrustManagerFactory, it can pass a custom KeyStore directly through the API instead of relying on default system properties.

Example configuration flow:

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(trustStorePath)) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagerFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());

trustManagerFactory.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        null,
        trustManagerFactory.getTrustManagers(),
        null);
~~~

This is the core configuration snippet; the variables trustStorePath and trustStorePassword must be provided from application configuration or a secret manager. When using a custom SSLContext, verify that the HTTP client or TLS client actually uses this socket factory/context.

## 8. Does a custom truststore replace cacerts?

When javax.net.ssl.trustStore is configured to point to a custom file, JSSE uses that file for the default TrustManager. It does not automatically merge entries from the custom truststore with cacerts.

Example:

~~~text
JDK cacerts:
  Public Root CA A
  Public Root CA B
  Public Root CA C

app-truststore.p12:
  Company Root CA
~~~

If the application only uses app-truststore.p12, the public root CAs from cacerts are not automatically included in the custom truststore. The application may trust the internal CA while failing to access public websites.

There are three deployment approaches:

1. **Use only custom CAs**: suitable for applications that only connect to internal systems with a private PKI.
2. **Create a combined truststore**: include the required public CAs and internal CAs in a single application-managed truststore.
3. **Use a custom TrustManager strategy**: the application explicitly controls how multiple trust sources are combined according to security requirements.

If both public CAs and internal CAs are needed, create a combined truststore by importing verified certificates from trusted sources. Record the source, fingerprint, and update procedure for each CA.

Do not blindly copy the entire cacerts file into the application. The set of required CAs depends on the system, security policy, and certificate lifecycle.

## 9. Managing the default cacerts truststore

You can import a certificate into the JDK's default store using the -cacerts option:

~~~bash
keytool -importcert \
  -cacerts \
  -alias company-root-ca \
  -file company-root-ca.pem
~~~

keytool may require a password and appropriate write permissions. On some systems, the JDK installation directory does not allow regular users to write directly.

Inspect the entry:

~~~bash
keytool -list -v -cacerts -alias company-root-ca
~~~

Delete the entry when the CA is no longer trusted or has been revoked according to organizational policy:

~~~bash
keytool -delete -cacerts -alias company-root-ca
~~~

### Why should you be cautious when modifying cacerts?

cacerts is a shared CA store for the Java home. Changes can affect multiple applications running on the same JDK, not just a single application.

Key considerations:

- Only add CAs that have been verified and authorized to be trusted.
- Record the alias, subject, issuer, and fingerprint.
- Restrict write permissions on the cacerts file.
- Back up the file according to system administration procedures before making changes.
- Monitor for CA expiration, revocation, or JDK distrust policies.
- Test applications after updating or deleting certificates.

The initial password for cacerts in some JDK distributions is documented as changeit, but administrators may change the password and access permissions. Do not rely on the default password as a guarantee across all environments.

## 10. Inspecting and diagnosing a truststore

### List all entries

~~~bash
keytool -list \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

### View details of a specific certificate

~~~bash
keytool -list -v \
  -keystore app-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

### Inspect a certificate file before importing

~~~bash
keytool -printcert -file company-root-ca.pem
~~~

### Inspect the certificate presented by a server

~~~bash
keytool -printcert -sslserver api.example.com:443
~~~

### Check the keytool version

~~~bash
keytool -version
~~~

### Enable JSSE debug logging when investigating TLS

You can enable JSSE diagnostics:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
~~~

The output can be very verbose and contain details about the handshake, certificate chains, and trust decisions. Enable it only during controlled investigations, and do not leave sensitive debug logging enabled long-term in production.

## 11. Common truststore errors

| Error or symptom | Possible cause | Resolution |
|---|---|---|
| PKIX path building failed | Unable to find a path from the server certificate to a trust anchor | Check the chain, the expected CA, and the truststore used by the application |
| unable to find valid certification path | Missing root/intermediate CA or incomplete chain sent by the server | Verify the CA and import the appropriate trust anchor |
| Trust anchor for certification path not found | The certificate chain does not terminate at a trusted CA | Check the certificate, alias, and truststore |
| Keystore was tampered with, or password was incorrect | Wrong password, wrong store type, or corrupted file | Verify the password, PKCS12/JKS type, and file integrity |
| Unrecognized keystore format | Incorrect store type specified or file is not a valid keystore | Use the correct --storetype and verify the file |
| Truststore file not found | Incorrect system property path or file not deployed | Check the absolute path and read permissions |
| Certificate import reports alias already exists | The alias already points to a trusted certificate entry | Inspect the existing entry before changing or replacing the alias |
| Certificate expired | The certificate or CA has expired | Request a new certificate and update the chain |
| No subject alternative DNS name matching | Hostname does not match the certificate's SAN | Fix the hostname or issue a certificate with the correct SAN |
| Certificate signature algorithm disabled | The algorithm is disabled by JDK security policy | Use a certificate and algorithm that are still supported |
| Public HTTPS stops connecting after configuring a custom truststore | The custom truststore does not contain the required public root CAs | Create a combined truststore if the application needs both public and private CAs |
| Import succeeded but TLS still fails | The application uses a different SSLContext or TrustManager | Check the actual TLS configuration of the HTTP client |

## 12. Certificate chains and trust principles

Not every certificate should be imported into a truststore. Before importing, determine what role the certificate plays.

| Certificate | Role | Common handling |
|---|---|---|
| Root CA | Trust anchor at the top of the chain | Import if the organization confirms this CA should be trusted |
| Intermediate CA | CA that signs certificates for servers or subordinate CAs | Usually sent by the server in the chain; only use as a trust anchor when policy requires |
| Server/leaf certificate | Proves the identity of a specific hostname | Do not trust automatically just because it was retrieved from a server |
| Self-signed certificate | Self-signed certificate, often used in labs or private services | Trust only after verifying the fingerprint and under a clear policy |

### Why must you verify the fingerprint?

Anyone can generate a self-signed certificate with a Subject DN identical to a well-known CA. The name in a certificate does not by itself prove that the public key belongs to that CA.

Before importing a certificate:

1. Obtain the certificate from a source confirmed by your organization or the CA.
2. Use keytool -printcert to view the fingerprint.
3. Compare the SHA-256 fingerprint against the fingerprint published through an independent channel.
4. Check the subject, issuer, and validity.
5. Determine whether the certificate is the trust anchor the application needs.
6. Only then import it into the truststore.

Do not use -noprompt to automatically accept unverified certificates. Automated import workflows must include a fingerprint verification step or control over trusted certificate sources.

## 13. Updating, rotating, and deleting certificates

Certificates have lifecycles. Root CAs can be replaced, intermediate CAs can be renewed, server certificates can be reissued, and trust policies can change.

An update process should include:

1. Identify the old CA and the new CA.
2. Obtain the new certificate from an official source.
3. Verify the fingerprint, subject, and issuer.
4. Import the new certificate with a clear alias.
5. Inspect the truststore after importing.
6. Deploy the application and test TLS.
7. Confirm that connections are using the new chain.
8. Delete the old certificate when it is no longer needed per policy.

If you need to rename an alias:

~~~bash
keytool -changealias \
  -alias old-company-ca \
  -destalias company-root-ca \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

If you need to delete a certificate:

~~~bash
keytool -delete \
  -alias old-company-ca \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Do not delete the old CA before confirming that all related systems have migrated to the new chain. Changing trust anchors can disrupt connections that still depend on the old certificate.

## 14. Protecting the truststore in deployment environments

Public certificates do not need to be kept secret like private keys, but a truststore still requires integrity protection. An attacker with write access to the file could add an untrusted certificate to the truststore, causing the application to accept a rogue CA.

Appropriate measures include:

- Allow only deployment accounts or administrators to modify the truststore.
- Grant the application the minimum necessary read permissions.
- Do not place the truststore in temporary directories or directories with public write permissions.
- Manage passwords and file protection mechanisms per environment.
- Record certificate fingerprints and origins in administrative configuration.
- Track truststore changes via version control or appropriate artifact management, without committing secrets to repositories.
- Verify the truststore file after deployment.
- Maintain a CA revocation procedure in case a CA certificate or private key is compromised.

A truststore password primarily protects the integrity of the store. Certificates are public data; the critical security goal is preventing unauthorized modification of the trust anchor set.

## 15. Application truststore deployment workflow

A practical workflow for a project:

1. Identify the TLS endpoints and CAs the application needs to trust.
2. Determine whether the application uses the default SSLContext or a custom SSLContext.
3. Obtain the CA certificates from a verified source.
4. Check the SHA-256 fingerprint and certificate validity.
5. Create a dedicated PKCS12 truststore using keytool.
6. Import the certificates using meaningful aliases.
7. Use keytool -list -v to verify the entries.
8. Configure javax.net.ssl.trustStore and trustStoreType before SSLContext is created, or configure TrustManagerFactory directly.
9. If both public CAs and private CAs are required, create a controlled combined truststore.
10. Run HTTPS integration tests and confirm that hostname verification remains enabled.
11. Deploy the truststore with appropriate read permissions.
12. Document the fingerprint, certificate source, validity dates, and update schedule.

For mTLS applications, add the step of configuring a keystore so the application can present its client certificate. The truststore and keystore should be tested independently because server verification failures and client identity presentation failures are two distinct issues.

## 16. Key takeaways

- A truststore stores trusted certificates used to verify a peer's certificate chain.
- TrustManager uses the truststore; KeyManager uses the keystore containing the private key and identity certificate.
- A truststore typically contains trustedCertEntry records, such as root CAs or internal CAs.
- Truststores and keystores can use the same file formats, but they do not share the same role.
- JDK 9 and later use PKCS12 by default; JKS is a legacy format to consider migrating away from.
- cacerts is the JDK's default CA truststore; jssecacerts is checked before cacerts by the JSSE reference implementation when no trustStore property is set.
- javax.net.ssl.trustStore configures the truststore file for the default JSSE TrustManager.
- A custom truststore does not automatically merge with cacerts.
- Validating the certificate chain and verifying the hostname are two separate checks.
- Always verify the SHA-256 fingerprint through an independent source before importing a certificate.
- Do not use -noprompt to accept unverified certificates.
- Use keytool -list, -printcert, and -importcert to inspect, view, and add certificates.
- A truststore must be protected against unauthorized modification and updated according to the CA lifecycle.

## Official references

- [The keytool Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [Security Developer's Guide — Customizing JSSE, JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf)
- [JDK Trust Management](https://ops.java/security/trust)
- [JDK 26 Release Notes — Security Changes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Java KeyStore API — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html)