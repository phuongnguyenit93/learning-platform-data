# TLS Handshake Fails

## 1. Identify Where the Handshake Stops

In **SPRING_GRPC**, a client calls a service using gRPC over HTTP/2 and exchanges data according to a Protocol Buffers contract. When the TLS handshake fails, TCP may have connected successfully, but the two sides failed to agree on identity, certificates, TLS version, or security parameters to establish an encrypted channel.

A secure gRPC connection typically goes through these steps:

1. The client resolves the target and opens TCP to the host/port.
2. The client and server negotiate the TLS version, cipher suite, and extensions.
3. The client sends SNI if a hostname is present.
4. The server sends its certificate chain.
5. The client verifies the server's chain, validity period, and hostname/SAN.
6. If mTLS is enabled, the client sends its certificate; the server verifies the client's certificate chain and policy.
7. TLS ALPN negotiates `h2` for HTTP/2.
8. gRPC begins exchanging HTTP/2 frames and executing RPCs.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant S as TLS endpoint / server
    C->>S: TCP connect
    C->>S: ClientHello + SNI + ALPN(h2)
    S->>C: ServerHello + certificate chain
    C->>C: Verify CA, validity, SAN
    alt Mutual TLS enabled
        S->>C: CertificateRequest
        C->>S: Client certificate + proof of private key
        S->>S: Verify client certificate
    end
    S->>C: Finished
    C->>S: Finished
    Note over C,S: ALPN h2, then HTTP/2 and gRPC
~~~

Not every TLS error is caused by a certificate. `protocol_version`, `no_application_protocol`, an SNI mismatch, or mismatched plaintext/TLS settings can also stop the handshake before any gRPC method is invoked.

## 2. Distinguish TCP, TLS, and gRPC Errors

Read the root exception and logs from both client and server. `UNAVAILABLE` from gRPC is only an RPC-layer status; the underlying cause may sit deeper in the transport.

| Symptom | Likely Failing Layer | Direction to Check |
|---|---|---|
| `Connection refused` | TCP | Listener, port, bind address, and route |
| `Connection timed out` | TCP/network | Firewall, security group, NetworkPolicy |
| `SSLHandshakeException` | TLS | Certificate, trust, protocol, mTLS |
| `PKIX path building failed` | Certificate chain verification | CA trust store and intermediate certificates |
| `No subject alternative DNS name matching ...` | Hostname verification | SAN in certificate and target hostname |
| `certificate has expired` / `not yet valid` | Certificate validity | System clock and certificate lifecycle |
| `bad_certificate` / `unknown_ca` | Certificate verification on one side | Client/server certificate chain and CA trust |
| `handshake_failure` | TLS negotiation or policy | TLS versions, cipher suites, client auth |
| `protocol_version` | Incompatible TLS version | Minimum/maximum TLS versions on both ends |
| `no_application_protocol` | ALPN | HTTP/2 `h2` and proxy/TLS terminator configuration |
| `UNAUTHENTICATED` after handshake | gRPC authentication | Token, metadata, and interceptor |
| `PERMISSION_DENIED` after handshake | Authorization | Principal and permission policy |

If `grpcurl` or the client completed TLS yet the method returns `UNAUTHENTICATED`, stop swapping CAs or certificates randomly. Switch to checking application credentials.

## 3. Verify Both Ends Agree on Plaintext vs. TLS

Server and client must use the same transport mode:

- Server is plaintext, client enables TLS: the client sends a TLS ClientHello to an endpoint that does not speak TLS; the handshake fails.
- Server enables TLS, client is plaintext: the server receives plaintext HTTP/2 bytes where it expects a TLS record; the connection is closed or reports a protocol error.
- Both enable TLS but use different trust/certificates: TCP succeeds, yet the handshake may fail.

Probe using the matching mode:

~~~bash
# Only when the server is configured for plaintext.
grpcurl -plaintext orders-grpc.internal:9090 list

# TLS, verifying server certificate with the default trust store.
grpcurl orders-grpc.internal:9090 list

# TLS with a custom CA.
grpcurl -cacert ./certs/internal-ca.pem orders-grpc.internal:9090 list
~~~

`-plaintext` is not a TLS fix. `-insecure` is not a production configuration either; only use it in a controlled environment to isolate certificate verification issues, then restore trust and hostname verification.

## 4. Check the Server Certificate and Trust Chain

The client must trust the CA that signed the server certificate. The server certificate usually includes the leaf certificate and intermediate certificates required to build a chain to a root CA trusted by the client.

Check:

- Is the certificate still valid and unexpired?
- Is `Not Before` not in the future relative to the client's clock?
- Does the certificate include all necessary intermediate certificates?
- Was the certificate issued by a CA present in the client's trust store?
- Do the certificate and key pair actually belong together?
- Does the server present the right certificate for the hostname/SNI used by the client?

You can inspect a PEM certificate:

~~~bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
~~~

Inspect the fingerprint to compare against the deployed certificate:

~~~bash
openssl x509 -in server-cert.pem -noout -fingerprint -sha256
~~~

In a PEM chain, the file order is typically the leaf certificate first, followed by intermediate certificates. The root CA is usually installed in the client's trust store rather than needing to be resent as part of the server chain. Confirm the specific requirements of your TLS library and certificate packaging.

Do not confuse a server certificate with CA trust. Putting a leaf certificate in the trust store can be an intentional pinning choice, but it does not replace understanding the chain and rotation process.

## 5. SAN Must Match the Hostname Verified by the Client

The client does not just verify that the certificate is trusted by a CA; it also verifies the server's identity. For hostnames, the certificate needs a matching Subject Alternative Name (SAN).

Example client target:

~~~text
orders-grpc.backend.svc.cluster.local:9090
~~~

The server certificate must have a matching DNS SAN, for example:

~~~text
DNS:orders-grpc.backend.svc.cluster.local
~~~

If the client calls `orders.internal.example` while the certificate only has SAN `orders-grpc.backend.svc.cluster.local`, TLS hostname verification will fail even if the CA chain is valid.

Do not fix this error by disabling hostname verification. Issue a certificate whose SAN matches the service identity used by the client, or explicitly design an authority override if a proxy/service mesh requires a different authority. Ensure the verified name still represents the intended server.

For connections using an IP literal, the certificate needs a corresponding IP SAN. A DNS SAN containing an IP-like string does not replace an IP SAN.

## 6. SNI and Authority Are Related but Distinct Concepts

**SNI (Server Name Indication)** is an extension in the TLS ClientHello indicating which hostname the client wants to connect to. A TLS terminator can use SNI to select the appropriate certificate when a single IP address serves multiple hostnames.

HTTP/2 `:authority` is the request's authority information at the HTTP/2 layer. A gRPC client typically derives authority from the target, though override settings may exist in certain topologies.

If SNI is wrong:

- A proxy may return the default certificate of a different virtual host.
- The client receives a certificate whose SAN does not match the target.
- The TLS terminator may reject the handshake per policy.

Check with OpenSSL:

~~~bash
openssl s_client \
  -connect orders-grpc.internal:9090 \
  -servername orders-grpc.internal \
  -showcerts \
  -alpn h2
~~~

Testing with and without `-servername` in a controlled environment can reveal whether a TLS terminator selects certificates based on SNI. Do not drop SNI in production configuration just to avoid errors; fix the hostname, certificate, or TLS endpoint routing.

In gRPC Java, `overrideAuthority(...)` affects the authority used for the call. It does not fix DNS, does not issue certificates, and must not be used to bypass identity verification. Verify the exact behavior of your transport/version before using it.

## 7. Check mTLS: Does the Server Require a Client Certificate?

One-way TLS verifies the server certificate on the client side. **Mutual TLS (mTLS)** adds a requirement for the server to request and verify the client certificate.

With mTLS, both trust directions must be in place:

- The client trusts the CA that signed the server certificate.
- The server trusts the CA that signed the client certificate.
- The client sends the appropriate certificate when requested by the server.
- The client possesses the private key matching the certificate and proves key ownership.
- The client certificate is valid and satisfies policy (EKU, subject/SAN, or identity mapping).

Common symptoms:

- The server requests a client certificate, yet the client sends none: the handshake is rejected.
- The client sends a certificate, yet the server does not trust the CA: `unknown_ca` or `bad_certificate` error.
- The client certificate lacks the `clientAuth` EKU required by policy: the server may reject it.
- The private key does not match the certificate or cannot be read: the client cannot complete authentication.

Do not confuse mTLS errors with bearer tokens. A TLS client certificate authenticates the peer at the transport layer; a JWT/API token usually authenticates a principal or permissions at the application layer. A system may require both.

## 8. Probe mTLS with OpenSSL and grpcurl

OpenSSL can test a handshake with a client certificate:

~~~bash
openssl s_client \
  -connect orders-grpc.internal:9090 \
  -servername orders-grpc.internal \
  -alpn h2 \
  -CAfile ./certs/server-ca.pem \
  -cert ./certs/client-cert.pem \
  -key ./certs/client-key.pem \
  -verify_return_error
~~~

With `grpcurl`, you can pass the CA and client certificate/key:

~~~bash
grpcurl \
  -cacert ./certs/server-ca.pem \
  -cert ./certs/client-cert.pem \
  -key ./certs/client-key.pem \
  orders-grpc.internal:9090 list
~~~

The `list` command requires reflection to be enabled. If reflection is disabled, use `.proto`/protoset to describe and call methods; a reflection error does not prove TLS failed.

Do not pass private keys on the command line in environments with improper process listing/auditing exposure. In production, use a secret manager, proper file permissions, or a supported credential provider mechanism.

## 9. Check ALPN and HTTP/2

gRPC relies on HTTP/2. When TLS is used, both endpoints normally negotiate the `h2` application protocol via ALPN. The TLS handshake can fail if the endpoint only supports an incompatible protocol or a proxy does not advertise `h2`.

Check ALPN:

~~~bash
openssl s_client \
  -connect orders-grpc.internal:9090 \
  -servername orders-grpc.internal \
  -alpn h2
~~~

In the output, look for `ALPN protocol: h2`. If no protocol is selected, check:

- Does the TLS terminator enable ALPN `h2`?
- Does the load balancer listener support HTTP/2?
- Does the proxy forward upstream over HTTP/2 as required by the backend?
- Is any hop configured for HTTP/1.1 only?
- Is the TLS version/cipher policy compatible with the HTTP/2 implementation?

If a proxy terminates TLS at the edge and forwards to the backend, map each hop explicitly: does client→proxy use TLS/HTTP2 or plaintext/HTTP2; does proxy→gRPC server use TLS or plaintext; does the backend require separate mTLS? Do not assume TLS at the edge means the backend leg is encrypted as well.

## 10. TLS Versions and Cipher Suites

Client and server must share at least one compatible TLS version and cipher suite. Modern systems typically prefer TLS 1.2 or TLS 1.3 per security policy.

If one side only allows TLS 1.3 while the other side or an older TLS terminator only supports TLS 1.2, the handshake can fail. Overly restrictive cipher suites or incompatible security provider settings can also produce `handshake_failure`.

Do not downgrade to TLS 1.0/1.1 just to "make it run". Review policy and upgrade runtime/proxy/certificate configuration to agree on a secure common protocol.

OpenSSL can force versions for diagnostics:

~~~bash
openssl s_client -connect orders-grpc.internal:9090 -servername orders-grpc.internal -tls1_2 -alpn h2
openssl s_client -connect orders-grpc.internal:9090 -servername orders-grpc.internal -tls1_3 -alpn h2
~~~

Use these flags only to identify version differences. Afterward, fix the configuration under a unified policy rather than keeping weak settings around just to support a single un-upgraded client.

## 11. Configure TLS for a gRPC Java Client

With the gRPC Java API using channel credentials, the client can provide CA trust and an optional client certificate:

~~~java
import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.TlsChannelCredentials;

import java.io.File;

TlsChannelCredentials.Builder tls =
        TlsChannelCredentials.newBuilder()
                .trustManager(new File("certs/server-ca.pem"));

// Configure keyManager only when the server requires mTLS.
tls.keyManager(
        new File("certs/client-cert-chain.pem"),
        new File("certs/client-key.pem"));

ManagedChannel channel = Grpc.newChannelBuilder(
        "dns:///orders-grpc.backend.svc.cluster.local:9090",
        tls.build()).build();
~~~

This is an mTLS client example; if you only verify the server, omit `keyManager(...)`. Exact files and APIs depend on the gRPC Java version, transport provider, and supported private key format.

If the application uses `NettyChannelBuilder` and `GrpcSslContexts`, an equivalent configuration can be built with Netty `SslContext`. Do not mix two credential/SSL context mechanisms on the same channel without a clear reason.

Do not use `InsecureTrustManagerFactory` or a trust-all manager in production. It disables certificate verification and allows connections to forged peers.

## 12. Configure TLS for a gRPC Java Server

With the gRPC Java API using server credentials, the server supplies its certificate/private key; if mTLS is required, add a trust manager and set the client auth policy:

~~~java
import io.grpc.Grpc;
import io.grpc.Server;
import io.grpc.TlsServerCredentials;

import java.io.File;

TlsServerCredentials credentials =
        TlsServerCredentials.newBuilder()
                .keyManager(
                        new File("certs/server-cert-chain.pem"),
                        new File("certs/server-key.pem"))
                .trustManager(new File("certs/client-ca.pem"))
                .clientAuth(TlsServerCredentials.ClientAuth.REQUIRE)
                .build();

Server server = Grpc.newServerBuilderForPort(9090, credentials)
        .addService(ordersService)
        .build()
        .start();
~~~

This code requires a client certificate. If you only use one-way TLS, do not configure client auth `REQUIRE` and do not require a client CA this way. The server needs to send an appropriate chain; the client needs to trust the CA that signed the server certificate.

In a Spring gRPC application, the starter may create and manage the server automatically. In that case, configure TLS via the properties/API of your exact starter and version; do not programmatically create a second gRPC server just to enable TLS. Verify startup logs show the server binding to the right port and loading the certificate successfully.

## 13. Keystore, Truststore, and Private Key

In Java, you may use JKS or PKCS12 keystores/truststores depending on the API and starter:

- **Keystore:** holds the endpoint's own private key and certificate chain.
- **Truststore:** holds the CAs/certificates the endpoint trusts.
- **Server keystore:** typically holds the server private key and server certificate chain.
- **Client truststore:** holds the CA that trusts the server certificate.
- **Client keystore in mTLS:** holds the client private key and client certificate chain.
- **Server truststore in mTLS:** holds the CA that trusts the client certificate.

Do not confuse a keystore with a truststore. Adding a server certificate to a client's truststore can establish pinning, but it does not mean the client has the server's private key. Conversely, a truststore does not provide an identity private key for a server.

When converting PEM to PKCS12/JKS, verify the alias, chain, key password, store password, and key type. Do not hardcode passwords in source code or commit them to a repository; retrieve them from a secret manager or controlled secret injection.

## 14. Spring gRPC: Verify the Exact Starter Configuration

Different Spring gRPC starters and Spring gRPC libraries may use different property namespaces and TLS loading mechanisms. Before editing configuration:

1. Identify the actual starter running and its compatible version.
2. Determine whether the gRPC server is managed by the starter or created manually by the application.
3. Verify TLS properties, certificate/key paths, passwords, and client-auth mode against documentation for your exact version.
4. Check that files/secrets are mounted into the right container and the process user has read permissions.
5. Check startup logs for errors loading keys, parsing certificates, or binding ports.
6. Verify the server actually presents the new certificate after deployment.

Do not copy TLS properties from another starter just because the property names look similar. Do not set both `spring.grpc.*` and `grpc.server.*` expecting both to take effect; only one namespace may be bound.

## 15. TLS Termination at a Proxy or Service Mesh

In production, TLS may terminate at a load balancer, ingress gateway, or service mesh sidecar. Map the hops clearly:

~~~text
gRPC client
   | TLS + HTTP/2 (h2)
   v
Load balancer / gateway
   | TLS + HTTP/2, or plaintext + HTTP/2 per policy
   v
Service mesh sidecar
   | mTLS or configured transport
   v
Spring gRPC server
~~~

Common errors:

- The edge certificate is valid, yet the gateway picks the wrong certificate due to SNI.
- Client→gateway uses HTTP/2, yet gateway→backend uses HTTP/1.1.
- The gateway requires mTLS, yet the client does not send a certificate.
- The gateway terminates TLS while the backend also enables TLS, yet the gateway sends plaintext.
- The sidecar expects a workload identity/certificate different from the application configuration.

Check logs and metrics at each hop. If OpenSSL connects to the gateway yet the gRPC server receives no requests, investigate the upstream protocol and backend TLS separately. Successful TLS at the edge does not prove TLS/mTLS between the gateway and backend succeeded.

## 16. Enable TLS Diagnostics in Java

With the JSSE/JDK SSL provider, you can enable debugging in test or staging environments:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

Logs can show ClientHello, ServerHello, certificate chain, trust decisions, and alerts. However, gRPC Java may use the Netty/OpenSSL native provider; in that case, `javax.net.debug` will not necessarily display the full handshake. Check which provider is in use and enable appropriate logging for Netty/the TLS terminator.

Do not leave detailed TLS debugging enabled long-term in production if logs could expose sensitive details or generate excessive log volume. Collect logs during a controlled window, restrict access, and turn debugging off once diagnosis is complete.

## 17. TLS Handshake Isolation Workflow

Work from transport up to application:

1. **Confirm TCP:** can host/port be opened from the client's exact environment?
2. **Confirm mode:** do both server and client use TLS or plaintext as designed?
3. **Fetch actual certificate:** use `openssl s_client -showcerts` with the right SNI.
4. **Check chain and validity:** CA trust, intermediates, `Not Before`/`Not After`.
5. **Check SAN/SNI:** the hostname verified by the client must match the selected server certificate.
6. **Check mTLS:** does the server require a client certificate; does the client send key/cert and does the server trust the CA?
7. **Check TLS version/cipher:** find a common protocol allowed by policy.
8. **Check ALPN:** `h2` must be negotiated for gRPC over TLS.
9. **Check each proxy hop:** TLS termination, upstream protocol, and mTLS between workloads.
10. **Probe gRPC:** use `grpcurl` with appropriate CA/client certs; only then investigate authentication and methods.

Record evidence at each step. Do not change CA, hostname, TLS version, and proxy config simultaneously, or it will be hard to pinpoint the real cause.

## 18. Symptom and Resolution Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `PKIX path building failed` | Client cannot build a chain to a trusted CA | Install the right root CA and send complete intermediates |
| Hostname/SAN mismatch | Certificate does not represent the target used by client | Issue the right SAN or design an explicit authority |
| `certificate expired` | Certificate has expired | Rotate the certificate and check automation |
| `certificate not yet valid` | Clock skew or certificate not yet effective | Synchronize clocks and check validity |
| `unknown_ca` | One side does not trust the other side's CA | Install the right trust anchor on the right side |
| `bad_certificate` | Invalid certificate, wrong chain/key/EKU | Check chain, key pair, and certificate usage |
| Server requires client cert but client sends none | mTLS not configured on client | Load client certificate/private key |
| `protocol_version` | No overlapping TLS versions | Align secure minimum/maximum TLS versions |
| `handshake_failure` | Incompatible cipher/policy/client-auth | Read alerts and logs on both ends, compare against policy |
| `no_application_protocol` | ALPN could not negotiate `h2` | Fix HTTP/2/ALPN at endpoint and proxy |
| TLS succeeds but RPC returns `UNAUTHENTICATED` | Missing/invalid application-layer credential | Check tokens and interceptors |

## 19. Common Configuration Mistakes

| Wrong Practice | Consequence | Right Practice |
|---|---|---|
| Plaintext on one end, TLS on the other | Handshake/protocol fails | Align transport mode |
| Trusting CA without checking SAN | Might connect to the wrong server | Verify hostname identity |
| Using leaf certificate without intermediates | Client cannot build chain | Send the complete required chain |
| Confusing truststore with keystore | Missing trust or missing private key | Separate server/client identity and trust |
| Enabling mTLS on server without issuing client cert | Handshake rejected | Configure client key/cert and server trust CA |
| Disabling hostname verification or trust-all | Loses peer identity verification | Fix CA, SAN, SNI, and trust |
| Using an obsolete TLS version for compatibility | Lowers security posture | Upgrade runtime/proxy and align on TLS 1.2/1.3 |
| Skipping backend checks because edge TLS succeeded | Upstream mTLS/HTTP2 errors go undetected | Check each hop |
| Testing only TCP | Fails to detect certificate/ALPN errors | Use OpenSSL and grpcurl |

**Remember:** A gRPC TLS handshake requires all of these to be right simultaneously: transport mode, certificate chain, trust, SAN/SNI, mTLS policy, and ALPN `h2`. Verify each side: the client trusts the server certificate; if mTLS is enabled, the server must also trust the client certificate. Use OpenSSL to inspect certificates/ALPN, grpcurl to probe gRPC, and controlled TLS logging to identify alerts. With Spring gRPC, configure according to your exact starter/version and inspect each hop separately if a proxy or service mesh is present.
