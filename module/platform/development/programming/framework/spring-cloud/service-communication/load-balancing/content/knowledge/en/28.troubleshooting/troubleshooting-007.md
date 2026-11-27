# Per-client configuration has no effect or applies to the wrong service

An Order Service application may simultaneously call **inventory-service**, **payment-service**, and **catalog-service** via Spring Cloud LoadBalancer. The team wants Inventory to use **RandomLoadBalancer**, Payment to keep **RoundRobinLoadBalancer**, and Inventory to have its own health check and a different timeout from Payment. Yet after deployment, all three clients apply the same policy, or Inventory's custom configuration seems to have no effect. Another case is a change meant for Inventory accidentally applying to Payment as well.

These bugs rarely live in the load-balancing algorithm itself. Common root causes are **mismatched service IDs**, **misconfigured LoadBalancer child contexts**, configuration classes getting component-scanned into the parent context, HTTP client beans missing **@LoadBalanced**, a fixed URL causing Feign to bypass LoadBalancer, or properties using the wrong prefix / being overridden by a higher-precedence configuration source.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will go from symptoms to evidence, separate **LoadBalancer client contexts**, **HTTP client beans**, and **Feign named-client contexts**, inspect RestTemplate/RestClient/WebClient/OpenFeign integrations, verify per-service-ID configuration, read effective properties safely, test isolation between clients, and build a remediation runbook.

> **Scope:** Examples are based on current Spring Cloud Commons/LoadBalancer and Spring Cloud OpenFeign. APIs/packages may change across release trains; use a compatible Spring Boot–Spring Cloud BOM. Do not assume every property can be overridden per client: certain properties are strictly global, which are called out separately in this lesson.

## 1. Identify the exact symptom

Before modifying code, classify the symptom:

| Symptom | First question |
| --- | --- |
| Inventory still uses Round Robin despite configuring Random | Does the child context for **inventory-service** actually instantiate RandomLoadBalancer? |
| Both Inventory and Payment switched to Random | Did Inventory's config leak into the parent context or a global configuration? |
| Only RestClient ignores the configuration | Is the injected builder actually annotated with **@LoadBalanced**? |
| WebClient does not select instances | Does the builder carry the LoadBalancer filter, or is code calling **WebClient.create()** directly? |
| Feign calls a fixed host | Is there a **url** attribute on @FeignClient or **spring.cloud.openfeign.client.config.*.url**? |
| Inventory's Feign config affects other Feign clients | Was the config class component-scanned into a global bean? |
| Per-client property does not change behavior | Is the **spring.cloud.loadbalancer.clients.<serviceId>** prefix right, and does that property support per-client scoping? |
| Works locally, fails in production | Are profiles, env vars, CLI flags, Config Server, or ConfigMaps overriding it? |
| Configuration only takes effect after the first call | Is the LoadBalancer child context lazily initialized and retaining its constructed beans? |
| Changed service ID in one place, yet registry fails to find it | Do URI host, @LoadBalancerClient name, Feign name, and discovery ID match? |

**Diagnostic rule:** verify which client, which service ID, which context, and which bean the request actually goes through before modifying the algorithm.

## 2. Three kinds of “client context” that are easy to confuse

Spring Cloud mixes multiple configuration scopes within a single application:

~~~mermaid
flowchart TD
    P["Order Service: parent ApplicationContext"] --> LB1["LoadBalancer child context\ninventory-service"]
    P --> LB2["LoadBalancer child context\npayment-service"]
    P --> FEIGN["Feign named-client context\ninventoryReadClient"]
    P --> FEIGN2["Feign named-client context\npaymentClient"]
    P --> HTTP["HTTP client beans\nRestClient / WebClient / Feign transport"]
    LB1 --> S1["Supplier + ReactorLoadBalancer + policy"]
    LB2 --> S2["Supplier + ReactorLoadBalancer + policy"]
    FEIGN --> S3["Decoder / Encoder / Contract / Interceptors"]
    FEIGN2 --> S4["Decoder / Encoder / Contract / Interceptors"]
    HTTP --> S5["Connection pool / TLS / timeout"]
~~~

### 2.1. LoadBalancer child context

Spring Cloud LoadBalancer creates **one Spring child ApplicationContext per service ID**. For example, inventory-service and payment-service get two isolated contexts supplying:

- ReactorLoadBalancer<ServiceInstance>: selects the instance.
- ServiceInstanceListSupplier: fetches/filters the instance list.
- Policy, retry-aware selection, and health/zone/cache beans per configuration.

The context is normally **lazily initialized on the first request** for that service ID. A bean existing in Inventory's context does not make it automatically appear in Payment's context.

### 2.2. Feign named-client context

Spring Cloud OpenFeign also creates a separate **named client ensemble** for each Feign client containing its Decoder, Encoder, Contract, Client, and custom beans. A `contextId` can separate configuration for two Feign interfaces calling the same service.

This is a **Feign client configuration** context, not the same thing as Spring Cloud LoadBalancer's child context. A Feign client still requires its service ID / LoadBalancer integration when selecting backends.

### 2.3. HTTP client bean/context

RestClient, RestTemplate, WebClient, and the transport under Feign have their own lifecycle: builders, filters/interceptors, connection pools, TLS, and timeouts. A single HTTP client bean in the parent context can call multiple service IDs; **@LoadBalancerClient does not automatically create a separate RestClient per service ID**.

Therefore, identify exactly which layer a requirement belongs to:

| What you want to change | Scope to configure |
| --- | --- |
| Inventory selection algorithm | LoadBalancer child context for inventory-service |
| Inventory-specific instance list/health/zone | ServiceInstanceListSupplier in child context or per-client properties |
| Inventory Feign Decoder/Retryer/RequestInterceptor | Feign named-client context |
| Inventory Feign connect/read timeout | Feign client properties or Request.Options/client transport |
| TLS truststore for one RestClient | That client's HTTP connector/request factory and SSL bundle |
| Shared trace header on every request | Intentional global interceptor/filter |

## 3. Quick diagnostic flowchart

~~~mermaid
flowchart TD
    A["Request uses wrong configuration"] --> B{"Which client?"}
    B -->|RestClient / RestTemplate| C["Check @LoadBalanced builder/template"]
    B -->|WebClient| D["Check @LoadBalanced builder or LB filter"]
    B -->|OpenFeign| E["Check starter, @FeignClient name, and url"]
    C --> F{"Does URI host match exact service ID?"}
    D --> F
    E --> F
    F -->|No| G["Fix logical service ID"]
    F -->|Yes| H["Check @LoadBalancerClient mapping"]
    H --> I{"Does child context have right config?"}
    I -->|No| J["Check component scan / annotation / package"]
    I -->|Yes| K["Check clients.<serviceId> property prefix"]
    K --> L["Check global properties and precedence"]
    L --> M["Check supplier chain / bean overrides"]
    M --> N["Test each service ID and real HTTP requests"]
~~~

Follow this order so you do not waste time tuning RandomLoadBalancer while requests are actually hitting a fixed URL.

## 4. Step 1 — identify the request's true service ID

In LoadBalancer, the **service ID** is normally extracted from the host in the HTTP request's logical URI or from the Feign client's name.

Example:

~~~java
restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

The service ID here is **inventory-service**.

With WebClient:

~~~java
webClient.get()
        .uri("http://payment-service/api/payments/{id}", id)
        .retrieve()
        .bodyToMono(PaymentResponse.class);
~~~

The service ID is **payment-service**.

With OpenFeign:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogClient {
    @GetMapping("/api/products/{id}")
    ProductResponse find(@PathVariable("id") String id);
}
~~~

The client name used to look up the LoadBalancer client is **catalog-service**.

### 4.1. Name in @LoadBalancerClient must match the service ID

~~~java
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
class LoadBalancerRegistration {
}
~~~

If requests use http://inventory-service/... yet the annotation registers name = "inventory", your custom configuration attaches to **inventory**, whereas requests look up the **inventory-service** context. As a result, default configuration gets used for real traffic.

Verify every value:

| Declaration site | Value to match |
| --- | --- |
| RestClient/RestTemplate URI host | inventory-service |
| WebClient URI host | inventory-service |
| @FeignClient(name=...) | inventory-service |
| @LoadBalancerClient(name=...) | inventory-service |
| SimpleDiscoveryClient/registry service ID | inventory-service |
| spring.cloud.loadbalancer.clients.<clientId> | inventory-service |

**Never rely on Java variable names or bean names** to infer the service ID. Names like inventoryClient, inventoryRestClient, or inventoryReadClient do not automatically become the service ID.

### 4.2. Distinguish service ID from instance ID

- **Service ID**: logical name of the whole service, e.g., inventory-service.
- **Instance ID**: identifier of a single replica, e.g., inventory-a.
- **Host/port**: physical address of an instance, e.g., 10.2.1.8:8080.

@LoadBalancerClient(name=...) accepts a **service ID**, not an instance ID or a specific pod hostname. If you configure name="inventory-a" while the URL host is inventory-service, LoadBalancer will not apply that context to requests.

## 5. Step 2 — verify custom config attaches to the right child context

A per-service LoadBalancer configuration:

~~~java
package com.example.order.lb.inventory;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

// @Configuration is optional when the class is imported
// directly via @LoadBalancerClient.
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

Registration:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class OrderApplication {
}
~~~

This snippet shows how to read the **current child context's service ID** via LoadBalancerClientFactory.PROPERTY_NAME. When a configuration serves multiple service IDs, do not hardcode "inventory-service" inside the bean implementation; hardcoding makes the selector look up the wrong supplier across services.

### 5.1. Common mistake: child config gets component-scanned into parent

A class like this causes unintended side effects:

~~~java
package com.example.order;

@Configuration
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryLoadBalancer(...) {
        // ...
    }
}
~~~

If the class sits inside the main application's @SpringBootApplication/@ComponentScan scope, its bean gets registered in the **parent ApplicationContext**. Meanwhile, Spring Cloud LoadBalancer expects classes passed to @LoadBalancerClient to configure the **child context**.

Spring Cloud docs require classes passed to **@LoadBalancerClient** or **@LoadBalancerClients** to either:

- omit @Configuration; **or**
- if annotated with @Configuration, live outside component-scan packages.

A clear package layout:

~~~text
com.example.order
  OrderApplication.java
  client/
    InventoryClient.java
  service/
    OrderService.java

com.example.order.lbconfig
  InventoryLoadBalancerConfiguration.java
  PaymentLoadBalancerConfiguration.java
~~~

If lbconfig remains a subpackage under the scanned root package, merely moving folders is not enough. Place the config package outside the scan root or explicitly exclude it from component scanning.

### 5.2. Does a configuration without @Configuration still register @Bean methods?

Yes. When a class is registered via the **configuration class argument** of @LoadBalancerClient, Spring processes its @Bean methods. This is the standard pattern in Spring Cloud documentation. Never import that class into the parent context just to make its @Bean methods recognized.

### 5.3. Global vs. per-service registration

When multiple clients need separate policies:

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClients({
        @LoadBalancerClient(
                name = "inventory-service",
                configuration = InventoryLoadBalancerConfiguration.class),
        @LoadBalancerClient(
                name = "payment-service",
                configuration = PaymentLoadBalancerConfiguration.class)
})
class ServiceLoadBalancerRegistrations {
}
~~~

This registration class can live in parent configuration; **the two configuration classes passed into it** must still follow the non-component-scanned rule above.

## 6. Step 3 — separate per-client configuration from global configuration

Spring Cloud LoadBalancer supports the prefix:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 35s
      health-check:
        initial-delay: 1s
      clients:
        inventory-service:
          cache:
            ttl: 10s
          health-check:
            interval: 15s
        payment-service:
          cache:
            ttl: 30s
          health-check:
            interval: 45s
~~~

Default values under **spring.cloud.loadbalancer.*** merge with per-client values; per-client settings take precedence for supported properties.

Example:

| Property | Shared default | Inventory | Payment |
| --- | --- | --- | --- |
| cache.ttl | 35s | 10s | 30s |
| health-check.initial-delay | 1s | Inherits 1s | Inherits 1s |
| health-check.interval | 25s (default) | 15s | 45s |

Not every property supports per-client overrides identically. Specifically, current Spring Cloud docs call out several **global** properties:

| Global property | Important behavior |
| --- | --- |
| spring.cloud.loadbalancer.enabled | Enables/disables LoadBalancer application-wide |
| spring.cloud.loadbalancer.retry.enabled | Enables/disables retry globally; if global is enabled, a specific client can disable retry, but per-client cannot enable it when global is off |
| spring.cloud.loadbalancer.cache.enabled | Enables/disables cache globally; if global is off, a plain client prefix cannot re-enable it alone |
| spring.cloud.loadbalancer.stats.micrometer.enabled | Enables/disables LoadBalancer metrics globally |

**Misguided expectation example:**

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      clients:
        inventory-service:
          retry:
            enabled: true
~~~

Do not expect Inventory to enable retries when global retry is disabled. Documentation describes the supported override direction as **global on, specific client off**; clients cannot invert every global toggle.

### 6.1. Map properties with their own compatibility rules

Certain properties are already keyed as maps by service ID, such as:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          inventory-service: /actuator/health/readiness
      hints:
        inventory-service: canary
~~~

For maps like **hints** or **health-check.path**, Spring Cloud preserves direct service-ID keys for backward compatibility. Do not move all of these maps under **clients.inventory-service** simply because other properties use the clients prefix.

When unsure about prefixes, consult the **Configuration Properties Reference for your exact release train** rather than relying on IDE autocomplete or an old blog post.

### 6.2. Never use bean names as property keys

The key in:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          cache:
            ttl: 10s
~~~

is the **service ID inventory-service**. It is not the Java field name inventoryRestClient, bean name inventoryClient, or Feign interface InventoryFeignClient.

## 7. Step 4 — check property precedence and runtime values

A property with the right prefix can still fail to take effect because a higher-precedence source overrides it.

Example:

~~~text
application.yml:
  spring.cloud.loadbalancer.clients.inventory-service.cache.ttl = 10s

application-prod.yml:
  spring.cloud.loadbalancer.clients.inventory-service.cache.ttl = 30s

Deployment environment:
  SPRING_CLOUD_LOADBALANCER_CLIENTS_INVENTORY_SERVICE_CACHE_TTL = 45s
~~~

In production, environment variables win over profile YAML files according to Spring Boot's PropertySource order. Never conclude YAML is broken before inspecting the final resolved value.

### 7.1. Common override sources

- Profile-specific files, e.g., application-prod.yml.
- External config files outside the JAR or via spring.config.import.
- Environment variables from Deployment/ConfigMap.
- Java system properties (-D...).
- Command-line arguments (--spring.cloud...).
- Test properties or DynamicPropertySource in integration tests.
- Config Server / Kubernetes PropertySource when integrated.

When inspecting, record the **source name** and sanitized values; never dump the full Environment containing credentials.

### 7.2. Inspecting Environment safely

In tests you can verify:

~~~java
@Autowired
Environment environment;

@Test
void inventoryClientPropertyIsPresent() {
    assertEquals(
            Duration.ofSeconds(10),
            environment.getProperty(
                    "spring.cloud.loadbalancer.clients.inventory-service.cache.ttl",
                    Duration.class));
}
~~~

This test only proves **Environment has the property bound**, not that the supplier inside the child context actually caches for 10 seconds. Verify the supplier bean or observe HTTP/discovery behavior to confirm the rest.

### 7.3. Actuator env/configprops must be protected

Actuator helps verify bound properties, but never expose env/configprops endpoints publicly. Configure sanitization and authentication/authorization per policy. Never print client secrets, API keys, tokens, or private keys into logs to inspect another property.

## 8. Step 5 — verify child contexts exist for the right service ID

LoadBalancer child contexts are created **lazily** on the first load-balanced request to a service ID. Looking only at startup logs before any Inventory request runs may not show an Inventory context at all.

You can eagerly initialize critical services:

~~~yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - inventory-service
          - payment-service
~~~

Eager-loading only initializes contexts early; **it does not fix wrong service IDs, conjure discovery providers, or convert a fixed URL into load-balanced calls**.

### 8.1. Checking context beans in tests

In a Spring Boot integration test, inject **LoadBalancerClientFactory** and inspect beans per service ID:

~~~java
@SpringBootTest
class LoadBalancerClientContextTest {

    @Autowired
    LoadBalancerClientFactory factory;

    @Test
    void inventoryHasLoadBalancerAndSupplier() {
        ReactorLoadBalancer<?> loadBalancer =
                factory.getInstance(
                        "inventory-service", ReactorLoadBalancer.class);
        ServiceInstanceListSupplier supplier =
                factory.getInstance(
                        "inventory-service",
                        ServiceInstanceListSupplier.class);

        assertNotNull(loadBalancer);
        assertNotNull(supplier);
    }
}
~~~

Imports depend on release train and include **LoadBalancerClientFactory**, **ReactorLoadBalancer**, **ServiceInstanceListSupplier**, Spring Boot Test, and JUnit. This test proves **beans exist inside the named service ID context**, not that the bean is your intended custom implementation or that live requests route through it.

If you need to verify the implementation, assert the concrete class (such as RandomLoadBalancer) in a test pinned to your chosen version. Avoid asserting concrete default classes in cross-version tests if default implementations might change.

### 8.2. Comparing two child contexts

~~~java
@Test
void inventoryAndPaymentHaveDifferentSuppliers() {
    ServiceInstanceListSupplier inventory =
            factory.getInstance(
                    "inventory-service",
                    ServiceInstanceListSupplier.class);
    ServiceInstanceListSupplier payment =
            factory.getInstance(
                    "payment-service",
                    ServiceInstanceListSupplier.class);

    assertNotNull(inventory);
    assertNotNull(payment);
    assertNotSame(inventory, payment);
}
~~~

**Not every app requires two suppliers to have different classes**; this test merely illustrates two separate contexts. If both use DiscoveryClientServiceInstanceListSupplier, having the same class type is completely valid. What matters is verifying each context's **configuration and instance lists** for its service ID.

## 9. Step 6 — verify @LoadBalanced on the right HTTP client

Even when the child context is configured right, requests bypass LoadBalancer if the HTTP client itself is not wired.

First verify **spring-cloud-starter-loadbalancer** is on the runtime classpath and managed by a compatible Spring Cloud BOM. RestClient load balancing is supported in corresponding Spring Boot/Spring Cloud lines; if your project uses an older line, do not apply newer snippets without checking API integration.

### 9.1. RestClient

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Verify:

- Does the builder bean carry **@LoadBalanced**?
- Is the RestClient bean built from that exact annotated builder?
- If multiple RestClient.Builder beans exist, do injection points qualify **@LoadBalanced**?
- Is the URI host the service ID?
- Is any code calling a different RestClient instance?

A plain builder and a @LoadBalanced builder can coexist. Injecting the plain builder by mistake sends `inventory-service` to the DNS resolver as an ordinary hostname, producing UnknownHostException.

### 9.2. RestTemplate

~~~java
@Bean
@LoadBalanced
RestTemplate inventoryRestTemplate() {
    return new RestTemplate();
}
~~~

If the app has both plain and load-balanced RestTemplates, use **@Qualifier** or explicit bean names when injecting. Never convert a global bean to @LoadBalanced just to fix one caller if other components need direct host calls.

### 9.3. WebClient

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}

@Bean
WebClient inventoryWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder
            .baseUrl("http://inventory-service")
            .build();
}
~~~

Common mistakes:

- Calling **WebClient.create()** or **WebClient.builder()** directly instead of the LoadBalancer-integrated builder.
- Manually adding ReactorLoadBalancerExchangeFilterFunction onto a builder that already auto-configured it.
- Building WebClient from a different builder lacking @LoadBalanced.
- Using a URI like http://inventory-a.internal (fixed instance host) instead of the service ID.

You can configure WebClient manually with **ReactorLoadBalancerExchangeFilterFunction**, but choose **one intentional integration style** and verify the filter is added only once.

### 9.4. Never mix qualifiers across builder types

@LoadBalanced acts as a qualifier marker for its respective beans. Annotating a RestClient.Builder does not make WebClient.Builder load-balanced, and vice versa. Verify the exact **bean type + qualifier + client instance** in use.

## 10. Step 7 — OpenFeign: check starter, name, url, and contextId

OpenFeign requires **spring-cloud-starter-loadbalancer** to wire FeignBlockingLoadBalancerClient. The OpenFeign starter does not force LoadBalancer onto every app because that dependency is optional.

Load-balanced Feign example:

~~~java
@EnableFeignClients(basePackages = "com.example.order.clients")
@SpringBootApplication
class OrderApplication {
}

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse findStock(@PathVariable("sku") String sku);
}
~~~

Verify:

1. Are compatible **spring-cloud-starter-openfeign** and **spring-cloud-starter-loadbalancer** dependencies present?
2. Does **@EnableFeignClients** scan the right package or list the client classes?
3. Does **name** match the service ID in discovery?
4. Is a fixed URL set in the annotation or properties?
5. Was a config class accidentally component-scanned into a default config for all Feign clients?

### 10.1. Fixed URLs cause Feign to bypass LoadBalancer

Per Spring Cloud OpenFeign, URL combinations behave as follows:

| Declaration | Outcome |
| --- | --- |
| @FeignClient(name="inventory-service") | Uses name as service ID, load-balanced |
| @FeignClient(name="inventory-service", url="http://localhost:8081") | Uses annotation URL, not load-balanced |
| Annotation omits url, but property spring.cloud.openfeign.client.config.inventory-service.url is set | Uses property URL, not load-balanced |
| Both annotation url and property url are set | Annotation URL wins; property URL has no effect |

**A URL added purely for local testing convenience can silently stop production from using service discovery.** Check both annotation placeholders and environment/profile properties.

### 10.2. Name and contextId play different roles

~~~java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient",
        configuration = InventoryFeignConfiguration.class)
interface InventoryReadClient {
}

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryAdminClient",
        configuration = InventoryAdminFeignConfiguration.class)
interface InventoryAdminClient {
}
~~~

Both Feign interfaces call the same service ID **inventory-service**, yet need separate Feign configs. **name** identifies the target service; **contextId** separates Feign's named-client ensemble and bean configuration when multiple clients share a name.

Never rename `name` to `inventoryReadClient` just to split Feign configurations. Doing so tells LoadBalancer to look up service ID `inventoryReadClient`, which probably does not exist in the registry.

### 10.3. Feign configuration component-scanned into global scope

A class meant exclusively for Inventory:

~~~java
class InventoryFeignConfiguration {

    @Bean
    RequestInterceptor inventoryAuthInterceptor() {
        return template -> template.header(
                "X-Client-Type", "inventory");
    }
}
~~~

If this class gets scanned into the parent context, its beans become defaults applied to other Feign clients. OpenFeign docs recommend omitting @Configuration on per-client config classes; if @Configuration is present, place it outside component scanning or exclude it explicitly.

### 10.4. Feign property precedence

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventoryReadClient:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
~~~

The key must match the **named client identity** (derived from name/value/contextId) used by Feign in your running version. When multiple clients share a service ID with distinct contextIds, check keys under contextId and test effective Request.Options.

By default, OpenFeign properties can override Java configuration beans. You can invert precedence with **spring.cloud.openfeign.client.default-to-properties=false**. When timeouts or interceptors appear ignored in @Configuration, check property overrides first.

## 11. Step 8 — inspect the supplier chain and overridden beans

A LoadBalancer child context can use custom suppliers to fetch/filter the ServiceInstance list. Placing suppliers in the wrong context or creating unintended beans can disable per-client policies.

### 11.1. Custom supplier applied to every service

Anti-pattern:

~~~java
@Configuration
class GlobalSupplierConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

If scanned into the parent, this bean can affect multiple LoadBalancer child contexts or conflict with default configuration. Put custom suppliers inside **configuration registered for the specific service ID**, or use supported per-client properties.

### 11.2. Proper supplier chain ordering

~~~text
DiscoveryClientServiceInstanceListSupplier
        |
        v
CachingServiceInstanceListSupplier
        |
        v
ZonePreference / Hint / Filtering supplier
        |
        v
ReactorLoadBalancer.choose()
~~~

If using **HealthCheckServiceInstanceListSupplier**, it includes internal Flux replay caching; documentation advises against wrapping it with CachingServiceInstanceListSupplier at the same time. Place caching/health suppliers immediately after the network retrieval supplier and before other filtering suppliers per your release train's guidance.

### 11.3. Match the active DiscoveryClient stack

Spring Cloud supports blocking **DiscoveryClient** and reactive **ReactiveDiscoveryClient**. When building suppliers manually, choose the builder matching your active stack. A blocking discovery supplier does not magically adapt simply because WebClient is reactive, or vice versa.

### 11.4. @ConditionalOnMissingBean and multiple beans of the same type

Default configuration typically declares beans with **@ConditionalOnMissingBean**. If a ServiceInstanceListSupplier or ReactorLoadBalancer bean already exists in context, auto-configuration backs off. This enables customization, yet an accidentally scanned global bean can suppress default beans across multiple contexts unexpectedly.

When multiple beans of the same type appear, check:

- Whether each bean lives in the parent or child context.
- Which bean is @Primary.
- Which @ConditionalOnMissingBean matched.
- Whether a config package was mistakenly component-scanned.
- Whether a custom config class was registered twice.

Never slap @Primary on blindly to “fix” NoUniqueBeanDefinitionException; first identify which bean belongs to which service ID.

## 12. Step 9 — find configurations applied too broadly

Some mechanisms intentionally apply to **all LoadBalancer clients**. Using a global mechanism when only Inventory needs customization affects Payment and Catalog too.

### 12.1. @LoadBalancerClients defaultConfiguration

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClients(
        defaultConfiguration = CommonLoadBalancerConfiguration.class)
class AllLoadBalancerClientsConfiguration {
}
~~~

The **defaultConfiguration** attribute sets defaults for all LoadBalancer clients. If only Inventory needs Random, register it specifically via **@LoadBalancerClient(name="inventory-service", configuration=...)**.

### 12.2. Properties in the global namespace

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: zone-preference
~~~

This is global configuration in the default namespace. If only Inventory needs zone preference, use the per-client mechanism for your release train or a dedicated child context configuration. Never put settings in global scope and expect Payment to remain unaffected.

### 12.3. Scanned custom configuration classes

If an Inventory-specific configuration class carries @Configuration inside OrderApplication's scanned packages, its beans register in the parent context. That can:

- turn a custom ReactorLoadBalancer into a shared bean;
- suppress default ServiceInstanceListSupplier creation via @ConditionalOnMissingBean;
- leak one client's beans/filters/interceptors into another client;
- cause multiple-bean errors or divergence between tests and production.

**Fix:** move the config class outside component scanning or drop @Configuration when passing it directly to @LoadBalancerClient; keep beans inside the child context of the target service ID.

## 13. Step 10 — separate unsupported per-client properties from wrong prefixes

When a property does not alter behavior, ask three questions:

1. Does the property exist in the current release train?
2. Does it support the clients.<clientId> prefix?
3. Does the executing component actually read that property?

Examples:

| Setting | Configurable per client? | Notes |
| --- | --- | --- |
| Cache TTL | Usually yes | clients.inventory-service.cache.ttl |
| Health-check interval | Usually yes | clients.inventory-service.health-check.interval |
| Retry max attempts | Usually yes | Use client prefix per docs |
| LoadBalancer enabled | No, global | Disabling affects the whole app |
| Retry enabled | Limited | Global off cannot be re-enabled per client |
| Cache enabled | Limited | Global off cannot be re-enabled by client property alone |
| Micrometer stats enabled | Global | Not a per-client toggle |
| Health-check path map | Map by service ID | Keep direct syntax health-check.path.inventory-service |
| Hint map | Map by service ID | Keep syntax hints.inventory-service |

### 13.1. Custom suppliers can ignore property chains

Suppose application.yml sets:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          configurations: health-check
~~~

Yet the child config defines a custom **ServiceInstanceListSupplier** bean that only wraps DiscoveryClient without health checks. Once the custom bean is chosen, the `configurations` property may not assemble the chain you expect.

**Do not look only at properties.** Inspect the actual supplier bean, delegates, and chain ordering. A custom bean replacing the default chain must explicitly wire caching, health, zone, or hint behaviors as needed.

### 13.2. Never wrap cache/health multiple times

Spring Cloud docs recommend when assembling a custom supplier chain:

- Use **either** CachingServiceInstanceListSupplier or HealthCheckServiceInstanceListSupplier per design; do not stack both arbitrarily.
- Place caching/health right after network instance retrieval.
- Place request-based/zone/hint filters downstream per contract.

Wrong ordering can cache per-request filtered lists or prevent health checks from seeing refreshed instances. Consult supplier ordering in the reference docs for your exact version.

## 14. Step 11 — ensure Feign config is not confused with LoadBalancer config

There are two independent configuration blocks:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          cache:
            ttl: 10s

    openfeign:
      client:
        config:
          inventoryReadClient:
            connectTimeout: 500
            readTimeout: 1500
~~~

The first block configures **LoadBalancer for service ID** inventory-service. The second configures **Feign named client** inventoryReadClient. Never rename the first key to inventoryReadClient just because Feign's contextId uses that name.

### 14.1. Separate service ID and contextId in a table

~~~java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient")
interface InventoryReadClient {
}
~~~

| Value | Used for |
| --- | --- |
| name = inventory-service | Service ID looked up in discovery by Feign LoadBalancer |
| contextId = inventoryReadClient | Isolates Feign named-client ensemble/bean configuration |
| spring.cloud.loadbalancer.clients.inventory-service.* | Per-service-ID LoadBalancer config |
| spring.cloud.openfeign.client.config.inventoryReadClient.* | Per-client-identity Feign named-client config |

OpenFeign docs describe feignName in configuration properties as tied to value/name and contextId; when multiple Feign clients share a name with distinct contextIds, use contextId to prevent collisions and verify effective settings on your release train.

### 14.2. Precedence between Feign Java config and properties

By default, properties override Feign Java configuration beans. To make Java configuration win, set:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        default-to-properties: false
~~~

If timeouts, logger levels, RequestInterceptors, or Retryers appear replaced, check:

- whether the client config key matches name/contextId;
- whether a property is defined in another profile;
- whether a URL property accidentally bypassed LoadBalancer;
- whether default-to-properties has the expected value;
- whether the config class was scanned globally.

### 14.3. Never use Feign RequestInterceptor to change the service ID

RequestInterceptor modifies request headers/templates. It does not change the named-client context or the service ID already consumed by LoadBalancer. To pick Inventory, declare the right `name`; to add headers, use a properly scoped interceptor. Never try rewriting the host after LoadBalancer selects an instance.

## 15. Step 12 — verify with real requests, not just reading YAML

A solid verification workflow gathers **three layers of evidence**:

| Layer | What to verify | Evidence |
| --- | --- | --- |
| Configuration | Right property name/source/value | Protected Environment/configprops |
| Context/bean | Right service ID and implementation | LoadBalancerClientFactory + bean type |
| HTTP route | Real request hits intended backend | Backend instance ID, access logs, MockWebServer |

### 15.1. Isolated test for Inventory vs. Payment

Example structure:

~~~text
InventoryLoadBalancerConfiguration
  -> RandomLoadBalancer (test policy)

PaymentLoadBalancerConfiguration
  -> RoundRobinLoadBalancer (default or custom)

Caller:
  GET http://inventory-service/whoami
  GET http://payment-service/whoami
~~~

In an integration test:

1. Provide independent instance lists for Inventory and Payment via SimpleDiscoveryClient or test suppliers.
2. Send requests using **service IDs**, never calling localhost directly.
3. Record the instance ID returned by each backend.
4. Verify Inventory's policy does not alter Payment's policy.
5. Re-run tests after moving config packages or changing @ComponentScan to catch global leakage.

### 15.2. Verify bean types per service

~~~java
@Test
void inventoryUsesRandomAndPaymentUsesRoundRobin() {
    ReactorLoadBalancer<?> inventory =
            factory.getInstance(
                    "inventory-service", ReactorLoadBalancer.class);
    ReactorLoadBalancer<?> payment =
            factory.getInstance(
                    "payment-service", ReactorLoadBalancer.class);

    assertInstanceOf(RandomLoadBalancer.class, inventory);
    assertInstanceOf(RoundRobinLoadBalancer.class, payment);
}
~~~

This test fits when an app **deliberately configures those two implementations** as shown. If Payment uses a custom implementation or another release train changes defaults, adapt assertions to your app's contract.

### 15.3. Test a non-existent service ID

Send a request to:

~~~text
http://inventroy-service/api/stock/BOOK-01
~~~

where the name has a typo. The outcome is typically **no ServiceInstance** or resolution failure depending on client/adapter. This test separates:

- service ID missing in discovery;
- @LoadBalancerClient registered under the wrong name;
- client missing LoadBalancer integration and attempting DNS lookup.

Do not assert only status codes. Check **backend request counts**: if zero backends received requests, failure occurred before the HTTP backend or at DNS/connection.

## 16. Logs and metrics for diagnosis

In test environments, you can raise log levels for:

~~~yaml
logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
    org.springframework.cloud.openfeign: DEBUG
~~~

Increase logging only briefly and per environment. Never enable Feign FULL logging in production if bodies/headers can contain tokens, cookies, PII, or sensitive data.

### 16.1. What to record

- Logical service ID.
- Selected instance ID/host/port (per security policy).
- Actual LoadBalancer implementation type.
- Supplier chain / eligible instance count.
- Config revision and active profiles.
- HTTP status, root exception, attempt number.
- Client type: RestClient, RestTemplate, WebClient, or Feign.

### 16.2. Avoid high-cardinality tags or leaking secrets

Never put into metric tags:

- order ID, SKU, customer ID, trace ID;
- full URLs containing dynamic query params;
- bearer tokens, API keys, Cookies, Authorization headers;
- secret values or private keys.

Use sampled traces/logs to investigate individual requests. Metrics should stick to service ID, operation template, error class, status, and client type with bounded cardinality.

## 17. Common symptom and root-cause matrix

| Symptom | Likely root cause | How to verify |
| --- | --- | --- |
| Random not applied to Inventory | @LoadBalancerClient name mismatches URI host | Compare service ID across request, annotation, and registry |
| Inventory uses default config | Config class in wrong context or unregistered | Inspect bean via LoadBalancerClientFactory |
| Inventory config affects Payment | Class component-scanned into parent or uses defaultConfiguration | Check package, @LoadBalancerClients, and parent beans |
| Per-client TTL unchanged | Wrong clients.<id> prefix or overridden elsewhere | Check effective property and configprops |
| Per-client retry stays disabled | Global retry.enabled=false | Check global/per-client precedence limits |
| Per-client cache stays disabled | Global cache.enabled=false | Check global flag and supplier chain |
| Health-check path unchanged | Wrong map syntax or supplier is not health-check | Check health-check.path.<serviceId> and supplier bean |
| RestClient throws UnknownHostException | Non-@LoadBalanced builder injected | Check bean qualifier and logical URI |
| RestTemplate calls fixed host | Non-@LoadBalanced bean or different request factory/client | Inspect actual injected bean |
| WebClient skips LB filter | WebClient.create() or plain builder | Check @LoadBalanced WebClient.Builder |
| WebClient invokes twice / duplicate metrics | LB filter added twice | Check auto-config vs. manual filter |
| Feign calls localhost URL | url in @FeignClient or Feign properties | Remove URL if discovery/LB is desired |
| Feign skips LB despite @FeignClient name | Missing spring-cloud-starter-loadbalancer | Check dependency tree/BOM |
| One Feign client's config affects others | Config class scanned into parent | Move config outside scan or omit @Configuration |
| Two Feign clients with same name overwrite each other | Missing distinct contextId | Assign unique contextId values |
| Feign timeout property ignored | Wrong feignName/contextId or properties override Java config | Check key and default-to-properties |
| Supplier lacks health filter | Custom supplier replaced default chain | Inspect delegates and supplier ordering |
| One service has instances, another empty | Different discovery/service IDs | Check registry per service ID |
| Tests pass yet production fails | TestPropertySource or different profile/env | Compare active profiles and config revisions |
| Context missing from startup logs | LoadBalancer context initializes lazily | Send a request or configure eager-load |
| Edited YAML yet runtime unchanged | Context already built, higher-precedence override, or process not restarted | Check property sources and lifecycle |

## 18. Runbook for ineffective configuration

Proceed in order and record findings at each step:

### 18.1. Scope the request

1. Identify the executing client: RestTemplate, RestClient, WebClient, or OpenFeign.
2. Record the logical URI (with sensitive queries stripped).
3. Identify the service ID from URI host or Feign name.
4. Confirm whether any fixed URL exists.
5. Confirm which HTTP client bean is actually injected.

### 18.2. Scope the context

1. Match the service ID against @LoadBalancerClient name/value.
2. Check whether the config was component-scanned into the parent context.
3. Check whether @LoadBalancerClients defaultConfiguration accidentally applies globally.
4. Inspect child contexts and bean types per service ID.
5. Inspect the active supplier list and algorithm.

### 18.3. Scope properties

1. Confirm the property supports per-client configuration.
2. Verify spelling of the clients.<serviceId> prefix.
3. Check global exceptions such as enabled/retry.enabled/cache.enabled/stats.micrometer.enabled.
4. Check map properties that retain direct service-ID syntax.
5. Check profiles, environment variables, Config Server, CLI flags, and test overrides.
6. Check Feign name/contextId and separate URL properties.

### 18.4. Verify with real requests

1. Call a safe endpoint via service ID.
2. Identify which backend instance received the request.
3. Verify selected instance and response body/access logs.
4. Check HTTP attempt count if retries are enabled.
5. Call a second service ID to confirm config does not leak across clients.

### 18.5. Fix and deploy

- Fix service ID or prefix in the authoritative configuration source.
- Move config classes out of component scan or switch to per-client registration.
- Fix the exact builder/client bean injected at call sites.
- Remove fixed URLs if LoadBalancer is required.
- Rebuild a properly ordered supplier chain if a custom supplier replaced the default.
- Restart/refresh contexts when startup-bound config changes; do not assume every bean updates dynamically.
- Re-run unit and integration tests before rollout.

## 19. Scenario exercises

### 19.1. Scenario A: Both Inventory and Payment use Random

~~~java
@Configuration
@LoadBalancerClients(
        defaultConfiguration = RandomLoadBalancerConfiguration.class)
class LoadBalancerConfiguration {
}
~~~

**Question:** Why did Payment also change algorithms?

**Answer:** defaultConfiguration acts as the default configuration for LoadBalancer clients. If only Inventory needs Random, register it via @LoadBalancerClient(name="inventory-service", configuration=...) and keep the config class outside component scanning.

### 19.2. Scenario B: @LoadBalancerClient is right, yet requests still do DNS lookup

**Context:** The annotation registers inventory-service accurately, yet RestClient throws UnknownHostException.

**Answer:** Check whether RestClient.Builder carries @LoadBalanced and whether the inventoryRestClient bean is built from that exact builder. @LoadBalancerClient does not automatically make every RestClient load-balanced.

### 19.3. Scenario C: Per-client retry stays disabled

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      clients:
        inventory-service:
          retry:
            enabled: true
~~~

**Question:** Is the service ID wrong?

**Answer:** The service ID may be right, yet this property has global/per-client constraints. Global retry disabled cannot be re-enabled per client in the opposite direction. Enable globally if policy allows, then disable retries selectively on clients that should not retry.

### 19.4. Scenario D: Feign name is right, yet it calls localhost

~~~java
@FeignClient(
        name = "inventory-service",
        url = "http://localhost:8081")
interface InventoryClient {
}
~~~

**Answer:** The annotation URL makes Feign call directly, bypassing LoadBalancer. To use service discovery, omit url and keep name. Also check for URLs in spring.cloud.openfeign.client.config.

### 19.5. Scenario E: Inventory's Feign configuration gives Payment an Inventory header

**Answer:** The config class was likely component-scanned into the parent context or set as defaultConfiguration. Keep the class outside component scanning, pass it only to Inventory's @FeignClient configuration, and assign distinct contextId values if multiple Feign clients target the same service ID.

### 19.6. Scenario F: Health-check path unchanged despite clients.inventory-service

**Answer:** health-check.path is a service-ID map preserving direct syntax for backward compatibility, i.e., health-check.path.inventory-service. In addition, HealthCheckServiceInstanceListSupplier must actually be present in the supplier chain; declaring the path alone does not create the scheduler/health supplier in every configuration.

### 19.7. Scenario G: Tests see Random, production uses Round Robin

**Answer:** Compare active profiles, Config Server labels, environment variables, CLI args, and custom config classes in deployment. Check whether the child context is overridden by global/default configuration. Verify the actual bean implementation inside the production process rather than trusting one YAML file in Git.

## 20. Anti-patterns to avoid

| Anti-pattern | Consequence | Right approach |
| --- | --- | --- |
| Using @LoadBalancerClients defaultConfiguration for one service | All clients inherit default config | Use per-service-ID @LoadBalancerClient |
| Putting custom LB config in a component-scanned package | Bean registers in parent/global context | Omit @Configuration or place outside scan |
| Hardcoding service ID inside custom LoadBalancer bean | Other service contexts reference wrong supplier | Use LoadBalancerClientFactory.PROPERTY_NAME |
| Confusing instance ID with service ID | Config fails to match requests | Use service ID in annotations/prefixes |
| Using Java bean name as clients.<id> key | Property fails to match client | Use the exact service ID |
| Building RestClient from a plain builder | LB interceptor never runs | Inject @LoadBalanced RestClient.Builder |
| Calling WebClient.create() on a service-ID URI | Bypasses LB integration | Use @LoadBalanced WebClient.Builder |
| Attaching the LB filter twice | Requests/metrics processed twice | Use a single integration path |
| Putting a fixed URL in @FeignClient | Bypasses LoadBalancer | Use name and discovery |
| Using contextId as service ID instead of name | Registry lookup fails | Keep name as service ID; contextId isolates Feign config |
| Scanning per-client Feign config globally | Interceptors/decoders leak to other clients | Separate config package |
| Assuming every property uses clients.<id> | Map/global properties do not bind as expected | Read version-matched configprops/reference |
| Trying to enable per-client when global flag is off | Has no effect | Fix global policy or supplier config |
| Adding multiple ServiceInstanceListSupplier beans without clear order | Default/custom chain overridden | Control bean scope and delegates |
| Treating Git YAML as runtime proof | Misses env/profile overrides | Inspect effective Environment safely |
| Restarting entire cluster when one bean is misconfigured | Large blast radius | Identify affected context/client and roll out cleanly |

## 21. Checklist before concluding the fix is complete

- [ ] Identified the exact HTTP client being invoked.
- [ ] Identified the true logical service ID from URI host or Feign name.
- [ ] @LoadBalancerClient name/value matches the service ID.
- [ ] Registry/DiscoveryClient has entries for that exact service ID.
- [ ] Client carries the matching @LoadBalanced integration.
- [ ] No fixed URL bypasses LoadBalancer.
- [ ] LoadBalancer child context exists and holds expected beans.
- [ ] Custom configuration class is not accidentally component-scanned into parent.
- [ ] defaultConfiguration does not unintentionally affect all clients.
- [ ] clients.<serviceId> prefix is valid and property supports per-client scoping.
- [ ] Checked global exceptions for enabled/retry/cache/stats.
- [ ] Map properties use the proper direct service-ID syntax.
- [ ] Profiles/env/CLI/Config Server do not override unexpectedly.
- [ ] Supplier chain and cache/health/filter ordering are valid.
- [ ] Feign name/contextId/URL/property URL are cleanly separated.
- [ ] Per-client Feign config is not scanned into global config.
- [ ] Unit tests verify bean types/contexts per service ID.
- [ ] Integration tests send HTTP via service ID to real/mock backends.
- [ ] Tested at least two service IDs to catch configuration leakage.
- [ ] Logs/metrics do not expose tokens, API keys, cookies, or sensitive data.
- [ ] Rollout/rollback are controlled with an explicit config revision.

## 22. Summary

When per-client Spring Cloud LoadBalancer configuration fails to take effect or applies to the wrong service, the cause almost always lies in **service ID and context boundaries**, **component-scan scope**, **HTTP client integration**, or **property precedence**.

Always inspect in this order:

1. **Which service ID is the request calling?**
2. **Is the HTTP client truly wired with LoadBalancer?**
3. **Which child context was created and which beans live inside it?**
4. **Is the setting per-client, global, or a special map property?**
5. **Which runtime configuration source wins?**
6. **Which backend actually receives the request?**

Distinguishing LoadBalancer child contexts from Feign named-client contexts and HTTP client beans narrows down bugs rapidly. After fixing, test **both the target client and an unrelated client** to prove configurations are properly isolated.

## 23. References

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): child contexts, @LoadBalancerClient/@LoadBalancerClients, per-client properties, supplier chains, and global properties.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestTemplate, RestClient.Builder, and WebClient.Builder.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): property names and data types by release train.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named-client contexts, name/contextId, configuration properties, URL overrides, and LoadBalancer integration.
- [Spring Cloud LoadBalancer – Source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): default ReactorLoadBalancer, ServiceInstanceListSupplier, and auto-configuration conditions.
- [Spring Cloud LoadBalancer – Getting Started](https://spring.io/guides/gs/spring-cloud-loadbalancer): example per-client configuration with @LoadBalancerClient.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, profiles, and environment variables.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): securing env/configprops and runtime configuration inspection.
- [Spring Framework – RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient.Builder and request factories.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient.Builder and reactive filter chains.
