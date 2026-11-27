# Certificate Rotation in Spring gRPC

In a **SPRING_GRPC** system, TLS certificates authenticate the server's identity and, when using mutual TLS (mTLS), the client's identity as well. Certificates expire, private keys can be compromised, or CAs can be replaced; therefore, an application needs a rotation process to replace certificates/keys and trust material without unplanned RPC disruption.

Rotation is more than copying a new file into a directory. You must coordinate the update order of trust stores, server/client certificates, existing HTTP/2 connections, and the rollout process. With Spring Boot, SSL bundles centralize key/trust material declarations; whether automatic reloading is supported depends on the specific consumer. This lesson focuses on the certificate lifecycle for gRPC servers/clients, safe rotation, hot-reload limitations, and post-change verification.

## 1. Certificate, private key, and trust chain

A gRPC connection over TLS typically involves the following components:

- **Leaf/server certificate:** confirms the server's identity. Its Subject Alternative Name (SAN) must match the hostname the client connects to.
- **Server private key:** proves the server owns the certificate. The key must match the public key in the certificate.
- **Intermediate CA:** links the server certificate to the root CA trusted by the client.
- **Client trust store:** contains the CAs or certificates permitted to authenticate the server.
- **Client certificate/private key:** required only when the server enforces mTLS.
- **Server trust store:** contains the CAs authorized to issue certificates for mTLS clients.

The TLS handshake verifies the chain, validity period, hostname, and certificate attributes appropriate to the role. For gRPC over HTTP/2, the transport must also negotiate HTTP/2 (ALPN `h2`) properly.

Distinguish two kinds of changes:

| Change | Components that must be updated |
| --- | --- |
| Renewing leaf certificate issued by the same CA | New certificate and private key on the endpoint; client trust usually stays unchanged |
| Replacing private key without changing CA | New certificate/key must match; clients still trust the old CA |
| Migrating to a new CA | Peer trust stores and endpoint certificate chains |
| Rotating client certificate in mTLS | Client key/certificate; server CA trust if the issuing CA changes |
| Compromised private key | Emergency key/certificate replacement, revocation per PKI policy, and removal of compromised trust/identity |

Do not confuse certificate rotation with token rotation. Certificates authenticate identity at the TLS handshake layer; tokens or credentials in metadata can be checked per RPC.

## 2. Declaring an SSL bundle for the gRPC server

Spring Boot provides SSL bundles to group a keystore, truststore, and TLS settings under a single name. Spring gRPC lets the Netty server use a bundle via `spring.grpc.server.ssl.bundle`.

PEM example for one-way server TLS:

```yaml
spring:
  ssl:
    bundle:
      pem:
        grpc-server:
          keystore:
            certificate: "file:/run/secrets/grpc/server-chain.pem"
            private-key: "file:/run/secrets/grpc/server.key"

  grpc:
    server:
      ssl:
        bundle: grpc-server
```

`server-chain.pem` typically contains the leaf certificate and intermediate chain in the format required by the server. The private key file must match the certificate. The secrets directory should be mounted with least-privilege read access for the process.

For mTLS, add trust material for client certificates and require client authentication:

```yaml
spring:
  ssl:
    bundle:
      pem:
        grpc-server:
          keystore:
            certificate: "file:/run/secrets/grpc/server-chain.pem"
            private-key: "file:/run/secrets/grpc/server.key"
          truststore:
            certificate: "file:/run/secrets/grpc/client-ca-bundle.pem"

  grpc:
    server:
      ssl:
        bundle: grpc-server
        client-auth: require
```

`client-auth: require` forces clients to present a certificate verified by the server against its trust material. For one-way TLS, mandatory client-auth does not need to be configured. The bundle name in `spring.grpc.server.ssl.bundle` must match the name under `spring.ssl.bundle`.

Configuration examples and supported properties depend on the Spring Boot, Spring gRPC, and server transport versions. Check the reference for your exact version before deploying.

## 3. Leaf certificate rotation without changing the CA

This is the simplest case: the CA issues a new leaf certificate for the same server identity, optionally rotating the private key at the same time.

Procedure:

1. Generate a new key pair in a secure key management system.
2. Request a new certificate from the CA with the right SAN, EKU, and chain.
3. Validate the new certificate, private key, and chain before introducing them at runtime.
4. Update the secret or mounted file that the server reads.
5. Reload/recreate the server or perform a rolling restart according to transport capabilities.
6. Establish a new TLS connection and verify the client receives the new certificate.
7. Monitor handshakes, authentication errors, and RPC status before deleting the old material.

If the CA has not changed and clients still trust that CA, reissuing the client trust bundle is usually unnecessary. Nevertheless, clients still verify the hostname and chain of the new certificate; an expired certificate, wrong SAN, or missing intermediate will still break the handshake.

Never overwrite the certificate and private key in a way that allows the process to read half of the old pair and half of the new pair. Stage the complete set of files in a staging directory and publish via an atomic operation supported by the OS or secret manager.

## 4. CA rotation with a trust overlap phase

Changing a CA is more complex because the server and clients must transition trust without creating a window where they distrust each other. The safe approach is trust overlap: during a transition window, peers trust both the old and new CAs.

Example temporary client trust bundle containing:

```text
-----BEGIN CERTIFICATE-----
... old CA ...
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
... new CA ...
-----END CERTIFICATE-----
```

Recommended rollout sequence:

1. **Widen trust first:** update clients to trust both the old CA and the new CA. For mTLS, update the server trust bundle to accept client certificates issued by either CA.
2. **Confirm the new trust has propagated:** verify that all replicas, workers, batch jobs, and external clients have received the new bundle.
3. **Switch the server certificate:** issue the server certificate from the new CA and roll out the server.
4. **Switch client certificates if using mTLS:** issue and deploy new client certificates while the server still accepts both old and new CAs.
5. **Observe the overlap period:** confirm handshakes succeed on new connections and no peers still depend on old certificates.
6. **Narrow trust:** only after all endpoints have migrated, remove the old CA from trust bundles and roll out the affected components again.

Do not remove the old CA immediately after replacing the server certificate. Old clients may still require the old CA, or another mTLS service may not have updated yet. Record the expiration timestamp of old certificates and the agreed overlap window.

## 5. Client certificate rotation in mTLS

With mTLS, the server verifies the client certificate during the TLS handshake. When rotating a client certificate:

- Issue the new client certificate with `clientAuth` EKU, organizational SAN/identity conventions, and an appropriate lifetime.
- If the CA is unchanged, server trust can remain untouched.
- If the CA changes, the server must trust the new CA before the client switches to the new certificate.
- Update the client-side secret and recreate connections/channels according to the application's mechanism.
- Verify the server extracts the expected new identity and authorization still maps that identity to the intended principal/role.

Certificates authenticate the client at the transport layer. Authorization by user, tenant, or method permissions may still require metadata/tokens and Spring Security. A valid certificate does not automatically grant all business permissions.

## 6. Spring Boot SSL bundle reloading and gRPC limitations

Spring Boot supports PEM SSL bundles with `reload-on-update`. When watched key material files change, the bundle can reload and emit an update event. Example:

```yaml
spring:
  ssl:
    bundle:
      pem:
        web-tls:
          reload-on-update: true
          keystore:
            certificate: "file:/run/secrets/web/fullchain.pem"
            private-key: "file:/run/secrets/web/privkey.pem"
```

The file watcher can use a quiet period to wait for all files to finish updating before reloading. This feature does not issue or renew certificates by itself; external tools such as Certbot, cert-manager, or a PKI system must do that.

**Important point for Spring gRPC:** Spring Boot documentation currently describes reloadable SSL bundles for compatible consumers such as Tomcat and Netty web servers. gRPC documentation confirms that native `grpc-netty` and `grpc-netty-shaded` can use SSL bundles, yet it does not guarantee that a native gRPC server swaps its serving certificate immediately upon bundle reload. Do not infer from Netty web server hot reload that the gRPC Netty server hot-reloads as well.

Therefore, for a native gRPC server:

- Check your exact starter/transport version and verify whether a supported server TLS context update mechanism exists.
- If there is no explicit guarantee, use a rolling restart or spin up a new server with the new bundle and shift traffic.
- Never merely replace files and assume rotation is complete; inspect the certificate over a brand-new TLS connection.
- If zero-restart hot reload is required, consider terminating TLS at a proxy/load balancer with a verified reload mechanism, or implementing a thoroughly tested custom server lifecycle.

If gRPC runs over a servlet container, TLS is usually managed by the web server. In that case, reload behavior depends on the container and how Spring Boot integrates SSL bundles; still verify it in practice.

## 7. Existing HTTP/2 connections and when new certificates take effect

gRPC typically maintains long-lived HTTP/2 channels and multiplexes many RPCs over a single TCP/TLS connection. Certificates are verified during the TLS handshake when the connection is established. Replacing a certificate on the server does not re-handshake in-flight RPCs on existing connections.

This leads to three consequences:

- RPCs on existing connections may continue running even after the server loads a new certificate.
- Clients only observe the new certificate when establishing a new TLS connection.
- A client channel created from an older SSL context may continue using old trust/key material for new connections it opens, depending on how the channel and transport were built.

To verify rotation, create a new channel or force a fresh connection to the endpoint. During server rollouts, drain old connections in line with graceful shutdown policies and RPC deadlines. Never conclude rotation succeeded merely because an RPC on an existing channel still returns a response.

## 8. Zero-downtime rolling rotation

With multiple replicas behind a load balancer, certificates can be rotated in waves:

1. Widen trust on clients and mTLS servers to accept both old and new CAs.
2. Update the secret for one replica.
3. Restart/recreate the replica with the new certificate.
4. Wait for readiness and perform a new TLS handshake against that replica.
5. Put the replica into service; proceed to the next replica.
6. After all replicas have switched, drain and close old connections.
7. Remove the old CA/certificate after the overlap period and confirm no consumers remain.

Make readiness succeed only once the server has bound its port, required services are registered, and essential dependencies are ready. Graceful shutdown must give in-flight RPCs enough time to finish; clients must still set finite deadlines.

If only one replica exists, use a parallel server or accept a planned maintenance window. Compromised-key rotation is an emergency: prioritize revoking the compromised identity per PKI procedures and accept an emergency rollout rather than extending an unsafe overlap.

## 9. Checking certificates before and after rotation

Before publishing, inspect subject, issuer, validity dates, and SAN:

```bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
```

Verify the chain against the intended CA:

```bash
openssl verify -CAfile ca-bundle.pem server.crt
```

Confirm that the certificate and private key match by comparing the public key extracted from each file. Use the tool appropriate for the key type; never print private keys to logs or shared terminals.

After rollout, open a fresh connection and verify TLS/HTTP2:

```bash
openssl s_client \
  -connect grpc.example.com:9090 \
  -servername grpc.example.com \
  -alpn h2 \
  -CAfile ca-bundle.pem \
  -verify_return_error \
  -showcerts
```

If the server has reflection enabled, you can check with grpcurl:

```bash
grpcurl -cacert ca-bundle.pem grpc.example.com:9090 list
```

With mTLS:

```bash
grpcurl -cacert server-ca.pem \
  -cert client.crt \
  -key client.key \
  grpc.example.com:9090 list
```

If reflection is disabled, invoke a method using the appropriate proto file/import path instead of `list`. Never pass flags that skip certificate validation in production checks; they hide trust and hostname errors.

## 10. Testing rotation in a test environment

An integration test should prove both success and failure paths:

- Valid server certificate and matching hostname: TLS handshake succeeds.
- Client trusts the wrong CA: handshake fails.
- Expired certificate or before `notBefore`: verification fails per policy.
- mTLS without a client certificate when required by server: connection rejected.
- Client certificate issued by an untrusted CA: handshake fails.
- After replacing the server certificate and creating a new channel: client verifies the new certificate.
- During CA overlap: client trusts both old and new CAs; after removing the old CA, the old certificate must no longer be accepted.

Use dedicated short-lived test certificates with private keys never reused in production. Synchronize test environment clocks to avoid false failures from clock skew.

A test running on the in-process transport does not test TLS because there is no network TLS handshake. You must use Netty/a real transport or an integration environment with a TLS listener.

## 11. Monitoring rotation and troubleshooting

Monitor these signals throughout a rotation:

| Signal | What to detect |
| --- | --- |
| Certificate expiration date | Certificate nearing expiry or renewal job failing to run |
| TLS handshake failures | Wrong chain, hostname mismatch, unpropagated CA, or key/cert mismatch |
| mTLS authentication errors | Missing or expired client certificate, or client CA not yet trusted |
| gRPC `UNAVAILABLE` | Closed connection, server not ready, or proxy/network issues |
| gRPC `UNAUTHENTICATED` | Identity/credential rejected; inspect both TLS and the authentication layer |
| Replica readiness | New replica has not bound listener or services are not ready yet |
| New connection success rate | Confirms clients are actually handshaking with the new certificate |

Log issuer, serial number, fingerprint, and certificate expiration at an operational level if policy permits; never log private keys, keystore passwords, or secret contents. Keep an audit trail of who issued certificates, deployment timestamps, and when the old CA was removed.

## 12. Practical rotation checklist

- [ ] Identify which certificate is being rotated: server, client, or CA.
- [ ] Verify SAN, EKU, chain, validity dates, and private key pair.
- [ ] Confirm secret storage location and process read permissions.
- [ ] Distribute new trust before switching certificates if the CA changes.
- [ ] Verify actual reload capability of your exact gRPC transport.
- [ ] If hot reload is unsupported, prepare rolling restarts or server replacement.
- [ ] Establish a new TLS connection to verify the new certificate.
- [ ] Drain old HTTP/2 connections and monitor in-flight RPCs.
- [ ] Keep overlap long enough for all clients/replicas to update.
- [ ] Remove the old CA only after confirming no consumers remain.
- [ ] Monitor handshake failures and expiry alerts after rollout.

### Key takeaway

**Certificate rotation is a controlled transition of identity and trust.** Renewing a leaf certificate under the same CA usually requires updating only the endpoint; changing the CA requires trust overlap before switching certificates. Spring SSL bundles help manage key/trust material, but that does not mean every gRPC server hot-reloads automatically. With native gRPC Netty, verify your exact version's capabilities or use rolling restarts/server replacement; then open a fresh connection, verify the chain/hostname/mTLS, and remove old trust only once all peers have migrated.

## References

- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot — gRPC and SSL support](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring gRPC — Server](https://docs.spring.io/spring-grpc/reference/server.html)
- [OpenSSL — x509](https://docs.openssl.org/3.5/man1/openssl-x509/)
- [OpenSSL — s_client](https://docs.openssl.org/3.5/man1/openssl-s_client/)
