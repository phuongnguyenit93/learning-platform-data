# Filter Chain Ordering, securityMatcher, and requestMatcher

## 1. Why does filter chain ordering matter for an Authorization Server?

When implementing an **OAuth 2.0 / OpenID Connect Authorization Server** using **Spring Security** and **Spring Authorization Server** in a Spring Boot application, an HTTP request can target several functional groups: token issuance endpoints, OIDC endpoints, user login pages, business APIs, or static assets. These groups typically require **different authentication mechanisms, login sessions, and protection policies**.

Spring Security lets you define multiple <code>SecurityFilterChain</code> beans. However, a request **does not run sequentially through every matching chain**. <code>FilterChainProxy</code> picks **the first chain whose matcher matches** in the ordered list, then runs that chain's filters. This rule means placing <code>@Order</code>, <code>securityMatcher</code>, and <code>requestMatchers</code> in the right positions directly affects the correctness and security of the Authorization Server.

Lesson goals:

1. Distinguish **ordering between SecurityFilterChains**, **filter ordering inside a chain**, and **authorization rule ordering**.
2. Explain accurately where <code>securityMatcher</code>, <code>requestMatchers</code>, and <code>anyRequest</code> are evaluated.
3. Configure separate chains for Spring Authorization Server, a Bearer-token API, and the login UI.
4. Trace an actual request and diagnose issues where a chain intercepts the wrong requests, an endpoint is left unprotected, or unexpected 404/401/403 responses occur.
5. Verify chain ordering with Spring Security tests rather than merely inspecting the configuration.

Running example throughout: the application has an **Authorization Server** at <code>/oauth2/**</code> and OIDC endpoints, an **Orders API** at <code>/api/orders/**</code>, and a <code>/login</code> page serving form-based login.

## 2. The big picture: where does a request go?

In a Spring MVC application running on Servlet, the overall path is as follows:

~~~mermaid
flowchart TD
    A["HTTP request arrives at Servlet container"] --> B["DelegatingFilterProxy: springSecurityFilterChain"]
    B --> C["FilterChainProxy"]
    C --> D{"Select first SecurityFilterChain where matches(request) = true"}
    D --> E["Security filters of the selected chain"]
    D --> N["No matching chain: request is not protected by Spring Security"]
    E --> F{"Did a filter handle or terminate the request?"}
    F -- "Yes" --> G["Return redirect / response / authentication error"]
    F -- "No" --> H["DispatcherServlet / controller / target resource"]
    N --> H
~~~

Each component has a distinct responsibility:

| Component | Responsibility |
| --- | --- |
| <code>DelegatingFilterProxy</code> | Bridges the container's Servlet Filter mechanism to the Spring bean named <code>springSecurityFilterChain</code>. |
| <code>FilterChainProxy</code> | Holds the list of <code>SecurityFilterChain</code> beans and selects the **first chain** matching the request. |
| <code>SecurityFilterChain</code> | Consists of a <code>RequestMatcher</code> deciding whether the chain applies and an ordered list of filters for that chain. |
| Security filters | Perform tasks such as security context management, CSRF, client authentication, OAuth 2.0/OIDC endpoint handling, Bearer token authentication, exception handling, or authorization. |
| <code>AuthorizationFilter</code> | Enforces policies configured via <code>authorizeHttpRequests</code> once the request has been routed into the chain containing this filter. |

Spring Authorization Server implements many endpoints via **security filters**, such as <code>OAuth2AuthorizationEndpointFilter</code> and <code>OAuth2TokenEndpointFilter</code>. An endpoint can be fully handled inside a filter without ever reaching a Spring MVC controller.

Therefore, distinguish:

- **Does the chain match?** Determined by the <code>SecurityFilterChain</code>'s matcher.
- **Which filters run, and in what order?** Determined by the selected chain's filter configuration.
- **Is the request allowed to access the resource?** Determined by the chain's authentication, authorization, and other control mechanisms.

## 3. Three kinds of "ordering" that are easy to confuse

### 3.1. Ordering between SecurityFilterChains

Declaring <code>@Order(1)</code>, <code>@Order(2)</code>, <code>@Order(3)</code> on <code>SecurityFilterChain</code> beans specifies which chain is evaluated first. **Lower order values have higher priority**.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http) throws Exception {
    // Narrow matcher for Authorization Server endpoints
    // ...
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    // Matcher /api/**
    // ...
    return http.build();
}

@Bean
@Order(3)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    // No securityMatcher => chain catches remaining requests
    // ...
    return http.build();
}
~~~

<code>FilterChainProxy</code> iterates in order and stops at the **first matching chain**. If the first chain matches every request, the second and third chains never get a chance to process any request, even if the rules inside those later chains are completely valid.

In real configurations, place **specific matchers first** and a **broad fallback chain last**. Do not rely on accidental bean registration order when multiple chains might match the same path.

### 3.2. Filter ordering *inside* a SecurityFilterChain

Once a chain is selected, Spring Security executes its filters according to **an internal filter order managed by Spring Security**. For example, filters that build the security context usually must run before steps that read authentication details; authentication mechanisms must be ready when authorization rules are evaluated.

Filters related to the Authorization Server may include client authentication filters, the authorization endpoint filter, the token endpoint filter, and additional endpoints; exact positions depend on the Spring Security/Spring Authorization Server version and enabled configurers. **Do not treat example diagrams or filter lists in documentation as a fixed order across every version.**

<code>@Order</code> on a **<code>SecurityFilterChain</code> bean** only orders chains relative to one another; it does not reorder filters inside a chain. If you must insert a custom filter, use the appropriate <code>HttpSecurity</code> APIs, for example:

~~~java
http.addFilterBefore(customAuditFilter, AuthorizationFilter.class);
// Or addFilterAfter(...), addFilterAt(...) when specifically required.
~~~

Do not insert a filter at an arbitrary position just to "run before everything"; determine which authentication steps it must run after, whether it needs the security context, and whether it could accidentally log secrets, authorization codes, or access tokens.

### 3.3. Ordering of <code>requestMatchers</code> rules inside a chain

Inside <code>authorizeHttpRequests</code>, rules are evaluated in **declaration order**; the first matching rule decides the authorization requirement.

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
);
~~~

<code>anyRequest()</code> applies to **remaining requests within the current chain**. Never place <code>anyRequest()</code> before specific rules. For endpoints sharing a path with different HTTP methods, distinguish methods explicitly as shown above.

All three kinds of ordering can coexist:

| Level | Common configuration | Effect |
| --- | --- | --- |
| Chain selection | <code>@Order</code> + <code>securityMatcher</code> | Which chain is responsible for the request |
| Filter execution | Filter order managed by the framework/configurers | How authentication, endpoint handling, and authorization occur |
| Rule selection | <code>requestMatchers(...)</code> inside <code>authorizeHttpRequests</code> | Allow/deny conditions within the selected chain |

## 4. <code>securityMatcher</code> vs. <code>requestMatchers</code>: where do they differ?

### 4.1. <code>securityMatcher</code> defines the scope of the entire chain

~~~java
http.securityMatcher("/api/**");
~~~

This call configures a matcher so that **only API requests** enter the chain being configured. When the path does not match, <code>FilterChainProxy</code> moves on to check the next chain. The current chain's filters and authorization rules **are not executed** for non-matching requests.

If <code>securityMatcher</code> is omitted, the chain typically defaults to matching every request. Thus, a chain without an explicit matcher placed at a high priority can "swallow" all subsequent chains.

<code>securityMatcher</code> also accepts a custom <code>RequestMatcher</code>, such as the one provided by Spring Authorization Server or a composite <code>OrRequestMatcher</code>. You should not assume all OAuth/OIDC endpoints share a single path pattern.

### 4.2. <code>requestMatchers</code> selects authorization rules, not the chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

For <code>GET /api/public/ping</code>, the API chain is selected first; inside the chain, the <code>/api/public/**</code> rule permits access without login. This **does not mean security filters are skipped**: filters attached to the chain still execute; <code>permitAll()</code> simply represents the authorization decision for that request.

For <code>GET /login</code>, the API chain does not match; even if you add <code>.requestMatchers("/login").permitAll()</code> **inside the API chain**, that rule will never be applied to <code>/login</code>.

### 4.3. Distinguishing from other RequestMatchers

<code>RequestMatcher</code> is a general interface with a <code>matches(HttpServletRequest)</code> method. It is used at multiple layers:

- <code>http.securityMatcher(...)</code>: matcher for the **entire SecurityFilterChain**.
- <code>authorizeHttpRequests().requestMatchers(...)</code>: matcher for an **authorization rule**.
- Matchers inside authentication filters: for example, the filter handling <code>/oauth2/token</code> only acts on matching endpoint requests.
- Matchers for exception handling or CSRF: determine how to handle **a specific group of requests**.

Do not treat two methods containing the word "matcher" as interchangeable. They share the same request-matching foundation but differ in **where they sit in the processing pipeline**.

### 4.4. Scenario table

Suppose the first chain has <code>securityMatcher("/api/**")</code> and the second fallback chain matches all requests:

| Request | Selected chain | Evaluated rule |
| --- | --- | --- |
| <code>GET /api/orders/42</code> | API | GET <code>/api/orders/**</code> rule |
| <code>POST /api/orders</code> | API | POST <code>/api/orders</code> rule |
| <code>GET /login</code> | Fallback | Rule in fallback chain |
| <code>POST /oauth2/token</code> | Fallback if no prior AS chain exists | No AS token-issuance filter if that chain is not configured |

The last row highlights an important configuration mistake: **adding <code>permitAll()</code> for <code>/oauth2/token</code> in the fallback chain does not create a token endpoint**. The endpoint is provided by Spring Authorization Server's filters and must reside in the chain carrying that configurer.

## 5. Designing chains for Spring Authorization Server

### 5.1. Why separate the Authorization Server from the UI chain?

An Authorization Server serves both **browser** requests and **OAuth 2.0 client** requests:

- <code>GET /oauth2/authorize</code>: requires a user login session; may redirect to <code>/login</code>.
- <code>POST /oauth2/token</code>: client exchanges an authorization code, sends a refresh token, or uses an appropriate grant; requires client authentication and OAuth 2.0 protocol processing.
- Metadata/JWK/OIDC endpoints: have distinct protocol requirements and protection levels.
- <code>/login</code>: usually provided by <code>formLogin</code> in the **UI chain**, not the token endpoint.

Lumping everything into the UI chain with identical settings can cause token requests to receive an HTML login redirect instead of a protocol response; conversely, forcing the entire system into a stateless Bearer API can break interactive user login.

### 5.2. Using the Authorization Server's <code>getEndpointsMatcher()</code>

Spring Authorization Server provides <code>OAuth2AuthorizationServerConfigurer</code> and a matcher for the endpoint set managed by that configurer:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.oidc(Customizer.withDefaults())
    );
~~~

This is a **more accurate way to express the scope** than <code>securityMatcher("/oauth2/**")</code>, because some OIDC/metadata endpoints use paths such as <code>/.well-known/openid-configuration</code>, <code>/userinfo</code>, or <code>/connect/logout</code>, and paths can be customized via <code>AuthorizationServerSettings</code>.

The matcher provided by Authorization Server reflects the endpoints configured by that configurer. When OIDC is enabled, related OIDC endpoints must be accounted for; do not assume every endpoint is available or enabled by default in all versions.

### 5.3. Three-chain example: Authorization Server, API, Web application

The snippet below illustrates a **Spring Security Servlet** configuration using the Spring Authorization Server API style supporting <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> and <code>HttpSecurity.with(...)</code>. <code>import</code> statements are omitted to focus on ordering. Cross-check APIs against your actual version and configure the foundational beans: registered clients, authorization/consent services, signing keys, and <code>JwtDecoder</code> if using OIDC/JWT endpoints.

~~~java
@Configuration
@EnableWebSecurity
public class SecurityChainsConfiguration {

    // Chain 1: endpoints managed by the Authorization Server.
    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
            )
            // Serves OIDC endpoints requiring a Bearer access token,
            // such as UserInfo when enabled.
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    // Chain 2: business API accepting Bearer tokens only.
    @Bean
    @Order(2)
    SecurityFilterChain apiSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Only disable CSRF in this API chain if the API truly uses
            // Bearer tokens only, without cookie/session authentication.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    // Chain 3: login UI and remaining pages.
    @Bean
    @Order(3)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Reading the configuration by responsibility:**

1. The **first** chain holds Authorization Server OAuth 2.0/OIDC filters and protocol endpoint policies. <code>getEndpointsMatcher()</code> bounds the scope precisely. When an unauthenticated browser request requires login, the entry point redirects to <code>/login</code>.
2. The **second** chain matches only <code>/api/**</code>, requiring a JWT Bearer token and route-specific authorities. The stateless/CSRF settings here are scoped strictly to a **Bearer-token-only** API. If the API accepts cookies/sessions or other automatic browser authentication mechanisms, CSRF protection must be redesigned.
3. The **third** chain omits <code>securityMatcher</code> and thus serves as the **fallback**; <code>formLogin</code> provides the interactive login mechanism needed for the authorization code flow.

<code>oauth2ResourceServer().jwt()</code> in the first chain serves OIDC endpoints that need to read Bearer tokens; in the API chain, it authenticates access tokens calling the Orders API. These are two separate protection scopes even though they may share a decoder. For APIs requiring audience restrictions, configure <code>JwtDecoder</code> and an appropriate <code>OAuth2TokenValidator</code>; **selecting the right chain does not replace validating issuer, audience, expiration, and scope**.

The example assumes a <code>JwtDecoder</code> and key source aligned with the Authorization Server. If the Authorization Server and Resource Server are split into separate applications, each application has its own chain configuration; there is no need to copy all three chains into every service.

### 5.4. Why doesn't <code>/login</code> belong to the Authorization Server chain?

When an unauthenticated user without a session sends <code>GET /oauth2/authorize</code>, the protocol filter may require authentication. The browser entry point redirects to <code>/login</code>. The browser issues a new request:

1. <code>/login</code> **does not match** the Authorization Server endpoint matcher, since it is an application login page.
2. The request is checked against the API chain next, and does not match <code>/api/**</code> either.
3. The fallback Web chain matches, and <code>formLogin</code> handles the login page and credentials.
4. After successful login, the browser returns to the <code>/oauth2/authorize</code> flow via the saved request/redirect mechanism.

If you register only the Authorization Server chain without a corresponding chain for the login page, a redirect to <code>/login</code> will not work as expected. If you set a custom login page like <code>/signin</code>, configure <code>loginPage</code>, the route, public access rules, and the form-processing path to match the UI chain.

### 5.5. Paths of five requests

~~~mermaid
flowchart LR
    R["Request"] --> AS{"Order 1: AS endpoints?"}
    AS -- "Yes" --> A["AS chain: OAuth2/OIDC filters"]
    AS -- "No" --> API{"Order 2: /api/**?"}
    API -- "Yes" --> B["API chain: Bearer + scope"]
    API -- "No" --> C["Order 3: Web chain: formLogin"]
~~~

| Request | First matching chain | Primary processing |
| --- | --- | --- |
| <code>GET /oauth2/authorize</code> | Authorization Server | Authorization endpoint, prompts user to log in when needed |
| <code>POST /oauth2/token</code> | Authorization Server | Client authentication, token endpoint, and grant processing |
| <code>GET /.well-known/openid-configuration</code> | Authorization Server if OIDC metadata endpoint is enabled | Serves discovery metadata per endpoint policy |
| <code>GET /login</code> | Web | Login page / form login |
| <code>GET /api/orders/42</code> | API | Verifies Bearer token, scope, and order permissions |

Within a single request, there is no sequence where "the AS chain finishes and hands off to the API chain". A redirect from <code>/oauth2/authorize</code> to <code>/login</code> is **a new HTTP request**, so chain selection runs again.

## 6. Detailed Authorization Code + PKCE flow

Consider client <code>orders-web</code> initiating an Authorization Code Flow with PKCE:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant P as FilterChainProxy
    participant AS as Authorization Server chain
    participant W as Web chain
    participant C as OAuth Client
    B->>P: GET /oauth2/authorize?...
    P->>AS: Select chain by endpoints matcher
    AS-->>B: Redirect /login if unauthenticated
    B->>P: GET /login
    P->>W: Select fallback Web chain
    W-->>B: Render login page
    B->>P: POST /login + CSRF token
    P->>W: Authenticate form and create session
    W-->>B: Redirect back to authorization request
    B->>P: GET /oauth2/authorize?...
    P->>AS: AS chain; auth/consent/policy
    AS-->>B: Redirect client with authorization code
    C->>P: POST /oauth2/token + code + code_verifier
    P->>AS: AS chain; validate client and grant
    AS-->>C: Access token / ID Token if OIDC
~~~

From the filter chain perspective:

- PKCE, client checks, redirect URI validation, authorization code handling, and OIDC requirements are the responsibility of **protocol components** enabled in the AS chain, not something <code>requestMatchers().authenticated()</code> automatically verifies on its own.
- <code>authorizeHttpRequests().anyRequest().authenticated()</code> on the AS chain is a general policy layer. It does not replace endpoint-specific filters and is no reason to blindly apply <code>permitAll()</code> to the token endpoint.
- Login requests use the **Web chain**, typically with session and CSRF tailored for forms. Never disable CSRF application-wide to fix a POST error on an OAuth endpoint.
- <code>POST /oauth2/token</code> is a **new request from the client**, typically without the user's browser session; client/grant validation resides in Authorization Server mechanisms.

Actual flows may vary depending on client type, client authentication method, consent requirements, login method, and enabled endpoints. The diagram illustrates **chain selection paths**, not every protocol message.

## 7. Building accurate matchers for multiple paths

### 7.1. Do not replace the AS matcher with <code>"/oauth2/**"</code>

A common mistake:

~~~java
// Error illustration: only matches /oauth2/**, missing other OIDC/metadata endpoints.
http
    .securityMatcher("/oauth2/**")
    .with(authorizationServerConfigurer, configurer ->
        configurer.oidc(Customizer.withDefaults()));
~~~

Consequence: <code>/.well-known/openid-configuration</code>, <code>/userinfo</code>, or custom endpoints outside <code>/oauth2/**</code> may fall through to another chain and bypass the proper endpoint filters. Fix this by using <code>authorizationServerConfigurer.getEndpointsMatcher()</code> and checking the actual endpoint list for your version, <code>AuthorizationServerSettings</code>, and enabled features.

### 7.2. Configuring one chain for multiple API groups

When a single chain genuinely needs to cover multiple path scopes, you can combine matchers:

~~~java
RequestMatcher apiEndpoints = new OrRequestMatcher(
    new AntPathRequestMatcher("/api/**"),
    new AntPathRequestMatcher("/internal/**")
);

http.securityMatcher(apiEndpoints);
~~~

This example illustrates the **OR** semantics of matchers. In newer Spring Security versions, prefer URL/path matchers aligned with your MVC/Servlet stack; older matchers like <code>AntPathRequestMatcher</code> are deprecated in newer releases in favor of <code>PathPatternRequestMatcher</code>. Do not mix multiple path-matching strategies without clearly verifying <code>servletPath</code> and context path behavior.

Many versions also support the shorthand <code>securityMatcher("/api/**", "/internal/**")</code>. In larger codebases, a clearly named <code>RequestMatcher</code> is often easier to test and govern.

### 7.3. Paths, servlet path, and context path

Suppose the application is deployed under context path <code>/identity</code>, so the external URL is <code>/identity/oauth2/token</code>. In Servlet Security, many URL matchers evaluate against the relative path **excluding the context path**. Mechanically prepending <code>/identity</code> to <code>"/oauth2/**"</code> can prevent the matcher from matching.

If the application uses a custom servlet path, multiple servlets, or sits behind a reverse proxy rewriting prefixes, matching behavior can vary by matcher and framework version. Verify **requestURI, contextPath, servletPath, pathInfo**, forwarded header settings, and the chosen matching strategy; write integration tests using the actual deployment configuration rather than guessing from user-facing URLs.

### 7.4. <code>permitAll</code> does not mean skipping security

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Static asset requests still traverse the selected chain. As a result, security headers and security filters continue to apply. By contrast, configurations like <code>web.ignoring()</code> exclude requests from the Spring Security filter chain altogether and should only be used when truly justified and its consequences are understood. For public application endpoints, <code>permitAll()</code> is generally preferred.

## 8. Common configuration mistakes

### Mistake 1: Placing a catch-all chain first

~~~java
@Bean
@Order(1)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize ->
        authorize.anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    // Authorization Server filters
    // ...
    return http.build();
}
~~~

The Web chain has a default matcher that matches every request, so the Authorization Server chain **is never selected**. Fix this by placing the narrow AS chain at higher priority and the Web fallback at the end.

### Mistake 2: Placing API rules inside a chain that only matches AS endpoints

~~~java
http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    );
~~~

The <code>/api/orders/**</code> rule is never used because API requests do not match the AS chain's matcher. A separate API chain is required (or the chain scope must be intentionally reorganized).

### Mistake 3: Using <code>permitAll()</code> to "open" the token endpoint

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/oauth2/token").permitAll()
    .anyRequest().authenticated()
);
~~~

This is only an authorization rule; it **does not create** <code>OAuth2TokenEndpointFilter</code>, does not automatically enable client or grant checks, and does not replace Authorization Server configuration. On the contrary, arbitrarily opening protocol endpoints can break security assumptions. Use the AS configurer properly and let protocol mechanisms handle specialized requirements.

### Mistake 4: Forcing every request into a stateless API configuration

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .csrf(csrf -> csrf.disable());
~~~

Applying this policy to a chain that also covers the login page can break browser-session-based Authorization Code flows; disabling CSRF for form login is also inappropriate. Separate responsibilities across chains and apply stateless/CSRF exceptions only where the authentication model is explicitly established.

### Mistake 5: Trying to reorder filters using the chain's <code>@Order</code>

<code>@Order(1)</code> on a <code>SecurityFilterChain</code> does not move a custom filter ahead of <code>OAuth2ClientAuthenticationFilter</code> or <code>AuthorizationFilter</code> inside it. Specify filter placement using <code>HttpSecurity</code> filter-registration APIs and understand side effects on sessions and the security context.

### Mistake 6: Covering all endpoints with one path pattern and forgetting OIDC

<code>securityMatcher("/oauth2/**")</code> misses endpoints on other paths if your AS/OIDC configuration actually needs them. Use the matcher from the configurer and verify whenever toggling endpoints or changing <code>AuthorizationServerSettings</code>.

### Mistake 7: Missing fallback chain

If you only configure an AS chain with a restricted matcher and omit a matching chain for <code>/login</code> or other routes, unmatched routes **are not protected by Spring Security**. They might return 404 because no application route exists, but a 404 does not prove the route is secured. Explicitly define chains for all expected URL areas and provide a fallback when needed.

### Mistake 8: Diagnosing 401/403 without identifying the chain

HTTP 401 or 403 can originate from very different stages. Even a 302 redirect to <code>/login</code> does not prove the request passed through the Authorization Server chain. Check **which chain was selected, which filter handled the request, and whether that filter's request matcher matched** before altering authorization rules.

## 9. How to diagnose which chain a request enters

### 9.1. Inspecting Spring Security traces in development

You can enable logging to observe chain selection and related filters:

~~~properties
# Enable only while diagnosing in a development environment.
logging.level.org.springframework.security=TRACE
~~~

Depending on the version, logs from <code>FilterChainProxy</code> show the request being secured and matcher evaluation steps. Also inspect Spring Authorization Server logs when tracing endpoint execution. Avoid verbose logging in production: OAuth 2.0 requests may carry credentials, codes, or tokens, and logs can leak sensitive data.

When <code>/oauth2/token</code> returns an HTML login page, check in order:

1. Is the AS chain registered and ordered before the fallback?
2. Does the AS <code>getEndpointsMatcher()</code> match the configured token endpoint?
3. Is another chain with a broader matcher intercepting the request first?
4. Are the AS endpoint filters properly added to the chain?
5. Did the response originate from the client authentication filter, an OAuth endpoint, or the default entry point?

### 9.2. Directly testing the first matching chain

With Spring Security Test, you can construct a <code>MockHttpServletRequest</code> and find the first matching chain in <code>FilterChainProxy</code>. The example assumes the three-chain configuration above is loaded and uses AssertJ/JUnit:

~~~java
@Autowired
FilterChainProxy springSecurityFilterChain;

private SecurityFilterChain firstMatchingChain(
        String method, String path) {

    MockHttpServletRequest request =
        new MockHttpServletRequest(method, path);
    request.setServletPath(path);

    return springSecurityFilterChain.getFilterChains().stream()
        .filter(chain -> chain.matches(request))
        .findFirst()
        .orElseThrow(() -> new AssertionError(
            "No security chain matches " + method + " " + path));
}

@Test
void tokenEndpointUsesAuthorizationServerChain() {
    SecurityFilterChain chain =
        firstMatchingChain("POST", "/oauth2/token");

    assertThat(chain.getFilters()).anyMatch(
        filter -> filter instanceof OAuth2TokenEndpointFilter
    );
}

@Test
void apiRequestUsesApiChain() {
    SecurityFilterChain chain =
        firstMatchingChain("GET", "/api/orders/42");

    assertThat(chain.getFilters())
        .anyMatch(filter ->
            filter instanceof BearerTokenAuthenticationFilter)
        .noneMatch(filter ->
            filter instanceof OAuth2TokenEndpointFilter);
}

@Test
void loginRequestUsesWebChain() {
    SecurityFilterChain chain =
        firstMatchingChain("POST", "/login");

    assertThat(chain.getFilters()).anyMatch(
        filter -> filter instanceof UsernamePasswordAuthenticationFilter
    );
}
~~~

This tests **chain routing and filter composition**, not full OAuth 2.0 behavior. Add integration tests with <code>MockMvc</code> or a real HTTP client, matching your context/servlet path setup, and verify runtime behavior: authorization redirects, token requests, client authentication, CSRF/form login, JWT validation, issuer/audience/scope, and API permissions.

To prove a filter actually processed a request, execute the request and verify the response or expected side effect. A filter merely **being present** in a chain only confirms registration, not that its internal matcher triggered or that the token was validated.

### 9.3. Minimum test matrix

| Scenario | What to verify |
| --- | --- |
| Unauthenticated <code>GET /oauth2/authorize</code> | Enters AS chain; redirects properly to login; does not hit API chain |
| <code>POST /oauth2/token</code> missing valid client credentials | Enters AS chain; returns protocol error response, not HTML login |
| Enabled OIDC discovery endpoint | Matches AS chain and returns metadata per configuration |
| <code>GET /login</code>, <code>POST /login</code> | Enters Web chain; handles form, session, and CSRF as configured |
| <code>GET /api/orders/42</code> without Bearer token | Enters API chain; rejects when authentication is required |
| Access token with right scope but wrong audience | Resource Server rejects token (if audience validator is configured) |
| Access token with right audience but missing scope | API denies required permission |
| Access token with right scope/audience but no access to the order | Service/domain layer denies based on data-level authorization |
| Changing context path / servlet path | Matcher still selects the right chain under actual deployment paths |
| Unknown route, e.g., <code>/unknown</code> | Fallback chain applies before 404 handling or other policies |

## 10. Security takeaways to remember

**Selecting the right chain is a necessary condition, not the entirety of OAuth 2.0/OIDC security.** Multiple layers must work together:

- **Endpoint routing:** the Authorization Server matcher selects the right chain, including enabled OIDC endpoints.
- **Client authentication and grant validation:** protocol filters/components verify grant type, client, redirect URI, PKCE, codes, tokens, etc., per endpoint role.
- **User authentication and session:** the Web chain handles interactive login and CSRF protection where required.
- **Access token validation:** the Resource Server checks token validity, issuer, expiration, audience, and profile constraints.
- **Authorization:** scopes/authorities constrain actions; the business layer continues checking ownership, organization, tenant, or specific data objects.

An access token with a valid signature is not automatically valid for every API. A request with <code>permitAll()</code> does not mean all security filters are bypassed. And a route returning 404 is not guaranteed to have passed through any security chain.

## 11. Practice exercise

Suppose an application exposes the following routes:

- Authorization Server: <code>/oauth2/authorize</code>, <code>/oauth2/token</code>, <code>/oauth2/jwks</code>.
- OIDC: <code>/.well-known/openid-configuration</code>, <code>/userinfo</code> when enabled.
- API: <code>/api/catalog/**</code>, <code>/api/billing/**</code>.
- Web UI: <code>/login</code>, <code>/admin/**</code>, <code>/assets/**</code>.

Complete the following tasks:

1. Diagram the chain sequence, specify each chain's matcher, and assign <code>@Order</code>.
2. Design rules so that <code>GET /api/catalog/**</code> requires <code>SCOPE_catalog.read</code>, while <code>/api/billing/**</code> has its own policy.
3. Explain why <code>/userinfo</code> might not be properly handled if you use <code>"/oauth2/**"</code> as the matcher.
4. Predict what happens when a Web chain matching all requests is moved to <code>@Order(1)</code>.
5. Write tests confirming <code>/oauth2/token</code> enters the AS chain, <code>/api/catalog/10</code> enters the API chain, and <code>/login</code> enters the Web chain.
6. Add a <code>/public/status</code> route and distinguish handling it via <code>permitAll()</code> in the fallback chain versus excluding the route from Spring Security.

A sound design must explicitly specify **each chain's matcher**, **chain selection order**, **authorization rules within each chain**, and **authentication filter responsibilities**. Whenever endpoints change or OIDC features are added, update the test matrix as well.

## 12. Reference documentation

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): <code>DelegatingFilterProxy</code>, <code>FilterChainProxy</code>, <code>SecurityFilterChain</code>, and filter ordering.
- [Spring Security — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): multiple <code>SecurityFilterChain</code> beans, <code>@Order</code>, <code>securityMatcher</code>, and <code>requestMatchers</code>.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): rule ordering, <code>permitAll</code>, <code>denyAll</code>, and authorization matchers.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): <code>OAuth2AuthorizationServerConfigurer</code> and Authorization Server endpoints.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): basic configuration with Authorization Server security filter chains and login page.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): access token verification and authority mapping.
