# Aggregating Statuses with StatusAggregator

## 1. From multiple check results to a single overall status

An application may check a database, cache, and partner service. Each check returns a status, yet monitoring software often needs one conclusion for the entire system or a check group.

Suppose the results are:

~~~text
storage: UP
cache: UP
partner: DOWN
~~~

The question to solve is not "how many UP words appear in JSON", but: **under the chosen health policy, how should this set of statuses be concluded?**

`StatusAggregator` is the strategy that aggregates `Status` values into a single `Status`. In the health pipeline, it sits after running checks and before mapping the result to an HTTP status code:

~~~text
HealthIndicator executes check
        ↓
Health carries status of each component
        ↓
StatusAggregator selects aggregated status
        ↓
HttpCodeStatusMapper selects HTTP status code
        ↓
Health endpoint returns response
~~~

This lesson uses **Spring Boot 3.3.x and Java 21**. The custom status examples are policies defined by this lesson, not default statuses or rules that Spring Boot applies automatically.

## 2. The StatusAggregator contract: input is a set of statuses

The core method has the signature:

~~~java
Status getAggregateStatus(Set<Status> statuses);
~~~

This is an illustrative interface signature, not a standalone runnable Java file.

`Status` is an object representing a status, with constants such as `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`; it also allows creating custom codes with `new Status("DEGRADED")`. It is not an enum containing strictly four fixed values. See [Status API 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Status.html).

### 2.1. The aggregator does not receive full Health objects

The input does not contain bean names, check timestamps, exceptions, service URLs, or details maps. Therefore, a typical aggregator does not know whether DOWN came from the database or an auxiliary service.

If you need a policy like "database is required, recommendation service may fail", express that scope using health groups, contributor structure, or a dedicated check. Do not try to reverse-infer identity from a set of statuses that has already lost that information.

### 2.2. A Set does not preserve vote counts

For example:

~~~text
UP, UP, UP, DOWN
        ↓
Set containing UP and DOWN
~~~

That input does not indicate whether three components are UP or three thousand components are UP. Nor does it preserve bean registration order.

Consequently, this contract alone cannot accurately compute a majority policy or "at least 2 out of 3 machines healthy". A dedicated indicator can know the list of machines, count results, and return a final status; that status then enters the overall aggregator.

The interface also has a convenience method accepting multiple `Status` values, which ultimately converts them into a set for aggregation; see [StatusAggregator 3.3 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/StatusAggregator.java).

### 2.3. This is a conclusion policy, not a place for network checks

An aggregator should not re-query the database or send HTTP requests to verify each status. Indicators are responsible for performing checks; the aggregator processes the results already produced.

A proper implementation should be deterministic, independent of Set iteration order, not mutate the input Set, and hold no mutable state across requests. This also makes behavior easy to test when multiple health requests occur concurrently.

## 3. What does the default SimpleStatusAggregator do?

Spring Boot provides `SimpleStatusAggregator`, which uses a status priority list. In Boot 3.3, the default order is:

~~~text
DOWN → OUT_OF_SERVICE → UP → UNKNOWN
~~~

This is a policy-defined order, not alphabetical order and not indicator execution order.

How to read the algorithm:

1. Consider the statuses present in the input set.
2. Keep only codes recognized by the order list.
3. Pick the status with the earliest priority position.
4. If no recognized status remains, return `UNKNOWN`.

Not all statuses in the list need to appear. Just one DOWN means DOWN takes precedence over the other standard values.

| Input set | Default result |
| --- | --- |
| UP | UP |
| UP, DOWN | DOWN |
| UP, OUT_OF_SERVICE | OUT_OF_SERVICE |
| DOWN, OUT_OF_SERVICE | DOWN |
| UP, UNKNOWN | UP |
| UNKNOWN | UNKNOWN |
| Empty set when calling aggregator directly | UNKNOWN |

Two points worth noting:

- UNKNOWN comes after UP by default. It does not automatically turn an UP result into UNKNOWN.
- The empty-set rule is the result of calling the aggregator directly. Do not generalize that a health endpoint with no contributors must always return the same result; the endpoint also has logic handling the case of no contributions.

The selection mechanism and default order can be verified in [SimpleStatusAggregator 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java). Constructors accepting a list or ordered codes are in the [SimpleStatusAggregator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

## 4. UNKNOWN differs from a code unrecognized by the aggregator

This is an important distinction:

- `Status.UNKNOWN` is a standard status present in the default list.
- `new Status("DEGRADED")` is a custom code; by default there is no slot for it.

With the default aggregator:

| Input set | Result | Reason |
| --- | --- | --- |
| UP, DEGRADED | UP | DEGRADED is unrecognized, UP remains |
| DEGRADED | UNKNOWN | No code in the set is recognized |
| DOWN, DEGRADED | DOWN | DOWN is recognized and prioritized |
| UP, MYSTERY | UP | Unknown code does not automatically become a severe error |

The aggregator does not understand the English meaning of DEGRADED or FATAL. A word that sounds severe to humans does not cause the framework to assign severity automatically.

Practical consequence: an indicator can display `status: "DEGRADED"` on a component, while the root remains UP because another component is UP. To change the overall conclusion, you must configure the order or provide an appropriate aggregator.

Status codes should be standardized across the program, such as using uppercase and underscores for standard codes. Do not rely on alphabetical order or spelling variations to express severity.

## 5. Configuring the order: explicitly keep the statuses to consider

If the requirement is "DEGRADED must take priority over UP and UNKNOWN must not be masked by UP either", you can use:

~~~yaml
management:
  endpoint:
    health:
      status:
        order:
          - down
          - out-of-service
          - degraded
          - unknown
          - up
~~~

This list is **a new policy**. Compared to the default, UNKNOWN has been moved ahead of UP; this is an intentional choice, not a copy of the default.

Results under the list above:

| Input | Result |
| --- | --- |
| UP, DEGRADED | DEGRADED |
| UP, UNKNOWN | UNKNOWN |
| DEGRADED, UNKNOWN | DEGRADED |
| DOWN, DEGRADED | DOWN |
| UP, MYSTERY | UP |

The last row still deserves attention: MYSTERY is not in the new list, so it remains unrecognized.

The configuration list is not a request to "add one item and keep every default item". A short list like just `degraded,up` will drop DOWN and OUT_OF_SERVICE from the set of codes selected by that list. If UP appears together with DOWN, a policy missing DOWN can conclude UP.

Explicitly declare all codes the policy needs to understand, and test both standard and custom statuses. Do not only test the DEGRADED case and forget to check DOWN.

## 6. Status order and HTTP status codes are two different configurations

After aggregating to DEGRADED, HTTP does not automatically change to 503. By default DOWN and OUT_OF_SERVICE map to 503; unmapped codes usually use 200, including UNKNOWN and custom codes.

If you want DEGRADED to return 503 and preserve the standard error mappings:

~~~yaml
management:
  endpoint:
    health:
      status:
        http-mapping:
          down: 503
          out-of-service: 503
          degraded: 503
~~~

When declaring a custom mapping, you must keep DOWN and OUT_OF_SERVICE if you want to preserve default behavior. Declaring only `degraded: 503` can cause the two standard statuses to no longer map to 503 as before.

The two configurations answer two questions:

| Configuration | Question |
| --- | --- |
| `status.order` | Among the child results, which health conclusion is chosen? |
| `status.http-mapping` | Once that conclusion is chosen, which HTTP code must be returned? |

Setting `http-mapping.degraded=503` does not automatically prioritize DEGRADED ahead of UP. Conversely, placing DEGRADED at the top of the list does not automatically give it HTTP code 503.

UNKNOWN by default can still return 200 even when a cautious aggregation policy chooses UNKNOWN. If you decide UNKNOWN should not be considered ready to serve traffic, you must also address HTTP mapping and how monitoring software consumes the result.

Ordering, custom codes, and the rule for retaining default mappings are described in the [Spring Boot 3.3 health guide](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

## 7. Small program to observe the algorithm

This example only calls the aggregator class; it does not start a web server and performs no network checks.

In a Gradle project that already has the Java plugin, Spring Boot 3.3.x plugin, and dependency management, the required dependency is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Create `src/main/java/com/example/aggregation/AggregatorConsoleDemo.java`:

~~~java
package com.example.aggregation;

import java.util.Set;

import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.actuate.health.StatusAggregator;

public class AggregatorConsoleDemo {
    public static void main(String[] args) {
        StatusAggregator defaults = new SimpleStatusAggregator();
        StatusAggregator ordered = new SimpleStatusAggregator(
            "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UNKNOWN", "UP"
        );
        Status degraded = new Status("DEGRADED");

        System.out.println("default UP+DOWN = " +
            defaults.getAggregateStatus(Set.of(Status.UP, Status.DOWN)).getCode());
        System.out.println("default UP+UNKNOWN = " +
            defaults.getAggregateStatus(Set.of(Status.UP, Status.UNKNOWN)).getCode());
        System.out.println("default UP+DEGRADED = " +
            defaults.getAggregateStatus(Set.of(Status.UP, degraded)).getCode());
        System.out.println("default DEGRADED = " +
            defaults.getAggregateStatus(Set.of(degraded)).getCode());
        System.out.println("ordered UP+DEGRADED = " +
            ordered.getAggregateStatus(Set.of(Status.UP, degraded)).getCode());
        System.out.println("ordered UP+UNKNOWN = " +
            ordered.getAggregateStatus(Set.of(Status.UP, Status.UNKNOWN)).getCode());
        System.out.println("default empty = " +
            defaults.getAggregateStatus(Set.<Status>of()).getCode());
    }
}
~~~

Add a run task to `build.gradle`:

~~~groovy
tasks.register('runAggregatorDemo', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.aggregation.AggregatorConsoleDemo'
}
~~~

Run from PowerShell:

~~~powershell
.\gradlew.bat runAggregatorDemo --quiet
~~~

Lines printed by the program:

~~~text
default UP+DOWN = DOWN
default UP+UNKNOWN = UP
default UP+DEGRADED = UP
default DEGRADED = UNKNOWN
ordered UP+DEGRADED = DEGRADED
ordered UP+UNKNOWN = UNKNOWN
default empty = UNKNOWN
~~~

This code uses Spring Boot libraries, so a bare `javac` command without the Actuator classpath will not suffice. The `JavaExec` task pulls the classpath from the project dependencies.

## 8. When do you need to write a custom StatusAggregator?

An ordered list works well when the requirement is prioritizing known codes. If you need a different rule, such as "any unrecognized code must make the result UNKNOWN rather than being masked by UP", you can write a custom implementation.

The following example policy:

1. Empty set → UNKNOWN.
2. Contains DOWN → DOWN.
3. Contains OUT_OF_SERVICE → OUT_OF_SERVICE.
4. Contains a code outside the known list or contains UNKNOWN → UNKNOWN.
5. Contains DEGRADED → DEGRADED.
6. Remaining cases, with a non-empty set containing only known codes → UP.

This is a lesson policy, not a mandatory standard for all systems. With DOWN plus an unfamiliar code, DOWN is still chosen at step 2. With DEGRADED plus UNKNOWN, UNKNOWN is chosen; this differs from the list in the previous section.

`ConservativeStatusAggregator.java`:

~~~java
package com.example.aggregation;

import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.actuate.health.StatusAggregator;

public final class ConservativeStatusAggregator implements StatusAggregator {
    private static final Set<String> KNOWN_CODES = Set.of(
        "DOWN", "OUT_OF_SERVICE", "UNKNOWN", "DEGRADED", "UP"
    );

    @Override
    public Status getAggregateStatus(Set<Status> statuses) {
        if (statuses.isEmpty()) {
            return Status.UNKNOWN;
        }

        Set<String> codes = statuses.stream()
            .map(Status::getCode)
            .collect(Collectors.toSet());

        if (codes.contains("DOWN")) {
            return Status.DOWN;
        }
        if (codes.contains("OUT_OF_SERVICE")) {
            return Status.OUT_OF_SERVICE;
        }
        if (!KNOWN_CODES.containsAll(codes) || codes.contains("UNKNOWN")) {
            return Status.UNKNOWN;
        }
        if (codes.contains("DEGRADED")) {
            return new Status("DEGRADED");
        }
        return Status.UP;
    }
}
~~~

Codes in this implementation are compared using standardized uppercase strings. It does not automatically use SimpleStatusAggregator's code normalization rules. If the system receives multiple casing styles, normalization must be defined and tested rather than assuming both implementations behave identically.

Do not return null when the result is unknown; use a status with a clear meaning. This example's input must be a non-null Set containing valid Status instances. It does not define a contract for null values.

### Registering the bean in a dedicated profile

When using Spring Boot, merely instantiating an object with `new` inside an ordinary class does not make the endpoint use it. A bean must be registered.

`ConservativeAggregationConfiguration.java`:

~~~java
package com.example.aggregation;

import org.springframework.boot.actuate.health.StatusAggregator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("conservative")
public class ConservativeAggregationConfiguration {
    @Bean
    StatusAggregator healthStatusAggregator() {
        return new ConservativeStatusAggregator();
    }
}
~~~

Activate the `conservative` profile so the endpoint uses this implementation. When the profile is inactive, Spring Boot can auto-configure SimpleStatusAggregator from properties if no other bean is present.

Once a custom bean is provided, editing `management.endpoint.health.status.order` does not automatically change the algorithm in that bean. The code above also does not read this property. Do not configure an order list and assume it is definitely controlling your custom-written bean.

That auto-configuration only creates an aggregator when a matching bean is absent can be verified in [HealthEndpointConfiguration 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

## 9. Endpoint hands-on: observing policy changes

This section adds a web server to the project from section 7. Keep the classes already created, add dependencies, and specify the main class to separate it from the console program:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.aggregation.AggregationApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

These dependency declarations are merged into the project's dependencies block; there is no need to declare actuator a second time.

`AggregationApplication.java`:

~~~java
package com.example.aggregation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AggregationApplication {
    public static void main(String[] args) {
        SpringApplication.run(AggregationApplication.class, args);
    }
}
~~~

`DemoHealthConfiguration.java`:

~~~java
package com.example.aggregation;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoHealthConfiguration {
    @Bean
    HealthIndicator primaryHealthIndicator() {
        return () -> Health.up()
            .withDetail("source", "simulated")
            .build();
    }

    @Bean
    HealthIndicator remoteHealthIndicator(
            @Value("${lab.remote-status:DEGRADED}") String remoteStatus) {
        return () -> Health.status(remoteStatus)
            .withDetail("source", "simulated")
            .build();
    }
}
~~~

These are two simulated checks, not connecting to a real system. Because the beans have the HealthIndicator suffix, their corresponding IDs are `primary` and `remote`.

`src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: always
      show-details: never
      probes:
        enabled: false
  health:
    defaults:
      enabled: false

lab:
  remote-status: DEGRADED
~~~

Disabling default auto-configured indicators ensures the lab uses only the simulated contributors. The example does not add Spring Security and listens only on loopback. If used in a secured project, it must satisfy that project's policy.

### 9.1. Running with the default aggregator

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal:

~~~powershell
curl.exe -i `
    -H "Accept: application/vnd.spring-boot.actuator.v3+json" `
    http://127.0.0.1:8080/actuator/health
~~~

The HTTP code is 200; the body is semantically equivalent to:

~~~json
{
  "status": "UP",
  "components": {
    "primary": {
      "status": "UP"
    },
    "remote": {
      "status": "DEGRADED"
    }
  }
}
~~~

This is not a display bug. DEGRADED is not yet in the default order, so UP is selected.

### 9.2. Configuring the aggregator to recognize DEGRADED

Create `src/main/resources/application-ordered.yml`:

~~~yaml
management:
  endpoint:
    health:
      status:
        order:
          - down
          - out-of-service
          - degraded
          - unknown
          - up
~~~

Stop the previous run with Ctrl+C and run:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ordered"
~~~

The root conclusion becomes DEGRADED, yet HTTP is still 200 because no dedicated mapping exists yet. Both components retain their statuses; changing aggregation policy does not rewrite indicator results.

### 9.3. Adding HTTP mapping

Create `src/main/resources/application-mapped.yml`:

~~~yaml
management:
  endpoint:
    health:
      status:
        http-mapping:
          down: 503
          out-of-service: 503
          degraded: 503
~~~

Restart:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ordered,mapped"
~~~

The root is still DEGRADED; HTTP is now 503. This is a change at the mapping layer, not a new network check.

### 9.4. Trying a code unknown to the list

Restart with remote set to MYSTERY:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ordered,mapped --lab.remote-status=MYSTERY"
~~~

The root is UP again, HTTP 200: the ordered list still does not know MYSTERY, while primary returns UP.

Switch to the conservative bean:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=conservative,mapped --lab.remote-status=MYSTERY"
~~~

The root becomes UNKNOWN because the bean does not ignore unfamiliar codes. HTTP is still 200 because the mapped profile has not mapped UNKNOWN. To make UNKNOWN return 503, you must decide and additionally declare `unknown: 503`; do not infer that merely from the profile name conservative.

JSON key order has no policy meaning. When verifying, compare status and HTTP separately, rather than comparing raw response strings.

## 10. Matrix testing instead of a single UP branch

Create `src/test/java/com/example/aggregation/StatusAggregationTest.java`:

~~~java
package com.example.aggregation;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.actuate.health.StatusAggregator;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StatusAggregationTest {
    private final StatusAggregator defaults = new SimpleStatusAggregator();
    private final StatusAggregator ordered = new SimpleStatusAggregator(
        "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UNKNOWN", "UP"
    );
    private final StatusAggregator conservative =
        new ConservativeStatusAggregator();

    @ParameterizedTest
    @MethodSource("cases")
    void comparePolicies(Set<Status> input, String defaultCode,
                         String orderedCode, String conservativeCode) {
        assertEquals(defaultCode,
            defaults.getAggregateStatus(input).getCode(), "default");
        assertEquals(orderedCode,
            ordered.getAggregateStatus(input).getCode(), "ordered");
        assertEquals(conservativeCode,
            conservative.getAggregateStatus(input).getCode(), "conservative");
    }

    static Stream<Arguments> cases() {
        return Stream.of(
            Arguments.of(statuses(), "UNKNOWN", "UNKNOWN", "UNKNOWN"),
            Arguments.of(statuses("UP"), "UP", "UP", "UP"),
            Arguments.of(statuses("UP", "DOWN"), "DOWN", "DOWN", "DOWN"),
            Arguments.of(statuses("UP", "OUT_OF_SERVICE"),
                "OUT_OF_SERVICE", "OUT_OF_SERVICE", "OUT_OF_SERVICE"),
            Arguments.of(statuses("UP", "UNKNOWN"),
                "UP", "UNKNOWN", "UNKNOWN"),
            Arguments.of(statuses("UP", "DEGRADED"),
                "UP", "DEGRADED", "DEGRADED"),
            Arguments.of(statuses("DEGRADED"),
                "UNKNOWN", "DEGRADED", "DEGRADED"),
            Arguments.of(statuses("UP", "MYSTERY"),
                "UP", "UP", "UNKNOWN"),
            Arguments.of(statuses("MYSTERY"),
                "UNKNOWN", "UNKNOWN", "UNKNOWN"),
            Arguments.of(statuses("DOWN", "DEGRADED"),
                "DOWN", "DOWN", "DOWN"),
            Arguments.of(statuses("UP", "DEGRADED", "UNKNOWN"),
                "UP", "DEGRADED", "UNKNOWN")
        );
    }

    private static Set<Status> statuses(String... codes) {
        return Arrays.stream(codes)
            .map(Status::new)
            .collect(Collectors.toSet());
    }
}
~~~

There are 11 input cases, each verifying three policies. The last case is especially informative: ordered picks DEGRADED ahead of UNKNOWN, whereas conservative intentionally picks UNKNOWN ahead of DEGRADED.

### Also testing wiring and HTTP mapping

Create `src/test/java/com/example/aggregation/AggregationHttpTest.java`:

~~~java
package com.example.aggregation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "lab.remote-status=DEGRADED",
    "management.endpoint.health.status.order=down,out-of-service,degraded,unknown,up",
    "management.endpoint.health.status.http-mapping.down=503",
    "management.endpoint.health.status.http-mapping.out-of-service=503",
    "management.endpoint.health.status.http-mapping.degraded=503"
})
@AutoConfigureMockMvc
class AggregationHttpTest {
    @Autowired MockMvc mvc;

    @Test
    void orderedStatusIsMappedToHttp() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DEGRADED"))
            .andExpect(jsonPath("$.components.primary.status").value("UP"))
            .andExpect(jsonPath("$.components.remote.status").value("DEGRADED"));
    }
}
~~~

Run:

~~~powershell
.\gradlew.bat test --tests "*StatusAggregationTest" --tests "*AggregationHttpTest"
~~~

The pure unit test verifies the algorithm; the MockMvc test further verifies whether properties are used to construct the endpoint's aggregator and mapper. Run the tests with the exact minimal project, without accidentally activating the conservative profile from external configuration.

When using a custom bean, add a corresponding integration test to prove the endpoint actually uses that bean. A passing `new ConservativeStatusAggregator()` test does not automatically prove Spring registration is wired properly.

## 11. Aggregation scope: tree and health group

### 11.1. Parent node receives child results

In the contributor tree, a composite branch receives child statuses, and its conclusion in turn propagates up to the parent node. The parent's aggregator does not automatically recover any leaf information that was already reduced.

For example, when using the same priority policy:

~~~text
root
├── primary: UP
└── partners: DEGRADED
    ├── delivery: UP
    └── payment: DEGRADED
~~~

If the policy recognizes DEGRADED and prioritizes it before UP, both partners and root can become DEGRADED.

With custom policies, you must test multi-level trees as well, not just flat status sets. Codes returned by an aggregator must remain meaningful when used as inputs at the parent node.

The framework collects the statuses of child results to build the Set for the aggregation step; see [HealthEndpointSupport 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### 11.2. Groups select inputs; aggregator selects conclusion

If you do not want a failure in an optional dependency to affect a specific serving view, you can design a health group with the appropriate member list. That is selecting the contributor set, distinct from changing how Status values are prioritized.

By default, a group inherits system health's aggregation and mapping settings, though it can have its own settings. Illustrative example if a group named `serving` truly needs a different policy:

~~~yaml
management:
  endpoint:
    health:
      group:
        serving:
          include: primary,remote
          status:
            order: down,out-of-service,degraded,unknown,up
            http-mapping:
              down: 503
              out-of-service: 503
              degraded: 503
~~~

This snippet is supplementary configuration, not part of the profiles run in section 9. Included IDs must exist. If a group-specific bean is needed, Spring Boot supports a qualifier matching the group name; do not use Spring bean `@Order` to express health status severity.

Do not alter system-wide policy just to fix one group's result without considering all other consumers of health. Liveness, readiness, and a diagnostic group have different purposes; one decision can lead to alerts, stopping traffic, or restarts depending on the monitoring system. Group rules are in the [health groups 3.3 documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

## 12. Usages that easily lead to wrong conclusions

| Practice | Problem |
| --- | --- |
| Treating the aggregator as majority voting | The input Set does not retain counts of each status |
| Assuming UNKNOWN always precedes UP | Boot 3.3 default places UP before UNKNOWN |
| Only adding a custom code in an indicator | The aggregator may not recognize that code yet |
| A list containing only DEGRADED and UP | Can drop DOWN from recognized codes |
| Only setting HTTP mapping for DEGRADED | Does not change whether DEGRADED is selected as root |
| Only setting `degraded: 503` in custom mapping | Does not automatically preserve standard failure mappings |
| Editing properties and forgetting a custom aggregator bean | The bean may not read that property |
| Sorting statuses alphabetically | Does not reflect the agreed health policy |
| Picking the first element in the Set | Result can depend on unguaranteed iteration order |
| Making network calls or mutating the registry in an aggregator | Mixes checking with conclusion policy, causing side effects |
| Using details to report errors while keeping status UP | Aggregator only receives status, does not interpret details fields |
| Testing the algorithm and assuming wiring is also right | Endpoint may be using another config or bean |

When results are unexpected, inspect along the chain: **contributors in scope → actual status of each node → active aggregator → its list or algorithm → HTTP mapper**.

If no response is received due to timeout/connection error, that is not the aggregator returning UNKNOWN. Distinguish an endpoint call failure from a valid health response.

## 13. Self-check

1. Why can UP with DEGRADED conclude UP by default, yet become DEGRADED after configuring order?
2. Why can two sets—one UP/one DOWN and many UPs/one DOWN—not be distinguished through the Set contract?
3. When wanting only to add DEGRADED to the policy, why must DOWN and OUT_OF_SERVICE still be explicitly listed?
4. Root is already DEGRADED yet HTTP is still 200: which layer should be inspected?
5. How does UNKNOWN caused by all unfamiliar codes being dropped differ from an indicator actively returning UNKNOWN?
6. If a custom bean does not read properties, what effect does changing `status.order` have on the bean's algorithm?
7. When a failure comes from an optional dependency, how should group membership be reviewed before changing the global aggregation policy?

You truly understand StatusAggregator when you can write out the expected result table in advance, choose complete inputs for each scope, and separately verify **the aggregation algorithm, bean wiring/usage, and HTTP mapping**.
