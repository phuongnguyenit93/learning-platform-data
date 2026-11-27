# Testing CSRF, CORS, session fixation, and logout redirects

A Spring Authorization Server simultaneously handles requests from user browsers, OAuth client applications, and backend systems. Each request group carries credentials differently and introduces distinct risks. Disabling CSRF across the entire application just to make the token endpoint easier to call, or opening CORS to every origin so a SPA works, can leave login and consent pages in an unsafe state. Testing only successful logins without verifying session lifecycles and post-logout redirect targets still leaves the application exposed to session hijacking or open redirects.

This lesson establishes how to test four control groups in Spring Security and Spring Authorization Server: CSRF for browser session-based actions, CORS for cross-origin browser requests, session fixation after authentication, and post-logout redirects. The examples use common default endpoints; when an application changes endpoints or Spring Boot/Spring Security versions, align matchers and configurations with the actual endpoints.

## 1. Defining security boundaries properly

Before writing tests, distinguish the typical flows in an Authorization Server:

| Flow | Primary authentication mechanism | Controls to watch |
|---|---|---|
| Opening `/oauth2/authorize` | User session cookie at the Authorization Server | Valid session, login, client-managed `state`, consent, and CSRF for form POSTs |
| Submitting login or consent forms | Session cookie and form data | CSRF token, session fixation control |
| Calling `/oauth2/token` | Client authentication or public client info with authorization code and PKCE | Client authentication, code/PKCE checks, CORS if a SPA calls directly from the browser |
| Calling introspection or revocation | Client authentication per endpoint policy | Client authentication, permission boundaries, never relying on user login cookies |
| Logging out from Authorization Server login page | User session cookie | CSRF for POST, session invalidation, and safe redirect |
| OIDC RP-Initiated Logout | Protocol logout request, often with `id_token_hint` | Client verification, `post_logout_redirect_uri` check, and `state` preservation |

`state` in the authorization request helps the OAuth client correlate responses with the original request and protects the client's callback against certain CSRF attacks. `nonce` binds the ID token to the OIDC request. Neither value replaces a CSRF token for login forms, consent forms, or logout forms served by the Authorization Server.

An important rule is that CSRF protection is only needed for state-changing requests relying on credentials automatically sent by the browser, typically session cookies. The token endpoint usually receives requests from a client's backend or from a SPA using authorization code + PKCE; it must enforce the corresponding OAuth authentication mechanisms. CORS governs whether a browser is allowed to read a cross-origin response, whereas a CSRF token verifies that the request originated from a valid application context. The two mechanisms solve different problems.

## 2. Testing CSRF

### Why keep CSRF for login and consent?

CSRF occurs when a browser already holds a valid session cookie and is tricked by another site into sending a request on the user's behalf. The browser may automatically attach cookies to the Authorization Server. If the server checks only the cookie without requiring proof that the request originated from a legitimate page, an external website can trigger unintended actions.

In an Authorization Server, requests to evaluate include:

- Login form POST, if the application uses form login.
- Consent form POST when the user approves or denies scopes.
- Logout POST to terminate the session.
- Administrative forms or client configuration changes if served within the same application.

Spring Security enables CSRF protection by default for state-changing HTTP methods such as POST, PUT, PATCH, and DELETE. GET, HEAD, TRACE, and OPTIONS are considered safe by convention and do not require a CSRF token by default. Applications must never turn GET into a data-mutating operation.

For server-rendered forms, the CSRF token must be present in the form. Thymeleaf integrated with Spring Security can automatically insert a hidden field into POST forms. For hand-written HTML forms, add the token explicitly:

```html
<form action="/oauth2/authorize" method="post">
  <input type="hidden" name="client_id" value="web-client">
  <input type="hidden" name="state" value="state-from-authorization-request">
  <input type="hidden" name="_csrf" value="${csrfToken}">
  <button type="submit" name="consent_action" value="authorize">
    Approve
  </button>
</form>
```

The parameter name and token rendering must come from `CsrfToken` provided by Spring Security; never create static tokens or hardcode values. With a template engine, use the framework's built-in expressions to avoid accidentally printing an unevaluated expression into HTML.

### Exempting only appropriate protocol endpoints from CSRF

OAuth clients do not send a user session's CSRF token when calling the token endpoint. Therefore, certain protocol POST endpoints need to be excluded from the CSRF filter, but the exemption scope must be specific. The example below illustrates default back-channel endpoints protected by client authentication:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    RequestMatcher csrfExemptProtocolPosts = request -> {
        if (!"POST".equals(request.getMethod())) {
            return false;
        }
        return Set.of(
                "/oauth2/token",
                "/oauth2/introspect",
                "/oauth2/revoke"
        ).contains(request.getServletPath());
    };

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .csrf(csrf -> csrf.ignoringRequestMatchers(csrfExemptProtocolPosts))
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

    return http.build();
}
```

This is an illustrative example with default endpoints. If you customize `AuthorizationServerSettings`, update the matcher to match the actual URIs. If enabling device authorization or another back-channel POST endpoint, add that endpoint only after verifying that requests do not rely on user session cookies and have appropriate protocol authentication.

Do not include `/oauth2/authorize`, device verification pages, consent forms, `/login`, or `/logout` in the exemption list. In particular, consent POST requests typically go through the authorization endpoint and still require a CSRF token. Do not use `ignoringRequestMatchers(authorizationServerConfigurer.getEndpointsMatcher())` as a blanket shortcut for the entire Authorization Server if that endpoint matcher also covers browser interactions.

### Writing CSRF tests with MockMvc

Spring Security Test provides `csrf()` to send requests with a valid token. Tests should cover missing tokens, invalid tokens, and valid tokens:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CsrfSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginPostWithoutCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "secret"))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginPostWithInvalidCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "secret")
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginPostWithValidCsrfReachesAuthentication() throws Exception {
        mockMvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "wrong-password")
                        .with(csrf()))
                .andExpect(status().is3xxRedirection());
    }
}
```

In the last test, invalid login credentials still produce a redirect back to the login page with an error message; the purpose of the test is to confirm the request passes the CSRF filter and reaches authentication. Adjust status and URL assertions according to your actual `AuthenticationFailureHandler`.

Consent POST also needs independent testing. Sending a request without a CSRF token must be rejected before consent is recorded; sending a request with a valid token must proceed to checking the user, client, scopes, and authorization state. Do not assert only the status code: verify that persisted consent remains unchanged when a request is rejected by CSRF.

For token endpoints intentionally exempt from CSRF, tests must prove that requests are not blocked by the CSRF filter while still passing through client authentication and grant validation. A request missing client authentication may return an OAuth error such as `invalid_client`; what to avoid is returning `403` due to a browser CSRF token check. Then add a passing test with a valid client and valid PKCE to confirm the complete flow.

## 3. Testing CORS

### What does CORS protect?

A browser's Same-Origin Policy restricts JavaScript from reading responses from another origin. CORS lets a server declare which origins, methods, and headers are allowed to access resources cross-origin. CORS does not authenticate clients, does not replace CSRF protection, and does not prevent every cross-site request from reaching the server. For example, a simple HTML form can send a cross-site request even though JavaScript on another origin cannot read the response.

In OAuth/OIDC, `/oauth2/authorize` is usually opened via browser navigation and redirects between origins. That does not mean wide CORS must be enabled on the authorization endpoint. CORS is typically required when a SPA calls the token endpoint directly from JavaScript to exchange an authorization code with PKCE. Allow only the registered SPA origins and the methods/headers the flow actually needs.

### Restricted CORS configuration for the token endpoint

The example below allows a specific SPA to send POST requests to the token endpoint. Credential cookies are disabled because token requests should use OAuth client mechanisms and PKCE rather than relying on the Authorization Server's session cookie:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration tokenCors = new CorsConfiguration();
    tokenCors.setAllowedOrigins(List.of("https://app.example.com"));
    tokenCors.setAllowedMethods(List.of("POST"));
    tokenCors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    tokenCors.setAllowCredentials(false);
    tokenCors.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/oauth2/token", tokenCors);
    return source;
}
```

Enable CORS in the filter chain serving the token endpoint:

```java
http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .cors(Customizer.withDefaults());
```

This snippet integrates into the Authorization Server configuration shown earlier. If the token endpoint path has been changed, update the registered CORS path. CORS handling must run before authentication so preflight OPTIONS requests are not forced to authenticate like business requests.

Do not use `allowedOrigins("*")` on systems with cookies or browser credentials. When `allowCredentials` is enabled, origins must be specified explicitly; wildcards are not a substitute for a trusted origin list. Nor should you arbitrarily reflect the `Origin` header sent by the client. If multiple environments are needed, manage the origin list per environment configuration and validate it at startup.

### Testing preflight and rejected origins

Browsers typically send an OPTIONS preflight before cross-origin requests that use non-simple methods or headers. Tests must verify that valid origins receive appropriate CORS headers and unknown origins are rejected:

```java
@Test
void tokenEndpointAllowsConfiguredSpaOrigin() throws Exception {
    mockMvc.perform(options("/oauth2/token")
                    .header(HttpHeaders.ORIGIN, "https://app.example.com")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "authorization,content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.com"));
}

@Test
void tokenEndpointRejectsUnconfiguredOrigin() throws Exception {
    mockMvc.perform(options("/oauth2/token")
                    .header(HttpHeaders.ORIGIN, "https://evil.example")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
}
```

The status behavior for rejected CORS requests can depend on configuration and version; in every case, disallowed origins must never receive a valid `Access-Control-Allow-Origin` header. Add a test sending an actual POST request from an allowed origin and verify the response includes CORS headers. Testing preflight alone does not prove the endpoint processes tokens properly.

A CORS test suite should include a valid origin, a lookalike origin with a different hostname, HTTP instead of HTTPS, a different port, a disallowed method, a disallowed header, and a request without an `Origin` header. Ensure you do not accidentally open CORS on `/oauth2/authorize`, `/login`, `/logout`, or all of `/**` merely because a SPA needs to call `/oauth2/token`.

## 4. Testing session fixation

### Session ID rotation mechanism after login

Session fixation occurs when an attacker knows or controls a session ID before the user logs in, then exploits the application keeping that same ID after authentication. When a user logs in successfully, the session ID must be changed so the pre-authentication session cannot become the authenticated session.

Spring Security provides session fixation protection. On servlet containers supporting Servlet 3.1 or higher, the default strategy typically uses `changeSessionId`, which changes the ID of the current session. You can declare it explicitly so the policy is readable and easy to test:

```java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()));

    return http.build();
}
```

Other strategies include `newSession` or `migrateSession`, depending on the version and application requirements. `changeSessionId` retains the current session while changing its identifier; `newSession` creates a brand-new session; `migrateSession` creates a new session and copies existing attributes. Choose a strategy compatible with your servlet container and session-stored application data. Never choose `none` just to avoid changing the session in a test.

### Testing session ID before and after authentication

Tests should create a session before login, retain the old ID, perform a successful login, and verify that the post-authentication ID has changed:

```java
@Test
void sessionIdChangesAfterSuccessfulAuthentication() throws Exception {
    MockHttpSession preAuthSession = new MockHttpSession();
    String oldSessionId = preAuthSession.getId();

    MvcResult result = mockMvc.perform(post("/login")
                    .session(preAuthSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "correct-password"))
            .andExpect(authenticated())
            .andReturn();

    HttpSession authenticatedSession = result.getRequest().getSession(false);
    assertNotNull(authenticatedSession);
    assertNotEquals(oldSessionId, authenticatedSession.getId());
}
```

This test assumes the application has a user `alice` and the corresponding test password. If login succeeds through a custom `AuthenticationSuccessHandler`, keep the session ID check intact and adjust the data setup.

Also test session attributes that are intentionally preserved or cleared. For example, a UI locale attribute may be migrated to the new session; unauthenticated data must never be treated as proof of authentication. With a distributed session store such as Spring Session Redis, verify both that the new ID is persisted and that the old ID can no longer restore an authenticated session.

MockMvc is helpful for testing filter logic, but it does not fully simulate cookies and session behavior of a real servlet container. Have at least one integration test running on a production-equivalent container: obtain a cookie before login, log in, verify the cookie/session ID changes, and try reusing the old cookie. The old cookie must not access authenticated resources.

## 5. Testing logout and safe redirects

### Local logout on the Authorization Server

Local logout is typically a POST to `/logout` when CSRF protection is enabled. Spring Security clears the authentication and invalidates the session via logout handlers. You can configure a fixed target URL and clear the session cookie:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .invalidateHttpSession(true)
        .clearAuthentication(true)
        .deleteCookies("JSESSIONID")
        .logoutSuccessUrl("/login?logout"));
```

The cookie name must match the actual configuration; if using Spring Session, the cookie name may have been customized. `logoutSuccessUrl` in the example is a fixed path within the same application. Never read `redirect`, `returnUrl`, or `next` directly from query parameters and redirect without validation.

Logout tests should cover requests missing a CSRF token, requests with a valid token, exact redirect target, session invalidation, and cookie deletion if the application is configured to delete cookies:

```java
@Test
void logoutRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/logout").with(user("alice")))
            .andExpect(status().isForbidden());
}

@Test
void logoutInvalidatesSessionAndUsesFixedRedirect() throws Exception {
    MockHttpSession session = new MockHttpSession();

    mockMvc.perform(post("/logout")
                    .session(session)
                    .with(user("alice"))
                    .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"))
            .andExpect(cookie().maxAge("JSESSIONID", 0));

    assertTrue(session.isInvalid());
}
```

Some applications use a custom `LogoutSuccessHandler` or Spring Session, so response cookies may differ. In that case, test equivalent behavior: the old session ID is no longer valid, authentication is cleared, and redirects go only to allowed URLs. Never weaken tests by omitting the session invalidation check.

### OpenID Connect RP-Initiated Logout

OIDC logout has a broader scope than local logout: the relying party (RP) asks the OpenID Provider to end the SSO session and may redirect the user back to a registered callback. `post_logout_redirect_uri` must be validated against the client's registered URI list. Even a URI differing only in scheme, hostname, port, path, or trailing slash must be evaluated by the implementation's matching rules; never use substring checks such as `contains("example.com")`.

When registering the client, configure a specific post-logout URI, for example:

```java
RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("web-client")
        // Other client settings, grant types, and redirect URIs...
        .postLogoutRedirectUri("https://app.example.com/logout/callback")
        .build();
```

RP-Initiated Logout tests should verify:

- Registered URIs are accepted for the matching client and protocol conditions.
- Unregistered URIs, lookalike hostnames, scheme/port changes, or URIs pointing to external domains are rejected.
- `id_token_hint` is validated per provider rules; never accept an arbitrary token as proof of a valid session.
- `state` is returned intact in valid redirects so the RP can correlate it with the initial logout request.
- Missing or invalid `post_logout_redirect_uri` follows defined safe behavior, such as rendering a confirmation page or fixed completion page.
- Logout actually ends the session at the provider per policy, even when the redirect is rejected.

Do not confuse Spring Security's `logoutSuccessUrl` with OIDC's `post_logout_redirect_uri`. The first controls redirects after local logout inside the application; the second is a protocol parameter validated against registered clients. Never allow an arbitrary query parameter to override both policies.

## 6. Organizing filter chains to test the right scope

An Authorization Server typically needs one filter chain for OAuth2/OIDC endpoints and another chain for login pages, consent, or application UI. Chain order and matchers dictate which filters run. Configuring an overly broad chain can cause protocol endpoints to inherit web page policies, or consent pages to become accidentally exempt from CSRF.

A common organization pattern is:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    // Apply scoped CSRF and CORS configuration for protocol endpoints here.
    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()))
        .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessUrl("/login?logout"));

    return http.build();
}
```

This configuration skeleton illustrates the boundary between the two chains; merge the CSRF matcher and CORS source presented earlier into the Authorization Server chain. Consent pages may be served through the authorization endpoint, so confirm that the actual matcher and CSRF policy still require a token for consent POSTs. Filter chain configurations should be re-tested after every endpoint change or Spring Security/Spring Authorization Server upgrade.

## 7. Security test matrix

The following matrix helps avoid testing only happy paths:

| Category | Test case | Expected outcome |
|---|---|---|
| CSRF | Login POST without token | Rejected; no authentication created |
| CSRF | Login POST with invalid token | Rejected |
| CSRF | Consent POST without token | Rejected; consent not saved |
| CSRF | Logout POST without token | Rejected; session remains active |
| CSRF | Token endpoint without CSRF token but valid client | Passes CSRF filter and is processed per client auth, code, and PKCE |
| CORS | Preflight from allowed SPA origin | Returns CORS headers with matching origin and method |
| CORS | Unknown origin or lookalike hostname | No CORS permission; no valid allow-origin header returned |
| CORS | Method/header outside allowlist | Preflight rejected |
| Session fixation | Successful login from pre-auth session | Session ID changes after authentication |
| Session fixation | Reusing pre-login session ID | Cannot restore authenticated session |
| Local logout | Successful logout | Authentication cleared, session invalidated, and redirects to fixed URL |
| OIDC logout | Registered redirect URI | Redirects to exact URI and preserves `state` |
| OIDC logout | Unregistered redirect URI or external attacker origin | Does not redirect to untrusted URI |

Run tests with the same servlet container and session repository type as production. With Redis or a distributed session store, add tests verifying that the new session ID is persisted, the old session is invalidated, and behavior holds when the next request hits a different instance.

## 8. Pre-release checklist

- [ ] CSRF protection remains enabled for login, consent, logout, and session-based state-changing forms.
- [ ] The CSRF exemption list includes only evaluated back-channel POST endpoints; never exempt authorization/consent or logout.
- [ ] OAuth client authentication, PKCE, and authorization code checks still work after exempting the token endpoint from CSRF.
- [ ] CORS is enabled only on endpoints requiring cross-origin calls, with specific origins, methods, and headers.
- [ ] Wildcard origins are not used alongside credential cookies; CORS is never treated as a substitute for CSRF.
- [ ] Session ID rotates after authentication; the old session can no longer access protected resources.
- [ ] Logout requires a CSRF token, clears authentication, and invalidates the session.
- [ ] Post-local-logout redirects use a fixed URL or a strictly validated allowlist.
- [ ] OIDC `post_logout_redirect_uri` is verified against the registered client; `state` is preserved.
- [ ] Positive and negative tests exist for every control group, running on near-production configuration.

Effective security testing must prove both that legitimate requests succeed and that invalid requests are blocked at the proper protective layer. With Spring Authorization Server, keeping clear boundaries between session-based forms, OAuth/OIDC protocol endpoints, and SPA cross-origin requests ensures CSRF, CORS, session fixation, and logout redirects work properly without disrupting authorization flows.
