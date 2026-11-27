# Updating Java DSL, Deprecated APIs, and Public Extension Points

Spring Authorization Server and Spring Security evolve with each release. During an upgrade, security configuration may need to move from legacy adapters to `SecurityFilterChain` beans, from `.and()` chaining to the lambda DSL, or from deprecated APIs to new public extension points. If you only fix compilation errors, the system can still alter filter ordering, matcher scope, consent handling, or token issuance behavior.

This lesson explains how to read API changes, reorganize the Java DSL, choose the right public SPIs, and verify OAuth 2.0/OpenID Connect behavior after upgrading. The examples use the modern configuration style of Spring Security and Spring Authorization Server. Exact method names and compatibility depend on the version in use; consult the Javadoc and migration notes for your exact target version before applying them.

## Objectives

After this lesson, you will be able to:

- Identify common legacy configurations and determine the corresponding migration path.
- Organize multiple `SecurityFilterChain` beans with clear matchers and ordering.
- Write Java DSL using lambdas and configure `OAuth2AuthorizationServerConfigurer` according to the target version's API.
- Distinguish configuration APIs from public extension points for storage, authentication, tokens, and keys.
- Replace customizations based on internal classes with supported interfaces or customizers.
- Upgrade incrementally and test authorization code, PKCE, client authentication, refresh token, and OIDC flows.

## 1. Start by Identifying Versions

Before modifying code, record the versions of Java, Spring Boot, Spring Framework, Spring Security, and Spring Authorization Server. These components have compatibility relationships; upgrading one library alone can introduce an API not yet supported by the others.

For Spring Boot projects, prefer using dependency management or the BOM managed by the Boot version. Only override Spring Security or Spring Authorization Server versions after verifying the compatibility matrix and documenting a clear reason. Avoid declaring multiple different versions of `spring-security-*` modules in the same application.

List existing configurations and extension points before making changes:

| Area | Items to Inventory |
|---|---|
| Security configuration | `WebSecurityConfigurerAdapter`, `SecurityFilterChain` beans, chain order, and matchers |
| Authorization Server | `OAuth2AuthorizationServerConfigurer`, endpoint matcher, OIDC, and custom endpoints |
| Client and consent | `RegisteredClientRepository`, `OAuth2AuthorizationConsentService` |
| Authorization | `OAuth2AuthorizationService`, token storage and revocation policies |
| Token | `OAuth2TokenGenerator`, `OAuth2TokenCustomizer`, custom converters and providers |
| Keys | `JWKSource`, `JwtEncoder`, keystore or KMS/HSM |
| Integration | Resource Server, login, CORS, CSRF, method security, and custom filters |

Record the current behavior of each flow: called endpoints, client authentication methods, grant types, scopes, token formats, consent, token lifetimes, and revocation behavior. This serves as the baseline for comparing before and after the upgrade.

## 2. Common Java DSL Changes

The changes below represent common migration paths as applications move from legacy Spring Security configuration to bean-based configuration and the lambda DSL. Not every old method is removed in the same version. Check `@Deprecated` annotations, the version marked deprecated, and the planned removal version in the Javadoc of the library you are using.

| Legacy Configuration Style | Migration Path | Reason |
|---|---|---|
| `WebSecurityConfigurerAdapter` | Declare `SecurityFilterChain` beans and `WebSecurityCustomizer` only when truly needed | Each chain can be configured and tested independently |
| `authorizeRequests()` | `authorizeHttpRequests(...)` | Modern request authorization API supporting lambda DSL |
| `antMatchers(...)`, `mvcMatchers(...)` | `requestMatchers(...)` with appropriate matchers | Matcher APIs unified across Spring Security versions |
| Chaining `.and()` across configurers | Nested lambda configuration | Reduces reliance on return types and clarifies configuration scope |
| `http.apply(configurer)` in versions where deprecated | `http.with(configurer, customizer)` if supported by target version | New API style for applying configurers |
| Configuring Authorization Server via default helpers | Explicitly configure `OAuth2AuthorizationServerConfigurer` when endpoint control is needed | Shows matchers, OIDC, and customization points in one place |
| Relying on internal implementations | Use public interfaces, converters, providers, and customizers | Reduces coupling to implementation details that may change |

### 2.1. Moving from Adapter to `SecurityFilterChain`

In legacy configuration, a class typically extended `WebSecurityConfigurerAdapter` and overrode configuration methods. With bean-based configuration, declare `SecurityFilterChain` directly:

```java
@Configuration
@EnableWebSecurity
public class ApplicationSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/health/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

`SecurityFilterChain` represents a set of filters along with its matching condition. When multiple chains exist, a chain is selected by order and matcher. A request passes through only the first matching chain; therefore, order and matcher scope are part of your security logic.

`WebSecurityCustomizer` should only be used when you need to bypass Spring Security completely for genuinely appropriate static requests. For most endpoints, use `permitAll()` inside `authorizeHttpRequests` so requests still pass through necessary security filters.

### 2.2. Moving to the Lambda DSL

Example of legacy chained configuration:

```java
http
    .authorizeRequests()
        .antMatchers("/assets/**").permitAll()
        .anyRequest().authenticated()
    .and()
    .formLogin();
```

Rewritten using the lambda DSL:

```java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/assets/**").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults());
```

The lambda DSL makes clear which configurer each configuration belongs to. There is no need to call `.and()` to return to the `HttpSecurity` object. When migrating a long configuration, migrate one functional group at a time and preserve authorization rule order; catch-all rules such as `anyRequest()` must come after specific rules.

### 2.3. Choosing Accurate Request Matchers

Do not replace every `antMatchers` call with `requestMatchers` without reviewing semantics. Matchers can be based on path, HTTP method, servlet path, or request type. Check:

- Whether paths have a context path or separate servlet path.
- Whether rules restrict HTTP methods or apply to all methods.
- Whether internal endpoints get matched earlier by a broad matcher.
- Whether there are differences involving trailing slashes, path variables, and wildcards.
- Whether `FORWARD`, `ERROR`, or `ASYNC` dispatch requests require separate policies.

For complex requirements, create explicit matchers, give variables meaningful names, and write tests for both allowed and denied cases. Do not conclude two matchers behave identically merely because their syntax looks similar.

## 3. Configuring Authorization Server with Public Configurers

The Authorization Server usually has its own chain for protocol endpoints. Explicit configuration lets the application control the endpoint matcher and enable OIDC in the right place.

Example for Spring Authorization Server versions providing the `OAuth2AuthorizationServerConfigurer.authorizationServer()` factory and Spring Security supporting `HttpSecurity.with(...)`:

```java
@Configuration
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer
                    .oidc(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a configuration pattern for APIs present in the target version. In older versions, constructors, generic types, or how configurers are attached may differ; do not copy a template verbatim into an unsupported version. Use the Javadoc of the artifact being built to verify exact signatures.

Key points to note:

- `getEndpointsMatcher()` aggregates endpoints managed by the Authorization Server. Use this matcher so the protocol chain does not accidentally apply to the entire application.
- `@Order(1)` ensures the Authorization Server chain is evaluated before the application chain. If the order is reversed, the application chain may intercept requests first.
- The application chain must have appropriate matchers or rules for the remaining requests.
- Enable OIDC with `oidc(...)` when the system needs OpenID Connect features; do not enable it simply because the application uses OAuth 2.0.
- Each `HttpSecurity` instance can only be built into one `SecurityFilterChain`. Do not reuse the same already-built object across multiple beans.

### 3.1. Customizing Endpoints and Consent

Sub-configurers are the public configuration points for each endpoint group. For example, the consent page can be redirected to an application-managed UI. The following snippet replaces the `.with(...)` callback body in the previous configuration example; do not call `.with(...)` a second time for the same configurer:

```java
http.with(authorizationServerConfigurer, authorizationServer ->
    authorizationServer
        .authorizationEndpoint(authorizationEndpoint ->
            authorizationEndpoint.consentPage("/oauth2/consent")
        )
        .oidc(Customizer.withDefaults())
);
```

The consent page must display the client, scopes, and permission details to approve using data authenticated by the server. When submitting the consent decision, the browser must return to the endpoint designed for the authorization flow and preserve the protocol parameters. Do not build a custom consent submission endpoint that bypasses state, client, or authorization request validation.

Depending on version and needs, the configurer also exposes areas such as client authentication, token endpoint, authorization endpoint, device authorization, device verification, token introspection, token revocation, and OIDC endpoints. Only configure features the application actually uses; check method signatures in Javadoc as sub-APIs can change across releases.

### 3.2. Configuring Issuer and Endpoints with `AuthorizationServerSettings`

In versions that have moved to `AuthorizationServerSettings`, use this bean to define the issuer and endpoint paths. Example:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
}
```

If endpoint paths need to be changed, the builder provides corresponding properties per version, such as authorization endpoint, token endpoint, JWK Set endpoint, introspection, and revocation. Do not change the issuer arbitrarily across environments: the issuer is the identifier embedded in metadata and tokens, and is used by resource servers to verify the issuing source.

When migrating from older configurations such as `ProviderSettings`, check the version where that API was marked deprecated and use `AuthorizationServerSettings` if provided by the target version. Verify discovery metadata, the issuer in tokens, and endpoint URLs after upgrading.

## 4. Distinguishing Configuration from Public Extension Points

The Java DSL determines how security components are assembled. Public extension points determine where the application alters business behavior. Choose the right kind of extension point instead of replacing internal filters or providers unnecessarily.

| Need | Extension Point to Consider |
|---|---|
| Store registered clients | `RegisteredClientRepository` |
| Store authorizations and issued tokens | `OAuth2AuthorizationService` |
| Store consent decisions | `OAuth2AuthorizationConsentService` |
| Customize JWT claims | `OAuth2TokenCustomizer<JwtEncodingContext>` |
| Customize opaque access token claims | `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>` |
| Generate tokens | `OAuth2TokenGenerator` and supported generators |
| Authenticate requests at endpoints | `AuthenticationConverter` and `AuthenticationProvider` |
| Provide signing keys and JWKS | `JWKSource<SecurityContext>` or appropriate signer integration |
| Configure issuer and endpoints | `AuthorizationServerSettings` |
| Customize endpoints | Public configurer for the corresponding endpoint |

These interfaces have distinct contracts and responsibilities. For example, the repository storing client data does not replace the authorization storage service; a customizer altering claims does not replace request authentication; and an `AuthenticationProvider` should not rewrite the entire filter chain.

### 4.1. Storing Clients, Authorizations, and Consents

The three key storage abstractions have separate roles:

- `RegisteredClientRepository` finds and saves client configurations such as client ID, authentication methods, grant types, redirect URIs, scopes, and token lifetimes.
- `OAuth2AuthorizationService` stores authorization state along with tokens and related metadata, supporting lookup by ID or token.
- `OAuth2AuthorizationConsentService` stores scopes that a resource owner has approved for a client.

When moving from in-memory to JDBC or a custom data store, preserve the semantics of `save`, `remove`, lookup methods, and revoked token handling. For authorization data, do not store only the token string: preserve status, issued/expiration timestamps, metadata, and information needed for introspection or revocation.

If implementing a custom repository or service, use the public interfaces and test not-found cases, concurrent updates, revocation, expiration, and application restarts. Do not subclass JDBC implementation classes just to override an internal method if the public API does not promise support for doing so.

### 4.2. Customizing JWTs with `OAuth2TokenCustomizer`

When you need to add claims to a JWT, use `OAuth2TokenCustomizer<JwtEncodingContext>`:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            context.getClaims().claim("application", "rental-api");
        }
    };
}
```

This example adds only a static claim to illustrate the customization point. In real applications, only add data that has been verified and is needed by token consumers. Do not put passwords, client secrets, refresh tokens, unnecessary personal data, or sensitive internal information into JWTs because tokens may be read by multiple components.

Check `context.getTokenType()` before adding claims to avoid accidentally applying the same data to both ID tokens and access tokens. If claims depend on the client or principal, clearly identify the data source, access permissions, and impact when data changes.

For opaque/reference access tokens, the appropriate customizer is `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>` when supported by the generator and version in use. Do not use a JWT customizer expecting it to modify opaque token contents.

### 4.3. Changing the Token Generator

`OAuth2TokenGenerator` is the abstraction for generating access tokens, refresh tokens, or JWT-formatted tokens depending on configuration. When you need to change token generation, identify the token type and appropriate generator before writing a custom generator.

Common structure example in an application issuing JWTs:

```java
JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
jwtGenerator.setJwtCustomizer(jwtTokenCustomizer);

OAuth2AccessTokenGenerator accessTokenGenerator =
    new OAuth2AccessTokenGenerator();

OAuth2TokenGenerator<?> tokenGenerator =
    new DelegatingOAuth2TokenGenerator(
        jwtGenerator,
        accessTokenGenerator,
        new OAuth2RefreshTokenGenerator()
    );
```

This snippet illustrates how generators are combined, not a complete configuration for every system. You must supply a `JwtEncoder` backed by an appropriate key source, configure an opaque access token customizer if used, and ensure the generator is wired into the configurer or bean according to the target version's mechanism. Do not add or remove generators without checking current token formats, grant types, and refresh token policies.

### 4.4. Adding a Custom Grant Type

When a business protocol requires a custom grant type, the primary integration points are a converter and provider on the token endpoint:

1. `AuthenticationConverter` reads the HTTP request, validates parameter structure, and converts it into a dedicated `Authentication` type for that grant.
2. `AuthenticationProvider` checks the client, principal, authorization conditions, and input data; it rejects invalid requests with the appropriate OAuth error.
3. The provider uses public services such as `OAuth2AuthorizationService` and `OAuth2TokenGenerator` to save the authorization and generate tokens.
4. Register the converter and provider with the token endpoint configurer according to the API of the version in use.

Configuration shape example:

```java
authorizationServerConfigurer.tokenEndpoint(tokenEndpoint ->
    tokenEndpoint
        .accessTokenRequestConverter(customGrantAuthenticationConverter)
        .authenticationProvider(customGrantAuthenticationProvider)
);
```

This is the registration point; `customGrantAuthenticationConverter` and `customGrantAuthenticationProvider` must be implemented with a dedicated `Authentication` type, thoroughly verify client permissions, and handle errors per the protocol. Do not accept a grant type simply because a client sends the grant name in the request. The grant must be allowed in the client configuration and have explicit authentication, anti-replay, lifetime, and revocation policies.

If the requirement can be met with a standard grant type such as authorization code with PKCE or client credentials, prefer the standard protocol to maintain compatibility and reduce security burden.

### 4.5. Customizing Client Authentication

For additional client authentication methods, consider `AuthenticationConverter` and `AuthenticationProvider` on the client authentication configurer. The converter parses authentication credentials from the request; the provider verifies the client and credentials according to the registered method. Do not read client secrets manually in a separate filter and bypass the Authorization Server's storage, comparison, and error-handling rules.

When supporting multiple methods, verify whether `RegisteredClient` declares the proper `ClientAuthenticationMethod`. Test cases where the client uses an allowed method, a disallowed method, wrong credentials, a non-existent client, and requests containing multiple credential mechanisms simultaneously.

## 5. Extending Endpoints with Supported APIs

Each endpoint has its own group of extension points. Place customizations near the endpoint that owns them so maintainers clearly see the scope of impact.

| Endpoint | Common Need | Extension Path |
|---|---|---|
| Authorization | Redirect consent page, add converter or provider | Authorization endpoint configurer |
| Token | Add grant, process token request, or customize response | Token endpoint configurer, converter, provider, generator |
| Client authentication | Add client authentication method | Client authentication configurer |
| Introspection | Customize reference token checks | Introspection endpoint configurer and authorization storage service |
| Revocation | Adjust revocation handling | Revocation endpoint configurer and authorization storage service |
| Device authorization/verification | Adjust UI or device flow handling | Device endpoint configurer |
| OIDC UserInfo | Map user claims permitted for disclosure | OIDC UserInfo endpoint configurer and public mapper |
| JWKS | Publish public keys | `JWKSource` and key configuration |

Avoid inserting a filter before or after an internal Authorization Server filter if a configurer or SPI already meets the need. Internal filter positions can change across versions, leading to subtle bugs such as requests being authenticated twice, CSRF checks being skipped, or endpoints failing to return properly formatted OAuth errors.

If a custom application-level filter is strictly required, identify the target chain, its position relative to standard filters, exception handling, and matcher. Write tests proving the filter does not accidentally interfere with protocol endpoints.

## 6. Key Management and JWT Integration

The key source is an important extension point, but it should not be mixed with claim customization logic. `JWKSource<SecurityContext>` supplies appropriate keys to JWT components; `JwtEncoder` uses keys for signing. Depending on infrastructure, keys can come from a keystore, secret manager, KMS, or HSM.

When upgrading key configuration:

- Keep the issuer and algorithms supported by consumers unchanged, unless a protocol change is planned.
- Ensure `kid` is unique within the JWKS and the corresponding public key is published.
- Never package private keys or keystore passwords into source control or container images.
- Verify workload identity read/sign permissions against KMS/HSM.
- During rotation, publish the new public key before using it to sign; retain the old key while previously issued tokens still need verification.
- Test startup, key reload, and failure handling when the key source is temporarily unavailable.

Do not replace `JWKSource` by accessing internal fields or classes of the encoder. If you must use an HSM that does not expose private keys as JWKs, design a signer integration using public APIs compatible with the chosen JWT library and verify signatures with the public key.

## 7. Common Upgrade Failures

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Token endpoint returns 404 or is blocked by application chain | Incorrect matcher or `SecurityFilterChain` order | Inspect `getEndpointsMatcher()`, `@Order`, and matchers of remaining chains |
| Protocol endpoint unexpectedly requires form login | Application chain intercepts request first or Authorization Server chain has wrong scope | Enable appropriate security logging in a test environment and confirm which chain was selected |
| Compile error reports deprecated or missing method | Target version changed or removed API | Read Javadoc and release notes for the exact version; inspect dependency tree |
| Scopes or consent behave differently after upgrade | Repository or consent service behavior changed | Compare consent records and authorization requests before/after |
| JWT missing claims | Customizer not wired to generator properly or token type condition mismatch | Check beans, generator, and JWT payload in tests |
| JWT fails verification after config change | Issuer, algorithm, `kid`, or JWKS changed | Compare discovery metadata, JWKS, and JWT headers |
| Refresh token stops working | Grant type, lifetime, reuse/rotation, or authorization storage changed | Check client settings, token generator, and authorization state |
| Custom grant not recognized | Converter not registered or provider does not support authentication token | Check converter/provider order and `supports` condition |
| Custom integration breaks after upgrade | Coupled to internal implementation or filter order | Migrate to public SPIs and test integration contracts |

Do not work around errors by lowering protections, permitting all requests, or temporarily disabling authentication in production. Reproduce the error with tests or in staging and pinpoint the exact chain, matcher, or extension point causing the issue.

## 8. Controlled Upgrade Process

A practical process can be broken into the following steps:

1. **Lock in target versions.** Confirm compatible Java, Spring Boot, Spring Security, and Spring Authorization Server versions; record the dependency tree.
2. **Establish a baseline.** Run existing tests and capture behavior of OAuth/OIDC flows, metadata, JWKS, and tokens.
3. **List APIs to replace.** Find legacy adapters, deprecated methods, old matchers, custom configurers, and imports from implementation packages.
4. **Migrate Java DSL.** Move configuration to `SecurityFilterChain`, lambda DSL, and explicit matchers; preserve rule order and chain order.
5. **Migrate Authorization Server configurer.** Use the target version's configurer API; verify endpoint matchers, OIDC, and sub-configurations.
6. **Move extension points.** Migrate storage to public repositories/services, customize tokens with customizers, and integrate grants/authentication via converters/providers.
7. **Run regression tests.** Execute functional and security tests for every grant, endpoint, consent, token, key, and error case.
8. **Canary deploy and observe.** Compare error rates, latency, issued token counts, verification failures, and authorization data between old and new builds.
9. **Deploy with a rollback plan.** Maintain the ability to revert to compatible application versions and data during the transition window; never roll back by restoring lost data or reviving revoked tokens.

Upgrading in focused groups of changes speeds up root-cause analysis. If you change the DSL, repositories, generators, and keys all at once, a token issuance failure can stem from multiple areas and become hard to isolate.

## 9. Testing After the Update

Do not treat a successful build as proof the upgrade is complete. You must verify protocol behavior and security policies.

| Scenario | What to Confirm |
|---|---|
| Discovery metadata | Issuer, endpoints, and capabilities are published accurately |
| JWKS | Public keys have the right `kid` and verify token signatures |
| Authorization Code | Redirect URI, state, code exchange, and client authentication work properly |
| PKCE | Valid `code_verifier` is accepted; wrong or missing verifier is rejected per policy |
| Consent | Scopes are displayed, approved, and denied accurately; saved consent is read back |
| Client Credentials | Only permitted clients receive tokens with granted scopes |
| Refresh Token | Permitted client and grant; expired, revoked, or invalid tokens are rejected |
| Introspection/Revocation | Active/inactive token status accurately reflects storage and revocation state |
| OIDC | ID token, UserInfo, and logout work properly if enabled |
| Negative cases | Wrong client secret, wrong redirect URI, unauthorized scopes, and unsupported grants are all rejected |
| Multi-chain security | Requests are handled by the right chain without bypassing authentication |

With MockMvc, tests should send real requests through the filter chain to verify matchers, CSRF, and filter order. Isolated service tests remain useful for repositories, customizers, and providers, but they do not replace endpoint integration tests.

Also check Java and Jakarta changes when upgrading from older Spring generations to newer Spring Boot generations. If the application moves from `javax.*` to `jakarta.*`, update imports, dependencies, and integration libraries accordingly; do not do blind text replacements without verifying library contracts.

## 10. Principles for Sustainable Integration

- Prefer documented APIs and public SPIs. A class in an `internal` or `impl` package or with restricted visibility is usually not a stable extension contract.
- Keep business logic in application services; use converters/providers to bridge the protocol to those services.
- Use customizers for claim or metadata changes within supported boundaries; do not mutate internal objects after tokens have been issued.
- Avoid depending on internal filter order if the framework provides a configurer for the same need.
- Keep matchers, chain order, and authorization rules concise, with tests demonstrating which requests are allowed.
- Document the minimum API version required by custom extensions.
- When upgrading libraries, address deprecations release by release and remove legacy adapters once tests prove equivalent behavior.

## Conclusion

Upgrading the Authorization Server Java DSL and APIs requires preserving security behavior at every endpoint. `SecurityFilterChain`, the lambda DSL, and `OAuth2AuthorizationServerConfigurer` make configuration clearer; SPIs such as repositories, authorization services, token customizers, generators, converters, and providers create stable extension boundaries. By locking in compatible versions, migrating APIs group by group, testing all OAuth/OIDC flows, and monitoring after deployment, the application reduces reliance on legacy APIs while maintaining exact token issuance and validation policies.
