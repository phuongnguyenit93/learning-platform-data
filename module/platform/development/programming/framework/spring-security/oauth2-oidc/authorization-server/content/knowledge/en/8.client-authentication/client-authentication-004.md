# `client_secret_jwt` and Client Assertion Verification

## 1. Context and Objectives

In a Spring Boot application using **Spring Security** and **Spring Authorization Server** to build an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server**, a client typically must prove its identity before being issued tokens or calling certain protocol endpoints. <code>client_secret_jwt</code> is a **client authentication** method: the client creates an **HMAC-signed JWT** using a secret shared with the Authorization Server and sends that JWT in the <code>client_assertion</code> parameter.

Running example throughout: the <code>orders-batch</code> service runs internal jobs and is registered with the <code>client_credentials</code> grant and scope <code>orders.read</code>. The service generates a fresh assertion for each authentication attempt, signs it with an HMAC key derived from the client secret, and sends it to <code>https://auth.example.com/oauth2/token</code>. The Authorization Server verifies the assertion, checks the registered client, and only then processes the grant to issue an access token.

This lesson helps you:

1. Distinguish a client assertion from an **access token, ID Token, authorization grant**, and a client secret sent directly over HTTP.
2. Understand how to construct a standards-compliant JWT assertion, especially <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>iat</code>, <code>nbf</code>, <code>jti</code>, and the JWS header.
3. Configure <code>RegisteredClient</code> and HMAC algorithms in Spring Authorization Server; identify the filters/providers responsible for authentication.
4. Add server-side validation, replay protection, and secret lifecycle controls while understanding the limits of default validation.
5. Test valid requests as well as invalid signatures, wrong clients, wrong audiences, expired assertions, and replayed assertions.

**Scope:** This lesson covers the protocol and Spring Authorization Server's Servlet architecture using APIs familiar from the Spring Authorization Server 1.x branch. Newer Spring Security releases integrate Authorization Server components and may differ in packages/DSLs; always verify against the version you are running. Code snippets are educational examples, not a standalone runnable Spring Boot project.

## 2. Where Does Client Authentication Happen?

OAuth 2.0 separates **client authentication** (who the client is) from the **authorization grant** (the basis for issuing an access token). Both can appear in the same request to the token endpoint, yet they are verified by different components.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as orders-batch (Client)
    participant AS as Spring Authorization Server
    participant R as RegisteredClientRepository
    participant V as JWT assertion validator
    participant T as Token Endpoint / Grant Provider
    C->>C: Create new JWT, HMAC-sign with client secret
    C->>AS: POST /oauth2/token, grant_type=client_credentials, client_assertion=JWT
    AS->>R: Look up RegisteredClient and verify registered method
    R-->>AS: orders-batch + client settings
    AS->>V: Verify HMAC, alg, iss/sub/aud, timestamps, replay policy
    V-->>AS: Valid client or invalid_client
    AS->>T: If client is valid, process grant and access scope
    T-->>C: Access token or protocol error
~~~

In Spring Authorization Server, <code>OAuth2ClientAuthenticationFilter</code> receives the client authentication request. Under the framework's default setup, <code>JwtClientAssertionAuthenticationConverter</code> converts request data into an authentication token, and <code>JwtClientAssertionAuthenticationProvider</code> uses <code>JwtClientAssertionDecoderFactory</code> to verify the JWT against the specific <code>RegisteredClient</code>.

The client authentication result can be stored in the <code>SecurityContext</code> so the token endpoint or matching endpoint can continue processing. **Successful client authentication does not mean the grant or every scope is accepted**: the Authorization Server still must check the grant type, client permissions, policies, token lifetimes, and related conditions.

## 3. Distinguishing <code>client_secret_jwt</code> from Similar Mechanisms

| Mechanism | Credentials sent by client | Verification method | When to use |
| --- | --- | --- | --- |
| <code>client_secret_basic</code> | Client ID and secret via HTTP Basic | Match secret against registered data | Simple confidential client, strictly over HTTPS |
| <code>client_secret_post</code> | Client ID and secret in form body | Match secret | When compatibility with endpoints supporting it is needed; limit body exposure |
| **<code>client_secret_jwt</code>** | JWT HMAC-signed with a shared secret | Verify signature, claims, and client policy | Confidential client needing short-lived assertions |
| <code>private_key_jwt</code> | JWT signed with the client's **private key** | Verify trusted public key and claims | Client can manage its own private key, facilitating key separation |
| <code>none</code> | No secret client credentials | Public client policy, usually requiring PKCE for Authorization Code | SPAs/mobile apps that cannot hold secrets |
| <code>tls_client_auth</code> / <code>self_signed_tls_client_auth</code> | Authentication via TLS certificate | Verify certificate and registration binding | Environments with suitable mTLS infrastructure |

Do not confuse:

- A **JWT client assertion** proves the identity of an **OAuth client** to the Authorization Server.
- A **JWT access token** is a token issued for the client to call a **Resource Server**, with the API's audience as designed.
- An **OIDC ID Token** is proof of End-User authentication intended for an OIDC client.
- A **JWT Bearer authorization grant** uses <code>grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer</code> to present an assertion as a **grant**; that is a different purpose from <code>client_assertion</code>.

A validly signed JWT from a client **must not automatically be treated as an access token**. Accepting the same JWT across different contexts can lead to token substitution or cross-JWT confusion vulnerabilities.

## 4. Sending Assertions Under RFC 7523

### 4.1. HTTP Request

When a client uses <code>client_secret_jwt</code> for the <code>client_credentials</code> grant:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders.read&
client_id=orders-batch&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=eyJhbGciOiJIUzI1NiIsInR5cCI6ImNsaWVudC1hdXRoZW50aWNhdGlvbitqd3QifQ...
~~~

Line breaks and the truncated JWT string are only for readability. Real requests must be **properly form-URL-encoded**, sent over HTTPS, include the complete compact JWS assertion, and **never log raw JWTs or secrets**.

Two core parameters:

| Parameter | Value / Meaning |
| --- | --- |
| <code>client_assertion_type</code> | Constant <code>urn:ietf:params:oauth:client-assertion-type:jwt-bearer</code>. |
| <code>client_assertion</code> | A signed, short-lived JWT proving possession of the client secret. |

Including <code>client_id</code> in the example helps clearly identify the client; if sent, it must match <code>iss</code>/<code>sub</code> and the actual registration. Do not also send <code>Authorization: Basic ...</code> to present a second client authentication method in the same request. The grant may be <code>authorization_code</code>, <code>refresh_token</code>, or another suitable type if registered for the client; this example uses <code>client_credentials</code> to focus on client authentication.

### 4.2. JWT Header and Payload

Example JWS header:

~~~json
{
  "alg": "HS256",
  "typ": "client-authentication+jwt"
}
~~~

Example payload with **illustrative** timestamps, which must be replaced with real Unix timestamps when generating an assertion:

~~~json
{
  "iss": "orders-batch",
  "sub": "orders-batch",
  "aud": "https://auth.example.com",
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794800060,
  "jti": "7b6c24a5-16c1-4f0c-b8d9-b812ab7ed8fc"
}
~~~

Do not use the timestamps above verbatim. In practice, the client sets <code>iat</code> to the current time, <code>exp</code> shortly afterward (for example, 60 seconds), and a fresh <code>jti</code> per assertion; server policy determines the allowed clock skew and TTL.

| Field | Requirement and verification |
| --- | --- |
| <code>alg</code> | JWT signing algorithm, here HMAC SHA-256. The server must accept only algorithms registered/allowed for the client; **never accept <code>none</code>**. |
| <code>typ</code> | RFC 10070 recommends <code>client-authentication+jwt</code> to distinguish client authentication assertions. Use compatibility rules when rolling out with legacy clients. |
| <code>iss</code> | For client authentication, <code>iss</code> is the **client ID** of the client issuing the JWT. |
| <code>sub</code> | For client authentication, **must be the client ID**. Not the End-User and not the Authorization Server's issuer URL. |
| <code>aud</code> | Issuer identifier of the **target Authorization Server**, singular per RFC 10070. |
| <code>exp</code> | Required; expired JWTs must be rejected. Overly distant expiration times should also be rejected per policy. |
| <code>nbf</code> | Optional; if present, do not accept the JWT before this timestamp (aside from accepted clock skew). |
| <code>iat</code> | Optional under RFC 7523; useful to cap assertion age and detect clock drift. |
| <code>jti</code> | Optional under RFC 7523; should be uniquely generated and checked for replays when single-use assertions are required. |

**Note:** Legacy examples sometimes set <code>aud</code> to the token endpoint URL. That no longer aligns with the updated requirement specifically for **JWT client authentication** in RFC 10070 (11/2026), presented in the next section.

## 5. New Audience Requirement in RFC 10070 (11/2026)

**RFC 10070** updates RFCs 7521, 7522, 7523, and 9126 to eliminate ambiguous audience choices when assertions are sent to an Authorization Server. For **JWT client authentication**, the current rules are:

1. The Authorization Server must have a stable **issuer identifier** per RFC 8414.
2. The JWT client assertion must set **<code>aud</code> exclusively to that issuer identifier**, for example <code>https://auth.example.com</code>.
3. The JWT client assertion **must not use the token endpoint URL as audience**, even though the physical request is sent to <code>https://auth.example.com/oauth2/token</code>.
4. The Authorization Server must **reject** assertions with a different audience or multiple audiences; clients must update assertion generation for compatibility.
5. Clients **should** use JWS header <code>typ=client-authentication+jwt</code>; the RFC does not recommend rejecting legacy clients solely for omitting explicit typing, to preserve compatibility while tightening audience validation.

Audience validation examples:

| JWT <code>aud</code> claim | Outcome under RFC 10070 |
| --- | --- |
| <code>"https://auth.example.com"</code> | Valid for the **audience check** if it matches the server's issuer. |
| <code>"https://auth.example.com/oauth2/token"</code> | **Rejected**: the token endpoint is not the issuer identifier. |
| <code>["https://auth.example.com", "https://other.example.com"]</code> | **Rejected**: contains an additional audience. |
| <code>"https://orders.api.example.com"</code> | **Rejected**: this is an API, not the Authorization Server. |
| Missing <code>aud</code> | **Rejected**. |

A single-element audience array containing **only the issuer value** can represent the same content under JSON Web Token rules, though emitting a plain issuer string when tooling allows is preferable. Validation must verify that the **audience set contains solely the exact issuer**; a naive <code>contains(issuer)</code> check would allow multi-audience arrays and is insufficient for the new requirement.

RFC 10070 applies specifically to **client authentication assertions**; JWTs used as **authorization grants** have their own audience rules. Do not infer that every OAuth 2.0 JWT must set <code>aud</code> to the Authorization Server issuer: access tokens meant for Resource Servers carry different audiences per profile.

**Version compatibility note:** Some older implementations or legacy clients may still apply original RFC 7523 audience validation, accepting token endpoint URLs or multiple audiences. Verify the exact Spring Authorization Server version you run and add appropriate validators if it does not yet enforce RFC 10070; never assume the library already reflects every protocol update.

## 6. HMAC and the Shared Secret

With <code>client_secret_jwt</code>, the client and Authorization Server share a **shared secret**. The client computes a JWS signature using the configured HMAC algorithm. For <code>HS256</code>, HMAC uses the bytes of the **UTF-8 representation of the client secret** as the key:

~~~text
JWT signing input = BASE64URL(header) + "." + BASE64URL(payload)
signature         = HMAC-SHA256(UTF8(client_secret), signing_input)
client_assertion  = BASE64URL(header) + "." + BASE64URL(payload)
                    + "." + BASE64URL(signature)
~~~

The Authorization Server must look up the right registered client, fetch the **corresponding key from a trusted source**, and verify the signature. Simply decoding JSON claims and seeing matching <code>iss</code>/<code>sub</code> is not enough: an attacker can forge any payload if HMAC is not verified.

### 6.1. Secret Length and Entropy

An HS256 signing secret should be generated with a **cryptographically secure random generator** and have entropy at least matching the desired security level (typically at least 256 bits for HS256). Guessable passwords like <code>secret123</code> or secrets reused across clients are vulnerable to offline key-guessing if an assertion is captured.

HMAC does not mean "no need to protect the secret" just because the client does not send the raw secret in an HTTP form. Anyone holding the secret can sign valid assertions; thus the secret must be distributed and protected like any credential. Always use TLS and keep requests/responses out of logs, proxy analytics, or payload-capturing monitoring tools.

### 6.2. HMAC Secrets Differ from Password Hashes

This is a common pitfall when implementing <code>client_secret_jwt</code>:

- With <code>client_secret_basic</code>, the server can store a **one-way hash** of the secret (such as BCrypt) and compare against the secret the client sends.
- With <code>client_secret_jwt</code>, the server needs the **HMAC key** to compute and verify signatures itself. A BCrypt hash cannot be reversed to recover the exact bytes of the original secret.
- Therefore, you must design **a mechanism that provides the usable secret/HMAC key for verification**: a secret manager/KMS or protected trusted store, integrated with <code>RegisteredClientRepository</code> and the framework version's decoder factory. Do not assume that storing <code>{bcrypt}...</code> in <code>RegisteredClient.clientSecret</code> works directly with HMAC verification.

Spring Security recommends formatting client secrets in <code>RegisteredClient</code> for <code>PasswordEncoder</code> in secret-comparison flows; meanwhile <code>client_secret_jwt</code> has distinct HMAC key-material requirements. When the same client needs multiple methods, design storage/rotation and test against the actual implementation rather than inferring from property descriptions. Consider <code>private_key_jwt</code> when you do not want the server storing shared signing secrets.

## 7. Registering the Client in Spring Authorization Server

### 7.1. Java <code>RegisteredClient</code> Example

~~~java
// Spring Authorization Server 1.x configuration snippet.
// Isolated demo only: {noop} provides no storage protection for the secret.
RegisteredClient batchClient = RegisteredClient
    .withId("orders-batch-record-001")
    .clientId("orders-batch")
    .clientSecret("{noop}DEMO_REPLACE_WITH_RANDOM_HIGH_ENTROPY_SECRET")
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_JWT)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .tokenEndpointAuthenticationSigningAlgorithm(MacAlgorithm.HS256)
        .build())
    .build();

RegisteredClientRepository clients =
    new InMemoryRegisteredClientRepository(batchClient);
~~~

<code>ClientAuthenticationMethod.CLIENT_SECRET_JWT</code> enables this method. <code>tokenEndpointAuthenticationSigningAlgorithm(MacAlgorithm.HS256)</code> pins the HMAC algorithm for JWT client authentication. Do not use RSA/EC algorithms (such as <code>RS256</code>) for shared-secret assertions, as those belong to <code>private_key_jwt</code>.

The secret value here **is intentionally a non-production placeholder**; for real testing, replace it with a sufficiently strong random secret distributed consistently to both client and server and verify storage formatting per your Spring version. <code>{noop}</code> is only for local illustration, not a production credential storage choice. <code>InMemoryRegisteredClientRepository</code> suits learning; production should use persistent storage and secret-protection mechanisms.

### 7.2. Spring Boot Properties Can Register the Method

In Spring Boot versions with Spring Authorization Server auto-configuration, a static client can be defined under the <code>spring.security.oauth2.authorizationserver.client</code> namespace:

~~~yaml
spring:
  security:
    oauth2:
      authorizationserver:
        client:
          orders-batch:
            registration:
              client-id: orders-batch
              client-secret: "{noop}LOCAL_DEMO_ONLY_SECRET"
              client-authentication-methods:
                - client_secret_jwt
              authorization-grant-types:
                - client_credentials
              scopes:
                - orders.read
            token-endpoint-authentication-signing-algorithm: HS256
~~~

**Note:** Property mappings and nested attribute locations depend on the Spring Boot version. This example illustrates the registration idea and must be checked against your active version's configuration metadata. Do not define the same real client simultaneously in YAML and a manually created Java <code>RegisteredClientRepository</code> bean expecting the two sources to merge; auto-configuration may back off when a manual bean is present. In production, prefer a secret manager and never commit real key values to YAML.

### 7.3. Why Do You Still Need an Authorization Server SecurityFilterChain?

<code>RegisteredClient</code> is only a **client registration record**; it does not expose the token endpoint by itself. The Authorization Server must wire protocol components through the DSL:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());
    return http.build();
}
~~~

This is a **DSL skeleton**; it still requires core Authorization Server infrastructure beans and a user login chain if End-Users are involved. <code>OAuth2ClientAuthenticationFilter</code> and the JWT client assertion provider are part of the default Authorization Server configuration when properly enabled. Do not write a custom filter to parse JWTs yourself unless you have an explicit extension requirement and have verified the framework hooks.

## 8. How Does the Client Build a JWT Assertion?

The client must use the raw secret provisioned through a secure mechanism, not the server's <code>{noop}...</code> prefix or BCrypt hash as the key. With Spring Security JOSE/JWT, you can use <code>NimbusJwtEncoder</code> and <code>ImmutableSecret</code> for HMAC signing.

~~~java
// Code running in the CLIENT backend; never place in frontend/mobile apps.
String clientId = "orders-batch";
String issuerOfAuthorizationServer = "https://auth.example.com";
String rawSecret = secretManager.read("oauth/orders-batch/hmac-secret");

// secretManager is an application-provided abstraction. HS256 key must be strong.
byte[] hmacKey = rawSecret.getBytes(StandardCharsets.UTF_8);
JwtEncoder encoder = new NimbusJwtEncoder(
    new ImmutableSecret<SecurityContext>(hmacKey));

Instant now = Instant.now();
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer(clientId)
    .subject(clientId)
    .audience(List.of(issuerOfAuthorizationServer))
    .issuedAt(now)
    .notBefore(now)
    .expiresAt(now.plusSeconds(60))
    .id(UUID.randomUUID().toString())
    .build();

JwsHeader header = JwsHeader.with(MacAlgorithm.HS256)
    .type("client-authentication+jwt")
    .build();

String assertion = encoder.encode(
    JwtEncoderParameters.from(header, claims)).getTokenValue();
~~~

<code>SecretManager</code> here is an illustrative application interface, not a built-in Spring Security class. You must supply a secure implementation, such as integrating an approved secret manager. <code>ImmutableSecret</code> comes from Nimbus JOSE/JWT; imports and dependencies must match your Spring Boot/Spring Security version.

Then send the form request (for example with Spring <code>WebClient</code>):

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("grant_type", "client_credentials");
form.add("scope", "orders.read");
form.add("client_id", clientId);
form.add("client_assertion_type",
    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer");
form.add("client_assertion", assertion);

// Token endpoint must be a trusted HTTPS URL configured from metadata.
Mono<String> response = WebClient.create()
    .post()
    .uri("https://auth.example.com/oauth2/token")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(form))
    .retrieve()
    .bodyToMono(String.class);
~~~

This snippet uses <code>WebClient</code> to illustrate sending the request; configure timeouts, TLS verification, error handling, and token response deserialization before production use. **Generate a fresh assertion on every authentication attempt** rather than caching one assertion across requests. Never log assertions or send them to analytics.

**Audience note:** <code>audience(List.of(issuerOfAuthorizationServer))</code> represents exactly one audience. If the framework encodes it as a single-element JSON array, it still holds strictly that single issuer value; for peers requiring a plain JSON string, test interoperability against your actual configuration. Never substitute the token endpoint URI for the issuer.

## 9. Steps to Verify a Client Assertion

To accept a <code>client_secret_jwt</code> request, the Authorization Server performs a coordinated set of checks:

~~~mermaid
flowchart TD
    R["POST /oauth2/token"] --> A{"Valid client_assertion_type and well-formed JWT?"}
    A -- No --> E["invalid_client"]
    A -- Yes --> B{"RegisteredClient found and client_secret_jwt allowed?"}
    B -- No --> E
    B -- Yes --> C{"Registered HMAC alg and signature valid for client key?"}
    C -- No --> E
    C -- Yes --> D{"iss = sub = client_id, aud solely AS issuer?"}
    D -- No --> E
    D -- Yes --> F{"exp / nbf / iat and TTL valid?"}
    F -- No --> E
    F -- Yes --> G{"jti unused if anti-replay policy applies?"}
    G -- No --> E
    G -- Yes --> H["Client authenticated"]
    H --> I{"Grant type, scope, policy valid?"}
    I -- No --> J["Reject with appropriate grant/scope error"]
    I -- Yes --> K["Issue access token"]
~~~

The diagram illustrates **logical checks**; the exact order across parsers, decoders, providers, and grant providers depends on the implementation. Certain checks such as <code>iat</code> age caps, maximum TTLs, and <code>jti</code> replay protection are **additional hardening**—do not assume the framework enables them automatically.

### 9.1. Verifying Client and Algorithm

- Look up the exact <code>RegisteredClient</code> by client identity; never use an unauthenticated <code>kid</code> header or <code>iss</code> claim to pick **any** key outside the client's scope.
- Verify the client registered <code>CLIENT_SECRET_JWT</code>, the secret is neither expired nor revoked, and the client is active per policy.
- Accept <code>HS256</code> only if the client is configured for HS256; prevent substitution with <code>alg=none</code>, <code>RS256</code>, or other algorithms.
- With HMAC, the secret belongs to **that specific client**; never share one key across clients where client A could impersonate client B.
- Do not require <code>jwkSetUrl</code> for standard HMAC <code>client_secret_jwt</code>; <code>private_key_jwt</code> uses public keys/JWKS and follows a different key-custody model.

### 9.2. Verifying Claims

1. <code>iss</code> must be a valid client ID consistent with the resolved client.
2. <code>sub</code> must equal the client ID, not an end-user's username.
3. <code>aud</code> must contain solely the Authorization Server's issuer per RFC 10070.
4. <code>exp</code> must be present and unexpired; the server should enforce a reasonable upper bound to prevent overly long-lived assertions.
5. <code>nbf</code>, if present, must permit use at the current time; <code>iat</code> should be bounded when an assertion age policy applies.
6. If replay protection is implemented, <code>jti</code> must be unique per client within the acceptance window and accepted only once.
7. The <code>typ</code> header should identify the assertion type appropriately; manage legacy client compatibility per RFC 10070 and RFC 8725.

Never rely solely on inspecting <code>iss</code>/<code>sub</code> before verifying the JWT signature. Base64URL decoding or reading the JWT payload **does not** verify the issuer.

### 9.3. Assertions Authenticate the Client Only, Not Scopes

After the client is authenticated, the token endpoint still verifies <code>grant_type</code>, scopes, policies, and client type. For instance, a completely valid HS256 assertion from <code>orders-batch</code> still cannot request <code>billing.admin</code> if that scope is not in its registration/policy. Nor may a grant type be accepted if the client is not authorized to use it.

## 10. Adding Custom Validators in Spring Authorization Server

### 10.1. Default Validation and Gaps You May Need to Fill

Spring Authorization Server documentation describes <code>JwtClientAssertionDecoderFactory.DEFAULT_JWT_VALIDATOR_FACTORY</code> as the default validator set for <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, and <code>nbf</code>. It does not guarantee that custom policies—such as maximum TTL, <code>jti</code> replay protection, or **strictly single-issuer audience** per RFC 10070—are enforced across all versions.

To add rules, the framework provides the hook <code>JwtClientAssertionAuthenticationProvider.setJwtDecoderFactory()</code>. The proper pattern is to **keep the default validators and compose additional validators**, rather than replacing all mandatory checks.

### 10.2. Example: Enforcing Single-Issuer Audience and TTL Limits

The example below uses Spring Authorization Server 1.x to add a hardening layer for **JWT client assertions**. It assumes the core Authorization Server infrastructure beans and version-appropriate imports are present:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.clientAuthentication(clientAuth ->
                clientAuth.authenticationProviders(providers -> {
                    for (AuthenticationProvider provider : providers) {
                        if (provider instanceof JwtClientAssertionAuthenticationProvider jwtProvider) {
                            JwtClientAssertionDecoderFactory factory =
                                new JwtClientAssertionDecoderFactory();

                            factory.setJwtValidatorFactory(client ->
                                new DelegatingOAuth2TokenValidator<>(
                                    JwtClientAssertionDecoderFactory
                                        .DEFAULT_JWT_VALIDATOR_FACTORY.apply(client),
                                    issuerOnlyAndShortLifetime("https://auth.example.com")
                                )
                            );
                            jwtProvider.setJwtDecoderFactory(factory);
                        }
                    }
                }))
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}

private static OAuth2TokenValidator<Jwt> issuerOnlyAndShortLifetime(
        String expectedIssuer) {
    return jwt -> {
        List<String> audiences = jwt.getAudience();
        if (audiences.size() != 1
                || !expectedIssuer.equals(audiences.get(0))) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Client assertion must target the AS issuer only", null));
        }

        Instant issuedAt = jwt.getIssuedAt();
        Instant expiresAt = jwt.getExpiresAt();
        if (issuedAt == null || expiresAt == null
                || issuedAt.isAfter(Instant.now().plusSeconds(30))
                || expiresAt.isAfter(issuedAt.plusSeconds(120))) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Invalid client assertion lifetime", null));
        }
        return OAuth2TokenValidatorResult.success();
    };
}
~~~

The 120-second cap and 30-second clock skew are **illustrative policies**; set them to match your security and time-sync requirements. The default validator still enforces standard claims. In the HTTP response, JWT client authentication failures must map to **<code>invalid_client</code>** per RFC 7523; the <code>invalid_token</code> string inside <code>OAuth2Error</code> in this example is an internal validator error code, not a recommendation to return <code>invalid_token</code> to the client.

**Important note:** this example enforces a single-issuer audience and checks lifetime, but **does not yet implement a <code>jti</code> anti-replay store**. For distributed client assertion validation, add a shared <code>jti</code> storage/check mechanism with TTL and atomic semantics—never use a local <code>HashSet</code> and assume it is safe across multiple instances.

### 10.3. Do Not Reuse the Resource Server JWT Decoder as the Client Assertion Decoder

JWT access tokens signed by the Authorization Server are typically verified by Resource Servers using the Authorization Server's **public** JWKs. By contrast, <code>client_secret_jwt</code> must be verified with the **client's shared secret** and matched against the registered client. These are two different trust relationships.

Never point the client assertion decoder to the public JWKS that the Authorization Server publishes for access tokens/ID Tokens. Likewise, never expose HMAC secrets on a public JWKS endpoint. <code>JwtClientAssertionDecoderFactory</code> exists to build decoders within the **RegisteredClient context**, not a shared decoder unaware of which client signed the token.

## 11. Replay Protection and <code>jti</code> Management

A JWT assertion is typically a **short-lived bearer credential**: anyone holding a copy of a still-valid assertion can attempt to replay it at the token endpoint. Checking the signature and <code>exp</code> prevents payload tampering, **but does not automatically block replays within the validity window**.

RFC 7523 allows using <code>jti</code> to identify tokens and track used values during their validity period. A replay-mitigation design should:

1. Have the client generate a fresh <code>jti</code> using a random UUID or high-entropy identifier for **each assertion**.
2. After verifying the signature and resolving the client, have the server record <code>(registeredClientId, jti)</code> in a **centralized** cache/database with a TTL at least covering the assertion lifetime plus relevant clock skew.
3. Make accepting a <code>jti</code> **atomic**: the first request creates the record successfully; subsequent requests with the same <code>jti</code> are rejected. Never use a separate read-then-write sequence vulnerable to race conditions.
4. If replay state cannot be determined due to store failure, apply fail-closed behavior for endpoints requiring replay protection.
5. Never log full assertions for auditing. You may log client ID, timestamp, outcome, and a controlled hash/ID per data policy.

**This is an additive design**, not a claim that Spring Authorization Server ships with a built-in <code>jti</code> cache satisfying all of these requirements. If adopted, identify the appropriate hook/provider, test concurrent requests, and plan expiry/cleanup strategies.

If an HMAC secret is compromised, <code>jti</code> replay protection only blocks replaying **the exact same assertion**; an attacker holding the secret can still sign new assertions. Therefore you need secret protection, rotation, and anomaly detection together.

## 12. Safely Operating Secrets, Algorithms, and Issuers

### 12.1. Protecting and Rotating Client Secrets

Because HMAC requires both client and server to compute signatures with the same key, manage:

- **Key generation:** generate high-entropy secrets with enough bytes for approved algorithms like HS256/HS384/HS512.
- **Distribution:** exchange via a secret manager and secure channel; only the confidential client backend and Authorization Server should have read access.
- **Storage:** encrypt and restrict key access; never copy into source code, logs, metrics, frontends, CI output, or tickets.
- **Rotation:** plan rollover timing, compatibility windows, and safe ordering for updating client and server; never assume every client/version supports multiple HMAC keys simultaneously.
- **Revocation:** on suspected compromise, replace the secret, block old assertions, and review issued tokens based on revocation capabilities; update audit/incident response records.
- **Monitoring:** track rates of <code>invalid_client</code>, wrong audience, wrong alg, duplicate <code>jti</code>, and clock errors; apply thoughtful rate limiting to mitigate brute force/DoS.

If your product requires independent key rotation by <code>kid</code> and publishing public keys without sharing secrets, <code>private_key_jwt</code> is usually a better fit. Never treat a client-supplied <code>kid</code> as a trusted directive to fetch arbitrary keys from external URLs.

### 12.2. Issuer and Proxies

In a reverse-proxy environment:

~~~text
Client -- HTTPS --> https://auth.example.com/oauth2/token
                         |
                         v
                 Trusted reverse proxy
                         |
                         v
                 Authorization Server app
                 internal: http://auth-svc:9000

JWT client assertion aud = "https://auth.example.com"
AuthorizationServerSettings.issuer = "https://auth.example.com"
~~~

<code>aud</code> must be the **public issuer** advertised by the server (not <code>http://auth-svc:9000</code>). Keep the issuer aligned with OAuth Authorization Server Metadata / OIDC discovery. Forwarded headers must be set by a trusted proxy and never spoofable by users to alter the computed issuer or endpoints.

### 12.3. Standards Compliance Level

If migrating from legacy RFC 7523 examples written prior to November 2026, check whether clients currently set <code>aud</code> to the token endpoint or send multiple audiences. When upgrading to comply with RFC 10070, update both client assertion generation and Authorization Server validation logic under a coordinated rollout plan, avoiding long-term exceptions that accept wrong audiences just to "keep things working."

## 13. Returned Errors and Diagnostics

During client authentication, an invalid or mismatched JWT must yield the OAuth error <code>invalid_client</code>; the HTTP status is typically 400 or 401 depending on the case, implementation, and HTTP authentication requirements. Never expose secrets, signing-key details, or the full JWT in responses.

| Symptom | Causes to check |
| --- | --- |
| <code>invalid_client</code> even though client ID exists | Client not registered for <code>client_secret_jwt</code>, wrong secret/key, disabled client, or invalid assertion. |
| HMAC signature mismatch | Different raw secrets, different bytes/UTF-8 encoding, different alg, overly short key, or using a BCrypt hash as the key. |
| Invalid <code>iss</code>/<code>sub</code> | Client assertion sets username or AS issuer instead of client ID; client ID mismatches registration. |
| Invalid <code>aud</code> | Uses token endpoint URL instead of AS issuer or sends multiple audiences; this must be rejected under RFC 10070. |
| Expired / not yet valid | Wrong <code>exp</code>/<code>nbf</code>/<code>iat</code> or clock skew between client and server. |
| Replayed assertion | Same <code>jti</code> resent and rejected by replay policy. |
| Valid assertion but no token issued | Grant type/scope unregistered or rejected by another server policy; inspect grant error separately. |
| Token endpoint returns HTML login or 404 | AS security filter chain mismatch, configurer not attached, or request fell through to web chain. |
| Failures after rotation | Client/server using different key versions or old key retired too early. |

A safe diagnostic practice is logging **the error code and client ID**, timestamp, request ID, and validation condition tag (for example <code>aud_mismatch</code>), without logging raw assertions or secrets. In development you can enable controlled Spring Security DEBUG logging; avoid TRACE in production or insecure log pipelines.

## 14. Testing <code>client_secret_jwt</code>

### 14.1. Integration Test Matrix

| Test | Input variation | Expected outcome |
| --- | --- | --- |
| Valid client | HS256 with right key, <code>iss=sub=orders-batch</code>, audience matches issuer, valid lifetime | Client authenticated; grant processed per policy. |
| Wrong key | HMAC signed with another client's secret | <code>invalid_client</code>. |
| Wrong algorithm | Change <code>alg</code> to <code>none</code>, <code>RS256</code>, or unregistered HMAC alg | <code>invalid_client</code>. |
| Wrong client ID | <code>sub</code> is a different client from <code>iss</code>/<code>client_id</code> | <code>invalid_client</code>. |
| Legacy-style wrong audience | <code>aud=https://auth.example.com/oauth2/token</code> | Rejected per RFC 10070. |
| Second audience added | <code>aud</code> contains issuer plus another URL | Rejected per RFC 10070. |
| Missing or past <code>exp</code> | Missing claim / expired | <code>invalid_client</code>. |
| Exceeds internal TTL | <code>exp</code> set too far after <code>iat</code> | Rejected if TTL cap is enabled. |
| Future <code>nbf</code> | Not yet valid | Rejected subject to clock skew. |
| Reused <code>jti</code> | Two requests with the same signed assertion | Second request rejected **if anti-replay is implemented**. |
| Client not registered for JWT method | RegisteredClient only supports <code>client_secret_basic</code> | <code>invalid_client</code>. |
| Valid JWT, unregistered scope | Client requests <code>admin.write</code> | Scope/grant rejected appropriately; no over-privileged permissions issued. |
| Client Credentials without End-User | Valid JWT client assertion | Token represents client/service per grant, creates no End-User session. |
| Restart / multi-node / rotation | Instance or key switch | Consistent behavior per secret store and replay state. |

Tests should send real requests through <code>OAuth2ClientAuthenticationFilter</code>, <code>JwtClientAssertionAuthenticationProvider</code>, and the real token endpoint. Unit-testing a claim parser alone or using MockMvc with a fake <code>authentication()</code> does not prove signatures and audiences are actually verified.

### 14.2. Example Audience Validator Test

The snippet below illustrates a unit test for **the extra validator in Section 10**, not a replacement for integration tests:

~~~java
@Test
void rejectsMultipleAudiencesForClientAssertion() {
    OAuth2TokenValidator<Jwt> validator =
        issuerOnlyAndShortLifetime("https://auth.example.com");

    Instant now = Instant.now();
    Jwt assertion = Jwt.withTokenValue("test-only")
        .header("alg", "HS256")
        .issuer("orders-batch")
        .subject("orders-batch")
        .audience(List.of(
            "https://auth.example.com",
            "https://other.example.com"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(60))
        .build();

    assertThat(validator.validate(assertion).hasErrors()).isTrue();
}
~~~

This test only confirms the custom audience validator rejects multiple audiences. It **does not verify signatures** because <code>Jwt.withTokenValue()</code> constructs a synthetic JWT object for testing. To prove client authentication integration, call the token endpoint with a genuinely signed assertion using the registered key and inspect the HTTP response.

### 14.3. Security Invariants to Preserve

~~~text
Accepted client assertion:
  authenticated client == RegisteredClient(client_id)
  iss == sub == client_id
  aud == AS issuer (sole audience)
  alg == registered JWS algorithm
  signature verified with the corresponding client key
  exp/nbf valid; TTL policy satisfied
  jti not replayed (if required by policy)

After client authentication:
  granted scopes ⊆ client registered/policy allowed scopes
  grant type ∈ client registered/allowed grant types
~~~

## 15. Practice Exercise

You are designing an Authorization Server for three clients: <code>batch-exporter</code>, <code>billing-worker</code>, and <code>dashboard-spa</code>.

1. Select an appropriate client authentication method for each client. Explain why a browser SPA cannot be considered a confidential client just because its JavaScript can construct a JWT.
2. Write a <code>RegisteredClient</code> for <code>batch-exporter</code> using <code>client_secret_jwt</code> with HS256, <code>client_credentials</code>, and scope <code>reports.export</code>. Indicate where the secret is retrieved from a secret manager.
3. Construct a JWT payload with <code>iss=sub=batch-exporter</code>, <code>aud=https://identity.example.com</code>, <code>exp</code> 60 seconds after <code>iat</code>, and a unique <code>jti</code>. Explain why <code>https://identity.example.com/oauth2/token</code> must not be used as the audience.
4. Design validation covering key verification, algorithm, registered method, issuer/sub, sole audience, timestamps, and a replay-protection mechanism running across two instances.
5. Create an HMAC secret rotation plan for suspected compromise, identifying tokens/authorizations to review, transition window, and how to monitor authentication failures.
6. Write an integration test sending a valid JWT and a JWT with one byte modified in the payload; verify the tampered request receives <code>invalid_client</code>.
7. Compare operational overhead and trust boundaries between <code>client_secret_jwt</code> and <code>private_key_jwt</code> in a multi-client system.

A solid solution must **separate client authentication from access token issuance**, describe the HMAC key accurately, validate audiences per RFC 10070, and never assume optional protections like replay prevention are enabled by the framework automatically.

## 16. References

- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): defines how JWT client assertions are sent and core claims.
- [RFC 10070 (11/2026) — Updates to JWT Client Authentication and Assertion-Based Grants](https://www.rfc-editor.org/rfc/rfc10070): mandatory update requiring sole audience equal to the Authorization Server issuer and recommending explicit JWT typing.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer identifier and metadata.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithms, explicit typing, and preventing token confusion.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): claim structure, audience, and timestamps.
- [OpenID Connect Core 1.0, §9 — Client Authentication](https://openid.net/specs/openid-connect-core-1_0.html#ClientAuthentication): <code>client_secret_jwt</code>, HMAC keys from client secrets, and OIDC methods.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): <code>OAuth2ClientAuthenticationFilter</code>, converters/providers, and customizing <code>JwtClientAssertionDecoderFactory</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>ClientSettings</code>, repositories, and algorithm settings.
- [Spring Boot — OAuth2 Support](https://docs.spring.io/spring-boot/reference/security/oauth2.html): auto-configuration examples and client properties.
