# HTTP Method and Request Path

## 1. Method and Path Are the Starting Point of an HTTP Contract

In Spring Cloud Contract, a contract describes the communication behavior that a **consumer** is allowed to expect from a **producer**. With HTTP, the consumer sends a request; the producer processes the request and returns a response. If the producer changes how it accepts the request, the consumer can fail even if the JSON response remains unchanged.

The first two elements to define in the `request` section are:

- **HTTP method:** Does the consumer call `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, or another method?
- **Request path:** Which endpoint does the consumer call, for example `/api/orders` or `/api/orders/ORD-123`?

According to the Spring Cloud Contract DSL, **method and URL are the two required pieces of information to define an HTTP request**. The body, headers, and query parameters can be added when they are part of the agreement between systems.

This lesson belongs to the **Request HTTP** chapter in the `SPRING_CLOUD_CONTRACT` module. It focuses on declaring the method and path using **Groovy/YAML DSL**, distinguishing path from query, representing dynamic parameters, and verifying the producer through generated tests. This knowledge forms the foundation for publishing stubs, running Stub Runner, and using CI to detect incompatible APIs.

### Learning Objectives

After this lesson, you will be able to:

1. Choose an HTTP method appropriate for the communication intent and interpret the consequences of changing the method.
2. Distinguish between **scheme/host**, **path**, **path segment**, **path variable**, and **query parameter**.
3. Write the `request` section with `method` and `urlPath` or `url` in Groovy DSL.
4. Express the corresponding contract using YAML DSL.
5. Design fixed paths and paths with varying values without making matchers overly broad.
6. Identify changes that can break consumers, and integrate contract tests into producer CI.

## 2. Analyzing an HTTP Request from a Contract Perspective

Consider the request:

~~~http
GET /api/orders/ORD-123?includeItems=true HTTP/1.1
Host: order-service.internal
Accept: application/json
~~~

The components serve different roles:

| Component | Example Value | Role in the Contract |
| --- | --- | --- |
| Method | `GET` | The HTTP action performed by the consumer |
| Path | `/api/orders/ORD-123` | Routes to a resource or behavior |
| Path variable | `ORD-123` | A varying value embedded in a path segment |
| Query parameter | `includeItems=true` | Additional option or criteria for the request |
| Host | `order-service.internal` | Address where the producer runs, often varying by environment |
| Request header | `Accept: application/json` | Declares the response format accepted by the consumer |

In the full URL `https://order-service.internal/api/orders/ORD-123?includeItems=true`, `https://order-service.internal` identifies the scheme and host, `/api/orders/ORD-123` is the **path**, and `includeItems=true` is the **query string**. The `?` character separates the path from the query.

In most consumer-driven contract tests, what matters are the **method, path, and request data that the consumer actually sends**. The internal host usually does not need to be hardcoded into the contract because it may differ across developer machines, CI, and deployment environments.

> Contract tests care about **observable communication**. They do not need to know which Java method name the producer uses internally, which repository it calls, or what database table is named.

## 3. Choosing an HTTP Method: The Same Path Alone Is Not Enough

The HTTP method is part of the public interface. Two requests with the **same path but different methods** usually represent two different behaviors.

| Method | Common Semantics | Example in the Order Service | Points to Note |
| --- | --- | --- | --- |
| `GET` | Read a resource representation without intending to modify state | `GET /api/orders/ORD-123` | The consumer may depend on the response structure or a `404` status |
| `POST` | Submit data for processing or create a resource per the API | `POST /api/orders` | May require a request body, `201`, or another agreed status |
| `PUT` | Create or replace resource state according to API semantics | `PUT /api/orders/ORD-123` | Typically aims for idempotency |
| `PATCH` | Partially modify a resource | `PATCH /api/orders/ORD-123` | Must agree on media type and patch structure |
| `DELETE` | Request deletion of a resource | `DELETE /api/orders/ORD-123` | Response may be `204`, `200`, or another published status |
| `HEAD` | Receive headers like `GET` but with no response body | `HEAD /api/orders/ORD-123` | Can be important for caching or existence checks |
| `OPTIONS` | Describe communication methods/options | `OPTIONS /api/orders` | Can relate to CORS/preflight |

The table above outlines **common HTTP semantics**, without imposing fixed statuses on every service. A contract must describe the **actual API behavior agreed upon by the producer and consumer**.

For example, a consumer that only calls:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
~~~

will not be automatically compatible if the producer drops support for `GET` and requires `POST /api/orders/lookup`. Even if the producer still returns an identical JSON body, the old consumer's request will no longer hit the right endpoint.

### 3.1. Method Should Be Chosen by Behavior, Not by Java Method Name

A Java method named `getOrder()` can be mapped with `@PostMapping`; the Java method name does not dictate the HTTP method. Conversely, renaming a Java method from `findById` to `lookupOrder` is not a breaking change if the observable HTTP endpoint remains unchanged.

In the contract DSL, declare the **method that the real client sends**. Only add contracts for other methods when a consumer actually uses them.

### 3.2. Idempotency Is a Semantic Concern That Must Be Tested at the Right Layer

Under HTTP semantics, `GET` is safe, while `PUT` and `DELETE` are designed to be idempotent. However, **a contract that only verifies a representative request/response does not prove idempotent behavior under repeated calls**. If repeating a call without side effects is an important requirement, add corresponding integration/domain tests.

## 4. Defining Method and Path in Groovy DSL

Minimal contract structure:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description('Get order by ID')

    request {
        method 'GET'
        urlPath('/api/orders/ORD-123')
    }

    response {
        status OK()
    }
}
~~~

Explanation:

- `Contract.make { ... }` creates a contract definition.
- `request { ... }` declares the request conditions sent by the consumer.
- `method 'GET'` requires the HTTP method to be `GET`.
- `urlPath('/api/orders/ORD-123')` declares the **path** portion of the URL.
- `response { status OK() }` commits the producer to return HTTP `200` for this scenario.

The contract above is conceptually valid, but **it does not verify a JSON body or media type yet**, because those two parts have not been declared. In a real-world scenario, you should include the fields that the consumer uses.

### 4.1. Using String Syntax or Helper Methods

The Groovy DSL supports equivalent ways to declare the method and status:

~~~groovy
request {
    method 'GET'
    urlPath '/api/orders/ORD-123'
}

response {
    status 200
}
~~~

You can use helpers:

~~~groovy
request {
    method GET()
    urlPath('/api/orders/ORD-123')
}

response {
    status OK()
}
~~~

**Pick one style in your project** for consistent readability, but what must remain stable is the method and path of the HTTP interface. Do not change `GET` to `POST` merely because of a DSL style preference.

### 4.2. A More Complete Contract

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')
    description('Consumer queries a confirmed order')

    request {
        method 'GET'
        urlPath('/api/orders/ORD-123')
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
            totalAmount: 199000
        )
    }
}
~~~

The contract specifies the **exact method and path** used by the consumer, while also recording important headers and the response body. Generated tests on the producer side must verify this behavior with an appropriate fixture; the stub generated from the contract provides a sample response for the consumer to test against.

A separate contract file typically resides in a directory such as:

~~~text
src/test/resources/contracts/orders/get_confirmed_order.groovy
~~~

The actual location can be reconfigured via the Maven or Gradle plugin; do not infer the location from the controller package name.

## 5. How Do `url` and `urlPath` Differ?

The Spring Cloud Contract Groovy DSL allows declaring the request URL using **`url` or `urlPath`**. The two options **must not be declared simultaneously in the same contract**.

~~~groovy
request {
    method 'GET'
    url('/api/orders/ORD-123')
}
~~~

and:

~~~groovy
request {
    method 'GET'
    urlPath('/api/orders/ORD-123')
}
~~~

In simple cases, both can represent the same path. However, the Spring Cloud Contract documentation **recommends `urlPath` for relative, host-independent paths**. This approach fits well when the producer runs on different addresses or ports in local tests and CI.

`url` also supports absolute URLs:

~~~groovy
request {
    method 'GET'
    url('http://localhost:8888/api/orders/ORD-123')
}
~~~

This syntax is supported, but it can tie the configuration to a specific environment. If the consumer is not committed to a fixed host, do not put temporary hostnames/ports into the contract just because they work on a developer machine.

**Do not do this:**

~~~groovy
request {
    method 'GET'
    url('/api/orders/ORD-123')
    urlPath('/api/orders/ORD-123') // Invalid: using both url and urlPath at the same time
}
~~~

Choose exactly one of the two. Throughout this lesson, examples prefer `urlPath` when only the path needs to be identified.

## 6. Defining Method and Path in YAML DSL

The same order lookup contract can be written in YAML:

~~~yaml
name: get_confirmed_order
description: Consumer queries a confirmed order
request:
  method: GET
  urlPath: /api/orders/ORD-123
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-123
    status: CONFIRMED
    totalAmount: 199000
~~~

Key fields:

| Groovy | YAML | Meaning |
| --- | --- | --- |
| `method 'GET'` | `method: GET` | HTTP method sent by the consumer |
| `urlPath('/api/orders/ORD-123')` | `urlPath: /api/orders/ORD-123` | Request path |
| `url('/api/orders/ORD-123')` | `url: /api/orders/ORD-123` | Another way to declare the URL |
| `response { status OK() }` | `response: status: 200` | Status committed by the producer |

In YAML, `request.method` and `request.urlPath` sit inside the `request` mapping. Do not place `urlPath` at the top level alongside `response`, because then the definition no longer matches the Spring Cloud Contract request structure.

Also, **do not include both `request.url` and `request.urlPath`** in the same YAML contract. Choose one property.

### 6.1. Choosing the DSL Format by Project

Groovy works well when a team needs a flexible DSL, matchers, nested lists/maps, and controlled expressive logic. YAML is approachable for people accustomed to reading declarative data. Both produce similar commitments for method and path, so **avoid maintaining duplicate copies of the same interaction** in the contract source directory read by the build.

## 7. Path, Path Variable, and Route Template

Consider two requests:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
GET /api/orders/ORD-456 HTTP/1.1
~~~

Both can be routed by Spring MVC to:

~~~java
@GetMapping("/api/orders/{orderId}")
public OrderView findById(@PathVariable String orderId) {
    return orderService.findById(orderId);
}
~~~

`{orderId}` in `@GetMapping` is a **server routing framework placeholder**. It is not the literal path string that the consumer sends over HTTP. The consumer sends a concrete value, such as `ORD-123`.

Therefore, a contract for a concrete request should use:

~~~groovy
request {
    method 'GET'
    urlPath('/api/orders/ORD-123')
}
~~~

Instead of assuming that:

~~~groovy
request {
    method 'GET'
    urlPath('/api/orders/{orderId}')
}
~~~

will automatically turn into a matcher for any ID. Without configuring a matcher, the curly braces may be treated as literal characters of the path, unlike Spring MVC's `@PathVariable` handling. **A server route template and a contract request matcher are two different concepts.**

### 7.1. A Path Segment Can Be an ID, Slug, or Version

| Path | Varying Segment | What Needs to Be Agreed On? |
| --- | --- | --- |
| `/api/orders/ORD-123` | `ORD-123` | ID format and lookup rules |
| `/api/products/keyboard-01` | `keyboard-01` | Is the slug case-sensitive? |
| `/api/users/42/addresses/7` | `42` and `7` | Resource identifiers and hierarchy |
| `/api/v1/orders/ORD-123` | `v1` and `ORD-123` | API version as part of the path |
| `/api/files/report%20november.pdf` | Space-encoded segment | Path encoding and decoding rules |

There is no need to test every possible ID; choose **representative paths that consumers use** and reasonable matchers to recognize valid formats.

### 7.2. Does a Path Distinguish a Trailing Slash?

The following two paths differ at the string level:

~~~text
/api/orders
/api/orders/
~~~

An application may redirect automatically or accept both, but that behavior depends on the framework and routing configuration. Do not assume the two paths are always equivalent. If a consumer depends on whether the path has a trailing `/` or not, explicitly decide on the committed endpoint and test according to actual behavior.

## 8. Dynamic Request Paths: Using Regex Purposefully

If the producer needs to serve many order IDs, a contract can use **regex** to match the path when generating the stub, while providing a **concrete value** so the generated producer test has a stable request.

Groovy example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description('Path following order ID format')

    request {
        method 'GET'
        url $(consumer(regex('/api/orders/ORD-[0-9]+')),
              producer('/api/orders/ORD-123'))
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(orderId: 'ORD-123')
    }
}
~~~

Explanation:

- `consumer(regex('/api/orders/ORD-[0-9]+'))`: **stub/consumer-side** matcher that accepts paths matching the ID pattern.
- `producer('/api/orders/ORD-123')`: **concrete** path value used when the generated producer test sends the request.
- `method 'GET'` remains a required part of the match condition; regex on the path does not change the method.

**Be careful with the stub's response body:** The sample contract still returns `orderId: ORD-123` even when the consumer calls `/api/orders/ORD-456` and the path regex allows that request. If the consumer requires the ID in the response to always equal the ID sent, you need an appropriate mechanism (such as suitable response templating), to restrict the stub to a fixed path, or to separate scenarios. A broad path matcher **does not automatically make response data dynamic based on the path variable**.

### 8.1. Regex Should Accurately Describe What the Consumer Is Allowed to Send

Examples:

| Matcher | Meaning | Risk |
| --- | --- | --- |
| `/api/orders/ORD-[0-9]+` | ID starting with `ORD-` followed by digits | Good when this is the public format |
| `/api/orders/.+` | Any non-empty path segment | May accept malformed IDs as well |
| `/api/.*` | Almost the entire API | Easily matches the wrong endpoint |
| Literal path `/api/orders/ORD-123` | Exactly one example | Stable for test scenarios, but does not describe an ID range |

The pattern must match **the entire segment checked by the framework** according to the regex semantics used by Spring Cloud Contract; avoid writing an ambiguous regex and expecting substring matching.

### 8.2. Why Not Use Regex for Every Path?

If the consumer actually calls the fixed endpoint `/api/orders/summary`, a regex like `/api/orders/.+` can accidentally match both `summary` and IDs. This makes the stub behave differently from the real producer or masks confusion between a fixed endpoint and an endpoint with a path variable.

Prefer literals when the scenario is truly fixed; only use regex when varying values carry communication meaning. When matchers have overlapping match regions, add distinguishing conditions or redesign the contract scope rather than relying on file ordering.

## 9. Path and Query Parameters: Do Not Mix Them Together

The following two requests have the **same path**, but different queries:

~~~http
GET /api/orders?status=PAID&page=0 HTTP/1.1
GET /api/orders?status=PENDING&page=0 HTTP/1.1
~~~

- **Path:** `/api/orders`
- **Query parameters:** `status` and `page`

In Groovy DSL, group them under `urlPath { queryParameters { ... } }`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('list_paid_orders')

    request {
        method GET()

        urlPath('/api/orders') {
            queryParameters {
                parameter 'status': 'PAID'
                parameter 'page': 0
                parameter 'size': 20
            }
        }

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
            items: [
                [orderId: 'ORD-123', status: 'PAID']
            ],
            page: 0
        )
    }
}
~~~

The contract describes a request with path `/api/orders` and the required query parameters. Using simple literals creates corresponding exact match conditions; when parameters need to vary, Spring Cloud Contract supports query parameter matchers such as `equalTo`, `containing`, and `matching`.

### 9.1. Equivalent YAML Example

~~~yaml
name: list_paid_orders
request:
  method: GET
  urlPath: /api/orders
  queryParameters:
    status: PAID
    page: 0
    size: 20
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    items:
      - orderId: ORD-123
        status: PAID
    page: 0
~~~

In YAML DSL, `queryParameters` is a mapping inside `request`. This representation clearly separates path and query; do not treat `status=PAID` as a path variable.

### 9.2. Distinguishing Path Variables from Query Parameters

| Request | Meaning | How to Describe |
| --- | --- | --- |
| `GET /api/orders/ORD-123` | Look up a specific order | The ID value is inside `urlPath` |
| `GET /api/orders?status=PAID` | Find orders by status | `urlPath('/api/orders')` + `queryParameters` |
| `GET /api/orders/ORD-123?includeItems=true` | Look up an order with an expansion option | ID in path, option in query |
| `GET /api/orders?page=2` | Paginate a collection | Fixed path, page index in query |

You cannot unilaterally change `GET /api/orders/ORD-123` into `GET /api/orders?id=ORD-123` and still consider it compatible, unless the producer intentionally supports both forms and the consumer is updated or already uses both.

### 9.3. Do You Need to Declare Every Query Parameter?

No. A good contract constrains the query parameters that the consumer **needs and actually depends on**. If the consumer does not care about an optional parameter, fixing it in the contract can make the stub unnecessarily strict. Conversely, if the consumer depends on the `status=PAID` filter, omitting that query can cause the stub to return data for the wrong scenario.

In addition, **a missing query parameter, an empty value, and a concrete value** are different states. If the API has different meanings for these cases, create separate appropriate contract scenarios.

## 10. Method and Path Are Not Enough When the Consumer Has Additional Conditions

Spring Cloud Contract defines the minimal HTTP request via method and URL, but sometimes those two elements alone are not enough to distinguish behavior. Other parts of the request can cause the producer to choose a different processing branch:

| Additional Component | Example | Why Record It in the Contract? |
| --- | --- | --- |
| `Content-Type` | `application/json` | The producer needs to know how to parse the request body |
| `Accept` | `application/json` or `application/xml` | The consumer requests a specific response type |
| Business header | `X-Tenant-Id` | The request may route/scope data by tenant |
| Query | `includeItems=true` | Changes response structure or level of detail |
| Request body | Order creation JSON | `POST` or `PATCH` often depends on the payload |
| Path version | `/api/v2/orders` | Identifies the interface version |

For example, two contracts may both use `GET /api/orders/ORD-123` but differ in the `Accept` header and therefore expect different response media types. When designing stubs, include the condition that actually distinguishes the two cases in the contract; if both mappings match the same request while returning different responses, consumer test results may not be as intended.

### 10.1. Example POST Request with the Right Method and Endpoint

~~~groovy
request {
    method POST()
    urlPath('/api/orders')
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: 'CUS-7',
        items: [
            [sku: 'BK-1', quantity: 2]
        ]
    )
}
~~~

If the producer changes to `POST /api/order` (missing the `s`) or `PUT /api/orders`, the corresponding generated producer test/consumer stub needs to reflect the difference. Do not edit the contract to match the new code without first checking whether old consumers are affected.

## 11. One Endpoint, Multiple Methods: Create Separate Contracts

Suppose the producer has the same path `/api/orders/ORD-123` but supports:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
~~~

~~~http
PATCH /api/orders/ORD-123 HTTP/1.1
Content-Type: application/json

{"status":"CANCELLED"}
~~~

~~~http
DELETE /api/orders/ORD-123 HTTP/1.1
~~~

These are **three distinct interactions**. Do not try to cram three methods onto a single `method` line, and do not assume a contract written for `GET` will protect `PATCH` or `DELETE`.

You can organize them into files:

~~~text
src/test/resources/contracts/orders/
├── get_order.groovy
├── cancel_order.groovy
└── delete_order.groovy
~~~

Or group related contracts into one file returning a list of `Contract.make`. Whichever approach you choose, **each contract must have its own request conditions and its own expected response**.

### 11.1. HTTP `404`, `405`, and Path Changes

In typical web applications:

- `404 Not Found` commonly occurs when no matching route/resource exists, though not every `404` is caused by a non-existent path.
- `405 Method Not Allowed` commonly occurs when a route is recognized but the method is not supported.
- `301`, `302`, or `308` may appear if the server/proxy performs a redirect.

The exact status code depends on the server, routing, security, and application configuration. Contracts must stick to **the status actually committed to the consumer**, rather than mechanically inferring that changing the method always produces `405` or changing the path always produces `404`.

## 12. Which Changes Break the Method/Path Contract?

Consider a consumer sending `GET /api/v1/orders/ORD-123`. Producer changes have different impacts:

| Change from Producer | Likely Compatible with Old Consumer? | Reason |
| --- | --- | --- |
| Change to `POST /api/v1/orders/ORD-123` and remove `GET` | No | Consumer still sends `GET` |
| Change path to `/api/v2/orders/ORD-123` and remove v1 | No | Consumer still uses the v1 path |
| Keep old endpoint, add new endpoint | Possibly | Old consumer can still call the committed endpoint |
| Rename Java method or controller class | Yes | Does not change HTTP communication if routing/response stay the same |
| Add required path segment `/tenant/1` | No for old clients | Old request does not match the new endpoint |
| Move `orderId` from path to query and remove old path | No | Old clients do not rewrite URLs automatically |
| Add optional query parameter with compatible default | Usually yes | Old request remains valid if server preserves committed behavior |
| Add required query parameter | Potentially breaking | Old clients do not send the new field |
| Change `/api/orders` to `/api/orders/` | Configuration-dependent | Paths may be distinguished by the router/proxy |

**API evolution strategy:** If you need to change a method or path, you can keep the old route during a transition period, add the new route, migrate consumers on a schedule, and only remove the old route after verifying no dependent consumers remain. A new URL version does not automatically make old clients compatible.

## 13. How Do Producer Tests and Stub Runner Verify Method/Path?

Given the contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_by_id')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
    }

    response {
        status OK()
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED'
        )
    }
}
~~~

Typical flow:

~~~mermaid
flowchart TD
    A["Contract: GET /api/orders/ORD-123"] --> B["Plugin generates producer-side tests"]
    B --> C["Test calls producer/MockMvc using defined GET and path"]
    C --> D{"Does response match contract?"}
    D -- "No" --> E["Producer verification fails"]
    D -- "Yes" --> F["Producer verification passes"]
    A --> G["Plugin generates stub for corresponding request"]
    F --> H["Publish versioned stub artifact"]
    G --> H
    H --> I["Consumer test uses Stub Runner"]
    I --> J["Verify client calls the right method/path"]
~~~

**Producer side:** Generated tests send requests matching the method and path in the DSL. The base class must provide an appropriate runtime environment (such as Spring MVC/MockMvc) and fixtures so the producer returns the response per the contract.

**Consumer side:** Stub Runner can launch stubs from the published artifact. If a consumer accidentally changes `GET` to `POST` or calls the wrong path, the stub mapping for the agreed interaction will fail to match the request, helping catch bugs in how the client communicates.

Contract tests **do not automatically test every route**, nor do they replace security testing, proxy configuration checks, performance testing, or real gateway routing tests. They protect the interactions that have been written, generated into tests, and actually executed.

### 13.1. Integrating Producer Verification into CI

For a Maven project configured with the Spring Cloud Contract plugin:

~~~bash
./mvnw -B clean verify
~~~

For a Gradle project configured with the plugin and appropriate test tasks:

~~~bash
./gradlew clean build
~~~

These commands only illustrate how to run the pipeline. Test generation and contract execution depend on the build configuration, Spring Boot/Spring Cloud Contract versions, and the project's base test class.

A valuable CI pipeline should verify that:

1. Groovy/YAML contracts are placed in the source directory read by the plugin.
2. Generated producer tests are **generated and executed**, not skipped.
3. A breaking change to method/path causes tests to fail as expected.
4. Stubs are published after the producer passes the corresponding verification.
5. Consumer CI uses the managed stub version to catch calls to the wrong endpoint.

## 14. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Invalid contract DSL | Missing `method` or both `url` and `urlPath` specified | Check the two required properties; choose exactly one URL form |
| Test returns `404` instead of `200` | Wrong path or fixture lacks the resource | Compare request path, controller mapping, and data setup |
| Test returns `405` | Wrong method relative to registered route | Cross-check method across consumer, contract, and producer |
| Test fails in CI environment | Contract hardcodes local host/port | Use an appropriate relative path or configure the environment properly |
| Stub does not match request | Different query/header or overly strict regex | Check the actual matching conditions |
| Stub matches wrong scenario | Overly broad regex or overlapping mappings | Narrow the pattern/distinguishing conditions |
| Path contains spaces/Unicode | Different encoding between client and server | Standardize percent-encoding and inspect data on the wire |
| Endpoint has trailing slash | Router distinguishes `/orders` and `/orders/` | Standardize public URL or verify intentional redirects |
| Generated test does not appear | Plugin not configured, wrong contract path, build skipped | Inspect logs of the generation and test execution steps |
| Test redirects unexpectedly | Gateway, proxy, or filter alters path/redirects | Check request target across layers and public commitment |

### 14.1. Checklist When Encountering Method/Path Errors

When a generated test fails, cross-check in order:

1. **Contract:** What is `method`, what is `url`/`urlPath`, and are there accompanying queries/headers?
2. **Generated request:** Which URL does the test actually send to, and are dynamic path values encoded?
3. **Producer routing:** Do `@GetMapping`/`@PostMapping`/gateway configuration match the method and path?
4. **Base class:** Are the right controller, servlet context path, sample data, and filters initialized?
5. **Response:** Did it fail because the route was not found, because data was missing, or because the producer broke the commitment?

Do not edit generated test code in the build output directory to hide errors: on the next generation run, those changes will be overwritten. Fix the source in the contract, setup, or producer code.

## 15. Hands-On Exercise: Building HTTP Contracts for Inventory Service

Suppose `Inventory Service` provides three behaviors:

| Scenario | Request | Result to Verify |
| --- | --- | --- |
| Look up stock | `GET /api/inventory/SKU-100` | `200`, `sku: SKU-100`, `available: 8` |
| Filter stock by warehouse | `GET /api/inventory?warehouse=HCM&page=0` | `200`, list of SKUs in the warehouse |
| Update stock | `PATCH /api/inventory/SKU-100` | `200`, new quantity or appropriate business error code |

### 15.1. Tasks

1. Write a Groovy contract for `GET /api/inventory/SKU-100`, using `method` and `urlPath`.
2. Write an equivalent YAML contract for the same scenario. Do not keep both duplicate contracts active in the same source tree when verifying the build.
3. Write a second Groovy contract for `GET /api/inventory` with two query parameters `warehouse=HCM` and `page=0`.
4. Choose a sample request for `PATCH /api/inventory/SKU-100` with body `{"available": 10}`. Explain why you cannot use the `GET` contract to verify this `PATCH` request.
5. Suppose the producer removes the `/api/inventory/SKU-100` path and only supports `/api/stock/SKU-100`. Predict which producer verification step must fail.
6. Update the producer to preserve the old endpoint or agree on a new contract with the consumer; re-run verification using the existing pipeline.

### 15.2. Suggested Groovy Solution for Single-SKU Lookup

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('inventory_get_sku_success')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
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
            sku: 'SKU-100',
            available: 8
        )
    }
}
~~~

### 15.3. Suggested YAML Solution

~~~yaml
name: inventory_get_sku_success
request:
  method: GET
  urlPath: /api/inventory/SKU-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-100
    available: 8
~~~

### 15.4. Suggested Query Parameters Solution

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('inventory_search_by_warehouse')

    request {
        method 'GET'
        urlPath('/api/inventory') {
            queryParameters {
                parameter 'warehouse': 'HCM'
                parameter 'page': 0
            }
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            items: [
                [sku: 'SKU-100', available: 8]
            ]
        )
    }
}
~~~

To verify `PATCH`, you need a separate contract with `method PATCH()` (or `'PATCH'`), `urlPath('/api/inventory/SKU-100')`, and the agreed JSON body. The path may be the same as `GET` but the method differs, so the two scenarios must be verified independently.

### 15.5. Self-Assessment

- When changing `GET` to `POST`, how should the old producer test react?
- When changing `/api/inventory/SKU-100` to `/api/stock/SKU-100`, should you just edit the contract and ignore running consumers?
- Does the `warehouse=HCM` parameter belong to the path or the query? If you omit it from the contract, will the stub still distinguish the warehouse properly?
- When using the matcher `/api/inventory/SKU-[0-9]+`, why should you consider the response data and fixed endpoints that could match the same pattern?

**Suggested answers:** Method and path are communication commitments, so changing them can break old clients; query parameters are a separate component; regex should be sufficiently tight and stub responses should stay consistent with real requests.

## 16. Checklist Before Saving an HTTP Contract

- [ ] The contract clearly declares the **method** that the consumer actually sends.
- [ ] The contract uses **one** of the two properties `url` or `urlPath`.
- [ ] The path is written to match the public interface, including prefix, version, and slashes as needed.
- [ ] Path variables, query parameters, and headers have been properly distinguished.
- [ ] If regex is used for a dynamic path, a concrete producer-side value is provided so generated tests run reliably.
- [ ] The matcher is not overly broad in a way that causes the stub to mismatch endpoints or return wrong data.
- [ ] Separate contracts exist for different methods/scenarios that consumers depend on.
- [ ] Fixtures and base classes are sufficient for the producer to return the result specified by the contract.
- [ ] Method/path changes have been evaluated for consumer compatibility before merging.
- [ ] CI generates **and runs** producer tests; stubs are published according to the verified producer version.

## 17. References

- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): required components of an HTTP request, `url`, `urlPath`, and query parameters.
- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matchers and consumer/producer values used in contracts.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, contract structure, and stub/test generation mechanisms.

**Remember:** **HTTP method and request path** are the first two commitments of an HTTP contract. `GET /api/orders/ORD-123` is a different interaction from `POST /api/orders/ORD-123` or `GET /api/orders?id=ORD-123`. Describe the consumer's exact request using Groovy/YAML DSL, keep matchers precise enough, and run generated producer tests in CI before publishing stubs.
