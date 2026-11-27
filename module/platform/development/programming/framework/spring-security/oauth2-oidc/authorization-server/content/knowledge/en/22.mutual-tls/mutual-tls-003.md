# Binding Access Tokens to Client Certificates

> **Chapter:** mTLS  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module goal:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Example versions:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x on the Servlet stack. The `TokenSettings.x509CertificateBoundAccessTokens` setting has been available since Spring Authorization Server 1.3. For Spring Security 7.x with integrated Authorization Server, check the APIs for your version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **mTLS client authentication** at the Authorization Server from **certificate-bound access tokens** when accessing a Resource Server.
2. Explain why an access token bound to an X.509 certificate is no longer a pure bearer token.
3. Describe how RFC 8705 uses `cnf.x5t#S256` to bind an access token to a client certificate.
4. Distinguish between the two methods `tls_client_auth` (PKI) and `self_signed_tls_client_auth`.
5. Configure `RegisteredClient` and `TokenSettings.x509CertificateBoundAccessTokens(true)` in Spring Authorization Server.
6. Understand how the AS obtains the certificate from the TLS handshake, verifies the client, and embeds the thumbprint into the access token.
7. Implement proof-of-possession checks at the Resource Server: the certificate in the TLS handshake must match the thumbprint in the token.
8. Handle TLS termination at a reverse proxy/load balancer, certificate rotation, refresh tokens, certificate revocation, and operational scenarios.
9. Write tests for wrong certificates, tokens without `cnf`, thumbprint mismatches, old tokens, and certificate rotation.

**Core principle:** The client must prove possession of the private key corresponding to the certificate used to obtain the token. When accessing the API, the client must establish an mTLS connection using **that exact certificate**. The Resource Server compares the actual certificate's thumbprint against `cnf.x5t#S256` in the access token. Having only a valid access token or only a valid certificate is not enough.

## 2. Problem: Stolen Access Tokens

In standard OAuth 2.0, a Client receives an access token and sends:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
~~~

With a bearer token, any party that obtains the token string can use it within its remaining lifetime and scopes. Signing the token as a JWT does not change this characteristic: the signature protects integrity and issuer authenticity, but does not prove that the sender of the request is the client that originally received the token.

A certificate-bound access token adds proof of possession:

- When requesting a token, the client uses an X.509 certificate and private key to complete mTLS with the Authorization Server (AS).
- The AS computes the SHA-256 thumbprint of the certificate and binds it to the access token.
- When calling the Resource Server (RS), the client continues using the corresponding private key to complete mTLS.
- The RS extracts the certificate from the TLS layer and compares its thumbprint against the token.
- If the token is stolen but the attacker lacks the private key, the attacker cannot establish an mTLS connection matching that token.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: TLS handshake + client certificate C1
    AS->>AS: Verify certificate / client registration
    C->>AS: POST /oauth2/token + grant
    AS->>AS: Compute SHA-256 thumbprint of C1
    AS-->>C: Access token + cnf.x5t#S256
    Note over C,AS: Token is bound to C1
    C->>RS: TLS handshake + same certificate C1
    C->>RS: Authorization: Bearer token
    RS->>RS: Verify token + compare C1 thumbprint with cnf
    RS-->>C: Accept if signature, permissions, and certificate binding are all valid
~~~

**Certificate-bound access tokens do not encrypt the token and do not hide it from a thief.** Instead, they prevent the token from being used independently if an attacker lacks the corresponding certificate's private key.

## 3. Two Mechanisms to Distinguish

mTLS client authentication and certificate-bound access tokens are closely related but answer two different questions.

| Mechanism | Timing | Question Answered |
| --- | --- | --- |
| **mTLS client authentication** | Client connects to the AS Token Endpoint | Which client is calling the AS, and does it have a valid certificate? |
| **Certificate-bound access token** | Client uses an access token at the RS | Does the sender of the token possess the private key of the certificate bound to the token? |

### 3.1. mTLS client authentication

The client presents an X.509 certificate during the TLS handshake. The server verifies the certificate chain and/or matches the certificate against the client's registration info.

RFC 8705 defines two authentication methods:

- `tls_client_auth`: the PKI method, where the client certificate is issued by a CA trusted by the AS.
- `self_signed_tls_client_auth`: the client uses a self-signed certificate, and the AS matches the certificate against a JWK Set registered for the client.

When mTLS is used for client authentication, the client typically sends `client_id` in the token request body because `client_secret_basic` is not used to identify the client.

### 3.2. Certificate-bound access token

After verifying the certificate at the Token Endpoint, the AS computes the certificate's thumbprint and binds it to the access token. For JWTs, RFC 8705 specifies the confirmation method:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "booking-worker",
  "aud": ["booking-api"],
  "scope": "booking.read",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_THUMBPRINT_OF_CERTIFICATE"
  }
}
~~~

`cnf` is the confirmation claim. `x5t#S256` is the SHA-256 thumbprint of the X.509 certificate, Base64URL-encoded without padding.

This value is computed from the **DER encoding of the entire certificate**, not the PEM text, standalone public key, Subject DN, or serial number.

With reference/opaque access tokens, the Resource Server retrieves `cnf.x5t#S256` from the Token Introspection response rather than reading a JWT payload.

### 3.3. Certificate-bound tokens are not DPoP

| Criterion | mTLS certificate-bound token | DPoP |
| --- | --- | --- |
| Proof of possession | X.509 certificate and private key via TLS handshake | JWK and DPoP proof signature at the HTTP layer |
| TLS | Requires mTLS for protected resource access | Uses HTTPS; DPoP proof binds the request |
| Binding in token | `cnf.x5t#S256` | `cnf.jkt` |
| Verifying component | TLS layer provides client certificate; RS compares thumbprint | RS verifies proof JWT, method/URI/time/nonce, and JWK thumbprint |

You cannot substitute `jkt` for `x5t#S256` or use a DPoP proof to satisfy mTLS certificate binding.

## 4. How to Compute the Certificate Thumbprint

RFC 8705 defines `x5t#S256` via these steps:

1. Obtain the client X.509 certificate used in the TLS handshake.
2. Obtain its DER encoding via the certificate API.
3. Compute SHA-256 over the entire DER bytes.
4. Encode the digest using Base64URL.
5. Remove any trailing `=` padding characters.

~~~text
certificate_der = X509Certificate.getEncoded()
digest          = SHA-256(certificate_der)
thumbprint      = BASE64URL(digest, no_padding)
~~~

Java example:

~~~java
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Base64;

public final class CertificateThumbprints {

    private CertificateThumbprints() {
    }

    public static String x5tS256(X509Certificate certificate)
            throws Exception {

        byte[] der = certificate.getEncoded();
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(der);

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

In a real application, you can declare specific exceptions such as `CertificateEncodingException` and `NoSuchAlgorithmException`. SHA-256 is supported by the Java runtime; do not replace it with SHA-1.

**Do not compute the thumbprint over the public key:** two different certificates can share the same public key while having different issuers, subjects, serial numbers, validity periods, or extensions. RFC 8705 binds to **the certificate**, so the hash must be computed over the certificate's DER bytes.

## 5. Two mTLS Client Authentication Methods

### 5.1. PKI mutual TLS — `tls_client_auth`

With the PKI method:

1. The AS requires the client to send a certificate in the TLS handshake.
2. The TLS stack verifies the certificate chain up to a configured trust anchor.
3. The AS identifies the RegisteredClient by client ID.
4. The AS verifies certificate attributes against the registration.
5. If valid, client authentication succeeds and the AS can process the grant.

In Spring Authorization Server, the default certificate verifier of `X509ClientCertificateAuthenticationProvider` matches the certificate's Subject Distinguished Name (DN) against `ClientSettings.x509CertificateSubjectDN`.

Registration example:

~~~java
RegisteredClient mtlsClient = RegisteredClient
    .withId("mtls-client-registration")
    .clientId("mtls-client")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("booking.read")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=mtls-client,OU=Platform,O=Example,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

The example is based on Spring Authorization Server 1.5.x. You must import `RegisteredClient`, `ClientAuthenticationMethod`, `AuthorizationGrantType`, `ClientSettings`, `TokenSettings`, and `Duration`. The registration must be persisted via `RegisteredClientRepository`; do not regenerate a random ID on every startup if saved authorizations reference the registration.

**Limitation of the default verifier:** configuring `x509CertificateSubjectDN` only compares Subject DN. If policy requires SANs (DNS, URI, IP, email) or other attributes, you must configure a custom certificate verifier. When customizing, do not skip PKI chain validation, validity checks, key usage, EKU, and required certificate policy checks.

### 5.2. Self-signed certificate mutual TLS — `self_signed_tls_client_auth`

This method does not require client certificates issued by a public CA/trusted PKI. Instead:

1. The client registers a JWK Set or `jwks_uri` URL with the AS.
2. The JWK Set contains the certificate in the `x5c` attribute of a JWK.
3. The client sends the corresponding certificate in the TLS handshake.
4. The AS compares the received certificate against the certificate registered for the client.

Spring Authorization Server uses `ClientSettings.jwkSetUrl` to fetch the client's JWK Set in the default configuration.

~~~java
RegisteredClient selfSignedMtlsClient = RegisteredClient
    .withId("self-signed-mtls-registration")
    .clientId("partner-device")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("partner.read")
    .clientSettings(ClientSettings.builder()
        .jwkSetUrl("https://partner.example.test/.well-known/jwks.json")
        .build())
    .tokenSettings(TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

The client's JWK Set must include the corresponding public key and `x5c` containing the certificate. Per RFC 7517, the public key represented in the JWK must match the public key of the first certificate in `x5c`.

**Self-signed does not mean accepting arbitrary self-signed certificates.** The AS still must verify that the certificate received from the handshake matches the certificate registered by the client. Protect the client's `jwks_uri` endpoint from unauthorized modification; if an attacker swaps the certificate in the JWK Set, they can take over the client's identity.

### 5.3. Comparing the two methods

| Attribute | `tls_client_auth` | `self_signed_tls_client_auth` |
| --- | --- | --- |
| Trust model | PKI/CA | Directly registered certificate |
| Chain verification | TLS stack verifies up to a trusted CA | Does not rely on a CA chain like the PKI method |
| Registration binding | Spring default compares Subject DN | Matches certificate in client JWKS |
| SAS configuration | `x509CertificateSubjectDN` | `jwkSetUrl` |
| Certificate rotation | Issue new cert from CA per policy | Update JWK Set/client registration |
| Operations | Manage CA, trust store, CRL/OCSP | Protect JWKS, manage certificate pinning |

RFC 8705 warns of certificate spoofing risks if the PKI method only compares Subject DN while the AS trusts too many CAs. Two certificates issued by two different CAs can have the same Subject DN; therefore, trust anchors must be restricted according to policy.

## 6. Enabling Certificate-Bound Access Tokens in Spring Authorization Server

### 6.1. Configuring TokenSettings

Spring Authorization Server provides:

~~~java
TokenSettings.builder()
    .x509CertificateBoundAccessTokens(true)
    .build();
~~~

When this setting is enabled for a RegisteredClient using `tls_client_auth` or `self_signed_tls_client_auth`, the AS binds the access token to the X.509 certificate received during client authentication.

The default setting is `false`. The `x509CertificateBoundAccessTokens(boolean)` API has been available since Spring Authorization Server 1.3.

A fuller example:

~~~java
RegisteredClient mtlsWorker = RegisteredClient
    .withId("mtls-worker-id")
    .clientId("mtls-worker")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("booking.read")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=mtls-worker,OU=Services,O=Example,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .x509CertificateBoundAccessTokens(true)
        .build())
    .build();
~~~

`SELF_CONTAINED` is chosen so that the access token is a JWT, allowing the RS to verify the signature and `cnf` claim locally. If `REFERENCE` is chosen, the RS needs introspection to obtain status and certificate confirmation metadata.

### 6.2. The setting does not automatically configure TLS on the server

`x509CertificateBoundAccessTokens(true)` does not automatically configure the TLS listener. The AS application must also:

- Enable HTTPS.
- Configure the TLS stack to request/receive client certificates.
- Configure the trust store/CAs per the PKI model if using `tls_client_auth`.
- Ensure Spring Authorization Server receives the certificate chain from the TLS layer.
- Register the client with the proper authentication method.
- Test the certificate verifier and token generation.

If there is no certificate in the handshake, the AS cannot obtain a valid thumbprint to bind the token.

### 6.3. Distinguishing client authentication and token binding

It is possible to enable mTLS client authentication without enabling certificate-bound access tokens. In that case, the certificate is used to authenticate the client at the AS, while the issued access token can still be a bearer token.

RFC 8705 describes certificate-bound access tokens as a distinct binding mechanism; variants can even be designed for public clients. However, Spring Authorization Server's built-in setting is documented for clients using `tls_client_auth` or `self_signed_tls_client_auth`. Do not assume a `none` public client is automatically bound merely because the connection carries a certificate.

## 7. Configuring the TLS Listener on the Authorization Server

### 7.1. HTTPS and client certificates

Example Spring Boot configuration for an AS serving both mTLS clients and clients using other methods:

~~~yaml
server:
  ssl:
    enabled: true
    client-auth: want
    trust-store: classpath:as-client-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: ${AS_CLIENT_TRUSTSTORE_PASSWORD}
~~~

- `client-auth: want` asks the client to present a certificate if available without requiring every client to have one.
- `client-auth: need` requires every connection to that listener to present a client certificate.
- The trust store must contain the appropriate CAs if using PKI `tls_client_auth`.
- Trust store secrets must be supplied via a secret manager/environment, never hardcoded in the repository.

If the same host/port serves browser login, public clients, and other client authentication methods, setting `need` globally can prevent browsers or clients without certificates from completing the TLS handshake. You can use `want` or separate the mTLS Token Endpoint/alias onto a dedicated hostname or port.

### 7.2. Self-signed method requires appropriate TLS configuration

With `self_signed_tls_client_auth`, RFC 8705 is designed so that the AS verifies the certificate against a registered JWK Set rather than relying on a CA trust chain. The TLS listener must request a certificate, while certificate verification needs to coordinate with SAS's verifier mechanism. Do not apply a broad trust-all configuration just to make self-signed work.

### 7.3. Reverse proxy or load balancer terminating TLS

If TLS terminates at a proxy:

~~~mermaid
flowchart LR
    C["Client<br/>certificate + private key"]
    LB["Load Balancer / Reverse Proxy<br/>mTLS handshake"]
    AS["Spring Authorization Server"]
    DB[("RegisteredClientRepository<br/>Authorization Store")]

    C -->|"mTLS"| LB
    LB -->|"Protected backend connection<br/>+ verified certificate metadata"| AS
    AS --> DB
~~~

The AS no longer directly observes the client's TLS handshake. Certificate metadata must be forwarded by the proxy to the backend over a trusted channel.

Mandatory requirements:

- The proxy must strip any client-sent certificate headers before inserting its own metadata.
- The backend must accept connections only from the trusted proxy, preferably over a private network and mTLS between proxy and backend.
- Do not allow clients to reach the backend directly to spoof the proxy path.
- Metadata must represent the certificate extracted by the proxy from the TLS handshake, not an arbitrary string supplied by the request.
- Configure an appropriate converter/verifier so SAS receives the proper certificate chain.

RFC 8705 leaves the details of passing certificate metadata between proxy and application out of scope of the standard. This is a trust boundary that must be explicitly designed and tested.

## 8. Client Calling the Token Endpoint with mTLS

Client Credentials example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=mtls-worker&grant_type=client_credentials&scope=booking.read
~~~

The client does not send `client_secret_basic` when the registration uses `tls_client_auth`. The client certificate is presented during the TLS handshake.

Illustrative curl command:

~~~bash
curl --cert mtls-worker.crt \
     --key mtls-worker.key \
     --cacert auth-server-ca.crt \
     --header "Content-Type: application/x-www-form-urlencoded" \
     --data "client_id=mtls-worker&grant_type=client_credentials&scope=booking.read" \
     https://auth.example.test/oauth2/token
~~~

- `--cert`: the client's certificate.
- `--key`: the corresponding private key.
- `--cacert`: the CA used to verify the AS's certificate.
- `client_id`: identifies the RegisteredClient.
- The client must protect the private key and allow only authorized workloads to use it.

Never transmit private keys in HTTP bodies, URLs, headers, or logs. In production, use a keystore/PKCS#12, HSM, KMS, or an appropriate key management platform.

### 8.1. Response containing a JWT access token

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJ...SIGNED_JWT...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "booking.read"
}
~~~

The JWT payload may contain:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "mtls-worker",
  "aud": ["booking-api"],
  "scope": "booking.read",
  "iat": 1893455700,
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_CERTIFICATE_DER"
  }
}
~~~

`cnf` holds the certificate binding information. The thumbprint value is not a private key and does not replace the JWT signature. The RS still must verify the signature, issuer, audience, expiration, scopes, and certificate binding.

### 8.2. Reference access tokens and introspection

If the access token has the `REFERENCE` format, the RS cannot read `cnf` from the opaque string. The RS calls the Introspection Endpoint with appropriate client authentication. An active response may contain:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "mtls-worker",
  "scope": "booking.read",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_CERTIFICATE_DER"
  }
}
~~~

Per RFC 8705, `cnf` and `x5t#S256` are included in the introspection response so the RS can compare against the actual certificate. Do not assume custom metadata is returned intact if response handlers or introspection implementations have been customized; test the real contract.

## 9. The Resource Server Must Verify Proof-of-Possession

### 9.1. A JWT signature is not enough

An RS using standard JWT configuration typically checks the signature, issuer, audience if a validator is configured, `exp`/`nbf` timestamps, scopes, and business policies.

Those steps **do not automatically extract the certificate from the TLS request and compare it with `cnf.x5t#S256`**. For certificate-bound tokens, the RS must add a request-aware step that checks the actual certificate.

### 9.2. Verification sequence at the RS

1. The TLS layer receives the certificate from the client during the mutual TLS handshake.
2. Bearer token authentication verifies the access token as usual.
3. The RS reads `cnf.x5t#S256` from the JWT or introspection attributes.
4. The RS extracts the actual leaf certificate from the TLS layer.
5. The RS computes SHA-256 over the DER certificate and encodes it as unpadded Base64URL.
6. The RS compares the actual thumbprint with the thumbprint in the token.
7. If the certificate is missing, `cnf` is missing, or they mismatch, return HTTP 401 with `invalid_token`.
8. If binding is valid, proceed to check scopes and business permissions.

~~~mermaid
flowchart TD
    REQ["HTTPS Request + Bearer token"]
    TLS["TLS layer extracts client certificate"]
    AUTH["Resource Server verifies access token"]
    CNF{"Token has cnf.x5t#S256?"}
    CERT{"TLS request has certificate?"}
    HASH["SHA-256(DER certificate)<br/>Base64URL no padding"]
    MATCH{"Thumbprint matches?"}
    AUTHZ["Check scope / data permissions"]
    OK["Allow request"]
    DENY["401 invalid_token"]

    REQ --> TLS --> AUTH --> CNF
    CNF -->|"No"| DENY
    CNF -->|"Yes"| CERT
    CERT -->|"No"| DENY
    CERT -->|"Yes"| HASH --> MATCH
    MATCH -->|"No"| DENY
    MATCH -->|"Yes"| AUTHZ --> OK
~~~

### 9.3. Extracting the certificate from the Servlet request

When TLS is terminated directly at the Servlet container, the certificate chain can be read from the request attribute:

~~~java
Object value = request.getAttribute(
    "jakarta.servlet.request.X509Certificate");

if (value instanceof X509Certificate[] chain && chain.length > 0) {
    X509Certificate clientCertificate = chain[0];
}
~~~

The first certificate in the chain is the client's leaf certificate. This attribute is only populated when the TLS/container receives a client certificate. If a proxy terminates TLS in front, the attribute may not exist; in that case, use a verified and protected metadata forwarding mechanism from the proxy.

### 9.4. Certificate-binding verification filter

The example below illustrates a filter for routes requiring certificate-bound JWTs. This is an **integration skeleton** and must be adapted to your application's TLS container, filter chain, token format, and error handling.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CertificateBoundTokenFilter
        extends OncePerRequestFilter {

    private static final String CERTIFICATE_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    private final AuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            reject(request, response);
            return;
        }

        Object certificateValue =
            request.getAttribute(CERTIFICATE_ATTRIBUTE);

        if (!(certificateValue instanceof X509Certificate[] chain)
                || chain.length == 0) {
            reject(request, response);
            return;
        }

        Map<String, Object> confirmation =
            jwtAuth.getToken().getClaimAsMap("cnf");

        Object expectedValue = confirmation == null
            ? null
            : confirmation.get("x5t#S256");

        if (!(expectedValue instanceof String expectedThumbprint)) {
            reject(request, response);
            return;
        }

        try {
            String actualThumbprint = x5tS256(chain[0]);

            boolean matches = MessageDigest.isEqual(
                expectedThumbprint.getBytes(StandardCharsets.US_ASCII),
                actualThumbprint.getBytes(StandardCharsets.US_ASCII));

            if (!matches) {
                reject(request, response);
                return;
            }
        }
        catch (GeneralSecurityException ex) {
            reject(request, response);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private static String x5tS256(X509Certificate certificate)
            throws GeneralSecurityException {

        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(certificate.getEncoded());

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }

    private void reject(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException, ServletException {

        SecurityContextHolder.clearContext();

        this.entryPoint.commence(
            request,
            response,
            new OAuth2AuthenticationException(
                new OAuth2Error("invalid_token")));
    }
}
~~~

The filter above:

- Accepts only `JwtAuthenticationToken` and access tokens containing `cnf.x5t#S256`.
- Extracts the leaf certificate from the Servlet attribute.
- Computes the thumbprint over the DER certificate.
- Uses `MessageDigest.isEqual` for comparison.
- Returns a Bearer challenge `invalid_token` if invalid.

If the RS uses opaque tokens, the principal is typically `BearerTokenAuthentication`. In that case, read `cnf` from the token attributes returned by introspection instead of `JwtAuthenticationToken.getToken().getClaimAsMap("cnf")`. Do not skip thumbprint comparison simply because the token is opaque.

### 9.5. Registering the filter for mTLS routes

Example separate filter chain:

~~~java
@Bean
SecurityFilterChain mtlsApiSecurity(
        HttpSecurity http,
        CertificateBoundTokenFilter certificateBoundTokenFilter)
        throws Exception {

    http
        .securityMatcher("/api/mtls/**")
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(Customizer.withDefaults()))
        .addFilterAfter(
            certificateBoundTokenFilter,
            BearerTokenAuthenticationFilter.class);

    return http.build();
}
~~~

This is an illustrative filter chain for endpoints requiring mTLS-bound tokens. A separate chain is needed if regular APIs still accept bearer tokens not bound to certificates. The TLS listener/gateway for the `/api/mtls/**` route must require a client certificate so the request attribute has data.

Never let a route requiring mTLS accidentally fall into a chain that only verifies standard JWTs. If a token lacks `cnf` and the route still accepts it, an attacker can use stolen bearer tokens just like before.

## 10. Client Calling the Resource Server with the Exact Certificate

After receiving the access token, the client must use the same certificate and private key presented to the AS:

~~~http
GET /api/mtls/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
~~~

curl example:

~~~bash
curl --cert mtls-worker.crt \
     --key mtls-worker.key \
     --cacert resource-server-ca.crt \
     --header "Authorization: Bearer $ACCESS_TOKEN" \
     https://api.example.test/api/mtls/bookings
~~~

If the client sends only `Authorization: Bearer` without a client certificate, the TLS handshake may be rejected or the application returns `401 invalid_token` depending on listener configuration. If the client sends a different certificate, the thumbprint will not match and the request must be rejected.

### 10.1. An access token cannot be moved to another machine independently

| Scenario | Outcome |
| --- | --- |
| Token + matching private key/certificate | Can be verified, if token and permissions remain valid |
| Stolen token without the private key | Cannot complete mTLS with the corresponding certificate |
| Token + different certificate | Thumbprint mismatch, 401 |
| Right certificate but expired token | Token validation fails |
| Right certificate and valid token, but missing scope | Authorization fails |
| Expired or revoked certificate | TLS/PKI policy or certificate status check must reject per policy |

Certificate-bound tokens reduce the risk of token theft, though they do not protect if an attacker compromises the private key itself or controls a workload authorized to use the key.

## 11. Refresh Tokens and Certificate Binding

RFC 8705 distinguishes access token binding from refresh tokens:

- Access tokens can carry `cnf.x5t#S256` directly or via introspection.
- Refresh tokens are inherently bound to the client in OAuth 2.0.
- For confidential clients using `tls_client_auth` or `self_signed_tls_client_auth`, the client must continue authenticating at the Token Endpoint when using a refresh token.
- Because client authentication uses the certificate, the refresh token is **indirectly** bound to the client/certificate authentication.
- Do not assume a refresh token carries a `cnf.x5t#S256` claim like an access token.

When a client refreshes an access token, connect to the Token Endpoint using the certificate registered and used for client authentication. The AS verifies the client and issues a new access token per policy; the new token is bound to the certificate used in that request.

### 11.1. Why can't a stolen refresh token be used alone?

An attacker holding a refresh token without the client's private key/certificate will be unable to complete mTLS client authentication at the Token Endpoint. However, if the attacker steals both the refresh token and the private key, mTLS can no longer stop them.

Therefore, you still must protect refresh tokens, private keys, secret stores, process access permissions, and audit logs.

## 12. Certificate Rotation and Token Lifecycle

### 12.1. What happens to old access tokens when a certificate changes?

An access token is bound to the thumbprint of a specific certificate. When a client rotates its certificate:

- The new certificate has a different thumbprint, even if the Subject DN is unchanged.
- The old access token still contains the old certificate's thumbprint.
- Requests to the RS with the new certificate do not match the old token.
- The client needs to request a new access token using the new certificate.

RFC 8705 treats an access token bound to an old certificate as unusable once the client updates its certificate, and the client can acquire a new token and retry the request.

### 12.2. Certificate rotation plan

1. Generate a new certificate/key pair in a secure keystore.
2. Register the new certificate per PKI policy or update the client JWKS if using the self-signed method.
3. Ensure the AS accepts the new certificate and authenticates the right client.
4. Verify that the new token contains the new thumbprint.
5. Switch the client to the new certificate and acquire a new token.
6. The RS receives the new certificate and compares it against the new thumbprint in the token.
7. Retain the old certificate during a transition window if needed for still-valid old tokens.
8. Once old tokens expire or are revoked, remove the old certificate from trust/registration per policy.

If using the PKI method and the default verifier only compares Subject DN, a new certificate with the same Subject DN may be accepted when its chain is issued by a trusted CA. Even so, **the thumbprint still changes**, so old access tokens cannot automatically be used with the new certificate.

### 12.3. Emergency rotation when a private key is compromised

When a private key compromise is suspected:

- Revoke the certificate via the PKI/CA process or remove the certificate from the client JWKS.
- Prevent the AS from continuing to accept the old certificate.
- Prevent the RS from accepting the old thumbprint via a denylist/authorization policy if immediate reaction is required.
- Revoke related refresh tokens/authorizations.
- Issue a new certificate and new tokens.
- Monitor requests presenting the old thumbprint and conduct an audit investigation.
- Do not wait for access tokens to expire if there is evidence the key was compromised.

Simply removing a certificate from a trust store does not guarantee every running RS picks up the change immediately, especially if TLS terminates across multiple proxies or with caches/connection pools. A synchronized deployment process is required.

## 13. TLS Termination, Proxies, and Trust Boundaries

### 13.1. Why can a proxy break certificate binding?

Suppose a client connects via mTLS to a load balancer, and then the load balancer calls the backend AS/RS over plain HTTP or one-way TLS. The backend does not directly observe the client's TLS handshake. If the backend blindly trusts any `X-Client-Cert` header, an attacker can send a forged header to spoof a certificate.

### 13.2. Secure configuration

- Only trusted proxies may forward certificate metadata.
- The proxy strips client-supplied headers before creating internal headers.
- The backend allows connections only from the proxy over a private network/firewall and should have mTLS between proxy and backend.
- The proxy verifies the client certificate per policy before forwarding metadata.
- Metadata must use a standard encoding/format and the backend must parse the certificate strictly.
- Do not expose the backend directly to the Internet.
- Write tests confirming spoofed client headers are stripped and never used as identity.

~~~mermaid
flowchart TD
    ATTACKER["Client sends forged certificate header"]
    LB["Trusted Load Balancer"]
    BACK["Backend AS / RS"]

    ATTACKER -->|"TLS mTLS + forged header"| LB
    LB -->|"Strip client-sent header"| LB
    LB -->|"Add verified certificate metadata<br/>over trusted backend channel"| BACK
    ATTACKER -.->|"Direct access blocked"| BACK
~~~

Whenever possible, TLS pass-through or terminating TLS directly at the AS/RS reduces the number of components that must be trusted to forward certificate metadata. If TLS must terminate at a proxy, treat the proxy as part of the security boundary.

## 14. Certificate Validation and Its Limits

### 14.1. PKI validation

With `tls_client_auth`, you must verify:

- Chain reaches an approved CA trust anchor.
- Certificate is currently valid by time.
- Key Usage/Extended Key Usage is appropriate for client authentication.
- Subject DN or SAN matches client registration.
- CRL/OCSP/revocation policy if required by the system.
- CA has an issuance policy meeting security requirements.

Comparing Subject DN alone without restricting trust anchors introduces spoofing risks: another trusted CA could issue a certificate with the same DN.

### 14.2. Self-signed validation

With `self_signed_tls_client_auth`:

- The client certificate must match the certificate registered in the JWKS.
- JWK `x5c` must contain the right certificate and the JWK public key must match it.
- The JWKS URI must be protected against unauthorized modification.
- Have certificate rotation and revocation procedures.
- Do not accept a certificate merely because it is self-signed and can complete a TLS handshake.

### 14.3. Certificate-bound proof does not replace all PKI checks

At the RS, the goal of RFC 8705 is to verify that the client proves possession of the private key corresponding to the certificate bound in the token. The RFC notes that the RS does not necessarily have to rebuild the full PKI trust chain like the AS; however, deployments may enforce additional certificate validity/revocation policies.

What matters is that the RS obtains the certificate from a trusted TLS layer and compares its thumbprint against the token. If it only reads Subject DN from a header or an unverified certificate, proof-of-possession is weakened.

### 14.4. Certificate expiration does not automatically alter token claims

The `exp` of an access token and the `notAfter` of a certificate are two separate lifetimes. The system must decide:

- Whether the TLS layer rejects expired certificates.
- Whether the AS checks validity/revocation when issuing tokens.
- Whether the RS checks certificate validity/revocation or relies solely on thumbprint as proof-of-possession.
- How to block continued use of old access tokens when a certificate is revoked.

Do not assume the access token will expire at the exact moment the certificate expires. If immediate blocking is needed, you need a revocation/denylist mechanism or certificate status check policy.

## 15. Configuring Spring Authorization Server: Extension Points

### 15.1. Client authentication filter and provider

Spring Authorization Server includes default components:

- `X509ClientCertificateAuthenticationConverter`: retrieves the certificate chain from the HTTP request/TLS layer and builds a client authentication request.
- `X509ClientCertificateAuthenticationProvider`: verifies the client certificate for `tls_client_auth` or `self_signed_tls_client_auth`.
- `OAuth2ClientAuthenticationFilter`: executes client authentication and places the authenticated result into the SecurityContext.

Do not write a custom converter reading `X-Client-Cert` from requests unless a proxy trust model is established. If TLS terminates at the Servlet container, prefer the default X.509 mechanism.

### 15.2. Customizing the verifier for SANs

Spring Authorization Server allows setting a custom certificate verifier on `X509ClientCertificateAuthenticationProvider`. This is useful if registration policy requires SANs instead of Subject DN.

Configuration pattern:

~~~java
authorizationServerConfigurer.clientAuthentication(clientAuthentication ->
    clientAuthentication.authenticationProviders(providers ->
        providers.forEach(provider -> {
            if (provider instanceof
                    X509ClientCertificateAuthenticationProvider x509Provider) {

                x509Provider.setCertificateVerifier(context -> {
                    OAuth2ClientAuthenticationToken clientAuthentication =
                        context.getAuthentication();

                    RegisteredClient registeredClient =
                        context.getRegisteredClient();

                    X509Certificate[] chain =
                        (X509Certificate[]) clientAuthentication.getCredentials();

                    X509Certificate certificate = chain[0];

                    // Verify SAN / certificate attributes per policy.
                    // If invalid, throw OAuth2AuthenticationException.
                });
            }
        })
    )
);
~~~

This is a customization skeleton. When setting a new verifier, the application is responsible for implementing complete validation logic for the desired certificate attributes. Never leave TODOs or empty logic in production. If default Subject DN matching suffices, do not override the verifier.

### 15.3. Checking APIs by version

`X509ClientCertificateAuthenticationProvider` and certificate-bound token settings vary across library branches. In Spring Authorization Server 1.5.x, the classes/APIs listed above are available; if using an older version, check Javadocs/release notes rather than assuming a method exists.

## 16. Testing Certificate-Bound Access Tokens

### 16.1. Test matrix at the Authorization Server

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| Valid client certificate | Valid chain, DN/SAN matches registration | Client authentication succeeds |
| Certificate from untrusted CA | PKI method, invalid trust chain | TLS/client authentication fails |
| Wrong Subject DN | Valid certificate but DN mismatch | Reject client |
| Wrong SAN | Custom verifier requires specific SAN | Reject client |
| Properly registered self-signed certificate | JWKS contains matching x5c | Client authentication succeeds |
| Unregistered self-signed certificate | No matching cert in JWKS | Reject client |
| Client sends no certificate | Registration requires mTLS | Cannot authenticate client |
| Bound token setting enabled | Valid mTLS client | Access token contains certificate confirmation |
| Bound token setting disabled | mTLS client but policy does not enable binding | Token lacks binding per configuration |
| Client lacks grant | Right certificate but grant not registered | Reject grant |
| Expired/revoked certificate | Per PKI policy | Reject per verification policy |

### 16.2. Test matrix at the Resource Server

| Test Case | Token | Certificate in TLS Handshake | Result |
| --- | --- | --- | --- |
| Right certificate | cnf has thumbprint C1 | C1 | Acceptable |
| Wrong certificate | cnf has C1 | C2 | 401 `invalid_token` |
| No certificate | cnf has C1 | None | Rejected |
| Token without cnf on mTLS route | No confirmation | C1 | Rejected |
| Tampered token | Invalid signature | C1 | Rejected before or during JWT validation |
| Expired token | exp in the past | C1 | Rejected |
| Wrong audience | aud not for RS | C1 | Rejected |
| Missing scope | Valid token and right C1 | C1 | 403 per authorization policy |
| Active opaque token | Introspection cnf=C1 | C1 | Acceptable |
| Inactive opaque token | active=false | C1 | Rejected |
| Certificate rotation | Old token cnf=C1 | C2 | Old token rejected |
| Revoked certificate | cnf=C1 | C1 but cert is revoked | Rejected per revocation policy |

### 16.3. Standalone thumbprint tests

Create controllable certificate fixtures and verify:

1. `certificate.getEncoded()` returns DER bytes.
2. Digest is SHA-256.
3. Base64URL without padding.
4. Output matches `x5t#S256` in JWT fixtures.
5. Hashing PEM text or standalone public key yields a different value.

Never use real certificates or production private keys in tests.

### 16.4. End-to-end TLS tests

Filter unit tests only prove comparison logic. You need integration tests with a real HTTPS listener or a test server supporting client certificates:

- Request without a certificate.
- Request with certificate C1 and token cnf C1.
- Request with certificate C2 and token cnf C1.
- Valid JWT token but missing cnf.
- JWT token with invalid signature.
- Request through a reverse proxy with trusted certificate metadata.
- Request through a proxy with a spoofed client-sent certificate header.
- Client certificate changed between the Token Endpoint and the Resource Server.

End-to-end tests must prove the certificate comes from the TLS layer, rather than manually setting a request attribute and concluding mTLS works.

## 17. Operations and Observability

### 17.1. Tracking metrics

| Metric | Objective |
| --- | --- |
| TLS client-auth handshake success/failure | Detect certificate/trust store errors |
| OAuth2 client authentication failures by method | Distinguish mTLS errors from secret/basic errors |
| Bound token issuance count | Track how many tokens carry certificate binding |
| Missing/mismatch cnf count at RS | Detect clients using wrong certificates or tokens |
| Certificate expiry window | Alert on certificates approaching expiration |
| CRL/OCSP lookup failures | Detect revocation infrastructure failures |
| Token refresh failures after certificate rotation | Detect clients that haven't rotated certificates/tokens |
| Proxy certificate metadata validation failures | Detect proxy misconfiguration or header spoofing |

Do not log private keys, access tokens, refresh tokens, or full certificate chains unnecessarily. Controlled thumbprints may be logged for auditability, considering privacy and cardinality.

### 17.2. Signals requiring alerts

- Spike in `invalid_token` rates after certificate rotation.
- Mass client authentication failures after trust store updates.
- New certificate deployed while self-signed JWKS has not been updated.
- A client ID suddenly using multiple certificates outside any rotation plan.
- Tokens containing `cnf` while the RS receives no certificate attribute.
- Proxy forwarding headers appearing from untrusted sources.
- Multiple requests using the same token with different thumbprints.

### 17.3. Runbook when a client cannot call the API after changing certificates

1. Inspect the certificate the client actually sends to the RS during the TLS handshake.
2. Read `cnf.x5t#S256` from the verified token.
3. Compute the thumbprint from the DER certificate at the RS.
4. Compare the two values.
5. If different, determine which certificate was used to issue the token.
6. Have the client use the new certificate to request a new token from the AS.
7. If the new certificate is not yet registered/trusted by the AS, fix registration/CA/JWKS.
8. Verify the proxy does not drop or overwrite certificate metadata.
9. Re-check scopes, audience, and expiry once binding matches.

Never work around this by disabling the certificate-binding filter or accepting all thumbprints.

## 18. Design Mistakes to Avoid

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Thinking HTTPS equals mTLS | No client certificate authentication | Configure TLS to request/receive client certs |
| Thinking mTLS client authentication automatically binds tokens | Access token can still be a bearer token | Enable `x509CertificateBoundAccessTokens(true)` |
| Verifying only the JWT signature at the RS | Stolen tokens still work | Compare `cnf.x5t#S256` with TLS client cert |
| Hashing PEM or public key | Thumbprint violates RFC | Hash DER certificate with SHA-256 |
| Using Subject DN as a thumbprint | Multiple certificates can share a DN | Use `x5t#S256` |
| Trusting client-sent certificate headers | Certificate spoofing | Extract from TLS layer or trusted proxy |
| Not securing the reverse proxy | Attackers bypass proxy and forge metadata | Network isolation, backend mTLS, strip client headers |
| Using `client-auth: need` on all endpoints | Browsers/clients without certs fail handshake | Separate listeners or use `want` where needed |
| Trusting all self-signed certificates | Client impersonation | Match certificate against client's registered JWKS |
| Overly broad PKI trust | Certificate spoofing with same Subject DN | Restrict trust anchors and verify SAN/DN |
| Rotating cert while reusing old access tokens | Thumbprint mismatch | Obtain new access token using new cert |
| Treating refresh tokens as having the same cnf claim as access tokens | Misunderstanding binding mechanics | Refresh tokens bind to client and mTLS client auth per RFC 8705 |
| Skipping revocation checks | Revoked certs remain usable under lax policy | CRL/OCSP/denylist or online status checks |
| Only unit testing thumbprints | Does not prove TLS actually supplies the cert | Test HTTPS/mTLS end-to-end |
| mTLS filter not applied to all protected routes | API paths accept plain bearer tokens | Partition security matchers and filter chains |
| Ignoring audience/scope when cnf matches | Client with right cert can access wrong API | Validate full token and permissions |

## 19. Self-Check Questions

**Question 1.** How do mTLS client authentication and certificate-bound access tokens differ?

**Answer:** mTLS client authentication authenticates the client when calling the AS. Certificate-bound access tokens bind the access token to a certificate so the RS verifies that the client possesses the corresponding private key when calling the API.

**Question 2.** What data is `cnf.x5t#S256` computed from?

**Answer:** SHA-256 over the DER encoding of the entire X.509 certificate, Base64URL-encoded without padding.

**Question 3.** If a JWT has a valid signature but the certificate in the TLS handshake differs from the thumbprint in cnf, how does the RS handle it?

**Answer:** Reject the request with HTTP 401 and `invalid_token` per RFC 8705.

**Question 4.** How do `tls_client_auth` and `self_signed_tls_client_auth` differ?

**Answer:** The PKI method verifies the chain up to a trusted CA and binds the client via certificate attributes; the self-signed method matches the certificate against the client's registered JWKS.

**Question 5.** Does `TokenSettings.x509CertificateBoundAccessTokens(true)` automatically configure the TLS listener?

**Answer:** No. The listener must be configured to receive client certificates, and the AS must verify the certificate/client registration.

**Question 6.** Can a client reuse an old access token after rotating to a new certificate?

**Answer:** Not on an RS enforcing certificate binding, because the thumbprint in the token is bound to the old certificate. The client needs to request a new token with the new certificate.

**Question 7.** Can a Resource Server simply trust an `X-Client-Cert` header from the Internet?

**Answer:** No. Certificate metadata must come from the TLS layer or a trusted proxy that strips client-sent headers and forwards metadata over a protected backend channel.

**Question 8.** Must a refresh token contain `cnf.x5t#S256`?

**Answer:** No. Per RFC 8705, a confidential client's refresh token is bound indirectly via client ID and the requirement to authenticate the client with mTLS when presenting the refresh token.

**Question 9.** Why is testing a custom filter only with a mocked request attribute insufficient?

**Answer:** Because that test does not prove the TLS handshake actually requests and provides the certificate, that proxy forwarding is secure, or that the client possesses the corresponding private key.

## 20. Production Checklist

- [ ] Client is registered with the correct `TLS_CLIENT_AUTH` or `SELF_SIGNED_TLS_CLIENT_AUTH`.
- [ ] PKI trust anchors are restricted and lifecycle-managed.
- [ ] `x509CertificateSubjectDN` or client JWKS/x5c is properly configured.
- [ ] `TokenSettings.x509CertificateBoundAccessTokens(true)` is enabled for clients requiring binding.
- [ ] TLS listener properly requests/receives client certificates.
- [ ] Browsers and regular clients are not accidentally forced to use certificates when unnecessary.
- [ ] JWT tokens contain `cnf.x5t#S256`; opaque token introspection returns `cnf`.
- [ ] Resource Server obtains the certificate from a trusted TLS layer.
- [ ] Resource Server computes SHA-256 over the DER certificate and compares thumbprints.
- [ ] Missing certificates, missing cnf, and mismatches are all rejected.
- [ ] Routes requiring mTLS are not bypassed by another chain lacking the binding filter.
- [ ] If TLS terminates at a proxy, metadata travels over a trusted channel and header spoofing is blocked.
- [ ] Client uses the same certificate at both the Token Endpoint and the Resource Server.
- [ ] Certificate rotation includes plans to acquire new tokens and retire old tokens/certs.
- [ ] Refresh tokens still require appropriate client authentication.
- [ ] Policies exist for certificate expiry, CRL/OCSP, revocation, and compromise response.
- [ ] Real HTTPS/mTLS integration tests and proxy boundary tests are in place.
- [ ] Private keys, access tokens, refresh tokens, and unnecessary certificate data are never logged.

## 21. References and Conclusion

Standards and framework documentation:

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8705, Section 2 — Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705#section-2)
- [RFC 8705, Section 3 — Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705#section-3)
- [RFC 8705, Section 6 — Implementation Considerations](https://www.rfc-editor.org/rfc/rfc8705#section-6)
- [RFC 8705, Section 7 — Security Considerations](https://www.rfc-editor.org/rfc/rfc8705#section-7)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html)
- [Spring Authorization Server — X509ClientCertificateAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/X509ClientCertificateAuthenticationProvider.html)
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)

**Conclusion:** Certificate-bound access tokens add proof-of-possession to OAuth 2.0: the AS binds the token to the SHA-256 thumbprint of the client certificate, and the RS verifies that the certificate in the TLS handshake matches `cnf.x5t#S256`. Spring Authorization Server supports this configuration via `TokenSettings.x509CertificateBoundAccessTokens(true)` alongside mTLS client authentication. An implementation is complete only when all three layers work properly: the AS verifies the client certificate, the token carries the accurate binding, and the RS actually validates the certificate upon receiving requests. Managing proxy trust, certificate rotation, refresh tokens, and revocation are inseparable parts of taking mTLS-bound tokens to production.
