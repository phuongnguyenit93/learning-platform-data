# CORS, Preflight, and Handling Before Token Enforcement

When building a **Spring Security OAuth 2.0 / OIDC Resource Server** for a web application, the frontend and API often live on **two different origins**. For example, a JavaScript app running at `https://app.example.test` calls a Resource Server at `https://api.example.test` and sends an **OAuth 2.0 Bearer Access Token** in the `Authorization` header.

A common issue is: **the frontend has a valid Access Token yet the browser still reports a CORS error**, or **the OPTIONS request returns 401 for missing a token**. The reason is that before the actual request, the browser may send a **CORS preflight** to ask the server whether the cross-origin request is allowed. A preflight normally **carries no Bearer token**, so it must be handled **before the token authentication enforcement step**.

This lesson focuses on distinguishing **Origin, same-origin policy, CORS, and preflight**, configuring `http.cors(...)` and `CorsConfigurationSource` in Spring Security, the role of filter order, 401/403 error responses, relationships with CSRF and sessions/cookies, issues when running behind reverse proxies, and testing methods. Examples use **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet, and Java 17+**. Illustrative hostnames and tokens are not real credentials.

## 1. Real-world problem: the browser has a Bearer token yet cannot call the API

Suppose the frontend:

~~~text
https://app.example.test
~~~

calls the API:

~~~text
https://api.example.test
~~~

JavaScript code:

~~~javascript
async function loadOrders(accessToken) {
  const response = await fetch(
    "https://api.example.test/api/orders",
    {
      method: "GET",
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      }
    }
  );

  if (!response.ok) {
    throw new Error("API returned " + response.status);
  }

  return response.json();
}
~~~

The frontend may see in DevTools:

~~~text
Access to fetch at 'https://api.example.test/api/orders'
from origin 'https://app.example.test' has been blocked
by CORS policy.
~~~

A new developer might inspect the token, swap JWTs, tweak scopes, or turn off security. Yet **CORS does not mean JWT validation**. Sometimes the request containing the JWT was **never even sent**: the browser stopped beforehand because **the preflight failed**.

### 1.1. Two separate requests

With a cross-origin Authorization header, the browser typically sends:

~~~text
1. OPTIONS /api/orders
   Origin: https://app.example.test
   Access-Control-Request-Method: GET
   Access-Control-Request-Headers: authorization

   No Authorization: Bearer ...
                 |
                 v
   Server returns Access-Control-Allow-* headers
                 |
                 v
2. GET /api/orders
   Origin: https://app.example.test
   Authorization: Bearer ACCESS_TOKEN
                 |
                 v
   Spring Security authenticates token, checks scopes and data
~~~

**A preflight is not a business request.** It is the mechanism by which **the browser asks permission to perform a cross-origin request**. The browser needs to know whether the intended origin, HTTP method, and request headers are approved by the server before sending the actual request.

If the API demands a Bearer token on the OPTIONS request, the preflight can receive 401; the browser aborts and **never sends the GET**, even though the JavaScript app prepared a completely valid Access Token.

### 1.2. Design goals

A proper Resource Server must achieve two goals **at the same time**:

1. **Allow browsers to execute valid CORS preflights without a Bearer token.**
2. **Still require a valid Bearer token and proper permissions on actual API requests** such as GET, POST, PATCH, or DELETE.

You cannot solve this by opening all of `/api/**` with `permitAll()`: that would expose business endpoints. Nor should you blindly allow all `OPTIONS /**` while ignoring Origin/method/header policies. CORS must be handled properly in **a filter before authentication**.

## 2. What is an Origin?

A web page's **origin** is defined by **scheme + host + port**.

| URL | Origin | Compared to `https://app.example.test` |
| --- | --- | --- |
| `https://app.example.test/home` | `https://app.example.test` | Same origin. |
| `https://app.example.test/api` | `https://app.example.test` | Same origin. |
| `https://api.example.test/api` | `https://api.example.test` | Different host → different origin. |
| `http://app.example.test` | `http://app.example.test` | Different scheme → different origin. |
| `https://app.example.test:8443` | `https://app.example.test:8443` | Different port → different origin. |
| `https://app.example.test:443` | Default HTTPS port 443 | Equivalent to default HTTPS origin. |

**Path is not part of the origin.** Two URLs with the same scheme, hostname, and port share the same origin, even if their paths differ.

### 2.1. Same-Origin Policy

Browsers enforce the **Same-Origin Policy** to restrict how scripts from one origin read data from another origin. This policy helps prevent an arbitrary website from directly reading data from a site where the user is logged in.

**CORS — Cross-Origin Resource Sharing** is an HTTP mechanism allowing a server to inform the browser that **certain cross-origin callers** are permitted to make requests and read responses under declared conditions.

Example:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

This header tells the browser that origin `https://app.example.test` is allowed to access the response under CORS. It **does not grant OAuth scopes**, does not verify JWTs, does not prove user login, and does not replace owner/tenant checks in the domain.

### 2.2. CORS is a browser policy

Scripts in a browser are subject to same-origin/CORS, whereas `curl`, Postman, or a backend HTTP client **are not subject to browser CORS enforcement**.

Example:

~~~bash
curl -i \
  -H 'Authorization: Bearer TEST_ACCESS_TOKEN' \
  'https://api.example.test/api/orders'
~~~

A CLI client can call the API directly even if the server returns no `Access-Control-Allow-Origin`. It still must provide a valid Bearer token if the endpoint is protected.

Therefore, **CORS is not an API authentication layer** and is not a way to block non-browser clients outside allowed origins. To protect a Resource Server, use JWT/opaque validation, audience, scopes, and authorization; to restrict network callers, add network/gateway policies if needed.

## 3. What kind of request is a CORS preflight?

A **preflight** is an `OPTIONS` request automatically generated by the browser in cross-origin situations requiring permission checks before the actual request.

Example:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

The browser asks:

- Is origin `https://app.example.test` allowed to call the resource?
- Is sending **POST** allowed?
- Are request headers **Authorization** and **Content-Type** allowed?

A valid preflight response might be:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-ID
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

`200 OK` is just an example; **204 No Content** can also be appropriate depending on infrastructure. Browsers look for a successful status alongside matching CORS headers, without requiring one fixed success code across all implementations.

Once the preflight is approved, the browser sends the actual request:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Content-Type: application/json

{"productCode":"BOOK-01","quantity":2}
~~~

**This POST request itself** must pass Bearer authentication, scope authorization, and business validation. The preflight OPTIONS does not create an `Authentication` for the POST.

### 3.1. CORS preflight usually carries no token or cookie

A typical browser-sent CORS preflight **does not carry the main request's credentials**, including the `Authorization: Bearer` header or cookies. That is why it must be handled before filters that require user authentication.

Do not ask JavaScript to manually add `Authorization` to the preflight: the browser constructs this request and does not let the app attach a Bearer token to browser-managed OPTIONS preflight requests.

If a developer manually calls `fetch` with method `OPTIONS`, that is an **application-initiated request**, not necessarily a browser CORS preflight. The two types of OPTIONS must be distinguished via **`Origin`** and **`Access-Control-Request-Method`**.

### 3.2. When does the browser send a preflight?

In many cases, the browser sends a preflight when a cross-origin request **is not in the CORS-safelisted requests group**. Common cases:

- Sending an **Authorization header**, e.g., `Authorization: Bearer ...`.
- Using HTTP methods **PUT, PATCH, DELETE**.
- Sending `Content-Type: application/json` (not among safelisted Content-Types).
- Sending custom headers such as `X-Tenant-ID`, `X-Request-ID`, or `X-Requested-With` if not safelisted.
- Requests with other characteristics triggering a preflight under Fetch/CORS rules.

| JavaScript request | Usually preflighted? | Reason |
| --- | --- | --- |
| Cross-origin GET, no custom headers | Possibly **no** | GET may fall into the safelisted group. |
| GET + `Authorization: Bearer ...` | **Yes** | Authorization is not a safelisted request header. |
| POST + `Content-Type: application/json` | **Yes** | Content-Type is not safelisted. |
| POST with safelisted form Content-Type, no custom headers | Possibly **no** | May qualify as a simple CORS request. |
| PATCH + Bearer | **Yes** | Both method and Authorization require checking. |
| DELETE + Bearer | **Yes** | Method is not safelisted. |

Browsers can **cache successful preflights**, so DevTools will not necessarily show an OPTIONS before *every* GET/POST. Do not treat the absence of OPTIONS on a single call as proof that CORS is off.

### 3.3. Ordinary OPTIONS and preflight are not identical

Request:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
~~~

lacks `Origin` and `Access-Control-Request-Method`, so it is **not a CORS preflight** by standard detection. It may be an application/infrastructure OPTIONS request meant for normal handling, and **is not implicitly permitted without a token**.

Conversely:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

is a preflight that must be handled by the CORS processor before Spring Security demands a Bearer token. Proper CORS configuration avoids opening all OPTIONS requests to every client with a wildcard rule.

## 4. Meaning of CORS headers

### 4.1. Request headers group

| Header | Who sends it? | Meaning |
| --- | --- | --- |
| `Origin` | Browser | Origin where JavaScript initiates the request. |
| `Access-Control-Request-Method` | Browser in preflight | Intended method of the actual request. |
| `Access-Control-Request-Headers` | Browser in preflight | Intended request-header names for which the browser must ask permission. |
| `Authorization` | Client's actual request | Bearer Access Token; **not** a header sent in preflight. |

For example, `Access-Control-Request-Headers: authorization,content-type` contains **header names**, not the Access Token. The preflight only asks whether the `Authorization` header may be used, without supplying its value.

### 4.2. Response headers group

| Header | Role |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin permitted to read the response under CORS. |
| `Access-Control-Allow-Methods` | HTTP methods allowed for cross-origin requests. |
| `Access-Control-Allow-Headers` | Request header names the browser may send, e.g., `Authorization`, `Content-Type`. |
| `Access-Control-Allow-Credentials` | Indicates the browser may expose credentialed responses in the CORS flow; use only if the design permits. |
| `Access-Control-Max-Age` | Suggests how long the browser may cache the preflight result, subject to browser caps. |
| `Access-Control-Expose-Headers` | Response headers JavaScript may read beyond safelisted headers, e.g., `WWW-Authenticate`. |
| `Vary` | Informs shared caches that responses vary by Origin/preflight request parameters. |

Do not confuse:

~~~http
Access-Control-Allow-Headers: Authorization
~~~

with:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

The first allows the browser to **send the header named Authorization** on the actual request; the second allows **that specific origin** to access the response. Both conditions must be met when the browser sends a cross-origin Bearer token.

### 4.3. Missing even one header can make preflight fail

Example:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server responds:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Content-Type
~~~

The browser still rejects it because **POST is not in Allowed Methods** and **Authorization is not in Allowed Headers**. This is a CORS policy error, not an invalid JWT signature.

Conversely, if the server approves the preflight yet the actual request lacks or sends an invalid token, the actual request may receive **401**. CORS and Bearer authentication are **two separate decisions**.

## 5. Why must CORS be processed before Spring Security authentication?

In a Servlet Resource Server, Spring Security includes security filters such as **`BearerTokenAuthenticationFilter`** and **`AuthorizationFilter`**. If a preflight hits token-requiring logic **before CORS is handled**, the server can return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

The browser does not treat this as an approved preflight and aborts the request. The frontend typically sees only a **CORS error** instead of the API endpoint's JSON response.

### 5.1. Ideal ordering

~~~text
OPTIONS /api/orders (preflight, no token)
                  |
                  v
        CORS processor / CorsFilter
                  |
          Is Origin allowed?
          Is Method allowed?
          Are Headers allowed?
             /           \
           No            Yes
            |             |
            v             v
       CORS reject   Preflight response
                     Access-Control-Allow-*
                          |
                          v
                     Browser proceeds
                     with actual request

GET /api/orders (Authorization: Bearer ...)
                  |
                  v
          CORS check origin
                  |
                  v
          Bearer authentication
                  |
                  v
          HTTP authorization
                  |
                  v
          Domain authorization
~~~

**The CORS processor must run before Bearer token authentication is required.** With proper configuration, a valid preflight can be answered **right at the CORS layer** without hitting the JWT decoder or controller.

### 5.2. Spring Security recommends integrated CORS

Spring Security provides the DSL:

~~~java
http.cors(Customizer.withDefaults());
~~~

When a matching **`UrlBasedCorsConfigurationSource`** bean exists, Spring Security integrates CORS handling into the security filter chain. That is a clean, explicit choice for Servlet APIs.

Crucially, do not merely declare `permitAll()` for OPTIONS. **`permitAll()` lives in authorization**, which may be too late if Bearer authentication rejects the preflight earlier; moreover, it does not generate the **`Access-Control-Allow-*` response headers** the browser requires.

### 5.3. What happens without a CORS configuration?

If you only add:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

what can happen is:

1. OPTIONS passes security authorization.
2. No CORS processor answers Origin/Method/Headers properly.
3. The response is 200/404/405 without `Access-Control-Allow-Origin`.
4. The browser still blocks the actual request.

Thus **permitting OPTIONS** does not replace configuring a **CORS policy and filter ordering**.

## 6. Complete Spring Boot + Spring Security Resource Server configuration

Suppose the API is at `https://api.example.test`, and the approved frontend is **`https://app.example.test`**. The API uses JWT Bearer Access Tokens and does not use cookies/sessions for authentication.

### 6.1. Dependencies

Gradle Groovy DSL example with Spring Boot-managed versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 6.2. `application.yml` for the JWT Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

`issuer-uri` defines the trusted Authorization Server. `audiences` is supported in matching Spring Boot versions to require tokens issued for `orders-api`; on other versions, add an audience validator. Besides issuer/audience, the Resource Server needs JWT signature, expiration, algorithm, and matching token profile validators.

**This configuration does not solve CORS by itself.** CORS is configured separately on the Spring Security filter chain and `CorsConfigurationSource`.

### 6.3. `CorsConfigurationSource` bean

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Only allow approved frontends.
        cors.setAllowedOrigins(
            List.of("https://app.example.test"));

        // HTTP methods the frontend may use.
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH",
                    "DELETE", "OPTIONS"));

        // Request headers the browser is allowed to send.
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type",
                    "X-Request-ID"));

        // Allow the frontend to read these headers when API returns 401/403.
        cors.setExposedHeaders(
            List.of("WWW-Authenticate", "X-Request-ID"));

        // Example uses Bearer headers, not cookie credentials.
        cors.setAllowCredentials(false);

        // Browser may cache preflight per its limits.
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Explanation of each option:

- `allowedOrigins`: contains only approved origins, **without paths** like `/home`. Scheme, host, and port must match.
- `allowedMethods`: list of methods the browser may invoke cross-origin; **does not grant POST/DELETE permissions** in Spring Security. It is solely a CORS policy.
- `allowedHeaders`: includes **Authorization** and **Content-Type** when the frontend sends Bearer tokens and JSON bodies. HTTP header names are case-insensitive.
- `exposedHeaders`: lets the frontend read the **WWW-Authenticate** response header to inspect authentication/authorization errors from a cross-origin context.
- `allowCredentials(false)`: the example only uses explicitly attached header tokens and **does not need credentialed CORS cookie sessions**. If your design relies on cookies, see section 11.
- `maxAge`: browsers can cache preflights per their own policies; it does not extend token lifetimes.
- `registerCorsConfiguration("/api/**", ...)`: applies the CORS policy to API paths. Routes outside `/api/**` need their own policies if called cross-origin.

**Configuration note:** When declaring a custom `CorsConfigurationSource`, make sure the `SecurityFilterChain` uses that exact bean. With multiple beans of the same type or parallel MVC CORS settings, the framework may fail to resolve a single unambiguous source; configure explicitly to avoid conflicting policies.

### 6.4. `SecurityFilterChain`: CORS before Bearer token authentication

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // Integrate CORS into the Spring Security filter chain.
            .cors(Customizer.withDefaults())

            // Apply only when the API uses Bearer headers, not cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/public/catalog").permitAll()

                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(
                    HttpMethod.POST,
                    "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.PATCH,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .anyRequest().denyAll())

            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Worth noting:** The configuration above **does not declare an `OPTIONS /**.permitAll()` rule**. A properly integrated CORS processor recognizes and handles preflights before reaching Bearer-token-requiring logic. Actual API requests must still satisfy scope rules.

In this example there is a single chain not narrowed by `securityMatcher`, so it acts as the policy for other requests as well with a `denyAll()` fallback. If your application uses multiple chains, handle routing separately as in section 10.

Never disable CSRF application-wide simply because one API uses JWTs. When a backend serves both Bearer APIs and **cookie/session-based web OIDC Login**, separate the security chains and CSRF strategies appropriately.

### 6.5. Example controller

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record CreateOrder(String productCode, int quantity) {}

@RestController
@RequestMapping("/api")
public class OrdersController {

    @GetMapping("/public/catalog")
    Map<String, Object> catalog() {
        return Map.of("items", List.of("BOOK-01"));
    }

    @GetMapping("/orders")
    Map<String, Object> listOrders() {
        // Illustrative response, no database query.
        return Map.of("orders", List.of());
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, Object>> create(
            @RequestBody CreateOrder input) {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("created", true));
    }
}
~~~

This controller is for observing CORS/security behavior and **does not enforce complete business permissions**. A real system must validate inputs, authorize by user/tenant, and check ownership of each order.

## 7. How does the browser send the two different requests?

### 7.1. Preflight for a GET with an Authorization header

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

In the correct flow, the CORS processor checks whether origin `https://app.example.test` is in `allowedOrigins`, GET is in `allowedMethods`, and Authorization is in `allowedHeaders`. If so, the server replies with the matching `Access-Control-Allow-*` headers.

Then the browser sends:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Only on the **actual request** does `BearerTokenAuthenticationFilter` verify the JWT with the decoder. If the token is valid yet lacks `SCOPE_orders.read`, the request is still rejected with **403 Forbidden** after the successful preflight.

### 7.2. Preflight for a JSON POST

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

A successful preflight allows the browser to send:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Content-Type: application/json

{"productCode":"BOOK-01","quantity":2}
~~~

Spring Security must still require `SCOPE_orders.write`; CORS allowing POST **does not grant write permission**. CORS is only a condition for the browser **to be allowed to send the request**, not a guarantee the API **processes it successfully**.

### 7.3. What if there is no Origin?

A non-browser HTTP client can send:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Without `Origin`, the request can be processed as an ordinary API call without CORS response headers. It **must still pass JWT validation and authorization**. Absence of `Origin` is neither proof of a trusted caller nor a reason to skip Access Token enforcement.

## 8. CORS succeeds yet the API still returns 401 or 403

At least four scenarios should be distinguished:

| Scenario | Preflight | Actual request | What the frontend sees |
| --- | --- | --- | --- |
| Allowed Origin/Method/Headers, valid Bearer token, sufficient scope | Succeeds. | 200/201 per API. | Can read the response. |
| Valid preflight, actual request missing/invalid token | Succeeds. | **401 Unauthorized**. | Can read HTTP 401 if actual response has CORS headers. |
| Valid preflight, valid token lacking scope | Succeeds. | **403 Forbidden**. | Can read HTTP 403 if actual response has CORS headers. |
| Origin or headers not accepted by CORS | Fails. | Browser usually **does not send actual request**. | CORS/network error in JavaScript. |

**A successful preflight does not guarantee the actual request is authorized.** It merely clears the browser to send the request.

### 8.1. Example 401 after a valid preflight

The browser sends GET, yet the token has expired:

~~~http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.test
WWW-Authenticate: Bearer error="invalid_token"
~~~

This is a normal API response. When the proper CORS header is present, the frontend can read `response.status === 401`. If configuration exposed `WWW-Authenticate`, the frontend can also read `response.headers.get("WWW-Authenticate")`.

Never fix this error by adding `permitAll()` to the API: the token must be refreshed or the client must reauthenticate via the proper OAuth flow.

### 8.2. Example 403 after a valid preflight

The token has `orders.read`, yet the client invokes POST:

~~~http
HTTP/1.1 403 Forbidden
Access-Control-Allow-Origin: https://app.example.test
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

CORS is still working. The failure is **authorization**: the client lacks `orders.write`. Refreshing a token with the same permissions will not magically grant a new scope.

### 8.3. When an actual 401/403 is surfaced as a "CORS error"

If the authentication/authorization handler returns 401/403 **without `Access-Control-Allow-Origin`**, the browser may block JavaScript from reading the response. The frontend then sees a CORS error instead of the real HTTP status code.

Therefore, ensure **CORS processing runs before security error handlers**, so error responses to requests from approved origins still include proper CORS headers. This lets the frontend distinguish an **invalid token** from an **insufficient scope** without loosening permissions.

If a 401/403 is generated by an **API gateway, CDN, or reverse proxy** before reaching Spring Security, those responses also need the right CORS policy for valid origins. Backend Java CORS settings alone cannot fix responses blocked at an upstream network layer.

## 9. Should you use `permitAll` for OPTIONS?

Do not treat:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

as a default CORS solution. It has three problems:

1. **It does not generate the CORS headers** needed for the browser to accept the response.
2. **Authorization rules may run after the authentication filter**; if a filter already rejected the preflight, `permitAll` is too late.
3. **Opening all OPTIONS requests** may be inappropriate for endpoints with business OPTIONS semantics or across multiple security chains.

Some applications have explicit requirements to allow OPTIONS at a gateway or HTTP policy; that must be an intentional decision and does not replace configuring a **CORS source** and filter ordering.

### 9.1. When does an OPTIONS request need a token?

An **OPTIONS request that is not a CORS preflight** may be handled by the API as a normal HTTP request. It is not automatically exempt from authentication merely because its method is OPTIONS.

A standard preflight is identified by:

- Method **OPTIONS**.
- Header **Origin**.
- Header **Access-Control-Request-Method**.

If a caller tries to send arbitrary `OPTIONS` requests to an internal endpoint for business behavior, it should pass through the endpoint's designed policy. **The CORS filter exists to handle preflights properly**, not to turn all OPTIONS requests into an access-control bypass.

### 9.2. What if the preflight returns 404/405?

A common cause is that the CORS processor **is not integrated** or the request hits another router first. The browser sends OPTIONS, which reaches `DispatcherServlet`/a controller without an OPTIONS mapping, producing 404/405.

The fix is to inspect **CORS filter and path registration** before rushing to add `@RequestMapping(method=OPTIONS)` to every controller. When CORS is properly wired, valid preflights are typically answered in the filter without writing manual OPTIONS controller endpoints.

## 10. Multiple SecurityFilterChains: ensuring OPTIONS enters the right chain

An application may be split into:

~~~text
/api/**       -> Bearer JWT Resource Server
/web/**       -> OIDC Login and HTTP session
/actuator/**  -> Separate management policy
fallback      -> denyAll
~~~

In Spring Security:

- `http.securityMatcher(...)` decides **which `SecurityFilterChain` applies** to the request.
- `authorizeHttpRequests().requestMatchers(...)` decides **permissions inside the selected chain**.
- `@Order` determines priority between chains; the first matching chain is chosen.

### 10.1. Configuring an API chain with CORS

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

This is a **multi-chain structural option**, an alternative rather than something deployed alongside the single-chain example in section 6. The API group here uses `authenticated()` to focus on routing; in production, replace it with appropriate **scope/authority rules** per endpoint.

Crucially, `securityMatcher("/api/**")` **is not restricted by method**: both the OPTIONS preflight and the actual GET/POST enter the same API chain where the CORS processor resides.

### 10.2. Bug: a chain matching only GET/POST

A careless configuration might match a chain only on **method GET**:

~~~text
API chain: matches only GET /api/**
Preflight: OPTIONS /api/orders
         -> does not match API chain
         -> falls into fallback chain
         -> blocked before the API's CORS policy
~~~

Here GET may succeed in direct tests yet the browser still cannot send the real GET because OPTIONS landed in another chain. Design chain matchers to cover **both preflight and actual requests** of the same API, or place a CORS filter outside all security chains under a controlled architecture.

### 10.3. OIDC Login and session cookies differ from Bearer APIs

When a backend simultaneously serves:

- **Web routes** authenticated via session/cookie after `oauth2Login()`.
- **API routes** authenticated with `Authorization: Bearer`.

keep these clearly separated:

1. CORS: which origins may call which endpoints?
2. CSRF: do forms/session cookies need CSRF tokens?
3. Session policy: browser web uses sessions; Bearer API can be stateless.
4. Entry points: web login may redirect; API typically returns a 401 Bearer challenge.
5. CORS filter chain: preflights are not redirected to a login page.

Do not apply `csrf.disable()` or `SessionCreationPolicy.STATELESS` to all web routes just to fix an API preflight issue.

## 11. How do CORS, cookie credentials, and CSRF differ?

### 11.1. Bearer headers and cookie sessions

Two frontend architectures may both run in a browser while using different credential mechanisms:

| Architecture | Actual request credential | Key notes |
| --- | --- | --- |
| **Bearer API** | `Authorization: Bearer ...` header explicitly sent by client. | CORS must allow Authorization; JWT/opaque validation on actual request. |
| **Web session** | Cookie auto-sent by browser per cookie policy. | CORS credentials and CSRF/SameSite must be designed together. |
| **BFF (Backend for Frontend)** | Browser uses session cookie with BFF; BFF calls API server-side. | Browser may not hold Access Tokens directly; CSRF and cookies remain critical at BFF. |

There is no rule that every Spring Security JWT API must set `allowCredentials=true`. If cookies or client certificates are not used in cross-origin credentialed requests, **leaving credentials disabled** reduces surface area and prevents confusion.

### 11.2. When using cookies and credentials mode

For cross-origin requests where the browser must send cookies/sessions, the CORS policy may need to return:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

The frontend can use:

~~~javascript
fetch("https://api.example.test/web/profile", {
  credentials: "include"
});
~~~

With credentialed requests, **never use `Access-Control-Allow-Origin: *`** to allow all origins. The server must return the specific approved origin and never echo `Origin` unconditionally. Cookies remain governed by **SameSite, Secure, Domain, and Path**; CORS does not by itself force browsers to send cookies.

**Important:** If the server uses cookies for authentication, **CORS does not replace CSRF protection**. A cross-origin simple request can be sent and cause side effects regardless of whether the browser blocks JavaScript from reading the response. Automatic cookie attachment is why CSRF must be evaluated separately.

### 11.3. Example of CSRF not reliably blocked by CORS

Suppose a banking website uses a session cookie and an endpoint:

~~~http
POST /transfer HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=...

amount=100&to=another-account
~~~

If the request takes a form the browser sends **without a preflight**, the CORS policy may only prevent external scripts from **reading the response**; it does not reliably stop the server from processing the transfer. Hence CSRF tokens, SameSite cookie policies, and proper anti-CSRF measures are needed—**never rely on CORS as your sole protection**.

### 11.4. "`allowCredentials`" does not grant OAuth permissions

`Access-Control-Allow-Credentials: true` is a browser/CORS mechanism. It **does not mean JWTs automatically gain scopes**, does not create sessions, and does not replace `Authorization: Bearer`.

Conversely, `Access-Control-Allow-Credentials: false` does not protect an API from all invalid requests. The Resource Server still must authenticate and authorize every actual request.

## 12. Insecure CORS configurations to avoid

### 12.1. Opening all origins for development speed

Example:

~~~java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowedMethods(List.of("*"));
cors.setAllowedHeaders(List.of("*"));
~~~

For an API holding sensitive data, this configuration opens cross-origin response reading far wider than needed. It does not remove JWT authentication, yet can widen exposure to external websites whenever a client already holds credentials.

Evaluate the approved set of frontends carefully, especially if the site also uses cookies/sessions. Never combine `allowCredentials(true)` with a literal wildcard origin in violation of CORS; Spring may reject that combination outright.

### 12.2. Blindly reflecting `Origin`

Dangerous example:

~~~java
// DO NOT DO THIS:
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin"));
~~~

This trusts the caller-supplied `Origin` and opens cross-origin access to any website. `Origin` is an input for **allowlist checking**, not a value the server should trust unconditionally.

### 12.3. Allowing arbitrary subdomains without control

If the frontend lives at `app.example.test`, do not hastily allow `https://*.example.test`: a subdomain hosting user-uploaded content or suffering a takeover could become an approved origin.

Spring supports `allowedOriginPatterns` for flexible matching when needed, but consider:

- Who can create subdomains?
- Do any subdomains run untrusted JavaScript?
- Are there lookalike/IDN/different-port/different-scheme domains?
- Are cookie credentials allowed?
- Are development origins like localhost leaking into production?

An **explicit allowlist** is usually simpler and easier to audit than overly broad patterns.

### 12.4. Using HTTP scheme in production frontends

`http://app.example.test` and `https://app.example.test` are different origins. Never add an HTTP origin to production just to silence browser CORS errors when the web app requires HTTPS. CORS does not protect tokens in transit; both API and frontend must use proper TLS.

### 12.5. Exposing all response headers

Do not expose headers carrying sensitive data merely for frontend debugging. `Access-Control-Expose-Headers` should be limited to headers genuinely needed by client code, such as `WWW-Authenticate` or a request correlation ID.

Never return a Bearer Access Token in a response header to an unauthorized client. **CORS exposed headers are not an Access Token delivery mechanism.**

## 13. Do not confuse Authorization Server CORS with Resource Server CORS

In an OAuth 2.0 / OIDC system there are at least two addresses:

~~~text
Authorization Server:
  https://identity.example.test

Resource Server API:
  https://api.example.test
~~~

The frontend may:

1. Navigate the browser to the Authorization Server's **Authorization Endpoint** to log in.
2. Receive an authorization code at the OAuth2 Client's redirect URI.
3. Use appropriate OAuth2 Client mechanisms (e.g., Authorization Code + PKCE) to obtain an Access Token.
4. Send the Access Token to the **Resource Server** to call the API.

CORS on the Resource Server API does not automatically allow the frontend to call the **Authorization Server token endpoint** cross-origin. The token endpoint, discovery, JWKS, userinfo, and authorization endpoint each have their own policies and contracts.

### 13.1. Do not use fetch in place of authorization redirects

The OAuth2 Authorization Endpoint is typically invoked via **top-level browser navigation/redirect**, not a cross-origin `fetch` expecting JSON to render a login page. Browser CORS on `fetch` calls to the Authorization Endpoint may be blocked by design and should not be "fixed" by opening broad CORS on the IdP.

### 13.2. API CORS only serves requests reaching that API

Configuration:

~~~java
source.registerCorsConfiguration("/api/**", cors);
~~~

applies only to requests hitting URLs registered in that Spring application. If the frontend calls an IdP on another domain, **the IdP** controls CORS there. If the frontend calls the API through a gateway on another domain, **gateway and backend** must align on CORS.

### 13.3. An API gateway can change behavior

Example:

~~~text
Browser
  -> https://gateway.example.test/api/orders
  -> API Gateway
  -> Spring Resource Server
~~~

The gateway may:

- Handle preflight OPTIONS itself without forwarding to Spring.
- Block OPTIONS because a gateway policy only allows GET/POST.
- Enforce Authorization at the gateway before CORS runs.
- Add or strip `Access-Control-Allow-Origin`.
- Return 401/403 before the backend ever sees the request.

**If the gateway generates the response, CORS must be resolved at the gateway or at a layer before it rejects requests.** Backend `http.cors()` configuration cannot fix responses generated entirely at the gateway tier.

Designate a clear **source of truth** for the CORS policy, or coordinate layers so they agree on a single allowlist. Never let both proxy and backend emit duplicate or conflicting `Access-Control-Allow-Origin` headers, as browsers can reject the response.

## 14. Preflight caching, `Vary`, and performance

### 14.1. `Access-Control-Max-Age`

When the server returns:

~~~http
Access-Control-Max-Age: 1800
~~~

it tells the browser it may cache the preflight result for a suggested duration. Browsers enforce their own internal caps, so exact 1800-second caching is not guaranteed across all browsers.

**Preflight cache is not a token cache.** It does not store the user's `Authentication`, does not extend a JWT's `exp`, and does not let the API skip token validation on actual requests.

### 14.2. `Vary` prevents cross-origin cache poisoning

When a server permits multiple origins from an allowlist, responses can differ by `Origin`:

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Shared caches/CDNs must respect these variance dimensions so they do not serve origin A's CORS response to origin B. Standard `CorsFilter` typically sets the relevant headers, yet upstream proxies may still cache or alter responses; verify behavior end-to-end.

### 14.3. Do not change CORS policy while forgetting caches

If you just removed an origin from the allowlist, browsers may retain an **old preflight cache** briefly. Even with a cached preflight, **actual requests still pass through server-side CORS checks and authentication**. Never rely on preflight alone as data-access enforcement.

For responses carrying sensitive user data, HTTP caching should have its own policy such as appropriate `Cache-Control`. Do not conflate preflight caching with response caching or JWT caching.

## 15. Testing with curl: accurately simulating a preflight

**curl does not enforce CORS policies** the way a browser does, yet it can observe which headers the server returns for a simulated preflight request.

### 15.1. Valid preflight

~~~bash
curl -i -X OPTIONS \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Expected result (implementation-dependent):

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-ID
~~~

**Do not send a Bearer token** in the simulated preflight command. If you receive a 401 Bearer challenge, inspect CORS filter ordering and where a token was required before the CORS processor.

### 15.2. Preflight from a disallowed origin

~~~bash
curl -i -X OPTIONS \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

With Spring's CORS processor, a disallowed origin typically receives **403 Invalid CORS request** or no matching CORS allowance. A browser **will not send the actual request** when the preflight is rejected.

Not every system must return the exact body message "Invalid CORS request"; what matters is that the policy grants no CORS permission to disallowed origins.

### 15.3. Actual API request without a token

~~~bash
curl -i \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://app.example.test'
~~~

Expected:

~~~http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.test
WWW-Authenticate: Bearer
~~~

The response may carry the CORS header yet **still return 401 for missing a token**. This is the desired behavior, not broken CORS.

### 15.4. Actual API request with a token

~~~bash
curl -i \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Authorization: Bearer TEST_ACCESS_TOKEN'
~~~

If the token is genuinely valid, matches issuer/audience, and has read scope, the request passes HTTP authorization. Otherwise, the API returns 401 or 403 depending on the failure. Never paste real Access Tokens into terminals with shared history/logs; use test fixture tokens or secure secret handling.

**Note:** curl always sends the actual request when invoked; unlike a browser, it does not abort after a failed preflight. Therefore combine curl checks with browser tests or MockMvc to verify full security behavior.

## 16. Testing Spring Security CORS with MockMvc

Test objectives:

1. A valid preflight **does not require a Bearer token**.
2. A disallowed origin **receives no CORS allowance**.
3. Actual requests still require a JWT.
4. CORS success does not by itself grant scopes.
5. HTTP 401/403 responses on actual requests still include CORS headers so the frontend can read them.

### 16.1. Example test with SpringBootTest

Assumes `ApiCorsConfig`, `ApiSecurityConfig`, and `OrdersController` from section 6 are present. The test defines a synthetic decoder solely to avoid connecting to an Authorization Server during application context startup; `with(jwt())` requests create a test `Authentication` **without invoking the decoder**.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(CorsPreflightHttpTest.TestDecoder.class)
class CorsPreflightHttpTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException(
                    "Synthetic decoder rejects raw tokens");
            };
        }
    }

    @Test
    void validPreflightDoesNotRequireBearerToken() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                containsString("Authorization")));
    }

    @Test
    void unknownOriginIsRejected() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://evil.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualRequestStillRequiresJwt() throws Exception {
        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"));
    }

    @Test
    void validPrincipalWithReadScopeCanAccessGet()
            throws Exception {
        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void readerCannotPostEvenIfCorsAllowsPost()
            throws Exception {
        mvc.perform(post("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test")
                .contentType("application/json")
                .content("{\"productCode\":\"BOOK-01\",\"quantity\":2}")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"));
    }
}
~~~

These tests demonstrate **CORS + HTTP authorization** assuming the example's controller and beans are present. If your project already defines a production `JwtDecoder`, adjust the test bean to avoid conflicts. If using a real controller or different policy paths, update expected statuses accordingly.

**Important:** `spring-security-test`'s `with(jwt())` directly creates an authenticated principal **without verifying JWT signature, issuer, audience, or expiration**. Therefore, add separate decoder tests using JWTs signed with a test key. Meanwhile, the preflight test verifies the path with `Origin`/`Access-Control-Request-Method` and no `Authorization` header.

### 16.2. Testing non-preflight OPTIONS

To avoid accidentally opening all OPTIONS requests, add a test:

~~~java
mvc.perform(options("/api/orders"))
    .andExpect(status().isForbidden());
~~~

In a **single-chain `SecurityFilterChain` with `anyRequest().denyAll()`**, an OPTIONS request lacking `Origin`/`Access-Control-Request-Method` is not treated as a preflight by the CORS filter; if the request is unauthenticated, depending on Spring Security's entry point, the status may be **401 instead of 403**. In real tests, assert that **it is denied** per policy rather than rigidly assuming one status code. To assert an exact status, include an authentication fixture to avoid anonymous/entry-point differences.

### 16.3. Testing disallowed methods and headers

Example preflight requesting a method not in allowed methods:

~~~java
mvc.perform(options("/api/orders")
        .header(HttpHeaders.ORIGIN,
            "https://app.example.test")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
            "TRACE"))
    .andExpect(status().isForbidden());
~~~

With an unapproved request header:

~~~java
mvc.perform(options("/api/orders")
        .header(HttpHeaders.ORIGIN,
            "https://app.example.test")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
            "x-unapproved-header"))
    .andExpect(status().isForbidden());
~~~

These tests confirm the policy does not blindly pass every OPTIONS request carrying a valid Origin.

### 16.4. Should you verify `JwtDecoder` is not called on preflight?

An advanced test can spy/mock `JwtDecoder` and assert `decode` is never invoked when the browser sends a **valid OPTIONS preflight without an Authorization header**. However, if the test uses a stub decoder and the preflight carries no token, the decoder normally isn't called anyway; what matters more is that the response **is approved by the CORS processor before authentication enforcement** while actual endpoints stay protected.

Consider integration tests with a **real frontend/browser** or browser automation to verify the browser actually sends GET/POST after OPTIONS succeeds. MockMvc does not fully simulate browser CORS enforcement, preflight caching, or network proxies.

## 17. When the frontend still reports errors, isolate the cause layer by layer

### 17.1. Symptom and cause matrix

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| OPTIONS returns **401 Bearer** | Authentication runs before CORS or preflight hit another chain. | `http.cors()`, `CorsConfigurationSource`, filter chain order, gateway. |
| OPTIONS returns **403 Invalid CORS request** | Origin/method/headers not allowlisted or path does not match CORS mapping. | `allowedOrigins`, `allowedMethods`, `allowedHeaders`, `/api/**`. |
| OPTIONS returns 404/405 | CORS filter did not handle it; request reached routing/controller. | Filter registration/chain selection before adding OPTIONS controllers. |
| OPTIONS returns 200 but lacks `Access-Control-Allow-Origin` | Response is not a valid CORS approval. | CORS source, Origin, and proxy headers. |
| OPTIONS returns 200, ACAO right, yet Authorization missing from Allow-Headers | Browser not allowed to send Bearer header. | `allowedHeaders` list. |
| Actual GET returns 401 | Missing Bearer token, or invalid signature/audience/issuer/exp. | Decoder and auth entry point; do not open public endpoints. |
| Actual POST returns 403 | Valid token missing write scope or domain permission. | `SCOPE_orders.write`, data policies. |
| API returns 401/403 yet JavaScript only sees CORS error | Error response lacks ACAO or proxy blocked before backend. | CORS on error responses, gateway/CDN. |
| curl succeeds yet browser fails | curl does not enforce CORS. | DevTools Network, OPTIONS, and CORS response headers. |
| Works in dev, fails in production | Different scheme/host/port, CDN, or HTTPS reverse proxy. | Production origins, gateway, environment config. |
| Cookies not sent | Mismatched credentials mode/SameSite/Secure/Domain/CORS policy. | Cookie policy and CORS credentials; check CSRF separately. |
| CORS works intermittently or returns wrong origin | Shared cache ignoring `Vary` or inconsistent node configs. | CDN/cache `Vary`, deployment consistency. |

### 17.2. Using DevTools effectively

In Chrome/Firefox/Safari DevTools:

1. Open **Network**, filter by Fetch/XHR or inspect requests by path.
2. Locate the **OPTIONS** request preceding the GET/POST.
3. Read **Request Headers**: Origin, Access-Control-Request-Method, Access-Control-Request-Headers.
4. Read **Response Headers**: Access-Control-Allow-Origin/Methods/Headers, Vary, and status.
5. If OPTIONS succeeded, check whether the **actual request** includes Authorization and returns 401/403/2xx.
6. If OPTIONS is absent, check browser preflight caching or whether the request triggers a preflight.
7. If a gateway/redirect appears, inspect the actual URL, status, and where the response originated.

Avoid pasting Bearer Tokens from DevTools into public tickets/chats/screenshots. Redact headers/tokens and share only status, Origin, method, header names, and request IDs.

### 17.3. Never "fix" CORS errors by disabling Spring Security

A dangerous reaction:

~~~java
// DO NOT DO THIS to "fix CORS".
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
~~~

Or:

~~~java
// DO NOT DO THIS in real environments just to bypass OPTIONS:
.oauth2ResourceServer(oauth -> { })
~~~

These changes can strip Bearer token protection from the API. **The right path is fixing the CORS policy and filter order**, while keeping authentication and authorization enforced on actual requests.

## 18. Edge cases to recognize

### 18.1. Preflight gets redirected

The browser sends:

~~~text
OPTIONS https://api.example.test/api/orders
~~~

yet a proxy replies:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/sign-in
~~~

This indicates the preflight was treated as an unauthenticated request. A CORS preflight should never be redirected to a login UI; it must be answered with appropriate CORS headers at the resource origin, **before Bearer token enforcement**. Browsers/environments handle redirects on preflights inconsistently, so never rely on redirects for preflights.

### 18.2. HTTPS redirect at proxy

If the frontend calls `http://api.example.test` and the server redirects to HTTPS, the preflight can fail due to redirect rules or mixed-content policies. The frontend should use the **final HTTPS URL** from the start. Never use CORS workarounds to permit sending Bearer tokens over plain HTTP.

### 18.3. Gateway performs auth before CORS

A gateway with a JWT plugin might enforce Authorization on **every** method, including OPTIONS. In that case, the downstream Spring Resource Server with `http.cors()` never even sees the OPTIONS request.

Adjust gateway ordering: handle valid CORS preflights before auth at the gateway, or place a proper CORS layer ahead of the JWT/auth plugin. **Do not** open actual GET/POST requests in the same way.

### 18.4. Reverse proxy rewrites the path

For example, the browser calls:

~~~text
https://gateway.example.test/orders-api/api/orders
~~~

yet the proxy rewrites it to:

~~~text
/api/orders
~~~

`CorsConfigurationSource` in Spring must match **the path the application actually receives**, rather than guessing from the pre-proxy URL. If you register `/api/**` while the backend sees `/orders-api/api/**`, the CORS policy will not apply.

### 18.5. Duplicate CORS response headers

If both the gateway and Spring emit:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

and infrastructure collapses them into two invalid header values, the browser may reject the response. Establish a single source for CORS headers and ensure layers do not produce conflicting values. Only allow approved origins; never reflect arbitrary Origins.

### 18.6. Downloads or streaming responses

If the frontend needs to read `Content-Disposition` for a filename or `X-Request-ID` for tracing, add those header names to **`exposedHeaders`**. This grants permission for JavaScript to **read the response header**, not permission to download the file; the endpoint must still validate tokens and check data permissions.

### 18.7. Methods beyond GET/POST

Methods like PATCH, DELETE, HEAD, OPTIONS, and custom application methods must be explicitly evaluated:

- Are they allowed cross-origin?
- Is there a real backend handler?
- Is there an appropriate JWT scope rule?
- When will browsers preflight them?
- Do proxies/gateways forward and control them consistently?

Allowing `DELETE` in `Access-Control-Allow-Methods` **does not** permit a user to delete resources. It only tells the browser it may send that method cross-origin; authorization must still be enforced.

## 19. Relationship with web state and other security headers

Within the **Web Security and State** chapter, view CORS as part of the broader browser security picture:

| Mechanism | Purpose | Cannot replace |
| --- | --- | --- |
| **CORS** | Controls browser cross-origin request/response sharing. | JWT validation, authorization, CSRF. |
| **CSRF protection** | Prevents unintended state-changing requests when browsers auto-attach credentials. | CORS policy or data authorization. |
| **SameSite/Secure cookies** | Restricts how browsers send cookies and protects cookies over HTTPS. | Bearer token validation, CORS allowlist. |
| **Content Security Policy (CSP)** | Mitigates certain untrusted content loading/execution risks. | OAuth scopes, CORS, authorization. |
| **HTTPS/TLS** | Protects data in transit and authenticates the server. | Origin decisions, token scopes, owner/tenant checks. |
| **JWT/opaque token validation** | Verifies credentials issued by a trusted source for the right API. | CORS, CSRF, resource-level authorization. |
| **HTTP/domain authorization** | Decides whether user/client has rights to endpoints and resources. | CORS or TLS. |

In a **BFF application using session cookies**, CORS changes can impact web browsers, yet **never disable CSRF** just to let preflights pass. In a **stateless Bearer Resource Server**, cookies are not used as credentials so the CSRF policy can differ. Identify the exact credential architecture of each path.

## 20. Common misconceptions and mistakes

| Misconception | Why it is wrong | Proper approach |
| --- | --- | --- |
| "If the frontend has a valid JWT, OPTIONS must send the JWT too." | Browser preflights typically carry no Bearer credential. | Handle CORS before authentication. |
| "permitAll OPTIONS is enough for CORS." | Does not generate CORS headers; auth filter may run earlier. | `http.cors()` + properly ordered CORS source/gateway. |
| "CORS 200 means the API request returns 200 too." | Preflight and actual request are two distinct requests. | JWT/scope checks still apply to GET/POST/PATCH. |
| "CORS blocks curl/Postman." | CORS is enforced by browsers. | Resource Server still must check tokens and permissions. |
| "Access-Control-Allow-Headers: Authorization means the JWT is valid." | Only allows the browser to send the header name. | `JwtDecoder` or introspection validates the token. |
| "CORS returning 403 always means the user lacks a scope." | CORS 403 can come from Origin/method/header rejection. | Distinguish preflight from actual requests. |
| "If JWT returns 401, turn off Security to stop CORS errors." | The token may genuinely be invalid. | Ensure CORS headers on 401; fix authentication separately. |
| "Whatever Origin arrives in the header should be reflected back." | The header comes from the caller, not a trusted allowlist. | Match Origin against an allowlist before returning ACAO. |
| "Wildcard origin is safe with cookies." | Credentialed CORS needs explicit origins and CSRF protection. | Configure explicit origins, cookies, and CSRF separately. |
| "CORS replaces CSRF." | Simple requests can cause side effects even without reading responses. | Use CSRF protection whenever browsers auto-send session credentials. |
| "Routes outside `/api/**` also get CORS if a bean exists." | Path registrations or chains may not cover them. | Design CORS policies per endpoint group. |
| "MockMvc jwt() tests both preflight and token signatures." | Helper creates a mock Authentication, bypassing `JwtDecoder`. | Test CORS + real-signed `JwtDecoder` separately. |
| "If curl GET succeeds, browser GET will surely succeed." | curl neither sends nor checks preflights. | Simulate OPTIONS and run real browser tests. |
| "Opening CORS on the backend fixes a gateway 401." | The gateway rejected the request before the backend. | Fix CORS/auth ordering at the gateway. |
| "Preflight cache keeps JWTs from expiring." | CORS caching and token lifetimes are completely separate. | Actual requests always validate tokens per security design. |

## 21. Safe implementation checklist

1. **Map all origins:** frontend, API gateway, Resource Server, and Authorization Server. Note scheme/host/port for each origin.
2. **Trace credential flows:** does the API accept Bearer headers or does web use cookies/sessions? Is there a BFF? Never apply one CSRF/CORS policy everywhere when credentials differ.
3. **Build a frontend origin allowlist:** allow only domains actually hosting the app; separate dev/staging/prod.
4. **List methods and headers:** which GET/POST/PATCH/DELETE calls does the frontend make; are Authorization and JSON Content-Type needed?
5. **Run CORS before authentication:** use `http.cors()` with `CorsConfigurationSource` or equivalent gateway setup so preflights are not forced to carry Bearer tokens.
6. **Keep actual requests protected:** JWT/opaque validation, audience, issuer, expiration, scope/authority, and domain authorization.
7. **Verify multiple chains and path rewrites:** OPTIONS and GET/POST for the same API must hit the right CORS policy; include a fallback security chain for other URLs.
8. **Verify 401/403 actual responses:** approved origins must receive appropriate CORS headers even on invalid tokens or missing scopes; never fix via `permitAll()`.
9. **Do not enable credentials needlessly:** with cookies/sessions, configure `allowCredentials`, `SameSite`, `Secure`, and CSRF deliberately; never combine wildcard origins with credentialed responses.
10. **Write negative tests:** unknown origins, disallowed methods, unapproved custom headers, tokenless OPTIONS, tokenless GET, invalid tokens, insufficient scopes, and gateway errors.
11. **Inspect browser DevTools and reverse proxies:** confirm preflight succeeds before the actual request with no login-page redirects or duplicate CORS headers.
12. **Monitor operations:** distinguish `cors_preflight_denied`, `invalid_token`, `insufficient_scope`, gateway timeouts, and auth provider outages; never log Bearer tokens.

**Takeaway:** **A CORS preflight is the browser's permission check before the actual request**, and it normally **contains no Bearer token**. In a Spring Security Resource Server, **CORS must be handled before authentication enforcement**, via a properly designed CORS filter/configuration source or gateway. **Only preflights pass under the CORS policy; actual GET/POST/PATCH/DELETE requests must still authenticate tokens and check permissions.** CORS does not replace JWT validation, CSRF, or data authorization.

## References

- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — Multiple HttpSecurity instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html).
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- [MDN — Preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request).
- [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
