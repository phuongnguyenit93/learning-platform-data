# Creating Resources via Location and Managing Resource URIs in Spring Data REST

When a client creates a new resource via Spring Data REST, the request is typically sent as an HTTP POST to a collection resource. The server creates the entity, persists it to the repository, and returns a response indicating the new resource was created. The **Location** header provides the URI of the new resource so the client can subsequently read, update, or delete the exact item resource.

Clients should take the URI from the Location header or the self link in the HAL representation returned by the server. Do not construct URIs from IDs or assume a repository's URL structure, because base paths, path mappings, identifier mappings, and export configurations can change.

## 1. Resource creation flow with POST

Suppose Spring Data REST exports the Person repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

The client sends POST to the collection resource:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com"
}
~~~

Spring Data REST binds the JSON into the entity, saves it via the repository, and returns a response to the client. On successful creation, the response typically uses status **201 Created** with a Location header pointing to the new item resource.

Example:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
Content-Type: application/hal+json
~~~

The URI in Location is the address the client can use to access the newly created resource. The value /people/42 is only an example; the actual ID and path are determined by the application and Spring Data REST.

## 2. Location is the URI of the new resource

The Location header has special meaning in a resource creation response. With status 201 Created, it identifies the primary resource created by the request.

Example:

~~~http
Location: https://api.example.com/people/42
~~~

The client can store this URI as the identifier of the newly created resource and use it for subsequent requests:

~~~http
GET /people/42
Accept: application/hal+json
~~~

~~~http
PATCH /people/42
Content-Type: application/json

{
  "lastName": "Tran"
}
~~~

~~~http
DELETE /people/42
~~~

In real applications, clients should use the exact URI received from Location or resolve a relative URI against the request URI. Do not simply extract the number 42 and append it to a guessed base URL.

### Location can be a relative URI

HTTP allows Location to contain a URI-reference. If the value is not an absolute URI, the client must resolve it against the request URI according to URI resolution rules.

For example, a request is sent to:

~~~text
https://api.example.com/v1/people
~~~

and the response includes:

~~~http
Location: /v1/people/42
~~~

The client resolves Location to:

~~~text
https://api.example.com/v1/people/42
~~~

Use a URI builder or an HTTP library that supports URI resolution to handle scheme, host, port, context path, and slashes properly.

## 3. Reading Location in a Java client

With Spring RestClient, the client can retrieve the response entity and read the header:

~~~java
RestClient restClient = RestClient.create();

ResponseEntity<Void> response = restClient.post()
    .uri("https://api.example.com/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(personRequest)
    .retrieve()
    .toBodilessEntity();

URI location = response.getHeaders().getLocation();

if (location == null) {
    throw new IllegalStateException(
        "Create response did not contain a Location header"
    );
}
~~~

If you need the response body, use a body type matching the representation returned by the server:

~~~java
ResponseEntity<PersonRepresentation> response =
    restClient.post()
        .uri("https://api.example.com/people")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .body(personRequest)
        .retrieve()
        .toEntity(PersonRepresentation.class);

URI location = response.getHeaders().getLocation();
~~~

The Java type receiving the body must match the HAL representation and the client's Jackson/HATEOAS configuration. If you only need the URI to continue, you can read Location without deserializing the entire body.

With WebClient, Location can be read from the response headers:

~~~java
Mono<URI> createdLocation = webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(personRequest)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            URI location = response.headers()
                .asHttpHeaders()
                .getLocation();

            if (location == null) {
                return Mono.error(
                    new IllegalStateException("Missing Location header")
                );
            }

            return Mono.just(location);
        }

        return response.createException()
            .flatMap(Mono::error);
    });
~~~

This snippet illustrates reading the header; in production applications, handle specific status codes per the API contract rather than treating every 2xx response as a newly created resource.

## 4. Using Location to read the newly created resource

After receiving Location, the client can GET that URI to fetch the latest representation:

~~~java
PersonRepresentation created =
    restClient.get()
        .uri(location)
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .body(PersonRepresentation.class);
~~~

This approach is useful when:

- The POST response returns no body.
- The client needs the full representation after the server applies default values or business logic.
- The server generates IDs, timestamps, or derived attributes.
- The client wants the association links and metadata published by Spring Data REST.

Do not assume the POST body always contains enough data to build client state. Location identifies the item resource's address; a subsequent GET lets the client read the representation under the current contract.

## 5. Location and self link in HAL

Spring Data REST typically returns representations in HAL. In the response, _links.self.href also points to the item resource.

Example:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
Content-Type: application/hal+json
~~~

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "person": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Clients can use the self link in the body or Location in the header to locate the item resource. When both are present, they typically point to the same primary resource; use the URI published by the server instead of assembling a different one.

HAL links may also include relations such as address, orders, or profile. Those links let the client navigate to related associations or metadata after creating the entity.

### Location and self link have closely related roles in different places

| Element | Location | Role |
|---|---|---|
| Location | HTTP response header | URI of the resource created by the request |
| _links.self.href | HAL response body | URI to access the current resource |
| _links.<rel>.href | HAL response body | URI of a related resource or capability |

Clients can use Location to store the URI even without deserializing HAL. If hypermedia navigation is needed, read the self link and relations in the body.

## 6. Distinguishing Location from Content-Location

These two headers have similar names but different meanings:

- **Location** in a 201 response identifies the newly created resource.
- **Content-Location** identifies the URI of the representation sent in the message body, according to the corresponding HTTP semantics.

Example resource creation response:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.com/people/42
Content-Type: application/hal+json
~~~

Location is the header clients must use to locate the new resource.

Do not use Content-Location in place of Location simply because the response has a body. Follow HTTP semantics and the API contract published by the server.

Location can also appear in 3xx redirect responses as the redirect target URI. Clients need to inspect the status code to interpret the header in each case.

## 7. Response body of resource creation

Spring Data REST can be configured to return or omit a representation body after POST. RepositoryRestConfiguration includes options controlling whether bodies are returned on create and update.

Therefore, clients should not rely on the assumption that POST always returns a HAL body or always returns only a Location header. Verify the API configuration and handle both cases:

- Location present and body present: the client can use the body immediately or GET the URI again.
- Location present but empty body: the client GETs the URI to retrieve the representation.
- Body has a self link: the client can use that link as the resource URI.
- Both Location and self link missing: the response does not provide enough information for the client to identify the new URI via the standard flow; handle per the API contract or raise an error.

When changing return-body configuration, check existing clients because they may depend on the status, headers, or body of the POST response.

## 8. CORS and reading Location in the browser

An application running in a browser may send POST to an API on another origin. Browsers enforce CORS and do not expose every response header to JavaScript by default.

For JavaScript to read Location, the server may need to expose the header:

~~~http
Access-Control-Expose-Headers: Location
~~~

For example, Spring MVC/Spring Security configuration must allow the origin and expose headers per the application's policy. Adding Access-Control-Expose-Headers alone does not replace Access-Control-Allow-Origin, preflight handling, or authorization.

If the browser receives a 201 response but response.headers.get("Location") returns null, check the exposed CORS headers in the actual response before concluding the server did not send Location.

JavaScript example:

~~~javascript
const response = await fetch("https://api.example.com/people", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/hal+json"
  },
  body: JSON.stringify({
    firstName: "An",
    lastName: "Nguyen"
  })
});

const location = response.headers.get("Location");

if (!response.ok) {
  throw new Error("Create request failed");
}

if (!location) {
  throw new Error("Location header is not available");
}

const createdResponse = await fetch(location, {
  headers: { "Accept": "application/hal+json" }
});
~~~

This code assumes the server has configured CORS for the client's origin and exposed Location. Production clients also need to handle credentials, network errors, redirects, and specific status codes.

## 9. Managing URIs after creation

After successful creation, the client should persist the server-supplied URI alongside the corresponding client-side data.

Helpful principles:

- Store the URI as a resource identifier, not just the raw ID if the API can use custom URIs.
- Use the URI received from Location or the self link for subsequent requests.
- Do not concatenate base URL and ID as strings when the server already provides links.
- When switching environments or changing base paths, let the client discover new links from responses.
- Do not assume URIs will never change if the API supports redirects or URI migration.
- Validate scheme and host before the client trusts a URI from outside the application's trusted scope.

In multi-tenant applications or multi-host APIs, URIs can encode routing information. Storing the URI prevents the client from having to re-implement routing rules.

## 10. Retrying POST and avoiding duplicate creation

Resource-creating POST requests are generally not idempotent. If a client sends POST and times out before receiving the response, the client cannot know for sure whether the server created the entity.

Do not blindly resend POST. The first request may have created the resource while the response was lost; a second request would create another record.

Ways to handle this:

- If a response is received, use Location to identify the created resource.
- On timeout, check state using a business key or request correlation identifier if supported by the API.
- For workflows requiring safe retries, design an idempotency key and persist processing results on the server.
- Enforce a unique constraint on the business key if the domain prohibits duplicates.
- Design client retries around the API contract rather than inferring outcomes from status codes or network exceptions.

Location helps manage the URI after a successful response is received; it does not by itself solve the case where the response is lost before the client can read the header.

## 11. Creating resources via a custom controller

If the application uses a custom controller instead of standard repository endpoints, the controller must explicitly return the proper status and Location semantics.

Example:

~~~java
@PostMapping("/people")
public ResponseEntity<Person> create(@RequestBody PersonRequest request) {
    Person saved = personService.create(request);

    URI location = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .path("/{id}")
        .buildAndExpand(saved.getId())
        .toUri();

    return ResponseEntity.created(location).body(saved);
}
~~~

ResponseEntity.created(location) produces a 201 Created response and sets Location. The URI is built from the current request and the saved entity's ID.

For custom endpoints integrated into Spring Data REST, consider using @RepositoryRestController and appropriate assemblers/representations so responses follow the API's hypermedia contract. If the controller returns a custom DTO or representation, clearly define the URI and links that clients are allowed to use.

Do not build Location from the ID before the entity is saved if the ID is database-generated. Create the entity, persist it successfully, then read the identifier and build the URI.

## 12. Handling errors and unexpected responses

Clients should distinguish these cases:

- **201 Created:** a new resource was created; read Location if present.
- **200 OK or 204 No Content:** not the standard 201 resource creation response; verify the custom API contract.
- **400 Bad Request:** invalid body or input data.
- **401/403:** client is unauthenticated or lacks creation permission.
- **409 Conflict:** may occur when a business key or constraint conflicts.
- **415 Unsupported Media Type:** Content-Type is not supported by the endpoint.
- **5xx or timeout:** outcome may be uncertain if the server processed the request but the response did not reach the client.

Do not assume every 2xx status carries Location. Check status codes and headers per operation, and handle empty response bodies.

## 13. Testing Location and URI lifecycle

Write HTTP integration tests to confirm the server returns valid URIs and clients can use them.

Cases to verify:

1. POST valid data to the collection resource.
2. Assert status is 201 Created per the API contract.
3. Assert the response has Location pointing to the new item resource.
4. If the body contains HAL, assert _links.self.href matches Location.
5. GET the URI from Location and verify the newly created entity can be read.
6. Verify responses when configured not to return a body.
7. Test base path, context path, reverse proxy, and relative URIs if configured by the application.
8. Verify CORS so browser clients can read Location.
9. Test missing Location or a body without a self link.
10. Test timeouts and retries to prevent duplicate resource creation.
11. Verify custom controllers returning ResponseEntity.created(location) produce the right header.
12. Verify clients do not assemble URIs from IDs when the server publishes official URIs.

## 14. Implementation workflow

1. Identify the collection resource the client uses for POST.
2. Send the request with appropriate Content-Type and Accept headers.
3. Check the creation status code per the API contract.
4. Read the Location header and store the new URI.
5. If the body contains HAL, read the self link and needed relations.
6. If the body is empty or the client needs fresh data, GET the URI from Location.
7. If the client runs in a browser, configure CORS to expose Location.
8. Establish a retry/idempotency policy for timeout scenarios.
9. Test status, Location, self link, and the subsequent GET request.

## 15. Key takeaways

- POST to a collection resource is the standard way to create entities via Spring Data REST.
- Successful creation responses typically return 201 Created and a Location header pointing to the new item resource.
- Clients should use Location or the HAL self link instead of constructing URLs from IDs.
- Location can be a relative URI and must be resolved against the request URI.
- Content-Location and Location have different semantics.
- Response bodies after POST depend on configuration; clients must handle empty bodies.
- Browser clients require the server to expose Location via CORS so JavaScript can read the header.
- POST is generally not idempotent; timeouts and retries can create duplicate records without an idempotency mechanism.
- Custom controllers can use ResponseEntity.created(location) to return 201 and Location.
- Test headers, HAL self links, and reading back the resource using the received URI.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Framework — ResponseEntity API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html)
- [HTTP Semantics — RFC 9110, 201 Created and Location](https://www.rfc-editor.org/rfc/rfc9110.html)
- [MDN — Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Expose-Headers)
