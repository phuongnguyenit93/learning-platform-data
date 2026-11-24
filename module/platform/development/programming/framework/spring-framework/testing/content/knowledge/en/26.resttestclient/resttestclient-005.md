# Preparing URI, Headers, and Body Before `exchange()`

`RestTestClient` provides a synchronous, fluent API to send HTTP requests and verify responses in Spring tests. Before calling `exchange()`, the test needs to fully describe the request: HTTP method, URI, query parameters, headers, and body if present. `exchange()` is the point where the request is executed; only afterwards does the test move on to assertions like `expectStatus()`, `expectHeader()`, and `expectBody()`.

Preparing requests explicitly helps tests accurately reflect the endpoint's HTTP contract. The URI identifies the resource and parameters; headers describe metadata such as body format, desired response format, authentication info, or correlation ID; the body carries business data that the server needs to process.

## 1. Structure of a RestTestClient Request

A basic request looks like this:

```java
restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-100")
        .body(new CreateProductRequest("Notebook", 12.5))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(ProductView.class)
        .value(product -> assertThat(product.name()).isEqualTo("Notebook"));
```

The request chain can be divided into two parts:

| Part | Operations | Purpose |
| --- | --- | --- |
| Request preparation | `post()`, `uri()`, `header()`, `accept()`, `contentType()`, `body()` | Define the exact content to send |
| Execution and verification | `exchange()`, `expectStatus()`, `expectHeader()`, `expectBody()` | Send the request and verify the response |

Before `exchange()`, methods are configuring a request. Only when `exchange()` is called does the client execute the request and receive the response. Do not split a single request into multiple `exchange()` calls if the goal is to test a single business operation.

`RestTestClient` is a synchronous API introduced in Spring Framework 7.0. Examples in this document use the `RestClient`-style `body(...)` API. If the project is using Spring Framework 6.x, use APIs available in that version such as `MockMvc`, `WebTestClient`, or corresponding testing tools; merely changing imports cannot create an API not present in the dependencies.

## 2. Choosing the HTTP Method Before Preparing the URI

The client starts with the method matching the HTTP operation:

```java
restTestClient.get()
restTestClient.head()
restTestClient.post()
restTestClient.put()
restTestClient.patch()
restTestClient.delete()
restTestClient.options()
```

The method is part of the endpoint contract. For example:

| Method | Common purpose | Has request body? |
| --- | --- | --- |
| `GET` | Read a resource | Typically no |
| `HEAD` | Read resource metadata | No |
| `POST` | Create a resource or execute a command | Often yes |
| `PUT` | Replace or update an entire resource | Usually yes |
| `PATCH` | Partially update a resource | Usually yes |
| `DELETE` | Delete a resource | Typically no |
| `OPTIONS` | Query supported methods or capabilities | Typically no |

GET example:

```java
restTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk();
```

DELETE example:

```java
restTestClient.delete()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isNoContent();
```

Not every method needs a body. If a request has no body, `Content-Type` usually does not need to be set. For requests with a body, choose the method and media type matching the API contract.

## 3. Preparing the URI with Paths and URI Templates

`uri(...)` specifies the endpoint the request will be sent to. When the client already has a `baseUrl`, relative paths can be used:

```java
RestTestClient restTestClient = RestTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

restTestClient.get()
        .uri("/api/products")
        .exchange();
```

URI templates allow placing variables in the path instead of manual string concatenation:

```java
restTestClient.get()
        .uri("/api/products/{id}", 42)
        .exchange()
        .expectStatus().isOk();
```

A map can be passed for multiple variables:

```java
Map<String, Object> variables = Map.of(
        "category", "stationery",
        "id", 42);

restTestClient.get()
        .uri("/api/categories/{category}/products/{id}", variables)
        .exchange();
```

URI templates separate URL structure from input data. The URI builder can encode variables according to proper URI rules; this avoids many bugs caused by spaces, `&`, `/`, or Unicode characters when concatenating strings manually.

If you need to pass a pre-built URI, you can use `URI`:

```java
URI uri = URI.create("http://localhost:8080/api/products/42");

restTestClient.get()
        .uri(uri)
        .exchange();
```

Absolute URIs are often useful when testing connections to a real server or when explicitly specifying scheme, host, and port. When tests bind to mock infrastructure, use a base URL and paths matching the client configuration.

## 4. Adding Query Parameters with URI Builder

Query parameters are the part after `?` in a URI, commonly used for searching, filtering, sorting, or pagination. You can build a URI using a `UriBuilder` callback:

```java
restTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/products")
                .queryParam("category", "stationery")
                .queryParam("page", 0)
                .queryParam("size", 20)
                .build())
        .exchange()
        .expectStatus().isOk();
```

When path variables are needed together with query parameters:

```java
restTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/categories/{category}/products")
                .queryParam("sort", "name,asc")
                .queryParam("active", true)
                .build("stationery"))
        .exchange();
```

If a query value contains special characters, let the URI builder perform encoding. For example, the keyword `blue pen & pencil` must be properly encoded so `&` is not misinterpreted as a separator between two parameters.

Do not concatenate strings manually like this:

```java
String uri = "/api/search?q=" + keyword + "&page=" + page;
```

String concatenation easily produces invalid URIs when `keyword` contains spaces, `&`, `#`, or characters requiring encoding. The URI builder represents each component separately and handles encoding consistently.

## 5. Setting Base URL and Distinguishing Relative/Absolute URIs

Base URL is configured when creating the client, while `uri(...)` usually only needs the path:

```java
RestTestClient client = RestTestClient.bindToServer()
        .baseUrl("https://api.example.test")
        .build();

client.get()
        .uri("/v1/products")
        .exchange();
```

This keeps tests from repeating host and port on every request. Base URL can be configured based on the test environment, such as the random port of a running server.

With an absolute URI, scheme and authority are already inside the URI:

```java
client.get()
        .uri(URI.create("https://api.example.test/v1/products"))
        .exchange();
```

Be consistent in how base URL and absolute URIs are used within a test suite. If both base URL is configured and an absolute URI is supplied, the absolute URI determines the target host of the request. This is especially important when the client has interceptors, authentication, or host-dependent routing.

## 6. Setting Request Headers

Headers carry HTTP message metadata. You can set a single header with `.header(...)`:

```java
restTestClient.get()
        .uri("/api/products/42")
        .header("X-Request-Id", "req-100")
        .header("X-Client", "catalog-test")
        .exchange();
```

If you need to set multiple headers at once, use `.headers(...)` to work with `HttpHeaders`:

```java
restTestClient.get()
        .uri("/api/products/42")
        .headers(headers -> {
            headers.set("X-Request-Id", "req-100");
            headers.set("X-Client", "catalog-test");
            headers.setBearerAuth("test-access-token");
        })
        .exchange();
```

`set(...)` sets or replaces a header's value; `add(...)` appends a value to the existing list. Distinguish these two operations when a header allows multiple values, such as `Accept` or certain custom headers.

You can pass multiple values for the same header:

```java
restTestClient.get()
        .uri("/api/products")
        .header("X-Feature", "search", "recommendations")
        .exchange();
```

Only add headers that the endpoint or client contract actually requires. Adding many unrelated headers makes tests harder to read and can hide unintended dependencies.

## 7. Distinguishing `Accept` and `Content-Type`

These two headers are often prepared together on a request, yet describe two different data directions:

| Header | Description | Setup API |
| --- | --- | --- |
| `Accept` | Media type the client wants to receive in the response | `.accept(MediaType...)` |
| `Content-Type` | Media type of the request body being sent | `.contentType(MediaType)` |

Example sending JSON and requesting JSON:

```java
restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreateProductRequest("Notebook", 12.5))
        .exchange();
```

In the example, `Content-Type` indicates the request body is JSON; `Accept` indicates the client wants the response in JSON. Setting `Accept` does not automatically turn the body into JSON, and setting `Content-Type` does not force the server to return JSON.

Multiple response media types can be requested:

```java
restTestClient.get()
        .uri("/api/products/42")
        .accept(MediaType.APPLICATION_JSON, MediaType.APPLICATION_XML)
        .exchange();
```

The server chooses a representation based on `Accept`, `produces` mappings, and configured converters. If the endpoint does not support any media type the client accepts, the response may be 406 Not Acceptable.

For requests without a body such as GET, usually only `Accept` is needed if you want to constrain the response format. There is no need to add `Content-Type: application/json` when not sending a JSON body.

## 8. Authentication Headers and Request Metadata

APIs may require authentication information or metadata to process requests. Using `headers(...)` lets you configure related values in one place:

```java
restTestClient.get()
        .uri("/api/me")
        .headers(headers -> {
            headers.setBearerAuth("test-token");
            headers.set("X-Correlation-Id", "corr-202");
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .exchange()
        .expectStatus().isOk();
```

If the API uses Basic authentication, you can set the corresponding header:

```java
restTestClient.get()
        .uri("/api/private")
        .headers(headers -> headers.setBasicAuth("test-user", "test-password"))
        .exchange()
        .expectStatus().isOk();
```

Authentication values in tests should be dummy credentials dedicated to the test environment. If the application uses Spring Security, headers are only one part of the request; tests need to configure an authentication provider or corresponding test security context to verify real security behavior.

Headers can be used for conditional requests:

```java
restTestClient.get()
        .uri("/api/products/42")
        .header(HttpHeaders.IF_NONE_MATCH, "\"product-42-v1\"")
        .exchange()
        .expectStatus().isNotModified();
```

This example assumes the endpoint supports ETag and returns 304 when the resource has not changed. Conditional headers should only be included in tests when the endpoint has a corresponding contract.

## 9. Sending an Object as the Body

For JSON requests, a DTO can be passed directly via `.body(...)`:

```java
CreateProductRequest request = new CreateProductRequest("Notebook", 12.5);

restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(request)
        .exchange()
        .expectStatus().isCreated();
```

The client selects an appropriate `HttpMessageConverter` to serialize the object into an HTTP body. For JSON, test applications typically need Jackson and a JSON converter. The Java type must be supported by the converter, such as a DTO, record, map, or collection.

`Content-Type` is very important when serializing objects. If the body is an object but the media type is unsuitable or there is no converter to write that type, the request may not be built as intended and the client may throw a message-writing error before the request reaches the server.

You can send a string or byte array when you want exact control over the body:

```java
String json = """
        {"name":"Notebook","price":12.5}
        """;

restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(json)
        .exchange();
```

Or:

```java
byte[] payload = json.getBytes(StandardCharsets.UTF_8);

restTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(payload)
        .exchange();
```

When sending a string or byte array, the test is responsible for ensuring the content actually conforms to the declared format. Setting `Content-Type: application/json` does not automatically validate whether the string is valid JSON.

## 10. Sending URL-Encoded Forms

URL-encoded forms are commonly used when an endpoint accepts data in `application/x-www-form-urlencoded` format. You can prepare the data using `MultiValueMap`:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("username", "lan");
form.add("password", "example-password");

restTestClient.post()
        .uri("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(form)
        .exchange()
        .expectStatus().is3xxRedirection();
```

`MultiValueMap` allows one key to have multiple values, suitable for forms with checkboxes sharing the same name or repeated fields. `FormHttpMessageConverter` can serialize the map into a form body when registered.

Do not send a form map with `Content-Type: application/json`. The Java data type may be a map in both cases, but the media type determines how the converter represents the data over HTTP.

## 11. Sending Multipart Data and File Uploads

For file uploads, requests typically use `multipart/form-data`. You can build multipart data using `MultiValueMap<String, Object>`:

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("description", "Product manual");
parts.add("file", new ByteArrayResource(
        "manual content".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "manual.txt";
    }
});

restTestClient.post()
        .uri("/api/documents")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(parts)
        .exchange()
        .expectStatus().isCreated();
```

`ByteArrayResource` provides file contents in memory; override `getFilename()` so the multipart part has a filename. You can use `FileSystemResource` or `ClassPathResource` when fixture files already exist in test resources.

Do not set a boundary manually when the client/converter is building the multipart body. The boundary is part of the multipart `Content-Type` and must match the delimiter in the body; the converter needs to manage them in sync.

If the endpoint accepts multiple files or multiple parts with the same name, `MultiValueMap` allows adding multiple values for a single key. Verify part names, filenames, part content types, and file contents according to the endpoint contract.

## 12. Setting Conditional Headers and Repeated Values

Some headers can have multiple values or need to vary depending on the test scenario. Using `headers(...)` allows logic before sending:

```java
restTestClient.get()
        .uri("/api/products")
        .headers(headers -> {
            headers.setAccept(List.of(
                    MediaType.APPLICATION_JSON,
                    MediaType.APPLICATION_XML));
            headers.set("X-Client-Version", "2");
            if (includeExperimentalFeature) {
                headers.add("X-Feature", "experimental");
            }
        })
        .exchange();
```

`set(...)` replaces the header's list of values with a new value; `add(...)` appends a value. Use the right operation to avoid accidentally sending duplicate headers or wiping out values set by shared configuration.

When default headers come from interceptors or client configuration, identify which headers belong to shared configuration and which belong to the specific request. Tests should explicitly override when the contract requires a special value.

## 13. Combining URI, Headers, and Body in a Complete Example

Suppose an order creation endpoint accepts JSON, supports a correlation ID, and returns JSON along with a `Location` header:

```java
OrderCommand command = new OrderCommand(
        "customer-42",
        List.of(new OrderLine("BK-01", 2)));

restTestClient.post()
        .uri(uriBuilder -> uriBuilder
                .path("/api/customers/{customerId}/orders")
                .queryParam("notify", false)
                .build("customer-42"))
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers -> {
            headers.set("X-Correlation-Id", "order-test-001");
            headers.setBearerAuth("test-token");
        })
        .body(command)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectHeader().exists(HttpHeaders.LOCATION)
        .expectBody(OrderView.class)
        .value(order -> {
            assertThat(order.customerId()).isEqualTo("customer-42");
            assertThat(order.lines()).hasSize(1);
        });
```

The example clearly illustrates each part of the HTTP contract:

- The path variable identifies the customer who owns the order.
- The query parameter controls the notification option.
- `Content-Type` describes the request body as JSON.
- `Accept` requests a JSON response.
- The correlation ID supports request tracing.
- The bearer token represents the test's authentication credentials.
- The DTO is serialized into the request body.
- `exchange()` sends the request before inspecting the response.

## 14. Pitfalls to Avoid When Preparing Requests

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Building query strings by string concatenation | Malformed URI when data contains special characters | Use URI templates or `UriBuilder` |
| Confusing `Accept` with `Content-Type` | Server picks the wrong converter or returns 406/415 | `Accept` for response; `Content-Type` for request body |
| Sending a DTO without a suitable converter | Client cannot serialize the body | Add the required converter/codec and declare media type |
| Sending a form map with JSON media type | Body does not match the form contract | Use `APPLICATION_FORM_URLENCODED` |
| Creating a manual multipart boundary mismatched with the body | Server cannot parse multipart | Let the converter manage the boundary |
| Adding the same header multiple times unintentionally | Server receives unexpected multiple values | Use `set` to replace, `add` to append |
| Setting a body on GET when endpoint does not support it | Inconsistent behavior between client/server | Only send a body when the contract requires it |
| Calling `exchange()` before finishing configuration | Request executes with incomplete info | Complete URI, headers, and body before `exchange()` |
| Using an absolute URI with the wrong host | Request goes to a different target | Check base URL and target URI |

A common mistake is that a test only checks the response while sending requests unlike a real client. For example, a test sends a JSON object without `Content-Type`, whereas the production client always sends JSON. In that case, the test may fail to reproduce the real bug the endpoint encounters in production. Describe requests accurately according to the contract, including method, URI, media type, and required headers.

## 15. Principles for Organizing Request Specifications

1. Choose the HTTP method matching the endpoint's behavior.
2. Use URI templates for path variables and `UriBuilder` for complex query parameters.
3. Configure base URL once when possible, keeping request URIs short and clear.
4. Use `.header(...)` for simple headers and `.headers(...)` when manipulating multiple headers.
5. Distinguish `Accept` from `Content-Type`; only set Content-Type when the request has a body to describe.
6. Choose Java object, text, byte array, form map, or multipart map body according to the endpoint contract.
7. Ensure a suitable converter is present to serialize objects into the request body.
8. Complete all request preparation before calling `exchange()`.
9. Send one request per business action and chain assertions on that response.
10. When a test fails, inspect the actual request before concluding the bug is in the controller.

In `RestTestClient`, preparing the URI, headers, and body determines the exact request the server receives. The URI identifies the resource, headers describe metadata and media types, and the body carries the data to process. When these parts are configured explicitly before `exchange()`, the test becomes a clear specification of the HTTP contract the application must support.
