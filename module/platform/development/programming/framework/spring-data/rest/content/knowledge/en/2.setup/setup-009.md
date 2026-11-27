# Configuring `spring.data.rest.*` and `RepositoryRestConfigurer`

Spring Data REST automatically exports Spring Data repositories as REST resources. When an application needs to change the base path, page size limits, query parameter names, default media type, or repository export policy, there are two main configuration mechanisms:

- **`spring.data.rest.*`** properties in **`application.properties`** or **`application.yml`** are well-suited for static, environment-specific settings.
- **`RepositoryRestConfigurer`** is well-suited when Java-based configuration is needed, such as conditional rules, HTTP method exposure control, CORS, converters, or validators.

Spring Boot configures Spring Data REST automatically when the application includes **`spring-boot-starter-data-rest`** and uses **`@SpringBootApplication`** or **`@EnableAutoConfiguration`**. You do not need to import **`RepositoryRestMvcConfiguration`** manually in a standard Spring Boot application. To customize settings, register a bean implementing **`RepositoryRestConfigurer`**.

## 1. `spring.data.rest.*` Properties

Spring Boot binds properties prefixed with **`spring.data.rest`** into Spring Data REST configuration. Use kebab-case in configuration files.

Example **`src/main/resources/application.properties`**:

```properties
spring.data.rest.base-path=/api
spring.data.rest.default-page-size=25
spring.data.rest.max-page-size=100
spring.data.rest.page-param-name=p
spring.data.rest.limit-param-name=limit
spring.data.rest.sort-param-name=sort
spring.data.rest.default-media-type=application/hal+json
spring.data.rest.return-body-on-create=true
spring.data.rest.return-body-on-update=true
spring.data.rest.detection-strategy=annotated
spring.data.rest.enable-enum-translation=false
```

With the configuration above, repository resources are placed under the **`/api`** prefix. For example, the **`/books`** collection becomes **`/api/books`**. Pagination parameters are renamed to **`p`** (page number), **`limit`** (maximum items per page), and **`sort`** (sorting).

### Meaning of Each Property

| Property | Effect |
|---|---|
| **`base-path`** | URL prefix for repository resources, e.g., **`/api`** |
| **`default-page-size`** | Default number of items when the client does not specify a page size |
| **`max-page-size`** | Upper bound on items per page; requests exceeding this are capped |
| **`page-param-name`** | Query parameter name used to select the page number |
| **`limit-param-name`** | Query parameter name used to specify the desired number of items |
| **`sort-param-name`** | Query parameter name used for sorting |
| **`default-media-type`** | Default media type when a request does not specify a response format |
| **`return-body-on-create`** | Whether to return a representation in the response after creating an entity |
| **`return-body-on-update`** | Whether to return a representation in the response after updating an entity |
| **`detection-strategy`** | Rule deciding which repositories are exported |
| **`enable-enum-translation`** | Enables or disables translating enum values via Spring Data REST's default resource bundle |

**`default-media-type`** is only the fallback choice. Clients can still request a representation via the **`Accept`** header, such as **`Accept: application/hal+json`**. HAL is well-suited for clients that read hypermedia links.

If **`return-body-on-create`** or **`return-body-on-update`** is explicitly set to **`true`**, the response after the corresponding operation includes a body. If set to **`false`**, the body is omitted. When left unset, the decision may depend on the request's **`Accept`** header. This header does not change whether the operation succeeds; clients should still inspect the status code and **`Location`** header when creating resources.

### Repository Detection Strategy

**`spring.data.rest.detection-strategy`** decides which repositories Spring Data REST detects and exports.

| Value | Behavior |
|---|---|
| **`default`** | Exports public repository interfaces while respecting the **`exported`** flag on **`@RepositoryRestResource`** |
| **`all`** | Exports all repositories, regardless of visibility or annotations |
| **`annotated`** | Exports only repositories with **`@RepositoryRestResource`**, excluding those marked **`exported = false`** |
| **`visibility`** | Exports only public repositories annotated with **`@RepositoryRestResource`** |

Example setting **`annotated`**:

```properties
spring.data.rest.detection-strategy=annotated
```

When using this strategy, repositories must be explicitly annotated:

```java
@RepositoryRestResource(path = "books", collectionResourceRel = "books")
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

The **`annotated`** strategy is useful when an application has many internal repositories and only a small subset should become HTTP APIs. This is a repository detection rule; it does not replace per-user authentication and authorization.

## 2. Configuring with `application.yml`

The same configuration can be written in YAML:

```yaml
spring:
  data:
    rest:
      base-path: /api
      default-page-size: 25
      max-page-size: 100
      page-param-name: p
      limit-param-name: limit
      sort-param-name: sort
      default-media-type: application/hal+json
      return-body-on-create: true
      return-body-on-update: true
      detection-strategy: annotated
      enable-enum-translation: false
```

Choose **`application.properties`** or **`application.yml`** according to your project's convention. Do not duplicate the same settings in both files. You can place environment-specific settings in **`application-dev.yml`** or **`application-prod.yml`** and activate the corresponding Spring profile.

Spring Boot also supports overrides via environment variables or command-line arguments. For instance, the environment variable **`SPRING_DATA_REST_BASE_PATH`** maps to **`spring.data.rest.base-path`**. This allows keeping a single application artifact while deploying with different base paths per environment.

## 3. What Is `RepositoryRestConfigurer`?

**`RepositoryRestConfigurer`** is the extension interface for configuring Spring Data REST. Spring Boot automatically discovers this bean and invokes its hooks during initialization.

The most commonly used hook is:

```java
void configureRepositoryRestConfiguration(
    RepositoryRestConfiguration config,
    CorsRegistry cors
)
```

- **`RepositoryRestConfiguration`** provides a Java API for base path, pagination, media types, repository detection, projections, and HTTP method exposure.
- **`CorsRegistry`** lets you declare Cross-Origin Resource Sharing (CORS) policies for Spring Data REST endpoints.

In Spring Data REST 3.4 and later, override the two-parameter method shown above. The older single-parameter signature has been replaced in newer versions.

## 4. Java Configuration Example

Assume the project already has a **`Book`** entity and **`BookRepository`**. Create **`RestApiConfiguration.java`**:

```java
package com.example.books.config;

import com.example.books.Book;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setBasePath("/api");
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
        config.setPageParamName("p");
        config.setLimitParamName("limit");
        config.setSortParamName("sort");
        config.setDefaultMediaType(MediaTypes.HAL_JSON);
        config.setReturnBodyOnCreate(true);
        config.setReturnBodyOnUpdate(true);

        config.getExposureConfiguration()
            .forDomainType(Book.class)
            .withItemExposure((metadata, methods) ->
                methods.disable(HttpMethod.DELETE)
            );

        cors.addMapping("/**")
            .allowedOrigins("https://client.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Content-Type", "Authorization");
    }
}
```

**Explanation:**

1. **`@Configuration`** registers this class as a Spring bean. Spring Boot detects beans implementing **`RepositoryRestConfigurer`** without manual invocation.
2. **`setBasePath("/api")`** sets the prefix for repository resources. Clients access the root resource at **`/api/`** and the book collection at **`/api/books`**.
3. **`setDefaultPageSize(25)`** sets the default item count; **`setMaxPageSize(100)`** caps the maximum page size.
4. **`setPageParamName`**, **`setLimitParamName`**, and **`setSortParamName`** rename the query parameters.
5. **`setDefaultMediaType(MediaTypes.HAL_JSON)`** selects HAL JSON when the request specifies no media type.
6. **`setReturnBodyOnCreate`** and **`setReturnBodyOnUpdate`** control whether representations are returned after creation or update.
7. **`getExposureConfiguration()`** customizes HTTP methods per domain type and resource type. In this example, **`DELETE`** is disabled on **`Book`** item resources.
8. **`CorsRegistry`** allows only the specified frontend origin to call the API from a browser using the listed methods and headers.

This Java configuration demonstrates settings equivalent to the properties example while adding CORS rules and HTTP method exposure controls. In a real project, pick a single source of truth for each setting. Avoid configuring the same property in both a config file and a configurer, as it becomes harder to tell which setting takes effect when multiple configurers run.

### Simple Configuration with `withConfig`

If you only need to adjust a few values in **`RepositoryRestConfiguration`**, you can use the factory method instead of creating a separate class:

```java
package com.example.books.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class SimpleRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.setBasePath("/api");
            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        });
    }
}
```

**`withConfig`** creates a **`RepositoryRestConfigurer`** implementation from a lambda. Use this form for concise setups that only need **`RepositoryRestConfiguration`**. If you need CORS configuration or multiple hooks, implementing the interface as a class is easier to read.

## 5. Customizing HTTP Method Exposure

Exported repository methods can expose corresponding HTTP methods. For example, **`save`** can back **`POST`** on the collection and **`PUT`/`PATCH`** on the item. Therefore, hiding a method with an annotation is sometimes insufficient when you want per-method granularity by resource type.

### Disabling Methods at the Repository or Method Level

You can mark a repository as not exported:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
```

Or hide a single method from the REST API:

```java
@RepositoryRestResource(path = "books")
public interface BookRepository extends JpaRepository<Book, Long> {

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);
}
```

The method still exists on the repository for internal code to call, but is not exported as an endpoint. The overridden signature must match the parent interface and your Spring Data version.

### Disabling Methods by Resource Type

Use **`ExposureConfiguration`** when you need to distinguish collection and item resources:

```java
config.getExposureConfiguration()
    .forDomainType(Book.class)
    .withCollectionExposure((metadata, methods) ->
        methods.disable(HttpMethod.POST)
    )
    .withItemExposure((metadata, methods) ->
        methods.disable(HttpMethod.DELETE)
    );
```

With this setup, **`POST`** is disabled on the **`Book`** collection resource, and **`DELETE`** is disabled on **`Book`** item resources. Rules are scoped to the specified domain type. You can also configure association exposure separately to control operations on links.

Do not confuse **`detection-strategy`** with **`ExposureConfiguration`**: the detection strategy decides which repositories are exported; exposure configuration decides which HTTP methods are permitted on exported resources.

## 6. Configuring CORS

CORS allows browsers to send requests from a different origin to the API when the server returns appropriate CORS headers. Example:

```java
cors.addMapping("/**")
    .allowedOrigins("https://client.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
    .allowedHeaders("Content-Type", "Authorization");
```

- **`allowedOrigins`** specifies allowed origins, including scheme, host, and port if present.
- **`allowedMethods`** specifies allowed HTTP methods.
- **`allowedHeaders`** specifies request headers that browser clients may send.

Never use CORS as an authentication or authorization mechanism. CORS is primarily a browser-enforced policy; clients like curl can still call endpoints. Your API still needs Spring Security, authentication, and business-level authorization. If using cookies or credentials from a browser, configure credentials alongside explicit origins; do not combine credentials with wildcard origins.

## 7. Other `RepositoryRestConfigurer` Hooks

Besides **`configureRepositoryRestConfiguration`**, the interface provides hooks for specialized needs:

| Hook | Use Case |
|---|---|
| **`configureValidatingRepositoryEventListener`** | Register `Validator` beans to run before or after repository events such as create and save |
| **`configureConversionService`** | Register converters for domain types or request/response types |
| **`configureHttpMessageConverters`** | Add or customize `HttpMessageConverter` instances |
| **`configureJacksonObjectMapper`** | Customize how Jackson generates JSON |
| **`configureExceptionHandlerExceptionResolver`** | Customize exception handling and argument resolvers |

You do not need to override every hook. Only add configuration when your application has a specific requirement. For simple validation, Spring Data REST also supports registering `Validator` beans by naming convention tied to events, such as **`beforeCreateBookValidator`** or **`beforeSaveBookValidator`**. Manual registration via **`configureValidatingRepositoryEventListener`** is suitable when you want direct control over validators and events.

When customizing Jackson or message converters, test both HAL representations and your application's other MVC endpoints. Overly broad serialization changes can alter responses that existing clients depend on.

## 8. Verifying Configuration After Startup

After starting the application, check the root resource:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/
```

The root resource should return links for exported repositories. If **`BookRepository`** is exported, clients will find the corresponding relation under **`_links`**.

Read the collection using the renamed query parameters:

```bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/api/books?p=0&limit=10&sort=title,asc"
```

This request asks for the first page, up to 10 results, sorted ascending by **`title`**. Parameter names must match the active configuration.

Test a disabled method:

```bash
curl -i -X DELETE -H "Accept: application/hal+json" http://localhost:8080/api/books/1
```

With the exposure configuration in the example, the **`Book`** item resource does not support **`DELETE`**, and the server returns a method-not-allowed error, typically **`405 Method Not Allowed`**.

You can verify CORS preflight with an **`OPTIONS`** request including **`Origin`** and **`Access-Control-Request-Method`** headers:

```bash
curl -i -X OPTIONS http://localhost:8080/api/books -H "Origin: https://client.example.com" -H "Access-Control-Request-Method: GET"
```

The response should include an **`Access-Control-Allow-Origin`** header matching the allowed origin. Test another origin as well to confirm disallowed origins are rejected.

## 9. Common Configuration Mistakes

| Symptom | Possible Cause | Fix |
|---|---|---|
| Endpoint remains at **`/books`**, not **`/api/books`** | Wrong key, wrong profile, or configurer not detected by Spring | Check **`spring.data.rest.base-path`**, active profile, and configurer bean |
| Repositories disappear after setting **`annotated`** | Repository lacks **`@RepositoryRestResource`** | Add the annotation to repositories that should be exported |
| Internal repositories appear unexpectedly | Detection strategy is too permissive | Choose **`annotated`**, mark **`exported = false`**, and audit each repository |
| Old query parameters stop working | Renamed **`page`**, **`limit`**, or **`sort`** | Update clients to use the new parameter names |
| Clients receive more items than expected | **`max-page-size`** not capped or parameter name misunderstood | Set a reasonable ceiling and inspect live requests |
| Response has no body after POST/PUT | Return-body setting or **`Accept`** header | Check **`return-body-on-create/update`** and send an appropriate `Accept` header |
| Browser reports CORS errors | Origin, method, or header not permitted | Check preflight and **`CorsRegistry`** |
| DELETE is still exported | Exposure rule not applied to the right domain/resource | Check **`forDomainType`**, item/collection exposure, and method annotations |

When multiple settings interact, verify in sequence: active profile, bound property values, whether the **`RepositoryRestConfigurer`** bean is picked up by component scanning, and whether requests hit the right base path and query parameters. Then inspect the HAL response and HTTP status to confirm the policy took effect.

## 10. Choosing the Right Configuration Mechanism

| Need | Appropriate Mechanism |
|---|---|
| Switch base path between dev and prod | **`spring.data.rest.base-path`** in profiles |
| Set default and maximum page size | **`default-page-size`**, **`max-page-size`** |
| Rename query parameters | **`page-param-name`**, **`limit-param-name`**, **`sort-param-name`** |
| Export only annotated repositories | **`detection-strategy=annotated`** |
| Disable DELETE specifically on a domain type's item resource | **`RepositoryRestConfigurer`** and **`ExposureConfiguration`** |
| Allow a frontend origin to call the API | **`RepositoryRestConfigurer`** and **`CorsRegistry`** |
| Add converters or validators | Corresponding hook in **`RepositoryRestConfigurer`** |
| Completely hide a repository or method | **`@RepositoryRestResource(exported = false)`** or **`@RestResource(exported = false)`** |

Prefer properties for simple, environment-friendly settings. Use **`RepositoryRestConfigurer`** when you need Java APIs or custom logic. Combine repository annotations to make exposed resources explicit. Finally, use Spring Security to protect endpoints based on client identity and permissions.

## 11. Practice Exercises

1. Change the base path from **`/api`** to **`/v1`** and confirm the root resource moves accordingly.
2. Set **`default-page-size=10`** and **`max-page-size=30`**. Call the collection without parameters and with **`limit=100`**; observe the actual item count returned.
3. Rename **`page-param-name`** to **`p`** and **`sort-param-name`** to **`order`**, then update the client request.
4. Set **`detection-strategy=annotated`**. Add one unannotated repository and one repository with **`@RepositoryRestResource`**; compare the exported endpoints.
5. Disable **`DELETE`** on the **`Book`** item resource using **`ExposureConfiguration`** and verify the status when calling DELETE.
6. Configure CORS for a frontend origin and send preflight OPTIONS requests with both an allowed origin and a disallowed origin.
7. Test **`return-body-on-create`** set to **`true`** and **`false`**, then compare POST responses with the same `Accept` header.

## References

- [Spring Data REST — Getting Started and Basic Settings](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
