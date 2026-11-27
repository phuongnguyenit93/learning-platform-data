# Using Plaintext in Production

## 1. Why is plaintext a risk?

In **SPRING_GRPC**, clients and servers exchange Protobuf requests/responses over HTTP/2. When a client configures a channel with plaintext, the transport does not encrypt data. Any party able to observe the wire can read payloads, metadata, and responses; any party able to tamper with traffic can also modify or forge data in transit.

Some requests may contain access tokens, customer data, payment information, internal data, or state-changing commands. Using plaintext in production makes all of this data completely dependent on the trustworthiness of the network path.

Key risks:

- **Confidentiality:** an eavesdropper can read requests, responses, and metadata.
- **Integrity:** traffic can be modified without channel-level protection.
- **Server identity:** the client has no cryptographic proof that it is connecting to the intended server.
- **Credential exposure:** bearer tokens in metadata can be harvested and replayed.
- **Lateral movement:** a compromised workload can observe or spoof internal traffic if network isolation is not sufficiently strict.

Plaintext may be appropriate for local development or a controlled internal link under a specific threat model. It should not be the production default simply because services run in the same VPC, cluster, or subnet.

## 2. Plaintext and TLS differ at the transport layer

gRPC uses HTTP/2 to transmit messages. TLS protects the transport channel before gRPC sends application data:

| Property | Plaintext | TLS |
| --- | --- | --- |
| Wire data encryption | No | Yes |
| Record integrity verification | No TLS protection | Yes |
| Server identity verification | No | Client verifies certificate chain and hostname |
| Client identity verification | No at TLS layer | Possible via mTLS |
| HTTP/2 negotiation | h2c/cleartext per configuration | ALPN negotiates h2 inside TLS |
| Metadata/token protection | No | Encrypted within TLS channel |

TLS does not replace business authorization. A client with a valid certificate still needs to be checked for permission to call specific RPC methods and access specific resources.

## 3. Using TLS on the gRPC client

With gRPC Java, `ManagedChannel` can enable transport security using `useTransportSecurity()`:

```java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("orders.internal.example", 8443)
    .useTransportSecurity()
    .build();
```

This configuration uses the runtime's default trust roots. It is suitable when the server certificate is issued by a CA trusted by the client environment.

If the service uses a private CA, the client must trust the right CA/certificate chain:

```java
SslContext sslContext = GrpcSslContexts.forClient()
    .trustManager(new File("/etc/grpc/pki/internal-ca.pem"))
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal.example", 8443)
    .sslContext(sslContext)
    .build();
```

Netty TLS classes depend on whether the project uses `grpc-netty` or `grpc-netty-shaded`; package imports must match the active dependency. If using a Spring gRPC starter, prefer configuring TLS through the starter's channel/client configuration mechanism so Spring manages the channel lifecycle. Do not create a secondary out-of-lifecycle channel just to enable TLS.

The client must verify that the certificate chain and hostname/SAN match the target authority. Do not disable hostname verification, use a trust-all manager, or accept arbitrary certificates as a "quick fix" for handshake errors.

## 4. Configuring TLS for the gRPC server

The server requires a certificate chain and corresponding private key. With a Netty gRPC server, you can configure an SSL context:

```java
SslContext sslContext = GrpcSslContexts
    .forServer(
        new File("/etc/grpc/pki/server-chain.pem"),
        new File("/etc/grpc/pki/server-key.pem")
    )
    .build();

NettyServerBuilder serverBuilder = NettyServerBuilder
    .forPort(8443)
    .sslContext(sslContext)
    .addService(orderService);
```

The example illustrates the gRPC Java Netty API; package names depend on `grpc-netty` or `grpc-netty-shaded`. In a Spring application, the starter typically owns the server builder and lifecycle. Configure certificates/keys via the server TLS properties or customizers supported by the starter in use; avoid manually spinning up a second server alongside Spring's server.

The certificate must include a SAN matching the DNS name the client uses. A bare Common Name should not be treated as a substitute for a Subject Alternative Name in modern designs.

## 5. TLS handshake, certificate chain, and hostname verification

When a client initiates a TLS connection, both sides negotiate protocol/ciphers and verify certificates. For gRPC over HTTP/2, ALPN must negotiate the `h2` protocol.

The client checks:

1. The certificate is valid within the current time window.
2. The certificate chain leads to a trust anchor trusted by the client.
3. The certificate has an appropriate key usage/purpose.
4. The SAN matches the hostname/authority the client is calling.
5. The certificate has not been revoked if the environment performs revocation checks.

A valid server certificate whose SAN does not match the target must still be rejected. For example, if the client calls `orders.internal.example`, the certificate must contain a matching DNS SAN or a valid wildcard per hostname matching rules.

Do not call an endpoint by IP address if the certificate only has a DNS SAN, unless the certificate also contains a matching IP SAN. Do not use authority override to mask a mismatch in production; fix DNS/target/certificate so identities align.

## 6. Mutual TLS to verify both client and server

One-way TLS verifies the server to the client. **Mutual TLS (mTLS)** requires the client to also present a certificate so the server can verify the calling workload's identity.

mTLS is useful when:

- Internal services need to verify workload identity.
- Only workloads issued certificates by a trusted CA may establish a channel.
- The network hosts multiple services/tenants and needs to reduce client spoofing risks.
- Infrastructure uses a service mesh or internal PKI issuing short-lived certificates.

Example of a server requiring a client certificate:

```java
SslContext serverContext = GrpcSslContexts
    .forServer(serverChainFile, serverKeyFile)
    .trustManager(clientCaFile)
    .clientAuth(ClientAuth.REQUIRE)
    .build();

NettyServerBuilder server = NettyServerBuilder
    .forPort(8443)
    .sslContext(serverContext)
    .addService(orderService);
```

The client presents its own certificate while verifying the server:

```java
SslContext clientContext = GrpcSslContexts.forClient()
    .trustManager(serverCaFile)
    .keyManager(clientCertificateFile, clientPrivateKeyFile)
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal.example", 8443)
    .sslContext(clientContext)
    .build();
```

The server should map certificate identity (e.g., SAN URI/DNS or subject per PKI policy) to a principal/workload identity. A successful TLS handshake only confirms the certificate was accepted; authorization must still verify whether the principal is allowed to call that method.

If using a service mesh, the mesh may perform mTLS at the sidecar/proxy. Clearly understand which proxy verifies identity and how that identity is forwarded to the application. Do not trust an arbitrary client-supplied identity header; only trust metadata stripped/rewritten and protected by a trusted proxy per the architecture.

## 7. TLS termination at a load balancer or proxy

Some deployments terminate TLS at an ingress/load balancer and then forward traffic to an internal gRPC server. This creates two connection hops:

- Client → load balancer: TLS.
- Load balancer → backend: may be TLS or plaintext depending on configuration.

TLS on the first hop does not automatically encrypt the second hop. If the backend network can be observed or accessed by untrusted workloads, internal plaintext remains risky.

Options:

- **End-to-end TLS:** client establishes TLS directly to the gRPC server.
- **TLS re-encryption:** load balancer decrypts and establishes a new TLS connection to the backend.
- **mTLS between proxy and backend:** verifies both workloads on the internal hop.
- **Controlled internal plaintext:** only when threat model, network isolation, workload identity, and policy explicitly accept it.

With HTTP/2 gRPC, the proxy/load balancer must support HTTP/2 on the respective hop and preserve streaming, trailers, deadline, and status semantics. Correct TLS configuration paired with a proxy downgrading to incompatible HTTP/1.1 can break RPCs or lose streaming behavior.

## 8. Managing certificates and private keys

Certificates expire; private keys are secrets that must be protected. Do not commit private keys to Git, bake production keys into JARs/container images, or write keys to logs.

Recommended practices:

- Store private keys in a secret manager, a Kubernetes Secret with encryption at rest, or a managed PKI agent.
- Restrict key read permissions by service identity.
- Prefer short-lived certificates with automated issuance/renewal.
- Monitor expiration dates and alert before certificates expire.
- Provide the full certificate chain so clients can verify it.
- Maintain a process to revoke and replace compromised certificates.
- Separate certificates by environment and workload identity.

Do not share the same private key across all services without a clear architectural reason. A shared key widens the blast radius if a single workload is compromised.

## 9. Rotating certificates without disrupting RPCs

Certificate rotation requires coordinating server, client, CA trust, and channel lifecycle.

A typical safe process is:

1. Issue the new certificate while the old certificate is still valid.
2. Update the trust bundle so clients accept the new CA/certificate before switching the server, if the trust anchor changes.
3. Update the server certificate/key and reload or launch new server instances via a supported mechanism.
4. Verify the handshake with a production-like client.
5. Update client certificates if using mTLS.
6. Drain old connections and monitor handshake/RPC errors.
7. Remove the old trust only after all clients have migrated and no valid old certificates still need support.

Not all Netty/gRPC servers automatically reload certificate files when files change on disk. Use a framework-supported reload mechanism or perform a rolling replacement with health checks and draining. Active client channels may also retain the old SSL context; rotation must account for creating new channels in a controlled manner and draining old ones.

## 10. TLS does not replace authentication and authorization

TLS protects the channel and verifies transport identity. The application still must decide what callers are permitted to do:

- Authentication may rely on mTLS principals, OAuth/JWT bearer tokens, or a trusted identity mechanism.
- Authorization checks whether the principal has permission to invoke the RPC method and access the resource.
- Tenant isolation must be enforced in application/database queries.
- Metadata must not be trusted simply because it traveled over TLS; an authenticated client can still send invalid or over-privileged metadata.
- Auditing must record the verified identity and action, not secrets/tokens.

If using bearer tokens, send them in gRPC metadata over TLS. Never send tokens over plaintext, log sensitive metadata, or place tokens in metric labels.

## 11. Distinguishing TLS errors from RPC/application errors

TLS errors usually occur before the RPC method executes:

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Certificate unknown/untrusted | CA chain not in trust store | Update the proper trust bundle |
| Hostname/SAN mismatch | Target does not match certificate | Fix DNS/authority or issue certificate with matching SAN |
| Certificate expired | Certificate has expired | Renew/rotate per procedure |
| Client certificate required | Server enables mTLS but client sends no cert | Issue and configure client certificate |
| Client certificate rejected | CA or identity not accepted by server | Check client CA and identity policy |
| ALPN/protocol negotiation failure | Proxy/transport failed to negotiate HTTP/2 properly | Check TLS/ALPN and proxy configuration |
| UNAVAILABLE after handshake | Server/network unavailable | Investigate transport/server health |
| INVALID_ARGUMENT/NOT_FOUND | RPC reached application and hit business error | Fix request or handle resource per contract |

Do not map every handshake failure to `INVALID_ARGUMENT`. Many TLS errors occur before the server can return a normal gRPC status; the client may observe `UNAVAILABLE` or a specific transport error.

## 12. Testing TLS in production-like environments

Tests are needed to prove the server rejects untrusted connections and accepts valid certificates:

| Test | What to verify |
| --- | --- |
| Client trusts right CA | TLS handshake succeeds and RPC runs |
| Untrusted CA | Handshake fails |
| SAN mismatches hostname | Client rejects server certificate |
| Expired certificate | Handshake fails |
| mTLS missing client cert | Server rejects connection |
| mTLS cert from wrong CA | Server rejects connection |
| Valid mTLS cert | Handshake succeeds; authorization is still checked |
| Certificate rotation | New client connects while old channel drains |
| Proxy termination | TLS on each hop matches threat model |
| Plaintext to TLS listener | Connection fails |
| TLS client to plaintext listener | Connection fails or negotiation fails per configuration |

Use dedicated test CA certificates, explicit SANs, and appropriate test lifetimes. Do not disable certificate verification in tests to make tests "green"; that only hides configuration errors.

TLS tests should run against the same transport/proxy topology as production if the system depends on an ingress or service mesh.

## 13. Local development vs. production environments

Local development can use plaintext to reduce certificate setup steps when communicating solely over loopback or in an isolated environment:

```java
ManagedChannel localChannel = ManagedChannelBuilder
    .forAddress("localhost", 9090)
    .usePlaintext()
    .build();
```

Separate configurations by profile/environment. Do not allow the production profile to inherit plaintext due to a default property or misconfigured conditional config.

A local CA and test certificates can be used so developers can test TLS early. CI should also run at least one integration suite with TLS enabled to catch SAN, trust chain, ALPN, and mTLS regressions prior to deployment.

Production should fail startup or fail health/readiness checks if required TLS material is missing or invalid, rather than silently falling back to plaintext.

## 14. Review checklist

- Production channels use TLS; plaintext is only intentionally enabled for local/test.
- Server certificate chain and private key are issued/managed from a trusted source.
- Client trusts the right CA and verifies hostname/SAN.
- TLS negotiation supports HTTP/2 via ALPN.
- No trust-all managers, disabled hostname verification, or authority overrides to bypass errors.
- mTLS is used when client workload identity must be verified.
- Certificate identity is mapped to a principal; authorization still runs in the application.
- TLS termination/proxy hops are evaluated individually, never assuming internal hops are safe by default.
- Private keys are absent from source control/images/logs and access is restricted.
- Processes exist for certificate expiry, renewal, revocation, and rotation.
- Channel/server rotation includes draining and health checks.
- Integration tests cover wrong CA, wrong SAN, expiry, mTLS, and proxy topology.
- Authentication, authorization, tenant isolation, and auditing are not replaced by TLS.

In **SPRING_GRPC**, using plaintext in production leaves gRPC data and metadata unprotected in transit, and prevents the client from verifying server identity. Configure TLS with the proper trust chain and hostname; use mTLS when mutual workload verification is needed; and manage private keys and certificate rotation in a controlled way. If TLS terminates at a proxy, evaluate each hop to the backend separately. TLS protects the transport, while authentication and authorization must still be enforced at the application layer.
