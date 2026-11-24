# Reading Custom Application Annotations to Generate Metadata

In a Spring Boot application, multiple controllers may share a business convention that standard Spring MVC or OpenAPI annotations cannot fully express. For example, a development team might want to mark operations belonging to the catalog domain, identify internal endpoints, attach a business code, describe a parameter's sensitivity level, or apply a documentation rule across many controllers.

Java lets you create **custom annotations** to store metadata directly on classes, methods, or parameters. springdoc-openapi provides extension points such as **OperationCustomizer** and **ParameterCustomizer** to read that metadata and attach it to the OpenAPI objects being generated.

The processing flow has two parts: the custom annotation captures the application's intent; the customizer reads the annotation and translates that intent into OpenAPI metadata. This approach lets you reuse documentation conventions across many endpoints without repeating the same configuration on every operation.

## 1. When Are Custom Annotations Needed?

Standard annotations already cover most needs:

- @GetMapping and @PostMapping define Spring MVC routes.
- @Operation describes summary, description, operationId, and tags.
- @Parameter describes HTTP parameters.
- @Schema describes data structures.
- @ApiResponse describes an operation's responses.

Custom annotations are useful when the application has proprietary metadata, such as:

| Custom Metadata | Example Need |
|---|---|
| Business domain | Mark operations belonging to catalog, orders, or billing |
| Publication scope | Mark internal or partner-facing operations |
| Feature code | Attach a use case ID readable by documentation systems or contract checkers |
| Parameter rules | Describe identifiers, sensitive values, or deprecation conventions |
| Tooling metadata | Add x-* extensions for an API gateway or pipeline |

Do not create a custom annotation merely to wrap an existing attribute of @Operation or @Schema. A custom annotation is worthwhile when it encapsulates an application convention that is reused repeatedly and handled consistently in one place.

For example, if many operations need a business domain code attached to OpenAPI, you can declare @ApiDomain on controllers or methods, then use an OperationCustomizer to read the annotation and add the x-business-domain extension.

## 2. Declaring Custom Annotations Properly

An annotation intended to be read at runtime needs three key elements:

- **@Target** specifies where the annotation is allowed to appear.
- **@Retention(RetentionPolicy.RUNTIME)** retains the annotation in bytecode so reflection can read it.
- **@Documented** allows the annotation to appear in the Javadoc of marked elements.

Example annotation describing operation metadata:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE
})
public @interface ApiDomain {

    String value();

    String description() default "";

    boolean internal() default false;

    boolean deprecated() default false;
}
~~~

Meaning:

- **TYPE** allows marking a controller or class.
- **METHOD** allows overriding metadata on individual handler methods.
- **ANNOTATION_TYPE** allows using ApiDomain as a meta-annotation to create specialized annotations.
- **RUNTIME** is required for customizers to read the annotation via reflection.
- **value** is the business domain name; the remaining attributes have defaults so callers do not have to specify every field.

Valid annotation attribute types include primitives, String, Class, enums, annotations, and arrays of these types. Arbitrary objects or collections cannot be used directly as annotation attributes.

### Why Is RetentionPolicy.RUNTIME Important?

Java has three retention policies:

| Retention | Where Does the Annotation Remain? | Readable via Reflection at Runtime? |
|---|---|---|
| SOURCE | Only in source code before compilation | No |
| CLASS | Stored in the class file but not guaranteed in runtime reflection | Not via standard reflection |
| RUNTIME | Retained for reflection access | Yes |

If a custom annotation uses SOURCE or CLASS, customizers cannot read it using standard reflection APIs. For metadata that springdoc must process at startup or document generation time, use RUNTIME.

## 3. Placing Annotations on Controllers and Methods

An annotation can be placed at the class level to supply default metadata for the entire controller:

~~~java
@ApiDomain(
    value = "catalog",
    description = "Lookup and management operations for the catalog"
)
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @GetMapping("/books")
    public List<BookResponse> listBooks() {
        // ...
        return List.of();
    }

    @GetMapping("/authors")
    public List<AuthorResponse> listAuthors() {
        // ...
        return List.of();
    }
}
~~~

If a method has specific metadata, place the annotation directly on the method:

~~~java
@ApiDomain(
    value = "catalog-search",
    description = "Search for books by keyword"
)
@GetMapping("/search")
public List<BookResponse> search(
    @RequestParam String keyword
) {
    // ...
    return List.of();
}
~~~

A simple convention is **method-level wins over class-level**. If the method has @ApiDomain, use the method's metadata; otherwise, take metadata from the controller. Precedence rules must be defined explicitly in the customizer so behavior does not depend on guesswork.

Annotations can be used at both levels without conflict:

- The controller declares the default catalog domain.
- The search method declares catalog-search.
- The listBooks and listAuthors methods inherit catalog metadata per the customizer's convention.

## 4. Reading Annotations with Java Reflection

Java Reflection allows retrieving annotations directly from a class or method:

~~~java
ApiDomain classMetadata =
    CatalogController.class.getAnnotation(ApiDomain.class);

Method method = CatalogController.class.getMethod("listBooks");
ApiDomain methodMetadata =
    method.getAnnotation(ApiDomain.class);
~~~

If the annotation is declared directly, this approach works. However, getAnnotation is not always sufficient in Spring applications:

- It does not resolve all composed annotations automatically.
- It does not apply Spring's attribute aliasing rules.
- Looking up metadata on interfaces, superclasses, or overridden methods requires an explicit lookup policy.

Spring provides **AnnotatedElementUtils** and **MergedAnnotations** to look up annotations using merged-annotation semantics. These APIs are helpful when custom annotations are composed from multiple annotations or use @AliasFor.

Example finding a merged annotation:

~~~java
ApiDomain metadata =
    AnnotatedElementUtils.findMergedAnnotation(
        handlerMethod.getMethod(),
        ApiDomain.class
    );
~~~

For the controller class:

~~~java
ApiDomain classMetadata =
    AnnotatedElementUtils.findMergedAnnotation(
        handlerMethod.getBeanType(),
        ApiDomain.class
    );
~~~

**findMergedAnnotation** can locate direct annotations and meta-annotations via Spring's mechanism while synthesizing aliased attributes. If the system places annotations on interfaces or superclass methods, decide explicitly whether to search the entire type hierarchy and use MergedAnnotations with the appropriate SearchStrategy. Never assume every reflection call discovers annotations across every inheritance position.

### @Inherited Does Not Solve All Cases

Java's @Inherited only affects annotation lookup on a subclass when the annotation is declared on a superclass. It does not propagate annotations across interfaces, does not apply to methods, and does not apply to parameters.

If you need to read annotations from interfaces or method hierarchies, use Spring's merged-annotation lookup with an appropriate strategy and write tests for that inheritance convention.

## 5. Creating Composed Annotations with Meta-Annotations and @AliasFor

When many controllers belong to the same domain, you can create a specialized annotation so developers do not have to repeat the domain value.

~~~java
import org.springframework.core.annotation.AliasFor;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE
})
@ApiDomain(value = "catalog")
public @interface CatalogApi {

    @AliasFor(
        annotation = ApiDomain.class,
        attribute = "description"
    )
    String description() default "";
}
~~~

Usage:

~~~java
@CatalogApi(
    description = "Book and author lookup operations"
)
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {
    // ...
}
~~~

**@AliasFor** tells Spring that CatalogApi's description attribute maps to ApiDomain's description attribute. When using AnnotatedElementUtils.findMergedAnnotation to look up ApiDomain, Spring returns the merged metadata from the composed annotation.

Conditions to uphold:

- The base annotation must allow ANNOTATION_TYPE if used as a meta-annotation.
- The composed annotation must have RUNTIME retention if customizers read it at runtime.
- The type and default value of the aliased attribute must be compatible with the target attribute.
- Do not create circular aliases or map attributes with unrelated meanings.

If only a fixed value is needed, a meta-annotation does not require @AliasFor. Use aliases when callers of the specialized annotation need to customize part of the base annotation's metadata.

## 6. Reading Operation Metadata with OperationCustomizer

**OperationCustomizer** lets you modify an Operation while springdoc builds the document. In springdoc-openapi 2.x, the interface resides in **org.springdoc.core.customizers** and receives both Operation and HandlerMethod.

~~~java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.util.StringUtils;
import org.springframework.web.method.HandlerMethod;
import io.swagger.v3.oas.models.Operation;

@Configuration
public class OpenApiCustomizationConfiguration {

    @Bean
    OperationCustomizer apiDomainCustomizer() {
        return (operation, handlerMethod) -> {
            ApiDomain metadata =
                AnnotatedElementUtils.findMergedAnnotation(
                    handlerMethod.getMethod(),
                    ApiDomain.class
                );

            if (metadata == null) {
                metadata =
                    AnnotatedElementUtils.findMergedAnnotation(
                        handlerMethod.getBeanType(),
                        ApiDomain.class
                    );
            }

            if (metadata == null) {
                return operation;
            }

            operation.addExtension(
                "x-business-domain",
                metadata.value()
            );

            if (metadata.internal()) {
                operation.addExtension("x-internal", true);
            }

            if (metadata.deprecated()) {
                operation.setDeprecated(true);
            }

            if (StringUtils.hasText(metadata.description())
                    && !StringUtils.hasText(operation.getDescription())) {
                operation.setDescription(metadata.description());
            }

            return operation;
        };
    }
}
~~~

The customizer performs these steps:

1. Receives the handler method being documented by springdoc.
2. Searches for ApiDomain on the method first.
3. If absent on the method, searches on the controller class.
4. If no metadata is found, leaves the operation unchanged.
5. If found, adds the x-business-domain vendor extension.
6. Marks the operation as internal or deprecated when requested by the annotation.
7. Sets description only if the operation has no description yet, avoiding overwriting an explicit @Operation description.

**HandlerMethod** identifies the method and bean type associated with the operation. It bridges customizers to application annotations rather than operating solely on already-created OpenAPI objects.

### Vendor Extensions x-*

OpenAPI allows adding extended metadata prefixed with **x-**. Example:

~~~yaml
paths:
  /api/catalog/books:
    get:
      operationId: listBooks
      x-business-domain: catalog
      x-internal: false
~~~

Vendor extensions can be consumed by custom tools such as API gateways, documentation generators, or validation pipelines. Only add values of valid JSON types such as string, number, boolean, array, or object. Never place secrets, tokens, or sensitive data into extensions because they are published along with the documentation.

Extensions do not replace standard tags, security requirements, or response metadata. If the information has a standard OpenAPI structure, use the standard property; reserve extensions for application-specific metadata.

## 7. Reading Parameter Annotations with ParameterCustomizer

When metadata resides on a method parameter, **ParameterCustomizer** receives OpenAPI's Parameter object and Spring's MethodParameter. From MethodParameter, the customizer accesses annotations on the Java parameter.

Declaring the annotation:

~~~java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE
})
public @interface ApiParameterDoc {

    String description();

    String example() default "";

    boolean deprecated() default false;

    boolean sensitive() default false;
}
~~~

Using it on a controller:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @ApiParameterDoc(
        description = "Keyword to search by book title",
        example = "Spring"
    )
    @RequestParam(name = "keyword")
    String keyword
) {
    // ...
    return List.of();
}
~~~

Customizer:

~~~java
import org.springdoc.core.customizers.ParameterCustomizer;
import org.springframework.core.MethodParameter;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.util.StringUtils;
import io.swagger.v3.oas.models.parameters.Parameter;

@Bean
ParameterCustomizer apiParameterCustomizer() {
    return (parameter, methodParameter) -> {
        ApiParameterDoc metadata =
            AnnotatedElementUtils.findMergedAnnotation(
                methodParameter.getParameter(),
                ApiParameterDoc.class
            );

        if (metadata == null) {
            return parameter;
        }

        parameter.setDescription(metadata.description());

        if (metadata.deprecated()) {
            parameter.setDeprecated(true);
        }

        if (metadata.sensitive()) {
            parameter.setExample(null);
        } else if (StringUtils.hasText(metadata.example())) {
            parameter.setExample(metadata.example());
        }

        return parameter;
    };
}
~~~

This example uses a custom annotation to standardize description, example, and deprecation. If the parameter is marked sensitive, the customizer omits any example from documentation. This is a documentation convention; the server must still protect and handle sensitive data through separate runtime mechanisms.

ParameterCustomizer applies only to OpenAPI Parameters generated by springdoc from method parameters. It does not handle request bodies, DTO properties, or arbitrary method annotations. For request bodies or schema properties, use extension points suited to those respective objects.

## 8. Distinguishing Customizers by Target Object

Choosing the right extension point avoids reading the wrong metadata or modifying the wrong level:

| Extension Point | Received Objects | Use When |
|---|---|---|
| **OperationCustomizer** | Operation and HandlerMethod | Reading controller/method annotations, adding operation metadata |
| **ParameterCustomizer** | Parameter and MethodParameter | Reading Java parameter annotations, modifying OpenAPI parameters |
| **OpenApiCustomizer** | Entire OpenAPI document | Modifying paths, tags, servers, or components at the document level |
| **GlobalOpenApiCustomizer** | Default document and groups globally | Applying document-level changes across multiple documents |
| **GroupedOpenApi customizer** | Document of the configured group | Applying rules only to one specific group |

OperationCustomizer is appropriate when HandlerMethod is needed to determine which annotation produced the operation. OpenApiCustomizer receives the built OpenAPI document; it does not directly have a HandlerMethod per operation. If you need to read custom annotations attached to methods, handle them in OperationCustomizer or maintain an explicit mapping mechanism.

In springdoc 2.x, customizers can be registered as Spring beans. If you only want to target one group, use the customizer API attached to the corresponding GroupedOpenApi. Scope across global beans and groups can vary by customizer type and version; inspect each group's documentation endpoint after configuration.

## 9. Reading Annotations on Interfaces and Inherited Methods

Some projects declare controller contracts on interfaces:

~~~java
@ApiDomain(value = "catalog", description = "Catalog API")
public interface CatalogOperations {

    @GetMapping("/api/catalog/books")
    List<BookResponse> listBooks();
}

@RestController
public class CatalogController implements CatalogOperations {

    @Override
    public List<BookResponse> listBooks() {
        // ...
        return List.of();
    }
}
~~~

If a customizer only calls findMergedAnnotation on the implementing method and bean class, metadata placed on the interface may not be found as expected. When allowing annotations on interfaces or superclasses, define an explicit search strategy.

Spring provides **MergedAnnotations.SearchStrategy.TYPE_HIERARCHY** to search across the type hierarchy:

~~~java
MergedAnnotation<ApiDomain> merged =
    MergedAnnotations.from(
        handlerMethod.getBeanType(),
        MergedAnnotations.SearchStrategy.TYPE_HIERARCHY
    ).get(ApiDomain.class);

ApiDomain metadata =
    merged.isPresent() ? merged.synthesize() : null;
~~~

For methods, you can use MergedAnnotations on the method with an appropriate hierarchy strategy for your Spring version. Write tests covering direct classes, direct methods, interfaces, and superclasses to confirm precedence order.

Do not use @Inherited as a substitute for these strategies. @Inherited does not automatically propagate method or interface annotations in all scenarios.

## 10. Defining Precedence Order When Multiple Annotations Exist

A controller may carry annotations on the class, on methods, and via composed annotations. Without defined precedence, metadata becomes unpredictable.

A simple policy:

1. Direct or composed annotations on the method have the highest priority.
2. If absent on the method, read the annotation from the controller class.
3. If absent on the class, optionally search interfaces/superclasses if the project enables hierarchy rules.
4. If not found, add no custom metadata.

You can extract metadata lookup into a helper to avoid duplicating logic:

~~~java
private ApiDomain resolveApiDomain(HandlerMethod handlerMethod) {
    ApiDomain methodMetadata =
        AnnotatedElementUtils.findMergedAnnotation(
            handlerMethod.getMethod(),
            ApiDomain.class
        );

    if (methodMetadata != null) {
        return methodMetadata;
    }

    return AnnotatedElementUtils.findMergedAnnotation(
        handlerMethod.getBeanType(),
        ApiDomain.class
    );
}
~~~

If interfaces or superclasses are permitted, extend the helper with MergedAnnotations and specify the exact order. Avoid automatically merging two annotations into one object without explicit per-attribute rules.

For example: a method-level domain may override the class domain, while an empty description on the method could be treated as “not provided” so it inherits the class description. If that behavior is desired, write per-attribute merging logic instead of picking the entire method annotation wholesale.

## 11. Separating Documentation Metadata from Runtime Behavior

Custom annotations read by OperationCustomizer or ParameterCustomizer modify only the OpenAPI document. They do not automatically:

- Register Spring MVC routes.
- Change how Spring binds query, path, header, or body data.
- Enable Bean Validation.
- Grant or deny access permissions.
- Alter response status codes and payloads.
- Hide endpoints from the runtime server.

For example, @ApiDomain(internal = true) above adds the x-internal extension to the documentation. It does not secure the endpoint. To block access, configure Spring Security or enforce authorization in the appropriate layer.

Similarly, ApiParameterDoc(sensitive = true) only prevents the customizer from adding an example per the written convention. It does not encrypt values, scrub logs, or protect requests.

If metadata must influence runtime behavior, build a separate runtime component that reads the annotation. Never assume documentation customizers run during HTTP request processing.

## 12. Verifying Customizers via OpenAPI JSON

After the application starts, fetch the document at **/v3/api-docs**. If an operation has the ApiDomain annotation, inspect the extension:

~~~json
{
  "paths": {
    "/api/catalog/books": {
      "get": {
        "x-business-domain": "catalog",
        "description": "Lookup and management operations for the catalog"
      }
    }
  }
}
~~~

If a parameter has ApiParameterDoc, verify name, description, example, and deprecated under the operation's parameters section.

You can use jq:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/catalog/search"].get'
~~~

To inspect parameters:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/catalog/search"].get.parameters'
~~~

If the application has multiple GroupedOpenApi instances, call each group's endpoint and confirm the customizer has the intended scope. An extension present in the default document yet absent in a group can indicate the customizer was registered in the wrong scope.

## 13. Writing Integration Tests for Annotations and Customizers

You can verify generated metadata using MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiDomainDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsBusinessDomainExtension() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/catalog/books'].get['x-business-domain']"
            ).value("catalog"));
    }

    @Test
    void appliesParameterMetadata() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/catalog/search'].get.parameters[0].description"
            ).value("Keyword to search by book title"));
    }
}
~~~

Tests should cover:

- Annotations directly on methods.
- Class-level annotations and fallback to methods.
- Composed annotations with @AliasFor.
- Annotations on parameters.
- Cases without annotations.
- Method-level overriding class-level.
- Group-specific documents if the customizer is scoped per group.

If interfaces or superclasses are used, add tests verifying hierarchy search. JSON tests catch metadata not being read or customizers overwriting existing OpenAPI details.

## 14. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Customizer cannot find annotation | Retention is not RUNTIME or target does not match | Check @Retention and @Target |
| getAnnotation returns null on composed annotations | Direct reflection does not resolve merged metadata | Use AnnotatedElementUtils or MergedAnnotations |
| Annotation on interface is not read | Only searching implementing method and class | Use intentional hierarchy search and write tests |
| Method metadata overridden by class metadata | Unclear precedence order or code always reads class first | Prioritize method-level first, then fall back to class-level |
| @AliasFor does not reflect attribute | Incompatible alias target or default value | Check base annotation, attribute, and composed annotation |
| ParameterCustomizer does not run for request body | Request body is not an OpenAPI Parameter Object | Use an extension point for operation/body/schema |
| @Operation description is lost | Customizer overwrites description unconditionally | Add only when empty or merge with explicit rules |
| Extension missing in a group | Customizer not applied to that group | Check global and group-specific registration |
| Using extensions to protect endpoints | Confused documentation metadata with authorization | Configure Spring Security or runtime authorization |
| Sensitive examples appear in docs | Customizer did not apply sensitive rule | Strip examples and use synthetic sample data |

## 15. Workflow for Implementing Custom Annotations

When bringing proprietary metadata into OpenAPI, follow this sequence:

1. **Identify metadata:** which information cannot be expressed by standard annotations and which tools will read it?
2. **Choose placement:** class, method, or parameter; avoid allowing broader targets than needed.
3. **Declare the annotation:** set RUNTIME retention, appropriate targets, and clear defaults.
4. **Define inheritance rules:** specify whether methods override classes and whether interfaces/superclasses are scanned.
5. **Select customizer:** OperationCustomizer for operations/HandlerMethod; ParameterCustomizer for parameters/MethodParameter.
6. **Translate to OpenAPI metadata:** use standard fields where appropriate, or x-* extensions for proprietary metadata.
7. **Preserve existing details:** do not overwrite summary, description, schema, or responses without explicit merge rules.
8. **Test:** inspect /v3/api-docs and each group; verify both annotated and unannotated cases yield right results.
9. **Check runtime boundaries:** ensure documentation metadata is never confused with routing, validation, or security.

## 16. Maintainable Design Principles

- Create custom annotations for meaningful conventions, not as wrappers around individual standard annotations that add no extra value.
- Use RUNTIME retention if metadata is read at runtime.
- Choose the narrowest @Target that satisfies requirements.
- Use Spring merged-annotation utilities when composed annotations or aliases are needed.
- Clearly define method-level, class-level, and hierarchy precedence.
- Use OperationCustomizer when HandlerMethod is needed; use ParameterCustomizer when MethodParameter is needed.
- Keep standard OpenAPI metadata in standard properties; use x-* only for proprietary details.
- Never put secrets or real sensitive data into extensions or examples.
- Never substitute documentation customizers for Spring Security, Bean Validation, or binding logic.
- Write integration tests to ensure metadata is generated accurately across the default document and relevant groups.

## Conclusion

Custom annotations allow applications to store proprietary metadata on controllers, methods, and parameters. To be readable at runtime, annotations need RUNTIME retention and appropriate targets. Spring merged-annotation utilities handle composed annotations and @AliasFor; OperationCustomizer reads metadata tied to HandlerMethod, while ParameterCustomizer reads MethodParameter metadata. Customizers translate that information into OpenAPI properties or x-* vendor extensions. Define clear precedence rules, preserve existing OpenAPI descriptions, and verify the JSON output. Documentation metadata modifies only the published contract; routing, binding, validation, and security behavior must still be implemented in the corresponding runtime layers.
