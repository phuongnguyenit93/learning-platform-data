# 9.2. HttpSessionOAuth2AuthorizationRequestRepository in the Servlet Flow

## 1. The Problem: How to Link the Callback to the Login Initiation?

In a Spring Security OAuth 2.0/OIDC Client application running on the **Servlet stack**, the Authorization Code Flow has a key characteristic: the login request starts at the application, travels through the browser to the Authorization Server/OpenID Provider, and then returns to the application via a callback. Between those two points in time, there may be many other requests, multiple browser windows, or multiple users logging in concurrently.

Example:

~~~text
GET /oauth2/authorization/company
    → Redirect to https://idp.example.org/authorize?...&state=RANDOM_STATE

User logs in at IdP
    → Redirect back to /login/oauth2/code/company?code=AUTH_CODE&state=RANDOM_STATE
~~~

Upon receiving the callback, the application must be able to answer these questions:

1. Does this callback belong to **a valid authorization request initiated earlier**?
2. Does the returned <code>state</code> value match the saved request?
3. Which **ClientRegistration**, redirect URI, and scopes did the application use when starting the flow?
4. If **PKCE** is used, where is the <code>code_verifier</code> corresponding to the authorization code located?
5. How can that information be retrieved after the browser has left the application and returned?

**<code>HttpSessionOAuth2AuthorizationRequestRepository</code>** is the default component of Spring Security OAuth2 Login Servlet that handles saving and looking up **<code>OAuth2AuthorizationRequest</code> in the HTTP session**. It helps Spring Security correlate the callback with the initiated login request and continue the Authorization Code Flow.

This class belongs to the package:

~~~java
org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository
~~~

> **Distinction:** This repository stores *the authorization code request waiting to complete*. It is not a store for access tokens, refresh tokens, ID Tokens, ClientRegistrations, or the SecurityContext after the user logs in.

## 2. Concepts Involved in Correlation

| Concept | Role | Relation to HTTP session |
|---|---|---|
| <code>OAuth2AuthorizationRequest</code> | Describes the request sent to the authorization endpoint: authorization URI, client ID, redirect URI, scopes, state, additional parameters, attributes | The object temporarily stored by the repository for callback lookup |
| <code>state</code> | Unpredictable value used to bind the authorization response to the authorization request and mitigate login CSRF | The value in the saved request; the callback must carry the matching state |
| <code>HttpSession</code> | Server-side storage tied to a browser session | Holds the authorization request between the outbound redirect and the return callback |
| Session cookie (<code>JSESSIONID</code> or another configured name) | Allows the browser to send back the HTTP session identifier | If the callback lacks the corresponding cookie, the server may fail to find the authorization request |
| <code>code</code> | Authorization code issued by the Authorization Server | Used to exchange for tokens after confirming the callback is valid |
| <code>code_verifier</code> (PKCE) | Single-use secret of the authorization request | May reside in the attributes of the authorization request stored by Spring Security |
| <code>ClientRegistration</code> | OAuth2/OIDC Client configuration for the provider | Looked up by registration ID; not stored by this repository |

### 2.1. What Does the Repository Store, and What Does It Not Store?

<code>OAuth2AuthorizationRequest</code> can contain important information:

- <code>authorizationUri</code>: URL of the provider's authorization endpoint.
- <code>authorizationGrantType</code>: typically <code>AuthorizationGrantType.AUTHORIZATION_CODE</code>.
- <code>responseType</code>: typically <code>code</code>.
- <code>clientId</code>, <code>redirectUri</code>, <code>scopes</code>.
- <code>state</code>: value used to correlate with the callback.
- <code>additionalParameters</code>: may contain parameters such as <code>nonce</code>, <code>code_challenge</code>, <code>code_challenge_method</code> depending on the flow.
- <code>attributes</code>: internal data allowing the client to continue the flow, such as the registration ID and PKCE verifier depending on Spring Security configuration.

An authorization request is **distinct from** an authorization response. In the callback, the Authorization Server returns <code>code</code>, <code>state</code>, or error information. The repository holds the **initiating request** side, not a store for authorization codes or issued access tokens.

## 3. Flow for Saving, Retrieving, and Removing the Authorization Request

Spring Security OAuth2 Login Servlet has two notable filters:

- **<code>OAuth2AuthorizationRequestRedirectFilter</code>** handles the login initiation path (default <code>/oauth2/authorization/{registrationId}</code>). It creates the <code>OAuth2AuthorizationRequest</code> via a resolver, saves the request using <code>AuthorizationRequestRepository</code>, and redirects the browser to the Authorization Server.
- **<code>OAuth2LoginAuthenticationFilter</code>** handles the callback (default <code>/login/oauth2/code/{registrationId}</code>). It retrieves the saved authorization request, combines it with the authorization response received from the callback, and performs authentication and token exchange.

Both filters must use **the same repository/state mechanism** so a request saved on the outbound leg can be found when the callback returns.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant B as Browser
    participant C as Spring Security Servlet Client
    participant S as HttpSession
    participant OP as OpenID Provider
    U->>B: Choose login with company
    B->>C: GET /oauth2/authorization/company
    C->>C: Resolve ClientRegistration, create state and authorization request
    C->>S: saveAuthorizationRequest(request)
    C-->>B: HTTP 302 to OP, carrying state
    B->>OP: GET /authorize?...&state=...
    OP->>U: Authenticate and ask consent if needed
    OP-->>B: HTTP 302 to callback?code=...&state=...
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>S: removeAuthorizationRequest(callback)
    S-->>C: Saved OAuth2AuthorizationRequest if state/session match
    C->>C: Create OAuth2AuthorizationExchange and verify correlation
    C->>OP: POST /token with authorization code and required data
    OP-->>C: Token response
    C->>C: Process OAuth2/OIDC authentication
    C-->>B: Login succeeded / failure handling
~~~

In a typical sequence:

**Step 1 — Initialize the authorization request.** The user accesses a URL such as <code>/oauth2/authorization/company</code>. Spring Security looks up <code>ClientRegistration</code>, generates a random state, builds the authorization request, and appends applicable parameters such as PKCE if configured.

**Step 2 — Save to the HTTP session.** Before redirecting, <code>OAuth2AuthorizationRequestRedirectFilter</code> calls the repository to save the authorization request. The browser receives the redirect response along with a session cookie if the session was created at that moment.

**Step 3 — Redirect to the provider.** The provider receives the authorization request with <code>state</code>, but does not receive the application's HTTP session contents. With PKCE S256, the provider receives <code>code_challenge</code> and must not receive <code>code_verifier</code> in the authorization URL.

**Step 4 — Callback returns.** The browser redirects to <code>/login/oauth2/code/company</code> with <code>code</code> and <code>state</code>. The browser must also send back the matching session cookie so the application reads the right session.

**Step 5 — Look up and consume the request.** <code>OAuth2LoginAuthenticationFilter</code> calls the repository to retrieve and delete the corresponding authorization request. If the session or state does not match, building the authorization exchange cannot validly proceed.

**Step 6 — Exchange tokens and complete authentication.** The client uses the authorization code along with the original request details to call the token endpoint. With OIDC, the client verifies the ID Token against issuer, audience, signature, and applicable rules before considering the user authenticated.

> **Deleting the authorization request after use** is critical: the pending callback state has the lifetime of a single login attempt and must not be reused.

## 4. The AuthorizationRequestRepository Contract

<code>HttpSessionOAuth2AuthorizationRequestRepository</code> implements:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Core methods:

~~~java
OAuth2AuthorizationRequest loadAuthorizationRequest(HttpServletRequest request);

void saveAuthorizationRequest(
    OAuth2AuthorizationRequest authorizationRequest,
    HttpServletRequest request,
    HttpServletResponse response);

OAuth2AuthorizationRequest removeAuthorizationRequest(
    HttpServletRequest request,
    HttpServletResponse response);
~~~

These are abbreviated API signatures for learning; in Spring Security 6 the Servlet types live in the <code>jakarta.servlet.http</code> namespace.

| Method | Typical timing | Effect |
|---|---|---|
| <code>saveAuthorizationRequest(...)</code> | Before redirecting to the Authorization Server | Writes the authorization request to the backing store |
| <code>loadAuthorizationRequest(...)</code> | When reading a request awaiting callback | Returns the matching request if state is valid, otherwise returns <code>null</code> |
| <code>removeAuthorizationRequest(...)</code> | When processing the callback and consuming the original request | Returns the matching request while removing the used state |

### 4.1. How the Default Implementation Checks State

In the default session implementation, the repository relies on <code>state</code> in the callback to match against the <code>state</code> of the authorization request stored in the session. If the request has no state, there is no matching session/request, or the state differs, loading does not return a valid authorization request.

Conceptual logic description:

~~~text
loadAuthorizationRequest(callback):
    callbackState = callback.query["state"]
    savedRequest = session.authorizationRequest
    if callbackState is empty or savedRequest does not exist:
        return null
    if callbackState != savedRequest.state:
        return null
    return savedRequest

removeAuthorizationRequest(callback):
    request = loadAuthorizationRequest(callback)
    if request is valid:
        remove saved request from session
    return request
~~~

This is **pseudocode**, not Spring Security's internal source code. The key takeaway is that the repository does not trust a callback merely because it has a syntactically valid <code>code</code>; it must locate the request the client actually issued and verify `state`.

### 4.2. The Default Typically Stores One Authorization Request at a Time

<code>HttpSessionOAuth2AuthorizationRequestRepository</code> by default stores **a single current authorization request in one session attribute** rather than maintaining a map of multiple independent requests keyed by state.

For example, when a user opens two tabs sharing the same HTTP session:

~~~text
Tab A: starts login A → saves request A (state=A)
Tab B: starts login B → overwrites with request B (state=B)
Tab A: callback arrives with state=A → session currently holds state=B
Result: repository cannot find a matching request for A
~~~

Tab B's flow may still succeed if request B has not been replaced and the session still exists. When an application frequently handles parallel logins, multiple tabs, or multiple concurrent providers, consider a custom repository supporting multiple authorization requests keyed by state, with clear bounds on count and lifetime.

Do not jump to the conclusion that a state error is always an attack; Tab B overwriting request A is a real-world operational cause.

## 5. Default Configuration in Spring Boot OAuth2 Login

With Spring Boot 3 and Spring Security 6, declaring the OAuth2 Client starter and a ClientRegistration is enough to get started with Servlet OAuth2 Login:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Example <code>application.yml</code> for an OIDC provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: company-web
            client-secret: replace-with-secret-from-secure-storage
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

These URIs and credentials are placeholders. In real deployments, load the client secret from a secret manager/environment variable and register the exact redirect URI on the OP. <code>issuer-uri</code> is the base issuer, not the Discovery Document URL.

A minimal security bean:

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
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

When calling <code>.oauth2Login(Customizer.withDefaults())</code>, Spring Security configures the OAuth2 Login components, where the default authorization request repository for Servlet is **<code>HttpSessionOAuth2AuthorizationRequestRepository</code>**. For standard use cases, you do not need to instantiate the repository manually in Java.

The application initiates the flow from:

~~~text
GET /oauth2/authorization/company
~~~

The IdP redirects back to the callback:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

The filter handling the callback must see **the same HTTP session** where the authorization request was previously saved.

## 6. Declaring the Repository Explicitly in Java

When you want to configure the correlation component yourself, you can explicitly supply a repository instance to OAuth2 Login's authorization endpoint:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

@Configuration
public class ExplicitAuthorizationRequestRepositoryConfig {

    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
            authorizationRequestRepository() {
        return new HttpSessionOAuth2AuthorizationRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)));

        return http.build();
    }
}
~~~

This is an **alternative configuration** to the <code>SecurityFilterChain</code> bean in section 5; do not declare both beans simultaneously unless you have an explicit multi-chain design. Calling <code>authorizationRequestRepository(repository)</code> on the OAuth2 Login DSL is the standard way to instruct Spring Security to use the specified repository in the flow.

This configuration still relies on the HTTP session and does not change the default correlation mechanism. The value of explicit configuration is the ability to swap in another repository implementation or control dependencies in your application design.

**Note:** Registering an <code>AuthorizationRequestRepository</code> bean in the Spring context **does not mean every filter will automatically use it** across all versions or configurations. Configure it via the OAuth2 Login DSL or framework-supported extension points rather than assuming creating a bean alone is sufficient.

### 6.1. When Should You Configure It Manually?

- The application wants to change where authorization requests are stored (for example, a state-keyed repository supporting multiple tabs or an appropriate backend store).
- You need to control behavior across multiple providers/tenants or attach internal metadata during the flow.
- You want to pass the same repository to related components when customizing the authorization request resolver or OAuth2 Login filter.
- You need to test scenarios involving lost state/session, invalid callbacks, or concurrent logins.

If you have no special requirements, keeping the default configuration reduces the amount of code you have to maintain.

## 7. Observing the save, load, and remove APIs with Spring Mock Servlet

The example below illustrates repository behavior **without calling an Authorization Server**. It demonstrates that the request is only retrieved when the callback carries the right state and the same session.

In a Spring Boot project, <code>spring-boot-starter-test</code> typically provides <code>spring-test</code> along with the mock servlet objects.

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

class AuthorizationRequestRepositoryExampleTest {

    @Test
    void callbackMustUseSameSessionAndState() {
        var repository = new HttpSessionOAuth2AuthorizationRequestRepository();

        var authorizationRequest = OAuth2AuthorizationRequest.authorizationCode()
            .authorizationUri("https://idp.example.org/oauth2/authorize")
            .clientId("company-web")
            .redirectUri("https://app.example.org/login/oauth2/code/company")
            .state("random-state-for-this-example")
            .build();

        var start = new MockHttpServletRequest(
            "GET", "/oauth2/authorization/company");
        var startResponse = new MockHttpServletResponse();

        // Save the request before the browser leaves the application.
        repository.saveAuthorizationRequest(
            authorizationRequest, start, startResponse);

        var session = (MockHttpSession) start.getSession(false);
        assertNotNull(session);

        // Callback with the same session and matching state.
        var callback = new MockHttpServletRequest(
            "GET", "/login/oauth2/code/company");
        callback.setSession(session);
        callback.setParameter("state", "random-state-for-this-example");

        var loaded = repository.loadAuthorizationRequest(callback);
        assertNotNull(loaded);
        assertEquals(authorizationRequest.getState(), loaded.getState());

        var removed = repository.removeAuthorizationRequest(
            callback, new MockHttpServletResponse());
        assertNotNull(removed);
        assertNull(repository.loadAuthorizationRequest(callback));
    }
}
~~~

This is a **repository API**-level example, not an end-to-end OAuth2 Login test: it does not verify the authorization code at the token endpoint, the ID Token, or the SecurityContext. The fixed state string is purely illustrative; in a real system, Spring Security generates an unpredictable value per flow.

### 7.1. Callback with Wrong State

If the same session is reused but the state is changed:

~~~java
callback.setParameter("state", "unrelated-state");
OAuth2AuthorizationRequest result =
        repository.loadAuthorizationRequest(callback);
assertNull(result);
~~~

This callback is not treated as an authorization response for the saved request. In a real flow, Spring Security can handle this as a login failure because no matching authorization request was found.

### 7.2. Callback in a Different Session

If a new callback request is created **without attaching** the previous <code>MockHttpSession</code>:

~~~java
var differentBrowser = new MockHttpServletRequest(
    "GET", "/login/oauth2/code/company");
differentBrowser.setParameter(
    "state", "random-state-for-this-example");

assertNull(repository.loadAuthorizationRequest(differentBrowser));
~~~

Even with the same state, the repository still cannot find the request because there is no HTTP session holding the corresponding authorization request. This is an essential property that binds the callback to the session that initiated login.

## 8. How Do State, Session, and PKCE Work Together?

These three elements address different parts of the Authorization Code Flow:

| Element | Where does it appear? | What does it protect? |
|---|---|---|
| <code>state</code> | Authorization request and callback | Correlates the authorization response with the initial request; reduces login CSRF risk |
| HTTP session | In the browser via an identifying cookie, actual data on the server | Helps the Client look up the authorization request and needed context on callback |
| PKCE <code>code_verifier</code> | Held by Client on start, sent to token endpoint on code exchange | Binds the authorization code to the party that initiated the authorization request |

With PKCE S256:

~~~text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
~~~

When sending the authorization request, the Client may send <code>code_challenge</code> and <code>code_challenge_method=S256</code> to the OP, while keeping <code>code_verifier</code> inside the internal attributes of the saved authorization request. When the callback returns and state/session match, Spring Security retrieves that verifier to include in the token request.

If a custom repository only stores <code>state</code> and <code>redirectUri</code> and drops the attributes of <code>OAuth2AuthorizationRequest</code>, PKCE can fail even if the callback has the right state. Therefore, when replacing the repository, preserve **all information needed by the token exchange**, not just the two parameters visible in the URL.

### 8.1. Is OIDC Nonce the Same as State?

No. In OIDC, <code>nonce</code> (when used) binds the **ID Token** to the authentication request; it is sent in the authorization request and verified according to OIDC rules. <code>state</code> binds the **authorization response/callback** to the authorization request.

Spring Security may store the data needed to verify `nonce` inside the authorization request/attributes, depending on the flow and version. Do not substitute `nonce` for <code>state</code> or skip validating ID Token issuer, audience, and signature just because a session exists.

## 9. Why Does a Callback Lose Its Session?

An HTTP session is typically identified by a browser cookie, such as <code>JSESSIONID</code> (the exact name depends on the Servlet container, Spring Session, and application config). When the browser leaves the application for the IdP and returns, the cookie must be sent back according to browser and server rules.

Some common causes:

**Cookie is not sent on callback.** The cookie is blocked by an inappropriate <code>SameSite</code>, <code>Secure</code>, <code>Domain</code>, or <code>Path</code> configuration. For Authorization Code Flow callbacks via **top-level GET**, <code>SameSite=Lax</code> normally allows sending cookies on cross-site navigation; if the provider uses <code>response_mode=form_post</code> (cross-site POST), cookie behavior may differ and requires careful configuration.

**Session expired or was invalidated.** The user lingered on the IdP page, the application timed out the session, the user logged out in another tab, or some component called <code>invalidate()</code>, wiping out the pending callback data.

**Multiple instances do not share sessions.** The start request hit instance A, the callback hit instance B, and B lacks the corresponding session. A load balancer without sticky sessions or a system lacking a shared session store can cause intermittent failures.

**Host/port/scheme changed.** The start URL used <code>localhost</code> while the callback used an internal IP or a different domain; cookies scoped to the original host will not be sent by the browser. A reverse proxy misconfiguring external host/scheme also breaks the redirect URI or cookie.

**Multiple tabs overwrite the authorization request.** A second tab creates a new request in the same session; the first tab calls back with an old state and cannot find a matching request.

**Custom repository loses data.** Incomplete serialization/deserialization of <code>OAuth2AuthorizationRequest</code>, saving under the wrong key, or using different repositories between start and callback can prevent the data from being retrieved.

### 9.1. Cookies and Browser Policies

Cookie attributes to understand:

| Attribute | Role | Impact on callback |
|---|---|---|
| <code>Secure</code> | Cookie is only sent over appropriate secure connections | Production apps use HTTPS; requires accurate proxy and cookie configuration |
| <code>HttpOnly</code> | Restricts JavaScript from reading the cookie | Protects session cookie from script access; does not itself decide whether callback sends it |
| <code>SameSite</code> | Controls cookie sending in cross-site contexts | Affects GET or POST redirects from the IdP |
| <code>Domain</code> | Host scope of the cookie | Callback to a different host may not receive the cookie |
| <code>Path</code> | URL path scope of the cookie | Callback outside the cookie path may lack the session |
| <code>Max-Age</code>/<code>Expires</code> | Cookie lifetime | Cookie expiring before callback leads to missing session |

<code>SameSite=None</code> should only be chosen when there is a clear cross-site requirement and must be paired with <code>Secure</code> per modern browser rules. Do not disable cookie protections application-wide to work around a callback error before identifying the root cause.

### 9.2. Multi-Instance Applications with Spring Session

In a multi-instance architecture, you can use Spring Session with a shared store (such as Redis) so all nodes access the same HTTP session via the browser cookie. Then an authorization request stored in the session can be accessed regardless of which node receives the callback, provided all nodes use compatible session configurations.

Do not confuse <code>HttpSessionOAuth2AuthorizationRequestRepository</code> with a standalone Redis repository: this repository still accesses the <code>HttpSession</code> interface; **Spring Session** is what changes how HTTP session data is persisted underneath.

Pay attention to object serializability in the session, latency, timeouts, and concurrent update behavior when using distributed sessions. If you add custom attributes to the authorization request, they must also be compatible with session storage.

## 10. Multiple Filter Chains: Start and Callback Must Hit the Right Chain

Spring Security Servlet can have multiple <code>SecurityFilterChain</code> beans. <code>FilterChainProxy</code> picks **the first chain** whose matcher matches. If the start URL and callback URL hit chains without compatible OAuth2 Login configuration, the flow can fail before the repository is even invoked.

Common pitfall:

~~~java
http
    .securityMatcher("/app/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2Login(Customizer.withDefaults());
~~~

This chain does not match the default endpoints:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
~~~

Therefore, merely having <code>oauth2Login()</code> inside a chain is not enough if that chain does not cover the login infrastructure URLs.

### 10.1. Designing Separate API Chain and Web Chain

Example separating API from web:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultipleChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        // Web chain catches all remaining URLs, including start and callback.
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This example requires adding the resource-server dependency and valid JWT decoder/issuer configuration for the API if you want to run bearer token APIs. Web OAuth2 Login still needs the OAuth2 Client dependency and ClientRegistration. The two configurations serve different security roles.

Here:

| Request | First matching chain | Goal |
|---|---|---|
| <code>/api/orders</code> | API <code>@Order(1)</code> | Authenticate with bearer JWT |
| <code>/oauth2/authorization/company</code> | Web <code>@Order(2)</code> | Save authorization request, redirect to IdP |
| <code>/login/oauth2/code/company</code> | Web <code>@Order(2)</code> | Load/remove authorization request, handle code and state |
| <code>/dashboard</code> | Web <code>@Order(2)</code> | Serve logged-in user |

If the web chain has a narrow <code>securityMatcher</code>, it must include the authorization start endpoint, callback, login page, and related URLs. Simply adding <code>.requestMatchers("/login/oauth2/code/**").permitAll()</code> in <code>authorizeHttpRequests</code> will not route the callback into the chain if <code>securityMatcher</code> already excluded the request up front.

### 10.2. Do Not Arbitrarily Make Web OAuth2 Login Stateless

Bearer-JWT-only APIs usually fit <code>SessionCreationPolicy.STATELESS</code>. However, Servlet OAuth2 Login by default needs to retain the authorization request across browser redirects. If the web chain is configured as <code>STATELESS</code> without an explicitly designed alternative state-storage solution, retaining sessions and completing authentication may no longer work as expected.

Do not assume that <code>STATELESS</code> makes <code>HttpSessionOAuth2AuthorizationRequestRepository</code> automatically switch to another store. This repository specifically writes to `HttpSession`; a sessionless architecture requires proactively changing how authorization requests and authentication are stored, along with a security review.

## 11. Custom Repository When Multiple Parallel Authorization Requests Are Needed

The default of one request per session suffices for many apps, but does not always fit when users open multiple tabs, switch providers in rapid succession, or leave one login flow pending while starting another.

One extension approach is storing a **Map keyed by state** in the HTTP session:

~~~text
session["PENDING_AUTHORIZATION_REQUESTS"] =
    {
      "state-A": OAuth2AuthorizationRequest-A,
      "state-B": OAuth2AuthorizationRequest-B,
      ...
    }
~~~

A custom <code>AuthorizationRequestRepository<OAuth2AuthorizationRequest></code> implementation can follow this principle:

~~~text
save(request):
    verify request.state exists
    get map from session, or create new
    put an entry with key = request.state
    write map back to session

load(callback):
    get state from callback
    access only the map of the matching session
    return request with matching state key, if present

remove(callback):
    get request with matching state key from session
    remove only that entry
    return the removed request
~~~

This is a conceptual design, not production-ready code. When building your own:

- `state` must be sufficiently random and unique per authorization request.
- Never accept an arbitrary `state` from a callback to synthesize a new request.
- Do not lose PKCE verifier, `nonce`, registration ID, or data needed for token exchange.
- Remove entries upon use and clean up expired entries to prevent unbounded growth in the session.
- Cap the number of pending requests per session; do not let a user create unlimited authorization requests to exhaust memory.
- Handle concurrent updates across tabs/requests and ensure compatibility with distributed sessions if deployed across multiple nodes.
- Avoid logging the map since authorization requests may contain sensitive details.

You do not need a custom repository merely because your app supports multiple providers: one session can still log in sequentially; the need for customization arises when you want multiple **concurrently pending authorization attempts** or non-default state management.

### 11.1. Why Not Put the Entire Request in a Cookie?

Some online examples replace the HTTP session with a cookie containing the serialized authorization request. This approach requires careful consideration:

- If the cookie contains a verifier, nonce, or sensitive data, you must protect confidentiality and integrity; Base64 is not encryption.
- Cookies have size limits and are subject to domain, path, SameSite, Secure, and HttpOnly rules.
- You must prevent the client from tampering with data to alter the redirect URI, registration ID, or attributes.
- You must enforce expiration, clear the cookie after callback, and account for multiple tabs or colliding cookies.

A poorly designed cookie-based repository can introduce greater security risks than the original session issue. In standard Servlet applications, prefer HTTP sessions or a protected server-side state store.

## 12. Distinguishing from Other Repositories/Services in Spring Security

Components with similar names store different kinds of data:

| Component | Data stored/looked up | Lifecycle |
|---|---|---|
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | Authorization request awaiting callback | From authorization redirect until callback or timeout |
| <code>ClientRegistrationRepository</code> | Client and provider metadata such as client ID, endpoints, scopes | Typically throughout application runtime |
| <code>OAuth2AuthorizedClientRepository</code> | Authorized client bound to principal/request, including issued tokens | After token exchange completes |
| <code>OAuth2AuthorizedClientService</code> | Authorized clients by registration/principal, typically for service-layer | Per persistence/token policy |
| <code>SecurityContextRepository</code> | SecurityContext containing request/user Authentication | Across requests, per session/context strategy |
| <code>RequestCache</code> | Saved request the user tried to access before login | Useful for redirecting the user back to the target page after login |

For example: a user initially visits <code>/dashboard</code> and is redirected to the IdP. <code>RequestCache</code> can remember <code>/dashboard</code> to return to after login; **<code>HttpSessionOAuth2AuthorizationRequestRepository</code> remembers the authorization request along with state** to process the callback. Both mechanisms may use the session, yet they solve completely different problems.

Similarly, completing the callback does not mean the authorization request should be kept around to reuse access tokens. Tokens are managed via authorized client components if the application needs to store and use tokens in subsequent requests.

## 13. Diagnosing Callback and Correlation Failures

### 13.1. From Symptom to Cause

| Symptom | Cause to inspect | How to resolve |
|---|---|---|
| <code>authorization_request_not_found</code> or equivalent error | Callback cannot find request by session/state | Check same session cookie, state, repository, and chain |
| Login succeeds at OP, but callback returns 404 | Callback URL did not hit a chain with <code>OAuth2LoginAuthenticationFilter</code> or filter processing URI mismatches | Check redirect URI, `securityMatcher`, filter chain order |
| Callback returns 401/403 | API/basic chain blocked the request, authorization rule, or request method/CSRF mismatch | Find the first matching chain, inspect callback policy |
| First login works, opening a second tab breaks the first tab | Later request overwrote earlier request in session | Limit concurrent flows or use a multi-entry state-keyed repository |
| Intermittent failures in multi-instance setups | HTTP session not shared, inconsistent routing or session persistence | Check sticky sessions/Spring Session/session store |
| Callback has valid state but repository load returns <code>null</code> | Lost session, state mismatch, or session saved a newer request | Verify cookie/session ID and request lifecycle |
| Token endpoint returns <code>invalid_grant</code> after callback is received | Code expired/reused, wrong redirect URI/PKCE | Inspect token exchange after confirming correlation |
| After login, target page remains anonymous | SecurityContext not saved/read as expected or target page chain has different policy | Inspect SecurityContextRepository, session, and target page's chain |
| Cross-site POST callback lacks cookie | Cookie SameSite or CSRF/method policy incompatible with <code>form_post</code> | Evaluate callback method, cookie policy, and controlled CSRF protection |
| OIDC login reports issuer/nonce mismatch | ID Token does not match OP/authorization request | Check issuer, registration, nonce, and library validation |

### 13.2. Practical Troubleshooting Order

When encountering a callback error, inspect points in dependency order:

1. **Actual callback URL:** host, scheme, path, registration ID, and HTTP method.
2. **SecurityFilterChain:** which chain does the callback request match first; does that chain have the OAuth2 Login filter?
3. **HTTP session:** did the browser send the same session cookie as on login initiation; does the session still exist on the node receiving the callback?
4. **State:** does the callback have `state`, and does `state` match the stored authorization request?
5. **Repository:** do start and callback use the same repository and the same key/storage?
6. **PKCE/nonce:** did the authorization request retain the attributes needed until token exchange?
7. **Provider response:** is the authorization code still valid, is the redirect URI valid, and are the token/ID Token verified properly?

An error in an earlier step can mask later ones. For example, if the callback is intercepted by an API chain, the web repository may never be called at all; do not prematurely conclude it is a state mismatch.

### 13.3. Enabling Logs for Observability

In a development environment, you can temporarily enable relevant Spring Security logs:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security.oauth2.client: DEBUG
~~~

Log levels and category names may vary by version. Use logs to observe chains/filters and error types, but **never record raw authorization codes, state, PKCE verifiers, client secrets, access tokens, refresh tokens, or ID Tokens** in logs, tickets, analytics tools, or screenshots. Those values can be sensitive or usable within a short window.

If adding application logging around the flow, log only the registration ID, endpoint name, a safe request correlation ID, success/failure status, and sanitized error codes. There is no need to log the raw contents of <code>OAuth2AuthorizationRequest</code>.

## 14. Common Misconceptions

**“If a callback has state, it must be valid.”** No. `state` must match an authorization request saved in **the right session**; a state string supplied by the client alone is not enough.

**“The repository stores the authorization code and tokens.”** No. It stores the initial request. The authorization code arrives in the callback, while tokens are handled after token exchange via other components.

**“Just enabling oauth2Login ensures you never lose sessions.”** No. Cookie policies, session timeouts, load balancers, reverse proxies, and multiple tabs can lose or overwrite authorization requests.

**“Two login tabs won't affect each other because their states are different.”** Not with the default implementation holding a single current request in the session. A tab opened later can overwrite the earlier tab's request.

**“Switching the entire app to STATELESS makes OAuth2 Login simpler.”** No. HTTP session is the default mechanism to hold the authorization request between two redirects in Servlet; changing it requires designing another state store and authentication persistence strategy.

**“Just adding permitAll for the callback is enough.”** No. The request must first route to a chain containing the OAuth2 Login filter before authorization rules apply. <code>securityMatcher</code> and chain ordering govern this.

**“The PKCE verifier can be recovered from code_challenge.”** No. With S256 and a strong random verifier, the challenge is one-way derived. The Client must retain the original verifier in the authorization request state until token exchange.

## 15. Exercises and Practical Scenarios

### Scenario A: Callback from Another Session

Browser A initiates login with session <code>S1</code> and state <code>V1</code>. Browser B sends a callback containing the exact string <code>V1</code> but without the cookie for <code>S1</code>.

**Question:** Will the repository find the authorization request?

**Answer:** No. The repository relies on the HTTP session; B does not have the session containing A's request. Even if it knows the state, B does not own the corresponding authorization request state inside A's session.

### Scenario B: Two Tabs Sharing One Session

~~~text
Tab A: state=A, saves request A to session
Tab B: state=B, saves request B to the same session
Tab A: callback state=A
~~~

**Question:** What is likely to happen with the default implementation?

**Answer:** Request B may have replaced request A. Tab A's callback cannot find a request with state A, so authentication cannot continue. If concurrent authorization attempts are a business requirement, consider a custom repository keyed by state.

### Scenario C: PKCE Lost When Switching Repositories

The development team replaces the session repository with a mechanism that only saves JSON containing <code>state</code> and <code>redirectUri</code>. The callback has a matching state, yet the token endpoint rejects the code.

**Explanation:** If the Client uses PKCE, <code>code_verifier</code> and attributes needed for token exchange may be lost when serialization is stripped down. A custom repository must preserve the full authorization request and flow-related data intact.

### Scenario D: API Chain Intercepts the Callback

~~~text
@Order(1): securityMatcher("/login/**", "/api/**"), httpBasic()
@Order(2): securityMatcher("/app/**", "/login/oauth2/code/**"), oauth2Login()
~~~

**Question:** Which chain handles the callback <code>/login/oauth2/code/company</code>?

**Answer:** The first chain matches <code>/login/**</code> first, so the chain containing OAuth2 Login is not selected. You must narrow the first chain's matcher or redesign chain precedence so start and callback hit the right flow.

### Hands-On Exercise: Observing Session Request Lifecycle

1. Create a Spring Boot Servlet web app with <code>spring-boot-starter-oauth2-client</code> and a test OIDC ClientRegistration.
2. Enable <code>oauth2Login()</code>; visit <code>/oauth2/authorization/{registrationId}</code>.
3. Observe the redirect response and the presence of the session cookie without copying secret values into logs.
4. Complete login via the OP and verify the callback uses the same session.
5. Use the Mock Servlet example to invoke <code>saveAuthorizationRequest</code>, <code>loadAuthorizationRequest</code>, and <code>removeAuthorizationRequest</code>; observe the request disappearing after removal.
6. Test a callback with a different state or a different session in the test environment; explain why load returns <code>null</code>.
7. Try initiating login twice in the same session before completing the first attempt and observe the effect of the later saved request.

These exercises focus on **correlation and the authorization request lifecycle**. End-to-end OAuth2/OIDC testing requires a proper test Authorization Server to issue real codes and tokens according to protocol.

## 16. Summary

- **<code>HttpSessionOAuth2AuthorizationRequestRepository</code>** is the default Servlet implementation using the HTTP session to store <code>OAuth2AuthorizationRequest</code> between the authorization redirect and the callback.
- <code>OAuth2AuthorizationRequestRedirectFilter</code> saves the request before redirecting to the IdP; <code>OAuth2LoginAuthenticationFilter</code> retrieves/removes the request on callback and uses it to continue authentication.
- Correlation depends on **the right HTTP session and the right state**. The PKCE verifier and related data must be preserved if the flow uses PKCE.
- The default implementation typically holds **one authorization request at a time in the session**; multiple concurrent login tabs can overwrite state.
- The callback must land in a **SecurityFilterChain containing the OAuth2 Login filter**, and the cookie/session must be returned by the browser and exist on the node receiving the callback.
- If replacing the repository, preserve complete authorization request data, protect confidentiality/integrity, handle single-use consumption, expiration, and concurrent updates.

### References

- **Spring Security Reference — OAuth2 Login (Servlet):** authorization endpoint, redirection endpoint, authorization request repository, and login filters.
- **Spring Security Java API — <code>HttpSessionOAuth2AuthorizationRequestRepository</code> and <code>AuthorizationRequestRepository</code>:** <code>load</code>, <code>save</code>, and <code>remove</code> contracts.
- **Spring Security Java API — <code>OAuth2AuthorizationRequestRedirectFilter</code> and <code>OAuth2LoginAuthenticationFilter</code>:** usage points of the authorization request repository.
- **Spring Security Reference — Servlet Architecture:** <code>FilterChainProxy</code>, <code>SecurityFilterChain</code>, and matcher selection.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization request, <code>state</code>, authorization response, and authorization code grant.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code verifier/challenge and safer authorization code exchange.
- **OpenID Connect Core 1.0:** authorization code flow, nonce, and ID Token verification rules.
