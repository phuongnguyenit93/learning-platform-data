# Building Queries and @QueryMapping

In Spring for GraphQL, a read operation starts from a field of the root `Query` type in the SDL schema. Spring maps that field to a Java method using `@QueryMapping`; the method calls a service to fetch data and returns the result to the GraphQL runtime. This hands-on practice builds a book lookup API to demonstrate the full flow from schema and resolver to request and testing.

## 1. Objectives and Scenario

Suppose a book catalog management application needs to provide three read operations:

- Retrieve all books.
- Find a book by its ID.
- Search books by a keyword in the title or author name.

After this lesson, you will be able to:

1. Declare `Query` fields and return types using SDL.
2. Write a GraphQL controller with `@Controller` and `@QueryMapping`.
3. Receive query parameters using `@Argument`.
4. Choose appropriate return types and handle cases where data is not found.
5. Send GraphQL queries with variables and test resolvers using `GraphQlTester`.

We focus on fields at the `Query` level. Resolving nested relationship fields and optimizing N+1 queries will be covered in the lessons on `@SchemaMapping`, `@BatchMapping`, and `DataLoader`.

## 2. Project Setup

Use a Spring Boot application with Spring for GraphQL and an HTTP server. With Maven, the main dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Spring Boot looks for schema files in `classpath:graphql/` by default and exposes the HTTP endpoint at `/graphql`. Create the file:

~~~text
src/main/resources/graphql/schema.graphqls
~~~

If you want to change the endpoint, you can configure it in `application.properties`:

~~~properties
spring.graphql.path=/graphql
~~~

If you keep the default value above, there is no need to declare this property. The schema filename can be different as long as it is located in the schema locations configured for the application.

## 3. Declaring the SDL Schema

Create `schema.graphqls` with the following content:

~~~graphql
type Query {
    books: [Book!]!
    bookById(id: ID!): Book
    searchBooks(keyword: String!): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: String!
    publishedYear: Int!
    price: Float!
}
~~~

Reading the schema part by part:

| Declaration | Meaning |
|---|---|
| type Query | The root type containing read operations that clients can call. |
| books: [Book!]! | Returns a non-null list; each element in the list is also non-null. |
| bookById(id: ID!): Book | Requires passing `id`; the `Book` result can be null if not found. |
| searchBooks(keyword: String!): [Book!]! | Requires passing a keyword; the result is always a list, which may be empty. |
| ID! | Required identifier. `ID` is an identifier type; clients should not depend on whether it looks like a number or a string. |
| Float! | Floating-point number; this example uses `double` in Java. |

The exclamation mark indicates non-nullability. For example, `[Book!]!` means the list cannot be null and no element in the list can be null. Meanwhile, `Book` has no exclamation mark, so it can return null. This design fits a lookup-by-ID operation: a syntactically valid ID that does not exist in the data yields a `null` result.

The schema is the API contract. Field names, argument names, and data types in Java must be compatible with that contract. GraphQL only returns the fields requested by the client, so a request can fetch `id` and `title` without receiving all properties of `Book`.

## 4. Creating the Data Type and Service

Use a Java record to represent the book data:

~~~java
package com.example.bookcatalog.book;

public record Book(
        String id,
        String title,
        String author,
        int publishedYear,
        double price
) {
}
~~~

Create a service that provides sample data. In a real application, this service can call a repository or another storage system.

~~~java
package com.example.bookcatalog.book;

import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Locale;
import java.util.Optional;

@Service
public class BookService {

    private final List<Book> books = List.of(
            new Book("B-101", "Spring in Action", "Craig Walls", 2022, 39.90),
            new Book("B-102", "Effective Java", "Joshua Bloch", 2018, 45.00),
            new Book("B-103", "GraphQL in Action", "Samer Buna", 2021, 42.50)
    );

    public List<Book> findAll() {
        return books;
    }

    public Optional<Book> findById(String id) {
        return books.stream()
                .filter(book -> book.id().equals(id))
                .findFirst();
    }

    public List<Book> searchByKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return List.of();
        }

        String normalizedKeyword = keyword.trim().toLowerCase(Locale.ROOT);

        return books.stream()
                .filter(book ->
                        book.title().toLowerCase(Locale.ROOT).contains(normalizedKeyword)
                        || book.author().toLowerCase(Locale.ROOT).contains(normalizedKeyword))
                .toList();
    }
}
~~~

The service is responsible for looking up data. The GraphQL controller receives the request, forwards the arguments to the service, and returns the result. This separation keeps data access details out of the resolver while allowing the service to be reused across other flows.

## 5. Writing Resolvers with @QueryMapping

Create `BookQueryController`:

~~~java
package com.example.bookcatalog.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping(name = "searchBooks")
    public List<Book> search(@Argument("keyword") String keyword) {
        return bookService.searchByKeyword(keyword);
    }
}
~~~

Key components:

- `@Controller` registers the class as a Spring bean so Spring for GraphQL discovers the handler methods.
- `@QueryMapping` maps a method to a field on the root `Query` type.
- If no name is specified in `@QueryMapping`, Spring uses the method name as the GraphQL field name. Therefore, `books()` handles the `books` field and `bookById()` handles the `bookById` field.
- You can explicitly specify the field name with `@QueryMapping(name = "searchBooks")`. In the example, the Java method name is `search`, while the GraphQL field name is `searchBooks`.
- `@Argument("id")` binds the `id` argument in SDL to the Java `id` parameter. Specifying the argument name explicitly avoids relying on parameter name metadata at compile time.
- The method's return type is converted by the GraphQL runtime into the field's value. A `List<Book>` becomes a list of `Book`; a `Book` becomes a `Book` object.

Spring GraphQL also supports explicit mapping declarations with `@SchemaMapping(typeName = "Query", field = "books")`. `@QueryMapping` is a specialized shorthand for `Query` fields, making it better suited for root-level read resolvers.

Note that the GraphQL field name must exist in the schema. Having a `@QueryMapping` method does not automatically add a field to the SDL. When a resolver returns a `Book` object, the `id`, `title`, `author`, `publishedYear`, and `price` fields are read from the corresponding properties of the object.

## 6. Sending Queries and Reading Results

### Retrieving the Book List

Request:

~~~graphql
query {
    books {
        id
        title
        author
    }
}
~~~

The client only requests three fields, so the response only contains those three fields:

~~~json
{
  "data": {
    "books": [
      {
        "id": "B-101",
        "title": "Spring in Action",
        "author": "Craig Walls"
      },
      {
        "id": "B-102",
        "title": "Effective Java",
        "author": "Joshua Bloch"
      },
      {
        "id": "B-103",
        "title": "GraphQL in Action",
        "author": "Samer Buna"
      }
    ]
  }
}
~~~

### Finding a Book by ID Using Variables

Variables should be used when arguments change per request. Query:

~~~graphql
query BookDetail($id: ID!) {
    bookById(id: $id) {
        id
        title
        author
        publishedYear
        price
    }
}
~~~

Variable value:

~~~json
{
  "id": "B-101"
}
~~~

When calling over HTTP, the client sends a `POST` request to `/graphql` with a body containing `query` and `variables`:

~~~json
{
  "query": "query BookDetail($id: ID!) { bookById(id: $id) { id title author publishedYear price } }",
  "variables": {
    "id": "B-101"
  }
}
~~~

Response when the book is found:

~~~json
{
  "data": {
    "bookById": {
      "id": "B-101",
      "title": "Spring in Action",
      "author": "Craig Walls",
      "publishedYear": 2022,
      "price": 39.9
    }
  }
}
~~~

If the ID does not exist, the resolver returns `null` and the response looks like:

~~~json
{
  "data": {
    "bookById": null
  }
}
~~~

This is valid because the `bookById` field is declared as nullable `Book`. If you change the schema to `Book!`, returning `null` violates the non-null contract and GraphQL produces an execution error; the null value can propagate up to the nearest nullable parent field. Therefore, choose nullability based on the expected business behavior.

### Searching by Keyword

Query:

~~~graphql
query SearchBooks($keyword: String!) {
    searchBooks(keyword: $keyword) {
        id
        title
        author
    }
}
~~~

Variables:

~~~json
{
  "keyword": "java"
}
~~~

The result includes books whose title or author contains the keyword, case-insensitively. If there are no matches, the resolver returns an empty list. Since the schema declares `[Book!]!`, an empty list is a valid result.

## 7. Testing with GraphQlTester

You can test resolvers at the GraphQL layer using `@GraphQlTest`. If the project does not yet have test dependencies, add both `spring-boot-starter-test` and `spring-graphql-test` (with `test` scope):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~java
package com.example.bookcatalog.book;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookQueryController.class)
@Import(BookService.class)
class BookQueryControllerTest {

    @Autowired
    private GraphQlTester graphQlTester;

    @Test
    void shouldReturnBooks() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("books[0].id")
                .entity(String.class)
                .isEqualTo("B-101");
    }

    @Test
    void shouldFindBookById() {
        graphQlTester.document("""
                query BookDetail($id: ID!) {
                    bookById(id: $id) {
                        title
                    }
                }
                """)
                .variable("id", "B-102")
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Effective Java");
    }

    @Test
    void shouldReturnNullWhenBookDoesNotExist() {
        graphQlTester.document("""
                query BookDetail($id: ID!) {
                    bookById(id: $id) {
                        id
                    }
                }
                """)
                .variable("id", "UNKNOWN")
                .execute()
                .path("bookById")
                .valueIsNull();
    }
}
~~~

`@GraphQlTest` configures a test slice for GraphQL and the specified controller. `@Import` brings `BookService` into the context because the test needs the real service to supply sample data. `GraphQlTester` sends the document, passes variables, and asserts data at paths in the response.

The three tests verify different behaviors: the list can be queried, arguments are passed properly to the resolver, and the `bookById` field can return `null` when data is not found. When running tests in your project, make sure `schema.graphqls` is in the right location and field names in the document match the SDL.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| Field not found in Query | The field is not declared in SDL or the resolver name does not match. | Compare the name in `type Query` with the method name or the `name` attribute of `@QueryMapping`. |
| Resolver is not invoked | The class is missing `@Controller`, is outside component scan, or the method is missing `@QueryMapping`. | Check the application package and annotations on the controller. |
| Argument receives null | The argument name in `@Argument` does not match the argument name in SDL. | Use `@Argument("id")` and verify that the request passes `id`. |
| Data type error | The Java type is incompatible with the scalar or SDL structure. | Cross-check `String`/`ID`, `int`/`Int`, `double`/`Float`, and list types. |
| Non-null error when record not found | The resolver returns `null` while SDL declares the field as non-null. | Review nullability or the convention for handling not-found cases. |
| Schema not loaded | The file is in the wrong directory or schema locations configuration does not include the directory containing the file. | Check the location of `graphql/schema.graphqls` and Spring GraphQL configuration. |

When an error occurs, read both `data` and `errors` in the response. GraphQL can return partial data alongside a list of errors; HTTP status alone does not fully describe the execution result of a GraphQL operation.

## 9. Practice Exercises

Continue extending the book catalog API:

1. Add a `latestBooks` field to `Query` to return at most `N` latest books. Declare the `limit` argument in SDL, receive it with `@Argument`, and enforce input bounds in the service.
2. Add a `booksByYear(year: Int!)` field to filter by publication year. Write a dedicated service method and a resolver using `@QueryMapping`.
3. Write tests for the empty list case, existing book ID, and non-existent book ID.
4. Try changing the return type of `bookById` from `Book` to `Book!` and observe what happens when the resolver returns `null`. Then restore the schema according to your chosen business rule.

Completion criteria: the schema accurately describes the three read operations; each `Query` field has a corresponding resolver; arguments are bound properly; the response contains only fields requested by the client; and both found and not-found cases have tests.
