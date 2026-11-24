# Reading application/x-www-form-urlencoded via exchange

In **Spring WebFlux**, an HTML form can be submitted in the HTTP request body as a URL-encoded form. With the media type `application/x-www-form-urlencoded`, fields are represented as name–value pairs such as `username=alice&remember=true`. Spring WebFlux provides the `ServerWebExchange.getFormData()` API to read this body into a reactive `MultiValueMap<String, String>`.

This API is useful when a controller needs direct access to the entire form, needs to handle repeated fields, read dynamic fields, or combine form data with the request context. It does not read the query string: query parameters live in `exchange.getRequest().getQueryParams()`, whereas the form body lives in `exchange.getFormData()`.

This lesson explains how WebFlux decodes forms, how to read multiple values with the same name, body lifecycle, memory limits, data validation, and how to test with `WebTestClient`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Recognize the structure and media type of a URL-encoded form.
2. Use `ServerWebExchange.getFormData()` to read a form reactively.
3. Understand the `Mono<MultiValueMap<String, String>>` return type and how to retrieve values.
4. Handle missing fields, empty fields, repeated fields, and Unicode data.
5. Distinguish the form body from query parameters and HTTP headers.
6. Understand how `FormHttpMessageReader` decodes the body and how to configure codecs.
7. Avoid reading the request body multiple times or manually parsing the form string.
8. Limit form size, handle errors, and protect sensitive data.
9. Write a runnable Java 17 controller and test it with `WebTestClient`.

## 2. What is application/x-www-form-urlencoded?

`application/x-www-form-urlencoded` is the format commonly used when a browser submits an HTML form without file uploads. The body contains key-value pairs joined by `&`; names and values are separated by `=`.

Example body:

~~~text
username=alice&displayName=Alice+Nguyen&remember=true
~~~

A form with multiple values for the same name can send:

~~~text
tag=reactive&tag=webflux&tag=spring
~~~

Important encoding rules:

- The `&` character separates pairs; the `=` character separates the name and the value.
- A plus sign `+` in form encoding represents a space.
- A literal plus sign must be percent-encoded as `%2B`.
- Characters outside the ASCII set are encoded according to the charset, typically UTF-8.
- Special characters are represented using percent-encoding, for example `%26` is `&`.
- A key may appear multiple times; do not assume each key has only one value.

Example:

~~~http
POST /api/forms/submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

username=alice&displayName=Nguy%E1%BB%85n+V%C4%83n+A&tag=reactive&tag=webflux
~~~

Spring decodes the pairs above into Java data. The controller does not need to split the string by `&` or `=` manually.

## 3. Reading a Form with ServerWebExchange.getFormData()

In WebFlux, `ServerWebExchange` represents an HTTP request/response. The method:

~~~java
Mono<MultiValueMap<String, String>> getFormData()
~~~

returns a `Mono` containing the form fields. A `MultiValueMap` is a map where each key can hold multiple values.

Example of reading a form:

~~~java
@PostMapping(
    path = "/submit",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
Mono<String> submit(ServerWebExchange exchange) {
    return exchange.getFormData()
        .map(form -> {
            String username = form.getFirst("username");
            return "username=" + username;
        });
}
~~~

This is an illustrative snippet; the corresponding Spring types need to be imported. The controller receives the exchange directly, calls `getFormData()`, and processes the result inside `map`. Reading the body happens reactively; there is no need to block the thread with `block()`.

### 3.1. Return Type

`getFormData()` returns:

~~~java
Mono<MultiValueMap<String, String>>
~~~

There are two layers to understand:

- `Mono` represents the decoded form result that will be provided asynchronously.
- `MultiValueMap<String, String>` contains field names and lists of String values.

A form may have no fields; in that case, the map can be empty. If a field is required, the controller must check the existence and value of the field instead of assuming data is always present.

### 3.2. Retrieving a Single Value with getFirst

When a field should only have one value, use `getFirst`:

~~~java
String username = form.getFirst("username");
~~~

`getFirst` returns the first value or `null` if the key does not exist. If the form sends multiple values for the same key, this method only takes the first value; the application must decide whether to accept repeated fields.

Validating a required field:

~~~java
String username = form.getFirst("username");

if (username == null || username.isBlank()) {
    // Return a validation error for the username field.
}
~~~

Distinguish three cases:

| Case | Example | How to detect |
| --- | --- | --- |
| Field missing | username not sent | `form.getFirst("username") == null` |
| Field present but empty | `username=` | Value is an empty string |
| Field has a value | `username=alice` | Value is `alice` |

Do not use a single check for every field. An unchecked checkbox may be absent; a text input may have an empty string; each type of field needs its own business rules.

### 3.3. Retrieving All Values with get

When a key can appear multiple times, use `get`:

~~~java
List<String> tags = form.get("tag");
~~~

With the body:

~~~text
tag=reactive&tag=webflux&tag=spring
~~~

the resulting list contains three elements in order of appearance. To handle the case where the key is absent:

~~~java
List<String> tags = form.getOrDefault("tag", List.of());
~~~

If you need to store the list or pass it to the business layer, you can create an immutable copy:

~~~java
List<String> tags = List.copyOf(
    form.getOrDefault("tag", List.of())
);
~~~

Do not call `toSingleValueMap()` if you need to preserve repeated values, because a single-value map drops multiple values for the same key.

## 4. Form Body vs. Query Parameters

This is the easiest point to confuse when migrating from Spring MVC to WebFlux.

- The form body is read using `exchange.getFormData()`.
- The query string is read using `exchange.getRequest().getQueryParams()`.
- Headers are read using `exchange.getRequest().getHeaders()`.

Example request:

~~~http
POST /api/forms/submit?source=newsletter
Content-Type: application/x-www-form-urlencoded

username=alice&tag=reactive
~~~

Reading each source separately:

~~~java
Mono<String> handle(ServerWebExchange exchange) {
    return exchange.getFormData().map(form -> {
        String username = form.getFirst("username");
        String source = exchange.getRequest()
            .getQueryParams()
            .getFirst("source");

        return "username=" + username + ", source=" + source;
    });
}
~~~

`username` comes from the body; `source` comes from the query string. If both the query and the form contain the key `username`, the two values still belong to two separate sources. They are not automatically merged into a single value.

In Spring WebFlux, `@RequestParam` focuses on query parameters. If you want to read a URL-encoded form body directly and explicitly, use `getFormData()`. For forms with a fixed DTO structure, `@ModelAttribute` is also a data binding option; meanwhile, the exchange API is useful when you need to handle dynamic maps, repeated fields, or multiple parts of the request.

## 5. FormHttpMessageReader and the Decoding Process

`ServerWebExchange.getFormData()` relies on WebFlux's message reader mechanism. The dedicated `FormHttpMessageReader` reads the URL-encoded body and converts it into a `MultiValueMap<String, String>`.

High-level processing flow:

~~~text
HTTP request body
Content-Type: application/x-www-form-urlencoded
        |
        v
ServerWebExchange.getFormData()
        |
        v
FormHttpMessageReader
        |
        v
Decode charset and percent-encoding
        |
        v
MultiValueMap<String, String>
        |
        v
Controller processes the data
~~~

The reader performs work that application code should not reimplement:

- Splits name and value pairs.
- Decodes percent-encoding.
- Handles plus signs according to form encoding rules.
- Decodes bytes using the supported charset.
- Preserves multiple values for a single key.
- Applies configured buffering limits.

### 5.1. Content-Type Must Be Correct

The endpoint should declare:

~~~java
consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
~~~

The client sends:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

If the endpoint only accepts URL-encoded forms but the client sends `application/json` or `multipart/form-data`, the mapping may be rejected with `415 Unsupported Media Type`.

Do not confuse the three formats:

| Content-Type | Content | Appropriate reading API |
| --- | --- | --- |
| `application/x-www-form-urlencoded` | URL-encoded key-value pairs | `exchange.getFormData()` |
| `multipart/form-data` | Separate parts, may contain files | `exchange.getMultipartData()` or `@RequestPart` |
| `application/json` | JSON object/array | `@RequestBody` or JSON reader |

### 5.2. Charset and Unicode

URL-encoded forms typically use UTF-8. The charset can be sent explicitly:

~~~http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Vietnamese field example:

~~~text
displayName=Nguy%E1%BB%85n+V%C4%83n+A
~~~

After decoding, the value is `Nguyễn Văn A`. When testing or sending with curl, use `--data-urlencode` so the tool encodes characters properly.

Do not manually call URLDecoder on a value already decoded by Spring. Doing so can double-decode and turn data such as plus signs or percent sequences into something different from the original intent.

## 6. Request Body Lifecycle and Reading the Form Multiple Times

The HTTP request body is a data stream. In a reactive server, the body should not be treated as a string that can be arbitrarily read multiple times.

`ServerWebExchange.getFormData()` stores the decoded form result in the exchange so subsequent calls can reuse the cached result. However, this does not mean all body-reading APIs can run independently afterward.

Rules:

1. Call `getFormData()` when you need to read a URL-encoded form.
2. Do not call `exchange.getRequest().getBody()` and expect to still be able to read the raw body after the form reader has consumed the body.
3. Do not manually subscribe to the body inside a controller or filter.
4. If multiple components need the same data, read the form once and pass the needed values along.
5. Do not store the exchange or body publisher in a singleton/cache for use in other requests.

Example of what not to do:

~~~java
exchange.getFormData().subscribe(form -> log.info("{}", form));
return chain.filter(exchange);
~~~

This snippet creates a side subscription and can consume the body outside the request lifecycle. Return a publisher or compose operations into the main publisher instead. Furthermore, never log the entire form if it contains passwords, tokens, or personal information.

## 7. Validating and Normalizing Form Data

Form data is input from the client. Having the reader decode it into Strings does not mean the data is valid or trustworthy.

A typical processing workflow includes:

1. Read the fields.
2. Check required fields.
3. Trim or normalize according to business rules.
4. Validate length and format.
5. Check the number of values for repeated fields.
6. Convert to a strongly typed command/DTO.
7. Check authorization before performing the action.

Example of validating username:

~~~java
String username = form.getFirst("username");

if (username == null || username.isBlank()) {
    return badRequest("username is required");
}

username = username.trim();

if (username.length() > 80) {
    return badRequest("username is too long");
}
~~~

This is illustrative pseudocode for the validation part; `badRequest` needs to be replaced by the application's appropriate response/exception.

### 7.1. Checking Repeated Fields

For a field expected to have only one value, check its count:

~~~java
List<String> values = form.get("role");

if (values != null && values.size() != 1) {
    // Reject requests with repeated role values.
}
~~~

Do not take the first value by default for security-sensitive fields such as role, accountId, or redirect URL. An attacker can send multiple values with the same name to exploit differences between parsers at the proxy, framework, and application layers.

### 7.2. Type Conversion

Form values are always decoded as Strings. If you need an integer:

~~~java
String rawAge = form.getFirst("age");

Integer age = null;
if (rawAge != null && !rawAge.isBlank()) {
    try {
        age = Integer.valueOf(rawAge);
    }
    catch (NumberFormatException ex) {
        // Return an error indicating age must be an integer.
    }
}
~~~

For dates, enums, or custom types, use a Converter/Formatter or a centralized mapper class. Do not duplicate complex parsing logic in every controller.

### 7.3. Binding to a DTO

If the form has a stable structure, create a command DTO:

~~~java
record RegistrationCommand(
    String username,
    String displayName,
    List<String> tags
) {}
~~~

After reading the form, build the DTO from the validated fields:

~~~java
RegistrationCommand command = new RegistrationCommand(
    username,
    displayName,
    List.copyOf(tags)
);
~~~

The DTO should only contain fields the client is allowed to submit. Do not bind directly to persistence entities that have sensitive properties such as role, balance, ownerId, or audit metadata.

## 8. Configuring Memory Limits

A URL-encoded form is decoded into a map, so the reader needs to buffer the body data to parse the key-value pairs. A very large form body can consume a lot of memory.

Spring WebFlux's default codecs have a buffering limit; the default is typically 256 KiB for codecs that apply this limit. When the threshold is exceeded, the request may fail with `DataBufferLimitException`.

This can be configured on the server:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024);
    }
}
~~~

The example above sets a 512 KiB limit for default codecs that support that configuration. This is not the total multipart upload size limit or a request limit for every network layer. Multipart has separate limits for memory, disk, and number of parts.

### 8.1. Choosing Limits Based on Needs

When deciding on maxInMemorySize, consider:

- Maximum number of fields in the form.
- Maximum length of names and values.
- Number of concurrent requests.
- Heap/direct memory capacity of the application.
- Request body limits at the reverse proxy/gateway.
- Whether the form should contain large data at all.

Do not increase the limit to tens or hundreds of MB just to handle an unusual form. URL-encoded forms are suited for small form data; file uploads should use multipart or an appropriate streaming upload API.

### 8.2. Handling DataBufferLimitException

You can standardize limit-exceeded errors using an exception handler:

~~~java
@RestControllerAdvice
class FormExceptionHandler {

    @ExceptionHandler(DataBufferLimitException.class)
    ResponseEntity<Map<String, String>> handleLimit(
            DataBufferLimitException exception) {

        return ResponseEntity
            .status(HttpStatus.PAYLOAD_TOO_LARGE)
            .body(Map.of(
                "error", "form body exceeds the configured limit"
            ));
    }
}
~~~

This is an integration snippet; the corresponding types need to be imported. Mapping to 413 is the API policy of this example; the application should align status codes and error schemas with the gateway as well as other endpoints. Other decode errors can be mapped to 400 Bad Request.

## 9. Runnable Java 17 Example with Spring Boot WebFlux

The example below creates an endpoint that accepts a URL-encoded form and returns JSON. The controller reads the body using `ServerWebExchange.getFormData()`, preserves repeated tags, and also reads the `source` query parameter separately.

### 9.1. Project Structure

~~~text
form-exchange-demo/
├── build.gradle
└── src/
    ├── main/java/demo/FormExchangeApplication.java
    ├── main/java/demo/FormController.java
    └── test/java/demo/FormControllerTest.java
~~~

### 9.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages compatible versions of Spring Framework, Reactor, Jackson, and test dependencies. The example uses Java 17 and Spring Boot 3.3.5 for an easily reproducible baseline; for new projects, choose a supported Spring Boot patch and let the BOM manage Spring module versions.

### 9.3. FormExchangeApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormExchangeApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormExchangeApplication.class, args);
    }
}
~~~

### 9.4. FormController.java

~~~java
package demo;

import java.util.List;
import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import org.springframework.util.MultiValueMap;

import reactor.core.publisher.Mono;

record FormResult(
    boolean accepted,
    String username,
    String displayName,
    List<String> tags,
    String source,
    String error
) {}

@RestController
class FormController {

    @PostMapping(
        path = "/api/forms/submit",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<FormResult>> submit(
            ServerWebExchange exchange) {

        return exchange.getFormData().map(form -> {
            String username = Optional
                .ofNullable(form.getFirst("username"))
                .orElse("")
                .trim();

            String displayName = Optional
                .ofNullable(form.getFirst("displayName"))
                .orElse("");

            List<String> tags = List.copyOf(
                form.getOrDefault("tag", List.of())
            );

            String source = exchange.getRequest()
                .getQueryParams()
                .getFirst("source");

            if (username.isBlank()) {
                FormResult error = new FormResult(
                    false,
                    null,
                    displayName,
                    tags,
                    source,
                    "username is required"
                );
                return ResponseEntity.badRequest().body(error);
            }

            FormResult result = new FormResult(
                true,
                username,
                displayName,
                tags,
                source,
                null
            );

            return ResponseEntity.ok(result);
        });
    }
}
~~~

Points to note:

- The mapping only accepts `application/x-www-form-urlencoded`.
- `getFormData()` reads the body into a `MultiValueMap`.
- `getFirst("username")` retrieves a single value; `getOrDefault("tag", List.of())` keeps all repeated tags.
- `getQueryParams()` reads the query string separately, so `source` is not mixed with the form body.
- `List.copyOf` creates a list that cannot be modified externally.
- The handler returns `Mono<ResponseEntity<FormResult>>`; it does not call `block()` or `subscribe()`.

The example does not handle user authentication or database persistence. In a real application, do not return passwords/tokens, do not trust permission fields from the client, and always check authorization before performing business logic.

### 9.5. FormControllerTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class FormControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsFormFieldsAndRepeatedValues() {
        client.post()
            .uri("/api/forms/submit?source=newsletter")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                    "username", "alice"
                )
                .with("displayName", "Nguyễn Văn A")
                .with("tag", "reactive")
                .with("tag", "webflux"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice")
            .jsonPath("$.displayName").isEqualTo("Nguyễn Văn A")
            .jsonPath("$.tags[0]").isEqualTo("reactive")
            .jsonPath("$.tags[1]").isEqualTo("webflux")
            .jsonPath("$.source").isEqualTo("newsletter")
            .jsonPath("$.accepted").isEqualTo(true);
    }

    @Test
    void rejectsMissingRequiredUsername() {
        client.post()
            .uri("/api/forms/submit")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Alice"
            ))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo(false)
            .jsonPath("$.error").isEqualTo("username is required");
    }

    @Test
    void queryParameterIsNotTreatedAsFormField() {
        client.post()
            .uri("/api/forms/submit?username=query-user")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Alice"
            ))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.error").isEqualTo("username is required");
    }

    @Test
    void rejectsJsonWhenEndpointRequiresUrlEncodedForm() {
        client.post()
            .uri("/api/forms/submit")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"username\":\"alice\"}")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
~~~

The tests use WebTestClient and Spring's body inserter to send actual forms. The first test verifies Unicode, query parameters, and repeated fields; the second test checks the required field; the third test proves that a query parameter does not automatically become a form field; the last test checks that an inappropriate media type is rejected.

### 9.6. Running Tests and the Application

Run tests:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

Run the application:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

If you do not have the Gradle Wrapper, you can use `gradle test` and `gradle bootRun` when Gradle is installed.

## 10. Calling the Endpoint with curl

Send a form with Unicode and multiple tags:

~~~bash
curl -i -X POST \
  'http://localhost:8080/api/forms/submit?source=newsletter' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'displayName=Nguyễn Văn A' \
  --data-urlencode 'tag=reactive' \
  --data-urlencode 'tag=webflux'
~~~

Expected JSON body:

~~~json
{
  "accepted": true,
  "username": "alice",
  "displayName": "Nguyễn Văn A",
  "tags": ["reactive", "webflux"],
  "source": "newsletter",
  "error": null
}
~~~

Send a form missing username:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/forms/submit \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice'
~~~

The request is rejected with status 400 Bad Request and a body containing error `username is required`.

Send the wrong media type:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/forms/submit \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice"}'
~~~

The endpoint only accepts URL-encoded forms, so the JSON request does not match the consumes condition and is rejected. In the test, we check the 4xx family so it does not depend on specific exception handling configuration.

## 11. Security When Handling Forms

Forms often contain user-entered data; some forms also carry sensitive information.

### 11.1. Do Not Trust Client Data

All values in a form are untrusted input. Validate types, lengths, formats, value counts, and permissions before using them. A field named role, admin, or tenant does not grant privileges to the sender on its own.

### 11.2. Do Not Log Passwords or Tokens

Avoid logging the entire MultiValueMap. If debugging is needed, only log allowlisted field names and omit or mask sensitive fields such as password, access_token, csrf token, email, or phone number.

### 11.3. CSRF Protection for Browser Forms

If a form is submitted from a browser and the application uses session/cookie authentication, configure Spring Security's CSRF protection appropriately. Do not disable CSRF just because the endpoint uses POST or URL-encoded Content-Type. Content-Type does not replace CSRF checks.

### 11.4. Use HTTPS

URL encoding is only a data representation format, not secret encryption. Do not send passwords or tokens over unencrypted HTTP. Use HTTPS/TLS and appropriate cookie policies.

### 11.5. Avoid Parameter Pollution

A key can be repeated multiple times. For a field that must be unique, reject it if there is more than one value. Do not let the reverse proxy, security layer, and controller interpret duplicate fields in different ways.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `getQueryParams()` to read the form body | Cannot retrieve fields in the body | Use `getFormData()` |
| Using `@RequestParam` as in Spring MVC expecting to read the form body | Does not match the WebFlux query parameter model | Use the exchange API or `@ModelAttribute` |
| Not declaring consumes | Endpoint may accept the wrong format or give confusing errors | Declare `application/x-www-form-urlencoded` |
| Manually splitting the body by `&` and `=` | Fails on percent-encoding, plus signs, Unicode, and repeated fields | Use `FormHttpMessageReader` via exchange |
| Using only getFirst for every field | Loses repeated values | Use get and check cardinality |
| Not distinguishing missing fields from empty fields | Incorrect validation or bypass | Check null, blank, and field rules |
| Reading the raw body then calling getFormData | Body is already consumed or can no longer be read as expected | Choose one reading mechanism and pass the result along |
| Calling block/subscribe in the controller | Blocks the event loop or creates a side subscription | Compose logic inside Mono/Flux and return the publisher |
| Setting maxInMemorySize too high | Many concurrent requests can cause memory pressure | Limit form size and process large data via streaming |
| Logging the entire form | Leaks passwords, tokens, and personal data | Log filtered/masked metadata |
| Trusting role/tenant from the form | Users can escalate privileges themselves | Verify principal and authorization on the server side |
| Confusing URL-encoded with multipart | Fails to handle file uploads properly | Use multipart reader, FilePart, or PartEvent |
| Calling URLDecoder again | Double-decoding, altering plus signs/percent sequences | Use values already decoded by FormHttpMessageReader |
| Treating URL-encoded form as secure encryption | Data can still be read over insecure connections | Use HTTPS/TLS |

## 13. Checklist When Using getFormData()

Before deploying the endpoint, check:

1. **Media type:** does the client send `application/x-www-form-urlencoded` and does the mapping declare the right consumes?
2. **Data source:** are the fields in the body or query string? Are they read from the right API?
3. **Cardinality:** is the field single-valued or multi-valued? Should repeated keys be rejected?
4. **Missing values:** have null, empty string, and valid values been distinguished?
5. **Encoding:** are UTF-8 and percent-encoding handled properly?
6. **Body lifecycle:** does any component read the raw body before getFormData?
7. **Memory:** are maxInMemorySize and body limits appropriate for the form size?
8. **Validation:** are length, format, and business rules validated?
9. **Security:** are CSRF protection, authorization, HTTPS, and sensitive data masking in place?
10. **Tests:** has WebTestClient tested Unicode, repeated fields, missing fields, separate query/body, and wrong media types?

**Remember:** `ServerWebExchange.getFormData()` is the direct, reactive way to read `application/x-www-form-urlencoded` in WebFlux. The result is `Mono<MultiValueMap<String, String>>`, allowing you to retrieve a single value with getFirst or keep repeated values with get. The form body and query parameters are two separate sources; let `FormHttpMessageReader` handle encoding, control body size, validate data, and keep the request body within a single lifecycle.

## References

- Spring Framework — WebFlux Form Data: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/form-data.html
- Spring Framework — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework — FormHttpMessageReader API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/FormHttpMessageReader.html
- Spring Framework — WebFlux HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
