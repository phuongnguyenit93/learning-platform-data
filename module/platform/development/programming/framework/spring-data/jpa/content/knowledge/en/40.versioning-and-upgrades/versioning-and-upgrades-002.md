# Migrating from javax.persistence to jakarta.persistence

When upgrading from the older Java EE/JPA ecosystem to Jakarta EE, the `javax.persistence.*` package changes to `jakarta.persistence.*`. This is a namespace and Java type change, not merely a documentation rename. An entity annotated with `javax.persistence.Entity` is not recognized as an entity by a Jakarta provider looking for `jakarta.persistence.Entity`.

With Spring Data JPA, this migration typically accompanies upgrading Spring Boot 2.x to 3.x, Spring Framework 5 to 6, and Hibernate ORM 5 to 6. You need to upgrade the JDK, framework, provider, dependencies, and mapping configuration together. Do not simply replace imports while keeping older libraries.

## 1. Why did javax.persistence change to jakarta.persistence?

Previously, Java Persistence API (JPA) belonged to the Java EE ecosystem and used the `javax.persistence` namespace. After Java EE was transferred to the Eclipse Foundation, the platform continued development under the name Jakarta EE.

Starting with Jakarta EE 9, Java EE APIs moved to the new `jakarta.*` namespace. Jakarta Persistence continued evolving under the `jakarta.persistence` package.

For example:

| Before | After migration |
|---|---|
| `javax.persistence.Entity` | `jakarta.persistence.Entity` |
| `javax.persistence.Id` | `jakarta.persistence.Id` |
| `javax.persistence.EntityManager` | `jakarta.persistence.EntityManager` |
| `javax.persistence.ManyToOne` | `jakarta.persistence.ManyToOne` |
| `javax.persistence.PersistenceContext` | `jakarta.persistence.PersistenceContext` |
| `javax.persistence.criteria.CriteriaBuilder` | `jakarta.persistence.criteria.CriteriaBuilder` |

Class names and most familiar mapping APIs remain the same, but the package changed. Because Java treats two classes with the same name in different packages as two independent types, a Jakarta provider does not automatically recognize annotations from the old namespace.

This is why a class can still have `@Entity` in source code yet the application reports `Not a managed type`: the imported annotation may be `javax.persistence.Entity` while Hibernate 6 is looking for `jakarta.persistence.Entity`.

## 2. Relationship between Spring Boot, Spring Data JPA, and Hibernate

The namespace migration is usually part of a platform upgrade:

| Generation | Persistence API | Hibernate ORM | Minimum Java |
|---|---|---|---|
| Spring Boot 2.x | JPA 2.x, `javax.persistence` | Hibernate 5.x | Depends on Boot version |
| Spring Boot 3.x | Jakarta Persistence, `jakarta.persistence` | Hibernate 6.x | Java 17 |
| Spring Boot 4.x | Next-generation Jakarta Persistence | Hibernate version managed by Boot | Java 17 or higher depending on Boot line |

This table describes compatible generations, not a full matrix for every minor/patch release. Use the dependency management of the exact Spring Boot version to see which Spring Data JPA, Hibernate, and Jakarta Persistence API versions are managed.

Spring Boot 3 moves to Spring Framework 6 and Jakarta EE 10. Jakarta Persistence 3.1 is the API generation used in the Boot 3.0 line. Later Boot 3.x releases may manage different Hibernate versions; do not infer the provider version solely from the Boot major number.

Spring Data JPA 3.x uses Jakarta Persistence. Hibernate ORM 6 is a provider following the Jakarta namespace. Therefore, when migrating an application to Boot 3+, upgrade the entire corresponding dependency group instead of merely adding a `jakarta.persistence-api` JAR to a Boot 2 project.

## 3. Replacing imports in entities and related classes

Start by migrating all JPA imports in source code:

Before:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.ManyToOne;
import javax.persistence.FetchType;
```

After:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;
```

Example entity after migration:

```java
package com.example.store.product.domain;

import jakarta.persistence.Column;
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

    @Column(nullable = false, length = 120)
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

Not only primary entities need changes. Review all persistence-related classes:

- `@Embeddable`, `@Embedded`, `@EmbeddedId`.
- `@MappedSuperclass` and inherited entities.
- `AttributeConverter` and `@Converter`.
- Entity listeners and lifecycle callbacks.
- `EntityManager`, `EntityManagerFactory`, `PersistenceContext`.
- Criteria API, metamodel, query parameters, and exception types.
- Test fixtures, integration tests, custom repository implementations, and internal libraries.

If a shared-domain module still compiles against `javax.persistence` while the main application uses Hibernate 6, that module must be upgraded or replaced with a Jakarta-compatible version.

## 4. Updating Maven or Gradle dependencies

With Spring Boot 3+, the simplest approach is to use Spring Boot dependency management and the JPA starter:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Gradle:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("org.postgresql:postgresql")
}
```

The starter manages compatible versions of Spring Data JPA, Hibernate, and the Jakarta Persistence API. There is no need to declare `javax.persistence:javax.persistence-api`.

If the project previously declared it directly:

Old Maven:

```xml
<dependency>
    <groupId>javax.persistence</groupId>
    <artifactId>javax.persistence-api</artifactId>
    <version>2.2</version>
</dependency>
```

Remove the old dependency when migrating to Jakarta. Typically the new starter already provides the required API. Only declare `jakarta.persistence-api` directly if the build architecture genuinely needs it and you must use the exact version compatible with the provider/framework.

Avoid these situations:

- Keeping both `javax.persistence-api` and `jakarta.persistence-api` simultaneously.
- Upgrading Hibernate alone to 6 while keeping an older Spring Data JPA that uses `javax.persistence`.
- Forcing a Hibernate version outside dependency management without verifying compatibility.
- Using an old custom repository or auditing library that only supports JPA 2.x.

Inspect the dependency tree to detect old APIs or providers pulled in transitively.

Maven:

```bash
mvn dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

If multiple versions appear together, inspect which dependency pulls them in and update the root dependency or exclude the incompatible artifact. Do not exclude a JAR based only on package name; verify whether that library actually belongs to the old API or a still-valid Java SE API.

## 5. Do not replace every javax package with jakarta

This is a common migration mistake. Only Java EE/Jakarta EE APIs whose namespaces moved need to be changed. Not every package starting with `javax.` became `jakarta.`.

Examples of Java SE packages that remain unchanged:

| Package still in use | Role |
|---|---|
| `javax.sql.DataSource` | JDBC datasource |
| `javax.crypto` | Cryptography |
| `javax.naming` | Naming and directory services |
| `javax.net` | Networking |
| `javax.management` | JMX management |
| `javax.xml.parsers` | XML parsing |
| `javax.annotation.processing` | Java compiler annotation processing |

Some other Java EE APIs have new namespaces, for example:

| Old API | Jakarta namespace |
|---|---|
| `javax.persistence` | `jakarta.persistence` |
| `javax.transaction` (JTA) | `jakarta.transaction` |
| `javax.validation` | `jakarta.validation` |
| `javax.servlet` | `jakarta.servlet` |
| `javax.ws.rs` | `jakarta.ws.rs` |
| `javax.inject` | `jakarta.inject` |
| `javax.annotation` (Common Annotations API) | `jakarta.annotation` |

Distinguish JTA's `javax.transaction.Transactional` from Spring's `org.springframework.transaction.annotation.Transactional`. The Spring annotation keeps its package and continues to work in Spring Boot 3 applications. Do not change the Spring annotation to a Jakarta package.

Similarly, `javax.sql.DataSource` remains a Java SE JDBC API. Do not change this import to `jakarta.sql.DataSource`, because that package does not exist.

Do not blindly run a project-wide search-and-replace for `javax.`. Identify which APIs changed namespaces, check which artifacts provide them, and update only the required imports.

## 6. Updating persistence.xml and orm.xml configurations

Spring Boot usually configures the persistence unit via auto-configuration, so many applications do not have a `persistence.xml`. However, applications using manual JPA bootstrap or XML mapping must update descriptor namespaces and versions.

Example `persistence.xml` for Jakarta Persistence 3.1:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="store">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.store.product.domain.Product</class>
    </persistence-unit>
</persistence>
```

The provider name in the example is Hibernate. If the application uses another provider, declare that provider or let the bootstrap mechanism select according to configuration.

If `orm.xml` is present, update its namespace and schema to the corresponding Jakarta Persistence version. Do not keep the old JPA XML namespace just because the source code imports changed.

In addition to descriptors, review standard property configurations with old prefixes. For example, standard JDBC and schema generation properties may need to change from `javax.persistence.*` to `jakarta.persistence.*` according to the new specification. Properties starting with `hibernate.*` are Hibernate properties; do not rename their prefix under the JPA namespace replacement rule.

For Spring Boot configurations using `spring.datasource.url`, `spring.datasource.username`, and `spring.datasource.password`, those properties remain unchanged. They belong to Spring Boot, not `javax.persistence`.

## 7. Updating transaction and validation APIs in the right places

Some applications also use JTA or Bean Validation alongside JPA. When migrating to Jakarta EE, imports from these APIs may also need to change:

JTA:

```java
import jakarta.transaction.Transactional;
```

Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
```

However, if the application uses Spring's transaction annotation, the import remains:

```java
import org.springframework.transaction.annotation.Transactional;
```

Spring Data JPA, Spring transaction, and Spring validation have their own Spring packages; do not change them just because you are migrating from Java EE to Jakarta EE.

Check constraints on entities, DTOs, request bodies, and custom validators. If validation dependencies still use the old API, the application may encounter compile errors, ignore annotations, or fail to run validation as expected.

Example DTO using Jakarta Validation:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Size(max = 120)
        String name) {
}
```

If using Spring MVC, confirm that the validation starter and a Jakarta-compatible provider are declared. Do not just update imports while forgetting the dependency providing the implementation.

## 8. Checking Hibernate 5 to Hibernate 6

Migrating to Jakarta usually comes with upgrading Hibernate 5 to 6. This is a separate upgrade step that can introduce changes beyond the namespace.

Some areas requiring reading the migration guide for the exact version:

- HQL/JPQL queries and how Hibernate 6 parses queries.
- Custom types, `UserType`, `BasicType`, `TypeContributor`, and JDBC type mappings.
- Dialects and database-specific configuration.
- ID generators, sequences, and schema generation.
- SQL functions, native queries, and result mappings.
- Fetching, collection semantics, and entity deduplication during fetch joins.
- Second-level cache and cache provider integration.
- Logging, statistics, and Hibernate internal SPIs.

For example, custom types or code directly using `org.hibernate.type.*` may require changes when upgrading to Hibernate 6. Those APIs are already provider-dependent, so changing the `javax` package alone is not enough.

Do not automatically replace every old Hibernate class with a similarly named class. Read the Javadoc and migration guide for the exact target version, then test each custom feature in use.

## 9. Migrating Spring Data JPA repositories

Standard repositories keep the same structure. The domain type remains the entity, but the entity must use Jakarta annotations:

```java
import com.example.store.product.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Derived queries and Spring Data annotations also keep Spring Data's packages:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.name like concat('%', :keyword, '%')
        """)
    List<Product> searchByName(
            @Param("keyword") String keyword);
}
```

Do not change `org.springframework.data.jpa.repository.Query` to `jakarta.persistence.Query`. One is the annotation declaring a query on a repository method; the other is the Jakarta Persistence runtime query interface.

If a custom repository implementation injects `EntityManager`, change the import to `jakarta.persistence.EntityManager`. Standard APIs such as `createQuery`, `createNativeQuery`, `flush`, `clear`, and `find` remain standard, but dependencies must provide the proper Jakarta types.

## 10. Step-by-step migration process

Migrate on a separate branch and follow a verifiable sequence:

1. **Record the baseline:** current build, Java version, Spring Boot, Spring Data JPA, Hibernate, database driver, and custom libraries.
2. **Select target versions:** use the compatibility matrix and dependency management of the target Spring Boot release; confirm the minimum JDK.
3. **Upgrade JDK and build tool:** for Spring Boot 3, move runtime/build to Java 17 or higher and update Maven/Gradle plugins if needed.
4. **Upgrade framework/provider together:** update the Spring Boot parent/plugin and starters; do not retain incompatible older Spring Data JPA or Hibernate versions.
5. **Migrate source imports:** change Java EE APIs whose namespaces moved, especially `javax.persistence` to `jakarta.persistence`.
6. **Update XML and properties:** check `persistence.xml`, `orm.xml`, persistence properties, and other descriptors if used by the application.
7. **Review internal libraries:** confirm entity modules, custom repositories, auditing, validation, and integration libraries have Jakarta-compatible releases.
8. **Compile and fix errors by root cause:** address imports, method signatures, SPIs, or behavior changes; avoid adding both APIs just to make the build pass temporarily.
9. **Run integration tests:** verify entity scanning, repository bootstrap, persist/read/update/delete, transactions, and migrations.
10. **Verify SQL and trial deployment:** confirm dialects, sequences, locking, queries, and connection pools against the target database.

For large systems, you can upgrade module by module or service by service. However, module boundaries must agree on the namespace: a module containing entities used by a Jakarta application must provide classes compiled with Jakarta annotations, not old artifacts using `javax.persistence`.

## 11. Finding remaining javax references

Use source search to detect old imports:

```bash
rg -n "javax\.persistence|javax\.transaction|javax\.validation|javax\.servlet" .
```

Then classify each result:

- Old JPA imports need to be changed to Jakarta.
- Old JTA/Validation/Servlet imports need to be migrated if the application upgraded the corresponding APIs.
- Java SE packages such as `javax.sql` or `javax.crypto` must be kept unchanged.
- Packages from other libraries require reading those libraries' own documentation.

Also check XML and configuration files:

```bash
rg -n "javax\.persistence|persistence_2|orm_2" src
```

Searching does not replace inspecting the dependency tree. A third-party library can bundle bytecode or metadata referencing the old API without showing up in the application's source code. Inspect runtime dependencies and upgrade such libraries to Jakarta-supported versions.

## 12. Testing after migration

At a minimum, include these test groups:

**Context startup**

- Spring Boot context starts successfully.
- Hibernate provider initializes EntityManagerFactory.
- Repositories are created and domain entities are in the JPA metamodel.
- No `Not a managed type`, `NoClassDefFoundError`, or `ClassNotFoundException` caused by the old API.

**Mapping and repositories**

- Persist and read back entities.
- Test `@OneToMany`, `@ManyToOne`, embedded IDs, converters, and inheritance.
- Test derived queries, JPQL, native queries, and projections.
- Test lazy loading, fetch plans, and pagination.

**Transactions and database**

- Verify commit/rollback and propagation.
- Test optimistic locking and sequences/identity.
- Run schema migrations on the target database.
- Test native SQL and dialect-specific behavior.

**Integration**

- Run integration tests against a real database or Testcontainers when behavior depends on dialects, locking, sequences, or JDBC types.
- Verify Flyway/Liquibase and data migrations.
- Verify caching, auditing, validation, and serialization if used by the application.

Do not rely solely on unit tests or H2 if production uses PostgreSQL/MySQL/Oracle. Different databases can differ in sequences, JSON, timestamps, locking, and SQL syntax.

## 13. Common migration errors

| Error | Cause | Resolution |
|---|---|---|
| `Not a managed type` | Entity still uses `javax.persistence.Entity` or is not scanned by the Jakarta factory. | Update annotations/imports and verify the metamodel. |
| `ClassNotFoundException: javax.persistence...` | Old dependency or library still references the old JPA API. | Upgrade the library, inspect the dependency tree and runtime classpath. |
| `NoClassDefFoundError: jakarta/persistence/...` | Missing compatible Jakarta API or dependency excluded from runtime. | Use the appropriate starter/BOM and check runtime dependencies. |
| Validation annotations do not work | DTO/entity still uses `javax.validation` or missing Jakarta Validation provider. | Migrate imports and update validation dependencies. |
| Repository fails to initialize | Old Spring Data JPA incompatible with Jakarta or invalid entity generic type. | Upgrade Spring Data JPA together with Spring Boot. |
| Hibernate queries fail after upgrade | HQL, custom types, or SPIs changed between Hibernate major versions. | Read the migration guide and update the specific query/API. |
| XML mapping is not read | Descriptor still has the old namespace/schema. | Update to the Jakarta Persistence namespace and version. |
| Compile errors after global replace | Accidentally changed Java SE APIs such as `javax.sql`. | Restore Java SE packages and only change APIs whose namespaces moved. |

## 14. Migration completion checklist

- Spring Boot, Spring Framework, Spring Data JPA, and Hibernate are in a compatible version set.
- JDK meets the target Spring Boot version requirement.
- Entities, embeddables, converters, listeners, and EntityManager use `jakarta.persistence`.
- No `javax.persistence-api` JPA dependency remains at runtime.
- No Java SE packages such as `javax.sql`, `javax.crypto`, or `javax.naming` were mistakenly renamed.
- JTA, Validation, Servlet, and Annotation APIs were migrated within the right scope.
- `persistence.xml`, `orm.xml`, and standard properties were updated if present.
- Custom Hibernate extensions were cross-checked against the migration guide.
- Repository bootstrap and JPA metamodel were verified.
- Integration tests run against a database matching production.
- Schema migrations, transactions, queries, locking, and fetching were tested.

Migrating from `javax.persistence` to `jakarta.persistence` is a namespace change that affects type identity and dependency compatibility. Performing it alongside upgrading the framework/provider, migrating only the APIs whose namespaces changed, and testing against the target database will help prevent startup failures as well as post-deployment runtime discrepancies.
