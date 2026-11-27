# mTLS-Bound Tokens and Matching Tokens Against Connection Certificates

In **Spring Security OAuth 2.0 / OIDC Resource Server**, a standard Bearer Access Token has an important property: whoever holds the token can try using it. If the token is stolen from logs, a workstation, a proxy, or a compromised connection, the thief can send requests to the API until the token expires or is revoked.

**Mutual TLS (mTLS) certificate-bound Access Tokens** under **RFC 8705** add a constraint: the Authorization Server binds the Access Token to the **client's X.509 certificate**. When the client calls the Resource Server, it must prove possession of the corresponding private key via TLS client authentication. The Resource Server verifies the certificate at the TLS layer, computes the certificate's thumbprint, and compares it against the confirmation claim in the token.

Three components must go together:

- **Access Token**: credential carrying the issuer, subject/client, audience, scopes, and expiration.
- **Client certificate**: X.509 certificate presented in the TLS handshake; the corresponding private key resides on the client.
- **Certificate binding**: the `cnf.x5t#S256` claim in the Access Token containing the SHA-256 thumbprint of the bound certificate.

**An mTLS-bound token is not a new token replacing the Access Token.** The client still sends the Access Token in the Authorization header using the Bearer mechanism while presenting the matching client certificate on the TLS connection. The Resource Server accepts the token only when the token is valid and the connection certificate matches the binding.

This lesson is part of the **Proof-of-Possession Tokens** chapter, using **Java 17+, Spring Boot 3.x, Spring Security 6.x** as context. It covers RFC 8705, token issuance, the `cnf` claim, how `x5t#S256` is computed, TLS configuration, Resource Server integration, TLS termination behind proxies, certificate lifecycle, testing, and operations. All URLs, certificates, and tokens in the examples are dummy data.

## 1. Bearer Tokens and the Stolen-Token Problem

With a standard Bearer token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The Resource Server verifies the token. If the token is valid and scopes permit, the request is processed. The server has no cryptographic proof that the sender is the original client that received the token.

~~~text
Legitimate client ---- Bearer token T ----> Resource Server
       |
       +---- Token T copied ----> Attacker
                                     |
                                     +---- Bearer T ----> Resource Server
~~~

The attacker needs no private key beyond holding T. TLS protects the token in transit, yet does not prevent the token from being copied from storage, endpoints, or logs.

With an mTLS-bound token:

~~~text
Authorization Server issues T
  cnf.x5t#S256 = thumbprint(certificate C)

Client holds private key matching C
        |
        +-- TLS handshake to Resource Server
        |      Client presents certificate C
        |      Proves private-key possession
        |
        +-- HTTP Authorization: Bearer T
                 |
                 v
          Resource Server
            - Verifies TLS client certificate
            - Verifies Access Token
            - Computes thumbprint(cert C)
            - Compares with token.cnf.x5t#S256
            - Checks scopes and domain permissions
~~~

An attacker who steals only T without the corresponding private key **cannot complete TLS client authentication with the bound certificate**. This is a **sender-constrained token** mechanism.

## 2. Three Concepts That Must Not Be Confused

| Component | Role | Where It Is Verified |
| --- | --- | --- |
| **Access Token** | Carries resource access permissions. | Spring Security JWT decoder or opaque-token introspection. |
| **Client certificate** | Proves private-key possession over TLS. | TLS server/proxy during handshake. |
| **Certificate binding** | Confirms the token was issued for that exact certificate. | Resource Server compares `cnf.x5t#S256` against the connection's certificate. |

Certificates can be used at two different OAuth stages:

1. **mTLS client authentication at the Authorization Server**: the certificate authenticates the OAuth client when calling the token endpoint.
2. **Certificate-bound Access Token at the Resource Server**: that same certificate is bound to the Access Token, and the client must prove possession when calling the API.

These two purposes are related, yet **not synonymous**. Using mTLS at the AS to authenticate the client does not automatically prove the Resource Server checked token-to-certificate binding. Conversely, the Resource Server can verify binding only when the AS issued the token with the confirmation claim per contract.

## 3. RFC 8705: Certificate-Bound Access Tokens

**RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens** defines how X.509 certificates are used in OAuth 2.0:

- Mutual TLS can be used to authenticate an OAuth client to the Authorization Server.
- An Access Token can be **bound to a client certificate**.
- The Resource Server verifies the connection's client certificate and compares its thumbprint against the token.

### 3.1. Confirmation Claim in a JWT Access Token

If the Access Token is a JWT, the payload might contain:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERTIFICATE_THUMBPRINT"
  }
}
~~~

`cnf` is the **confirmation claim**. In RFC 8705's certificate-bound profile, the `x5t#S256` member holds the SHA-256 thumbprint of the certificate.

### 3.2. Opaque Access Tokens

An opaque token cannot be decoded directly into JWT claims at the Resource Server. On introspection, the Authorization Server may return metadata:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-client",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERTIFICATE_THUMBPRINT"
  }
}
~~~

The Resource Server must use a **verified introspection response** as its binding source. If the AS does not return `cnf.x5t#S256` for a token expected to be certificate-bound, the Resource Server lacks sufficient information to verify the sender constraint and must reject per policy.

### 3.3. Token Type and Authorization Header

Certificate-bound Access Tokens under RFC 8705 are still typically sent with the **Bearer authorization scheme**:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The difference lies in the **TLS client certificate and the binding comparison step**, rather than switching to a new HTTP scheme. This differs from DPoP, where the client sends a proof in the `DPoP` header and uses token type `DPoP`.

Do not assume every Bearer token is certificate-bound. The Resource Server needs to know which tokens **must** carry a binding per the issuer/client/resource contract and reject them if the claim is missing.

## 4. How Is the `x5t#S256` Thumbprint Calculated?

`x5t#S256` is the **Base64url-encoded SHA-256 thumbprint of the DER-encoded X.509 certificate**.

~~~text
certificateDer = X509Certificate.getEncoded()
digest         = SHA-256(certificateDer)
thumbprint     = BASE64URL(digest) without padding
~~~

Key points:

- Hash the **DER certificate bytes**, not PEM text with headers/footers/newlines.
- Do not hash the standalone public key (SPKI) instead of the certificate.
- Do not hash the certificate chain or CA certificate if the token binding was created from the client leaf certificate.
- Do not use SHA-1.
- Base64url encoding must follow JOSE rules, with no padding.

### 4.1. Java Calculation Example

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.cert.CertificateEncodingException;
import java.security.cert.X509Certificate;
import java.util.Base64;

public final class CertificateThumbprints {

    private CertificateThumbprints() {
    }

    public static String x5tS256(X509Certificate certificate) {
        try {
            byte[] der = certificate.getEncoded();
            byte[] digest =
                MessageDigest.getInstance("SHA-256").digest(der);

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (CertificateEncodingException
                 | NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "Cannot calculate certificate thumbprint", ex);
        }
    }
}
~~~

This code only computes the thumbprint; **it does not verify the certificate chain, validity, EKU, revocation, or TLS handshake**. Those steps must be performed by the TLS stack or a trusted proxy component.

### 4.2. Why Not Compare Subject CN?

Two certificates can share the exact same Subject/CN while having different public keys or serial numbers. Conversely, a newly rotated certificate can have a similar Subject while having different DER bytes:

~~~text
Certificate C1:
  Subject = CN=orders-client
  thumbprint = H1

Certificate C2:
  Subject = CN=orders-client
  thumbprint = H2

H1 != H2
~~~

Binding uses the **exact certificate thumbprint**, not CN, SAN, or subject name strings. Subject/SAN fields can serve separate client-identification policies, but they do not replace `x5t#S256`.

## 5. Flow for Issuing a Certificate-Bound Token

The client holds certificate C and its corresponding private key. When obtaining an Access Token, the client sends a request over a TLS connection with client authentication to the Authorization Server.

~~~text
Client                         Authorization Server
  |                                    |
  | Create/receive certificate C       |
  | Hold private key k                 |
  |                                    |
  | TLS handshake with AS              |
  | Client Certificate: C              |
  | Proof of private-key possession    |
  |----------------------------------->|
  |                                    |
  | POST /oauth2/token                 |
  | grant_type=client_credentials ...  |
  |----------------------------------->|
  |                                    |
  | AS authenticates OAuth client per  |
  | mTLS policy (if configured)        |
  |                                    |
  | AS issues Access Token T           |
  | cnf.x5t#S256 = thumbprint(C)       |
  |                                    |
  | access_token=T, token_type=Bearer  |
  |<-----------------------------------|
~~~

In this example, mTLS both authenticates the client at the token endpoint and provides the certificate to bind the token. For authorization-code flow, refresh, or other grants, request details vary, but the binding principle must still follow RFC 8705 and the AS contract.

### 5.1. Example Token Request

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

The client certificate is presented during the **TLS handshake**, not sent as a form field. The server authenticates the client under its TLS certificate policy and can issue a token bound to the certificate's thumbprint.

### 5.2. Token Response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
~~~

If the token is a JWT, the `cnf` claim sits inside the AS-signed payload. If opaque, the Resource Server must obtain the binding via introspection.

### 5.3. Client Authentication and Token Binding Are Two Checks

Never jump to the conclusion:

> "The AS requires mTLS when obtaining a token, so every API receiving this token automatically knows the certificate."

The Resource Server may sit on a different domain, TLS listener, or proxy. It must **receive the client connection's certificate** and compare its thumbprint against the token. If the RS only receives a Bearer header over a regular TLS connection with no client certificate, it cannot prove possession of the bound certificate.

## 6. Calling the Resource Server with a Certificate-Bound Token

The client opens a TLS connection to the Resource Server, presents the matching certificate C, and sends Access Token T:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

The client certificate **does not appear in standard HTTP headers**. It is presented during the TLS handshake; the TLS server receives the peer certificate after client authentication is requested and succeeds.

The Resource Server checks:

~~~text
TLS connection
  - client certificate chain valid?
  - certificate unexpired and allowed for client auth?
  - TLS stack verified private-key possession?
          |
          v
HTTP Authorization: Bearer T
  - Access Token valid?
  - issuer/audience/exp/scope valid?
  - token has cnf.x5t#S256?
          |
          v
certificate thumbprint == token.cnf.x5t#S256?
          |
     +----+----+
     |         |
    Yes        No
     |         |
     v         v
 Continue    Reject
     |
     v
 Domain authorization
~~~

**Both the token and the certificate must be verified.** A TLS-trusted certificate that does not match the token must not be usable with that token; a token with a valid `cnf` claim on a TLS connection lacking a valid certificate must also be rejected.

## 7. The TLS Layer Must Verify the Client Certificate

mTLS means **both server and client authenticate certificates during the TLS handshake**:

- The client verifies the server certificate to ensure it is connecting to the right Resource Server.
- The Resource Server verifies the client certificate against trust anchors/policies.
- The TLS stack verifies private-key proof-of-possession during the handshake.
- The application retrieves the peer certificate accepted by the TLS stack and compares it against the token binding.

### 7.1. Certificate Checks to Consider

| Check | Meaning |
| --- | --- |
| Certificate chain | Builds a chain to a configured trust anchor. |
| Validity period | `notBefore`/`notAfter` valid for the current time. |
| Key usage | Appropriate for client authentication. |
| Extended Key Usage | Includes `clientAuth` per policy. |
| Algorithm/key strength | Meets security baseline. |
| Certificate revocation | CRL/OCSP or revocation mechanism per policy. |
| Name/identity policy | SAN/subject/issuer if the system enforces extra identity policies. |
| Thumbprint binding | Active leaf certificate matches `cnf.x5t#S256` in the token. |

**Thumbprint matching does not replace certificate validation.** If a server merely hashes a certificate self-sent by the client in an HTTP body without verifying the chain and private-key possession, an attacker can send a copy of the public certificate and spoof the binding.

### 7.2. Certificate Revocation Differs from Access Token Revocation

If a certificate is revoked at the CA:

- The TLS server needs a policy to check CRL/OCSP or an appropriate certificate status source.
- The fact that a certificate's thumbprint matches the token does not prove the certificate is still permitted.
- If the TLS stack does not check certificate revocation per policy, a revoked certificate may still pass chain validation depending on implementation.
- Access Tokens may need to be revoked separately at the AS; the two lifecycles do not synchronize automatically.

When a private key/certificate is compromised, you typically must **revoke the certificate, revoke tokens bound to it, issue a new certificate, and mint new tokens**.

## 8. Configuring Inbound mTLS in Spring Boot

With embedded Tomcat/Jetty supporting appropriate SSL settings, for example:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/orders-server.p12
    key-store-type: PKCS12
    key-store-password: CHANGE_ME_FROM_SECRET_STORE
    trust-store: file:/run/secrets/client-ca-trust.p12
    trust-store-type: PKCS12
    trust-store-password: CHANGE_ME_FROM_SECRET_STORE
    client-auth: need
~~~

Meaning:

- **key-store** holds the server certificate/private key so clients can verify the API.
- **trust-store** holds the CAs/trust anchors the API uses to verify client certificates.
- **client-auth: need** requires clients to present a certificate; handshakes without a valid certificate fail before reaching controllers/security filters.

The password values above are placeholders and must come from a secret manager/environment per deployment practice. Never commit passwords or private keys to a repository.

### 8.1. `client-auth`: `need`, `want`, and `none`

| Value | General Behavior | Use Case |
| --- | --- | --- |
| `need` | Requires a client certificate during the TLS handshake. | Listener/endpoint requiring mTLS for all connections. |
| `want` | Requests a certificate but may continue without one, depending on TLS/container behavior. | Use only when the app has explicit per-route policies and ensures missing certs never reach protected endpoints. |
| `none` | Does not request a client certificate. | APIs not using inbound mTLS. |

**`client-auth: need` normally applies at the TLS connector/listener level**, not just a single controller. If the same listener serves public endpoints not requiring mTLS, design separate listeners/gateways or controlled routing; never assume a Spring Security path matcher can demand a TLS handshake certificate after the handshake has already finished.

### 8.2. Server Trust Store vs. Client Trust Store

- Client trust store: client trusts the API's server certificate.
- Server trust store: API trusts the CAs issuing client certificates.

The two sides may use different CAs. Do not load the entire public internet CA bundle into the client-certificate trust store if only a specific internal CA/PKI group is permitted to call the API.

### 8.3. Separating Public and mTLS Listeners

A deployment might have:

~~~text
Public HTTPS listener :443
  - public endpoints
  - Bearer tokens under separate policy

mTLS listener :8443
  - requires client certificate
  - certificate-bound Access Tokens
  - accepts only from registered networks/clients
~~~

Separating listeners reduces confusion between routes that require mTLS and routes that do not. Still, every path to protected resources must be controlled; never let the same certificate-bound endpoint be accidentally exposed on the public listener bypassing the binding check.

## 9. Matching Tokens Against Certificates in a Spring Security Application

Spring Security can validate JWT Access Tokens or introspect opaque tokens. However, **enabling JWT/opaque Resource Server alone does not automatically guarantee token-to-TLS-certificate thumbprint binding in all configurations**. The application needs an integration that enforces matching the connection's certificate against `cnf.x5t#S256`.

### 9.1. X.509 Authentication Does Not Automatically Replace Certificate-Bound Token Validation

Spring Security provides `x509()` to authenticate a client certificate and map the subject/certificate identity to a principal. That is **certificate-based authentication**. It does not automatically enforce:

~~~text
verified Access Token.cnf.x5t#S256
             ==
thumbprint(TLS peer certificate)
~~~

If an endpoint requires **an OAuth Access Token bound to a certificate**, this comparison must be performed explicitly. Do not use CN mapping as a substitute for `x5t#S256`.

### 9.2. Retrieving the Peer Certificate from a Servlet Request

When TLS client authentication is handled directly by the Servlet container, the peer certificate chain can typically be retrieved from a request attribute per the Servlet API:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.security.cert.X509Certificate;

public final class PeerCertificateExtractor {

    private static final String CERT_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    private PeerCertificateExtractor() {
    }

    public static X509Certificate requireLeaf(
            HttpServletRequest request) {
        Object value = request.getAttribute(CERT_ATTRIBUTE);

        if (!(value instanceof X509Certificate[] chain)
                || chain.length == 0
                || chain[0] == null) {
            throw new IllegalArgumentException(
                "A verified TLS client certificate is required");
        }

        return chain[0];
    }
}
~~~

In the Servlet API, the standard attribute typically holds an array of X.509 peer certificates for the TLS connection, with the leaf certificate first. Verify the exact behavior of your **container/connector**; if TLS terminates at a proxy, the application may not see the client's original certificate in this request attribute.

**Never replace this extractor by reading an arbitrary client-sent header**, such as `X-Client-Cert`, unless a proxy has verified it and stripped incoming headers. Proxy handling is covered in Section 13.

### 9.3. Comparing Thumbprints in Java

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import org.springframework.security.authentication.BadCredentialsException;

public final class CertificateBindingVerifier {

    private CertificateBindingVerifier() {
    }

    public static void verify(
            String expectedX5tS256,
            X509Certificate peerCertificate) {

        if (expectedX5tS256 == null
                || expectedX5tS256.isBlank()
                || peerCertificate == null) {
            throw new BadCredentialsException(
                "Certificate-bound token requirements are missing");
        }

        String actual =
            CertificateThumbprints.x5tS256(peerCertificate);

        boolean matches = MessageDigest.isEqual(
            expectedX5tS256.getBytes(StandardCharsets.US_ASCII),
            actual.getBytes(StandardCharsets.US_ASCII));

        if (!matches) {
            throw new BadCredentialsException(
                "Access token is not bound to this TLS certificate");
        }
    }
}
~~~

`MessageDigest.isEqual` compares byte arrays in a manner better suited for sensitive values than ordinary string comparison; nonetheless, the entire implementation should be reviewed against security requirements. The expected value must come from a **verified Access Token** or an authenticated introspection response.

## 10. Integrating with `JwtAuthenticationProvider` Using `AuthenticationManagerResolver`

An important technical detail: `OAuth2TokenValidator<Jwt>` is typically invoked during token decoding and **does not directly receive `HttpServletRequest` or the peer certificate**. Thus, you cannot simply write a validator needing the certificate and expect Spring to inject the TLS request automatically.

An illustrative integration approach for Servlet is:

1. Use `JwtDecoder` to verify the standard Access Token.
2. Use `JwtAuthenticationProvider` to build the `Authentication`.
3. Wrap the `AuthenticationManager` per `HttpServletRequest`.
4. After the token is verified, read `cnf.x5t#S256` from the verified `Jwt`.
5. Retrieve the peer certificate from the TLS connection's request attribute.
6. Compare the thumbprint before returning the `Authentication` to Spring Security.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.security.cert.X509Certificate;
import java.util.Map;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.jwt.JwtDecoder;

public final class MtlsBoundAuthenticationManagerResolver
        implements AuthenticationManagerResolver<HttpServletRequest> {

    private final AuthenticationManager delegate;

    public MtlsBoundAuthenticationManagerResolver(
            JwtDecoder jwtDecoder) {
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(jwtDecoder);
        this.delegate = provider::authenticate;
    }

    @Override
    public AuthenticationManager resolve(
            HttpServletRequest request) {

        // The certificate must come from a trusted TLS stack.
        X509Certificate peer =
            PeerCertificateExtractor.requireLeaf(request);

        return authentication -> {
            Authentication result =
                delegate.authenticate(authentication);

            if (!(result instanceof JwtAuthenticationToken jwtAuth)) {
                throw new BadCredentialsException(
                    "Expected JWT bearer authentication");
            }

            Map<String, Object> cnf =
                jwtAuth.getToken().getClaimAsMap("cnf");

            Object rawThumbprint = cnf == null
                ? null : cnf.get("x5t#S256");

            if (!(rawThumbprint instanceof String expected)) {
                throw new BadCredentialsException(
                    "Certificate confirmation claim is missing");
            }

            CertificateBindingVerifier.verify(expected, peer);
            return result;
        };
    }
}
~~~

This is an **integration pattern**, not a complete production configuration. You must add:

- A `JwtDecoder` configured to verify issuer, audience, expiration, not-before, and allowed algorithms.
- A TLS listener that actually requires/verifies client certificates.
- Appropriate error handling/challenges.
- Separate policies for non-certificate-bound token types; endpoints requiring mTLS-bound tokens must reject tokens missing `cnf`.
- Request tests through the real TLS connector/container.
- If supporting multiple issuers/tenants, the resolver must select decoders from trusted configuration; never derive JWKS URIs from an unverified token.

### 10.1. Wiring the Resolver into `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MtlsApiSecurityConfiguration {

    @Bean
    SecurityFilterChain mtlsApiChain(
            HttpSecurity http,
            MtlsBoundAuthenticationManagerResolver resolver)
            throws Exception {

        return http
            .securityMatcher("/mtls-api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/mtls-api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

In the example, `AuthenticationManagerResolver` captures a reference to the request to read the peer certificate when authentication executes. Verify filter ordering and container lifecycle for your specific application. In other versions/framework integrations, you may choose a dedicated authentication provider/filter; the invariant remains: **the binding check must complete before the `Authentication` is used to authorize endpoints**.

### 10.2. Audience/Issuer Validators Are Still Required

The resolver above illustrates only certificate binding; it does not establish the entire JWT trust policy. A decoder must configure issuer and audience, conceptually:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(
        "https://identity.example.test")
        .build();

// Attach validators:
// - exact issuer
// - audience contains orders-api
// - exp/nbf per clock policy
// - allowlisted signing algorithms
~~~

Never pass a token to the binding verifier before the decoder verifies its signature and claims. Never trust `cnf` from a JWT whose payload was merely base64-decoded.

## 11. Integrating with `OpaqueTokenIntrospector`

If the Access Token is opaque, use introspection to obtain the principal:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERTIFICATE_THUMBPRINT"
  }
}
~~~

You can build a wrapper around `OpaqueTokenIntrospector` or a dedicated `AuthenticationManager`:

1. Introspect the token over HTTPS using the Resource Server's client credentials.
2. Proceed only if `active` is boolean `true`.
3. Read `cnf.x5t#S256` from the principal attributes returned by the trusted introspector.
4. Compare it against the request's peer certificate.
5. If binding is missing or mismatches, reject authentication.
6. Only then apply scope and domain authorization.

Never use the raw opaque token as a certificate thumbprint, and never try decoding an opaque token to find `cnf`. If the AS does not return `cnf`, the integration contract is insufficient for certificate-bound enforcement.

### 11.1. Do Not Turn Introspection Failures into a Bearer Fallback

A token issued by the AS with a certificate binding whose binding the RS cannot read must be rejected on an endpoint requiring mTLS-bound tokens. Never do:

~~~text
Introspection lacks cnf
   -> skip binding
   -> accept as Bearer token
~~~

That **downgrades the sender constraint** and defeats the original protection goal.

## 12. Where Do mTLS Client Authentication and Certificate-Bound Tokens Differ?

The two flows often share the same certificate, yet must be clearly distinguished:

### 12.1. Client Authentication at the Authorization Server

The client uses its certificate in the TLS handshake to the **token endpoint**. The AS authenticates the client by certificate and client registration mapping.

~~~text
Client -- mTLS certificate --> Authorization Server
                              |
                              +-- identifies OAuth client
~~~

### 12.2. Certificate Binding at the Resource Server

The client uses its certificate to connect to the **Resource Server**. The RS compares the thumbprint with the issued token.

~~~text
Client -- mTLS certificate + Access Token --> Resource Server
                                             |
                                             +-- verify cnf.x5t#S256
~~~

### 12.3. Comparison Table

| Scenario | AS Token Endpoint | Resource Server |
| --- | --- | --- |
| mTLS client authentication | Certificate authenticates the OAuth client. | Does not automatically prove token binding. |
| Certificate-bound Access Token | AS records thumbprint in token upon issuance. | Compares TLS peer certificate thumbprint with token. |
| Both enabled | AS can use cert to authenticate and bind token. | RS must still verify binding. |
| Cert only at AS | Client authenticates to AS. | If RS receives no cert, it cannot verify token binding. |
| Cert only at RS | RS can validate certificate. | Yet token must have been issued by AS with matching binding. |

**mTLS on one network hop does not automatically propagate to another hop.** A certificate on the client→AS connection does not automatically appear on the client→RS connection, and vice versa.

## 13. TLS Termination at a Reverse Proxy or API Gateway

A common deployment:

~~~text
Client -- mTLS --> Gateway -- HTTP/internal TLS --> Spring Resource Server
~~~

The gateway receives and validates the client certificate, while the TLS connection to Spring may be initiated by the **gateway**, not the client. Spring then sees the gateway's certificate or no peer certificate at all.

If the application grabs the certificate from the internal TLS connection and compares it to the token, it may be comparing the **gateway certificate** instead of the original client certificate. That fails or creates a trust gap.

### 13.1. Three Architectural Options

**Option A — End-to-end mTLS to the application:** TLS passthrough at the gateway or an architecture preserving the peer certificate all the way to the Resource Server. Spring receives the original client certificate from the TLS stack.

**Option B — Gateway verifies and forwards certificate identity over a trusted internal channel:** the gateway authenticates the mTLS client, then sends the verified certificate identity/representation to the application via a standard header or protected internal protocol. The application trusts this info only from an authenticated gateway; the gateway must strip any same-named header sent by clients.

**Option C — Gateway enforces token binding itself:** the gateway fully verifies both the token and certificate binding before forwarding requests. The backend trusts the gateway under an explicit security contract rather than assuming checks occurred without proof.

### 13.2. Forwarded Headers Must Not Be Trusted Directly

Do not do:

~~~http
X-Client-Certificate: -----BEGIN CERTIFICATE-----
...
~~~

if a client can send this header directly to the application. An attacker could declare any arbitrary certificate.

If using certificate forwarding:

- Use a standard mechanism/agreed format, such as **RFC 9440 — Client-Cert HTTP Header Field** where appropriate.
- The gateway must strip client-supplied headers before inserting its own forwarding header.
- The gateway→application hop must be protected, typically with mTLS and network policy.
- The application accepts forwarding headers only from an authenticated gateway/identity proxy.
- The gateway must verify the certificate chain and possession before asserting that certificate as the peer certificate.
- Enforce size limits, encoding checks, and safe certificate parsing.
- Never allow public network traffic to reach the backend directly and spoof internal headers.

**A forwarded certificate is a proxy assertion**, no longer a peer certificate received directly from the client by Spring's TLS stack. You must protect both the integrity of the assertion and the identity of the proxy.

### 13.3. Forwarded Headers Differ from X.509 Peer Certificates

Spring Boot/Tomcat can process `Forwarded`/`X-Forwarded-*` to reconstruct URLs, yet that does not mean the container automatically validates a certificate sent in a header. URL forwarding and **client certificate forwarding** are two different mechanisms; never blindly enable trust for all forwarded headers just to solve mTLS.

## 14. Certificate Rotation and Token Lifecycle

Suppose token T1 is bound to certificate C1:

~~~text
T1.cnf.x5t#S256 = thumbprint(C1)
~~~

The client rotates to certificate C2:

~~~text
thumbprint(C2) != thumbprint(C1)
~~~

T1 **does not automatically switch to bind C2**. If the client sends T1 over a TLS connection using C2, the Resource Server must reject it.

### 14.1. Rotation with Overlap

A workflow:

1. Generate C2 and store the new private key securely.
2. Register/get C2 accepted by the AS per client registration policy.
3. Obtain Access Token T2 with `cnf.x5t#S256 = thumbprint(C2)`.
4. During transition, the client may retain C1/T1 if policy allows and C1 is unrevoked.
5. Shift traffic to C2/T2.
6. Revoke T1/credential C1 or let its lifecycle expire per policy.
7. Confirm no service/replica still accepts tokens bound to C1 if C1 was compromised.

Never obtain a new token bound to C2 and send it over a TLS connection still presenting C1.

### 14.2. Expired or Revoked Certificates

TLS certificate validation must check validity and revocation per policy. A token's `exp` may still be in the future after a certificate expires, yet new handshakes must reject the invalid certificate. Also revoke Access Tokens bound to a compromised certificate at the AS so other checks reflect the true status.

### 14.3. Connection Pooling and HTTP/2

Certificates are presented when establishing the TLS connection. Client connection pools must be partitioned by **certificate identity/key material**:

- Never reuse a connection established with C1 and assume it presents C2.
- When rotating certificates, open new TLS connections using C2.
- HTTP/2 can multiplex many requests over one connection; all streams share that connection's TLS peer certificate.
- If multiple tenants/service identities use different certificates, do not share pools/connections indiscriminately.

Swapping certificate files on disk does not change the certificate already negotiated on an open TLS connection.

## 15. TLS Session Resumption and Certificate Identity

TLS session resumption reuses session state to cut handshake overhead. The Resource Server must rely on the **TLS stack having authenticated the current connection's peer identity**, even under resumption; never assume that a request lacking a certificate attribute because a resumed handshake omitted the full chain means the client has no identity.

When configuring TLS termination/proxies or session resumption:

- Verify whether the container exposes the peer certificate properly on resumed sessions.
- Ensure session tickets/caches do not outlive certificate rotation/revocation policies.
- When a certificate is compromised, invalidate TLS sessions/tickets and close existing connections as needed.
- Verify token binding against the **connection's actual certificate identity**, not an unrelated certificate cached in an application session.

Details depend on TLS version, provider, server connector, and session ticket operations; test on the real production stack.

## 16. How Does DPoP Differ from mTLS-Bound Tokens?

Both mechanisms bind tokens to a client key, but operate at different layers:

| Criterion | DPoP | mTLS-Bound Token |
| --- | --- | --- |
| Proof of possession | Client signs a DPoP proof JWT. | TLS client authentication with certificate/private key. |
| Public key binding | `cnf.jkt` is a JWK thumbprint. | `cnf.x5t#S256` is a certificate thumbprint. |
| Request proof | Every request has a `DPoP` header. | Possession proof occurs during the TLS handshake/connection. |
| Access Token header | `DPoP` scheme. | Typically `Bearer`. |
| Verification components | Application/proof verifier and replay cache. | TLS stack/proxy + token binding verifier. |
| Infrastructure | No client certificate required. | Requires client cert PKI/trust config at RS or proxy. |
| Best fit | Public clients, browser/native apps where client certs are hard. | Service-to-service, enterprise PKI, workload identity. |

DPoP proofs typically bind method/URI and Access Token hash per request. mTLS-bound tokens rely on the TLS connection's verified certificate; they do not sign the HTTP body or individual method/URI pairs like DPoP.

## 17. TLS Certificate Identity Is Not Automatically User Identity

A certificate can represent:

- An OAuth client/service.
- A workload or device.
- An application installation.
- An organization under PKI policy.

It does not inherently prove who the **end user** is. If a service uses mTLS-bound Access Tokens across multiple users, tokens still need appropriate subject/claims and domain policies.

### 17.1. Subject and SAN

Additional policies may exist:

~~~text
certificate SAN URI = spiffe://example.test/ns/orders/sa/worker
token client_id      = orders-worker
token aud            = orders-api
token cnf.x5t#S256   = thumbprint(certificate)
~~~

SAN/URI/subject values can help map workload identity if defined by PKI contract. However, RFC 8705 binding still relies on the **certificate thumbprint**, not a CN string comparison.

### 17.2. Scope and Tenant Authorization Are Still Required

A valid certificate for `service-orders` with a properly bound token may be allowed to call the API yet still must not access all tenants:

~~~text
TLS certificate valid
  AND Access Token valid
  AND certificate thumbprint matches cnf
  AND aud = orders-api
  AND scope = orders.read
  AND workload belongs to tenant alpha
  AND order belongs to alpha
~~~

If any required condition is missing, reject. **mTLS-bound tokens do not replace BOLA/tenant ownership checks.**

## 18. Common Implementation Mistakes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Enabling mTLS without reading `cnf`. | Any trusted client cert can use an unbound token. | Compare TLS peer cert thumbprint with token. |
| Checking `cnf.x5t#S256` without requiring mTLS. | Client can send a public cert copy without proving private-key possession. | Mandatory TLS client authentication. |
| Comparing CN/SAN instead of thumbprint. | Two different certificates can share the same name. | RFC 8705 certificate thumbprint. |
| Hashing PEM text instead of DER bytes. | Thumbprint mismatches. | SHA-256 of `certificate.getEncoded()`. |
| Hashing public key/SPKI instead of certificate. | Wrong binding algorithm. | Hash DER-encoded X.509 leaf certificate. |
| Using CA certificate instead of leaf client cert. | Binding does not represent connection certificate. | Use peer leaf certificate. |
| Skipping certificate chain/EKU/validity checks. | Self-signed or wrong-purpose certs could be accepted. | TLS truststore/client-auth policy. |
| Using `x509()` as if it checks `cnf` itself. | X.509 principal is authenticated, but token binding is unchecked. | Custom token-certificate binding check. |
| AS uses mTLS, but RS lacks client cert. | Binding is not enforced at the resource. | mTLS at RS or trusted gateway assertion. |
| Trusting client-sent `X-Client-Cert`. | Header spoofing, forged peer certificate. | Strip header; trust only authenticated proxies. |
| Proxy terminates TLS, yet app hashes proxy cert. | Compares wrong certificate identity. | Forward original client cert via trusted channel or end-to-end mTLS. |
| Token T1 bound to C1, but client rotates to C2. | Thumbprint mismatch. | Obtain new token bound to C2. |
| Not checking CRL/OCSP per policy. | Revoked certificates may remain usable depending on TLS stack. | Configure certificate revocation checking. |
| Sharing HTTP connection pool across certs. | Requests travel on a connection with a different peer cert. | Partition pools/connections by certificate identity. |
| Letting bound tokens pass a non-mTLS Bearer listener. | Bypasses sender constraint. | Block any route/listener not enforcing binding. |
| Testing only the matching certificate. | Misses mismatch/missing cert/proxy bypass bugs. | Negative tests and real TLS integration tests. |

## 19. Testing Certificate-Bound Access Tokens

Tests must run through a **real TLS handshake** or a controlled test proxy verifying certificates. Mocking request headers alone does not prove the client possesses the private key.

### 19.1. Test Matrix

| Scenario | Expected Result |
| --- | --- |
| Token bound to C1, TLS connection presents valid C1 | Passes certificate binding, proceeds to authorization. |
| Token bound to C1, TLS connection presents C2 | **Reject**. |
| Token bound to C1, no client cert | TLS handshake rejected if listener requires mTLS. |
| Untrusted certificate chain | TLS handshake fails. |
| Expired certificate | TLS handshake fails validation. |
| Certificate revoked per policy | Rejected via CRL/OCSP or configured revocation mechanism. |
| Token missing `cnf` on mTLS-bound-required endpoint | Reject; no Bearer fallback. |
| Malformed/mismatched `cnf.x5t#S256` | Reject. |
| Token invalid signature/expired/wrong issuer | Reject even if cert matches. |
| Token wrong audience | Reject. |
| Token matching cert, missing scope | 403 per authorization. |
| Client sends forged certificate header | Never trust headers from public clients. |
| Proxy forwards verified cert | Accept only when proxy/channel sits inside trust boundary. |
| Client rotates C1 → C2, keeps using T1 | Reject; T1 remains bound to C1. |
| New token T2 bound to C2, connection uses C2 | Passes binding. |
| HTTP/2 connection using C1 sends token T2 bound to C2 | Reject. |
| Public non-mTLS listener calls protected endpoint | Must be blocked by route/architecture policy. |

### 19.2. Unit Test for Thumbprint

Test the helper with a test certificate fixture:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import java.security.cert.X509Certificate;

class CertificateThumbprintsTest {

    @Test
    void sameDerCertificateHasStableThumbprint() {
        X509Certificate cert = loadTestCertificate();

        String first =
            CertificateThumbprints.x5tS256(cert);
        String second =
            CertificateThumbprints.x5tS256(cert);

        assertEquals(first, second);
    }

    private X509Certificate loadTestCertificate() {
        // Load a certificate fixture created specifically for tests.
        // Never use production certificates or private keys.
        throw new UnsupportedOperationException(
            "Provide a test certificate fixture");
    }
}
~~~

`loadTestCertificate` is a fixture hook to implement using a dedicated test resource. This only illustrates testing thumbprint stability, not testing an mTLS handshake.

### 19.3. Integration Testing Over TLS

1. Generate a test CA, client certificates C1/C2, and a server certificate.
2. Configure the Resource Server test listener to trust the test CA and require client certificates.
3. Mint a test JWT with `cnf.x5t#S256` computed from C1.
4. Use an HTTP client keystore holding C1 to call the endpoint; verify authentication passes.
5. Call with the same token using connection/keystore C2; must be rejected.
6. Call without a client certificate; TLS handshake must fail when the listener uses `client-auth: need`.
7. Send a token missing `cnf`; certificate-bound endpoints must reject it.
8. Send tokens with wrong issuer/audience/scope to confirm other validators still work.
9. If behind a proxy, rerun through the proxy and attempt to spoof forwarded certificate headers.
10. Test certificate rotation, connection pooling, and certificate revocation policies.

Pure `MockMvc` cannot prove the container verified a TLS client certificate handshake. `MockMvc` can help test security logic once a certificate fixture is injected, yet **separate end-to-end TLS tests** are required to verify the transport boundary.

## 20. Operations and Observability

Useful metrics:

- TLS handshake successes/failures grouped by cause.
- Client certificate chain/validity/revocation failures.
- Token validation failures (issuer/audience/expiration/signature).
- Certificate thumbprint binding mismatches.
- Missing `cnf` on endpoints requiring certificate-bound tokens.
- Upcoming client certificate rotations/expirations.
- Proxy forwarded-certificate validation failures.
- Requests rejected for token/certificate mismatches.

Never log private keys, raw Access Tokens, Authorization headers, or unnecessary full certificate chains. Certificates are public material yet can contain sensitive identifying info; log only fingerprints/serial/issuer metadata per policy and access controls.

### 20.1. Certificate Expiry Monitoring

Track `notAfter` to rotate proactively before clients lose the ability to open TLS connections. Alert early enough for clients to:

- Register the new certificate.
- Obtain Access Tokens bound to the new thumbprint.
- Refresh connection pools.
- Confirm old tokens are revoked/expired per policy.

### 20.2. Trust Store Updates

When adding/removing CAs:

- Roll out truststores cleanly under change control.
- Monitor affected clients.
- Avoid trusting broader CAs than necessary.
- Confirm all replicas have uniform trust configuration.
- Plan how open connections/sessions established prior to the trust change are handled.

### 20.3. Fail Closed When Peer Certificate Cannot Be Obtained

If an endpoint requires mTLS-bound tokens yet the app cannot read the certificate:

- Never fall back to comparing CN from the token.
- Never trust certificate headers from clients.
- Never skip binding because "the gateway probably checked it."
- Inspect the proxy contract or reject the request.

**If binding cannot be verified, the token must not be treated as satisfying the sender constraint.**

## 21. Implementation Roadmap

1. **Select client certificate PKI:** CA, issuance, identity mapping, key protection, expiry, and revocation.
2. **Align RFC 8705 with the Authorization Server:** mTLS client authentication, certificate-bound token issuance, and `cnf.x5t#S256`.
3. **Define token format:** JWTs can read claims after signature validation; opaque tokens must introspect `cnf`.
4. **Configure mTLS at the Resource Server:** truststore, client-auth policy, listener/route boundaries.
5. **Read the peer certificate accurately:** directly from the TLS stack or from an integrity-protected trusted proxy assertion.
6. **Compute standard thumbprints:** SHA-256 over the DER leaf certificate, unpadded Base64url.
7. **Integrate Spring Security:** token validation + certificate binding before authorization; do not confuse `x509()` with `cnf` comparison.
8. **Keep other validators:** issuer, audience, expiration, algorithms, scopes, tenant/owner.
9. **Handle TLS termination:** end-to-end mTLS or standardized trusted forwarding; strip client-supplied headers.
10. **Design certificate rotation/revocation:** old tokens stay bound to old certs; issue new tokens after rotation.
11. **Test over real TLS:** matching/wrong/missing/revoked certificates, missing/mismatched `cnf`, proxy spoofing.
12. **Monitoring and runbooks:** certificate expiry, truststore rollouts, mismatches, handshake errors, and emergency revocation.

**Remember:** An mTLS-bound Access Token is an **Access Token bound to an X.509 client certificate**. The Authorization Server sets `cnf.x5t#S256` to `Base64url(SHA-256(DER certificate))`; the client presents that exact certificate in the TLS handshake to the Resource Server; the Resource Server verifies the certificate at the TLS layer, validates the token, and compares thumbprints. **mTLS client authentication at the token endpoint does not automatically prove the Resource Server checked the binding**. Spring Security needs an integration enforcing the comparison before authorization; TLS termination via proxy must protect the forwarded certificate identity. Certificate binding reduces standalone token-theft risk, but still requires TLS, certificate lifecycle management, token validation, scopes, and domain authorization.

## References

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 9440 — Client-Cert HTTP Header Field](https://www.rfc-editor.org/rfc/rfc9440).
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html).
- [Spring Boot — SSL Configuration](https://docs.spring.io/spring-boot/reference/features/ssl.html).
