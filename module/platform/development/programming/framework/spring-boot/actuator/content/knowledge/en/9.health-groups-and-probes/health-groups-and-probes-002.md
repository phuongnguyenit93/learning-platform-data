# Selecting Child Components of a Composite Indicator and Validating Membership

This lesson uses Spring Boot 3.3.13 and Java 21. The goal is to select the right branch in a health check tree, understand the group's status after selection, and catch configurations that reference nonexistent members.

## 1. Understanding the Problem: One Check Tree, Multiple Observation Goals

An application may check multiple dependent systems. A single system may itself have multiple components: for example, a billing service has a primary node and a replica. If everything is combined into a single overall status, a replica failure can obscure the answer we actually need: can the order-processing flow still use its required components?

In Actuator, a leaf check typically implements `HealthIndicator` and returns `Health`. A node containing multiple checks is represented by `CompositeHealthContributor`. A health group selects members from this tree to produce a result for a dedicated purpose. `CompositeHealthContributor.fromMap(...)` builds a composite node from named entries in a `Map`. [CompositeHealthContributor 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Consider the following illustrative tree; statuses are fixed for easy verification:

```text
backends                         CompositeHealthContributor
├── inventory                    HealthIndicator → UP
└── billing                      CompositeHealthContributor
    ├── primary                  HealthIndicator → UP
    └── replica                  HealthIndicator → DOWN
```

`backends` is the root-level ID. `inventory` and `billing` are its direct child names; `primary` and `replica` are child names of `billing`. Node name and status are two separate pieces of information: `replica` still validly exists even while reporting `DOWN`.

Three questions may require three different member sets:

| Purpose | Leaves to evaluate | Result in the example |
| --- | --- | --- |
| Order placement flow `checkout` | `inventory` and `billing/primary` | `UP` |
| Full observation of the `billing` branch | `primary` and `replica` | `DOWN` |
| Observing only the required part of `billing` | Select `billing`, then exclude `replica` | `UP` |

A group does not duplicate checks and does not alter the underlying results. It defines the member set that participates in that specific group's result.

## 2. Member Paths Run from the Root to the Target Node

Configuration paths join node names with `/`:

```text
backends
backends/inventory
backends/billing
backends/billing/primary
backends/billing/replica
```

`backends/billing` refers to a composite node; `backends/billing/primary` refers to a leaf. If you select a composite node, the leaves beneath it fall within the selection scope, except for any removed by `exclude`. Spring Boot supports selecting or excluding part of a composite by full path. [Health Groups — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

This path starts from the health contributor registry. When descending one level, the framework looks up the child name in the container holding named members; `NamedContributors.getContributor(name)` returns `null` if not found. [NamedContributors API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/NamedContributors.html).

Therefore, distinguish the following strings:

| String | Meaning or issue |
| --- | --- |
| `backends/billing/primary` | Valid member path in the illustrative tree |
| `primary` | Looks only for a root-level contributor named `primary`; does not search for every leaf with that name |
| `backends.billing.primary` | Does not represent three levels in the tree using the `/` syntax |
| `/actuator/health/backends/billing/primary` | Query URL, not a member value to put in `include` |
| `com.example.health.PrimaryHealthIndicator` | Java class name, not a path in the registry |
| `backends/billing/primary/status` | `status` is result data; not a child contributor of the `primary` leaf |

Do not treat JSON presentation keys such as `components` or `details` as segments of the path. For example, `components/backends/components/billing` is not a member path.

In the runnable example below, the bean is explicitly named `backends`, and child names come directly from the `Map` keys. When working with existing contributors in another application, check the actual registered IDs rather than inferring them from class names.

## 3. Using include and exclude to Select the Right Check Set

### 3.1. Selecting Two Specific Leaves

The following configuration creates the `checkout` group:

```properties
management.endpoint.health.group.checkout.include=backends/inventory,backends/billing/primary
```

The two entries in `include` are two independent paths. Commas separate members; `/` separates levels within a path. This group does not take the `replica` leaf.

The YAML equivalent of that exact configuration is:

```yaml
management:
  endpoint:
    health:
      group:
        checkout:
          include:
            - "backends/inventory"
            - "backends/billing/primary"
```

Choose one configuration format for the application to avoid duplicate declarations. In `.properties` files, paths can be written directly as shown, without quotes around the values.

### 3.2. Selecting an Entire Branch

```properties
management.endpoint.health.group.billing.include=backends/billing
```

With the tree under consideration, the `billing` group takes both `primary` and `replica`. Because `replica=DOWN`, this group reports `DOWN` under the default status aggregation mechanism.

### 3.3. Selecting a Branch and Excluding One Leaf

```properties
management.endpoint.health.group.billingPrimary.include=backends/billing
management.endpoint.health.group.billingPrimary.exclude=backends/billing/replica
```

`exclude` removes the matched part even though it sits under the branch selected by `include`. Here, only `primary` participates in the `billingPrimary` result. There is no need to modify the `replica` `HealthIndicator` to achieve this view.

### 3.4. Broad Selection vs. Explicit Leaf Selection Have Different Consequences

Suppose the `backends/billing/archive` leaf is added later. A group that selects the entire `backends/billing` branch will pick up that new leaf unless an appropriate exclusion rule exists. A group that lists only `backends/billing/primary` keeps a narrower scope. This is a design decision: does the group need to monitor the whole branch, or a clearly bounded set of dependencies?

The `*` value used to select everything also creates a broad scope. In YAML, `"*"` must be quoted. This lesson uses explicit paths to make clear which members are required; do not assume patterns like `backends/*/primary` are supported path-matching syntax.

Also separate two easily confused settings: `management.endpoints.web.exposure.include=health` exposes the health endpoint over HTTP, whereas `management.endpoint.health.group.checkout.include=...` selects members inside the group. Selecting members does not configure the entire HTTP access mechanism.

## 4. When Does Membership Validation Happen?

### 4.1. Validated by Default at Startup

```properties
management.endpoint.health.validate-group-membership=true
```

In Spring Boot 3.3, this property defaults to `true`. It applies at the health endpoint level, not under a specific group. If a group references a nonexistent contributor in `include` or `exclude`, default validation causes startup to fail. [Actuator 3.3 properties reference](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator.management.endpoint.health.validate-group-membership).

For the explicit path `backends/billing/primary`, the validation step can be understood as:

```text
registry
  → look up backends
  → look up billing in backends
  → look up primary in billing
  → confirm final contributor is found
```

Missing a name at any level makes the path invalid. Attempting to traverse past a leaf, such as appending `/status` after `primary`, is also invalid because that leaf contains no child contributors.

In this version, the validation mechanism runs after singletons are initialized, iterates through group configurations, and looks up paths in the registry. It does not invoke health checks to decide whether member names are valid. [Validation source in HealthEndpointConfiguration 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

### 4.2. Valid Membership and Being Healthy Are Two Different Things

| Case | Membership validation | When querying the group |
| --- | --- | --- |
| `backends/billing/primary` exists, returns `UP` | Passes | Member contributes `UP` |
| `backends/billing/replica` exists, returns `DOWN` | Passes | Member contributes `DOWN` if selected |
| Typo `backends/billing/primray` | Fails with default validation | Application fails to start |
| Name in `exclude` does not exist | Also fails with default validation | Must fix the name or adjust environment configuration |

Passing membership validation only proves that the path exists at validation time. It does not prove the group covers all dependencies required by business logic. For example, selecting only `inventory` is a valid configuration by name, but it may miss the billing check that the order placement flow requires.

### 4.3. Disabling Validation Does Not Fix a Missing Member

```properties
management.endpoint.health.validate-group-membership=false
```

Setting `false` skips the membership validation gate at startup. It does not register the missing contributor, does not fix typos, and does not turn a `DOWN` result into `UP`.

With `include=backends/inventory,backends/billing/primray`, if validation is disabled, the group may still return `UP` because of `inventory`, while the intended `primary` check is omitted. That green result is not enough to conclude the configuration is correct.

In applications where contributors depend on profiles, libraries, or bean conditions, align group configuration with the actual environment. Prefer declaring appropriate member sets per profile and keeping validation enabled. If a design registers contributors dynamically after validation runs, disabling validation must be paired with a separate verification ensuring the required member set actually appears.

## 5. Complete Standalone Runnable Example

The example below is a standalone Maven project for learning the mechanism, requiring no database or external services. The indicators return fixed statuses; they do not connect to real systems. You need JDK 21, Maven, and network access for the initial library download.

### 5.1. File Structure

```text
composite-health-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/health/CompositeHealthDemoApplication.java
    └── resources/application.properties
```

### 5.2. pom.xml

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
    <groupId>com.example</groupId>
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

Version 3.3.13 is pinned to match the behavior in this lesson. `spring-boot-starter-web` provides the Servlet web application; `spring-boot-starter-actuator` provides the health endpoint. Spring Security is not added to this minimal project.

### 5.3. CompositeHealthDemoApplication.java

```java
package com.example.health;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompositeHealthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompositeHealthDemoApplication.class, args);
    }

    @Bean(name = "backends")
    CompositeHealthContributor backends() {
        Map<String, HealthContributor> billing = new LinkedHashMap<>();
        billing.put("primary", fixed(true));
        billing.put("replica", fixed(false));

        Map<String, HealthContributor> backends = new LinkedHashMap<>();
        backends.put("inventory", fixed(true));
        backends.put("billing", CompositeHealthContributor.fromMap(billing));
        return CompositeHealthContributor.fromMap(backends);
    }

    private static HealthIndicator fixed(boolean available) {
        return () -> available ? Health.up().build() : Health.down().build();
    }
}
```

`fixed(true)` creates an `UP` leaf; `fixed(false)` creates a `DOWN` leaf. Two `fromMap(...)` calls create two levels of composite nodes. Both `billing` and `backends` have type `Map<String, HealthContributor>`, so they can hold both leaves and composite nodes. The leaves inside the maps are not separate beans additionally registered at the root level.

`LinkedHashMap` makes the initialization structure easier to read; property ordering in JSON is not a contract to rely on. What needs to be verified are the member names, nested structure, and statuses.

### 5.4. application.properties

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.validate-group-membership=true
management.endpoint.health.group.checkout.include=backends/inventory,backends/billing/primary
management.endpoint.health.group.billing.include=backends/billing
management.endpoint.health.group.billingPrimary.include=backends/billing
management.endpoint.health.group.billingPrimary.exclude=backends/billing/replica
```

`server.address=127.0.0.1` restricts the example to the local machine. `show-components=always` lets you observe the member structure in the response. That is an observation condition for the example; it does not select members itself. In a real deployment, visibility and access-control settings must align with what is allowed to be exposed.

### 5.5. Compiling and Running

In the directory containing `pom.xml`, run:

```shell
mvn clean package
java -jar target/composite-health-demo-1.0.0.jar
```

Keep the application process running and open a second terminal. By default the example uses port 8080. If that port is already in use, you can pass `--server.port=8081` when running and update the URLs accordingly. This program uses Spring libraries, so compile with a Maven-managed classpath; running bare `javac` on a single file will miss dependencies.

## 6. Observing the Result After Member Selection

### 6.1. The checkout Group Retains Parent Nodes to Represent the Tree

Query:

```shell
curl -i http://127.0.0.1:8080/actuator/health/checkout
```

In PowerShell, you can use `curl.exe -i ...` to invoke the actual curl executable. The expected response has HTTP status `200`; the JSON body below is formatted with line breaks for readability, and property order is not guaranteed:

```json
{
  "status": "UP",
  "components": {
    "backends": {
      "status": "UP",
      "components": {
        "billing": {
          "status": "UP",
          "components": {
            "primary": {
              "status": "UP"
            }
          }
        },
        "inventory": {
          "status": "UP"
        }
      }
    }
  }
}
```

The group keeps `backends` and `billing` as organizing nodes. Selecting a leaf does not promote that leaf to a root-level member in JSON. `replica` is absent from the result tree of `checkout`.

Actuator filters contributions according to group membership and aggregates status over what remains. Therefore, `billing` inside the `checkout` response reports `UP`: in this view, only `primary` is present. This is the result of the filtered branch. [HealthEndpointSupport 3.3.13 source](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### 6.2. Comparing the Same Tree Across Three Groups

```shell
curl -i http://127.0.0.1:8080/actuator/health/billing
curl -i http://127.0.0.1:8080/actuator/health/billingPrimary
```

| URL | Participating leaf members | Status | Default HTTP code in example |
| --- | --- | --- | --- |
| `/actuator/health/checkout` | `inventory`, `primary` | `UP` | `200` |
| `/actuator/health/billing` | `primary`, `replica` | `DOWN` | `503` |
| `/actuator/health/billingPrimary` | `primary` | `UP` | `200` |

The table assumes unchanged status aggregator and status-to-HTTP mapping. Member set, aggregation rules, and HTTP codes are three layers to distinguish when diagnosing a customized application.

Try querying a leaf that does not belong to the group:

```shell
curl -i http://127.0.0.1:8080/actuator/health/checkout/backends/billing/replica
```

With the example's component visibility configuration, the result is HTTP `404`. The `replica` contributor exists in the overall tree, but it is not a member of `checkout`. Thus, seeing a `404` alone is not enough to conclude the bean was never created; you must consider both the queried group and visibility settings.

## 7. Testing Configuration Errors to See the Validation Gate in Action

### 7.1. Misspelling a Name in include

Stop the application with Ctrl+C. Restart with an override argument intentionally misspelling `primary` as `primray`:

```shell
java -jar target/composite-health-demo-1.0.0.jar --management.endpoint.health.group.checkout.include=backends/billing/primray
```

The application fails to start. The diagnostic message contains the following text; timestamps and surrounding log lines depend on the environment:

```text
Included health contributor 'backends/billing/primray' in group 'checkout' does not exist
```

Fix the path back to `backends/billing/primary` or restore the original configuration. There is no need to change the `primary` check itself, because the error is in the member name.

### 7.2. Misspelling a Name in exclude Is Also an Error

```shell
java -jar target/composite-health-demo-1.0.0.jar --management.endpoint.health.group.billingPrimary.exclude=backends/billing/repilca
```

In this run, `replica` is misspelled as `repilca`. The application also fails to start. This is helpful because if a misspelled exclusion name were silently ignored, the intended excluded member would remain active and cause the group to report an unintended status.

### 7.3. Control Run with Validation Disabled

Run a new process with both arguments below:

```shell
java -jar target/composite-health-demo-1.0.0.jar --management.endpoint.health.validate-group-membership=false --management.endpoint.health.group.checkout.include=backends/inventory,backends/billing/primray
```

The application can start and `checkout` returns HTTP `200`, `status=UP`, but `components.backends.components` contains only `inventory`. The misspelled name does not create a billing check. This demonstrates that disabling membership validation can mask configuration errors.

Stop the test process and re-run the original command without override arguments to return to the valid configuration.

## 8. Diagnosing Errors at the Right Layer

| Symptom | What to check |
| --- | --- |
| Startup fails because a member does not exist | Check every `/` segment, root-level ID, child map keys, profiles, and contributor creation conditions |
| A name in exclude causes startup failure | Check against the actual tree; exclude also requires existing names when default validation is enabled |
| Group is UP but missing a required check | Compare the actual leaf set against requirements; check whether validation was disabled or the scope was too narrow |
| Group is DOWN because of an unnecessary leaf | Review the group's intent and whole-branch selection; adjust the member set if requirements actually allow it |
| `components` not visible in JSON | Check `show-components` and viewer permissions; hiding the tree does not prove the group is empty |
| Child URL returns 404 | Check path, group membership, and visibility policy; distinguish from a nonexistent contributor |
| One group is UP while another is DOWN on the same branch | Compare the selected leaf sets before suspecting aggregation |

Changing `show-components` or `show-details` only for observation is not a fix for member names. Changing HTTP status codes also does not fix the check set. Good troubleshooting starts with what question the group is meant to represent, then compares the contributor tree with the configuration.

In a probe context, add only members that are meaningful for the decision the probe will trigger. The example uses a dedicated `checkout` group to focus on branch selection techniques; do not treat it as a liveness or readiness probe for every system.

## 9. Practice and Self-Check

1. Change `checkout.include` to `backends/billing`. Predict the result and re-run. With the fixed data in the example, the group will contain both `primary` and `replica`, reporting `DOWN`/503.
2. Keep the whole-branch selection from question 1 and add `checkout.exclude=backends/billing/replica` under the proper `management.endpoint.health.group` prefix. The group keeps `primary`, reporting `UP`/200.
3. Change the include value to `backends/billing/primary/status`. With default membership validation, the application fails to start because it cannot traverse past the `primary` leaf to find a `status` contributor.
4. Keep the original example, but change `replica`'s `fixed(false)` to `fixed(true)`. Membership validation still passes as before; the `billing` group changes from `DOWN` to `UP`. This change belongs to the check result, not name validity.
5. Explain why disabling validation and seeing `checkout=UP` does not prove the group is complete. The answer should point out that an intended check may not have participated at all.

Before using a group as an operational signal, confirm that the path exists, the leaf set matches requirements, the aggregated status is appropriate, and observability allows verifying the configuration. In this example, what mattered was selecting `backends/billing/primary` accurately and keeping the startup mechanism that catches misspelled names.
