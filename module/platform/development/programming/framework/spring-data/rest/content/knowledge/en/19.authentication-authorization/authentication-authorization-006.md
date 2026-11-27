# Reviewing All save, delete, and Inherited Method Variants in Spring Data REST

## Objective

Spring Data REST can automatically publish repositories as REST resources. Write and delete operations on the Java side typically rely on inherited Spring Data methods such as save, saveAll, delete, deleteById, and store-module variants.

When designing authentication and authorization, do not look only at POST or DELETE at the HTTP boundary. List every path capable of mutating data:

- CRUD methods inherited from CrudRepository, ListCrudRepository, PagingAndSortingRepository, and JpaRepository.
- JPA save/flush and delete/batch variants.
- Derived delete queries, custom repository fragments, and self-declared methods.
- Standard Spring Data REST endpoints.
- Association resources that can modify relationships.
- Services, controllers, batch jobs, scheduled tasks, and message consumers that call repositories directly.

The goal is to determine who is allowed to create, update, delete a single entity, or delete in bulk; check permissions per entity; and ensure every write path adheres to the same business rules.

## 1. Distinguishing repository methods and REST endpoints

Spring Data REST maps several standard HTTP operations to collection, item, and association resources:

| Resource | Typical HTTP method | Effect |
|---|---|---|
| Collection, e.g., /api/people | GET | Read collection. |
| Collection | POST | Create a new entity. |
| Item, e.g., /api/people/42 | GET | Read entity. |
| Item | PUT | Replace representation per endpoint semantics. |
| Item | PATCH | Partially update representation. |
| Item | DELETE | Delete entity. |
| Association resource | GET | Read relationship. |
| Association resource | PUT/POST/DELETE depending on relation type | Modify or remove links. |

These URIs form the HTTP surface. Spring Data REST does not create a separate URL for every Java method such as saveAll, deleteAll, or saveAndFlush merely because the repository inherits them.

The REST exporter uses repository metadata and a repository invoker to perform standard operations. The exact method invoked can depend on the Spring Data REST version, repository type, and store module. Therefore, when protecting methods at the repository level, test the actual HTTP requests and repository proxy in your target version.

Conversely, bulk methods can still be invoked by services, controllers, jobs, or internal code even without corresponding standard REST endpoints.

## 2. Reviewing CrudRepository

CrudRepository provides the core set of operations. This is the starting checklist:

| Method | Effect | Risk to verify |
|---|---|---|
| save(entity) | Saves a new entity or updates an existing entity. | May write properties beyond the caller's permissions. |
| saveAll(entities) | Saves multiple entities. | A single call may affect multiple tenants or owners. |
| deleteById(id) | Deletes by ID. | ID may point to an entity outside permitted scope. |
| delete(entity) | Deletes the passed entity. | Caller might pass an entity they are not allowed to delete. |
| deleteAllById(ids) | Deletes multiple entities by ID. | Must validate all IDs and limit count. |
| deleteAll(entities) | Deletes entities in the iterable. | Can delete multiple entities at once. |
| deleteAll() | Deletes the entire repository. | Broad impact, usually reserved for administrative tasks. |

Do not assume deleteById is the only delete path. If code can call delete(entity), deleteAllById, or deleteAll, policies must cover those methods as well.

Similarly, protecting save does not automatically prove saveAll is protected. Review every method actually present in the interface hierarchy and those overridden.

## 3. ListCrudRepository and PagingAndSortingRepository

Depending on the Spring Data version, a repository may extend ListCrudRepository and PagingAndSortingRepository.

ListCrudRepository offers similar CRUD operations where some methods return List instead of Iterable, for example:

~~~java
<S extends T> List<S> saveAll(Iterable<S> entities);
List<T> findAll();
List<T> findAllById(Iterable<ID> ids);
~~~

saveAll remains a bulk write operation and needs the same level of control as other variants.

PagingAndSortingRepository mainly adds paginated and sorted read capabilities. While not a write group, still inspect the full interface hierarchy to know everything the repository actually inherits.

Do not rely on memory of a different Spring Data version. Hierarchies, method signatures, and return types can change across versions. Inspect your actual dependency and repository interfaces.

## 4. Write and delete variants of JpaRepository

JpaRepository adds methods related to flushing and batching.

### The save group

| Method | Effect | Required controls |
|---|---|---|
| save(entity) | Saves one entity. | Create/update permission and allowed writable properties. |
| saveAll(entities) | Saves multiple entities. | Per-entity permission and batch limits. |
| saveAndFlush(entity) | Saves and flushes the persistence context. | Same policy as save; flush adds no authorization. |
| saveAllAndFlush(entities) | Saves multiple entities and flushes. | Same policy as saveAll; control bulk scope. |

### The delete group

| Method | Effect | Required controls |
|---|---|---|
| delete(entity) | Deletes one entity. | Verify entity, tenant, owner, and state. |
| deleteById(id) | Deletes by ID. | Do not trust ID; check permissions on target entity. |
| deleteAll(entities) | Deletes passed entities. | Check each entity or constrain dataset. |
| deleteAllById(ids) | Deletes by list of IDs. | Validate all IDs and limit count. |
| deleteAll() | Deletes the entire repository. | Special permission and administrative procedure. |
| deleteAllInBatch(entities) | Deletes multiple entities in a batch. | Control dataset and JPA semantics. |
| deleteAllByIdInBatch(ids) | Deletes by IDs in a batch. | Check tenant, ownership, and count. |
| deleteAllInBatch() | Deletes all data in a batch. | Very broad impact; disallow for normal callers. |

Some versions have older methods like deleteInBatch(entities), which may be deprecated or replaced. If the codebase still calls them, include them in the audit list.

### Flush is not a security boundary

saveAndFlush and saveAllAndFlush change when the persistence context synchronizes with the database. They do not add authorization or validation.

Batch deletes can execute directly via a query without loading each entity to run full lifecycle callbacks. They may not follow cascade and entity lifecycle semantics the same way single-entity deletes do. Entities held in the persistence context may not immediately reflect database state after a bulk operation.

Before using batch methods, understand their impact on transactions, foreign keys, cascades, callbacks, and JPA provider flush/clear behavior.

## 5. Do not overlook custom and derived mutation methods

Repositories can also define other data-mutating paths:

- Derived delete methods such as deleteByStatus or removeByStatus.
- Queries annotated with @Modifying.
- Custom repository fragments.
- Default methods on interfaces.
- Store-specific methods.
- Services using EntityManager or templates directly.
- Controllers invoking repositories with custom logic.

Example:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long>, PersonRepositoryCustom {

    long deleteByStatus(PersonStatus status);
}
~~~

deleteByStatus is a delete path even without the name deleteAll. If called by the application or exposed via a custom API, check permissions, tenant scope, record count, and auditing.

Custom fragments must also have their implementations reviewed. Methods named archive, purge, reassignOwner, or transferTenant can still mutate data even without save or delete in the name.

## 6. Method security on repository methods

Spring Security method security can protect calls through the repository proxy. Enable method security:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {
}
~~~

You can override inherited methods in the repository to declare policies:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @Override
    @PreAuthorize("hasAuthority('people:write')")
    <S extends Person> S save(S entity);

    @Override
    @PreAuthorize("hasAuthority('people:write')")
    List<Person> saveAll(Iterable<Person> entities);

    @Override
    @PreAuthorize("hasAuthority('people:delete')")
    void deleteById(Long id);

    @Override
    @PreAuthorize("hasAuthority('people:delete')")
    void delete(Person entity);
}
~~~

This is an illustrative example. Signatures must match your actual interfaces and version; saveAll's return type may be Iterable or List depending on the inherited interface.

If only deleteById is annotated, internal callers can still invoke delete(entity), deleteAllById, deleteAll, or batch deletes. Declare policies for every method in use.

Example bulk delete group needing dedicated protection:

~~~java
@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllById(Iterable<? extends Long> ids);

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAll();

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllInBatch(Iterable<Person> entities);

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllByIdInBatch(Iterable<Long> ids);

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllInBatch();
~~~

Adjust these signatures to match your JpaRepository version. If a method is unnecessary, omit it from the service API or hide it from the REST exporter if clients should not invoke it over HTTP.

### save does not automatically distinguish create and update

save can be used for both new entities and existing entities. A single annotation on save does not automatically separate create permission from update permission.

If create and update require different permissions, use separate service commands or policies that check entity state appropriately. A service can inspect ID/state, principal, and tenant before calling the repository.

## 7. Distinguishing method security and REST exposure

The two mechanisms serve different purposes:

- REST exposure decides whether Spring Data REST publishes an HTTP operation.
- Method security protects method calls through the repository proxy, including internal callers if routed through the protected proxy.

You can hide an inherited method from Spring Data REST by overriding it with exported=false:

~~~java
@Override
@RestResource(exported = false)
void deleteAll();
~~~

This controls exporting the method over REST. It does not prevent other Java code from calling repository.deleteAll().

If the entire repository should not be exposed over REST:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalPersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Hiding a repository is a resource-level decision. It does not replace authorization for services or repositories that are still injected and called internally.

## 8. Restricting HTTP methods with ExposureConfiguration

Spring Data REST allows controlling HTTP methods on collection and item resources by domain type.

Example allowing only reading Person via repository REST:

~~~java
@Configuration
class RestExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .forDomainType(Person.class)
            .withCollectionExposure((metadata, methods) ->
                methods.disable(HttpMethod.POST))
            .withItemExposure((metadata, methods) ->
                methods.disable(
                    HttpMethod.PUT,
                    HttpMethod.PATCH,
                    HttpMethod.DELETE
                ));
    }
}
~~~

POST on the collection is disabled; PUT/PATCH/DELETE on items are disabled. GET can remain enabled.

Exposure configuration controls Spring Data REST's HTTP surface. It does not disable saveAll, deleteAllInBatch, or repository calls from services/jobs. Association resources must also be reviewed separately if clients can modify relationships.

## 9. Separating create, update, delete, and bulk permissions

An easily testable policy typically separates permissions by task:

| Example authority | Scope |
|---|---|
| people:read | Read collections and items. |
| people:create | Create Person. |
| people:update | Update existing Person. |
| people:delete | Delete one Person within allowed scope. |
| people:delete:bulk | Delete multiple Person records. |
| people:admin | Special administrative operations. |

Authority names are examples; align them with your actual permission model.

You do not have to use a single people:write permission for every method. Bulk deletes usually carry a much larger impact than single-item deletes. deleteAll or deleteAllInBatch can wipe an entire repository, so they need separate permissions or should not be offered to normal operational flows.

## 10. Checking tenant, owner, and state before writing/deleting

Authorization is more than checking roles. With multi-tenant or owned data, inspect the target entity.

Example service deleting a Person:

~~~java
@Transactional
public void deletePerson(Long id, CurrentUser user) {
    Person person = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException());

    if (!person.getTenantId().equals(user.tenantId())) {
        throw new AccessDeniedException("Not allowed");
    }

    if (!user.canDeletePeople()) {
        throw new AccessDeniedException("Not allowed");
    }

    repository.delete(person);
}
~~~

The order is: load entity, verify tenant/ownership, check business permission, and only then call delete.

For bulk deletes, do not check just one representative ID. Identify the entire affected entity set, verify all belong to allowed scope, and enforce count limits. For large datasets, use a dedicated service operation with explicit query criteria and thorough auditing.

For save/update, check both current state and incoming data. For example, an APPROVED Person might not allow changing owner or tenant even if the caller has profile-editing permissions.

## 11. Controlling association updates

Spring Data REST can allow clients to change associations via the target entity's URI. Therefore, inspect not only POST/PUT/PATCH/DELETE on items, but also association resources.

When assigning an association, the server must verify:

- Does the principal have permission to modify the source entity?
- Which tenant/owner does the source entity belong to?
- Does the target entity exist and fall within allowed scope?
- Is the relationship valid in the current workflow state?
- What data might cascade, orphan removal, or foreign keys affect?

Hiding association links is not enough to protect the endpoint. Clients can call the URI directly. Test both association requests and JSON binding into relationship properties.

## 12. Bulk operations and auditing

Methods such as deleteAll, deleteAllById, deleteAllInBatch, and deleteAllByIdInBatch have broad impact. You should:

- Resolve the affected record set before executing.
- Never trust ID lists from the client.
- Cap the number of records per call.
- Use dedicated permissions for bulk operations.
- Audit the actor, query criteria, record count, and timestamp.
- Consider soft delete/archiving if recovery is needed.
- Check foreign keys and related data.
- Understand differences between single-entity deletion and bulk queries.

Batch deletes can bypass normal entity lifecycle callbacks and cascade semantics. Consider flush/clear behavior and transaction boundaries per JPA provider.

Do not adopt bulk methods solely for performance optimization before understanding their business and security impact.

## 13. Auditing the interface chain and codebase

An audit process:

1. Find all repository interfaces.
2. Record parent interfaces: CrudRepository, ListCrudRepository, PagingAndSortingRepository, JpaRepository, or store-specific interfaces.
3. List inherited write/delete methods.
4. Check which methods are overridden in child repositories.
5. Check @PreAuthorize, @Secured, @RolesAllowed, or equivalent policies.
6. Find custom repository fragments and default methods.
7. Find derived delete methods and @Modifying queries.
8. Find controllers/services calling save/delete directly.
9. Find batch jobs, scheduled tasks, listeners, and message consumers.
10. Inspect Spring Data REST exposure configuration.
11. Test calls via HTTP and via repository proxies.

Useful search terms:

~~~text
save(
saveAll(
saveAndFlush(
saveAllAndFlush(
delete(
deleteById(
deleteAll(
deleteAllById(
deleteAllInBatch(
deleteAllByIdInBatch(
deleteInBatch(
deleteBy
removeBy
@Modifying
~~~

This is a starting point; expand it to match your application's custom repository APIs and store modules.

## 14. Authorization test matrix

Do not test only REST endpoints. Test method security on repository proxies and service paths.

Example matrix:

| Caller | save | saveAll | deleteById | deleteAll | deleteAllInBatch |
|---|---|---|---|---|---|
| Anonymous | Denied | Denied | Denied | Denied | Denied |
| Read-only user | Denied | Denied | Denied | Denied | Denied |
| User with update | Per scope | Per bulk policy | Denied if missing delete permission | Denied | Denied |
| Admin with bulk permission | Allowed | Per scope | Allowed | Per policy | Per policy |

This is an illustrative policy; replace it with your application's permission model.

Tests should cover:

- POST collection without create permission.
- PUT/PATCH item without update permission.
- DELETE item without delete permission.
- Calling save and saveAll through the repository proxy.
- Calling every delete variant used by the application.
- Bulk delete with IDs belonging to another tenant.
- deleteAll by a user who only has single-item delete permission.
- Methods hidden via exposure are rejected over REST.
- Java calls remain protected by method security if the method still exists.
- Database remains unchanged after denied requests.

With Spring Security 6, @EnableMethodSecurity enables method security. Older projects may use @EnableGlobalMethodSecurity(prePostEnabled = true); use the configuration compatible with your actual version.

## 15. Common pitfalls

1. **Protecting only save and deleteById.** saveAll, delete(entity), deleteAllById, and batch deletes can still be called.
2. **Assuming each repository method has its own URL.** Spring Data REST maps standard HTTP operations, not an endpoint for every Java method.
3. **Hiding HTTP methods and assuming services cannot call the repository.** Exposure only controls the REST surface.
4. **Marking exported=false and assuming the Java method is disabled.** It controls exporting, not internal invocations.
5. **Overlooking inherited methods.** Always audit the full interface hierarchy.
6. **Overlooking saveAll.** Writing multiple entities has a different blast radius than saving a single entity.
7. **Overlooking deleteAllInBatch.** Batch deletes can remove large datasets and carry different JPA semantics.
8. **Using the same permission for single-item delete and deleting the entire repository.** Bulk operations need separate permissions.
9. **Trusting client-supplied IDs.** Always verify the target entity, tenant, and ownership.
10. **Assuming flush adds security.** Flush only synchronizes the persistence context with the database.
11. **Forgetting custom fragments and derived delete queries.** Differently named methods can still delete data.
12. **Testing only HTTP endpoints.** Internal jobs/services can call repositories directly.
13. **Checking only roles.** Permissions may depend on tenant, owner, or workflow state.
14. **Using batch deletes without understanding cascade/lifecycle.** Bulk queries can bypass callbacks and cascade semantics.
15. **Relying on UI or HAL links to protect operations.** The server must enforce permissions on every request and method invocation.

## 16. Pre-production checklist

- Listed all parent interfaces and inherited methods.
- Audited save, saveAll, saveAndFlush, and saveAllAndFlush.
- Audited delete, deleteById, deleteAll, and deleteAllById.
- Audited JPA batch deletes and deprecated methods still in use.
- Audited derived deletes, custom fragments, and self-declared methods.
- Identified which REST endpoints trigger write/delete operations.
- Configured exposure for collection, item, and association resources.
- Applied method security to write paths requiring protection.
- Separated permissions for create, update, single-item delete, and bulk delete.
- Enforced server-side checks for tenant, owner, state, and associations.
- Enforced count limits on bulk operations.
- Added audit logging for sensitive operations.
- Tested via both HTTP and repository proxies.
- Verified denied requests leave the database unchanged.
- Accounted for transactions, cascades, lifecycle callbacks, and persistence context behavior of batch operations.

## Summary

When auditing authentication and authorization for Spring Data REST, examine all write/delete methods inherited from repositories, not just POST and DELETE endpoints. The core set includes save, saveAll, delete, deleteById, deleteAll, and deleteAllById. For JPA, also inspect saveAndFlush, saveAllAndFlush, deleteAllInBatch, deleteAllByIdInBatch, and any remaining version-specific variants.

Exposure configuration and @RestResource(exported = false) control API publishing. @PreAuthorize with method security protects repository/service invocations. Validation, tenant/ownership checks, and domain rules decide whether a change is legitimate. Bulk operations need dedicated policies because they can affect many records and have different persistence semantics from single-entity deletions.

Audit the interface chain, custom repositories, controllers, services, batch jobs, and scheduled tasks; then test each call path with different principals and verify the database remains unchanged when operations are denied.

## References

- [Spring Data Commons — Repository Core Concepts](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html)
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html)
- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Configuring the REST URL Path and Exposure](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
