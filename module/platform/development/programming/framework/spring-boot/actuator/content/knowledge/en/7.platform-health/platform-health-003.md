# Roles of HealthContributor, HealthIndicator, and CompositeHealthContributor

## 1. The core model: a tree of branches and leaves

An application may need to check caches, multiple database connections, payment systems, or multiple queues. If it only returns a single general status, operators have trouble knowing which component has an issue. If each check defines its own separate endpoint, organizing and aggregating results easily becomes fragmented.

Spring Boot Actuator organizes health information sources into a **tree**:

- **Leaf nodes** perform an evaluation and produce a health result.
- **Branch nodes** contain named child information sources, which may include other branches.
- The health endpoint infrastructure traverses the tree, obtains the results, and aggregates the status according to policy.

The three types in this topic serve that exact model:

| Type | Role | Question it answers |
| --- | --- | --- |
| `HealthContributor` | Common contract to identify a component participating in the health tree | Does this object participate in providing health information? |
| `HealthIndicator` | Leaf node providing a check result | What is the result of this evaluation? |
| `CompositeHealthContributor` | Branch node organizing named contributors | Which child components belong to this branch? |

This lesson uses Java 21 and Spring Boot 3.3.13. The types examined belong to the synchronous check contract in the `org.springframework.boot.actuate.health` package.

## 2. HealthContributor: the common type, not a check

`HealthContributor` is a marker interface. Abbreviated view of the type relationship:

```java
public interface HealthContributor {
}
```

It does not declare a `health()` method. Therefore, a variable whose static type is HealthContributor cannot have `health()` called on it based solely on this contract.

For Boot 3.3's health model, a contributor must provide one of two meaningful contracts: HealthIndicator or CompositeHealthContributor. Merely creating an empty class implementing HealthContributor provides no way for the endpoint to obtain a result or traverse child components.

Why is this common type needed? A branch needs to hold both leaf nodes and child branches in the same collection. `Map<String, HealthContributor>` expresses that without forcing every component into the same leaf type.

Basic relationship:

```text
HealthContributor
    ^
    |
    +-- HealthIndicator
    |       Leaf node: health() produces a Health
    |
    +-- CompositeHealthContributor
            Branch node: access and iterate child contributors
```

This is a type relationship, not an execution order. HealthContributor does not sit at a "step before" HealthIndicator in a pipeline.

See the definition of [HealthContributor 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributor.html).

## 3. HealthIndicator: where a health condition is actually evaluated

HealthIndicator extends HealthContributor and has the primary method `Health health()`. This interface is a functional interface, so it can be implemented with a lambda.

The short example below is a declaration using Health and HealthIndicator imports, not a standalone program:

```java
HealthIndicator localCheck = () ->
        Health.up().withDetail("probe", "local-demo").build();
```

When calling `localCheck.health()`, the result is a Health object containing a status and optionally detail data. For a real check, the logic might query a connection client, read resource pool state, or perform a lightweight check operation.

A HealthIndicator should represent an operationally meaningful evaluation. It may require multiple internal operations; there is no rule that "every call must become a separate HealthIndicator". If multiple distinct sub-components need to be displayed on the tree, that is a reason to consider a composite.

### 3.1. HealthIndicator is the source; Health is the result

The two objects have different responsibilities:

- HealthIndicator holds the logic to produce health information.
- Health is the result of a single evaluation.

Creating a Health and holding onto it forever does not automatically make the result change when the dependent system changes state. In the full example, the indicator reads the simulated state **inside the lambda**, each time it is called, rather than precomputing Health at bean initialization.

### 3.2. getHealth(boolean) and detail visibility

HealthIndicator also has the default method `getHealth(boolean includeDetails)`. This parameter indicates whether to include details in the result.

With the default implementation, calling `getHealth(false)` still executes `health()`, then strips details from the result. It does not mean "skip the check", nor is it automatically a result cache.

The test suite in this lesson uses a counter to verify this behavior: details are stripped, yet the execution count still increases.

### 3.3. When a check may throw an exception

HealthIndicator does not automatically turn arbitrary code into a fault-tolerant check. If you implement it with a lambda and let exceptions escape, do not assume you will always get the desired Health DOWN.

`AbstractHealthIndicator` is a base class that helps build Health and handles Exceptions from `doHealthCheck` as status DOWN. This is an option when the convention "check exception means DOWN" fits the design. You must control exception data placed into details and timeouts on real clients.

See [HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html) and [AbstractHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.html).

## 4. CompositeHealthContributor: structure holding child information sources

CompositeHealthContributor is also a HealthContributor, but its focus is **named child contributors**, not a method returning a Health of its own.

It supports:

- Retrieving a direct child via `getContributor(name)`.
- Iterating named elements via `iterator()` or `stream()`.
- Creating a composite from a map with `CompositeHealthContributor.fromMap(...)`.

For example, the same payments branch can contain a banks branch and a queue check:

```text
payments                    CompositeHealthContributor
├── banks                   CompositeHealthContributor
│   ├── bankA               HealthIndicator
│   └── bankB               HealthIndicator
└── queue                   HealthIndicator
```

The map of payments holds both a composite and an indicator. The HealthContributor type allows describing those two kinds of child objects in the same structure.

### 4.1. Creating a composite does not mean running checks

`fromMap` creates an object organizing contributors. Creating a composite or retrieving a child object does not automatically invoke `health()` on leaf nodes.

The endpoint infrastructure only uses this structure to gather information when evaluation is needed. Execution frequency also depends on how it is called and system configuration; "being a composite" itself does not schedule background checks or cache results.

### 4.2. Child names are keys of that exact branch

`getContributor("banks")` on payments retrieves the banks branch. To get bankB in Java code, retrieve banks first, then call `banks.getContributor("bankB")`.

Do not naively call `payments.getContributor("banks/bankB")`: this method looks up a direct child name, not a path parser. The HTTP endpoint can process multi-segment paths to traverse the tree; that is a different responsibility from a single key lookup.

Two different branches can use the same child name if names are understood within each branch's scope. However, names in the same map should be distinct, stable, and free of secret data.

### 4.3. Composite does not define aggregation policy on its own

A composite containing bankA and bankB does not automatically assert that just one working bank makes the whole branch UP. Using the default aggregation policy, one DOWN node in the example makes the branch and root DOWN.

If the business requires a rule like "at least one payment route available", you must explicitly design an evaluation or appropriate aggregation policy. Do not infer such fallback rules merely from putting two indicators into the same composite.

See [CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html) and [NamedContributors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/NamedContributors.html).

## 5. Distinguishing the source tree from the result tree

Similar names can easily cause confusion:

| Source/logic | Computed result | Distinction to make |
| --- | --- | --- |
| HealthIndicator | Health | An evaluation is different from the data it produces |
| CompositeHealthContributor | CompositeHealth | Child source structure is different from child result structure |
| HealthContributor | HealthComponent is the common result-side type | Two type hierarchies serve two different sides |

CompositeHealth has a status and a collection of child HealthComponents. It is not a CompositeHealthContributor for continuing to run checks.

Overall flow:

```text
HealthContributor Beans
        |
HealthContributorRegistry
        |
HealthEndpoint infrastructure traverses branches and calls leaf indicators
        |
Health at leaves; CompositeHealth/HealthComponent on the result side
        |
StatusAggregator chooses the aggregated status
        |
Visibility policy + mapping status to HTTP
```

The diagram describes responsibilities, not a guarantee of a specific invocation order for leaf nodes. Do not build logic relying on bankA always being called before bankB.

In Boot 3.3, status aggregation uses StatusAggregator. With UP and DOWN in this lesson, DOWN governs parent branch statuses. HTTP codes are decided via a separate mapping mechanism; by default DOWN maps to 503. HealthIndicator does not directly return an HTTP ResponseEntity object.

See [CompositeHealth](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealth.html) and [Boot 3.3 Health Information](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

## 6. Registry connects beans to the root of the tree

HealthContributorRegistry holds named contributors at the root level. Boot normally discovers contributor beans and creates the appropriate registry.

This does not mean every child object you create inside a Java method becomes a Spring bean or automatically appears at the root. If bankB is only inside the banks map, the path to it goes through payments → banks → bankB.

For a HealthIndicator registered by Boot from a bean, the identifier strips the `HealthIndicator` suffix if present. In the example:

| Name source | Identifier used on the tree |
| --- | --- |
| Bean `cacheHealthIndicator` | cache |
| Composite bean explicitly named `payments` | payments |
| Key `banks` in payments' map | banks, inside the payments branch |
| Key `bankB` in banks' map | bankB, inside the banks branch |

Do not mechanically apply the root bean suffix-stripping rule to every custom key in every map.

Registry also allows registering and unregistering contributors at runtime. That changes the set of monitored components; it is not the same operation as toggling an existing indicator's UP/DOWN result. The test section will add a temporary contributor and remove it in `finally`.

See [HealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html).

## 7. Full example: a payments branch with two banks

Tree to build:

```text
Root presented by HealthEndpoint
├── cache                         HealthIndicator
└── payments                      CompositeHealthContributor
    ├── banks                     CompositeHealthContributor
    │   ├── bankA                 HealthIndicator
    │   └── bankB                 HealthIndicator
    └── queue                     HealthIndicator
```

The bank, queue, and cache names in the example are all **simulations**. They help observe structure and aggregation; they do not prove connections to real banks or external infrastructure.

bankB reads a status flag. When the flag is false, it returns DOWN. Other leaf nodes return UP so status propagation is easy to observe.

### 7.1. Project structure

```text
health-contributor-tree/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── HealthTreeApplication.java
    │   │   ├── LabDependencyState.java
    │   │   └── HealthTreeConfiguration.java
    │   └── resources/application.yml
    └── test/java/example/
        ├── HealthTreeTest.java
        └── HiddenHealthTreeTest.java
```

### 7.2. pom.xml

Use JDK 21 and Maven 3.6.3+. No database, Docker, or real payment system is needed.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>health-contributor-tree</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

### 7.3. src/main/java/example/HealthTreeApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HealthTreeApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthTreeApplication.class, args);
    }
}
```

### 7.4. src/main/java/example/LabDependencyState.java

```java
package example;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class LabDependencyState {
    private final AtomicBoolean bankBUp;

    public LabDependencyState(@Value("${demo.bank-b-up:true}") boolean initiallyUp) {
        this.bankBUp = new AtomicBoolean(initiallyUp);
    }

    public boolean isBankBUp() {
        return bankBUp.get();
    }

    public void setBankBUp(boolean up) {
        bankBUp.set(up);
    }
}
```

AtomicBoolean allows reads and updates to the simulated flag to observe values safely. The setter method is only called in the lesson's test code; there is no HTTP API that mutates the flag.

The `demo.bank-b-up` property decides the initial state. A real check would obtain its signal from the system being evaluated instead of this flag.

### 7.5. src/main/java/example/HealthTreeConfiguration.java

```java
package example;

import java.util.LinkedHashMap;

import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HealthTreeConfiguration {
    @Bean
    HealthIndicator cacheHealthIndicator() {
        return () -> Health.up()
                .withDetail("scope", "in-memory-demo")
                .build();
    }

    @Bean("payments")
    CompositeHealthContributor payments(LabDependencyState state) {
        HealthIndicator bankA = () -> Health.up()
                .withDetail("probe", "simulated")
                .build();

        HealthIndicator bankB = () -> {
            if (state.isBankBUp()) {
                return Health.up()
                        .withDetail("probe", "simulated")
                        .build();
            }
            return Health.down()
                    .withDetail("reason", "simulated-unavailable")
                    .build();
        };

        var banks = new LinkedHashMap<String, HealthContributor>();
        banks.put("bankA", bankA);
        banks.put("bankB", bankB);

        HealthIndicator queue = () -> Health.up()
                .withDetail("probe", "simulated")
                .build();

        var payments = new LinkedHashMap<String, HealthContributor>();
        payments.put("banks", CompositeHealthContributor.fromMap(banks));
        payments.put("queue", queue);
        return CompositeHealthContributor.fromMap(payments);
    }
}
```

Points to compare with the model:

- Bean `cacheHealthIndicator` is a leaf node and is placed into the registry with identifier cache.
- The bean named payments is a composite at the root.
- banks and queue are child objects inside payments' map.
- bankA and bankB are child objects inside banks' map.
- Child indicators are not additionally declared with `@Bean`, so they do not automatically become standalone entries at the root.
- LinkedHashMap preserves the chosen iteration order in the example's source structure. Do not rely on JSON property order as a health contract.

HealthContributor is used as the map's value type. If you changed the map to `Map<String, HealthIndicator>`, you could not place the banks branch of type CompositeHealthContributor into that map; that is precisely why a common type for both branches and leaves is needed.

### 7.6. src/main/resources/application.yml

```yaml
server:
  port: 8080
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: always
      show-components: always
  health:
    defaults:
      enabled: false

demo:
  bank-b-up: true
```

`management.health.defaults.enabled: false` disables default auto-configured indicators so the illustrative tree focuses on cache and payments. It does not remove our custom declared contributors. This is a choice for observing the example; a real system must explicitly decide which infrastructure checks must be kept.

The two properties show-details and show-components are enabled to see the tree and sample data. The server listens only on 127.0.0.1. This full-detail visibility configuration is for learning on a personal machine; do not infer that all health details should be exposed on a public entrypoint.

## 8. Running and observing results

In the directory containing pom.xml:

```bash
mvn clean test
mvn spring-boot:run
```

Or package and run the JAR:

```bash
mvn package
java -jar target/health-contributor-tree-1.0.0.jar
```

Run only one application instance on port 8080. This is a Spring application with dependencies, so use Maven to resolve the classpath; invoking `javac` alone on a single file does not supply the required libraries.

### 8.1. Initial state: all UP

```bash
curl -sS http://127.0.0.1:8080/actuator/health
```

The JSON content corresponds to the sample tree, formatted for readability; property ordering is not a matching condition:

```json
{
  "status": "UP",
  "components": {
    "cache": {
      "status": "UP",
      "details": {
        "scope": "in-memory-demo"
      }
    },
    "payments": {
      "status": "UP",
      "components": {
        "banks": {
          "status": "UP",
          "components": {
            "bankA": {
              "status": "UP",
              "details": {
                "probe": "simulated"
              }
            },
            "bankB": {
              "status": "UP",
              "details": {
                "probe": "simulated"
              }
            }
          }
        },
        "queue": {
          "status": "UP",
          "details": {
            "probe": "simulated"
          }
        }
      }
    }
  }
}
```

The `components` entries represent the results of branches; `details` in the example are data added to Health by each leaf indicator. They are not two interchangeable names for the same thing.

URLs illustrating tree traversal:

```text
/actuator/health
/actuator/health/cache
/actuator/health/payments
/actuator/health/payments/banks
/actuator/health/payments/banks/bankB
```

The path to bankB contains all names from the root. There is no root contributor named bankB in this model, so do not infer an equivalent `/actuator/health/bankB` path.

### 8.2. Switching bankB to DOWN

Stop the current session and restart with the simulation flag set to false:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.bank-b-up=false"
```

If using the JAR:

```bash
java -jar target/health-contributor-tree-1.0.0.jar --demo.bank-b-up=false
```

Check the bankB node:

```bash
curl -sS http://127.0.0.1:8080/actuator/health/payments/banks/bankB
```

Content:

```json
{"status":"DOWN","details":{"reason":"simulated-unavailable"}}
```

The tree state at this point:

```text
cache: UP
payments: DOWN
  banks: DOWN
    bankA: UP
    bankB: DOWN
  queue: UP
Root: DOWN
```

bankA and queue do not turn DOWN on their own. The aggregated results of parent branches change because a child result is DOWN under the active policy.

The commands below are for Bash; on PowerShell use `curl.exe` and replace `/dev/null` with `NUL`:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/payments/banks/bankA
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/payments/banks/bankB
```

Results when bankB is DOWN:

```text
503
200
503
```

This is the HTTP result of the health endpoint with the default mapping in the lesson. Code 503 is not written directly inside the HealthIndicator lambda.

### 8.3. Hiding structure does not mean stopping checks

After closing the old session, you can run the JAR with the tree hidden:

```bash
java -jar target/health-contributor-tree-1.0.0.jar --demo.bank-b-up=false --management.endpoint.health.show-details=never --management.endpoint.health.show-components=never
```

GET to root still returns 503, but the body is only:

```json
{"status":"DOWN"}
```

bankB is still evaluated, and the status is still aggregated. Only the presentation policy changed. Two dedicated tests in the next section confirm this.

## 9. Testing source structure, results, and endpoint

The following classes use the full Spring Boot context together with MockMvc. They verify the registry, Java contracts, and request handling through the health endpoint in the same process, without opening a real network port.

This testing approach is suitable for proving the roles of the three types and the result structure. It does not verify firewalls, TLS, or a real banking system; the lesson's contributors are simulated.

### 9.1. src/test/java/example/HealthTreeTest.java

```java
package example;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.CompositeHealth;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HealthTreeTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    HealthContributorRegistry registry;

    @Autowired
    HealthEndpoint endpoint;

    @Autowired
    LabDependencyState state;

    @BeforeEach
    void startWithBankBUp() {
        state.setBankBUp(true);
    }

    @AfterEach
    void restoreBankB() {
        state.setBankBUp(true);
    }

    @Test
    void registryHoldsBothKindsOfContributor() {
        assertThat(registry.getContributor("cache")).isInstanceOf(HealthIndicator.class);
        assertThat(registry.getContributor("payments"))
                .isInstanceOf(CompositeHealthContributor.class);
        assertThat(registry.getContributor("cacheHealthIndicator")).isNull();
    }

    @Test
    void compositePreservesNestedNamesInsteadOfFlatteningThem() {
        var payments = (CompositeHealthContributor) registry.getContributor("payments");
        var banks = (CompositeHealthContributor) payments.getContributor("banks");

        assertThat(payments.stream().map(named -> named.getName()).toList())
                .containsExactly("banks", "queue");
        assertThat(banks.getContributor("bankA")).isInstanceOf(HealthIndicator.class);
        assertThat(banks.getContributor("bankB")).isInstanceOf(HealthIndicator.class);
        assertThat(registry.getContributor("bankB")).isNull();
        assertThat(payments.getContributor("banks/bankB")).isNull();
    }

    @Test
    void indicatorCreatesHealthAndCanOmitDetails() {
        var executions = new AtomicInteger();
        HealthIndicator indicator = () -> {
            executions.incrementAndGet();
            return Health.up().withDetail("probe", "demo").build();
        };

        Health result = indicator.getHealth(false);
        assertThat(result.getStatus()).isEqualTo(Status.UP);
        assertThat(result.getDetails()).isEmpty();
        assertThat(executions.get()).isEqualTo(1);
    }

    @Test
    void constructingACompositeDoesNotRunItsIndicator() {
        var executions = new AtomicInteger();
        HealthIndicator indicator = () -> {
            executions.incrementAndGet();
            return Health.up().build();
        };

        var composite = CompositeHealthContributor.fromMap(Map.of("leaf", indicator));
        assertThat(executions.get()).isZero();
        var leaf = (HealthIndicator) composite.getContributor("leaf");
        assertThat(executions.get()).isZero();
        assertThat(leaf.health().getStatus()).isEqualTo(Status.UP);
        assertThat(executions.get()).isEqualTo(1);
    }

    @Test
    void healthEndpointReturnsResultObjectsRatherThanContributors() {
        var result = endpoint.health();
        assertThat(result).isInstanceOf(CompositeHealth.class);
        assertThat(result).isNotInstanceOf(CompositeHealthContributor.class);
    }

    @Test
    void allUpTreeIsVisibleOverTheEndpoint() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.cache.status").value("UP"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankA.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankB.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.payments.components.queue.status").value("UP"));
    }

    @Test
    void downLeafPropagatesThroughItsAncestors() throws Exception {
        state.setBankBUp(false);
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components.cache.status").value("UP"))
                .andExpect(jsonPath("$.components.payments.status").value("DOWN"))
                .andExpect(jsonPath("$.components.payments.components.banks.status").value("DOWN"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankA.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankB.status")
                        .value("DOWN"));
    }

    @Test
    void individualLeafPathsKeepTheirOwnStatus() throws Exception {
        state.setBankBUp(false);
        mvc.perform(get("/actuator/health/payments/banks/bankA"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
        mvc.perform(get("/actuator/health/payments/banks/bankB"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"));
    }

    @Test
    void registryCanAddAndRemoveATopLevelContributor() throws Exception {
        HealthIndicator temporary = () -> Health.up().build();
        registry.registerContributor("temporary", temporary);
        try {
            mvc.perform(get("/actuator/health"))
                    .andExpect(jsonPath("$.components.temporary.status").value("UP"));
        }
        finally {
            registry.unregisterContributor("temporary");
        }
        assertThat(registry.getContributor("temporary")).isNull();
    }
}
```

Key assertions:

- Registry holds both an indicator and a composite, matching the role of the common type.
- The cache name is normalized from bean cacheHealthIndicator; bankB does not automatically appear at the root.
- Looking up a child key does not automatically parse the string `banks/bankB` as a path.
- Creating a composite does not yet execute leaf nodes.
- `getHealth(false)` still executes the indicator even though details are omitted.
- The object returned by the endpoint belongs to the result side, not contributor.
- When bankB is DOWN, only parent branch and root statuses are aggregated to DOWN; bankA stays UP.
- Registry can add a root contributor and clean it up after testing.

The simulated flag is restored before and after each method. Adding the contributor is also removed in finally. If switching tests that share state to run in parallel, state isolation must be reorganized; do not let tests mutate a shared flag and rely on random order.

### 9.2. src/test/java/example/HiddenHealthTreeTest.java

```java
package example;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "management.endpoint.health.show-details=never",
        "management.endpoint.health.show-components=never"
})
@AutoConfigureMockMvc
class HiddenHealthTreeTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    LabDependencyState state;

    @AfterEach
    void restoreBankB() {
        state.setBankBUp(true);
    }

    @Test
    void healthyTreeCanBeDisplayedAsStatusOnly() throws Exception {
        state.setBankBUp(true);
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void hiddenTreeStillComputesTheDownStatus() throws Exception {
        state.setBankBUp(false);
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }
}
```

Run:

```bash
mvn clean test
```

The example suite has 11 test methods: 9 in HealthTreeTest and 2 in HiddenHealthTreeTest. The success condition is zero failures, errors, or skipped tests. Full log output or execution times do not need to match.

The two detail-hiding tests are important: presentation policy must not lead learners to think child nodes were removed from the registry or no longer affect the root status.

## 10. When to choose an indicator, when to choose a composite?

| Need | Typically suitable choice |
| --- | --- |
| One evaluation producing one meaningful status | HealthIndicator |
| Multiple connections needing to be viewed separately under one parent name | CompositeHealthContributor containing indicators |
| A subsystem with smaller sub-branches | CompositeHealthContributor with child composites |
| A business rule evaluating serving capability from multiple signals | HealthIndicator for that rule, or an explicitly designed aggregation policy |
| Adding/removing monitored components at the root level | HealthContributorRegistry |
| Same source tree, needing a selective operational view | Consider Health Group, do not equate it with composite |

There is no need to create a composite just to hold a single leaf if that structure carries no meaning. Conversely, returning a single Health with a massive details map is not equivalent to a composite: entries in details do not automatically become child contributors that can be traversed and queried under the tree contract.

### 10.1. Composite and Health Group are different

A composite is a structure created by contributors, such as payments/banks/bankB. A Health Group is a configured view selecting matching contributors or components for a purpose.

For instance, having a payments branch does not automatically make it readiness or liveness. Those operational decisions require separate design. In particular, grouping external system checks into a composite does not mean the entire branch should be used as a signal to restart the application.

This lesson focuses on the structure and responsibilities of the three types, so it does not add probe policies or a bank fallback system to the example.

### 10.2. Naming and avoiding duplicate checks

If you both declare bankB as a root bean and place that same object inside a composite, you may accidentally present and evaluate the same source in two places. Decide the location where operators need to see it, rather than registering in multiple places just to "make sure it is discovered".

Keep the tree free of reference cycles, child names clear, and depth reasonable. An overly deep tree or names containing path-separator characters make access, group configuration, and diagnosis harder.

### 10.3. Timeouts and failures of real checks

Indicators are typically called during a health check request. A network call without a timeout can stall the request even when the composite structure is designed properly.

Time limits and check operation choices must be designed in the appropriate client/execution mechanism. A "slow indicator" warning is not itself a mechanism to cancel a network call. Do not perform operations that mutate business data just to see if a resource is still alive.

## 11. Connection to Reactive applications

Boot has a corresponding type hierarchy for Reactive checks:

| Synchronous in this lesson | Corresponding Reactive contract |
| --- | --- |
| HealthContributor | ReactiveHealthContributor |
| HealthIndicator | ReactiveHealthIndicator |
| CompositeHealthContributor | CompositeReactiveHealthContributor |

In the Reactive contract, `ReactiveHealthIndicator.health()` returns `Mono<Health>`. The roles of common source, leaf node, and branch node still maintain a similar distinction.

Do not merely rename the interface while keeping a blocking network call inside and assume it has become a non-blocking check. When building a WebFlux application, choose the appropriate contract and check the adaptation mechanism of the registry/endpoint in use. The full example in this lesson intentionally uses Spring MVC's synchronous hierarchy to clarify the three types in question.

See [Boot 3.3 Reactive Health Indicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive).

## 12. Common mistakes

| Misconception or symptom | Correct understanding |
| --- | --- |
| Calling health() on a HealthContributor variable | The marker type has no such method; the HealthIndicator contract is needed at leaf nodes |
| Only implementing an empty HealthContributor | Does not provide the leaf or branch behavior required by the endpoint model |
| HealthIndicator returning the contributor object itself | The health() method must return Health |
| CompositeHealthContributor having its own health() like an indicator | It organizes child contributors; the endpoint infrastructure retrieves and aggregates results |
| CompositeHealth and CompositeHealthContributor are the same | One is result data, the other is a structured source |
| fromMap runs checks immediately | Creating a composite does not automatically call health() on leaves |
| Putting two indicators in a composite means only one needs to be UP | Aggregation policy does not infer business fallback rules |
| Every child object automatically becomes a root bean | Objects in a map stay only at the position you organize, unless also registered separately |
| Not seeing components means there is no source tree | Check show-components and show-details before concluding |
| DOWN means the indicator directly returns HTTP 503 | Health status and HTTP mapping are two separate responsibilities |
| Child keys can always be looked up via segmented paths | getContributor looks up a direct child name; the endpoint handles multi-segment paths |
| UP proves all business operations work correctly | UP only reflects the conditions that the checks are actually evaluating |

## 13. Self-check exercises

1. Run the 11 tests and identify which variables are check sources and which are result data.
2. Add a bankC in the banks map. Explain why it sits under payments/banks instead of automatically becoming a root contributor.
3. Turn bankB into a root bean in the lab project while also keeping it in the composite. Observe the structure and decide whether both locations are needed.
4. Disable showing components and details. Prove that bankB DOWN still affects the aggregated status.
5. Before replacing the simulated flag with a real client, define the UP/DOWN conditions, timeout, permitted detail data, and why a separate leaf or branch is needed.

You have grasped the model properly when you can distinguish the **common type participating in the tree**, the **leaf node performing evaluations**, the **branch node organizing child sources**, and the **result tree presented by the endpoint**, and then trace the path from a DOWN leaf to the aggregated status.
