# Migrating Springfox Docket Configuration to GroupedOpenApi Where Appropriate

When migrating a Spring Boot application from Springfox to springdoc-openapi, you should not mechanically replace each line of Docket configuration with a line of GroupedOpenApi. A Springfox Docket bundles many responsibilities into a single object: selecting controllers and paths, naming the group, declaring API metadata, security, and shared parameters and responses. springdoc's GroupedOpenApi primarily describes a group of endpoints to expose as an OpenAPI document. Shared metadata, security schemes, and other customizations are configured via an OpenAPI bean, annotations, or dedicated customizers.

The official springdoc migration guide makes an important distinction: if the application has only one Docket, remove that bean and move package/path filters to properties; only when you have multiple Dockets generating separate documents should you replace them with GroupedOpenApi beans. API metadata such as title, description, version, and license moves to an OpenAPI bean.

This guide explains how to inventory your existing Dockets, choose the right replacement strategy, map selectors and Swagger 2 annotations to OpenAPI 3, migrate security and global configuration, and verify the new documentation before removing Springfox completely.

## 1. What does a Docket do?

A Docket typically contains these parts:

- DocumentationType: selects whether Springfox generates Swagger 2 or OpenAPI 3 format.
- select, apis, and paths: selects controllers, methods, and URLs included in the document.
- groupName: the document group name.
- apiInfo: title, description, version, contact, and license.
- securitySchemes and securityContexts: declares authentication mechanisms and protected operations.
- globalRequestParameters or globalOperationParameters: default parameters applied across many operations.
- globalResponses: default responses by HTTP method.
- ignoredParameterTypes, alternateTypeRules, and directModelSubstitute: adjusts how Springfox recognizes parameters and models.
- host, protocols, pathMapping, or PathProvider: adjusts the documented public URL.

Not all of the above belong to GroupedOpenApi. Before migrating, map out your current Docket configuration and identify the corresponding target in springdoc.

## 2. Distinguish between a single Docket and multiple Dockets

This is the first decision of the migration.

| Current Springfox configuration | Appropriate migration path |
| --- | --- |
| No Docket, using default configuration | Add springdoc starter; no GroupedOpenApi needed |
| Single Docket only filtering packages/paths | Remove Docket, use springdoc.packages-to-scan and springdoc.paths-to-match |
| Single Docket mainly setting apiInfo | Remove Docket, create an OpenAPI bean |
| Single Docket both filtering APIs and setting metadata | Use properties for filters and an OpenAPI bean for metadata |
| Multiple Dockets generating separate documents | Create one GroupedOpenApi per group |
| Multiple Dockets with different selectors but shared metadata | GroupedOpenApi for selectors; OpenAPI bean for shared metadata |
| Docket with complex security or global parameters | Split into OpenAPI security, annotations, and customizers |

For example, if an application only has a single Docket to exclude internal controllers from Swagger, creating a single GroupedOpenApi is usually unnecessary. springdoc properties are sufficient to scope the default document.

If an application has two Dockets such as public and admin, each producing an independent document with its own set of operations, GroupedOpenApi is the right choice.

## 3. Choose the springdoc version based on Spring Boot

Before editing code, identify your Spring Boot version and pick the matching springdoc major version. Do not use one springdoc version across all Boot lines.

| Spring Boot | Compatible springdoc line | Notes |
| --- | --- | --- |
| 4.1.x | 3.1.x to 3.2.x | Per the current compatibility matrix |
| 4.0.x | 3.0.x | Use springdoc 3.x |
| 3.5.x | 2.8.x to 2.10.x | Use springdoc v2 documentation |
| 3.4.x | 2.7.x to 2.8.x | Use springdoc v2 documentation |
| 3.3.x | 2.6.x | Use springdoc v2 documentation |
| 3.2.x | 2.3.x to 2.5.x | Use springdoc v2 documentation |
| 3.1.x | 2.2.x | Use springdoc v2 documentation |
| 3.0.x | 2.0.x to 2.1.x | Use springdoc v2 documentation |
| Spring Boot 2.x or 1.x | springdoc 1.8.0 is the final open-source line | This is the legacy line |

If upgrading Spring Boot 2 to Boot 3, you also need to handle the Java EE to Jakarta EE migration, such as javax.validation to jakarta.validation and javax.servlet to jakarta.servlet. Do not simply swap the springdoc dependency and expect all legacy libraries to be compatible automatically.

## 4. Replace Springfox dependencies

For a Spring MVC application needing both OpenAPI endpoints and Swagger UI, the common dependency is:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Version 3.2.0 in the example is for Spring Boot 4.1.x according to the current matrix. If your application uses Spring Boot 3.x, choose the corresponding 2.x version; do not copy this version verbatim into a Boot 3 project.

If you only need JSON/YAML documents without the Swagger UI interface, you can use the API starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

For Spring WebFlux, use the corresponding starter:

| Web stack | With Swagger UI | API document only |
| --- | --- | --- |
| Spring MVC | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-api |
| Spring WebFlux | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-api |

Remove used Springfox dependencies such as springfox-swagger2, springfox-swagger-ui, springfox-boot-starter, springfox-data-rest, and other springfox modules. Also remove legacy Swagger 2 annotation dependencies if declared separately. OpenAPI 3 annotations are provided through the springdoc starter.

Do not keep Springfox and springdoc together long-term to "run side-by-side" inside the same ApplicationContext. The two libraries may register overlapping handlers, converters, or UI resources, causing duplicate endpoints, divergent documents, or startup failures. If you need to compare during migration, use a separate branch or test profile, then remove Springfox after verification.

## 5. Remove Springfox activation annotations

Annotations such as @EnableSwagger2 or @EnableSwagger2WebMvc belong to Springfox. When switching to springdoc, delete them along with the Docket configuration.

springdoc is registered via the starter's Spring Boot auto-configuration. Usually there is no need to add @EnableOpenApi or any separate activation annotation.

After removing Springfox, verify:

- No remaining imports from springfox.documentation.*.
- No remaining Swagger 2 annotation imports from io.swagger.annotations.*.
- No remaining Docket beans.
- No remaining legacy Springfox Swagger UI configuration.
- No transitive dependency pulling swagger-models or swagger-annotations 1.x onto the runtime classpath.

## 6. Map Docket configuration to springdoc

The table below is a map of responsibilities, not a one-to-one replacement table:

| Springfox Docket | springdoc equivalent | Notes |
| --- | --- | --- |
| Docket.groupName | GroupedOpenApi.builder().group(...) | Used when grouped documents are needed |
| RequestHandlerSelectors.basePackage | packagesToScan or springdoc.packages-to-scan | Filter by package |
| PathSelectors.any/regex | pathsToMatch and paths-to-exclude | Re-verify pattern semantics |
| RequestHandlerSelectors.withMethodAnnotation | addOpenApiMethodFilter | Filter by method annotation |
| Docket.apiInfo | OpenAPI bean with Info | Document-wide metadata |
| Docket.securitySchemes | Components.securitySchemes or @SecurityScheme | Declare schemes |
| Docket.securityContexts | SecurityRequirement, annotations, or customizer | Decide which operations require security |
| globalRequestParameters | Parameter/OperationCustomizer/GlobalOperationCustomizer | No single direct replacement |
| globalResponses | @ApiResponse, @ApiResponses, OpenApiCustomizer, or GlobalOpenApiCustomizer | Choose customizer by target document scope |
| ignoredParameterTypes | @Parameter(hidden = true), @Hidden, or customizer | Hide parameters/controllers from docs |
| alternateTypeRules/directModelSubstitute | Explicit DTO, @Schema, ModelConverter, or SpringDocUtils | Review each model rule individually |
| host, protocols, servers | OpenAPI.servers and reverse proxy configuration | Verify public URLs |
| useDefaultResponseMessages | Response annotations/customizers and ControllerAdvice | Do not copy default responses blindly |

Key point: GroupedOpenApi decides which endpoints belong to which document. It does not replace the OpenAPI bean, security schemes, or model converters.

## 7. Migrate a single Docket to properties

Example legacy Springfox configuration:

~~~java
@Bean
Docket applicationApi() {
    return new Docket(DocumentationType.SWAGGER_2)
        .select()
        .apis(RequestHandlerSelectors.basePackage("com.example.api"))
        .paths(PathSelectors.regex("/api/.*"))
        .build()
        .apiInfo(apiInfo());
}
~~~

If this is the only Docket, remove the bean and configure springdoc:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
~~~

There is no need to create a GroupedOpenApi just to get a default document. springdoc automatically generates the document from controllers matching the package/path filters.

If the old Docket used RequestHandlerSelectors.any() and PathSelectors.any(), you may not need to configure packages-to-scan or paths-to-match at all. By default, springdoc scans eligible APIs in the application.

## 8. Migrate multiple Dockets to GroupedOpenApi

Suppose Springfox has two Dockets:

~~~java
@Bean
Docket publicApi() {
    return new Docket(DocumentationType.SWAGGER_2)
        .select()
        .apis(RequestHandlerSelectors.basePackage(
            "com.example.api.publicapi"))
        .paths(PathSelectors.regex("/public.*"))
        .build()
        .groupName("public")
        .apiInfo(apiInfo());
}

@Bean
Docket adminApi() {
    return new Docket(DocumentationType.SWAGGER_2)
        .select()
        .apis(RequestHandlerSelectors.basePackage(
            "com.example.api.admin"))
        .paths(PathSelectors.regex("/admin.*"))
        .build()
        .groupName("admin")
        .apiInfo(apiInfo());
}
~~~

Migrate to:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .packagesToScan("com.example.api.publicapi")
            .pathsToMatch("/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .packagesToScan("com.example.api.admin")
            .pathsToMatch("/admin/**")
            .build();
    }
}
~~~

The two groups create two separate OpenAPI documents. Under default configuration, their JSON URLs are:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
~~~

Swagger UI can list these groups in the UI configuration. Group names must be unique. Avoid duplicate names or arbitrary renames because portals, export scripts, and client generators may depend on the group URLs.

## 9. Migrate method-annotation selectors

Springfox allows selecting methods via RequestHandlerSelectors.withMethodAnnotation(Admin.class). springdoc supports filtering methods in GroupedOpenApi using addOpenApiMethodFilter.

Declare the annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Admin {
}
~~~

Declare the group:

~~~java
@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/**")
        .addOpenApiMethodFilter(
            method -> method.isAnnotationPresent(Admin.class))
        .build();
}
~~~

The method filter is applied in addition to package/path conditions if those are declared. If you only want to filter by annotation, you can omit pathsToMatch or use an appropriate path scope. Inspect the generated document to confirm the final set of operations matches expectations.

## 10. Migrate a Docket with multiple selectors

A Docket may combine a package selector and a path selector. Example:

~~~java
.apis(RequestHandlerSelectors.basePackage("com.example.api"))
.paths(PathSelectors.regex("/v1/.*"))
~~~

In springdoc:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /v1/**
~~~

Both package and path conditions narrow down the endpoint set together. If the old Docket had annotation selectors, method filters, or custom selectors, add the corresponding criteria with addOpenApiMethodFilter or a customizer.

Do not copy raw regex strings from PathSelectors.regex into paths-to-match. Springfox regexes and the path patterns used by springdoc do not necessarily share the same semantics. For instance, the regex /public.* is often converted to the pattern /public/** after checking the actual URLs, though the final pattern must reflect the application's path structure.

After migrating, build a list of expected endpoints and compare it against the OpenAPI document. An application returning HTTP 200 on /v3/api-docs does not prove the filters selected the right endpoints.

## 11. Migrate apiInfo to an OpenAPI bean

Docket.apiInfo typically holds global metadata. In springdoc, declare an OpenAPI bean:

~~~java
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class OpenApiMetadataConfiguration {

    @Bean
    OpenAPI applicationOpenAPI(Environment environment) {
        String publicApiUrl =
            environment.getRequiredProperty("app.public-api-url");

        return new OpenAPI()
            .info(new Info()
                .title("Spring Shop API")
                .description("Store management API")
                .version("1.0.0")
                .license(new License()
                    .name("Apache 2.0")
                    .url("https://www.apache.org/licenses/LICENSE-2.0")))
            .externalDocs(new ExternalDocumentation()
                .description("Technical documentation")
                .url("https://docs.example.com/api"))
            .components(new Components()
                .addSecuritySchemes(
                    "bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")))
            .addServersItem(new Server()
                .url(publicApiUrl)
                .description("Public API gateway"));
    }
}
~~~

The OpenAPI bean serves as shared metadata across groups. If a group needs its own description or external documentation, use an OpenApiCustomizer attached directly to the corresponding GroupedOpenApi.

Example:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import io.swagger.v3.oas.models.info.Info;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/partner/**")
        .addOpenApiCustomizer(openApi ->
            openApi.info(new Info()
                .title("Partner API")
                .version("1.0.0")
                .description("API for partners")))
        .build();
}
~~~

Only customize group-specific information here. Do not duplicate all global metadata in every group if it should stay uniform.

Configure environment-specific public URLs, for example in application.yml:

~~~yaml
app:
  public-api-url: https://api.example.com
~~~

## 12. Migrate Swagger 2 annotations to OpenAPI 3

springdoc uses annotations from the io.swagger.v3.oas.annotations package. Common changes:

| Springfox / Swagger 2 | springdoc / OpenAPI 3 |
| --- | --- |
| @Api | @Tag |
| @ApiIgnore | @Parameter(hidden = true), @Operation(hidden = true), or @Hidden |
| @ApiImplicitParam | @Parameter |
| @ApiImplicitParams | @Parameters |
| @ApiModel | @Schema |
| @ApiModelProperty | @Schema |
| @ApiModelProperty(allowEmptyValue = true) | @Schema(nullable = true) |
| @ApiOperation(value = "...", notes = "...") | @Operation(summary = "...", description = "...") |
| @ApiParam | @Parameter |
| @ApiResponse(code = 404, message = "...") | @ApiResponse(responseCode = "404", description = "...") |

Annotations with the same name such as ApiResponse can come from two different packages. After migration, verify imports. OpenAPI 3 annotations must use the io.swagger.v3.oas.annotations.responses package, not io.swagger.annotations.

Controller example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Orders", description = "Order management")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{orderId}")
    @Operation(
        operationId = "getOrderById",
        summary = "Get order by ID",
        description = "Returns information for a single order."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Order found"
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Order not found"
        )
    })
    OrderResponse getOrder(
        @Parameter(description = "Order ID", example = "ORD-10001")
        @PathVariable String orderId) {
        return orderService.findById(orderId);
    }
}
~~~

When replacing annotations, preserve operationId if client SDKs or contract tests rely on operation names. Re-check summary, description, response codes, and examples because Swagger 2 and OpenAPI 3 have different structures.

## 13. Migrate model and field annotations

Springfox typically uses @ApiModel and @ApiModelProperty. In springdoc, use @Schema:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderResponse", description = "Order details")
public record OrderResponse(
    @Schema(
        description = "Order ID",
        example = "ORD-10001"
    )
    String orderId,

    @Schema(
        description = "Order status",
        allowableValues = {"PENDING", "CONFIRMED", "SHIPPED", "CANCELLED"}
    )
    String status,

    @Schema(
        description = "Optional note that may have no value",
        nullable = true
    )
    String note
) {
}
~~~

Do not just rename annotations while ignoring semantics. Check:

- Whether required and nullable are still accurate.
- Whether allowEmptyValue genuinely corresponds to nullable in that case.
- Whether allowableValues still reflects the business value set.
- Whether example has the right type and format.
- Whether accessMode or readOnly/writeOnly needs adjustment.
- Whether Jackson @JsonProperty, @JsonIgnore, and @JsonView cause the schema to differ from the Java DTO.

If a method accepts an object containing multiple query parameters, springdoc provides @ParameterObject to document the object's fields as individual parameters. For example, with Pageable or query DTOs, apply this annotation when needed and check the actual URL parameters in the generated document.

## 14. Migrate securitySchemes and securityContexts

Springfox usually separates scheme declarations and applicability conditions via securitySchemes() and securityContexts(). In OpenAPI 3, these two concepts correspond to:

1. Security schemes in components.securitySchemes.
2. Security requirements attached to the whole document, a controller, or an operation.

Bearer JWT example:

~~~java
// Add to the OpenAPI bean declared in the metadata section:
.components(new Components()
    .addSecuritySchemes(
        "bearerAuth",
        new SecurityScheme()
            .type(SecurityScheme.Type.HTTP)
            .scheme("bearer")
            .bearerFormat("JWT")));
~~~

This is part of the same global OpenAPI bean—do not create a second OpenAPI bean. A typical application should have a single OpenAPI configuration combining metadata, security schemes, and server URLs; multiple independent OpenAPI beans can cause ambiguity when springdoc selects the base document.

Attach the requirement to controllers or operations that require protection:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Admin")
@SecurityRequirement(name = "bearerAuth")
class AdminController {
    // Operations in this controller require bearerAuth.
}
~~~

If only some methods require authentication, place @SecurityRequirement on the method rather than the whole class. You can declare global security on the OpenAPI bean if all operations require the same scheme, but proactively mark public endpoints so they are not documented inaccurately.

Springfox SecurityContexts can filter by path regex and HTTP method. Do not replace them with a single global security requirement if the API has public, login, health, or callback endpoints that do not require a bearer token. Inspect the security array of each operation in the OpenAPI JSON.

## 15. Migrate global request parameters

Docket.globalRequestParameters() is commonly used to add shared headers such as X-Request-Id, X-Tenant-Id, or locale. There are two common approaches:

- If a parameter applies to only a few endpoints, declare @Parameter on the controller/method.
- If a parameter genuinely applies to every operation, use GlobalOperationCustomizer or the appropriate customizer mechanism.

Example customizer adding a shared header while avoiding duplicate parameters:

~~~java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.GlobalOperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CommonParameterConfiguration {

    @Bean
    GlobalOperationCustomizer requestIdHeader() {
        return (operation, handlerMethod) -> {
            boolean alreadyDeclared = operation.getParameters() != null
                && operation.getParameters().stream()
                    .anyMatch(p -> "X-Request-Id".equals(p.getName())
                        && "header".equals(p.getIn()));

            if (!alreadyDeclared) {
                operation.addParametersItem(new Parameter()
                    .name("X-Request-Id")
                    .in("header")
                    .description("Request correlation ID")
                    .required(false)
                    .schema(new StringSchema()));
            }
            return operation;
        };
    }
}
~~~

GlobalOperationCustomizer is used when changes must apply to operations in the default document and all groups. If only one group needs the parameter, use an OperationCustomizer attached to that GroupedOpenApi. Check whether parameters get duplicated when a controller also declares the same header.

Do not mark a header as required if the application does not actually enforce it. OpenAPI is a contract with consumers; misrepresenting an optional header as required can make client generators produce inappropriate code or validation.

## 16. Migrate global responses

Springfox offers globalResponses() or globalResponseMessage() to add shared responses by HTTP method. In OpenAPI, responses should be documented closely matching each operation's actual behavior:

- Use @ApiResponse/@ApiResponses for operation-specific responses.
- Use @ControllerAdvice to standardize errors and document common error responses.
- Use OpenApiCustomizer for the default document; use GlobalOpenApiCustomizer if the change must appear in the default document and every group.
- Use GroupedOpenApi.addOpenApiCustomizer(...) if the response belongs to a single specific group.
- Check the springdoc.override-with-generic-response property if you want springdoc to add responses from ControllerAdvice to operations.

Example:

~~~java
@Operation(summary = "Create order")
@ApiResponses({
    @ApiResponse(responseCode = "201", description = "Order created"),
    @ApiResponse(responseCode = "400", description = "Invalid request"),
    @ApiResponse(responseCode = "409", description = "Insufficient inventory")
})
~~~

Do not add every error response to every operation just because the old Docket had a global list. A read endpoint might not return 409; an order-creation endpoint may have specific business errors. Documentation should reflect responses that can actually occur.

## 17. Migrate ignoredParameterTypes and hidden APIs

Springfox has ignoredParameterTypes() to exclude parameter types from documentation. In springdoc, hide the specific parameter or operation:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/profile")
ProfileResponse profile(
    @Parameter(hidden = true)
    @AuthenticationPrincipal UserPrincipal principal) {
    return profileService.get(principal);
}
~~~

If you need to hide an entire controller or method, you can use @Hidden or hidden = true on @Operation. Only hide technical parameters such as principal, servlet requests, or context objects; never hide business parameters that clients must pass.

## 18. Migrate alternateTypeRules and model substitution

Rules such as alternateTypeRules(), directModelSubstitute(), and genericModelSubstitutes() swap internal types for other types in the Swagger model. They have no simple one-step replacement in GroupedOpenApi.

Preferred order:

1. Create explicit request/response DTOs dedicated to the API.
2. Use @Schema(implementation = ...) when an operation needs to represent a specific type.
3. Use ModelConverter or schema customization mechanisms when model conversion rules must change globally.
4. Use SpringDocUtils for library-supported type substitutions, checking the package for your version.

Do not replace a complex type rule with an OpenApiCustomizer that only renames the schema. A customizer modifies the document after schemas are generated; it does not necessarily change how Jackson serializes actual data.

Specifically check Pageable, Page, Sort, generic wrappers, interface/abstract types, and polymorphic DTOs. springdoc includes model converters for several common types; do not retain old custom rules if the new starter already supports them accurately.

## 19. Migrate host, protocols, and pathMapping

If the old Docket set host, scheme, or base path, determine the URL clients actually use. In OpenAPI 3, base URLs are described via servers:

~~~java
// Add to the OpenAPI bean declared in the metadata section:
.addServersItem(new Server()
    .url(publicApiUrl)
    .description("Public API gateway"))
~~~

The server URL can be loaded from environment-specific configuration rather than hard-coded. Add servers to the existing OpenAPI bean; do not declare a second OpenAPI bean solely to set the URL.

If the application runs behind a reverse proxy, configure forwarded headers and proxy prefixes according to how the proxy preserves or strips prefixes. Do not hard-code internal hostnames like service-name:8080 into a public OpenAPI document.

Do not prepend the context path to both servers.url and operation paths if operation paths already include that prefix. After migration, verify the server URL and Try it out in Swagger UI in a staging environment.

## 20. Configure path/package filters and endpoint groups

Key properties:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  packages-to-exclude:
    - com.example.api.internal
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /internal/**
~~~

These properties apply to the default document. For each GroupedOpenApi, you can configure packagesToScan, packagesToExclude, pathsToMatch, and pathsToExclude on the builder.

If a group has its own selectors, configure them directly inside GroupedOpenApi to avoid inadvertently altering the default document or other groups. Then check the URLs:

| Document | Default URL |
| --- | --- |
| Default document | /v3/api-docs |
| Group public | /v3/api-docs/public |
| Group admin | /v3/api-docs/admin |

If you changed springdoc.api-docs.path, the actual URLs of all documents change according to the new base path.

## 21. Springfox compatibility issues with Spring Boot 2.6 and later

Spring Boot 2.6 switched Spring MVC's default path matching from AntPathMatcher to PathPatternParser. Release notes warned that this configuration can cause issues with some Springfox applications, especially alongside Actuator; Boot 2.6 also changed how Actuator matches paths.

Some legacy projects used:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

to temporarily revert to the old matcher for Spring MVC. This is not a long-term migration solution and does not fix all Actuator-related issues, because Actuator's path matching is not controlled by this property. When migrating to springdoc, re-evaluate this property and keep it only if the application has a specific remaining need for AntPathMatcher.

If upgrading from Boot 2.x to Boot 3.x, also address the Jakarta namespace and compatible dependencies. springdoc v2 targets Boot 3; springdoc v3 targets Boot 4. Do not mix legacy javax annotations or servlet APIs into a new Jakarta runtime.

## 22. Step-by-step migration workflow

1. Record all Docket beans, selectors, groupNames, apiInfo, security, parameters, responses, and model rules.
2. Count the Dockets and determine how many OpenAPI documents actually need to be maintained.
3. Choose the springdoc version matching your Spring Boot version.
4. Add the appropriate MVC or WebFlux starter; decide whether Swagger UI is needed or only API endpoints.
5. Remove Springfox dependencies and legacy activation annotations.
6. If there is only one Docket, move package/path filters to properties and apiInfo to an OpenAPI bean.
7. If there are multiple Dockets, create a GroupedOpenApi per document.
8. Convert Swagger 2 annotations to OpenAPI 3 annotations.
9. Migrate security schemes, operation requirements, global parameters, and responses according to their individual responsibilities.
10. Handle model substitutions, path/server URLs, and proxies.
11. Start the application and call the default document and each group.
12. Compare operations, schemas, security, responses, and examples against the prior contract.
13. Verify Swagger UI, OAuth2/bearer auth, Try it out, and static resources.
14. Remove Springfox workarounds that are no longer needed, such as the old path matching strategy if present.
15. Completely remove any remaining Springfox dependencies and re-run tests/build.

Do not remove Springfox before capturing the prior contract. Without a snapshot or list of expected operations, migration comparison relies on manual inspection and can easily miss endpoints.

## 23. Verify the document after migration

Fetch the OpenAPI JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json
~~~

Verify the JSON contains operations:

~~~bash
jq -e '.openapi and (.paths | length > 0)' openapi.json
~~~

For each group:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs/public \
  --output openapi-public.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs/admin \
  --output openapi-admin.json
~~~

Minimum checks:

- Every required path and HTTP method is present.
- No internal endpoints are exposed.
- operationIds are unique and stable.
- Request/response schemas preserve fields, types, required flags, nullability, and enums.
- Response statuses and media types are not lost.
- Security schemes and security requirements are accurate per operation.
- public/admin groups do not accidentally contain each other's endpoints.
- Server URLs do not point to internal hosts.
- Swagger UI loads the document properly and Try it out calls the right URL.

Valid OpenAPI JSON does not guarantee correct runtime API behavior. Add MockMvc or WebTestClient contract tests for key requests/responses and security tests for protected endpoints.

## 24. Common errors when migrating Dockets

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Only one default document despite having multiple Dockets before | Only added properties without creating GroupedOpenApi for separate groups | Create a bean for each group to retain |
| Empty group document | packagesToScan or pathsToMatch is too restrictive | Check actual packages/paths and method filters |
| Group contains extra endpoints | New selector is not equivalent to the Springfox selector | Compare operation lists and adjust filters |
| Metadata title/version disappeared | Created GroupedOpenApi but forgot the OpenAPI bean | Move apiInfo to an OpenAPI bean |
| Group missing security scheme | Added requirement without declaring scheme or wrong customizer scope | Declare components.securitySchemes and check group |
| Header appears twice | Annotation and global customizer both add the parameter | Check before adding the parameter |
| Swagger UI reports failure to load definition | Wrong API docs path, blocked by security, or wrong proxy rewrite | Check /v3/api-docs and swagger-config |
| DTO has wrong schema | Renamed annotations only, missing Jackson or model converters | Compare actual JSON with schema and use explicit DTOs |
| Error responses appear on every operation | Migrated globalResponses too broadly | Use annotations/customizers with the right scope |
| Spring Boot fails to start | Remaining Springfox dependency or path matching/Actuator conflict | Remove old dependencies and check Boot configuration |
| Swagger 2 client generator cannot read new document | Consumer still assumes Swagger 2 structure | Upgrade generator and check OpenAPI 3 compatibility |

## 25. Migration completion checklist

- [ ] Inventoried the number of Dockets and the purpose of each bean.
- [ ] Decided between a single default document or multiple groups.
- [ ] Spring Boot and springdoc versions match the compatibility matrix.
- [ ] Added the correct MVC/WebFlux starter.
- [ ] Removed Springfox and legacy Swagger 2 dependencies.
- [ ] Removed @EnableSwagger2 and Docket beans.
- [ ] Single Docket replaced with properties where appropriate.
- [ ] Multiple Dockets replaced with GroupedOpenApi per group.
- [ ] apiInfo migrated to an OpenAPI bean.
- [ ] Swagger 2 annotations migrated to OpenAPI 3.
- [ ] Security schemes and security requirements applied to the right operations.
- [ ] Global parameters/responses migrated with appropriate scope.
- [ ] Model substitutions evaluated case by case.
- [ ] Server URLs, context path, and reverse proxy verified.
- [ ] Default document JSON and each group JSON verified.
- [ ] Swagger UI, authentication, and Try it out verified working.
- [ ] No internal endpoints exposed unintentionally.
- [ ] Critical contract tests and security tests passed.

A good migration preserves the contracts consumers depend on while removing Springfox configuration that no longer fits modern Spring Boot platforms. Use GroupedOpenApi when you genuinely need multiple documents; let metadata, security, parameters, and schemas be managed by their corresponding OpenAPI components. This separation makes configuration easier to understand and avoids turning an old Docket into an overloaded GroupedOpenApi bean.

## References

- [springdoc-openapi – Migrating from SpringFox](https://springdoc.org/migrating-from-springfox.html)
- [springdoc-openapi – Core Properties Reference](https://springdoc.org/core-properties.html)
- [springdoc-openapi – FAQ: Multiple OpenAPI definitions and GroupedOpenApi](https://springdoc.org/faq.html)
- [springdoc-openapi – Migrating from springdoc v1 to v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Spring Boot 2.6 – Release Notes: PathPattern based path matching](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.6-Release-Notes)
- [Springfox – Docket Javadoc](https://springfox.github.io/springfox/javadoc/current/springfox/documentation/spring/web/plugins/Docket.html)
- [Springfox – Releases](https://github.com/springfox/springfox/releases)
