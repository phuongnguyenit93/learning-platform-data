# Distinguishing Missing Beans, Bean Conflicts, Circular Dependencies, and Initialization Failures in Spring Boot

## 1. Goal: classify accurately before fixing

A Spring Boot application can stop during startup even when Java code compiles cleanly. Logs often show phrases such as **Error creating bean with name**, **Unsatisfied dependency**, or **APPLICATION FAILED TO START**. Yet those three phrases can stem from completely different root causes. Fixing based on a surface log line without identifying the **underlying error category** often leads to piling on annotations, disabling Spring safeguards, or introducing new errors.

This article focuses on four main categories of **startup failures**:

1. **Missing bean:** Spring needs a dependency, but **there is no matching candidate**.
2. **Bean conflict:** There are **multiple candidates of the same type** for one injection point, or **two definitions share the same bean name**. These two cases must be distinguished.
3. **Circular dependency:** Bean A needs B and B needs A, directly or indirectly; the container cannot construct the required graph.
4. **Initialization failure:** Spring found the bean definition and is constructing it, but its constructor, @Bean factory method, @PostConstruct, init method, or related configuration **throws an error**.

Each category has different messages, exceptions, and fixes. This guide uses Spring Boot **3.3.x**, Spring Framework **6.1.x**, and Java **17+** for version consistency.

## 2. Which stages does a bean pass through?

A bean does not merely have two states: "exists" and "does not exist". Picture a pipeline:

~~~text
Read configuration / component scan / auto-configuration
                       |
            Register BeanDefinition
                       |
            Resolve dependencies
                       |
        Call constructor / factory method
                       |
        Dependency injection / binding
                       |
      BeanPostProcessor / @PostConstruct
                       |
             Init method succeeds
                       |
         Bean ready for the context
                       |
  Context refresh completes -> Started -> Runners -> Ready
~~~

The order above is **simplified**; depending on the bean, post-processors, proxies, factories, scopes, and auto-configuration, specific steps vary.

Failures typically correspond to these stages:

| Stage | Example issue | Diagnostic category |
| --- | --- | --- |
| Definition registration | Two beans with the same name, overriding disallowed | Bean definition conflict |
| Dependency resolution | No bean of type NotificationGateway | Missing bean |
| Dependency resolution | Two matching NotificationGateways | Ambiguity from multiple beans of same type |
| Dependency resolution / instantiation | A needs B, B needs A | Circular dependency |
| Constructor / @Bean method | Throws IllegalArgumentException | Instantiation failure |
| @PostConstruct / init method | Throws IllegalStateException | Initialization failure |
| Configuration binding | Wrong data type / validation | Configuration and initialization failure |
| Post-refresh runner | ApplicationRunner throws error | Startup failure, not necessarily a bean error |

**ApplicationStartedEvent** is published only after context refresh succeeds. **ApplicationReadyEvent** comes after runners. When a required bean cannot be created during refresh, the application **does not reach Ready along the success path**; Spring Boot may publish **ApplicationFailedEvent**. However, runner failures can happen **after all beans have been created**, so do not classify every startup failure as a bean error.

## 3. Quick identification matrix by exception and log

| Scenario | Common signals | Actual problem | Primary fix direction |
| --- | --- | --- | --- |
| No matching bean | NoSuchBeanDefinitionException; UnsatisfiedDependencyException | 0 candidates | Register bean, fix scan/profile/condition/type |
| Multiple beans of same type | NoUniqueBeanDefinitionException; expected single matching bean but found 2 | Multiple candidates, cannot pick one | @Qualifier, @Primary, collection, or split interface design |
| Two beans with same name | BeanDefinitionOverrideException; bean name already defined | Duplicate bean name in registry | Rename, remove duplicate config; do not blindly enable override |
| Bean A needs B needs A | BeanCurrentlyInCreationException; requested bean currently in creation; dependency cycle | Cycle in graph | Redesign dependencies, extract shared responsibility or add mediator |
| Constructor / factory error | BeanCreationException, BeanInstantiationException, specific root cause | Bean construction code throws exception | Fix constructor/factory, inputs, and resources |
| @PostConstruct/init error | BeanCreationException, invocation of init method failed | Init callback throws exception | Fix data, timeout, validation, cleanup |
| Config binding error | ConfigurationPropertiesBindException, bind/validation cause | Wrong or missing property | Fix configuration, data type, and constraints |

**Note:** BeanCreationException and UnsatisfiedDependencyException are often **wrappers**. They report that creating a bean failed without necessarily stating the final cause directly. Inspect the entire **Caused by** chain and the original bean/dependency. **NoUniqueBeanDefinitionException** means one bean could not be chosen among existing beans—it does **not** mean "no bean exists".

## 4. Category 1 — Missing bean (missing dependency)

### 4.1. Signals

A constructor or @Bean factory requires:

~~~java
@Service
class AlertService {
    AlertService(NotificationGateway gateway) {
        // ...
    }
}
~~~

This is an **illustrative snippet** requiring a NotificationGateway declaration and @Service import. If no bean matches NotificationGateway, Spring cannot instantiate AlertService.

Logs usually state something like:

~~~text
Parameter 0 of constructor in ...AlertService
required a bean of type ...NotificationGateway
that could not be found.
~~~

Depending on the injection site and version, the exception chain may contain **UnsatisfiedDependencyException** wrapping **NoSuchBeanDefinitionException**. Do not assume that seeing UnsatisfiedDependencyException means you must add @Component to the class named in the outer line; the missing dependency may sit several layers deeper.

### 4.2. Why does Java have the class while Spring reports a missing bean?

**A class existing on the classpath does not mean a bean is registered.** Common reasons:

1. The class lacks @Component/@Service/@Repository, or has not been declared via @Bean.
2. The class is **outside component scan scope**. `@SpringBootApplication` by default scans the main class's package and its subpackages; sibling packages may not be scanned.
3. `@Profile` differs from the active profile. For instance, the bean exists only under `prod` while running locally with `dev`.
4. `@ConditionalOnProperty`, `@ConditionalOnClass`, or auto-configuration conditions are not satisfied.
5. A missing starter/module prevents auto-configuration from creating the expected bean.
6. Interface T is required, but `@Bean` declares a different type, qualifiers do not match, or the bean lives in another ApplicationContext.
7. Annotations were placed on an object created manually with `new` rather than a container-managed instance.
8. Bean scope/proxy or generic type parameters do not match the injection point.
9. Wrong `@Qualifier` name leaves **zero candidates in the filtered set**, even though beans of that interface exist.

### 4.3. Proper fixes

When the dependency is mandatory, register it through an appropriate mechanism:

~~~java
@Service
class SmtpNotificationGateway implements NotificationGateway {
    // ... implement contract ...
}
~~~

Or:

~~~java
@Configuration
class GatewayConfiguration {
    @Bean
    NotificationGateway gateway() {
        return new SmtpNotificationGateway();
    }
}
~~~

These two illustrative snippets are **not standalone projects**: they require the interface, implementation, and imports. Choose **one** appropriate registration mechanism to avoid accidentally creating two beans for the same role when unnecessary.

If the dependency is **genuinely optional**, you can use `Optional<NotificationGateway>`, `ObjectProvider<NotificationGateway>`, or configuration conditions to select a clear branch. However, **do not turn a mandatory dependency into Optional just to hide a startup failure**; the service might appear ready yet break on real requests.

### 4.4. Checklist when seeing NoSuchBeanDefinitionException

- Verify the **exact type**, generic parameters, qualifier, and injection site.
- Verify the main `@SpringBootApplication` class is in the proper root package.
- Check whether the bean is created by `@Component`, `@Bean`, or auto-configuration.
- Check the active profile: `spring.profiles.active`.
- Check `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` conditions.
- Verify the right module/starter is on the runtime classpath.
- Verify the configuration is not excluded from `@Import`/`@ComponentScan` or auto-config.
- If multiple contexts exist, determine which context holds the bean and the parent-child relationship.

## 5. Category 2 — Bean conflicts have two distinct forms

### 5.1. Multiple beans of the same type, ambiguous injection

Suppose we have:

~~~java
@Bean
NotificationGateway emailGateway() {
    return new EmailGateway();
}

@Bean
NotificationGateway smsGateway() {
    return new SmsGateway();
}
~~~

This is illustrative code requiring EmailGateway/SmsGateway classes. When a constructor only asks for:

~~~java
AlertService(NotificationGateway gateway) {
    // ...
}
~~~

Spring has **two candidates of the same type**, with no selection signal. The error typically includes **NoUniqueBeanDefinitionException**, or FailureAnalyzer prints:

~~~text
required a single bean, but 2 were found:
  - emailGateway
  - smsGateway
~~~

**This is not a duplicate bean name error.** Both beans have distinct names and exist validly; the problem is solely that **the injection point requires a single instance**.

Ways to fix:

**@Primary**: mark one implementation as default:

~~~java
@Bean
@Primary
NotificationGateway emailGateway() {
    return new EmailGateway();
}
~~~

When an injection point requests a NotificationGateway without a qualifier, Spring normally picks the single primary bean unless another precedence condition applies.

**@Qualifier**: specify the desired bean at the injection site:

~~~java
AlertService(@Qualifier("smsGateway") NotificationGateway gateway) {
    // ...
}
~~~

**Collection injection**: if all implementations are intentionally needed, inject `List<NotificationGateway>` or `Map<String, NotificationGateway>` instead of picking one.

**Clearer interface design**: if email and SMS represent distinct business roles, split the contract or inject a router selecting by channel rather than overusing `@Primary`.

**Do not rely on constructor parameter names** as the primary fix: Spring can match by bean name when parameter name metadata is retained; with Spring Framework 6.1 the compiler **-parameters** flag is required for parameter-name matching. `@Qualifier` is an explicit contract and resilient to variable renames.

### 5.2. Two bean definitions with the same name (bean name collision)

A completely different failure:

~~~java
@Configuration
class ConfigA {
    @Bean("sharedGateway")
    NotificationGateway first() {
        return new EmailGateway();
    }
}

@Configuration
class ConfigB {
    @Bean("sharedGateway")
    NotificationGateway second() {
        return new SmsGateway();
    }
}
~~~

This is an illustrative snippet with undefined types. Both methods assign the same bean name **sharedGateway** in the registry. By default, Spring Boot 3.3 **disallows bean definition overriding**. Therefore, when attempting to register the second definition, **BeanDefinitionOverrideException** can occur.

A typical error message conveys:

~~~text
The bean 'sharedGateway' could not be registered.
A bean with that name has already been defined
and overriding is disabled.
~~~

Proper fix: rename the bean, remove the duplicate `@Configuration`, exclude one config via `@Profile`/`@Conditional`, or fix module imports/component scan so each definition has a clear owner.

There is a property:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

**Do not treat this property as a default fix.** When enabled, one bean definition can silently replace another depending on registration order, hiding configuration that ought to be explicit. This is especially dangerous during module upgrades or classpath changes.

Some component scan conflicts may surface as **ConflictingBeanDefinitionException** instead of BeanDefinitionOverrideException depending on the registration path. Use the original error message to distinguish them.

### 5.3. Quick comparison

| Characteristic | NoUniqueBeanDefinitionException | BeanDefinitionOverrideException |
| --- | --- | --- |
| Number of bean names | Two or more distinct names | Same name defined more than once |
| When failure occurs | Resolving an injection requiring a single bean | Registering a BeanDefinition |
| Does @Qualifier help directly? | Yes, by selecting the right candidate | Does not fix duplicate definition names |
| Does @Primary help directly? | Yes, if only one primary matches | Does not fix duplicate definition names |
| Rename/remove duplicate config | Can reduce ambiguity | Primary fix |
| Enable overriding | Not a solution | Use only when intentionally designing overriding |

## 6. Category 3 — Circular dependency

Suppose A depends on B via constructor, while B depends on A:

~~~text
OrderService -> PaymentService
       ^               |
       +---------------+
~~~

The graph has no starting point to construct either instance normally. Spring throws **BeanCurrentlyInCreationException**, sometimes wrapped in **UnsatisfiedDependencyException** or BeanCreationException.

Structural example:

~~~java
class OrderService {
    OrderService(PaymentService payment) {
        // ...
    }
}

class PaymentService {
    PaymentService(OrderService order) {
        // ...
    }
}
~~~

This is an illustrative Java snippet without bean annotations. With pure constructor injection, each needs the other instance **before its own constructor finishes**.

### Spring Boot 3.3 default

~~~properties
spring.main.allow-circular-references=false
~~~

Spring Boot 3.3 defaults to **false**. Setting it to `true` lets Spring attempt to resolve **some** cycles using property/setter injection, but it **cannot resolve pure constructor injection cycles**. Spring Boot recommends fixing the dependency structure rather than turning this `true`.

### Architectural fixes

**Extract shared logic into a third bean:**

~~~text
Before:
OrderService -> PaymentService -> OrderService

After:
OrderService -> PaymentService
OrderService -> OrderPolicy
PaymentService -> OrderPolicy
~~~

**Invert dependency direction** via an interface or events: one service publishes a business event and the other listens at a designed boundary, avoiding mutual constructor references.

**Move orchestration** into a coordinator: instead of OrderService calling PaymentService and PaymentService calling back into OrderService, create CheckoutCoordinator depending on both while the two services stay independent.

**@Lazy** on one edge of the dependency can defer resolution behind a proxy, occasionally breaking initialization cycles. However, it **does not eliminate the logical cycle**, can defer failures to runtime, and can cause unpredictable behavior. Treat it as a conditional workaround, not a primary refactoring.

**Do not confuse with @DependsOn**: `@DependsOn` expresses before/after initialization ordering; it does not turn a cyclic dependency graph into an acyclic one. `@Order` controls ordering in other contexts and cannot cure constructor cycles.

## 7. Category 4 — Failures during bean creation and initialization

Spring may already know the definition and locate every dependency, yet the bean itself **throws an exception while being built**.

Error sources:

1. **Constructor** throws IllegalArgumentException, IllegalStateException, or NullPointerException.
2. **@Bean factory method** calls an external resource or validates config and throws an exception.
3. **@PostConstruct** throws an exception during init.
4. **@Bean(initMethod="...")** throws an exception.
5. **InitializingBean.afterPropertiesSet()** throws an exception.
6. **@ConfigurationProperties binding** fails due to invalid data types or validation.
7. **BeanPostProcessor / proxy creation** fails.
8. **Resources** such as files, keys, certificates, sockets, or databases are inaccessible during init.

Typically you see **BeanCreationException**, possibly wrapping **BeanInstantiationException** or the underlying business exception. Saying "Error creating bean with name 'fragileClient'" is not enough to know whether to add `@Component` or tweak `@Qualifier`: you must read **Caused by**.

### @PostConstruct example

~~~java
@Component
class ConfigurationVerifier {
    @PostConstruct
    void initialize() {
        if (System.getenv("API_TOKEN") == null) {
            throw new IllegalStateException("API_TOKEN is missing");
        }
    }
}
~~~

This is an **illustrative snippet** requiring imports for Component and **jakarta.annotation.PostConstruct** in Spring Boot 3.x. If the environment variable is missing, the bean definition already exists; the error is not NoSuchBeanDefinitionException, but an **exception from the init callback**.

### Should connection failures during init fail startup?

Base the decision on the business contract:

- If no useful requests can be served without the dependency, **fail fast** or keep readiness refusing traffic under an explicit policy.
- If a safe degraded mode exists, avoid remote connections in constructors/`@PostConstruct`; instead initialize quickly with separate timeouts/health checks.
- Never run unbounded network operations inside bean init, because context refresh can hang.
- If an init method already opened a socket/file before throwing, clean up partially created resources; do not assume `@PreDestroy` always runs for a bean that never finished initializing.

### Confusing this with configuration errors

~~~properties
client.connect-timeout=abc
~~~

When binding to a Duration/Integer property requiring valid syntax, a **binding/conversion** failure can appear before the service runs. That is a configuration error, not automatically a missing bean. Inspect the binding path, property source precedence, active profiles, and validation message.

## 8. A runnable project reproducing all four failure categories

This example uses **Spring Boot 3.3.13 + Java 17+ + Gradle** in non-web mode so startup is easy to observe. Each failure lives in an **independent Spring profile**; run one profile at a time so exceptions do not mix.

Profiles:

- **healthy**: no error; uses `@Primary` and `@Qualifier` properly.
- **missing**: requires NotificationGateway with no candidate.
- **ambiguous**: two NotificationGateways, cannot choose one.
- **collision**: two `@Bean`s named `sharedGateway`.
- **cycle**: constructor dependency cycle between Alpha and Beta.
- **initfail**: FragileClient's init method intentionally throws IllegalStateException.

### 8.1. Project structure

~~~text
startup-failure-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          StartupFailureLab.java
          ScenarioConfigs.java
      resources/
        application.properties
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'startup-failure-lab'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

File **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
~~~

Do not enable bean overriding or circular references; let Spring Boot keep both safe defaults.

### 8.2. Main class and shared types

File **src/main/java/demo/StartupFailureLab.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupFailureLab {

    public static void main(String[] args) {
        SpringApplication.run(StartupFailureLab.class, args);
    }

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyObserver() {
        return event -> System.out.println("APPLICATION_READY");
    }
}

interface NotificationGateway {
    String channel();
}

record DemoGateway(String channel) implements NotificationGateway { }

record Alpha(Beta beta) { }

record Beta(Alpha alpha) { }

class FragileClient {
    public void initialize() {
        throw new IllegalStateException("Simulated init failure");
    }
}
~~~

**Java syntax:** this is a single file with one public class matching the filename; the remaining interface, records, and class are package-private in the same `demo` package. Records are supported on Java 17.

### 8.3. Separate profile configurations

File **src/main/java/demo/ScenarioConfigs.java**:

~~~java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("healthy")
class HealthyConfig {

    @Bean("emailGateway")
    @Primary
    NotificationGateway emailGateway() {
        return new DemoGateway("email");
    }

    @Bean("smsGateway")
    NotificationGateway smsGateway() {
        return new DemoGateway("sms");
    }

    @Bean
    ApplicationRunner healthyRunner(
            NotificationGateway defaultGateway,
            @Qualifier("smsGateway") NotificationGateway selectedGateway) {
        return args -> {
            System.out.println("HEALTHY_PRIMARY=" + defaultGateway.channel());
            System.out.println("HEALTHY_QUALIFIED=" + selectedGateway.channel());
        };
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("missing")
class MissingConfig {
    @Bean
    ApplicationRunner missingRunner(NotificationGateway gateway) {
        return args -> System.out.println(gateway.channel());
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("ambiguous")
class AmbiguousConfig {

    @Bean
    NotificationGateway emailGateway() {
        return new DemoGateway("email");
    }

    @Bean
    NotificationGateway smsGateway() {
        return new DemoGateway("sms");
    }

    @Bean
    ApplicationRunner ambiguousRunner(NotificationGateway gateway) {
        return args -> System.out.println(gateway.channel());
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("collision")
class CollisionConfigA {
    @Bean("sharedGateway")
    NotificationGateway firstDefinition() {
        return new DemoGateway("first");
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("collision")
class CollisionConfigB {
    @Bean("sharedGateway")
    NotificationGateway secondDefinition() {
        return new DemoGateway("second");
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("cycle")
class CircularConfig {

    @Bean
    Alpha alpha(Beta beta) {
        return new Alpha(beta);
    }

    @Bean
    Beta beta(Alpha alpha) {
        return new Beta(alpha);
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("initfail")
class InitFailureConfig {

    @Bean(initMethod = "initialize")
    FragileClient fragileClient() {
        return new FragileClient();
    }
}
~~~

**Why the example does not trigger all failures at once:**

- Every scenario `@Configuration` class is component-scanned from package `demo`.
- Each scenario is guarded by `@Profile`; run **only one profile per attempt**.
- The `@Bean` methods for missing/ambiguous cases accept dependencies as parameters; Spring must resolve them during context refresh.
- The two collision configs intentionally register the **same name** `sharedGateway` to trigger a bean-definition overriding failure.
- The constructor cycle through `@Bean` parameters builds a graph where Alpha needs Beta and Beta needs Alpha.
- `FragileClient` has a public init method that intentionally throws an exception to reproduce initialization failure even with zero missing dependencies.
- The `healthy` profile includes both `@Primary` and `@Qualifier` to demonstrate two distinct bean selection mechanisms.

**Why the healthy profile code is reliable:** parameter `defaultGateway` does not match bean names `emailGateway` or `smsGateway`, yet `emailGateway` is marked `@Primary`; parameter `selectedGateway` carries `@Qualifier("smsGateway")`, so it selects `sms`.

## 9. Running each profile and reading the results

If Gradle wrapper is available:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=healthy"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=healthy"
~~~

If you have not generated a wrapper yet but have a compatible Gradle installed:

~~~bash
gradle bootRun --args="--spring.profiles.active=healthy"
~~~

With **healthy**, the lines printed by our code in order are:

~~~text
HEALTHY_PRIMARY=email
HEALTHY_QUALIFIED=sms
APPLICATION_READY
~~~

Spring Boot and Gradle logs may interleave. Although a non-web app exits naturally after startup when no non-daemon threads remain, `ApplicationReadyEvent` fired on the success branch.

### 9.1. Missing bean

~~~bash
./gradlew bootRun --args="--spring.profiles.active=missing"
~~~

Expected: a FailureAnalyzer or stack trace showing **the NotificationGateway parameter of missingRunner has no matching bean**. The cause chain may include **NoSuchBeanDefinitionException/UnsatisfiedDependencyException**. No `APPLICATION_READY` line appears from `readyObserver`, because the context did not finish starting.

### 9.2. Ambiguous due to multiple beans of the same type

~~~bash
./gradlew bootRun --args="--spring.profiles.active=ambiguous"
~~~

Expected: **two candidates emailGateway and smsGateway** for the NotificationGateway parameter of `ambiguousRunner`. With no matching `@Primary`/`@Qualifier`, **NoUniqueBeanDefinitionException** or an equivalent message appears. `APPLICATION_READY` does not appear along the success path.

### 9.3. Bean definition name collision

~~~bash
./gradlew bootRun --args="--spring.profiles.active=collision"
~~~

Expected: **BeanDefinitionOverrideException** because both `@Bean` methods in `CollisionConfigA`/`CollisionConfigB` use the name **sharedGateway** and overriding is disabled by default. This fails during definition registration, not because a constructor parameter lacks a candidate.

### 9.4. Circular dependency

~~~bash
./gradlew bootRun --args="--spring.profiles.active=cycle"
~~~

Expected: a message or graph showing **alpha -> beta -> alpha** with **BeanCurrentlyInCreationException** or a BeanCreationException/UnsatisfiedDependencyException chain. Do not enable `allow-circular-references` to solve this, because a pure constructor cycle has no completed instance to reuse.

### 9.5. Init method failure

~~~bash
./gradlew bootRun --args="--spring.profiles.active=initfail"
~~~

Expected: **BeanCreationException** referencing `fragileClient`, and root cause **IllegalStateException: Simulated init failure**. This is a genuine initialization failure—neither a missing bean nor two beans sharing a name.

**Do not assert the entire verbatim stack trace**: line numbers, proxy classes, FailureAnalyzer output, and wording vary across Spring Boot/Framework/Gradle versions. In tests, assert **the cause type, involved bean, candidate names, and that Ready does not fire** rather than comparing full logs.

## 10. Fixing each scenario in the project

### Missing bean: register an implementation in the right profile

You can add a `@Bean` returning `NotificationGateway` to `MissingConfig`:

~~~java
@Bean
NotificationGateway gateway() {
    return new DemoGateway("email");
}
~~~

This is a **replacement/addition inside MissingConfig**, not a separate Java class. Once a NotificationGateway exists, `missingRunner` can resolve its dependency.

### Ambiguous: choose via @Qualifier or @Primary

Replace `ambiguousRunner`:

~~~java
@Bean
ApplicationRunner ambiguousRunner(
        @Qualifier("emailGateway") NotificationGateway gateway) {
    return args -> System.out.println(gateway.channel());
}
~~~

This method replaces the existing method in `AmbiguousConfig` rather than registering two methods with the same name simultaneously. Alternatively, add `@Primary` to **one** implementation, not both.

### Name collision: give distinct names or remove redundant configuration

Change `secondDefinition` to:

~~~java
@Bean("alternateGateway")
NotificationGateway secondDefinition() {
    return new DemoGateway("second");
}
~~~

Once the two beans have different names, `BeanDefinitionOverrideException` is eliminated. If an injection point then requests a `NotificationGateway` without a qualifier, a new **NoUniqueBeanDefinitionException** can arise; resolve the next scenario properly rather than assuming renaming solves everything.

### Circular dependency: fix the graph

Instead of Alpha needing Beta and Beta needing Alpha, move shared responsibility into a third component, or let a coordinator depend on both while the two services do not depend on each other. Conceptual model:

~~~text
Before: A -> B -> A

After:  Coordinator -> A
                  -> B
        A -> SharedPolicy
        B -> SharedPolicy
~~~

This is an architectural diagram, not Java source.

### Init failure: fix the initialization condition

If init needs an environment variable, validate the property and provide a message naming the missing key; if it needs a remote API, use bounded timeouts/retries and clean up partially opened resources. In the demo, `initialize()` deliberately always throws, so replacing it with valid initialization code is the real fix; adding `@Qualifier` has zero effect.

## 11. Step-by-step startup debugging workflow

### Step 1: Identify which stage the failure started in

- **Definition registration**: BeanDefinitionOverrideException or ConflictingBeanDefinitionException.
- **Dependency resolution**: NoSuchBeanDefinitionException, NoUniqueBeanDefinitionException.
- **Bean construction/init**: BeanCreationException with constructor/@PostConstruct/binding root cause.
- **Lifecycle/runner**: SmartLifecycle.start or ApplicationRunner; not always a bean error.
- **Web startup**: port in use, invalid certificate, misconfigured datasource; inspect the specific root cause.

### Step 2: Locate the exact bean or injection point

Read the logs to identify:

- Which bean name is being created?
- Which class or factory method requested the dependency?
- What is the exact required type, generic signature, or qualifier?
- How many candidates exist and what are their names?
- Which beans form the cycle graph?
- Which init method actually threw the exception?

A line saying "Error creating bean with name 'orderService'" may only be **the first affected bean**. Subsequent causes point to the real failure in `paymentGateway` or `remoteClient`.

### Step 3: Read the entire Caused by chain

Example:

~~~text
UnsatisfiedDependencyException: Error creating orderService
Caused by: BeanCreationException: Error creating pricingClient
Caused by: IllegalArgumentException: Invalid region code
~~~

Do not patch `orderService` with random annotations when the root cause is an invalid **region code** while creating `pricingClient`.

### Step 4: Use FailureAnalyzer and the conditions report

Spring Boot includes many **FailureAnalyzer**s to print specific **Description** and **Action** sections. If it is unclear why an auto-configured bean is present or absent, try:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=missing --debug"
~~~

Or with an executable JAR:

~~~bash
java -jar build/libs/startup-failure-lab-1.0.0.jar --spring.profiles.active=missing --debug
~~~

The **--debug** flag in Spring Boot enables the conditions evaluation report and helpful diagnostic logging; it does not attach a JVM debugger. Use enough logging to see which conditions **matched** or **did not match**, especially `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean`. Never ship logs containing full secrets to untrusted systems.

### Step 5: Fix one root cause at a time

For instance, fixing a missing bean by registering two implementations may transition the error to `NoUniqueBeanDefinitionException`; that does not mean the prior step was "completely wrong", only that injection still is not uniquely defined. Repeat diagnosis on the **current error** instead of flipping multiple flags at once.

### Step 6: Verify startup and real runtime behavior

Do not merely check that stack traces disappeared from logs. Verify:

- Did `ApplicationReadyEvent` fire after runners finished?
- Was the intended bean implementation injected?
- Do the profile and configuration match the target environment?
- Does the endpoint or job using the dependency actually work?
- Did the fix unexpectedly alter bean ordering or definitions?
- If solved with `@Lazy` or optional injection, was the error merely deferred until the first request?

## 12. Commonly misclassified cases

### 12.1. Missing bean caused by @Profile

~~~java
@Profile("prod")
@Service
class RealGateway implements NotificationGateway {
    // ...
}
~~~

When running with the `dev` profile, the type exists on the classpath, yet **the bean is not registered**. This is still a missing bean, not a constructor bug in `RealGateway`.

### 12.2. Multiple beans from declaring a duplicate alongside auto-configuration

You declare a custom bean of type T while auto-configuration also provides a bean of type T. Possible outcomes:

- Auto-config uses `@ConditionalOnMissingBean` and **backs off**, with no error.
- Auto-config does not back off, the two beans have **different names**, and injecting T becomes ambiguous.
- Both beans share the **same name**, causing a definition overriding failure.

Always check the actual types, names, conditions, and registration order; do not assume "having two beans" always produces `BeanDefinitionOverrideException`.

### 12.3. Wrong @Qualifier can look like a missing bean

EmailGateway and SmsGateway both exist, yet injection uses `@Qualifier("pushGateway")`. Spring finds no matching candidate in the filtered set and reports no qualifying bean found. Do not add a random new implementation; fix the semantic qualifier.

### 12.4. Null inside constructor vs @PostConstruct failure

If a constructor receives its dependencies and then throws `NullPointerException` due to internal logic, that is a **bean instantiation** error, not a missing bean. If `@PostConstruct` calls a remote API and times out, that is an init/remote dependency error, not a cycle.

### 12.5. Constructor cycle vs runtime call cycle

A constructor-depending on B and B constructor-depending on A is a **bean creation cycle**. By contrast, `A.method` calling `B.method` which infinitely calls back into `A.method` is **runtime recursion**, which can trigger `StackOverflowError` after the context is ready even though bean creation has no cycle.

### 12.6. @Lazy can hide errors until runtime

Enabling:

~~~properties
spring.main.lazy-initialization=true
~~~

causes many beans to be created only on demand. Startup succeeding does not prove lazy dependencies are valid. Test real endpoints/jobs and enforce fail-fast policies for critical components. Do not use `lazy-initialization` to avoid fixing broken wiring.

### 12.7. Different classloaders or multiple ApplicationContexts

A bean registered in a child context is not automatically visible from the parent in every direction; class T in a different classloader may not be treated as the same type even with an identical fully qualified name. This is an advanced scenario; do not try to fix it with global component scanning or by blindly enabling overriding.

## 13. Which fix should take priority?

| Root cause | Priority 1 | Avoid doing right away |
| --- | --- | --- |
| No bean | Verify scan/profile/conditions, register a single implementation | Adding `@Autowired(required=false)` to mask the failure |
| Multiple beans of same type | Semantically clear `@Qualifier` or `@Primary` | Enabling bean overriding |
| Two beans with same name | Rename or remove duplicate config, design clear ownership | `allow-bean-definition-overriding=true` to silence the error |
| Circular dependency | Refactor dependency direction, mediator/shared service | `allow-circular-references=true` as a permanent fix |
| Constructor/init throws exception | Fix root cause, inputs, config, timeouts, and cleanup | Adding `@Primary`/`@Qualifier` or randomly renaming beans |
| Config binding fails | Fix keys/types/validation and profiles | Swallowing `BindException` |
| Runner fails | Fix startup task conditions and propagate errors properly | Stripping out all startup validation |

**When multiple implementations are intentionally needed**, define the selection mechanism explicitly. **For plugin architectures**, inject a collection or name-keyed `Map` and select in a router layer. **When two services depend cyclically**, it usually reflects unseparated responsibilities; fixing the dependency graph beats adding annotations.

## 14. Testing and QA strategy

1. **Missing:** enable profile `missing`; logs clearly state `NotificationGateway` has no bean. After adding an implementation, it starts cleanly.
2. **Ambiguous:** enable profile `ambiguous`; exactly two candidates exist. Add `@Qualifier` or one `@Primary` and verify the right implementation is injected.
3. **Collision:** enable profile `collision`; duplicate name `sharedGateway` is blocked. Rename or remove the duplicate definition, then still verify injection by type.
4. **Cycle:** enable profile `cycle`; inspect the alpha/beta graph and do not try to "fix" constructor cycles with `allow-circular-references`.
5. **Init failure:** enable profile `initfail`; root cause is `IllegalStateException` with message `Simulated init failure`; verify resource cleanup if there were side effects.
6. **Healthy:** enable profile `healthy`; observe both `PRIMARY`/`QUALIFIED` lines and `APPLICATION_READY`.
7. **Runtime/test:** for production code, add `ApplicationContextRunner` or `@SpringBootTest` tests per profile. For negative tests, use AssertJ to assert context failure and root cause rather than matching entire logs verbatim.
8. **Build/package:** run with the same Java version and profile as deployment; review dependencies on the runtime classpath, not only compile classpath.
9. **Config drift:** inspect `application.properties`, environment variables, command-line args, and Kubernetes ConfigMaps, including secret injection.
10. **Failure handling:** verify the application does not falsely publish Ready or open listeners to accept work while critical dependencies are unready.

### Testing failures with ApplicationContextRunner

The Spring Boot test module provides **ApplicationContextRunner** to build a small context from a chosen set of configurations/auto-configurations. It is ideal for testing bean presence or absence conditions without starting a full web server.

Illustrative example:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(MissingConfig.class)
        .run(context -> {
            // Check context.getStartupFailure()
            // and expected root cause/bean type.
        });
~~~

This is an **illustrative snippet, not a standalone runnable test**; it requires `spring-boot-test`, AssertJ, imports, runner setup, and concrete assertions. Tests should verify intended behavior rather than merely checking "some exception was thrown".

## 15. Common wrong fixes

**"Seeing UnsatisfiedDependencyException means add @Component to every class."** Wrong. The dependency may genuinely be missing or excluded by profile/conditional/qualifier; adding annotations blindly can create duplicates.

**"Two beans of the same type means duplicate bean names."** Wrong. Duplicate type causes ambiguity during injection resolution; duplicate name causes definition registration failure.

**"@Primary fixes BeanDefinitionOverrideException."** Wrong. `@Primary` only helps select a candidate when autowiring by type; it does not allow two definitions with the same name to register.

**"@Qualifier fixes any missing dependency."** Wrong. If no bean of that type exists, a qualifier cannot conjure one.

**"spring.main.allow-bean-definition-overriding=true fixes all conflicts."** Wrong. It can silently shadow one definition and make configuration order-dependent.

**"spring.main.allow-circular-references=true always fixes cycles."** Wrong. Constructor cycles generally cannot be resolved this way, and it is not a recommended design.

**"@DependsOn breaks constructor cycles."** Wrong. It only adds initialization ordering/dependencies without removing the cycle.

**"@Order controls how Spring injects every bean."** Wrong. `@Order` is not equivalent to `@Qualifier` or `@Primary`.

**"Spring Boot automatically creates a bean for every interface on the classpath."** Wrong. There must be a matching component, configuration, or satisfied auto-configuration.

**"A class with @Service in any package is guaranteed to be scanned."** Wrong. Default scan scope is anchored at the `@SpringBootApplication` class's package.

**"BeanCreationException is always the root cause."** Wrong. It is usually a wrapper around a specific factory, init, or binding exception.

**"Getting the application to start is enough."** Not if the error was hidden behind lazy/optional wiring or the wrong implementation was injected.

## 16. Self-check questions

**Q1:** A constructor needs `PaymentGateway` and no bean of this type exists. Which category?  
**Answer:** Missing bean, typically `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException`.

**Q2:** Two `PaymentGateway` beans named `cardGateway` and `bankGateway` exist with no `@Primary`, and injection asks for one `PaymentGateway`. Error?  
**Answer:** Multiple candidates of the same type; `NoUniqueBeanDefinitionException`.

**Q3:** Two `@Bean` methods share the name `paymentGateway`. Default error in Boot 3.3?  
**Answer:** Likely `BeanDefinitionOverrideException` because overriding defaults to false.

**Q4:** Does `@Primary` fix two `@Bean`s with the same name?  
**Answer:** No. You must fix the bean names or configuration ownership.

**Q5:** A's constructor needs B, and B's constructor needs A. Error?  
**Answer:** Constructor cycle; typically `BeanCurrentlyInCreationException`.

**Q6:** Does enabling `allow-circular-references=true` guarantee breaking a constructor cycle?  
**Answer:** No.

**Q7:** A bean's `@PostConstruct` throws `IllegalStateException`. Is this a missing bean?  
**Answer:** No; the bean was found, but initialization failed.

**Q8:** `@Profile("prod")` is on a `@Service` class while only `dev` is active. Will it be registered?  
**Answer:** Not under that profile; this can lead to a missing bean error.

**Q9:** Why read `Caused by` instead of only the `Error creating bean` line?  
**Answer:** The reported bean may only be the victim; the root cause lies in a deeper dependency or init method.

**Q10:** Does renaming two colliding beans always prevent `NoUniqueBeanDefinitionException`?  
**Answer:** No; once two beans have distinct names of the same type, injection can become ambiguous.

**Q11:** Does `@Lazy` fix broken dependency wiring?  
**Answer:** No; it may simply defer the exception until first use.

**Q12:** Is `ApplicationReadyEvent` published if a required bean fails during context refresh?  
**Answer:** No on the successful startup path.

**Q13:** Changing `@Qualifier("emailGateway")` to `@Qualifier("pushGateway")` when no `pushGateway` exists causes what?  
**Answer:** Zero candidates match the qualifier, likely reporting no qualifying bean found.

**Q14:** What approach should you choose when two services call each other because they hold too many responsibilities?  
**Answer:** Refactor—introduce a coordinator/mediator, split services or interfaces, and separate shared data properly.

## 17. Checklist before concluding a fix is complete

- Identify the exact **stage**: definition, dependency resolution, instantiation, initialization, runner, or runtime.
- Identify the exact **bean name, required type, qualifier, generics, and profile**.
- Distinguish **0 candidates**, **multiple candidates with different names**, and **duplicate definition names**.
- If there is a cycle, draw the full dependency graph and **break an edge** via refactoring.
- If there is an init failure, find the original exception and remove its cause instead of hiding it.
- Verify Boot 3.3 defaults: **bean overriding=false**, **circular references=false**.
- For auto-configuration, read the conditions report and active properties.
- Ensure the fix does not create duplicate beans or swap in an untested implementation.
- Run tests under a runtime/profile matching production.
- After startup succeeds, verify runners/Ready and actual functionality.
- On failure and retry, ensure partially opened resources are cleaned up without uncontrolled duplicate side effects.

**Conclusion:** "Error creating bean" is a shared symptom of multiple causes. **Missing bean** means zero candidates; **type conflict** means multiple candidates with no selection rule; **name collision** means two definitions claim the same name; **circular dependency** means the creation graph loops back on itself; **initialization failure** means factory/constructor/init code threw an error. A lasting fix targets the **root cause, failure stage, and dependency contract**, not just silencing the startup warning.

### References

- [Spring Boot 3.3.13 — SpringApplication API: Allow Bean Definition Overriding and Circular References](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot — SpringApplication: Startup Failure, Events and Conditions Report](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework — Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — @Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Circular Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Lifecycle and Bean Initialization](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
