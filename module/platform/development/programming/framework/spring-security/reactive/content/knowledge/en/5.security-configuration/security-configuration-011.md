# Controlling Bean Conflicts and Understanding Auto-Configuration Back-Off Conditions in Reactive Spring Security

## 1. Lesson Objectives

When initializing Spring Boot + Spring WebFlux + Spring Security, the application normally already has a default security configuration even if you have not defined any security beans. Once you add a bean of your own, part of the default configuration may **back off**. Sometimes the app still starts yet endpoints behave differently than expected; other times `ApplicationContext` creation fails due to duplicate bean names or multiple beans of the same type.

This lesson helps you:

1. Understand how Spring Boot evaluates auto-configuration conditions, especially `@ConditionalOnMissingBean`, `@ConditionalOnClass`, and `@ConditionalOnWebApplication`.
2. Distinguish configuring the **security WebFilter chain**, configuring the **user/authentication source**, and **enabling reactive Spring Security infrastructure**.
3. Know which beans cause default configuration to back off, and which beans **do not** affect the rest.
4. Recognize three distinct failure categories: **duplicate bean names**, **multiple beans of the same type causing injection ambiguity**, and **unmatched auto-config conditions**.
5. Run a Java 17+ example and inspect the Conditions Evaluation Report to verify changes.

**Focus:** Investigate **bean types**, **evaluated conditions**, and the **actual `SecurityWebFilterChain`** before editing configuration. The existence of one custom bean does not mean all of Spring Security is automatically disabled.

## 2. The big picture: from classpath to running beans

Spring Boot starts from libraries on the classpath and the state of the `ApplicationContext`. An auto-configuration class typically has conditions like:

~~~java
// ILLUSTRATIVE structure example, not complete Spring Boot source code
@AutoConfiguration
@ConditionalOnClass(SomeSecurityType.class)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
class ExampleReactiveAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ExampleService.class)
    ExampleService exampleService() {
        return new DefaultExampleService();
    }
}
~~~

The classes `SomeSecurityType`, `ExampleService`, and `DefaultExampleService` in this example are **hypothetical names to illustrate the mechanism**, not for compiling. Four key points:

- `@AutoConfiguration` marks configuration contributed by Boot. Applications enable auto-configuration via `@SpringBootApplication` or `@EnableAutoConfiguration`.
- `@ConditionalOnClass` applies only when the required classes are present on the classpath.
- `@ConditionalOnWebApplication(type = REACTIVE)` applies only to reactive web applications.
- `@ConditionalOnMissingBean` creates the default part only if **no bean matching the criteria already exists**. Criteria can be class/interface, bean name, annotation, or combined conditions.

**Back off** means Boot **skips registering part of its default configuration because a condition was not met**, letting the application-provided bean take over that responsibility. It is different from deleting a running bean, disabling the whole framework, or automatically merging rules.

Conditions are evaluated while processing bean definitions. `@ConditionalOnMissingBean` is specifically suited for **auto-configuration processed after user-declared beans**; do not casually put it on regular `@Configuration` classes assuming bean registration order will always be identical.

## 3. Three distinct configuration layers in Spring Security WebFlux

This is the most important part for avoiding confusion:

| Layer | Common components | Responsibility | When you change it |
| --- | --- | --- | --- |
| **Web security infrastructure** | `WebFilterChainProxy`, `@EnableWebFluxSecurity`, `WebFilter` beans | Wires Spring Security into WebFlux and dispatches security chains | A custom proxy bean affects the infrastructure layer; this is an advanced intervention |
| **HTTP request policy** | `SecurityWebFilterChain` built from `ServerHttpSecurity` | HTTP Basic, form login, JWT, matchers, and authorization rules | Defines your app's own chains/rules; you must cover all relevant routes |
| **Identity and authentication source** | `ReactiveUserDetailsService`, `ReactiveAuthenticationManager` | Loads users, verifies credentials, and builds `Authentication` | Replaces the default user mechanism; does not rewrite URL rules |

Several relationships to keep in mind:

- Having a custom `SecurityWebFilterChain` **does not mean** you have supplied a custom `ReactiveUserDetailsService`.
- Having a custom `ReactiveUserDetailsService` **does not mean** you have supplied `/admin/**` rules or permitted `/public`.
- Having a `WebFilterChainProxy` is different from having a `SecurityWebFilterChain`: the **proxy** selects and executes **the chains**.
- Reactive Spring Security uses `SecurityWebFilterChain` and `ServerHttpSecurity`. `SecurityFilterChain` and `HttpSecurity` are Servlet APIs and cannot substitute directly in WebFlux.

### 3.1. Auto-configuration classes worth knowing

According to Spring Boot 4.x documentation:

- `ReactiveWebSecurityAutoConfiguration` enables Spring Security configuration for reactive web apps. It relies on classpath and web-app type conditions; the API documentation notes that automatic activation backs off if the application defines its own `WebFilterChainProxy` bean.
- `ReactiveUserDetailsServiceAutoConfiguration` can provide a default in-memory `ReactiveUserDetailsService` and a `user` account with a generated password for development. It checks for the presence of authentication-related beans such as `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, `ReactiveAuthenticationManagerResolver`, and `ReactiveJwtDecoder`, among other conditions.
- When Spring Boot Actuator is added, `ReactiveManagementWebSecurityAutoConfiguration` is conditional on missing `SecurityWebFilterChain` and `WebFilterChainProxy`; it can back off for application-created chains, so you must define permissions for actuator endpoints yourself.

**Read at the right level of precision:** never infer all auto-configuration behavior from a single annotation or condition. Many config classes have nested conditions involving classpath, web application type, bean definitions, and properties.

### 3.2. A helpful state table

Assuming the project is **reactive WebFlux**, has the Spring Security starter, and has no other advanced configuration:

| What you declare | Which HTTP rules are used? | Boot's default user source? |
| --- | --- | --- |
| No custom security beans | Default policy requiring authentication | Usually creates `user` and a generated password |
| Only `SecurityWebFilterChain` | Your declared rules apply by matcher | **May still exist** because authentication source was not replaced |
| Only `MapReactiveUserDetailsService` | Default HTTP policy still applies | **Backs off** for the default user source; uses your users |
| Both chain and `ReactiveUserDetailsService` | Your declared rules | Your provided users |
| Custom `ReactiveAuthenticationManager` | Chains still must be configured properly | Default user config usually backs off per authentication condition |
| Custom `WebFilterChainProxy` | Depends on how the proxy is constructed | Does not automatically disable `ReactiveUserDetailsService` since that is a separate decision |

The table shows typical behavior. If a project uses OAuth2 Client, Resource Server, SAML, another security library config, or special properties, confirm the actual outcome using the application's own **Conditions Evaluation Report**.

## 4. Conditions that commonly trigger auto-config back-off

### 4.1. @ConditionalOnMissingBean: checking for absence of a bean

Suppose the application declares:

~~~java
@Bean
MapReactiveUserDetailsService applicationUsers() {
    UserDetails user = User.withUsername("learner")
            .password("{noop}learner123")
            .roles("USER")
            .build();
    return new MapReactiveUserDetailsService(user);
}
~~~

This is a **method that must be placed inside `@Configuration` or `@SpringBootApplication` with appropriate Spring Security imports**, not a standalone program. `MapReactiveUserDetailsService` implements `ReactiveUserDetailsService`, so the condition "no `ReactiveUserDetailsService` bean present" is no longer satisfied. Boot no longer needs to create the default in-memory user.

Common misconception: if you stop seeing "Using generated security password" in logs after adding this bean, that **does not prove** Spring Security was turned off; it may simply mean the **default user source** was replaced by the one you defined.

### 4.2. @ConditionalOnClass: dependencies altering conditions

When you add OAuth2 Client, OAuth2 Resource Server, or SAML2 Service Provider dependencies, the default authentication source may back off per Spring Boot's policy. This is not a "bean conflict" in the duplicate-name sense. With a JWT resource server, Spring Security may need a `ReactiveJwtDecoder` along with matching issuer/JWK settings; do not assume HTTP Basic with a random generated user still exists for login as before.

A dependency listed in `pom.xml` yet **absent from `runtimeClasspath`** does not satisfy classpath conditions either. Conversely, starters can pull classes in transitively and alter condition outcomes. Inspect `mvn dependency:tree` or `gradlew dependencies`.

### 4.3. @ConditionalOnWebApplication: Servlet or reactive?

An application including `spring-boot-starter-webflux` is not guaranteed to run in reactive mode if the MVC starter is also present and Boot chooses the Servlet web application type. In that case, configurations conditioned on `REACTIVE` will not apply as expected. Verify the classpath, `ApplicationContext` type, and web application type before adding extra security beans "to fix 404/401".

Never try to fix this by adding `SecurityFilterChain` and `SecurityWebFilterChain` side by side before determining which stack is actually running.

### 4.4. @ConditionalOnProperty: properties are not a master key

Some auto-configurations have property conditions. Yet you cannot assume setting an arbitrary property like `spring.security.enabled=false` will safely disable all security configuration. Check the **properties published in the exact version's documentation** and read the Conditions Report; for Spring Security, a custom security chain is usually the clearer way to establish HTTP policy.

### 4.5. Bean definition ordering and classpath

Conditions can be affected by:

- Beans declared in an internal module and picked up by `@ComponentScan`.
- Beans coming from a third-party library with `@AutoConfiguration`.
- A `@Configuration` class being `@Import`ed multiple times, or a bean with the same name declared in two configurations.
- `@Primary`, `@Qualifier`, and `@Order` used in different places with different meanings.
- Beans altered by test slices, `@Profile`, `@ConditionalOnProperty`, or environment profiles.

Therefore, inspecting the final configuration from the `ApplicationContext` is more reliable than looking at a single Java file.

## 5. Distinguishing types of bean conflicts

### 5.1. Two beans with the same name: overlapping definitions

**Broken configuration example for recognition**:

~~~java
@Configuration
class FirstSecurityConfig {
    @Bean("securityPolicy")
    String policyA() {
        return "A";
    }
}

@Configuration
class SecondSecurityConfig {
    @Bean("securityPolicy")
    String policyB() {
        return "B";
    }
}
~~~

This snippet omits imports and the startup class, strictly for illustration. The same bean name `securityPolicy` is registered twice. Spring Boot defaults to `spring.main.allow-bean-definition-overriding=false`; with two bean definitions competing for the same name, registration can throw `BeanDefinitionOverrideException`. Some Java configuration patterns have special overriding rules, so read the actual exception rather than guessing from two method names.

**How to resolve:** determine which bean owns the configuration, remove the duplicate declaration, or rename if **both are genuinely needed**. Never enable `spring.main.allow-bean-definition-overriding=true` just to "make the app start": that can hide confusion over which bean ultimately takes effect.

### 5.2. Multiple beans of the same type: injection ambiguity

A service requiring a single `SomeInterface`, when the context contains two implementations without a clear choice, can fail with `NoUniqueBeanDefinitionException` or a related dependency injection error.

To choose a bean **at an injection point**, you can use `@Qualifier("beanName")` or `@Primary` when semantically appropriate. Short illustrative example:

~~~java
@Service
class ReportService {
    private final ReportPolicy policy;

    ReportService(@Qualifier("strictPolicy") ReportPolicy policy) {
        this.policy = policy;
    }
}
~~~

This is an **illustrative snippet**, assuming `ReportPolicy` and a bean named `strictPolicy` are already defined. It does not represent selecting a security chain when an HTTP request arrives.

**Specifically:** having **multiple `SecurityWebFilterChain` beans is not automatically an error**. Spring Security supports multiple chains to protect different URL groups. In that case, use `@Order` and `securityMatcher(...)` appropriately. `@Primary` does not replace per-request security chain selection.

### 5.3. Back off: not an exception

When `@ConditionalOnMissingBean` is not met, Boot normally just records a "negative match" in the Conditions Report without **throwing an exception**. The application can start normally, yet now runs under your custom configuration. If a custom chain forgets a URL or drops an actuator permission rule, security behavior can change with no startup error.

### 5.4. Bean exists, yet wrong web stack

Servlet's `SecurityFilterChain` bean cannot replace WebFlux's `SecurityWebFilterChain`. A configuration bean "existing" in the `ApplicationContext` does not mean reactive requests pass through it. Choose the right packages and web application type.

## 6. Java 17+ lab: custom chain and custom users

The example below demonstrates two independent decisions: **defining HTTP policy** and **supplying a user service**, while helping compare outcomes when removing each bean.

### 6.1. Create the project

Using [Spring Initializr](https://start.spring.io/), choose Maven, Java 17+, Spring Boot **4.1.2** (or a compatible supported stable patch), group `com.example`, artifact `reactive-beans-demo`. Add **Spring Reactive Web** and **Spring Security**.

Minimal complete `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-beans-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

Let Maven/Boot's BOM manage Spring Security, Spring Framework, and Reactor versions without adding individual `<version>` tags per module. For Spring Boot 3.5.x, use the corresponding 3.5 parent/BOM and verify APIs on the version in use.

### 6.2. Complete Java code

Create `src/main/java/com/example/reactivebeans/ReactiveBeansDemoApplication.java`:

~~~java
package com.example.reactivebeans;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveBeansDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveBeansDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .pathMatchers("/profile").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService applicationUsers() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learner123")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(learner, admin);
    }

    @RestController
    static class ExampleController {

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/profile")
        Mono<String> profile() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "PROFILE:" + name);
        }

        @GetMapping("/admin")
        Mono<String> adminEndpoint() {
            return Mono.just("ADMIN_OK");
        }
    }
}
~~~

**Why is this code meaningful for back-off?**

1. `@SpringBootApplication` enables auto-configuration using the reactive web stack.
2. `applicationSecurity()` provides **`SecurityWebFilterChain`**: you define access rules and HTTP Basic. The app no longer relies on the default URL policy for the covered matchers.
3. `applicationUsers()` provides **`MapReactiveUserDetailsService`**, which is a `ReactiveUserDetailsService`: Boot stops creating the default in-memory user source once the missing-bean condition is no longer met.
4. You do not need to create `WebFilterChainProxy` manually. Boot and Spring Security still manage the required filter infrastructure.
5. `@EnableWebFluxSecurity` is not needed in a standard Spring Boot WebFlux app because Boot can activate it automatically. Outside Boot or with manual infrastructure setup, requirements may differ.
6. `"{noop}"` is strictly for local learning. In production, store passwords with an appropriate encoder, use HTTPS, and never hardcode credentials.
7. The `profile()` controller reads authentication from the Reactor Context rather than Servlet-style ThreadLocal `SecurityContextHolder`.

### 6.3. Running the project and observing results

If the project has the Maven wrapper generated by Spring Initializr:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

On Windows, substitute `.\mvnw.cmd clean package` and `.\mvnw.cmd spring-boot:run`. Without a wrapper, use your installed Maven: `mvn clean package` and `mvn spring-boot:run`.

With the server at `http://localhost:8080`, run in another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u learner:learner123 http://localhost:8080/profile
curl -i -u learner:learner123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/not-found
~~~

Expected outcomes:

| Request | HTTP status | Notable content | Reason |
| --- | --- | --- | --- |
| `/public`, anonymous | **200** | `PUBLIC_OK` | `permitAll` |
| `/profile`, anonymous | **401** | Depends on HTTP Basic config | Authentication required |
| `/profile`, learner | **200** | `PROFILE:learner` | User from `applicationUsers()` |
| `/admin`, learner | **403** | Config-dependent | Missing `ROLE_ADMIN` |
| `/admin`, admin | **200** | `ADMIN_OK` | Sufficient role |
| `/not-found`, admin | **403** | Config-dependent | `denyAll` blocks before handler lookup |

The two successful requests return plain text bodies matching the table in the example. Headers, 401/403 response bodies, and content negotiation can vary by version. These GET requests do not require CSRF adjustments; adding HTTP POST/PUT/DELETE requires reviewing CSRF tokens per authentication model.

### 6.4. Two small experiments to observe back-off clearly

Perform these in a **copy of the lab project**, changing one bean at a time and rebuilding/re-running.

**Experiment A — remove only `applicationUsers()`.** Keep `applicationSecurity()`. Without another custom authentication source, Boot can again create the `user` account with a random development password. Yet `/public`, `/profile`, and `/admin` rules are still governed by your custom chain. Credentials `learner:learner123` no longer exist.

**Experiment B — restore `applicationUsers()`, remove only `applicationSecurity()`.** Boot and Spring Security use the default web security policy for the app. Users `learner` and `admin` are still provided because `MapReactiveUserDetailsService` remains. `/public` is no longer `permitAll` under your custom policy, so anonymous access is normally blocked. Authentication challenge/redirect behavior depends on the `Accept` header and default setup.

**Conclusion from the two experiments:** changing the **user source** and changing **URL rules** are two independent decisions. Seeing the generated password log disappear or seeing one endpoint's status change is not enough to claim "all auto-configuration turned off".

## 7. Multiple SecurityWebFilterChain beans: when valid and when risky?

Spring Security WebFlux supports multiple `SecurityWebFilterChain` beans—for instance, protecting `/api/**` with JWT while protecting web pages with sessions/HTTP Basic. Each request is matched against chains in **order**; the highest-priority matching chain is used.

**Alternative configuration class** replacing the `applicationSecurity()` method in section 6 (do not add both simultaneously):

~~~java
package com.example.reactivebeans;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
public class MultiChainConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

Filename: `src/main/java/com/example/reactivebeans/MultiChainConfiguration.java`. Replace `applicationSecurity()` in the main class with this class, **keeping `applicationUsers()`** if you want to authenticate with the example users. `/profile` and `/admin` will be blocked by the `denyAll` fallback in this new setup; that is **intentional for illustration**, not a configuration protecting the previous section's endpoints. To allow them, declare appropriate rules before `denyAll`.

Lessons here:

- Two `SecurityWebFilterChain` beans with **different names** can coexist: Spring Security uses `@Order` and `securityMatcher` to pick a chain. Do not try fixing with `@Primary` because request routing does not use `@Primary` to pick chains.
- If **both chains match all URLs**, the higher-priority chain can shadow the other.
- If **no chain matches** a URL, requests may fall outside Spring Security's protection. Keep a fallback chain with an explicit policy.
- `@Order` governs chain evaluation order, while `pathMatchers(...)` order inside a chain governs authorization rules. These are two distinct levels.
- Spring Security WebFlux uses `ServerWebExchangeMatcher`. Never copy Servlet's `RequestMatcher` without switching to the reactive API.

## 8. Actuator: security bugs that easily appear when replacing chains

If a project adds Spring Boot Actuator, besides application endpoints there are operational endpoints such as `/actuator/health`, `/actuator/info`, `/actuator/metrics`, and `/actuator/conditions` (HTTP accessibility depends on exposure, availability, and permissions).

According to Spring Boot documentation and APIs, `ReactiveManagementWebSecurityAutoConfiguration` usually **backs off when the user supplies a `SecurityWebFilterChain` or `WebFilterChainProxy`**. Once you define your own chain, you must specify the required actuator policy yourself. Never assume actuator rules "automatically stay intact" after replacing the chain.

Configuration tip when the Actuator starter is actually present: use reactive `EndpointRequest` to match management endpoints by id, for example:

~~~java
import org.springframework.boot.security.autoconfigure.web.reactive.EndpointRequest;

// Inside authorizeExchange:
.matchers(EndpointRequest.to("health")).permitAll()
.matchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
.anyExchange().authenticated()
~~~

This is an **additional configuration snippet**, not a standalone runnable Java file. Order matchers specific before broad; add the required imports and `spring-boot-starter-actuator`. Beyond HTTP authorization, still configure which endpoints are exposed, restrict network access, and consider a separate management port. Never expose `conditions`, `env`, or sensitive data on public networks.

## 9. Diagnostics: the Conditions Evaluation Report is a reliable source

### 9.1. Viewing the conditions report with --debug

Spring Boot supports displaying the auto-configuration conditions report. In a Maven project:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

On Windows use `.\mvnw.cmd spring-boot:run -Dspring-boot.run.arguments=--debug`, or when running a JAR:

~~~bash
java -jar target/reactive-beans-demo-0.0.1-SNAPSHOT.jar --debug
~~~

The report typically includes sections such as **Positive matches** (conditions met), **Negative matches** (conditions not met), **Exclusions**, and **Unconditional classes**, depending on version/log format. Look for:

- `ReactiveWebSecurityAutoConfiguration`
- `ReactiveUserDetailsServiceAutoConfiguration`
- `ReactiveManagementWebSecurityAutoConfiguration` if using Actuator
- `OnBeanCondition`, `OnClassCondition`, `OnWebApplicationCondition` details and the bean or class that altered the condition.

Read only your own application's report after startup; never draw conclusions from another project's log screenshot. Enable debug in dev or test environments and handle logs per data-security policies.

### 9.2. Reading signals from startup errors

| Error / signal | Question to answer | Resolution path |
| --- | --- | --- |
| `BeanDefinitionOverrideException` | Are there two beans with the same name? Which classes declare them? | Remove or rename the unintended definition |
| `NoUniqueBeanDefinitionException` | Who is injecting a single bean where multiple candidates of that type exist? | Apply `@Qualifier`/`@Primary` at the right spot; for security chains check chain matching |
| `NoSuchBeanDefinitionException` | Was an expected bean skipped due to a condition, profile, or missing starter? | Check Conditions Report, classpath, and bean definitions |
| Missing generated password | Is there a custom `ReactiveUserDetailsService`, authentication manager, or JWT decoder? | Verify authentication source; do not assume security is off |
| `/public` returns 401 after adding a chain | Is the `permitAll` rule inside the selected chain? | Inspect `securityMatcher`, `@Order`, and matchers in `authorizeExchange` |
| Admin/actuator endpoints changed behavior | Did management security auto-config back off? | Define actuator policy explicitly on your chain |
| Both MVC and WebFlux starters present | Is the `ApplicationContext` actually Servlet or reactive? | Pick the stack clearly and use the matching security APIs |
| Unexpected 401/403 | Is it authentication, authorization, or CSRF/another filter? | Test each request, check authorities and filter chain |

**Methodological warning:** an exception name suggests an investigation direction, not the sole proof. Read the full stack trace, bean names, and relevant conditions. Whenever classpath or profiles change, re-run the report because results are computed for the current context.

### 9.3. When Spring Boot Actuator is present

In development environments, you can use Actuator's `conditions` endpoint if supported by your version, exposed, and accessible. It shows whether auto-configuration conditions matched or not. Protect that endpoint with an explicit security policy restricted to authorized environments or accounts; adding the starter does not expose all endpoints by default.

### 9.4. Inspecting the dependency graph

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

For Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
~~~

On Windows replace `./mvnw` and `./gradlew` with `.\mvnw.cmd` and `.\gradlew.bat`. These commands confirm the exact reactive Spring Security, WebFlux, and OAuth2 modules, BOMs, and resolved versions. A `spring-security-oauth2-resource-server` pulled in transitively can alter condition results compared to a project with only the base security starter.

## 10. When to use @Qualifier, @Primary, @Order, or @ConditionalOnMissingBean?

| Tool | What problem does it solve? | When NOT to use it? |
| --- | --- | --- |
| `@Qualifier` | Pick a specific bean at an injection point when multiple beans share a type | Do not use to route HTTP requests to `SecurityWebFilterChain` |
| `@Primary` | Mark the preferred candidate when injecting by type | Does not replace Spring Security chain selection order |
| `@Order` | Order collections/filters/chains per their respective mechanism | Does not resolve duplicate **bean names** |
| `@ConditionalOnMissingBean` | Let an auto-config bean back off when the app supplies a matching bean | Do not treat as a "duplicate-bean patch" for arbitrary manual config |
| `@ConditionalOnProperty` | Toggle a **condition-aware** configuration via an exact property | Do not invent unsupported properties |
| `@Profile` | Register beans only in matching profiles | Does not prevent two configs in the same profile from colliding |
| `@SpringBootApplication(exclude=...)` | Exclude a specific auto-configuration class for a clear reason and scope | Do not use to "turn off all security" when only rules need fixing |
| `@EnableWebFluxSecurity` | Enable Spring Security WebFlux support when needed | Do not add blindly if Boot already sets up infrastructure |

**Design priority:** keep single ownership of core "system" beans; split security chains by clear purpose; create authentication source beans in one controlled place. When upgrading Spring Boot/Security, re-run integration tests and the Conditions Report.

## 11. Scenario exercises

### Scenario A — "I added a custom SecurityWebFilterChain, why does the default user still exist?"

Because `SecurityWebFilterChain` defines **HTTP rules**, not a `ReactiveUserDetailsService` or `ReactiveAuthenticationManager` implementation. Define an appropriate user/authentication source if you want to replace the default login credentials. Check the Conditions Report before drawing conclusions.

### Scenario B — "I added MapReactiveUserDetailsService, why does /public still require login?"

Because a custom user source only changes **authentication data**; the default HTTP policy may still require authentication for every request. Declare a `SecurityWebFilterChain` with `pathMatchers("/public").permitAll()` and an intentional catch-all rule.

### Scenario C — "Are two SecurityWebFilterChain beans an error?"

No. Multiple chains are a normal feature of WebFlux Security. Check `@Order`, `securityMatcher`, and the fallback chain to ensure every necessary route is protected. If two `@Bean` methods have the **same name**, that is a separate bean-definition issue.

### Scenario D — "I added OAuth2 Resource Server and the default password disappeared."

Specialized authentication modules can cause the default-user condition to stop matching. Inspect the classpath, `ReactiveJwtDecoder`, OAuth2 settings, and `ReactiveUserDetailsServiceAutoConfiguration` conditions. Configure the proper authentication mechanism rather than adding random beans to bring back the default user.

### Scenario E — "The app starts, yet /actuator/** lost its old rules."

A custom `SecurityWebFilterChain` can cause management security auto-configuration to back off. Check actuator exposure, `EndpointRequest`, and explicit rules on your chain; write tests for management endpoints instead of testing only app URLs.

### Scenario F — "Is setting allow-bean-definition-overriding=true enough?"

It only permits certain forms of bean-name overriding; it does not guarantee the right security chain or policy, and can mask wrong configuration sources. Fix bean ownership, naming, and actual conditions instead.

## 12. Pre-runtime checklist

1. The project is actually running **Reactive WebFlux**, using `ServerHttpSecurity` and `SecurityWebFilterChain`.
2. An explicit HTTP policy exists, covering public routes, role-restricted routes, and a final rule; with multiple chains, ordering and matchers leave no URLs unprotected.
3. The intended **authentication source** is in place, never relying on Boot's random user/password in production.
4. No unintended duplicate bean names, and no unresolved injection ambiguity.
5. Properties, profiles, and dependencies driving auto-config conditions are verified with the Conditions Report.
6. If Actuator is present, exposure, management port, and per-endpoint authorization are clearly defined.
7. Re-test anonymous, valid user, insufficient-role user, invalid path/method, and any CSRF/OAuth2/JWT flows in use.
8. Never use `{noop}` or hardcoded credentials in real deployments; never enable bean overriding to hide unclear configuration sources.

## 13. Knowledge self-check

**Question 1.** You have a custom `SecurityWebFilterChain` bean without a custom `ReactiveUserDetailsService`. Must the default user disappear?

**Answer:** No. Default user configuration has its own conditions and may still be created if other conditions hold.

**Question 2.** Why is `@Primary` not the way to prioritize a security chain for `/api/**`?

**Answer:** `@Primary` prioritizes a candidate during bean injection, whereas WebFlux Security selects chains per request using `@Order` and `securityMatcher`.

**Question 3.** The Conditions Report says `ReactiveUserDetailsServiceAutoConfiguration` did not match because a matching bean already exists. Is that a startup error?

**Answer:** Not necessarily. It can be intentional back-off behavior. Treat it as a bug only if the custom bean or actual auth behavior fails requirements.

**Question 4.** Why can the same configuration run WebFlux in project A yet have no effect in project B?

**Answer:** Different classpath, web application type, profiles, bean definitions, or conditions; verify the running context.

**Question 5.** After adding a custom chain, actuator endpoints are no longer protected as before—what should you inspect?

**Answer:** Whether actuator security auto-config backed off, chain matchers, `EndpointRequest`, exposure/port, and integration tests.

## 14. Official documentation

- [Spring Boot — Spring Security / WebFlux Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Auto-configuration and Conditions Report](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Creating your own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ReactiveWebSecurityAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/web/reactive/ReactiveWebSecurityAutoConfiguration.html)
- [Spring Boot API — ReactiveUserDetailsServiceAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/ReactiveUserDetailsServiceAutoConfiguration.html)
- [Spring Boot API — ReactiveManagementWebSecurityAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/reactive/ReactiveManagementWebSecurityAutoConfiguration.html)
- [Spring Boot — Actuator Endpoints and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Security — WebFlux Security and Multiple Chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
