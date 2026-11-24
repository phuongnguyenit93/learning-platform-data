# Passing Host Configuration and Services Through a Scoped Context

In a runtime extensibility architecture, the host application can load extensions/plugins to add features. Plugins often need to read a few configuration parameters and invoke certain host capabilities, such as emitting events, querying permitted data, or reading system time. If the host hands over the entire application object, configuration store, DI container, or database connection to a plugin, the extension contract becomes hard to control: the plugin couples to internal details, easily overreaches permissions, and is difficult to detach upon shutdown.

The solution is a **scoped/limited context**: the host constructs an object conforming to a public API, containing minimal configuration tailored to a single plugin and only the services that plugin is authorized to call. The host itself controls identity, scope, quotas, lifecycle, and execution of each service; the plugin receives a stable usage contract.

## 1. Distinguishing the Three Components

- **Extension contract** defines the entry points and lifecycle that a plugin must implement, such as `start(PluginContext)` and `stop()`. This is the API that both the host and plugins compile against.
- **Plugin configuration** is configuration data scoped to the plugin: feature flags, limits, names of allowed resources, processing policies, etc. The host filters, validates, and converts it into a well-defined data type.
- **Host services** are action capabilities controlled by the host, such as EventPublisher, DocumentReader, or TaskScheduler. The plugin calls them through a narrow interface; real implementations, credentials, and infrastructure connections remain in the host.

The key point is that **the context is not a copy of the entire host**. The contract exposes only what is required for the plugin's task.

~~~text
Host / system configuration / infrastructure
          |
          v
  Identify plugin identity
  Validate policy, choose scope
          |
          v
  Create per-plugin PluginContext
    - PluginConfig (filtered, validated)
    - EventPublisher (with quota)
    - Clock/Time API (selected)
          |
          v
    Plugin.start(context)
          |
          v
  Plugin calls API -> Host checks -> Executes
          |
          v
    Host revokes when plugin stops
~~~

If two plugins have different roles, the host must issue **two distinct contexts**, even if they share the same interface class. A plugin must not self-select or escalate its own scope.

## 2. Designing Configuration Around a Clear Contract

### Provide Only Minimal Data

Instead of passing the entire ApplicationConfig, System.getenv(), Spring ApplicationContext, or a Map containing every key, build a configuration type containing only the required values. For example, a greeting plugin only needs a greeting message and an event quota—not internal URLs, database passwords, or token signing keys.

A well-designed configuration typically satisfies these properties:

1. **Explicit and typed**: use a record, enum, or predefined interface; avoid forcing plugins to cast from an arbitrary Map<String, Object>.
2. **Validated by the host before issuance**: check for missing values, numeric ranges, allowlists, and cross-parameter invariants. Do not treat data from manifests/plugins as implicitly trustworthy.
3. **Immutable by contract**: a record with String, integers, and enums is usually appropriate; if it contains List/Map, perform defensive copying and watch out for mutable elements inside.
4. **Clear scope and provenance**: which values are host defaults, which are configured by an administrator, and which are per-plugin or per-tenant.
5. **Clear update policy**: a fixed snapshot for the duration of a run, or an explicit configuration update mechanism (version/event) if dynamic updates are supported.

For instance, a record `PluginConfig(String greeting, int maxEvents)` can reject blank greetings and out-of-range quotas at construction time. These checks protect data consistency. However, **actual permissions and quotas must be enforced by the host inside the service**, not just trusted to parameters visible to the plugin.

### When Configuration Changes

With a snapshot context, the plugin continues seeing the version it received until the host reconfigures or reinitializes it. If the application must support live updates while running, design an explicit contract—such as a versioned snapshot reader or a change callback. Define consistency clearly: when updates take effect for new calls, how in-flight calls are handled, and what happens if the new configuration is invalid.

Do not let a plugin hold a reference to an internal configuration Map that can be mutated concurrently, as results become unpredictable and out-of-scope data can leak.

## 3. Providing Services as Scoped Capabilities

Here, a **capability** is an object permitting a specific set of actions. The interface should describe the business operation the plugin is allowed to perform rather than returning a full-privilege infrastructure object.

| Plugin need | API to provide | Avoid passing directly |
| --- | --- | --- |
| Emit plugin events | EventPublisher.publish(message) with host-attached quota and identity | Full-privilege message broker client |
| Read approved documents | DocumentReader.read(allowedId) with per-call checks | DataSource or filesystem root |
| Read time for processing | Clock or now() method | Entire Runtime/host object |
| Write logs tagged with source | PluginLogger automatically attaching pluginId and filtering data | Unconstrained logger with arbitrary sinks |
| Submit background tasks | TaskScheduler limiting task types, count, and duration | Shared unconstrained ExecutorService |

Services should **bind identity and scope when the host constructs the adapter**. A plugin must not pass its own pluginId or tenantId on each call to spoof identity. Checking permissions on *every call* is essential, especially when permissions can be revoked while the plugin is running.

On the host side, wrappers/adapters can add call-count limits, payload size checks, timeouts, rate limiting, auditing, output filtering, and translation of infrastructure errors into contract error types. These limits must be enforced at the actual service boundary; merely noting them in API docs does not prevent misuse.

**Interface selection principle:** if a plugin only needs to send an event, a `publish(event)` API is far better than returning an object that allows creating topics, deleting queues, browsing all events, and reconfiguring the broker.

## 4. Self-Contained Java 17 Example

The example below shows the host creating a dedicated context for a greeting extension. The configuration is typed and validated; the host provides a single message-publishing service with a quota of two calls; the pluginId label is attached by the host; and the host can revoke the service after the extension stops. A fixed clock makes output verification deterministic.

Save the file **PluginContextDemo.java** (UTF-8):

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class PluginContextDemo {
    public static void main(String[] args) {
        PluginConfig config = new PluginConfig("Hello", 2);
        ScopedPublisher publisher =
                new ScopedPublisher("greeting", config.maxEvents());
        PluginContext context = new SimpleContext(
                config,
                publisher,
                Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"),
                            ZoneOffset.UTC)
        );

        Extension extension = new GreetingExtension();
        extension.start(context);

        // Host revokes the service when the extension lifecycle ends.
        publisher.revoke();
        try {
            context.events().publish("Message after stop");
        } catch (IllegalStateException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }

    // Public contract shared between host and plugin.
    public interface Extension {
        void start(PluginContext context);
    }

    public interface PluginContext {
        PluginConfig config();
        EventPublisher events();
        Instant now();
    }

    public interface EventPublisher {
        void publish(String message);
    }

    public record PluginConfig(String greeting, int maxEvents) {
        public PluginConfig {
            Objects.requireNonNull(greeting, "greeting");
            if (greeting.isBlank() || maxEvents < 1 || maxEvents > 10) {
                throw new IllegalArgumentException("Invalid configuration");
            }
        }
    }

    // Implementation classes owned by the host; not part of the public API.
    private static final class SimpleContext implements PluginContext {
        private final PluginConfig config;
        private final EventPublisher events;
        private final Clock clock;

        private SimpleContext(PluginConfig config,
                              EventPublisher events,
                              Clock clock) {
            this.config = Objects.requireNonNull(config);
            this.events = Objects.requireNonNull(events);
            this.clock = Objects.requireNonNull(clock);
        }

        @Override
        public PluginConfig config() {
            return config;
        }

        @Override
        public EventPublisher events() {
            return events;
        }

        @Override
        public Instant now() {
            return clock.instant();
        }
    }

    private static final class ScopedPublisher implements EventPublisher {
        private final String pluginId;
        private final int quota;
        private int sent;
        private boolean active = true;

        private ScopedPublisher(String pluginId, int quota) {
            this.pluginId = Objects.requireNonNull(pluginId);
            this.quota = quota;
        }

        @Override
        public synchronized void publish(String message) {
            Objects.requireNonNull(message, "message");
            if (!active) {
                throw new IllegalStateException("service has been revoked");
            }
            if (message.length() > 120) {
                throw new IllegalArgumentException("message is too long");
            }
            if (sent >= quota) {
                throw new IllegalStateException("event quota exceeded");
            }

            sent++;
            System.out.println("[" + pluginId + "] " + message);
        }

        private synchronized void revoke() {
            active = false;
        }
    }

    private static final class GreetingExtension implements Extension {
        @Override
        public void start(PluginContext context) {
            context.events().publish(
                    context.config().greeting() + ", Lan @ " + context.now()
            );
            context.events().publish(
                    context.config().greeting() + ", Minh @ " + context.now()
            );

            try {
                context.events().publish("Third attempt");
            } catch (IllegalStateException ex) {
                System.out.println("Rejected: " + ex.getMessage());
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 PluginContextDemo.java
java PluginContextDemo
~~~

Output:

~~~text
[greeting] Hello, Lan @ 2026-01-01T00:00:00Z
[greeting] Hello, Minh @ 2026-01-01T00:00:00Z
Rejected: event quota exceeded
Rejected: service has been revoked
~~~

**Walkthrough:**

- The host constructs PluginConfig and ScopedPublisher, then passes only PluginContext to the extension. The extension never receives the global configuration object or a reference to any real broker.
- The first two publish calls succeed. The third call is rejected by the quota check inside ScopedPublisher, even though the plugin can still invoke the method on the interface.
- After the host calls `revoke()`, even a retained EventPublisher reference cannot be used to emit further messages through this adapter.
- The `now()` method goes through the contract and uses the Clock chosen by the host; time in this example is fixed for reproducible output.
- `synchronized` makes quota checking, counter incrementing, and permission revocation consistent across multiple threads within this example's scope. In production systems, avoid holding internal locks across slow external service calls or plugin callbacks.

Public types are nested inside one file so the example runs standalone. In a real project, place Extension, PluginContext, PluginConfig, and EventPublisher as public types in a **stable module/API JAR**; keep SimpleContext and ScopedPublisher on the host side. Never copy host implementation classes into plugins.

## 5. Integration Structure in a Real Plugin System

A typical initialization flow:

1. **Discover the extension** via manifest, ServiceLoader, or a host-supported plugin loader. Discovery only identifies candidates; it does not grant service access yet.
2. **Determine identity and policy from the host side**, such as verified pluginId, compatible API version, and the permission set granted by an administrator.
3. **Read configuration and construct a private view**: filter keys, apply defaults, validate types and ranges; refuse startup if required data is missing.
4. **Create scoped service adapters**: bind host-selected pluginId/tenantId, permit only approved operations, apply resource limits, and add auditing.
5. **Create the context and invoke lifecycle**: call `start(context)`, then serve plugin invocations. Do not hand over the entire service registry just because a plugin has a `start` method.
6. **Stop and clean up**: block new requests, cancel or await in-flight work per policy, revoke capabilities, close associated resources, and release references to support unloading.

Useful lifecycle states are typically `CREATED -> ACTIVE -> STOPPING -> CLOSED`. Specify clearly whether calls during `STOPPING` are rejected or allowed to finish, timeouts for in-flight tasks, and behavior when `stop` is called multiple times. A context should have a lifecycle bound to a single plugin session; avoid reusing an old adapter for a restarted session.

If the system supports multiple tenants or multiple concurrent sessions for the same plugin, scope must include tenant/session where appropriate. Never use a singleton adapter that accidentally shares permissions, quotas, or data across tenants.

## 6. Boundaries to Clarify

### Access Control and Data Safety Boundaries

- **Data minimization**: a plugin sees only configuration needed for approved functionality; avoid passing secrets, unnecessary personal data, or infrastructure objects holding credentials.
- **Never trust self-declared plugin parameters**: enforce resource and tenant authorization in the host. For instance, `DocumentReader.read(id)` must verify `id` belongs to the permitted set; do not check only at context creation and skip per-read checks.
- **Do not expose privilege-escalation methods**: an interface should offer only concrete business operations; never provide `getHost()`, `getApplicationContext()`, `getAllServices()`, `unwrap()`, or mutation rights on allowlists.
- **Track resource cost**: quotas, timeouts, payload sizes, concurrency limits, and memory budgets must align with host resources. Prevent one plugin from exhausting shared execution pools.
- **Keep errors safe**: messages returned to plugins must not expose connection strings, tokens, server file paths, or infrastructure stack traces. The host can still record internal audits under proper access controls.

If a plugin genuinely needs to interact with a credentialed service, prefer having the host perform the call rather than handing over raw credentials. If a dedicated token must be issued, enforce narrow permissions, short lifetimes, rotation plans, and prevent logging tokens.

### Technical Boundaries Do Not Equal Security Sandboxing

A constrained API reduces coupling and governs access paths **through that API**, but **is not a security sandbox for arbitrary Java code**. A plugin running in the same JVM can still call other Java APIs directly, open network sockets, access resources under the process's OS privileges, or use reflection depending on the environment. ClassLoader/module boundaries help organize code and class compatibility; they do not automatically erect a security wall against untrusted code. Do not rely on the Java Security Manager as a modern sandboxing mechanism.

For plugins from untrusted sources, evaluate running them in a **separate process or container** with controlled OS permissions, filesystem, network, resource limits, and IPC protocols. In that setup, the context can be modeled as configuration data plus RPC capabilities instead of passing direct Java object references.

## 7. Lifecycle, Asynchrony, and Scalability

When a plugin retains a context for background work, the host must clearly specify:

- Adapters continue checking `ACTIVE` state and permissions at **invocation time**, not solely in `start()`. Revoking access is a state transition that takes effect for subsequent requests.
- Whether tasks already running during `stop` are allowed to finish or must be canceled; if using an executor, provide cancellation, deadlines, and bounds on pending work.
- Thread-safety mechanics for quotas and state. The example above uses `synchronized` to keep counting accurate; systems doing I/O should separate state checks, quota updates, and network calls so locks are not held for long periods.
- Contexts must not contain resources whose lifetime is shorter than granted work; closed handles must fail with clear errors rather than silently executing in a new session.
- If policies are updated at runtime, services must reflect revocations/grants per contract. An immutable configuration snapshot does not replace dynamic policy checks inside services.

A slow, hung, or throwing plugin must be handled via timeouts, fault isolation, metrics, and recovery policies at the host boundary. Never allow callback failures from a plugin to disrupt the application's primary execution path.

## 8. Contract Versioning and Testing

When host and plugins can be released independently, interfaces, records, enums, exceptions, and service semantics are all part of the API whose compatibility must be managed. Specify minimum/maximum supported versions, policies for adding methods, defaults, and handling ungranted capabilities. Bump the contract version for breaking changes; prevent plugins from reaching into host internals to bypass the contract.

Test categories to include:

| Case | What to prove |
| --- | --- |
| Valid/missing/mistyped configuration | Host validates and builds the context properly or rejects startup with clear reasons |
| Plugin not granted a service | Capability is absent or calls are rejected in a controlled manner |
| Plugin attempts to read another tenant's resource | Host blocks at the actual read/write operation |
| Quota threshold reached | Subsequent calls are rejected, including concurrent calls |
| Plugin stopped | Old handles cannot continue performing operations through the host adapter |
| Configuration or policy reload | Snapshot/update/revocation semantics match the contract |
| Incompatible plugin version | Host fails at load time rather than waiting for runtime errors |
| Plugin throws exceptions or runs slowly | Host isolates faults, honors timeouts, and cleans up resources |

In plugin unit tests, EventPublisher can be replaced with a fake and `now()` with a fixed clock to test logic without spinning up real infrastructure. In host integration tests, use real adapters or test doubles that enforce **the same policies**, especially around permissions, quotas, and post-`revoke()` behavior.

## 9. Common Mistakes

1. **Passing the entire DI container/ApplicationContext to a plugin**: plugins can look up beans outside the contract, making compatibility and permission checks hard to preserve. Provide a dedicated facade/interface instead.
2. **Assuming an unmodifiable Map is completely safe**: `Map.copyOf` only locks the map structure, not mutable objects held as values. Use immutable value types or deep defensive copies across nested structures.
3. **Letting the plugin self-report its identity or tenant on each call**: creates spoofing risks. The host must bind identity inside the adapter and enforce resource checks server-side.
4. **Checking permissions only when constructing the context**: policies can change; check at the execution boundary and support revocation.
5. **Exposing unrestricted DataSource, ExecutorService, or HTTP client**: makes per-plugin quotas and auditing very hard to enforce. Wrap them in narrow services with explicit limits.
6. **Failing to define stop/unload**: stale service references keep getting invoked, threads leak, or tasks run into new sessions. Require explicit states, revocation, and cleanup.
7. **Confusing API constraints with malicious-code isolation**: interfaces do not stop a plugin from calling Java/OS APIs directly if running with the same privileges in the JVM; use process isolation when the threat model demands it.
8. **Coupling plugins to host implementation details**: internal changes break plugins. Maintain a separate API JAR, versioning, and contract tests.

## 10. Design Checklist

Before publishing a new PluginContext, clearly answer: which **configuration values** the plugin needs and how they must be validated; which **actions** it needs via services; **who supplies identity/scope**; **where and how often** permissions and quotas are checked; how **config updates, stop, timeouts, and concurrent calls** are handled; whether the API is **version-compatible** with released plugins; and whether the **isolation level** matches the trust level of the plugin code.

A well-designed context lets an extension accomplish its assigned work through a small, mockable, testable contract, while the host retains responsibility for authorization, policy enforcement, infrastructure ownership, and revoking capabilities when needed.