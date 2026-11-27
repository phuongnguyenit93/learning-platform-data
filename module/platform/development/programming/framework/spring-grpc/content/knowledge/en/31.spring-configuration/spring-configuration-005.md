# Configuring TLS for the Client in Spring gRPC

In the **SPRING_GRPC** ecosystem, clients often call services over an internal network, service mesh, or load balancer. TLS protects data in transit and verifies the server's identity before the client sends requests. When mutual authentication is required, the client also presents its own workload certificate using mutual TLS (mTLS).

Spring Boot integrates gRPC client TLS configuration with **SSL bundles** and per-channel properties. This allows the application to choose one-way TLS or mTLS, manage truststores/keystores per environment, and create stubs from configured channels. This lesson focuses on client-side TLS configuration, certificate/hostname verification, and testing real connections.

## 1. What must the client verify?

In one-way TLS, the server presents a certificate; the client must verify:

- The certificate is valid at the time of connection.
- The certificate chain leads to a CA trusted by the client.
- The hostname in the address the client connects to matches a Subject Alternative Name (SAN) in the certificate.
- The certificate has the appropriate key usage for server authentication.
- The TLS handshake negotiates HTTP/2 (ALPN `h2`) so gRPC can operate.

In mTLS, the server also requires the client to present a certificate. The client then additionally needs the workload's private key and certificate; the server verifies the client's chain against the server-side truststore.

| Mechanism | Certificate presented | Verifying party |
| --- | --- | --- |
| One-way TLS | Server certificate | Client verifies server |
| mTLS | Server and client certificates | Both client and server verify peer |

TLS verifies identity at the connection layer. It does not automatically decide which RPCs a service account is allowed to call; method-level authorization may still require tokens, scopes, or application-layer policies.

## 2. Configuring one-way TLS with channel properties

For servers using a certificate issued by a public CA or a CA already present in the JVM truststore, you can enable TLS directly on the channel:

```yaml
spring:
  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            enabled: true
```

Where:

- `inventory` is the logical channel name used by the application when creating stubs.
- `target` specifies the gRPC endpoint. The `static://` scheme indicates a static target.
- `ssl.enabled: true` enables TLS for the channel.

Equivalent example in `application.properties`:

```properties
spring.grpc.client.channel.inventory.target=static://inventory.internal.example:9090
spring.grpc.client.channel.inventory.ssl.enabled=true
```

If the server certificate is signed by a CA trusted by the JVM, the client can use the default trust. If the server uses an internal CA or private PKI, configure dedicated trust material using an SSL bundle as shown in the next section.

The DNS name in `target` must match the server certificate's SAN. If the client connects by IP, the certificate needs a matching IP SAN; never disable hostname verification to bypass certificate configuration errors.

## 3. Using an SSL bundle with a private CA

A Spring Boot SSL bundle groups a truststore and/or keystore under a single name. For one-way TLS using an internal CA, the client only needs a truststore containing the CA that issued the server certificate.

PEM example:

```yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-trust:
          truststore:
            certificate: "file:/etc/pki/inventory/server-ca-chain.pem"

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-trust
```

The truststore file contains the root CA and, when necessary, intermediate CAs that the client uses to build the certificate chain. There is no need to put the server's private key into the client truststore.

You can use JKS/PKCS12 instead of PEM:

```yaml
spring:
  ssl:
    bundle:
      jks:
        inventory-trust:
          truststore:
            location: "file:/etc/pki/inventory/truststore.p12"
            password: ${INVENTORY_TRUSTSTORE_PASSWORD}
            type: PKCS12

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-trust
```

When a channel references `ssl.bundle`, TLS is enabled automatically unless overridden by configuration. Choose one clear trust source per channel to avoid mixing up the default CA with an internal CA.

## 4. Configuring mTLS with an SSL bundle

With mTLS, the client needs both:

- A truststore containing the CA used to verify the server.
- A keystore containing the client certificate chain and matching private key.

PEM bundle example:

```yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-mtls:
          keystore:
            certificate: "file:/run/secrets/grpc/client-chain.pem"
            private-key: "file:/run/secrets/grpc/client.key"
          truststore:
            certificate: "file:/etc/pki/inventory/server-ca.pem"

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-mtls
```

The server must be configured to require client authentication and trust the CA that issued the client certificate. If the server does not request a client certificate, the client certificate may not be used in the handshake according to server policy.

Equivalent with PKCS12:

```yaml
spring:
  ssl:
    bundle:
      jks:
        inventory-mtls:
          keystore:
            location: "file:/run/secrets/grpc/client.p12"
            password: ${CLIENT_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: "file:/etc/pki/inventory/server-trust.p12"
            password: ${SERVER_TRUSTSTORE_PASSWORD}
            type: PKCS12

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-mtls
```

Never package private keys or keystore passwords into a JAR, Docker image, or Git. Mount keys from a secret manager with minimal read permissions; public certificates and private keys must be managed as two different sensitivity levels.

## 5. Creating stubs from a configured channel

After declaring channel properties, inject `GrpcChannelFactory` to create the channel and bind generated stubs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.grpc.client.GrpcChannelFactory;

@Configuration
class InventoryClientConfiguration {

    @Bean
    StockServiceGrpc.StockServiceBlockingStub stockStub(
            GrpcChannelFactory channels) {

        return StockServiceGrpc.newBlockingStub(
                channels.createChannel("inventory"));
    }
}
```

The channel named `inventory` is resolved from `spring.grpc.client.channel.inventory`. TLS is applied when the channel is created; the generated stub does not need to build an SSL context itself.

If the project uses `@ImportGrpcClients` so Spring creates stub beans automatically, you can configure the corresponding channel target in properties and let the import mechanism bind the stub to the channel. Choose manual or automatic creation according to application structure, while ensuring the stub uses the right TLS-enabled channel.

Do not create a new `ManagedChannel` for each RPC. Channels should be managed according to the application lifecycle and shut down cleanly when the application stops.

## 6. Channel name, hostname, and certificate SAN

TLS does not only check the CA. The client must also verify the server's identity against the hostname it calls.

Target example:

```yaml
target: static://inventory.internal.example:9090
```

The server certificate needs a matching SAN, such as:

```text
DNS:inventory.internal.example
```

If the client calls another DNS alias, that alias must also be covered by the certificate. Connecting to an IP requires an IP-type SAN; a DNS SAN alone is not sufficient to verify an IP address.

When there is a load balancer or service discovery, the certificate must match the name the client actually uses as the authority. Never resolve a hostname mismatch by disabling certificate validation; fix the DNS, target, or certificate SAN so they match.

## 7. Distinguishing TLS from authentication metadata

A channel can both use TLS and send a Bearer token or authentication metadata:

- TLS encrypts requests/responses and verifies the server certificate.
- mTLS adds workload identity at the connection layer.
- A Bearer token identifies the principal/claims at the RPC layer.
- Authorization decides whether the principal is allowed to invoke a method.

If a service requires OAuth2, configuring TLS does not automatically add a token. Use a client interceptor or a dedicated credentials mechanism to send metadata on each RPC. Conversely, a Bearer token does not replace TLS because the token can be exposed if sent over an untrusted plaintext connection.

## 8. Do not disable certificate verification in production

Spring Boot has a `bypass-certificate-validation` property for channels, primarily to support certain testing scenarios. When enabled, the client skips server certificate checks; the connection can accept a spoofed server and loses TLS identity guarantees.

Do not use the following configuration in production:

```yaml
spring:
  grpc:
    client:
      channel:
        inventory:
          bypass-certificate-validation: true
```

If a handshake fails, find the real cause:

- The CA is not yet in the truststore.
- An intermediate certificate is missing.
- The certificate is expired or not yet valid.
- The hostname does not match the SAN.
- The server is not sending the proper certificate chain.
- Client and server do not agree on TLS/HTTP2 or allowed ciphers/protocols.

Only use validation-bypass mode in isolated tests without connecting to real data, and never let that configuration slip into a production profile.

## 9. Verifying the TLS handshake

You can verify the certificate chain and ALPN before calling RPCs using OpenSSL:

```bash
openssl s_client \
  -connect inventory.internal.example:9090 \
  -servername inventory.internal.example \
  -alpn h2 \
  -CAfile server-ca.pem \
  -verify_return_error \
  -showcerts
```

The output should show successful certificate verification and ALPN selecting `h2`. This command tests the TLS handshake, not RPC logic or authorization.

If the server has reflection enabled, test gRPC with `grpcurl`:

```bash
grpcurl \
  -cacert server-ca.pem \
  inventory.internal.example:9090 \
  list
```

With mTLS:

```bash
grpcurl \
  -cacert server-ca.pem \
  -cert client.crt \
  -key client.key \
  inventory.internal.example:9090 \
  list
```

If reflection is disabled, provide the proto file/import path and invoke a specific method instead of `list`. Never put private keys, passwords, or real tokens into command history or CI logs.

## 10. Integration testing for client TLS

A test suite over a real network transport should cover:

1. Server certificate issued by a trusted CA and matching SAN: channel connects successfully.
2. Server certificate issued by an untrusted CA: handshake fails.
3. Target hostname does not match SAN: client rejects the server.
4. Expired or not-yet-valid certificate: verification fails.
5. With mTLS, valid client certificate: server accepts.
6. With mTLS, missing client certificate or wrong CA: server rejects the handshake.
7. After replacing the truststore/certificate, create a new connection to verify that the new material is actually used.

In-process transport does not perform a network TLS handshake, so in-process tests are only suitable for testing stub/service/interceptor logic. To verify TLS, you must run Netty or a real network transport with test certificates.

## 11. Diagnosing common errors

| Symptom | Causes to check |
| --- | --- |
| `UNAVAILABLE` with handshake error | CA, chain, hostname, protocol, or TLS listener |
| `PKIX path building failed` | Client cannot build a chain to a trusted CA |
| `No subject alternative DNS name` | Target hostname is not in the SAN |
| Server requires client certificate | Channel lacks keystore/client identity or certificate is untrusted |
| `handshake_failure` | Trust/key material, TLS protocol/cipher, or mTLS policy mismatch |
| TLS succeeds, but RPC is rejected | Check authentication metadata and RPC-layer authorization |
| New channel still uses old certificate | Channel/SSL context has not been recreated or bundle not updated |

When diagnosing, inspect the exception cause and TLS logs in a test environment. Do not enable logs containing secrets or private keys. Distinguish handshake failures from gRPC statuses returned after the RPC reaches the server.

## 12. Client TLS configuration checklist

- [ ] Channel target uses a hostname present in the server certificate's SAN.
- [ ] `ssl.enabled` enables one-way TLS or `ssl.bundle` references the right bundle.
- [ ] Truststore contains the required CAs and the chain includes all intermediates.
- [ ] For mTLS, keystore contains a valid client certificate/private key.
- [ ] Server requires mTLS and trusts the CA that issued the client certificate.
- [ ] Private keys/passwords come from a secret manager or secret mount.
- [ ] `bypass-certificate-validation` is not enabled in production.
- [ ] TLS handshake and ALPN `h2` are verified.
- [ ] Integration tests run over a real network transport.
- [ ] Channels are reused and closed according to the application lifecycle.

### Key Takeaways

**Configuring TLS for the client means configuring trust and, when required, the workload's certificate identity.** Use `ssl.enabled` for one-way TLS with default trust; use `ssl.bundle` when a private CA or mTLS with both truststore and keystore is needed. Ensure the target hostname matches the SAN, never disable certificate verification in production, and verify the handshake over a real network transport before release.

## References

- [Spring Boot — gRPC: Client SSL Support](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring gRPC — Client and Channel Configuration](https://docs.spring.io/spring-grpc/reference/client.html)
- [gRPC — Authentication](https://grpc.io/docs/guides/auth/)
