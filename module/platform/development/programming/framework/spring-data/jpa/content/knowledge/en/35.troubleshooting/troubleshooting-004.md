# Not a Managed Type and Entity Scanning Errors

The error `Not a managed type: class ...` typically occurs when Spring Data JPA initializes a repository or when JPA accesses the metamodel. It means the current persistence unit does not recognize the class declared as the repository's domain type as a JPA entity.

For example, a repository declares `JpaRepository<Product, Long>`, yet `Product` has not been registered in the persistence unit. Common causes involve the `@Entity` annotation, package scanning, the `javax.persistence`/`jakarta.persistence` namespace, multiple `EntityManagerFactory` configurations, or the repository's generic type parameter.

Distinguish three independent mechanisms: component scanning discovers Spring beans, repository scanning discovers repository interfaces, and entity scanning registers JPA entity types. One mechanism working properly does not guarantee the other two are configured correctly.

## 1. Understanding the Not a Managed Type Error Message

Example repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Spring Data needs to know that `Product` is a JPA-managed entity in order to build repository metadata. When the corresponding entity cannot be found in the metamodel, the application may report:

```text
IllegalArgumentException: Not a managed type: class com.example.store.Product
```

This message typically occurs while Spring creates repository beans, so the application may fail immediately at startup. In some configurations, the error only appears when the repository or `EntityManager` is used.

The JPA Metamodel is the metadata set that the persistence provider builds from registered entities and mapping types. A managed entity can be found in `EntityManagerFactory.getMetamodel().getEntities()`.

This error does not mean the database is missing a table. It means the Java class is not recognized as an entity in the active persistence unit. Even if the table exists with the right name and schema, the class does not automatically become an entity.

## 2. Checking Whether the Class Is Declared as an Entity

A class used as the domain type of a `JpaRepository` must be annotated with `@Entity` and have an identifier defined via `@Id` or `@EmbeddedId`.

Example with Spring Boot 3 and Jakarta Persistence:

```java
package com.example.store.product.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
package com.example.store.product.repository;

import com.example.store.product.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Common declaration mistakes:

- Having `@Table` without `@Entity`. `@Table` only customizes table mapping for an entity; it does not register a class as an entity.
- Forgetting to declare `@Id` or `@EmbeddedId`.
- Annotating a class with `@Embeddable` or `@MappedSuperclass` and using it directly as a repository domain type. These are not standalone entities.
- Using a DTO, projection, or request class as the first generic type argument of `JpaRepository`.
- The class fails basic entity requirements, such as missing a `public` or `protected` no-arg constructor, or violating JPA entity class rules.

A `@MappedSuperclass` can hold shared mapping fields for subclasses; the concrete subclass must be annotated with `@Entity`. An `@Embeddable` is a value type embedded inside an entity, not a root entity for declaring a `JpaRepository`.

## 3. Checking the javax vs. jakarta Namespace

This is a frequent cause when upgrading Spring Boot or mixing incompatible dependencies.

| Platform | Persistence Namespace |
|---|---|
| Spring Boot 2.x / JPA 2.x | `javax.persistence.*` |
| Spring Boot 3.x / Jakarta Persistence 3.x | `jakarta.persistence.*` |

With Spring Boot 3, entities must use Jakarta annotations:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
```

If an entity still imports:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
```

then a Jakarta-based Hibernate/JPA provider does not treat those `javax.persistence` annotations as mapping annotations to process. The class may look annotated with `@Entity` in source code yet remain unmanaged.

When upgrading:

- Check all imports across entities, mapped superclasses, embeddables, and converters.
- Align versions of Spring Boot, Spring Data JPA, Hibernate, and Jakarta Persistence.
- Do not include both `javax.persistence` and `jakarta.persistence` APIs simultaneously as a temporary workaround.
- Inspect the dependency tree to find legacy libraries pulling in an incompatible JPA API.
- Clean build and re-run the application after fixing imports/dependencies.

With Spring Boot 2, use `javax.persistence` matching the version your application uses. Do not switch namespaces solely because an online example uses Jakarta.

## 4. Checking Spring Boot's Default Base Package

Spring Boot typically determines the root package from the class annotated with `@SpringBootApplication`. Default configuration uses that package as the starting point for component scanning and auto-configuration packages; default JPA entity scanning also relies on this root package.

A convenient layout:

```text
com.example.store
├── StoreApplication.java
├── product
│   ├── domain
│   │   └── Product.java
│   └── repository
│       └── ProductRepository.java
└── customer
    ├── domain
    │   └── Customer.java
    └── repository
        └── CustomerRepository.java
```

Application class:

```java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Because the application class is in `com.example.store`, subpackages like `com.example.store.product.domain` fall within the default scan scope.

If the application class is placed in too deep a package:

```text
com.example.store
├── StoreApplication.java
└── product
    └── domain
        └── Product.java
```

and `StoreApplication` resides in `com.example.store.config`, the package `com.example.store.product.domain` is not a subpackage of `com.example.store.config`. The entity may be missed by default scanning.

Good practice is to place the application class in a common parent package of your modules. Avoid putting the main class in the default package, as the scan scope can become overly broad and hard to control.

## 5. Using @EntityScan When Entities Are Outside the Root Package

If entities reside in another package or a shared module, you can explicitly declare entity packages with `@EntityScan`:

```java
package com.example.application;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;

@SpringBootApplication
@EntityScan(basePackages = {
    "com.example.application.domain",
    "com.example.shared.persistence.entity"
})
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

You can use `basePackageClasses` to avoid hard-coding package names:

```java
@EntityScan(basePackageClasses = {
    Product.class,
    SharedEntityMarker.class
})
```

When using `basePackageClasses`, Spring takes the packages of the specified classes as the packages to scan. A marker class can be an empty class placed inside the shared entity package.

Note: `@EntityScan` controls entity packages for Spring Boot auto-configuration. If the application manually defines multiple `LocalContainerEntityManagerFactoryBean` instances, configure `setPackagesToScan()` on each corresponding factory; do not assume `@EntityScan` automatically configures manually defined persistence units.

## 6. Distinguishing Entity Scanning from Repository Scanning

Three annotations are often confused:

| Annotation | Purpose |
|---|---|
| `@ComponentScan` | Discovers Spring beans such as `@Service`, `@Component`, `@Controller`, `@Repository`. |
| `@EnableJpaRepositories` | Discovers Spring Data JPA repository interfaces. |
| `@EntityScan` | Declares packages containing entities for Spring Boot JPA auto-configuration. |

For example, `@EnableJpaRepositories` might find `ProductRepository` while `Product` is still unregistered in the JPA metamodel. Spring then locates the repository interface but cannot instantiate the repository because its domain type is not a managed type.

Configuration:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.store.product.repository"
)
@EntityScan(
    basePackages = "com.example.store.product.domain"
)
public class JpaPackageConfig {
}
```

In a simple Spring Boot application, you do not need to add these two annotations if auto-configuration already scans the right packages. Only declare them when you need to expand or restrict the scan scope.

Do not use `@ComponentScan` to fix entity scanning errors. Component scan can discover repository or service beans, but it does not replace registering entities into the persistence unit.

## 7. Checking the Repository's Generic Type

The first type parameter in `JpaRepository<T, ID>` must be a managed entity. Projections/DTOs are query return types, not the repository's domain type.

Incorrect:

```java
public interface ProductRepository
        extends JpaRepository<ProductSummary, Long> {
}
```

If `ProductSummary` is a record or DTO, JPA does not manage it as an entity and may report `Not a managed type`.

Correct:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select new com.example.store.product.api.ProductSummary(
            p.id, p.name
        )
        from Product p
        where p.name like concat('%', :keyword, '%')
        """)
    List<ProductSummary> searchSummaries(
            @Param("keyword") String keyword);
}
```

In this example:

- `Product` is the managed entity and is used as the domain type.
- `ProductSummary` is a DTO projection, used only as the query result type.
- The constructor of `ProductSummary` must match the order and types of the selected expressions.

Also verify that the repository imports the right class. Having two classes with the same name in different packages can cause the repository to point to a DTO or an old entity instead of the intended entity.

## 8. Checking Whether the Class Is on the Runtime Classpath

In multi-module projects, an entity may exist in source code while the runnable application module does not depend on the module containing the entity.

Example:

```text
store-app
├── build.gradle
└── src/main/java/...

shared-domain
├── build.gradle
└── src/main/java/com/example/shared/domain/Customer.java
```

If `store-app` does not declare a dependency on `shared-domain`, the `Customer` entity is absent from the runtime classpath. Adding the package to `@EntityScan` cannot scan a class that is not loaded into the application.

Check:

- Whether the module containing the entity builds successfully.
- Whether the application module declares the proper dependency.
- Whether the dependency is on the runtime classpath rather than only test/compile configurations.
- Whether the deployed artifact contains the latest classes.
- Whether two library versions contain duplicate entity classes or overlapping packages.

With Gradle:

```gradle
dependencies {
    implementation project(":shared-domain")
}
```

With Maven, declare the dependency to the artifact containing the entity in the application's `pom.xml`. After fixing, rebuild and inspect the dependency tree or artifact contents.

## 9. Applications with Multiple EntityManagerFactory Beans

An application may use multiple databases or multiple persistence units. Each `EntityManagerFactory` has its own metamodel and list of managed entities.

An entity scanned by `catalogEntityManagerFactory` is not automatically managed by `billingEntityManagerFactory`.

With manual configuration, bind repositories to the right factory and transaction manager:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.catalog.repository",
    entityManagerFactoryRef = "catalogEntityManagerFactory",
    transactionManagerRef = "catalogTransactionManager"
)
public class CatalogJpaConfig {

    @Bean
    LocalContainerEntityManagerFactoryBean catalogEntityManagerFactory(
            @Qualifier("catalogDataSource") DataSource dataSource,
            JpaVendorAdapter vendorAdapter) {

        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.catalog.domain");
        factory.setJpaVendorAdapter(vendorAdapter);
        return factory;
    }

    @Bean
    PlatformTransactionManager catalogTransactionManager(
            @Qualifier("catalogEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

This example only illustrates the primary wiring; a real configuration also requires datasource beans, vendor adapter, properties, and other supporting beans. Key points:

- `setPackagesToScan()` registers entities for the right factory.
- `entityManagerFactoryRef` binds the repository package to the corresponding factory.
- `transactionManagerRef` selects the transaction manager for that persistence unit.
- Repositories must not be bound to a factory that does not manage their entities.

When using multiple databases, cleanly separate repository and entity packages per persistence unit to avoid confusion.

## 10. Inspecting the JPA Metamodel Directly

Once the application initializes `EntityManagerFactory`, you can check whether an entity is managed:

```java
import jakarta.persistence.EntityManagerFactory;
import org.springframework.stereotype.Component;

@Component
public class JpaMetadataInspector {

    private final EntityManagerFactory entityManagerFactory;

    public JpaMetadataInspector(EntityManagerFactory entityManagerFactory) {
        this.entityManagerFactory = entityManagerFactory;
    }

    public boolean isManagedEntity(Class<?> type) {
        return entityManagerFactory.getMetamodel()
                .getEntities()
                .stream()
                .anyMatch(entityType ->
                        entityType.getJavaType().equals(type));
    }
}
```

If `isManagedEntity(Product.class)` returns `false`, the class is not registered as an entity in the injected factory.

You can print the list of recognized entities:

```java
entityManagerFactory.getMetamodel()
        .getEntities()
        .forEach(entityType ->
                System.out.println(
                        entityType.getName() + " -> "
                        + entityType.getJavaType().getName()));
```

Note when multiple `EntityManagerFactory` beans exist: the injected `EntityManagerFactory` bean must be the factory used by the repository. Injecting the wrong factory yields a metamodel list that does not reflect the persistence unit under inspection.

Another direct check is:

```java
entityManagerFactory.getMetamodel().entity(Product.class);
```

This call returns the entity metadata if the class is managed; otherwise, it throws `IllegalArgumentException`. This is a great check inside integration tests.

## 11. Writing Integration Tests to Catch Scan Errors Early

You can use `@DataJpaTest` to verify entities and repositories are configured properly:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

import jakarta.persistence.EntityManagerFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Autowired
    ProductRepository productRepository;

    @Test
    void productIsManagedByJpa() {
        assertDoesNotThrow(() ->
                entityManagerFactory.getMetamodel()
                        .entity(Product.class));
    }

    @Test
    void repositoryCanPersistProduct() {
        Product saved = productRepository.save(
                new Product("Keyboard"));

        assertDoesNotThrow(() ->
                productRepository.findById(saved.getId()));
    }
}
```

`@DataJpaTest` creates a JPA-focused slice test and typically uses an embedded database if available on the classpath. If the application configures multiple datasources or custom persistence units, tests must load the corresponding configurations. Without an embedded database, Testcontainers or a test datasource configuration can be used.

Do not just verify context startup. Persist and read back an entity to confirm the repository actually uses the right mapping and test database.

## 12. Ordered Diagnostic Workflow

When encountering `Not a managed type`, go step by step:

1. **Read the exact class in the exception.** Confirm which class and package the repository is using and what its first generic type is.
2. **Check entity annotations.** Confirm the class has `@Entity`, has `@Id` or `@EmbeddedId`, and is not just a DTO, `@Embeddable`, or `@MappedSuperclass`.
3. **Check import namespaces.** Boot 2 uses `javax.persistence`; Boot 3 uses `jakarta.persistence`. Align dependencies with Spring/Hibernate.
4. **Check the root package.** Place the application class in a common parent package or declare `@EntityScan`.
5. **Distinguish the two scan types.** Confirm both repository scan and entity scan cover the right packages.
6. **Check runtime dependencies.** If the entity lives in another module, ensure that module is on the runtime classpath.
7. **Check multiple persistence units.** Confirm the repository points to the right `EntityManagerFactory` and that the factory scans the entity package.
8. **Inspect the metamodel.** List managed entities and try `getMetamodel().entity(Product.class)`.
9. **Clean build and run integration tests.** Avoid stale artifacts after fixing packages, imports, or dependencies.

Do not fix this by adding wide sets of packages to component scan or switching every relationship to EAGER. Fix the specific missing scan mechanism or mapping.

## 13. Related Errors Easily Confused

| Message | Common meaning | Where to check |
|---|---|---|
| `Not a managed type: class ...` | Repository domain type is missing from the active factory's metamodel. | `@Entity`, namespace, entity scan, generic type, target factory. |
| `No identifier specified for entity` | Entity has no mapped primary key. | `@Id`, `@EmbeddedId`, inheritance mapping. |
| `Not an entity` or similar entity metadata error | Class is not recognized by provider as an entity or mapping is invalid. | Annotations and persistence unit. |
| `UnknownEntityTypeException` | Provider cannot find the entity type in the queried/operated context. | Entity scan, factory, and actual class. |
| `No property ... found for type ...` | Property name in derived query does not match domain class. | Field/getter names and repository generic type. |
| `UnknownEntityException` in JPQL | Entity name in JPQL does not match the declared entity name. | `@Entity(name = "...")` and name used in JPQL. |

These messages may appear at different stages. Read both the root cause and the specific class in the stack trace instead of relying solely on the first error line.

## 14. Prevention Checklist

- Place entities in clear packages under the application root package or declare `@EntityScan`.
- Use the Persistence namespace matching the Spring Boot version.
- Ensure entities have `@Entity` and a valid primary key.
- Only use entities as the generic domain type of `JpaRepository`; use DTOs/projections as query return types.
- Distinguish `@ComponentScan`, `@EnableJpaRepositories`, and `@EntityScan`.
- Verify runtime dependencies for modules containing entities.
- With multiple databases, bind repositories to the proper entity manager factory and transaction manager.
- Add integration tests verifying the entity is in the metamodel and the repository can persist/read.
- Inspect artifacts and dependency trees after upgrading Spring Boot or Hibernate.

`Not a managed type` is a persistence unit metadata error. Identify the class the repository uses, check annotations and namespaces, and verify package scanning or the associated factory. Once you separate entity scanning from repository scanning, the error is usually isolated quickly without arbitrary changes to mappings or configuration.
