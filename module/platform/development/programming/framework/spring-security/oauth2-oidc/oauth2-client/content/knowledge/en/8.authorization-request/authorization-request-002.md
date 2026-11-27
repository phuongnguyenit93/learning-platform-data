# 8.2. OAuth2AuthorizationRequestResolver and the Default Servlet Resolver

## 1. Problem: Who Creates the Authorization Request When a User Chooses to Log In?

A **Spring Boot Servlet** application using **Spring Security OAuth 2.0 Client** typically lets users log in with an account from an **OpenID Provider (OP)** or initiate API access authorization through an **OAuth 2.0 Authorization Server**.

Example: Employee Portal has a **Sign in with corporate account** button. The user clicks the button, and the browser visits:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
~~~

The Portal needs to construct a URL to the Identity Provider's (IdP) authorization endpoint. That URL contains information such as:

- **response_type=code**: requests the Authorization Code Flow.
- **client_id**: the OAuth Client identifier issued by the IdP.
- **redirect_uri**: the callback URL where the IdP will return the user.
- **scope**: requested permissions, such as `openid profile orders.read`.
- **state**: a value binding the authorization response to the initiated request.
- **nonce** when required for OIDC; **code_challenge** and **code_challenge_method** if PKCE is used.

Who retrieves the configuration, builds the parameters, generates transaction-protection values, and packages the authorization request before redirecting the browser?

In Spring Security Servlet, that responsibility belongs to **`OAuth2AuthorizationRequestResolver`** and its default implementation **`DefaultOAuth2AuthorizationRequestResolver`**. The resolver saves the application from manually concatenating query parameter strings or re-implementing the Authorization Code Flow.

> This lesson focuses on the **authorization request on the Servlet OAuth2 Client side**. This is the request the client **sends to the Authorization Server to initiate authorization**, not an HTTP request carrying a Bearer token sent to a Resource Server, and not the authorization response containing `code` returned by the IdP afterward.

## 2. Where the Resolver Fits in the Spring Security Architecture

Suppose the system consists of:

| Component | Role |
|---|---|
| **Browser** | Sends login requests to the Portal and follows redirects |
| **Employee Portal** | Spring Boot Servlet acting as an OAuth2 Client/OIDC Relying Party |
| **Company IdP** | Authorization Server and OpenID Provider; authenticates users, issues codes and tokens |
| **Orders API** | Resource Server receiving an access token after Portal completes login/authorization |

A login-initiating request flows through the main components:

~~~text
Browser
   |
   | GET /oauth2/authorization/company
   v
Servlet Filter Chain
   |
   v
OAuth2AuthorizationRequestRedirectFilter
   |
   | calls resolve(HttpServletRequest)
   v
OAuth2AuthorizationRequestResolver
   |
   | usually DefaultOAuth2AuthorizationRequestResolver
   | uses ClientRegistrationRepository
   v
OAuth2AuthorizationRequest
   |
   | stores request info for callback verification
   v
AuthorizationRequestRepository
   |
   | HTTP 302 Location: IdP authorization endpoint
   v
Browser -> IdP
~~~

**`OAuth2AuthorizationRequestRedirectFilter`** is the Servlet filter handling the initial redirect step. The filter invokes the resolver to obtain **`OAuth2AuthorizationRequest`**, saves the request via **`AuthorizationRequestRepository`**, and sends a redirect to the authorization endpoint.

**The resolver does not authenticate the user itself**, does not exchange the authorization code for tokens, and does not make API calls. Those steps belong to other Spring Security components and the Authorization Server.

## 3. The OAuth2AuthorizationRequestResolver Interface

In Spring Security Servlet, the interface has two methods:

~~~java
package org.springframework.security.oauth2.client.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public interface OAuth2AuthorizationRequestResolver {

    OAuth2AuthorizationRequest resolve(HttpServletRequest request);

    OAuth2AuthorizationRequest resolve(
        HttpServletRequest request,
        String clientRegistrationId
    );
}
~~~

Both methods accept the same **`HttpServletRequest`**, but differ in how they select the client registration:

| Method | Usage |
|---|---|
| **resolve(request)** | Typically handles authorization-initiation URLs, automatically finding the matching **registrationId** from the HTTP request |
| **resolve(request, clientRegistrationId)** | Explicitly passed a registration ID; useful when the caller already knows which client to use |

If the request does not match the authorization-initiation criteria, the resolver can return **`null`**. This is not a "login failure": it simply means the resolver does not create an authorization request for that HTTP request.

Do not assume every URL is handled by the resolver, or redirect every request to the IdP. In an application with many filters and endpoints, identifying the **exact initiation URL** is critical.

### 3.1. What Is a Client Registration ID?

A Registration ID is the name an application assigns to an OAuth Client configuration, for example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal
~~~

Here:

- **`company`** is the **registration ID** used in the internal URL `/oauth2/authorization/company`.
- **`employee-portal`** is the **client ID** registered with the Authorization Server.

The two values can differ. The resolver must retrieve the **`ClientRegistration`** for the corresponding registration ID from **`ClientRegistrationRepository`**; do not grab a client ID from a browser-sent query parameter and immediately trust it as a valid client.

## 4. What Does OAuth2AuthorizationRequest Contain?

The **`OAuth2AuthorizationRequest`** object models an authorization request the client prepares to send to the Authorization Server. It is built from **`ClientRegistration`** information, HTTP request data, and additional values generated by the resolver.

Notable properties:

| Property / API | Meaning |
|---|---|
| **authorizationUri** | The IdP's authorization initiation endpoint |
| **authorizationGrantType** | Usually `authorization_code` for web login |
| **responseType** | Usually `code` |
| **clientId** | The OAuth Client ID |
| **redirectUri** | The Portal's callback, which must match a URI registered at the IdP |
| **scopes** | The set of scopes requested by the client |
| **state** | A random value binding the request to the response |
| **additionalParameters** | Additional protocol/provider parameters, such as `nonce`, `prompt`, `code_challenge` if applicable |
| **attributes** | Internal data the client must retain to handle the callback, such as registration-related and PKCE info |
| **authorizationRequestUri** | The complete URI to redirect the browser to the IdP |

**`additionalParameters`** and **`attributes`** have different meanings:

- **Additional parameters** are information meant to appear in the **authorization request sent to the IdP**, depending on the protocol and provider.
- **Attributes** are **internal to the request object** for the framework to manage the flow. Not every attribute needs or is allowed to appear in the redirect URL.

For example, with PKCE, **`code_challenge`** is a parameter sent in the authorization request; **`code_verifier`** must be kept for the client to use when exchanging the code at the token endpoint, and `code_verifier` is never sent to the authorization endpoint.

### 4.1. Example of the Generated URL

An authorization request can be serialized into a URL like:

~~~text
https://login.example.test/oauth2/authorize
  ?response_type=code
  &client_id=employee-portal
  &scope=openid%20profile%20orders.read
  &state=<random-state>
  &redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany
  &nonce=<oidc-nonce-if-any>
  &code_challenge=<pkce-challenge-if-any>
  &code_challenge_method=S256
~~~

The example above is **split across lines for readability**; the actual **Location** header value is a single encoded URL without literal line breaks. Parameters like `nonce` and `code_challenge` depend on the flow and configuration.

The client secret **is not in this URL**. For a confidential client, the secret is used in the server-to-server step with the **token endpoint**, according to the registered client authentication method.

## 5. Default Resolver: DefaultOAuth2AuthorizationRequestResolver

Spring Security provides the standard implementation:

~~~java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver
~~~

In a typical Servlet OAuth2 login setup, the default resolver:

1. Determines whether the request matches the **authorization request base URI**.
2. Extracts the corresponding **clientRegistrationId**.
3. Looks up **`ClientRegistration`** from **`ClientRegistrationRepository`**.
4. Builds **`OAuth2AuthorizationRequest`** from registration metadata, such as authorization URI, client ID, scopes, and redirect URI.
5. Generates or adds Authorization Code Flow security parameters such as **state**, along with OIDC/PKCE parameters when needed.
6. Allows customizing the request via a **`Consumer<OAuth2AuthorizationRequest.Builder>`** registered with `setAuthorizationRequestCustomizer(...)`.
7. Returns the request object; the filter continues by saving it and redirecting the browser.

Common constructor:

~~~java
new DefaultOAuth2AuthorizationRequestResolver(
    clientRegistrationRepository,
    authorizationRequestBaseUri
);
~~~

Where:

- **`clientRegistrationRepository`** holds the configured clients.
- **`authorizationRequestBaseUri`** defines the URL prefix that starts authorization.

Default value in the Servlet redirect filter:

~~~java
OAuth2AuthorizationRequestRedirectFilter
    .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
~~~

Which corresponds to:

~~~text
/oauth2/authorization
~~~

With registration ID **company**, the starting endpoint is normally:

~~~text
/oauth2/authorization/company
~~~

### 5.1. Distinguishing Authorization URI and Authorization Request Base URI

These two URIs sound similar but point to **two different systems**:

| URI | Example | Belongs To |
|---|---|---|
| **Authorization request base URI** | `/oauth2/authorization` | **Portal**: path the browser calls to ask Spring to start login |
| **Provider's authorization URI** | `https://login.example.test/oauth2/authorize` | **IdP**: endpoint receiving authorization requests from the OAuth Client |

The browser visits the first URI at the Portal. The resolver reads configuration and constructs the URL to the second URI. Do not set the token endpoint or Portal callback directly as the authorization request base URI.

### 5.2. The Callback URL Is a Different Component

The default callback path for Authorization Code login is typically:

~~~text
/login/oauth2/code/{registrationId}
~~~

Example:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

The callback is handled by **`OAuth2LoginAuthenticationFilter`** when using OAuth2 Login. The resolver is the component that **initiates** the authorization request, not the callback handler. Changing the initiation base URI does not automatically change the callback.

## 6. Complete Servlet Flow: Resolver, Redirect, Callback, and Token

~~~mermaid
sequenceDiagram
    actor User as User
    participant Browser as Browser
    participant RedirectFilter as OAuth2AuthorizationRequestRedirectFilter
    participant Resolver as DefaultOAuth2AuthorizationRequestResolver
    participant Repo as AuthorizationRequestRepository
    participant IdP as Authorization Server / OIDC Provider
    participant LoginFilter as OAuth2LoginAuthenticationFilter

    User->>Browser: Clicks corporate sign in
    Browser->>RedirectFilter: GET /oauth2/authorization/company
    RedirectFilter->>Resolver: resolve(request)
    Resolver->>Resolver: Look up ClientRegistration(company), generate state and required params
    Resolver-->>RedirectFilter: OAuth2AuthorizationRequest
    RedirectFilter->>Repo: saveAuthorizationRequest(request, response)
    RedirectFilter-->>Browser: 302 Location: IdP authorization endpoint
    Browser->>IdP: GET /authorize?...&state=...
    IdP->>User: Authenticate and consent when needed
    IdP-->>Browser: 302 back to callback with code and state
    Browser->>LoginFilter: GET /login/oauth2/code/company?code=...&state=...
    LoginFilter->>Repo: load/remove authorization request for verification
    LoginFilter->>IdP: Exchange code for tokens via token endpoint
    IdP-->>LoginFilter: Token response
    LoginFilter-->>Browser: Create login session, redirect to application
~~~

The sequence shows that **the resolver only appears at the initial stage**. Callback handling and code exchange are not executed by the resolver, even though all belong to the same login attempt.

Several security invariants must be maintained:

- **state** must be freshly generated per authorization request and verified when the callback arrives.
- **nonce** is used in OIDC as required by the flow and must be validated according to OIDC rules.
- **PKCE** uses `code_challenge` in the authorization request and `code_verifier` at code exchange; both values must correspond to the same transaction.
- `redirect_uri` used in the authorization request and token exchange must match the configuration accepted by the IdP.
- The HTTP session/request storage mechanism must still be valid when the browser returns from the IdP.

## 7. Creating a Minimal Servlet OAuth2/OIDC Client Project

The example project uses Java 17+, Spring Boot 3, and Spring Security 6.

### 7.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

**`spring-boot-starter-web`** uses the Servlet stack (Spring MVC). **`spring-boot-starter-oauth2-client`** provides OAuth 2.0 Client and OIDC login support. If using WebFlux, you need the reactive stack's resolvers and filters; the `HttpServletRequest` signatures in this lesson do not apply directly to WebFlux.

### 7.2. Configuring ClientRegistration

~~~yaml
# application.yml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Where:

- **`OIDC_ISSUER_URI`** is the issuer of the provider trusted by the client.
- **`OIDC_CLIENT_ID`** is the client ID registered at the IdP.
- **`OIDC_CLIENT_SECRET`** must be supplied via the runtime environment or a secret manager; never hardcode it in Git or frontend code.
- **`openid`** activates OIDC login semantics, while **`orders.read`** is just an illustrative API scope and must be allowed by the IdP.

If the provider publishes OIDC metadata via discovery, **issuer-uri** helps Spring Security locate the required endpoints. Do not manually construct `/authorize` or `/token` URLs by string concatenation when the provider already exposes trusted metadata.

With the configuration above, users initiate login via:

~~~text
http://localhost:8080/oauth2/authorization/company
~~~

The IdP must allow the local callback, for example:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

In production, the callback must use HTTPS and the Portal's actual hostname.

### 7.3. SecurityFilterChain

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**`oauth2Login()`** enables the filter chain for logging in via OAuth 2.0/OIDC. **`oauth2Client()`** adds client authorization management capabilities for scenarios where the application needs to call APIs. In this minimal example, the application can use the default resolver without declaring a resolver bean explicitly.

The `/oauth2/authorization/company` path is an **endpoint handled by a security filter**. It does not require a corresponding `@GetMapping` in a Controller.

## 8. Explicitly Configuring DefaultOAuth2AuthorizationRequestResolver

When you need to customize the authorization request, you can create a resolver and bind it to the **authorization endpoint** configuration of `oauth2Login()`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2AuthorizationConfig {

    @Bean
    OAuth2AuthorizationRequestResolver authorizationRequestResolver(
        ClientRegistrationRepository registrations
    ) {
        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations,
                OAuth2AuthorizationRequestRedirectFilter
                    .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
            );

        return resolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationRequestResolver resolver
    ) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)))
            .build();
    }
}
~~~

This is an **alternative configuration** replacing `SecurityConfig` in the previous section when testing a custom resolver; you should not keep two identical `SecurityFilterChain` beans just for illustration.

Key parts:

1. **ClientRegistrationRepository** is built by Spring Boot from `spring.security.oauth2.client.registration.*` and `provider.*`.
2. **DefaultOAuth2AuthorizationRequestResolver** preserves standard Authorization Code Flow behavior.
3. **authorizationEndpoint(...).authorizationRequestResolver(resolver)** explicitly specifies which resolver `OAuth2AuthorizationRequestRedirectFilter` uses for the OIDC login flow.

Declaring a resolver bean **should not be assumed to automatically switch all filters to use that bean**. Binding the resolver in the corresponding DSL makes it clear which instance the filter receives.

## 9. Customizing Authorization Request Parameters with a Customizer

Some OIDC providers support extra parameters at the authorization endpoint, such as:

| Parameter | Common Meaning |
|---|---|
| **prompt** | Hints how the provider should handle authentication/consent, e.g. `login`, `consent`, `select_account` |
| **login_hint** | Account hint for the provider to display or preselect |
| **ui_locales** | UI language hint, e.g. `vi`, `en` |
| **acr_values** | Requested/suggested authentication level or context per provider policy |
| **max_age** | Value related to authentication session freshness |

Not every provider supports all parameters; sending a parameter is only a request/hint per protocol and provider policy. If a mandatory authentication level is required, the application must verify the authentication result or enforce server-side policy rather than relying solely on a hint.

**`DefaultOAuth2AuthorizationRequestResolver`** provides:

~~~java
setAuthorizationRequestCustomizer(
    Consumer<OAuth2AuthorizationRequest.Builder> customizer
)
~~~

Example adding **`prompt=select_account`** so the IdP can let users choose an account:

~~~java
@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
    ClientRegistrationRepository registrations
) {
    DefaultOAuth2AuthorizationRequestResolver resolver =
        new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            OAuth2AuthorizationRequestRedirectFilter
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
        );

    resolver.setAuthorizationRequestCustomizer(builder ->
        builder.additionalParameters(parameters ->
            parameters.put("prompt", "select_account")
        )
    );

    return resolver;
}
~~~

This snippet is a **replacement for the bean body** in section 8. Afterward, when a user visits:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: localhost:8080
~~~

The redirect URL may contain:

~~~text
...&prompt=select_account
~~~

This customizer applies **fixed** parameters across all registrations handled by the resolver. If the application has multiple providers, only add parameters accepted by the relevant providers, or wrap the resolver with selection logic keyed to specific registrations.

### 9.1. Enabling PKCE for a Confidential Client

**Proof Key for Code Exchange (PKCE)** binds the authorization code to the client that initiated the transaction. In scenarios where Spring Security automatically enables PKCE for a **public client**, the resolver can add `code_challenge` automatically. For a confidential client, PKCE can be requested explicitly if supported by the Authorization Server:

~~~java
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;

// After creating DefaultOAuth2AuthorizationRequestResolver:
resolver.setAuthorizationRequestCustomizer(
    OAuth2AuthorizationRequestCustomizers.withPkce()
);
~~~

If you want to **both** enable PKCE and add `prompt` at the same time, combine them in **one customizer** rather than calling `setAuthorizationRequestCustomizer(...)` twice expecting the first customizer to remain active:

~~~java
var withPkce = OAuth2AuthorizationRequestCustomizers.withPkce();

resolver.setAuthorizationRequestCustomizer(builder -> {
    withPkce.accept(builder);
    builder.additionalParameters(parameters ->
        parameters.put("prompt", "select_account")
    );
});
~~~

This makes it explicit that **each request generates a corresponding `code_verifier` and `code_challenge`**, while the client can still authenticate with its client secret at the token endpoint. **Do not log the code verifier or client secret** for inspection.

## 10. When Should You Implement OAuth2AuthorizationRequestResolver Yourself?

Using **DefaultOAuth2AuthorizationRequestResolver** with a static customizer is usually sufficient for:

- Adding a shared provider parameter, such as `prompt=select_account`.
- Enabling PKCE per application policy.
- Using the standard `/oauth2/authorization` base URI or a single custom fixed base URI.

Implementing the interface yourself is useful when the authorization request depends on **validated incoming HTTP context**, for example:

- Hinting the IdP language based on the user's **vi/en** selection.
- Selecting `prompt` from a safe, application-defined set of values.
- Adjusting a provider-required parameter while preserving security values generated by the default resolver.
- Customizing per registration in an application with multiple providers.

You should **wrap/delegate** to the default resolver and modify only what is necessary, instead of rewriting state, nonce, PKCE, redirect URI, and request attribute generation from scratch.

### 10.1. Wrapper Example Adding `ui_locales` per Request

Suppose the Portal wants to support:

~~~text
/oauth2/authorization/company?lang=vi
/oauth2/authorization/company?lang=en
~~~

Only the two values `vi` and `en` are allowed. A Servlet implementation can look like:

~~~java
package com.example.portal.config;

import java.util.Set;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.web.util.UriComponentsBuilder;

public final class LocaleAuthorizationRequestResolver
    implements OAuth2AuthorizationRequestResolver {

    private static final Set<String> ALLOWED_LOCALES = Set.of("vi", "en");

    private final OAuth2AuthorizationRequestResolver delegate;

    public LocaleAuthorizationRequestResolver(
        ClientRegistrationRepository registrations
    ) {
        this.delegate = new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            OAuth2AuthorizationRequestRedirectFilter
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
        );
    }

    @Override
    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
        return withLocale(request, delegate.resolve(request));
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
        HttpServletRequest request,
        String clientRegistrationId
    ) {
        return withLocale(request,
            delegate.resolve(request, clientRegistrationId));
    }

    private OAuth2AuthorizationRequest withLocale(
        HttpServletRequest servletRequest,
        OAuth2AuthorizationRequest original
    ) {
        if (original == null) {
            return null;
        }

        String locale = servletRequest.getParameter("lang");
        if (!ALLOWED_LOCALES.contains(locale)) {
            return original;
        }

        // URI already built by default resolver; locale can only be "vi" / "en".
        String uri = UriComponentsBuilder
            .fromUriString(original.getAuthorizationRequestUri())
            .queryParam("ui_locales", locale)
            .build(true)
            .toUriString();

        return OAuth2AuthorizationRequest.from(original)
            .additionalParameters(params ->
                params.put("ui_locales", locale))
            .authorizationRequestUri(uri)
            .build();
    }
}
~~~

Bean and filter configuration:

~~~java
@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
    ClientRegistrationRepository registrations
) {
    return new LocaleAuthorizationRequestResolver(registrations);
}

// Wire the bean above into:
// http.oauth2Login(login -> login.authorizationEndpoint(endpoint ->
//     endpoint.authorizationRequestResolver(authorizationRequestResolver)));
~~~

**Why must `authorizationRequestUri` also be adjusted?** That is the URL the filter actually uses in the HTTP 302. When wrapping a request already built by the default resolver, modifying only `additionalParameters` without controlling the final URI can make the object data and the redirect URL inconsistent. The example illustrates keeping both fields synchronized while restricting input values.

**Why use `OAuth2AuthorizationRequest.from(original)`?** This inherits the values already generated by the default resolver, especially **state**, redirect URI, nonce, scopes, and PKCE attributes when present. Building a brand-new request from a few query parameters can easily drop the state or code verifier needed at callback.

This example intentionally refuses to accept `issuer`, `client_id`, `redirect_uri`, `scope`, or an arbitrary user-supplied URL. Those values must come from client registration configuration and trusted application policies. When the provider already sets `ui_locales` or supports multiple locale sources, define clear override rules to avoid appending duplicate query parameters.

## 11. AuthorizationRequestRepository: Where Requests Are Stored for Callback

The resolver creates **`OAuth2AuthorizationRequest`**; the filter then asks **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`** to store the needed data before the browser leaves the Portal for the IdP.

For Servlet OAuth2 login, the common default implementation is:

~~~java
HttpSessionOAuth2AuthorizationRequestRepository
~~~

It stores the authorization request in the HTTP session and lets the callback flow load/remove the saved request for verification.

**This is different from `OAuth2AuthorizedClientRepository`**:

| Component | What Does It Store? | Timing |
|---|---|---|
| **AuthorizationRequestRepository** | Pending authorization request awaiting IdP response, including verification data like state | **Before** exchanging the code for tokens |
| **OAuth2AuthorizedClientRepository/Service** | Authorized client, access token, and refresh token if issued | **After** OAuth2 authorization succeeds |
| **SecurityContextRepository / HTTP session** | Authentication, principal, and login state | Once the user is authenticated |
| **RequestCache** | Original URL/access the user wanted to open before being asked to log in | Supports returning to the original page after login |

Do not use an authorized client repository to replace the authorization request repository: they belong to two different stages and have different data structures.

### 11.1. Customizing the Repository

If special behavior is required, Spring Security allows configuring:

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

@Bean
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
authorizationRequestRepository() {
    return new HttpSessionOAuth2AuthorizationRequestRepository();
}
~~~

And wiring it into login configuration:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestRepository(authorizationRequestRepository)
    )
);
~~~

This is a **configuration illustration**, not a requirement to declare a repository bean when the default behavior is already suitable. If using a custom cookie-based or distributed repository, you must preserve protections for **state, integrity, expiration, and binding to the right browser/session**. Never put sensitive data such as a PKCE verifier into a cookie that could be tampered with or read without authorization.

### 11.2. Multi-Instance Applications

In a multi-replica environment, an authorization request saved in one instance's session may not exist on the instance handling the callback, unless the application uses appropriate session persistence or session affinity routing.

Example:

~~~text
Login start -> Portal instance A -> saves state in session A
Callback    -> Portal instance B -> cannot find corresponding request
~~~

As a result, the callback may fail state verification or report that the authorization request was not found. When running multiple nodes, configure a session store or affinity per your infrastructure design and protect session data. A resolver alone does not solve distributed state storage.

## 12. Comparing `oauth2Login()` and `oauth2Client()` on Servlet

Spring Security has two configurations related to OAuth Client:

| Configuration | Main Goal | Scenario |
|---|---|---|
| **`oauth2Login()`** | Log users in via OAuth 2.0/OIDC and create an application Authentication | Portal with an SSO login button |
| **`oauth2Client()`** | Support OAuth Client authorization and manage tokens/authorized clients to call resources | Portal needs to call Orders API on behalf of the user |

In some applications, **`oauth2Login()`** alone is enough to initiate Authorization Code login. If the application both logs users in and calls APIs, **`oauth2Client()`** is also commonly configured as needed.

For **OAuth2 Login**, the resolver configuration hook is:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(customResolver)
    )
);
~~~

For **OAuth2 Client Authorization Code Grant** on Servlet, Spring Security also has a corresponding DSL:

~~~java
http.oauth2Client(client -> client
    .authorizationCodeGrant(grant -> grant
        .authorizationRequestResolver(customResolver)
    )
);
~~~

Choose the hook matching your actual application flow. If both DSLs are used, make sure filter configurations, base URIs, resolvers, and repositories do not conflict or create two unintended authorization initiation paths.

**Do not confuse with Resource Server**: `oauth2ResourceServer()` protects APIs receiving Bearer tokens; it does not create authorization requests to redirect the browser to an IdP.

## 13. What Does Changing the Authorization Request Base URI Affect?

An application may want a different login-initiation URL, such as:

~~~text
/signin/oauth2/company
~~~

In that case, the resolver can be created with the new base URI:

~~~java
DefaultOAuth2AuthorizationRequestResolver resolver =
    new DefaultOAuth2AuthorizationRequestResolver(
        registrations,
        "/signin/oauth2"
    );
~~~

Ensure the URL handled by `OAuth2AuthorizationRequestRedirectFilter` aligns with the configured resolver, for example via `authorizationEndpoint(...).authorizationRequestResolver(...)`.

Things to watch out for:

- Login links in templates/HTML must point to the new base URI.
- The **Redirect URI callback** can remain `/login/oauth2/code/company`; changing the initiation URL does not force changing the callback.
- If you change the callback, configure **`redirectionEndpoint().baseUri(...)`** and **`registration.redirect-uri`** consistently, and update the redirect URI at the IdP.
- Avoid sharing the base URI with business controllers that have different semantics.
- If the app sits behind a reverse proxy or path prefix, account for the external scheme/host/prefix when constructing `redirect_uri`.

## 14. Multiple Providers, Multiple Client Registrations

An application can integrate multiple IdPs:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${COMPANY_ISSUER_URI}
          partner:
            issuer-uri: ${PARTNER_ISSUER_URI}
~~~

This is an **alternative example for the registration section in section 7**, not a YAML snippet to append to the existing file.

With the default base URI, the corresponding links are:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

The resolver looks up the right `ClientRegistration` by ID, so:

- **company** has company's issuer, client ID, redirect URI, and scopes.
- **partner** has its own configuration per registration.
- The ID in the URL must be managed in the repository; never dynamically build an IdP configuration from an arbitrary URL sent by the client.

If you want to add `prompt=select_account` only for `company`, use a wrapper resolver or a customizer with logic scoped to the specific registration before customizing. Do not apply provider-specific parameters to all providers if other providers do not support them.

## 15. Security Boundaries When Customizing a Resolver

The resolver sits at the entry point of the authorization flow, making it easy to introduce vulnerabilities if customized from untrusted data.

### 15.1. Do Not Let Users Arbitrarily Control Sensitive Parameters

Avoid designs like:

~~~text
/oauth2/authorization/company
    ?redirect_uri=https://attacker.example/callback
    &client_id=unknown-client
    &scope=admin
~~~

And copying query parameters directly into `OAuth2AuthorizationRequest`. That approach can lead to open redirects, improper privilege requests, or misdirection of the authentication flow.

Values such as **client ID**, **authorization URI**, **redirect URI**, **valid scopes**, and **provider** must come from trusted configuration or an application-controlled allowlist.

### 15.2. Preserve State

**state** must be freshly generated, bound to the right session, and verified when the IdP invokes the callback. Do not use a fixed state, do not overwrite state with a browser-supplied value, and do not remove the repository just to "fix `invalid_state` errors."

### 15.3. Keep PKCE/Nonce Consistent

When customizing the builder:

- Do not remove `code_challenge` if PKCE is in use.
- Do not send `code_verifier` to the authorization endpoint.
- Do not overwrite attributes that Spring Security stores for code exchange.
- Do not strip or corrupt `nonce` in an OIDC flow.
- Do not replace `response_type=code` with another response type when the app is configured for the Authorization Code Flow.

### 15.4. Do Not Leak Data While Debugging

Authorization redirect URLs can contain **state**, **nonce**, **login_hint**, or other user-session-related parameters. Do not write the full URL to public logs or analytics systems. **Client secrets**, token responses, and code verifiers must especially never be logged. When investigating issues, log the registration name, grant type, approved IdP hostname, and error outcome without credentials.

### 15.5. Proxies, HTTPS, and Callbacks

When the Portal runs behind a reverse proxy, `{baseUrl}` used for the redirect URI must reflect the public URL, typically **HTTPS**, rather than an internal container hostname/port. If using:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

configure trusted proxies to filter and supply valid `Forwarded`/`X-Forwarded-*` headers, and do not trust arbitrary headers from external clients. The final callback must still match the URI registered at the IdP.

## 16. Observing Resolver Behavior with an HTTP Request

Once the Portal, IdP, and environment variables are configured, you can verify authorization request creation without completing login.

### 16.1. Sending a Login Initiation Request

~~~bash
curl -i "http://localhost:8080/oauth2/authorization/company"
~~~

With a valid configuration, the response is normally a redirect:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=...
Set-Cookie: JSESSIONID=<session-value>; Path=/; HttpOnly
~~~

This is an **illustrative response**, not actual command output. The real `Location` header will contain encoded parameters, and cookies/headers depend on session configuration.

### 16.2. Things to Observe

| What to Observe | Expected Result |
|---|---|
| Portal request path | `/oauth2/authorization/company` matches base URI and registration ID |
| HTTP status | Usually **302** to the IdP's authorization endpoint |
| **client_id** | Matches **company** configuration |
| **response_type** | `code` |
| **redirect_uri** | Public callback with correct scheme, host, path, and registration |
| **scope** | Scopes supported by the IdP; OIDC login must include `openid` |
| **state** | Random value, different across independent authorization requests |
| **nonce** | Generated when OIDC applies per provider/framework mechanism |
| **code_challenge** | Present when PKCE is enabled; `code_verifier` is not in the redirect URL |
| **prompt/ui_locales** | Appears properly when added by customizer/resolver and supported by provider |

Do not share a raw real `Location` header if it contains state, nonce, login hint, or private data. You can inspect parameter names and presence with values redacted.

### 16.3. Testing a Request Outside the Base URI

Example:

~~~text
/any/other/path
~~~

The default resolver is not a catch-all controller; the filter will not turn every request into an authorization request. URLs outside its scope continue through other filters/controllers per security configuration.

### 16.4. Testing an Undeclared Registration ID

Example:

~~~text
/oauth2/authorization/unknown
~~~

If there is no matching `ClientRegistration`, a valid authorization request to the IdP cannot be created. The exact HTTP error behavior depends on framework version and exception handling configuration; do not assume a fixed status code without checking the application.

## 17. Troubleshooting: Common Authorization Request Errors

| Symptom | Possible Cause | How to Check / Fix |
|---|---|---|
| Clicking login does not redirect to IdP | URL does not match base URI, missing starter, or OAuth2 Login not enabled | Check link, `oauth2Login()`, `ClientRegistrationRepository` |
| Generated URL uses wrong registration | Calling wrong `/oauth2/authorization/{id}` | Verify registration ID in YAML and URL |
| IdP reports **invalid_redirect_uri** | `redirect_uri` does not match whitelist at IdP | Compare decoded URL, scheme/host/port/path |
| Callback uses HTTP even though external traffic is HTTPS | Reverse proxy/forwarded headers misconfigured | Check trusted proxy, `{baseUrl}`, and HTTPS termination |
| Custom resolver is not invoked | Bean not wired into DSL or filter uses another resolver | Check `authorizationEndpoint().authorizationRequestResolver(...)` |
| `prompt` does not appear | Only modified object without updating final URI, or customizer did not run | Check active resolver and `authorizationRequestUri` |
| Provider parameter rejected by IdP | Provider does not support it or invalid value | Check IdP documentation and registration scope |
| Callback reports state mismatch | Lost session, browser blocks cookies, reused state, or inconsistent request store | Check browser session, session store, proxy/cookies |
| Callback fails when PKCE is enabled | `code_verifier` not preserved or provider rejects sent PKCE mode | Preserve request attributes and check IdP PKCE policy |
| Login intermittently fails across multiple replicas | Request saved on node A but callback hits node B | Design session persistence or infrastructure routing |
| Login succeeds but API returns 403 | Token lacks required scope or API enforces authorization policy | Distinguish authorization request step from Resource Server authorization |

Post-callback failures can also originate from the **token endpoint**, client secret, token authentication, or OIDC validation; do not blame the resolver for everything. Confirm whether the request **built the URL and redirected** successfully first to isolate the responsible layer.

## 18. Common Misconceptions

**"The resolver is responsible for calling the Authorization Server to obtain tokens."** No. It creates the request for the browser to go to the authorization endpoint. Exchanging the code for tokens happens after the callback and is handled by other client authentication components.

**"An authorization request is an access token."** No. An authorization request initiates authorization; an access token is only received during the subsequent token issuance phase.

**"Just building a URL with `client_id` and `scope` is enough."** No. The Authorization Code Flow also requires a valid redirect URI, state, parameters, and transaction-protection data. Manually constructing URLs while skipping the repository, nonce, or PKCE easily breaks login and introduces security risks.

**"`/oauth2/authorization/company` is the IdP's endpoint."** No. It is the initiation endpoint on the Portal, handled by a Spring Security filter. The IdP has its own authorization endpoint, normally a different HTTPS URL.

**"Changing the authorization request base URI means changing the callback URI."** No. Initiation and callback have separate configurations; if you change the callback, configure it consistently with the IdP.

**"It is safe to change `redirect_uri` via a query parameter."** You should not. The redirect URI must be registered and controlled; customizing it from untrusted data easily causes open redirects or authorization failures.

**"Declaring `@Bean DefaultOAuth2AuthorizationRequestResolver` makes every filter use it automatically."** Do not assume that. Wire the resolver via `authorizationEndpoint().authorizationRequestResolver(...)` or the appropriate OAuth2 Client hook.

**"OIDC login and OAuth2 Resource Server share the same resolver."** No. The resolver belongs to the OAuth2 Client initiating authorization; the Resource Server validates Bearer tokens for API requests.

## 19. Practice Exercise

Suppose the Portal has two registrations:

~~~text
company -> company OIDC Provider
partner -> partner OIDC Provider
~~~

Requirements:

1. Company users click **Company Sign In**, and the app must redirect to the company IdP.
2. Partner users click **Partner Sign In**, and the app must redirect to the partner IdP.
3. Only company requires displaying an account chooser screen via `prompt=select_account`.
4. Both need a secure Authorization Code Flow with a unique state per request; company uses PKCE when supported by the IdP.
5. In production, the company callback is `https://portal.example.test/login/oauth2/code/company`.

Determine:

- What is the authorization initiation link for each provider?
- Which component looks up the registration, generates state, and builds the redirect URL?
- Where should `prompt` be added so it does not affect partner?
- Who saves the authorization request before the browser leaves the Portal?
- Which component receives the authorization code on callback?
- Can an arbitrary `redirect_uri` be passed in a query parameter on the login link?

**Solution approach:**

1. Default links are `/oauth2/authorization/company` and `/oauth2/authorization/partner`.
2. **DefaultOAuth2AuthorizationRequestResolver** creates `OAuth2AuthorizationRequest` based on `ClientRegistrationRepository`; **OAuth2AuthorizationRequestRedirectFilter** uses the result to redirect.
3. Wrap the default resolver or use a customizer with logic restricted to registration **company**; do not add company's prompt for every provider.
4. **AuthorizationRequestRepository**, usually `HttpSessionOAuth2AuthorizationRequestRepository`.
5. **OAuth2LoginAuthenticationFilter** handles the callback in the OAuth2 Login flow, coordinating code exchange and authentication verification components.
6. No. The Redirect URI must come from controlled configuration and be permitted by the IdP.

## 20. Architectural Conclusion

In **Spring Security OAuth 2.0 Client on Servlet**, **`OAuth2AuthorizationRequestResolver`** determines how an **authorization request** is constructed from an HTTP request and client registration. **`DefaultOAuth2AuthorizationRequestResolver`** already provides standard Authorization Code Flow behavior, including registration selection, request creation, and managing transaction-protection parameters per configuration.

**`OAuth2AuthorizationRequestRedirectFilter`** receives the request object, saves needed data via **`AuthorizationRequestRepository`**, and redirects the browser to the Authorization Server. After the IdP returns an authorization code, the callback filter and other OAuth Client components continue verifying state, exchanging the code for tokens, and completing the login session.

In most projects, **use the default resolver and customize only genuinely necessary parameters** via `setAuthorizationRequestCustomizer(...)`. When requests depend on HTTP context, wrap the default resolver, preserve state, nonce, PKCE, and redirect URI, and strictly constrain input data. This separation aligns with Spring Security Servlet's design while keeping Authorization Code/OIDC login consistent and safe across environments.
