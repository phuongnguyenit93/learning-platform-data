# Inline Fragments When Querying in GraphQL

GraphQL **interfaces** and **unions** allow a field to return multiple concrete object types. When a client queries a field with such an abstract type, the selection set can only directly select fields exposed by that abstract type. To fetch fields specific to each object type, the client uses an **inline fragment** with the `... on TypeName` syntax.

Inline fragments enable a single query to handle multiple result types in the same response while keeping the schema clearly structured. In Spring for GraphQL, resolvers return the corresponding Java objects; the GraphQL runtime determines the concrete type to apply the matching fragment and return the selected fields.

## 1. Why Are Inline Fragments Needed?

Suppose a library API has two types of search results: books and articles. Both have an ID and a title, yet their specific fields differ:

- Books have `isbn` and `pages`.
- Articles have `source` and `publishedAt`.

The client wants to invoke a single search query and receive both result types. If the field returns a `SearchResult` interface, the client can select the interface's shared fields directly. When specific fields are needed, the client uses inline fragments.

~~~graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
    pages: Int!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
    publishedAt: String!
}

type Query {
    search: [SearchResult!]!
}
~~~

In this schema, `id` and `title` are fields of the `SearchResult` interface, so clients can select them directly. `isbn`, `pages`, `source`, and `publishedAt` exist only on the concrete object types, so fragments are needed to select them.

## 2. Inline Fragment Syntax

An inline fragment has the form:

~~~graphql
... on TypeName {
    fieldA
    fieldB
}
~~~

`TypeName` is a type condition. The fields inside the fragment are only applied when the actual object matches that type condition.

Example `search` query:

~~~graphql
query SearchLibrary {
    search {
        id
        title
        ... on Book {
            isbn
            pages
        }
        ... on Article {
            source
            publishedAt
        }
    }
}
~~~

When an element has the runtime type `Book`, GraphQL returns `id`, `title`, `isbn`, and `pages`. When an element has the runtime type `Article`, GraphQL returns `id`, `title`, `source`, and `publishedAt`.

The client does not need to send two separate requests for books and articles. A single query describes all fields to retrieve; GraphQL only executes the fragment matching each object in the result.

## 3. Interfaces and Directly Selectable Fields

An interface defines a set of fields that every implementing object type must provide. Therefore, clients can select shared fields directly on the interface without needing a fragment.

~~~graphql
query SearchLibrary {
    search {
        id
        title
        ... on Book {
            isbn
        }
        ... on Article {
            source
        }
    }
}
~~~

In this query:

- `id` and `title` are selected directly because they belong to `SearchResult`.
- `isbn` is selected only when the element is a `Book`.
- `source` is selected only when the element is an `Article`.

An interface can inherit from another interface, and an object type can implement multiple interfaces if the schema declares all required fields. The field selection rule remains the same: fields defined on the current static type can be selected directly; fields present only on concrete types must sit inside the corresponding fragment.

## 4. Unions Require Inline Fragments for Object Fields

A union represents one of several object types. Unlike an interface, a union does not define shared business fields. Hence, clients cannot select `id` or `title` directly from a union even if those fields exist on all member object types.

Union declaration:

~~~graphql
union CatalogItem = Book | Article

type Query {
    catalog: [CatalogItem!]!
}
~~~

Querying the union with inline fragments:

~~~graphql
query Catalog {
    catalog {
        __typename
        ... on Book {
            id
            title
            isbn
            pages
        }
        ... on Article {
            id
            title
            source
            publishedAt
        }
    }
}
~~~

`__typename` is a meta field provided by GraphQL that returns the actual object type name of each element. Clients can use this value to branch rendering or decode the response. It is also a useful way to retrieve common type information when querying a union.

You cannot write `catalog { id title }` if `catalog` has type `[CatalogItem!]!`, because the union does not declare those fields. Fields must be placed inside `... on Book` or `... on Article` fragments.

## 5. Combining Interfaces, Unions, and __typename

`__typename` can be selected on objects, interfaces, and unions. With an interface, clients can select shared fields and add `__typename` to identify the concrete object:

~~~graphql
query SearchLibrary {
    search {
        __typename
        id
        title
        ... on Book {
            isbn
        }
        ... on Article {
            source
        }
    }
}
~~~

Shortened example response:

~~~json
{
    "data": {
        "search": [
            {
                "__typename": "Book",
                "id": "book-101",
                "title": "GraphQL in Practice",
                "isbn": "978-604-000-001"
            },
            {
                "__typename": "Article",
                "id": "article-204",
                "title": "Modern API Design",
                "source": "Engineering Journal"
            }
        ]
    }
}
~~~

The response contains only the fields requested by the selection set. The `Book` element does not have `source`; the `Article` element does not have `isbn`. Clients should rely on `__typename` to determine the data branch and avoid assuming every element has the same specific fields.

## 6. Inline Fragments with Directives

You can combine fragments with `@include` or `@skip` directives to control field fetching based on query variables.

~~~graphql
query SearchLibrary($includeBookDetails: Boolean!) {
    search {
        __typename
        id
        title
        ... on Book @include(if: $includeBookDetails) {
            isbn
            pages
        }
        ... on Article {
            source
        }
    }
}
~~~

When `includeBookDetails` is `true`, the `isbn` and `pages` fields are fetched for `Book` elements. When `false`, this fragment is skipped. Directives do not alter the schema or type conditions; they only decide whether a selection is executed in the current operation.

Directives can also be placed on fields inside a fragment:

~~~graphql
... on Book {
    isbn
    pages @include(if: $includeBookDetails)
}
~~~

Use directives when clients genuinely need context-dependent field selection, such as a list screen and a detail screen sharing a single operation. Never use directives as a substitute for authorization; a client can write another query and request the field directly.

## 7. Inline Fragments vs. Named Fragments

GraphQL supports named fragments for reusing selection sets. Both inline fragments and named fragments can carry type conditions, though their declarations differ.

Inline fragment:

~~~graphql
query SearchLibrary {
    search {
        id
        ... on Book {
            isbn
            pages
        }
    }
}
~~~

Named fragment:

~~~graphql
query SearchLibrary {
    search {
        id
        ...BookDetails
    }
}

fragment BookDetails on Book {
    isbn
    pages
}
~~~

Comparison:

| Criterion | Inline Fragment | Named Fragment |
| --- | --- | --- |
| Syntax | `... on Book { ... }` | `...BookDetails` and a separate definition |
| Reuse scope | Right at the declaration site | Reusable across multiple selection sets matching the type condition |
| Readability | Convenient when the fragment is short and used once | Convenient when the selection is long or reused |
| Type condition | Located directly in the inline fragment | Located in the fragment definition |

Both approaches can be combined in the same query. For example, use a named fragment for shared `Book` fields and an inline fragment for a small field needed in just one place.

## 8. Nested Queries with Multi-Level Fragments

Type conditions can be used at multiple levels of a selection set. For example, a search returns `SearchResult`, and each `Book` has a `relatedItems` field returning a list of the `CatalogItem` union:

~~~graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
    pages: Int!
    relatedItems: [CatalogItem!]!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
}

union CatalogItem = Book | Article

type Query {
    search: [SearchResult!]!
}
~~~

Query with nested fragments:

~~~graphql
query SearchWithRelatedItems {
    search {
        __typename
        id
        title
        ... on Book {
            relatedItems {
                __typename
                ... on Book {
                    isbn
                    pages
                }
                ... on Article {
                    source
                }
            }
        }
        ... on Article {
            source
        }
    }
}
~~~

At the outer level, the fragments determine whether an element of `search` is a `Book` or an `Article`. Only when it is a `Book` does the client query `relatedItems`. At the inner level, each element of the union branches again by `Book` or `Article`.

Nested queries can increase query cost and the number of resolver invocations. When fragments select relational fields such as `relatedItems`, pay attention to batching, DataLoader, and depth and complexity limits to prevent N+1 issues or overly heavy queries.

## 9. Spring for GraphQL Returning Concrete Types for Interfaces and Unions

Inline fragments only work properly when the GraphQL runtime determines the actual object type. When a resolver returns a value whose static type is an interface or an abstract type, GraphQL Java needs a `TypeResolver` to map the Java object to an object type name in the schema.

Example Java models:

~~~java
import java.util.List;

public interface SearchResult {
    String id();
    String title();
}

public record Book(
        String id,
        String title,
        String isbn,
        int pages
) implements SearchResult {}

public record Article(
        String id,
        String title,
        String source,
        String publishedAt
) implements SearchResult {}

public interface SearchService {
    List<SearchResult> search();
}
~~~

Resolver returning multiple concrete objects:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search() {
        return searchService.search();
    }
}
~~~

Spring for GraphQL supports `ClassNameTypeResolver` to infer GraphQL object types from Java class names. The default behavior is convenient when concrete class names match object type names in SDL, such as Java class `Book` mapping to GraphQL type `Book`. If Java classes have different names or require custom rules, configure a `TypeResolver` in `RuntimeWiring` for the corresponding interface or union.

Example configuring an explicit mapping when Java classes have different names:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class GraphQlTypeResolverConfiguration {

    @Bean
    RuntimeWiringConfigurer searchTypeResolverConfigurer() {
        ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
        typeResolver.addMapping(BookView.class, "Book");
        typeResolver.addMapping(ArticleView.class, "Article");

        return wiring -> wiring
                .typeResolver("SearchResult", typeResolver)
                .typeResolver("CatalogItem", typeResolver);
    }
}
~~~

`BookView` and `ArticleView` here are application Java classes; their names can differ from the GraphQL object types `Book` and `Article`. If class names already match the schema and the default resolver works properly, you do not need to register custom mappings.

## 10. Testing Inline Fragments with GraphQlTester

You should verify that the query returns the right fields per concrete type and that `__typename` has the expected value.

Example test for the `SearchResult` interface:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@GraphQlTest(SearchController.class)
class InlineFragmentTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    SearchService searchService;

    @Test
    void resolvesFieldsForEachConcreteType() {
        given(searchService.search()).willReturn(List.of(
                new Book("book-101", "GraphQL in Practice", "978-604-000-001", 320),
                new Article("article-204", "Modern API Design",
                        "Engineering Journal", "2026-11-20")
        ));

        graphQlTester.document("""
                query {
                    search {
                        __typename
                        id
                        ... on Book {
                            isbn
                        }
                        ... on Article {
                            source
                        }
                    }
                }
                """)
            .execute()
            .path("search[0].isbn")
            .entity(String.class)
            .isEqualTo("978-604-000-001");

        graphQlTester.document("""
                query {
                    search {
                        __typename
                        ... on Article {
                            source
                        }
                    }
                }
                """)
            .execute()
            .path("search[1].source")
            .entity(String.class)
            .isEqualTo("Engineering Journal");
    }
}
~~~

This test illustrates checking one `Book` result and one `Article` result. `SearchService` is a dependency mocked with `@MockitoBean`; `Book`, `Article`, and `SearchService` must reside in the test package or be imported from their packages. The test slice must also retain the type resolver configuration if the application uses custom mappings.

For unions, add similar tests to confirm each member object type resolves properly and fields appear only in matching fragments. If a query fails with an error such as "Could not determine type" or an abstract type resolution error, check `TypeResolver` before checking the selection set.

## 11. Common Mistakes When Using Inline Fragments

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Field not recognized on interface | Field exists only on a concrete object type | Place the field inside `... on ConcreteType` |
| Union query reports field does not exist | Union declares no shared business fields | Use inline fragments for each member type and select `__typename` if distinguishing is needed |
| Fragment does not run for an element | Runtime object type does not match the type condition | Check the concrete type and `TypeResolver` |
| GraphQL cannot resolve abstract type | Missing or misconfigured `TypeResolver` | Configure the interface/union mapping to GraphQL object types |
| Specific field returns null or errors | Concrete type's resolver/property fetcher does not provide that field | Check the Java model, getter/record accessor, and field mapping |
| Nested fragments slow down the query | Selection set traverses deeply across many relations | Use DataLoader/batching and limit query complexity/depth |
| Using fragments as a security mechanism | Assuming a field is protected if the client does not query the fragment | Enforce authorization in resolvers/services or via field-level security |

## 12. Security and Performance When Selecting Fields via Fragments

Inline fragments only determine which fields are selected based on runtime type. They are not an authorization mechanism. If `Book` has an `internalNotes` field, placing that field inside a fragment does not prevent another client from writing its own query to request it.

For sensitive fields, check permissions in resolvers or the service layer. You can apply method security, inspect the principal in `GraphQLContext`, or use Spring Security's field-level security mechanisms. Access permissions must be verified per request and per resource.

Fragments also do not automatically reduce resolver calls. When a fragment selects relational fields such as `Book.author` or `Book.relatedItems`, GraphQL still executes the corresponding data fetchers for matching objects. Use `@BatchMapping`, DataLoader, or service-layer batching to prevent N+1 queries, and limit operation depth and complexity.

## 13. Workflow for Writing Queries with Inline Fragments

When querying a field that returns an interface or union, you can follow these steps:

1. Check whether the field returns an interface or a union and identify the object types that may appear.
2. Directly select fields declared on the interface; for a union, start with `__typename`.
3. Add `... on TypeName` for fields that exist only on each concrete object type.
4. Use named fragments if the selection set is long or reused; use inline fragments for short, local branches.
5. Add directives such as `@include` or `@skip` when controlling fields via query variables.
6. Verify that the GraphQL runtime determines the right concrete type using `TypeResolver`.
7. Test each type branch, specific fields, access permissions, and resolver cost.

Inline fragments are GraphQL's explicit way of expressing fields that depend on the actual object type. When combined properly with interfaces, unions, `__typename`, and type resolution in Spring for GraphQL, clients can retrieve multiple shapes of data in a single query while keeping selection sets schema-safe.

## References

- [GraphQL Specification — Type Refinement](https://spec.graphql.org/October2021/#sec-Type-Refinement)
- [GraphQL Specification — Interfaces](https://spec.graphql.org/October2021/#sec-Interfaces)
- [GraphQL Specification — Unions](https://spec.graphql.org/October2021/#sec-Unions)
- [Spring for GraphQL — Request Execution and Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
