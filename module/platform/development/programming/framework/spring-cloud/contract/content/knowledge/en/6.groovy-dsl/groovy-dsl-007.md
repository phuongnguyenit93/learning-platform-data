# Defining Multiple Contracts in the Same Groovy DSL File

In **Spring Cloud Contract**, each contract describes one interaction that the **producer** must fulfill: an HTTP request and response, or a message send/receive scenario. The producer uses contracts to **generate tests verifying implementation behavior**; from the same specification source, the build produces **stubs** so consumers can test their calling code via **Stub Runner**. When behaviors are closely related, you can place **multiple contracts in a single Groovy DSL file** instead of creating a separate file for each scenario.

This lesson belongs to the **Groovy DSL** chapter of the SPRING_CLOUD_CONTRACT module. The focus is not writing an entire system from scratch, but understanding **how a Groovy file returns multiple `Contract` objects**, organizing and naming each scenario, avoiding ambiguous request-matching rules, and verifying that both producer tests and consumer stubs reflect **all** declared contracts.

## 1. When Should You Put Multiple Contracts in One File?

For example, **Order Service** provides the `GET /api/orders/{id}` API; **Billing Service** needs to handle at least two cases: an existing order and a non-existent order. These two expectations can be described by two contracts:

| Scenario | HTTP request | HTTP response | Consumer Behavior to Verify |
| --- | --- | --- | --- |
| Order `42` exists and is paid | `GET /api/orders/42` | `200`, `{"id":42,"status":"PAID"}` | Reads `id` and `status` properly, continues business flow. |
| Order `404` does not exist | `GET /api/orders/404` | `404`, `{"code":"ORDER_NOT_FOUND","message":"Order does not exist"}` | Recognizes business error, does not treat it as a valid order. |

Both cases belong to the **read order** behavior, so they can live together in `get_order.groovy`. This organization is helpful when:

- Scenarios share the same business topic and are typically reviewed or updated together.
- You want readers to immediately see both success and failure branches of the same API.
- The number of scenarios is moderate and each contract has a clear name, request, and outcome.

When the number of scenarios grows large, multiple consumers own distinct requirements, or each contract has an independent change lifecycle, **splitting into multiple files** is usually easier to maintain. Spring Cloud Contract supports both approaches; choose based on readability, reviewability, and version management rather than feeling forced to cram all contracts into one place.

## 2. Core Syntax: Returning a List of `Contract`s

For an individual Groovy contract, the file typically looks like this:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method 'GET'
        url '/health'
    }
    response {
        status 200
    }
}
```

To define **multiple contracts in one file**, place **the `Contract.make { ... }` calls inside a Groovy list** and make that list the **script's return value**:

```groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'firstScenario'
        request {
            method 'GET'
            url '/first'
        }
        response {
            status 200
        }
    },
    Contract.make {
        name 'secondScenario'
        request {
            method 'GET'
            url '/second'
        }
        response {
            status 404
        }
    }
]
```

Note four points:

1. The outer `[ ... ]` pair is a **Groovy list**, not the body of a `Contract.make`.
2. **Each element** is an independent `Contract.make` call with its own `request` and `response`.
3. Elements are separated by commas `,`; the closing `]` ends the list.
4. The entire list is the **final expression** of the script, so the contract loader receives the collection of `Contract` objects.

Semantically, the file returns a **`List<Contract>`**. Do not write two loose `Contract.make` calls assuming the tool will collect them automatically: in a Groovy script, only the **last expression** is returned. Also do not place another statement returning a different value, such as `println`, after the list.

The `name` property lets you give scenarios meaningful names and helps identify generated test results. **Names should be unique, stable, and descriptive within the contract set**; exact generated class/method naming may depend on plugin configuration and Spring Cloud Contract version.

## 3. Complete Example: Two Order-Reading Cases in One File

Suppose the producer stores the contract at:

```text
order-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── orders/
                    └── get_order.groovy
```

Full contents of `src/test/resources/contracts/orders/get_order.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldGetPaidOrder'
        description 'Read an existing order in PAID status'

        request {
            method 'GET'
            url '/api/orders/42'
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body(
                id: 42,
                status: 'PAID'
            )
        }
    },

    Contract.make {
        name 'shouldReturnNotFoundForMissingOrder'
        description 'Reading a non-existent order returns a business error'

        request {
            method 'GET'
            url '/api/orders/404'
        }

        response {
            status 404
            headers {
                contentType(applicationJson())
            }
            body(
                code: 'ORDER_NOT_FOUND',
                message: 'Order does not exist'
            )
        }
    }
]
```

Here **two contracts share one file without sharing content**: the first requires HTTP `200`, an `Order` object, and `PAID`; the second requires HTTP `404` and an error payload. The two paths contain different IDs, allowing stubs to match requests unambiguously.

Setting distinct `name` and `description` values per scenario helps reviewers pinpoint the cause when a producer test fails. `description` states business intent; `name` is a short identifier and should use characters valid for generated test names. Do not reuse the same name for both, as that makes scenarios hard to tell apart in build reports.

### 3.1. Adding a Third Contract

Add **another `Contract.make` element** to the same list, separated by a comma. For example:

```groovy
// Add as a new element inside the existing list.
Contract.make {
    name 'shouldGetPendingOrder'
    request {
        method 'GET'
        url '/api/orders/43'
    }
    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(id: 43, status: 'PENDING')
    }
}
```

This snippet is only **the element to insert**, not the full Groovy file contents. Update the producer to return the right data for `43`, then re-run the generated tests. If you add the contract before implementing the corresponding behavior, the new producer test **must fail**; that is the expected feedback of contract testing.

## 4. Each Contract Must Be an Independent Scenario

Within a single `Contract.make`, you typically describe **one concrete request -> response relationship**. Do not combine two status codes or two incompatible responses into one `response` hoping Spring Cloud Contract will pick the right one dynamically.

Comparison:

| Organization | Meaning | Consequence |
| --- | --- | --- |
| **One file containing a list of two contracts** | Two separate scenarios that are close in business domain. | Generates the corresponding producer checks and stub mappings. |
| **Two files, one contract each** | Two scenarios managed independently. | Still generates the corresponding tests and stubs when the plugin reads both files. |
| **One contract listing two outcomes with no distinguishing condition** | Ambiguous or contradictory expectations. | Hard to verify and causes stubs to mismatch. |

An important rule: **keep requests distinguishable**. If two contracts match the exact same `method`, `url`, headers, query parameters, and body while describing two different responses, the stub server lacks enough information to know which scenario to choose. With WireMock, mapping selection also depends on priority/matching rules; tests may behave unexpectedly.

For example, if you need to distinguish two behaviors via query parameters, express that difference in each contract's **request matcher**. If behavior differs due to producer-side data state while the HTTP request is identical, design fixtures, data identifiers, or simulation mechanisms clearly so each contract produces a request distinguishable when running stubs. Do not carelessly add overlapping contracts and rely on list order to determine the response.

## 5. How Will the Producer Test Both Contracts?

With Spring Cloud Contract Verifier integrated into the producer build, the plugin reads the Groovy file and **generates tests from each contract**. The plugin does not run the `.groovy` file directly as a JUnit test; it translates contract definitions into test classes using project configuration (e.g., MockMvc), and Maven/Gradle executes those tests.

For both contracts above to be verified by the producer, the implementation must handle both cases. An illustrative Spring MVC controller:

```java
package com.acme.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> getOrder(@PathVariable long id) {
        if (id == 42L) {
            return ResponseEntity.ok(new OrderResponse(42L, "PAID"));
        }
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse(
                        "ORDER_NOT_FOUND", "Order does not exist"));
    }

    public record OrderResponse(long id, String status) {}
    public record ErrorResponse(String code, String message) {}
}
```

This implementation is **solely for demonstrating the contract**, where `42` always exists and `404` does not. A real application should use services/repositories and proper test fixtures rather than hardcoding business IDs as shown here.

Suppose the project already has a base class configuring MockMvc for generated tests:

```java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {
    @Autowired MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Example Maven plugin snippet in the producer's `pom.xml`:

```xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
```

This is a **POM snippet**, not a complete POM. The producer also needs the Spring MVC starter, test dependencies, Spring Cloud Contract Verifier, and compatible Spring Boot/Spring Cloud Contract versions. The `${spring-cloud-contract.version}` property must be defined in the POM or managed via plugin management.

From the producer project directory, run:

```shell
mvn clean verify
```

Check three outcomes:

1. The plugin read `get_order.groovy` and generated test code corresponding to **both contract names**.
2. The test report shows that **both scenarios ran and passed**; do not rely solely on `BUILD SUCCESS`.
3. If you change the producer code to return `200` for ID `404`, the test associated with `shouldReturnNotFoundForMissingOrder` fails, while the `42` test may still pass.

Even though both contracts reside in the same file, they **do not collapse into a single combined assertion**: you should see clearly which test passed and which failed. Exact generated Java filenames, class names, and method names may vary by plugin version or naming configuration; verify against **actual build output**.

## 6. Stubs Generated from a Contract List and Consumer Usage

From **the same file** `get_order.groovy`, HTTP stub generation can produce **two mappings**: one returning `200` when the consumer calls `/api/orders/42`, and the other returning `404` with the error body when calling `/api/orders/404`.

Both mappings are packaged into the stub artifact alongside the producer's version, typically with the `stubs` classifier. For example:

```text
com.acme:order-service:1.0.0:stubs
order-service-1.0.0-stubs.jar
```

With the build plugin properly configured, the command:

```shell
mvn clean install
```

runs producer tests, generates/packages the stub, and installs the artifact into the local Maven repository. If producer tests fail, that artifact should not be published as a reliable stub. In CI, place the **publish step after the passing producer test gate**.

In the Billing project, suppose a real `OrderClient` exists with the method:

```java
OrderView getOrder(long id);
```

where `OrderView` is a DTO with `id` and `status`, and the client reads `orders.base-url` from configuration. The consumer test can point this URL to the stub:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.HttpClientErrorException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired OrderClient orderClient;

    @Test
    void shouldReadPaidOrder() {
        OrderView order = orderClient.getOrder(42L);
        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
    }

    @Test
    void shouldReportMissingOrder() {
        assertThatThrownBy(() -> orderClient.getOrder(404L))
            .isInstanceOf(HttpClientErrorException.NotFound.class)
            .hasMessageContaining("404");
    }
}
```

This is a **test snippet illustration**: the consumer project must define `OrderClient`, `OrderView`, the Stub Runner dependency, and a client using `RestClient.retrieve()` or equivalent error-throwing behavior on HTTP 404. If `OrderClient` translates 404 into a domain exception like `OrderNotFoundException`, assert that exception instead of `HttpClientErrorException.NotFound`. The two test methods consume **the two scenarios generated from the single file**.

**Do not treat just any HTTP 404 from the stub as proof that the error scenario matched.** WireMock also returns `404` when a request **matches no mapping at all**. A consumer test asserting only `404` can pass falsely. For error scenarios, also check the `ORDER_NOT_FOUND` error code, message, or headers specified in the **response contract**, or verify via stub inspection that the intended mapping matched.

To consume artifacts **published to a Maven repository**, replace `LOCAL` with `REMOTE` and configure `repositoryRoot` pointing to the real repository with secure CI credentials. Never edit stub mappings manually on the consumer side just to make tests green; every behavior change should originate from the contract and be verified by the producer first.

## 7. Contract Names, Paths, and Organizational Boundaries

A file containing multiple contracts should still be easy to locate and review. For example:

```text
src/test/resources/contracts/
└── orders/
    ├── get_order.groovy         # 200 and 404 for read operations
    ├── create_order.groovy      # Order creation scenarios
    └── cancel_order.groovy      # Order cancellation scenarios
```

This is **one suggested layout**, not the only structure Spring Cloud Contract permits. Grouping related contracts in one file helps review by operation; separate files help isolate less-related behavior groups. If a file grows long enough that finding individual scenarios becomes tedious, split it in a controlled change and verify **no contracts were lost** when the plugin generates tests and stubs.

Rules to follow:

- **Unique, meaningful contract names**: prefer `shouldGetPaidOrder`, `shouldReturnNotFoundForMissingOrder` over names like `case1` or `test2`.
- **Every request has clear distinguishing criteria**: method, URL, query parameters, headers, or body should reflect the scenario's meaningful difference.
- **Keep test data stable**: if a producer test needs order `42`, fixtures must prepare the exact `PAID` state.
- **Each contract represents an expectation valuable to consumers**; do not create sprawling lists just to cover low-value data permutations.
- **Review modifying and deleting contracts** like an API interface change; check whether older consumers still depend on prior behavior.

**Sharing a file does not mean independent versioning:** when publishing a stub artifact, all contracts belonging to that build/version are distributed together. If one consumer requires keeping the old response, rewriting every contract in the list to a new shape may let producer tests and newer consumers pass while still breaking older consumers.

## 8. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Resolve |
| --- | --- | --- |
| Tests generated for only one contract despite writing two `Contract.make` blocks. | Calls stand loosely, script does not return a list, or final expression is not the contract list. | Wrap contracts in `[ ... ]` and ensure the list is the file's last expression. |
| Groovy reports a syntax error while loading contracts. | Missing comma between elements, missing `}` or `]`, quote mismatch. | Check braces, brackets, and commas around each `Contract.make`. |
| Both contracts generate stubs, yet requests hit the wrong response. | Overlapping mappings: same method/path without distinguishing conditions. | Clarify request matchers or redesign scenarios; do not rely on list order. |
| Producer test passes one scenario but fails another. | Producer implements only one of the behaviors, or fixture lacks data. | Check report by scenario name and fix implementation or fixture accordingly. |
| Consumer receives `404` when expecting `200`. | Client calls wrong path, misses header/query, or stub artifact lacks mapping. | Compare real request with artifact mapping; check version and classifier. |
| Consumer `404` error test still passes when sending the wrong path. | Assertion checks only status without distinguishing unmatched 404 from business 404. | Also assert `code: ORDER_NOT_FOUND` from the contract or verify mapping match. |
| Consumer CI cannot find the new stub. | Producer did not publish artifact, CI uses stale version, or wrong repository. | Verify `stubs` artifact is published, repository is readable, and version is pinned. |
| Refactoring to split files drops tests. | Scenarios omitted or given duplicate names while converting list to separate files. | Compare contract names and generated scenario counts before/after; re-run producer and consumer tests. |

When diagnosing, ask in order: **How many contracts did the Groovy script return?** -> **How many producer tests did the plugin generate and execute?** -> **Which mappings are inside the stub artifact?** -> **Which mapping did the consumer hit and what assertions did it run?**. Tracing from the specification source to both test endpoints finds the real root cause instead of patching a stub to mask failures.

## 9. Practice: Expanding a File to Three Contracts

Carry out this exercise in a sample producer/consumer project already configured with Spring Cloud Contract:

1. Create `contracts/orders/get_order.groovy` containing the **two contracts** `shouldGetPaidOrder` and `shouldReturnNotFoundForMissingOrder` as in Section 3.
2. Implement the producer endpoint responding properly to both scenarios; run the build and inspect the **test report** to confirm both tests are generated and executed.
3. Install or publish the `stubs` artifact, run the consumer with Stub Runner, and verify both **200** and **404 with the contract-defined error payload**.
4. Add a third element `shouldGetPendingOrder` for `GET /api/orders/43` returning `200` and `status: PENDING`. Before updating the producer, run producer tests and observe the new scenario fail.
5. Update the producer and fixture for order `43`; re-run producer tests so all three scenarios pass. Regenerate the stub artifact and add a consumer test for `PENDING`.
6. Temporarily change `GET /api/orders/43` in the new contract to collide with `/api/orders/42` while keeping the `PENDING` response; analyze why two mappings for the same request can yield non-deterministic stub responses. Revert the change before finishing.

Results to prove via build output: **one Groovy file returns three contract objects, three scenarios are verified on the producer, and three scenarios are tested by the consumer via corresponding stubs**. The number of generated Java classes may depend on the plugin, so evaluate by **individual executed scenarios** rather than forcing test class count to equal contract count.

## 10. Self-Check Questions

- Why is placing two loose `Contract.make` calls not a reliable way to return multiple contracts from a Groovy script?
- Where must two contracts in the same file differ if they share the same URL yet expect different responses?
- How do `name` and `description` help when one of the generated producer tests fails?
- A new contract for `PENDING` status has been added, but the producer does not support it yet. Which test should fail before publishing stubs?
- When the consumer receives HTTP 404 from WireMock, how do you distinguish the business error described in the contract from a request that matched no mapping?
- If both the producer and the new consumer pass tests after deleting an old contract, what risk remains for consumers running older versions?

**Key takeaway:** In Spring Cloud Contract Groovy DSL, **multiple contracts in one file = a script returning a list of independent `Contract.make { ... }` definitions**. Each contract needs a clear name, unambiguous request matching, and verifiable producer behavior. Once the producer build verifies all scenarios prior to publishing stubs, consumers can use **Stub Runner** to test their calling code against the exact committed set of behaviors.
