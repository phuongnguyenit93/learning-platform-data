# Inspecting Effective WebFlux Configuration When Library Beans Alter Defaults

## 1. Problem: Adding a Library Changes WebFlux Behavior

In Spring Boot, the exact same WebFlux controller code can return different results after adding a starter or upgrading a dependency, even without touching `application.yml`. A library may contribute auto-configuration, declare `@Bean`s, or register `WebFilter`, `WebExceptionHandler`, `WebFluxConfigurer`, codecs, converters, routers, or a security chain. Those new beans can **add** behavior, **displace** default beans conditionally, or **alter processing order**.

Real-world examples:
- Before adding a starter, `GET /api/products` returned 200; afterward it returns 401 because Spring Security added a filter chain.
- A library's `WebFilter` adds a new response header or blocks a group of URLs.
- A `WebFluxConfigurer` alters CORS, formatters, or static-resource routing.
- A `CodecCustomizer` changes JSON decoding or buffer limits, causing previously accepted bodies to fail.
- A `WebExceptionHandler` bean formats errors differently, or intercepts exceptions before controller advice sees them.
- A configuration carrying `@EnableWebFlux` causes Spring Boot's WebFlux customizations to stop applying as before.

The central question of this lesson: **How do you prove which bean came from a library, which configuration conditions changed, and where actual HTTP behavior differs?**

### Learning Outcomes

After this lesson, you will be able to:
1. Distinguish auto-configuration **back-off** from **additive bean contribution**.
2. Distinguish `WebFluxConfigurer` (keeps Boot auto-config) from `@EnableWebFlux` (takes manual control of WebFlux config).
3. Read `ConditionEvaluationReport` and Actuator endpoints `conditions`, `beans`, `configprops`, `env`, and `mappings` purposefully.
4. Trace a bean's origin from dependencies, classes, or auto-config imports, along with filter order and error-resolution order.
5. Build reproducible before/after experiments covering requests, responses, and assertions.
6. Pick the minimal fix without disabling auto-configuration indiscriminately.

Scope: Spring Boot **3.5.x**, Spring Framework 6, Java 17+, WebFlux reactive runtime. Code uses 3.x-specific packages/imports; on Spring Boot 4.x+, verify APIs and module names accordingly.

## 2. Understanding the Three Mechanisms That Alter Defaults

### 2.1. Library Adds New Beans to the Processing Pipeline: Additive

Many bean types are **additive** and do not remove existing configuration.

For example, `WebFilter` beans present in the application context are added to Spring WebFlux's filter chain. When a library contributes a new `WebFilter`, requests pass through an extra step before/after handlers. That filter can mutate requests, set headers, reject calls, or intercept downstream errors. The controller is unchanged, yet the HTTP outcome changes.

Similarly, a `WebFluxConfigurer` can append `CorsRegistry` rules, converters, or resource handlers to WebFlux configuration. Simply having a `WebFluxConfigurer` bean does not make Spring Boot stop configuring WebFlux.

### 2.2. Auto-Configuration Backs Off Because a Condition No Longer Holds: Back-Off

Spring Boot uses conditional annotations such as:

| Common condition | What it checks | Why it can change after adding a library |
|---|---|---|
| `@ConditionalOnClass` | Checks whether a class is on the classpath | New starter brings in extra APIs/drivers/classes |
| `@ConditionalOnMissingClass` | Active only when a class is absent | Newly present class causes default branch to back off |
| `@ConditionalOnBean` | Requires a bean of matching type/name | Library provides a bean that activates a new branch |
| `@ConditionalOnMissingBean` | Creates config/bean only if none exists yet | App/library bean appears, suppressing the default bean |
| `@ConditionalOnProperty` | Checks property presence and value | Dependency supplies defaults or alters startup environment |
| `@ConditionalOnWebApplication` | Applies only to matching web application type | Runtime resolved as Servlet instead of REACTIVE |
| `@Profile` | Creates bean only when matching profile is active | Differences across dev/staging/prod or test profiles |

**There is no rule saying "every library bean disables defaults."** You must locate the exact auto-configuration class or conditional `@Bean` method and inspect the condition that was evaluated.

Fragment illustrating a starter's mechanism (fragment only, not a full runnable library):

~~~java
@AutoConfiguration
class VendorPolicyAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RequestPolicy.class)
    RequestPolicy defaultRequestPolicy() {
        return new VendorDefaultRequestPolicy();
    }
}
~~~

If another eligible `RequestPolicy` bean already exists when the condition is evaluated, the default factory method may not activate. Verify the details in the **conditions report**. For a properly packaged Spring Boot 3.x starter, its auto-configuration classes are typically listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; the fragment above omits that registration file and domain types.

### 2.3. Ordering or Priority Among Multiple Beans Changes

Even when both beans exist:
- `@Order` / `Ordered` on `WebFilter` controls execution order on the inbound path.
- A `WebExceptionHandler` can handle errors ahead of other handlers.
- Handler mappings and router functions have their own ordering/specificity rules; a new route can match requests ahead of an old route.
- `@Primary` influences dependency injection selection when multiple candidates exist; it **does not** reorder filters or automatically make an auto-configuration back off.
- `@Qualifier` selects a specific bean at an injection site; `@ConditionalOnMissingBean` is a bean registration rule, not an injection rule.

Therefore, conclusions must be grounded in **which beans were created, which beans are actually invoked, and the final request behavior**.

## 3. Confirming This Really Is a WebFlux Runtime

Do not start debugging `WebFilter` behavior if the application is actually running Spring MVC.

Spring Boot defaults to MVC when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present. This is intentional because MVC apps often use `WebClient`. If you want a `REACTIVE` runtime, verify the application type explicitly—for instance, when genuinely needed via `SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)`—and inspect dependencies and configuration.

Distinctions:

| Signal | Appropriate conclusion |
|---|---|
| `WebClient` class is on the classpath | Proves only that reactive client APIs are available, **not** a WebFlux server |
| `spring-boot-starter-webflux` is present | Usually indicates WebFlux, but insufficient if an MVC starter is also present |
| Context is a reactive web server application context and mappings use `DispatcherHandler` | Strong evidence of a WebFlux runtime |
| `WebFilter` bean exists yet requests bypass it | Check runtime type, bean loading, filter chain, and order |
| Servlet `FilterRegistrationBean` is present | Not the mechanism for registering WebFlux `WebFilter` on Reactor Netty |

Inspect the dependency tree:

~~~bash
mvn dependency:tree
# Gradle projects:
./gradlew dependencies --configuration runtimeClasspath
~~~

Look for `spring-boot-starter-web`, `spring-boot-starter-webflux`, `spring-boot-starter-security`, and vendor starters. Check **transitive** dependencies too: an internal starter can pull in MVC or security unnoticed.

## 4. Distinguishing WebFluxConfigurer and @EnableWebFlux

This distinction is critical when libraries register configuration classes.

### 4.1. Extending Configuration While Keeping Spring Boot Defaults

Spring Boot recommends declaring `@Configuration` implementing `WebFluxConfigurer` **without `@EnableWebFlux`** when you want to add WebFlux settings while preserving Boot's auto-configured features.

Example adding CORS:

~~~java
@Configuration(proxyBeanMethods = false)
class CorsConfiguration implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://example.org")
                .allowedMethods("GET", "POST");
    }
}
~~~

This is a fragment for a WebFlux project with matching imports. It only adds a CORS mapping and does not replace the WebFlux infrastructure. If a library contributes a bean like this, effective CORS behavior can change even if properties were untouched.

### 4.2. Taking Full Control of WebFlux Configuration

`@EnableWebFlux` imports Spring Framework's WebFlux configuration and hands detailed configuration control to the application. In Spring Boot, this annotation causes parts of **Boot's WebFlux auto-configuration to back off**, since Boot assumes the application wants full manual ownership of WebFlux.

Consequently, Boot defaults for codecs, static resources, or other integrations may behave differently than before the annotation was added. Do not claim the framework "has no defaults left": Spring Framework still supplies its own configuration. Exactly which pieces changed must be verified via the conditions report and tests.

If an imported library `@Configuration` accidentally carries `@EnableWebFlux`, it is a prime suspect to check. **Never blindly add `@EnableWebFlux` just to make a `WebFluxConfigurer` bean take effect** in a Boot app.

### 4.3. HttpHandler/Codec Interception Points

Other mechanisms include:
- `WebHttpHandlerBuilderCustomizer` customizes the `HttpHandler` builder auto-configured by Boot.
- `CodecCustomizer` adjusts `HttpMessageReader` and `HttpMessageWriter`, affecting JSON, SSE, and read buffer limits.
- `WebFilter` wraps request handling.
- `WebExceptionHandler` resolves errors at the WebFlux layer.

All modify "WebFlux configuration," yet operate at distinct stages. **Identify the exact bean/type and measure real behavior rather than guessing from a JAR name.**

## 5. Audit Table of Beans a Library Might Contribute

| Bean / change | Runtime symptom | Primary check |
|---|---|---|
| `WebFilter` | Adds headers, blocks requests, alters routing, adds latency | List filters, check order, test same URL |
| `WebExceptionHandler` | Status codes, error bodies, and content types change | Check bean/order, pre-handler vs. in-handler errors |
| `WebFluxConfigurer` | CORS, converters, formatters, static mappings change | Bean definitions, CORS preflight, and mappings |
| `CodecCustomizer` | JSON/SSE/decoding behavior or memory limits change | Codec registrations, payload tests, conditions |
| `WebHttpHandlerBuilderCustomizer` | `HttpHandler` pipeline changes | Bean definition + request trace |
| `SecurityWebFilterChain` & security starter | 401/403, login redirects, CSRF, CORS changes | Security configuration and filter chain |
| `RouterFunction` / `HandlerMapping` | New 404s, route precedence shifts, new handlers | `/actuator/mappings`, request tracing |
| `WebFluxConfigurationSupport` / `@EnableWebFlux` | Boot WebFlux auto-config stops matching as before | `/actuator/conditions`, search for annotation/imports |
| `ReactiveWebServerFactory` / factory customizer | Port, SSL, server engine, or server settings change | Bean inventory + startup log + HTTP check |
| Jackson module / converter bean | JSON fields, null/enum/date serialization changes | Config/codec beans + JSON golden tests |
| Added property source | Different binding despite unchanged config file | `/actuator/env`, `/actuator/configprops`, property precedence |

The third column is vital: **merely seeing more beans is not proof**. Confirm whether the new bean actually participates in the failing endpoint's pipeline.

## 6. Investigation Workflow: From Symptom to Root Cause

### Step 1 — Lock Down a Reproducible Difference

Record baseline (before adding the library) and candidate (after adding the library):
- Commit/build hash, JDK, Spring Boot version, active profiles, property sources, and key environment variables.
- Runtime dependencies, transitive dependency tree, and library versions.
- Exact request: method, URL, query string, headers, auth, and body.
- Response: status, `Content-Type`, `Access-Control-Allow-Origin`, security headers, and body.
- Network conditions, reverse proxies, and DB/external API state.

Hold everything else constant if possible. Changing profiles while adding a library obscures the root cause.

~~~text
BASELINE:  GET /api/probe, Origin=https://client.example
           status 200, no X-Library, no CORS allow-origin

CANDIDATE: GET /api/probe, Origin=https://client.example
           status 200, has X-Library and Access-Control-Allow-Origin

=> suspect a WebFilter and a WebFluxConfigurer were activated
~~~

This is a hypothetical example illustrating the method, not measured output from your environment.

### Step 2 — Read the Condition Evaluation Report

Spring Boot prints its auto-configuration decisions when started with `--debug`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

For a built executable JAR, use `java -jar <jar-name>.jar --debug` (substituting your real JAR filename). The report groups positive matches and negative matches, detailing which conditions passed or failed.

Questions to answer:
- Did `WebFluxAutoConfiguration` match in both runs?
- Did a new vendor auto-configuration activate?
- Did any `@ConditionalOnMissingBean` stop matching because a library bean already existed?
- Was `SecurityAutoConfiguration` or reactive security configuration added?
- Did the environment switch to Servlet instead of REACTIVE?

**The condition report is evidence of bean creation decisions**, not complete proof of HTTP behavior. Combine it with the bean inventory and HTTP tests.

### Step 3 — Inspect Diagnostic Actuator Endpoints

With `spring-boot-starter-actuator` and configuration **restricted to secure local/test environments**, useful endpoints include:

| Endpoint | Question answered |
|---|---|
| `/actuator/conditions` | Why auto-configs matched or did not match |
| `/actuator/beans` | Which beans exist, their types, and origins/dependencies per endpoint detail |
| `/actuator/configprops` | Which `@ConfigurationProperties` bound and their effective values (sanitized) |
| `/actuator/env` | Property sources and resolved `Environment` values |
| `/actuator/mappings` | Registered controller/function/router mappings |
| `/actuator/health` | App is running and health status; does not prove auto-config correctness |

Example local `application.properties` for investigation:

~~~properties
management.endpoints.web.exposure.include=health,conditions,beans,configprops,env,mappings
~~~

Requires the Actuator dependency and proper endpoint access permissions. **Never expose** sensitive diagnostic endpoints publicly in production: bean inventories and configuration metadata can reveal class names, architecture, or secrets despite Spring Boot masking sensitive values. Protect them with authentication/authorization or run only in isolated local environments.

Inspect:

~~~bash
curl -s http://localhost:8080/actuator/conditions
curl -s http://localhost:8080/actuator/beans
curl -s http://localhost:8080/actuator/mappings
~~~

Responses are large JSON payloads; do not assume every endpoint is always enabled or returns HTTP 200. Availability depends on dependencies, exposure, access rules, and security.

### Step 4 — Trace the Bean Back to Its JAR / Configuration

In the `beans` output or an `ApplicationContext` debugger, identify:
- Bean name and concrete bean type.
- Which `@Bean` method or `@Configuration` class declared it.
- Whether it came from application `@ComponentScan`, `@Import`, Boot auto-config, or a vendor library.
- Whether conditions/profiles restrict it to specific environments.
- Whether the bean is additive, overrides injection, or caused a default bean to back off.
- What order a filter/handler has and whether it matches the failing URL.

In library JARs, inspect `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` (if the library uses Boot 3 auto-config) or manually imported `@Configuration` classes. Never patch framework internals as a workaround before finding the true origin.

### Step 5 — Compare Final HTTP Behavior

Replay baseline and candidate requests with identical headers, methods, and bodies. For example, for CORS:

~~~bash
curl -i -H "Origin: https://client.example" http://localhost:8080/probe
~~~

A thorough CORS check also requires an OPTIONS preflight when clients send methods/headers that trigger browser preflight. Verify `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials` where applicable; browsers may block responses even when `curl` reads them. Tests must match your application's real CORS contract.

## 7. Runnable Example: Simulating a Library Contributing WebFlux Beans

The example below uses a configuration annotated with `@Profile("vendor")` to **simulate beans a library might contribute**. It is a local before/after experiment and does not claim to replicate every mechanic of a real-world third-party starter.

Two beans are added when the `vendor` profile is active:
- A `WebFilter` adding the `X-Library: enabled` header.
- A `WebFluxConfigurer` declaring CORS for `/probe`.

There is no `@EnableWebFlux`, so Boot's auto-configuration features remain intact.

### 7.1. Create the Maven Project, Java 17+

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-bean-drift</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

File `src/main/resources/application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,conditions,beans,configprops,mappings
~~~

These Actuator endpoints are for isolated local testing only. The example omits Spring Security; this configuration is not safe to expose directly to the Internet.

File `src/main/java/example/diag/BeanDriftApplication.java`:

~~~java
package example.diag;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class BeanDriftApplication {

    public static void main(String[] args) {
        SpringApplication.run(BeanDriftApplication.class, args);
    }

    @Bean
    ApplicationRunner beanEvidence(ConfigurableApplicationContext context) {
        return args -> {
            System.out.println("LIBRARY_FILTER="
                    + context.containsBean("vendorHeaderFilter"));
            System.out.println("LIBRARY_CORS="
                    + context.containsBean("vendorCorsConfigurer"));
        };
    }
}

@RestController
class ProbeController {

    @GetMapping(path = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> probe() {
        return Mono.just("ok");
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("vendor")
class SimulatedVendorLibraryConfiguration {

    @Bean
    WebFilter vendorHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders().set("X-Library", "enabled");
            return chain.filter(exchange);
        };
    }

    @Bean
    WebFluxConfigurer vendorCorsConfigurer() {
        return new WebFluxConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/probe")
                        .allowedOrigins("https://client.example")
                        .allowedMethods("GET");
            }
        };
    }
}
~~~

In the Java file above, there is one public class matching the filename. Package-private classes in the same package are scanned by `@SpringBootApplication`. `SimulatedVendorLibraryConfiguration` activates only when the `vendor` profile is active. The `Component` import is unused and can be removed without changing how the program runs.

### 7.2. Run Baseline

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Lines printed by `ApplicationRunner`:

~~~text
LIBRARY_FILTER=false
LIBRARY_CORS=false
~~~

In another terminal:

~~~bash
curl -i -H "Origin: https://client.example" http://localhost:8080/probe
~~~

Expected HTTP status is **200**, body **`ok`**. Because no vendor filter or configurer is active, the response has no `X-Library: enabled` header and no `Access-Control-Allow-Origin: https://client.example` header from the vendor config. Other headers depend on the container.

### 7.3. Run Candidate with "Library" Beans

Stop the baseline instance and run the same project with the `vendor` profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=vendor
~~~

Lines printed by `ApplicationRunner`:

~~~text
LIBRARY_FILTER=true
LIBRARY_CORS=true
~~~

Resend the request:

~~~bash
curl -i -H "Origin: https://client.example" http://localhost:8080/probe
~~~

Expected observations:
- HTTP **200**, body **`ok`** unchanged.
- Header **`X-Library: enabled`** appears.
- CORS header **`Access-Control-Allow-Origin: https://client.example`** appears for the allowed `Origin`.

The experiment proves behavior can diverge solely due to **new beans in the context**, even when controllers and endpoints are untouched. When analyzing a real starter, replace "enabling the `vendor` profile" with controlled dependency changes and compare the same evidence.

### 7.4. Verify via Actuator

In the local environment of the example:

~~~bash
curl -s http://localhost:8080/actuator/beans
curl -s http://localhost:8080/actuator/conditions
curl -s http://localhost:8080/actuator/mappings
~~~

In the candidate run, look for `vendorHeaderFilter` and `vendorCorsConfigurer`. In the baseline run, those two beans do not exist. `conditions` shows Boot's auto-configuration decisions; enabling additive beans may not cause `WebFluxAutoConfiguration` to stop matching. `mappings` shows `GET /probe` is still registered.

**Crucial takeaway:** HTTP behavior can change while `conditions` reports no back-off, simply because additive beans joined the filter/configurer chain. Do not expect the conditions report alone to reveal every runtime change.

## 8. Testing When Added Beans Cause Defaults to Back Off

The experiment above demonstrated **additive contribution**. To investigate **back-off**, inspect an auto-configuration conditioned on `@ConditionalOnMissingBean`. General rule:

~~~text
Before:
  No bean of type Policy exists
  -> VendorDefaultAutoConfiguration creates defaultPolicy
  -> /actuator/conditions shows condition matched

After:
  Another starter or app adds a bean of type Policy
  -> MissingBean condition no longer holds
  -> defaultPolicy is not created
  -> New Policy bean is used at injection points
~~~

The diagram is conceptual. In real Spring Boot, conditions are evaluated during bean definition registration in auto-config processing order. Do not place `@ConditionalOnBean`/`@ConditionalOnMissingBean` arbitrarily on `@Configuration` classes with uncontrolled ordering; in starters, use Boot's official auto-configuration model and ordering.

To prove this in a real application:
1. Locate the entry in `/actuator/conditions` and record the auto-config method and condition message.
2. Find the replacement bean name/type in `/actuator/beans`.
3. Trace the new bean's source to a JAR, `@Bean` method, `@Import`, or auto-config imports.
4. Run the matching request/codec/serialization test.
5. If removing the library restores the condition match and baseline HTTP behavior, you have strong causal evidence.

If two beans of the same type exist without a qualifier or `@Primary`, you may hit **`NoUniqueBeanDefinitionException`** rather than "silently picking the other one." If two beans attempt to register the same name when overriding is disabled, the app may **fail to start**. Never confuse bean name collisions, injection ambiguity, and conditional back-off.

## 9. Typical Case: A Library Pulls In Spring Security

Adding the security starter to a WebFlux app can change default endpoint access: a previously open URL may start requiring authentication depending on active configuration. This stems from security auto-configuration and the reactive filter chain, not from controllers changing business logic.

Steps to verify:
- Check whether `spring-boot-starter-security` entered the runtime classpath directly or transitively.
- Inspect `SecurityWebFilterChain`, `WebFilterChainProxy`, and related security configurations.
- Read the conditions report for conditional security auto-configs; do not guess from a single package name.
- Send the same request with and without an `Authorization` header, checking for 401, 403, redirects, or other changes.
- Do not disable security globally just to make tests return 200; define explicit security policies and write integration tests.

Regular WebFlux `WebFilter`s and Spring Security's `WebFilterChainProxy` interact via ordering. However, external `WebFilter` order **differs** from internal security filter order inside the security chain. When a request is rejected before reaching a controller, `@RestControllerAdvice` does not necessarily produce the security response. Distinguish Spring Security's authentication entry point and access denied handler.

## 10. Case: Codecs/JSON Change When a Library Enters the Classpath

Spring WebFlux uses `HttpMessageReader` and `HttpMessageWriter` coordinated through codec configuration. Spring Boot supplies defaults based on libraries on the classpath and `CodecCustomizer` beans.

Adding a JSON/Jackson module, custom deserializer, or codec customizer can alter:
- Which media types are supported for reading/writing.
- How enums, dates/times, nulls, or special fields are serialized.
- How much data may be buffered in memory during decoding.
- How codec errors, `415 Unsupported Media Type`, `406 Not Acceptable`, `400 Bad Request`, or `DataBufferLimitException` behave depending on where the failure occurs.

Do not infer behavior solely from seeing a `CodecCustomizer`: inspect what methods it actually calls. The snippet below is a fragment inside a `WebFluxConfigurer`, not a complete class:

~~~java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
~~~

This adjusts the maximum memory size for certain decode operations that buffer into RAM; it is not a total HTTP request size limit in all cases. When a library supplies a `CodecCustomizer`, verify the resulting effective configuration and test representative payloads.

**Never enable `registerDefaults(false)` on `CodecConfigurer` unless you explicitly register full replacements for all needed readers and writers.** A customizer accidentally disabling default codecs can abruptly break JSON endpoints.

## 11. Case: Added Routes, Error Handlers, or Filters Change Handling

### WebFilter and Execution Timing

Lower order values generally run earlier on the inbound path. A filter can set status/headers, continue via `chain.filter(exchange)`, or short-circuit immediately without calling the chain. If a library adds a filter blocking `/api/**`, requests never reach the controller even though Actuator still lists the mapping.

Once a response is committed, filters and exception handlers cannot change already-sent status codes or headers. Check `exchange.getResponse().isCommitted()`, use `beforeCommit` when headers must be prepared before writing, and avoid setting required headers inside `doFinally` after the body completes.

### WebExceptionHandler

A new `WebExceptionHandler` can intercept errors ahead of other error handlers. Check `@Order`/`Ordered`, which exception types it handles, and whether it returns `Mono.empty()`/completed publisher or `Mono.error(ex)` to pass along. Never catch every exception and return 200, as that hides failures.

### RouterFunction and HandlerMapping

A library contributing a `RouterFunction` or handler mapping can add routes, shift matching order, or create conflicts. Use `/actuator/mappings` and live requests to verify effective routing. Functional route filters (`HandlerFilterFunction`) apply only to the router functions they wrap, whereas `WebFilter` applies across the WebFlux application; they are not interchangeable.

## 12. Regression Testing in CI and Integration Environments

The goal is turning the hypothesis "a new dependency may alter defaults" into repeatable verification.

### 12.1. Testing HTTP Contracts

In a WebFlux app with test dependencies, use `WebTestClient` to assert not only 200 status, but also headers and body. Fragment inside a test class with a configured `WebTestClient client`:

~~~java
client.get()
        .uri("/probe")
        .header("Origin", "https://client.example")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Library", "enabled")
        .expectHeader().valueEquals(
                "Access-Control-Allow-Origin", "https://client.example")
        .expectBody(String.class).isEqualTo("ok");
~~~

This asserts the **candidate `vendor` profile** of the example; the baseline lacks those two headers. For integration tests, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an appropriately configured `WebTestClient`, and activate the target profile with `@ActiveProfiles("vendor")`.

### 12.2. Testing Bean Definition Differences

You can verify a bean's presence with Spring Test:

~~~java
assertThat(context.containsBean("vendorHeaderFilter")).isTrue();
assertThat(context.containsBean("vendorCorsConfigurer")).isTrue();
~~~

This is a fragment inside a test with an `ApplicationContext context` and AssertJ. Checking bean presence alone is **not enough**: you must also test the resulting status, headers, and behavior. To test a starter's auto-configuration conditions in isolation, Spring Boot provides `ApplicationContextRunner` and `ReactiveWebApplicationContextRunner` (or version-specific runners); initialize the right auto-configs and environment in tests so you do not draw false conclusions from a context lacking real WebFlux infrastructure.

### 12.3. Establishing a Baseline When Upgrading Libraries

For every version or starter upgrade:
1. Save a runtime dependency manifest for both baseline and candidate.
2. Run smoke tests covering status codes, security, CORS, JSON, and critical URLs.
3. Inspect the conditions report whenever behavior diverges.
4. Compare bean inventories for sensitive types; avoid asserting exact total bean counts because Spring Boot upgrades may add valid new beans.
5. Distinguish documented migration-guide changes from unintended regressions.
6. If a new feature intentionally updates defaults, document the new contract and update tests deliberately.

Note that `@WebFluxTest` does not scan every `@Component` and library auto-configuration the way a full application does. When suspecting a third-party bean, **prefer full `@SpringBootTest` with matching dependencies and profiles**, or explicitly import the configuration under test.

## 13. Safe Fixes by Root Cause

| Finding | Preferred fix | Avoid |
|---|---|---|
| Library adds an unwanted `WebFilter` | Use library properties/conditions or adjust filter chain/order | Disabling all of WebFlux |
| Starter enables security by default | Define reactive security policy and add intentional 401/403 tests | Opening all endpoints just to get 200s back |
| `WebFluxConfigurer` alters CORS | Adjust/exclude the specific config bean, verify preflight | Setting `allowedOrigins("*")` carelessly with credentials |
| `@EnableWebFlux` imported unintentionally | Remove annotation from configuration to restore Boot auto-config | Manually re-adding individual default beans blindly |
| `CodecCustomizer` changes codecs | Apply minimal codec override, test JSON and large payloads | Disabling all default codecs |
| A bean causes auto-config back-off | Inspect bean name/type/conditions; adjust registration or make overrides explicit | Turning on bean definition overriding as a first resort |
| Library adds a route | Adjust router order, path/matchers, or module routing | Deleting working controllers without tests |
| `WebExceptionHandler` alters errors | Handle only targeted exception types and respect committed responses | Returning 200/400 for every `Throwable` |
| App runs MVC instead of WebFlux | Audit dependencies and web application type | Assuming having `WebClient` is enough |

**Fix directly at the root cause:** official starter properties, bean registration conditions, qualifiers/orders/matchers, or Boot-supported Spring WebFlux configuration. `spring.autoconfigure.exclude` can disable a specific auto-config when genuinely required, but it is a broad hammer that can drop other vital beans. Always inspect the resulting bean/condition diff after excluding.

## 14. Diagnosing Startup Failures

Not every default change shows up as HTTP 401 or altered JSON. A starter can also cause startup failures.

Key failure types to distinguish:

- **`BeanDefinitionOverrideException`:** two beans share the same name when overriding is disallowed; locate both declarations. Never "quick-fix" by setting `spring.main.allow-bean-definition-overriding=true` before explaining the conflict.
- **`NoUniqueBeanDefinitionException`:** multiple beans of the same type qualify for injection; apply `@Qualifier`, `@Primary`, or keep a single bean per requirements.
- **`NoSuchBeanDefinitionException`:** a default bean backed off while a component still requires a dependency that no longer exists; inspect conditions and import chains.
- **Ambiguous mapping:** overlapping annotated or functional routes whose order/handlers conflict; inspect mappings and registration code.
- **`ClassNotFoundException` / `NoClassDefFoundError`:** incompatible dependency versions or classpath issues, distinct from valid conditional back-off.
- **Stack trace during codec/mapper creation:** library Java configuration failing when creating beans before runtime even starts serving requests.

Read the **root cause** at the bottom of the cause chain and cross-reference the conditions report; do not blame every Spring context failure on "auto-config didn't pick up my bean."

## 15. Common Pitfalls

1. **"Adding a bean always makes Boot turn off its default."** False: many beans are additive, like `WebFilter` and `WebFluxConfigurer`.
2. **"Having WebClient means the server is WebFlux."** False: MVC apps can also use `WebClient`.
3. **"`@EnableWebFlux` is required just to turn on Spring Boot WebFlux."** False: that annotation moves configuration control away from Boot.
4. **"`@Primary` makes a `WebFilter` run first."** False: `@Order`/`Ordered` and chain assembly govern order.
5. **"A matched condition guarantees the endpoint works as expected."** False: filters, routing, codecs, security, and response writers also apply.
6. **"Seeing 401 after adding the Security starter means the controller is broken."** False: security filters may reject the request beforehand.
7. **"Testing only HTTP 200 is enough."** False: headers, CORS preflight, content types, and JSON can all shift.
8. **"Seeing a bean in `/actuator/beans` means it handles every request."** False: it must still be wired into runtime execution and match the request.
9. **"`@WebFluxTest` always matches the production context."** False: test slices exclude beans and configs outside slice scope.
10. **"Actuator `/conditions` alone catches every change."** False: additive beans alter behavior without causing auto-config back-off.
11. **"Exposing `/actuator/env` and `/actuator/beans` publicly is fine for debugging production."** False: those endpoints expose internal details and must be restricted and secured.
12. **"Just delete the library when behavior differs."** Not always viable: the library may be needed for security or codecs; configure it properly and add tests.
13. **"Same property file means identical environments."** False: profiles, environment variables, classpath, and auto-config conditions can differ.
14. **"Enabling `allow-bean-definition-overriding` reveals the root cause."** It masks conflicts instead of resolving them.
15. **"Adding any custom codec is harmless."** It can disable default readers/writers or alter memory behavior.

## 16. Investigation Checklist Before Merging Dependency Changes

- [ ] Verified the app runs `WebApplicationType.REACTIVE`, not MVC by mistake.
- [ ] Recorded both direct and transitive dependencies before and after.
- [ ] Reproduced the failing request with identical profile, properties, headers, and body.
- [ ] Read auto-configuration conditions, especially `@ConditionalOnMissingBean` branches.
- [ ] Located new beans via `/actuator/beans` or `ApplicationContext` and noted their declaration source.
- [ ] Classified each new bean as additive, back-off, injection selection, or order-changing.
- [ ] Checked whether any library imports `@EnableWebFlux` or `WebFluxConfigurationSupport`.
- [ ] Audited `WebFilter`, `WebExceptionHandler`, `WebFluxConfigurer`, codecs, routing, and security.
- [ ] Checked effective resolved properties, not only the base config file.
- [ ] Verified HTTP status, headers, body, and CORS preflight with real requests.
- [ ] Added full application context tests when libraries configure behavior via auto-config.
- [ ] Applied the minimal targeted fix and re-measured before/after behavior.
- [ ] Confirmed sensitive Actuator endpoints are not exposed publicly for debugging.
- [ ] Documented new bean/configuration decisions and expected HTTP behavior.

## 17. Conclusion

When adding a library changes Spring WebFlux behavior, never start by disabling auto-configuration. Instead: **confirm the runtime, diff dependencies, inspect configuration conditions, locate new beans, trace how they are invoked, and verify with real HTTP requests**. Library beans may join the filter chain directly, override selection via ordering/DI, or trigger `@ConditionalOnMissingBean` back-offs. `WebFluxConfigurer` is normally the extension mechanism that preserves Spring Boot conveniences, while `@EnableWebFlux` signals taking explicit manual control. A change is truly understood only when you have evidence from both **beans/conditions** and **runtime HTTP responses**, backed by regression tests.

## References

- Spring Boot 3.5 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html
- Spring Boot 3.5 — Actuator endpoints: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Framework 6 — WebFlux Config: https://docs.spring.io/spring-framework/reference/web/webflux/config.html