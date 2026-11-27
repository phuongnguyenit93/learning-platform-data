# TLS, Certificate Verification, and Proxy Connections

Spring Boot often calls managed services over HTTPS: Azure App Configuration, Azure Key Vault, AWS S3, Google Cloud Storage, or internal APIs. HTTPS protects data in transit, but the application is only properly protected when it **verifies server certificates**, uses the right trust material, handles proxies intentionally, and tests the actual connection paths.

In Java, TLS is enforced by JSSE or the HTTP client's TLS stack. Spring Boot provides **SSL bundles** to manage truststores/keystores and apply them to certain auto-configured clients. However, the AWS SDK, Azure SDK, and Google Cloud client libraries each have their own HTTP transports and proxy configuration mechanisms. Therefore, a single TLS/proxy configuration in Spring does not automatically apply to every client in the application.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, including identity/permissions, storage access, messaging, data, secret protection, testing, and evaluating differences across cloud providers. The goal of this lesson is to establish reliable TLS connections, verify certificates, configure proxies per transport, and diagnose errors without disabling security mechanisms.

## 1. Objectives and Real-World Scenario

Suppose `order-service` needs to:

- Call `https://payments.example.com` to process transactions.
- Call Azure Key Vault to retrieve secrets.
- Call Amazon S3 or Google Cloud Storage to read documents.
- Route through a corporate proxy on an internal network.
- Connect to a partner API that requires **mutual TLS (mTLS)**.

After this lesson, you will be able to:

1. Distinguish between TLS, server certificates, truststores, keystores, and mTLS.
2. Explain the verification process for certificate chains, hostnames, and certificate validity periods.
3. Create a PKCS12/JKS truststore and configure a Spring Boot SSL bundle using JKS or PEM.
4. Apply an SSL bundle to `RestClient`/`WebClient` and pass `SSLContext` to SDKs when the transport supports it.
5. Distinguish between an HTTP forward proxy, an HTTPS CONNECT tunnel, and a TLS inspection proxy.
6. Configure proxies differently for the Azure SDK, AWS SDK for Java 2.x, and Google Cloud Java client libraries.
7. Test TLS success/failure, verify proxies, handle certificate rotation, and read handshake logs.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["HTTP client / cloud SDK transport"]
    B --> C["Proxy if present"]
    C --> D["TLS handshake with endpoint"]
    D --> E["Receive certificate chain"]
    E --> F["Truststore: Is CA trusted?"]
    F --> G["Does Hostname/SAN match?"]
    G --> H["TLS session established"]
    H --> I["HTTP request / gRPC RPC"]
    F -->|No| X["Handshake failed"]
    G -->|No| X
~~~

**Key point:** A proxy only determines the path of the request. TLS must still verify the endpoint's identity according to the trust policy.

## 2. What Does TLS Protect?

TLS (Transport Layer Security) provides three core properties for a connection:

- **Confidentiality:** encrypts exchanged data so eavesdroppers cannot read the content.
- **Integrity:** detects data tampering in transit.
- **Authentication:** verifies the server via certificates; with mTLS, the server also verifies the client.

HTTPS is HTTP running over TLS. Cloud services typically require HTTPS and modern TLS versions. For example, the AWS SDK for Java 2.x requires a JDK that supports at least TLS 1.2 and recommends TLS 1.3.

### 2.1. Server authentication

When a Java client connects to `api.partner.example`:

1. The client sends a ClientHello containing TLS versions, cipher suites, and parameters needed for negotiation.
2. The server responds and sends its certificate chain.
3. The client checks whether the certificate can build a trust path to a CA located in the truststore.
4. The client checks the validity period, key usage purposes, signatures, and certificate constraints.
5. The client verifies that the URL hostname matches the Subject Alternative Name (SAN) of the certificate.
6. Both sides complete the handshake and derive session keys to encrypt data.

If the certificate chain is valid but the SAN does not contain the target hostname, the connection must still fail. Never bypass hostname verification just to make a connection succeed.

### 2.2. Certificate chain

A typical chain:

~~~text
Server certificate (leaf)
       |
       v
Intermediate CA certificate
       |
       v
Root CA certificate (trust anchor)
       |
       v
Client truststore
~~~

The server typically sends the leaf certificate and the necessary intermediate certificates. The client already has the trusted root CA in its truststore to verify the chain. If the server omits an intermediate certificate or the client lacks the required trust anchor, the handshake may report `PKIX path building failed`.

Do not simply import a single server's leaf certificate into the truststore as a temporary workaround. Normally, trust **the root or intermediate CA approved by your organization**. Leaf certificate pinning is a separate strategy that requires a certificate replacement and rollback plan.

### 2.3. SAN, hostname, and SNI

Three concepts that are often confused:

| Concept | Role |
| --- | --- |
| **SAN (Subject Alternative Name)** | List of DNS names/IPs that the certificate is issued for |
| **Hostname verification** | Compares the hostname in the URL against the certificate's SAN |
| **SNI (Server Name Indication)** | Client indicates the host name during the handshake so the server selects the appropriate certificate |

If an endpoint is called by IP address but the certificate only has DNS SANs, hostname verification can fail. If a proxy or load balancer mishandles SNI, the server may return a certificate for a different virtual host.

Do not use an IP address instead of a hostname when an endpoint is designed for DNS-based verification, unless the certificate has a valid IP SAN.

## 3. Truststore and Keystore: Two Different Roles

| Component | What does it contain? | What is it used for? |
| --- | --- | --- |
| **Truststore** | Certificates of trusted CAs | Verifying server/peer certificates |
| **Keystore** | The application's own private key and certificate chain | Proving client or server identity in mTLS |
| **Certificate chain** | Leaf and intermediate certificates | Allowing the peer to build a trust path |
| **Private key** | The private key corresponding to the certificate | Proving key ownership; must be kept secret |

When an application only calls standard HTTPS APIs, it usually needs a **truststore**, not a client keystore. When a partner requires mTLS, the client needs a **keystore** containing the application's certificate and private key, while still needing a truststore to verify the server.

### 3.1. One-way HTTPS connection

~~~text
Spring Boot client
  - Truststore: CA that signed the server certificate
  - No client certificate needed
          |
          | TLS: verify server
          v
HTTPS server
  - Server certificate + private key
~~~

### 3.2. Mutual TLS connection

~~~text
Spring Boot client                         Partner server
  Keystore: client cert + private key        Truststore: CA that signed client cert
  Truststore: CA that signed server cert     Keystore: server cert + key
            |                                          |
            |---- Client verifies server ------------->|
            |<--- Server requests client certificate --|
            |---- Client sends certificate chain ----->|
            |<--- Server verifies client --------------|
            |=========== TLS session ==================|
~~~

The private key is never sent during the TLS handshake. The client sends its certificate and creates a handshake signature using its private key to prove ownership of the corresponding key.

## 4. Creating and Inspecting a Truststore with keytool

Java provides the `keytool` utility to manage certificates and keystores. For example, an enterprise has an internal CA `corp-root-ca.pem` used to sign certificates for a TLS inspection proxy or internal APIs.

### 4.1. Verify the certificate before importing

Inspect certificate details:

~~~bash
keytool -printcert -file corp-root-ca.pem
~~~

Or with OpenSSL:

~~~bash
openssl x509 -in corp-root-ca.pem -noout -subject -issuer -dates -fingerprint -sha256
~~~

Cross-check the fingerprint against a trusted channel provided by your CA/security team. Do not import a certificate merely because it appeared in a handshake error or was sent over an unverified channel.

### 4.2. Create a PKCS12 truststore

~~~bash
keytool -importcert \
  -alias corp-root-ca \
  -file corp-root-ca.pem \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

`keytool` will prompt for a password if not provided. Do not put real passwords on the command line, in committed scripts, or in shell history. Verify the contents:

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

In production, the truststore should be mounted from secret/configuration management or packaged through a controlled process. Do not commit private keys or passwords to Git. Public CA certificates are not private keys, but their source and change management still need verification.

### 4.3. Create a keystore for an mTLS client

If you have received a client certificate from a CA, you need a keystore containing the **client-owned private key** along with the corresponding certificate chain. The typical workflow includes:

1. Generate a key pair and CSR in a keystore or HSM.
2. Submit the CSR to the CA/partner according to procedure.
3. Receive the certificate reply and intermediate chain.
4. Import the certificate chain into the exact alias containing the private key.
5. Verify the alias, validity period, SAN/subject, and key usage.

Example generating a key pair in PKCS12 (for testing environments only):

~~~bash
keytool -genkeypair \
  -alias checkout-client \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -keystore checkout-client.p12 \
  -storetype PKCS12
~~~

In real environments, choose key algorithms and key sizes according to CA standards and organizational policy. Do not use self-signed certificates in production unless the trust model has been explicitly approved.

## 5. Configuring Spring Boot SSL Bundles

Spring Boot supports **SSL bundles** to group trust material, key material, protocols, and TLS options under a single name. A bundle can be used for a server or a client; a standard HTTPS client needs a truststore, while mTLS additionally requires a client keystore.

### 5.1. JKS/PKCS12 truststore for outbound HTTPS

Example `application.yml`:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        partner-api:
          truststore:
            location: "file:/run/secrets/partner-truststore.p12"
            password: "${PARTNER_TRUSTSTORE_PASSWORD}"
            type: PKCS12
~~~

- `partner-api` is the bundle name chosen by the application.
- `location` is the truststore file mounted at runtime.
- `password` is retrieved from secret management; never commit real values.
- `type: PKCS12` specifies the keystore type.

There is no need to declare a keystore if the client does not use mTLS. When configuring a custom truststore, check that it contains **all necessary CAs** for the endpoints the client calls. A custom truststore containing only an internal CA may cause other public endpoints to stop being trusted if the client exclusively uses that truststore.

### 5.2. PEM truststore

If your certificate management system uses PEM format:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-api:
          truststore:
            certificate: "file:/run/secrets/partner-ca-chain.pem"
~~~

Spring Boot can also accept inline PEM content or resource locations. For mounted files, use an explicit URI such as `file:/run/secrets/...`. Do not confuse public certificates with private keys.

### 5.3. Outbound mTLS using a JKS/PKCS12 bundle

If a partner requires a client certificate:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        partner-mtls:
          key:
            alias: checkout-client
          keystore:
            location: "file:/run/secrets/checkout-client.p12"
            password: "${CLIENT_KEYSTORE_PASSWORD}"
            type: PKCS12
          truststore:
            location: "file:/run/secrets/partner-truststore.p12"
            password: "${PARTNER_TRUSTSTORE_PASSWORD}"
            type: PKCS12
~~~

The bundle serves two roles:

- `keystore`: the client's certificate and private key sent to the partner.
- `truststore`: the CA used to verify the partner's certificate.

The private key must be protected by secret management or an appropriate HSM. Do not mount private keys into a directory with broad read permissions.

### 5.4. Configuring a server to require client certificates

When Spring Boot itself acts as the server and requires client mTLS, configure the server bundle containing the server's certificate/private key and the truststore of the CA that issues client certificates:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: inbound-mtls
    client-auth: need

spring:
  ssl:
    bundle:
      jks:
        inbound-mtls:
          key:
            alias: checkout-server
          keystore:
            location: "file:/run/secrets/server-keystore.p12"
            password: "${SERVER_KEYSTORE_PASSWORD}"
            type: PKCS12
          truststore:
            location: "file:/run/secrets/client-ca-truststore.p12"
            password: "${CLIENT_CA_TRUSTSTORE_PASSWORD}"
            type: PKCS12
~~~

`client-auth: need` requires clients to present a valid certificate. The `want` value requests a client certificate but allows proceeding without one; `none` does not require a client certificate. Always enforce authorization policies at the application layer after TLS verifies the certificate identity; mTLS does not automatically grant business permissions.

## 6. Applying SSL Bundles to Spring REST Clients

### 6.1. RestClient in Spring Boot 3.5

Spring Boot provides `RestClientSsl` to apply a declared bundle:

~~~java
package com.example.checkout;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class PartnerHttpConfiguration {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl) {
        return builder
                .baseUrl("https://payments.example.com")
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

`RestClientSsl.fromBundle("partner-api")` attaches the bundle's trust material to the `ClientHttpRequestFactory`. With the `partner-mtls` bundle, the client can send a client certificate if the transport and configuration support it.

Note: applying an SSL bundle may replace a previously configured `ClientHttpRequestFactory`. If you need to combine proxy settings, timeouts, and SSL, configure a suitable request factory explicitly rather than assuming all previous customizers will be preserved automatically.

### 6.2. WebClient

For `WebClient`, Spring Boot provides `WebClientSsl` to apply a bundle to the connector:

~~~java
package com.example.checkout;

import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            WebClientSsl ssl) {
        return builder
                .baseUrl("https://payments.example.com")
                .apply(ssl.fromBundle("partner-api"))
                .build();
    }
}
~~~

Exact import/package APIs and connectors depend on the Spring Boot version. If you create a `WebClient` manually with `WebClient.create()`, Spring Boot's auto-configurations/customizers are not applied automatically; you must configure the corresponding `ClientHttpConnector`.

### 6.3. Using an SSL bundle with a custom SDK client

Spring Boot auto-configures an `SslBundles` bean. You can obtain an `SSLContext` from the bundle to pass to SDKs/HTTP transports that support it:

~~~java
import javax.net.ssl.SSLContext;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Component;

@Component
public class PartnerTlsContext {
    private final SSLContext sslContext;

    public PartnerTlsContext(SslBundles sslBundles) {
        this.sslContext = sslBundles.getBundle("partner-api").createSslContext();
    }

    public SSLContext sslContext() {
        return sslContext;
    }
}
~~~

Not every SDK accepts `SSLContext` directly. Some SDKs require configuration via Netty, Apache HttpClient, a gRPC channel, or a dedicated native transport. Check the builder of the **exact HTTP client implementation** used by the SDK.

**An SSL bundle is not a global configuration for every library.** It is only used where you explicitly apply the bundle or pass the SSL objects into the corresponding transport.

## 7. TLS and Proxies: Understanding the Connection Path

A corporate proxy is typically a **forward proxy**. Clients send requests to the proxy; the proxy connects to the destination host according to network policy.

### 7.1. HTTP CONNECT tunnel

For HTTPS through an HTTP proxy, the client typically asks the proxy to establish a tunnel:

~~~text
Client -> Proxy: CONNECT payments.example.com:443
Proxy -> Client: 200 Connection Established
Client <====== Direct TLS handshake with payments.example.com ======>
Client <================ HTTPS request/response =====================>
~~~

The proxy sees the hostname/port and network metadata, but in a standard CONNECT tunnel, TLS traffic is encrypted end-to-end between client and server.

### 7.2. HTTPS proxy

If the proxy endpoint itself uses HTTPS, the client establishes TLS to the **proxy** first. It can then create a TLS tunnel to the destination server. Distinguish between:

- Proxy certificate: verifies the TLS connection to the proxy when the proxy uses HTTPS.
- Origin certificate: verifies the destination server inside the tunnel.
- Proxy authentication: authenticates the client to the proxy, such as username/password or an enterprise mechanism.

Proxy authentication and server certificate validation are two separate steps.

### 7.3. TLS inspection proxy

Some corporate proxies decrypt and re-encrypt TLS traffic. In that case:

~~~text
Client --TLS--> Corporate proxy --TLS--> Origin server
        cert signed by corporate CA
~~~

The client sees a certificate issued by the internal CA for the destination hostname. For the connection to succeed, the application must trust the inspection CA approved by the security team.

This is a critical trust decision: the proxy can read request/response payloads within the inspection scope. Do not blindly install a CA encountered in a handshake error; verify its fingerprint and scope before trusting it.

### 7.4. A proxy does not replace TLS

| Component | Responsibility |
| --- | --- |
| Proxy | Routing, outbound control, may require proxy authentication |
| TLS | Encryption and endpoint verification |
| Truststore | Defines which CAs the client accepts |
| Hostname verification | Ensures the certificate belongs to the exact host being called |
| mTLS | Verifies both client and server using certificates |

Never disable TLS verification so that a proxy can forward requests. If proxy inspection is a legitimate requirement, install the proper trust anchor and continue enforcing hostname verification.

## 8. Configuring Proxies in Java

### 8.1. Java system properties

Some Java HTTP clients use system properties:

~~~bash
java \
  -Dhttps.proxyHost=proxy.corp.example \
  -Dhttps.proxyPort=8080 \
  -Dhttp.nonProxyHosts="localhost|127.*|*.svc.cluster.local" \
  -Djavax.net.ssl.trustStore=/run/secrets/corp-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar order-service.jar
~~~

Common properties:

| Property | Meaning |
| --- | --- |
| `http.proxyHost`, `http.proxyPort` | Proxy for HTTP |
| `https.proxyHost`, `https.proxyPort` | Proxy for HTTPS in supporting clients |
| `http.nonProxyHosts` | List of hosts to reach directly |
| `javax.net.ssl.trustStore` | Default truststore for JSSE |
| `javax.net.ssl.trustStorePassword` | Truststore password |
| `javax.net.ssl.keyStore` | Default keystore for JSSE |
| `javax.net.ssl.keyStorePassword` | Keystore password |

System properties are **JVM-wide** configurations for clients using JSSE/default proxy behavior. If an application uses multiple SDKs with different transports, global settings might not be applied or might affect unintended clients. Prefer per-client configuration when different policies are needed.

### 8.2. Environment variables

Some SDKs/clients support:

~~~bash
export HTTP_PROXY="http://proxy.corp.example:8080"
export HTTPS_PROXY="http://proxy.corp.example:8080"
export NO_PROXY="localhost,127.0.0.1,.svc.cluster.local"
~~~

The rules for reading proxy environment variables are **not identical across all SDKs**. For example, the Azure SDK for Java has its own precedence order; the AWS SDK for Java 2.x and Google Cloud Java libraries also have support matrices by HTTP transport.

Do not assume that setting `HTTPS_PROXY` configures every library in the same JVM. Verify with a test request for each SDK.

### 8.3. Proxy authentication

If the proxy requires a username/password, do not embed credentials in the URL:

~~~text
Avoid:
https://user:password@proxy.corp.example:8080
~~~

Instead, retrieve credentials from a secret manager and configure them via a builder/client that supports proxy authentication. Never log proxy URLs containing userinfo, `Proxy-Authorization` headers, or proxy environment variables that contain passwords.

### 8.4. Non-proxy hosts

Internal endpoints can be reached directly:

~~~text
localhost
127.0.0.1
*.svc.cluster.local
metadata.google.internal
~~~

`NO_PROXY` and `http.nonProxyHosts` have different wildcard and delimiter rules depending on the client. AWS SDK for Java 2.x behaves differently across Apache, Netty, URLConnection, and CRT-based clients; Azure and Google also have their own configuration conventions. Check the documentation of the specific transport in use instead of copying a single wildcard string across all SDKs.

## 9. Configuring Proxies by Cloud Provider

### 9.1. Azure SDK for Java

The Azure SDK for Java supports proxy configuration via:

- Environment/global Configuration.
- A dedicated `Configuration` for the HTTP client.
- Explicit `ProxyOptions` on the client builder.

Example Netty HTTP client with an authenticated proxy:

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.ProxyOptions;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import java.net.InetSocketAddress;

HttpClient azureHttpClient = new NettyAsyncHttpClientBuilder()
        .proxy(new ProxyOptions(
                ProxyOptions.Type.HTTP,
                new InetSocketAddress("proxy.corp.example", 8080))
                .setCredentials(proxyUsername, proxyPassword))
        .build();
~~~

Then pass `azureHttpClient` into the Azure service client builder that supports `httpClient(...)` or the corresponding `httpClient` option. For example, client builders based on Azure Core typically accept a configured `HttpClient`.

Azure SDK builders may read environment proxy settings according to their own rules. Microsoft documentation notes that implicit use of `HTTP_PROXY`/`HTTPS_PROXY` depends on Java proxy/system configuration. If you need a dedicated proxy for one client, passing explicit `ProxyOptions` keeps the scope well-bounded.

If you want to ignore proxy environment/global configuration, the Azure HTTP client builder can use `Configuration.NONE`; only do so when a direct network path to the endpoint is permitted.

### 9.2. AWS SDK for Java 2.x

AWS SDK for Java 2.x allows proxy configuration on the HTTP client builder:

~~~java
import java.net.URI;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.http.apache.ProxyConfiguration;
import software.amazon.awssdk.services.s3.S3Client;

var proxy = ProxyConfiguration.builder()
        .endpoint(URI.create("http://proxy.corp.example:8080"))
        .username(proxyUsername)
        .password(proxyPassword)
        .addNonProxyHost("localhost")
        .build();

var httpClient = ApacheHttpClient.builder()
        .proxyConfiguration(proxy)
        .build();

S3Client s3 = S3Client.builder()
        .httpClient(httpClient)
        .build();
~~~

Proxy settings can also come from JVM system properties and environment variables. **Support for HTTPS proxy properties depends on the HTTP client type**: AWS documentation states that Apache/URLConnection, Netty, and CRT have different support matrices. Verify the exact `ApacheHttpClient`, `NettyNioAsyncHttpClient`, or `AwsCrtAsyncHttpClient` being used.

TLS also differs: the AWS SDK uses JSSE with certain HTTP clients, whereas AWS CRT has its own TLS stack. System properties such as `jdk.tls.client.protocols` and `javax.net.debug` do not behave the same way with CRT. Do not conclude that the entire AWS SDK uses JSSE just because the application runs on a JVM.

### 9.3. Google Cloud Java client libraries

Google Cloud Java client libraries use HTTPS and gRPC. Google documentation states that proxies can be configured via Java system properties `https.proxyHost`/`https.proxyPort`; HTTP clients can use `http.proxyHost`.

For an HTTP transport requiring custom proxy authentication, you can create an `HttpTransportFactory` and pass it to `GoogleCredentials`. Architectural example:

~~~java
HttpTransportFactory transportFactory = createAuthenticatedProxyTransport(
        proxyHost, proxyPort, proxyUsername, proxyPassword);

GoogleCredentials credentials =
        GoogleCredentials.getApplicationDefault(transportFactory);
~~~

The `createAuthenticatedProxyTransport` method needs to configure an Apache HTTP transport with a proxy route planner and credentials provider per Google's guidance. Never hardcode the proxy password in source code.

For custom gRPC proxies, Google Cloud docs guide providing a `ProxyDetector` to `ManagedChannelBuilder` and constructing an `HttpConnectProxiedSocketAddress`. Because gRPC transport differs from HTTP/REST, setting `HTTPS_PROXY` does not guarantee that all gRPC clients use proxy authentication in the same way.

### 9.4. Quick comparison

| Provider | Where is the proxy configured? | Key caveats |
| --- | --- | --- |
| **Azure SDK for Java** | Environment/Configuration or `ProxyOptions` on HTTP client | Proxy is bound per `HttpClient`; can use Netty, OkHttp, or JDK |
| **AWS SDK for Java 2.x** | Per-client `ProxyConfiguration`, JVM properties, or env | Behavior differs across Apache/URLConnection/Netty/CRT; CRT has its own TLS stack |
| **Google Cloud Java** | Java proxy properties; custom `HttpTransportFactory` or gRPC `ProxyDetector` | HTTP and gRPC require configuring their respective transports |
| **Spring RestClient/WebClient** | Request factory/connector and SSL bundle | Does not automatically configure proxies for standalone cloud SDKs |

## 10. Combining Proxy and SSL Bundle in One Client

A single client may simultaneously need:

- A TLS truststore to verify the server.
- A client keystore if using mTLS.
- Proxy routing and proxy authentication.
- Connect/read timeouts.
- A list of hosts allowed to bypass the proxy.

Not every builder API accepts both `SSLContext` and proxy settings in the same configuration block. When needed, build the specific HTTP client implementation and pass it into Spring or the SDK.

Example using JDK HttpClient for Spring `RestClient`, obtaining `SSLContext` from a bundle and setting a proxy:

~~~java
package com.example.checkout;

import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;
import javax.net.ssl.SSLContext;

import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class ProxiedPartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            SslBundles sslBundles) {
        SSLContext sslContext =
                sslBundles.getBundle("partner-api").createSslContext();

        HttpClient jdkClient = HttpClient.newBuilder()
                .sslContext(sslContext)
                .proxy(ProxySelector.of(
                        new InetSocketAddress("proxy.corp.example", 8080)))
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        return builder
                .baseUrl("https://payments.example.com")
                .requestFactory(new JdkClientHttpRequestFactory(jdkClient))
                .build();
    }
}
~~~

The example above uses an unauthenticated proxy to focus on combining an SSL context and a proxy. If the proxy requires authentication, the JDK `HttpClient` needs a suitable `Authenticator` and dedicated credential-handling policy; never manually inject proxy headers into requests intended for the origin.

For a cloud SDK, use the HTTP transport builder supported by that SDK. Do not treat a `RestClient` proxy config as proof that AWS/Azure/GCP clients are routing through the same proxy.

## 11. Verifying TLS and Proxy Connections

### 11.1. Inspecting server certificates with OpenSSL

From an environment with OpenSSL:

~~~bash
openssl s_client \
  -connect payments.example.com:443 \
  -servername payments.example.com \
  -showcerts \
  -verify_return_error
~~~

Options:

- `-connect`: host and port to connect to.
- `-servername`: sends the proper SNI hostname.
- `-showcerts`: prints the certificate chain sent by the server.
- `-verify_return_error`: causes the command to fail if chain verification encounters an error.

Testing through an HTTP CONNECT proxy:

~~~bash
openssl s_client \
  -proxy proxy.corp.example:8080 \
  -connect payments.example.com:443 \
  -servername payments.example.com \
  -showcerts \
  -verify_return_error
~~~

If TLS inspection is active, the leaf certificate may be signed by a corporate CA. Inspect the issuer and fingerprint, then verify that CA through a secure channel before importing it.

### 11.2. Inspecting certificate fields

After saving the leaf certificate to a file:

~~~bash
openssl x509 -in server-leaf.pem -noout -subject -issuer -dates -ext subjectAltName
~~~

Verify:

- Does the SAN contain the target hostname?
- Is the certificate currently valid?
- Is the issuer the expected CA?
- Does the certificate chain include the required intermediates?
- Are the Key Usage / Extended Key Usage appropriate for server/client purposes?

### 11.3. Inspecting a Java truststore

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

Check the alias, subject, issuer, serial number, and validity dates. If the certificate is missing from the truststore yet Java still succeeds, the client may be using the default truststore or a different transport. Verify which bundle the client is actually using.

### 11.4. Enabling TLS handshake debugging in Java

Run the JVM with:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar order-service.jar
~~~

The logs can show the protocol, certificates, and the exact failing handshake step. Only enable this in controlled dev/test environments because logs are verbose and can expose connection metadata. Place the JVM property **before** `-jar`; do not place it after the jar name as an application argument.

AWS CRT uses its own TLS stack, so the JSSE debug property may not display CRT handshakes. For other native/SDK clients, use the logging/diagnostics of that specific transport.

## 12. Testing TLS and Proxies

A test that merely calls a public endpoint successfully is not enough to prove all security checks. Separate tests for certificate trust, hostname verification, proxy routing, and cloud SDK transports.

### 12.1. Unit testing SSL bundle configuration

Verify that the bundle configuration loads and can create an `SSLContext`:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import javax.net.ssl.SSLContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PartnerSslBundleTest {

    @Autowired
    SslBundles sslBundles;

    @Test
    void loadsPartnerSslBundle() {
        SSLContext context =
                sslBundles.getBundle("partner-api").createSslContext();

        assertThat(context).isNotNull();
        assertThat(context.getProtocol()).isNotBlank();
    }
}
~~~

This test verifies that the configured material is read and can build an `SSLContext`. It does not prove that the real server certificate matches the hostname or that the proxy can establish a tunnel.

### 12.2. Integration testing with a TLS test server

Set up a local test server using certificates signed by a test CA:

| Test | Configuration | Expected result |
| --- | --- | --- |
| Valid CA, matching hostname | Truststore has test CA; URL matches SAN | TLS handshake succeeds |
| Untrusted CA | Truststore lacks server signing CA | Handshake fails |
| Hostname mismatches SAN | Connect using a host not in certificate | Hostname verification fails |
| Expired certificate | Use an expired test certificate | Handshake fails |
| mTLS missing client cert | Server requires client certificate | Handshake rejected |
| mTLS untrusted client cert | Client cert signed by different CA | Server rejects client |
| Proxy rejects CONNECT | Proxy returns 403/407 | Client reports proxy error, not origin certificate error |

Use dedicated test certificates and test CAs; never put test CAs into a production truststore.

### 12.3. Proxy integration testing

You can use a mock proxy or a containerized test proxy to verify:

1. The client sends CONNECT to the correct hostname/port.
2. Hosts in `NO_PROXY` go direct as configured.
3. Proxy authentication success and failure are properly distinguished.
4. The HTTPS origin certificate is still verified after the tunnel is established.
5. TLS inspection tests use a separate simulated CA and do not affect production truststores.

### 12.4. Testing each cloud SDK

| SDK | Recommended test |
| --- | --- |
| Azure SDK | Build an `HttpClient` with `ProxyOptions`, call a dev endpoint, verify traffic routes through the proxy |
| AWS SDK v2 | Configure `ProxyConfiguration` on the exact HTTP client implementation, test `NO_PROXY` |
| Google Cloud HTTP client | Use a custom `HttpTransportFactory` and test proxy authentication |
| Google Cloud gRPC | Configure `ProxyDetector` and verify the CONNECT tunnel |
| Spring RestClient/WebClient | Apply SSL bundle, test trust/hostname verification and request factory/connector |

Do not use production credentials in proxy tests. Record the host, port, transport type, and correlation ID, but never log proxy passwords, Authorization headers, or private keys.

## 13. Troubleshooting Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `PKIX path building failed` | Truststore missing root/intermediate CA or server omits chain | Inspect the chain and CA trust anchors |
| `unable to find valid certification path` | Client does not trust the CA that signed the server cert | Check the actual truststore used by the HTTP client |
| `No subject alternative DNS name matching` | URL hostname does not match SAN | Use the correct hostname or request a certificate with the right SAN |
| `certificate expired` / `not yet valid` | Certificate expired or clock skew | Check validity dates and synchronize clocks |
| `handshake_failure` | Incompatible protocol/cipher, mTLS, EKU, or certificate | Enable handshake debug in dev and check policies on both sides |
| `bad_certificate` | Peer rejected client certificate or chain | Check keystore, alias, chain, and the CA trusted by the server |
| HTTP 407 | Proxy requires authentication | Configure proxy credentials on the transport |
| HTTP 403 on CONNECT | Proxy disallows hostname/port | Check proxy policy, allowlist, and port |
| `Connection refused` to proxy | Wrong proxy host/port or unreachable | Check DNS, routing, firewall, and listener |
| Only Azure SDK uses proxy, AWS does not | SDKs read proxy settings via different mechanisms | Configure the proper client builder for each SDK |
| Spring RestClient succeeds, GCP gRPC fails | HTTP/gRPC use different transports | Configure `ProxyDetector` or the channel builder |
| TLS inspection causes certificate errors | JVM does not trust corporate CA or hostname/SAN mismatch | Verify inspection CA, import approved trust anchor |
| Updated truststore but app does not pick it up | Client created and cached old SSLContext | Recreate client/connection pool or perform a controlled restart |
| AWS CRT lacks JSSE debug output | CRT uses its own TLS stack | Use diagnostics for CRT/the corresponding transport |

**Do not fix errors by disabling certificate verification.** Approaches such as `TrustAllStrategy`, `NoopHostnameVerifier`, `InsecureTrustManagerFactory`, or configurations skipping hostname verification cause clients to accept forged servers and open the door to man-in-the-middle attacks.

## 14. Certificate and Trust Material Lifecycle

Certificates expire; internal CAs can be rotated; inspection proxies may change roots; mTLS clients require new certificates. Applications must have a process for updating truststores/keystores.

### 14.1. Overlapping CA rotation

When rotating a root CA:

1. Verify the new root CA and fingerprint through a trusted channel.
2. Release a truststore containing **both the old CA and the new CA**.
3. Deploy the new truststore to applications and recreate clients/`SSLContext` if needed.
4. Verify connectivity with the new certificate chain across all instances.
5. Switch servers/proxies to the new chain.
6. After all clients have updated, remove the old CA from the truststore on schedule.

Do not remove the old CA before active endpoints have switched certificates; otherwise, an outage may occur.

### 14.2. Reloading SSL bundles

Spring Boot supports `reload-on-update` for certain PEM-based SSL bundles. Current documentation lists compatible consumers including embedded Tomcat and Netty web servers. This does not guarantee that every `RestClient`, cloud SDK, HTTP pool, or gRPC channel updates automatically.

When using an SSL bundle with a file watcher, ensure you:

- Store certificates/keys at file paths permitted for watching.
- Update files atomically or ensure chain/key files remain synchronized.
- Only rely on reload for consumers that support it.
- For client SDKs, recreate the client/`SSLContext` if the transport does not support reload.
- Test both pre-rotation and post-rotation states.

### 14.3. Managing private keys

Private keys in keystores must be protected like secrets:

- Store them in Key Vault/HSM or an appropriate secret manager when architecture permits.
- Restrict permissions on mounted files and container access.
- Never log passwords, PEM private keys, or keystore contents.
- Restrict key export if HSM/non-exportable keys can be used.
- Track certificate expiration dates and the owner responsible for renewal.

## 15. Configuration Decisions by Scenario

| Scenario | Trust material | Proxy | How to apply |
| --- | --- | --- | --- |
| Calling public cloud APIs over HTTPS | JVM public CA trust or default SSL bundle | None | Default HTTP clients already support TLS |
| Internal API using corporate CA | Truststore with verified corporate root/intermediate | Possibly via proxy | Dedicated SSL bundle for internal APIs |
| TLS inspection proxy | Truststore with approved corporate inspection CA | Corporate proxy | Keep hostname verification and control trust scope |
| Partner requiring mTLS | Keystore with client cert/private key + truststore with server CA | Depends on network | mTLS SSL bundle and supporting client transport |
| Azure SDK through proxy | Trust material for Azure endpoints and proxy if needed | `ProxyOptions` or Configuration | Configure Azure HTTP client separately |
| AWS SDK v2 through proxy | Trust material per HTTP client/TLS stack | `ProxyConfiguration` | Choose the right Apache/Netty/CRT client |
| Google Cloud REST/gRPC | Trust material per transport | Java proxy properties, custom HTTP factory, or gRPC ProxyDetector | Configure HTTP and gRPC separately |

## 16. Comprehensive Hands-On Exercise

`shipping-service` calls a partner API across a corporate network:

- The API `https://api.shipping.example` uses a certificate issued by a partner CA.
- The proxy `proxy.corp.example:8080` requires authentication.
- The partner requires mTLS with a dedicated client certificate.
- The application simultaneously calls Azure Key Vault and Google Cloud Storage.
- The client certificate expires in 45 days.

**Tasks:**

1. Create a truststore containing the CA that signs the partner's server certificate.
2. Create a keystore containing the client certificate and private key per CA procedure.
3. Configure an SSL bundle named `shipping-mtls`.
4. Apply the bundle to `RestClient` and configure the proxy in the appropriate request factory.
5. Configure proxies separately for the Azure SDK and Google Cloud HTTP/gRPC transports.
6. Write integration tests for untrusted CA, hostname mismatch, missing client certificate, and proxy 407.
7. Plan an overlapping certificate rotation, generate a new client certificate, and verify before revoking the old certificate.

**Self-assessment questions:**

- Why are a truststore and a keystore not interchangeable?
- Should a valid certificate chain whose SAN does not include the hostname be accepted?
- Does a standard CONNECT proxy decrypt HTTPS payloads?
- How must a TLS inspection proxy be trusted?
- Why does a Spring Boot SSL bundle not automatically apply to AWS CRT or Google Cloud gRPC?
- When updating a truststore file, why might a running HTTP client still use old trust material?
- Why should a new CA be deployed before servers switch to a new certificate chain?

**Guided answers:** a truststore verifies the peer while a keystore proves the application's identity; the hostname must match the SAN; CONNECT creates a tunnel whereas TLS inspection can decrypt and re-encrypt; SDKs use separate transports; clients typically retain `SSLContext` at initialization; CA overlap avoids trust gaps.

## 17. Official References

- [Spring Boot – SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): JKS/PKCS12, PEM, truststore, keystore, SSLContext, and reload.
- [Spring Boot 3.5 – RestClient SSL API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html): applying SSL bundles to RestClient.
- [Spring Boot – Calling REST services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClient/WebClient and SSL bundle support.
- [Oracle – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): truststores, keystores, and TLS properties.
- [Oracle – keytool](https://docs.oracle.com/en/java/javase/23/docs/specs/man/keytool.html): importing certificates, checking fingerprints, and managing keystores.
- [Microsoft Learn – Configure proxies in Azure SDK for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/proxying): environment, Configuration, and ProxyOptions.
- [Microsoft Learn – HTTP clients and pipelines in Azure SDK for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline): Netty, OkHttp, JDK HTTP client, and transport.
- [AWS – Working with TLS in SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/security-java-tls.html): TLS versions, JSSE, and AWS CRT.
- [AWS – Configure HTTP proxies in SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-config-proxy-support.html): ProxyConfiguration, system properties, environment, and non-proxy hosts.
- [Google Cloud – Configure a proxy for Java](https://docs.cloud.google.com/java/docs/configuring-a-proxy?hl=en): HTTPS, HTTP transport, and gRPC ProxyDetector.

**Remember:** TLS is only secure when the client properly verifies the certificate chain and hostname; a proxy is only safe when trust boundaries are clearly understood; an SSL bundle only takes effect on the clients/transports where it is applied. For Spring Cloud applications integrating multiple providers, test each HTTP/gRPC transport and plan trust material rotation before certificates expire.
