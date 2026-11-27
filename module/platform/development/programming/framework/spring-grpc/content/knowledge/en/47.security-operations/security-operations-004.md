# Trust Store Management

A trust store is a repository of certificates and trust anchors that an application uses to decide whether a peer's certificate is trusted. In gRPC over TLS, the client typically uses a trust store to verify the server certificate; when mutual TLS (mTLS) is enabled, the server also needs a trust store to verify the client certificate. Proper trust store management helps restrict trusted CAs, roll out CA changes safely, and avoid connection errors during certificate rotation.

In Spring gRPC, the trust store belongs to the TLS configuration of the channel or server listener. You must determine whether TLS actually runs on JSSE or Netty/OpenSSL, configure the proper trust manager for each connection direction, and enforce hostname/SAN checks. The mere fact that a trust store file exists or is mounted into a container does not prove the gRPC channel is using it.

## 1. How Does a Trust Store Differ from a Key Store?

The two stores serve distinct purposes:

| Store | What It Contains | What It Is Used For |
| --- | --- | --- |
| Trust store | CA certificates or certificates configured as trust anchors | Verifying certificates presented by peers |
| Key store | Private keys and the certificate chains matching those private keys | Proving the application's own identity |

In one-way TLS, the client needs a trust store to verify the server certificate; the server needs its private key and server certificate chain in its key material to complete the handshake.

In mTLS:

- The client needs a trust store to verify the server.
- The client also needs key material containing the client private key and certificate chain.
- The server needs the server's key material.
- The server needs a trust store containing the CAs authorized to issue client certificates.

Never put a private key into a trust store simply because a configuration file name includes the word "trust". A trust store does not replace a key store, and a key store does not automatically define which CAs the application trusts.

## 2. Trust Anchors and Certificate Chains

When a peer sends its leaf certificate, the verifier builds a certificate path from the leaf through intermediate CAs to a configured trust anchor. A trust anchor is usually a root CA certificate, though some environments pin an intermediate or leaf certificate per policy.

```text
orders.internal server certificate (leaf)
             |
             v
       Workload Issuing CA
             |
             v
       Internal Root CA  <--- trust anchor in client trust store
```

A trust store should contain only the CAs required for the connection. Importing an overly broad CA makes every valid certificate issued by that CA (and matching path/hostname/EKU constraints) a trusted candidate. Scope trust anchors by environment and workload to reduce blast radius if a CA key is compromised.

Intermediate certificates are normally sent by the peer during the handshake so the client can build the chain. It is unnecessary to import every intermediate into the trust store if the server provides the full chain and the root CA is already trusted. If intermediates are missing, handshakes may fail even when the root CA is in the trust store.

## 3. Choosing a Format and Protecting the Trust Store

Java supports several keystore types. PKCS12 is typically the right choice for new configurations because it is a standard format and can hold certificate/key entries:

```bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12
```

This command imports a certificate into the trust store; verify the fingerprint before accepting the certificate. Never auto-confirm trust for a certificate from an unverified source.

Inspect the contents:

```bash
keytool -list -v \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12
```

Verify the alias, subject, issuer, serial number, validity period, SHA-256 fingerprint, and entry type. A trust entry must hold the expected CA/trust anchor certificate; do not confuse it with a private key entry.

A password protects the store's integrity and can encrypt sensitive entries in the file, but it does not replace file permissions, secret management, or host protection. Never commit passwords to source code, Docker images, or repositories. Provide passwords via a secret manager or platform secret injection; restrict file read permissions to the required process.

## 4. Building a Trust Store from Multiple CAs

An application may connect to multiple internal systems whose certificates are issued by different CAs. Multiple CAs can be imported into the same trust store under distinct aliases:

```bash
keytool -importcert \
  -alias orders-root-ca \
  -file orders-root-ca.pem \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12

keytool -importcert \
  -alias payments-root-ca \
  -file payments-root-ca.pem \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12
```

Each alias should clearly describe the CA and environment. Avoid generic aliases like `ca1` or `cert` if they hinder auditing and rotation. If two systems should not trust the same CAs, consider separate trust stores or per-channel trust managers rather than pooling every CA into one global store.

Before importing, verify the CA fingerprint through an independent trusted channel. A PEM file named `internal-root-ca.pem` does not prove its contents genuinely belong to the internal CA.

## 5. Using a Trust Store with JSSE TrustManagerFactory

For JSSE-based TLS, `TrustManagerFactory` creates trust managers from a trust store:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

Path trustStorePath = Path.of("/run/secrets/grpc-truststore.p12");
char[] password = loadTrustStorePassword();

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustStorePath)) {
    trustStore.load(input, password);
}

TrustManagerFactory trustManagers =
    TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, trustManagers.getTrustManagers(), null);
```

This example creates an `SSLContext` that trusts peers according to the trust store. It does not configure a client certificate/private key; mTLS requires a separate `KeyManagerFactory` passed to `sslContext.init`. Zero out or clear the password char array after use as appropriate for the application lifecycle.

On the client, this trust manager verifies the server certificate. On an mTLS server, a trust manager is similarly configured to verify client certificates. Hostname verification must be enabled on the client; a valid trust chain whose SAN does not match the hostname must still be rejected.

## 6. Trust Stores in grpc-java Netty

When gRPC uses the Netty transport, the TLS context is typically constructed using Netty `SslContext`. Example of a client trusting a CA from PEM:

```java
import io.grpc.netty.GrpcSslContexts;
import io.grpc.netty.NettyChannelBuilder;
import io.netty.handler.ssl.SslContext;

SslContext clientTls = GrpcSslContexts.forClient()
    .trustManager(new File("/run/secrets/internal-root-ca.pem"))
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal", 8443)
    .sslContext(clientTls)
    .build();
```

Packages/imports differ if the project uses `grpc-netty-shaded`; in that case use the corresponding shaded namespace and do not mix unshaded and shaded Netty classes. Exact APIs must match the `grpc-java` version in your dependency graph.

An mTLS server example requires both server key material and the trusted CA for clients:

```java
SslContext serverTls = GrpcSslContexts.forServer(
        new File("/run/secrets/server-chain.pem"),
        new File("/run/secrets/server-key.pem"))
    .trustManager(new File("/run/secrets/client-root-ca.pem"))
    .clientAuth(ClientAuth.REQUIRE)
    .build();
```

On the server side, `trustManager` specifies the CA used to verify client certificates; `clientAuth(REQUIRE)` requires clients to present a certificate. Configuring only the server certificate without enabling `clientAuth` does not enforce mTLS client authentication.

Not every Spring gRPC starter directly exposes `SslContext` or the same builder API. Some setups use SSL bundles, customizers, or dedicated extension points. Use the exact hook provided by your starter version; do not invent property names and assume they take effect.

## 7. Client and Server Trust Stores in mTLS

Each side makes an independent trust decision:

| Component | Key Material | Trust Store |
| --- | --- | --- |
| gRPC client | Client certificate/private key if mTLS | CA that issued the server certificate |
| gRPC server | Server certificate/private key | CA that issued client certificates |

If client and server share the same internal CA, both may trust that root. If workloads are partitioned into trust domains, use separate CAs or separate trust stores so one service does not automatically trust certificates from every workload.

Server certificates need a SAN matching the DNS name clients connect to. Client certificates need an EKU/key usage matching the client role and subject/SAN/URI SAN per the system's identity policy. The trust store validates the chain; authorization must still verify identity and permissions after the TLS handshake.

Never disable hostname verification to resolve SAN errors. Fix the certificate or target hostname to match the contract. Likewise, never switch to a trust-all `TrustManager` to bypass trust chain failures in production.

## 8. Inspecting Hostnames, Chains, and Certificates with Tools

You can use OpenSSL to observe the server certificate chain and verify trust:

```bash
openssl s_client \
  -connect orders.internal:8443 \
  -servername orders.internal \
  -showcerts \
  -verify_return_error \
  -CAfile internal-root-ca.pem
```

For mTLS environments, add the client certificate and private key:

```bash
openssl s_client \
  -connect orders.internal:8443 \
  -servername orders.internal \
  -cert client-chain.pem \
  -key client-key.pem \
  -CAfile server-root-ca.pem \
  -verify_return_error
```

This command is useful for testing handshakes independently of the application, but it does not prove Spring gRPC is loading the right trust store or using the intended TLS provider. Inspect runtime configuration and invoke RPCs over an actual channel.

When diagnosing failures, distinguish:

- Unknown CA: missing trust anchor or unable to build chain.
- Expired/not yet valid: certificate timestamps are outside validity.
- SAN/hostname mismatch: server identity does not match target.
- Missing intermediate: peer did not send the required chain.
- Wrong EKU/key usage: certificate does not fit the client/server role.
- Client certificate required: server requires mTLS but client presented no certificate.

Never post private keys or passwords in logs/tickets. Subject, issuer, serial, and fingerprint may be shared after assessing sensitivity.

## 9. Updating Trust Stores and Rotating CAs

Trust anchor changes must roll out in order to prevent outages:

1. Distribute the new CA into the trust stores of clients/servers that need to trust the new certificates.
2. Verify the file, alias, fingerprint, and that the trust manager has loaded the new CA.
3. Deploy new leaf certificates signed by the new CA.
4. Open new connections and verify TLS/mTLS along with business RPCs.
5. Monitor handshake errors across all replicas.
6. Once no valid peers use the old CA, remove the old CA from trust stores.

The overlap phase allows trusting both old and new CAs during transition. Do not remove the old CA before all required peers have migrated certificates, unless the old CA is compromised and needs emergency revocation.

A trust store file updated on disk is not necessarily reloaded by a running process. `TrustManagerFactory`/`SSLContext`/Netty `SslContext` are typically initialized from data read at startup. Reload the TLS context, create new channels/servers, or restart instances using a mechanism supported by the application.

With gRPC HTTP/2, channels can hold long-lived connections. To pick up a new trust store, drain and recreate channels so new handshakes use the updated configuration. Verify every replica, sidecar, and gateway shares the same trust policy before concluding rotation.

## 10. Managing Trust Stores in Spring Deployments

In Spring gRPC, trust stores are typically delivered as mounted secrets or platform-managed files. Key principles:

- Keep trust stores outside the application artifact and container image.
- Use minimal file permissions; the process only needs read access.
- Pass passwords via secret manager/controlled environment injection; never commit them in public YAML.
- Separate trust stores by environment and workload boundary.
- Record version, fingerprint, issuer, and update timestamp.
- Provide a reload/channel-recreation or rolling-restart mechanism when the trust store changes.
- Monitor handshake and certificate chain errors after rollout.

If using Spring Boot SSL bundles or starter-specific TLS settings, verify that the bundle actually applies to the gRPC channel/server. Configuring Actuator HTTPS or the HTTP server does not automatically prove the gRPC Netty listener uses the same trust store.

## 11. Testing Trust Stores

Create dedicated CAs/certificates for tests. Never use production private keys. Basic test matrix:

| Test Case | Expected Outcome |
| --- | --- |
| Server certificate signed by CA in trust store | Client handshake succeeds |
| Server certificate signed by untrusted CA | Client rejects handshake |
| Missing intermediate in chain | Handshake fails unless a valid chain can be built |
| SAN does not match target hostname | Client rejects server |
| Expired server certificate | Handshake fails |
| mTLS client certificate signed by server-trusted CA | Server accepts handshake |
| Client certificate signed by untrusted CA | Server rejects handshake |
| Client sends no certificate when server `REQUIRE`s it | Handshake fails |
| New trust store loaded into a new channel | Connection with new CA succeeds |
| Old channel retains old TLS context | Behavior verified prior to draining |
| Wrong alias/fingerprint | Deployment validation catches it |
| Wrong password or file permissions | Application reports a clear configuration error |

Integration tests must run through an actual gRPC channel, not just call `TrustManager` directly. Verify client hostname verification, server mTLS client validation, observed status/transport errors, and channel recreation behavior.

## 12. Applied Exercise

A platform has `OrderClient` calling `OrderService` over mTLS. Both services currently use `Internal Root CA v1`; the organization is preparing to migrate to `Root CA v2`. `OrderClient` runs multiple replicas with long-lived HTTP/2 channels.

**Tasks:**

1. Identify the key material and trust stores required on client and server.
2. Build a PKCS12 trust store containing both `CA v1` and `CA v2` for the overlap period.
3. Verify aliases, issuers, serials, and SHA-256 fingerprints before deployment.
4. Configure the client to trust the server CA and the server to trust the client CA per the exact TLS provider.
5. Verify hostname/SAN and EKU for both certificates.
6. Deploy new leaf certificates, create new channels, and verify mTLS.
7. Drain old channels before removing `CA v1` from the trust store.
8. Write tests proving untrusted CAs and mismatched hostnames are rejected.
9. Verify the Spring gRPC starter is actually using the configured trust manager/TLS context, not just that the file is mounted.

**Self-check questions:**

- How does a trust store differ from a key store in contents and purpose?
- What roles do trust anchors and intermediate certificates play?
- Why does importing overly broad CAs expand the trust boundary?
- In mTLS, whose trust store do the client and server each need?
- Why must a valid chain with a mismatched hostname still fail?
- Which component does `TrustManagerFactory` create in JSSE?
- How can Netty `SslContext` and JSSE `SSLContext` differ?
- Why does updating a trust store file not automatically change a running `SSLContext`?
- Why must HTTP/2 channels be drained when rotating trust anchors?
- Which tests prove a gRPC listener is genuinely using a new trust store?

**Takeaway:** A trust store defines which peer CAs/certificates are trusted; a key store provides the application's own private key and certificate. In mTLS, each side presents its key material and verifies the peer's trust chain. Manage aliases/fingerprints, hostnames, and EKUs; roll out new CAs with an overlap phase; reload TLS contexts and create new channels; and test through the exact Spring gRPC TLS provider running in production.
