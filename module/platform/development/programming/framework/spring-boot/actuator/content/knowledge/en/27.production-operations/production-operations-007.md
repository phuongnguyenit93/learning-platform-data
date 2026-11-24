# Managing Personal Data, Retention Periods, and Read Permissions for Logs, Traces, or Dumps

> Scope: operating Spring Boot Actuator 3.3.x applications. Configuration snippets are technical examples; retention periods in this article belong to a hypothetical policy and must be re-determined based on intended use and requirements applicable to the real system.

## 1. Diagnostic Data Must Also Be Managed Like System Data

Logs help explain events, traces help connect operations across services, and dumps help analyze process state. They are created to support operations yet can contain data from requests, business objects, login sessions, or configuration.

A typical incident: an application does not store email addresses in a business log table, yet an exception puts the entire customer object into the message. Logs are copied to a centralized system; an investigator also downloads a heap dump to a personal machine. The main application's data policy does not yet govern those copies.

The problem comprises three related decisions:

| Decision | Questions to answer |
| --- | --- |
| Collection and data minimization | Which fields truly need to be kept for investigation? Can collecting sensitive parts be avoided? |
| Retention period | Until when is the data needed, from which timestamp is it measured, and in which places is it deleted? |
| Read permissions | Who may view which data type, for which service/tenant/incident scope, and until when? |

Restricting read permissions does not fix over-collection. Encryption does not make data expire. Masking a value in a UI also does not prove the original has been removed.

## 2. Classifying Each Data Type Before Granting Permissions

| Type | Content that may appear | Points to control |
| --- | --- | --- |
| Application logs | Error messages, business attributes, request or exception information | Logged content, query permissions, and downloading whole files |
| Traces | Span attributes, operation names, URLs, correlation IDs, and errors | Attributes, error events, export destinations, and linkage scope |
| Thread dumps | Call stacks, class/method names, thread names, lock info | Thread names or custom details may also contain internal data |
| Heap dumps | Objects and strings currently residing in heap memory | May contain personal data, tokens, or secrets never written to logs |

A thread dump is not a copy of the entire heap; a heap dump also does not contain only log lines. Therefore, do not apply the same permission level and retention period to every type by default.

Actuator exposes heapdump via a dedicated endpoint. On the JVM side there are also independent diagnostic tools, such as jcmd or JMX; disabling the HTTP path does not automatically remove those paths. [HeapDumpWebEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/management/HeapDumpWebEndpoint.html), [JDK 21 diagnostic tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).

Personal data is not only full names or email addresses. A customer ID, IP address, URL containing identifiers, or correlation ID can link to a person when combined with other data. Replacing a name with an ID does not by itself prove the data is anonymous.

## 3. Minimizing Data Before It Enters Storage

### Choosing Allowed Fields to Record

Prefer a structured event and include only selected fields. Illustrative example using synthetic data:

```json
{
  "event": "order_lookup_failed",
  "service": "orders-api",
  "environment": "production",
  "route": "/api/orders/{id}",
  "outcome": "dependency_timeout",
  "durationMs": 143,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Routes are recorded as templates instead of copying order IDs into the path. Error codes are categorized instead of dumping raw responses from another system into the message. traceId helps correlation lookups yet still needs protection according to the system's data-linkage risk.

Items that usually need to be excluded from logs include passwords, access tokens, secret keys, session cookies, and personal data that does not serve the logging purpose. Also encode output in the proper format and handle control characters so input data cannot forge fake log lines. [OWASP logging guide](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

### Do Not Just Look for a Few Key Names to Mask

Data leakage paths can fall outside familiar filters:

- Exceptions containing the raw request, SQL statements with bound values, or third-party responses.
- Business object `toString` methods containing customer information.
- Query strings, span names, or thread names constructed from input data.
- Log-shipper queue files storing raw copies before the collector processes them.
- Data placed into common attributes that then propagates across many events.

An allowlist of allowed fields is usually easier to verify than hoping a regular expression catches every form of sensitive data. Filtering at the application before writing helps reduce raw copies; the collector can add another filtering layer. Check actual outputs of both layers. [Handling sensitive data in OpenTelemetry](https://opentelemetry.io/docs/security/handling-sensitive-data/).

If hashing is used to correlate events by user, assess guessability and cross-linkage risks. Hashing a predictable dataset does not mean anonymization; the hashed values themselves still need appropriate access and storage policies.

### Traces and Baggage

Inspect span names, attributes, events, and exception messages alike. Lowering the trace sampling rate only reduces data volume; it does not remove sensitive parts from traces that are still sampled.

Baggage can be propagated over HTTP to other services, including outbound calls outside the system. Do not use it as an arbitrary bag for emails, tokens, or personal information. Baggage also has no built-in integrity check to be trusted as an authorization source. [OpenTelemetry Baggage security considerations](https://opentelemetry.io/docs/concepts/signals/baggage/#baggage-security-considerations).

## 4. Understanding Actuator's Protection Boundaries Accurately

Three layers to distinguish are: whether an endpoint is enabled, whether it is exposed over HTTP/JMX, and whether the caller is authorized to read it. In Spring Boot 3.3, enabling/disabling endpoints uses the enabled property; exposing an endpoint does not replace authorization checks. [Spring Boot 3.3 endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

A reference configuration enabling only health and prometheus:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,prometheus
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
    prometheus:
      enabled: true
    env:
      show-values: never
    configprops:
      show-values: never
    quartz:
      show-values: never
```

This snippet merges into an application that already has the required dependencies, including the Prometheus registry if that endpoint is used. Remaining endpoints are not enabled by the chosen default configuration. Excluding from JMX here applies only to Actuator endpoints, not all custom MBeans.

In Spring Boot 3.3, env/configprops/quartz support value masking via show-values. This mechanism applies to responses from those endpoints; it does not re-scan logs, spans, or objects in the heap.

In particular, when-authorized must be evaluated together with roles configuration and the authentication mechanism. Do not infer that every signed-in user should read raw configuration just because they can access the application.

logfile reads log file contents; loggers can change logging levels. These are two different permissions. Allowing a logger to be switched to DEBUG can increase the amount of data collected, so permission to modify observability configuration needs to be managed separately from permission to view metrics.

An endpoint not appearing over HTTP also does not prove dumps will not be created: JVM out-of-memory dump settings, OS tools, or diagnostic operations must still be controlled at the platform layer.

## 5. Granting Read Permissions by Resource, Scope, and Expiration

Authentication answers who the caller is; authorization decides what they may do with which resource. Default-deny and checking on every request prevent a single link or ID from becoming a read path to the entire store. [OWASP authorization guide](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

A reference permission matrix:

| Principal | Permanent permissions that may be granted | Permissions requiring separate grant |
| --- | --- | --- |
| Metrics collector | Read selected metrics endpoints of the service | Does not inherit read access to logs, traces, or dumps |
| Developer | Query minimized logs for assigned service/scope | Detailed production data or bulk data export |
| Incident responder | Read logs/traces within incident scope and needed time window | Heap dumps or high-sensitivity raw copies |
| Store administrator | Manage configuration and lifecycle per duties | Does not by default imply reading all contents |

The matrix is a design example, not a mandatory role list. Separate at least these actions: querying, viewing a single record, downloading files, bulk exporting, creating dumps, changing log levels, and deleting data.

For multi-tenant systems, check tenant on the server side for every resource and every query. Do not trust a tenant filter sent by the browser as proof the user has permission. Nor should permission to read one trace default to opening every log or dump sharing the same incident ID.

### Example Protecting Actuator HTTP Paths

The Java snippet below is for a Servlet application using Spring Security and OAuth2 Resource Server JWT. It requires a valid JwtDecoder configured from the project's authentication mechanism, such as via a verified issuer-uri.

In the example, health exposes only status; prometheus requires scope metrics.read. Other Actuator endpoints and all remaining paths are denied. This is an intentionally illustrative configuration and does not contain a complete application's business API access policies.

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class OperationalReadSecurity {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .requestMatchers(EndpointRequest.to("prometheus"))
                .hasAuthority("SCOPE_metrics.read")
            .anyRequest().denyAll());
        http.oauth2ResourceServer(oauth -> oauth.jwt(withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
```

EndpointRequest selects endpoints by Actuator location rather than relying solely on hardcoded paths. When providing a SecurityFilterChain yourself, you must also cover non-Actuator requests; hence the example includes a second chain. [EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html), [Securing HTTP endpoints in Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

With default JWT scope mapping, metrics.read corresponds to authority SCOPE_metrics.read. Do not assume this scope is present in every token or every customized converter. [Resource Server JWT scope mapping](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html#oauth2resourceserver-jwt-authorization).

This configuration protects the application ingress; read permissions on log/trace stores, files inside containers, object storage, and host management paths must still be enforced at those exact places.

## 6. Building Retention Periods Across the Entire Lifecycle

Retention periods must accompany purpose, start timestamp, where applied, deletion method, and owner. Copies in queues, exports, and backups also belong to the diagnostic data lifecycle. [Log lifecycle management per NIST SP 800-92](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-92.pdf).

Hypothetical policy for discussion:

| Data group | Illustrative retention | Primary enforcement point |
| --- | --- | --- |
| Minimized operational logs | 7 days | Centralized log store and all copies per policy |
| Attribute-filtered traces | 3 days | Trace store and related queues/exports |
| Heap dump for an incident | 24 hours from creation | Diagnostic store with dedicated read permissions |
| Access audit trail | A separate policy per audit purpose | Audit store with separated modify/delete permissions |

The numbers above are not Spring Boot defaults and do not define a universal retention period for every system.

### Start Timestamp Must Be Defined

You can choose event time or system ingestion time, yet you must document the choice and handle late-arriving data. For dumps, creation time and expiresAt can be stored in resource metadata.

When copying or re-exporting, preserve the data's original expiration deadline; do not accidentally start a fresh retention period just because a copy was ingested into another system. If using timestamps from an untrusted source, validate them rather than letting the source extend retention itself.

### Verifying Every Place Data May Still Exist

1. Active files and rotated files on hosts/containers.
2. Buffers or persistent queues of agents/collectors.
3. Indexes, primary stores, and cold storage tiers of centralized systems.
4. Object storage, old object versions, and backup copies.
5. Exported files, analysis machines, investigation tools, and temporary files.

Encryption at rest and in transit protects content but does not replace TTL, read permissions, or deletion procedures. Deleting a search index also does not prove the original in object storage is gone.

If an exception is needed to preserve data for investigation, it must have a scope, justification, owner, and dedicated review date; do not turn exceptions into indefinite retention. For immutable stores or backups that cannot be selectively deleted, define access controls, expiration timelines, and handling during data restoration.

## 7. Local Log Rotation Is Not a System-Wide Retention Policy

The following example is for an application using Logback configuration managed by Spring Boot, deployed with Linux-style file paths:

```yaml
logging:
  file:
    name: /var/log/orders-api/application.log
  logback:
    rollingpolicy:
      file-name-pattern: /var/log/orders-api/archive/application.%d{yyyy-MM-dd,UTC}.%i.log.gz
      max-file-size: 10MB
      max-history: 7
      total-size-cap: 1GB
      clean-history-on-start: true
```

Spring Boot provides rollingpolicy properties to configure log file storage. If the project has a custom logback-spring.xml, verify whether the actual appender uses these values. [Spring Boot 3.3 logging configuration](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.file-rotation).

With the date pattern above, max-history is interpreted in rollover periods of the rolling policy; it does not guarantee every record exists for exactly 7 times 24 hours. %i allows multiple files within the same period when hitting the size limit.

Logback cleans archives according to the rolling mechanism and asynchronous handling; the active file, when new events arrive, and total size limits all need consideration. total-size-cap can cause older archives to be deleted earlier than the age limit. [Logback rolling mechanism and maxHistory](https://logback.qos.ch/manual/appenders-rolling.html).

Therefore, verify both sides: do not retain longer than policy allows, and do not lose data before the minimum required retention. Insufficient disk capacity should not be hidden by silently altering retention goals.

These settings do not set retention for traces, heap dumps, stdout collected by the platform, centralized log stores, or backup copies.

## 8. Managing Dumps Case by Case

A heap dump can include data that never passed through any log filter. Do not rely on logs masking passwords to conclude dumps contain no secrets. Nor should you use a few string replacements as a guarantee that an entire binary dump file is sanitized.

A reference workflow:

1. Define the investigation question and check whether less sensitive data is already sufficient.
2. If a dump is needed, record the exact service/instance, incident, owner, and assess creation impact.
3. Store in a location with encryption, dedicated read permissions, classification metadata, and an expiration deadline.
4. Grant time-bound access to the right person and resource; analyze in a controlled environment.
5. Log reads/downloads/exports and verify deletion of copies when the purpose ends or retention expires.

Permission to create a dump differs from permission to read an existing dump. Permission to read metadata also does not necessarily include permission to download the entire content.

Do not move a production dump to another analysis system merely because that tool can open the file. First verify that the destination is permitted to receive that data classification and preserves access, retention, and copying constraints.

## 9. Java Illustration: Read Expiration and Retention Expiration Are Two Independent Conditions

The following program uses hypothetical metadata. Artifact is a diagnostic resource; ReadGrant describes a scoped read permission. Valid intervals include the start timestamp and exclude the end timestamp.

Resource metadata must come from a trusted store; a grant must be tied to an authenticated principal and issued by an authorization service. Callers must not submit a ReadGrant themselves to grant themselves access. The example only verifies condition logic; it does not replace an authentication, auditing, or file-deletion system.

File DiagnosticAccessDemo.java:

```java
import java.time.Instant;
import java.util.Set;

public class DiagnosticAccessDemo {
    record Artifact(String id, String tenant, Instant createdAt,
                    Instant expiresAt) {
        Artifact {
            if (!createdAt.isBefore(expiresAt)) {
                throw new IllegalArgumentException("Invalid retention window");
            }
        }
    }

    record ReadGrant(String tenant, Set<String> readableIds,
                     Instant validFrom, Instant validUntil) {
        ReadGrant {
            readableIds = Set.copyOf(readableIds);
            if (!validFrom.isBefore(validUntil)) {
                throw new IllegalArgumentException("Invalid grant window");
            }
        }
    }

    static boolean mayRead(Artifact artifact, ReadGrant grant, Instant now) {
        return artifact.tenant().equals(grant.tenant())
            && grant.readableIds().contains(artifact.id())
            && !now.isBefore(artifact.createdAt())
            && now.isBefore(artifact.expiresAt())
            && !now.isBefore(grant.validFrom())
            && now.isBefore(grant.validUntil());
    }

    public static void main(String[] args) {
        Instant created = Instant.parse("2026-11-06T09:00:00Z");
        Instant expires = Instant.parse("2026-11-07T09:00:00Z");
        Artifact dump = new Artifact("dump-42", "tenant-a", created, expires);
        Artifact otherId = new Artifact("dump-43", "tenant-a", created, expires);
        Artifact otherTenant = new Artifact(
            "dump-42", "tenant-b", created, expires
        );

        ReadGrant shortGrant = new ReadGrant(
            "tenant-a", Set.of("dump-42"),
            Instant.parse("2026-11-06T09:30:00Z"),
            Instant.parse("2026-11-06T11:00:00Z")
        );
        Instant now = Instant.parse("2026-11-06T10:00:00Z");

        System.out.println("authorizedNow=" + mayRead(dump, shortGrant, now));
        System.out.println("otherArtifact=" + mayRead(otherId, shortGrant, now));
        System.out.println("otherTenant=" + mayRead(otherTenant, shortGrant, now));
        System.out.println("atGrantDeadline="
            + mayRead(dump, shortGrant, shortGrant.validUntil()));

        ReadGrant laterGrant = new ReadGrant(
            "tenant-a", Set.of("dump-42"),
            Instant.parse("2026-11-07T08:00:00Z"),
            Instant.parse("2026-11-07T10:00:00Z")
        );
        System.out.println("atRetentionDeadline="
            + mayRead(dump, laterGrant, dump.expiresAt()));
    }
}
```

Compile and run with JDK 21 or later:

```powershell
javac --release 21 -encoding UTF-8 DiagnosticAccessDemo.java
java DiagnosticAccessDemo
```

Stdout:

```text
authorizedNow=true
otherArtifact=false
otherTenant=false
atGrantDeadline=false
atRetentionDeadline=false
```

The example demonstrates:

- A currently valid grant opens only the granted resource within the right tenant.
- At the exact validUntil timestamp, the temporary grant no longer permits reading.
- A grant issued on a later day does not automatically extend the data's expiresAt.

The function returning false at expiresAt blocks reads under the example's policy. It does not prove physical data has been deleted. Data-cleanup jobs must be executed and verified separately. Evaluation clocks and time metadata must also remain consistent.

## 10. Auditing and Data Export Paths

A read action should leave a trail sufficient to know who, what action, which service/tenant/resource, when, under which grant or incident, and what outcome. Avoid copying sensitive payloads into the audit record itself.

Govern bulk export permissions and download-link sharing as well. For pre-signed URLs, link lifetime should not exceed grant expiration or resource expiration; do not assume closing a UI revokes an already-issued link.

Verify revocation capability at the actual store/gateway, caching policies, and link issuance durations. An already-downloaded copy does not vanish when server-side permissions expire; that copy must still be managed within the data lifecycle.

Separate permissions to write data, read data, and delete audit trails whenever possible. Review permanent and temporary permissions after incidents, rather than checking only when a user first joins the system.

If a token or data that should not be logged is discovered, fix it at the source, identify where it was copied, and restrict access scope. If it is an exposed authentication secret, handle the lifecycle of that secret; deleting a log line does not invalidate a token.

## 11. Testing with Synthetic Data Before Putting into Operations

| Test case | Result to prove |
| --- | --- |
| Request with fake secret field and exception containing business object | That content does not appear in logs, spans, or collector output outside policy |
| Principal with metrics-only permission | Cannot read logs, traces, or dumps via other paths |
| Principal with right role but wrong tenant or wrong ID | Denied on the server side |
| Temporary grant expired | New read requests are rejected; also evaluate issued download links |
| Data expired | Unreadable via index, primary store, or exports outside policy; deletion evidence exists |
| Log size cap hit | Early deletion is evaluated, not confused with guaranteed full-period retention |
| Restoring a backup copy | Expired data is not accidentally reopened as fresh data |
| Changing log level to DEBUG | Access control is enforced and additional collected data is checked |

For Actuator, test against enabled/exposed configuration and actual security filters. A single 401, 403, or 404 status code is not enough to prove all other read paths are locked down. For retention, merely seeing a file vanish from one UI is not enough either.

## 12. Self-Practice

1. Draw the path of a log entry from the application to where an investigator downloads an export. Note who is accountable for read permissions and expiration at each point.
2. If env.show-values=never yet logfile still returns a token that was written to the log, explain why the two behaviors do not contradict each other.
3. Add a check to the Java program for timestamps before validFrom. Explain why that check differs from retention expiration.
4. A dump expires after 24 hours, yet a download URL was issued for 48 hours. Identify which layers must be checked and why changing only the TTL displayed in the UI is not enough.
5. With max-history=7 and total-size-cap=1GB, explain why you cannot guarantee every log is always kept for a full 7 days.

A complete design must state what data is created, where it can travel, who may read it, and how to prove every copy is handled properly when permissions or retention periods end.
