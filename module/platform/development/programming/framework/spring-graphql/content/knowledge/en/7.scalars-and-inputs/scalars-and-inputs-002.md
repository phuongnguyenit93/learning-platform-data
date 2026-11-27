# ID Scalar in GraphQL

`ID` is a built-in GraphQL scalar type used to represent an identifier value. It commonly appears on fields such as `id`, `product(id: ...)`, `user(id: ...)`, or in inputs used to reference an existing object.

The key aspects of `ID` are its identifier semantics and how it is serialized: GraphQL returns `ID` values in the response as strings. When accepting input, GraphQL accepts either string or integer values; however, clients should generally send IDs as strings to preserve consistent formatting. `ID` is not a numeric type for calculations, nor does it provide authentication or authorization on its own.

## ID Is a Built-in Scalar Type

GraphQL defines five built-in scalar types:

| Scalar | Meaning |
| --- | --- |
| `Int` | Signed 32-bit integer. |
| `Float` | Floating-point number. |
| `String` | UTF-8 character string. |
| `Boolean` | True or false value. |
| `ID` | Identifier value, serialized as a string. |

`ID` is a case-sensitive type name. Write `ID` exactly; `Id` or `id` is not the name of the built-in scalar.

Schema example:

```graphql
type Product {
  id: ID!
  name: String!
  sku: String!
}

type Query {
  product(id: ID!): Product
  productBySku(sku: String!): Product
}
```

In this example, `id` identifies a Product in the API, while `sku` is a business product code. A SKU may be a string that users read, search for, or enter from product labels; ID usually serves as a stable reference to the object. The two values might have the same text format yet carry different meanings.

## Serialization and Input Coercion Rules

### Return Values Are Serialized as Strings

When the server returns a value for a field of type `ID`, GraphQL serializes it into a string representation in the response. For example, a system storing integer primary keys can still declare the field as `ID`:

```graphql
type Product {
  id: ID!
}
```

The JSON response looks like this:

```json
{
  "data": {
    "product": {
      "id": "42"
    }
  }
}
```

The client receives `"42"` as a string, not the number `42`. This prevents the ID from being mistaken for a quantity to add, subtract, or sort numerically.

### Input Accepts Strings or Integers

When using `ID` as an argument or input field, GraphQL accepts string values and integer values. For example, both literal forms below are valid in terms of type:

```graphql
query ProductById {
  byString: product(id: "42") {
    id
    name
  }
  byInteger: product(id: 42) {
    id
    name
  }
}
```

In client applications, prefer passing strings:

```graphql
query ProductById($id: ID!) {
  product(id: $id) {
    id
    name
  }
}
```

JSON variables:

```json
{
  "id": "42"
}
```

Strings preserve identifiers with leading zeros, long values, UUIDs, or codes containing alphabetic characters. For example, `"000042"` is a different identifier from `"42"` if the system treats those two strings as distinct.

GraphQL does not accept every scalar type as an ID input. Boolean, Float, or object values are not valid inputs for `ID`. For an `ID!` field, `null` is also invalid; for nullable `ID`, `null` may be passed if business rules allow it.

| Input | Valid for `ID`? | Notes |
| --- | --- | --- |
| `"42"` | Yes | Identifier string; should be used in variables. |
| `42` | Yes | Integer input is accepted and normalized according to ID rules. |
| `42.5` | No | Float is not a valid ID input form. |
| `true` | No | Boolean is not an ID. |
| `null` | Depends on nullability | Invalid for `ID!`. |

## Using ID in Queries and Mutations

ID is commonly used to retrieve an object:

```graphql
type Query {
  product(id: ID!): Product
  productsByIds(ids: [ID!]!): [Product!]!
}
```

`product` takes a required ID. `productsByIds` takes a list of IDs; both the list and each element cannot be null. A client can call:

```graphql
query LoadProducts($ids: [ID!]!) {
  productsByIds(ids: $ids) {
    id
    name
  }
}
```

```json
{
  "ids": ["p-100", "p-101", "p-102"]
}
```

ID is also commonly used in mutations to identify the object to update or delete:

```graphql
input UpdateProductInput {
  id: ID!
  name: String
  price: Float
}

type Mutation {
  updateProduct(input: UpdateProductInput!): Product
  deleteProduct(id: ID!): Boolean!
}
```

Using `ID!` in the input ensures the client must supply an identifier value according to the schema. It does not guarantee that the object exists in the database. The service must still look up the record, handle the not-found case, and enforce business rules.

## Distinguishing ID from String and Int

The three scalars can carry data that looks similar while expressing different meanings:

| Declaration | Appropriate Meaning |
| --- | --- |
| `id: ID!` | Identifies an object or resource in the API. |
| `sku: String!` | Textual business code that can be searched or displayed to users. |
| `quantity: Int!` | Quantity used in arithmetic operations. |

You should not declare `id` as `Int` just because the current database primary key is an integer. Doing so couples clients to the storage representation and can cause difficulties if you later migrate to UUIDs or another identifier format.

Conversely, not every string should be an `ID`. Names, emails, SKU codes, statuses, or notes have their own distinct semantics; choose the scalar that accurately reflects the API contract. If a business code requires special format validation, consider a custom scalar or validation at the input/service layer.

`ID` also does not dictate comparison rules, ordering, or internal structure of the value. Clients should treat it as an opaque identifier token and avoid parsing its contents to infer business information.

## Mapping ID in Spring for GraphQL and Java

In Spring for GraphQL, the SDL schema still declares `ID`; the controller receives the argument via `@Argument` just like other scalars. A simple approach is to use `String` in the GraphQL layer:

```graphql
type Product {
  id: ID!
  name: String!
}

type Query {
  product(id: ID!): Product
}
```

```java
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

Here GraphQL accepts the `id` argument using the `ID` scalar; the controller method receives the value already processed by GraphQL as a string. The service can convert the string to an internal identifier type if needed.

### Working with UUID

GraphQL has no built-in `UUID` scalar. If the system stores IDs using `java.util.UUID`, you can keep the GraphQL contract as `ID` and convert explicitly at the service boundary:

```java
@QueryMapping
public Product product(@Argument String id) {
    UUID productId;
    try {
        productId = UUID.fromString(id);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException("Invalid Product ID");
    }

    return productService.findById(productId);
}
```

In a real application, use exceptions and error mapping consistent with your API conventions to return an error code that clients can handle. Do not let internal information or stack traces appear in public error messages.

When returning an object with an `id: ID!` field, you can expose the UUID value as a string using `uuid.toString()` or map the field to String in a DTO:

```java
public record ProductGraphQlView(
        String id,
        String name) {

    public static ProductGraphQlView from(Product product) {
        return new ProductGraphQlView(
                product.getId().toString(),
                product.getName());
    }
}
```

Explicit conversion keeps the GraphQL contract independent of the specific primary key type in persistence. If the project has a dedicated conversion mechanism for UUID, you can use it, but be sure to verify the coercion and serialization behavior of the GraphQL Java version in use.

## ID Does Not Automatically Protect Resources

`ID` only describes an identifier scalar. It does not encode access permissions, verify whether the caller is allowed to view the object, or prevent users from trying other IDs.

Schema example:

```graphql
type Query {
  order(id: ID!): Order
}
```

The fact that a client knows `orderId` does not mean the client is allowed to read that order. The resolver or service must check whether the current user has permission to access the order:

```java
@QueryMapping
public Order order(@Argument String id) {
    Order order = orderService.findById(id)
            .orElseThrow(OrderNotFoundException::new);

    authorizationService.checkCanRead(order);
    return order;
}
```

Authorization checks should be based on the authenticated principal and resource scope, including tenant or owner when needed. Do not rely on IDs being hard to guess as a substitute for authorization.

### Choosing an ID Format

Systems can use several formats:

- **Sequential integers:** easy to store and look up, though they can reveal data scale or enable sequential enumeration if endpoints lack access control.
- **UUID:** has a large value space and suits distributed identifiers; requires consistent casing and validation rules.
- **ULID or random codes:** can support time-based sorting or reduce predictability depending on generation, though access control is still required.
- **Business codes:** can embed meaning such as an order prefix or store code; consider whether that structure should be exposed through the API.

Choose a format based on persistence, integration, and operational requirements. If reducing ID guessability is needed, using sufficiently unpredictable identifiers is an extra layer; every request must still go through authentication and authorization.

## ID and the Global Object Identification Pattern

In some APIs following Relay conventions, a `node(id: ID!)` field can be used to retrieve an object from a global ID:

```graphql
interface Node {
  id: ID!
}

type Product implements Node {
  id: ID!
  name: String!
}

type Query {
  node(id: ID!): Node
}
```

A Relay implementation may encode the object type together with the identifier key into a global ID, such as a Base64 string representing the type-and-ID pair. This is a **convention of the Relay model or the application**, not default behavior of the `ID` scalar. GraphQL does not automatically encode, decode, or look up objects simply because a field has type `ID`.

If an API does not implement Global Object Identification, an ID can simply identify an object within a specific resource type, such as `product(id: ...)` or `order(id: ...)`. How the ID is interpreted depends on the field and the schema contract.

## Common Errors When Using ID

| Symptom | Common Cause | Solution |
| --- | --- | --- |
| Client passes a Float to an `ID` argument | Confusing ID with a numeric type. | Send a string or integer input matching the contract. |
| ID with leading zeros gets altered | Client converts ID to a number before sending. | Keep ID as a string end-to-end. |
| Resolver receives an unexpected type | Java binding or custom conversion mismatches scalar coercion. | Inspect the `@Argument` value, use String at the GraphQL boundary, and convert explicitly. |
| Object not found despite valid input | Value has a valid ID type but does not exist in the system. | Handle not-found in the service and return an error per API conventions. |
| User can access another user's resource | Checking only the ID without checking permissions. | Enforce authorization by principal, tenant, and resource. |
| Client assumes ID is numeric or decodable | Depending on internal formatting. | Treat ID as an opaque value; only the server interprets it. |

When debugging, check the declared type in the SDL, the variable type in the operation, the JSON variables, the value received by the controller, and the conversion step to the persistence identifier. Also verify access permissions in the service.

## Takeaways

`ID` is a built-in GraphQL scalar intended for identifier values. The server serializes IDs as strings; input coercion accepts strings or integers. You should pass IDs as strings to preserve formatting and treat ID as an opaque value rather than using it for arithmetic.

In Spring for GraphQL, you can accept an ID with `@Argument String` and then convert it to a UUID or internal key type at the service layer. `ID` does not automatically guarantee global uniqueness, verify object existence, or grant access rights. Authentication and authorization must still be enforced independently for each resource.
