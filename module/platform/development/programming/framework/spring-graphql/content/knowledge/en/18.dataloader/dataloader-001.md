# N+1 select problem

GraphQL allows clients to select nested fields as needed. A single query can fetch a list of `Book`s and then select the `Author` of each `Book` within the same operation. This structure is convenient for the API, but if each child field runs its own database query for every parent object, the server runs into the **N+1 select** problem.

N+1 select means one query to fetch a list of N parent objects, followed by N additional queries to fetch related data for each object. With a small list, the cost may be hard to notice. When N grows to tens or hundreds, the number of database accesses increases accordingly and can noticeably slow down the request.

In Spring for GraphQL, this phenomenon commonly occurs when a root resolver returns a collection while a field resolver or a JPA lazy association loads related data individually for each element. DataLoader and **@BatchMapping** are important mechanisms for batching those loads together. Before choosing how to handle it, you need to understand where N+1 originates, how to identify it, and common misconceptions.

## 1. What is N+1 select?

Suppose a book management system has two tables:

~~~sql
CREATE TABLE author (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE book (
    id BIGINT PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    author_id BIGINT NOT NULL REFERENCES author(id)
);
~~~

A catalog page needs to display a list of books along with each author's name. There are N books in the result.

The first query fetches the list of books:

~~~sql
SELECT id, title, author_id
FROM book
ORDER BY id
LIMIT 20;
~~~

Next, the application fetches the author for each book:

~~~sql
SELECT id, name
FROM author
WHERE id = ?;
~~~

If each book has a different author and every call triggers a query, the total number of SQL statements is:

\[
Q(N) = 1 + N
\]

Where:

- **1** is the query to fetch the list of books.
- **N** is the number of queries to fetch the author for each book.

For example:

| Number of books N | Book queries | Author queries | Total queries |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 5 | 1 | 5 | 6 |
| 20 | 1 | 20 | 21 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |

The name N+1 comes from this structure. This is the number of database queries, not the number of HTTP requests from the client. A single GraphQL operation can still generate hundreds of SQL statements on the server.

### Why is this a problem?

A database can execute each individual SELECT statement quickly, but every round-trip carries overhead:

- Preparing and executing the statement.
- Acquiring a connection from the connection pool.
- Sending the request to the database and waiting for the response.
- Transforming data and mapping the result.
- Holding a transaction or connection longer.

If each query takes a few milliseconds, hundreds of sequential queries or many database round-trips can noticeably increase latency. Executing some queries in parallel at certain layers does not eliminate database overhead, connection pool pressure, and overall system load.

## 2. How does N+1 appear in GraphQL?

GraphQL executes an operation as a tree of fields. A parent field returns an object or a list of objects; each object may in turn have child fields that need to be resolved.

SDL:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
~~~

The client sends an operation:

~~~graphql
query {
  books(first: 20) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

The operation makes only one call to the GraphQL endpoint, yet the server needs to resolve:

1. The root field `Query.books` to fetch the list of `Book`s.
2. The `Book.author` field for each `Book`.
3. The `Author.id` and `Author.name` fields on the corresponding `Author` object.

If `Book.author` queries the author using a separate SELECT for each `Book`, N+1 occurs.

### Execution flow diagram

~~~mermaid
flowchart TD
    A[GraphQL query books] --> B[Query.books resolver]
    B --> C[SELECT list of N Books]
    C --> D[List of Books]
    D --> E1[Resolve author of Book 1]
    D --> E2[Resolve author of Book 2]
    D --> E3[Resolve author of Book N]
    E1 --> F1[SELECT Author 1]
    E2 --> F2[SELECT Author 2]
    E3 --> F3[SELECT Author N]
    F1 --> G[GraphQL response]
    F2 --> G
    F3 --> G
~~~

GraphQL does not automatically merge field resolvers that share the same return type or the same service call into a single database query. Each field resolver is designed to return a value for a single source object. If the resolver calls a repository individually, the query count can grow with the number of source objects.

## 3. N+1 example with Spring for GraphQL

A controller might be written as follows:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public List<Book> books(@Argument Integer first) {
        return bookService.findFirst(first);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

The two methods have different responsibilities:

- **books** fetches the list of `Book`s once.
- **author** is called for each `Book` whose `author` field is selected.

If the query returns 20 `Book`s, the `author` handler may be invoked 20 times. If each call to `authorService.findById` executes a SELECT, there will be one query for books and 20 queries for authors in total.

An important point is that the number of field resolver invocations and the number of SQL statements are not always the same. A resolver might use a cache, read preloaded data, or return results from a DataLoader. Conversely, a seemingly simple getter can trigger an ORM query. You need to measure the actual SQL to conclude whether N+1 is happening.

## 4. N+1 caused by JPA lazy loading

An explicit repository call inside `@SchemaMapping` is not required for N+1 to occur. An ORM can load relational data when an association getter is invoked.

Entity example:

~~~java
@Entity
public class BookEntity {

    @Id
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private AuthorEntity author;

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public AuthorEntity getAuthor() {
        return author;
    }
}
~~~

Root resolver:

~~~java
@QueryMapping
public List<BookEntity> books() {
    return bookRepository.findAll();
}
~~~

If the schema defines the `Book.author` field and there is no custom `DataFetcher`, the default property fetcher may invoke `getAuthor()` on each `BookEntity`. For an unloaded LAZY association, Hibernate may execute a separate SELECT for each author when the property is accessed.

SQL log example:

~~~sql
-- First query
select b.id, b.title, b.author_id
from book b;

-- Then, each association access may issue a query
select a.id, a.name
from author a
where a.id = ?;

select a.id, a.name
from author a
where a.id = ?;

select a.id, a.name
from author a
where a.id = ?;
~~~

The result is one query for `Book` plus additional queries to load `Author`. This is N+1 caused by lazy loading.

### Not every LAZY association is guaranteed to produce N+1

The actual query count depends on:

- Whether the association has already been loaded beforehand.
- Whether the persistence context has the corresponding entity in the first-level cache.
- Whether second-level cache or query cache is enabled.
- The fetch plan of the repository/query.
- The number of parents and the number of distinct child IDs.
- How the GraphQL selection set requests fields.

For instance, multiple `Book`s referencing the same `Author` might not produce N distinct queries within a single persistence context if Hibernate already holds that `Author` in its identity map. However, you should not rely on incidental caching to guarantee performance. As the number of parents increases and relations vary, N+1 can still appear.

## 5. N+1 across multiple relationship levels

N+1 can occur deeper than one level.

SDL:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
  reviews: [Review!]!
}

type Review {
  id: ID!
  content: String!
}
~~~

Client:

~~~graphql
query {
  books(first: 20) {
    title
    author {
      name
      reviews {
        content
      }
    }
  }
}
~~~

Suppose there are N `Book`s and each `Book` belongs to a different `Author`. Each `Author` has M `Review`s on average. If resolvers load each relationship individually:

- 1 query to fetch `Book`s.
- N queries to fetch `Author`s.
- N queries to fetch the list of `Review`s for each `Author`.

The total number of queries can approach:

\[
Q(N) = 1 + N + N
\]

If each `Author` has another child field that is also loaded per record, the query count continues to grow. With one-to-many relationships and nested resolvers, the number of accesses can scale with the total number of source objects at each level, not only with the number of root elements.

You should not model the cost with a single fixed formula for every schema. The query count depends on cardinality, the selection set, caching, and the fetch strategy. What you need to observe is whether each resolver level issues separate queries per parent.

## 6. N+1 depends on the client's selection set

GraphQL only resolves fields selected in the operation. If the client only fetches `id` and `title`:

~~~graphql
query {
  books(first: 20) {
    id
    title
  }
}
~~~

The `author` field is not selected, so the `DataFetcher` for `Book.author` does not need to run. In that case, the queries to load `Author` may not be issued.

If the client adds:

~~~graphql
author {
  id
  name
}
~~~

then the resolver or property fetcher for `author` is executed.

This is why N+1 sometimes appears only in certain operations or when clients expand their selection sets. An API may run fast for basic list queries but become slow when clients select more relational fields.

GraphQL gives the client control over field selection, so the server must design data fetching to be efficient whenever relationships are requested.

## 7. N+1 is different from having many field resolvers

A field resolver being called N times does not automatically mean N SQL statements are executed.

Resolver example:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorCache.get(book.getAuthorId());
}
~~~

The method may be invoked for every `Book` while reading data from a cache without querying the database each time.

Conversely, a single `DataFetcher` can also call multiple repository methods and issue many SQL statements. Therefore, you should distinguish between:

| Concept | Meaning |
|---|---|
| Resolver invocation count | Number of times a handler/DataFetcher is called |
| SQL query count | Actual number of SQL statements sent to the database |
| Database round-trip | Number of communication trips to the database |
| GraphQL request count | Number of operations/requests from the client |

N+1 is a data access pattern issue. The most important measurement is tracking the SQL query count and how it scales with list size.

## 8. Why doesn't pagination automatically solve N+1?

Limiting the number of root elements caps the severity, but it does not eliminate the N+1 structure.

For example:

- Page with 10 `Book`s: 1 + 10 = 11 queries.
- Page with 20 `Book`s: 1 + 20 = 21 queries.
- Page with 100 `Book`s: 1 + 100 = 101 queries.

Pagination reduces N from 100 to 20, yet there is still one child query for every parent.

Pagination remains essential for controlling payload size, memory, and processing time. However, it should be combined with batch loading or an appropriate fetch strategy.

For GraphQL connections with cursor pagination, the server should enforce a maximum page size. Clients should not be allowed to request an arbitrary count, as a large operation can inflate both the object count and N+1 overhead.

## 9. Performance impact of N+1

N+1 affects multiple layers of the system:

### Latency

Every query carries fixed overhead and database wait time. If queries execute sequentially, total wait time grows with N. Even if some run in parallel, the database still has to process many statements and the system endures heavier load.

### Connection pool

Resolvers may require connections during querying. When multiple concurrent requests each emit hundreds of queries, the connection pool can quickly saturate and other requests are forced to wait.

### Database CPU and I/O

Many small queries still consume CPU, buffer cache, parse/plan time, and I/O. A database can process a JOIN query or an IN query more efficiently than many individual queries, depending on the execution plan and data.

### Memory and transaction duration

An ORM can retain many entities in the persistence context. Numerous relational queries prolong transactions and increase the number of managed objects. This raises memory pressure and the risk of holding connections for too long.

### Scalability

An operation that performs fine with 5 objects can degrade sharply at 100 or 500 objects. As concurrent requests increase, query costs multiply and create a database bottleneck.

## 10. How to detect N+1 in a Spring for GraphQL application

Do not merely guess from the code. Measure the query count using a representative operation.

### Enable SQL logging during development

With Spring Boot and Hibernate, you can enable SQL logging:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

To view bind parameters in development environments:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger names may vary by Hibernate version. Sensitive parameter logging should not be enabled in production, as it may record personal data or secrets.

### Use Hibernate statistics

You can enable Hibernate statistics in test environments:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics help observe the number of prepared statements, entity loads, collection fetches, and related metrics. You should reset or read metrics per test/request to avoid mixing data across multiple operations.

### Use a datasource proxy or SQL inspector

Tools like datasource proxy, P6Spy, or JDBC-layer interceptors can count and log SQL statements. This is useful when you need to know the exact number of queries emitted by a GraphQL operation.

### Compare across different list sizes

Run the same operation with varying numbers of `Book`s:

| Scenario | List size | Expected SQL query count if N+1 exists |
|---|---:|---:|
| A | 1 | About 2 |
| B | 10 | About 11 |
| C | 50 | About 51 |
| D | 100 | About 101 |

If the query count increases roughly linearly with the number of parents, inspect the resolver or association that loads child data.

The query count does not have to equal N+1 in every environment. Caching, ORM query batching, fetch plans, and other auxiliary queries can alter the numbers. The primary symptom is a query count scaling unexpectedly with the number of parents.

## 11. Ways to handle N+1

No single technique fits every relationship. Choose based on how the data is accessed.

| Approach | Suitable when | Notes |
|---|---|---|
| DataLoader | Multiple resolvers need to load the same type of data by key | Batches keys together and distributes results |
| **@BatchMapping** | A relational field in an annotated controller needs to handle multiple source objects | Concise Spring syntax for batch field resolvers |
| SQL JOIN/fetch join | Required relationships are known ahead of time for a use case | Be careful with collections and pagination |
| EntityGraph/fetch plan | You want to declare relationships to load at the repository layer | Avoid loading all associations by default |
| DTO/projection query | Only a specific set of fields is needed for the response | Reduces entity graph and unnecessary data |
| Cache | Data repeats and an appropriate invalidation strategy exists | Caching does not replace batching in all cases |
| Pagination/limit | Restricting the amount of data a client can request | Reduces scale, does not eliminate N+1 |

### DataLoader

DataLoader enables multiple resolvers requesting data by key within the same execution to be batched together. Instead of calling a repository once per author ID, resolvers enqueue keys into the loader; upon dispatch, the batch loader queries multiple IDs at once.

Example of a batch query:

~~~sql
SELECT id, name
FROM author
WHERE id IN (?, ?, ?, ...);
~~~

As a result, the query count can drop from one query per `Book` to one query per batch of keys, depending on batch size and dispatch behavior.

### @BatchMapping

Spring for GraphQL provides **@BatchMapping** to declare a handler that receives a list of source objects and returns the corresponding results. This is a convenient approach when a child field needs to load data in groups.

### Fetch join or EntityGraph

You can load `Book` and `Author` in the same query:

~~~sql
SELECT b.id, b.title, a.id, a.name
FROM book b
JOIN author a ON a.id = b.author_id
ORDER BY b.id
LIMIT 20;
~~~

A JOIN query can work well when the required relationship is known and cardinality is controlled. However, you should not arbitrarily fetch-join multiple collections simultaneously, as this can cause row multiplication, duplicate data, high memory usage, or pagination issues.

### DTO or projection

If an operation only needs the `Book` title and `Author` name, you can query a projection returning just those columns. This avoids loading entire entities and lazy relations.

Consider projections when a use case has a stable selection set or can use a suitable read model. GraphQL selection sets can vary by client, so creating a dedicated projection for every single query is not always appropriate.

## 12. DataLoader does not eliminate every kind of N+1

DataLoader handles batching key-based loads well, but it does not automatically optimize every query:

- A batch loader itself can contain inefficient SQL.
- A large batch may exceed the database's parameter limit.
- Different fields may require different batch loaders.
- Data not sharing the same key space cannot be batched together.
- Resolvers may still issue standalone queries outside of DataLoader.
- A batch loader can return missing keys or misdistribute results if mapping is incorrect.

DataLoader typically requires a batch function that takes a list of keys and returns results mappable back to each key. You must ensure results match the correct keys, even when the database returns rows in a different order than the input or when some keys are not found.

Additionally, DataLoader caching is usually scoped to a single GraphQL execution/request. Do not assume that cache is an application-wide shared cache. Request scope prevents one user's data or permissions from leaking into another request.

## 13. When is DataLoader not needed for N+1?

Some cases have simpler alternatives:

- The root resolver already loaded all necessary relationships.
- The field is a scalar property already present in the DTO.
- A JOIN query or projection satisfies the use case well.
- The number of elements is capped very small and its cost has been measured as acceptable.
- The field is rarely selected and has an appropriate cache.

Do not add a DataLoader for every field simply because the module supports it. Each added loader requires a batch function, lifecycle management, error handling, and tests. Measure first, then pick the least complex solution that meets performance requirements.

## 14. Testing to prevent N+1 regressions

An integration test that only asserts a correct response is insufficient for catching N+1. A response can be completely accurate even while the server issues hundreds of SQL statements.

You should have tests or performance checks that track query counts:

1. Prepare test data with multiple distinct `Book`s and `Author`s.
2. Execute a GraphQL operation selecting the suspected relational field.
3. Count the SQL statements issued during the operation.
4. Repeat with multiple list sizes.
5. Verify that the query count does not grow linearly beyond expectations after optimization.

Conceptual test example:

~~~java
@SpringBootTest
class BookQueryPerformanceTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveAuthorsForBookList() {
        graphQlTester.document("""
                query {
                    books(first: 20) {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books")
            .entityList(BookView.class)
            .hasSize(20);
    }
}
~~~

The test above verifies the response and element count. To detect N+1, you need to add a SQL counter or Hibernate statistics along with a query-count assertion suited to the test setup. Do not hard-code an absolute number if the test also executes data setup queries or auxiliary framework queries; reset the counter right before the operation and measure only the intended scope.

In production, tracing or APM can correlate GraphQL operations with database spans. This data helps identify which fields generate many queries and which operations suffer from high latency.

## 15. Common misconceptions

| Misconception | Reality |
|---|---|
| A single GraphQL request produces only one database query | An operation can invoke multiple DataFetchers and issue many SQL statements |
| Having `@SchemaMapping` always causes N+1 | It only happens when the resolution approach creates unnecessary repeated loads |
| No `@SchemaMapping` means no N+1 | A property fetcher can invoke a lazy JPA getter and trigger queries |
| Pagination completely solves N+1 | Pagination only limits N |
| Calling a resolver N times means N SQL queries | A resolver may read from cache or preloaded data |
| JOIN is always better than DataLoader | JOIN can cause row multiplication and is hard to combine with pagination |
| DataLoader automatically batches all repository calls | Only loads routed through the loader are batched |
| Caching eliminates N+1 in every scenario | Cache misses, scopes, and distinct keys can still produce many queries |
| A correct response means an efficient query | Query count and latency must be measured separately |

## 16. Workflow for investigating N+1

When a GraphQL operation is slow:

1. Record the actual operation and selection set.
2. Identify root fields returning a list or multiple parent objects.
3. List child fields that may load data from repositories or lazy relations.
4. Count the number of handler invocations and actual SQL statements.
5. Run the same operation with a small N and a large N to see how the query count changes.
6. Identify which queries repeat per parent.
7. Choose DataLoader, **@BatchMapping**, fetch join, EntityGraph, or projection depending on the relationship.
8. Verify that batch results map to the correct keys/source objects.
9. Re-measure SQL count, latency, and memory after the change.
10. Add tests or monitoring to catch regressions.

N+1 select is a consequence of loading related data individually for each parent object. In GraphQL, this commonly emerges in nested fields when a root query returns a list and each field resolver or lazy JPA getter queries the database. A single operation can generate a vast number of SQL queries even though the client sends only one request. Observe the query count relative to list size, pinpoint the field causing repeated loads, and choose an appropriate solution such as DataLoader, **@BatchMapping**, a fetch plan, or a projection. The goal is to keep the response faithful to the schema while keeping database access growth under control.
