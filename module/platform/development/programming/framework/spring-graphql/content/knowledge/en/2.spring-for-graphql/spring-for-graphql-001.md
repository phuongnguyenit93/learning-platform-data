# What is Spring for GraphQL?

Spring for GraphQL is a project in the Spring ecosystem for building GraphQL servers with the Spring Framework. It connects the GraphQL Java execution engine with familiar Spring mechanisms such as dependency injection, bean management, application configuration, Spring Boot, Spring Security, and testing. As a result, Java applications can expose a GraphQL API without having to build the entire request-handling, schema-mapping, and business-invocation layer from scratch.

Spring for GraphQL is a good fit when an application needs to expose an API based on a data graph model: the client specifies the fields it wants to receive, while the server is responsible for validating the operation and resolving each field according to the schema. The library does not generate business logic on its own or automatically turn a database into a GraphQL API. Developers still define the API contract, write resolvers, and decide how data is accessed.

## What problem does GraphQL solve?

With REST, each endpoint typically represents a resource or an action. A screen that needs book, author, and review information might have to call multiple endpoints. If an endpoint returns too many fields, the client receives unnecessary data; if an endpoint returns too few, the client has to make additional requests.

GraphQL lets the client send a single operation describing the exact data structure it needs to receive. For example, a client can request book details along with the author's name in one request:

~~~graphql
query {
  book(id: "book-101") {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

The server returns data whose structure matches the selection set:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring in Action",
      "author": {
        "id": "author-12",
        "name": "Craig Walls"
      }
    }
  }
}
~~~

A GraphQL API is described by a strongly typed schema. The schema specifies which operations can be called, what types the fields have, which fields are required, and how data types relate to one another. The client can select fields within the scope of the schema, but cannot request arbitrary fields that the server has not exposed.

GraphQL is a query language and API execution model, not a database query language. A resolver can read data from a database, call another REST service, fetch data from a cache, or combine multiple sources. The GraphQL schema is the contract of the API; it does not necessarily match the table or entity structure in the storage layer.

## Where does Spring for GraphQL sit in the architecture?

Spring for GraphQL uses GraphQL Java as its execution engine. GraphQL Java handles core tasks such as parsing operations, validating operations against the schema, and executing fields. Spring for GraphQL adds integration for these tasks into a Spring application.

An application typically has the following components:

- **Schema SDL** describes the data types and fields exposed by the API.
- **GraphQlSource** provides the schema and runtime configuration for the GraphQL execution engine.
- **Controllers and resolvers** map schema fields to Java methods.
- **Services and repositories** execute business logic, access data, or call external systems.
- **Transport handlers** receive GraphQL requests over HTTP, WebSocket, or another configured transport.
- **GraphQL Java** executes the operation and produces results according to the schema.

High-level HTTP processing flow:

~~~mermaid
flowchart TD
    A["GraphQL client"] -->|"POST /graphql"| B["HTTP handler"]
    B --> C["ExecutionGraphQlService"]
    C --> D["GraphQL Java"]
    D --> E["Resolver in Spring Controller"]
    E --> F["Service"]
    F --> G["Repository / external system"]
    G --> F
    F --> E
    E --> D
    D --> H["GraphQL response: data and errors"]
    H --> A
~~~

Before receiving requests, Spring builds the GraphQL runtime from the schema and mapping configurations. When a request arrives, the transport layer passes the operation and variables to the execution service. GraphQL Java validates the operation, then invokes the resolvers corresponding to the fields that need to be resolved. A resolver may call a service; GraphQL Java assembles the results into the structure requested by the client.

In a Spring Boot application, most of the foundational configuration is set up automatically when the appropriate dependencies are present. Developers still need to provide the schema, resolvers, and additional configuration for specific requirements such as security, transport, or error handling.

## Schema SDL as the contract of a GraphQL API

Spring for GraphQL typically uses a schema-first approach: declaring the schema using the GraphQL Schema Definition Language (SDL), then mapping schema fields to Java code. A small schema for a book domain might look like this:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Subscription {
  bookCreated: Book!
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

input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

The three common root types serve different roles:

| Root type | Purpose | Example |
| --- | --- | --- |
| **Query** | Read data without representing write operations | Fetch a single book or a list of books |
| **Mutation** | Perform changes to data or state | Create, update, or delete a book |
| **Subscription** | Receive events emitted over time | Receive notifications when a new book is added |

Several notations in SDL need to be understood accurately:

- **ID** is a scalar commonly used for identifiers. In Java, this value is usually mapped to **String**.
- The **!** mark indicates a non-null value. **ID!** means an ID is required.
- **[Book!]!** means the list cannot be null and each element in the list also cannot be null.
- **input** declares an input data structure. An input object is used to group related arguments of a mutation or field.
- **type** declares an output data type that clients can query.

The schema is the public boundary of the API. A property that exists in a Java object does not automatically become a public field unless the schema declares it. Conversely, every field in the schema needs an appropriate resolution mechanism, either default property access or a resolver provided by the application.

## Spring Boot integration

With Gradle and Spring Boot, basic dependencies can be declared as follows:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Spring Boot manages compatible library versions when the project uses Boot's dependency management. **spring-boot-starter-graphql** brings Spring for GraphQL into the application. **spring-boot-starter-web** provides the Spring MVC foundation for serving GraphQL over HTTP. If the application uses the reactive stack, you can choose **spring-boot-starter-webflux** instead of the MVC starter.

Place schema files in the resources directory, for example:

~~~text
src/main/resources/
└── graphql/
    └── schema.graphqls
~~~

Spring Boot automatically discovers schemas in the default GraphQL directory and configures the HTTP endpoint at **/graphql**. You can change the path using the **spring.graphql.path** property. Having the GraphQL starter does not mean the application already has a business API: the schema and corresponding resolvers still have to be written.

## Mapping schema to Java with annotations

Spring for GraphQL provides annotations to declare methods that handle fields. These methods typically reside in beans annotated with **@Controller**.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return bookService.findAuthor(book.authorId());
    }
}
~~~

In this example:

- **@QueryMapping** maps a method to a field on the **Query** root type. The method name is used as the field name by default unless configured otherwise.
- **@MutationMapping** maps a method to a field on the **Mutation** root type.
- **@SchemaMapping** maps a specific field of a data type. The source parameter **Book book** represents the parent object currently being resolved by GraphQL.
- **@Argument** extracts an argument value from the GraphQL operation and converts it to the corresponding Java type.

An input type example can be represented as a Java record:

~~~java
public record CreateBookInput(String title, String authorId) {
}
~~~

When the client invokes the **createBook** field, Spring converts the input object according to the schema into **CreateBookInput**, then passes it to the controller method. The controller calls the service to execute the business logic. This structure keeps resolvers focused on connecting the schema to the application, while business rules stay in the service.

**@SchemaMapping** can also be written more concisely when the field name and source type can be inferred from the method name and parameter. When the schema has many types or the method name does not match the field, explicitly specifying **typeName** and **field** makes the mapping easier to read.

## Query, Mutation, and Subscription in an application

**Query** is used for reading data. Clients can send multiple fields in a single operation and select nested fields. Query resolvers should focus on returning data and avoid causing unintended state changes.

**Mutation** is used for operations that modify data. Mutations often take an input object to avoid long argument lists and make the schema easier to evolve. Input validation, authorization, and business rules remain the responsibility of the application.

**Subscription** is used to receive data when new events occur. In Spring for GraphQL, a method annotated with **@SubscriptionMapping** can return a reactive publisher, such as **Flux<Book>**. For clients to receive the event stream, the application must configure a transport that supports subscriptions, such as WebSocket or RSocket. Merely declaring the **Subscription** root type in SDL is not enough to create a working event channel.

An example operation with variables separates input data from the query string:

~~~graphql
query GetBook($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

An HTTP request can send the operation and variables as JSON:

~~~json
{
  "operationName": "GetBook",
  "query": "query GetBook($id: ID!) { book(id: $id) { id title author { name } } }",
  "variables": {
    "id": "book-101"
  }
}
~~~

A GraphQL response normally contains **data**; if errors occur during processing, the response may also contain **errors**. Some fields may still return data successfully while another field errors out, depending on where the error occurred and the schema's nullability rules. Therefore, clients should inspect both **data** and **errors**, rather than relying solely on the HTTP status code to conclude an operation succeeded completely.

## Resolving data relationships and the N+1 problem

GraphQL allows clients to query nested fields, so a query fetching a list of books and their authors can cause the server to resolve the **author** field many times. If each resolver queries the database individually, a single request can trigger one query for the list of books plus N queries for the authors. This is the N+1 problem.

Spring for GraphQL provides **@BatchMapping** to batch the resolution of the same field across multiple source objects. For example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> authors(List<Book> books) {
    return authorService.findAuthorsFor(books);
}
~~~

Instead of calling the service once per book, the method receives a group of **Book** objects and returns the corresponding result for each object. This approach works well when the service or repository can load data in batches.

Another option is DataLoader. DataLoader batches key lookup requests within the same execution into a single batch load and can cache results within the request scope. Spring for GraphQL supports registering batch loaders and injecting DataLoader into resolver parameters. Choosing between **@BatchMapping** and DataLoader depends on how data access is organized; both require an actual batch query at the service/repository layer to reduce the number of calls to the data source.

Beyond N+1, the API should consider pagination for large lists, limiting operation depth or complexity, timeouts, and resource limits. Because clients can choose fields freely, a schema-valid query can still consume excessive resources if it queries too deeply or requests a huge amount of data.

## Error handling, validation, and security

GraphQL distinguishes between syntax errors, schema validation errors, and errors during resolver execution. Spring for GraphQL lets you customize how exceptions from resolvers are translated into GraphQL errors through mechanisms such as **DataFetcherExceptionResolver**. Applications should return information helpful enough for the client without exposing stack traces, SQL statements, credentials, or internal details.

Input from the client must be validated before executing business logic. You can combine input types in SDL with Java-layer validation, such as Jakarta Bean Validation, and convert validation failures into appropriate GraphQL errors. The schema checks types and nullability, but does not replace business rules such as quantity limits, valid states, or data ownership.

For security, you need to control both requests to the endpoint and access permissions for individual fields or records. Spring Security can protect the HTTP endpoint and apply method security on resolver methods, for example with **@PreAuthorize**. With deeply nested queries, authenticating the user at the endpoint alone is not enough: resolvers still have to verify whether the user has permission to view the requested object or field. Multi-tenant queries must also enforce tenant conditions at the data access layer.

## Testing a GraphQL API

Spring for GraphQL provides **GraphQlTester** to test operations without forcing tests to handle raw JSON request and response details. Depending on the test type, you can use a tester directly against the execution service or a tester bound to the HTTP transport.

Example of testing a query:

~~~java
graphQlTester.document("""
        query GetBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
~~~

Tests should verify happy-path results, not-found cases, invalid input, unauthorized users, and errors from data sources. For mutations, verify that the business state change actually occurs. For subscriptions, verify the event stream and the configured transport.

## When should you use Spring for GraphQL?

Spring for GraphQL is well suited when an application needs a flexible data contract for multiple types of clients, when data comes from multiple domains or services, or when clients need to combine related data in a single operation. It is especially useful when the frontend frequently changes how data is displayed and needs to select the exact set of fields for each screen.

GraphQL does not have to replace all REST APIs. A system can use REST for resource endpoints or actions where it fits well, while using GraphQL for screens that need to aggregate multiple data sources. The decision should be based on client needs, schema complexity, caching requirements, security, and operability.

In production deployments, monitor execution time by operation and resolver, the number of calls to databases or external services, response sizes, and error rates. These metrics help identify slow resolvers, N+1 queries, overly expensive queries, and bottlenecks across branches of the graph.

Spring for GraphQL provides the integration layer to build GraphQL servers naturally in a Spring application: the schema describes the contract, annotations map fields to Java, services handle business logic, and GraphQL Java executes operations. Understanding the boundaries between these parts helps you design APIs that are easy to test, enforce access control, and optimize when data has many relationships.
