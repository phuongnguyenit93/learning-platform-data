# Allowing the Browser to Read Location, ETag, and Essential Headers in Spring Data REST

Spring Data REST frequently returns meaningful HTTP headers when a client creates or updates a resource. For example, `Location` can indicate the URI of a newly created resource; `ETag` can carry the resource's version so the client can control concurrent updates. However, when the frontend runs on a different origin from the API, the browser enforces CORS and does not let JavaScript arbitrarily read every response header.

For the frontend to read these headers, the server needs to declare them in `Access-Control-Expose-Headers`. With Spring Data REST, that list can be configured using `CorsRegistry.exposedHeaders(...)` in `RepositoryRestConfigurer`. Distinguish exposing response headers from allowing origins, methods, and request headers: each part solves a different problem.

## 1. How Does CORS Affect Reading Response Headers?

An origin is formed by three components: scheme, host, and port. For example, `https://app.example.com` and `https://api.example.com` are two different origins; `http://localhost:3000` and `http://localhost:8080` also differ because their ports differ.

The Same-Origin Policy restricts how a web page reads resources from another origin. CORS is the mechanism for the server to advertise which origins and cross-origin operations are permitted. The browser checks CORS response headers before granting JavaScript code access to the result.

There are two independent questions:

- Is the request allowed to be sent to the API from the current origin? The server answers with headers such as `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers`.
- After the request is accepted, which response headers is JavaScript allowed to read? The server advertises the list with `Access-Control-Expose-Headers`.

A request can succeed at the HTTP layer yet JavaScript still cannot read a header because that header has not been exposed. CORS is a browser protection mechanism; tools like curl or Postman do not apply the same response-header reading restrictions.

## 2. Why Do Location and ETag Need to Be Exposed?

Under CORS rules, browsers by default only allow JavaScript to read a group of safe response headers, typically including:

- `Cache-Control`
- `Content-Language`
- `Content-Length`
- `Content-Type`
- `Expires`
- `Last-Modified`
- `Pragma`

Headers such as `Location` and `ETag` are not in this default group. If the API returns them without exposing them, `response.headers.get(...)` in frontend code may receive `null`.

### Location

When a client creates a resource via POST, the API typically returns `Location` to indicate the URI of the new resource. The client can read this URI to navigate to a details page or perform subsequent requests.

Example response:

    HTTP/1.1 201 Created
    Location: https://api.example.com/api/orders/42
    Content-Type: application/hal+json

The `Location` header must actually be present in the response. CORS exposure only permits JavaScript to read the value already sent by the server; it does not generate Location and does not change the status code.

### ETag

`ETag` is a validator representing a version of the resource. The client can store this value and send it back in a later request to check for concurrent updates, usually via `If-Match`.

Example response:

    HTTP/1.1 200 OK
    ETag: "7"

When updating, the client can send:

    PUT /api/orders/42
    If-Match: "7"
    Content-Type: application/json

    {
      "description": "Updated order"
    }

If the resource version has changed, the server can reject the update using optimistic locking, usually with status `412 Precondition Failed` or a conflict response according to how the application is configured. ETag must be generated and validated properly by the server; merely exposing the header does not enable optimistic locking.

In Spring Data REST, the ETag mechanism may depend on mapping and persistence configuration, such as a `@Version` property. Inspect the endpoint's actual response to confirm that ETag is emitted.

## 3. Configuring CORS for Spring Data REST

Spring Data REST provides `RepositoryRestConfigurer` to customize REST repository configuration. Permitted origins, methods, request headers, and response headers can all be declared in the same `CorsRegistry`.

Spring Boot 3 example:

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
                    "GET", "POST", "PUT", "PATCH", "DELETE"
                )
                .allowedHeaders(
                    "Authorization",
                    "Content-Type",
                    "If-Match",
                    "If-None-Match"
                )
                .exposedHeaders(
                    "Location",
                    "ETag"
                )
                .allowCredentials(true)
                .maxAge(3600);
        }
    }

Meaning of each part:

- `addMapping("/**")`: applies the configuration to endpoints matching the path. If the API has a custom base path, you can narrow the mapping to the actual path.
- `allowedOrigins(...)`: allows the frontend at the specified origin to call the API. Origin values include only scheme, host, and port, without adding a path.
- `allowedMethods(...)`: declares the HTTP methods that cross-origin requests are permitted to use.
- `allowedHeaders(...)`: declares request headers the browser is allowed to send, such as `Authorization`, `Content-Type`, and `If-Match`.
- `exposedHeaders(...)`: declares response headers JavaScript is allowed to read, `Location` and `ETag` in this example.
- `allowCredentials(true)`: allows the browser to send credentialed authentication details such as cookies in cross-origin requests.
- `maxAge(3600)`: allows the browser to cache preflight results for up to 3,600 seconds, subject to browser limits.

If the frontend only needs to read Location and ETag, those two headers are the core of `exposedHeaders`. Other headers should only be added when the client genuinely needs to read them, such as `X-Request-Id` for log correlation.

Do not register multiple overlapping CORS configurations for the same endpoint if they produce conflicting `Access-Control-Allow-Origin` or exposed header values. Place the policy in the configuration matching the application's request path.

## 4. Distinguishing allowedHeaders and exposedHeaders

This is a common point of confusion when configuring CORS:

| Configuration | Applies to | Example | Purpose |
|---|---|---|---|
| `allowedHeaders` | Request sent from browser to server | `Authorization`, `If-Match` | Permits the client to send the header |
| `exposedHeaders` | Response from server to browser | `Location`, `ETag` | Permits JavaScript to read the header |

For example, the frontend wants to use ETag in an update flow:

1. GET the resource and read the `ETag` response header. The server needs to expose `ETag`.
2. Store the ETag on the frontend.
3. Send PUT or PATCH with the `If-Match` request header. The server needs to permit the `If-Match` request header via `allowedHeaders`.
4. The server compares the version and processes the update.
5. If the new response includes an ETag, the frontend again needs that header exposed to read the next version.

Adding only `ETag` to `exposedHeaders` will not allow the browser to send `If-Match`. Conversely, adding only `If-Match` to `allowedHeaders` will not allow JavaScript to read the `ETag` response header either.

## 5. Using Headers in the Frontend

Example using the Fetch API to create an order and read the new resource's URI:

    const response = await fetch(
      "https://api.example.com/api/orders",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          description: "New order"
        })
      }
    );

    if (!response.ok) {
      throw new Error("Create order failed: " + response.status);
    }

    const location = response.headers.get("Location");
    const etag = response.headers.get("ETag");

    console.log("Created resource:", location);
    console.log("Resource version:", etag);

If the server returns both headers and CORS exposes them properly, the frontend can read them. If the value is `null`, inspect the actual response and CORS policy before concluding that the server did not produce the header.

Example sending ETag in an update request:

    const response = await fetch(
      "https://api.example.com/api/orders/42",
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "If-Match": savedEtag
        },
        body: JSON.stringify({
          description: "Updated order"
        })
      }
    );

    if (response.status === 412) {
      throw new Error("The order has changed; reload before editing.");
    }

    if (!response.ok) {
      throw new Error("Update failed: " + response.status);
    }

    const nextEtag = response.headers.get("ETag");

A request containing the `If-Match` header usually triggers the browser to send a preflight because it is not a CORS-safelisted request header. The server must permit that header in `allowedHeaders`. Exposing response headers remains configured separately.

## 6. Credentials, Wildcards, and Specific Origins

When the frontend sends cross-origin cookies, the Fetch API needs to use:

    fetch(url, {
      credentials: "include"
    });

The server must permit credentials and return a specific origin, for example:

    Access-Control-Allow-Origin: https://app.example.com
    Access-Control-Allow-Credentials: true
    Access-Control-Expose-Headers: Location, ETag

`Access-Control-Allow-Credentials: true` cannot be combined with the wildcard origin `*` in a way that lets the browser accept a credentialed response. Spring also checks this constraint when `allowedOrigins("*")` is used together with `allowCredentials(true)`.

With credentialed requests, do not use `Access-Control-Expose-Headers: *` in place of a specific header list. When a request carries credentials, `*` does not act as an expose wildcard; the browser interprets it as the name of a header with an asterisk character. List them explicitly:

    .exposedHeaders("Location", "ETag")

If only using a Bearer token in the `Authorization` request header, `Authorization` still must be permitted in `allowedHeaders`. Whether `allowCredentials(true)` is needed depends on how the application transmits credentials; do not enable this option just because the request has an Authorization header.

Allow only trusted origins. Do not arbitrarily reflect the Origin value sent by the client and do not open all origins when the API uses cookies or sensitive authentication credentials.

## 7. Spring Security and Preflight Requests

If the application has Spring Security, CORS must be processed before security requires authentication for the actual request. The browser may send an `OPTIONS` preflight to ask the server whether the origin, method, and request headers are permitted. Preflights usually do not carry session cookies like the main request.

When configuring the security chain, enable appropriate CORS support and ensure security's CORS policy does not conflict with the Spring Data REST configuration. Example security configuration might use:

    http.cors(Customizer.withDefaults());

How `CorsConfigurationSource` is provided or integrated with MVC depends on the application's security architecture. Avoid registering two independent policies with different values for the same path.

If the preflight receives 401 or 403, check the order of CORS and security processing. If the preflight succeeds yet JavaScript cannot read ETag, check `Access-Control-Expose-Headers`; these two errors occur at two different stages.

## 8. Checking CORS and Response Headers

You can use browser DevTools:

1. Open the Network tab and make the request from the frontend.
2. Select the actual request, inspect the status code and response headers.
3. Confirm whether the server returns `Location` or `ETag`.
4. Confirm the response has a matching `Access-Control-Allow-Origin`.
5. Confirm the response has `Access-Control-Expose-Headers` containing the header names to be read.
6. If an OPTIONS request appears, check whether the preflight permits the method and request headers the browser asked for.

You can test preflight with curl:

    curl -i -X OPTIONS \
      "https://api.example.com/api/orders" \
      -H "Origin: https://app.example.com" \
      -H "Access-Control-Request-Method: POST" \
      -H "Access-Control-Request-Headers: content-type,authorization"

Compare the response against the expected origin, method, and request headers. Curl only shows the HTTP response; it does not simulate the browser blocking JavaScript from reading headers under CORS.

Common symptoms:

| Symptom | Possible cause | What to check |
|---|---|---|
| Network shows Location but JavaScript gets null | Location is not exposed | Add Location to exposedHeaders |
| Network has no Location | Endpoint does not emit Location or request did not create a resource | Check endpoint status and response |
| Network shows ETag but JavaScript gets null | ETag is not exposed | Add ETag to exposedHeaders |
| Preflight is rejected | Origin, method, or request header is not permitted; security blocks OPTIONS | Check allowedOrigins, allowedMethods, allowedHeaders, and security |
| Can read ETag but sending If-Match is blocked | Request header is not permitted | Add If-Match to allowedHeaders |
| Curl reads every header but browser cannot | Curl does not enforce browser CORS policy | Check CORS response and test from the exact frontend origin |

## 9. Deployment Checklist

Before putting the configuration into production, confirm:

- The frontend origin is declared accurately, including scheme and port if applicable.
- Only the HTTP methods the client needs are permitted.
- Request headers such as `Authorization`, `Content-Type`, and `If-Match` are permitted when used.
- Response headers `Location`, `ETag`, and any headers that actually need to be read are exposed.
- If using cross-origin cookies, the frontend sends credentials and the server permits credentials with specific origins.
- Spring Security processes preflights properly and does not override the CORS policy.
- The endpoint actually emits Location or ETag; exposing does not create missing headers.
- Both preflight, successful requests, and responses where JavaScript reads headers have been tested.

CORS exposure is the bridge between Spring Data REST's HTTP responses and the frontend's ability to observe them. When both the permission to send requests and the permission to read responses are configured properly, the frontend can use Location to navigate to newly created resources and ETag to support concurrent update control.