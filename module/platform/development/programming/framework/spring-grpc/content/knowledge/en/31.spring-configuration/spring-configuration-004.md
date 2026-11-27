# Configuring TLS for the Server

gRPC runs over HTTP/2 and typically requires **TLS** to encrypt data in transit, authenticate the server's identity, and protect metadata/requests from being read or modified on the network. In **Spring gRPC**, TLS configuration for the server consists of the server certificate, corresponding private key, TLS version policy, and how the `SslContext` is integrated into the Spring-managed gRPC server.

TLS protects the transport channel; it does not replace user authentication, authorization, or business-layer permission checks. A server with a valid certificate still must verify credentials, tenant, and access permissions per RPC.

## 1. Where is TLS established in gRPC?

Before exchanging gRPC messages, the client and server perform a TLS handshake. The server presents its certificate chain for the client to verify its identity; both sides negotiate the TLS version, cipher suite, and session keys. Next, HTTP/2 is negotiated via **ALPN** with the `h2` protocol, and only then does gRPC transmit requests/responses.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant S as Spring gRPC server
    C->>S: TCP connection
    C->>S: TLS ClientHello
    S-->>C: Certificate chain + TLS parameters
    C->>C: Validate certificate and hostname
    C->>S: TLS handshake completed, ALPN h2
    C->>S: HTTP/2 + gRPC request
    S-->>C: HTTP/2 + gRPC response
~~~

If the certificate is not trusted by the client, is expired, or does not match the hostname, the handshake fails before the service implementation receives any RPC. If ALPN fails to select `h2`, the connection can fail even when the certificate is valid.

## 2. Preparing the certificate and private key

The server needs at least:

- **Certificate chain**: the server's certificate and any intermediate certificates required for the client to build a trust chain.
- **Private key**: the private key matching the public key in the server certificate.
- **CA trust**: the client needs to trust the CA that signed the server certificate. With mutual TLS, the server also needs CA trust to verify client certificates.

The server certificate must have a Subject Alternative Name (SAN) matching the DNS name clients use to connect, such as `grpc.internal.example.com`. Clients verify the hostname against the SAN; do not disable hostname verification to bypass certificate errors.

Never commit private keys to Git, package them into a source JAR, or write them directly in `application.yml`. Store keys in a secret manager, Kubernetes Secret, or protected secret mount; restrict file read permissions and avoid logging key contents.

## 3. Declaring TLS paths in Spring configuration

You can manage certificate paths via your application's own configuration properties:

~~~yaml
app:
  grpc:
    tls:
      certificate-chain: /run/secrets/grpc/server-chain.pem
      private-key: /run/secrets/grpc/server-key.pem
      require-client-certificate: false
      client-ca: /run/secrets/grpc/client-ca.pem
~~~

This is an application-defined configuration namespace, not a default property set of every Spring gRPC starter. Example record:

~~~java
@ConfigurationProperties(prefix = "app.grpc.tls")
public record GrpcServerTlsProperties(
    Path certificateChain,
    Path privateKey,
    boolean requireClientCertificate,
    Path clientCa
) {}
~~~

Register the properties using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(GrpcServerTlsProperties.class)`. In production environments, validate on application startup that the files exist, are readable, and have a valid format so configuration errors surface early.

## 4. Creating an SslContext for the gRPC server

With Netty transport, use `GrpcSslContexts` to create an `SslContext` configured appropriately for gRPC/HTTP/2:

~~~java
import io.grpc.netty.GrpcSslContexts;
import io.netty.handler.ssl.ClientAuth;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;

@Configuration
@EnableConfigurationProperties(GrpcServerTlsProperties.class)
public class GrpcTlsConfiguration {

    @Bean
    SslContext grpcServerSslContext(
            GrpcServerTlsProperties properties) throws SSLException {

        SslContextBuilder builder = GrpcSslContexts.forServer(
            properties.certificateChain().toFile(),
            properties.privateKey().toFile());

        builder.protocols("TLSv1.3", "TLSv1.2");

        if (properties.requireClientCertificate()) {
            if (properties.clientCa() == null) {
                throw new IllegalStateException(
                    "client-ca is required when mTLS is enabled");
            }
            builder.trustManager(properties.clientCa().toFile());
            builder.clientAuth(ClientAuth.REQUIRE);
        } else {
            builder.clientAuth(ClientAuth.NONE);
        }

        return builder.build();
    }
}
~~~

This example uses the unshaded Netty package (`grpc-netty`). If your project uses `grpc-netty-shaded`, Netty imports must come from the corresponding shaded package; never mix the two sets of classes. Choose a transport version compatible with the gRPC Java version in use.

`GrpcSslContexts.forServer(...)` sets up the ALPN configuration required for gRPC over Netty. The example allows only TLS 1.3 and TLS 1.2; actual policy should follow your environment's security standards. Do not downgrade to older TLS versions to work around incompatible clients.

## 5. Attaching SslContext to the server

With a directly created gRPC Java server:

~~~java
Server server = NettyServerBuilder.forPort(9090)
    .sslContext(grpcServerSslContext)
    .addService(orderService)
    .build()
    .start();
~~~

`NettyServerBuilder.sslContext(...)` enables TLS on the transport. When using a Spring starter that creates the server automatically, pass the `SslContext` bean into the server builder extension point provided by your exact starter/version. Do not create a second server just to enable TLS if the starter already manages the server lifecycle.

If managing the server yourself with Spring, the bean can declare start/shutdown lifecycle hooks according to your application's mechanism. During shutdown, stop accepting new calls and allow in-flight requests to finish within the grace period before closing executors and related resources.

## 6. One-way TLS and mutual TLS

### One-way TLS (server authentication)

In the basic configuration, the server presents its certificate; the client verifies the certificate and hostname. The server does not require the client to present a certificate during the TLS handshake. The client can still authenticate at the gRPC layer using a bearer token, OAuth2, or appropriate credentials.

This is a common choice when client identity is managed via tokens/interceptors and the server needs to protect the transport channel.

### Mutual TLS (mTLS)

With mTLS, the server requires the client to present a certificate. The server verifies that certificate against the configured CA trust. The code above enables mTLS when `require-client-certificate` is `true`:

~~~yaml
app:
  grpc:
    tls:
      certificate-chain: /run/secrets/grpc/server-chain.pem
      private-key: /run/secrets/grpc/server-key.pem
      require-client-certificate: true
      client-ca: /run/secrets/grpc/client-ca.pem
~~~

`ClientAuth.REQUIRE` forces the client to provide a certificate accepted by the trust manager. A valid certificate establishes machine/client identity at the transport layer; the application still must map that identity to a service account, workload identity, or authorization policy. Do not grant business permissions by default merely because the TLS handshake succeeded.

## 7. Client configuration must match the server

The client needs to trust the CA that issued the server certificate and connect using a hostname present in the SAN. In internal environments, you can use an enterprise CA or private CA distributed securely to clients.

With mTLS, the client also needs its own certificate chain and private key to present to the server. Never share the server's private key with clients. Manage client certificate lifecycles per workload identity and revoke them when credentials are no longer valid.

If TLS is terminated at a gateway/proxy rather than the Spring gRPC server, the proxy-to-backend hop still needs protection according to the trust boundary. Internal TLS or mTLS can be used; avoid sending plaintext over untrusted networks just because the client-facing hop is encrypted.

## 8. Certificate rotation and deployment configuration

Certificates have expiration dates. Operational procedures need to:

1. Issue a new certificate with the right SAN and full chain.
2. Distribute the certificate/private key via secret management.
3. Verify file permissions, PEM format, and that the certificate/key pair match.
4. Update the `SslContext` or restart/reload the server according to the capabilities of your integration.
5. Verify that client handshakes succeed with the new certificate.
6. Revoke the old certificate following CA procedures once the transition period ends.

Replacing files on disk does not mean a previously created `SslContext` automatically reloads the new certificate. If the application does not support dynamic TLS context reloading, perform a controlled rolling restart. During a CA transition, you may need to trust both the old and new CAs simultaneously to avoid disrupting clients.

## 9. Testing TLS configuration

You cannot verify a TLS handshake using only an in-process transport because that transport does not establish a real TLS socket. Integration tests with a Netty server and client over loopback or an equivalent test environment are required.

Cases to test:

- Client trusts the right CA and hostname matches SAN: handshake succeeds, RPC works.
- Client does not trust the CA: handshake fails.
- Hostname does not match SAN or certificate is expired: client rejects the connection.
- Server requires mTLS, but client does not present a certificate: handshake fails.
- Client presents a certificate signed by an untrusted CA: server rejects it.
- Certificate/key mismatch or unreadable file: server fails to start.
- HTTP/2 ALPN selects `h2` and gRPC trailers/status continue to work.

Also test a plaintext connection against the TLS port to ensure the server does not accidentally accept unencrypted connections. Never use trust-all mode in tests because it hides certificate verification errors.

## 10. Diagnosing handshake errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `UNAVAILABLE` with handshake error | TLS negotiation failed | Inspect cause chain, protocol, and cipher compatibility |
| Certificate unknown/untrusted | Client lacks CA or server chain is incomplete | Check trust store and intermediate certificates |
| Hostname verification failed | SAN does not match target | Connect using the right DNS name or reissue the certificate |
| Bad certificate on server | Client certificate is untrusted or lacks appropriate EKU | Check client CA, certificate usage, and mTLS policy |
| ALPN fails to select `h2` | Proxy/transport does not negotiate HTTP/2 | Check ALPN and HTTP/2 configuration on each hop |
| Server fails to start | Wrong path, file permissions, invalid PEM, or key mismatch | Validate secret mount and certificate/key pair |

Never log private keys, tokens, or full certificate material in application logs. You can log fingerprints, subject, issuer, expiry, and handshake failure category to aid operations.

## 11. Key takeaways and self-check

**Configuring TLS for the server** requires a certificate chain, matching private key, and an `SslContext` attached to the gRPC server transport. With Netty, `GrpcSslContexts` helps configure ALPN for HTTP/2; mTLS adds client CA trust and `ClientAuth.REQUIRE`. In Spring, manage paths via configuration properties/secret mounts and integrate `SslContext` into the server owned by the starter.

Self-check:

1. Why must the server certificate's SAN match the hostname used by the client?
2. How do `grpc-timeout` and TLS solve two different problems?
3. How does mTLS differ from one-way TLS regarding client-side certificate requirements?
4. Why does replacing a certificate file not guarantee that the running `SslContext` has been updated?
5. What needs to be tested beyond confirming that the server starts successfully?

Properly configured and operated TLS helps Spring gRPC encrypt the transport channel, authenticate server/client identities per policy, and maintain secure HTTP/2 connections across deployment environments.
