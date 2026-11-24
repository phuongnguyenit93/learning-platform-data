# Distinguishing Functional, Contract, Security, and Performance Testing in Spring Boot

## 1. Four Test Types Answer Four Different Questions

When a Spring Boot API returns HTTP 200, that alone is not enough to conclude the system works properly. The API might return the wrong amount, change its JSON structure and break another application, expose data to an unauthorized user, or respond too slowly under load. Four testing approaches address these four corresponding risks:

- **Functional testing:** Does the system execute business rules and produce expected outcomes for specific inputs and states?
- **Contract testing:** Do communicating parties adhere to the agreed interface, such as HTTP methods, paths, data fields, data types, status codes, and error handling?
- **Security testing:** Does the system enforce authentication, authorization, data protection, and resistance against unauthorized access or malicious inputs?
- **Performance testing:** Under a defined workload, dataset, and environment, does the system meet response-time, throughput, error-rate, and resource-utilization targets?

They complement one another; the same endpoint may require all four. Classify tests by **the risk and claim being verified**, not merely by tool name or test level.

| Dimension | Functional | Contract | Security | Performance |
|---|---|---|---|---|
| Core question | Is the business outcome right? | Do caller and provider agree on the interface? | Who may do what, and is data protected? | How does the system respond under load? |
| What is verified | Rules, branches, state, data | Request/response, schemas, status codes, compatibility | Authentication, authorization, sensitive data, vulnerabilities, configuration | Latency, throughput, errors, CPU, memory, connection pools |
| Example defect | Total amount miscalculated | Field `amountVnd` renamed to `amount` | A user can view another user's orders | p95 rises from 200 ms to 3 s as user count grows |
| Common Java/Spring tools | JUnit 5, AssertJ, MockMvc, Testcontainers | OpenAPI validation/diff, Pact, Spring Cloud Contract | Spring Security Test, OWASP ZAP, SAST/SCA, authorized penetration testing | k6, Gatling, JMeter, Micrometer/Prometheus |
| Evaluation criteria | Business assertions pass | Published contract verified for consumers | No unauthorized access paths; security controls work | Meets SLOs under the defined load scenario |

**Running example:** GET /api/orders/42 must return JSON containing id, status, and amountVnd for a user with role VIEWER. Order 42 is paid, and its amount is 120000 VND. A functional test checks the values; a contract test verifies the message shape; a security test verifies unauthorized users are rejected; a performance test measures response behavior under concurrent requests. Checking only HTTP 200 proves none of the other three.

## 2. Functional Testing: Correct Business Behavior

**Goal:** Verify actual behavior against requirements: valid inputs, boundaries, invalid inputs, missing-data states, error paths, and state-transition rules.

For GET /api/orders/{id}, cases to consider include:
1. Existing ID: HTTP 200, matching id, and status and amountVnd matching the source data.
2. Non-existent ID: HTTP 404; does not mistakenly return another order.
3. Invalid parameter: the application rejects it per the input contract rather than throwing an unhandled 500 error.
4. Business state change: returned values reflect the updated state after a mutation operation, if supported by the API.

**Test level is not synonymous with test type.** Unit tests verify isolated functions or services, web slice tests verify controllers and HTTP mappings, integration tests verify connections to real or Testcontainers-managed databases/queues/infrastructure, and end-to-end tests traverse a business flow. All four levels can perform functional testing. Pick the lowest level that still proves the risk; add integration tests for behavior relying on transactions, serialization, mappings, configuration, or real queries.

Confidence comes from meaningful assertions. Asserting only “no exception thrown” or “HTTP 200” often misses calculation bugs. For an API returning an order, verify the exact key business fields, boundary inputs, and expected errors.

## 3. Contract Testing: Correct Interfaces Between Components

A **contract** is the agreement that a provider and consumer rely on to exchange data. It can include:
- Paths, HTTP methods, required query/path/header parameters, and body formats.
- HTTP status codes, Content-Type, JSON schemas: field names, types, required/optional status, and value constraints.
- Error structures, pagination format, date/time formats, and version compatibility rules.
- For messages/events: topic names, schemas, keys, required fields, and event interpretation semantics.

Example OpenAPI excerpt describing response shape; this is a **contract specification**, not an automated test by itself:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                type: object
                required: [id, status, amountVnd]
                properties:
                  id: { type: integer, format: int64 }
                  status: { type: string }
                  amountVnd: { type: integer, format: int64 }
        '404':
          description: Order not found
~~~

Two common strategies:

**Schema/API contract:** The provider publishes an OpenAPI spec or schema; CI compares the specification against running endpoints, validates requests/responses, and detects breaking changes. A JSONPath assertion checking that a field exists is only a basic shape check; it is **not automatically a full OpenAPI verification**.

**Consumer-driven contract (CDC):** Consumers describe the exact interactions they actually depend on, such as “call GET with a valid ID, receive HTTP 200 and fields id/status/amountVnd with the right types.” Contracts are shared; the provider runs verification against existing consumer contracts (e.g., via Pact or Spring Cloud Contract). This catches changes that would break active consumers early without spinning up the entire end-to-end system on every run.

**Changes to evaluate carefully:** Removing or renaming a required field, changing a number to a string, changing status codes, or turning an optional request parameter into a required one are typically breaking changes. Adding an optional response field is usually compatible with consumers that ignore unknown fields, though you should not assume every consumer does. Adding an enum value can also break consumer code handling a fixed list. Contract testing detects interface incompatibility; it does not prove that the amount is calculated accurately per business rules.

## 4. Security Testing: Correct Permissions and Attack Controls

Distinguish three layers:
- **Authentication:** Who is the caller, and has their identity been verified? For an API accepting only Basic/Bearer auth, unauthenticated requests typically receive 401.
- **Authorization:** Is that identity permitted to perform the action on the **specific resource**? Authenticated callers lacking permission typically receive 403.
- **Data protection and attack surface:** Input/output sanitization, information leaks in errors, IDOR/BOLA, SQL injection, XSS, CSRF where applicable to the auth model, CORS configuration, secrets, TLS, and dependency vulnerabilities.

For example, the VIEWER role allows access to certain orders within a granted scope. A test checking only the VIEWER role is **insufficient** in a multi-tenant application: a VIEWER in tenant A must not view tenant B's orders. That is an object-level authorization flaw, even if the request passes authentication and returns HTTP 200.

Combine multiple techniques: security tests with Spring Security Test (401/403, access rules, CSRF on write methods when using cookies/sessions), integration tests through the real filter chain and token/session mechanisms, SAST/SCA in pipelines, scoped DAST with authorization, configuration audits, and dedicated penetration testing when needed. **@WithMockUser simulates a user in SecurityContext**: it is great for checking authorization rules, but does not verify JWT issuance, signatures, expiration, revocation, or the real login flow.

Never conclude an API is secure from a single 401/403 test. Security spans multiple layers and depends on your threat model and deployment context.

## 5. Performance Testing: Service Levels Under Defined Conditions

A request responding in 100 ms on a developer laptop says nothing about performance when hundreds of users access it concurrently. A performance test must define the **workload** (rate, virtual user count, ramp-up phase, endpoint mix, dataset size, read/write ratio), **environment** (CPU, RAM, database, cache, network), **thresholds**, and **observability**.

Key metrics:
- **Latency:** p50 describes the median, while p95/p99 reflect the slow tail; averages can hide very slow requests.
- **Throughput:** actual requests/second or transactions/second, not synonymous with virtual user (VU) count.
- **Error rate:** 5xx, timeouts, defined business errors, connection failures; separate script/auth errors from backend failures.
- **Saturation:** CPU, heap/GC, threads, database connection pools, queue lag, I/O; locate bottlenecks as load increases.

Test types:
- **Load test:** Measure at expected production workload.
- **Stress test:** Push beyond expected load to find limits and observe degradation/recovery.
- **Spike test:** Sudden surge or drop in traffic.
- **Soak/endurance test:** Sustained load over time to detect resource leaks or latency creep.

Example thresholds: under the described workload, p95 below 300 ms and failure rate below 1%. These are **illustrative criteria only**; real SLOs must come from product targets and measured baselines. Measure after appropriate warm-up, keep data and infrastructure consistent enough for comparison, repeat runs when needed, and correlate metrics/tracing to find root causes. Benchmarks on a single local machine do not represent production.

## 6. Spring Boot 3.3.x / Java 17+ Example: Three Perspectives on One API

This small example can be run with Maven and Java 17+. Order data is hardcoded to illustrate assertions; in a real system, replace it with services/repositories and use integration tests for data access. Create this structure:

~~~text
pom.xml
src/main/java/demo/testing/TestingApplication.java
src/test/java/demo/testing/OrderApiTest.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>testing-example</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController {
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> getOrder(@PathVariable long id) {
        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }
        Map<String, Object> order = new LinkedHashMap<>();
        order.put("id", 42L);
        order.put("status", "PAID");
        order.put("amountVnd", 120_000L);
        return ResponseEntity.ok(order);
    }
}

@Configuration
class ApiSecurity {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**").hasRole("VIEWER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This configuration uses Spring Security 6, allowing only role VIEWER to access /api/orders/** and enabling HTTP Basic so unauthenticated requests receive a 401 challenge. The example code has no multi-tenant logic or database; therefore it does not prove object-level security or real order calculation correctness. CSRF remains at Spring Security's default; the GET endpoint is a read operation.

**src/test/java/demo/testing/OrderApiTest.java**

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "VIEWER")
    void functional_returnsCorrectBusinessValues() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("PAID"))
            .andExpect(jsonPath("$.amountVnd").value(120000));
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void functional_unknownIdReturns404() throws Exception {
        mvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void contract_responseHasExpectedShape() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").isNumber())
            .andExpect(jsonPath("$.status").isString())
            .andExpect(jsonPath("$.amountVnd").isNumber());
    }

    @Test
    void security_missingAuthenticationReturns401() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "GUEST")
    void security_wrongRoleReturns403() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run in the directory containing pom.xml:

~~~bash
mvn test
~~~

**How to read the results:** The two functional tests check values and the 404 branch. The contract_responseHasExpectedShape test only checks the provider's response structure at a basic level; to call it full contract testing, verify the endpoint against OpenAPI/schemas or consumer Pact/contracts in CI. The two security tests confirm the 401/403 flows through the filter chain with MockMvc, though @WithMockUser does not test real HTTP Basic credentials. None of these tests measure performance.

To strengthen this suite, add tests with real order data in a dedicated database (e.g., Testcontainers), test endpoints with real test credentials/tokens, test for IDOR if order ownership applies, and add OpenAPI or CDC verification steps. Avoid using production customer data or secrets in test fixtures.

## 7. Load Measurement Example with k6

This script is **independent of Maven/JUnit** and runs using an installed k6 binary. It measures GET /api/orders/42 at 20 virtual users for 30 seconds; it does not prove a fixed throughput because VUs and requests/second are different metrics.

**perf-orders.js**

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
    vus: 20,
    duration: '30s',
    thresholds: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<300'],
    },
};

export default function () {
    const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';
    const headers = __ENV.AUTH_HEADER
        ? { Authorization: __ENV.AUTH_HEADER }
        : {};
    const response = http.get(baseUrl + '/api/orders/42', { headers });
    check(response, { 'HTTP 200': r => r.status === 200 });
}
~~~

~~~bash
k6 run perf-orders.js
~~~

**Prerequisites:** The application must be running, BASE_URL must point to the right test environment, and AUTH_HEADER must be set to valid test credentials with the VIEWER role (for the example config, a Basic auth header). Never store passwords/tokens in script files or logs. If credentials are missing, requests will receive 401 and the benchmark will fail due to test setup; do not conclude the server has a performance bug from that result.

The p95 under 300 ms and failed request rate under 1% thresholds are illustrative only. Real systems require a load model matching production usage (read/write ratio, dataset size, caching, warm-up, duration, arrival rate), a representative environment, clear SLOs, and CPU/DB/GC analysis alongside k6 results. This script does not cover stress/spike/soak testing; each goal needs its own scenario.

## 8. Choosing Tests and Quality Gates in CI/CD

| Stage | Priority Tests | Gate Criteria (Example) |
|---|---|---|
| When changing business logic, every pull request | Unit/web/integration functional | Key rules and error branches have assertions; all tests pass |
| When APIs/events change, every pull request | OpenAPI/schema diff and provider/consumer contract verification | Existing consumers not broken; breaking changes handled via deliberate versioning/migration |
| Every pull request and periodically | Security unit/integration, dependency scan, secret scan; DAST in appropriate environment | No unauthorized access paths or unresolved critical findings per policy |
| Before release and on load/infra changes | Load tests with representative data and environment | Meets p95/p99, error rate, throughput, and saturation per documented SLOs |
| Scheduled and during incident investigation | Soak, stress, spike, deep security | Understand limits, recovery behavior, resource leaks, and emerging risks |

Separate fast, deterministic tests from time-consuming tests. Never run long load tests on a shared environment impacted by other pipelines and treat the results as a baseline. Contract verification can run very fast on PRs; DAST and performance tests usually need dedicated environments. Avoid tests that rely on randomly changing data, real-time clocks, or uncontrolled external services.

## 9. Common Misconceptions

1. **“It returned HTTP 200, so it is right.”** 200 is only an HTTP signal; the body may be functionally wrong, break the contract, or respond too slowly.
2. **“Functional tests and contract tests are the same thing.”** A response can match the schema while returning the wrong amountVnd; conversely, functionally correct data can still rename a field and break old clients.
3. **“Unit tests are functional; integration tests are contract.”** Unit/integration/end-to-end describe execution scope, whereas functional/contract/security/performance describe what is being verified.
4. **“Having @WithMockUser means comprehensive security.”** It helps verify authorization rules; you still need real authentication tests, object-level authorization, configuration checks, and other defense layers.
5. **“20 VUs means 20 requests/second.”** VUs simulate users looping through transactions; request rate depends on response time and think time. To control arrival rate, use an arrival-rate executor model.
6. **“A good p95 means every request is fast.”** 5% of requests are still slower than the p95 threshold; inspect p99, timeouts, errors, and user impact.
7. **“Local machine benchmarks represent production.”** Real systems differ in network, connection pools, data volume, dependencies, autoscaling, and concurrent traffic; define measurement conditions explicitly.
8. **“Contract tests completely replace end-to-end tests.”** Contracts reduce interface-drift risk; they do not guarantee multi-service workflows, data, or operational configuration integrate properly.

## 10. How to Choose Test Types from a Requirement

For the requirement “View Order API”:
- If the goal is that a paid order must return **amountVnd = 120000** → write **functional tests** for data and business logic.
- If the goal is that the mobile app still receives **id/status/amountVnd matching the schema and status** → write **contract tests**, ideally verifying the contract the consumer actually uses.
- If the goal is that only authorized users within the right ownership scope can view orders → write **security tests** for 401, 403, and cross-tenant/owner access.
- If the goal is keeping p95 under the agreed threshold under realistic traffic → write **performance tests** with a defined workload, environment, and metrics.

**Guiding principle:** Start from the risk you need to prove, write matching assertions or metrics, pick just enough test level and tooling, and combine test types to close the gaps that any single type leaves uncovered.