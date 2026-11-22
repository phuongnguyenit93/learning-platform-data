# Access Origin in Java Audit Logging

## 1. What Is "Access Origin" and Why Must It Be Recorded?

**Audit logging** records actions that require traceability: who accessed which resource, what they did, when, what the outcome was, and based on what context or evidence. Within this, **access origin/source** helps answer: *where did this request or operation enter the system from, through which channel, and how trustworthy is the evidence for that origin?*

For example, when an internal document is opened without authorization, a line like `DOCUMENT_READ result=ALLOW` alone is not enough. Investigators also need to know the authenticated actor, client type, request ID, network address observed by the server, which proxy/gateway forwarded the request, and which source of information was trusted to identify the client.

However, **access origin is not synonymous with user identity**. An IP address can belong to a NAT, VPN, reverse proxy, or shared network. An HTTP header such as `X-Forwarded-For` can be spoofed by a client if the infrastructure does not enforce trust boundaries. Audit logs must clearly distinguish **what the system observed** from **what the system inferred from verified evidence**, rather than turning a self-asserted client string into "truth."

After this lesson, you will be able to:
- Distinguish **actor/principal**, **connection source**, **inferred client source**, **calling application**, **access channel**, and **target resource**.
- Design an access event schema with sufficient investigative detail without logging tokens, cookies, or unnecessary data.
- Understand how reverse proxies, load balancers, and API gateways affect `remoteAddr`, `Forwarded`, and `X-Forwarded-For`.
- Write a standalone Java 17 example using JUL to record audit events and distinguish the socket peer from a verified forwarded client.
- Test scenarios involving header spoofing, multiple proxies, unauthenticated requests, service-to-service APIs, and system errors.

## 2. Mental Model: Who, From Where, Through Where, Doing What?

An access audit event should clearly separate these dimensions:

| Field | Question Answered | Illustrative Example |
| --- | --- | --- |
| `actor_id` | Which principal performed the action? | `principal-17` |
| `actor_type` | What type of actor? | `USER`, `SERVICE`, `JOB` |
| `action` | What was requested? | `DOCUMENT_READ`, `ROLE_UPDATE` |
| `resource_type` / `resource_id` | Which resource was the target of access? | `DOCUMENT` / `doc:42` |
| `result` | Was the action allowed, denied, or did it error? | `ALLOW`, `DENY`, `ERROR` |
| `occurred_at` | When did the action occur? | System-recorded UTC timestamp |
| `request_id` / `trace_id` | Which request/flow does the event belong to? | `req-101` |
| `source_socket_peer` | Which network peer did the server see on the incoming connection? | `192.0.2.7` |
| `source_client_ip` | What client address was obtained from an accepted source? | `203.0.113.50` |
| `source_evidence` | What evidence/path determined the client IP? | `SOCKET_PEER`, `TRUSTED_PROXY` |
| `source_channel` | Which access channel was identified? | `WEB`, `API`, `INTERNAL_JOB` |
| `client_app_id` | Which calling application/client was authenticated? | `billing-service` |
| `service` / `instance_id` | Which service/instance recorded the audit event? | `document-api` / `node-a` |

Addresses in the `192.0.2.0/24` and `203.0.113.0/24` ranges are used solely for illustration and do not represent real user information.

Distinguishing several easily confused fields:

- **Actor** is the identity authenticated or classified by the system (`principal-17`, `service-billing`). It does not have to be a human; a background job is also an actor.
- **Source** refers to the origin or access path: connection address, client IP with supporting evidence, calling application, gateway, and channel.
- **Resource/target** is the object being accessed (`doc:42`). Do not use the term `source` to refer to the target resource or the Java file emitting the log.
- **Observer** is the service recording the audit event. When multiple microservices handle the same request, each service may see a different network source; you need to know **at which point** a value was observed.
- **Correlation ID** helps link logs together, but it is **not proof of identity authentication**: a client-supplied request ID can be altered, duplicated, or forged.

Separating these fields helps investigate a chain such as "user U via mobile app called gateway G, gateway forwarded to document service S, and the request to read document D was denied."

## 3. Trust Levels of Access Origin Data

Not all information present in an HTTP request is equally trustworthy. Some examples:

| Information | Collection Source | What Can Be Concluded? |
| --- | --- | --- |
| Socket peer | Connection layer observed by the service/servlet container | Peer address of the **incoming connection to the service** at the observation point; may be a proxy |
| `Forwarded` / `X-Forwarded-For` | HTTP header | Data **supplied by the HTTP sender**; trustworthy only after processing at a configured proxy boundary |
| Actor ID | Security context after authentication | Principal authenticated by the system according to the configured method; trust depends on authn/authz |
| Client app ID | Authenticated via mTLS, OAuth client identity, or another mechanism | Identity of the calling application per the authentication mechanism; not taken from an arbitrary header |
| User-Agent | Client-sent header | Self-asserted information only, easily changed, not unique device proof |
| Host/Referer/Origin header | Sent by client or browser | Useful for protocol handling when properly validated, but not definitive proof of physical origin |
| Trace ID | Tracing middleware or client-sent | Correlation identifier for investigation; may need validation/normalization before use |
| Ingress/load balancer metadata | Controlled infrastructure | Can be stronger evidence if passed over an authenticated channel and not overridable by the client |

A good schema can include `source_evidence` or `source_resolution` to state the **resolution rule** used for the source value. For example, `SOCKET_PEER` means only the connection peer is trusted; `TRUSTED_PROXY` means an infrastructure-permitted proxy chain was used; `INTERNAL_JOB` means the activity has no HTTP client IP in the usual sense.

**Do not create a `real_ip` field and treat it as always being the user's real IP.** Even a client address properly resolved through a proxy may still be a NAT, VPN, or corporate egress IP. A neutral field name such as `client_ip` paired with `source_evidence` is usually more accurate.

## 4. Proxies and the Origin Spoofing Problem

### 4.1. Why `getRemoteAddr()` May Not Be the Client Address

A common deployment flow:

```text
Browser / mobile client
        |
        v
Internet / NAT / VPN
        |
        v
CDN / Load balancer / Reverse proxy
        |
        v
API Gateway
        |
        v
Java service
```

For the Java service, the peer address of the final TCP connection is usually the **gateway or reverse proxy**, not the IP where the browser originated the request. The Servlet API provides `HttpServletRequest.getRemoteAddr()`, but its exact meaning is also influenced by the container and any configured forwarded-header handling. If a trusted filter or valve has rewritten the request, this value may be the processed client IP rather than the raw socket peer.

Therefore, an audit design must specify **which value comes from where**:
- Raw peer observed at the socket/ingress layer (if safely accessible).
- Client address processed by a **trusted proxy resolver**.
- User/application identity from the security context.
- Gateway/instance recording the event.

Do not assign meaning to `getRemoteAddr()` based solely on the method name; verify the framework configuration and runtime environment.

### 4.2. `X-Forwarded-For` Can Be Spoofed

A client-crafted request can send:

```http
GET /documents/42 HTTP/1.1
Host: example.test
X-Forwarded-For: 203.0.113.50
```

`203.0.113.50` is only a **client-claimed value**; nothing in the request above proves this is the real origin. If an application logs `clientIp=request.getHeader("X-Forwarded-For")` and treats it as a trusted source, an attacker can spoof the address.

When multiple proxies are involved, the header can also be a chain of addresses. **Do not blindly take the first or last element**; the rule must come from your topology and trusted proxy policy. If the ingress can be called directly from the Internet, or if a proxy only *appends* to an unnormalized header, a client-supplied string can still appear in the list.

The system should:
1. Identify exactly which proxies/load balancers are trusted, based on the managed connection path/infrastructure; do not trust a flag sent by the client.
2. Prevent direct access that bypasses the proxy if the architecture requires a single ingress.
3. At the boundary, **strip or normalize** forwarding headers sent by untrusted clients according to controlled proxy configuration.
4. Use a resolver/framework mechanism suited to the topology, trusted proxy ranges, hop count, and header syntax.
5. Record the evidence source: `SOCKET_PEER` or `TRUSTED_PROXY`, and optionally the verified gateway/ingress name.
6. Test both direct and proxied paths with spoofed headers to ensure client header changes cannot alter the trusted audit value.

The standard `Forwarded` header and the common `X-Forwarded-For` header are not authentication mechanisms. They can only assist with origin identification when header **creation and propagation** are controlled by a trust boundary.

### 4.3. Do Not Confuse `source_ip` with the Actor

Two users in the same office network may share a public IP. One user may change IPs across mobile networks or VPNs. Many requests may pass through the same API gateway, and a single service may use multiple outbound IPs.

Audit correlation should combine `actor_id`, `auth_method`/client identity, `request_id`, time, result, resource, and IP according to policy. An IP is an **investigative signal**, not proof that a specific person performed an action.

## 5. Designing an Access Origin Audit Event

An example JSON containing only permitted and purposeful fields:

```json
{
  "event_id": "evt-001",
  "occurred_at": "2026-11-10T03:00:00Z",
  "service": "document-api",
  "actor_type": "USER",
  "actor_id": "principal-17",
  "action": "DOCUMENT_READ",
  "resource_type": "DOCUMENT",
  "resource_id": "doc:42",
  "result": "DENY",
  "request_id": "req-002",
  "source": {
    "socket_peer": "192.0.2.7",
    "client_ip": "203.0.113.50",
    "evidence": "TRUSTED_PROXY",
    "channel": "API",
    "client_app_id": "portal-web"
  }
}
```

This is an **illustrative schema**, not a log collected from a real system. Timestamps, IDs, and IPs are example data.

Several important design decisions:

- `event_id`: unique identifier for the **audit event**, useful for forwarding/retries and duplicate detection; it should not be replaced by `request_id` because one request can produce multiple events.
- `request_id`/`trace_id`: used to locate related technical logs; character and length validation may be needed.
- `actor_id`: taken from the authenticated principal, not from a client-supplied request field. For unauthenticated requests, use `ANONYMOUS` or a null/placeholder value per schema—**never fabricate a trusted actor from an IP**.
- `source.socket_peer`: address observed at the defined connection point; if only a post-proxy-rewriting address is available, state the source clearly and do not pretend it is the raw peer.
- `source.client_ip`: value resolved through a trusted resolver if available. When undetermined, record null or the peer address with `evidence=SOCKET_PEER`; avoid recording an unsubstantiated "estimated" IP.
- `result`: must be consistent across `ALLOW`, `DENY`, `ERROR`, or business states; distinguish the **authorization decision** from **whether execution succeeded**.
- `resource_id`: include only permitted identifiers. For highly sensitive resources, tokenization or internal IDs may be needed instead of names or paths containing PII.
- `client_app_id`: use the authenticated client identity if available. Do not take a self-asserted `X-Client-Name` field directly and call it client identity.

A good event must answer **what was observed, what was authenticated, and what is merely a claim**. If two values have different trust levels, separate them into two fields or omit the less trustworthy one instead of blending them into a single string.

## 6. Standalone Java 17 Example: Distinguishing Connection Source from Verified Source

The following program uses **JUL** (`java.util.logging`), built into JDK 17, requiring no Maven, Gradle, or external libraries. It simulates two access paths:
- The first request includes a self-asserted `X-Forwarded-For` but **did not come through a trusted proxy**: only the socket peer is recorded in `clientIp`.
- The second request comes through a proxy verified as trusted by the infrastructure, which provides `validatedForwardedClient`: both the peer and the verified client IP are recorded.

The `socketPeerIsTrustedProxy` flag and `validatedForwardedClient` value in the example **simulate output from trusted infrastructure/resolver**, rather than reading directly from a client-sent header. In production, never populate this flag from unverified query parameters, bodies, or headers.

Create `AuditAccessSourceDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AuditAccessSourceDemo {
    private record Origin(
            String socketPeer, String clientIp, String evidence) {}

    private record AuditEvent(
            String eventId, String actor, String action,
            String resource, String result, Origin origin) {}

    private static Origin resolveOrigin(
            String socketPeer,
            boolean socketPeerIsTrustedProxy,
            String validatedForwardedClient) {

        if (socketPeerIsTrustedProxy
                && validatedForwardedClient != null
                && !validatedForwardedClient.isBlank()) {
            return new Origin(
                    socketPeer, validatedForwardedClient, "TRUSTED_PROXY");
        }
        return new Origin(socketPeer, socketPeer, "SOCKET_PEER");
    }

    private static String safe(String value) {
        return value.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
                .replace("|", "\\|");
    }

    private static void writeAudit(Logger logger, AuditEvent event) {
        Origin source = event.origin();
        logger.info("AUDIT eventId=" + safe(event.eventId())
                + " actor=" + safe(event.actor())
                + " action=" + safe(event.action())
                + " resource=" + safe(event.resource())
                + " result=" + safe(event.result())
                + " socketPeer=" + safe(source.socketPeer())
                + " clientIp=" + safe(source.clientIp())
                + " evidence=" + safe(source.evidence()));
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("audit.access.source.demo");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            Origin untrusted = resolveOrigin(
                    "192.0.2.7", false, "203.0.113.50");
            Origin trusted = resolveOrigin(
                    "192.0.2.7", true, "203.0.113.50");

            writeAudit(logger, new AuditEvent(
                    "evt-01", "principal-17", "DOCUMENT_READ",
                    "doc:42", "ALLOW", untrusted));

            writeAudit(logger, new AuditEvent(
                    "evt-02", "principal-17", "DOCUMENT_READ",
                    "doc:42", "DENY", trusted));
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AuditAccessSourceDemo.java
java AuditAccessSourceDemo
```

**Exact stdout** when run in a fresh JVM with no external configuration interfering with the example's logger:

```text
AUDIT eventId=evt-01 actor=principal-17 action=DOCUMENT_READ resource=doc:42 result=ALLOW socketPeer=192.0.2.7 clientIp=192.0.2.7 evidence=SOCKET_PEER
AUDIT eventId=evt-02 actor=principal-17 action=DOCUMENT_READ resource=doc:42 result=DENY socketPeer=192.0.2.7 clientIp=203.0.113.50 evidence=TRUSTED_PROXY
```

### Why This Example Is Useful

1. Both calls receive **the same string in `validatedForwardedClient`**, yet only the second is allowed to use it because `socketPeerIsTrustedProxy=true` simulates evidence from a trusted infrastructure boundary. The first call does not promote a client claim into a trusted source.
2. `socketPeer` is always kept separate, showing the address of the direct connection to the service in this example model.
3. `safe` escapes newlines, tabs, backslashes, and the `|` delimiter in log values, reducing the risk of **log injection** in text format. It is **not** a secret filter, not a complete IP validator, and not a replacement for a standard JSON encoder.
4. `actor` is a **simulated** authenticated principal; the example does not infer identity from an IP address.
5. The demo intentionally omits dynamic timestamps so stdout is easy to compare. Production audits must include sufficiently accurate event timestamps, service/instance IDs, durability strategies, retention, and appropriate access controls.
6. The custom `Handler` is for illustration only. It does not guarantee concurrency safety, durable disk writes, tamper resistance, or crash recovery retries. Do not replace a production audit store with a simple stdout handler like this.

**Critical limitation:** The `resolveOrigin` method contains no logic to determine trusted proxies on its own, parse IPv4/IPv6, process proxy chains, or verify forwarded headers; it **requires input already verified by infrastructure**. In a real product, perform trust resolution before calling such a function, or use a properly configured integration for your container/gateway.

## 7. Integrating in a Java Web Application

### 7.1. Servlet Requests and Network Information

In a Jakarta Servlet application (such as modern Spring Boot using the Servlet stack), you can observe the following values:

```java
// Integration snippet, requires jakarta.servlet.http.HttpServletRequest.
String observedRemote = request.getRemoteAddr();
String claimedForwarded = request.getHeader("X-Forwarded-For");
```

**Do not immediately record `claimedForwarded` as `client_ip`.** It is merely a claim from the request unless you have configured and verified a trusted proxy processing path. `observedRemote` must also be understood in the context of the current container and any forwarded header filter/valve; it may already have been transformed by middleware.

A reliable implementation approach typically looks like this:

1. At the ingress/gateway, allow only expected request paths and identify trusted proxies.
2. Normalize forwarded metadata according to the topology, stripping values that untrusted clients could inject.
3. In the service, use **a single configured resolver** that returns a `ClientOrigin` (client IP, socket peer if available, evidence, gateway).
4. Attach this origin to an internal **request-scoped context**, propagating only safe fields.
5. When an access decision occurs, build the audit event from the security principal, action/resource, result, and verified context; avoid reading headers ad hoc across individual controllers.

On Spring Boot/Tomcat/Jetty/Undertow, various components support handling forwarded headers or trusted proxies, but option names and semantics differ by stack and version. Configure them to match your actual infrastructure rather than copying a property across every system and assuming the IP is authenticated.

### 7.2. Actor Must Come from the Security Context

Conceptual flow example:

```text
Authentication / mTLS / token verification
                |
                v
  Verified principal or service identity
                |
                v
Authorization checks for resource/action
                |
                +--> ALLOW / DENY / ERROR
                |
                v
  Audit event + verified source metadata
```

`actor_id` should come from the result of **completed authentication**, not from `?userId=`, `X-User-Id`, or the request body. If an upstream gateway forwards principal information, the service must verify the trust channel and authentication mechanism between the gateway and the service. Likewise, do not assume a JWT `sub` claim is valid unless the token's signature, issuer, audience, and expiration have been verified according to policy.

An **unauthenticated** request may also require an audit event, especially when blocked at login or the gateway. In that case, `actor_type=ANONYMOUS`, `actor_id=null`, and result `DENY` with appropriate source evidence is far more accurate than using an IP as the "actor."

### 7.3. Access Channels and Calling Applications

Not every access is an HTTP request from a browser:

| Scenario | Useful Origin Data to Audit | What Not to Assume |
| --- | --- | --- |
| Browser via gateway | Authenticated principal, trusted client IP, gateway, safe session reference | That IP equals a unique user |
| Mobile API | Client identity if authenticated, request ID, trusted-resolved IP | That `User-Agent` proves a genuine app |
| Service-to-service | Service principal from mTLS/OAuth or workload identity, network peer/gateway | That a self-asserted `X-Service-Name` is identity |
| Scheduled job | Job ID, scheduler, service account, execution ID | Fabricating a nonexistent "user client IP" |
| Message consumer | Producer identity if verifiable, topic/queue, message ID, trace context | That an arbitrary message header is an authenticated actor |
| Admin console | Admin principal, action type, trusted source, result | That an internal IP alone proves admin authorization |
| Database integration | Application principal and operation name, observation point | That a JDBC connection string is an end-user identity |

Use a `source_channel` such as `WEB`, `API`, `SERVICE`, `BATCH`, or `MESSAGE` from a managed list. If a channel is inferred only from self-asserted client headers, either add an `UNVERIFIED` classification field or omit it to avoid creating false evidence.

## 8. Designing Audit Events with SLF4J and Structured Logging

SLF4J is a facade; persistence and JSON output depend on Logback, Log4j 2, or the actual backend. The snippet below is **integration code** using the SLF4J 2.x fluent API, not a standalone Java program that runs without dependencies:

```java
// Variables created from the security context and a trusted origin resolver.
// logger is an SLF4J 2.x logger configured in the application.
auditLogger.atInfo()
    .addKeyValue("event_id", eventId)
    .addKeyValue("actor_id", principalId)
    .addKeyValue("action", "DOCUMENT_READ")
    .addKeyValue("resource_id", safeResourceId)
    .addKeyValue("result", "DENY")
    .addKeyValue("source_client_ip", verifiedOrigin.clientIp())
    .addKeyValue("source_evidence", verifiedOrigin.evidence())
    .addKeyValue("request_id", requestId)
    .log("Access decision recorded");
```

Notes:
- `principalId` must come from the security context **after authentication**, not from unverified query parameters or headers.
- `verifiedOrigin` represents an object provided by a trusted resolver, **not a built-in SLF4J class**; you must define it in your application.
- The backend/encoder must support emitting key-value pairs into structured output. Not every text pattern automatically outputs all fields.
- Do not include `authorization_header`, raw JWTs, passwords, cookies, API keys, session tokens, or request bodies.
- If `safeResourceId` contains personal data, apply appropriate minimization or pseudonymization policies.
- Logging at `INFO` level through the normal application pipeline may be filtered, dropped, or fail to write; for mandatory audits, use a storage and integrity mechanism with appropriate guarantees rather than relying on standard logs by default.

### 8.1. Audit Is More Than Debug Logging

A statement like `logger.info("user {} accessed ...")` does not by itself create a trustworthy audit system. Auditing requires additional properties such as:
- Consistent schema/version, event identity, and actor/action/result classification.
- Traceable records protected against unauthorized modification or deletion per policy.
- Clock/timestamp synchronization and recording when the event was persisted.
- Protection, retention, and backup policies, plus missing-event and duplicate detection.
- Controls over who can read, export, and delete logs, including auditing log-administration actions themselves.

Depending on requirements, you may need an **append-only audit store**, a transaction-bound event outbox, or a dedicated durable storage mechanism. Audit logging in a standard pipeline can serve best-effort investigations, but it **does not automatically guarantee exactly-once delivery, immutability, or crash durability**.

### 8.2. Recording Origin at the Right Time

If you record the audit event at **authorization decision time**, `result=ALLOW` usually means "permitted to proceed," **not necessarily** that the data was successfully returned. If you record when **access completes**, you can include technical outcomes, bytes, error codes, or execution details. Define event types clearly so they are not conflated:
- `AUTHZ_DENIED`: rejected by permission check.
- `ACCESS_ATTEMPTED`: request started.
- `ACCESS_COMPLETED`: operation finished.
- `ACCESS_FAILED`: technical or business error occurred.

Do not log the same event under multiple names without an event ID or correlation, or investigators may miscount access attempts.

## 9. Pitfalls with Origin Data

### 9.1. Log Injection and Untrusted Input

Clients can send headers with unusual strings, control characters, or very long values. Concatenating them directly into a text log can split an event across multiple lines or confuse parsers. You should:
- Record only truly necessary fields with appropriate trust sources.
- Validate syntax, normalize, and enforce length limits.
- Use a structured encoder with proper escaping; never build JSON via string concatenation.
- If writing text logs, escape newlines, carriage returns, and delimiters.
- Avoid logging the entire raw `X-Forwarded-For` chain or a long User-Agent just to capture an IP.

### 9.2. IPv4, IPv6, NAT, and Network Identifiers

An IP can be IPv4 or IPv6. A header string may include ports, brackets around addresses, or IPv6 addresses with `:` notation. **Do not split on commas/colons yourself and treat it as a complete IP parser.** Use a parser/resolver tested for the standards and topology in use.

With NAT/VPN, a single IP does not uniquely identify a person. With IPv6 privacy addresses, addresses can change over time. Internal/private addresses or proxy IPs can also be sensitive infrastructure information. Retention and display policies should account for both address families.

### 9.3. Multi-Proxy Environments

A request passing through a CDN and load balancer can generate multiple hops of metadata. Declare the trusted proxy list and trust boundary location at the right infrastructure layer; if using an `X-Forwarded-For` chain, deciding which hop to extract must follow the resolver's formal policy, not an unconditional "take the first IP" trick.

Trusting gateway A when A accepts unsanitized headers from the client **does not automatically make every element in the header trustworthy**. You must verify the actual sanitize/overwrite/append behavior at each hop.

### 9.4. Service Identity and Network Origin Can Differ

If mTLS authenticates client `billing-service` while the TCP peer is a sidecar proxy, an audit record can validly store:
- `actor_type=SERVICE`, `actor_id=billing-service` (from verified workload identity).
- `source_socket_peer` as the observed sidecar/gateway.
- `source_channel=SERVICE`.
- `source_client_ip` if the resolver provides trusted evidence.

Do not "fix" the source IP to match the actor or assume differing values indicate an error. They measure **different dimensions**.

## 10. Privacy and Access Origin Minimization

Origin data is valuable for investigations, but it can also be **personal data or sensitive system information**. IPs, devices, resource access history, location, and correlation IDs can be combined to infer an individual's activity.

Key principles:
1. **Record only data needed for a specific audit purpose.** Do not collect full headers, geolocation, fingerprints, or tokens by default.
2. **Separate identity from network data.** Actor ID can be an internal ID; avoid logging real names/emails when unnecessary.
3. **Restrict audit log access.** People with technical debugging access do not necessarily need to view sensitive resource access histories.
4. **Enforce bounded retention**, with deletion/anonymization policies and export/backup controls per organizational and applicable legal requirements.
5. **Protect data in transit and at rest**, audit access to the audit store itself, and monitor for signs of anomalous modification or deletion.
6. **Never store raw credentials**, cookies, JWTs, API keys, client secrets, or signed URLs to "verify origin."
7. **Be careful with pseudonymization.** Simply hashing an IP or user ID may still allow activity linkage and does not automatically render data anonymous. When linkability must be reduced, design according to a specific policy.

If origin data must be retained for fraud prevention, state the purpose, retention period, and authorized readers. Do not assume all audit logs may be kept indefinitely simply because they serve security.

## 11. Record Reliability: Integrity and Log Loss

An accurately resolved origin is useless if the event is lost, altered, or if you cannot verify who read the record.

A serious audit system must consider:
- **Durable writes**: if a transaction commits and the process crashes before writing the audit record, the record can be lost. For mandatory audits, consider an outbox/transactional event or audit storage with appropriate synchronization.
- **Integrity**: append-only/WORM storage, edit/delete controls, signing or hash chaining where appropriate, and auditing administrative operations; hashing alone does not solve write permissions.
- **Chronological ordering**: UTC timestamps with offsets, clock synchronization, per-stream event IDs/sequences, and distinguishing `occurred_at` from `recorded_at`.
- **Latency constraints**: async queues can drop events when full or during shutdown; track accepted/emitted/dropped counts and flush deadlines.
- **Duplicates**: retries and failovers can deliver an event to multiple sinks; event IDs enable downstream deduplication.
- **Observation source**: if both gateway and service write audit logs, a service/observer ID is needed to know where each record came from; do not treat two records describing the same request as two separate accesses.

Do not claim that `logger.info` returning means "the record was safely persisted." What success means depends on the handler/appender, queue, collector, and acknowledgement mechanism.

## 12. Testing Access Origin with Positive and Negative Scenarios

Test both valid values and **spoofed/missing cases**:

| Scenario | Expected Audit Origin |
| --- | --- |
| Direct client access without a proxy | Client IP based on observed peer, `evidence=SOCKET_PEER` |
| Client sends `X-Forwarded-For` but peer is not a trusted proxy | Header is not used to promote client IP |
| Request via trusted proxy with normalized header | Resolver extracts client IP per topology; records `evidence=TRUSTED_PROXY` |
| Client attempts to inject multiple fake IPs into header | Spoofed data does not become a trusted client IP |
| Multiple trusted proxies present | Selects the correct hop per configuration; no blind "first element" rule |
| Service accessed directly, bypassing gateway | Does not treat forwarding claims as verified origin; may block request if policy requires |
| Valid IPv6 | Parser and storage handle IPv6 properly |
| Malformed or oversized IP/header | Fails closed per trust policy; does not record arbitrary values as verified origin |
| Unauthenticated request | `actor=ANONYMOUS`/unknown per schema; origin can still record evidence |
| mTLS service-to-service | Actor from mTLS identity; peer address stored separately |
| Non-HTTP job | `source channel=JOB`, job/execution ID; do not invent a client IP |
| Spoofed User-Agent | Do not use it as client identification evidence |
| Logging queue full or collector failure | Telemetry/failure policy in place; do not claim audit complete if persistence is not guaranteed |
| Sensitive user data in URL | Do not print full URL/query; use permitted route template/resource ID |

### An End-to-End Testing Workflow

1. Set up a staging environment matching production's proxy/gateway topology and framework versions.
2. Generate two different simulated authenticated actors and one anonymous request; trigger events for `ALLOW`/`DENY`/`ERROR`.
3. Send direct requests with self-asserted forwarding headers to test spoofing; verify the audit log still uses the socket peer or rejects the request.
4. Send requests through a trusted proxy; verify the trusted client IP is extracted correctly by the resolver and tagged with evidence.
5. Inspect events at the **final destination** (audit store/index), not just in the console; verify event ID, actor, action, resource, outcome, request ID, source, and timestamp.
6. Test duplicates/retries, shutdown/queue overflow, and collector outage; observe error metrics and missing-event reports.
7. Verify that no Authorization tokens, cookies, passwords, raw query secrets, or spoofed headers appear in the logs.

Archive test evidence by request type, topology, and active configuration. A single successful request through proxy A does not prove that every other ingress path is handled securely.

## 13. Common Mistakes When Logging Access Origin

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Every request shows the same internal IP | Java service only sees the reverse proxy/gateway | Use a topology-accurate trusted proxy resolver; keep peer separate |
| Audit IP changes whenever client changes header | Application trusts raw `X-Forwarded-For` | Trust only configured proxies; sanitize headers at ingress |
| Audit source IP looks plausible, but actor is wrong | Taking username/userId from payload instead of security principal | Use authenticated identity |
| IP is used to prove "who" accessed | Equating network address with identity | Combine actor, authn evidence, source, and correlation |
| No origin shown for background jobs | Assuming every event has an HTTP request | Use job/service identity and an appropriate `source_channel` |
| Gateway and microservice report different origins | Each service observes a different hop | Record observer/service ID and evidence at each point |
| IPv6 addresses parsed incorrectly | Manual header splitting or missing normalization | Use a parser supporting IPv6 and proxy chains |
| Header containing newlines creates fake log entries | Logging raw text without escaping/truncation | Validate, enforce length limits, use a structured encoder |
| User-Agent treated as a verified device | Client self-asserted data | Treat only as untrusted metadata if truly needed |
| Audit contains bearer tokens/cookies | Logging full headers/requests | Use an allowlist; exclude secrets from events |
| Audit shows ALLOW, yet operation still failed | Confusing authorization `ALLOW` with execution `SUCCESS` | Separate decision events from completion events |
| Missing events after a crash | Async logging queue not flushed or collector failed | Choose appropriate durability/acks; measure loss and shutdown |
| One operation produces two audit events | Both gateway and service log, or retries occur | Use event IDs and observer IDs with a dedup/correlation model |

## 14. Exercises and Answers

**Exercise 1 — Spoofed header.** The service sees socket peer `192.0.2.7`. The client sends `X-Forwarded-For: 203.0.113.50`, but the peer is not in the trusted proxy set. What should you record for `source_client_ip`?

**Answer:** If your schema falls back to the peer, record `192.0.2.7` with `source_evidence=SOCKET_PEER`. Do not record `203.0.113.50` as a trusted IP. If policy requires all requests to go through the proxy, you can reject the access path and audit the violation.

**Exercise 2 — Two different origins.** The gateway logs client IP `203.0.113.50`, while the service logs peer `10.0.0.8`. Is one side necessarily wrong?

**Answer:** No. The gateway observes the client near the edge; the service observes the gateway as its socket peer. To investigate consistently, you need an observer ID, trusted forwarding provenance, and a correlation ID.

**Exercise 3 — Unauthenticated principal.** An unauthenticated request tries to open a document. Should the audit log record `actor_id=request.getParameter("user")` or `ANONYMOUS`?

**Answer:** `ANONYMOUS` or an unknown form per your schema. A client-supplied parameter is not an authenticated identity.

**Exercise 4 — Service-to-service.** The system authenticates `billing-service` via mTLS. Can you rely solely on IP to record the "origin"?

**Answer:** Not sufficient. Store the verified service identity in the actor/client app field and the peer address separately; the IP may belong to a sidecar or gateway and does not replace mTLS authentication.

**Exercise 5 — Actor and outcome.** When an authorization check returns `ALLOW` but the database query fails, should you record `result=ALLOW` or `SUCCESS`?

**Answer:** It depends on the event type. For `AUTHZ_DECISION`, `ALLOW` is accurate for the decision result. For `ACCESS_COMPLETED`, the actual operation failed and needs the corresponding result/error. Use clear event types so the two meanings are not mixed.

## 15. Checklist for Applying in a Java System

Before deploying access-origin audit logging, confirm:

1. **Actor, source, target, and observer** are defined and stored in separate fields.
2. Actor comes from an **authenticated security principal/workload identity**; anonymous requests are represented honestly.
3. Socket peer and proxy-resolved client address are **never confused**; evidence/trust provenance is recorded.
4. `Forwarded`/`X-Forwarded-For` are processed only with verified trusted proxy configuration and topology; raw headers are never trusted.
5. Parsers support IPv4/IPv6, multiple hops, malformed headers, length limits, and ingress boundaries.
6. Source channel and client app identity derive from trusted signals; self-asserted User-Agent does not prove identity.
7. Audit events include accurate action, resource, outcome, event ID, request/trace ID, and UTC timestamp.
8. No tokens, passwords, cookies, raw request bodies, or secret URL query parameters are logged; personal data is minimized per policy.
9. Log injection is controlled through validation, escaping, and standard structured encoders.
10. The audit store has appropriate access controls, retention, integrity protection, loss/duplicate measurement, and failover policies.
11. Testing covers direct access, trusted/untrusted proxies, service-to-service, jobs, anonymous requests, async failures, and recovery.
12. Investigators can correlate origin evidence with identity, time, action, and outcome **without guessing**.

**Conclusion:** Access origin in audit logging is **the set of evidence showing where and how an action entered the system**, not merely an IP string. In Java, combine the observed connection source, trusted-resolver client address, authenticated actor, access channel, and event metadata; explicitly record trust levels, prevent forwarded header spoofing, and protect privacy. Only by distinguishing *what was observed*, *what was verified*, and *what was self-asserted by the client* do audit logs become reliable for traceability and investigation.
