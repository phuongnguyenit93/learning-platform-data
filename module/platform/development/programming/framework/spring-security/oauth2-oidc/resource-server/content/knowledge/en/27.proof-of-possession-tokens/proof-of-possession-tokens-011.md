# TLS Authentication Does Not Automatically Replace Token-to-Certificate Binding Checks

In OAuth 2.0 Mutual-TLS (mTLS), client and server can authenticate each other's certificates when establishing a TLS connection. This tells the Resource Server **which certificate the TLS connection peer is using** and whether that certificate is accepted by the trust policy. However, TLS authentication alone **is not enough to prove the submitted access token belongs to that exact certificate**.

Suppose client A receives an access token bound by the Authorization Server to certificate A. An attacker who steals the token without A's private key can open a different mTLS connection using a valid certificate B. If the Resource Server checks only "does the TLS connection have a valid client certificate," it may accept certificate B and still honor A's token. To prevent this, the Resource Server must **compare the client certificate on the connection against the certificate thumbprint bound in the token**.

RFC 8705 defines **certificate-bound access tokens**. With a JWT access token, the Authorization Server can include a confirmation claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-client-certificate"
  }
}
~~~

`cnf.x5t#S256` is the SHA-256 thumbprint of the client X.509 certificate, calculated from its DER encoding and Base64URL-encoded without padding. Upon receiving a request, the Resource Server must verify:

1. The TLS peer certificate is authenticated per trust policy.
2. The access token is verified per the JWT or introspection profile.
3. The token contains the appropriate confirmation claim.
4. The thumbprint in the token **matches exactly** the leaf client certificate on the connection carrying the request.

**TLS authenticates the connection; certificate binding verifies that the token is being used with the exact bound certificate.** These two checks complement each other.

## 1. TLS Server Authentication, mTLS Client Authentication, and Token Binding

Three commonly confused concepts:

| Mechanism | Who Proves What? | Does It Verify Token-to-Certificate Binding? |
| --- | --- | --- |
| Standard TLS (one-way TLS) | Client verifies server certificate; server proves server identity to client | No. Typically the server receives no client certificate |
| mTLS | Client and server verify peer certificates during the TLS handshake | Insufficient. Only proves the peer holds a certificate valid under TLS policy |
| Certificate-bound access token | Resource Server compares connection's client certificate with confirmation thumbprint in token | **Yes**, if binding verification is properly enforced |

### Standard TLS

In standard HTTPS, the server presents a server certificate so the client can verify hostname, chain, validity period, and trust anchor. The client normally **does not present a certificate**.

~~~text
Browser / API client                  Resource Server
       |                                    |
       | -------- TLS ClientHello --------> |
       | <------- Server Certificate ------ |
       | -- verify server identity -------- |
       |                                    |
       | ===== TLS application data =====> |
~~~

The server certificate in the diagram is **the server's certificate**, not the OAuth client's certificate. You cannot take the server certificate and compare it with `cnf.x5t#S256` of a client token.

### Mutual TLS

In mTLS, the server requests that the client present a certificate. The client proves possession of the corresponding private key during the TLS handshake; the server verifies the certificate chain and policy:

~~~text
OAuth client                         Resource Server
     |                                     |
     | -------- TLS ClientHello ---------> |
     | <------- Server Certificate ------- |
     | <------- CertificateRequest ------- |
     | -------- Client Certificate ------> |
     | -------- CertificateVerify -------> |
     |                                     |
     |       TLS handshake complete       |
     |                                     |
     | ===== HTTP request + Bearer T =====>|
~~~

mTLS tells you the connection peer proved possession of the client certificate's private key. Yet if the request also carries a Bearer token unrelated to that certificate, the Resource Server still must check that relationship.

### Certificate-Bound Access Token

When the Authorization Server issues a certificate-bound token, it records the certificate's thumbprint under the agreed issuance mechanism. The Resource Server receives the token and certificate at request time, computes the thumbprint, and compares them:

~~~mermaid
flowchart TD
    A["Client opens mTLS to Resource Server"] --> B["TLS checks certificate chain and proof of possession"]
    B --> C["Client sends Bearer access token T"]
    C --> D["Resource Server verifies JWT or introspects token"]
    D --> E["Read cnf.x5t#S256 from token"]
    B --> F["Get leaf client certificate of TLS request"]
    E --> G["Compare thumbprints"]
    F --> G
    G --> H{"Match and both sides valid?"}
    H -- "Yes" --> I["Proceed to scope/role/object authorization"]
    H -- "No" --> J["Reject token/request"]
~~~

If the token and certificate do not match, the token must not be accepted on that connection even if the certificate alone has a valid chain and the token alone has a valid signature.

## 2. RFC 8705: Two Related Capabilities with Different Purposes

RFC 8705 describes two important capabilities:

1. **OAuth 2.0 Mutual-TLS Client Authentication:** The OAuth client authenticates to the Authorization Server using a client certificate when calling the token endpoint or supported OAuth endpoints.
2. **OAuth 2.0 Certificate-Bound Access Tokens:** The access token is bound to a client certificate, and the Resource Server verifies the client certificate when the token is used.

A system may enable one or both capabilities. **Never infer that enabling mTLS client authentication at the token endpoint means every access token is automatically certificate-bound.** Confirm that the Authorization Server actually emits the confirmation claim and the Resource Server actually checks it.

### mTLS Client Authentication at the Token Endpoint

The client obtains a token over an mTLS connection:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

During the TLS handshake, the client presents its certificate and proves possession of the private key. The Authorization Server identifies the client per the configured certificate mapping/registration. Then the AS issues a token per policy.

If the AS is configured to issue **certificate-bound access tokens**, the token may contain:

~~~json
{
  "cnf": {
    "x5t#S256": "thumbprint-of-certificate-used-for-binding"
  }
}
~~~

### Resource Server Checks Binding at Request Time

The client must continue using the exact corresponding certificate when calling the API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <certificate-bound-access-token>
~~~

The certificate does not reside in the HTTP Authorization header; it is exchanged during the **TLS handshake**. The Resource Server reads the peer certificate from the TLS connection or from metadata forwarded by a trusted proxy, and compares it against `cnf`.

| Question | mTLS Client Authentication | Certificate-Bound Access Token |
| --- | --- | --- |
| Where is it checked? | Authorization Server when OAuth client calls endpoint | Resource Server when receiving token |
| Evidence | Client certificate and proof of possession in TLS | Thumbprint in token matches request's client certificate |
| Authenticated subject | OAuth client at the AS | Token being used on the connection |
| Is `cnf` required? | Not necessarily for client authentication alone | **Yes, confirmation binding per profile** |
| Prevents stolen token use with another cert? | Not sufficient alone | Yes, if binding is checked |
| Replaces audience/scope validation? | No | No |

## 3. How Is the `x5t#S256` Thumbprint Calculated?

Per RFC 8705, the `x5t#S256` value is:

~~~text
BASE64URL-NOPAD(SHA-256(DER-ENCODED-CLIENT-CERTIFICATE))
~~~

Steps:

1. Select the **leaf client certificate** presented in the TLS handshake, not the root CA, intermediate CA, or server certificate.
2. Obtain the DER encoding of the certificate.
3. Compute SHA-256 over the full DER bytes.
4. Encode the digest using Base64URL.
5. Strip `=` padding.
6. Compare the result with `cnf["x5t#S256"]`.

Do not hash PEM text with headers/footers and newlines. Do not hash only the public key, subject DN, serial number, or certificate chain. None of those is RFC 8705's thumbprint formula.

### Java Helper

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
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(der);
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (CertificateEncodingException
                 | NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "Cannot calculate certificate thumbprint", exception);
        }
    }
}
~~~

SHA-256 must be available in the Java runtime. `X509Certificate.getEncoded()` returns the certificate's DER encoding. Never replace it with `getPublicKey().getEncoded()`, because that is the public key encoding rather than the certificate encoding.

### Constant-Time Comparison

Avoid arbitrary string comparison when a constant-time comparison can be used:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

static boolean sameThumbprint(String expected, String actual) {
    if (expected == null || actual == null) {
        return false;
    }
    return MessageDigest.isEqual(
        expected.getBytes(StandardCharsets.US_ASCII),
        actual.getBytes(StandardCharsets.US_ASCII));
}
~~~

Base64URL thumbprints are ASCII strings. Check for null/format and compare exact values; never change casing or strip characters to "make them match."

## 4. The `cnf` Confirmation Claim in a JWT Access Token

A certificate-bound JWT access token can have the structure:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "client_id": "orders-worker",
  "scope": "orders.read orders.write",
  "iat": 1763164800,
  "exp": 1763168400,
  "cnf": {
    "x5t#S256": "a-valid-base64url-certificate-thumbprint"
  }
}
~~~

This is an illustrative payload. The thumbprint value must be computed from a real certificate bound by the Authorization Server; the example string is not a valid certificate.

The Resource Server must run two groups of checks.

**Token validation**

- Verify the JWT signature against a trusted key/algorithm.
- Check issuer, audience, expiration, and token profile.
- Confirm the token is an access token intended for the API.
- Read the confirmation claim from the verified token.

**Certificate binding**

- Extract the client certificate of the exact TLS request.
- Identify the leaf certificate and ensure the TLS layer verified it.
- Compute `x5t#S256` using DER/SHA-256/Base64URL-no-padding.
- Compare with `cnf.x5t#S256`.
- Reject if the claim is missing, the certificate is missing, or there is a mismatch on an endpoint requiring binding.

### Never Read `cnf` Before Verifying the Token

A JWT payload is merely sender-supplied data until signature/issuer/profile are verified. Never Base64URL-decode and trust `cnf` or scopes before validation. If an attacker crafts a token with a `cnf` matching their own certificate, the token must still be rejected because the signature/issuer is invalid.

### What Does a Missing `cnf` Mean?

If an endpoint requires **certificate-bound tokens**, a token lacking `cnf.x5t#S256` must be rejected. Never fall back to "normal Bearer token" on the same route if policy requires proof-of-possession.

If an API has both Bearer-only endpoints and certificate-bound endpoints, partition policies clearly by route/resource. Never allow an unbound token to call a binding-required route just because it has a similar scope.

## 5. Opaque Access Tokens and Introspection Responses

Certificate-bound tokens do not have to be JWTs. An opaque token can be checked via an introspection endpoint; the response must provide confirmation data usable by the Resource Server.

Example response:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1763168400,
  "cnf": {
    "x5t#S256": "a-valid-base64url-certificate-thumbprint"
  }
}
~~~

Flow:

~~~text
Bearer opaque token
       |
       v
Reactive/Servlet OpaqueTokenIntrospector
       |
       v
active == true?
       |
       v
principal attributes include cnf.x5t#S256?
       |
       v
compare with TLS peer certificate thumbprint
       |
       v
scope/audience/tenant/object authorization
~~~

**`active: true` does not replace certificate binding.** If an API requires mTLS-bound tokens yet the introspection response lacks the required confirmation claim, the token does not satisfy the API's contract.

Some Authorization Servers return `cnf` only to authorized introspection clients or under a specific profile. Verify that your introspection client receives this field and that real responses match the schema. Never infer certificate binding simply because the AS returned `active=true`.

## 6. TLS Certificate Validation and Token Binding Are Two Separate Checks

A valid client certificate typically needs checking at the TLS layer per PKI policy:

- Certificate chain leads to a configured trust anchor.
- `notBefore`/`notAfter` validity window.
- Key usage / extended key usage suitable for client authentication.
- Subject/SAN or certificate identity mapping matching the client.
- Algorithm/key size meeting policy.
- Revocation via OCSP/CRL if required by the environment and configured in the TLS stack.
- Client proves possession of the private key during the handshake.

Next, token binding must also check:

- Token was issued by a trusted issuer.
- Token is intended for the right resource/audience.
- `cnf.x5t#S256` is present and valid.
- Thumbprint matches the client certificate of the **current request**.

| TLS Peer Certificate | Token | Binding Result |
| --- | --- | --- |
| Valid, thumbprint A | `cnf` contains A | Binding matches |
| Valid, thumbprint B | `cnf` contains A | **Mismatch, reject** |
| No client certificate | `cnf` contains A | **No proof, reject** |
| Untrusted certificate | `cnf` contains its thumbprint | TLS handshake must fail; binding cannot rescue it |
| Valid certificate A | Token lacks `cnf` | Reject if endpoint requires certificate-bound token |
| Valid certificate A | Invalid JWT signature, forged `cnf` contains A | Reject at token validation |

A CA-trusted client certificate cannot make an arbitrary access token valid on its own.

## 7. Retrieving the Client Certificate in Servlet and WebFlux

The Resource Server can verify binding only if it can retrieve **the peer client's certificate for that request**. How to retrieve it depends on the server stack and where TLS terminates.

### Servlet Container

When TLS terminates directly at the Servlet container, the Servlet API typically exposes the certificate chain via a request attribute:

~~~java
import java.security.cert.X509Certificate;
import jakarta.servlet.http.HttpServletRequest;

X509Certificate[] certificates = (X509Certificate[])
    request.getAttribute("jakarta.servlet.request.X509Certificate");

if (certificates == null || certificates.length == 0) {
    // No client certificate on this connection.
}

X509Certificate leafCertificate = certificates[0];
~~~

In legacy Spring Boot 2 / Spring Framework apps using `javax.servlet`, the attribute name under that Servlet namespace may differ. Verify the exact API/container version running in your project rather than hardcoding one namespace across all projects.

The certificate array typically puts the leaf certificate first, but code should rely on the container/connector contract and verify the exact certificate used in the handshake. Never take the first certificate from a client-supplied header.

### WebFlux

With Spring WebFlux running on a server supporting TLS metadata, the request can expose `SslInfo`:

~~~java
import java.security.cert.X509Certificate;
import org.springframework.http.server.reactive.SslInfo;
import org.springframework.http.server.reactive.ServerHttpRequest;

X509Certificate[] peerCertificates(ServerHttpRequest request) {
    SslInfo sslInfo = request.getSslInfo();
    if (sslInfo == null) {
        return new X509Certificate[0];
    }
    X509Certificate[] certificates = sslInfo.getPeerCertificates();
    return certificates != null
        ? certificates
        : new X509Certificate[0];
}
~~~

This snippet illustrates a WebFlux server exposing peer certificates via `SslInfo`. Exact behavior depends on the Reactor Netty/servlet adapter, TLS connector, and proxy topology. If TLS already terminated at an ingress, `getSslInfo()` may describe the connection from the ingress to the application rather than the client's original connection.

### Never Use `ThreadLocal` to Pass Certificates Through a Reactive Flow

In WebFlux, never store certificates or principals in a `ThreadLocal` assuming a request stays on one thread. Use `ServerWebExchange`, Reactor Context, and request-scoped APIs. A publisher can switch threads during processing.

## 8. TLS Termination at a Reverse Proxy: A Critical Trust Boundary

In production, TLS often terminates at a load balancer, API gateway, or ingress:

~~~text
OAuth Client
   |
   | mTLS: client certificate A
   v
Ingress / API Gateway
   |
   | New TLS to application
   | backend peer certificate may be the gateway's certificate
   v
Spring Resource Server
~~~

If the ingress terminates mTLS, the backend Servlet container or Reactor Netty typically sees only the **ingress's certificate** on the upstream connection. Comparing the ingress's thumbprint with the client's `cnf` will be wrong.

Three common architectural patterns:

1. **TLS passthrough:** pass the raw TLS session through to the Resource Server so the application authenticates the client certificate directly.
2. **Trusted certificate propagation:** the ingress verifies the client certificate and forwards the verified certificate info over a protected internal channel/header.
3. **Gateway enforces token binding:** the gateway holds verified info for both the client certificate and token and checks binding before forwarding; the backend trusts the gateway under an explicit trust contract.

### Forwarded Certificate Headers Are Not Inherently Trustworthy

Some proxies can forward certificate metadata, such as XFCC or a configured internal header. If used:

- The ingress must **strip incoming headers of the same name sent by clients** before writing verified values.
- The backend must accept requests only from trusted proxies via network policy/mTLS.
- The header must follow an agreed format/schema containing the required certificate chain/leaf identity.
- Never use a text DN or subject string instead of a DER certificate thumbprint when the contract requires `x5t#S256`.
- Ensure the header cannot be altered by another proxy or untrusted intermediate service.
- Logs must not record full certificates/PII beyond operational needs.

If a client can send `X-Client-Cert`, `X-SSL-CERT`, or a similar header directly to the backend, an attacker can spoof a certificate identity. **Never read certificate binding from a client-controlled header.**

### Proxy-to-Application mTLS Differs from Client-to-Proxy mTLS

If the gateway uses mTLS to talk to the backend, the backend authenticates **the gateway**. That protects the internal hop, yet does not prove the gateway properly verified the OAuth client's certificate. You need a separate trust contract for forwarded identities and header protection.

## 9. Certificate Binding Does Not Replace Other JWT Checks

A token with a matching `cnf` still requires all standard validators:

~~~text
Valid JWT signature
AND trusted issuer
AND correct audience
AND exp / nbf valid
AND accepted access-token profile
AND required scope/permissions
AND certificate thumbprint matches TLS peer
AND tenant/object policy passes
~~~

### Token Has Valid Binding but Wrong Audience

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

If a request to the Orders API carries certificate A, the binding matches, yet the token is not intended for `orders-api`. The Resource Server must reject it during audience validation.

### Token Has Valid Scope but Wrong Certificate

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

A request using certificate B—even if B is trusted by the CA and the token has `SCOPE_orders.read`—must still be rejected due to binding mismatch.

### Object Permissions Must Still Be Checked After Binding

A certificate-bound token proves the token is being used with the bound certificate. It does not prove the caller can read every order. Services must still check tenant, owner, membership, sharing, assignment, and business state.

## 10. Spring Security Does Not Infer Token Binding from TLS Alone

Enabling HTTPS or requiring client certificates on a server connector does not automatically make Spring Security compare `cnf.x5t#S256` against the peer certificate. Likewise, enabling `oauth2ResourceServer().jwt()` configures only JWT verification via decoder/validators; do not assume it performs certificate binding unless your application configures that behavior.

Spring Security provides the building blocks:

- OAuth2 Resource Server authenticates Bearer JWTs or opaque tokens.
- `JwtDecoder` and `OAuth2TokenValidator<Jwt>` verify JWT signatures/claims.
- Opaque token introspectors retrieve principals/attributes from the AS.
- X.509 support can map a peer certificate to an `Authentication` in suitable use cases.
- Filters/authorization managers can enforce per-request policies after authentication.

**X.509 authentication and certificate-bound access token validation remain two separate tasks.** The X.509 filter can build an `Authentication` from a certificate, but does not automatically know that a Bearer token's `cnf` must match that certificate.

A clean way to structure enforcement:

1. The TLS connector or trusted ingress validates the client certificate.
2. Resource Server validates the Bearer token.
3. A binding enforcement component retrieves both the verified `Authentication` and the request's client certificate.
4. That component compares `cnf.x5t#S256`.
5. Authorization rules continue checking scopes/roles and object policies.

Exact APIs and classes differ between Servlet and WebFlux, so never copy Servlet filters into a reactive chain.

## 11. Enforcement Example in Spring Security Servlet

The example below illustrates a **custom filter** for routes requiring certificate-bound JWTs. It runs after `BearerTokenAuthenticationFilter`, once JWT authentication has been created. In a real application, restrict the filter to the right routes and handle all accepted token types.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CertificateBindingFilter extends OncePerRequestFilter {

    private static final String CERTIFICATE_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        // Unauthenticated requests are handled by the entry point/authorization.
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            filterChain.doFilter(request, response);
            return;
        }

        Map<String, Object> confirmation =
            jwtAuth.getToken().getClaim("cnf");
        Object expectedValue = confirmation != null
            ? confirmation.get("x5t#S256")
            : null;

        X509Certificate[] certificates = (X509Certificate[])
            request.getAttribute(CERTIFICATE_ATTRIBUTE);

        if (!(expectedValue instanceof String expected)
                || certificates == null
                || certificates.length == 0
                || certificates[0] == null) {
            reject(response);
            return;
        }

        String actual = CertificateThumbprints.x5tS256(certificates[0]);
        boolean matches = MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.US_ASCII),
            actual.getBytes(StandardCharsets.US_ASCII));

        if (!matches) {
            reject(response);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private static void reject(HttpServletResponse response)
            throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer error=\"invalid_token\"");
    }
}
~~~

`CertificateThumbprints.x5tS256(...)` is the helper from earlier. This filter illustrates the JWT path; opaque tokens must read `cnf` from principal attributes per the introspector implementation and introspection contract.

### Wiring the Filter into the Right Chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain certificateBoundApi(
        HttpSecurity http,
        CertificateBindingFilter bindingFilter) throws Exception {
    return http
        .securityMatcher("/api/mtls/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("SCOPE_orders.read"))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> { }))
        .addFilterAfter(
            bindingFilter, BearerTokenAuthenticationFilter.class)
        .build();
}
~~~

This is a **Servlet configuration pattern**; adjust it for your Spring Security version and application APIs. If `CertificateBindingFilter` is declared as a Servlet `Filter` bean, prevent Spring Boot from registering it twice—both directly with the servlet container and inside the `SecurityFilterChain`. You may need a `FilterRegistrationBean` to disable container registration so it runs only at the intended Spring Security position.

### What This Example Needs for Production Completeness

- The matcher must cover only endpoints requiring certificate-bound tokens.
- The TLS connector must actually require/verify client certificates, or the app must receive certificate metadata from a trusted ingress.
- If JWT `Authentication` is absent, the chain must still deny protected routes via authorization; never let anonymous requests slip past the filter into controllers.
- Opaque tokens need a corresponding binding extractor.
- Tokens missing `cnf` must be rejected on this route.
- Certificate chain validation, EKU, revocation, and client identity mapping must be configured at the TLS/proxy layer.
- The filter must handle thumbprint calculation errors by failing closed; never let an encoding exception create a bypass branch.
- Test mismatches and missing certificates via MockMvc.

This snippet does not replace a full implementation for every connector/proxy. If TLS terminates at a gateway, the servlet attribute may contain the gateway's certificate; use a verified forwarded-identity source per the proxy section.

## 12. WebFlux: Enforcing Binding in Reactive Requests

In WebFlux, request TLS info can be obtained from `ServerHttpRequest.getSslInfo()` when the server adapter supplies peer certificates. Comparison must run within the reactive request flow and receive the verified `Authentication`, the current `ServerWebExchange`, and the corresponding peer certificate.

Helper skeleton for reading certificates:

~~~java
import java.security.cert.X509Certificate;
import org.springframework.http.server.reactive.SslInfo;
import org.springframework.http.server.reactive.ServerHttpRequest;

X509Certificate[] peerCertificates(ServerHttpRequest request) {
    SslInfo sslInfo = request.getSslInfo();
    if (sslInfo == null) {
        return new X509Certificate[0];
    }
    X509Certificate[] certificates = sslInfo.getPeerCertificates();
    return certificates != null
        ? certificates
        : new X509Certificate[0];
}
~~~

After obtaining the principal, the binding check can be integrated into a `ReactiveAuthorizationManager<AuthorizationContext>` or a `WebFilter` placed appropriately in the security flow. Pseudocode:

~~~java
Mono<AuthorizationDecision> authorize(
        Mono<Authentication> authentication,
        ServerWebExchange exchange) {

    return authentication
        .filter(JwtAuthenticationToken.class::isInstance)
        .cast(JwtAuthenticationToken.class)
        .map(jwtAuth -> {
            String expected = readX5tS256(jwtAuth.getToken());
            X509Certificate certificate =
                firstPeerCertificate(exchange.getRequest());

            boolean allowed = expected != null
                && certificate != null
                && sameThumbprint(
                    expected,
                    CertificateThumbprints.x5tS256(certificate));

            return new AuthorizationDecision(allowed);
        })
        .defaultIfEmpty(new AuthorizationDecision(false));
}
~~~

This is **composition pseudocode**, not a complete class for every Spring Security version. The `ReactiveAuthorizationManager` signature and authorization result types vary across versions; check the API you use. An authorization denial typically results in 403; if your contract requires treating a binding mismatch as an invalid Bearer token returning 401, design corresponding authentication failure handling rather than silently treating every authorization denial as `invalid_token`.

**Never use `block()` or `ThreadLocal`** to retrieve `SecurityContext`/certificates. Compose `Mono` within the same subscriber flow.

## 13. TLS Termination and Forwarded Certificates: Configuration Must Protect Headers

When using an ingress/gateway, clearly establish **who validates the client certificate** and **who performs the thumbprint comparison**.

### TLS Passthrough

~~~text
Client --mTLS--> Resource Server
                    |
                    +-- TLS connector sees client peer cert
                    +-- Bearer authentication
                    +-- cnf thumbprint comparison
~~~

This is the most direct model for applications needing the peer certificate, though it can limit the gateway's ability to perform TLS routing/inspection.

### Gateway Terminates mTLS and Forwards the Certificate

~~~text
Client --mTLS--> Trusted Gateway --mTLS/private network--> Resource Server
                     |
                     +-- validate client certificate
                     +-- strip client-supplied cert headers
                     +-- inject verified certificate metadata
                                      |
                                      v
                           Binding verifier at backend
~~~

In this model, the backend must have a way to verify the header came from the right gateway. Controls typically needed:

- Backend accepts traffic only from the gateway via network policy.
- Gateway and backend use internal mTLS or an equivalent channel.
- Gateway strips all client-sent certificate headers before writing verified metadata.
- Backend trusts only configured proxy identities, not arbitrary `X-Forwarded-*` headers.
- Certificate/chain format is defined; if thumbprints are needed, compute from the corresponding DER certificate rather than comparing subject text.
- Tests send spoofed headers directly from a client and confirm the backend rejects them.

Never toggle a blanket "trust forwarded certificate" property for all requests. Trusting headers is a trust-boundary decision.

### Proxy-to-Application mTLS Differs from Client-to-Proxy mTLS

If the gateway uses mTLS to talk to the backend, the backend authenticates **the gateway**. That protects the internal hop, yet does not prove the gateway properly verified the OAuth client's certificate. You need a separate trust contract for forwarded identities and header protection.

## 14. Certificate Binding Does Not Replace Other JWT Checks

A token with a matching `cnf` still requires all standard validators:

~~~text
Valid JWT signature
AND trusted issuer
AND correct audience
AND exp / nbf valid
AND accepted access-token profile
AND required scope/permissions
AND certificate thumbprint matches TLS peer
AND tenant/object policy passes
~~~

### Token Has Valid Binding but Wrong Audience

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

If a request to the Orders API carries certificate A, the binding matches, yet the token is not intended for `orders-api`. The Resource Server must reject it during audience validation.

### Token Has Valid Scope but Wrong Certificate

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "thumbprint-A"
  }
}
~~~

A request using certificate B—even if B is trusted by the CA and the token has `SCOPE_orders.read`—must still be rejected due to binding mismatch.

### Object Permissions Must Still Be Checked After Binding

A certificate-bound token proves the token is being used with the bound certificate. It does not prove the caller can read every order. Services must still check tenant, owner, membership, sharing, assignment, and business state.

## 15. Certificate Renewal, Rotation, and Token Lifetime

Thumbprints are computed over the **entire DER certificate**. Therefore, when a certificate is renewed/reissued, the thumbprint usually changes even if the client keeps the same public/private key pair, because the serial number, validity, or certificate encoding differs.

~~~text
Certificate A:
  thumbprint = THUMB-A
  Token T1: cnf.x5t#S256 = THUMB-A

Certificate B (renewed):
  thumbprint = THUMB-B

T1 + Certificate A -> binding matches
T1 + Certificate B -> binding mismatch
New token T2 issued with Certificate B -> binding matches
~~~

A rotation plan should include:

1. Register/authorize the new certificate at the Authorization Server per client identity policy.
2. Confirm the token endpoint issues new tokens with the new certificate's thumbprint.
3. Client switches to the new certificate and new token per rollout plan.
4. Retain the old certificate long enough for old tokens to remain usable if policy allows overlap.
5. After overlap ends, revoke the old certificate and/or old tokens.
6. Verify every Resource Server instance has picked up the new trust/certificate configuration.

Never switch certificates while continuing to send tokens bound to the old thumbprint. Never modify the `cnf` claim in a token yourself; only the Authorization Server may issue a new token under a trusted mechanism.

### Certificate Revocation and Token Revocation Are Two Lifecycles

- **Certificate revocation:** PKI/CA/OCSP/CRL or a trust registry decides whether the certificate is still accepted.
- **Access token revocation:** Authorization Server decides whether the token is still active.
- **Binding comparison:** proves the token is being used with the exact bound certificate.

An unrevoked certificate with an expired token must still be rejected. An unexpired token with a revoked certificate must be rejected at the TLS/trust layer. An active token with a certificate having a different thumbprint must be rejected at the binding layer.

## 16. What Does Certificate Binding Protect Against and What Does It Not?

### Bearer Token Only

~~~text
Client A receives token T
Attacker steals T
Attacker sends Authorization: Bearer T
Resource Server only checks T is valid
=> Attacker can use token until expiry/revocation
~~~

### Token Bound to Certificate A

~~~text
Client A:
  private key A + certificate A
  token T: cnf = thumbprint(A)

Attacker steals T but only has certificate B:
  TLS mTLS with B may succeed
  token T has cnf thumbprint(A)
  request certificate thumbprint(B)
  => mismatch, reject
~~~

### What This Mechanism Does Not Solve

- An attacker obtains **both the access token and the client's private key**.
- Malware controlling the client process can use the key via HSM/keystore if authorized.
- A gateway validates certificates improperly or forwards spoofed metadata.
- The Resource Server skips checking `cnf` or compares against the wrong proxy certificate.
- The issuer mints tokens with the wrong thumbprint or an unverified token profile.
- Audience/scope/tenant/object authorization is misconfigured loosely.
- TLS private keys leak or a certificate authority is compromised.
- Replay in an environment where the attacker still has access to use the right key/certificate.

Certificate-bound tokens **reduce standalone stolen-token risk**, not render tokens immune to every compromise.

## 17. Certificate-Bound Tokens Differ from DPoP

Both certificate-bound access tokens and **Demonstrating Proof of Possession (DPoP)** aim to bind access tokens to a client key, yet their proofs and claims differ.

| Aspect | mTLS Certificate-Bound Token | DPoP |
| --- | --- | --- |
| Proof | Client certificate in TLS handshake | DPoP proof JWT signed by client per request |
| Token confirmation | `cnf.x5t#S256` | `cnf.jkt` |
| Binding | Thumbprint of X.509 client certificate | Thumbprint of public JWK |
| Transport requirement | TLS with client certificate/mTLS per profile | DPoP proof attached to HTTP request; still uses TLS |
| Possession proof | TLS handshake proves client holds certificate private key | Proof JWT signature proves possession of JWK private key |
| Request verification | Compares connection certificate against token | Verifies proof JWT, method/URI/time/nonce, and token binding |

Never compare `cnf.jkt` against a certificate thumbprint. Never use `x5t#S256` to verify a DPoP proof. Both aim for sender-constrained tokens, yet **they do not replace each other**.

## 18. Testing Certificate Binding

Tests should separate:

1. Is the TLS client certificate accepted during the handshake?
2. Does JWT/introspection validate the token?
3. Is `cnf.x5t#S256` read from the verified token?
4. Is the thumbprint computed from the exact leaf certificate?
5. Are binding mismatches rejected before controllers or business side effects run?
6. Are proxy-forwarded certificates protected against spoofing?

### Unit Testing the Thumbprint

Use a test certificate fixture created specifically for tests. Compute the expected thumbprint independently or use a known-value fixture; test:

- Same DER certificate yields the same thumbprint.
- Different certificate yields a different thumbprint.
- Base64URL encoding has no padding.
- Null/missing claim comparisons return false.
- Does not hash PEM text or public key encoding.

Never use production private keys/certificates in test fixtures.

### MockMvc Test Matrix

In Servlet, filter/chain tests can mock or inject the request certificate attribute in the test harness:

| Token | Request Certificate | Expected |
| --- | --- | --- |
| Valid JWT signature, `cnf=A` | Valid A | Binding passes; proceeds to authorization |
| Valid JWT signature, `cnf=A` | Valid B | 401 `invalid_token` per binding policy |
| Valid JWT signature, missing `cnf` | Valid A | Reject on certificate-bound route |
| Valid JWT signature, `cnf=A` | No cert | Reject |
| Invalid JWT signature, forged payload `cnf=A` | Valid A | Reject at JWT validation |
| Token with valid binding, missing scope | Valid A | Binding passes, authorization returns 403 |
| Token with valid binding, wrong audience | Valid A | Reject at token validation |
| Token with valid binding, expired/revoked cert | TLS/trust policy rejects | Never reaches business handler |
| Spoofed certificate header from client | No trusted proxy identity | Header must not be treated as verified cert |

A unit test that manually sets `jakarta.servlet.request.X509Certificate` **does not prove TLS handshake or PKI validation**. It tests only the binding comparison. You need integration tests with an HTTPS/mTLS server and a test CA certificate to verify the connector.

### WebFlux Test Matrix

In WebFlux, test `ServerHttpRequest.getSslInfo()` on a server/adapter with TLS support. `WebTestClient` bound directly to controllers may lack TLS peer certificates present in real runtime. When handshake testing is required, run an HTTPS test server with test client certificates and a test trust store.

Reactive binding tests must also confirm:

- Authentication and certificate belong to the same request/subscriber.
- No certificate from another request or stale `ThreadLocal` is used.
- Mismatches produce a denied decision and never invoke controllers.
- Publishers never call `block()`/`subscribe()` independently.
- Proxy mode trusts certificate metadata only from an authenticated gateway.

## 19. Configuring TLS Client Authentication by Environment

Spring Boot can configure TLS server client-auth at the connector. Conceptual example:

~~~yaml
server:
  ssl:
    enabled: true
    key-store: /run/secrets/server-keystore.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_PASSWORD_FROM_SECRET_STORE
    trust-store: /run/secrets/client-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: CLIENT_TRUSTSTORE_PASSWORD_FROM_SECRET_STORE
    client-auth: need
~~~

Verify property names and behavior against your exact Spring Boot version and container. `client-auth: need` typically requires a client certificate on **that connector**. If the connector also serves public health checks or routes not requiring mTLS, requiring certificates globally can block those connections.

Architectural options:

- Dedicated port/connector for mTLS-bound routes.
- Ingress/gateway terminates mTLS and forwards certificate metadata over a trusted channel.
- TLS connector configured for optional client certificates if supported by the stack, with the binding filter requiring certificates on corresponding routes.

Never assume an HTTP path can alter TLS handshake requirements after a connection has already been established. The TLS handshake happens before HTTP routing; therefore mTLS is enforced per connector/connection, not simply as a `requestMatchers` rule.

### Trust Store and CAs

The trust store must hold the appropriate CA/intermediate certificates to verify client certificates. Never import an arbitrary client certificate as a trust anchor just for quick testing; that can turn the trust policy into an unintended allowlist.

Depending on policy, verify CA chain/path building, Extended Key Usage `clientAuth`, Key Usage, certificate validity, revocation status/OCSP/CRL if required, subject/SAN or certificate-to-client mapping, certificate renewal, and CA rollover.

## 20. Verification Matrix Across Dev, Staging, and Production

Certificate binding often fails when dev, staging, and production have different topologies. Maintain a dedicated capability table:

| Item | Dev | Staging | Production |
| --- | --- | --- | --- |
| TLS termination point | App / local proxy | Staging ingress | Production gateway/ingress |
| Client certificate request | Optional/required per test | Match production as closely as possible | Per approved policy |
| Client CA trust | Dedicated test CA | Staging CA | Production CA/PKI |
| Certificate profile | Test key/cert | Production-like cert | CA, EKU, key size, renewal policy |
| Token `cnf` | Test thumbprint | Staging AS issues real cert binding | Production AS contract |
| JWT/opaque mode | Verified | Verified | Verified |
| Introspection exposes `cnf` | Tested if opaque | Tested | Tested |
| Proxy forwarding | Anti-spoof header test | Ingress config test | Trusted proxy chain / network policy |
| Thumbprint calculation | DER/SHA-256/Base64URL | Cross-implementation test | Versioned contract |
| Certificate rotation | Test A → B | Test overlap/rollout | Runbooks/monitoring |
| Certificate revocation | Test CA fixture | Test propagation | OCSP/CRL/trust registry SLA |
| Token revocation | AS test | End-to-end | SLO / incident process |
| Failure response | Missing/mismatch | Missing/mismatch/proxy | Contract 401/5xx and alerts |
| Private key storage | Local keystore / test HSM | Secret store / HSM | HSM/TPM/managed key service if required |

Never let a dev test CA certificate be trusted in production. Never share client private keys across environments. If production TLS terminates at a gateway, test exact certificate forwarding and header spoofing in the real topology.

## 21. Common Mistakes

**"HTTPS is active, so certificate binding is protected."** Standard HTTPS authenticates only the server. Client certificates require mTLS, and token binding also requires thumbprint comparison.

**"Enabling mTLS is enough."** mTLS proves the peer has a valid certificate/private key; the token could belong to a different certificate. You must compare `cnf.x5t#S256`.

**"Using the server certificate to check `cnf`."** Wrong object. Here `cnf.x5t#S256` binds the client certificate.

**"Comparing only subject DN or serial number."** RFC 8705 uses the SHA-256 thumbprint of the DER certificate. Subject/serial do not replace that formula.

**"Hashing PEM text."** Wrong byte input. Hash the DER encoding of the certificate.

**"Hashing the public key is equivalent."** No. Certificate thumbprints and public-key thumbprints are different values.

**"The JWT has `cnf`, so signature verification isn't needed."** No. Claims are trustworthy only after token validation.

**"Introspection returned `active=true`, so certificate comparison isn't needed."** No. You must read and verify `cnf` if the endpoint requires bound tokens.

**"The gateway forwards `X-Client-Cert`, so the backend can trust it."** Not unless client-sent headers are stripped and the backend authenticates the gateway.

**"Enable `client-auth: need` on the connector, and only `/api/mtls/**` will require a cert."** The TLS handshake precedes HTTP routing; the connector may demand certificates for every request on that port.

**"Certificate renewal keeps the same thumbprint if the public key doesn't change."** No. The thumbprint is computed over the entire DER certificate; a new certificate usually has a new thumbprint.

**"Token binding replaces scope, audience, and owner checks."** No. Binding only ties the token to the certificate; the remaining checks are still required.

**"Spring Security's X.509 authentication automatically checks `cnf`."** Never assume so. X.509 authentication and Bearer token binding are two separate tasks.

## 22. Workflow for Deploying Certificate-Bound Access Tokens

1. **Finalize the profile:** define RFC 8705, JWT vs. opaque tokens, `cnf.x5t#S256`, and API/resource audience.
2. **Configure the Authorization Server:** client registration, mTLS authentication if needed, and certificate-bound access token issuance.
3. **Obtain a test token:** use certificate A; verify token/introspection returns thumbprint A.
4. **Configure TLS peer authentication:** trusted CAs, certificate chain, EKU, expiry, and revocation per policy.
5. **Define topology:** TLS passthrough vs. trusted gateway termination; never confuse proxy certificates with client certificates.
6. **Implement binding enforcement:** extract the request's leaf certificate, compute DER/SHA-256/Base64URL-no-padding, and compare against token confirmation.
7. **Fail closed:** missing certificates, missing `cnf`, mismatches, parsing errors, or absent trusted proxy metadata must never grant access.
8. **Keep token validation:** signature/introspection, issuer, audience, time, token type, and claim profiles.
9. **Keep authorization:** scopes, roles, tenants, owners, sharing, and resource state.
10. **Manage lifecycles:** certificate renewal/rotation, token lifetimes, revocation, CA rollover, and key storage.
11. **Test thoroughly:** thumbprint unit tests, JWT/introspection tests, TLS handshake tests, mismatches, missing certs, proxy spoofing, and certificate rotation.
12. **Monitor operations:** binding mismatches, missing peer certs, TLS handshake failures, unknown CAs, cert expiry, and token validation errors; never log access tokens or private keys.
13. **Validate each environment:** use dedicated CAs, client certs, tokens, and topologies for dev/staging/production.

**Key takeaway:** TLS/mTLS verifies the peer and protects the connection, yet **does not automatically prove the Bearer access token belongs to the active client certificate**. For certificate-bound access tokens under RFC 8705, the Resource Server must verify the token first, read `cnf.x5t#S256`, obtain the verified leaf client certificate from that exact TLS request, compute its SHA-256 thumbprint over DER, and compare. On certificate mismatch, missing certificate, or missing binding claim on routes requiring mTLS-bound tokens, reject the request. Only after binding matches should scope, audience, tenant, and object-level authorization proceed.
