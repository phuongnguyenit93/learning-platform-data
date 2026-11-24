# Combining Annotations with Jackson Configuration for Subtypes

A request can contain a property that accepts multiple different data types. For example, an order can be paid by card or bank transfer; each method has its own fields while sharing the conceptual `PaymentMethod` type. This is polymorphism. Jackson needs to know how to read JSON into the right subclass, while OpenAPI needs to document all possible types so clients send valid payloads.

In Spring Boot, you can combine Jackson annotations such as `@JsonTypeInfo`, `@JsonSubTypes`, and `@JsonTypeName` with the OpenAPI annotation `@Schema(oneOf = ..., discriminatorProperty = ...)`. When Java classes cannot be modified, Jackson mix-in configuration or subtype registration on `ObjectMapper` can handle JSON processing; the OpenAPI schema still needs to be published clearly and verified independently.

## 1. The Subtype Problem in JSON

Suppose a transaction creation API accepts a `paymentMethod`. There are two payment types:

- `CardPayment`: contains a payment token and the last four digits of the card.
- `BankTransferPayment`: contains a bank code and the recipient account number.

A JSON request can look like:

```json
{
  "paymentMethod": {
    "kind": "card",
    "token": "tok_demo_123",
    "last4": "4242"
  }
}
```

Or:

```json
{
  "paymentMethod": {
    "kind": "bank_transfer",
    "bankCode": "VCB",
    "accountNumber": "0123456789"
  }
}
```

The `kind` property is the discriminator (type-distinguishing field). Jackson reads this value to select the corresponding subclass. In OpenAPI, `oneOf` indicates that the data must match one of the subschemas; `discriminator` identifies which field determines the concrete schema.

If you only declare the property as an interface or abstract class without configuring polymorphism, Jackson does not automatically know which subclass to instantiate when receiving JSON. If you only configure Jackson without documenting `oneOf` in OpenAPI, the documentation may not clearly show the variants clients are permitted to send.

## 2. Declaring Subtypes with Jackson Annotations

Jackson provides a group of annotations to describe relationships between a supertype and its subtypes:

| Annotation | Role |
| --- | --- |
| `@JsonTypeInfo` | Enables type information handling and chooses how the discriminator is placed in JSON |
| `@JsonSubTypes` | Lists permitted subclasses and their identifier names |
| `@JsonTypeName` | Sets the identifier name for a subclass |
| `@JsonTypeInfo.Id.NAME` | Uses logical names like `card`, `bank_transfer` instead of Java class names |
| `@JsonTypeInfo.As.PROPERTY` | Places the discriminator in JSON as a property |

Example of the `PaymentMethod` supertype:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
@Schema(
    name = "PaymentMethod",
    description = "One of the supported payment methods",
    oneOf = {CardPayment.class, BankTransferPayment.class},
    discriminatorProperty = "kind",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "card", schema = CardPayment.class),
        @DiscriminatorMapping(value = "bank_transfer", schema = BankTransferPayment.class)
    }
)
public interface PaymentMethod {}
```

Here there are two groups of annotations with two different roles:

- `@JsonTypeInfo` and `@JsonSubTypes` control how Jackson reads and writes JSON.
- `@Schema` with `oneOf`, `discriminatorProperty`, and `discriminatorMapping` documents the OpenAPI contract.

The names `card` and `bank_transfer` must agree between Jackson configuration and OpenAPI mapping. The fact that Springdoc can infer part of the structure from Jackson does not remove the need to verify the discriminator and mappings in the generated document.

## 3. Defining the Subclasses

Each subclass declares its own properties. You can use records with Java 17:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "CardPayment",
    description = "Tokenized card payment"
)
public record CardPayment(
    @Schema(description = "Token issued by the payment gateway", example = "tok_demo_123")
    String token,

    @Schema(description = "Last four digits of the card", example = "4242")
    String last4
) implements PaymentMethod {}
```

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "BankTransferPayment",
    description = "Bank transfer payment"
)
public record BankTransferPayment(
    @Schema(description = "Bank code", example = "VCB")
    String bankCode,

    @Schema(description = "Recipient account number", example = "0123456789")
    String accountNumber
) implements PaymentMethod {}
```

In the configuration above, Jackson adds the `kind` discriminator to JSON based on the subtype name. You do not need to declare `kind` as a record component if the application only needs Jackson to use it for type selection. If you want the discriminator value also populated into a regular Java property, consider `visible = true` in `@JsonTypeInfo`; in that case, design the field/constructor and test deserialization to avoid setting data twice or with the wrong type.

`@JsonSubTypes.Type(name = ...)` already provides the logical name for each subclass. You can use `@JsonTypeName("card")` on a subclass to declare the name on the class itself, though you should pick one clear convention and avoid conflicting names in two places.

## 4. Putting the Polymorphic Type into a Request DTO

A DTO holding the supertype can use `PaymentMethod` like an ordinary property:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Request to create a payment transaction")
public record CreatePaymentRequest(
    @Schema(description = "Selected payment method")
    PaymentMethod paymentMethod
) {}
```

Controller receiving the request via Spring `@RequestBody`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentController {

    @PostMapping(
        path = "/api/payments",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        summary = "Create a payment",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreatePaymentRequest.class),
                examples = {
                    @ExampleObject(
                        name = "CardPaymentExample",
                        summary = "Card payment",
                        value = "{\"paymentMethod\":{\"kind\":\"card\",\"token\":\"tok_demo_123\",\"last4\":\"4242\"}}"
                    ),
                    @ExampleObject(
                        name = "BankTransferExample",
                        summary = "Bank transfer payment",
                        value = "{\"paymentMethod\":{\"kind\":\"bank_transfer\",\"bankCode\":\"VCB\",\"accountNumber\":\"0123456789\"}}"
                    )
                }
            )
        )
    )
    public ResponseEntity<Void> create(@RequestBody CreatePaymentRequest request) {
        // Handle according to the concrete type of request.paymentMethod().
        return ResponseEntity.accepted().build();
    }
}
```

The example uses `@ExampleObject` to present two valid payloads. The token and account values are dummy data. Never include real payment tokens, real account numbers, or sensitive data in public documentation.

## 5. Describing `oneOf` and Discriminator in OpenAPI

`oneOf` expresses that a value must match exactly one of the listed schemas. `discriminator` provides the rule mapping a property value to the corresponding schema.

The abbreviated OpenAPI output might resemble:

```yaml
components:
  schemas:
    PaymentMethod:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransferPayment'
      discriminator:
        propertyName: kind
        mapping:
          card: '#/components/schemas/CardPayment'
          bank_transfer: '#/components/schemas/BankTransferPayment'
    CardPayment:
      type: object
      properties:
        token:
          type: string
        last4:
          type: string
    BankTransferPayment:
      type: object
      properties:
        bankCode:
          type: string
        accountNumber:
          type: string
```

This is a structural illustration. Actual schemas may include `required`, descriptions, examples, constraints, and reference names generated by Springdoc. Inspect `components.schemas.PaymentMethod` to confirm that `oneOf`, `discriminator.propertyName`, and each mapping appear.

### Distinguishing `oneOf`, `anyOf`, and `allOf`

| Keyword | Meaning | Common use case |
| --- | --- | --- |
| `oneOf` | Data matches exactly one schema in the list | Mutually exclusive variants such as card or bank transfer payment |
| `anyOf` | Data matches at least one schema in the list | Structures that can overlap or combine |
| `allOf` | Data must satisfy all combined schemas | Reusing or extending schema structures |

With a discriminator selecting one concrete subtype, `oneOf` is usually more appropriate. Use `allOf` only when the schema model genuinely needs to combine parts; do not use it as an arbitrary substitute for Jackson polymorphism configuration.

## 6. Using `@JsonTypeName` When Naming on Subclasses

Instead of putting names in `@JsonSubTypes.Type`, Jackson lets you attach logical names directly on subclasses:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public record CardPayment(String token, String last4) implements PaymentMethod {}
```

When using this style, still register the subclasses in `@JsonSubTypes` but omit the `name` attribute so Jackson reads the name from `@JsonTypeName`:

```java
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class),
    @JsonSubTypes.Type(value = BankTransferPayment.class)
})
```

Correspondingly, put `@JsonTypeName("bank_transfer")` on `BankTransferPayment`. `@JsonTypeName` only names the subtype; by itself it does not replace `@JsonTypeInfo` on the supertype and does not document `oneOf` in OpenAPI.

Do not use Java class names as public discriminators unnecessarily. Logical names like `card` are more stable across package or class renames. If a discriminator name is already used by clients, changing it can be an API contract change.

## 7. When the Supertype Cannot Be Modified: Using a Jackson Mix-in

Some supertypes come from external libraries or shared modules whose source the team does not want to modify. A Jackson mix-in allows attaching Jackson annotations from another class onto the target type.

A mix-in for `PaymentMethod` places annotations at the type level:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
abstract class PaymentMethodMixin {}
```

Register the mix-in with the Jackson builder managed by Spring Boot:

```java
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonPolymorphismConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer paymentMethodMixin() {
        return builder -> builder.mixIn(PaymentMethod.class, PaymentMethodMixin.class);
    }
}
```

Spring Boot applies the customizer when creating the auto-configured `ObjectMapper`. If the application manually declares multiple `ObjectMapper` beans, custom converters, or custom Jackson setups, verify that the mapper actually used by `MappingJackson2HttpMessageConverter` also receives the mix-in.

Mix-ins solve how Jackson serializes/deserializes. For OpenAPI to describe the subtypes accurately, declare `@Schema(oneOf = ..., discriminatorProperty = ..., discriminatorMapping = ...)` on the DTO property or on a documentation class Springdoc reads. Whether Springdoc reflects every mix-in can depend on mapper setup and library version; do not assume mix-ins always generate complete `oneOf` and discriminator entries automatically.

Example declaring the schema directly on the property when `@Schema` cannot be added to the supertype:

```java
public record CreatePaymentRequest(
    @Schema(
        description = "Payment method",
        oneOf = {CardPayment.class, BankTransferPayment.class},
        discriminatorProperty = "kind",
        discriminatorMapping = {
            @DiscriminatorMapping(value = "card", schema = CardPayment.class),
            @DiscriminatorMapping(value = "bank_transfer", schema = BankTransferPayment.class)
        }
    )
    PaymentMethod paymentMethod
) {}
```

## 8. Registering Subtypes via `ObjectMapper` Configuration

Beyond `@JsonSubTypes`, Jackson lets you register subtypes using `NamedType`. This is useful when you want to manage the subtype list centrally in configuration:

```java
import com.fasterxml.jackson.databind.jsontype.NamedType;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PaymentSubtypeConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer registerPaymentSubtypes() {
        return builder -> builder.postConfigurer(mapper ->
            mapper.registerSubtypes(
                new NamedType(CardPayment.class, "card"),
                new NamedType(BankTransferPayment.class, "bank_transfer")
            )
        );
    }
}
```

Subtype registration still needs `@JsonTypeInfo` on the supertype or mix-in so Jackson knows to read the `kind` discriminator. If you use this registration style, there is no need to repeat `@JsonSubTypes`; choose one place as the source of truth for the subtype list to avoid duplicate or mismatched mappings.

Registering subtypes on `ObjectMapper` only configures Jackson runtime behavior. OpenAPI still needs to be documented with `oneOf` and a discriminator. If the supertype cannot carry `@Schema`, place metadata on the DTO property as shown in the previous section.

## 9. Keeping Jackson and OpenAPI Mappings Consistent

A common mistake is Jackson using `bank_transfer` while OpenAPI mapping uses `bank-transfer` or the class name. Requests may still deserialize in some cases, yet documentation instructs clients to send the wrong discriminator.

Maintain a clear mapping table:

| `kind` value in JSON | Java class | OpenAPI schema |
| --- | --- | --- |
| `card` | `CardPayment` | `#/components/schemas/CardPayment` |
| `bank_transfer` | `BankTransferPayment` | `#/components/schemas/BankTransferPayment` |

Check the following points:

1. The name in `@JsonSubTypes.Type(name = ...)`, `@JsonTypeName`, or `NamedType` matches the discriminator value clients send.
2. `@JsonTypeInfo(property = "kind")` uses the same name as `@Schema(discriminatorProperty = "kind")`.
3. `@DiscriminatorMapping(value = ...)` points to the right child schema.
4. Each child schema describes the fields Jackson actually accepts and returns.
5. JSON examples use the exact discriminator and fields of the subtype.
6. All registered subtypes are types the API genuinely permits.

If multiple endpoints use the same polymorphic type, place schema metadata on the supertype or in a shared documentation configuration to prevent operations from drifting apart.

## 10. Testing Deserialization, Serialization, and OpenAPI Docs

Do not look solely at Swagger UI to conclude polymorphism works. Verify both runtime JSON and the specification.

### Testing Input JSON

Send a request with discriminator `card`:

```bash
curl -X POST http://localhost:8080/api/payments \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"paymentMethod":{"kind":"card","token":"tok_demo_123","last4":"4242"}}'
```

Then try `bank_transfer` with its corresponding fields. If the controller receives the right subclass, Jackson selected the subtype from the discriminator.

### Inspecting OpenAPI

Open `/v3/api-docs` or `/v3/api-docs.yaml` and confirm:

- The parent schema `PaymentMethod` has `oneOf` pointing to all supported subtypes.
- Discriminator has `propertyName: kind`.
- Mapping contains `card` and `bank_transfer` referencing the right schemas.
- Child schemas include accurate fields, data types, `required` entries, and examples.
- The operation's request body references the DTO containing `PaymentMethod`.

Swagger UI should display the variants and examples so integrators can choose the right payload. Depending on the Swagger UI version, how `oneOf` is rendered may vary; the JSON/YAML document is the authoritative source for verifying contract structure.

## 11. Handling Invalid Discriminators and Unknown Subtypes

If a request omits `kind` or sends an unregistered value, Jackson can throw an exception such as `InvalidTypeIdException`. Spring MVC typically turns request body conversion errors into `400 Bad Request`, depending on the application's exception handler.

Clearly define API behavior:

- Is the discriminator required?
- Which error code do clients receive if `kind` is missing?
- Which error code do clients receive if `kind` is unsupported?
- When adding a new subtype, do older clients need to handle unknown values?

If you have a custom exception handler, document error responses with actual schemas. Do not automatically pick a default subtype for unrecognized input if that could cause requests to be misinterpreted by business logic.

## 12. Security Notes When Enabling Polymorphic Deserialization

Incoming client JSON requests are untrusted data. Subtype configuration must strictly restrict which classes the API is allowed to instantiate.

- Prefer `JsonTypeInfo.Id.NAME` with an explicit allowlist of subtypes via `@JsonSubTypes` or `NamedType`.
- Avoid `JsonTypeInfo.Id.CLASS` for untrusted payloads because clients could send Java class names, leaking implementation details and expanding the range of types Jackson processes.
- Do not indiscriminately enable global default typing on an `ObjectMapper` that reads external input. If genuinely needed, use a restrictive subtype validator and carefully assess risks.
- Do not register arbitrary classes just to make a payload deserialize. Only register subtypes that belong to the API contract.
- Do not put real payment details, tokens, or personal data into examples.

`Id.NAME` paired with an explicit subtype list keeps the contract stable and limits which types Jackson can instantiate. It is a much safer choice for public APIs than letting clients supply Java class names directly.

## 13. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Jackson reports subtype not found | Missing `@JsonSubTypes`, `@JsonTypeName`, or `NamedType` registration | Check subtype list and `kind` value |
| JSON deserializes into wrong type | Duplicate discriminator names or inconsistent mapping | Use a unique logical name for each subtype |
| Swagger UI does not show subtypes | Missing `@Schema(oneOf = ...)` or Springdoc does not pick up Jackson config | Declare schema explicitly and check `components.schemas` |
| `oneOf` present but missing discriminator | Missing `discriminatorProperty` or mapping | Add `discriminatorProperty` and `@DiscriminatorMapping` |
| Discriminator in JSON differs from OpenAPI | Jackson and `@Schema` use different property names or mapping values | Align `kind`, subtype names, and mappings |
| Mix-in works in another controller but not this endpoint | Converter uses a different `ObjectMapper` than the configured one | Check `HttpMessageConverter` and mapper beans |
| Discriminator field missing in Java object | Jackson uses type id to select subtype without binding it as a regular property | Use `visible = true` only when the DTO genuinely needs to retain that property |
| Request with unknown `kind` returns error | Subtype is not in the allowlist | Document the appropriate error and only register supported types |

## 14. Checklist for Combining Jackson and OpenAPI

- [ ] Supertype has `@JsonTypeInfo` or a mix-in configuring type information.
- [ ] Subtypes are listed explicitly via `@JsonSubTypes`, `@JsonTypeName`, or `NamedType`.
- [ ] Stable logical discriminators such as `card` or `bank_transfer` are used.
- [ ] `@Schema(oneOf = ...)` lists all subclasses completely.
- [ ] `discriminatorProperty` matches `property` in `@JsonTypeInfo`.
- [ ] `@DiscriminatorMapping` matches the subtype names used by Jackson.
- [ ] Child schemas have descriptions and examples matching actual JSON.
- [ ] Mix-ins are attached to the exact `ObjectMapper` used by Spring MVC.
- [ ] Tested JSON deserialization/serialization for every subtype.
- [ ] Verified `oneOf`, discriminator, and mappings in `/v3/api-docs`.
- [ ] Defined how missing or invalid discriminators are handled.
- [ ] Only controlled subtypes are permitted; broad default typing is not enabled for untrusted data.

Jackson decides how JSON is converted into subtypes and how discriminators are written to JSON; Springdoc publishes those subtypes as `oneOf` and `discriminator` in OpenAPI. When annotations, `ObjectMapper` configuration, and schema metadata share the same subtype list and mapping names, the API both deserializes data correctly and provides a clear contract for clients.
