# Aliases

In GraphQL, an alias lets a client specify a custom response key name for a field in a query. This syntax is especially useful when calling the same field multiple times with different arguments—for example, fetching two products by two IDs or fetching both the shipping address and billing address of the same customer.

An alias only changes the key name in the response received by the client. It does not rename the field in the schema, create a new field on the server, or require writing additional resolvers. In Spring for GraphQL, resolvers remain mapped to the real field names in SDL; aliases belong to the operation sent by the client.

## 1. What is an alias?

Alias syntax:

```graphql
responseKey: fieldName
```

Where:

- `responseKey` is the name the client wants to appear in the response.
- `fieldName` is the actual field declared in the schema.

Example schema with a `product` field:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    price: Float!
}
```

The client can assign the alias `selectedProduct`:

```graphql
query {
    selectedProduct: product(id: "p-101") {
        id
        name
        price
    }
}
```

The response uses the alias as the key:

```json
{
  "data": {
    "selectedProduct": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "price": 125.5
    }
  }
}
```

Without an alias, the default key would be `product`. An alias name does not need to exist in the schema; it is a local response name within the current operation.

## 2. Calling the same field multiple times with different arguments

A common use case is comparing two products. The schema only needs one `product(id: ID!)` field, while the client wants to fetch two different records in the same operation.

```graphql
query CompareProducts {
    firstProduct: product(id: "p-101") {
        id
        name
        price
    }
    secondProduct: product(id: "p-205") {
        id
        name
        price
    }
}
```

The response has two separate keys:

```json
{
  "data": {
    "firstProduct": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "price": 125.5
    },
    "secondProduct": {
      "id": "p-205",
      "name": "Wireless Mouse",
      "price": 49.9
    }
  }
}
```

Both fields call the `product` schema field, but with different `id` arguments and different response keys. The client receives two clearly named results in a single GraphQL response.

If you do not use aliases and write `product` twice with different arguments, GraphQL validation detects a response key conflict. Aliases distinguish these two field selections.

## 3. Using aliases with nested fields

Aliases are not limited to root fields. They can be used at any level in a selection set.

Suppose a customer has multiple types of addresses:

```graphql
type Query {
    customer(id: ID!): Customer
}

type Customer {
    id: ID!
    name: String!
    address(type: AddressType!): Address
}

enum AddressType {
    SHIPPING
    BILLING
}

type Address {
    street: String!
    city: String!
    postalCode: String!
}
```

The client needs both shipping and billing addresses:

```graphql
query CustomerAddresses($id: ID!) {
    customer(id: $id) {
        name
        shippingAddress: address(type: SHIPPING) {
            street
            city
            postalCode
        }
        billingAddress: address(type: BILLING) {
            street
            city
            postalCode
        }
    }
}
```

The response has an easy-to-use structure:

```json
{
  "data": {
    "customer": {
      "name": "Lan Nguyen",
      "shippingAddress": {
        "street": "12 Nguyen Hue",
        "city": "Ho Chi Minh City",
        "postalCode": "700000"
      },
      "billingAddress": {
        "street": "88 Le Loi",
        "city": "Ho Chi Minh City",
        "postalCode": "700000"
      }
    }
  }
}
```

Here, aliases distinguish the two results of the same `address` field based on the `type` argument. The client can access `shippingAddress` and `billingAddress` directly without having to reassemble data after receiving the response.

## 4. Combining aliases with variables

Aliases can be combined with variables for more flexible queries. For example, a client comparing two products whose IDs come from UI state:

```graphql
query CompareProducts($leftId: ID!, $rightId: ID!) {
    left: product(id: $leftId) {
        id
        name
        price
    }
    right: product(id: $rightId) {
        id
        name
        price
    }
}
```

Variables:

```json
{
  "leftId": "p-101",
  "rightId": "p-205"
}
```

Aliases and variables solve two different things:

- Aliases name the results in the response.
- Variables pass values into arguments without interpolating strings into the query document.

Alias names are part of the GraphQL document, whereas ID values are passed at execution time. The client can reuse the same document for many different pairs of IDs.

## 5. Aliases and response key rules

GraphQL refers to the name used as the key in the response as the *response name*. If a field has an alias, the response name is the alias; if there is no alias, the response name is the field name itself.

Example:

```graphql
query {
    featured: product(id: "p-101") {
        name
    }
}
```

The response name is `featured`, not `product`.

Fields with the same response name must be compatible so GraphQL can merge selections. If the same response key points to different fields or uses conflicting arguments, the operation may fail validation.

Conflict example:

```graphql
query {
    product(id: "p-101") {
        id
    }
    product(id: "p-205") {
        id
    }
}
```

Both selections share the response key `product` but have different `id` arguments. The fix is to assign separate aliases:

```graphql
query {
    first: product(id: "p-101") {
        id
    }
    second: product(id: "p-205") {
        id
    }
}
```

Conversely, if the same field with the same arguments is selected repeatedly under the same response name and compatible selections, GraphQL can merge those selections according to field collection rules. There is no need to create aliases just to repeat identical data.

## 6. Aliases in fragments

Aliases can appear inside fragments just like in regular selection sets. This lets you reuse a query structure while naming response keys for the context.

```graphql
fragment ProductCard on Product {
    productName: name
    currentPrice: price
}

query {
    product(id: "p-101") {
        ...ProductCard
    }
}
```

Response:

```json
{
  "data": {
    "product": {
      "productName": "Mechanical Keyboard",
      "currentPrice": 125.5
    }
  }
}
```

Because the aliases are inside the fragment, the corresponding response keys are still renamed when the fragment is spread into a selection set. If multiple fragments are shared across several places, check the expected response shape at each site and avoid creating conflicting aliases.

## 7. How do aliases affect GraphQL errors?

When a field encounters an error during execution, the GraphQL response can contain `errors` with a `path` pointing to the failing field. Elements of the path use the response name—that is, the alias if the field was aliased.

Example query:

```graphql
query {
    chosenProduct: product(id: "p-101") {
        displayPrice: price
    }
}
```

If the `price` resolver throws an error, the path may look like:

```json
{
  "errors": [
    {
      "message": "Price is temporarily unavailable",
      "path": ["chosenProduct", "displayPrice"]
    }
  ],
  "data": {
    "chosenProduct": null
  }
}
```

The path uses the aliases `chosenProduct` and `displayPrice`, because those are the response keys seen by the client. When handling errors or logging on the client side, rely on the response path rather than always assuming the path contains schema field names.

## 8. Aliases when using Spring for GraphQL

Aliases are a feature of the GraphQL query language and execution engine. Spring for GraphQL does not need a special annotation to declare aliases. Controllers still map to field names in the schema.

Schema example:

```graphql
type Query {
    product(id: ID!): Product
}
```

Controller:

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

Client sends:

```graphql
query {
    keyboard: product(id: "p-101") {
        id
        name
    }
    mouse: product(id: "p-205") {
        id
        name
    }
}
```

Both selections invoke the `product` schema field, so Spring maps them to the `@QueryMapping product` method. The resolver executes for each field occurrence with its respective arguments. You do not need to create `keyboard()` or `mouse()` methods, nor declare two new fields in SDL.

Aliases do not change `@Argument` names. The method still receives the `id` argument, because that is the argument name on the `product` schema field. If you need execution location or operation metadata in infrastructure logic, you can use GraphQL Java's execution context APIs; regular business logic should not depend on client-chosen aliases.

## 9. Aliases with mutations

Aliases can also be used in mutation operations. For example, one operation renaming two products:

```graphql
mutation RenameProducts {
    keyboard: renameProduct(id: "p-101", name: "Keyboard Pro") {
        id
        name
    }
    mouse: renameProduct(id: "p-205", name: "Mouse Pro") {
        id
        name
    }
}
```

The response will have two keys, `keyboard` and `mouse`. Top-level mutation fields in the same operation are executed sequentially in the order they appear in the document.

Aliases do not turn an operation into a transaction. If the first mutation succeeds and the second mutation fails, GraphQL does not automatically roll back the first change. For workflows requiring atomicity, provide a single business command on the server and manage the transaction in the service/domain layer.

Do not use aliases to disguise or alter the business meaning of a mutation. Alias names only organize the response for the client; access control, validation, and auditing must still be based on the actual command and resources.

## 10. Limits and best practices

Aliases are very flexible, but each field selection can still trigger resolvers and data access. A query using dozens of aliases to invoke the same field with many arguments can put heavy load on the server.

Principles to apply:

- Choose concise aliases that clearly express the role of the result, such as `shippingAddress`, `billingAddress`, `primaryContact`.
- Use aliases when you need to distinguish calls to the same field or need context-appropriate response keys.
- Use variables for values that vary across executions; never construct new query documents by concatenating input strings.
- Limit depth, complexity, and returned item counts to control query cost.
- Check authorization for every resolved resource and field, even when they appear under different aliases.
- Never use aliases as a security mechanism or to hide sensitive fields.
- Monitor operation and resolver costs; client-supplied alias names can vary and are not stable identifiers for grouping metrics.

Aliases do not alter schema introspection and do not create new API fields. The client merely renames response keys within the current operation. This keeps the schema concise while letting each client organize data according to its needs.

## 11. Checklist when using aliases

- Is the alias a valid GraphQL Name?
- Is the response key clear enough for the client to understand what the data represents?
- Do repeated calls to the same field with different arguments have separate aliases?
- Are fields sharing the same response name compatible for merging?
- Does the client handle error paths based on aliases?
- Does the query have reasonable call limits and resolver cost limits?
- For mutations, are transactions and idempotency designed independently of aliases?

Aliases are a small but important tool for organizing GraphQL responses. They allow the same field to appear multiple times with different arguments, give meaningful names to nested data, and help clients receive context-appropriate responses. In Spring for GraphQL, the server still handles fields via the existing schema and resolvers; aliases only affect how results are named in the response.
