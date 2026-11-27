# Designing Contracts for Success, Errors, and Empty Data

## Learning Objectives

In **Spring Cloud Contract**, a contract is a testable description of an interaction between a **producer** (the service providing an API or emitting messages) and a **consumer** (the party using the API or receiving messages). After this lesson in the **Contract Design** chapter, you can:

- Classify responses into **success with data**, **success with no results**, and **error** according to business semantics.
- Choose appropriate HTTP statuses, headers, and body structures so the consumer can handle every branch.
- Write **Groovy DSL** and **YAML DSL** examples for key scenarios in Spring Cloud Contract.
- Understand how contract tests are generated on the producer side, how stubs serve consumers via **Stub Runner**, and how CI catches incompatible API changes.
- Avoid contracts that are too loose, too rigid, or missing edge cases.

## 1. Why Must You Design All Three Response Groups?

Suppose the system has:

- **Catalog Service**: producer providing an API to search and retrieve products.
- **Shopfront Service**: consumer displaying product lists and details.

Defining only the “product exists, return `200 OK`” case is insufficient. The consumer also needs to know what happens when a filter yields no results, a user queries a non-existent product ID, or a parameter is invalid.

Example published API:

| Scenario | HTTP request | Agreed outcome | What the consumer should do |
|---|---|---|---|
| Products exist in category | `GET /api/products?category=books` | `200 OK` and array of products | Display the list |
| No matching products | `GET /api/products?category=no-match` | `200 OK` and empty array `[]` | Display a “no results yet” state |
| Malformed category parameter | `GET /api/products?category=INVALID!` | `400 Bad Request` and error code `INVALID_CATEGORY` | Display or handle the input error |
| Querying a non-existent ID | `GET /api/products/P-404` | `404 Not Found` and error code `PRODUCT_NOT_FOUND` | Display “product not found” |

In this example, `category` only accepts lowercase letters and hyphens; `no-match` is syntactically valid but currently has no products. These paths and error codes are **illustrative conventions** agreed by the two teams, not mandatory rules for every API.

Key takeaway: **“no results found in a collection” is not equivalent to “the resource path does not exist”, and both differ from “invalid request”.**

## 2. Define the Contract Boundary Before Writing DSL

A contract should describe **what the consumer observes** at the communication boundary, rather than the producer's internal structure.

| Needs design/verification | Example | Do not hardcode if the consumer doesn't depend on it |
|---|---|---|
| Method, URL, query parameters | `GET`, `/api/products`, `category` | Controller name or Java method name |
| HTTP status per scenario | `200`, `400`, `404` | How the service queries the database |
| Contract-relevant headers | `Content-Type: application/json` | Infrastructure headers meaningless to the consumer |
| JSON shape and data types | `id` is string, `price` is number | Ordering of JSON properties |
| Stable error code and handling semantics | `INVALID_CATEGORY` | Stack trace content, exception class name |
| Empty-case representation | `[]`, `null`, omitted field, or `204` | Specific demo values when values vary |

Before writing a contract, clarify four questions:

1. **Which branches does the consumer distinguish?** For example: results found / no results / input error / ID not found.
2. **What does each branch mean?** Is zero search results a normal business state or an error?
3. **Which fields does the consumer rely on?** For instance `id`, `name`, `price`, `code`, their data types, and whether they are required.
4. **Which changes break expectations?** For instance changing `[]` to `null`, or changing status `404` to `200` with an error body.

An HTTP contract typically needs to describe at least: **request** (method, path, query, headers/body if any) and **response** (status, headers, body). Matchers help verify types or formats without necessarily locking every sample value.

## 3. Designing a Successful Response with Data

For category `books`, the producer returns:

~~~http
GET /api/products?category=books HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[
  {
    "id": "B-101",
    "name": "Java Fundamentals",
    "price": 150000
  }
]
~~~

Decisions that must be agreed upon include: this is a **JSON array**, each item has `id` (string), `name` (string), `price` (number), and price has a well-defined meaning (e.g., monetary amount in the currency unit specified by the API). Without a semantic agreement on price, both sides can parse the JSON cleanly yet miscalculate totals.

### Groovy DSL: success with data

Example of a standalone file, `src/test/resources/contracts/products/listBooks.groovy`, in a project configured with Spring Cloud Contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'List of products belonging to category books'

    request {
        method 'GET'
        urlPath('/api/products') {
            queryParameters {
                parameter 'category': 'books'
            }
        }
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body([
            [
                id: 'B-101',
                name: 'Java Fundamentals',
                price: 150000
            ]
        ])
        bodyMatchers {
            jsonPath('$[0].id', byRegex('B-[0-9]+'))
            jsonPath('$[0].price', byType())
        }
    }
}
~~~

**How to read it:**

- `urlPath` with `queryParameters` specifies the path and parameter value to which this scenario applies.
- `status 200` and `contentType(applicationJson())` represent a successful JSON response.
- `body` provides a valid sample: an array containing one product.
- `bodyMatchers` state the rules when verifying the producer response: ID matches `B-` followed by digits, and price matches the sample's data type. Depending on the DSL, matchers can be added for other varying fields.

If the real application may return multiple products, decide whether the consumer depends on **item count or ordering**. Do not accidentally turn “always exactly one item with a fixed ID” into an unintended requirement. Fixed samples give stubs concrete data, but covering sorting, pagination, or multiple items requires designing additional scenarios and appropriate matchers.

## 4. Designing a Successful Response with Empty Data

The consumer searches for products with a **valid** category that currently has no products:

~~~http
GET /api/products?category=no-match HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

In the illustrative contract, `200 OK` + `[]` means: **valid query, processed successfully, but zero matching records**. It is still a list, keeping a consistent data type with the non-empty case.

### Groovy DSL: empty list

Saved in a separate file `src/test/resources/contracts/products/listNoMatch.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Valid category with no products'

    request {
        method 'GET'
        urlPath('/api/products') {
            queryParameters {
                parameter 'category': 'no-match'
            }
        }
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body([])
    }
}
~~~

The line `body([])` is crucial: it represents an **empty JSON array**, distinct from an absent body, an empty string `""`, an empty object `{}`, or JSON `null`. For list-oriented data, maintaining a consistent array type typically means fewer branches in consumer code.

### Non-equivalent ways to represent “empty”

| Response | Possible intended meaning | What the consumer must watch out for |
|---|---|---|
| `200` + `[]` | List query succeeded, 0 items | Still deserializes a JSON array |
| `200` + `{}` | Valid object with no properties, if defined by API | Cannot arbitrarily substitute for an array |
| `200` + `null` | Value represented as JSON null, if allowed by contract | Consumer must accept null, different from an empty list |
| `200` + omitted field | Field may be optional | Consumer must know whether missing field differs from `null` |
| `204 No Content` | Request succeeded, no response body | Consumer **must not** attempt to parse `[]` or JSON from the body |
| `404 Not Found` | Identified resource does not exist | Usually has a dedicated handling branch for “not found” errors |

Choosing between `200 []` and `204` must come from **API semantics and consumer agreement**. Once `200 []` is published, switching to `204` just because “it also means no data” can break consumers expecting a JSON array. With `204`, do not declare a response body in the contract.

If a paginated API returns an object shaped like `{ "items": [], "total": 0 }`, the empty case must preserve that exact **published pagination shape**, not switch arbitrarily to `[]`.

## 5. Designing Errors for Invalid Requests

In our example, `category` may only contain lowercase letters and hyphens. Thus, `INVALID!` is malformed; this is an **input error**, not a valid empty category.

~~~http
GET /api/products?category=INVALID! HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "INVALID_CATEGORY",
  "message": "category must contain lowercase letters or hyphens"
}
~~~

The consumer should be able to branch on a **machine-readable error code** such as `INVALID_CATEGORY`. The `message` field is for explanation or display when appropriate; do not branch on English prose because wording may be revised or localized.

### Groovy DSL: 400 error

Saved in `src/test/resources/contracts/products/invalidCategory.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Rejects malformed category parameter'

    request {
        method 'GET'
        urlPath('/api/products') {
            queryParameters {
                parameter 'category': 'INVALID!'
            }
        }
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 400
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVALID_CATEGORY',
            message: 'category must contain lowercase letters or hyphens'
        )
    }
}
~~~

The contract above protects **one concrete invalid case**. It does not prove every invalid input is rejected. If the producer must reject missing, blank, overly long, or other special-character query parameters, add scenarios or matchers aligned with business rules.

### Designing a stable error body

Agree on a consistent error template across endpoints, such as:

~~~json
{
  "code": "INVALID_CATEGORY",
  "message": "category must contain lowercase letters or hyphens"
}
~~~

You can add `requestId` for tracing, `details` for field-level errors, or `retryable` if that is an official commitment. Specify which fields are required, their types, and when they appear. Avoid locking the contract to dynamic timestamps, random IDs, or dynamic error text via exact string matching if the consumer does not rely on them; use matchers if format validation is needed.

Do not expose stack traces or internal implementation details in the error body. For authentication or authorization failures, distinguish `401 Unauthorized` from `403 Forbidden` per protocol semantics; for downstream dependency failures, consider `503 Service Unavailable` if the consumer has fallback or retry logic. Only include cases the consumer actually needs and can verify.

## 6. Designing Errors When a Resource Does Not Exist

Now consider retrieving **a single product by ID**:

~~~http
GET /api/products/P-404 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "PRODUCT_NOT_FOUND",
  "message": "Product does not exist"
}
~~~

This differs from a list query returning an empty array. The consumer is requesting **a specific resource** that does not exist in the system; if the API specifies `404`, the consumer can transition to a “product not found” screen.

### YAML DSL: 404 error

Spring Cloud Contract also supports defining contracts using **YAML DSL**. Example file `src/test/resources/contracts/products/productNotFound.yml`:

~~~yaml
description: Product by ID does not exist
request:
  method: GET
  url: /api/products/P-404
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: PRODUCT_NOT_FOUND
    message: Product does not exist
~~~

YAML expresses the same core components as Groovy DSL: request, response, status, headers, body. Pick one format per project conventions; there is no need to maintain duplicate files for one scenario just to “cover both DSLs”.

Do not reuse the same `404` to mask empty datasets, validation errors, and infrastructure failures if the consumer needs to handle them differently. Error codes and semantics must be unambiguous.

## 7. Decision Flow When Designing Contracts

When unsure between statuses, you can apply the following flow:

~~~mermaid
flowchart TD
    A["Receive request"] --> B{"Is request valid?"}
    B -- "No" --> C["400 + validation error code"]
    B -- "Yes" --> D{"Querying a specific ID?"}
    D -- "Yes" --> E{"Does resource exist?"}
    E -- "No" --> F["404 + not-found error code"]
    E -- "Yes" --> G["200 + object"]
    D -- "No, list query" --> H{"Any results?"}
    H -- "Yes" --> I["200 + non-empty array"]
    H -- "No" --> J["200 + empty array []"]
~~~

**Note:** This is a **design decision for the illustrative API**, not a mandatory standard flowchart for every system. Some APIs return `204` for successful operations with no content, `201` when creating a resource, or `202` when accepting asynchronous processing. What matters is that every branch is clearly and consistently defined in the contract.

Before finalizing, answer:

- For success cases, does the JSON shape stay stable regardless of record count?
- When there are no results, does the consumer receive `[]`, `204`, or a pagination object? Is there one exact convention?
- For errors, are status and `code` sufficient for the consumer to choose its handling path?
- Are error codes, data types, field names, and paths covered in the agreed contract tests?
- Do scenarios **distinguish requests clearly** so stubs pick the right response?

## 8. How Spring Cloud Contract Verifies All Three Branches

The three scenario types are defined in separate contract files. Once the plugin and test infrastructure are configured appropriately:

1. **Producer runs generated contract tests.** Spring Cloud Contract generates tests from contracts, sends requests to the producer application or HTTP test layer, and checks status, headers, and body against expectations.
2. **Producer publishes stubs.** The build packages stubs corresponding to verified contracts into an artifact; the workflow typically integrates with Maven or Gradle.
3. **Consumer runs tests with Stub Runner.** The consumer uses Stub Runner to download or start the right stub version, sends its own requests, and verifies success, empty, and error handling branches.
4. **CI detects incompatible changes.** The producer pipeline fails if the implementation drifts from the contract; the consumer pipeline fails if consumer code mishandles the responses from the stub it uses.

Examples of consumer expectations to verify:

| Consumer test | Request sent to stub | Expectation on consumer code |
|---|---|---|
| `shouldDisplayBooks` | `category=books` | Displays products from result array |
| `shouldShowEmptyState` | `category=no-match` | Receives `[]` and displays “no results”, does not throw a system error |
| `shouldHandleInvalidCategory` | `category=INVALID!` | Receives `400` and handles `INVALID_CATEGORY` |
| `shouldHandleUnknownProduct` | `/api/products/P-404` | Receives `404` and handles `PRODUCT_NOT_FOUND` |

To test against an HTTP stub started by Stub Runner on a configured port, the consumer must call **the stub's address** (not the real producer). Artifact coordinates, ports, stub retrieval modes, and versions depend on the project.

**Warning about stub representativeness:** consumer tests passing against a stub do not prove the real producer honors the contract; you need passing generated contract tests on the producer side. Conversely, green producer tests alone do not verify all consumer-side logic.

**Warning about versions:** if a consumer continues testing against an old stub, pipelines can stay green even after the producer changes its interface. CI needs a policy to synchronize/verify contract and stub versions, along with an approval process for breaking changes.

## 9. Common Design Mistakes

| Design mistake | Consequence | How to improve |
|---|---|---|
| Having only success contracts | Consumer is unprotected on error/empty branches | Design a test matrix from consumer behavior |
| Returning `404` for a valid list query with zero results when docs promise `200 []` | Consumer treats empty state as an error | Preserve the published semantics and status |
| Returning `200` with `null` after publishing a JSON array | Consumer may fail when iterating the list | Keep a consistent `[]` shape |
| Returning `200` with an `error` field instead of an agreed error HTTP status | Consumer may treat an error as success | Use consistent status codes and error body |
| Branching on natural-language error messages | Copy edits or localization break the consumer | Check stable machine-readable error codes |
| Hardcoding timestamps, UUIDs, random data | Producer tests fail when valid dynamic data varies | Use matchers for appropriate formats/types |
| Overly broad matchers ignoring critical fields | Fails to detect type changes or missing fields | Explicitly constrain fields the consumer depends on |
| Stubs out of sync with upcoming producer release | Tests are green yet real integration fails | Manage versions and integrate verification in CI |

## 10. Self-Assessment Practice Exercise

New requirement: Shopfront displays products for the `electronics` category. The producer team wants to add pagination and change the empty-category response from `[]` to:

~~~json
{
  "items": [],
  "total": 0
}
~~~

Answer:

1. **Could this change break the consumer?** Yes. The shape changes from an array to an object; a consumer parsing a list directly can break even though the status remains `200`.
2. **Which scenarios need new contracts?** At least non-empty list and empty list in the paginated shape. If the consumer uses pagination, add interactions with `page`, `size` query params and related constraints.
3. **In what order should producer and consumer roll out?** Agree on the new contract, consider keeping the old format or versioning the API, let the consumer migrate and test against the new stubs before retiring the old interface.
4. **What if `page=-1`?** If the API defines `page` as non-negative, create a validation contract—for example `400` with error code `INVALID_PAGE`. Do not confuse an invalid request with an empty result page.

### Self-check questions

- When is `200 []` more appropriate than `404`?
- Why does `204` differ from `200 []` from the consumer's perspective?
- Which parts of an error response must remain stable for consumer code to handle?
- What bugs in the empty branch can a success-with-data contract miss?
- Why do we need both producer-side generated contract tests and consumer-side tests with stubs?

## Remember

**Design contracts around behavior the consumer actually needs:** success with data, success with empty data, and errors are distinct outcomes that must have **consistent semantics, HTTP statuses, and bodies**. Spring Cloud Contract lets you express them in Groovy/YAML DSL, generating producer tests and stubs to run consumer tests via Stub Runner. Putting these checks together with stub version management in CI lets teams catch expectation-breaking changes early instead of discovering them only after live integration.
