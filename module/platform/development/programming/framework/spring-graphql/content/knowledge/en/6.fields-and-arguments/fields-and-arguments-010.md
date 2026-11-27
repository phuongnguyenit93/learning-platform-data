# Inline Fragments

GraphQL lets clients select fields according to the data structure published by the server. For a concrete object type, the client can select the object's fields directly. However, when a field returns an interface or union, the actual object type is only determined at execution time. The client needs a way to request fields specific to each concrete type. **Inline fragments** handle this situation by constraining a selection set to a specific data type.

Inline fragments are especially useful when an API returns search results containing multiple object types, or when a field returns an interface with multiple implementations. In Spring for GraphQL, inline fragments are client-side syntax; the server needs to declare the schema accurately, return matching Java objects, and configure a type resolver so GraphQL can identify the concrete type when needed.

## Basic syntax

An inline fragment uses three dots, followed by a type condition and a selection set:

~~~graphql
... on Book {
  id
  title
}
~~~

The **on Book** part is the type condition. It specifies that the inner fields are selected only when the object being processed has the concrete type Book. If the object has another type, this branch does not apply.

An operation can have multiple inline fragments:

~~~graphql
query SearchCatalog($text: String!) {
  search(text: $text) {
    ... on Book {
      id
      title
    }
    ... on Author {
      id
      name
    }
  }
}
~~~

If search returns a Book, GraphQL retrieves id and title. If it returns an Author, GraphQL retrieves id and name. The client describes both possibilities in a single operation without having to call a separate endpoint for each result type.

## Why are inline fragments needed?

An object type has fixed fields. Interfaces and unions, however, describe a value that can be one of multiple object types:

- **Interfaces** specify shared fields that implementing object types must provide.
- **Unions** allow a field to return one of several object types without requiring them to share fields.

With an interface, clients can select fields from the shared contract directly. With a union, clients can only select special GraphQL-supported fields on the union directly, such as __typename; fields of each concrete object must be selected inside an inline fragment.

Example schema for a book catalog:

~~~graphql
interface Node {
  id: ID!
}

type Book implements Node {
  id: ID!
  title: String!
  author: Author
}

type Author implements Node {
  id: ID!
  name: String!
  books: [Book!]!
}

union SearchResult = Book | Author

type Query {
  node(id: ID!): Node
  search(text: String!): [SearchResult!]!
}
~~~

Book and Author both implement Node, so both have the id field. However, title exists only on Book, while name exists only on Author. The SearchResult union allows search results to contain both books and authors.

## Inline fragments with interfaces

When a field returns an interface, clients can query shared fields without a fragment. Inline fragments are used when selecting fields that exist only on a specific implementation:

~~~graphql
query FindNode($id: ID!) {
  node(id: $id) {
    id
    __typename
    ... on Book {
      title
      author {
        id
        name
      }
    }
    ... on Author {
      name
      books {
        id
        title
      }
    }
  }
}
~~~

The id field is declared on Node so it can be selected directly. The title and author fields exist only on Book; name and books exist only on Author, so they must be placed inside their respective branches.

If node returns a Book, the response may look like this:

~~~json
{
  "data": {
    "node": {
      "id": "book-101",
      "__typename": "Book",
      "title": "Spring in Action",
      "author": {
        "id": "author-12",
        "name": "Craig Walls"
      }
    }
  }
}
~~~

If node returns an Author, GraphQL applies the Author branch. Fields outside the matching branch will not appear in the response. Thus, the client receives exact data for the actual type without guessing from nullable fields.

## Inline fragments with unions

Unions do not define shared business fields. Therefore, clients cannot write id, title, or name directly on SearchResult even though its member object types may contain those fields. Use inline fragments instead:

~~~graphql
query Search($text: String!) {
  search(text: $text) {
    __typename
    ... on Book {
      id
      title
      author {
        name
      }
    }
    ... on Author {
      id
      name
      books {
        id
        title
      }
    }
  }
}
~~~

Suppose the results contain one book and one author; the response can be:

~~~json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-101",
        "title": "Spring in Action",
        "author": {
          "name": "Craig Walls"
        }
      },
      {
        "__typename": "Author",
        "id": "author-20",
        "name": "Jane Doe",
        "books": [
          {
            "id": "book-202",
            "title": "Reactive Systems"
          }
        ]
      }
    ]
  }
}
~~~

Each element has a different structure because GraphQL executes only the selection set matching that element's concrete type. Fragment branches are not list filter conditions; they do not exclude non-matching objects from the result. They only decide which fields are fetched for each object.

## The __typename field

**__typename** is a meta-field provided by GraphQL. It returns the name of the concrete object type being processed, such as Book or Author. Clients can select __typename on an object, interface, or union without declaring it in the schema.

__typename is often used alongside inline fragments because clients can rely on it to distinguish result types:

~~~graphql
query Search($text: String!) {
  search(text: $text) {
    __typename
    ... on Book {
      title
    }
    ... on Author {
      name
    }
  }
}
~~~

On the frontend, __typename is helpful for rendering the right component, distinguishing cached entries, or handling polymorphic search results. For example, the client can render BookCard when __typename is Book and AuthorCard when __typename is Author.

Do not use __typename as an authorization mechanism. This value only indicates the type of object returned; permission to read fields or objects must still be checked on the server.

## Inline fragments without a type condition

GraphQL also allows inline fragments without **on Type**. This syntax groups fields into a selection set and lets you attach a directive to the whole group:

~~~graphql
query BookDetails($id: ID!, $includeReviews: Boolean!) {
  book(id: $id) {
    id
    title
    ... @include(if: $includeReviews) {
      reviews {
        id
        rating
      }
    }
  }
}
~~~

In this example, the branch without a type condition still applies to the same Book object. The @include directive instructs GraphQL to execute the reviews field group only when the includeReviews variable is true. The @skip directive has the opposite effect: skipping the selection when its condition is true.

Inline fragments without a type condition are useful when you want to apply a directive to a group of fields without repeating the directive on every field. When a type condition is present, the fragment also selects fields by concrete object type.

## Distinguishing inline fragments from named fragments

A named fragment is a named selection set that can be reused across multiple places. An inline fragment writes the selection set directly in place:

~~~graphql
fragment BookSummary on Book {
  id
  title
}

query Search($text: String!) {
  search(text: $text) {
    ...BookSummary
    ... on Author {
      id
      name
    }
  }
}
~~~

In the example, BookSummary is a named fragment that can be reused across many operations or selection sets. The Author branch is an inline fragment because its selection set is declared only at the site of use.

| Criterion | Inline fragment | Named fragment |
| --- | --- | --- |
| Invocation | Writes the selection set directly after three dots | Uses a fragment spread with the fragment name |
| Reusability | Typically used in one place | Can be used in multiple places |
| Type condition | Optional | Required |
| Best suited for | Short, single-use branches or directive-grouped fields | Field groups shared across multiple queries |

Both forms are validated by GraphQL against the schema. A fragment must have a type condition compatible with the parent type at the usage site; GraphQL rejects the operation if the two type sets cannot intersect.

## Combining inline fragments with directives

The standard directives @include and @skip can be attached to inline fragments to enable or skip a branch based on a variable:

~~~graphql
query Search(
  $text: String!
  $showBookDetails: Boolean!
  $showAuthorDetails: Boolean!
) {
  search(text: $text) {
    __typename
    ... on Book @include(if: $showBookDetails) {
      id
      title
    }
    ... on Author @include(if: $showAuthorDetails) {
      id
      name
    }
  }
}
~~~

Clients can tailor field groups to screen needs without building many nearly identical operations. However, directives do not replace pagination or query complexity limits. The server still needs to control execution cost and verify access permissions for every selected field.

## How does GraphQL determine the concrete type?

When a resolver returns a concrete object type directly such as Book, GraphQL already knows the concrete type from the field declaration. However, for an interface or union, GraphQL only knows that the field returns an abstract type. At execution time, the runtime must determine which GraphQL object type the current Java object corresponds to.

GraphQL Java uses a **TypeResolver** for interfaces and unions. A type resolver takes the source object and determines the concrete GraphQL object type. Spring for GraphQL provides **ClassNameTypeResolver** to map Java classes to object type names; explicit mappings can be declared to avoid relying on class-name conventions.

Example Java model:

~~~java
public interface SearchResult {
}

public record Book(String id, String title) implements SearchResult {
}

public record Author(String id, String name) implements SearchResult {
}
~~~

Search resolver returning a list of concrete objects:

~~~java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search(@Argument String text) {
        return searchService.search(text);
    }
}
~~~

Registering the type resolver for the interface and union:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlTypeConfiguration {

    @Bean
    RuntimeWiringConfigurer typeResolverConfigurer() {
        ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
        typeResolver.addMapping(Book.class, "Book");
        typeResolver.addMapping(Author.class, "Author");

        return builder -> {
            builder.typeResolver("Node", typeResolver);
            builder.typeResolver("SearchResult", typeResolver);
        };
    }
}
~~~

In this configuration, when the runtime encounters Book, the resolver returns the GraphQL object type Book; when it encounters Author, it returns Author. The same type resolver can be registered for the Node interface and SearchResult union if both abstract types share matching member object types. For more complex models, you can write a custom TypeResolver to decide the type based on class, a discriminator property, or domain rules.

Names in the mapping must match the object types in SDL. Member objects must also belong to the possible types of the interface or union. If the type resolver returns an invalid type or cannot determine a concrete type, GraphQL cannot finish executing the inline fragment branches as expected.

## Operation checks and common errors

Inline fragments are validated before resolvers execute. Common errors include:

- Using a field that does not exist on the object type in the type condition.
- Writing a type condition that is not in the possible types of the interface or union.
- Selecting a member-specific field directly on a union instead of inside an inline fragment.
- Returning a Java object from a resolver that has no mapping to a concrete GraphQL type.
- Declaring an interface or union in SDL without registering an appropriate runtime type resolver.

Invalid example:

~~~graphql
query Search {
  search(text: "Spring") {
    title
  }
}
~~~

If search returns the SearchResult union, title is not a direct field of the union. The correct way is:

~~~graphql
query Search {
  search(text: "Spring") {
    ... on Book {
      title
    }
  }
}
~~~

When debugging, inspect the schema, the Java type returned by the resolver, the TypeResolver configuration, and the operation sent by the client in order. You can add __typename to the selection set to observe which object type the runtime is returning.

## Security and performance when using inline fragments

Inline fragments only select fields based on object type. They do not automatically check user permissions and do not make sensitive fields safe. Fields in every branch still need protection via Spring Security, method security, permission checks in resolvers or services, and appropriate data access conditions.

An operation with multiple fragment branches can request many nested fields. The server must still account for depth, complexity, pagination, batching, and execution time. Do not treat a fragment branch skipped by the client as the sole resource-limiting mechanism; configure query limits at runtime or at the gateway according to application policy.

When testing a GraphQL API with Spring for GraphQL, cover returning each concrete type, returning null for the interface or union if the schema allows it, matching fragment branches, non-matching branches, toggling directives, and type resolution errors. With GraphQlTester, you can assert __typename and paths of each element to confirm the data has the right type.

Inline fragments help clients consume polymorphic schemas safely and clearly. Type conditions determine which fields are selected per object, __typename reveals the concrete type, and TypeResolver helps GraphQL Java recognize the corresponding Java object. When schema, resolvers, and type mappings are consistent, Spring for GraphQL can return diverse data structures in a single operation while maintaining a strongly typed API contract.
