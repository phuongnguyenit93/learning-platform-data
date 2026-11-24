# Describing Purpose, Preconditions, and Observable Outcomes

An operation in OpenAPI should help integrators answer three questions: **What is this operation for? What conditions must the client satisfy before calling it? After calling it, what outcomes can the client observe?** Paths, HTTP methods, and data types only describe the mechanics of communication. The operation description must clarify business semantics so API consumers know when to call it, what to prepare, and how to handle each outcome.

With springdoc-openapi, we typically use the **@Operation** annotation to describe the purpose and business conditions, combined with **@Parameter**, request schemas, **@ApiResponse**, and response schemas to describe inputs and outcomes. OpenAPI has no dedicated fields named preconditions or postconditions; this information is expressed through the operation description, parameters, security requirements, request body, responses, headers, and HTTP status codes.

## 1. Why Describe the Purpose of an Operation?

Method names and paths can indicate the technical action, yet are rarely sufficient to explain business rules. For instance, POST /api/v1/orders might create a draft order, place a confirmed order, or accept a pending order request. Readers need to know which behavior the operation actually performs.

A good description helps:

- **Choose the right operation:** clients understand when the operation applies and what limitations exist.
- **Prepare the request:** integrators know which data to send, which fields are required, and which values are accepted.
- **Handle errors:** clients distinguish authentication failures, invalid data, unsuitable business states, and resource conflicts.
- **Predict outcomes:** clients know which resources are created or updated, which status is returned, and any side effects to watch for.
- **Contract testing:** the development team can turn stated conditions and outcomes into concrete test cases.

The goal is to describe what API callers need to know. There is no need to expose internal algorithms, database table names, or service organization in public documentation.

## 2. Distinguishing summary and description

In OpenAPI, each operation can have a summary and a description.

| Field | Role | How to Write |
|---|---|---|
| summary | Briefly states the main action | One short sentence with a verb and target object |
| description | Explains purpose, preconditions, rules, and behavior | Structured paragraphs or Markdown |

Example:

```yaml
paths:
  /api/v1/orders:
    post:
      summary: Create order
      description: |
        Creates a new order from the customer-submitted list of products and quantities.

        The order is created in PENDING_PAYMENT status. The system reserves
        inventory for 15 minutes so the customer can complete payment.
```

Summary lets readers quickly scan the operation list in Swagger UI. Description explains what cannot be conveyed clearly through the endpoint name alone. Avoid generic summaries like "Process data", "Execute operation", or "Order API", because they do not tell the client what it will achieve.

## 3. What Are Preconditions?

**Preconditions** are requirements that must be satisfied before an operation can succeed. They can be grouped into several categories.

### 3.1. Identity and Permission Conditions

Clients may need to be authenticated, hold a valid access token, or possess a specific role. Describe:

- Whether the operation requires authentication.
- Which user groups or permissions are allowed to perform it.
- Whether the resource must fall within the caller's access scope.
- Which HTTP outcome an expired token or missing permission produces under API policy.

OpenAPI has security and securitySchemes mechanisms to describe authentication methods. Business descriptions can supplement permission scopes—for example, only the order owner or an authorized manager may cancel an order. Never put sample tokens, passwords, or real secrets in descriptions or examples.

### 3.2. Resource State Conditions

An action may only be valid when a resource is in a certain state. For example:

- Only orders in DRAFT status can be confirmed.
- Only unshipped orders can be canceled.
- Only active accounts can initiate transactions.
- Only products currently on sale can be added to an order.

If a condition is not met, state the invalid state and the outcome the client receives. For instance, a shipped order cannot be canceled and the API returns 409 Conflict.

### 3.3. Input Data Conditions

A request may require mandatory fields, positive quantities, valid value ranges, date-time formats, or size limits. Rules can be expressed across multiple layers:

- required and schema describe structure in OpenAPI.
- minimum, maximum, minLength, maxLength, pattern, and enum describe constraints representable in schema.
- @Valid, Bean Validation, and OpenAPI annotations derive constraints from DTOs.
- description explains business rules that cannot be fully represented by schemas.

For example, a schema can express that quantity is an integer greater than 0. Description can explain that the maximum quantity per order line is 20 and the product must currently be on sale.

### 3.4. Resource and Environment Conditions

An operation may depend on related resources or system state:

- The customer ID must exist and belong to the current tenant.
- The warehouse must be able to fulfill the requested quantity.
- A record must not be soft-deleted.
- The payment service must support the chosen method.

Only state conditions that clients can understand or verify. If a condition can change between when the client checks and when the server processes it, explain that the server still re-verifies it at execution time.

## 4. What Are Observable Outcomes?

**Observable outcomes** are what a client can observe after sending a request. They include:

1. HTTP status code.
2. Response body and schema.
3. Meaningful response headers such as Location, ETag, Retry-After.
4. Resource state after the operation.
5. Business effects the API commits to, such as inventory being reserved or a request being accepted.
6. Follow-up actions the client must perform, such as paying before a deadline or polling processing status.

Each outcome should be described with specific conditions. For example, 201 Created indicates the resource was created; the response should provide its identifier and initial state. If the operation only accepts an asynchronous job, 202 Accepted should clearly explain that the job has been accepted but is not yet complete.

### 4.1. Describing Success

For each successful response, state:

- The HTTP status and its meaning.
- Returned data, especially resource identifiers and state.
- Headers needed for subsequent interactions.
- Effects already completed at the time the response is returned.
- Effects that will occur afterward and the conditions under which they happen.

Do not use vague descriptions like "Success" when clients need to know whether a resource was created, updated, deleted, or only queued for processing.

### 4.2. Describing Errors and Unmet Preconditions

Not every error is 400 Bad Request. Choose status codes according to the nature of the outcome:

| Status | Typical Situation | Information to Explain |
|---|---|---|
| 400 Bad Request | Invalid syntax or parameters | Incorrect fields, formats, or validation rules |
| 401 Unauthorized | Missing or invalid authentication credentials | Required authentication method |
| 403 Forbidden | Caller is authenticated but lacks permission | Access permission requirements |
| 404 Not Found | Resource not found or its existence cannot be disclosed | Which resource was not found |
| 409 Conflict | Current state conflicts with the request | Which state prevents the operation from executing |
| 412 Precondition Failed | Conditional HTTP header, such as If-Match, is not met | How to fetch the latest version and retry |
| 422 Unprocessable Content | Syntactically valid content that violates processing rules per API policy | Violated business rule |
| 429 Too Many Requests | Rate limit exceeded | When to retry if available |

These are common situations, not a mandatory list for every operation. Only publish responses the API can actually return. Descriptions must match exception handlers, Spring Security, gateways, and runtime implementation.

## 5. How Does OpenAPI Express Preconditions and Outcomes?

OpenAPI has no dedicated standard fields for preconditions or postconditions. We combine the following components:

| OpenAPI Component | Information That Can Be Described |
|---|---|
| summary | Main purpose of the operation |
| description | Purpose, business preconditions, state transition rules, and effects |
| security | Required authentication mechanisms |
| parameters | Conditions passed via path, query, header, or cookie |
| requestBody | Data required to perform the operation |
| schema | Types, required fields, limits, and valid values |
| responses | Success and error outcomes |
| headers | Outcome metadata such as Location, ETag, or Retry-After |
| links | Links a response to a follow-up operation when describable |

If an organization needs a specific business condition to be machine-readable, it can standardize on an OpenAPI Specification Extension starting with x-. However, extensions are custom conventions; Swagger UI or client generators may ignore them if unsupported. For most APIs, a clear description combined with complete schemas and responses is sufficient.

## 6. Business Example: Creating an Order and Reserving Inventory

Suppose an API provides an order creation operation at POST /api/v1/orders. The customer sends a list of products and quantities. The operation has these rules:

- The caller must be authenticated and have permission to place orders in the current account.
- The customer account must be active.
- Every product must exist and currently be on sale.
- Each line item quantity must be an integer from 1 to 20.
- Inventory is checked and reserved within the same order creation flow.
- If full reservation is not possible, the entire request fails and no partial order is created.

On success:

- The API returns 201 Created.
- The order has status PENDING_PAYMENT.
- Inventory is reserved for 15 minutes.
- The response returns the order ID, total amount, status, and reservation expiration timestamp.
- The Location header points to the order URI.

If the customer does not pay before the deadline, the order expires and the reserved inventory is released according to system policy. This is an observable business outcome later in time, so the documentation should clearly state the deadline and subsequent state.

### 6.1. Describing the Operation in OpenAPI YAML

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      tags:
        - Orders
      summary: Create order and reserve inventory
      description: |
        Creates an order from the customer-submitted list of products and quantities.

        **Preconditions**
        - Caller is authenticated and has permission to place orders in the current account.
        - Customer account is active.
        - All products exist and are currently on sale.
        - Quantity for each product is an integer from 1 to 20.
        - Inventory can fulfill the entire request at processing time.

        **Outcomes on success**
        - Order is created in PENDING_PAYMENT status.
        - Inventory is reserved for 15 minutes.
        - Response contains the order ID, total amount, and reservation expiration timestamp.
        - Location header contains the URI of the new order.

        If full reservation is not possible, the request fails and no partial order is created.
        If the customer does not pay before the deadline, the order expires
        and reserved inventory is released.
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order was created and inventory was reserved.
          headers:
            Location:
              description: URI of the new order.
              schema:
                type: string
                format: uri-reference
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          description: Request is missing required fields or has improperly formatted values.
        '401':
          description: Missing access token or invalid token.
        '403':
          description: Caller does not have permission to place orders for this account.
        '404':
          description: One or more requested products were not found.
        '409':
          description: Insufficient inventory or product state no longer permits ordering.
        '422':
          description: Account is inactive or business rules are not satisfied.
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - items
      properties:
        items:
          type: array
          minItems: 1
          items:
            type: object
            required:
              - productId
              - quantity
            properties:
              productId:
                type: integer
                format: int64
              quantity:
                type: integer
                minimum: 1
                maximum: 20
    OrderResponse:
      type: object
      required:
        - orderId
        - status
        - total
        - reservationExpiresAt
      properties:
        orderId:
          type: string
          example: ord_1024
        status:
          type: string
          enum:
            - PENDING_PAYMENT
        total:
          type: number
          format: double
          example: 1250000
        reservationExpiresAt:
          type: string
          format: date-time
          description: Inventory reservation expiration time in UTC.
```

The description above informs callers of both preconditions and outcomes. Responses are also separated by scenario so clients can handle them properly. In a real project, status codes and error schemas must match the backend implementation; do not declare 404, 409, or 422 if the API does not return them.

### 6.2. Adding the Description to a Spring Boot Controller

Springdoc reads OpenAPI annotations on controllers to enrich the document. Abbreviated example:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders")
@Tag(name = "Orders", description = "Order management API")
public class OrderController {

    @PostMapping
    @Operation(
        operationId = "createOrder",
        summary = "Create order and reserve inventory",
        security = @SecurityRequirement(name = "bearerAuth"),
        description =
            "Creates an order from the customer-submitted list of products and quantities. " +
            "\n\n**Preconditions**\n" +
            "- Caller is authenticated and has permission to place orders in the current account.\n" +
            "- Customer account is active.\n" +
            "- All products exist, are on sale, and have sufficient inventory.\n" +
            "- Quantity for each product is an integer from 1 to 20.\n" +
            "\n**Outcomes on success**\n" +
            "- Order is created in PENDING_PAYMENT status.\n" +
            "- Inventory is reserved for 15 minutes.\n" +
            "- Response contains the order ID, total amount, and reservation expiration timestamp.\n" +
            "- If full reservation is not possible, no partial order is created."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Order was created and inventory was reserved.",
            headers = @Header(
                name = "Location",
                description = "URI of the new order."
            ),
            content = @Content(
                schema = @Schema(implementation = OrderResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Request is missing required fields or has improperly formatted values."
        ),
        @ApiResponse(
            responseCode = "401",
            description = "Missing access token or invalid token."
        ),
        @ApiResponse(
            responseCode = "403",
            description = "Caller does not have permission to place orders for this account."
        ),
        @ApiResponse(
            responseCode = "404",
            description = "One or more requested products were not found."
        ),
        @ApiResponse(
            responseCode = "409",
            description = "Insufficient inventory or product is no longer on sale."
        ),
        @ApiResponse(
            responseCode = "422",
            description = "Account is inactive or business rules are not satisfied."
        )
    })
    public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        OrderResponse response = orderService.create(request);
        URI location = URI.create("/api/v1/orders/" + response.orderId());
        return ResponseEntity.created(location).body(response);
    }
}
```

This example illustrates annotation structure; types CreateOrderRequest, OrderResponse, and orderService must be defined according to your application. The example assumes OrderResponse has an orderId() accessor and the bearerAuth scheme is declared in shared OpenAPI configuration. The java.net.URI import must be included for the Location variable.

@Valid enables Bean Validation for the request DTO. OpenAPI annotations describe the public contract; they do not enforce order permissions, inventory checks, or reservation timeouts. Those conditions must be implemented and tested by the backend.

## 7. Describing HTTP-Level Preconditions

Beyond business conditions, HTTP also provides conditional request mechanisms. For example, a client wants to update a resource only if it has not changed since the last read. The client can send the If-Match header with the previously received ETag:

```yaml
paths:
  /api/v1/products/{productId}:
    put:
      summary: Update product if version is unchanged
      description: |
        Updates only when the product's current ETag matches the If-Match
        value sent by the client. If the product has changed since it was read,
        the server does not apply the update and returns 412 Precondition Failed.
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: integer
            format: int64
        - name: If-Match
          in: header
          required: true
          description: ETag of the product version the client read.
          schema:
            type: string
      responses:
        '200':
          description: Product was updated.
          headers:
            ETag:
              description: New ETag of the product.
              schema:
                type: string
        '412':
          description: ETag no longer matches; client must re-read the resource before retrying the update.
```

In this case, If-Match is an HTTP-layer condition. It differs from a business condition such as "the order must be in DRAFT status". Both need to be described, though their checking mechanisms and status codes can differ.

## 8. Describing Synchronous and Asynchronous Outcomes

An operation can complete immediately during the request or simply accept work for processing.

| Processing Type | Common Responses | What Clients Need to Know |
|---|---|---|
| Synchronous completion | 200 OK, 201 Created, 204 No Content | The outcome is already final when the response arrives |
| Asynchronous acceptance | 202 Accepted | Work has been accepted; does not yet mean completion |

For 202 Accepted, describe how clients track the outcome: status URI in the response body, Location header, webhook callback, or another notification mechanism. Also state intermediate states and terminal outcomes such as completed, failed, or expired.

Example:

```yaml
responses:
  '202':
    description: Report export request has been accepted; file generation is in progress.
    headers:
      Location:
        description: URI to query task status.
        schema:
          type: string
          format: uri-reference
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/JobAccepted'
```

Do not describe 202 with "Report exported successfully" if the file has not been generated yet. Integrators need to know which state the job is in and what to do next.

## 9. Writing Readable and Testable Descriptions

A useful description should answer items in order:

1. **Purpose:** what need does the operation address?
2. **Target:** which resource or entity is affected?
3. **Preconditions:** what permissions, state, input data, and related resources must be satisfied?
4. **Processing rules:** which limits or business decisions affect the outcome?
5. **Success outcome:** what are the HTTP status, data, headers, and resource state?
6. **Failure outcomes:** what conditions lead to each error code and what should the client do?
7. **Time-based effects:** are there deadlines, background processing, resource releases, or follow-up steps?

Short yet informative description example:

```text
Creates a refund request for a paid transaction.

Preconditions:
- The transaction exists and belongs to the caller's account.
- The transaction is in PAID status.
- The refund amount is greater than 0 and does not exceed the remaining refundable amount.
- The caller has refund management permission.

Outcomes:
- Returns 201 when the refund request is created.
- The request starts in PENDING_REVIEW status.
- The response includes refundId and the request creation timestamp.
- Returns 409 if the transaction no longer has sufficient refundable balance or its status does not allow a refund.

A request in PENDING_REVIEW status does not yet mean funds have been returned to the account.
```

Each condition can be turned into one or more test cases. For example, a PAID transaction creates the request successfully; a CANCELLED transaction returns 409; an unauthorized caller receives 403; an amount of 0 is rejected by validation rules.

## 10. Avoiding Misleading Descriptions

| Weak Writing | Problem | Better Writing |
|---|---|---|
| "Performs order creation." | Does not state what status the order is created in | "Creates an order in PENDING_PAYMENT status and reserves inventory for 15 minutes." |
| "Request must be valid." | Does not specify validity criteria | State required fields, value ranges, and business rules |
| "Returns error if unsuccessful." | Does not help clients classify errors | Declare separate responses for 400, 401, 403, 404, 409... when actually supported |
| "202: Success." | May mislead clients into thinking the job is finished | Clearly state the task was accepted and how to poll status |
| "Only admins can call this." | Does not specify the security mechanism or admin scope | Describe the security scheme and specific permissions per API policy |
| "System processes via internal workflow." | Provides no observable outcomes | Describe the status, response, headers, and deadlines visible to clients |
| "Not found or invalid." | Lumps distinct scenarios together | Separate 404, 409, or 422 according to the actual contract |

Do not make commitments the system does not guarantee. For example, if the API only checks stock before creating an order without reserving it, do not write that inventory is reserved. If payment processing is asynchronous, do not describe the acceptance response as payment completion.

## 11. Integrating Operation Descriptions into the Development Workflow

To keep descriptions from going stale, treat them as part of the contract that must be updated alongside controllers and DTOs.

When adding or changing an operation:

1. Identify the business need the operation solves.
2. Document permissions, resource states, and input conditions.
3. Define success outcomes along with possible error responses.
4. Describe response body, schemas, and headers so clients can use the result.
5. Add @Operation, @Parameter, @ApiResponse, or @Schema in appropriate places.
6. Inspect the JSON/YAML document generated by springdoc.
7. Write tests for key conditional branches and compare actual behavior against documentation.

You can check the default documentation endpoint with:

```bash
curl -s http://localhost:8080/v3/api-docs
```

In the JSON document, locate the operation's path and method, then verify summary, description, parameters, requestBody, security, and responses. Open Swagger UI to check whether the displayed content is readable and clear enough for integrators.

In CI, you can add checks ensuring public operations have summaries, descriptions, success responses, and error responses per project conventions. Contract tests should verify both schemas and the business outcomes promised by the description.

## 12. Key Takeaways

- summary briefly states the purpose; description explains usage motivation and business rules.
- Preconditions can involve identity, permissions, resource state, input data, and dependent resources.
- Observable outcomes include status codes, response bodies, headers, resource state, and follow-up effects.
- OpenAPI has no dedicated standard fields for preconditions/postconditions; combine description, security, parameters, requestBody, schemas, responses, and headers.
- Every response must describe what clients can actually observe; clearly distinguish completed processing from newly accepted requests.
- OpenAPI annotations only describe the contract. The backend must still enforce and test business conditions.
- Good descriptions help integrators call the right operation, handle outcomes properly, and help developers turn contracts into test cases.

When writing documentation with springdoc-openapi, describe operations from the API caller's perspective: why they need the action, which conditions they must satisfy, and which outcomes they can rely on. A clear contract keeps client integrations stable and ensures business changes are evaluated accurately.
