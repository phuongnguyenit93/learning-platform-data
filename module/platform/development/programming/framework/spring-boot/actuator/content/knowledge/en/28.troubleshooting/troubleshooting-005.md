# Finding Why a Health Group Has a Non-Existent Member or Wrong Status Mapping

## 1. Identify Which Step the Error Occurs In

A health group selects a set of health check components to answer a specific question, such as "is the application ready to serve traffic?". To diagnose accurately, separate three steps:

```text
Select members that have actually been registered
    -> retrieve each member's status
    -> aggregate into the group status using StatusAggregator
    -> convert the group status into an HTTP code using HttpCodeStatusMapper
```

**Member name**, **health status**, and **HTTP status code** are three different kinds of data. For example, `billing` is a member name, `DOWN` is a status, and `503` is an HTTP status code.

This lesson uses **Spring Boot 3.3.13 and Java 21**. The `ready` group in the examples is a custom-defined group, not a mandatory Spring Boot built-in name.

| Symptom | Step to check first |
| --- | --- |
| App fails to start, reporting a contributor does not exist | Member name and registration conditions |
| Member reports `DOWN`, yet group reports `UP` | Member set and status aggregation order |
| Group reports `DOWN`, yet HTTP is 200 | Status-to-HTTP-code mapping |
| Calling a group path returns 404 | Group name, path, and endpoint config; cannot yet conclude status mapping is wrong |

Do not change all three steps at once. One controlled change at a time reveals which cause actually affects the outcome.

## 2. Non-Existent Member: Check the Registered List

### 2.1. Distinguishing Bean Name, Member ID, and Group Name

Suppose the application registers a bean:

```java
@Bean
HealthIndicator billingHealthIndicator() {
    return () -> Health.up().build();
}
```

This is an illustrative snippet; it must be placed in a configuration class with appropriate imports. The complete program is in section 5.

Under Spring Boot's naming convention, the `HealthIndicator` suffix is stripped when determining the indicator's ID. The bean above has ID `billing`. The group uses that ID:

```properties
management.endpoint.health.group.ready.include=billing
```

Do not replace `billing` with the class name, `billingHealthIndicator`, or the URL `/actuator/health/billing` just because they refer to the same check. `ready` is the group name; it does not become a contributor name either. ID rules are described in [Writing Custom HealthIndicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

For composite contributors, you must inspect the member tree. For instance, if a `storage` composite actually has a child branch `primary`, the member path is `storage/primary`. Do not turn it into `storage.primary` or `primary` when they are not registered that way.

### 2.2. Reading the Error Message for Three Facts

Configuration:

```properties
management.endpoint.health.group.ready.include=billing,ghost
```

If there is no `ghost` contributor, the example's error description will include:

```text
Included health contributor 'ghost' in group 'ready' does not exist
```

Three facts to extract:

- `Included`: the wrong name is in the `include` list.
- `ghost`: the contributor to compare against the actual registration list.
- `ready`: the group containing the invalid configuration.

The `exclude` list is also validated. Excluding a non-existent name can cause startup to fail rather than always being ignored:

```text
Excluded health contributor 'ghost' in group 'ready' does not exist
```

In this version's default mechanism, validation runs when initializing health infrastructure; the validator traverses each segment of the contributor path. You can cross-check [HealthEndpointGroupMembershipValidator in the 3.3.13 source](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

### 2.3. Why Might a Name Look Right Yet Still Not Exist?

| Common cause | Evidence to look for | Fix based on cause |
| --- | --- | --- |
| Typo, wrong casing, or using bean name instead of ID | Actual name in registry or diagnostic logs | Fix the name in the right group |
| Auto-configured indicator lacks creation conditions | Missing dependency, backing bean, or unmet auto-config condition | Supply required conditions if the check belongs to the design |
| Indicator disabled by configuration | Effective configuration value | Re-enable that indicator or adjust group scope |
| Custom bean only exists in one profile | Active profile and conditions on the bean | Align group config with the profile |
| Wrong path into a composite | Actual contributor structure | Use the right parent/child path |
| Group copied from another environment | Dependencies and beans differ between environments | Write group config appropriate for each environment |

For example, the name `db` does not create a `DataSource`; the name `redis` does not add the Redis library either. Names in a group only select checks that already exist.

When needing in-place verification, `HealthContributorRegistry` provides the registered contributors and can be inspected via diagnostic code. See [HealthContributorRegistry API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html). Do not infer the actual list solely from the starters you remember declaring.

### 2.4. Disabling Validation Does Not Create the Missing Member

You can skip the startup check with:

```properties
management.endpoint.health.validate-group-membership=false
```

However, this property **does not register a new contributor, rename anything, or execute the missing check**. If a group accidentally omits a critical dependency, the application starting successfully does not mean the group is checking enough.

Prefer fixing the name, bean creation conditions, or per-environment configuration. Only disable membership validation when the design genuinely permits a contributor to be absent and you have verified the group still checks everything required. Do not use it to mask a copy-paste config bug.

## 3. Member Status Is Right, Yet Group Status Is Wrong

`StatusAggregator` selects the aggregated status according to the configured priority order. This is not majority voting: one `DOWN` member can still determine the group status even when all other members are `UP`.

With Spring Boot 3.3.13's default aggregator, the order is `DOWN`, `OUT_OF_SERVICE`, `UP`, `UNKNOWN`. The aggregator only considers statuses present in its known order; if none match, the result is `UNKNOWN`. This mechanism can be inspected in [SimpleStatusAggregator](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Suppose `billing` returns a custom status `FATAL`, while `cache` returns `UP`. If the aggregator does not yet know about `FATAL`, that status can be ignored and the group returns `UP`.

Adding only the mapping `fatal=503` does not solve it: the mapper receives the **already aggregated status of the group**, and does not scan all child statuses itself.

Configure the order for the group:

```properties
management.endpoint.health.group.ready.status.order=fatal,down,out-of-service,unknown,up
```

This is an example policy: placing `FATAL` before `DOWN`, and choosing `UNKNOWN` with higher priority than `UP`. Choose an order matching your system's operational meaning; do not treat this as a verbatim copy of the default order.

When setting a custom order, list all group statuses that need handling. For example, setting only `fatal,up` may cause a `DOWN` to no longer be considered as intended. Similarly, placing `up` before `down` can select `UP` when both appear together.

If the group status is wrong, verify **both the selected members and the aggregator** before adjusting HTTP codes.

## 4. Group Reports DOWN, Yet HTTP Is 200

### 4.1. Defaults and the Trap When Adding Custom Mappings

With the default mapper:

| Group status | HTTP code |
| --- | --- |
| `DOWN` | 503 |
| `OUT_OF_SERVICE` | 503 |
| `UP` | 200 |
| `UNKNOWN` | 200 |
| Unmapped status | 200 |

In Spring Boot 3.3, declaring custom mappings drops the default `DOWN` and `OUT_OF_SERVICE` mappings unless you re-declare them. That is why a config that looks like "just adding FATAL" can alter `DOWN` behavior.

Incomplete configuration:

```properties
management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

If the group aggregates to `DOWN`, the custom table above lacks `DOWN`; the mapped result is 200.

Complete configuration for the example policy:

```properties
management.endpoint.health.group.ready.status.http-mapping.fatal=503
management.endpoint.health.group.ready.status.http-mapping.down=503
management.endpoint.health.group.ready.status.http-mapping.out-of-service=503
```

The tests in section 6 verify directly via `HttpCodeStatusMapper`; the mapper API is documented at [SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

### 4.2. Distinguishing Global Configuration from Group-Specific Configuration

Two different scopes:

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

When a group has no dedicated config or bean for a given function, it inherits the shared aggregator/mapper. However, once a group has its own non-empty mapping table, do not assume it is merged key-by-key with the global table. In the example above, `ready` can map `DOWN` to 200 even though global has `down=503`.

The fix is to declare the full needed table on the group, or remove the group-specific table if you want the group to use the shared policy. Check the same behavior for `status.order`.

In addition to properties, look for `StatusAggregator` and `HttpCodeStatusMapper` beans and beans annotated with `@Qualifier("ready")`. A custom bean can determine actual runtime behavior instead of the one built from properties. How configuration and beans are selected is shown in [AutoConfiguredHealthEndpointGroups](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

## 5. Minimal Application to Reproduce

Prepare JDK 21 and Maven. The example uses two simulated checks and makes no external database or cache connections. Statuses are passed via configuration to reproduce each scenario deterministically.

File tree:

```text
health-group-lab/
├── pom.xml
└── src/main/
    ├── java/example/HealthGroupLabApplication.java
    └── resources/application.properties
```

Full contents of `pom.xml`:

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
    <artifactId>health-group-lab</artifactId>
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

Full contents of `HealthGroupLabApplication.java`:

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthEndpointGroups;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthGroupLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthGroupLabApplication.class, args);
    }

    @Bean
    HealthIndicator billingHealthIndicator(
            @Value("${lab.billing-status:UP}") String status) {
        return () -> Health.status(status).build();
    }

    @Bean
    HealthIndicator cacheHealthIndicator(
            @Value("${lab.cache-status:UP}") String status) {
        return () -> Health.status(status).build();
    }

    @Bean
    @ConditionalOnProperty(name = "lab.report", havingValue = "true")
    ApplicationRunner report(
            HealthEndpoint endpoint,
            HealthEndpointGroups groups,
            ConfigurableApplicationContext context) {
        return args -> {
            var health = endpoint.healthForPath("ready");
            var group = groups.get("ready");
            System.out.println("ready.status=" + health.getStatus().getCode());
            System.out.println("ready.http=" + group.getHttpCodeStatusMapper()
                    .getStatusCode(health.getStatus()));
            SpringApplication.exit(context);
        };
    }
}
```

Contents of `src/main/resources/application.properties`:

```properties
server.port=8183
management.endpoints.web.exposure.include=health
management.endpoint.health.group.ready.include=billing,cache
management.endpoint.health.group.ready.show-components=always
management.endpoint.health.group.ready.show-details=always
```

The two beans have IDs `billing` and `cache`. The `lab.*` properties are simulation switches defined by this example, not standard Actuator properties.

The `report` bean is created only when `--lab.report=true` is passed. It fetches the group result via `healthForPath("ready")`, prints the status and code returned by the group's own mapper, and exits the application. This method belongs to the [HealthEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

Package from the directory containing `pom.xml`:

```shell
mvn package
```

Maven prepares the classpath and builds an executable JAR; do not compile this file alone with a `javac` command lacking Spring dependencies.

Run in normal HTTP mode:

```shell
java -jar target/health-group-lab-1.0.0.jar
```

From another terminal:

```shell
curl -i http://localhost:8183/actuator/health/ready
```

With the default statuses of the two checks, the group returns `UP` and HTTP 200. The JSON body looks like:

```json
{
  "status": "UP",
  "components": {
    "billing": { "status": "UP" },
    "cache": { "status": "UP" }
  }
}
```

JSON field order is not a test requirement. The component/detail visibility configuration in the example is for local diagnosis; when applying to a real system, keep an appropriate visibility policy.

Stop with Ctrl+C before changing configuration and starting another case. On Windows PowerShell, use `curl.exe` if `curl` is an alias.

## 6. Tests Isolating Each Root Cause

To focus on configuration without opening an HTTP port, the example includes an in-process report mode. The commands below disable the web server, enable JMX infrastructure to keep the endpoint available, and invoke health via the Java API.

**`ready.http` is the code returned by the mapper, not the result of a network request.** When verifying a real deployment, you must still test both direct HTTP and the path through proxies/security.

Each command is a standalone run. Options disabling the banner and logging leave stdout on success with only the program's two lines.

### 6.1. Control Baseline

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true
```

Stdout:

```text
ready.status=UP
ready.http=200
```

### 6.2. Non-Existent Member

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --management.endpoint.health.group.ready.include=billing,ghost
```

The application fails to start. The error description contains:

```text
Included health contributor 'ghost' in group 'ready' does not exist
```

This is a configuration error before the application serves traffic normally, not an HTTP 500 health response. Fix `ghost` to a valid contributor or remove that check requirement if the design permits.

To reproduce the exclusion-list error, run a separate invocation with:

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --management.endpoint.health.group.ready.exclude=ghost
```

This time the description states `Excluded` as in section 2.2.

### 6.3. DOWN with the Default Mapper

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=DOWN
```

Stdout:

```text
ready.status=DOWN
ready.http=503
```

`cache=UP` does not cancel the effect of `billing=DOWN`.

### 6.4. Adding Only FATAL Mapping and Accidentally Losing DOWN

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=DOWN --management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

Stdout:

```text
ready.status=DOWN
ready.http=200
```

The group status is still right; the bug is in the mapping table.

To fix, re-run the command above and add **two differently named options**:

```text
--management.endpoint.health.group.ready.status.http-mapping.down=503
--management.endpoint.health.group.ready.status.http-mapping.out-of-service=503
```

Place both options in the same command, separated by a space. Do not run them as two separate programs. Stdout after fixing:

```text
ready.status=DOWN
ready.http=503
```

### 6.5. Having FATAL Mapping Without an Aggregation Order

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=FATAL --management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

Stdout:

```text
ready.status=UP
ready.http=200
```

In this test, `FATAL` is not yet in the order known by the aggregator, while `cache` returns `UP`. The mapper receives `UP`, so the `fatal` key never gets a chance to be used.

Complete configuration for both steps:

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=FATAL --management.endpoint.health.group.ready.status.order=fatal,down,out-of-service,unknown,up --management.endpoint.health.group.ready.status.http-mapping.fatal=503 --management.endpoint.health.group.ready.status.http-mapping.down=503 --management.endpoint.health.group.ready.status.http-mapping.out-of-service=503
```

Stdout:

```text
ready.status=FATAL
ready.http=503
```

**Key distinction:** editing the aggregation order changes `ready.status`; editing the HTTP table only changes the mapped code for the already chosen status.

## 7. Diagnostic Procedure in a Real Application

1. **Identify when the failure happens.** If startup fails because a contributor does not exist, resolve the validation error first. If the app is already running, record the group name, JSON status, and HTTP code.
2. **Verify effective configuration.** Check profiles, files outside the JAR, environment variables, and startup arguments. A value in source code can be overridden by another source; see [configuration source precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
3. **Cross-check actual members.** Check IDs in the registry, bean creation conditions, and composite paths. Distinguish "check does not exist" from "check exists and is DOWN."
4. **Compare child statuses with group status.** When needed, allow viewing components through the existing diagnostic policy. If a status is ignored, check the member set and `status.order`.
5. **Compare group status with HTTP.** When the group is already `DOWN` yet HTTP is 200, look for a custom mapping table missing keys, group/global scope differences, and `HttpCodeStatusMapper` beans.
6. **Check the request path.** If the code from the app differs from what is observed externally, check proxies, gateways, security filters, and probe config. Do not blame Actuator for every difference.
7. **Fix one cause and re-verify.** Test a healthy case, a failing case, and important custom statuses. Verify both the status payload and the HTTP code; checking only "not 500" is not enough.

Root health `/actuator/health` and group `/actuator/health/ready` can return different results because their member sets or aggregation policies differ. That alone is not a bug: check the exact group that external callers query.

Similar-looking names also need separating. `readiness` may be a probe group name, while `readinessState` is the ID of a readiness state check. If using auto-configured probe components, check their enabling conditions; do not swap one name for the other in the membership list.

## 8. Fixes That Easily Hide Bugs

- **Disabling validation so the app starts:** can lose a mandatory check without creating the missing contributor.
- **Mapping every HTTP code to 200:** can make load balancers keep sending requests to an unready application.
- **Adding only `fatal=503`:** does not fix aggregation order and can drop default failure mappings.
- **Editing the global table while ignoring the group table:** a group with its own config can still keep different behavior.
- **Using `show-details` to "fix" statuses:** visibility properties aid observation; they do not fix members, the aggregator, or the HTTP table.
- **Equating UNKNOWN with healthy:** by default it may map to 200, yet the check meaning is still undetermined. Operational policy must decide whether to accept that state.

## 9. Self-Check

**A. A group references `billingHealthIndicator`, yet the registry only has `billing`. Do you need to change HTTP mapping?**

No. Fix the member ID in the group; you have not even reached aggregation or HTTP mapping.

**B. Group JSON is `DOWN`, HTTP is 200, and the group has its own `fatal=503`. What do you check first?**

Check the group's own HTTP mapping table and re-declare `down`/`out-of-service` per the desired policy.

**C. A member returns `FATAL`, yet the group returns `UP` despite `fatal=503`.**

Check `status.order` and whether the member is in the group. The mapper only receives the aggregated status.

**D. `down=503` globally, yet the group still maps DOWN to 200.**

Look for a group-specific mapping table or bean. Do not assume group-specific config merges key-by-key with global config.

**E. You disable member validation and the app starts successfully. Have you proven the critical dependency is being checked?**

No. You must verify the contributor is actually registered, included in the group, and properly affects both the status and the HTTP code.
