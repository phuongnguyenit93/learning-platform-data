# Controlling Third-Party Library Listeners in Spring Application Events

## 1. Security Concerns When Integrating Libraries with Listeners

Spring Application Events allow code to publish events via `ApplicationEventPublisher.publishEvent(...)`, and matching listeners react without the producer needing to know the consumer list. A library or Spring Boot starter may provide beans implementing `ApplicationListener<?>`, `@EventListener` methods, or programmatic listener registration. Once registered in the right `ApplicationContext`, that listener can observe any event it subscribes to.

This is convenient for auditing, logging, monitoring, caching, analytics, and integrations. Yet for systems holding sensitive data, ask:

- Does the library genuinely need to receive this event?
- What is in the event payload: emails, phone numbers, tokens, payment details, `Authentication`, JPA entities, requests, or tenant data?
- How is the listener registered: `@ComponentScan`, `@Import`, auto-configuration, or `SpringApplication.addListeners(...)`?
- Could the library log data, call external APIs, or publish child events?
- If the listener is slow or throws an exception, are the source request and transaction affected?
- If the starter version is upgraded, might a new listener appear automatically?
- Is there a way to disable that exact listener before the application starts and test that it is disabled?

Risk flow example:

~~~text
OrderService
    |
    +-- publish(OrderPlaced)
                  |
                  +-- InternalAuditListener          (internal)
                  +-- SearchProjectionListener       (internal)
                  +-- VendorAnalyticsListener        (third-party library)
                  +-- LibraryTelemetryListener       (another library)
~~~

If `OrderPlaced` contains an entire `Customer` object with addresses, emails, and private details, matching listeners can access that data. That **does not prove** the vendor will necessarily leak data, yet it is reason enough to govern **data flow** and integration permissions.

**Important principle:** Spring `ApplicationEventPublisher` **is not an authorization mechanism or sandbox**. Listeners in the same JVM are code running in the same process and may have other ways to access data besides listening to events. Disabling a listener or filtering events only controls specific behavior; **it does not guarantee isolation of untrusted code**.

### Learning Objectives

After this lesson, learners will be able to:

1. Identify the mechanisms libraries use to register `ApplicationListener` and `@EventListener`.
2. Distinguish having a class on the classpath from having an active listener in the context.
3. Use explicit registration, component-scan scoping, conditional configuration, and auto-config exclusions properly.
4. Design immutable, minimal event DTOs with data classification.
5. Distinguish event routing, `@Order`, and `@EventListener(condition)` from real authorization.
6. Detect third-party listeners that can impact transactions, latency, and side effects.
7. Test a real Spring context with vendor listeners enabled/disabled and payloads free of sensitive data.
8. Move integrations out to a separate gateway/service when stronger trust boundaries are needed.

## 2. How Does Spring Discover Listeners?

In `ApplicationContext`, `ApplicationEventMulticaster` selects listeners based on event type and matching metadata. `SimpleApplicationEventMulticaster` by default invokes listeners on the **publisher's thread**. A listener may take these forms:

~~~java
// Illustrative code; requires real types/imports.
public class VendorApplicationListener
        implements ApplicationListener<SomeApplicationEvent> {

    @Override
    public void onApplicationEvent(SomeApplicationEvent event) {
        // Handle event.
    }
}
~~~

Or:

~~~java
// Illustrative code inside a Spring-managed bean.
@Component
public class VendorAnnotatedListener {

    @EventListener
    public void on(AccountLifecycleNotice notice) {
        // Handle notice.
    }
}
~~~

With the second form, Spring uses `EventListenerMethodProcessor` to find `@EventListener` methods on managed beans and register listener adapters. Hence, **you cannot inventory all listeners simply by counting beans extending/implementing `ApplicationListener`**.

Spring also supports publishing POJO/record events; objects may be wrapped in `PayloadApplicationEvent<?>` during processing. Do not search only for classes extending `ApplicationEvent` when auditing published data.

### 2.1. Registration Paths That May Appear

| Path | How It Works | Control Point |
| --- | --- | --- |
| `@ComponentScan` | `@Component` beans in scanned packages | Restrict packages/filters |
| `@Bean` | App/vendor `@Configuration` creates listener | Import only reviewed configs |
| `@Import` | Imports vendor configuration | Audit import points |
| Spring Boot auto-configuration | Starter supplies config when conditions match | Properties and exclude auto-config |
| Programmatic | `context.addApplicationListener(...)` | Audit bootstrap/plugin-loader code |
| Boot early listener | `SpringApplication.addListeners(...)` or `spring.factories` | Audit startup registration |
| Framework/plugin manager | Instantiates beans or attaches listeners per custom lifecycle | Explicit owner and policy |

**Adding a JAR dependency does not automatically activate every listener inside the JAR.** A registration path must exist. Conversely, a starter can auto-configure a listener without application code ever calling it directly.

### 2.2. Type Matching Is Not a Permission Check

`@EventListener` can declare an event class or `condition`. That helps the framework decide whether a method participates in dispatch; it **does not enforce an ACL on other listeners**.

For instance, an `@EventListener(condition = "...")` method does not prevent another listener from subscribing to the same event. `@Order` adjusts execution order under matching conditions rather than making payloads "secret" from later listeners.

If an event contains a token, creating an internal `@Order(0)` listener to "strip the token first" is not a trustworthy security design either: objects may be shared/mutable, other listeners may still be invoked, and ordering is not a data-access policy.

## 3. Risk Classification by Confidentiality, Integrity, and Availability

| Risk Category | Scenario | Mitigation |
| --- | --- | --- |
| Confidentiality | Vendor listener receives PII, tokens, or internal data | Do not publish unnecessary data; outbound gateway with allowlist |
| Integrity | Listener writes wrong state or publishes forged facts | Restrict rights, authenticate commands, idempotency |
| Availability | Synchronous listener makes slow HTTP calls or throws errors | Timeouts, retry policies, bulkheads, exception handling |
| Data governance | Logs/exports/event history retain data too long | Retention, audits, DLP, and data reviews |
| Supply chain | Upgrade introduces a new listener/exporter | SBOM, scanning, version pinning, integration tests |

There are at least two distinct **trust models**:

- **Trusted library, optional listener functionality:** feature flags, opt-in/opt-out configs, and testing can be used.
- **Untrusted library/code or risk of compromise:** a feature flag on a listener **does not create a security boundary**. Evaluate running the code in the same process, restrict secrets/OS/network permissions, or isolate it in a separate process/service.

### 3.1. Threat Modeling Before Integration

Ask explicitly:

1. Who owns the library, and how are artifacts updated and verified?
2. Can the library's beans inject `ApplicationContext`, `Environment`, `DataSource`, internal clients, or credentials?
3. Does it have outbound network access, and which destinations are permitted?
4. What data does the vendor need, how long is it retained, and are consent/data-processing agreements required?
5. Is there a risk of cross-tenant access via IDs in events?
6. When events reach logs/traces/outboxes/brokers, are extra PII copies created?
7. Can the integration be replaced by an API accepting a minimal DTO in a separate service?

If vendor code can truly execute arbitrary instructions with the application's privileges, **blocking event paths alone is not enough to stop access to other resources**. State this limitation transparently during security reviews.

## 4. Inventory Listeners Before Disabling or Restricting Them

Do not try to disable what you have not identified. A useful inventory workflow:

1. Identify starters/JARs, versions, and the dependency tree.
2. Scan the vendor for `@EventListener`, `ApplicationListener`, `@Configuration`, `@Import`, and `@AutoConfiguration`.
3. Check whether `@ComponentScan` unintentionally scans vendor packages.
4. Inspect Boot auto-config metadata (for Boot 3.x, `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`).
5. Inspect code calling `addApplicationListener` or factory registrations during bootstrap.
6. Run context tests to confirm whether the vendor bean actually exists and the listener is invoked for the target events.
7. Audit outbound calls and logging in that listener, not just its annotations.
8. Diff before and after every vendor library upgrade.

### 4.1. Why Counting ApplicationListener Beans Is Not Enough

~~~java
// Illustrative snippet: only one data source for inventory.
Map<String, ApplicationListener> beans =
    context.getBeansOfType(ApplicationListener.class);
~~~

This code requires a `context` variable and appropriate imports. It sees only beans of type `ApplicationListener` returned by the container, **not necessarily listener adapters created from `@EventListener` methods**. Combine source review, bean config inspection, integration tests, and instrumentation for a reliable inventory.

### 4.2. Spring Boot Condition Report and Actuator

With Spring Boot, you can inspect the condition evaluation report by enabling `--debug` diagnostics appropriately. If Actuator is present, `/actuator/beans` and `/actuator/conditions` help reveal existing beans and auto-configurations.

Never expose these endpoints publicly: they disclose internal structure. Access them only behind proper protection, and avoid printing secrets when debug logs are enabled.

### 4.3. Do Not Conclude From Class Names Alone

A vendor having a `VendorAnalyticsListener` class that is never registered is not an active listener. Conversely, a generically named class like `StarterConfiguration` may instantiate multiple listener beans. Follow the actual dependency graph and registration mechanisms.

## 5. Prefer Not Registering Unnecessary Listeners

The cleanest control is **not creating the bean/listener** if the feature is not authorized.

Avoid overly broad component scans:

~~~java
// Example snippet: may unintentionally scan all vendor components.
@ComponentScan(basePackages = {
    "com.example.application",
    "com.vendor.all"
})
~~~

When the app owns configuration, import only reviewed parts:

~~~java
@Configuration
@Import(ApprovedVendorConfiguration.class)
public class ApplicationConfiguration {
    // Remaining configs must be explicit and controlled.
}
~~~

Both snippets require specific imports and types; they **do not** mean merely omitting `@Import` disables every vendor listener. A vendor may still enter the context via Spring Boot auto-config, component scanning, programmatic listeners, or Boot early listeners.

### 5.1. Opt-In Configuration via Spring Boot Conditions

When the app controls the config creating the listener, gate context creation with a condition:

~~~java
// Spring Boot snippet; @ConditionalOnProperty is not in Spring core.
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "integrations.vendor",
    name = "events.enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class VendorEventConfiguration {
    @Bean
    VendorListener vendorListener() {
        return new VendorListener();
    }
}
~~~

In the properties file:

~~~properties
integrations.vendor.events.enabled=false
~~~

When the property is `false` and the configuration above is the **only path creating that listener**, the listener bean is not created. If the library has its own independent auto-config, a property invented by the app **does not automatically disable** that auto-config. Use the vendor's documented property or intervene at the actual registration path.

**Do not treat dynamic properties as unregistering.** Conditions are typically evaluated while building the `ApplicationContext`. Changing a property after startup does not automatically destroy already-registered beans/listeners or undo already-processed events.

### 5.2. Exclude Specific Spring Boot Auto-Configurations

When a vendor starter provides a specific auto-configuration class, Spring Boot supports exclusion:

~~~properties
spring.autoconfigure.exclude=com.vendor.starter.VendorEventsAutoConfiguration
~~~

Or use `@SpringBootApplication(excludeName = "...")` with the matching fully qualified name.

Mandatory condition: that class must actually be a **Boot auto-configuration** loaded by Boot, not an arbitrary `@Component`. Excluding auto-config does not remove the JAR from the classpath and does not stop another registration mechanism from creating listeners. Class names in examples are illustrative; verify documentation/metadata for your exact version.

### 5.3. @ConditionalOnMissingBean Is Not a Kill Switch for All Vendor Listeners

Some starters back off when the app provides a bean of the same type via `@ConditionalOnMissingBean`. Rely on this **only if the vendor genuinely uses that condition** and matches the exact bean type/name. Creating a dummy bean to "block all listeners" can hide remaining side effects or produce a broken configuration.

### 5.4. Do Not Unregister Late When You Can Prevent Creation Upfront

`ApplicationEventMulticaster` provides registration-management APIs, yet removing a listener after `refresh` can be unsafe because:

- `@EventListener` methods have internal adapters, not always a direct bean.
- The listener may already have run, read payloads, or sent data externally.
- Another source may re-register it.
- In-flight async tasks may continue running.
- Broad remove-all APIs can break internal/framework listeners.

The preferred approach is controlling configuration **before the context finishes initializing**, then verifying via integration tests. Dynamic plugin lifecycles require explicit ownership/register/unregister contracts, not ad-hoc removal calls.

## 6. Protecting Data with Minimal Event DTOs

Even with registration controlled, sensitive data **should not be placed on a shared event bus unnecessarily**.

Counterexample:

~~~java
// Illustrative code: do not publish payloads like this.
publisher.publishEvent(
    new CustomerUpdated(
        customerEntity, authentication, servletRequest, accessToken
    )
);
~~~

With such a payload, any matching listener receives objects carrying PII, tokens, sessions, JPA relations, and references capable of querying additional data. Async listeners face extra risks from mutable objects, lazy proxies, or out-of-transaction persistence contexts.

Better design:

~~~java
public record AccountLifecycleNotice(
    String accountRef,
    String action,
    long aggregateVersion
) { }
~~~

Publish a minimal fact:

~~~java
publisher.publishEvent(
    new AccountLifecycleNotice("acct-42", "CREATED", 1L)
);
~~~

That is a data-allowlisted contract: identifier, change type, version. Each field still requires classification. For example, `accountRef` may still be personal data if identity can be looked up from it. Yet omitting redundant emails, passwords, raw HTTP requests, or entity graphs drastically reduces the exposure surface.

### 6.1. What Generally Should Not Appear in Shared Events

- Passwords, API keys, OAuth tokens, refresh tokens, cookies, session IDs.
- `Authentication`, `Principal`, security contexts, or full HTTP headers.
- Large JPA entities, mutable objects, or lazy relationships with unclear lifecycles.
- Addresses, phone numbers, or emails when consumers only need to know an object changed state.
- Full payment details, internal contracts, or logs/error messages containing PII.
- `DataSource`, connections, transaction/session objects.
- Entire command/request DTOs when they contain many unused fields.
- Data from another tenant when consumers handle only the current tenant.

For records, `toString()` normally prints the name and value of every component. Never casually log entire event records if any component is sensitive.

### 6.2. Required and Controlled Metadata

| Field | Purpose | Notes |
| --- | --- | --- |
| `eventId` | Dedup and audit | Never substitute customer email |
| `eventType` | Business fact | Clear name, versionable |
| `schemaVersion` | Payload contract | Supports evolution |
| `aggregateRef` | Related object | ID may still be PII |
| `occurredAt` | Timestamp when fact occurred | UTC/Instant |
| `correlationId` | Workflow tracing | Avoid embedding sensitive data directly |
| `tenantRef` | Data scope | Does not replace authorization checks |
| `audience` (if custom-defined) | Outbound policy hint | Spring **does not enforce ACLs** from this field |

An `audience` field in an event is just data. A **trusted gateway/adapter** is required to decide which consumer receives which data.

## 7. Complete Java 17+ Program: Deliberate Vendor Listener Configuration

This example uses Spring Framework 6.2.8, JDK 17+, and Maven without Spring Boot. It aims only to demonstrate:

1. A vendor listener **is absent** if the app does not import the config creating the bean.
2. When the config is registered before `refresh`, the listener receives permitted events.
3. The service accepts a private email, yet the event record **contains no email**.
4. This is **registration control and data minimization**, not a security sandbox.

### 7.1. Directory Structure

~~~text
vendor-listener-demo/
├── pom.xml
└── src/main/java/VendorListenerControlDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>vendor-listener-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                    <mainClass>VendorListenerControlDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/VendorListenerControlDemo.java

~~~java
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class VendorListenerControlDemo {

    // DTO containing only data approved for the event bus.
    public record AccountLifecycleNotice(
        long accountId,
        String action
    ) { }

    public static class AccountService {
        private final ApplicationEventPublisher publisher;

        public AccountService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void register(long id, String privateEmail) {
            Objects.requireNonNull(privateEmail, "privateEmail");
            if (id <= 0 || privateEmail.isBlank()) {
                throw new IllegalArgumentException("Invalid account");
            }
            // Email data is not placed into the event record.
            System.out.println("SERVICE_UPDATED id=" + id);
            publisher.publishEvent(
                new AccountLifecycleNotice(id, "CREATED")
            );
        }
    }

    // Simulates a listener inside an optional library.
    public static class VendorListener {
        private int received;

        @EventListener
        public void on(AccountLifecycleNotice notice) {
            received++;
            System.out.println(
                "VENDOR_NOTICE id=" + notice.accountId()
                + " action=" + notice.action()
            );
        }

        public int receivedCount() {
            return received;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        AccountService accountService(
                ApplicationEventPublisher publisher) {
            return new AccountService(publisher);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class VendorConfig {
        @Bean
        VendorListener vendorListener() {
            return new VendorListener();
        }
    }

    private static void scenario(boolean vendorEnabled) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.register(CoreConfig.class);
            if (vendorEnabled) {
                context.register(VendorConfig.class);
            }
            context.refresh();

            System.out.println("VENDOR_ENABLED=" + vendorEnabled);
            context.getBean(AccountService.class)
                .register(42L, "private@example.invalid");

            int handled = context
                .getBeansOfType(VendorListener.class)
                .values()
                .stream()
                .mapToInt(VendorListener::receivedCount)
                .sum();

            System.out.println("VENDOR_DELIVERED=" + handled);
        }
    }

    public static void main(String[] args) {
        scenario(false);
        scenario(true);
    }
}
~~~

Run from the `vendor-listener-demo` directory using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines **printed by the program** (excluding Maven logs) in order:

~~~text
VENDOR_ENABLED=false
SERVICE_UPDATED id=42
VENDOR_DELIVERED=0
VENDOR_ENABLED=true
SERVICE_UPDATED id=42
VENDOR_NOTICE id=42 action=CREATED
VENDOR_DELIVERED=1
~~~

### 7.4. Proper Interpretation

In the first scenario, only `CoreConfig` is registered; `VendorListener` does not exist in the context. The service still publishes the event, yet no vendor listener receives it, so the counter is 0.

In the second scenario, `VendorConfig` is registered **before `context.refresh()`**. Spring detects the `@EventListener` method and registers an adapter; the listener runs synchronously when `AccountLifecycleNotice` is published, prints one line, and the counter becomes 1.

`AccountLifecycleNotice` has only `accountId` and `action`. The input email is validated inside the service and never placed in the event payload. **However**, the event omitting the email does not prove a malicious library could not obtain the email another way; if it has access to repositories/HTTP clients/credentials in the same JVM, it still holds other capabilities. Real security boundaries and permissions are needed when trust is low.

### 7.5. Scope Not Covered by the Demo

- The demo has no Boot auto-configuration or component scanning of vendor packages.
- It does not test runtime listener unregistration.
- It has no multi-tenant authorization.
- It has no database transactions, brokers, outboxes, async executors, or network I/O.
- It does not prove preventing a vendor library from loading classes or accessing resources once the library is already in the same process.
- It does not prove protecting data from a plugin capable of executing arbitrary code.

This is an example of **functional registration control** and **data minimization**, not a security sandbox.

## 8. When Should Third-Party Listeners Be Moved Off the Internal Event Bus?

If a library only needs to forward certain facts to an analytics or notification service, consider a **trusted outbound gateway** instead of letting a vendor SDK subscribe directly to an internal bus carrying rich payloads.

~~~text
Domain use case
     |
     +-- internal state change
     |
     +-- Trusted OutboundGateway
             |
             +-- select approved fact
             +-- validate business and tenant policy
             +-- map to public DTO
             +-- redact / pseudonymize as required
             +-- enqueue durable intent if necessary
             |
             v
         Isolated vendor adapter
             |
             +--> vendor API / broker
~~~

Principles:

- The app keeps unnecessary sensitive data **inside the trusted boundary**.
- Outbound DTOs are allowlist-designed, never serialized straight from entities.
- Authorization is enforced at the gateway/data layer, not just by looking at a `tenantId` field.
- Credentials are scoped strictly to what the vendor API needs.
- Network egress is allowlisted, rate-limited, and audited.
- Retries/idempotency are explicit, avoiding unintended duplicate side effects.
- Logs and telemetry use approved fields with defined retention.

For **genuinely untrusted** vendor code, separating processes/containers/services with IAM, filesystem, and network boundaries is stronger than sharing a JVM. Even so, a separate process is not automatically safe if it is still handed overly broad data and permissions. End-to-end policies are needed.

### 8.1. Separate Contexts Are Not Necessarily a Sandbox

One or more `ApplicationContext` instances in the same JVM separate configuration/lifecycles, not arbitrary code execution. Furthermore, events from a child context can propagate up to the parent; placing a vendor listener in the parent does not guarantee isolating it from child events. Never treat context hierarchy as an implicit ACL.

### 8.2. Distinguish Event Contracts from Commands/Authorization

An event describes a fact that already happened. If a vendor needs to **perform a privileged action**, expose an authorized API/command gateway instead of letting it call arbitrary internal services from a listener. Events do not prove which principal is authorized to execute side effects.

## 9. Exceptions, Latency, and Transactions of Vendor Listeners

A library listener can cause incidents even when the payload is non-sensitive:

- Slow HTTP calls inflate request p95/p99 latency.
- Runtime exceptions propagate back during synchronous dispatch.
- Side effects keep the source transaction holding connections/locks longer.
- The listener publishes child events, creating chains or loops.
- Error logging captures excessive details.
- Retries lacking idempotency cause duplicate notifications/payments.

### 9.1. Synchronous Listeners Can Trigger Rollbacks

`SimpleApplicationEventMulticaster` by default invokes regular listeners on the publisher thread. If `publishEvent` runs inside `@Transactional` and a listener throws an unhandled exception, the exception can propagate and cause the source transaction to roll back per transaction rules.

If a vendor listener only performs auxiliary work, decide explicitly: **should its failure be allowed to fail the primary use case?** Never let a starter silently alter business semantics.

### 9.2. ErrorHandler Is Not Permission Enforcement

~~~java
// Configuration snippet; requires beans/imports in the application.
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(ex -> {
        System.err.println(
            "Listener failure type=" +
            ex.getClass().getSimpleName()
        );
    });
    return multicaster;
}
~~~

`ErrorHandler` handles errors when the multicaster invokes a listener; depending on logic, the exception may be logged/suppressed or rethrown. It **does not stop** the listener from having already read the event and does not undo completed side effects. Do not treat an error handler as data-loss prevention.

### 9.3. @Async Does Not Make a Library Trustworthy

`@Async @EventListener` can move the handler body onto an executor, yet:

- The payload is still delivered to the listener.
- The code still executes inside the application's JVM with process privileges.
- Errors in `@Async void` usually go to `AsyncUncaughtExceptionHandler` instead of the publisher's call stack.
- Executors can fill up, reject tasks, or lose tasks if the process crashes.
- Thread-bound transactions and some `ThreadLocal` contexts do not propagate automatically.
- Timeouts and circuit breakers must be configured on outbound calls.

Consider a **dedicated bounded executor/bulkhead** for vendor workloads to reduce availability blast radius, yet preventing data exposure still requires proper payload/gateway design upfront.

### 9.4. AFTER_COMMIT Does Not Make Data Safer

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` synchronizes timing after commit in an active transaction; it does not restrict who reads the payload. If published outside a transaction, the handler does not run by default unless `fallbackExecution=true` is set.

After-commit is not durable delivery either. If the process dies before the job finishes, the task can be lost. When events must not be lost, use a **transactional outbox** or durable job storage with idempotent consumers. An outbox containing PII also requires encryption, access controls, and retention; it is not safe by default.

## 10. Testing Vendor Listeners and Data Contracts

### 10.1. Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Vendor disabled | Vendor listener bean/config is absent across controlled registration paths |
| Vendor enabled | Listener receives the exact approved event contract |
| Minimal event payload | No sensitive emails/tokens/requests/entities |
| Vendor auto-config excluded | No listener registered via the excluded config |
| Vendor has secondary registration | Test detects if the listener still enters the context via another path |
| Sync listener error | Propagation/rollback matches policy |
| Async listener error | Error monitoring and retry policy verified |
| Slow listener | Timeouts/bulkheads and latency SLA hold |
| Child/parent context | No unintended propagation |
| Boot early listener | Does not run before permitted startup phase |
| Dependency upgrade | Contract and listener inventory do not change unexpectedly |
| Outbound vendor payload | Only allowlisted data is sent to approved destinations |
| Multi-tenant | Authorization and data segregation enforced |
| Retry/dedup | No duplicate side effects on redelivery |

### 10.2. Use a Real Spring Context to Test Wiring

A Mockito mock of `ApplicationEventPublisher` can verify `publishEvent(...)` was called, yet **does not dispatch** to Spring listeners. Therefore, mocked unit tests **do not prove** whether a vendor listener is enabled or disabled.

For registration tests, boot an `ApplicationContext` matching the target environment's configuration, publish via the real publisher, and measure listener/gateway outcomes. In the demo, `VendorListener.receivedCount()` is observable because the handler runs synchronously.

### 10.3. Checking Record Schema Allowlists

For a minimal DTO record, a unit test can verify component names:

~~~java
// JUnit test snippet, not part of the runnable demo file.
var names = java.util.Arrays.stream(
    AccountLifecycleNotice.class.getRecordComponents()
).map(java.lang.reflect.RecordComponent::getName).toList();

assertEquals(
    java.util.List.of("accountId", "action"),
    names
);
~~~

However, checking the record schema alone **is insufficient** to conclude absolute safety. IDs may link back to data, and outbound adapters may add metadata/headers/logs not inside the record. A stronger test asserts that the **actual serialized request/payload at the trusted gateway** contains no forbidden data.

### 10.4. A Data Negative Test

1. Create an account with a fake email containing a canary marker string.
2. Invoke the use case in the test environment.
3. Capture the outbound request/body at the vendor adapter's mock server.
4. Assert the allowlisted schema and absence of the canary email string.
5. Verify no tokens or raw entities were logged.
6. Test exception paths too so error logs never print full payloads.

Never use real emails, real tokens, or real customer details in test logs.

## 11. Spring Boot Early Listeners and Lifecycle

Several Spring Boot startup events occur before an `ApplicationContext` exists. Listeners registered via `SpringApplication.addListeners(...)` or `META-INF/spring.factories` can run very early. An `@EventListener` bean inside the context does not receive every event occurring before the context forms.

This matters when auditing vendor libraries: a starter may register startup listeners outside beans, and tests checking only after `ApplicationReadyEvent` will miss early startup behavior.

When the context closes, `ContextClosedEvent` fires during shutdown. A vendor listener may call APIs while executors/dependencies are stopping. Set appropriate timeouts and shutdown policies, and never assume late async shutdown events will always finish running.

### 11.1. What Capabilities Does Library Code in the Same JVM Have?

Once vendor code is loaded into the same process, it can interact with Spring beans, the filesystem, or the network depending on privileges and design. An event router cannot stop other activities by that code. Therefore:

- Audit dependencies, provenance, signatures/CVEs.
- Separate egress credentials for integrations.
- Do not expose broad `DataSource`/secrets unnecessarily.
- Restrict network endpoints and container/process permissions.
- Consider running the adapter in a separate process/service when trust is low.

**Never present an `allowedListener` field or type filter as a sandbox.**

## 12. Auditing, Metrics, and Detecting Unexpected New Listeners

Logs should describe **who processed which event**, without putting PII into log content:

~~~text
event=AccountLifecycleNotice id=e-42
publisher=AccountService listener=VendorListener
listener=VendorListener enabled=true status=handled
vendor_outbound=analytics dataClass=APPROVED_REFERENCE
~~~

You can collect:

- Event type, `schemaVersion`, publisher, context ID.
- Listener class/bean, module origin, dependency version.
- Handler duration, exceptions, retries, and rejected tasks.
- Outbound destination and data classification.
- Auto-config conditions and feature flags at startup.
- Timestamps of config changes and deployment versions.

Example **application-defined** metrics:

~~~text
app_event_published_total{type="AccountLifecycleNotice"}
app_event_listener_calls_total{listener="VendorListener"}
app_event_listener_failures_total{listener="VendorListener"}
app_vendor_outbound_requests_total{destination="analytics"}
app_vendor_outbound_denied_total{reason="policy"}
~~~

Never put `eventId`/`accountId`/emails into high-cardinality metric labels. Detailed IDs belong in protected logs/traces with explicit retention.

### 12.1. Sample Policy Table

| Event | Data Category | Approved Consumers | Outbound Policy |
| --- | --- | --- | --- |
| `AccountLifecycleNotice` | Approved ID, action | InternalAudit, VendorGateway | May send after tenant/business checks |
| `FullCustomerProfileUpdated` | Sensitive PII | Trusted internal services only | Never publish to shared bus for vendors |
| `PaymentCaptured` | Transaction fact | Ledger, billing | Exact mapping, idempotency |
| `CredentialRotated` | Minimal metadata only | Security monitor | Never send credential secrets |

This is an **application-defined** governance policy, not an ACL table automatically enforced by Spring.

## 13. Controlling Changes When Upgrading Libraries

A vendor upgrade can:

- Add a new `@EventListener` method to an existing bean.
- Move a listener from explicit config to Boot auto-configuration.
- Change toggle properties or auto-config class names.
- Register a startup listener via `spring.factories`.
- Switch a sync handler to async, altering error propagation.
- Add an HTTP exporter/telemetry or payload logging.
- Change event schemas or PII handling.
- Require new credentials/network permissions.

Thus, a secure application does not control listeners only when first written, but also guards against **dependency version drift**.

### 13.1. Recommended CI/Release Gate

1. Pin vendor versions and inspect the SBOM/dependency tree.
2. Scan security advisories and verify artifact provenance.
3. Diff auto-config/import/annotation registrations before and after upgrades.
4. Run integration tests for both vendor-enabled and vendor-disabled configurations.
5. Run data-contract tests with synthetic PII and capture outbound requests.
6. Verify exception, latency, and shutdown behavior.
7. Review any new permissions, destinations, and retention requirements.
8. Record approval results before release.

A test confirming a specific `VendorListener` is absent **does not guarantee** the library runs no other functionality, so never use that result to skip security reviews.

## 14. Common Mistakes

1. **Confusing an annotated class with an active listener:** registration is required.
2. **Disabling only `@ComponentScan` while forgetting auto-configuration:** the vendor may still register via a starter.
3. **Believing `@Order` filters payloads:** ordering is not an ACL.
4. **Believing `@EventListener(condition=...)` governs all listeners:** it only governs that method.
5. **Publishing JPA entities, raw requests, or `Authentication`:** exposes more data than needed.
6. **Assuming IDs are always non-sensitive:** IDs can link back to individuals or tenants.
7. **Logging entire `event.toString()`:** records can print every component.
8. **Giving vendor SDKs all application credentials:** event filtering does not limit DB/network access.
9. **Using `@Async` to "isolate" an untrusted library:** it still runs in the same JVM.
10. **Treating `ErrorHandler` as DLP:** exception handling does not retract an already-received payload.
11. **Mocking the publisher and concluding listeners do not run:** mocks do not dispatch Spring events.
12. **Counting only `ApplicationListener` beans:** misses method-level adapters.
13. **Changing a runtime property and expecting beans to unregister:** conditions are normally evaluated at context startup.
14. **Removing a listener after publishing:** data read and side effects already executed cannot be undone.
15. **Using parent/child contexts as a sandbox:** child events can bubble to the parent; both share one process.
16. **Assuming `AFTER_COMMIT` means no PII:** transaction phase does not restrict data access.
17. **Storing sensitive events in an outbox without retention/encryption:** creates another long-lived data copy.
18. **Ignoring Spring Boot early events:** listeners can run before the context exists.
19. **Skipping version-upgrade tests:** a new startup listener can appear with zero app code changes.
20. **Omitting bounded executors/timeouts:** vendor handlers can exhaust resources.
21. **Skipping cross-tenant authorization:** a `tenantId` field is not enough to stop wrong-tenant data access.
22. **Assuming a separate process is automatically safe:** you must still restrict APIs, IAM, network, schemas, and logs.

## 15. Pre-Integration Checklist for Vendor Listeners

- [ ] Identified the library, version, all registration paths, and auto-config sources?
- [ ] Does the listener genuinely need to receive published events?
- [ ] Reviewed `@ComponentScan`, `@Import`, and vendor properties?
- [ ] Tested opt-out on a real context rather than just inspecting properties files?
- [ ] Do events use minimal, immutable DTOs without unnecessary secrets/PII?
- [ ] Are IDs/pseudonyms properly classified?
- [ ] Does the outbound gateway enforce tenant/business permissions instead of trusting event fields?
- [ ] Verified serialized outbound payloads and logs do not leak sensitive data?
- [ ] Tracked exceptions, latency, rejected tasks, and retries?
- [ ] Can the listener affect the source transaction, and is that intentional?
- [ ] Is process isolation in place if the library lacks sufficient trust?
- [ ] Are least-privilege credentials, network allowlists, and retention configured?
- [ ] Considered Boot startup listeners and `ContextClosedEvent`?
- [ ] Do library upgrades have integration tests and SBOM/security reviews?
- [ ] If side effects matter, are idempotency/outboxes and failure policies in place?

## 16. Self-Check Exercises

1. A class inside a JAR has `@EventListener` but is not a Spring bean: will it automatically handle events?
2. Why does `context.getBeansOfType(ApplicationListener.class)` fail to show every listener?
3. Can an `@Order(1)` listener stop another vendor listener from reading the payload?
4. An event record contains `CustomerEntity` and `Authentication`. Why should it be replaced with a minimal DTO?
5. Does removing `@ComponentScan("com.vendor")` guarantee disabling listeners created by Boot auto-config?
6. Which type of config does `spring.autoconfigure.exclude` target, and does it remove the JAR from the classpath?
7. Does changing `integrations.vendor.events.enabled` at runtime automatically remove already-created beans?
8. In the demo, why does the first scenario print `VENDOR_DELIVERED=0` and the second print `VENDOR_DELIVERED=1`?
9. Why does the demo not prove that a vendor SDK running in the same JVM is sandboxed?
10. What impact can a synchronous vendor listener throwing an exception have on the source transaction?
11. Does `SimpleApplicationEventMulticaster.setErrorHandler` stop a listener from reading data before failing?
12. Does `@Async` strip tokens from a payload delivered to a vendor?
13. Does `@TransactionalEventListener(AFTER_COMMIT)` control execution timing or data read permissions?
14. Is having `tenantId` in an event enough to enforce cross-tenant authorization?
15. When a library is untrusted, what architecture offers a stronger boundary than registering its listener in the Spring context?
16. Why should you capture the serialized outbound request rather than inspecting only record component names?
17. When a vendor upgrade adds a startup listener via `spring.factories`, are tests that run only after readiness sufficient?

**Answer guide:** (1) no, registration is required; (2) `@EventListener` adapters are not necessarily `ApplicationListener` beans; (3) no; (4) avoid unnecessary payload/graph/PII exposure; (5) no; (6) Boot auto-config, does not remove the JAR; (7) not automatically; (8) opt-in configuration; (9) same JVM/privileges; (10) may propagate and trigger rollback; (11) no; (12) no; (13) timing; (14) no, enforcement is required; (15) separate service/process with IAM/network policies; (16) mappers/metadata/outbound layers can add data; (17) no, startup registrations must be reviewed.

## 17. Summary

**Controlling third-party library listeners** coordinates three layers:

1. **Registration control:** create listener beans strictly opt-in, limit scans/imports, exclude specific Boot auto-configurations, and test real Spring event wiring.
2. **Data minimization and outbound policies:** never publish events with unnecessary secrets/PII, map through allowlisted DTOs, and verify serialized payloads and authorization at trusted gateways.
3. **Trust boundaries and reliability:** code running in the same JVM is not sandboxed by the Spring event bus; when trust is low, consider process isolation and least privilege while governing exceptions, transactions, async execution, timeouts, and retries.

`@Order`, `@EventListener(condition=...)`, `@Async`, `ErrorHandler`, and `@TransactionalEventListener(AFTER_COMMIT)` each serve specific roles, yet **none are data-authorization mechanisms**.

A sound integration asks not only **"does the listener run?"**, but also **"who is registered, what does the payload expose, what other capabilities does the library hold, and how does the system react when the library fails or changes?"**

## References

- Spring Framework Reference 6.2 — *Application Events and @EventListener*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.8 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc — *EventListenerMethodProcessor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html
- Spring Boot Reference — *Application Events and Listeners*: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot Reference — *Auto-configuration and exclusion*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
