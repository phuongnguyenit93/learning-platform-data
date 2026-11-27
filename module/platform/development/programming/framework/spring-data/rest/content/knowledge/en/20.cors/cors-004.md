# Global CORS Configuration via RepositoryRestConfigurer and CorsRegistry

## Objectives

After this lesson, you will be able to:

- Explain why browsers apply the same-origin policy and when CORS is needed.
- Understand that an origin consists of scheme, host, and port.
- Distinguish a preflight request from an actual request.
- Configure CORS for repository resources using RepositoryRestConfigurer and CorsRegistry.
- Choose allowedOrigins, allowedMethods, allowedHeaders, exposedHeaders, allowCredentials, and maxAge.
- Distinguish global configuration from narrow-scoped @CrossOrigin.
- Integrate CORS with Spring Security and inspect response headers with curl.
- Avoid using CORS as an authentication or authorization mechanism.

## 1. What Problem Does CORS Solve?

Browsers apply the **same-origin policy** to restrict how a web page reads data from another origin. An origin is defined by three components:

- **Scheme**: the protocol, such as http or https.
- **Host**: the domain name or server address.
- **Port**: the connection port.

For example:

~~~text
Frontend: https://app.example.com
API:      https://api.example.com
~~~

The two addresses above have different hosts, so they are two different origins. When JavaScript from the frontend calls the API, the browser checks the **Cross-Origin Resource Sharing (CORS)** policy in the API's response to decide whether to let JavaScript read the response.

CORS is a browser-side mechanism based on HTTP headers returned by the server. The server declares which origins are allowed access, which methods are permitted, which request headers can be sent, and which response headers JavaScript can read.

CORS does not prevent any other client from calling the API. curl, backend applications, or arbitrary HTTP programs do not enforce the browser's same-origin policy. Therefore, CORS does not replace authentication, authorization, CSRF protection, or data validation.

## 2. When Does a Request Need a Preflight?

Some cross-origin requests can be sent directly under CORS rules. For requests outside the simple group, the browser sends a **preflight request** using the OPTIONS method to ask the server before sending the actual request.

For example, the frontend sends a POST with Content-Type application/json and an Authorization header. The browser may first send:

~~~http
OPTIONS /api/people HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
~~~

The server returns headers indicating whether the request is permitted:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: authorization, content-type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

If the preflight is accepted, the browser then sends the actual POST. If the server does not allow the requested origin, method, or headers, the browser blocks the actual request according to CORS rules.

Not every request has a preflight. Some simple requests can be sent directly; the browser still checks the CORS response before allowing JavaScript to read the result.

## 3. Global CORS in Spring Data REST

Spring Data REST lets you configure CORS for repository resources through the **RepositoryRestConfigurer** interface. The **configureRepositoryRestConfiguration** method receives a **CorsRegistry** object, from which you register mappings and CORS policies.

Example configuration for a repository API:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RepositoryCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
            )
            .allowedHeaders(
                "Accept",
                "Content-Type",
                "Authorization",
                "If-Match",
                "If-None-Match"
            )
            .exposedHeaders(
                "Location",
                "ETag",
                "Link"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

The configuration above illustrates a frontend with a fixed origin. The **/*** mapping applies to repository paths managed by Spring Data REST. If the application needs a narrower scope, use a path pattern that matches the actual base path and repository resources.

Each method in CorsRegistry has its own role. Do not treat them as different ways of writing the same header list.

## 4. Meaning of Each CorsRegistry Configuration

| Method | Role | Example |
|---|---|---|
| **addMapping(path)** | Selects the paths where CORS applies | **/*** |
| **allowedOrigins(...)** | Declares permitted origins | **https://app.example.com** |
| **allowedMethods(...)** | Declares permitted HTTP methods | GET, POST, PATCH |
| **allowedHeaders(...)** | Declares request headers the client can send | Authorization, Content-Type |
| **exposedHeaders(...)** | Declares response headers JavaScript can read | Location, ETag, Link |
| **allowCredentials(true)** | Allows cross-origin requests to use credentials per browser policy | Cookies or supported credentials |
| **maxAge(seconds)** | Duration for which the browser can cache the preflight result | 3600 |

### addMapping

**addMapping** takes the path pattern of the handlers where CORS applies. For example, **/*** is suitable when you want to apply one policy to all repository endpoints configured in Spring Data REST.

If the API has a custom base path such as **/api**, check how the base path is mapped in the application and choose a pattern matching the actual handler path. Do not add or omit prefixes by guessing; inspect the request URL and exporter configuration.

### allowedOrigins

**allowedOrigins** lists specific origins permitted to access:

~~~java
.allowedOrigins(
    "https://app.example.com",
    "https://admin.example.com"
)
~~~

The origin must match scheme, host, and port. For example, https://app.example.com and http://app.example.com are two different origins. An origin running on port 3000 also differs from an origin on port 443.

Declare only frontends that genuinely need API access. Do not include paths like /dashboard in an origin because paths are not part of an origin.

### allowedMethods

**allowedMethods** determines which cross-origin methods are permitted:

~~~java
.allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
~~~

Choose the exact methods the API provides. If the browser needs to perform an OPTIONS preflight, the framework handles OPTIONS for CORS; you can explicitly include OPTIONS in the list when appropriate for the application's configuration and setup.

CORS allows a method to pass the browser check. The server must still verify whether the endpoint actually supports that method and whether the caller has permission to execute it.

### allowedHeaders

**allowedHeaders** specifies request headers the frontend is allowed to send:

~~~java
.allowedHeaders(
    "Accept",
    "Content-Type",
    "Authorization",
    "If-Match"
)
~~~

If the frontend sends Authorization or a custom header that is not permitted, the preflight may fail.

HTTP header names are case-insensitive. You can explicitly declare the headers the application uses to make the contract readable and limit the request surface.

### exposedHeaders

**exposedHeaders** controls the response headers that JavaScript can read via Fetch or XMLHttpRequest:

~~~java
.exposedHeaders("Location", "ETag", "Link")
~~~

Browsers only expose a few response headers by default. If the client needs to read Location after POST, ETag to send If-Match, or Link for hypermedia discovery, expose the corresponding headers.

Distinction:

- **allowedHeaders**: headers the frontend is allowed to send in a request.
- **exposedHeaders**: headers the frontend is allowed to read in a response.

Putting ETag into allowedHeaders does not allow JavaScript to read the ETag response header. Conversely, exposing Location does not allow the frontend to send a Location request header on its own.

### allowCredentials

When the frontend sends cookies or credentials cross-origin, the configuration needs to permit credentials:

~~~java
.allowCredentials(true)
~~~

The frontend also needs to request sending credentials, for example Fetch using **credentials: "include"**. Server and client configuration must align with cookie policy, SameSite, Secure, and cookie domain.

When allowing credentials, do not use the wildcard origin **\*** in Access-Control-Allow-Origin. The server needs to return the specific accepted origin. Use a trusted origin list; do not arbitrarily reflect the Origin value from the request.

### maxAge

**maxAge** tells the browser how long it can cache the preflight result:

~~~java
.maxAge(3600)
~~~

The value is in seconds. During that time, the browser may skip re-sending OPTIONS for the same combination of origin, method, and request headers according to CORS rules.

maxAge only caches preflight results. It is not the TTL of API data and does not control GET HTTP response caching.

## 5. Generated Request and Response Headers

With an appropriate CORS configuration, the server may return the following response headers:

| Response header | Meaning |
|---|---|
| **Access-Control-Allow-Origin** | Origin permitted to read the response |
| **Access-Control-Allow-Methods** | Methods permitted in the CORS policy |
| **Access-Control-Allow-Headers** | Permitted request headers |
| **Access-Control-Expose-Headers** | Response headers exposed to JavaScript |
| **Access-Control-Allow-Credentials** | Indicates whether the response allows credentials |
| **Access-Control-Max-Age** | Duration to cache the preflight result |
| **Vary: Origin** | Tells caches that the response may vary by Origin |

Spring Framework generates these headers from the CorsRegistry configuration. When verifying, inspect both the OPTIONS response and the actual request's response.

If the server returns **Access-Control-Allow-Origin: https://app.example.com**, the browser can let JavaScript from that origin read the response when other CORS conditions are also valid. If the origin is not accepted, the header may be missing or the response will not satisfy preflight.

## 6. Repository-Scoped Configuration

Configuration in RepositoryRestConfigurer is suitable when multiple repository resources share a single policy. If a repository needs its own origins or methods, consider configuring at the repository scope using the **@CrossOrigin** annotation if the application's version and mapping of Spring Data REST support it.

Example:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.web.bind.annotation.CrossOrigin;

@CrossOrigin(origins = "https://app.example.com")
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

A narrow scope is useful when only one repository needs to be accessed by a specific frontend. Global configuration avoids repeating the same policy across multiple repositories.

When combining global and repository-level configurations, verify which rules apply to a specific endpoint. Avoid creating multiple overlapping CORS policies that cause responses to have duplicate headers or inconsistent values.

## 7. CORS with Spring Security

If the application uses Spring Security, OPTIONS preflight requests may be processed by security filters before reaching Spring MVC. Preflights usually do not send session cookies like the actual request, so if security requires immediate authentication, the browser may receive 401 or 403 before CORS is processed.

Enable CORS integration in SecurityFilterChain:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.cors(withDefaults());

        // Keep existing authentication/authorization rules.
        return http.build();
    }
}
~~~

Spring Security can use the CORS configuration from Spring MVC when integrated appropriately, or use a separately declared **CorsConfigurationSource**. If the application already has a separate CORS configuration source for the security filter chain, synchronize the permitted origins, methods, and headers with the repository exporter's policy.

Do not open all endpoints to anonymous access just to make preflight work. CORS needs to be processed in the right order; authentication and authorization for actual requests must still be preserved according to the application policy.

## 8. Frontend Example Sending Requests with Credentials

If the API uses session cookies and allows the frontend to send credentials:

~~~javascript
const response = await fetch(
  "https://api.example.com/api/people",
  {
    method: "GET",
    credentials: "include",
    headers: {
      "Accept": "application/hal+json"
    }
  }
);

const etag = response.headers.get("ETag");
const location = response.headers.get("Location");
~~~

The server must allow the exact origin and credentials. If the frontend needs to read ETag or Location, those headers must be in exposedHeaders.

If using a bearer token instead of cookies, the frontend sends Authorization:

~~~javascript
const response = await fetch(
  "https://api.example.com/api/people",
  {
    headers: {
      "Accept": "application/hal+json",
      "Authorization": "Bearer <access-token>"
    }
  }
);
~~~

Authorization usually causes the request to require preflight because it is not a CORS-safelisted request header. The server needs to allow the Authorization header in allowedHeaders. CORS allowing the header to be sent does not authenticate the token; the authentication filter must still validate the token.

## 9. Testing Preflight with curl

curl does not enforce the same-origin policy, but it can send a simulated preflight OPTIONS request to inspect the headers returned by the server.

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  http://localhost:8080/api/people
~~~

Verify:

1. Whether the response has a success status for preflight.
2. Whether Access-Control-Allow-Origin matches the frontend origin.
3. Whether Access-Control-Allow-Methods includes POST.
4. Whether Access-Control-Allow-Headers includes Authorization and Content-Type.
5. Whether Access-Control-Max-Age has the desired duration.
6. Whether Vary: Origin is present when the response depends on the origin.

Then send the actual request:

~~~bash
curl -i \
  -H "Origin: https://app.example.com" \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

The actual response also needs appropriate CORS headers so the browser allows JavaScript to read the content. Checking only OPTIONS is not enough.

## 10. Inspecting in Browser DevTools

Open the Network tab and filter by API requests:

- Look for the **OPTIONS** request before POST/PUT/PATCH if the browser performs a preflight.
- Inspect Request Headers, especially Origin, Access-Control-Request-Method, and Access-Control-Request-Headers.
- Inspect Response Headers of the preflight.
- Open the actual request and check Access-Control-Allow-Origin.
- If JavaScript reads Location or ETag as null, check Access-Control-Expose-Headers.
- If the request gets 401/403, determine whether the error comes from the CORS handler or the authentication/authorization filter.

CORS messages in the console usually only state that the browser prevented JavaScript from reading the response. Inspect the Network panel to identify the actual response, status code, and any missing headers.

## 11. Common Errors

### Origin Mismatch

An origin consists of scheme, host, and port. http differs from https; app.example.com differs from api.example.com; port 3000 differs from port 443. Declare the exact origin where the frontend is running.

### Using Wildcard with Credentials

Access-Control-Allow-Origin cannot be a wildcard when the response allows credentials. Use specific origins and permit only trusted frontends.

### Mixing Up allowedHeaders and exposedHeaders

allowedHeaders is for request headers sent by the client. exposedHeaders is for response headers read by JavaScript. If the frontend cannot read Location, check exposedHeaders.

### Preflight Gets 401 or 403

Spring Security may be blocking OPTIONS before CORS is processed. Enable CORS integration and ensure the configuration is applied before authentication for preflights, while actual requests remain protected.

### Configuring Only OPTIONS While Forgetting the Actual Method

The preflight asks the server about methods like POST or PATCH. allowedMethods must allow the actual method that the frontend will call.

### curl Succeeds but Browser Still Blocks

curl does not apply CORS. Inspect the response headers, actual origin, credentials, preflight, and actual request response in DevTools.

### Configuring CORS but Forgetting to Expose Location or ETag

The header may appear in the Network response yet remain unreadable to JavaScript. Add the exact response header to exposedHeaders.

### Unnecessarily Allowing All Origins

An overly broad CORS policy increases the access surface from other websites. Restrict origins, methods, and request headers to the frontend's actual needs.

### Thinking CORS Replaces API Security

A program outside the browser can still call the endpoint. The server must still authenticate users, authorize resources, protect against CSRF when using cookies, and validate data.

## 12. Key Takeaways

- An origin is defined by scheme, host, and port.
- CORS lets the browser read cross-origin responses based on the server's policy.
- Preflights use OPTIONS to check origin, method, and request headers before the actual request.
- RepositoryRestConfigurer and CorsRegistry centrally configure CORS for Spring Data REST repository resources.
- allowedOrigins, allowedMethods, and allowedHeaders control requests; exposedHeaders controls response headers JavaScript can read.
- allowCredentials requires a specific origin policy; do not use a wildcard origin with credentials.
- maxAge caches preflight results, not API data TTL.
- When using Spring Security, ensure CORS is processed before the authentication step blocks preflights.
- curl helps inspect HTTP headers but does not simulate browser enforcement; verify further in DevTools.
- CORS does not replace authentication, authorization, CSRF protection, or validation.

## References

- [Spring Data REST Reference — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/cors.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
