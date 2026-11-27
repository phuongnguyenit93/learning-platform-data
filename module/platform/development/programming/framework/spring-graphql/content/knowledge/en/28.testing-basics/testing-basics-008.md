# JSONPath Response

When testing a GraphQL API, verifying that a request does not throw an exception is not enough. Tests must inspect the data returned by the server: whether a field has the expected value, whether nested objects have the right structure, whether a list has the expected elements, and which field becomes null when a resolver fails.

Spring for GraphQL provides **GraphQlTester** with the **path(...)** API to read responses using **JSONPath**. JSONPath lets you select a single value, a nested property, or multiple elements in an array. After selecting a path, tests can convert data into Java types to assert using **entity(...)**, **entityList(...)**, or direct JSON comparison.

This lesson focuses on using JSONPath with GraphQlTester: path syntax relative to data, accessing nested objects and lists, wildcards and filters, aliases, verifying null values or missing paths, converting into Java objects, comparing JSON, handling GraphQL errors, and testing partial data.

## 1. What Is a JSONPath Response?

A GraphQL response typically has this JSON structure:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "Spring for GraphQL",
      "author": {
        "name": "An Nguyen"
      }
    }
  }
}
~~~

In tests, you may need to read the book's title, the author's name, a list of titles across multiple books, the first element or an element matching a condition, and whether a field is null.

JSONPath is an expression syntax for accessing locations in JSON. With GraphQlTester, the **path(String)** method accepts a JSONPath expression and returns an API to assert the value at that location.

Example:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                id
                title
            }
        }
        """)
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

The path book.title selects the title field inside the book object in the data section of the response.

## 2. Preparing GraphQlTester

Add the Spring for GraphQL testing dependency:

~~~gradle
testImplementation("org.springframework.graphql:spring-graphql-test")
~~~

When using Spring Boot dependency management, let the Spring Boot BOM manage compatible versions instead of manually picking a spring-graphql-test version different from spring-graphql.

**GraphQlTester** is the common abstraction for sending requests and verifying responses. Request APIs and JSONPath assertions are identical across transports; how the tester is created depends on where the test executes.

Commonly used implementations:

| Tester | Scope |
|---|---|
| ExecutionGraphQlServiceTester | Calls ExecutionGraphQlService directly, no HTTP needed |
| WebGraphQlTester | Calls through WebGraphQlHandler and the WebGraphQlInterceptor chain |
| HttpGraphQlTester | Sends requests over HTTP using WebTestClient |
| WebSocketGraphQlTester | Sends requests over WebSocket |
| RSocketGraphQlTester | Sends requests over RSocket |

Example creating a server-side tester without going through a transport:

~~~java
GraphQlTester graphQlTester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);
~~~

Example creating a tester over HTTP targeting a running server:

~~~java
WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

If you need to test HTTP headers, authentication, CORS, or interceptors, use a tester at the appropriate transport layer. If you only need to test GraphQL execution and returned data, ExecutionGraphQlServiceTester is usually simpler.

## 3. Paths in GraphQlTester Are Relative to data

This is the most important rule when writing JSONPath responses:

**GraphQlTester.path(...) starts from the data section of the GraphQL response.**

Given this response:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "Spring for GraphQL"
    }
  }
}
~~~

Correct path:

~~~java
.path("book.title")
~~~

Do not add the data prefix:

~~~java
// Do not use data.book.title
// No need to start with $.data.book.title
~~~

A path can be a root operation field name, such as book, or a JSONPath expression like books[*].title.

This differs from parsing the entire JSON response manually with a general JSONPath library, where expressions usually start from the root JSON document.

## 4. Accessing Nested Objects

Suppose the schema is:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  name: String!
  email: String
}
~~~

Client query:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    author {
      name
      email
    }
  }
}
~~~

You can assert each nested field individually:

~~~java
graphQlTester.document(document)
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-01")
    .path("book.author.name")
    .entity(String.class)
    .isEqualTo("An Nguyen");
~~~

When asserting multiple fields under the same object, use the path overload with a callback:

~~~java
graphQlTester.document(document)
    .execute()
    .path("book", book -> {
        book.path("id")
                .entity(String.class)
                .isEqualTo("book-01");

        book.path("title")
                .entity(String.class)
                .isEqualTo("Spring for GraphQL");

        book.path("author.name")
                .entity(String.class)
                .isEqualTo("An Nguyen");
    });
~~~

Inside the callback, subsequent paths are evaluated relative to the book object. This helps group assertions for one part of the response and avoids repeating prefixes.

## 5. Accessing Elements in an Array

Suppose a query returns multiple books:

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

Illustrative response:

~~~json
{
  "data": {
    "books": [
      {
        "id": "book-01",
        "title": "Spring for GraphQL",
        "author": {
          "name": "An Nguyen"
        }
      },
      {
        "id": "book-02",
        "title": "GraphQL in Practice",
        "author": {
          "name": "Binh Tran"
        }
      }
    ]
  }
}
~~~

JSONPath supports access by index:

~~~java
.path("books[0].title")
.entity(String.class)
.isEqualTo("Spring for GraphQL");
~~~

Indexing starts at 0. You can read the next element with books[1].title.

Index access is appropriate when ordering is part of the contract under test. If the API does not guarantee order, check the set of values or per-element conditions instead of relying on indices.

## 6. Using Wildcards to Extract Multiple Values

The wildcard **[*]** selects all elements in an array at that position.

Example extracting the title of every book:

~~~java
graphQlTester.document("""
        query {
            books {
                title
            }
        }
        """)
    .execute()
    .path("books[*].title")
    .entityList(String.class)
    .contains(
            "Spring for GraphQL",
            "GraphQL in Practice");
~~~

The path books[*].title returns a collection of title values from the elements in books.

You can check the element count:

~~~java
.path("books[*].title")
.entityList(String.class)
.hasSize(2);
~~~

Or check the exact order and full contents:

~~~java
.path("books[*].title")
.entityList(String.class)
.containsExactly(
        "Spring for GraphQL",
        "GraphQL in Practice");
~~~

Common assertions on EntityList:

| Method | Meaning |
|---|---|
| hasSize(n) | List has exactly n elements |
| hasSizeGreaterThan(n) | Has more than n elements |
| hasSizeLessThan(n) | Has fewer than n elements |
| contains(...) | Contains the values, regardless of order |
| containsExactly(...) | Has the exact values in the exact order |
| doesNotContain(...) | Does not contain the specified values |
| singleElement() | Verifies the list has exactly one element and returns an assertion for that element |

## 7. Using Filter Expressions in JSONPath

JSONPath supports filters to select elements matching a condition.

For example, a query returning books with pageCount and title:

~~~graphql
query {
  books {
    id
    title
    pageCount
  }
}
~~~

You can select books with more than 300 pages:

~~~java
graphQlTester.document(document)
    .execute()
    .path("books[?(@.pageCount > 300)].title")
    .entityList(String.class)
    .contains("GraphQL in Practice");
~~~

In the filter:

- ? begins the conditional expression.
- @ represents the current element.
- pageCount is a property of the element.
- > 300 is the filter condition.

Example checking published books:

~~~java
.path("books[?(@.published == true)].id")
.entityList(String.class)
.hasSizeGreaterThan(0);
~~~

Filters can only use fields that actually appear in the GraphQL response. If the document does not select pageCount or published, JSONPath cannot filter by those fields.

Avoid overly complex filter expressions for every assertion. When filter logic becomes hard to read, decode the list into Java objects and use AssertJ assertions.

## 8. JSONPath with GraphQL Aliases

GraphQL allows clients to alias fields:

~~~graphql
query {
  featuredBook: book(id: "book-01") {
    id
    title
  }
}
~~~

The response uses the alias as the key:

~~~json
{
  "data": {
    "featuredBook": {
      "id": "book-01",
      "title": "Spring for GraphQL"
    }
  }
}
~~~

Because JSONPath reads the actual response, tests must use the alias:

~~~java
.path("featuredBook.title")
.entity(String.class)
.isEqualTo("Spring for GraphQL");
~~~

Do not use the schema field name book in the path if the response key was replaced by featuredBook.

## 9. Converting a Path into a Java Object

When an object has many fields or nested structure, you can convert a path into a Java type.

DTO:

~~~java
public record BookView(
        String id,
        String title,
        AuthorView author) {
}

public record AuthorView(
        String name,
        String email) {
}
~~~

Test:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                id
                title
                author {
                    name
                    email
                }
            }
        }
        """)
    .execute()
    .path("book")
    .entity(BookView.class)
    .satisfies(book -> {
        assertThat(book.id()).isEqualTo("book-01");
        assertThat(book.title()).isEqualTo("Spring for GraphQL");
        assertThat(book.author().name()).isEqualTo("An Nguyen");
    });
~~~

Ways to assert on Entity:

- isEqualTo(expected): compares the object with an expected value.
- isNotEqualTo(other): verifies the object differs from the specified value.
- matches(predicate): checks the object using a predicate.
- satisfies(consumer): runs multiple assertions on the object.
- get(): retrieves the decoded object for use in other assertions.

Converting to a DTO is appropriate when a test needs to verify multiple properties together. If you only need a single scalar, using entity(String.class), entity(Integer.class), or the matching type is simpler.

## 10. Verifying Generic Data Types

If the response path is an object with a generic type, use **ParameterizedTypeReference** to preserve type information during decoding.

Example:

~~~java
ParameterizedTypeReference<Map<String, Object>> mapType =
        new ParameterizedTypeReference<>() {};

graphQlTester.document(document)
    .execute()
    .path("book.metadata")
    .entity(mapType)
    .satisfies(metadata ->
            assertThat(metadata).containsKey("language"));
~~~

For lists of generic types, GraphQlTester also provides an entityList(ParameterizedTypeReference) overload. Choosing explicit Java types avoids manual casts and ClassCastException errors.

## 11. Comparing JSON at a Path

When you need to verify the JSON structure of an object, you can use **matchesJson(...)**:

~~~java
graphQlTester.document(document)
    .execute()
    .path("book")
    .matchesJson("""
            {
              "id": "book-01",
              "title": "Spring for GraphQL"
            }
            """);
~~~

This method compares the JSON at the path with the expected JSON. The comparison ignores line breaks and whitespace differences in JSON.

To use matchesJson, the JSONassert library must be on the test classpath. Check your project's test dependencies if you encounter a missing JSONassert error.

JSON comparison is useful when checking part of a response structure. If you only need to check a few fields, path(...).entity(...) usually keeps tests easier to read and less coupled to the entire object shape.

## 12. Distinguishing Null from a Nonexistent Path

A GraphQL response can have a selected field whose value is null:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "author": null
    }
  }
}
~~~

Test:

~~~java
.path("book.author")
.valueIsNull();
~~~

Meanwhile, if the query did not select the author field, the response may lack the author key:

~~~json
{
  "data": {
    "book": {
      "id": "book-01"
    }
  }
}
~~~

Test:

~~~java
.path("book.author")
.pathDoesNotExist();
~~~

These two cases have different meanings:

| Assertion | Meaning |
|---|---|
| valueIsNull() | Path exists, but its value is null |
| pathDoesNotExist() | Corresponding path/key does not exist in the response |
| hasValue() | Path has a non-null value; for lists, the list must be non-empty |

Do not use pathDoesNotExist to check that a resolver returned null. If the field was selected and the resolver returned null, use valueIsNull.

## 13. Checking Responses with Partial Data and GraphQL Errors

GraphQL allows a response to contain both data and errors. For example, the author field fails while title still resolves:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Unable to load author",
      "path": ["book", "author"]
    }
  ]
}
~~~

When a response contains errors, GraphQlTester requires the test to inspect or filter errors before moving to a data path. Otherwise, calling path(...) may fail to warn the test that errors remain unhandled.

Example verifying an expected error and partial data:

~~~java
graphQlTester.document(document)
    .execute()
    .errors()
    .expect(error ->
            error.getMessage().contains("Unable to load author"))
    .verify()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

After verifying the expected error, the test can still inspect the remaining fields in data.

### filter and expect Differ

**filter(...)** marks a category of errors as ignorable. Filtering does not require that error to appear.

~~~java
.errors()
.filter(error -> error.getMessage().contains("expected warning"))
.verify()
~~~

**expect(...)** declares an error that must be present. If no error matches the predicate, the assertion fails.

~~~java
.errors()
.expect(error -> error.getMessage().contains("Unable to load author"))
.verify()
~~~

Filter only errors that are explicitly expected. If you filter all errors, tests may hide newly introduced bugs.

### Using satisfy to Check All Errors

You can inspect the error list directly:

~~~java
.errors()
.satisfy(errors ->
        assertThat(errors)
                .anyMatch(error ->
                        error.getMessage().contains("Unable to load author")));
~~~

Note: satisfy marks errors as inspected and allows continuing to read data. Therefore, inside the callback, thoroughly verify all errors the test cares about.

## 14. Testing Mutations Without Response Data

Some mutations return a scalar or payload that does not need complex JSONPath assertions. If the goal is simply to confirm the request has no GraphQL errors, use **executeAndVerify()**:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-01")
        }
        """)
    .executeAndVerify();
~~~

executeAndVerify executes the request and confirms the response contains no errors. If you need to check the returned value, use execute() and navigate to the corresponding path.

Example:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-01")
        }
        """)
    .execute()
    .path("archiveBook")
    .entity(Boolean.class)
    .isEqualTo(true);
~~~

## 15. JSONPath Does Not Replace the GraphQL Selection Set

JSONPath can only read what appears in the response.

Example GraphQL document:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Tests can read books[*].title, but cannot read books[*].author.name if the query did not select author and name.

When a path does not exist, check in this order:

1. Did the GraphQL document select the field being read?
2. Is an alias changing the key in the response?
3. Is the field inside the parent object as defined by the schema?
4. Did the resolver return null, or is the key genuinely absent from the response?
5. Did GraphQL errors or null propagation turn the parent object into null?

JSONPath does not access the schema directly and does not execute fields itself. It only queries the received JSON response.

## 16. Choosing the Right Assertion

Not every test needs a complex JSONPath expression. Choose the assertion style based on your goal:

| Goal | Usage |
|---|---|
| Verify a scalar | path(...).entity(Type.class) |
| Verify an object | path(...).entity(Dto.class) |
| Verify a list | path(...).entityList(Type.class) |
| Verify a nested field | path(parent.child) |
| Verify multiple fields on the same object | path(parent, callback) |
| Verify all list elements | path(items[*].field) |
| Filter elements by condition | JSONPath filter expression |
| Verify null | valueIsNull() |
| Verify missing key | pathDoesNotExist() |
| Verify JSON shape | matchesJson(...) |
| Verify partial data with expected errors | errors().expect(...).verify() then path(...) |

Prefer assertions that clearly express the API contract. If list order is not guaranteed, use contains or predicate checks instead of containsExactly.

## 17. Common Errors When Using JSONPath Responses

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Path cannot find field | Wrong data prefix added or misspelled field name | Remember paths start from data |
| Path uses schema name absent in response | GraphQL field has an alias | Use the alias as the key in JSONPath |
| Cannot read nested field | Query did not select the nested field | Add the field to the selection set |
| path(...) fails even though data has a value | Response contains unhandled errors | Use errors().verify(), expect, or satisfy first |
| valueIsNull fails | Path does not exist instead of being null | Use pathDoesNotExist when the key is missing |
| entityList fails to decode | Path does not return an array or type mismatches | Check JSON shape and Java type |
| Filter returns an empty list | Filtered field was not selected or predicate is wrong | Check selection set and expression |
| Test depends on unstable ordering | Resolver/repository does not guarantee ordering | Assert set of values or sort intentionally |
| matchesJson reports missing library | JSONassert is not on the test classpath | Add the appropriate JSONassert dependency |
| Test ignores unexpected errors | Error filter is too broad | Filter only specific accepted errors |
| Mutation test without data is verbose | Used execute without asserting a path | Use executeAndVerify when only verifying zero errors |

## 18. Workflow for Writing JSONPath Response Assertions

When testing a GraphQL response:

1. Identify the fields and JSON structure returned by the GraphQL operation.
2. Write a document whose selection set includes the exact fields to verify.
3. Send the request via GraphQlTester and call execute().
4. Verify or handle errors before navigating to a data path.
5. Write JSONPath relative to data, without adding the data prefix.
6. Use indices when ordering is part of the contract; use wildcards or filters when selecting multiple elements.
7. Convert paths into scalars, DTOs, or lists using entity/entityList.
8. Check null and missing paths using the corresponding assertions.
9. Verify partial data when an operation has expected errors.
10. Use matchesJson when comparing JSON structures and JSONassert is available.
11. Keep assertions focused on the API contract, avoiding unstable details.
12. Run tests at the right layer: execution, WebGraphQlHandler, or HTTP transport depending on what needs verification.

JSONPath responses let you verify returned GraphQL data precisely using concise expressions. With GraphQlTester, every path starts from the data section; nested objects, arrays, wildcards, filters, and aliases can all be inspected through path(...). After selecting a path, use entity or entityList to decode into Java types, or matchesJson to compare JSON. When responses contain errors, verify them before reading data, and distinguish null fields from nonexistent paths. These practices keep tests faithful to the GraphQL API contract and catch bugs in both data and response structure.

## References

- Spring for GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- GraphQlTester API — Traversable and Path: https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Traversable.html
- Jayway JsonPath: https://github.com/json-path/JsonPath
- JSONassert: https://jsonassert.skyscreamer.org/
