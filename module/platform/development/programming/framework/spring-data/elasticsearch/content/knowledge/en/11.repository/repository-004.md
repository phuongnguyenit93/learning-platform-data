# Shared Base Interfaces and `@NoRepositoryBean`

In a Spring Data Elasticsearch application, multiple entities often need the same set of repository operations: saving documents, finding by ID, deleting, counting, or querying by common properties. If each repository repeats the same declarations and helper logic, the codebase becomes harder to maintain when shared rules change.

Spring Data lets you create **shared base repository interfaces** using generic types. Concrete repositories extend this interface and supply the entity type along with the ID type. The `@NoRepositoryBean` annotation marks an intermediate interface as not being a standalone repository bean. Spring Data skips creating an implementation for the base interface, yet still includes its methods when creating implementations for concrete interfaces.

This lesson covers how to design generic repository interfaces, the role of `@NoRepositoryBean`, how Spring Data discovers repositories, how methods are inherited and analyzed against concrete entities, and the differences between base interfaces, custom repository fragments, and custom repository base classes.

## 1. Repository Interfaces in Spring Data Elasticsearch

A Spring Data repository is an abstraction that lets an application interact with data through interfaces. Spring Data generates runtime implementations based on the repository interface and the configured datastore type.

With Spring Data Elasticsearch, repositories typically extend `ElasticsearchRepository<T, ID>`:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

The two generic types mean:

- `T`: the entity/document type managed by the repository, here `Product`.
- `ID`: the identifier type of the entity, here `String`.

Spring Data uses this information to determine mapping metadata, convert between entities and documents, and build the appropriate repository operations.

A concrete repository can also declare additional query methods:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

Spring Data parses the method name `findByCategory` against `Product` entity properties and builds the corresponding query. If multiple entities share a common group of operations, those shared methods can be placed in a parent interface.

## 2. Why Use a Shared Base Interface?

Suppose an application has `Product`, `Customer`, and `Order` entities. Each repository may need:

- Standard CRUD operations.
- Shared utility methods, such as finding an entity that must exist by ID.
- Tenant-based query rules if all entities share a `tenantId` field.
- Consistent business methods across multiple repositories.

If the same method is written in every repository, a small change must be applied repeatedly. A generic base repository lets you define it once and reuse it:

```text
BaseElasticsearchRepository<T, ID>
                 |
       +---------+---------+
       |         |         |
       v         v         v
ProductRepository  CustomerRepository  OrderRepository
<Product,String>  <Customer,String>    <Order,String>
```

Generic types keep the base interface independent of any specific entity. Child repositories supply concrete types when extending it.

## 3. Creating a Generic Repository Interface

Create a base interface with two generic types `T` and `ID`:

```java
package com.example.catalog.repository;

import java.util.NoSuchElementException;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    default T getRequiredById(ID id) {
        return findById(id).orElseThrow(
                () -> new NoSuchElementException("Document not found: " + id));
    }
}
```

This interface extends `ElasticsearchRepository<T, ID>`, so concrete repositories inherit the operations provided by Spring Data Elasticsearch. The `getRequiredById` method is a Java default method; it reuses `findById` and throws an exception if the document is not found.

`@NoRepositoryBean` is an important annotation on the base interface. It informs the repository infrastructure not to create a standalone repository bean for this interface. The interface acts strictly as a shared definition for concrete repositories to extend.

### 3.1. Why does a generic interface need `@NoRepositoryBean`?

Spring Data scans repository interfaces within the configured scope. If an interface extends a repository abstraction and is not excluded from repository creation, Spring Data may treat it as a repository candidate.

With a generic interface such as:

```java
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {
}
```

Spring Data has no concrete entity for creating an independent repository for `T`. A repository needs an actual domain type and ID type to build the mapping context, query methods, and implementation. Intermediate interfaces should only be realized once a sub-interface provides concrete types.

`@NoRepositoryBean` excludes the base interface from bean creation. Without the annotation, application startup may fail because Spring Data tries to create a repository for an interface not yet parameterized with a concrete domain type, or throws errors related to resolving the domain type.

This annotation does not remove the interface's methods, nor does it prevent sub-interfaces from inheriting them. It simply marks the current interface as not a repository bean to instantiate.

## 4. Creating a Concrete Repository Extending the Base Interface

Suppose we have a `Product` entity:

```java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructors, getters and setters
}
```

The concrete repository extends the base interface and supplies the actual types:

```java
package com.example.catalog.repository;

import java.util.List;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends BaseElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

When Spring Data discovers `ProductRepository`, it knows:

- The domain type is `Product`.
- The ID type is `String`.
- Methods inherited from `ElasticsearchRepository` are provided for `Product`.
- The `getRequiredById` method is inherited from the base interface.
- The `findByCategory` method is parsed against `Product`'s mapping.

Spring Data creates a bean for `ProductRepository`. It does not create a separate bean for `BaseElasticsearchRepository` because that interface carries `@NoRepositoryBean`.

## 5. Using One Base Interface Across Multiple Entities

Other repositories can extend the same interface:

```java
public interface CustomerRepository
        extends BaseElasticsearchRepository<Customer, String> {
}

public interface OrderRepository
        extends BaseElasticsearchRepository<Order, String> {
}
```

Each child repository provides its own domain type. CRUD methods and default methods from the base interface work with the corresponding type.

For example, a service can inject the concrete repository:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Product getRequired(String id) {
        return productRepository.getRequiredById(id);
    }
}
```

The service does not need to know the implementation details generated by Spring Data. It depends only on the domain-specific interface.

## 6. Putting Shared Query Methods in a Base Interface

A base interface can declare query methods if those methods are valid for every domain type extending it.

For example, all documents in a system may have a `tenantId`. You can express that contract with a Java interface:

```java
public interface TenantScoped {
    String getTenantId();
}
```

A concrete entity has the `tenantId` property:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product implements TenantScoped {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String name;

    @Override
    public String getTenantId() {
        return tenantId;
    }
}
```

Generic repository for tenant-scoped entities:

```java
import java.util.List;

import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface TenantScopedRepository<T extends TenantScoped, ID>
        extends BaseElasticsearchRepository<T, ID> {

    List<T> findByTenantId(String tenantId);
}
```

Concrete repository:

```java
public interface ProductRepository
        extends TenantScopedRepository<Product, String> {

    List<Product> findByName(String name);
}
```

Spring Data parses `findByTenantId` against the concrete domain type `Product`. Because `Product` has a persistent property `tenantId`, the method can be translated into a query.

An important requirement: every domain type using `TenantScopedRepository` must actually have the persistent property referenced by the query method. The Java interface `TenantScoped` expresses the contract at the source-code level, but Spring Data still needs to find the corresponding property in the entity's metadata.

If a child repository uses an entity without a `tenantId` field, Spring Data may fail during repository initialization because the property referenced in the method name cannot be found. Do not place a query method that depends on an entity-specific field into a base interface shared across all entities.

## 7. Multiple Layers of Base Interfaces Are Possible

An application can organize layers of interfaces for reuse by domain group:

```text
ElasticsearchRepository<T, ID>
              |
              v
BaseElasticsearchRepository<T, ID>
              |
              v
TenantScopedRepository<T extends TenantScoped, ID>
              |
              +-------------------+
              |                   |
              v                   v
ProductRepository           CustomerRepository
```

None of the intermediate interfaces should become standalone beans, so `@NoRepositoryBean` must be placed on every intermediate interface used as a base repository.

Example:

```java
@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {
    // Shared methods
}

@NoRepositoryBean
public interface TenantScopedRepository<T extends TenantScoped, ID>
        extends BaseElasticsearchRepository<T, ID> {
    List<T> findByTenantId(String tenantId);
}

public interface ProductRepository
        extends TenantScopedRepository<Product, String> {
}
```

Whenever a new intermediate interface is added, evaluate whether it is an actual repository bean or purely a shared definition. If it is only a shared definition, annotate it with `@NoRepositoryBean`.

## 8. `@NoRepositoryBean` Does Not Belong on Concrete Repositories

This annotation is meant for base interfaces that should not be instantiated directly. Do not place it on a concrete repository interface that services need to inject.

Inappropriate example:

```java
@NoRepositoryBean
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

In this case, Spring Data is instructed to skip creating the `ProductRepository` bean. If a service injects `ProductRepository`, the application will fail to find the corresponding bean.

Appropriate declaration:

```java
@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {
}

public interface ProductRepository
        extends BaseElasticsearchRepository<Product, String> {
}
```

Only the base interface receives `@NoRepositoryBean`; the concrete interface is left for Spring Data to instantiate.

## 9. Repository Scanning and Package Structure

Spring Boot typically auto-discovers repositories within the package scan scope starting at the `@SpringBootApplication` class's package and its subpackages. Example layout:

```text
com.example.catalog
├── CatalogApplication.java
├── domain
│   ├── Product.java
│   └── Customer.java
├── repository
│   ├── BaseElasticsearchRepository.java
│   ├── TenantScopedRepository.java
│   ├── ProductRepository.java
│   └── CustomerRepository.java
└── service
    └── ProductService.java
```

Repository interfaces should reside in scanned packages. If repositories live outside the default scope or if you want explicit package control, use `@EnableElasticsearchRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository")
public class ElasticsearchRepositoryConfig {
}
```

There is no need to add this annotation if auto-configuration already scans the right packages. Avoid duplicate or overly broad scan configurations that cause unintended repositories to be discovered.

`@NoRepositoryBean` remains relevant when repository scanning is configured explicitly: the base interface is excluded from bean creation, while concrete repositories in the scan scope are processed normally.

## 10. Which Methods Belong in a Base Interface?

Not every method belongs in a base interface. Distinguish three groups:

| Method group | Example | Should it live in the base interface? |
|---|---|---|
| Generic methods independent of specific fields | `getRequiredById(ID id)` | Yes, if multiple repositories need the same behavior |
| Query methods based on properties present in every entity in a group | `findByTenantId(String tenantId)` | Yes, if the contract is guaranteed and mappings exist on every entity |
| Query methods based on a single entity's specific field | `findByCategory(String category)` | Place in that entity's concrete repository |

A good base interface contains truly shared contracts. If a base interface accumulates too many specialized query methods, entities are forced into artificial structural similarity and domain changes become difficult.

### 10.1. Default methods for shared logic

Default methods fit small pieces of logic that can be built using existing repository methods:

```java
@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    default boolean existsAndHasId(ID id) {
        return id != null && existsById(id);
    }
}
```

Default methods are implemented directly in the Java interface and avoid creating custom implementations just to compose a couple of built-in methods.

If the logic needs complex Elasticsearch APIs, multi-step orchestration, or other service dependencies, consider a service or a custom repository fragment rather than cramming all logic into a base interface.

### 10.2. Query methods are analyzed against concrete entities

A method name such as `findByTenantId` is analyzed when Spring Data creates the concrete repository. The property path must exist on the final domain type. For nested properties, the method name must match the property path structure and Spring Data's splitting rules.

If a property path is invalid, the error usually surfaces during repository initialization rather than only when the method is called. This helps catch mapping/query contract mismatches early at startup.

## 11. `@NoRepositoryBean` vs. Custom Repository Implementations

`@NoRepositoryBean` only controls whether Spring Data creates a repository bean for the current interface. It does not supply custom implementations for methods and does not replace repository extension mechanisms.

Spring Data provides other mechanisms for custom logic:

- **Default methods:** implement small logic directly inside the interface.
- **Repository fragments:** isolate a group of custom methods into a separate interface and corresponding implementation class.
- **Custom repository base class:** replace the underlying base implementation used across multiple repositories.

These three mechanisms solve different needs. `@NoRepositoryBean` can appear on generic base interfaces, whereas fragments or base classes are configured separately to supply implementations.

## 12. Using Repository Fragments for Specialized Elasticsearch Behavior

When specific repositories need complex queries, create a fragment instead of adding specialized methods to a shared base interface.

Fragment interface:

```java
import java.util.List;

public interface ProductSearchRepository {
    List<Product> searchByText(String text);
}
```

Fragment implementation (illustrating structure; query construction depends on the Spring Data Elasticsearch version's API):

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchRepositoryImpl implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByText(String text) {
        // Build a full-text query and execute it with ElasticsearchOperations.
        // The exact NativeQuery API depends on the Spring Data release train.
        throw new UnsupportedOperationException("Implement the version-specific query here");
    }
}
```

Concrete repository combining the standard repository and the fragment:

```java
public interface ProductRepository
        extends BaseElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
```

Spring Data merges auto-generated CRUD/query methods with custom methods from the fragment. Implementation naming conventions and registration rules follow Spring Data's repository fragment mechanism; follow the documentation for the version you are using.

The example above focuses on fragment structure. In production code, replace the placeholder with a concrete query using `NativeQuery`, `ElasticsearchOperations`, or the API supported by your project's release train.

## 13. Custom Repository Base Classes Are a Different Mechanism

If you want to customize the base implementation across many repositories, Spring Data lets you configure a repository base class. This is a repository implementation class, not a shared interface, and is not controlled by `@NoRepositoryBean`.

A custom base class typically extends Spring Data Elasticsearch's default implementation and adds shared behavior. Its constructors must match the factory/repository infrastructure of the Spring Data version in use.

Choose this mechanism only when you need to change foundational behavior across many repositories and have verified the constructor API. For logic needed by only a few repositories, repository fragments are easier to isolate. For small logic built on existing methods, default methods are simpler.

## 14. API Changes Across Spring Data Versions

The repository hierarchy can change between major Spring Data versions. Notably, Spring Data 3.x adjusted relationships among `CrudRepository`, `ListCrudRepository`, `PagingAndSortingRepository`, and related abstractions. Therefore, do not assume every repository interface inherits the exact same method set across all versions.

`ElasticsearchRepository<T, ID>` is the specialized abstraction of Spring Data Elasticsearch. Check the Javadoc for your exact dependency version to confirm which contracts it extends, which collection types it returns, and which Elasticsearch-specific APIs it provides.

When creating a base interface, you can extend `ElasticsearchRepository<T, ID>` if you want the Elasticsearch-specific repository abstraction. If you manually combine interfaces such as `CrudRepository` and `PagingAndSortingRepository`, verify the hierarchy in your release train to avoid missing or redundantly declared methods.

Do not pull in a separate version of `spring-data-commons` or `spring-data-elasticsearch` just for a newer interface without checking Spring Boot dependency management. Spring Data modules must remain mutually compatible.

## 15. Common Pitfalls

### Forgetting `@NoRepositoryBean` on a generic base interface

Spring Data may try to instantiate a repository for an intermediate interface without a concrete domain type. Annotate the base interface with `@NoRepositoryBean`.

### Placing `@NoRepositoryBean` on a concrete repository

Spring Data skips that repository, preventing services from injecting the bean. Only place the annotation on intermediate interfaces that should not be instantiated.

### Query methods referencing properties not present on all entities

A method like `findByCategory` in a base interface is only valid if every extending domain type has a persistent `category` property. Otherwise, move the method to the concrete repository or create a specialized base interface with an appropriate type bound/contract.

### Using unspecified generic types

Extending a base interface with a raw type or omitting concrete domain/ID types can prevent Spring Data from resolving required metadata. Extend the base interface with complete generic arguments, such as `Product, String`.

### Placing complex business logic inside the base interface

Base interfaces become hard to understand when packed with specialized queries and logic. Move logic into services or repository fragments according to usage scope.

### Confusing `@NoRepositoryBean` with `@Repository`

`@NoRepositoryBean` is not a bean-registration annotation. It excludes the base interface from repository bean creation. Concrete repositories are discovered by Spring Data via repository scanning.

### Using APIs missing in the running Spring Data version

Repository interfaces and methods evolve across release trains. Check the dependency tree and Javadoc of the exact version instead of relying on examples from another major version.

## 16. Base Repository Design Workflow

When creating a shared base interface, follow this sequence:

1. List the operations genuinely shared across entities.
2. Choose generic types `T` and `ID` to represent the domain and identifier types.
3. Extend `ElasticsearchRepository<T, ID>` or the abstraction appropriate for your release train.
4. Place `@NoRepositoryBean` on the intermediate interface.
5. Only put query methods in the base interface when every extending entity has the corresponding property path.
6. Use default methods for small logic built on existing repository methods.
7. Use repository fragments or services for complex, specialized search logic.
8. Create concrete repositories with explicit domain and ID types.
9. Ensure package scanning discovers the concrete repositories.
10. Start the application so Spring Data parses repository methods and catches property-path errors early.

## 17. Summary

Generic repository interfaces help standardize shared operations across multiple repositories in Spring Data Elasticsearch. A base interface typically declares `T` for the entity and `ID` for the identifier type, then extends `ElasticsearchRepository<T, ID>` to inherit standard repository operations.

`@NoRepositoryBean` marks intermediate interfaces so they are not turned into standalone repository beans. Concrete repositories extend that interface and supply the actual domain type and ID type, allowing Spring Data to generate implementations for the concrete repositories and apply the inherited methods.

Only put methods in a base interface that make sense for every entity in the group. Property-based query methods must match each domain type's mapping. For complex logic, use services or repository fragments; for changes to foundational implementation behavior, consider a custom repository base class. Distinguishing these mechanisms properly keeps repositories reusable, manageable, and compatible across Spring Data Elasticsearch versions.
