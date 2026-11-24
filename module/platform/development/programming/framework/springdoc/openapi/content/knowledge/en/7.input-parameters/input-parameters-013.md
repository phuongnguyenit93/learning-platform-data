# Reusable Parameters via components.parameters

An API often repeats the same parameters across multiple operations: a tenant ID in a header, a version code in a query, pagination filters, or an identifier passed in a path. If each operation redeclares the entire name, type, description, and constraints, documentation easily drifts out of sync when rules change.

OpenAPI provides <code>components.parameters</code> to define a reusable Parameter Object. Operations or Path Items can reference that definition using <code>$ref</code>. With springdoc-openapi, you can create components via an OpenAPI bean and attach references to operations using <code>OpenApiCustomizer</code> or <code>GlobalOpenApiCustomizer</code>.

## 1. Parameter Object and components.parameters

A Parameter Object describes a parameter that a client sends in a request. A parameter is identified by its name and location:

- <code>path</code>: part of the URL path.
- <code>query</code>: query string after <code>?</code>.
- <code>header</code>: HTTP request header.
- <code>cookie</code>: cookie sent with the request.

For example, the <code>X-Tenant-Id</code> parameter sent in a header:

~~~yaml
name: X-Tenant-Id
in: header
required: true
description: Tenant identifier making the request
schema:
  type: string
~~~

When it appears in only one operation, you can declare the Parameter Object directly on that operation. When multiple operations share the same definition, place it under <code>components.parameters</code>:

~~~yaml
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      description: Tenant identifier making the request
      schema:
        type: string
~~~

<code>TenantId</code> is a key chosen by the API team to identify the component. This key is case-sensitive and does not have to match the HTTP parameter name. The actual HTTP name is still declared in the <code>name</code> property.

Placing a definition in <code>components.parameters</code> only creates a reusable entry. It **does not automatically add the parameter to all endpoints**. For an operation to use that definition, it must reference the component via <code>$ref</code>.

## 2. Referencing Components with $ref

An operation can use a Parameter Object declared in components:

~~~yaml
paths:
  /customers:
    get:
      operationId: listCustomers
      parameters:
        - $ref: "#/components/parameters/TenantId"
      responses:
        "200":
          description: List of customers
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      description: Tenant identifier making the request
      schema:
        type: string
~~~

The path <code>#/components/parameters/TenantId</code> is a JSON Pointer pointing to the component keyed <code>TenantId</code> in the current document. Key names must match exactly.

An operation can have multiple reusable parameters:

~~~yaml
paths:
  /orders:
    get:
      parameters:
        - $ref: "#/components/parameters/TenantId"
        - $ref: "#/components/parameters/PageSize"
      responses:
        "200":
          description: List of orders
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      schema:
        type: string
    PageSize:
      name: pageSize
      in: query
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
~~~

A component can be referenced from multiple operations and also from a Path Item's <code>parameters</code> array. Parameters at the Path Item level apply to every operation under that path; operation-level parameters apply only to that specific operation.

Do not declare duplicate parameters with the same name and location on the same operation. OpenAPI determines parameter uniqueness by the combination of <code>name</code> and <code>in</code>. If you have referenced component <code>TenantId</code>, do not add another inline parameter that also has <code>name: X-Tenant-Id</code> and <code>in: header</code>.

## 3. Important Properties of Parameter Object

Parameter Object has several commonly used properties:

| Property | Meaning |
|---|---|
| <code>name</code> | HTTP parameter name |
| <code>in</code> | Location: path, query, header, or cookie |
| <code>description</code> | Description of how to use the parameter |
| <code>required</code> | Whether the parameter is mandatory; path parameters are always required |
| <code>deprecated</code> | Marks the parameter as deprecated |
| <code>schema</code> | Data type and value constraints |
| <code>example</code> / <code>examples</code> | Illustrative values |
| <code>style</code> and <code>explode</code> | How values are serialized into HTTP strings |

Example of a shared query parameter for pagination:

~~~yaml
components:
  parameters:
    PageSize:
      name: pageSize
      in: query
      required: false
      description: Maximum number of items per page
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
      example: 25
~~~

In this example, <code>required: false</code> allows clients to omit the query parameter. <code>default: 20</code> documents the contract's default value; the server must still implement the corresponding default behavior. <code>minimum</code> and <code>maximum</code> document valid bounds, though they do not automatically add validation to the controller.

For path parameters, <code>required</code> must be <code>true</code>:

~~~yaml
components:
  parameters:
    CustomerId:
      name: customerId
      in: path
      required: true
      description: Customer ID to retrieve
      schema:
        type: string
~~~

Do not place <code>Accept</code>, <code>Content-Type</code>, or <code>Authorization</code> headers in Parameter Objects. OpenAPI reserves dedicated mechanisms for them: content negotiation is expressed via <code>content</code> in request bodies/responses; authentication is documented via <code>components.securitySchemes</code> and security requirements.

## 4. Distinguishing components.parameters from Other Components

In OpenAPI, entries under <code>components</code> serve distinct purposes. Do not use them interchangeably:

| Component | Description | Typical Reference Location |
|---|---|---|
| <code>components.parameters</code> | Request parameters such as path, query, header, cookie | Path Item or Operation <code>parameters</code> |
| <code>components.headers</code> | Response headers | Response Object <code>headers</code> |
| <code>components.schemas</code> | JSON/XML data structures or schema types | Request/response <code>schema</code> |
| <code>components.requestBodies</code> | Reusable request body definitions | Operation <code>requestBody</code> |
| <code>components.responses</code> | Reusable response definitions | Operation <code>responses</code> |
| <code>components.securitySchemes</code> | Authentication mechanisms such as API key, HTTP bearer, OAuth2 | Security requirements |

For example, <code>X-Request-Id</code> sent by the client is a request parameter in the header location and can be defined in <code>components.parameters</code>. The header <code>X-RateLimit-Remaining</code> returned by the server is a response header and belongs in <code>components.headers</code>.

## 5. Declaring Reusable Components via an OpenAPI Bean

springdoc-openapi allows providing an <code>OpenAPI</code> bean to add definitions to the document. The following example declares two shared parameters:

~~~java
import java.math.BigDecimal;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiComponentsConfiguration {

    @Bean
    OpenAPI reusableParametersOpenAPI() {
        return new OpenAPI()
            .components(new Components()
                .addParameters("TenantId",
                    new Parameter()
                        .name("X-Tenant-Id")
                        .in("header")
                        .required(true)
                        .description("Tenant identifier making the request")
                        .schema(new StringSchema()))
                .addParameters("PageSize",
                    new Parameter()
                        .name("pageSize")
                        .in("query")
                        .required(false)
                        .description("Maximum number of items per page")
                        .schema(new IntegerSchema()
                            .minimum(new BigDecimal("1"))
                            .maximum(new BigDecimal("100"))
                            ._default(20))))
            .info(new Info()
                .title("Customer API")
                .version("1.0.0"));
    }
}
~~~

The bean above adds definitions to <code>components.parameters</code>. The definitions <code>TenantId</code> and <code>PageSize</code> will appear in the OpenAPI document. Parameters are not attached to operations until a <code>$ref</code> reference is added.

If the project already has an OpenAPI bean declaring <code>info</code>, <code>servers</code>, or security schemes, add the <code>addParameters(...)</code> calls to the existing <code>Components</code>. An application should have only one unified OpenAPI bean configuration; do not create a second bean just to declare parameters.

An OpenAPI bean suits components shared across the whole document, even when the application has multiple <code>GroupedOpenApi</code> groups. If a component only needs to appear in one group, add it via a customizer attached to that group.

## 6. Attaching $ref to Operations with OpenApiCustomizer

Controllers still need Spring annotations to bind requests at runtime:

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @GetMapping("/customers")
    Object listCustomers(
            @RequestHeader(name = "X-Tenant-Id") String tenantId,
            @RequestParam(name = "pageSize", required = false) Integer pageSize) {
        // Query customers by tenant and page size
        return List.of();
    }
}
~~~

springdoc will automatically generate two inline Parameter Objects from <code>@RequestHeader</code> and <code>@RequestParam</code>. If you want the final document to use component references, the customizer must replace those two inline parameters with <code>$ref</code>. Simply adding references while leaving the inline copies creates duplicate parameters with the same name and location.

~~~java
import java.util.ArrayList;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ReusableParameterCustomizerConfiguration {

    @Bean
    OpenApiCustomizer customerParameterReferences() {
        return openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }
            PathItem pathItem = openApi.getPaths().get("/customers");
            if (pathItem == null || pathItem.getGet() == null) {
                return;
            }

            Operation operation = pathItem.getGet();
            if (operation.getParameters() == null) {
                operation.setParameters(new ArrayList<>());
            }

            operation.getParameters().removeIf(parameter ->
                ("header".equals(parameter.getIn())
                    && "X-Tenant-Id".equals(parameter.getName()))
                || ("query".equals(parameter.getIn())
                    && "pageSize".equals(parameter.getName())));

            operation.addParametersItem(
                new Parameter().$ref("#/components/parameters/TenantId"));
            operation.addParametersItem(
                new Parameter().$ref("#/components/parameters/PageSize"));
        };
    }
}
~~~

This example replaces the inline parameters generated by springdoc for the <code>GET /customers</code> operation with component references. If the path or HTTP method changes, update the operation lookup condition accordingly. When many operations share parameters, write a helper function to replace parameters across a chosen list of paths/methods.

Customizers only affect the OpenAPI specification. Binding <code>X-Tenant-Id</code> and <code>pageSize</code> is still performed by Spring annotations in the controller. Component references do not create Spring request parameters and do not change validation logic.

### 6.1. OpenApiCustomizer and GlobalOpenApiCustomizer

springdoc-openapi has two customizer scopes to distinguish:

- <code>OpenApiCustomizer</code> applies to the default OpenAPI document.
- <code>GlobalOpenApiCustomizer</code> applies to the default document as well as all <code>GroupedOpenApi</code> group documents.

If the application has multiple groups and every group needs to reference shared components, change the customizer bean return type to <code>GlobalOpenApiCustomizer</code>:

~~~java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;

@Bean
GlobalOpenApiCustomizer customerParameterReferences() {
    return openApi -> {
        // Find operations in the current group document,
        // remove matching inline parameters, and add $refs.
    };
}
~~~

If only a single group needs those references, attach the customizer directly when building <code>GroupedOpenApi</code> via <code>addOpenApiCustomizer(...)</code>. Components defined in an OpenAPI bean can be shared; customizers decide which operations in each document receive references.

## 7. Using Reusable Parameters at the Path Item Level

If every operation on the same path requires a parameter, you can place the reference at the Path Item level:

~~~yaml
paths:
  /reports:
    parameters:
      - $ref: "#/components/parameters/TenantId"
    get:
      operationId: listReports
      responses:
        "200":
          description: List of reports
    post:
      operationId: createReport
      responses:
        "201":
          description: Report created
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      schema:
        type: string
~~~

Path-level parameters apply to all operations under that path. Specific operations can still add their own parameters. If an operation declares a parameter with the same <code>name</code> and <code>in</code> combination as a path-level parameter, handle it per OpenAPI override rules and avoid creating inconsistent declarations.

Do not promote a header needed by only one operation to the Path Item level if other operations do not need it. Placing parameters at the right level keeps documentation accurate to the contract and avoids requiring clients to send extra parameters.

## 8. API-Wide Shared Parameters vs. Reusable Parameters

These two ideas differ:

- **Reusable parameter**: defined once in <code>components.parameters</code> and referenced only on operations that need it.
- **Global parameter**: adds a parameter to every operation or a subset of operations per API policy.

A component in <code>components.parameters</code> does not automatically become a global parameter. If every endpoint needs a header, you can use a customizer to add the same reference to matching operations. Filter the target scope carefully, as some operations like health checks, public endpoints, or callbacks may not require that header.

Do not turn authentication parameters into ordinary header parameters. For API keys, bearer tokens, or OAuth2, declare security schemes and security requirements so Swagger UI and client tools understand the security mechanism properly.

## 9. Verifying Components and References

After configuration, download the OpenAPI JSON document:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Verify these locations:

- <code>components.parameters.TenantId</code> and <code>components.parameters.PageSize</code> exist.
- Operation <code>GET /customers</code> has two <code>$ref</code> entries pointing to the exact components.
- No duplicate inline parameters remain with the same name and location pair.
- <code>name</code>, <code>in</code>, <code>required</code>, schema, and description in the component match how the controller binds data.
- Group documents also contain the components and references if the customizer applies to those groups.

Expected partial output:

~~~yaml
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      schema:
        type: string
    PageSize:
      name: pageSize
      in: query
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
paths:
  /customers:
    get:
      parameters:
        - $ref: "#/components/parameters/TenantId"
        - $ref: "#/components/parameters/PageSize"
~~~

You can quickly inspect references using <code>jq</code>:

~~~bash
curl -s http://localhost:8080/v3/api-docs |
  jq -r '.paths | to_entries[] |
    .key as $path |
    .value | to_entries[] |
    .key as $method |
    (.value.parameters // [])[] |
    select(.$ref != null) |
    [$method, $path, .$ref] | @tsv'
~~~

After checking the document, test real requests with and without parameters, using both valid and invalid values. Documentation describes the rules; controllers, validation, and services enforce that behavior.

## 10. Common Issues

**Component is defined but missing from operations.** <code>components.parameters</code> is only where definitions live. You must add <code>$ref</code> to the <code>parameters</code> array of a Path Item or Operation.

**Parameter appears twice.** Controller annotations caused springdoc to generate inline parameters. When the customizer adds references, remove the inline copies with the matching name and location first.

**$ref cannot resolve component.** Check the key under <code>components.parameters</code>, spelling, and case sensitivity in the JSON Pointer.

**Misusing components.headers.** <code>components.headers</code> is for response headers; request parameters in headers must use <code>components.parameters</code>.

**Parameter definition mismatches runtime binding.** Check <code>name</code> and <code>in</code> on the component alongside <code>@RequestParam</code>, <code>@PathVariable</code>, <code>@RequestHeader</code>, or <code>@CookieValue</code>. <code>$ref</code> only modifies documentation.

**Customizer does not run for grouped documents.** To apply a customizer across <code>GroupedOpenApi</code> as well, use <code>GlobalOpenApiCustomizer</code> or register a dedicated customizer in the group configuration.

**Adding authentication headers as regular parameters.** Do not document <code>Authorization</code> using a Parameter Object. Use <code>components.securitySchemes</code> and security requirements.

## 11. Pre-Publication Review Checklist

- [ ] Repeated parameters have definitions in <code>components.parameters</code>.
- [ ] Component keys have clear, stable, and non-conflicting names.
- [ ] Every target operation references components properly via <code>$ref</code>.
- [ ] No duplicate parameters share the same <code>name</code> and <code>in</code> within an operation.
- [ ] Path Item-level parameters apply only to operations that genuinely need them.
- [ ] Spring runtime binding matches component definitions.
- [ ] Verified whether customizers target the default document or all groups.
- [ ] Authentication headers are documented via security schemes.
- [ ] Inspected generated documentation and tested real requests.

## References

- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object): defining reusable components, including <code>parameters</code>.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): parameter attributes, locations, and rules.
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object): syntax and behavior of <code>$ref</code>.
- [springdoc-openapi FAQ](https://springdoc.org/faq.html): declaring shared parameters in an OpenAPI bean, referencing via <code>$ref</code>, and scope differences between <code>OpenApiCustomizer</code> and <code>GlobalOpenApiCustomizer</code>.
- [Swagger – Describing Parameters](https://swagger.io/docs/specification/describing-parameters/): documenting path, query, header, and cookie parameters.
