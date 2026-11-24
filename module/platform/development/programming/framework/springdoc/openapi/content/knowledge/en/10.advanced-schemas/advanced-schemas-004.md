# Records, Immutable Classes, and Data Derived from Accessors

In modern Java, DTOs used for APIs can be represented as records or immutable classes with `final` fields. These data types restrict state mutation after initialization, clarify input and output data, and reduce getter/setter boilerplate. However, when springdoc-openapi generates schemas, the result also depends on how Jackson recognizes properties from record components, constructors, getters, and additional accessors.

A class can hold stored data alongside values computed from that data. For example, `ProductView` has `name` and `price`, while also exposing `displayName` or `formattedPrice` via getters. If Jackson treats such a getter as a serialized property, springdoc can include the corresponding property in the OpenAPI schema. When documentation and actual JSON diverge, clients may misunderstand responses or mistakenly send server-only fields.

This lesson explains how records and immutable classes are recognized, how to name and control properties with Jackson, how to document derived fields in OpenAPI, and how to verify generated schemas alongside runtime JSON.

## Objectives

After this lesson, you will be able to:

- Understand how Jackson and springdoc-openapi recognize properties from record components, fields, constructors, and accessors.
- Use records for request/response DTOs and immutable classes when explicit constructors are needed.
- Distinguish record accessors, JavaBean getters, and ordinary utility methods.
- Control property names, read/write direction, and exclusion using Jackson annotations.
- Document server-computed fields using `@Schema`, `readOnly`, or `writeOnly`.
- Prevent unintended accessors from leaking data or skewing schemas.
- Verify OpenAPI schemas and serialized/deserialized JSON payloads in Spring Boot.

## 1. From Java Types to OpenAPI Schemas

springdoc-openapi analyzes controllers, parameter types, return types, and metadata from related libraries to build the OpenAPI specification. For DTOs, results are typically influenced by two layers:

1. **Jackson** decides which attributes count as properties when reading or writing JSON, what the JSON names are, and in which direction properties can be read or written.
2. **Swagger Core and springdoc-openapi** construct OpenAPI schemas from Java types and annotation metadata, including Swagger/OpenAPI annotations and the Jackson information supported by the analyzer.

Consequently, a schema is not simply the list of fields declared in a class. A public getter can become a JSON property even if the class has no backing field. Conversely, an internal field may be omitted if Jackson ignores it. Annotations can rename, hide, or mark properties as read-only or write-only.

For example, a response can have the following properties:

| Source in Java | JSON name that may appear | Meaning |
|---|---|---|
| Record component `name` | `name` | Component data of the record |
| Getter `getDisplayName()` | `displayName` | Property per JavaBean convention |
| Boolean getter `isAvailable()` | `available` | Boolean property per JavaBean convention |
| Method `normalizedName()` | Usually does not appear automatically | Utility method, not a JavaBean getter |
| Method with `@JsonProperty("label")` | `label` | Property explicitly exposed by Jackson |

These are common recognition rules; `ObjectMapper` configuration, visibility settings, mix-ins, and custom annotations can change the result. Treat serialized JSON and the actual OpenAPI JSON as the final source of truth for your project.

## 2. Records and Record Components

A record is a data type designed to hold a fixed set of values. Components declared in the record header generate:

- Data components with clear names and types.
- Corresponding backing fields, typically `private final`.
- Accessors sharing the component name, such as `name()` instead of `getName()`.
- A canonical constructor accepting the components in declaration order.
- Automatically generated `equals`, `hashCode`, and `toString` methods.

Example:

~~~java
public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

An instance is created once with the given values:

~~~java
ProductResponse product =
    new ProductResponse(42L, "Mechanical keyboard", new BigDecimal("1250000"));

Long id = product.id();
String name = product.name();
~~~

Records do not generate setters for components. This suits response DTOs because data is typically constructed in the service and serialized back to clients. Records can also serve as request DTOs when the framework and Jackson version support constructor binding for records.

Records provide shallow immutability. Components cannot be reassigned after initialization, though objects referenced by components may still be mutable. For instance, a record containing a `List` can still be modified if an external mutable list reference is retained. You can perform defensive copying in a compact constructor:

~~~java
public record TeamView(List<String> members) {
    public TeamView {
        members = List.copyOf(members);
    }
}
~~~

The OpenAPI schema still describes `members` as an array; defensive copying ensures internal record values cannot be altered through external collection references.

### How Does Jackson Recognize Records?

Records are a Java feature finalized in Java 16. Jackson supports records starting from the 2.12 line. With a compatible version, record components are recognized as JSON properties even though accessors look like `name()` rather than `getName()`. When Spring MVC binds JSON into a record, Jackson can invoke the canonical constructor to create an instance.

Spring Boot releases manage Jackson versions through dependency management. Before using records in APIs, verify the Java, Spring Boot, and Jackson versions your project actually runs. Do not upgrade Jackson independently without care when Spring Boot manages a compatible version set.

In responses, springdoc typically generates schemas based on the components:

~~~yaml
ProductResponse:
  type: object
  properties:
    id:
      type: integer
      format: int64
    name:
      type: string
    price:
      type: number
    # Other properties depending on annotations and configuration.
~~~

The illustrative schema is abbreviated. To know the actual `required` list, formats, nullability, and examples, inspect the `/v3/api-docs` document produced by the application.

## 3. Using Separate Records for Requests and Responses

Separating request DTOs and response DTOs helps control which fields clients can send and which fields the server generates:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Schema(name = "CreateProductRequest")
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Product name", example = "Mechanical keyboard")
    String name,

    @Positive
    @Schema(description = "Selling price", example = "1250000")
    BigDecimal price
) {}

@Schema(name = "ProductResponse")
public record ProductResponse(
    @Schema(description = "Server-assigned product ID", example = "42")
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {

        ProductResponse created = productService.create(request);
        URI location = URI.create("/api/products/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}
~~~

In the example, clients only send `name` and `price`. The server assigns `id` and returns `ProductResponse`. Using two separate records makes the contract explicit without relying on hiding a field on a shared DTO to reuse it in both directions.

Bean Validation annotations on record components are supported by modern frameworks through annotation propagation and validation mechanisms. For validation to run in controllers, `@Valid` and the corresponding Bean Validation dependency are still required. springdoc can use constraint metadata to describe `required`, bounds, or formats, yet inspect the generated schema instead of assuming all business rules appear automatically.

## 4. Record Accessors Differ from JavaBean Getters

Records generate accessors matching the exact component names:

~~~java
public record CustomerView(String fullName, boolean active) {
    // Generated accessors: fullName() and active()
}
~~~

These are not JavaBean getters `getFullName()` or `isActive()`. Jackson recognizes record components through record support, so the `fullName` and `active` properties can still be serialized.

For regular Java classes, the JavaBean convention typically uses:

~~~java
public final class CustomerView {
    private final String fullName;
    private final boolean active;

    public CustomerView(String fullName, boolean active) {
        this.fullName = fullName;
        this.active = active;
    }

    public String getFullName() {
        return fullName;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Jackson normally maps `getFullName()` to property `fullName` and `isActive()` to property `active`, depending on visibility configuration and naming rules. When migrating from a getter/setter class to a record, Java accessor names change while JSON property names can remain identical.

### Utility Methods Do Not Automatically Become Properties

In a record:

~~~java
public record CustomerView(String fullName) {

    public String normalizedName() {
        return fullName.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

`normalizedName()` is a utility method, not a JavaBean getter. Normally, Jackson does not automatically treat it as a JSON property. If you want to expose this value in responses, annotate it explicitly with `@JsonProperty` or define a conventional getter:

~~~java
public record CustomerView(String fullName) {

    @JsonProperty("normalizedName")
    public String normalizedName() {
        return fullName.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

When using `@JsonProperty`, the method becomes a property Jackson considers for JSON. Check both the OpenAPI schema and JSON responses to confirm the property appears with the expected name.

## 5. Immutable Classes with Explicit Constructors

Not every DTO needs to be a record. An immutable class fits when you need compatibility with existing class hierarchies, have complex initialization logic, or need constructor control:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "Money")
public final class Money {

    private final String currency;
    private final BigDecimal amount;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Money(
            @JsonProperty("currency") String currency,
            @JsonProperty("amount") BigDecimal amount) {
        this.currency = Objects.requireNonNull(currency);
        this.amount = Objects.requireNonNull(amount);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
    }

    @JsonProperty("currency")
    public String getCurrency() {
        return currency;
    }

    @JsonProperty("amount")
    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

`@JsonCreator` indicates which constructor Jackson uses to instantiate the object when reading JSON. `@JsonProperty` on parameters binds JSON names to constructor arguments; on getters, the annotation determines property names during serialization. Because fields are `final` with no setters, they cannot be mutated via setters after the object is constructed.

With immutable classes, ensure that:

- Jackson knows which constructor or factory method to use for deserialization.
- Every constructor parameter is mapped to the right JSON property name.
- Getters or annotations specify the properties to serialize.
- Validation rules in the constructor do not create unexpected discrepancies with request DTO validation.

Constructor parameter names can be inferred in some setups if bytecode includes suitable metadata, yet explicit `@JsonProperty` declarations generally keep the contract more stable. For records supported by Jackson, the canonical constructor is usually recognized automatically, avoiding the need to repeat this constructor pattern.

### When to Choose a Record vs. an Immutable Class?

| Criterion | Record | Immutable class |
|---|---|---|
| Purpose | Concise DTO/value carrier with fixed data | Model requiring initialization control or complex structure |
| Accessors | Component names like `amount()` | Typically JavaBean getters like `getAmount()` |
| Constructor | Canonical constructor generated | Custom constructor/factory declared explicitly |
| Jackson | Record support in compatible versions | Usually requires clear getters and creator/constructor |
| Inheritance | Records are final; cannot extend other classes | Can organize inheritance if design permits |
| Additional logic | Can add methods and secondary constructors | Can add methods, factories, and multiple constructors |

For simple request/response DTOs, records typically make schemas and data easier to read. For models requiring backward compatibility or custom initialization rules, immutable classes may be more suitable.

## 6. Properties Computed from Accessors

A response can hold base data along with derived values. For example:

~~~java
public final class ProductView {
    private final Long id;
    private final String name;
    private final BigDecimal price;

    public ProductView(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public String getDisplayName() {
        return name + " (#" + id + ")";
    }

    public boolean isPremium() {
        return price.compareTo(new BigDecimal("1000000")) >= 0;
    }
}
~~~

Under typical Jackson configuration, JavaBean getters such as `getDisplayName()` and `isPremium()` can become JSON properties. The JSON can contain both the three stored fields and the two computed fields:

~~~json
{
  "id": 42,
  "name": "Mechanical keyboard",
  "price": 1250000,
  "displayName": "Mechanical keyboard (#42)",
  "premium": true
}
~~~

Derived values have no dedicated backing fields yet remain part of the JSON representation if Jackson serializes the corresponding getters. springdoc can include them in the response schema when the analyzer identifies them as properties.

### Why Can Accessors Change the Schema?

Suppose previously a response only had `id`, `name`, and `price`. Adding a public getter `getDisplayName()` can cause Jackson to add a `displayName` property to the JSON. The generated OpenAPI specification can also change, even though you did not add a new field to the class.

This is often useful when a derived value is part of the contract, such as:

- `totalAmount` computed from unit price and quantity.
- `displayName` combining resource name and ID.
- `available` reflecting orderability.
- `canEdit` representing the current user's action permissions.

However, a utility getter can accidentally become a public property. Before adding a method starting with `get` or `is` to a DTO, decide whether it should appear in JSON and OpenAPI.

### Non-JavaBean Getter Methods

Methods like `calculateTotal()` or `normalizedName()` are usually not automatically recognized by Jackson as properties merely for being public. If you want to include the result in JSON, annotate it with `@JsonProperty`:

~~~java
@JsonProperty("normalizedName")
public String normalizedName() {
    return name.trim().toLowerCase(Locale.ROOT);
}
~~~

If you do not want to expose it, keep the method with an ordinary name and do not mark it as a property. When a project customizes visibility or uses mix-ins, rules may differ, so test with the `ObjectMapper` configured by Spring Boot.

## 7. Naming and Controlling Properties with Jackson

Jackson provides annotations to control which properties appear and what they are named. Common annotations include:

| Annotation | Effect |
|---|---|
| `@JsonProperty("publicName")` | Explicitly sets the JSON property name |
| `@JsonIgnore` | Ignores the property during serialization/deserialization per Jackson settings |
| `@JsonProperty(access = READ_ONLY)` | Property is output but does not accept values from input JSON |
| `@JsonProperty(access = WRITE_ONLY)` | Property is accepted from input JSON but omitted from responses |
| `@JsonGetter("name")` | Specifies the method used to serialize a property under a specific name |
| `@JsonInclude` | Controls when a property is included in output, e.g., omitting nulls |
| `@JsonAlias` | Allows additional alternative names during deserialization |

Example renaming properties:

~~~java
public record AccountView(
    @JsonProperty("account_id")
    Long id,
    @JsonProperty("display_name")
    String displayName
) {}
~~~

JSON uses `account_id` and `display_name`. springdoc typically reflects property names after Jackson processing, yet verify in `/v3/api-docs` since naming strategies or library versions can affect results.

### Hiding Internal Properties

~~~java
public final class AccountView {
    private final String username;
    private final String internalRiskScore;

    public AccountView(String username, String internalRiskScore) {
        this.username = username;
        this.internalRiskScore = internalRiskScore;
    }

    public String getUsername() {
        return username;
    }

    @JsonIgnore
    public String getInternalRiskScore() {
        return internalRiskScore;
    }
}
~~~

`@JsonIgnore` instructs Jackson to skip the property. springdoc generally respects Jackson metadata and excludes ignored properties from schemas. Even so, if mix-ins, custom serializers, or separate documentation settings exist, verify both outputs.

Do not use `@Schema(hidden = true)` as the sole mechanism to hide sensitive data. That annotation controls OpenAPI documentation; it does not guarantee Jackson stops serializing the property.

## 8. Describing Read and Write Direction with readOnly and writeOnly

A property may only be returned by the server or only sent by clients. OpenAPI expresses these two cases with:

- `readOnly: true`: property belongs to responses; clients should not send it in requests.
- `writeOnly: true`: property belongs to requests; the server does not return it in responses.

With springdoc, you can use `@Schema(accessMode = Schema.AccessMode.READ_ONLY)` or `WRITE_ONLY`:

~~~java
public record ProductView(
    @Schema(accessMode = Schema.AccessMode.READ_ONLY,
            description = "Server-assigned ID")
    Long id,
    String name,
    BigDecimal price
) {}
~~~

This is documentation metadata. If you need Jackson to enforce the same read/write direction in JSON, also add `@JsonProperty(access = JsonProperty.Access.READ_ONLY)`:

~~~java
public record ProductView(
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @Schema(accessMode = Schema.AccessMode.READ_ONLY,
            description = "Server-assigned ID")
    Long id,
    String name,
    BigDecimal price
) {}
~~~

For write-only fields, such as a password during registration:

~~~java
public record RegisterRequest(
    @NotBlank String username,
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY,
            description = "Password used only when creating an account")
    @NotBlank String password
) {}
~~~

`@JsonProperty(access = ...)` controls how Jackson reads/writes the property; `@Schema(accessMode = ...)` documents the direction in OpenAPI. Use both when you want runtime JSON and the contract to enforce the same rule. If you only add `@Schema`, do not assume Jackson stops accepting or returning that property.

### Do Not Replace Request/Response DTOs with accessMode in Every Case

A shared schema with `readOnly`/`writeOnly` can work when both directions are nearly identical. However, if requests and responses differ across many fields, have different validation rules, or evolve independently, split them into separate DTOs. This prevents clients from mistakenly sending server-managed fields and avoids accidentally returning sensitive data.

## 9. Attaching OpenAPI Metadata to Derived Properties

When a derived getter is part of the contract, document its meaning, example, and data direction right on the accessor:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "ProductView", description = "Product information displayed to clients")
public record ProductView(
    Long id,
    String name,
    BigDecimal price
) {

    @JsonProperty(value = "displayName", access = JsonProperty.Access.READ_ONLY)
    @Schema(
        description = "Display name composed from product name and ID",
        example = "Mechanical keyboard (#42)",
        accessMode = Schema.AccessMode.READ_ONLY
    )
    public String getDisplayName() {
        return name + " (#" + id + ")";
    }

    @JsonIgnore
    public String getInternalSearchKey() {
        return name.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

In the example:

- `displayName` is serialized by Jackson and documented as a read-only property.
- `internalSearchKey` is ignored by Jackson and is not public response data.
- The record components remain the core data of `ProductView`.

Derived getters should compute from data already present in the DTO, produce deterministic results, and have low cost. Avoid database queries, network calls, or reading mutable state from getters; serialization may invoke a getter multiple times and make responses slow or inconsistent. If a value depends on the current user or access permissions, compute it in the service and pass it into the response DTO with clearly documented semantics.

The OpenAPI schema is expected to have `displayName` with `readOnly: true` and exclude `internalSearchKey`. Runtime JSON should also include `displayName` without `internalSearchKey`. Verify both because custom Jackson settings can alter default behavior.

### When Should @Schema(hidden = true) Be Used?

`@Schema(hidden = true)` is useful when a property should not appear in documentation for presentation reasons or because a schema serves a specific context. However, it does not replace `@JsonIgnore` if the property must not appear in JSON. Before hiding a property from the contract, consider whether clients need to know the field exists to parse responses or send requests.

## 10. Jackson Annotations That Can Affect Schemas

Several annotations alter JSON in ways that can change OpenAPI schemas:

| Annotation | Effect on JSON | What to check in OpenAPI |
|---|---|---|
| `@JsonProperty` | Renames or exposes property | Property name under `properties` |
| `@JsonIgnore` | Excludes property | Whether the property is omitted from the schema |
| `@JsonProperty(access = READ_ONLY)` | Serialize only | `readOnly: true` |
| `@JsonProperty(access = WRITE_ONLY)` | Deserialize only | `writeOnly: true` |
| `@JsonInclude(NON_NULL)` | Omits null properties from JSON | Whether `required`, nullability, and examples remain accurate |
| `@JsonAlias` | Accepts alternative names when reading JSON | Whether the schema describes the canonical name clients should send |
| `@JsonUnwrapped` | Flattens child object properties into parent object | Whether the schema reflects the flattened structure |
| `@JsonValue` | Serializes object via a single representative value | Whether the schema is scalar instead of an object |

Not every serialization detail is inferred identically across all versions of springdoc/swagger-core. For instance, a custom serializer can turn a class into a JSON string while the schema is still inferred from fields. In such cases, declare the schema explicitly with `@Schema(type = ...)`, `implementation = ...`, or an appropriate customizer and verify the actual output.

### @JsonInclude Does Not Mean a Property Does Not Exist

`@JsonInclude(Include.NON_NULL)` typically omits a property from JSON when its value is null. This does not necessarily mean the property is absent from the schema or can never appear. The schema may still declare the property as non-required; clients must understand the value can be absent.

### @JsonAlias Does Not Change the Canonical Name When Serializing

`@JsonAlias("old_name")` allows Jackson to accept an old name during deserialization. When serializing, the canonical name still follows the configured property name. OpenAPI contracts should guide clients to use the current standard name; aliases primarily support backward compatibility on the server side.

### @JsonUnwrapped and Flattened Structures

If a nested object is annotated with `@JsonUnwrapped`, Jackson can lift child properties into the parent object. Check the schema generated by springdoc because the nested Java structure and actual JSON no longer share the same shape. If the tool does not infer it correctly, declare the corresponding schema or adjust the DTO to make the structure explicit.

## 11. Verifying Runtime JSON with ObjectMapper

Do not look solely at schemas to conclude whether a property appears in responses. Serialize objects using the exact `ObjectMapper` configured by Spring Boot:

~~~java
import java.math.BigDecimal;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest
class ProductViewJsonTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesDerivedPropertyButOmitsInternalProperty() throws Exception {
        ProductView view = new ProductView(
            42L,
            "Mechanical keyboard",
            new BigDecimal("1250000")
        );

        JsonNode json = objectMapper.readTree(
            objectMapper.writeValueAsString(view)
        );

        assertEquals("Mechanical keyboard (#42)", json.path("displayName").asText());
        assertFalse(json.has("internalSearchKey"));
    }

    @Test
    void readOnlyDerivedPropertyIsNotAcceptedFromInput() throws Exception {
        String input = """
            {
              "id": 42,
              "name": "Mechanical keyboard",
              "price": 1250000,
              "displayName": "Fake value sent by client"
            }
            """;

        ProductView view = objectMapper.readValue(input, ProductView.class);

        assertEquals("Mechanical keyboard (#42)", view.getDisplayName());
    }
}
~~~

The example assumes `ProductView` is defined as in the previous section and has a record constructor supported by Jackson. The first check confirms the derived getter is serialized and the internal property does not appear. The second check confirms a client-sent `displayName` value does not override the computed result because the property is marked `READ_ONLY`.

If the project has a dedicated `ObjectMapper`, custom modules, mix-ins, or custom serializers, tests must inject the exact bean used by MVC. Creating a new `ObjectMapper` via the default constructor can produce different results from the application's runtime configuration.

## 12. Verifying Schemas Generated by springdoc

Suppose a controller returns `ProductView`:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductViewController {

    @GetMapping("/{id}/view")
    public ProductView getView(@PathVariable Long id) {
        return productService.getView(id);
    }
}
~~~

In the OpenAPI document, the `ProductView` schema is expected to include the read-only derived property and exclude the internal property:

~~~yaml
components:
  schemas:
    ProductView:
      type: object
      properties:
        id:
          type: integer
          format: int64
        name:
          type: string
        price:
          type: number
        displayName:
          type: string
          description: Display name composed from product name and ID
          readOnly: true
~~~

This is an illustrative structure, not fixed output for all versions. Schema names, numeric types, the `required` list, and nullability handling depend on the DTO, Jackson, and the OpenAPI version generated by the application.

You can verify with `MockMvc`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductOpenApiSchemaTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsDerivedPropertyAsReadOnly() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.components.schemas.ProductView.properties.displayName.readOnly"
            ).value(true))
            .andExpect(jsonPath(
                "$.components.schemas.ProductView.properties.internalSearchKey"
            ).doesNotExist());
    }
}
~~~

If the application splits `GroupedOpenApi`, call the spec endpoint of the group containing `ProductView`. If the schema name was changed via `@Schema(name = ...)`, use that exact name in the JSONPath. Schema tests do not replace JSON response tests; keep both to catch cases where documentation and runtime diverge.

### Comparison Matrix

| Question | Where to check | Expected result in the example |
|---|---|---|
| Are record components serialized? | JSON from `ObjectMapper` | `id`, `name`, `price` appear |
| Is the derived getter serialized? | JSON from `ObjectMapper` | `displayName` appears |
| Is the internal getter excluded? | JSON from `ObjectMapper` | `internalSearchKey` is absent |
| Is the derived property documented? | `/v3/api-docs` | `displayName` is in the schema |
| Does the property have the right direction? | `/v3/api-docs` | `displayName.readOnly` is `true` |
| Does documentation leak internal properties? | `/v3/api-docs` | `internalSearchKey` is absent |
| Can clients override derived properties? | Deserializing JSON | Computed value is still determined by server/DTO |

## 13. Common Pitfalls and How to Handle Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Record fails to deserialize | Jackson too old or incompatible constructor binding | Check Spring Boot-managed Jackson and Java versions |
| Record property missing in JSON | Jackson config or annotations changed visibility | Inspect `ObjectMapper` and annotations on components |
| Adding a getter introduces a new response field | Jackson treats JavaBean getters as properties | Use `@JsonIgnore` if not public; if public, update contract |
| Utility method does not appear | Method is not a getter and lacks `@JsonProperty` | Mark as a property explicitly if it is public data |
| Schema has property but JSON does not | `@Schema` only documents or serializer omits property | Inspect Jackson and synchronize metadata |
| JSON has property but schema misses it | springdoc does not infer custom serializer/accessor | Declare `@Schema` or customizer and re-verify |
| Internal field still returned | Only used `@Schema(hidden = true)` | Control via DTO, `@JsonIgnore`, or serializer |
| Clients can send values into server-managed fields | Only marked `readOnly` in documentation | Use `@JsonProperty(access = READ_ONLY)` or separate DTOs |
| Schema has unexpected property names | Naming strategy or `@JsonProperty` renamed them | Check canonical JSON names and OpenAPI `properties` |
| Null field absent from JSON | `@JsonInclude(NON_NULL)` or serialization config | Document optionality and potential absence accurately |

## 14. Design Principles for Immutable API DTOs

When designing records or immutable classes, apply these principles:

1. Separate request DTOs and response DTOs if the data directions differ in meaning or write permissions.
2. Keep record components aligned with the public data clients need to send or receive.
3. Add derived JavaBean getters only when those values genuinely belong to the API contract.
4. Clearly mark property data directions in both Jackson and OpenAPI when needed.
5. Use `@JsonIgnore` or separate DTOs to prevent internal data from appearing in JSON.
6. Use `@JsonProperty` to stabilize JSON names when refactoring field or accessor names.
7. Do not assume every custom serializer is inferred accurately by springdoc.
8. Inspect both runtime JSON and OpenAPI JSON after changing DTOs or accessors.
9. Evaluate compatibility impact when adding, removing, or renaming response properties.

A new getter can constitute a contract change even without adding a backing field. If a client generator builds models from OpenAPI, a new property can alter client code, snapshots, or data-handling rules. Review schema changes alongside Java changes.

## 15. Hands-on Practice Exercise

Build a product viewing API using immutable DTOs:

1. Create `CreateProductRequest` and `ProductView` as records.
2. Create an immutable `Money` class with a `@JsonCreator` constructor and `@JsonProperty` parameters.
3. Add a derived getter `getDisplayName()` to `ProductView`.
4. Use `@JsonProperty(access = READ_ONLY)` and `@Schema(accessMode = READ_ONLY)` on `displayName`.
5. Add an internal accessor and exclude it from JSON using `@JsonIgnore`.
6. Add a `password` field to a test request DTO and mark it `WRITE_ONLY`.
7. Start the application, view `/v3/api-docs`, and inspect the `ProductView` schema.
8. Use `ObjectMapper` tests to verify which properties are serialized/deserialized.
9. Use `MockMvc` tests to compare JSON responses against the OpenAPI schema.
10. Try adding a new getter and compare the before/after documents to spot contract changes.

### Completion Criteria

- [ ] Record components are recognized accurately in JSON and OpenAPI.
- [ ] Immutable class has clear constructor binding and deserializes successfully.
- [ ] Derived JavaBean accessors appear only when intentionally published.
- [ ] Utility methods are not mistakenly treated as unintended properties.
- [ ] Read-only/write-only properties have matching direction in both Jackson and OpenAPI.
- [ ] Internal data does not appear in response JSON.
- [ ] OpenAPI schema accurately reflects names, types, descriptions, and access modes.
- [ ] Tests verify serialization, deserialization, and generated schemas.

## Continuing Your Learning

After this lesson, combine records and immutable classes with schema composition, polymorphism, custom serializers, and contract versioning. Whenever you change accessors or annotations, review runtime JSON, the OpenAPI schema, and clients generated from the specification. All three artifacts must describe the same data model for an API to remain stable and easy to integrate.

