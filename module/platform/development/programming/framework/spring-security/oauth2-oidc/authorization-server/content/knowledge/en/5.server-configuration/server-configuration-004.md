# Configuration via Java DSL and Spring Boot Properties

## 1. Objectives and Scope

When implementing an **OAuth 2.0/OpenID Connect Authorization Server** with **Spring Security** and **Spring Authorization Server** in a **Spring Boot** application, two configuration styles frequently appear side by side:

- **Java DSL**: describes how HTTP requests are protected, attaches OAuth 2.0/OIDC protocol filters, defines security filter chains, enables OIDC, and extends Authorization Server behavior.
- **Spring Boot properties** in <code>application.yml</code>/<code>application.properties</code>: supply environment-specific configuration values, such as HTTP port, registered client information, and certain settings supported by Spring Boot auto-configuration.

The two approaches serve different parts of the system. Understanding this boundary prevents common errors: declaring a client yet the token endpoint does not work, enabling OAuth filters without a client repository, changing the issuer while metadata becomes inconsistent, or creating manual beans that cause YAML configuration to stop taking effect as intended.

After this lesson, you will be able to:

1. Choose the right place to configure filter chains, OAuth/OIDC endpoints, registered clients, token services, signing keys, and issuer.
2. Read a Spring Boot configuration and recognize which properties actually belong to the Authorization Server.
3. Assemble a working **Java DSL + Boot properties** example with an Authorization Code/OIDC flow.
4. Replace in-memory demo configurations with persistent storage components and production key management.
5. Test configuration after changing profiles, public URLs, clients, or framework versions.

**Running example:** An Authorization Server is published at <code>https://auth.example.com</code>; the web application <code>portal-web</code> uses Authorization Code for OIDC login and requests the <code>orders.read</code> scope when calling the Orders API. The illustrations follow the API conventions of **Spring Boot 3.x and Spring Authorization Server versions compatible with <code>HttpSecurity.with(...)</code>**. Properties and methods may change across versions; when upgrading, verify against the documentation and configuration metadata of the exact running version.

## 2. Responsibility Map of Configuration Layers

~~~mermaid
flowchart TB
    ENV["application.yml / environment / secret manager"]
    BOOT["Spring Boot property binding and auto-configuration"]
    JAVA["Java @Configuration / SecurityFilterChain / DSL"]
    AS["Spring Authorization Server filters and services"]
    DATA["RegisteredClientRepository / AuthorizationService / ConsentService"]
    KEY["JWKSource / JwtDecoder / AuthorizationServerSettings"]
    WEB["HTTP requests to OAuth 2.0 / OIDC endpoints"]
    ENV --> BOOT
    BOOT --> JAVA
    BOOT --> DATA
    JAVA --> AS
    DATA --> AS
    KEY --> AS
    WEB --> AS
~~~

The diagram depicts **configuration relationships**; it does not mean every bean is automatically created by Spring Boot from YAML. In many projects, the development team must explicitly define signing keys, data stores, and appropriate security policies.

| Need | Where to configure | Notes |
| --- | --- | --- |
| Select URLs belonging to the Authorization Server | <code>OAuth2AuthorizationServerConfigurer</code> in Java DSL | Prefer <code>getEndpointsMatcher()</code>. |
| Register security endpoints and login | <code>SecurityFilterChain</code> with <code>HttpSecurity</code> | Can separate the AS chain and Web chain. |
| Enable OIDC endpoints | <code>authorizationServer.oidc(...)</code> | Not enabled automatically just by having the <code>openid</code> scope. |
| Register client, grant, redirect URI, scopes | Boot properties **or** <code>RegisteredClientRepository</code> bean | Do not maintain two independent registration sources that accidentally duplicate clients. |
| Set issuer URL and customize endpoint paths | <code>AuthorizationServerSettings</code> (or property mechanisms supported by the Boot version) | Values must match public URLs. |
| Generate, store, and rotate signing keys | <code>JWKSource&lt;SecurityContext&gt;</code> / key store | Never place private keys in public YAML or generate a new key on every restart in production. |
| Persist authorization codes, refresh tokens, consent | <code>OAuth2AuthorizationService</code>, <code>OAuth2AuthorizationConsentService</code> | Use persistent storage in real operations. |
| Customize claims, audience, TTL/token format | Java beans such as <code>OAuth2TokenCustomizer</code>, <code>TokenSettings</code> | Enforce clear token issuance policies. |
| Port, TLS/proxy, profiles, logging levels | Spring Boot properties and infrastructure | Must coordinate proxy and issuer configuration. |

## 3. Preparing the Application and Dependencies

In Spring Boot, the project needs compatible Spring Security and Spring Authorization Server libraries. With Spring Boot 3.x releases providing the corresponding starter, you can begin with:

~~~xml
<!-- Maven: Boot dependency management manages compatible versions. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
~~~

If using Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
}
~~~

Do not arbitrarily mix Spring Security/Spring Authorization Server versions outside Boot's dependency management: mismatched versions can cause DSL method errors or missing beans. Different Boot/framework versions package starters and APIs differently; examples in this lesson use the Java DSL API family introduced in section 1.

At a minimum, you need these components:

- **SecurityFilterChain for the Authorization Server** and a chain handling interactive login.
- **RegisteredClientRepository**: looks up valid clients, grants, redirect URIs, and scopes.
- **OAuth2AuthorizationService**: stores authorization state, authorization codes, and related tokens.
- **OAuth2AuthorizationConsentService**: stores user consent if that feature is used.
- **JWKSource** and appropriate JWT components to sign/verify ID Tokens or JWT access tokens.
- **AuthorizationServerSettings** for issuer and endpoint settings.
- **User authentication** when supporting Authorization Code/OIDC with interactive user login.

Some beans may be supplied by the framework/Boot depending on the classpath and auto-configuration conditions; do not assume every system automatically gets all required components simply by adding the dependency.

## 4. Configuring Clients with Spring Boot Properties

### 4.1. Example <code>application.yml</code>

Properties under <code>spring.security.oauth2.authorizationserver.client</code> can let Boot construct registered client configurations when auto-configuration conditions are satisfied:

~~~yaml
server:
  port: 9000
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      authorizationserver:
        client:
          portal-web:
            registration:
              client-id: portal-web
              # Environment value is an encoded hash such as {bcrypt}...
              client-secret: "${PORTAL_CLIENT_SECRET_HASH}"
              client-authentication-methods:
                - client_secret_basic
              authorization-grant-types:
                - authorization_code
                - refresh_token
              redirect-uris:
                - https://portal.example.com/login/oauth2/code/portal-web
              post-logout-redirect-uris:
                - https://portal.example.com/
              scopes:
                - openid
                - profile
                - orders.read
            require-authorization-consent: true
~~~

This is an example of a **confidential web client** capable of protecting its client secret on the backend. For browser or mobile apps that are **public clients**, never embed a client secret in the frontend; instead register an appropriate authentication method and PKCE policy rather than using this confidential client configuration.

Meaning of key branches:

| Property | Role |
| --- | --- |
| <code>client.portal-web</code> | Registration key in Boot configuration; does not have to equal <code>client-id</code>. |
| <code>registration.client-id</code> | Client identifier sent to OAuth 2.0 endpoints. |
| <code>registration.client-secret</code> | Secret **encoded to match the PasswordEncoder**, e.g. a string prefixed with <code>{bcrypt}</code>. The actual client sends the raw secret. |
| <code>registration.client-authentication-methods</code> | Accepted client authentication methods, e.g. <code>client_secret_basic</code>. |
| <code>registration.authorization-grant-types</code> | Grants the client is permitted to use; do not allow all grant types just because a client might request them. |
| <code>registration.redirect-uris</code> | Exact list of registered redirect URIs; avoid wildcards or arbitrary redirects. |
| <code>registration.scopes</code> | Scopes the client may request; actually granted scopes also depend on policy/consent. |
| <code>require-authorization-consent</code> | Requires user consent when appropriate for the flow and server policy. |

**Version note:** This property shape is common in Spring Boot releases integrating Spring Authorization Server. Inspect the configuration metadata of your exact version to confirm the name, placement, and support scope of each property, especially advanced options such as client settings and token settings. Do not assume every setter on <code>RegisteredClient</code> has a matching YAML key.

### 4.2. What Makes a Client Secret Secure?

<code>PORTAL_CLIENT_SECRET_HASH</code> must be encoded with the password encoder used by the Authorization Server, such as <code>{bcrypt}$2a$...</code>. The <code>{bcrypt}</code> prefix tells a standard <code>DelegatingPasswordEncoder</code> how to match it. Never commit raw client secrets, production secrets, or private signing keys to Git.

For local demos, you may see <code>{noop}dev-secret</code> in tutorials. That approach is **only suitable for learning in an isolated environment**, never for production clients. In production, manage secrets through deployment configuration, a secret manager, least-privilege read access, and rotation procedures.

### 4.3. Distinguishing Three OAuth Namespaces in Spring Boot

The following keys look similar yet serve **different roles**:

| Namespace | What role is the application playing? |
| --- | --- |
| <code>spring.security.oauth2.authorizationserver.client...</code> | **Authorization Server**: registers clients that will be issued tokens. |
| <code>spring.security.oauth2.client.registration...</code> | **OAuth 2.0/OIDC Client**: application logging in/authorizing with an external provider. |
| <code>spring.security.oauth2.resourceserver.jwt...</code> | **Resource Server**: API receiving and validating JWT access tokens. |

For example, adding <code>spring.security.oauth2.client.registration.portal-web</code> to the Authorization Server does not register that client in <code>RegisteredClientRepository</code>. Likewise, declaring <code>resourceserver.jwt.issuer-uri</code> only helps an API consume JWTs per that configuration; it does not stand up a token endpoint.

## 5. Configuring SecurityFilterChain with Java DSL

### 5.1. Dedicated Chain for OAuth 2.0/OIDC Endpoints

Java DSL determines **which requests are processed by the OAuth2/OIDC filters**. Below is a configuration template for Spring Authorization Server versions supporting <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> and <code>HttpSecurity.with(...)</code>:

~~~java
@Configuration
@EnableWebSecurity
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Imports are omitted. The snippet focuses on **DSL layout**; add the beans and dependencies appropriate for your project version before running.

**Explanation:**

1. <code>@Order(1)</code> places the Authorization Server chain before the Web chain. Spring Security selects the **first matching chain**; the Web chain without a <code>securityMatcher</code> acts as fallback.
2. <code>getEndpointsMatcher()</code> covers endpoints managed by the Authorization Server configurer. Do not replace it with <code>"/oauth2/**"</code> because OIDC metadata/UserInfo/logout may sit outside that prefix.
3. <code>.with(authorizationServer, ...)</code> attaches the protocol filters and components to the chain; <code>.oidc(...)</code> enables OIDC support under the corresponding conditions/configurers.
4. <code>.authorizeHttpRequests(...authenticated())</code> is an **HTTP authorization rule**; validating clients, authorization codes, PKCE, tokens, and consent is still handled by dedicated OAuth2/OIDC components. Never open <code>/oauth2/token</code> with <code>permitAll()</code> to "fix" client authentication errors.
5. The entry point redirects **HTML requests requiring login** to <code>/login</code>; that route is handled by the Web chain via <code>formLogin</code>.
6. <code>oauth2ResourceServer().jwt()</code> may be required for OIDC endpoints accepting Bearer tokens such as UserInfo. It requires an appropriate <code>JwtDecoder</code>; it does not mean this application already hosts a full business API.

This configuration intentionally does not disable CSRF globally. The Authorization Server configurer handles CSRF appropriately for protocol endpoints; the Web chain still needs CSRF protection when using cookie/session-based login forms.

### 5.2. Configuring a Fixed, Consistent Issuer

~~~java
@Configuration
class AuthorizationServerMetadataConfig {
    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
    }
}
~~~

<code>issuer</code> is the token-issuing identifier used by clients and Resource Servers to verify <code>iss</code>, and it usually appears in discovery metadata as well. It is **not** an arbitrary address to change per HTTP request.

Infrastructure example:

~~~text
Browser / OAuth Client
      |
      | https://auth.example.com (TLS)
      v
Trusted reverse proxy / load balancer
      |
      | http://authorization-server:9000 (private network)
      v
Spring Boot Authorization Server
~~~

The application can listen on internal port 9000 while publishing the issuer <code>https://auth.example.com</code>. When running behind a proxy:

- Use a **public, stable** issuer URL; do not let an internal host <code>localhost</code>, container name, or individual port become the production issuer.
- Forwarded headers should only be trusted when the proxy/infrastructure **strips spoofed headers from clients and sets trusted headers itself**; configuring <code>server.forward-headers-strategy</code> must accompany proxy configuration.
- Cross-check <code>issuer</code> in discovery metadata, JWT <code>iss</code>, the issuer URI configured on clients/Resource Servers, and actual URLs. Changing the issuer is a change of issuer identity requiring a compatibility and migration plan.
- If customizing endpoint paths, use centralized <code>AuthorizationServerSettings</code> configuration instead of scattering hard-coded URLs across multiple filters and clients.

### 5.3. Configuring JWT Decoder and JWKSource

An Authorization Server must have an appropriate signing key source when issuing JWT-formatted tokens. When OIDC is enabled, configuring <code>JwtDecoder</code> from `JWKSource` is a common pattern:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

The bean above **does not generate keys**; the project must supply <code>JWKSource&lt;SecurityContext&gt;</code> from a trusted key store or signing configuration. In local demos, tutorials sometimes generate an RSA key pair via <code>KeyPairGenerator</code> at application startup. Never use that as-is in production: a restart replaces the key, which can render previously issued tokens unverifiable. Store keys securely, use explicit <code>kid</code> values, plan an overlap period for old/new keys during rotation, and publish only **public** keys via the JWKS endpoint.

Never insert literal private keys into documentation examples, logs, or committed configuration sources. Token formats, signing algorithms, and supported key sets must be chosen consistently with Resource Servers.

### 5.4. Enabling OIDC Differs from Enabling Basic OAuth 2.0

An OAuth 2.0 Authorization Server can issue access tokens without providing OIDC login capabilities. When enabling <code>oidc(Customizer.withDefaults())</code>, the system adds corresponding OIDC capabilities such as ID Tokens and version-supported endpoints, yet you still must:

- Register <code>openid</code> in the appropriate client's scope list.
- Provide an End-User authentication source and a way to determine the subject (<code>sub</code>).
- Have signing keys/decoder and supporting services for required OIDC endpoints.
- Test discovery metadata, authorization responses, and ID Tokens; never assume "declaring the openid scope" alone makes OIDC work.

OIDC should only expose features/endpoints you actually use; for instance, dynamic client registration should not be left publicly enabled without appropriate registration policies and authentication.

## 6. When Should You Declare RegisteredClient in Java Instead of YAML?

Boot properties are suited for **a small number of static clients**, typically in test environments or small deployments. When a system has many clients, per-tenant administration, automated onboarding, controlled updates to scopes/redirect URIs, or requires durable persistence, use an explicit <code>RegisteredClientRepository</code>.

Example creating the same <code>portal-web</code> client in Java (this is an **alternative** to YAML registration, not an additional parallel declaration):

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        @Value("${PORTAL_CLIENT_SECRET_HASH}") String secretHash) {

    RegisteredClient portal = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("portal-web")
        .clientSecret(secretHash)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://portal.example.com/login/oauth2/code/portal-web")
        .postLogoutRedirectUri("https://portal.example.com/")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
            .requireAuthorizationConsent(true)
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(portal);
}
~~~

The client fields above correspond to the <code>registration</code> section of the YAML example. Do not keep independent copies of the same client across multiple data sources, as it becomes unclear which is the source of truth.

**Lifecycle warning:** <code>InMemoryRegisteredClientRepository</code> is suitable for demos. Calling <code>UUID.randomUUID()</code> on every startup changes the client record ID; in real systems, use stable IDs, deterministic configuration/migrations, and a database-backed repository. With multi-instance deployments, client data must stay consistent across nodes.

### 6.1. JDBC-Backed Repositories

Spring Authorization Server provides JDBC implementations for core data:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(JdbcTemplate jdbc) {
    return new JdbcRegisteredClientRepository(jdbc);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbc,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(jdbc, registeredClients);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbc,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationConsentService(jdbc, registeredClients);
}
~~~

This is only bean registration scaffolding, **not a complete database configuration**. Before running, prepare the schema matching your library version and migration mechanism; seed initial client records; configure connection pooling, indexes, transactions, backups, expired data cleanup, and database permissions. Multi-node systems must share required state and trust the same key source, issuer, and client records.

If you declare a custom <code>RegisteredClientRepository</code> bean, Boot's auto-configuration creating a repository from properties **may back off under auto-configuration conditions**. Therefore, never assume a client in YAML is automatically registered. Always verify the active repository at runtime and with a valid OAuth 2.0 request.

### 6.2. Configuring Tokens in Java

Token policies often vary per client and token type, for example:

~~~java
TokenSettings tokens = TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(10))
    .refreshTokenTimeToLive(Duration.ofDays(7))
    .reuseRefreshTokens(false)
    .build();

RegisteredClient client = RegisteredClient.withId("stable-client-record-id")
    .clientId("portal-web")
    // Other required authentication/grant/redirect URI/scope fields...
    .tokenSettings(tokens)
    .build();
~~~

This is only an illustrative snippet: a real <code>RegisteredClient</code> must include all other valid fields. In real systems, access/refresh token lifetimes, refresh token rotation, revocation, replay detection, and re-authentication requirements are **security policies**, not arbitrary numbers. Changing a token lifetime can impact service load, user experience, and the exposure window of compromised credentials.

## 7. Auto-Configuration and Manual Beans: How Do They Work Together?

**Spring Boot auto-configuration is conditional**, evaluating present dependencies, existing bean types, and matching properties. Adding an application-defined bean can prevent a default Boot-provided bean from being created. This is especially important when combining Java DSL with Boot properties.

### 7.1. Three Common Organizational Patterns

| Pattern | Advantages | Limitations / Fit |
| --- | --- | --- |
| Boot properties as static client source; Java DSL for chain/issuer/keys | Concise, easy to read per profile | Must verify auto-configuration conditions; fits rarely changing clients. |
| Java <code>RegisteredClientRepository</code> + Java DSL | Explicit control over client objects and policies | Can introduce boilerplate configuration; requires managing ID and secret lifecycles. |
| JDBC repositories + Java DSL + environment properties | Fits multi-instance, client administration, and long-term operations | Must manage schema, migrations, keys, DB connections, and sensitive data. |

There is no rule saying "Java DSL always overrides all YAML" or "properties always override beans". **Each auto-configuration has its own conditions.** When in doubt, inspect the condition evaluation report (e.g., enabling debug during dev diagnostics), the actual registered beans, and HTTP test results. Do not resort to trial-and-error by defining duplicate beans of the same type and letting Spring pick arbitrarily.

### 7.2. Environment Property Precedence

Spring Boot supports configuration from files, profiles, environment variables, command-line arguments, and other property sources with well-defined precedence rules. An environment-split configuration can look like:

~~~yaml
# application.yml: shared baseline, containing no secrets.
server:
  port: 9000

logging:
  level:
    org.springframework.security: INFO
~~~

~~~yaml
# application-dev.yml: enabled only when working on a developer machine.
logging:
  level:
    org.springframework.security: DEBUG
~~~

Never embed sensitive data in committed profile files. For public issuers and client registrations, manage configuration from a single unified source to prevent profiles or environment variables from causing metadata, redirect URIs, or signing keys to drift across instances.

## 8. Boundaries Between Java DSL, Endpoint Settings, and Application Properties

Three configuration groups are very easy to mix up:

1. **<code>HttpSecurity</code>**: configures request protection, authentication, exception handling, sessions, CSRF, and filter chains.
2. **<code>AuthorizationServerSettings</code>**: configures the Authorization Server's issuer identifier and endpoint paths using framework-provided APIs.
3. **Spring Boot properties**: supplies environment values and configurations bound/auto-configured by Boot, including client registration details in supported versions.

For instance, changing the token endpoint path via <code>AuthorizationServerSettings</code> does not mean you just update a hard-coded matcher in the chain. When using <code>getEndpointsMatcher()</code>, the AS chain automatically stays aligned with the AS endpoint settings. Still, clients must call the new URL and metadata must reflect the official configuration.

An example of customizing settings (use only when backed by clear product requirements):

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .tokenEndpoint("/oauth2/token")
        .build();
}
~~~

In the example, <code>.tokenEndpoint("/oauth2/token")</code> is the common default value, written to demonstrate the settings API. Changing it to another path requires updating proxy configuration, clients, discovery, monitoring, and tests; do not customize endpoints purely for naming convenience.

## 9. Verifying That the Application Is Properly Configured

### 9.1. Checking Discovery and JWKS

When OIDC is configured and deployed at a public URL, you can check:

~~~bash
# OIDC discovery; endpoint must be enabled and publish the accurate issuer.
curl -i https://auth.example.com/.well-known/openid-configuration

# JWKS: contains public key information only.
curl -i https://auth.example.com/oauth2/jwks
~~~

In the discovery JSON, inspect <code>issuer</code>, <code>authorization_endpoint</code>, <code>token_endpoint</code>, <code>jwks_uri</code>, and other capabilities. These URLs must use valid public hostnames/schemes; the issuer in metadata must match the value trusted by clients/Resource Servers. If you changed endpoints via <code>AuthorizationServerSettings</code>, re-check the corresponding metadata.

If JWKS returns 404, verify <code>JWKSource</code>, endpoint settings, filter chains, and framework configuration. If OIDC discovery returns 404, check whether OIDC is enabled, the AS chain has the right matcher, and your library version supports the expected endpoint.

### 9.2. Verifying Client Registration via Protocol Behavior

With the <code>portal-web</code> web client, execute **Authorization Code + PKCE** from a real registered OAuth/OIDC client or via an integration test:

~~~text
GET /oauth2/authorize
    ?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal-web
    &scope=openid%20orders.read
    &state=<secure-random-state>
    &code_challenge=<base64url-sha256-pkce-challenge>
    &code_challenge_method=S256
~~~

This snippet **only illustrates the request structure**: line breaks are for readability, state and PKCE values must be genuinely generated and properly verified, and the client must satisfy its authentication policy. A successful flow proves multiple components work together: the request hits the AS chain, the client is resolved from the repository, the redirect URI is valid, the user logs in, consent/grant is approved, and tokens are issued.

If the server returns <code>invalid_client</code>, <code>invalid_request</code>, <code>invalid_scope</code>, or a redirect error, do not rush to loosen rules with <code>permitAll()</code>. Check client ID, authentication method, redirect URI, grant, scopes, PKCE, and registration policy first.

### 9.3. Configuration Test Matrix

| Case | Expected result |
| --- | --- |
| <code>/oauth2/authorize</code> with registered client | AS chain handles request, routes to login/consent when appropriate. |
| <code>/oauth2/token</code> with wrong client secret | Returns appropriate protocol/client-authentication error; issues no token. |
| Client requests unregistered scope | Does not grant permissions outside registration/policy. |
| Redirect URI has modified host/path | Request rejected according to redirect URI rules. |
| Client uses unregistered grant | Request is not accepted. |
| OIDC discovery when OIDC is enabled | Provides metadata consistent with public issuer/endpoints. |
| JWKS endpoint | Publishes appropriate public keys; exposes no private key. |
| JWT access/ID Token | Signed with active key; <code>iss</code>, <code>aud</code>, and lifetimes are appropriate. |
| Restart an instance | Signing keys, repository, and required state do not change unexpectedly. |
| Running multiple instances | Clients, authorizations/consents, and keys share a unified data/key source. |
| Switching profile or secret | Runtime config honors precedence; no sensitive values logged. |
| Accessing <code>/login</code> | Handled by login chain, not "swallowed" by the AS chain. |

In Spring Security Test, mocked JWT authentication can **bypass** signature/issuer/audience verification; to test the real decoder and keys, run integration tests exercising the actual authentication path.

## 10. Diagnosing Common Configuration Errors

### Error A: Client declared in YAML yet server reports <code>invalid_client</code>

**Symptom:** <code>application.yml</code> defines <code>spring.security.oauth2.authorizationserver.client...</code>, yet the token endpoint does not recognize the client.

**Checks:** Is a manual <code>RegisteredClientRepository</code> bean causing Boot to back off? Is the right profile active? Are properties bound for this version? Do <code>client-id</code>, authentication method, and secret match? Which repository actually holds the client?

**Remediation:** Pick one authoritative registration source, inspect runtime beans and client records, and execute a real client authentication request. Never fix this by disabling client authentication.

### Error B: <code>/oauth2/token</code> returns 404 or an HTML login page

**Possible causes:** Authorization Server chain lacks the configurer, a catch-all chain is ordered ahead of it, the endpoint path changed, or the request fell into the Web chain.

**Remediation:** Inspect <code>@Order</code>, <code>securityMatcher(authorizationServer.getEndpointsMatcher())</code>, endpoint settings, and <code>FilterChainProxy</code> debug logs; keep AS and Web chain responsibilities separate.

### Error C: Tokens are issued, yet OIDC discovery or UserInfo does not work

**Possible causes:** <code>oidc(...)</code> not enabled, missing required JWT beans, missing endpoint matcher, missing matching token, or endpoint not enabled in the current version/framework.

**Remediation:** Check OIDC configurer, metadata, JWKSource/JwtDecoder, <code>openid</code> scope, token type, and configured endpoints. Never assume all OIDC endpoints are always enabled by default.

### Error D: JWT carries an internal address as issuer instead of the public URL

**Possible causes:** Missing fixed issuer or inconsistent proxy/forwarded headers configuration.

**Remediation:** Set a stable public issuer in <code>AuthorizationServerSettings</code>; configure trusted proxies and verify discovery plus the JWT <code>iss</code> claim.

### Error E: After restart, clients report old tokens are invalid

**Possible causes:** Generating a fresh key pair on every startup; tokens signed with the old key are no longer published.

**Remediation:** Store keys securely and implement a rotation workflow with an overlap window publishing both old and new public keys. Combine with persistent authorization/consent storage for flows requiring state across restarts.

### Error F: Secret from YAML fails authentication

**Possible causes:** Entered plaintext directly, missing appropriate encoder prefix, or confusing the raw secret with the hashed secret.

**Remediation:** Verify the Authorization Server's actual <code>PasswordEncoder</code>; store a properly formatted hash, deliver the raw secret to the confidential client via a secure secret mechanism, and check how the secret is sent per the registered <code>client_authentication_method</code>.

### Error G: Disabling CSRF globally to fix token request errors

**Risk:** The Web chain containing session/cookie-based form login loses CSRF protection; token endpoint errors may stem from client registration or matcher configuration rather than CSRF.

**Remediation:** Let the AS configurer handle OAuth2 endpoints appropriately; keep CSRF enabled for web login, applying only targeted exemptions for clearly identified endpoints/authentication models.

## 11. Moving from Demo to Production

A demo version might use <code>InMemoryRegisteredClientRepository</code>, mock users, and startup-generated key pairs. For real operations:

1. **Issuer and public URLs:** fixed via official configuration, using HTTPS, consistent metadata, protected proxy and forwarded header configuration.
2. **Client lifecycle:** store clients with stable IDs; manage adding/editing redirect URIs, grants, scopes, client status, and secret rotation via controlled processes.
3. **Token and consent persistence:** use a database or appropriate backend with backups/migrations and expired data cleanup. Test transactions and multiple nodes.
4. **Token signing:** use protected private keys supporting <code>kid</code>, rotation, key overlap windows, and recovery plans; never change keys merely on restart.
5. **User authentication:** integrate user directories/MFA/session login policies; never ship demo users/secrets to production.
6. **Least privilege:** restrict grants and scopes per client; Resource Servers verify issuer, audience, expiration, and data-level permissions.
7. **Monitoring and audit:** track authentication/issuance errors, latency, database and key health; keep logs safe without writing raw authorization codes, access tokens, refresh tokens, or client secrets.
8. **Upgrades:** pin compatible dependency versions, run integration tests when upgrading Boot/Security/Authorization Server, and re-verify property binding and DSL.

## 12. Hands-On Exercise

A company wants to deploy a shared Authorization Server for <code>customer-portal</code> and <code>billing-backend</code>:

1. <code>customer-portal</code> is a confidential web client needing Authorization Code and <code>openid profile invoices.read</code>. Write the corresponding Boot properties.
2. <code>billing-backend</code> is a service client needing Client Credentials and <code>invoices.generate</code>. Explain why you should not add <code>openid</code> or expect an End-User from this grant.
3. Write two <code>SecurityFilterChain</code> beans: one for OAuth2/OIDC endpoints using <code>getEndpointsMatcher()</code>, and one for the login page.
4. Decide to move the client list from YAML to JDBC. Identify the repository bean to create, the data needing migration, and how to verify there are no longer two parallel client sources.
5. The application runs behind a reverse proxy. Verify that issuer, discovery, JWKS, and URL fields in JWTs match <code>https://identity.example.com</code>.
6. Build a test matrix covering wrong client secret, wrong redirect URI, missing scope, wrong grant, rotated keys, restart, and two instances sharing a database.

**Design check hint:** A strong solution clearly explains **what is bound from properties**, **what must be created via beans/Java DSL**, **which chain handles each request**, and **which configuration survives restarts**.

## 13. References

- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): minimal configuration components and Authorization Server setup.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): <code>OAuth2AuthorizationServerConfigurer</code>, endpoints, and DSL customization.
- [Spring Authorization Server — Core Model / RegisteredClient](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, repositories, authorization, and consent.
- [Spring Boot — OAuth2 Authorization Server](https://docs.spring.io/spring-boot/reference/web/spring-security.html): Spring Security/Authorization Server integration and auto-configuration by Boot version.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, profiles, and precedence order.
- [Spring Security — Servlet Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): <code>SecurityFilterChain</code>, <code>HttpSecurity</code>, and multiple chains.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validating access tokens on the Resource Server.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Authorization Server metadata and issuer.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): discovery metadata for OIDC.
