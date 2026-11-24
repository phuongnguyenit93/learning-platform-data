# Verifying Generated Specifications Alongside Actual HTTP Responses

springdoc-openapi generates an OpenAPI specification from a Spring Boot application's controllers, mappings, and annotations. The specification describes how clients should send requests and which responses they may receive. However, a successfully generated document does not prove the application actually returns the data published in that document. A controller might declare a **201** response yet return **200** at runtime; OpenAPI might state **application/json** while the endpoint actually returns **application/problem+json**; or a schema might omit fields the response sends.

Therefore, both sides must be verified in the same workflow:

- **The generated specification** at the OpenAPI endpoint, usually **/v3/api-docs**.
- **Actual HTTP responses** when sending requests to business endpoints.

The goal is confirming that paths, methods, request bodies, status codes, headers, media types, and actual payload structures match the OpenAPI contract. This is a core part of API contract testing in the **SPRINGDOC_OPENAPI** module, alongside describing requests, responses, schemas, security, and documentation groups.

## 1. Why Compare the Specification Against Actual HTTP Behavior?

Springdoc analyzes Spring MVC or WebFlux configurations and annotations to build documentation. It does not invoke every endpoint with every payload to observe all possible outcomes. A specification can be generated faithfully from source metadata and still diverge from runtime behavior because:

- Business logic returns a different status code or response type than expected.
- Jackson renames fields, omits null fields, or alters enum or date-time formats.
- Validation produces an error response that is not fully documented.
- Message converter or content negotiation settings alter the **Content-Type**.
- Spring Security, filters, interceptors, or gateways return errors before the request reaches the controller.
- Context path, reverse proxy, or documentation group settings make public URLs differ from URLs in the document.
- A new handling branch is added without updating **@ApiResponse** annotations.

For example, a controller is documented as returning **201 Created**, while a business branch returns **409 Conflict** when an order already exists. If OpenAPI lacks a **409** response, clients generated from the specification may fail to handle the real-world case.

Another case is an API returning errors via **ProblemDetail** with **application/problem+json**, while the documentation only lists **application/json**. Both are JSON, yet their media types and contract structures differ.

## 2. Components to Compare

Cross-checking is more than checking whether a response is JSON. Inspect all parts of the operation and response:

| Component | In OpenAPI | In Actual HTTP |
| --- | --- | --- |
| Path and method | **paths**, **get**, **post**, **put**, **delete**... | Sent URL and method |
| Path/query/header parameters | **parameters**, **in**, **required**, **schema** | URL values, query string, and request headers |
| Request body | **requestBody.content**, **required**, schema | Sent body, **Content-Type** |
| Status code | Keys in **responses**, e.g. **200**, **201**, **400**, **409** | Received status code |
| Media type | **responses.content** | Response header **Content-Type** |
| Schema | **$ref**, **properties**, **required**, **format**, **enum** | Actual JSON or payload in body |
| Response headers | **responses.headers** | **Location**, **ETag**, **Content-Disposition**, **Cache-Control**... |
| Security | **security**, **securitySchemes** | Behavior with valid token, missing token, or insufficient permissions |
| Error payload | Responses for **4xx** and **5xx** | Error body returned by validation, security, exception handlers, or gateways |

Not every response has a body. For instance, **204 No Content** usually has no **Content-Type** or body schema. For this response, verify the status and that the body is actually empty rather than expecting a JSON schema.

## 3. Verification Workflow from Documentation to Real Requests

### Step 1: Fetch the OpenAPI Specification Served by the Application

Start the application with the exact profile and configuration to test. Under springdoc's default configuration, fetch JSON with:

~~~powershell
curl.exe -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

If the application uses a context path, reverse proxy, or changed **springdoc.api-docs.path**, use the URL clients actually access. When multiple documentation groups exist, fetch the endpoint for the specific group under test.

Quickly check the OpenAPI version and paths:

~~~powershell
jq -r '.openapi, (.paths | keys[])' openapi.json
~~~

For example, inspect the request body and responses documented for the create-order operation:

~~~powershell
jq '.paths["/api/orders"].post | {
  requestBody: .requestBody,
  responses: .responses
}' openapi.json
~~~

These commands only read the generated documentation. They do not prove the business endpoint returns the right data.

### Step 2: Send Requests with Known Data

Send a request to the business endpoint itself and capture status, headers, and body. Use **-i** to see headers alongside the response:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/orders -H "Content-Type: application/json" -H "Accept: application/json" -d '{"customerCode":"CUS-100","quantity":2}'
~~~

Record at least:

- The URL and HTTP method called.
- Request headers and request body.
- HTTP status code.
- Response headers, especially **Content-Type** and headers published in the contract.
- Raw response body.

Use deterministic test data so tests are repeatable. Do not use a single success example to conclude every error branch also conforms to the contract.

### Step 3: Compare the Operation and Response

For the create-order request above, inspect the **POST /api/orders** operation in OpenAPI:

~~~json
{
  "requestBody": {
    "required": true,
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/CreateOrderRequest"
        }
      }
    }
  },
  "responses": {
    "201": {
      "description": "Order has been created",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/OrderView"
          }
        }
      }
    }
  }
}
~~~

If the actual HTTP call returns **201** and **Content-Type: application/json**, that response must be documented under **responses["201"].content["application/json"]**. Then verify that the **OrderView** schema in **components.schemas** contains the actual fields such as **id**, **customerCode**, **quantity**, and **status**.

If the actual status or media type is missing from the specification, it signals an incomplete or inaccurate contract. Determine whether the runtime behavior is intentional or an implementation bug before changing annotations or controller logic.

### Step 4: Repeat for Other Outcome Branches

Verify at least the meaningful scenarios for the endpoint:

| Scenario | HTTP Behavior to Verify | Required Specification |
| --- | --- | --- |
| Valid request | **200 OK** or **201 Created** per design | Success response and schema |
| Missing required field or invalid format | Usually **400 Bad Request** | Validation error response |
| Unauthenticated | **401 Unauthorized** | Authentication error response |
| Insufficient permissions | **403 Forbidden** | Authorization error response |
| Resource does not exist | **404 Not Found** | Not-found error response |
| Business conflict | **409 Conflict** if designed | Conflict error response |
| No content | **204 No Content** | Response without a body |
| Unexpected error | **500 Internal Server Error** or standardized code | Error response matching API policy |

The status codes above are common examples, not mandatory rules for every API. Cross-check against your application's design decisions and ensure every reachable branch is clearly documented.

## 4. Automated Verification with MockMvc

**MockMvc** lets you invoke requests through Spring MVC in integration tests without opening a real HTTP port. You can use it to fetch **/v3/api-docs**, call business endpoints, and compare actual statuses and media types against the operation in the specification.

The example below assumes the application has **POST /api/orders**, accepts a JSON **CreateOrderRequest**, and returns **OrderView** with **201 Created**. DTO and controller classes belong to the application code; the example focuses on the contract verification test.

~~~java
import java.util.Iterator;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiRuntimeContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void createOrderResponseMatchesOpenApi() throws Exception {
        // Fetch the specification from the application under test.
        MvcResult specResult = mockMvc.perform(
                get("/v3/api-docs").accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andReturn();

        JsonNode openApi = objectMapper.readTree(
            specResult.getResponse().getContentAsString()
        );

        JsonNode operation = openApi
            .path("paths")
            .path("/api/orders")
            .path("post");

        // Verify the request body published by the specification.
        JsonNode requestContent = operation
            .path("requestBody")
            .path("content")
            .path("application/json");

        assertThat(requestContent.isMissingNode()).isFalse();
        assertThat(operation.path("requestBody").path("required").asBoolean())
            .isTrue();

        // Call the business endpoint with valid data.
        String requestJson = """
            {
              "customerCode": "CUS-100",
              "quantity": 2
            }
            """;

        MvcResult actualResult = mockMvc.perform(
                post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson)
            )
            .andReturn();

        int actualStatus = actualResult.getResponse().getStatus();
        String statusKey = Integer.toString(actualStatus);

        // Actual status must be documented in responses.
        JsonNode responses = operation.path("responses");
        JsonNode responseDefinition = responses.path(statusKey);
        if (responseDefinition.isMissingNode()) {
            responseDefinition = responses.path("default");
        }

        assertThat(responseDefinition.isMissingNode()).isFalse();

        // Actual media type must appear in content for that status.
        String actualContentType = actualResult.getResponse().getContentType();
        assertThat(actualContentType).isNotBlank();

        MediaType parsedType = MediaType.parseMediaType(actualContentType);
        String mediaTypeKey = parsedType.getType() + "/" + parsedType.getSubtype();

        JsonNode mediaDefinition = responseDefinition
            .path("content")
            .path(mediaTypeKey);

        assertThat(mediaDefinition.isMissingNode()).isFalse();

        // Compare actual fields with the referenced response schema.
        JsonNode schemaDefinition = mediaDefinition.path("schema");
        String schemaRef = schemaDefinition.path("$ref").asText(null);
        JsonNode responseSchema = schemaRef == null
            ? schemaDefinition
            : openApi.at(schemaRef.substring(1));

        assertThat(responseSchema.isMissingNode()).isFalse();

        JsonNode actualBody = objectMapper.readTree(
            actualResult.getResponse().getContentAsString()
        );
        JsonNode declaredProperties = responseSchema.path("properties");

        Iterator<String> fieldNames = actualBody.fieldNames();
        while (fieldNames.hasNext()) {
            String fieldName = fieldNames.next();
            assertThat(declaredProperties.has(fieldName))
                .as("Field '%s' must be described in OpenAPI", fieldName)
                .isTrue();
        }
    }
}
~~~

The example uses AssertJ, Jackson, JUnit 5, and Spring test classes. If your project uses another response type or inline schemas, adjust schema resolution to match the actual document. The test demonstrates three essential verification layers: request media type is published, actual status exists in **responses**, and response media type and actual fields match the referenced schema.

The field check in the example is one-way: every field appearing in the sample response must be allowed by the schema. For a stricter contract, also check required fields, data types, **format**, **enum**, null values, nested object structures, and schema constraints.

If an endpoint can return **204 No Content**, do not parse the body with **ObjectMapper** in that branch. Instead, assert status **204**, an empty body, and no content declared in OpenAPI for that response.

## 5. When Testing Through a Real HTTP Server Is Needed

**MockMvc** tests Spring MVC processing flow but does not traverse HTTP sockets, reverse proxies, ingress, or API gateways. When those layers can alter URLs, headers, or responses, add tests running the application on a random port with **@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)** and invoke it via **TestRestTemplate**, **WebTestClient**, or the project's HTTP client.

Conceptual example with **TestRestTemplate**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpContractTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void endpointUsesDocumentedStatusAndMediaType() {
        ResponseEntity<String> response = http.postForEntity(
            "/api/orders",
            new CreateOrderRequest("CUS-100", 2),
            String.class
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        MediaType actualType = response.getHeaders().getContentType();
        assertThat(actualType).isNotNull();
        assertThat(actualType.isCompatibleWith(MediaType.APPLICATION_JSON)).isTrue();
    }
}
~~~

This example tests responses through an embedded HTTP server. To compare fully against OpenAPI, also fetch **/v3/api-docs** with the same HTTP client and apply the status, media type, and schema assertions shown in the **MockMvc** section.

For staging or production environments, tests can run externally via **curl.exe** or an HTTP client in the pipeline. Use public URLs and appropriate credentials while avoiding logging tokens or sensitive data in test output.

## 6. Comparing Schemas with Serialized JSON

Java types do not always match actual JSON. Springdoc usually infers schemas from DTOs and annotations, while Jackson determines the JSON written to the response. The following configurations can cause the two sides to diverge:

- **@JsonProperty** renames fields in JSON.
- **@JsonIgnore** excludes fields from JSON.
- **@JsonInclude** may omit null fields or fields with default values.
- Enums may be serialized as names, codes, or values depending on configuration.
- **@JsonFormat** and ObjectMapper settings affect date-time formatting.
- Naming strategies can convert **customerCode** to **customer_code**.
- Custom serializers may write different data types than the original Java type.

When verifying schemas, use field names in the serialized JSON to compare against schema **properties**, rather than looking solely at Java class property names. For dates and times, verify **type**, **format**, timezone, and realistic examples. For enums, compare possible runtime values against the documented **enum** list.

For example, if the actual JSON response is:

~~~json
{
  "order_id": "ORD-1001",
  "customer_code": "CUS-100",
  "status": "CREATED"
}
~~~

then the OpenAPI schema must describe the corresponding names **order_id**, **customer_code**, and **status**. A schema still listing **id** or **customerCode** will cause clients generated from OpenAPI to misunderstand the data structure.

## 7. Checking Headers and Content Negotiation

Contract responses may include headers besides **Content-Type**. For example:

- **Location** indicates the URL of a newly created resource.
- **ETag** supports caching and conditional updates.
- **Content-Disposition** describes file download behavior and filename.
- **Cache-Control** specifies caching rules.
- **WWW-Authenticate** provides authentication scheme details when returning **401**.

If clients rely on a header, document that header in the OpenAPI response and verify its runtime value. Do not check merely that the header exists; verify its content has the format and semantics clients require.

For content negotiation, send different **Accept** values to verify the endpoint supports the published media types. For instance, if the API supports JSON and XML, test both and confirm the corresponding response **Content-Type**. When sending an unsupported **Accept**, check **406 Not Acceptable** behavior and decide whether that response needs to appear in the contract.

For requests, test sending an unsupported **Content-Type** to verify **415 Unsupported Media Type** if the endpoint restricts **consumes**. The specification should list the media types the endpoint accepts, not formats the controller cannot actually process.

## 8. Checking Validation, Security, and Errors

A contract documenting only success responses is insufficient when the API has predictable error branches. Test separately:

**Validation.** Send missing required fields, strings exceeding limits, out-of-range numbers, or invalid enums. Verify status, media type, and error schema. If using **ProblemDetail**, inspect properties such as **type**, **title**, **status**, **detail**, **instance**, and application-specific extensions.

**Authentication.** Call a protected endpoint without a token. Verify status **401**, the **WWW-Authenticate** header if used, and the response body against the contract.

**Authorization.** Send a valid token lacking permissions. Verify status **403** and the error payload. Do not conflate **401** and **403** if clients need to distinguish the two scenarios.

**Business exceptions.** Trigger cases such as non-existent resources, data conflicts, or disallowed states. Confirm **@ControllerAdvice** or exception handlers return the documented status and body.

**Infrastructure errors.** When gateways or reverse proxies can return their own errors, test responses at the boundary clients actually call. Responses generated by gateways may bypass controllers and springdoc, so they should be managed in the corresponding distribution contract.

## 9. Integrating Verification into CI

Automatically fetch the specification from an application started with test configuration, execute representative requests, and verify outcomes. A basic pipeline can follow this sequence:

~~~text
Start application with test profile
              |
              v
Fetch /v3/api-docs and verify valid document
              |
              v
Verify paths, methods, requestBody, and responses
              |
              v
Send representative success and error requests
              |
              v
Compare status, headers, media type, and body against OpenAPI
              |
              v
Diff specification against released baseline (if any)
              |
              v
         Report CI results
~~~

In CI, checks can be divided into groups:

1. **Specification structure check:** **/v3/api-docs** succeeds, JSON is valid, and required version, paths, and schemas exist.
2. **Mapping check:** methods, paths, parameters, request bodies, and media types match implemented endpoints.
3. **Response check:** all key statuses and media types are documented; schemas cover actual payloads.
4. **Error branch check:** validation, authentication, authorization, and business errors have stable statuses and bodies.
5. **Contract change check:** diff current OpenAPI against the released baseline to detect breaking client changes.

OpenAPI diff tools can detect changes between two specification versions, but by themselves do not prove runtime returns the right contract. Conversely, testing a handful of HTTP responses does not prove every operation and schema in the document is accurate. Combining specification checks, HTTP tests, and version diffs yields stronger coverage.

## 10. Checklist Upon Completing a Verification Pass

- [ ] Fetched OpenAPI from the right application, profile, context path, and document group.
- [ ] URLs and HTTP methods in the documentation match actual endpoints.
- [ ] Parameters, request bodies, **Content-Type**, and **Accept** match how endpoints handle them.
- [ ] Every key runtime status has a corresponding response in OpenAPI.
- [ ] Response **Content-Type** is declared in **responses.content**.
- [ ] Actual JSON matches field names, data types, enums, and formats in the schema.
- [ ] Headers needed by clients are documented and carry accurate values.
- [ ] Validation, authentication, authorization, and business error responses have been verified.
- [ ] Bodyless responses such as **204** are verified properly.
- [ ] Tests run in CI and fail when contract discrepancies are detected.

## 11. Conclusion

The OpenAPI specification is the contract published to clients, while HTTP responses are the behavior clients actually receive. springdoc generates the contract from a Spring Boot application; integration tests and HTTP checks confirm that contract accurately reflects runtime behavior. Cross-check both requests and responses, including status, headers, media types, schemas, and error branches. When these checks run automatically in CI, controller or serialization changes surface discrepancies early before documentation and APIs are shipped to consumers.
