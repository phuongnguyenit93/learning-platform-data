# 22.1. Determining Grants Supported by Spring Security by Version

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, the question "Does Spring Security support grant X?" sounds simple, yet actually requires checking multiple layers. A grant may be defined in an RFC, supported by the Authorization Server (AS), have a provider class in a given Spring Security version, yet **not be enabled** in the application's `OAuth2AuthorizedClientManager`.

This matters even more for **extension grants** such as **JWT Bearer** or **Token Exchange**, because the APIs and configuration approach change across versions. An example written for Spring Security 6.5 might not compile in 6.1; an older example using `password()` still exists in 6.5 but is no longer suitable for Spring Security 7.

After this lesson, you will be able to:

1. Distinguish between **a grant defined by the protocol**, **accepted by the AS**, **having a Spring Security implementation**, and **enabled in the application**.
2. Identify the exact running `spring-security-oauth2-client` version without confusing it with the Spring Boot or Spring Framework version.
3. Read versioned Reference Documentation, Javadoc, `@Since`, `@Deprecated`, release notes, and the corresponding source code.
4. Use a version milestone table for `authorization_code`, `refresh_token`, `client_credentials`, `password`, `jwt-bearer`, and `token-exchange`.
5. Explain the differences between grant types, client authentication methods, and supplementary features such as PKCE/OIDC.
6. Understand `OAuth2AuthorizedClientProviderBuilder`, `ReactiveOAuth2AuthorizedClientProviderBuilder`, and how to add extension providers.
7. Distinguish between **Servlet** and **Reactive/WebFlux** support, along with how to select the appropriate manager.
8. Handle upgrading from Spring Security 5.x/6.x to 7.x without retaining removed grants.
9. Verify support for a new grant without inferring it merely from YAML accepting the `authorization-grant-type` string.
10. Design integration tests that prove the grant actually works with the configured Authorization Server.

## 1. Why Does "Supporting a Grant" Have Multiple Meanings?

Suppose you are asked to integrate a service with an Authorization Server using `urn:ietf:params:oauth:grant-type:token-exchange`. A developer tries adding:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          downstream-api:
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
~~~

The application starts without errors. Can we conclude that Token Exchange is already working?

**Not yet.** The binder accepting a custom `AuthorizationGrantType` only confirms **one part of configuration**. It does not prove that:

- The dependency has the appropriate implementation.
- The manager already has a provider that executes Token Exchange.
- The provider can find a valid `subject_token`.
- The token response client sends the request in the right format.
- The Authorization Server supports Token Exchange for this client.
- The issued token has the appropriate audience/scope for the Resource Server.
- Success/failure outcomes are stored and handled properly.

You must evaluate these sequentially.

### 1.1. Four Layers to Confirm

| Layer | Question to Answer | Evidence |
|---|---|---|
| **A — OAuth protocol** | Is grant X defined in a specification or by the AS? | RFC/spec or provider documentation |
| **B — Authorization Server** | Does the AS support the grant and **allow this client** to use it? | Metadata, client registration, docs, token endpoint |
| **C — Spring Security library** | Does the library version include the corresponding provider/token response client? | Version-matched Javadoc, release notes, dependency |
| **D — Runtime configuration** | Does the application wire the provider/manager, context, and store properly? | Bean configuration, startup, integration test |

**All four layers must align** before you can say "grant X is supported in the system".

### 1.2. Decision Flowchart

~~~mermaid
flowchart TD
    A["Need grant X"] --> B{"Defined by Spec / AS?"}
    B -->|No| C["Cannot arbitrarily use an undefined grant"]
    B -->|Yes| D{"Does AS allow client to use grant?"}
    D -->|No| E["Fix policy/registration at AS"]
    D -->|Yes| F{"Does Spring version have provider?"}
    F -->|Yes| G{"Is provider enabled in manager?"}
    F -->|No| H["Upgrade version or write extension provider"]
    G -->|No| I["Register/wire provider"]
    G -->|Yes| J{"Context, assertion/token, and API match?"}
    J -->|No| K["Add token resolver / response client"]
    J -->|Yes| L["Integration test with AS and API"]
    L --> M{"Token endpoint and Resource Server accept?"}
    M -->|Yes| N["Grant works in the system"]
    M -->|No| O["Diagnose client auth, audience, scope, policy"]
~~~

## 2. What Is a Grant Type?

An **authorization grant** is a mechanism for an OAuth client to obtain an access token from an Authorization Server or obtain/update the corresponding authorization.

Familiar values include:

~~~text
authorization_code
refresh_token
client_credentials
password
urn:ietf:params:oauth:grant-type:jwt-bearer
urn:ietf:params:oauth:grant-type:token-exchange
~~~

However, these values have very different support lifecycles.

### 2.1. Core Grants and Extension Grants

Three mechanisms commonly encountered in modern Spring Security applications:

- `authorization_code`: the user interacts via the authorization endpoint; the client exchanges the authorization code for tokens.
- `refresh_token`: when a previously issued refresh token is present, the client requests a new token.
- `client_credentials`: the client/service uses its own identity to request an access token.

Extension grants:

- `urn:ietf:params:oauth:grant-type:jwt-bearer`: uses a JWT assertion as an authorization grant according to the corresponding profile.
- `urn:ietf:params:oauth:grant-type:token-exchange`: exchanges a security token to obtain a token intended for a different purpose/resource according to AS policy.
- Other grants such as device authorization, CIBA, or provider-specific grants **must be verified per version**; do not assume Spring Security OAuth2 Client includes a built-in provider simply because an RFC exists.

### 2.2. `password`: Historically Supported, No Longer Suitable

The Resource Owner Password Credentials grant (`password`) allows a client to directly receive the resource owner's username/password and exchange them for a token.

This design does not align with modern OAuth security guidance. **Spring Security deprecated the password grant API in the 5.8 line and removed support in 7.0**.

That creates a major difference between an older 5.8/6.5 codebase and a new 7.x application.

### 2.3. Refresh Token Is a Renewal Grant, Not a Standalone Login Flow

To use `refresh_token`, the client typically must already have an `OAuth2AuthorizedClient` containing a refresh token previously issued by the AS.

Having the `refreshToken()` provider present does not guarantee the AS issues a refresh token initially. If the client does not yet have R1, this provider will not fabricate a fake refresh token.

### 2.4. OpenID Connect Is Not a New Grant Type

OIDC typically uses the Authorization Code flow with the `openid` scope; the ID token adds an End-User authentication layer.

Therefore:

~~~text
authorization_code + openid
~~~

is different from:

~~~text
grant_type = oidc
~~~

There is no default `AuthorizationGrantType("oidc")` supported by the manager.

### 2.5. PKCE Is Also Not a Separate Grant

PKCE is a mechanism for protecting the Authorization Code flow using a code verifier/challenge. It does not add an OAuth grant type named `pkce`.

When asking whether a version supports PKCE, look at Authorization Code features, resolvers, and client registration—do not look for `OAuth2AuthorizedClientProviderBuilder.pkce()`.

## 3. First, Know the Exact Library Version

An application may declare:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

However, **the Spring Boot version is not identical to the Spring Security version**. Boot normally manages a compatible set of dependency versions; an application may override versions or pull in transitive dependencies that cause differences.

### 3.1. Numbers to Record

When investigating, you should capture:

~~~text
Java version:
Spring Boot version:
Spring Framework version:
spring-security-config version:
spring-security-oauth2-client version:
Spring Security reference doc version:
Servlet or Reactive stack:
Authorization Server product/version:
~~~

Do not compare based solely on "Spring Boot 3.x" and conclude which grants exist. Every `@Since` in Spring Security is keyed to **Spring Security**, not Boot.

### 3.2. Maven: Inspecting the Dependency Tree

Run in a real Maven project when checking:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-oauth2-client
~~~

Or inspect related dependencies:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

The output shows the `spring-security-oauth2-client` version resolved by Maven. When dependency management or overrides exist, this is more meaningful than merely reading the starter version in source.

### 3.3. Maven: Inspecting the Effective POM

~~~bash
mvn help:effective-pom
~~~

The effective POM shows the dependency management and properties merged by Maven across parent/BOM/profiles.

If you need to diagnose dependency versions, do not modify the BOM or force a version just to make a snippet compile; you must evaluate overall compatibility across Spring Boot/Spring Framework/Spring Security.

### 3.4. Gradle: Inspecting dependencyInsight

~~~bash
./gradlew dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

On Windows, you can use:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

To view the dependency group:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

If the project has multiple modules, run the task on the module that actually contains the OAuth2 client. Gradle's output shows the dependency selected after conflict resolution/platform constraints.

### 3.5. Identifying Dependencies from the Wrong Package

There are modules with similar names:

~~~text
spring-security-oauth2-client
spring-security-oauth2-resource-server
spring-security-oauth2-jose
spring-security-oauth2-authorization-server (depending on project)
~~~

- **OAuth2 Client**: requests, stores, and uses tokens to call APIs.
- **Resource Server**: validates tokens sent to APIs.
- **Authorization Server**: issues tokens and manages grants as an AS.

**Having a grant class in Authorization Server does not prove OAuth2 Client has a corresponding provider**. You must verify the right module and package.

## 4. Key Version Milestone Table

The milestones below are **feature/API milestones**, not a promise that any particular configuration is enabled by default. For real projects, always cross-check the Javadoc for **the exact patch/minor version in use**.

| Spring Security Line | Key Points When Evaluating Grants |
|---|---|
| **5.2** | `OAuth2AuthorizedClientProviderBuilder` and its reactive counterpart have existed since 5.2; the builder supports `authorization_code`, `refresh_token`, `client_credentials`, and `password` in the corresponding 5.x releases |
| **5.5** | `JwtBearerOAuth2AuthorizedClientProvider` is present from 5.5 (per Javadoc `Since`); the JWT Bearer grant is an extension and requires configuration |
| **5.8** | The `password()` API begins to be **deprecated**, following OAuth Security Best Current Practice guidance |
| **6.2** | Component-based configuration can pick up `OAuth2AuthorizedClientProvider` beans to add extensions to the default manager, subject to auto-configuration conditions |
| **6.3** | `TokenExchangeOAuth2AuthorizedClientProvider` and its reactive counterpart are introduced (Javadoc `Since: 6.3`) |
| **6.5** | Has the three common grants, JWT Bearer, and Token Exchange providers; `password` still appears but is deprecated/for removal |
| **7.0** | **Removes the password grant**; the main builder retains `authorization_code`, `refresh_token`, `client_credentials`, with the `provider(...)` hook for extensions |

**How to read this:** do not interpret "6.5 supports password" as a recommendation to implement a new password grant. In 6.5, this API is already deprecated and slated for removal.

### 4.1. Evolution Diagram

~~~mermaid
timeline
    title Spring Security OAuth2 Client API Milestones
    5.2 : AuthorizedClientProviderBuilder
        : authorization_code / refresh_token / client_credentials / password
    5.5 : JwtBearerOAuth2AuthorizedClientProvider
    5.8 : password grant API deprecated
    6.2 : More convenient provider bean integration
    6.3 : TokenExchangeOAuth2AuthorizedClientProvider
    6.5 : password still present but deprecated
    7.0 : password grant removed
~~~

The table and timeline help identify implementation direction, but **specific classes/methods must be verified against the actual artifact**.

## 5. Grants by Version Line

To avoid confusing the three states "API exists / enabled by default / must be configured", the table uses these markers:

- **API available**: an implementation/provider exists in the corresponding version line.
- **Extension**: an API exists, though the provider typically must be declared appropriately.
- **Deprecated**: the API is still present, but should not be used and may be removed.
- **Removed**: no standard supporting API exists in that line.

| Grant | 5.8 | 6.2 | 6.3–6.5 | 7.0 |
|---|---|---|---|---|
| `authorization_code` | API available | API available | API available | API available |
| `refresh_token` | API available | API available | API available | API available |
| `client_credentials` | API available | API available | API available | API available |
| `password` | Deprecated | Deprecated | Deprecated | **Removed** |
| `jwt-bearer` | Extension with provider | Extension with provider | Extension with provider | Extension with provider |
| `token-exchange` | No built-in provider until 6.3 | No built-in provider until 6.3 | Extension with provider | Extension with provider |
| AS-specific grant | Needs extension if unavailable | Needs extension if unavailable | Needs extension if unavailable | Needs extension if unavailable |

**Important note:** the `token-exchange` row refers to **Spring Security's built-in provider**. An application on an older version can still write a custom provider or use another library if the AS supports it; that does not make `TokenExchangeOAuth2AuthorizedClientProvider` exist before `Since: 6.3`.

### 5.1. Why Doesn't the Table Say "Enabled by Default"?

"Enabled by default" depends on:

- Servlet vs. Reactive.
- `HttpSecurity.oauth2Client()`, `oauth2Login()`, or the WebFlux DSL.
- Whether the manager is auto-created or defined as a custom application bean.
- Whether the provider chain is replaced by the application.
- Whether context tokens/assertions are supplied.
- Whether the extension part is registered.

Merely having a class on the classpath **does not guarantee the grant works**.

### 5.2. Version 7.x Requires Separate Checks

When upgrading to Spring Security 7.x, the `password()` API no longer exists. If code still calls:

~~~java
OAuth2AuthorizedClientProviderBuilder.builder()
        .password()
        .build();
~~~

that is one of the places requiring migration. Do not try to replace it with a workaround that collects the user's username/password to emulate ROPC.

## 6. High-Trust Sources for Determining Grant Support

Follow this priority order as needed:

1. **The actual dependency** resolved by Maven/Gradle.
2. **Versioned Spring Security Reference Documentation** matching major/minor.
3. **Version-matched Javadoc**, especially `Since`, `Deprecated`, and API signatures.
4. **What's New / Migration Guide** for major/minor upgrades.
5. **Source/jar** of the exact artifact when documentation leaves behavior unclear.
6. **Integration tests** against the Authorization Server used by the project.

### 6.1. Clearly Version-Labeled Documentation

Examples of official paths:

- [Spring Security 6.5 — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Security 6.5 — Authorization Grant Support](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorization-grants.html)
- [Spring Security 7.0 — OAuth2 Client](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/client/index.html)
- [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)

Do not read an unversioned `/reference/servlet/oauth2/client/` page and assume it describes the 5.8 version you are running.

### 6.2. Builder Javadoc by Version

- [6.5 — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [7.0 — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [6.5 — ReactiveOAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientProviderBuilder.html)
- [7.0 — ReactiveOAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientProviderBuilder.html)

Comparing the methods across the two versions shows `password()` present and deprecated in 6.5, but absent from the 7.0 builder.

### 6.3. Extension Provider `Since` Javadoc

- [JWT Bearer provider — Since 5.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/JwtBearerOAuth2AuthorizedClientProvider.html)
- [Token Exchange provider — Since 6.3](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/TokenExchangeOAuth2AuthorizedClientProvider.html)
- [Reactive Token Exchange provider — Since 6.3](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/TokenExchangeReactiveOAuth2AuthorizedClientProvider.html)

`Since` only proves **the API class has existed since that version**. It does not prove Spring Boot auto-wires the bean or that the Authorization Server accepts the grant.

### 6.4. What If You Encounter Older Documentation?

A blog post written for Spring Security 5.3 may use older APIs or implement an extension manually. A post for 6.5 might still use `password()` despite deprecation.

When referencing articles:

- Record the date and version of the example.
- Check the current packages/imports and classes.
- Cross-check methods against the actual Javadoc.
- Consult the migration guide if copying code across major versions.
- Do not treat code from a different snapshot version as official guidance for production.

## 7. Reading `OAuth2AuthorizedClientProviderBuilder` Properly

In the Servlet stack, Spring Security provides:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder
~~~

With Spring Security 6.5 and 7.0, the three core grants are commonly selected:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();
~~~

This creates a `DelegatingOAuth2AuthorizedClientProvider` containing the corresponding providers.

### 7.1. What the Builder Supports Is Not What the Manager Has Enabled

Having a `clientCredentials()` method on the builder means the library version provides a way to configure this provider. If the actual application constructs its manager with only:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build();
~~~

then this custom manager **does not automatically include `client_credentials`**, even though the provider class is on the classpath.

### 7.2. The `provider(...)` Extension Hook

In versions supporting the builder, you can add an `OAuth2AuthorizedClientProvider` implementation:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(customExtensionProvider)
                .build();
~~~

In this example, `customExtensionProvider` must be an actual provider object created using the API of the version in use.

This is how extension grants are plugged into the manager; not every grant needs a dedicated builder method like `tokenExchange()`.

### 7.3. Finding the Class Is Not Enough to Know Token Requests Will Work

You also need to inspect:

- The `OAuth2AccessTokenResponseClient` corresponding to the grant.
- Token request converters / header converters.
- Assertion / subject token resolvers.
- The client authentication method.
- Error response parsing.
- The manager's success/failure handlers.

A provider that is present but lacks a valid assertion can still fail to authorize.

## 8. Spring Security 6.5: Core Grants

### 8.1. `authorization_code`

Suitable for interactive browser logins or corresponding Authorization Code flows.

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

`authorization_code` requires an authorization endpoint, redirect/callback handling, and a matching token endpoint. In OIDC, `openid` triggers the ID token request and OIDC validations.

Do not treat `OAuth2AuthorizedClientManager.authorize(...)` as an API that can open a browser on its own inside a background job.

### 8.2. `refresh_token`

The `refreshToken()` provider can request a new access token when a stored refresh token exists and refresh conditions are met.

Not every AS issues a refresh token after Authorization Code. Without R1, the provider will not create R1 on its own.

When a refresh response contains no new refresh token, the client normally retains the old refresh token; if the AS issues R2, R1 is replaced by R2.

### 8.3. `client_credentials`

Used for machine-to-machine service identity:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

The client can request an initial token and request a new token upon expiration. No End-User OIDC Login or ID token is required.

### 8.4. Having the Provider API Does Not Mean the AS Allows It

If the AS does not allow the `reporting-service` client to use `client_credentials`, the token endpoint may return `unauthorized_client`. Modifying providers in Spring Security does not replace registering the grant at the AS.

## 9. Extension Grant: JWT Bearer

### 9.1. Do Not Confuse with JWT Client Authentication

This is one of the most common conceptual mistakes.

| Concept | What Is the JWT Used For? |
|---|---|
| **JWT Bearer authorization grant** | The JWT assertion is the grant used to request an access token |
| **`private_key_jwt` client authentication** | The JWT assertion proves the identity of the **OAuth client** at the token endpoint |
| **OIDC ID token** | Proves End-User authentication results to the Relying Party |
| **JWT access token** | Credential validated by the Resource Server based on issuer/audience/scope |

An application may use the `authorization_code` grant while using `private_key_jwt` for client authentication. That does **not** turn the grant into `jwt-bearer`.

### 9.2. Grant URN

Value of the JWT Bearer grant:

~~~text
urn:ietf:params:oauth:grant-type:jwt-bearer
~~~

Conceptual token request example:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=<JWT_ASSERTION>
~~~

Separate client authentication may still be required per the AS contract. Do not log the raw assertion because it can be a sensitive credential.

### 9.3. Provider Available Since 5.5

Class:

~~~java
org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider
~~~

Javadoc notes **`Since: 5.5`**. This means the class exists in 5.5 and later compatible releases, yet **is not automatically enabled in every manager**.

### 9.4. Example Registration Configuration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          jwt-delegation:
            provider: company-auth
            client-id: ${JWT_GRANT_CLIENT_ID}
            client-secret: ${JWT_GRANT_CLIENT_SECRET}
            authorization-grant-type: urn:ietf:params:oauth:grant-type:jwt-bearer
            scope:
              - orders.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

This is a hypothetical client configuration. The AS must permit the JWT Bearer grant and agree on the assertion's issuer, audience, signature, and subject.

### 9.5. Adding the Provider to the Manager

In a Servlet app, you can configure:

~~~java
import org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(new JwtBearerOAuth2AuthorizedClientProvider())
                .build();
~~~

This only adds grant-handling capability to the chain. The client must have a valid JWT assertion, and the token response client/provider must know where to obtain it.

In certain scenarios, `JwtBearerOAuth2AuthorizedClientProvider` obtains the JWT assertion from an appropriate principal (for example `JwtAuthenticationToken`). If the JWT comes from another source, configure `setJwtAssertionResolver(...)` per the Javadoc of the version in use.

Do not arbitrarily use a user's ID token as an assertion unless permitted by the AS.

### 9.6. Distinguishing Grant and Audience

A JWT assertion may be issued for a very specific purpose. The AS only accepts it when signature, issuer, subject, audience, expiry, and policy match.

Do not simply attach an arbitrary existing JWT to the `assertion` parameter hoping the AS will exchange it for an access token for any API.

## 10. Extension Grant: Token Exchange

### 10.1. Meaning

Token Exchange under RFC 8693 allows a client to send a **subject token** and optionally an **actor token** to request a new token under AS constraints.

Architectural example:

~~~text
Browser / Alice
   |
   v
Gateway (has user access token A1)
   |
   | Token Exchange request
   v
Authorization Server
   |
   | access token B1 for Payments API
   v
Gateway -> Payments API
~~~

The new token does not automatically share the same scopes/audience as the original token. The AS decides what permissions are exchanged and enforces delegation/impersonation policy.

### 10.2. Integration Milestone in Spring Security

`TokenExchangeOAuth2AuthorizedClientProvider` has Javadoc **`Since: 6.3`**. Its reactive counterpart also has `Since: 6.3`.

Therefore:

- On Spring Security 6.1/6.2: do not rely on this built-in provider class.
- From 6.3 onward: you can use the provider supplied by Spring Security.
- Spring Security 6.5 and 7.0: the appropriate provider can be used when wired properly.

### 10.3. Grant URN

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

A conceptual token request may include:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&subject_token=<SUBJECT_TOKEN>&subject_token_type=urn:ietf:params:oauth:token-type:access_token
~~~

Client authentication, requested token type, audience/resource, scope, and actor token depend on the specific contract with the AS.

### 10.4. Registration Configuration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          payments-exchange:
            provider: company-auth
            client-id: ${EXCHANGE_CLIENT_ID}
            client-secret: ${EXCHANGE_CLIENT_SECRET}
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            scope:
              - payments.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

Here `payments.read` is only an illustrative scope. The AS must allow the exchange and issue an access token suitable for Payments API.

### 10.5. Adding the Token Exchange Provider (6.3+)

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;

TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
        new TokenExchangeOAuth2AuthorizedClientProvider();

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(exchangeProvider)
                .build();
~~~

**Configuring the provider does not complete the entire use case.** You must also ensure a valid `subject_token`, subject/actor resolvers, and an appropriate token response client.

### 10.6. Subject Token Resolver

Per the Javadoc of supported versions, the Token Exchange provider has extension points such as:

~~~java
exchangeProvider.setSubjectTokenResolver(context -> {
    // Retrieve the already-verified source token from a trusted context.
    // Return an appropriate OAuth2Token per the contract.
    throw new UnsupportedOperationException(
            "Configure a trusted subject token resolver");
});
~~~

This snippet only sketches the API, not a production-ready resolver.

In official examples, the provider can obtain the token from a `JwtAuthenticationToken` principal in suitable contexts. Do not let the browser pass an arbitrary `subject_token` for the backend to exchange using the client's credentials.

### 10.7. Actor Token and Delegation

An actor token is not always present; some flows require representing an actor acting on behalf of a subject.

When using token exchange:

- Identify who the subject is.
- Identify who the actor is if needed.
- Determine the target resource/audience.
- Enforce policies against privilege escalation.
- Validate the new token at the Resource Server.
- Never log raw subject/actor tokens.

## 11. Component-Based Configuration Since Spring Security 6.2

This milestone is easy to misunderstand because it changed **how providers are wired**, not when every extension grant was invented.

Spring Security documentation from 6.2 onward describes declaring an `OAuth2AuthorizedClientProvider` bean to be automatically configured into the appropriate manager when the framework manages the default manager.

### 11.1. JWT Bearer Bean Example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;

@Configuration
public class ExtensionGrantConfiguration {

    @Bean
    OAuth2AuthorizedClientProvider jwtBearerProvider() {
        return new JwtBearerOAuth2AuthorizedClientProvider();
    }
}
~~~

In an appropriate Spring Security configuration, the provider bean is added to the default manager alongside commonly used grants.

### 11.2. Do Not Assume Every Custom Manager Collects Beans Automatically

If the application explicitly constructs:

~~~java
DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
~~~

then this manager only uses the provider you configured, unless the application explicitly collects/assembles other beans.

Therefore, the statement "since 6.2 you just declare a provider bean" must be understood **within the corresponding auto-configuration mechanism**, not as a rule for every custom manager.

### 11.3. Before 6.2

Without this convenient component-based mechanism, the explicit configuration steps are:

1. Create a composite `OAuth2AuthorizedClientProvider`.
2. Add the required core grants.
3. Add the extension provider using `provider(...)`.
4. Create/configure the `OAuth2AuthorizedClientManager`.
5. Set the provider chain on the manager.

Replacing the default manager while keeping only the extension grant can cause previously used `authorization_code`, `refresh_token`, or `client_credentials` grants to stop working.

## 12. Servlet Manager Example with Extension Grants

Configuration template for Spring Security **6.3+**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class ServletGrantConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider chain =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .provider(
                                new JwtBearerOAuth2AuthorizedClientProvider())
                        .provider(
                                new TokenExchangeOAuth2AuthorizedClientProvider())
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(chain);
        return manager;
    }
}
~~~

### 12.1. Conditions for the Example to Actually Run

- The Spring Security version includes the imported extension providers.
- `ClientRegistrationRepository` contains the corresponding registrations.
- The Token Exchange/JWT Bearer providers receive valid source assertions/tokens.
- The AS allows the registered grants and client authentication methods.
- The target Resource Server accepts the issued tokens.
- The authorized client repository/service persists state per appropriate principal.

### 12.2. Why Is `password()` Excluded?

In 6.5, `password()` is deprecated; in 7.0, the API is gone. This example configuration uses modern recommended grants and does not rely on ROPC.

### 12.3. Do Not Confuse Manager with Token Request Client

The manager orchestrates providers and authorized clients; each provider invokes an `OAuth2AccessTokenResponseClient` to interact with the token endpoint.

An extension grant may require its own token response client, especially when the AS expects custom parameters, headers, or response formats.

Merely adding an `AuthorizationGrantType` value without a provider and token response client is insufficient.

## 13. Servlet and Reactive Must Be Checked Separately

Spring Security has two major models:

| Aspect | Servlet | Reactive |
|---|---|---|
| Manager interface | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `authorize` result | `OAuth2AuthorizedClient` or `null` | `Mono<OAuth2AuthorizedClient>` |
| Provider interface | `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| Builder | `OAuth2AuthorizedClientProviderBuilder` | `ReactiveOAuth2AuthorizedClientProviderBuilder` |
| Web request | `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange` |
| Authorized client storage | `OAuth2AuthorizedClientRepository/Service` | `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` |
| HTTP client | `RestClient`, optionally WebClient on Servlet | `WebClient` |

### 13.1. Reactive Extension Providers

In Spring Security 6.5, classes include:

~~~java
org.springframework.security.oauth2.client.JwtBearerReactiveOAuth2AuthorizedClientProvider
org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider
~~~

The class names do not follow the exact Servlet naming pattern, because the `Reactive` suffix/segment is inserted mid-name.

### 13.2. Reactive Provider Builder

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.JwtBearerReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider;

ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(
                        new JwtBearerReactiveOAuth2AuthorizedClientProvider())
                .provider(
                        new TokenExchangeReactiveOAuth2AuthorizedClientProvider())
                .build();
~~~

**The reactive Token Exchange provider has existed since Spring Security 6.3.** This example requires a compatible version and must also be attached to a reactive manager.

### 13.3. Do Not Wrap a Servlet Provider in Reactor to "Simulate Reactive Support"

Architecturally wrong example:

~~~java
Mono.fromCallable(() -> servletProvider.authorize(context));
~~~

This does not turn a blocking HTTP token exchange into genuine non-blocking reactive I/O, nor does it satisfy the `ReactiveOAuth2AuthorizedClientProvider` contract.

If the application is WebFlux, use the reactive APIs and reactive token response clients.

### 13.4. Password Grant and Reactive

Spring Security 6.5 still has the password provider/reactive password provider APIs in deprecated status. In 7.0, the reactive builder also removes `password()`.

Therefore, migration plans must audit **both Servlet and Reactive call sites**, not just one builder.

## 14. Verifying a Grant Beyond Provider Javadoc

A provider can exist and still fail because **required input data is missing**.

For example, with Token Exchange:

~~~text
ClientRegistration:
  grantType = token-exchange

Provider:
  TokenExchangeOAuth2AuthorizedClientProvider exists

OAuth2AuthorizationContext:
  no subject token present

AS:
  supports token-exchange
~~~

Authorization will still fail. The provider needs a valid source token per its contract.

### 14.1. Checking Context Resolvers

- JWT Bearer: where does the JWT assertion come from?
- Token Exchange: where do the subject token/actor token come from?
- Authorization Code: where are browser callbacks, code/state/PKCE handled?
- Refresh Token: does the authorized client hold a refresh token?
- Client Credentials: what is the client authentication method at the token endpoint?

### 14.2. Checking the Token Response Client

In newer Spring Security versions, an extension grant may have a token response client built on `RestClient` or `WebClient`.

Do not use newly named token response client APIs against an older dependency version without checking Javadoc. A grant supported in 5.5 may use a different client implementation than in 6.5.

### 14.3. Client Authentication Is Distinct from Grant

Example:

~~~yaml
client-authentication-method: private_key_jwt
authorization-grant-type: authorization_code
~~~

This is **Authorization Code** with JWT client authentication. It does **not** use the JWT Bearer authorization grant.

Conversely:

~~~yaml
authorization-grant-type: urn:ietf:params:oauth:grant-type:jwt-bearer
client-authentication-method: client_secret_basic
~~~

this could be the JWT Bearer grant paired with HTTP Basic client authentication, if the AS permits it.

Table:

| Grant | Possible Client Authentication | Same Concept? |
|---|---|---|
| Authorization Code | `client_secret_basic`, `private_key_jwt`, mTLS, public client `none` | No |
| Client Credentials | `client_secret_basic`, `private_key_jwt`, mTLS | No |
| JWT Bearer grant | Depends on AS; may require separate client authentication | No |
| Token Exchange | Depends on AS; may require separate client authentication | No |

## 15. Checking Authorization Server Support

Even when Spring Security provides a provider, the AS can still return errors.

### 15.1. Metadata `grant_types_supported`

If the AS publishes OAuth Authorization Server Metadata, you might see:

~~~json
{
  "issuer": "https://id.example.com",
  "token_endpoint": "https://id.example.com/oauth2/token",
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials",
    "urn:ietf:params:oauth:grant-type:token-exchange"
  ]
}
~~~

This is **illustrative JSON**, not real provider output.

Metadata helps discover grants advertised by the AS, but remember:

- Not every AS lists all extensions in its metadata.
- Metadata does not prove a **specific client** is allowed to use a grant.
- The AS may require separate configuration or matching policies/audiences.
- AS documentation and integration tests are still required.

### 15.2. Client Registration at the AS

The AS may support Token Exchange generally yet reject client `employee-portal` because that client is not authorized.

Error example:

~~~json
{
  "error": "unauthorized_client"
}
~~~

You cannot fix this by adding `provider(new TokenExchangeOAuth2AuthorizedClientProvider())` when the issue lies in AS policy.

### 15.3. Errors to Distinguish

| Error | Likely Cause |
|---|---|
| `unsupported_grant_type` | AS does not recognize the grant, grant name is wrong, or endpoint/profile is not enabled |
| `unauthorized_client` | AS recognizes the grant, but the client is not permitted to use it |
| `invalid_client` | Client authentication failed |
| `invalid_grant` | Grant/assertion/subject token is invalid, expired, or unsuitable |
| `invalid_scope` | Requested scope is not allowed |
| HTTP 401/403 from Resource Server | Final access token is rejected or lacks permissions |

Do not conclude "Spring Security does not support the grant" simply because the token endpoint returned `invalid_client`.

## 16. Researching an Unfamiliar Grant: 10-Step Process

When encountering `urn:example:params:oauth:grant-type:custom-delegation`, follow this process:

1. **Record the exact grant value** per the protocol/AS; avoid mistyping the URN.
2. **Confirm the actual resolved dependency version** of `spring-security-oauth2-client`.
3. **Determine Servlet vs. Reactive**.
4. **Check that version's Javadoc** to see if a provider class exists.
5. **Check the builder** for a dedicated method or `provider(...)` hook.
6. **Check `Since`/`Deprecated`** and migration notes.
7. **Check the token response client, resolvers, and context requirements**.
8. **Verify the AS** supports the grant and authorizes the client to use it.
9. **Configure the provider/manager/repository properly** without dropping existing grants.
10. **Run integration tests** against a test AS tenant and Resource Server without logging real tokens.

### 16.1. Built-In Integration vs. Custom Extension Decision

~~~mermaid
flowchart TD
    A["Need extension grant X"] --> B{"Built-in provider in current version?"}
    B -->|Yes| C["Use existing provider"]
    B -->|No| D{"Can upgrade Spring Security compatibly?"}
    D -->|Yes| E["Perform controlled upgrade"]
    D -->|No| F["Design custom OAuth2AuthorizedClientProvider"]
    C --> G["Supply context/assertion/token resolver"]
    E --> G
    F --> G
    G --> H["AS policy + token endpoint integration test"]
    H --> I["Resource Server audience/scope validation"]
~~~

### 16.2. Do Not Ignore Spring Boot Compatibility

Upgrading Spring Security alone just to obtain a new provider can skew the dependency stack. You must verify the Spring Boot BOM, Spring Framework, Java baseline, and security configuration migrations.

Do not override versions piecemeal without a compatibility and testing plan.

## 17. Writing a Custom Extension Provider When No Built-In Exists

### 17.1. When Is It Needed?

It may be necessary when:

- The AS uses a genuinely custom grant.
- Your framework version does not provide a built-in provider.
- Compatibility requirements prevent upgrading versions.
- The grant requires a specialized token request/response format.

However, **writing your own provider is an option only after verifying** no suitable implementation exists. Managing token endpoints and credentials yourself expands the security bug surface.

### 17.2. The `OAuth2AuthorizedClientProvider` Contract

In Servlet:

~~~java
public interface OAuth2AuthorizedClientProvider {
    OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context);
}
~~~

This is a simplified signature illustrating the contract.

A custom provider must:

- Check whether the `ClientRegistration`'s grant matches what it supports.
- Return `null` when it cannot handle the grant/context—never fabricate dummy tokens.
- Obtain trusted input data from `OAuth2AuthorizationContext`.
- Call the token endpoint with proper client authentication.
- Parse/validate the response and build an appropriate `OAuth2AuthorizedClient`.
- Handle expiry/reauthorization and refresh when part of the contract.
- Protect token sources; never log assertions, access tokens, or client secrets.

### 17.3. Provider Pseudocode

~~~java
public final class CustomGrantProvider
        implements OAuth2AuthorizedClientProvider {

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context) {

        ClientRegistration registration =
                context.getClientRegistration();

        if (!"urn:example:grant:custom-delegation".equals(
                registration.getAuthorizationGrantType().getValue())) {
            return null;
        }

        // 1. Check current authorized client and expiry.
        // 2. Obtain subject/assertion from a trusted source.
        // 3. Call the token endpoint per the AS contract.
        // 4. Parse the token response.
        // 5. Return OAuth2AuthorizedClient with matching registration/principal.
        // Never create dummy tokens or log raw tokens.

        throw new UnsupportedOperationException(
                "Implement using the AS contract and token client");
    }
}
~~~

This is a **structural outline**, not a production-ready implementation. Imports and dependencies must be added per your actual project.

### 17.4. Do Not Misuse `ClientRegistration.authorizationGrantType`

You can instantiate:

~~~java
AuthorizationGrantType customGrant =
        new AuthorizationGrantType(
                "urn:example:grant:custom-delegation");
~~~

However, this object only holds the **grant name**. It does not define how to call the token endpoint, payload format, client auth, or grant semantics.

## 18. Upgrading from 6.5 to 7.0: Password Grant Scenario

### 18.1. Legacy Code

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .password()
                .refreshToken()
                .build();
~~~

In the 6.5 line, `password()` is deprecated. In 7.0, the method is removed, so code relying on it no longer compiles.

### 18.2. Do Not Fix by Passing Username/Password Another Way

Switching from the `password()` builder to manually POSTing:

~~~text
grant_type=password
username=...
password=...
~~~

is not a secure migration path. OAuth Security Best Current Practice disallows the Resource Owner Password Credentials grant in modern designs.

### 18.3. Replacement Paths

Depending on the use case:

| Use Case | Potentially Suitable Replacement |
|---|---|
| Web user login | Authorization Code + PKCE/OIDC Login |
| Native/public client | Authorization Code + PKCE |
| Service-to-service | Client Credentials if permissions belong to the service |
| Exchanging/delegating tokens between services | Token Exchange if supported by AS |
| Input-constrained devices | Device Authorization flow if supported by stack/AS and integrated |
| Headless login requiring username/password | Redesign the flow and identity boundary; do not emulate ROPC |

There is no single drop-in replacement for every case. Evaluate the roles of the **End-User** and the **client/service** before choosing.

### 18.4. Indicators to Search For During Migration

- `OAuth2AuthorizedClientProviderBuilder.password()`.
- `ReactiveOAuth2AuthorizedClientProviderBuilder.password()`.
- `PasswordOAuth2AuthorizedClientProvider`.
- `PasswordReactiveOAuth2AuthorizedClientProvider`.
- Legacy token response clients/configs for the password grant.
- `authorization-grant-type: password` properties.
- Code collecting user usernames/passwords to exchange for tokens.

Do not stop at the first compilation error: configuration and runtime paths tied to the password grant may still remain.

## 19. Spring Security 7.0: What Remains in the Builder?

In the 7.0 Javadoc, `OAuth2AuthorizedClientProviderBuilder` exposes these primary grant methods:

~~~java
.authorizationCode()
.refreshToken()
.clientCredentials()
.provider(extensionProvider)
~~~

`password()` is absent.

Its reactive counterpart likewise provides:

~~~java
ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .provider(reactiveExtensionProvider)
        .build();
~~~

**Do not confuse "the builder only has three dedicated methods" with "the framework does not support extension grants".** The `provider(...)` hook lets you integrate JWT Bearer, Token Exchange, or custom grant providers as needed.

### 19.1. Extensions Are Not Enabled by Default

Even when `TokenExchangeOAuth2AuthorizedClientProvider` is on the classpath, the manager will not necessarily use it automatically. Verify that the provider bean or composite provider is wired properly.

### 19.2. Do Not Copy 7.x APIs Back to 5.x

A newer `RestClient`-based token response client may not exist in the 5.x line. Always check Javadoc for the exact version instead of copying class names from newer docs.

### 19.3. Watch for Other API Changes

Moving major versions can change packages, Java baselines, component models, DSLs, or deprecated APIs outside grants. Follow the appropriate migration guide and maintain a supported dependency stack.

## 20. Example: Checking "Class Exists" in the Actual Artifact

When verifying that code actually compiles:

### 20.1. Import the Class into the Project

For Token Exchange:

~~~java
import org.springframework.security.oauth2.client
        .TokenExchangeOAuth2AuthorizedClientProvider;
~~~

If the class does not exist in the resolved version, the IDE/compiler reports an error.

This is more reliable than reading a Javadoc page for a different version. Still, compiling cleanly does not prove the provider is active in the manager.

### 20.2. Check Methods via Javadoc and IDE

For example, inspect:

~~~java
OAuth2AuthorizedClientProviderBuilder.builder()
        .provider(new TokenExchangeOAuth2AuthorizedClientProvider())
        .build();
~~~

and verify the `provider(OAuth2AuthorizedClientProvider)` method signature.

Do not use runtime reflection in business logic as a primary mechanism to "probe whether a class exists". Grant support is an architectural decision that should be declared, tested, and controlled through dependencies.

### 20.3. Inspect the Source Jar

When Javadoc leaves behavior unclear, read the source of the exact version to see:

- How is the grant value compared?
- When does the provider return `null`?
- Where are assertions/subject tokens retrieved from?
- How does reauthorization occur when an access token expires?
- Does the provider modify the refresh token?
- How is the token endpoint request constructed?

Do not rely on the framework's `main` branch source if runtime uses an older release.

## 21. Runtime Evidence That It Works

A truly functional grant must be tested in a test environment against the corresponding AS.

### 21.1. Testing Initial Token Issuance

With a client authorized for the grant:

1. Invoke the manager with the appropriate registration and principal.
2. The provider matches the grant.
3. The AS accepts client authentication.
4. The token request contains the correct `grant_type`, assertion/subject token, and parameters.
5. The AS returns a valid token response.
6. The manager saves the `OAuth2AuthorizedClient`.
7. The target API accepts the access token for the expected audience/scope.

### 21.2. Testing When Not Enabled

Example:

~~~text
Registration:
  grantType = token-exchange

Manager:
  only has authorizationCode + refreshToken + clientCredentials
~~~

The manager may fail to produce a new authorized client for this grant. That is a **provider wiring issue**, not evidence that the AS lacks Token Exchange support.

### 21.3. Testing AS Grant Rejection

If the token endpoint returns `unsupported_grant_type`:

- Check whether the grant value is accurate.
- Does the AS support the extension?
- Is the client endpoint URL correct?
- Is the feature/tenant policy enabled?
- Does the token request use the right content type/parameters?

### 21.4. Testing Issued Token Permissions

Successful Token Exchange does not prove the new token is accepted by every API. A Resource Server may return 401/403 due to mismatched audience, issuer, or scope.

Do not "work around" this by trying the token against different APIs until one accepts it. Establish a clear AS/API contract.

## 22. Project Compatibility Decision Record Template

You can record a decision table in your architecture documentation:

| Attribute | Illustrative Value |
|---|---|
| Client | `payments-exchange` |
| Spring Boot | Actual project version |
| Spring Security | `6.5.x` (example) |
| Runtime stack | Servlet |
| Grant | `urn:ietf:params:oauth:grant-type:token-exchange` |
| Provider implementation | `TokenExchangeOAuth2AuthorizedClientProvider` |
| API milestone | Since 6.3 |
| Wiring | Provider bean or composite manager |
| Subject token source | Verified `JwtAuthenticationToken` |
| Client authentication | Per AS configuration |
| Target Resource Server | Payments API |
| Audience/scope | Per Payments API contract |
| Integration test | Yes, using test AS tenant |
| Secret/token logging | Disabled/redacted |

This table helps future upgraders understand why the grant works rather than leaving only a bare YAML property.

## 23. Common Misconceptions

### 23.1. "YAML accepts the grant URN, so Spring supports it"

**False.** You also need the appropriate provider and token response client wired into the manager, plus AS authorization.

### 23.2. "The class is in the latest Javadoc, so it must be in our project"

**False.** Latest Javadoc may be 7.x while your project uses 6.1. Compare against the resolved dependency version.

### 23.3. "Having the provider on the classpath enables it automatically"

**False or conditional.** You must check component-based configuration, bean collection, and the actual manager. With a custom manager, you may need to set the composite provider explicitly.

### 23.4. "JWT Bearer grant is the same as `private_key_jwt`"

**False.** One is an authorization grant; the other is client authentication.

### 23.5. "OIDC is a new grant"

**False.** OIDC typically pairs the Authorization Code grant with an ID token, not `grant_type=oidc`.

### 23.6. "PKCE is a grant"

**False.** PKCE protects the Authorization Code flow.

### 23.7. "Having `refreshToken()` means the AS always issues refresh tokens"

**False.** The AS decides whether to issue a refresh token.

### 23.8. "Spring Security 6.5 still has `password()`, so we should use it"

**False.** The API is deprecated and removed in 7.0. Do not build new ROPC integrations.

### 23.9. "Token Exchange has existed since 6.2 because provider beans are auto-picked up from 6.2"

**False.** 6.2 improved wiring; the built-in Token Exchange provider has `Since: 6.3`.

### 23.10. "JWT Bearer is from 6.2 because of the new bean configuration style"

**False.** `JwtBearerOAuth2AuthorizedClientProvider` has existed since 5.5; 6.2 improved bean integration.

### 23.11. "Having any JWT access token lets you use the JWT Bearer grant"

**Not automatically.** A JWT assertion used as a grant must satisfy the AS contract and intended purpose. Never grab an arbitrary JWT to exchange for tokens.

### 23.12. "If the Authorization Server supports the grant, Spring handles it automatically"

**False.** The client must still have the proper implementation and configuration.

## 24. Security When Using Extension Grants

### 24.1. Never Log Tokens or Assertions

Sensitive data that must be protected:

~~~text
access_token
refresh_token
id_token
subject_token
actor_token
jwt_assertion
client_secret
private_key
authorization_code
code_verifier
session_cookie
~~~

Log only registration ID, grant type, correlation ID, token issuance status, and normalized error codes where permitted.

### 24.2. Least Privilege

Token Exchange must never be used to escalate privileges beyond AS policy. New tokens need audience/scope tailored to the specific Resource Server. Client Credentials tokens represent service privileges, not End-User privileges.

### 24.3. Never Blindly Accept Assertions Supplied by the Browser

If the backend takes a JWT from a user and exchanges it using the organization's client secret, a confused deputy risk arises. Verify the token source, issuer, audience, subject, expiry, and exchange permission before calling the AS.

### 24.4. Identify the Credential Owner

An `OAuth2AuthorizedClient` is keyed by principalName and registration. In multi-issuer/multi-tenant setups, never use email or a bare `sub` alone as a global key if collisions are possible.

### 24.5. The Token Endpoint and Resource Server Are Distinct Destinations

Never send refresh tokens or client secrets to a Resource Server. Never use an ID token in place of an access token. The token response client must send grants/assertions only to a verified AS token endpoint.

### 24.6. Never Fall Back to Less Secure Grants

When an AS denies Token Exchange or Authorization Code, never fall back to `password` or collect End-User credentials manually to bypass security constraints.

## 25. Scenario Exercises

### Scenario A: A Spring Security 6.1 application wants Token Exchange

You find a blog post using:

~~~java
new TokenExchangeOAuth2AuthorizedClientProvider();
~~~

**Analysis:** this built-in provider has `Since: 6.3`, so do not assume 6.1 includes it. Either perform a controlled version upgrade or implement a custom extension if upgrading is impossible, with an explicit AS contract.

### Scenario B: Spring Security 5.8 wants JWT Bearer

**Analysis:** `JwtBearerOAuth2AuthorizedClientProvider` has existed since 5.5. Review the extension provider API and configure the manager for that exact version. Do not use a 7.x `RestClientJwtBearerTokenResponseClient` example if that class does not exist in your version.

### Scenario C: Spring Security 6.5 has `password()` code

**Analysis:** the API may still compile, yet is deprecated. Plan a migration before Spring Security 7.

### Scenario D: Spring Security 7.0 build fails on `password()`

**Analysis:** password grant support has been removed. Do not build an ROPC workaround; redesign using Authorization Code + PKCE/OIDC or an appropriate service grant.

### Scenario E: Added `authorization-grant-type: token-exchange` but the manager returns no token

**Analysis:** the grant value may use the wrong URN, the provider may not be enabled, a subject token may be missing, or the AS may disallow it. Check layer by layer.

### Scenario F: Spring Security 6.2 has a JWT Bearer bean, yet a custom manager ignores it

**Analysis:** the custom manager may be overriding the provider chain. Inspect the actual wiring logic rather than just checking that the bean exists.

### Scenario G: AS returns `unauthorized_client`

**Analysis:** this is typically an AS policy/client registration issue, not proof that the library lacks a grant provider.

### Scenario H: Token exchange returns an access token, yet the API returns 403

**Analysis:** the grant may already be working; the new token lacks required scopes/authorities/ownership. Check API authorization, not only the manager.

### Scenario I: WebFlux uses the Servlet Token Exchange provider

**Analysis:** select the reactive counterpart, reactive manager, and reactive token response client; do not wrap a blocking provider in `Mono` and treat it as non-blocking.

### Scenario J: AS metadata does not list a custom grant

**Analysis:** metadata may be incomplete for specialized extensions; verify AS documentation, client configuration, and real integration tests. Do not conclude a grant does not exist solely from a missing metadata entry.

## 26. Self-Check Questions

**Question 1.** Does a grant existing in an RFC mean Spring Security supports it automatically?

**Answer:** No. You need a provider/implementation in the version used, manager configuration, AS support, and integration tests.

**Question 2.** Does Spring Boot successfully binding an `authorization-grant-type` string prove the token endpoint can be called?

**Answer:** No. It only proves the configuration can be represented; there is no proof yet that a provider is enabled or that the AS accepts it.

**Question 3.** How do you know which Spring Security version a project actually uses?

**Answer:** Check resolved dependencies via Maven `dependency:tree` or Gradle `dependencyInsight`, combined with effective POM/BOM when needed.

**Question 4.** Since which line has `OAuth2AuthorizedClientProviderBuilder` existed?

**Answer:** Javadoc states `Since: 5.2`.

**Question 5.** Since which line has `JwtBearerOAuth2AuthorizedClientProvider` existed?

**Answer:** `Since: 5.5`.

**Question 6.** Since which line has `TokenExchangeOAuth2AuthorizedClientProvider` existed?

**Answer:** `Since: 6.3`.

**Question 7.** What notable change did Spring Security 6.2 introduce for extension providers?

**Answer:** A more convenient component-based mechanism to integrate provider beans into the default manager subject to configuration conditions.

**Question 8.** Does Spring Security 7.0 still have `password()` in the provider builder?

**Answer:** No. Password grant support has been removed.

**Question 9.** Is `private_key_jwt` a JWT Bearer authorization grant?

**Answer:** No. It is client authentication; the JWT Bearer grant uses a JWT assertion as the grant to request a token.

**Question 10.** Is PKCE a grant?

**Answer:** No. PKCE protects the Authorization Code flow.

**Question 11.** Is OIDC Login an `oidc` grant?

**Answer:** No. Typically OIDC uses Authorization Code with `openid` and an ID token.

**Question 12.** Is having the Token Exchange provider on the classpath enough?

**Answer:** Not yet. You also need provider wiring, subject token/resolver, AS policy, token response handling, and API validation.

**Question 13.** Can you use a Servlet provider in WebFlux via `Mono.fromCallable(...)` to solve compatibility?

**Answer:** You should not. Use the corresponding reactive provider/manager and reactive token response client.

**Question 14.** If the AS returns `invalid_client`, does that mean Spring Security does not support the grant?

**Answer:** No. Client authentication may be wrong; diagnose at the proper layer.

**Question 15.** What should you check if the AS returns `unsupported_grant_type`?

**Answer:** Grant value, endpoint, AS feature/client policy, request format, and provider version.

**Question 16.** Can a JWT assertion be taken from any ID token?

**Answer:** No. The AS must permit the JWT to be used as an assertion, and the client must validate/constrain the source per the contract.

**Question 17.** Does upgrading Spring Security mean all Spring Boot APIs are immediately compatible?

**Answer:** No. You must check the BOM, dependencies, Java baseline, migration guides, and tests.

**Question 18.** Which test proves end-to-end that a grant works?

**Answer:** An integration test against a test AS tenant, with the right provider/manager, token endpoint response, and a Resource Server validating audience/scope.

## Key Takeaways

- **"Spring Security supports a grant" must be understood by version and across multiple layers:** protocol, AS policy, library API/provider, and runtime wiring.
- **Verify the exact `spring-security-oauth2-client` version** via resolved dependencies before consulting Javadoc and code examples.
- **Three modern core grants:** `authorization_code`, `refresh_token`, and `client_credentials`; do not confuse OIDC/PKCE with new grants.
- **JWT Bearer provider exists since 5.5; Token Exchange provider exists since 6.3.** These are extension grants that generally must be enabled and supplied with valid assertions/subject tokens.
- **Since 6.2 there is a more convenient bean-based provider integration**, though it does not automatically apply to every custom manager.
- **`password` was deprecated in 5.8 and removed in 7.0**; do not implement new ROPC flows or build custom workarounds collecting End-User passwords.
- **Servlet and Reactive have separate managers/providers**. Do not copy classes from one stack to the other without checking.
- **`ClientRegistration.authorizationGrantType` accepting a value does not mean the grant works.** You still need the provider, response client, context, and AS grant permission.
- **Versioned Javadoc, `Since`, `Deprecated`, migration notes, and integration tests** are reliable grounds for determining compatibility.
- **Issued tokens must still carry the right audience, scope, principal, and Resource Server validation**; never log assertions/tokens or use extension grants to escalate privileges.
