# Literals, Maps, Lists, and Multiline Strings

## 1. Why Must You Master Data Types in Groovy DSL?

Spring Cloud Contract helps producers and consumers agree on HTTP or messaging behavior through verifiable contract files. In a Groovy contract, the contents of `request`, `response`, and `outputMessage` typically contain data simulating a real request or response: identifiers, monetary amounts, status flags, JSON objects, lists of items, or multiline text.

These values are expressed using **Groovy syntax** before Spring Cloud Contract converts them into generated producer tests and consumer stubs. Writing the wrong type or structure in the DSL can lead to two kinds of failures:

- **The contract fails to compile or generate tests:** for example, missing brackets, invalid string declarations, or invalid Groovy constructs.
- **The contract is valid, but verifies the wrong intent:** for example, the producer returns the number `2` while the contract uses the string `'2'`, or the consumer expects a JSON array while the contract describes an object.

This lesson belongs to the **Groovy DSL** chapter of the `SPRING_CLOUD_CONTRACT` module. It focuses on literals, `Map`, `List`, and multiline strings used in HTTP or messaging specifications, laying the foundation for subsequent steps: generating provider-side tests, publishing stubs, running Stub Runner, and integrating with CI to detect incompatible API changes.

After this lesson, you will be able to:

1. Choose appropriately typed literals for strings, numbers, booleans, and `null`.
2. Use Groovy maps to represent nested JSON objects, including keys with special characters.
3. Use lists and lists of maps to represent ordered JSON arrays.
4. Write multiline strings with triple quotes and understand when Groovy interpolates expressions.
5. Distinguish literal data from flexible matchers in contract tests.
6. Write a complete HTTP contract with multiple data types and check for common mistakes before putting it into CI.

> Scope: The examples assume a producer built with Spring MVC and source contracts written in Groovy DSL. They illustrate how to **declare contracts**, not business-logic code or full build configurations.

## 2. Where Groovy Values Fit in a Contract

A typical contract file:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Retrieve details of a confirmed order'

    request {
        method 'GET'
        url '/api/orders/ORD-100'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-100',
            status: 'CONFIRMED',
            totalAmount: 120000,
            paid: true
        )
    }
}
~~~

In this example, `Contract.make { ... }` is the Spring Cloud Contract DSL; `'ORD-100'`, `120000`, and `true` are **Groovy literals**. The syntax `body(orderId: 'ORD-100', ...)` produces a map-like structure so the framework can convert it into JSON content and verification conditions.

Distinguish two layers:

| Layer | Example | Role |
| --- | --- | --- |
| Contract structure | `request { ... }`, `response { ... }`, `outputMessage { ... }` | Defines which interaction is verified |
| Values inside the contract | `'CONFIRMED'`, `120000`, `true`, `[sku: 'A']`, `['A', 'B']` | Describes the data being sent or received |

**Correctly typed values** matter a great deal. JSON `{"quantity":2}` is different from JSON `{"quantity":"2"}`; for a consumer with strict schemas or data types, that difference can break the application even though both display the digit "2".

## 3. What Is a Literal?

A **literal** is a value written directly in Groovy code, without computing from a variable or calling a function. Literals frequently used in Spring Cloud Contract:

| Purpose | Groovy DSL | JSON Type/Meaning |
| --- | --- | --- |
| String | `'ORD-100'` or `"ORD-100"` | `"ORD-100"` |
| Integer | `2`, `120000` | `2`, `120000` |
| Decimal number | `19.95` | `19.95` |
| Boolean | `true`, `false` | `true`, `false` |
| Null value | `null` | `null`, distinct from an absent field |
| Map | `[id: 'C-1', vip: true]` | JSON object |
| List | `['NEW', 'PAID']` | JSON array |
| List of maps | `[[sku: 'BK-1', qty: 2]]` | JSON array of objects |

Observe each group in a response:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        id: 'ORD-100',       // String
        quantity: 2,        // number
        accepted: true,     // boolean
        discountCode: null, // JSON null
        tags: ['web', 'new'] // list of strings
    )
}
~~~

Resulting JSON payload:

~~~json
{
  "id": "ORD-100",
  "quantity": 2,
  "accepted": true,
  "discountCode": null,
  "tags": ["web", "new"]
}
~~~

Do not carelessly turn `null` into the string `'null'`, or `false` into `'false'`. Adding quotes converts a value into a **String** and alters the contract.

### 3.1. Integer and Decimal Literals

Groovy supports integer and decimal numeric literals:

~~~groovy
body(
    quantity: 3,
    price: 49.90,
    taxRate: 0.08,
    totalInVnd: 159000
)
~~~

Here `49.90` is a numeric literal, not a string. However, the exact representation in generated tests, JSON serializers, and consumers may differ in scale or internal numeric type. For money, two common conventions are:

- **Integer in the smallest currency unit** defined by the API, such as `totalInVnd: 159000`.
- **Decimal with an explicit unit and rounding rules**, such as `price: 49.90`.

Agree in the contract on units, precision, and how the consumer decodes values. Avoid using the string `'49.90'` just because you want to keep two digits after the decimal point, unless the API actually defines the field as a String.

### 3.2. Booleans and Null

~~~groovy
body(
    available: true,
    discontinued: false,
    promotionCode: null
)
~~~

Equivalent to:

~~~json
{
  "available": true,
  "discontinued": false,
  "promotionCode": null
}
~~~

**`promotionCode: null` does not mean the `promotionCode` key is absent.** A consumer may distinguish three states: present with a value, `null` value, or missing field. If the API allows omitting a field, describe that commitment accurately; do not add `null` just for convenience when writing the DSL.

## 4. Single-Quoted vs. Double-Quoted Strings: Similarities and Differences

Groovy permits both single and double quotes:

~~~groovy
def a = 'CONFIRMED'
def b = "CONFIRMED"
~~~

When containing only fixed text, both represent the same content. The difference appears when a string uses **interpolation**:

~~~groovy
def orderId = 'ORD-100'

def literalText = 'Order: $orderId'
def interpolatedText = "Order: $orderId"
~~~

- `literalText` contains the literal characters `$orderId`.
- `interpolatedText` becomes `Order: ORD-100` because double quotes support GString interpolation.

In a contract, if a field must hold a **fixed string**, using single quotes helps prevent accidental variable interpolation. If you genuinely need to build data from variables, you can use a Groovy expression, but consider contract stability when producer and consumer tests run in different environments.

### 4.1. Quotes Inside String Content

~~~groovy
body(
    message: 'Customer selected "Express Delivery"',
    note: "Order for customer 'Lan'"
)
~~~

Alternatively, escape quotes of the same kind with a backslash:

~~~groovy
body(
    note: 'Customer said: \'Deliver before 18:00\''
)
~~~

When a string contains many double quotes, using outer single quotes is usually easier to read. You do not need to escape every `"` inside a single-quoted Groovy string.

### 4.2. Backslashes Are Not Harmless Characters

Groovy still processes escape sequences in certain String forms, including single-quoted strings. For example, `'\n'` represents a newline character, whereas `'\\n'` represents a backslash followed by the letter `n`.

If a contract needs a literal `\` character (for instance, a Windows path or a regex), you must check **both escaping layers**: Groovy's String syntax and the target JSON/regex format.

## 5. Groovy Maps: Representing a JSON Object

A **Map** stores data as key-value pairs. In Groovy, map literals use square brackets with `key: value` syntax:

~~~groovy
def customer = [
    id: 'CUS-7',
    name: 'Lan',
    vip: true
]
~~~

When placed inside a body:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        customer: [
            id: 'CUS-7',
            name: 'Lan',
            vip: true
        ]
    )
}
~~~

JSON meaning:

~~~json
{
  "customer": {
    "id": "CUS-7",
    "name": "Lan",
    "vip": true
  }
}
~~~

### 5.1. Nested Maps

Maps can contain other maps to any reasonable depth:

~~~groovy
body(
    orderId: 'ORD-100',
    delivery: [
        receiver: [
            name: 'Lan',
            phone: '0900000000'
        ],
        address: [
            city: 'Da Nang',
            postalCode: '550000'
        ]
    ]
)
~~~

Here `delivery`, `receiver`, and `address` are all JSON objects. Nested structures should reflect the schema the consumer actually uses; do not add internal fields just because the producer has them on its database entity.

### 5.2. Passing an Explicit Map vs. Named Arguments

The following two forms generally express the same body data:

~~~groovy
// Named arguments syntax, easy to read for simple bodies
body(
    id: 'ORD-100',
    paid: true
)
~~~

~~~groovy
// Create an explicit map and pass it to body
body([
    id: 'ORD-100',
    paid: true
])
~~~

The first syntax is convenient for JSON objects. The second is useful when representing complex maps or when you want to make clear you are passing **a single map** to the DSL method.

### 5.3. Keys with Hyphens, Spaces, or Special Characters

For JSON keys that are not valid standard Groovy identifiers, wrap the key in quotes:

~~~groovy
body([
    'order-id': 'ORD-100',
    'customer name': 'Lan',
    'is-active': true
])
~~~

Equivalent JSON:

~~~json
{
  "order-id": "ORD-100",
  "customer name": "Lan",
  "is-active": true
}
~~~

Use `'order-id'` as a quoted map key instead of writing `order-id` and letting Groovy misinterpret it as a subtraction expression.

### 5.4. Do Not Merge Multiple Fields into a Single String by Mistake

Semantically wrong if the consumer expects an object:

~~~groovy
body(
    customer: 'id=CUS-7,name=Lan'
)
~~~

Correct when the consumer expects an object:

~~~groovy
body(
    customer: [
        id: 'CUS-7',
        name: 'Lan'
    ]
)
~~~

This is not merely a code style issue. The first contract specifies a JSON string, while the second specifies a JSON object with two fields that the consumer can read individually.

## 6. Groovy Lists: Representing a JSON Array

A **List** in Groovy is an ordered collection of elements written with square brackets and commas:

~~~groovy
def tags = ['new', 'online', 'promotion']
def quantities = [1, 2, 5]
~~~

When used in a contract:

~~~groovy
body(
    orderId: 'ORD-100',
    tags: ['new', 'online'],
    quantities: [1, 2, 5]
)
~~~

Equivalent JSON:

~~~json
{
  "orderId": "ORD-100",
  "tags": ["new", "online"],
  "quantities": [1, 2, 5]
}
~~~

Unlike maps, **element order in a list can carry meaning**: a sequence of steps, priority lists, sorted results, or line items displayed by the consumer in order.

### 6.1. Lists Containing Multiple Maps

A common scenario is an order with multiple line items:

~~~groovy
body(
    orderId: 'ORD-100',
    items: [
        [
            sku: 'BK-1',
            quantity: 2,
            unitPrice: 55000
        ],
        [
            sku: 'PEN-9',
            quantity: 1,
            unitPrice: 10000
        ]
    ]
)
~~~

Equivalent JSON:

~~~json
{
  "orderId": "ORD-100",
  "items": [
    { "sku": "BK-1", "quantity": 2, "unitPrice": 55000 },
    { "sku": "PEN-9", "quantity": 1, "unitPrice": 10000 }
  ]
}
~~~

Reading from outside in:

1. `body(...)` represents the **order object**.
2. `items: [ ... ]` represents the **array of line items**.
3. Each element `[sku: ..., quantity: ..., unitPrice: ...]` is **an object**.

### 6.2. Nested Lists

~~~groovy
body(
    matrix: [
        [1, 2],
        [3, 4]
    ]
)
~~~

Equivalent to `{"matrix":[[1,2],[3,4]]}`. This is useful when the consumer actually expects a matrix or 2D structure, but do not nest lists merely to simulate distinct objects.

### 6.3. Empty List and Empty Map Are Different Values

~~~groovy
body(
    items: [],    // empty JSON array
    metadata: [:]  // empty JSON object
)
~~~

Equivalent to:

~~~json
{
  "items": [],
  "metadata": {}
}
~~~

Pay close attention: `[]` in Groovy is an **empty list**, while `[:]` is an **empty map**. In JSON, `[]` and `{}` have different types; many consumers deserialize directly into a `List<T>` or an object and will not accept them interchangeably.

### 6.4. When the Body Has a Root-Level JSON Array

Not every HTTP API returns an object containing fields. If an endpoint returns an array directly:

~~~json
[
  { "sku": "BK-1", "quantity": 2 },
  { "sku": "PEN-9", "quantity": 1 }
]
~~~

You can represent the body value as a list of maps:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body([
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-9', quantity: 1]
    ])
}
~~~

The **outermost** square brackets represent the JSON array. Do not write `body(items: [...])` if the consumer actually receives a root-level array, as that changes the schema into an object with an `items` field.

## 7. Multiline Strings in Groovy

Multiline strings commonly appear in descriptions, email templates, text-bearing payloads, plain-text HTTP bodies, or verbatim JSON. Groovy supports triple quotes:

- `''' ... '''`: multiline string **without interpolating** Groovy expressions.
- `""" ... """`: multiline string that **can interpolate** variables/expressions just like double quotes.

Example:

~~~groovy
def note = '''Deliver during business hours.
Call before arriving.
Do not leave packages at reception.'''
~~~

The value of `note` contains newline characters between the three sentences. If the consumer receives text with newlines, the contract may need to constrain this content; if the consumer only needs any descriptive text, consider an appropriate matcher so you do not over-constrain text unnecessarily.

### 7.1. Multiline Strings in a JSON Field

~~~groovy
body(
    orderId: 'ORD-100',
    deliveryNote: '''Deliver during business hours.
Call before arriving.'''
)
~~~

Data-wise, `deliveryNote` is **a String containing a newline character**. When serialized to JSON, the newline is typically escaped as `\n` in JSON's character representation, while after the consumer parses it the string still contains a line break.

Do not confuse:

~~~groovy
// Actual newline inside the String value
deliveryNote: '''Line one
Line two'''
~~~

with:

~~~groovy
// Value containing literal backslash and letter n characters
deliveryNote: 'Line one\\nLine two'
~~~

Those two values are not equivalent: the second uses `\\n` in Groovy code to preserve a backslash in the data after Groovy parses the string.

### 7.2. Writing an Entire JSON Body with a Multiline String

When a payload has many nested levels, an alternative is describing **the raw JSON as a String**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method 'POST'
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body('''{
          "customer": {
            "id": "CUS-7",
            "vip": true
          },
          "items": [
            {"sku": "BK-1", "quantity": 2},
            {"sku": "PEN-9", "quantity": 1}
          ],
          "note": "Deliver during business hours"
        }''')
    }

    response {
        status CREATED()
    }
}
~~~

With `Content-Type: application/json`, a body string containing valid JSON is a supported way in Spring Cloud Contract to describe a request. Unlike a map, you can directly see the exact JSON syntax the client sends.

**Two different ways to write the same data:**

~~~groovy
// A. Groovy Map
body(
    customer: [id: 'CUS-7', vip: true],
    items: [
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-9', quantity: 1]
    ],
    note: 'Deliver during business hours'
)
~~~

~~~groovy
// B. Stringified JSON
body('''{
  "customer": {"id": "CUS-7", "vip": true},
  "items": [
    {"sku": "BK-1", "quantity": 2},
    {"sku": "PEN-9", "quantity": 1}
  ],
  "note": "Deliver during business hours"
}''')
~~~

Choose a **Groovy map** when you want consistent DSL syntax and want to leverage nested field values/matchers. Choose a **JSON string** when you need easy comparison with an existing JSON sample or a deeply nested payload that your team finds easier to review as JSON. Both must be verified with generated tests.

### 7.3. Be Careful with Leading/Trailing Whitespace and Newlines

For JSON objects, spaces and newlines outside strings usually do not change the meaning of data. For **text/plain**, email templates, or String fields, whitespace and newline characters can be part of the contract.

Example:

~~~groovy
def exactText = '''Line one
Line two'''
~~~

differs from:

~~~groovy
def textWithLeadingNewline = '''
Line one
Line two'''
~~~

In the second example, the value starts with a newline immediately after `'''`. To control whitespace, start the text right after the opening quotes, or use `stripIndent()` or `trim()` when appropriate and after checking the actual result. Do not add `trim()` arbitrarily if blank lines and spaces matter to the consumer.

## 8. Interpolation in Multiline Strings: When to Use and Avoid?

Example:

~~~groovy
def customerName = 'Lan'

def noInterpolation = '''Hello $customerName,
Your order is being processed.'''

def withInterpolation = """Hello $customerName,
Your order is being processed."""
~~~

In `noInterpolation`, the text retains `$customerName` literally. In `withInterpolation`, Groovy replaces `$customerName` with `Lan`.

This is especially important when **the body naturally contains `$` characters**. For instance, a document payload or template containing placeholders like `${field}` can be interpreted by Groovy as an expression if written inside a triple-double-quoted string. To send the characters verbatim, use `'''...'''` or escape them properly.

### 8.1. Do Not Use Interpolation to Hide Unstable Data

The following example may execute in Groovy, yet produces a hard-to-reproduce contract:

~~~groovy
def requestId = java.util.UUID.randomUUID().toString()

Contract.make {
    request {
        method 'POST'
        url '/api/events'
        body(requestId: requestId)
    }
    response {
        status ACCEPTED()
    }
}
~~~

The contract value changes whenever the DSL is loaded. This easily causes generated tests, packaged stubs, and consumer tests across environments to have inconsistent data. For truly dynamic data, use a **stable sample value for the stub** and an appropriate **matcher** for producer verification, rather than generating random values at DSL parse time.

## 9. Complete Example: Order Creation Contract with Literals, Maps, Lists, and Multiline Text

Suppose the consumer calls `POST /api/orders` with customer details, line items, and a delivery note. The producer returns an order ID and total amount.

### 9.1. Business Requirements

| Field | JSON Type | Meaning to the Consumer |
| --- | --- | --- |
| `customer.id` | String | Customer identifier |
| `customer.vip` | Boolean | Business branch for VIP customers |
| `items` | Array | Line items to process |
| `items[].quantity` | Number | Ordered quantity |
| `deliveryNote` | String | Note, may contain newlines |
| `orderId` | String | Order code for consumer lookup |
| `totalAmount` | Number | Total amount in the agreed currency unit |
| `accepted` | Boolean | Indicates whether the order creation request was accepted |

### 9.2. Groovy Contract

File `src/test/resources/contracts/orders/create_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_with_two_items')
    description('Accept an order with two items and a multiline note')

    request {
        method 'POST'
        url '/api/orders'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            customer: [
                id: 'CUS-7',
                vip: true
            ],
            items: [
                [
                    sku: 'BK-1',
                    quantity: 2,
                    unitPrice: 55000
                ],
                [
                    sku: 'PEN-9',
                    quantity: 1,
                    unitPrice: 10000
                ]
            ],
            deliveryNote: '''Deliver during business hours.
Call before arriving.'''
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }

        body(
            orderId: 'ORD-100',
            totalAmount: 120000,
            accepted: true,
            tags: ['new', 'online']
        )
    }
}
~~~

Here:

- `'POST'` and `'/api/orders'` are String literals describing the HTTP method and URL.
- `customer: [id: ..., vip: ...]` is a nested map in the request.
- `items: [[...], [...]]` is a list containing two maps.
- `deliveryNote` is a String containing a newline.
- `totalAmount` is a number; `accepted` is a boolean; `tags` is a list of Strings.
- `status CREATED()` specifies HTTP status `201`, independent of body values.

Illustrative calculation: two `BK-1` items at `55,000` each plus one `PEN-9` item at `10,000` gives a total of `120,000`, excluding tax or shipping fees. In practice, pricing and calculation rules must be handled properly in the producer's business logic; the contract only reflects the **communication commitment** in this scenario.

### 9.3. JSON Sent by the Consumer

~~~json
{
  "customer": {
    "id": "CUS-7",
    "vip": true
  },
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 55000},
    {"sku": "PEN-9", "quantity": 1, "unitPrice": 10000}
  ],
  "deliveryNote": "Deliver during business hours.\nCall before arriving."
}
~~~

Committed producer response:

~~~json
{
  "orderId": "ORD-100",
  "totalAmount": 120000,
  "accepted": true,
  "tags": ["new", "online"]
}
~~~

The `\n` in JSON is **how a newline is represented inside a String**. It does not require the consumer to receive a literal backslash followed by `n`; after JSON parsing, the value contains an actual line break.

## 10. Same Data Types in Messaging DSL

Spring Cloud Contract does not use Groovy DSL for HTTP alone. When a producer emits messages, `outputMessage { body(...) }` can also contain literals, maps, lists, and multiline strings.

Example where `Payment Service` emits a `PaymentAuthorized` event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Emit payment authorized event'
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')

        headers {
            header('contentType', 'application/json')
        }

        body(
            eventType: 'PaymentAuthorized',
            paymentId: 'PAY-9',
            approved: true,
            amount: 120000,
            items: [
                [sku: 'BK-1', quantity: 2],
                [sku: 'PEN-9', quantity: 1]
            ],
            note: '''Payment authorized.
Waiting for delivery completion.'''
        )
    }
}
~~~

Producer verification for messaging requires a way to execute `publishAuthorizedPayment()` and observe the message emitted by the producer, according to the configured message verifier/binder mechanism. The data in `body` follows the same map/list/String representation as HTTP, but **the destination, headers, and trigger mechanism differ from an HTTP response**.

The contract above does not prove exactly-once message delivery, broker ordering, retries, or idempotency; those properties require appropriate integration tests.

## 11. Fixed Literals vs. Matchers in Contract Testing

A literal means you are describing one specific value. That is very useful for values representing **stable business meaning**, such as:

~~~groovy
body(
    status: 'CONFIRMED',
    accepted: true,
    currency: 'VND'
)
~~~

However, many values are **dynamic**, such as a server-generated `orderId` or an `occurredAt` timestamp when an event is emitted. If you always assert them with a fixed literal, tests may fail even when the producer remains compatible.

Spring Cloud Contract lets you combine a **sample value** with a **matcher**. Example in a response:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }

    body(
        orderId: 'ORD-123',
        status: 'CONFIRMED'
    )

    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
    }
}
~~~

In this case:

- `'ORD-123'` is the contract's sample value; it can be used in the stub served to the consumer.
- `byRegex('ORD-[0-9]+')` allows the generated producer test to accept order codes matching the format.
- `status: 'CONFIRMED'` remains a literal because the consumer expects that exact business status.

**Matchers do not change the meaning of data.** If the consumer needs the exact status `CONFIRMED` to make decisions, switching it to an "any string" matcher prevents the contract from catching breaking changes. If the consumer expects a number, do not use a string matcher to legitimize the producer returning a mistyped String.

## 12. Common Mistakes with Literals, Maps, Lists, and Multiline Strings

| Mistake | Example/Symptom | Consequence | How to Fix |
| --- | --- | --- | --- |
| Turning numbers into Strings | `quantity: '2'` | JSON gets String instead of number | Use `quantity: 2` if schema requires number |
| Turning booleans into Strings | `active: 'false'` | Consumer reading boolean may fail | Use `active: false` |
| Confusing null with String | `note: 'null'` | No longer JSON null | Use `note: null` or omit field if contract allows absence |
| Confusing empty map with empty list | `metadata: []` | JSON array instead of object | Use `metadata: [:]` |
| Missing a list nesting level | `items: [sku: 'A']` | Object instead of array of objects | Use `items: [[sku: 'A']]` |
| Unquoted keys with hyphens | `order-id: 'X'` | Syntax easily misinterpreted | Write `'order-id': 'X'` in map |
| Unintended leading newline | Triple quotes start on the line before text | String begins with a newline | Place text right after opening quotes or handle newlines intentionally |
| Unintended interpolation | Using `"""$value"""` for payload that must keep `$` literally | Groovy substitutes content | Choose `'''...'''` when placeholders must stay verbatim |
| Typing invalid raw JSON | Trailing comma, unquoted keys inside JSON string | Fails to parse JSON | Validate JSON format or use Groovy maps |
| Expecting object key order | Comparing entire JSON by key position | Test is stricter than JSON semantics | Verify important fields and values |
| Ignoring ordered lists | Swapping `['first', 'second']` | Consumer may process wrong order | Enforce order when API commits to ordering |
| Generating random IDs when loading DSL | `UUID.randomUUID()` in contract | Stub and tests have non-reproducible data | Use stable sample values + intentional matchers |
| Flattening JSON structure into a String | `customer: 'id=C-1'` | Loses object schema | Use `customer: [id: 'C-1']` |
| Wrong root-level object | `body(items: [...])` when API returns array | Response schema is altered | Use `body([...])` for a root array |

### Subtle Mistake: Map Literal with Duplicate Keys

~~~groovy
body([
    status: 'PENDING',
    status: 'CONFIRMED'
])
~~~

A Groovy map cannot represent two fields with the same name as you might expect; one value can overwrite the other when the map is constructed. Choose a single definition per key, or split into **two contracts** if they represent two different scenarios.

### Subtle Mistake: Writing Verbatim JSON but Forgetting Content-Type

~~~groovy
request {
    method 'POST'
    url '/api/orders'
    body('''{"quantity": 2}''')
}
~~~

The snippet above describes the body, yet the real consumer may send `Content-Type: application/json`. When the header is part of the agreed communication, declare it explicitly:

~~~groovy
headers {
    contentType(applicationJson())
}
~~~

Doing so ensures the contract verifies that producer and consumer agree not only on the payload, but also on the media type.

## 13. From DSL to Producer Tests, Stubs, and CI

Data in a contract directly impacts the Spring Cloud Contract lifecycle:

~~~mermaid
flowchart LR
    A["Groovy DSL: literal/map/list/multiline"] --> B["Generate producer tests"]
    A --> C["Generate stub mappings"]
    B --> D{"Does producer match data and types?"}
    D -- "No" --> E["Fix producer or negotiate contract"]
    D -- "Yes" --> F["Valid build"]
    C --> G["Consumer tests with Stub Runner"]
    F --> H["Publish verified stubs"]
    H --> G
~~~

For example, the consumer expects `quantity` to be a JSON number. If the producer changes it to `"quantity": "2"`, the generated producer test from the old contract can detect the type/value mismatch under the chosen matcher rules, and CI blocks the release.

When changing a field from `tags: []` to `tags: [:]`, you have changed a **JSON array into a JSON object**, a change likely to break consumers. Assess compatibility before updating a contract just to make tests pass.

A practical verification workflow:

1. Place the Groovy DSL file in the contract source directory configured by the build tool, typically `src/test/resources/contracts`.
2. Set up the base test class and required fixture data on the producer.
3. Run a build that generates **and executes** the generated tests, for example `./mvnw -B clean verify` in a Maven project configured with Spring Cloud Contract.
4. Verify that tests fail when you intentionally change a data type or remove a field the consumer uses.
5. Package/publish stubs only after the producer passes the required verifications; let the consumer test with Stub Runner.
6. Keep contracts, generated tests, and stubs aligned to the exact version the pipeline releases.

Simply creating a Groovy DSL file is not enough to guarantee tests run. The Maven/Gradle plugin, Spring Cloud Contract dependencies, base class, and test runner must all be configured for the project's version.

## 14. Practice: Writing a Contract for a Shopping Cart API

`Cart Service` exposes `POST /api/carts/checkout` and receives:

~~~json
{
  "customerId": "CUS-42",
  "items": [
    {"sku": "MOUSE-1", "quantity": 1, "unitPrice": 350000},
    {"sku": "PAD-2", "quantity": 2, "unitPrice": 50000}
  ],
  "coupon": null,
  "urgent": false,
  "note": "Deliver after 17:00.\nCall 15 minutes ahead."
}
~~~

Expected result:

~~~json
{
  "checkoutId": "CHK-9",
  "totalAmount": 450000,
  "accepted": true,
  "warnings": []
}
~~~

### Requirements

1. Write a `Contract.make` in Groovy DSL declaring the method, URL, `Content-Type`, and both bodies.
2. Use properly typed literals for `customerId`, `urgent`, `coupon`, `quantity`, and `totalAmount`.
3. Use a list of maps to represent the two `items` entries.
4. Use a triple-quoted string for `note` to include an actual newline.
5. Use an empty list for `warnings`; explain why an empty map must not be used.
6. Try changing the producer to return `"totalAmount": "450000"`; explain why the existing contract must catch this change if the consumer relies on a number.

### A Reference Solution

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('checkout_cart_success')

    request {
        method 'POST'
        url '/api/carts/checkout'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'CUS-42',
            items: [
                [sku: 'MOUSE-1', quantity: 1, unitPrice: 350000],
                [sku: 'PAD-2', quantity: 2, unitPrice: 50000]
            ],
            coupon: null,
            urgent: false,
            note: '''Deliver after 17:00.
Call 15 minutes ahead.'''
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            checkoutId: 'CHK-9',
            totalAmount: 450000,
            accepted: true,
            warnings: []
        )
    }
}
~~~

In this solution, `warnings: []` indicates **no warning items**. Replacing it with `warnings: [:]` would give the consumer an empty object instead of an empty array. Similarly, `totalAmount: 450000` is a number; having the producer switch it to a string could break the consumer's price calculation logic.

### Extension Questions

- If the producer generates `checkoutId` randomly, should you keep a literal or add a matcher? State the sample value and committed format.
- If `coupon` is an optional field and can be omitted completely, how should verification change?
- If `items` is a list ordered according to user selection, is swapping two elements a compatible change?
- If a payment confirmation email is sent via a message broker, should the `items` structure be reused as-is in `outputMessage`? Which fields does the message consumer actually need?

**Hints:** Matchers help with dynamic IDs; optional fields require explicit present/absent/null policies; lists may require order preservation; messaging contracts should be driven by actual subscribers rather than blindly copying the entire HTTP payload.

## 15. Checklist Before Completing a Groovy Contract

- [ ] Every String literal has appropriate quotes; no unintended interpolation.
- [ ] Numbers and booleans use properly typed literals, not wrapped in strings unless the API defines them that way.
- [ ] `null` only appears when the schema truly allows or requires a null value.
- [ ] JSON objects are represented with maps; JSON arrays are represented with lists.
- [ ] Empty maps use `[:]` and empty lists use `[]`, never swapped.
- [ ] Lists of objects have the proper two levels of square brackets such as `[[sku: 'A']]`.
- [ ] Keys with hyphens, spaces, or special characters are properly quoted.
- [ ] Multiline values are checked for newlines and leading/trailing whitespace.
- [ ] Raw JSON strings are valid JSON and include the committed media type header.
- [ ] Matchers are used only when needed, without weakening fields that require exact business values.
- [ ] The contract has suitable fixtures/producer setup so generated tests can run.
- [ ] Confirmed that generated tests run in CI; stubs are published alongside the verified producer version.

**Key takeaway:** In Spring Cloud Contract Groovy DSL, **literals** determine types and values; **maps** describe JSON objects; **lists** describe JSON arrays; and **multiline strings** preserve text with newlines or verbatim JSON. Getting these four elements right ensures the contract verifies the exact behavior consumers depend on, rather than merely producing a syntactically valid DSL file.
