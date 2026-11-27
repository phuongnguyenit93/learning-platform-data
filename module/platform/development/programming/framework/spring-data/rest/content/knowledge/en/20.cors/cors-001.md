# Same-Origin, Cross-Origin, and the Browser Preflight Mechanism

When a frontend running on one origin calls a Spring Data REST API on another origin, the browser enforces the Same-Origin Policy (SOP) to restrict how JavaScript reads resources across origins. CORS (Cross-Origin Resource Sharing) is the HTTP mechanism that allows a server to declare which origins, methods, and request headers are permitted to access it. For certain requests, the browser sends an additional preliminary check request called a **preflight** using HTTP OPTIONS.

CORS is a policy enforced by the browser based on the server's response headers. The backend must be configured properly; the frontend cannot grant itself CORS permissions by adding an arbitrary request header.

## 1. Origin and the Same-Origin Policy

An origin is defined by three components:

- **Scheme:** the protocol, for example `http` or `https`.
- **Host:** the domain name or host address.
- **Port:** the connection port.

Two URLs share the same origin when all three components are identical. The path does not participate in the origin comparison.

For example:

| First URL | Second URL | Same origin? | Reason |
|---|---|---|---|
| `https://app.example.test/home` | `https://app.example.test/api` | Yes | Same scheme, host, and default port |
| `https://app.example.test` | `http://app.example.test` | No | Different scheme |
| `https://app.example.test` | `https://api.example.test` | No | Different host |
| `https://app.example.test` | `https://app.example.test:8443` | No | Different port |
| `http://localhost:3000` | `http://localhost:8080` | No | Different port |

The Same-Origin Policy restricts JavaScript from reading responses or accessing certain resources belonging to another origin. It is a foundational browser safeguard against one web page arbitrarily reading data from another site where the user is logged in.

CORS adds a controlled way for a server to allow specific origins to read responses. CORS does not merge two origins into one; the browser still recognizes the request as cross-origin and applies CORS rules.

It is also important to distinguish **origin** from **site**. Two subdomains may be considered the same site under certain cookie rules while still being two different origins. CORS compares the origin consisting of scheme, host, and port.

## 2. How Does CORS Work?

When JavaScript calls a cross-origin API using Fetch or XMLHttpRequest, the browser sends an `Origin` header to let the server know where the request originated.

For example, a frontend at `https://app.example.test` calls:

```javascript
fetch("https://api.example.test/people", {
  method: "GET"
});
```

The request may carry headers:

```http
GET /people HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
```

A server that permits that origin may return:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/hal+json
```

The browser checks `Access-Control-Allow-Origin`. If the value matches the page's origin, JavaScript is allowed to read the response according to the CORS policy. If the header is missing or does not match, the browser blocks JavaScript from reading the response and displays a CORS error in the console.

The server may still have received and processed the request before the browser blocked the response. Therefore, a CORS error does not mean the request definitely did not reach the server or did not cause side effects. This is especially important for data-modifying requests.

## 3. Simple Requests and Requests Requiring Preflight

Not every cross-origin request requires a preflight. The browser can send certain simple requests directly; other requests must check permissions first.

A request generally belongs to the **CORS-safelisted (simple)** group when it meets the main conditions:

- The method is GET, HEAD, or POST.
- Request headers consist only of safelisted headers and their values satisfy CORS rules.
- If `Content-Type` is present, the media type belongs to one of the safelisted types: `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`.
- There are no other factors that disqualify the request from the safelisted group.

Simple GET example:

```javascript
fetch("https://api.example.test/people", {
  method: "GET"
});
```

POST sending form data example:

```javascript
const form = new URLSearchParams();
form.set("name", "An");

fetch("https://api.example.test/people-form", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: form
});
```

Some requests that typically require preflight:

- Using the PUT, PATCH, or DELETE methods.
- Using non-safelisted headers, such as a custom header `X-Request-ID`.
- Sending an `Authorization` header.
- Sending JSON with `Content-Type: application/json`, since this media type is not in the safelisted Content-Type group.

Example PATCH request to Spring Data REST:

```javascript
fetch("https://api.example.test/people/42", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/merge-patch+json",
    "Accept": "application/hal+json"
  },
  body: JSON.stringify({
    firstName: "An"
  })
});
```

This request requires preflight because it uses PATCH and non-safelisted headers/media types. The browser sends OPTIONS before sending the actual PATCH.

A request being simple does not mean it is business-safe or does not require authentication. It only means the browser does not need a preflight under CORS conditions.

## 4. Preflight Request Using OPTIONS

A preflight is an OPTIONS request automatically sent by the browser before a non-safelisted cross-origin request. It asks the server whether the current origin is allowed to use the intended method and request headers.

For example, the browser intends to send a PATCH with Content-Type and Accept:

```http
OPTIONS /people/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, accept
```

Meaning:

- `Origin` is the origin of the frontend.
- `Access-Control-Request-Method` indicates the method of the actual request about to be sent.
- `Access-Control-Request-Headers` lists the request headers that the actual request wants to use.

If the policy allows it, the server may return:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Accept
Access-Control-Max-Age: 3600
Vary: Origin
```

Only after checking the preflight response does the browser proceed to send the actual PATCH request. If the preflight fails, the browser does not send the actual request in that flow.

Preflights typically do not carry the credentials of the actual request. However, for credentialed requests, both the preflight response and the actual response must still satisfy the CORS rules for credentialed requests, including `Access-Control-Allow-Credentials: true` and a specific origin.

The browser may cache the preflight result for the duration advertised by the server via `Access-Control-Max-Age`, within limits enforced by the browser. Therefore, changes to a CORS policy might not take effect immediately in a browser that has cached the preflight; when debugging, consider caching and retry under appropriate conditions.

## 5. Important CORS Response Headers

| Header | Role |
|---|---|
| `Access-Control-Allow-Origin` | The origin allowed to read the response; can be a specific origin or `*` when credentials are not used |
| `Access-Control-Allow-Methods` | The methods permitted in the CORS context |
| `Access-Control-Allow-Headers` | The request headers the browser is permitted to send |
| `Access-Control-Allow-Credentials` | Allows the browser to share the response of a credentialed request when the value is `true` |
| `Access-Control-Expose-Headers` | Allows JavaScript to read additional response headers outside the safelisted group |
| `Access-Control-Max-Age` | Duration for which the browser can cache the preflight result |
| `Vary: Origin` | Tells caches that the response may vary depending on the Origin request header |

Example of a server allowing only a specific frontend to call the API:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, Accept, X-Request-ID
Access-Control-Expose-Headers: ETag, Location
Vary: Origin
```

`Access-Control-Allow-Methods` is not the same as the HTTP `Allow` header. `Allow` describes the HTTP methods supported by the target resource; `Access-Control-Allow-Methods` is part of the CORS policy for the browser and the origin/request under consideration. A method present in Allow is not necessarily permitted by CORS.

Similarly, `Access-Control-Allow-Headers` governs the request headers the browser is allowed to send; `Access-Control-Expose-Headers` governs the response headers JavaScript is allowed to read.

## 6. Credentials: Cookies, Sessions, and Authorization

If the frontend needs to send cookies or automatic HTTP authentication, Fetch must enable credentials:

```javascript
fetch("https://api.example.test/people", {
  method: "GET",
  credentials: "include"
});
```

The server needs to return appropriate headers, for example:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

Important rules:

- The value of `Access-Control-Allow-Credentials` must be lowercase `true`.
- When credentials are allowed, `Access-Control-Allow-Origin: *` is not valid for sharing the response; the server must return a specific origin.
- If the server responds with an origin dynamically based on the request, `Vary: Origin` is needed so caches do not mistakenly reuse a response for another origin.
- Cookies are also subject to cookie attributes such as `SameSite`, `Secure`, domain, and path. Correct CORS alone does not guarantee the browser will send cookies.
- The `Authorization` header typically causes the request to require preflight and must be explicitly allowed in `Access-Control-Allow-Headers`.

Do not reflect any arbitrary Origin value without validation. If the server takes the Origin from the request and echoes it right back, every website could be allowed to read the response, defeating the purpose of the allowlist.

## 7. Configuring CORS in Spring MVC

CORS can be configured in Spring MVC using `WebMvcConfigurer`. Example:

```java
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
            .allowedOrigins("https://app.example.test")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH",
                "DELETE", "OPTIONS"
            )
            .allowedHeaders(
                "Authorization", "Content-Type",
                "Accept", "X-Request-ID"
            )
            .exposedHeaders("ETag", "Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
```

The domain, path, method, and header values are examples. In production, list only the frontend origins that actually need access. If there are multiple frontend environments, manage the allowlist via environment configuration rather than unnecessarily broadening a wildcard.

You can use the `@CrossOrigin` annotation on a controller or handler mapping for per-endpoint configuration. However, Spring Data REST automatically generates many endpoints from repositories; global configuration or CORS configuration suited for repository REST is usually easiest to manage. Verify that the configuration applies to collection, item, search, and association resources alike.

Avoid creating multiple conflicting CORS configurations across a proxy, Spring MVC, and Spring Security at the same time. The browser needs to receive one consistent set of response headers on the final response.

## 8. Configuring CORS When Using Spring Security

If the application uses Spring Security, CORS must be processed before security filters reject the preflight request. Preflights usually do not send the cookie/session of the actual request, so a rule requiring authentication for every OPTIONS request can cause preflights to fail if CORS has not been handled properly.

You can declare a `CorsConfigurationSource` and enable CORS in `SecurityFilterChain`:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.test")
    );
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH",
                "DELETE", "OPTIONS")
    );
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type",
                "Accept", "X-Request-ID")
    );
    config.setExposedHeaders(
        List.of("ETag", "Location")
    );
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );

    return http.build();
}
```

The illustrative configuration uses modern Spring Security. Specific imports and APIs depend on the version. You can configure CORS via MVC and let Spring Security use the MVC configuration if the application is set up appropriately, or provide a `CorsConfigurationSource` as shown above. Choose one clear configuration source and test across the entire filter chain.

Do not simply add a rule allowing all OPTIONS requests and consider CORS configured. The browser needs valid CORS response headers, not just a 200 or 204 status. Nor should you disable security altogether to resolve preflight errors.

## 9. CORS Is Not Authentication, Authorization, or CSRF Protection

CORS only determines whether the browser allows JavaScript from another origin to read the response. It does not authenticate users, check business permissions, or prevent every client from sending requests directly.

Distinguish between:

- **Authentication:** determines who the caller is, for example via session or bearer token.
- **Authorization:** determines whether the caller has permission to read, create, update, delete, or link a resource.
- **CORS:** determines whether the browser allows a script from another origin to access the response.
- **CSRF protection:** mitigates the risk of another website abusing credentials automatically sent by the browser to perform unintended actions.

A simple cross-origin request can be delivered to the server even if the browser subsequently blocks JavaScript from reading the response. Therefore, do not rely on CORS as the sole barrier against CSRF. With cookie/session authentication, you must still configure appropriate CSRF protection for state-changing requests. If using a bearer token in the Authorization header, design authentication and CSRF policies according to how the token is actually stored and sent.

CORS also does not apply in the same way to every HTTP client. cURL, backend services, or native applications do not have the browser Same-Origin Policy enforced on them. A request that works with cURL but fails in the browser usually points to an issue with the CORS policy or browser credentials, not necessarily a broken Spring Data REST endpoint.

## 10. Common CORS Errors

| Symptom | Possible cause | How to check |
|---|---|---|
| Missing `Access-Control-Allow-Origin` | Origin is not allowlisted or an error response bypassed the CORS handler | Check the request Origin and mapping configuration |
| Preflight returns 401/403 | Security filter rejects OPTIONS before CORS processes it | Enable CORS in SecurityFilterChain and check filter order |
| Preflight does not allow PATCH/DELETE | Method missing from `Access-Control-Allow-Methods` | Add the exact method to the allowlist |
| Preflight does not allow Content-Type/Authorization | Header missing from `Access-Control-Allow-Headers` | Declare the required request headers |
| Credentialed request blocked by browser | Using wildcard origin or missing `Access-Control-Allow-Credentials: true` | Return a specific origin and enable credentials intentionally |
| JavaScript cannot read ETag or Location | Header is not exposed | Add the header to `Access-Control-Expose-Headers` |
| cURL works but browser fails | cURL does not enforce CORS like a browser | Inspect the Network panel and CORS response headers |
| Only some endpoints fail | CORS mapping does not cover search/association/error paths or a proxy overwrites headers | Check the actual URL and final response |

A successful preflight does not guarantee the actual request will succeed. The actual request can still receive 401, 403, 404, 409, 415, or validation errors according to the API contract. Conversely, a business 400/500 response still needs appropriate CORS headers if the browser must be able to read the error body.

## 11. Debugging Workflow in the Browser

When encountering a CORS error with Spring Data REST, follow this order:

1. Open Developer Tools and select the Network tab.
2. Find the OPTIONS request that shares the same URL as the failing API request.
3. Inspect the request headers: `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
4. Inspect the status and response headers of OPTIONS: `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials` if using credentials.
5. If the preflight succeeded, check whether the actual request was sent.
6. If the actual request was sent, read the status and body of the response; this may be an authentication, authorization, validation, or persistence error independent of CORS.
7. Check whether the response passes through a proxy/gateway and whether CORS headers are stripped or duplicated.
8. When changing policies, account for preflight caching and retry after the cache expires or in an appropriate browser session.

You can simulate a preflight with cURL to see what headers the server returns:

```bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type,authorization" \
  https://api.example.test/people/42
```

cURL only displays the response; it does not enforce CORS policy on behalf of the browser. This result is useful for checking server configuration, while the final conclusion requires observing requests from a real browser.

## 12. CORS Configuration Checklist for Spring Data REST

1. Identify the exact scheme, host, and port of each frontend origin.
2. Distinguish origin from site; different subdomains or ports are still cross-origin.
3. Allowlist only the origins that truly need access.
4. Declare the exact methods, request headers, and exposed response headers.
5. If using cookies/sessions, configure credentials with specific origins; also check the cookie's SameSite and Secure attributes.
6. When using Spring Security, process CORS before authorization rejects the preflight.
7. Cover collection, item, search, and association endpoints of Spring Data REST.
8. Keep authentication, authorization, and CSRF protection independent of CORS.
9. Test simple requests, preflights, credentialed requests, and error responses.
10. Inspect the final response through any proxy/gateway and handle `Vary: Origin` when the origin is selected dynamically.

SOP restricts scripts from reading data across origins by default. CORS allows Spring Data REST to advertise a controlled allowlist so cross-origin frontends can access the API. Browsers use simple requests when safelist conditions are met; otherwise, they send an OPTIONS preflight to check the intended method and headers. Configuring CORS properly in Spring MVC/Spring Security while keeping authentication, authorization, and CSRF separate makes frontend/API integration clearer and more secure.
