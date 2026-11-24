# Organizing Multiple Components with Composite Health Contributors

## 1. From a Single Check to a Health Tree

Suppose a purchasing feature depends on inventory and two regional payment connections. Returning only a single `DOWN` status tells the operator that the feature has a problem, yet not which branch failed. Putting every check at the same flat level makes it hard for the result structure to reflect relationships among them.

A **composite health contributor** organizes multiple named components into a tree. Each leaf executes a check; each composite node holds child components. When reading health, Actuator traverses the tree, collects results from the leaves, and aggregates statuses for each branch.

This lesson uses Spring Boot 3.3.x and Java 17 or newer; the sample project picks JDK 21. The goal is to build a health tree, read results accurately, and avoid confusing tree structure with health evaluation policy.

The tree we will build:

```text
health
└── commerce
    ├── inventory
    └── payments
        ├── eu
        └── us
```

- `commerce`: branch serving purchasing.
- `inventory`: inventory check.
- `payments`: branch containing payment checks.
- `eu`, `us`: two independent payment leaves.

Region names are only examples. The program simulates statuses via configuration rather than calling real warehouses, banks, or external services.

## 2. What Roles Do the Data Types Play?

| Type | Role in this lesson |
| --- | --- |
| `HealthContributor` | Common type for registering a component into the health system. |
| `HealthIndicator` | Leaf providing a `Health` result via `health()`. |
| `CompositeHealthContributor` | Node holding named child `HealthContributor` instances; a child may itself be a composite. |
| `Health` | Result of a check, containing `status` and optionally `details`. |
| `CompositeHealth` | Aggregate result containing a status and child component results. |
| `StatusAggregator` | Policy selecting an aggregate status from child statuses. |

`HealthIndicator` is a functional interface and can be written as a lambda. `CompositeHealthContributor` provides child traversal and lookup by name; it does not have a `health()` method to invoke like an indicator. See [HealthIndicator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html) and [CompositeHealthContributor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Distinguish the two sides:

```text
Structure used to perform checks           Result after execution
HealthIndicator                    -->  Health
CompositeHealthContributor         -->  CompositeHealth
```

Therefore, do not return a `CompositeHealth` from a `@Bean` method expecting Spring to treat it as a check contributor. Result objects do not replace check-executing objects. [CompositeHealth API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealth.html) describes that result side.

Another easy confusion: placing multiple values into `Health.up().withDetail(...)` only creates detail data for a single leaf. Those values do not automatically become separately queryable and aggregatable health components.

## 3. Complete Runnable Project

### 3.1. File Structure

Create a standalone directory with the layout:

```text
composite-health-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── health/
        │           └── CompositeHealthApplication.java
        └── resources/
            └── application.properties
```

The two required dependencies are Web and Actuator. No database, Docker, or Spring Security is needed for this local experiment.

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>composite-health-demo</artifactId>
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

The version is pinned so the experiment is reproducible within the Spring Boot 3.3 line. When applying to another project, use the patch version approved by that project instead of copying version numbers mechanically.

### 3.2. Declaring a Composite Containing a Composite

Contents of `src/main/java/example/health/CompositeHealthApplication.java`:

```java
package example.health;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class CompositeHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompositeHealthApplication.class, args);
    }

    @Bean(name = "commerce")
    CompositeHealthContributor commerce(
            @Value("${demo.inventory-up:true}") boolean inventoryUp,
            @Value("${demo.payment-eu-up:false}") boolean paymentEuUp) {

        HealthIndicator inventory = () -> simulated("inventory", inventoryUp);
        HealthIndicator eu = () -> simulated("eu", paymentEuUp);
        HealthIndicator us = () -> simulated("us", true);

        Map<String, HealthContributor> paymentChildren = new LinkedHashMap<>();
        paymentChildren.put("eu", eu);
        paymentChildren.put("us", us);
        CompositeHealthContributor payments =
                CompositeHealthContributor.fromMap(paymentChildren);

        Map<String, HealthContributor> commerceChildren = new LinkedHashMap<>();
        commerceChildren.put("inventory", inventory);
        commerceChildren.put("payments", payments);
        return CompositeHealthContributor.fromMap(commerceChildren);
    }

    private static Health simulated(String check, boolean available) {
        Health.Builder builder = available ? Health.up() : Health.down();
        return builder.withDetail("check", check)
                .withDetail("mode", "simulation")
                .build();
    }
}
```

Four points to read in order:

1. The three variables `inventory`, `eu`, and `us` are three `HealthIndicator` instances. Lambdas execute only when `health()` is called; creating the lambda does not run the check yet.
2. `paymentChildren` maps child names to check objects. `fromMap` builds the `payments` branch from that map.
3. `commerceChildren` holds both a leaf and a composite, so its value type is `HealthContributor`, not `HealthIndicator`.
4. Only `commerce` is declared as a bean. The leaves and the `payments` branch are reached through this tree.

`LinkedHashMap` makes the insertion order of children explicit in code. Software reading JSON must rely on property names, not on field position or ordering in the response.

There are no real payment connections here. The `simulated` method simply builds stable results to focus on observing the tree structure.

### 3.3. Configuration for Local Experimentation

Contents of `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always

demo.inventory-up=true
demo.payment-eu-up=false
```

`show-components` controls displaying the component tree; `show-details` controls detailed check data. These two visibility options do not alter check outcomes.

The `always` settings here serve observation on a local machine. When moving to production, choose appropriate viewing permissions and access policies; do not put secrets into `details`. The [Health Information and Health Groups documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health) explains visibility properties, HTTP status mapping, and health groups.

### 3.4. Compiling and Running

From the directory containing `pom.xml`, using JDK 21 and Maven:

```shell
mvn clean package
java -jar target/composite-health-demo-1.0.0.jar
```

This application has Spring Boot dependencies, so do not run `javac CompositeHealthApplication.java` standalone with an empty classpath. Maven resolves dependencies and builds an executable JAR. The first build needs to download dependencies if the machine does not have them cached yet.

Open another terminal:

```shell
curl -i http://127.0.0.1:8080/actuator/health/commerce
```

On Windows PowerShell, you can use `curl.exe` to invoke the real curl program. Startup logs include timestamps and environment info, so there is no single fixed stdout for the whole process.

With the configuration above, the HTTP status code is **503**, and the JSON body has the following structure; whitespace and field ordering may vary:

```json
{
  "status": "DOWN",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "check": "inventory",
        "mode": "simulation"
      }
    },
    "payments": {
      "status": "DOWN",
      "components": {
        "eu": {
          "status": "DOWN",
          "details": {
            "check": "eu",
            "mode": "simulation"
          }
        },
        "us": {
          "status": "UP",
          "details": {
            "check": "us",
            "mode": "simulation"
          }
        }
      }
    }
  }
}
```

This response shows the path to the cause is `commerce → payments → eu`. Looking only at `commerce.status` would not suffice to tell which leaf caused that status.

If calling `/actuator/health`, the result may also contain indicators auto-configured by Spring Boot, such as `diskSpace` or `ping`. Therefore, do not use the JSON of the `commerce` branch alone as a fixed template for the whole application.

## 4. How Is the Aggregate Status Produced?

In the example, evaluation can be understood layer by layer:

```text
eu = DOWN, us = UP
        |
        v
payments = DOWN

inventory = UP, payments = DOWN
        |
        v
commerce = DOWN
```

Composites provide structure and child names; the aggregation policy decides the representative status. In Spring Boot 3.3, the default order of `SimpleStatusAggregator` prioritizes `DOWN`, then `OUT_OF_SERVICE`, `UP`, `UNKNOWN`. The aggregator selects the highest-priority status among those it recognizes. This is not majority voting. Ten `UP` leaves and one `DOWN` leaf can still yield `DOWN`. [SimpleStatusAggregator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

With the default policy and only the two statuses `UP`/`DOWN` in this lesson:

| inventory | eu | us | payments | commerce |
| --- | --- | --- | --- | --- |
| UP | DOWN | UP | DOWN | DOWN |
| UP | UP | UP | UP | UP |
| DOWN | UP | UP | UP | DOWN |
| DOWN | DOWN | UP | DOWN | DOWN |

Each row's outcome is predictable from the evaluation policy, not because names like `inventory` or `payments` carry special meaning to Spring.

To run the case where every leaf is `UP`, stop the previous process with Ctrl+C and run:

```shell
java -jar target/composite-health-demo-1.0.0.jar --demo.payment-eu-up=true
```

Then `/actuator/health/commerce` returns `status=UP` and HTTP **200**.

Continue testing the case where inventory fails while payments operate:

```shell
java -jar target/composite-health-demo-1.0.0.jar --demo.payment-eu-up=true --demo.inventory-up=false
```

Now `payments` is `UP`, whereas `commerce` is `DOWN` and HTTP **503**. Both parameters are read when initializing the bean; editing the configuration file does not automatically update a running bean's status. You must restart to switch the experiment to another parameter set.

Do not assume every non-`UP` status gets HTTP 503. Under default mapping, `DOWN` and `OUT_OF_SERVICE` map to 503; unmapped statuses, including `UNKNOWN`, may return 200. If configuring custom status ordering or HTTP mapping, results must be evaluated against that configuration.

## 5. Component Names Form the Path in the Tree

With the initial example, the following levels can be queried:

| Path | Observed target | Default result in the example |
| --- | --- | --- |
| `/actuator/health/commerce` | Entire purchasing branch | DOWN, HTTP 503 |
| `/actuator/health/commerce/inventory` | Inventory leaf | UP, HTTP 200 |
| `/actuator/health/commerce/payments` | Payments branch | DOWN, HTTP 503 |
| `/actuator/health/commerce/payments/eu` | EU payment leaf | DOWN, HTTP 503 |
| `/actuator/health/commerce/payments/us` | US payment leaf | UP, HTTP 200 |

The outermost bean name is pinned via `@Bean(name = "commerce")`. Subsequent segments come from the keys of each map. The `eu` leaf is not a root-level bean, so `/actuator/health/eu` is not its path.

Accessing child paths also depends on component visibility permissions and security configuration. An incorrect path or hidden component can yield 404; 401/403 requires checking the authentication/authorization layer first. Do not treat every HTTP error as proof that a dependency broke.

Spring Boot 3.3.0's [HealthEndpointSupport source](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java) shows how contributors are looked up segment by segment and how results are aggregated.

### Accessing via Java When You Already Have a Composite

The following snippet is illustrative code placed in a method receiving a `CompositeHealthContributor` variable named `commerce`, not a standalone program:

```java
HealthContributor paymentsNode = commerce.getContributor("payments");
if (paymentsNode instanceof CompositeHealthContributor payments) {
    HealthContributor euNode = payments.getContributor("eu");
    if (euNode instanceof HealthIndicator euIndicator) {
        Health result = euIndicator.health();
        System.out.println(result.getStatus().getCode());
    }
}
```

With the initial tree, the printed line is:

```text
DOWN
```

Calling `getContributor("payments/eu")` on `commerce` does not replace two lookup steps: its direct keys are `inventory` and `payments`. HTTP paths are split into segments by the endpoint; the child lookup API uses the child name at the current level directly.

Do not cast every `HealthContributor` to `HealthIndicator`: the `payments` branch is a composite and that cast will fail.

## 6. Encapsulating Multiple Checks While Keeping Clear Responsibilities

A maintainable design usually separates two concerns:

- **Leaves** know how to check one concrete dependency and turn the outcome into `Health`.
- **Composites** know which leaves belong to a branch, what their names are, and what the hierarchy looks like.

In a real application, lambdas can be replaced by a `HealthIndicator` class receiving a client through its constructor. The composite still organizes those objects via maps. There is no need to cram all connection code, error handling, and naming rules into one giant method.

The API provides two useful factory forms:

```java
CompositeHealthContributor.fromMap(contributors);
CompositeHealthContributor.fromMap(resources, resource -> toIndicator(resource));
```

This illustrates the call signatures: `contributors` already holds contributors; `resources` holds resources, and `toIndicator` is an application-provided function turning each resource into a contributor. Those two lines are not standalone runnable code and there is no built-in `toIndicator` function in Spring.

Do not run a network check and cache a fixed `Health` result right when building the tree. Keep an object capable of executing the check at the appropriate health read time. In this lesson, booleans are fixed intentionally for simulation; that is not how to detect when a real connection recovers.

### Avoid Duplicate Leaf Registration

If you both annotate an indicator with `@Component` and place the same object inside a composite, that indicator can appear both at the root level and inside the branch. Reading health may run the same check multiple times.

When you want a leaf to belong solely to a composite:

- Create the leaf inside the composite's factory as in the example; or
- Register a helper object that does not implement `HealthContributor` as a bean, then create the wrapping indicator inside the composite.

If a leaf must exist in multiple views for distinct purposes, accept and control the evaluation cost. Do not use appearing in multiple places as a status-duplication trick without checking its impact.

### Names and Structure Should Be Stable

Choose short, operationally meaningful names that stay stable across deployments. Within the same map, each name maps to one child; calling `put` again with the same key replaces the previous value rather than creating two duplicate-named leaves.

Avoid names containing `/`, names taken from user data, or unbounded child counts. Changing a map key also changes the observation path and can break dashboards or group configurations referencing the old name.

Trees can contain multiple levels, yet must be finite and non-self-referential. Do not mutate a map or child list concurrently while the endpoint is traversing it unless an explicit synchronization mechanism is designed. Map-based factories fit statically built structures best; do not assume by default that they are thread-safe dynamic registries.

Spring provides `HealthContributorRegistry` to register or remove contributors at runtime, yet managing a dynamic registry is a separate responsibility. Adding an entry to an external map is not a guaranteed contract for dynamic registration. [HealthContributorRegistry API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html).

## 7. Composites and Health Groups Solve Different Needs

| Need | Suitable mechanism |
| --- | --- |
| Represent `commerce` containing `inventory` and `payments` | Composite contributor |
| Create a view containing only selected existing contributors | Health group |
| Compute overall status from child statuses | Status aggregator |
| Convert status to HTTP 200/503 or another code | HTTP status mapper |
| Show or hide child/detail data | `show-components`, `show-details`, and access permissions |

A composite is structure. A group selects components and policies for a view. Creating a group does not automatically create new indicators and does not make dependencies genuinely independent of one another.

After running the basic example, you can add to `application.properties`:

```properties
management.endpoint.health.group.checkout.include=commerce
management.endpoint.health.group.usOnly.include=commerce/payments/us
```

Restart the application with the initial state:

- `/actuator/health/checkout` evaluates all of `commerce`, so it remains `DOWN`.
- `/actuator/health/usOnly` evaluates only the US leaf, so it is `UP`, even though the EU leaf outside the selected set is `DOWN`.

When configuring a group to select a nested leaf, use the full path `commerce/payments/us`. Writing `include=us` targets a root-level ID that does not exist in the example. Adding groups can also cause responses to include a `groups` field; do not compare the extended configuration's JSON verbatim against the earlier JSON sample.

Only exclude a dependency from a group after confirming it does not govern serving capability for that view. Creating a group that omits EU only changes the question asked of the system; it does not fix the EU connection.

This lesson does not alter liveness/readiness configuration. When considering adding branches to those probes, evaluate serving semantics and operational consequences first rather than putting every external dependency into every probe by default.

## 8. Execution Cost and Mistakes to Prevent

### Composites Do Not Automatically Create Parallelism

For the synchronous tree in this example, the endpoint iterates through contributors and collects indicator results. Grouping multiple leaves into a composite does not automatically turn blocking calls into parallel tasks or grant them timeouts.

If three sequential checks take 200 ms, 300 ms, and 400 ms, the time spent on them can be roughly 900 ms before other overhead. This is an estimate for sequential execution, not a Spring latency guarantee.

When replacing simulation with real clients:

- Configure connect, read, and resource-wait timeouts at the appropriate client layer.
- Keep checks lightweight, repeatable, and free of business transactions.
- Convert expected errors into meaningful health results; avoid letting an unhandled exception turn health reads into unexpected errors.
- Do not let each health read run long retries or write data into dependencies.
- Distinguish slow checks from failed checks; the warning threshold does not replace client timeouts.

The example uses direct lambdas with no extra exception-catching layer. When writing real checks, `AbstractHealthIndicator` is one option for managing result construction and exception handling per its contract; understand its behavior thoroughly before substituting it.

### Reactive Trees Use Their Own Type Hierarchy

For reactive flows, the corresponding types are `ReactiveHealthIndicator`, `ReactiveHealthContributor`, and `CompositeReactiveHealthContributor`; leaves return `Mono<Health>`. Reactive composite factories accept reactive contributors. Do not pass a synchronous map into a reactive factory expecting it to understand every type automatically.

A blocking network call does not become asynchronous merely by being placed in a lambda that creates a `Mono`. Choose clients, scheduling, and timeout policies suited to the execution thread. This section only outlines the boundary to avoid mixing type systems; the runnable example in this lesson is synchronous Spring MVC. [CompositeReactiveHealthContributor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeReactiveHealthContributor.html).

### Do Not Mistake a Neat Structure for the Right Policy

A composite does not by default understand "two payment regions where only one needs to work." Under the policy where `DOWN` beats `UP`, one failing region still makes the `payments` branch `DOWN`.

If the system genuinely keeps serving via regional failover or a fallback plan, define the serving condition explicitly and represent it with appropriate indicators, groups, or aggregation policies. Do not name a composite `highAvailability` and assume Spring will automatically compute "at least one region alive."

Likewise, an empty composite or a group selecting no leaves does not prove functionality works. Catch missing configurations rather than relying on a generic status and missing the absence of real checks.

## 9. Quick Diagnostics When Results Differ from Expectations

| Symptom | What to inspect |
| --- | --- |
| Only `status` is visible, no tree | `show-components`, `show-details`, viewing permissions, and group configuration. |
| Child branch returns 404 | Full path, map key spelling, registered tree, and component visibility permissions. |
| A leaf appears both at root and inside composite | Whether the leaf is also a self-registered bean. |
| Most leaves are UP yet branch is DOWN | Aggregation policy; majority voting is not used. |
| Health slows down after adding many children | Cost of each leaf, client timeouts, call counts, and duplicate registration. |
| Config changed yet simulated status did not | Example reads booleans at startup; stop the old process and restart. |
| Group fails to initialize | Whether included/excluded contributor names exist at their full paths. |
| Casting contributor throws an error | Whether the object is an indicator or a composite; check type before calling leaf APIs. |

If the response contains extra components beyond the sample, inspect the classpath and auto-configuration first. A new dependency can add other indicators; do not delete useful indicators just to make the response resemble documentation.

## 10. Self-Verification Practice

1. Run the example as-is. Verify that the EU leaf, `payments` branch, and `commerce` branch are all `DOWN`, while the US leaf stays `UP`.
2. Restart with `--demo.payment-eu-up=true`. Verify that `payments` and `commerce` switch to `UP`.
3. Restart with EU working while inventory fails. Explain why `payments` is `UP` yet `commerce` is `DOWN`.
4. Add a `refunds` leaf to `paymentChildren` before creating the composite, with a simulated `UP` check. Identify the new leaf's path as `/actuator/health/commerce/payments/refunds`.
5. Add the `usOnly` group as shown above. Explain why this group can be `UP` while `commerce` is `DOWN`, and why that result does not prove all of payments recovered.
6. Change `show-components` and `show-details` to `never`, restart, and compare the root endpoint against child paths. Separate visibility issues from check status.

You have mastered this lesson when you can build a tree from contributors yourself, trace the exact path to a leaf, explain status aggregation, and choose cleanly between changing composite structure and creating a health group view.
