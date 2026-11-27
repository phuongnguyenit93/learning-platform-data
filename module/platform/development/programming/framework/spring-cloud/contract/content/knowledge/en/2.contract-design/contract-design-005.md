# Choosing Representative Examples for Each Interaction Branch

## 1. Why Select Examples by Interaction Branch?

In **Spring Cloud Contract** (`SPRING_CLOUD_CONTRACT` module), the producer publishes behaviors that the consumer can rely on via HTTP or messaging contracts, described using Groovy DSL or YAML DSL. From the contracts, the tool can generate tests for the producer and stubs for the consumer to run independently; Stub Runner helps the consumer use published stubs during development and CI.

However, a contract describing only the happy path is usually not enough. The consumer also needs to know what happens when input is invalid, a resource does not exist, an operation is rejected, or a message leads to a different outcome. **Choosing representative examples for each interaction branch** means selecting a small set of cases that covers the *observable* outcomes that matter to the consumer.

After this lesson, you can:

- Distinguish API interaction branches from internal control-flow branches in source code.
- Build a scenario matrix covering input requirements, conditions, outcomes, and outcome consumers.
- Choose sample data that is representative, deterministic, and repeatable for writing Groovy/YAML contracts.
- Explain which branches need separate contracts and which should be verified with unit/integration tests.
- Connect selected contracts to producer tests, consumer stubs, and CI.

## 2. What Is an Interaction Branch?

An **interaction branch** is a class of scenarios where, at the service boundary, the caller receives a meaningfully different behavior: status code, body structure, headers, error type, or emitted message. For example, `201 Created` and `409 Conflict` are two distinct branches because the consumer may decide either to proceed with the workflow or report out-of-stock.

Conversely, two `if` branches inside a service that both return `200 OK` with the exact same data contract may simply be implementation details. They do not necessarily need two contracts. Spring Cloud Contract verifies **behavior at the integration boundary**, not line-by-line code coverage.

| Characteristic | Usually needs a separate contract example | Usually belongs to internal tests |
| --- | --- | --- |
| HTTP status code changes | `201` on creation success, `400` on invalid input | Two algorithms producing the same `201` result |
| Body shape or meaning changes | Success has `id`; failure has `code` | Changing how a DTO is built while JSON stays identical |
| Headers carrying integration semantics | `Location`, `Content-Type`, API version if committed | Headers used solely for internal monitoring |
| Messaging behavior changes | Emitting `RESERVED` vs. `REJECTED` to another consumer | Changing logging or cache storage |
| Access-control rules change | `401` vs. `403` if part of the public contract | Token-parsing details inside a security library |

> Principle: group by **outcomes the consumer must handle**, then choose at least one representative example per group. There is no need to turn every data combination into a contract.

## 3. Running Example: Order Service

Suppose a producer provides an ordering API with the following illustrative rules (these are **lesson design assumptions**, not default rules enforced by Spring Cloud Contract):

- `POST /api/orders` accepts JSON containing `productId` and `quantity` (positive integer).
- Product `SKU-001` exists and has sufficient stock; `SKU-OUT` exists but has insufficient stock.
- Successful creation returns `201`, JSON containing `id`, `status`, and a `Location` header.
- `quantity <= 0` returns `400` with `code = INVALID_QUANTITY`; out of stock returns `409` with `code = OUT_OF_STOCK`.
- `GET /api/orders/{id}` returns `200` when found and `404` with `ORDER_NOT_FOUND` when not found.
- If the service has authentication per its public contract, missing or invalid credentials are handled separately (`401`), while authenticated requests lacking permission may return `403`.

### 3.1. Build a branch matrix before writing DSL

| Branch | Input scenario / precondition | Observable outcome | Meaning for the consumer |
| --- | --- | --- | --- |
| Order created successfully | `POST`, `SKU-001`, `quantity = 2`, in stock | `201`, `id`, `status = CREATED`, `Location` | Navigate to order details screen |
| Invalid quantity | `POST`, `quantity = 0` | `400`, `code = INVALID_QUANTITY` | Show input validation error, do not retry the same request |
| Out of stock | `POST`, `SKU-OUT`, `quantity = 2` | `409`, `code = OUT_OF_STOCK` | Report business conflict, optionally suggest another quantity |
| Read existing order | `GET /api/orders/ord-1001` with seeded data | `200`, order details | Display order |
| Read non-existent order | `GET /api/orders/ord-missing` | `404`, `code = ORDER_NOT_FOUND` | Display not-found state |
| Unauthenticated | No credentials, if API requires them | `401`, published error format | Prompt login / refresh token |
| Insufficient permission | Valid auth but unauthorized, if applicable | `403`, published error format | Do not continue the forbidden action |

This matrix is a starting point for discussion with the API owner and consumer. Do not add `401`, `403`, or other error branches to contracts unless that behavior has been agreed upon.

### 3.2. Choose proper equivalence classes and boundary values

For `quantity`, inputs `2`, `5`, and `9` all illustrate the **valid** class when stock is available. Choosing `2` suffices for one representative contract. The value `0` sits right at the boundary between valid (`1`) and invalid (`0`) and is therefore better than an arbitrary invalid value like `-999` for testing the positive-number branch.

If the API also has a maximum limit, e.g. `quantity <= 100`, add the boundary pair `100`/`101` in an appropriate test. Only add a dedicated contract when the consumer has meaningful behavior relying on it, such as a distinct error code for exceeding the quota; remaining variations can be covered by unit or parameterized tests.

## 4. Turning Representative Examples into HTTP Contracts

In the examples below, each contract is a standalone file under the contracts directory configured by the project. Descriptive filenames reflect the branch, aiding traceability when producer tests or stubs fail. The Groovy DSL syntax uses Spring Cloud Contract's `Contract.make`.

### 4.1. Order creation success branch: `create_order_success.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'create_order_success'
    description 'Successfully creates an order when the product has sufficient stock'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body([
            productId: 'SKU-001',
            quantity : 2
        ])
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
            header 'Location': '/api/orders/ord-1001'
        }
        body([
            id    : 'ord-1001',
            status: 'CREATED'
        ])
    }
}
```

**Why is this example representative?** It captures the complete behavior the consumer needs on success: method, URL, request format, `201` status, response format, `id`, `status`, and `Location`. There is no need for another contract that merely changes `quantity` from `2` to `3` if both share the same API promise.

**Stability conditions:** The example uses a fixed `ord-1001` for readability; when running producer tests, you must prepare data and a controllable ID-generation mechanism (such as fixtures or test configuration), and reset state between runs. If IDs are dynamically generated in the real application, replace fixed-value matching with matchers or appropriate producer/consumer values, and ensure `Location` stays consistent with the returned ID.

### 4.2. Invalid input branch: `create_order_invalid_quantity.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'create_order_invalid_quantity'
    description 'Rejects quantity equal to 0'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body([
            productId: 'SKU-001',
            quantity : 0
        ])
    }

    response {
        status 400
        headers {
            contentType(applicationJson())
        }
        body([
            code   : 'INVALID_QUANTITY',
            message: 'quantity must be greater than 0'
        ])
    }
}
```

Input validation errors are a separate branch because the consumer needs to map `INVALID_QUANTITY` to the corresponding UI feedback. If `message` may be localized or reworded compatibly, the team should consider committing only to the error code and structure, using an appropriate matcher for the text instead of enforcing exact character matching.

This same contract can be written in **YAML DSL** instead of Groovy DSL (pick one representation per scenario to avoid duplicate registration):

```yaml
name: create_order_invalid_quantity
description: Rejects quantity equal to 0
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    productId: SKU-001
    quantity: 0
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
    message: quantity must be greater than 0
```

### 4.3. Business conflict branch: `create_order_out_of_stock.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'create_order_out_of_stock'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body([
            productId: 'SKU-OUT',
            quantity : 2
        ])
    }

    response {
        status 409
        headers {
            contentType(applicationJson())
        }
        body([code: 'OUT_OF_STOCK'])
    }
}
```

Even though both `400` and `409` are failure outcomes, they should not be merged. `400` indicates invalid input data; `409` indicates a conflict with current business state. The consumer may handle these two situations differently.

### 4.4. Not-found branch: `get_order_not_found.groovy`

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'get_order_not_found'

    request {
        method GET()
        url '/api/orders/ord-missing'
    }

    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body([code: 'ORDER_NOT_FOUND'])
    }
}
```

This example should accompany a `GET` contract returning `200` for an existing record, because a read API has at least two outcomes that the consumer distinguishes. The `404` branch is not equivalent to `400`: the request can be completely valid while the resource does not exist.

## 5. How to Avoid Overly Rigid or Overly Broad Contracts?

Representative examples must be concrete enough to generate deterministic stubs while avoiding accidentally turning incidental data into long-term commitments. Apply these principles:

1. **Stabilize inputs.** Use clearly named fixture data (`SKU-001`, `SKU-OUT`, `ord-missing`); define upfront which records exist, which do not, available stock levels, and required security state.
2. **Assert the fields the consumer actually uses.** If the consumer branches on `code`, check `code`. If it only needs `id` to have a valid format, there is no need to force the producer to use one fixed ID.
3. **Avoid overly broad matchers.** A `.*` regex across the entire body does not prove the producer maintains JSON structure. Narrow matchers to attributes that genuinely vary, such as `id`, timestamps, or transaction codes.
4. **Ensure stubs distinguish requests.** Two `POST /api/orders` contracts cannot differ only in filename while matching any body; Stub Runner may pick an unintended response. Conditions on `productId`, `quantity`, headers, or query parameters must sufficiently separate the branches.
5. **Do not rely on implicit state across contracts.** Producer tests may run in any order. Plain HTTP stubs do not automatically execute a multi-step business state machine. If the problem requires a `POST` followed by `GET` sequence, prepare independent fixtures or use dedicated integration tests for that stateful flow.

In Groovy DSL, when you need to accept multiple valid input IDs rather than a single value, you can use a matcher on the request:

```groovy
request {
    method GET()
    urlPath($(consumer(regex('/api/orders/ord-[0-9]+')),
               producer('/api/orders/ord-1001')))
}
```

The snippet above only illustrates that the **consumer-side stub** can match multiple URLs while the **producer test** still uses a concrete URL. Only apply this pattern when *every* ID matched by the regex truly belongs to the same behavioral class. For a `404` branch, a broad regex like this can easily intercept URLs meant for the `200` contract, so specific example paths or non-overlapping patterns are usually preferable.

## 6. Choosing Branches for Messaging Interactions

In a system with a message broker, the consumer observes not just HTTP responses, but also incoming/outgoing messages, destinations, and payloads. Suppose the inventory service receives messages from `orders.created` and publishes results to `inventory.reservations`:

| Branch | Input message | Committed output message |
| --- | --- | --- |
| Reservation succeeded | `orderId = ord-1001`, `productId = SKU-001`, `quantity = 2` | `result = RESERVED` |
| Insufficient stock | `orderId = ord-1002`, `productId = SKU-OUT`, `quantity = 2` | `result = REJECTED`, `reason = OUT_OF_STOCK` |

If these two events are agreed public behavior, choose two separate message contracts. Example for the success branch:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'inventory_reserved_after_order_created'

    input {
        messageFrom('orders.created')
        messageBody([
            orderId  : 'ord-1001',
            productId: 'SKU-001',
            quantity : 2
        ])
    }

    outputMessage {
        sentTo('inventory.reservations')
        body([
            orderId: 'ord-1001',
            result : 'RESERVED'
        ])
    }
}
```

In the `REJECTED` branch, the input uses the out-of-stock fixture and the output carries `result = REJECTED`, `reason = OUT_OF_STOCK`. Cases where the specification says **emit no message at all** should be thoroughly tested with integration tests or appropriate observability mechanisms; do not interpret the absence of `outputMessage` as proof that *not* emitting an event was verified.

Destination, payload format, correlation headers (`correlationId` if applicable), and retry/duplicate semantics must be agreed upon with the consumer whenever they impact compatibility. Do not assume every system shares the same topic names or delivery mechanisms as the example.

## 7. From Branch Matrix to Producer Tests, Stubs, and CI

A practical workflow aligned with learning Spring Cloud Contract:

1. **Finalize the matrix with the consumer.** Each row has preconditions, representative request/message, expected outcome, and how the consumer uses the outcome. Mark mandatory branches versus assumptions requiring confirmation.
2. **Create one contract per distinguishable behavior.** Use names describing the branch (`create_order_success`, `create_order_invalid_quantity`); pick Groovy DSL or YAML DSL according to project conventions.
3. **Set up fixtures and generate producer tests.** Run the build step integrated with Spring Cloud Contract to generate/run the corresponding tests. When the producer changes `409` to `200` or drops `code`, the test for that branch must report an error.
4. **Generate and publish stubs from the same verified contracts.** The consumer uses Stub Runner to run tests covering success/error scenarios without starting the real producer. Stubs must have distinct enough request conditions so the consumer can intentionally trigger each branch.
5. **Verify in CI.** The producer pipeline verifies contracts before publishing stub artifacts; the consumer pipeline tests against the selected stub version. When contracts change, both sides must confirm the new behavior before bumping dependency versions.

An example of a valuable consumer test is: when the stub returns `409` with `OUT_OF_STOCK`, the application does not navigate to the order-created page and instead displays an out-of-stock notice. This test verifies **the consumer's decision** based on the contract-described outcome, rather than merely checking whether the stub returned JSON.

## 8. Common Mistakes When Selecting Examples

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Recording only `200`/`201` branches | Consumer lacks stubs for critical error cases | Add branches that differ in status code, error code, or event |
| One contract for all input values | Stub easily returns the wrong branch; tests don't prove rules | Use data and matcher conditions that clearly separate scenarios |
| One contract for every number in the same equivalence class | Contract suite bloats and becomes hard to maintain | Pick representatives and boundaries; move the rest to unit/parameterized tests |
| Depending on leftover database state from previous runs | Producer tests flake in CI | Prepare and clean up independent fixtures per test |
| Exact-matching random IDs or timestamps | Producer tests fail even when behavior is compatible | Use bounded matchers or controlled generated data |
| Forgetting `Content-Type`, `Location`, or `code` used by consumer | Contract fails to protect critical integration behavior | List fields/headers the consumer needs and add them to assertions |
| Merging `400` and `409` errors because both are failures | Consumer loses the ability to distinguish handling logic | Keep branches with distinct business meanings separate |

## 9. Self-Check Practice Exercise

Suppose the `POST /api/orders` API adds a rule: maximum `quantity` is `10`, and when `quantity > 10` it returns `422` with `code = QUANTITY_LIMIT_EXCEEDED`.

1. Add a row to the matrix with input `quantity = 11`, status `422`, error code, and expected consumer behavior. Because there is a **new error code and handling path**, this branch needs its own contract.
2. Choose `quantity = 10` as the valid boundary value to verify with an appropriate test; you do not necessarily need a new contract if the outcome matches the order creation success branch.
3. Write the contract `create_order_quantity_limit_exceeded` (Groovy or YAML) asserting `422` and `QUANTITY_LIMIT_EXCEEDED`; ensure the product fixture has enough stock so the quantity limit rule is the direct cause of the error.
4. Simulate the consumer receiving `422` from Stub Runner, verifying the app suggests lowering the quantity instead of retrying the unchanged request.

**Checklist before finalizing a contract suite:** each branch has a distinct observable outcome; requests are specific enough to select the right stub; fixture data is reproducible; critical fields and headers are asserted; dynamic fields are not arbitrarily locked; every scenario has a clear testing purpose; new branches are wired into CI.

When examples are selected this way, the contract suite serves both as shared behavioral documentation between producer and consumer and as an early warning layer for incompatible API changes.
