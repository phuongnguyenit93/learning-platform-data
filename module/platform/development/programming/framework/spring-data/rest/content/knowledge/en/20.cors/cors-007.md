# Origins, Methods, Headers, Credentials, and Wildcard Restrictions in CORS

## Goal

Cross-Origin Resource Sharing (CORS) is the mechanism that lets web browsers call resources on another origin according to a policy advertised by the server. With Spring Data REST, CORS can be configured at the repository level using `@CrossOrigin` or at the path level using `RepositoryRestConfigurer` and `CorsRegistry`.

A CORS policy needs to clearly define:

- **Origins**: which websites are permitted to send requests from a browser to the API.
- **Methods**: the HTTP methods that origin is permitted to use.
- **Allowed headers**: the request headers the browser is permitted to send.
- **Exposed headers**: the response headers browser-side JavaScript is permitted to read.
- **Credentials**: whether requests are allowed to send cookies or browser authentication credentials.
- **Max age**: how long the browser can cache preflight results.

These values are interrelated. In particular, when credentials are enabled, the wildcard origin `*` cannot be used in the usual way. Each component must be configured properly to avoid preflight failures, response-reading errors, or exposing the API to unintended origins.

## 1. What Is an Origin?

An origin is defined by three components:

```text
scheme + host + port
```

For example:

- `https://app.example.com`
- `http://localhost:3000`
- `http://localhost:5173`

The following URLs are different origins:

| URL | Reason |
|---|---|
| `http://localhost:3000` | Port 3000 |
| `http://localhost:5173` | Port 5173 |
| `https://localhost:3000` | HTTPS scheme instead of HTTP |
| `https://app.example.com` | Host other than localhost |

The path is not part of the origin. For example, `https://app.example.com/page-a` and `https://app.example.com/page-b` share the same origin.

The browser sends the `Origin` request header to inform the server which web page initiated the cross-origin request. The server compares this value against the allowed origins list and returns the corresponding CORS response headers.

CORS is primarily a policy enforced by the browser. Programs like curl, Postman, or backend services can send requests directly without being blocked by the browser's CORS mechanism. Therefore, successfully calling an API with Postman does not prove that browser CORS configuration is correct.

## 2. How Does CORS Work?

When the frontend and API have different origins, the browser inspects CORS response headers. Depending on the request type, the browser may send the request directly or send a preflight request first.

### 2.1. Simple Request

For certain simple requests, the browser sends the actual request along with `Origin`. The server must return a matching `Access-Control-Allow-Origin` for JavaScript to be allowed to read the response.

Example:

```http
GET /people
Origin: https://app.example.com
Accept: application/hal+json
```

If the origin is allowed, the response may contain:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

If the server does not allow the origin, the browser denies JavaScript access to the response. The simple request may still have reached the server and been processed; CORS is not a request authentication mechanism.

### 2.2. Preflight Request

For requests outside the simple request group, the browser usually sends a preflight via HTTP OPTIONS to ask the server before sending the actual request. For example, a PUT with `Content-Type: application/json` and an `Authorization` header typically requires preflight.

Preflight request:

```http
OPTIONS /people/42
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization, content-type, x-request-id
```

The server returns headers indicating whether the actual request is permitted:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

If the preflight succeeds, the browser sends the actual PUT request. If the origin, method, or header is not allowed, the browser halts the flow and does not send the actual request.

OPTIONS is the method the browser uses to ask in advance. In `allowedMethods`, declare the actual methods the frontend intends to call, such as GET, POST, PUT, PATCH, and DELETE. Spring handles OPTIONS preflights based on the method requested in `Access-Control-Request-Method`; do not confuse this with granting business permissions to an OPTIONS endpoint.

## 3. Repository-Level CORS Configuration with @CrossOrigin

Spring Data REST supports `@CrossOrigin` on repository interfaces. This configuration applies to resources belonging to that repository.

Example:

```java
@RepositoryRestResource(path = "people")
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.PUT,
        RequestMethod.PATCH
    },
    allowedHeaders = {
        "Authorization",
        "Content-Type",
        "X-Request-Id"
    },
    exposedHeaders = {
        "Location",
        "ETag"
    },
    allowCredentials = "true",
    maxAge = 3600
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Meaning:

- `origins`: only the frontend at `https://app.example.com` is permitted to make cross-origin calls.
- `methods`: limits the HTTP methods the frontend can call.
- `allowedHeaders`: lets the browser send Authorization, Content-Type, and X-Request-Id.
- `exposedHeaders`: lets JavaScript read Location and ETag in the response.
- `allowCredentials`: lets the browser send credentials according to the CORS policy.
- `maxAge`: caches the preflight result for 3,600 seconds.

If only a simple configuration is needed for a repository without cookies or credentials, you can use:

```java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = { RequestMethod.GET, RequestMethod.POST }
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Avoid using `@CrossOrigin` without attributes on sensitive repositories without reviewing the defaults. According to the Spring Data REST documentation, the default annotation form allows all origins and all HTTP methods. Declare specific origins and methods according to API needs.

Spring Data REST also supports CORS on custom controllers annotated with `@RepositoryRestController`. These controllers can inherit `@CrossOrigin` configuration from the associated repository.

## 4. Global CORS Configuration with RepositoryRestConfigurer

When you need to configure by URL path instead of repeating annotations across many repositories, implement `RepositoryRestConfigurer`:

```java
@Component
public class SpringDataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE"
            )
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            )
            .exposedHeaders(
                "Location",
                "ETag"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
```

The `/people/**` mapping applies to people URIs, including collection, item, and matching subpaths. If Spring Data REST has a base path, verify the mapping path according to the application's configuration and test the actual URI.

You can register separate mappings for multiple resources:

```java
cors.addMapping("/people/**")
    .allowedOrigins("https://people.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "Authorization")
    .allowCredentials(true);

cors.addMapping("/public-catalog/**")
    .allowedOrigins("*")
    .allowedMethods("GET", "HEAD")
    .allowedHeaders("*")
    .allowCredentials(false);
```

The second example uses a wildcard origin for a public catalog without credentials. Do not use this configuration for endpoints containing user data or login sessions.

**Important note:** existing Spring MVC CORS configuration via `WebMvcConfigurer.addCorsMappings(...)` is not automatically applied to Spring Data REST. If you want to configure CORS for repository resources, use Spring Data REST's CORS mechanisms such as `RepositoryRestConfigurer` or `@CrossOrigin`. If the application also has custom MVC controllers alongside Spring Data REST, clearly identify which configuration each group of endpoints receives.

## 5. allowedOrigins: Specifying Permitted Origins

`allowedOrigins(...)` accepts a list of specific origins or the wildcard `*` when credentialed requests are not used.

Example origin list:

```java
cors.addMapping("/people/**")
    .allowedOrigins(
        "https://app.example.com",
        "https://admin.example.com",
        "http://localhost:5173"
    )
    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE");
```

Each origin must match the scheme, host, and port that the browser sends in the `Origin` header. When the frontend switches from HTTP to HTTPS or changes the dev server port, update the allow-list.

Do not include a path segment in the origin. A valid example is `https://app.example.com`, not `https://app.example.com/dashboard`.

If using `allowedOrigins("*")`, the server permits every origin under that mapping's CORS policy. This choice should only be used for public resources that do not require credentials and do not contain user-dependent data.

## 6. allowedOriginPatterns: Pattern-Based Wildcards

Spring Framework supports `allowedOriginPatterns(...)` to match a set of origins by pattern. Example:

```java
cors.addMapping("/tenant-api/**")
    .allowedOriginPatterns("https://*.example.com")
    .allowedMethods("GET", "POST")
    .allowCredentials(true);
```

Unlike `allowedOrigins("*")`, the pattern is used to find a matching origin; when a request matches, the response returns the request's actual origin instead of returning the wildcard string. This allows patterns to be used in certain credentialed request configurations.

However, a pattern does not automatically make an origin trustworthy. If any tenant or user can create a subdomain under `example.com`, the `https://*.example.com` pattern could allow origins that should not access the API. Clearly establish who controls hosts matching the pattern.

`allowedOriginPatterns` has been supported since Spring Framework 5.3. If the project uses an older version, check the corresponding API before using it. For systems with a stable list of frontends, a list of specific origins remains the easiest choice to control.

## 7. allowedMethods: Restricting HTTP Methods

`allowedMethods(...)` specifies the HTTP methods the browser is allowed to use for permitted origins.

Example:

```java
.allowedMethods("GET", "HEAD", "POST")
```

If the frontend needs to update resources, add PUT or PATCH. If it needs to delete, add DELETE. Do not open methods simply because the repository supports them; base this on what the client actually needs.

Example method permissions by resource:

| Resource | CORS methods to open |
|---|---|
| Public catalog | GET, HEAD |
| People directory | GET |
| Profile management | GET, PUT, PATCH |
| Order management | GET, POST, PUT, PATCH |
| Admin operation | GET, POST, DELETE |

CORS only tells the browser which methods are permitted to be sent cross-origin. It does not replace authorization. If an origin is allowed to send DELETE, the user must still pass Spring Security and business permission checks before deleting data.

## 8. Differences Between allowedHeaders and exposedHeaders

These two settings are frequently confused.

### 8.1. allowedHeaders: Permitted Request Headers

`allowedHeaders(...)` controls the headers the browser is allowed to send in a cross-origin request. Example:

```java
.allowedHeaders(
    "Authorization",
    "Content-Type",
    "X-Request-Id",
    "X-XSRF-TOKEN"
)
```

When a preflight is sent, the browser lists the headers it intends to use in `Access-Control-Request-Headers`. The server must permit those headers via `Access-Control-Allow-Headers`.

Common headers:

- `Authorization`: sends a bearer token or credentials depending on the mechanism the client uses.
- `Content-Type`: describes the request body format, such as JSON.
- `X-Request-Id`: correlation ID for tracing requests.
- `X-XSRF-TOKEN`: CSRF token if the application uses cookie-based CSRF.

There is no need to add every header to the allow-list if the frontend does not send them. Inspect actual requests in the browser's Network panel to know the required list.

### 8.2. exposedHeaders: Response Headers JavaScript Can Read

By default, browsers only allow JavaScript to read a few safe response headers. If the frontend needs to read other headers, the server must declare `exposedHeaders(...)`.

Example:

```java
.exposedHeaders(
    "Location",
    "ETag",
    "Link",
    "X-Request-Id"
)
```

Common scenarios:

- `Location`: read the new item's URI after POST.
- `ETag`: use as a validator for caching or conditional updates.
- `Link`: read link metadata if the client needs to process this header.
- `X-Request-Id`: display or log the trace ID.

Declaring `allowedHeaders("Location")` does not let JavaScript read the Location response header. To make the browser allow reading a response header, you must use `exposedHeaders("Location")`.

## 9. Credentials: Cookies, Sessions, and Authentication Credentials

When the frontend needs to send cookies or credentials via cross-origin requests, CORS must be configured to allow credentials.

Example:

```java
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "X-XSRF-TOKEN")
    .exposedHeaders("Location")
    .allowCredentials(true)
    .maxAge(3600);
```

Browser-side with Fetch API:

```javascript
const response = await fetch("https://api.example.com/people", {
  method: "GET",
  credentials: "include",
  headers: {
    "Accept": "application/hal+json"
  }
});
```

With XMLHttpRequest, the corresponding property is `withCredentials = true`.

The server needs to return:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

The value `Access-Control-Allow-Origin: *` is not valid for credentialed requests. Browsers reject responses containing a wildcard origin when a request uses credentials.

Enabling credentials establishes high trust with the permitted origin because the browser can send session cookies, authentication credentials, and CSRF tokens. Enable it only when genuinely needed and only for controlled origins.

CORS does not override cookie `SameSite`, `Secure`, domain, or path. Cookies must still satisfy the browser's cookie policies. In production environments, cross-site cookies often need `SameSite=None; Secure`, though attributes should be chosen according to the application's domain architecture and threat model.

## 10. Wildcard Restrictions When Credentials Are Enabled

Here is the rule to remember:

```java
// Invalid when allowCredentials(true)
.allowedOrigins("*")
.allowCredentials(true)
```

Spring Framework rejects configuring `allowedOrigins("*")` together with `allowCredentials(true)`, because the server cannot return a wildcard origin in a credentialed response under the CORS specification.

There are two approaches:

**Approach 1: declare specific origins**

```java
.allowedOrigins(
    "https://app.example.com",
    "https://admin.example.com"
)
.allowCredentials(true)
```

**Approach 2: use controlled origin patterns**

```java
.allowedOriginPatterns("https://*.example.com")
.allowCredentials(true)
```

When a pattern matches, Spring returns the actual origin instead of the wildcard character. Even so, a broad pattern can still allow a large set of hosts; do not use a pattern if subdomain creation is not under your control.

Wildcards in allowed methods and allowed headers behave differently from wildcard origins. When credentials are enabled, Spring can copy the method and headers requested by the browser in preflight into the corresponding response headers. This configuration is convenient but makes the policy broader; if the required methods/headers are known in advance, declare specific lists.

For `exposedHeaders("*")`, actual behavior differs from wildcard origin rules and has compatibility limits with the CORS specification when credentials are enabled. Do not rely on a wildcard to expose all headers in a credentialed application; list the response headers the frontend actually needs to read.

## 11. maxAge: Caching Preflight Results

`maxAge(...)` specifies how long the browser can cache preflight results, in seconds.

Example:

```java
.maxAge(3600)
```

The browser can reuse the cached preflight result for up to one hour, subject to the browser's internal caps. Consequently, subsequent requests under the same conditions do not need to send OPTIONS every time.

A long duration reduces the number of preflight requests, but causes CORS policy changes not to take effect immediately in the browser until the cache expires. In development environments or while tuning policies, use a shorter duration; once the policy stabilizes, increase it appropriately.

Do not confuse `maxAge` with login expiration, cookie expiration, or data response cache expiration.

## 12. Integrating CORS with Spring Security

If the application enables Spring Security, ensure CORS is processed before the appropriate authentication/authorization step. OPTIONS preflights usually do not carry session cookies like actual requests; if a security filter blocks OPTIONS before CORS handles it, the browser will report a CORS error even though GET/PUT endpoints may be properly protected.

Spring Security has built-in CORS support. Filter chain configuration can enable this mechanism:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

When using `.cors(Customizer.withDefaults())`, Spring Security needs to find an appropriate CORS configuration source. Check the application's existing CORS configuration and ensure the mapping also applies to repository resources. Do not create multiple CORS filters or conflicting configuration sources that result in duplicate response headers.

With Spring Data REST, configure CORS for repository resources using `RepositoryRestConfigurer` or `@CrossOrigin`. The Spring Data REST documentation notes that existing Spring MVC CORS configuration does not automatically apply to Spring Data REST. When also using Spring Security, test preflight through the entire filter chain rather than testing only the handler mapping.

## 13. CORS Does Not Replace Authentication, Authorization, or CSRF

CORS and security solve different problems:

| Mechanism | Question addressed |
|---|---|
| CORS | Browsers from which origins are allowed to read cross-origin responses? |
| Authentication | Who is the caller? |
| Authorization | Which operations is the caller allowed to perform on the resource? |
| CSRF protection | Is a request using automatically sent cookies forged from another site? |

An API allowing `https://app.example.com` via CORS must still authenticate users and check data access permissions. CORS does not stop curl or backend services from sending requests directly.

In particular, a simple request can reach the server even if the browser later blocks JavaScript from reading the response. Therefore, do not use CORS as an anti-CSRF measure. If the application uses cookie/session authentication, keep appropriate CSRF protection and send the CSRF token via an allow-listed header.

Do not allow all origins with credentials just to fix a browser error. Identify the frontend's real origin, required methods, and required headers, then configure the allow-list accordingly.

## 14. Environment-Specific Configuration Examples

In development, the frontend might run on localhost with a separate port:

```java
cors.addMapping("/people/**")
    .allowedOrigins("http://localhost:5173")
    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
    .allowedHeaders("Content-Type", "Authorization", "X-XSRF-TOKEN")
    .exposedHeaders("Location", "ETag")
    .allowCredentials(true)
    .maxAge(300);
```

In production:

```java
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "Authorization", "X-XSRF-TOKEN")
    .exposedHeaders("Location", "ETag")
    .allowCredentials(true)
    .maxAge(3600);
```

If an admin frontend sits on another origin, add that origin intentionally or create a separate mapping if permissions and capabilities differ.

Avoid putting `http://localhost:5173` in production configuration just to avoid errors in dev. Separate configurations by profile or externalize the origin list via application configuration, ensuring a production profile does not accidentally inherit wildcards from development configuration.

## 15. Checking CORS with curl

You can send a manual preflight to see what the server returns:

```bash
curl -i -X OPTIONS "http://localhost:8080/people/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Check the response headers:

- Does `Access-Control-Allow-Origin` match the origin?
- Does `Access-Control-Allow-Methods` include PUT?
- Does `Access-Control-Allow-Headers` include the headers requested by the browser?
- Does `Access-Control-Allow-Credentials` equal `true` if the request uses credentials?
- Does `Access-Control-Max-Age` have the configured value?

Test a disallowed origin:

```bash
curl -i -X OPTIONS "http://localhost:8080/people/42" \
  -H "Origin: https://unknown.example.net" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
```

The response must not grant `Access-Control-Allow-Origin` to an origin outside the policy. Curl only displays the response; it does not enforce CORS rules like a browser.

After checking with curl, test from a real frontend in a browser because the browser also applies cookies, SameSite, preflight caching, and its own CORS restrictions.

## 16. Testing CORS in the Application

You can test with MockMvc to verify that preflight is handled:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonCorsTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowsConfiguredOriginAndPutPreflight() throws Exception {
        mvc.perform(options("/people/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "PUT"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"
                ))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"
            ));
    }

    @Test
    void doesNotAllowUnknownOrigin() throws Exception {
        mvc.perform(options("/people/42")
                .header(HttpHeaders.ORIGIN, "https://unknown.example.net")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "PUT"
                ))
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
            ));
    }
}
```

This is an integration test skeleton; the preflight status and how the security filter chain handles OPTIONS depend on the application configuration. You may need to add Spring Security Test request post-processors or corresponding test authentication configuration.

You should also test:

- Valid origins and invalid origins.
- Allowed methods and rejected methods.
- Allowed request headers and disallowed headers.
- Response headers only being readable by JavaScript when listed in exposed headers.
- Credentials having `Access-Control-Allow-Credentials: true` and a non-wildcard origin.
- Both custom repository controllers and Spring Data REST repository resources receiving the expected policy.
- Preflight not being blocked by Spring Security before CORS processing.

## 17. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Browser reports CORS yet Postman succeeds | Postman does not enforce CORS like a browser | Inspect Origin and CORS response headers in the browser |
| OPTIONS returns 401/403 | Security filter blocks preflight before CORS | Enable CORS integration and ensure preflight is handled before authorization appropriately |
| Localhost frontend fails after changing port | Origin includes scheme, host, and port | Add the exact origin of the dev server |
| GET works but PUT/PATCH fails | Method is not in allowedMethods | Add the methods actually needed |
| Preflight reports header not allowed | Header missing from allowedHeaders | Add Authorization, Content-Type, or required custom headers |
| JavaScript cannot read Location | Location is not in exposedHeaders | Add exposedHeaders("Location") |
| Credentials do not work | Missing allowCredentials or browser not sending credentials | Enable allowCredentials and use credentials: "include" |
| Spring rejects CORS configuration | allowedOrigins("*") combined with allowCredentials(true) | Use specific origins or controlled allowedOriginPatterns |
| Origin pattern allows too many sites | Wildcard pattern covers untrusted subdomains | Narrow the pattern or use a list of specific origins |
| CORS annotation has no effect on repository | Annotation placed on another MVC controller or wrong bean | Place @CrossOrigin on the repository interface or use RepositoryRestConfigurer |
| MVC CORS does not apply to Spring Data REST | The two configurations belong to different handler mappings | Configure Spring Data REST CORS separately |
| Browser still sends request even though response is blocked | CORS is not a mechanism to block all requests or CSRF | Use appropriate authentication, authorization, and CSRF protection |

## 18. CORS Configuration Checklist

- Identify the exact origin of each frontend: scheme, host, and port.
- Allow only origins that actually need API access.
- Choose `@CrossOrigin` for a specific repository or `RepositoryRestConfigurer` for path-based mappings.
- Declare the HTTP methods the client actually uses.
- Distinguish request headers allowed to be sent from response headers allowed to be read.
- Add Location or ETag to exposed headers when the frontend needs to read them.
- Enable credentials only when the application requires cookies or browser credentials.
- Do not use `allowedOrigins("*")` together with `allowCredentials(true)`.
- Use `allowedOriginPatterns` only when you control all hosts matching the pattern.
- Set maxAge appropriately for how frequently the policy changes.
- Verify OPTIONS preflight through both CORS and Spring Security.
- Do not treat CORS as a replacement for authentication, authorization, or CSRF.
- Separate development and production origins.
- Test with a real browser in addition to curl/MockMvc checks.

## Conclusion

CORS in Spring Data REST can be configured at the repository level using `@CrossOrigin` or by URL path using `RepositoryRestConfigurer` and `CorsRegistry`. Origins determine which websites are allowed to make calls; methods restrict HTTP methods; allowedHeaders controls request headers; exposedHeaders determines which response headers JavaScript can read; credentials allow the browser to send cookies or authentication credentials; maxAge caches preflight results. When enabling credentials, do not use `allowedOrigins("*")`; declare specific origins or use controlled `allowedOriginPatterns`. CORS does not replace authentication, authorization, or CSRF protection. Test preflight through the full Spring Security configuration and a real browser to confirm the policy works properly.

## References

- Spring Data REST – Configuring CORS: https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html
- Spring Framework – CORS in Spring MVC, credentialed requests, origin patterns and preflight: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security – CORS integration and filter ordering: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- MDN – Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
