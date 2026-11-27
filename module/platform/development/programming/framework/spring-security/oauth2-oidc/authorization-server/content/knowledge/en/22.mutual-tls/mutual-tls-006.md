# Passing Certificate Identity Through a Reverse Proxy Under a Trust Model

## 1. Problem: TLS Terminates at the Reverse Proxy, Yet the Application Still Needs the Client Certificate

In OAuth 2.0/OpenID Connect (OIDC) deployments, a reverse proxy, API gateway, or load balancer often sits in front of the Spring Boot application. The proxy accepts HTTPS connections from clients, terminates TLS, verifies the client certificate if **mutual TLS (mTLS)** is enabled, and forwards the HTTP request to the backend Authorization Server or Resource Server.

When TLS terminates at the proxy, the backend does not directly participate in the initial TLS handshake. Consequently, the backend Servlet container does not see the original client's certificate in the `jakarta.servlet.request.X509Certificate` attribute. If the application needs the certificate identity for authentication, principal mapping, token binding checks, or authorization, the proxy must pass the certificate information over a trusted channel.

This is a **delegated identity across a network boundary** problem. A header containing certificate content does not by itself prove that the client performed mTLS. The backend may trust the header only when all of the following are verified simultaneously:
- The connection to the backend originates from an authorized reverse proxy.
- The proxy verified the client's certificate on the outer TLS connection.
- The proxy strips or overwrites any certificate headers sent by the caller.
- The proxy forwards the certificate over a protected backend connection, preferably mTLS.
- The backend accepts the header only from a trusted proxy and performs mapping/authorization per clear policies.

**RFC 9440** defines two standard HTTP headers for passing certificates through a TLS-terminating reverse proxy: `Client-Cert` and `Client-Cert-Chain`. This lesson presents that model, contrasts it with Envoy's `X-Forwarded-Client-Cert` (XFCC), and explains how to integrate with Spring Security.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant P as Reverse Proxy
    participant A as Spring Boot Application
    C->>P: TLS handshake + client certificate
    P->>P: Verify certificate chain, policy and revocation
    C->>P: HTTPS request
    P->>P: Remove untrusted Client-Cert headers
    P->>P: Set Client-Cert from verified TLS session
    P->>A: Backend mTLS + forwarded certificate header
    A->>A: Authenticate proxy peer
    A->>A: Parse and map original client certificate
    A->>A: Apply authorization policy
    A-->>C: Response through proxy
~~~

## 2. Distinguishing Three Identities in the Proxy Model

When deploying mTLS through a reverse proxy, at least three identities can appear in the same request:

| Identity | Where Is It Verified? | Meaning |
| --- | --- | --- |
| **Original client** | TLS handshake between client and reverse proxy | Certificate of the user, device, or OAuth client that connected to the edge |
| **Reverse proxy** | TLS handshake between proxy and backend | Workload/service permitted by the backend to forward requests |
| **Application principal** | Spring Security after mapping the certificate | Internal identity used for authorization, auditing, and business logic |

Do not conflate these three identities into one. For example, if the backend receives an mTLS connection from Envoy, the certificate seen by the Servlet container is **Envoy's** certificate. The user device's certificate resides in the header forwarded by Envoy. The two certificates have different origins and purposes.

### 2.1. Two TLS connections, two authentication decisions

~~~text
Client  -- TLS A (mTLS) --> Reverse Proxy -- TLS B (mTLS) --> Backend

TLS A:
  Peer certificate at proxy = original client's certificate

TLS B:
  Peer certificate at backend = reverse proxy's certificate

HTTP request forwarded by proxy:
  Client-Cert = original client certificate (per RFC 9440)
  Client-Cert-Chain = issuer chain of client certificate (if present)
~~~

The proxy authenticates the client on TLS A. The backend authenticates the proxy on TLS B. The backend may treat the certificate in the header as data attested by a trusted proxy only after proving TLS B belongs to the right proxy.

### 2.2. Certificate identity is not synonymous with application identity

A valid certificate can represent:
- An OAuth confidential client.
- A service-to-service workload.
- A registered device.
- A user with a smart card or enterprise certificate.

The application must determine which category the certificate belongs to before mapping it to a principal. Do not assume every certificate with `CN=Alice` is end-user Alice, nor assume a certificate with `CN=orders-service` is an OAuth client permitted to call every API.

## 3. RFC 9440: Client-Cert and Client-Cert-Chain

RFC 9440 standardizes how a TLS-terminating reverse proxy passes the client's certificate to an origin server over HTTP. The two headers have specific semantics:

| Header | Content | Rules |
| --- | --- | --- |
| `Client-Cert` | End-entity/leaf certificate used by the client in the TLS handshake with the proxy | Structured Field Byte Sequence; singleton, must not repeat or contain a list |
| `Client-Cert-Chain` | Certificates in the chain used to validate the leaf certificate | Structured Field List; excludes the leaf certificate already in `Client-Cert` |

These headers are used only in HTTP requests, never in HTTP responses. `Client-Cert-Chain` must not appear if `Client-Cert` is absent. The chain preserves the TLS certificate ordering; the root may be omitted if the origin server already holds the corresponding trust anchor.

### 3.1. Encoding: DER certificate as a Structured Field Byte Sequence

RFC 9440 does not define the header value as a subject DN, PEM text, or an arbitrary CN string. The certificate is encoded by:
1. Taking the certificate in ASN.1 DER form.
2. Base64-encoding without line breaks.
3. Wrapping the value in colons per Structured Fields Byte Sequence syntax.

Illustrative example:

~~~http
Client-Cert: :MIID...BASE64_DER_LEAF_CERT...:
Client-Cert-Chain: :MIIC...BASE64_DER_INTERMEDIATE_1...:, :MIIC...BASE64_DER_INTERMEDIATE_2...:
~~~

The data here is a placeholder. For `Client-Cert-Chain`, each item in the list is a byte sequence. Because the leaf certificate is already passed in `Client-Cert`, it is not repeated in the chain.

**Do not parse the header by extracting a CN string or splitting arbitrarily on commas.** These are Structured Fields; a production parser must properly understand byte sequence/list syntax, duplicate fields, whitespace, and size limits. A parser that only recognizes `:base64:` strings may suffice for minimal examples, but does not replace a complete Structured Fields parser.

### 3.2. Mandatory rules the proxy must enforce

RFC 9440 places header protection responsibility on the TLS-terminating reverse proxy:

- The proxy **MUST remove or overwrite** any pre-existing `Client-Cert` and `Client-Cert-Chain` headers in the incoming request before forwarding.
- The proxy may reject with HTTP 400 if the client request already sent either header itself.
- If the client-to-proxy connection **did not negotiate mTLS**, the proxy must sanitize by removing all occurrences of both headers.
- The proxy writes `Client-Cert` from the actual leaf certificate in the TLS session.
- The proxy may send `Client-Cert-Chain` if configured.
- Forward proxies and other intermediaries must not add or modify RFC 9440 headers on their own.
- Clients must not send these two headers themselves as a way to declare certificate identity.

This rule prevents clients from sending `Client-Cert: :...:` to impersonate another certificate. The backend must never accept headers self-declared by browsers, mobile apps, or Internet callers.

### 3.3. Certificate headers and HTTP caching

If a response is selected based on `Client-Cert` (e.g., an API returning data per certificate identity), RFC 9440 requires the response to be:
- Non-cacheable, e.g., `Cache-Control: no-store`; or
- Include `Vary: Client-Cert` so caches distinguish requests by certificate.

Evaluate caching across CDNs, reverse proxies, and browsers. Caching responses by URL while ignoring the client certificate can leak one principal's data into another principal's session.

## 4. Trust Model: Which Proxies Does the Backend Trust, and What Does It Trust?

A secure architecture has distinct trust layers:

~~~mermaid
flowchart TD
    C[Client certificate] --> T[TLS mTLS at edge]
    T --> V[Proxy verifies CA, validity, EKU, revocation]
    V --> H[Proxy strips caller-sent headers]
    H --> F[Proxy sets Client-Cert / Client-Cert-Chain]
    F --> M[Backend mTLS: authenticate proxy certificate]
    M --> G[Backend accepts headers only from trusted proxy]
    G --> P[Parse certificate and check policy]
    P --> I[Map certificate to principal]
    I --> Z[Authorization per API/resource]
    V -->|Invalid| X[Reject TLS/request]
    M -->|Untrusted proxy| X
~~~

### 4.1. Layer 1 — Authenticating the client at the edge

The reverse proxy must:
- Require a client certificate on listeners/routes applying mTLS.
- Verify the certificate path up to configured CAs/trust anchors.
- Check the validity period and required extensions.
- Enforce appropriate Key Usage/Extended Key Usage policies, typically including `id-kp-clientAuth` when required by the certificate profile.
- Have a revocation checking policy via CRL/OCSP or an enterprise PKI mechanism.
- Map issuer, SAN, serial, or fingerprint to an authorized identity.
- Reject the handshake or request when the certificate fails policy.

Forward only a certificate that the proxy **actually received and verified** from the TLS session. Never build headers from query parameters, cookies, or other caller-controlled headers.

### 4.2. Layer 2 — Authenticating the proxy at the backend

The backend should accept traffic only from the proxy over a private network and a mutually authenticated TLS connection:
- The backend has a server certificate for the proxy to verify.
- The proxy has a client certificate for the backend to verify.
- The backend trust store contains only CAs/certificates permitted to issue proxy identities.
- Firewalls/security groups open the backend listener only to authorized proxies/workloads.
- The proxy certificate has a clear SAN/identity for the backend to verify.

Relying solely on a private network without peer authentication allows another workload on the network to send forged `Client-Cert` headers. A private network reduces the attack surface but does not establish proxy identity by itself.

### 4.3. Layer 3 — Validating headers and mapping identity

Only after confirming the peer is a trusted proxy may the backend use RFC 9440 headers. Next:
- Parse the DER certificate properly.
- Verify the certificate matches the application's profile and trust policy.
- Decide whether to trust the proxy's validation result or have the backend independently build/validate the certificate path.
- Map identity using SAN or a stable identifying attribute.
- Check that the certificate is still permitted to access the corresponding resource/tenant/client.
- Audit using appropriate fingerprint/issuer/serial values, without logging private material.

**Proxy-to-backend TLS proves the request came from the proxy.** It does not by itself prove the certificate inside the header is valid if the proxy skipped outer TLS verification or if the header could be altered before reaching the proxy.

## 5. How Envoy's XFCC Differs from RFC 9440

`X-Forwarded-Client-Cert` (XFCC) is a header used by Envoy to carry certificate information across a proxy chain. It is an implementation-specific format, not equivalent to the two RFC 9440 standard headers.

Envoy can represent one or more XFCC elements, each describing a certificate/proxy in the request path. The text form typically uses attributes such as `By`, `Hash`, `Subject`, `URI`, `DNS`, and `Cert`; elements are comma-separated and attributes are semicolon-separated. Values containing delimiters must be escaped/quoted per the XFCC format.

| Criterion | RFC 9440 | Envoy XFCC |
| --- | --- | --- |
| Header | `Client-Cert`, `Client-Cert-Chain` | `X-Forwarded-Client-Cert` |
| Syntax | Structured Fields; DER byte sequence | Envoy-defined XFCC format, text or JSON |
| Leaf certificate | `Client-Cert` | Can appear in the `Cert` attribute if configured |
| Chain/proxy hops | `Client-Cert-Chain` contains issuer chain | Can represent multiple XFCC elements/hops |
| Interoperability | IETF Standard | Specific to Envoy and supporting ecosystems |

Do not parse XFCC with an RFC 9440 parser, and do not treat `Client-Cert` as a renamed variant of XFCC. Pick one clear contract between proxy and backend; if compatibility across multiple gateways is required, consider normalizing at an adapter on the trust boundary.

### 5.1. Envoy XFCC forwarding modes

Envoy provides `forward_client_cert_details` with modes that have distinct semantics:

| Mode | Behavior |
| --- | --- |
| `SANITIZE` | Default; does not send XFCC to the next hop |
| `FORWARD_ONLY` | When the client connection is mTLS, forwards existing XFCC |
| `APPEND_FORWARD` | When the client connection is mTLS, appends current certificate info to existing XFCC |
| `SANITIZE_SET` | When the client connection is mTLS, resets XFCC with current certificate info and forwards |
| `ALWAYS_FORWARD_ONLY` | Always forwards XFCC, regardless of whether the client connection is mTLS |

At a trust boundary receiving certificates from Internet clients, you must clearly understand the difference between **forwarding existing values** and **sanitizing then setting values from the current TLS session**. Preserving client-sent headers lets an attacker inject a forged XFCC element. Never blindly choose `FORWARD_ONLY` or `APPEND_FORWARD` unless upstream headers were already sanitized at a trusted hop.

`SANITIZE_SET` is typically appropriate when this proxy authenticates the original client certificate and needs to reconstruct XFCC from the current TLS connection. With multiple hops, design the trust chain and append/sanitize policy at each hop; the backend trusts only authenticated proxies.

## 6. Choosing Certificate Identity: SAN, Issuer, and Fingerprint

### 6.1. Do not rely solely on CN

A Subject DN can include `CN`, `OU`, `O`, `C`, or email. Extracting `CN` with regex easily causes collisions:
- Two different CAs can issue the same CN.
- CN may not be unique within a tenant.
- DN strings can vary in escaping, attribute order, and encoding.
- CN is typically a display name, not a stable identifier key.

Prefer SANs per an agreed profile, such as URI SAN for workload identity, DNS SAN for service identity, or a CA-managed enterprise identifier. Combine issuer/trust domain with SAN to prevent two CAs from issuing the same URI/name.

### 6.2. Certificate fingerprint and issuer/serial

A certificate can be identified by the SHA-256 fingerprint of the DER leaf certificate:

~~~text
fingerprint = BASE64URL_NO_PADDING(
    SHA-256(leaf_certificate_DER)
)
~~~

A fingerprint identifies **one specific certificate**, not necessarily a user/service across re-issuances. When a certificate is renewed, the fingerprint changes. You can use issuer + serial or SAN + issuer depending on the identity lifecycle, bearing in mind that serial numbers are unique only within an issuer.

A mapping table may include:

| Attribute | Purpose |
| --- | --- |
| Trust domain / issuer | Identifies the CA or PKI that issued the certificate |
| SAN URI/DNS/otherName | Identifies the workload, client, or device |
| Serial number | Looks up the certificate within the issuer |
| SHA-256 fingerprint | Uniquely identifies the presented certificate |
| Status / validity | Active, revoked, expired, or suspended |
| Tenant / application roles | Maps to internal permissions |

Never grant a role merely because a certificate has a CN string matching a role name. Authorization must rely on an organization-controlled registry/policy.

## 7. Which Certificate Does Spring Security See?

Spring Security Servlet X.509 integrates via `X509AuthenticationFilter`. This filter reads the certificate from the Servlet attribute:

~~~text
jakarta.servlet.request.X509Certificate
~~~

Then `X509PrincipalExtractor` extracts a principal from `X509Certificate`, and `PreAuthenticatedAuthenticationProvider`/`AuthenticationUserDetailsService` can load authorities for that principal.

When the backend uses mTLS with a reverse proxy, the Servlet container typically exposes the **proxy's** certificate in that attribute. It does not automatically read the `Client-Cert` header or automatically know the original client certificate. This is a crucial point when using Spring Security behind TLS termination.

### 7.1. When to use http.x509()?

Use the configuration:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .x509(Customizer.withDefaults())
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );
    return http.build();
}
~~~

when the Servlet container actually receives and verifies the TLS peer's certificate on the connection to the application. In the proxy-to-backend mTLS model, `x509()` typically authenticates the **reverse proxy**, not the original end-user/client.

Spring Security documentation describes X.509 authentication as pre-authentication: requesting and validating the certificate happens at the container/TLS layer, and Spring Security uses that certificate to resolve an Authentication and authorities. `x509PrincipalExtractor` customizes how the principal is extracted, but the extractor itself does not turn an arbitrary HTTP header into a certificate.

### 7.2. Header forwarding requires a dedicated adapter

If the application needs a principal from the original certificate in `Client-Cert`, you can build an integration following these steps:
1. A filter running after the request has passed the proxy trust gate.
2. Verify the backend peer certificate belongs to an accepted proxy.
3. Read exactly one `Client-Cert` and parse the Structured Field Byte Sequence.
4. Construct an `X509Certificate` from the DER bytes.
5. Apply the chosen certificate trust/identity policy.
6. Create a pre-authentication token or supply the certificate to an authentication provider.
7. Let Spring Security populate the SecurityContext and proceed with authorization.

Never add a filter that reads `Client-Cert` on every request without authenticating the proxy. Never use `X509PrincipalExtractor` as proof that the header came from a trusted proxy.

An illustrative layout in the Servlet filter chain is to authenticate the proxy with `x509()` first, and only then run the filter processing the original certificate:

~~~java
http
    .x509(x509 -> x509
        .x509PrincipalExtractor(proxyPrincipalExtractor)
        .userDetailsService(proxyUserDetailsService)
    )
    .addFilterAfter(
        forwardedClientCertificateFilter,
        X509AuthenticationFilter.class
    );
~~~

The TLS container verifies the **proxy peer's** chain against the trust store; `proxyPrincipalExtractor` extracts the principal and `proxyUserDetailsService` loads authorities for that proxy. `forwardedClientCertificateFilter` is an application-built filter; it must verify the proxy's Authentication is accepted before reading the header, then create an Authentication for the original client certificate. Apply the filter only to endpoints that genuinely need forwarded client identity. If an endpoint lacks a certificate header per policy, do not synthesize a default principal.

## 8. Implementation Example: Backend Trusts Only the Reverse Proxy via mTLS

### 8.1. TLS configuration for the Spring Boot backend

Example backend requiring a certificate from the proxy:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:backend-server.p12
    key-store-type: PKCS12
    key-store-password: ${BACKEND_KEYSTORE_PASSWORD}
    trust-store: classpath:trusted-proxy-clients.p12
    trust-store-type: PKCS12
    trust-store-password: ${PROXY_TRUSTSTORE_PASSWORD}
    client-auth: need
~~~

`client-auth: need` requires the peer to send a certificate and the container verifies it against the trust store. On this connection, the peer is the reverse proxy. Certificates in `trusted-proxy-clients.p12` must contain only CAs/certificates allowed to authenticate proxies. Do not put broader enterprise client CAs into the proxy trust store unless needed.

Configure the proxy to verify the backend's server certificate and use the proxy workload's own client certificate. Retrieve secrets/passwords from a secret manager or secure deployment mechanism; never commit literals to the repository.

### 8.2. Proxy strips forged headers and rewrites the verified certificate

An RFC 9440 proxy must execute logic equivalent to:

~~~text
on incoming request:
    if client TLS session has verified client certificate:
        remove all incoming Client-Cert headers
        remove all incoming Client-Cert-Chain headers
        set Client-Cert = RFC9440(DER(verified_leaf_certificate))
        optionally set Client-Cert-Chain = RFC9440_LIST(verified_chain_without_leaf)
    else:
        remove all incoming Client-Cert headers
        remove all incoming Client-Cert-Chain headers

forward request to backend over authenticated mTLS
~~~

This is pseudocode describing behavior, not copy-pasteable NGINX/Envoy configuration. Directive names and certificate serialization vary by proxy. Verify that your proxy product emits proper RFC 9440 encoding or use a dedicated XFCC adapter.

### 8.3. Parsing the certificate after the trust gate

The Java snippet below accepts only `byte[]` DER **already extracted by a Structured Fields parser** from `Client-Cert`. It is not a complete header parser:

~~~java
static X509Certificate toX509Certificate(byte[] der) {
    try {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(
                new ByteArrayInputStream(der));
    }
    catch (CertificateException ex) {
        throw new IllegalArgumentException("Invalid forwarded client certificate", ex);
    }
}
~~~

In production:
- The Structured Fields parser must reject duplicate `Client-Cert` headers, lists instead of byte sequences, and oversized values.
- Invoke the parser only after confirming the request comes from a trusted proxy.
- If the backend needs to verify the chain itself, parse `Client-Cert-Chain` as a Structured Field List and build a PKIX path with local trust anchors.
- If trusting the proxy's validation result, authenticate the proxy peer via mTLS and restrict that proxy's permissions.
- Do not log DER certificates or raw headers at normal log levels.

### 8.4. Creating a pre-authenticated principal

Once the certificate is accepted, the application can map it to an identity and use a pre-authentication provider:

~~~java
X509Certificate certificate = forwardedCertificateResolver.resolve(request);
String principal = certificateIdentityMapper.map(certificate);

PreAuthenticatedAuthenticationToken authenticationRequest =
        new PreAuthenticatedAuthenticationToken(principal, "N/A");

Authentication authenticated =
        authenticationManager.authenticate(authenticationRequest);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
~~~

This is an illustrative snippet placed inside a custom filter/provider appropriate for the filter chain; handle `AuthenticationException`, persist the SecurityContext using your Spring mechanism, and never call the mapper before the trust gate. `forwardedCertificateResolver`, `certificateIdentityMapper`, and `authenticationManager` are application-built dependencies.

If the certificate needs to be preserved as authentication details, the provider can accept a rich principal object rather than just a username string. Even so, authorization should rely on the mapped stable identity and authorities loaded from a trusted source.

## 9. Using Certificate Forwarding with OAuth 2.0 mTLS

RFC 8705 describes two related yet distinct capabilities:

1. **OAuth client authentication with mTLS:** the client authenticates to the Authorization Server using a certificate on the TLS connection to the token endpoint.
2. **Certificate-bound access tokens:** the access token is bound to a certificate; the Resource Server verifies that the certificate presented by the client matches the certificate bound to the token.

In the TLS termination model, if the Authorization Server or Resource Server sits behind a reverse proxy, you must distinguish the original client's certificate from the proxy's certificate. If the token is bound to the original client's certificate, the backend must identify that exact certificate through a trusted proxy channel or maintain end-to-end mTLS.

### 9.1. cnf.x5t#S256

A certificate-bound access token may contain a confirmation claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "service-client",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_LEAF_CERT_DER"
  }
}
~~~

The `x5t#S256` value is the SHA-256 thumbprint of the **DER-encoded end-entity certificate** used in mTLS, Base64URL-encoded without padding. Never hash PEM text, Subject DN, or the entire certificate chain.

When the Resource Server receives the token, it must verify the access token first, extract the thumbprint in `cnf.x5t#S256`, compute the thumbprint from the certificate verified across the trust boundary, and compare them. If the certificate in the header is trusted only via proxy forwarding, the backend must authenticate the proxy peer and ensure the proxy verified the original client certificate properly.

### 9.2. Do not confuse client authentication with end-user identity

| Question | OAuth client authentication | Certificate-bound access token | Forwarded certificate identity |
| --- | --- | --- | --- |
| Who does the certificate represent? | OAuth client | Key/certificate holder using the token | TLS peer client at the edge |
| Purpose | Authenticate client to AS | Bind token to certificate | Pass certificate across TLS termination |
| Where verified | Token endpoint TLS/client auth | Resource Server | Proxy and backend trust boundary |
| Claim/header | Client auth method mTLS | `cnf.x5t#S256` | `Client-Cert`/`Client-Cert-Chain` or XFCC |

A user certificate forwarded through a proxy does not automatically become OAuth client authentication for the client application. Nor does the presence of `Client-Cert` mean the access token is certificate-bound.

### 9.3. TLS termination does not automatically pass mTLS client authentication to the backend

RFC 8705 client authentication requires the Authorization Server to authenticate the OAuth client's certificate per the registered mTLS method. If TLS terminates at the proxy, the TLS connection from the proxy to the AS carries the **proxy's** certificate. Having the backend additionally receive `Client-Cert` does not automatically make the Servlet container treat the original client certificate as the TLS peer of the backend connection.

There are two architectural approaches:
- **TLS passthrough/end-to-end:** preserve the client's TLS handshake all the way to the AS/Resource Server itself; the application/container sees the original certificate and can use standard mTLS mechanisms directly. L4 proxies cannot perform full HTTP routing/inspection over encrypted TLS.
- **Trusted certificate forwarding:** the proxy authenticates the client at the edge, strips/overwrites headers, and forwards the certificate over backend mTLS. The AS must have an explicitly designed integration to use the proxy-attested certificate for client authentication or token binding. The integration must bind proxy identity, client certificate, client registration, and trust policy; never simply read a header and trust it.

Similarly, when issuing a certificate-bound access token, `cnf.x5t#S256` must be computed from the **authenticated and bound client certificate**, not from the proxy's certificate on backend TLS. The Resource Server must also compare against the original client certificate forwarded across the trust boundary. If that path cannot be guaranteed, do not claim the token is bound to the original client certificate.

## 10. Multi-Proxy Models and Trust Chains

There can be multiple hops:

~~~text
Browser / Device
   |
   | mTLS: client's certificate
   v
Edge Gateway
   |
   | mTLS: Edge Gateway's identity
   v
Internal Ingress
   |
   | mTLS: Internal Ingress's identity
   v
Spring Boot Backend
~~~

Each hop must have a clear contract:
- Which hop actually terminates TLS from the original client?
- Which hop verifies the certificate chain and revocation?
- Which hop is allowed to write or append forwarded certificate headers?
- Does the backend trust the final proxy or a specific proxy chain?
- Is the original client's certificate chain preserved or only the leaf?
- Which headers are stripped at each hop?

**Never trust every element in a header merely because the header is named X-Forwarded.** If multiple proxies append data, a downstream proxy must authenticate the preceding proxy and normalize the chain. The backend should verify the mTLS peer is the designated ingress proxy, and then apply agreed parsing/trust rules.

### 10.1. Certificate chain and trust anchors

`Client-Cert-Chain` can carry intermediate certificates, while the root trust anchor may be omitted if the backend already knows that trust anchor. The backend must never take a root from the header as an automatic trust anchor. Trust anchors must be configured independently and managed per PKI policy.

If the proxy already validated the chain and the backend simply trusts the proxy's result, the backend must protect the proxy as an authentication authority. If the backend re-validates independently, it must have full trust anchors, algorithms, revocation policies, and path validation. Never simply call `certificate.checkValidity()` and conclude the certificate is trustworthy: that method primarily checks expiration dates and does not verify the chain or revocation status.

## 11. Risks, Misconfigurations, and Mitigations

| Risk | Cause | Mitigation |
| --- | --- | --- |
| Header spoofing | Proxy preserves client-sent `Client-Cert` | Strip/overwrite at edge; backend trusts only proxy mTLS |
| Direct backend bypass | Backend is public or reachable directly by unknown workloads | Private listener, firewall, mTLS peer allowlist |
| Proxy identity confusion | Using proxy certificate as user identity | Separate proxy principal from original client certificate |
| CN collision | Mapping solely by CN | Use SAN + issuer/trust domain or fingerprint |
| Chain injection | Trusting caller-supplied chain | Chain constructed only by proxy; backend validates against local trust anchors |
| Expired/revoked certificate | Missing revocation policy | CRL/OCSP or PKI mechanism; handle caching/latency explicitly |
| XFCC parsing bug | Splitting commas/semicolons without handling quotes/escapes | Use a proper XFCC-compliant parser |
| RFC 9440 parsing bug | Treating header as PEM or raw Base64 | Structured Fields parser, size limits, and duplicate rejection |
| Multi-hop spoofing | Downstream proxy appends data from untrusted hop | Authenticate each hop, sanitize, and define trust chain |
| Cache data leak | Response depends on certificate while cache ignores identity | `Cache-Control: no-store` or `Vary: Client-Cert` |
| Stale certificate mapping | Certificate renewed/revoked while principal cache is stale | Short cache TTL, invalidate by fingerprint/status |
| Authorization bypass | Valid certificate treated as sufficient permission for all APIs | Still verify scopes, audience, tenant, and business authorization |

## 12. Test Matrix

### 12.1. Testing the proxy and trust boundary

| Scenario | Expected Result |
| --- | --- |
| Client sends valid mTLS certificate | Proxy verifies and forwards leaf per contract |
| Client sends no certificate on mTLS-required route | TLS/request rejected per policy |
| Client sends forged `Client-Cert` header | Proxy removes/overwrites or returns 400 |
| Client sends multiple `Client-Cert` headers | Proxy sanitizes or rejects; backend never sees ambiguous values |
| Client sends `Client-Cert-Chain` without leaf | Proxy removes/rejects |
| Client connection did not negotiate mTLS | Both RFC 9440 headers are stripped |
| Backend receives request from non-proxy workload | TLS mTLS or network policy rejects |
| Proxy certificate expired/untrusted | Backend rejects TLS |
| Certificate header modified between proxy and backend | Backend transport/authentication detects or rejects request |
| Proxy forwards request across multiple hops | Only trusted hops can create/append metadata per policy |

### 12.2. Testing certificates and the application

| Scenario | Expected Result |
| --- | --- |
| Valid RFC 9440 header | Leaf DER parsed accurately |
| Header violates Structured Field syntax | Rejected; no fallback to CN header |
| Leaf certificate expired | Rejected per trust policy |
| Certificate has wrong EKU/Key Usage | Rejected if profile requires clientAuth |
| Issuer not in trust domain | Rejected |
| Certificate revoked | Rejected per revocation policy |
| Two certificates share CN but have different issuers | Principal is not mis-mapped |
| SAN missing from registry | Identity/authority not granted |
| Certificate renewed | Identity lifecycle updates to new mapping |
| Token has wrong cnf.x5t#S256 | Token/certificate binding rejected |
| Client certificate differs from proxy certificate | Each identity handled in its proper role |
| Response varies by client certificate | Cache does not leak data across identities |

### 12.3. Testing Spring Security

- Verify `x509()` by default reads the certificate from the Servlet attribute and in backend mTLS receives the proxy's certificate.
- Verify the custom forwarded-certificate filter does not run when requests do not originate from a trusted proxy.
- Verify that missing `Client-Cert` never creates a synthetic certificate principal.
- Verify that certificate headers do not grant authorities on their own; authorities must come from a user/identity service or trusted policy.
- Verify that OAuth2 Resource Server still checks issuer, signature, audience, expiry, scopes, and the confirmation claim.
- Verify that a request with a Bearer token lacking certificate proof cannot use a certificate-bound access token.
- Verify that logs do not record raw certificates, headers, or unnecessary secrets.

## 13. Scenario Exercise

A system has an Edge Gateway and a Spring Boot Authorization Server:

~~~text
Client A:
  connects via HTTPS + mTLS to Edge Gateway
  certificate subject CN=payments-client
  SAN URI=spiffe://corp.example/workload/payments

Edge Gateway:
  validates certificate against Corp-Client-CA
  forwards request to backend over mTLS
  gateway's client certificate is issued by Platform-CA

Spring Boot:
  server.ssl.client-auth=need
  trust store trusts only Platform-CA
~~~

A request reaching the backend carries:
- TLS peer certificate: Edge Gateway.
- Header `Client-Cert`: payments-client's certificate.
- Header `Client-Cert-Chain`: Corp-Client-CA's intermediate chain.

Answer the following:

1. Why might `http.x509()` on the backend authenticate Edge Gateway instead of payments-client?
2. Which conditions must hold before the backend trusts `Client-Cert`?
3. If Client A sends another `Client-Cert` header itself, what must Edge Gateway do?
4. If another pod in the cluster calls the backend directly and sends a forged header, what mechanisms block the request?
5. Why is mapping by SAN URI + trust domain generally safer than mapping CN alone?
6. If the backend needs to validate the chain itself, what else must it have besides `Client-Cert-Chain`?
7. If the access token contains `cnf.x5t#S256`, which certificate is the thumbprint computed from?
8. When responses vary by client certificate, how must caching be handled?

**Hint:** The TLS peer at the backend is the gateway, while the original client certificate is in the header. Trust the header only after verifying the gateway peer, restricting the network, ensuring the gateway strips/overwrites headers, and validating the leaf certificate against trust policies. RFC 8705's thumbprint is computed over the DER leaf certificate of the client bound to the token, not the gateway's certificate or the entire chain.

## 14. Production Deployment Checklist

1. **TLS edge:** enable mTLS on the proper listeners/routes and verify certificate chains, validity, EKU/Key Usage, and revocation.
2. **Header contract:** choose RFC 9440 or XFCC; document encoding, chain ordering, duplicates, and multi-hop behavior.
3. **Sanitization:** strip/overwrite client headers; when mTLS is absent, remove all forwarded certificate headers.
4. **Backend transport:** allow only proxies to reach the backend; prefer proxy-to-app mTLS with a dedicated trust store.
5. **Proxy identity:** backend verifies the proxy's certificate, keeping it separate from the original client certificate.
6. **Certificate parsing:** use a proper Structured Fields/XFCC parser, enforce size limits, and reject ambiguous input.
7. **Trust policy:** decide whether to trust proxy validation or re-validate chains at the backend; maintain independent trust anchors and clear revocation policies.
8. **Identity mapping:** use SAN + issuer/trust domain, fingerprint/serial, and lifecycle management; do not rely on standalone CNs.
9. **Spring Security:** understand that `X509AuthenticationFilter` reads the Servlet certificate attribute; forwarded headers require an adapter/custom authentication integration.
10. **OAuth mTLS:** distinguish client authentication, certificate-bound tokens, and forwarded end-user/workload identities.
11. **Caching:** responses depending on `Client-Cert` must use no-store or proper Vary per RFC 9440.
12. **Observability:** audit proxy identity, certificate fingerprint, issuer, and reason codes; minimize logging raw certificate material.
13. **Testing:** test spoofed headers, direct backend calls, wrong proxy certs, chain tampering, expiry/revocation, multi-hop paths, and cache isolation.
14. **Incident response:** establish procedures for revoking certificates, updating trust stores, revoking tokens, and handling key/CA compromises.

## 15. Standards and Spring Documentation References

- [RFC 9440 — Client-Cert HTTP Header Field](https://www.rfc-editor.org/rfc/rfc9440.html): `Client-Cert`, `Client-Cert-Chain`, DER/Structured Fields, proxy sanitization, and cache behavior.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): OAuth client mTLS authentication and `cnf.x5t#S256`.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): certificate paths, extensions, key usage, and revocation lists.
- [RFC 8941 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc8941.html): Byte Sequence and List serialization used by RFC 9440.
- [Spring Security 7.0 — X.509 Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/x509.html): X.509 pre-authentication, Servlet certificate attributes, and principal extraction.
- [Spring Security 7.1 — X509Configurer Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/X509Configurer.html): configuring X509AuthenticationFilter and principal extractors.
- [Envoy — HTTP Header Manipulation: XFCC](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/headers): XFCC syntax and how certificates are forwarded/sanitized.
- [Envoy — HttpConnectionManager ForwardClientCertDetails](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto): SANITIZE, FORWARD_ONLY, APPEND_FORWARD, SANITIZE_SET, and ALWAYS_FORWARD_ONLY modes.

**Key takeaway:** When TLS terminates at a reverse proxy, the original client certificate does not automatically appear in the backend Servlet container. The proxy must verify the client on outer TLS, remove caller-sent headers, and forward the certificate under a clear contract such as RFC 9440. The backend must authenticate the proxy on a separate connection, and only then trust and map the certificate in the header. In Spring Security, `x509()` by default reads the TLS peer certificate supplied by the Servlet container; behind proxy mTLS, that is usually the proxy certificate. Keep proxy identity, original client certificate, and application principal separate throughout the entire authentication/authorization flow.
