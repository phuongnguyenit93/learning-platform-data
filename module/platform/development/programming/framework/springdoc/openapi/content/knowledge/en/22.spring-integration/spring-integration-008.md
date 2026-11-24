# Javadoc as a Supplementary Source of Descriptions When Supported

Javadoc is commonly written right next to methods and fields to explain the purpose, inputs, and outputs of Java code. Springdoc-openapi can read certain Javadoc comments to supplement descriptions in the OpenAPI document. Thus, the same explanation can serve both source-code readers and API consumers in Swagger UI.

This capability must be configured properly. Springdoc does not automatically read all Javadoc just because a project has comments in source files. You need the `therapi-runtime-javadoc` library to read metadata at runtime and the `therapi-runtime-javadoc-scribe` annotation processor to extract Javadoc during compilation. Without both components, Javadoc support can fail silently without a clear error.

## 1. What Role Does Javadoc Play in OpenAPI Documentation?

Springdoc builds OpenAPI from controllers, Spring configuration, Java types, and Swagger annotations. Javadoc acts as an additional description source for certain inferred elements.

According to mappings published in springdoc documentation:

| Javadoc source | Supplemented OpenAPI element |
|---|---|
| Method comment | `description` of `@Operation` |
| Method `@return` tag | `description` of response in `@Operation` |
| Model field/attribute comment | `description` of property in `@Schema` |

For example, a comment on a controller method can become the operation description; the `@return` tag explains the response content; a comment on a DTO field explains the property in the schema.

Javadoc supplements natural-language descriptions. It does not determine HTTP methods, URLs, status codes, security schemes, or full request/response structures. That information is still inferred by springdoc from Spring mappings and types, or must be declared with Swagger annotations when inference is insufficient.

## 2. How It Works: Compile-Time Processing and Runtime Reading

Javadoc comments are source-code comments. The JVM does not retain all these comments as part of standard reflection metadata. Therefore, springdoc requires a dedicated mechanism to read comment contents when generating documentation.

`therapi-runtime-javadoc-scribe` is an annotation processor. During compilation, the processor reads Javadoc and generates metadata for later use. `therapi-runtime-javadoc` is the runtime library providing access to that metadata. Springdoc integrates with the runtime library to place descriptions into OpenAPI.

The processing flow can be visualized as follows:

```text
Java source
   |
   | Javadoc comments
   v
therapi-runtime-javadoc-scribe
   |
   | metadata generated at compile time
   v
Build output
   |
   | runtime dependency
   v
therapi-runtime-javadoc
   |
   v
springdoc-openapi
   |
   v
OpenAPI JSON/YAML -> Swagger UI
```

If you only add the runtime library without running the annotation processor, the required metadata will not be generated. If you only configure the processor without the runtime library, springdoc has no component to read the metadata at runtime. Both must be declared.

## 3. Choosing the Springdoc Dependency Matching Your Web Stack

In springdoc-openapi 2.x, Javadoc support is already built into `springdoc-openapi-starter-common`. You do not need to add the legacy `springdoc-openapi-javadoc` module for projects using 2.x starters.

Choose the starter by stack:

| Application | Only OpenAPI JSON/YAML needed | Swagger UI needed |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

If the project already has a UI starter, there is no need to add an API starter just to enable Javadoc. The UI starters already pull in the required API parts. The springdoc version must match the project's Spring Boot version: the 2.x line is for Spring Boot 3, the 3.x line is for Spring Boot 4; older Spring Boot 2 projects use the 1.x line per their corresponding guide.

Differences in Javadoc modules across major versions:

| Springdoc line | How Javadoc is integrated |
|---|---|
| v1.8.x | Use the separate `springdoc-openapi-javadoc` module alongside the matching UI/API starter and Therapi processor/runtime |
| v2.x | Javadoc support is included in `springdoc-openapi-starter-common`; do not add the v1 module |
| v3.x | Use the matching starter from the current line; do not use the v1 `springdoc-openapi-javadoc` module |

Do not mix artifacts across major versions. When upgrading from v1 to v2, remove the old Javadoc module and use a v2 starter compatible with Spring Boot 3.

## 4. Adding Runtime Library and Annotation Processor with Maven

For springdoc 2.x, add `therapi-runtime-javadoc` to dependencies and `therapi-runtime-javadoc-scribe` to annotation processor paths.

```xml
<dependencies>
    <!-- Existing Spring Boot and springdoc dependencies -->
    <dependency>
        <groupId>com.github.therapi</groupId>
        <artifactId>therapi-runtime-javadoc</artifactId>
        <version>0.15.0</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.github.therapi</groupId>
                        <artifactId>therapi-runtime-javadoc-scribe</artifactId>
                        <version>0.15.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Place the processor in `annotationProcessorPaths` so the Maven Compiler Plugin runs it during compilation. If the project already configures other processors such as Lombok or MapStruct, append Therapi to the existing list instead of replacing the entire list; otherwise, earlier processors may stop running.

Version `0.15.0` is the version shown in springdoc v2 documentation. If your organization manages dependency versions centrally, place the version in dependency management or a property according to project conventions.

## 5. Gradle Configuration

With Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    runtimeOnly("com.github.therapi:therapi-runtime-javadoc:0.15.0")
    annotationProcessor("com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0")
}
```

With Gradle Groovy DSL (`build.gradle`):

```groovy
dependencies {
    runtimeOnly 'com.github.therapi:therapi-runtime-javadoc:0.15.0'
    annotationProcessor 'com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0'
}
```

`annotationProcessor` places the processor on the dedicated annotation-processing compile classpath; `runtimeOnly` puts the Javadoc reader library on the runtime classpath. If the project uses multiple source sets or separate Java modules, ensure the processor and runtime dependency are declared in the modules that actually compile controllers/DTOs and run the application.

## 6. Writing Javadoc for Controller Methods

The method comment is used as the operation `description`. The `@return` tag is used as the response description.

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * Returns products that the current caller is permitted to view.
     * Results are sorted by creation time, newest first.
     *
     * @return list of products matching the current query
     */
    @GetMapping
    List<ProductResponse> listProducts() {
        return productService.listVisibleProducts();
    }
}
```

When Javadoc support is active, springdoc can generate an operation similar to:

```yaml
paths:
  /api/products:
    get:
      description: >-
        Returns products that the current caller is permitted to view.
        Results are sorted by creation time, newest first.
      responses:
        '200':
          description: list of products matching the current query
```

This illustrates the shape of the relevant metadata; the actual document may also include `operationId`, tags, content, and schemas inferred from the controller and DTOs.

Write method descriptions in terms of API behavior observable by clients. Avoid exposing implementation details such as repository names, SQL queries, internal caches, or algorithms that do not affect the contract.

## 7. Writing Javadoc for DTO Fields

A field comment in a model can become the `description` of the property in the schema.

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(name = "ProductResponse", description = "Product details returned by the API")
public class ProductResponse {

    /** Stable identifier assigned to the product. */
    private UUID id;

    /** Product name displayed to customers. */
    private String name;

    /** Current selling price in the store's currency. */
    private BigDecimal price;

    // Constructors, getters and setters
}
```

The schema portion may be generated similarly to:

```yaml
ProductResponse:
  type: object
  properties:
    id:
      type: string
      format: uuid
      description: Stable identifier assigned to the product.
    name:
      type: string
      description: Product name displayed to customers.
    price:
      type: number
      description: Current selling price in the store's currency.
```

Field Javadoc only supplements the property's meaning. Data types are still inferred by springdoc from Java types/Jackson models; constraints like required, min/max, format, or enum may require Bean Validation and `@Schema`.

## 8. Combining Javadoc with Swagger Annotations

Javadoc and Swagger annotations can coexist. When both provide a description for the same element, springdoc documentation specifies that the description from the Swagger annotation takes precedence.

Method example:

```java
/**
 * Returns products that the current caller is permitted to view.
 *
 * @return list of products matching the current query
 */
@Operation(description = "Returns active products in the current store.")
@GetMapping
List<ProductResponse> listProducts() {
    return productService.listVisibleProducts();
}
```

`@Operation(description = ...)` is the prioritized description source for this operation. Javadoc remains useful for source-code documentation, but will not override an explicit description in the Swagger annotation.

Field example:

```java
/** Price before applying promotional campaigns. */
@Schema(description = "Final price the customer must pay.")
private BigDecimal price;
```

`@Schema(description = ...)` takes precedence for the property. This combination is helpful when you want Javadoc to explain code internals to developers while OpenAPI uses more concise, client-oriented phrasing.

## 9. Javadoc Does Not Replace `@Operation`, `@ApiResponse`, and `@Parameter`

Javadoc is suited for prose descriptions. For structured metadata, continue using Swagger annotations or Spring mappings.

| Information to describe | Appropriate mechanism |
|---|---|
| HTTP method and path | `@GetMapping`, `@PostMapping`, `@RequestMapping` |
| Explicit operation summary and description | `@Operation` |
| Response codes and response schemas | `@ApiResponse`, `@ApiResponses` |
| Query/path/header parameters | `@Parameter`, `@Parameters`, and Spring parameter annotations |
| Request body schema | Spring's `@RequestBody` with `@Content`/`@Schema` when explicit description is needed |
| Default field description | Javadoc on field or `@Schema(description = ...)` |
| Security scheme and requirement | `@SecurityScheme`, `@SecurityRequirement` |
| Concrete examples | `@ExampleObject`, `@Parameter(example = ...)`, `@Schema(example = ...)` |
| Requiredness, limits, and validation | Bean Validation and `@Schema` |

Springdoc documentation notes that the primary Javadoc mappings are method comments, `@return`, and field/attribute comments. Do not assume all Javadoc tags like `@throws`, `@see`, `@since`, or `@param` automatically map to corresponding OpenAPI elements. For parameter descriptions, declaring `@Parameter` is explicit and easier to verify.

## 10. Precedence Rules When Descriptions Are Declared in Multiple Places

When an element has both Javadoc and a Swagger annotation, the Swagger annotation with a description wins. Therefore, if you update Javadoc and Swagger UI does not change, check whether `@Operation(description = ...)`, `@ApiResponse(description = ...)`, or `@Schema(description = ...)` is already supplying a value.

Establish a team convention:

- Use Javadoc as the default description when no special OpenAPI wording is needed.
- Use Swagger annotations when an API contract needs tailored phrasing.
- Avoid maintaining two diverging descriptions without reason; they easily cause source documentation and API documentation to contradict each other.
- If an annotation overrides Javadoc, update both whenever the content matters to both code readers and API consumers.

## 11. Checking That Dependencies and the Annotation Processor Are Working

When Javadoc does not appear in OpenAPI, check in order:

1. The project uses the right springdoc starter for Spring MVC or WebFlux.
2. The runtime classpath includes `therapi-runtime-javadoc`.
3. Compilation runs `therapi-runtime-javadoc-scribe`.
4. The processor is configured in the exact modules containing controller and DTO sources.
5. The build tool actually executes annotation processing without compiler flags disabling it.
6. Source files have Javadoc comments on the right methods or fields.
7. No Swagger annotation description is overriding Javadoc.
8. The application is running from the latest build output after adding the processor.

With Maven, inspect compile logs to confirm the compiler plugin and annotation processor executed. With Gradle, check the `annotationProcessor` configuration of the corresponding source set. After enabling the processor for the first time, run a clean build so metadata is regenerated; do not merely restart using stale class outputs.

Note: springdoc documentation warns that if either the runtime library or the annotation processor is missing, Javadoc support may fail silently. Thus, the application starting successfully does not prove the feature is fully configured.

## 12. Verifying Contents in OpenAPI JSON/YAML

After running the application, fetch the default OpenAPI document:

```bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
```

Inspect the operation description:

```bash
jq '.paths["/api/products"].get.description' openapi.json
```

Inspect the response description:

```bash
jq '.paths["/api/products"].get.responses["200"].description' openapi.json
```

Inspect a field description in the schema:

```bash
jq '.components.schemas.ProductResponse.properties.name.description' openapi.json
```

If the application exports YAML, inspect `/v3/api-docs.yaml` or use a YAML parser. These URLs may change if the project configures `springdoc.api-docs.path` or runs under a context path.

Compare the results against Javadoc in source code. Do not inspect only Swagger UI; checking JSON/YAML verifies whether descriptions were actually written into the OpenAPI document rather than rendered by a UI layer.

## 13. Verifying in Swagger UI

Swagger UI displays descriptions fetched from the OpenAPI document:

- Method Javadoc appears in the operation description section.
- `@return` may appear in the corresponding response description.
- Field Javadoc appears in property descriptions of schema models.

If a description is long, split it into short sentences or paragraphs. Content should explain meaning, usage conditions, units, time zones, or business rules that the field name alone cannot convey. Avoid repeating the property name verbatim or writing overly long paragraphs on a single line.

Swagger UI only renders the OpenAPI document. If the document lacks descriptions, fix the metadata source or processor configuration; changing CSS or UI styling will not solve the root cause.

## 14. Complete Example: Controller and DTO Using Javadoc

Example combining Javadoc for methods/fields and annotations for structured parts:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * Returns products belonging to the requested category.
     * Results are sorted by most recently created product first.
     *
     * @return products belonging to the selected category
     */
    @Operation(operationId = "listProducts", summary = "List products")
    @GetMapping
    List<ProductResponse> listProducts(
            @Parameter(description = "Filter by product category", example = "accessories")
            @RequestParam(required = false) String category) {
        return productService.list(category);
    }
}

@Schema(name = "ProductResponse")
class ProductResponse {

    /** Stable identifier issued by the product service. */
    private UUID id;

    /** Product name displayed in the store. */
    private String name;

    /** Current selling price in the store's currency. */
    private BigDecimal price;

    // Constructors, getters and setters
}
```

In this example:

- `@Operation` supplies an explicit `operationId` and summary.
- Javadoc on `listProducts` supplies the operation description.
- Javadoc `@return` supplies the response description.
- Javadoc on `id`, `name`, and `price` supplies property descriptions in `ProductResponse`.
- `@RequestParam` with Java types supplies parameter info; when a dedicated description is needed for a query parameter, add `@Parameter`.

This example illustrates metadata placement. When adding it to a project, supply imports, service implementation, getters/setters, and response annotations matching your actual structure.

## 15. Common Mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Javadoc does not appear in OpenAPI | Missing runtime library or annotation processor | Add `therapi-runtime-javadoc` and `therapi-runtime-javadoc-scribe` |
| Build succeeds but no descriptions appear | Annotation processor did not run; support can fail silently | Check Maven/Gradle configuration and run a clean build |
| Method description does not change | `@Operation(description = ...)` is overriding Javadoc | Check Swagger annotation descriptions |
| Field description does not change | `@Schema(description = ...)` is already declared | Update the annotation or remove duplicate description if using Javadoc |
| `@return` does not appear as expected | Method lacks Javadoc tag or response annotation already has a description | Check `@return` and `@ApiResponse(description = ...)` |
| Only one module has Javadoc | Processor configured in only one module | Declare the processor in every module compiling sources to document |
| Maven stops running Lombok/MapStruct after adding Therapi | Overwrote existing `annotationProcessorPaths` | Merge all processors into the same configuration |
| Swagger UI does not show new content | OpenAPI JSON/YAML not regenerated or viewing a different group | Check the exact docs endpoint and build output directly |
| Relying on `@param` yet parameter has no description | Not every Javadoc tag is equally supported by documentation | Use `@Parameter(description = ...)` to declare explicitly |
| Comments contain implementation details confusing to clients | Javadoc was written for code maintainers, not API consumers | Write descriptions around API behavior or override with Swagger annotations |

## 16. Guidelines for Writing Good API Javadoc

- Describe methods by behavior observable to clients, not merely repeating the method name.
- Use `@return` to explain what the returned data represents, not just writing "result".
- Describe fields with business meaning, units, format, or important rules.
- Keep Javadoc concise, clear, and free of sensitive internal details.
- Use `@Operation`, `@ApiResponse`, `@Parameter`, and `@Schema` when structured metadata or OpenAPI-specific content is needed.
- Ensure both the runtime library and annotation processor are configured together.
- If the project uses multiple annotation processors, merge configurations instead of overwriting existing processors.
- Inspect OpenAPI JSON/YAML after compiling and running the application.
- Keep descriptions in Javadoc and Swagger annotations consistent to avoid conflicting documentation.

## Conclusion

Javadoc can be a useful supplementary source for springdoc-openapi: method comments become operation descriptions, `@return` becomes response descriptions, and field comments become schema property descriptions. For this feature to work, both `therapi-runtime-javadoc` at runtime and `therapi-runtime-javadoc-scribe` as an annotation processor are required. In springdoc 2.x, Javadoc support is already included in the common starter; no separate v1 Javadoc module is needed. When a Swagger annotation also declares a description, the annotation takes precedence. Use Javadoc for natural descriptions, Swagger annotations for structured metadata, and verify the result in OpenAPI JSON/YAML and Swagger UI.

## References

- [springdoc-openapi v2 – Javadoc support, section 3.13](https://springdoc.org/v2/)
- [springdoc-openapi v2 – Migrating from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Therapi Runtime Javadoc](https://github.com/dnault/therapi-runtime-javadoc)
