# Configuring @CrossOrigin on Repositories

## 1. What Is CORS and Why Does Spring Data REST Need Configuration?

CORS (Cross-Origin Resource Sharing) is an HTTP mechanism that allows a browser to read a response from a different origin than the current web page when the server permits it. An origin is defined by the triplet of scheme, host, and port.

For example:

- The frontend runs at https://app.example.com.
- Spring Data REST runs at https://api.example.com.
- The two addresses have different hosts, so they are two different origins.
- A page at http://localhost:3000 calling an API at http://localhost:8080 is also cross-origin because the ports differ.

Browsers apply the same-origin policy to restrict JavaScript from reading data from another origin. CORS gives the server a way to declare which origins, methods, and headers are permitted to be accessed from a browser.

Spring Data REST has supported CORS through Spring CORS support since version 2.6. It can be configured on repository interfaces using @CrossOrigin, on custom repository REST controllers, or globally using RepositoryRestConfigurer.

CORS is a policy enforced by the browser. It is not authentication, authorization, or a mechanism to protect endpoints from all clients. A curl command, backend application, or other HTTP tool can still send requests directly even if a browser is blocked by CORS.

## 2. Configuring CORS Directly on a Repository Interface

Spring Data REST allows placing the @CrossOrigin annotation on a repository interface. This configuration applies to the REST resources exported from that repository.

Example:

~~~~java
@CrossOrigin
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

When annotated like this, cross-origin support is enabled for the repository. The default configuration is quite broad, allowing all origins and methods according to the behavior described in the Spring Data REST documentation. Do not use this permissive configuration in production if the application only needs a specific frontend.

It is better to declare origins and methods explicitly:

~~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.DELETE
    },
    maxAge = 3600
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

In this example:

- Only the origin https://app.example.com is allowed to make calls from a browser.
- Only GET, POST, and DELETE methods are permitted via CORS.
- maxAge = 3600 allows the browser to cache the preflight result for up to one hour, subject to browser limits.

CORS configuration does not create additional endpoints or repository methods. If a repository does not export DELETE, adding DELETE to the CORS list will not make a DELETE endpoint appear.

## 3. Important Attributes of @CrossOrigin

Spring Web's @CrossOrigin annotation provides the main attributes:

| Attribute | Meaning |
|---|---|
| origins | List of permitted origins |
| originPatterns | Patterns used to match origins; requires a supporting Spring version |
| methods | HTTP methods permitted via CORS |
| allowedHeaders | Request headers the browser is allowed to send |
| exposedHeaders | Response headers JavaScript is allowed to read |
| allowCredentials | Whether the browser is allowed to send credentials |
| maxAge | Duration to cache the preflight result |

An origin consists of scheme, hostname, and port. For example, https://app.example.com and http://app.example.com are two different origins; https://app.example.com:8443 also differs from an origin without a specified port.

When using origins, declare the exact origin without adding the application's path to the origin value:

~~~~java
@CrossOrigin(origins = "https://app.example.com")
~~~~

If there are multiple valid frontends, you can list each origin:

~~~~java
@CrossOrigin(origins = {
    "https://app.example.com",
    "https://admin.example.com"
})
~~~~

Some Spring versions support originPatterns for pattern matching, such as subdomains belonging to a controlled domain. Use only sufficiently narrow patterns and check the Spring Framework version in the dependency tree. Avoid broad patterns that cause unexpected origins to be accepted.

## 4. Distinguishing allowedHeaders and exposedHeaders

These two attributes serve two different directions.

**allowedHeaders** controls the request headers that the browser is allowed to send in a cross-origin request. Example:

~~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    allowedHeaders = {
        "Content-Type",
        "Authorization",
        "If-None-Match",
        "If-Match"
    }
)
~~~~

If the frontend sends Authorization or Content-Type: application/json, the server needs to permit the corresponding headers in the CORS policy. Headers automatically added by the browser such as Origin do not need to be declared manually.

**exposedHeaders** controls the response headers that JavaScript is allowed to read. Response headers not on the CORS-safelisted response headers list will be hidden from JavaScript by the browser unless the server exposes them.

Spring Data REST can return headers such as ETag, Location, or Link. If the frontend needs to read these values, expose them explicitly:

~~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    exposedHeaders = {
        "ETag",
        "Location",
        "Link"
    }
)
~~~~

For example, when using ETag for conditional GET or If-Match for conditional updates, a frontend running on another origin needs to read ETag from the response. Allowing only the If-Match/If-None-Match request headers is not enough; if JavaScript needs to obtain ETag, expose the ETag response header.

## 5. Complete Repository Example

A restricted configuration for a people API can be written as:

~~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.RequestMethod;

@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.PUT,
        RequestMethod.PATCH,
        RequestMethod.DELETE
    },
    allowedHeaders = {
        "Content-Type",
        "Authorization",
        "If-None-Match",
        "If-Match"
    },
    exposedHeaders = {
        "ETag",
        "Location",
        "Link"
    },
    maxAge = 3600
)
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

This is an example for a frontend that needs to read, create, update, and delete people. If the application only reads data, narrow methods down to GET and HEAD according to the endpoint contract.

Important imports:

- org.springframework.web.bind.annotation.CrossOrigin
- org.springframework.web.bind.annotation.RequestMethod
- org.springframework.data.rest.core.annotation.RepositoryRestResource

Placing the annotation on the repository interface configures CORS for the entire resource group of that repository. If you only want it to apply to a custom route, consider annotating the controller method instead of opening the whole repository.

## 6. Preflight Requests and OPTIONS

Not every cross-origin request needs a preflight. For certain simple requests, the browser can send the request directly. For requests using methods or headers outside the simple group, the browser usually sends an OPTIONS request beforehand to ask the server whether the actual request is permitted.

For example, the frontend sends a PATCH with JSON and If-Match. The browser may send:

~~~~http
OPTIONS /people/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, if-match
~~~~

The server needs to return appropriate CORS headers, for example:

~~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization, If-None-Match, If-Match
Access-Control-Max-Age: 3600
Vary: Origin
~~~~

After the preflight succeeds, the browser then sends the actual PATCH request. If the preflight fails, JavaScript typically only receives a CORS error and the actual request may not be sent.

An OPTIONS preflight is not a resource update operation. It is a step for negotiating cross-origin permissions between the browser and the server.

When debugging, inspect both the OPTIONS request and the actual GET/POST/PATCH request. Checking only the response of the actual request can miss preflight failures.

## 7. Global CORS Configuration via RepositoryRestConfigurer

If multiple repositories share a policy, you can configure CORS by path at the Spring Data REST level using RepositoryRestConfigurer.

Example:

~~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
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
                "Content-Type",
                "Authorization",
                "If-None-Match",
                "If-Match"
            )
            .exposedHeaders(
                "ETag",
                "Location",
                "Link"
            )
            .allowCredentials(false)
            .maxAge(3600);
    }
}
~~~~

The mapping /people/** applies the policy to URLs belonging to the people resource, including item paths like /people/42. If there are associations or custom routes at other paths, configure corresponding mappings.

Advantages of global configuration:

- Centralizes policies in one place.
- Uses path patterns to select groups of endpoints.
- Explicitly declares origins, methods, request headers, and exposed response headers.
- Can be combined with annotation configuration at the repository or controller level.

Use global configuration when multiple repositories share the same policy. Use annotations when a single repository needs its own policy. Avoid declaring overlapping policies with unclear intent; verify the actual response headers after combining them.

## 8. Important Note: Spring MVC CORS Does Not Automatically Apply to Spring Data REST

Spring Data REST has its own CORS configuration via RepositoryRestConfigurer. The Spring Data REST documentation explicitly states that existing Spring Web MVC configuration is not automatically applied to Spring Data REST resources.

Therefore, if the application already has:

~~~~java
@Bean
WebMvcConfigurer webMvcConfigurer() {
    return new WebMvcConfigurer() {
        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/api/**")
                    .allowedOrigins("https://app.example.com");
        }
    };
}
~~~~

you should not assume that Spring Data REST repository resources are configured for CORS by this mapping. Configure them separately via RepositoryRestConfigurer or @CrossOrigin on the repository.

Custom controllers annotated with @RepositoryRestController can use @CrossOrigin following Spring MVC's controller method mechanism. These controllers can also inherit @CrossOrigin configuration from the corresponding repository according to the Spring Data REST documentation.

## 9. CORS with Credentials, Cookies, and Authorization

Some frontends need to send login session cookies or browser authentication credentials. In that case, the CORS policy must allow credentials.

In global configuration:

~~~~java
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "Authorization")
    .allowCredentials(true)
    .maxAge(3600);
~~~~

When allowCredentials is enabled:

- Do not use the wildcard origin "*" with credentials.
- Declare specific origins or controlled origin patterns.
- The browser must send the request with the appropriate credentials mode, for example fetch using credentials: "include" when cross-origin cookies are needed.
- Cookies are still subject to the browser's SameSite, Secure, domain, and path policies.
- CORS does not replace session, token, CSRF, or access permission checks.

If the frontend uses a bearer token in the Authorization header, Authorization must be allowed in allowedHeaders. Sending a token does not necessarily mean cookie credentials must be enabled; choose the policy based on the application's actual authentication mechanism.

Do not enable credentials just because the frontend and backend are on two different origins. Only enable it when the application truly needs the browser to send cookies or related credentials.

## 10. CORS Is Not Authorization or CSRF Protection

CORS primarily controls whether the browser lets JavaScript read cross-origin responses. It does not prevent non-browser clients from calling the API, nor does it prove the caller has permissions on the data.

For example:

- curl can still send DELETE directly to an endpoint.
- Another backend can still call the API if networking and authentication permit.
- A web page can send certain types of cross-origin requests, though the browser will not let JavaScript read the response if CORS forbids it.
- If an endpoint uses cookie authentication, CSRF must be evaluated separately; a CORS policy does not replace CSRF protection.

Therefore, authentication, authorization, method security, tenant checks, and CSRF must still be configured according to the application model. Do not treat the allowedOrigins list as a list of users authorized to access data.

## 11. Testing CORS with curl

curl does not enforce the same-origin policy like a browser, but it can send requests and inspect response headers.

### Testing an actual GET request

~~~~bash
curl -i \
  -H "Origin: https://app.example.com" \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people
~~~~

Check that the response includes Access-Control-Allow-Origin matching the permitted origin.

### Testing an OPTIONS preflight

~~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type, if-match" \
  http://localhost:8080/people/42
~~~~

Verify:

- Access-Control-Allow-Origin has the correct origin.
- Access-Control-Allow-Methods includes PATCH.
- Access-Control-Allow-Headers includes content-type and if-match.
- Access-Control-Max-Age has the expected value.
- The response is not blocked by the authentication layer before CORS is processed.

### Testing a disallowed origin

~~~~bash
curl -i \
  -H "Origin: https://untrusted.example.net" \
  http://localhost:8080/people
~~~~

The server should not return Access-Control-Allow-Origin for an origin outside the policy. However, the endpoint might still return a normal HTTP status; what matters is that the browser is not allowed to expose the response to JavaScript from that origin.

## 12. Testing with MockMvc and the Browser

You can verify preflight in an integration test:

~~~~java
mockMvc.perform(options("/people/42")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "PATCH")
        .header(
            "Access-Control-Request-Headers",
            "content-type, if-match"
        ))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.com"
    ))
    .andExpect(header().string(
        "Access-Control-Allow-Methods",
        org.hamcrest.Matchers.containsString("PATCH")
    ));
~~~~

You can add tests for disallowed origins, disallowed headers, disallowed methods, credentials, and exposed headers.

Finally, verify in browser DevTools:

1. Open Network.
2. Send a request from a frontend on another origin.
3. Inspect the OPTIONS request if the browser performs a preflight.
4. Check the CORS response headers.
5. Check whether the actual request is sent.
6. Read the Console to identify which origin, method, or header was rejected.

curl and MockMvc verify response headers against simulated requests; browser testing verifies the actual behavior of the same-origin policy, cookies, and frontend.

## 13. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Frontend reports CORS even though API returns 200 | Response lacks Access-Control-Allow-Origin or origin mismatches | Check Origin and repository/path policy |
| OPTIONS gets 401 or 403 | Security filter blocks preflight before CORS handling | Configure CORS processing order appropriately with Spring Security |
| GET works but PATCH fails | Preflight does not allow PATCH or headers required by PATCH are not allowed | Check Access-Control-Allow-Methods and Allow-Headers |
| JavaScript cannot read ETag | ETag is not in exposedHeaders | Expose ETag |
| Authorization cannot be sent | Authorization is not permitted in allowedHeaders | Add Authorization to allowedHeaders |
| Cookies are not sent | Credentials not enabled or browser cookie policy forbids it | Check allowCredentials, fetch credentials, and cookie attributes |
| WebMvcConfigurer configuration has no effect | Spring Data REST has its own CORS registry | Use RepositoryRestConfigurer or @CrossOrigin on the repository |
| Using "*" with credentials | CORS forbids wildcard origin with credentials | Declare a specific origin or a safe pattern |
| Local origin works but production fails | Production scheme, host, or port differs from configuration | Declare the exact production origin |
| curl succeeds but browser fails | curl does not enforce CORS policy | Inspect OPTIONS and Console in the browser |

## 14. Conclusion

@CrossOrigin on a repository interface allows configuring CORS for the REST resources exported by Spring Data REST from that repository. You can restrict origins, HTTP methods, request headers, exposed response headers, and preflight cache duration. For shared policies or configurations by URL path, RepositoryRestConfigurer provides a CorsRegistry at the Spring Data REST level.

Keep in mind that Spring Data REST CORS has its own configuration; WebMvcConfigurer does not automatically apply to repository resources. OPTIONS preflights must be handled before the actual request when required by the browser, response headers must match the origin/method/headers used by the frontend, and ETag/Location/Link need to be exposed if JavaScript must read them. CORS does not replace authentication, authorization, or CSRF protection. Use specific origins, restrict required methods/headers, and test both the actual response and the preflight in a browser.

## References

- [Spring Data REST Reference — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html)
- [Spring Framework Reference — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Guides — Enabling Cross Origin Requests for a RESTful Web Service](https://spring.io/guides/gs/rest-service-cors)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
