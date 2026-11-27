# Spring Boot Auto-Configuration and Repository Discovery Conditions in Spring Data REST

Spring Data REST does not scan every interface in a project and turn it into an endpoint automatically. A working API goes through multiple configuration layers: dependencies must be on the classpath, Spring Boot must detect the web application type and storage technology, Spring Data must scan repository interfaces and create repository beans, and only then does Spring Data REST decide which repositories are exported as HTTP resources.

The most important distinction is between **repository discovery** and **repository exposure**:

- **Discovery:** Spring Data finds interfaces in configured packages, identifies the corresponding store, and registers proxy beans in the `ApplicationContext`.
- **Exposure:** Spring Data REST selects among discovered repository beans to generate collection resources, item resources, search resources, and HTTP endpoints.

A repository bean can be created by Spring Data without being exposed by Spring Data REST. Conversely, if the repository bean does not exist yet, changing Spring Data REST's detection strategy will not make endpoints appear.

## 1. Required Dependencies

Spring Data REST requires Spring Data REST's MVC integration and a specific Spring Data repository module. For a JPA application, you typically add both the Data REST starter and the Data JPA starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")

    runtimeOnly("org.postgresql:postgresql")
}
~~~

This example uses Gradle Kotlin DSL and PostgreSQL. You can replace JPA with another store, such as:

| Data Store Type | Common Spring Data Starter |
|---|---|
| JPA / relational database | `spring-boot-starter-data-jpa` |
| MongoDB | `spring-boot-starter-data-mongodb` |
| JDBC | `spring-boot-starter-data-jdbc` |
| Redis | `spring-boot-starter-data-redis` |
| Elasticsearch | `spring-boot-starter-data-elasticsearch` |

Exact starter names and versions depend on your Spring Boot release. Let Spring Boot dependency management handle compatible versions instead of mixing different Spring Data versions manually.

Each dependency serves a distinct role:

- The store starter provides the Spring Data module and infrastructure to create repositories for that store.
- The JDBC driver or store client enables the application to connect to the storage system.
- The Data REST starter provides the REST integration layer to publish repositories over Spring MVC.
- Spring Boot auto-configuration wires the components together when the corresponding conditions are satisfied.

Having only `spring-boot-starter-data-jpa` allows JPA repositories to work as application beans, but does not automatically expose them as REST endpoints. Having only `spring-boot-starter-data-rest` is also insufficient if no store repositories are registered.

## 2. Spring Boot Auto-Configuration Operates Conditionally

`@SpringBootApplication` includes `@EnableAutoConfiguration`. Spring Boot evaluates the classpath, application type, existing beans, and properties to decide which auto-configurations apply. Auto-configuration is not a fixed setup enabled unconditionally; each configuration can use conditions such as:

- `@ConditionalOnClass`: applies only when required classes are present on the classpath.
- `@ConditionalOnMissingBean`: applies only when a corresponding custom bean is not already defined.
- `@ConditionalOnBean`: applies only when dependent beans already exist.
- `@ConditionalOnProperty`: applies only when a property has a matching value.
- `@ConditionalOnWebApplication`: applies only to a matching web application type, such as Servlet or Reactive.

When a condition is not met, Spring Boot skips that auto-configuration. This is often why a feature is inactive even though its dependency appears in the build file.

### 2.1. Store Repository Auto-Configuration

For JPA, Spring Boot detects Spring Data JPA on the classpath and configures repository infrastructure accordingly. This process requires related components such as the JPA API, `EntityManager`, `EntityManagerFactory`, and a validly configured `DataSource`.

For MongoDB, Boot uses the MongoDB module and corresponding Mongo connection components. Redis, JDBC, Elasticsearch, and other stores each have their own auto-configuration.

Store auto-configuration is responsible for locating repository interfaces and registering repository proxy beans. The default scan location usually comes from the registered auto-configuration packages, typically the package containing the main class annotated with `@SpringBootApplication` and its subpackages.

### 2.2. Spring Data REST Auto-Configuration

Spring Data REST has its own auto-configuration for the MVC integration layer. In Spring Boot 3.5.x, this class is:

~~~java
org.springframework.boot.autoconfigure.data.rest.RepositoryRestMvcAutoConfiguration
~~~

The Boot 3.5 Javadoc describes the main conditions:

~~~java
@ConditionalOnWebApplication(type = SERVLET)
@ConditionalOnMissingBean(RepositoryRestMvcConfiguration.class)
@ConditionalOnClass(RepositoryRestMvcConfiguration.class)
@EnableConfigurationProperties(RepositoryRestProperties.class)
@Import(RepositoryRestMvcConfiguration.class)
~~~

Meaning:

1. The application must be a Servlet web application. This is a Spring MVC integration; running a pure WebFlux application does not satisfy this Servlet condition.
2. Spring Data REST's `RepositoryRestMvcConfiguration` class must be on the classpath.
3. If the application already defines a `RepositoryRestMvcConfiguration` bean, default auto-configuration backs off to avoid duplicate configuration.
4. Properties under the `spring.data.rest` prefix are bound to Spring Data REST configuration.
5. Spring Data REST's MVC configuration is imported to register the REST infrastructure.

Starting in Spring Boot 4, the auto-configuration class name and package changed. The corresponding class is:

~~~java
org.springframework.boot.data.rest.autoconfigure.DataRestAutoConfiguration
~~~

Boot 4 continues to check for a Servlet web application, Spring Data REST classes on the classpath, and the absence of a custom `RepositoryRestMvcConfiguration`; it binds `DataRestProperties` and imports Spring Data REST's MVC configuration. Therefore, when reading the Condition Evaluation Report or Javadoc, always check against the exact major version you are running. Do not copy auto-configuration class names from Boot 3 into Boot 4.

Keep in mind: REST auto-configuration prepares the HTTP layer and REST settings. It does not replace repository scanning by JPA, MongoDB, or other store modules.

## 3. Pipeline from Dependencies to Endpoints

The initialization sequence can be visualized as follows:

~~~mermaid
flowchart TD
    A["Dependencies on classpath"] --> B["Spring Boot detects store"]
    B --> C["Store repository auto-configuration"]
    C --> D["Scan repository packages"]
    D --> E["Create repository proxy bean"]
    F["Data REST starter and Servlet MVC"] --> G["Data REST auto-configuration"]
    G --> H["RepositoryRestMvcConfiguration"]
    E --> I["Repository detection and export rules"]
    H --> I
    I --> J["REST resources and HTTP endpoints"]
~~~

Step-by-step breakdown:

1. Dependencies place Spring Data classes, store implementations, and Spring Data REST on the runtime classpath.
2. Spring Boot evaluates conditions to enable the corresponding auto-configurations.
3. The store module searches for repository interfaces in configured packages.
4. Spring Data creates proxy beans for repositories. These proxies execute CRUD or query operations via the store implementation.
5. Spring Data REST registers MVC infrastructure and reads repository metadata from Spring Data.
6. The repository detection strategy determines which repositories are exposed.
7. Exported repositories become HTTP resources; paths and relations can use default conventions or custom annotations.

Steps 3–4 and steps 5–6 are two independent gates. When debugging, determine whether the failure lies in repository bean creation or in an existing repository not being exported.

## 4. Conditions for Spring Data to Discover a Repository Interface

A Spring Data repository is typically an interface extending `org.springframework.data.repository.Repository` directly or via a store-specific interface. For example:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

`JpaRepository` extends Spring Data's general repository contracts and adds JPA-specific operations. Spring Data recognizes this interface, creates a proxy bean, and supplies a store-appropriate implementation.

You do not have to write implementation classes for each repository. Spring Data creates proxies when the `ApplicationContext` initializes and delegates method calls to the underlying execution engine.

### 4.1. Interfaces Must Reside in Scanned Packages

Suppose you have this package structure:

~~~text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── Product.java
│   └── ProductRepository.java
└── category
    ├── Category.java
    └── CategoryRepository.java
~~~

Main class:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Because the main class is in `com.example.catalog`, subpackages such as `com.example.catalog.product` and `com.example.catalog.category` fall under the default auto-configuration package scope. Spring Boot can use this scope to locate repositories and entities.

If the main class is placed in `com.example.bootstrap` while repositories live in `com.example.catalog.product`, the repositories may fall outside the default package scope. In that case, you must configure the scan scope explicitly.

### 4.2. Using `@EnableJpaRepositories` to Specify Scan Scope

When you need explicit control over repository packages, use the store-specific annotation:

~~~java
package com.example.bootstrap;

import com.example.catalog.product.ProductRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication
@EnableJpaRepositories(
    basePackageClasses = ProductRepository.class
)
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`basePackageClasses` derives the package from the specified class and is safer than hardcoding package strings. You can use `basePackages` when multiple packages are needed.

Store-specific annotations include:

- `@EnableJpaRepositories`
- `@EnableMongoRepositories`
- `@EnableJdbcRepositories`
- `@EnableRedisRepositories`

In simple Spring Boot applications, you typically do not need to add these annotations manually because store auto-configuration already scans the auto-configuration package. Use them only when overriding the default scan scope or structure.

### 4.3. Repository Scanning and Entity Scanning Are Separate

For JPA, discovering a repository interface does not guarantee that the entity is managed.

- `@EnableJpaRepositories` specifies where to look for repository interfaces.
- `@EntityScan` specifies where to look for entities to include in the persistence unit.
- `@ComponentScan` looks for components such as `@Service`, `@Controller`, and `@Configuration`.

If the repository is discovered while the entity lies outside the entity scan scope, the application may fail when creating the `EntityManagerFactory` or report an unmanaged domain type. Fixing repository scanning does not substitute for configuring entity scanning.

In Spring Boot's default package layout, repositories and entities located under the main application package are automatically detected. When splitting modules or packages, configure both scopes as needed.

## 5. Domain Type and Repository Type

A repository must identify its domain type and ID type. There are two common ways to do this.

### 5.1. Extending a Spring Data Interface

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

`Product` is the domain type; `Long` is the ID type. Inherited methods from `JpaRepository` provide CRUD, pagination, sorting, and common JPA operations.

Commonly used interfaces:

| Interface | Purpose |
|---|---|
| `Repository<T, ID>` | Marker and root of the Spring Data repository contract |
| `CrudRepository<T, ID>` | Basic CRUD operations |
| `ListCrudRepository<T, ID>` | CRUD returning `List` for multi-element methods |
| `PagingAndSortingRepository<T, ID>` | Pagination and sorting |
| `JpaRepository<T, ID>` | Repository contract tailored for JPA |
| `MongoRepository<T, ID>` | Repository contract tailored for MongoDB |

Not every repository needs to extend `JpaRepository`. You can choose a narrower interface to restrict the operations the application exposes or uses.

### 5.2. Using `@RepositoryDefinition`

If you prefer not to extend a standard repository interface, you can declare the domain type and ID type via annotation:

~~~java
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(domainClass = Product.class, idClass = Long.class)
public interface ProductRepository {
    Optional<Product> findById(Long id);
    List<Product> findByNameContaining(String name);
}
~~~

The interface must still sit inside the repository scan scope and follow the rules of the target store. `@RepositoryDefinition` does not enable Spring Data REST on its own; it only declares the repository contract for Spring Data to recognize.

### 5.3. Preventing Registration of Base Interfaces as Business Repositories

When building a shared base interface, mark it with `@NoRepositoryBean`:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);
}
~~~

Sub-interface with concrete domain types:

~~~java
public interface ProductRepository
        extends BaseRepository<Product, Long> {
}
~~~

`@NoRepositoryBean` tells Spring Data not to create a repository proxy directly for the base interface. Omitting this annotation on a generic interface without concrete domain types can cause Spring Data to attempt creating an invalid bean or throw a startup error.

## 6. Selecting the Right Store with Multiple Spring Data Modules

When only one store module is present, Spring Data can infer the store for a repository from that module. When multiple modules exist on the classpath, Spring Data switches to strict repository configuration mode to determine which repository belongs to which store.

For example, an application using both Spring Data JPA and Spring Data MongoDB:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}

public interface AuditRepository
        extends MongoRepository<AuditDocument, String> {
}
~~~

Store-specific interfaces such as `JpaRepository` and `MongoRepository` give clear signals about the store. Domain types can also be identified via store annotations such as `@Entity` for JPA and `@Document` for MongoDB.

An interface extending only `CrudRepository` may not carry enough information for Spring Data to assign a store when multiple modules are active. In that situation:

- Prefer store-specific repository interfaces.
- Annotate domain types appropriately for their storage technology.
- Use `@EnableJpaRepositories` and `@EnableMongoRepositories` to separate packages explicitly.
- Avoid ambiguous repository interfaces that multiple stores could claim.

Example with separate package configurations:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = JpaOrderRepository.class
)
@EnableMongoRepositories(
    basePackageClasses = MongoAuditRepository.class
)
public class RepositoryConfiguration {
}
~~~

You can enable or disable auto-configured repositories per module using properties under `spring.data.*.repositories.enabled` when supported by the module. When using multiple stores, consult the property metadata for your exact Spring Boot version.

## 7. Having a Repository Bean Does Not Guarantee REST Export

After Spring Data registers a repository bean, Spring Data REST uses `RepositoryDetectionStrategy` to decide which repositories are exposed as HTTP resources.

By default, Spring Data REST uses the `DEFAULT` strategy. This strategy exposes public repository interfaces or repositories annotated with `@RepositoryRestResource`, while respecting the annotation's `exported` flag.

Four common strategies:

| Strategy | Exposure Rule |
|---|---|
| `DEFAULT` | Exposes public repositories or those annotated with `@RepositoryRestResource`, respecting `exported=false` |
| `ALL` | Considers all repositories regardless of visibility or annotations |
| `VISIBILITY` | Exposes only public repository interfaces |
| `ANNOTATED` | Exposes only repositories marked with the appropriate annotation and not set to `exported=false` |

The difference between `DEFAULT` and `VISIBILITY` is notable: a package-private repository can still be exposed when explicitly annotated under `DEFAULT`, whereas `VISIBILITY` considers only public interfaces.

You can configure the strategy in `application.yml`:

~~~yaml
spring:
  data:
    rest:
      detection-strategy: annotated
      base-path: /api
~~~

With the `annotated` strategy, repositories must be explicitly annotated:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

If a repository is strictly internal, you can disable export:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
~~~

You can also hide individual query methods or associations using `@RestResource(exported = false)` on the corresponding member. This is an exposure rule at the Spring Data REST layer; it does not prevent Spring Data from creating the repository bean for internal code.

Avoid choosing `ALL` casually in applications that have internal repositories, as it widens the surface area considered for exposure. Pick a strategy matching your API contract and verify export flags in your active version.

## 8. Customizing Spring Data REST via Properties and Configurers

Properties under the `spring.data.rest` prefix adjust REST behavior. Example:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
      detection-strategy: annotated
      default-page-size: 20
      max-page-size: 100
~~~

In this example:

- `base-path` sets the prefix for endpoints.
- `detection-strategy` selects the repository exposure rule.
- `default-page-size` sets the default number of items per page.
- `max-page-size` caps the maximum number of items per page.

Exact property names can vary across releases. Consult configuration metadata and documentation for your exact Spring Boot version, especially across major version upgrades.

When custom logic beyond properties is needed, register a `RepositoryRestConfigurer` bean:

~~~java
@Configuration
public class RestRepositoryConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return new RepositoryRestConfigurer() {
            @Override
            public void configureRepositoryRestConfiguration(
                    RepositoryRestConfiguration config,
                    CorsRegistry cors) {

                config.setBasePath("/api");
            }
        };
    }
}
~~~

This is the designated extension point for Spring Data REST configuration. Spring Boot continues to supply auto-configuration while applying your custom configurer. Prefer `RepositoryRestConfigurer` and properties over importing `RepositoryRestMvcConfiguration` directly.

If you declare `RepositoryRestMvcConfiguration` yourself, `@ConditionalOnMissingBean` causes default REST auto-configuration to back off. Your application then becomes responsible for ensuring all required configuration components are registered.

## 9. Checking Whether a Repository Is Discovered and Exported

An effective diagnostic approach splits troubleshooting into two questions.

### 9.1. Does the Repository Bean Exist?

Check:

- Is the store dependency on the runtime classpath?
- Is store auto-configuration enabled?
- Does the interface extend `Repository` or use `@RepositoryDefinition`?
- Is the repository's package within the scan scope?
- Does the domain type belong to the corresponding store and is it managed?
- Is the repository marked with `@NoRepositoryBean`?
- Are multiple store modules making the repository ambiguous?

If the application fails to create the repository bean, the issue lies in discovery or store infrastructure. Changing `spring.data.rest.detection-strategy` will not fix it.

### 9.2. Is the Repository Bean Exported by REST?

If the repository bean exists but endpoints do not appear, check:

- Are the Data REST starter and `RepositoryRestMvcConfiguration` on the runtime classpath?
- Is the application a Servlet web application?
- Was `RepositoryRestMvcConfiguration` replaced by manual configuration, causing Boot auto-configuration to back off?
- Does `spring.data.rest.detection-strategy` exclude this repository?
- Does the repository have `@RepositoryRestResource(exported = false)`?
- Was auto-configuration excluded via `@EnableAutoConfiguration` or `spring.autoconfigure.exclude`?
- Was the base path changed to `/api` or another prefix?

### 9.3. Enabling Auto-Configuration Debug Output

You can start the application with `--debug`:

~~~bash
./gradlew bootRun --args="--debug"
~~~

Or when running a JAR:

~~~bash
java -jar build/libs/catalog.jar --debug
~~~

Spring Boot prints the Condition Evaluation Report, showing which auto-configurations matched and which were skipped along with reasons. When reading the report, look for entries related to your active store and Spring Data REST.

You can also raise logging levels for repository configuration:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
    org.springframework.data.rest: DEBUG
~~~

Logs reveal scanned packages, registered repositories, and REST mapping details. Exact logger names and useful log levels may vary by version.

### 9.4. Calling the Root Resource to Verify the API

If the base path is `/api`, send a request:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/
~~~

The root resource typically returns relations pointing to exported repositories. If a repository does not appear here, revisit discovery and exposure checks. If it appears in the root resource but collection requests fail, inspect routing, security, store connectivity, and data state.

## 10. Common Scenarios

| Symptom | Possible Cause | How to Check |
|---|---|---|
| App runs, but no REST repository endpoints exist | Missing Data REST starter or REST auto-configuration conditions not met | Check runtime classpath, Servlet MVC, and Condition Evaluation Report |
| Repository interface does not create a bean | Interface outside scan scope or missing store infrastructure | Check packages, store starter, and `@Enable…Repositories` |
| JPA repository found, but entity errors occur | Entity outside entity scan or invalid mapping | Check `@EntityScan`, entity annotations, and persistence unit |
| Bean exists, but no link at root | Repository excluded by detection strategy or `exported=false` | Check `spring.data.rest.detection-strategy` and annotations |
| Public repository still does not appear | REST auto-configuration excluded or app not running Servlet MVC | Check classpath, web conditions, and custom MVC configuration |
| Only some repositories are exported | Differences in visibility, annotations, or packages | Compare repository interfaces and detection strategy |
| Both JPA and Mongo claim a repository | Generic repository or insufficient domain metadata | Use store-specific interfaces and separate packages |
| Endpoint works, but URL differs from expected | Custom `base-path` or `@RepositoryRestResource(path=...)` | Check `spring.data.rest.base-path` and annotations |
| Query method has no `search` link | Method not exported or does not meet query rules | Check method signature and `@RestResource` |
| App fails on startup after adding starter | Missing `DataSource` config, driver, or store bean | Read root cause and failure analysis in startup logs |

## 11. Checklist When Adding a New Repository

Before expecting endpoints to appear, verify in order:

1. Are both the Data REST starter and the appropriate store starter added?
2. Does the runtime classpath include the required driver or client?
3. Does the main class have `@SpringBootApplication` in an appropriate root package?
4. Does the repository interface extend the proper Spring Data interface or use `@RepositoryDefinition`?
5. Is the repository's package within the scan scope?
6. Is the domain type managed by the store and included in entity scanning?
7. If multiple stores are present, does the repository clearly identify its store?
8. Is the repository free of `@NoRepositoryBean`?
9. Does the detection strategy permit exporting this repository?
10. Is `exported=false` absent from annotations, and is auto-configuration not excluded?
11. Does the base path match the URL you are calling?
12. Does the root resource advertise the relation for the collection?

Following this sequence lets you quickly pinpoint whether an endpoint is missing at the repository bean creation stage or at the Spring Data REST exposure stage.

## References

- [Spring Boot Reference — Use Spring Data Repositories](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot How-to — Data Access](https://docs.spring.io/spring-boot/how-to/data-access.html)
- [Spring Boot 3.5 API — RepositoryRestMvcAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/data/rest/RepositoryRestMvcAutoConfiguration.html)
- [Spring Boot 4 API — DataRestAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/rest/autoconfigure/DataRestAutoConfiguration.html)
- [Spring Boot 4 API — DataRestProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/rest/autoconfigure/DataRestProperties.html)
- [Spring Data REST Reference — Getting Started and Detection Strategy](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST Reference — Customizing Repository Exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
