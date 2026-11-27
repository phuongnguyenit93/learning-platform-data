# Designing Base Interfaces with @NoRepositoryBean

## 1. Problem statement and objectives

A Spring Data MongoDB application often has multiple aggregate roots, such as Product, Customer, and Order. Each document type has its own repository, yet all of them may need shared operations like finding by ID, counting records, and handling not-found cases. Instead of duplicating common methods across every interface, we can create a **base repository interface**.

The problem is that Spring Data automatically scans repository interfaces to create beans. A generic interface such as `BaseMongoRepository<T, ID>` has no concrete domain, so **it should not be instantiated as a standalone repository bean**. The **@NoRepositoryBean** annotation solves this exact problem.

In the **SPRING_DATA_MONGODB** module, this mechanism supports repository-layer design when connecting to MongoDB, mapping documents, and operating through **MongoTemplate** or **MongoRepository**. Repository methods serve as the foundation for building queries, aggregations, indexes, transactions, reactive access, testing, and performance analysis; however, `@NoRepositoryBean` only affects **repository bean creation** and does not itself alter those features.

Objectives after this lesson:

1. Understand why generic repositories require `@NoRepositoryBean`.
2. Create a shared base interface and child repositories bound to concrete domain and ID types.
3. Choose between a full CRUD contract and a restricted read-only API.
4. Distinguish between default methods, derived queries, and custom implementations.
5. Know when a repository fragment or repository base class is needed.
6. Test bean creation, collection mapping, CRUD operations, and misconfiguration cases.

## 2. How does Spring Data create repositories?

Standard declaration:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {
}
~~~

During repository scanning, Spring Data locates eligible interfaces, resolves the **domain type** and **ID type**, and then uses a repository factory to create a proxy/bean. That bean can be injected into a service to perform MongoDB operations.

~~~mermaid
flowchart TD
    A["Repository scanning"] --> B{"Interface discovered"}
    B -->|"Concrete repository"| C["Resolve domain + ID"]
    C --> D["Repository factory"]
    D --> E["Repository proxy/bean"]
    B -->|"@NoRepositoryBean"| F["Skip creating standalone bean"]
    F --> G["Still allows child repositories to extend"]
    G --> C
~~~

For `ProductRepository`, the concrete types are `ProductDocument` and `ObjectId`. For `BaseMongoRepository<T, ID>`, the two parameters remain generic, so it is only **an intermediate contract** and cannot know ahead of time which collection to operate on.

## 3. Exact meaning of @NoRepositoryBean

The annotation belongs to Spring Data Commons:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
~~~

A minimal base interface:

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

The annotation tells Spring Data: **do not create a repository bean directly for BaseMongoRepository**. It does not prevent child interfaces from extending it and using the entire CRUD contract.

Two concrete interfaces:

~~~java
public interface ProductRepository
        extends BaseMongoRepository<ProductDocument, ObjectId> {
}

public interface CustomerRepository
        extends BaseMongoRepository<CustomerDocument, ObjectId> {
}
~~~

Spring Data can create `ProductRepository` and `CustomerRepository` beans normally as long as they are within scanning scope and their domain types are valid.

| Case | Expected outcome |
| --- | --- |
| `@NoRepositoryBean` on `BaseMongoRepository<T, ID>` | No standalone repository bean for the generic base. |
| `ProductRepository` extends base, without `@NoRepositoryBean` | Creates concrete bean for `ProductDocument`. |
| `@NoRepositoryBean` mistakenly placed on `ProductRepository` | `ProductRepository` bean is not created; injection can fail. |
| Base interface has a Java `default` method | Child repositories inherit the method body. |
| Base declares an arbitrary abstract method | Must support query derivation or have a matching implementation. |

**@NoRepositoryBean is not @Repository.** One annotation prevents creating a repository bean for an intermediate interface; the other is typically used to mark persistence-layer components. Spring Data repository scanning can automatically create beans for valid repositories without requiring `@Repository` on every child interface.

## 4. Complete example: Product and Customer sharing a base

### 4.1. Two independent documents

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    boolean active
) {}
~~~

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public record CustomerDocument(
    @Id ObjectId id,
    String displayName,
    String email
) {}
~~~

The **@Document** annotation determines the collection. `BaseMongoRepository` does not need to know where `Product` or `Customer` are stored; each child repository along with the MongoDB infrastructure uses domain metadata to choose the corresponding collection.

### 4.2. Base interface containing a useful default method

~~~java
package com.example.catalog;

import java.util.NoSuchElementException;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    default T getRequired(ID id) {
        return findById(id).orElseThrow(
            () -> new NoSuchElementException(
                "Document not found for id: " + id
            )
        );
    }
}
~~~

`getRequired` has a **Java method body** and calls `findById`, which is already provided by the repository. Spring Data does not need to parse `getRequired` as a query, nor do you need to write a new implementation class for this method.

### 4.3. Child repositories with their own queries

~~~java
package com.example.catalog;

import java.util.Optional;
import org.bson.types.ObjectId;

public interface ProductRepository
        extends BaseMongoRepository<ProductDocument, ObjectId> {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;

public interface CustomerRepository
        extends BaseMongoRepository<CustomerDocument, ObjectId> {
}
~~~

`ProductRepository` has `getRequired`, `save`, `insert`, `findById`, `deleteById`, and `findBySku`. `CustomerRepository` also has `getRequired` and shared CRUD methods, but **does not inherit `findBySku`**, because `CustomerDocument` has no `sku` property.

### 4.4. Using through a service

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public ProductDocument create(String sku, String name) {
        ProductDocument draft = new ProductDocument(
            null, sku, name, true
        );
        return products.insert(draft);
    }

    public ProductDocument getById(ObjectId id) {
        return products.getRequired(id);
    }
}
~~~

With an immutable record, `insert` returns the persisted entity; you should use **the returned object** because the ID may be assigned by creating a new instance during persistence. `getRequired` uses `findById` and throws an exception if no matching document exists; it does not yet decide the HTTP status or API-layer error structure.

~~~mermaid
flowchart LR
    A["BaseMongoRepository<T, ID>"] --> B["ProductRepository<ProductDocument, ObjectId>"]
    A --> C["CustomerRepository<CustomerDocument, ObjectId>"]
    B --> D["products collection"]
    C --> E["customers collection"]
~~~

## 5. What happens if you forget @NoRepositoryBean?

Consider this interface:

~~~java
// Not yet annotated with @NoRepositoryBean.
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

When it lies within scanning scope, Spring Data may try to create a dedicated repository for the generic interface. However, `T` and `ID` have no concrete types, causing repository initialization failures or missing domain metadata errors. The exact scenario and exception message depend on configuration, but the root cause remains that an interface meant for inheritance is being treated as a complete repository.

Fix:

~~~java
@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

If there are multiple intermediate generic layers, annotate every layer that should not become a repository bean:

~~~java
@NoRepositoryBean
public interface AuditedRepository<T, ID>
        extends BaseMongoRepository<T, ID> {
}
~~~

`AuditedRepository` in the example does not implement auditing yet; the name is only for illustrating an inheritance hierarchy. If auditing is truly needed, a dedicated audit mechanism must be configured and designed.

## 6. Choosing the right root repository

Not every project wants to expose full CRUD operations.

| Interface | Scope | When to use |
| --- | --- | --- |
| `Repository<T, ID>` | Marker interface; select signatures manually | When exposing a selective API. |
| `CrudRepository<T, ID>` | General CRUD contract | When basic operations are needed without MongoDB specifics. |
| `ListCrudRepository<T, ID>` | CRUD variant returning `List` results | Use when supported by your Spring Data version. |
| `MongoRepository<T, ID>` | Synchronous MongoDB-specific contract | When standard MongoDB CRUD is needed. |
| `ReactiveMongoRepository<T, ID>` | Reactive CRUD contract | Use `Mono`/`Flux` in reactive applications. |

In newer Spring Data versions, certain capabilities like pagination or sorting reside in specialized interfaces. Always check the exact API of your project's version when selecting the base contract.

### 6.1. Full CRUD base

~~~java
@NoRepositoryBean
public interface FullAccessMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

This is a simple choice when every child repository is allowed to expose CRUD. It does not mean end users have database write permissions; operation protection must be handled in other layers.

### 6.2. Read-only base using Repository<T, ID>

~~~java
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadOnlyMongoRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    boolean existsById(ID id);

    Iterable<T> findAll();
}
~~~

Concrete repository:

~~~java
public interface ProductReadRepository
        extends ReadOnlyMongoRepository<ProductDocument, ObjectId> {
}
~~~

These signatures correspond to CRUD operations that the base implementation knows how to handle. Because the interface does not expose `save` or `delete`, code receiving `ProductReadRepository` **cannot directly call write methods through that type**.

However, this is only a **Java API restriction**. Other code can still use `MongoTemplate`, the driver, or another repository to write data. If writes must actually be prohibited, MongoDB access permissions and appropriate application controls must be enforced.

## 7. Distinguishing four kinds of methods

| Kind | Example | Mechanism |
| --- | --- | --- |
| Inherited CRUD | `findById`, `save`, `deleteById` | Built-in repository infrastructure implementation. |
| Java default method | `getRequired` | Has a body inside the interface, using inherited APIs. |
| Derived query | `findBySku(String sku)` | Spring Data parses the method name against domain properties. |
| Custom method | `existsAnyByIds(Iterable<ID>)` | Requires an explicit implementation if not part of standard CRUD. |

### 7.1. A default method is not a derived query

~~~java
@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    default boolean isEmptyRepository() {
        return count() == 0;
    }
}
~~~

Spring Data does not look for a property named `emptyRepository`; Java already knows how to compute it via `count`. On the flip side, `count` has its own query cost, so avoid calling it repeatedly on very large collections unnecessarily.

### 7.2. Derived queries require real properties

~~~java
// Unsuitable in the base if not every domain has status.
List<T> findByStatus(String status);
~~~

If `ProductDocument` lacks a `status` field, Spring Data can fail when initializing `ProductRepository` due to unresolved properties. Only place truly shared queries in the base when all domains share the corresponding property contract.

The `findBySku` method belongs in `ProductRepository` because `sku` is specific to `ProductDocument`.

### 7.3. @NoRepositoryBean does not generate arbitrary implementations

~~~java
@NoRepositoryBean
public interface ExtendedMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    boolean existsAnyByIds(Iterable<ID> ids);
}
~~~

Without an implementation or query annotation, Spring Data may misinterpret `existsAnyByIds` as a derived query and throw a property resolution error. `@NoRepositoryBean` only instructs Spring Data to **skip creating a bean for the intermediate interface**—it does not automatically implement abstract methods.

## 8. Extending with a repository base class

If a specialized operation truly needs to apply across **all configured repositories**, you can build a base implementation extending `SimpleMongoRepository` and configure the repository factory.

### 8.1. Shared contract

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ExtendedMongoRepository<T, ID>
        extends MongoRepository<T, ID> {

    boolean existsAnyByIds(Iterable<ID> ids);
}
~~~

### 8.2. Illustrative implementation

~~~java
package com.example.catalog;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.repository.query.MongoEntityInformation;
import org.springframework.data.mongodb.repository.support.SimpleMongoRepository;

public class ExtendedMongoRepositoryImpl<T, ID>
        extends SimpleMongoRepository<T, ID>
        implements ExtendedMongoRepository<T, ID> {

    private final MongoOperations mongoOperations;
    private final Class<T> domainType;

    public ExtendedMongoRepositoryImpl(
            MongoEntityInformation<T, ID> information,
            MongoOperations mongoOperations) {
        super(information, mongoOperations);
        this.mongoOperations = mongoOperations;
        this.domainType = information.getJavaType();
    }

    @Override
    public boolean existsAnyByIds(Iterable<ID> ids) {
        Objects.requireNonNull(ids, "ids must not be null");

        List<ID> values = new ArrayList<>();
        ids.forEach(values::add);
        if (values.isEmpty()) {
            return false;
        }

        Query query = Query.query(
            Criteria.where("_id").in(values)
        );
        return mongoOperations.exists(query, domainType);
    }
}
~~~

`existsAnyByIds` checks whether at least one document carries an ID in the input collection. For an empty collection, it returns `false` and avoids an unnecessary query. `MongoOperations` receives **`domainType`**, enabling it to use mapping metadata to select the appropriate collection.

The example relies on Spring Data MongoDB APIs supporting the constructor signature above. When bringing this into a real project, check your library version and `SimpleMongoRepository`/`MongoEntityInformation` signatures, especially if the system uses custom ID converters or multiple templates/databases.

### 8.3. Registering repositoryBaseClass

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackages = "com.example.catalog",
    repositoryBaseClass = ExtendedMongoRepositoryImpl.class
)
public class MongoRepositoryConfiguration {
}
~~~

Child repository:

~~~java
public interface ProductRepository
        extends ExtendedMongoRepository<ProductDocument, ObjectId> {
}
~~~

The service can call:

~~~java
boolean found = products.existsAnyByIds(
    java.util.List.of(idA, idB)
);
~~~

**Merely adding `ExtendedMongoRepositoryImpl` while forgetting to configure `repositoryBaseClass` is not enough** for the repository factory to use this implementation. If the project already has repository scanning handled by Spring Boot or a separate configuration, integrate the necessary attributes into a single consistent configuration and avoid scanning the same interface twice.

### 8.4. When should you use a repository fragment?

A repository base class affects all repositories within the configured **factory scope**. If only `ProductRepository` needs a custom capability, such as full-text search or a complex aggregation, a **repository fragment** is usually more appropriate.

A fragment consists of a contract interface and an implementation composed into the repository that needs it. It differs from `@NoRepositoryBean` because a fragment provides execution behavior, whereas `@NoRepositoryBean` only governs whether a repository bean is created for an intermediate interface.

| Need | Mechanism to consider |
| --- | --- |
| Share `getRequired` built on `findById` | Default method in a base interface. |
| Share standard CRUD | Base interface extending `MongoRepository`. |
| Only Product needs custom aggregation | Custom fragment on `ProductRepository`. |
| Many repositories need the same foundational custom-coded operation | Custom base class / shared fragment. |
| Prevent bean creation from a generic base | `@NoRepositoryBean`. |

## 9. Choosing the exact generic types T and ID

Intermediate interface:

~~~java
@NoRepositoryBean
interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

Child repositories must bind the exact domain and ID types:

~~~java
interface ProductRepository
        extends BaseMongoRepository<ProductDocument, ObjectId> {
}
~~~

Avoid incompatible ID types:

~~~java
// Unsuitable when ProductDocument declares @Id ObjectId.
interface WrongProductRepository
        extends BaseMongoRepository<ProductDocument, String> {
}
~~~

In some cases, Spring Data can convert between hex `String` and BSON `ObjectId`, but declaring the wrong type parameter makes the Java contract unclear and harder to test. When the domain uses `ObjectId`, stay consistent with `ObjectId` across the repository and service unless a deliberate design requires otherwise.

### 9.1. Do not confuse type T with collection name

In the example, `ProductDocument` carries **`@Document(collection = "products")`** and `CustomerDocument` carries **`@Document(collection = "customers")`**. Even though both extend `BaseMongoRepository`, each child repository operates using its own **domain type metadata**.

If an application uses multiple databases or `MongoTemplate` instances, repository infrastructure is bound to the corresponding MongoDB configuration; `@NoRepositoryBean` does not route a repository to a different database.

## 10. Repository scanning scope and dependency injection

In a Spring Boot application with standard package layout, repository scanning is usually auto-configured around the application package. If repositories live outside that scope, explicit configuration is needed:

~~~java
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@EnableMongoRepositories(
    basePackages = "com.example.catalog"
)
public class RepositoryConfiguration {
}
~~~

The snippet above illustrates scanning; if you already use **`repositoryBaseClass`** as in section 8, declare the attributes on the appropriate factory configuration and avoid creating two overlapping scan configurations.

In a service, a Spring Data repository is an injected bean:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogLookupService {
    private final ProductRepository products;

    public CatalogLookupService(ProductRepository products) {
        this.products = products;
    }
}
~~~

You do not need to put `@Repository` on `ProductRepository` if repository scanning already creates a valid bean. Conversely, **do not put `@NoRepositoryBean` on `ProductRepository`** if you want to inject that repository directly.

### 10.1. Testing the true meaning of NoRepositoryBean

A common testing mistake:

~~~java
// Wrong expectation if ProductRepository has already been successfully created.
applicationContext.getBeansOfType(BaseMongoRepository.class).isEmpty();
~~~

Why is this wrong? `ProductRepository` is a bean that is a **subtype** of `BaseMongoRepository`. Thus looking up beans by `BaseMongoRepository.class` can still return `ProductRepository`. `@NoRepositoryBean` only prevents a **dedicated bean for the generic base interface**; it does not remove concrete beans from the type hierarchy.

When testing, verify that `ProductRepository` is actually injected and its methods can be invoked, while no standalone repository bean exists for `BaseMongoRepository`.

## 11. @NoRepositoryBean does not alter CRUD semantics

### 11.1. Soft delete

If you define:

~~~java
@NoRepositoryBean
interface SoftDeleteRepository<T, ID>
        extends MongoRepository<T, ID> {
}
~~~

then `deleteById` still carries **MongoRepository's delete semantics**. Renaming an interface does not cause data to be "marked as deleted". Soft delete requires implementing custom methods and policies, including a status field, default queries, indexes, retention, and tests.

### 11.2. Multi-tenancy

A generic base does not automatically append a `tenantId` filter to every derived query, aggregation, or `MongoTemplate` call. If tenant isolation is required, you need an explicit policy and verification across all read/write paths, not just a repository interface.

### 11.3. Transactions

`@NoRepositoryBean` does not create transactions. Even when multiple repositories share a base, consecutive `save` calls across multiple documents do not automatically become an atomic unit. Transactions must be configured on a supported MongoDB deployment with boundaries aligned to business invariants.

### 11.4. Reference cascading

When an entity references another document via `ObjectId`, `@DBRef`, or `@DocumentReference`, calling `save`/`delete` on the parent repository does not cascade-save/cascade-delete target documents by default. Relationship handling rules are a business design independent of the base repository.

## 12. Specializing repositories in reactive systems

A project using `ReactiveMongoRepository` needs its own reactive base:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseReactiveMongoRepository<T, ID>
        extends ReactiveMongoRepository<T, ID> {
}
~~~

Concrete repository:

~~~java
public interface ReactiveProductRepository
        extends BaseReactiveMongoRepository<ProductDocument, ObjectId> {
}
~~~

A reactive default method can return `Mono`:

~~~java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;

@NoRepositoryBean
public interface BaseReactiveMongoRepository<T, ID>
        extends ReactiveMongoRepository<T, ID> {

    default Mono<T> getRequired(ID id) {
        return findById(id).switchIfEmpty(
            Mono.error(new NoSuchElementException(
                "Document not found for id: " + id
            ))
        );
    }
}
~~~

**`@NoRepositoryBean` still prevents creating a bean for the generic base**, but it does not turn a synchronous `MongoRepository` into a reactive one. Do not call `block()` inside a default method to synchronously extract a `Mono` value. Any custom reactive repository base also needs implementation infrastructure compatible with the reactive driver/template.

## 13. Package design and reuse scope

An illustrative structure:

~~~text
com.example.catalog
├── persistence
│   ├── base
│   │   ├── BaseMongoRepository.java
│   │   └── ExtendedMongoRepositoryImpl.java
│   ├── product
│   │   ├── ProductDocument.java
│   │   └── ProductRepository.java
│   └── customer
│       ├── CustomerDocument.java
│       └── CustomerRepository.java
└── service
    └── ProductService.java
~~~

`BaseMongoRepository` is an infrastructure contract inherited by multiple repositories; domain queries belong in concrete repositories. When multiple modules share a base interface, keep its API small and clear. A "super repository" containing dozens of business-specific methods often creates coupling and query failure risks on domains lacking those properties.

When sharing a base repository across services, consider Spring Data version compatibility, ID type choices, exception policies, and scanning scope. There is no need to create a shared library just to reuse a single `getRequired` method if dependency overhead outweighs the benefit.

## 14. Integration testing

Repository tests should run against a **dedicated test MongoDB**, such as a Testcontainers instance configured for the application. Mocking `ProductRepository` alone does not verify whether the repository factory creates the child bean.

Things to verify:

1. `ProductRepository` is created and injected successfully.
2. `BaseMongoRepository` is not instantiated as a standalone generic bean.
3. The default method `getRequired` works on the child repository.
4. `ProductRepository` uses the `products` collection as declared by `@Document`.
5. `findBySku` uses a real property; `save`/`insert` and ID handling work properly.
6. If a custom base implementation is added, custom methods run through the registered implementation.

JUnit 5 example with a configured test MongoDB:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @Autowired
    private MongoTemplate template;

    @Test
    void concreteRepositoryInheritsBaseMethod() {
        assertThat(template.getCollectionName(ProductDocument.class))
            .isEqualTo("products");

        String sku = "TEST-" + UUID.randomUUID();
        ProductDocument inserted = products.insert(
            new ProductDocument(null, sku, "Sample", true)
        );
        ObjectId id = inserted.id();

        assertThat(id).isNotNull();
        try {
            ProductDocument found = products.getRequired(id);
            assertThat(found.sku()).isEqualTo(sku);
            assertThat(products.findBySku(sku)).isPresent();
        } finally {
            products.deleteById(id);
        }
    }
}
~~~

The example requires Spring Boot test and a properly configured test MongoDB. If the project uses a custom `repositoryBaseClass`, import/configure the corresponding factory in tests to verify the production code path.

### 14.1. Testing configuration errors

Checks to include during review:

- Forgetting `@NoRepositoryBean` on a generic interface: check startup behavior.
- Mistakenly adding `@NoRepositoryBean` to a concrete repository: confirm the bean is not created.
- Putting `findBySku` on the base when a domain lacks `sku`: catch derived query failure.
- Changing repository ID type from `ObjectId` to `String` without updating the model: detect contract mismatch.
- Having a custom method without configuring an implementation: detect repository creation failure.

Do not leave intentional misconfigurations in production code; they are training scenarios or isolated test fixtures if the project tests startup validation.

## 15. Diagnosing common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Spring tries to create a repository for `BaseMongoRepository` | Missing `@NoRepositoryBean` on generic interface | Place `@NoRepositoryBean` on the proper base. |
| `ProductRepository` cannot be injected | `@NoRepositoryBean` placed on concrete interface or missing scan | Verify annotations and package scanning. |
| Cannot resolve domain/ID | Interface remains generic or type binding is wrong | Bind `T`/`ID` in the concrete child repository. |
| Startup reports missing property | Derived query on base uses a field absent on some domains | Move the query to the repository that owns the field. |
| Custom method does not run | Signature declared without implementation | Use a default method, fragment, or `repositoryBaseClass`. |
| Custom base class is ignored | `repositoryBaseClass` not registered | Check repository factory configuration. |
| Queries target the wrong collection | Wrong `@Document` or template/database | Check domain metadata and MongoDB configuration. |
| Read-only API still allows writes elsewhere | Interface restriction is not database authorization | Add authorization and application boundaries. |
| Reactive code blocks threads | Using synchronous repository or `block()` | Use `ReactiveMongoRepository` and `Mono`/`Flux` pipelines. |

Diagnostic sequence in order:

1. Identify the interface name being processed by the repository factory.
2. Check whether it is a generic base or concrete repository and verify `@NoRepositoryBean` placement.
3. Confirm the domain type, ID type, and `@Document` annotation.
4. Check scanning scope and which template/database is bound.
5. If a derived query is present, match the method name against the domain's Java properties.
6. If a custom method is present, check fragment/base implementation and `repositoryBaseClass` configuration.
7. Once the bean is created successfully but queries are slow, check indexes, actual data, and MongoDB query plans; `@NoRepositoryBean` does not directly control query performance.

## 16. Practice exercises

### Exercise 1: where does the annotation go?

~~~java
interface SharedRepository<T, ID>
        extends MongoRepository<T, ID> {}

interface ItemRepository
        extends SharedRepository<ItemDocument, ObjectId> {}
~~~

**Question:** Where should `@NoRepositoryBean` be added so `ItemRepository` can still be injected?

**Answer:** Add the annotation to `SharedRepository`, because it is the generic intermediate interface. `ItemRepository` is the concrete interface and must not be annotated if you want Spring Data to create a bean for it.

### Exercise 2: does a default method need an implementation class?

~~~java
@NoRepositoryBean
interface BaseRepository<T, ID> extends MongoRepository<T, ID> {
    default T require(ID id) {
        return findById(id).orElseThrow();
    }
}
~~~

**Answer:** No separate implementation class is needed for `require`. It is a default method using the built-in `findById`, and it is not parsed as a derived query.

### Exercise 3: invalid derived query

`ProductDocument` has `sku`, while `CustomerDocument` does not. What happens if `findBySku(String sku)` is placed in `BaseMongoRepository`?

**Answer:** The repository for the domain lacking `sku` can fail at startup because Spring Data cannot resolve the property. Move `findBySku` into `ProductRepository`.

### Exercise 4: restricting CRUD

Design `ReadOnlyMongoRepository<T, ID>` exposing only `findById`, `existsById`, and `findAll`.

**Hint:** Extend `Repository<T, ID>`, add `@NoRepositoryBean`, and declare signatures compatible with the CRUD implementation. Actually prohibiting writes requires MongoDB permissions and suitable application architecture.

### Exercise 5: implementing a custom method

A base interface has `existsAnyByIds(Iterable<ID> ids)`, but the application fails when creating child repositories. What should you check?

**Answer:** Check whether the method has a default body or custom implementation. If extending `SimpleMongoRepository`, configure `repositoryBaseClass`; `@NoRepositoryBean` does not implement methods automatically.

### Exercise 6: misunderstanding bean types

A test expects `applicationContext.getBeansOfType(BaseMongoRepository.class)` to return empty even though `ProductRepository` works. Why is this expectation wrong?

**Answer:** `ProductRepository` is a bean whose type inherits from `BaseMongoRepository`, so looking up by the base type still returns `ProductRepository`. The annotation only prevents creating a bean directly for the base interface.

### Exercise 7: switching to reactive

The application uses Reactor and wants `getRequired` to return `Mono<T>`. Should you keep using `MongoRepository` for the base?

**Answer:** No. Create `BaseReactiveMongoRepository` extending `ReactiveMongoRepository`, annotate it with `@NoRepositoryBean`, and write a default method returning `Mono`, avoiding `block()`.

## 17. Key principles to remember

1. **Place `@NoRepositoryBean` on intermediate repository interfaces** that Spring Data should not instantiate as standalone beans.
2. **Concrete repositories bound to domain/ID still get Spring Data beans** if within scanning scope and not excluded.
3. **`MongoRepository` shares CRUD**, while the collection is determined by domain metadata and the child repository's MongoDB configuration.
4. **Java default methods** need no separate implementation; derived queries must match Java properties; custom methods must have an implementation mechanism.
5. **Repository fragments and `repositoryBaseClass`** supply additional behavior, whereas `@NoRepositoryBean` only controls repository discovery.
6. **`ReadOnlyRepository` restricts the compile-time API**, not database permissions.
7. **`ReactiveMongoRepository` requires a separate reactive base** with `Mono`/`Flux` methods.
8. **Soft delete, transactions, tenancy, and cascading must be designed explicitly**—they do not come automatically from annotations.
9. **Test repositories against a real test MongoDB** to confirm beans, IDs, collections, and CRUD behavior before expanding.

Designing base interfaces with **@NoRepositoryBean** keeps the **SPRING_DATA_MONGODB** repository layer consistent, avoids accidental creation of generic beans, and maintains a clear boundary between shared CRUD and document-specific business queries. This provides a solid foundation for building testable and maintainable repositories, `MongoTemplate` usage, aggregations, indexes, and data access flows.
