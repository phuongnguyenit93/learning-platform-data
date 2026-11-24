# Creating Health Groups and Selecting Members with `include` or `exclude`

> Scope: Spring Boot Actuator 3.3.x. The standalone example below uses Java 21, Spring Boot 3.3.0, and Gradle 8.5. Dependency checks are simulated to focus on member selection without needing to install a database or cache.

## 1. What Question Does a Health Group Answer?

An application may check its data store, payment gateway, and cache. However, operators do not always need a single combined answer for all three. If the cache only speeds up reads and the application can still handle requests by reading from the primary data source, a cache failure may warrant a separate alert rather than being interpreted as the entire business functionality being down.

A **health group** creates a named view over the registered health checks. You select the members of the group and query the aggregated status tailored to that specific purpose.

In this lesson's scenario:

| Component | Role in the scenario | Initial simulated status |
| --- | --- | --- |
| `primaryStore` | Primary data store | `UP` |
| `billingGateway` | Payment gateway | `UP` |
| `optionalCache` | Cache that can be bypassed on failure | `DOWN` |

We want to observe three questions:

- `business`: are the two selected business dependencies healthy?
- `noncache`: are the checks other than the cache healthy?
- `cacheOnly`: is the cache alone healthy?

`business` and `noncache` can return `UP` while `cacheOnly` and the overall health return `DOWN`. These are answers with different scopes; interpreting them correctly requires knowing which members belong to each group.

### Terms to Distinguish

- `HealthIndicator`: a check that provides a `Health` result, such as `UP` or `DOWN`.
- `HealthContributor`: the umbrella concept for a component that provides health information; it can be a single indicator or a composite structure containing multiple child components.
- Member ID: the name Actuator uses to identify a contributor, for example `optionalCache`.
- Group name: the name you configure to group contributors together, for example `business`.
- Group status: the aggregated result computed from the members belonging to the group.

With the default base path and no separate context path or management port, the `business` group is queried at `/actuator/health/business`. It is a group inside the `health` endpoint; there is no need to write a new Controller. [Spring Boot 3.3 Health Groups documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

## 2. Where Does Configuration Live and What Does It Select?

A group's configuration lives under:

```text
management.endpoint.health.group.<group-name>
```

Example explicitly selecting two members:

```yaml
management:
  endpoint:
    health:
      group:
        business:
          include:
            - primaryStore
            - billingGateway
```

`include` accepts the IDs of registered contributors. The configuration above does not create `primaryStore` or `billingGateway` itself; the application must provide those two contributors.

### `include`: Add Only the Selected Members to the Group

Use `include` when you want to express an explicit scope: exactly which checks belong to this business group. When a new indicator is added to the application, a group with an explicit `include` list does not automatically pick up that indicator.

### `exclude`: Remove Members from the Selected Set

If `include` is not declared, the group considers all contributors and then removes the IDs listed in `exclude`:

```yaml
management:
  endpoint:
    health:
      group:
        noncache:
          exclude:
            - optionalCache
```

In the initial scenario, the group keeps `primaryStore` and `billingGateway`. If the application later registers another contributor that is not excluded, the scope of `noncache` can expand.

### Combining Both Properties

```yaml
management:
  endpoint:
    health:
      group:
        narrowed:
          include:
            - primaryStore
            - billingGateway
          exclude:
            - billingGateway
```

`narrowed` ends up with only `primaryStore`: an ID appearing in both lists is excluded. You can think of this as two steps: select the initial set using `include`, then subtract using `exclude`; the order of the two keys in YAML does not determine precedence.

For the flat contributors in this lesson, let `U` be the set of actually registered IDs:

```text
Initial set   = U                         if include is not declared
              = U                         if include selects "*"
              = the IDs selected by include  if an explicit list is given

Group members = initial set minus the IDs excluded by exclude
```

Configured IDs must also pass the existence check at startup. This formula helps reason about member selection; it does not replace status aggregation rules.

| Configuration in the scenario with three initial IDs | Selected members |
| --- | --- |
| `include: [primaryStore, billingGateway]` | `primaryStore`, `billingGateway` |
| Only `exclude: [optionalCache]` | `primaryStore`, `billingGateway` |
| `include: "*"` and `exclude: [optionalCache]` | `primaryStore`, `billingGateway` |
| `include: [primaryStore, billingGateway]` and `exclude: [billingGateway]` | `primaryStore` |

`"*"` means select all; in YAML it must be wrapped in quotes to avoid being interpreted as alias syntax. Do not assume patterns such as `*Cache` or `db*` are supported name filters. When selecting a specific ID, use the exact name and exact letter casing.

## 3. How Does an Indicator ID Differ from a Group Name?

For an indicator bean with the `HealthIndicator` suffix, Actuator strips that suffix when forming the conventional ID:

| Bean in the example | ID used in `include`/`exclude` |
| --- | --- |
| `primaryStoreHealthIndicator` | `primaryStore` |
| `billingGatewayHealthIndicator` | `billingGateway` |
| `optionalCacheHealthIndicator` | `optionalCache` |

Therefore, configuring `include: primaryStoreHealthIndicator` will not match the `primaryStore` ID in this example. If you specify an explicit bean name, verify the actual ID instead of inferring it solely from the class name.

Names like `db` or `redis` are common in applications with the corresponding configuration, but installing Actuator does not guarantee all of those IDs exist. A profile that does not create a `DataSource` cannot assume `db` is already present.

`business` is a group name while `primaryStore` is a contributor ID. Do not use another group's name as a way to reuse a member list; groups can select the same contributor, but `include`/`exclude` take contributor IDs or child component paths.

## 4. Standalone Example: One Application, Three Health Scopes

The example uses three custom-defined indicators. There are no network connections to external dependencies; `optionalCache` gets its status from the `demo.cache-up` property.

### 4.1. Project Setup

Create a separate project directory with the following four files:

```text
health-group-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/HealthGroupDemo.java
    └── resources/application.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'health-group-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

These are fixed versions for the experiment. If applying this to an existing Spring Boot 3.3.x application, keep the application's build configuration and ensure the two required starters are present.

### 4.2. Providing the Checks

`src/main/java/demo/HealthGroupDemo.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthGroupDemo {
    public static void main(String[] args) {
        SpringApplication.run(HealthGroupDemo.class, args);
    }

    @Bean
    HealthIndicator primaryStoreHealthIndicator() {
        return () -> Health.up().build();
    }

    @Bean
    HealthIndicator billingGatewayHealthIndicator() {
        return () -> Health.up().build();
    }

    @Bean
    HealthIndicator optionalCacheHealthIndicator(
            @Value("${demo.cache-up:false}") boolean cacheUp) {
        return () -> cacheUp ? Health.up().build() : Health.down().build();
    }
}
```

The first two lambdas always report `UP`; the last lambda reports according to the property value at bean creation time. Change the property and restart the application to switch scenarios. These are not real database, payment gateway, or cache checks; in a real application, the indicator body must perform an appropriate check.

### 4.3. Creating the Groups

`src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  health:
    defaults:
      enabled: false
  endpoint:
    health:
      show-components: always
      group:
        business:
          include:
            - primaryStore
            - billingGateway
        noncache:
          exclude:
            - optionalCache
        cacheOnly:
          include:
            - optionalCache

demo:
  cache-up: false
```

Explanation of the experiment's choices:

- `management.health.defaults.enabled: false` disables default auto-configured indicators from Boot so the output depends only on the three sample beans. It does not disable the custom `HealthIndicator` beans defined above. You do not need to copy this setting into a real system just to create groups.
- `show-components: always` lets you see member names and statuses while learning. Showing components and showing details are two separate choices; in deployment, choose an appropriate visibility policy and access control.
- `business` uses an explicit allowlist; `noncache` uses an exclusion list; `cacheOnly` shows that one contributor can belong to multiple health views.
- `management.endpoints.web.exposure.include: health` exposes the `health` endpoint; it does not define group membership.

### 4.4. Running and Observing

In the project directory, with JDK 21 and Gradle 8.5:

```shell
gradle bootRun
```

If the project already has a matching Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows. The Java file above requires Spring Boot dependencies; it cannot be run with `javac HealthGroupDemo.java` on an empty classpath.

Wait for the application to finish starting, then open another terminal. The commands below use `curl.exe` on Windows; on Linux/macOS use `curl`:

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health/business
```

JSON output and HTTP status code:

```text
{"status":"UP","components":{"billingGateway":{"status":"UP"},"primaryStore":{"status":"UP"}}}
HTTP 200
```

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health/noncache
```

```text
{"status":"UP","components":{"billingGateway":{"status":"UP"},"primaryStore":{"status":"UP"}}}
HTTP 200
```

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health/cacheOnly
```

```text
{"status":"DOWN","components":{"optionalCache":{"status":"DOWN"}}}
HTTP 503
```

JSON key ordering is not a contract to rely on; compare member names, statuses, and HTTP status codes. This sample does not add Spring Security. When applied to a secured application, actual access depends on the application's security configuration.

Check overall health:

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health
```

Under the example's conditions, the overall result has `status: DOWN`, all three initial components, and status code `503`. It still sees `optionalCache`; excluding the cache from `noncache` does not exclude the cache from overall health.

### 4.5. Switching the Cache to Healthy

Stop the running process and restart it:

```shell
gradle bootRun --args="--demo.cache-up=true"
```

Call the four URLs again and compare:

| URL | `cache-up=false` | `cache-up=true` |
| --- | --- | --- |
| `/actuator/health` | `DOWN`, HTTP `503` | `UP`, HTTP `200` |
| `/actuator/health/business` | `UP`, HTTP `200` | `UP`, HTTP `200` |
| `/actuator/health/noncache` | `UP`, HTTP `200` | `UP`, HTTP `200` |
| `/actuator/health/cacheOnly` | `DOWN`, HTTP `503` | `UP`, HTTP `200` |

The member set does not change when the cache changes status. Only the results of views containing the cache change. This table assumes default aggregation and HTTP mapping policies, with no extra indicators or customizations.

## 5. Member Selection Is Distinct from Aggregation and Visibility

Read a health response in steps:

1. Which contributors does the group select via `include`/`exclude`?
2. What status do those contributors return on this check?
3. How does the group's status aggregator (`StatusAggregator`) decide the overall result?
4. Which HTTP status code is the result mapped to, and how much is the caller allowed to see?

By default, a group inherits aggregation and HTTP mapping settings from overall health unless customized individually. `include`/`exclude` determine the inputs; they do not redefine the meaning of `DOWN` or change data visibility permissions. [How groups are configured in Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

For example, hiding `components` does not stop a `DOWN` member from affecting the group. Conversely, excluding the cache from `noncache` prevents the cache's result from participating in aggregation for that group, without modifying the cache bean or the status of the `cacheOnly` group.

## 6. When to Use `include` vs. `exclude`?

| What needs to be expressed | Clear choice | Consequence to anticipate |
| --- | --- | --- |
| Group serves a specific decision based only on a few identified dependencies | Explicit `include` list | Adding a new indicator does not automatically expand the group |
| Diagnostic group wants to monitor everything except a few known components | `exclude`, or `include: "*"` with `exclude` | New indicators may automatically become members |
| A shared configuration needs to select a broad set and then exclude a subset | Use both and verify the final result | An ID in `exclude` is removed even if selected by `include` |

In the example, `business` and `noncache` currently have the same two members. If `searchIndex` is added to the registry:

- `business` still contains only the two listed IDs.
- `noncache` automatically picks up `searchIndex`, because only `optionalCache` is excluded.

If `searchIndex` reports a failure, the two groups can begin returning different statuses. Therefore, two configurations that produce the same result today may not carry the same meaning as the application evolves. When choosing how to configure a group, state clearly which operational question the group answers.

A health group also does not turn itself into an infrastructure probe. The deployer must select the proper URL and response policy. In particular, before using a group as a liveness or readiness signal, consider the impact of adding external dependencies; this lesson only builds the member set.

## 7. Wrong IDs, Conditional Members, and Empty Groups

### 7.1. Startup Existence Validation

By default, Spring Boot validates IDs declared in both `include` and `exclude`. If an ID does not exist, startup fails. For example, add or change:

```yaml
management:
  endpoint:
    health:
      group:
        business:
          include:
            - primaryStoreTypo
```

In the sample application, the error message includes:

```text
Included health contributor 'primaryStoreTypo' in group 'business' does not exist
```

This differs from an existing contributor returning `DOWN`: a misconfiguration can prevent the application from starting; a failing dependency is a check result from a running application.

For a contributor created only under a specific profile, place the corresponding group configuration in that profile or ensure the contributor exists in the target environment. Do not add the name of a planned service and assume Actuator will automatically create a check for it.

### 7.2. Disabling Validation Does Not Create Members

Boot allows disabling existence validation with:

```properties
management.endpoint.health.validate-group-membership=false
```

This property does not create missing contributors and does not prove the group scope is right. It only disables the configuration validation gate. Using it to mask typos can lead operators to believe a dependency is being monitored when no check actually exists.

Validation runs during singleton initialization; pay attention to registration timing if the application manages contributors dynamically. [Membership validation source in Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

### 7.3. Do Not Leave a Group Empty and Assume It Is Healthy

For example, `include: [primaryStore]` paired with `exclude: [primaryStore]` removes every member. Such a configuration cannot answer the health question you intended to ask.

With Boot 3.3's HTTP implementation, when no health contributions remain in a group, querying it may yield no health result and return `404`; do not assume an empty group will always return `UP`. Verify both the member set and the actual response. [Health contribution collection flow](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

## 8. When Contributors Have Child Components

A contributor can be a tree rather than a single check. For instance, suppose the application registers the following structure:

```text
stores
├── primary
└── reporting
```

To select only the `primary` child component, use the full path:

```yaml
management:
  endpoint:
    health:
      group:
        writepath:
          include:
            - stores/primary
```

Or select the `stores` tree and exclude one branch:

```yaml
management:
  endpoint:
    health:
      group:
        writepath:
          include:
            - stores
          exclude:
            - stores/reporting
```

This is an additional illustrative snippet; do not paste it directly into the three-indicator application above because that application does not register a composite `stores` contributor. The `/` separator denotes a child contributor path, not the name of another health group. When verifying, inspect the corresponding `components` structure; do not assume the tree will be flattened into a flat list.

## 9. Common Misconceptions

| Symptom or assumption | Cause to check | How to handle |
| --- | --- | --- |
| Startup fails because a member does not exist | Wrong ID, wrong casing, bean not created in the active profile | Check actual registered contributors and configure the right profile |
| `business` does not appear when added to web exposure | Confusing group name with endpoint ID | Expose `health`; place the group under `management.endpoint.health.group` |
| Excluding cache from a group and thinking cache is globally disabled | Confusing member selection with disabling an indicator | Check overall health and any group that still includes the cache |
| `noncache` changes after adding a new starter or indicator | Selection scope is all-except-excluded | Re-check membership; use explicit `include` if a fixed scope is needed |
| JSON only shows status so the group seems to have no members | Visibility policy hides components | Check `show-components` and access permissions with an appropriate policy |
| Looking only at HTTP `200` and concluding everything is fine | Not verifying the exact URL, group, and health payload | Check the members and the business status to be observed |
| YAML configuration fails with `*` | `*` is not quoted | Write `include: "*"` |
| Group does not produce the expected health result after excluding all IDs | Final member set is empty | Keep at least one meaningful check and re-verify the response |

Also distinguish similarly named properties:

```text
management.endpoint.health.group.<name>.include/exclude
  → selects contributors of a group

management.endpoints.web.exposure.include/exclude
  → selects endpoints exposed over HTTP

management.health.<key>.enabled
  → controls the corresponding auto-configured indicator, when supported
```

Moving an ID from the group list to the exposure list is not the way to fix a membership error.

## 10. Self-Check Practice

Perform these steps one by one on the standalone example:

1. Keep `cache-up=false`, and predict the statuses of all four URLs before calling them.
2. Replace `noncache.exclude` with `noncache.include: [primaryStore, billingGateway]`. Do the initial results change?
3. Add a `searchIndexHealthIndicator` bean returning `Health.down().build()`. Compare the `noncache` group using `exclude` with the group using an explicit `include`.
4. Add a `narrowed` group containing both business IDs and exclude `billingGateway`. Verify the group has exactly one member left.
5. Intentionally misspell an ID in `exclude` and restart. Determine whether this is a configuration error or a `DOWN` health response.

Results you should be able to explain:

- In step 2, the current member sets are identical, so the statuses are the same.
- In step 3, the exclusion-based group picks up `searchIndex`; the group explicitly including only the two business IDs does not.
- In step 4, `exclude` wins when an ID is both included and excluded.
- In step 5, default validation blocks startup because the ID does not exist; it is not a dependency check that ran and failed.

A group configuration fulfills its purpose when you can clearly state the question it answers, list its final member set, and predict the outcome when each member changes status.
