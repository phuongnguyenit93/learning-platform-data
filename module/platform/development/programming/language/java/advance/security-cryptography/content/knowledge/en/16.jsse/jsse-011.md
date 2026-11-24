# 16.11. Diagnosing SSLHandshakeException, Certificate Errors, and No-Common-Configuration Failures

**`SSLHandshakeException` is not a single error.** It is a common Java exception class thrown when two sides cannot complete an SSL/TLS handshake. The cause may be **an untrusted certificate**, **an expired certificate or wrong hostname**, **no common TLS version**, **no cipher suite allowed by both sides**, **the server lacking a matching certificate/key**, **an mTLS client missing a certificate**, or **mismatches in signature schemes, named groups, SNI/ALPN, and security policy**.

Reading a single line `javax.net.ssl.SSLHandshakeException: handshake_failure` and concluding "the server has an SSL bug" lacks evidence. Conversely, seeing `PKIX path building failed` and "fixing" it with a `TrustManager` that accepts every certificate is a severe security flaw: the app may connect, yet it loses the ability to authenticate the real peer and becomes vulnerable to man-in-the-middle (MITM) attacks.

**Rule of this lesson:** always diagnose in order: **right endpoint → right handshake stage → right cause chain → right configuration on both sides → right trust/identity → only then choose a fix**. Diagnosing never means loosening security policy. Exception/alert names can vary by Java version, TLS version, provider, proxy, and whichever side detected the failure; combine multiple signals instead of guessing from one message.

## 1. Learning objectives

After completing this lesson, you will be able to:

- Distinguish **network/DNS/TCP** errors, **TLS handshake** errors, **certificate path/hostname** errors, and **post-handshake HTTP/application** errors.
- Understand `SSLHandshakeException`'s place in JSSE and how to trace `Throwable.getCause()`, `CertificateException`, `CertPathValidatorException`, `CertificateExpiredException`, and related types.
- Recognize "no common configuration" errors across **TLS protocol versions, cipher suites, signature algorithms, supported groups/key shares, certificate/key types, ALPN, SNI, and client authentication**.
- Enable scoped JSSE tracing with `-Djavax.net.debug=ssl,handshake,trustmanager,keymanager` and cert-path tracing with `-Djava.security.debug=certpath`; understand limits and sensitive-data risks in logs.
- Use `keytool` and Java APIs to inspect **keystore/truststore configuration, certificate chains, SAN, validity, KeyUsage, and EKU** without turning untrusted certificates into trusted roots.
- Use `SSLContext`, `SSLEngine`, and `SSLParameters` to inspect capabilities and configuration pre-handshake, without confusing **supported** with **enabled** and **negotiated**.
- Run a Java 17+ program with verifiable output, classify a failing certificate cause in a composite example, and identify two disjoint configurations.
- Build a security runbook for client/server/mTLS, reverse proxies, internal CAs, rotation, and dev/staging/production environments.

## 2. Reading from which side, at which layer?

Before editing TLS settings, identify **who detected the error** and **the specific transport hop**.

```text
Java client            Reverse proxy / API gateway             Java backend
-----------            ---------------------------             ------------
DNS / TCP connect -->
                      TLS connection #1 may terminate here
                      HTTPS request -->
                               TCP/TLS connection #2 -------->
                                                  JSSE handshake may occur here
                                                  Application logic / HTTP
```

A failure from the Java client to the gateway can happen before the backend ever sees a request. An mTLS failure between the gateway and another service might not appear in the Java client log. If HTTP returned `401`/`403`/`500` over a valid TLS connection, that is normally **not** evidence that the TLS handshake between those two hops failed.

Quick localization table:

| Symptom | Usually involved layer | Next question |
| --- | --- | --- |
| `UnknownHostException` | DNS/name resolution | Is the host name right? Do DNS/proxy/container differ across environments? |
| `ConnectException: Connection refused` | TCP connect | Are the port, server listener, and firewall open/running? |
| `SocketTimeoutException` on connect/read | Network or stalled handshake/read | At which phase did it time out? Was `ServerHello` received? |
| `SSLHandshakeException` | TLS handshake/authentication | What is the cause chain? Did the alert come from the peer or local JSSE? |
| `SSLProtocolException` | TLS protocol/framing | Which alert/version/record? Is non-TLS data arriving on the port? |
| `SSLPeerUnverifiedException` | Peer authentication in TLS context | Was a certificate/peer identity present and verified? |
| `CertificateException` / `CertPathValidatorException` in cause | Certificate trust/validity/policy | Missing CA, clock skew, wrong chain, or revocation? |
| HTTP `401/403` | Application auth/authz | TLS passed, yet token/role/tenant is invalid? |
| HTTP `502/503` from proxy | Proxy/upstream health | Did the proxy hit a TLS failure connecting to the backend? |

Do not assume every `SSLException` happens during initial handshaking: a connection may finish handshaking and later fail on records/EOF/alerts, session resumption, or I/O. Even handshaking itself can start on the first read/write depending on the API; to know the exact stage, inspect JSSE logs or instrument `SSLSocket.startHandshake()`/`SSLEngine`.

### 2.1. Exceptions and TLS alerts have different origins

For example:

```text
javax.net.ssl.SSLHandshakeException: Received fatal alert: handshake_failure
```

typically tells you Java **received an alert from the peer**, yet why the peer sent that alert requires inspecting **the peer's logs** or capturing the handshake. There is not enough evidence in this generic message alone to conclude whether it is a certificate or cipher-suite error.

Conversely:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed: ...
Caused by: sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
```

usually indicates the Java side **could not build a trust path** to an appropriate anchor. This is a message-format example, **not a standardized contract**; internal `sun.security...` classes can change, so never import or depend on them in code.

**Always record:** actual host/port, TLS termination point, Java/JDK version, provider, configured truststore/keystore paths, expected hostname, timestamp, full vs. resumed handshake, and the **first** root-cause message rather than reading only hundreds of cascading lines afterward.

## 3. TLS handshake stages help narrow down failures

A typical certificate-based TLS 1.3 handshake:

```text
Client                                                  Server
------                                                  ------
ClientHello (supported_versions, suites, SNI,
             key_share/groups, sig_algs, ALPN) -------->
                                        <--------------- ServerHello
                                        <--------------- EncryptedExtensions
                                        <--------------- Certificate
                                        <--------------- CertificateVerify
                                        <--------------- Finished
Client validates certificate path, hostname and
handshake authentication; key schedule finishes
Finished ---------------------------------------------->
              <====== encrypted application data ======>
```

**Conceptual diagram:** handshakes can differ with PSK resumption, mutual TLS, `HelloRetryRequest`, or other policies. Not every TLS 1.3 connection includes `Certificate`/`CertificateVerify`, and many handshake messages after `ServerHello` are encrypted.

From this, deduce:

- **No `ServerHello` seen:** check whether `ClientHello` leaves the client, whether the server/port speaks TLS, whether a gateway/firewall blocks it, and whether protocol/version/suite/key-share overlap. The server may also abort early on SNI or cipher policy.
- **Reaches `Certificate` then fails:** focus on certificate chain, trust anchor, validity, SAN/hostname, algorithm constraints, key usage, revocation, and mTLS if applicable.
- **`CertificateVerify`/`Finished` fails:** may involve handshake signatures, private keys, transcripts/parameters, or implementation/proxy issues; inspect provider logs on the relevant side.
- **TLS `Finished` succeeds then HTTP errors:** do not touch the truststore to fix token/route/authorization bugs.
- **Client receives fatal alert after sending client certificate:** check the server's mTLS trust/certificate policy, not just the client's truststore.

### 3.1. Receiver-side or sender-side failure?

If the client logs `Received fatal alert: certificate_unknown`, the **server** may have rejected the mTLS client certificate; if the server logs similarly, the **client** may have rejected the server certificate. Identify which side sent the alert and at which handshake stage.

`handshake_failure`, `bad_certificate`, `certificate_unknown`, `unknown_ca`, `protocol_version`, and `no_application_protocol` are useful alerts/concepts, yet **there is no strict one-to-one mapping from an alert to one root cause**. An implementation may emit a generic alert for several local failures.

## 4. Reading `SSLHandshakeException` causes systematically

Never rely on a single `contains("PKIX")` check as the basis for editing an environment. Separate:

1. **Top-level exception:** Java class name and bounded message.
2. **Cause chain:** walk `getCause()` down to the deepest cause, including `CertificateException`/`CertPathValidatorException`.
3. **TLS debug sequence:** `ClientHello`, `ServerHello`, certificate, trust validation, alert/handshake failure.
4. **Peer-side logs:** which certificates/keys does the server hold, does it require a client cert, did it reject a suite/group/ALPN?
5. **Config provenance:** JVM flags, env vars, effective truststore/keystore, framework overrides, reverse proxies.
6. **Security policy:** does the fix preserve peer identity and permitted algorithms?

A structure for recording an incident without logging secrets:

```text
incidentId: 6ef4f9c2          # non-sensitive example ID
direction: Java client -> api.example.com:443
TLS termination: gateway-1
JDK runtime: Java 17 / provider SunJSSE
expected service identity: api.example.com
TLS configured: versions [TLSv1.3, TLSv1.2]
stage: received Certificate, path validation failed
top exception: SSLHandshakeException
cause category: CERT_PATH_UNTRUSTED
observed result: fail closed
last known good: deployment/config revision X
```

Never put `Authorization` headers, cookies, passwords, private keys, session tickets, application payloads, or full TLS secrets into tickets/logs just to "have enough data." The strongest diagnostics rely on **metadata, policies, public certificate fields, and cause classes**, without exporting secrets.

### 4.1. Separating root cause from cascading symptoms

A debug line like `Fatal (CERTIFICATE_UNKNOWN)` right after JSSE logs `PKIX path building failed` is usually a **consequence of the trust validation failure**. Do not look only at the final `Fatal` line. Likewise, `Broken pipe` on the server after the client already rejected the certificate is not evidence that the server has bad ciphers.

An effective workflow:
- Record the **first fatal event** and **the exception that triggered it**.
- Correlate timestamps/logs from **both sides** via correlation IDs or timestamps.
- Verify whether the failure repeats across multiple endpoints or only one host/SNI.
- Compare against a previously working configuration revision rather than copying keystore/truststore files arbitrarily.
- Change one configuration group at a time and re-run negative tests.

## 5. Group 1 — Certificate and trust-path errors

### 5.1. `PKIX path building failed`

Common form:

```text
SSLHandshakeException: PKIX path building failed
  ...
  unable to find valid certification path to requested target
```

Likely causes:
- The client **does not trust** the root CA or required intermediate for the server certificate.
- The server failed to send all required intermediate certificates, preventing path building.
- The Java runtime/container uses a different truststore than the OS/browser; a CA trusted by a browser is not necessarily trusted by the JDK.
- The app points to the wrong truststore file, or the truststore is empty/unreadable.
- A TLS inspection proxy/corporate gateway issues certificates from an internal CA not yet trusted by the app per policy.
- The chain has an issuer mismatch, signature mismatch, policy constraints failure, or disallowed algorithm.
- Older JDK/CA bundle unsuitable for new PKI, or differences between staging and production.

**Right remediation:** identify the **actual CA issuer/chain**, verify the public CA/enterprise CA source via trusted administrative channels, and fix the server chain or update the truststore **under control**. Never "import the certificate just received from the server into the truststore" unverified; doing so can turn an attacker's certificate into a trusted root.

### 5.2. `trustAnchors parameter must be non-empty`

This usually means the **trust anchor set passed to PKIX is empty** or validator configuration lacks trusted CAs. Check:
- Does the truststore file exist and is it readable?
- Store type: PKCS12/JKS/PKCS11 per policy and provider?
- Are the truststore password/settings correct?
- Does the file actually contain approved certificate entries?
- Did code initialize `TrustManagerFactory` with a fresh empty `KeyStore` and accidentally apply it to all HTTPS connections?
- Did the container mount the truststore properly into the runtime?

**Never** fix this by adding an unverified root or building a `TrustManager` that skips checks.

### 5.3. Expired or not-yet-valid certificates

```text
java.security.cert.CertificateExpiredException
java.security.cert.CertificateNotYetValidException
```

The certificate or a chain element has a `notBefore/notAfter` window incompatible with the check time. Verify:
- UTC/clock on JVM/host/container and NTP sync.
- Validity windows of both leaf and intermediate certificates.
- Whether a service is still serving an old certificate after rotation.
- Whether different nodes behind a load balancer hold different certs.
- Whether certificate policy mandates revocation/short-lived credentials.

**Never fix by setting the system clock wrong or disabling `checkValidity()` in production.** Synchronize clocks and renew/roll out certificates properly.

### 5.4. SAN or hostname mismatch

Examples:

```text
No subject alternative DNS name matching api.example.com found
No name matching api.example.com found
No subject alternative names present
```

Exact message varies by provider. If the app calls `api.example.com` while the cert lists only `db.example.com` or has invalid CN/SAN, it must **reject** even when the CA chain is trusted.

How to check:
1. Confirm the expected hostname from a trusted URL/service discovery source.
2. Inspect the corresponding DNS/IP `SubjectAlternativeName` entries.
3. Check whether the client sends the right SNI and whether the server virtual host selects the right cert.
4. For IP literals, check `iPAddress` SANs and matching policy; do not assume a DNS SAN suffices.
5. Fix the certificate/SNI/routing per reality; never disable hostname verification.

If an app connects via an internal IP while the certificate holds only public DNS names, the fix is to **connect to the certified name** with proper DNS/routing or issue a valid certificate for the desired identity—never install an always-true `HostnameVerifier`.

### 5.5. Valid certificate chain signatures yet policy failure

Cases:
- `BasicConstraints: CA=false` on a certificate used as an intermediate CA.
- CA missing `keyCertSign` when required by policy/KeyUsage.
- Leaf certificate has wrong `ExtendedKeyUsage`, e.g., `clientAuth` only used for `serverAuth`.
- Certificate contains an unrecognized/unsatisfied critical extension.
- `NameConstraints` restricts names inconsistently.
- Signature/key algorithm too weak under `jdk.certpath.disabledAlgorithms` and runtime algorithm constraints.
- Fails revocation policy (CRL/OCSP) when required.

Calling `cert.verify(issuerPublicKey)` checks only the **signature on the certificate**; it is not a complete PKIX trust validation system. Never use a standalone `verify` call to mark a cert trusted.

### 5.6. Revocation/OCSP/CRL

A certificate may be **unexpired** with valid signatures yet **already revoked**. Check PKIX/trust manager/OCSP policy, responder reachability, CRL freshness, stapling, timeouts, and fail-closed vs. soft-fail per system rules. Never assume "if OCSP errors, just turn off revocation." Some deployments use short-lived certificates and rotation to replace or supplement revocation checks; every choice needs a threat model.

## 6. Truststore and keystore: two different roles

| Store/config | What does it hold? | Used for what? | If misconfigured |
| --- | --- | --- | --- |
| **Truststore** | Policy-trusted CAs/anchors or certificates | **Verifying the peer's certificate** | `PKIX path building failed`, unknown CA, empty trust anchors |
| **Keystore / key entry** | This side's own private key + matching certificate chain | **Proving one's own identity** when handshake requires | `No available authentication scheme`, missing client cert, server cannot present cert |
| **JDK security policy** | Protocol/algorithm constraints | Blocks weak algorithms or keys | No common config despite suite appearing in supported list |
| **SSLContext/JSSE config** | KeyManagers, TrustManagers, SecureRandom, protocol state | Creates TLS engines/sockets | Wrong store used, default overridden, missing key |
| **SNI/endpoint config** | Target service identity to connect to | Selects virtual host/cert, verifies hostname | Wrong cert, hostname failure |

### 6.1. An HTTPS client normally needs only a truststore

If Java is an **HTTPS client**, it needs to trust the server certificate; it normally does not need its own client certificate unless the server requires **mutual TLS (mTLS)**.

- Client truststore: CAs to verify the server certificate.
- Client keystore: client private key/cert **if** mTLS.
- Server keystore: server private key/cert.
- Server truststore: CAs to verify client certificates **if** mTLS.

"I imported the CA into the keystore and the client still says PKIX" can happen from **importing into the store playing the wrong role** or because the app uses a different file.

### 6.2. Default truststore vs. custom truststore

In SunJSSE/JDK, default trust material typically comes from JSSE truststore configuration—e.g., `javax.net.ssl.trustStore` if set, or runtime default locations such as `jssecacerts`/`cacerts` depending on provider and configuration. **Never assume the JVM automatically reads the OS certificate store** or another JDK's file.

A wrong path in `-Djavax.net.ssl.trustStore=/app/config/truststore.p12` can result in unexpected trust behavior; directly verify file existence, contents, read permissions, and which runtime is executing.

When using a custom `SSLContext`:
- `TrustManagerFactory.init(customTrustStore)` replaces the anchor source for that context; it does not automatically "merge" all OS/JDK CAs.
- `KeyManagerFactory.init(keyStore, ...)` grants the ability to present this side's certificate/key.
- `SSLContext.init(keyManagers, trustManagers, secureRandom)` combines those decisions.
- A framework may build its own `SSLContext` and ignore JVM-wide properties; inspect the actual context of each HTTP client.
- When needing both internal and public CAs, manage trust policy explicitly rather than arbitrarily adding untrusted CAs.

### 6.3. Distinguishing key password from store password

`KeyStore.load(...)` uses the store password, while a private key entry may have a distinct key password/PKCS12 setting depending on provider. Trying to fix "cannot read private key" by passing a truststore password instead of the key password without understanding the structure can still fail.

Never pass production passwords in command-line flags easily exposed in process lists, shell history, or CI logs. Use secret managers and approved deployment APIs/mechanisms; enforce file permissions and auditing.

## 7. Group 2 — No common TLS configuration

Even when certificates are trusted, both sides must **negotiate** a compatible TLS version, key exchange algorithm, signature, and cipher suite.

### 7.1. No common protocol version

Client enables only `TLSv1.3`, server enables only `TLSv1.2`:

```text
Client enabled protocols: [TLSv1.3]
Server enabled protocols: [TLSv1.2]
Intersection: EMPTY
Result: handshake cannot select common TLS version
```

You may see `protocol_version`, `handshake_failure`, `No appropriate protocol`, or another message. Do not assert that a single identical message appears across all providers.

Key distinctions:
- **Supported**: the provider is capable of supporting it if policy allows.
- **Enabled**: the list configured for an instance, e.g., `SSLEngine.getEnabledProtocols()`.
- **Negotiated**: the version chosen **after the handshake**, observable via `SSLSession.getProtocol()`.
- **Disabled by security policy**: present in the provider yet blocked via settings like `jdk.tls.disabledAlgorithms`.

If a server supports only TLS 1.0/1.1, never enable those weak protocols in a production client just to "get connected." Upgrade the server/gateway and uphold current policy.

### 7.2. No common cipher suite

```text
Client enabled suites: [TLS_AES_128_GCM_SHA256]
Server enabled suites: [TLS_CHACHA20_POLY1305_SHA256]
Intersection: EMPTY
```

This is an **intentionally disjoint** configuration example. Even before checking whether a specific provider supports a suite or security policy permits it, if both sides configure only the sets above, there is no common suite to select.

Real-world cases:
- Client/server share no permitted suite.
- A suite overlaps on paper, yet `jdk.tls.disabledAlgorithms` or the provider blocks it.
- A TLS 1.2 suite requires a certificate/key-exchange type absent from the server keystore.
- A security gateway drops suites/curves per policy while an old service runtime keeps legacy config.

### 7.3. TLS 1.3 trait: the suite doesn't tell the whole handshake story

A TLS 1.3 cipher suite like `TLS_AES_128_GCM_SHA256` or `TLS_AES_256_GCM_SHA384` describes mainly the AEAD cipher and HKDF hash. It **does not specify** whether the server uses an RSA certificate, ECDSA certificate, Ed25519 signature, or which ECDHE group.

Therefore, even after confirming a shared cipher suite, still check:
- **Signature schemes:** `signature_algorithms` from the client and algorithms supported by the signer/server certificate.
- **Supported groups/named groups:** X25519, P-256, P-384, etc. per policy.
- **Key shares:** a `HelloRetryRequest` may occur when another group is needed; if no group overlaps, the handshake fails.
- **Certificate/key algorithm:** server has a private key and certificate chain matching the selection.
- **ALPN:** whether application protocols `h2`/`http/1.1` or another profile are permitted by both sides.
- **SNI:** server name used to pick the right certificate/vhost/backend.

Never explain every TLS 1.3 failure as "disjoint cipher suites" when the cause may be **signatures or key shares**.

### 7.4. `No available authentication scheme`

JSSE/peer may report errors such as:

```text
No available authentication scheme
No available certificate corresponding to the SSL cipher suites...
```

Do not rush to conclude an untrusted CA. On the **server side**, this usually hints that no certificate/private key matches the algorithms/schemes accepted by the peer, or the key manager failed to choose a matching alias.

Check:
1. Did `KeyManagerFactory` load the right keystore?
2. Does the keystore contain a **`PrivateKeyEntry`** rather than only a **`trustedCertEntry`**?
3. Do the certificate chain and private key belong together?
4. Are the RSA/EC/EdDSA key type, signature schemes, and KeyUsage/EKU supported by JSSE and allowed by policy?
5. Which virtual host is SNI requesting, and how does the key manager pick an alias?
6. Does the Java provider support the matching key and signature algorithms?
7. Is the client demanding a configuration supporting only a scheme the server lacks?

On the **mTLS client side**, there may also be no client certificate matching the server's `CertificateRequest`. Inspect the client's `keymanager` trace and the server's trust policy.

### 7.5. `Handshake failure` can still be an ALPN/SNI issue

- Servers use SNI to select certificates or routing; if the client omits or sends the wrong hostname, the server may return a default certificate **not matching the SAN** or reject.
- ALPN negotiates application protocols like `h2` or `http/1.1`. If policy requires a protocol with no overlap, the server may send an alert like `no_application_protocol`.
- An HTTP server may accept the TLS handshake and then misinterpret the application protocol; do not confuse HTTP/2 framing errors with PKIX.
- A proxy may terminate TLS and open upstream requests with different SNI/ALPN than the origin endpoint; inspect config at the right hop.

## 8. Group 3 — mTLS: client-side certificate errors

When the server requires a client certificate:
- The server signals a certificate request per the active TLS handshake.
- The client `KeyManager` must locate a cert/private key matching issuers/signature schemes/policy.
- The client presents the certificate and performs the corresponding handshake proof.
- The server `TrustManager` checks the certificate chain/`clientAuth` constraints.
- The application must still map the certificate identity to principal/tenant/role and perform authorization.

### 8.1. Common scenarios

| Symptom | Side to inspect | Likely cause |
| --- | --- | --- |
| Server reports `certificate_required` | Client and server | Client sent no certificate when required by server |
| Server reports `unknown_ca` or cert-path error | Server trust config | CA issuing client cert is not trusted by the server |
| Client logs `Received fatal alert: bad_certificate` | Server decision | Client certificate/usage/chain fails server policy |
| Client keymanager selects no alias | Client | No matching `PrivateKeyEntry`/issuer/key type |
| Handshake passes yet API returns 403 | Application server | Certificate identity lacks permission; not a PKIX error |
| Some nodes pass mTLS, others fail | Gateway/backend fleet | Truststore, CA rollout, or cert rotation out of sync |

**A Java client's truststore for verifying the server** differs from **the server's truststore for verifying clients**. Importing the client CA into the client's own truststore usually does nothing to help the server trust the client certificate.

### 8.2. Having a cert does not mean the server accepts it

Check:
- Complete certificate chain and server-accepted issuer.
- Private key matching the certificate.
- `clientAuth` EKU, KeyUsage, and validity.
- Certificate DN/SAN mapping to an authorized workload identity.
- Server-side CA/root and revocation policy.
- TLS signature algorithms/group lists/certificate request context.

Never enable mTLS by disabling server validation just to let the client connect; that turns an authenticated client/server into a connection vulnerable to MITM.

## 9. JSSE debugging: flipping the right switches, reading the right stage

This is the primary tool for diagnosing Java TLS in controlled test environments.

### 9.1. JSSE debug flags

Command-line example (substitute your application class name):

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager,keymanager MyTlsApp
```

Common debug categories:
- `ssl`: general SSL/TLS debugging.
- `handshake`: handshake messages and negotiation flow.
- `trustmanager`: trust manager and certificate validation trace per implementation.
- `keymanager`: local key/certificate selection for this endpoint.
- `session` or `sessioncache`: helps investigate resumption/caching when needed.
- `record`: TLS record info; be mindful of what is logged.

To list options supported by the **running JDK**, you can run:

```bash
java -Djavax.net.debug=help MyTlsApp
```

Depending on the provider, this mode may display help and exit the application. Do not treat log formatting as a stable API: Oracle notes diagnostic options may change and providers other than SunJSSE may not support them identically.

**Warning:** never enable `all`, `plaintext`, `packet`, or byte-dump modes by default on production systems with real data. Traces can expose certificate metadata, session identifiers, handshake contents, hostnames/tenants, and other sensitive info; enforce access controls, retention, and redaction.

### 9.2. CertPath debug flags

When encountering `PKIX path building failed` or algorithm/chain constraints:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath MyTlsApp
```

`java.security.debug=certpath` emits traces related to PKIX path building/validation in the Sun security provider when applicable. JDK versions may vary in format and verbosity. There is no need to enable `certpath` for errors like TCP refused or ALPN mismatches.

### 9.3. How to read a JSSE trace effectively

A reading sequence:

1. **`ClientHello`**: offered TLS versions, cipher suites, `signature_algorithms`, `supported_groups`, `key_share`, SNI, and ALPN.
2. **`ServerHello`** if present: chosen version/suite, key share/PSK, or `HelloRetryRequest`.
3. **`Certificate`/`CertificateRequest`** (if present): server chain, mTLS client cert request.
4. **Trust/key manager logs**: loaded CA anchors, selected alias/certificate; path failure/hostname mismatch.
5. **First fatal alert**: alert name, sender/receiver, and cause.
6. **Application data**: if reached, initial TLS likely succeeded; check errors at other layers.
7. **Cross-check server-side trace**: especially when the client sees only `Received fatal alert: handshake_failure`.

Never paste full debug logs into public emails/tickets. Extract only the fields needed to isolate the failure, redacting tokens/cookies, personal info, secrets, and unnecessary key shares/debug bytes.

### 9.4. Before increasing debug verbosity

Check simple, low-impact items first:
- `java -version` and the actual JDK running in the container.
- URL/hostname/port, TLS termination point, proxies, gateway routes.
- Startup flags like `javax.net.ssl.trustStore`/`keyStore`/`https.protocols`/`jdk.tls.client.protocols`, taking care which flag applies to which API/provider.
- Security properties such as `jdk.tls.disabledAlgorithms` and `jdk.certpath.disabledAlgorithms`.
- Whether the truststore/keystore file is actually readable, permissions, cert chain, and alias.
- Time synchronization, certificate expiration, SAN, certificate rotation status.
- Server version/certificate policy, mTLS requirements, and SNI/ALPN selection.

Some properties live in the JDK's `java.security` file or are overridden via JVM flags; never assume from a dev machine that a production container shares the exact same security policy.

## 10. `keytool`: inspecting certificates and stores without breaking the trust model

The following commands are for **reading/inspecting**, not blindly adding CAs or weakening TLS.

### 10.1. Observing a server certificate

```bash
keytool -printcert -sslserver api.example.com:443 -rfc
```

This command can display the certificate presented by the server on a connection to host/port, depending on network and tooling. **Printing a certificate does not mean it is trusted**; verify chain/trust anchor/expected hostname using a standard TLS client. For complex virtual hosts, verify SNI/tooling compatibility to make sure you see the right certificate.

### 10.2. Reading a certificate file

```bash
keytool -printcert -file server-certificate.pem
```

Inspect:
- Subject/Issuer.
- Validity Not Before/Not After.
- Subject Alternative Name (DNS/IP names).
- KeyUsage, ExtendedKeyUsage.
- BasicConstraints/CA flag.
- SHA-256 fingerprint **after verifying a trusted source**.

A fingerprint only helps comparison when you have a reference value from another authenticated channel. If an attacker hands you a certificate plus a fingerprint computed from that very certificate over an untrusted channel, comparing them proves no ownership.

### 10.3. Inspecting a truststore (e.g., PKCS12)

```bash
keytool -list -v -keystore truststore.p12 -storetype PKCS12
```

This command may prompt interactively for a password. Verify certificate entries/issuers and whether the right approved CA is present. **Do not** hastily pass passwords on command lines or into CI logs; paths here are merely examples.

### 10.4. Inspecting an identity keystore

```bash
keytool -list -v -keystore identity.p12 -storetype PKCS12
```

What to look for:
- Desired alias has type `PrivateKeyEntry`, not just `trustedCertEntry`.
- Certificate chain accompanying the private key.
- Key algorithm/length, signature, EKU/KeyUsage, SAN, and validity.
- For mTLS, whether issuer/key type matches the server's `CertificateRequest`.
- Whether the service is reading that exact keystore, alias, and key password.

**Do not** print/export private keys into logs/tickets to check "if the key is right." To verify key matching, use controlled APIs/providers, the certificate public key, and a safe signing test in an authorized environment.

## 11. Java 17+: offline program distinguishing capabilities and disjoint configurations

The first example **opens no sockets, sends no real TLS ClientHello, and requires no server**. It is designed to verify easily confused points:

1. `SSLContext`/`SSLEngine` exposes **supported protocols** from the provider.
2. `SSLParameters` sets `EndpointIdentificationAlgorithm("HTTPS")` in client mode. This **requests hostname verification enforcement during a corresponding TLS handshake**, rather than proving a host was verified in an offline demo.
3. Two simulated TLS protocol sets **have no intersection**, contrasted with a pair that intersects.
4. Two simulated cipher-suite name sets **have no intersection**. That intersection is a **necessary condition**, insufficient on its own to guarantee a real handshake succeeds.
5. A synthetic `SSLHandshakeException` wrapping `CertificateExpiredException` is classified by **cause class**, rather than guessing from message strings alone.
6. Never claims "TLS is fixed" without a remote server or full handshake.

Create **`JsseHandshakePreflightDemo.java`**:

```java
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.CertPathValidatorException;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;

public class JsseHandshakePreflightDemo {
    static boolean overlap(String[] first, String[] second) {
        for (String a : first) {
            for (String b : second) {
                if (a.equals(b)) {
                    return true;
                }
            }
        }
        return false;
    }

    static String safeCauseCategory(Throwable problem) {
        for (Throwable current = problem;
                current != null;
                current = current.getCause()) {
            if (current instanceof CertificateExpiredException) {
                return "CERTIFICATE_EXPIRED";
            }
            if (current instanceof CertificateNotYetValidException) {
                return "CERTIFICATE_NOT_YET_VALID";
            }
            if (current instanceof CertPathValidatorException) {
                return "CERT_PATH_INVALID";
            }
            if (current instanceof CertificateException) {
                return "CERTIFICATE_ERROR";
            }
        }
        return "OTHER_HANDSHAKE_ERROR";
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLEngine engine = context.createSSLEngine(
                "api.example.invalid", 443
        );
        engine.setUseClientMode(true);

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);

        System.out.println("Supports TLSv1.2: "
                + Arrays.asList(engine.getSupportedProtocols())
                        .contains("TLSv1.2"));
        System.out.println("Supports TLSv1.3: "
                + Arrays.asList(engine.getSupportedProtocols())
                        .contains("TLSv1.3"));
        System.out.println("Client mode: " + engine.getUseClientMode());
        System.out.println("Endpoint identification: "
                + engine.getSSLParameters()
                        .getEndpointIdentificationAlgorithm());

        System.out.println("Disjoint example protocols overlap: "
                + overlap(
                    new String[]{"TLSv1.3"},
                    new String[]{"TLSv1.2"}
                ));

        System.out.println("Compatible example protocols overlap: "
                + overlap(
                    new String[]{"TLSv1.3", "TLSv1.2"},
                    new String[]{"TLSv1.2"}
                ));

        System.out.println("Disjoint example suites overlap: "
                + overlap(
                    new String[]{"TLS_AES_128_GCM_SHA256"},
                    new String[]{"TLS_CHACHA20_POLY1305_SHA256"}
                ));

        SSLHandshakeException sample =
                new SSLHandshakeException("redacted");
        sample.initCause(
                new CertificateExpiredException("test fixture")
        );
        System.out.println("Synthetic failure category: "
                + safeCauseCategory(sample));

        System.out.println("Real handshakes performed: 0");
    }
}
```

Compile and run with JDK 17+:

```bash
javac JsseHandshakePreflightDemo.java
java JsseHandshakePreflightDemo
```

Verified stdout on a SunJSSE JDK providing TLSv1.2 and TLSv1.3 (protocol support results may vary if using a special provider):

```text
Supports TLSv1.2: true
Supports TLSv1.3: true
Client mode: true
Endpoint identification: HTTPS
Disjoint example protocols overlap: false
Compatible example protocols overlap: true
Disjoint example suites overlap: false
Synthetic failure category: CERTIFICATE_EXPIRED
Real handshakes performed: 0
```

### 11.1. Why is this test reliable yet bounded?

- `engine.getSupportedProtocols()` returns versions supported by the provider; it **does not guarantee** all are enabled or permitted after security policy. Use `getEnabledProtocols()` to inspect an engine's specific settings.
- `setEndpointIdentificationAlgorithm("HTTPS")` only sets policy on an engine. Because no handshake occurs, the program has not verified a real certificate or hostname.
- `overlap(...)` operates on the **given strings**, without considering certificates, X25519/P-256 groups, signature schemes, trust anchors, or disabled algorithms. **Overlap is necessary, not sufficient.**
- `SSLHandshakeException sample` is constructed **deliberately from a test fixture**, not a real SSL failure. `CERTIFICATE_EXPIRED` classification illustrates walking the cause chain; in production, certificate failures also require checking certs/chains/peer logs.
- Real debugging may need to inspect `SSLProtocolException`, `SSLException`, `CertPathBuilderException`, provider-specific classes, and peer alerts; `safeCauseCategory` is not an exhaustive classifier for all causes.
- Prints no bytes of session secrets, private keys, raw certificate chains, or user data; config strings are all public synthetic examples.

### 11.2. Why not auto-edit suites when `overlap=false`?

Suppose the client allows only TLS 1.3 and the server supports only TLS 1.2. The right step is asking:
1. Why doesn't the server support TLS 1.3? Can the runtime/gateway be upgraded?
2. If organizational policy still allows TLS 1.2, do both sides share at least one secure suite/group/signature?
3. If the server offers only banned protocols/suites, **never re-enable weak configs** just to connect.
4. Whenever changing protocols, re-run certificate validation, mTLS, ALPN/HTTP version, and negative tests.

Similarly, seeing `overlap=true` is no reason to skip truststore/hostname checks; it only means a version could be negotiated, not yet that authenticated TLS exists.

## 12. Java 17+: live-connection program when observing a real handshake

The second example **requires network access and an HTTPS endpoint you are authorized to test**. It demonstrates how to:
- Connect TCP with a connect timeout.
- Wrap the socket as an `SSLSocket` using JSSE.
- Set **HTTPS endpoint identification** for the requested host before the handshake.
- Call `startHandshake()` explicitly.
- Distinguish `SSLHandshakeException` from other `IOException`s without bypassing trust.
- Print **only controlled metadata**, never raw certificates/secrets.

File **`JsseLiveProbe.java`**:

```java
import java.net.InetSocketAddress;
import java.net.Socket;
import java.io.IOException;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

public class JsseLiveProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java JsseLiveProbe <hostname> <port>");
            return;
        }

        String host = args[0]; // Intended DNS identity from trusted configuration.
        int port = Integer.parseInt(args[1]);

        SSLContext context = SSLContext.getDefault();
        try (Socket tcp = new Socket()) {
            tcp.connect(new InetSocketAddress(host, port), 5000);
            tcp.setSoTimeout(5000);

            try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
                    .createSocket(tcp, host, port, true)) {
                tls.setUseClientMode(true);
                tls.setSoTimeout(5000);

                SSLParameters parameters = tls.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                tls.setSSLParameters(parameters);

                tls.startHandshake();
                System.out.println("Handshake: OK");
                System.out.println("Protocol: " + tls.getSession().getProtocol());
                System.out.println("Cipher suite: "
                        + tls.getSession().getCipherSuite());
            }
        } catch (SSLHandshakeException failure) {
            System.err.println("Handshake: FAILED (see controlled JSSE trace)");
            System.err.println("Exception type: "
                    + failure.getClass().getSimpleName());
            throw failure; // In a lab; production API should map to safe error.
        } catch (IOException networkOrTls) {
            System.err.println("Connection/I-O failure: "
                    + networkOrTls.getClass().getSimpleName());
            throw networkOrTls;
        }
    }
}
```

Example lab command:

```bash
javac JsseLiveProbe.java
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath JsseLiveProbe api.example.com 443
```

**No fixed stdout**: certificate, TLS protocol, cipher suite, DNS/network/proxy, and truststore depend on the endpoint/environment. `api.example.com` is merely an illustrative name and must be replaced with a hostname you are actually authorized to test. Never run the program against unmanaged/unauthorized endpoints or use it for out-of-scope network scanning.

**Limitations:** this is a basic HTTPS TLS probe; it sends no HTTP request and is not designed for proxy authentication, SNI overrides, custom mTLS credentials, ALPN/HTTP2, or custom truststores. Production HTTPS client libraries like `java.net.http.HttpClient` are usually more suitable and can handle endpoint identification/trust policies per config. If you must use a custom `SSLSocket`, never forget to explicitly enable hostname verification as shown above.

### 12.1. When no certificate error appears

If `startHandshake()` succeeds, that proves a TLS connection was created per the active context's trust/identity policy; do **not** conclude the application principal is authorized to access resources. HTTP 401/403 belongs to the subsequent authentication/authorization layer.

If `startHandshake()` fails right before certificates, it does not mean the certificate is "good" or "bad" — it may never have reached that step due to a protocol/suite/SNI mismatch.

## 13. Practicing error classification by symptom

| Message/error group | Priority hypothesis | Check to confirm | Never do |
| --- | --- | --- | --- |
| `PKIX path building failed` | Missing CA/path, wrong truststore, missing intermediate | JSSE trustmanager + certpath, actual truststore, chain | Trust-all / auto-import root from peer |
| `trustAnchors must be non-empty` | Empty truststore / wrong file | File path, store type, entries, custom SSLContext | Accept any certificate |
| `CertificateExpiredException` | Expired leaf/intermediate, clock skew | NTP time, full chain validity, cert rollout | Fake the clock, skip validity |
| `CertificateNotYetValidException` | Future/notBefore certificate, clock skew | Clock/timezone & cert validity | Skip time checks |
| `No subject alternative ...` | Endpoint identity mismatch | Requested host, SAN, SNI, vhost | Always-true `HostnameVerifier` |
| `Received fatal alert: unknown_ca` | One peer does not trust the other's CA | Read logs on both sides, mTLS direction | Blindly edit client truststore |
| `bad_certificate` | Peer rejected the certificate | Key usage, chain, EKU, validity, trust policy | Turn off client auth to "pass" |
| `certificate_required` | Missing client certificate in mTLS | Server `CertificateRequest`, client keymanager alias | Add CA on the wrong side |
| `No available authentication scheme` | No matching private key/cert/signer | Keymanager, `PrivateKeyEntry`, sig schemes, SNI | Enable all weak ciphers |
| `No cipher suites in common` | Disjoint suites or blocked by constraints | Config on both sides, TLS version, JDK policy | Enable RC4/3DES/NULL |
| `No appropriate protocol` | No common valid TLS version | Enabled protocols, disabled algorithms | Enable SSLv3/TLS1.0 |
| `Received fatal alert: protocol_version` | Peer rejected the version | `ClientHello`/`ServerHello` and server TLS policy | Arbitrarily downgrade |
| `no_application_protocol` | ALPN mismatch | `h2`/`http/1.1`, gateway/app policy | Swap certificates without reason |
| Generic `handshake_failure` | Many possibilities, including SNI/keys/algorithms | JSSE + peer traces by handshake stage | Conclude from a single line |
| `Socket closed`/EOF after `ClientHello` | Peer/network drop, non-TLS listener, TLS policy | TCP path, load balancer logs, server listener | Swap truststores without checking |
| TLS success then HTTP `403` | App authorization | Access token, roles, tenant/resource | Delete TLS session or disable validation |

The table above is a **diagnostic heuristic**, not a guaranteed message→cause rule across all JDKs, providers, and TLS versions.

## 14. Step-by-step investigation examples

### 14.1. Case A: Java client fails yet browser succeeds

Scenario:
- Java `HttpClient` calls `https://api.example.com` and throws `SSLHandshakeException` with `PKIX path building failed`.
- A browser on a laptop opens the URL fine.

Steps:
1. Is Java running inside a container with a different truststore/JDK than the browser?
2. Is the browser using the OS trust store, an enterprise CA, or an HTTP proxy/TLS inspection not used by the JVM?
3. Is the server sending the full chain, especially intermediate certificates, for the right SNI?
4. Which `cacerts` is the Java runtime using; are properties overriding it or is a custom `SSLContext` in use?
5. Has the server's CA chain been verified via a trusted channel?
6. If the server lacks an intermediate, fix the server/gateway config to send the full chain.
7. If the app needs to trust an enterprise/internal CA, add **the exact verified CA** per policy, never trusting random certificates off the network.
8. Re-run the Java TLS handshake with the expected hostname and run wrong-CA/wrong-hostname tests to prove it still fails closed.

**Key takeaway:** browser success does not prove the CA is in the JDK; JVM trust is explicitly configured.

### 14.2. Case B: mTLS fails after deployment

Scenario:
- Service A uses a client certificate to call Service B over mTLS.
- After CA rotation, the client sees `Received fatal alert: bad_certificate`.

Steps:
1. Identify Service B's TLS termination point (gateway or backend).
2. On client A, inspect `keymanager` trace to verify it selects the `PrivateKeyEntry` with the right key/certificate chain.
3. On server B, inspect `trustmanager`/PKIX trace to see if it trusts the new issuer CA; check client cert validity and `clientAuth` EKU.
4. Check whether B has multiple nodes and whether the CA/truststore rollout is synchronized.
5. Verify A's service identity SAN and policy mapping.
6. If server B rejected the new CA, update B's truststore per the rotation plan (with an overlap window), rather than editing client A's truststore instead.
7. After handshake success, verify service-principal authorization to the API remains accurate.

**Key takeaway:** "certificate error on client" does not mean the **client** performed the failing trust check. The client may merely have received the alert from the server.

### 14.3. Case C: Disjoint TLS versions

Scenario:
- Client enables TLS 1.3 only.
- Legacy gateway enables TLS 1.2 only.
- Java client sees `protocol_version` or `handshake_failure`.

Steps:
1. Collect enabled protocols from both sides.
2. Compare intersection; confirm it is empty.
3. Evaluate upgrading the gateway/TLS termination or configuring TLS 1.2 **only if policy permits**.
4. After changing, check suites, signature algorithms, named groups, certificate, and hostname.
5. Keep negative tests rejecting weak versions; never disable `jdk.tls.disabledAlgorithms`.

**Key takeaway:** this is a negotiation mismatch, not necessarily caused by certificates/truststores.

### 14.4. Case D: Common cipher suite yet still `handshake_failure`

Scenario:
- Both sides list `TLS_AES_128_GCM_SHA256`.
- Server has only a certificate/key unacceptable to the client or mismatched signers/groups.

Check:
- TLS 1.3 `signature_algorithms`, `supported_groups`, `key_share`, and certificate public key.
- Does the server keymanager have a matching `PrivateKeyEntry`?
- Do CA/cert chains satisfy policy?
- Did SNI pick the right vhost/certificate?
- Which algorithms/key sizes do security properties block?
- Are `CertificateRequest` and client cert requirements involved?

**Key takeaway:** TLS 1.3 suite intersection does not guarantee a shared authentication/key-share configuration.

### 14.5. Case E: Only one hostname on the same server fails

Scenario:
- `api.internal.example` passes; `billing.internal.example` fails.
- Both DNS names point to the same gateway IP.

Possibilities:
- SNI route returns the wrong certificate/default backend.
- Billing cert lacks SAN or expired; API cert is fine.
- One virtual host enforces a different ALPN/TLS policy.
- One load-balancer node holds a stale certificate.
- App calls an IP literal while expecting a DNS certificate.

Never use `-Dcom.sun.net.ssl.checkRevocation=false` or turn off hostname verification to work around it. Capture the exact certificate per SNI and fix the virtual-host/certificate chain.

## 15. Low-risk sequential runbook

### Step 1 — Gather minimal evidence

Record:
- Specific JDK runtime/provider.
- Client→host:port and expected hostname (do not substitute an arbitrary IP).
- TLS termination point and whether proxy/mTLS is present.
- Failure timestamp, recent deployments/CA rotations.
- **Sanitized** exception types/cause chain and last identified handshake stage.

### Step 2 — Separate network from TLS

Verify DNS, port, listener, firewall, proxy, and upstream route. If you cannot reach the TLS port, don't dig into PKIX. If hitting an HTTP-only port while the client speaks TLS, you will get record/protocol errors that importing CAs cannot fix.

### Step 3 — Enable scoped debugging in an authorized environment

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager,keymanager MyTlsApp
```

If investigating certificate trust paths:
```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath MyTlsApp
```

Limit log retention and never upload raw traces containing sensitive data to public channels.

### Step 4 — Compare configurations on both sides

- Enabled TLS versions, cipher suites, and algorithm constraints.
- TLS 1.3 supported groups/key shares/signature schemes.
- Server certificate/private key, mTLS client cert, and CAs.
- SNI expected host, ALPN application protocols.
- Resumption vs. full handshake and specific server node if failures vary by traffic.

### Step 5 — Verify PKIX/hostname

- Certificate chain leaf→intermediates→trust anchor.
- Actual truststore of each endpoint, not just a similarly named file.
- Validity, SAN, issuer, BasicConstraints, EKU/KeyUsage, algorithm constraints, revocation policy.
- Exact expected hostname from client/service config.
- Verify private key/handshake policy through the TLS stack, not just `X509Certificate.verify(...)`.

### Step 6 — Pick a safe fix and run negative tests

Examples:
- Server missing intermediate: fix the server chain.
- Enterprise CA not yet trusted by JVM: update truststore **after verifying the CA**.
- Wrong hostname: issue cert with matching SAN, fix SNI/route, or use the right expected host.
- mTLS CA rollout out of sync: fix server trust anchors and rotation plan.
- No shared TLS version: upgrade server or enable only policy-approved versions/suites.
- Missing key entry: provision/configure matching `PrivateKeyEntry` and protect the private key.
- ALPN mismatch: configure application protocols supported by both sides.

Then **verify that wrong CA, wrong host, expired cert, weak ciphers, and missing mTLS cert cases still fail**.

### Step 7 — Document root cause and prevent recurrence

- Classify errors accurately, avoiding generic `SSLHandshakeException` buckets.
- Health checks for certificate expiry/chain/hostname.
- Pre-expiry CA/certificate rotation alerts, staged rollouts, and rollback plans.
- Validate truststore/key entries at startup (without printing secrets).
- Test TLS/mTLS contracts between teams and gateways in CI staging.
- Track handshake failures by TLS termination point, JDK/provider, route, SNI, and policy version.
- Maintain a runbook checking **peer logs** too when the client sees only a generic fatal alert.

## 16. Things you must NEVER use as a "fix"

| Wrong action | Why it is dangerous | Right alternative |
| --- | --- | --- |
| TrustManager accepting all certificates | Drops chain/path validation, opens MITM | Use a truststore with verified CAs |
| Always-true HostnameVerifier | Certificates for other hosts are accepted | Fix SAN/SNI/expected hostname |
| Installing a peer-fetched root into truststore | Trusts a CA potentially controlled by an attacker | Verify root through administrative channels |
| Enabling SSLv3/TLS 1.0/1.1 or NULL/anonymous suites | Weakens protocol, enables downgrade | Upgrade peer and uphold algorithm policy |
| Clearing `jdk.tls.disabledAlgorithms` to force connection | Re-enables banned algorithms/keys | Replace certificate/key/server config |
| Catching `CertificateException` and continuing | Peer authentication is no longer trustworthy | Fail closed, fix certificate/trust |
| Logging private keys, TLS session secrets, tokens | Long-term leaks via diagnostics | Log only metadata and cause categories |
| Guessing root cause from `handshake_failure` alone | Generic alert; peer usually knows more | Inspect JSSE + peer logs per stage |
| Catching `SSLHandshakeException` and retrying infinitely | Causes DoS, masks misconfig, slows recovery | Controlled retries only for transient faults |
| Falling back to plaintext HTTP "temporarily" | Loses confidentiality/integrity/peer auth | Fix TLS or block the transaction |
| Dropping mTLS `clientAuth` check because CAs aren't synced | Loses client authentication and principal binding | Roll out CAs via controlled rotation |
| Testing only the happy path after a "fix" | Security bypasses can let happy-path tests pass | Test wrong-CA, wrong-host, expired, mTLS rejection |

## 17. QA and regression checklist

### Certificate trust and identity

- [ ] Valid chain to approved CA + matching SAN → handshake succeeds.
- [ ] Untrusted self-signed → rejected.
- [ ] CA absent from truststore → rejected.
- [ ] Expired/notYetValid leaf/intermediate → rejected per policy.
- [ ] Valid chain yet wrong SAN/hostname → rejected.
- [ ] Tampered issuer/chain or missing intermediate → handled properly (fails or builds valid path).
- [ ] Mismatched EKU/KeyUsage/BasicConstraints → rejected.
- [ ] Revocation/OCSP/CRL checked per policy.

### Negotiation

- [ ] Disjoint client/server protocol sets → handshake fails, no downgrade.
- [ ] Common protocol yet no common cipher suite → handshake fails per policy.
- [ ] Common TLS 1.3 suite yet disjoint signature schemes → fails properly.
- [ ] Disjoint named groups/key shares → fails or triggers `HelloRetryRequest` per protocol.
- [ ] Required ALPN has no overlap → fails/handled per app profile.
- [ ] Wrong SNI → cert/route selected per policy; wrong host does not pass.
- [ ] Security-disabled algorithms were not re-enabled during fixes.

### mTLS

- [ ] Client lacks certificate when server requires one → rejected.
- [ ] Client certificate issued by unlisted CA → rejected.
- [ ] Client cert lacks matching private key/alias or has wrong EKU → rejected.
- [ ] Post-handshake, principal mapping and authorization match tenant/resource.
- [ ] Client and server CA/cert rotations have safe transition windows.

### Observability and operations

- [ ] Errors classified across network/TLS/PKIX/identity/app.
- [ ] JSSE debug flags enabled only in authorized environments with retention/redaction.
- [ ] Server/peer logs traceable via correlation ID.
- [ ] Container/runtime truststore/keystore verified on the exact target JDK.
- [ ] No passwords hardcoded in JVM args or logs/CI secrets.
- [ ] Runbook includes rollback and negative tests to detect bypasses.

## 18. Self-check questions

**1. Is `SSLHandshakeException` always a certificate error?**  
No. It covers many handshake failures: protocol/cipher/group/signature mismatches, mTLS, PKIX, endpoint identity, and other issues.

**2. Is `Received fatal alert: handshake_failure` enough to conclude the client is missing a CA?**  
No. That is a generic alert from the peer; inspect peer logs and handshake stage/cause.

**3. When Java reports `PKIX path building failed`, should you immediately import the server's certificate into the truststore?**  
No. Verify the chain/CA via a trusted source first, then fix the truststore or chain under control; never blindly trust unverified network data.

**4. How do truststore and keystore differ in a standard HTTPS client?**  
The truststore provides CAs to verify the **server**. The keystore provides the **client's** private key/certificate if using mTLS.

**5. If the client supports only TLS 1.3 and the server only TLS 1.2, will a valid certificate make the handshake succeed?**  
No. There is no common protocol version; fix config/upgrade per policy before reaching certificate authentication.

**6. Why can TLS 1.3 fail even when both sides share `TLS_AES_128_GCM_SHA256`?**  
Because authentication/signature schemes, supported groups/key shares, certificate/key types, SNI/ALPN, and policies are separate requirements.

**7. If a Java client logs `Received fatal alert: bad_certificate` in mTLS, which side should you inspect?**  
Both, prioritizing the server/gateway that emitted the alert since it may have rejected the client certificate; inspect client keymanager and server trustmanager.

**8. Does `SSLSession.getProtocol()` returning `TLSv1.3` prove `CertificateVerify` ran in every resumed handshake?**  
No. TLS 1.3 has PSK resumption and not every handshake repeats certificate authentication; understand session/handshake mode. Nor does it prove application authorization.

**9. Does running `keytool -printcert -sslserver ...` and seeing a certificate mean the root is already trusted?**  
No. That tool displays the certificate; trust validation and hostname matching are separate security checks.

**10. How much `javax.net.debug` should be enabled?**  
Start with `ssl,handshake,trustmanager,keymanager` per failure; add `java.security.debug=certpath` when needed. Never leave data/plaintext/packet dumps enabled indiscriminately in production.

**11. What is `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` for?**  
Requests endpoint identity/hostname checking during a JSSE handshake in the right context; it does not replace certificate path validation or a complete network handshake.

**12. Why does a difference in truststores between a browser and a Java container produce different results?**  
Because the browser and JVM can use different CA stores, proxies/TLS interception, and security policies; browser success does not prove the Java trust anchor is right.

**13. After "fixing" by removing the `HostnameVerifier`, all requests pass. Is the task done?**  
No. That is a security regression: the client can accept certs for wrong endpoints. Fix SAN/SNI/trust configuration and run negative tests.

**14. If Java completed TLS and the server returned HTTP 403, is debugging `SSLHandshakeException` the right direction?**  
No. HTTP 403 is application authorization/identity policy and must be debugged at that layer.

**15. When a client has no client certificate yet the server requires mTLS, which side needs fixing?**  
The client needs a matching `PrivateKeyEntry`/certificate chain; the server needs to trust the client issuer per policy. Never replace with trust-all or turn off mTLS.

**16. Why is knowing the TLS termination point essential?**  
Because handshakes/certificates are checked at each specific hop (client↔gateway vs. gateway↔backend); editing a backend keystore won't help client↔gateway if TLS terminates at the gateway.

## 19. End-of-lesson decision flowchart

```text
Connection failed
      |
      v
DNS/TCP success?
  |             |
 NO             YES
  |              |
Network/route   TLS handshake begins
                 |
                 v
          ClientHello/ServerHello overlap?
             |                 |
            NO                 YES
             |                  |
       version/cipher/          certificate/auth phase
       group/signature                 |
       ALPN/SNI policy                 v
                              PKIX certificate path valid?
                               |                 |
                              NO                 YES
                               |                  |
                           CA/chain/              expected hostname valid?
                           validity/               |                |
                           revocation/            NO                YES
                           algorithm               |                 |
                                                SAN/SNI/          mTLS + Finished?
                                                identity          |          |
                                                                 NO          YES
                                                                  |           |
                                                             keymanager/     HTTP/application
                                                             trustmanager    authorization

  At every failure:
  - Read cause chain and first meaningful fatal event
  - Check BOTH endpoints' logs + actual TLS termination hop
  - Preserve strong trust, hostname verification, algorithm constraints
  - Make a scoped fix and re-run negative tests
```

**Conclusion:** Diagnosing `SSLHandshakeException` requires distinguishing **certificate validation**, **correct hostname/peer identity**, **mTLS client authentication**, and **common negotiation capabilities** across protocols, cipher suites, signature schemes, groups, and ALPN. JSSE debug, certpath traces, `keytool`, and `SSLParameters` help locate the root cause, yet are only meaningful once you identify the **exact runtime and exact TLS termination point**. Fix certificates/CAs/configs to align with policy rather than disabling trust or downgrading. A "fix" is complete only when **valid handshakes succeed and invalid handshakes are still rejected**.

### References

- Oracle Java SE 17 — *Java Secure Socket Extension (JSSE) Reference Guide*, troubleshooting, certificate exceptions, and debugging sections: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- Java SE 17 `SSLHandshakeException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html
- Java SE 17 `SSLEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html
- Java SE 17 `SSLParameters`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html
- Java SE 17 `SSLContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html
- Java SE 17 `SSLSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Java SE 17 `X509TrustManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509TrustManager.html
- Java SE 17 `CertPathValidatorException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.html
- Java SE 17 `KeyStore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html
- Oracle Java 17 — *keytool* command reference: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- RFC 5280 — X.509 certificate path validation: https://www.rfc-editor.org/rfc/rfc5280
- RFC 9846 — TLS 1.3 specification current in 2026: https://www.rfc-editor.org/rfc/rfc9846