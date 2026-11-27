# 5.7. `InMemoryClientRegistrationRepository` and Java Configuration

## 1. Context: Where Does a Spring Security Application Get OAuth 2.0 Client Details?

When a Spring Boot application signs users in with OAuth 2.0 or OpenID Connect (OIDC), it needs to know how it is registered with the Authorization Server/OpenID Provider. That information includes **client ID**, client authentication method, authorization endpoint, token endpoint, redirect URI, scopes, and possibly issuer/JWK Set URI when using OIDC.

Spring Security represents such a configuration with a **<code>ClientRegistration</code>** object. Each registration has a unique **<code>registrationId</code>** within the application, such as <code>google</code>, <code>github</code>, or <code>company-sso</code>.

Spring Security does not force applications to store registrations in <code>application.yml</code>. The framework only needs a bean of type **<code>ClientRegistrationRepository</code>** to look up registrations by ID.

**<code>InMemoryClientRegistrationRepository</code>** is a simple implementation of this interface. It holds a collection of <code>ClientRegistration</code>s in application memory, suitable when the provider list is fixed or constructed from Java configuration at startup.

Overview flow:

~~~mermaid
flowchart TD
    A["Java configuration / environment variables / discovery"] --> B["Create ClientRegistration"]
    B --> C["InMemoryClientRegistrationRepository"]
    D["GET /oauth2/authorization/company-sso"] --> E["Spring Security OAuth2 Login"]
    E --> F["findByRegistrationId('company-sso')"]
    F --> C
    C --> G["Matching ClientRegistration"]
    G --> H["Create authorization request"]
    H --> I["Authorization Server / OpenID Provider"]
~~~

> **Distinguish from the start:** This repository stores **Client configuration**, not access tokens, refresh tokens, ID Tokens, or user login sessions.

## 2. Data Types and Role of Each Component

| Component | Role | Example data |
|---|---|---|
| <code>ClientRegistration</code> | Describes **one** OAuth 2.0/OIDC Client registered with a provider | <code>clientId</code>, <code>redirectUri</code>, <code>authorizationUri</code>, <code>scope</code> |
| <code>ClientRegistrationRepository</code> | Contract for looking up a registration by <code>registrationId</code> | <code>findByRegistrationId("company-sso")</code> |
| <code>InMemoryClientRegistrationRepository</code> | Implementation holding multiple registrations in memory | Set of registrations <code>company-sso</code>, <code>github</code> |
| <code>OAuth2AuthorizedClient</code> | Associates a ClientRegistration and principal with issued tokens | Access token, refresh token if present |
| <code>OAuth2AuthorizedClientService</code> | Manages authorized clients by registration/principal, typically for the service layer | <code>loadAuthorizedClient(...)</code> |
| <code>OAuth2AuthorizedClientRepository</code> | Stores/looks up authorized clients in a web request context | Tokens tied to session/request |
| <code>SecurityFilterChain</code> | Configures how the application enables OAuth2 Login or OAuth2 Client | <code>oauth2Login()</code>, <code>oauth2Client()</code> |

The <code>InMemory...</code> name can be misleading. <code>InMemoryClientRegistrationRepository</code> **does not store login state itself**. Choosing where to store user sessions, authorized clients, and tokens is a separate decision implemented by other components.

### 2.1. `ClientRegistrationRepository` Interface

The interface's core contract is tiny:

~~~java
public interface ClientRegistrationRepository {
    ClientRegistration findByRegistrationId(String registrationId);
}
~~~

Spring Security uses <code>registrationId</code> to select a registration when starting login, receiving callbacks, or handling OAuth2 Client operations. If the ID is not found, <code>findByRegistrationId</code> returns <code>null</code>; downstream callers may fail because no Client configuration was found.

<code>InMemoryClientRegistrationRepository</code> also implements <code>Iterable&lt;ClientRegistration&gt;</code>, allowing Spring Security to iterate through registrations in scenarios such as generating a login page with multiple OAuth providers.

### 2.2. Ways to Instantiate the Repository

Two common usages:

~~~java
ClientRegistration first = /* create first ClientRegistration */;
ClientRegistration second = /* create second ClientRegistration */;

ClientRegistrationRepository byVarargs =
        new InMemoryClientRegistrationRepository(first, second);

ClientRegistrationRepository byList =
        new InMemoryClientRegistrationRepository(List.of(first, second));
~~~

You must import <code>java.util.List</code> and the corresponding Spring Security classes. This is an API illustration, not a standalone Java file: both <code>first</code> and <code>second</code> variables must be built from valid configurations beforehand.

The repository retains the set of registrations passed when constructing the bean. It suits **a stable configuration list**; this API does not provide dynamic provider administration or automatic synchronization of registrations from a database across instances.

## 3. Configuring OIDC in Java with Issuer Discovery

This is the easiest approach to maintain when the application uses an OpenID Provider supporting an **OIDC Discovery Document**. Instead of declaring authorization URL, token URL, and JWKS URL manually, the application provides <code>issuer-uri</code> so the library discovers metadata.

### 3.1. Dependencies

With Spring Boot 3 and Spring Security 6, use the OAuth2 Client starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

If using Maven, the equivalent dependency is <code>org.springframework.boot:spring-boot-starter-oauth2-client</code> alongside the appropriate web/security starters.

### 3.2. Application-Specific Configuration Properties

Because we will create the bean in Java, we can place provider details in a custom configuration group instead of using the auto-config group <code>spring.security.oauth2.client.registration</code>:

~~~yaml
# application.yml
app:
  oidc:
    issuer-uri: https://login.example.org/realms/training
    client-id: ${APP_OIDC_CLIENT_ID}
    client-secret: ${APP_OIDC_CLIENT_SECRET}
~~~

<code>APP_OIDC_CLIENT_ID</code> and <code>APP_OIDC_CLIENT_SECRET</code> are environment variables supplied by the deployment system. <code>https://login.example.org/realms/training</code> is an illustrative issuer that must be replaced with your OP's official issuer.

Store the client secret in an appropriate secret manager/environment variable; never commit real values into files or source code.

### 3.3. Creating the `ClientRegistrationRepository` Bean

~~~java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class OAuth2ClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.oidc.issuer-uri}") String issuerUri,
            @Value("${app.oidc.client-id}") String clientId,
            @Value("${app.oidc.client-secret}") String clientSecret) {

        ClientRegistration training = ClientRegistrations
            .fromIssuerLocation(issuerUri)
            .registrationId("training")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .build();

        return new InMemoryClientRegistrationRepository(training);
    }
}
~~~

Step-by-step explanation:

1. <code>ClientRegistrations.fromIssuerLocation(issuerUri)</code> fetches metadata from the issuer per the discovery mechanism supported by your Spring Security version. Metadata helps populate endpoints and provider info. The issuer URL must come from trusted configuration.
2. <code>registrationId("training")</code> sets the internal key for the registration, which does not need to match the host, tenant, or Client ID.
3. <code>clientId</code>/<code>clientSecret</code> are the application credentials registered with the OP.
4. <code>CLIENT_SECRET_BASIC</code> defines how the confidential Client authenticates at the token endpoint; it must match the actual registration on the OP.
5. <code>AUTHORIZATION_CODE</code> selects the Authorization Code Flow.
6. <code>redirectUri</code> uses Spring Security's default URI template, expanded from the request and registration ID at runtime. The expanded Redirect URI must match the URI registered at the OP.
7. The <code>openid</code> scope requests OIDC; <code>profile</code>/<code>email</code> scopes are granted only when permitted by the OP and Client policy.
8. The repository is created with one <code>ClientRegistration</code>. Spring Security looks it up by ID <code>training</code>.

With <code>fromIssuerLocation</code>, the library may perform network calls **while creating the bean**, typically during application startup. If the OP is unavailable, the issuer is wrong, or TLS/DNS has issues, initializing the `ClientRegistration` can fail. This must be accounted for in deployment and operations planning.

If the system requires a public client, do not use a client secret; register the right Client type, choose <code>ClientAuthenticationMethod.NONE</code>, and ensure PKCE is applied. The example above is for a server-side **confidential web Client**.

### 3.4. Enabling OAuth2 Login

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

When running the application, the default path to start the flow is:

~~~http
GET /oauth2/authorization/training HTTP/1.1
Host: app.example.org
~~~

Spring Security looks up registration ID <code>training</code>, constructs the authorization request, and sends the browser to the OP. The corresponding default callback is:

~~~text
https://app.example.org/login/oauth2/code/training
~~~

After authentication, Spring Security processes the code/tokens and establishes the principal based on OAuth2/OIDC. If the provider issues a valid OIDC ID Token, the framework processes it via the OIDC Login flow.

> You only need <code>oauth2Login()</code> for the user login use case. If the application also actively calls downstream APIs as an OAuth2 Client, you may need to additionally configure <code>oauth2Client()</code>, an authorized client manager, and an appropriate token storage mechanism.

## 4. Java Configuration with Manually Declared Endpoints

Not every OAuth 2.0 provider supports OIDC Discovery. When using an OAuth 2.0 provider with fixed endpoints, you can directly construct a <code>ClientRegistration</code> via <code>ClientRegistration.withRegistrationId(...)</code>.

Example of an illustrative OAuth 2.0 provider whose UserInfo endpoint returns JSON with an <code>id</code> property:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class ManualProviderConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration legacy = ClientRegistration
            .withRegistrationId("legacy")
            .clientId("replace-with-client-id")
            .clientSecret("replace-with-secret")
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("read_profile")
            .authorizationUri("https://legacy.example.org/oauth2/authorize")
            .tokenUri("https://legacy.example.org/oauth2/token")
            .userInfoUri("https://legacy.example.org/api/user")
            .userNameAttributeName("id")
            .clientName("Legacy Provider")
            .build();

        return new InMemoryClientRegistrationRepository(legacy);
    }
}
~~~

This is **an independent alternative** to the bean in section 3.3; do not declare two <code>ClientRegistrationRepository</code> beans simultaneously without a deliberate design and explicit bean-selection mechanism. Sample values must be replaced with the provider's official configuration, and secrets in particular should not be hardcoded in real applications.

Key builder methods:

| Method | Meaning |
|---|---|
| <code>withRegistrationId("legacy")</code> | Creates a builder for the registration with ID <code>legacy</code> |
| <code>clientId(...)</code> | Client ID issued by the Authorization Server |
| <code>clientSecret(...)</code> | Secret for a confidential Client, if required by the authentication method |
| <code>clientAuthenticationMethod(...)</code> | How the Client authenticates at the token endpoint |
| <code>authorizationGrantType(...)</code> | Grant type, authorization code in this example |
| <code>redirectUri(...)</code> | Client callback |
| <code>scope(...)</code> | Requested scopes |
| <code>authorizationUri(...)</code> | Authorization endpoint |
| <code>tokenUri(...)</code> | Token endpoint |
| <code>userInfoUri(...)</code> | Provider's UserInfo address if used to retrieve user information |
| <code>userNameAttributeName(...)</code> | Attribute identifying the principal in an OAuth2 provider's user info response |
| <code>jwkSetUri(...)</code> | JWKS URI when JWT/ID Token verification is needed |
| <code>issuerUri(...)</code> | OP issuer in configurations that support this field |
| <code>clientName(...)</code> | Client display name, useful on login pages |

With an **OIDC provider** that does not publish discovery metadata, ensure the application has sufficient information to validate **issuer, ID Token signature, audience**, and other OIDC constraints. Adding the <code>openid</code> scope to a plain OAuth 2.0 example does not automatically turn the provider into OIDC or guarantee proper validation.

### 4.1. Using `CommonOAuth2Provider` for Well-Known Providers

Spring Security also provides the <code>CommonOAuth2Provider</code> enum with pre-defined builders for several popular providers. Example of a Google registration:

~~~java
import org.springframework.security.config.oauth2.client.CommonOAuth2Provider;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Bean
ClientRegistrationRepository clientRegistrationRepository() {
    ClientRegistration google = CommonOAuth2Provider.GOOGLE
        .getBuilder("google")
        .clientId("replace-with-google-client-id")
        .clientSecret("replace-with-google-client-secret")
        .scope("openid", "profile", "email")
        .build();

    return new InMemoryClientRegistrationRepository(google);
}
~~~

This is merely an illustrative bean snippet to place inside a <code>@Configuration</code> class—**do not declare it alongside beans of the same name/type from other examples**. In practice, inject credentials from a secret manager or configuration properties. The provider's builder pre-fills appropriate default endpoints and settings, yet you must still register the OAuth Client and callback properly with the provider.

## 5. Multiple Providers in One `InMemoryClientRegistrationRepository`

An application can let users sign in with enterprise SSO and an external provider. In that case, create **two `ClientRegistration`s** with two different registration IDs:

~~~java
@Bean
ClientRegistrationRepository clientRegistrationRepository(
        @Value("${app.oidc.issuer-uri}") String issuer,
        @Value("${app.oidc.client-id}") String ssoClientId,
        @Value("${app.oidc.client-secret}") String ssoSecret,
        @Value("${app.google.client-id}") String googleClientId,
        @Value("${app.google.client-secret}") String googleSecret) {

    ClientRegistration sso = ClientRegistrations.fromIssuerLocation(issuer)
        .registrationId("company-sso")
        .clientId(ssoClientId)
        .clientSecret(ssoSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile")
        .build();

    ClientRegistration google = CommonOAuth2Provider.GOOGLE
        .getBuilder("google")
        .clientId(googleClientId)
        .clientSecret(googleSecret)
        .scope("openid", "profile", "email")
        .build();

    return new InMemoryClientRegistrationRepository(sso, google);
}
~~~

This example replaces the earlier repository beans. To use it, import the corresponding classes from the examples above and add the four <code>app.google.*</code>/<code>app.oidc.*</code> properties with secure values.

When using default <code>oauth2Login()</code>, the application can initiate login via:

~~~text
/oauth2/authorization/company-sso
/oauth2/authorization/google
~~~

Default callbacks:

~~~text
/login/oauth2/code/company-sso
/login/oauth2/code/google
~~~

The crucial requirement is that **<code>registrationId</code> must be unique** within the same repository. Do not create two registrations with the same ID expecting Spring to pick one based on hostname or issuer. If multiple providers/tenants share one app, you must select the right registration from the start of the flow and validate tokens against the chosen provider.

### 5.1. Looking Up `ClientRegistration` in Java

In another component of the application, inject the interface:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Service
public class ProviderInfoService {
    private final ClientRegistrationRepository registrations;

    public ProviderInfoService(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String authorizationEndpoint(String registrationId) {
        ClientRegistration registration =
                registrations.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown registrationId: " + registrationId);
        }

        return registration.getProviderDetails().getAuthorizationUri();
    }
}
~~~

This example only shows how to retrieve provider metadata. It does not perform an OAuth Authorization Request. In actual login-handling code, let Spring Security use the OAuth2 authorization request resolver rather than manually concatenating URLs missing <code>state</code>, PKCE, or other security parameters.

### 5.2. Iterating Over Registrations

One feature of <code>InMemoryClientRegistrationRepository</code> is that it implements <code>Iterable&lt;ClientRegistration&gt;</code>. You can use this in components intentionally bound to this implementation:

~~~java
for (ClientRegistration registration : inMemoryRepository) {
    String id = registration.getRegistrationId();
    String displayName = registration.getClientName();
    // Use id and displayName to build login options.
}
~~~

In this example, <code>inMemoryRepository</code> is a variable of type <code>InMemoryClientRegistrationRepository</code>. The <code>ClientRegistrationRepository</code> interface itself **does not extend `Iterable`**, so do not assume all other implementations support iteration.

Never display <code>clientSecret</code> or any sensitive values in a provider selection UI.

## 6. Relationship with Spring Boot Auto-Configuration

When declaring the familiar configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            client-id: some-client-id
            client-secret: some-client-secret
            scope: [openid, profile]
        provider:
          training:
            issuer-uri: https://login.example.org/realms/training
~~~

Spring Boot can auto-create the repository from these properties when dependencies and auto-configuration conditions match.

When the application **defines its own <code>ClientRegistrationRepository</code> bean**, auto-configuration normally **backs off** in favor of the application-supplied bean. That means Boot does not automatically merge the registrations from the YAML above into your Java repository.

| Configuration approach | Who creates `ClientRegistrationRepository`? | When is it suitable? |
|---|---|---|
| Only <code>spring.security.oauth2.client.*</code> | Spring Boot auto-configuration | Simple configuration, minimal Java code |
| Java bean returning <code>InMemoryClientRegistrationRepository</code> | Application | Need conditional logic, combining config sources, or custom builders |
| Java bean built from application-bound properties | Application | Want Java logic while still managing values in files/env |
| Custom repository backed by database/secret store | Application | Dynamic provider list, centralized administration, custom business requirements |

If you choose Java configuration, proactively add **all** needed registrations to that bean or build an explicit combining strategy. Never assume declaring <code>registration.google</code> in YAML will automatically appear alongside Java registrations.

Similarly, avoid creating two <code>ClientRegistrationRepository</code> beans without clear qualifier/primary/resolution mechanisms. Spring Security components normally expect a single consistently chosen repository.

## 7. Can In-Memory Registrations Be Used in Production?

**Yes**, if the list of OAuth/OIDC Clients is known in advance, configuration is stable, and each application startup can rebuild all metadata cleanly. You do not need a database just to store two or three fixed `ClientRegistration`s.

However, understand the limitations:

- **Lifecycle:** the repository is rebuilt at application startup; it does not provide runtime add/remove registration operations under its public API contract.
- **Multi-instance deployment:** each instance has its own repository. Ensure consistent configuration across instances and environments.
- **Credential changes:** when a client secret changes, an appropriate config refresh/redeploy strategy is needed. The repository does not watch the secret store automatically.
- **Startup discovery:** if built from an issuer and the library needs to fetch metadata, the application may depend on OP reachability at startup.
- **Sensitive data:** <code>ClientRegistration</code> may hold client secrets in memory. Never log the entire object, return it via REST APIs, or hardcode secrets in source code.

In-memory here is not an inherent security flaw. The choice depends on provider update frequency, operations, availability, and secret management requirements.

### 7.1. Distinguishing Registration Storage from Token Storage

~~~mermaid
flowchart LR
    A["ClientRegistrationRepository"] --> B["Client and provider metadata"]
    C["OAuth2AuthorizedClientService / Repository"] --> D["Access token / refresh token per principal"]
    E["HTTP Session / SecurityContext"] --> F["Login state and authentication"]
    B --> G["Used when building authorization / token requests"]
    D --> H["Used when Client calls protected APIs"]
    F --> I["Used when identifying the signed-in user"]
~~~

<code>InMemoryOAuth2AuthorizedClientService</code> is a **completely different** class from <code>InMemoryClientRegistrationRepository</code>. The first handles storing authorized clients/tokens per principal and registration ID; the second stores Client definitions. Do not assume tokens are shared across instances just because they share the same provider registration.

If a server-side application runs multiple instances and needs shared login state, consider session stores, token persistence, and related components per your architecture, independent of the metadata repository choice.

## 8. Important Configuration Details

### 8.1. Where Is `registrationId` Used?

<code>registrationId</code> is an internal key used to:

1. Select the provider from the login initiation URL: <code>/oauth2/authorization/{registrationId}</code>.
2. Wire the default callback: <code>/login/oauth2/code/{registrationId}</code>.
3. Look up `ClientRegistration` for token exchange and authorized client handling.
4. Select the right provider configuration when the application integrates multiple OAuth 2.0/OIDC Clients.

The ID name does not have to match the <code>clientId</code> issued by the provider. For example, internally it may be called <code>company-sso</code> while <code>clientId</code> is <code>hr-portal-prod-01</code>.

### 8.2. Redirect URI and Reverse Proxy

By default, Spring Security typically uses the URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

In a reverse proxy environment, <code>{baseUrl}</code> must reflect the **external** hostname, scheme, and port. If the application actually runs on HTTPS while the backend sees only HTTP and an internal host, the redirect URI may mismatch what is registered at the OP.

Configure proxy/forwarded headers to match your deployment model and trust forwarded headers only from trusted proxies. Never modify the provider registration to allow broad wildcard redirect URIs as a workaround for callback errors.

### 8.3. Scopes and Distinguishing OAuth 2.0 from OIDC

In OIDC, scopes must include <code>openid</code>. Without <code>openid</code>, it may be regular OAuth 2.0 Login and the application should not expect an ID Token.

With OIDC, issuer/JWKS and ID Token validation are critical. Configuring the provider with <code>fromIssuerLocation</code> fetches trusted metadata and lets the library perform the corresponding checks. If declaring endpoints manually, ensure complete validation is configured.

Other scopes such as <code>profile</code> and <code>email</code> merely request additional details; actual claim values depend on the provider, consent, and grant policy.

### 8.4. Client Authentication and PKCE

A confidential web Client typically uses <code>CLIENT_SECRET_BASIC</code> or another method registered at the provider. Public Clients cannot keep a client secret confidential long-term and usually use <code>ClientAuthenticationMethod.NONE</code>.

Authorization Code + **PKCE S256** binds the authorization code to the client that initiated the request. For public Clients, Spring Security has appropriate PKCE support; for confidential Clients, PKCE can be explicitly enabled via an authorization request customizer when supported by the Authorization Server.

Never expose a client secret in browser JavaScript, login URLs, or logs. Never treat PKCE as a replacement for validating <code>state</code>, issuer, ID Token, or token security policies.

## 9. Common Errors When Manually Creating the Repository

| Symptom | Common cause | Resolution |
|---|---|---|
| <code>/oauth2/authorization/training</code> does not recognize provider | Bean lacks <code>training</code>, registrationId casing differs, or OAuth2 Login is not configured | Check registration ID, injected bean, and <code>oauth2Login()</code> |
| Spring Boot properties define a provider, yet Java repository does not see it | Custom bean prevents auto-config from creating/merging repository from YAML | Explicitly build that registration in Java or stick to one consistent config approach |
| Bean creation fails at startup | <code>fromIssuerLocation</code> cannot reach discovery, issuer metadata mismatches, TLS/DNS error | Check public issuer, network connectivity, certificates, and metadata |
| Provider rejects redirect URI | Callback URI has wrong scheme/host/path or is unregistered | Compare actual redirect URI with OP; check reverse proxy |
| Token endpoint returns <code>invalid_client</code> | Wrong Client ID/secret or mismatched authentication method | Check registration at OP, environment, and Client authentication setup |
| Authorization code received, yet token exchange fails | Misconfigured grant/callback/PKCE, expired or reused code | Check flow and Spring Security components managing it |
| OAuth login succeeds, yet no <code>OidcUser</code> received | Missing <code>openid</code> scope or provider does not issue OIDC ID Tokens | Verify OP supports OIDC and scope is valid |
| Invalid ID Token signature or issuer | Wrong metadata/JWKS, token from another provider, or mismatched claims | Use official issuer, that issuer's JWKS, and standard validation |
| Ambiguous bean error | Multiple `ClientRegistrationRepository` beans without selection mechanism | Clean up bean definitions; ensure components receive the intended repository |
| Multiple instances have inconsistent user state | Confusing metadata repository with session/token persistence | Design dedicated session/authorized client persistence |

### 9.1. Diagnosing Along the Dependency Chain

When users cannot sign in, trace step by step:

~~~text
Valid registrationId?
    → ClientRegistration found?
        → Correct authorizationUri/tokenUri/redirectUri?
            → OP accepts Client?
                → Authorization Code Flow succeeds?
                    → Valid ID Token (for OIDC)?
                        → Authentication/session completed?
~~~

Never print full client secrets, access tokens, refresh tokens, ID Tokens, or authorization codes to logs for debugging. A much more useful approach is logging error type, registration ID, timestamp, which endpoint failed, and a safe correlation ID.

## 10. Practice Exercises

### Exercise 1 — One OIDC Provider with Java Config

Suppose an OP exposes issuer <code>https://login.example.org/realms/training</code> and has registered Client ID <code>training-web</code>:

1. Create a Spring Boot application with the OAuth2 Client starter.
2. Declare the issuer, Client ID, and secret in application-specific properties/a secret store.
3. Build a <code>ClientRegistration</code> using <code>ClientRegistrations.fromIssuerLocation</code> with ID <code>training</code>.
4. Return <code>new InMemoryClientRegistrationRepository(training)</code> from a Java bean.
5. Enable <code>oauth2Login()</code> and visit <code>/oauth2/authorization/training</code>.
6. Compare the outgoing redirect URI with the redirect URI registered at the OP, and verify the ID Token is validated by the library.

Key takeaway: <code>ClientRegistrationRepository</code> participates from **provider selection** through token exchange configuration; it does not perform user authentication itself.

### Exercise 2 — Two Providers

Add a second <code>ClientRegistration</code> with registration ID <code>google</code> or another OP. Use a single repository:

~~~java
return new InMemoryClientRegistrationRepository(training, secondProvider);
~~~

Observe the two login initiation URLs, two callbacks, and how the application selects the right registration ID. Do not share the same <code>clientSecret</code> across OPs unless officially provisioned that way; each provider needs its own credentials/registration.

### Exercise 3 — Find the Configuration Bug

A team creates a Java repository containing only <code>company-sso</code>, while also declaring <code>spring.security.oauth2.client.registration.google</code> in YAML. The URL <code>/oauth2/authorization/google</code> does not work.

**Explanation:** The application-defined repository is the source Spring Security uses to look up registrations; YAML is not automatically merged into that bean. You must either build/add the <code>google</code> registration in the Java repository, or standardize on Spring Boot auto-configuration if custom Java logic is unnecessary.

### Exercise 4 — Distinguish Data Responsibilities

Given three requirements:

1. Store Google's <code>clientId</code>, <code>authorizationUri</code>, and <code>scope</code>.
2. Store access tokens/refresh tokens issued to logged-in users.
3. Store HTTP session state after user authentication.

**Solution:** (1) belongs to <code>ClientRegistrationRepository</code>; (2) belongs to <code>OAuth2AuthorizedClientService</code> or <code>OAuth2AuthorizedClientRepository</code> depending on the flow; (3) belongs to the corresponding session and `SecurityContext` strategy. Do not use <code>InMemoryClientRegistrationRepository</code> to handle all three.

## 11. Key Takeaways

- <code>ClientRegistration</code> describes **one** OAuth 2.0/OIDC Client; <code>ClientRegistrationRepository</code> enables looking up registrations by **<code>registrationId</code>**.
- <code>InMemoryClientRegistrationRepository</code> holds registrations in memory and supports both lookup and iteration, suited for relatively static provider configurations.
- Registrations can be built with **<code>ClientRegistrations.fromIssuerLocation(...)</code>** for OIDC with discovery, **<code>ClientRegistration.withRegistrationId(...)</code>** for manual endpoint configuration, or **<code>CommonOAuth2Provider</code>** for common providers.
- When you supply your own repository bean, Spring Boot normally backs off from auto-configuration. Registrations in YAML **are not automatically merged** into your Java bean.
- The metadata repository **does not store tokens or sessions**. Authorized client persistence, HTTP sessions, client secret management, TLS, issuer validation, and PKCE are separate responsibilities that must be designed properly.

### Further Reading

- **Spring Security Reference — OAuth2 Client / OAuth2 Login:** how to configure OAuth2 Client, `ClientRegistrationRepository`, authorization requests, and login.
- **Spring Security Java API:** <code>ClientRegistration</code>, <code>ClientRegistrations</code>, <code>ClientRegistrationRepository</code>, <code>InMemoryClientRegistrationRepository</code>, and <code>CommonOAuth2Provider</code>.
- **Spring Boot Reference — OAuth2 Client:** property mappings and auto-configuration behavior.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Client Registration, Authorization Code Grant, and Client authentication.
- **OpenID Connect Discovery 1.0** and **OpenID Connect Core 1.0:** issuer, discovery metadata, and ID Token verification.
