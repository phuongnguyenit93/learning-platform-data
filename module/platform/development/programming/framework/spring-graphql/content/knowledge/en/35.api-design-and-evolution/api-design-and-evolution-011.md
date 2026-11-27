# Mutation Payload Contracts

A Mutation is an operation that mutates state or triggers an action in a GraphQL API. A solid mutation contract should clearly define what data the client sends, what the success result contains, how business errors are returned, and how clients can handle retries.

Instead of returning an entity, scalar, or boolean directly, design a dedicated payload type for each mutation. A payload provides a stable contract so you can later add `userErrors`, warnings, metadata, or related objects without changing the mutation field's return type. In Spring for GraphQL, SDL defines the payload contract, while `@MutationMapping` receives inputs, invokes an application use case, and maps the outcome to a payload.

## 1. Mutations express business actions

A mutation should describe an action meaningful to users or the domain, for example:

- `createOrder` — place an order.
- `cancelOrder` — cancel an order.
- `capturePayment` — capture a payment.
- `changeShippingAddress` — update the shipping address.
- `publishArticle` — publish an article.

Mutation names should express concrete actions. Generic fields like `updateEntity` or `saveData` struggle to convey the business preconditions, permissions, and side effects the client is requesting.

Two common naming conventions are verb-first (`createOrder`) and noun-first (`orderCreate`). Either works; what matters is picking one convention and keeping it consistent across the schema. Examples below use verb-first.

## 2. Why not return an entity or boolean directly?

A simple mutation might return an entity directly:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): Order
}
```

Or return a boolean:

```graphql
type Mutation {
    cancelOrder(id: ID!): Boolean!
}
```

These two forms may work in small APIs, but lack room to evolve the contract. When you need to return validation errors, warnings, related objects, or metadata, you have to change the return type and force clients to rewrite operations.

Instead, return a dedicated payload type:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}
```

Clients can select `order`, `userErrors`, or additional fields added later. Payloads create a stable extension point for mutations.

## 3. Use a dedicated input object for each mutation

Group input data into a named input object passed via an `input` argument:

```graphql
input CreateOrderInput {
    customerId: ID!
    items: [OrderItemInput!]!
    idempotencyKey: String
}

input OrderItemInput {
    productId: ID!
    quantity: Int!
}

type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}
```

This approach offers several benefits:

- Client operations only need a single `$input` variable.
- Optional fields can be added to the input without changing the mutation's argument list.
- Input types have distinct names, making them easy to reuse in documentation and code generation.
- It clearly separates `CreateOrder` inputs from `UpdateOrder` inputs even when both operations share several fields.
- It avoids mutations with too many disconnected arguments.

Do not share one giant input type across every mutation just because they all operate on `Order`. `CreateOrderInput`, `UpdateOrderInput`, and `CancelOrderInput` usually serve different purposes and rules.

## 4. Designing dedicated payload types for mutations

Payloads should have specific names, typically ending in `Payload`:

```graphql
type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type CancelOrderPayload {
    order: Order
    userErrors: [UserError!]!
}
```

Not every payload needs the exact same fields. `CreateOrderPayload` may return the newly created order; `CancelOrderPayload` may return the canceled order along with refund details; `CapturePaymentPayload` may return the payment transaction.

If several mutations genuinely share the exact same outcome and semantics, they may share a type. However, do not force every mutation into a catch-all `MutationPayload` full of unrelated nullable fields. Dedicated payloads make the schema easier to explore and evolve.

## 5. Success and business error contracts

A common payload has two parts:

- A business result field, such as `order`.
- A `userErrors` list describing unmet business conditions.

Convention:

| Outcome | `order` | `userErrors` |
|---|---|---|
| Success | Present | Empty list. |
| Insufficient stock | `null` | Contains `INSUFFICIENT_STOCK` error. |
| Product not found | `null` | Contains `PRODUCT_NOT_FOUND` error. |
| User not allowed to order | `null` | Contains error per API policy. |

Example success response:

```json
{
  "data": {
    "createOrder": {
      "order": {
        "id": "order-101",
        "status": "PLACED"
      },
      "userErrors": []
    }
  }
}
```

Example response with a business error:

```json
{
  "data": {
    "createOrder": {
      "order": null,
      "userErrors": [
        {
          "code": "INSUFFICIENT_STOCK",
          "message": "Insufficient product stock",
          "inputPath": ["items", "0", "quantity"]
        }
      ]
    }
  }
}
```

In the second case, the mutation still executed normally per GraphQL; the business logic rejected the action and reported that detail in the payload. Top-level `errors` does not need an entry for a business rejection already modeled in the payload.

## 6. Defining `UserError` clearly

SDL can declare:

```graphql
enum UserErrorCode {
    INVALID_INPUT
    INVALID_QUANTITY
    PRODUCT_NOT_FOUND
    PRODUCT_UNAVAILABLE
    INSUFFICIENT_STOCK
    CUSTOMER_NOT_ALLOWED
    IDEMPOTENCY_KEY_REUSED
    VERSION_CONFLICT
}

type UserError {
    code: UserErrorCode!
    message: String!
    inputPath: [String!]
}
```

Field meanings:

- `code`: stable code for client branching logic.
- `message`: text suitable for user display or mapping through client localization.
- `inputPath`: path to the offending input segment when the error maps to a specific field.

For example, `inputPath: ["items", "0", "quantity"]` points to the `quantity` field of the first element in `items`. For global errors not tied to a single field, `inputPath` can be `null`.

Never require clients to parse the `message` string to drive logic. Messages can change phrasing or language; `code` is the machine-readable contract.

## 7. Distinguishing `inputPath` from GraphQL error `path`

These two paths mean different things:

| Path | Where it lives | Description |
|---|---|---|
| `userErrors[].inputPath` | Inside mutation payload | Location in client-submitted input that caused the business error. |
| Top-level GraphQL `errors[].path` | Inside GraphQL response errors | Location of the response field that failed execution. |

Example `inputPath`:

```json
{
  "code": "INVALID_QUANTITY",
  "message": "Quantity must be greater than 0",
  "inputPath": ["items", "1", "quantity"]
}
```

Example top-level `path`:

```json
{
  "message": "Unable to load customer information",
  "path": ["createOrder", "order", "customer"]
}
```

Clients can use `inputPath` to highlight form fields. GraphQL `errors[].path` identifies which response field failed. Never substitute one concept for the other.

## 8. Distinguishing business errors from GraphQL execution errors

Not every error belongs in `userErrors`.

| Error type | Example | Appropriate representation |
|---|---|---|
| GraphQL syntax/validation | Missing brace, selecting nonexistent field | Top-level GraphQL `errors`. |
| Input coercion | Passing a string to an `Int!` argument | Top-level GraphQL `errors`; resolver is never called. |
| Binding/Bean Validation | DTO binding failure or constraint violation | Per API policy; usually a GraphQL error unless intentionally mapped into payload. |
| Business rejection | Out of stock, order already canceled, ineligible | `userErrors` in payload. |
| Authentication/authorization | Invalid token or unauthorized access | Security/GraphQL error or payload per consistent API policy. |
| System/infrastructure failure | Database disconnect, programming bug, dependency timeout | Top-level GraphQL execution error. |

A business rejection is a predictable business outcome that clients can handle. A system failure is an execution fault preventing the server from completing the resolver. Do not catch every exception and stuff it into `userErrors`, as doing so can mask outages and mislead clients into thinking the action failed due to user input.

## 9. Choosing nullability for payloads

A common SDL setup:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}
```

Rationale:

- `CreateOrderPayload!`: for normally handled business outcomes, the resolver always returns a payload.
- `order: Order`: nullable because there is no order when business rules reject the request.
- `userErrors: [UserError!]!`: always returns a list, empty on success; individual error items are never null.

Do not declare `order: Order!` if the mutation can be rejected without an order to return. If a resolver returns null for a non-null field, GraphQL raises an execution error and null bubbles up to the nearest nullable parent.

## 10. Understanding null propagation on system errors

A non-null payload does not mean the resolver can never fail. For instance, `createOrder` returns `CreateOrderPayload!`, yet the database throws an exception. GraphQL records a top-level error. Because the mutation field is non-null, null can bubble up to the root response `data`.

If an API executes multiple root mutation fields in one operation and wants a failure in one field not to wipe out results from another completed mutation field, consider making root mutation fields nullable:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload
}
```

Then an execution error can null out only `createOrder` while preserving sibling fields per propagation rules. Even so, multiple root mutation fields still do not automatically share a single transaction. Choosing `Payload!` vs. `Payload` should be driven by desired error isolation and API semantics, not a mechanical rule.

## 11. Do not mix expected errors with unexpected errors

A mutation can encounter two categories of failures:

**Business rejection:** out-of-stock product, invalid quantity, order state disallows cancellation. The use case returns a structured rejection; the resolver maps it to `userErrors`.

**Execution failure:** database disconnect, programming bug, unhandled timeout. The exception flows through Spring for GraphQL's error handling mechanism and becomes a top-level GraphQL error.

Do not write:

```java
try {
    return useCase.execute(command);
} catch (Exception ex) {
    return new CreateOrderPayload(null, List.of(
        new UserError("UNKNOWN", ex.getMessage(), null)
    ));
}
```

This snippet turns every system failure into an input error while risking internal detail leakage via `ex.getMessage()`.

## 12. Implementing a resolver that maps application outcomes to payloads

Define the input DTO:

```java
import java.util.List;

public record CreateOrderInput(
    String customerId,
    List<OrderItemInput> items,
    String idempotencyKey
) {}

public record OrderItemInput(String productId, int quantity) {}
```

Define the GraphQL response model:

```java
import java.util.List;

public record CreateOrderPayload(
    OrderView order,
    List<UserError> userErrors
) {
    public CreateOrderPayload {
        userErrors = List.copyOf(userErrors);
    }
}

public record UserError(
    UserErrorCode code,
    String message,
    List<String> inputPath
) {}

public enum UserErrorCode {
    INVALID_INPUT,
    INVALID_QUANTITY,
    PRODUCT_NOT_FOUND,
    PRODUCT_UNAVAILABLE,
    INSUFFICIENT_STOCK,
    CUSTOMER_NOT_ALLOWED,
    IDEMPOTENCY_KEY_REUSED,
    VERSION_CONFLICT
}
```

The application layer returns a GraphQL-independent outcome:

```java
import java.util.List;
import java.util.Optional;

public record BusinessViolation(
    String code,
    String message,
    List<String> inputPath
) {}

public record CreateOrderOutcome(
    Optional<OrderSummary> order,
    List<BusinessViolation> violations
) {
    public static CreateOrderOutcome success(OrderSummary order) {
        return new CreateOrderOutcome(Optional.of(order), List.of());
    }

    public static CreateOrderOutcome rejected(List<BusinessViolation> violations) {
        return new CreateOrderOutcome(Optional.empty(), List.copyOf(violations));
    }
}
```

The resolver only converts inputs into a command, invokes the use case, and maps the outcome:

```java
import java.security.Principal;
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderMutationController {

    private final CreateOrderUseCase createOrder;

    OrderMutationController(CreateOrderUseCase createOrder) {
        this.createOrder = createOrder;
    }

    @MutationMapping
    CreateOrderPayload createOrder(
            @Argument("input") CreateOrderInput input,
            Principal principal) {

        CreateOrderCommand command = new CreateOrderCommand(
            principal.getName(),
            input.customerId(),
            input.items().stream()
                .map(item -> new OrderLineCommand(item.productId(), item.quantity()))
                .toList(),
            input.idempotencyKey()
        );

        CreateOrderOutcome outcome = createOrder.execute(command);

        OrderView order = outcome.order()
            .map(OrderView::from)
            .orElse(null);

        List<UserError> userErrors = outcome.violations().stream()
            .map(this::toUserError)
            .toList();

        return new CreateOrderPayload(order, userErrors);
    }

    private UserError toUserError(BusinessViolation violation) {
        return new UserError(
            toUserErrorCode(violation.code()),
            violation.message(),
            violation.inputPath()
        );
    }

    private UserErrorCode toUserErrorCode(String code) {
        return switch (code) {
            case "INVALID_QUANTITY" -> UserErrorCode.INVALID_QUANTITY;
            case "PRODUCT_NOT_FOUND" -> UserErrorCode.PRODUCT_NOT_FOUND;
            case "PRODUCT_UNAVAILABLE" -> UserErrorCode.PRODUCT_UNAVAILABLE;
            case "INSUFFICIENT_STOCK" -> UserErrorCode.INSUFFICIENT_STOCK;
            case "CUSTOMER_NOT_ALLOWED" -> UserErrorCode.CUSTOMER_NOT_ALLOWED;
            case "IDEMPOTENCY_KEY_REUSED" -> UserErrorCode.IDEMPOTENCY_KEY_REUSED;
            case "VERSION_CONFLICT" -> UserErrorCode.VERSION_CONFLICT;
            case "INVALID_INPUT" -> UserErrorCode.INVALID_INPUT;
            default -> throw new IllegalStateException("Unsupported business error code");
        };
    }
}
```

Application and view types used by the resolver:

```java
import java.util.List;

public record CreateOrderCommand(
    String actorId,
    String customerId,
    List<OrderLineCommand> lines,
    String idempotencyKey
) {}

public record OrderLineCommand(String productId, int quantity) {}

public record OrderSummary(String id, String status) {}

public interface CreateOrderUseCase {
    CreateOrderOutcome execute(CreateOrderCommand command);
}

public record OrderView(String id, String status) {
    public static OrderView from(OrderSummary summary) {
        return new OrderView(summary.id(), summary.status());
    }
}
```

The resolver explicitly maps application error codes to the GraphQL enum. Unsupported codes are treated as programming errors and flow through execution error handling rather than silently returning a fallback code.

## 13. Placing business validation in the application/domain layer

The use case decides whether the business action can proceed. For example, before creating an order:

1. Verify the customer falls within the actor's authorized scope.
2. Check that every quantity is greater than 0.
3. Verify products exist and are currently for sale.
4. Check inventory stock.
5. Calculate pricing and apply discount policies.
6. Create the order and persist data inside a transaction.

If business conditions fail, the use case returns `CreateOrderOutcome.rejected(...)` with one or more `BusinessViolation`s. The resolver converts them into `UserError`s.

If rejection happens after writes have occurred, ensure the transaction does not commit partial state. Validate before writing, use proper transaction rollback, or model an explicit workflow state. Never return a rejection payload after leaving out-of-contract side effects behind.

## 14. Naming and stabilizing error codes

Error codes are part of the API contract. Choose codes that are:

- Stable across message wording changes.
- Clear in meaning to clients.
- Independent of Java exception names.
- Free of IDs, emails, or sensitive data.
- Documented with expected client handling.

Example:

| Code | Meaning | Client handling |
|---|---|---|
| `INVALID_QUANTITY` | Quantity is invalid | Highlight error on the quantity input. |
| `PRODUCT_NOT_FOUND` | Product not found | Prompt user to select another product. |
| `PRODUCT_UNAVAILABLE` | Product is no longer for sale | Update the shopping cart. |
| `INSUFFICIENT_STOCK` | Insufficient inventory | Allow reducing quantity. |
| `CUSTOMER_NOT_ALLOWED` | Actor is not authorized | Display an appropriate permission notice. |
| `IDEMPOTENCY_KEY_REUSED` | Key used for a different payload | Generate a new key or inspect the prior request. |
| `VERSION_CONFLICT` | Data has changed | Reload the latest data. |

If using a GraphQL enum for codes, adding enum values can affect clients using exhaustive `switch` statements. For APIs needing frequent code additions, consider `String!` paired with documented error codes and client fallbacks. Whether using an enum or string, never change the meaning of a published code.

## 15. Distinguishing GraphQL validation from business validation

GraphQL checks several conditions automatically before any resolver runs:

- Whether the query syntax is valid.
- Whether fields exist in the schema.
- Whether required arguments are provided.
- Whether values can coerce to the GraphQL scalar/input type.
- Whether input objects contain undeclared fields.

For example, a client passes `quantity: "many"` while the schema declares `Int!`. GraphQL input coercion fails and the resolver is never invoked. That is a top-level GraphQL error.

By contrast, `quantity: 500` is a type-valid integer that may exceed available stock. That is business validation and belongs in `userErrors`.

Spring for GraphQL also supports Bean Validation via `@Valid` on arguments. When a constraint fails, `ConstraintViolationException` is thrown. Your application must decide explicitly whether to map that error to a top-level GraphQL error or convert it into payload `userErrors`; do not assume every `@Valid` failure automatically lands in the payload.

## 16. Using `@GraphQlExceptionHandler` for execution errors

Exceptions from annotated controllers can be handled using `@GraphQlExceptionHandler` inside the controller or a `@ControllerAdvice`.

Example mapping a system error:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class GraphQlExecutionErrorHandler {

    @GraphQlExceptionHandler
    GraphQLError handle(
            UnexpectedOrderServiceException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Unable to process request right now")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
    }
}
```

`GraphqlErrorBuilder` is prepared by Spring with the current `DataFetchingEnvironment`, preserving accurate path and location details. Never put internal exception messages or stack traces in the response.

For `DataFetcher`s outside annotated controllers, use `DataFetcherExceptionResolver` and register it with `GraphQlSource`. The Spring Boot starter auto-detects `DataFetcherExceptionResolver` beans.

## 17. Should you add `success: Boolean!` to payloads?

Some APIs define:

```graphql
type CreateOrderPayload {
    success: Boolean!
    order: Order
    userErrors: [UserError!]!
}
```

A `success` field is usually redundant when the contract already specifies:

- Success: `order` is present and `userErrors` is empty.
- Business rejection: `order` is null and `userErrors` is non-empty.

If `success` is added, the server must keep all three fields consistent in every scenario. Only add it when it represents a meaningful independent state that clients genuinely need. Do not use a boolean to replace error codes or business outcomes.

## 18. Should you use unions for mutation results?

Another design uses a union to model mutually exclusive outcomes:

```graphql
union CreateOrderResult = Order | OrderRejected

type OrderRejected {
    userErrors: [UserError!]!
}

type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderResult!
}
```

Clients must use inline fragments per concrete type:

```graphql
mutation CreateOrder($input: CreateOrderInput!) {
    createOrder(input: $input) {
        ... on Order {
            id
            status
        }
        ... on OrderRejected {
            userErrors {
                code
                message
                inputPath
            }
        }
    }
}
```

Unions make mutually exclusive variants explicit, which works well when each outcome has a very different structure. However, payload objects are usually easier to extend when returning extra metadata or related objects across both success and failure. Pick one pattern and keep it consistent across mutations in the same group.

## 19. Is `clientMutationId` required?

Relay-style mutations often pass `clientMutationId` in the input and echo the same value in the payload:

```graphql
input CreateOrderInput {
    customerId: ID!
    clientMutationId: String
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
    clientMutationId: String
}
```

This field helps clients correlate responses with submissions, especially in certain optimistic UI or Relay mutation workflows. It is not required by the GraphQL specification and does not provide idempotency on its own.

If clients do not use Relay or do not need an echoed correlation value, do not add this field merely because an older mutation template had it. To prevent duplicate creation on retries, use an idempotency key with explicit server-side semantics.

## 20. Idempotency for mutations with side effects

Clients may resend a mutation after a timeout or network drop without knowing whether the server succeeded. For creating orders, capturing payments, or booking reservations, blind retries can duplicate side effects.

You can add `idempotencyKey` to the input:

```graphql
input CapturePaymentInput {
    orderId: ID!
    amount: Float!
    idempotencyKey: String!
}
```

The server should clearly define:

1. Keys are scoped by actor/tenant and operation type.
2. Keys are stored alongside an input fingerprint and the processed outcome.
3. Retried requests with the same key and identical input return the recorded outcome.
4. Same key with different input must be rejected with a stable code such as `IDEMPOTENCY_KEY_REUSED`.
5. Recording the key and updating business state must remain consistent in the persistence layer.
6. Key retention duration and retry policies must be documented.

An idempotency key is not an access token and does not replace authorization. For payment providers, forward an appropriate idempotency key to the provider if their API supports it.

## 21. Concurrency and optimistic locking

Mutations updating an entity can collide with concurrent changes. The input can carry `expectedVersion`:

```graphql
input UpdateOrderInput {
    id: ID!
    expectedVersion: Int!
    note: String
}
```

If the current version differs from the version the client read, the use case returns `VERSION_CONFLICT` in the payload. The client reloads the latest data and decides whether to resubmit.

Do not include `updatedAt` or a version purely for decoration. The server must check the version condition inside a transaction—typically via optimistic locking or a conditional update statement. Otherwise, two concurrent requests can still overwrite each other.

## 22. Transactions and mutation semantics

A payload describes the API outcome; it does not provide transactions by itself. The application use case must define which operations require atomicity.

For example, creating an order may require:

1. Verifying the customer and products.
2. Checking inventory stock.
3. Creating the order and order lines.
4. Writing a reservation or updating stock.
5. Persisting the idempotency record.

Database changes requiring atomicity should execute inside a single use-case transaction. If business validation fails, never leave partial state behind.

A GraphQL request with multiple root mutation fields executes them sequentially, yet that does not automatically wrap those resolvers in a single transaction. If two steps must succeed or roll back together, create one mutation/use case encompassing both.

Do not hold a database transaction open while waiting on a slow remote payment gateway. When coordinating multiple systems, consider outbox, saga, idempotency, and compensation patterns.

## 23. Using `ArgumentValue` for partial updates

In update mutations, distinguish two states:

- Client omits the field: keep the existing value.
- Client sends the field with `null`: clear the existing value if permitted by the contract.

With a standard `@Argument`, both cases can bind to null. Spring for GraphQL provides `ArgumentValue<T>` to tell whether an argument was omitted or explicitly provided.

Example input DTO:

```java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateProductInput(
    String id,
    ArgumentValue<String> description
) {}
```

The use case can handle it:

```java
if (input.description().isOmitted()) {
    // Do not change description.
} else if (input.description().value() == null) {
    // Client requested clearing description.
} else {
    // Client sent a new description.
}
```

SDL must make `description` nullable so clients can pass null:

```graphql
input UpdateProductInput {
    id: ID!
    description: String
}
```

`ArgumentValue` is also supported on fields inside object arguments. Test omitted, explicit null, and concrete values so patch contracts are never misinterpreted.

## 24. Designing payloads for partial success

Not every mutation is all-or-nothing. For example, importing a product list might accept some rows while rejecting others. When business rules genuinely allow partial success, the payload should express partial outcomes clearly:

```graphql
type ImportProductsPayload {
    imported: [Product!]!
    rejected: [RejectedProduct!]!
    userErrors: [UserError!]!
}

type RejectedProduct {
    rowNumber: Int!
    inputPath: [String!]
    code: String!
    message: String!
}
```

The contract must state clearly whether each row has its own transaction or the entire import is atomic. Never return `success: true` when only part of the data was saved if clients have no way to tell which parts succeeded.

For mutations creating a single resource like `createOrder`, usually keep semantics simple: create completely or return business errors without leaving a half-created order behind.

## 25. Testing success payloads with `GraphQlTester`

Add test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The operation can be written with variables:

```graphql
mutation CreateOrder($input: CreateOrderInput!) {
    createOrder(input: $input) {
        order {
            id
            status
        }
        userErrors {
            code
            message
            inputPath
        }
    }
}
```

A success test should assert that `order` has data and `userErrors` is empty:

```java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;

@GraphQlTest(OrderMutationController.class)
@Import(GraphQlExecutionErrorHandler.class)
@WithMockUser(username = "alice")
class CreateOrderMutationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    CreateOrderUseCase createOrder;

    private static final String CREATE_ORDER_DOCUMENT = """
        mutation CreateOrder($input: CreateOrderInput!) {
            createOrder(input: $input) {
                order { id status }
                userErrors { code message inputPath }
            }
        }
        """;

    private Map<String, Object> input(int quantity) {
        return Map.of(
            "customerId", "customer-1",
            "items", List.of(Map.of(
                "productId", "product-1",
                "quantity", quantity
            ))
        );
    }

    @Test
    void returnsOrderAndEmptyUserErrorsOnSuccess() {
        given(createOrder.execute(any(CreateOrderCommand.class)))
            .willReturn(CreateOrderOutcome.success(
                new OrderSummary("order-101", "PLACED")
            ));

        GraphQlTester.Response response = graphQlTester.document(CREATE_ORDER_DOCUMENT)
            .variable("input", input(2))
            .executeAndVerify();

        response.path("createOrder.order.id")
            .entity(String.class)
            .isEqualTo("order-101");

        response.path("createOrder.userErrors")
            .entityList(UserError.class)
            .hasSize(0);
    }
}
```

This example uses `@GraphQlTest` from Spring Boot 3.x and `@MockitoBean` from Spring Framework 6.2 and later. `@WithMockUser` provides a principal for the resolver; the `spring-security-test` dependency is only needed when tests include Spring Security. `executeAndVerify()` verifies that the response has no top-level GraphQL errors, while the two assertions on the same `Response` check the outcome and the business error list.

In Spring Boot 4.x, `@GraphQlTest` moved to package `org.springframework.boot.graphql.test.autoconfigure`. `@MockitoBean` is part of Spring Framework 6.2 and later; for older projects, use the mock bean annotation corresponding to your Spring Boot version.

## 26. Testing business rejections in payloads

For a business rejection, GraphQL execution still succeeds, so do not call `errors().verify()` expecting a top-level error. Inspect the payload instead:

```java
@Test
void returnsUserErrorWhenStockIsInsufficient() {
    given(createOrder.execute(any(CreateOrderCommand.class)))
        .willReturn(CreateOrderOutcome.rejected(List.of(
            new BusinessViolation(
                "INSUFFICIENT_STOCK",
                "Insufficient product stock",
                List.of("items", "0", "quantity")
            )
        )));

    GraphQlTester.Response response = graphQlTester.document(CREATE_ORDER_DOCUMENT)
        .variable("input", input(200))
        .executeAndVerify();

    response.path("createOrder.order").valueIsNull();
    response.path("createOrder.userErrors[0].code")
        .entity(String.class)
        .isEqualTo("INSUFFICIENT_STOCK");
}
```

This is a continuation method inside `CreateOrderMutationTests` from the previous section. It executes the mutation once and checks both paths on the same response. Business rejections do not produce top-level GraphQL errors, so `executeAndVerify()` remains appropriate.

## 27. Testing top-level execution errors separately

When a use case throws a system exception, the test must verify a top-level GraphQL error without leaking internal messages:

```java
@Test
void reportsUnexpectedFailureAsGraphQlError() {
    given(createOrder.execute(any(CreateOrderCommand.class)))
        .willThrow(new UnexpectedOrderServiceException("database details"));

    GraphQlTester.Response response = graphQlTester.document(CREATE_ORDER_DOCUMENT)
        .variable("input", input(2))
        .execute();

    response.errors()
        .expect(error -> error.getMessage().equals("Unable to process request right now"))
        .verify();
}
```

This is a continuation method inside `CreateOrderMutationTests` from the previous section. The class imports `GraphQlExecutionErrorHandler` so the test slice uses the exception mapping. This test checks the boundary between business `userErrors` and execution errors. If the schema declares the mutation payload non-null, an execution error can make `data` null due to non-null propagation; tests should not assume the payload still exists after a system failure.

## 28. Testing contracts for older clients

When a payload is expanded, older operations should still run:

- If `warnings` is added, older clients not selecting that field remain valid.
- If `payment` is added, older clients can still select only `order` and `userErrors`.
- If `clientMutationId` is added, older operations not requiring that field still work.
- If an optional input field is added, older inputs remain valid.

Store representative mutation operations in test resources or a persisted operation registry so CI can re-run them after every schema change. Verify both schema diffs and runtime behavior; checking SDL alone does not prove resolvers return valid payloads.

## 29. Extending payloads without breaking clients

Dedicated payload types allow adding new fields additively:

```graphql
type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
    warnings: [MutationWarning!]!
    replayed: Boolean
}

type MutationWarning {
    code: String!
    message: String!
}
```

Older clients selecting only `order` and `userErrors` stay valid. Newer clients can select `warnings` or `replayed`.

When adding payload fields:

- Preserve the semantics of existing fields.
- Use nullable if data is not always available.
- If a list field can always return an empty list, use `[Type!]!` and ensure the resolver always returns a list.
- Never repurpose `userErrors` from business errors to system errors.
- Never alter a published error code to mean something else.
- Evaluate performance if the new field triggers extra service or database calls.

## 30. Authorization and sensitive information in payloads

Mutation payloads are returned to clients, so never expose internal details in `userErrors`:

- Never return SQL, stack traces, or internal exception class names.
- Never return sensitive stock figures if the user is not authorized to view them.
- Never return customer or payment data outside authorized scope.
- Never use `message` to reveal whether a resource exists if security policy requires concealing it.
- Never treat `customerId` in the input as proof the user is authorized to act on that customer.

Resolvers can obtain `Principal` from Spring Security and pass the actor ID into the use case. The application layer checks permissions on the specific resource. If returning a business rejection for unauthorized access, align that choice with the API's overall security policy; many systems still use top-level `FORBIDDEN` for authorization failures.

## 31. Common mistakes when designing mutation payloads

**Returning an entity directly and later discovering errors are needed.** Changing the return type forces clients to modify operations. Use a dedicated payload type from the start.

**Returning a boolean for every mutation.** Clients cannot tell what failed or what state the resource is in afterward. Return an object payload with outcomes and error details.

**Using an overly broad shared payload.** Unrelated nullable fields clutter the schema. Create dedicated payloads aligned with business actions.

**Using `userErrors` for system errors.** A database outage is not an input error. Let execution errors flow through GraphQL error handling.

**Putting client logic on `message`.** Messages change across languages and rewrites. Use a stable `code` for logic.

**Making `userErrors` nullable or allowing null items.** Clients end up handling too many states. Typically use `[UserError!]!` and return an empty list on success.

**Making the result field non-null when business rejections produce no result.** Non-null propagation can wipe out the payload. Use a nullable result field like `order: Order`.

**Adding required input fields or arguments to existing mutations.** Older clients become invalid. Start with optional or defaulted input fields.

**Treating `clientMutationId` as an idempotency key.** Echoing a correlation ID does not prevent duplicate execution. Server-side idempotency storage and semantics are required.

**Executing a mutation twice in one test to check two paths.** Can produce duplicate side effects. Capture one response and assert multiple paths.

**Using enum error codes without an unknown-value strategy.** Client exhaustive `switch` statements may fail on new codes. Consider string codes or fallbacks.

## 32. Mutation contract design checklist

- [ ] Mutation name clearly describes a business action.
- [ ] Mutation has a dedicated input object type and an `input` argument.
- [ ] Mutation returns a dedicated, evolvable payload type.
- [ ] Result field is nullable when business rejection produces no result.
- [ ] `userErrors` always returns a list, empty on success.
- [ ] Error codes are stable; `message` is never used as a machine contract.
- [ ] `inputPath` is kept distinct from top-level GraphQL error paths.
- [ ] Business rejections are separated from validation/coercion and system errors.
- [ ] Resolver invokes an application use case rather than implementing business rules directly.
- [ ] Transactions span the exact use case requiring atomicity.
- [ ] Mutations with side effects support idempotency when safe retries are required.
- [ ] Update mutations distinguish omitted vs. explicit null where needed.
- [ ] Authorization and tenant ownership are enforced server-side.
- [ ] `GraphQlTester` verifies success, business rejections, and execution errors.
- [ ] Contract tests confirm older operations still work after payload expansion.

## Conclusion

A mutation payload is the contract between clients and server-side business workflows. Use dedicated input objects, dedicated payload types, and result field nullability aligned with success/failure possibilities. Place business rejections in `userErrors` with stable codes and clear input paths; keep GraphQL syntax/coercion faults and system execution failures in top-level `errors`. In Spring for GraphQL, `@MutationMapping` should translate inputs into a command, call an application use case, and map the outcome into a payload. Test success, business rejections, and execution errors with `GraphQlTester`, while designing idempotency, concurrency, and transactions around actual side effects.

## References

- [GraphQL — Naming Conventions and Design Standards](https://www.graphql.org/learn/naming-design/)
- [GraphQL — Schema Design](https://graphql.org/learn/schema-design/)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Testing with GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Apollo — Designing GraphQL Mutations](https://www.apollographql.com/blog/designing-graphql-mutations)
- [Shopify — GraphQL API Design Tutorial](https://github.com/Shopify/graphql-design-tutorial/blob/master/TUTORIAL.md)
