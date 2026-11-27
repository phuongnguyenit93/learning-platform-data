# Why Pagination with Collection Fetch Joins Fails or Consumes Excessive Memory in Spring Data JPA

Pagination is normally used to load only a subset of data, such as 20 posts per page. However, if a query simultaneously fetches a collection such as comments, orders, or lineItems, the number of SQL rows can be far larger than the number of root entities. One post with 10 comments produces 10 result rows after a JOIN. The database applies LIMIT/OFFSET to those rows, whereas the application expects to limit the number of Posts.

The mismatch between SQL row count and root entity count makes pagination with collection fetch joins unpredictable. Hibernate often has to drop database-level pagination and paginate in memory to avoid truncating collections; this can load enormous amounts of data. Some providers or configurations may throw an error instead of doing this silently. This lesson explains the mechanism, how to recognize the risk, and safe implementation patterns in Spring Data JPA.

## 1. How Does Fetch Join Differ from Regular JOIN?

A regular JPQL JOIN combines data and filters results. JOIN FETCH additionally tells the JPA provider to load the association alongside the root entity within that same query.

Example Post entity with many Comments:

~~~java
@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
    private List<Comment> comments = new ArrayList<>();
}
~~~

~~~java
@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id")
    private Post post;

    private String body;
}
~~~

Regular JOIN query:

~~~java
@Query("""
       select p
       from Post p
       join p.comments c
       where c.body like :keyword
       """)
List<Post> findPostsWithMatchingComments(
        @Param("keyword") String keyword);
~~~

This query uses comments to filter Posts. It does not require the comments collection to be fully initialized in the result.

Fetch join query:

~~~java
@Query("""
       select p
       from Post p
       left join fetch p.comments
       where p.status = :status
       """)
List<Post> findPostsWithComments(
        @Param("status") PostStatus status);
~~~

Here Hibernate loads Posts and their comments collections at the same time. Once the query completes, each Post's collection is already initialized in the persistence context.

Fetch join is especially useful for avoiding N+1 when you know you need the association. Problems emerge when combining a collection fetch join with setFirstResult/maxResults or Pageable.

## 2. Why Does a Collection JOIN Multiply Rows?

Suppose there are three Posts:

| Post | Comment Count |
|---|---:|
| Post A | 5 |
| Post B | 2 |
| Post C | 4 |

The SQL JOIN generates a row count matching the collection elements:

~~~sql
SELECT p.id, p.title, c.id, c.body
FROM posts p
LEFT JOIN comments c ON c.post_id = p.id
ORDER BY p.id;
~~~

The result has 11 rows, even though there are only 3 Posts. Post A repeats 5 times, Post B repeats 2 times, and Post C repeats 4 times.

Visualize it as:

~~~text
Post A + Comment 1
Post A + Comment 2
Post A + Comment 3
Post A + Comment 4
Post A + Comment 5
Post B + Comment 1
Post B + Comment 2
Post C + Comment 1
Post C + Comment 2
Post C + Comment 3
Post C + Comment 4
~~~

This is row multiplication: a single root entity appears across multiple SQL result rows because there are multiple elements in the joined collection.

If multiple collections are joined, the row count can grow as the product of element counts. For example, a Post with 5 comments and 3 tags can produce 15 row combinations for that single Post. This increases JDBC data transfer, entity hydration time, and memory consumption.

## 3. LIMIT/OFFSET Limits SQL Rows, Not Root Entities

When a repository receives Pageable, Hibernate/JPA usually needs to translate page size and offset into database query limits.

Suppose a query fetches Post and comments with page size 3:

~~~sql
SELECT p.*, c.*
FROM posts p
LEFT JOIN comments c ON c.post_id = p.id
ORDER BY p.created_at DESC
LIMIT 3 OFFSET 0;
~~~

LIMIT 3 at the SQL level only takes three joined rows. If the first Post has three comments, the result may contain only one Post. If the first Post has five comments, the database returns only a partial collection for that Post.

The provider cannot treat those three rows as three independent Posts. Returning one Post with a truncated partial collection would leave the persistence context with an incomplete representation of the collection.

Hence, paginating a collection fetch join has a fundamental mismatch: page size is defined in terms of root entities, while the SQL row limit is applied to the multiplied JOIN result.

## 4. Hibernate Can Paginate in Memory

When a collection fetch join is combined with result limits, Hibernate typically detects that SQL pagination could truncate collections. To keep collections intact, Hibernate may:

1. Execute the JOIN query without applying LIMIT/OFFSET at the database.
2. Read and hydrate all matching rows.
3. Assemble root entities and their collections inside the persistence context.
4. Apply offset/page size in memory.
5. Return the entities belonging to the requested page.

The result may look right in terms of entities and collections, but the cost is huge. For instance, a query asking for 20 Posts might load 200,000 joined rows if many rows match.

Hibernate 6 commonly logs warning code HHH90003004 in this situation, with a message stating that firstResult/maxResults is being applied in memory due to collection fetching. Exact log text may vary by version.

This causes:

- Increased data transferred from database to application.
- Increased CPU usage to hydrate and deduplicate entities.
- Increased heap usage and risk of OutOfMemoryError.
- Response times scaling with total matching data rather than page size.
- Pagination appearing to work on small test data while becoming noticeably slow on large production datasets.

Do not conclude a query is safe simply because the returned list matches the page size. Inspect the SQL, Hibernate logs, and actual rows read.

## 5. The JPA Specification and Undefined Behavior

The Jakarta Persistence specification states that using setFirstResult() or setMaxResults() on a query with a collection fetch join has undefined behavior.

Therefore, do not rely on a specific provider outcome when paginating a collection fetch join. Hibernate may choose in-memory pagination to preserve collections; other providers may behave differently.

Spring Data JPA merely forwards Pageable down to the JPA layer. Pageable does not resolve the row multiplication issue of a collection fetch join. Declaring Page<T>, Slice<T>, or a separate countQuery does not make the content query safe if it still fetch-joins a collection in the same paginated query.

## 6. Why Doesn't DISTINCT Solve the Problem?

A common attempt is adding DISTINCT:

~~~java
@Query("""
       select distinct p
       from Post p
       left join fetch p.comments
       where p.status = :status
       """)
Page<Post> findDistinctPostsWithComments(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

DISTINCT can prevent the same Post from repeating at the JPQL result layer. However, it does not make SQL row limits correspond to Post counts.

When rows contain different Comment columns, the database still needs to retain those rows to hydrate the collection. DISTINCT across all selected columns cannot collapse distinct comments into a single row while preserving full collection data.

Consequently:

- DISTINCT can deduplicate root references in query results.
- DISTINCT does not turn a collection join into a one-to-one relationship.
- DISTINCT does not ensure database LIMIT/OFFSET bounds the exact root entity count.
- Hibernate may still fall back to in-memory pagination.

Do not treat DISTINCT as a fix for collection fetch joins with Pageable.

## 7. A Separate countQuery Does Not Fix the Content Query Either

Spring Data JPA lets you declare countQuery:

~~~java
@Query(
    value = """
            select distinct p
            from Post p
            left join fetch p.comments
            where p.status = :status
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
            """
)
Page<Post> findPosts(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

A separate countQuery can calculate the exact total number of Posts and avoid inflated counts from JOINs. However, the content query is still a collection fetch join combined with Pageable, so the risk of in-memory pagination remains.

Separate two concerns:

- Count query: computes the total number of matching entities.
- Content query: retrieves data for the current page.

Fixing countQuery only solves counting. For efficient pagination, the content query must also avoid paginating directly over a collection fetch join.

## 8. The Safe Approach: Paginate IDs First, Fetch Collections Afterward

A common, controllable pattern is splitting into two queries:

1. The first query selects only the IDs of root entities and paginates on IDs.
2. The second query fetches collections for that exact page of IDs, without Pageable.
3. Reorder the results according to the first query's ID order because IN does not guarantee order.

Flow:

~~~mermaid
flowchart TD
    A[Receive Pageable] --> B[Query 1: select Page of Post IDs]
    B --> C[Database applies LIMIT/OFFSET on Post]
    C --> D[Query 2: fetch Post and comments by IDs]
    D --> E[Restore page ID order]
    E --> F[Return Page<Post> with total from query 1]
~~~

### Repository

The first query does not fetch-join the collection:

~~~java
public interface PostRepository extends JpaRepository<Post, Long> {

    @Query(
        value = """
                select p.id
                from Post p
                where p.status = :status
                """,
        countQuery = """
                select count(p)
                from Post p
                where p.status = :status
                """
    )
    Page<Long> findPageIdsByStatus(
            @Param("status") PostStatus status,
            Pageable pageable);

    @Query("""
           select distinct p
           from Post p
           left join fetch p.comments
           where p.id in :ids
           """)
    List<Post> findAllWithCommentsByIdIn(
            @Param("ids") Collection<Long> ids);
}
~~~

The first query returns Page<Long>, so each result is a single Post ID. Pageable applies to one row per Post with no collection join multiplying rows.

The second query loads Posts with comments for the selected IDs. This query does not take Pageable, so no SQL limit truncates collections.

### Service Preserving Page Order

~~~java
@Service
public class PostQueryService {

    private final PostRepository repository;

    public PostQueryService(PostRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Post> findPostsWithComments(
            PostStatus status,
            int pageNumber,
            int pageSize) {

        Pageable pageable = PageRequest.of(
                pageNumber,
                pageSize,
                Sort.by(Sort.Direction.DESC, "createdAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );

        Page<Long> idPage =
                repository.findPageIdsByStatus(status, pageable);

        if (idPage.isEmpty()) {
            return new PageImpl<>(
                    List.of(),
                    pageable,
                    idPage.getTotalElements()
            );
        }

        List<Post> fetched =
                repository.findAllWithCommentsByIdIn(idPage.getContent());

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

Key imports for the service:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
~~~

Explanation:

- The first query retrieves the exact page IDs and the total number of matching Posts.
- The second query fetch-joins collections for those IDs.
- IN (:ids) does not guarantee result order, so the service uses the original ID list to restore order.
- PageImpl receives the ordered content, pageable, and totalElements from the first query.
- @Transactional maintains the same persistence context across both queries and association handling.
- Page size should be reasonably bounded to avoid overly large IN lists.

In the example, Pageable sorts by createdAt and id. ID acts as a tie-breaker to keep ordering stable when multiple Posts share the same createdAt. If the application accepts sorting from clients, whitelist permitted properties and ensure a unique key is appended.

If a Post is deleted between the two queries by another transaction, the second query may return fewer IDs. The example filters out nulls while restoring order to avoid NullPointerException; if business rules require a strictly consistent snapshot, consider an appropriate isolation level or database snapshot mechanism.

## 9. Using Slice When Total Record Count Is Unneeded

If the UI only needs a "Next page" button without total page counts, you can paginate IDs using Slice:

~~~java
Slice<Long> findIdsByStatus(
        PostStatus status,
        Pageable pageable);
~~~

Spring Data can fetch one extra element to determine hasNext(). The service runs the collection-fetching query for the IDs in content and restores order just like the Page example.

Slice avoids counting total records in many cases, but you still must avoid collection fetch joins in the paginated content query. Switching from Page to Slice does not fix row multiplication.

## 10. Filtering by Collection While Still Paginating the Root Entity

Sometimes filter conditions depend on a collection, such as finding Posts with at least one Comment containing a keyword. Joining the collection in the paginated query can duplicate root IDs.

You can use EXISTS to filter without bringing the collection into the SELECT row set:

~~~java
@Query(
    value = """
            select p.id
            from Post p
            where p.status = :status
              and exists (
                  select c.id
                  from Comment c
                  where c.post = p
                    and lower(c.body) like lower(concat('%', :keyword, '%'))
              )
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
              and exists (
                  select c.id
                  from Comment c
                  where c.post = p
                    and lower(c.body) like lower(concat('%', :keyword, '%'))
              )
            """
)
Page<Long> findPageIdsWithMatchingComment(
        @Param("status") PostStatus status,
        @Param("keyword") String keyword,
        Pageable pageable);
~~~

EXISTS only checks for at least one matching comment; it does not multiply a Post into multiple rows in the outer result. Then use the second query to fetch collections if needed.

If filtering with JOIN is necessary, use select distinct p.id and count(distinct p.id) where appropriate, and inspect the query plan. EXISTS usually expresses the "at least one element" semantics more cleanly.

## 11. Batch Fetching: Reducing N+1 Without Fetch-Joining the Entire Collection

Another option is leaving collections LAZY and configuring batch fetching. When accessing collections of a batch of Posts, Hibernate loads multiple collections in a few IN queries instead of one query per Post.

Using the Hibernate annotation:

~~~java
@OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<Comment> comments = new ArrayList<>();
~~~

Or global default configuration:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~

Batch size is the number of associations/entities Hibernate attempts to group into one batch; an appropriate value should be measured based on page size, collection sizes, bind parameter limits, and database.

Advantages:

- The root pagination query does not fetch collections.
- Reduces query count compared to N+1.
- Does not multiply root rows in the page query.
- Only loads collections when the application actually accesses them.

Disadvantages:

- Additional queries still run when collections are accessed.
- If many large collections are accessed, total data volume can still be high.
- Actual batch counts and SQL must be measured.

Batch fetching is a Hibernate feature; the @BatchSize annotation and configuration property are not part of standard JPA.

## 12. SUBSELECT Fetching and Its Limitations

Hibernate has a SUBSELECT strategy for collections:

~~~java
@OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<Comment> comments = new ArrayList<>();
~~~

When a collection is initialized for a group of loaded owners, Hibernate can issue a secondary query based on the owner set to load their collections.

This can reduce N+1 when a page contains many Posts. However:

- It is a Hibernate-specific feature.
- The secondary query may load more collections than expected depending on how owners were loaded in the persistence context.
- Very large collections still consume significant memory.
- Inspect actual SQL and avoid assuming it is always optimal.

Do not use SUBSELECT as an automatic substitute for two-phase pagination design. Choose the strategy based on data sizes and access patterns.

## 13. EntityGraph Does Not Automatically Eliminate the Risk

Spring Data JPA supports @EntityGraph to specify associations to load:

~~~java
@EntityGraph(attributePaths = "comments")
Page<Post> findByStatus(PostStatus status, Pageable pageable);
~~~

EntityGraph describes a fetch plan, while the provider decides how to execute it. If Hibernate implements the collection fetch via a JOIN within the same paginated query, the row multiplication problem still occurs.

Therefore:

- EntityGraph for to-one relationships generally fits root pagination better because it does not multiply roots by a collection.
- EntityGraph with collections requires checking SQL and pagination warnings.
- Do not assume EntityGraph is a safe fix for collection fetch joins.
- For large collections, prefer paginating IDs first and fetching separately, or using batch fetching.

## 14. To-One Fetch Joins Are Usually Safer

To-one relationships such as ManyToOne or OneToOne have at most one target per root entity. A to-one fetch join generally does not multiply root rows like a collection.

Example:

~~~java
@Query("""
       select p
       from Post p
       join fetch p.author
       where p.status = :status
       """)
Page<Post> findPageWithAuthor(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

If author is a true to-one relationship and the mapping/database enforces cardinality, each Post still yields at most one JOIN row. Thus root pagination can usually be executed in the database.

Even so, review the join type, data, and actual mapping. If cardinality is modeled inaccurately or the query also joins another collection, the risk can still appear.

## 15. When Only Aggregated Data Is Needed, Use DTO Projections

Not every screen needs to load the full collection. If the UI only displays Posts with comment counts, you can query a DTO and COUNT:

~~~java
public record PostCommentCount(
        Long postId,
        String title,
        Long commentCount
) {
}
~~~

~~~java
@Query(
    value = """
            select new com.example.post.PostCommentCount(
                p.id,
                p.title,
                count(c)
            )
            from Post p
            left join p.comments c
            where p.status = :status
            group by p.id, p.title
            order by p.id desc
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

This query does not fetch entity collections; the database aggregates comment counts per Post. Because SELECT returns one grouped row per Post, Pageable can limit groups per page. Ensure GROUP BY includes the non-aggregated expressions in SELECT and countQuery counts the exact number of root Posts.

DTO projections fit lists, dashboards, or APIs needing summary metrics. If the user later opens a Post's details, load the collection in a separate endpoint.

## 16. Multiple Collection Fetch Joins Can Be Even More Expensive

Fetching multiple collections in one query can create a Cartesian product of rows. Example:

~~~java
select distinct p
from Post p
left join fetch p.comments
left join fetch p.tags
~~~

If a Post has 10 comments and 5 tags, the query can generate 50 row combinations for a single Post. This increases duplicate data and hydration overhead.

With multiple bag collections (typically Lists without @OrderColumn), Hibernate may also throw MultipleBagFetchException because it cannot fetch multiple bags simultaneously that way.

How to handle:

- Fetch only the collections needed for the use case.
- Fetch one collection per query and rely on the persistence context to merge entities.
- Use batch fetching for remaining collections.
- Use DTO projections if only aggregates are needed.
- Avoid changing List to Set merely to bypass the exception if doing so breaks domain semantics.

## 17. Configuring Hibernate to Catch Errors Early

Hibernate can warn when a collection fetch join combined with pagination forces in-memory pagination. In supported versions, you can fail instead of only warning:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

When enabled, Hibernate throws an exception if it detects pagination over a collection fetch. This surfaces the error during development/testing instead of silently causing heavy load in production.

Verify the property against your Hibernate version. If the application upgrades Spring Boot/Hibernate, rerun integration tests to confirm the warning or failure behavior still works as expected.

You can enable SQL logging for inspection:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

In production environments, avoid indiscriminately enabling SQL logging that contains sensitive data. Use controlled logging, metrics, or APM to observe query counts and execution times.

## 18. Testing Two-Phase Pagination

An integration test should create multiple Posts with varying comment counts and verify:

1. The ID query returns the exact number of Posts for the page.
2. Each ID appears once.
3. The second fetch query loads all comments for the selected Posts.
4. Returned order preserves the ID page's order.
5. totalElements and totalPages come from the root count query.

Conceptual repository/service test example:

~~~java
@DataJpaTest
class PostPaginationTest {

    @Autowired
    private PostRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void pagesPostIdsBeforeFetchingComments() {
        Post first = persistPostWithComments("First", 5);
        Post second = persistPostWithComments("Second", 2);
        Post third = persistPostWithComments("Third", 4);

        entityManager.flush();
        entityManager.clear();

        Pageable pageable = PageRequest.of(
                0,
                2,
                Sort.by(Sort.Direction.DESC, "createdAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );

        Page<Long> idPage =
                repository.findPageIdsByStatus(PostStatus.PUBLISHED, pageable);

        assertThat(idPage.getContent()).hasSize(2);
        assertThat(idPage.getTotalElements()).isEqualTo(3);

        List<Post> posts =
                repository.findAllWithCommentsByIdIn(idPage.getContent());

        assertThat(posts).hasSize(2);
        assertThat(posts)
                .allSatisfy(post ->
                        assertThat(post.getComments()).isNotNull());
    }

    private Post persistPostWithComments(String title, int count) {
        Post post = new Post(title, PostStatus.PUBLISHED, Instant.now());
        entityManager.persist(post);

        for (int i = 0; i < count; i++) {
            entityManager.persist(new Comment(post, "Comment " + i));
        }

        return post;
    }
}
~~~

This is an illustrative test skeleton; Post/Comment constructors, repository mappings, and imports must match the actual entities. To verify that the collection was initialized, use PersistenceUnitUtil.isLoaded(post, "comments") or Hibernate.isInitialized(post.getComments()) before closing the persistence context.

To confirm the first query actually uses LIMIT/OFFSET in the database and the second query has no limit, enable SQL logging in the test or inspect statements with a datasource proxy. Checking List size alone does not prove the SQL is optimized.

## 19. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Page has few Posts despite large page size | SQL LIMIT applied to JOIN rows, not root entities | Paginate IDs first, then fetch collections |
| Hibernate logs in-memory pagination warning | Collection fetch join paired with Pageable | Remove collection fetch from paginated query |
| Query is slow despite small page size | Hibernate must load all matching JOIN rows | Use two-phase loading, batch fetching, or DTOs |
| Heap grows sharply | Large collections and many roots hydrated before pagination | Limit queries, batch, and monitor heap |
| DISTINCT does not eliminate warning | Child columns still differ and row multiplication remains | Do not rely on DISTINCT to fix pagination |
| countQuery is accurate but query stays slow | Only count query was fixed; content query still fetch-joins collections | Redesign the content query |
| EntityGraph still triggers warning | Provider performs collection fetch via JOIN | Check SQL; use batching or two queries |
| Order lost after IN query | SQL IN does not guarantee ID list order | Restore order from the ID page |
| Multiple collections cause huge row explosion | Cartesian product across collections | Fetch one collection at a time or use batching/DTOs |
| MultipleBagFetchException | Simultaneously fetching multiple bag collections | Split queries or change fetch strategy |
| N+1 after removing fetch join | LAZY collection accessed per entity | Use batch fetching or use-case-specific fetching |
| Page shifts between two queries | Data modified/deleted concurrently | Choose appropriate isolation and consistency policy |

## 20. Practical Design Principles

- Do not combine Pageable directly with a collection fetch join when paginating root entities.
- Remember that SQL limits JOIN rows, not the concept of a root entity page.
- Do not treat DISTINCT or a separate countQuery as a complete fix.
- Use a first query to paginate IDs/root entities, and a second query to fetch collections by ID.
- Restore order according to the ID page because IN does not guarantee order.
- Keep both queries inside a transaction when a unified persistence context is needed.
- Add a unique tie-breaker to sort for stable pagination.
- Use EXISTS when filtering roots by the existence of collection elements.
- Use batch fetching to avoid N+1 without joining the entire collection.
- Use DTO projections when only aggregated numbers are required.
- To-one fetch joins are generally safer than collection fetch joins, though mappings must still be verified.
- Enable fail_on_pagination_over_collection_fetch in dev/test if supported by Hibernate.
- Measure SQL, row counts, query latency, and heap on production-like data.

## 21. Self-Assessment Checklist

- [ ] Distinguish JOIN and JOIN FETCH.
- [ ] Explain row multiplication when fetching collections.
- [ ] Understand why SQL LIMIT/OFFSET does not correspond to root entity counts.
- [ ] Explain why Hibernate may paginate in memory.
- [ ] Recognize warning HHH90003004 and property fail_on_pagination_over_collection_fetch.
- [ ] Understand why JPA treats pagination with collection fetch joins as undefined.
- [ ] Know that DISTINCT does not eliminate row limit issues.
- [ ] Know that a separate countQuery only fixes counting, not the content query.
- [ ] Implement two-phase pagination: paginate IDs, then fetch collections.
- [ ] Restore result order after an IN query.
- [ ] Use EXISTS to filter roots by a collection without multiplying rows.
- [ ] Distinguish batch fetching, SUBSELECT, and EntityGraph.
- [ ] Know when DTO projections fit better than entity collections.
- [ ] Recognize Cartesian row multiplication when fetching multiple collections.
- [ ] Test entity counts, full collections, ordering, and actual SQL.

## 22. Conclusion

A collection fetch join multiplies a single root entity into multiple SQL rows. When the database applies LIMIT/OFFSET to those rows, page size no longer matches root entity count and collections risk being truncated. Hibernate typically avoids incorrect results by loading all matching rows and paginating in memory, consuming extra time and heap.

The standard safe approach is to paginate root entity IDs first, then fetch collections for that exact ID set and restore page ordering. For other use cases, batch fetching, EXISTS, or DTO projections may be a better fit. Inspect SQL and enable early warnings/failures to catch collection fetch pagination before large datasets expose the issue.