# Converting IDs with BackendIdConverter, URL Encoding, and Handling Invalid IDs

## Objectives

Spring Data REST builds item resources with an ID at the end of the path, for example /customers/1001. The ID in the URL is the public representation of the backend identifier. For simple IDs like Long or UUID, the default representation is usually sufficient. For composite keys, IDs needing custom formatting, or cases where the internal ID type must not be exposed directly, you can use BackendIdConverter to convert back and forth between the URI ID and the ID used by the repository.

When designing resource paths, four concerns should be kept separate:

1. Determining the base path and the repository's collection path.
2. Generating an item URI from an ID as exactly one path segment.
3. Converting the public ID in the request into the backend ID type using BackendIdConverter.
4. Returning clear errors when an ID is malformed or does not point to an existing entity.

Paths, URI encoding, and ID conversion are related, yet they are distinct layers. BackendIdConverter does not rename the collection path; it only controls how the ID is represented in the URI and how the ID is recovered for lookup.

## 1. Resource Path Structure

A Spring Data REST item resource typically has the form:

    https://example.test/<context-path>/<base-path>/<repository-path>/<id>

Each segment has a distinct meaning:

| Component | Example | Configuration Source |
|---|---|---|
| Host and port | https://example.test | Application server |
| Context path | /app | Servlet or Spring Boot configuration |
| Spring Data REST base path | /api | spring.data.rest.base-path or RepositoryRestConfiguration |
| Repository path | /customers | Domain type or @RepositoryRestResource |
| Item ID | /1001 | ID converted into a URI string |

For example, when the application runs under context path /app, Spring Data REST base path /api, and repository path /customers, an item resource may be:

    https://example.test/app/api/customers/1001

### 1.1. Default Repository Path

Spring Data REST publishes the collection resource based on the simple name of the domain class. The name is lowercased and pluralized using the framework's pluralization rules.

For example:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

This repository is typically exported at /customers, and each item has a URI matching /customers/{id}.

Do not infer URLs from interface names if the project has custom configuration. Send a GET request to the root resource and follow the HAL links in _links to discover actual paths.

### 1.2. Changing the Repository Path and Relation

Use @RepositoryRestResource to change the collection's path and link relation name:

    @RepositoryRestResource(
        path = "customers",
        collectionResourceRel = "customers"
    )
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Where:

- path = "customers" changes the collection URI to /customers.
- collectionResourceRel = "customers" changes the relation name in _links.
- Item resources are placed under the collection path, e.g., /customers/{id}.

Path and rel are not synonymous. Path affects the URL; rel affects the link name clients see in HAL.

### 1.3. Changing Query Method and Association Paths

Use method-level @RestResource to change the path of a query method:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {

        @RestResource(path = "by-email", rel = "byEmail")
        Optional<Customer> findByEmailAddress(
                @Param("email") String email);
    }

The query method is placed under the search resource:

    GET /customers/search/by-email?email=an@example.test

path = "by-email" changes the URL; rel = "byEmail" changes the relation name in the search resource's link list.

Similarly, you can place @RestResource on an association property to change the path and relation of an association resource. Association resources typically reside under the item resource:

    /customers/{id}/orders

### 1.4. Changing the Base Path

You can set the base path in Spring Boot:

    spring.data.rest.base-path=/api

Or configure it via RepositoryRestConfigurer:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setBasePath("/api");
        }
    }

The base path only adds a prefix to Spring Data REST resources. It is distinct from the context path of the entire application and distinct from each repository's own path.

## 2. The ID in a URI Is One Path Segment

An item resource has the form:

    /customers/{id}

The ID occupies a single path segment. It is not a query parameter and must not contain characters that alter the path structure.

For example, if the raw ID is A+B/42, it should not be concatenated directly into:

    /customers/A+B/42

A slash creates an extra segment. A question mark starts the query string; a hash starts the fragment. Spaces and many other characters also require percent-encoding before being sent over HTTP.

Some encoding examples for a single path segment:

| Raw Value | Percent-Encoded Form |
|---|---|
| A B | A%20B |
| A+B | A%2BB |
| A/B | A%2FB |
| A?B | A%3FB |
| A#B | A%23B |
| A%B | A%25B |
| Nguyễn | Encode each UTF-8 byte and then percent-encode |

Percent-encoding is applied to each UTF-8 byte of non-ASCII characters. Thus a single Unicode character can produce multiple %HH groups.

### 2.1. Building URIs with Spring UriComponentsBuilder

When a client constructs URIs programmatically, use a URI builder to encode the value as a path segment variable:

    URI uri = UriComponentsBuilder
            .fromUriString("https://example.test")
            .pathSegment("api", "customers", "{id}")
            .encode()
            .buildAndExpand("A+B/42")
            .toUri();

The ID value is treated as data for one segment. Spring encodes characters with special meaning in the variable value when expanding the URI template.

If building links manually for a single segment, Spring also provides UriUtils.encodePathSegment. In most cases, UriComponentsBuilder manages both URI structure and encoding more cleanly.

### 2.2. Do Not Use URLEncoder for Path Segments

java.net.URLEncoder is designed for application/x-www-form-urlencoded form data, typically used in queries or form bodies. Its rule turns spaces into plus signs (+). That is not the general rule for encoding a path segment.

In a path:

- A plus sign can be a literal plus character.
- A space is represented as %20.
- To represent a literal plus inside a value, it is usually percent-encoded as %2B.

Using the wrong encoder can cause the server to receive a different ID from the original.

### 2.3. Avoid Double Encoding

Encode values only once at the URI construction boundary. For example:

- A % character in a raw ID is encoded as %25.
- If a string that already contains %2F is encoded again, % becomes %25 and the server receives the literal string %2F instead of a decoded slash.
- Double encoding causes the resulting ID to no longer match the original ID.

BackendIdConverter receives an ID already parsed from the request path. Do not call URLDecoder by default inside fromRequestId. Inspect the exact value the application receives before adding any decoding step.

URLDecoder also uses form rules, where plus signs can be interpreted as spaces. Do not use it as a general path-segment decoder.

### 2.4. Be Careful with Slashes in IDs

UriComponentsBuilder can encode a slash inside a path segment as %2F. However, reverse proxies, web servers, or servlet containers may reject or normalize encoded slashes before Spring receives the request.

Therefore, avoid relying on IDs containing / in URLs if deployment infrastructure cannot control how encoded slashes are handled. Use URL-safe formats such as UUID or URL-safe Base64 so the ID always fits cleanly in one segment.

## 3. What Is BackendIdConverter?

BackendIdConverter is an SPI in the package:

    org.springframework.data.rest.webmvc.spi

It lets you customize how entity IDs are placed into URIs and how IDs from requests are converted into backend values for lookup.

The interface has three key parts:

| Member | Role |
|---|---|
| supports(Class<?> entityType) | Determines whether the converter applies to this domain type |
| toRequestId(Serializable id, Class<?> entityType) | Converts the backend ID into a string ID for use in URIs |
| fromRequestId(String id, Class<?> entityType) | Converts the string ID from a request into the backend ID |

Round-trip flow:

    Backend entity ID
        |
        v
    toRequestId(...)
        |
        v
    ID in URI / HAL link
        |
        v
    HTTP request
        |
        v
    fromRequestId(...)
        |
        v
    Backend entity ID
        |
        v
    Repository lookup

BackendIdConverter.DefaultIdConverter is the default converter. It uses the ID as-is: toRequestId returns the string representation of the ID and fromRequestId returns the received string. If you do not need a custom ID format, you do not need to write a new converter.

### 3.1. When Should You Use a Custom Converter?

A custom converter can be helpful when:

- The repository uses a composite key or @EmbeddedId.
- The backend ID needs a stable, readable, or URL-safe URI representation.
- The system needs to expose an ID form different from the internal representation, yet deterministically reversible.
- Different domain types require different ID rules.

Do not use a converter merely to change the collection path. Use @RepositoryRestResource(path = "...") for that.

A converter also does not replace authentication or authorization. An unpredictable or encoded ID still does not prove the caller has permission to read or modify an entity.

## 4. Implementing BackendIdConverter

The following example assumes Customer has a Long backend ID. The ID is exposed in URLs as URL-safe Base64 of its decimal string representation.

Repository:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Converter:

    @Component
    public class CustomerIdConverter implements BackendIdConverter {

        @Override
        public boolean supports(Class<?> entityType) {
            return Customer.class.equals(entityType);
        }

        @Override
        public Serializable fromRequestId(
                String requestId, Class<?> entityType) {

            if (!Customer.class.equals(entityType)) {
                throw new IllegalArgumentException(
                        "Unsupported entity type");
            }

            try {
                byte[] bytes = Base64.getUrlDecoder().decode(requestId);
                String value = new String(bytes, StandardCharsets.UTF_8);

                if (!value.matches("[1-9][0-9]*")) {
                    throw new IllegalArgumentException(
                            "Invalid customer identifier");
                }

                Long backendId = Long.valueOf(value);

                String canonical = Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(value.getBytes(StandardCharsets.UTF_8));

                if (!canonical.equals(requestId)) {
                    throw new IllegalArgumentException(
                            "Non-canonical customer identifier");
                }

                return backendId;

            } catch (IllegalArgumentException ex) {
                throw new IllegalArgumentException(
                        "Invalid customer identifier", ex);
            }
        }

        @Override
        public String toRequestId(
                Serializable id, Class<?> entityType) {

            if (!Customer.class.equals(entityType)
                    || !(id instanceof Long)) {
                throw new IllegalArgumentException(
                        "Expected a Long customer identifier");
            }

            String value = id.toString();

            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(value.getBytes(StandardCharsets.UTF_8));
        }
    }

The converter is registered as a Spring bean, for instance with @Component in a component-scanned package. Spring Data REST builds a registry from BackendIdConverter beans and selects the converter whose supports returns true for the given domain type.

With backend ID 1001:

- toRequestId converts the string "1001" into the token "MTAwMQ".
- HAL links may contain /customers/MTAwMQ.
- When a request arrives, fromRequestId decodes the token and returns Long.valueOf("1001").
- The repository proceeds to look up using the Long backend ID.

URL-safe Base64 uses a character alphabet suited for URL paths and omits trailing padding. Note that this is only reversible encoding, not cryptographic encryption. Anyone can decode the token to learn the original value. If you need public IDs that do not reveal sequential IDs, consider a random UUID stored as a public identifier or a keyed token mechanism with clear lifecycle management.

### 4.1. Supporting Composite IDs

For composite keys, fromRequestId can decode the token and reconstruct a value object implementing Serializable, such as OrderId containing tenantId and orderNumber. toRequestId performs the reverse conversion.

Make sure that:

- OrderId has consistent equals and hashCode.
- Combining components is unambiguous. You can use a schema-defined JSON structure or properly escaped delimiters.
- The encoded string always fits in a single path segment.
- Two distinct composite IDs never produce the same request ID.
- ID format versioning is managed if the API must support format changes in the future.

BackendIdConverter does not create composite keys for the entity itself. It only converts between the URI representation and the ID object expected by the repository.

### 4.2. Converter Implementation Rules

A reliable converter should follow these rules:

1. supports must return true only for the domain types the converter actually handles.
2. toRequestId and fromRequestId must be inverses of each other.
3. toRequestId output must be deterministic and unique for each backend ID.
4. fromRequestId must return a non-null Serializable per the interface contract.
5. Do not return null to indicate an invalid ID. Throw a meaningful exception so the HTTP layer turns it into an appropriate error response.
6. Validate length limits, character alphabet, overflow, and canonical format before lookup.
7. Do not let a converter apply to another entity merely because that entity has the same ID type.

## 5. Handling Invalid IDs

Two cases must be distinguished: IDs that cannot be converted and IDs that are valid but match no entity.

| Case | Example | Recommended API Response |
|---|---|---|
| Malformed ID | Token is not URL-safe Base64 or decodes to a non-numeric string | 400 Bad Request |
| ID out of backend range | Decoded number exceeds Long range | 400 Bad Request |
| Valid ID but no entity found | Token decodes to 1002, but repository has no Customer 1002 | 404 Not Found |
| Resource does not support HTTP method | Sending POST to an item resource | 405 Method Not Allowed |
| Caller lacks permission | ID exists, but caller is not authorized to access it | 401 or 403 depending on security setup |

### 5.1. Validating Syntax Before Querying

fromRequestId should validate the token before returning a backend ID:

- Token is non-empty.
- Length is within reasonable bounds.
- Only accepts characters in the format's defined alphabet.
- Decoded data conforms to the expected structure.
- Numeric value fits within the ID type's range.
- If the format requires canonical form, the re-encoded token matches the input token exactly.

Do not turn malformed tokens into 0, null, or a default ID. Doing so could cause an invalid request to accidentally point to a real entity.

### 5.2. Distinguishing 400 and 404

400 Bad Request is appropriate when the client sends an ID value that cannot be parsed or violates the API format. This is an input error.

404 Not Found is appropriate when the ID was parsed successfully but no matching entity exists. Do not turn a parse error into 404 just to mask a format error, and do not return 500 for ordinary invalid input.

Spring Data REST has its own exception handling mechanism. How a specific exception maps to a status code can depend on the version and the application's exception handlers. Verify actual responses in the version you are running. If a converter throws a custom exception that does not map to 400 by default, configure an exception handler for that exception type and keep the response body concise without leaking internal details.

### 5.3. Malformed URI Encoding Can Be Rejected Before the Converter

If a request contains an invalid percent escape such as %ZZ, or an encoded slash rejected by a proxy/container, the request may be rejected before Spring Data REST parses the path variable. In that case, fromRequestId is never called.

When investigating errors, check in this order:

1. Did the client build the URI properly?
2. Did a reverse proxy or gateway modify the path?
3. Does the servlet container accept that encoded path segment?
4. Can Spring MVC parse the path variable?
5. Did BackendIdConverter receive the exact ID string?
6. Does the repository have an entity with that backend ID?

This order helps pinpoint whether the issue occurs at the URI layer, the ID conversion layer, or the data layer.

## 6. Testing the Converter and Paths

### 6.1. Round-Trip Unit Tests

For a valid backend ID, conversion must restore the exact original value:

    Long backendId = 1001L;

    String requestId = converter.toRequestId(
            backendId, Customer.class);

    Serializable restoredId = converter.fromRequestId(
            requestId, Customer.class);

    assertEquals(backendId, restoredId);

Also test boundary cases: minimum supported ID, maximum ID, empty token, invalid-alphabet token, non-numeric decoded data, and numbers overflowing Long.

### 6.2. HTTP Integration Tests

Use MockMvc or equivalent HTTP tests to verify the full path:

- GET root and collection to verify HAL links.
- GET item with a valid ID token where the entity exists.
- GET item with a valid ID token where the entity does not exist.
- GET item with a malformed token.
- Verify IDs containing special characters are properly encoded in URIs.
- Confirm the converter is not applied to other domain types.
- Confirm routes have the configured base path and repository path.

Basic expectations:

| Request | Expected Result |
|---|---|
| GET /api/customers/MTAwMQ, Customer 1001 exists | 200 OK |
| GET /api/customers/MTAwMg, Customer 1002 does not exist | 404 Not Found |
| GET /api/customers/not-a-valid-token | 400 Bad Request |
| POST /api/customers/MTAwMQ when item does not support POST | 405 Method Not Allowed |

If the project uses custom exception handlers, tests must confirm the exact status codes and error structure promised by the API.

## 7. Path and ID Troubleshooting Checklist

When an item URL does not work, check in order:

1. Does the root HAL resource contain a link to the right repository?
2. Does the repository have a custom path set via @RepositoryRestResource?
3. Are the base path and context path missing or duplicated when combined?
4. Is the ID placed within exactly one path segment?
5. Does the client percent-encode path variable values properly?
6. Is URLEncoder or URLDecoder being used in the wrong context?
7. Is double encoding or double decoding occurring?
8. Does BackendIdConverter.supports select the right domain type?
9. Does fromRequestId produce the right backend ID type and avoid returning null?
10. Does an entity exist with the converted backend ID?
11. Do proxies, gateways, or the servlet container alter or block encoded paths?
12. Do status codes and response bodies accurately reflect parse errors, not-found errors, unsupported methods, or access errors?

Prefer following HAL links returned by the server. Those links reflect the base path, repository path, relation, and ID representation currently used by the server.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST — BackendIdConverter API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/spi/BackendIdConverter.html)
- [Spring Data REST — BackendIdHandlerMethodArgumentResolver API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/BackendIdHandlerMethodArgumentResolver.html)
- [Spring Framework — URI Links and URI Encoding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
