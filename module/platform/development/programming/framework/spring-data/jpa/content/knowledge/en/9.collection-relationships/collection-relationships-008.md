# CascadeType and the Propagation Scope of Each Operation

In JPA, one entity can reference another entity. When performing an operation on a parent entity, we sometimes want the corresponding operation applied to related entities. For example, when saving a new author along with their books, we may want to save both the author and the books within the same business flow.

JPA provides **cascade** to propagate certain lifecycle operations from a source entity to target entities across an association. The **cascade** attribute on a relationship annotation controls which operations propagate.

The standard cascade types are:

- **PERSIST**
- **MERGE**
- **REMOVE**
- **REFRESH**
- **DETACH**
- **ALL** (includes all of the operations above)

Cascading helps manage the lifecycle of a group of entities with clear ownership relationships. However, it does not determine which entity owns the foreign key, does not replace transactions, and is not equivalent to database **ON DELETE CASCADE**. Choosing the wrong cascade can accidentally delete shared data or trigger unintended saves.

**Example prerequisites:** the code snippets below use Spring Boot 3.x, Java 17 or higher, and Jakarta Persistence. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a corresponding schema. These are files inside a Spring Boot application, not standalone programs runnable with just **javac**.

## 1. What Is Cascading?

Suppose an author has many books. When creating a new author and adding several books to their list, we may want to call **persist(author)** once so JPA saves both the author and the new books.

Without cascade:

~~~text
persist(author)
      |
      v
Author enters the persistence context
      |
      +-- New Books remain transient
              |
              +-- May fail on flush if the relationship requires referencing unsaved Books
~~~

With PERSIST cascade:

~~~text
persist(author)
      |
      v
Author enters the persistence context
      |
      +-- cascade PERSIST
              |
              +-- Book A is persisted
              +-- Book B is persisted
              +-- Book C is persisted
~~~

Cascade is configured on an association. It is directional: an operation invoked on the source entity propagates to referenced target entities. Cascade does not automatically propagate backward along another direction of the association.

For example, if cascade is declared from **Author** to **Book**, calling persist on Author can propagate to Book. That does not mean calling persist on Book will propagate back up to Author.

## 2. The Six Standard CascadeType Values

| Type | Propagated operation | Meaning |
|---|---|---|
| **PERSIST** | persist | When persisting the source entity, persist associated target entities |
| **MERGE** | merge | When merging the source entity, merge associated target entities |
| **REMOVE** | remove | When removing the source entity, remove associated target entities |
| **REFRESH** | refresh | When refreshing the source entity, refresh associated target entities |
| **DETACH** | detach | When detaching the source entity, detach associated target entities |
| **ALL** | all of the above | Equivalent to declaring all five other cascade types |

Example:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<Book> books = new ArrayList<>();
~~~

Only **PERSIST** and **MERGE** propagate across this association. Removing `Author` does not automatically delete `Book`s merely because the association has those two cascade types.

**CascadeType.ALL** includes PERSIST, MERGE, REMOVE, REFRESH, and DETACH. It does not mean “cascade everything that could ever happen”: JPA has no standard cascade for SELECT queries, flush, or arbitrary repository operations.

## 3. PERSIST: Saving New Entities Along an Association

**CascadeType.PERSIST** is useful when the target entity's lifecycle depends on the source entity and it is typically created alongside the source entity.

Example where Author has many Books:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(
        mappedBy = "author",
        cascade = CascadeType.PERSIST
    )
    private List<Book> books = new ArrayList<>();

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        books.add(book);
        book.assignAuthor(this);
    }

    public Long getId() {
        return id;
    }

    public List<Book> getBooks() {
        return books;
    }
}
~~~

Book side:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    void assignAuthor(Author author) {
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public Author getAuthor() {
        return author;
    }
}
~~~

Repository:

~~~java
public interface AuthorRepository extends JpaRepository<Author, Long> {
}
~~~

Service:

~~~java
@Service
public class AuthorService {

    private final AuthorRepository authorRepository;

    public AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional
    public void registerAuthor() {
        Author author = new Author("Nguyen Van An");
        author.addBook(new Book("Spring Data JPA"));
        author.addBook(new Book("Hibernate in Practice"));

        authorRepository.save(author);
    }
}
~~~

For a new entity, Spring Data JPA typically calls persist when **save(author)** determines `Author` is new. JPA executes PERSIST cascade across the Book list, so the new Books are also persisted in the transaction.

### Why Must Both Sides of the Relationship Be Updated?

In the example, **Author.books** declares **mappedBy = "author"**, so it is the inverse side. **Book.author** is the owning side because it holds **@JoinColumn** and controls the **author_id** foreign key value.

The **addBook** method adds the Book to the collection and sets **book.author = this**. If you only add to the collection without updating the owning side, the database may not receive the expected foreign key.

Cascade and owning side are two independent concepts:

- Cascade determines whether lifecycle operations propagate.
- Owning side determines which side controls relationship updates in the database.

## 4. MERGE: Synchronizing Detached Entity State

**CascadeType.MERGE** propagates the merge operation from the source entity to target entities.

Merging typically occurs when the application receives a detached object or data graph that must be synchronized into the persistence context. In Spring Data JPA, **save(entity)** calls either persist or merge depending on new-entity detection. Only when the actual operation is a merge does MERGE cascade propagate to associations configured for it.

Example:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<Book> books = new ArrayList<>();
~~~

When merging `Author`, JPA also merges associated `Book`s via MERGE cascade.

An important aspect of merge is that **merge does not simply re-attach the original detached object as managed**. JPA copies the state of the source object onto a managed instance (which may be a different instance) and returns that managed instance.

Therefore, when calling EntityManager directly:

~~~java
Author managedAuthor = entityManager.merge(detachedAuthor);
~~~

continue working with **managedAuthor**. Do not assume **detachedAuthor** has become managed.

Similarly, when using Spring Data:

~~~java
Author managedAuthor = authorRepository.save(detachedAuthor);
~~~

use the returned object if you need to continue operating on the managed instance. Determining whether an entity is new or existing depends on Spring Data's new-state detection, such as the ID or a **@Version** field.

Do not use MERGE as a substitute for designing clean DTOs and explicit update workflows. Merging an entire detached graph can overwrite data with nulls or stale values if the input object is incomplete.

## 5. REMOVE: Cascading Deletion and Its Risks

**CascadeType.REMOVE** means that when the source entity is removed, associated target entities also receive the remove operation.

For example, if `Book` only exists as part of `Author` and has no independent lifecycle, you might consider REMOVE cascade from `Author` to `Book`:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    }
)
private List<Book> books = new ArrayList<>();
~~~

When calling:

~~~java
authorRepository.deleteById(authorId);
~~~

if the operation executes through proper entity lifecycle removal, REMOVE cascade can propagate to the associated Books. The exact SQL and deletion order are managed by the provider; the database must still satisfy foreign key constraints.

### Why Is REMOVE Dangerous on ManyToOne?

Suppose multiple Books reference the same Author:

~~~text
Author A
  ^
  +---- Book 1
  |
  +---- Book 2
  |
  +---- Book 3
~~~

If **cascade = REMOVE** is declared on **Book.author**, deleting one Book can cascade to deleting Author. That can wipe out the author still referenced by other Books, causing foreign key errors or deleting shared data.

Normally, never cascade REMOVE from a ManyToOne side to a shared entity. Only use REMOVE when the target entity genuinely has a dependent lifecycle and is not shared.

Be especially cautious with **@ManyToMany**: both sides usually reference independent entities that can be shared across many records. REMOVE cascade on this relationship can delete shared entities. Deleting the link row in the join table is usually the desired behavior rather than deleting the entity on the other end.

## 6. REFRESH: Reloading State from the Database

**CascadeType.REFRESH** propagates the refresh operation to related entities.

Refresh instructs JPA to reload an entity's state from the database. It is useful when you want to discard state currently held in the persistence context and synchronize with current database data.

Example:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = CascadeType.REFRESH
)
private List<Book> books = new ArrayList<>();
~~~

When calling:

~~~java
entityManager.refresh(author);
~~~

related Books are also refreshed via cascade.

Be careful: refresh can overwrite unflushed changes in managed entities with the current database state. Do not call refresh carelessly on a graph holding unsaved business modifications.

REFRESH does not mean “load lazy associations” in general. It is a specific lifecycle operation that propagates when invoked on the source entity.

## 7. DETACH: Separating Entities from the Persistence Context

**CascadeType.DETACH** propagates the detach operation from the source entity to target entities.

A managed entity is tracked by the persistence context. Once detached, the entity is no longer tracked by that persistence context; subsequent changes on the object will not automatically be written to the database by dirty checking.

Example:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = CascadeType.DETACH
)
private List<Book> books = new ArrayList<>();
~~~

When calling:

~~~java
entityManager.detach(author);
~~~

related Books are also detached via cascade.

DETACH is useful in certain persistence context management or memory control scenarios, though it is rarely a business operation called directly. If used, understand that any unflushed changes on the graph will not be synchronized once the entity is detached.

Do not confuse DETACH with REMOVE:

- DETACH only stops tracking the object in the persistence context.
- REMOVE marks the entity to be deleted from the database when the transaction commits.

## 8. Is CascadeType.ALL the Best Default?

**CascadeType.ALL** is equivalent to:

~~~java
cascade = {
    CascadeType.PERSIST,
    CascadeType.MERGE,
    CascadeType.REMOVE,
    CascadeType.REFRESH,
    CascadeType.DETACH
}
~~~

It is convenient when the target entity's lifecycle depends completely on the source entity. However, ALL also includes REMOVE, REFRESH, and DETACH—not just PERSIST/MERGE.

Example:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<Book> books = new ArrayList<>();
~~~

This configuration can make sense if `Book` is an owned component of `Author` and does not exist independently. Deleting `Author` deletes its `Book`s; removing a `Book` from the collection triggers orphan removal to delete that `Book`.

Do not add ALL to every association out of habit. Before using it, answer:

- Can the target entity be shared by other entities?
- Should deleting the source entity truly delete the target entity?
- Should refreshing the source overwrite changes on the target entity?
- Should detaching the source detach the entire graph?
- Are target entities created and updated alongside the source?

If you only need PERSIST and MERGE, declare only those two operations. Explicit configuration helps readers understand data lifecycles and reduces accidental deletion risks.

## 9. CascadeType vs. orphanRemoval

**orphanRemoval = true** is a separate mechanism, not a `CascadeType` value. It applies to **@OneToOne** or **@OneToMany** relationships when a child entity cannot exist independently after being removed from its parent relationship.

Example:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    },
    orphanRemoval = true
)
private List<Book> books = new ArrayList<>();
~~~

If a `Book` is removed from the `Author.books` collection, JPA schedules that orphan for deletion on flush according to orphan removal rules.

Bidirectional synchronization method:

~~~java
public void removeBook(Book book) {
    books.remove(book);
    book.assignAuthor(null);
}
~~~

For a mandatory relationship, unlinking must be understood as deleting the child entity. Orphan removal fits when `Book` is a private component of `Author` in this model. If `Book` can be moved to another `Author` or shared by business rules, design relationship transfer carefully and normally avoid `orphanRemoval`.

Comparison:

| Mechanism | When triggered | Scope |
|---|---|---|
| **CascadeType.REMOVE** | When calling remove on the source entity | Propagates remove to associated target entities |
| **orphanRemoval = true** | When a child entity is removed from the parent relationship or the parent is deleted per JPA semantics | Deletes child entities that no longer belong to a parent |
| Database **ON DELETE CASCADE** | When the database deletes a parent row referenced by a cascade-configured foreign key | Database automatically deletes dependent rows along the FK |

These three mechanisms are related but distinct. JPA cascade is a persistence lifecycle rule; `orphanRemoval` describes child entity lifecycle; `ON DELETE CASCADE` is behavior executed by the database.

## 10. Does Cascade Work with Bulk JPQL DELETE/UPDATE?

Bulk JPQL update/delete statements operate directly on the database and bypass the normal per-entity lifecycle in the persistence context. Therefore, do not expect JPA cascade, `orphanRemoval`, or entity callbacks to run as they do when deleting entities individually via EntityManager/repository lifecycle methods.

Example:

~~~java
@Modifying
@Query("delete from Book b where b.author.id = :authorId")
int deleteBooksByAuthorId(@Param("authorId") Long authorId);
~~~

This bulk delete statement is not equivalent to loading each `Book` and calling remove. It does not execute REMOVE cascade across the entity graph in the usual way.

If the database has a foreign key with **ON DELETE CASCADE**, the database can automatically delete child rows when a parent row is deleted. However, the bulk query here deletes `Book` rows directly; JPA cascade rules still do not apply.

After a bulk update/delete, the persistence context may still hold stale entities in memory. Appropriate clearing or refreshing may be needed to avoid reading stale state. Spring Data provides **clearAutomatically** and **flushAutomatically** options on **@Modifying**, though use them deliberately because clearing detaches all entities currently managed in the persistence context.

## 11. Cascade and Transactions Are Separate Responsibilities

Cascade determines which operations propagate across an association. Transactions determine whether a group of operations commits or rolls back as a unit.

Example:

~~~java
@Transactional
public void registerAuthor() {
    Author author = new Author("Nguyen Van An");
    author.addBook(new Book("Spring Data JPA"));

    authorRepository.save(author);
}
~~~

- **@Transactional** opens a transaction for the business operation.
- **save(author)** asks Spring Data JPA to save the entity.
- If `Author` is new, Spring Data typically calls persist.
- **CascadeType.PERSIST** propagates persist to `Book`.
- When the transaction completes successfully, changes are committed.

If persist cascade runs but the transaction subsequently rolls back, changes inside that transaction are not committed. Cascade itself neither opens a transaction nor guarantees atomicity.

With default **REQUIRED** propagation, repository operations join the service's existing transaction if called under the matching transaction manager. With multiple databases and transaction managers, explicitly configure which transaction manager the service uses.

## 12. Testing Cascade

An integration test verifies persist cascade behavior:

~~~java
@DataJpaTest
class AuthorCascadeTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private AuthorRepository authorRepository;

    @Test
    void persistsBooksWhenAuthorIsPersisted() {
        Author author = new Author("Nguyen Van An");
        author.addBook(new Book("Spring Data JPA"));

        authorRepository.save(author);
        entityManager.flush();
        entityManager.clear();

        Author loaded = authorRepository.findById(author.getId())
            .orElseThrow();

        assertThat(loaded.getBooks()).hasSize(1);
    }
}
~~~

The test uses **flush()** to force synchronization to the database and **clear()** to evict entities from the persistence context before reading back. That ensures the assertion does not merely inspect the in-memory collection.

This test assumes **Author.books** has **CascadeType.PERSIST** and the test configuration provides an appropriate database/schema. If the collection is loaded LAZY, the verification must run while the test persistence context is active.

Separate tests can be written for REMOVE or `orphanRemoval` by deleting the entity or removing a child from the collection, flushing, and querying again from a fresh persistence context. Do not assert only the in-memory collection; verify persisted state after flush.

## 13. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Saving parent does not save children | Missing `CascadeType.PERSIST` or children not persisted separately | Review lifecycle and add PERSIST if parent owns children |
| Updating detached graph does not propagate to children | Missing `CascadeType.MERGE` | Add MERGE if the business flow truly requires graph merging |
| Deleting parent loses shared entities | REMOVE/ALL cascade placed on a shared relationship | Remove REMOVE and manage the target entity independently |
| Child removed from collection, but row remains | `orphanRemoval` not enabled or remove not called explicitly | Enable `orphanRemoval` only when child has a dependent lifecycle |
| JPQL delete does not run cascade | Bulk queries bypass the entity lifecycle | Use entity lifecycle operations or appropriate database constraints |
| Association points to wrong side after add/remove | Only inverse side was updated | Synchronize owning and inverse sides via helper methods |
| Editing old object after merge | Misunderstanding merge as re-attaching the source object | Use the managed instance returned by merge |
| Deleting Book deletes Author | REMOVE cascade declared from ManyToOne | Do not cascade remove to a shared entity |
| Child edits overwritten on refresh | REFRESH cascade reloads the entire graph | Only refresh when discarding unflushed changes is acceptable |

## 14. Cascade Selection Checklist

- [ ] Identify which entity owns the lifecycle of related entities.
- [ ] Check whether the target entity can be shared or exist independently.
- [ ] Use **PERSIST** when saving a source entity needs to persist new children.
- [ ] Use **MERGE** when business logic updates detached graphs.
- [ ] Use **REMOVE** only when deleting the source must truly delete the target entity.
- [ ] Use **REFRESH** and **DETACH** only with clear understanding of their effect on persistence context state.
- [ ] Use **ALL** only when every lifecycle operation should propagate.
- [ ] Distinguish cascade from owning side and `mappedBy`.
- [ ] Use `orphanRemoval` only for children with dependent lifecycles.
- [ ] Do not confuse JPA cascade with database `ON DELETE CASCADE`.
- [ ] Do not expect bulk JPQL update/delete to trigger entity lifecycle cascades.
- [ ] Write integration tests for required persist, merge, and remove flows.

## 15. Conclusion

**CascadeType** defines which JPA lifecycle operations propagate from a source entity to related entities. PERSIST and MERGE are commonly helpful for cohesive aggregates; REMOVE demands caution because it can delete shared data; REFRESH and DETACH directly affect persistence context state; ALL encompasses all of these operations.

Choose cascades based on ownership and real business lifecycles. Maintain the owning side properly, use `orphanRemoval` when children truly depend on the parent, and remember that cascade never replaces transactions or database constraints.