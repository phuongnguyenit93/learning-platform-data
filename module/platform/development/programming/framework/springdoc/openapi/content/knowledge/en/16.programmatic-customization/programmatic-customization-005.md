# `OperationCustomizer` and `HandlerMethod` Metadata

Springdoc automatically generates OpenAPI metadata from Spring MVC controllers, but sometimes a development team needs to apply shared rules based on the specific method handling a request. For example, operations for partners might need the `x-audience: partner` extension; legacy endpoints might need to be marked deprecated according to an internal annotation; or a required convention-based header might need to be added to the documentation.

`OperationCustomizer` provides an extension point for each individual operation. Its callback receives the `Operation` object that Springdoc is building along with the corresponding Spring MVC `HandlerMethod`. With `HandlerMethod`, the customizer can inspect the controller class, Java method, parameters, return type, and annotations to contextually adjust operation metadata.

## 1. How Does `OperationCustomizer` Work?

`OperationCustomizer` belongs to the `org.springdoc.core.customizers` package. It is a functional interface with the method:

```java
Operation customize(Operation operation, HandlerMethod handlerMethod);
```

The two parameters serve distinct roles:

- `operation` is the OpenAPI model of the operation being built. It contains summary, description, operationId, tags, parameters, request body, responses, security, and extensions.
- `handlerMethod` is Spring MVC handler metadata. It indicates which controller and Java method Spring uses to handle that endpoint.

The customizer can modify the operation and return the modified object. Springdoc uses the result in the generated OpenAPI document.

Example processing flow:

```text
Spring MVC HandlerMethod
          |
          v
Springdoc reads mappings and annotations
          |
          v
Creates OpenAPI Operation
          |
          v
OperationCustomizer.customize(operation, handlerMethod)
          |
          v
Customized Operation
          |
          v
OpenAPI JSON/YAML and Swagger UI
```

This callback runs while Springdoc is building the documentation, not on every client request to the endpoint. It does not invoke controller business logic and does not alter how Spring routes requests.

## 2. What Information Does `HandlerMethod` Provide?

`HandlerMethod` belongs to Spring Framework in the `org.springframework.web.method` package. It bridges an OpenAPI operation and the Java method discovered by Spring MVC.

| API | Information Returned | Use Case |
| --- | --- | --- |
| `getBeanType()` | Class containing the handler method | Reading controller-level annotations, identifying API domain |
| `getMethod()` | Java reflection `Method` | Reading method name, return type, and annotations on the method |
| `getMethodAnnotation(...)` | Annotation directly on the method | Reading custom metadata attached to the endpoint |
| `hasMethodAnnotation(...)` | Checks whether the method has an annotation | Toggling customization rules |
| `getMethodParameters()` | Array of `MethodParameter` | Analyzing method parameters and parameter annotations |
| `getReturnType()` | `MethodParameter` describing return type | Determining response-related metadata |

If you need to process annotations composed from meta-annotations or inherited annotations, use Spring's `AnnotatedElementUtils` utility instead of calling reflection directly. This is useful when a project creates composed annotations to standardize metadata across multiple controllers.

Do not rely on method names to dictate the API contract if explicit annotations can be used. Java method names can change during refactoring and are not necessarily the operation names clients see.

## 3. Creating an Internal Annotation to Mark Audience

Suppose an API is used by multiple client groups: public applications, partners, and internal systems. You can create an `@ApiAudience` annotation to mark the API consumer group.

```java
package com.example.api.docs;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface ApiAudience {
    String value();
}
```

`RetentionPolicy.RUNTIME` enables the customizer to read the annotation via reflection when Springdoc generates documentation. `TYPE` allows setting a default on the controller class; `METHOD` allows overriding it on a specific endpoint.

Example controller:

```java
package com.example.orders;

import com.example.api.docs.ApiAudience;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@ApiAudience("partner")
public class OrderController {

    @GetMapping
    public String listOrders() {
        return "orders";
    }

    @GetMapping("/summary")
    @ApiAudience("internal")
    public String internalSummary() {
        return "summary";
    }
}
```

The `listOrders` method inherits the `partner` audience from the class. The `internalSummary` method has its own annotation, so it is treated as `internal`. This is team-defined documentation metadata; it does not enforce endpoint access authorization.

## 4. Reading Annotations from `HandlerMethod` and Adding OpenAPI Extensions

OpenAPI supports specification extensions prefixed with `x-`. You can use `x-audience` to publish the audience for internal tools or documentation portals.

```java
package com.example.api.docs;

import io.swagger.v3.oas.models.Operation;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.method.HandlerMethod;

public class AudienceOperationCustomizer implements OperationCustomizer {

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        ApiAudience audience = AnnotatedElementUtils.findMergedAnnotation(
            handlerMethod.getMethod(), ApiAudience.class
        );

        if (audience == null) {
            audience = AnnotatedElementUtils.findMergedAnnotation(
                handlerMethod.getBeanType(), ApiAudience.class
            );
        }

        if (audience != null) {
            Map<String, Object> extensions = operation.getExtensions();
            if (extensions == null) {
                extensions = new LinkedHashMap<>();
                operation.setExtensions(extensions);
            }
            extensions.put("x-audience", audience.value());
        }

        return operation;
    }
}
```

The customizer looks for the annotation on the method first, then falls back to the class. That way, method-level metadata takes precedence over controller-level defaults. `getExtensions()` can return `null` if the operation has no extensions yet; therefore, the example initializes the map before adding entries.

The resulting OpenAPI output may contain:

```yaml
paths:
  /api/orders:
    get:
      x-audience: partner
  /api/orders/summary:
    get:
      x-audience: internal
```

Extensions are custom metadata. Generic OpenAPI tools do not necessarily understand the meaning of `x-audience`; a documentation portal or custom pipeline can read it to categorize, filter, or validate contracts.

## 5. Registering Customizers with `GroupedOpenApi`

To control scope clearly, attach the customizer to a group using `addOperationCustomizer`. The example below uses Spring Boot 3 and Springdoc 2.x:

```java
package com.example.api.docs;

import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/**")
            .addOperationCustomizer(new AudienceOperationCustomizer())
            .addOperationCustomizer(new LegacyOperationCustomizer())
            .build();
    }
}
```

The group document can be accessed at `/v3/api-docs/partner`. Because the customizer is attached to this group, the rules apply to operations belonging to that group's document.

If multiple groups need the same rule, register the customizer on each relevant group or use the global customizer mechanism supported by your project's Springdoc version. Do not assume a customizer attached to one group automatically applies to every document.

In Springdoc 1.x, the package of `GroupedOpenApi` differs from 2.x. Check your dependency version before copying imports; do not mix configuration APIs across the two generations.

## 6. Customizing Summary, Description, Tags, and Deprecated Status

Customizers can modify operation fields. For example, if controllers use an internal annotation to mark legacy endpoints, a customizer can mark those operations as deprecated:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface LegacyEndpoint {}
```

```java
public class LegacyOperationCustomizer implements OperationCustomizer {

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        if (AnnotatedElementUtils.findMergedAnnotation(
                handlerMethod.getMethod(), LegacyEndpoint.class) != null) {
            operation.setDeprecated(true);
        }
        return operation;
    }
}
```

An endpoint can be marked as:

```java
@GetMapping("/api/orders/legacy-report")
@LegacyEndpoint
public void legacyReport() {
    // Legacy endpoint remains operational during the transition period.
}
```

`deprecated: true` in OpenAPI informs consumers that the operation should not be used for new integrations. It does not disable the endpoint, return `410`, or remove the route. Decommissioning must be carried out through a separate migration plan and runtime changes.

You can use `operation.setSummary(...)`, `setDescription(...)`, `setDeprecated(...)`, or `addTagsItem(...)` to adjust an operation. Only overwrite summary/description when you have an intentional metadata source; avoid erasing details already inferred from `@Operation` or Springdoc.

## 7. Adding Header Parameters Based on Method Annotations

Another case is an endpoint with a header mapping condition where the header parameter is not yet clearly shown in the documentation. You can create an annotation marking endpoints that require a tenant header, then add the parameter to the OpenAPI operation.

Annotation:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface RequiresTenantHeader {}
```

Controller:

```java
@GetMapping(path = "/api/tenant/orders", headers = "X-Tenant-Id")
@RequiresTenantHeader
public void listTenantOrders() {
    // Retrieve tenant from the validated request context.
}
```

Customizer:

```java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.method.HandlerMethod;

public class TenantHeaderOperationCustomizer implements OperationCustomizer {

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        boolean required = AnnotatedElementUtils.findMergedAnnotation(
            handlerMethod.getMethod(), RequiresTenantHeader.class
        ) != null;

        if (required && !hasTenantHeader(operation)) {
            operation.addParametersItem(
                new Parameter()
                    .name("X-Tenant-Id")
                    .in("header")
                    .required(true)
                    .description("Tenant identifier assigned to the client")
                    .schema(new StringSchema())
            );
        }

        return operation;
    }

    private boolean hasTenantHeader(Operation operation) {
        if (operation.getParameters() == null) {
            return false;
        }

        return operation.getParameters().stream().anyMatch(parameter ->
            "header".equalsIgnoreCase(parameter.getIn())
                && "X-Tenant-Id".equalsIgnoreCase(parameter.getName())
        );
    }
}
```

Register this customizer on the group containing tenant endpoints:

```java
@Bean
GroupedOpenApi tenantApi() {
    return GroupedOpenApi.builder()
        .group("tenant")
        .pathsToMatch("/api/tenant/**")
        .addOperationCustomizer(new TenantHeaderOperationCustomizer())
        .build();
}
```

The example checks existing parameters before adding to avoid creating two headers with the same name. If the controller already declares `@RequestHeader("X-Tenant-Id")`, Springdoc usually creates the parameter automatically; the customizer can update that parameter rather than adding a duplicate.

In a real application, ensure runtime actually checks the tenant header and verifies tenant access permissions. The `@RequiresTenantHeader` annotation in the example is only custom metadata; it does not create filters, validate tenants, or protect data.

## 8. How Does `OperationCustomizer` Differ from `OpenApiCustomizer`?

These two extension points operate at different scopes:

| Extension Point | Received Object | Appropriate Scope |
| --- | --- | --- |
| `OperationCustomizer` | One `Operation` and its corresponding `HandlerMethod` | Rules depending on a specific controller/method |
| `OpenApiCustomizer` | Entire `OpenAPI` model | Document-level metadata such as servers, tags, info, or components |

For example, adding `x-audience` from a method annotation is well suited for `OperationCustomizer`. Adding environment-specific server URLs or license metadata for the entire document fits `OpenApiCustomizer` better.

Do not use `OperationCustomizer` to modify global structures like `components.schemas` when an OpenAPI-level customizer can be used. Conversely, using `OpenApiCustomizer` to locate and edit operations via reflection is more complex because it does not directly receive the corresponding `HandlerMethod`.

## 9. Reading Annotations on Methods, Classes, and Parameters

`HandlerMethod` allows reading metadata at multiple levels. Define a clear precedence order:

1. Method-level annotations usually represent overrides or exceptions for a specific endpoint.
2. Class-level annotations usually provide defaults for all operations in the controller.
3. Parameter-level annotations can describe headers, query parameters, or parameter-specific rules.

Example reading parameters:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface ParameterMetadata {
    String value();
}
```

After defining the parameter annotation, the customizer can read it:

```java
import org.springframework.core.MethodParameter;
import org.springframework.core.annotation.AnnotatedElementUtils;

for (MethodParameter methodParameter : handlerMethod.getMethodParameters()) {
    ParameterMetadata metadata = AnnotatedElementUtils.findMergedAnnotation(
        methodParameter.getParameter(), ParameterMetadata.class
    );

    if (metadata != null) {
        // Use metadata to adjust the matching operation parameter.
    }
}
```

The snippet illustrates accessing annotations on each parameter. When modifying a parameter in `Operation`, match both name and location (`query`, `path`, `header`, `cookie`) to update the exact parameter generated by Springdoc. Avoid adding a new parameter if a matching one already exists.

If annotations reside on interfaces or are composed via meta-annotations, verify how Spring and `AnnotatedElementUtils` resolve annotations in your project's controller hierarchy. Not all Java inheritance patterns exhibit identical annotation lookup behavior.

## 10. Safety Rules When Customizing Operations

Customizers directly affect the published contract, so keep changes intentional and stable:

- **Do not create duplicate operationIds.** If changing `operationId`, ensure values are unique within the document and stable across builds; client generators often use this field to name generated methods.
- **Do not erase inferred metadata unnecessarily.** Summary, tags, parameters, request body, and responses may already have been built accurately by Springdoc.
- **Do not add duplicate parameters.** Check both `name` and `in` before adding; a header and a query parameter with the same name are still two distinct parameters.
- **Do not alter response schemas arbitrarily.** Every change must reflect the runtime payload.
- **Do not treat extensions as security.** `x-audience`, `x-internal`, or `deprecated` are only metadata; they do not block requests.
- **Avoid I/O or network queries.** Customizers may run when generating or refreshing documentation; heavy processing slows down generation and introduces unpredictability.
- **Keep results deterministic.** The same handler and configuration should produce identical metadata so documentation remains stable in CI.
- **Avoid relying on runtime bean state.** Rely on `getBeanType()`, `getMethod()`, and annotations rather than calling business methods or reading mutable bean state.

## 11. Verifying Customizer Results

After registering the customizer, open the corresponding OpenAPI document, such as `/v3/api-docs/partner`. Check:

1. Operations at the expected paths and HTTP methods are customized.
2. The `x-audience` extension has values taken from the method or class in the right precedence order.
3. Endpoints with `@LegacyEndpoint` are marked `deprecated: true`.
4. Header parameters are added in the right location, with the right name, and without duplicates.
5. Existing summary, description, tags, request body, and responses remain intact.
6. Other groups are not unexpectedly modified.

Example JSON check by inspecting an operation:

```json
{
  "get": {
    "x-audience": "partner",
    "summary": "List orders"
  }
}
```

This is an illustrative excerpt. The full structure may also contain tags, parameters, responses, security, and other metadata.

Write tests for customizer logic when a rule is widely used. You can construct a `HandlerMethod` from a test method and a new `Operation` model, invoke `customize`, and verify that extensions or flags were set. Beyond unit tests, inspect the OpenAPI document generated by Springdoc to confirm the customizer is registered on the right group.

## 12. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Customizer does not run | Not registered on the group being checked or bean not discovered by Spring | Check `@Component`/`@Bean` and `addOperationCustomizer` |
| Class annotation is not read | Only checking the method or lookup does not handle meta-annotations | Use `AnnotatedElementUtils` and define a clear fallback |
| Method value does not override class value | Wrong annotation lookup order | Check the method first, then the class |
| Header appears twice | Springdoc already auto-created the parameter from `@RequestHeader` | Search parameters by both `name` and `in` before adding |
| `x-audience` does not appear | Extension map not initialized or customizer did not run | Initialize the map and verify the right group document |
| Endpoint marked deprecated yet still accessible | Confused OpenAPI metadata with runtime behavior | Execute decommissioning separately at the controller/gateway |
| Documentation differs across builds | Customizer depends on mutable data or external time | Remove non-deterministic sources, use stable metadata |
| Works in one group but missing in another | Customizer attached only to one group | Register on every target group or use the version-appropriate global mechanism |
| Duplicate OperationId after customization | IDs generated from method names are not unique enough | Keep Springdoc-generated IDs or build a uniqueness rule with validation |

## 13. Checklist for `OperationCustomizer`

- [ ] Customizer receives `Operation` and `HandlerMethod` for the intended purpose.
- [ ] Method annotations are read before class annotations when method overrides apply.
- [ ] `AnnotatedElementUtils` is used when meta-annotation support is needed.
- [ ] Only modifies metadata grounded in the controller or declared conventions.
- [ ] Initializes the extension map when absent and prefixes extension names with `x-`.
- [ ] Checks existing parameters before adding to prevent duplicates.
- [ ] Does not confuse OpenAPI metadata with runtime authentication, authorization, or routing.
- [ ] Registers the customizer on the right `GroupedOpenApi` or version-compatible global mechanism.
- [ ] Uses `OpenApiCustomizer` when changing the entire document rather than one operation.
- [ ] Inspects generated JSON/YAML and preserves metadata created by Springdoc.
- [ ] Keeps the customizer fast, deterministic, and free of controller business calls.

`OperationCustomizer` combined with `HandlerMethod` turns controller metadata into reusable documentation rules. By reading annotations in a clear precedence order and modifying operations only within the necessary scope, teams can add audience, deprecation status, parameters, or extensions while keeping the OpenAPI contract consistent with Spring Boot controllers.
