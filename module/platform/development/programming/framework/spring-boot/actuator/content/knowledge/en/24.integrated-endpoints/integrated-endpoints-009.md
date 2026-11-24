# Evaluating Dependency, Bean, and Access Conditions for Each Built-in Endpoint

## 1. An Endpoint URL Works Thanks to Several Distinct Conditions

Adding `spring-boot-starter-actuator` does not guarantee every built-in endpoint has a callable URL or returns useful data.

For example, the same symptom "cannot read HTTP exchanges" can stem from different causes:

- No bean storing HTTP exchanges exists.
- The endpoint is disabled or not exposed over HTTP.
- Calling the wrong management port.
- The request is blocked by the security layer.
- The endpoint is readable, but the repository has recorded no requests yet.

The right way to evaluate is to separate the condition layers:

~~~text
Dependency present on runtime classpath
                ↓
Required beans and application infrastructure created
                ↓
Endpoint enabled and auto-configuration conditions met
                ↓
Endpoint exposed over the right HTTP/JMX channel
                ↓
Correct address, path, method, and parameters
                ↓
Authenticated, authorized, and CSRF satisfied if applicable
                ↓
Operation has suitable runtime data source/resource
~~~

This diagram is an investigation model, not a guarantee that every security filter runs after routing inside the framework. In a specific application, the security layer may process a request before knowing whether it maps to a valid endpoint.

**Dependency**, **bean**, **enabled**, **exposure**, and **access permissions** answer different questions. This article uses Spring Boot **3.3.x**, with the experiment pinned to **3.3.0** and Java **17 or higher**.

## 2. Distinguishing Five Concepts Before Reading Configuration

| Concept | Question to Answer | Appropriate Evidence |
| --- | --- | --- |
| Dependency | Are the required library classes in the running process? | Runtime dependency graph, packaged artifact contents |
| Bean/infrastructure | Are the objects the endpoint uses created and configured properly? | ApplicationContext, conditions report, startup logs |
| Enabled | Does configuration allow the endpoint to be enabled? | `management.endpoint.<id>.enabled` and default settings |
| Exposure | Is the endpoint exposed on the HTTP/JMX channel under review? | `management.endpoints.<channel>.exposure.*`, actual mappings |
| Permissions and executability | Is the caller allowed to run the operation, and does it have data/resources? | Security configuration, request/response, data source state |

A dependency declared only in `testImplementation` does not prove it exists in the deployed application. Likewise, seeing a class inside a JAR file does not prove the corresponding bean was created.

Auto-configuration typically combines conditions such as:

- `@ConditionalOnClass`: required classes are present.
- `@ConditionalOnBean`: required beans already exist.
- `@ConditionalOnMissingBean`: yields to application-supplied configuration.
- `@ConditionalOnWebApplication`: matching web application type.
- `@ConditionalOnAvailableEndpoint`: endpoint enablement/exposure conditions met.

Do not read one annotation in isolation and ignore the remaining conditions. If the application supplies its own endpoint or infrastructure, default auto-configuration may intentionally back off.

In Boot 3.3, an endpoint is considered available when it is enabled and exposed; separate dependency/bean conditions must still be satisfied. Source: [Spring Boot 3.3 endpoint model](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 3. Evaluation Table of Endpoints by Data Source and Platform Conditions

The tables below help identify key conditions of built-in endpoints in the Boot 3.3 branch. They **do not replace** checking annotations and effective configuration of the exact patch version running. GET/POST/DELETE permissions in an app are security policies set by the application, with no single universal default role per row.

### 3.1. Endpoints Primarily Based on Context, Environment, or JVM Infrastructure

| Endpoint | Dependency/Bean/Infrastructure to Check | What to Evaluate Next |
| --- | --- | --- |
| `health` | Health infrastructure and contributors configured by Boot/app | Status and detail-visibility permissions; HTTP `503` can reflect unhealthy status |
| `info` | `InfoContributor` beans and corresponding info sources | `200 {}` may simply mean no info has been contributed yet |
| `beans` | ApplicationContext and beans inside the context | Application structure info must be restricted to authorized viewers |
| `conditions` | Auto-configuration conditions report | Explains why configurations matched/did not match, not a list of mandatory errors to fix |
| `env` | Application `Environment` | Call permission and value-display policy are two separate layers |
| `configprops` | Configuration properties infrastructure and corresponding beans | Missing expected group may mean the bean was not created/bound |
| `mappings` | Components supplying mappings in the active web stack/context | Read the right context/port; do not assume every mapping is a public API |
| `scheduledtasks` | Scheduling infrastructure and objects supplying registered tasks | Having the endpoint does not mean the app has scheduled tasks to list |
| `loggers` | Compatible and active `LoggingSystem` | Reading loggers and changing log levels carry different permission/impact levels |
| `threaddump` | Thread diagnostic infrastructure of the JVM runtime | Thread-reading permissions and collection cost; no need to write a custom HTTP controller instead |

For this group, "no optional business library required" does not mean "no conditions at all." For instance, `loggers` still depends on the logging system, and `info` content still depends on contributors/data sources.

### 3.2. Endpoints Tied to Specialized Libraries or Beans

| Endpoint | Key Condition to Verify | Important Distinction |
| --- | --- | --- |
| `auditevents` | `AuditEventRepository` bean | Having authentication does not automatically guarantee an audit store exists for the endpoint |
| `httpexchanges` | `HttpExchangeRepository` bean | Repository existing differs from recorded data existing; in-memory store has retention limits |
| `metrics` | Micrometer infrastructure, `MeterRegistry` bean | Having a registry differs from having the specific meter you query |
| `prometheus` | `micrometer-registry-prometheus` and corresponding Prometheus registry/infra | Having `metrics` does not automatically create the Prometheus scrape endpoint |
| `caches` | Spring's `CacheManager` class; endpoint receives managers in context | Boot 3.3 can create the endpoint with an empty manager map; do not enforce "must have one CacheManager" as a bean creation condition |
| `flyway` | `Flyway` class and bean | Adding only a database driver does not create a matching Flyway bean |
| `liquibase` | `SpringLiquibase` class and bean | A database having migration history does not mean the app configures Liquibase |
| `quartz` | Quartz `Scheduler` class and bean | `@Scheduled` tasks do not automatically become Quartz jobs |
| `integrationgraph` | Spring Integration and initialized Integration infrastructure | Having the library name alone does not prove Integration components are registered |
| `sessions` | Spring Session and stack-appropriate store: `SessionRepository` or `ReactiveSessionRepository` | Lookup by username also needs corresponding indexing capability; reading/deleting by ID is a separate capability |

The conditions for `Flyway`, `SpringLiquibase`, `Scheduler`, and Integration can be cross-checked in the auto-configuration source of [Flyway](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/flyway/FlywayEndpointAutoConfiguration.java), [Liquibase](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/liquibase/LiquibaseEndpointAutoConfiguration.java), [Quartz](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/quartz/QuartzEndpointAutoConfiguration.java), and [Integration Graph](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/integration/IntegrationGraphEndpointAutoConfiguration.java).

For `sessions`, note the version nuance: the Boot 3.3 overview table describes Servlet requirements, while [v3.3.0 code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/session/SessionsEndpointAutoConfiguration.java) already contains both Servlet and reactive branches. When overview docs and code differ, check the exact stack and implementation deployed.

Specifically for `metrics` and `prometheus`, distinguish a general registry from a registry serving a specific monitoring system. Refer to [Boot 3.3 Micrometer and registry auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 3.3. Endpoints Also Dependent on Startup Mode or Runtime Resources

| Endpoint | Condition to Check | What Must Not Be Inferred |
| --- | --- | --- |
| `startup` | Use `BufferingApplicationStartup` properly when starting the application | Exposing the endpoint cannot retroactively capture startup steps never recorded |
| `logfile` | Log file or external file properly configured; file must be readable | Console output does not automatically become a downloadable file for the endpoint |
| `heapdump` | Web channel and JVM runtime supporting the corresponding dump mechanism | GET can still impose significant resource cost and produce sensitive data |
| `shutdown` | Disabled by default; requires enablement/exposure and supported deployment model | Do not use this endpoint as a harmless read test; it stops the application |
| `sbom` | Available in Boot 3.3; content depends on supplied/configured SBOM resources | Having the endpoint does not prove a software bill of materials was generated |

`logfile` is a classic example of two condition layers: the endpoint bean may be created when file configuration is satisfied, yet a read request still needs the actual file resource. See [LogFileWebEndpoint auto-configuration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/logging/LogFileWebEndpointAutoConfiguration.java).

For `startup`, the application must choose the recording mechanism before startup, such as a snippet added into an existing main startup method:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setApplicationStartup(new BufferingApplicationStartup(2048));
application.run(args);
~~~

This snippet uses Boot's `SpringApplication` and `BufferingApplicationStartup` from `org.springframework.boot.context.metrics.buffering`; it is not a standalone Java program. Endpoint conditions live in [StartupEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/startup/StartupEndpointAutoConfiguration.java).

## 4. Reading Enabled and Exposure as Two Independent Decisions

Example management configuration for an existing web application:

~~~yaml
management:
  server:
    port: 9090
    address: 127.0.0.1
  endpoints:
    enabled-by-default: false
    web:
      base-path: /manage
      exposure:
        include: health,info,httpexchanges
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
    httpexchanges:
      enabled: true
~~~

The address to check for HTTP exchanges is:

~~~text
http://localhost:9090/manage/httpexchanges
~~~

The configuration above does not yet create `HttpExchangeRepository` and does not establish an access control policy. It only resolves enablement/exposure choices and the management address.

A bean for the lab can be registered in the application's `@Configuration` class:

~~~java
@Bean
HttpExchangeRepository httpExchangeRepository() {
    return new InMemoryHttpExchangeRepository();
}
~~~

This snippet requires importing `Bean`, `HttpExchangeRepository`, and `InMemoryHttpExchangeRepository` accordingly. An in-memory store serves short-term experimentation/diagnostics and is not implicitly a durable historical store.

Three rules to check:

1. `enabled=true` does not automatically expose the endpoint over HTTP.
2. `exposure.include` does not automatically enable an endpoint that is disabled.
3. `exposure.exclude` takes precedence over `include`.

If the endpoint is also exposed over JMX, excluding it from HTTP does not necessarily make the endpoint bean disappear. Distinguish **bean exists** from **HTTP mapping exists**. The experiment in the next section restricts configuration so no other exposure channel keeps the tested endpoint alive.

## 5. Java Experiment Verifying Endpoint Creation Conditions

The example uses `ApplicationContextRunner` to create lightweight contexts, vary individual conditions, and close each context. This is a Boot testing library tool; the program runs standalone to observe auto-configuration and **does not start an HTTP server**.

It loads only the two specified auto-configuration classes. Therefore, the output proves the conditions of those configurations and does not replace routing or security tests for the whole application.

### 5.1. Dependencies

In a separate lab directory, create `pom.xml`:

~~~xml
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
    <groupId>learning</groupId>
    <artifactId>endpoint-conditions-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-test</artifactId>
        </dependency>
        <dependency>
            <groupId>org.assertj</groupId>
            <artifactId>assertj-core</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Test dependencies are placed on the compilation classpath of the lab program because it runs via `main`. In a real application, do not move test libraries to runtime scope just to get endpoints.

### 5.2. Complete Program

Place `EndpointConditionsDemo.java` alongside `pom.xml`:

~~~java
import org.springframework.boot.actuate.autoconfigure.cache.CachesEndpointAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.web.exchanges.HttpExchangesEndpointAutoConfiguration;
import org.springframework.boot.actuate.cache.CachesEndpoint;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

public class EndpointConditionsDemo {
    public static void main(String[] args) {
        var base = new ApplicationContextRunner().withConfiguration(
                AutoConfigurations.of(
                        HttpExchangesEndpointAutoConfiguration.class,
                        CachesEndpointAutoConfiguration.class));

        var exposed = base.withPropertyValues(
                "management.endpoints.web.exposure.include=httpexchanges,caches");
        var withRepository = exposed.withBean(
                HttpExchangeRepository.class, InMemoryHttpExchangeRepository::new);

        show("exposed, no repository", exposed);
        show("exposed, with repository", withRepository);
        show("disabled", withRepository.withPropertyValues(
                "management.endpoint.httpexchanges.enabled=false"));
        show("excluded from web", withRepository.withPropertyValues(
                "management.endpoints.web.exposure.exclude=httpexchanges"));
        show("default exposure", base.withBean(
                HttpExchangeRepository.class, InMemoryHttpExchangeRepository::new));
        show("enabled explicitly, default exposure", base.withBean(
                HttpExchangeRepository.class, InMemoryHttpExchangeRepository::new)
                .withPropertyValues("management.endpoint.httpexchanges.enabled=true"));

        exposed.run(context -> {
            if (context.getStartupFailure() != null) {
                throw new IllegalStateException(context.getStartupFailure());
            }
            var caches = context.getBean(CachesEndpoint.class);
            System.out.println("caches without CacheManager: managers="
                    + caches.caches().getCacheManagers().size());
        });
    }

    private static void show(String label, ApplicationContextRunner runner) {
        runner.run(context -> {
            if (context.getStartupFailure() != null) {
                throw new IllegalStateException(context.getStartupFailure());
            }
            System.out.println(label + ": httpexchanges bean="
                    + context.containsBean("httpExchangesEndpoint"));
        });
    }
}
~~~

The experiment is based on the bean conditions of [HttpExchangesEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/web/exchanges/HttpExchangesEndpointAutoConfiguration.java) and how [CachesEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/cache/CachesEndpointAutoConfiguration.java) receives the cache manager map.

### 5.3. Compiling and Running

Requires JDK 17+, Maven; fetching dependencies the first time requires connectivity to the Maven repository.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$conditionsClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$conditionsClasspath" EndpointConditionsDemo.java
java -cp ".;$conditionsClasspath" EndpointConditionsDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
conditions_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$conditions_classpath" EndpointConditionsDemo.java
java -cp ".:$conditions_classpath" EndpointConditionsDemo
~~~

Stdout:

~~~text
exposed, no repository: httpexchanges bean=false
exposed, with repository: httpexchanges bean=true
disabled: httpexchanges bean=false
excluded from web: httpexchanges bean=false
default exposure: httpexchanges bean=false
enabled explicitly, default exposure: httpexchanges bean=false
caches without CacheManager: managers=0
~~~

Interpretation:

- Exposing `httpexchanges` without the repository does not create the endpoint bean.
- When both the repository and exposure config exist, the endpoint bean is created.
- Disabling the endpoint or excluding it from web both prevent the condition from matching within the context under test.
- Having the repository and enabling explicitly is still not enough when default exposure does not include that endpoint.
- `caches` exists and returns an empty manager map. This is proof you must not apply a single rule "every data endpoint must have at least one source bean" to all endpoints.

## 6. Permission to Call a URL Differs from Permission to View Inner Values

After confirming the endpoint has a mapping, inspect the security policy next.

### 6.1. Authentication and Authorization

- **Authentication:** who the caller is, or whether they hold valid credentials.
- **Authorization:** which specific operations the caller is permitted to perform.
- **Data display:** which contents are returned to a caller already permitted into the endpoint.

These three are not identical. An account allowed to GET `env` may still only see masked values; someone allowed to read loggers is not necessarily allowed to change log levels.

`env`, `configprops`, and `quartz` have `show-values` policies; `health` has detail/component visibility settings. Do not use `show-values=always` as a way to "fix 403": it does not grant URL access permissions, it alters what content is displayed.

Example policies to define for each operation group:

| Group/Operation | What Must Be Decided |
| --- | --- |
| Minimal `health` | Who can read status; who can view details |
| `info`, `metrics`, `prometheus` | Which operators/monitoring systems need access |
| `beans`, `conditions`, `mappings`, `env`, `configprops` | Who can read structural/configuration info |
| `auditevents`, `httpexchanges`, `sessions` | Who can read activity/user-related data |
| `flyway`, `liquibase`, `quartz`, `integrationgraph`, `scheduledtasks`, `startup`, `sbom` | Who needs to observe the corresponding data sources or infrastructure |
| `loggers` when changing log levels; `caches`/`sessions` when deleting | State-mutating permissions, distinct from read-only |
| `logfile`, `threaddump`, `heapdump` | Diagnostic collection permissions and permitted data/resource scope |
| `shutdown` | Permission to stop the application, kept separate from all read permissions |

These are application policy decisions, not role names Boot automatically provisions.

### 6.2. A Custom SecurityFilterChain Must Cover the Whole Application

When Spring Security is present and the application has not provided a `SecurityFilterChain`, Boot provides default Actuator protection. When declaring your own chains, you take responsibility for the scope the default configuration yields.

The example below is an **illustrative configuration for a Servlet app with Spring Security**, using roles supplied by the existing authentication system:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .requestMatchers(EndpointRequest.to("info", "metrics", "prometheus"))
                    .hasAnyRole("ACTUATOR_VIEW", "ACTUATOR_ADMIN")
                .anyRequest().hasRole("ACTUATOR_ADMIN"));
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
~~~

The example grants the viewer group access only to `info`, `metrics`, and `prometheus`; remaining endpoints require the admin role even for GET, except minimal health permitted above. The matcher uses endpoint IDs so it does not hard-code base paths; see [EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

This configuration does not create accounts and does not assign roles. `hasRole("ACTUATOR_ADMIN")` evaluates authorities using Spring Security's `ROLE_` prefix convention.

The first chain handles only Actuator scope; the second covers remaining requests. Before adding this to an app that already has chains, check existing ordering and matchers instead of adding a chain with overlapping responsibility.

### 6.3. CSRF Is a Separate Condition for Mutating Operations

The illustrative configuration keeps default CSRF protection. Consequently, someone holding the admin role who sends POST/DELETE without a valid CSRF token can still receive `403`.

Do not infer from "GET succeeded" that DELETE will succeed too. Nor should you disable CSRF application-wide just to skip finding the cause.

If an API strictly for non-browser clients requires a different strategy, decide based on the authentication model and exact endpoint scope. Source: [Boot 3.3 Actuator security and CSRF](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

## 7. Evaluate Down to Operation and Data Level, Not Just Endpoint Name

One endpoint can have multiple operations with different requirements.

For example:

- `caches`: reading the list differs from DELETE clearing a cache.
- `sessions`: reading/deleting by ID differs from searching by principal, which requires an indexed store.
- `loggers`: reading log levels differs from changing a log level.
- `health`: reading minimal status differs from viewing full details.
- `metrics`: listing meter names differs from querying whether a specific meter or tag combination exists.

For each operation, record:

~~~text
Endpoint ID
+ HTTP method and path
+ required dependency/runtime
+ data source bean
+ effective enabled/exposure configuration
+ caller permissions and CSRF condition
+ specific resource/parameters
+ response evidence
~~~

You do not need to open every endpoint to test one feature. For example, to verify Prometheus scraping, check the matching registry, endpoint configuration, and scraper permissions; do not use `include: "*"` as a default diagnostic method.

Also distinguish response types: many endpoints return JSON, while Prometheus serves a scrape format, heap dump returns file-like diagnostic data, and logfile returns log content. An inappropriate `Accept` header or HTTP method can produce errors distinct from permission errors.

## 8. Diagnosing from Evidence Inside Out

### 8.1. Confirm Exact Running Build and Runtime Dependencies

In a Gradle project, you can use the runtime classpath report or `dependencyInsight` on the running module to inspect actual libraries and versions.

Do not read only dependencies declared in the root build, because per-module configuration, optional dependencies, exclusions, or packaging may differ. Do not blindly add a library if the endpoint does not need it: a missing endpoint can also stem from beans/configuration/security.

### 8.2. Reading the Bean Creation Conditions Report

In the lab, you can enable the conditions report at startup:

~~~shell
java -jar app.jar --debug
~~~

`app.jar` here is the packaged filename of the application under check. When using this in a real project, run the exact built artifact with that environment's configuration.

Locate the corresponding auto-configuration class and read the exact reason: missing class, missing bean, endpoint not available, or application already provided a bean.

If the `conditions` endpoint is ready and the caller has permission, it is another source for reading the report. If that endpoint itself is unreachable, use startup logs; do not create a circular dependency of "must hit `conditions` to learn why `conditions` isn't open."

### 8.3. Checking Exposure Channel and Address

Confirm port, base path, context path, proxy routing, and whether HTTP or JMX is being checked. An endpoint bean in the context is not enough evidence that an HTTP URL exists.

The `/actuator` discovery page or changed base path can help locate links. However, the discovery page may be disabled or blocked; a missing link is not the sole proof of whether a bean exists.

### 8.4. Checking Request and Security

Record the exact HTTP method, path, query/body, required headers, identity/roles, and response code. Never record real passwords, tokens, or cookies in diagnostic reports.

| Response/Symptom | Initial Interpretation |
| --- | --- |
| Cannot connect | Check process, port, network, TLS before checking endpoint beans |
| `401` or login redirect | Check configured authentication mechanism and entry point |
| `403` | Check authorization and CSRF; do not treat it as proof authentication succeeded |
| `404` | Could be wrong path, unmapped endpoint, missing target object, or masked by another layer |
| `405` | Recheck which HTTP methods the operation supports |
| `400` | Check required parameters, binding, and input values |
| `406`/`415` | Check media type and body contract |
| `200` but empty/masked | Check data source or display policy; do not assume an exposure error |
| `503` from health | Read health status; do not equate with an authorization error |

These are triage directions, not absolute one-to-one mappings between HTTP codes and causes.

### 8.5. Confirming Data and Runtime Impact

Once able to reach the endpoint, verify the right source: does the repository have data, is the meter registered, does the file exist/is it readable, is the session store indexed properly.

Do not use POST/DELETE as harmless probes. A valid request can change log levels, clear caches, delete sessions, or stop the process. Choose data and test environments appropriate to the operation being proven.

## 9. Practicing Evaluation on Three Scenarios

### Scenario A: httpexchanges Returns 404 Despite Being Included

First check whether the endpoint is enabled and whether an `HttpExchangeRepository` exists. If the store is missing, tweaking permissions or re-adding the same include property will not satisfy the bean creation condition.

Once the store exists, proceed to check HTTP mapping and permissions. If you receive `200` with an empty list, move on to checking data recording/retention.

### Scenario B: metrics Works but prometheus Is Missing

Do not conclude all of Actuator is broken. Verify the Prometheus dependency and matching registry, auto-configuration conditions, exposure of `prometheus` itself, and then scraper permissions.

Another `MeterRegistry` can still make `metrics` work without providing the Prometheus scrape path.

### Scenario C: GET sessions Succeeds but DELETE Gets 403

Confirm both requests use the same identity and appropriate permission scope. Next check CSRF for DELETE. There is no evidence yet to change Spring Session dependencies or recreate session tables based solely on `403`.

**Self-check exercises:**

- Why are `enabled=true` and `include=httpexchanges` still insufficient when the repository bean is missing?
- Why is `caches` with an empty manager list different from an endpoint not being created?
- An endpoint bean remains alive via JMX yet has no HTTP URL: which configuration must be checked?
- A user can GET `env` but sees only masked values: which permission/policy layers must be distinguished?
- Why shouldn't you use a single `404` result to immediately decide a dependency is missing?

Evaluation results should pinpoint **which condition has evidence, which condition is unmet, and the specific operation under test**, rather than merely saying "the endpoint doesn't work."
