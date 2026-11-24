# Do Not Use Attributes to Expose Sensitive Data

## 1. Why Can ManagedAttribute Become a Data Leak Vector?

In Spring Framework JMX, `@ManagedAttribute` exposes a getter or setter as a **JMX attribute**. This is a useful mechanism for application management and observability: operators can read connection counts, cache state, warning thresholds, or running task counts from JConsole and other JMX tools.

However, that very ability to read runtime values creates a risk: **a seemingly harmless getter can leak secrets or sensitive data outside its intended authorization boundary**.

For example, a bean may hold:

- database passwords, API keys, access tokens, and refresh tokens;
- private keys, client secrets, or service account credentials;
- connection strings with embedded credentials;
- customer personal information, order contents, or user payloads;
- session IDs, cookies, `Authorization` headers, or authentication data;
- internal configuration that could help an attacker understand the system, such as a list of unprotected management endpoints.

If a getter returns those values directly and is exported as a JMX attribute, any client able to access the MBean can read them via `MBeanServerConnection.getAttribute(...)`. The data can appear in GUIs, monitoring scripts, logs, or configuration dumps.

**Core principle:** JMX is a privileged management plane. Every exported attribute must be treated as part of the management API and exposed only when there is a clear operational purpose.

## 2. Data Path from Spring Bean to JMX Client

Simple model:

```text
   Spring-managed bean
       |
       | @ManagedAttribute on getter
       v
   AnnotationMBeanExporter / MBeanExporter
       |
       | build metadata + register MBean
       v
   MBeanServer (ObjectName, MBeanInfo)
       |
       | getAttribute(...)
       v
   JConsole / JMX client / monitoring tool
       |
       +--> display, collect, log, cache, forward
```

When exposing an attribute, developers often only see a getter in Java code. On the JMX client side, however, that getter becomes part of **an externally accessible interface from outside the bean**, discoverable via `MBeanInfo`.

For a registered MBean, clients can read metadata:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() + " readable=" + attribute.isReadable()
    );
}
```

Metadata does not necessarily reveal the value; however, if an attribute is readable and the connector/client has access, the client can request the actual value.

**Just because data does not appear in the business UI does not mean it is not exposed.** A getter intended only for "debugging" but exported via JMX is still a separate data read path that must be controlled.

## 3. Unsafe Example: Exporting Entire Configuration

Consider the following bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "demo.config:type=PaymentConfig")
public class PaymentConfigMonitor {

    private final String apiKey;
    private final String endpoint;

    public PaymentConfigMonitor(PaymentProperties properties) {
        this.apiKey = properties.getApiKey();
        this.endpoint = properties.getEndpoint();
    }

    @ManagedAttribute
    public String getApiKey() {
        return apiKey; // UNSAFE
    }

    @ManagedAttribute
    public String getEndpoint() {
        return endpoint;
    }
}
```

Once the bean is exported properly, `ApiKey` is a readable attribute. A JMX tool does not need to go through the payment system's business authentication endpoints to retrieve that value.

Even though `apiKey` is `private final` and has no setter, this **does not protect the value from JMX**. Java modifiers govern access within code; `@ManagedAttribute` actively creates a new management interface.

In particular, **read-only does not mean confidential**. A read-only attribute prevents setting the value via JMX, yet still allows retrieving it. For secrets, read access is typically the biggest risk.

If a connection string looks like:

```text
jdbc:postgresql://db.internal:5432/orders?user=service&password=SECRET
```

exporting the raw string can also disclose credentials, even if the getter is merely named `getJdbcUrl()`. Inspect the **actual contents**, not just the method name.

## 4. Classifying Data Before Exposing Attributes

A useful design approach is to categorize values by operational purpose.

| Data Type | Example | How to Handle in JMX Design |
|---|---|---|
| Non-sensitive operational metrics | Request count, queue depth, cache hit count | Can export if needed |
| Aggregated state | `READY`, `DEGRADED`, `AUTH_CONFIGURED` | Prefer exporting as state |
| Configuration thresholds | Timeout, pool size, warning threshold | Export only with proper permissions and validation |
| Infrastructure identifiers | Hostname, endpoint, database name | Assess sensitivity and need; do not assume safe by default |
| Credentials/secrets | Password, access token, API key, private key | Do not export values |
| User data | Email, phone number, order contents | Avoid exporting; use aggregated statistics |
| Session data | Session ID, cookie, Authorization header | Do not export values |
| Error data | Exception message, raw payload, request body | Filter and bound before exporting |

There is no rule that "every URL is safe" or "every username is as sensitive as a password." Sensitivity depends on context, threat model, and operational requirements. However, for secrets and authentication data, the default design should be **never expose values under any attribute**.

A JSON record containing a configuration object must also be reviewed field by field. Exporting a `Map<String, Object>` or DTO does not automatically make data safer just because there is no dedicated `getPassword()` getter.

## 5. Replace Secrets with Useful Status Information

Operators rarely need to know the **value** of an API key. They only need to know:

- whether the key is configured;
- whether the key is expired, if the application knows the expiration date;
- whether the latest authentication check succeeded or failed;
- whether the subsystem is healthy or degraded;
- whether rotation is needed.

Instead of:

```java
@ManagedAttribute
public String getPaymentApiKey() {
    return properties.getApiKey();
}
```

provide status:

```java
@ManagedAttribute(description = "Whether payment credentials are configured")
public boolean isPaymentCredentialConfigured() {
    String key = properties.getApiKey();
    return key != null && !key.isBlank();
}
```

A better design can use a component holding verified state:

```java
public enum CredentialStatus {
    MISSING,
    CONFIGURED,
    VALIDATION_FAILED,
    READY
}
```

and export:

```java
@ManagedAttribute(description = "Payment credential readiness")
public String getCredentialStatus() {
    return credentialHealth.getStatus().name();
}
```

`CONFIGURED` does not mean `READY`: a non-empty key string might be expired or revoked. Therefore, name the attribute accurately for what is being measured.

**Optimal mindset:** export an operational signal sufficient for decision-making, avoiding exporting the raw data used to compute that signal.

## 6. A Safe, Applicable Spring Example

Suppose a system has a service communicating with a third party. Instead of having the JMX bean hold/expose the token, create an independent operational state class.

```java
// PaymentHealth.java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class PaymentHealth {

    public enum State {
        NOT_CONFIGURED, STARTING, READY, DEGRADED
    }

    private final AtomicReference<State> state =
        new AtomicReference<>(State.STARTING);

    private final AtomicReference<Instant> lastSuccess =
        new AtomicReference<>();

    public State currentState() {
        return state.get();
    }

    public Instant lastSuccessfulCheck() {
        return lastSuccess.get();
    }

    public void markReady() {
        lastSuccess.set(Instant.now());
        state.set(State.READY);
    }

    public void markDegraded() {
        state.set(State.DEGRADED);
    }

    public void markNotConfigured() {
        state.set(State.NOT_CONFIGURED);
    }
}
```

The MBean only reads the aggregated state:

```java
// PaymentOperationsMBean.java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
@ManagedResource(
    objectName = "demo.payment:type=PaymentOperations",
    description = "Operational status without credentials"
)
public class PaymentOperationsMBean {

    private final PaymentHealth health;

    public PaymentOperationsMBean(PaymentHealth health) {
        this.health = health;
    }

    @ManagedAttribute(description = "Payment subsystem state")
    public String getState() {
        return health.currentState().name();
    }

    @ManagedAttribute(description = "Last successful health check epoch millis")
    public long getLastSuccessEpochMillis() {
        Instant last = health.lastSuccessfulCheck();
        return last == null ? -1L : last.toEpochMilli();
    }

    @ManagedAttribute(description = "Whether payment subsystem is ready")
    public boolean isReady() {
        return health.currentState() == PaymentHealth.State.READY;
    }
}
```

The bean above does not need to hold passwords or tokens; it only depends on a state holder. The `lastSuccess` state is updated by business code or health checking **in the appropriate place**, not inside the JMX getter itself. Getters return quickly without making network calls every time a client refreshes.

For these annotations to be exported in plain Spring Framework, enable the corresponding configuration, such as:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Appropriate configuration and dependencies for your Spring version are required; in Spring Boot, JMX auto-configuration has dedicated settings like `spring.jmx.enabled`. A standalone `@Component` does not guarantee an MBean appears.

This is an **allowlist** pattern: only specific, purposeful getters are annotated with `@ManagedAttribute`. Classes holding secrets in the configuration layer are not exported directly.

## 7. Allowlist: Expose Only Strictly Necessary Getters

The safest strategy for management MBeans is **explicitly selecting the attributes to expose**, rather than scanning all bean state or returning an uncontrolled composite DTO.

For example, a business class has:

```java
class ConnectionSettings {
    private String endpoint;
    private String username;
    private String password;
    private int connectTimeoutMillis;
    private int maxConnections;
}
```

Do not export the entire `ConnectionSettings` over JMX. Create a narrow view:

```java
@ManagedAttribute
public int getConnectTimeoutMillis() {
    return settings.getConnectTimeoutMillis();
}

@ManagedAttribute
public int getMaxConnections() {
    return settings.getMaxConnections();
}
```

Even `endpoint` and `username` should be evaluated for whether operators truly need them. Seemingly non-secret information can help infer topology, service account names, or environments.

**Do not use automatic reflection or expose all getters indiscriminately.** A DTO initially containing only non-sensitive data might have a `token` field added in the future. If the whole DTO is exported, a domain change can inadvertently expand the JMX surface without anyone actively approving it.

Every new attribute should be treated as a management API change.

## 8. Why Is Simple Masking Still Risky?

Many codebases try to "hide" secrets by returning partial characters:

```java
@ManagedAttribute
public String getMaskedApiKey() {
    String key = properties.getApiKey();
    return "****" + key.substring(key.length() - 4);
}
```

There are several issues:

- Short secrets can throw an exception if length is not checked.
- Partial prefixes/suffixes may still aid correlation or credential identification.
- Combining multiple "masked" values can leak additional information.
- Calling `getApiKey()` inside a JMX getter expands the code paths touching credentials.
- Operators rarely need the last few characters to evaluate system health.

If there is a need to verify rotation or key version, prefer a **non-secret version identifier** issued separately by the system, such as `credentialVersion=2026-11` or a `rotationRequired` status. Do not assume hashing a secret is guaranteed safe; digests can aid identification, correlation, or be attacked if the input has low entropy.

Masking may fit certain purpose-built diagnostic UIs, but it does not replace the principle of minimizing data exposed via JMX.

## 9. Distinguishing Read-Only, Write-Only, and Read-Write

A JMX attribute has `isReadable()` and `isWritable()` metadata. Understand clearly:

| Attribute Type | Read via JMX | Write via JMX | Primary Risk |
|---|---|---|---|
| Read-only | Yes | No | Exposing existing data |
| Write-only | No | Yes | Unintended state changes |
| Read-write | Yes | Yes | Both data exposure and modification |

**Making a secret read-only is unsafe.** It is still readable.

**Making a secret write-only is not safe by default either.** A setter accepting an API key over JMX creates a secret transport path requiring strict governance. Secrets can leak in the invoking tool, connection, logs, or handling code. If the application needs rotation, use a secret manager or dedicated security workflow, not an MBean setter by default.

**Read-write for secrets is especially dangerous:** authorized clients can read and change credentials. Restricting connection permissions reduces risk but does not address unnecessary data exposure.

For ordinary operational configuration, read-write may be appropriate with validation and protection; for example, thresholds or logging levels. Keep those parameters separate from authentication credentials.

## 10. Not Only Passwords: Indirect Data Is Also Sensitive

Some leak paths do not carry obvious names:

### 10.1. Exception Messages

```java
@ManagedAttribute
public String getLastError() {
    return lastException.getMessage();
}
```

Errors from HTTP clients, database drivers, or SDKs can contain endpoints, usernames, queries, request metadata, or configuration info. An exception message generated by a library is not sanitized data.

Replace with an error category or stable status code:

```java
@ManagedAttribute
public String getLastFailureCategory() {
    return failureState.getCategory().name();
}
```

If debugging details are required, send them to logging with appropriate redaction and separate access controls. Do not assume logs are safe by default; logs can also leak if raw payloads are written.

### 10.2. Object.toString()

```java
@ManagedAttribute
public String getConfigurationSummary() {
    return configuration.toString();
}
```

If `toString()` is auto-generated by records, Lombok, or an IDE, it may include `password` or `clientSecret` fields. Changes to the class can also alter the summary contents without touching the JMX getter.

Replace with an explicit string of specific components:

```java
return "timeoutMillis=" + config.getTimeoutMillis()
    + ", poolSize=" + config.getPoolSize();
```

Even those fields must be reviewed against operational necessity.

### 10.3. DTOs or Maps Containing Raw Data

```java
@ManagedAttribute
public Map<String, String> getAllProperties() {
    return systemProperties;
}
```

A "convenient" map may hold credentials or sensitive paths. With MXBeans, maps/DTOs may be mapped to `TabularData` or `CompositeData`; changing representation does not make the underlying data less sensitive.

Only export DTOs specifically designed for observability with a stable set of fields.

### 10.4. Thread Dumps, System Properties, and Environment

Diagnostic APIs can reveal stack traces, JVM arguments, environment variables, or system properties. These sources sometimes contain secrets if applications pass credentials via command-line flags or improper configuration.

Do not create custom MBeans to export all of `System.getenv()`, `System.getProperties()`, or the full JVM argument list. At the same time, when securing remote JMX, remember that certain platform MXBeans already provide diagnostic information: merely removing custom sensitive getters is not enough to declare the entire JMX surface free of protected data.

## 11. Local vs. Remote JMX Have Different Risk Levels

Local JMX typically relies on OS/process access permissions and attach mechanisms. Someone permitted to interact with a local JVM may have many other diagnostic capabilities outside JMX. However, that does not make every attribute safe: information can still be copied, logged, or forwarded into other tools.

Remote JMX has a larger attack surface. Depending on deployment, it may use RMI and require configuring endpoints, ports, TLS, authentication, and authorization. Never expose a JMX management port publicly to the Internet or deploy test configurations with security disabled in production.

Key principles:

1. Prefer a dedicated management network or controlled access channel.
2. Enable authentication and transport encryption for remote access.
3. Apply least privilege: monitoring accounts should only have required capabilities.
4. Restrict exported MBeans, attributes, and operations by purpose.
5. Audit management changes, especially operations and writable attributes.
6. Manage credential lifecycles in the appropriate place; do not use JMX as a secret store or display channel.
7. Check auto-export/collection behavior of monitoring tools to prevent sensitive data from being copied into metrics/log storage.

Do not assume every JMX connector has fine-grained per-attribute RBAC. Authorization mechanisms depend on the actual server, connector, and configuration. Therefore, **data minimization right at the MBean layer** remains a vital safeguard.

## 12. Monitoring Tools Can Also Propagate Data

Even if only one management client has read permission, that client can:

- automatically scrape attributes periodically;
- store raw values in log files or caches;
- export metrics to a centralized backend;
- forward data through intermediary gateways/agents;
- display values in dashboards viewable by many people.

This is why you cannot only ask "who is allowed to open JConsole?". You must ask **where the data goes after it is read**.

For example, an exporter that automatically collects every `String` attribute could place `ApiKey` into labels or diagnostic payloads. Adding a sanitization step on the monitoring side can reduce risk, yet the application source still should not export credentials.

Defense-in-depth design:

```text
Application bean
   |
   +--> Do not export sensitive data
   |
MBeanServer / JMX connector
   |
   +--> Authentication, encryption, network restrictions, and permissions
   |
Monitoring collector
   |
   +--> Metric allowlist, redaction, label/payload limits
   |
Storage / Dashboard
   |
   +--> Access permissions, retention, audit
```

A failure at a downstream layer should not expose unnecessary secrets that were already published by an upstream layer.

## 13. Designing Safe Metadata and Attribute Names

Attribute names themselves are metadata discoverable by clients. Do not embed customer IDs, tokens, or secrets in names, such as:

```text
ApiKey_abc123SECRET
SessionToken_<raw value>
```

Use stable, descriptive names:

```text
PaymentCredentialConfigured
PaymentState
ConnectionPoolActive
LastSuccessfulHealthCheckEpochMillis
```

Descriptions in `@ManagedAttribute(description = "...")` are also public metadata visible to JMX clients; avoid inserting secret contents, sensitive internal URLs, or runtime values into descriptions.

If per-tenant or per-account information is needed, consider exporting aggregated statistics instead of creating an ObjectName/attribute per user. ObjectNames containing sensitive user IDs are also a metadata leak vector.

## 14. Auditing the List of Exposed Attributes

Reviews should be based on **actual `MBeanInfo`**, because exporting via Spring annotations, Standard MBeans, or MXBeans can produce different interfaces.

A Java snippet to inventory names and read/write flags:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("demo.payment:type=PaymentOperations");

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s, type=%s, readable=%s, writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
```

The snippet requires importing `java.lang.management.ManagementFactory`. It reads metadata only; it does not print attribute values. In production, avoid "security checks" that automatically read and dump all JMX values to stdout.

For custom MBeans, inventory names such as `Password`, `Token`, `Secret`, `Authorization`, `Cookie`, `PrivateKey`, `JdbcUrl`, `Environment`, `Properties`, and `DebugContext`. These are indicators to investigate, not exhaustive criteria: an attribute named `Info` could contain a secret, while an attribute named `TokenConfigured` returning only a boolean may be completely sound.

Inspect the returned data type, the value's origin, and its path to clients. A safe name does not prove safe contents.

## 15. Do Not Let Operations and Notifications Become Leak Bypasses

This lesson focuses on `ManagedAttribute`, but JMX also has `@ManagedOperation` and notifications. If you do not export a token via a getter, yet have:

```java
@ManagedOperation
public String dumpConfiguration() {
    return configuration.toString();
}
```

sensitive data can still be read via an operation. Similarly, `Notification.setUserData(...)` can deliver raw requests or secrets to listeners.

Therefore, when designing the management surface, audit everything:

- Readable attributes.
- Operations with return values.
- Exception/error messages emitted by operations or getters.
- Notification payloads, `userData`, and messages.
- ObjectNames, descriptions, and open metadata.

Not all administrative information should travel over JMX. An action like credential rotation usually requires a dedicated secrets management system, auditing, authorization, and verification workflow.

## 16. Real-World Scenario: Debugging Payment Connection Failures

Suppose a payment gateway repeatedly returns `401 Unauthorized`. Operators want to know whether the key is right or wrong. There are two design approaches:

**Risky approach:**

```java
@ManagedAttribute
public String getApiKey() {
    return paymentProperties.getApiKey();
}
```

Operators can view the key, but at the same time every client permitted to read that attribute can retrieve the credential. A debugging aid increases secret exposure.

**More appropriate approach:**

```java
@ManagedAttribute
public boolean isCredentialConfigured() {
    return paymentHealth.isConfigured();
}

@ManagedAttribute
public String getAuthenticationStatus() {
    return paymentHealth.getAuthenticationStatus().name();
}

@ManagedAttribute
public long getLastSuccessfulAuthenticationEpochMillis() {
    return paymentHealth.getLastSuccessEpochMillis();
}
```

Combined with redacted logging and a diagnostic code/correlation ID, operators can tell that a credential exists, authentication is failing, and when it last succeeded. If the secret needs changing, perform it via the secret management pipeline rather than reading secrets via JMX.

The difference is **observing the outcome of using a credential**, instead of exposing the credential itself.

## 17. Common Mistakes When Protecting JMX Attributes

### 17.1. "Read-only so it's safe"

Wrong. Read-only attributes can still be read via `getAttribute`. That is the exact leak path for secrets.

### 17.2. "The MBean only runs locally, no need to check data"

Insufficient. Local access is still a privilege boundary, and data can be copied to other clients/monitoring tools. Not exporting secrets remains the right principle.

### 17.3. "I masked the last four characters"

Masking can still reveal credential identifiers or correlatable data. Prefer non-sensitive state/version identifiers issued separately by the system.

### 17.4. "Returning a Map won't leak anything"

Maps and DTOs can hold many sensitive fields; MXBeans can even map them to easily discoverable OpenData. Inspect the contents, not just the data type.

### 17.5. "The getter is only for debugging, nobody uses it"

Once a getter is exported, management tools or automatic exporters can discover and read it. Do not treat a "debug" label as a security control.

### 17.6. "Having no password in code is enough"

Secrets can come from the environment, config servers, vaults, system properties, or SDK runtimes. What the getter returns is what matters.

### 17.7. "Using a write-only setter to rotate keys is enough"

Sending secrets via a JMX setter still requires authorization, transport protection, log controls, and a rotation workflow. Write-only does not guarantee a secure channel.

### 17.8. "I only exported the error status"

Error status can contain raw exception messages, request URLs, usernames, or request bodies. Design aggregated error codes rather than returning raw error objects.

## 18. Practice Exercises

**Exercise 1 — Spot Risks in an MBean:**

```java
@ManagedResource(objectName = "demo:type=Config")
public class ConfigMonitor {

    @ManagedAttribute
    public String getApiKey() { return config.getApiKey(); }

    @ManagedAttribute
    public String getLastError() { return error.getMessage(); }

    @ManagedAttribute
    public int getConnectTimeoutMillis() {
        return config.getConnectTimeoutMillis();
    }
}
```

Classify each getter; fix the bean to retain only purposeful operational state and configuration. For `LastError`, use a standardized enum error code instead of the raw exception message.

**Exercise 2 — Design a Status Without Revealing Keys.** Create `CredentialStatus` with values `MISSING`, `CONFIGURED`, `INVALID`, `READY`. Export `getCredentialStatus()` and `getLastValidationEpochMillis()`. Explain why these two attributes serve operations better than `getSecret()`.

**Exercise 3 — Inventory Metadata.** Register a Spring MBean, use `MBeanServer.getMBeanInfo()` to list attribute names and types without reading values. Cross-check against `@ManagedAttribute` annotations in code.

**Exercise 4 — Risks from toString().** Create a DTO `ConnectionInfo` with `host`, `username`, `password`, and `poolSize`. Write a getter returning `info.toString()`, identify the risk, then replace it with a summary exposing only `poolSize` and connection status.

**Exercise 5 — Separate Observation and Control.** Design an MBean with `getCredentialStatus()` (read-only) and `refreshCredentialStatus()` (an operation requesting re-validation without printing secrets). Explain why the operation should not return tokens or raw exceptions on failure.

**Exercise 6 — Check Path to Monitoring.** Suppose a JMX exporter automatically scrapes all attributes. Create an allowlist containing only `PaymentState`, `ConnectionPoolActive`, and `PaymentErrorsTotal`, and explain why `Configuration`, `Environment`, and `LastRequest` should not be scraped.

## 19. Self-Check Questions

1. How does `@ManagedAttribute` on a getter alter the data access surface?
2. Why is `private final String apiKey` insufficient protection if a getter is exported?
3. Are read-only and confidential the same concept?
4. How does a `CredentialConfigured` status help operations?
5. Why should you avoid exporting entire configuration objects or property maps?
6. What types of sensitive information can an exception message contain?
7. Is masking part of a token always safe?
8. What can MBean metadata reveal without reading attribute values?
9. Why does securing the remote connector not replace minimizing exported data?
10. Besides attributes, what other JMX channels can leak information?

## 20. Key Takeaways

**ManagedAttribute is a promise to expose data over JMX.** Export only attributes genuinely needed for operations; never expose passwords, API keys, tokens, user data, raw exceptions, or uncontrolled composite configurations. Replace them with purpose-built statuses, metrics, error codes, and aggregated signals.

Security comes from restricting data right at the source, combined with connector protection, access permissions, auditing, and monitoring pipeline controls. When an attribute does not need to reveal raw values to support operational decisions, export **the observed outcome** rather than **the sensitive data that produced it**.
