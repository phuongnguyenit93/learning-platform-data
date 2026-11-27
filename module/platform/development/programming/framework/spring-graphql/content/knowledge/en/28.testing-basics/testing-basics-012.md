# Testing Schema Mapping

## Objectives

After this lesson, you will be able to:

- Explain why mapping between a GraphQL schema and data fetchers must be tested.
- Use @GraphQlTest to test annotated controllers and @SchemaMapping.
- Verify argument binding, source objects, and nested fields.
- Verify that a nested resolver runs only when its field is selected.
- Test @BatchMapping with multiple parent objects.
- Verify GraphQL errors, partial data, and null propagation caused by field resolvers.
- Use schema mapping inspection to detect missing or mismatched mappings.
- Choose among GraphQlTester, ExecutionGraphQlServiceTester, WebGraphQlTester, and HttpGraphQlTester.

## What Is Schema Mapping?

A GraphQL schema describes the API clients can call: object types, fields, arguments, scalars, enums, interfaces, and unions. Schema mapping connects those declarations to execution logic on the server.

In Spring for GraphQL, an annotated controller method can become the data fetcher for a field:

- @QueryMapping maps a method to a field on the root Query.
- @MutationMapping maps a method to a field on the root Mutation.
- @SubscriptionMapping maps a method to a field on the root Subscription.
- @SchemaMapping maps a method to a field on an object type or interface.
- @BatchMapping batches field resolution across multiple parent objects.

A @SchemaMapping method can accept the parent/source object, arguments, Principal, or DataFetchingEnvironment. When GraphQL executes a query, the framework finds the right data fetcher, binds parameters, invokes the method, and places the result into the response.

Testing schema mapping must verify both sides: the operation must be valid against SDL, and the field must be wired to the right controller method. Calling the Java method directly does not prove that the GraphQL runtime registered the mapping or bound source objects and arguments properly.

## Why Test Through a GraphQL Operation?

Suppose the schema is:

~~~graphql
type Query {
  book(id: ID!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

A client may send:

~~~graphql
query {
  book(id: "book-101") {
    title
    author {
      name
    }
  }
}
~~~

The server must perform a chain of work:

1. Parse and validate the operation against the schema.
2. Call the data fetcher for Query.book.
3. Receive Book as the source object for child fields.
4. Call the mapping for Book.author if the client selected that field.
5. Call the mapping for Author.name or read the corresponding property.
6. Assemble the values into response data.

A unit test that only calls BookController.author(book) will not catch bugs such as:

- Annotation declaring the wrong typeName or field.
- Field missing or misspelled in SDL.
- Source parameter not bound as expected.
- Argument name or type mismatch.
- Resolver not registered with the GraphQL runtime.
- Client not selecting a nested field, so the resolver does not run.

Therefore, send GraphQL documents through a tester to test mappings in their real execution context.

## Choosing the Right Tester

Spring for GraphQL provides testers at multiple layers:

| Tester | Scope | When to Use |
| --- | --- | --- |
| ExecutionGraphQlServiceTester | Direct GraphQL execution via ExecutionGraphQlService | Testing schema, resolvers, and data fetchers without web transport |
| WebGraphQlTester | WebGraphQlHandler and WebGraphQlInterceptor | Also testing web interceptors or request context |
| HttpGraphQlTester | HTTP endpoint via WebTestClient | Testing HTTP routing, headers, filter chains, and transport responses |
| WebSocketGraphQlTester | WebSocket GraphQL transport | Testing subscriptions over WebSocket |

For controller slice tests in Spring Boot, @GraphQlTest is usually a convenient choice. This annotation configures the GraphQL infrastructure and provides GraphQlTester without starting an HTTP server.

If you only want to test execution, you can create ExecutionGraphQlServiceTester directly. If the goal is to verify HTTP filters or security headers, you need HttpGraphQlTester; ExecutionGraphQlServiceTester does not go through the web layer.

## Preparing Schema and Controller

Place the test or application schema under the GraphQL resources directory. Spring Boot's default configuration searches for .graphqls and .gqls files in classpath:graphql/**, typically src/main/resources/graphql.

Example schema:

~~~graphql
type Query {
  book(id: ID!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Java models:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

Book contains authorId so the resolver can look up the author. The schema does not expose authorId; clients only query the author field. This is a common scenario when internal model structures differ from the GraphQL API.

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

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
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book source) {
        return authorService.findById(source.authorId());
    }
}
~~~

The book method handles the root field Query.book. The author method handles the nested field Book.author. The Book source parameter is the parent object returned by the parent resolver.

## Testing Controllers with @GraphQlTest

With Spring Boot 4.2, add the corresponding testing dependencies and let Spring Boot manage versions:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-graphql-test'
}
~~~

spring-graphql-test provides GraphQlTester and layer-specific testers. spring-boot-graphql-test provides the @GraphQlTest slice annotation in Spring Boot 4.x. In Spring Boot 3.x or earlier versions, the artifact and annotation package may differ; use dependency management and documentation matching your project's version.

Example test:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void resolvesBookAndNestedAuthor() {
        Book book = new Book(
                "book-101",
                "Spring for GraphQL",
                "author-12");
        Author author = new Author("author-12", "Ada Nguyen");

        given(bookService.findById("book-101")).willReturn(book);
        given(authorService.findById("author-12")).willReturn(author);

        GraphQlTester.Response response = graphQlTester.document("""
                query BookDetails($id: ID!) {
                    book(id: $id) {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
                .variable("id", "book-101")
                .execute();

        response.path("book.id")
                .entity(String.class)
                .isEqualTo("book-101");

        response.path("book.author.name")
                .entity(String.class)
                .isEqualTo("Ada Nguyen");

        response.errors().verify();

        verify(bookService).findById("book-101");
        verify(authorService).findById("author-12");
    }
}
~~~

@GraphQlTest scans only components belonging to the GraphQL slice, such as @Controller, @ControllerAdvice, RuntimeWiringConfigurer, converters, and DataFetcherExceptionResolver. Regular services are not automatically created in the slice. Use @MockitoBean to replace collaborators, or @Import if a specific supporting configuration is needed in the test.

## Testing Source Objects and Field Arguments

Schema mappings often need both the parent object and child field arguments. Example:

~~~graphql
type Book {
  recommendations(first: Int!): [Book!]!
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "recommendations")
public List<Book> recommendations(
        Book source,
        @Argument("first") int first) {

    return recommendationService.findForBook(source.id(), first);
}
~~~

Test operation:

~~~graphql
query {
  book(id: "book-101") {
    recommendations(first: 3) {
      id
      title
    }
  }
}
~~~

In the test, mock the service to return three books and verify the service receives both the source ID and the first argument:

~~~java
given(recommendationService.findForBook("book-101", 3))
        .willReturn(recommendedBooks);

GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-101") {
                recommendations(first: 3) {
                    id
                    title
                }
            }
        }
        """)
        .execute();

response.path("book.recommendations")
        .entityList(Book.class)
        .hasSize(3);

verify(recommendationService).findForBook("book-101", 3);
~~~

This test verifies that the framework bound the parent Book to the source parameter and bound first to @Argument. If the argument name in the annotation does not match the schema, the operation may fail or the parameter may receive an unexpected value.

## Verifying That a Resolver Runs Only When Selected

GraphQL only resolves fields present in the selection set. If the client requests only title, the Book.author resolver does not need to run.

Example:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotResolveAuthorWhenFieldIsNotSelected() {
    Book book = new Book("book-101", "Spring for GraphQL", "author-12");
    given(bookService.findById("book-101")).willReturn(book);

    graphQlTester.document("""
            query {
                book(id: "book-101") {
                    title
                }
            }
            """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");

    verify(bookService).findById("book-101");
    verifyNoInteractions(authorService);
}
~~~

To run the verifyNoInteractions assertion, import static org.mockito.Mockito.verifyNoInteractions. This check is useful when a nested resolver accesses a database or external service; it confirms the server does not perform work the client did not request.

Avoid excessive interaction assertions. If the implementation is allowed to change how it loads data while keeping the response contract unchanged, prefer asserting the output. Only verify collaborator invocation counts when protecting a performance or batching requirement.

## Testing @BatchMapping

@BatchMapping maps a field for a list of parent objects. Instead of calling a service separately for each Book, the resolver receives List<Book> and loads Authors in a batch:

In the schema for the batch variant, add this root field:

~~~graphql
extend type Query {
  books: [Book!]!
}
~~~

~~~java
@Controller
public class BookBatchController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookBatchController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsForBooks(books);
    }
}
~~~

The test should send a query returning multiple parent objects and selecting the nested author field:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

Fixture setup:

Place BookBatchController in its own test slice using @GraphQlTest(BookBatchController.class), then use @MockitoBean for BookService and AuthorService. Do not put BookController and BookBatchController in the same slice if both register a Book.author mapping.

~~~java
Book firstBook = new Book("book-1", "GraphQL Basics", "author-1");
Book secondBook = new Book("book-2", "Spring APIs", "author-2");
Author firstAuthor = new Author("author-1", "An");
Author secondAuthor = new Author("author-2", "Binh");

given(bookService.findAll()).willReturn(List.of(firstBook, secondBook));
given(authorService.findAuthorsForBooks(List.of(firstBook, secondBook)))
        .willReturn(Map.of(
                firstBook, firstAuthor,
                secondBook, secondAuthor));
~~~

Then assert both branches:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            books {
                id
                author {
                    name
                }
            }
        }
        """)
        .execute();

response.path("books[0].author.name")
        .entity(String.class)
        .isEqualTo("An");

response.path("books[1].author.name")
        .entity(String.class)
        .isEqualTo("Binh");

response.errors().verify();
verify(authorService).findAuthorsForBooks(List.of(firstBook, secondBook));
~~~

This test verifies that the mapping returns the right author for each source object and that the batch service is called with the expected set of parents. If using Map<Book, Author>, Book needs stable equals/hashCode so the map looks up keys reliably. If the resolver returns a List, element order must correspond to parent order per the batch mapping contract.

Do not check only the total service call count while ignoring per-parent results. A batch might run only once yet pair the wrong Author with a Book; path-by-path assertions catch that bug.

## Verifying GraphQL Errors from Schema Mapping

A nested resolver can throw an exception. GraphQL records the error at the field's path and can still return partial data if the field is nullable.

Example schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

If AuthorService cannot find the author and the resolver throws an exception, the test can verify that title still has data while author is null:

~~~java
given(bookService.findById("book-101"))
        .willReturn(new Book("book-101", "Spring for GraphQL", "missing-author"));
given(authorService.findById("missing-author"))
        .willThrow(new AuthorNotFoundException("missing-author"));

GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-101") {
                title
                author {
                    name
                }
            }
        }
        """)
        .execute();

response.path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getPath())
            .containsExactly("book", "author");
});
~~~

If the schema declares author: Author!, the error may propagate up to Book or further per null propagation rules. Tests must reflect the actual nullability in SDL.

If the application has a DataFetcherExceptionResolver or @GraphQlExceptionHandler, check the error code in extensions to protect the error contract. Do not rely solely on free-form messages because messages can be edited or localized.

## Schema Mapping Inspection

Some mapping mistakes do not necessarily cause application startup to fail. For example, a schema may have a field with no registered data fetcher and no corresponding property on the source object; the field may return null without an obvious exception.

Spring for GraphQL provides schema mapping inspection to audit mappings at startup. Inspection can detect:

- Schema fields with no corresponding data fetcher or property.
- Data fetchers registered for fields that do not exist in the schema.
- Arguments in controller methods that do not match schema field arguments.
- Certain nullability differences between the schema and Java types when type information can be determined.

It can be configured via GraphQlSource.Builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;

@Configuration
public class GraphQlInspectionConfiguration {

    private static final Logger logger =
            LoggerFactory.getLogger(GraphQlInspectionConfiguration.class);

    @Bean
    GraphQlSourceBuilderCustomizer schemaMappingInspection() {
        return builder -> builder.inspectSchemaMappings(
                report -> logger.info("GraphQL schema mapping inspection:\n{}", report));
    }
}
~~~

The inspection report is a supplementary diagnostic. It does not replace GraphQL integration tests: inspection cannot verify runtime data, access permissions, business branches, or repository results. Conversely, tests only cover operations they send; inspection helps uncover fields that tests have not exercised yet.

When interfaces or unions are present, some mappings may lack sufficient Java type information for inspection to conclude. Read the skipped types section in the report as well and add type mappings if needed.

## Testing with ExecutionGraphQlServiceTester

If you are not using a Spring Boot slice test, you can create a tester directly from ExecutionGraphQlService:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);
~~~

This tester runs operations at the server execution layer without HTTP or WebSocket transport. It is suitable for applications that configure GraphQlSource and ExecutionGraphQlService themselves, or when testing a specific execution configuration.

If a test needs to verify WebGraphQlInterceptor, use WebGraphQlTester with WebGraphQlHandler. If you need to verify HTTP requests actually hitting the server, use HttpGraphQlTester. Do not pick ExecutionGraphQlServiceTester and conclude that HTTP filters or authentication headers work.

## Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Controller method is not invoked | Wrong annotation, typeName, or field name | Match the annotation with the schema and query |
| Query returns null despite controller having the method | Mapping not registered or incompatible method signature | Check @Controller, GraphQlSource, and test via GraphQL operation |
| Nested resolver does not run | Client did not select the nested field | Check the selection set |
| Resolver receives wrong source object | Method expects wrong parent type or wrong typeName mapping | Check source parameter and GraphQL parent type |
| Argument receives null or default value | Argument name mismatch or schema allows null | Use @Argument with an explicit name and check SDL |
| Test passes despite broken mapping | Test called the Java method directly | Send documents through GraphQlTester |
| @GraphQlTest cannot find service | Slice test does not scan regular components | Use @MockitoBean or @Import |
| Batch mapping returns wrong parent-child pairs | Map keys or List ordering is incorrect | Assert nested values for each parent |
| Null field with no error | No data fetcher and no corresponding property | Add a resolver and enable schema mapping inspection |
| Child field failure wipes out parent object | Field or parent is declared non-null | Check nullability and partial data contract |
| Test fails to check HTTP authentication | Using a tester that bypasses transport | Use HttpGraphQlTester with WebTestClient |

## Comprehensive Practice

Build a test suite for a library schema:

1. Create a schema with Query.book, Book.author, and Book.recommendations(first: Int!).
2. Write BookController with @QueryMapping and two @SchemaMapping methods.
3. Use @GraphQlTest to create a slice test and inject GraphQlTester.
4. Mock BookService, AuthorService, and RecommendationService with @MockitoBean.
5. Send a query fetching Book.author.name and verify the parent object is passed properly.
6. Send a query with recommendations(first: 3) and verify the field argument is bound properly.
7. Send a query selecting only title and verify the author resolver is not called.
8. Create a variant using @BatchMapping to load authors for multiple books.
9. Verify nested field results per parent object, not just batch invocation counts.
10. Add a case where a resolver throws an exception and check error path, partial data, and null propagation.
11. Enable schema mapping inspection to audit unmapped fields and arguments.
12. Add WebGraphQlTester or HttpGraphQlTester if you need to test interceptors or HTTP transport.

After completing it, explain why sending GraphQL operations is necessary instead of calling controller methods directly, how GraphQL passes source objects down to nested resolvers, and why batch mapping tests must check results per parent.

## Takeaways

Schema mapping connects fields in GraphQL SDL to server-side data fetchers. Use @GraphQlTest and GraphQlTester to test operations through the runtime, including root mappings, nested mappings, source objects, and argument binding. With @BatchMapping, verify that each parent receives its matching result. Also verify errors, partial data, and null propagation when resolvers fail. Schema mapping inspection adds the ability to spot unmapped fields or arguments right at startup. Choose ExecutionGraphQlServiceTester for the execution layer, WebGraphQlTester for web handlers/interceptors, and HttpGraphQlTester for HTTP transport.

## References

- [Spring Boot – Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL – Annotated Controllers and Schema Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL – Schema Mapping Inspection](https://docs.spring.io/spring-graphql/reference/request-execution.html)
