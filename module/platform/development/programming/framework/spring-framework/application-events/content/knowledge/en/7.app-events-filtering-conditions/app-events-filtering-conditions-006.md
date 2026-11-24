# Dynamic Environment-Based Conditions in Spring Application Events

## 1. The Problem and Mental Model

An application emits an `OrderPlaced` event whenever an order is created. An auditing processor only needs to run when the configuration `events.audit.enabled=true` is set; it may also need to be restricted to region `VN`. When the flag is off, the application must still emit the event and other listeners must still process normally. What we need is a **condition for a single listener**, not cancelling the event system-wide.

In Spring Framework, `Environment` provides two kinds of information: **profiles** (e.g., `dev`, `staging`, `prod`) and **properties** (e.g., `events.audit.enabled`). The word "dynamic" has two distinct meanings to separate clearly:

- **Chosen when creating the `ApplicationContext`:** Spring inspects profiles/properties to decide whether to register the listener bean. Once the context is initialized, changing configuration does not automatically recreate beans.
- **Evaluated on each event:** the listener is already registered; each incoming event is checked against the configuration value at processing time. When the configuration source actually changes and can be re-read, subsequent events can yield a different outcome without rebuilding the listener.

The typical flow is: `publishEvent(event)` → Spring finds listeners compatible with the event type → evaluates `condition` if present → invokes the listener method when the condition is true. A `false` condition only skips **that listener method**; other listeners can still run.

## 2. Three Easily Confused Mechanisms

| Mechanism | Decision time | Use case |
| --- | --- | --- |
| `@Profile("prod")` on class or bean | At bean registration when context is initialized | Listener exists only in a specific deployment environment |
| `@ConditionalOnProperty` (Spring Boot) | During configuration processing/bean registration | Enable or disable an entire bean based on startup properties |
| `@EventListener(condition = "...")` | Each time Spring evaluates an event for a registered listener | Filter events by payload, feature flags, or policies read at runtime |
| `@EventListener` with `if` inside method body | Each time the listener method is invoked | Complex conditions, needing clear debugging or depending on multiple services |

`@Profile` belongs to Spring Framework. `@ConditionalOnProperty` belongs to **Spring Boot** and is not available if a project only depends on `spring-context`. Both typically decide **whether the bean exists** at startup, and do not make a listener automatically appear or disappear when properties change after `refresh()`.

Example of profile-based configuration:

~~~java
@Component
@Profile("prod")
public class ProductionAuditListener {
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // This listener bean exists only when the prod profile matches at startup.
    }
}
~~~

This snippet only illustrates the annotations and requires the `OrderPlaced` type, appropriate imports, and component scanning configuration to work. If a listener must remain in the context but be toggled per event publication, use the mechanism in the next section.

## 3. Writing SpEL Conditions for `@EventListener`

The `condition` attribute takes a Spring Expression Language (SpEL) expression. Spring evaluates the expression when considering an event; a Boolean `true` causes the method to be invoked, and `false` causes it to be skipped. Data can be accessed via `#root.args`, `#a0` or `#p0` (first parameter), and by parameter name if name metadata is available at compile time.

~~~java
@EventListener(condition = "#a0.region() == 'VN'")
public void handle(OrderPlaced event) {
    // Only handle events whose region equals VN.
}
~~~

With a Java `record OrderPlaced(String id, String region)`, `region()` is the record's accessor method. Using `#a0` keeps the expression independent of parameter variable names in bytecode.

To make a condition depend on configuration, put the configuration-reading logic into a clearly named bean, then invoke that bean from SpEL:

~~~java
@EventListener(
    condition = "@auditSwitch.enabled() and #a0.region() == 'VN'"
)
public void handle(OrderPlaced event) {
    // Runs when the current flag is enabled and the order belongs to region VN.
}
~~~

The `@auditSwitch` notation references the bean named `auditSwitch` in the context. The `and` operator performs logical AND; if the flag is off, the region check branch does not need to be evaluated. Using a bean allows testing and centralizes property reading policies; avoid scattering property key strings, type conversions, and default rules across listeners.

**Key takeaway:** the expression is evaluated every time a matching event arrives, but the value it sees is only "dynamic" if `auditSwitch.enabled()` actually reads an updated source. Editing a YAML file on disk or changing an OS environment variable on the host does not automatically reload the running `Environment`.

## 4. Runnable Example: Toggling a Flag Between Events

This example uses only Spring Framework and does not require Spring Boot. The program creates a `MapPropertySource` backed by a mutable configuration map, publishes four events in sequence, and checks whether the listener runs according to the **flag value at the time each event is published**.

Directory structure:

~~~text
demo/
├── pom.xml
└── src/main/java/DynamicEnvironmentEventsDemo.java
~~~

`pom.xml` (Java 17+, Spring Context 6.2.0):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>dynamic-environment-events-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>DynamicEnvironmentEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/DynamicEnvironmentEventsDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public final class DynamicEnvironmentEventsDemo {

    // A plain data object can also be published as an event.
    public record OrderPlaced(String id, String region) { }

    public static final class AuditSwitch {
        private final Environment environment;

        public AuditSwitch(Environment environment) {
            this.environment = environment;
        }

        public boolean enabled() {
            // Missing or invalid per type converter => handle appropriately;
            // in this example, property "true"/"false" is valid and defaults to false.
            return environment.getProperty(
                "events.audit.enabled", Boolean.class, false
            );
        }
    }

    public static final class AuditListener {
        @EventListener(
            condition = "@auditSwitch.enabled() and #a0.region() == 'VN'"
        )
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("AUDIT " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("auditSwitch")
        AuditSwitch auditSwitch(Environment environment) {
            return new AuditSwitch(environment);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    private static void publish(
        AnnotationConfigApplicationContext context,
        String id,
        String region
    ) {
        System.out.println("PUBLISH " + id + " " + region);
        context.publishEvent(new OrderPlaced(id, region));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            Map<String, Object> flags = new HashMap<>();
            flags.put("events.audit.enabled", "false");

            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("demoFlags", flags)
            );
            context.register(AppConfig.class);
            context.refresh();

            publish(context, "A-001", "VN");   // flag false: do not audit

            flags.put("events.audit.enabled", "true");
            publish(context, "A-002", "VN");   // flag true, VN: audit
            publish(context, "A-003", "US");   // flag true, US: skip

            flags.put("events.audit.enabled", "false");
            publish(context, "A-004", "VN");   // flag false: skip
        }
    }
}
~~~

In the `demo/` directory, run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program to `stdout`, in exact order:

~~~text
PUBLISH A-001 VN
PUBLISH A-002 VN
AUDIT A-002
PUBLISH A-003 US
PUBLISH A-004 VN
~~~

Explanation: When receiving `A-001`, Spring skips `AuditListener` because the flag is `false`. We update the value in the source map and emit `A-002`; `AuditSwitch` re-reads `Environment`, returns `true`, and `region()` is `VN`, so it prints `AUDIT A-002`. `A-003` is filtered out by region. `A-004` is filtered out because the flag was turned back off. At no point did the listener need to be re-registered.

**Why can the example change immediately?** `MapPropertySource` is backed by the same `flags` object. Here the updates occur sequentially on a single thread, and the next property read sees the new value. This demonstrates evaluation-time behavior; in a multithreaded application, do not use a shared mutable `HashMap` like this as a dynamic configuration store. Choose a configuration source with explicit update semantics and thread safety.

## 5. Using `Environment` Inside a Listener When Conditions Are Complex

You do not have to use SpEL for the entire policy. The listener can be invoked and decide for itself whether to proceed:

~~~java
@Component
public class BillingEventListener {
    private final Environment environment;

    public BillingEventListener(Environment environment) {
        this.environment = environment;
    }

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        boolean enabled = environment.getProperty(
            "events.billing.enabled", Boolean.class, false
        );
        if (!enabled || !"VN".equals(event.region())) {
            return;
        }
        // Business logic: send payment request, write log...
    }
}
~~~

This snippet illustrates a bean in a project that already defines `OrderPlaced`; it requires imports for `Component`, `EventListener`, and `Environment`. Spring still calls `onOrderPlaced` for every `OrderPlaced`, and the `return` statement skips the business work. This approach fits when the policy has many branches, needs to log why an event was skipped, or needs to call services instead of writing a long expression.

If you want something cleaner while still filtering before the method call, create a policy service with an `allows(OrderPlaced)` method and reference it from SpEL:

~~~java
@EventListener(condition = "@orderEventPolicy.allows(#a0)")
public void onOrderPlaced(OrderPlaced event) {
    // Business logic
}
~~~

`orderEventPolicy` must be an actual bean with this name and an accessible `allows` method. That way the expression only coordinates; the service handles reading properties, checking region, tenant, or configuration rules.

## 6. Profiles, Properties, and Runtime Changes

### Profiles for Deployment Environments

Place `@Profile("prod")` on a listener class when **which environment should have the bean** is an initialization-time decision. You can activate profiles via application configuration before the context starts. Changing `spring.profiles.active` after the context has called `refresh()` does not cause Spring to automatically scan, create, or destroy listeners for the new profile.

### Properties for Feature Toggles

In Spring Boot, `@ConditionalOnProperty(prefix = "events.audit", name = "enabled", havingValue = "true")` can decide bean creation at configuration time. This differs from an `@EventListener` condition: that Boot condition **does not re-trigger automatically** when the property changes at runtime. When toggling per event is needed, keep the listener in the context and read the flag in the event handling path.

### How Configuration Sources Actually Change

`Environment` looks up values across `PropertySource`s in priority order. For a configuration file or OS environment variable already loaded into the context, Spring Framework does not watch for changes and emit refresh notifications by default. Depending on requirements, use an updatable value source, a feature flag service, a dedicated refresh mechanism, or a controlled context reload. Verify **value freshness**, **source precedence**, and **thread safety**.

Do not call `System.getenv()` inside a listener assuming that changing an external environment variable will immediately appear inside the running Java process. Process environment variables and dynamic configuration systems are two different concepts.

## 7. Design Rules and Common Pitfalls

1. **Distinguish registration conditions from processing conditions:** `@Profile`/`@ConditionalOnProperty` are for bean creation; `@EventListener(condition = ...)` is for individual events. If a listener is never registered, none of its filter expressions are evaluated.
2. **Choose safe defaults:** for optional features like supplementary auditing, using `false` when the property is missing can be appropriate. For mandatory business tasks, never silently skip processing just because configuration is missing; raise a configuration error or design a resilient fallback.
3. **Use Boolean type when reading flags:** `getProperty(key, Boolean.class, false)` makes intent clearer than comparing a series of strings manually. A property with an unconvertible value can cause a conversion error; validate configuration inputs.
4. **Avoid overly complex SpEL:** long expressions, network service calls, or database access inside `condition` reduce observability and can cause errors or slow down the publishing path. Move policies into a bean/service, add appropriate caching, and test separately.
5. **Know whether events run synchronously or asynchronously:** with the default multicaster without a custom executor, normal listeners run synchronously on the publishing thread. If using `@Async` or an executor on the multicaster, the actual evaluation time of the flag may be later than the `publishEvent` call; do not expect a "publish-time" configuration snapshot unless you put that snapshot into the event.
6. **Never use conditions as a security boundary:** the event is still published to the context and other listeners. `@EventListener` filtering does not replace authorization checks, tenant isolation, or ensuring only one party sees the data.
7. **Do not confuse internal events with durable queues:** Spring Framework's `ApplicationEventPublisher` does not persist skipped events and does not transport events across processes. If retries, delivery guarantees, or replay are required, design dedicated storage/messaging.
8. **Test on → off → on transitions:** do not test only one initial configuration; publish events after each configuration source update, including non-matching payloads and missing properties.

Quick selection table:

| Requirement | Solution to start with |
| --- | --- |
| Listener exists only in `prod` | `@Profile("prod")` |
| Bean created only when startup flag is on, using Spring Boot | `@ConditionalOnProperty` |
| Listener exists, toggled by flag updated at runtime | `@EventListener(condition = "@namedPolicy.allowed(#a0)")` |
| Need detailed logging of skip reasons and multiple branches | Inject `Environment`/policy service and `if (...) return` in listener |
| Need to lock in policy at publish time despite async processing | Include decision snapshot or required configuration data in the event |

## 8. Self-Check Exercises

1. Keep `events.audit.enabled=false` and publish three different `OrderPlaced` events. Why does the audit listener print nothing even though `publishEvent` still runs?
2. Change the flag from `false` to `true` in the active `MapPropertySource`, then emit a `VN` event again. What causes the outcome to change: SpEL re-evaluation or automatic bean re-registration?
3. Replace `@EventListener(condition = ...)` with `@Profile("prod")` and try changing the active profile after `refresh()`. Why is this not an equivalent replacement?
4. If an event is processed asynchronously, how can the rule "use the flag at publish time" remain deterministic? Hint: evaluate or snapshot the configuration value at publish time and include that information in the payload.

**Self-check answers:** (1) the flag blocks only that listener invocation; (2) SpEL re-evaluates and the policy reads the new value; (3) profiles affect bean registration during context construction; (4) pass the immutable decision/snapshot in the event instead of reading a flag that may change later.

## References

- Spring Framework Reference, *Application Events / Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Environment Abstraction / Profiles / PropertySource*: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Framework API, *EventListener.condition*: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html