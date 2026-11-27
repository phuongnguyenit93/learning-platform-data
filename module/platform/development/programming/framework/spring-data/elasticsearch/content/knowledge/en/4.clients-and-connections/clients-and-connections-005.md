# Configuring HTTPS, CAs, and Certificate Verification

When a Spring Data Elasticsearch application connects to an Elasticsearch cluster over the network, the connection must protect both authentication credentials and exchanged data. HTTPS uses TLS to encrypt traffic, authenticate server identity, and detect data tampering in transit. To authenticate the server successfully, the application must trust the CA that signed the certificate and verify the hostname it is connecting to.

In a simple development environment, the application might connect to `http://localhost:9200`. For clusters with security enabled or deployed over a network, the endpoint is typically HTTPS, such as `https://es.example.com:9200`. Changing `http` to `https` alone is not enough: the JVM needs the appropriate CA in its truststore, the server certificate must be valid for the hostname, and the client must keep default TLS verification enabled.

This lesson explains how TLS authenticates Elasticsearch, how to prepare a CA/truststore, how to configure Spring Data Elasticsearch with an SSL context, how to inspect certificates, and how to troubleshoot common errors.

## 1. How do HTTPS and TLS protect the connection?

HTTPS is HTTP running inside a TLS connection. When a client connects to `https://es.example.com:9200`, the TLS handshake takes place before any HTTP request is sent:

1. The client opens a TCP connection to Elasticsearch's hostname and port.
2. The client and server negotiate the TLS version, cipher suite, and cryptographic parameters to use.
3. The server sends its TLS certificate along with any intermediate certificates needed to build the certificate chain.
4. The client checks whether the certificate chain leads to a CA it trusts, whether the certificate is within its validity period, and whether the certificate matches the target hostname.
5. Both sides complete session key establishment. If mutual TLS (mTLS) is enabled, the server also asks the client to prove its identity with a client certificate.
6. After the handshake, HTTP requests and responses are encrypted and integrity-protected by TLS.

```text
Spring Boot application                 Elasticsearch
        |                                     |
        | -------- TCP connection ----------> |
        |                                     |
        | <------ Server certificate -------- |
        |                                     |
        | Validate CA chain, dates, hostname  |
        |                                     |
        | <------ TLS handshake ------------> |
        |                                     |
        | ===== Encrypted HTTP traffic =====> |
        | <==== Encrypted HTTP response ===== |
```

If the client cannot verify the certificate, the TLS handshake fails and no HTTP request is sent to Elasticsearch. This is a TLS-layer error, distinct from an HTTP `401 Unauthorized` error that occurs after a TLS connection has been established when authentication credentials are invalid.

TLS provides three essential properties:

- **Confidentiality:** eavesdroppers on the network cannot read request/response contents.
- **Integrity:** data modified in transit is detected.
- **Server authentication:** the client verifies it is communicating with a server whose identity matches the hostname and whose certificate is signed by a trusted CA.

TLS does not replace Elasticsearch authentication and authorization. The application still needs an account or API key with the minimum required privileges.

## 2. Distinguishing certificate, CA, truststore, and keystore

These concepts often appear together but serve different roles:

| Component | Meaning | Used on which side? |
|---|---|---|
| Server certificate | Certificate confirming the Elasticsearch server's identity | Server sends to client |
| CA certificate | Certificate Authority's certificate used to sign or verify a certificate chain | Client must trust this CA |
| Intermediate CA | Intermediate CA linking the server certificate to the root CA | Usually sent by the server in the certificate chain |
| Truststore | Store of CAs/certificates the application accepts as trust anchors | Client uses to verify the server |
| Keystore | Store holding an entity's own private key and certificate | Server or client uses when proving its identity |

In standard one-way TLS, the Spring Boot application only needs a truststore containing the trusted CA to verify the server certificate. The application does not need Elasticsearch's private key, nor does it need its own client certificate.

In mTLS, each side authenticates the other. The client still needs a truststore to verify the server, and also needs a keystore holding the client certificate and private key to present when the server requests it.

Do not confuse installing a CA into a truststore with installing a server certificate into a keystore. A truststore answers "which CAs do I trust?", while a keystore answers "which private key and certificate do I hold to prove my own identity?".

## 3. Certificate chain and CA

A server certificate is often not signed directly by the root CA. A certificate chain may look like:

```text
Root CA
   |
   v
Intermediate CA
   |
   v
Elasticsearch HTTP certificate
   |
   v
Hostname: es.example.com
```

The server certificate is signed by the intermediate CA; the intermediate CA is signed by the root CA. The client verifies signatures up the chain until it reaches a trusted CA in its truststore. The server usually must send both the server certificate and any relevant intermediate certificates. The root CA is normally already in the truststore and does not necessarily need to be sent during the handshake.

A public CA certificate is not a secret. However, retrieve it from a trusted source and verify its fingerprint or checksum through an independent channel when your deployment process requires it. If an attacker replaces the CA in the truststore with a CA they control, the client could accept forged certificates signed by that CA.

For Elastic Cloud, the deployment provides the HTTPS endpoint and required CA details per the service documentation. For self-managed Elasticsearch, the HTTP CA may be generated during security setup or via the `elasticsearch-certutil` tool. In both cases, the application needs the exact CA that signed the certificate chain returned by the endpoint.

## 4. Hostname verification and Subject Alternative Name

Trusting the CA is not enough to authenticate a server. The client must also verify that the hostname in the URL matches the identity listed in the certificate. For example, when connecting to `https://es.example.com:9200`, the certificate needs a Subject Alternative Name (SAN) matching `es.example.com`.

A SAN can contain DNS names or IP addresses. If the application connects by IP `https://10.0.0.15:9200`, the certificate needs a corresponding IP SAN. A certificate containing only `DNS:es.example.com` is not automatically valid when the client connects via an IP address, even if that IP points to the same server.

Common hostname mismatch scenarios:

- The certificate was issued for `es.internal.example.com`, but the application configuration calls `localhost`.
- The certificate has a DNS SAN, but the application connects directly by IP.
- A load balancer or proxy alters the hostname used by the client.
- An older certificate lacks the new hostname after an endpoint rename.

Use a DNS hostname included in the certificate's SAN and configure DNS/load balancers accordingly. Do not work around errors by disabling hostname verification or using `NoopHostnameVerifier`; doing so lets the client connect to an impostor server even if the CA chain appears valid.

## 5. Preparing the CA for the application

Before configuring Spring, obtain the CA certificate that signed Elasticsearch's HTTP certificate. A common filename in some self-managed Elasticsearch installations is `http_ca.crt`, though the exact path depends on deployment setup. For managed services, download the CA following the provider's instructions.

Do not copy the CA's private key into the application. A client application only needs the public CA certificate to verify the server.

### 5.1. Inspecting certificate details

If OpenSSL is available, you can inspect certificate details:

```bash
openssl x509 -in http_ca.crt -noout -subject -issuer -dates -fingerprint -sha256
```

This command prints the subject, issuer, validity dates, and SHA-256 fingerprint. Compare the fingerprint against the value published through a trusted channel before adding the CA to your truststore.

To view the SANs of a server certificate (if you have the server certificate file):

```bash
openssl x509 -in http.crt -noout -text
```

Look for the `X509v3 Subject Alternative Name` section and confirm the hostname your application uses appears in that list.

### 5.2. Creating a PKCS12 truststore with keytool

The JDK ships with `keytool`, which can create a PKCS12 truststore and import a CA certificate:

```bash
keytool -importcert \
  -alias elasticsearch-http-ca \
  -file http_ca.crt \
  -keystore elasticsearch-truststore.p12 \
  -storetype PKCS12
```

`keytool` prompts for a truststore password and confirmation to import the certificate. Verify the contents after creation:

```bash
keytool -list -v \
  -keystore elasticsearch-truststore.p12 \
  -storetype PKCS12
```

A truststore contains only public CA certificates and does not require the same protection as a private key, but its password should still be managed to control modifications to the truststore. Do not commit real environment truststores or passwords to the repository if prohibited by your organization's policy.

You can place the truststore in a mounted configuration directory or package the CA certificate/truststore according to your release process. In container/Kubernetes environments, files are commonly mounted and passwords supplied via secrets.

### 5.3. Direct PEM CA or truststore?

Some clients or SSL configurations support reading a PEM CA certificate directly. Other Java configurations require a JKS or PKCS12 truststore. Choose the format supported by your client and framework version.

PKCS12 is a widely used portable format supported by the JDK. If the application needs to trust multiple CAs, you can import multiple certificates into the same truststore under distinct aliases. Add only the CAs actually needed; never blindly import certificates retrieved from an unverified connection.

## 6. Testing HTTPS before configuring Spring Boot

First, test connectivity from the environment where the application runs. This confirms the CA and endpoint are right before investigating Java configuration.

With `curl`, specify the CA certificate:

```bash
curl --cacert http_ca.crt https://es.example.com:9200
```

If Elasticsearch requires Basic Authentication, supply the username so curl prompts for the password:

```bash
curl --cacert http_ca.crt \
  --user elastic \
  https://es.example.com:9200
```

Do not put real passwords directly into shell history or shared command lines. Use a secret mechanism appropriate for the actual environment.

You can test the TLS handshake with OpenSSL:

```bash
openssl s_client \
  -connect es.example.com:9200 \
  -servername es.example.com \
  -CAfile http_ca.crt \
  -verify_hostname es.example.com \
  -verify_return_error
```

`-servername` sends SNI so the server or load balancer selects the right certificate; `-CAfile` specifies the trusted CA; `-verify_hostname` checks the hostname. When verification succeeds, OpenSSL reports successful verification of the certificate chain. This command tests TLS; it does not replace testing an application request with Elasticsearch authentication credentials.

Avoid using `curl -k` or `--insecure` as a lasting setup. These flags skip certificate verification, allowing tests to succeed even when the application is connecting to an untrusted server.

## 7. Configuring Spring Data Elasticsearch with SSLContext

Spring Data Elasticsearch provides `ClientConfiguration` to describe endpoints, authentication, and SSL for the client. When a custom CA is needed, the application can build an `SSLContext` with a truststore containing the CA and pass this context to `ClientConfiguration`.

The example below shows how to load a PKCS12 truststore using standard Java APIs:

```java
import java.io.InputStream;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ElasticsearchSslContextFactory {

    private ElasticsearchSslContextFactory() {
    }

    public static SSLContext fromTrustStore(
            InputStream trustStoreInput,
            char[] trustStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        trustStore.load(trustStoreInput, trustStorePassword);

        TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(null, trustManagerFactory.getTrustManagers(), null);
        return sslContext;
    }
}
```

`KeyStore` loads the CA certificate from the truststore. `TrustManagerFactory` creates trust managers responsible for validating the certificate chain. `SSLContext` bundles the TLS configuration for the client to use. Passing `null` for `KeyManager[]` means this example provides no client certificate; it fits one-way TLS.

Never create a trust manager that accepts all certificates. Never replace the hostname verifier with an implementation that always returns `true`. Both practices defeat the very server identity verification HTTPS is meant to provide.

### 7.1. Integrating SSLContext with ClientConfiguration

With Spring Data Elasticsearch client configuration, you can extend `ElasticsearchConfiguration` and return `ClientConfiguration`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

import javax.net.ssl.SSLContext;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    private final SSLContext sslContext;

    public ElasticsearchClientConfig(SSLContext sslContext) {
        this.sslContext = sslContext;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("es.example.com:9200")
                .usingSsl(sslContext)
                .withBasicAuth("${ES_USERNAME}", "${ES_PASSWORD}")
                .build();
    }
}
```

The snippet above illustrates wiring an SSL context into a manually configured client. In a real application, do not write placeholders `"${ES_USERNAME}"` and `"${ES_PASSWORD}"` as literal Java strings. Inject credentials from Spring configuration or a secret manager, and build `SSLContext` from similarly injected resources/passwords. Also ensure these client configuration beans properly replace the active auto-configuration; do not declare two parallel configurations creating the same Elasticsearch client.

Package names and configuration APIs may vary across major/minor releases of Spring Data Elasticsearch. Check the Javadoc/documentation for your project's exact version, especially when upgrading clients. The essence of the configuration is that `ClientConfiguration` must use HTTPS and receive an `SSLContext` built from a trusted CA.

### 7.2. Configuration example using application.yml

Keep environment-specific values out of source code:

```yaml
app:
  elasticsearch:
    host: ${ELASTICSEARCH_HOST:es.example.com}
    port: ${ELASTICSEARCH_PORT:9200}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    truststore: ${ELASTICSEARCH_TRUSTSTORE:file:/run/secrets/elasticsearch-truststore.p12}
    truststore-password: ${ELASTICSEARCH_TRUSTSTORE_PASSWORD}
```

This is a custom application configuration namespace used for the custom client example; these properties are not standard `spring.elasticsearch.*` properties. A configuration class needs to bind them using `@ConfigurationProperties` or equivalent injection, open the truststore from the declared resource, and create the SSL context.

When running in containers, `/run/secrets/elasticsearch-truststore.p12` must be mounted into the container. In other deployments, replace the path with the actual truststore location. Never put real passwords into committed YAML files.

## 8. Using Spring Boot SSL bundles

Some Spring Boot versions provide SSL bundles to manage truststores/keystores centrally and allow integrations to reference them. How SSL bundles are configured and whether the Elasticsearch REST client has a property linking directly to a bundle depend on the specific Spring Boot version.

When your version supports linking an SSL bundle to the Elasticsearch client, configure it according to the property metadata and documentation of that version. For example, a JKS/PKCS12 bundle definition might look like:

```yaml
spring:
  ssl:
    bundle:
      jks:
        elasticsearch:
          truststore:
            location: file:/run/secrets/elasticsearch-truststore.p12
            password: ${ELASTICSEARCH_TRUSTSTORE_PASSWORD}
            type: PKCS12
```

The bundle name in this example is `elasticsearch`. This configuration declares trust material for the bundle; by itself, it does not guarantee the Elasticsearch client automatically uses the bundle. You must configure the SSL bundle integration property provided by your exact Spring Boot version, or register a customizer/client configuration per that version's API.

If your Spring Boot version lacks SSL bundle integration for the Elasticsearch client, you can use the `SSLContext` and `ClientConfiguration` approach from the previous section. Do not mix a custom client configuration with default auto-configuration unless it is clear which bean is active.

## 9. When is mutual TLS needed?

In one-way TLS, the client verifies the server using a CA. The server does not ask for a client-specific certificate; the application typically authenticates with Basic Authentication or an API key after the TLS handshake completes.

In mutual TLS, the server requires the client to present a certificate. In that case, the application needs:

1. A truststore containing the CA used to verify the server.
2. A keystore containing the client certificate and its corresponding private key.
3. A TLS context configured with both `KeyManager[]` and `TrustManager[]`.
4. Elasticsearch or the proxy in front configured to trust the CA that issued the client certificate and map the certificate to appropriate permissions.

Example initializing an SSLContext for mTLS at the JDK level:

```java
KeyStore clientKeyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = clientKeyStoreResource.getInputStream()) {
    clientKeyStore.load(input, clientKeyStorePassword.toCharArray());
}

KeyManagerFactory keyManagerFactory = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagerFactory.init(clientKeyStore, clientKeyPassword.toCharArray());

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = trustStoreResource.getInputStream()) {
    trustStore.load(input, trustStorePassword.toCharArray());
}

TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagerFactory.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        keyManagerFactory.getKeyManagers(),
        trustManagerFactory.getTrustManagers(),
        null);
```

This snippet handles creating the SSL context; pass that context into the Elasticsearch client configuration as shown earlier. A keystore containing a private key is sensitive material. Restrict file read permissions, never log private keys or passwords, and rotate certificates according to security policy.

Do not enable mTLS merely because the server uses HTTPS. Only configure a client certificate when the cluster or gateway actually requires it.

## 10. TLS authentication differs from Elasticsearch authentication

These two layers of authentication are independent:

| Layer | Question Answered | Mechanism |
|---|---|---|
| TLS server authentication | Is the client connecting to the right server? | CA chain, validity dates, SAN/hostname verification |
| TLS client authentication (if mTLS is enabled) | Does the client have a certificate accepted by the server? | Client certificate and a CA trusted by the server |
| Elasticsearch authentication | Which user/service account does the request belong to? | Basic Authentication, API key, or configured auth mechanism |
| Elasticsearch authorization | What is that identity allowed to do? | Roles, privileges, and cluster/index permissions |

For example, the TLS handshake may succeed while Elasticsearch returns `401 Unauthorized` due to a wrong username/password. Conversely, a valid username/password will not get past a `PKIX path building failed` error, because the request never cleared the TLS step.

For production applications, provision a dedicated service account and grant only the required permissions on specific indices. Do not use the administrative `elastic` account for everyday application operations.

## 11. Troubleshooting common TLS errors

| Message or Symptom | Common Cause | How to Fix |
|---|---|---|
| `PKIX path building failed` | JVM cannot build a certificate chain to a trusted CA | Check the CA, truststore, certificate chain, and which truststore the process actually loads |
| `unable to find valid certification path` | Missing CA/intermediate or wrong truststore | Obtain the right CA from a trusted source, import it into the truststore, and verify path settings |
| `No subject alternative DNS name matching ...` | Hostname in the URL does not match the certificate SAN | Use a hostname present in the SAN or reissue the certificate with the proper SAN |
| `CertificateExpiredException` | Certificate has expired | Renew/reissue the certificate and update the chain/trust material |
| `CertificateNotYetValidException` | System clock is wrong or certificate validity starts in the future | Check system clock/NTP and certificate validity dates |
| `handshake_failure` | Sides cannot agree on TLS/ciphers or mTLS is invalid | Check TLS versions, ciphers, client certificate, and server/proxy configuration |
| `unknown_ca` | Receiving side does not trust the issuer CA of the peer's certificate | Check the corresponding truststore and the CA that issued the certificate |
| `401 Unauthorized` | TLS succeeded, but Elasticsearch credentials are invalid/missing | Check Basic Auth/API key and access permissions |
| `Connection refused` or timeout | Endpoint, port, DNS, firewall, or node not ready | Check network and Elasticsearch status before investigating certificates |

### 11.1. Verifying the right truststore is being used

A common mistake is creating the right truststore while the application still reads a different truststore or no file at all. Check:

- The path resolves inside the process/container, not on the host machine.
- The file is properly mounted and readable by the user running the JVM.
- The declared store type matches the file format, e.g., `PKCS12`.
- The truststore password is correct.
- The CA in the truststore is the CA that signed the certificate chain of the target endpoint.
- The application actually uses the configured SSL context/client bean rather than accidentally falling back to another auto-configured client.

In test environments, you can enable JVM TLS debug logging to diagnose handshakes. TLS logs can contain detailed certificate and connection data, so enable them only temporarily, restrict access, and turn them off after investigation.

## 12. Managing certificates in operations

TLS requires ongoing operational maintenance. Certificates expire and CAs can be replaced, so applications need a process for updating trust material.

### 12.1. CA rotation

When migrating from an old CA to a new CA, you can roll it out in phases:

1. Add the new CA to the application's truststore while keeping the old CA.
2. Issue or switch server certificates to the new CA.
3. Verify all application instances connect successfully with the new certificate.
4. Once no server uses the old CA, remove the old CA from the truststore in a subsequent release.

This phased rollout avoids a window where applications distrust certificates actively served by the servers. Exact steps should coordinate with how the cluster, load balancers, and applications roll out certificates.

### 12.2. Tracking certificate expiration

Track start and expiration dates of server certificates, intermediate CAs, client certificates (if using mTLS), and related certificates. Set alerts far enough ahead of expiration to allow time for issuing, distributing, and testing new certificates.

### 12.3. Managing secrets and files

- Store truststore, keystore, and private key passwords in a secret manager or platform secret store.
- Restrict read permissions on truststore/keystore files following least privilege.
- Never log passwords, private keys, or secret contents.
- Never commit private keys or real credentials to Git.
- Mount certificates and truststores so they can be updated during rotation.
- Check configuration reload behavior: some clients load the SSL context only at startup. After replacing a truststore, you may need to recreate the client or restart the application depending on deployment mechanics.

## 13. Recommendations for configuring HTTPS in Spring Data Elasticsearch

When deploying an application, follow these principles:

- Use `https://` for TLS endpoints with a hostname matching the server certificate SAN.
- Trust only verified CAs; keep the full certificate chain intact.
- Keep default client certificate validation and hostname verification enabled.
- Use a dedicated truststore or a Spring Boot-supported SSL bundle when an internal CA is needed.
- Only configure a keystore/client certificate when the system requires mTLS.
- Externalize endpoints, usernames, passwords, and truststore passwords out of source code.
- Keep TLS versions/ciphers at secure levels supported by the JDK and Elasticsearch; never downgrade TLS just to bypass handshake errors.
- Distinguish TLS errors, HTTP authentication errors, and authorization errors to address the right layer.
- Plan CA/certificate rotation and test ahead of expiration.

## 14. Reference deployment workflow

A workflow for configuring an HTTPS connection from Spring Boot to Elasticsearch can follow these steps:

1. Obtain the HTTPS endpoint and CA certificate from the cluster administrator or service provider.
2. Verify the CA's origin and fingerprint; check the server certificate SAN and expiration date.
3. Test the endpoint with `curl --cacert` or OpenSSL with hostname verification.
4. Create a PKCS12 truststore from the CA if the client requires a Java truststore.
5. Provision the truststore into the application runtime and put its password in a secret manager.
6. Configure Spring Data Elasticsearch with an SSL context holding the trust manager from the truststore, or use the SSL bundle integration supported by your Spring Boot version.
7. Configure Elasticsearch authentication separately using Basic Auth/API key; only add a client certificate if mTLS is enabled.
8. Start the application and verify a real request succeeds over HTTPS.
9. Monitor certificate expiration and prepare a CA rotation process.

Once properly configured, Spring Data Elasticsearch continues to provide repository operations and queries as normal. HTTPS and the CA handle the underlying transport security layer; entities, mappings, and repository calls do not need to change simply because the endpoint switched from HTTP to HTTPS.
