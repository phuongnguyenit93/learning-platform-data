# Many-to-Many Mapping with @ManyToMany and @JoinTable

A many-to-many relationship occurs when one record of an Entity can be associated with multiple records of another Entity, while each record on the other side can also be associated with multiple records on the first side. For example, a post has many tags, and a tag can be used across many posts.

In JPA, this relationship is typically mapped with `@ManyToMany`. The two Entity tables are connected via a **join table**; `@JoinTable` lets you declare the join table name, the foreign key column(s) pointing to the owning Entity, and the foreign key column(s) pointing to the other Entity.

The most important design decision is identifying the **owning side** of the relationship. This side controls writing relationship changes to the join table. In a bidirectional mapping, the other side uses `mappedBy` to point to the owning side's property.

## 1. What Is a Many-to-Many Relationship?

Example of a post and tag management system:

- A Post can have many Tags.
- A Tag can appear on many Posts.
- A Post can have no Tags.
- A Tag may not be attached to any Post yet.

Relationship diagram:

~~~text
POST                         TAG
-----                        -----
id (PK)                      id (PK)
title                        name
   |                            |
   |                            |
   +--------- POST_TAG ---------+
             post_id (FK)
             tag_id  (FK)
~~~

The `POST_TAG` table stores link pairs. For example:

| post_id | tag_id |
|---:|---:|
| 10 | 1 |
| 10 | 2 |
| 11 | 1 |

Post 10 has two Tags (1 and 2). Tag 1 is used in both Post 10 and Post 11.

Relationally in the database, this consists of two one-to-many relationships through the join table:

- POST 1 - N POST_TAG.
- TAG 1 - N POST_TAG.

JPA can hide the join table in the object model using `@ManyToMany`, but that table still exists in the schema.

## 2. Unidirectional Mapping with @ManyToMany and @JoinTable

If you only need to navigate from Post to Tag, you can map it unidirectionally:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "post_tags",
        joinColumns = @JoinColumn(name = "post_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private List<Tag> tags = new ArrayList<>();

    protected Post() {
    }

    public Post(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public List<Tag> getTags() {
        return tags;
    }
}
~~~

Tag Entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "tags")
public class Tag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    protected Tag() {
    }

    public Tag(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

In `@JoinTable`:

- `name = "post_tags"` is the join table name.
- `joinColumns` describes the foreign key column pointing to the owning Entity, which here is Post.
- `inverseJoinColumns` describes the foreign key column pointing to the other Entity, which here is Tag.
- `@JoinColumn(name = "post_id")` names the column storing Post's key.
- `@JoinColumn(name = "tag_id")` names the column storing Tag's key.

In this example, Post is the owning side because `@JoinTable` is declared on Post's `tags` property. Tag does not need to know the list of Posts if the application only needs one-way navigation.

Unidirectional mapping is appropriate when business operations mostly start from one side and do not need reverse access from Tag to Post. You do not need to declare a bidirectional mapping just because the database can query in both directions; you can write a dedicated query if reverse lookup is the only need.

## 3. Bidirectional Mapping and mappedBy

When the application needs to access both `Post.tags` and `Tag.posts`, you can map the relationship bidirectionally.

Owning side `Post`:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "post_tags",
        joinColumns = @JoinColumn(name = "post_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private List<Tag> tags = new ArrayList<>();

    protected Post() {
    }

    public Post(String title) {
        this.title = title;
    }

    public void addTag(Tag tag) {
        if (!tags.contains(tag)) {
            tags.add(tag);
            tag.addPostFromPost(this);
        }
    }

    public void removeTag(Tag tag) {
        if (tags.remove(tag)) {
            tag.removePostFromPost(this);
        }
    }

    public List<Tag> getTags() {
        return tags;
    }
}
~~~

Inverse side `Tag`:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "tags")
public class Tag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @ManyToMany(mappedBy = "tags", fetch = FetchType.LAZY)
    private List<Post> posts = new ArrayList<>();

    protected Tag() {
    }

    public Tag(String name) {
        this.name = name;
    }

    void addPostFromPost(Post post) {
        if (!posts.contains(post)) {
            posts.add(post);
        }
    }

    void removePostFromPost(Post post) {
        posts.remove(post);
    }

    public List<Post> getPosts() {
        return posts;
    }
}
~~~

Explaining `mappedBy`:

~~~java
@ManyToMany(mappedBy = "tags")
private List<Post> posts;
~~~

The value `"tags"` is the **Java property name** in the Post Entity where `@JoinTable` is declared. It is neither the table name `post_tags` nor the column name `tag_id`.

In a bidirectional relationship:

- Post is the owning side because it has `@JoinTable`.
- Tag is the inverse side because it has `mappedBy`.
- Modifying only the inverse side's collection may not persist changes to the join table.
- When adding or removing a link, synchronize both collections in memory.

The `addTag` and `removeTag` methods keep both sides updated. They do not save data by themselves; the Entities must still be persisted or modified inside an appropriate transaction.

## 4. The Owning Side Controls Persistence of the Relationship

This is the most important rule of JPA bidirectional relationships.

Suppose Post has:

~~~java
@ManyToMany
@JoinTable(name = "post_tags", ...)
private List<Tag> tags;
~~~

and Tag has:

~~~java
@ManyToMany(mappedBy = "tags")
private List<Post> posts;
~~~

If you only call:

~~~java
tag.getPosts().add(post);
~~~

you are only changing the inverse-side collection. JPA relies on the owning side to write the relationship; therefore, this change may not be saved to `post_tags`.

Call the helper on the owning side instead:

~~~java
post.addTag(tag);
~~~

This method updates both `Post.tags` and `Tag.posts`. When the transaction flushes, the provider synchronizes the link based on the owning side's state.

Without helper methods, you can update both collections directly, but you must be careful not to miss either side. Avoid letting controllers or multiple services manipulate the collections with inconsistent rules.

## 5. Join Table Schema

For Post and Tag tables using `Long` keys, a typical SQL schema is:

~~~sql
CREATE TABLE posts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE tags (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE post_tags (
    post_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (post_id, tag_id),
    CONSTRAINT fk_post_tags_post
        FOREIGN KEY (post_id) REFERENCES posts(id),
    CONSTRAINT fk_post_tags_tag
        FOREIGN KEY (tag_id) REFERENCES tags(id)
);
~~~

The identity syntax may need to be adjusted depending on the database. This example illustrates the relational structure: two foreign keys and a composite primary key on `(post_id, tag_id)`.

A composite primary key or unique constraint on the pair of columns prevents a Post from being linked to the same Tag twice at the database level. This is a useful safeguard even if application code has a bug.

If you need specific constraint or index names, create them via Flyway/Liquibase migrations rather than relying entirely on Hibernate's auto-generated DDL. For example, an index on `tag_id` can be useful when frequently querying all Posts for a given Tag.

## 6. Adding and Removing Links in a Transaction

Usually, Tag is shared data. Before attaching a Tag to a Post, load a managed Tag from the persistence context or create a new Tag according to business rules.

Service example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PostService {

    private final PostRepository postRepository;
    private final TagRepository tagRepository;

    public PostService(
            PostRepository postRepository,
            TagRepository tagRepository) {
        this.postRepository = postRepository;
        this.tagRepository = tagRepository;
    }

    @Transactional
    public void addExistingTag(Long postId, Long tagId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Post not found"));

        Tag tag = tagRepository.findById(tagId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Tag not found"));

        post.addTag(tag);
    }

    @Transactional
    public void removeTag(Long postId, Long tagId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Post not found"));

        Tag tag = tagRepository.findById(tagId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Tag not found"));

        post.removeTag(tag);
    }
}
~~~

When the Entities are managed within the same transaction, dirty checking can write the join table changes when the transaction commits. Calling `save()` again on already managed Entities is not strictly required, though it can be called if project conventions mandate it.

To create a new Post and Tag, persist both in the appropriate order and then add the link. By default, `@ManyToMany` declares no cascade. If PERSIST cascade is not used, explicitly save both Tag and Post before establishing the link.

## 7. Cascade in Many-to-Many Relationships

Cascade allows operations on one Entity to propagate to related Entities. However, in many-to-many relationships, an Entity is typically shared by many other Entities.

For example, the Tag `"java"` may be used by thousands of Posts. If Post declares:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private List<Tag> tags;
~~~

`CascadeType.ALL` includes REMOVE. Deleting a Post can propagate the delete to the shared Tag, resulting in losing data that other Posts still use or violating foreign key constraints.

Practical guidelines:

- Do not cascade REMOVE or ALL to shared Entities such as Tag unless there is a special lifecycle model.
- Only cascade PERSIST or MERGE when creating/updating the related Entity is genuinely the responsibility of the source Entity.
- If Tag is managed independently, save and delete Tags via a separate `TagRepository`/service.
- Removing a Post-Tag link should delete the corresponding row in `post_tags`, not delete the Tag record.

`@OneToMany` has `orphanRemoval`, whereas `@ManyToMany` has no `orphanRemoval` attribute. Removing an element from a many-to-many collection removes the link without automatically deleting the Entity on the other end.

## 8. Fetching and Query Cost

`@ManyToMany` defaults to LAZY fetching. It is good practice to specify it explicitly:

~~~java
@ManyToMany(fetch = FetchType.LAZY)
private List<Tag> tags = new ArrayList<>();
~~~

LAZY defers loading the collection until it is accessed, though it is a fetch hint/contract that the provider handles under JPA rules. Never assume every operation produces only a single SQL statement.

N+1 example:

~~~java
List<Post> posts = postRepository.findAll();

for (Post post : posts) {
    System.out.println(post.getTags().size());
}
~~~

If the collection has not been loaded, accessing `tags` for each Post can trigger an extra query per Post. With many Posts, the query count grows rapidly.

You can use a fetch join for a query that needs the related data:

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PostRepository
        extends JpaRepository<Post, Long> {

    @Query("""
        select distinct p
        from Post p
        left join fetch p.tags
        where p.id = :id
        """)
    Optional<Post> findByIdWithTags(@Param("id") Long id);
}
~~~

`distinct` eliminates duplicate Post references at the Entity level when the join produces multiple rows for a single Post. Be careful with collection fetch joins and pagination: combining pagination with a collection fetch join can produce unexpected page results or force the provider to load large amounts of data and paginate in memory. For paginated lists, consider querying IDs first and then loading relationships for that set of IDs, or using an appropriate projection.

Do not set EAGER just to hide a `LazyInitializationException`. Identify what data each use case needs, load it within the appropriate transaction, and use controlled projections, entity graphs, or fetch joins.

## 9. When the Join Table Has Its Own Attributes

`@ManyToMany` only fits when the join table holds foreign keys and no business data of its own. If the relationship has additional attributes such as:

- when the Tag was attached to the Post,
- who performed the action,
- display order,
- approval status,
- tagging source or notes,

then the join table has become a meaningful business Entity. In that case, replace `@ManyToMany` with an association Entity, such as `PostTag`, having two `@ManyToOne` relationships.

Example:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "post_tags",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"post_id", "tag_id"}
    )
)
public class PostTag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "tag_id", nullable = false)
    private Tag tag;

    @Column(nullable = false)
    private Instant addedAt;

    protected PostTag() {
    }

    public PostTag(Post post, Tag tag, Instant addedAt) {
        this.post = post;
        this.tag = tag;
        this.addedAt = addedAt;
    }
}
~~~

At this point, you can add a dedicated Repository for `PostTag` and query relationship attributes directly. The model becomes much clearer when links have their own lifecycle, validation, or data.

## 10. Bidirectional Collection Synchronization and Serialization

In bidirectional relationships, helper methods should keep both collections synchronized. However, returning Entities directly from a REST API can cause JSON infinite recursion:

~~~text
Post -> tags -> posts -> tags -> ...
~~~

Avoid serializing both sides directly. Instead:

- Use DTOs or projections for responses.
- Explicitly select the fields to return.
- Jackson annotations can be used to manage bidirectional relationships if the project chooses that approach, though DTOs usually make API contracts easier to control.
- Do not let collection getters accidentally trigger lazy loading outside a transaction.

If using Lombok, avoid `@Data` on Entities with bidirectional relationships because auto-generated `equals()`, `hashCode()`, and `toString()` may traverse collections, causing recursion, unintended data loading, or unstable comparisons.

## 11. Common Mistakes

**Updating only the collection on the mappedBy side**

Changes on the inverse side may not be written to the join table. Update the owning side and synchronize both collections using helper methods.

**Placing @JoinTable on both sides**

In a bidirectional mapping, only the owning side declares `@JoinTable`. The other side uses `mappedBy` pointing to the owning side's Java property.

**Using CascadeType.ALL on shared Entities**

There is a risk that REMOVE cascade deletes shared Tags. Delete the link instead of deleting the related Entity.

**Using @ManyToMany when the join table has its own data**

When the link has a creation date, ordering, or status, model the join table as a separate Entity with two `@ManyToOne` relationships.

**Loading large collections in list views**

This can cause N+1 queries or return excessive data. Use projections, pagination, and intentional fetching.

**Calling lazy getters after the transaction ends**

This can cause `LazyInitializationException`. Load data within the transaction or design queries that return the exact data needed.

**Not preventing duplicate associations**

Use a unique constraint or composite primary key on the foreign key pair in the join table. Also check the collection before adding a link.

## 12. Checklist for Reviewing a Many-to-Many Mapping

When implementing a new relationship, check:

1. Is the business model truly many-to-many, or does the relationship need its own association Entity?
2. Does the join table have a clear name, two foreign keys, and a unique constraint on the key pair?
3. Are the owning side and `mappedBy` correctly identified?
4. Do helper methods update both sides?
5. Are cascade settings appropriate for the lifecycle of shared Entities?
6. Is the collection fetched LAZY and do queries control relationship loading?
7. Do paginated queries avoid inappropriate collection fetch joins?
8. Does serialization avoid recursion and unintended lazy loading?
9. Do integration tests verify adding, removing, and reading back links from the database?

## 13. Conclusion

`@ManyToMany` and `@JoinTable` map many-to-many relationships through a join table. In a bidirectional mapping, the owning side controls writing the relationship; the inverse side uses `mappedBy` and should be kept in sync by helper methods. For shared Entities like Tag, be cautious with REMOVE cascade. When the join table acquires business attributes, convert it into an association Entity with two `@ManyToOne` relationships. Fetching must be designed per use case to avoid N+1 queries, over-fetching, and lazy loading errors.