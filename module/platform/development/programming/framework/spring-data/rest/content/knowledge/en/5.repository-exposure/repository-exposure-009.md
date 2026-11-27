# ExposureConfiguration: Restricting HTTP Methods Globally or by Domain Type

## 1. What Problem Does ExposureConfiguration Solve?

Spring Data REST automatically exports Spring Data repositories as REST resources. From repository methods, the framework determines which HTTP methods can be used on each resource type. In many applications, the default rules suffice. However, some APIs require finer-grained policies: for example, disallowing PATCH on all item resources, while prohibiting only the `User` resource from being created via PUT.

`ExposureConfiguration` is the configuration API for adjusting the set of HTTP methods supported by Spring Data REST. You can register filters that apply globally or scope filters to a specific domain type using `forDomainType(Class)`. This API was introduced in Spring Data REST 3.1.

This configuration applies to repository resources managed by Spring Data REST. It does not automatically govern custom Spring MVC controllers outside the repository export mechanism.

## 2. Default HTTP Method Rules

Before adding filters, Spring Data REST already determines supported methods based on the operations the repository can perform.

For example:

- If a repository does not provide a `delete(…)` operation, the corresponding item resource will not support HTTP `DELETE`.
- If a repository method must be declared strictly for internal use, you can mark it with `@RestResource(exported = false)` so it produces no corresponding HTTP exposure.
- The `save(…)` method can back multiple operations: `POST` on the collection resource and `PUT` or `PATCH` on the item resource. Consequently, hiding `save(…)` with `exported = false` can remove several HTTP methods at once.

When you need to adjust individual HTTP methods while keeping the repository method available for other operations, use `ExposureConfiguration`.

## 3. Obtaining ExposureConfiguration in Spring Data REST Configuration

Applications access this object via `RepositoryRestConfiguration.getExposureConfiguration()`. A common approach is registering a bean implementing `RepositoryRestConfigurer` and adding filters in the configuration callback.

The following example combines one global rule with two per-domain-type rules:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.core.mapping.ExposureConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestExposureConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config, CorsRegistry cors) {

        ExposureConfiguration exposure = config.getExposureConfiguration();

        // Global rule: disallow PATCH on all item resources.
        exposure.disablePatchOnItemResources();

        // Only the User domain type cannot create new items using PUT.
        exposure.forDomainType(User.class)
                .disablePutForCreation();

        // Only Order item resources do not support DELETE.
        exposure.forDomainType(Order.class)
                .withItemExposure((metadata, httpMethods) ->
                        httpMethods.disable(HttpMethod.DELETE));
    }
}
```

In this example:

- `disablePatchOnItemResources()` is a global shortcut: it applies to item resources of every repository exported by Spring Data REST.
- `forDomainType(User.class)` scopes the subsequent filter to the aggregate belonging to domain type `User`.
- `forDomainType(Order.class)` scopes the subsequent filter to the aggregate belonging to domain type `Order`.

`User.class` and `Order.class` are entity/domain classes, not repository interfaces or URL strings. The configuration bean must be discovered by Spring, for example through component scanning.

## 4. Three Customizable Resource Groups

Spring Data REST distinguishes three resource groups. Each group has its own filter registration method:

| API | Scope | Example Purpose |
|---|---|---|
| `withCollectionExposure(filter)` | Collection resource, e.g., `/api/users` | Restrict resource creation methods on collections |
| `withItemExposure(filter)` | Item resource, e.g., `/api/users/42` | Restrict read, replace, update, or delete methods on items |
| `withAssociationExposure(filter)` | Association resource, e.g., links under `/api/users/42/roles` | Restrict methods to read or modify relationships |

The first two filters use `ExposureConfigurer.AggregateResourceHttpMethodsFilter`; the association filter uses `ExposureConfigurer.AssociationResourceHttpMethodsFilter`.

Filters receive the resource metadata and a `ConfigurableHttpMethods` instance. This object lets you modify the set of supported methods:

```java
exposure.withCollectionExposure((metadata, httpMethods) ->
        httpMethods.disable(HttpMethod.POST));

exposure.withItemExposure((metadata, httpMethods) ->
        httpMethods.disable(HttpMethod.PATCH, HttpMethod.DELETE));

exposure.withAssociationExposure((metadata, httpMethods) ->
        httpMethods.disable(HttpMethod.PUT));
```

These are examples of global filters because they are registered directly on `ExposureConfiguration`. To scope a filter to a single domain type, register it via `forDomainType`:

```java
exposure.forDomainType(User.class)
        .withItemExposure((metadata, httpMethods) ->
                httpMethods.disable(HttpMethod.PATCH));
```

Filters receive `ConfigurableHttpMethods`, which provides `disable(HttpMethod...)` and `enable(HttpMethod...)`. They adjust the resource's method set based on existing metadata; adding a method to the exposure set does not automatically supply missing repository functionality.

## 5. Distinguishing Shortcuts Related to PUT and PATCH

`ExposureConfiguration` provides three commonly used shortcuts. They differ in scope:

| Method | Meaning |
|---|---|
| `disablePutForCreation()` | Disallows using HTTP `PUT` to create a new item resource |
| `disablePutOnItemResources()` | Disables HTTP `PUT` support on item resources |
| `disablePatchOnItemResources()` | Disables HTTP `PATCH` support on item resources |

Example:

```java
ExposureConfiguration exposure = config.getExposureConfiguration();

exposure.disablePutForCreation();
exposure.disablePutOnItemResources();
exposure.disablePatchOnItemResources();
```

All three lines above are global rules. Note that `disablePutForCreation()` is narrower: it specifically targets creating a new item with PUT. If the requirement is to disable PUT on item resources in general, use `disablePutOnItemResources()`.

`disablePutForCreation()` is also available on `ExposureConfigurer`, so it can be scoped by domain type:

```java
exposure.forDomainType(User.class)
        .disablePutForCreation();
```

Meanwhile, `disablePutOnItemResources()` and `disablePatchOnItemResources()` are shortcuts on `ExposureConfiguration`. To apply equivalent rules to a specific domain type, register a filter via `forDomainType(...).withItemExposure(...)`.

## 6. Example Outcomes by Scope

Suppose an application has the endpoints:

- `/api/users` and `/api/users/42`
- `/api/orders` and `/api/orders/7`
- `/api/users/42/roles`

With the configuration from Section 3, the policy reads as follows:

| Resource | Restricted HTTP Method | Scope |
|---|---|---|
| All item resources, including User and Order | `PATCH` | Global |
| User item resource | `PUT` on creation | User only |
| Order item resource | `DELETE` | Order only |
| Collection resource | No additional filter in example | Default exposure |
| Association resource | No additional filter in example | Default exposure |

If you add:

```java
exposure.forDomainType(User.class)
        .withAssociationExposure((metadata, httpMethods) ->
                httpMethods.disable(HttpMethod.PUT));
```

then the association filter applies only to association resources for properties owned by domain type `User`. It does not automatically apply to `Order` associations.

## 7. Working Alongside @RestResource, CORS, and Spring Security

These three mechanisms solve different problems:

**`@RestResource(exported = false)`**

Use when you want to hide a repository method or resource from HTTP exposure. This is useful when a method is strictly internal. However, if a method like `save(…)` backs multiple HTTP methods, hiding it can have broader effects than intended. `ExposureConfiguration` lets you precisely choose which collection, item, or association method to adjust.

**CORS**

CORS determines whether a browser from another origin is allowed to send requests with specific HTTP methods and headers. CORS does not replace Spring Data REST exposure configuration. Allowing `PUT` in `CorsRegistry` does not automatically restore a PUT operation disabled in `ExposureConfiguration`.

**Spring Security**

`ExposureConfiguration` decides which HTTP methods Spring Data REST supports on repository resources. It does not authenticate users, authorize by role, or replace authorization. If only certain users are allowed to call `DELETE`, use Spring Security to control callers; if the API must never offer `DELETE` for that resource, adjust exposure.

## 8. How to Troubleshoot When an HTTP Method Does Not Work

When a request produces an unexpected result, check in order:

1. Determine whether the URL is a collection, item, or association resource.
2. Verify whether the repository provides the corresponding operation; for example, `DELETE` typically requires an appropriate delete operation.
3. Look for `@RestResource(exported = false)` annotations on the repository or related methods.
4. Confirm the `RepositoryRestConfigurer` bean is detected by Spring and the configuration callback actually executes.
5. Check whether the filter was registered globally or via the right `forDomainType(Domain.class)`.
6. Verify the filter modifies the right resource group: collection, item, or association.
7. Also check CORS and Spring Security if the request comes from a browser or depends on caller permissions.

Write integration tests for each key resource type and method. For example, if the goal is to forbid `PATCH` only for User, verify `PATCH /api/users/42` is rejected according to policy while `PATCH` on another domain type retains its expected behavior. The final status code also depends on routes, handlers, and application security configuration, so verify actual behavior rather than assuming a single error code.

## 9. Key Takeaways

`ExposureConfiguration` is the class for adjusting Spring Data REST HTTP methods across three resource levels: collection, item, and association. Filters registered directly on the configuration apply globally; filters registered via `forDomainType(Class)` are scoped to aggregates and associations belonging to that domain type. Use shortcuts when common policies already exist, and use lambda filters when you need to select exact methods to enable or disable.

## References

- [Spring Data REST — Customizing supported HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Javadoc — ExposureConfiguration](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/ExposureConfiguration.html)
- [Javadoc — ExposureConfigurer](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/ExposureConfigurer.html)
- [Javadoc — ConfigurableHttpMethods](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/ConfigurableHttpMethods.html)
- [Javadoc — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
