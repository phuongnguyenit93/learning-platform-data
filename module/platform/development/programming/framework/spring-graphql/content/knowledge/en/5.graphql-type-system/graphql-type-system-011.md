# Nested list types in GraphQL

In GraphQL SDL, a **list type** represents a list of values. A list can contain scalars, enums, or object types; an element of a list can also be another list. When lists are nested, the schema describes multi-level data such as matrices, products grouped by category, data tables, or grouped result sets.

The key when declaring nested lists is understanding two layers of rules: square brackets `[]` define the list structure, while the exclamation mark `!` specifies which positions are not allowed to be `null`. These two rules compose recursively at each level of the list.

## Basic list types

GraphQL uses square brackets to declare a list:

```graphql
type Query {
  productIds: [ID]
  names: [String!]
  products: [Product!]
}
```

The declarations above mean:

- `[ID]`: the field can return `null` or a list; each ID element can also be `null`.
- `[String!]`: the field can be `null`, but if a list is returned, every element must be a non-null string.
- `[Product!]`: the field can be `null`; every element in the list must be a valid `Product`.

Lists preserve the element order returned by the server. GraphQL does not automatically deduplicate elements, nor does it impose an element count limit by itself. When there is no data, the server typically returns an empty list `[]`; an empty list is distinct from `null`.

## How to read nested list types

A nested list is declared by placing one list type inside another list type. Example:

```graphql
type Query {
  matrix: [[Int]]
}
```

`[[Int]]` is an outer list where each element of the outer list is itself a list of integers. A matching value might be:

```json
{
  "data": {
    "matrix": [
      [1, 2, 3],
      [4, 5, 6],
      [7, 8, 9]
    ]
  }
}
```

You can read the type from the outside in:

1. Outermost `[...]`: list of rows.
2. Inner `[...]`: each row is a list.
3. `Int`: each element in a row is an integer.

GraphQL allows multiple levels of nesting, such as `[[[String!]!]!]!`. Each pair of square brackets introduces a list layer. However, a nested list only describes nested structure; it does not guarantee that rows have equal length, a fixed row count, or that the data forms a rectangular matrix. Those constraints must be validated at the business layer.

## Combining lists with Non-Null

The `!` modifier can be placed after the element type or after a closing bracket. Its placement determines exactly which values may be null.

For a one-dimensional list, the four common forms are:

| SDL | Can the list be null? | Can elements be null? |
| --- | --- | --- |
| `[Int]` | Yes | Yes |
| `[Int]!` | No | Yes |
| `[Int!]` | Yes | No |
| `[Int!]!` | No | No |

Examples:

- `[Int]!` requires the resolver to return a list. The list may contain `null`, such as `[1, null, 3]`.
- `[Int!]` allows the whole field to be `null`, but if a list is present, its elements must be integers, such as `[1, 2, 3]`.
- `[Int!]!` requires both the list and every element to be non-null.

For nested lists, the same rules apply at each level:

| SDL | Meaning |
| --- | --- |
| `[[Int]]` | Outer list can be null; inner lists can be null; Int elements can be null. |
| `[[Int]!]!` | Outer list and every inner list cannot be null; Int elements can be null. |
| `[[Int!]]!` | Outer list cannot be null; inner lists can be null; Int elements cannot be null. |
| `[[Int!]!]` | Outer list can be null; inner lists and every Int element cannot be null. |
| `[[Int!]!]!` | Outer list, every inner list, and every Int element cannot be null. |

For example, `[[Int!]!]!` can be read as:

1. The final `!`: the outer list must exist.
2. The `!` right after the inner `]`: each element of the outer list must be a non-null inner list.
3. The `!` after `Int`: every integer in each inner list cannot be null.

```graphql
type Query {
  strictMatrix: [[Int!]!]!
  flexibleMatrix: [[Int!]]!
}
```

`strictMatrix` permits no nulls at any level. `flexibleMatrix` requires the outer list to exist and every integer to have a value, while allowing an element of the outer list to be a `null` inner list.

## Nested list examples in real schemas

### Number matrix

An analytics API might return rows of metrics:

```graphql
type Query {
  salesByMonth: [[Float!]!]!
}
```

Illustrative response:

```json
{
  "data": {
    "salesByMonth": [
      [120.5, 132.0, 128.75],
      [140.0, 151.25, 149.5]
    ]
  }
}
```

In this example, each row is a group of figures. The SDL type guarantees no list or numeric element is null, but does not require each month to have exactly three values. If business rules require every row to have the same number of columns, the service must check that condition before returning the data.

### Grouping objects by category

Nested lists can also hold object types instead of scalars:

```graphql
type Product {
  id: ID!
  name: String!
  price: Float!
}

type Query {
  productGroups: [[Product!]!]!
}
```

Each element of the outer list is a product group; each group is a list of `Product` items. This pattern can represent groups partitioned by region, price tier, or another business criterion.

When a client queries `productGroups`, the client still must select the fields of `Product`:

```graphql
query ProductGroups {
  productGroups {
    id
    name
    price
  }
}
```

GraphQL applies the selection set to every object across all inner lists. If fields of `Product` require dedicated resolvers, field mapping still applies to each corresponding object.

## Nested lists in input

List types do not appear only in output. GraphQL also supports nested lists in field arguments and input objects. For example, a client sends a matrix of numbers for the server to compute:

```graphql
input MatrixInput {
  values: [[Int!]!]!
}

type Mutation {
  calculateMatrix(input: MatrixInput!): MatrixSummary!
}

type MatrixSummary {
  rowCount: Int!
  columnCount: Int!
  total: Int!
}
```

Clients can send variables like this:

```graphql
mutation Calculate($input: MatrixInput!) {
  calculateMatrix(input: $input) {
    rowCount
    columnCount
    total
  }
}
```

```json
{
  "input": {
    "values": [
      [1, 2, 3],
      [4, 5, 6]
    ]
  }
}
```

The type `[[Int!]!]!` requires the input to contain an outer list, each row to be a non-null list, and each element to be a non-null Int. If the client sends `null` at any level declared Non-Null, GraphQL rejects the input before the resolver executes.

### Singleton-to-list coercion rule

GraphQL has an input coercion rule for lists: when a non-list input value is provided for a list-typed position, that value can be coerced into a single-element list after coercing the element value according to the inner type.

For example, the following field declares a list of strings:

```graphql
type Query {
  search(tags: [String!]!): [String!]!
}
```

A client can pass a single string as the `tags` argument; GraphQL treats it as a single-element list equivalent to `["graphql"]`. Even so, when writing clients and variables, send the array form explicitly so the payload clearly reflects the expected data structure.

This coercion rule only provides flexibility in representing input. It does not bypass nullability constraints, nor does it automatically validate business conditions such as row counts, column counts, or matrix size limits.

## Null propagation when a nested list element fails

Nullability directly affects how GraphQL handles errors during resolution. If a resolver returns `null` at a position declared Non-Null, GraphQL raises an execution error and bubbles the null up to the nearest nullable parent position.

For lists, if a non-nullable element fails, the entire list containing that element becomes null. If that list itself is also non-nullable, null continues propagating up to its parent level. This rule repeats across each layer of a nested list.

Consider two fields:

```graphql
type Query {
  strictMatrix: [[Int!]!]!
  tolerantMatrix: [[Int!]]!
}
```

Suppose an integer in the second row fails to resolve:

- For `strictMatrix`, the non-nullable Int element turns the second row's list into null. Because that row is also a non-nullable element of the outer list, the outer list becomes null. Since the outer list is non-nullable as well, null continues propagating to the root response.
- For `tolerantMatrix`, the non-nullable Int element turns the second row's list into null. However, the outer list permits null inner-list elements, so the remaining rows can still be returned.

An illustrative response for the second case might be:

```json
{
  "data": {
    "tolerantMatrix": [
      [1, 2, 3],
      null,
      [7, 8, 9]
    ]
  },
  "errors": [
    {
      "message": "Could not compute value at cell",
      "path": ["tolerantMatrix", 1, 0]
    }
  ]
}
```

`path` points to the field, row index, and element index that caused the error. When null stops at a nullable field, the rest of the data can be preserved. If null reaches the query root because the root field is non-nullable, `data` can become `null` as a whole. Clients should read both `data` and `errors` to handle partial data.

## Mapping nested lists in Spring for GraphQL

With Spring for GraphQL, nested lists in SDL typically map naturally to nested Java collection types. Example schema:

```graphql
type Query {
  matrix: [[Int!]!]!
}
```

The controller can return `List<List<Integer>>`:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MatrixController {

    @QueryMapping
    public List<List<Integer>> matrix() {
        return List.of(
            List.of(1, 2, 3),
            List.of(4, 5, 6),
            List.of(7, 8, 9)
        );
    }
}
```

GraphQL Java processes nested collections according to the list types declared in the schema. The Java types must align with SDL nullability: if the schema uses `!`, the resolver must ensure no null is returned at that corresponding position. `Integer` is a boxed type and can represent null; the primitive type `int` cannot represent null.

For input, nested lists can be received with `@Argument`:

```java
@MutationMapping
public MatrixSummary calculateMatrix(@Argument MatrixInput input) {
    return matrixService.calculate(input.values());
}
```

In this example, `MatrixInput` is an application DTO or record with a `values` property corresponding to `List<List<Integer>>`. The service must validate business constraints such as empty matrices, maximum dimensions, uniform column counts, or value bounds.

### Nested object lists and resolvers

When a list contains objects, each object still adheres to its schema type. For example, `[[Product!]!]!` means GraphQL receives a list of Product groups; when the client selects `name`, `price`, or other relational fields, the engine resolves those fields for each Product.

Nested lists do not automatically batch data access. If each Product's `seller` field queries a repository separately, a matrix with many Products can still trigger the N+1 problem. You can use DataLoader or `@BatchMapping` in Spring for GraphQL to batch relationship loading.

## Designing safe and efficient nested lists

Nested lists are convenient but can produce large responses. A single query returning many groups, each with thousands of items, can consume significant memory and serialization time even in one request.

When designing the schema, consider:

- **Choose nullability by contract:** only use `!` when the server truly guarantees a value exists. Overly strict Non-Null can cause one element failure to wipe out a large structure.
- **Bound sizes:** enforce maximum group counts, row counts, and element counts in the business layer; do not rely on SDL to limit list lengths.
- **Paginate:** if each group can grow unboundedly, consider returning connections or fields with pagination parameters instead of a huge nested list.
- **Control depth and complexity:** nested lists combined with object relationships can multiply resolver calls and execution cost. Enforce appropriate query depth/complexity limits.
- **Batch relational data:** use DataLoader or `@BatchMapping` when many objects across lists need to load the same kind of related data.
- **Validate input:** nested list inputs need size limits, empty-row checks, row-length checks, and domain rule validation.
- **Avoid nested lists for arbitrary grouping:** if each group item has metadata such as group name, total count, or an identifier, an object type containing a list field usually expresses it more clearly.

For example, instead of returning only `[[Product!]!]!`, you can declare a group type with its own metadata:

```graphql
type ProductGroup {
  groupId: ID!
  title: String!
  products: [Product!]!
}

type Query {
  productGroups: [ProductGroup!]!
}
```

This lets clients access metadata for each group and paginate the inner product list if the schema adds corresponding arguments.

## Common mistakes with nested lists

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Schema validation reports wrong return type | Resolver returns a 1D list while SDL requires a nested list. | Ensure the Java type has the exact number of collection levels, e.g., `List<List<Integer>>`. |
| Response contains unexpected `null` | SDL allows null at a list level or the resolver returns null. | Check `!` placement and the service's return contract. |
| Part of the response disappears when one item fails | Element or parent list is declared Non-Null, causing null to bubble up. | Identify appropriate nullable boundaries to isolate failures per business rules. |
| Client sends an array but resolver receives wrong structure | JSON variables do not match the list nesting depth or the input DTO shape is wrong. | Compare SDL, JSON variables, and the `@Argument` type. |
| Data looks like a matrix but rows have uneven lengths | GraphQL lists do not enforce element counts per row. | Validate column counts and data shape in the service. |
| Nested list requests make the server slow or memory-heavy | Large list sizes or nested fields trigger many data fetches. | Enforce size limits, pagination, batching, and query complexity limits. |

When debugging, read the type from the outside in, map each `[]` pair to a collection level, and inspect `!` at each level. Then compare against the data returned by the resolver or the structure of JSON variables.

## Key takeaways

Nested list types let GraphQL represent multi-level data such as `[[Int]]` or `[[Product!]!]!`. Square brackets define the list structure; `!` specifies whether the list or element at that position is allowed to be null. Nullability rules apply at each level and determine how errors propagate through the response.

In Spring for GraphQL, nested lists typically map to nested Java collections such as `List<List<Integer>>`. SDL does not enforce row counts, column counts, or response sizes by itself; the service must validate data, and resolvers and DataLoaders should be designed to avoid redundant queries when lists contain many objects.
