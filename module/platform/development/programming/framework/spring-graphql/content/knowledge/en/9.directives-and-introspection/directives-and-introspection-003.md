# Built-in @include

In GraphQL, the `@include` directive allows a client to decide whether a field or part of a selection set is included in the result based on a Boolean condition. This directive is useful when a UI has optional data sections, such as loading a detailed description only when a user expands a product or fetching contact details only when the screen needs to display them.

`@include` is a built-in GraphQL directive. The GraphQL engine evaluates the condition during operation execution; a Spring for GraphQL application does not need a separate Java annotation or resolver for this directive. A field's resolver is executed only when the field remains selected after conditional directives are applied.

## 1. Syntax of @include

Basic syntax:

```graphql
fieldName @include(if: Boolean!)
```

The directive takes a single argument named `if` of type `Boolean!`:

- If `if` is `true`, the field or selection is kept for execution.
- If `if` is `false`, the field or selection is omitted from the operation being executed.
- If the value cannot be coerced to a Boolean or is `null`, the request is invalid because the argument requires `Boolean!`.

Simple example:

```graphql
query {
    product(id: "p-101") {
        id
        name
        description @include(if: true)
    }
}
```

Because the condition is `true`, the `description` field is included in the response. If changed to `false`, that field is skipped for that execution.

The directive can be attached to a field, fragment spread, or inline fragment. It is an executable directive, meaning a directive used in a GraphQL operation. `@include` is not a directive for configuring schema types or declaring field metadata in SDL.

## 2. Using Variables to Control Fields

In real-world applications, the condition typically depends on UI state or user choices. Using variables lets you reuse the same query document with different values.

```graphql
query ProductDetail($id: ID!, $showDescription: Boolean!) {
    product(id: $id) {
        id
        name
        description @include(if: $showDescription)
    }
}
```

Variables when a detailed description is needed:

```json
{
  "id": "p-101",
  "showDescription": true
}
```

Variables when only summary information is needed:

```json
{
  "id": "p-101",
  "showDescription": false
}
```

With `true`, the response might be:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "description": "A compact keyboard for everyday work."
    }
  }
}
```

With `false`, the response does not contain the `description` key:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard"
    }
  }
}
```

The key point to remember is that a field excluded from the selection set is not returned as a field with a `null` value. The field's key does not appear in the response unless another selection with the same response key still requests that field.

## 3. @include on Nested Fields

The directive can be applied to any field in the selection set. This lets clients toggle individual parts of the data on or off without creating multiple nearly identical queries.

```graphql
query CustomerDetail(
    $id: ID!
    $includeContact: Boolean!
    $includeOrders: Boolean!
) {
    customer(id: $id) {
        id
        name
        email @include(if: $includeContact)
        phone @include(if: $includeContact)
        orders @include(if: $includeOrders) {
            id
            status
            total
        }
    }
}
```

This example allows a profile screen to load only the customer's ID and name. When the user opens the contact section, the client sends `includeContact: true`; when opening order history, the client sends `includeOrders: true`.

Conditions apply independently to each field. If `includeOrders` is `false`, the `orders` field is skipped and its resolver does not need to run. The `id` and `name` fields still execute normally.

## 4. Using @include on a Fragment Spread

When a group of fields is usually toggled together, placing the directive on a fragment spread keeps the query cleaner.

```graphql
fragment CustomerContact on Customer {
    email
    phone
    address {
        street
        city
    }
}

query CustomerDetail($id: ID!, $showContact: Boolean!) {
    customer(id: $id) {
        id
        name
        ...CustomerContact @include(if: $showContact)
    }
}
```

If `showContact` is `false`, none of the selections in `CustomerContact` are executed at that fragment spread location. When `true`, the fragment's fields are expanded into the selection set and executed according to normal rules.

Directives on fragment spreads are especially useful when a fragment contains many nested fields or is shared across multiple queries. Clients can reuse the fragment without duplicating the selection set.

## 5. Using @include on an Inline Fragment

Inline fragments are commonly used with interfaces or unions to select fields based on the concrete object type. You can combine them with `@include` to fetch polymorphic data only when needed.

```graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    author: String!
}

type Author implements SearchResult {
    id: ID!
    title: String!
    biography: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

A client can request type-specific fields conditionally:

```graphql
query Search($keyword: String!, $showExtra: Boolean!) {
    search(keyword: $keyword) {
        id
        title
        ... on Book @include(if: $showExtra) {
            author
        }
        ... on Author @include(if: $showExtra) {
            biography
        }
    }
}
```

When `showExtra` is `false`, both inline fragments are excluded from the selection. When `true`, the fragment matching each result's concrete type is applied. `@include` does not change an object's actual type and does not turn a `Book` into an `Author`.

## 6. Combining @include with @skip

GraphQL has two built-in conditional directives that are often used together:

- `@include(if: Boolean!)`: includes the selection only when the condition is `true`.
- `@skip(if: Boolean!)`: excludes the selection when the condition is `true`.

The two directives express opposite perspectives of the same need. For example:

```graphql
query ProductDetail($showDescription: Boolean!) {
    product(id: "p-101") {
        id
        name
        description @include(if: $showDescription)
        internalCode @skip(if: $showDescription)
    }
}
```

In the example above, the product description is fetched when `showDescription` is `true`, while `internalCode` is fetched when that condition is `false`.

Both `@include` and `@skip` can be placed on the same selection. The selection is executed only when all conditions allow it: `@include` must receive `true` and `@skip` must receive `false`. If either condition excludes the selection, the field is skipped.

Avoid overusing multiple conditions on the same field if a single clearly named Boolean variable suffices to express the intent. Readable queries help clients and operators understand the exact expected response.

## 7. Distinguishing Skipped Fields, Null, and Empty Lists

These three states have different meanings:

| State | Meaning | Response Example |
| --- | --- | --- |
| Field omitted by `@include` | Client did not request the field in this operation | No `description` key |
| Field executed and returned null | Resolver returned null or data has no value, if schema allows | `"description": null` |
| Field executed and returned an empty list | Field was requested and the result has zero elements | `"orders": []` |

Clients should not interpret a missing field as if the server confirmed the field's value is null or an empty list. A field may be omitted because the `@include` condition was false, or because it was never selected in the operation in the first place.

If a field is skipped due to a directive, the server has no opportunity to resolve that field during the current execution. This differs from a resolver running and explicitly returning null.

## 8. How @include Affects Resolver Execution

Conditional directives are evaluated by the GraphQL engine during field collection for execution. A selection excluded by `@include(if: false)` is not added to the set of fields to resolve at that location.

This can reduce unnecessary work, especially when a field requires a database query, an external service call, or expensive computation. However, do not assume every query cost drops proportionally with the number of hidden fields:

- The query parser and validation still have to process the document.
- Depth or complexity analyzers may calculate cost conservatively without evaluating runtime conditions.
- A field with the same response key might still be requested by another selection.
- Parent resolvers still need to run to produce the object containing nested selections.

Therefore, measure execution cost rather than just counting fields in the response. If query cost is used to protect the server, configure limit policies to match how the cost analyzer handles directives.

## 9. Using @include with Spring for GraphQL

Spring for GraphQL uses GraphQL Java to parse, validate, and execute operations. Because `@include` is a standard GraphQL directive, it is handled automatically. There is no need to declare `@IncludeMapping`, `@SchemaMapping`, or a custom resolver for the directive.

Example SDL:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    description: String
}
```

Controller handling the root field:

```java
package com.example.graphql.product;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }
}
```

Client sends operation:

```graphql
query ProductDetail($id: ID!, $showDescription: Boolean!) {
    product(id: $id) {
        id
        name
        description @include(if: $showDescription)
    }
}
```

Spring still maps the root `product` field to the `@QueryMapping product` method. The `description` field is resolved via the default mechanism from the object's property/accessor or the corresponding resolver if the application defined one. When `showDescription` is `false`, GraphQL skips the `description` selection; there is no need to check `showDescription` in the controller to manually build the response.

If you need to avoid loading description data from the database, design appropriate data access or projections. `@include` prevents the field resolver from running, but if the parent resolver already fetched the entire entity including its description, that data may already have been retrieved before GraphQL skips the child field.

## 10. Testing @include Conditions with GraphQlTester

You can test the same document with two different variable values. For example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void includesDescriptionWhenRequested() {
        graphQlTester.document("""
                query ProductDetail($id: ID!, $showDescription: Boolean!) {
                    product(id: $id) {
                        id
                        description @include(if: $showDescription)
                    }
                }
                """)
            .variable("id", "p-101")
            .variable("showDescription", true)
            .execute()
            .path("product.description")
            .entity(String.class)
            .isEqualTo("A compact keyboard.");
    }

    @Test
    void omitsDescriptionWhenNotRequested() {
        graphQlTester.document("""
                query ProductDetail($id: ID!, $showDescription: Boolean!) {
                    product(id: $id) {
                        id
                        description @include(if: $showDescription)
                    }
                }
                """)
            .variable("id", "p-101")
            .variable("showDescription", false)
            .execute()
            .path("product.description")
            .pathDoesNotExist();
    }
}
```

The example above assumes the test has a product fixture `p-101` with a known description and provides a mock or test bean for `ProductService`. The first test verifies that the field has data when the condition is true; the second test verifies that the response path does not exist when the condition is false. You can add service or repository interaction checks to confirm an expensive field resolver is not called when the selection is excluded.

For queries using fragments, write tests for both the case where the fragment is included and the case where it is skipped. For operations containing both `@include` and `@skip`, test Boolean combinations to avoid inverted conditions.

## 11. Limitations and Common Pitfalls

| Issue | Cause | How to Fix |
| --- | --- | --- |
| Using `@include` without passing the `if` argument | The argument is required | Declare and pass `Boolean!` |
| Passing null for `if` | `Boolean!` does not accept null | Send `true` or `false` |
| Expecting the field to appear with null when the condition is false | Confusing omission with null | Check for the presence of the response key |
| Attaching the directive to an unsupported location | `@include` only has specific executable locations | Use on a field, fragment spread, or inline fragment |
| Using the directive to protect sensitive fields | Clients can send a query without the directive | Perform authorization on the server |
| Assuming an omitted field incurs zero cost | Parent resolvers, parsing, and validation may still run | Measure queries and design projections/data access |
| Using multiple hard-to-read conditions | Query is difficult to maintain | Name variables after UI meaning and simplify selections |

`@include` is not a mechanism for filtering records in a list. If a query returns `[Product!]!`, a directive on the `description` field determines whether to fetch descriptions for the products; it does not remove products from the list. To filter records, use field arguments or appropriate data query rules.

## 12. Checklist for Using @include

- Does the condition use the `Boolean!` type?
- Does the variable name clearly describe the UI section or data to toggle?
- Have you distinguished omitted fields from null fields or empty lists?
- Is the directive placed at a valid location: field, fragment spread, or inline fragment?
- Should it be applied to an entire fragment instead of repeating on individual fields?
- Does the query combine `@skip` in an easy-to-understand way?
- Are access permissions still checked on the server when clients modify conditions?
- Have both true and false cases been tested?
- Is a parent resolver loading unnecessary data before the directive excludes a child field?

`@include` helps clients control selection sets using a Boolean condition directly in the GraphQL document. It makes responses flexible, reduces loading and resolving unnecessary fields, and lets one query be reused across multiple UI states. In Spring for GraphQL, the directive is handled automatically by the GraphQL runtime; the application still needs efficient data access design, server-side permission checks, and tests for both condition branches.
