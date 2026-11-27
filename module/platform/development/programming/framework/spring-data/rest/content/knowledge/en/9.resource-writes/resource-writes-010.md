# Deleting Resources with DELETE and the Impact of Data Constraints

## Objectives

Spring Data REST allows clients to delete an entity via HTTP DELETE on an item resource. For example, if a repository manages Customer and the collection path is /customers, the customer item with ID 1001 is accessed at:

    DELETE /customers/1001

This request can permanently remove real data in the persistence store. The outcome depends on the delete methods exposed by the repository, entity state, JPA relationships, foreign keys, cascades, triggers, and the application's business rules.

When designing or investigating DELETE, answer:

1. Does the URL point to an item resource or an association resource?
2. Which delete methods does the repository expose?
3. Is the entity allowed to be deleted under business rules?
4. Are other entities referencing the entity to be deleted?
5. What effects do JPA cascade, orphan removal, or database ON DELETE have?
6. If the database rejects the operation, what happens to the transaction and HTTP response?

## 1. DELETE on an item resource

Spring Data REST creates an item resource for each entity under the collection resource. If the collection is /customers, an item typically has URI /customers/{id}.

Repository example:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Request to delete an item:

    curl -i -X DELETE \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/1001

DELETE on an item resource requests deleting the entity represented by that URI. This is a repository entity deletion operation, distinct from merely removing an association link.

### 1.1. Distinguishing item DELETE and association DELETE

The following two URLs have different meanings:

| Request | Meaning |
|---|---|
| DELETE /customers/1001 | Deletes the Customer entity with ID 1001 |
| DELETE /customers/1001/orders | Unbinds the orders association from Customer 1001 |

DELETE on an association resource only unbinds the association. It does not automatically delete the linked entity. If you want to delete an Order, the client must call DELETE on the Order's item resource, using the item URL provided by HAL.

This distinction is especially important for one-to-many and many-to-many relationships. Removing an element from a collection association and deleting the entity itself are two different data changes.

### 1.2. Successful HTTP response

By default in Spring Data REST, the DELETE response depends on the Accept header:

- When the request includes an Accept header, the response may return the entity representation with status 200 OK.
- When the request has no Accept header, a successful response typically has no body and returns 204 No Content.

This behavior can be changed via RepositoryRestConfiguration.setReturnBodyOnDelete(...).

Example configuration to return a body after deletion:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setReturnBodyOnDelete(true);
        }
    }

Distinguish the DELETE operation's status from the database deletion outcome. A 200 or 204 response should only be returned when the operation has been processed successfully per the endpoint contract.

### 1.3. DELETE not exported

Spring Data REST only exposes an HTTP method when the repository has the corresponding method and that method is allowed to be exported.

If the repository lacks a suitable delete method, or the delete method is marked exported = false, the item resource does not support DELETE and may return:

    405 Method Not Allowed

Collection resources support only GET and POST by default. Do not send DELETE to /customers for bulk deletion. Standard item resource DELETE must target a specific item.

## 2. Repository methods used

Spring Data REST maps item resource DELETE to repository delete methods. The Repository resources documentation describes the lookup order as:

1. delete(entity)
2. delete(id)
3. delete(iterable)

Specific public signatures vary across Spring Data generations. In modern CrudRepository, common methods are:

    void delete(T entity);
    void deleteById(ID id);
    void deleteAllById(Iterable<? extends ID> ids);
    void deleteAll(Iterable<? extends T> entities);
    void deleteAll();

Do not assume every version shares the exact same method names. Check the CrudRepository interface and Spring Data REST version used by your application.

### 2.1. Deleting an entity vs. deleting by ID

There are two common approaches:

- Delete entity: the repository receives an entity object and deletes it.
- Delete by ID: the repository receives an identifier and attempts to delete the corresponding record.

With Spring Data JPA, deleting an entity typically goes through EntityManager.remove on a managed entity. The repository implementation may load the entity before deleting to support lifecycle events and optimistic locking.

With deleteById, modern CrudRepository specifies that if the ID does not exist in the persistence store, the operation may be silently ignored. However, the REST flow may need to load the entity to emit events or process the item resource. Therefore, do not infer the HTTP status code solely from a repository method's Javadoc; verify the behavior of your actual Spring Data REST version.

### 2.2. Deleting multiple entities is not item DELETE

Methods such as deleteAll(), deleteAllById(...), or deleteAll(Iterable) have a broader scope than deleting a single item.

Do not create a collection DELETE endpoint calling deleteAll() unless the API has an explicit requirement, permission restrictions, and confirmation mechanisms. Bulk deletion can affect large amounts of data and requires a dedicated contract, typically through a well-designed service or business endpoint.

### 2.3. Hiding DELETE from the REST API

If a repository still needs a delete method for internal logic but you do not want clients calling it over HTTP, you can:

- Mark the appropriate delete methods with @RestResource(exported = false), based on the signatures of the Spring Data version in use.
- Use RepositoryRestConfiguration.getExposureConfiguration() to disable HTTP DELETE for item resources.

Example disabling DELETE across all item resources:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.DELETE));
        }
    }

The configuration above applies to item resources in general. If you only want to block deletion for one domain type, use exposure rules per domain type suited to your version's API or organize the repository so delete methods are not exported for that type.

## 3. Processing flow when DELETE is called

A typical deletion flow can be understood through the following steps:

1. The client sends DELETE to the item URI.
2. Spring MVC routes the request to the repository's item resource.
3. The framework converts the ID in the URI to the backend ID type and identifies the entity to process.
4. Spring Data REST publishes BeforeDeleteEvent.
5. The repository delete method is called.
6. The persistence provider marks the entity for removal and synchronizes changes to the database on flush or commit.
7. If the operation succeeds, Spring Data REST publishes AfterDeleteEvent and builds the response per configuration.
8. If the operation fails, the transaction may roll back and the exception is passed through the application's error-handling mechanism.

Internal details may vary by store module and version. The important point is that DELETE is not just deleting a SQL row: the repository, persistence context, event handlers, and database constraints can all participate.

## 4. Foreign keys and referential constraints

Foreign keys ensure that a child row does not reference a nonexistent parent row. For example:

- Customer is the parent table.
- Order has a customer_id column referencing Customer.id.
- One Customer can be referenced by many Orders.

If Customer 1001 still has Orders referencing it, the database may reject DELETE on Customer 1001 to protect data integrity.

Relationship example:

    Customer
      id (PK)
       |
       +---- Order.customer_id (FK)

When the client sends DELETE /customers/1001, the database may report a foreign key constraint error if Orders still reference it and the foreign key is configured with RESTRICT or NO ACTION.

### 4.1. Common ON DELETE policies

| Policy | Outcome when deleting a parent row |
|---|---|
| RESTRICT | Rejects deletion if child rows still reference it |
| NO ACTION | Checks constraint per database rules; typically rejects if references remain |
| CASCADE | Database deletes referencing child rows |
| SET NULL | Database sets foreign key in child rows to NULL if the column allows it |
| SET DEFAULT | Database sets foreign key to default value if supported and valid |

Not every database supports all policies in the same way. Constraint checking timing can also vary, such as checking immediately when the statement executes or at transaction commit if the constraint is declared deferred.

### 4.2. When should RESTRICT be kept?

RESTRICT is appropriate when child entities are independent business data that must be retained. For example, a Customer should not be deleted if existing Orders must be kept for auditing, invoicing, or reporting.

In this case, the application can:

- Reject the deletion and require the user to handle related Orders.
- Transition the Customer to an inactive or archived state.
- Unlink the relationship only when business rules allow and child data can exist independently.

Do not enable CASCADE merely to avoid foreign key errors. Clearly determine whether child data genuinely loses meaning when the parent entity is deleted.

## 5. JPA CascadeType.REMOVE and orphanRemoval

JPA provides cascading to propagate persistence operations from one entity to related entities. Two configurations often confused are CascadeType.REMOVE and orphanRemoval.

### 5.1. CascadeType.REMOVE

CascadeType.REMOVE propagates the remove operation from the source entity to the target entity of the configured association.

For example, an Order owns OrderLines, and an OrderLine has no independent meaning:

    @Entity
    public class Order {

        @OneToMany(
            mappedBy = "order",
            cascade = CascadeType.REMOVE
        )
        private List<OrderLine> lines = new ArrayList<>();
    }

When deleting Order, JPA also deletes the linked OrderLines via cascade remove.

Cascading is directional. Deleting a child does not automatically delete the parent just because a parent-child relationship exists. In a one-to-many relationship, cascading is typically configured from parent to child, because the parent manages the child's lifecycle.

Jakarta Persistence specifies that CascadeType.REMOVE should be used on OneToOne or OneToMany relationships to ensure portability. Do not arbitrarily place REMOVE on ManyToOne or ManyToMany.

### 5.2. orphanRemoval

orphanRemoval = true is used for OneToOne and OneToMany relationships. When a child is removed from its owner's relationship, JPA applies a remove operation to that child when the persistence context flushes.

Example:

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

If an OrderLine is removed from the lines collection and is no longer attached to the Order, it is considered an orphan and will be deleted.

Distinction:

- CascadeType.REMOVE: deleting the parent propagates the deletion to the children.
- orphanRemoval: removing a child from the owning relationship causes that child to be deleted.
- Removing an association via REST: changes the link via the association resource API; the final result also depends on mapping and persistence semantics.

orphanRemoval is suitable for children exclusively owned by a parent. Do not use it for objects shared across multiple aggregates or that need to exist independently.

### 5.3. CascadeType.ALL

CascadeType.ALL includes REMOVE along with other cascade operations such as PERSIST, MERGE, REFRESH, and DETACH.

Do not choose ALL just because you want to delete children along with the parent. If only cascading deletion is needed, CascadeType.REMOVE expresses a narrower and clearer intent.

## 6. Database cascade vs. JPA cascade

JPA cascade and database ON DELETE CASCADE are two different mechanisms.

| Mechanism | Where it executes | Behavior |
|---|---|---|
| CascadeType.REMOVE | JPA persistence provider | Propagates EntityManager.remove across the association |
| orphanRemoval | JPA persistence provider | Deletes child when detached from association owner |
| ON DELETE CASCADE | Database foreign key | Database automatically deletes child rows when parent row is deleted |

Hibernate has its own annotation @OnDelete(action = CASCADE) to generate a foreign key with ON DELETE CASCADE. This is a Hibernate extension, not a standard Jakarta Persistence annotation.

When the database deletes child rows automatically, the persistence context may not know about all deleted rows. Managed entities or the second-level cache can fall out of sync if the application does not handle it appropriately.

Therefore, when choosing database cascade:

- Verify that DDL actually creates the foreign key with ON DELETE CASCADE.
- Check caches and the persistence context.
- Verify whether JPA lifecycle callbacks need to run for each child.
- Check triggers and audit logs.
- Do not assume database cascade will fire JPA entity callbacks like individual entity removal does.

## 7. Data constraint errors and transactions

When the database rejects DELETE due to a foreign key or other constraint, the persistence provider typically raises a persistence exception. Spring can translate this error into DataIntegrityViolationException or an appropriate DataAccessException.

Example:

    try {
        customerRepository.deleteById(customerId);
        customerRepository.flush();
    } catch (DataIntegrityViolationException ex) {
        // Translate the failure into the API's documented error response.
    }

The example above is only suitable when the repository is a JpaRepository and the code runs inside a properly managed transaction service. Do not catch an exception and then continue using a transaction already marked rollback-only.

### 7.1. Why can errors appear at flush or commit time?

JPA often defers SQL until the persistence context flushes. Therefore, the delete call might not send a DELETE statement immediately when the method returns.

A foreign key error can surface:

- Directly during the repository call if the provider flushes early.
- When code calls EntityManager.flush or JpaRepository.flush.
- When the transaction commits and the framework performs the final flush.

If a constraint is only checked at commit time, catching exceptions inside a method before commit may miss the final error. Place exception handling at the appropriate transaction boundary.

### 7.2. Transaction rollback

When DELETE fails and the transaction rolls back:

- The database does not retain partial changes from the rolled-back transaction.
- Entities already marked removed in the persistence context may need handling according to the transaction lifecycle.
- Do not continue using a failed persistence context as if the deletion succeeded.
- The API must return a consistent error so the client knows the entity was not successfully deleted.

Do not send "deleted" notifications or emit events to external systems before the transaction commits successfully. If you need to publish messages after durable deletion, consider TransactionalEventListener with phase AFTER_COMMIT or a transactional outbox.

### 7.3. HTTP status when a constraint is violated

DataIntegrityViolationException is a data-access-layer exception. Spring Data REST and Spring MVC may map exceptions through different handlers depending on version and configuration.

Do not assume every foreign key error automatically returns 409 Conflict. If the API needs an explicit contract, configure an exception handler to translate appropriate cases into intentional status codes, for example:

- 409 Conflict: entity is still referenced or business state prevents deletion.
- 422 Unprocessable Content: syntactically valid request cannot be executed per business rules, if the API chooses this status.
- 404 Not Found: resource does not exist per the endpoint contract.
- 405 Method Not Allowed: DELETE is not exported or not allowed on that resource.

The response body should have a stable error code and clear message. Do not return raw SQL, internal table names, sensitive values, or stack traces to clients.

## 8. Spring Data REST events and JPA lifecycle callbacks

Spring Data REST emits events during repository operations, including:

- BeforeDeleteEvent: before the entity is deleted.
- AfterDeleteEvent: after the entity delete operation is executed.

You can use an annotated handler:

    @Component
    @RepositoryEventHandler(Customer.class)
    public class CustomerDeleteHandler {

        @HandleBeforeDelete
        public void beforeDelete(Customer customer) {
            if (customer.isProtected()) {
                throw new IllegalStateException(
                    "Customer cannot be deleted");
            }
        }

        @HandleAfterDelete
        public void afterDelete(Customer customer) {
            // Record application-level notification.
        }
    }

A BeforeDelete handler can check business rules and reject the request with an exception. Map that exception to an appropriate API error.

JPA also has entity lifecycle callbacks such as @PreRemove and @PostRemove:

    @PreRemove
    public void beforeRemove() {
        // Local entity lifecycle validation or bookkeeping.
    }

Difference:

| Mechanism | Scope |
|---|---|
| BeforeDeleteEvent / AfterDeleteEvent | Spring Data REST events when the REST exporter processes an entity |
| @HandleBeforeDelete / @HandleAfterDelete | Handlers that can filter by domain type |
| @PreRemove / @PostRemove | JPA entity lifecycle callbacks when the persistence provider performs remove |

Not every way of deleting data goes through the same pipeline. Bulk JPQL deletes, native SQL, or database cascades can bypass certain entity lifecycle callbacks. Choose the mechanism that matches the deletion path the application actually uses.

Spring application events are processed synchronously by default. However, AfterDeleteEvent should not be treated as proof that the transaction has durably committed. For external side effects such as sending email, calling webhooks, or publishing messages, handle them at the AFTER_COMMIT boundary or use an outbox to avoid notifying of deletion when the transaction ultimately rolls back.

## 9. Designing soft delete

Soft delete does not physically remove rows from the database. Instead, the application marks the entity as deleted or archived.

Example:

    @Entity
    public class Customer {

        @Id
        private Long id;

        private boolean deleted;
        private Instant deletedAt;
    }

When the client sends DELETE, the service can update deleted = true and deletedAt instead of calling physical repository deletion.

Clearly design:

- Do collection GET and item GET hide soft-deleted entities?
- Is there a restore endpoint?
- Do unique constraints account for soft-deleted entities?
- Do associations and query methods exclude deleted data?
- Who is allowed to view archived data?
- Where does the audit log store who deleted it and when?

Spring Data REST by default interprets DELETE as a repository delete operation. Soft delete typically requires a custom repository implementation, service, or custom REST endpoint to change state according to business rules. Do not just rename a method and assume all resources and queries automatically filter deleted data.

## 10. Securing the DELETE endpoint

Exporting a repository via REST does not mean every user is authorized to delete entities.

Configure separate authorization for DELETE:

- Only appropriate roles may delete.
- Verify tenant or ownership before deleting.
- Do not trust client-sent IDs alone as proof of access permission.
- Consider CSRF if the API uses cookie-based authentication.
- Audit actor, entity ID, timestamp, and deletion reason per business requirements.
- Do not let event handlers perform non-rollbackable side effects before transaction commit.

For critical data, a confirmation workflow, archived state, or approval step may be needed instead of direct physical deletion.

## 11. Checklist for investigating failed DELETE

When DELETE fails, check in order:

1. Is the URI the item resource of the entity to delete?
2. Does the repository have a suitable delete method and is that method exported?
3. Is HTTP DELETE disabled by RepositoryRestConfiguration or Spring Security?
4. Can the ID in the URI be converted to the backend ID?
5. Does the entity exist in the repository?
6. Is a BeforeDelete handler or business rule rejecting the operation?
7. Are other entities referencing it via foreign keys?
8. Does the JPA mapping have appropriate CascadeType.REMOVE or orphanRemoval?
9. Is the database foreign key using RESTRICT, NO ACTION, CASCADE, or SET NULL?
10. Are there triggers, check constraints, or other database rules?
11. Does the exception occur at repository call, flush, or transaction commit?
12. Did the transaction roll back?
13. Do the HTTP status and response body match the API contract?
14. If using caches or message events, is external data synchronized after commit?

Do not fix errors by blindly disabling foreign keys or turning on cascade. First determine the data relationships and business meaning of each entity.

## 12. Testing DELETE

A good integration test should verify both the HTTP response and persistence state.

Cases to include:

| Case | What to verify |
|---|---|
| Delete existing entity, no dependent rows | Repository deletes entity and response matches configuration |
| Delete nonexistent entity | Status and body match actual contract |
| Delete entity referenced by child with RESTRICT | Database rejects, transaction rolls back |
| Delete parent with CascadeType.REMOVE | Children are deleted per mapping |
| Delete parent with orphanRemoval | Child detached from association is deleted on flush |
| Delete association resource | Only unbinds association, does not automatically delete related entity |
| Repository does not export delete | Item DELETE returns 405 |
| BeforeDelete handler rejects | No durable change and API returns business error |
| Constraint fails at commit | Exception caught at appropriate transaction boundary |
| Soft delete | Entity is marked deleted and no longer appears in public queries |

State verification example:

    mockMvc.perform(delete("/customers/{id}", customerId))
        .andExpect(status().isNoContent());

    assertThat(customerRepository.existsById(customerId)).isFalse();

The example above assumes a configuration returning no response body and an entity with no constraints blocking deletion. In actual tests, use the status codes and data state defined by your API.

## References

- [Spring Data REST — Repository resources, item DELETE and association DELETE](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing supported HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Jakarta Persistence — Entity removal and orphan removal](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Hibernate — OnDelete annotation](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/OnDelete.html)
- [Spring Framework — DataIntegrityViolationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)