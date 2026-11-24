# Structure of status, components, and details in health responses

## 1. Reading health as a tree of check results

A health response is not just an "application is alive" flag. It can represent a tree: the whole system at the root, parts at the branches, and specific check results at the leaves.

Three fields to distinguish:

| Field | Question it answers |
| --- | --- |
| `status` | What health status does the node under consideration have? |
| `components` | Which child nodes make up this node? |
| `details` | What supplementary information explains this node's result? |

Short example:

~~~json
{
  "status": "UP",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "availableItems": 12
      }
    }
  }
}
~~~

Reading from outside in:

1. The overall status is `UP`.
2. There is a component named `inventory`.
3. That component is also `UP`.
4. The number `12` is supplementary data provided by the check, not a status code or health score.

This lesson uses **Spring Boot 3.3.x, Java 21, Servlet/Spring MVC, and the Actuator API V3 format**. The JSON payloads are intentional examples; other applications may have more or fewer components. The V3 structure is described in [Health API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

## 2. status always belongs to a specific scope

### 2.1. Status at the root and status at a component

For a `GET /actuator/health` request, the outermost `status` is the aggregated result for the contributors belonging to the health scope being evaluated.

For `GET /actuator/health/inventory`, the outermost `status` of the response belongs specifically to `inventory`. It does not turn into a whole-application check merely because the field name is still `status`.

Therefore, these two requests can simultaneously return:

~~~text
GET /actuator/health            -> HTTP 503, status DOWN
GET /actuator/health/inventory  -> HTTP 200, status UP
~~~

There is no contradiction if another part is `DOWN`. When reading a health JSON payload, first identify its URL and scope.

### 2.2. Standard statuses

| Status | Interpretation |
| --- | --- |
| `UP` | The check evaluates the part as functioning according to its criteria |
| `DOWN` | The check detected an unmet condition |
| `OUT_OF_SERVICE` | The evaluated part is currently out of service |
| `UNKNOWN` | No known matching status conclusion |

`UP` only has meaning within the limits of what was checked. An indicator checking a successful connection does not prove every query or every business workflow is correct.

`UNKNOWN` does not mean "checked and definitely good". It also does not automatically equate to HTTP 503.

Statuses are not scores to be summed or averaged. With Spring Boot 3.3's default aggregator, the priority order is:

~~~text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
~~~

The status prioritized earliest among recognized statuses is selected. Examples:

| Child statuses | Default aggregated status |
| --- | --- |
| UP, UP | UP |
| UP, DOWN | DOWN |
| UP, OUT_OF_SERVICE | OUT_OF_SERVICE |
| UP, UNKNOWN | UP |
| UNKNOWN, UNKNOWN | UNKNOWN |

In particular, `UP` together with `UNKNOWN` does not default to `UNKNOWN`. If operational requirements need a different rule, define it explicitly rather than inferring it from the English word. The default order can be verified in [SimpleStatusAggregator 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Applications can create custom statuses such as `DEGRADED`. In that case, both aggregation order and HTTP mapping must be considered; merely creating a new status string does not make the system understand its severity.

### 2.3. status in JSON is distinct from HTTP code

`status: "DOWN"` is Actuator data; `503` is the HTTP response code.

Under the default mapping:

| Health status | HTTP |
| --- | --- |
| UP | 200 |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UNKNOWN | 200 |

Two independent rules execute in sequence: aggregating the health status, then mapping that status to HTTP. Do not infer that every HTTP 200 means business readiness to serve traffic.

If you configure `status.http-mapping` yourself, the default mappings for DOWN and OUT_OF_SERVICE are no longer preserved automatically; you must re-declare them if you want to keep them. This rule is covered in the [health HTTP mapping documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators). The API responsible for mapping is [HttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

401, 403, or 404 may instead reflect access permissions or a resource not found; do not treat them as health status values.

## 3. components is a tree structure, not a fixed list

`components` is a JSON object whose keys are component names. Each component in turn has `status`; a composite component can have its own `components`:

~~~json
{
  "status": "DOWN",
  "components": {
    "inventory": {
      "status": "UP"
    },
    "partners": {
      "status": "DOWN",
      "components": {
        "payments": {
          "status": "UP"
        },
        "courier": {
          "status": "DOWN"
        }
      }
    }
  }
}
~~~

Corresponding tree:

~~~text
entire system: DOWN
├── inventory: UP
└── partners: DOWN
    ├── payments: UP
    └── courier: DOWN
~~~

`partners` is a composite node. It does not mean a single indicator sent requests to both partners using some special algorithm; in the example, it simply organizes two child contributors.

The status of `courier` feeds into the aggregation of `partners`; the status of `partners` in turn feeds into the aggregation at the root. Do not count UP nodes and vote: three UP nodes do not "beat" one DOWN node.

### Where do component names come from?

A `HealthIndicator` is a check returning `Health`. `CompositeHealthContributor` organizes multiple named child contributors. This is the tree-building model, not JSON fields manually assembled by a controller.

With a bean named `inventoryHealthIndicator`, Spring Boot convention strips the `HealthIndicator` suffix, so the ID is `inventory`. With a composite contributor, child names are determined by its registration structure. The composite concept is described in [CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Do not assume every application has `db`, `redis`, `diskSpace`, or fixed child names. Which entries appear depends on dependencies, beans, configuration, the registry, and the queried health scope. Renaming a bean can also change the path and contract that monitoring software relies on.

### Do not confuse component with health group

A component is a node in the contributor tree. A health group is a view selecting a subset of contributors for a specific purpose. Both can use URLs under `/actuator/health`, but they are not the same concept.

If the response also has a `groups` field, that is information about configured groups, not content replacing `components`. Reading liveness/readiness must rely on the right group and that group's criteria; do not infer from any UP value at an arbitrary URL.

## 4. details is explanatory data, not automatically aggregated

A leaf node usually has `status` and may have `details`:

~~~json
{
  "status": "DOWN",
  "details": {
    "reason": "simulated timeout",
    "region": "lab"
  }
}
~~~

Keys such as `reason`, `region`, `availableItems`, `database`, or `threshold` are not a universal set of fields that every health response must have. Whatever data an indicator provides is decided by that indicator's detail contract.

`details` can contain strings, numbers, booleans, arrays, or suitably serializable objects. It may be absent because there is no data or because policy does not allow showing it. Do not require every node to have `details: {}`.

### A DOWN string in details does not make the status DOWN

Consider the following result:

~~~json
{
  "status": "UP",
  "details": {
    "reportedStatus": "DOWN"
  }
}
~~~

Structurally, this is still a Health with status `UP`. `reportedStatus` is simply data named by the indicator author. The aggregator does not scan every string at every JSON level looking for the word DOWN.

Code producing the actual status must use the builder or equivalent mechanism, such as `Health.down()`. If an error was detected yet `Health.up().withDetail("error", "...")` was still returned, the indicator itself is reporting the wrong status, not Actuator ignoring a standard field.

Similarly, placing a map named `components` inside `details` does not create child contributors. To have a real health tree, register contributors/composites. The [Health](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html) class clearly separates status and the details map.

### Explanatory data can also be sensitive

File paths, hostnames, connection errors, and exception messages can aid investigation but also disclose infrastructure. Do not put passwords, access tokens, user content, or entire configurations into details.

Hiding details is a result presentation policy. It does not turn a broken check into a passing one, does not disable the indicator, and does not fix secrets already written to logs.

## 5. Why is only status visible sometimes?

Two separate properties control the level of information returned:

- `management.endpoint.health.show-components`: whether to show component structure.
- `management.endpoint.health.show-details`: whether to show explanatory data of results.

The main values are `never`, `always`, `when-authorized`. To make intent clear and avoid relying on inferred values across settings, the lab sets both explicitly.

| show-components | show-details | Illustrative view at root URL |
| --- | --- | --- |
| never | never | Overall status only |
| always | never | Component tree and statuses, without details |
| always | always | Component tree along with explanatory data if present |
| when-authorized | when-authorized | Information level depends on whether caller is authorized |

Example returning only:

~~~json
{
  "status": "DOWN"
}
~~~

That does not mean the system has no contributors or that indicators did not run. The failure result is still computed; only the tree and explanatory data are hidden.

With `when-authorized`, `management.endpoint.health.roles` must be considered; if roles are not set, any authenticated user can be considered authorized. Information visibility policy does not replace Spring Security URL access rules.

In Boot 3.3, if showing components is not allowed, a direct request to a component path also does not simply "bypass to view details": the endpoint does not provide a result for that sub-path. In this lesson's example, `/actuator/health/inventory` returns 404 when `show-components: never`, even though the indicator exists. You can inspect the path-handling condition in [HealthEndpointSupport 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

When additional security layers or proxies are present, the returned status code may be altered before reaching the endpoint. Thus, 404 is a signal to check alongside configuration, not sole proof that a bean does not exist.

## 6. Hands-on: a single node and a composite branch

The goal is to see the same check suite under three visibility levels, then observe a failure at one leaf propagate up to the parent node. No database or external service is required; all results are stable simulated data.

### 6.1. Preparing the project

Use a minimal Spring Boot 3.3.x project with the Spring Boot plugin, dependency management, Java 21, and Gradle Wrapper. Required dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This example does not add Spring Security; the application only listens on loopback and only exposes health. If added to a project that already has security, it must satisfy that project's access policy.

Create `src/main/java/com/example/healthshape/HealthShapeApplication.java`:

~~~java
package com.example.healthshape;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HealthShapeApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthShapeApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/healthshape/LabHealthContributors.java`:

~~~java
package com.example.healthshape;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LabHealthContributors {
    @Bean
    HealthIndicator inventoryHealthIndicator() {
        return () -> Health.up()
            .withDetail("availableItems", 12)
            .withDetail("source", "simulated")
            .build();
    }

    @Bean
    CompositeHealthContributor partners(
            @Value("${lab.courier-down:false}") boolean courierDown) {
        HealthIndicator payments = () -> Health.up()
            .withDetail("provider", "sandbox")
            .build();

        HealthIndicator courier = () -> {
            if (courierDown) {
                return Health.down()
                    .withDetail("reason", "simulated timeout")
                    .withDetail("region", "lab")
                    .build();
            }
            return Health.up()
                .withDetail("region", "lab")
                .build();
        };

        return CompositeHealthContributor.fromMap(Map.of(
            "payments", payments,
            "courier", courier
        ));
    }
}
~~~

Bean `inventoryHealthIndicator` becomes ID `inventory`; bean `partners` is a composite branch. The two variables `payments` and `courier` are not registered as standalone root health beans; they are placed inside the composite.

`courierDown` is read when the bean is created. Changing an environment variable after startup does not automatically update the value in the example; restart with the new configuration.

### 6.2. Summary view configuration

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
      show-components: never
      show-details: never
      probes:
        enabled: false
  health:
    defaults:
      enabled: false

lab:
  courier-down: false
~~~

Disabling the default auto-configured indicators keeps the example independent of disk space or external dependencies. It does not remove the two contributors declared by the lesson. Automatic probe groups are also disabled to focus on observing the tree being studied.

Run from PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal:

~~~powershell
$response = Invoke-WebRequest -UseBasicParsing `
    -Uri 'http://127.0.0.1:8080/actuator/health' `
    -Headers @{ Accept = 'application/vnd.spring-boot.actuator.v3+json' }
$response.StatusCode
$response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10
~~~

The HTTP code is `200`; the JSON content is semantically equivalent to:

~~~json
{
  "status": "UP"
}
~~~

Indentation and key ordering are not part of the result to assert.

### 6.3. Enabling the tree and explanatory information in a local profile

Create `src/main/resources/application-health-tree.yml`:

~~~yaml
management:
  endpoint:
    health:
      show-components: always
      show-details: always
~~~

Stop the previous run with Ctrl+C and run:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=health-tree"
~~~

Call the health URL again with Accept V3. When `lab.courier-down=false`, the JSON result is:

~~~json
{
  "status": "UP",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "availableItems": 12,
        "source": "simulated"
      }
    },
    "partners": {
      "status": "UP",
      "components": {
        "payments": {
          "status": "UP",
          "details": {
            "provider": "sandbox"
          }
        },
        "courier": {
          "status": "UP",
          "details": {
            "region": "lab"
          }
        }
      }
    }
  }
}
~~~

The order of `payments` and `courier` is not guaranteed because the example uses `Map.of`; check by key rather than comparing JSON strings by order.

Each scope can be queried individually:

| URL | Response shape |
| --- | --- |
| `/actuator/health` | Root status and components |
| `/actuator/health/inventory` | Inventory status and its details |
| `/actuator/health/partners` | Partners status and child components |
| `/actuator/health/partners/courier` | Courier status and its details |

A leaf URL does not wrap the entire parent path. With courier UP, it returns:

~~~json
{
  "status": "UP",
  "details": {
    "region": "lab"
  }
}
~~~

### 6.4. Keeping the tree while hiding details

Stop the previous run and restart:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=health-tree --management.endpoint.health.show-details=never"
~~~

Now the root still has inventory and partners with their statuses; the details fields of the leaves do not appear. The absence of details on the leaves does not prove they stopped checking.

Querying `/actuator/health/inventory` still returns a result because `show-components=always`, but the content is only:

~~~json
{
  "status": "UP"
}
~~~

### 6.5. Making a leaf DOWN

Restart with:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=health-tree --lab.courier-down=true"
~~~

Then:

~~~text
/actuator/health                   -> HTTP 503, status DOWN
/actuator/health/partners          -> HTTP 503, status DOWN
/actuator/health/partners/courier  -> HTTP 503, status DOWN
/actuator/health/inventory         -> HTTP 200, status UP
~~~

The response for courier alone is:

~~~json
{
  "status": "DOWN",
  "details": {
    "reason": "simulated timeout",
    "region": "lab"
  }
}
~~~

`Invoke-WebRequest` commands may throw an error when receiving 503. You can inspect both headers and body without PowerShell branching into an exception by using real curl:

~~~powershell
curl.exe -i `
    -H "Accept: application/vnd.spring-boot.actuator.v3+json" `
    http://127.0.0.1:8080/actuator/health
~~~

Read the HTTP status line and the status field in the body separately. Do not use `curl` without the `.exe` extension and assume every PowerShell session invokes the same program.

Finally, run summary mode again while the failure remains:

~~~powershell
.\gradlew.bat bootRun --args="--lab.courier-down=true"
~~~

The root returns HTTP 503 with `{"status":"DOWN"}`. The tree is hidden, yet the failure still affects the aggregated result. This is direct proof that **visibility policy is not status calculation policy**.

## 7. Testing structural contracts instead of JSON order

The test files below are placed in `src/test/java/com/example/healthshape/`. They use MockMvc to check schema and scope, without calling external services.

### 7.1. Full tree with one failing leaf

`HealthTreeTest.java`:

~~~java
package com.example.healthshape;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoint.health.show-components=always",
    "management.endpoint.health.show-details=always",
    "lab.courier-down=true"
})
@AutoConfigureMockMvc
class HealthTreeTest {
    private static final String V3 =
        "application/vnd.spring-boot.actuator.v3+json";

    @Autowired MockMvc mvc;

    @Test
    void failureFlowsFromLeafToRoot() throws Exception {
        mvc.perform(get("/actuator/health").accept(V3))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.components.inventory.status").value("UP"))
            .andExpect(jsonPath("$.components.partners.status").value("DOWN"))
            .andExpect(jsonPath(
                "$.components.partners.components.courier.status"
            ).value("DOWN"))
            .andExpect(jsonPath(
                "$.components.partners.components.courier.details.reason"
            ).value("simulated timeout"));
    }

    @Test
    void healthyLeafKeepsItsOwnScope() throws Exception {
        mvc.perform(get("/actuator/health/inventory").accept(V3))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("UP"))
            .andExpect(jsonPath("$.details.availableItems").value(12))
            .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void compositeEndpointReturnsItsChildren() throws Exception {
        mvc.perform(get("/actuator/health/partners").accept(V3))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.components.courier.status").value("DOWN"))
            .andExpect(jsonPath("$.components.payments.status").value("UP"));
    }

    @Test
    void aDetailValueDoesNotChangeActualStatus() {
        Health health = Health.up()
            .withDetail("reportedStatus", "DOWN")
            .build();

        assertEquals(Status.UP, health.getStatus());
        assertEquals(Status.UP, new SimpleStatusAggregator()
            .getAggregateStatus(Set.of(health.getStatus())));
    }
}
~~~

### 7.2. Showing overall status only

`HealthSummaryTest.java`:

~~~java
package com.example.healthshape;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoint.health.show-components=never",
    "management.endpoint.health.show-details=never",
    "lab.courier-down=true"
})
@AutoConfigureMockMvc
class HealthSummaryTest {
    @Autowired MockMvc mvc;

    @Test
    void hidingStructureDoesNotHideFailureStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.components").doesNotExist())
            .andExpect(jsonPath("$.details").doesNotExist());
    }

    @Test
    void componentPathIsUnavailableWhenComponentsAreHidden()
            throws Exception {
        mvc.perform(get("/actuator/health/inventory"))
            .andExpect(status().isNotFound());
    }
}
~~~

### 7.3. Showing the tree while hiding explanatory data

`HealthComponentsOnlyTest.java`:

~~~java
package com.example.healthshape;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoint.health.show-components=always",
    "management.endpoint.health.show-details=never",
    "lab.courier-down=true"
})
@AutoConfigureMockMvc
class HealthComponentsOnlyTest {
    @Autowired MockMvc mvc;

    @Test
    void statusesRemainVisibleWithoutDetails() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.components.inventory.status").value("UP"))
            .andExpect(jsonPath(
                "$.components.inventory.details"
            ).doesNotExist())
            .andExpect(jsonPath(
                "$.components.partners.components.courier.status"
            ).value("DOWN"))
            .andExpect(jsonPath(
                "$.components.partners.components.courier.details"
            ).doesNotExist());
    }

    @Test
    void leafPathWorksWithoutDetails() throws Exception {
        mvc.perform(get("/actuator/health/partners/courier"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.details").doesNotExist());
    }
}
~~~

Run all eight tests:

~~~powershell
.\gradlew.bat test --tests "com.example.healthshape.Health*Test"
~~~

All eight are expected to pass with the exact minimal project described. The tests do not pin key order, disk space, startup log content, or external service state.

If applying these tests to a project with Spring Security, custom groups, or additional contributors, account for differences before concluding Actuator returned the wrong output.

## 8. How monitoring software should read responses

A health reader needs to know what level of conclusion it requires:

1. Identify the exact endpoint and scope: whole system, group, or component.
2. Read the HTTP code according to the configured contract.
3. Read the actual status of the corresponding node.
4. If diagnosis is needed, descend into `components` by name and handle missing fields.
5. Only read `details` according to each indicator's contract; do not assume a single detail schema applies to all nodes.

Do not compare the entire response as a string. JSON key ordering carries no tree meaning or severity meaning. A resilient reader needs to distinguish:

- A `status` field is present with value UNKNOWN.
- Showing `components` is not allowed.
- The target component is no longer registered.
- Access to the endpoint is denied.
- No response was received due to a connection error or timeout.

No response is not a `{"status":"DOWN"}` response. It is a different operational signal that monitoring systems must handle explicitly.

Receiving UP once is also not a permanent guarantee. The result reflects the evaluation within the selected scope; load, connectivity, or data may change afterwards. If caching is configured at the endpoint or proxy, data freshness must also be considered.

## 9. Common misconceptions

| Claim | What to fix |
| --- | --- |
| Root UP means all business logic is verified | UP is based only on the contributors in scope and the current criteria |
| `components` is an array | It is an object keyed by component name |
| Every node must have details | Details may be empty, omitted, or hidden |
| A composite node must contain details of every child | Each child's information resides in its corresponding `components` tree |
| Hiding details prevents failures from affecting the root | Status aggregation still takes place |
| HTTP 200 always equals status UP | UNKNOWN also maps to 200 by default; custom mappings may exist |
| Having multiple UP nodes means the root must be UP | The aggregator follows status ordering, not voting |
| A DOWN string inside details automatically makes the root DOWN | Only the actual status of the health result participates in aggregation |
| Not seeing `db` means the database is definitely broken | There may be no indicator, it may be disabled, or it may be outside the scope |
| A component URL is always accessible if you guess its name correctly | It also depends on component visibility and security layers |
| Liveness, readiness, and root health always mean the same thing | Their scopes and purposes can differ |

When diagnosing, ask in order: which URL, which contributors, which visibility policy, which aggregator, and which HTTP mapping. Do not fix a missing field by opening all details before understanding the cause.

## 10. Self-check

1. In the `partners` tree, only `courier` is DOWN: what are the statuses of `partners` and root by default?
2. Why does `inventory` still return HTTP 200 when the root returns 503?
3. The root only shows `{"status":"DOWN"}`: can you conclude there are no components?
4. `details.reportedStatus` is DOWN while the outermost status is UP: which value does the aggregator use?
5. To show component names and statuses without showing paths or detailed errors, which configuration do you choose?
6. Why is testing with JSONPath by key better suited than comparing the full JSON string?
7. When receiving 404 on a component URL, what conditions should be checked besides whether the bean exists?

The goal is to read three distinct layers of information: **status gives the conclusion at a node, components describes the structure of child nodes, and details provides explanatory data without deciding the conclusion on its own**.
