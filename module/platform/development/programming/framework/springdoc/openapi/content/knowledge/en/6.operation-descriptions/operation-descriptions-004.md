# Unique, Stable operationId and Its Impact on Client Code Generators

In an OpenAPI document, each operation can have an <code>operationId</code> field to identify that operation with a string. This field is often used by client SDK generators as the basis for naming methods, and it can also be referenced from other parts of the specification. Therefore, a good <code>operationId</code> must be unique across the document, easy to understand, and stable across source code changes.

When using springdoc-openapi, you can declare this value directly via the <code>operationId</code> attribute of the <code>@Operation</code> annotation. Treat it as part of the API contract published to consumers, rather than merely an internal Java method name.

## 1. What is operationId?

<code>operationId</code> is an optional field in the OpenAPI Operation Object. Its value is a unique string used to identify the operation within the document.

~~~yaml
paths:
  /customers/{customerId}:
    get:
      operationId: getCustomerById
      summary: Get customer information
      responses:
        "200":
          description: Customer found
~~~

In the example, the operation is identified by the combination of HTTP method <code>GET</code> and path <code>/customers/{customerId}</code>. The value <code>getCustomerById</code> is the published identifier name for that operation.

Distinguishing the components:

| Component | Example | Role |
|---|---|---|
| HTTP method | <code>GET</code> | HTTP action of the operation |
| Path | <code>/customers/{customerId}</code> | Resource address |
| <code>operationId</code> | <code>getCustomerById</code> | Unique identifier of the operation in the document |
| <code>summary</code> | <code>Get customer information</code> | Short title for readers |
| Java method name | <code>findCustomer</code> | Implementation method name in the application |

These values serve different purposes. Renaming a Java method does not necessarily require changing <code>operationId</code>; changing a path also does not mandate changing it if the operation still represents the same business action and the contract is managed compatibly.

## 2. Uniqueness Rule in the Document

According to the OpenAPI Specification, if <code>operationId</code> is declared, that value must be unique among all operations in the API document. The uniqueness scope is the entire document, not just within a single path, controller, or tag.

The following example has a duplicate:

~~~yaml
paths:
  /customers:
    get:
      operationId: getResource
      responses:
        "200":
          description: OK
  /orders:
    get:
      operationId: getResource
      responses:
        "200":
          description: OK
~~~

The two operations have different paths but share the same <code>operationId</code>. The document fails the uniqueness requirement; code generators may report an error, produce conflicting method names, or behave inconsistently.

Corrected example:

~~~yaml
paths:
  /customers:
    get:
      operationId: listCustomers
      responses:
        "200":
          description: OK
  /orders:
    get:
      operationId: listOrders
      responses:
        "200":
          description: OK
~~~

Even when documentation is split into multiple groups using GroupedOpenApi, name consistently and avoid duplicates across groups if the specifications might be merged or share an SDK generation pipeline. The OpenAPI mandatory rule applies to each exported document.

## 3. Choosing Meaningful and Usable operationId Names

Use short names that describe the action and business entity. In the Java ecosystem, lower camel case is generally easy to read:

| Action | Suggested operationId |
|---|---|
| List customers | <code>listCustomers</code> |
| Get a customer by ID | <code>getCustomerById</code> |
| Create a customer | <code>createCustomer</code> |
| Update a customer | <code>updateCustomer</code> |
| Delete a customer | <code>deleteCustomer</code> |
| Search orders | <code>searchOrders</code> |

A good naming convention typically has these traits:

- Starts with an action verb such as <code>get</code>, <code>list</code>, <code>create</code>, <code>update</code>, <code>delete</code>, or <code>search</code>.
- Clearly specifies the business entity, such as <code>Customer</code> or <code>Order</code>.
- Uses a meaningful suffix when disambiguation is needed, e.g., <code>getCustomerById</code> and <code>getCustomerByEmail</code>.
- Avoids generic names such as <code>getData</code>, <code>process</code>, <code>execute</code>, or names dependent on endpoint ordering.
- Avoids spaces, punctuation, and characters that do not map cleanly to identifiers in programming languages.

OpenAPI requires the value to be a unique string; lower camel case is a design choice to improve readability and compatibility with code generators, not a mandatory syntax rule of the specification.

## 4. Declaring operationId with springdoc-openapi

For Spring MVC or Spring WebFlux using annotated controllers, declare <code>operationId</code> in <code>@Operation</code>:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/customers")
class CustomerController {

    @Operation(
        operationId = "getCustomerById",
        summary = "Get customer information by ID"
    )
    @GetMapping("/{customerId}")
    CustomerResponse getCustomer(
            @PathVariable String customerId) {
        // Find and return customer
        return new CustomerResponse(customerId, "Lan");
    }
}

record CustomerResponse(String id, String name) {}
~~~

When springdoc generates the document, the corresponding operation will have metadata roughly like this:

~~~yaml
paths:
  /customers/{customerId}:
    get:
      operationId: getCustomerById
      summary: Get customer information by ID
      parameters:
        - name: customerId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
~~~

The example focuses on where the declaration goes; actual response content depends on the application's DTOs and annotations. If <code>operationId</code> is omitted, springdoc may derive a value from handler metadata. Default generation can depend on library version and controller structure, so declare it explicitly for operations that are part of an SDK or public contract.

## 5. How Does the operationId Name Affect Code Generators?

Many client code generation tools use <code>operationId</code> as the basis for naming functions in the SDK. The exact transformation depends on the generator, language, and configuration, as illustrated below:

| operationId in OpenAPI | Generated Method Name Example |
|---|---|
| <code>listCustomers</code> | <code>listCustomers()</code> |
| <code>getCustomerById</code> | <code>getCustomerById(id)</code> |
| <code>createCustomer</code> | <code>createCustomer(request)</code> |
| <code>deleteCustomer</code> | <code>deleteCustomer(id)</code> |

For example, a Java client SDK might expose the call:

~~~java
Customer customer = customerApi.getCustomerById("C-100");
~~~

If the backend team renames <code>operationId</code> from <code>getCustomerById</code> to <code>fetchCustomer</code> while keeping the HTTP method and path unchanged, the regenerated client SDK may rename the corresponding method. Applications consuming the SDK may fail to compile until calling code is updated.

Therefore, changing <code>operationId</code> can be a source-level breaking change for the SDK, even when the HTTP endpoint still works as before. For SDKs distributed to external customers or multiple internal teams, manage this change as part of contract versioning.

Beyond method names, some tools use <code>operationId</code> for variable names, documentation anchors, telemetry operation names, or link mappings. Inspect the output of your specific generator instead of assuming every tool maps it identically.

## 6. Keeping operationId Stable Across Refactorings

When an operation still represents the same business action, keep <code>operationId</code> unchanged even if the Java method name or controller organization changes.

Example before refactoring:

~~~java
@Operation(operationId = "getCustomerById")
@GetMapping("/{id}")
CustomerResponse findCustomer(@PathVariable String id) {
    // ...
}
~~~

After renaming the internal method:

~~~java
@Operation(operationId = "getCustomerById")
@GetMapping("/{customerId}")
CustomerResponse loadCustomer(@PathVariable String customerId) {
    // ...
}
~~~

In the example, the Java method and path variable name changed, yet the public identifier remained stable. This allows generators to continue producing the same client method name if other parts of the contract do not alter the signature.

Keeping it stable does not mean retaining an old name for an action whose meaning has changed. If an operation is replaced with different business behavior, treat it as a new operation and pick a new identifier. If an old operation needs to be retired, mark it deprecated in the specification, maintain it during a transition window, and remove it according to your compatibility policy.

### 6.1. Which Changes Should Preserve operationId?

| Internal or Contract Change | Typically Appropriate Action |
|---|---|
| Rename Java method without changing action | Keep unchanged |
| Move method to another controller | Keep unchanged if it is still the same operation |
| Rename <code>@PathVariable</code> variable | Keep unchanged if action is unchanged |
| Change implementation or called service | Keep unchanged if contract behavior is unchanged |
| Change path while keeping same action with a compatibility plan | Can keep unchanged; evaluate URL breaking change separately |
| New operation with a different purpose | Create a new operationId |
| Remove old operation and replace with another | Manage deprecation/removal and new identifier per versioning policy |

### 6.2. operationId Can Also Be Referenced in OpenAPI Link

An OpenAPI Link Object can use the <code>operationId</code> field to reference another operation. For example, a create-order response can link to the operation that fetches the newly created order:

~~~yaml
responses:
  "201":
    description: Order created
    links:
      GetCreatedOrder:
        operationId: getOrderById
        parameters:
          orderId: "$response.body#/id"
~~~

In this case, <code>getOrderById</code> must match the <code>operationId</code> of the target operation in the document. Renaming an operationId without updating referencing Links can break links in the contract.

## 7. Avoiding Collisions Across Multiple Controllers

In large applications, multiple controllers may declare Java methods named <code>getById</code>. If springdoc is left to auto-derive identifiers, handler structures can lead to undesirable or hard-to-maintain values. Choose a resource-prefixed convention to prevent collisions:

~~~java
@Operation(operationId = "getCustomerById")
@GetMapping("/customers/{id}")
CustomerResponse getCustomerById(@PathVariable String id) {
    // ...
}

@Operation(operationId = "getOrderById")
@GetMapping("/orders/{id}")
OrderResponse getOrderById(@PathVariable String id) {
    // ...
}
~~~

If the API has multiple groups or versions, consider how the documents are consumed:

- Each independently exported OpenAPI document must have no duplicate operationIds within that document.
- If multiple groups are merged into one document or share a single SDK, ensure operationIds do not collide after merging.
- Do not rely on tag names alone to distinguish operationIds; tags do not expand the uniqueness scope of this field.

## 8. Verifying operationId in the Generated Document

After declaring annotations, inspect the specification at the default endpoint:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

In JSON, locate the <code>operationId</code> fields under each HTTP operation. For large documents, you can use <code>jq</code> to list them:

~~~bash
curl -s http://localhost:8080/v3/api-docs |
  jq -r '.paths | to_entries[] | .key as $path |
    .value | to_entries[] |
    select(.value.operationId != null) |
    [$path, .key, .value.operationId] | @tsv'
~~~

The output helps cross-check paths, HTTP methods, and operationIds. Then verify the following:

1. Every operation needing an identifier has an <code>operationId</code>.
2. No two operations share the same value within the same document.
3. Names reflect the action and resource.
4. Values do not change unexpectedly after renaming methods or moving controllers.
5. Any Link Object referencing an operationId still points to the correct operation.
6. The generated client SDK has the expected method names and signatures.

When the API feeds into code generation, store the released OpenAPI specification and diff it against new builds in CI. You can make uniqueness and operationId-change checks a contract verification step before release.

## 9. Pre-Release Review Checklist

- [ ] Every public operation has an explicit <code>operationId</code>.
- [ ] Values are unique across all operations in each document.
- [ ] Names use meaningful verbs and resource names.
- [ ] Identifiers do not depend on Java method names or controller declaration order.
- [ ] Internal refactoring does not unintentionally alter public identifiers.
- [ ] Link Objects and references using operationId have been reviewed.
- [ ] Test-generated the client SDK to confirm method names.
- [ ] operationId changes are evaluated during compatibility and contract versioning reviews.

## References

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): rules and semantics of <code>operationId</code>.
- [OpenAPI Specification – Link Object](https://spec.openapis.org/oas/latest.html#link-object): referencing operations via <code>operationId</code>.
- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html): integrating springdoc-openapi with Spring Boot.
- [Swagger Core – Operation annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Operation.html): the <code>operationId</code> attribute of the <code>@Operation</code> annotation.
- [OpenAPI Generator](https://openapi-generator.tech/docs/): how client/server generation tools use OpenAPI documents and generator options.
