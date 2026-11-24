# CORS Only Affects Browser Access, Not Server Access Control

CORS (Cross-Origin Resource Sharing) is a mechanism for a server to declare which origins are allowed to read responses from cross-origin browser requests. When Swagger UI is served from one origin and the API or OpenAPI document is on another origin, the browser enforces the Same-Origin Policy and inspects the CORS headers returned by the server.

CORS does not authenticate callers, does not check roles or scopes, and does not protect endpoints from <code>curl</code>, Postman, or another backend service. It is a policy enforced by browsers to control whether JavaScript may send certain cross-origin requests and read responses. Resource access must still be enforced on the server using authentication, authorization, and appropriate protection layers.

## 1. What Is an Origin?

An origin is defined by three components:

- Scheme, such as <code>http</code> or <code>https</code>.
- Host, such as <code>docs.example.com</code>.
- Port, such as <code>443</code> or <code>8080</code>.

If even one of the three components differs, the origins are different:

| Swagger UI Page | API | Result |
|---|---|---|
| <code>https://docs.example.com</code> | <code>https://docs.example.com/api/orders</code> | Same origin |
| <code>https://docs.example.com</code> | <code>https://api.example.com</code> | Different host, cross-origin |
| <code>https://docs.example.com</code> | <code>http://docs.example.com</code> | Different scheme, cross-origin |
| <code>http://localhost:3000</code> | <code>http://localhost:8080</code> | Different port, cross-origin |

Paths such as <code>/swagger-ui</code> and <code>/api</code> do not participate in origin comparison. Two URLs can have different paths yet still share the same origin if their scheme, host, and port match.

For example, if Swagger UI opens at <code>https://docs.example.com/swagger-ui/index.html</code> and calls <code>https://api.example.com/orders</code>, the browser treats this as a cross-origin request. The API must return appropriate CORS headers so JavaScript on the documentation page is allowed to read the response.

## 2. What Does CORS Control?

The Same-Origin Policy restricts how a web page reads resources from another origin. CORS lets a server selectively relax those restrictions using response headers.

For a cross-origin request, the browser checks the calling page's origin against CORS rules from the target server. Depending on the request type, the browser may:

- Send the request directly and allow JavaScript to read the response only if CORS checks pass.
- Send an <code>OPTIONS</code> preflight request first to ask the server whether the intended method and headers are permitted.
- Block JavaScript from reading the response if CORS headers are missing or incorrect.
- Skip sending the actual request if preflight is not accepted.

Crucially, CORS is not an API authorization layer. For certain simple requests, the browser may still send the request to the server even while blocking JavaScript from reading the response. Therefore, the server must still verify permissions and handle requests securely.

## 3. Distinguishing CORS, Authentication, and Authorization

Three mechanisms answer three different questions:

| Mechanism | Question | Example |
|---|---|---|
| CORS | Which origins may run JavaScript to send/read cross-origin requests under browser policy? | Allow <code>https://docs.example.com</code> to read API responses |
| Authentication | Who is the caller? Are their credentials valid? | Verify a JWT Bearer token |
| Authorization | Which actions on which resources is the caller permitted to perform? | Only users with <code>orders:read</code> can read orders |

A request can pass CORS yet still be rejected by authentication or authorization:

- Browser sends a request from an allowed origin without a token: server returns <code>401 Unauthorized</code>.
- Token is valid yet lacks permissions: server returns <code>403 Forbidden</code>.
- Token is valid and has sufficient permissions: server may return <code>200 OK</code>.

Conversely, the server may process a request and return a status, yet the browser refuses to let JavaScript read the response because CORS headers are unsuitable. The UI may report only a CORS error even though the server recorded the request. Inspect the Network tab and backend logs to determine whether the request reached the server.

## 4. CORS Does Not Protect APIs from Non-Browser Clients

Tools such as <code>curl</code>, Postman, native mobile apps, and backend services are not subject to the browser Same-Origin Policy. They can send requests directly to the API if network connectivity permits.

For example, the following command can still call the API even if the origin is not on the CORS list:

~~~bash
curl -i \
  -H "Origin: https://untrusted.example" \
  https://api.example.com/api/orders
~~~

<code>curl</code> will display whatever response the server returns. It does not reject the response simply because <code>Access-Control-Allow-Origin</code> does not match. The <code>Origin</code> header in that command can also be set arbitrarily by the client, so the server must never treat it as an authentication credential.

Consequently, never use CORS as a data-protection measure. Sensitive endpoints require server-side authentication and authorization; to restrict access at the network layer, use firewalls, gateways, private networks, or appropriate access controls.

## 5. Preflight Requests and Actual Requests

Browsers send a preflight request when a cross-origin request is not a simple request. Common examples include JSON requests with an <code>Authorization</code> header, or requests using <code>PUT</code>, <code>PATCH</code>, or <code>DELETE</code>.

Preflight is an <code>OPTIONS</code> request carrying headers such as:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://docs.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
~~~

The server must return headers indicating which origin, methods, and headers are permitted. For example:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://docs.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

If preflight succeeds, the browser sends the actual request using the declared method and headers. The actual response must also carry appropriate CORS headers for JavaScript to read it.

Not every cross-origin request triggers a preflight. A simple request can be sent directly. Checking preflight alone is therefore not enough; inspect the actual request's response as well.

## 6. Key CORS Headers

| Header | Sent By | Meaning |
|---|---|---|
| <code>Origin</code> | Browser | Origin of the page initiating the request |
| <code>Access-Control-Request-Method</code> | Browser in preflight | Method the actual request intends to use |
| <code>Access-Control-Request-Headers</code> | Browser in preflight | List of headers the actual request intends to send |
| <code>Access-Control-Allow-Origin</code> | Server | Origin permitted to access the response |
| <code>Access-Control-Allow-Methods</code> | Server | Methods permitted for cross-origin requests |
| <code>Access-Control-Allow-Headers</code> | Server | Request headers permitted |
| <code>Access-Control-Allow-Credentials</code> | Server | Allows the browser to include credentials in CORS requests |
| <code>Access-Control-Expose-Headers</code> | Server | Additional response headers JavaScript is allowed to read |
| <code>Access-Control-Max-Age</code> | Server | Duration the browser may cache preflight results |
| <code>Vary: Origin</code> | Server | Signals caches that the response may vary by Origin |

<code>Access-Control-Allow-Origin</code> is typically a specific origin or <code>*</code> when credentials are not used. When the server selects an origin dynamically from an allowlist, <code>Vary: Origin</code> prevents caches from serving one origin's CORS response to another origin.

<code>Access-Control-Expose-Headers</code> is required if JavaScript needs to read headers outside the default CORS-safelisted response headers. For example, if the UI or frontend needs to read <code>X-Request-Id</code> or <code>Location</code>, the server can expose those headers.

## 7. Configuring CORS for Spring Security

When an application uses Spring Security, configure CORS in the filter chain so CORS runs before authentication steps. Preflight requests typically do not carry cookies or Bearer tokens like actual requests; if an authentication filter rejects <code>OPTIONS</code> before CORS processes it, the browser reports an error.

Spring Boot 3 and Spring Security 6 example:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://docs.example.com"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id")
        );
        cors.setExposedHeaders(List.of("Location", "X-Request-Id"));
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

In this example:

- Only the origin <code>https://docs.example.com</code> is permitted to call the API cross-origin.
- Only the listed methods are allowed.
- Headers <code>Authorization</code>, <code>Content-Type</code>, and <code>X-Request-Id</code> are permitted in requests.
- JavaScript is allowed to read <code>Location</code> and <code>X-Request-Id</code> in responses.
- The configuration applies only to paths under <code>/api/**</code>.

This example illustrates Bearer tokens explicitly sent by JavaScript via the <code>Authorization</code> header. That header is allowed via <code>setAllowedHeaders</code>; by itself, it does not require <code>allowCredentials(true)</code>. Replace origins, methods, headers, and paths with your system's values.

Enable <code>setAllowCredentials(true)</code> only if the browser needs to send credentials in credentials mode, such as session cookies or browser-managed HTTP authentication. When enabled, never use <code>allowedOrigins("*")</code>; declare explicit origins or use a controlled allowlist. Never blindly reflect arbitrary <code>Origin</code> values received from requests.

If using a JWT resource server as in the filter chain example, the application needs the <code>spring-boot-starter-oauth2-resource-server</code> dependency and an appropriate issuer or JWT decoder configuration. CORS does not replace that configuration.

## 8. CORS via WebMvcConfigurer When Not Configured Through Spring Security

A Spring MVC application without Spring Security can declare CORS using <code>WebMvcConfigurer</code>:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Authorization", "Content-Type", "X-Request-Id")
            .exposedHeaders("Location", "X-Request-Id")
            .maxAge(3600);
    }
}
~~~

Choose one intentional place to configure CORS so policies do not overlap or conflict. When Spring Security is present, CORS configuration should integrate with the filter chain—such as via <code>CorsConfigurationSource</code> and <code>.cors(withDefaults())</code>—or ensure Spring Security picks up the MVC configuration properly.

Do not add a second custom CORS filter without understanding filter ordering and policy merging. Two layers both modifying CORS headers can produce duplicate <code>Access-Control-Allow-Origin</code> headers or unpredictable behavior.

## 9. CORS for Swagger UI and OpenAPI Documentation

There can be two separate cross-origin requests:

1. Swagger UI fetches the OpenAPI specification file from <code>/v3/api-docs</code> or a configured document URL.
2. Swagger UI sends test requests to API endpoints such as <code>/api/orders</code>.

If the UI and OpenAPI document live on two different origins, the documentation-serving endpoint also needs suitable CORS rules so the browser can load the spec. If the UI and API live on two different origins, the API needs suitable CORS rules for Try it out requests.

In the <code>CorsConfigurationSource</code> example above, the mapping applies only to <code>/api/**</code>. If JSON documentation is served cross-origin, also register policies for the corresponding docs paths—such as <code>/v3/api-docs</code>, <code>/v3/api-docs/**</code>, and <code>/v3/api-docs.yaml</code>. You can restrict the documentation group to <code>GET</code> and only the request headers actually needed.

Example:

- Swagger UI: <code>https://docs.example.com</code>
- OpenAPI JSON: <code>https://api.example.com/v3/api-docs</code>
- API: <code>https://api.example.com/api/**</code>

In this case, define policies for both <code>/v3/api-docs/**</code> and <code>/api/**</code>. They can share an origin allowlist while still applying minimal methods/headers to each path group.

If Swagger UI and the API are served on the same origin behind a reverse proxy, the browser does not need CORS for those requests. Whenever changing domains or splitting the documentation host, review the policies again.

## 10. CORS Does Not Replace Protecting Swagger UI and OpenAPI JSON

A Swagger UI page might block browsers from unfamiliar origins from reading documentation, yet the <code>/v3/api-docs</code> endpoint can still be called directly with <code>curl</code> or another client. CORS does not make documentation private.

If API documentation is strictly for employees or partners, protect independently:

- The Swagger UI page, typically including <code>/swagger-ui/**</code> and the <code>/swagger-ui.html</code> entry point or custom path.
- JSON documents <code>/v3/api-docs/**</code>.
- YAML documents <code>/v3/api-docs.yaml</code> or custom path.
- Grouped documentation endpoints if the application uses <code>GroupedOpenApi</code>.

Use Spring Security, reverse proxies, gateways, or your organization's identity mechanism to require login and proper permissions. CORS can be added to restrict browser origins, yet it is not the primary access control layer.

Similarly, protecting the Swagger UI page does not automatically protect API endpoints. Business APIs need separate authentication and authorization rules.

## 11. CORS, Cookies, and CSRF

CORS and CSRF intersect in some browser architectures, yet neither replaces the other.

- CORS controls whether the browser allows cross-origin JavaScript to read responses and, for preflighted requests, can prevent the actual request from being sent.
- CSRF is an attack that exploits the browser's automatic sending of credentials (typically session cookies) to make an authenticated user perform unintended actions.

Certain simple requests can be sent cross-origin without a preflight. Thus, relying on CORS alone to prevent CSRF is insufficient, especially for APIs using automatically attached cookies.

If the application authenticates with session cookies:

- Enable CSRF protection appropriate for the client type and how CSRF tokens are sent.
- Set cookie attributes <code>SameSite</code>, <code>Secure</code>, and <code>HttpOnly</code> according to architecture.
- Enable CORS credentials only for trusted origins.
- Verify <code>Access-Control-Allow-Credentials</code> and exact origins.

For example, a frontend that needs to send session cookies in a cross-origin request must explicitly enable credentials on the client:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

The server must then configure a specific origin and <code>allowCredentials(true)</code>. Browsers still enforce cookie policies such as <code>SameSite</code>; CORS cannot force a browser to send a cookie that cookie policy forbids.

If the application uses Bearer tokens explicitly added by JavaScript to the Authorization header, requests typically trigger a preflight. Nevertheless, the server must still validate tokens and check permissions; never treat the mere presence of an Authorization header as proof of validity.

## 12. How to Troubleshoot CORS Errors

When Swagger UI reports a CORS error, check in order:

1. Identify the exact origin of the Swagger UI page in the address bar.
2. Check the Request URL and origin of the API or OpenAPI endpoint in the Network tab.
3. If there is a preflight, inspect the <code>OPTIONS</code> request, status, and <code>Access-Control-Request-*</code> headers.
4. Check whether the preflight response carries matching <code>Access-Control-Allow-Origin</code>, <code>Access-Control-Allow-Methods</code>, and <code>Access-Control-Allow-Headers</code>.
5. Check whether the actual request's response carries <code>Access-Control-Allow-Origin</code> and any headers requiring exposure.
6. If using cookies/credentials, verify <code>Access-Control-Allow-Credentials</code> and that the origin is not a wildcard.
7. Check backend and gateway logs to confirm whether the request reached the server.
8. Once CORS passes, inspect HTTP status, tokens, and access permissions.

A preflight can fail because a gateway blocks <code>OPTIONS</code>, Spring Security processes the request before CORS, a method/header is not allowed, or the origin is not in the allowlist. Fix the server-side policy instead of disabling browser protections.

### 12.1. Using curl to Inspect CORS Headers

You can check which headers the server returns with:

~~~bash
curl -i \
  -H "Origin: https://docs.example.com" \
  https://api.example.com/api/orders
~~~

To simulate a preflight:

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://docs.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  https://api.example.com/api/orders
~~~

These commands inspect server response headers. They do not fully simulate browser CORS enforcement and do not prove JavaScript will be permitted to read the response. Always confirm in the browser Network/Console panels.

## 13. Common Pitfalls

**Assuming CORS is authentication.** CORS is strictly a browser policy. APIs must still validate tokens, sessions, or credentials on the server.

**Assuming CORS blocks curl and Postman.** Those tools do not enforce the Same-Origin Policy. Requests can still reach the API.

**Configuring CORS only for the API while forgetting <code>/v3/api-docs</code>.** Swagger UI may fail to load the spec if the spec lives on a different origin.

**Configuring only preflight while forgetting actual responses.** Browsers require matching CORS headers on the actual response for JavaScript to read it.

**Using a wildcard origin with credentials.** When allowing credentials, an explicit origin is required; never use <code>Access-Control-Allow-Origin: *</code>.

**Blocking OPTIONS with authentication before CORS runs.** Integrate CORS into Spring Security so preflights are processed in the proper order.

**Opening all origins as a quick fix.** Allow only trusted origins, needed methods, and needed headers.

**Using CORS instead of CSRF protection.** Simple requests can still be sent cross-origin; cookie authentication requires an appropriate CSRF policy.

**Confusing CORS errors with 401/403.** CORS is a browser-enforced policy error; 401/403 are HTTP responses related to authentication/authorization. Inspect Network and server logs to tell them apart.

## 14. Pre-Publication Review Checklist

- [ ] Identified origins of Swagger UI, OpenAPI JSON/YAML, and the API.
- [ ] Allowed only trusted documentation origins.
- [ ] Allowed only necessary methods and request headers.
- [ ] Configured CORS for documentation endpoints if the spec is on a different origin from the UI.
- [ ] Configured CORS for the API if Try it out makes cross-origin calls.
- [ ] <code>OPTIONS</code> preflight is processed before authentication filters as appropriate.
- [ ] Actual responses carry CORS headers so the browser can read them.
- [ ] <code>allowCredentials</code> is enabled only when needed and never combined with a wildcard origin.
- [ ] Bearer tokens in the <code>Authorization</code> header are explicitly allowed; do not enable credentials just for Bearer tokens.
- [ ] Authentication and authorization remain enforced on the server.
- [ ] Swagger UI, <code>/v3/api-docs</code>, and documentation endpoints are independently protected if meant to be private.
- [ ] CSRF is handled separately when using cookie/session authentication.
- [ ] Tested with the browser Network tab and confirmed actual response headers.

## References

- [MDN – Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): how browsers enforce CORS and preflights.
- [Fetch Standard – CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): the browser CORS algorithm.
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): configuring CORS in Spring MVC.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): integrating CORS with the Security filter chain.
- [Spring Boot – Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): Spring Boot application security configuration.
- [OWASP – Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): why CORS does not replace CSRF defenses.
- [springdoc-openapi](https://springdoc.org/): configuring OpenAPI and Swagger UI endpoints in Spring Boot.
