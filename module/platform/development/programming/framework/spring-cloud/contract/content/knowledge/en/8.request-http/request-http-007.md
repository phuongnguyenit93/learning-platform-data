# JSON Request Bodies and Nested Structures

## Lesson Objectives

When a **consumer** calls a **producer**'s HTTP API, the JSON request body often has multiple layers: customer details, address, product list, and options for each product. If contract tests check only method and URL while ignoring the body, the producer can change the input structure, breaking the consumer even though the endpoint still exists.

With **Spring Cloud Contract**, we use **Groovy DSL** or **YAML DSL** to describe the request and response. From this contract, the tool generates producer-side tests, creates stubs for the consumer to test via **Stub Runner**, and helps CI detect incompatible API changes.

After this lesson, you will be able to:

- Analyze the object, array, and nested-value structure of a JSON request.
- Write bodies using maps/lists in Groovy DSL or mappings/sequences in YAML DSL.
- Use JSONPath and request body matchers for dynamic fields while keeping sample values stable for producer tests.
- Distinguish strings, numbers, booleans, null, empty strings, and absent properties.
- Design valid and invalid scenarios, especially with fields inside arrays.
- Explain the evidential limits of generated producer tests and stub tests.

## 1. What Does a Nested JSON Contract Describe?

Suppose the Checkout application calls the Order Service to create an order.

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
~~~

Sample request body:

~~~json
{
  "customer": {
    "id": "CUS-101",
    "address": {
      "city": "Ha Noi",
      "postalCode": "100000"
    }
  },
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2,
      "options": {
        "giftWrap": true
      }
    },
    {
      "sku": "PEN-002",
      "quantity": 1,
      "options": {
        "giftWrap": false
      }
    }
  ],
  "delivery": {
    "method": "STANDARD"
  }
}
~~~

Illustrative response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"ORD-9001","status":"CREATED"}
~~~

JSON structure branches:

~~~text
request body (object)
├── customer (object)
│   ├── id (string)
│   └── address (object)
│       ├── city (string)
│       └── postalCode (string)
├── items (array)
│   ├── [0] (object)
│   │   ├── sku (string)
│   │   ├── quantity (number)
│   │   └── options (object)
│   │       └── giftWrap (boolean)
│   └── [1] (object)
│       ├── sku (string)
│       ├── quantity (number)
│       └── options (object)
│           └── giftWrap (boolean)
└── delivery (object)
    └── method (string)
~~~

**Field paths** can be expressed with JSONPath:

| JSONPath | Type | Meaning to Consumer/Producer |
| --- | --- | --- |
| **$.customer.id** | string | Customer ID |
| **$.customer.address.city** | string | Delivery city |
| **$.customer.address.postalCode** | string | Postal code; kept as string so leading zeros are not lost |
| **$.items** | array | Product list |
| **$.items[0].sku** | string | SKU of the first element in the example |
| **$.items[0].quantity** | number | Quantity of the first product |
| **$.items[1].options.giftWrap** | boolean | Gift wrap option on the second element |
| **$.delivery.method** | string | Delivery method |

These commitments reflect the **integration interface**. They do not force the producer to use a specific Java DTO or database table. The producer can change internal deserialization, storage, or validation as long as the agreed public behavior is preserved.

## 2. Writing a JSON Request Body in Groovy DSL

Groovy DSL represents JSON objects with **maps** and JSON arrays with **lists**. An order creation contract with a multi-level nested body:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with address and multiple items"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
            header("Accept", "application/json")
        }
        body(
            customer: [
                id: "CUS-101",
                address: [
                    city: "Ha Noi",
                    postalCode: "100000"
                ]
            ],
            items: [
                [
                    sku: "BOOK-001",
                    quantity: 2,
                    options: [giftWrap: true]
                ],
                [
                    sku: "PEN-002",
                    quantity: 1,
                    options: [giftWrap: false]
                ]
            ],
            delivery: [
                method: "STANDARD"
            ]
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-9001", status: "CREATED")
    }
}
~~~

Explanation:

1. **body(...)** contains key–value pairs forming the top-level object.
2. **customer: [...]** and **address: [...]** are nested maps.
3. **items: [[...], [...]]** is a list containing two maps, corresponding to a JSON array.
4. **quantity: 2** preserves the numeric type; **giftWrap: true** preserves the boolean type.
5. **postalCode: "100000"** is a string. For codes that may begin with 0, converting to a number alters the data.

In Groovy, square brackets can construct either a **map** or a **list** depending on the expression inside. Therefore, you cannot judge JSON correctness merely by counting brackets: inspect the generated JSON structure and the request that the generated test actually sends.

This scenario uses deterministic values so the producer test has stable input. **ORD-9001** is a sample test response; it does not mean the production producer always returns this exact ID.

## 3. Writing the Same Behavior in YAML DSL

In YAML, a **mapping** uses keys and colons, while a **sequence** uses leading hyphens. The same contract:

~~~yaml
description: "Create order with address and multiple items"
name: create_order_with_nested_body
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customer:
      id: "CUS-101"
      address:
        city: "Ha Noi"
        postalCode: "100000"
    items:
      - sku: "BOOK-001"
        quantity: 2
        options:
          giftWrap: true
      - sku: "PEN-002"
        quantity: 1
        options:
          giftWrap: false
    delivery:
      method: STANDARD
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-9001"
    status: CREATED
~~~

YAML is readable for multi-level objects, yet it is very sensitive to **indentation**. If the hyphen of an item or the **options** field sits at the wrong level, the resulting JSON model may differ from what you intended.

To avoid mistakes, keep in mind:

- Use spaces for indentation, never tabs.
- Use **-** for each array element.
- Wrap strings that might be interpreted as numbers or booleans in quotes, especially identifiers and postal codes.
- Verify whether a field belongs under **customer**, **address**, **items**, or **delivery**.
- Avoid turning the entire JSON into one long string when it can be declared as structured YAML.

## 4. How Do Fixed Bodies and Matchers Differ?

The sample request has **customer.id = CUS-101**, yet Checkout may send many other valid customer IDs. If the stub only accepts one fixed string, other valid requests may fail to match. Spring Cloud Contract lets you declare **request body matchers** so parts of the body are matched by condition.

| Property | What Consumer/Producer Must Agree On | How to Represent |
| --- | --- | --- |
| Method and URL | POST /api/orders | Concrete values |
| Content-Type | JSON | Concrete header |
| customer.id | Follows customer ID format | Regex if appropriate |
| items[0].quantity | Numeric type; business rules usually require positive integers | Type matcher plus additional validation tests |
| delivery.method | STANDARD is a supported method | Concrete value or intentional value set |
| giftWrap | Boolean | Sample data or type matcher |

An important point: **request matchers mainly affect how the stub matches consumer requests**, whereas producer-side generated tests usually **send the declared example values**. A producer test passing with `CUS-101` does not automatically prove every ID matching the regex succeeds.

### Groovy `bodyMatchers` with JSONPath

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Create order with properly formatted customer ID"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customer: [id: "CUS-101"],
            items: [[sku: "BOOK-001", quantity: 2]],
            delivery: [method: "STANDARD"]
        )
        bodyMatchers {
            jsonPath('$.customer.id', byRegex('CUS-[0-9]{3}'))
            jsonPath('$.items[0].quantity', byType())
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-9001", status: "CREATED")
    }
}
~~~

- **$.customer.id** selects the `id` field inside `customer`. The regex specifies `CUS-` followed by three digits.
- **$.items[0].quantity** selects `quantity` of the first element. **byType()** expresses a type constraint via the matcher mechanism.
- The remaining fields are still part of the sample body; inspect the actual stub mapping to see how the tool combines matchers with other body conditions.

**`byType()` does not mean `quantity` must be positive.** The value `-1` is still a number. Business constraints such as greater than 0 or quantity caps must be described and verified through appropriate mechanisms, typically including scenarios where the producer returns errors for invalid input.

### YAML Request Matchers

YAML example using the same idea, focusing on the two fields:

~~~yaml
description: "Create order with request matchers"
name: create_order_with_matchers
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customer:
      id: "CUS-101"
    items:
      - sku: "BOOK-001"
        quantity: 2
    delivery:
      method: STANDARD
  matchers:
    body:
      - path: $.customer.id
        type: by_regex
        value: "CUS-[0-9]{3}"
      - path: $.items[0].quantity
        type: by_type
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-9001"
    status: CREATED
~~~

This is a common matcher form in YAML DSL. **Syntax and matcher options must be checked against the Spring Cloud Contract version in use** and confirmed via the actual generated stubs/tests. Do not assume every Groovy helper has a similarly named YAML counterpart across all versions.

## 5. JSONPath for Multi-Level Objects and Arrays

JSONPath is a syntax for selecting parts of a JSON document. Common examples:

| JSONPath Expression | Meaning |
| --- | --- |
| **$.customer** | Entire customer object |
| **$.customer.address.city** | City inside address object |
| **$.items[0].sku** | SKU of the first element |
| **$.items[1].quantity** | Quantity of the second element |
| **$.items[*].sku** | Selects SKUs of multiple elements (wildcard) |
| **$['customer']['address']['postalCode']** | Field selection using bracket notation |

The wildcard **[*]** can target multiple elements, yet **it does not guarantee element count**, nor does it check duplicate SKUs or ordering. Depending on the chosen matching mechanism, a matcher on one element may not inspect other elements. If the API requires at least one product, at most ten products, or unique SKUs, separate rules and tests are needed for those conditions.

If a property name literally contains dots or special characters, bracket notation helps distinguish the property name from object-level dot separators. Always test JSONPath expressions against sample bodies before using them in large contracts.

## 6. Distinguishing Number, String, Boolean, Null, and Absent Fields

Look at the JSON:

~~~json
{
  "quantity": 2,
  "quantityText": "2",
  "giftWrap": true,
  "giftWrapText": "true",
  "deliveryNote": null,
  "emptyNote": ""
}
~~~

| Value | Type | Potential Consequence |
| --- | --- | --- |
| Number **2** | JSON number | Valid for quantity if the API expects a number |
| String **"2"** | JSON string | Deserializer or validation may handle it differently |
| **true** | JSON boolean | Distinct from string **"true"** |
| **null** | JSON null | Field exists but carries no value |
| **""** | Empty string | Field exists with length 0 |
| Field does not exist | Absent | Producer may apply a default or return a missing-input error |

Example of three states of an optional note field:

~~~json
{"delivery":{"method":"STANDARD"}}
~~~

~~~json
{"delivery":{"method":"STANDARD","instructions":null}}
~~~

~~~json
{"delivery":{"method":"STANDARD","instructions":""}}
~~~

These are **three distinct requests**. Never assume Spring, Jackson, or a given schema always treats them equivalently. Producer and consumer teams must agree on the policy: may the field be omitted, is `null` accepted, is an empty string rejected?

In YAML, express types explicitly:

~~~yaml
postalCode: "00100"
quantity: 2
giftWrap: false
instructions: null
~~~

In Groovy, use numbers, booleans, and **null** with their exact types. If the consumer requires an integer, do not write the sample using a numeric string just because the producer happens to coerce types automatically in the current environment.

**A type matcher alone does not prove both `null` and absent are valid.** When two cases carry different meanings, add separate contracts or verification tests instead of letting one scenario stand in for all.

## 7. JSON Arrays: Size, Order, and Per-Element Rules

The **items** array raises more business questions than a plain object:

1. Is an empty array allowed, or is at least one item required?
2. Does each element require both **sku** and **quantity**?
3. Can the same SKU appear twice?
4. Is **options** required on every element?
5. Does item order matter?
6. What is the maximum number of elements?

A syntactically valid JSON body that is invalid per business rules:

~~~json
{
  "customer": {"id": "CUS-101"},
  "items": [{"sku": "BOOK-001", "quantity": -1}],
  "delivery": {"method": "STANDARD"}
}
~~~

A passing success contract with quantity `2` does not prove the producer rejects quantity `-1`. Similarly, matching only **$.items[0].quantity** does not check every element in a multi-item array.

When designing matchers for arrays:

- If a **fixed sample** is needed, declare each element so it is clear what exact body the producer receives.
- If **variable-length lists** must be allowed, account for both per-element rules and element count; a single JSONPath on the first element is not enough.
- If order has no business meaning, avoid turning order into an unnecessary public constraint.
- If every element must satisfy a rule, verify the rule across the entire array using suitable matcher capabilities or separate validation tests.

## 8. Writing an Error Scenario for a Nested Field

Let's describe the case where Order Service **rejects negative quantity** with HTTP 400:

~~~yaml
description: "Reject order with negative quantity"
name: reject_order_with_negative_quantity
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customer:
      id: "CUS-101"
    items:
      - sku: "BOOK-001"
        quantity: -1
    delivery:
      method: STANDARD
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_ORDER
    errors:
      - field: "items[0].quantity"
        reason: MUST_BE_POSITIVE
~~~

**INVALID_ORDER**, **MUST_BE_POSITIVE**, and the **errors** array are an **illustrative error schema**. They should become a real contract only when producer and consumer agree on them. Spring Cloud Contract does not prescribe an error response with this structure.

If the consumer displays errors keyed by the path **items[0].quantity**, changing the error field name to another string can break the consumer too. An error-branch contract must specify **exactly what the consumer uses**, not just the HTTP status code.

Add error scenarios whenever the consumer genuinely branches on cases such as: missing customer, empty items, invalid SKU, wrong quantity type, or out-of-bounds quantity. Avoid packing multiple errors into one body if the producer only reports the first error, since internal validation ordering can make tests flaky.

## 9. How Does One Contract Serve Both Producer Tests and Consumer Stubs?

~~~mermaid
flowchart TD
    A["Groovy/YAML contract with JSON request body"] --> B["Spring Cloud Contract"]
    B --> C["Generate producer test"]
    B --> D["Generate stub/mapping"]
    C --> E["Send sample request to producer"]
    E --> F["Verify response status/headers/body"]
    D --> G["Consumer uses Stub Runner"]
    G --> H["Stub matches consumer request"]
    H --> I["Return response for consumer processing"]
~~~

**Producer side:** the generated test builds a request from the contract example, sends it to the producer in the test environment, and checks the response. If the producer changes its input structure and no longer accepts the old JSON, the test can fail, helping CI catch potential incompatibilities.

**Consumer side:** the stub matches requests against conditions generated from the DSL, including method, URL, headers, and body. If matchers are too strict, valid requests will not receive stub responses; if too loose, a request that the real producer rejects may still receive a success response from the stub.

**Evidence must be tied to the same version:** a producer test passing on one contract revision while consumer tests run against an old stub is not enough to confirm the new producer is compatible with that consumer. Stubs must be generated and published from the verified contract with clear versioning, and consumers must test against them via Stub Runner.

## 10. Example of a Schema Change Breaking the Consumer

Old Checkout sends:

~~~json
{
  "customer": {
    "id": "CUS-101",
    "address": {"city": "Ha Noi"}
  },
  "items": [{"sku": "BOOK-001", "quantity": 2}]
}
~~~

New producer only accepts:

~~~json
{
  "customerId": "CUS-101",
  "shippingAddress": {"city": "Ha Noi"},
  "lines": [{"productCode": "BOOK-001", "count": 2}]
}
~~~

Even though both requests carry similar business data, they have **different public structures**:

| Old JSONPath | New JSONPath | Risk |
| --- | --- | --- |
| **$.customer.id** | **$.customerId** | Producer no longer reads `customer.id` |
| **$.customer.address.city** | **$.shippingAddress.city** | Address moved to another branch |
| **$.items[0].sku** | **$.lines[0].productCode** | Array and child field renamed |
| **$.items[0].quantity** | **$.lines[0].count** | Quantity field renamed |

The producer may return HTTP 400 or silently fall back to unexpected defaults. Keeping the `POST /api/orders` endpoint intact is **not enough** to preserve compatibility.

Mitigation approaches include: continuing to accept the old schema during a transition period; updating consumers first with dual-format support; or creating a new API version with a clear rollout/rollback plan. Before release, re-run producer tests against contracts of active consumers and test consumers against stubs from the new producer version.

## 11. Common Mistakes When Describing JSON Bodies

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing **items** as an object instead of an array | Producer/stub parses body with wrong structure | Use a Groovy list or YAML sequence |
| Wrong YAML indentation | Field ends up in the wrong parent object | Inspect the generated request |
| Sending **"quantity": "2"** instead of a number | Mismatched JSON type | Declare the proper numeric type |
| Matching only the first array element | Misses errors in other elements | Design coverage for the full array |
| Overly broad regex | Stub accepts unwanted data | Constrain to the actual format |
| Not distinguishing `null` and absent | Producer misinterprets optional fields | Create separate scenarios when needed |
| Testing only success requests | Broken validation goes undetected | Add important error branches |
| Using random values in expected bodies | Tests and stubs become non-reproducible | Use stable fixtures or matchers |
| Matching whole JSON as a fixed-order string | Tests easily break when serializer reorders keys | Use structured JSON/appropriate matchers |
| Consumer CI still uses an old stub | PASS does not reflect the new schema | Pin stub version and re-run |

When the consumer fails to receive a response from the stub, inspect method, URL, `Content-Type`, JSONPath, body matchers, and the generated mapping before concluding the real producer is broken.

## 12. Hands-On Exercises

### Exercise A — Convert JSON to Groovy

Given the request:

~~~json
{
  "buyer": {"id": "CUS-101"},
  "lines": [
    {"sku": "A-001", "quantity": 1},
    {"sku": "B-002", "quantity": 3}
  ],
  "metadata": {"source": "WEB", "gift": false}
}
~~~

**Task:** write the `body` section of the `POST /api/orders` contract using maps/lists, preserving numeric and boolean types. Hint:

~~~groovy
body(
    buyer: [id: "CUS-101"],
    lines: [
        [sku: "A-001", quantity: 1],
        [sku: "B-002", quantity: 3]
    ],
    metadata: [source: "WEB", gift: false]
)
~~~

### Exercise B — Choose Matchers

The consumer can send any `buyer.id` formatted as `CUS-` followed by three digits, while `quantity` must be numeric.

**Task:** write the corresponding JSONPath and matchers. Explain why a numeric type matcher does not prove the value is positive.

**Hint:** JSONPath **$.buyer.id** with regex **CUS-[0-9]{3}**; **$.lines[0].quantity** with **byType()**. The value `-1` still has a numeric type.

### Exercise C — Optional Fields

The producer defines `delivery.instructions` as an optional note. Consumers may omit the field, send `null`, or send an empty string.

**Task:** agree on how each case is handled and write two or three contracts proving that policy. Do not assume all three representations are automatically equivalent.

### Exercise D — Field Rename Breaking Change

The producer renames **lines[].quantity** to **lines[].count**. The old consumer still sends `quantity` and last week's stub tests continue to PASS.

**Task:** explain why the old result is insufficient evidence, identify which contracts must be re-run, and explain how to use Stub Runner to test the consumer against the new producer version.

## 13. Checklist for Designing Nested JSON Requests

- [ ] Method, URL, `Content-Type`, and body structure are clearly declared.
- [ ] Objects, arrays, and nesting levels match the JSON sent by the consumer.
- [ ] Number/string/boolean/null types match the public interface.
- [ ] Required, optional, `null`, absent, and empty-string rules are explicit.
- [ ] For arrays, rules on element count, ordering, and per-element constraints are considered as needed.
- [ ] Fixed sample data and fields needing matchers are intentionally separated.
- [ ] JSONPath expressions target the right level; matchers are tight enough for consumer requirements.
- [ ] Important error scenarios exist for invalid or missing nested fields.
- [ ] Generated producer tests actually execute and verify responses.
- [ ] Stubs are generated from the right contract revision without missing mappings.
- [ ] Consumer tests via Stub Runner use the exact new stub version.
- [ ] Any change to field names, types, or request structure is evaluated for compatibility before release.

**Remember:** a JSON request body is **part of the integration contract**, encompassing field names, data types, and nested object/array relationships. Groovy DSL uses maps/lists, YAML DSL uses mappings/sequences, and JSONPath plus request body matchers help express intentional flexibility. Only when both producer tests and consumer stub tests verify the right behavior does CI have a solid basis to detect incompatible request schema changes.
