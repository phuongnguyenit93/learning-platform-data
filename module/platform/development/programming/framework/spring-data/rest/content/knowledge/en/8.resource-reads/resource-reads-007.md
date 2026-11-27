# Reading Location, Content-Type, and Response Headers

## Objectives

After this lesson, you will be able to read status codes and response headers; locate a newly created resource's URI via **Location**; understand **Content-Type** and content negotiation; distinguish Location from Content-Location and HAL self links; recognize ETag, caching, and CORS headers; and inspect headers using curl and Java HTTP Client.

## 1. Structure of an HTTP response

An HTTP response consists of a status line, headers, and a body. The status line indicates the outcome, headers describe response metadata, and the body contains the representation returned by the server.

Illustrative example when creating a member with Spring Data REST:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/members/42
Content-Type: application/hal+json

{
  "name": "Lan",
  "emailAddress": "lan@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members/42"
    }
  }
}
~~~

This is an illustrative response. Actual status, URI, body, and headers depend on the endpoint, configuration, framework version, and data.

When reading a response, start with the status code, then inspect headers relevant to the operation, and finally read the body. Do not look only at the JSON and ignore HTTP metadata.

## 2. Location: URI of the created resource

**Location** is especially useful when a client creates a resource via POST. The request might look like:

~~~http
POST /api/members HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
Content-Type: application/json

{
  "name": "Lan",
  "emailAddress": "lan@example.com"
}
~~~

Upon successful creation, the server typically returns **201 Created** and indicates the URI of the new resource in **Location**:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/members/42
Content-Type: application/hal+json
~~~

The client uses the URI in Location to access the newly created resource:

~~~http
GET /api/members/42 HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

This approach saves the client from manually assembling URLs or guessing IDs from the response body. IDs may not be sequential numbers, URLs may have custom structures, and the server may change routing rules.

### Location can be a relative URI

The Location value can be a URI reference. Many servers return an absolute URL, but clients must also handle the relative case by resolving it against the URI of the current response/request.

Example:

~~~text
Request URI: http://localhost:8080/api/members
Location:    /api/members/42
Resolved:    http://localhost:8080/api/members/42
~~~

Use a URI library to resolve URI references. Avoid manual string concatenation because it easily produces broken URLs when slashes, query strings, or proxy prefixes are involved.

### Not every response has Location

Location typically appears in successful resource creation responses or certain redirect responses. Standard GET requests are not required to return this header. If an endpoint does not return Location, the client should rely on the API contract and links in the body instead of guessing.

## 3. Content-Type: representation type in the response

**Content-Type** describes the format of the body the server is sending. Spring Data REST typically returns HAL with the media type:

~~~http
Content-Type: application/hal+json
~~~

This media type indicates that the body is JSON structured according to HAL, with components such as **_links** and possibly **_embedded**.

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members/42"
    }
  },
  "name": "Lan",
  "emailAddress": "lan@example.com"
}
~~~

Responses may use other media types depending on negotiation and configuration. Do not assume all JSON shares the same structure: plain JSON and HAL JSON both use JSON syntax but have different representation contracts.

### Distinguishing Accept and Content-Type

| Header | Where it appears | Role |
|---|---|---|
| **Accept** | Request | Client tells the server which media type it wants to receive |
| **Content-Type** | Request with body | Client tells the server what format the uploaded body uses |
| **Content-Type** | Response with body | Server tells the client what format the returned body uses |

Example where the client sends JSON and wants HAL JSON in return:

~~~http
Accept: application/hal+json
Content-Type: application/json
~~~

These two headers describe two different directions. If the client requests a media type the server does not support, the server may return **406 Not Acceptable**. If the client sends a body with a Content-Type not supported by the endpoint, the server may return **415 Unsupported Media Type**.

Responses with no body, such as **204 No Content**, typically do not have a Content-Type because there is no representation to describe. Clients should check the status before parsing JSON.

## 4. Location, Content-Location, and HAL self link

Three elements may all contain URIs yet do not share the same meaning:

| Element | Meaning |
|---|---|
| **Location** | URI of the created resource in a 201 response, or target of certain redirect responses |
| **Content-Location** | URI identifying the representation in the response body |
| **_links.self.href** | Hypermedia link pointing to the resource/representation itself per the HAL contract |

Example HAL body:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members/42"
    }
  },
  "name": "Lan"
}
~~~

**_links.self.href** resides in the body and helps the client continue API discovery. **Location** is HTTP-level metadata; after a successful creation POST, clients typically use Location to learn the URI of the newly created resource. If the body also includes a self link, the two URIs often point to the same resource, though you should not assume they are always identical.

**Content-Location** refers to the URI of the representation in the message. Do not use it in place of Location when handling resource creation results.

## 5. Other headers to recognize

| Header | Meaning | Usage |
|---|---|---|
| **ETag** | Validator representing a version of a representation | Resend via If-None-Match or If-Match if supported by the server |
| **Last-Modified** | Time the representation was last modified | Can be used with If-Modified-Since |
| **Cache-Control** | Caching policy | Determines whether and for how long a response can be cached |
| **Vary** | Which request headers affect the representation | Helps caches distinguish response variants |
| **Link** | Header-level HTTP links per Web Linking | Can supplement relationships outside the body |
| **Allow** | HTTP methods supported by the resource | Useful when checking valid methods |
| **Access-Control-Expose-Headers** | Response headers readable by JavaScript over CORS | Needed if the frontend needs to read Location, ETag, or Link |

Not every endpoint returns all of the headers above. Treat them as optional metadata depending on the contract and server configuration.

### ETag and conditional requests

If the server returns:

~~~http
ETag: "member-42-v3"
~~~

the client can send this validator in a subsequent request:

~~~http
If-None-Match: "member-42-v3"
~~~

For GET, if the representation has not changed and the server supports conditional requests, the server may return **304 Not Modified** so the client can use its cached copy. For updates, **If-Match** can help prevent overwriting a modified version; the server may return **412 Precondition Failed** if the validator no longer matches.

ETag only works this way when the server actually issues and validates validators. Do not generate ETags on the client and do not assume Spring Data REST always returns an ETag for every repository.

### Cache-Control and Vary

**Cache-Control** can specify whether a response is public, private, no-cache, or no-store, along with cache duration. For personal data, clients must respect the server's cache policy and avoid storing sensitive responses in shared caches.

**Vary: Accept** indicates the representation may vary by the Accept request header. Caches must distinguish HAL responses from other media type variants if the server provides them.

### Link header and HAL _links

The HTTP **Link** header and the **_links** field in HAL both describe link relationships, but in different locations and through different representation mechanisms. Spring Data REST typically uses the HAL body for repository resource discovery. If a response includes a Link header, parse relations and URIs according to that header's syntax; do not confuse it with the JSON object in the body.

## 6. Inspecting responses with curl

Use **-i** to print both response headers and body:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members
~~~

When creating a member, include Content-Type for the request body:

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","emailAddress":"lan@example.com"}' \
  http://localhost:8080/api/members
~~~

Focus on checking:

1. Whether the status code is **201 Created** on successful creation.
2. Whether the **Location** header is present and whether its URI points to the item resource.
3. Whether **Content-Type** matches the representation requested by the client.
4. Whether the body has appropriate HAL links for further navigation.
5. Whether cache/validator headers appear and need to be handled by the client.

You can save headers and body separately:

~~~bash
curl -sS \
  -D response-headers.txt \
  -o response-body.json \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members
~~~

The **-D** option writes response headers to a file; **-o** writes the body. This is useful when comparing metadata across multiple requests.

## 7. Reading headers with Java HTTP Client

Java 21 includes HTTP Client in the JDK. After sending a request, the client can retrieve the status code, headers, and body from the same response.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Optional;

public class MemberApiClient {

    private final HttpClient httpClient = HttpClient.newHttpClient();

    public void createMember() throws Exception {
        URI collectionUri =
            URI.create("http://localhost:8080/api/members");

        String json = """
            {
              "name": "Lan",
              "emailAddress": "lan@example.com"
            }
            """;

        HttpRequest request = HttpRequest.newBuilder(collectionUri)
            .header("Accept", "application/hal+json")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = httpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        int status = response.statusCode();

        Optional<String> locationHeader =
            response.headers().firstValue("Location");

        Optional<String> contentType =
            response.headers().firstValue("Content-Type");

        URI createdUri = locationHeader
            .map(collectionUri::resolve)
            .orElse(null);

        System.out.println("Status: " + status);
        System.out.println("Location: " + createdUri);
        System.out.println("Content-Type: " + contentType.orElse("(absent)"));
        System.out.println("Body: " + response.body());
    }
}
~~~

In the example, **firstValue** returns an Optional because the header may be absent. **URI.resolve** handles both absolute and relative URIs based on the collection URI. A real application should check the status code before treating the response as a successful creation, and only then use Location.

HTTP header names are case-insensitive. When reading headers, use the HTTP client's API rather than manually parsing raw response text by string searching.

## 8. Reading headers in the browser and CORS

A response may contain Location, yet JavaScript running on another origin still cannot read that header if the server does not expose it.

Frontend example:

~~~javascript
const response = await fetch(
  "http://localhost:8080/api/members",
  {
    method: "POST",
    headers: {
      "Accept": "application/hal+json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      name: "Lan",
      emailAddress: "lan@example.com"
    })
  }
);

const location = response.headers.get("Location");
const contentType = response.headers.get("Content-Type");
~~~

For JavaScript to read **Location**, **ETag**, **Link**, or **Content-Location**, the server must expose those headers via CORS:

~~~http
Access-Control-Expose-Headers: Location, Content-Location, ETag, Link
~~~

Example Spring Data REST configuration via RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestCorsConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        cors.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Accept", "Content-Type", "If-Match", "If-None-Match")
            .exposedHeaders("Location", "Content-Location", "ETag", "Link");
    }
}
~~~

Replace the example origin with your actual frontend origin and integrate it into your existing CORS configuration. If requests use credentials, the origin must be specific and compliant with credential policies; do not use wildcards arbitrarily.

CORS only controls whether the browser allows JavaScript to read the response. It does not replace authentication or authorization on the server.

## 9. Common errors

### POST succeeds, but the client cannot find the new resource

Check the status code and the Location header. If the client only parses the body, it may miss the canonical URI provided by the server. For a 201 response, prioritize Location per the HTTP contract and cross-check the self link if the body contains HAL.

### Client parses the body even when the response has no content

A 204 response has no body. Check the status before calling a JSON parser or deserializing an entity.

### Sending the wrong Accept header

A client sending an unsupported Accept header may receive 406. Request a media type the API actually provides and read the response Content-Type to see what the server returned.

### Confusing request Content-Type with response Content-Type

Request Content-Type describes the JSON sent by the client; response Content-Type describes the HAL/JSON returned by the server. The two values can differ.

### Browser cannot read Location

Inspect the actual response in the Network panel. If the header is present but JavaScript reads null, check Access-Control-Expose-Headers and the server's CORS configuration.

### Treating Location as proof of authorization

Location specifies a URI. It does not grant access. A GET request to that URI still has to pass authentication, authorization, and data checks like any other request.

## 10. Key takeaways

- Read the status code first, then decide how to process headers and body.
- **Location** typically indicates the URI of a newly created resource after **201 Created**.
- **Content-Type** describes the representation format in the response; HAL typically uses **application/hal+json**.
- **Accept** is the client's representation preference; **Content-Type** describes the body being sent or received.
- **Content-Location** and HAL **_links.self.href** have distinct roles and do not arbitrarily replace Location.
- **ETag**, **Last-Modified**, **Cache-Control**, and **Vary** support validators and caching when provided by the server.
- Browsers require **Access-Control-Expose-Headers** for JavaScript to read response headers that are not exposed by default.
- Headers do not replace the body, hypermedia, validation, or security; read them together to understand the full response.
