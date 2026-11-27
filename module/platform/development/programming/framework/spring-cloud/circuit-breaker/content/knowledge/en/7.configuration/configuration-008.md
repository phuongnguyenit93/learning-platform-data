# Profile-Based Configuration and Verifying Applied Values

In a Spring Cloud Circuit Breaker application, the same breaker may need different failure thresholds, wait durations, and timeouts in development, test, and production environments. Spring Boot supports splitting configuration by profile so each environment loads an appropriate set of values. However, the configuration written in a file is not always the effective configuration: environment variables, command-line arguments, external files, or ID-specific configurations may override those values.

This lesson covers managing profiles for Resilience4j, keeping configuration IDs consistent with the factory, and verifying the final values loaded by the application. Verification is critical because a misconfigured Circuit Breaker can open too early, recover too slowly, or fail to protect calls to a dependent service.

## 1. Profiles in Spring Boot

A profile is a named group of configurations activated according to the environment or purpose of running the application. For example, `dev` is for local development, `test` for integration testing, and `prod` for production. Spring Boot loads common configuration and then applies configuration sections belonging to the active profiles.

There are two common ways to separate configuration:

- Using separate files such as `application-dev.yml`, `application-test.yml`, and `application-prod.yml`. A profile-suffixed file is loaded only when the corresponding profile is active.
- Using multiple YAML documents in the same `application.yml`, separated by `---` and specifying activation conditions via `spring.config.activate.on-profile`.

For applications running in production, select the profile from the deployment environment or startup arguments rather than hardcoding the production profile inside a configuration file packaged with the application.

## 2. Activating profiles

You can activate a profile using an environment variable:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
```

Or pass a startup argument:

```bash
java -jar app.jar --spring.profiles.active=prod
```

In a container, orchestrator, or deployment pipeline, you can set `SPRING_PROFILES_ACTIVE=prod` in the workload configuration. For multiple profiles, separate them with commas, such as `dev,metrics`.

`spring.profiles.active` and `spring.profiles.default` are properties used to select profiles, so they must be placed in a profile-independent configuration source, such as environment variables, command-line arguments, or the common document. Do not put `spring.profiles.active` inside a document that is itself activated by another profile. If no profile is activated, Spring Boot uses the `default` profile.

## 3. Splitting Circuit Breaker configuration across profile files

An example common configuration in `application.yml` declares the application name and basic observability settings:

```yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

In `application-dev.yml`, you can use easier-to-observe thresholds and shorter wait durations for quick testing:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallRateThreshold: 80
        slowCallDurationThreshold: 1s
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 2

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
```

In `application-prod.yml`, choose thresholds appropriate for real traffic and the inventory service's SLA:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 50
        failureRateThreshold: 40
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 1200ms
```

These are illustrative values, not default recommendations for every system. `TIME_BASED` with `slidingWindowSize: 30` means a 30-second observation window; `COUNT_BASED` with `slidingWindowSize: 10` means a window of up to the 10 most recent calls. `minimumNumberOfCalls` prevents the breaker from evaluating failure rates before enough samples exist. Choose values based on traffic, normal latency, recovery time, and business tolerance for fallbacks.

In both files, the ID `inventory` must match the ID the application code uses when creating the breaker, such as `circuitBreakerFactory.create("inventory")` or `reactiveCircuitBreakerFactory.create("inventory")`. Configuring a different ID will not affect the breaker protecting the call.

## 4. Using multiple YAML documents in the same application.yml

If you prefer keeping configuration in a single file, separate documents with `---`. The first document contains common settings; subsequent documents load only when the profile condition matches:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true

---
spring:
  config:
    activate:
      on-profile: dev

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 5s

---
spring:
  config:
    activate:
      on-profile: prod

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 50
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
```

`spring.config.activate.on-profile` specifies that the document is added to the Environment when the matching profile is active. When using a separate file `application-dev.yml`, there is no need to declare this condition inside the file because the filename itself binds it to the `dev` profile.

Avoid declaring the same property in multiple places unintentionally. When multiple sources provide a value, the higher-precedence source wins; someone reading a file might assume the YAML value is active while runtime actually receives a value from the environment or startup arguments.

## 5. Understanding configuration precedence order

Spring Boot merges properties from multiple sources. Keep these important operational rules in mind:

- Application default values have low precedence.
- Within Config Data, configuration files outside the artifact generally take precedence over files packaged inside the artifact; files for active profiles override common files at the same configuration location.
- Environment variables and JVM system properties can override values in configuration files.
- `SPRING_APPLICATION_JSON` can supply overriding values; application command-line arguments generally take higher precedence than the sources above.

These are general guidelines to direct investigation, not an exhaustive list of every property source. The exact order depends on configuration source type, file location, profile, and how the application is launched. When investigating an unexpected value, inspect the property source list and property origin rather than searching only in `application.yml`.

For example, `application-prod.yml` sets `failureRateThreshold: 40`, yet the launch command includes `--resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold=25`. In that case, the value 25 from the command-line argument has higher precedence and is used. This might be intentional for a rollout, or it could be a leftover environment variable.

Spring Boot's environment variable naming rule converts property names to uppercase, replaces dots with underscores, and removes hyphens. For example, the property:

```text
resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold
```

can be set via the environment variable:

```text
RESILIENCE4J_CIRCUITBREAKER_INSTANCES_INVENTORY_FAILURERATETHRESHOLD
```

For complex names, check the relaxed binding rules of the Spring Boot version in use and verify the value after the application starts. Do not guess an environment variable name and assume it bound successfully.

## 6. Configuring Spring Cloud CircuitBreaker by ID

Spring Cloud CircuitBreaker uses the ID passed to the factory to select the breaker's configuration. Reactive example:

```java
ReactiveCircuitBreaker inventoryBreaker =
        reactiveCircuitBreakerFactory.create("inventory");

return inventoryBreaker.run(
        inventoryClient.getStock(sku),
        error -> Mono.just(Stock.unavailable(sku))
);
```

For synchronous calls, the corresponding API is `circuitBreakerFactory.create("inventory")`. The name `inventory` must match the key under `resilience4j.circuitbreaker.instances` and `resilience4j.timelimiter.instances`.

Spring Cloud CircuitBreaker allows default, group, and ID-specific configuration. When using properties, per-instance configuration can override group or default configuration. Property configuration has higher precedence than Java `Customizer`. Consequently, if a `Customizer` bean sets `failureRateThreshold` to 50 while a profile file or environment variable sets it to 30, the value from properties takes precedence.

To avoid confusion, choose one primary configuration source for each environment. Use `Customizer` for settings that must be built in code or conditional logic; use properties for operational values that need to change per profile or deployment without recompiling the application.

## 7. Verifying the active profile

First, confirm the application is actually running with the expected profile. You can check at startup via Spring Boot logs or by reading `Environment`:

```java
@Component
public class ActiveProfileLogger implements ApplicationRunner {
    private static final Logger log =
            LoggerFactory.getLogger(ActiveProfileLogger.class);

    private final Environment environment;

    public ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles()));
    }
}
```

The example requires imports for `ApplicationArguments`, `ApplicationRunner`, `Component`, `Environment`, `Logger`, `LoggerFactory`, and `Arrays`. In real applications, log only non-sensitive configuration details. Never print the entire Environment because it may contain tokens, passwords, or connection credentials.

If the output is an empty array, check `SPRING_PROFILES_ACTIVE`, `--spring.profiles.active`, deployment configuration, and the default profile. If multiple profiles are active, check their order because a profile activated later can override values from an earlier profile.

## 8. Verifying effective property values

Spring Boot Actuator provides the `env` endpoint to inspect property sources and the `configprops` endpoint to inspect beans bound from configuration. In test environments, you can expose them in a controlled manner:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,metrics
```

Example inspecting a specific property through the endpoint:

```text
GET /actuator/env/resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold
```

The response can show the resolved value and which property source supplied it. `configprops` is useful when inspecting bound configuration objects. Endpoint names, response structure, and value masking policies may vary across Spring Boot versions.

Expose `env` and `configprops` only in controlled environments protected by authentication and authorization. These endpoints can disclose internal information; Spring Boot includes sensitive-value masking, but do not rely on automatic masking to expose them publicly. Production should normally expose only endpoints strictly necessary for monitoring.

For non-sensitive properties, you can check directly via `Environment`:

```java
String threshold = environment.getProperty(
        "resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold");
log.info("Inventory failure threshold: {}", threshold);
```

This check reports the resolved value from Environment. It does not prove every bean was constructed with that value if configuration is read manually or a `Customizer` modifies the builder afterward. When final verification is needed, inspect the bean/registry or actual breaker behavior.

## 9. Verifying Resilience4j configuration and breaker behavior

If the application uses `CircuitBreakerRegistry` directly, you can read the instance's configuration after the registry has created the breaker:

```java
CircuitBreaker breaker = circuitBreakerRegistry.circuitBreaker("inventory");
CircuitBreakerConfig config = breaker.getCircuitBreakerConfig();

log.info("Inventory failure threshold: {}",
        config.getFailureRateThreshold());
log.info("Inventory sliding window size: {}",
        config.getSlidingWindowSize());
log.info("Inventory minimum calls: {}",
        config.getMinimumNumberOfCalls());
log.info("Inventory slow-call threshold: {}",
        config.getSlowCallRateThreshold());
```

Reading the registry this way applies when the application has access to Resilience4j's `CircuitBreakerRegistry`. With Spring Cloud CircuitBreaker, the factory manages breaker creation and does not always expose the registry directly to application code; in that case, rely on property origins, metrics, and behavioral testing rather than assuming the registry can be injected.

To verify behavior, use a mock service and perform these steps:

1. Start the application with the `dev` profile; confirm the active profile and threshold/wait values resolve to match `application-dev.yml`.
2. Have the dependency return controlled errors, send at least the minimum number of calls, and confirm the `inventory` breaker transitions to `OPEN` at the profile's threshold.
3. Send additional requests while the circuit is `OPEN`; confirm calls to the dependency are blocked and the fallback returns the expected result.
4. Restart with the `prod` profile; confirm values from the production file are loaded and deployment parameters do not unintentionally override them.
5. Wait past `waitDurationInOpenState`, let the dependency recover, and confirm probe calls in `HALF_OPEN` return the breaker to `CLOSED`.
6. Cross-check property origins, metrics, logs, and actual request counts on the mock server to catch discrepancies between intended and running configuration.

Do not look solely at a single value in `/actuator/env`. A reliable check combines active profiles, resolved property sources, instance configuration, and Circuit Breaker behavior.

## 10. Investigation workflow when configuration does not take effect

When running values differ from the configuration file, check in order:

- Confirm the right artifact and target deployment environment are running.
- Confirm active profiles and any additional profiles.
- Check whether the profile file is in a location Spring Boot searches and is named exactly `application-{profile}.yml`.
- Check whether environment variables, JVM system properties, `SPRING_APPLICATION_JSON`, or command-line arguments override the property.
- Check whether the ID in `create(...)` matches the ID in Resilience4j configuration.
- Check Spring Cloud CircuitBreaker instance, group, and default configuration; check `Customizer` if the project uses one.
- Use Actuator or selective logging to identify the property source and bound value.
- Run a controlled failure scenario to confirm the breaker opens, rejects requests, and recovers on schedule.

Do not tweak thresholds just to make a dashboard look healthy. Find the overriding source first, then adjust the proper configuration source managed by the operations team.

## 11. Common mistakes

- Placing `spring.profiles.active` inside a document activated only by another profile, causing invalid profile configuration or unexpected loading behavior.
- Assuming `application-prod.yml` is always used even when the `prod` profile has not been activated.
- Letting environment variables or command-line arguments override YAML files unnoticed.
- Using different IDs across the factory, Circuit Breaker instance, and TimeLimiter instance.
- Putting the same value in YAML, `Customizer`, and environment variables without clarifying which source is authoritative.
- Inspecting only the configuration file without checking active profiles, property sources, and runtime values.
- Exposing `/actuator/env` or `/actuator/configprops` publicly, leaking internal details.
- Using identical thresholds for dev and production even though traffic, SLAs, and recovery times differ between the two environments.

## References

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profiles, configuration files, property sources, precedence order, and environment variables.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile activation and profile conditions in YAML documents.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): default, group, instance, properties, and Customizer configuration.
- [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`, `configprops`, `metrics` endpoints and exposure control.
