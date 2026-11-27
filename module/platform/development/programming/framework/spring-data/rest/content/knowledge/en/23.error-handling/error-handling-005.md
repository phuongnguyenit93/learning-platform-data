# 406 Not Acceptable and 415 Unsupported Media Type When Accept or Content-Type Is Unsupported

## Objectives

Spring Data REST automatically publishes Spring Data repositories as REST resources. When a client calls a resource, the server must handle two separate tasks: choosing the representation to return to the client and reading the representation in the request body. These two tasks use two different HTTP headers:

- `Accept` describes the media types the client can receive in the response.
- `Content-Type` describes the media type of the request body the client is sending.

If the client requests a response representation that the resource does not provide, the server may return `406 Not Acceptable`. If the request body has a format unsupported by the method on the resource, the server may return `415 Unsupported Media Type`. Identifying the right header and resource type is the first step to fixing the error.

## 1. Distinguishing Accept and Content-Type

| Header | Used for | Example |
|---|---|---|
| `Accept` | Client declares desired response format | `Accept: application/hal+json` |
| `Content-Type` | Client declares request body format | `Content-Type: application/json` |
| `Content-Encoding` | Client declares encoding/compression applied to the sent representation | `Content-Encoding: gzip` |

For example, when creating a person via `POST /people`:

- `Content-Type: application/json` indicates the body is JSON so Spring reads and converts it into a domain object.
- `Accept: application/hal+json` indicates the client wants to receive the response as HAL JSON.

Do not use `Accept` to declare the format of the outgoing body. Likewise, do not use `Content-Type` to request a response format.

Spring MVC checks the `Accept` header by default to determine the response media type. Spring Data REST uses HAL as the default hypermedia representation; repository resources also support `application/json` per official documentation.

## 2. 406 Not Acceptable: response does not satisfy Accept

According to HTTP Semantics (RFC 9110, Section 15.5.7), `406 Not Acceptable` means the target resource does not have a current representation that would be acceptable to the user agent according to the proactive negotiation header fields received in the request, and the server is unwilling to supply a default representation.

In Spring MVC, this error is typically associated with `HttpMediaTypeNotAcceptableException`. The handler cannot produce a response matching the media type requested by the client.

Example of a client accepting only XML:

```http
GET /people HTTP/1.1
Host: localhost:8080
Accept: application/xml
```

If the collection resource only supports JSON/HAL JSON, `application/xml` is incompatible and the request may receive `406`.

Fix the request using a media type supported by the endpoint:

```http
GET /people HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
```

Or use `Accept: application/json` if the client wants a plain JSON representation. Spring Data REST uses HAL by default for JSON representations; you can inspect `RepositoryRestConfiguration.useHalAsDefaultJsonMediaType()` to understand this behavior.

Note: an empty response body after a successful request is not automatically a 406. For `PUT` and `DELETE`, Spring Data REST defaults to using the presence of `Accept` to decide whether to return a body; configuring `setReturnBodyOnUpdate(...)` and `setReturnBodyOnDelete(...)` changes the corresponding behavior. Read the status code and `Location` header before concluding the request failed.

## 3. 415 Unsupported Media Type: request body is not supported

According to RFC 9110, Section 15.5.16, `415 Unsupported Media Type` indicates the origin server is refusing to service the request because the payload is in a format not supported by this method on the target resource. The issue may come from `Content-Type`, `Content-Encoding`, or direct content inspection by the server.

In Spring MVC, the error is typically tied to `HttpMediaTypeNotSupportedException` when the request handler cannot read the media type sent by the client. This commonly happens with `POST`, `PUT`, or `PATCH`.

Example of sending XML to a collection resource that does not support XML:

```http
POST /people HTTP/1.1
Host: localhost:8080
Content-Type: application/xml
Accept: application/hal+json

<person><name>Ada</name></person>
```

If the resource only supports JSON, the server may return `415`. Send actual JSON and declare the proper media type:

```http
POST /people HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/hal+json

{"name":"Ada"}
```

Merely changing the header to `application/json` while the body is still XML is not a valid fix. The `Content-Type` value must accurately describe the body format.

## 4. Media types supported by Spring Data REST

Supported media types depend on the resource type and HTTP method. Do not infer one endpoint's contract from another endpoint in the same application.

| Resource | Method | Documented media types |
|---|---|---|
| Collection | `GET` | `application/hal+json`, `application/json` |
| Collection | `POST` | `application/hal+json`, `application/json` |
| Item | `GET` | `application/hal+json`, `application/json` |
| Item | `PUT` | `application/hal+json`, `application/json` |
| Item | `PATCH` | `application/hal+json`, `application/json`, `application/patch+json`, `application/merge-patch+json` |
| Association | `GET` | `application/hal+json`, `application/json` |
| Association | `PUT` | `text/uri-list` |
| Association (collection association) | `POST` | `text/uri-list` |
| Search/query resource | `GET` | `application/hal+json`, `application/json` |

Important cases:

- `POST /people` creates an entity, so the JSON body can use `Content-Type: application/json`.
- `PUT /people/1` replaces item state; `PATCH /people/1` partially updates it.
- `PATCH` can use JSON Patch (`application/patch+json`) or JSON Merge Patch (`application/merge-patch+json`). The body must follow the structure and semantics of the corresponding media type.
- `PUT /people/1/manager` binds the referenced resource to the association. The request body is a URI or list of URIs, so it uses `Content-Type: text/uri-list`.
- `POST` to a collection association adds a new element and also uses `text/uri-list`.
- `text/uri-list` is not an alternative body format for JSON when creating an entity on a collection resource.

Example association request:

```http
PUT /people/1/manager HTTP/1.1
Host: localhost:8080
Content-Type: text/uri-list

http://localhost:8080/managers/2
```

The path `/people/1/manager` is only an example. The association path name depends on the domain property and repository export configuration.

The matrix above is based on current Spring Data REST documentation. Custom controllers, custom converters, repository export configurations, and library versions may alter actual behavior.

## 5. Examples testing with cURL

Adjust the host, collection path, and JSON properties for your application.

### 5.1. GET collection with HAL JSON

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people
```

Expected: successful response (typically `200 OK`) with a HAL JSON-compatible `Content-Type`.

### 5.2. Triggering 406 with an unsupported Accept

```bash
curl -i -H "Accept: application/xml" http://localhost:8080/people
```

Expected: `406 Not Acceptable` if the endpoint does not provide XML. Fix with:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people
```

### 5.3. POST entity using JSON

```bash
curl -i -X POST http://localhost:8080/people   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{"name":"Ada"}'
```

Expected: resource is created, typically `201 Created`. Response body and `Location` header depend on endpoint behavior and configuration.

### 5.4. Triggering 415 with an unsupported Content-Type

```bash
curl -i -X POST http://localhost:8080/people   -H "Content-Type: application/xml"   -H "Accept: application/hal+json"   --data '<person><name>Ada</name></person>'
```

Expected: `415 Unsupported Media Type` if the collection resource does not accept XML. Fix by sending actual JSON as in example 5.3.

### 5.5. PATCH using JSON Merge Patch

```bash
curl -i -X PATCH http://localhost:8080/people/1   -H "Content-Type: application/merge-patch+json"   -H "Accept: application/hal+json"   --data '{"name":"Ada Lovelace"}'
```

Use `application/merge-patch+json` when the body conforms to JSON Merge Patch. If using JSON Patch, declare `application/patch+json` and send an array of operations in JSON Patch format.

### 5.6. PUT association using a URI list

```bash
curl -i -X PUT http://localhost:8080/people/1/manager   -H "Content-Type: text/uri-list"   --data 'http://localhost:8080/managers/2'
```

If you send a JSON object to an association resource, the request may receive 415 even though JSON is supported on the collection resource. The two resources have different media type contracts.

## 6. Diagnostic workflow

1. **Collect the actual request.** Record URL, method, `Accept`, `Content-Type`, `Content-Encoding`, and body. Use `curl -v`, HTTP client logs, or reverse proxy logs to see which headers actually reach the application.
2. **Identify the resource.** Distinguish collection, item, association, search/query resource, and custom controller. Inspect links from the API root or HAL responses to determine the resource URL.
3. **If 406, check Accept.** Compare each media type requested by the client against the response media types of the method/resource. Try `application/hal+json` to test a HAL response. For GET without a body, changing `Content-Type` does not fix response negotiation.
4. **If 415, check Content-Type and body.** Confirm the actual body matches the declared format. A JSON body needs a JSON converter; XML needs an XML converter and an endpoint configured to support XML. Also check `Content-Encoding` if the request is compressed.
5. **Check associations.** If the URL is an association sub-resource, verify whether the method requires `text/uri-list`. Do not use a JSON entity body for URI linking operations.
6. **Check custom mappings.** For self-written controllers, check `consumes` and `produces` on `@RequestMapping`. `consumes` constrains the request body media type; `produces` constrains the response representation.
7. **Check message converters.** Spring MVC uses `HttpMessageConverter` to read request bodies and write responses. Check registered converters, Java types, supported media types, and `WebMvcConfigurer` configuration.
8. **Verify versions.** Check the actual Spring Data REST and Spring Framework versions in the dependency tree; consult documentation for that exact version. Do not assume one version's configuration applies verbatim to another.
9. **Distinguish status codes.** `400 Bad Request` usually indicates an invalid or unparseable body; `404 Not Found` indicates the resource/path does not exist; `405 Method Not Allowed` indicates the method is not supported or not exported. Changing media types does not fix these errors.

## 7. Configuring default media type and content negotiation

Spring Data REST provides `RepositoryRestConfiguration.setDefaultMediaType(...)` to select the default media type when a request does not explicitly specify one. Example configuring HAL JSON via `RepositoryRestConfigurer`:

```java
@Configuration
class RestMediaTypeConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setDefaultMediaType(
                MediaType.parseMediaType("application/hal+json"));
    }
}
```

Required imports depend on the package structure of the Spring Data REST version in use, including `Configuration`, `RepositoryRestConfigurer`, `RepositoryRestConfiguration`, `CorsRegistry`, and `MediaType`.

Configuring the default media type only determines the fallback when a request does not specify a media type. It does not automatically enable XML, does not make an explicit incompatible `Accept` valid, and does not change the `text/uri-list` contract of association resources.

In Spring MVC, you can customize how the response media type is determined via `WebMvcConfigurer.configureContentNegotiation(ContentNegotiationConfigurer)`. By default, only the `Accept` header is checked. Declaring aliases or extension mappings for XML does not automatically register an XML message converter, nor does it guarantee every endpoint can serialize/deserialize XML.

For custom endpoints, you can declare the contract explicitly:

```java
@PostMapping(
    path = "/imports",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<ImportResult> importData(@RequestBody ImportRequest request) {
    // Handle the request.
}
```

In the example, `consumes` states that the request body must be JSON; `produces` describes the response representation. This configuration applies to application-managed controllers and does not replace the media type matrix of Spring Data REST repository resources.

## 8. Testing 406 and 415 with MockMvc

`MockMvc` executes requests through Spring MVC request handling using mock requests/responses, without starting a real HTTP server. You can use `@SpringBootTest` and `@AutoConfigureMockMvc` to test repository resources exported in the application context.

Example assuming the application has a collection resource `/people`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryMediaTypeTests {

    private static final MediaType HAL_JSON =
            MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsHalJsonWhenRequested() throws Exception {
        mockMvc.perform(get("/people").accept(HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(HAL_JSON));
    }

    @Test
    void rejectsUnsupportedAcceptHeader() throws Exception {
        mockMvc.perform(get("/people").accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/people")
                        .accept(HAL_JSON)
                        .contentType(MediaType.APPLICATION_XML)
                        .content("<person><name>Ada</name></person>"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
```

Key static imports and types:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Run tests with `./mvnw test` or `./gradlew test` depending on the project's build tool. Adjust paths and JSON fields for the actual domain model. If receiving 404 or 405 instead of the expected status, verify that the repository is exported, the collection path is correct, and the method is enabled. If GET returns 200 with a different content type than expected, check HAL configuration and converters before changing assertions.

Add integration tests for your application's specific contracts:

- POST collection with JSON body and `Content-Type: application/json`.
- PUT item with JSON body.
- PATCH item with JSON Patch or JSON Merge Patch with a semantically valid body.
- PUT association with `Content-Type: text/uri-list`.
- POST collection association with `Content-Type: text/uri-list`.
- Request with an unsupported Accept to verify 406.
- Request with an unsupported Content-Type to verify 415.

## 9. Troubleshooting checklist

- [ ] Recorded the actual request method, URL, and headers.
- [ ] Identified whether the resource is a collection, item, association, or custom controller.
- [ ] For 406, checked `Accept` and supported response media types.
- [ ] For 415, checked `Content-Type`, `Content-Encoding`, and the actual body format.
- [ ] Confirmed the body matches the declared media type.
- [ ] Used `text/uri-list` for association PUT/POST when required by the endpoint.
- [ ] Reviewed `consumes`/`produces`, message converters, and content negotiation config.
- [ ] Checked dependency versions and matching documentation.
- [ ] Tested valid and invalid requests with MockMvc or HTTP integration tests.

## Official documentation

1. [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): supported methods and media types for collection, item, association, search, and query resources.
2. [Spring Data REST — Domain Object Representations](https://docs.spring.io/spring-data/rest/reference/representations.html): JSON/HAL representations and response representations.
3. [Spring Data REST — Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): configuring repository REST via `RepositoryRestConfigurer`.
4. [RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): configuring default media type and HAL.
5. [Spring Framework — Content Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html): how Spring MVC determines requested media types and configures content negotiation.
6. [Spring Framework — Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converters for reading request bodies and writing response bodies.
7. [HttpMediaTypeNotAcceptableException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/HttpMediaTypeNotAcceptableException.html): exception when no acceptable response can be generated.
8. [HttpMediaTypeNotSupportedException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/HttpMediaTypeNotSupportedException.html): exception when the handler does not support the request media type.
9. [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): executing and verifying Spring MVC requests in tests.
10. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): definitions of Content-Type, 406 (Section 15.5.7), and 415 (Section 15.5.16).

*Reference documentation verified on 2026-11-11. When applying, select documentation matching the exact Spring Data REST/Spring Framework release line in your project's dependencies.*