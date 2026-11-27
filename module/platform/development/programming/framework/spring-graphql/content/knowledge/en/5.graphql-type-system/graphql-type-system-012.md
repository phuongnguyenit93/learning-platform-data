# Type compatibility when mapping Java

## Objectives

After this lesson, you will be able to:

- Choose Java types that match scalars and data types in GraphQL SDL.
- Distinguish GraphQL nullability from Java's ability to hold null.
- Map lists, enums, input objects, object types, interfaces, and unions.
- Use @Argument, @QueryMapping, and @SchemaMapping to connect the schema to Java methods.
- Recognize when custom scalars or type resolvers are needed.
- Detect mismatches between the schema and Java signatures before running queries.

## 1. Why care about type compatibility?

A GraphQL schema is the data-type contract visible to clients. Java is the server language used to receive arguments, invoke business logic, and return results. Both sides must agree on types, structures, and whether values can be empty/null.

Example SDL declaration:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  pageCount: Int
  rating: Float
}
~~~

A Java controller can receive id as a String and return a Book object. If Java returns null for the title field while the schema declares String!, GraphQL raises an execution error and applies null propagation rules.

Similarly, if the schema declares pageCount: Int yet Java uses a Long value exceeding the 32-bit integer range, the data no longer conforms to the GraphQL contract.

Type compatibility therefore spans several aspects:

- Scalar types can serialize and parse correctly.
- Object and list structures match the schema.
- Nullability is respected at both field and list-element levels.
- Input arguments can bind to Java parameters.
- Concrete Java types can be resolved to the corresponding GraphQL object type.
- Enums and custom scalars follow consistent conversion rules.

## 2. Mapping GraphQL scalars to Java

GraphQL defines five basic scalars: Int, Float, String, Boolean, and ID. When implementing in Java, choose a representation that fits the range and semantics of each scalar.

| GraphQL scalar | Common Java type | Notes |
|---|---|---|
| String | String | Unicode character string |
| Boolean | Boolean or boolean | Use wrapper if the field can be null |
| Int | Integer or int | Signed 32-bit integer |
| Float | Double or double | Double-precision floating-point number |
| ID | String | Treat ID as an opaque identifier, do not assume it is numeric |

### Int is not synonymous with every Java integer type

GraphQL Int has a signed 32-bit integer range, from -2,147,483,648 to 2,147,483,647. Java Integer shares the same range and is the natural choice.

Java Long has a wider range. Do not use Long to represent a GraphQL Int field if values can exceed the 32-bit limit. If the business domain needs large integers, pick an explicit approach:

- Use a custom scalar with clear serialize/parse rules.
- Use ID if the value is purely an identifier.
- Use String if large numbers need to be passed as text and clients process them under an explicit contract.

Do not change a quantity or monetary field to ID merely to avoid integer range limits. GraphQL types should reflect business semantics.

### Float and precision

GraphQL Float is a double-precision floating-point number. Java Double is the common matching type. Java BigDecimal can represent decimal numbers with higher precision, but it is not synonymous with the Float scalar.

For prices or financial data requiring exact decimal precision, consider a custom scalar such as Decimal and define how it parses, serializes, and formats over JSON. Do not rely on Double when floating-point rounding errors can affect business outcomes.

### ID should be treated as an identifier

GraphQL ID is serialized as a string. Input values may be passed as either a string or an integer, but the API should treat ID as an identifier, not an arithmetic measurement.

Example:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Using String decouples Java from whether IDs are generated from auto-incrementing numbers, UUIDs, or another opaque format.

## 3. Nullability: GraphQL ! and Java primitives/wrappers

GraphQL uses `!` to declare that a value cannot be null. Java has two relevant type categories:

- Primitives such as int, long, boolean: always have a default value and cannot represent null.
- Reference types such as Integer, Long, Boolean, String, and objects: can hold null.

Therefore, choose Java types according to nullability in the SDL:

| GraphQL | Common Java type | Meaning |
|---|---|---|
| String | String | Can return null |
| String! | String | Application must guarantee a value |
| Int | Integer | Can return null |
| Int! | int or Integer | Must not return null |
| Boolean | Boolean | Can return null |
| Boolean! | boolean or Boolean | Must not return null |

Primitives do not automatically guarantee correct business logic. For instance, using int pageCount for a nullable field leaves Java unable to represent an absent page count; the default value 0 could be mistaken for real data. Use Integer if the field can be missing.

### Null propagation in GraphQL

Suppose the schema is:

~~~graphql
type Book {
  title: String!
  subtitle: String
}
~~~

If the resolver returns null for subtitle, the response remains valid because that field is nullable. If the resolver returns null for title, GraphQL raises an error and bubbles null up to the nearest nullable parent field.

If the parent field is also non-null, propagation continues upward. Consequently, a null value on a child field can turn an entire object or a large portion of the response into null.

Do not mark every field non-null just to make the schema appear strict. Use ! when data and business rules genuinely guarantee the value always exists.

## 4. Mapping lists and collections

GraphQL uses square bracket syntax to declare lists. Java typically represents these fields using List<T>, Collection<T>, arrays, or an appropriate collection type.

Example:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Several nullability variants must be distinguished:

| SDL | List can be null? | Element can be null? |
|---|---:|---:|
| [Book] | Yes | Yes |
| [Book!] | Yes | No |
| [Book]! | No | Yes |
| [Book!]! | No | No |

Java generics such as List<Book> describe the element type at compile time, but do not encode both levels of nullability by themselves. The GraphQL engine still enforces schema nullability rules when serializing results.

For example, with [Book!]!, the resolver must return a non-null list containing no null elements. If a null element appears, GraphQL raises an error and applies null propagation according to the schema structure.

### Reactive collections

Spring for GraphQL supports reactive return types. Common forms include:

- Mono<Book>: zero or one result.
- Flux<Book>: a stream of multiple results, commonly used for list fields or Subscriptions.
- List<Book>: synchronous list.

Subscription example:

~~~graphql
type Subscription {
  bookEvents: BookEvent!
}
~~~

~~~java
@SubscriptionMapping
public Flux<BookEvent> bookEvents() {
    return bookService.events();
}
~~~

Subscriptions require a publisher to emit multiple values over time. Queries or Mutations can use synchronous or reactive types depending on the service architecture.

## 5. Mapping object types to Java classes

GraphQL object types are typically represented by POJOs, records, or domain objects on the Java side. By default, GraphQL Java can use PropertyDataFetcher to read data from the source object by field name.

Example SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  pageCount: Int
}
~~~

Java class:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final Integer pageCount;

    public Book(String id, String title, Integer pageCount) {
        this.id = id;
        this.title = title;
        this.pageCount = pageCount;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Integer getPageCount() {
        return pageCount;
    }
}
~~~

If Query returns a Book object, GraphQL can read the id, title, and pageCount fields from the corresponding getters.

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

GraphQL field names and Java property names must follow matching conventions. If names differ or values must be computed, declare an explicit mapping:

~~~java
@SchemaMapping(typeName = "Book", field = "displayTitle")
public String displayTitle(Book book) {
    return book.getTitle().toUpperCase();
}
~~~

@SchemaMapping binds the method to a field of a GraphQL type. The source parameter Book comes from the parent object currently being resolved. The method's return type must match the displayTitle field's type in the SDL.

There is no need to write a separate resolver for every simple property. Leverage default property mapping when names and structures align; use @SchemaMapping when a field needs custom logic or its own data source.

## 6. Mapping input objects to Java DTOs

GraphQL uses input types to describe data clients are allowed to send in. An input object is an input type and cannot be replaced directly with a GraphQL object type.

Example SDL:

~~~graphql
input UpdateBookInput {
  title: String!
  pageCount: Int
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book
}
~~~

Java DTO:

~~~java
public record UpdateBookInput(
        String title,
        Integer pageCount) {
}
~~~

Controller:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {

    return bookService.update(
            id,
            input.title(),
            input.pageCount());
}
~~~

Spring for GraphQL uses GraphQlArgumentBinder to bind GraphQL argument data into Java parameters. The binder supports nested structures and can instantiate objects via constructors or populate matching properties. Java records are a concise choice for immutable DTOs with matching constructors.

Field names in the input object must match property names or constructor parameters usable by the binder. If the structure is complex, inspect the DTO and nested data types to avoid runtime binding errors.

### Distinguishing omitted and explicit null

In GraphQL, an input field can be omitted or explicitly sent with a null value. These two cases can have different business meanings, for example:

- Omitting subtitle: keep the current subtitle unchanged.
- Sending subtitle: null: remove the subtitle.

Example schema for a patch operation:

~~~graphql
type Mutation {
  patchBook(id: ID!, subtitle: String): Book
}
~~~

A plain Java String parameter is insufficient to reliably distinguish these two states after binding. Spring for GraphQL provides ArgumentValue<T> to represent an argument value while distinguishing the omitted case from the explicitly passed null case.

Example:

~~~java
@MutationMapping
public Book patchBook(
        @Argument("id") String id,
        @Argument("subtitle") ArgumentValue<String> subtitle) {

    if (!subtitle.isOmitted()) {
        return bookService.updateSubtitle(id, subtitle.value());
    }

    return bookService.findById(id);
}
~~~

This approach is helpful for patch-style mutations. Design the schema, DTOs, and update logic consistently so an omitted field is never accidentally treated as a data deletion.

## 7. Mapping enums

GraphQL enums constrain a field's value to a defined set of names.

SDL:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  status: BookStatus!
}
~~~

Java:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

When enum value names in SDL match Java enum constant names, GraphQL Java can map them by name by default.

If the system uses different names—for instance, Java has IN_REVIEW while the schema exposes PENDING_REVIEW—configure an enum value mapping in RuntimeWiring instead of assuming the two names are automatically compatible.

Avoid using arbitrary strings for an enum field when a Java enum can be used. Enum types restrict valid values in code and reduce typos.

## 8. Mapping interfaces and unions

GraphQL interfaces and unions are abstract types. A field can return multiple concrete object types. When that happens, GraphQL needs to determine the object's actual type to know which fields are allowed to be returned.

SDL:

~~~graphql
interface SearchResult {
  id: ID!
}

type Book implements SearchResult {
  id: ID!
  title: String!
}

type Author implements SearchResult {
  id: ID!
  name: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

Java can use a shared interface:

~~~java
public interface SearchResult {
    String getId();
}

public class BookResult implements SearchResult {
    private final String id;
    private final String title;

    public BookResult(String id, String title) {
        this.id = id;
        this.title = title;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}

public class AuthorResult implements SearchResult {
    private final String id;
    private final String name;

    public AuthorResult(String id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

When Java objects do not carry enough information for GraphQL to identify the concrete type automatically, configure a TypeResolver. Spring for GraphQL can use ClassNameTypeResolver to infer GraphQL types from class names by convention. If class names and GraphQL type names do not match, or multiple classes share no inheritance hierarchy, use a custom type resolver.

Example resolver configuration:

~~~java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return wiringBuilder -> wiringBuilder.type("SearchResult", typeBuilder ->
        typeBuilder.typeResolver(environment -> {
            Object value = environment.getObject();

            if (value instanceof BookResult) {
                return environment.getSchema()
                        .getObjectType("Book");
            }

            if (value instanceof AuthorResult) {
                return environment.getSchema()
                        .getObjectType("Author");
            }

            throw new IllegalStateException(
                    "Unsupported SearchResult type: " + value.getClass().getName());
        })
    );
}
~~~

For unions, the approach is similar: GraphQL must determine the concrete object type among the union's declared members. The result from the resolver must be a valid GraphQL object type according to the schema.

## 9. Custom scalars for specialized Java types

Built-in scalars cannot express every business data type. For example:

- LocalDate or OffsetDateTime.
- UUID.
- Decimal with exact precision requirements.
- Monetary values or custom-formatted identifiers.

In such cases, you can declare scalars in SDL:

~~~graphql
scalar DateTime
scalar Decimal

type Invoice {
  id: ID!
  issuedAt: DateTime!
  total: Decimal!
}
~~~

And register the corresponding coercing in runtime wiring:

~~~java
@Bean
RuntimeWiringConfigurer customScalars() {
    return wiringBuilder -> wiringBuilder
            .scalar(dateTimeScalar())
            .scalar(decimalScalar());
}
~~~

Each custom scalar must clearly specify:

- How to parse values from JSON variables.
- How to parse literals in GraphQL documents if supported.
- How to serialize Java values into JSON responses.
- How to handle invalid input and error messages.

Do not merely rename a scalar to DateTime without registering how it converts. Without an appropriate coercing implementation, GraphQL does not know how to translate between wire values and application Java types.

## 10. Schema mapping inspection and compatibility checks

A syntactically valid SDL does not guarantee that every Java method maps properly. Example:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Yet the controller declares:

~~~java
@QueryMapping
public List<Book> book(@Argument("id") String id) {
    return bookService.findRelatedBooks(id);
}
~~~

The book field in the schema returns a single Book, while the Java method returns a list. This is a structural result mismatch.

Spring for GraphQL supports schema mapping inspection to find certain incompatibilities between the schema and data fetchers, such as fields missing a mapping or Java signatures mismatching GraphQL types that inspection can infer.

You can enable inspection when building the source:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .inspectSchemaMappings(System.out::println)
        .build();
~~~

Inspection is helpful, but it does not replace runtime testing. It cannot know for sure what values repositories actually return in every scenario, nor can it prove that data always satisfies business rules.

Combine these verification methods:

1. **Schema validation:** verify SDL and queries against the GraphQL schema.
2. **Schema mapping inspection:** find unmapped fields and incompatible Java signatures detectable by the tool.
3. **Controller tests:** test argument binding and resolver return types.
4. **Integration tests:** execute real operations with representative data, including nulls, empty lists, and business errors.

## 11. Common mapping errors

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Non-null field errors on response | Java returned null | Check data, resolver, and nullability contract |
| GraphQL Int fails to serialize | Value exceeds 32-bit range or incompatible type | Use Integer within range; design a custom scalar if needed |
| Object field returns null | Getter/property does not match field name | Verify property name or declare @SchemaMapping |
| Input binding fails | DTO lacks matching constructor/property or nested type is incompatible | Inspect input structure and Java DTO |
| Enum fails to convert | Enum value name differs from Java constant name | Configure enum value mapping |
| Interface/union cannot resolve type | Missing or incorrect TypeResolver | Configure type resolver for actual objects |
| Decimal loses precision | Using Float/Double for data requiring exactness | Use custom scalar and BigDecimal |
| List violates nullability | Contains null element or entire list is null | Ensure data conforms to [T], [T!], [T]!, or [T!]! |

## 12. Principles for designing GraphQL-compatible Java models

When designing models and resolvers, apply these principles:

- Choose Java wrapper types for nullable GraphQL fields.
- Use primitives only when business rules guarantee a value can never be null.
- Use String for opaque IDs; do not assume IDs are always numeric.
- Use Integer for GraphQL Int and enforce 32-bit bounds.
- Use custom scalars when representing domain types that do not map directly to standard scalars.
- Use dedicated DTOs for input objects when the request structure differs from the domain model.
- Use Java enums when the schema restricts values to a fixed set.
- Use @SchemaMapping when default property mapping is insufficient.
- Configure a TypeResolver whenever GraphQL returns an interface or union.
- Check nullability and collections at both the list level and the element level.

The schema should describe a stable API contract, while Java models should reflect application needs. You do not have to use persistence entities directly as GraphQL outputs or inputs. DTOs prevent database schemas from dictating the public API and help control which data gets exposed.

## Conclusion

Type compatibility when mapping Java is the alignment between GraphQL types in SDL and the data Java accepts or returns. Key areas include scalars, nullability, collections, enums, input binding, object property mapping, and abstract type resolution.

Spring for GraphQL provides @Argument, @QueryMapping, @SchemaMapping, GraphQlArgumentBinder, RuntimeWiringConfigurer, and schema mapping inspection to bridge both sides. By choosing appropriate Java types, designing explicit nullability, and testing both the schema and resolvers, your API will reduce conversion errors and keep the GraphQL contract consistent.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Schema Mapping Inspection](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Specification — Type System](https://spec.graphql.org/October2021/#sec-Type-System)
- [GraphQL Java — Documentation](https://www.graphql-java.com/documentation/)
