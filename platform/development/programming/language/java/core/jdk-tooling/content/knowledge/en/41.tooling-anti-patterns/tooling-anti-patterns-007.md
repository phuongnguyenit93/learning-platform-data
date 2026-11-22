# Public Production Debugging in Java Applications

**Public production debugging** is an anti-pattern where an application serving real users exposes internal diagnostic tools or data through an interface accessible to outsiders. Examples include error pages with stack traces, debug consoles, unauthenticated management endpoints, remote debugger ports, JMX exposed to the Internet, publicly downloadable heap dumps, or logs containing tokens and personal data.

This information helps operations teams find the root cause of errors, but when made public, it can reveal system architecture, libraries, versions, file paths, hostnames, database queries, sessions, secrets, and customer data. Some interfaces even allow reading the state of or modifying a running JVM.

In production, users need error messages clear enough to know that a request failed and how to proceed. Operations teams need detailed information to investigate through a controlled channel. These two purposes must be served with appropriate access controls and levels of detail.

## 1. Why Is Public Debugging an Anti-Pattern?

Development environments typically enable stack traces, auto-reload, debug toolbars, verbose logging, and management tools to shorten the development feedback loop. Production has real data, real credentials, real traffic, and connections to critical systems. Leaving development debug configurations enabled creates an unnecessary attack surface.

When outsiders can access diagnostic information, they can:

- Identify the frameworks, application servers, libraries, and versions in use.
- Discover file paths, package structures, class names, table names, and SQL queries.
- Uncover internal hostnames, service addresses, buckets, databases, or queues.
- See tokens, cookies, session IDs, API keys, passwords, or connection strings.
- Read personal data, request payloads, transaction data, or customer information.
- Download heap dumps, thread dumps, log files, or configurations containing sensitive data.
- Invoke administrative operations, change log levels, stop the application, or interfere with runtime state if endpoints allow it.
- Slow down the application or exhaust resources by requesting heavy dumps, traces, or profiling.

Even a seemingly harmless error—such as displaying a class name or an absolute path—can help an attacker map the system and choose their next exploitation path.

## 2. Identifying Forms of Public Debugging

| Exposure Type | Examples | Risk |
|---|---|---|
| Detailed error pages | Stack traces, exception messages, SQL | Leaks code structure, queries, paths, and data |
| Debug mode | Debug toolbar pages, interactive consoles | Leaks runtime variables or allows executing operations |
| Custom debug endpoints | `/debug`, `/dump`, `/config`, `/test-db` | Bypasses authorization or returns internal data |
| Remote debugger | JDWP port open to public networks | Outsiders can attach a debugger and control the debug session |
| Remote JMX | Unprotected JMX RMI port | Remote monitoring or management of the JVM |
| Actuator/management | `env`, `heapdump`, `logfile`, `threaddump` | Leaks environment, memory, logs, and system state |
| Public log viewer | Unauthenticated log download or search page | Leaks requests, tokens, PII, and operational info |
| Configuration dump | Displaying environment variables or application properties | Leaks passwords, secrets, endpoints, and feature flags |
| Source maps/debug symbols | Public frontend source maps | Leaks source code, module names, and internal logic |
| Overly detailed metrics/traces | Labels containing email, user ID, or request data | Leaks data and creates high cardinality |

Not every observability endpoint is dangerous. Minimal health checks can serve load balancers or orchestrators. Risk increases when an endpoint returns internal details, allows state changes, or lacks proper access control.

## 3. Do Not Return Stack Traces to Users

Stack traces are useful for developers because they show where an exception occurred and which methods it passed through. However, public responses should not contain:

- Internal class and package names.
- Source paths or deployment directories.
- Database, table, column names, and SQL queries.
- Hostnames, private IPs, and internal service names.
- Exception messages that may contain user input or sensitive data.
- Framework versions, server versions, or dependency versions.
- Tokens, cookies, session IDs, or connection strings.

A safe response should have the right HTTP status, a stable error code, a generic message, and a request/correlation ID for users to provide when contacting support.

Example:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store
X-Request-ID: 7d1c2f9a-...

{
  "code": "INTERNAL_ERROR",
  "message": "An error occurred. Please try again later.",
  "requestId": "7d1c2f9a-..."
}
```

This response indicates that the request failed and provides a lookup ID. The stack trace and technical root cause are written to controlled internal logs with the same request ID.

Do not return HTTP 200 for every error just to avoid showing errors. Keep appropriate status codes such as 400, 401, 403, 404, 409, 429, or 500 so clients and monitoring handle them properly.

## 4. Distinguish Information for Clients vs. Operations

| Information | Public Client | Internal Logs/Traces |
|---|---|---|
| Stable error code | Yes | Yes |
| User-friendly message | Yes | Optional |
| Request ID | Yes | Yes |
| Stack trace | No | Yes, if needed |
| Exception class/cause | No | Yes |
| SQL, query parameters | No | Only when sanitized of sensitive data and genuinely needed |
| Internal absolute paths/hostnames | No | Restricted to investigation needs |
| Access tokens/passwords | No | Do not log directly |
| PII/sensitive data | No | Collect only when justified, minimally, and protected |
| Runtime/configuration dumps | No | Only via authorized administrative tools |

Internal logs do not mean a place where anything can be written. Logs may be replicated across multiple systems, retained for a long time, downloaded, or accessed by multiple teams. Apply access control, retention, masking, and auditing to the logging system itself.

## 5. Log Exceptions Safely

When an exception occurs at a request boundary, log enough information for tracing:

- Request ID or trace ID.
- Timestamp, service, environment, and deployed version.
- Operation or route being handled.
- Exception class and stack trace.
- Handling outcome and latency if needed.
- Business attributes classified as safe.

Avoid logging directly:

- Passwords, access tokens, refresh tokens, API keys, and private keys.
- Unredacted session IDs or cookies.
- `Authorization` headers.
- Database connection strings.
- Payment card data, health information, or sensitive personal identifiers.
- Full request/response bodies by default.
- Unfiltered secrets or environment variables.

If you need to correlate multiple events in the same session, use a pseudonymous identifier or a hashed value according to your data policy. Do not use real authentication tokens as correlation IDs.

User-submitted data may contain newlines or control characters. When writing to logs, encode/escape them to prevent log injection, where forged input creates log lines that look like separate events.

## 6. Use Correlation IDs to Investigate Errors

A correlation ID links the client response to internal logs, traces, and events. Clients may send a request ID, but the server must validate its length/characters and never trust an arbitrary value as an identity or access right.

A simple approach is for the server to generate the ID itself:

```java
import java.util.UUID;

String requestId = UUID.randomUUID().toString();

System.out.println("requestId=" + requestId);
```

Stdout:

```text
requestId=<UUID-generated-at-runtime>
```

In a web application, generate the ID in a request filter/interceptor, attach it to the logging context (such as a logging framework's MDC), return it in a response header, and include it in traces. When receiving a support ticket, operations teams look up that exact ID in the logging system.

A correlation ID is not a secret, session token, or authentication mechanism. Do not grant log access just because a user knows a request ID. Do not allow client-supplied IDs containing newlines or abnormally long content.

## 7. Java 17+ Example: Returning Sanitized Errors and Logging Internal Causes

The example below uses the built-in JDK HTTP server to illustrate separating public responses from technical logs. The demo endpoint always throws an error for easy observation; do not use this mock logic in real business endpoints.

Create `SafeErrorServer.java`:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public final class SafeErrorServer {
    private static final System.Logger LOG =
            System.getLogger(SafeErrorServer.class.getName());

    private SafeErrorServer() {
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8080), 0);

        server.createContext("/demo", SafeErrorServer::handle);
        server.start();

        System.out.println("listening=http://127.0.0.1:8080");
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        String requestId = UUID.randomUUID().toString();

        try {
            // Demo: replace with a business operation that may throw an error.
            throw new IllegalStateException(
                    "Database connection unavailable");
        } catch (RuntimeException failure) {
            LOG.log(
                    System.Logger.Level.ERROR,
                    "request_id=" + requestId + " operation=demo",
                    failure);

            String json = "{"
                    + "\"code\":\"INTERNAL_ERROR\","
                    + "\"message\":\"An error occurred. Please try again later.\","
                    + "\"requestId\":\"" + requestId + "\""
                    + "}";

            byte[] body = json.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "application/json; charset=utf-8");
            exchange.getResponseHeaders().set("Cache-Control", "no-store");
            exchange.getResponseHeaders().set("X-Request-ID", requestId);

            exchange.sendResponseHeaders(500, body.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        } finally {
            exchange.close();
        }
    }
}
```

Compile and run on JDK 17+:

```sh
javac --add-modules jdk.httpserver SafeErrorServer.java
java --add-modules jdk.httpserver SafeErrorServer
```

Stdout when the server starts:

```text
listening=http://127.0.0.1:8080
```

Send a request in another terminal:

```sh
curl -i http://127.0.0.1:8080/demo
```

The response body looks like:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "An error occurred. Please try again later.",
  "requestId": "<UUID>"
}
```

The request ID changes on every request. The exception and stack trace are sent to the logger; in production, configure the logger to forward them to an authorized internal log collector. Do not configure the process's `stderr` as a public endpoint or public log stream.

The demo server binds to loopback `127.0.0.1` for local testing. In actual deployments, the bind address must match the network/service mesh architecture; binding to a private interface alone does not replace authentication, authorization, and firewalls.

## 8. Centralized Exception Handling in Web Frameworks

In a Spring MVC application, you can use `@RestControllerAdvice` to standardize errors in one place:

```java
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleUnexpected(Exception error) {
        String requestId = UUID.randomUUID().toString();

        log.error("request_id={} operation=api-request",
                requestId, error);

        ApiError body = new ApiError(
                "INTERNAL_ERROR",
                "An error occurred. Please try again later.",
                requestId);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .header("X-Request-ID", requestId)
                .body(body);
    }

    public record ApiError(
            String code,
            String message,
            String requestId) {
    }
}
```

This example depends on Spring Web and SLF4J; it is not a JDK-only class. In real applications, you should have dedicated handlers for expected business errors (validation, not found, conflict, rate limit) and a general handler for unexpected errors.

Do not catch `Throwable` and continue running as if nothing happened. Serious JVM errors like `OutOfMemoryError` should not be handled like ordinary request errors. Let the runtime/orchestrator handle them according to appropriate recovery policies.

## 9. Disable Debug Mode and Error Details in Production

Production configuration must be separated from development. Do not rely on developers remembering to uncheck a box before releasing.

Typical controls needed:

- Do not package dev consoles or interactive debug pages into the production runtime.
- Disable verbose error pages and stack traces in HTTP responses.
- Do not enable development profiles in production.
- Do not leave debug toolbars, test controllers, or mock endpoints in release artifacts.
- Do not enable remote restart/devtools on public environments.
- Use safe-by-default production configurations and verify them during deployment.
- Fail the deployment if debug settings are unsuitable for production.

With Spring Boot, the following properties help prevent exception details from appearing in error responses:

```yaml
server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
```

This is a Spring Boot configuration example. Check the documentation for the exact framework version you are using before applying it; error response configuration does not replace security rules for management endpoints.

## 10. Actuator Is Not a Public Debug Console

Spring Boot Actuator provides monitoring and management endpoints. Some endpoints can return sensitive data or perform operations that affect the application.

Endpoints that need careful evaluation:

| Endpoint | Content/Function | Risk When Public |
|---|---|---|
| `/actuator/health` | Health status | May reveal components if details are enabled |
| `/actuator/env` | Environment and property sources | May leak configs/secrets if unsanitized |
| `/actuator/configprops` | Configuration properties | May leak sensitive configurations |
| `/actuator/beans` | Beans in the application context | Reveals application structure |
| `/actuator/mappings` | Request mappings | Reveals routes and handlers |
| `/actuator/loggers` | Read/change log levels | Can leak data via verbose logging |
| `/actuator/threaddump` | Thread dump | Reveals stacks, thread names, and internal activity |
| `/actuator/heapdump` | Heap dump | May contain passwords, tokens, and in-memory data |
| `/actuator/logfile` | Log file contents | May leak requests, PII, and secrets |
| `/actuator/shutdown` | Request to shut down the application | Can cause service disruption if enabled |

Current Spring Boot documentation states that only the `health` endpoint is exposed over HTTP by default. The default `health` endpoint does not show details. When exposing additional endpoints, you must evaluate the returned data and protect them with an appropriate security policy.

If management endpoints are needed for monitoring, expose only the ones genuinely required. Place the management interface on a private network, use authentication/authorization, and apply firewall or service mesh policies. Separating the management port can be architecturally useful, but a different port alone is not a security boundary.

If your application has a custom Spring Security `SecurityFilterChain`, Actuator's auto-configuration rules may no longer apply as expected. Write and test explicit rules for each endpoint group.

## 11. Public Health Checks Should Return Minimal Information

Load balancers and orchestrators typically need to know whether the application is alive or ready to receive traffic. They do not need the full database configuration, hostnames, credentials, or the status of every dependency.

You can distinguish between:

- **Liveness:** the process is still running and does not need an immediate restart.
- **Readiness:** whether the instance can accept new requests.
- **Deep diagnostics:** detailed information about dependencies, pools, queues, threads, and resources; strictly for authorized monitoring/operations.

Public health responses should avoid returning:

- JDBC URLs or database hostnames.
- Bucket, queue, or internal service names.
- Exception messages from dependencies.
- Secrets or connection statuses with authentication details.
- Stack traces and runtime configurations.

If health details are needed, display them only to authenticated monitoring roles or on the management network. Be careful with health checks that depend too heavily on external services: a temporarily failing dependency can mark every instance unhealthy and amplify an outage.

## 12. Do Not Expose the JDWP Remote Debugger to the Internet

The Java Debug Wire Protocol (JDWP) allows a debugger to communicate with a JVM being debugged. The socket transport uses TCP; when the target VM listens, a debugger can attach and send commands to the JVM.

Example startup option:

```sh
-agentlib:jdwp=transport=dt_socket,server=y,address=*:5005,suspend=n
```

The `*` address instructs the socket to listen on all network interfaces. If port 5005 is publicly reachable, outsiders can attempt to connect to the debug agent. Treat JDWP connectivity as privileged access to the process.

Do not enable JDWP in normal production. If an incident genuinely requires a debugger:

1. Prefer reproducing the issue on staging with sanitized data.
2. If debugging production is unavoidable, obtain incident approval and assign an owner.
3. Bind to loopback or a controlled private interface.
4. Connect using a VPN, bastion, or authenticated SSH tunnel.
5. Restrict source IPs and the duration the port remains open.
6. Do not open debug ports directly on public load balancers/security groups.
7. Log who attached, when, and what actions were taken.
8. Disable JDWP, close tunnels/firewall rules, and verify the port is no longer listening after the investigation.

Example binding to loopback:

```sh
-agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005,suspend=n
```

You can create a tunnel from an authenticated administrative machine:

```sh
ssh -L 5005:127.0.0.1:5005 operator@private-host
```

The tunnel command is only meaningful when the SSH host is securely accessible and the target debug port binds only to that host's loopback. Do not treat JDWP as a protocol with authentication/encryption equivalent to a protected production API.

## 13. Protect Remote JMX

JMX supports monitoring and managing the JVM, MBeans, and certain runtime operations. Remote JMX can be useful for operational tools but must not be left open on the Internet.

Oracle warns that remote JMX requires security to prevent unauthorized users from monitoring or controlling the application. Production documentation recommends using both SSL/TLS client certificates and password authentication to authenticate hosts/clients and users.

Principles:

- Enable remote JMX only when there is a specific operational need.
- Restrict network paths to the management network.
- Enable TLS and client authentication per policy.
- Use password/access files or an appropriate identity mechanism, protecting credential files with strict permissions.
- Separate read-only and control permissions if the system supports it.
- Do not set `com.sun.management.jmxremote.authenticate=false` together with `com.sun.management.jmxremote.ssl=false` in production.
- Do not expose RMI registry and connector ports to public networks.
- Monitor access logs and rotate credentials/certificates according to their lifecycle.

Read-only JMX can still leak runtime information. Management permissions can alter configuration or application behavior; assign permissions based on role.

## 14. Heap Dumps, Thread Dumps, and Java Flight Recorder

JVM diagnostic tools are very helpful when handling memory leaks, deadlocks, or latency issues. They can also contain sensitive information.

A **heap dump** can contain live objects in the heap: request payloads, sessions, tokens, temporary passwords, personal data, and caches. A heap dump file can be large and consume significant CPU/I/O to generate.

A **thread dump** contains stack traces, thread names, class names, locks, and application activity. It can reveal internal routes, dependencies, and running operations.

**Java Flight Recorder (JFR)** records runtime events for performance analysis. Depending on the events and configuration, a recording may contain sensitive metadata or data.

Store these files in internal storage with ACLs, encryption at rest, short retention, and download auditing. Do not place heap dumps or recordings in static/public web directories. Define who is allowed to download them, the purpose of use, and the retention period; delete copies per the retention policy after an incident if they do not need to be preserved as evidence.

Do not generate heap dumps continuously in production just to "take a look." Evaluate disk space, performance impact, and collection methods before proceeding.

## 15. Do Not Expose Log Viewers or Configuration Dumps Publicly

A log viewer page that is convenient for developers can become a data leak source when published alongside the application.

Do not create public endpoints to:

- Download log files by a path supplied in the request.
- Search logs by user or session without authorization.
- View all environment variables.
- View all Spring properties or secrets.
- Read arbitrary configuration files.
- Return heap/thread dump contents.
- Run SQL queries or commands to inspect the system.

User-supplied paths to a log viewer can also cause path traversal if handled improperly. Logging systems should be accessed through a dedicated observability platform with SSO/MFA, roles, auditing, and data filtering.

Configuration dumps are especially dangerous because many secrets are injected from the environment, secret managers, or mounted files. Do not return raw config objects for debugging convenience; only provide filtered status without secret values.

## 16. Metrics and Traces Can Also Leak Data

Metrics are often assumed safe because they only contain numbers. However, labels can contain sensitive information if emails, usernames, account IDs, order IDs, or full URLs are put into metric dimensions.

Avoid:

- Per-user or per-request labels.
- Recording raw query strings containing tokens.
- Putting emails, phone numbers, or personal identifiers into tags.
- Recording unfiltered SQL bind parameters in spans.
- Using exception messages as metric labels.
- Exposing metrics endpoints publicly without a network policy.

Metrics need low-cardinality labels without personal data. Traces need sampling, attribute masking, and access control. For URLs, keep only the route template such as `/orders/{id}` instead of the full URL containing identifiers or query parameters.

## 17. Source Maps and Debug Symbols in Frontend Artifacts

A Java application may serve frontend bundles. Public source maps can allow recovering readable source code, module names, directory structures, and some internal comments/logic.

Before release:

- Determine whether source maps need to be public or only used for error monitoring.
- If using an error monitoring service, upload source maps over an authenticated channel and do not make those files public.
- Verify that web servers/CDNs do not serve `.map` files unintentionally.
- Do not embed secrets in frontend bundles; any value sent to the browser can be viewed by users.
- Verify that production artifacts do not contain debug assets or development configs.

Obfuscation does not replace security. Any logic or credential running in the browser must be considered observable from the client side.

## 18. Do Not Use Debug Endpoints to Modify Production Data

Some endpoints created temporarily to assist with incidents can perform dangerous operations:

- Changing order or account statuses.
- Clearing caches or queues.
- Running arbitrary SQL.
- Resetting passwords or creating admin users.
- Resending events or payments.
- Invoking internal methods by class/method name.
- Adjusting log levels or feature flags without auditing.

If administrative operations are needed, build a separate control plane with authentication, authorization, validation, auditing, approval, and idempotency. Do not create secret endpoints relying on hard-to-guess URLs or a query parameter like `?admin=true`.

An endpoint not linked in any menu can still be discovered via route discovery, logs, source code, or traffic. "Nobody knows the URL" is not an access control mechanism.

## 19. Safe Production Debugging Workflow

When an incident occurs, prioritize using pre-designed observability data:

1. Identify the timestamp, service, deployed version, and scope of impact.
2. Use metrics to identify error trends, latency, saturation, and dependencies.
3. Use traces to find slow spans or failing services.
4. Use internal logs by request ID to inspect exceptions and operations.
5. Check deployment/config changes near the time errors began.
6. Reproduce on staging with anonymized data if possible.
7. If privileged diagnostics in production are needed, grant access per incident, with a time limit and an owner.
8. Collect dumps/recordings into protected storage and record the impact.
9. Restore configurations, close ports/tunnels, and revoke temporary access after the investigation.
10. If sensitive data was exposed, assess the scope, preserve evidence, and rotate/revoke credentials per the incident response plan.

Do not enable public debugging just to speed up an investigation. If telemetry is lacking, add controlled instrumentation after evaluating the data being collected.

## 20. Checking Production Configuration Before Release

Create a release checklist for each service:

- The production profile is selected.
- Debug mode, dev consoles, debug toolbars, and test routes are disabled/removed.
- Error responses do not contain stack traces or exception details.
- Actuator exposes only approved endpoints.
- Health details do not reveal dependencies or internal hostnames.
- JDWP is disabled; no debug ports are public.
- Remote JMX is disabled if unnecessary, or protected per policy.
- Log viewers/config dumps are not public.
- Heap dumps, thread dumps, and recordings are stored in private storage.
- Metrics/traces do not contain PII, tokens, or high-cardinality identifiers.
- Source maps/debug symbols are not unintentionally public.
- Security rules have been tested after adding custom filter chains.
- Secrets do not appear in responses, logs, artifacts, or container images.
- Public route scans find no unexpected debug/admin endpoints.

Verify the actual effective configuration of the built artifact and deployment environment. Having a correct `application-prod.yml` file does not guarantee the deployment actually uses that profile.

## 21. Testing Against Information Leakage

In test/staging or authorized security tests, trigger controlled errors and verify public responses.

Check that:

- HTTP 500 errors do not return stack traces, exception messages, or internal paths.
- Validation errors do not echo secrets or full sensitive inputs.
- Responses include a request ID and the proper status code.
- Health endpoints return only minimal information.
- Unauthorized management endpoints return 401/403 or do not exist per policy.
- JDWP/JMX ports are not reachable from public networks.
- Logs include request IDs without passwords/tokens/cookies.
- Heap dumps/log files are not served from static web directories.
- Production artifacts contain no dev-only endpoints or public source maps.
- Non-admin users cannot invoke control endpoints.

You can check responses with automated tests:

```sh
curl -i https://app.example.com/api/demo-error
```

Then verify that the body does not contain strings like `java.lang.`, `at com.`, `/opt/app/`, `jdbc:`, `password=`, `Authorization:`, or real tokens. These strings are only search indicators; security checks must consider context to avoid false positives.

Do not run fuzzing or heavy load generation against production without proper planning and approval.

## 22. Common Issues and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Users see HTTP 500 stack traces | Framework is including exceptions/stack traces | Disable error details and use a centralized handler |
| Response contains SQL or database hostname | Exception message is returned directly | Return a generic error code; log sanitized details internally |
| Actuator returns environment/config | Endpoint exposure is too broad or sanitizer is inadequate | Expose only necessary endpoints, authenticate, and verify sanitization |
| Heap dump is downloadable from a public URL | Dump is in a static directory or unprotected endpoint | Move to private storage and restrict permissions |
| JDWP port appears in a public scan | Debug agent binds to wildcard/public interface | Disable JDWP or bind to loopback/private network and close firewall |
| JMX does not require authentication | Remote JMX security is disabled | Enable TLS/client auth/passwords and restrict network access |
| Logs contain tokens or cookies | Logging entire headers/requests | Mask/drop sensitive fields before writing |
| Metrics contain emails/user IDs | Using user data as labels | Use aggregated, low-cardinality dimensions |
| Frontend source maps are accessible | Build/deploy made `.map` files public unintentionally | Keep source maps in a separate error-monitoring service |
| Debug endpoint missing from menus is still accessible | Hard-to-guess URL treated as security | Apply server-side authorization and remove the route |
| Only staging is safe; production still has debug enabled | Wrong deployment profile or environment variable | Inspect effective config and fail deployment when debug is on |
| Forgot to close debug port after incident | No expiry and cleanup owner | Use time-bound changes, tickets, and port-closure verification |
| Actuator security rules stopped working | Custom `SecurityFilterChain` altered auto-configuration | Write explicit endpoint rules and run integration tests |

## 23. Runbook When Public Debugging Is Discovered

If production is found to be exposing debug information:

1. Identify the exposed endpoint/port and accessible data.
2. Collect minimal evidence: URL, timestamp, redacted sample response, source IP, and related logs.
3. Determine whether sensitive data, tokens, credentials, or PII were exposed.
4. Block public access via network/security rules or disable the endpoint per the incident process.
5. Do not delete logs/evidence needed for the investigation.
6. Rotate/revoke credentials if there is a possibility they were exposed.
7. Determine when the exposure started and who could have accessed it.
8. Inspect access logs to identify requests that hit the endpoint.
9. Restore a safe configuration and deploy the fix.
10. Re-verify from an external network perspective.
11. Document the root cause, impact, remediation actions, and preventive measures.

If the endpoint allowed state changes or privileged operations, treat it as a security incident according to your organization's procedures.

## 24. Checklist

- [ ] Production does not enable debug mode, interactive consoles, or debug toolbars.
- [ ] Error responses do not return stack traces, exception messages, or internal paths.
- [ ] Error codes and request IDs are used for internal lookup.
- [ ] Exception logs are stored in an access-controlled system.
- [ ] Logs do not contain passwords, tokens, cookies, connection strings, or private keys.
- [ ] PII and request bodies are collected minimally and masked per policy.
- [ ] Log inputs are sanitized to prevent log injection.
- [ ] Actuator exposes only approved endpoints.
- [ ] Health responses do not return dependency details or secrets.
- [ ] Management endpoints have authentication, authorization, and network controls.
- [ ] JDWP is not exposed to public networks.
- [ ] Remote JMX is disabled or protected with TLS/client certificates and authentication.
- [ ] Heap dumps, thread dumps, and JFR recordings are stored in private storage with retention.
- [ ] Log viewers and configuration dumps are not public.
- [ ] Metrics/traces do not contain PII, tokens, or high-cardinality identifiers.
- [ ] Source maps/debug symbols are not unintentionally public.
- [ ] Admin/debug operations have RBAC, auditing, and approval.
- [ ] Production profile and effective configuration are verified during release.
- [ ] Error/endpoint exposure is tested automatically.
- [ ] Temporary diagnostic access has an owner, expiry, and cleanup step.
- [ ] Credentials are rotated if there is evidence or possibility of exposure.

## 25. References

- OWASP Error Handling Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html
- OWASP Web Security Testing Guide — Improper Error Handling: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/08-Error_Handling/01-Improper_Error_Handling/
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Spring Boot Reference — Actuator Endpoints and Security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Oracle Java Platform Debugger Architecture — Connection and Invocation Details: https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html
- Oracle Java Management — Monitoring and Management Using JMX: https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html
- Oracle Java Management — JMX Security: https://docs.oracle.com/en/java/javase/17/jmx/security.html

Public production debugging increases the risk of exposing system architecture, customer data, and runtime control. Return generic errors with a request ID, store diagnostics in access-controlled logs/observability, restrict Actuator/JMX/JDWP to a protected management plane, and open temporary debug access only under an audited, time-bound incident process.
