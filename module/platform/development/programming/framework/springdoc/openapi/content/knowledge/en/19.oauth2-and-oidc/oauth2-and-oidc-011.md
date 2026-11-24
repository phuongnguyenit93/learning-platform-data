# CORS, Redirect URI, and Why Login Succeeds While API Calls Fail

A web application can successfully log a user in via OAuth2 or OpenID Connect, return to the frontend page normally, yet fail on the subsequent request to the API. This situation often leads development teams to think their OAuth2 configuration is wrong. In reality, the login flow and the API call flow consist of multiple distinct requests governed by different mechanisms: **redirect URI**, **CORS**, token management, Resource Server authentication, and authorization.

The key is clarifying which request succeeded and which request failed. A redirect from the Identity Provider back to the application does not prove the browser exchanged the authorization code for a token; having a token does not prove that token is intended for the API being called; and an API receiving a token can still reject it due to wrong audience or missing scopes.

This article traces the entire path from the browser to the Identity Provider and Resource Server, explains the roles of redirect URI and CORS, configures CORS in Spring Security, and provides an investigation workflow using the Network tab, curl, and MockMvc.

## 1. Distinguishing redirect URI from CORS

These two concepts often appear together yet solve two different problems.

**Redirect URI** is the address where the Authorization Server redirects the browser after the user completes authentication and consent. This URI must match the URI registered for the OAuth2 client according to the provider's rules.

**CORS (Cross-Origin Resource Sharing)** is the mechanism the browser uses to decide whether JavaScript from one origin is permitted to read a response from another origin. The server returns CORS HTTP response headers to allow or deny sharing the response.

| Component | Question Resolved | Example |
|---|---|---|
| Redirect URI | After login, where does the browser return? | **https://app.example.com/login/oauth2/code/my-client** |
| CORS | Is JavaScript from the frontend origin allowed to read the API response? | Allow **https://app.example.com** to call **https://api.example.com** |
| Authentication | Is the token or session valid? | JWT signature, issuer, expiration, or session |
| Authorization | Does the authenticated identity have permission to call the operation? | Scope **orders.read** or role **ADMIN** |

A correct redirect URI does not configure CORS automatically. Valid CORS also cannot fix an incorrect redirect URI. Both configurations must be verified independently.

## 2. What is an origin and when does the browser apply CORS?

An origin is defined by the tuple:

- Scheme, such as **https**.
- Host, such as **app.example.com**.
- Port, such as **443** or **8080**.

Two URLs share the same origin when all three components match. Examples:

| Frontend | API | Cross-origin? |
|---|---|---|
| https://app.example.com | https://app.example.com/api | No |
| https://app.example.com | https://api.example.com | Yes, different host |
| http://localhost:3000 | http://localhost:8080 | Yes, different port |
| https://app.example.com | http://api.example.com | Yes, different scheme |

When JavaScript uses fetch or XMLHttpRequest to call another origin, the browser enforces CORS. If the server does not return appropriate headers, the browser blocks JavaScript from reading the response. The request may have reached the server and the server may even have finished processing it, yet the frontend still reports a CORS error because sharing the response is disallowed.

CORS is a browser policy. Tools like curl, Postman, or backend-to-backend calls do not enforce CORS policies the way browsers do. Therefore, curl succeeding does not prove the browser will allow JavaScript to read the response.

## 3. Requests in a browser OAuth2/OIDC flow

With Authorization Code Flow and PKCE, the flow typically involves these steps:

~~~mermaid
sequenceDiagram
    participant B as Browser / Frontend
    participant I as Identity Provider
    participant A as Application / BFF
    participant R as Resource Server API

    B->>I: Navigate to authorization endpoint
    I->>B: Login and consent
    I->>A: Redirect to redirect_uri with authorization code
    A->>I: Exchange code for token (server-to-server if BFF)
    I->>A: Access token / ID token
    A->>B: Create session or return login result
    B->>R: Call API with access token or session cookie
    R->>B: API response and CORS headers
~~~

In a pure SPA, the frontend itself may exchange the authorization code for a token using PKCE. In that case, the browser sends a request to the Identity Provider's token endpoint; the token endpoint must allow the frontend origin under the provider's CORS policy.

In the BFF (Backend for Frontend) model, the application backend receives the callback, exchanges the code for a token server-side, and keeps the token on the server. The browser typically receives only a BFF session cookie. Server-to-server calls from the backend to the token endpoint or APIs are not governed by browser CORS.

The authorization redirect is normally a browser-level page navigation, not a fetch/XHR call made by JavaScript to read cross-origin data. Thus, CORS is usually not why navigating to the login page fails; check redirect URI and callback first. CORS can surface when the SPA calls the token endpoint or calls the API via fetch/XHR.

Steps to distinguish:

1. Top-level navigation to the authorization endpoint.
2. Identity Provider redirect back to the redirect URI.
3. Exchanging the authorization code for tokens.
4. Frontend or BFF calling the Resource Server API.
5. Resource Server verifying the token and enforcing permissions.

Login succeeding at step 2 does not guarantee step 3 or step 4 succeeded.

## 4. Redirect URI must match exactly

With Spring Security OAuth2 Client, the default redirect URI usually looks like:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Client configuration example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          my-client:
            provider: my-provider
            client-id: example-client
            client-secret: SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          my-provider:
            issuer-uri: https://id.example.com
~~~

Register the corresponding redirect URI at the Identity Provider, for example:

~~~text
https://app.example.com/login/oauth2/code/my-client
~~~

The value must match the URI the application actually sends in the authorization request. Providers typically compare scheme, host, port, path, and potentially trailing slash. Do not rely on two URLs looking similar.

### Common redirect URI errors

- Registered **http** while the real environment uses **https**.
- Wrong host or port after deployment.
- Missing context path or reverse proxy prefix.
- Wrong registrationId in the callback path.
- One side has a trailing slash while the other does not.
- Application generates an internal redirect URI like **http://localhost:8080** while users access it over a public HTTPS domain.

If the Identity Provider returns a redirect_uri_mismatch error, compare the actual redirect_uri value in the authorization request against the list of registered URIs. Do not edit CORS to fix a mismatch error.

## 5. Reverse proxies can break the redirect URI

Applications often run behind Nginx, ingress, or a load balancer. The browser connects over HTTPS, yet the proxy forwards to Spring Boot over internal HTTP. If the application does not receive proper forwarded headers, Spring may build base URLs from the internal connection and send an incorrect redirect URI.

Example:

~~~text
Browser -> https://app.example.com
Proxy   -> http://spring-app:8080
~~~

If the application generates a callback as **http://spring-app:8080/login/oauth2/code/my-client**, that URI will not match the registered public URI.

Spring Boot can be configured to process forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The proxy needs to forward external scheme, host, and port details, typically via **Forwarded** or **X-Forwarded-*** headers. Only trust forwarded headers from trusted reverse proxies; do not let external clients spoof them.

After configuring, inspect the redirect_uri sent in the authorization request. Do not just check property values because proxies and context paths can alter the final URL.

## 6. CORS preflight: why doesn't the API see GET/POST requests?

Before certain cross-origin requests, the browser sends a check request called a **preflight** using HTTP OPTIONS. The preflight asks the server whether the upcoming origin, method, and request headers are allowed.

For example, the frontend sends:

~~~http
GET /api/orders
Origin: https://app.example.com
Authorization: Bearer <access-token>
~~~

Because **Authorization** is not a CORS-safelisted request header, the browser usually sends a preflight:

~~~http
OPTIONS /api/orders
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

The server must respond with appropriate headers, for example:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Vary: Origin
~~~

Only after the preflight is accepted does the browser send the actual GET request. If OPTIONS receives 401/403 from Spring Security or lacks appropriate CORS headers, the GET request may never be sent.

A request using **Content-Type: application/json** also usually triggers a preflight because application/json is not a CORS-safelisted content type. Custom headers such as **X-Request-Id** also need to be allowed.

## 7. Important CORS response headers

| Header | Role |
|---|---|
| **Access-Control-Allow-Origin** | Origin allowed to read the response |
| **Access-Control-Allow-Methods** | Allowed HTTP methods |
| **Access-Control-Allow-Headers** | Request headers the client is allowed to send |
| **Access-Control-Allow-Credentials** | Allows the browser to expose responses of requests with credentials |
| **Access-Control-Expose-Headers** | Allows JavaScript to read additional response headers |
| **Access-Control-Max-Age** | Duration the browser may cache preflight results |
| **Vary: Origin** | Tells caches that responses may vary by Origin |

If the frontend sends a bearer token in Authorization, this header must be in Access-Control-Allow-Headers. If the API returns headers such as Location, ETag, or X-Request-Id that JavaScript must read, declare them in Access-Control-Expose-Headers.

Do not confuse Access-Control-Allow-Headers with Access-Control-Expose-Headers: one permits clients to send request headers, while the other permits JavaScript to read response headers.

### Do not use wildcards with credentials

When requests use cookies or browser credentials, the server must return a specific origin, for example:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

You cannot use Access-Control-Allow-Origin with a wildcard (*) together with Access-Control-Allow-Credentials: true. The browser will reject sharing the response per CORS rules.

For bearer tokens explicitly set by the frontend in the Authorization header without cookies/session credentials, you can configure CORS without credentials while still allowing the Authorization header. Enable credentials only when the application genuinely needs to send cookies or browser-managed credentials.

## 8. Configuring CORS in Spring Security

With Spring Security, CORS should be processed before authentication. Preflight OPTIONS requests normally carry no access token; if the authentication filter blocks OPTIONS before CORS runs, the browser gets 401 or 403 and never sends the actual request.

Centralized CORS configuration example for an API:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(
            List.of("https://app.example.com")
        );
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
        );
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id")
        );
        config.setExposedHeaders(
            List.of("Location", "X-Request-Id")
        );
        config.setAllowCredentials(false);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

In this example, the application only allows the frontend at origin **https://app.example.com** to call APIs under **/api/**. Credentials are disabled because the example uses bearer tokens explicitly attached by the frontend to the Authorization header rather than cross-origin session cookies.

Wire this configuration into Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                Customizer.withDefaults()
            ))
            .build();
    }
}
~~~

When a CorsConfigurationSource bean exists, Spring Security can use it for CORS configuration. Call **.cors(Customizer.withDefaults())** in SecurityFilterChain to integrate CORS into the security filter chain. Avoid creating a second CORS configuration with conflicting origins or headers unintentionally.

## 9. Allowing cookie/session credentials

If the frontend uses cross-origin session cookies, configuration must allow credentials and specify exact origins:

~~~java
config.setAllowedOrigins(
    List.of("https://app.example.com")
);
config.setAllowCredentials(true);
~~~

The frontend needs to send requests with credentials:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Cookies must also match Domain, Path, Secure, and SameSite attributes. For cross-site cookies, browsers typically require **SameSite=None; Secure**; browser third-party cookie blocking policies may still interfere. CORS does not make cookies get sent if cookie attributes or browser policies disallow them.

If only using bearer headers, do not enable allowCredentials by default. Enable credentials only when cookies or browser credentials genuinely need to be sent cross-origin.

## 10. Configuring CORS with Spring MVC

If the application does not use Spring Security, or wants to declare CORS at the MVC layer, you can use WebMvcConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
            )
            .allowedHeaders(
                "Authorization", "Content-Type", "X-Request-Id"
            )
            .exposedHeaders("Location", "X-Request-Id")
            .allowCredentials(false)
            .maxAge(3600);
    }
}
~~~

When Spring Security is present, CORS must be integrated in the right order within the security filter chain. Use CorsConfigurationSource as in the earlier example or a CORS config recognized by Spring Security. Avoid having MVC and Security emit conflicting CORS headers.

**@CrossOrigin** fits controller-level or method-level configuration, yet when many controllers share a policy, centralized configuration is easier to audit. Regardless of approach, verify actual preflight behavior and ensure OPTIONS is handled before authentication.

## 11. Why does login succeed yet the API still returns 401?

HTTP 401 usually indicates the request did not authenticate successfully. After login, check these causes:

### Frontend does not yet have an access token

Login via redirect may only create a backend session. If the frontend calls the API directly with a bearer token without having one, the request cannot be authenticated.

In a BFF architecture, the browser typically calls the BFF with a session cookie; the BFF holds the access token and calls APIs server-side. Do not expect the frontend to read the access token if the architecture intentionally keeps tokens on the backend.

### Using an ID token instead of an access token

An OIDC ID token proves user authentication info to the client. An access token is issued to access a resource server. Do not send an ID token to an API unless the API is explicitly designed to accept that token type.

### Access token intended for a different API

A token may be valid for the Identity Provider yet not intended for the Resource Server being called. Check audience, issuer, expiration, and claims required by the API. A JWT with a valid signature can still be rejected by the API if the audience does not match.

### Token not sent in the right header

For HTTP bearer, requests should look like:

~~~http
Authorization: Bearer <access-token>
~~~

Inspect the Network tab to confirm the actual header is sent. Avoid sending duplicate Bearer prefixes or placing tokens in query strings.

### API rejects the issuer or algorithm

The Resource Server may be configured with an issuer-uri or jwk-set-uri that does not match the token. Check decoder configuration, key rotation, issuer, and custom validators.

## 12. Why does login succeed yet the API returns 403?

HTTP 403 usually indicates the request was authenticated, yet the identity lacks sufficient permission, though exact application policies can vary.

Common causes:

- Access token does not contain the required scope.
- Scope claim maps to a different authority than the hasAuthority or hasRole expression.
- API requires a role while the token only has scopes.
- User is logged in, yet not granted permission for the specific resource.
- CSRF protection rejects state-changing requests in cookie/session-based applications.

With Spring Security Resource Server, scopes typically map to authorities prefixed with **SCOPE_**. For example, scope orders.read can be checked with:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

If the application uses roles, configure appropriate claim mapping and distinguish hasRole("ADMIN") from hasAuthority("ROLE_ADMIN").

## 13. CORS does not replace CSRF

CORS controls whether JavaScript from another origin can read responses. CSRF protects the server against forged requests sent by the browser with automatically attached credentials, usually session cookies.

If an API uses bearer tokens explicitly attached by the frontend in the Authorization header without relying on automatic cookies, CSRF risk differs from session-cookie apps. If authenticating via cookies, evaluate CSRF protection, SameSite cookies, and how CSRF tokens are sent.

Do not disable CSRF simply because you hit a CORS error. Likewise, do not add CORS headers trying to fix a 403 CSRF error. Identify which filter or mechanism generated the error response.

## 14. Swagger UI and CORS

Swagger UI is also a frontend running in the browser. If Swagger UI is on a different origin than the API, the Try it out button is subject to the same CORS policy as a frontend app.

Example:

- Swagger UI: **https://docs.example.com**
- API: **https://api.example.com**

The API must allow the docs page's origin if users want to send requests from Swagger UI. The Security Scheme in OpenAPI tells Swagger UI how to add the Authorization header, yet does not configure CORS on the server.

Also check:

- servers in OpenAPI point to the exact API host and base path.
- CORS allows Swagger UI's origin.
- CORS allows Authorization and Content-Type headers.
- Spring Security permits preflight requests.
- Tokens used in Authorize have matching audience, issuer, and scopes.

If docs load but Try it out fails, inspect the API request in the Network tab; loading OpenAPI JSON and invoking an operation are two separate requests.

## 15. Step-by-step investigation in DevTools

Open browser Developer Tools, select the Network tab, enable Preserve log, then perform login and call the API. Locate requests in chronological order:

1. Identity Provider's authorization endpoint.
2. Callback to the redirect URI.
3. Token endpoint if the SPA exchanges the code directly.
4. OPTIONS preflight request to the API.
5. Actual API request such as GET or POST.

For each request, inspect:

| Request | What to Check |
|---|---|
| Authorization redirect | redirect_uri, client_id, response_type, scope, state, code_challenge |
| Callback | URL, status, code/error parameter, cookies, and state |
| Token exchange | Status, CORS response headers, grant_type, invalid_grant or invalid_client errors |
| OPTIONS preflight | Origin, Access-Control-Request-Method, Access-Control-Request-Headers, and response CORS headers |
| API request | Authorization header or cookie, status, response body, and CORS headers |

Never share real authorization codes, access tokens, refresh tokens, ID tokens, session cookies, or state/nonce values in public logs or screenshots.

### Reading error signals

- **Redirect mismatch**: check redirect_uri and registration at the Identity Provider.
- **OPTIONS 401/403**: check the CORS filter and Spring Security ordering.
- **OPTIONS 2xx but missing Allow-Origin**: origin mismatch or CORS mapping does not apply.
- **OPTIONS allowed but GET 401**: check access token, session, issuer, audience, and expiration.
- **GET 403**: check scope, authority, role, and CSRF.
- **GET 2xx but browser still reports CORS**: the actual request's response lacks CORS headers even though preflight succeeded.
- **API returns 2xx but JavaScript cannot read response header**: check Access-Control-Expose-Headers.

## 16. Using curl to inspect preflight

You can simulate OPTIONS to see which headers the server returns:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

The output should include the allowed origin, GET method, and requested headers. If using cookie credentials, also check:

~~~http
Access-Control-Allow-Credentials: true
Access-Control-Allow-Origin: https://app.example.com
~~~

curl only shows what headers the server returned. curl does not execute the browser's CORS algorithm and does not prove JavaScript will be permitted to read the response.

You can check the actual request:

~~~bash
curl -i "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Authorization: Bearer invalid-token"
~~~

In test environments, replace the dummy token with a token legitimately issued for the API. Do not put real tokens into shared commands or shell history.

## 17. Testing CORS preflight with MockMvc

Integration tests help catch lost CORS configuration after Spring Security changes:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsConfigurationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsPreflightFromFrontend() throws Exception {
        mockMvc.perform(options("/api/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "https://app.example.com"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"
                ))
            .andExpect(status().is2xxSuccessful())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("GET")
            ));
    }
}
~~~

This test confirms preflight is answered and the expected origin/method are allowed. You can add assertions checking that Access-Control-Allow-Headers includes Authorization and Content-Type.

Include a test from a disallowed origin to confirm the server does not grant Allow-Origin for that origin. Also test an actual GET request to confirm the real response carries CORS headers; testing only OPTIONS is insufficient.

If endpoints are protected, tests should verify separately:

- OPTIONS preflight is processed without requiring an access token.
- Actual GET requires a valid token.
- Token lacking permissions receives 403 per policy.
- Error responses 401/403 still carry appropriate CORS headers so the frontend can read the error.

## 18. CORS and redirect URI in deployment environments

Configuration that works on localhost can break when moved to staging or production because public origins and hosts change.

| Environment | Frontend origin | API origin | Redirect URI |
|---|---|---|---|
| Local | http://localhost:3000 | http://localhost:8080 | http://localhost:8080/login/oauth2/code/my-client or registered SPA callback |
| Staging | https://app.staging.example.com | https://api.staging.example.com | https://app.staging.example.com/login/oauth2/code/my-client |
| Production | https://app.example.com | https://api.example.com | https://app.example.com/login/oauth2/code/my-client |

Separate origin lists and redirect URIs per environment. Do not allow wildcards for deployment convenience if the application uses cookie credentials or needs to restrict which websites may call the API.

When supporting multiple frontend domains, list each allowed origin explicitly or use controlled allowed origin patterns. If allowing credentials, ensure responses return a specific origin, never a wildcard.

## 19. Common errors and fixes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Login reports success yet callback fails | Redirect URI mismatch or callback state/cookie lost | Compare sent redirect_uri with registered URI; check cookie/state |
| Callback succeeds yet frontend has no token | App uses BFF/session or token exchange incomplete | Determine SPA vs BFF architecture and inspect token exchange |
| Token endpoint reports CORS | SPA exchanges code directly yet IdP disallows frontend origin | Configure origin at IdP or use an appropriate BFF |
| OPTIONS returns 401/403 | Spring Security blocks preflight before CORS | Enable http.cors and ensure CORS runs before authentication |
| OPTIONS succeeds yet GET gets CORS | Actual request's response lacks CORS headers | Check CORS mappings for path/method and exception responses |
| Authorization not allowed | Missing Authorization in allowed headers | Add header to allowedHeaders |
| JSON request fails preflight | Content-Type or method not permitted | Allow application/json, required methods, and headers |
| Cookie is not sent | credentials mode, SameSite, Secure, Domain, or third-party cookie policy | Check request credentials and cookie attributes |
| Wildcard origin fails with cookies | credentials disallow Access-Control-Allow-Origin: * | Return specific origin and enable allowCredentials when needed |
| API returns 401 despite login succeeding | Missing access token, ID token used, wrong audience/issuer, or expired token | Check Authorization header and access token claims |
| API returns 403 | Missing scope/role or CSRF rejected | Check authority mapping and CSRF |
| Wrong Redirect URI behind proxy | App does not detect external scheme/host | Configure forwarded headers and verify actual redirect URI |
| Swagger UI loads docs yet Try it out fails | API origin does not allow docs page origin | Add Swagger UI origin to CORS if permitted |
| curl succeeds yet browser fails | curl does not enforce CORS | Check preflight and response headers in Network tab |

## 20. Checklist before deploying an OAuth2/OIDC frontend to production

- [ ] Determined whether the frontend uses a direct SPA or BFF model.
- [ ] Actual Redirect URI matches the registered URI at the Identity Provider exactly.
- [ ] Reverse proxy forwards accurate scheme, host, port, and context path.
- [ ] Authorization Code Flow uses PKCE where appropriate for public clients.
- [ ] Token endpoint allows frontend origin if the browser exchanges codes directly.
- [ ] API CORS allowlist contains only necessary origins.
- [ ] CORS permits actual methods and request headers, especially Authorization and Content-Type.
- [ ] OPTIONS preflight does not require a bearer token.
- [ ] Both success responses and error responses carry appropriate CORS headers.
- [ ] If using cross-origin session cookies, credentials, SameSite, Secure, and Domain are properly configured.
- [ ] Access token targets the right Resource Server; ID token is not used instead of access token.
- [ ] Issuer, audience, expiration, scopes, and authority mappings have been checked.
- [ ] CSRF is evaluated separately if authentication relies on cookies.
- [ ] Swagger UI origin is allowed if Try it out is needed from the docs domain.
- [ ] Both preflight tests and actual API request tests exist.

## Conclusion

Redirect URI determines where the Identity Provider returns the browser after login; CORS determines which origins' JavaScript may read cross-origin responses. Both mechanisms are independent and do not replace authentication or authorization. When login succeeds yet API calls fail, trace the authorization redirect, callback, token exchange, OPTIONS preflight, and actual API request. In Spring Security, configure CORS so preflight runs before authentication, permit exact origins/methods/headers, and enable credentials only when cookies are needed. Then verify access token, issuer, audience, scopes, CSRF, and forwarded headers. The Network tab shows which step failed; curl reveals response headers; MockMvc keeps CORS configuration stable across changes.
