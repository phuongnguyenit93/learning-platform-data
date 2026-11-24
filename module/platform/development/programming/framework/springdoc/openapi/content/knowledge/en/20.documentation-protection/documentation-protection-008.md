# Session Cookies, CSRF, and State-Changing Try It Out Calls

Swagger UI lets users call APIs directly from the documentation page via the **Try it out** button. If Spring Boot authenticates users with session cookies, the browser automatically attaches cookies to matching requests. This is convenient for testing, yet it also means state-changing requests must be protected against Cross-Site Request Forgery (CSRF).

When integrating springdoc-openapi with Spring Security, three mechanisms must work together:

1. **Session cookie** identifies the login session and is sent automatically by the browser according to cookie policy.
2. **CSRF token** proves a state-changing request originated from an application that obtained a valid token.
3. **Swagger UI** sends the CSRF token in a header when a user uses Try it out, allowing Spring Security to verify the request.

CSRF is an independent protection layer separate from authentication and authorization. A request with a valid session can still be rejected if it lacks a CSRF token. Conversely, a valid CSRF token does not prove the user has business permission to perform the operation.

## 1. Why Do Session Cookies Need CSRF Protection?

Browsers automatically attach cookies matching the target URL. If a user is logged in to api.example.com, a malicious website can try to make that user's browser send a request to the API. The browser may attach the session cookie without the user noticing.

For example, suppose a user is logged in to an order management system. Another site could create a form submitting a request:

~~~html
<form action="https://api.example.com/api/orders/123/cancel" method="POST">
  <button type="submit">Continue</button>
</form>
~~~

If the endpoint lacks CSRF protection, the server may accept the request along with the user's session cookie and execute the order cancellation. Because browsers send cookies automatically, checking only that the session is logged in is insufficient to distinguish requests created by the legitimate application from forged requests.

A CSRF token adds a value that another website cannot read or validly guess. The client must send the token in a header or request parameter; browsers do not attach this value automatically to cross-site requests the way they attach cookies.

## 2. CSRF, Authentication, and Authorization Are Different

| Mechanism | Question Answered | Example |
| --- | --- | --- |
| Authentication | Who is sending the request? | Session cookie identifies the logged-in session |
| Authorization | Is that person allowed to do this? | User has permission to cancel orders |
| CSRF protection | Does the request carry a valid token from the app? | X-XSRF-TOKEN header matches server-stored token |

A POST request can:

- Have a valid session cookie yet lack a CSRF token: rejected.
- Have a valid CSRF token yet an expired session: unauthenticated.
- Have both a valid session and CSRF token yet insufficient permissions: rejected by authorization rules.
- Satisfy all three conditions: forwarded to the controller for business processing.

Do not disable CSRF simply because the API uses JSON, as browsers can still automatically send cookies on certain kinds of requests. Disabling CSRF is appropriate only when you have designed and verified that the API does not rely on automatic browser credentials—for instance, a stateless resource server accepting only bearer tokens explicitly placed in headers by the client.

## 3. Which HTTP Methods Require a CSRF Token?

By default, Spring Security protects unsafe HTTP methods—typically POST, PUT, PATCH, and DELETE. Safe methods such as GET, HEAD, OPTIONS, and TRACE should not be used to modify business state.

| Method | Typical Purpose | CSRF |
| --- | --- | --- |
| GET | Read resources | Token not required by default matcher |
| HEAD | Read metadata | Token not required by default matcher |
| OPTIONS | Discover HTTP/CORS capabilities | Token not required by default matcher |
| POST | Create resources or execute actions | Token required |
| PUT | Replace resources | Token required |
| PATCH | Partially update resources | Token required |
| DELETE | Delete resources | Token required |

Never build GET endpoints that delete data, process payments, cancel orders, or alter permissions. If an operation changes state, model it with an unsafe method and let the CSRF filter validate it.

Try it out gets no CSRF exemption. When a user clicks Execute for POST, PUT, PATCH, or DELETE, Swagger UI sends a real request to the API. That request requires a valid session, business permissions, and a valid CSRF token just like any request from another frontend.

## 4. Session Cookies and CSRF Cookies Are Two Separate Cookies

An application using cookie sessions typically has at least two kinds of cookies:

| Cookie | Function | Should JavaScript Read It? |
| --- | --- | --- |
| JSESSIONID or custom session cookie | Identifies the login session | No; keep HttpOnly |
| XSRF-TOKEN | Supplies token for client to send back in header | May need to be readable if using cookie-to-header |

The session cookie should have appropriate attributes:

- **HttpOnly** so JavaScript cannot read the session ID.
- **Secure** so it is sent only over HTTPS connections.
- **SameSite** per architecture, often Lax or Strict where appropriate.
- **Path** and **Domain** scoped as narrowly as needed.
- Cookie lifetime and session lifetime managed consistently.

If Swagger UI uses the cookie-to-header pattern, the CSRF cookie may need HttpOnly=false so JavaScript can read the token value and put it in the header. That does not mean disabling HttpOnly on the session cookie. Only the CSRF cookie read by the client needs readability; the session cookie must remain private.

## 5. Synchronizer Token and Cookie-to-Header

Two common patterns:

**Synchronizer Token Pattern:** the server stores the CSRF token in the session. The application receives the token via HTML, JSON, or a response header, then sends the token back in a header or form parameter. The server compares the received token against the token stored in the session.

**Cookie-to-header Pattern:** the server places the CSRF token in a JavaScript-readable cookie such as XSRF-TOKEN. The client reads that cookie and sends its value in a header such as X-XSRF-TOKEN. The server compares the header value with the expected token per the repository configuration.

Cookie-to-header flow:

~~~mermaid
sequenceDiagram
    actor User as User
    participant UI as Swagger UI
    participant API as Spring Boot + Spring Security

    User->>UI: Open API documentation
    UI->>API: GET /swagger-ui or /v3/api-docs
    API-->>UI: Set-Cookie: SESSION; Set-Cookie: XSRF-TOKEN
    User->>UI: Execute a POST request
    UI->>UI: Read XSRF-TOKEN from cookie
    UI->>API: POST /api/orders + Cookie + X-XSRF-TOKEN
    API->>API: Validate session and check CSRF token
    API->>API: Check business permissions
    API-->>UI: 2xx or appropriate error
~~~

Cookies are sent automatically by the browser. The CSRF header is added explicitly by the client. This difference lets the server distinguish requests that a browser might send automatically from requests crafted by an application that received the token.

Never use the session ID as the CSRF token. Nor should you check only the CSRF cookie while ignoring the header or request parameter: browsers send cookies automatically, so an attacker can trigger sending the cookie in a forged request.

## 6. Configuring CSRF in Spring Security

Spring Security enables CSRF protection by default for unsafe HTTP methods. By default, HttpSessionCsrfTokenRepository stores the token in HttpSession. If you want Swagger UI to read the token from a cookie and send the header automatically, you can use CookieCsrfTokenRepository.

The default repository uses:

- Cookie: XSRF-TOKEN.
- Request header: X-XSRF-TOKEN.
- Fallback request parameter: _csrf.

These names match the default configuration of springdoc Swagger UI CSRF support.

### Spring Security 7: SPA helper configuration

In Spring Security 7, you can use the spa() helper to configure a cookie repository and request handler suited for JavaScript applications:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .csrf(csrf -> csrf.spa())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**")
                    .authenticated()
                .requestMatchers("/api/**")
                    .authenticated()
                .anyRequest()
                    .permitAll()
            )
            .build();
    }
}
~~~

This snippet illustrates a policy requiring login for documentation and APIs; adjust matchers to fit your application. The csrf.spa() method was introduced in Spring Security 7.0. It handles SPA specifics such as cookie tokens, request handlers, and token refresh after authentication or logout.

### Spring Security 6: CookieCsrfTokenRepository and request handler

In Spring Security 6, you can start with CookieCsrfTokenRepository.withHttpOnlyFalse() so the client can read the CSRF cookie:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse()
                )
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**")
                    .authenticated()
                .requestMatchers("/api/**")
                    .authenticated()
                .anyRequest()
                    .permitAll()
            )
            .build();
    }
}
~~~

This covers only repository configuration, not the complete SPA setup for every Spring Security 6 application. Starting in Spring Security 6, CSRF tokens are deferred by default and use XOR-based BREACH protection. For an SPA reading the cookie token and sending the raw value in a header, you must configure a CsrfTokenRequestHandler following the official SPA guide to decode/compare tokens properly and ensure a fresh token is issued after login or logout. Never drop the default request handler just to make an example run without evaluating BREACH impact.

If using Spring Security 6, implement the SpaCsrfTokenRequestHandler class following the official example for your exact minor version in the Spring Security documentation. That setup combines XorCsrfTokenRequestAttributeHandler with CsrfTokenRequestAttributeHandler to handle headers and request parameters properly.

## 7. Enabling Built-In CSRF Support in springdoc Swagger UI

Springdoc provides dedicated properties so Swagger UI reads the CSRF token and sends it automatically in requests. For Spring Security's default cookie/header names, configure:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
      cookie-name: XSRF-TOKEN
      header-name: X-XSRF-TOKEN
      use-local-storage: false
      use-session-storage: false
~~~

Or using application.properties:

~~~properties
springdoc.swagger-ui.csrf.enabled=true
springdoc.swagger-ui.csrf.cookie-name=XSRF-TOKEN
springdoc.swagger-ui.csrf.header-name=X-XSRF-TOKEN
springdoc.swagger-ui.csrf.use-local-storage=false
springdoc.swagger-ui.csrf.use-session-storage=false
~~~

Meaning:

| Property | Effect |
| --- | --- |
| csrf.enabled | Enables sending CSRF tokens on requests from Swagger UI |
| csrf.cookie-name | Name of the cookie holding the token the UI should read |
| csrf.header-name | Name of the header sent back to the server with the token |
| csrf.use-local-storage | Reads token from Local Storage if the app stores it there |
| csrf.use-session-storage | Reads token from Session Storage if the app stores it there |

Per the Swagger UI Properties Reference, CSRF support is disabled by default; the default cookie is XSRF-TOKEN and the default header is X-XSRF-TOKEN. Springdoc added this feature starting in the 1.4.4 release line. Check your actual springdoc version before using these properties.

With standard cookie/header names, springdoc can attach the token automatically to Try it out requests. If your system uses different names or stores the token elsewhere, configure cookie-name/header-name or use a custom request interceptor.

## 8. Request Interceptor for Non-Standard CSRF Token Names

Swagger UI supports requestInterceptor to modify requests before sending them. This can be used when the backend uses custom cookie or header names. The following example illustrates reading a cookie:

~~~javascript
function readCookie(name) {
    const prefix = name + "=";
    const item = document.cookie
        .split("; ")
        .find(value => value.startsWith(prefix));

    return item ? decodeURIComponent(item.substring(prefix.length)) : null;
}

function csrfRequestInterceptor(request) {
    const apiOrigin = window.location.origin;
    const requestUrl = new URL(request.url, apiOrigin);

    // Only attach the token for trusted same-origin APIs.
    if (requestUrl.origin === apiOrigin &&
        requestUrl.pathname.startsWith("/api/")) {
        const token = readCookie("APP-XSRF");
        if (token) {
            request.headers["X-APP-CSRF"] = token;
        }
    }

    return request;
}
~~~

The interceptor must restrict the scope of URLs allowed to receive the token. Do not attach the CSRF token to every request regardless of destination, because Swagger UI may load OpenAPI definitions or call OAuth endpoints on external hosts. Sending the token to an external domain could leak it.

With springdoc, a custom request interceptor usually needs to be injected into Swagger UI via configuration or a resource transformer depending on how the UI is packaged. If standard names meet your requirements, prefer built-in CSRF properties to avoid maintaining custom JavaScript.

## 9. Protecting Session Cookies and CSRF Cookies

Session cookies and CSRF cookies have different requirements:

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: XSRF-TOKEN=...; Path=/; Secure; SameSite=Lax
~~~

In the cookie-to-header pattern, the CSRF cookie must be readable from JavaScript. Consequently, XSRF-TOKEN normally omits HttpOnly. The session cookie keeps HttpOnly to prevent scripts from reading the session ID.

Never put a CSRF token in a URL; query parameters can appear in logs or shared links. Never log session IDs or tokens. Tokens must be sufficiently random and verified by the server against the session or corresponding signing mechanism.

SameSite=Lax or Strict can mitigate some cross-site requests carrying cookies, yet should be treated as an additional defense layer. Do not rely solely on SameSite if the application spans multiple subdomains, integration flows, or browsers with differing policy enforcement.

## 10. CORS When Swagger UI and API Are on Different Origins

The simplest setup is serving Swagger UI and the API from the same origin. If docs run at https://docs.example.com while the API runs at https://api.example.com, requests are cross-origin even if both hosts belong to the same site.

When sending session cookies cross-origin, all of the following are needed:

- Swagger UI enables credentials on requests if its configuration requires it.
- Cookies have appropriate Domain/Path/Secure/SameSite attributes.
- The server allows the specific documentation origin.
- CORS allows credentials.
- CORS allows custom CSRF headers such as X-XSRF-TOKEN.

Spring MVC configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders(
                "Content-Type",
                "X-XSRF-TOKEN",
                "X-Request-Id"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Never combine allowedOrigins("*") with credentials. When using Spring Security, ensure CORS is processed properly in the filter chain and OPTIONS preflight requests do not require session/CSRF as if they were state-changing requests.

CORS does not replace CSRF. CORS primarily determines whether the browser lets JavaScript read cross-origin responses and send certain requests. The server must still validate CSRF tokens on state-changing requests.

## 11. Describing CSRF Requirements in OpenAPI

A CSRF token is not an access token and is not a user-authentication security scheme. It is an anti-forgery value tied to a server session or token mechanism.

For APIs called by multiple clients, documentation should explain:

- Which session cookie the API uses.
- How to obtain the CSRF token before sending state-changing requests.
- Which header or request parameter must be sent.
- When the token expires or must be refreshed, such as after login/logout.
- What response is returned when the token is missing or invalid.

You can document this on an operation using @Operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(
        summary = "Create order",
        description = """
            Requires a valid session cookie and a CSRF token in the
            X-XSRF-TOKEN header. Swagger UI is configured to automatically
            send the token read from the XSRF-TOKEN cookie.
            """
    )
    @PostMapping("/api/orders")
    OrderView createOrder(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

If documentation targets external integrators, you can describe the CSRF header via a Parameter Object or reusable component parameter. However, when Swagger UI has CSRF integration enabled, avoid forcing users to enter the same token manually if the UI already injects the header. Avoid duplicate declarations or confusing input fields.

Error response example:

~~~yaml
responses:
  '403':
    description: Missing or invalid CSRF token, or user does not have permission
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ProblemDetail'
~~~

If the API wants to distinguish CSRF failures from authorization failures, define an appropriate application error code or response detail. HTTP 403 can be returned for multiple AccessDeniedException types, so clients should not guess the cause solely from status code.

## 12. Try It Out Can Perform Real Mutations

Try it out sends requests to the backend configured in OpenAPI. If a user selects a production server and clicks Execute on POST, PUT, PATCH, or DELETE, production data can actually be modified.

Risk-reduction measures when providing Swagger UI:

- Provide a sandbox environment or test tenant for users trying calls.
- Use test accounts with least privilege.
- Restrict who can access the documentation and APIs.
- Use supported-submit-methods to disable methods you do not want executable from the UI.
- Write clear descriptions for destructive, payment, or notification-sending operations.
- Keep authorization and CSRF protection active just as for real requests.

Example allowing Try it out only for GET:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - head
~~~

This value controls only the Try it out button in Swagger UI. It does not lock down POST/PUT/PATCH/DELETE on the server and does not replace Spring Security. Users can still call endpoints using curl or another HTTP client if they are authorized.

## 13. Refreshing the CSRF Token After Login and Logout

Spring Security may clear the current CSRF token after successful authentication or logout. For SPAs using a cookie repository, the client must obtain a new token before the next unsafe request.

This typically plays out as follows:

1. The user logs in successfully.
2. A session is created or the session ID is rotated.
3. The old CSRF token is cleared to prevent binding a pre-auth token to the new session.
4. The client must issue a request to obtain a new token.
5. Subsequent POST/PUT/PATCH/DELETE requests send the new token in the header.

If Swagger UI receives 403 on the first request right after logging in, check whether the XSRF-TOKEN cookie was reissued. Reload the documentation or call your application's CSRF bootstrap endpoint, then retry.

In Spring Security 7, csrf.spa() handles SPA token-refresh details. In Spring Security 6, follow the request handler and fresh-token issuance setup documented for that exact version.

## 14. Testing CSRF with MockMvc

Spring Security Test provides the csrf() request post processor to verify whether an endpoint requires a CSRF token.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCsrfTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(user("tester").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"P-100","quantity":1}
                    """))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenCanReachAuthorizationAndController()
            throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(user("tester").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"P-100","quantity":1}
                    """))
            .andExpect(status().isCreated());
    }
}
~~~

The test assumes the endpoint returns 201 when the user is authorized and the payload is valid. If the controller returns 200 or requires a different authority, adjust assertions to match the real contract.

csrf() generates a token suitable for default testing. If the application uses CookieCsrfTokenRepository, add an integration test verifying the cookie token is issued and requests send the header with the right name, as well as checking that old tokens after logout are no longer accepted. MockMvc testing does not replace verifying cookie behavior in a real browser.

## 15. Testing Try It Out in the Browser

After configuring Spring Security and springdoc:

1. Open Swagger UI on an allowed origin.
2. Log in with a test account.
3. In Developer Tools, open the Network tab and reload the documentation page.
4. Check responses for Set-Cookie headers for session and CSRF token.
5. Verify the session cookie has HttpOnly, Secure, and SameSite per policy.
6. Verify the CSRF cookie is readable if using cookie-to-header.
7. Select a POST or PATCH operation and click Try it out.
8. Check that the request includes the session cookie and the X-XSRF-TOKEN header.
9. Verify the response succeeds and data changes only in a test environment.
10. Resend the request without the CSRF header or with an old token; the server must reject it.

If Swagger UI and the API are on different origins, also check OPTIONS preflight, Access-Control-Allow-Origin, Access-Control-Allow-Credentials, and Access-Control-Allow-Headers.

## 16. Common Pitfalls

**POST from Swagger UI returns 403 while GET works.** This is usually a sign that an unsafe request is missing the CSRF token or the token does not match the session. Inspect the CSRF cookie and header in the Network panel.

**Enabled springdoc CSRF yet the header does not appear.** Check springdoc.swagger-ui.csrf.enabled, cookie name, header name, and springdoc version. Make sure the browser actually receives the CSRF cookie.

**Session cookie is present yet XSRF-TOKEN cookie is missing.** Check whether Spring Security uses CookieCsrfTokenRepository, whether the token is materialized in the response, and whether the request handler matches your version.

**XSRF-TOKEN cookie is present yet JavaScript cannot read it.** Check the HttpOnly attribute on the CSRF cookie. For cookie-to-header, the CSRF cookie must be readable; the session cookie must remain HttpOnly.

**Spring Security 6 returns 403 even though the header contains the exact cookie value.** Check the SPA request handler and BREACH encoding. The cookie token may be the raw token while the default request handler expects an XOR-encoded value.

**First request right after login gets 403.** The CSRF token may have been cleared after authentication success. Fetch a new token before sending an unsafe request.

**Logout fails from Try it out.** Logout via POST typically also requires a CSRF token. Do not switch logout to GET to bypass CSRF.

**CORS preflight fails.** Allow the specific documentation origin, required methods, and CSRF header. When using credentials, never use a wildcard origin.

**Disabling CSRF makes Try it out work.** This is not an appropriate fix for APIs using session cookies. Re-enable CSRF and configure the token flow properly.

**Restricted methods in Swagger UI yet endpoints are still called.** supported-submit-methods only hides/disables actions in the UI. Use Spring Security and server-side permission checks to protect endpoints.

**CSRF token is sent to another host.** Check your custom request interceptor. Attach the token only for trusted API origins and paths.

## 17. Implementation Checklist

- [ ] Use session cookies with appropriate Secure, HttpOnly, and SameSite attributes.
- [ ] Keep CSRF protection enabled for cookie-authenticated APIs.
- [ ] Never use GET for state-changing actions.
- [ ] Choose HttpSessionCsrfTokenRepository or CookieCsrfTokenRepository according to architecture.
- [ ] If using cookie-to-header, make only the CSRF cookie readable; keep the session cookie HttpOnly.
- [ ] With Spring Security 7, consider csrf.spa() for SPAs.
- [ ] With Spring Security 6, configure the request handler per the SPA/BREACH guide for your exact version.
- [ ] Enable springdoc.swagger-ui.csrf.enabled=true.
- [ ] Synchronize cookie names and header names between Spring Security and springdoc.
- [ ] Refresh tokens after login/logout.
- [ ] If cross-origin, configure CORS credentials and explicit CSRF headers.
- [ ] Restrict who can access Swagger UI and use test environments.
- [ ] Do not treat supported-submit-methods as a server protection mechanism.
- [ ] Test requests with missing tokens, stale tokens, and valid tokens.
- [ ] Inspect the Network panel to confirm actual cookies/headers.

## 18. Conclusion

Session cookies let browsers maintain login sessions, yet because browsers send cookies automatically, state-changing requests need CSRF protection. Spring Security provides token repositories and request handlers; springdoc provides settings so Swagger UI reads the CSRF cookie and sends the token in a header during Try it out. Keep session cookies HttpOnly, expose only the CSRF cookie when needed for cookie-to-header, handle SPA/BREACH differences properly between Spring Security 6 and 7, and verify real requests in the browser. Try it out always calls real APIs, so protect the server and constrain test environments just as for any other client.

## 19. References

- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF filter, token repositories, CookieCsrfTokenRepository, BREACH, and SPA integration.
- [Springdoc — Swagger UI Properties Reference](https://springdoc.org/ui-properties.html): springdoc.swagger-ui.csrf.enabled, cookie-name, header-name, and storage options.
- [Springdoc — FAQ, CSRF support](https://springdoc.org/faq.html): enabling CSRF support in Swagger UI and using a request interceptor for non-standard token names.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): requestInterceptor and request/response interception.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, signed double-submit cookie, SameSite, and defense in depth.
