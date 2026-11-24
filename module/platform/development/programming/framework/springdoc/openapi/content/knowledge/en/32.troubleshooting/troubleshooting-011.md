# 401, 403, CSRF, or CORS Errors During Try It Out

When Swagger UI opens successfully yet **Try it out** returns 401, 403, or a CORS error, identify which request is rejected and which layer processes that request. Swagger UI is only a browser-based interface; requests to the OpenAPI document, requests to the actual API, and browser preflight requests may pass through different endpoints, filters, and security rules.

In Spring Boot with springdoc-openapi, four common error categories are:

- **401 Unauthorized:** the request lacks authentication credentials or credentials are invalid.
- **403 Forbidden:** the user is authenticated but lacks sufficient permissions; or Spring Security rejects the request due to a missing/invalid CSRF token.
- **CSRF:** a state-changing request fails to send a valid token in an application using cookie/session-based authentication.
- **CORS:** the browser blocks a cross-origin request because the server does not allow the requested origin, method, or headers.

Do not handle all four by turning off Spring Security. Use the Network tab to locate the failing request, inspect status and response headers, then fix the exact filter chain, authorization rule, CSRF repository, or CORS configuration.

## 1. Identifying Which Request Is Failing

Swagger UI typically issues multiple distinct requests:

| Request | Purpose | Common errors |
|---|---|---|
| /swagger-ui.html | Swagger UI entry URL, usually redirects to the UI | 302 loop, 401, 403, or 404 |
| /swagger-ui/** | JavaScript, CSS, and UI assets | 401, 403, or 404 |
| /v3/api-docs/swagger-config | Loads Swagger UI configuration | 401, 403, or 404 |
| /v3/api-docs | Loads the default OpenAPI document | 401, 403, or 404 |
| /v3/api-docs/{group} | Loads a group's document | 401, 403, or 404 |
| /api/** | Business API called via Try it out | 400, 401, 403, 404, 415, or others |
| OPTIONS /api/** | CORS preflight sent by browser before the real request | 401, 403, or missing CORS headers |

Open Browser Developer Tools, select the **Network** tab, enable Preserve log, then repeat the failing action. Filter by Fetch/XHR and inspect:

1. Request URL and HTTP method.
2. Request status code.
3. Request headers, especially `Origin`, `Authorization`, `Cookie`, `Content-Type`, `Accept`, and `Access-Control-Request-*`.
4. Response headers, especially `WWW-Authenticate`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, and `Access-Control-Allow-Headers`.
5. Response body if the browser allows reading it.
6. Whether an `OPTIONS` request precedes the actual request.

For example, if `/swagger-ui/index.html` returns 200 yet `/v3/api-docs` returns 401, the issue lies in OpenAPI document access permissions. If the document loads yet `POST /api/products` returns 403, check authorization or CSRF on the business endpoint.

A "Failed to fetch" or "NetworkError" message is not enough to conclude the server is down. CORS can prevent JavaScript from reading the response even when the server already returned 401 or 403. Inspect request and response headers in the Network tab.

## 2. Distinguishing 401 and 403

401 and 403 represent two distinct states:

| Status | Common meaning | Diagnostic questions |
|---|---|---|
| 401 Unauthorized | Unauthenticated or invalid credentials | Did the request send a token/cookie? Is the token unexpired with valid issuer/audience and signature? |
| 403 Forbidden | Authenticated but unauthorized; or blocked by CSRF | Does the user have the required role/scope? Does the request carry a CSRF token? |

With HTTP Bearer authentication, a 401 response typically includes `WWW-Authenticate: Bearer`. The token may be missing, expired, wrongly signed, have wrong issuer/audience, or be rejected by the resource server.

403 typically occurs when a principal is identified yet lacks authority or scope. However, the CSRF filter also commonly returns 403 when a state-changing method lacks a valid CSRF token. Therefore, do not assume every 403 is a role error.

## 3. Verifying Access to Swagger UI and OpenAPI Endpoints

A Spring Security configuration may require authentication across the whole application. If users should open documentation publicly, permit Swagger UI and springdoc endpoints before rules requiring authentication.

Example with Spring Boot 3 / Spring Security 6 or newer:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/swagger-ui.html",
                    "/swagger-ui/**",
                    "/v3/api-docs",
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml"
                ).permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
            )
            // Only skip CSRF for the API if it is stateless and uses bearer tokens exclusively.
            .csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                Customizer.withDefaults()
            ));

        return http.build();
    }
}
~~~

In this example:

- `permitAll()` applies only to documentation paths and Swagger UI.
- `/api/admin/**` still requires the `ADMIN` role.
- `/api/**` still requires authentication.
- The JWT resource server still authenticates business requests.

Do not add `/api/**` to `permitAll()` just so Swagger UI can invoke APIs. The UI can load publicly while APIs remain protected.

The paths above are common defaults. If you changed `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, or use a context path or reverse proxy prefix, update matchers to match actual URLs. Some older versions may serve assets under `/webjars/**`; add that matcher only if the Network tab shows the application actually uses that path.

If the OpenAPI document contains internal endpoints or non-public details, do not make it public just to fix a 401. Protect the document, split public/private groups, or publish a separately filtered document.

## 4. Rule Order and Multiple SecurityFilterChains

`requestMatchers` are evaluated in declaration order inside a `SecurityFilterChain`. Broad rules like `/api/**` or `anyRequest().authenticated()` placed before specific rules can prevent later rules from applying as expected.

If the application has multiple `SecurityFilterChain` beans, Spring Security selects a chain by `securityMatcher` and `@Order`. Permitting Swagger UI in one chain has no effect if the request is captured earlier by another chain.

Example with a dedicated chain for APIs:

This example uses `AbstractHttpConfigurer` in modern configuration; the corresponding import is `org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer`.

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        // Use only when the entire API chain is stateless and authenticated with bearer tokens.
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            Customizer.withDefaults()
        ));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webAndDocsSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs/**",
                "/v3/api-docs.yaml"
            ).permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

This example illustrates splitting chains; actual configuration must include your application's rules and authentication mechanisms. The first chain matches only `/api/**`, so it does not handle `/v3/api-docs` or `/swagger-ui/**`. The second chain handles the rest. Disabling CSRF in the first chain is only appropriate when every API request uses stateless bearer tokens; if the API uses cookies/sessions, keep CSRF enabled and require tokens.

When diagnosing 401/403, inspect `securityMatcher`, `@Order`, specific rules, and catch-all rules. Enable Spring Security `DEBUG` logging in development to see which chain/filter handles the request; never leave sensitive debug logging enabled in production.

## 5. Swagger UI Authorize Does Not Configure Spring Security

The **Authorize** button in Swagger UI reads security schemes from the OpenAPI document and attaches credentials to requests sent by Swagger UI per that scheme. It does not create users, grant roles, or replace Spring Security configuration.

Example declaring HTTP Bearer JWT in OpenAPI:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product API",
        version = "v1"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {}
~~~

Attach the requirement to an operation or controller:

~~~java
@RestController
@RequestMapping("/api/products")
@SecurityRequirement(name = "bearerAuth")
class ProductController {

    @GetMapping
    List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

When a user enters a JWT in Authorize, Swagger UI can send:

~~~http
Authorization: Bearer eyJ...
~~~

Verify in the Network tab whether the `Authorization` header actually appears on the API request. If absent, inspect the security scheme, requirement, how the token was entered, and Swagger UI configuration.

`@SecurityScheme` and `@SecurityRequirement` only describe security in OpenAPI. They do not configure `oauth2ResourceServer`, JWT decoders, role mappings, or Spring Security authorization rules. Both sides must be configured consistently.

### Note When the OpenAPI Document Is Also Protected

Swagger UI must load the document before rendering full operations. The Authorize button can normally only be used after the UI loads configuration/document and the user sees the interface.

If `/v3/api-docs` requires a bearer token yet tokens can only be entered via Authorize after the document loads, a catch-22 can occur: the UI fails to load the document and therefore does not display the Authorize button to enter a token.

Ways to handle this:

- Allow public access to the document if its contents may be public.
- Provide a static document or a separately filtered public document.
- Use a pre-authenticated cookie/session mechanism before opening Swagger UI.
- If specially required, configure a request interceptor to send credentials when fetching the document; ensure tokens are not leaked.

Do not confuse Authorize sending tokens to operations with Swagger UI fetching `/v3/api-docs/swagger-config` and `/v3/api-docs`.

## 6. Diagnosing Bearer and OAuth2 Tokens

When an API returns 401, check:

1. Does the request contain `Authorization: Bearer ...`?
2. Is the token truncated, wrapped in quotes, or carrying a duplicated `Bearer` prefix?
3. Is the token unexpired (`exp`)?
4. Do `iss` and `aud` match resource server configuration?
5. Was the JWT signed by a key trusted by the server?
6. Is the token the intended token type for this API?
7. Do clocks on the token issuer and API server have significant skew?
8. Did a reverse proxy strip or fail to forward the `Authorization` header?

With OAuth2, distinguish access tokens from ID tokens. ID tokens are for clients identifying users; API resource servers typically need access tokens with matching audience and scopes.

When an API returns 403, check authority mappings:

- Scope `products.read` usually maps to authority `SCOPE_products.read` in default resource server configuration.
- Role `ADMIN` is usually checked with `hasRole("ADMIN")`, matching authority `ROLE_ADMIN`.
- `hasAuthority("SCOPE_products.read")` and `hasRole("products.read")` are not equivalent.

For example:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/products/**")
        .hasAuthority("SCOPE_products.read")
    .requestMatchers(HttpMethod.POST, "/api/products/**")
        .hasAuthority("SCOPE_products.write")
    .anyRequest().authenticated()
);
~~~

Never put real JWTs into source code, screenshots, tickets, or logs. When debugging, use short-lived test tokens with minimal permissions; share only sanitized non-sensitive claims.

## 7. Distinguishing CSRF from Authentication

CSRF (Cross-Site Request Forgery) is an attack exploiting a browser's automatic attachment of user credentials, typically session cookies. An attacker can trick a logged-in browser into sending state-changing requests to another site.

Spring Security enables CSRF protection by default for state-changing requests such as POST, PUT, PATCH, and DELETE. GET, HEAD, OPTIONS, and TRACE requests are treated as safe methods by the default matcher.

When CSRF is enabled, requests must send a valid CSRF token in addition to the authentication cookie. The session cookie proves the login session; the CSRF token proves the state-changing request originated from the application that issued the token.

Common symptoms:

- GET APIs succeed while POST/PUT/DELETE return 403.
- Requests from Swagger UI return 403 even though the JWT looks valid.
- Server logs report missing or mismatched CSRF token.
- Session cookie is present yet CSRF header is absent.

Do not disable CSRF simply upon seeing 403. First determine whether the application uses session cookies, cookie authentication, or bearer tokens explicitly sent in the `Authorization` header.

## 8. When Can CSRF Be Skipped for an API?

If an API is truly stateless and authenticates solely via bearer tokens in the `Authorization` header, browsers do not automatically attach that header like session cookies. In that architecture, CSRF protection for the API alone may be unnecessary.

You can skip CSRF for API paths using a targeted matcher:

~~~java
http
    .csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        Customizer.withDefaults()
    ));
~~~

Only use this when `/api/**` does not rely on cookies/sessions or browser-auto-sent credentials. If the API uses cookie authentication, browser-cached Basic authentication, or shares a session with a web UI, skipping CSRF can open a vulnerability.

A safer choice when an application hosts both web sessions and stateless APIs is splitting into separate `SecurityFilterChain` beans: the stateless API chain has its own CSRF policy; the web chain retains CSRF protection.

Never disable CSRF globally just so Swagger UI can invoke an operation if the application still has form login or session-cookie-based state-changing endpoints.

## 9. Configuring CSRF Tokens for Swagger UI

If the application uses session/cookie authentication and still needs CSRF, Swagger UI must send the token in the header or request parameter the server expects.

Springdoc has a property supporting Swagger UI CSRF when using standard header/cookie names:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
~~~

This property defaults to `false` and has existed since springdoc-openapi v1.4.4. In standard Spring Security configurations with `CookieCsrfTokenRepository`, the cookie is named `XSRF-TOKEN` and the header is `X-XSRF-TOKEN`. Springdoc Swagger UI can automatically read and send the token per standard convention when CSRF support is enabled and your installed version supports this property.

If the application uses custom cookie/header names or a different token storage mechanism, configure Swagger UI's `requestInterceptor` to extract the token and attach the right header. Check docs for your installed springdoc version; do not assume newer properties exist in all older versions.

Example `CookieCsrfTokenRepository` for applications needing JavaScript to read the CSRF cookie:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

`HttpOnly=false` allows JavaScript to read the CSRF cookie. Apply this only to the cookie holding the CSRF token, never to session cookies or cookies holding access tokens. Use HTTPS, set appropriate `SameSite`, and evaluate application security requirements before enabling.

Modern Spring Security features deferred tokens and BREACH protection; SPAs have specific considerations when reading tokens from cookies. When using a custom SPA flow or upgrading Spring Security, follow the CSRF guide for your exact version rather than copying old setups.

## 10. What Is CORS and When Does Swagger UI Need CORS?

CORS (Cross-Origin Resource Sharing) is a browser mechanism controlling whether JavaScript can read responses from another origin.

An origin consists of scheme, host, and port. Examples:

| Swagger UI | API | Cross-origin? |
|---|---|---|
| http://localhost:8080 | http://localhost:8080 | No |
| http://localhost:8080 | http://localhost:9090 | Yes, different port |
| https://docs.example.com | https://api.example.com | Yes, different host |
| https://docs.example.com | http://api.example.com | Yes, different scheme |

If Swagger UI and the API share the same origin, the browser does not require CORS for those requests. If Swagger UI calls an API on another origin, the API server must return appropriate CORS headers.

CORS can also be needed when Swagger UI loads the OpenAPI document from a URL outside the current domain, e.g., `springdoc.swagger-ui.url` pointing to another service. In that case, the origin must be allowed on the server serving the document.

CORS is not authentication and does not grant API access permissions. It only governs browser behavior for cross-origin requests. `curl`, Postman, or service-to-service clients do not enforce browser CORS policies.

## 11. Why Do CORS Preflight Requests Return 401 or 403?

For cross-origin requests with non-simple methods or headers, the browser sends an `OPTIONS` preflight request first:

~~~http
OPTIONS /api/products HTTP/1.1
Origin: https://docs.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

The server must confirm the allowed origin, method, and headers. Only if preflight succeeds does the browser send the real `POST`.

Preflight requests typically carry no session cookies or auth headers. If Spring Security authenticates the `OPTIONS` request before CORS is processed, the filter chain may return 401/403 because the request lacks credentials. Therefore, CORS must be processed before Spring Security authorization.

Enable CORS integration in Spring Security:

~~~java
http.cors(Customizer.withDefaults());
~~~

Spring Security can pick up an appropriate `CorsConfigurationSource`. When there are multiple `CorsConfigurationSource` beans or multiple `SecurityFilterChain` beans, specify the source per chain explicitly if Spring Security cannot auto-select it.

Do not merely add `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` and skip CORS configuration. Permitting `OPTIONS` does not automatically emit `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, or `Access-Control-Allow-Headers`; the browser will still block the request.

## 12. Configuring `CorsConfigurationSource`

Example for Swagger UI at `https://docs.example.com` calling the API:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(
        List.of("https://docs.example.com")
    );
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    );
    configuration.setAllowedHeaders(
        List.of(
            "Authorization",
            "Content-Type",
            "Accept",
            "X-XSRF-TOKEN",
            "X-Requested-With"
        )
    );
    configuration.setExposedHeaders(
        List.of("Location", "WWW-Authenticate")
    );
    configuration.setAllowCredentials(true);
    configuration.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
~~~

And enable it in the filter chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Explanation:

- `allowedOrigins` lists allowed origins, including scheme and port if applicable.
- `allowedMethods` lists HTTP methods the browser may invoke.
- `allowedHeaders` must include headers requested by preflight, such as `Authorization`, `Content-Type`, and the CSRF header.
- `exposedHeaders` lists response headers JavaScript needs to read, such as `Location`.
- `allowCredentials(true)` permits credentialed requests per the CORS protocol.
- `maxAge` lets browsers cache preflight results for a set duration.
- Register the exact API path, avoiding broader policies than needed.

When using `allowCredentials(true)`, never use `allowedOrigins("*")`. Declare explicit origins or controlled origin patterns. If the API does not use browser cookie/credential mode, consider `allowCredentials(false)` and permit only necessary headers.

For multiple origins, list each trusted origin explicitly. Never blindly echo arbitrary `Origin` request header values into `Access-Control-Allow-Origin`.

## 13. CORS with Cookies and CSRF

If Swagger UI is on another origin and the API uses session cookies, coordinate CORS, cookies, and CSRF:

1. CORS permits the exact Swagger UI origin.
2. Server allows credentials.
3. Browser sends cookies using the appropriate credential mode.
4. Cookies have `SameSite`/`Secure` attributes compatible with the topology.
5. Swagger UI retrieves the CSRF token per application mechanism.
6. Preflight allows the CSRF header, such as `X-XSRF-TOKEN`.
7. POST/PUT/PATCH/DELETE requests send the matching CSRF token.

`Access-Control-Allow-Credentials: true` alone does not cause browsers to send cookies. The client must also issue requests with matching credentials, and cookies must satisfy `SameSite`/`Secure`. For Swagger UI, check your version and configure `requestInterceptor` if controlling credential mode is needed.

Cross-site cookies generally require `SameSite=None; Secure`, but configure this only when your architecture truly needs cross-site cookies and the entire flow runs over HTTPS. Do not relax `SameSite` on every cookie just to fix a Try it out issue.

CORS preflight does not replace a CSRF token. An origin permitted to call the API must still provide a CSRF token if the endpoint uses cookies/sessions and CSRF protection is enabled.

## 14. Checking OpenAPI Security Schemes and Server URLs

Swagger UI invokes URLs based on the OpenAPI document. If `servers` points to the wrong host, port, scheme, or context path, Try it out may call the wrong origin and hit CORS or 404.

Example server declaration:

~~~java
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com",
            description = "Production API"
        )
    }
)
class OpenApiServerConfiguration {}
~~~

In local environments, use profiles or suitable document config so requests do not accidentally target production. Do not commit a staging or localhost server URL as the sole URL across all environments.

Check the `servers` section in `/v3/api-docs`, then check the actual Request URL sent by Swagger UI. If the application runs behind a reverse proxy or has a context path, configure forwarded headers and public URLs to match the deployment environment.

Security schemes in OpenAPI must also match the right type:

- HTTP bearer for `Authorization: Bearer ...`
- HTTP basic for Basic authentication.
- OAuth2 for authorization/token flows and scopes.
- apiKey for API keys in headers, queries, or cookies.

Declaring the wrong scheme can make Swagger UI send credentials in the wrong format even when Spring Security is configured properly.

## 15. Testing CORS Preflight with curl

You can check preflight responses without opening Swagger UI:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/products" \
  -H "Origin: https://docs.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

For an allowed origin and request, the response should typically include:

~~~http
Access-Control-Allow-Origin: https://docs.example.com
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Vary: Origin
~~~

When using credentials, the response needs `Access-Control-Allow-Credentials: true` and `Access-Control-Allow-Origin` must be the specific origin, never `*`.

`curl` does not enforce browser CORS policies; it only reveals which headers the server returns. A successful `curl` call does not prove browsers will accept the response. Ultimately test in a browser from the actual origin.

## 16. Testing CORS with MockMvc

MockMvc can send preflight requests and assert CORS headers:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductCorsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsSwaggerUiOriginToSendAuthorizedPostRequest() throws Exception {
        mockMvc.perform(options("/api/products")
                .header(HttpHeaders.ORIGIN, "https://docs.example.com")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"
                ))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://docs.example.com"
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"
            ));
    }
}
~~~

This test assumes the CORS policy allows credentials. If the application uses bearer headers without cookies, you can set `allowCredentials` to false and adjust assertions.

Add a test for disallowed origins:

~~~java
@Test
void doesNotAllowUntrustedOrigin() throws Exception {
    mockMvc.perform(options("/api/products")
            .header(HttpHeaders.ORIGIN, "https://untrusted.example")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            ))
        .andExpect(header().doesNotExist(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
        ));
}
~~~

Do not test only allowed origins. An overly permissive CORS configuration can pass happy-path tests while exposing the API to unintended origins.

## 17. Testing CSRF Tokens

With MockMvc and `spring-security-test`, you can verify that endpoints enforce CSRF:

~~~java
@Test
void rejectsStateChangingRequestWithoutCsrfToken() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice").roles("USER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "displayName": "Alice" }
                """))
        .andExpect(status().isForbidden());
}

@Test
void acceptsStateChangingRequestWithCsrfToken() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "displayName": "Alice" }
                """))
        .andExpect(status().isOk());
}
~~~

Add the test dependency if the project does not have it yet:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The two tests above assume `/web/profile` uses session authentication and CSRF protection. If a stateless API is configured to skip CSRF, do not apply this assertion to `/api/**`; test each chain's exact policy.

To verify Swagger UI's real cookie flow, integration/browser tests are needed: load the page, receive the CSRF cookie, send a state-changing request, and verify the token header is attached. MockMvc `.with(csrf())` only tests token-processing filters and does not prove Swagger UI JavaScript reads the cookie and sends the header properly.

## 18. Testing Security of Documentation and UI

If Swagger UI is exposed publicly, test that these endpoints return 200 or valid redirects:

- /swagger-ui.html
- /swagger-ui/index.html
- /v3/api-docs/swagger-config
- /v3/api-docs

Example:

~~~java
@Test
void exposesSwaggerUiAndOpenApiDocument() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ));

    mockMvc.perform(get("/v3/api-docs/swagger-config"))
        .andExpect(status().isOk());
}
~~~

If policy requires documentation authentication, test with appropriate credentials and roles rather than expecting public 200. Also verify UI assets are not blocked while the document is permitted, or vice versa.

With multiple `SecurityFilterChain` beans, testing each endpoint is a quick way to catch misconfigured chain matchers. A 200 HTML page does not prove JavaScript/CSS assets and JSON documents are all allowed to load.

## 19. Diagnosing CORS When Swagger UI Uses an External Document or API

Swagger UI can be configured with a document URL outside the application:

~~~yaml
springdoc:
  swagger-ui:
    url: https://catalog.example.com/v3/api-docs
~~~

Here the browser loads the document from `catalog.example.com`. The server serving the document must permit the origin hosting Swagger UI. If the document loads yet `servers` inside the document points to another host, Try it out requests also require CORS on that API host.

Distinguish two flows:

1. **CORS when loading the OpenAPI document:** browser calls the URL configured in Swagger UI.
2. **CORS when invoking an operation:** browser calls the URL in `servers` or the URL inferred by Swagger UI.

Each host may have a different policy. Enabling CORS on the app serving Swagger UI does not automatically enable CORS on an external API service.

## 20. Reading Logs and Response Headers to Identify the Rejecting Layer

In development, enable logging:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.web.cors: DEBUG
~~~

Logs help identify:

- Which `SecurityFilterChain` was selected.
- Whether the request was rejected at authentication, authorization, or the CSRF filter.
- Whether CORS configuration matched origin/method/headers.
- Whether the authentication provider or JWT decoder rejected credentials.

Turn off or lower logging after diagnostics. Never log access tokens, session IDs, CSRF tokens, or sensitive data.

Common clues:

| Clue | Investigation area |
|---|---|
| 401 with `WWW-Authenticate: Bearer` | Token, issuer, audience, expiry, signature |
| 403 with log showing CSRF missing/invalid token | CSRF cookie/header, token repository, request method |
| 403 with `AccessDenied` log | Role, authority, scope, matchers |
| OPTIONS 401/403 | CORS not running before security or source not selected |
| Response lacks `Access-Control-Allow-Origin` | Disallowed origin, unmatched path, or unconfigured CORS |
| API returns 200 yet browser reports CORS | Actual response lacks CORS headers or redirects to another origin |
| `/v3/api-docs` 401 while UI HTML 200 | Docs matcher not permitted or docs intentionally protected |

## 21. Risky Workarounds to Avoid

Avoid these approaches:

- Disabling all of Spring Security just to make Swagger UI work.
- Calling `permitAll()` on all of `/api/**`.
- Allowing `allowedOrigins("*")` together with `allowCredentials(true)`.
- Disabling CSRF globally when the application still uses session/cookie authentication.
- Allowing every method/header/origin without clear necessity.
- Putting tokens or cookies into OpenAPI examples.
- Hard-coding access tokens into Swagger UI configuration.
- Exposing `/v3/api-docs/**` publicly when the document contains internal endpoints or sensitive schemas.
- Using `@Hidden` to resolve 401/403; that annotation only affects documentation, not authorization.

If documentation must be public while APIs stay protected, allow reading the document under a dedicated policy while keeping API security rules intact. If the document itself is sensitive, protect it intentionally with authentication and supply credentials before Swagger UI loads it.

## 22. Quick Diagnostic Table

| Symptom | Common cause | How to fix |
|---|---|---|
| Swagger UI HTML returns 401 | `/swagger-ui/**` not permitted or requires login | Check matchers and authentication policy |
| Swagger UI HTML 200 yet `/v3/api-docs` 401 | OpenAPI endpoint not permitted | Add right matcher for docs or supply credentials before loading |
| Try it out returns 401 | Missing/invalid token or cookie | Check `Authorization`/`Cookie` in Network tab |
| Try it out returns 403 for GET | Missing role/scope or authorization policy | Check principal and authority mappings |
| POST returns 403, GET succeeds | Missing/invalid CSRF token or POST auth differs from GET | Check CSRF header and method rules |
| OPTIONS returns 401 | Preflight handled by authentication before CORS | Enable `http.cors()` and configure CORS source |
| OPTIONS returns 403 | Disallowed origin/method/header or blocked by filter | Compare `Access-Control-Request-*` against policy |
| Browser reports CORS yet curl succeeds | CORS is a browser-enforced policy | Inspect response headers in browser Network tab |
| `Authorization` missing from request | Security scheme or Authorize misconfigured | Check OpenAPI security scheme and token |
| Cookies not sent cross-origin | Mismatched credentials mode or `SameSite`/`Secure` | Check cookie attributes and browser request |
| CSRF cookie exists yet POST still 403 | Wrong header sent, stale token, or handler mismatch | Check `XSRF-TOKEN` and `X-XSRF-TOKEN` |
| CORS fails only in production | Proxy, host, HTTPS, or public origin differs from local | Check `Origin` and forwarded headers |
| One API group returns 401 | Group endpoint has different security policy | Check group URL and filter chain |
| Swagger UI calls wrong localhost | `servers` in OpenAPI uses wrong environment | Configure server URL per profile/environment |

## 23. Procedure for Handling a Try It Out Error

Follow this sequence:

1. Open the Network tab and reproduce the error.
2. Identify whether the failing request is a Swagger UI asset, `swagger-config`, OpenAPI document, `OPTIONS` preflight, or API operation.
3. Record URL, method, status, `Origin`, and request headers.
4. If 401, check authentication credentials and `WWW-Authenticate`.
5. If 403, check CSRF first, then roles/scopes and authorization matchers.
6. If CORS, check preflight, origin, method, allowed headers, and credentials.
7. Identify which `SecurityFilterChain` actually handles the request.
8. Fix matchers or configuration at the right layer; never broaden access across all APIs.
9. Test with MockMvc or WebTestClient.
10. Re-test in the browser from the exact origin and deployment environment.

## 24. References

- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS processing order, `CorsConfigurationSource`, and `SecurityFilterChain` integration.
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF tokens, cookie repository, JavaScript applications, and SPAs.
- [Springdoc OpenAPI FAQ](https://springdoc.org/faq.html): enabling CSRF support for Swagger UI via `springdoc.swagger-ui.csrf.enabled`.
- [Springdoc OpenAPI Properties](https://springdoc.org/properties.html): Swagger UI, OpenAPI endpoint, and related property configuration.
- [Spring Security – Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers and authorization rules.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): bearer JWT validation.
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS configuration in Spring MVC.
- [MDN – Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): origins, preflight, and CORS response headers.

## 25. Practical Summary

401 typically indicates an authentication issue; 403 can be authorization or CSRF; CORS is the browser's cross-origin policy. These three error classes can surface on different requests within a single Swagger UI interaction.

Pinpoint the exact request in the Network tab, inspect the security filter chain and headers, then adjust the right matcher, token flow, or CORS policy. Keep business APIs protected, expose documentation resources intentionally, and skip CSRF only for truly stateless endpoints. When Swagger UI, OpenAPI security schemes, and Spring Security runtime align, Try it out accurately reflects how real clients call the API.
