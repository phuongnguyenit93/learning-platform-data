# Argument name and parameter name in Spring for GraphQL

In GraphQL SDL, each field can declare arguments with names determined by the schema. In a Java controller, handler methods receive those values via method parameters, typically using the `@Argument` annotation. Spring for GraphQL needs to know which GraphQL argument name should be bound to each Java parameter.

The GraphQL argument name and the Java parameter name can be identical or different. When they match and the compiler preserves parameter name metadata, Spring can infer the name automatically. When they differ, or when you want the code to be independent of compiler metadata, specify the name explicitly using `@Argument("...")`.

## 1. Two kinds of names with different roles

Consider the schema:

```graphql
type Query {
    bookById(bookId: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

`bookId` is the argument name in the GraphQL API. It is part of the contract that clients use:

```graphql
query {
    bookById(bookId: "book-10") {
        id
        title
    }
}
```

In Java, the method parameter can be named `bookId`, `id`, `requestedId`, or something else. The Java name only serves server-side code. Spring for GraphQL needs to map the GraphQL name `bookId` to the right Java parameter.

```java
@QueryMapping
public Book bookById(@Argument("bookId") String id) {
    return bookService.findById(id).orElse(null);
}
```

In this example, the GraphQL argument is `bookId`, while the Java parameter is `id`. The value from `bookId` is bound to `id` thanks to the name specified in `@Argument`.

| Concept | Example | Role |
| --- | --- | --- |
| GraphQL argument name | `bookId` in SDL | The name the client must use when calling the field. |
| Java parameter name | `id` in method | The variable name used inside the method body. |
| `@Argument` name | `@Argument("bookId")` | Specifies which GraphQL argument to bind to the parameter. |

## 2. Explicitly declaring the argument name with `@Argument`

`@Argument` is located in the `org.springframework.graphql.data.method.annotation` package. You can pass the GraphQL argument name directly into the annotation:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("bookId") String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`@Argument("bookId")` explicitly targets the argument named `bookId`. The Java variable name `id` can be changed without altering the schema or client queries. This style is useful when:

- The GraphQL name follows an API convention that differs from the Java naming in code.
- The Java parameter has a short name or carries a domain-specific meaning.
- You want to avoid depending on compiler metadata.
- You are maintaining a long-lived API and want readable mappings right at the method signature.

The annotation also supports the `name` attribute, e.g., `@Argument(name = "bookId")`. The `value` attribute is an alias for `name`, so `@Argument("bookId")` and `@Argument(name = "bookId")` have the exact same meaning.

## 3. Inferring the argument name from the Java parameter name

If no name is specified in `@Argument`, Spring for GraphQL defaults to using the Java parameter name when that name can be discovered from the compiled class.

SDL example:

```graphql
type Query {
    bookById(bookId: ID!): Book
}
```

Controller:

```java
@QueryMapping
public Book bookById(@Argument String bookId) {
    return bookService.findById(bookId).orElse(null);
}
```

Because the Java parameter is named `bookId`, Spring infers the GraphQL argument is also named `bookId`. Clients continue calling `bookById(bookId: ...)` as declared in the SDL.

For Java reflection to read parameter names, classes must be compiled with parameter name metadata. With Java 8 and later, the explicit and recommended way is to enable the `-parameters` compiler option. Some compiler versions/configurations may also expose names via debug information, but you should not rely on that behavior if builds must remain consistent across environments.

If parameter name metadata is missing and `@Argument` does not specify a name, the framework cannot reliably infer which argument to retrieve. In that case, enable `-parameters` or declare the name explicitly in the annotation.

## 4. Enabling `-parameters` in Maven

With the Maven Compiler Plugin, enable the `parameters` option:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This configuration instructs the compiler to write parameter names into the bytecode so Java reflection can access them. If the project manages plugins in `pluginManagement`, ensure the configuration is placed where the plugin is actually applied to the compiling module.

After making the change, recompile the sources so new classes with metadata are generated. Editing `pom.xml` alone while running old `.class` files may still result in parameter names not being found.

## 5. Enabling `-parameters` in Gradle

With the Gradle Java plugin, you can add the compiler argument to `JavaCompile` tasks:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

If the build uses Kotlin DSL (`build.gradle.kts`):

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Place this configuration in the build script of the module containing the controllers or in a shared convention configuration suitable for the project. Then re-run compile/test so classes are built with the new parameter metadata.

## 6. Comparing the two mapping approaches

Suppose the schema has an `authorId` argument:

```graphql
type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
```

First approach: rely on the Java parameter name for inference:

```java
@QueryMapping
public List<Book> booksByAuthor(@Argument String authorId) {
    return bookService.findByAuthor(authorId);
}
```

Second approach: declare the GraphQL argument name explicitly:

```java
@QueryMapping
public List<Book> booksByAuthor(@Argument("authorId") String id) {
    return bookService.findByAuthor(id);
}
```

Both approaches produce equivalent results if parameter metadata is available in the first approach. The explicit approach does not depend on Java variable names or compiler flags; the inferred approach is shorter when both names match and the build guarantees metadata.

| Criterion | Inferred from parameter name | Explicit name in `@Argument` |
| --- | --- | --- |
| Syntax | Shorter | Mapping is clear right at the annotation |
| Metadata requirement | Requires discoverable parameter names | Does not require parameter name metadata |
| Renaming Java variable | May require changing GraphQL argument or annotation | Does not affect GraphQL mapping |
| Best suited for | Consistent Java and SDL names | Different Java and SDL names or stable explicit mapping |

In a large codebase, a team can agree on a convention: use `@Argument("...")` for arguments whose names differ from Java parameters; use inference when names match and `-parameters` is enabled across all modules. The key is consistent team adoption and testing the build configuration.

## 7. Argument names with input objects

`@Argument` does not bind only scalars. When an argument is an input object, Spring for GraphQL can bind the value into a Java record or class.

Schema:

```graphql
input BookSearchInput {
    keyword: String
    authorId: ID
    publishedAfter: String
}

type Query {
    searchBooks(filter: BookSearchInput!): [Book!]!
}
```

Java input record and resolver:

```java
public record BookSearchCriteria(
        String keyword,
        String authorId,
        String publishedAfter) {
}
```

```java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") BookSearchCriteria criteria) {
    return bookService.search(criteria);
}
```

Here, `filter` is the GraphQL argument name. `BookSearchCriteria` is the Java type receiving that argument's value. The Java class name does not have to match `BookSearchInput`, but its properties/constructor parameters must be compatible with the fields inside the input object.

Spring uses `GraphQlArgumentBinder` to instantiate the target object. For records or classes with a primary/data constructor, the binder maps input values into the constructor. For classes with a default constructor, the binder can instantiate an object and assign values via setters. Binding runs recursively for nested input objects.

Record components have their names stored in record metadata; for classes using regular constructors, ensure constructor parameter names are discoverable if the binder relies on them. Keeping Java component/property names aligned with SDL fields makes binding predictable. If the schema and Java properties must follow different naming conventions, you can customize `GraphQlArgumentBinder` via `AnnotatedControllerConfigurer` and a `nameResolver` instead of arbitrarily renaming public schema fields.

## 8. Distinguishing `@Argument` and `@Arguments`

These two annotations have different scopes:

- `@Argument` retrieves a single named argument from the current field and binds its value to the parameter.
- `@Arguments` retrieves the entire top-level argument map of the field and binds that map into an object or `Map`.

Example SDL with two separate arguments:

```graphql
type Query {
    searchBooks(keyword: String, limit: Int): [Book!]!
}
```

Use `@Argument` to retrieve each argument individually:

```java
@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") String text,
        @Argument("limit") Integer pageSize) {
    return bookService.search(text, pageSize);
}
```

Use `@Arguments` to bind all arguments into a record:

```java
public record SearchBooksArguments(String keyword, Integer limit) {
}
```

```java
import org.springframework.graphql.data.method.annotation.Arguments;

@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(arguments.keyword(), arguments.limit());
}
```

With `@Arguments Map<String, Object>`, the method receives the raw map of all arguments. With `@Argument("filter") Map<String, Object>`, the method receives the raw map of the `filter` argument alone. Do not use `@Argument Map` to retrieve the entire argument map; for that purpose, use `@Arguments Map`.

## 9. GraphQL and Java naming conventions

GraphQL typically uses `camelCase` for fields and arguments:

```graphql
type Query {
    booksByAuthor(authorId: ID!, pageSize: Int = 20): [Book!]!
}
```

Java also typically uses `camelCase` for parameters:

```java
@QueryMapping
public List<Book> booksByAuthor(
        @Argument String authorId,
        @Argument Integer pageSize) {
    return bookService.findByAuthor(authorId, pageSize);
}
```

When names match, the code is concise and readable. When they differ, express the mapping via the annotation:

```java
@QueryMapping
public List<Book> booksByAuthor(
        @Argument("authorId") String writerId,
        @Argument("pageSize") Integer limit) {
    return bookService.findByAuthor(writerId, limit);
}
```

Do not rename a GraphQL argument just to match a local Java variable. A GraphQL argument is part of the public contract and may be used by multiple clients. Keep schema names stable, and map them to internal names with `@Argument`.

## 10. Argument names do not determine requiredness or default values

`@Argument` is used to specify the argument to bind; the annotation has no `required` or `defaultValue` attributes. Requiredness and default values are declared in the GraphQL SDL.

```graphql
type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}
```

In the schema above:

- `id: ID!` is a required argument. GraphQL rejects requests missing `id` or passing null.
- `limit: Int = 20` has a default value of 20 when the client omits the argument.
- `limit` is nullable so the client can explicitly pass null; the default does not replace an explicitly sent null value.

The resolver only needs to bind the argument:

```java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}

@QueryMapping
public List<Book> books(@Argument("limit") Integer limit) {
    return bookService.findRecent(limit);
}
```

If `limit` can be null, the service should clearly define how to handle it, or the schema should provide a default/Non-Null tailored to the business rules. Do not expect annotation attributes to replace SDL validation rules.

## 11. Binding errors and how to diagnose them

If a GraphQL argument cannot be bound to the target Java type, Spring for GraphQL can throw a `BindException` containing field-path errors within the input. For example, the input includes `filter.authorId`, but the Java record lacks a corresponding constructor/property or the data type cannot be converted.

When diagnosing, check in order:

1. Does the argument name in the SDL match `@Argument("...")` or the inferred Java parameter name?
2. Does the build enable `-parameters` if name inference is being used?
3. Is the client sending the right argument name and the right GraphQL type?
4. If the argument is an input object, are the Java constructors/properties compatible with the input type's fields?
5. Are there nested types or collections that the binder needs to convert?
6. Is there any custom conversion or `GraphQlArgumentBinder` configuration altering how binding behaves?

Example error due to name mismatch:

```graphql
type Query {
    bookById(bookId: ID!): Book
}
```

```java
// Wrong if parameter metadata indicates the name is "id" and there is no "id" argument.
@QueryMapping
public Book bookById(@Argument String id) {
    return bookService.findById(id).orElse(null);
}
```

Fix by specifying the GraphQL argument name explicitly:

```java
@QueryMapping
public Book bookById(@Argument("bookId") String id) {
    return bookService.findById(id).orElse(null);
}
```

Or rename the parameter to `bookId` and ensure the compiler preserves parameter metadata.

## 12. Testing argument name mappings

You should test resolvers through GraphQL documents to confirm the SDL contract and method parameters work together properly.

Example testing an explicitly mapped argument:

```java
@Test
void explicitArgumentNameIsBoundToJavaParameter() {
    graphQlTester.document("""
            query FindBook($id: ID!) {
                bookById(bookId: $id) {
                    title
                }
            }
            """)
        .variable("id", "book-10")
        .execute()
        .path("bookById.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
}
```

Example testing an input object:

```java
@Test
void namedInputArgumentIsBoundToRecord() {
    graphQlTester.document("""
            query Search($filter: BookSearchInput!) {
                searchBooks(filter: $filter) {
                    title
                }
            }
            """)
        .variable("filter", Map.of("keyword", "spring"))
        .execute()
        .path("searchBooks[0].title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
}
```

These examples assume `graphQlTester`, the service, and test fixtures are configured in the test context. If your project relies on parameter name inference, keep an integration test running against classes compiled with the actual build configuration. Testing only via an IDE or a different build tool than production might miss a missing `-parameters` flag.

Cases you should test:

1. Argument name matches parameter name and is successfully inferred.
2. GraphQL argument name differs from Java parameter name and `@Argument("...")` maps it properly.
3. A build lacking parameter metadata still works when annotations declare explicit names.
4. Missing or null required arguments are rejected by GraphQL per SDL.
5. Arguments with defaults receive the expected value when omitted.
6. Input objects bind accurately to records/classes, including nested fields.
7. `@Argument Map` and `@Arguments Map` receive their respective scopes of data.

## 13. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Argument not found when method uses unnamed `@Argument` | Java parameter name is not stored in bytecode | Enable `-parameters` or write `@Argument("name")`. |
| Resolver receives null even though client sends a value | Name in SDL does not match annotation/parameter name | Compare argument names and mapping in method signature. |
| Renaming Java variable breaks queries | Mapping depends on inferred parameter name | Use an explicit name in `@Argument` or keep names in sync. |
| Using `@Argument Map` receives only partial data | Annotation retrieves a single specified argument | Use `@Arguments Map` if you need the entire argument map. |
| Input object fails to bind | Java constructor/properties incompatible with input type | Check record components, constructors, setters, and nested types. |
| Expecting `@Argument` to enforce required values | Confusing binding annotation with schema validation | Declare `!` or defaults in SDL. |
| Works locally but fails in another environment | Inconsistent compiler configuration across modules | Standardize `-parameters` and test artifacts built in CI. |

## 14. Checklist for mapping argument names

1. Identify the official argument name in the GraphQL SDL.
2. If the Java parameter has the same name, enable `-parameters` so Spring can infer it.
3. If the names differ or you want compiler-independent mapping, use `@Argument("graphqlName")`.
4. Use `@Argument` for a single argument; use `@Arguments` for the entire top-level argument map.
5. For input objects, ensure the Java record/class has compatible constructors or properties.
6. Put requiredness/defaults in the SDL, not by looking for attributes on `@Argument`.
7. Keep GraphQL names stable when refactoring Java variables.
8. Test explicit mappings, name inference, and the actual build configuration.

The GraphQL argument name belongs to the API contract; the Java parameter name belongs to the resolver implementation. Spring for GraphQL connects both sides via `@Argument`, either inferring from parameter names or using an explicit name to control the mapping. Understanding both options and configuring the compiler consistently makes controllers easier to read, less prone to binding errors, and safer to refactor.

Reference: [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html).
