# GraphQL Documentation in Schema

## Objectives

After this lesson, you will be able to:

- Explain the role of descriptions in a GraphQL schema.
- Distinguish descriptions preserved by introspection from comments meant only for source-code readers.
- Write documentation for types, fields, arguments, input fields, enums, and enum values using SDL.
- Use the @deprecated directive to announce upcoming API removals.
- Read descriptions and deprecation information via GraphQL introspection.
- Enable GraphiQL in Spring Boot to explore the schema and API documentation.
- Write concise, accurate, and useful descriptions for clients.

## 1. Why Document Directly in the Schema?

A GraphQL schema is the contract between the server and clients. The schema describes what types exist, which fields can be queried, which arguments are passed, and what data types are returned.

However, field names and data types are not enough to explain business meaning. For instance, a field named `status` of type `String` does not tell you which values are valid, which state is final, or whether clients are allowed to update it.

GraphQL supports descriptions directly in Schema Definition Language (SDL). Descriptions are stored in the schema and can be retrieved via introspection. Tools like GraphiQL can display those descriptions in the API documentation.

Example:

~~~graphql
"""
A book available in the catalog.
"""
type Book {
  """
  Stable identifier of the book.
  """
  id: ID!

  """
  Title displayed to readers.
  """
  title: String!
}
~~~

When a client inspects the schema, it can read the meaning of the Book type and the id and title fields without opening the server's source code.

In-schema documentation helps:

- Clients understand the purpose of fields and arguments.
- API documentation generators automatically include business context.
- Frontend and backend teams align on how to use the API.
- Developers identify legacy fields, replacement fields, and usage constraints.
- Reduce reliance on external documentation that can become outdated.

## 2. Descriptions Differ from Comments in SDL

SDL supports both comments and descriptions, but the two elements serve different purposes.

### Comments

Comments start with `#`. They are meant for readers of the SDL file and do not become description metadata in the GraphQL schema.

~~~graphql
# Book data returned by the catalog.
type Book {
  id: ID!
  title: String!
}
~~~

The comment above does not appear as Book's description when clients introspect the schema.

### Descriptions

A description is a string literal placed immediately before the definition it describes. You can use a single-line string or a multi-line block string.

~~~graphql
"Represents a book in the catalog."
type Book {
  "Stable identifier."
  id: ID!

  """
  Title shown to readers.
  The value is localized by the catalog service.
  """
  title: String!
}
~~~

The description is attached to the corresponding schema element and can be retrieved via introspection.

| Element | `#` Comment | String Description |
|---|---|---|
| Helps readers of the SDL file | Yes | Yes |
| Stored as description metadata | No | Yes |
| Retrievable via introspection | No | Yes |
| Displayed in schema documentation tools | Not directly | Yes |

Use comments for notes about file organization, implementation decisions, or internal reminders. Use descriptions for information consumers of the GraphQL API need to know.

## 3. String and Block String Syntax

Descriptions can use regular string literals:

~~~graphql
"Returns the display name of the author."
type Author {
  name: String!
}
~~~

For multi-sentence descriptions or descriptions needing line breaks, use a triple-quoted block string:

~~~graphql
"""
Represents an author in the catalog.

An author can be associated with multiple books.
The name is displayed according to the user's locale.
"""
type Author {
  name: String!
}
~~~

Block strings make long descriptions easier to read in SDL. Content is processed according to GraphQL's block string rules, including stripping common indentation.

Several guidelines:

- Place the description immediately before the element being described.
- Write complete sentences using terminology consistent with the domain.
- Avoid stating the obvious by merely repeating the field name.
- Do not cram internal implementation details into public documentation.
- If a description has multiple ideas, use a block string and separate paragraphs cleanly.

## 4. Documenting Types and Fields

A type description should explain what the object represents in the domain. A field description should describe its meaning, units, rules, and conditions that can affect the client.

Example:

~~~graphql
"""
A monetary amount represented in the currency of the order.
"""
type Money {
  """
  Amount in the smallest currency unit.
  For VND, this value represents đồng.
  """
  amount: Int!

  """
  ISO 4217 currency code, such as VND or USD.
  """
  currency: String!
}

"""
An order placed by a customer.
"""
type Order {
  """
  Unique order identifier.
  """
  id: ID!

  """
  Current lifecycle state of the order.
  """
  status: OrderStatus!

  """
  Total amount charged for this order.
  """
  total: Money!
}
~~~

In this example, Money's description explains the overall concept. The description of amount clarifies the storage unit; currency specifies the ISO 4217 currency code. Clients have enough context to display monetary amounts accurately.

Avoid writing descriptions like “The amount” for the amount field if users still do not know what unit the amount is measured in.

## 5. Documenting Queries, Mutations, and Arguments

Fields on Query and Mutation also need clear behavior descriptions. In particular, arguments should explain conditions, units, limits, and default values when they carry business meaning.

~~~graphql
type Query {
  """
  Finds an order by its identifier.

  Returns null when the order does not exist.
  """
  order(
    """
    Identifier returned when the order was created.
    """
    id: ID!
  ): Order

  """
  Returns orders visible to the current user.

  Results are ordered by creation time, newest first.
  """
  orders(
    """
    Maximum number of orders to return.
    Must be between 1 and 100.
    """
    first: Int = 20
  ): [Order!]!
}

type Mutation {
  """
  Cancels an order if its current state allows cancellation.

  The operation may fail when fulfillment has already started.
  """
  cancelOrder(
    """
    Identifier of the order to cancel.
    """
    id: ID!
  ): Order!
}
~~~

Argument descriptions are placed inside the field's parentheses, immediately before the corresponding argument.

A good argument description should answer these questions:

- Which entity or condition does the argument identify?
- What unit or format does the value have?
- Are there min/max limits or an allowed set of values?
- What is the default behavior when the argument is omitted?
- What does a null value mean if the argument is nullable?

Do not just describe `first` as “number of items”. Explicitly state bounds and ordering if they are part of the API contract.

## 6. Documenting Input Objects and Input Fields

Input objects typically represent data for creation or updates. Descriptions should clarify the meaning of each field, especially for nullable or optional fields.

~~~graphql
"""
Information required to create a customer account.
"""
input CreateCustomerInput {
  """
  Full name displayed on invoices and customer pages.
  """
  fullName: String!

  """
  Email address used for account notifications.
  Must be unique within the customer system.
  """
  email: String!

  """
  Optional phone number in international format.
  """
  phoneNumber: String
}
~~~

For partial-update mutations, explain the difference between omitting a field and passing null if the API supports distinct behaviors.

~~~graphql
"""
Fields that can be changed on an existing customer.
Omitted fields remain unchanged.
A nullable field explicitly set to null is cleared.
"""
input UpdateCustomerInput {
  displayName: String
  phoneNumber: String
}
~~~

Descriptions help clients understand business semantics, but a description by itself does not alter how GraphQL binds data. The logic distinguishing omitted fields from explicit null must still be implemented in the resolver or input-handling layer.

## 7. Documenting Enums and Enum Values

Enums restrict a field to a defined set of values. Document both the enum and each value so clients understand the meaning of every state.

~~~graphql
"""
Lifecycle states of an order.
"""
enum OrderStatus {
  """
  The order has been created but payment is pending.
  """
  PENDING

  """
  Payment was confirmed and the order is being prepared.
  """
  CONFIRMED

  """
  The order has been handed to the delivery provider.
  """
  SHIPPED

  """
  The order was delivered to the customer.
  """
  DELIVERED

  """
  The order was cancelled before completion.
  """
  CANCELLED
}
~~~

The enum description explains the overall concept. Each value's description clarifies the state and prevents clients from misinterpreting it solely from its name.

If an enum includes states that only occur in internal workflows, consider whether they should be exposed via the API at all. Documentation does not substitute for properly scoping public data.

## 8. Using @deprecated to Document Field Lifecycle

When an API needs to replace a field or enum value, do not delete it immediately if clients are still using it. GraphQL provides the built-in @deprecated directive to mark elements that are no longer recommended.

Example:

~~~graphql
type Customer {
  id: ID!

  """
  Legacy display name field.
  Use fullName instead.
  """
  name: String @deprecated(
    reason: "Use fullName instead."
  )

  """
  Customer's full display name.
  """
  fullName: String!
}
~~~

@deprecated can also be applied to enum values:

~~~graphql
enum PaymentMethod {
  CARD

  """
  Legacy bank transfer option.
  """
  BANK_TRANSFER @deprecated(
    reason: "Use BANK_REDIRECT instead."
  )

  BANK_REDIRECT
}
~~~

Characteristics of the @deprecated directive:

- `reason` explains why usage is no longer recommended.
- If `reason` is omitted, GraphQL uses the default reason from the specification.
- Introspection tools can display the deprecated status and reason.
- Clients can migrate to the replacement field or enum value during the compatibility window.

In supporting GraphQL versions, this directive can also apply to certain input value definitions such as arguments and input fields. Verify the GraphQL Java version your project uses before applying newer locations.

Deprecated does not mean deleted. The server can still receive queries using that field until the field is actually removed from the schema.

## 9. Reading Documentation via Introspection

GraphQL introspection lets clients ask the schema itself about types, fields, arguments, enums, and directives. Description metadata is also exposed through the corresponding introspection fields.

For example, retrieving descriptions for the Book type and its fields:

~~~graphql
query BookDocumentation {
  __type(name: "Book") {
    name
    description
    fields {
      name
      description
      isDeprecated
      deprecationReason
      args {
        name
        description
      }
    }
  }
}
~~~

Part of the response might look like this:

~~~json
{
  "data": {
    "__type": {
      "name": "Book",
      "description": "A book available in the catalog.",
      "fields": [
        {
          "name": "id",
          "description": "Stable identifier of the book.",
          "isDeprecated": false,
          "deprecationReason": null,
          "args": []
        }
      ]
    }
  }
}
~~~

You can explore an enum and the descriptions of each value:

~~~graphql
query OrderStatusDocumentation {
  __type(name: "OrderStatus") {
    name
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
  }
}
~~~

Key fields:

| Introspection Type | Metadata |
|---|---|
| __Type | name, description, fields, inputFields, enumValues |
| __Field | name, description, args, isDeprecated, deprecationReason |
| __InputValue | name, description, type, defaultValue |
| __EnumValue | name, description, isDeprecated, deprecationReason |
| __Directive | name, description, locations, args |

Introspection does not return comments starting with `#`. Only descriptions declared in the schema can be retrieved as descriptive metadata.

## 10. Exploring Documentation with GraphiQL in Spring Boot

Spring Boot can serve the GraphiQL UI for developing and exploring a GraphQL API. When GraphiQL is enabled, developers can run queries and browse schema documentation backed by introspection.

Example configuration:

~~~yaml
spring:
  graphql:
    graphiql:
      enabled: true
      path: /graphiql
~~~

After the application starts with the HTTP GraphQL transport and appropriate configuration, open the configured GraphiQL path in a browser.

In the GraphiQL UI, the Documentation Explorer can display:

- Root operations such as Query, Mutation, and Subscription.
- Lists of object types, interfaces, unions, and enums.
- Type and field descriptions.
- Arguments, data types, and default values.
- Deprecation status along with reasons.

If descriptions do not appear, check that SDL uses description strings rather than only comments. Also verify whether introspection is permitted in the running environment.

GraphiQL is a development support tool. Enabling this UI in production must follow your system's deployment and security policies.

## 11. Documentation Does Not Replace Validation and Authorization

Descriptions only provide information for schema readers. They do not enforce business rules.

For example, describing that the `first` argument has a limit from 1 to 100 does not cause GraphQL to automatically reject 500. The resolver or validation layer must still check that limit.

Similarly:

- A description saying “Only the owner can view this field” does not protect the field on its own.
- A description saying “Email must be unique” does not create a unique constraint in the database.
- A description saying “This operation is idempotent” does not make a mutation idempotent by itself.
- @deprecated announces the API lifecycle but does not automatically route requests to the new field.

Implement validation, authorization, transactions, and corresponding rules on the server. Documentation must accurately describe implemented behavior, never promise behavior the system does not guarantee.

## 12. Guidelines for Writing Good Documentation

An easy-to-use schema requires consistent and genuinely helpful descriptions. You can use this checklist when reviewing SDL:

- [ ] Every important type has a description explaining its business meaning.
- [ ] Fields with special rules, units, or usage conditions are documented.
- [ ] Arguments have their bounds, formats, and default behavior explained.
- [ ] Input fields clearly distinguish required, optional, and nullable semantics.
- [ ] Enums and enum values have clear descriptions.
- [ ] Legacy fields or enum values have @deprecated and a replacement reason.
- [ ] Descriptions do not contradict validation and resolver behavior.
- [ ] `#` comments are not used in place of descriptions when content needs to be visible to clients.
- [ ] No secrets or internal implementation details are placed in public schemas.

Prioritize describing what clients need to use the API correctly. For example, for an `amount` field, currency units and rounding rules are far more useful than a sentence repeating the field name.

## 13. Complete Documented Schema Example

The comprehensive example below combines descriptions for types, fields, arguments, input objects, enums, and deprecation:

~~~graphql
scalar Date

"""
Lifecycle states of a reservation.
"""
enum ReservationStatus {
  """
  Reservation is awaiting confirmation.
  """
  PENDING

  """
  Reservation has been confirmed.
  """
  CONFIRMED

  """
  Reservation has been cancelled.
  """
  CANCELLED
}

"""
A reservation made by a customer.
"""
type Reservation {
  """
  Stable reservation identifier.
  """
  id: ID!

  """
  Current state in the reservation lifecycle.
  """
  status: ReservationStatus!

  """
  Customer-facing note attached to the reservation.
  """
  note: String

  """
  Legacy reference field. Use id instead.
  """
  reference: String @deprecated(
    reason: "Use id instead."
  )
}

"""
Information required to create a reservation.
"""
input CreateReservationInput {
  """
  Identifier of the customer making the reservation.
  """
  customerId: ID!

  """
  Date on which the reservation takes place.
  """
  reservationDate: Date!

  """
  Optional note visible to the customer.
  """
  note: String
}

type Query {
  """
  Finds a reservation by its identifier.

  Returns null if no matching reservation exists.
  """
  reservation(
    """
    Stable reservation identifier.
    """
    id: ID!
  ): Reservation
}

type Mutation {
  """
  Creates a reservation for the current customer.
  """
  createReservation(
    """
    Reservation details supplied by the client.
    """
    input: CreateReservationInput!
  ): Reservation!
}
~~~

When tools introspect the schema, clients can retrieve descriptions for Reservation, status, note, the CreateReservationInput input, and each operation's arguments. The reference field is also recognized as deprecated with its replacement reason.

## Conclusion

GraphQL documentation in the schema is declared using SDL description strings. Unlike `#` comments, descriptions are stored as metadata and can be retrieved via introspection. You can document types, fields, arguments, input fields, enums, and enum values to create a clear API contract.

Combining descriptions with @deprecated, introspection, and GraphiQL helps clients explore the schema, understand how to use it, and migrate away from legacy APIs. In Spring for GraphQL, treat documentation as part of schema design and keep descriptions aligned with validation, authorization, and actual resolver behavior.

## References

- [GraphQL Specification — Descriptions](https://spec.graphql.org/October2021/#sec-Descriptions)
- [GraphQL Specification — Type System](https://spec.graphql.org/October2021/#sec-Type-System)
- [GraphQL Specification — Introspection](https://spec.graphql.org/October2021/#sec-Introspection)
- [GraphQL Specification — @deprecated](https://spec.graphql.org/October2021/#sec--deprecated)
- [Spring Boot — Spring for GraphQL and GraphiQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
