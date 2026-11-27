# Direct field access

In GraphQL, after a parent field returns an object, GraphQL continues resolving the child fields selected by the client. If a child field's value already exists on the source object, the server usually does not need to write an extra resolver. GraphQL Java provides the default **PropertyDataFetcher** mechanism to read properties from the source object; Spring for GraphQL relies on this mechanism when there is no explicit DataFetcher for the field.

This is the common approach for simple fields such as **Book.title**, **Book.id**, or **Author.name**. A **@QueryMapping** handler can return a Java record, DTO, JavaBean, or Map; child fields are read directly by their matching property names. When a field needs to query additional data, compute a value, or apply a dedicated policy, you can switch to **@SchemaMapping** or **@BatchMapping**.

This lesson explains how direct field access works, which Java types can act as source objects, naming rules, how nested objects and lists are handled, limitations of property fetchers, and considerations around nullability, security, JPA lazy loading, and testing.

## 1. What is direct field access?

Suppose the schema is:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

The root field **Query.book** needs a DataFetcher to look up the book. You can use **@QueryMapping**:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Suppose the method returns:

~~~java
public record Book(
        String id,
        String title,
        Integer publishedYear) {
}
~~~

Client query:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    publishedYear
  }
}
~~~

After **Query.book** returns a Book instance, GraphQL needs to retrieve the three child fields. If the application does not register separate DataFetchers for **Book.id**, **Book.title**, and **Book.publishedYear**, GraphQL Java uses the default property data fetcher to read the values from the Book object.

There is no need to write three **@SchemaMapping** methods just to return properties that already exist. That is what direct field access means in this context.

### Processing flow

~~~mermaid
flowchart TD
    A[Client query Query.book] --> B[@QueryMapping book]
    B --> C[Book source object]
    C --> D[Resolve Book.id]
    C --> E[Resolve Book.title]
    C --> F[Resolve Book.publishedYear]
    D --> G[PropertyDataFetcher]
    E --> G
    F --> G
    G --> H[Response]
~~~

The root field **Query.book** still requires an appropriate resolver or DataFetcher to produce the source object. Direct field access shines on child fields whose values reside directly on the source object.

## 2. How does PropertyDataFetcher work?

GraphQL Java uses **PropertyDataFetcher** to look up a value by GraphQL field name on the source object. For a field named **title**, the property fetcher attempts to read the corresponding property from the object.

Common source types:

- JavaBeans with getters like **getTitle()**.
- Boolean properties following JavaBean conventions like **isAvailable()**.
- Java records with accessors matching component names like **title()**.
- Objects with property accessor methods matching the name.
- Maps with keys matching the GraphQL field name.
- Other data types with properties recognized by GraphQL Java's property access mechanism.

Property fetchers connect schema fields and source object properties without requiring manual resolvers for every field.

JavaBean example:

~~~java
public class Book {

    private String id;
    private String title;

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

With SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
}
~~~

The **id** property is read via **getId()**, and **title** is read via **getTitle()**.

Prefer explicit getters or accessors. Do not rely on GraphQL Java accessing private fields via reflection, as that makes code harder to understand and can depend on class structure, module access rules, or library versions.

## 3. Direct access with Java records

Java records are well suited as GraphQL output DTOs because each component has a public accessor with the exact same name.

Example:

~~~java
public record Author(
        String id,
        String name,
        String biography) {
}

public record Book(
        String id,
        String title,
        Integer pageCount,
        Author author) {
}
~~~

SDL:

~~~graphql
type Author {
  id: ID!
  name: String!
  biography: String
}

type Book {
  id: ID!
  title: String!
  pageCount: Int
  author: Author
}
~~~

Root resolver:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

When the client requests:

~~~graphql
query {
  book(id: "book-01") {
    title
    author {
      name
      biography
    }
  }
}
~~~

GraphQL Java can read **title()** and **author()** from the Book record. Then, on the returned Author object, it reads **name()** and **biography()**.

There is no need to write:

~~~java
@SchemaMapping(typeName = "Book", field = "title")
public String title(Book book) {
    return book.title();
}
~~~

That method simply returns an already available property, adding no extra value.

### Nested records

Records can be nested across multiple levels:

~~~java
public record Address(
        String street,
        String city,
        String postalCode) {
}

public record Author(
        String id,
        String name,
        Address address) {
}

public record Book(
        String id,
        String title,
        Author author) {
}
~~~

GraphQL resolves Book, Author, and Address sequentially according to the selection set. Each object becomes the source object for its child fields.

Direct access is not limited to one level. It applies across the entire object tree as long as every property exists on its source and the return type is compatible with the schema.

## 4. Direct access with JavaBeans

Applications can use DTOs or JavaBean classes instead of records:

~~~java
public class BookView {

    private String id;
    private String title;
    private AuthorView author;

    public BookView(String id, String title, AuthorView author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public AuthorView getAuthor() {
        return author;
    }
}
~~~

With schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Getters expose the corresponding properties. Because the GraphQL field name is **author**, the getter **getAuthor()** matches it.

### Boolean properties

JavaBeans typically expose primitive booleans with an **isAvailable()** accessor:

~~~java
public class BookView {

    private boolean available;

    public boolean isAvailable() {
        return available;
    }
}
~~~

Schema:

~~~graphql
type Book {
  available: Boolean!
}
~~~

For the Boolean wrapper type, the common convention is **getAvailable()**:

~~~java
private Boolean available;

public Boolean getAvailable() {
    return available;
}
~~~

Follow JavaBean conventions consistently so properties are recognized unambiguously. If a class has non-conventional accessors or names that do not match the schema, use an explicit DTO or explicit resolver.

## 5. Direct access from a Map

PropertyDataFetcher can also read data from a Map. This is useful when the source is produced from projections, aggregated data, or flexible structures.

Example:

~~~java
@QueryMapping
public Map<String, Object> book(@Argument String id) {
    return Map.of(
            "id", id,
            "title", "Spring GraphQL",
            "pageCount", 320);
}
~~~

SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  pageCount: Int
}
~~~

With a Map, keys must match GraphQL field names:

- **id** corresponds to field **Book.id**.
- **title** corresponds to field **Book.title**.
- **pageCount** corresponds to field **Book.pageCount**.

Nested Maps work the exact same way:

~~~java
@QueryMapping
public Map<String, Object> book(@Argument String id) {
    Map<String, Object> author = Map.of(
            "id", "author-01",
            "name", "An Nguyen");

    return Map.of(
            "id", id,
            "title", "Spring GraphQL",
            "author", author);
}
~~~

GraphQL reads the **author** key to obtain the child Map, and then reads **id** and **name** from that Map.

Maps are flexible, but they lack compile-time type checking. A typo in a key name can cause the property fetcher to return null and trigger an error if the GraphQL field is non-null. For stable structures, records/DTOs are generally safer.

## 6. Java property names and GraphQL field names

Direct access works most smoothly when Java property names match GraphQL field names.

| GraphQL field | Java property/accessor |
|---|---|
| **id** | **getId()** or record accessor **id()** |
| **title** | **getTitle()** or **title()** |
| **publishedYear** | **getPublishedYear()** or **publishedYear()** |
| **available** | **isAvailable()** or **getAvailable()** |
| **author** | **getAuthor()** or **author()** |

SDL example:

~~~graphql
type Book {
  displayTitle: String!
}
~~~

If the Java class only has **getTitle()**, the default property name **title** does not match **displayTitle**. There are two options:

1. Update the DTO to expose a **displayTitle** property.
2. Write a **@SchemaMapping** to map the GraphQL field **displayTitle** to the Java value **title**.

Example explicit resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "displayTitle")
public String displayTitle(Book book) {
    return book.getTitle();
}
~~~

Keep names consistent unless there is a domain or API reason for a difference. When names intentionally differ, an explicit resolver makes the mapping easier to read.

## 7. Direct access with nested objects and collections

A property can return another object or a collection. GraphQL continues resolving the selection set on each returned value.

Java:

~~~java
public record Review(
        String id,
        String content,
        Integer rating) {
}

public record Book(
        String id,
        String title,
        List<Review> reviews) {
}
~~~

SDL:

~~~graphql
type Review {
  id: ID!
  content: String!
  rating: Int!
}

type Book {
  id: ID!
  title: String!
  reviews: [Review!]!
}
~~~

Query:

~~~graphql
query {
  book(id: "book-01") {
    title
    reviews {
      content
      rating
    }
  }
}
~~~

The property fetcher reads the **reviews** list from Book. GraphQL then resolves **content** and **rating** for each Review.

Direct access is suitable when the list is already present on the returned object. If fetching reviews requires a database query by book ID, a property getter might trigger lazy data loading or the field needs a dedicated resolver.

### Lists containing Maps or DTOs

List elements can be records, JavaBeans, or Maps as long as each element provides the required properties. GraphQL does not require all source objects to share the exact same class if the schema and runtime type resolution support those returned types.

For interfaces or unions, the server must also resolve the concrete object type. Direct property access does not replace runtime type resolution for abstract types.

## 8. Direct access does not mean database querying

PropertyDataFetcher reads a value from an existing source object. It does not inherently know how to call a repository or generate SQL to load data.

Example:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookRepository.findById(id).orElse(null);
}
~~~

If Book already holds **title**, **pageCount**, and **status**, those fields can be read directly. If **author** is a JPA lazy relation, calling **getAuthor()** can cause the ORM to load additional data.

That can trigger an N+1 problem:

1. Query fetches a list of 100 Books.
2. Client selects **author** for each Book.
3. The property fetcher calls the author getter for each Book.
4. Each getter triggers a separate query if the association has not been loaded.

Direct access reduces resolver boilerplate, but does not guarantee an optimal number of database queries. Review the data model and how the ORM loads relationships.

### When batch loading is needed

If a field needs to load data across multiple source objects, you can use **@BatchMapping**:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::getAuthorId)
            .distinct()
            .toList();

    Map<String, Author> authors = authorService.findAllByIds(authorIds);

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        result.put(book, authors.get(book.getAuthorId()));
    }
    return result;
}
~~~

Here **@BatchMapping** replaces reading the simple author property with a single grouped load. Use batch mapping when there is data-loading cost worth batching; if author is already an eagerly loaded property with no significant cost, direct access can suffice.

## 9. When do you need @SchemaMapping instead of direct access?

Direct access fits fields that directly reflect data already present on the source object. Use **@SchemaMapping** when a field needs custom behavior.

| Need | Suitable choice |
|---|---|
| Return **book.title** already in record | Direct property access |
| Return **author.name** already on Author object | Direct property access |
| Rename GraphQL field relative to Java property | **@SchemaMapping** or a DTO with matching name |
| Compute **fullName** from firstName and lastName | **@SchemaMapping** |
| Load author from authorId | **@SchemaMapping** or **@BatchMapping** |
| Check permissions before returning field | Resolver with appropriate authorization or field security |
| Call an external service to compute value | **@SchemaMapping** |
| Batch-load data for multiple parents | **@BatchMapping** or DataLoader |

Computed field example:

~~~graphql
type Author {
  firstName: String!
  lastName: String!
  fullName: String!
}
~~~

~~~java
@SchemaMapping(typeName = "Author", field = "fullName")
public String fullName(Author author) {
    return author.firstName() + " " + author.lastName();
}
~~~

**fullName** is not a property already available on the source object, so a resolver supplies the computed value.

### Explicit resolvers override the default property fetcher

When a field has an explicitly registered DataFetcher, GraphQL uses that DataFetcher for the field. This lets the application control behavior instead of relying on default property reading.

Do not write a resolver just to return the same property without reason. Every added resolver is another point to maintain and test.

## 10. Nullability and non-existent properties

The schema determines whether a field is allowed to return null.

~~~graphql
type Book {
  title: String!
  subtitle: String
}
~~~

If the source object has **title = null** while the SDL declares **String!**, GraphQL cannot validly return null for that field. Execution produces an error and null can propagate up to parent fields according to non-null propagation rules.

If **subtitle** is nullable, a null property value is valid:

~~~json
{
  "data": {
    "book": {
      "title": "Spring GraphQL",
      "subtitle": null
    }
  }
}
~~~

If the property is not found on the source object or the Map lacks the corresponding key, the property fetcher can return null. For non-null fields, that becomes an execution error; for nullable fields, the response contains null.

Therefore:

- Ensure every non-null field has a backing property that always provides a value.
- Declare fields nullable if real-world data can be missing.
- Check getter names, record components, and Map keys when encountering unexpected nulls.
- Do not use artificial defaults just to hide missing data if the domain does not allow it.

## 11. Security when using direct property access

A Java object may contain more properties than the API should expose. If you return entities or domain objects directly, be aware that properties can be read by GraphQL if they are declared in the schema and accessible to the property fetcher.

Entity example:

~~~java
public class Customer {

    private String id;
    private String displayName;
    private String passwordHash;
    private String internalNote;

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getInternalNote() {
        return internalNote;
    }
}
~~~

The public schema should only define the fields that are needed:

~~~graphql
type Customer {
  id: ID!
  displayName: String!
}
~~~

GraphQL does not automatically add **passwordHash** or **internalNote** to the schema just because getters exist. However, if the schema inadvertently exposes sensitive fields, direct property access can return those values without a dedicated resolver performing permission checks.

Principles:

- Use output DTOs/records containing only data permitted to be public.
- Avoid returning persistence entities with sensitive getters unnecessarily.
- Check access permissions for sensitive fields before including them in responses.
- Do not treat a client not selecting a field as a data protection mechanism.
- Enforce authorization on the server; clients can freely modify selection sets.

For fields requiring dedicated policies, use a resolver with permission checks or an appropriate field security mechanism. A plain getter is not the right place to enforce complex authorization.

## 12. Limitations of returning JPA entities directly

Direct access can feel convenient when returning entities, but persistence entities often carry characteristics poorly suited to an API contract:

- Lazy associations can trigger queries when getters are invoked.
- Bidirectional relationships can create circular references.
- Entities contain internal fields that should not be exposed.
- Database schema changes can unexpectedly alter API responses.
- Getters can have side effects or depend on an active persistence session.

Relationship example:

~~~java
class BookEntity {
    AuthorEntity author;
}

class AuthorEntity {
    List<BookEntity> books;
}
~~~

If a GraphQL query traverses from Book to Author and back to Author.books, watch out for relationship cycles and data loading costs. A GraphQL selection set is bounded per operation, but lazy loading and relational queries can still incur heavy costs.

A cleaner organization is mapping entities into output DTOs:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

The DTO contains only the data needed for the API. The author field can be loaded via a resolver or batch mapping using `authorId`. This keeps queries controlled and decoupled from the entire entity graph.

## 13. Property fetchers and field mappings can coexist

An object type can use direct access for most fields and dedicated resolvers for a few specific fields.

SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
  reviewCount: Int!
}
~~~

Java:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}
~~~

Resolver:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Book", field = "reviewCount")
    public int reviewCount(Book book) {
        return reviewService.countByBookId(book.id());
    }
}
~~~

**Book.id** and **Book.title** are read directly from the record. **Book.author** and **Book.reviewCount** have explicit DataFetchers because they need to query services.

This is a common combination: let the property fetcher handle simple fields, and write resolvers only for fields requiring custom logic.

## 14. Testing direct field access

GraphQlTester can verify that properties on the source object are included in the response as expected.

Example:

~~~java
@SpringBootTest
class BookDirectAccessTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReadRecordProperties() {
        graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        id
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

You should test:

1. Record components are read accurately by field name.
2. JavaBean getters are mapped properly.
3. Boolean properties following getter conventions work as expected.
4. Map keys match GraphQL field names.
5. Nested objects and lists are resolved completely.
6. Null properties match SDL nullability.
7. Missing non-null fields produce the expected GraphQL error.
8. Fields with **@SchemaMapping** use their explicit resolvers.
9. Sensitive fields are not exposed through output types.
10. Lazy associations or costly fields do not trigger unexpected N+1 queries.

When checking SQL query counts, add tests at the service/repository layer or enable query statistics in the test environment. Checking only the GraphQL response is not enough to conclude direct access is database-efficient.

## 15. Common pitfalls when using direct field access

| Symptom | Possible cause | Fix |
|---|---|---|
| Field returns null | Property/getter not found or wrong Map key | Check field names and accessors |
| Record component is not read | Component name does not match schema or accessor is incompatible | Check record component and GraphQL field |
| Boolean is always null | Getter does not follow conventions or wrong property name | Use **isX()** for boolean or **getX()** as appropriate |
| Non-null field causes execution error | Property is actually null or missing | Check data and nullability |
| Query generates many SQL statements | Lazy relation getter loads each object individually | Use a fetch plan or batch loading |
| Sensitive field is returned | Schema exposes a property that should stay private | Narrow output DTO and verify authorization |
| Getter causes side effects | Query or business logic placed inside accessor | Move to service or explicit resolver |
| API name differs from Java name | Property fetcher cannot locate property | Update DTO or write **@SchemaMapping** |
| Returning entity creates relationship cycle | Entity graph has bidirectional relationships | Use DTOs and limit field mappings |
| Writing a resolver that only calls a getter | Unnecessary boilerplate code | Let the default property fetcher handle it |

## 16. Workflow for choosing direct access

When adding a field to a GraphQL object type:

1. Determine whether the field already exists on the source object or requires computation/data loading.
2. If the property already exists, check the corresponding getter, record accessor, or Map key.
3. Ensure the property name matches the GraphQL field.
4. Verify the Java type is compatible with the scalar, enum, object, or list in the SDL.
5. Choose nullability based on actual data possibilities.
6. Use records/DTOs as output models when you need control over exposed data.
7. Use **@SchemaMapping** if you need custom logic, renaming, or authorization.
8. Use **@BatchMapping**/DataLoader if the field needs to load data for multiple parents.
9. Inspect lazy loading, query counts, and entity relationships.
10. Write GraphQlTester tests covering property access, nullability, and custom field resolvers.

Direct field access allows GraphQL to return properties already available on the source object without writing a separate DataFetcher for every field. GraphQL Java handles this via PropertyDataFetcher; Spring for GraphQL lets you combine that default seamlessly with **@QueryMapping** and **@SchemaMapping** handlers. Use records/DTOs or JavaBeans with clear accessors, keep field names consistent, and switch to explicit resolvers when data loading, computation, or permission checks are needed. That keeps the schema concise while maintaining control over data and performance.
