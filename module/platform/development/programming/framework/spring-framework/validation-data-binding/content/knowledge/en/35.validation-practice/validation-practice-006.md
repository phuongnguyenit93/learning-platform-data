# Organizing Bean Validation for Create and Update in Spring Framework

For the same resource, **create**, **full replace/update (update/PUT)**, and **partial update (PATCH)** usually have different input rules. Using a single DTO with `@NotNull`, `@NotBlank`, and `@Size` across every endpoint without defining clear behavior leads to two opposite bugs:

- **Validation too strict:** a PATCH endpoint that only wants to update `name` gets rejected because `sku` or `price` was not sent.
- **Validation too loose:** a developer drops `@NotNull` so PATCH works, causing POST create to accept requests missing required fields.

Spring Framework supports Jakarta Bean Validation with `@Valid`, `@Validated`, validation groups, cascaded validation, and custom constraints. However, **choosing the right rules per operation is an API design decision**, not something you can leave up to annotations alone.

This hands-on lesson belongs to the **Practice** group of the **Spring Framework — validation-data-binding** module. It covers two organizational strategies: **dedicated request DTOs per operation (preferred by default)** and **Bean Validation groups when reusing one model is genuinely warranted**; distinguishing POST, PUT, and PATCH; nested DTOs, group inheritance/conversion, error handling, field modification permissions, service invariants, and testing.

The complete example uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Jakarta Bean Validation 3.x, Spring MVC Servlet, and JUnit 5/MockMvc**. These versions serve to make the lesson reproducible, not as a claim that they are always the latest.

## 1. Define the API Contract Before Writing Annotations

Suppose a product management system has the following data:

~~~json
{
  "id": 42,
  "sku": "PEN-001",
  "name": "Blue pen",
  "price": 19.90,
  "description": "Blue ballpoint pen"
}
~~~

Rules:

- `id` is assigned by the server; clients cannot change it.
- `sku` is required on creation and **immutable** thereafter (cannot be modified by PUT/PATCH).
- `name` is required, must not be blank, max 100 characters.
- `price` is required and must be a non-negative decimal.
- `description` is optional, max 500 characters.
- On PUT update, the client must supply the **full set of updatable fields** (`name`, `price`; `description` may be null to clear it).
- On PATCH, an **absent field** means keep the existing value, while a **present field with null** must have clearly defined semantics.

### Operation Matrix

| Field | POST /products | PUT /products/{id} | PATCH /products/{id} |
|---|---|---|---|
| `id` | Server-generated, not accepted from client | Path ID, not bound from body | Path ID, not bound from body |
| `sku` | Required and properly formatted | Cannot be updated | Cannot be updated |
| `name` | Required, non-blank | Required, non-blank | If present, must be non-blank |
| `price` | Required, non-negative | Required, non-negative | If present, must be non-negative |
| `description` | May be null | May be null to clear description | Absent = keep; null = clear description |
| Unknown fields | Choose explicit reject or ignore | Choose explicit reject or ignore | Should reject keys outside allowlist |
| Field permissions | Server-controlled | Mutable fields set only | Mutable fields set only |

Having **action-specific rule sets** is not just about annotations. It also involves **field ownership, HTTP semantics, authorization, concurrent updates, transactions, and how data is merged**.

## 2. Three Validation Organization Strategies

### Option A — Dedicated DTOs for Create and Update (Recommended Default)

~~~java
public record CreateProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price,
    @Size(max = 500) String description
) {
}

public record ReplaceProductRequest(
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price,
    @Size(max = 500) String description
) {
}
~~~

These are snippets; runnable classes with full imports/constraints are in section 9.

Pros:

- Each endpoint's contract is **explicit on its DTO**.
- `sku` is absent from the update DTO, reducing mass assignment risk.
- API docs/OpenAPI clearly show required fields for POST vs PUT.
- Tests are easy to read without tracking which group is active.
- Easy to evolve when two APIs diverge over time.

Cons: annotations on shared fields may be repeated. For small and medium APIs, **a bit of duplication in request contracts is usually better than an abstraction that hides business differences**.

### Option B — One Model with Bean Validation Groups

~~~java
public record GroupedProductInput(
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price,
    @NotBlank(groups = OnCreate.class) String sku
) {
}
~~~

Then select groups per endpoint with Spring `@Validated(...)`. This fits when a model shares many constraints and differs on only a few rules by action, yet it **does not make dangerous fields vanish from the object**. You still must control mapping/allowlisting.

### Option C — Combining Separate DTOs + Internal Groups

You can keep **separate DTOs at the API boundary** while using **custom reusable constraints**, composed constraints, shared validators, or groups inside nested objects whose logic genuinely varies. This reduces duplication while keeping external contracts clear.

**Choice for this lesson:** the runnable POST/PUT code uses **separate DTOs**; section 12 demonstrates groups with standalone unit tests. PATCH is explained separately because it has absent/null semantics that groups alone do not solve.

## 3. Why Is a Single DTO with All Nullable Fields Error-Prone?

Common pitfall:

~~~java
public record ProductRequest(
    String sku,
    String name,
    BigDecimal price,
    String description
) {
}
~~~

Without validation or conditional checks, POST could create a product missing a SKU, PUT could save a null name, and the service might forget to check a field. Adding `@NotNull` to everything instead prevents PATCH from updating a single field.

A second counterexample:

~~~java
public record ProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull BigDecimal price
) {
}
~~~

If this same DTO is used for PUT, the client must resend `sku`. If a mapper accidentally copies SKU from the body onto the entity, clients can modify a field meant to be immutable.

**Design principle:** distinguish **required fields**, **modifiable fields**, and **fields present in the request**. `@NotNull` addresses only part of the first; it does not solve the other two.

### Entities Differ from Request DTOs

An entity often also has `id`, `ownerId`, `role`, `status`, `createdAt`, `version`, and internal associations. Never bind `@RequestBody`/`@ModelAttribute` directly onto a JPA managed entity and let the client decide which fields change.

The flow should be:

~~~text
HTTP body -> Request DTO -> Validation -> Authorization
                                |
                                v
                     Service / domain invariants
                                |
                                v
                    Explicit allowed-field mapping
                                |
                                v
                   Transaction + repository/entity
~~~

Each POST/PUT/PATCH operation can use its own DTO/command and mapping.

## 4. Meaning of Commonly Used Annotations

| Annotation | Condition | Is null valid? | Notes |
|---|---|---|---|
| `@NotNull` | Value is non-null | No | Does not check blank strings |
| `@NotBlank` | CharSequence has non-whitespace content | No | Good for required name/SKU |
| `@NotEmpty` | Collection/String/array/map is non-empty | No | Whitespace-only string still has length |
| `@Size(min,max)` | Length/element count within bounds | Usually yes | Combine with NotNull/NotBlank when required |
| `@DecimalMin("0.00")` | Numeric ≥ 0.00 | Usually yes | Suitable for BigDecimal |
| `@Positive` | Number > 0 | Usually yes | Price of 0 is invalid if Positive is used |
| `@Pattern` | String matches regex | Usually yes | Does not replace `@NotBlank` |
| `@Email` | Email format per provider | Usually yes | Does not verify email ownership |
| `@Valid` | Cascaded validation | Ignores nested null | Not a constraint itself |
| `@Validated(...)` | Spring activation/groups | Does not mean “null-safe” | Use at the proper Spring MVC position |

Create SKU example:

~~~java
@NotBlank
@Size(min = 3, max = 32)
@Pattern(regexp = "[A-Z0-9-]+")
String sku
~~~

`@Pattern` checks format; `@Size` checks length; `@NotBlank` rejects null/blank. With these constraints, **do not rely on annotation declaration order to infer execution order**.

### Price Is BigDecimal; Avoid double for Money

In Java, `BigDecimal` represents decimal monetary values far more appropriately than `double`. `@DecimalMin("0.00")` checks non-negative prices; you still need precision/scale checks, currency units, rounding rules, and maximum limits in the domain layer/DB schema.

If the system allows a price of 0, do not use `@Positive`. If prices must be strictly positive, use `@DecimalMin(value="0.00",inclusive=false)` or `@Positive` depending on the data type.

## 5. POST Create: The Validation Boundary

POST endpoint accepting `CreateProductRequest`:

~~~java
@PostMapping
public ResponseEntity<Product> create(
        @Valid @RequestBody CreateProductRequest request) {
    Product result = service.create(request);
    return ResponseEntity.created(
        URI.create("/api/products/" + result.id()))
        .body(result);
}
~~~

When a provider is present, `@Valid` on the argument causes Spring MVC to validate the DTO after JSON deserialization. If a constraint fails on a regular command object, Spring MVC typically throws **`MethodArgumentNotValidException`** and returns HTTP **400** by default before the method body executes.

However, there are mechanistic exceptions:

- If the method has **direct constraint annotations on parameters/return values**, Spring MVC 6.1+ may use method validation and throw `HandlerMethodValidationException` instead of argument-level validation alone.
- If the handler places `Errors`/`BindingResult` **immediately after** the argument, it can handle errors locally.
- If no provider is on the classpath, annotations may not run as expected.
- `@Valid` does not validate a DTO constructed outside the controller when Java code calls a service directly; the service needs its own boundary if that is a requirement.

To minimize ambiguity in the example, the controller **does not place `@Validated` at the class level**, has no direct constraints on `@PathVariable`, and does not accept `BindingResult`. Thus tests can assert `MethodArgumentNotValidException` on DTO input where appropriate.

### POST Is Not PUT with a Null ID

Do not merge both operations by accepting `id=null` to mean create and `id!=null` to mean update. That makes authorization harder to protect, idempotency harder to verify, and required fields harder to express. HTTP method and path should state the business intent.

## 6. PUT Update: Full Update of the Modifiable Portion

Endpoint:

~~~http
PUT /api/products/42
Content-Type: application/json

{
  "name": "Premium blue pen",
  "price": 25.00,
  "description": "Smooth ink flow"
}
~~~

In this example's contract:

- `id=42` comes from the **path**.
- `sku` is not editable and is absent from `ReplaceProductRequest`.
- `name` and `price` are required as a **complete representation of the mutable fields**.
- `description` absent/null is interpreted as clearing the description, because this is a full replacement per this contract.
- The service loads the existing resource, checks permissions, and updates **only allowed fields**.
- If the resource does not exist, return HTTP **404**.
- With optimistic locking, use `ETag/If-Match` or a version field and return HTTP 409/412 per contract.

Do not equate PUT with PATCH: a PUT sending only `{"name":"New pen"}` will receive HTTP 400 because `price` is missing in this example. That behavior is **intentional**, not an automatic Spring default.

### PUT and Idempotency

Calling a complete PUT request multiple times with the **same resource state** should converge to the same final resource state, even if response metadata varies by system. For idempotent updates, avoid emitting duplicate records/events merely because a request was retried.

For POST create, idempotency is not guaranteed merely because two requests look identical. Systems may need an idempotency key or unique SKU policy in the service.

## 7. PATCH: Three States — Absent, Null, Has Value

PATCH differs from PUT by **sending only the fields to modify**.

Example current resource:

~~~json
{
  "name": "Blue pen",
  "price": 19.90,
  "description": "Standard"
}
~~~

Three bodies with different meanings:

~~~json
{"name":"New blue pen"}
~~~

- `name` present and new → update name.
- `price` absent → keep existing price.
- `description` absent → keep existing description.

~~~json
{"description":null}
~~~

- `description` present with null → clear description per JSON Merge Patch semantics if used.
- Other fields absent → keep existing values.

~~~json
{"price":null}
~~~

- `price` present with null → per the demo policy **invalid**, because price is required on the merged resource.

### Why Is `record PatchRequest(String name, BigDecimal price)` Not Enough?

When Jackson deserializes an ordinary Java record, an **absent property** and a **property present with JSON null** both become Java `null` unless a separate presence mechanism is used. You cannot just write:

~~~java
if (patch.price() != null) {
    current.setPrice(patch.price());
}
~~~

and claim full PATCH support: that statement treats **explicit null** as “do not change”, so it cannot express clearing a field, and it also hides client errors trying to set a required field to null.

### Options for PATCH

1. **JSON Merge Patch (RFC 7396):** defines null as removing a member during merge; apply business rules to the merged result.
2. **JSON Patch (RFC 6902):** a list of add/remove/replace operations by path with its own content type; must validate paths and authorization.
3. **Presence wrapper:** a representation like `PatchField<T>` with `present: boolean`, `value: T` plus a custom Jackson deserializer or library.
4. **`JsonNode/ObjectNode` for a small set of fields:** distinguish `node.has("field")` and `node.get("field").isNull()`, then map selectively.
5. **Action-specific endpoints** if a resource has complex update rules, avoiding a catch-all generic PATCH.

Regardless of approach, the safe pipeline is:

~~~text
Read current resource + authorization
        |
        v
Parse PATCH with presence information
        |
        v
Reject unsupported paths/fields
        |
        v
Apply patch to a COPY / immutable candidate
        |
        v
Validate final candidate + cross-field invariants
        |
        v
Check version/concurrency
        |
        v
Persist atomically and publish effects safely
~~~

**Validating only the incoming fragment is not enough:** the interaction between a new field and an existing value can violate a domain rule. After merging, validate the **final state**.

## 8. Common Ways PATCH Goes Wrong

### Wrong: Reusing POST Validation

~~~java
public void patch(
    @Valid @RequestBody CreateProductRequest request) {
    // ...
}
~~~

A client wanting only to edit description gets rejected by `@NotBlank` on SKU/name. Removing `@NotBlank` to fix PATCH then breaks POST's required checks.

### Wrong: Having an Update Group Only Check Non-Null Fields

A rule like `@NotBlank(groups=Create.class)` with no constraint on Update can allow **PUT to omit name**. For full-replacement PUT, name must remain required.

### Wrong: Validating Each Field Before Merging

Updating price alone might violate a price/discount rule depending on the entity's category. Sometimes you must validate both the input fragment and the complete candidate.

### Wrong: Binding PATCH Directly onto a JPA Managed Entity

If one field fails conversion/validation after other fields have been mutated, the entity is partially modified; avoid dirty-checking side effects. Bind to a DTO/copy, validate, and only then apply permitted fields to the entity.

### Wrong: Letting PATCH Update Any Field with an Entity Setter

A client sends `id`, `sku`, `ownerId`, `stock`, or `status` and a mapper blind-copies it, causing mass assignment. Field allowlists are an authorization decision; **validation groups do not provide property-level authorization**.

## 9. Runnable Hands-On Project: Separate DTOs for POST and PUT

Create a Spring Boot 3.5.x, Java 17 project with **Spring Web**, **Validation**, and **Spring Boot Starter Test**. The application stores data **in-memory** to focus on validation without requiring a database.

Structure:

~~~text
product-validation/
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/productvalidation/
    ProductValidationApplication.java
    CreateProductRequest.java
    ReplaceProductRequest.java
    ProductService.java
    ProductController.java
    ProductGroups.java
    GroupedProductInput.java
  src/test/java/com/example/productvalidation/
    ProductControllerTest.java
    ProductServiceTest.java
    GroupedProductValidationTest.java
~~~

`build.gradle` in the project configures the Spring Boot plugin and corresponding dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Do not use `javax.validation.*` in Boot 3; use `jakarta.validation.*`.

### 9.1. `application.properties`

`src/main/resources/application.properties`:

~~~properties
# Choose policy to reject JSON properties outside the request DTO.
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

This is a Jackson feature on the Spring Boot-managed `ObjectMapper`, not a substitute for authorization. Enabling it application-wide can affect backward compatibility with clients already sending extra fields; in production, consider scoping or versioning before enabling.

**Why actively reject unknown fields?** If a client sends `sku` in PUT even though the DTO omits `sku`, many default Jackson configurations **ignore** it rather than rejecting it. Both are contract choices; this lesson uses **strict rejection** to illustrate protecting immutable fields.

### 9.2. `ProductValidationApplication.java`

`src/main/java/com/example/productvalidation/ProductValidationApplication.java`:

~~~java
package com.example.productvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProductValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ProductValidationApplication.class, args);
    }
}
~~~

### 9.3. `CreateProductRequest.java`

`src/main/java/com/example/productvalidation/CreateProductRequest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 32)
    @Pattern(regexp = "[A-Z0-9-]+")
    String sku,

    @NotBlank
    @Size(max = 100)
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @Size(max = 500)
    String description
) {
}
~~~

On POST, `sku` is required because of `@NotBlank`. `@Pattern` enforces uppercase ASCII/digits/hyphens without normalizing on the caller's behalf. For `price`, use `@NotNull` alongside `@DecimalMin` because `@DecimalMin` alone does not reject null.

### 9.4. `ReplaceProductRequest.java`

`src/main/java/com/example/productvalidation/ReplaceProductRequest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ReplaceProductRequest(
    @NotBlank
    @Size(max = 100)
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @Size(max = 500)
    String description
) {
}
~~~

Compared to the Create DTO:

- No `sku`; a SKU cannot be passed into the immutable replace command.
- `name` and `price` remain required, because this is **PUT**, not PATCH.
- `description` may be null.
- `id` is absent from both DTOs; the service generates it or takes it from the path.

### 9.5. `ProductService.java`

`src/main/java/com/example/productvalidation/ProductService.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProductService {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentHashMap<Long, Product> products =
        new ConcurrentHashMap<>();

    public Product create(CreateProductRequest request) {
        long id = nextId.incrementAndGet();

        Product created = new Product(
            id,
            request.sku(),
            request.name(),
            request.price(),
            request.description());

        products.put(id, created);
        return created;
    }

    public Product replace(
            long id, ReplaceProductRequest request) {

        Product updated = products.computeIfPresent(
            id, (key, previous) -> new Product(
                previous.id(),
                previous.sku(), // Keep existing SKU, never take from body.
                request.name(),
                request.price(),
                request.description()));

        if (updated == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found");
        }
        return updated;
    }

    public Product find(long id) {
        Product found = products.get(id);
        if (found == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found");
        }
        return found;
    }

    public record Product(
        long id,
        String sku,
        String name,
        BigDecimal price,
        String description
    ) {
    }
}
~~~

**Important:** this is an **in-memory illustrative service**, not a production implementation with uniqueness, idempotency, database transactions, optimistic locking, or authorization.

`ConcurrentHashMap.computeIfPresent(...)` replaces the record only when the key exists and preserves the old SKU. With a real database, protect immutable SKUs and these invariants **in the domain/service layer** even when the controller already validates the DTO.

### 9.6. `ProductController.java`

`src/main/java/com/example/productvalidation/ProductController.java`:

~~~java
package com.example.productvalidation;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService products;

    public ProductController(ProductService products) {
        this.products = products;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductService.Product> create(
            @Valid @RequestBody CreateProductRequest request) {

        ProductService.Product created =
            products.create(request);

        return ResponseEntity.created(
            URI.create("/api/products/" + created.id()))
            .body(created);
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ProductService.Product> replace(
            @PathVariable long id,
            @Valid @RequestBody ReplaceProductRequest request) {

        ProductService.Product result =
            products.replace(id, request);

        return ResponseEntity.ok(result);
    }

    @GetMapping("/{id}")
    public ProductService.Product get(@PathVariable long id) {
        return products.find(id);
    }
}
~~~

Both POST and PUT use `@Valid`, but with **different DTO classes**, so validation rules naturally differ. The controller neither accepts entities nor maps `id` or `sku` from the update body.

### 9.7. Running with Gradle

From the project directory with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If the machine only has Gradle without a wrapper, run `gradle wrapper` from an appropriately configured project and then run the wrapper.

### 9.8. Calling the API

Create a product:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"sku":"PEN-001","name":"But xanh","price":19.90,"description":"But bi"}'
~~~

On a fresh app with only one create request, expect HTTP **201 Created**, header `Location: /api/products/1`, and body:

~~~json
{
  "id": 1,
  "sku": "PEN-001",
  "name": "But xanh",
  "price": 19.90,
  "description": "But bi"
}
~~~

The ID may differ if the app has already received other requests; do not hard-code IDs in shared-data tests.

PUT replacing mutable fields:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"But xanh moi","price":25.00,"description":null}'
~~~

Expect HTTP **200 OK**, `sku` still `"PEN-001"`, updated `name`, updated `price`, and `description` null. In production, verify the user is authorized to update ID=1 before mutating it.

POST missing SKU:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"But xanh","price":19.90}'
~~~

Expect HTTP **400 Bad Request** because SKU is required for creation.

PUT missing price:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"But xanh moi"}'
~~~

Expect HTTP **400** because `price=null` violates `@NotNull` in the Replace DTO.

PUT attempting to change SKU:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1" \
  -H "Content-Type: application/json" \
  -d '{"sku":"HACKED","name":"But moi","price":25.00}'
~~~

Due to the strict Jackson unknown-field setting above, expect HTTP **400** from **JSON deserialization**, not from `@NotBlank`. If the strict setting is removed, Jackson may ignore SKU; even then, the service never takes SKU from the Replace DTO.

## 10. MockMvc Tests for POST and PUT

`src/test/java/com/example/productvalidation/ProductControllerTest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ProductService service;

    @Test
    void createValidReturns201AndLocation() throws Exception {
        var product = new ProductService.Product(
            42L, "PEN-001", "Pen",
            new BigDecimal("19.90"), "Blue");

        when(service.create(any(CreateProductRequest.class)))
            .thenReturn(product);

        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\"Pen\","
                    + "\"price\":19.90,\"description\":\"Blue\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/products/42"))
            .andExpect(jsonPath("$.sku").value("PEN-001"))
            .andExpect(jsonPath("$.price").value(19.90));

        verify(service).create(
            new CreateProductRequest(
                "PEN-001", "Pen",
                new BigDecimal("19.90"), "Blue"));
    }

    @Test
    void createBlankSkuReturns400BeforeService()
            throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"\",\"name\":\"Pen\","
                    + "\"price\":19.90}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("sku"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void createBlankNameReturns400BeforeService()
            throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\" \","
                    + "\"price\":19.90}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("name"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void createNegativePriceIsRejected() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\"Pen\","
                    + "\"price\":-0.01}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("price"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void createMissingPriceIsRejected() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\"Pen\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("price"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void putValidUpdatesMutableFields() throws Exception {
        var product = new ProductService.Product(
            42L, "PEN-001", "New Pen",
            new BigDecimal("25.00"), null);

        when(service.replace(
                eq(42L),
                any(ReplaceProductRequest.class)))
            .thenReturn(product);

        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"New Pen\","
                    + "\"price\":25.00,"
                    + "\"description\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("PEN-001"))
            .andExpect(jsonPath("$.name").value("New Pen"));

        verify(service).replace(
            42L,
            new ReplaceProductRequest(
                "New Pen", new BigDecimal("25.00"), null));
    }

    @Test
    void putMissingNameIsRejected() throws Exception {
        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"price\":25.00}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("name"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void putNegativePriceIsRejected() throws Exception {
        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"New Pen\",\"price\":-2.00}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("price"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void putUnknownSkuFieldIsRejected() throws Exception {
        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"HACKED\","
                    + "\"name\":\"New Pen\",\"price\":25.00}"))
            .andExpect(status().isBadRequest());

        // Rejected before the service can ever touch SKU.
        verifyNoInteractions(service);
    }

    @Test
    void putMissingResourceReturns404() throws Exception {
        when(service.replace(
                eq(404L),
                any(ReplaceProductRequest.class)))
            .thenThrow(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found"));

        mvc.perform(put("/api/products/404")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"New Pen\",\"price\":25.00}"))
            .andExpect(status().isNotFound());
    }
}
~~~

**Ten MockMvc tests** verify: valid POST 201/Location, POST missing SKU/name/price or negative price, valid PUT preserving SKU, PUT missing name/negative price, rejecting SKU not belonging to the update DTO, and PUT for a missing resource returning 404.

Tests with invalid input use `verifyNoInteractions(service)`, so they do not merely assert HTTP 400—they also ensure **the service is never called before validation passes**.

**Note:** `@WebMvcTest` tests the MVC slice and loads properties in the test context, but bypasses reverse proxies/API gateways. If the application has Spring Security filters, add valid authentication/CSRF tests. If configuring a custom `ObjectMapper`, verify strict unknown-field handling remains active.

## 11. Service Unit Tests: SKU Remains Immutable After PUT

`src/test/java/com/example/productvalidation/ProductServiceTest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductServiceTest {

    @Test
    void replaceKeepsSkuAssignedOnCreate() {
        ProductService service = new ProductService();

        var first = service.create(
            new CreateProductRequest(
                "PEN-001", "Pen",
                new BigDecimal("19.90"), "Blue"));

        var result = service.replace(
            first.id(),
            new ReplaceProductRequest(
                "Updated Pen",
                new BigDecimal("25.00"), null));

        assertEquals(first.id(), result.id());
        assertEquals("PEN-001", result.sku());
        assertEquals("Updated Pen", result.name());
        assertEquals(new BigDecimal("25.00"), result.price());
        assertEquals(null, result.description());
    }

    @Test
    void replacingUnknownIdDoesNotCreateRecord() {
        ProductService service = new ProductService();

        ResponseStatusException ex = assertThrows(
            ResponseStatusException.class,
            () -> service.replace(
                999L,
                new ReplaceProductRequest(
                    "Pen", new BigDecimal("10.00"), null)));

        assertEquals(HttpStatus.NOT_FOUND, ex.getStatusCode());
    }
}
~~~

**Two tests** verify controller-independent invariants: SKU stays unchanged after PUT, and updating a non-existent ID does not turn into a create. This is illustrative because the demo service lacks authorization; in production, invariants must be checked inside transactions and tested against race conditions.

### Running

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

The tests in this section are designed for Boot 3.5/Spring 6.2 and statically reviewed; **this article does not claim Gradle was executed**.

## 12. Alternative: Using Bean Validation Groups for Create/Update

When a DTO shares many fields and truly differs by only a few constraints, Bean Validation groups let you select a **constraint set** per operation.

### 12.1. Marker Interfaces

`src/main/java/com/example/productvalidation/ProductGroups.java`:

~~~java
package com.example.productvalidation;

public final class ProductGroups {

    private ProductGroups() {
    }

    public interface OnCreate {
    }

    public interface OnUpdate {
    }
}
~~~

These are **marker interfaces** with no methods. Jakarta Validation uses their `Class<?>` tokens to assign constraints to groups. They do not trigger any validation by themselves.

### 12.2. Shared DTO with Group-Specific Rules

`src/main/java/com/example/productvalidation/GroupedProductInput.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record GroupedProductInput(
    @NotBlank
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @NotBlank(groups = ProductGroups.OnCreate.class)
    String sku,

    @Size(max = 10, groups = ProductGroups.OnUpdate.class)
    String updateReason
) {
}
~~~

Here:

- `name` and `price` belong to the **Default group** because no `groups` are specified.
- `sku` is checked only when `OnCreate` is selected.
- `updateReason` is checked only when `OnUpdate` is selected.
- **No field-level authorization:** even though `sku` is not checked under the Update group, the property still exists on the DTO. The service **must not use** this value to alter SKU.

**Emphasis:** `@NotBlank(groups=OnCreate.class)` does not mean “forbid sending SKU on update”. It only states that the `NotBlank` constraint belongs to one group. If a client sends a new SKU, the property can still deserialize—unless API/mapper/DTO rules block it separately.

### 12.3. Selecting Groups in Spring MVC

With a grouped DTO:

~~~java
@PostMapping("/grouped")
public ResponseEntity<?> createGrouped(
    @Validated({
        Default.class,
        ProductGroups.OnCreate.class
    })
    @RequestBody GroupedProductInput input
) {
    // ...
}
~~~

and:

~~~java
@PutMapping("/grouped/{id}")
public ResponseEntity<?> replaceGrouped(
    @PathVariable long id,
    @Validated({
        Default.class,
        ProductGroups.OnUpdate.class
    })
    @RequestBody GroupedProductInput input
) {
    // ...
}
~~~

These are **snippets** outside the runnable controller in section 9 and require the corresponding Spring/Jakarta imports. Do not add routes like these to the main project unless you want a group-based API.

Why specify **`Default.class` explicitly**?

Constraints without a `groups` attribute belong to `Default`. When you write:

~~~java
@Validated(ProductGroups.OnCreate.class)
~~~

and `OnCreate` does not extend `Default`, constraints belonging only to `Default` such as `name`/`price` **will not execute automatically**. To avoid missing them, this example requests both groups:

~~~java
@Validated({Default.class, ProductGroups.OnCreate.class})
~~~

Another option is declaring `interface OnCreate extends Default` to apply inheritance explicitly, though this requires codebase-wide conventions and tests. Never assume Spring automatically adds `Default` whenever you pick a custom group.

### 12.4. Testing Groups Directly with Jakarta Validator

`src/test/java/com/example/productvalidation/GroupedProductValidationTest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class GroupedProductValidationTest {

    @Autowired
    private Validator validator;

    private static GroupedProductInput badAll() {
        return new GroupedProductInput(
            "",
            new BigDecimal("-1.00"),
            "",
            "reason-exceeds-ten-characters");
    }

    private Set<String> fields(Class<?>... groups) {
        Set<ConstraintViolation<GroupedProductInput>> results =
            validator.validate(badAll(), groups);

        return results.stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());
    }

    @Test
    void createRunsDefaultPlusCreateRules() {
        Set<String> errors = fields(
            Default.class, ProductGroups.OnCreate.class);

        assertEquals(3, errors.size());
        assertTrue(errors.contains("name"));
        assertTrue(errors.contains("price"));
        assertTrue(errors.contains("sku"));
        assertFalse(errors.contains("updateReason"));
    }

    @Test
    void updateRunsDefaultPlusUpdateRules() {
        Set<String> errors = fields(
            Default.class, ProductGroups.OnUpdate.class);

        assertEquals(3, errors.size());
        assertTrue(errors.contains("name"));
        assertTrue(errors.contains("price"));
        assertTrue(errors.contains("updateReason"));
        assertFalse(errors.contains("sku"));
    }

    @Test
    void updateGroupAloneDoesNotImplicitlyRunDefault() {
        Set<String> errors = fields(
            ProductGroups.OnUpdate.class);

        assertEquals(Set.of("updateReason"), errors);
    }
}
~~~

**Three tests** prove:

- Create runs `Default + OnCreate`, producing errors on `name`, `price`, `sku`.
- Update runs `Default + OnUpdate`, producing errors on `name`, `price`, `updateReason`.
- Selecting only `OnUpdate` **skips `Default`** in this example, the most common regression when using groups.

**In total, the project has 15 `@Test` methods**: 10 MockMvc + 2 service + 3 grouped-provider tests. Both separate DTOs and groups have dedicated examples and tests, while the main product routes use separate DTOs.

## 13. Validation Groups Are Not Field Permissions

This is a critical security trap:

~~~java
public record SharedAccount(
    @NotBlank(groups = Create.class)
    String email,

    String role
) {
}
~~~

Even when Update does not run `NotBlank` on email, the `role` field can still deserialize. If the service blind-copies:

~~~java
entity.setRole(input.role());
~~~

then validation groups fail to protect role modification permissions. That is **mass assignment**.

**Solution:** per-action DTOs, allowlists, explicit mapping, and service authorization. Never use Jakarta constraint selection to decide which fields a client is permitted to modify.

### Validation Groups Also Do Not Control JSON Schema

Jackson still deserializes properties according to JSON mapping rules. Bean Validation groups do not automatically hide fields in OpenAPI, reject unknown properties, or select which setters may run.

If a field is only valid in POST and completely forbidden in PUT, **do not merely “omit the constraint from the Update group”**. Remove the field from the Replace DTO or use explicit input mapping/validation mechanisms.

## 14. Group Inheritance, Sequences, and Group Conversion

### Group Inheritance

Jakarta Validation allows groups to extend each other:

~~~java
public interface BaseChecks {
}

public interface CreateChecks extends BaseChecks {
}
~~~

Validating `CreateChecks` also evaluates constraints belonging to `BaseChecks` via inheritance. To include the `Default` group when selecting Create, you can declare `CreateChecks extends Default`; however, group constraints need clear conventions rather than mixing styles inconsistently.

### `@GroupSequence`

Normally, constraints across multiple groups have **no guaranteed execution order**. When you want cheap/simple constraints to run before more expensive groups, you can use:

~~~java
@GroupSequence({
    Default.class,
    ProductGroups.OnCreate.class
})
public interface OrderedCreateChecks {
}
~~~

This is a snippet requiring the `OrderedCreateChecks` interface and imports. When an earlier group in the sequence produces violations, subsequent groups **are not executed** in that sequence.

Do not use `@GroupSequence` as a field-permission API. It solves **validation ordering**, and you must check the rules when redefining `Default` via a class-level group sequence (which differs from a sequence interface).

### `@ConvertGroup` When Cascading Nested Objects

If root and nested DTOs use different group names, you can convert groups as `@Valid` cascades:

~~~java
public record OrderInput(
    @Valid
    @ConvertGroup(
        from = ProductGroups.OnCreate.class,
        to = AddressChecks.class
    )
    AddressInput address
) {
}
~~~

This snippet requires defining `AddressInput`/`AddressChecks` and importing `jakarta.validation.groups.ConvertGroup`. `@ConvertGroup` **must accompany `@Valid`** and applies only at the cascade boundary. It does not change the root object's group, is not a JSON field conversion, and does not apply recursively through an arbitrary chain of mapped groups.

If rules in `AddressInput` still belong to `Default` while you select `OnCreate` at the root, nested validation may not evaluate `Default` as expected. Design group inheritance/conversion clearly and test `ConstraintViolation.getPropertyPath()` for nested paths.

## 15. PATCH Design Pattern That Validates the Post-Merge Result

For applications needing PATCH, do not simply mark every field nullable and apply `@Valid`. Example of controlled manual handling with Jackson `JsonNode`:

~~~java
// Snippet inside service/controller, not a standalone file.
// current: Product with name(), price(), description().
// patch: already-parsed ObjectNode/JsonNode.
// validator: jakarta.validation.Validator.

if (!patch.isObject()) {
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST, "Patch must be an object");
}

Set<String> allowed =
    Set.of("name", "price", "description");

Iterator<String> keys = patch.fieldNames();
while (keys.hasNext()) {
    if (!allowed.contains(keys.next())) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Unknown patch field");
    }
}

String name = current.name();
BigDecimal price = current.price();
String description = current.description();

if (patch.has("name")) {
    JsonNode value = patch.get("name");
    if (!value.isTextual()) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid name type");
    }
    name = value.asText();
}

if (patch.has("price")) {
    JsonNode value = patch.get("price");
    if (!value.isNumber()) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid price type");
    }
    price = value.decimalValue();
}

if (patch.has("description")) {
    JsonNode value = patch.get("description");
    if (value.isNull()) {
        description = null;
    }
    else if (value.isTextual()) {
        description = value.asText();
    }
    else {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid description type");
    }
}

ReplaceProductRequest candidate =
    new ReplaceProductRequest(name, price, description);

Set<ConstraintViolation<ReplaceProductRequest>> errors =
    validator.validate(candidate);

if (!errors.isEmpty()) {
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST, "Invalid patch result");
}

// After authorization + concurrency check:
// service.applyValidatedCandidate(id, candidate);
~~~

Required imports include `java.util.Set`, `java.util.Iterator`, `java.math.BigDecimal`, `com.fasterxml.jackson.databind.JsonNode`, `org.springframework.http.HttpStatus`, `org.springframework.web.server.ResponseStatusException`, and `jakarta.validation.ConstraintViolation`. The snippet intentionally stays outside the runnable project because it focuses on **merge + validate**, rather than pretending to be a full PATCH endpoint handling transactions, ETags, RFC-compliant JSON Merge Patch, or authorization.

An important point: in this snippet, **`price:null` is rejected because `!value.isNumber()`**; `name:null` is rejected; `description:null` is allowed to clear the field. Absent keys retain their old values.

**Do not call this a full RFC 7396 implementation:** it handles only three top-level fields with chosen semantics. RFC 7396 also specifies recursive object rules; if advertising `application/merge-patch+json`, implement the RFC faithfully and test thoroughly.

### Read–Merge–Write Race Condition

Suppose two PATCH requests read the same resource version:

~~~text
T1 reads {name=A, price=10}
T2 reads {name=A, price=10}
T1 changes name -> B, writes {name=B, price=10}
T2 changes price -> 20, writes {name=A, price=20}
~~~

Without versioning/locking, T2 can overwrite T1's name change. With a real DB, use optimistic locking (`@Version`), ETag/If-Match, row versioning, or appropriate transaction isolation.

**Bean Validation does not solve concurrency.** A valid candidate can still be stale; the service must re-check inside a transaction.

## 16. Cross-Field Constraints: Validate Final State

Suppose a product has `discountPrice` requiring `discountPrice <= price`. If PATCH lowers `price` below the stored `discountPrice`, validating the incoming `price` field in isolation is insufficient.

Proper approach:

1. Load the current resource by ID and check authorization.
2. Merge allowed fields from PATCH into a copy.
3. Validate the merged candidate using `jakarta.validation.Validator` or domain rules.
4. Persist changes only when valid.

A class-level constraint:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PriceRangeValidator.class)
public @interface ValidPriceRange {
    String message() default "Invalid price range";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This snippet requires `java.lang.annotation.*`, `jakarta.validation.*`, and a `PriceRangeValidator` implementation. Do not attach it to an unmerged PATCH fragment object, because cross-field constraints need to see the entire state.

### Controller Validation Does Not Replace Domain Invariants

Even when the controller applies `@Valid`, a service can be invoked by a scheduled job, message listener, CLI, another test, or another service. Core invariants (immutable SKU, modification permissions, valid prices, order state, uniqueness) must still be enforced in the domain/service layer.

A DTO passing Bean Validation yet violating business state must still be rejected. Define domain exceptions to map to HTTP 409/422 where appropriate per contract rather than cramming everything into `@NotNull`.

## 17. Service Method Validation: Is `@Validated` Needed on Services?

To validate method parameters **when a service is called outside MVC**, you can use:

~~~java
@Service
@Validated
public class ProductCommandService {

    public void create(
            @Valid CreateProductRequest request) {
        // ...
    }
}
~~~

This is an illustrative snippet: a `@Validated` service class invoked through a Spring-managed proxy can trigger method-validation AOP. However:

- Simply placing `@Valid` on a parameter and calling `new ProductCommandService()` will not run checks.
- Self-invocation within the same bean typically bypasses the AOP proxy.
- Using service AOP validation is an **extra layer**, not a replacement for domain checks.
- It can throw `ConstraintViolationException` or an adapted method-validation exception depending on configuration, rather than MVC's `MethodArgumentNotValidException`.

Do not add class-level `@Validated` to controllers just to “enable validation”; Spring MVC 6.1+ has built-in method validation and the documentation recommends omitting class-level `@Validated` on controllers when using that mechanism.

## 18. Error Handling by Operation

| Input | POST | PUT | PATCH |
|---|---|---|---|
| Missing `sku` | 400: SKU required | Not present in DTO | Not allowed to modify |
| Blank name | 400 | 400 | 400 if name is present and blank |
| Missing name | 400 | 400 | Valid: keep existing name |
| Negative price | 400 | 400 | 400 if price is present and negative |
| Missing price | 400 | 400 | Valid: keep existing |
| Null price | 400 | 400 | 400 (required field of candidate) |
| Null description | Valid | Valid: clear | Valid: clear |
| Unknown field `role` | 400 if strict JSON | 400 if strict JSON | Reject per allowlist |
| Non-existent ID | Not applicable | 404 | 404 |
| Stale version | Not applicable | 409/412 per contract | 409/412 per contract |
| Unauthorized | 401/403 | 401/403 | 401/403 |

**This is the sample API's policy**, not an automatic error code table applied to every Spring application. Error statuses and `ProblemDetail` schemas should be defined consistently in `@RestControllerAdvice` or `ResponseEntityExceptionHandler`.

### Distinguishing Parse, Binding, and Validation Errors

- Malformed JSON or unknown property under strict Jackson → typically `HttpMessageNotReadableException`.
- DTO violating `@NotBlank`/`@DecimalMin` → typically `MethodArgumentNotValidException` when MVC argument validation runs.
- Direct method constraints → potentially `HandlerMethodValidationException`.
- Domain/business conflict → exception chosen by the service.
- Missing resource → `ResponseStatusException(HttpStatus.NOT_FOUND)` or a domain exception mapped to 404.

Do not use status 400 alone to “prove Bean Validation ran”. Tests should assert the expected exception/field path in relevant cases.

## 19. Error Message Quality and i18n

A `MethodArgumentNotValidException` holds a `BindingResult`, letting you read:

~~~java
List<FieldError> fields =
    ex.getBindingResult().getFieldErrors();
~~~

This is a snippet inside an exception handler. For public APIs, map errors into a stable error DTO such as:

~~~json
{
  "code": "INVALID_INPUT",
  "issues": [
    {
      "field": "price",
      "code": "PRICE_BELOW_ZERO"
    }
  ]
}
~~~

Never return the raw `BindingResult` or `getRejectedValue()` in responses, as it can leak secrets, private data, or internal object graphs.

`MessageSource` resolves Spring/Bean Validation message codes by locale, without deciding which constraints fire. To localize messages differently for create vs update, define clear keys and test locales. Never tie frontend branching logic directly to human-readable text messages; rely on stable machine-readable codes.

### Global Errors and Nested Paths

With class-level constraints, `BindingResult.getGlobalErrors()` can contain errors not tied to a single field. With nested DTOs, paths like `shippingAddress.postalCode` may appear; tests should not look only at `getFieldError("postalCode")`.

If an API needs an error spanning multiple fields, it can return `path="$object"` per its own schema, documented clearly rather than pretending to be a real property.

## 20. Essential Create/Update Test Matrix

| Scenario | Key assertion |
|---|---|
| Valid full POST | 201, Location, `service.create` invoked |
| POST missing SKU | 400, field `sku`, service not called |
| POST bad SKU format | 400, field `sku` |
| POST blank name | 400, field `name` |
| POST negative price | 400, field `price` |
| POST null/missing price | 400, field `price` |
| Valid PUT name+price | 200, `service.replace` invoked |
| PUT missing name | 400, field `name` |
| PUT missing price | 400, field `price` |
| PUT with out-of-DTO sku | 400 if strict, or ignored per policy |
| PUT non-existent ID | 404 |
| PUT updates name/price | Entity's SKU remains unchanged |
| Create group | Both Default + OnCreate constraints run |
| Update group | Both Default + OnUpdate constraints run |
| Custom group only | Default does not run automatically unless inherited/selected |
| PATCH name only | Existing price/description preserved |
| PATCH null description | Description cleared |
| PATCH null price | 400 |
| PATCH sku | 400/403 depending on API policy |
| PATCH stale version | 409/412 per ETag/locking policy |

The tests in sections 10–12 implement the core POST/PUT/groups cases. The PATCH matrix is a **test plan for future PATCH implementation**, not tests already present in this project.

### Do Not Claim “Tests PASS” Without Running Them

The examples follow Spring Boot 3.5/Spring Framework 6.2/Java 17 APIs and have been checked statically for file/import consistency; however, **no actual Gradle build was executed in this article**. When applying to a real repository, run `./gradlew test` with your project's versions and adjust per compiler/test runner output.

## 21. Common Pitfalls When Organizing Validation by Operation

| Symptom | Cause | Fix |
|---|---|---|
| Single-field PATCH rejected because other fields are null | Reused POST/PUT DTO with required constraints | Patch DTO with presence or merge before validating |
| POST allows missing name after fixing PATCH | Removed `@NotBlank` from shared DTO | Split DTOs or select groups properly |
| PUT missing price still accepted | Update group lacked Default/required rules | Run Default + Update or separate DTO |
| Update modifies SKU despite no Update constraint | Groups do not block mapping | Remove SKU from update DTO/service mapper |
| `@Validated(OnCreate.class)` skips Default `@NotBlank` | Custom group does not run Default automatically | Include `Default.class` or group inheritance |
| Nested child constraints do not run | Missing `@Valid` on association | Add cascade, test nested field path |
| Wrong child group | Pass-through groups mismatched with child | Use `@ConvertGroup` with tests |
| `@GroupSequence` misused and later group skipped | Violation in earlier group stops sequence | Design and test ordering explicitly |
| Annotations present but provider missing | Only `jakarta.validation-api` on classpath | Add starter-validation/provider |
| Boot 3 code imports `javax.validation.*` | Wrong namespace | Migrate to Jakarta |
| PUT sending unknown JSON field still returns 200 | Jackson ignores unknowns by default/config | Enable strict mapping if contract requires |
| PUT 404 turns into 500 | Missing resource not mapped | `ResponseStatusException`/domain handler |
| Duplicate constraints across separate DTOs | Haven't extracted reusable custom constraint | Create composed constraint/value object when helpful |
| Grouped DTO becomes hard to follow | Too many action-specific groups | Split clear command DTOs per use case |
| PATCH null does not clear description | Code uses `if(value!=null)` | Distinguish absent/present/null |
| PATCH overwrites another request's edit | Read-modify-write without version | Optimistic locking/ETag |
| Controller validation works, job-triggered service skips it | Trusted only web boundary | Domain/service invariants or method validation |
| Client modifies ownerId/status via DTO | Mass assignment | Dedicated DTO, allowlist, authorization |
| Test asserts 400, yet service was invoked | Checked errors after service call | Early validation gate + `verifyNoInteractions` |
| Numeric price becomes double | Floating-point representation | Use `BigDecimal` + scale/domain rules |
| Validation group used to hide fields from JSON | Conflating validation with serialization | Separate DTO mapping/authorization |
| PUT sends one field and app wipes others | Client using PUT like PATCH | Define contract/method clearly, test |
| API docs mark every field optional | Shared DTO/group misunderstood by schema generator | Separate DTOs or OpenAPI customization |
| Constraints do not run when service created via `new` | Bypassed AOP | Use Spring-managed bean or explicit validation |

## 22. Design Checklist for Real Projects

- [ ] Clearly distinguish POST, PUT, and PATCH in the API contract.
- [ ] Document each field: required, mutable, nullable, immutable.
- [ ] Use separate DTOs when create and update differ significantly.
- [ ] Never bind requests directly onto JPA entities.
- [ ] Ensure immutable id/ownerId/SKU have no writable path from client updates.
- [ ] Pair `@NotNull` with constraints on required fields.
- [ ] For `BigDecimal` prices, check non-negativity and domain bounds.
- [ ] Ensure a Jakarta provider is on the runtime classpath.
- [ ] Place `@Valid`/`@Validated` at the proper handler position.
- [ ] When using groups, explicitly define `Default` and group inheritance.
- [ ] Never treat `@Validated(OnUpdate)` as a way to forbid modifying a property.
- [ ] Use cascaded `@Valid` for nested objects and `@ConvertGroup` when genuinely needed.
- [ ] Distinguish missing/null/value in PATCH.
- [ ] Validate the **merged candidate** before persisting.
- [ ] Use optimistic locking/ETag when concurrent updates are a risk.
- [ ] Verify resource/field modification permissions in the service.
- [ ] Choose an explicit JSON unknown-properties policy.
- [ ] Never invoke the service when request input is invalid.
- [ ] On domain conflicts, map errors to proper statuses instead of hiding them.
- [ ] Never serialize rejected values or internal object graphs.
- [ ] Test both positive and negative paths for POST/PUT.
- [ ] Test group-specific rules independently and verify `Default` fallback.
- [ ] Test that SKU/ID remain immutable after update.
- [ ] If supporting PATCH, test absent/null/value/unknown fields/concurrency.
- [ ] Verify OpenAPI schemas reflect each operation's contract.
- [ ] Run real compilation and tests on the repository before deploying.

**Conclusion:** Bean Validation for create and update should start from **each operation's contract**. **Separating the Create DTO and Replace DTO** is the clearest and easiest-to-protect approach for most APIs. **Validation groups** help when many constraints are genuinely shared, provided you account for `Default`, group selection, and cascading; they never replace field authorization. For **PATCH**, you must distinguish **absent / explicit null / value**, merge into a candidate, and validate the final state before saving. Even when the controller validates input, critical invariants must still be enforced in the service/domain layer.

## Official References

- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — MVC Validator Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Hibernate Validator Reference Guide — Grouping Constraints](https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#chapter-groups)
- [Jackson Databind — DeserializationFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902)
