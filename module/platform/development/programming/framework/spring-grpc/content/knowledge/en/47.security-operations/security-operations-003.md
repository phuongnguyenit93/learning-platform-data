# Certificate Revocation

Certificate revocation is the action of marking a certificate as no longer trusted before it expires. In gRPC over TLS, this is especially critical for mutual TLS (mTLS): the client verifies the server certificate, and the server verifies the client certificate. When a private key is compromised, a device is lost, personnel leave the organization, or a certificate is misissued, waiting for expiration is insufficient.

In Spring gRPC, certificate revocation is a PKI and operational process integrated with the TLS trust manager, channel lifecycle, and configuration rollout. You must determine which peer checks revocation status, how CRL/OCSP is distributed, how the application behaves when the responder is unreachable, and how already-established HTTP/2 connections are closed. Certificate revocation protects new TLS authentications; it does not automatically terminate in-flight RPCs on an already-handshaked connection.

## 1. What Problem Does Certificate Revocation Solve?

An X.509 certificate binds a public key to an identity and is signed by a CA. The trust chain determines which CAs are trusted; the validity period defines how long the certificate remains valid. Revocation adds a revoked status within that validity window.

Common causes include:

- Private key exposure, unauthorized copying, or insecure storage.
- Compromise of the host, pod, workload, or device holding the certificate.
- Certificate issued with the wrong SAN, EKU, subject, or scope.
- Workload decommissioned, replaced, or transferred in ownership.
- CA detects an error during certificate issuance or signing.
- Intermediate CA or CA key compromise.

Certificate revocation differs from expiration. Expiration is the end of the timestamp recorded in the certificate; revocation is an active decision by the CA or issuing organization prior to that timestamp. Replacing a certificate does not automatically revoke the old one: both actions must be coordinated through a rotation procedure.

## 2. Who Checks Revocation Status in gRPC TLS?

In one-way TLS, the client verifies the server certificate. In mTLS, both sides verify the peer's certificate:

| Connection | Verifying Party | Certificate Checked |
| --- | --- | --- |
| TLS | gRPC client | gRPC server certificate |
| mTLS | gRPC client | gRPC server certificate |
| mTLS | gRPC server | Client certificate |
| Gateway/proxy terminates TLS | Gateway/proxy | Certificate of the TLS peer connecting directly to the gateway |

If TLS terminates at an ingress or service mesh sidecar, the Spring gRPC application behind it may only receive internal connections already authenticated by the proxy. In that setup, revocation checking happens at the proxy/sidecar; you must also verify the proxy-to-service hop and how identity is forwarded to the application. Never assume external client certificates are always checked inside the service JVM.

With direct mTLS between two gRPC processes, both client and server must have matching trust configurations and revocation policies. A truststore containing trusted CAs does not mean leaf certificates are checked against CRL or OCSP.

## 3. CRL and OCSP

Two standard mechanisms for querying revocation status are Certificate Revocation Lists (CRL) and Online Certificate Status Protocol (OCSP).

| Mechanism | How It Works | Advantages | Operational Considerations |
| --- | --- | --- | --- |
| CRL | CA publishes a list of revoked certificate serials; verifiers download and check the list | Can be cached and used in connectivity-constrained environments | Must update CRL on time, check `nextUpdate`, and distribute to all verifiers |
| OCSP | Verifier queries a responder for a single certificate's status | Status can be fresher than large CRLs | Requires responder availability, low latency, sensible caching, and response signature verification |
| OCSP stapling | TLS server sends a CA/responder-signed OCSP response during the handshake | Reduces direct client queries to the responder | Must verify TLS provider/client supports it and handles responses per policy |

A CRL typically contains serial numbers, revocation timestamps, and revocation reasons. Verifiers must construct the proper certificate path and use the CRL applicable to the corresponding issuer. Expired or stale CRLs cannot be treated as trustworthy revocation data.

OCSP typically returns `GOOD`, `REVOKED`, or `UNKNOWN`. `GOOD` only means the responder has no record of the certificate being revoked at the response timestamp; it does not replace checking the certificate signature, hostname/SAN, EKU, validity period, or trust chain. `UNKNOWN` does not mean `GOOD`.

No revocation mechanism enables itself automatically just because an application uses TLS. You must configure the trust manager/provider to perform the checks and verify that the actual TLS provider supports the chosen mechanism.

## 4. Policy When CRL/OCSP Is Unreachable

When a verifier cannot retrieve revocation information, the system must have an explicit policy:

- Fail closed: reject the handshake if revocation status cannot be verified per policy.
- Soft fail/fail open: proceed if the responder or CRL endpoint is temporarily unavailable.
- Use valid cache: accept a verified response/CRL if it remains within the policy's allowed freshness window.

Fail closed reduces the risk of accepting a revoked certificate but can disrupt connectivity during CA/responder outages. Fail open increases availability but opens a risk window while status cannot be verified. This is a security architecture decision and should not be left to library defaults.

Specify explicitly:

1. How long CRL/OCSP cache entries remain fresh.
2. How to handle `UNKNOWN` responses, invalid signatures, issuer mismatches, or expired CRLs.
3. Timeouts and retries for responders to avoid stalling handshakes.
4. Alerts when revocation sources fail or data nears expiration.
5. Emergency procedures to immediately reject a serial even before responders/caches update.

Never treat a network error reaching an OCSP responder as proof that a certificate is valid. Nor retry indefinitely inside a TLS handshake, which can exhaust threads and disrupt all new connections.

## 5. Enabling Revocation Checking in Java TLS

Java JSSE supports PKIX revocation checking. For the SunJSSE/PKIX trust manager, commonly used system properties include:

```text
-Dcom.sun.net.ssl.checkRevocation=true
-Dcom.sun.security.enableCRLDP=true
-Docsp.enable=true
```

These properties instruct JSSE to check revocation status via CRL Distribution Points and/or OCSP depending on the certificate path and provider configuration. They must be set before initializing the TLS context/trust manager. Verify behavior on the exact JDK, security provider, and PKIX setup your application runs on.

Example JVM startup:

```bash
java \
  -Dcom.sun.net.ssl.checkRevocation=true \
  -Dcom.sun.security.enableCRLDP=true \
  -Docsp.enable=true \
  -jar orders-grpc.jar
```

This is an example for JSSE; do not infer that every TLS provider honors these properties. `grpc-java` may run via Netty with OpenSSL/native providers or a custom `TrustManagerFactory`. When using another provider, configure revocation on that provider/trust manager and verify with a revoked test certificate.

In Spring applications, place JVM/security configuration in the deployment environment and initialize `SSLContext` after those settings take effect. Do not add properties to application config and assume the starter or native TLS engine will apply them automatically.

## 6. Trust Managers and gRPC Channels/Servers

Revocation checking must be part of certificate path validation performed by the TLS trust manager. In implementation terms:

- The gRPC client uses a trust manager to verify the server certificate.
- The gRPC server uses a trust manager to verify client certificates when mTLS is enabled.
- The key manager supplies the local certificate/private key; the trust manager decides whether the peer certificate is trusted.
- CRL/OCSP sources and caches must be reachable from the exact runtime/container.

In `grpc-java` Netty, TLS contexts are typically built via `SslContextBuilder` and can accept a `TrustManagerFactory`. The `TrustManagerFactory` must be configured with proper PKIX/revocation checking; simply passing a plain CA truststore does not prove revocation checking is enabled.

In Spring gRPC, how you provide an `SSLContext`, `TrustManagerFactory`, or Netty `SslContext` depends on the starter and version in use. Use your project's actual extension points to configure both the client channel and server listener. Do not invent property names, and do not configure only the client while the mTLS server still accepts revoked client certificates.

If implementing a custom `X509TrustManager`, it must perform full chain validation, validity checks, key usage/EKU checks, client-side hostname verification, and revocation checking. A wrapper that only checks serial numbers against a static list while skipping PKIX path validation can introduce a severe vulnerability.

## 7. Revoking Client Certificates in mTLS

When a client certificate is revoked, the gRPC server is responsible for rejecting that certificate during new TLS handshakes. General workflow:

1. The CA marks the client certificate serial as `REVOKED`.
2. CRL/OCSP is updated and published.
3. The server's trust manager downloads/receives the updated data per its freshness policy.
4. The client opens a new mTLS connection.
5. The server verifies the certificate chain and revocation status.
6. The handshake is rejected before any RPC is dispatched.

If TLS terminates at a proxy, the proxy must check the client certificate. A backend service can rely on proxy-forwarded identity only if the proxy-to-service channel is authenticated and identity headers cannot be spoofed by callers.

A revoked client certificate typically results in a TLS handshake error rather than an application-level gRPC status like `PERMISSION_DENIED`. Because the handshake may fail before an HTTP/2/gRPC call is formed, clients typically observe transport/SSL errors or `UNAVAILABLE` depending on the channel/provider; tests should not depend on a single fixed gRPC status code across all TLS providers.

## 8. Revoking Server Certificates

When a server certificate is revoked, every gRPC client must check the server certificate status during the TLS handshake. Updating CRL/OCSP on the server is insufficient if client trust managers still hold stale data or have revocation checking disabled.

Workflow:

1. The CA revokes the compromised server certificate.
2. Publish the updated CRL/OCSP and verify the responder returns `REVOKED`.
3. Update revocation data/trust configuration across the entire client fleet.
4. Establish a new TLS connection from client to server.
5. Verify the client rejects the revoked server certificate.
6. Issue and deploy a new server certificate following the rotation procedure.

In mTLS, revoking the server certificate does not replace client certificate checking on the server side. Each authentication direction has its own trust manager and revocation data.

## 9. Revoked Certificates and Open HTTP/2 Connections

Revocation checks typically run during certificate verification in the TLS handshake. gRPC uses HTTP/2 connections that can carry many RPCs and stay open for a long time. When a CA marks a certificate as revoked, previously handshaked TLS connections do not automatically rerun certificate validation for each RPC.

Therefore, incident response must coordinate:

- Stop dispatching new calls on affected channels/connections.
- Close or drain existing channels to force new TLS handshakes.
- Clear/refresh connection pools and session caches as supported by the provider.
- Restart or reload client/server TLS contexts if revocation caches/trust managers are read only at initialization.
- Verify all replicas and proxies have received the updated CRL/OCSP before considering the incident resolved.

TLS session resumption must also be considered: a resumed session may skip full certificate validation depending on the protocol/provider. For key compromise incidents, invalidate sessions/caches or restart/rotate connections as supported by the runtime, and test against the actual TLS provider.

## 10. Normal Rotation vs. Emergency Revocation

Rotation is replacing a certificate before or near expiration. Revocation is rendering a certificate unacceptable. A normal rotation workflow can have an overlap window to avoid disruption:

| Phase | Action |
| --- | --- |
| Prepare | Issue new certificate, verify SAN/EKU/chain, and distribute required CAs |
| Deploy | Deploy the new certificate to server/client |
| Refresh | Create new TLS contexts/channels or drain old connections |
| Verify | Verify handshakes and RPCs using the new certificate |
| Retire | Stop using the old certificate |
| Revoke | Revoke the old certificate when no longer needed or per policy |

In a compromise incident, do not wait for normal overlap to complete. Immediately revoke the old certificate, update revocation sources, apply an emergency denylist if needed, and force affected connections/sessions to re-authenticate. A temporary denylist at the gateway or trust layer can speed up response, but it must have an owner, expiration, and removal procedure so it does not linger permanently outside PKI.

If a CA private key is compromised, revoking a single leaf certificate is insufficient. Assess all certificates signed by that CA, remove the compromised CA/intermediate from appropriate trust paths, and distribute updated truststores. Root CA compromise typically requires replacing the trust anchor across the entire fleet.

## 11. Runbook for Compromised Certificates

Upon receiving an alert of a compromised private key:

1. **Determine scope:** subject, issuer, serial, fingerprint, SAN, EKU, owner, workload, and certificate validity.
2. **Isolate:** identify all servers/clients, gateways, sidecars, and connection pools using the certificate.
3. **Revoke:** request the CA to revoke the serial and publish updated CRL/OCSP.
4. **Distribute:** update revocation caches/trust managers and verify all replicas receive the fresh data.
5. **Emergency block:** if revocation sources lag, apply a serial/fingerprint denylist at controlled trust enforcement points.
6. **Close old connections:** drain channels, invalidate sessions/caches, or restart affected components to force fresh handshakes.
7. **Replace certificate:** issue a new certificate and deploy the new private key via secret manager.
8. **Verify:** old certificate is rejected; new certificate connects; legitimate RPCs succeed.
9. **Monitor:** inspect handshake failures, OCSP/CRL errors, lingering TLS sessions, and un-updated replicas.
10. **Record audit:** log serial/fingerprint, timestamps, approver, CA actions, and rollout results; never log private keys.

The runbook needs owners across CA, platform, service teams, and security operations. Revoking at the CA without refreshing channels/trust managers can allow existing connections to keep running.

## 12. Testing Revocation

Prepare a dedicated test CA and test certificates for testing. Never use production private keys or certificates in tests. Cover these cases:

| Certificate/Test Case | Expected Outcome |
| --- | --- |
| Valid, unrevoked certificate | TLS handshake succeeds |
| Leaf certificate serial in CRL | Handshake is rejected |
| OCSP returns `REVOKED` | Handshake is rejected |
| OCSP returns `UNKNOWN` | Handled per defined policy, never defaulted to `GOOD` |
| Expired or stale CRL | Fails per freshness/fail-open policy |
| OCSP responder timeout | Fails per timeout and fail-open/closed policy |
| Invalid OCSP/CRL signature | Rejects invalid status data |
| Expired certificate | Handshake is rejected |
| SAN/hostname mismatch | Client rejects server |
| Inappropriate EKU/key usage | Certificate is rejected for that role |
| Revoked Intermediate CA | Path validation rejects the chain |
| Revoked client certificate in mTLS | Server rejects new handshakes |
| Revoked server certificate | Client rejects new handshakes |
| HTTP/2 connection opened before revocation | Terminated only when channel/session is drained or closed per procedure |

For handshake failures, verify that the client cannot invoke RPCs over that connection and that server/client logs contain sufficient diagnostic information without leaking secrets. Test CRL/OCSP cache freshness and refresh behavior after updates.

## 13. Applied Exercise

A Spring gRPC system uses mTLS between `OrderClient` and `OrderService`. The client certificate is issued by an internal CA; the server certificate has SAN `orders.internal`. A client private key is exposed in a CI incident while multiple pods hold long-lived HTTP/2 channels.

**Tasks:**

1. Identify which peer checks the client certificate and which checks the server certificate.
2. Plan revoking the client certificate serial and publishing CRL/OCSP.
3. Identify the actual TLS provider/trust manager on client and server; verify revocation checking is enabled in both required directions.
4. Choose a fail-open/closed policy for CRL/OCSP responder failures and freshness.
5. Plan draining old channels/sessions to force new handshakes.
6. Issue a new client certificate, deploy the secret, and verify mTLS.
7. Write tests proving the old certificate is rejected and the new certificate is accepted.
8. Inspect logs/metrics/audits to identify any replicas that have not picked up the revocation update.

**Self-check questions:**

- How does CRL differ from OCSP in distributing revocation status?
- Can OCSP `UNKNOWN` be treated as `GOOD`?
- In mTLS, which side checks the client and server certificates?
- Why does enabling TLS not imply revocation checking is enabled?
- Why must you verify the actual TLS provider instead of only setting JSSE properties?
- Does revocation automatically terminate an already-open HTTP/2 connection?
- How does TLS session resumption affect incident response?
- When must an intermediate/root CA be removed from the truststore?
- Why does a handshake failure not necessarily surface as an application gRPC status?
- What must be verified after revoking and rotating a certificate?

**Takeaway:** Certificate revocation requires both updating PKI status and forcing affected connections to re-authenticate. Check CRL/OCSP at the right trust managers on both mTLS client and server; explicitly define freshness and fail-open/closed policies; refresh channels/sessions after revocation; and verify the old certificate is rejected while the new certificate works. In Spring gRPC, configure according to your actual TLS provider/starter and test over the real production transport.
