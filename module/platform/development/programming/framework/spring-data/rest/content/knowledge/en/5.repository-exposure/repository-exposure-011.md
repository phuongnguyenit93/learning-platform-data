# Reviewing Delete Method Variants and Designing Read-Only Repositories

## 1. Why Review Delete APIs Before Exposing a Repository?

Spring Data provides deletion operations at several levels: deleting one entity, deleting by ID, deleting a collection of entities or IDs, deleting all data, and conditional deletion. These methods differ in inputs, execution cost, and impact on the entity lifecycle.

When using Spring Data REST, repositories can be exposed as HTTP APIs. Consequently, extending an interface that includes write methods also affects the API surface. Clarify:

- Does the repository truly need to allow deletion?
- If so, who is allowed to delete and within what scope?
- Which Java methods exist due to interface inheritance?
- Which methods are exposed as endpoints by Spring Data REST?
- How do you guarantee a read-only API even if custom controllers or other access paths exist?

A read-only repository should be designed starting from a minimal Java contract before configuring Spring Data REST exposure.

## 2. Delete Variants in CrudRepository

In Spring Data Commons, CrudRepository defines the following common deletion operation groups (exact signatures may vary slightly across versions):

~~~~java
void deleteById(ID id);
void delete(T entity);
void deleteAllById(Iterable<? extends ID> ids);
void deleteAll(Iterable<? extends T> entities);
void deleteAll();
~~~~

Meaning of each method:

| Method | Deletion Scope | When to Use |
|---|---|---|
| deleteById(id) | A single entity identified by ID | Client or service has only the ID and wants to delete one resource |
| delete(entity) | The passed-in entity | You already hold the entity and want to request deleting that exact entity |
| deleteAllById(ids) | Entities whose IDs are in the input collection | Deleting a set of records identified by IDs |
| deleteAll(entities) | The passed-in entities | Deleting a pre-loaded or pre-selected group of objects |
| deleteAll() | All entities of the repository | Only for administrative tasks with tightly controlled scope and permissions |

CRUD contracts typically specify that if an entity does not exist, deletion may be silently ignored without throwing an error. However, read the contract and behavior of your specific store if the application relies on distinguishing "deleted" from "not found".

### Deleting by ID vs. Deleting by Entity

**deleteById(id)** fits when the caller only has the identifier. The repository handles finding and deleting as required by the store implementation.

**delete(entity)** takes an object. With JPA, the entity may be detached; the implementation must manage persistence state and check the corresponding entity in the persistence context or database. Do not assume passing an object with an ID always equals a simple SQL DELETE statement.

Both methods can achieve the same business result, yet execution paths and costs may differ. If you need to check ownership, state, or preconditions before deletion, place that logic in a service or a clearly transacted business operation.

### Deleting Multiple Records

**deleteAllById(ids)** takes IDs; **deleteAll(entities)** takes entities. These two overloads clearly express request inputs, but method names do not guarantee the implementation emits a single bulk DELETE statement.

In many stores, list-based deletions iterate over each element. Measure performance with realistic batch sizes and check how your module's implementation handles batching, transactions, and callbacks.

### Deleting Everything

**deleteAll()** has the widest blast radius: every entity belonging to the repository. Do not include this operation in a public API unless business requirements specifically demand it. In multi-tenant applications, ensure operations cannot cross the current tenant boundary.

With Spring Data JPA, distinguish per-entity deletion methods from bulk variants such as **deleteAllInBatch()** or **deleteAllByIdInBatch(ids)** on JpaRepository. Bulk operations can execute directly against the database and bypass certain per-entity lifecycle behaviors, such as entity callbacks or cascades. After a bulk operation, an existing persistence context holding stale entities may no longer reflect database state. Use them only when you understand those differences and manage transactions and the persistence context accordingly.

## 3. Derived Delete Queries and Bulk Deletes

Spring Data supports query methods starting with **deleteBy** or **removeBy**, for example:

~~~~java
long deleteByStatus(Status status);
void removeByExpiredAtBefore(Instant cutoff);
~~~~

These are query methods parsed from the method name. With Spring Data JPA, derived delete queries typically fetch matching entities and then delete them individually, preserving per-entity lifecycle behavior just like single-object deletes. Supported return types depend on the module and version; common ones are void or the count of deleted records.

An alternative is declaring a bulk delete using @Modifying and @Query:

~~~~java
@Modifying
@Query("delete from Session s where s.expiredAt < :cutoff")
int deleteExpired(@Param("cutoff") Instant cutoff);
~~~~

Bulk JPQL can delete directly in the database more efficiently when many records are affected. In exchange, it bypasses the per-entity deletion pipeline, so entity-level callbacks, cascades, and persistence context state require separate consideration.

| Criterion | Derived delete query | Bulk delete with @Modifying @Query |
|---|---|---|
| Target selection | Method name parsing | Developer-declared JPQL/SQL |
| Execution | Often loads matching entities then deletes individually (especially with JPA) | Executes set-based delete statement in database |
| Entity lifecycle | Can trigger per-entity callbacks | Does not trigger per-entity delete callbacks like regular remove |
| Performance on large sets | Can consume memory and issue many operations | Usually better suited for bulk operations |
| Persistence context state | Entities follow normal lifecycle | May leave stale entities in persistence context; consider clear/refresh |

A delete-oriented query method is a write operation, even though its name resembles a search method. Do not let a destructive operation become accessible like a read API simply because it sits in the search group. If you do not want to expose that method, apply @RestResource(exported = false) to it or omit it from exposed repositories.

## 4. How Spring Data REST Exposes Delete Operations

Spring Data REST maps repository resources to HTTP operations following a resource model. For an item resource, the standard delete operation typically looks like:

~~~~http
DELETE /people/{id}
~~~~

This request asks to delete the resource with the given ID. Spring Data REST handlers use repository metadata and repository invokers to perform the delete. Clients interact with resource URLs; they do not directly invoke a specific Java overload.

Crucially, do not infer that every overload in CrudRepository automatically becomes its own endpoint. Whether a Java method exists and whether it is exposed over REST are two separate questions. Actual routes also depend on repository type, method metadata, annotations, Spring Data REST version, and application configuration.

For methods or repositories to hide:

- **@RepositoryRestResource(exported = false)** on the repository: does not expose that repository as a REST resource.
- **@RestResource(exported = false)** on a method: hides the method from REST exposure.
- To hide a method inherited from CrudRepository, redeclare the exact signature in the child repository with @RestResource(exported = false), then verify the actual mapping in your version.

Example hiding inherited write operations:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends CrudRepository<Person, Long> {

    @Override
    @RestResource(exported = false)
    <S extends Person> S save(S entity);

    @Override
    @RestResource(exported = false)
    <S extends Person> Iterable<S> saveAll(Iterable<S> entities);

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);

    @Override
    @RestResource(exported = false)
    void delete(Person entity);

    @Override
    @RestResource(exported = false)
    void deleteAllById(Iterable<? extends Long> ids);

    @Override
    @RestResource(exported = false)
    void deleteAll(Iterable<? extends Person> entities);

    @Override
    @RestResource(exported = false)
    void deleteAll();
}
~~~~

This example illustrates redeclaring methods and disabling export. Match generic signatures against the Spring Data Commons version in your project. If the repository also inherits store-specific write APIs from JpaRepository such as saveAndFlush, deleteAllInBatch, or deleteAllByIdInBatch, review them separately; hiding CrudRepository methods does not automatically hide every write method added by another interface.

## 5. Designing a Read-Only Repository from the Start

The cleanest way to restrict the contract is to extend the **Repository<T, ID>** marker interface and declare only the read methods needed. Do not extend CrudRepository, JpaRepository, or another interface carrying write methods if the application does not need them.

Example:

~~~~java
@RepositoryRestResource(path = "articles")
public interface ArticleReadRepository extends Repository<Article, Long> {

    Optional<Article> findById(Long id);

    Page<Article> findAll(Pageable pageable);

    List<Article> findAll(Sort sort);

    List<Article> findByStatus(ArticleStatus status);

    Optional<Article> findBySlug(String slug);

    boolean existsBySlug(String slug);

    long countByStatus(ArticleStatus status);
}
~~~~

In this example:

- The repository is still a Spring Data repository because it extends Repository<T, ID>.
- Only read methods are declared.
- Spring Data can derive queries from method names or handle the declared read methods.
- Spring Data REST can expose resources and read search methods according to configuration.
- No save, delete, or deleteAll exists in the contract for clients to accidentally invoke through this repository.

You can add Page, Slice, Sort, projections, or query methods as needed. Include in the interface only the read operations the API truly needs to support.

### When You Must Extend CrudRepository

Sometimes internal services need full CRUD while the public API must be read-only. There are two options:

1. Split into two interfaces: an internal repository with write access and a read repository dedicated to Spring Data REST. Name and configure scanning carefully to avoid inadvertently creating two repository beans managing the same domain type.
2. Keep one repository extending CrudRepository while redeclaring all write methods with @RestResource(exported = false). This keeps a single repository bean, but you must maintain the list of write methods when upgrading Spring Data or extending new interfaces.

If both the service layer and REST only need read access, extending Repository<T, ID> is usually the simpler contract.

## 6. Choosing the Right Exposure Approach

| Requirement | Design Approach |
|---|---|
| Read-only everywhere | Extend Repository<T, ID>, declare only finder/read methods |
| Internal repository needs writes, REST is read-only | Split read API or hide all write methods with @RestResource(exported = false) |
| Disallow REST access to repository | @RepositoryRestResource(exported = false) |
| Allow reading and single-item deletion | Selectively expose repository; verify item DELETE and authorization |
| Allow conditional deletion | Design a dedicated business endpoint with clear HTTP method, permissions, validation, and transaction |
| Allow bulk deletion | Restrict to admin roles; bound scope, batch size, auditing, and business confirmation |

Do not use **@RepositoryRestResource(exported = false)** when the goal is "read-only": that annotation disables the entire resource, including GET. To keep reads and disable writes, restrict write methods or build a read-only interface.

## 7. Read-Only at REST Does Not Mean the Database Cannot Be Written

Hiding write methods from Spring Data REST only limits the exposed endpoint surface. It does not prevent:

- A custom controller calling the repository to write.
- An internal service or scheduled job modifying data.
- Another application accessing the database using an account with write privileges.
- A custom query method with side effects being called through another path.

Therefore, for strictly protected data, combine multiple layers:

- **Repository contract:** declare only read methods in exposed repositories.
- **REST exposure:** hide write methods and avoid unintentionally exposing destructive endpoints.
- **Authorization:** restrict endpoints by role/authority; never rely on obscure URLs.
- **Database permissions:** use a SELECT-only database account for truly read-only applications or components when architecture permits.
- **Transaction:** use @Transactional(readOnly = true) for read flows to express intent and assist persistence provider optimizations. This is a hint/transaction setting, not a substitute for database privileges or an absolute security mechanism.
- **Auditing and logging:** record delete operations in flows that hold write access.

If one application needs both reads and writes across different features, separate database roles or service boundaries can enforce privileges to match each requirement.

## 8. Testing Read-Only Repositories

Test both the Java contract and the HTTP API:

1. **Interface check:** exposed repositories extend only Repository and declare no write methods.
2. **GET checks:** collection, item, paging/sorting, and read search resources work properly.
3. **HTTP write checks:** POST, PUT, PATCH, and DELETE are not exposed or are rejected per expected configuration. Exact status codes can depend on mappings and security filters; verify actual behavior rather than assuming 404 or 405.
4. **Hidden method checks:** when redeclaring methods with @RestResource(exported = false), verify corresponding routes do not appear in API profiles/mappings.
5. **Permission checks:** users with only a read role cannot invoke write endpoints on other controllers.
6. **Database checks:** if data-level enforcement is required, attempt a write using a read-only database account and confirm the database rejects it.

You can use MockMvc or Spring Boot integration tests to verify real requests. In development environments, HAL links/profiles and Actuator mappings (if enabled) also help confirm which affordances and handlers are exposed.

## 9. Conclusion

Delete overloads express distinct deletion scopes: by ID, by entity, by ID collection, by entity collection, or the entire repository. Derived delete queries and bulk deletes further differ in execution and entity lifecycle effects. Do not treat them as equivalent options in performance or impact.

If the goal is exposing a read-only API, prefer a repository extending Repository<T, ID> declaring only read methods. If extending CRUD is unavoidable, hide every write method—including store-specific extensions—and test mappings. Finally, combine authorization and database permissions if you must ensure no write path bypasses the REST layer.

## References

- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/CrudRepository.html)
- [Spring Data Commons — Repository marker interface](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/Repository.html)
- [Spring Data REST — Hiding repository resources and methods](https://docs.spring.io/spring-data/rest/reference/customizing/visibility.html)
- [Spring Data JPA — Derived delete queries](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html)
