# parameterWithName for URI variables

## Objectives

In **Spring REST Docs**, REST API documentation is generated from executed HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. When you need to document variables in the path, we use **parameterWithName(...)** inside **pathParameters(...)**. The result is a parameter table that can be checked for matching the request's URI template, then included in Asciidoctor documentation and the build/CI pipeline.

After this lesson, you will be able to:

- Accurately identify variable names in a URI template, distinguishing variable names from runtime values.
- Write one **parameterWithName("...")** per variable, with a description useful for API consumers.
- Use descriptors inside a MockMvc test to generate **path-parameters.adoc**.
- Detect errors from misspelled names, extra declarations, or missing variables.
- Understand when **ignored()** is needed, and why you must be cautious with **optional()** and **relaxedPathParameters(...)**.
- Reuse path variable documentation approaches with WebTestClient/REST Assured, and integrate snippets into documentation and CI.

## 1. What is a URI variable?

Suppose an API returns information about a product at a store:

~~~http
GET /api/stores/store-09/products/product-31
Accept: application/json
~~~

In source code, the path is typically defined with a **URI template**:

~~~text
/api/stores/{storeId}/products/{productId}
~~~

| Component | Role |
| --- | --- |
| **/api/stores/**, **/products/** | Fixed path segments, not variables |
| **{storeId}** | Variable name identifying the store |
| **{productId}** | Variable name identifying the product |
| **store-09** | Value bound to **storeId** in the example request |
| **product-31** | Value bound to **productId** in the example request |

The **{storeId}** notation is used in the template to identify a variable placeholder; curly braces do not appear in the final URL sent to the server.

Key distinction:

- **@PathVariable("storeId")** in Spring MVC extracts the value from the request for business processing.
- **parameterWithName("storeId")** in Spring REST Docs declares how to **document** that exact variable name.
- **pathParameters(...)** groups those declarations into a path parameters *snippet*.

Therefore, the name passed to **parameterWithName(...)** is **storeId**, not **{storeId}**, **store-09**, or a Java parameter name that happens to differ from the URL name.

## 2. parameterWithName(...) syntax and usage context

Basic declaration:

~~~java
pathParameters(
    parameterWithName("storeId")
        .description("ID of the store containing the product"),
    parameterWithName("productId")
        .description("ID of the product to look up in the store")
)
~~~

Two static imports are required:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
~~~

**parameterWithName(name)** creates a descriptor for the parameter named **name**. The **description(...)** method attaches the business description, while **pathParameters(...)** specifies that these descriptors belong to the **URI path**. This declaration generates content for the **path-parameters.adoc** snippet when passed to **document(...)** inside a test configured with REST Docs.

Important characteristics:

1. **Names are case-sensitive**: **storeId** and **storeID** are two different names.
2. **Each variable has a corresponding descriptor**: if the URI template contains **{storeId}** and **{productId}**, describe both.
3. **Descriptions must convey meaning**: "ID of the store containing the product" is more useful than "storeId".
4. **Descriptors do not validate types or formats automatically**: writing "UUID" in the description does not make REST Docs reject malformed values.
5. **Where it is used determines the parameter kind**: the same **parameterWithName(...)** API can be used for other parameter snippet groups; **pathParameters(...)** is what defines these as *path parameters*.

Do not confuse this with query parameters. In the URL **/api/stores/store-09/products?limit=20**, **limit** appears after the **?** character, so it is not a path variable and must not be documented inside **pathParameters(...)**.

## 3. Complete example: controller and MockMvc test

The example below assumes a **Spring Boot 3.x**, **Java 17+**, **JUnit 5** project with the test dependencies:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Spring Boot BOM/dependency management can manage the versions for these libraries. For a Maven project, add the corresponding dependencies and use the snippet directory at **target/generated-snippets**.

### 3.1. Sample controller

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductLocationController {

    @GetMapping("/api/stores/{storeId}/products/{productId}")
    ProductLocation getProduct(
            @PathVariable("storeId") String storeId,
            @PathVariable("productId") String productId) {
        return new ProductLocation(storeId, productId, "AVAILABLE");
    }
}

record ProductLocation(String storeId, String productId, String status) {}
~~~

The request **GET /api/stores/store-09/products/product-31** returns example JSON:

~~~json
{
  "storeId": "store-09",
  "productId": "product-31",
  "status": "AVAILABLE"
}
~~~

The illustrative controller only returns hardcoded data; in a real application, product lookup logic usually lives in a service. What to observe in this lesson are the variable names in **@GetMapping** and how they match the descriptors.

### 3.2. HTTP test and documentation generation

Place the test in the same package as the controller so the example can access the package-private class:

~~~java
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

@WebMvcTest(ProductLocationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductLocationDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProductWithinStore() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products/{productId}",
                    "store-09", "product-31")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.storeId").value("store-09"))
            .andExpect(jsonPath("$.productId").value("product-31"))
            .andDo(document("product-location-get",
                pathParameters(
                    parameterWithName("storeId")
                        .description("ID of the store containing the product"),
                    parameterWithName("productId")
                        .description("ID of the product to look up")
                )
            ));
    }
}
~~~

There are three decisive details here:

- **RestDocumentationRequestBuilders.get(...)** preserves the URI template information so Spring REST Docs recognizes the names **storeId** and **productId**. With MockMvc, this is the direct and explicit way to document path variables.
- **get("/.../{storeId}/.../{productId}", "store-09", "product-31")** supplies the two runtime values in order for the two variable positions. Those values make the request execute, while the *names* used for documentation remain **storeId** and **productId**.
- **andDo(document(..., pathParameters(...)))** generates the snippet after the request runs; the test also asserts both the status and returned data.

If you write the request with a fixed path **get("/api/stores/store-09/products/product-31")**, the template information may no longer be available for Spring REST Docs to recognize the two variable names as intended. Always use the request builder meant for URI template documentation.

### 3.3. Output snippets

When the test runs successfully, Spring REST Docs creates files under the directory:

~~~text
build/
└── generated-snippets/
    └── product-location-get/
        ├── http-request.adoc
        ├── http-response.adoc
        ├── curl-request.adoc
        └── path-parameters.adoc
~~~

This is an abbreviated illustrative structure; REST Docs may generate additional default snippets depending on configuration. In **path-parameters.adoc**, the important part is a table with two corresponding rows:

| Parameter | Description |
| --- | --- |
| **storeId** | ID of the store containing the product |
| **productId** | ID of the product to look up |

These names and descriptions come from the test and should not be edited manually inside the **generated-snippets** directory, because they will be regenerated on the next test run.

## 4. Name-matching rules between URI template and descriptor

Spring REST Docs needs to know both the variables present in the URI template and the descriptors you declared. In strict documentation mode, omitting a variable declaration or describing a variable absent from the request can cause snippet generation to fail.

| URI template and declaration | Evaluation |
| --- | --- |
| **{storeId}** ↔ **parameterWithName("storeId")** | Match |
| **{storeId}** ↔ **parameterWithName("storeID")** | Case mismatch |
| **{storeId}** ↔ **parameterWithName("{storeId}")** | Incorrect because it includes curly braces |
| **{storeId}** ↔ **parameterWithName("store-09")** | Incorrect because a value is used instead of the name |
| **{storeId}**, **{productId}**, only **storeId** declared | Missing description for **productId** |
| Only **{storeId}**, also declares **productId** | Declares a name that does not exist in the template |

Incorrect example:

~~~java
get("/api/stores/{storeId}/products/{productId}",
        "store-09", "product-31")
// ...
pathParameters(
    parameterWithName("storeId").description("Store ID"),
    parameterWithName("id").description("Product ID")
)
~~~

The name **id** does not match **productId**. The proper fix is to replace the second descriptor with **parameterWithName("productId")**; there is no need to change the **product-31** value in the request.

A common point of confusion: **the variable name in the URL** must match the descriptor name, whereas **the Java parameter name** does not have to match if the controller explicitly specifies the binding name:

~~~java
@GetMapping("/api/stores/{storeId}")
String getStore(@PathVariable("storeId") String id) {
    return id;
}
~~~

In this case, the descriptor is still **parameterWithName("storeId")** rather than **parameterWithName("id")**, because the URI template uses **{storeId}**.

## 5. Writing description as an API contract

The greatest value of **parameterWithName(...)** lies in clear and stable descriptions. State specifically what the identifier refers to, what scope it belongs to, and any format constraints.

| Unclear description | Useful description |
| --- | --- |
| “ID” | “ID of the order to query” |
| “userId” | “UUID identifying the user whose information is retrieved” |
| “Code” | “Warehouse code, case-sensitive” |
| “Item number” | “Sequence number of the line item in the order, starting from 1” |

Example endpoint using a UUID:

~~~text
GET /api/users/{userId}
~~~

~~~java
pathParameters(
    parameterWithName("userId")
        .description("UUID identifying the user; example: "
            + "550e8400-e29b-41d4-a716-446655440000")
)
~~~

This is only a **description**. To enforce a valid UUID, you must add validation constraints in the application and test both valid and invalid paths. REST Docs does not automatically verify that a value is UUID-formatted based solely on the string inside **description(...)**.

For identifiers whose URL values contain special characters, clients must apply proper URI encoding. For example, **/tasks/{taskId}** with a value containing spaces must be properly encoded; parameter descriptions do not replace URL encoding tests. In particular, a **/** character inside an ID can be interpreted as a boundary between two path segments; design consistent path structures and encoding rules rather than assuming any ID can be placed directly into a segment.

Do not put secret tokens, passwords, or sensitive data into path parameter examples: URLs are frequently recorded in access logs, browser history, and observability systems.

## 6. ignored(), optional(), and relaxedPathParameters(...)

### 6.1. Omitting a variable from the table with ignored()

Sometimes a technical variable exists in the URI, but user-facing documentation does not need to display it. **ignored()** marks the descriptor as recognized while omitting it when building the table:

~~~java
pathParameters(
    parameterWithName("tenantId").ignored(),
    parameterWithName("orderId")
        .description("Order ID within the current tenant")
)
~~~

This fits when the endpoint genuinely has the template **/api/tenants/{tenantId}/orders/{orderId}**, and the **tenantId** concept has already been explained in a shared documentation section. Do not use **ignored()** to hide a parameter that callers must know how to pass.

### 6.2. Meaning of optional()

**optional()** marks the descriptor as not required to appear in the *documented request*. However, a variable on a specific route such as **/orders/{orderId}** is usually required for that route to match. Attaching **optional()** to a descriptor does **not** alter Spring MVC's routing rules and does not turn a **@PathVariable** into an optional parameter by itself.

If a resource supports both **/orders** and **/orders/{orderId}**, you should document and test them as **two separate endpoints**. Adding **optional()** to mask a missing-variable error distorts the meaning of the API contract.

### 6.3. Relaxed documentation

**relaxedPathParameters(...)** is an option that allows certain variables present in the request to remain unlisted in the documentation. While convenient when gradually adopting REST Docs in a legacy project, it can let new path variables go undocumented while tests still pass. For public APIs or when you need strictly verifiable documentation, prefer **pathParameters(...)** and document everything completely.

## 7. Applying the same principles with HTTP test clients

The examples below are excerpts from tests that have already **configured Spring REST Docs integration** for the respective HTTP client; imports and client initialization steps must be added according to the test type.

### WebTestClient

~~~java
webTestClient.get()
    .uri("/api/stores/{storeId}/products/{productId}",
        "store-09", "product-31")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("product-location-webtestclient",
        pathParameters(
            parameterWithName("storeId").description("Store ID"),
            parameterWithName("productId").description("Product ID")
        )
    ));
~~~

Here **document(...)** belongs to **WebTestClientRestDocumentation**. The client must have REST Docs configured, for instance via **documentationConfiguration(...)**. Variable-naming rules remain unchanged.

### REST Assured

~~~java
given(spec)
    .filter(document("product-location-rest-assured",
        pathParameters(
            parameterWithName("storeId").description("Store ID"),
            parameterWithName("productId").description("Product ID")
        )
    ))
    .pathParam("storeId", "store-09")
    .pathParam("productId", "product-31")
    .when()
    .get("/api/stores/{storeId}/products/{productId}")
    .then()
    .statusCode(200);
~~~

Here **document(...)** belongs to **RestAssuredRestDocumentation**, and **spec** is a **RequestSpecification** configured with REST Docs. The two **pathParam(...)** calls supply the request values; the two **parameterWithName(...)** calls describe the variable names in the template.

## 8. Reusing descriptors to avoid inconsistent descriptions

If multiple endpoints share **{storeId}** with the same meaning, you can share a descriptor factory method:

~~~java
import org.springframework.restdocs.request.ParameterDescriptor;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

static ParameterDescriptor storeIdParameter() {
    return parameterWithName("storeId")
        .description("ID of the store containing the resource");
}
~~~

Inside each test:

~~~java
pathParameters(
    storeIdParameter(),
    parameterWithName("productId").description("Product ID")
)
~~~

This keeps descriptions consistent across routes sharing a contract. If **{storeId}** has a different meaning across APIs, prefer a context-specific description. Returning a new descriptor per call also helps avoid descriptor state mutation when tests apply options such as **ignored()**.

## 9. Including the path parameters table in Asciidoctor and CI

In **src/docs/asciidoc/index.adoc**, you can include the snippet:

~~~asciidoc
= Product Location API
:toc: left

== Look up product by store

GET /api/stores/{storeId}/products/{productId}

=== Path parameters

include::{snippets}/product-location-get/path-parameters.adoc[]

=== Request

include::{snippets}/product-location-get/http-request.adoc[]

=== Response

include::{snippets}/product-location-get/http-response.adoc[]
~~~

This example assumes the build passes the **snippets** attribute to Asciidoctor, pointing to **build/generated-snippets**. With Gradle and the Asciidoctor JVM plugin configured, tasks are typically wired together as follows:

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

In CI, run snippet-generating tests before the documentation build step and publish only when all required steps succeed. That way, if **{productId}** is renamed to **{sku}** on the endpoint and you forget to update the descriptor, the documentation test will catch the mismatch before a new page is produced.

Spring REST Docs generates AsciiDoc snippets by default. If your project publishes Markdown, you need a conversion mechanism or compatible snippet templates; the **include::{snippets}/...[]** syntax is Asciidoctor syntax, not standard Markdown syntax.

## 10. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Path parameter not recognized | Request uses a fixed URL or does not preserve the URI template | Use **RestDocumentationRequestBuilders** for MockMvc with a URL containing **{...}** |
| Descriptor reported as unexpected/extra | **parameterWithName(...)** does not match any variable | Check names against the template and remove curly braces from the descriptor |
| Variable reported as undocumented | Missing a **parameterWithName(...)** | Add the descriptor and corresponding business description |
| Generated table has right names but is unclear | Description merely repeats the technical name | Add role, scope, format, and examples where needed |
| Missing **path-parameters.adoc** | **document(...)** was not executed or REST Docs is not configured | Check test extensions/filters/annotations and output path |
| Asciidoctor cannot find snippet | Tests have not run or **snippets** attribute is incorrect | Make the Asciidoctor task depend on tests and check the generated-snippets path |
| Variable name differs from Java parameter name | **@PathVariable** mapped a different name | Take the name from the URI template, not from the Java variable name |

## 11. Practice exercise

Given the URI template:

~~~text
/api/teams/{teamId}/members/{memberId}/permissions/{permissionCode}
~~~

Test request:

~~~http
GET /api/teams/team-2/members/user-8/permissions/READ
~~~

Requirements:

1. Create an HTTP test using all three URI template variables, verifying the status code and returned data.
2. Use **pathParameters(...)** with three **parameterWithName(...)** descriptors. Describe **teamId** as the team ID, **memberId** as the member ID in the team, and **permissionCode** as the permission code being looked up.
3. Generate the snippet **team-member-permission-get/path-parameters.adoc** and include it in Asciidoctor documentation.
4. Try changing **parameterWithName("memberId")** to **parameterWithName("userId")**; predict why the documentation test reports an error.
5. Add a test confirming the API handles a non-existent **permissionCode** properly; explain why merely describing the parameter name does not automatically test this behavior.

Solution for the descriptor part:

~~~java
pathParameters(
    parameterWithName("teamId")
        .description("ID of the team containing the member"),
    parameterWithName("memberId")
        .description("ID of the member whose permissions are checked in the team"),
    parameterWithName("permissionCode")
        .description("Permission code to look up, e.g., READ or WRITE")
)
~~~

Evaluate the exercise against four criteria: correct **names** of all three variables, accurate **meaning** for each variable, the test generates **path-parameters.adoc**, and changing a descriptor to a wrong name causes a mismatch error to be detected.

## Summary

**parameterWithName("variableName")** is the declaration for a parameter name appearing in a URI template. Place it inside **pathParameters(...)** to document path variables; use **description(...)** to communicate business roles and constraints. When wired into HTTP tests configured with Spring REST Docs, this declaration produces verifiable snippets that integrate into Asciidoctor/Markdown alongside your build and CI pipeline.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/) and [RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html).
