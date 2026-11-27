# Numbers, UUIDs, and strings in paths

## Lesson Objectives

A variable in an HTTP path is always transmitted as URI characters, yet the application may treat that value as an **integer**, a **UUID**, or a **string identifier**. With **Spring REST Docs**, we must clearly describe the meaning and expected format of these variables while testing how Spring handles valid and invalid values.

This lesson belongs to the **Path parameters** group of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, and parameters; and compiling them into **Asciidoctor/Markdown** documentation within a build and CI pipeline.

After completing this lesson, you will be able to:

- Distinguish a **variable name** in a URI template from its **value** and its **Java data type**.
- Understand the steps of route matching, path variable extraction, type conversion, and business validation.
- Handle integer IDs, UUIDs, and slugs/strings with appropriate rules.
- Write MockMvc tests generating **path-parameters.adoc** for all three data types.
- Test malformed values; distinguish routing errors from type conversion errors or resource-not-found errors.
- Document formats clearly without confusing REST Docs descriptions with validation mechanisms.
- Integrate snippets into Asciidoctor and the build/CI pipeline.

## 1. Whether number or UUID, the value lives in the URI

Consider three endpoints:

~~~text
GET /api/orders/42
GET /api/users/550e8400-e29b-41d4-a716-446655440000
GET /api/articles/spring-rest-docs-guide
~~~

In a controller, they can be described by three URI templates:

~~~text
/api/orders/{orderId}
/api/users/{userId}
/api/articles/{slug}
~~~

| Variable in URI template | Sample request value | Typical Java type | Meaning |
| --- | --- | --- | --- |
| **{orderId}** | **42** | **Long** or **Integer** | Numeric key of the order |
| **{userId}** | **550e8400-e29b-41d4-a716-446655440000** | **UUID** | User identifier |
| **{slug}** | **spring-rest-docs-guide** | **String** | String identifying the article |

**{orderId}**, **{userId}**, and **{slug}** are *variable names*; the strings **42**, **550e...**, and **spring-rest-docs-guide** are *values*. Spring MVC uses **@PathVariable** to extract the value from the path and convert it into the type declared by the controller method.

There is no "Long" or "UUID" type at the URI syntax level. On the wire, a URI consists of characters; interpreting that string as a number, UUID, or slug belongs to the application.

### 1.1. Three processing steps to distinguish

~~~mermaid
flowchart LR
    A["GET /api/orders/42"] --> B["Match /api/orders/{orderId}"]
    B --> C["Extract string 42"]
    C --> D["Convert to Long"]
    D --> E["Business check / lookup"]
    E --> F["HTTP response"]
    F --> G["Spring REST Docs generates snippet from test"]
~~~

| Stage | Key question | Example failure |
| --- | --- | --- |
| **Routing** | Does the request match the pattern **/api/orders/{orderId}**? | Missing segment **/{orderId}**, may return 404 if no other route exists |
| **Data conversion** | Can the variable string be converted to **Long/UUID**? | **abc** cannot be converted to **Long**, typically returns 400 |
| **Business logic & validation** | Is the type-valid value allowed and does it exist? | ID **9999** has the right type, but no order exists; the application may return 404 |

Spring REST Docs **does not govern** the three stages above. It generates documentation from the requests/responses executed by tests, helping verify variable names in the URI template and the author's descriptions.

## 2. Integer path parameters

### 2.1. Declaring Long/Integer types

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
    return orderService.getOrder(orderId);
}
~~~

When sending **GET /api/orders/42**, Spring matches the pattern, extracts the character value **42**, and converts it to **Long**. With a non-integer value such as **abc**, converting to **Long** typically triggers **400 Bad Request** under Spring MVC's default error handling configuration.

Cases to watch out for:

| Value in path | Binding to **Long** | What to check |
| --- | --- | --- |
| **42** | Converts to number 42 | Does the value exist and is access authorized? |
| **00042** | Usually converts to 42 | If leading **0** digits are meaningful, do not use a numeric type |
| **-42** | Can convert to -42 | The **Long** type does not automatically enforce positive IDs |
| **abc** | Cannot convert | Usually causes a 400 error |
| Number exceeding **Long** range | Cannot convert | Needs tests for out-of-range values |
| **42.5** | Not valid for an integer | Usually causes a 400 error |

Type conversion only ensures the syntax and range supported by the Java type; it **does not automatically guarantee** that an ID must be positive, exist in the database, or belong to a resource the caller is allowed to access. Those rules belong to validation, services, and business tests.

### 2.2. When should you use String for numeric-looking IDs?

For example, customer code **00001234**. If leading **0** digits are a mandatory part of the code, converting to **Long** loses that representation. Using **String** and validating the format is more appropriate:

~~~java
@GetMapping("/api/customers/{customerCode}")
CustomerResponse getCustomer(
        @PathVariable("customerCode") String customerCode) {
    // customerCode keeps "00001234" intact for lookup
    return customerService.getByCode(customerCode);
}
~~~

The decision should be based on the nature of the **business ID**, not merely on whether the string currently consists only of digits.

## 3. UUID path parameters

A UUID is typically represented as a string of hexadecimal character groups separated by hyphens, for example:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

A controller can accept **java.util.UUID** directly:

~~~java
import java.util.UUID;

@GetMapping("/api/users/{userId}")
UserResponse getUser(@PathVariable("userId") UUID userId) {
    return userService.getUser(userId);
}
~~~

Spring usually converts the path value to a UUID through its type conversion system. With a string that cannot be parsed as a UUID, binding fails and under default configuration typically returns **400**.

Keep two concepts separate:

- **Syntactically valid UUID:** the converter obtains a UUID object.
- **UUID valid per the API contract:** the application may also restrict the UUID version, require canonical formatting, or require the ID to actually exist.

A string can be accepted by the UUID parser yet still fail API-specific rules. Therefore, if the contract requires a **specific UUID version** or **canonical lowercase format**, apply explicit checks and write tests for that rule rather than relying solely on the Java parameter type.

In documentation, include an explicit example:

~~~java
parameterWithName("userId")
    .description("UUID identifying the user; e.g. "
        + "550e8400-e29b-41d4-a716-446655440000")
~~~

The **description(...)** call only displays text. It **does not automatically validate** the correctness of submitted UUIDs.

## 4. String, slug, or business-code path parameters

Some resources use string IDs instead of numbers or UUIDs:

~~~text
GET /api/articles/spring-rest-docs-guide
GET /api/products/SKU-2026-001
GET /api/locales/vi
~~~

With **@PathVariable String**, Spring can receive a string within a path segment:

~~~java
@GetMapping("/api/articles/{slug}")
ArticleResponse getArticle(@PathVariable("slug") String slug) {
    return articleService.getBySlug(slug);
}
~~~

**String** does not automatically guarantee that a slug only contains lowercase letters, digits, and hyphens. If the API requires the **[a-z0-9-]+** format, you can:

1. Restrict route matching with a suitable URI pattern.
2. Let the route match and apply validation in the controller/service, returning an error code per the API contract.

Example of a Spring MVC route with a pattern constraint:

~~~java
@GetMapping("/api/articles/{slug:[a-z0-9-]+}")
ArticleResponse getArticle(@PathVariable("slug") String slug) {
    return articleService.getBySlug(slug);
}
~~~

In this case, **/api/articles/spring-rest-docs** can match, while **/api/articles/Invalid_Slug** fails to match the pattern because it contains uppercase letters and an underscore. If no other mapping exists, the result is typically **404** at the routing stage. If you choose validation at the validation layer instead of a route pattern, the application may return **400**; document and test the expected behavior clearly.

### 4.1. URL encoding special characters

A path is part of a URI and has its own encoding rules. Common cases to watch for:

| Business value | Issue | Handling |
| --- | --- | --- |
| **spring-rest-docs** | Letters, digits, and hyphens are safe for slugs | Can be placed directly in a segment |
| **café** or accented text | Must have a valid URI representation | Use a URI builder/client with proper encoding |
| **A B** | Spaces should not be placed raw in a URI | Encode the value before sending |
| **A/B** | The **/** character separates path segments | Avoid using it inside a single-segment ID; encoded slashes can be handled differently by proxies/servers |
| **A?B** or **A#B** | **?** opens a query; **#** starts a client-side fragment | Encode properly or design safe identifiers |

For article titles, choose short, stable slugs with minimal special characters. If an ID must contain separators, reconsider the endpoint design or how it is passed, rather than assuming **{slug}** will accept any arbitrary string uniformly across all HTTP servers.

Do not pass passwords, access tokens, or sensitive information through paths: URLs may be recorded in access logs, browser history, or monitoring systems.

## 5. Using pathParameters(...) to document all three types

Spring REST Docs does not require a separate method per type. Numbers, UUIDs, and strings all use:

~~~java
pathParameters(
    parameterWithName("orderId")
        .description("Order ID as a positive integer")
)
~~~

With the URI template **/api/orders/{orderId}**, **parameterWithName("orderId")** must match the **variable name** inside the curly braces. It does not accept the value **42**, nor does it accept the full string **{orderId}** as the name.

| Type | Template | Recommended description |
| --- | --- | --- |
| **Long** | **/api/orders/{orderId}** | Integer data, bounds/constraints if any, meaning of the ID |
| **UUID** | **/api/users/{userId}** | Which resource the UUID identifies, plus a standard example value |
| **String/slug** | **/api/articles/{slug}** | Character rules, case sensitivity, example |

Information about the **data type** in these descriptions is an **API convention provided by the documentation author**. **pathParameters(...)** itself does not inspect the controller's **Long/UUID/String** type to verify the description text. It primarily checks the **names** of variables in the URI template against the descriptors.

## 6. Complete example with Spring Boot and MockMvc

The example uses **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, and **Spring REST Docs MockMvc**. A project with the Spring Boot plugin and BOM dependency management can use this Gradle configuration:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

### 6.1. Controller accepting Long, UUID, and String

Create **PathValuesController.java**:

~~~java
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PathValuesController {

    @GetMapping("/api/orders/{orderId}")
    PathValueView getOrder(@PathVariable("orderId") Long orderId) {
        return new PathValueView("order", orderId.toString());
    }

    @GetMapping("/api/users/{userId}")
    PathValueView getUser(@PathVariable("userId") UUID userId) {
        return new PathValueView("user", userId.toString());
    }

    @GetMapping("/api/articles/{slug}")
    PathValueView getArticle(@PathVariable("slug") String slug) {
        return new PathValueView("article", slug);
    }
}

record PathValueView(String kind, String value) {}
~~~

This controller simply returns the bound data to illustrate the mechanism. A real application checks access permissions, performs validation, and looks up resources through a service/repository.

### 6.2. Snippet-generating tests

Create **PathValuesDocumentationTest.java** in the same package as the controller:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PathValuesController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PathValuesDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    private static final UUID USER_ID = UUID.fromString(
        "550e8400-e29b-41d4-a716-446655440000");

    @Test
    void documentNumericId() throws Exception {
        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("order"))
            .andExpect(jsonPath("$.value").value("42"))
            .andDo(document("order-id-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Order ID as a Long integer")
                )
            ));
    }

    @Test
    void documentUuid() throws Exception {
        mockMvc.perform(get("/api/users/{userId}", USER_ID)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("user"))
            .andExpect(jsonPath("$.value")
                .value("550e8400-e29b-41d4-a716-446655440000"))
            .andDo(document("user-uuid-get",
                pathParameters(
                    parameterWithName("userId")
                        .description("UUID identifying the user")
                )
            ));
    }

    @Test
    void documentStringSlug() throws Exception {
        mockMvc.perform(get("/api/articles/{slug}",
                    "spring-rest-docs-guide")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("article"))
            .andExpect(jsonPath("$.value")
                .value("spring-rest-docs-guide"))
            .andDo(document("article-slug-get",
                pathParameters(
                    parameterWithName("slug")
                        .description("Article slug, e.g. spring-rest-docs-guide")
                )
            ));
    }

    @Test
    void rejectInvalidNumber() throws Exception {
        mockMvc.perform(get("/api/orders/{orderId}", "not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectInvalidUuid() throws Exception {
        mockMvc.perform(get("/api/users/{userId}", "invalid-uuid"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Why is **RestDocumentationRequestBuilders.get(...)** important? With **MockMvc**, REST Docs' builder preserves URI template information such as **/api/users/{userId}**. If replaced by an already-expanded URL like **/api/users/550e...**, the variable name **userId** is no longer explicitly preserved, causing path parameter table generation to easily fail.

The two invalid-value tests only verify **how Spring MVC performs type conversion** in the sample controller; they do not generate parameter tables and are not meant to imply every API must return the exact same error code when custom exception handling is configured.

### 6.3. Generated snippets

After running the tests successfully, we expect these directories:

~~~text
build/generated-snippets/
├── order-id-get/
│   └── path-parameters.adoc
├── user-uuid-get/
│   └── path-parameters.adoc
└── article-slug-get/
    └── path-parameters.adoc
~~~

The diagram above lists only the path parameters snippets; Spring REST Docs can also generate **http-request.adoc**, **http-response.adoc**, **curl-request.adoc**, and other snippets depending on configuration. Corresponding table content example:

| Snippet | Parameter | Description |
| --- | --- | --- |
| **order-id-get/path-parameters.adoc** | **orderId** | Order ID as a Long integer |
| **user-uuid-get/path-parameters.adoc** | **userId** | UUID identifying the user |
| **article-slug-get/path-parameters.adoc** | **slug** | Article slug, e.g. spring-rest-docs-guide |

Do not edit files under **generated-snippets** directly, as the next test run will regenerate them from the descriptors.

## 7. Separating variable-name checks from data validation

**pathParameters(...)** checks the match between documentation declarations and URI template variables. This is different from testing parsed/validated data.

| Scenario | Responsible check |
| --- | --- |
| Template uses **{userId}** but descriptor writes **userID** | Spring REST Docs can report a documentation error |
| Template has **{orderId}** but forgets to describe **orderId** | Strict snippet reports an undocumented parameter |
| Value **abc** sent to **@PathVariable Long** | Spring MVC type conversion and HTTP test |
| Value **invalid-uuid** sent to **@PathVariable UUID** | Spring MVC type conversion and HTTP test |
| Value **-42** converts to **Long**, yet ID must be positive | Application validation or business logic |
| Syntactically valid UUID, yet user does not exist | Service/repository and business tests |
| Slug contains disallowed characters | Route regex/validation and corresponding tests |

Therefore, a high-quality test suite should have **valid tests that generate snippets**, **invalid-type tests**, and **invalid-business-condition tests** if those conditions are part of the API contract.

### 7.1. Should you use optional() with an ID in the path?

For the route **/api/orders/{orderId}**, the segment for **{orderId}** must be present to match the pattern. **parameterWithName("orderId").optional()** only changes a property of the Spring REST Docs descriptor; it does **not** make **GET /api/orders** match the detail route.

If the API needs both a list endpoint **GET /api/orders** and a detail endpoint **GET /api/orders/{orderId}**, declare two route patterns, and test and document each case separately. Do not use **optional()** to try turning a path segment into a routing option.

### 7.2. When to use ignored()?

If a technical variable exists in the path but is already explained in a shared section, you can choose to omit it from the table:

~~~java
pathParameters(
    parameterWithName("tenantId").ignored(),
    parameterWithName("userId")
        .description("UUID of the user belonging to the tenant")
)
~~~

Assuming the URI template is **/api/tenants/{tenantId}/users/{userId}**, the **tenantId** segment still needs to be supplied when calling the route. **ignored()** only keeps the descriptor from appearing in the snippet; consider carefully whether API readers still need to know how to pass this variable.

## 8. WebTestClient and REST Assured apply the same way

Correctness of numbers, UUIDs, and slugs is checked by the application; the other two test clients can also generate snippets with the same **pathParameters(...)**.

### 8.1. WebTestClient

In a test with the REST Docs documentation generator configured for **WebTestClient**:

~~~java
webTestClient.get()
    .uri("/api/users/{userId}",
        "550e8400-e29b-41d4-a716-446655440000")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("user-uuid-webtestclient",
        pathParameters(
            parameterWithName("userId")
                .description("UUID identifying the user")
        )
    ));
~~~

In the snippet above, **document(...)** belongs to **WebTestClientRestDocumentation**, and the client must attach REST Docs configuration (e.g., **documentationConfiguration(...)**) before calling.

### 8.2. REST Assured

With a **RequestSpecification spec** configured with Spring REST Docs integration:

~~~java
given(spec)
    .filter(document("article-slug-rest-assured",
        pathParameters(
            parameterWithName("slug")
                .description("Slug identifying the article")
        )
    ))
    .pathParam("slug", "spring-rest-docs-guide")
    .when()
    .get("/api/articles/{slug}")
    .then()
    .statusCode(200);
~~~

Here **document(...)** is imported from **RestAssuredRestDocumentation**. **pathParam(...)** assigns the value to the request; **parameterWithName(...)** defines the variable name to document. For values with special characters, use the HTTP client's URI encoding capabilities and test server/proxy behavior.

## 9. Including snippets in Asciidoctor and CI integration

In **src/docs/asciidoc/index.adoc**, assuming the **snippets** attribute is passed by the build:

~~~asciidoc
= API Path Identifiers
:toc: left

== Order by numeric ID

GET /api/orders/{orderId}

include::{snippets}/order-id-get/path-parameters.adoc[]
include::{snippets}/order-id-get/http-response.adoc[]

== User by UUID

GET /api/users/{userId}

include::{snippets}/user-uuid-get/path-parameters.adoc[]
include::{snippets}/user-uuid-get/http-response.adoc[]

== Article by slug

GET /api/articles/{slug}

include::{snippets}/article-slug-get/path-parameters.adoc[]
include::{snippets}/article-slug-get/http-response.adoc[]
~~~

Example **Gradle Groovy DSL** configuration when the **org.asciidoctor.jvm.convert** plugin is installed:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

The **dependsOn test** relationship ensures the documentation build task runs the snippet-generating tests first. In **CI**, publish documentation only when both the relevant tests and the documentation build task succeed. That way, if a URI template is renamed from **{userId}** to **{accountId}** without updating the descriptor, strict snippet generation can detect the out-of-sync change.

Spring REST Docs usually generates AsciiDoc snippets under default configuration. If your project publishes in **Markdown**, use an appropriate conversion mechanism or snippet templates; the **include::...[]** directive is Asciidoctor syntax and does not work automatically in plain Markdown.

## 10. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| **/api/orders/abc** returns 400 | Spring cannot convert the string to **Long** | Send an appropriate integer or redesign the code type |
| **/api/users/invalid-uuid** returns 400 | Value cannot be parsed into a UUID | Use a valid UUID and add tests for invalid cases |
| **/api/orders/-1** still reaches controller | **Long** allows negative numbers | Add validation/business constraints if the ID must be positive |
| Code **00042** turns into **42** | ID was bound to a numeric type | Use **String** if leading zeros have business meaning |
| **/api/articles/A/B** does not match route **/{slug}** | The **/** character separates path segments | Choose a safe slug or design a different route |
| Malformed slug still succeeds | **String** does not validate format on its own | Add a route regex or validation |
| Descriptor reported as not found | Name in **parameterWithName(...)** differs from URI template | Use the exact name, e.g. **userId**, not the UUID value |
| **path-parameters.adoc** not generated | Test did not call **document(...)**, missing config, or URI template not preserved | Use the REST Docs builder and check test setup |
| Asciidoctor missing snippet | Tests have not run or **snippets** attribute is incorrect | Check build task order and output path |
| Docs say UUID while endpoint accepts arbitrary String | Description was not cross-checked against Java type/validation | Review contract and write accept/reject tests |

## 11. Practice exercise

Build three endpoints:

~~~text
GET /api/invoices/{invoiceId}
GET /api/customers/{customerId}
GET /api/products/{productCode}
~~~

Business rules:

- **invoiceId** is a positive integer within the **Long** range.
- **customerId** is a UUID, e.g., **550e8400-e29b-41d4-a716-446655440000**.
- **productCode** is a string code that may contain leading zeros, e.g., **00007A**.

Follow these steps:

1. Write a controller accepting **Long**, **UUID**, and **String** via three corresponding **@PathVariable** parameters.
2. Write valid HTTP tests for each endpoint using **RestDocumentationRequestBuilders.get(...)**; verify HTTP status and one JSON response field.
3. For each request, call **document(...)** and **pathParameters(parameterWithName(...).description(...))** to generate separate snippets.
4. Add tests sending **invoiceId=abc** and **customerId=not-a-uuid**, and explain why a data type error differs from a resource-not-found error.
5. Verify that **productCode=00007A** preserves its exact value. Explain why this code should not be coerced into a **Long**.
6. Include the three **path-parameters.adoc** files in Asciidoctor; run tests and then build the docs, ensuring CI will catch test failures.

Sample documentation declarations:

~~~java
// For GET /api/invoices/{invoiceId}
pathParameters(
    parameterWithName("invoiceId")
        .description("Invoice ID as a positive integer")
)

// For GET /api/customers/{customerId}
pathParameters(
    parameterWithName("customerId")
        .description("UUID identifying the customer")
)

// For GET /api/products/{productCode}
pathParameters(
    parameterWithName("productCode")
        .description("Product code as a string, preserving leading zeros")
)
~~~

**Completion criteria:** all three valid requests generate snippets; tests properly check binding and value errors; descriptions clearly state format/meaning; Asciidoctor documentation displays the three corresponding tables.

## Key Takeaways

Path values are transmitted in the URI as characters; **Spring MVC** converts them into **Long**, **UUID**, or **String** according to the controller signature and application rules. **Integers** require bounds/business checks, **UUIDs** require format convention checks if applicable, and **strings** require attention to slugs and URL encoding. **Spring REST Docs** uses the same **pathParameters(...)** and **parameterWithName(...)** mechanism to document all three, without automatically validating the format stated in the description. Combine valid/invalid data tests, generate snippets from real requests, and integrate into build and CI for verifiable REST API documentation.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html), and [Spring MVC URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
