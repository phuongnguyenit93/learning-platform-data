# Enabling or Disabling Individual Indicators and Default Indicators

## 1. What are we enabling or disabling?

A `HealthIndicator` is a check returning health information, such as whether disk space is sufficient or a database connection can be acquired. Spring Boot Actuator can create indicators automatically when the application satisfies configuration conditions.

When asked to "disable the database check", identify the exact intent:

- Do not register the auto-configured database check in the health set.
- Keep the check but exclude it from a specific health group.
- Still compute the result but hide details from callers.
- Disallow accessing the health endpoint over HTTP.

These are different operations. This lesson focuses on **indicator creation and registration conditions**, especially two configuration forms:

```properties
management.health.<key>.enabled=true
management.health.defaults.enabled=false
```

`<key>` is a placeholder for the key name to replace with an actual name like `db`, `diskspace`, or `ping`; do not copy `<...>` literally into configuration files.

Examples and verification programs use **Spring Boot 3.3.0, JDK 21**. Class/package names and remarks about probes in this lesson belong to the **3.3.x** branch; when switching version branches, re-verify the corresponding configuration.

### 1.1. Why select the set of checks?

Suppose an application has a database used for an auxiliary feature. When that database service fails, its indicator can cause overall health to report failure. Before removing the check, answer: can the application still perform the functionality users need?

A good configuration clearly states which conditions are monitored. If you only want a traffic-routing group to ignore a dependency, consider that group's membership before disabling the check application-wide. Conversely, if an auto-configured check does not fit the runtime environment, you can disable it individually.

Disabling an indicator **does not fix a broken resource**, does not turn its result into `UP`, and does not stop the underlying resource. For example, `management.health.db.enabled=false` does not mean the `DataSource` bean is disabled.

## 2. Enable/disable keys, bean names, and component names

### 2.1. Using the exact key supported by Spring Boot

Some examples in Spring Boot 3.3:

| Config key | Check meaning | Actual condition required |
| --- | --- | --- |
| `diskspace` | Disk space | Disk space check configuration |
| `ping` | Returns status `UP` | Does not require connecting to external services |
| `db` | Acquire JDBC connection | Suitable `DataSource` present |
| `redis` | Redis connection | Suitable library types and connection bean present |
| `rabbit` | RabbitMQ connection | Corresponding connection infrastructure present |
| `mail` | Mail server connection | Suitable mail-sending configuration present |

These keys are listed in [Spring Boot 3.3 Health Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.auto-configured-health-indicators).

Do not infer that adding `management.health.redis.enabled=true` automatically creates Redis, installs libraries, or supplies connection settings. This switch is only one condition; auto-configuration also has conditions on classes, beans, and resources.

`ping` also does not prove every business feature works. An endpoint left with only `ping` can still report `UP` even though the application has not checked any critical dependency.

### 2.2. Distinguishing the three names for disk space

| Where used | Name in Spring Boot 3.3 example |
| --- | --- |
| Enable/disable key | `management.health.diskspace.enabled` |
| Bean created by auto-configuration | `diskSpaceHealthIndicator` |
| Component ID in registry/JSON/groups | `diskSpace` |

In source code, disk space configuration carries `@ConditionalOnEnabledHealthIndicator("diskspace")` and creates a bean named `diskSpaceHealthIndicator` when no conflicting bean exists. That is why you must use the exact config key instead of converting the bean name into a property yourself. [DiskSpaceHealthContributorAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/system/DiskSpaceHealthContributorAutoConfiguration.java)

With a self-declared bean `catalogHealthIndicator`, the usual ID is `catalog`. However, having ID `catalog` **does not automatically create** a mechanism reading `management.health.catalog.enabled`; the bean must carry a condition using that key.

## 3. Precedence mechanism: specific config first, global default second

For an indicator using `@ConditionalOnEnabledHealthIndicator("key")`, the rule reads as:

```text
Is management.health.key.enabled present?
    Yes -> use that specific value.
    No  -> use management.health.defaults.enabled if present.
           If also absent -> allow by default.
```

This condition is part of auto-configuration, not a filter deleting health beans after they have already been created. Spring Boot's condition class uses the `management.health.` prefix to evaluate indicators. [OnEnabledHealthIndicatorCondition 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/OnEnabledHealthIndicatorCondition.java)

### 3.1. Precedence table

The table below evaluates the values **effective in Spring Environment** after configuration sources have been applied:

| `defaults.enabled` | `<key>.enabled` | Condition for that indicator |
| --- | --- | --- |
| Undeclared | Undeclared | Allowed |
| `true` | Undeclared | Allowed |
| `false` | Undeclared | Disallowed |
| Undeclared | `true` | Allowed |
| Undeclared | `false` | Disallowed |
| `true` | `true` | Allowed |
| `true` | `false` | Disallowed |
| `false` | `true` | Allowed |
| `false` | `false` | Disallowed |

"Allowed" is not enough to guarantee the bean definitely appears: other auto-configuration conditions must still be satisfied.

Two implications to remember:

1. `defaults.enabled=false` **is not an absolute ban**: a specific `true` switch can re-enable an indicator.
2. `defaults.enabled=true` **does not force every indicator on**: a specific `false` switch still wins.

Auto-configurations using this annotation are listed in [ConditionalOnEnabledHealthIndicator API in 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/health/class-use/ConditionalOnEnabledHealthIndicator.html). The program in section 7 directly verifies this precedence rule using the **3.3.0** libraries.

### 3.2. Disabling one indicator individually

```properties
management.health.diskspace.enabled=false
```

Other indicators continue following their own configuration. There is no need to set `defaults.enabled=true` just to keep default behavior.

Another example:

```properties
management.health.db.enabled=false
management.health.redis.enabled=true
```

This means disallowing auto-configuration from creating the JDBC check, while allowing auto-configuration to create the Redis check if remaining conditions are met. These switches do not change the application's ability to use JDBC or Redis in business logic.

### 3.3. Disabling by default then opting back in

```properties
management.health.defaults.enabled=false
management.health.ping.enabled=true
management.health.diskspace.enabled=true
```

This is a way to declare the set of auto-configured checks explicitly. `ping` and `diskspace` are allowed; other indicators under the global default mechanism will not be allowed without their own switch.

YAML equivalent:

```yaml
management:
  health:
    defaults:
      enabled: false
    ping:
      enabled: true
    diskspace:
      enabled: true
```

In the same YAML file, combine these entries under **one** `management` key. Do not create multiple duplicate `management` keys and expect them to merge as desired.

The official properties list is the place to check switch names and meanings by version. [Spring Boot 3.3 Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

## 4. Are self-declared beans governed by the default switch?

The answer depends on **conditions on the bean-creating code**, not just on whether the bean implements `HealthIndicator`.

### 4.1. Bean without an enable/disable condition

The following snippet sits inside a Spring configuration class:

```java
@Bean
HealthIndicator catalogHealthIndicator() {
    return () -> Health.up().build();
}
```

Merely adding the following configuration does not remove that bean:

```properties
management.health.defaults.enabled=false
management.health.catalog.enabled=false
```

No code on the sample bean reads those two switches. Spring Boot does not treat every name after `management.health.` as a command to delete the corresponding health bean.

This also matters when supplying your own bean to replace a built-in indicator. Setting `enabled=false` can prevent the auto-configured path from creating a bean, yet a bean actively created by the application through another path can still exist.

### 4.2. Giving the bean an application-specific switch

```java
@Bean
@ConditionalOnProperty(prefix = "demo.health.catalog", name = "enabled",
        havingValue = "true", matchIfMissing = true)
HealthIndicator catalogHealthIndicator() {
    return () -> Health.up().build();
}
```

Imports for the snippet above:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
```

With this condition:

- `demo.health.catalog.enabled` undeclared: bean is created because `matchIfMissing=true`.
- Value `true`: bean is created.
- Value `false`: bean is not created.
- `management.health.defaults.enabled` does not participate in this custom condition.

`havingValue="true"` and `matchIfMissing=true` are choices written explicitly in code, not universal defaults of the annotation. [ConditionalOnProperty 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)

### 4.3. Letting the bean use management.health rules

If you want the `catalog` bean to participate in the precedence mechanism from section 3, use this **instead of the annotation in section 4.2**:

```java
@Bean
@ConditionalOnEnabledHealthIndicator("catalog")
HealthIndicator catalogHealthIndicator() {
    return () -> Health.up().build();
}
```

Additional import:

```java
import org.springframework.boot.actuate.autoconfigure.health.ConditionalOnEnabledHealthIndicator;
```

Then:

```properties
management.health.defaults.enabled=false
management.health.catalog.enabled=true
```

will allow creating the `catalog` bean, whereas:

```properties
management.health.catalog.enabled=false
```

will disallow creating that bean even though the global default is `true`.

Do not keep both annotations simultaneously unless you intentionally require **both conditions** to be satisfied. The two approaches are alternative designs with two different configuration namespaces.

## 5. Experiment on an HTTP application

We create an application with only Web, Actuator, and one self-declared indicator. The goal is to observe the **set of registered IDs**, separate from whether a check reports `UP` or `DOWN`.

### 5.1. Project files

```text
indicator-demo/
├── pom.xml
└── src/main/
    ├── java/example/indicators/IndicatorDemoApplication.java
    └── resources/application.properties
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>indicator-demo</artifactId>
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

`src/main/java/example/indicators/IndicatorDemoApplication.java`:

```java
package example.indicators;

import java.util.TreeSet;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.NamedContributor;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IndicatorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IndicatorDemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(prefix = "demo.health.catalog", name = "enabled",
            havingValue = "true", matchIfMissing = true)
    HealthIndicator catalogHealthIndicator() {
        return () -> Health.up().withDetail("source", "local-demo").build();
    }

    @Bean
    ApplicationRunner printContributors(HealthContributorRegistry registry) {
        return args -> {
            var names = new TreeSet<String>();
            for (NamedContributor<HealthContributor> item : registry) {
                names.add(item.getName());
            }
            System.out.println("contributors=" + names);
        };
    }
}
```

The `catalog` indicator intentionally returns a fixed local result so the experiment needs no external system. In a real application, replace the check with a meaningful condition; do not use this fixed result as proof that business logic works.

`src/main/resources/application.properties`:

```properties
spring.application.name=indicator-demo
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=never
management.endpoint.health.probes.enabled=false
management.health.livenessstate.enabled=false
management.health.readinessstate.enabled=false
```

The last three switches isolate probes and lifecycle state indicators from the experiment. They are not a requirement to disable probes in a real application.

`show-components=always` is only used to easily observe component names in the local example. In deployment, choose an appropriate visibility policy and access permissions. `show-details=never` keeps check details out of the response; it does not stop checks from running.

### 5.2. Packaging and inspecting the default set

In the directory containing `pom.xml`:

```powershell
mvn -q package
java -jar target/indicator-demo-1.0.0.jar
```

After startup, find the line printed by `ApplicationRunner`, separate from other logs:

```text
contributors=[catalog, diskSpace, ping]
```

The list is sorted via `TreeSet` so it does not depend on bean appearance order. This line proves **presence in the registry**, not that every indicator returns `UP`.

In PowerShell on Windows, open another terminal and read the IDs over HTTP:

```powershell
$healthSnapshot = curl.exe -sS http://localhost:8080/actuator/health | ConvertFrom-Json
$healthSnapshot.components.PSObject.Properties.Name | Sort-Object
```

Component name output:

```text
catalog
diskSpace
ping
```

Invoke `curl.exe` to avoid the `curl` alias in some PowerShell versions. Do not use `--fail` in this observation: if actual disk space causes health to report failure, we still need to read the response body.

### 5.3. Disabling diskspace individually

Stop the process with `Ctrl+C`, then run:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.diskspace.enabled=false
```

The application prints:

```text
contributors=[catalog, ping]
```

`diskSpace` is no longer in the registered set. `ping` and `catalog` remain present. The application did not rename `diskSpace` or force its result to `UP`; this auto-configured indicator creation path was disabled.

### 5.4. Disabling global defaults

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false
```

The application prints:

```text
contributors=[catalog]
```

`diskSpace` and `ping` are not created by the default mechanism. `catalog` remains because it uses the application's own `demo.health.catalog.enabled` switch with `matchIfMissing=true`.

### 5.5. Re-enabling ping even when global defaults is false

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false --management.health.ping.enabled=true
```

The application prints:

```text
contributors=[catalog, ping]
```

Test the opposite direction:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=true --management.health.ping.enabled=false
```

The application prints:

```text
contributors=[catalog, diskSpace]
```

The specific switch takes precedence in both directions.

### 5.6. Disabling the self-declared bean using its exact switch

The following command **does not disable catalog** in the sample application:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false --management.health.catalog.enabled=false
```

The application still prints:

```text
contributors=[catalog]
```

To disable the bean using the exact annotation it carries:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false --demo.health.catalog.enabled=false
```

The application prints:

```text
contributors=[]
```

An empty list only shows there are no contributors left in the experiment. Do not use it as proof that the application has checked all conditions required to serve users.

Each command above is **a separate launch**. Stop the previous run before starting the next so port `8080` does not collide.

## 6. Distinguishing disabling an indicator from similar-looking configurations

| Goal | Configuration/mechanism | Consequence to understand |
| --- | --- | --- |
| Prevent creating an auto-configured indicator | `management.health.<key>.enabled=false` | The indicator from that configuration path is not registered |
| Change default for supported indicator group | `management.health.defaults.enabled=false` | Specific switches and other bean-creation paths must still be checked |
| Exclude a contributor from one group | `management.endpoint.health.group.<group>.exclude` | Contributor can still exist and participate in root/other groups |
| Hide details | `management.endpoint.health.show-details=never` | Does not prevent the check from executing |
| Hide components | `management.endpoint.health.show-components=never` | JSON is not enough to conclude the contributor was removed |
| Disable the endpoint | `management.endpoint.health.enabled=false` | Operates at endpoint level, not per-check switch |
| Unpublish endpoint over HTTP | `management.endpoints.web.exposure.exclude=health` | Controls HTTP reachability, not check results |
| Block callers via security | Authentication/authorization rules | Blocked responses do not prove an indicator was disabled |

Example excluding `diskSpace` from **a custom-named group**:

```properties
management.endpoint.health.group.traffic.include=*
management.endpoint.health.group.traffic.exclude=diskSpace
```

The `traffic` group can ignore this check while overall health still includes `diskSpace`. In YAML, write `include: "*"` because `*` has special meaning in YAML.

If a group's `include` specifies a contributor that was disabled or not created, group member validation can cause startup to fail. Fix the member set or contributor creation condition consistently rather than disabling group validation by default.

### 6.1. Limits with probes and separate configuration paths

Do not treat `management.health.defaults.enabled=false` as a switch closing every health mechanism. In Spring Boot 3.3, probes have their own configuration path via `management.endpoint.health.probes.enabled` and can be activated automatically when Kubernetes is detected.

Probes configuration can create `livenessState` and `readinessState` indicators via its own mechanism. Therefore, looking at `defaults.enabled` alone to conclude all indicators are absent is insufficient. [AvailabilityProbesAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/availability/AvailabilityProbesAutoConfiguration.java)

This lesson only uses those flags to isolate the experiment. Designing liveness/readiness semantics and their impact on restarts or routing must be decided per operational requirements.

### 6.2. When configuration takes effect

Bean-creation conditions are evaluated when building the ApplicationContext. With the sample application, editing a properties file after the application is already running does not automatically recreate or remove indicators; restart with the new configuration.

Spring Boot has an API to manage the registry at runtime, but that is a different mechanism. Do not treat the configuration switches in this lesson as a live per-HTTP-request toggle API.

## 7. Java program verifying nine scenarios

The following program builds a small ApplicationContext with only the health configurations to test. It does not open a web server and requires no JDBC, Redis, or external services.

Two nested configuration classes allow comparison:

- `CustomIndicators`: switch `demo.health.catalog.enabled`, independent of health defaults.
- `ManagedCustomIndicators`: switch `management.health.catalog.enabled`, respecting health defaults.

Create `experiments/IndicatorSwitchDemo.java` alongside the section 5 project, **outside** `src/main/java` so it does not add a second main class to the Spring Boot JAR:

```java
import java.util.Map;
import java.util.TreeSet;
import org.springframework.boot.actuate.autoconfigure.health.ConditionalOnEnabledHealthIndicator;
import org.springframework.boot.actuate.autoconfigure.health.HealthContributorAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.system.DiskSpaceHealthContributorAutoConfiguration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.NamedContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class IndicatorSwitchDemo {
    @Configuration(proxyBeanMethods = false)
    static class CustomIndicators {
        @Bean
        @ConditionalOnProperty(prefix = "demo.health.catalog",
                name = "enabled", havingValue = "true", matchIfMissing = true)
        HealthIndicator catalogHealthIndicator() {
            return () -> Health.up().build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ManagedCustomIndicators {
        @Bean
        @ConditionalOnEnabledHealthIndicator("catalog")
        HealthIndicator catalogHealthIndicator() {
            return () -> Health.up().build();
        }
    }

    static void run(String label, Class<?> customConfig,
                    Map<String, Object> properties) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("experiment", properties));
            context.register(customConfig,
                    DiskSpaceHealthContributorAutoConfiguration.class,
                    HealthContributorAutoConfiguration.class,
                    HealthEndpointAutoConfiguration.class);
            context.refresh();
            HealthContributorRegistry registry =
                    context.getBean(HealthContributorRegistry.class);
            var names = new TreeSet<String>();
            for (NamedContributor<HealthContributor> item : registry) {
                names.add(item.getName());
            }
            System.out.println(label + "=" + names);
        }
    }

    public static void main(String[] args) {
        run("default", CustomIndicators.class, Map.of());
        run("diskspace-off", CustomIndicators.class,
                Map.of("management.health.diskspace.enabled", false));
        run("defaults-off", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false));
        run("ping-opt-in", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "management.health.ping.enabled", true));
        run("custom-key-ignored", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "management.health.catalog.enabled", false));
        run("custom-off", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "demo.health.catalog.enabled", false));
        run("managed-defaults-off", ManagedCustomIndicators.class,
                Map.of("management.health.defaults.enabled", false));
        run("managed-opt-in", ManagedCustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "management.health.catalog.enabled", true));
        run("managed-explicit-off", ManagedCustomIndicators.class,
                Map.of("management.health.defaults.enabled", true,
                        "management.health.catalog.enabled", false));
    }
}
```

Obtain the Maven classpath, compile, and run in PowerShell on Windows:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$indicatorDemoClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $indicatorDemoClasspath experiments/IndicatorSwitchDemo.java
java -cp "$indicatorDemoClasspath;experiments" IndicatorSwitchDemo
```

On Linux/macOS, use `:` as the classpath separator and the corresponding shell syntax.

Stdout lines produced by the program:

```text
default=[catalog, diskSpace, ping]
diskspace-off=[catalog, ping]
defaults-off=[catalog]
ping-opt-in=[catalog, ping]
custom-key-ignored=[catalog]
custom-off=[]
managed-defaults-off=[]
managed-opt-in=[catalog]
managed-explicit-off=[diskSpace, ping]
```

Library logs, if any, are not part of the result lines above. The list is sorted for easy comparison.

### 7.1. How to read the results

1. `default` and `diskspace-off` show that disabling one does not affect remaining contributors.
2. `defaults-off` removes both auto-configured indicators but does not remove the custom bean using its own switch.
3. `ping-opt-in` confirms an individual `true` can re-enable after a global `false`.
4. `custom-key-ignored` shows that setting a property not read by the bean's condition will not automatically disable the bean.
5. `custom-off` disables the bean using the exact switch its code actually uses.
6. `managed-defaults-off` and `managed-opt-in` show a custom bean can participate in the global default mechanism if annotated accordingly.
7. `managed-explicit-off` confirms an individual `false` beats a global `true`.

This is a registry-presence verification via framework APIs. In a real application, you must also inspect profiles, effective configuration sources, active starters, self-supplied beans, and each group's member set.

## 8. Diagnosing when configuration does not yield the expected result

| Symptom | Possibility to check | Useful check |
| --- | --- | --- |
| Set `defaults=false` yet an indicator is still present | Specific `true` switch, self-declared bean, or separate config path | Find where the bean is created and its own condition |
| Set `redis=true` yet no Redis health | Missing library/connection bean or auto-config fails another condition | Check dependencies and condition evaluation report |
| Set `management.health.catalog.enabled=false` yet catalog remains | Bean does not use that rule | Inspect annotations on the bean; do not infer from ID |
| JSON lacks `components` | Visibility policy hides components | Check registry or enable visibility in test environment |
| Name in registry yet health reports `DOWN` | Indicator was created and check returned failure | Analyze check result; do not treat enable switch as forcing `UP` |
| Disabled `db` yet app still has connection errors in business logic | Health switch does not disable database-using code | Fix the connection or business path |
| Startup fails after disabling an indicator | A group requires a member that no longer exists | Check `group.*.include/exclude` and ID names |
| Edited properties yet run does not change | File/profile not loaded, overridden by another source, or not restarted | Check effective configuration and launch command |

You can start the sample application with `--debug` to view the condition evaluation report in logs:

```powershell
java -jar target/indicator-demo-1.0.0.jar --debug --management.health.diskspace.enabled=false
```

The report helps distinguish "configuration path did not match condition" from "bean was created yet hidden from JSON". There is no need to expose `env` or `conditions` endpoints publicly just to run this experiment.

## 9. Practice and self-check criteria

1. Using only configuration of the sample application, produce `[catalog, diskSpace]`. Predict which switch must be disabled, then compare against the `contributors` line.
2. Produce `[ping]` by disabling global defaults, individually enabling `ping`, and disabling `catalog` with the application's switch. Check both registry and HTTP.
3. Replace `catalog`'s annotation with `@ConditionalOnEnabledHealthIndicator("catalog")`. Re-run `defaults=false` and `catalog=true`; explain why `demo.health.catalog.enabled` is no longer the switch controlling the bean.
4. Keep `diskSpace` in the registry while excluding it from the `traffic` group. Distinguish that result from setting `management.health.diskspace.enabled=false`.
5. Explain why having only `ping` left and HTTP succeeding is not enough to assert the application can access the database.
6. For a real indicator you want to disable, write down which condition it checks, who consumes that signal, and what signal replaces it after disabling.

When reviewing an enable/disable change, compare three pieces of evidence: **effective configuration value, bean-creation condition, and actual contributor set**. They explain accurately what the application stopped checking, rather than relying on a JSON response that merely looks healthy.
