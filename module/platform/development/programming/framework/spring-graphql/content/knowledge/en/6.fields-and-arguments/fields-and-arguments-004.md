# Nullable Arguments

## Objectives

After this lesson, you will be able to:

- Explain the meaning of nullable arguments in a GraphQL schema.
- Distinguish an omitted argument from an argument passed a null value.
- Understand how default values interact with arguments and variables.
- Design query filters and partial-update mutations with nullable inputs.
- Bind arguments in Spring for GraphQL and use ArgumentValue<T> when you need to detect the omitted state.

## What is a nullable argument?

In GraphQL SDL, an argument without `!` is nullable. The client can pass a valid value or null, and can also omit the argument if the schema does not require it.

Example:

~~~graphql
type Query {
  books(authorId: ID, keyword: String, first: Int): [Book!]!
}
~~~

The three arguments `authorId`, `keyword`, and `first` are all nullable. The client can call the field without passing any arguments:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Or pass only some arguments:

~~~graphql
query {
  books(authorId: "author-12") {
    id
    title
  }
}
~~~

Or explicitly pass null:

~~~graphql
query {
  books(authorId: null, keyword: "Spring") {
    id
    title
  }
}
~~~

The fact that a nullable argument can accept null does not mean the application must handle null in one fixed way. The schema defines what data is valid in GraphQL; the business meaning of an omitted or null value is decided by the resolver and service.

## Distinguishing nullable and non-null

GraphQL uses `!` to declare a non-null value:

~~~graphql
type Query {
  bookById(id: ID!): Book
  books(authorId: ID): [Book!]!
}
~~~

`id: ID!` is a required argument: the client must provide a value and that value cannot be null. `authorId: ID` is an optional argument: the client can omit it or pass null.

| Declaration | Can be omitted? | Can null be passed? |
| --- | --- | --- |
| ID! without default | No | No |
| ID | Yes | Yes |
| Int = 20 | Yes, GraphQL uses the default | Yes; explicit null does not trigger the default |
| Int! = 20 | Yes, GraphQL uses the default | No |

A non-null argument with a default can still be omitted because GraphQL has a fallback value. Only a non-null argument without a default is a required argument in the sense that the client must supply it.

If the client passes null for a non-null argument, GraphQL rejects the request during the input validation/coercion phase. The resolver is not called with that null value.

## Distinguishing omitted and explicit null

This is an important distinction when designing an API. For a nullable argument without a default, both of the following requests are valid:

~~~graphql
query {
  books {
    id
  }
}
~~~

~~~graphql
query {
  books(authorId: null) {
    id
  }
}
~~~

The first request does not send the `authorId` argument. The second request sends the argument and its value is null. GraphQL preserves this distinction during input processing. However, if the resolver only accepts a nullable Java variable such as `String authorId`, both cases are usually bound to null; the method cannot infer whether the client omitted the argument or explicitly sent null.

This distinction is often important for:

- Search filters: omitting a filter may mean not filtering; sending null may mean finding records that have no value yet.
- Update mutations: omitting a field may mean keeping existing data; sending null may mean clearing the current value.
- Optional configuration: omitting may use the default configuration; null may indicate a request to disable or clear the configuration.

Define these semantics in the API contract. Clients should not have to guess what null means.

## When is a default value applied?

GraphQL allows declaring a default for an argument:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

If the client omits `first`, GraphQL uses the value `20`. If the client passes `first: 5`, the resolver receives `5`. If the client explicitly passes `first: null`, the value is null because the argument has a nullable type; the default does not replace an explicitly sent null value.

The same rule applies to fields in an input object:

~~~graphql
input BookSearchInput {
  keyword: String
  first: Int = 20
}

type Query {
  searchBooks(input: BookSearchInput): [Book!]!
}
~~~

If the `input` object is passed but omits the `first` field, GraphQL applies the default `20`. If the field is present with the value null, the value remains null because `first` is nullable.

A default value in the schema is part of the shared API contract. It is useful when every client should receive the same default value. If the default depends on the user, tenant, permissions, or request context, compute it at the service layer rather than hard-coding it in SDL.

## Nullable variables and arguments

Variables also have their own nullability. Example:

~~~graphql
query SearchBooks($authorId: ID, $first: Int) {
  books(authorId: $authorId, first: $first) {
    id
    title
  }
}
~~~

The client passes variables using JSON:

~~~json
{
  "authorId": "author-12",
  "first": 10
}
~~~

If there is no `authorId` key in the variables object, the variable is not provided. If there is a `"authorId": null` key, the variable is provided with a null value. With a nullable variable and a nullable argument, both cases are valid; the difference can affect whether the argument is present in the execution data.

A variable default is declared directly in the operation:

~~~graphql
query SearchBooks($first: Int = 10) {
  books(first: $first) {
    id
  }
}
~~~

If the client does not provide the `first` variable, GraphQL uses the default `10`. If the client passes `"first": null`, the variable value is null, and the default `10` is not used.

A nullable variable cannot be arbitrarily passed to a non-null position. For example, `$id: ID` cannot be used for an `id: ID!` argument without an appropriate default condition. The simplest and clearest approach for a required argument is to declare a non-null variable:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}
~~~

GraphQL checks compatibility between the variable type and its usage position before executing the resolver.

## Binding nullable arguments in Spring for GraphQL

With annotated controllers, `@Argument` binds an argument in the schema to a Java method parameter:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @Argument("authorId") String authorId,
            @Argument("keyword") String keyword,
            @Argument("first") Integer first) {

        int pageSize = first != null ? first : 20;
        return bookService.search(authorId, keyword, pageSize);
    }
}
~~~

With Java reference types such as `String` or `Integer`, the value can be null. Do not use the primitive type `int` for a nullable argument if the method needs to represent a missing value, because primitives cannot hold null.

In the example above, `first` can be defaulted in the service. If the schema already declares `first: Int = 20`, GraphQL applies the default before the resolver receives the argument. Choose one place responsible for setting the default to avoid duplicate logic and creating two different default values.

### Using ArgumentValue<T> to detect omitted

If you need to distinguish an omitted argument from an argument passed null, Spring for GraphQL provides `ArgumentValue<T>`. This wrapper indicates whether the argument was omitted and lets you read the underlying value:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @Argument("authorId") ArgumentValue<String> authorId) {

        if (authorId.isOmitted()) {
            return bookService.findAll();
        }
        if (authorId.value() == null) {
            return bookService.findWithoutAuthor();
        }
        return bookService.findByAuthorId(authorId.value());
    }
}
~~~

In this example, when the client omits `authorId`, all books are fetched; passing null finds books without an author; passing an ID filters by author. These are semantics chosen by the application. If business logic does not need to distinguish them, using a regular nullable parameter is simpler.

When you need to detect omission, consider default values in SDL. Defaults are applied during GraphQL input processing; if you want the resolver to decide between omitted and null itself, do not obscure that state with an unnecessary default.

## Nullable fields in input objects and partial-update mutations

Nullable arguments are especially useful for patch-style mutations. For example, a user might update the title or clear the subtitle of a book:

~~~graphql
input UpdateBookInput {
  title: String
  subtitle: String
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Both fields in `UpdateBookInput` are nullable. The client can send only the field to be updated:

~~~graphql
mutation UpdateTitle($id: ID!, $input: UpdateBookInput!) {
  updateBook(id: $id, input: $input) {
    id
    title
    subtitle
  }
}
~~~

Variables:

~~~json
{
  "id": "book-101",
  "input": {
    "title": "Spring GraphQL Guide"
  }
}
~~~

In this request, `title` is present, while `subtitle` is omitted. If `"subtitle": null` is sent, the client has explicitly specified a null value. A patch API can follow the convention that omitted means keep unchanged, while null means clear the content.

### Binding input objects with ArgumentValue

If you bind an input object into a DTO that only has regular nullable properties, omitted values and explicit null values may both become null. You can use `ArgumentValue<T>` on individual fields to preserve the omitted state:

~~~java
public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> subtitle) {
}
~~~

The controller can turn the DTO into an update command:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {

    if (!input.title().isOmitted() && input.title().value() == null) {
        throw new IllegalArgumentException("title must not be null");
    }

    return bookService.update(
            id,
            input.title(),
            input.subtitle());
}
~~~

The service receives each `ArgumentValue` and only changes fields that were not omitted. For `subtitle`, a null value can be interpreted as clearing the subtitle. For `title`, the example above rejects null according to business rules even though SDL allows nullable. That illustrates that schema nullability and business validation serve different roles.

When using `ArgumentValue` in an input DTO, verify binding with tests on your project's Spring for GraphQL version. Do not turn every nullable field into a wrapper if the use case does not need to distinguish omission from explicit null.

## Designing semantics for filters and patches

Before declaring a field nullable, answer two questions: can the client omit the field, and if null is sent, what should the system do?

| Use case | Omitted | Explicit null |
| --- | --- | --- |
| Filter by author | Do not apply filter | Fetch only books without an author |
| Filter by keyword | Do not restrict by keyword | Can reject or treat as no keyword |
| Patch subtitle | Keep current subtitle | Clear subtitle |
| Change contact email | Keep current email | Clear email if business rules allow |
| Result limit with default | Use schema default | Unlimited if service allows, or reject |

These are examples of semantics you can choose, not mandatory GraphQL rules. Document them clearly in the API docs and keep behavior consistent across mutations and queries.

## Testing omitted, null, and default

Tests should cover at least three states:

1. Not sending the argument or having no variable key.
2. Sending the argument/variable with a null value.
3. Sending a specific value.

With the query:

~~~graphql
query SearchBooks($authorId: ID) {
  books(authorId: $authorId) {
    id
  }
}
~~~

Run tests with variables missing the `authorId` key, variables containing `"authorId": null`, and variables containing `"authorId": "author-12"`. If the resolver uses `ArgumentValue`, verify both `isOmitted()` and `value()` for each case.

With a default value:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

Test omitting `first` to verify the effective value is 20, passing `first: 5` to verify the value is 5, and passing `first: null` to verify the default is not applied to explicit null.

For patch mutations, verify that omitted fields preserve existing data, fields with values are updated, and fields passed null are handled according to the published semantics. In addition to the returned result, verify the persisted state after the mutation to avoid tests that only assert the response and miss side effects.

## Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Nullable argument unexpectedly receives null | Client omitted the argument or passed null | Check variables and API semantics; use ArgumentValue if distinction is needed |
| Non-null argument is rejected | Client omitted a value or sent null | Fix schema/operation or send a valid value |
| Default is not applied | Client passed explicit null | Distinguish omitted from null; only omit the argument to use the default |
| Java fails when receiving null | Using a primitive like int for a nullable argument | Use a reference type such as Integer |
| Mutation accidentally deletes data | Resolver treats omitted and null as the same state | Use ArgumentValue and clearly define patch semantics |
| Input DTO does not distinguish omitted | DTO properties only use regular nullable types | Use ArgumentValue<T> on fields that need distinction and test binding |

## Hands-on practice

Build a book search and update API with the following requirements:

1. Query `books(authorId: ID, keyword: String, first: Int = 20)` allows clients to select filters.
2. If `authorId` is omitted, do not filter by author; if explicit null, return only books without an author.
3. If `first` is omitted, use the default value 20; if explicit null, return a validation error per API policy.
4. Mutation `updateBook(id: ID!, input: UpdateBookInput!)` supports partial updates.
5. If `subtitle` is omitted, keep it unchanged; if explicit null, clear the subtitle.

Use `ArgumentValue<T>` where state distinction is needed. Write tests for omitted, explicit null, specific value, and default cases. Then document the semantics of each argument so clients can use the API without guessing.

## Takeaways

Nullable arguments lack `!`, so clients can omit them or pass null. Those two states carry different meanings in many use cases, especially filters and partial-update mutations. GraphQL applies defaults when a value is omitted, whereas explicit null remains null if the type allows it. In Spring for GraphQL, a regular nullable `@Argument` parameter may not distinguish omitted from null; `ArgumentValue<T>` preserves this difference. Define the semantics in the schema, handle them in the service, and test all input states thoroughly.
