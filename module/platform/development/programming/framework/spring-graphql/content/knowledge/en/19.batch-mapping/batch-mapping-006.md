# Batch mapping type name

In Spring for GraphQL, `@BatchMapping` registers a batch resolver for a field of a GraphQL object type. The `typeName` attribute specifies **the GraphQL type that contains the field to resolve**. This tells Spring which type's field the batch method handles, especially when the Java class name does not match the schema type name or when an explicit mapping is desired.

For example, the `author` field on the GraphQL type `Book` is represented by `@BatchMapping(typeName = "Book", field = "author")`. The method receives a list of `Book` source objects, loads the authors in one call, and returns results mapped back to each book.

## 1. `typeName` specifies the parent GraphQL type

Suppose the schema has a relationship between books and authors:

```graphql
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
```

The `author` field resides inside the `Book` object type. Therefore, when registering a batch resolver for this field, `typeName` is `Book`:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    // Load authors for multiple books in a single call.
}
```

You can read the annotation by its structure:

- `typeName = "Book"`: the GraphQL object type that owns the field.
- `field = "author"`: the field to batch resolve on that type.
- `List<Book> books`: the source objects whose `author` field needs resolution.
- `Map<Book, Author>`: the result pairing each source object with its corresponding field value.

Thus, `typeName` is the parent type name in the SDL. It is not the return type name `Author`, not the Java package name, and not the controller name.

## 2. Declaring `@BatchMapping` with an explicit typeName

Full example with Java records:

```java
public record Book(
    String id,
    String title,
    Long authorId
) {}

public record Author(
    String id,
    String name
) {}
```

Batch controller:

```java
package com.example.graphql.book;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<Long> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

        Map<Long, Author> authorsById =
            authorService.findMapByIds(authorIds);

        Map<Book, Author> result = new LinkedHashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

`AuthorService.findMapByIds` here represents a method that loads multiple authors by a list of IDs and returns a map `authorId -> Author`. The batch method then builds a `Book -> Author` map so Spring for GraphQL matches results to each source object.

The snippet uses `LinkedHashMap` to preserve order for readability and allow null values if an author does not exist. Still, the most important requirement for a map result is that the keys match the exact source objects passed into the batch. The `author` field in the schema is nullable, so a book without an author can receive null under this contract.

## 3. Distinguishing typeName and field

The two attributes `typeName` and `field` address two different parts of the mapping:

| Attribute | Specifies | Example |
| --- | --- | --- |
| `typeName` | GraphQL type containing the field | `Book` |
| `field` | Field name on that GraphQL type | `author` |

Combining the two values forms the mapping address `Book.author`. You can picture it like a type/field path in the schema:

```text
Book
 ├── id
 ├── title
 └── author  <-- batch mapping
```

If you only declare `typeName = "Book"` and omit `field`, Spring infers the field name from the method name. If the method is named `author`, the mapping is `Book.author`.

```java
@BatchMapping(typeName = "Book")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

If the method name differs from the field in the SDL, declare `field` explicitly:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findByBooks(books);
}
```

In the second example, the method name `loadAuthors` is not the GraphQL field name. `field = "author"` is what determines the mapping.

## 4. When can Spring infer typeName?

`typeName` is an optional attribute. If omitted, Spring for GraphQL can infer the GraphQL type from the source type in the batch method's collection parameter.

Example:

```java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Since the source type is `Book`, Spring can infer the type owning the field is `Book`; the method name `author` is used to infer the field. This is a concise shorthand when Java type names align with GraphQL type names.

Inference is convenient in simple cases, but Java names do not always match GraphQL names. If the Java model is `BookEntity`, `BookView`, or another domain class while the SDL uses `Book`, declare `typeName` explicitly to prevent Spring from inferring a type name that does not exist in the schema.

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookEntity, AuthorView> author(List<BookEntity> books) {
    return authorService.findByBookEntities(books);
}
```

Here `BookEntity` is the Java type of the source objects; `Book` is the GraphQL type name owning the field. The two names do not need to match, because the annotation defines the mapping explicitly.

## 5. `typeName` is not the Java return type

A common mistake is using the class name of the return value as `typeName`. This is wrong because `typeName` refers to the object type that owns the field.

With the schema:

```graphql
type Book {
    id: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Correct mapping:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

`Book` is the parent type containing the `author` field; `Author` is the value type of the field. If you write `typeName = "Author"`, Spring will look for the `author` field on the `Author` type, which maps to the wrong place in the SDL.

Always determine the mapping by looking at where the field is declared in the SDL. If the field is inside `type X { ... }`, then `typeName` must point to `X`.

## 6. Multiple types with fields of the same name

A schema may declare multiple object types with identically named fields. For example, both `Book` and `Magazine` have a `publisher` field:

```graphql
type Book {
    id: ID!
    publisher: Publisher
}

type Magazine {
    id: ID!
    publisher: Publisher
}
```

The two fields share a name but may require different data loading logic. `typeName` distinguishes them clearly:

```java
@BatchMapping(typeName = "Book", field = "publisher")
public Map<Book, Publisher> bookPublishers(List<Book> books) {
    return publisherService.findForBooks(books);
}

@BatchMapping(typeName = "Magazine", field = "publisher")
public Map<Magazine, Publisher> magazinePublishers(List<Magazine> magazines) {
    return publisherService.findForMagazines(magazines);
}
```

Although both methods handle the `publisher` field, each mapping is identified by its type/field pair: `Book.publisher` and `Magazine.publisher`. This is why you should declare `typeName` explicitly when a controller handles multiple GraphQL types or when identically named fields have distinct logic.

## 7. Type name must match the name in the SDL

GraphQL type names are case-sensitive. If the SDL declares `type Book`, the annotation must use `"Book"`, not `"book"` or `"BOOK"`.

Example:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    author: Author
}
```

Mapping:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

If the annotation uses `typeName = "book"`, the mapping does not point to the declared GraphQL type. Similarly, if you rename a type in the SDL and forget to update the annotation, the resolver may not be attached to the intended field.

When the schema is split across multiple files, look up the actual type definition in the loaded SDL. File names or Java package names do not determine `typeName`.

## 8. Batch results must match the source objects

`typeName` selects the right GraphQL field, but it does not alter the input and output data contract of the batch method.

With `@BatchMapping`, the method typically receives a list of source objects. It can return:

- `Map<Source, Value>`: maps each source object to its corresponding result.
- `List<Value>`: a list of results in the exact order of the input source list.

Example returning a list:

```java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    List<Long> ids = books.stream()
        .map(Book::authorId)
        .toList();
    return authorService.findInSameOrder(ids);
}
```

If using `List<Value>`, the service must return results in the exact order of `books`. Do not assume a `WHERE id IN (...)` query preserves the order of input IDs. If ordering cannot be guaranteed, use a map or rebuild the list following the input list.

With `Map<Source, Value>`, the key must be the corresponding source object rather than an arbitrary ID, unless the signature/adapter is specifically designed for that key. `@BatchMapping` maps results back to parent objects; using the wrong key can cause fields to return null.

## 9. Using typeName with differently named DTOs or entities

In layered architectures, Java classes often have suffixes to distinguish persistence entities, domain models, and API views:

```java
public record BookView(
    String id,
    Long authorId
) {}

public record AuthorView(
    String id,
    String name
) {}
```

The SDL can still keep short, stable names:

```graphql
type Book {
    id: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Explicit declaration:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookView, AuthorView> author(List<BookView> books) {
    return authorService.findViewsForBooks(books);
}
```

`typeName` decouples the GraphQL contract from Java class names. As a result, you can rename `BookView` to another DTO without changing the public type name in the SDL, as long as the mapping is updated accordingly.

## 10. Distinguishing @BatchMapping and @SchemaMapping regarding typeName

Both annotations describe a field belonging to a GraphQL type, but they execute differently:

| Annotation | Source parameter | Common return type | Purpose |
| --- | --- | --- | --- |
| `@SchemaMapping` | One source object, e.g., `Book` | One `Author` or corresponding async type | Resolve a field individually for one parent |
| `@BatchMapping` | List of source objects, e.g., `List<Book>` | `Map<Book, Author>` or `List<Author>` | Batch field resolution across multiple parents |

Single mapping example:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

Batch mapping example:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> authors(List<Book> books) {
    return authorService.findByBooks(books);
}
```

In both cases, `typeName = "Book"` points to the parent type containing the `author` field. The difference is that batch mapping accepts multiple parents and processes data in bulk to reduce N+1.

Do not register both methods simultaneously for the same `Book.author` pair without an explicit, deliberate reason. Choose one resolution mechanism for that field to avoid duplicate mappings.

## 11. Type name and interfaces or unions

Interfaces and unions allow fields to appear on polymorphic types, so you must distinguish where the field is declared in the schema.

If the field is declared on an interface:

```graphql
interface Publication {
    id: ID!
    publisher: Publisher
}

type Book implements Publication {
    id: ID!
    publisher: Publisher
}
```

The `publisher` field belongs to the `Publication` interface; a mapping for a field declared on an interface must use the GraphQL type that owns the field according to your application's schema and runtime wiring. If instead the schema declares the field separately on each object type, each mapping must specify its corresponding object type.

Unions do not declare common fields, so there is no direct field on a union to attach a batch mapping to. Clients must use fragments to access fields of member object types; batch mappings must target fields on the concrete object types or corresponding interfaces.

In complex polymorphic schemas, inspect the SDL and runtime type resolution before deciding `typeName`. Do not infer `typeName` solely from the returned Java class or collection type.

## 12. Testing typeName and batch mapping

You should test both the type/field mapping and that results are matched back to the right parents. Example using `GraphQlTester`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest({BookQueryController.class, BookBatchController.class})
class BookBatchMappingTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesAuthorForBookType() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

The example assumes the test context provides a mocked or test `BookService` and `AuthorService` bean with matching data. The test verifies the `Book.author` field is resolved. You can use Mockito to verify the batch service receives multiple IDs in a single call instead of being called separately per book.

You should add tests when:

- The Java source class name differs from the GraphQL `typeName`.
- The method name differs from the field and uses an explicit `field`.
- Two GraphQL types share the same field name with two separate batch mappings.
- The batch result is a Map and a source has no corresponding value.
- The batch result is a List and output ordering must be guaranteed.
- The SDL renames a type or field.
- The mapping is declared on an interface or a concrete object type.

## 13. Common pitfalls when configuring typeName

| Symptom | Cause | Solution |
| --- | --- | --- |
| Field is not batch-resolved | `typeName` does not match the type name in the SDL | Check the exact GraphQL type name and casing |
| Field is mapped to the wrong place | Using the return type name instead of the parent type | Locate the SDL block containing the field and use that block's name |
| Spring infers a non-existent type | Java source class name differs from GraphQL type name | Declare `typeName` explicitly |
| Method does not match the field | Method name differs from field but `field` was omitted | Specify `field` explicitly |
| Two mappings handle one field | Duplicate `@SchemaMapping` and `@BatchMapping` for the same type/field | Keep one appropriate resolver |
| Field unexpectedly returns null | Map key is not the source object or List is out of order | Match results to the exact source objects |
| Same-named field on multiple types is mixed up | Not differentiating parent types | Declare `typeName` for each mapping |

When diagnosing issues, open the SDL first and determine which type owns the field. Then compare the `typeName`/`field` pair in the annotation, check the batch method's source parameter, and confirm the controller is detected by Spring. This usually finds the issue faster than randomly modifying the service or DataLoader.

## 14. Checklist for choosing typeName

- Have you identified the exact GraphQL type containing the field to batch resolve?
- Does `typeName` match the type name in the SDL, including case?
- Can it be safely inferred from the source type of the collection parameter?
- Does the Java source class have a different name from the GraphQL type; if so, is it declared explicitly?
- Does `field` match the field name on that type, or does it need to be declared explicitly?
- Have you distinguished the parent type from the returned value type?
- When multiple types share a field name, does each mapping specify its proper `typeName`?
- Does a Map result use the exact source objects as keys, or does a List preserve exact source order?
- Is there any duplicate mapping with `@SchemaMapping` or another batch resolver?
- Do tests verify the exact type/field pair and results across multiple parents?

`typeName` in `@BatchMapping` identifies the GraphQL type that owns the field to batch resolve. Spring can infer the type name from the method's source type when Java and SDL names match; when using differently named DTOs/entities, multiple types with identically named fields, or when wanting explicit mappings, declare `typeName` explicitly. Combining the right `typeName`, `field`, and Map/List results matched to source objects ensures batch resolvers are attached at the right place in the schema and return accurate data for each parent.
