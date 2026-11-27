# @BasePathAwareController and How It Differs from Regular @RestController

## Objectives

After this lesson, you will be able to:

- Explain the role of **@BasePathAwareController** in Spring Data REST.
- Understand how the repository exporter's base path is prepended to custom request mappings.
- Distinguish **@BasePathAwareController**, **@RestController**, and **@RepositoryRestController**.
- Choose the appropriate annotation for custom endpoints, views, or operations tied to repository resources.
- Return JSON, ResponseEntity, and Spring HATEOAS representations from custom controllers.
- Avoid URL conflicts, duplicate base path configuration, and misconceptions about CORS or security.
- Inspect endpoints using curl and browser DevTools.

## 1. Why Do You Need a Base-Path-Aware Controller?

Spring Data REST can automatically publish repositories as REST APIs. For example, if an application configures the base path as **/api**, the Person repository can be accessed at:

~~~text
/api/people
/api/people/42
~~~

In practice, applications often need additional custom endpoints such as system status, reports, business actions, or admin pages. If you create a standard Spring MVC controller, that controller's mappings do not automatically receive the Spring Data REST base path.

This easily produces two separate groups of URLs:

~~~text
Spring Data REST:  /api/people
Custom MVC:        /reports/summary
~~~

If you want custom endpoints to sit under the same base path as the repository API, Spring Data REST provides **@BasePathAwareController**. This annotation marks a controller whose request mappings should have the base URI configured in Spring Data REST prepended.

For example:

~~~text
Spring Data REST base path: /api
Custom mapping:             /system/status
Final URL:                  /api/system/status
~~~

As a result, if the base path changes from **/api** to **/rest**, the custom endpoint adjusts automatically with the global configuration without editing each mapping.

## 2. Configuring the Base Path

You can configure the base path via a Spring Boot property:

~~~properties
spring.data.rest.base-path=/api
~~~

Or using RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

In the following examples, assume the base path is **/api**. This base path belongs to Spring Data REST. It is distinct from the servlet context path that can be configured at the web application level.

If the application also uses a servlet context path, external URLs may include that context path as well. Be sure to distinguish both settings when verifying actual URLs.

## 3. What Is @BasePathAwareController?

**@BasePathAwareController** lives in the package:

~~~java
org.springframework.data.rest.webmvc.BasePathAwareController
~~~

It is a Spring Data REST annotation used to mark controllers whose request mappings should be prefixed with the base URI configured in RepositoryRestConfiguration.

Simple example:

~~~java
import java.util.Map;

import org.springframework.data.rest.webmvc.BasePathAwareController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@BasePathAwareController
public class SystemStatusController {

    @GetMapping("/system/status")
    @ResponseBody
    public Map<String, String> status() {
        return Map.of("status", "UP");
    }
}
~~~

With base path **/api**, the endpoint is served at:

~~~http
GET /api/system/status
~~~

Key points:

- **@BasePathAwareController** tells Spring Data REST that this controller must receive the configured base path.
- **@GetMapping** still defines the handler method's path portion.
- **@ResponseBody** instructs Spring to write the return value to the response body, for instance serializing the Map as JSON.
- The controller remains a custom endpoint defined by the application; the annotation does not automatically create a repository or entity resource.

If you want to return a Spring MVC view instead of JSON, the controller can use the corresponding view resolution mechanism. This is one reason the annotation suits custom operations or resources under the base path that are not necessarily operations on a single entity.

## 4. The path and value Attributes

**@BasePathAwareController** supports **path** and **value** attributes as aliases of each other. They specify a root path prepended to the handler method request mappings.

Example:

~~~java
@BasePathAwareController(path = "/ops")
public class OperationsController {

    @GetMapping("/health")
    @ResponseBody
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }
}
~~~

With base path **/api**, the combined URL is:

~~~text
/api/ops/health
~~~

You can use **value** instead of **path**:

~~~java
@BasePathAwareController("/ops")
public class OperationsController {
    // Handler mappings start from /ops.
}
~~~

Use only one of the two attributes to avoid duplicate configuration. This attribute acts as an additional root path for the controller's mappings; it does not replace the base path configured at the Spring Data REST level.

## 5. Distinguishing from Regular @RestController

**@RestController** is a Spring MVC annotation. It combines the controller role with **@ResponseBody**, so the handler method's return value is written to the HTTP response body and typically serialized via an HttpMessageConverter.

Example:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/reports/summary")
    public Map<String, Object> summary() {
        return Map.of(
            "activeMembers", 120,
            "pendingOrders", 8
        );
    }
}
~~~

The mapping above belongs to standard Spring MVC. If Spring Data REST has base path **/api**, **@RestController** does not automatically turn the URL into **/api/reports/summary**. The URL still depends on the servlet context path and application mappings, but does not automatically prepend the Spring Data REST base path.

Comparison:

| Criterion | @BasePathAwareController | @RestController |
|---|---|---|
| Mechanism | Controller recognized by Spring Data REST to prepend the base URI | Standard Spring MVC controller |
| Spring Data REST base path | Automatically prepended to request mappings | Not automatically prepended |
| Response body | Use @ResponseBody or return types like ResponseEntity when a body is needed | Includes @ResponseBody at the class level |
| Purpose | Custom operations/resources under the Spring Data REST base path | Standard application REST endpoints |
| Processing scope | Recognized by Spring Data REST's base-path-aware infrastructure | Outside Spring Data REST-specific processing |
| Example URL with /api base path | /api/system/status | /reports/summary |

If you use **@RestController** and hardcode **/api** into @RequestMapping, the endpoint may work at the moment. However, when the base path changes, that mapping does not change with it. This creates duplicated configuration and can cause custom endpoints to drift from the repository API.

Do not confuse **server.servlet.context-path** with **spring.data.rest.base-path**. The context path belongs to the web application; the base path belongs to the REST exporter. A standard MVC controller can sit under the context path, yet that does not make it base-path-aware in Spring Data REST.

## 6. @BasePathAwareController Does Not Mean @RestController

One important detail: **@BasePathAwareController** is responsible for marking a controller as base-path-aware. It should not be treated as a full alias for **@RestController**.

If a handler returns a Map, DTO, or object that needs to be serialized as JSON, explicitly declare **@ResponseBody** on the method:

~~~java
@BasePathAwareController
public class VersionController {

    @GetMapping("/system/version")
    @ResponseBody
    public Map<String, String> version() {
        return Map.of("version", "1.0.0");
    }
}
~~~

Or return ResponseEntity:

~~~java
@BasePathAwareController
public class VersionController {

    @GetMapping("/system/version")
    public ResponseEntity<Map<String, String>> version() {
        return ResponseEntity.ok(
            Map.of("version", "1.0.0")
        );
    }
}
~~~

ResponseEntity is a return type with an explicit body, status, and headers. For handlers returning an object directly, @ResponseBody specifies that the object is the response body rather than a view name.

Do not add **@RestController** just to get JSON and assume the base path will still be applied automatically. Choose the annotation based on the handler mapping behavior you need.

## 7. Further Distinction from @RepositoryRestController

Spring Data REST also provides **@RepositoryRestController**. This annotation also receives the base path, but serves a more specific purpose: custom handlers bound to the URI space managed by repository resources.

Example:

~~~java
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseBody;

@RepositoryRestController
public class PersonCustomController {

    private final PersonRepository repository;

    public PersonCustomController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/{id}/summary")
    @ResponseBody
    public PersonSummary summary(@PathVariable Long id) {
        Person person = repository.findById(id).orElseThrow();
        return PersonSummary.from(person);
    }
}
~~~

With base path **/api**, the illustrative URL is:

~~~text
/api/people/42/summary
~~~

Key differences:

- **@BasePathAwareController** is for custom operations under the base path, such as resources or views not directly tied to an operation on a repository entity.
- **@RepositoryRestController** is for handlers whose mappings lie inside a repository resource's URI space. Its specialized infrastructure can apply repository-specific CORS and OpenEntityManagerInViewInterceptor for JPA to support accessing lazy properties.
- **@RestController** is a regular Spring MVC controller, outside Spring Data REST-specific processing.

If a handler works with a repository item and needs repository-specific integration settings, consider **@RepositoryRestController**. If you only need a custom resource under the base path, **@BasePathAwareController** is usually more appropriate.

Do not use @RepositoryRestController for every endpoint just because its name looks like Spring Data REST. Its mappings need to fit the URI space managed by repositories.

## 8. Choosing an Annotation by Scenario

| Scenario | Annotation to Consider |
|---|---|
| Health/status endpoint under /api | **@BasePathAwareController** |
| Custom resource or view under the base path | **@BasePathAwareController** |
| Additional handler for a repository resource needing repository CORS/OEIV | **@RepositoryRestController** |
| Standalone application API without needing the Spring Data REST base path | **@RestController** |
| Standard MVC controller returning HTML views | **@Controller** |
| Collection/item CRUD already published by a repository | Repository managed by Spring Data REST; usually no custom controller needed |

Decide based on two questions:

1. Does the endpoint need to sit automatically under the Spring Data REST base path?
2. Does the endpoint need to be handled as a custom handler inside a repository's URI space, or just as a standalone custom resource?

The answers help you select the right annotation and avoid controllers unintentionally competing with the repository exporter for URLs.

## 9. Combining with Spring HATEOAS

A custom endpoint can return data accompanied by links so clients can discover the API. Spring HATEOAS provides **EntityModel**, **CollectionModel**, and RepresentationModel types to represent resources with links.

Example:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;

@BasePathAwareController
public class SystemInfoController {

    @GetMapping("/system/info")
    @ResponseBody
    public EntityModel<SystemInfo> info() {
        SystemInfo info = new SystemInfo("Spring Data REST");

        return EntityModel.of(
            info,
            linkTo(methodOn(SystemInfoController.class).info()).withSelfRel()
        );
    }
}
~~~

This example illustrates a custom resource with a self link. In a real project, check the link builder and servlet/base path configuration for your Spring HATEOAS version to ensure generated URIs match your deployment.

Placing a controller under the base path does not automatically add that endpoint's link to every repository HAL response. If clients need to discover the custom operation from an entity or the API root, add links using an appropriate mechanism such as RepresentationModelProcessor or ResourceProcessor.

## 10. Avoiding Mapping Conflicts

Spring Data REST already claims a URI space for collection, item, association, and search resources. When adding a custom controller, avoid defining paths that collide with endpoints already published by repositories.

For example, do not arbitrarily use:

~~~text
/api/people
/api/people/{id}
~~~

for another custom controller if those paths already belong to PersonRepository.

Instead, choose a clear namespace:

~~~text
/api/system/status
/api/reports/summary
/api/operations/reindex
~~~

If you need an operation attached to a specific item, use a non-conflicting subpath and consider **@RepositoryRestController**:

~~~text
/api/people/42/summary
~~~

When a mapping is not invoked as expected, check startup logs for ambiguous mappings, inspect the actual request URL, and identify which HandlerMapping is handling the endpoint.

## 11. CORS and Security Configuration

**@BasePathAwareController** only handles receiving the base path. It does not automatically grant frontend access and does not replace CORS configuration.

If a custom endpoint needs cross-origin access, configure CORS via the Spring MVC/Spring Security mechanism appropriate for that endpoint. Do not assume CORS rules configured for repository resources automatically apply identically to every custom controller.

Similarly, having a URL under **/api** does not automatically give the endpoint the authentication or authorization you expect. Check your SecurityFilterChain and apply explicit rules for custom paths.

A few principles:

- Allow only trusted frontend origins.
- Restrict HTTP methods and request headers as needed.
- Enforce user permissions on the server for each operation.
- If using cookie sessions, evaluate CSRF protection.
- Do not treat hiding links or changing the base path as a security measure.

With **@RepositoryRestController**, Spring Data REST can apply CORS configuration according to the repository mapped to the handler's path. This is one of the practical differences compared to custom endpoints using only @BasePathAwareController.

## 12. Testing Endpoints with curl

Assume:

- Base path: **/api**
- Controller: **@BasePathAwareController**
- Handler: **@GetMapping("/system/status")**

Call the endpoint:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/system/status
~~~

The expected result is a success status with a JSON body, for example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

Test a regular MVC endpoint:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/reports/summary
~~~

If a standard Spring MVC mapping is declared as in the earlier example, the URL does not automatically include **/api**. If the application has a servlet context path, include that context path according to the actual web configuration.

If you change the base path from **/api** to **/rest**, call again:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/rest/system/status
~~~

The base-path-aware endpoint follows the new prefix according to the updated configuration. A @RestController with a hardcoded mapping will not automatically follow the Spring Data REST base path.

## 13. Inspecting with Browser DevTools

In the Network panel:

1. Call the endpoint from the frontend.
2. Verify that the Request URL includes the correct base path.
3. Check the method and status code.
4. Inspect the Content-Type and response body.
5. If the browser reports CORS errors, inspect the OPTIONS preflight and response headers.
6. If you receive 404, check the base path, servlet context path, and controller mapping.
7. If you receive 406/415, check Accept and Content-Type.
8. If you receive 401/403, check the security rules for the custom path.

Use Actuator mappings or startup logs if the project enables appropriate diagnostic endpoints to view registered mappings. Do not expose sensitive mapping details to public environments if operational policies forbid it.

## 14. Common Pitfalls

### @RestController Is Not Under /api

@RestController uses standard Spring MVC mappings. It does not automatically receive the Spring Data REST base path. Use @BasePathAwareController or configure paths manually according to your application architecture.

### Manually Adding /api to Every Mapping

When the base path changes, hardcoded mappings do not update with it. Let Spring Data REST prepend the prefix using @BasePathAwareController.

### Using @BasePathAwareController but Objects Are Not Serialized as JSON

This annotation marks a base-path-aware controller and should not be treated as a full alias for @RestController. Use @ResponseBody on the handler or return ResponseEntity.

### Using @RepositoryRestController for Standalone Endpoints

RepositoryRestController fits the repository URI space and provides repository-specific integrations. For health, reports, or standalone resources under the base path, consider @BasePathAwareController.

### Custom Mapping Collides with a Repository

Collection, item, association, or search paths may already be claimed by the exporter. Choose a dedicated namespace and check for ambiguous mappings.

### Repository CORS Does Not Apply as Expected

CORS depends on handler mappings and security configuration. @BasePathAwareController does not automatically share the same repository-specific CORS behavior as @RepositoryRestController.

### Assuming the Base Path Provides Security

The base path is just a URL prefix. Authentication, authorization, CSRF, and validation must still be configured separately.

### Custom Endpoint Does Not Appear in HAL

A controller mapping does not automatically add links to repository representations. If clients need to discover the endpoint, add explicit hypermedia links.

## 15. Key Takeaways

- **@BasePathAwareController** marks a custom controller whose request mappings get the Spring Data REST base URI prepended.
- The base path can be configured with **spring.data.rest.base-path** or **RepositoryRestConfiguration.setBasePath(...)**.
- The annotation's **path/value** attributes can add a root path for handler mappings.
- **@RestController** is a standard Spring MVC controller and does not automatically receive the Spring Data REST base path.
- Use **@ResponseBody** or **ResponseEntity** when a base-path-aware handler needs to return a response body.
- **@RepositoryRestController** is for custom handlers in a repository's URI space and provides integrations such as repository-based CORS and OpenEntityManagerInView for JPA.
- Choose custom namespaces that avoid colliding with collection, item, association, and search resources.
- The base path does not automatically add hypermedia links, provide authentication, or replace authorization.
- Verify URLs, HandlerMapping, CORS, security, and responses with curl/DevTools.

## References

- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — BasePathAwareController API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/BasePathAwareController.html)
- [Spring Data REST — RepositoryRestController API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositoryRestController.html)
- [Spring Data REST — Getting Started and Base URI](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
