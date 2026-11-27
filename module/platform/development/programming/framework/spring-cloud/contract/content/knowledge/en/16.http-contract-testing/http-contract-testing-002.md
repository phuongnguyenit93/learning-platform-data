# Using RestAssuredMockMvc in Base Tests

## 1. The Problem: Contracts Are Generated into Tests, but How Do They Make HTTP Calls?

In **Spring Cloud Contract**, producer and consumer agree on verifiable interactions: HTTP methods, paths, query parameters, headers, request bodies, and expected responses. Contracts written in **Groovy/YAML DSL** are converted by **Contract Verifier** into producer-side tests; from the same contracts, stubs can be produced for the consumer to run via **Stub Runner**. CI can block incompatible API changes when generated producer tests fail.

However, the following Groovy snippet **cannot start a web application on its own**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 120000
        )
    }
}
~~~

The plugin can generate a test that sends a request like `GET /api/orders/ORD-123`, but the test still needs **an environment to invoke the producer's controller** and prepare data so the outcome is predictable. A common approach when the producer uses **Spring MVC** is configuring **RestAssuredMockMvc** in a **base test class**.

The central statement of this lesson is:

~~~java
RestAssuredMockMvc.mockMvc(mockMvc);
~~~

It tells RestAssuredMockMvc that RestAssured-style HTTP calls in generated tests should use the configured `MockMvc` instance rather than requiring a real HTTP server to be started.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **MockMvc**, **RestAssuredMockMvc**, **generated tests**, and the **base test class**.
2. Configure a base class with `@WebMvcTest` or `@SpringBootTest` depending on the verification scope.
3. Understand the role of `@BeforeEach` and `RestAssuredMockMvc.mockMvc(mockMvc)`.
4. Prepare appropriate mocks/fixtures so requests sent by generated tests receive the committed responses.
5. Read plugin configuration to verify generated tests extend the right base class and use the matching HTTP test mode.
6. Troubleshoot common errors: tests not found, application context failures, `401/403`, `404`, JSON mismatches, and genuine API changes.
7. Integrate producer verification into CI before publishing stubs for consumers.

> **Important limitation:** RestAssuredMockMvc is intended for **Spring MVC (Servlet stack)**. It does not turn a purely reactive WebFlux application into Spring MVC, nor does it replace testing gateways, HTTP sockets, TLS, or real deployment environments.

## 2. Four Components Working Together

| Component | Role | Who creates or configures it? |
| --- | --- | --- |
| **Contract DSL** | Describes requests and responses the consumer depends on | Producer/consumer development team |
| **Generated producer test** | Builds requests, calls producer, asserts status/headers/body | Spring Cloud Contract Verifier |
| **Base test class** | Sets up Spring environment, `MockMvc`, mocks/fixtures, and test hooks | Producer developer |
| **RestAssuredMockMvc** | Provides RestAssured-style request/response API running over Spring `MockMvc` | Library + base class configuration |

Execution flow:

~~~mermaid
flowchart TD
    A["Contract: GET /api/orders/ORD-123"] --> B["Contract Verifier generates producer test"]
    B --> C["Generated test extends ContractVerifierBase"]
    C --> D["@BeforeEach prepares MockMvc + fixtures"]
    D --> E["RestAssuredMockMvc sends request via MockMvc"]
    E --> F["Spring MVC routing → controller → serialization"]
    F --> G["Generated assertions: HTTP status, headers, JSON"]
    G --> H{"Matches contract?"}
    H -- "No" --> I["Build reports failure"]
    H -- "Yes" --> J["Producer verification passes"]
    A --> K["Generate stub mappings"]
    J --> L["Publish stubs after verification"]
    K --> L
    L --> M["Consumer tests via Stub Runner"]
~~~

Remember that generated tests **extend the base class** to use the prepared environment. RestAssuredMockMvc does not replace the JUnit test runner; it is the bridge between request/assertion code and Spring MVC.

### 2.1. Why Not Put All Setup Directly in the Contract?

Contracts should express only **observable behavior at the API boundary**. Putting repository mocking details, internal class names, or database records into the DSL tightly couples the contract to implementation details, making it harder to refactor architecture while keeping the API compatible.

For example, the consumer cares about:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

and not whether the controller called `OrderRepository.findById` or `OrderQueryService.findById`. Setup details belong in the producer's base class or test support code.

## 3. How Does MockMvc Differ from RestAssuredMockMvc and Real HTTP RestAssured?

**MockMvc** belongs to Spring Test. It simulates HTTP requests flowing through Spring MVC infrastructure: handler mapping, controllers, argument resolution, validation, message converters, and filters registered in the test context. No sockets are opened and no HTTP port is bound.

**RestAssuredMockMvc** provides RestAssured-like testing syntax while using MockMvc as the request dispatch mechanism. Spring Cloud Contract can generate tests in this mode.

**RestAssured** (real HTTP), by contrast, sends requests over the network to a running server, typically an application started with `@SpringBootTest(webEnvironment = RANDOM_PORT)` or another live HTTP environment.

| Criterion | RestAssuredMockMvc + MockMvc | Real HTTP RestAssured on Live Server |
| --- | --- | --- |
| Socket/HTTP port | Not needed | Requires a running HTTP server |
| Scope | Spring MVC inside test context | Full HTTP stack running on server |
| Startup performance | Usually fast, especially MVC slice | Can be heavier due to starting the server |
| MVC filter/security testing | Possible, depending on setup | Possible through the live stack |
| TLS/proxy/gateway outside app | No | Only when actually in the request path |
| Pure WebFlux application | Not a natural fit | Needs test mode suited to reactive stack |
| Base setup | `RestAssuredMockMvc.mockMvc(mockMvc)` | Host/port/base URI or HTTP client config |

A test using MockMvc **still executes real web-layer classes present in the context**, not merely "simulating responses" like a stub. However, if the underlying service is mocked, service logic is not exercised; that is a choice of **test scope**, not a flaw of MockMvc.

## 4. Example System Used in This Lesson: Order Service

Suppose the producer exposes `GET /api/orders/{orderId}`. The consumer expects that when order ID `ORD-123` exists, it receives:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000,
  "paid": true
}
~~~

An illustrative Spring MVC controller:

~~~java
package com.example.orders.api;

import com.example.orders.application.OrderService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    public OrderView getById(@PathVariable String orderId) {
        return orderService.findById(orderId);
    }
}
~~~

Response DTO using a Java record:

~~~java
package com.example.orders.api;

public record OrderView(
        String orderId,
        String status,
        long totalAmount,
        boolean paid
) {}
~~~

Illustrative service interface:

~~~java
package com.example.orders.application;

import com.example.orders.api.OrderView;

public interface OrderService {
    OrderView findById(String orderId);
}
~~~

When writing `@WebMvcTest`, we can **mock `OrderService`** so the controller returns a deterministic DTO. If the project uses a Java version without record support, substitute a DTO class with getters and equivalent serialization.

### 4.1. Source Contract

Illustrative file `src/test/resources/contracts/orders/get_confirmed_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')
    description('Consumer reads a confirmed order')

    request {
        method GET()
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
            totalAmount: 120000,
            paid: true
        )
    }
}
~~~

This contract requires the producer to satisfy the method, path, status, media type, and meaningful JSON values. The generated test will send the corresponding request for you, but **it does not yet know how to prepare order `ORD-123`**; that is the responsibility of the base class.

## 5. Approach 1: Base Test Using `@WebMvcTest` and RestAssuredMockMvc

For a Spring MVC endpoint that you want to verify at the **web slice** (controller, request mapping, HTTP status, JSON serialization), `@WebMvcTest` is often appropriate.

A base class can be written as follows:

~~~java
package com.example.orders.contract;

import com.example.orders.api.OrderController;
import com.example.orders.api.OrderView;
import com.example.orders.application.OrderService;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;

@WebMvcTest(OrderController.class)
public abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @BeforeEach
    protected void configureContractTest() {
        given(orderService.findById("ORD-123"))
                .willReturn(new OrderView(
                        "ORD-123", "CONFIRMED", 120000L, true
                ));

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

This is an **example for Spring Boot using Spring Framework 6.2+**, where `@MockitoBean` resides in package `org.springframework.test.context.bean.override.mockito`. On older Spring Boot versions, projects may need `@MockBean` instead and adjusted imports. Do not copy annotations without checking the Spring Boot/Spring Cloud Contract versions managed by your project.

### 5.1. Reading Each Part of the Base Class

**`@WebMvcTest(OrderController.class)`:** Loads the web slice containing the controller and supported MVC components; does not automatically load the entire application bean graph. It keeps tests focused on the HTTP boundary.

**`@Autowired MockMvc mockMvc`:** Receives the `MockMvc` instance provided by Spring Test for this context.

**`@MockitoBean OrderService orderService`:** Creates/replaces the controller's dependency with a Mockito mock in the context. This lets the test avoid needing a real database to create an `ORD-123` order.

**`given(...).willReturn(...)`:** Prepares a stable return value from the dependency when the controller looks up `ORD-123`. This data must **match the contract**.

**`@BeforeEach`:** Runs before each test method in JUnit Jupiter, including tests generated in subclasses extending the base class.

**`RestAssuredMockMvc.mockMvc(mockMvc)`:** Configures RestAssuredMockMvc so calls made by generated tests **go through the prepared MockMvc**.

### 5.2. Why Place Setup in `@BeforeEach`?

Generated tests may verify multiple contracts: existing orders, missing orders, responses with different headers or queries. Setup in `@BeforeEach` gives **each test a predictable starting state**.

In particular, RestAssuredMockMvc holds global configuration points in the test runtime. If a test suite uses multiple contexts or controllers, configure the proper MockMvc for each test to avoid order dependence and prevent later tests from inheriting leftover setup from earlier tests.

Do not use `@BeforeAll` and assume a single mock context suffices for all tests when multiple environments or distinct states exist. When the application needs mocks reset or changed across scenarios, organize setup per test or per appropriate contract group.

### 5.3. Notes on Class and Package Visibility

`ContractVerifierBase` must be **visible to generated tests at compile time** and configured in the plugin with the exact package and class name. Base classes are typically `public abstract class`. Generated tests extend it without needing manual hook calls if JUnit is configured compatibly.

If the plugin generates classes in a different package, they can still extend a public base class via import or fully-qualified name; however, package-private members in the base class can cause issues. Use appropriate visibility and avoid initialization logic that depends on the generated test's package name.

## 6. Approach 2: Using `@SpringBootTest` with `@AutoConfigureMockMvc`

`@WebMvcTest` focuses on an MVC slice. When you want to run **more real application beans** (services, mappings, configuration) while still sending requests via MockMvc, you can use:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
public abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    protected void configureContractTest() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

In this approach, producer tests exercise **more real Spring configuration**. Data for `ORD-123` must be prepared realistically: a test database, SQL fixtures, test transactions, stubs for external systems, or deliberate dependency overrides.

### 6.1. Comparing the Two Testing Levels

| Aspect | `@WebMvcTest` | `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` |
| --- | --- | --- |
| Controller and MVC serialization | Yes | Yes |
| Real service/repository | Usually no; requires mocking/importing | Can be present if loaded by context |
| Startup time | Usually lower | Can be higher |
| Debugging business wiring | Limited scope | Broader |
| Database/message broker dependencies | Can be avoided with mocks | May require configuration or replacement |
| Best suited for | Focused web contract verification | Verifying contracts across multiple application layers |

**Neither approach is universally superior.** A web-slice contract test catches routing, HTTP status, header, and DTO serialization bugs, but does not guarantee the real service calculates totals accurately. A full-context test covers more ground but is slower and more coupled to infrastructure. Choose based on API risk and environment isolation capability.

### 6.2. Why Not Use a Random Port Server to Call RestAssuredMockMvc?

`@SpringBootTest(webEnvironment = RANDOM_PORT)` starts an HTTP server, whereas RestAssuredMockMvc still uses **MockMvc** and does not automatically switch to calling the opened port. If your goal is real HTTP sockets, configure the matching generated test mode/client (for example, RestAssured HTTP). If your goal is an in-JVM web test, `MOCK` + `MockMvc` is clearer.

## 7. Common Ways to Initialize RestAssuredMockMvc

Depending on how tightly you want to control the context, RestAssuredMockMvc offers several initialization options.

### 7.1. Passing an Existing MockMvc

~~~java
@Autowired
MockMvc mockMvc;

@BeforeEach
protected void setup() {
    RestAssuredMockMvc.mockMvc(mockMvc);
}
~~~

This is the **central approach of this lesson**: you already have Spring Test configured and simply pass `MockMvc` into RestAssuredMockMvc.

### 7.2. Using WebApplicationContext

In projects that hold a `WebApplicationContext` and want RestAssuredMockMvc to build configuration from the context:

~~~java
@Autowired
WebApplicationContext context;

@BeforeEach
protected void setup() {
    RestAssuredMockMvc.webAppContextSetup(context);
}
~~~

Depending on the version, syntax and filter setup may need adjustment. This approach is helpful if you want to build directly from an existing web context instead of passing a Spring Test-provided `MockMvc`.

### 7.3. Standalone Setup

For isolating a controller and providing dependencies manually:

~~~java
OrderService orderService = mock(OrderService.class);
OrderController controller = new OrderController(orderService);

RestAssuredMockMvc.standaloneSetup(controller);
~~~

This is an **illustrative standalone configuration**, not a complete base class: you still need stubbing for `orderService`, and if the API uses custom exception handlers, converters, filters, or validation, you must register them explicitly. Standalone runs quickly but can omit MVC components active in production.

**Do not arbitrarily mix multiple setup methods in the same test.** Choose the method that matches your context and contract, then verify generated tests actually use the expected configuration.

## 8. Ensuring the Plugin Generates Tests with the Right HTTP Test Mode and Base Class

Creating `ContractVerifierBase` is not enough. The plugin must know which base class generated tests should extend, and the generated code must match the intended request dispatch mechanism.

Example Maven configuration (illustrative; use versions compatible with your project's Spring Boot/Spring Cloud):

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <baseClassForTests>
          com.example.orders.contract.ContractVerifierBase
        </baseClassForTests>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

In this example:

- `baseClassForTests` specifies the superclass for generated tests.
- `testFramework` determines which test framework code the plugin generates; `JUNIT5` targets JUnit Jupiter.
- `testMode` is `MOCKMVC` to generate RestAssuredMockMvc-based calls.
- `extensions` enables the Maven lifecycle integration for the plugin in the standard setup.
- The version placeholder **must be replaced with a compatible version** in your project; copying it verbatim will not resolve in Maven.

Test dependencies typically include the Spring Cloud Contract Verifier starter and Spring Boot test starter:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Dependency versions should be managed consistently via Spring Cloud/Spring Boot dependency management. In projects using other plugins or starters, adjust according to the corresponding version documentation.

### 8.1. Gradle Must Also Align the Test Mode

With Gradle, the goals remain the same:

1. Apply the appropriate Spring Cloud Contract plugin.
2. Declare the source directory containing contracts.
3. Specify the base class for generated tests.
4. Select a JUnit/test mode compatible with RestAssuredMockMvc.
5. Run the contract test generation task and related test execution tasks.

Gradle DSL configuration varies by plugin and version, so do not copy Maven XML like `<testMode>MOCKMVC</testMode>` into `build.gradle`. Use the Gradle syntax supported by your project and confirm directly by inspecting the generated Java test.

### 8.2. Contract Sources and Base Class Can Reside in Different Directories

Example directory tree:

~~~text
order-service/
├── src/test/resources/contracts/orders/
│   ├── get_confirmed_order.groovy
│   └── get_order_not_found.groovy
├── src/test/java/com/example/orders/contract/
│   └── ContractVerifierBase.java
└── target/generated-test-sources/contracts/
    └── ... generated Java tests ...
~~~

The output path only illustrates a common Maven layout. Plugins and projects may choose different locations.

**Rule:** Do not commit generated tests into source control just so they "always exist." The DSL and base class are active sources; generated tests are build outputs that should be generated and executed in CI.

## 9. Reading Generated Tests to Confirm MockMvc Is Connected Properly

When the plugin is configured properly, generated code may use APIs similar to:

~~~java
// ABBREVIATED ILLUSTRATION: not verbatim plugin-generated output
class GetConfirmedOrderTest extends ContractVerifierBase {

    @Test
    void validateGetConfirmedOrder() {
        MockMvcRequestSpecification request = given()
            .header("Accept", "application/json");

        ResponseOptions response = given()
            .spec(request)
            .get("/api/orders/ORD-123");

        assertThat(response.statusCode()).isEqualTo(200);
        // Assertions for Content-Type and JSON body per contract
    }
}
~~~

The name `GetConfirmedOrderTest` and exact assertion APIs may differ by plugin version; this example points out the **signs to look for**:

- The generated test **extends** the exact `ContractVerifierBase`.
- The test constructs a request with `GET`, path `/api/orders/ORD-123`, and `Accept` header.
- The call is executed by the MockMvc-style API generated for the selected mode.
- Response status and JSON fields have corresponding assertions.

Do not treat this abbreviated example as ready-to-compile Java source. In a real project, open the full generated Java file to inspect imports, `given()` calls, response types, and exact assertions.

### 9.1. How the Connection Flows Through the Base Class

When JUnit runs a test in the subclass:

~~~text
JUnit instantiates generated test
    ↓
Spring Test creates MVC context
    ↓
JUnit invokes @BeforeEach inherited from base class
    ↓
Base class prepares OrderService mock and RestAssuredMockMvc.mockMvc(mockMvc)
    ↓
Generated test sends GET /api/orders/ORD-123
    ↓
MockMvc routes to OrderController.getById(...)
    ↓
Controller calls OrderService mock, receives OrderView
    ↓
Spring JSON converter produces HTTP 200 + JSON
    ↓
Generated assertions verify contract
~~~

If you omit `RestAssuredMockMvc.mockMvc(mockMvc)` and have no equivalent setup, the generated test may fail to find the MockMvc environment required to dispatch requests. If the `OrderService` mock is missing in `@WebMvcTest`, the application context may fail to instantiate the controller.

## 10. Expanding: 404 Contracts and Base Classes with Multiple Fixtures

Consumers may rely on both success and not-found branches:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')

    request {
        method GET()
        urlPath('/api/orders/ORD-404')
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND'
        )
    }
}
~~~

The producer needs to return error code `ORDER_NOT_FOUND` if `ORD-404` does not exist. With `@WebMvcTest`, you can stub the dependency:

~~~java
@BeforeEach
protected void configureContractTest() {
    given(orderService.findById("ORD-123"))
        .willReturn(new OrderView(
            "ORD-123", "CONFIRMED", 120000L, true
        ));

    given(orderService.findById("ORD-404"))
        .willThrow(new OrderNotFoundException("ORD-404"));

    RestAssuredMockMvc.mockMvc(mockMvc);
}
~~~

This example assumes `OrderNotFoundException` and an exception handler already exist in the application. If `@WebMvcTest` does not automatically include the needed handler in the context, configure `@Import(OrderErrorHandler.class)` or the corresponding registration so error responses match the API structure.

### 10.1. Example Handler for 404

~~~java
@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> handle(
            OrderNotFoundException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "ORDER_NOT_FOUND"));
    }
}
~~~

This is an illustrative snippet; to compile, import the required Spring and Java classes along with the `OrderNotFoundException` definition. The key point: **service exceptions do not automatically turn into contract-compliant error JSON** unless the application has a matching handling mechanism.

A contract that only asserts status `404` can pass simply because the router could not find the endpoint, even when "order not found" handling is not implemented. Check both the **error body** and a valid path to avoid false conclusions.

## 11. Testing Requests with Bodies: POST and Validation

RestAssuredMockMvc also works for `POST`, `PUT`, or `PATCH` contracts with JSON bodies. For example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_valid')

    request {
        method POST()
        urlPath('/api/orders')
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'CUS-7',
            items: [[sku: 'BK-1', quantity: 2]]
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-200',
            status: 'CREATED'
        )
    }
}
~~~

For this generated test to pass, the web slice must have:

- A controller mapping `POST /api/orders`.
- A JSON message converter capable of deserializing the body.
- Bean Validation running if the controller uses `@Valid` or matching constraints.
- A service dependency or mock configured to return the corresponding response.
- HTTP status `201` and a JSON body matching the schema.

**Warning:** If you mock the controller directly or bypass validation/filters just to get the expected response, the generated test may pass without protecting the required HTTP behavior.

### 11.1. Testing Invalid Input Branches

An error contract might require:

~~~groovy
request {
    method POST()
    urlPath('/api/orders')
    headers {
        contentType(applicationJson())
    }
    body(customerId: '')
}

response {
    status BAD_REQUEST()
    headers {
        contentType(applicationJson())
    }
    body(code: 'VALIDATION_FAILED')
}
~~~

When running with `@WebMvcTest`, the request must go through MVC validation and proper exception mapping; the base class should not stub a service mock to fake `400` if the goal is testing web-layer validation. If the API expects error code `VALIDATION_FAILED`, the producer must have a handler/mapper producing that field—do not assume Spring Boot generates that exact body by default.

## 12. Matchers and Two-Sided Values in Generated Tests

Fields like IDs or timestamps can vary. Spring Cloud Contract can use matchers instead of rigid literals:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 'ORD-200',
        status: 'CREATED'
    )
    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
    }
}
~~~

With this matcher:

- Consumer stubs can use the sample value `ORD-200`.
- Generated producer tests can accept IDs such as `ORD-345` as long as they match `ORD-[0-9]+`.
- `status: CREATED` remains a business value verified strictly since it is not replaced by a matcher.

Important: **RestAssuredMockMvc is only the HTTP invocation mechanism in the test**; it does not decide which matchers to use. Assertions come from the DSL and the rules generated by the plugin. If a generated test accepts a wrong-typed response because a matcher is too permissive, fix the contract/matcher, not the MockMvc initialization.

### 12.1. Request Matchers

~~~groovy
body(
    customerId: $(consumer(regex('CUS-[0-9]+')),
                  producer('CUS-7'))
)
~~~

The generated producer test uses the **concrete value `CUS-7`** to send to the controller. Consumer-side stubs can accept codes matching the pattern. The base class should prepare fixtures for `CUS-7` and all producer-side cases actually generated into tests.

Do not assume a single generated test using `CUS-7` proves the producer works across all possible customer IDs. Add other tests according to risk for broader behavior.

## 13. Security Configuration: Do Not Disable Filters When Contracts Depend on Them

With Spring Security, web-slice tests can return `401 Unauthorized` or `403 Forbidden` even when the controller and fixtures are correct. That is not necessarily a contract bug; check what authentication the published API requires.

Some projects use:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

to strip filters during tests. While this lets simple scenarios run, it **simultaneously removes request filtering rules from verification**, including security filters. Do not treat this as a default fix for `403` errors.

Better options, depending on the contract:

1. Provide an appropriate principal/authorities in the Spring Security test context for valid requests.
2. Declare sample headers/tokens matching policy and configure test authentication accordingly.
3. Write dedicated contracts for `401`/`403` if consumers actually rely on those responses.
4. Disable filters only when the test scope is **explicitly defined as controller contracts excluding security**, with separate security tests in place.

### 13.1. CSRF with POST, PUT, PATCH, and DELETE

If the application enables CSRF protection and contracts send state-changing requests, generated tests may receive `403` due to a missing CSRF token. The solution must align with the API's **public authentication mechanism**. Never disable CSRF in production just to pass tests; conversely, do not add CSRF tokens to contracts if real consumers do not use that cookie/CSRF model.

## 14. Common Issues with `@WebMvcTest`

`@WebMvcTest` reduces startup cost by not loading every bean in the application. Some common issues include:

| Symptom | Likely cause | How to resolve |
| --- | --- | --- |
| `UnsatisfiedDependencyException` | Controller needs a service missing from the web slice | Add a mock bean or deliberately import the dependency |
| `NoSuchBeanDefinitionException` | Web configuration/custom converter/handler missing | Import configuration needed by the API contract |
| `404` despite matching URL | Controller absent from slice or different mapping | Check `@WebMvcTest` and `@RequestMapping` |
| `401`/`403` | Security filters active, test lacks auth/CSRF | Configure test security matching the API interface |
| `500` | Mock returns null or controller throws unhandled exception | Fix fixtures/mocks/exception handlers |
| Missing response JSON field | DTO serialization/naming differs from contract | Check getters/records/Jackson annotations |
| Wrong `Content-Type` | Controller produces/converters/header setup | Check advertised media types |
| Returns `404` on not-found contract with wrong body | Wrong route or exception handler | Verify path and error mapping |
| Generated test does not inherit base class | Plugin not pointing to right `baseClassForTests` | Check fully-qualified name and generated source |
| RestAssuredMockMvc not initialized | Missing `mockMvc(...)` or hook did not run | Check `@BeforeEach`, JUnit, and inheritance |

### 14.1. When a Controller Calls Multiple Dependencies

Suppose `OrderController` uses both `OrderService` and `CustomerPermissionService`. If `@WebMvcTest` only mocks one dependency, the context may fail to start or requests may take unintended branches. Declare the mocks genuinely required for the controller to handle requests, while avoiding turning the base class into an unmaintainable "simulator of the entire system."

### 14.2. Do Not Mix Up Spring MVC and WebFlux

A pure WebFlux application using `@RestController` and reactive routing may need `WebTestClient` or an appropriate HTTP test mode. `MockMvc` tests the Spring MVC Servlet stack; picking the wrong mode can prevent tests from running even when the contract DSL is completely valid.

## 15. Reading Generated Tests to Distinguish Setup Errors from Breaking Changes

Suppose CI reports:

~~~text
Expected HTTP status: 200
Actual HTTP status: 404
Request: GET /api/orders/ORD-123
~~~

Do not immediately change the DSL to `404`. Instead:

1. **Check the request:** Did the generated test call the exact method and path in the contract?
2. **Check the route:** Is `OrderController` actually loaded in the Spring MVC context?
3. **Check the fixture:** Does `OrderService.findById("ORD-123")` return an `OrderView` per the base class setup?
4. **Check filters:** Are redirects, auth, or context paths affecting the request?
5. **Check the real response:** If the real endpoint actually changed incompatibly, coordinate with the consumer before modifying the contract.

Another error example:

~~~text
Expected JSON field: $.totalAmount = 120000
Actual JSON field: $.totalAmount = "120000"
~~~

If the consumer expects a Number, this is a **JSON type mismatch**. MockMvc and RestAssuredMockMvc are doing their job properly: dispatching the request and returning the response for assertions to catch the bug. Fix the producer DTO/serializer or negotiate an API change—**never replace the matcher with a permissive regex to hide the bug**.

### 15.1. Distinguishing Three Root-Cause Categories

| Error category | Examples | Where to fix |
| --- | --- | --- |
| **Build / generation** | Tests not generated, compilation fails, missing dependencies | Plugin, dependencies, source paths, JUnit |
| **Test infrastructure / setup** | Broken context, wrong mock, missing data, wrong port/client mode | Base class, fixtures, Spring test configuration |
| **Genuine contract mismatch** | Method/path/status/JSON changed relative to commitment | Producer code or mutually agreed contract update |

**Do not edit generated Java test files directly.** They are regenerated during builds; durable fixes belong in the contract DSL, plugin configuration, base class, fixtures, or producer code.

## 16. Multiple Contract Groups: One Shared Base Class or Separate Ones?

Not every endpoint needs the same test context. For instance, one producer might have:

- `/api/orders/**` using a Spring MVC controller and mocked `OrderService`.
- `/api/payments/**` requiring a different test setup.
- Messaging contracts using triggers/destinations rather than MockMvc.

If all generated tests inherit a single oversized base class, setup may load unrelated beans and increase maintenance overhead.

Strategies:

1. **One shared base class** when all HTTP contracts genuinely share MVC configuration and test data.
2. **Base classes per package or contract directory** when different environments or controllers are needed.
3. **Separate base classes for HTTP and messaging** when tools, triggers, and verifiers differ.
4. **Extend a shared helper class** for reusable setup, without holding mutable shared state across tests.

Spring Cloud Contract supports configuring base class mappings in the plugin; option names and mapping rules depend on the Maven/Gradle plugin and version. When changing mappings, **inspect the generated `extends` clause** for each group rather than relying solely on configuration text.

## 17. Failures Caused by Shared Data Between Tests

One test can mutate the state of a mock, singleton, or database fixture, causing subsequent tests to return different results. For large contract suites:

- Design each test to be **independent with explicit input data**.
- Stub Mockito specifically for the conditions of each contract.
- Avoid depending on test execution order.
- Keep timestamps, IDs, or random data out of fixtures unless appropriate matchers are used.
- When using a database, choose an appropriate rollback/cleanup/fixture strategy.
- If RestAssuredMockMvc retains global configuration, ensure each test loads the configuration it needs before making calls.

### 17.1. Overly Broad Mocks Can Also Mask Bugs

For example:

~~~java
given(orderService.findById(anyString()))
    .willReturn(new OrderView(
        "ORD-123", "CONFIRMED", 120000L, true
    ));
~~~

This mock returns the same order for **every** ID. It may let the successful GET order test pass, while failing to verify not-found logic for other IDs. For the `ORD-404` contract, stub or prepare fixtures for the exact branch; when testing real service behavior, do not mock away the entire lookup logic.

## 18. RestAssuredMockMvc Does Not Replace Consumer Stub Runner

Once generated producer tests pass, Spring Cloud Contract can generate and package **stubs** for consumers to use via **Stub Runner**. Both workflows share the same contract source but serve different roles:

| Question | Producer + RestAssuredMockMvc | Consumer + Stub Runner |
| --- | --- | --- |
| Whose code is being tested? | Producer | Consumer |
| Does it call the real controller? | Yes, inside Spring MVC test context | No; calls a stub simulating the producer |
| Where do responses come from? | Producer's controller/serializer/handler | Mappings/templates generated from DSL |
| Who determines the request? | Generated producer test | Consumer test code |
| Mismatches detected | Producer fails to satisfy contract | Consumer sends wrong request or mishandles response |
| Is `ContractVerifierBase` needed? | Yes, if generated producer tests require it | Not like producer base; consumer has its own setup |

A green consumer test against stubs **does not prove the real producer is compatible** if producer verification was not executed. Conversely, a green producer test with MockMvc does not prove the consumer sent the right headers or handled all error branches. CI should therefore run both sides within their proper scopes.

## 19. Running Generated MockMvc Tests in CI

With Maven configured with the plugin and base class, the producer can run:

~~~bash
./mvnw -B clean verify
~~~

With Gradle configured with the Spring Cloud Contract plugin and corresponding test tasks:

~~~bash
./gradlew clean build
~~~

These are **example commands**, not proof that the pipeline actually executed Contract Verifier. CI must confirm:

1. Contract files in source directories are detected by the plugin.
2. Generated Java tests are produced and compiled.
3. Generated tests extend the right base class and use the intended `MOCKMVC` HTTP test mode.
4. The JUnit/Surefire/Gradle test runner actually executes the tests; no skips or `0 tests` reports.
5. The MockMvc context and fixtures are built reliably.
6. Important requests and assertions are verified.
7. Stubs are packaged and published only from producers that passed verification.
8. Consumer CI tests against the corresponding stub artifact/version.

### 19.1. What to Watch Out for When Upgrading Versions?

Upgrading Spring Boot, Spring Framework, or Spring Cloud Contract can affect:

- Mockito test annotation names or packages (`@MockBean` vs. `@MockitoBean`).
- JUnit versions and how runners execute generated tests.
- Generated Java source styles and assertions.
- How filters/security are handled in MockMvc.
- Plugin configuration and generated test source locations.
- RestAssuredMockMvc compatibility with related library versions.

After upgrading, **re-read generated tests and run both producer and consumer tests** before considering dependency changes safe.

## 20. Practice Lab: Building a Base Test for Catalog Service

Suppose `Catalog Service` publishes:

~~~http
GET /api/products/P-100 HTTP/1.1
Accept: application/json
~~~

Response:

~~~json
{
  "productId": "P-100",
  "name": "Wireless Mouse",
  "price": 350000,
  "available": true
}
~~~

### 20.1. Task A — Create the Contract

Write file `src/test/resources/contracts/products/get_product.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product')

    request {
        method GET()
        urlPath('/api/products/P-100')
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
            available: true
        )
    }
}
~~~

### 20.2. Task B — Create the Base Class

Assume the project has `ProductController` and `ProductService`. Create `ContractVerifierBase`:

~~~java
package com.example.catalog.contract;

import com.example.catalog.api.ProductController;
import com.example.catalog.api.ProductView;
import com.example.catalog.application.ProductService;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;

@WebMvcTest(ProductController.class)
public abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @BeforeEach
    protected void setup() {
        given(productService.findById("P-100"))
            .willReturn(new ProductView(
                "P-100", "Wireless Mouse", 350000L, true
            ));

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

This example targets Spring Framework 6.2+ with `@MockitoBean`. You need matching `ProductService.findById` and `ProductView` constructor signatures, and plugin configuration so generated tests extend `com.example.catalog.contract.ContractVerifierBase`.

### 20.3. Task C — Verify the Generated Test

After configuring Spring Cloud Contract Verifier in the practice project:

1. Generate and run the generated tests.
2. Open the generated source corresponding to `get_product`.
3. Identify the HTTP method, path, request header, and `200` assertion.
4. Identify the assertions for `productId`, `name`, `price`, and `available`.
5. Confirm the test invokes via `RestAssuredMockMvc` and receives `MockMvc` from the base class.

### 20.4. Task D — Intentionally Break the Test

Perform each change in turn:

| Change | Prediction |
| --- | --- |
| Remove `RestAssuredMockMvc.mockMvc(mockMvc)` without an alternative setup | Generated test may lack a MockMvc instance to execute |
| Remove the `ProductService` mock from `@WebMvcTest` | Context may fail to start due to missing dependency |
| Mock returns `price` as String `"350000"` instead of Number | Type mismatch can be detected if JSON contract constrains it properly |
| Change controller path to `/api/items/{id}` and drop the old path | Generated request may receive `404` |
| Change response `available` from boolean to String | JSON assertion/type check may fail |
| Add an auth filter while tests set no principal | May receive `401`/`403` depending on policy |
| Edit only `get_product.groovy` to match the new response to make the test pass | Risks hiding a breaking change from existing consumers |

### 20.5. Self-Assessment Questions

1. Why doesn't `MockMvc` need a real TCP port?
2. Why does a generated test need to extend a base class?
3. When would you choose `@WebMvcTest` over `@SpringBootTest` and vice versa?
4. If a test returns `404` because a fixture does not exist, is that a breaking change?
5. Why isn't disabling security filters with `addFilters = false` a default fix?
6. When upgrading to Spring Framework 6.2+, what should you check about mock bean annotations?
7. Is a passing producer test sufficient to conclude consumer code handles stubs properly?
8. If CI reports `BUILD SUCCESS` yet generated tests did not run, what should you inspect?

**Guidance:** MockMvc runs the MVC pipeline inside the JVM; the base class supplies context and data; choose test scope by risk; check fixtures before concluding a breaking change; preserve security tests; verify annotation compatibility across versions; producer and consumer tests complement each other; `0 tests` is not proof of contract verification.

## 21. Checklist Before Using RestAssuredMockMvc in Base Tests

- [ ] Producer genuinely uses Spring MVC or a MockMvc-compatible environment.
- [ ] Contract DSL accurately describes the requests and responses used by the consumer.
- [ ] Plugin configures MockMvc generated test mode and the corresponding base class.
- [ ] Base class inheritance and visibility allow generated tests to extend it.
- [ ] `@WebMvcTest` or `@SpringBootTest` is deliberately chosen for the test scope.
- [ ] A valid `MockMvc` is available and passed to `RestAssuredMockMvc.mockMvc(mockMvc)` in a test hook.
- [ ] Controller and critical web configurations/exception handlers are loaded.
- [ ] Service/repository dependencies are mocked or seeded with reproducible fixtures according to test scope.
- [ ] Security/validation is not inadvertently disabled to make tests pass.
- [ ] Status, headers, and JSON fields are verified against contract matchers.
- [ ] Each test is independent, without relying on mock or database state from prior tests.
- [ ] Build/setup failures are distinguished from genuine contract mismatches.
- [ ] Generated Java tests are generated, compiled, and executed in CI without being skipped.
- [ ] Stubs are published only after producer verification passes.
- [ ] Consumers continue verifying with Stub Runner using the exact artifact version.

## 22. References

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, HTTP test modes, Maven/Gradle plugins, and stubs.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): how to declare HTTP requests and responses.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): producer verification workflow, base tests, and generated tests.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): MockMvc's role in Spring MVC testing.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, and test slices.

**Key takeaway:** **RestAssuredMockMvc is the bridge between generated producer tests and the Spring MVC test context**. The base class provides `MockMvc`, prepares appropriate data/beans, and calls `RestAssuredMockMvc.mockMvc(mockMvc)` before tests execute. Distinguish **web-slice setup**, **full-context setup**, and a **real HTTP server**; inspect generated assertions instead of merely looking at a green build. When both producer verification and consumer Stub Runner run properly in CI, incompatible HTTP changes are caught much earlier.
