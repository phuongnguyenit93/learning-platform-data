# `extra-refreshable`, `never-refreshable`, and the `HikariDataSource` Case

This lesson belongs to the **Refresh Scope** chapter of the **SPRING_CLOUD_CORE** module. Spring Cloud Context can refresh certain beans when configuration changes. Beyond annotating beans directly with `@RefreshScope`, applications also have two properties to control which beans are included in or excluded from the refresh mechanism: `spring.cloud.refresh.extra-refreshable` and `spring.cloud.refresh.never-refreshable`.

These two properties address two different needs:

- **`extra-refreshable`:** adds beans by name or class name to refresh scope, typically useful when a bean comes from a library or auto-configuration whose definition the application cannot conveniently modify.
- **`never-refreshable`:** specifies beans by name or class name that must not be refreshed/rebound by Spring Cloud's mechanism.
- **`HikariDataSource`:** is an important exception; `com.zaxxer.hikari.HikariDataSource` is in the default `never-refreshable` list. Spring Cloud documentation recommends choosing a different `DataSource` implementation if DataSource refreshing is required.

Understand the scope of each property clearly before configuring it. Putting a connection pool, a socket-holding client, or a stateful bean into refresh scope by mistake can disrupt in-flight requests, create duplicate resources, or leave the application holding old connections. Conversely, excluding a bean from refresh when it truly needs updates can leave the application running with stale configuration.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain how refresh scope operates through a scoped proxy and target cache.
2. Distinguish beans annotated directly with `@RefreshScope` from beans added via `extra-refreshable`.
3. Configure `spring.cloud.refresh.extra-refreshable` using bean names or fully qualified class names.
4. Configure `spring.cloud.refresh.never-refreshable` to keep beans out of refresh/rebind.
5. Understand that the default `never-refreshable` list includes `HikariDataSource`.
6. Preserve the Hikari exclusion when the application overrides the `never-refreshable` list.
7. Explain why you should not force `HikariDataSource` into `extra-refreshable`.
8. Choose the appropriate strategy when database URLs, credentials, or pool settings change.
9. Test whether a bean is recreated or preserved after refresh.
10. Protect the refresh endpoint and observe errors when new targets fail to initialize.

## 2. How Does Refresh Scope Work?

Spring Cloud Context provides `RefreshScope`. Beans in this scope are accessed via a **scoped proxy**. The real target bean is initialized when the proxy receives the first call needing the target; the scope keeps the target in cache. Upon refresh, the cache entry is invalidated. The next call through the proxy creates a new target.

~~~mermaid
sequenceDiagram
    participant Caller as Service caller
    participant Proxy as Scoped proxy
    participant Cache as RefreshScope cache
    participant Target as Bean target
    Caller->>Proxy: Call method
    Proxy->>Cache: Get target
    Cache-->>Proxy: Current target
    Proxy->>Target: Execute method
    Target-->>Caller: Result
    Note over Cache: Refresh clears cache entry
    Caller->>Proxy: Next method call
    Proxy->>Cache: Get target
    Cache->>Target: Initialize new target if cache is empty
    Target-->>Proxy: New target
    Proxy->>Target: Execute method
~~~

This differs from mutating fields on a regular singleton. Callers usually hold the proxy throughout the context lifecycle; the target behind the proxy can be recreated.

### 2.1. Refresh Scope Does Not Automatically Detect Every Change

A refresh workflow typically requires these steps:

1. The configuration source changes.
2. New configuration is loaded into `Environment`.
3. Spring Cloud executes the refresh workflow.
4. Target caches of refresh-scoped beans are cleared.
5. The next call creates a new target using active configuration.

Merely editing a file on disk without a reload mechanism does not mean `Environment` has changed. If `Environment` changed without a refresh event/workflow, cached targets may still be used.

### 2.2. Refresh Scope Does Not Mean Restarting the Entire JVM

Refresh scope only manages targets of beans belonging to the scope. It does not restart the process, does not update every singleton automatically, and does not guarantee every external resource is replaced safely.

Beans depending on a refreshed target may continue holding stale state if they themselves snapshotted data in their constructors. Inspect the full dependency chain and how callers retain references.

## 3. Distinguishing the Three Mechanisms

| Mechanism | How it is declared | Effect |
| --- | --- | --- |
| `@RefreshScope` | Place annotation on a bean or bean method. | Bean is registered with refresh scope and accessed via proxy. |
| `spring.cloud.refresh.extra-refreshable` | List bean names or class names. | Spring Cloud adds matching beans to refresh scope when processing bean definitions. |
| `spring.cloud.refresh.never-refreshable` | List bean names or class names. | Spring Cloud excludes specified beans from refresh/rebind under the corresponding mechanism. |

Do not treat the two properties as symmetrical lists:

- `extra-refreshable` expands the set of beans post-processed into refresh scope.
- `never-refreshable` is an exclusion list that includes the default exclusion for `HikariDataSource`.
- Beans already annotated with `@RefreshScope` do not need to be listed again just to repeat the same intent.
- Do not configure the same bean in both lists; doing so creates conflicting operational intent and makes verification difficult.

### 3.1. When to Use the Annotation Directly?

If you own the source code and bean definitions, the clearest approach is usually annotating the bean directly:

~~~java
@Configuration
class RemoteClientConfiguration {

    @Bean
    @RefreshScope
    RemoteCatalogClient remoteCatalogClient(
            @Value("${catalog.base-url}") URI baseUrl) {
        return new RemoteCatalogClient(baseUrl);
    }
}
~~~

The bean is declared explicitly right where it is created. Code readers can recognize its refresh lifecycle without hunting for a global property.

### 3.2. When to Use `extra-refreshable`?

Use it when you do not control the bean definition, such as:

- Beans created by a third-party library's auto-configuration.
- Beans created from a module the application prefers not to modify.
- Beans that need to be placed in refresh scope by deployment policy.
- Situations where annotations cannot be added to the class or bean-creating method.

For example, a library provides `LegacyCatalogClient` and the bean is named `legacyCatalogClient`. The application can add the class or bean name to `extra-refreshable`.

Do not add every class in a package to the list. Only select beans that can be safely recreated and have compatible proxying paths.

### 3.3. When to Use `never-refreshable`?

Use it when a bean must not be replaced or rebound automatically during refresh workflows. Examples:

- Beans holding resources with complex lifecycles.
- Library components unsafe to recreate while requests are in flight.
- Beans that need to be replaced via a separate rollout or rotation procedure.
- `HikariDataSource`, which Spring Cloud already excludes from refresh by default.

This list acts as an operational constraint. When adding a bean to it, you must have an alternative plan for updating that bean's configuration, such as restart/rolling deployment or a dedicated resource-management process.

## 4. `spring.cloud.refresh.extra-refreshable`

### 4.1. Meaning and Matching Rules

`spring.cloud.refresh.extra-refreshable` accepts additional **bean names or class names** of beans to post-process into refresh scope.

Configuration example:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: com.example.catalog.LegacyCatalogClient,legacyCatalogClient
~~~

Where:

- `com.example.catalog.LegacyCatalogClient` is the fully qualified class name.
- `legacyCatalogClient` is the bean name.
- The list is comma-separated in the configuration value.

If a class is specified, Spring Cloud needs to resolve the bean definition's type. When beans are created via factory methods, the declared return type and bean definition metadata affect type detection. If matching does not behave as expected, inspect the actual bean name and type in the `ApplicationContext`.

### 4.2. When Are Beans Added to Refresh Scope?

Spring Cloud has a bean-definition post-processor to handle the extra-refreshable list. During bean definition registration, matching beans are switched to refresh scope and given scoped proxies.

This implies:

- The property must be available while `ApplicationContext` is building bean definitions.
- This is not an operation that attaches an annotation after beans have already initialized.
- Changing this property at runtime does not automatically turn an existing bean into a refresh-scoped bean.
- Changing scope policies typically requires restarting the application with the new configuration.

### 4.3. Example with a Third-Party Bean

Suppose a library creates a bean:

~~~java
@Configuration
class VendorClientConfiguration {

    @Bean
    LegacyCatalogClient legacyCatalogClient(
            CatalogProperties properties) {
        return new LegacyCatalogClient(properties.baseUrl());
    }
}
~~~

If you cannot modify the library's class or method to add `@RefreshScope`, the configuration can be:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: legacyCatalogClient
~~~

After the application starts with this configuration, callers receive the bean through a refresh-scope proxy. When the refresh workflow clears the target cache, the next call recreates the target.

### 4.4. Use Class Name or Bean Name?

| Criterion | Bean name | Class name |
| --- | --- | --- |
| Scope | Targets one specific bean. | Can apply to beans matching the type. |
| Stability | Depends on bean naming conventions. | Depends on the class used and how Spring resolves its type. |
| Useful when | Only one bean in the application needs refresh. | Applying policy by implementation class. |
| What to verify | Actual bean name in context. | Fully qualified class name and bean definition type. |

Prefer bean name when targeting a single specific bean. Use class name when the policy applies by implementation and you have verified how Spring resolves the type.

### 4.5. What `extra-refreshable` Does Not Do

This property does not:

- Reload configuration files or call Config Server on its own.
- Emit refresh events automatically.
- Automatically update every singleton depending on the bean.
- Guarantee the bean is proxyable under every declaration style.
- Guarantee creating the new target will succeed without errors.
- Guarantee old target resources are handled properly if the class lacks an appropriate lifecycle.

If a bean is `final`, has APIs coupled to a concrete class, or is incompatible with the proxy strategy, verify it in an integration test before deploying.

## 5. `spring.cloud.refresh.never-refreshable`

### 5.1. Meaning

`spring.cloud.refresh.never-refreshable` is a list of bean names or class names that must not be refreshed/rebound by Spring Cloud's mechanism.

Example:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

In this example:

- `HikariDataSource` stays on the non-refreshable list.
- `ImmutableKeyStore` is also excluded from refresh/rebind.
- Other beans follow default policies or their own annotations/scopes.

This list must be designed around operational requirements. If a bean is excluded from refresh, do not expect `Environment` changes to update that bean automatically.

### 5.2. Default Value Includes `HikariDataSource`

According to current Spring Cloud Commons documentation, `com.zaxxer.hikari.HikariDataSource` is the default value of `spring.cloud.refresh.never-refreshable`.

This is an important exception for applications using Spring Boot's default JDBC connection pool. Spring Cloud does not refresh `HikariDataSource` via the standard mechanism. If a refreshable `DataSource` is needed, the documentation recommends choosing another `DataSource` implementation.

### 5.3. Overriding the List Must Preserve Hikari

When declaring `spring.cloud.refresh.never-refreshable` in application configuration, your configured value replaces the default value used when the property is absent. Therefore, if you add another class to the list, keep `HikariDataSource` if the application still uses it.

Correct example when excluding an additional bean while preserving the Hikari exception:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Error-prone example:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.example.security.ImmutableKeyStore
~~~

In the second example, the configuration no longer lists `com.zaxxer.hikari.HikariDataSource`. If the application uses Hikari, proactively keep this class in the exclusion list as instructed by Spring Cloud.

Do not treat the list as automatically appended to the defaults. Explicitly configure all necessary exclusions.

### 5.4. `never-refreshable` Is Not a Bean Update Mechanism

Adding a bean to `never-refreshable` only prevents refresh/rebind mechanisms from applying to that bean. It does not on its own:

- Create a new instance.
- Reload configuration.
- Close old resources.
- Open new connections.
- Route requests to another bean.

If the bean needs configuration changes, design another controlled process such as restarting or rolling out instances.

## 6. The `HikariDataSource` Case

### 6.1. What Does HikariCP Hold?

`HikariDataSource` is a `DataSource` implementation using the HikariCP connection pool. It manages JDBC connections so multiple requests can borrow and return connections instead of opening a new connection per operation.

An active pool may hold:

- Connections actively in use by requests.
- Idle connections ready for the next borrow.
- Pool management threads and connection state.
- Bounds, timeouts, and pool lifecycle settings.

Changing a database URL or credentials touches an actively running resource. It cannot be treated like swapping a simple configuration string.

### 6.2. Why Doesn't Hikari Refresh by Default?

Spring Cloud Commons explicitly notes that `HikariDataSource` is in the default `never-refreshable` list and cannot be refreshed through this mechanism. When a refreshable `DataSource` is needed, the documentation recommends choosing another implementation.

Respect the framework's documented boundary. Do not try to put Hikari into `extra-refreshable` or strip the exclusion from `never-refreshable` just to force the refresh endpoint through.

Official documentation states this behavior and recommendation; concrete `DataSource` decisions must be evaluated alongside the driver, transaction manager, pool lifecycle, and system downtime requirements.

### 6.3. Typical Hikari Configuration

Initial configuration example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: order_service
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      connection-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

These values are read when creating the `DataSource`/pool. Changing `Environment` later does not cause the Hikari pool to close itself and recreate with the new URL or credentials.

If the application uses Hikari, plan connection parameter changes using one of these approaches:

- Restart/rolling-restart instances with the new configuration.
- Deploy a new configuration version accompanied by health/readiness checks.
- Use an application-managed pool rotation mechanism if runtime pool swapping is truly needed; that mechanism must handle borrowed connections, active transactions, and closing the old pool at the right time.

The third option is a custom application lifecycle design, not an automatic feature provided by `extra-refreshable`.

### 6.4. When to Choose a Different `DataSource` Implementation?

If a system requirement is changing the database URL or `DataSource` configuration at runtime via Spring Cloud refresh, evaluate a different `DataSource` implementation supported by Spring Cloud in refresh scope.

Choosing a different implementation still requires verifying:

- Can it be safely recreated through a proxy?
- Do beans and dependencies retain references to the old instance?
- How are currently borrowed connections handled?
- Can active transactions complete?
- When is the old pool closed?
- Is the new target health-checked before receiving requests?
- If the new target fails to initialize, can the application fall back to the old state or transition to `DOWN`?

Do not switch implementations merely to bypass the `never-refreshable` list. Verify actual pool semantics and lifecycles.

## 7. Configuring Both Properties in an Application

### 7.1. Combined Example

An application has a legacy client bean needing refresh while continuing to use `HikariDataSource`:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: com.example.catalog.LegacyCatalogClient
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Meaning:

- `LegacyCatalogClient` is added to refresh scope.
- `HikariDataSource` stays in the non-refreshable/non-rebindable list.
- `ImmutableKeyStore` is also excluded from refresh/rebind.
- Beans not in either list follow their annotations and default mechanisms.

If `LegacyCatalogClient` is already annotated directly with `@RefreshScope`, there is no need to also add that class to `extra-refreshable`.

### 7.2. Environment Variables

Spring Boot supports passing these properties via environment variables. Example:

~~~bash
SPRING_CLOUD_REFRESH_EXTRA_REFRESHABLE=com.example.catalog.LegacyCatalogClient
SPRING_CLOUD_REFRESH_NEVER_REFRESHABLE=com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

When running containers or service managers, set environment variables in deployment configuration and verify the process receives the exact values. These are startup configuration properties; changing environment variables in a terminal after the process is already running does not alter already-processed bean definitions.

### 7.3. Do Not Place One Bean in Both Lists with Contradictory Intent

A bean should not be simultaneously marked as needing refresh and excluded from refresh. If a bean must remain untouched, put it only in `never-refreshable`. If its target must be recreated, use `@RefreshScope` or `extra-refreshable`.

If exclusion policies mix bean names and class names, document them clearly in deployment notes so upgrades do not accidentally add the same bean to both groups.

## 8. How to Refresh and Verify Beans

### 8.1. Exposing the Refresh Endpoint in a Lab Environment

If the application already has Actuator and Spring Cloud Context, the refresh endpoint can be exposed:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Send request:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

The endpoint must be properly configured, exposed, and secured. Never expose the refresh endpoint to the public Internet or allow arbitrary users to call it. Production requires authentication, authorization, network restrictions, and auditing.

### 8.2. Refreshing All or Individual Beans

Spring Cloud provides `RefreshScope` with these operations:

- `refreshAll()`: clears cached targets of refresh-scoped beans.
- `refresh(String name)`: clears the cached target of a bean by name.

When using `/actuator/refresh`, Spring Cloud runs the corresponding refresh workflow. Invalidated targets are recreated on the next call through their proxies.

Do not confuse invoking refresh scope with updating `PropertySource`. The configuration source must actually be updated before new targets are created.

### 8.3. Health Indicator

Spring Cloud includes `RefreshScopeHealthIndicator` to track refresh scope status. If a bean fails to re-initialize or rebind after refresh, the health indicator can transition to `DOWN` and surface the related exception details.

Integrate this status into health/monitoring in line with the application's readiness policy. Do not mask new-target initialization failures by merely logging them while continuing to report the instance as healthy.

## 9. Testing `extra-refreshable`

### 9.1. Objective

Test a bean without `@RefreshScope` that is brought into refresh scope via bean name or class name.

A lab bean:

~~~java
public class LegacyCatalogClient {
    private final int generation;

    public LegacyCatalogClient(int generation) {
        this.generation = generation;
    }

    public int generation() {
        return generation;
    }
}
~~~

Bean declaration:

~~~java
@Configuration
class LegacyCatalogConfiguration {

    @Bean
    LegacyCatalogClient legacyCatalogClient(GenerationCounter counter) {
        return new LegacyCatalogClient(counter.next());
    }
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable: legacyCatalogClient
~~~

`GenerationCounter` is a lab bean that increments a number each time the factory is called. After application startup, call `generation()` to record the initial target. After refresh scope is refreshed, call again through the proxy and verify the new target has a different generation.

### 9.2. Test Scenario

1. Start `ApplicationContext` with `extra-refreshable` configured.
2. Inject `LegacyCatalogClient` into a singleton caller.
3. Call the method and record the initial generation.
4. Call `RefreshScope.refreshAll()` or refresh the bean by name.
5. Call the method again through the same reference held by the caller.
6. Verify the target was recreated.
7. Inspect target initialization logs and exceptions if the factory fails.

Expected result: the caller holds the proxy; the inner target is recreated after cache invalidation. If the caller holds the target directly instead of the proxy, the test may not reflect refresh scope behavior.

### 9.3. Verifying Class Name vs. Bean Name

Run two independent cases:

| Configuration style | Value | What to verify |
| --- | --- | --- |
| Bean name | `legacyCatalogClient` | Exact single bean is placed in refresh scope. |
| Class name | `com.example.catalog.LegacyCatalogClient` | Beans with matching type are recognized and proxied. |

If the class name does not match, inspect the actual bean type Spring resolves. For factory methods, declare concrete return types when possible and inspect bean definition metadata.

## 10. Testing `never-refreshable` and Hikari

### 10.1. Checking the Default List

In an application using Spring Cloud Context, verify `spring.cloud.refresh.never-refreshable` defaults to containing:

~~~text
com.zaxxer.hikari.HikariDataSource
~~~

You can check the resolved configuration via `Environment` in an integration test. No real database connection is needed just to check class names in the list.

### 10.2. Testing When Overriding the List

Suppose the application wants to add `com.example.security.ImmutableKeyStore` to the list. Configuration must keep Hikari as well:

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable: com.zaxxer.hikari.HikariDataSource,com.example.security.ImmutableKeyStore
~~~

Tests should verify:
- `HikariDataSource` is still present in the exclusion list.
- `ImmutableKeyStore` is present in the exclusion list.
- Other beans are not unintentionally excluded.
- No bean is configured in both `extra-refreshable` and `never-refreshable`.

### 10.3. Verifying `DataSource` Behavior

For an application actually using Hikari:

1. Confirm the runtime implementation of the `DataSource` bean.
2. Record non-sensitive URL/metadata and pool status.
3. Modify the source configuration in the test environment.
4. Run the refresh workflow.
5. Verify `HikariDataSource` is not replaced via the normal refresh mechanism.
6. Check that the application continues using the active pool or performs a rollout per designed procedures.
7. Never log passwords, JDBC URLs containing credentials, or sensitive connection data.

Do not conclude a new database URL took effect merely because `Environment` returns the new URL. Inspect the actual `DataSource` and new connections.

## 11. Decision Matrix

| Bean type | Appropriate policy | Reason |
| --- | --- | --- |
| Custom client bean needing recreation when config changes | `@RefreshScope` | Intent is declared right on the bean. |
| Library bean whose annotations cannot be edited | `extra-refreshable` | Can be selected by bean name or class name. |
| Bean holding resources unsafe to recreate | `never-refreshable` | Excluded from automatic refresh/rebind. |
| `HikariDataSource` | Keep in default `never-refreshable` | Spring Cloud does not support refreshing Hikari via this mechanism. |
| Other `DataSource` implementation with suitable lifecycle | Evaluate `@RefreshScope` or `extra-refreshable` | Must verify connection lifecycle and proxying. |
| Constructor-bound configuration properties | Do not use `extra-refreshable` assuming constructor rebinding | Requires dedicated snapshot/refresh scope design or restart. |
| Bean with dependencies holding stale references | Evaluate entire dependency graph | Refreshing target does not change snapshot state in callers. |

## 12. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Bean is not refreshed despite `extra-refreshable` config | Wrong bean/class name or bean definition not matched as expected | Check bean name, runtime type, and property loaded at startup. |
| Bean refreshed, yet caller still sees old value | Caller holds old target/reference or does not call via proxy | Inject and use scoped proxy; do not store target directly. |
| New bean fails initialization after refresh | New config is invalid or dependency is not ready | Check exceptions, health indicator, and pre-refresh validation. |
| `HikariDataSource` stays unchanged after refresh | Default behavior under `never-refreshable` | Use rollout/restart or evaluate another `DataSource` implementation. |
| Adding another bean to `never-refreshable` drops Hikari | New config overrode default without retaining Hikari | Re-add `com.zaxxer.hikari.HikariDataSource` to the list. |
| Hikari configured in `extra-refreshable` | Mistaking `extra-refreshable` as an override for `never-refreshable` | Remove Hikari from `extra-refreshable`; keep it in `never-refreshable`. |
| Bean excluded from refresh even though updates are needed | Bean/class name accidentally placed in `never-refreshable` | Review lists and choose one clear policy per bean. |
| Changing `extra-refreshable` at runtime has no effect | Bean definitions were already processed at startup | Restart with the new configuration. |
| Refresh endpoint returns 404 | Missing Actuator/Cloud Context or endpoint not exposed | Check dependencies and management endpoint configuration. |
| Refresh endpoint returns 401/403 | Security blocks administrative operation | Grant access to admin principal and keep endpoint on trusted network. |
| Old pool still active after config change | `DataSource` is not in refresh scope or is in `never-refreshable` | Check actual implementation and rollout/pool-rotation procedure. |

## 13. Safe Operational Principles

1. **Only add beans that truly need refresh.** Do not use `extra-refreshable` as a blanket list for all beans in the application.
2. **Keep Hikari in `never-refreshable`.** If overriding this property, re-include Hikari's fully qualified class name.
3. **Do not force Hikari into refresh scope.** Choose another `DataSource` implementation or design a dedicated pool rotation if runtime changes are required.
4. **Evaluate the dependency graph.** Dependent beans may keep old snapshots or resources even when underlying targets refresh.
5. **Validate before refreshing.** New configuration should be validated before entering `Environment` and creating new targets.
6. **Observe reinitialization.** Log bean name, revision, and initialization outcome; never log secrets.
7. **Have a rollback plan.** If a new target fails to initialize, know how to restore the prior revision or roll back.
8. **Protect management endpoints.** Refresh alters runtime state and requires authentication, authorization, auditing, and network restrictions.
9. **Check multiple instances.** Refreshing one instance does not automatically update the entire cluster; use broadcast or controlled rollout.
10. **Verify version compatibility.** Auto-configuration behavior and default lists must be checked against your actual Spring Cloud release train.

## 14. Completion Checklist

- [ ] Can explain `RefreshScope`'s scoped proxy and target cache.
- [ ] Can distinguish `@RefreshScope` from `spring.cloud.refresh.extra-refreshable`.
- [ ] Know that `extra-refreshable` accepts bean names or class names.
- [ ] Know that `extra-refreshable` is processed during bean definition registration.
- [ ] Can distinguish `extra-refreshable` from `never-refreshable`.
- [ ] Know that `spring.cloud.refresh.never-refreshable` lists beans excluded from refresh/rebind.
- [ ] Remember that `com.zaxxer.hikari.HikariDataSource` is the default exclusion in `never-refreshable`.
- [ ] When overriding `never-refreshable`, retain Hikari if the application uses it.
- [ ] Do not put Hikari into `extra-refreshable` to force pool refreshes.
- [ ] Can choose restart/rollout or another `DataSource` implementation when database configuration changes.
- [ ] Have tests proving `extra-refreshable` creates a new target after refresh.
- [ ] Have tests checking `never-refreshable` and Hikari exclusion.
- [ ] Check health indicators and logs when targets fail to initialize.
- [ ] Secure the refresh endpoint and establish auditing/rollback.
- [ ] Verify each instance's state after refresh in distributed environments.

**Official documentation to cross-check for your project version:**

- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `RefreshScope`, `extra-refreshable`, `never-refreshable`, `HikariDataSource`, and refresh health indicator.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): descriptions of `spring.cloud.refresh.extra-refreshable` and `spring.cloud.refresh.never-refreshable`.
- [Spring Cloud Commons – RefreshAutoConfiguration](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/autoconfigure/RefreshAutoConfiguration.java): how Spring Cloud processes bean definitions and refresh configuration.

Verify your exact Spring Boot/Spring Cloud release train before applying. Especially for `DataSource`, verify the runtime implementation, bean type, and connection lifecycle rather than inferring behavior from `Environment` values.
