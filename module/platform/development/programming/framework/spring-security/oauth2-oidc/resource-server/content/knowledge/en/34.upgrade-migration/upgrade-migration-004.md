# Changes to Decoders, Introspectors, and Default Implementation Classes

When upgrading a Spring Security OAuth 2.0 Resource Server, part of the risk lies in classes applications rarely write themselves: **JwtDecoder**, **ReactiveJwtDecoder**, **OpaqueTokenIntrospector**, **ReactiveOpaqueTokenIntrospector**, and their default implementations. These classes govern how access tokens are verified, how connections to the Authorization Server are made, how signing keys are handled, and how claims map to principals and authorities.

From Spring Security 6.5 to 7.0/7.1, several changes require advance preparation:

- Validation of the JWT **typ** header moves from Nimbus's internal check to **JwtTypeValidator**.
- Opaque-token introspection moves to passing unencoded client ID/secret values so Spring handles URL-encoding when building the request.
- Legacy constructors on several introspectors are marked deprecated; builders become the recommended way to instantiate them.
- Spring Security 7.1 adds **RestClientOpaqueTokenIntrospector** for the Servlet stack when using Spring `RestClient`.
- The default HTTP timeout for fetching JWKS in **NimbusJwtDecoder** changes from 500 ms to 30 seconds.
- Several setters on **BearerTokenAuthenticationFilter** are replaced by configuration via **BearerTokenAuthenticationConverter**.

Beyond version-specific changes, it is important to understand how Spring Boot auto-configures decoders/introspectors and when a custom bean overrides the default implementation. When constructing a decoder or introspector manually, an application can inadvertently drop issuer/timestamp/type validation, supply wrong credentials, alter timeouts, or lose lazy discovery behavior.

This lesson explains how to review the configuration, distinguish Servlet from WebFlux, upgrade safely from 6.5 to 7.x, test the new behavior, and avoid swapping implementations just because class names changed.

## 1. Map of Abstractions and Implementations

Spring Security separates the token verification contract from concrete implementations.

| Token and Stack | Contract | Common Spring Implementation |
|---|---|---|
| JWT, Servlet | **JwtDecoder** | **NimbusJwtDecoder** |
| JWT, WebFlux | **ReactiveJwtDecoder** | **NimbusReactiveJwtDecoder** |
| Opaque, Servlet | **OpaqueTokenIntrospector** | **SpringOpaqueTokenIntrospector**; **RestClientOpaqueTokenIntrospector** added in 7.1 |
| Opaque, WebFlux | **ReactiveOpaqueTokenIntrospector** | **SpringReactiveOpaqueTokenIntrospector** |

These abstractions serve distinct roles:

- **JwtDecoder** accepts a compact JWT string and returns a decoded, verified, and validated `Jwt`.
- **ReactiveJwtDecoder** works similarly but returns `Mono<Jwt>`.
- **OpaqueTokenIntrospector** calls the introspection endpoint and returns an `OAuth2AuthenticatedPrincipal`.
- **ReactiveOpaqueTokenIntrospector** performs introspection asynchronously and returns `Mono<OAuth2AuthenticatedPrincipal>`.

Higher-level authentication providers/managers rely on these contracts:

~~~mermaid
flowchart TD
    B[Authorization: Bearer token] --> S{Token strategy}
    S -->|JWT / Servlet| JD[JwtDecoder]
    S -->|JWT / WebFlux| RJD[ReactiveJwtDecoder]
    S -->|Opaque / Servlet| OI[OpaqueTokenIntrospector]
    S -->|Opaque / WebFlux| ROI[ReactiveOpaqueTokenIntrospector]
    JD --> JWT[Validated Jwt]
    RJD --> JWT
    OI --> P[OAuth2AuthenticatedPrincipal]
    ROI --> P
    JWT --> A[Authentication]
    P --> A
    A --> Z[Authorization]
~~~

**Do not swap implementations based solely on class names.** First identify the stack, token format, issuer contract, and validators/attributes the application depends on.

## 2. Default Auto-Configuration and Custom Beans

With Spring Boot, the Resource Server can create the required components from properties. For JWT, the minimal configuration is:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
~~~

For opaque tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/introspect
          client-id: resource-server
          client-secret: \${INTROSPECTION_CLIENT_SECRET}
~~~

When no custom bean is present, Boot/Security configures the default decoder or introspector alongside the Resource Server filter chain.

### 2.1. JWT: Default Decoder

For Servlet, the contract is **JwtDecoder**, and the default implementation is typically **NimbusJwtDecoder**.

For WebFlux, the contract is **ReactiveJwtDecoder**, and the default implementation is typically **NimbusReactiveJwtDecoder**.

Configuring **issuer-uri** lets the framework fetch Authorization Server metadata, resolve the JWKS URI, and validate the issuer. On the reactive stack, current documentation notes that discovery is deferred until the first JWT request via **SupplierReactiveJwtDecoder**, preventing startup from failing immediately if the Authorization Server is temporarily unavailable.

If you need to specify the JWKS URI directly while retaining issuer validation:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
          jwk-set-uri: https://idp.example.com/.well-known/jwks.json
~~~

**jwk-set-uri** skips metadata discovery. Keep **issuer-uri** so the `iss` claim continues to be validated.

### 2.2. Opaque: Default Introspector

For Servlet, the default implementation is **SpringOpaqueTokenIntrospector**.

For WebFlux, the default implementation is **SpringReactiveOpaqueTokenIntrospector**.

These implementations call the introspection endpoint using client credentials, verify the response contains **active: true**, and build a principal with authorities. By default, scopes are mapped to authorities prefixed with **SCOPE_**.

### 2.3. When Does a Custom Bean Replace the Default?

JWT example:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder.withIssuerLocation(issuer).build();
}
~~~

A custom **JwtDecoder** bean replaces the decoder Boot would otherwise create. In WebFlux, **ReactiveJwtDecoder** plays the same role.

Opaque token:

~~~java
@Bean
OpaqueTokenIntrospector introspector() {
    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Or reactive:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Declaring your own bean replaces the default implementation of the same type. When using the DSL, **decoder(...)** or **introspector(...)** can also override the corresponding auto-configuration.

Distinguish **overriding a property** from **replacing the entire implementation**:

| Configuration Approach | Scope |
|---|---|
| issuer-uri | Configures issuer and discovery |
| jwk-set-uri | Specifies JWKS source; retains issuer validation if issuer-uri is also set |
| jws-algorithms | Changes the algorithm allowlist |
| decoder(...) / JwtDecoder bean | Replaces the decoder implementation |
| introspection-uri() | Overrides the introspection endpoint |
| introspectionClientCredentials(...) | Overrides credentials for introspection |
| introspector(...) / introspector bean | Replaces the entire introspector implementation |

**Replacing a decoder or introspector changes security behavior.** Do not assume default validators, timeouts, authority mapping, and error handling remain active after replacing the bean.

## 3. JWT `typ` Change: From Nimbus Verifier to `JwtTypeValidator`

This change requires preparation when upgrading from Spring Security 6.5 to 7.0.

Previously, **NimbusJwtDecoder** relied on the Nimbus JOSE processor to verify the **typ** header. Spring Security 7 moves this responsibility to **JwtTypeValidator**, aligning it with how Spring Security validates other JWT claims.

### 3.1. Preparing in Spring Security 6.5

If the application already customized the Nimbus type verifier or wants to prepare in advance, disable Nimbus type verification and add the corresponding validator:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .validateTypes(false)
        .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithValidators(
            new JwtIssuerValidator(issuer),
            JwtTypeValidator.jwt()
        )
    );

    return decoder;
}
~~~

For standard JWT tokens, **JwtTypeValidator.jwt()** accepts `typ` equal to `JWT` or an absent `typ` header, matching the optional nature of that header in JOSE.

### 3.2. Configuration After Moving to Spring Security 7

In Spring Security 7, Nimbus **validateTypes** defaults to `false`, and **JwtValidators.createDefault...** factory methods already include **JwtTypeValidator.jwt()** in the default validator set.

Therefore, the standard configuration simplifies to:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Do not keep adding `JwtTypeValidator.jwt()` a second time once using version 7's default factories per the migration guide.

### 3.3. If the System Uses a Custom `typ`

Some token profiles use a type other than `JWT`, such as a dedicated JOSE profile. If the application previously configured **DefaultJOSEObjectTypeVerifier** inside **jwtProcessorCustomizer**, migrate that policy to **JwtTypeValidator** or a custom **OAuth2TokenValidator**.

Conceptual example:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .validateTypes(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(issuer),
        new JwtTypeValidator("JOSE")
    )
);
~~~

Permit only the types specified by your token profile and the migration docs for the active version. Do not allow a broader set of `typ` values just to let legacy tokens pass validation.

### 3.4. Avoid Dropping Type Validation When Configuring Validators Manually

A common mistake is:

~~~java
decoder.setJwtValidator(new JwtTimestampValidator());
~~~

This replaces the existing validator set with the single validator passed in. Setting only a timestamp validator can unintentionally drop issuer validation, type validation, and other policies.

When custom validators are needed, combine them with the defaults using **DelegatingOAuth2TokenValidator**:

~~~java
OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> audience = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        )
    );
};

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(defaults, audience)
);
~~~

This preserves the default checks while adding the audience policy.

## 4. Same `typ` Change in WebFlux

The reactive decoder uses a different contract from Servlet:

- Servlet: **JwtDecoder** and **NimbusJwtDecoder**.
- WebFlux: **ReactiveJwtDecoder** and **NimbusReactiveJwtDecoder**.

Preparation in 6.5:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
            .validateTypes(false)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithValidators(
            new JwtIssuerValidator(issuer),
            JwtTypeValidator.jwt()
        )
    );

    return decoder;
}
~~~

After upgrading to Spring Security 7:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

The same principles apply as in Servlet: keep default validators, add audience/tenant validators via composition, and never perform blocking network I/O on the Reactor event loop.

## 5. Opaque Introspection Client Credentials Changes

Spring Security 6.5 introduced builders for **SpringOpaqueTokenIntrospector** and **SpringReactiveOpaqueTokenIntrospector**. The builders automatically URL-encode the client ID and client secret before constructing HTTP Basic authorization for the introspection request.

This is a critical change for credentials containing characters unsafe in URL/form encoding.

### 5.1. Before the Change: Applications Encoded Credentials Manually

Some applications previously encoded the client ID/secret themselves before passing them to the legacy API or constructing **RestOperations** with Basic authentication.

If pre-encoded values are passed into the new builder, the framework can encode them a second time. The Authorization Server then receives credentials different from the registered ones and returns a client authentication error.

### 5.2. Recommended Approach in 6.5 and 7.x

Pass **raw, unencoded values** to the builder:

~~~java
@Bean
OpaqueTokenIntrospector introspector() {
    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(unencodedClientId)
        .clientSecret(unencodedClientSecret)
        .build();
}
~~~

Reactive:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(unencodedClientId)
        .clientSecret(unencodedClientSecret)
        .build();
}
~~~

Store client secrets in a secret manager or environment configuration. Never hard-code, log, or include secrets in exception messages.

### 5.3. Legacy Constructor Deprecated

The legacy constructor on **SpringReactiveOpaqueTokenIntrospector** accepting URL-encoded credentials was deprecated in 6.5 and marked for removal. Prefer the builder:

~~~java
SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(uri)
    .clientId(clientId)
    .clientSecret(clientSecret)
    .build();
~~~

Do not pre-encode values before calling **clientId(...)** or **clientSecret(...)**.

If using a custom `RestOperations`/`WebClient`, clearly establish where Basic authentication and encoding occur. Avoid encoding in application code while the builder also encodes a second time.

## 6. Opaque Token Implementations in Servlet: `SpringOpaqueTokenIntrospector` and `RestClientOpaqueTokenIntrospector`

On the Servlet stack, the traditional implementation is **SpringOpaqueTokenIntrospector**, which uses **RestOperations** to call the introspection endpoint.

Spring Security 7.1 adds **RestClientOpaqueTokenIntrospector**, backed by Spring Framework's **RestClient**.

Both classes implement **OpaqueTokenIntrospector**, but they use different HTTP client abstractions.

| Class | HTTP Client | When Appropriate |
|---|---|---|
| SpringOpaqueTokenIntrospector | RestOperations / RestTemplate | Existing apps using RestTemplate or wanting to keep current config |
| RestClientOpaqueTokenIntrospector | RestClient | Apps wanting Spring Framework's modern synchronous HTTP client |

**`RestClientOpaqueTokenIntrospector` is a new option in 7.1, not an automatic switch for all applications.** The default fallback in Resource Server documentation remains **SpringOpaqueTokenIntrospector** unless the application configures another implementation.

### 6.1. Using `RestClientOpaqueTokenIntrospector`

Basic builder example:

~~~java
@Bean
OpaqueTokenIntrospector introspector(
        String introspectionUri,
        String clientId,
        String clientSecret) {

    return RestClientOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

The builder accepts unencoded credentials and performs encoding per the implementation's contract.

### 6.2. Customizing `RestClient` and Timeouts

When custom request factories, timeouts, or interceptors are required, construct a **RestClient** and pass it to the constructor:

~~~java
@Bean
OpaqueTokenIntrospector introspector(
        String introspectionUri,
        String clientId,
        String clientSecret) {

    SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

    requestFactory.setConnectTimeout(Duration.ofSeconds(5));
    requestFactory.setReadTimeout(Duration.ofSeconds(5));

    RestClient restClient = RestClient.builder()
        .requestFactory(requestFactory)
        .defaultHeaders(headers ->
            headers.setBasicAuth(clientId, clientSecret)
        )
        .build();

    return new RestClientOpaqueTokenIntrospector(
        introspectionUri,
        restClient
    );
}
~~~

This illustrates a client managing Basic authentication directly. If you use the introspector's builder to manage credentials, do not also attach a second Basic `Authorization` header inside `RestClient`.

Choose timeouts based on your latency budget and availability policy. Introspection timeouts must never be treated as authentication success or a synthetic `active=true`.

### 6.3. When to Keep `SpringOpaqueTokenIntrospector`?

Keep the existing implementation if:

- The application already has `RestOperations` configured with appropriate connection pooling, proxy, TLS, and timeouts.
- There is no need to move to `RestClient`.
- Integration tests rely on the currently configured behavior.
- The upgrade does not require changing HTTP clients.

There is no need to swap implementations just because Spring Security 7.1 added a new class. Switch only when there is a concrete benefit and compatibility has been tested.

## 7. Opaque Token Implementations in WebFlux

WebFlux uses **ReactiveOpaqueTokenIntrospector**. The default implementation is **SpringReactiveOpaqueTokenIntrospector**, which uses `WebClient`/reactive HTTP to call the introspection endpoint.

Example:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Unlike Servlet, do not use **RestClientOpaqueTokenIntrospector** in a WebFlux Resource Server just because the class appeared in Spring Security 7.1. `RestClient` is a synchronous client; the reactive stack has its own reactive implementation.

### 7.1. Customizing Principal/Authorities via Delegation

If you need to customize scope, role, or attribute mapping, wrap the default introspector instead of rewriting the entire HTTP exchange:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    ReactiveOpaqueTokenIntrospector delegate =
        SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(introspectionUri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return token -> delegate.introspect(token)
        .map(principal -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(principal.getAuthorities());

            // Add mapping per the system's verified contract.
            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities
            );
        });
}
~~~

This snippet only illustrates decorating the principal; replace the mapping section with your specific policy. Never grant roles solely from an unverified attribute outside the issuer's contract.

### 7.2. Do Not Block Reactive Introspection

Never call `block()` inside **ReactiveOpaqueTokenIntrospector** or the WebFlux authentication path. Never use `RestTemplate` directly on the Reactor event loop. If a blocking library is unavoidable, offload it to an appropriate scheduler and bound concurrency; prefer the reactive `WebClient` implementation.

## 8. `NimbusJwtDecoder` Default Timeout Change

In Spring Security 7.0, **NimbusJwtDecoder** changed the default connect/read timeouts for the **RestOperations** used to fetch the JWK Set when the application does not supply its own `RestOperations`:

| Previous Version | Spring Security 7.0+ |
|---|---|
| 500 ms connect timeout | 30 seconds |
| 500 ms read timeout | 30 seconds |

This gives many deployments a more realistic window to fetch JWKS, but it can cause requests to wait longer when the Authorization Server is unresponsive.

This matters especially if the application previously relied on fast failures to trip a circuit breaker or fail fast.

### 8.1. Reviewing Timeouts During Migration

- Check JWKS fetch connect/read timeouts.
- Check overall ingress/API gateway timeouts.
- Check retries and circuit breakers.
- Check cold-start or first-key-fetch latency.
- Check behavior when the issuer/JWKS endpoint is unreachable.
- Never retry indefinitely on the request path.

This timeout change is documented specifically for **NimbusJwtDecoder** and **RestOperations**. Do not generalize that every reactive decoder or custom HTTP client shares the exact same defaults.

### 8.2. Configuring Dedicated `RestOperations` When Needed

If you want explicit timeout control, pass a custom **RestOperations** into the builder/decoder per your version's API:

~~~java
@Bean
JwtDecoder jwtDecoder(RestTemplateBuilder builder) {
    RestOperations restOperations = builder
        .connectTimeout(Duration.ofSeconds(2))
        .readTimeout(Duration.ofSeconds(2))
        .build();

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer)
            .restOperations(restOperations)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Verify the builder method against the exact Spring Security/Spring Framework release in use. The goal is to set timeouts aligned with your system's latency budget rather than implicitly relying on defaults that shift across versions.

## 9. `BearerTokenAuthenticationFilter` and Converter Changes

Spring Security 7 deprecates setters on **BearerTokenAuthenticationFilter**:

- **setBearerTokenResolver(...)**
- **setAuthenticationDetailsSource(...)**

Instead, configure both components on **BearerTokenAuthenticationConverter** and pass the converter into the filter.

Previously:

~~~java
BearerTokenAuthenticationFilter filter =
    new BearerTokenAuthenticationFilter(authenticationManager);

filter.setBearerTokenResolver(myBearerTokenResolver);
filter.setAuthenticationDetailsSource(myAuthenticationDetailsSource);
~~~

New approach:

~~~java
BearerTokenAuthenticationConverter converter =
    new BearerTokenAuthenticationConverter();

converter.setBearerTokenResolver(myBearerTokenResolver);
converter.setAuthenticationDetailsSource(
    myAuthenticationDetailsSource
);

BearerTokenAuthenticationFilter filter =
    new BearerTokenAuthenticationFilter(
        authenticationManager,
        converter
    );
~~~

For most applications, the **oauth2ResourceServer DSL** already handles standard use cases without manually instantiating the filter. This change mainly affects applications assembling **BearerTokenAuthenticationFilter** directly.

Do not alter token extraction behavior during migration without tests covering:

- Valid Bearer header.
- Missing header.
- Malformed header.
- Multiple token sources.
- Tokens in query/form parameters if supported by the application.
- Authentication details passed to the provider.

## 10. Default Algorithms and Validators Must Not Be Expanded Automatically

**NimbusJwtDecoder** and **NimbusReactiveJwtDecoder** trust only the **RS256** algorithm by default per current Resource Server documentation. If the issuer uses another algorithm, configure an explicit allowlist.

Servlet example:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Reactive:

~~~java
NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Multiple algorithms can be configured if the token issuer genuinely uses them. Never trust an algorithm solely because the JWT header declares `alg`; the allowlist must be server-configured.

In addition to signature and issuer, explicitly define validators for:

- `exp` and `nbf`.
- `aud`.
- Token type/profile.
- Client/resource binding.
- Required tenant and domain claims.
- Application-specific policies.

Never replace the default validator with a custom validator that checks only one claim and inadvertently drops the remaining checks.

## 11. Distinguishing Replacing the Decoder from Replacing `JwtAuthenticationConverter`

Some migrations confuse these two layers:

- **Decoder** verifies signature, issuer, timestamps, and claims.
- **Authentication converter** transforms the verified `Jwt` into an `Authentication`/`GrantedAuthority` set.

For example, custom scope mapping does not necessarily require a custom decoder. You can configure **JwtAuthenticationConverter** or **JwtGrantedAuthoritiesConverter** at the authority conversion stage.

If the decoder changes, test signature/issuer/audience/type/timestamps. If the converter changes, test principal/authority mapping.

Never use a custom converter to compensate for a decoder skipping validation. Never grant authorities from unverified claims.

## 12. Preserving Lazy Discovery and Startup Behavior

With **issuer-uri**, Spring Security can defer discovery until the first JWT request arrives. This lets the application start even when the Authorization Server is temporarily unavailable.

When declaring a custom decoder bean, verify whether the new construction triggers discovery earlier or repeatedly.

Options:

| Configuration | Behavior |
|---|---|
| issuer-uri only | Discovery resolves JWKS from metadata |
| issuer-uri + jwk-set-uri | Skips metadata discovery while still validating issuer |
| Custom decoder from withIssuerLocation | App controls decoder/validators; verify discovery timing |
| Custom decoder with static JWK source | App manages key source and rotation lifecycle |

Never call the metadata endpoint on every request. Reuse the decoder and key cache. If independence from the metadata endpoint at startup is required, configure a managed JWKS URI.

## 13. What Behavior Can Be Lost When Replacing Default Implementations?

Before replacing a decoder or introspector, document current behavior:

| Behavior | JWT Decoder | Opaque Introspector |
|---|---|---|
| Token verification | Signature, key, claims | Introspection active |
| Issuer | `iss` validator | Per AS/introspection contract and custom policy |
| Audience | Custom/default validators per config | Attributes/custom validation |
| Expiration | `exp`/`nbf` validators | AS returns active and claims |
| Authority mapping | Scope/scp converter | Scopes from introspection response |
| HTTP client | JWKS/discovery client | Introspection HTTP client |
| Timeout | JWKS fetch timeout | Introspection timeout |
| Key/credential rotation | JWKS cache/key refresh | Client secret/TLS/HTTP config |
| Error handling | `JwtException`/authentication failure | Introspection exception/authentication failure |

A custom implementation must preserve the required invariants. Never assume that implementing **JwtDecoder** or **OpaqueTokenIntrospector** causes Spring to automatically wrap it with all default validations.

## 14. Migration Process from 6.5 to 7.0/7.1

### Step 1 — Verify Dependency Alignment

Check the Spring Boot BOM/Spring Security BOM. Do not upgrade **spring-security-oauth2-resource-server** alone while **spring-security-core**, **oauth2-jose**, or **spring-security-test** remain on a different version.

For JWT, both **spring-security-oauth2-resource-server** and **spring-security-oauth2-jose** are required. Opaque-token introspection does not require the JOSE module just to call introspection.

### Step 2 — Locate Custom Decoders and Introspectors

Search the codebase for:

- `JwtDecoder`, `ReactiveJwtDecoder`.
- `NimbusJwtDecoder`, `NimbusReactiveJwtDecoder`.
- `OpaqueTokenIntrospector`, `ReactiveOpaqueTokenIntrospector`.
- `SpringOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`.
- `jwtProcessorCustomizer`, `setJwtValidator`.
- `introspectionClientCredentials`, `clientId`, `clientSecret`.
- `BearerTokenAuthenticationFilter` setters.

### Step 3 — Prepare `JwtTypeValidator` in 6.5

If customizing Nimbus type verification, migrate the policy to **JwtTypeValidator** or an equivalent custom **OAuth2TokenValidator**. Test valid, invalid, and missing `typ` values.

### Step 4 — Remove Manual Credential Encoding

Switch builder inputs to raw client ID/secret values. Verify the `Authorization` header sent to the introspection endpoint using a test server, especially for credentials containing special characters.

### Step 5 — Upgrade to Spring Security 7

Remove transitional `validateTypes(false)` if custom type config is no longer needed and use **JwtValidators.createDefaultWithIssuer(...)** for standard JWT profiles. Avoid duplicating the default `JwtTypeValidator`.

### Step 6 — Verify JWKS Timeouts

Measure the new 30-second behavior of `NimbusJwtDecoder`. If unsuitable, configure explicit `RestOperations` timeouts.

### Step 7 — Evaluate `RestClientOpaqueTokenIntrospector`

If a Servlet application wants to migrate from `RestTemplate`/`RestOperations` to `RestClient`, evaluate Spring Security 7.1's **RestClientOpaqueTokenIntrospector**. There is no need to switch if the current implementation already meets requirements.

### Step 8 — Update Custom Filter Assembly

If instantiating `BearerTokenAuthenticationFilter` manually, move the resolver/details source onto `BearerTokenAuthenticationConverter`. If using the DSL, check deprecation compiler warnings and keep the DSL if it fits the use case.

### Step 9 — Run Integration Tests

Test token signatures, issuer, audience, type, expiration, introspection credentials, timeouts, authority mapping, and error behavior. Do not rely on compilation alone.

### Step 10 — Roll Out and Observe

Monitor:

- Unexpected spikes in 401 responses.
- Introspection client authentication failures.
- JWKS fetch latency/timeouts.
- Decoder initialization.
- Unknown `typ`/signature errors.
- Scope/authority mapping changes.
- Startup/readiness behavior.

## 15. Required Test Suite After Migration

### 15.1. JWT Decoder

| Test | Expected Result |
|---|---|
| Valid signature, valid issuer, unexpired `exp` | Accept |
| Invalid signature | Reject |
| Invalid issuer | Reject |
| Invalid audience | Reject |
| Expired token | Reject |
| `nbf` in the future | Reject |
| `typ` is JWT | Per standard profile, accept |
| `typ` absent | Per default JWT validator, accept |
| Wrong profile `typ` | Reject |
| Algorithm outside allowlist | Reject |

Use signed test tokens and a test key/JWKS server to test the real decoder. The **jwt()** test helper injects only a mock `Authentication` and does not exercise the decoder.

### 15.2. Opaque Introspector

- `active=true` produces a principal.
- `active=false` is rejected.
- Client ID/secret with special characters are transmitted properly.
- Credentials are not double-encoded.
- Introspection 401/403 responses are handled appropriately.
- Timeouts/5xx do not fail open.
- Scopes map properly.
- Attributes/principal mapping preserves the contract.

Use an HTTP stub/test server to verify actual requests sent to the introspection endpoint.

### 15.3. Timeouts and Startup

- Fast JWKS endpoint.
- JWKS endpoint slower than 500 ms but below the new timeout.
- JWKS endpoint exceeding the timeout.
- Authorization Server unavailable at startup.
- First request triggering discovery.
- Key rotation and unknown `kid`.
- Introspection latency and cancellation in WebFlux.

### 15.4. Servlet and WebFlux

Run separate tests for both stacks. Never use Servlet **JwtDecoder** in WebFlux or **ReactiveJwtDecoder** in Servlet just because the interface names look similar.

In WebFlux, verify no `block()` calls exist in the decoder/introspector pipeline and that `SecurityContext` still propagates through the Reactor Context.

## 16. Common Anti-Patterns

**Passing already-encoded credentials into the new builder.** The framework can encode them again, causing Basic authentication to fail.

**Creating `NimbusJwtDecoder` manually while forgetting default validators.** Can drop issuer, timestamp, or type validation.

**Calling `setJwtValidator` with a single standalone validator.** Replaces the entire previous validator chain.

**Treating `JwtTypeValidator` as a purely syntactic change.** It is part of token profile validation.

**Expanding allowed algorithms dynamically from the JWT header.** Trusts algorithms outside the allowed trust policy.

**Replacing `SpringOpaqueTokenIntrospector` solely because 7.1 added a `RestClient` implementation.** Offers no benefit if the current HTTP client and behavior already fit.

**Using `RestClientOpaqueTokenIntrospector` inside WebFlux.** Pick the implementation matching the Servlet or reactive stack.

**Instantiating a new introspector per request.** Wastes HTTP client/configuration resources and defeats caching/pooling.

**Blocking inside `ReactiveOpaqueTokenIntrospector`.** Can stall the Reactor event loop.

**Failing to review timeouts after upgrading.** 30 seconds may exceed gateway/request deadlines.

**Rewriting the entire introspection HTTP flow just to customize authority mapping.** Risks losing default error handling and credential handling; prefer a delegate/decorator.

**Using a custom decoder to handle role mapping.** Authority conversion belongs in an appropriate authentication converter.

**Assuming Boot still uses the default decoder after a custom bean is declared.** A bean of the same type replaces auto-configuration.

**Testing only compilation after migration.** Encoding, type validation, and timeout changes usually surface only when calling a real or test Authorization Server.

## 17. Quick Reference Table by Version

| Component | Spring Security 6.5 | Spring Security 7.0 | Spring Security 7.1 |
|---|---|---|---|
| JWT `typ` | Preparing to move to `JwtTypeValidator` | `validateTypes` defaults to `false`; default validators add `JwtTypeValidator.jwt()` | Preserves 7.0 behavior |
| Opaque credentials | Builder encodes client ID/secret; pass raw values | Opaque support encodes credentials; do not pre-encode | Preserves behavior |
| SpringOpaqueTokenIntrospector | Builder recommended; legacy constructor may be deprecated | Remains default fallback | Still usable |
| SpringReactiveOpaqueTokenIntrospector | Builder recommended | Remains reactive default | Adds builder `postProcessor` |
| RestClientOpaqueTokenIntrospector | Not available | Not available | Added in 7.1, Servlet stack |
| NimbusJwtDecoder JWKS timeout | Legacy 500 ms default | 30-second default | Preserves 7.0 behavior |
| BearerTokenAuthenticationFilter setters | Still usable | Deprecated, move to converter | Use converter |

This table focuses on changes directly affecting decoders/introspectors and the Bearer filter. Always check the release notes and migration guide for the exact minor version your project is targeting.

## 18. Self-Check Questions

**1. Which contract does Servlet JWT use?**

`JwtDecoder`, typically implemented by `NimbusJwtDecoder`.

**2. Which contract does WebFlux JWT use?**

`ReactiveJwtDecoder`, typically implemented by `NimbusReactiveJwtDecoder`.

**3. Which introspectors do Servlet and WebFlux opaque tokens use?**

Servlet uses `OpaqueTokenIntrospector`; WebFlux uses `ReactiveOpaqueTokenIntrospector`.

**4. How does Spring Security 7 change `typ` validation?**

It moves type validation to `JwtTypeValidator`; default validator factories include `JwtTypeValidator.jwt()`.

**5. Should you URL-encode the client ID/secret before calling the introspector builder?**

No. Pass raw unencoded values and let the builder handle encoding.

**6. Which version introduced `RestClientOpaqueTokenIntrospector`?**

Spring Security 7.1, for the Servlet stack and Spring `RestClient`.

**7. Does `RestClientOpaqueTokenIntrospector` replace `SpringReactiveOpaqueTokenIntrospector`?**

No. WebFlux continues using the reactive introspector.

**8. How did the `NimbusJwtDecoder` default JWKS timeout change in 7.0?**

From 500 ms to 30 seconds for the default connect/read timeout of the JWKS `RestOperations`.

**9. Why use `DelegatingOAuth2TokenValidator`?**

To retain the default validators while adding audience or custom policies.

**10. Does declaring a `JwtDecoder` bean affect auto-configuration?**

Yes. A custom bean replaces the decoder Boot would otherwise auto-configure.

**11. When should `SpringOpaqueTokenIntrospector` be replaced with `RestClientOpaqueTokenIntrospector`?**

When a Servlet application needs `RestClient` or matching request factory/HTTP client customization; it is not mandatory merely because of a version upgrade.

**12. Why test against a real or stub introspection server?**

To verify credentials, URL encoding, HTTP requests, timeouts, active responses, and authority mapping; mock `Authentication` does not exercise these parts.

## Conclusion

Decoder and introspector migration should be treated as a migration of **authentication behavior**, not merely renaming classes or silencing deprecation warnings.

When upgrading from 6.5 to 7.x, address **JwtTypeValidator**, pass opaque client credentials unencoded, review the new JWKS timeout, and move custom Bearer filter settings onto **BearerTokenAuthenticationConverter**. On the Servlet stack, **RestClientOpaqueTokenIntrospector** is a new option in 7.1, while **SpringOpaqueTokenIntrospector** remains valid. In WebFlux, keep **ReactiveJwtDecoder** and **SpringReactiveOpaqueTokenIntrospector** respectively, and never introduce synchronous clients into the reactive path.

Before replacing a default implementation, identify which bean Boot creates, which validators run, how authorities map, which timeouts the HTTP client uses, and how errors are handled. **A safe migration preserves issuer, audience, timestamp, type, signature, introspection, and authority policies; every intentional change must be verified with integration tests using signed JWTs or a test introspection endpoint.**

### References

- [Spring Security 6.5 to 7.0 — OAuth 2.0 Migration Guide](https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html)
- [Spring Security 7.0 — OAuth 2.0 Migrations](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/oauth2.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security API — SpringOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Security API — RestClientOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/RestClientOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security — What’s New in 7.1](https://docs.spring.io/spring-security/reference/whats-new.html)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
