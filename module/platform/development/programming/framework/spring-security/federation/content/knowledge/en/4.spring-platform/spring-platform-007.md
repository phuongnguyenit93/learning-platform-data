# `SecurityFilterChain`, `AuthenticationProvider`, and `AuthenticationEntryPoint` in SSO

**Module:** Spring Security – federation  
**Knowledge group:** Spring Platform  
**Technical context:** Servlet/Spring MVC applications, Java 17+, Spring Boot 3.x, and Spring Security 6.x. Examples mainly use **OpenID Connect (OIDC) Authorization Code Flow**; OAuth 2.0 Resource Server is included to distinguish API flows from web login.

## 1. Three Components Answering Three Different Questions

In an SSO application, when a user accesses a resource requiring login, Spring Security must **choose the request protection mechanism**, **verify the authentication proof**, and **decide how to respond when the user lacks proof**.

| Component | Question Solved | Characteristics | Example in SSO |
| --- | --- | --- | --- |
| **SecurityFilterChain** | Which security filters does this request pass through? | Each chain has a **RequestMatcher** and filter list; **FilterChainProxy** selects the first matching chain | Web runs OIDC login; API runs Bearer JWT |
| **AuthenticationProvider** | Is this authentication proof valid and who is the subject? | Component specialized for one **Authentication** type, invoked via **AuthenticationManager**, typically **ProviderManager** | **OidcAuthorizationCodeAuthenticationProvider** handles the OIDC code flow; **JwtAuthenticationProvider** verifies access tokens for APIs |
| **AuthenticationEntryPoint** | When unauthenticated, how does the app ask the client to start authenticating? | Produces the HTTP response initiating the authentication mechanism; usually called by **ExceptionTranslationFilter** | Web **302** to the login-initiation URL/path; API **401** with **WWW-Authenticate: Bearer** |

**Easy way to remember:** SecurityFilterChain picks **the request processing path**; AuthenticationProvider checks **credentials/evidence**; AuthenticationEntryPoint replies **"authenticate this way"** when needed. They collaborate, yet no single component produces the entire SSO workflow alone.

**Key point:** In Spring Security, **AuthenticationEntryPoint is not the Identity Provider**. An "entry point" is an HTTP response strategy inside your application, whereas the **OpenID Provider (OP)/Identity Provider (IdP)** is the external system that actually authenticates the user.

## 2. High-Level Architecture of Spring Security Servlet

An HTTP request flows through this conceptual pipeline:

~~~text
HTTP request (browser or API client)
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy (springSecurityFilterChain)
        |
        | Selects the FIRST SecurityFilterChain matching RequestMatcher
        |
        +--> /api/**      -> BearerTokenAuthenticationFilter -> AuthenticationManager
        |                                                   -> JwtAuthenticationProvider
        |                                                   -> JwtDecoder
        |
        +--> /**          -> OAuth2AuthorizationRequestRedirectFilter
                            OAuth2LoginAuthenticationFilter -> AuthenticationManager
                                                              -> OIDC AuthenticationProvider
                            ExceptionTranslationFilter + AuthenticationEntryPoint
                            AuthorizationFilter
        |
        v
SecurityContext / Authorization / Controller
~~~

This is a **conceptual diagram**, not the complete ordering of every filter. Spring Security also includes filters for security context, CSRF, headers, logout, request cache, etc. Actual ordering depends on configuration and version. **Do not alter filter ordering** unless you understand the exact insertion point needed.

### 2.1. How Does `SecurityFilterChain` Differ from a Servlet Filter?

- **SecurityFilterChain** is not just a single hand-written filter. It declares a **RequestMatcher + filter list** for a group of requests. Spring Security uses FilterChainProxy to coordinate chains.
- **FilterChainProxy** bridges the servlet container and Spring Security filters, typically via **DelegatingFilterProxy**.
- Multiple SecurityFilterChain beans can be defined. Each request is handled only by **the first matching chain** in priority order.
- If **no chain matches**, the request is not protected by those Spring Security filter chains. That is why a **final fallback chain covering remaining URLs** is usually needed.
- If there is no reason to separate API and web, **a single chain** can also configure SSO cleanly. Split chains only when authentication/response mechanics genuinely differ.

### 2.2. Where Do `AuthenticationManager` and `ProviderManager` Sit?

Filters processing credentials normally construct an **unauthenticated Authentication object**, then call **AuthenticationManager.authenticate(authentication)**. The common implementation is **ProviderManager**, which tries **AuthenticationProvider** instances matching the token type. On success, an **authenticated Authentication** object is returned and stored into SecurityContext by that filter's mechanism.

**AuthenticationProvider does not directly select HTTP URLs; AuthenticationEntryPoint does not decode JWTs or exchange OAuth authorization codes either.**

## 3. `SecurityFilterChain`: Splitting Web SSO and REST API Protection Zones

One application can simultaneously act as:

1. **OIDC Relying Party (RP):** redirects browsers to the OP for employee login, then creates an **application session**.
2. **OAuth 2.0 Resource Server:** accepts **Bearer access tokens** to protect REST APIs without redirecting browsers to a login screen.
3. **OAuth 2.0 Client:** may request and manage access tokens to call other APIs; this capability is distinct from a resource server.

Because mechanisms and client types differ, one typically defines:

| Chain | Scope | Primary Mechanism | Unauthenticated Response |
| --- | --- | --- | --- |
| **apiChain – @Order(1)** | **/api/** | **oauth2ResourceServer().jwt()**; Stateless | **401** Bearer challenge |
| **webChain – @Order(2)** | Remaining URLs (**/**) | **oauth2Login()**; browser session | **302** into OIDC login flow |

### `securityMatcher` vs `requestMatchers`

**securityMatcher("/api/**")** operates at the **SecurityFilterChain selection** level: that chain's entire filter list processes only matching paths.

**authorizeHttpRequests().requestMatchers("/public/**").permitAll()** only decides **access permissions** inside the already-selected chain; it does not route the request to another chain.

Examples:

- **GET /api/report** matches the earlier API chain. Even though webChain's default matcher covers all requests, **webChain will not run for this request**.
- **GET /dashboard** does not match /api/** so it is handled by webChain.
- **GET /login/oauth2/code/company** must also pass through webChain so **OAuth2LoginAuthenticationFilter** receives the callback; if webChain only matches **/app/** and excludes the callback, login breaks.
- **/oauth2/authorization/company** is the endpoint initiating authorization requests in webChain; it must also sit within the properly protected/routed scope.
- With multiple specialized chains, use explicit **@Order**; an overly broad matcher can "swallow" requests meant for downstream chains.

### Chains Do Not Automatically Contain Every Filter

Selecting a chain via a matcher is not enough. To handle OIDC callbacks you must enable **oauth2Login()** (or equivalent config). To validate Bearer JWTs you must enable **oauth2ResourceServer().jwt()** (or equivalent config). If you only configure **anyRequest().authenticated()** without enabling an appropriate authentication mechanism, users can hit 401/403 with no expected SSO flow.

## 4. `AuthenticationProvider`: Who Actually Verifies the Proof?

### 4.1. `Authentication` and `ProviderManager`

**Authentication** can represent either an unverified request (e.g., a token carrying an authorization code or Bearer token) or an authenticated subject (principal, authorities, authenticated flag).

**AuthenticationProvider** has two core methods:

~~~java
Authentication authenticate(Authentication authentication)
    throws AuthenticationException;

boolean supports(Class<?> authentication);
~~~

This is an **abridged interface signature** for explanation, not a standalone compilable Java file.

- **supports(type):** whether the provider can handle this Authentication class.
- **authenticate(input):** returns an authenticated result on success; **throws AuthenticationException** when authentication fails; may return **null** if it cannot decide so another provider can try.
- **ProviderManager:** coordinates a list of providers; if no provider handles the input type, **ProviderNotFoundException** is typically thrown.
- A provider **is not invoked automatically on every request**: a filter or caller must pass an Authentication to the appropriate AuthenticationManager.

Never interpret **supports() = true** as meaning credentials are valid. It only means the provider recognizes the Authentication type.

### 4.2. Default Providers in OIDC Login

Spring Security's OIDC flow uses built-in components, for example:

- **OAuth2AuthorizationRequestRedirectFilter:** creates the authorization request and sends the browser to the authorization endpoint; this filter initiates the flow without verifying an ID token.
- **OAuth2LoginAuthenticationFilter:** handles the authorization code callback, builds an **OAuth2LoginAuthenticationToken**, and delegates to AuthenticationManager.
- **OidcAuthorizationCodeAuthenticationProvider:** provider specialized for the **OIDC Authorization Code Flow**, calling the token endpoint to exchange the code, validating the ID token via OIDC components, and building an **OidcUser** principal.
- **OAuth2LoginAuthenticationProvider:** supports non-OIDC **OAuth 2.0 Login**, exchanging the code for an access token and fetching user attributes via OAuth2UserService.
- **OidcUserService** and **DefaultOAuth2UserService:** load/map user details. These **are not AuthenticationProviders**; do not confuse these services with authentication providers.

When the client registration includes the **openid** scope, Spring Security uses the corresponding OIDC capability. Without **openid**, plain OAuth 2.0 login does not provide an ID token or standard OIDC authentication semantics.

**You do not need to write a custom AuthenticationProvider for standard OIDC**. Use **oauth2Login()** and register the proper OP/issuer, client, and redirect URI. Manually accepting JWTs or callbacks in a controller easily misses signature, state, nonce, audience, issuer, and required constraint checks.

### 4.3. Provider in Resource Server

With **oauth2ResourceServer().jwt()**:

1. **BearerTokenAuthenticationFilter** extracts the Bearer token from the HTTP request and creates a **BearerTokenAuthenticationToken**.
2. The filter passes the token to the configured AuthenticationManager.
3. **JwtAuthenticationProvider** uses **JwtDecoder** to validate signature, permitted algorithms, issuer, expiration, and JWT validators; maps permissions to authorities.
4. Success returns a **JwtAuthenticationToken**, whose principal is typically a **Jwt**. The Spring Security filter updates SecurityContext.
5. On failure, the filter handles the authentication error and normally invokes the Bearer AuthenticationEntryPoint to return 401.

If the access token is **opaque**, use the corresponding introspection mechanism/provider instead of JwtAuthenticationProvider.

**Common mistake:** an API accepting any validly signed ID token as a Bearer access token. ID tokens are meant for the **OIDC client/RP**, whereas APIs must validate access tokens **issued for the API's audience**, matching the deployment's token type, scopes/permissions, and issuer.

### 4.4. When Is a Custom `AuthenticationProvider` Needed?

Implement one yourself only if the application requires **a different credential type** not built into Spring Security or a custom protocol verified to be secure. A custom provider must enforce exact Authentication types, verify source/validity/replay/recipient, fail closed on errors, and return results without leaking secrets. If you only want to:

- **change an OIDC user's roles/authorities:** use a **GrantedAuthoritiesMapper** or an **OidcUserService** delegating to the default;
- **restrict claims in a JWT access token:** configure **JwtDecoder validators** and **JwtAuthenticationConverter**;
- **change the login path or 401 response:** customize **AuthenticationEntryPoint** or the filter chain;
- **block internal accounts after SSO:** map identities by **(issuer, subject)** and enforce policy in user mapping or authorization.

Those tasks **do not require** replacing the standard provider. Registering a custom provider in the wrong place can break OIDC login or open a path to accepting forged tokens.

## 5. `AuthenticationEntryPoint`: Responding When Unauthenticated

### 5.1. When Is the EntryPoint Invoked?

After chain execution, **ExceptionTranslationFilter** translates relevant security exceptions into HTTP responses:

- **AuthenticationException**, or access denied when the request is not yet fully authenticated: triggers authentication via **AuthenticationEntryPoint**.
- **AccessDeniedException** for an already-authenticated user lacking permissions: typically invokes **AccessDeniedHandler**, returning **403 Forbidden** instead of restarting SSO as an authorization workaround.
- Certain **authentication filters** catch authentication failures themselves and call configured failure handlers/entry points. For example, a failed OIDC callback may go to the login failure URL; not every failure comes from ExceptionTranslationFilter.

**EntryPoint does not verify passwords, call the IdP on behalf of every filter, or guarantee login success.** It only initiates the HTTP authentication interaction (redirect or challenge).

### 5.2. `LoginUrlAuthenticationEntryPoint` for Browsers

Example:

~~~java
new LoginUrlAuthenticationEntryPoint("/oauth2/authorization/company")
~~~

When an unauthenticated browser requests **/dashboard**, the EntryPoint can return **302 Location: /oauth2/authorization/company**. The subsequent request to that path is handled by **OAuth2AuthorizationRequestRedirectFilter** to build the **authorization request**, returning another **302** to the OP/IdP.

More precisely: **LoginUrlAuthenticationEntryPoint does not construct the OP's full authorization URL itself**; it sends the client to the endpoint Spring OAuth2 login uses to initiate the flow.

If the application has **multiple IdPs**, you can direct users to a provider selection page or use a trusted provider-selection mechanism; never construct arbitrary IdP domains from unvalidated input.

### 5.3. `BearerTokenAuthenticationEntryPoint` for REST APIs

When an API request lacks a token or carries an invalid token, typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

With a malformed/invalid token, the challenge may add **error="invalid_token"** and related parameters. Never return an HTML login page or a 302 to the IdP for automated API clients.

If the Bearer token **was authenticated** yet lacks required scopes/permissions, the API typically returns:

~~~http
HTTP/1.1 403 Forbidden
~~~

The resource server may include **WWW-Authenticate: Bearer error="insufficient_scope"** when appropriate permission context exists. Exact details depend on Spring Security, handlers, and version.

### 5.4. Do Not Equate `AuthenticationEntryPoint` with `AuthenticationFailureHandler`

| Scenario | Component Typically Handling | Typical Response |
| --- | --- | --- |
| Anonymous user visits private web page | **ExceptionTranslationFilter → AuthenticationEntryPoint** | Redirect to initiate SSO |
| API missing Bearer token | **Resource Server/EntryPoint** | 401 Bearer challenge |
| OP callback returns bad code/invalid state | **OAuth2LoginAuthenticationFilter + failure handler** | Login failure, typically redirect to **/login?error** |
| User has session yet lacks role | **AccessDeniedHandler** | 403 |
| API token signature/issuer/audience invalid | **BearerTokenAuthenticationFilter + authentication failure processing** | 401 |
| Authentication succeeds yet tenant is unauthorized | Authorization/policy or user mapping check | 403 or login failure depending on check location |

Assigning clear responsibilities prevents login loops and stops authorization errors from turning into "please log in again".

## 6. Full SSO Flow: From Request to Logged-In Session

### Step A – Unauthenticated Browser Visits `/dashboard`

1. **GET /dashboard** enters the Servlet container → FilterChainProxy.
2. FilterChainProxy tries **apiChain** (matcher /api/**) → no match; then selects **webChain**.
3. **AuthorizationFilter** requires authentication, yet the request has no valid session.
4. **ExceptionTranslationFilter** turns this state into an authentication initiation action.
5. **LoginUrlAuthenticationEntryPoint** returns 302 to **/oauth2/authorization/company**.
6. **OAuth2AuthorizationRequestRedirectFilter** generates the authorization request with **state**, redirect URI, **openid** scope, and required parameters, sending the browser to the OP.
7. The OP authenticates the user (or reuses an existing OP SSO session) and sends the browser back to the registered callback.

### Step B – OP Redirects Back to the Application

8. The browser calls **GET /login/oauth2/code/company?code=...&state=...**. The request enters webChain.
9. **OAuth2LoginAuthenticationFilter** receives the callback, retrieves the saved request, and checks constraints.
10. The filter invokes AuthenticationManager with **OAuth2LoginAuthenticationToken**.
11. **OidcAuthorizationCodeAuthenticationProvider** (in OIDC config) handles the code/token response, validates the ID token, and retrieves required OIDC info via the appropriate service.
12. On success, SecurityContext is established/persisted via Spring's login mechanism; typically an **HttpSession**/cookie is issued to the browser. The success handler redirects the browser back to the original URL if request cache config permits.
13. Visiting the protected page uses the stored **Authentication**; separate authorization rules can still deny users lacking roles.

### Step C – API Receives a Bearer Token

1. The API client calls **GET /api/reports** with **Authorization: Bearer ...**.
2. **apiChain** is selected; **BearerTokenAuthenticationFilter** processes the access token.
3. **JwtAuthenticationProvider** validates the token and creates a **JwtAuthenticationToken** if valid.
4. **AuthorizationFilter** requires authority **SCOPE_reports.read**.
5. Token has valid issuer/audience/signature/time and required scope → request proceeds; otherwise → 401 or 403 depending on failure type.

**Difference:** Browser SSO usually maintains an application session after verifying with the OP; Bearer APIs usually validate tokens **per request** without browser redirects. The same OP may issue tokens for both, yet tokens for the two roles must never be mixed.

## 7. Spring Boot 3.x Example: Two Chains with Different EntryPoints

This is a **Servlet/MVC configuration for Java 17+**, deployed in a Spring Boot 3.x project with a Maven parent/BOM. The **example.org** URLs are illustrative: you need a real OP supporting discovery, OIDC client registration, and issuing JWT access tokens for the API's audience before testing a live login flow. Class samples are complete code within a configured Boot project, not standalone Java programs runnable with plain javac.

### 7.1. Dependencies

Add to `pom.xml` **dependencies**; versions are managed by the Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 7.2. Client and JWT Resource Server Configuration

**src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/company
          audiences:
            - urn:reports-api
~~~

**Explanation:**

- **registration.company** identifies the OIDC client as **registrationId=company**; Spring creates default initiation endpoint **/oauth2/authorization/company** and callback **/login/oauth2/code/company**.
- **scope: openid** enables OIDC semantics so the RP validates ID tokens. **profile/email** only request extra claims; they do not automatically grant permissions.
- **issuer-uri** specifies the trusted OP/Authorization Server. Never extract arbitrary issuers from browser requests or unverified JWTs to auto-trust issuers.
- **resourceserver.jwt.audiences** requires API JWTs to carry audience **urn:reports-api**, preventing web client ID tokens or access tokens for other APIs from being accepted just because they share the same issuer.
- **client-id** and **client-secret** must come from a real registration, supplied via environment variables/secret manager; never commit secrets.
- Register the exact redirect URI at the OP: typically **{baseUrl}/login/oauth2/code/company**; behind a reverse proxy, configure proper public base URL, scheme, and forwarded headers via trusted proxies.
- Having two identical issuer-uri URLs illustrates **two distinct trust roles**: the OIDC client verifies ID tokens for the RP; the resource server verifies access tokens for the API.

**Authorization Code + PKCE:** enable PKCE according to client type and OP support; public clients must use PKCE and confidential clients should use PKCE per current security best practices. Use HTTPS, maintain proper **state**/nonce, and never skip callback validation. Never inject fake PKCE into response handlers.

### 7.3. `SecurityConfig.java` – Usable Configuration in Boot

**src/main/java/com/example/sso/SecurityConfig.java**:

~~~java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasAuthority("SCOPE_reports.read"))
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(
                    new LoginUrlAuthenticationEntryPoint(
                        "/oauth2/authorization/company")));
        return http.build();
    }
}
~~~

**Notes on the API chain:**

- Matches **/api/** ahead of webChain so API requests never redirect to SSO login.
- **oauth2ResourceServer().jwt()** automatically wires the filter and provider mechanics for Bearer JWTs; no need to write a custom **AuthenticationProvider**.
- By default, resource server configures **BearerTokenAuthenticationEntryPoint** suited for APIs; do not replace it with LoginUrlAuthenticationEntryPoint.
- **hasAuthority("SCOPE_reports.read")** enforces authorization after the token is authenticated. Spring by default maps **scope/scp** claims into authorities prefixed with **SCOPE_**.
- **STATELESS** avoids using HTTP sessions as an API authentication mechanism. CSRF is disabled only on the API chain in this example **because the API is designed to accept Bearer tokens via the Authorization header**; if an API also authenticates via cookies, CSRF protection must be re-evaluated.

**Notes on the web chain:**

- The web chain omits **securityMatcher** because it must catch all remaining requests: web pages, OIDC initiation endpoints, and callbacks.
- **oauth2Login()** adds the required OAuth2/OIDC filters. By default with multiple IdPs Spring may render a login selection page; this sample intentionally redirects straight to **company**.
- **exceptionHandling.authenticationEntryPoint** turns unauthenticated access to protected pages into a redirect starting OIDC; it does not validate ID tokens or set roles itself.
- **anyRequest().authenticated()** only requires authentication for web routes; business roles/permissions need dedicated policy.
- **@Order(2)** places the web chain after the API chain. Do not set a matcher limited only to **/dashboard/** that leaves OIDC endpoints outside the chain.

### 7.4. Main Application and Controller

**src/main/java/com/example/sso/SsoApplication.java**:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SsoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/sso/SsoController.java**:

~~~java
package com.example.sso;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SsoController {

    @GetMapping("/")
    public String home() {
        return "Public home page";
    }

    @GetMapping("/dashboard")
    public Map<String, String> dashboard(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getSubject()
        );
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(
            @AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getClaimAsString("iss")
        );
    }
}
~~~

**The responses above have no fixed subject/issuer**: they depend on the OP and actual tokens. Never log ID tokens/access tokens or return unnecessary sensitive details in production applications. The API snippet reads the **sub** claim, so the OP must include a valid subject in the API access token; if your real API uses `client_credentials` or another profile, design principal/responses accordingly.

### 7.5. Run Command and Expected Results

In a valid Spring Boot/Maven project, set **OIDC_CLIENT_ID** and **OIDC_CLIENT_SECRET** environment variables and replace the issuer with a real OP, then run:

~~~bash
mvn spring-boot:run
~~~

Testing the public resource:

~~~bash
curl -i http://localhost:8080/
~~~

**Response body:**

~~~text
Public home page
~~~

The command above requires no OP because **/** is configured as **permitAll**. Startup/metadata discovery may still depend on configuration and IdP reachability; an illustrative issuer does not allow testing real OIDC login.

For **GET /dashboard** without a session, expect the redirect sequence:

~~~text
GET /dashboard
 -> 302 /oauth2/authorization/company
 -> 302 https://<actual-issuer>/.../authorize?...
 -> authenticate at OP
 -> GET /login/oauth2/code/company?code=...&state=...
 -> create login session if ID token/flow is valid
~~~

This is an explanatory sequence, not a literal HTTP stdout string; final redirect URI, OP login path, headers, and status codes vary by deployment.

For the API without a token:

~~~bash
curl -i http://localhost:8080/api/reports
~~~

**Typical response:** **401 Unauthorized**, with header **WWW-Authenticate: Bearer**. The API should not return 302 to OP login.

With a **real access token** issued for **urn:reports-api** with **reports.read** permission, test:

~~~bash
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:8080/api/reports
~~~

**YOUR_ACCESS_TOKEN** is just a doc placeholder; to test you must supply a real token issued by a trusted OP. When valid, expect **200 OK** with JSON containing issuer/subject; when missing scope, typically **403 Forbidden**; an invalid token typically returns **401 Unauthorized**.

## 8. Analyzing Specific `AuthenticationProvider` Behavior When Debugging SSO

### 8.1. OIDC Login via Code

~~~text
Callback: /login/oauth2/code/company?code=...&state=...
   |
OAuth2LoginAuthenticationFilter
   |
OAuth2LoginAuthenticationToken (not yet authenticated)
   |
AuthenticationManager / ProviderManager
   |
OidcAuthorizationCodeAuthenticationProvider
   |  - exchanges code for tokens at the matching OP token endpoint
   |  - validates ID token: signature, issuer, audience, exp, nonce...
   |  - invokes OidcUserService when user info is needed
   v
Authenticated Authentication (OIDC principal)
   |
SecurityContext + browser session
~~~

If the client config omits **openid**, the **OAuth2LoginAuthenticationProvider** flow and user service differ from OIDC ID tokens. For identity-authenticating SSO, use **OIDC** whenever the OP supports it.

### 8.2. Bearer JWT for APIs

~~~text
GET /api/reports
Authorization: Bearer <access_token>
   |
BearerTokenAuthenticationFilter
   |
BearerTokenAuthenticationToken
   |
AuthenticationManager / ProviderManager
   |
JwtAuthenticationProvider
   |  - JwtDecoder checks signature/JWKS, exp, nbf, iss
   |  - audience validator checks urn:reports-api
   |  - JwtAuthenticationConverter maps scopes/authorities
   v
JwtAuthenticationToken
   |
AuthorizationFilter checks SCOPE_reports.read
   |
Controller or 403
~~~

Spring Security may route through an **AuthenticationManagerResolver** to select a manager per request, especially with multiple issuers. Do not assume every application has only a single global ProviderManager.

### 8.3. A `ProviderManager` Can Hold Multiple Providers

~~~text
ProviderManager
  - provider A: supports OAuth2LoginAuthenticationToken for OIDC
  - provider B: supports OAuth2LoginAuthenticationToken for plain OAuth2 login
  - provider C: handles another Authentication type if configured
~~~

This list is a conceptual example of delegation; never assume **all three always sit in the same manager**. The actual provider set varies by chain, configuration, version, and credential types.

Regarding **supports()**, a provider that does not support the input type will skip the request. If a provider supports it yet validation fails, the outcome depends on exception/orchestration rules; never allow "fallback to a less strict provider" to bypass signatures or wrong issuers.

## 9. Customizing in the Right Place: Choosing the Lowest-Risk Option

### 9.1. Restricting Who Can Log Into Web After OIDC

For example, the organization only allows internally linked accounts to access **/dashboard**. You can customize **OidcUserService**, delegate to the default service first, then look up the account by **(iss, sub)** and decide per policy. This is **post-authentication user mapping**, not a replacement for the provider's ID token validation.

Illustrative integration snippet (assuming an internal **AccountAccessService** exists):

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
        AccountAccessService accessService) {
    OidcUserService delegate = new OidcUserService();
    return request -> {
        OidcUser user = delegate.loadUser(request);
        String issuer = user.getIdToken().getClaimAsString("iss");
        String subject = user.getSubject();

        if (!accessService.isAllowed(issuer, subject)) {
            OAuth2Error error = new OAuth2Error("access_denied");
            throw new OAuth2AuthenticationException(
                error, "Account is not enabled for this application");
        }
        return user;
    };
}
~~~

This is an **extension snippet, not a standalone Java class**. Required imports come from **org.springframework.security.oauth2.client.userinfo.OAuth2UserService**, **org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService**, **org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest**, **org.springframework.security.oauth2.core.oidc.user.OidcUser**, **org.springframework.security.oauth2.core.OAuth2Error**, and **org.springframework.security.oauth2.core.OAuth2AuthenticationException**. **AccountAccessService** is a business abstraction defined by the application.

Plug the snippet into the web chain DSL if actively used:

~~~java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(oidcUserService)))
~~~

This replaces **.oauth2Login(Customizer.withDefaults())** in webChain, with a properly typed **oidcUserService** variable or bean. **isAllowed(issuer, subject)** must query trusted internal policy, never relying solely on email domains or client-supplied headers. Do not write a custom AuthenticationProvider just for this.

### 9.2. Authorizing JWTs by Custom Claims

Use **JwtAuthenticationConverter** to map trusted claims to authorities and **JwtDecoder/OAuth2TokenValidator** to enforce issuer/audience/timestamps. The converter must never grant admin roles based on a claim not strictly defined by the AS. For OIDC ID tokens, perform user-identity mapping/authorities in the web chain rather than accepting ID tokens like a JWT resource server.

### 9.3. Returning JSON 401 Responses for APIs

If you want REST endpoints to always return JSON, configure a custom **AuthenticationEntryPoint** for the API while preserving **401** and **WWW-Authenticate: Bearer** semantics per RFC 6750. Usually the default **BearerTokenAuthenticationEntryPoint** is sufficient; changing the response body does not change token validation logic.

### 9.4. Supporting Multiple OPs/IdPs

Create fixed client registrations for approved OPs, select the provider from bound request context, and prevent authorization-server mix-up; never dynamically build issuers or JWKS URLs from unverified query parameters. Multi-issuer APIs can use **JwtIssuerAuthenticationManagerResolver** with an approved issuer allowlist and corresponding audience policies; never establish trust dynamically from an unverified JWT's **iss** claim.

## 10. Common Errors and Root-Cause Analysis

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| **/dashboard** returns 401 instead of redirect | Wrong EntryPoint, request entered API chain, or oauth2Login not enabled | Check matchers, @Order, exceptionHandling in webChain |
| **/api/reports** returns 302 to IdP | API request matched webChain, or API uses login EntryPoint | Put API chain first, use securityMatcher("/api/**"), enable resource server |
| Login starts yet callback returns 404/401 | **/login/oauth2/code/company** outside webChain, redirect URI mismatch, missing oauth2Login filter | Check registrationId, callback matcher, redirect URI at OP, and reverse proxy |
| "No AuthenticationProvider found" | ProviderManager lacks a provider supporting the input Authentication | Check token type and enabled DSL; do not register providers on the wrong chain |
| OIDC login fails after switching issuer | ID token issuer/client/nonce/audience/signature mismatch | Read scrubbed error logs, OP metadata, client registration config |
| API reports invalid_token | JWT has wrong signature, issuer, audience, timestamps, or decoder | Check issuer-uri, audiences, JWKS, clock, and ensure token is meant for API |
| API returns 403 despite valid token | Missing **SCOPE_reports.read** authority or denied by internal policy | Check scope claims, converter, and authorizeHttpRequests |
| User logs in yet internal roles are wrong | Missing role mapping from OIDC identity, using inconsistent claims | Map **(iss, sub)** to application accounts/permissions |
| Callback enters 302 loop | Inconsistent session/cookie, SameSite, reverse-proxy scheme/host, redirect URI, request cache, or state | Compare request/response and cookie domain; verify proxy/trust |
| API automatically creates a session after sending JWT | API chain is not truly stateless or request matched webChain | Check @Order, securityMatcher, SessionCreationPolicy |
| Custom filter never runs | Registered on a different chain or request does not match | Inspect active filter list, matchers, and ordering |
| AuthenticationException occurs yet EntryPoint is skipped | Filter catches error with its own failure handler | Identify which filter throws/catches, check OAuth2LoginAuthenticationFilter or BearerTokenAuthenticationFilter |

### Controlled Debugging

Only during development, temporarily enable:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Observe **which chain was selected**, which filters are configured, issuer/audience/callback errors, and 401/403 outcomes. In production, control log levels and never log access tokens, ID tokens, authorization codes, client secrets, cookie/session IDs, or sensitive data.

**Effective troubleshooting order:** check **URL → selected chain → applied filters → AuthenticationProvider/token validation → authorities → EntryPoint/AccessDeniedHandler/failure handler**. Separating layers prevents fixing the wrong place.

## 11. Practice Scenarios and Solutions

### Scenario 1 – Wrong Chain Order

The app sets webChain **@Order(1)** with no securityMatcher, and apiChain **@Order(2)** for /api/**. An API call missing a token gets 302 to the OP.

**Explanation:** webChain matches all requests by default and is chosen first; apiChain never gets a turn. **Fix:** give apiChain **@Order(1)**, and webChain after it. No custom AuthenticationProvider needed.

### Scenario 2 – Unauthenticated User Visits Private Page

The browser sends **GET /dashboard** without a session, caught by webChain.

**Correct:** AuthorizationFilter requires authentication; ExceptionTranslationFilter/EntryPoint returns a redirect to the OIDC start endpoint; OAuth2AuthorizationRequestRedirectFilter then builds the request to the OP. **Do not call JwtAuthenticationProvider directly** for browser login.

### Scenario 3 – Logged-In User Lacks `ROLE_ADMIN`

The browser holds a valid OIDC session and visits **/admin**, which requires an admin role.

**Correct:** authorization checks authorities and returns **403**/AccessDeniedHandler when permissions are missing. **No need to call the OP again** because authentication and authorization are two separate steps.

### Scenario 4 – API Missing Bearer Token

An automation job calls **GET /api/reports** without an Authorization header.

**Correct:** return **401** with a Bearer challenge so the client supplies a token. Redirecting API clients to a web login page via 302 breaks client UX and protocols.

### Scenario 5 – Same OP, Different Audience

The web RP receives an OIDC ID token with **aud=company-web**. A client sends that token to an API expecting **aud=urn:reports-api**.

**Correct:** the API rejects the token; a valid JWT signature is not enough. An access token with the API's audience, scopes, profile-appropriate token type/claims, and trusted issuer is required.

### Scenario 6 – Writing a Custom `AuthenticationProvider` Just to "Read Payload"

A developer writes a provider that splits the JWT and reads **sub** without verifying the signature.

**Severe flaw:** an attacker can forge payloads. **Correct:** use JwtAuthenticationProvider/JwtDecoder properly configured with issuer, JWKS, aud, and validators; never parse credentials manually and set authenticated=true.

### Scenario 7 – Does Adding a Local Provider Make SSO Safer?

A team wants to add **DaoAuthenticationProvider** just to look up internal account roles after OIDC login.

**Unnecessary:** DaoAuthenticationProvider is for username/password authentication, not fetching roles for OIDC users. Use user mapping/authorities or a policy service after the OIDC ID token is verified.

### Scenario 8 – Multiple IdPs Logging In Together

The application supports both a corporate OP and a partner OP.

**Correct:** configure **two approved client registrations**, bind requests and callbacks to the selected provider, verify issuer, audience, nonce, state, and prevent mix-up. **Never** accept arbitrary issuer URLs from query parameters.

## 12. Pre-Production SSO Design Checklist

- [ ] Each request type routes to the right **SecurityFilterChain**; @Order and securityMatcher are verified.
- [ ] Web login endpoint **/oauth2/authorization/{registrationId}** and callback **/login/oauth2/code/{registrationId}** are handled by the chain with **oauth2Login()**.
- [ ] Bearer token APIs use the resource server chain and return **401**; unauthenticated browsers use the EntryPoint to redirect to login.
- [ ] Standard **AuthenticationProvider** implementations are used for OIDC/OAuth2/JWT; no custom token parsers or skipped verification.
- [ ] OIDC client registration declares **openid**, trusted issuer, client_id, exact redirect URI; state/PKCE/nonce protection and TLS are in place.
- [ ] ID tokens verify signature, issuer, RP audience, and expiration; API access tokens verify signature/introspection, issuer, API audience, expiration, and scopes/permissions.
- [ ] **AuthenticationEntryPoint** is distinct from **AccessDeniedHandler** and login **AuthenticationFailureHandler**; 403s do not trigger endless login loops.
- [ ] Browser sessions and stateless APIs are cleanly designed; cookies, CSRF, logout, and session expiration match each channel.
- [ ] SSO users are linked by **(issuer, subject)**, with internal authorization driven by trusted policies.
- [ ] Tested **missing token, invalid token, under-privileged session, failed callback, wrong audience, IdP unavailable, and proxy/cookie issues**.
- [ ] Logs capture enough detail to trace **chain/filter/provider/entrypoint** without leaking tokens/secrets/cookies.

**Key takeaway:** **SecurityFilterChain decides which security mechanism a request passes through; AuthenticationProvider validates that mechanism's credentials; AuthenticationEntryPoint initiates authentication when a request is unauthenticated.** For web SSO, the result is typically **redirect + OIDC ID token + browser session**; for APIs, it is typically **Bearer access token + 401/403**, without redirects.

## 13. Standard Sources for Further Reading

- [Spring Security 6.5 – Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): FilterChainProxy, filter chains, exception handling.
- [Spring Security 6.5 – Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): multiple SecurityFilterChains, @Order, securityMatcher, and requestMatchers.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): ProviderManager, AuthenticationProvider, AuthenticationEntryPoint, and SecurityContext.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): registration, authorization endpoint, callback, and OIDC scopes.
- [Spring Security – OAuth 2.0 Login Advanced](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): authorities mapping and OidcUserService.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JwtAuthenticationProvider, JwtDecoder, issuer, and audience.
- [Spring Boot – OAuth2](https://docs.spring.io/spring-boot/reference/security/oauth2.html): client, resource server, and redirect URL configuration.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token and identity validation rules.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): PKCE, CSRF, redirect protection, and security recommendations.
