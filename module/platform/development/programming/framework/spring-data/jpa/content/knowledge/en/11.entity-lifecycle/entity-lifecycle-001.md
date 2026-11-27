# Transient, managed, detached, and removed states

JPA does not just map a Java class to a database table. It also manages the lifecycle of each entity object within a **persistence context**. Depending on which state the object is in, JPA can track changes, automatically write data, ignore changes, or schedule the object for deletion from the database.

Four core states to distinguish:

- **Transient (new)**: a new Java object, not yet managed by a persistence context and with no corresponding managed record in the database.
- **Managed**: an object currently managed by a persistence context; changes can be detected and synchronized by dirty checking.
- **Detached**: an object that was previously managed but is no longer part of that persistence context; changes are not automatically synchronized.
- **Removed**: an entity currently managed but marked for deletion; a DELETE statement will be executed on flush.

Understanding the states properly helps you know when to call persist, merge, or remove, why you do not need to call save after every change, and why a detached entity does not automatically update the database.

**Example prerequisites:** the code snippets use Spring Boot 3.x, Java 17 or later, and Jakarta Persistence. The application requires the spring-boot-starter-data-jpa dependency, a JDBC driver, a DataSource, and an appropriate schema. The snippets are parts of a Spring Boot application, not standalone programs that can be run with javac alone.

## 1. What is a persistence context?

A persistence context is a set of entity instances managed by JPA within a unit of work. EntityManager is the primary API for interacting with the persistence context.

A persistence context has several key responsibilities:

1. Tracking managed entities and their changes.
2. Maintaining an identity map: within the same persistence context, one entity identifier corresponds to a single managed instance.
3. Performing dirty checking to detect changes.
4. Scheduling INSERT, UPDATE, and DELETE operations.
5. Synchronizing changes to the database on flush.

For example, within the same persistence context:

~~~java
Book first = entityManager.find(Book.class, 10L);
Book second = entityManager.find(Book.class, 10L);

System.out.println(first == second);
~~~

For the same entity type and ID in the same persistence context, the result is:

~~~text
true
~~~

Two lookups for the same identifier return the same managed object. This avoids having two different managed copies representing the same row in the same persistence context.

The persistence context is typically managed by Spring and bound to a transaction. When the transaction ends and the context closes, the entities are no longer managed by that context; they become detached with respect to the closed context.

## 2. The four entity states

| State | In persistence context? | Automatic dirty checking? | Can data be persisted? |
|---|---|---|---|
| Transient | No | No | Not yet, requires persist or an appropriate merge |
| Managed | Yes | Yes | Yes, on flush/commit |
| Detached | No | No | Not automatically; requires merge or another operation |
| Removed | Managed by the context in the removed state | No longer treated as a normal entity for updates | Scheduled for DELETE on flush |

You can visualize the main state transitions:

~~~text
                    persist()
     TRANSIENT ----------------------> MANAGED
         |                                |
         | merge()                        | remove()
         v                                v
   MANAGED COPY                         REMOVED
         ^                                |
         |                                | flush / commit
         | merge()                        v
     DETACHED <---------------------- (deleted in DB)
         ^
         |
   detach() / clear() / close()
         |
     MANAGED

MANAGED -- transaction-scoped context closes --> DETACHED
MANAGED -- refresh() --> MANAGED (state reloaded from DB)
~~~

The diagram highlights the common transition paths. Merge creates or updates a target managed instance; it does not turn the source detached object itself into a managed one. Removed is a state marked for deletion, and the delete operation is synchronized on flush.

## 3. Transient: a new object not yet managed by JPA

Transient (also called new) is a Java object created with the new operator that has not yet been placed into a persistence context.

Example:

~~~java
Book book = new Book("Spring Data JPA");
~~~

At this point:

- The object exists in JVM memory.
- JPA is not yet tracking the object.
- Modifying fields only modifies the object in memory.
- No INSERT is scheduled merely because the object was created.
- Without persist or merge, the object is not automatically saved to the database.

Example:

~~~java
Book book = new Book("Spring Data JPA");
book.changeTitle("Spring Data JPA in Practice");
~~~

The two lines above only manipulate a Java object. The database knows nothing about this object.

### Bringing a transient entity into the persistence context

Using EntityManager:

~~~java
entityManager.persist(book);
~~~

Or using Spring Data JPA:

~~~java
bookRepository.save(book);
~~~

When Spring Data determines that an entity is new, save usually calls EntityManager.persist. The entity transitions to managed in the current persistence context.

Note that when SQL INSERT is issued depends on the ID generation strategy and provider. With IDENTITY, Hibernate may need to insert early to obtain the key; with other strategies, INSERT can often be deferred until flush.

## 4. Managed: an entity tracked by the persistence context

Managed is the most important state when working with JPA. An entity can become managed when:

- Calling persist on a transient entity.
- Looking up an entity with EntityManager.find.
- Fetching an entity via a repository query within an active persistence context.
- Calling merge and using the returned managed instance.
- Obtaining an entity from an association initialized within the persistence context.

Example:

~~~java
Book book = entityManager.find(Book.class, 10L);
~~~

If the record is found, the returned entity is managed in the current persistence context.

### Dirty checking

JPA tracks the state of managed entities. When a field changes, the provider can detect the change and generate an UPDATE on flush.

~~~java
@Transactional
public void renameBook(Long id, String newTitle) {
    Book book = entityManager.find(Book.class, id);
    if (book == null) {
        throw new IllegalArgumentException("Book not found: " + id);
    }

    book.changeTitle(newTitle);
    // No need to call entityManager.merge(book) or repository.save(book).
}
~~~

When the transaction completes, Spring/JPA flushes the persistence context. Hibernate issues an UPDATE if it detects that data has changed.

This is dirty checking. It is why you do not need to call save after every setter on a managed entity.

### Identity map and consistent changes

Within the same persistence context, if two services/repositories operate on the same entity ID, JPA usually uses the same managed instance. When one part of the code modifies that instance, other code in the same context sees the change in memory.

This does not mean other transactions immediately see uncommitted changes. Transaction isolation and the database determine when other transactions see committed data.

## 5. Detached: an entity no longer managed

Detached is an object that was once managed but has been separated from the persistence context. Common causes:

- Calling EntityManager.detach(entity).
- Calling EntityManager.clear() to detach all managed entities.
- Closing the EntityManager or persistence context.
- Ending a transaction-scoped persistence context.

Example:

~~~java
Book book = entityManager.find(Book.class, 10L);
entityManager.detach(book);

book.changeTitle("New title");
~~~

After detach:

- The object still exists in the JVM.
- Its ID and existing fields remain intact.
- JPA no longer performs dirty checking on that object.
- Changes made after detach are not automatically written to the database.
- Uninitialized lazy associations may not be accessible if there is no longer an appropriate persistence context.

If you need to synchronize detached state, you can use merge. However, you must understand the exact semantics of merge.

## 6. merge(): copying state to a managed instance

A common misconception is thinking that merge will "reattach" the detached object itself to the persistence context. In reality, JPA copies the state of the source object into a target managed instance and then returns that target instance.

~~~java
Book detachedBook = ...;

Book managedBook = entityManager.merge(detachedBook);

managedBook.changeTitle("Updated title");
~~~

After the call:

- **detachedBook** remains detached.
- **managedBook** is the managed instance in the current persistence context.
- Subsequent changes should be made on managedBook.
- On flush, changes to managedBook can be written to the database.

If you ignore the return value:

~~~java
entityManager.merge(detachedBook);
detachedBook.changeTitle("Another title");
~~~

then the final change on detachedBook is not tracked by dirty checking. This is a common mistake.

### Merging a transient entity

Merge can also accept a transient object. JPA creates a managed copy and copies the state from the transient object into that copy. On flush, the managed copy can be inserted.

However, if the goal is to save a new entity, persist expresses the intent more clearly. With Spring Data JPA, save automatically determines whether an entity is new or existing via new-state detection and then chooses persist or merge.

### Merging a graph and cascade MERGE

If the source entity has an association and the mapping declares CascadeType.MERGE, the state of the related entity is also merged along with it. Without cascade MERGE, you should not assume the entire graph is merged recursively.

Be especially careful when merging a detached object constructed from an incomplete request DTO. Null fields or missing associations can overwrite existing data in the managed copy. A safe update workflow usually loads the managed entity within a transaction, checks permissions and business rules, and only modifies the permitted fields.

## 7. remove(): marking an entity for deletion

EntityManager.remove requires a managed entity. When called:

~~~java
Book book = entityManager.find(Book.class, id);
entityManager.remove(book);
~~~

the entity transitions to the removed state. JPA schedules a DELETE; the SQL is typically executed on flush or commit.

The removed state does not mean the row has immediately disappeared at the moment remove is called. Before flush, the operation may only be recorded in the persistence context.

Key points to remember:

- Calling remove on a managed entity is the standard usage path.
- Calling remove on a detached entity is invalid; you must load the managed entity or handle it appropriately.
- CascadeType.REMOVE can propagate removal to configured associations.
- orphanRemoval can schedule deletion of a child when the child is removed from an appropriate owning relationship.

Spring Data example:

~~~java
@Transactional
public void deleteBook(Long id) {
    Book book = entityManager.find(Book.class, id);
    if (book == null) {
        return;
    }

    entityManager.remove(book);
}
~~~

You can use repository.deleteById(id), though actual semantics depend on the implementation and entity state. When you need to understand the exact lifecycle, check the behavior of the Spring Data JPA version in use and inspect the SQL in integration tests.

## 8. detach(), clear(), and close()

All three operations affect whether entities remain managed by the persistence context.

### detach(entity)

Detaches a specific entity from the persistence context:

~~~java
entityManager.detach(book);
~~~

If an association has CascadeType.DETACH, the detach operation can propagate to related entities according to the mapping.

### clear()

Detaches all managed entities from the persistence context:

~~~java
entityManager.clear();
~~~

Clear is useful in batch processing or tests when you need to ensure subsequent reads fetch data from the database instead of using a managed instance still in the first-level cache.

Do not call clear arbitrarily in the middle of business logic if there are unflushed changes; those changes will no longer be tracked by the persistence context.

### close()

When EntityManager closes, its persistence context ends. Entities that were managed become detached with respect to that context.

In a Spring application, EntityManager is usually managed by the container/proxy; do not manually call close on an EntityManager injected into a bean.

## 9. refresh(): reloading state from the database

Refresh applies to a managed entity:

~~~java
entityManager.refresh(book);
~~~

JPA re-reads the state from the database and synchronizes the managed object with the current data according to transaction/database visibility. Unflushed changes on the entity may be overwritten.

Refresh differs from merge:

| Operation | Data direction | Purpose |
|---|---|---|
| merge(detached) | From source object into managed copy | Synchronize detached/transient object state into the persistence context |
| refresh(managed) | From database into managed object | Reload state from the database |

Do not use refresh as a way to save data. If you want to persist changes, let dirty checking/flush handle it; refresh can discard the very changes you wanted to save.

## 10. flush() is not commit

Flush synchronizes pending changes in the persistence context to the database using SQL. It does not end the transaction by itself.

~~~java
entityManager.persist(book);
entityManager.flush();
~~~

After flush, the INSERT statement may have been sent to the database, but the transaction can still roll back. Only committing the transaction confirms the changes according to database transaction semantics.

Some flush triggers:

- When the application calls EntityManager.flush or repository.flush.
- Before transaction commit.
- Before a query in an appropriate flush mode, such as AUTO, if pending changes could affect the query result.

Do not treat flush as a guarantee that data is durable to other transactions. It only synchronizes persistence context state to the database within the current transaction.

## 11. Lifecycle and the Spring Data JPA save() operation

Spring Data JPA provides save(entity). This method does not always call persist, nor does it always call merge. The repository determines whether the entity is new and chooses the appropriate operation.

Typically:

- New entity: calls persist.
- Existing/detached entity: calls merge.

New-state detection can be based on a **@Version** field or ID, or the **Persistable.isNew()** mechanism if the entity implements this interface.

Example:

~~~java
@Transactional
public Long createBook(String title) {
    Book book = new Book(title);

    Book saved = bookRepository.save(book);
    return saved.getId();
}
~~~

For a new entity, saved is usually the exact instance that was persisted. However, if save uses merge, the returned instance is a managed copy; you should continue using the returned object when needed.

For a managed entity already loaded in a transaction, there is usually no need to call save again after modifying it:

~~~java
@Transactional
public void rename(Long id, String title) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.changeTitle(title);
    // Dirty checking will synchronize on flush.
}
~~~

## 12. Rollback and in-memory object state

When a transaction rolls back, the database undoes the changes of that transaction. However, do not assume Java objects automatically revert to their pre-transaction state.

For example, if code changed the title of a managed entity and the transaction rolled back, the in-memory object may still retain the new title even though the database rolled back. The persistence context after a rollback may also no longer be suitable for continued use as a consistent state.

Safe practices:

- End the failed transaction.
- Do not continue using entities from a rolled-back persistence context for a new business operation.
- Reload the entity in a new transaction.
- If data is needed after a rollback, re-read it from the database instead of trusting the old object.

This is especially important when an entity has been passed across multiple layers or held in a variable outside a transaction.

## 13. Example verifying states with EntityManager

The following table summarizes a simple lifecycle flow:

| Step | Operation | State |
|---|---|---|
| 1 | new Book(...) | Transient |
| 2 | persist(book) | Managed |
| 3 | book.changeTitle(...) | Managed, with tracked changes |
| 4 | flush() | Managed, changes synchronized via SQL in transaction |
| 5 | detach(book) | Detached |
| 6 | book.changeTitle(...) | Detached, changes not automatically synchronized |
| 7 | merge(book) | Returns a managed copy |
| 8 | remove(managedCopy) | Removed |
| 9 | flush()/commit | DELETE executed / transaction confirmed |

An illustrative example in a test:

~~~java
@DataJpaTest
class BookLifecycleTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    @Test
    void entityMovesThroughManagedAndDetachedStates() {
        Book book = new Book("Original");

        testEntityManager.persist(book);
        testEntityManager.flush();

        Long id = book.getId();
        assertThat(testEntityManager.getEntityManager().contains(book)).isTrue();

        testEntityManager.detach(book);
        assertThat(testEntityManager.getEntityManager().contains(book)).isFalse();

        Book managedCopy = testEntityManager.getEntityManager().merge(book);
        assertThat(testEntityManager.getEntityManager().contains(managedCopy)).isTrue();

        assertThat(bookRepository.findById(id)).isPresent();
    }
}
~~~

The test requires a Book entity with an appropriate constructor and test database/schema configuration. **contains(entity)** indicates whether the entity belongs to the current persistence context; this is a direct way to check the managed state in tests.

## 14. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Object modified but database unchanged | Entity is transient or detached | Persist new entity or merge and use the managed copy |
| Called merge but source object stays detached | Misunderstanding merge as reattach | Use the managed object returned by merge |
| No INSERT seen immediately after persist | SQL is deferred until flush or commit | Understand lifecycle and flush timing; check ID generation |
| Deleting a detached entity fails | remove requires a managed entity | Load the entity in a transaction, then remove |
| Changes lost after clear | Clear detaches all entities and stops tracking unflushed changes | Flush before clear if changes need to be kept |
| Object data mismatches database after rollback | In-memory objects do not automatically revert | End the failed context and reload the entity |
| Two find calls return two different objects | Different persistence contexts or different identities | Compare within the same context using contains/identity |
| Lazy association error after context closes | Entity is detached and association was not initialized | Load required fetch plan in transaction, then map DTO |

## 15. Checklist when working with entity lifecycle

- [ ] Identify whether the entity is transient, managed, detached, or removed.
- [ ] Use persist for new entities when working directly with EntityManager.
- [ ] Use merge for detached state when you genuinely need to synchronize a graph.
- [ ] Always use the managed instance returned by merge.
- [ ] Use remove on managed entities.
- [ ] Use detach/clear intentionally and understand their impact on unflushed changes.
- [ ] Use refresh when you want to discard in-memory changes and reload data from the database.
- [ ] Distinguish flush from commit.
- [ ] Do not rely on an object after rollback as if it had automatically recovered.
- [ ] With Spring Data save(), understand new-state detection and use the returned object.

## 16. Conclusion

The four states—transient, managed, detached, and removed—describe the relationship between a Java object and the persistence context. Persist puts a new entity under management; find returns a managed entity; merge copies state into a managed instance; remove marks an entity for deletion; detach/clear ends tracking; refresh reloads state from the database.

When you understand the lifecycle, you know when JPA performs dirty checking automatically, when merge is needed, why flush is not yet commit, and why in-memory objects can differ from the database after a rollback. This is the foundation for writing transaction-safe services and repositories.