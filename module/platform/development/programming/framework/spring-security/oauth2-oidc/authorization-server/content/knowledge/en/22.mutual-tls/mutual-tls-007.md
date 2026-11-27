# Certificate Renewal, Revocation, and mTLS Authentication Failure Testing

> **Chapter: mTLS.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module: learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The focus is the X.509 certificate lifecycle for OAuth client authentication: **renewal with overlap, revocation upon compromise, certificate status checking, and failure testing from the TLS handshake to the OAuth token endpoint**.

## 1. Distinguishing the Two Certificates in an mTLS Connection

In standard TLS, the server presents a server certificate so the client can verify the hostname and trust chain. With **mutual TLS (mTLS)**, the server also requires the client to present an X.509 certificate and prove possession of the corresponding private key directly during the TLS handshake.

In OAuth, there are two sides to distinguish:

- **Client certificate:** the certificate presented by the OAuth client to the Authorization Server at the token endpoint to authenticate via `tls_client_auth` or `self_signed_tls_client_auth`.
- **Server certificate:** the certificate of the Authorization Server (or TLS-terminating reverse proxy) that the OAuth client verifies when connecting to `https://login.example.vn`.

If the API also requires mTLS, the Resource Server may require a separate client certificate or the same certificate depending on deployment policy. With certificate-bound access tokens, the certificate used at the token endpoint is bound to the token and must be presented again when the client calls the protected resource.

Running example:

| Component | Illustrative Value | Role |
|---|---|---|
| Authorization Server | `https://login.example.vn` | Receives token requests and authenticates OAuth clients |
| OAuth client | `billing-job` | Confidential client calling the Client Credentials grant |
| Client certificate | `CN=billing-job,OU=Integrations,O=Example` | Proves client identity during the TLS handshake |
| Internal CA | `Example Integration CA` | Trust anchor issuing and signing client certificates per PKI |
| Resource Server | `https://api.example.vn` | Verifies access tokens and certificate binding if enabled |
| Server certificate | SAN `DNS:login.example.vn` | Allows the client to verify it is connecting to the right Authorization Server |

**mTLS client authentication and certificate-bound access tokens are two separate mechanisms that can be deployed together or independently.** mTLS client authentication proves the OAuth client's identity to the AS. Certificate-bound access tokens bind the issued token to a certificate so the Resource Server checks possession when the client calls the API. RFC 8705 defines both mechanisms.

## 2. Verification Layers for a Client Certificate

A client certificate is accepted only when it passes both TLS-layer checks and OAuth client identity checks.

### 2.1. TLS handshake and X.509 verification

The TLS implementation/container performs cryptographic and PKI checks, typically including:

1. The certificate falls within its `notBefore`–`notAfter` validity window.
2. The certificate chain connects to a trust anchor permitted by the server.
3. Signatures of every certificate in the chain are valid.
4. Basic Constraints, Key Usage, and Extended Key Usage match the client certificate role.
5. Critical extensions and path constraints are processed properly.
6. Revocation policies (CRL/OCSP or an equivalent mechanism) are enforced if required by the deployment.
7. The client proves possession of the corresponding private key during the handshake.

A client certificate generally needs Extended Key Usage `clientAuth` and Key Usage appropriate for handshake signatures under the chosen algorithm. Never use a certificate with only `serverAuth` as a client certificate.

### 2.2. Mapping the certificate to RegisteredClient

After a successful handshake, Spring Authorization Server identifies the OAuth client from `client_id` and verifies whether the received certificate matches that client's configuration.

With PKI-based `tls_client_auth`, RFC 8705 allows binding a client to a registered Subject DN or Subject Alternative Name. Spring Authorization Server by default compares the certificate's Subject DN against `RegisteredClient.getClientSettings().getX509CertificateSubjectDN()`. If you need to compare SANs or other attributes, configure a custom certificate verifier.

With `self_signed_tls_client_auth`, the server compares the client certificate received in the handshake against the certificate published in the client's JWK Set via `jwks_uri`/`jwkSetUrl`; the certificate is represented by `x5c` in the JWK.

| Method | Trust Source | Client Identification | Certificate Rotation Approach |
|---|---|---|---|
| `tls_client_auth` | PKI chain to a trusted CA | Registered Subject DN or SAN | Issue new certificate from trusted CA; keep matching DN/SAN identity or update registration |
| `self_signed_tls_client_auth` | Client's registered JWK Set | Certificate in `x5c` matches handshake certificate | Update JWK Set with new certificate and manage overlap/caches |

Never treat a successful TLS handshake alone as sufficient to authenticate `client_id`. A valid certificate issued by an internal CA belonging to `reporting-job` must never impersonate `billing-job`.

## 3. Certificate Lifecycle and Milestones to Manage

Certificates have a finite expiration date. Operating mTLS requires lifecycle management from key pair generation, certificate issuance, deployment, monitoring, renewal, and revocation through retiring old trust entries.

| Phase | Actions Required | Evidence to Record |
|---|---|---|
| Provisioning | Generate private key, CSR, and issue certificate from CA or self-sign per policy | Owner, client ID, serial, issuer, SAN/subject, fingerprint |
| Enrollment | Register identity/certificate with the OAuth client | Registration version, trust profile, effective timestamps |
| Deployment | Install certificate/private key into keystore or secret store | Secret version, target nodes/pods updated |
| Monitoring | Track expiration dates, CRL/OCSP, handshake errors, and CA changes | Expiry metrics, alerts, audit logs |
| Renewal | Issue and deploy new certificate before old certificate expires | Old/new fingerprints, overlap window |
| Revocation | Revoke compromised, key-lost, or deauthorized certificates | Serial, reason, revocation timestamp, propagation |
| Retirement | Remove old certificate from keystore/JWKS/trust store after transition window | Confirmation no traffic remains on old certificate |

Maintain an inventory keyed by `client_id`, issuer, serial number, SHA-256 fingerprint, subject/SAN, start/end dates, private key storage location, and owner. Never record private keys or keystore passwords in inventories or logs.

### 3.1. Renew ahead of expiration; do not wait for handshake errors

Schedule alerts at multiple thresholds, such as 60/30/14/7 days before expiration. Exact intervals depend on certificate issuance procedures and rollout times. Monitor certificates across all layers:

- Clients calling the token endpoint.
- Authorization Server public endpoints/reverse proxies.
- Resource Servers requiring mTLS.
- CA/intermediate certificates and trust stores.
- Certificates published in JWK Sets for `self_signed_tls_client_auth`.

An expired certificate can cause the TLS handshake to fail before the application ever receives an HTTP request. In that case, clients usually see only TLS errors like `certificate expired`, `bad certificate`, or `handshake failure`; there will be no OAuth JSON `invalid_client` because the request never reached the token endpoint.

## 4. Renewing Client Certificates Under the PKI Method

With `tls_client_auth`, the client certificate is verified against the PKI chain and registered identity. RFC 8705 permits a client to renew with a new certificate from a trusted CA **without changing authentication metadata on the AS** if the new certificate retains the same registered Subject DN (or SAN depending on deployment configuration).

### 4.1. Rotation workflow with overlap

Suppose `billing-job` currently uses certificate `C0`, which is nearing expiration. Safe procedure:

1. **Inventory:** confirm `client_id`, Subject DN/SAN, issuer, serial, fingerprint, expiration date, and every location where `C0` is installed.
2. **Generate a new key pair:** create a new private key in the client's secret store/keystore. Never reuse the old private key just to simplify rotation.
3. **Create CSR:** submit the CSR to the right CA profile; retain the Subject DN/SAN matching the registered identity.
4. **Issue and inspect `C1`:** verify chain, SAN/DN, `clientAuth` EKU, Key Usage, validity, algorithm, and fingerprint.
5. **Install `C1` in parallel mode:** deploy the new certificate/key to a subset of instances or canary. Keep `C0` active during the transition phase.
6. **Test the token endpoint:** confirm `C1` authenticates `billing-job` properly; do not test with another client's certificate.
7. **Shift traffic:** roll all client instances over to `C1` while observing TLS and OAuth authentication errors.
8. **Confirm `C0` is no longer used:** check telemetry by client identity/fingerprint if available, without logging raw certificates or private keys.
9. **Revoke or retire `C0`:** for routine rotation, follow CA policy; if the old certificate was compromised, revoke urgently and handle related tokens.
10. **Clean up old secrets:** remove the old key from runtime, secret managers, and backups per retention policy.

**Overlap must be time-bounded.** If the old certificate's private key is suspected compromised, do not keep it active for transition convenience; prioritize immediate revocation and accept controlled downtime/reauthorization.

### 4.2. Same Subject DN does not mean the same certificate

In PKI `tls_client_auth`, Spring's default AS behavior identifies the client by its registered Subject DN. Thus, a new certificate issued by a trusted CA with the same Subject DN that passes chain checks can continue authenticating the same client.

However, certificate-bound access tokens are tied to **the thumbprint of a specific certificate**, not merely Subject DN. If token `T0` has `cnf.x5t#S256` matching `C0`, the client cannot use `T0` with `C1` even though both certificates share the same DN. When switching to `C1`, acquire a new access token using the new certificate and use the new certificate at the Resource Server. RFC 8705 treats an access token bound to an old certificate as unusable once the client updates its certificate.

### 4.3. If SAN changes

If a custom verifier maps clients by SAN (e.g., `URI:spiffe://example/billing-job` or `DNS:billing-job.internal`), the new certificate must preserve the exact SAN identity registered. If the SAN changes, update policy/registration under controlled change management before shifting traffic. Never use arbitrary wildcard SANs or substring matching.

## 5. Renewing Self-Signed Certificates

With `self_signed_tls_client_auth`, the AS does not rely on a public/internal CA to identify the client certificate. Spring Authorization Server uses `ClientSettings.getJwkSetUrl()` to download the client's JWK Set and find a certificate matching the one received from the TLS handshake; the certificate is represented in JWK `x5c`.

Rotation workflow:

1. The client generates a new key pair and a new self-signed certificate.
2. The client updates the JWK Set at `jwks_uri`, adding a JWK containing certificate `C1` (and keeping `C0` during overlap if policy allows).
3. Ensure the JWK Set has public key parameters matching the certificate in `x5c`, a stable `kid` per key, and a trusted HTTPS endpoint.
4. Check the AS's cache/refresh behavior for `jwks_uri`; never assume JWK Set updates take effect instantaneously across every node.
5. Switch client instances to `C1` and verify the token endpoint and downstream resources.
6. When `C0` is no longer needed, remove the old JWK from the set and confirm the AS no longer accepts it.
7. If `C0` is compromised, revoke the registration/credential via emergency procedures; do not wait for normal cache overlap to expire.

Client configuration example (Spring Authorization Server 1.5.x):

~~~java
RegisteredClient selfSignedClient = RegisteredClient
        .withId("registration-billing-job")
        .clientId("billing-job")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("invoices.read")
        .clientSettings(ClientSettings.builder()
                .jwkSetUrl("https://billing.example.vn/.well-known/mtls-jwks.json")
                .build())
        .build();
~~~

The JWK Set must include the certificate in `x5c`; condensed example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "billing-cert-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_KEY_MODULUS_BASE64URL",
      "e": "AQAB",
      "x5c": ["BASE64_DER_CERTIFICATE_WITHOUT_PEM_MARKERS"]
    }
  ]
}
~~~

This is illustrative JSON; `x5c` holds the Base64-encoded DER certificate per JWK spec, not a private key. Never accidentally publish a keystore containing private keys as a public JWK Set. Restrict access and protect the integrity/availability of the JWK Set endpoint; if an attacker can alter the certificate list, they can compromise client authentication.

## 6. Certificate Revocation: CRL, OCSP, and Emergency Handling

Renewal addresses certificates approaching expiration; **revocation** addresses certificates that must no longer be trusted before `notAfter`, for example:

- The private key is leaked or lost.
- A client instance/vendor is compromised.
- A certificate was issued with the wrong subject/SAN or for the wrong tenant.
- A client partnership ended or is no longer permitted to connect.
- A CA/intermediate was compromised or trust policy changed.
- Unauthorized certificate usage is detected.

### 6.1. CRL

A Certificate Revocation List (CRL) is a CA-signed list containing serial numbers of revoked certificates. The TLS validator fetches the CRL via CRL Distribution Points or out-of-band configuration and checks the certificate serial.

Advantages:

- Can be distributed as files/caches, suited for internal networks without calling a responder on every handshake.
- Can check many serial numbers in one list.
- Useful with scheduled CRL issuance and delta CRLs.

Limitations:

- CRLs introduce latency between revocation and distribution of the updated CRL.
- Large CRLs increase download and verification overhead.
- Stale/expired or unreachable CRLs require explicit policy: fail closed or soft-fail.
- CA/intermediate and client certificates may have different CRL Distribution Points.

### 6.2. OCSP

Online Certificate Status Protocol (OCSP) queries a responder for a certificate's status by issuer/serial. Responses can be `good`, `revoked`, or `unknown`, signed with a validity window.

The advantage is fresher status than a full CRL. However, you must operate OCSP responders, caches, timeouts, stapling (if supported by the platform), and policies for unreachable responders.

`unknown` does not mean `good`. For high-risk token-issuing endpoints, do not automatically accept certificates with indeterminate status if policy mandates strict revocation checking.

### 6.3. Revocation checking is a deployment decision

RFC 8705 permits revocation checking in the PKI method, leaving it to the deployment to decide whether and how to check. Therefore:

- Do not assume merely configuring `trust-store` enables CRL/OCSP.
- Do not assume Spring Authorization Server automatically downloads CRL/OCSP and checks every certificate.
- Do not confuse Spring's custom `CertificateVerifier` (used to check certificate content/identity after the handshake) with chain/revocation validation in the TLS stack.
- Identify the responsible component: embedded server, reverse proxy/load balancer, Java TLS provider, PKI agent, or custom trust manager.
- Test with an actually revoked certificate and measure propagation latency.

If TLS terminates at a proxy, the proxy itself may be where chain/revocation validation occurs. The backend application must receive certificate metadata over a protected internal channel, never trusting headers sent directly by Internet clients.

### 6.4. Revocation workflow when a private key is compromised

1. Identify `client_id`, certificate serial/fingerprint, issuer, and compromise timestamp.
2. Mark the credential revoked at the CA/PKI or remove the certificate from the JWK Set/registration depending on the method.
3. Block the certificate at TLS ingress/trust policies and all mTLS-requiring Resource Servers.
4. Prevent the client from continuing to obtain access/refresh tokens with the old certificate.
5. Revoke related authorizations/access tokens/refresh tokens per policy; certificate revocation **does not automatically delete all already-issued tokens** in systems without continuous revocation checks.
6. If access tokens are certificate-bound, ensure Resource Servers reject the revoked certificate; if using introspection, consider revoking tokens/authorizations so `active=false`.
7. Issue a new certificate after remediating the root cause, update registration/JWKS, re-test, and monitor.
8. Preserve audit trails, detection time, AS/RS blocking time, and affected requests.

## 7. Certificate-Bound Access Tokens and the Impact of Rotation

When certificate-bound access tokens are enabled, the AS computes the SHA-256 thumbprint of the client certificate at the token endpoint and binds it to the token.

For JWT access tokens, RFC 8705 uses the claim:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "billing-job",
  "aud": ["invoices-api"],
  "scope": "invoices.read",
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_CERTIFICATE_DER"
  }
}
~~~

`x5t#S256` is the unpadded Base64URL encoding of the SHA-256 hash over the certificate's DER encoding. For opaque tokens, binding information can be returned in the introspection response under `cnf.x5t#S256`.

### 7.1. Configuring Spring Authorization Server

Example `RegisteredClient` using PKI mTLS and requiring certificate-bound access tokens:

~~~java
RegisteredClient mtlsClient = RegisteredClient
        .withId("registration-billing-job")
        .clientId("billing-job")
        .clientAuthenticationMethod(ClientAuthenticationMethod.TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("invoices.read")
        .clientSettings(ClientSettings.builder()
                .x509CertificateSubjectDN(
                        "CN=billing-job,OU=Integrations,O=Example")
                .build())
        .tokenSettings(TokenSettings.builder()
                .x509CertificateBoundAccessTokens(true)
                .build())
        .build();
~~~

`x509CertificateBoundAccessTokens(true)` enables certificate binding for access tokens issued via the client. This setting does not replace TLS server/client certificate setup, trust stores, certificate lifecycle, or Resource Server verification. Confirm that actual tokens contain `cnf.x5t#S256`.

### 7.2. The Resource Server must match the certificate

When receiving an API request:

1. Extract the access token and client certificate from the TLS implementation layer.
2. Verify the access token (JWT signature/issuer/audience/expiry or introspection).
3. Compute the SHA-256 thumbprint of the active client certificate.
4. Compare against `cnf.x5t#S256` in the access token/introspection response.
5. Check certificate chain/revocation per Resource Server policy.
6. If thumbprints do not match, reject with `401 invalid_token`; only then evaluate scopes and business authorization.

Never take the certificate from an `X-Client-Cert`/`X-Forwarded-Client-Cert` header sent directly by an Internet request. If a proxy terminates mTLS, it must strip client-sent fake headers and only a trusted proxy may write certificate metadata; the proxy→application path must also be protected and authenticated.

### 7.3. Rotation renders old tokens unusable with the new certificate

Suppose `C0` has thumbprint `H0`, and token `T0` contains `cnf.x5t#S256=H0`. After the client switches to `C1` with thumbprint `H1`:

- `T0 + C0`: may remain valid if neither the certificate nor token is expired or revoked.
- `T0 + C1`: rejected because `H1 != H0`.
- Token `T1` issued after the client authenticates with `C1`: bound to `H1`, used alongside `C1` at the Resource Server.

Therefore, rotation planning must account for **token TTL, refresh tokens, certificate overlap, and traffic cutover timing**. If the old certificate was compromised, do not keep a `T0/C0` path open just to avoid re-issuing tokens.

### 7.4. Refresh tokens also need binding

For confidential clients using `tls_client_auth`, the refresh token is indirectly bound to the client ID and requires the client to authenticate with its certificate when sending refresh requests. For public clients using certificate-bound tokens, RFC 8705 recommends binding refresh tokens to the certificate and checking binding on refresh. Verify the behavior of your deployed AS; do not assume `x509CertificateBoundAccessTokens(true)` automatically configures every refresh-token binding policy for every client type.

## 8. TLS Configuration in Spring Boot

The example below illustrates an embedded server holding its own server certificate and requesting client certificates in **optional** mode so multiple OAuth client authentication methods can coexist:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/etc/example/as-server.p12
    key-store-type: PKCS12
    key-store-password: ${AS_KEYSTORE_PASSWORD}
    key-alias: authorization-server
    trust-store: file:/etc/example/client-ca-trust.p12
    trust-store-type: PKCS12
    trust-store-password: ${CLIENT_CA_TRUST_PASSWORD}
    client-auth: want
    enabled-protocols:
      - TLSv1.3
      - TLSv1.2
~~~

Explanation:

- `key-store` holds the private key and server certificate chain presented by the Authorization Server to clients.
- `trust-store` holds CA/intermediate trust anchors for the client certificate PKI.
- `client-auth: want` requests a client certificate while allowing the TLS handshake to proceed if none is provided. This is useful when the AS simultaneously supports `client_secret_basic`, `private_key_jwt`, public clients, or endpoints not needing mTLS.
- `client-auth: need` requires a certificate at the TLS layer for every connection to the connector. Use this only when all traffic through that connector genuinely requires a certificate; otherwise, browser logins, health checks, or other client authentication methods can fail before HTTP requests reach Spring.
- `enabled-protocols` restricts TLS versions per deployment policy.

**Distinguishing the two failure modes:** with `want`, a client sending no certificate can finish the handshake, yet OAuth client authentication for a `RegisteredClient` requiring `tls_client_auth` will fail (typically `invalid_client`). With `need`, a missing certificate causes the TLS handshake to be rejected; there is no JSON OAuth response.

Never put keystore passwords in source control. Use a secret manager, strict file permissions, rotation, and auditing. Trust store configuration must contain only CAs permitted to issue client certificates; never blindly import certificates from every partner.

### 8.1. Separate trust configuration for client certificates

Separate the server keystore and client CA trust store. Avoid using a single PKCS12 file holding both the server private key and shared trust anchors if doing so broadens access permissions or trust scope excessively.

When an intermediate CA is replaced:

1. Add the new CA to the trust store before switching certificates.
2. Deploy the trust store to all AS nodes/proxies.
3. Verify the new chain via a canary.
4. Migrate client certificates to the new CA.
5. Remove the old CA only after all valid clients have migrated and no old chains remain needed.

This is a CA rollover; it differs from renewing a single client certificate under the same CA.

## 9. Customizing SAN Verification in Spring Authorization Server

With `tls_client_auth`, Spring Authorization Server by default verifies Subject DN against `x509CertificateSubjectDN`. If the organization identifies clients by SAN URI/DNS, a custom verifier is required. Configuration must preserve the default provider and add appropriate identity verification without replacing TLS-layer chain validation.

Example extension structure (Spring Authorization Server 1.5.x; `certificatePolicy` is an application-defined service):

~~~java
@Bean
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        CertificatePolicy certificatePolicy) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.clientAuthentication(clientAuthentication ->
                            clientAuthentication.authenticationProviders(providers ->
                                    providers.forEach(provider -> {
                                        if (provider instanceof
                                                X509ClientCertificateAuthenticationProvider x509) {
                                            x509.setCertificateVerifier(context ->
                                                    certificatePolicy.verify(context));
                                        }
                                    }))))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
~~~

`CertificatePolicy.verify(context)` must:

- Retrieve the `RegisteredClient` from the context already resolved by `client_id`.
- Extract the certificate chain verified by the TLS layer from authentication credentials.
- Read the exact SAN type (DNS, URI, email, or IP) per policy; do not use substring matching.
- Match against the identity registered/approved for the client.
- Reject if SAN is missing, duplicated, or does not match the expected identity.
- Never log certificates/private keys or full authentication credentials.

The snippet above illustrates the extension point; the `CertificatePolicy` implementation must throw an appropriate authentication exception on mismatch and be tested against your exact Spring version. Never write a manual X.509 parser to validate chains; use a proven TLS/X.509 library.

## 10. TLS Termination at a Reverse Proxy/Load Balancer

Many systems terminate TLS at an ingress/load balancer and forward internal HTTP to Spring Boot. With mTLS, the proxy sees the client certificate during the handshake, whereas the backend application may no longer see the TLS peer certificate directly.

If the AS needs the certificate for OAuth `tls_client_auth` or certificate-bound access tokens, certificate metadata must be forwarded securely:

1. The proxy must verify the client certificate/chain and revocation per policy.
2. The proxy strips any certificate headers sent by Internet clients.
3. The proxy creates an internal header containing the verified certificate/metadata itself.
4. Only trusted proxies may connect to the application; protect proxy→application with a private network and/or mTLS.
5. The application trusts metadata only from an authenticated proxy; reject direct requests bypassing the proxy.
6. Standardize thumbprint calculation and certificate formatting across proxy, AS, and Resource Server.
7. Test spoofed headers, proxy failover, and certificate rotation.

RFC 8705 leaves how certificate metadata is securely passed from an intermediary to the application outside the scope of the standard. This is a deployment design responsibility. Never merely enable `server.forward-headers-strategy` and assume every certificate header is trustworthy.

## 11. Testing mTLS Authentication Failures

Testing must distinguish failures at the **TLS handshake**, failures mapping certificate→OAuth client, and certificate-bound token failures at the Resource Server.

### 11.1. Using OpenSSL to inspect the handshake

Illustrative command to verify the server certificate and present a client certificate:

~~~bash
openssl s_client \
  -connect login.example.vn:443 \
  -servername login.example.vn \
  -cert billing-client.crt \
  -key billing-client.key \
  -CAfile server-ca.pem \
  -verify_return_error \
  -showcerts
~~~

Inspect validity dates, subject, issuer, SAN, EKU, and fingerprint of the client certificate:

~~~bash
openssl x509 -in billing-client.crt -noout \
  -subject -issuer -serial -dates -ext subjectAltName \
  -ext extendedKeyUsage -fingerprint -sha256
~~~

Never put private keys in command output or tickets. The commands above only verify the handshake/certificate; they do not prove `client_id` matches RegisteredClient or that tokens are issued properly.

### 11.2. Calling the token endpoint with mTLS

For a client registered with `tls_client_auth` and the Client Credentials grant:

~~~bash
curl --verbose \
  --cacert server-ca.pem \
  --cert billing-client.crt \
  --key billing-client.key \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data "grant_type=client_credentials&client_id=billing-job&scope=invoices.read" \
  https://login.example.vn/oauth2/token
~~~

Use dummy certificates/keys in test environments; never place production private keys or secrets into shell history. Upon success, the response contains an access token. If certificate-bound access tokens are enabled, verify that JWT `cnf.x5t#S256` or introspection `cnf` matches the fingerprint of the active certificate.

### 11.3. Negative test matrix

| No. | Scenario | Failure Layer | Expected Result |
|---|---|---|---|
| 1 | No client certificate sent when connector uses `want` | OAuth client authentication | TLS may succeed; token endpoint rejects mTLS client without issuing a token |
| 2 | No certificate sent when connector uses `need` | TLS handshake | Handshake fails; no JSON OAuth response |
| 3 | Certificate issued by untrusted CA | TLS chain validation | Handshake rejected |
| 4 | Expired certificate | TLS validity | Handshake rejected |
| 5 | Certificate before `notBefore` | TLS validity | Handshake rejected |
| 6 | Revoked certificate with revocation check enabled | TLS/PKI revocation | Handshake rejected per policy |
| 7 | OCSP responder/CRL unreachable | Revocation dependency | Fail-open/fail-closed per defined policy; metrics/alerts emitted |
| 8 | Certificate missing intermediate | TLS path building | Rejected if valid chain cannot be constructed |
| 9 | Certificate EKU excludes `clientAuth` | TLS certificate usage | Rejected |
| 10 | Certificate Subject DN differs from RegisteredClient | OAuth certificate verifier | Handshake may succeed; OAuth client authentication fails (`invalid_client`) |
| 11 | Certificate from valid CA but belongs to another client | OAuth client binding | Must not impersonate `client_id` |
| 12 | Wrong SAN when using custom verifier | OAuth certificate verifier | Rejected |
| 13 | Client sends non-existent `client_id` | OAuth client lookup | `invalid_client` |
| 14 | Client registration requires `tls_client_auth`, but secret sent instead of cert | OAuth authentication method | Rejected |
| 15 | New certificate with same DN issued by trusted CA | PKI rotation | Can authenticate if chain, validity, and policy are valid |
| 16 | Self-signed certificate absent from client JWKS | Self-signed verifier | Certificate rejected |
| 17 | New certificate published, yet AS uses stale JWKS cache | JWKS rotation | Verify cache/refresh; do not accept outside policy |
| 18 | Access token bound to C0 used to call API with C1 | Resource Server token binding | `401 invalid_token` due to thumbprint mismatch |
| 19 | Token bound to C0, C0 revoked, yet RS skips revocation | Resource Server revocation | Test must catch gap; configure RS/TLS to reject |
| 20 | Server cert expired or hostname mismatch | Client verifying AS | Client refuses connection to AS |
| 21 | TLS proxy sends forged certificate header | Proxy trust boundary | Application rejects requests not from trusted proxy |
| 22 | Proxy fails to forward certificate metadata | Proxy integration | OAuth client mTLS fails explicitly without silent fallback |
| 23 | Rotation across multiple AS pods | Cluster consistency | All nodes accept the right trust version; no node uses stale config |
| 24 | Certificate revoked while client holds active access token | Token lifecycle | Block new token issuance; handle old tokens per revocation/binding policy |

### 11.4. Distinguishing TLS errors from OAuth errors

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| `handshake_failure`, `bad_certificate`, `certificate_expired` | TLS server rejected certificate or chain | TLS logs, trust store, validity, EKU, CRL/OCSP |
| Connection succeeds yet returns `invalid_client` | Certificate does not match client registration or missing certificate in `want` mode | RegisteredClient, `client_id`, DN/SAN verifier |
| Token endpoint returns `unauthorized_client` | Client authenticated but grant not registered | `authorizationGrantType` on RegisteredClient |
| Token issued successfully yet API returns `401 invalid_token` | Certificate-bound token does not match certificate at Resource Server | `cnf.x5t#S256`, TLS peer certificate, thumbprint |
| API returns `403` | Token and binding valid but insufficient scope/authorization | Scope, audience, tenant, and API policy |
| Only one pod fails | Trust store, certificate/JWKS cache, or proxy config inconsistent | Inspect individual nodes and rollout versions |

## 12. Common Operational Errors

| Error | Cause | Resolution |
|---|---|---|
| Certificate renewed, yet client still gets `invalid_client` | New DN/SAN no longer matches registration or new CA not yet trusted | Verify identity and roll out CA trust first |
| New certificate works at token endpoint, yet API rejects | Access token is still bound to old thumbprint | Fetch a new access token using the new certificate |
| Certificate revoked, yet client still obtains tokens | Revocation check disabled or node uses stale CRL/cache | Check TLS revocation policy and propagation |
| New CRL not yet effective on one pod | Inconsistent CRL cache/refresh | Synchronize refreshes and monitor CRL version/nextUpdate |
| OCSP timeouts cause intermittent errors | Unstable responder/network or unclear soft-fail policy | Set timeouts/caches/failure policies and alerts |
| `need` breaks health checks/login | Connector forces every client to present a certificate | Use `want` for mixed connectors or separate mTLS endpoints/connectors |
| Certificate header spoofed | App trusts forwarded headers from the Internet | Strip headers at edge; trust only authenticated proxies |
| Self-signed rotation misses new certificate | JWKS cache not refreshed or JWK `x5c` mismatches key | Check cache, `kid`, `x5c`, and public key parameters |
| New server cert rejected by clients | Missing intermediate or client does not yet trust new CA | Deploy full chain, trust overlap, and test hostname |
| Token remains usable after revoking client | RS only validates JWTs offline without checking binding/revocation | Appropriate TTLs, introspection/revocation propagation, and mTLS checks |

## 13. Renewal and Revocation Runbook

### 13.1. Planned renewal

- [ ] Identify client, certificate serial/fingerprint, Subject DN/SAN, issuer, and installation targets.
- [ ] Generate a new private key in the secret store/keystore, create CSR, and obtain certificate.
- [ ] Verify chain, validity, EKU, Key Usage, SAN/DN, and fingerprint.
- [ ] If changing CAs, add the new trust anchor before deploying the new certificate.
- [ ] If using self-signed, update JWK Set `x5c` and check caches/overlap.
- [ ] Deploy canary with new certificate; test token endpoint and Resource Server.
- [ ] Shift all traffic while monitoring errors per client ID/node.
- [ ] Acquire new tokens if access tokens are bound to the old certificate.
- [ ] Retire/revoke the old certificate per policy and securely delete the old private key.
- [ ] Update inventory and audit records.

### 13.2. Emergency revocation

- [ ] Identify affected certificate/serial/fingerprint and client.
- [ ] Revoke at the CA or remove certificate from the JWK Set/registration.
- [ ] Update CRL/OCSP/trust policy and confirm all ingresses/AS/RS pick up the new state.
- [ ] Block the certificate at the TLS layer; do not merely delete the file from one client pod.
- [ ] Block subsequent refresh/token requests using the compromised credential.
- [ ] Revoke related tokens/authorizations per policy and check already-issued tokens at Resource Servers.
- [ ] Issue new key/certificate via a clean workflow; verify identity and scopes.
- [ ] Monitor requests continuing to use the old certificate and preserve incident audit logs.

## 14. Self-Check Questions

1. Why is a successful TLS handshake not enough to prove a certificate belongs to the right `client_id`?
2. What is the difference between `tls_client_auth` and `self_signed_tls_client_auth`?
3. With PKI mTLS, why can a new certificate with the same Subject DN continue authenticating the client without changing registration?
4. Why can a certificate-bound access token still not be used with a new certificate even when the DN is identical?
5. Is revocation checking for PKI mTLS automatically enabled just by configuring a trust store?
6. How do CRL and OCSP differ in distributing/querying certificate status?
7. With `client-auth: want`, how does a missing-certificate failure differ from `client-auth: need`?
8. If a certificate is revoked while the Resource Server checks only `cnf.x5t#S256`, what check is still missing?
9. Why must certificate-bound refresh tokens be bound/checked upon refresh?
10. When TLS terminates at a reverse proxy, why must `X-Forwarded-Client-Cert` from the Internet never be trusted directly?
11. If using `self_signed_tls_client_auth`, what role does `x5c` in the client's JWK Set play?
12. How do you prove rotation is complete across all AS pods and Resource Servers?

## References

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): PKI/self-signed methods, certificate-bound tokens, expiration, refresh token binding, TLS termination, and security considerations.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): certificate path validation, CRL, and X.509 PKI.
- [RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)](https://www.rfc-editor.org/rfc/rfc6960.html): querying certificate status via OCSP.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication and token endpoint.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `tls_client_auth`, `self_signed_tls_client_auth`, `X509ClientCertificateAuthenticationProvider`, SAN verifier, and certificate-bound access tokens.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings`, and `TokenSettings`.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): X.509 authentication and TLS container integration.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles and TLS configuration in Spring Boot applications.
