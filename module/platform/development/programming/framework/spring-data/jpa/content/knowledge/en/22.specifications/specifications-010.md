# Separating Filter Predicates from Fetch Joins and Count Query Logic in Spring Data JPA

When building a paginated list, a query often has to solve three distinct tasks: deciding which entities match, loading which associations to display, and counting total matching entities. Merging all three into a single JPQL query with a collection fetch join can cause SQL row multiplication, wrong counts, or Hibernate falling back to in-memory pagination.

A sound design cleanly separates:

- **Filter predicate:** decides which root entities are selected.
- **Fetch plan:** decides which associations are loaded with the entities.
- **Count query:** counts the root entities satisfying the same filter criteria.

This lesson explains how to separate those three responsibilities using JPQL, `@Query`, `countQuery`, `EXISTS`, Specification, and a two-phase loading strategy. Examples use `Post` and `Comment`, where one `Post` has many `Comments`.

## 1. Three Responsibilities of a Paginated Query

Suppose a screen displays published posts that have at least one approved comment, sorted by newest creation timestamp, while displaying all comments for each post.

There are three independent questions:

1. **Filtering:** Which Posts have `status = PUBLISHED` and at least one approved Comment?
2. **Data loading:** Does the screen need Posts along with their comments, or only Posts and comment counts?
3. **Counting:** How many Posts satisfy the filter conditions in total?

Do not confuse JOIN used for filtering with JOIN FETCH used for loading associations. JOIN participates in query expressions and predicates; JOIN FETCH instructs the provider to initialize associations on the selected entities.

A paginated query may be executed by Spring Data using two SQL statements:

- A content query fetching the page's data.
- A count query computing total results to build the Page.

The count query must preserve the exact filtering semantics of the content query, without fetching entities or collections.

~~~mermaid
flowchart TD
    A[Pageable request] --> B[Filter predicate]
    B --> C[Content query: select root entity]
    B --> D[Count query: count root entity]
    C --> E[Fetch plan: load needed associations]
    D --> F[totalElements]
    E --> G[Page response]
    F --> G
~~~

When these three parts are designed independently, each can be optimized without breaking business consistency.

## 2. Example Model: Post and Comment

A Post has many Comments. This is a to-many relationship, so joining from Post to Comment can yield multiple rows for a single Post.

Status enum:

~~~java
package com.example.post;

public enum PostStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Post entity:

~~~java
package com.example.post;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.*;

@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private PostStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
    private List<Comment> comments = new ArrayList<>();

    protected Post() {
    }

    public Post(String title, PostStatus status, Instant createdAt) {
        this.title = title;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public PostStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public List<Comment> getComments() {
        return comments;
    }
}
~~~

Comment entity:

~~~java
package com.example.post;

import jakarta.persistence.*;

@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    @Column(nullable = false, length = 2000)
    private String body;

    @Column(nullable = false)
    private boolean approved;

    protected Comment() {
    }

    public Comment(Post post, String body, boolean approved) {
        this.post = post;
        this.body = body;
        this.approved = approved;
    }

    public Long getId() {
        return id;
    }

    public Post getPost() {
        return post;
    }

    public String getBody() {
        return body;
    }

    public boolean isApproved() {
        return approved;
    }
}
~~~

The `comments` association is marked LAZY. Entities do not eagerly load all comments on every Post query; repositories and services choose the fetch plan per use case.

## 3. Why Not Combine Filtering and Collection Fetch Joins?

A common query pattern is:

~~~java
@Query("""
       select distinct p
       from Post p
       join fetch p.comments c
       where p.status = :status
         and c.approved = true
       """)
Page<Post> findPublishedPostsWithApprovedComments(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

This query introduces several semantic issues:

- JOIN FETCH simultaneously filters Comments and requests loading the association.
- `c.approved = true` restricts which Comment rows participate in the JOIN.
- The initialized collection may contain only the matching Comments, even when the use case expects all comments belonging to the Post.
- A Post with multiple approved Comments produces multiple SQL rows for that Post.
- Applying Pageable to a collection fetch join query can force Hibernate into in-memory pagination or cause unexpected provider behavior.

If the goal is merely selecting Posts with at least one approved Comment, use EXISTS for filtering, and handle comment loading separately.

A core principle: the criteria identifying root entities do not have to use the exact same association being fetched. You can filter root entities via a subquery, then fetch the full association in another query.

## 4. Using EXISTS to Filter by a Collection Without Multiplying Root Rows

EXISTS checks whether at least one child row satisfies a condition. It does not bring individual Comments into the outer query's result rows, so each Post stays a single root entity.

JPQL:

~~~java
@Query("""
       select p
       from Post p
       where p.status = :status
         and exists (
             select c.id
             from Comment c
             where c.post = p
               and c.approved = true
         )
       """)
List<Post> findPostsWithAtLeastOneApprovedComment(
        @Param("status") PostStatus status);
~~~

How to read it:

1. Select Post.
2. Keep only Posts matching the status parameter.
3. For each Post, check whether the subquery finds a linked Comment with `approved = true`.
4. EXISTS evaluates to true when at least one matching row exists.

A Post with 1 or 100 approved Comments still produces a single Post result in the outer query. DISTINCT is unnecessary for deduplicating collection joins because the outer query does not JOIN the collection.

Equivalent SQL visualization:

~~~sql
SELECT p.*
FROM posts p
WHERE p.status = ?
  AND EXISTS (
      SELECT 1
      FROM comments c
      WHERE c.post_id = p.id
        AND c.approved = true
  );
~~~

EXISTS fits requirements like "has at least one", "has none", or "has an element matching condition" especially well. For negated conditions, `NOT EXISTS` can be used.

## 5. Content Query and countQuery Must Share the Same Filter Conditions

When a repository returns `Page<T>`, Spring Data needs the total result count. For complex queries, declare `countQuery` explicitly so the framework does not derive an incorrect count from the content query.

~~~java
public interface PostRepository extends JpaRepository<Post, Long> {

    @Query(
        value = """
                select p
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                order by p.createdAt desc, p.id desc
                """,
        countQuery = """
                select count(p)
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                """
    )
    Page<Post> findPageWithApprovedComment(
            @Param("status") PostStatus status,
            Pageable pageable);
}
~~~

Both queries share the exact same predicates:

- `p.status = :status`
- EXISTS a linked Comment with `approved = true`

The content query selects and sorts Posts; `countQuery` counts matching Posts. The count query has no JOIN FETCH, no collection selection, and no ORDER BY.

If the content query also filters by date, tenant, access permissions, keyword, or status, `countQuery` must mirror all of those conditions. Omitting even one predicate can yield accurate page content alongside an incorrect `totalElements`.

### A Count Query Is Not a Verbatim Copy of the Content Query

A count query serves a different purpose, so keep only what is needed to identify the root entity set:

| Component | Content Query | Count Query |
|---|---|---|
| SELECT | Entity, ID, or DTO | COUNT root |
| WHERE | Complete filter conditions | Same filter conditions |
| JOIN for filtering | Yes if needed | Keep if needed for predicates |
| EXISTS | Yes if needed | Keep if needed for predicates |
| JOIN FETCH | Possible for to-one or non-paginated queries | Do not use |
| ORDER BY | Yes when ordering is required | Normally omitted |
| Pageable limit/offset | Yes | Not applied like content |

The count query does not need to load associations. Its sole goal is counting matching root entities.

## 6. Why Can count(p) Be Wrong When Joining a Collection?

Consider:

~~~java
select p
from Post p
join p.comments c
where c.approved = true
~~~

If a Post has three approved Comments, the JOIN generates three rows for that Post. If you run:

~~~java
select count(p)
from Post p
join p.comments c
where c.approved = true
~~~

the count may return the number of joined rows rather than the number of unique Posts.

Two solutions:

**Option 1: EXISTS.** If you only need to check whether a matching Comment exists, use EXISTS as shown earlier. Then the outer query does not multiply rows, and `count(p)` counts roots accurately.

**Option 2: COUNT DISTINCT.** If a JOIN is needed for filtering or combining other conditions, count distinct root IDs:

~~~java
@Query(
    value = """
            select distinct p
            from Post p
            join p.comments c
            where p.status = :status
              and c.approved = true
            """,
    countQuery = """
            select count(distinct p.id)
            from Post p
            join p.comments c
            where p.status = :status
              and c.approved = true
            """
)
Page<Post> findPageUsingCommentJoin(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

`COUNT(DISTINCT p.id)` counts each Post once. The content query uses DISTINCT so root results do not repeat. Still, this query does not fetch comments and still incurs join cost; EXISTS is usually clearer when only testing existence.

Never apply `count(distinct p.id)` blindly. Choose the count expression based on actual cardinality and query predicates.

## 7. Separating Filter Predicates from the Fetch Plan

Filter predicates determine which Posts are chosen. The fetch plan determines which associations must be loaded for downstream use.

For instance, a list displaying only titles and author names can use a projection without loading comments. A Post detail screen may need comments, loaded only when the user opens that detail view.

Strategies:

- Query roots without collection fetches: safe for pagination.
- To-one fetch joins: usually do not multiply root rows when mapping cardinality is right.
- Fetch collections separately after paginating IDs: loads exact needed associations.
- Batch fetching: keep collections LAZY and load in batches when accessed.
- DTO projections: select only fields needed by the screen, computing counts via aggregates.

Do not mark every association EAGER just to avoid lazy loading. EAGER associations can make unrelated queries heavy and hard to control.

## 8. Paginate IDs First, Fetch Collections Second

When a page needs Posts along with all their comments, use two queries:

1. Fetch `Page<Long>` of Post IDs matching filters and sort order.
2. Fetch Posts with comments for that exact ID set, without passing Pageable to the collection-fetch query.
3. Restore the original order because `IN` does not guarantee ordering.

Repository:

~~~java
package com.example.post;

import java.util.Collection;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PostRepository extends JpaRepository<Post, Long> {

    @Query(
        value = """
                select p.id
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                order by p.createdAt desc, p.id desc
                """,
        countQuery = """
                select count(p)
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                """
    )
    Page<Long> findPageIdsWithApprovedComment(
            @Param("status") PostStatus status,
            Pageable pageable);

    @Query("""
           select distinct p
           from Post p
           left join fetch p.comments
           where p.id in :ids
           """)
    List<Post> fetchPostsWithCommentsByIdIn(
            @Param("ids") Collection<Long> ids);
}
~~~

The first query selects only root Post IDs. Pageable bounds the Posts before collections are loaded. The count query counts Posts using the exact same EXISTS condition.

The second query fetches the collection for the selected IDs. Do not pass Pageable to this method; collection fetch joins are not sliced mid-comment by SQL LIMIT/OFFSET.

Service preserving order:

~~~java
package com.example.post;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PostQueryService {

    private final PostRepository repository;

    public PostQueryService(PostRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Post> findPageWithComments(
            PostStatus status,
            int pageNumber,
            int pageSize) {

        Pageable pageable = PageRequest.of(pageNumber, pageSize);

        Page<Long> idPage =
                repository.findPageIdsWithApprovedComment(status, pageable);

        if (idPage.isEmpty()) {
            return new PageImpl<>(
                    List.of(),
                    pageable,
                    idPage.getTotalElements()
            );
        }

        List<Post> fetched =
                repository.fetchPostsWithCommentsByIdIn(idPage.getContent());

        Map<Long, Post> byId = fetched.stream()
                .collect(Collectors.toMap(Post::getId, Function.identity()));

        List<Post> ordered = idPage.getContent().stream()
                .map(byId::get)
                .filter(Objects::nonNull)
                .toList();

        return new PageImpl<>(
                ordered,
                pageable,
                idPage.getTotalElements()
        );
    }
}
~~~

Because the ID query uses `ORDER BY p.createdAt desc, p.id desc`, the page's ID order is deterministic. The `IN` query does not guarantee preserving that order; the service indexes results by ID into a Map and rebuilds the list following `idPage.getContent()`.

Both queries run inside the same `readOnly` transaction to keep the persistence context open throughout loading and processing. `readOnly = true` is a read optimization hint; it does not automatically establish a strict snapshot at every isolation level.

If a Post is deleted between the two queries by a concurrent transaction, the fetched list may contain fewer items than the ID page. Filtering out nulls prevents crashes when reconstructing order, though `totalElements` still reflects the count from the first query. If business rules demand strict snapshot consistency, configure an appropriate database isolation level or locking strategy.

## 9. Why Is Deterministic Ordering Necessary for Pagination?

Offset-based pagination requires a deterministic order. If you only `ORDER BY createdAt` and multiple Posts share the exact same timestamp, the database can return tied rows in different orders across calls.

Add a unique key as a tie-breaker:

~~~java
order by p.createdAt desc, p.id desc
~~~

This prevents duplicate or skipped items across pages caused by non-deterministic ordering. Still, offset pagination can shift if new rows are inserted or deleted earlier in the list between page fetches.

When data changes continuously and stable traversal is critical, consider keyset scrolling or cursor pagination. Subsequent fetches filter using the last sort key pair, such as `createdAt` and `id`, rather than an offset.

## 10. Specification: Reusing Filters Without Cramming Fetch Joins Inside

Spring Data JPA Specification fits dynamic filter criteria. You can create Specifications for status and EXISTS, then use them to fetch a Page of root entities.

Status filter example:

~~~java
package com.example.post;

import org.springframework.data.jpa.domain.Specification;

public final class PostSpecifications {

    private PostSpecifications() {
    }

    public static Specification<Post> hasStatus(PostStatus status) {
        return (root, query, cb) ->
                status == null
                        ? cb.conjunction()
                        : cb.equal(root.get("status"), status);
    }
}
~~~

This Specification only produces a predicate; it does not call `root.fetch()`. It can be composed:

~~~java
Specification<Post> spec =
        PostSpecifications.hasStatus(PostStatus.PUBLISHED);

Page<Post> page = repository.findAll(
        spec,
        PageRequest.of(0, 20)
);
~~~

The repository must extend `JpaSpecificationExecutor`:

~~~java
public interface PostRepository
        extends JpaRepository<Post, Long>,
                JpaSpecificationExecutor<Post> {
}
~~~

When using Specification with Page, Spring Data uses the predicate to build both the content query and the count query. If the Specification contains a collection fetch join, the count query may fail or emit invalid SQL because a count query is not an entity-graph loading query.

Keep Specifications focused on filter predicates. Fetch associations in a separate query or via an appropriate fetch plan after determining the root page.

### EXISTS in Specification

You can build an EXISTS predicate via the Criteria API:

~~~java
public static Specification<Post> hasApprovedComment() {
    return (root, query, cb) -> {
        var subquery = query.subquery(Long.class);
        var comment = subquery.from(Comment.class);

        subquery.select(comment.get("id"))
                .where(
                    cb.equal(comment.get("post"), root),
                    cb.isTrue(comment.get("approved"))
                );

        return cb.exists(subquery);
    };
}
~~~

Composition:

~~~java
Specification<Post> spec = Specification
        .where(PostSpecifications.hasStatus(PostStatus.PUBLISHED))
        .and(PostSpecifications.hasApprovedComment());
~~~

This is a filter-only Specification. Never add `root.fetch("comments")` to a Specification shared with Page queries.

## 11. Do Not Use One Fetch-Join Specification for Both Content and Count

An anti-pattern is placing a fetch inside a Specification:

~~~java
// Do not share across Page queries if fetching a collection.
return (root, query, cb) -> {
    root.fetch("comments", JoinType.LEFT);
    return cb.equal(root.get("status"), status);
};
~~~

Reasons:

- The Specification can be invoked for both the content query and the count query.
- The count query selects COUNT and does not need collections.
- Fetch joins are invalid in many count queries and can make Hibernate throw an exception.
- Even if a provider allows it, collection fetching can multiply rows and force in-memory pagination.
- The same Specification couples filtering criteria with data-fetching strategy, hurting reuse.

Some teams inspect `query.getResultType()` to add fetches only when the result type is not `Long`. That trick depends on how Spring Data/providers construct count queries and becomes brittle across version upgrades. Separating filter Specifications from fetch plans is cleaner.

## 12. To-One JOINs and Collection JOINs Have Different Effects

To-one relationships like ManyToOne or OneToOne point to at most one related object per root entity. A to-one fetch join normally does not multiply root rows when mappings and constraints reflect true cardinality.

Suppose Post has an Author:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "author_id")
private Author author;
~~~

A paginated query can fetch author:

~~~java
@Query(
    value = """
            select p
            from Post p
            join fetch p.author
            where p.status = :status
            order by p.createdAt desc, p.id desc
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
            """
)
Page<Post> findPageWithAuthor(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

The count query omits the fetch join because author does not participate in filtering. If filtering by an author attribute, keep the matching predicate in the count query without fetching author.

Conversely, collections like `comments` have multiple elements and multiply rows. Therefore, do not apply the same fetching rules to to-one and to-many associations.

## 13. @EntityGraph Does Not Automatically Fix Count Queries

Spring Data JPA supports `@EntityGraph` to declare associations to fetch:

~~~java
@EntityGraph(attributePaths = "comments")
Page<Post> findByStatus(PostStatus status, Pageable pageable);
~~~

EntityGraph declares the fetch plan, while the provider decides how to load the association. If the collection is loaded via a JOIN in a paginated content query, row multiplication and in-memory pagination can still happen.

Keep in mind:

- To-one EntityGraphs are generally low-risk.
- Collection EntityGraphs require inspecting SQL and Hibernate warnings.
- Count queries do not need to load collections.
- Do not treat EntityGraph as a replacement for separating filters and fetches.
- For large collections, paginate IDs first and fetch separately, or use batch fetching.

For Page queries using EntityGraph, enable SQL logging in tests to inspect how both content and count queries execute.

## 14. Batch Fetching When You Want to Avoid a Separate Collection Fetch Query

Another option is keeping collections LAZY and configuring Hibernate to fetch them in batches when code accesses the collection.

~~~java
@OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<Comment> comments = new ArrayList<>();
~~~

Or global configuration:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Once a batch of Posts is loaded, Hibernate groups uninitialized collections into a handful of `IN` queries instead of issuing one query per Post.

Benefits:

- Root pagination queries avoid collection fetching.
- Mitigates N+1 when multiple collections are accessed.
- Avoids writing manual collection-fetch queries for every use case.

Limitations:

- `@BatchSize` and `default_batch_fetch_size` are Hibernate features, not standard JPA.
- Very large collections can still consume substantial memory.
- Ideal batch size depends on page size, bind parameter limits, and database behavior.
- Actual SQL and query counts still need measurement.

Batch fetching is a fetch strategy; it does not alter filter conditions or count query logic.

## 15. When Only Association Counts Are Needed, Use Aggregate Projections

If a screen only displays Post titles and Comment counts, there is no need to load the entire collection.

DTO:

~~~java
package com.example.post;

public record PostCommentCount(
        Long postId,
        String title,
        Long commentCount
) {
}
~~~

Repository:

~~~java
@Query(
    value = """
            select new com.example.post.PostCommentCount(
                p.id,
                p.title,
                count(c.id)
            )
            from Post p
            left join p.comments c
            where p.status = :status
            group by p.id, p.title
            order by p.createdAt desc, p.id desc
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
            """
)
Page<PostCommentCount> findPostCommentCounts(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

LEFT JOIN preserves Posts with zero Comments; `count(c.id)` yields 0 for groups with no Comments. The query produces one group per Post, so the content page returns DTOs rather than entities with fetched collections.

The count query counts Posts by status without joining comments. `COUNT DISTINCT` is unnecessary because the count query has no to-many join.

If filtering by Comment attributes, add the same predicates to both the content query and the count query. If using a to-many JOIN in the content query, consider EXISTS or distinct root ID counting so joined rows are not counted.

## 16. Page, Slice, and Count Queries

`Page<T>` provides:

- Current page content.
- Total element count.
- Total page count.
- Page index and page size metadata.

To compute totals, Spring Data usually runs a count query. The framework can skip it in certain cases when total elements can be inferred from content, but never rely on that optimization to excuse an inaccurate count query design.

`Slice<T>` provides content and whether a next page exists, usually without counting the full dataset. When the UI does not need `totalElements`/`totalPages`, Slice reduces cost.

However, switching Page to Slice does not fix a collection fetch join paired with Pageable. Content queries still must avoid paginating directly over collection fetches.

With two-phase ID queries, `Page<Long>` runs a count query for total root entities. If only `Slice<Long>` is needed, you can skip counting; the second collection-fetch query still fetches the exact IDs of the current window.

## 17. Optional Filters and Count Queries

A query with multiple optional filters must keep identical logic across content and count queries.

Example searching Posts by nullable status and keyword:

~~~java
@Query(
    value = """
            select p
            from Post p
            where (:status is null or p.status = :status)
              and (:keyword is null
                   or lower(p.title) like lower(concat('%', :keyword, '%')))
            order by p.createdAt desc, p.id desc
            """,
    countQuery = """
            select count(p)
            from Post p
            where (:status is null or p.status = :status)
              and (:keyword is null
                   or lower(p.title) like lower(concat('%', :keyword, '%')))
            """
)
Page<Post> search(
        @Param("status") PostStatus status,
        @Param("keyword") String keyword,
        Pageable pageable);
~~~

Both queries contain identical optional conditions. If the content query filters by keyword while the count query forgets keyword, `Page.totalElements` will exceed the actual matching records.

Define null and empty-string handling clearly too. With `:keyword is null or ...`, an empty string is not null and produces pattern `%%`, typically matching every non-null title. Normalize blank strings to null in the service if that matches your API contract.

If LIKE searches must match literal `%` or `_` characters, escape wildcards per Spring Data/database rules. Parameter binding prevents SQL injection but does not turn wildcards into literal characters.

## 18. Count Queries with DISTINCT and GROUP BY

When the content query has a to-many JOIN, count unique root entities:

~~~java
@Query(
    value = """
            select distinct p
            from Post p
            join p.comments c
            where c.approved = true
            """,
    countQuery = """
            select count(distinct p.id)
            from Post p
            join p.comments c
            where c.approved = true
            """
)
Page<Post> findDistinctPostsWithApprovedComments(Pageable pageable);
~~~

If the content query uses GROUP BY to return DTOs, the count query does not necessarily have to replicate every aggregation. It must count the corresponding number of result groups. When grouping by a single root entity, you can count matching roots with a simpler dedicated query. For complex multi-dimensional grouping, design a matching count query or use Slice if totals are unneeded.

Do not use `count(p)` when a JOIN multiplies rows for the same `p`. Do not use `count(distinct p.id)` when the outer query has no multiplying join and `count(p)` already expresses the right semantics; pick the simplest expression that maintains accurate cardinality.

## 19. Native Queries and countQuery

For native SQL, Spring Data usually requires an explicit `countQuery` for `Page` whenever it cannot safely derive one from the original SQL.

~~~java
@Query(
    value = """
            select p.*
            from posts p
            where p.status = :status
            order by p.created_at desc, p.id desc
            """,
    countQuery = """
            select count(*)
            from posts p
            where p.status = :status
            """,
    nativeQuery = true
)
Page<Post> findNativePageByStatus(
        @Param("status") String status,
        Pageable pageable);
~~~

Native queries use physical table and column names, not entity properties. The count query must apply the same filters and return a matching count value. If a native content query joins a collection, the count query must count distinct root IDs or use EXISTS.

Native pagination syntax and sort binding vary across databases/providers and Spring Data versions. Test on the real database engine; never assume H2 reproduces every production behavior.

## 20. Testing Content and Count Queries Together

A test must verify both content and `totalElements`. Testing only content allows count query bugs to slip through unnoticed.

Repository test example:

~~~java
package com.example.post;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

@DataJpaTest
class PostRepositoryTest {

    @Autowired
    private PostRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void contentAndCountUseTheSameFilter() {
        Post first = new Post(
                "First", PostStatus.PUBLISHED,
                Instant.parse("2026-01-03T10:00:00Z"));
        Post second = new Post(
                "Second", PostStatus.PUBLISHED,
                Instant.parse("2026-01-02T10:00:00Z"));
        Post draft = new Post(
                "Draft", PostStatus.DRAFT,
                Instant.parse("2026-01-01T10:00:00Z"));

        entityManager.persist(first);
        entityManager.persist(second);
        entityManager.persist(draft);

        entityManager.persist(new Comment(first, "Approved", true));
        entityManager.persist(new Comment(first, "Another approved", true));
        entityManager.persist(new Comment(second, "Approved", true));
        entityManager.persist(new Comment(draft, "Approved", true));

        entityManager.flush();
        entityManager.clear();

        Page<Post> page = repository.findPageWithApprovedComment(
                PostStatus.PUBLISHED,
                PageRequest.of(0, 1));

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
~~~

This test sets up two matching PUBLISHED Posts where one Post has two approved Comments. The expected `totalElements` is 2, not 3. The Draft post has an approved Comment, yet is excluded because its status does not match.

To verify fetch plans, add a test for the separate fetch query and verify the collection is loaded before the persistence context closes. You can check `PersistenceUnitUtil.isLoaded(post, "comments")` or `Hibernate.isInitialized(post.getComments())`.

To confirm the count query actually executes and SQL omits fetch joins, enable SQL logging in tests or use a datasource proxy to count statements rather than inferring from Java outputs.

## 21. Observing SQL and Hibernate Warnings

When tuning paginated queries, inspect actual SQL rather than reading only JPQL.

Enable logging in development/test environments:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

Verify:

- Does the content query execute LIMIT/OFFSET in the database?
- Is there any collection JOIN/FETCH inside a paginated query?
- Does the count query share the exact same WHERE predicates?
- Does the count query have a to-many JOIN causing row multiplication?
- Is DISTINCT used only where needed?
- Does the query have a deterministic ORDER BY?
- Does the second query in an ID-based strategy load the expected collection?
- Is there a large discrepancy between returned SQL rows and root entities?

Hibernate warns when falling back to in-memory pagination due to collection fetching. In supported versions, the following property fails fast instead of merely warning:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

This property helps catch collection-fetch pagination issues early. Verify compatibility with your project's Hibernate version. Never casually enable SQL logging containing sensitive data in production.

## 22. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| totalElements exceeds root entity count | Count query counts to-many JOIN rows | Use EXISTS or count distinct root IDs |
| Content is right but totalElements is wrong | Content and count have mismatched predicates | Synchronize WHERE clauses across both queries |
| Count query fails with fetch join | Count query cannot fetch associations like content | Remove FETCH from `countQuery` |
| Small page is very slow | Hibernate paginates in memory due to collection fetch | Paginate IDs first, then fetch collection |
| Collection holds only filtered elements | Same collection alias filters and fetches | Use EXISTS to filter roots, fetch full collection separately |
| DISTINCT does not reduce cost as expected | Child columns still yield multiple SQL rows | Do not use DISTINCT as a substitute for separating fetches |
| @EntityGraph still generates collection join | Provider executes fetch plan via JOIN | Check SQL, use batch fetching, or split into two queries |
| Specification count query fails | Specification calls `root.fetch()` | Keep Specifications predicate-only |
| Count query misses optional filter | Only content query was updated | Maintain matching predicates or reuse filter logic |
| Page sort is unstable | Sort lacks a unique tie-breaker | Add ID to ORDER BY |
| IN query returns unexpected order | IN does not guarantee order | Restore order using the ID list |
| Native count query fails on dialect | Using property names instead of column names or incompatible SQL | Write per schema/dialect and test on real database |

## 23. Practical Design Principles

- Separate filter predicates from the fetch plan and count query.
- Use EXISTS when only checking whether a matching collection element exists.
- When a to-many JOIN multiplies root rows, use DISTINCT in content where appropriate and COUNT DISTINCT root IDs in the count query.
- The count query must preserve filter conditions without fetching associations.
- Never put collection fetch joins inside queries accepting Pageable.
- Use two-phase ID pagination followed by collection fetching when pages need full associations.
- Restore ordering after `IN` queries and append a unique tie-breaker to sorts.
- Keep Specifications focused on predicates; do not embed collection fetches in Specifications used with Page.
- To-one fetch joins carry lower row-multiplication risk than collections.
- Use batch fetching or DTO projections when loading full collections is unnecessary.
- Use Slice when total counts are not needed; switching Page to Slice does not fix collection-fetch pagination.
- Inspect content queries, count queries, SQL, and execution plans on the target database.
- Test content, `totalElements`, duplicate roots, collection completeness, and sort stability.

## 24. Self-Assessment Checklist

- [ ] Distinguish filter predicate, fetch plan, and count query.
- [ ] Explain how JOIN differs from JOIN FETCH.
- [ ] Understand why collection JOINs multiply root rows.
- [ ] Use EXISTS to filter roots by collection conditions.
- [ ] Write `@Query` with a `countQuery` sharing identical predicates.
- [ ] Know when `count(p)` is accurate vs. when `count(distinct p.id)` is required.
- [ ] Avoid placing collection fetch joins in paginated content queries.
- [ ] Paginate IDs first and fetch collections in a separate query.
- [ ] Restore result ordering after an IN query.
- [ ] Append a unique tie-breaker to ORDER BY.
- [ ] Keep Specifications focused solely on filter predicates when used with Page.
- [ ] Understand the limits of `@EntityGraph` and batch fetching.
- [ ] Choose DTO projections when only aggregated data is needed.
- [ ] Distinguish Page vs. Slice regarding count query needs.
- [ ] Write tests asserting both content and `totalElements`.
- [ ] Inspect SQL to catch in-memory pagination and wrong counts.

## 25. Conclusion

A solid paginated query selects the right root entities, loads the right associations, and counts roots accurately. Collection JOIN/FETCH clauses can multiply rows; therefore, collection filtering should favor EXISTS when checking element existence. The count query keeps identical predicates while counting only root entities without fetching associations.

When a page requires full collections, paginate IDs first, fetch collections in a second query, and restore the order. For dynamic criteria, Specifications should stick to predicates; for summary screens, DTO projections are usually more efficient than loading entity graphs. Always test both content and `totalElements` and inspect generated SQL to keep pagination accurate as data scales.
