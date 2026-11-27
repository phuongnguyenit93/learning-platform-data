# Default Field Names from Methods

## Objectives

After this lesson, you can:

- Explain how Spring for GraphQL infers field names from method names in annotated controllers.
- Distinguish between field name inference rules and type name inference rules.
- Use `@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping` for root fields.
- Use `@SchemaMapping` to map fields of object types.
- Override field or type names using annotation attributes when Java names differ from the SDL.
- Recognize mapping errors caused by method names, source parameters, or duplicate mappings.
- Write controllers with clear method names that stay consistent with the GraphQL schema.

## 1. Why Do Method Names Affect GraphQL Fields?

In Spring for GraphQL, annotated controllers connect Java methods to fields in the GraphQL schema. You do not need to manually register every `DataFetcher` as you do when working directly with GraphQL Java.

Spring can infer mappings from method names and source parameter types. As a result, controllers are typically concise:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

With the default conventions:

- `bookById` is mapped to the `Query.bookById` field.
- `author` is mapped to the `Book.author` field.
- The source parameter type `Book` helps Spring determine the parent GraphQL type for `author`.

This rule keeps Java names and GraphQL field names consistent. When a method needs a different name from the field in the SDL, you can declare the name explicitly via the annotation.

## 2. Default Inference Rules

There are two main pieces of information Spring needs to determine when registering a field mapping:

1. **Field name:** the GraphQL field name that the method handles.
2. **Type name:** the GraphQL type that owns that field.

How inference works depends on the annotation used:

| Annotation | Default Type Name | Default Field Name |
|---|---|---|
| `@QueryMapping` | `Query` | Method name |
| `@MutationMapping` | `Mutation` | Method name |
| `@SubscriptionMapping` | `Subscription` | Method name |
| `@SchemaMapping` | Inferred from source parameter type | Method name |
| `@BatchMapping` | Inferred from source parameter type | Method name |

The Query, Mutation, and Subscription annotations are specialized shortcuts for their corresponding root types. For fields belonging to other object types, use `@SchemaMapping` or `@BatchMapping`.

### Field Name Derived from Method Name

Example schema:

~~~graphql
type Query {
  books: [Book!]!
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Spring registers the `books` method for `Query.books` and the `bookById` method for `Query.bookById`. There is no need to pass the field name to the annotation when the method name already matches the SDL.

### Type Name Inferred from Source Parameter

For nested fields, the source parameter is the parent object currently being resolved. The Java type of this parameter is used to infer the GraphQL type.

Schema:

~~~graphql
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

Controller:

~~~java
@Controller
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

The `author` method is mapped to the `Book.author` field because:

- The method name is `author`.
- The source parameter has Java type `Book`.
- The GraphQL schema has an object type `Book` with a field `author`.

The `book` parameter is the source object returned by the parent field, such as `Query.bookById`. Spring passes that object into the method when `Book.author` needs to be resolved.

The variable name `book` does not determine the type name; the Java type `Book` is what matters. Renaming the variable to `source` does not change the mapping.

## 3. @QueryMapping: Method Name Becomes a Query Field

`@QueryMapping` is a shortcut for mapping on the `Query` root type. The method name is used as the field name if no other name is declared.

SDL:

~~~graphql
type Query {
  product(id: ID!): Product
  featuredProducts: [Product!]!
}
~~~

Controller:

~~~java
@Controller
public class ProductController {

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }

    @QueryMapping
    public List<Product> featuredProducts() {
        return productService.findFeatured();
    }
}
~~~

Resulting mappings:

| Java Method | GraphQL Field |
|---|---|
| `product(...)` | `Query.product` |
| `featuredProducts()` | `Query.featuredProducts` |

Method names must match the fields in the SDL. For example, if the schema uses `product` but the method is named `findProduct`, Spring looks for `Query.findProduct` by default. In that case, either rename the method or declare the field name explicitly.

## 4. @MutationMapping and @SubscriptionMapping Also Use Method Names

The same field name inference rule applies to Mutation and Subscription.

SDL:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
  deleteBook(id: ID!): Boolean!
}

type Subscription {
  bookAdded: Book!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }

    @MutationMapping
    public boolean deleteBook(@Argument String id) {
        return bookService.delete(id);
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return bookEventPublisher.bookAdded();
    }
}
~~~

Spring infers:

- `createBook` → `Mutation.createBook`.
- `deleteBook` → `Mutation.deleteBook`.
- `bookAdded` → `Subscription.bookAdded`.

Return types, arguments, or variable names do not determine the field name. If a method is named according to a business convention that differs from the schema, use the name attribute on the annotation to declare the mapping explicitly.

## 5. @SchemaMapping: Method Name and Source Type Determine Nested Fields

`@SchemaMapping` is used to handle a field of any GraphQL type. When attributes are omitted, Spring infers:

- Field name from the method name.
- Type name from the source parameter type.

Example schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
}

type Review {
  id: ID!
  rating: Int!
}
~~~

Controller:

~~~java
@Controller
public class BookFieldController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }
}
~~~

Corresponding mappings:

| Method | Source Parameter | GraphQL Mapping |
|---|---|---|
| `author(Book book)` | `Book` | `Book.author` |
| `reviews(Book book)` | `Book` | `Book.reviews` |

A method can also accept additional arguments or context parameters. The source object remains the parameter Spring recognizes as the parent object; parameters marked with annotations like `@Argument` or `@ContextValue` serve their own distinct purposes.

Example:

~~~java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument Integer minRating) {

    return reviewService.findByBookIdAndMinRating(
            book.getId(), minRating);
}
~~~

The method above still handles `Book.reviews`; the `minRating` argument simply adds a filter condition.

## 6. Overriding the Field Name When the Method Has a Different Name

Method names should usually match field names, though that is not always convenient. A method may be named according to business intent or Java conventions while the schema uses a shorter name.

With `@QueryMapping`, use the `name` attribute to specify the field:

~~~java
@Controller
public class BookController {

    @QueryMapping(name = "book")
    public Book findBookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Even though the method is named `findBookById`, Spring still maps it to `Query.book`.

With `@MutationMapping` and `@SubscriptionMapping`, you can specify the field name in the same way:

~~~java
@MutationMapping(name = "renameBook")
public Book updateBookTitle(
        @Argument String id,
        @Argument String title) {
    return bookService.rename(id, title);
}

@SubscriptionMapping(name = "bookEvents")
public Flux<BookEvent> streamBookChanges() {
    return bookEventPublisher.events();
}
~~~

With `@SchemaMapping`, use the `field` attribute:

~~~java
@SchemaMapping(field = "author")
public Author resolveBookAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

The `resolveBookAuthor` method still maps to the `author` field. The type name continues to be inferred from the `Book` source parameter.

You can specify both attributes to make the mapping completely explicit:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author resolveBookAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

This style is useful when the Java class name differs from the GraphQL type name or when you want readers of the controller to immediately see the target mapping.

## 7. Overriding the Type Name When the Java Class Differs from the GraphQL Type

Normally, the Java source type can infer the type name by naming convention. However, the domain model might use a different name than the public schema.

For example, Java uses the class `CatalogEntry`, while GraphQL exposes the object type `Book`:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Controller:

~~~java
@Controller
public class CatalogEntryController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(CatalogEntry entry) {
        return authorService.findById(entry.getAuthorId());
    }
}
~~~

Here, `typeName = "Book"` explicitly states that the field belongs to the GraphQL type `Book`, while the `CatalogEntry` parameter is the Java source object. Spring does not need to infer the GraphQL type name from the class name in this case.

Use this approach when a DTO, projection, or domain object has a different name from the schema. There is no need to rename a Java class solely to match the GraphQL type name.

## 8. Inference Rules Are Not JavaBean Getter Mapping

Method names in annotated controllers are used for field mapping according to annotation rules. Do not assume Spring will automatically strip `get` or `is` prefixes as it does when mapping JavaBean properties.

For example, the method:

~~~java
@SchemaMapping
public Author getAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Under method name inference, the default target field is `Book.getAuthor`. If the SDL declares the field `author`, rename the method to `author` or specify it explicitly:

~~~java
@SchemaMapping(field = "author")
public Author getAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Similarly, a method named `isAvailable` should not be expected to map automatically to the `available` field. Name the method to match the field or use the `field` attribute to avoid confusion.

This also makes code reviews easier: readers can determine the mapping from the annotation and method name without guessing JavaBean rules.

## 9. @BatchMapping Also Infers the Field from the Method

`@BatchMapping` is how you declare a batch resolver for a field, typically used to load related data for multiple source objects at once. The default field name rule is still based on the method name; the type name is inferred from the source type inside the collection.

Example:

~~~graphql
type Book {
  id: ID!
  author: Author
}
~~~

~~~java
@Controller
public class BookBatchController {

    @BatchMapping
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .collectMap(
                        Author::getId,
                        Function.identity()
                )
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();

                    for (Book book : books) {
                        result.put(
                                book,
                                authorsById.get(book.getAuthorId()));
                    }

                    return result;
                });
    }
}
~~~

Spring infers that the `author` method is a batch mapping for the `Book.author` field. If the method is named `loadAuthors`, declare the target field explicitly using the `field` attribute of `@BatchMapping`.

Batch mapping reduces calls to the data source when a query fetches multiple Books along with their authors. It does not change the field's meaning in the schema and does not replace choosing the right type name or field name.

When returning a Map, ensure keys have stable equality and map accurately to each source object. If returning an ordered Flux, the order of elements must correspond to the input source list.

## 10. Multiple Methods with the Same Name and Duplicate Mappings

Having the same method name across different controllers does not necessarily cause a conflict if they belong to different GraphQL types.

Example:

~~~java
@Controller
public class BookController {

    @SchemaMapping
    public String label(Book book) {
        return book.getTitle();
    }
}

@Controller
public class AuthorController {

    @SchemaMapping
    public String label(Author author) {
        return author.getName();
    }
}
~~~

The two methods correspond to:

- `Book.label`.
- `Author.label`.

They do not conflict because the type names are different.

Conversely, if two methods are both registered for `Book.label`, Spring cannot arbitrarily pick one. Duplicate or ambiguous mappings can cause controller mapping initialization to fail. Check whether:

- Two methods share the same type name and field name.
- One method explicitly declares a field already owned by another method.
- Both `@SchemaMapping` and a manual DataFetcher are registered for the same field.
- A controller is component-scanned multiple times or configured twice.

Keeping a single clear owner for each field mapping helps avoid hard-to-diagnose errors.

## 11. Common Errors When Inferring Field Names

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Query reports no matching field | Method name differs from SDL field | Rename method or use `@QueryMapping(name = "...")` |
| Nested field is not resolved | Source parameter infers wrong type name | Use `@SchemaMapping(typeName = "...")` |
| `getAuthor` does not map to `author` | Method name is used directly as field name | Use method `author` or `field = "author"` |
| Mutation cannot find field | Method name differs from field in Mutation | Use `@MutationMapping(name = "...")` |
| Subscription mapping is wrong | Method name differs from field in Subscription | Use `@SubscriptionMapping(name = "...")` |
| Mapping is ambiguous | Multiple methods registered for same type and field | Remove duplicate mapping or change target mapping |
| Source parameter is not recognized properly | Method signature has multiple parameters with unclear roles | Check annotations on each parameter and declare `typeName` explicitly |

When a field does not work, check in order:

1. Field name in the SDL.
2. Java method name.
3. Annotation used and its `name`/`field` attributes.
4. Type name inferred from the source parameter.
5. Other mappings with the same type and field.
6. Annotated controller startup logs to spot mapping registration errors.

## 12. Testing Mappings by Method Name

You should write integration tests to verify that Spring actually maps methods to fields as expected. `GraphQlTester` lets you execute operations against the configured schema and controllers.

Example schema:

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
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping(name = "book")
    public Book findBook(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(field = "author")
    public Author resolveAuthor(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Test:

~~~java
@Test
void shouldResolveFieldsUsingExplicitNames() {
    graphQlTester.document("""
            query {
                book(id: "b-01") {
                    id
                    title
                    author {
                        name
                    }
                }
            }
            """)
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
}
~~~

Cases worth testing:

- Method name matches field name without needing override attributes.
- Method name differs from field name and explicit mapping works.
- Java source type infers the right GraphQL type.
- Explicit `typeName` works when the Java class has a different name from the schema.
- Query, Mutation, and Subscription are registered under their respective root types.
- Two controllers use the same method name for different GraphQL types.
- Duplicate mappings are detected rather than silently calling the wrong method.

## 13. Method Naming Principles in Annotated Controllers

To keep controllers readable and less dependent on explicit overrides:

- Name methods to match GraphQL fields whenever possible.
- Use `@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping` for root operations.
- Use `@SchemaMapping` for object type fields.
- Let the source parameter clearly represent the parent object.
- Use `name`, `field`, or `typeName` only when Java names must diverge from schema names.
- Do not assume `get` or `is` prefixes are stripped automatically.
- Avoid registering multiple methods for the same type and field.
- Test actual operations whenever renaming methods or modifying the schema.

The method name is part of the mapping convention, so renaming a method can change which GraphQL field Spring registers if no override attribute is present. During refactoring, check the controller, the SDL, and the related integration tests together.

## Conclusion

Spring for GraphQL uses method names by default to infer field names. With `@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping`, the type names are Query, Mutation, and Subscription, respectively. With `@SchemaMapping` and `@BatchMapping`, the type name is inferred from the source parameter.

When a method name or Java type differs from the schema, you can declare `name`, `field`, and `typeName` to make the mapping explicit. Understanding these rules keeps controllers concise and readable, avoids missing-field errors, and prevents duplicate mappings as the application grows.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Spring for GraphQL — QueryMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/QueryMapping.html)
- [Spring for GraphQL — BatchMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
