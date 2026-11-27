# Batch mapping field name

In Spring for GraphQL, **@BatchMapping** maps a Java method to a field of a GraphQL object type and resolves that field for multiple source objects in a single batch. The field name can be inferred directly from the method name. When the method name does not match the field name in the SDL, you must specify the `field` attribute explicitly so Spring registers the right mapping.

This naming rule directly determines whether the resolver gets invoked. This lesson covers how Spring determines the field and type, when explicit declaration is needed, choosing Map or List return types, common naming mismatch errors, and testing.

## 1. Which field does @BatchMapping map to?

Suppose the schema has Book and Author:

~~~graphql
type Query {
    books: [Book!]!
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

Each Book may need to load its Author. With `@SchemaMapping`, the resolver typically handles one Book at a time. With `@BatchMapping`, the method receives a list of Books and loads Authors for the whole group:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findForBooks(books);
    }
}
~~~

In this example, Spring infers:

- The source GraphQL type is `Book` from the element type of `List<Book>`.
- The field name is `author` from the method name.
- The method handles the `Book.author` field.

The method name `author` matches the `author` field in the SDL, so there is no need to specify `typeName` and `field` in the annotation.

`@BatchMapping` does not automatically create a new field in the schema. The field must still be declared in the SDL, and the mapping name must match that contract.

## 2. Default rule: method name is the field name

When the `field` attribute is omitted, Spring uses the method name as the GraphQL field name to map.

SDL example:

~~~graphql
type Book {
    reviews: [Review!]!
}
~~~

Method:

~~~java
@BatchMapping
public Map<Book, List<Review>> reviews(List<Book> books) {
    return reviewService.findForBooks(books);
}
~~~

The method name `reviews` is used as the field name. Spring maps the method to `Book.reviews`.

Field names are matched by exact GraphQL name, including case. GraphQL is case-sensitive, so `reviews`, `Reviews`, and `review` are distinct names.

There is no automatic rule converting plural to singular or vice versa. If a method is named `authors`, Spring looks for the `authors` field; it does not infer that the method is meant to handle the `author` field.

The following example does not map to `Book.author`:

~~~java
@BatchMapping
public Map<Book, Author> authors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

If the schema only has `Book.author`, rename the method to `author` or declare `field = "author"`.

## 3. Specifying the field via the field attribute

When a method is named after Java conventions or a service operation, you can specify the GraphQL field using the `field` attribute.

SDL:

~~~graphql
type Book {
    author: Author
}
~~~

Java method:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Here:

- The Java method name is `loadAuthors`.
- The GraphQL field name is `author`.
- `field = "author"` explicitly identifies the mapping to register.

You can omit `typeName` if Spring can infer the source type from `List<Book>`. However, declaring both attributes lets readers see the full mapping coordinates at a glance:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Explicit declaration is helpful when the method name differs from the field name, when the Java type and GraphQL type names differ, or when the codebase has many mappings to review.

## 4. Rules for determining typeName

Besides the field name, Spring needs to know which GraphQL object type owns the field. `@BatchMapping` can infer the type from the source object type in the list parameter.

Example:

~~~java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Spring infers the source type as Book and the field as author.

If you want to specify the GraphQL type explicitly, use `typeName`:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

`typeName` must be the object type name in the SDL schema, not necessarily the Java class name if the two are mapped differently.

SDL example:

~~~graphql
type CatalogBook {
    id: ID!
    writer: Author
}
~~~

The Java model can still be named Book:

~~~java
public record Book(Long id, Long authorId) {
}
~~~

In that case, the mapping must specify the exact GraphQL type and field names:

~~~java
@BatchMapping(typeName = "CatalogBook", field = "writer")
public Map<Book, Author> loadWriters(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Do not use `typeName = "Book"` just because the Java class is named Book if the SDL actually exposes the type as CatalogBook.

## 5. When should you declare both typeName and field?

You can rely on default inference when methods and models are simple. However, explicit mapping is often easier to maintain in the following cases:

- The method name differs from the field name.
- The GraphQL type name differs from the Java class name.
- The source parameter uses generics or abstractions that make type inference hard to read.
- Multiple object types share fields with the same name.
- You want reviewers to immediately recognize the GraphQL coordinates handled by the method.

Example where two types both have an `owner` field:

~~~graphql
type Book {
    owner: User
}

type Article {
    owner: User
}
~~~

You can separate the two batch mappings:

~~~java
@BatchMapping(typeName = "Book", field = "owner")
public Map<Book, User> bookOwners(List<Book> books) {
    return userService.findOwnersOfBooks(books);
}

@BatchMapping(typeName = "Article", field = "owner")
public Map<Article, User> articleOwners(List<Article> articles) {
    return userService.findOwnersOfArticles(articles);
}
~~~

The Java method names can differ, while the two GraphQL coordinates remain unambiguous: `Book.owner` and `Article.owner`.

## 6. Method signature and source objects

A batch mapping receives a group of source objects belonging to the same GraphQL type. The list parameter represents the objects whose field needs to be resolved.

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

`List<Book>` is the list of source objects. Each element corresponds to one resolution of the `Book.author` field.

The method does not accept a single Book like a regular `@SchemaMapping`. If the source parameter is declared inappropriately, Spring may fail to infer the type or fail to register the batch mapping as expected.

Some forms of source parameter can make inference unclear, such as a raw `List` without a generic type:

~~~java
@BatchMapping
public Map<?, ?> author(List<?> books) {
    // Missing element type to infer the source type.
    return Map.of();
}
~~~

Declare a concrete generic type instead:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Even when `typeName` is specified, a concrete element type keeps the method signature clear and type-safe at compile time.

## 7. Choosing Map or List as the return type

`@BatchMapping` can return results in two common ways:

- `Map<S, V>`: maps each source object to its corresponding field value.
- `List<V>`: returns a list of results in the exact order of the input list of source objects.

### Returning a Map

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

The Map must use the source object itself as the key, not `authorId`, unless the source object itself happens to be that ID. Spring uses each Book as the key to look up the corresponding Author.

Example:

~~~java
Map<Book, Author> result = new HashMap<>();
result.put(bookA, authorA);
result.put(bookB, authorB);
result.put(bookC, authorC);
return result;
~~~

Do not return `Map<Long, Author>` keyed by Book ID if the method is declared as `Map<Book, Author>`. The key type must match the source object that Spring uses to match results.

### Returning a List

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    return authorService.findAuthorsInBookOrder(books);
}
~~~

With the List form, the element at index `i` must be the result for the source object at index `i` in the input list.

If Spring passes `[bookA, bookB, bookC]`, the result must correspond to `[authorA, authorB, authorC]`. Do not return a list in an arbitrary order from the database.

If a Book has no Author and the field is nullable, the list must preserve that slot with a corresponding null value. Because `List.of()` disallows null elements, use a mutable list or another suitable collection.

### Which one should you choose?

| Return type | When it fits | What to guarantee |
| --- | --- | --- |
| `Map<Book, Author>` | Results can be indexed by the source object. | Keys are the exact Books from the input batch. |
| `List<Author>` | The service can easily return results in exact source order. | Element order and count must match. |

The Map form is often easier to read when repository queries return unordered results. The List form fits well if the service already has a strategy to align results accurately with the source list.

## 8. Returning results asynchronously

A batch mapping may need to call an asynchronous service or repository. Spring for GraphQL supports asynchronous return types aligned with the data fetcher mechanism.

Example with `Mono`:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    return authorService.findForBooksReactive(books);
}
~~~

Or with `CompletableFuture`:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public CompletableFuture<Map<Book, Author>> author(List<Book> books) {
    return authorService.findForBooksAsync(books);
}
~~~

The return type should match your application's stack. If the repository is reactive, keep the pipeline reactive. If using a blocking repository, run I/O on an appropriate executor or scheduler; do not block event-loop threads.

Do not arbitrarily call `.block()`, `.join()`, or `.get()` inside a batch mapping, as doing so defeats asynchronous benefits and can cause thread starvation.

## 9. How does the field name affect DataLoader?

Spring uses `@BatchMapping` to create the corresponding DataLoader for the mapped field. The field name and type determine the mapping the GraphQL engine uses when resolving nested fields.

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

This method handles `Book.author`. If the client queries:

~~~graphql
query {
    books {
        title
        author {
            id
            name
        }
    }
}
~~~

GraphQL calls the batch mapping for the author field on the Books in the books result.

If the method accidentally maps to `Book.authors`, while the SDL only has `Book.author`, clients still cannot use that mapping for the author field. `@BatchMapping` does not rename fields in the SDL nor alter client operations.

Therefore, when a resolver is not invoked, check the type/field coordinates before investigating DataLoader or the repository.

## 10. Distinguishing @BatchMapping from @SchemaMapping

Both annotations map methods to fields of a GraphQL object type, but they handle sources differently.

### @SchemaMapping handles a single source object

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

The method receives one Book and typically loads the Author for that Book.

### @BatchMapping handles a group of source objects

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

The method receives a list of Books and loads Authors for the entire group.

Avoid registering both `@SchemaMapping` and `@BatchMapping` for the same `Book.author` coordinates unless there is a very specific, deliberate design. Both try to handle the same field and can cause conflicting mappings or unpredictable behavior.

`@BatchMapping` is suitable when data can be loaded in bulk. `@SchemaMapping` is suitable for fields needing custom per-source logic or no batching.

## 11. Common naming mismatch errors

Several common errors stem from mismatches between method, field, and type names.

| Symptom | Cause | Fix |
| --- | --- | --- |
| Resolver does not run for `Book.author` | Method is named `authors` and annotation lacks `field`. | Rename the method to `author` or set `field = "author"`. |
| Field is not mapped even with right method name | Source type was inferred incorrectly. | Set `typeName = "Book"` and check the source parameter type. |
| Mapping does not match schema | Using Java class name instead of GraphQL type name. | Use the exact type name from the SDL. |
| Field has different casing | GraphQL is case-sensitive. | Use the exact field name from the SDL. |
| Method uses raw List | Missing generic source type for clear inference. | Use `List<Book>` and declare `typeName` if needed. |
| Returned Map has no results | Map key is not the matching source object. | Use `Map<Book, Author>` keyed by the Books from the batch. |
| List returns wrong field values | List results do not match source object order. | Order results to match input order or use a Map. |
| Two methods map to the same coordinates | Duplicate mapping registration. | Keep one clear batch mapping per type/field. |

## 12. Testing the field name of @BatchMapping

Test an actual operation invoking the exact field in the SDL. For example:

~~~graphql
type Query {
    books: [Book!]!
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

Batch mapping:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Test with GraphQlTester:

~~~java
@Test
void resolvesAuthorFieldUsingExplicitFieldName() {
    graphQlTester.document("""
            query {
                books {
                    title
                    author {
                        name
                    }
                }
            }
            """)
        .execute()
        .path("books[0].author.name")
        .entity(String.class)
        .isEqualTo("Ada");
}
~~~

This test verifies that the `Book.author` field is resolved via the mapping explicitly configured with `field = "author"` even though the method is named `loadAuthors`.

Additional cases to test:

- Default mapping when method name matches the field.
- Explicit mapping when method name differs from the field name.
- Type name inferred from `List<Book>`.
- Type name declared explicitly when the GraphQL type differs from the Java class name.
- Two object types with identically named fields differentiated by `typeName`.
- Map containing keys for all source objects.
- List preserving source object order.
- Source objects with no related data.
- Batch mapping returning asynchronous results.
- No duplicate resolvers registered for the same coordinates.

A unit test calling the Java method directly is not enough to prove Spring registered the field properly. Execute operations through GraphQlTester to test the entire schema and mapping.

## 13. Workflow for naming and implementing batch mappings

When adding a new batch mapping, you can follow this sequence:

1. Identify the GraphQL object type containing the field to batch.
2. Check the exact type and field names in the SDL.
3. Choose a Java method name matching the field if using default inference.
4. If the method name differs, declare `field` explicitly.
5. If the type cannot be clearly inferred from the source parameter, declare `typeName`.
6. Use `List<SourceType>` as the source parameter with a concrete generic type.
7. Choose `Map<SourceType, Value>` or `List<Value>` and ensure accurate result matching.
8. Return an appropriate asynchronous type if the service performs I/O.
9. Verify no other mapping is registered for the same type/field.
10. Write GraphQlTester tests confirming the operation invokes the right field.
11. Verify batch counts and returned data when multiple source objects exist.

## 14. Key takeaways

- `@BatchMapping` maps a group of source objects to a field on a GraphQL object type.
- By default, the method name is the GraphQL field name.
- A method named `authors` does not automatically map to the `author` field; rename it or set `field = "author"`.
- `typeName` can be inferred from the generic source parameter; declare it explicitly when Java and GraphQL types differ or to clarify the mapping.
- GraphQL type and field names must match the SDL exactly, including case.
- The source parameter should have a concrete generic type such as `List<Book>`.
- `Map<Source, Value>` matches by source object; `List<Value>` must preserve exact source order.
- Results can be returned asynchronously when appropriate for the service/repository.
- Avoid registering both `@SchemaMapping` and `@BatchMapping` on the same coordinates unless intentional.
- Use GraphQlTester to verify the mapping is actually wired to the SDL field.

The field name rule of `@BatchMapping` is straightforward: the method name serves as the field name by default, while `field` lets you specify the GraphQL name explicitly when needed. Combined with the proper `typeName`, source generic type, and return type, Spring for GraphQL can attach batch results to the exact fields clients request.
