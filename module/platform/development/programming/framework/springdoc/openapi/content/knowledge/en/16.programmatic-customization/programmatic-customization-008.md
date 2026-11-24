# Replacing Shared Types with Version-Appropriate `SpringDocUtils` Configuration

springdoc-openapi normally infers OpenAPI schemas from the Java types used by controllers, DTOs, and parameters. This inference works well for common types such as String, BigDecimal, LocalDate, DTOs, and collections. However, applications may use types from external libraries, custom domain types, or types serialized differently from their default Java structure. If the same type appears across many requests and responses, adding annotations to every property causes repetitive configuration and is hard to maintain.

SpringDocUtils provides shared configuration to replace how springdoc interprets a Java type during documentation generation. The two key methods are replaceWithClass and replaceWithSchema. The first delegates inference to a representative class; the second supplies an OpenAPI Schema directly. This configuration affects the entire application, so choose its scope carefully and apply it before springdoc analyzes models.

## 1. When Should You Use SpringDocUtils?

Consider SpringDocUtils when a Java type is used in many places and needs a single consistent representation in OpenAPI. Examples:

- A currency type from an external library needs to be described as an object containing an amount and a currency code.
- A domain type is serialized via a custom Jackson serializer whose Java structure does not reflect the JSON on the wire.
- An internal wrapper type needs to be replaced by a client-friendly DTO type.
- A parameter type needs to be replaced with a POJO compatible with how Spring MVC binds query parameters.
- A default springdoc mapping needs to be disabled so the library re-infers the source type.

Global configuration is unnecessary if only one field or endpoint has a different representation. When the scope is a single location, annotations such as @Schema, @Parameter, or @ApiResponse are usually clearer. SpringDocUtils fits when the replacement rule is a shared convention everywhere the source type is used.

## 2. Distinguishing replaceWithClass and replaceWithSchema

Both methods take a source type, but their replacement mechanisms differ:

| Method | Target Parameter | How springdoc Generates Schema | Suitable Cases |
| --- | --- | --- | --- |
| replaceWithClass(source, target) | Another Java class | Infers schema from the target class, including its properties and annotations | Source type can be described by a representative DTO or Java model |
| replaceWithSchema(source, schema) | An OpenAPI Schema object | Uses the directly declared schema | Want to specify exact type, format, properties, enum, or example without a proxy class |

For example, if the source type MoneyAmount is actually serialized as a JSON object with amount and currency, you can map it to an ApiMoneyAmount class with those two properties via replaceWithClass. If you only want to describe that object using an OpenAPI model, you can use replaceWithSchema.

Crucially, both approaches change documentation generation only. They do not alter Java types in controllers, convert objects at runtime, or configure Jackson. Actual JSON is still governed by application code, HttpMessageConverters, and serializers.

## 3. Identifying the Package by Springdoc Version

The package name of SpringDocUtils changed when moving from springdoc 1.x to 2.x:

| Springdoc Line | Corresponding Spring Boot | SpringDocUtils Import |
| --- | --- | --- |
| 1.x | Spring Boot 1.x and 2.x | org.springdoc.core.SpringDocUtils |
| 2.x | Spring Boot 3.x | org.springdoc.core.utils.SpringDocUtils |
| 3.x | Spring Boot 4.x | org.springdoc.core.utils.SpringDocUtils |

When upgrading from springdoc 1.x to 2.x, update imports to the new package. Do not copy imports from older examples if the project uses a 2.x or 3.x starter. Check the actual dependency version and matching Javadoc if your IDE cannot find the class or method.

The Java examples in this guide use the springdoc 2.x/3.x import:

~~~java
import org.springdoc.core.utils.SpringDocUtils;
~~~

For springdoc 1.x, change the import to:

~~~java
import org.springdoc.core.SpringDocUtils;
~~~

## 4. Configuring replaceWithClass

replaceWithClass takes a source class and a target class. When springdoc encounters the source type during schema generation, it uses the target class to infer structure. The target class should be a clear model accurately reflecting the JSON the API exchanges.

Suppose the system uses a MoneyAmount type from a financial library. Jackson has been configured to serialize it as an object with amount and currency code. Create a representative class:

~~~java
import java.math.BigDecimal;

public class ApiMoneyAmount {

    private BigDecimal amount;
    private String currency;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Register the replacement once in configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springdoc.core.utils.SpringDocUtils;

@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .replaceWithClass(MoneyAmount.class, ApiMoneyAmount.class);
    }
}
~~~

After configuration, properties or parameters of type MoneyAmount are described according to the ApiMoneyAmount structure. For instance, if a DTO has the field:

~~~java
public class InvoiceResponse {
    private Long id;
    private MoneyAmount total;
}
~~~

the InvoiceResponse schema can reference the schema representing ApiMoneyAmount. Expected structure:

~~~yaml
InvoiceResponse:
  type: object
  properties:
    id:
      type: integer
      format: int64
    total:
      $ref: '#/components/schemas/ApiMoneyAmount'

ApiMoneyAmount:
  type: object
  properties:
    amount:
      type: number
    currency:
      type: string
~~~

The final component name may depend on class names, annotations, and model converter settings. Inspect the generated JSON rather than assuming every version names components identically to the example.

The springdoc FAQ also illustrates replacing MonetaryAmount with a built-in springdoc model:

~~~java
SpringDocUtils.getConfig()
    .replaceWithClass(
        MonetaryAmount.class,
        org.springdoc.core.converters.models.MonetaryAmount.class
    );
~~~

This is a convenient option when the target model provided by springdoc already reflects the exact representation the application wants to publish.

## 5. Configuring replaceWithSchema

If you prefer not to create an intermediate Java class, you can pass a Schema from swagger-models directly. For example, describing MoneyAmount as an object with amount and currency:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springdoc.core.utils.SpringDocUtils;

import io.swagger.v3.oas.models.media.NumberSchema;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;

@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .replaceWithSchema(
                MoneyAmount.class,
                new ObjectSchema()
                    .description("Monetary amount with currency code")
                    .addProperties(
                        "amount",
                        new NumberSchema().example(99.96)
                    )
                    .addProperties(
                        "currency",
                        new StringSchema().example("USD")
                    )
            );
    }
}
~~~

The replacement schema can declare any required OpenAPI properties:

- description to explain the type's meaning.
- type to identify the general data type.
- format to describe a specific format where appropriate.
- properties to define object fields.
- items to describe array elements.
- enum to constrain valid values.
- example or examples to provide sample data.
- required to list mandatory object properties.

For example, if currency is always required and amount must also be present, you can add required:

~~~java
ObjectSchema moneySchema = new ObjectSchema()
    .description("Monetary amount with currency code")
    .addProperties("amount", new NumberSchema().example(99.96))
    .addProperties("currency", new StringSchema().example("USD"))
    .addRequiredItem("amount")
    .addRequiredItem("currency");
~~~

Only declare required when the API truly enforces that field. Manually constructed schemas do not apply validation to runtime objects; if the application accepts a missing amount or blank currency, documentation should not publish stricter constraints than actual behavior.

## 6. Placing Configuration at the Right Time

SpringDocUtils.getConfig() returns the library's shared configuration. Replacement rules must be registered before springdoc processes models to generate OpenAPI. Springdoc documentation and official examples commonly place configuration inside a static initializer:

~~~java
@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .replaceWithClass(MoneyAmount.class, ApiMoneyAmount.class);
    }
}
~~~

The static block executes when the configuration class is loaded, registering the rule early. Multiple replacements can be chained in a single call sequence:

~~~java
static {
    SpringDocUtils.getConfig()
        .replaceWithClass(MoneyAmount.class, ApiMoneyAmount.class)
        .replaceWithSchema(
            LegacyIdentifier.class,
            new StringSchema()
                .description("String-formatted identifier")
                .example("ORD-2026-001")
        );
}
~~~

Do not register replaceWithClass or replaceWithSchema inside a request handler or on every API call. This is shared configuration, not a per-request document generation action. Also avoid placing this registration inside OpenApiCustomizer if the goal is to change how model converters handle the source type; customizers run in the document customization phase, after model inference may already have taken place.

Keep replacements centralized in a single configuration class. When multiple places register replacements for one source type, results become unpredictable and hard to maintain. A single rule per source type helps reviewers see which model represents that type.

## 7. Distinguishing Schema Replacement from Parameter Object Replacement

SpringDocUtils also provides replaceParameterObjectWithClass. This method serves cases where a type is used as a parameter object, such as an object bound by Spring MVC from multiple query parameters. It does not serve the same purpose as replaceWithClass:

| Method | Scope |
| --- | --- |
| replaceWithClass | Replaces the class used to infer the schema of a source type in general |
| replaceWithSchema | Replaces with an OpenAPI Schema for a source type in general |
| replaceParameterObjectWithClass | Replaces the representative class when handling the source type as a parameter object |

For example, in legacy projects needing to map Pageable to an API Pageable class so query parameter documentation expands properly:

~~~java
static {
    SpringDocUtils.getConfig()
        .replaceParameterObjectWithClass(
            Pageable.class,
            ApiPageable.class
        );
}
~~~

This is a specialized scenario. Newer springdoc versions include built-in Pageable support; check the documentation for your release line before adding manual replacements. If you only need to describe a parameter, the @ParameterObject annotation and Spring Data Web configuration may be a better choice.

## 8. Disabling an Existing Replacement Mapping

SpringDocUtils provides disableReplacement(source) to turn off a replacement rule already registered for a source type. This is useful when springdoc or an integration module provides a default mapping, yet the application needs the source type handled differently.

For example, an application might want to remove the default mapping for Pageable to describe the type itself:

~~~java
@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .disableReplacement(Pageable.class);
    }
}
~~~

Once replacement is disabled, springdoc will not use the disabled mapping for that source type. This does not automatically create a new replacement schema. If the source type cannot be inferred into a useful schema, add appropriate configuration or use annotations/another customizer.

Do not call disableReplacement purely by trial and error without identifying which mapping is active. Check the integration module documentation and current output before disabling, as the default mapping may already help represent framework types accurately against the API contract.

## 9. Impact Scope and Limitations

SpringDocUtils is shared application-wide configuration. When replacing a source type, every place springdoc encounters that type can be affected: DTO properties, request bodies, response bodies, collection elements, or parameters depending on the corresponding inference mechanism.

Therefore:

- Do not use global replacement if only one endpoint requires a different structure.
- Do not pick a target class just because its name or properties look similar; it must match actual JSON.
- Do not use a replacement schema to describe a type that runtime serializes in a different shape.
- Do not assume schema replacement changes Jackson, validation, or how Spring binds requests.
- Do not register multiple conflicting mappings for the same source type.
- Do not overlook generics or nested types in the target class; verify generated secondary schemas and references.

If the same Java type has multiple representations depending on context, global replacement is unsuitable. For instance, MoneyAmount in a public response might need an amount/currency object, whereas a query parameter accepts only the string "99.96 USD". Describe each operation separately using @Schema, @Parameter, or a customizer instead of forcing every usage of the source type into one schema.

## 10. Verifying Output in OpenAPI

After registering configuration, start the application and fetch the specification at the default /v3/api-docs endpoint or your customized endpoint. Verify:

1. The source type has been replaced by the expected class or schema.
2. Properties of the representative class appear completely with the right types.
3. Schemas of nested types are registered in components.schemas.
4. Operations using the source type reference valid schemas.
5. No legacy or default schemas conflict with the new mapping.
6. Actual request and response JSON have the exact structure described.
7. Separate document groups also receive the replacement configuration properly.

You can fetch the document using curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

If the application has multiple groups, check each /v3/api-docs/{group} URL. Do not verify a component in only the default document and assume all groups match.

After inspecting the schema, call the actual endpoint and inspect the JSON response or request payload. For example, if the schema publishes MoneyAmount as an object:

~~~json
{
  "amount": 99.96,
  "currency": "USD"
}
~~~

then the runtime serializer must also produce an object with the same structure. If the API actually returns only the string "USD 99.96", the object schema is wrong even if Swagger UI renders cleanly.

Write contract or integration tests verifying both the OpenAPI schema and actual JSON. When upgrading springdoc, swagger-core, or Spring Boot, re-run checks because converters and inference mechanisms can change between versions.

## 11. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| SpringDocUtils import does not exist | Using package from a different version line | Check dependency and use the right package for v1 or v2/v3 |
| Replacement has no effect | Configuration registered after springdoc analyzed models or configuration class not loaded | Place registration in a static initializer of a configuration loaded early by Spring |
| Schema looks right yet runtime JSON differs | Confused documentation replacement with data conversion | Sync Jackson serializer/deserializer or fix schema to match real JSON |
| One type changes across unexpected endpoints | Used SpringDocUtils for a case belonging to a single endpoint | Switch to @Schema, @Parameter, or operation customizer |
| Representative class misses properties | Target model does not reflect full payload | Add getters/fields and check actual Jackson properties |
| Nested component is missing | Target model has complex reference types or converter behaves unexpectedly | Inspect components.schemas, generic types, and swagger-core version |
| Object schema lacks expected required fields | Manual schema did not declare required | Add required for truly mandatory fields and check runtime validation |
| Pageable renders differently after disabling replacement | Spring Data default mapping was turned off | Restore mapping or declare a version-appropriate parameter object |
| Same source type needs multiple contextual schemas | Global replacement cannot express per-operation differences | Use distinct schemas on properties or operations requiring differences |

## 12. Safe Adoption Workflow

When you need to replace a shared type, follow this sequence:

1. Identify the source type and every place it appears in the API.
2. Inspect actual JSON serialized or deserialized by Jackson.
3. Decide whether global replacement is appropriate or only a single field/operation needs customization.
4. Choose replaceWithClass if an exact representative Java model exists; choose replaceWithSchema to declare OpenAPI structure directly.
5. Check the SpringDocUtils package for your springdoc release line.
6. Register the rule early in a static initializer and centralize configuration in one place.
7. Download the OpenAPI JSON and check components, references, and every relevant operation.
8. Call live endpoints to compare request/response payloads against the schema.
9. Re-run tests when upgrading library versions or modifying serializers.

## 13. Official References

- [springdoc-openapi FAQ](https://springdoc.org/faq.html) — replaceWithClass and replaceWithSchema examples for MonetaryAmount.
- [springdoc-openapi v2 FAQ](https://springdoc.org/v2/faq.html) — SpringDocUtils configuration and Spring Boot 3 compatibility examples.
- [springdoc-openapi v2 — Migration from v1](https://springdoc.org/v2/#migrating-from-springdoc-openapi-v1) — package change of SpringDocUtils from org.springdoc.core to org.springdoc.core.utils.
- [SpringDocUtils Javadoc v1.8.0](https://javadoc.io/static/org.springdoc/springdoc-openapi-common/1.8.0/org/springdoc/core/SpringDocUtils.html) — replaceWithClass, replaceWithSchema, replaceParameterObjectWithClass, and disableReplacement APIs for 1.x.
- [SpringDocConfiguration source](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-common/src/main/java/org/springdoc/core/configuration/SpringDocConfiguration.java) — how current configuration uses SpringDocUtils during initialization.

SpringDocUtils standardizes how springdoc interprets a Java type used in many places. Choosing between a representative class and a direct schema, using the version-appropriate package, registering configuration before documentation generation, and cross-checking against runtime JSON keeps the OpenAPI contract accurate without repeating annotations across every DTO.
