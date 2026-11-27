# Configuration Group Scoping and Per-Feign-Client Selection

A Spring application may declare multiple Feign clients to call services such as inventory, payment, shipping, and customer management. Clients often share certain settings such as log level or decoder, while still needing different timeouts, interceptors, retry policies, and fallbacks. If configuration is not scoped properly, a change intended for the inventory client can accidentally affect the payment client or every Feign client in the application.

Spring Cloud OpenFeign organizes configuration per client using a dedicated context. `@EnableFeignClients` defines the group of registered clients and can provide default configuration for that group; `@FeignClient(configuration = ...)` adds client-specific configuration. When Spring Cloud CircuitBreaker integration is enabled, the application can also choose fallbacks and circuit breaker policies per client, as well as enable group support when methods of the same client need to be grouped.

## 1. Distinguishing Client Scanning Scope and Configuration Scope

`@EnableFeignClients` determines which `@FeignClient` interfaces Spring finds and registers. You can limit the scope using `basePackages`, `basePackageClasses`, or explicitly list them with `clients`.

```java
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableFeignClients(
    basePackages = {
        "com.example.inventory.client",
        "com.example.payment.client"
    }
)
public class FeignClientsConfiguration {
}
```

In the example, only Feign interfaces located in the two declared packages are registered by this configuration. If `basePackages` is too broad, the application may accidentally register clients from unintended packages. For large applications, you can use `basePackageClasses` to avoid relying on package name strings or `clients` to list the exact interfaces to register.

Scanning scope is not the same as configuration bean application scope. `basePackages` selects Feign interfaces; `defaultConfiguration` and the `configuration` attribute select the configuration sources used when creating clients.

## 2. Default Configuration for a Group of Feign Clients

The `defaultConfiguration` attribute of `@EnableFeignClients` supplies default configuration for Feign clients registered through that annotation:

```java
@Configuration(proxyBeanMethods = false)
@EnableFeignClients(
    basePackages = "com.example.client",
    defaultConfiguration = DefaultFeignConfiguration.class
)
public class FeignClientRegistration {
}
```

Example default configuration class:

```java
import feign.Logger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DefaultFeignConfiguration {

    @Bean
    Logger.Level feignLoggerLevel() {
        return Logger.Level.BASIC;
    }
}
```

In this case, clients within the registration scope use log level `BASIC`, unless overridden by a dedicated configuration. You can place other shared beans here if they genuinely fit every client in the group, such as standard decoders or interceptors.

Do not put service-specific policies into the default configuration. For example, an interceptor attaching a token specific to the payment service should not be applied to the inventory client if the two services have different authentication mechanisms.

## 3. Dedicated Configuration per Feign Client

The `configuration` attribute of `@FeignClient` specifies a configuration class for that client. For instance, two clients can share the same service discovery name while requiring independent configurations:

```java
import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient",
    configuration = InventoryReadFeignConfiguration.class
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryAdminClient",
    configuration = InventoryAdminFeignConfiguration.class
)
public interface InventoryAdminClient {
    void reserveStock(String sku, int quantity);
}
```

Both interfaces call `inventory-service`, but have different `contextId` values and can use separate configurations. `name` identifies the target service or client name used in load balancing; `contextId` defines the configuration identifier of the client ensemble and prevents conflicts when multiple clients share the same `name`.

Example dedicated configuration class for the inventory read client:

```java
import feign.Logger;
import feign.Retryer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryReadFeignConfiguration {

    @Bean
    Logger.Level inventoryLoggerLevel() {
        return Logger.Level.BASIC;
    }

    @Bean
    Retryer inventoryRetryer() {
        return Retryer.NEVER_RETRY;
    }
}
```

The inventory read client can use log level `BASIC` and no retries at the Feign layer. The admin client can use a different configuration, such as shorter timeouts or its own interceptor. Only place beans in a client-specific configuration class when they genuinely need to differ from the default.

### Avoiding Dedicated Configurations Being Scanned as Global Configuration

A class referenced by `@FeignClient(configuration = ...)` may be annotated with `@Configuration`, but you must avoid letting it be picked up by the main application's component scan as global configuration. If this class enters the parent application context, beans such as `Encoder`, `Decoder`, `Contract`, `Retryer`, or `RequestInterceptor` can become defaults for many other Feign clients.

You can place client-specific Feign configuration classes in packages outside the main component scan area, or adjust the scan scope so they are loaded only through their respective client's configuration. This is one of the most common scoping mistakes when organizing multiple Feign clients.

## 4. Using contextId to Separate Configuration When Calling the Same Service

`name` and `contextId` do not serve the same purpose. One service can have multiple clients with different contracts: a read client, an admin client, or an internal client. When sharing `name = "inventory-service"`, set distinct `contextId` values so configurations and ensemble beans do not conflict.

| Attribute | Role | Example |
|---|---|---|
| `name` | Service name or target identifier of the Feign client. | `inventory-service` |
| `contextId` | Dedicated configuration identifier of the client ensemble. | `inventoryReadClient` |
| `configuration` | Additional configuration class for a specific client. | `InventoryReadFeignConfiguration.class` |
| `fallback` / `fallbackFactory` | Fallback class attached to a specific client. | `InventoryReadFallbackFactory.class` |

When configuring client-specific properties, use the exact client key that OpenFeign resolves. For a client with `contextId`, use that `contextId` identifier as the configuration name under `spring.cloud.openfeign.client.config` to distinguish clients sharing the same `name`.

## 5. Default and Per-Client Properties Configuration

Spring Cloud OpenFeign allows declaring default configuration under the `default` key and overriding per client:

```yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          default:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
          inventoryReadClient:
            connectTimeout: 300
            readTimeout: 800
            loggerLevel: full
          paymentClient:
            connectTimeout: 500
            readTimeout: 2000
            loggerLevel: basic
```

In the example:

- `default` sets baseline timeouts and log level for clients.
- `inventoryReadClient` overrides timeouts and log level for the inventory read client.
- `paymentClient` has a longer read timeout because the dependency may need more time to process transactions.

The key under `config` must match the client identifier OpenFeign uses; when `contextId` is declared, use that identifier consistently. The timeout values in the example are in milliseconds. Set values according to actual latency budgets and avoid making `readTimeout` longer than the deadline permitted by the caller.

Properties can configure many Feign client components such as `connectTimeout`, `readTimeout`, `loggerLevel`, `errorDecoder`, `retryer`, `requestInterceptors`, `defaultRequestHeaders`, `defaultQueryParameters`, `dismiss404`, and other supported options depending on the Spring Cloud OpenFeign version. Check the documentation for the release train in use before using a new property.

## 6. Precedence Between Properties and Java Configuration

By default, properties configuration can override beans declared in a Feign client's Java configuration class. This makes it easy to adjust timeouts or log levels per environment without modifying code.

You can change the precedence order with:

```yaml
spring:
  cloud:
    openfeign:
      client:
        default-to-properties: false
```

When `default-to-properties` is `false`, Java configuration takes precedence according to Spring Cloud OpenFeign's mechanism. Choose one consistent convention across the application and document which configuration is the authoritative source. If the same setting is declared in both YAML and Java without the team knowing which wins, investigating runtime configuration becomes difficult.

Avoid duplicating the exact same value in both places unnecessarily. Environment-varying settings generally fit properties; bean construction or complex custom logic fits Java configuration.

## 7. Enabling CircuitBreaker Integration for Feign

Spring Cloud OpenFeign can integrate Spring Cloud CircuitBreaker to wrap Feign calls. Enable the feature with the property:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
```

When enabled, Feign calls created through this integration can pass through a circuit breaker. A compatible Spring Cloud CircuitBreaker provider must be on the classpath, such as the Resilience4j starter. If `spring.cloud.openfeign.circuitbreaker.enabled` is not enabled, merely declaring `fallback` or `fallbackFactory` does not automatically ensure calls are wrapped by a circuit breaker.

This is an application-level switch for OpenFeign-CircuitBreaker integration. Selecting specific configurations and fallbacks can still be done per Feign client via corresponding annotations and configurations. Do not assume an independent `enabled` property exists per client if the version in use does not provide that mechanism.

## 8. Enabling Group Support for Methods of the Same Feign Client

By default, OpenFeign integrates circuit breakers using the identifier of each individual call. You can enable group support so the factory also receives a group name corresponding to the Feign client:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
        group:
          enabled: true
```

When group support is enabled, Spring Cloud OpenFeign can supply the client name as the group name when creating the circuit breaker. This is useful when you want to organize methods belonging to the same Feign client under a shared configuration or management group, while individual methods can still have distinct circuit breaker identifiers.

Group support does not mean all methods in a client automatically share a single circuit breaker state. Circuit breaker name, group name, and how the provider applies group configuration are distinct concepts. Check how the provider in use interprets `id` and `groupName`, especially when configuring Resilience4j per instance or per group.

Example Resilience4j configuration with a base config and instances:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      feignDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventoryReadClient:
        baseConfig: feignDefault
      paymentClient:
        baseConfig: feignDefault
        failureRateThreshold: 40
```

This snippet illustrates reusing a base configuration and tuning a specific instance. Instance names must match the actual circuit breaker IDs generated. Those names may depend on OpenFeign's naming rules and `CircuitBreakerNameResolver`; do not infer names solely from Java interfaces without checking the rules of the running version.

## 9. Setting fallback or fallbackFactory per Feign Client

Fallback is declared directly on `@FeignClient`, allowing a separate fallback strategy for each client:

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient",
    configuration = InventoryReadFeignConfiguration.class,
    fallbackFactory = InventoryReadFallbackFactory.class
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

Example `FallbackFactory` receiving the error cause:

```java
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryReadFallbackFactory
        implements FallbackFactory<InventoryReadClient> {

    @Override
    public InventoryReadClient create(Throwable cause) {
        return sku -> {
            // Record the cause in a controlled manner and return the fallback state.
            return Stock.unavailable(sku);
        };
    }
}
```

`fallbackFactory` is useful when you need to distinguish timeouts, connection errors, and `CallNotPermittedException`. If you only need to return a fixed fallback result, you can use the `fallback` attribute with a bean implementing the interface. Choose one of the two mechanisms as needed; do not declare both `fallback` and `fallbackFactory` on the same client.

Fallbacks must preserve proper business semantics. For example, `Stock.unavailable` must inform the caller that inventory data is currently unavailable; do not return quantity 0 if the target service could not be queried. For write operations such as payments or orders, do not return a fake success when it is unknown whether the service processed the transaction.

## 10. CircuitBreaker Names and Per-Method Scope

When CircuitBreaker is enabled for OpenFeign, circuit breaker names are usually generated from the client and method. The default naming rule can change across Spring Cloud versions and can be customized with `CircuitBreakerNameResolver`.

This means a Feign client with multiple methods can create multiple distinct circuit breaker IDs. Enabling group support adds a group name for the client; it does not necessarily merge all methods into a single breaker. When configuring Resilience4j per instance, inspect the actual ID names via logs, metrics, or resolver configuration.

Some versions support an option to convert breaker names to alphanumeric characters only:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        alphanumeric-ids:
          enabled: true
```

This option is useful when default names contain dots, parentheses, or characters unsuitable for the provider's instance naming conventions. Enable it only when the OpenFeign version in use supports that property; after enabling, update Resilience4j instance keys to the new names and inspect metrics to verify accurate mapping.

## 11. Combined Example: Two Clients for the Same Service with Different Policies

Suppose an application has an inventory read client and an inventory admin client. Both call `inventory-service`, but the read client needs short timeouts and temporary data fallback; the admin client performs write commands and must not retry arbitrarily.

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient",
    configuration = InventoryReadFeignConfiguration.class,
    fallbackFactory = InventoryReadFallbackFactory.class
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryAdminClient",
    configuration = InventoryAdminFeignConfiguration.class
)
public interface InventoryAdminClient {
    void reserveStock(String sku, int quantity);
}
```

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
        group:
          enabled: true
      client:
        config:
          inventoryReadClient:
            connectTimeout: 300
            readTimeout: 800
            loggerLevel: basic
          inventoryAdminClient:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
```

In this design:

- Both clients are registered and can use the application-wide CircuitBreaker integration.
- `contextId` separates the configuration and client ensemble identity despite sharing the same `name`.
- Timeouts are set independently per client.
- FallbackFactory is attached only to the inventory read client.
- The admin client needs safe write policies, idempotency, and explicit error handling; do not automatically retry `reserve` operations without duplicate-prevention mechanisms.

If configuring CircuitBreaker per Resilience4j instance, determine the actual ID generated by the resolver for each method and use that exact ID. If a shared policy for the entire client is needed, group support can help organize configuration by client; verify how the provider applies groups in the project's version.

## 12. Common Scoping Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| A client's configuration bean affects all clients | Dedicated configuration class was component-scanned into the parent application context. | Move the class outside component scan or restrict scan scope. |
| Two clients with the same `name` have config conflicts | Missing distinct `contextId`. | Assign a distinct `contextId` to each client ensemble. |
| Per-client properties are not applied | YAML key does not match the client identifier resolved by OpenFeign. | Check `name`/`contextId` and use the corresponding key. |
| Java config is overridden by YAML | `default-to-properties` is enabled by default. | Decide the intended configuration source and set the precedence property intentionally. |
| Fallback is not invoked | CircuitBreaker integration not enabled, provider missing, or fallback not registered as a bean. | Check starters, `spring.cloud.openfeign.circuitbreaker.enabled`, and fallback bean. |
| Resilience4j config does not match breaker | Wrong ID used or resolver/alphanumeric IDs not accounted for. | Observe actual breaker names and update instance keys. |
| Group config does not behave as expected | Confusing group name with circuit breaker ID or provider applies groups differently than assumed. | Check `create(id, groupName)` and the documentation for the provider in use. |

## 13. Pre-Release Scoping Checklist

Before shipping OpenFeign and CircuitBreaker configuration to production, verify:

- [ ] `@EnableFeignClients` scans only the required packages or client list.
- [ ] `defaultConfiguration` contains only beans truly shared across the client group.
- [ ] Each client needing its own policy has an explicit `configuration`.
- [ ] Dedicated configuration classes are not component-scanned as global configuration.
- [ ] Clients sharing the same `name` have distinct `contextId` values.
- [ ] Keys under `spring.cloud.openfeign.client.config` match client identifiers.
- [ ] Precedence between properties and Java configuration is explicitly defined.
- [ ] CircuitBreaker integration is enabled and the corresponding provider is present.
- [ ] Group support is enabled only when group names are needed.
- [ ] Fallback or FallbackFactory is bound to the right client and returns business-meaningful results.
- [ ] Resilience4j instance IDs match actual runtime breaker names.
- [ ] Gateway, Feign, and SDK retries do not multiply attempts beyond budget.

Organizing configuration with proper scoping gives an application consistent baseline policies while preserving necessary differences between individual Feign clients. Use `@EnableFeignClients` to restrict the registered group, `defaultConfiguration` for baseline settings, `@FeignClient(configuration = ...)` and `contextId` per client, and enable CircuitBreaker/group support intentionally. Finally, verify breaker names, properties, fallbacks, and metrics at runtime to ensure each configuration applies in the right place.
