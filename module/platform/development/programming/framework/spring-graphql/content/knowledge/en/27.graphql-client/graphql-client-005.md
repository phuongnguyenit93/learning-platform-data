# Client document

## Objectives

After this lesson, you will be able to:

- Explain what a GraphQL document is and its role in a client request.
- Create a request using GraphQlClient.document(String).
- Distinguish document text from operation name.
- Pass variables using variable() and variables().
- Select an operation when a document contains multiple operations.
- Reuse fragments inside a document.
- Store GraphQL documents as files and load them using documentName().
- Choose retrieve() or execute() after declaring a document.
- Avoid errors when constructing documents and testing client requests.

## What is a GraphQL document?

A GraphQL document is the GraphQL content that a client sends to the server to describe the operation to execute. A document can contain one or more operations such as query, mutation, subscription, and any fragments used by those operations.

Example of a query document:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}
~~~

This document contains:

- Operation name: BookById.
- Operation type: query.
- Variable declaration: $id of type ID!.
- Selection set: requests the fields bookById.id and bookById.title.

The document describes the data the client wants to fetch. The server uses the schema to parse, validate, and execute the operation. The client does not need to know which Java resolver will handle a field; it only needs to send a document valid against the schema.

In Spring for GraphQL, GraphQlClient provides a common workflow for sending requests across multiple transports. The client starts creating a request with document(String) or documentName(String), then adds variables and an operation name, and chooses how to read the response. The basic way of building a request is the same across HTTP, WebSocket, and RSocket. [Spring for GraphQL Documentation – Client](https://docs.spring.io/spring-graphql/reference/client.html)

## Initializing GraphQlClient

GraphQlClient is a common abstraction. Applications choose an implementation by transport:

| Client | Transport | Characteristics |
| --- | --- | --- |
| HttpGraphQlClient | HTTP via WebClient | Non-blocking, commonly used in reactive applications or services |
| HttpSyncGraphQlClient | HTTP via RestClient | Blocking, suitable for synchronous flows |
| WebSocketGraphQlClient | WebSocket | Shared connection, supports subscription streams |
| RSocketGraphQlClient | RSocket | Request/response and streaming over RSocket |

Example creating an HTTP client:

~~~java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

After creating the client, you can use document() to start a request. The rest of this lesson focuses on documents; configuring authentication, headers, and interceptors belongs to client/transport configuration.

## Creating a request with document(String)

The document(String) method takes a GraphQL document as a String and returns a RequestSpec for further configuration:

~~~java
String document = """
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """;

Mono<Book> book = graphQlClient.document(document)
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

In this example:

1. document(document) supplies the operation content.
2. variable("id", "book-101") assigns a value to the $id variable.
3. retrieve("bookById") selects the field in the data section of the response.
4. toEntity(Book.class) converts the field value into a Java object.

HttpGraphQlClient returns results via a reactive API, so retrieve() creates a publisher such as Mono<Book>. The request is executed only when the publisher is subscribed to by the runtime or tested with Reactor Test. Do not call block() inside a WebFlux pipeline just to obtain a synchronous result.

With a blocking HTTP client, you can use HttpSyncGraphQlClient and retrieveSync():

~~~java
import org.springframework.graphql.client.HttpSyncGraphQlClient;
import org.springframework.web.client.RestClient;

HttpSyncGraphQlClient syncClient =
        HttpSyncGraphQlClient.create(
                RestClient.create("https://api.example.com/graphql"));

Book book = syncClient.document(document)
        .variable("id", "book-101")
        .retrieveSync("bookById")
        .toEntity(Book.class);
~~~

Choose blocking or non-blocking based on your application architecture and transport in use. The syntax for declaring documents and variables remains similar.

## Distinguishing document from operation name

A document is the entire GraphQL content being sent. An operation name is the name of a specific operation located inside the document.

Example of a document containing two queries:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}

query RecentBooks($first: Int!) {
  recentBooks(first: $first) {
    id
    title
  }
}
~~~

The document has two operations. The GraphQL server needs to know which operation is selected for execution. The client uses operationName():

~~~java
Mono<Book> book = graphQlClient.document(document)
        .operationName("BookById")
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

The operation name must match the exact name declared in the document. If a document has only one operation, the client usually does not need to set operationName. If a document contains multiple operations, the request must explicitly specify which operation to execute.

Do not confuse them:

| Component | Example | Meaning |
| --- | --- | --- |
| Document | The entire GraphQL snippet | Request content |
| Operation name | BookById | Selects an operation inside the document |
| Field path | bookById | Location of data to read inside response.data |
| Variable name | id | Variable name declared in the operation |

retrieve("bookById") does not select an operation named BookById. It selects the bookById field path inside the response data. Selecting an operation and selecting a field path are two independent steps.

## Passing variables to a document

Do not concatenate input values directly into a GraphQL string. Declare variables in the document and assign values using variable() or variables().

Example document:

~~~graphql
query SearchBooks($keyword: String!, $first: Int!) {
  searchBooks(keyword: $keyword, first: $first) {
    id
    title
  }
}
~~~

Assigning individual variables:

~~~java
Mono<List<Book>> books = graphQlClient
        .document(searchBooksDocument)
        .variable("keyword", "Spring")
        .variable("first", 10)
        .retrieve("searchBooks")
        .toEntityList(Book.class);
~~~

Or passing multiple variables with a Map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 10);

Mono<List<Book>> books = graphQlClient
        .document(searchBooksDocument)
        .variables(variables)
        .retrieve("searchBooks")
        .toEntityList(Book.class);
~~~

Key names in the Map must match the variable names in the document without the leading $ character. Values must be compatible with the declared GraphQL types, such as String for String!, integer for Int!, and input object for input types.

### Passing input objects

GraphQL variables can hold objects corresponding to input types:

~~~graphql
input BookFilter {
  keyword: String
  category: String
  publishedAfter: String
}

query FilterBooks($filter: BookFilter!, $first: Int!) {
  books(filter: $filter, first: $first) {
    id
    title
  }
}
~~~

Java can use a Map:

~~~java
Map<String, Object> filter = Map.of(
        "keyword", "GraphQL",
        "category", "TECHNOLOGY");

Map<String, Object> variables = Map.of(
        "filter", filter,
        "first", 20);

Mono<List<Book>> books = graphQlClient
        .document(filterBooksDocument)
        .variables(variables)
        .retrieve("books")
        .toEntityList(Book.class);
~~~

Or use a DTO/record:

~~~java
public record BookFilter(
        String keyword,
        String category,
        String publishedAfter) {
}

public record FilterBooksVariables(
        BookFilter filter,
        int first) {
}
~~~

~~~java
FilterBooksVariables requestVariables =
        new FilterBooksVariables(
                new BookFilter("GraphQL", "TECHNOLOGY", null),
                20);

Mono<List<Book>> books = graphQlClient
        .document(filterBooksDocument)
        .variable("filter", requestVariables.filter())
        .variable("first", requestVariables.first())
        .retrieve("books")
        .toEntityList(Book.class);
~~~

Serializing DTOs into variables depends on the transport's JSON codec. With a WebClient-based HTTP client, Spring uses the codec configured on the WebClient. Check your codec and how null/omitted values are handled if the application uses input objects for partial updates.

### Do not interpolate inputs into the document

Do not build queries via string concatenation:

~~~java
// Not recommended: input can break syntax and create injection risks.
String document = "query { bookById(id: \"" + id + "\") { title } }";
~~~

Use variables instead:

~~~java
String document = """
        query BookById($id: ID!) {
            bookById(id: $id) {
                title
            }
        }
        """;

Mono<Book> book = graphQlClient.document(document)
        .variable("id", id)
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

GraphQL variables separate operation text from input data. This keeps documents stable, easy to validate, reusable, and avoids escaping issues when values contain quotes or special characters.

## Using fragments to reuse selection sets

Fragments allow defining a group of fields and reusing it across multiple operations or multiple places within the same document.

~~~graphql
fragment BookSummary on Book {
  id
  title
  publishedAt
}

query BookById($id: ID!) {
  bookById(id: $id) {
    ...BookSummary
    author {
      id
      name
    }
  }
}
~~~

Fragments keep selection sets consistent across requests. If a field needs to be added to BookSummary, operations using that fragment pick up the change.

When using fragments:

- Each fragment must have a unique name within the document.
- The type condition after on must match a valid object/interface/union in the schema.
- The operation must reference the fragment with the spread ...BookSummary.
- If a fragment references another fragment, the document must contain the related definitions.

Do not create an overly large fragment just to reuse every field. Clients should select only the data needed for the use case; a fragment should represent a meaningful selection set.

## Storing documents in files and using documentName()

For long queries or queries used in multiple places, you can store documents in .graphql or .gql files instead of embedding strings in Java.

Under Spring for GraphQL's default configuration, document files can be placed under graphql-documents/ on the classpath:

~~~text
src/
  main/
    resources/
      graphql-documents/
        bookById.graphql
        searchBooks.graphql
~~~

Contents of bookById.graphql:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

The client loads the document by name:

~~~java
Mono<Book> book = graphQlClient
        .documentName("bookById")
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

documentName("bookById") instructs DocumentSource to find the corresponding file, such as bookById.graphql. The name passed in is the document key, not the operation name. The operation inside the file might be named BookById; these two names do not have to be identical.

DocumentSource is the mechanism for loading documents by name. GraphQlClient's builder allows customizing DocumentSource if the application's directory structure or document storage differs from the default. When a document fails to load, the request has not yet been sent to the server; check the classpath, filename, and source configuration.

### When to use document(String) vs. documentName()?

| Usage | Best suited when |
| --- | --- |
| document(String) | Short operations, dynamically generated in code, or kept in constants |
| documentName(String) | Long operations, needing file storage, independent review, or reuse |
| Code-generated request | Projects using DGS Codegen or client API generators |

.graphql files are typically easier to review in pull requests and can benefit from IDE syntax highlighting, completion, or schema validation. Name files after the use case, such as bookById.graphql, createBook.graphql, or searchBooks.graphql.

Do not use documentName as a substitute for operationName. Document name locates the file; operation name selects an operation inside the file's content.

## Combining documents with retrieve() and execute()

After creating a RequestSpec with document() or documentName(), the client chooses how to process the response.

### retrieve() reads a single field path

retrieve(path) is a shortcut to read a field from the data section:

~~~java
Mono<Book> book = graphQlClient.documentName("bookById")
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

Path is relative to data. For nested fields, use dots:

~~~java
Mono<String> authorName = graphQlClient.documentName("bookById")
        .variable("id", "book-101")
        .retrieve("bookById.author.name")
        .toEntity(String.class);
~~~

For lists, paths support indices such as books[0].title. Only use paths matching the actual selection set in the document.

If the field does not exist or has a null value accompanied by a GraphQL error, retrieve may raise FieldAccessException. The exception provides the response and field so the application can inspect errors or choose a fallback. If the field exists but cannot be decoded into the requested Java type, the client may raise GraphQlClientException.

### execute() reads the entire response

When you need to inspect multiple fields, partial data, or errors, use execute():

~~~java
Mono<ClientGraphQlResponse> responseMono = graphQlClient
        .documentName("bookById")
        .variable("id", "book-101")
        .execute();
~~~

Then you can inspect the response:

~~~java
Mono<Book> bookResult = responseMono.map(response -> {
    if (!response.isValid()) {
        // The request has errors and no valid response data.
        throw new IllegalStateException("GraphQL request failed");
    }

    ClientResponseField field = response.field("bookById");
    if (field.getValue() == null) {
        if (field.getErrors().isEmpty()) {
            // Nullable field has no value.
        }
        else {
            // Field is null due to an execution error.
        }
    }

    return field.toEntity(Book.class);
});
~~~

retrieve() is suitable when only a single decoded result is needed. execute() is suitable when you need to read multiple fields, check path-scoped errors, or distinguish a normal null field from a field that is null due to an execution error.

## Client documents for Mutations

A document can be a mutation. Declaring and passing variables works the same way as queries:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

Java request:

~~~java
public record CreateBookInput(
        String title,
        String authorId) {
}

CreateBookInput input =
        new CreateBookInput("Spring for GraphQL", "author-12");

Mono<Book> createdBook = graphQlClient
        .documentName("createBook")
        .variable("input", input)
        .retrieve("createBook")
        .toEntity(Book.class);
~~~

The mutation's selection set determines the data returned after the server performs the change. Request only the fields the client needs; there is no need to query the entire object if the UI only needs ID and title.

For partial update mutations, understand the difference between an omitted field and a field explicitly sent as null. By default, GraphQL input allows nullable fields to be either omitted or sent as null. These two states can carry different meanings: omitted means keep as-is, null means clear the value. If using ArgumentValue<T> on the client side, configure Jackson with GraphQlJacksonModule to serialize the omitted state properly. Do not assume every JSON codec understands this wrapper automatically.

## Client documents for Subscriptions

A document can also declare a subscription:

~~~graphql
subscription BookCreated {
  bookCreated {
    eventId
    book {
      id
      title
    }
  }
}
~~~

The client requires a streaming-capable transport, such as WebSocketGraphQlClient or RSocketGraphQlClient. When using one, the same request construction approach applies:

~~~java
Flux<BookCreatedEvent> events = webSocketGraphQlClient
        .documentName("bookCreated")
        .retrieveSubscription("bookCreated")
        .toEntity(BookCreatedEvent.class);
~~~

retrieveSubscription returns a Flux, with each element corresponding to a subscription result. To stop receiving events, cancel the reactive subscription. The document is the operation content; transport and streaming lifecycle are managed by the respective client.

## Testing documents and requests

Test documents against a real schema or test server to catch syntax errors, field names, variable types, and fragments before integrating with remote systems.

Scenarios to test:

1. The document has the right operation type and required fields.
2. Variable names match the declarations in the document.
3. Variable values are compatible with GraphQL input types.
4. Documents with multiple operations always specify operationName.
5. Fragments are defined and referenced properly.
6. documentName locates the file on the classpath.
7. retrieve paths point to the right fields in response.data.
8. execute handles errors and partial data.
9. Mutations send input objects with the expected structure.
10. Subscriptions use a streaming transport and are cancelled when no longer needed.

You can mock GraphQlClient to verify that a service sends the right document and variables, but mocks do not verify that a GraphQL document is valid against the schema. To test against the schema and real responses, use integration tests with an appropriate GraphQL endpoint or test server.

## Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Server reports missing variable | Forgot to call variable() or variables() | Match $variable declarations against passed keys |
| Variable not recognized | Wrong key name or wrong input object structure | Use exact name without $ prefix and check DTO/Map |
| Multi-operation document rejected | Did not specify which operation to run | Call operationName() |
| retrieve cannot find field | Path does not match response data | Check aliases, selection set, and path |
| documentName fails to load file | Wrong filename, extension, or classpath location | Place file under graphql-documents and use the right document key |
| Invalid fragment | Missing fragment definition or wrong type condition | Check fragment spread and schema types |
| Query fails when input contains quotes | Direct string interpolation into document | Pass data via GraphQL variables |
| Client cannot distinguish null from errors | Using retrieve without checking FieldAccessException | Use execute when reading field errors and response |
| DTO input serializes incorrectly | Codec does not handle Java types as expected | Check JSON codec and mapper configuration |
| Subscription does not return Flux | Using a transport that only supports single request/response | Choose WebSocket, RSocket, or HTTP SSE |

## Comprehensive practice

Build a BookGraphQlClient:

1. Create an HttpGraphQlClient using WebClient.
2. Write a BookById query with variable $id: ID!.
3. Send the document using document(String) and pass the ID via variable().
4. Create a bookById.graphql file in src/main/resources/graphql-documents.
5. Send the same query using documentName("bookById").
6. Create a document containing two operations and select one using operationName().
7. Create a BookSummary fragment and reuse it in a query.
8. Write a createBook mutation with an input object and variables().
9. Use retrieve() to read a field, then use execute() to inspect errors.
10. Write tests verifying the document name, variables, and selected operation.

After completing this, explain the difference between document name, operation name, and response field path; why inputs should be passed via variables; and when to move a document from a Java string to a .graphql file.

## Key takeaways

A client document is the GraphQL content describing the operation and selection set that the client sends to the server. Spring for GraphQL uses GraphQlClient.document(String) for document text and documentName(String) to load documents via DocumentSource. After declaring the document, use operationName() to select an operation when multiple operations exist, variable() or variables() to pass inputs, and retrieve() or execute() to read the response. Fragments help reuse selection sets; .graphql files make long documents easier to review and enable IDE support. Always pass data using variables instead of string concatenation, check paths against response data, and choose a transport suitable for queries, mutations, or subscriptions.

## References

- [Spring for GraphQL – Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [GraphQlClient API – document and documentName](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/client/GraphQlClient.html)
- [GraphQlClient.RequestSpec API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [GraphQL – Learn: Queries and Variables](https://graphql.org/learn/queries/)
