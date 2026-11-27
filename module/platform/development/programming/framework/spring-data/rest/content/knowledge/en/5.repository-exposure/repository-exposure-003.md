# Effect of `public` Visibility and Annotations on Repository Detection in Spring Data REST

## Objectives

After this lesson, you can explain why a Spring Data repository is created as a bean yet may not appear as a REST resource; distinguish the impact of Java visibility (`public` or package-private) from annotations; and choose the right `RepositoryDetectionStrategy` to control which repositories Spring Data REST exposes.

## 1. Distinguishing Repository Creation from REST Resource Exposure

There are two separate steps:

1. **Spring Data recognizes the repository** according to the storage module's configuration (JPA, JDBC, MongoDB, ...), then creates the implementation/proxy for the application to use.
2. **Spring Data REST decides which repositories are exported** as HTTP resources, such as collection resources and item resources.

Therefore, a repository can work normally in services yet not appear in the Spring Data REST API. The cause usually lies in the detection strategy, the interface's access visibility, or the exposure annotation.

In this lesson, the word "public" refers to **the Java type's access visibility**. It does not mean the endpoint is allowed public access on the Internet, nor does it replace authentication or authorization.

## 2. How Does Java Visibility Affect Exposure?

A top-level interface declared `public` can be accessed from other packages:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

If you omit the `public` keyword, the top-level interface has package-private visibility:

```java
interface InternalCustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Spring Data REST treats public repositories as candidates for exposure by default. Package-private repositories are usually excluded from the default list because they are designed for internal use within the package. However, annotations and detection strategies can change this outcome.

Key point: package-private visibility does not turn a repository into a "non-existent" repository. It affects whether Spring Data REST selects the repository to create REST resources.

## 3. Role of `@RepositoryRestResource`

`@RepositoryRestResource` is an annotation placed on a repository interface to customize how Spring Data REST exposes the repository. This annotation can:

- Specify the collection path using `path`.
- Specify the HAL relation name using `collectionResourceRel`.
- Decide whether the resource is exported using `exported` (default is `true`).

Example:

```java
@RepositoryRestResource(
    path = "customers",
    collectionResourceRel = "customers"
)
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

The repository above is exposed under the collection path `/customers` (under the base path if the application configures one). The annotation clearly declares the intent to expose and customizes resource names; it does not replace declaring the repository for the Spring Data module.

To actively hide an entire repository from annotation-aware export mechanisms:

```java
@RepositoryRestResource(exported = false)
public interface AuditRepository
        extends CrudRepository<AuditEntry, Long> {
}
```

When you need to hide a specific query method or CRUD method, use `@RestResource(exported = false)` on that method. This is a different control scope than hiding the entire repository.

## 4. The Four RepositoryDetectionStrategies

Spring Data REST uses `RepositoryDetectionStrategy` to decide which repositories are turned into REST resources. The four standard options mean:

| Strategy | Repository selection rule |
| --- | --- |
| `DEFAULT` | Exposes public repositories or repositories explicitly marked with `@RepositoryRestResource`; the `exported` flag is respected for marked repositories. |
| `ALL` | Exposes all Spring Data repositories, regardless of Java visibility or annotation configuration. |
| `VISIBILITY` | Only exposes repositories with a public interface; annotations do not decide repository selection. |
| `ANNOTATED` | Only exposes repositories marked with `@RepositoryRestResource` (or equivalent REST annotation) and not set to `exported = false`. |

You can compare outcomes assuming all annotations use the default value `exported = true`:

| Repository type | DEFAULT | ALL | VISIBILITY | ANNOTATED |
| --- | --- | --- | --- | --- |
| Public, no annotation | Yes | Yes | Yes | No |
| Package-private, no annotation | No | Yes | No | No |
| Public, with `@RepositoryRestResource` | Yes | Yes | Yes | Yes |
| Package-private, with `@RepositoryRestResource` | Yes | Yes | No | Yes |

The table highlights two easily confused points:

- **Annotations can open the door for package-private repositories** when using `DEFAULT` or `ANNOTATED`.
- **Annotations do not broaden the scope of `VISIBILITY`**: the repository must still be public. Conversely, `ANNOTATED` requires an annotation, so a public repository without a marker will not be exposed.

`ALL` is the broadest option: every Spring Data repository is considered for export. Because this strategy ignores visibility and annotation settings, do not rely on annotations to restrict the list once `ALL` is chosen.

## 5. Choosing a Strategy Based on Goals

- Use **`DEFAULT`** when you want standard behavior: public repositories are exposed automatically, while non-public repositories can be explicitly opted in via annotation.
- Use **`ANNOTATED`** when you want to manage the REST repository list in an opt-in style: only marked repositories become resources.
- Use **`VISIBILITY`** when the project convention is that only public interfaces are exposed, regardless of annotations.
- Use **`ALL`** when you truly want to export every repository, including non-public interfaces. Review the API surface carefully before choosing it.

If the goal is an explicitly allow-listed API, `ANNOTATED` is usually easier to audit: looking at the repository interface immediately reveals which repositories are marked for exposure. With this strategy, `exported = false` lets you exclude a marked repository from the export list.

## 6. Configuring the Detection Strategy

With Spring Boot, you can set the strategy in `application.properties`:

```properties
spring.data.rest.detection-strategy=annotated
```

The corresponding values are `default`, `all`, `visibility`, and `annotated`.

If you need Java configuration, register a `RepositoryRestConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.core.mapping.RepositoryDetectionStrategy.RepositoryDetectionStrategies;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategies.ANNOTATED);
    }
}
```

This configuration changes how Spring Data REST selects repositories for export. It does not replace the storage module's repository scanning configuration.

## 7. Repository-Level vs. Method-Level Annotations

Distinguish two levels of control:

- `@RepositoryRestResource(exported = false)` placed on the interface tells Spring Data REST not to expose that repository.
- `@RestResource(exported = false)` placed on a query method, CRUD method, or eligible association hides that corresponding part of the resource.

Example hiding a query method while keeping the collection resource:

```java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @RestResource(exported = false)
    List<Customer> findByEmail(String email);
}
```

In this example, the repository remains exposed; only the email search endpoint is not exported. If you want to hide the entire repository, put `exported = false` on the interface-level annotation.

## 8. How to Troubleshoot When a Repository Does Not Appear

When a repository has no link in the REST API, check in this order:

1. **Has the repository been recognized by the Spring Data module?** Check whether the interface extends an appropriate repository, matches the storage module, and sits within the scan scope.
2. **Is the interface public?** If package-private, `DEFAULT` and `VISIBILITY` may not select it without a matching annotation.
3. **Which strategy is active?** Read `spring.data.rest.detection-strategy` or the `RepositoryRestConfigurer` setup; do not infer solely from a single annotation.
4. **Is the annotation placed at the right level?** `@RepositoryRestResource` controls the repository; `@RestResource` can control a method or association.
5. **Is a base path configured?** The resource may live under a different prefix instead of root `/`.

You can send `GET /` (or the configured base path) and inspect the HAL links to verify which collection resources are exposed. If the collection resource is completely missing, check the detection strategy and repository recognition. If the collection exists but an operation returns `405 Method Not Allowed`, check whether the corresponding method exists and whether it is hidden via `@RestResource(exported = false)`.

Finally, never use Java visibility or detection strategies as a security mechanism. They determine which resources are generated; user permissions to invoke endpoints must be protected separately using Spring Security and proper authorization rules.

## Summary

- `public` affects whether a repository is selected under `DEFAULT` or `VISIBILITY`.
- `@RepositoryRestResource` lets you explicitly declare a repository to expose and customize the resource.
- `DEFAULT` combines public visibility with annotations; `ALL` ignores both; `VISIBILITY` checks only `public`; `ANNOTATED` requires an annotation.
- `@RepositoryRestResource` controls the repository level; `@RestResource` can hide specific methods or associations.
- Exporting a repository does not mean the endpoint is protected by authentication and authorization.

## References

- [Spring Data REST — Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [RepositoryDetectionStrategy.RepositoryDetectionStrategies — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/RepositoryDetectionStrategy.RepositoryDetectionStrategies.html)
- [@RepositoryRestResource — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
