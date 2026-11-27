# TLS, mTLS, Certificates, and Truststores When Connecting to the Registry

Spring Cloud Service Discovery typically needs to connect to a registry system such as Eureka, Consul, or ZooKeeper. This connection carries service registration details, instance lists, metadata, and sometimes authentication credentials. When traversing untrusted networks, the communication channel must be protected with TLS to prevent eavesdropping, data tampering, and server spoofing.

One-way TLS authenticates the server to the client. Mutual TLS (mTLS) authenticates both the server and the client using digital certificates. To establish a connection, the application must trust the registry's certificate via a truststore; when the registry requires a client certificate, the application also needs a keystore containing its own private key and certificate chain.

This article explains how these components work together, how to configure secure connections to Eureka, Consul, and ZooKeeper, and procedures for testing, certificate rotation, and troubleshooting handshake errors. The examples use Java JSSE and common Spring Cloud configuration; property names or SSL context setup may vary by version and the HTTP transport of each starter.

## 1. TLS Protects the Connection to the Registry

TLS (Transport Layer Security) establishes an encrypted channel between two endpoints. In service discovery, one end is typically the Spring Boot application and the other is the Eureka Server, Consul agent, or ZooKeeper server.

TLS provides three essential properties:

- **Confidentiality:** intermediaries cannot read request/response payloads without the appropriate keys.
- **Data integrity:** tampering with data in transit is detected.
- **Peer authentication:** the client verifies the server's identity; with mTLS, the server also verifies the client's identity.

When a client calls the registry over plain HTTP, registration data, service IDs, instance addresses, and ACL tokens can be observed or modified by any party able to sniff or inject traffic on the wire. HTTPS protects that channel, but it does not determine which services a client is allowed to register or read. Access control still requires ACLs, authentication, and authorization at the application layer.

### One-Way TLS and mTLS

| Characteristic | One-Way TLS | Mutual TLS |
|---|---|---|
| Server sends certificate | Yes | Yes |
| Client verifies server certificate | Yes | Yes |
| Client sends certificate | Optional | Yes |
| Server verifies client certificate | No | Yes |
| Goal | Client knows it is connecting to the right registry | Both sides mutually authenticate identity at the TLS layer |

In one-way TLS, the Spring Boot application needs to trust the CA that signed the registry's certificate. In mTLS, the registry also needs to trust the CA that signed the client's certificate and be configured to require client certificates.

~~~mermaid
sequenceDiagram
    participant C as Spring Cloud client
    participant R as Registry
    C->>R: ClientHello
    R-->>C: Server certificate and handshake data
    C->>C: Verify chain, validity, and hostname
    opt mTLS
        R-->>C: CertificateRequest
        C->>C: Select client certificate and private key
        C->>R: Client certificate and proof of private key
        R->>R: Verify client certificate
    end
    C->>R: Complete TLS handshake
    C->>R: HTTP request to register or look up
    R-->>C: HTTP response
~~~

TLS only establishes the channel and authenticates the peer by certificate. The registry still needs to check the client's permissions after the handshake completes.

## 2. Certificates, CAs, Chains, and SANs

An X.509 certificate is a digital document binding an identity to a public key. A certificate typically contains a subject, issuer, validity period, public key, extensions, and the CA's signature.

Roles:

- **Root CA:** the root authority trusted directly by the client.
- **Intermediate CA:** an intermediate authority used to sign server or client certificates.
- **Server certificate:** the certificate presented by the registry when a client connects.
- **Client certificate:** the certificate presented by the application when the registry requires mTLS.
- **Private key:** the secret key corresponding to the public key in the certificate; must be strictly protected.

The server usually sends its certificate along with any intermediate certificates needed for the client to build a chain to a trusted CA. The Root CA is typically pre-installed in the client's truststore and does not need to be sent during the handshake.

### SAN and Hostname Verification

The client must verify that the hostname in the URL matches a Subject Alternative Name (SAN) in the server certificate. For example, if the registry is configured as https://eureka.internal:8761, the certificate needs a DNS SAN matching eureka.internal.

If the client connects by IP, the certificate needs a matching IP SAN. Placing the hostname solely in the Common Name is no longer a reliable substitute for SANs in modern TLS clients.

Never disable hostname verification to fix certificate mismatch errors. Fix the DNS, URL, or issue a certificate with the right SAN. Skipping hostname verification allows a client to accept a rogue server even if the certificate chain is valid.

### EKU and Certificate Usage Purpose

Certificates can restrict allowed usage via Extended Key Usage (EKU):

- A server certificate requires the **serverAuth** purpose.
- A client certificate used for mTLS requires the **clientAuth** purpose.

An expired certificate, a certificate not yet valid, a missing intermediate CA, or an incompatible EKU can all cause the handshake to fail. System clocks on both client and server must also be synchronized for accurate validity checks.

## 3. How Do Truststores and Keystores Differ?

These two concepts are frequently confused:

| Component | Primary Contents | Where Used |
|---|---|---|
| Truststore | CA certificates or trusted certificates | Client verifies server; server verifies client in mTLS |
| Keystore | Private key along with corresponding certificate chain | Client presents client certificate; server presents server certificate |

A truststore answers the question: "Which CA's signed certificates do I trust?" A keystore answers the question: "Which private key do I own and which identity can I prove?"

Example:

~~~text
Spring Boot client
  registry-truststore.p12
    - registry-root-ca
    - registry-intermediate-ca

  discovery-client-keystore.p12 (only needed for mTLS)
    - client private key
    - client certificate
    - intermediate certificate chain

Registry server
  registry-server-keystore.p12
    - server private key
    - server certificate
    - intermediate certificate chain

  client-ca-truststore.p12 (when mTLS is required)
    - CA signing client certificates
~~~

A truststore can be JKS or PKCS12. PKCS12 is a common format that can store both certificates and private keys; however, the logical role of the file depends on its contents and how it is configured, not merely its file extension.

Never place private keys or keystore passwords in Git, Docker images, or logs. Use a secret manager, protected Kubernetes Secrets, file mounts with restricted permissions, or an equivalent key management mechanism.

## 4. Preparing a Truststore for a Java Application

If the registry uses a certificate issued by an internal CA, the JVM must trust that CA. Typically, place the required root CA and intermediate CAs into the client's truststore. Avoid importing only the leaf certificate if the organization re-issues certificates regularly; trusting the CA allows replacing server certificates without updating every client, provided the chain and CA policy remain valid.

Example of creating a PKCS12 truststore from a CA file:

~~~bash
keytool -importcert -alias internal-registry-root -file registry-root-ca.crt -keystore registry-truststore.p12 -storetype PKCS12
~~~

Inspect truststore contents:

~~~bash
keytool -list -v -keystore registry-truststore.p12 -storetype PKCS12
~~~

The import command prompts for a password and trust confirmation. Before accepting a certificate, verify the CA fingerprint through an independent trusted channel. Never accept a certificate merely because it appeared in a failing connection.

### Specifying the Truststore for the JVM

For HTTP clients using the default JSSE SSLContext, you can configure the JVM:

~~~bash
java -Djavax.net.ssl.trustStore=/run/secrets/registry-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=REPLACE_WITH_SECRET -jar application.jar
~~~

These system properties must be set at JVM startup before the TLS context is initialized. The password in the example is just a placeholder; in actual deployments, obtain it from a secret store or platform secret injection mechanism, avoiding exposure in process listings or logs.

When setting javax.net.ssl.trustStore, the JVM may use only the trust anchors in that specified file instead of the default truststore. If the application also calls public HTTPS endpoints, ensure the truststore also contains needed public CAs or use a dedicated SSL context for registry connections.

Some HTTP clients or starters construct their own SSLContext. In such cases, JVM-wide system properties may not take effect as expected. Check the HTTP transport in use and configure trust material via the extension point supported by that version.

## 5. Configuring a Keystore for Client-Side mTLS

When the registry requires a client certificate, the application needs its own private key and certificate chain. Example JVM configuration for JSSE:

~~~bash
java -Djavax.net.ssl.trustStore=/run/secrets/registry-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=TRUSTSTORE_SECRET -Djavax.net.ssl.keyStore=/run/secrets/discovery-client-keystore.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -Djavax.net.ssl.keyStorePassword=KEYSTORE_SECRET -jar application.jar
~~~

In this configuration:

- The truststore verifies the registry's certificate.
- The keystore supplies the client certificate and private key when requested by the server.
- The registry must trust the CA that issued the client certificate.
- The client certificate must be valid, have the proper EKU, and be bound to an authorized identity.

These JSSE properties apply JVM-wide when the HTTP transport uses the default SSLContext. They can affect all outbound TLS connections from the application. If different registries or services require distinct identities, use a separate SSL context/HTTP client per target when supported by the integration library, rather than sending the same client certificate to every endpoint.

## 6. Outbound TLS Differs from Spring Boot Inbound HTTPS

A Spring Boot application can simultaneously:

- Expose HTTPS for consumers calling the service's API.
- Connect via HTTPS to Eureka Server or a Consul agent.

These are two independent connection directions.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: /run/secrets/inventory-server-keystore.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_SECRET
~~~

The server.ssl configuration above controls inbound HTTPS on the embedded web server. It does not automatically configure the truststore or client certificate for outbound connections from Eureka/Consul clients.

Similarly, configuring the JVM truststore to call the registry does not automatically enable HTTPS for inventory-service's API. If both are required, configure server SSL and the outbound registry client separately.

## 7. Connecting Eureka Client Over HTTPS

Eureka Client uses the registry URL declared in configuration. Example:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal:8761/eureka/
~~~

The URL must match the hostname, port, and context path of Eureka Server. The server certificate must have a SAN matching eureka.internal, and the chain must be trusted by the JVM or HTTP client.

If Eureka Server is protected by one-way TLS, the client needs a truststore trusting the server's CA. If the server requires mTLS, the client also needs a keystore holding the client certificate. How the SSL context is passed into Eureka's HTTP transport depends on the Spring Cloud Netflix version and configured transport (such as Jersey or another HTTP client). Do not assume the application's server.ssl automatically applies to outbound Eureka connections.

If Eureka Server sits behind a reverse proxy or ingress, the proxy may terminate TLS. In that case, ensure:

- Clients connect to the proxy's hostname and certificate.
- The proxy authenticates or forwards the client certificate if mTLS is used.
- The leg from the proxy to Eureka Server is protected according to internal requirements.
- Basic authentication or Eureka authorization mechanisms are still configured separately if needed.

TLS/mTLS verifies the channel and peer; it does not automatically grant permission to register or read every service.

## 8. Connecting Spring Cloud Consul Discovery Over HTTPS

Spring Cloud Consul Discovery typically communicates with the Consul agent over its HTTP API. When the agent enables HTTPS, configure the appropriate scheme:

~~~yaml
spring:
  cloud:
    consul:
      host: consul-agent.internal
      port: 8501
      scheme: https
      discovery:
        enabled: true
        register: true
        service-name: inventory-service
~~~

Port 8501 is commonly Consul's default HTTPS API port, though it can be changed in agent configuration. Verify the actual listener instead of relying solely on the default port number.

The client must trust the CA that issued the agent's certificate. With an HTTP transport using default JSSE, the JVM truststore can provide the CA. If the agent requires mTLS, configure the client identity for the HTTP client used by Spring Cloud Consul. Detailed configuration depends on the Spring Cloud Consul version and Consul client transport; check the corresponding property reference or extension point.

If Consul uses ACLs, the token is an API-level authentication/authorization layer independent of TLS. Issue least-privilege tokens for discovery and registration operations. Never embed tokens in URLs, logs, or service metadata.

## 9. Connecting to ZooKeeper with TLS

Spring Cloud Zookeeper uses Apache Curator and the ZooKeeper client to communicate with the ensemble. ZooKeeper can configure a secure client port for TLS client connections. This is configured on the ZooKeeper server and client transport; it is not enabled merely by setting server.ssl on the Spring Boot application.

On the server side, you need to:

- Configure the secure client port and server certificate/private key.
- Configure the truststore or trust material to verify client certificates if using mTLS.
- Keep internal quorum/election ports separate from the secure client port.

On the Spring Cloud client side, you need to:

- Connect to the ensemble's secure client port.
- Enable ZooKeeper client secure mode according to your version.
- Supply the truststore to verify the server certificate.
- Supply the client keystore if the server requires mTLS.

ZooKeeper/Curator have version-specific SSL properties and SSL context creation mechanisms. Property names, truststore formats, and how Spring Cloud passes configuration down to Curator can differ. Cross-check documentation for the exact versions of ZooKeeper, Curator, and Spring Cloud Zookeeper; never copy Eureka or Consul properties over to ZooKeeper.

ZooKeeper sessions, ephemeral znodes, and watches continue operating over the secure connection. TLS protects the transport, while session timeouts govern session and ephemeral node lifecycles.

## 10. Configuring mTLS on the Registry Server Side

Having a keystore on the client is only half of mTLS configuration. The registry server must be configured to require and verify client certificates.

Conceptually, the server needs:

1. A server keystore containing the registry's private key and certificate chain.
2. A truststore containing CAs authorized to issue client certificates.
3. Client authentication mode requiring certificates if mandatory by policy.
4. Authorization mapping certificate identities to appropriate API permissions.

For a Spring Boot server using an embedded server, server-side mTLS configuration may look like:

~~~yaml
server:
  port: 8761
  ssl:
    enabled: true
    key-store: /run/secrets/registry-server-keystore.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_SECRET
    trust-store: /run/secrets/registry-client-ca-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: CLIENT_CA_SECRET
    client-auth: need
~~~

This example illustrates a Spring Boot server requiring client certificates. Eureka Server can run on an embedded server or behind a proxy; if TLS terminates at a proxy, mTLS must be configured on the proxy and client identity forwarded securely per architecture. Consul and ZooKeeper have their own server configurations and do not directly use a Spring Boot application's server.ssl YAML.

When mTLS is terminated at a proxy, never trust a client-certificate header sent by the client itself. The proxy must strip externally supplied headers, verify the certificate itself, and inject identity information over a protected internal channel.

## 11. Certificate Management and Key Rotation

Certificates expire. If unmonitored, the registry or clients can suddenly lose connectivity when a certificate expires.

A sound management process includes:

- Tracking expiration dates of server and client certificates.
- Renewing well before expiration to leave time for testing and rollout.
- Using consistent CAs and chains across environments.
- Rotating certificates in stages: add the new CA to truststores first, deploy new certificates, verify all clients, and only then remove the old CA when no certificates depend on it.
- Protecting private keys and restricting file read permissions.
- Having a certificate revocation process when a private key is compromised.
- Synchronizing system clocks to avoid not-yet-valid or expired errors.

If truststores or keystores are mounted from a secret volume, updating the file on disk does not guarantee a running JVM or HTTP client will automatically reload its SSL context. Many clients load key material only at startup. Verify dynamic reload support of your transport; if unavailable, plan a safe restart/rollout after updating secrets.

Never rotate CAs, server certificates, and client certificates simultaneously across the whole system without a compatibility window. An overlap procedure ensures both old and new clients can verify chains during transition.

## 12. Verifying Certificates and TLS Connections

### Checking the Server Certificate with OpenSSL

~~~bash
openssl s_client -connect eureka.internal:8761 -servername eureka.internal -showcerts -verify_return_error
~~~

This command shows the certificate chain and verification errors from an environment with OpenSSL. To verify against an internal CA, specify the CA file:

~~~bash
openssl s_client -connect eureka.internal:8761 -servername eureka.internal -CAfile registry-root-ca.crt -verify_return_error
~~~

When testing mTLS, the client may need to supply a certificate and private key:

~~~bash
openssl s_client -connect consul-agent.internal:8501 -servername consul-agent.internal -CAfile registry-root-ca.crt -cert discovery-client.crt -key discovery-client.key -verify_return_error
~~~

Never use production private keys on an unprotected test machine. Run these commands only from authorized environments and with test certificates whenever possible.

### Inspecting Truststores and Keystores

~~~bash
keytool -list -v -keystore /run/secrets/registry-truststore.p12 -storetype PKCS12
keytool -list -v -keystore /run/secrets/discovery-client-keystore.p12 -storetype PKCS12
~~~

Verify:

- Whether the required alias exists.
- Whether the truststore contains the right CA.
- Whether the keystore has a PrivateKeyEntry and complete certificate chain.
- Whether certificates are still valid and have the right SAN/EKU.
- Whether passwords and file read permissions are correct.

### Enabling TLS Logs During Diagnostics

In test environments, you can enable JSSE debug logging:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar application.jar
~~~

TLS logs can contain hostnames, certificate metadata, and sensitive connection details. Enable only briefly, store with access controls, and turn off after diagnostics.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| PKIX path building failed | Client cannot build chain to a trusted CA | Check truststore and intermediate certificates |
| No subject alternative DNS name matching | URL hostname does not match SAN | Fix DNS/URL or reissue certificate with correct SAN |
| certificate_expired | Certificate has expired | Renew and deploy new certificate |
| bad_certificate | Invalid client certificate or server does not trust client CA | Check client keystore, chain, EKU, and server-side truststore |
| handshake_failure | Incompatible TLS version, cipher suite, certificate, or client-auth | Check logs on both sides and compare TLS policies |
| UnrecoverableKeyException | Cannot read private key or wrong key password | Check keystore type, alias, and passwords |
| HTTPS connects successfully but API returns 403 | TLS succeeded but ACL/authorization rejected request | Check Consul token, Eureka security, or registry permissions |
| JVM trusts certificate but HTTP client still fails | Transport uses a separate SSLContext or different truststore | Check client implementation and dedicated SSL configuration |
| Still using old certificate after updating secret | SSLContext cached key material | Verify reload support or perform safe rollout/restart |

Never resolve errors by disabling certificate verification, skipping hostname verification, or trusting all certificates. Those workarounds strip away the very protection TLS was configured to provide.

## 14. Distinguishing Security Layers

A service discovery system can have multiple distinct TLS channels:

| Channel | Purpose | Where Configuration Lives |
|---|---|---|
| Service client → Registry | Protect registration and lookup | Registry client HTTP/TLS transport |
| Consumer → Provider | Protect business requests | Service provider and consumer HTTPS/mTLS |
| Registry node → Registry node | Protect internal cluster communication | Corresponding cluster/server configuration |
| Client identity → API authorization | Determine what operations a client is allowed to perform | ACLs, authentication, and authorization |

For instance, enabling HTTPS on inventory-service does not mean the connection from inventory-service to Eureka is encrypted. Enabling HTTPS on Eureka does not automatically encrypt traffic between Eureka peers or between consumers and providers. Each channel must be configured and verified independently.

## 15. Secure Deployment Principles

- Use TLS for all registry connections traversing untrusted networks.
- Use mTLS when TLS-layer client authentication is needed and fully supported by both the registry and transport.
- Install required CAs in the truststore; keep private keys in a protected keystore.
- Verify certificate chains, SANs, EKUs, validity periods, and hostname verification.
- Do not confuse inbound HTTPS server.ssl with the registry client's outbound SSL context.
- Configure specifically for Eureka, Consul, or ZooKeeper; do not assume all starters share the same HTTP transport or SSL properties.
- Keep ACLs/tokens and authorization even after enabling TLS/mTLS.
- Never place secrets in repositories, images, URLs, or logs.
- Monitor certificate expiration and rotate CAs/certificates in phases with an overlap period.
- Verify connectivity from the actual application runtime/container/Pod using the exact HTTP client utilized by the starter.

TLS protects the connection channel to the registry; mTLS adds client certificate authentication. The truststore defines which CAs the application trusts, while the keystore holds the application's private key and identity certificate. When certificate chains, hostnames, API permissions, and key rotation lifecycles are configured properly, Spring Cloud Service Discovery can register and look up services securely while maintaining availability when certificates are replaced.
