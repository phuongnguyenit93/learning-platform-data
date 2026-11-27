# JSON Response Body and Data Structures

## 1. Why Is JSON Response Structure an Important Part of the Contract?

In a microservices system, an API can continue returning HTTP `200 OK` yet still break consumers if the JSON structure changes. For example, `Order Service` previously returned:

~~~json
{
  "orderId": "ORD-123",
  "totalAmount": 250000,
  "paid": true
}
~~~

After a refactor, the producer changes it to:

~~~json
{
  "id": "ORD-123",
  "totalAmount": "250000",
  "paid": "true"
}
~~~

Even though the status has not changed, a consumer reading `orderId` or decoding `totalAmount` as a number will fail. This is an **incompatible change at the HTTP boundary**.

**Spring Cloud Contract** allows the producer and consumer to agree on verifiable expectations: HTTP status, headers, and **response body**. Contracts can be written in the **Groovy DSL** or **YAML DSL**. The plugin generates tests that run on the producer side to detect when behavior no longer satisfies the contract; once the producer passes verification, stubs are published for the consumer to use via Stub Runner. In CI, this toolchain helps catch API changes earlier when teams deploy independently.

This lesson belongs to the **Response HTTP** chapter and focuses on **JSON response body and data structures**: writing contracts for objects, arrays, value types, nested fields, dynamic values, and error responses.

After this lesson, you will be able to:

1. Distinguish HTTP status, `Content-Type`, and JSON response body content.
2. Express JSON objects, arrays, and nested structures using the Groovy/YAML DSL.
3. Properly check String, number, boolean, `null`, and absent fields.
4. Use JSONPath and matchers to balance stability with breaking-change detection.
5. Organize meaningful success/error responses for the consumer.
6. Understand which verifications are generated for the producer and how to integrate them into CI pipelines.

> **Principle:** A contract should protect the parts of the response that the consumer truly depends on. Do not copy the producer's entire internal structure into a rigid snapshot if the consumer does not need those fields.

## 2. Three Layers to Read in an HTTP Response

Example full response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 250000
}
~~~

| Layer | Example | What the Consumer May Depend On |
| --- | --- | --- |
| HTTP status | `200` | Distinguish success, not found, invalid data |
| Response headers | `Content-Type: application/json` | Choose how to decode the body and related metadata |
| Response body | `orderId`, `status`, `totalAmount` | Access fields, validate types, and run business logic |

At the HTTP level, status and body are two distinct things:

- `200` with a fake error JSON in the body can cause the client to misbehave if the contract commits to success data.
- `404` with JSON containing a `code` field may need its own contract if the consumer reads the error code for display or retry decisions.
- `204 No Content` normally **has no body**. Do not create a meaningful JSON body for a `204` response.
- `Content-Type` must match the actual body; a JSON body does not necessarily mean the server declared the right media type.

### 2.1. Response Bodies Can Have Many Shapes

JSON is not required to be an object at the root level:

~~~json
{"id":"ORD-123","status":"CONFIRMED"}
~~~

~~~json
[
  {"id":"ORD-123","status":"CONFIRMED"},
  {"id":"ORD-456","status":"PENDING"}
]
~~~

~~~json
{
  "data": [
    {"id":"ORD-123","status":"CONFIRMED"}
  ],
  "page": {
    "number": 0,
    "size": 20
  }
}
~~~

The examples are, respectively, a **root object**, a **root array**, and an **object containing an array plus pagination metadata**. A consumer designed for `List<Order>` will not automatically understand a response changed to `{"data":[...]}`.

## 3. Writing JSON Responses with the Groovy DSL

A simple HTTP contract to start with:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')

    request {
        method 'GET'
        url '/api/orders/ORD-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 250000,
            paid: true
        )
    }
}
~~~

Here:

- `response { ... }` describes the result the producer must return.
- `status OK()` expresses HTTP `200`.
- `contentType(applicationJson())` describes a JSON-compatible `Content-Type` header.
- `body(...)` holds the JSON fields the consumer needs.
- `'ORD-123'`, `250000`, and `true` are String, number, and boolean respectively.

Corresponding JSON:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 250000,
  "paid": true
}
~~~

**You do not need to write a raw JSON string to describe a simple object.** In the Groovy DSL, the `body(key: value, ...)` syntax is very convenient, especially when nesting maps, lists, and matchers.

### 3.1. Root-Level Object Using a Map

Writing explicitly with a Groovy map also works:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body([
        orderId: 'ORD-123',
        status: 'CONFIRMED',
        totalAmount: 250000
    ])
}
~~~

Both `body(orderId: ..., status: ...)` and `body([orderId: ..., status: ...])` represent a JSON object at the data level. Pick one style so contracts across the project are easy to read and edit.

### 3.2. Is Writing Only the Body Enough?

Not necessarily. If a contract omits `Content-Type`, producer tests may fail to protect the media type the consumer relies on. If status is omitted, the contract does not fully describe the HTTP response.

A typical response contract should include:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        // Fields used by the consumer
        orderId: 'ORD-123'
    )
}
~~~

Special cases such as file downloads, plain text, or binary bodies need different descriptions. Do not set `application/json` on a non-JSON response just to make tests run easily.

## 4. JSON Data Types: String, Number, Boolean, and Null

Example:

~~~groovy
body(
    orderId: 'ORD-123',
    quantity: 3,
    price: 49.95,
    delivered: false,
    promotionCode: null
)
~~~

Represented JSON body:

~~~json
{
  "orderId": "ORD-123",
  "quantity": 3,
  "price": 49.95,
  "delivered": false,
  "promotionCode": null
}
~~~

| Field | JSON Type | A Change That Can Break the Consumer |
| --- | --- | --- |
| `orderId` | String | Returning a number or deleting/renaming the field |
| `quantity` | Number | Changing from `3` to `"3"` |
| `price` | Number | Changing to a formatted currency string without agreement |
| `delivered` | Boolean | Changing `false` to `"false"` |
| `promotionCode` | Null | Changing to string `"null"` or removing the field when the client needs to distinguish them |

### 4.1. Numeric Values and Monetary Formats

If the producer returns:

~~~json
{"totalAmount": 250000}
~~~

then `totalAmount` is a number. The following response has a different type:

~~~json
{"totalAmount": "250000"}
~~~

For monetary data, the contract should clarify **the unit and meaning of the number**, for instance `250000` is the amount in VND. A number might use `Integer`, `Long`, or `BigDecimal` in the Java application; JSON only has the `number` type at the data level. Consumers may need additional commitments on value ranges, precision, and rounding rules.

Generated tests check expectations according to the chosen DSL and matchers; do not assume that checking a sample value automatically proves all business constraints on monetary amounts. Rules like `totalAmount >= 0` still need unit/domain tests.

### 4.2. Boolean vs. String

~~~groovy
body(
    paid: true,
    cancelled: false
)
~~~

is different from:

~~~groovy
body(
    paid: 'true',
    cancelled: 'false'
)
~~~

The second response has String values. If the consumer uses a strongly typed parser such as `boolean paid`, this can be a breaking change.

### 4.3. Null, Absent Fields, and Empty Strings

The following three JSON payloads have different meanings:

~~~json
{"couponCode": null}
~~~

~~~json
{}
~~~

~~~json
{"couponCode": ""}
~~~

- `null`: the field is present with a null value.
- Absent field: the object does not contain the `couponCode` key.
- Empty string `""`: the field is present with a 0-character String value.

In a contract, `couponCode: null` describes **a field with a null value**, not an arbitrary optional field. If the consumer has different requirements for these three cases, define appropriate scenarios and check the real data policy.

## 5. Nested JSON Objects with Groovy Maps

Many APIs return nested objects to represent related entities:

~~~json
{
  "orderId": "ORD-123",
  "customer": {
    "id": "CUS-7",
    "name": "Lan"
  },
  "delivery": {
    "address": {
      "city": "Da Nang",
      "postalCode": "550000"
    },
    "priority": false
  }
}
~~~

In the Groovy DSL:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 'ORD-123',
        customer: [
            id: 'CUS-7',
            name: 'Lan'
        ],
        delivery: [
            address: [
                city: 'Da Nang',
                postalCode: '550000'
            ],
            priority: false
        ]
    )
}
~~~

How to read it:

1. `body(...)` is the **root object**.
2. `customer: [ ... ]` is a **child object**.
3. `delivery: [address: [...], priority: false]` is an **object nested inside an object**.
4. Map keys become JSON field names, while values retain their appropriate types.

### 5.1. JSON Keys That Are Not Valid Groovy Identifiers

If the real API has fields containing hyphens or dots, quote the keys:

~~~groovy
body([
    'order-id': 'ORD-123',
    'trace.id': 'TRACE-9',
    customer: [
        'display-name': 'Lan'
    ]
])
~~~

Corresponding JSON:

~~~json
{
  "order-id": "ORD-123",
  "trace.id": "TRACE-9",
  "customer": {
    "display-name": "Lan"
  }
}
~~~

Later when writing JSONPath matchers, special characters in field names usually require bracket notation, such as `$['trace.id']`, instead of dot-separated property paths.

### 5.2. Empty Maps

~~~groovy
body(
    metadata: [:]
)
~~~

is equivalent to:

~~~json
{"metadata": {}}
~~~

Note that `[:]` is an **empty map** in Groovy. `[]`, on the other hand, is an **empty list**, producing a JSON array `[]`. Mixing up these two types is a structural mistake that easily slips past if you only skim text logs.

## 6. JSON Arrays: Nested Lists and Root Lists

An order can contain multiple line items:

~~~json
{
  "orderId": "ORD-123",
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-7", "quantity": 1, "unitPrice": 10000}
  ]
}
~~~

In Groovy:

~~~groovy
body(
    orderId: 'ORD-123',
    items: [
        [sku: 'BK-1', quantity: 2, unitPrice: 50000],
        [sku: 'PEN-7', quantity: 1, unitPrice: 10000]
    ]
)
~~~

- The outer square brackets of `items` create a **list**.
- Each element `[sku: ..., quantity: ...]` is a **map**.
- JSON arrays are ordered. If ordering is part of the commitment, changing element positions can affect the consumer.

### 6.1. Root Arrays

Not every response has an outer wrapper object. For example, the producer returns a list directly:

~~~json
[
  {"sku": "BK-1", "available": true},
  {"sku": "PEN-7", "available": false}
]
~~~

The Groovy DSL can express a list at the root body level:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body([
        [sku: 'BK-1', available: true],
        [sku: 'PEN-7', available: false]
    ])
}
~~~

Do not write `body(items: [...])` if the API actually returns a root array; that changes the schema to:

~~~json
{
  "items": [
    {"sku": "BK-1", "available": true},
    {"sku": "PEN-7", "available": false}
  ]
}
~~~

The consumer can decode a root array as `List<Product>`, whereas it cannot automatically understand a newly introduced wrapper object.

### 6.2. Empty Lists, Null, and Absent Fields

For the `items` field, the three scenarios below are not equivalent:

~~~json
{"items": []}
~~~

~~~json
{"items": null}
~~~

~~~json
{}
~~~

If the consumer displays a "no items" state when `items: []`, yet treats `items: null` as a data error, the contract must clarify the exact behavior. Do not casually swap `[]` for `null` just because both "contain no elements".

### 6.3. How Many Elements Does an Array Have?

A fixed body might illustrate an example with two elements. Yet a search service can return 0–20 elements depending on the data. Decide what the consumer depends on:

- **An exact fixed set of elements**, such as agreed configuration item codes.
- **A variable-length list**, where the consumer mainly needs element types, required fields, and pagination limits.
- **Sort order**, if the API advertises a sort order and the consumer relies on it.
- **Pagination**, if the consumer relies on `totalElements`, `page`, or `hasNext`.

Variable-length cases need appropriate matchers or scenarios rather than taking a snapshot of one arbitrary response as a fixed rule for every call.

## 7. The Same Response Body with the YAML DSL

Spring Cloud Contract supports representing HTTP contracts in YAML. Example response with nested objects and arrays:

~~~yaml
name: get_order_detail
description: Consumer views order details
request:
  method: GET
  url: /api/orders/ORD-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-123
    status: CONFIRMED
    paid: true
    totalAmount: 110000
    customer:
      id: CUS-7
      name: Lan
    items:
      - sku: BK-1
        quantity: 2
        unitPrice: 50000
      - sku: PEN-7
        quantity: 1
        unitPrice: 10000
~~~

In YAML:

- A **mapping** under `body` corresponds to a JSON object.
- Items prefixed with `-` under `items` correspond to a JSON array.
- `true` and `110000` are boolean and number; `ORD-123` is a string.
- Indentation determines nesting structure, so it must be consistent.

The JSON body the consumer receives per the contract:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "paid": true,
  "totalAmount": 110000,
  "customer": {
    "id": "CUS-7",
    "name": "Lan"
  },
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-7", "quantity": 1, "unitPrice": 10000}
  ]
}
~~~

### 7.1. Groovy and YAML Comparison Table

| Data Type | Groovy DSL | YAML DSL | JSON |
| --- | --- | --- | --- |
| String | `status: 'PAID'` | `status: PAID` | `"status":"PAID"` |
| Number | `amount: 1000` | `amount: 1000` | `"amount":1000` |
| Boolean | `paid: true` | `paid: true` | `"paid":true` |
| Null | `coupon: null` | `coupon: null` | `"coupon":null` |
| Object | `customer: [id: 'C-1']` | `customer:` then indented `id: C-1` | `"customer":{"id":"C-1"}` |
| Array | `tags: ['vip', 'web']` | `tags:` then `- vip`, `- web` | `"tags":["vip","web"]` |
| Empty object | `metadata: [:]` | `metadata: {}` | `"metadata":{}` |
| Empty array | `items: []` | `items: []` | `"items":[]` |

**Be careful with YAML scalars:** Some strings that look like numbers, booleans, or null may be interpreted by the parser as other types depending on formatting and parser version. To ensure an ID with leading zeros or a YAML-keyword-like string stays a String, wrap it in quotes:

~~~yaml
body:
  zipCode: "00123"
  externalCode: "true"
  remarks: "null"
~~~

These values are Strings, distinct from the number `123`, boolean `true`, or JSON null.

### 7.2. Do Not Mix Up YAML Structure Between Contract Root and HTTP Response

Wrong indentation:

~~~yaml
response:
  status: 200
body:
  orderId: ORD-123
~~~

Here `body` is not inside `response`. The correct structure is:

~~~yaml
response:
  status: 200
  body:
    orderId: ORD-123
~~~

When using the YAML DSL, most structural errors stem from field placement and indentation rather than HTTP endpoint names.

## 8. When Should You Write a Raw JSON String?

The Groovy DSL also allows writing JSON as a multiline string:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body('''{
      "orderId": "ORD-123",
      "status": "CONFIRMED",
      "customer": {
        "id": "CUS-7",
        "vip": false
      },
      "items": [
        {"sku": "BK-1", "quantity": 2}
      ]
    }''')
}
~~~

The advantage of this style is that the JSON snippet looks just like API documentation or payload examples seen by users. However:

- You must guarantee valid JSON; trailing commas or mismatched quotes make the content unparseable.
- Groovy's triple single quotes preserve characters without string interpolation.
- Dynamic fields or JSONPath matchers can be easier to manage if the body is declared using maps/lists.
- For raw non-JSON text, matching and content types work differently; do not use `Content-Type: application/json` for plain text.

**Do not argue that one style is "always more right" than the other.** Choose a style that is easy to understand, verify, and maintain for the actual schema.

## 9. Fixed Values vs. Dynamic Values: Choosing the Strictness Level

An API may return both stable and dynamic fields in the same response:

~~~json
{
  "orderId": "ORD-98765",
  "status": "CONFIRMED",
  "createdAt": "2026-11-24T09:30:00Z",
  "currency": "VND"
}
~~~

If the consumer depends on exact `status` and `currency`, constrain those values. However, `orderId` and `createdAt` can change across runs. Pinning the entire response will cause generated tests to fail on valid changing data.

Spring Cloud Contract supports **response body matchers** to express the properties that need checking:

- Value **equals** a committed value.
- Value **matches a regex** (for example, an order code with the right format).
- Value **has the right JSON type**.
- Value **matches a date/time format**.
- Certain requirements on the number of elements in a collection.

Rules for choosing matchers:

| Response Value | Usually Should Check | Avoid |
| --- | --- | --- |
| `status: CONFIRMED` | Exact business status | Regex accepting any string |
| `currency: VND` | Exact match if consumer relies on VND | Any currency code without conversion |
| Server-generated `orderId` | Published ID format | Hardcoding one random ID |
| `createdAt` | Timestamp type/format | Hardcoding run timestamp |
| `totalAmount` | Number type and critical range rules | Accepting numeric strings if API defines Number |
| Paginated `items` | Element types, needed fields, count bounds | Snapshotting the entire environment data list |

## 10. Response `bodyMatchers` with JSONPath in Groovy

**JSONPath** selects a location inside JSON to verify. Some examples:

| JSONPath | What Does It Select? |
| --- | --- |
| `$.orderId` | `orderId` field on the root object |
| `$.customer.id` | `id` field inside the `customer` object |
| `$.items[0].sku` | `sku` of the first element in `items` |
| `$.items[*].quantity` | Collection of `quantity` fields in the array |
| `$['trace.id']` | Root field whose name contains a dot |
| `$[0].sku` | `sku` of the first element of a root array |

Example Groovy contract for a dynamic ID and a numeric field:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_with_dynamic_id')

    request {
        method 'GET'
        url '/api/orders/ORD-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 250000,
            customer: [
                id: 'CUS-7',
                vip: true
            ]
        )

        bodyMatchers {
            jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
            jsonPath('$.totalAmount', byType())
            jsonPath('$.customer.vip', byType())
        }
    }
}
~~~

Meaning:

1. `body(...)` provides a sample response. This sample is also useful when generating stubs for the consumer.
2. `bodyMatchers` specifies verification rules at specific JSONPaths for **the producer's response**.
3. `byRegex('ORD-[0-9]+')` requires the ID to fit the format; it does not force the ID to be literally `ORD-123`.
4. `byType()` checks the type against the sample value: `totalAmount` is a number, `vip` is a boolean.
5. The `status` field has no separate matcher, so it can still be verified against the sample value `CONFIRMED`.

> A matcher only checks the properties it was designed to check. `byType()` on a numeric field **does not automatically prove** positive numbers, rounding rules, or calculation formulas. For critical business properties, add appropriate constraints or domain tests.

### 10.1. Common Matchers

~~~groovy
bodyMatchers {
    jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
    jsonPath('$.status', byEquality())
    jsonPath('$.createdAt', byTimestamp())
    jsonPath('$.customer.id', byType())
}
~~~

These matchers illustrate different capabilities. To use them in a real contract, **the body must contain the corresponding fields**: `orderId`, `status`, `createdAt`, `customer.id`. If a matcher points to a field absent from the body or an invalid schema, the tool may error during test generation or fail the test.

### 10.2. Be Careful When Applying Matchers to Collections

Example:

~~~groovy
body(
    items: [
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-7', quantity: 1]
    ]
)

bodyMatchers {
    jsonPath('$.items[0].sku', byType())
    jsonPath('$.items[1].sku', byType())
}
~~~

This checks the type of the two specified `sku` fields, yet does not automatically prove every element or all other values in the array obey the intended rules. For variable-length lists, design matchers, element count bounds, and/or supplementary tests matching the consumer's actual scope of use.

Do not use `$.items[0]` and assume all `items[*]` have been verified. In particular, once a location has a matcher, the generated assertion for that location may behave differently from a literal comparison without a matcher.

## 11. Response Matchers in the YAML DSL

YAML uses `response.matchers.body` to describe rules equivalent to Groovy's `bodyMatchers`:

~~~yaml
name: get_order_with_dynamic_id
request:
  method: GET
  url: /api/orders/ORD-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-123
    status: CONFIRMED
    totalAmount: 250000
    customer:
      id: CUS-7
      vip: true
  matchers:
    body:
      - path: $.orderId
        type: by_regex
        value: 'ORD-[0-9]+'
      - path: $.totalAmount
        type: by_type
      - path: $.customer.vip
        type: by_type
~~~

Quick comparison table:

| Groovy DSL | YAML DSL | Purpose |
| --- | --- | --- |
| `jsonPath('$.orderId', byRegex('ORD-[0-9]+'))` | `path: $.orderId`, `type: by_regex`, `value: 'ORD-[0-9]+'` | Validate string against pattern |
| `jsonPath('$.totalAmount', byType())` | `path: $.totalAmount`, `type: by_type` | Validate type based on body |
| `jsonPath('$.status', byEquality())` | `path: $.status`, `type: by_equality` | Validate equal to sample value |
| `jsonPath('$.couponCode', byNull())` | `path: $.couponCode`, `type: by_null` | Validate null value |

Do not place `matchers` at the top level alongside the whole contract if you want to verify the **response**. It must sit inside `response` per the Spring Cloud Contract schema.

### 11.1. Null Matcher and Optional Fields

When a field must appear with a `null` value, the contract can state:

~~~groovy
response {
    status OK()
    body(
        couponCode: null
    )
    bodyMatchers {
        jsonPath('$.couponCode', byNull())
    }
}
~~~

If the interface allows the `couponCode` field to **be omitted**, clarify the schema policy and design corresponding scenarios. Checking for null is not synonymous with checking an optional field.

## 12. Real-World Example: Nested Order Detail Response

Now combine these concepts into a contract with business meaning. `Order Service` provides:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

Sample response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "currency": "VND",
  "totalAmount": 110000,
  "customer": {
    "id": "CUS-7",
    "name": "Lan"
  },
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-7", "quantity": 1, "unitPrice": 10000}
  ],
  "discountCode": null
}
~~~

### 12.1. Suggested Groovy Contract

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_detail')

    request {
        method 'GET'
        url '/api/orders/ORD-123'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            currency: 'VND',
            totalAmount: 110000,
            customer: [
                id: 'CUS-7',
                name: 'Lan'
            ],
            items: [
                [sku: 'BK-1', quantity: 2, unitPrice: 50000],
                [sku: 'PEN-7', quantity: 1, unitPrice: 10000]
            ],
            discountCode: null
        )

        bodyMatchers {
            jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
            jsonPath('$.totalAmount', byType())
            jsonPath('$.discountCode', byNull())
        }
    }
}
~~~

The contract preserves business-significant values like `status: CONFIRMED` and `currency: VND`. The ID may vary while still needing the right format. `totalAmount` must be a numeric value; however, verifying the sum `2 × 50000 + 1 × 10000 = 110000` still requires unit/domain tests or appropriate assertions if the consumer demands strict business accuracy.

### 12.2. Scenarios This Contract Does Not Cover

The contract above describes one concrete **happy path**. It does not assert:

- What the API returns when `ORD-123` does not exist.
- Whether the API supports an empty `items` array.
- What the consumer does if `customer` is missing or `name` is null.
- How the API handles pagination, status updates, or authentication.
- Which additional JSON fields the producer may return that the consumer is allowed to ignore.

Add contracts based on real consumer needs, avoiding hundreds of cases just to "cover" every combination of values.

## 13. JSON Error Responses Are Also Contracts

Success responses are not the only ones with bodies. Suppose the consumer displays a specific message when an order does not exist.

Groovy contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')

    request {
        method 'GET'
        url '/api/orders/ORD-404'
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order not found'
        )
    }
}
~~~

Expected response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
~~~

What needs to be decided with the consumer is **which fields are stable**:

- `code: ORDER_NOT_FOUND` can be the business code the consumer uses to choose handling branches.
- `message` may be display text only, subject to localization changes; do not constrain it rigidly if both sides do not commit to exact wording.
- `status 404` may be the critical part for the consumer to distinguish from `400`, `409`, or `500`.

Do not constrain an error response solely to an English message when the consumer actually only needs the error code. If a contract specifies a body, the producer must actually return that body; a controller throwing an exception whose default error handler returns a different structure will cause the generated test to fail.

### 13.1. Common Error Envelopes

Some systems use a structure like:

~~~json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "details": {
      "orderId": "ORD-404"
    }
  }
}
~~~

Other systems use:

~~~json
{
  "type": "https://example.org/problems/order-not-found",
  "title": "Order not found",
  "status": 404
}
~~~

These are **two different schemas**. A consumer decoding `error.code` will not automatically understand `type`. If choosing to standardize error responses, agree on the schema before release and write contract tests for the branches the consumer uses.

## 14. Datasets, Pagination, and Response Evolution

An example search API:

~~~json
{
  "items": [
    {"id": "P-1", "price": 100000},
    {"id": "P-2", "price": 200000}
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 42,
    "hasNext": true
  }
}
~~~

Do not check only `items[0].id` and ignore pagination metadata if the consumer relies on `hasNext` to show a "Next page" button. On the other hand, do not hardcode `totalElements: 42` if it varies frequently and the consumer only needs to know the field is a non-negative number.

### 14.1. Distinguishing Compatible vs. Breaking Changes

| Producer Change | Expected Impact | Action for the Contract |
| --- | --- | --- |
| Add `traceId` field ignored by consumer | Usually compatible if parser ignores unknown fields | No need to force every consumer to update |
| Remove `totalAmount` while consumer reads it | Breaking change | Producer test must detect it |
| Change `totalAmount` from number to String | Can break decoding and calculations | Check types and update interface by agreement |
| Change `items: []` to `items: null` | Can break client array iteration | Keep contract on list structure |
| Move `items` under `data.items` | Changes JSONPath/schema | Evaluate versioning/migration with consumer |
| Add a new enum value for `status` | Depends on consumer's ability to handle unknown states | Test realistic branches |
| Change `items` ordering | Only breaking if consumer depends on order | Explicitly state order when it is an API commitment |
| Add optional `discountCode` field | Depends on consumer's handling of missing/null fields | Clarify optional/null policy |

A good contract avoids **over-specification** (locking down what the consumer does not need), while remaining specific enough to catch wrong types, wrong structures, wrong error codes, or wrong semantics.

### 14.2. Do Not Use Regex to Mask Structural Bugs

If the sample body declares:

~~~groovy
body(
    totalAmount: 110000
)
~~~

then this field is numeric. Adding a matcher like "any string" so that a producer returning `"110000"` still passes can hide a breaking change from the consumer. Matchers must reflect the **committed schema**, not serve to make tests green at any cost.

## 15. From Response DSL to Generated Producer Tests and Stub Runner

Once the producer has a contract describing responses, the typical flow is:

~~~mermaid
flowchart LR
    A["Groovy/YAML contract"] --> B["Generate producer tests"]
    A --> C["Generate stub mapping"]
    B --> D["Run against producer"]
    D --> E{"Do status, headers, body match?"}
    E -- "No" --> F["Build fails"]
    E -- "Yes" --> G["Build passes"]
    C --> H["Package stub"]
    G --> H
    H --> I["Consumer uses Stub Runner"]
~~~

**On the producer side**, generated tests call the declared endpoint, then compare the HTTP status, headers, and parts of the JSON body required by the DSL. For example, if the controller returns `"paid":"true"` instead of boolean `true`, appropriate type verification must fail.

**On the consumer side**, stubs simulate sample responses. Stub Runner helps the consumer test whether the client sends the right request and handles responses according to the agreed structure without running the real producer.

**Important distinction:** Response matchers are typically used to verify values the real producer returns; consumer stubs still need sample responses or suitable templating mechanisms. A regex on `$.orderId` does not automatically turn a stub into a producer capable of generating valid business IDs for arbitrary requests.

### 15.1. Base Class and Fixtures Are Still Needed

Suppose the contract requires `GET /api/orders/ORD-123` to return `200`. If the test context lacks this order, the producer may return `404` and fail the test. That may be a **setup/fixture error**, not an API breaking change.

The producer-side base test class typically prepares data or mocks appropriate dependencies. If the contract describes status `CONFIRMED`, the test must put the producer into a state capable of returning that status.

### 15.2. CI Must Run Tests, Not Just Build Artifacts

For a Maven project configured with Spring Cloud Contract Verifier:

~~~bash
./mvnw -B clean verify
~~~

For a Gradle project configured with the corresponding plugin and tasks:

~~~bash
./gradlew clean build
~~~

These commands alone do not produce meaningful verification if the plugin, base class, and contract paths are not configured. In CI, verify:

1. Existing contracts are read properly from the source tree.
2. Generated producer tests are actually generated and executed, not skipped.
3. Tests fail when intentionally changing an important field from number to String or altering JSONPaths.
4. Stub artifacts are published from a producer that passed the corresponding verification.
5. Consumers use the right stub version via Stub Runner.

Contract tests only cover what you declare and execute. They do not replace tests for pricing formulas, performance, security, or multi-service end-to-end behavior.

## 16. Common Mistakes When Describing JSON Responses

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Omitting `Content-Type` that consumer needs | Verification misses media type | Add JSON header in `response.headers` |
| Using `'250000'` instead of `250000` | JSON String instead of number | Declare literals with the right type |
| Using `'false'` instead of `false` | JSON String instead of boolean | Write booleans without quotes |
| Confusing `[]` and `[:]` | JSON array/object type changes | Choose list/map per schema |
| Writing `body(items: ...)` when API returns root array | Adds an object layer absent from API | Use a list at the root body |
| Constraining a random ID to one literal | Test fails when ID legitimately varies | Use sample value and intentional matcher |
| Using an overly broad matcher for `status` | Misses business breaking changes | Keep critical enums/statuses strictly checked |
| Checking only the first item | Subsequent elements may be wrong | Add suitable element/collection verification |
| Confusing `null` with an absent field | Consumer handles optional fields wrongly | Define schema policy explicitly |
| Mis-indenting YAML `body` | Invalid contract or body not read | Nest `response.body` properly |
| Pointing JSONPath to wrong level | Matcher checks the wrong field | Compare real JSON against each path |
| Error and success contracts have identical request conditions | Stub mappings compete | Distinguish request/fixture or design scenarios |
| Copying entire database entity into response contract | Internal changes cause false alarms | Constrain only fields consumer truly reads |
| Editing contract to pass tests without evaluating consumer | Masks breaking changes | Negotiate API, preserve compatibility, or version |

### 16.1. Workflow to Diagnose a Failing Generated Test

When a generated producer test reports a mismatch:

1. Check that the **request** in the contract actually hits the intended endpoint.
2. Read the **actual HTTP status** received.
3. Check the **Content-Type** and headers returned by the producer.
4. Inspect the **actual JSON body**, comparing types, fields, and nesting levels.
5. Check **JSONPath matchers** to identify which fields are strictly matched vs. type-checked only.
6. Check the base test class, input data, and serialization; then fix **the producer or the contract** according to the real commitment.

Do not edit generated tests in the build output directory to hide failures, because those files will be regenerated.

## 17. Practice Exercise: Writing a JSON Response Contract for Catalog Service

`Catalog Service` provides:

~~~http
GET /api/products/P-100 HTTP/1.1
Accept: application/json
~~~

Sample JSON:

~~~json
{
  "productId": "P-100",
  "name": "Wireless Mouse",
  "price": 350000,
  "available": true,
  "category": {
    "id": "ACCESSORIES",
    "displayName": "Accessories"
  },
  "tags": ["wireless", "mouse"],
  "variants": [
    {"sku": "MOUSE-BLACK", "stock": 10},
    {"sku": "MOUSE-WHITE", "stock": 4}
  ],
  "discountCode": null
}
~~~

### Task A — Write a Contract with the Right Body Structure

Write a Groovy contract `get_product_detail` with:

- `request.method` as `GET`, URL `/api/products/P-100`.
- `response.status` as `200` and header `Content-Type: application/json`.
- `productId`, `name`, `tags` with appropriate String/String array types.
- `category` as a child object and `variants` as an array of two objects.
- `price`, `stock` as numbers; `available` as boolean.
- `discountCode` as JSON null.

### Task B — Add Matchers

Suppose `productId` always follows `P-` followed by digits, though the actual number may vary. Add `bodyMatchers` to verify the ID format without hardcoding `100`.

Next, use `byType()` on `$.price` and `$.available` to catch the producer switching numbers/booleans to Strings. Keep `category.id: ACCESSORIES` fixed if the consumer depends on this category code.

### Task C — Convert to YAML

Create an equivalent YAML representation; use `response.body` with mappings and sequences, and `response.matchers.body` for both matcher types. When testing the build, activate only one definition per interaction to avoid unintended duplicate tests/stubs.

### Task D — Intentionally Introduce Breaking Changes

Try the following producer changes one by one:

1. Change `price: 350000` to `price: "350000"`.
2. Change `category` from an object to a String.
3. Change `variants` from an array to an object.
4. Remove `productId`.
5. Add a `manufacturer: "ABC"` field that the consumer does not use.

Note which changes cause producer verification to fail under your designed assertions. If a dangerous change is not caught, review the contract or matchers before considering the verification suite complete.

### Suggested Groovy Solution

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product_detail')

    request {
        method GET()
        url('/api/products/P-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            productId: 'P-100',
            name: 'Wireless Mouse',
            price: 350000,
            available: true,
            category: [
                id: 'ACCESSORIES',
                displayName: 'Accessories'
            ],
            tags: ['wireless', 'mouse'],
            variants: [
                [sku: 'MOUSE-BLACK', stock: 10],
                [sku: 'MOUSE-WHITE', stock: 4]
            ],
            discountCode: null
        )

        bodyMatchers {
            jsonPath('$.productId', byRegex('P-[0-9]+'))
            jsonPath('$.price', byType())
            jsonPath('$.available', byType())
            jsonPath('$.discountCode', byNull())
        }
    }
}
~~~

Some matchers in the example allow values to vary. However, if the consumer requires **an exact price in a business scenario**, using `byType()` alone is too weak; add value verification and appropriate calculation rules.

### Suggested YAML Solution

~~~yaml
name: get_product_detail
request:
  method: GET
  url: /api/products/P-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    productId: P-100
    name: Wireless Mouse
    price: 350000
    available: true
    category:
      id: ACCESSORIES
      displayName: Accessories
    tags:
      - wireless
      - mouse
    variants:
      - sku: MOUSE-BLACK
        stock: 10
      - sku: MOUSE-WHITE
        stock: 4
    discountCode: null
  matchers:
    body:
      - path: $.productId
        type: by_regex
        value: 'P-[0-9]+'
      - path: $.price
        type: by_type
      - path: $.available
        type: by_type
      - path: $.discountCode
        type: by_null
~~~

**Discussion:** If the consumer always ignores `manufacturer`, the producer adding that field usually does not alter the meaning of existing fields. Still, actual compatibility depends on how the consumer decodes JSON and the strictness of contracts/tests.

## 18. Checklist Before Finalizing a JSON Response Contract

- [ ] Identified the response status and `Content-Type` the consumer genuinely depends on.
- [ ] Declared the right root shape for the body: object vs. array.
- [ ] Nested maps/lists sit at the right levels without adding or removing wrappers.
- [ ] String, Number, Boolean, and Null types are accurately represented.
- [ ] Clearly distinguished `null`, absent field, empty string, empty array, and empty object.
- [ ] Required fields for the consumer are protected; avoided snapshotting unnecessary internal fields.
- [ ] Dynamic values use appropriate matchers, while critical business codes/statuses remain tightly checked.
- [ ] JSONPaths point to the right fields, including keys with special characters.
- [ ] Arrays are checked for order/length/element types to the degree needed by the consumer.
- [ ] Error branches handled by the consumer have their own contracts.
- [ ] Base test class provides fixtures so generated producer tests can execute.
- [ ] CI genuinely generates and runs generated tests, blocking releases on breaking changes.
- [ ] Stubs are published from verified producer versions and consumed via Stub Runner.

## 19. References

- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): how to declare status, headers, and response body.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `bodyMatchers`, JSONPath, data type/regex matchers, and using YAML matchers.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML syntax, role of response, and test/stub generation sources.

**Takeaway:** In Spring Cloud Contract, **a JSON response body is a data commitment**, not just a block of text. Accurately describe objects, arrays, nested fields, and value types; use matchers for truly variable data; keep tight constraints on values the consumer needs for business logic. When producer tests run in CI and stubs are published from verified contracts, incompatible JSON changes are caught earlier.
