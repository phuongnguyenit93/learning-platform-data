# @NoRepositoryBean and Shared Base Repository Interfaces

This lesson is part of the **Repository Exposure** section of Spring Data REST. When multiple repositories share a common set of operations, you can group those declarations into a generic interface and have concrete repositories extend it. **@NoRepositoryBean** marks this intermediate interface so Spring Data does not attempt to create a standalone repository proxy for it.

## Objectives

After this lesson, you will be able to:

- Recognize when to create a shared base repository interface.
- Explain why an intermediate generic interface requires **@NoRepositoryBean**.
- Write a base interface with generic entity and ID types, then bind them in concrete repositories.
- Distinguish Spring Data creating a repository bean from Spring Data REST exposing endpoints.
- Choose the right extension approach when needing query methods, shared logic, or custom repository behavior.

## 1. Problem: Multiple Repositories Sharing the Same Contract

An application often has multiple per-entity repositories:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatus(OrderStatus status);
}

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByStatus(CustomerStatus status);
}
~~~

These repositories may need shared methods, such as querying data by tenant, fetching active records, or applying a consistent data-access convention. Copying the same declarations into multiple interfaces makes future changes prone to drifting out of sync across repositories.

You can create a generic base interface:

~~~java
public interface BaseRepository<T, ID> extends JpaRepository<T, ID> {
    // Shared declarations across multiple entities
}
~~~

However, Spring Data scans repository interfaces within the configured scope. The interface above still carries two type parameters **T** and **ID**, so when inspecting it on its own, Spring Data does not yet know the concrete entity and primary key type needed to create a repository proxy. This is why **@NoRepositoryBean** is required.

## 2. What Does @NoRepositoryBean Do?

Import the annotation:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
~~~

Place the annotation on the intermediate interface for which Spring Data must not create an instance directly:

~~~java
@NoRepositoryBean
public interface BaseRepository<T, ID> extends JpaRepository<T, ID> {
}
~~~

Meaning of the annotation:

1. Spring Data still recognizes this interface as part of the repository inheritance hierarchy.
2. Spring Data does not create a separate repository proxy for the intermediate interface itself.
3. Concrete repositories extending this interface are still discovered and proxied once they specify concrete entity and ID types.
4. Valid inherited methods continue to participate in concrete repositories.

You can visualize the inheritance hierarchy as follows:

~~~text
BaseRepository<T, ID>
  |  @NoRepositoryBean: do not create a separate repository here
  |
  +-- OrderRepository extends BaseRepository<Order, Long>
  |     -> repository proxy managing Order
  |
  +-- CustomerRepository extends BaseRepository<Customer, Long>
        -> repository proxy managing Customer
~~~

**@NoRepositoryBean is not an annotation to disable repositories in general.** It only excludes the annotated interface from direct repository instance creation. Child interfaces that specify concrete types can still be instantiated normally.

## 3. Complete Example with a Tenant-Scoped Base Repository

Suppose entities that support querying by tenant all share a **tenantId** property. We describe the shared contract:

~~~java
public interface TenantOwned {
    UUID getTenantId();
}
~~~

An entity can implement that contract:

~~~java
@Entity
public class PurchaseOrder implements TenantOwned {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private UUID tenantId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Override
    public UUID getTenantId() {
        return tenantId;
    }
}
~~~

Create the base repository interface:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface TenantScopedRepository<T extends TenantOwned, ID>
        extends JpaRepository<T, ID> {

    List<T> findAllByTenantId(UUID tenantId);
}
~~~

Points to note:

- **T extends TenantOwned** constrains entities used with this repository to those implementing the tenant contract.
- **ID** stays generic; each concrete repository supplies the actual primary key type.
- **JpaRepository** provides common JPA operations such as saving, finding, paging, and deleting.
- **findAllByTenantId** is a query method. Spring Data parses the method name in the context of the concrete child repository's entity.
- **@NoRepositoryBean** prevents Spring Data from creating a standalone repository for the interface still containing type variables **T** and **ID**.

The concrete repository binds the generic types:

~~~java
import java.util.List;

import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface PurchaseOrderRepository
        extends TenantScopedRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Here:

- **PurchaseOrder** is the managed entity.
- **Long** is the ID type.
- **PurchaseOrderRepository** is the concrete repository for which Spring Data can create a proxy.
- The child repository inherits both JPA operations and the tenant-scoped query method.
- **@RepositoryRestResource** is placed on the concrete repository to customize the path and relation name when Spring Data REST exposes the repository.

If Spring Data REST is configured and the repository satisfies the active detection/exposure policy, the collection resource can be accessed via **/orders**. The **findByStatus** query method can be exposed under the repository's search resource according to Spring Data REST rules.

> The example assumes every entity using **TenantScopedRepository** has a persistent property named **tenantId**. If an entity lacks this property, Spring Data may fail to create the query method for the corresponding repository.

## 4. Which Base Interface Should You Extend?

Choose an interface based on the operation set concrete repositories need:

| Interface | When to Use |
| --- | --- |
| **Repository<T, ID>** | You want to selectively include methods in the repository contract. This is Spring Data's minimal marker interface. |
| **CrudRepository<T, ID>** | General CRUD operations are needed. |
| **PagingAndSortingRepository<T, ID>** | Pagination and sorting are needed. |
| **JpaRepository<T, ID>** | The repository uses JPA and needs JPA-specific utilities. |
| **ReactiveCrudRepository<T, ID>** | Working with repositories in the reactive model. |

If the base interface extends **CrudRepository** or **JpaRepository**, the corresponding CRUD methods are already inherited; there is no need to redeclare them just to have them.

If you want to expose only part of the CRUD contract, extend **Repository<T, ID>** and declare the required signatures. For example:

~~~java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadWriteRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    <S extends T> S save(S entity);
}
~~~

These signatures match CRUD methods supported by Spring Data. A concrete repository extending **ReadWriteRepository<Order, Long>** will have a contract for reading by ID and saving entities without extending all of **CrudRepository**.

This approach is useful when limiting the repository's operation surface. Verify signatures against the exact Spring Data version and storage module in use.

## 5. Multi-Tier Base Interfaces

An application can split contracts into multiple tiers, such as a shared read tier and a tenant-query tier:

~~~java
@NoRepositoryBean
public interface ReadRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}

@NoRepositoryBean
public interface TenantRepository<T extends TenantOwned, ID>
        extends ReadRepository<T, ID> {

    List<T> findAllByTenantId(UUID tenantId);
}

public interface OrderRepository
        extends TenantRepository<Order, Long> {
}
~~~

Every intermediate interface that Spring Data must not instantiate directly requires **@NoRepositoryBean**. Annotating one tier does not substitute for annotating other intermediate interfaces in the hierarchy.

Leaf interfaces such as **OrderRepository** must not be annotated with **@NoRepositoryBean** if you want Spring Data to create a repository bean for them.

## 6. @NoRepositoryBean and REST Exposure Are Separate Concerns

This is an important distinction when working with Spring Data REST.

| Mechanism | Responsibility |
| --- | --- |
| **@NoRepositoryBean** | Prevents Spring Data from creating a repository instance directly for a generic intermediate interface. |
| **@RepositoryRestResource** | Customizes how a repository is exposed as a REST resource; also provides the **exported** attribute to enable/disable exposure. |
| **@RestResource** | Customizes or disables exposure of a specific method or association. |
| **RepositoryDetectionStrategy** | Defines which repositories are eligible to be detected and exposed by Spring Data REST. |
| Spring Security | Controls which callers are allowed to access operations and data. |

Example to keep a concrete repository from appearing as a REST resource:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalOrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Example to keep the repository exposed while hiding one query method:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @RestResource(exported = false)
    List<Order> findByInternalFlag(boolean internalFlag);
}
~~~

Do not use **@NoRepositoryBean** to hide a child repository's endpoints. If a concrete repository still gets a Spring Data bean created, Spring Data REST may expose it depending on dependencies, configuration, and detection strategy.

Likewise, do not treat disabling REST exposure as an authorization mechanism. Exposed endpoints still require proper authentication and authorization policies; sensitive data must be controlled via security, projections, and appropriate export settings.

## 7. A Base Interface Does Not Provide Implementations by Itself

**@NoRepositoryBean** only controls repository instance creation. The annotation does not write execution code for new methods.

Spring Data can handle different groups of methods:

- **Standard CRUD methods:** if the signature matches a CRUD contract supported by the module, Spring Data routes calls to the module's default implementation, such as **SimpleJpaRepository** in JPA.
- **Derived query methods:** Spring Data parses the method name against the concrete entity's properties, e.g., **findAllByTenantId**.
- **Methods requiring custom logic:** you must supply an implementation via a repository fragment, an appropriate default method, or a custom repository base class.

If you need a shared operation with custom logic across all JPA repositories, consider a custom base class extending **SimpleJpaRepository** and configuring **repositoryBaseClass** in **@EnableJpaRepositories**. The base interface defines the contract; the custom base class supplies the shared implementation.

If logic is only needed in a few repositories, a repository fragment is usually clearer than putting every method into a large base interface.

## 8. Common Issues

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Application fails at startup because Spring cannot determine entity or ID for a generic interface | Intermediate interface is missing **@NoRepositoryBean** | Annotate all intermediate interfaces that must be excluded from repository instantiation. |
| Concrete repository bean is not created | Leaf interface is annotated with **@NoRepositoryBean**, sits outside scan scope, or extends the wrong repository type | Remove the annotation from the leaf interface if a bean is needed; verify package scan and repository module. |
| Property not found error when building query | Query method on base interface references a property missing on a concrete entity | Only put shared derived queries on the base when all child entities have that property; otherwise move the method to concrete repositories or use a fragment. |
| Base interface compiles but calling a new method fails | Signature declared without a matching query or custom implementation | Use a valid derived query, fragment, default method, or custom base class. |
| Child repository still appears in API | Confusing **@NoRepositoryBean** with disabling REST export | Use **@RepositoryRestResource(exported = false)**, **@RestResource(exported = false)**, or an appropriate detection strategy. |
| Repository fails to bind to the right store in multi-module Spring Data apps | Hierarchy uses only generic interfaces without enough information to distinguish modules | Use a module-specific interface like **JpaRepository** or clear domain/configuration metadata so Spring Data picks the right module. |

## 9. Implementation and Verification Workflow

1. Identify methods that are genuinely identical across repositories.
2. Choose the root contract: **Repository**, **CrudRepository**, **PagingAndSortingRepository**, or a store-specific interface.
3. Declare type parameters **T** and **ID**; add type bounds if shared methods require an entity property or contract.
4. Place **@NoRepositoryBean** on every intermediate interface.
5. Create concrete repositories and supply concrete entity and ID types, e.g., **OrderRepository extends TenantRepository<Order, Long>**.
6. Start the application context and confirm the concrete repositories inject successfully.
7. Run persistence tests for inherited methods, especially derived queries relying on shared properties.
8. If using Spring Data REST, test the concrete repository's routes and query resources; separately verify repositories or methods marked **exported = false**.
9. Test authorization independently of whether the repository is exposed.

When writing tests, note that because concrete repositories extend the base interface, a concrete bean is also assignable to the base interface type. Therefore, do not conclude that the base interface was instantiated as its own repository merely by looking up a bean by the parent type; inspect repository metadata or the concrete repository's behavior instead.

## 10. Quick Checklist

- [ ] Base interface genuinely represents a shared contract.
- [ ] Concrete repository's entity and ID are explicitly bound.
- [ ] Every intermediate interface to exclude from instantiation has **@NoRepositoryBean**.
- [ ] Concrete repository interfaces are not mistakenly annotated with **@NoRepositoryBean**.
- [ ] Derived queries only reference properties present on every applicable entity.
- [ ] Methods with custom logic have a corresponding fragment or implementation.
- [ ] REST exposure is controlled via appropriate Spring Data REST configuration.
- [ ] Security is configured separately, not by relying on repository exclusion annotations.

## 11. Key Takeaways

**@NoRepositoryBean** lets you use a generic interface as a shared contract tier in the repository hierarchy without asking Spring Data to create a repository proxy for that tier itself. Once a child interface supplies a concrete entity and ID, Spring Data can still create the corresponding repository.

In Spring Data REST tasks, keep two questions separate:

- Does Spring Data create a repository bean for this interface?
- Does Spring Data REST expose that repository bean as a REST resource?

The first question relates to **@NoRepositoryBean** and repository configuration. The second question relates to **@RepositoryRestResource**, **@RestResource**, and the repository detection strategy.

## References

- Spring Data JPA — Defining Repository Interfaces: https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html
- Spring Data REST — Getting Started and Repository Detection Strategy: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
- Spring Data REST — RepositoryRestResource API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html
- Spring Data Commons — Repository API: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/Repository.html
- Spring Data Commons — NoRepositoryBean API: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/NoRepositoryBean.html
