# Risks of Secret Exposure via Command Line, Logs, `toString()`, and Error Messages in Spring Boot

## 1. Lesson goal

Spring Boot allows configuring applications via `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, Config Data, and many other `PropertySource`s. This mechanism is convenient for deploying across development, testing, and production environments. However, **putting a secret into configuration does not mean that secret is protected**.

The following values must be treated as sensitive whenever they appear in configuration:

- Passwords for databases, Redis, message brokers, and external services.
- API keys, access tokens, refresh tokens, bearer tokens, and client secrets.
- Private keys, passphrases, signing keys, encryption keys, and secrets used to sign JWTs.
- Connection strings with embedded authentication credentials.
- Session cookies, temporary verification codes, recovery codes, and short-lived credentials.
- Certain internal identifiers or configuration details if disclosure has a security impact.

This lesson focuses on four common leak paths:

1. **Command line**: secrets appearing in launch commands, process arguments, or shell history.
2. **Logs**: secrets printed to application logs, access logs, HTTP client logs, or log aggregation systems.
3. **`toString()`**: a configuration object/DTO containing secrets converted to a string and propagated to logs, debuggers, or exceptions.
4. **Error messages**: exceptions, binding errors, validation, error responses, or diagnostic endpoints accidentally displaying sensitive values.

The ultimate goal is not merely "masking a few characters when logging," but establishing a **lifecycle-wide secret management strategy**: introducing secrets into the application more safely, minimizing use, avoiding output to observability channels, testing for zero leaks, and having a rotation plan when incidents occur.

## 2. Distinguishing secrets from regular configuration

Some configuration can be public within the scope of the system:

~~~yaml
app:
  notification:
    enabled: true
    retry-count: 3
    connect-timeout: 5s
~~~

Other configuration, however, must be protected:

~~~yaml
app:
  integration:
    endpoint: https://api.example.org
    api-key: "DEMO-NOT-A-REAL-SECRET"
~~~

The string `DEMO-NOT-A-REAL-SECRET` is only **fake data for learning**, not a usable credential. In production, do not write real API keys directly into YAML and commit them to Git.

Worth noting: a property like `endpoint` looks non-sensitive, yet the actual URL may contain a username/password, a token in the query string, or signing parameters. Therefore, never judge whether a value is safe to log **based solely on the field name**.

A classic example:

~~~text
https://user:password@example.org/api?access_token=secret
~~~

Both the userinfo portion and the query parameter can disclose credentials. A system that logs full URLs can still leak secrets without ever printing a field named `password`.

## 3. Where secrets can propagate

Initially a secret sits inside a file or secret vault. Once loaded into the application, it can pass through many layers:

~~~text
Secret manager / mounted file / environment / CLI
                     |
                     v
           Spring Environment
                     |
                     v
      Binder / @Value / configuration bean
                     |
             +-------+--------+
             |       |        |
             v       v        v
        HTTP client  Logs   Exception
             |       |        |
             v       v        v
       Remote API  Log system  Error response
                     |
                     v
           Search, export, backup,
           dashboards, alerting
~~~

Each step introduces another trust boundary. For example:

- The secret manager has tight access control, yet the log aggregator is viewable by many staff groups.
- The secret file is only mounted into the container, yet a stack trace is sent to an external monitoring tool.
- End users cannot read configuration, yet an error handler returns the verbatim exception message.
- Data was not committed to Git, yet it ended up in shell history or CI job logs.

Therefore, the security question to ask is: **can the secret be observed, copied, stored, or surfaced outside where it actually needs to be used?**

## 4. Risk 1: passing secrets via command-line arguments

Spring Boot supports command-line properties:

~~~bash
java -jar app.jar --app.integration.api-key=DEMO-NOT-A-REAL-SECRET
~~~

The command above can bind the `app.integration.api-key` property properly. From a security standpoint, however, it carries risks:

- Command-line contents can appear in process management tools or inventory/monitoring systems.
- The shell may save the command into history.
- Job runners or CI/CD may display the command in logs.
- Launch scripts may be saved into repositories, artifacts, or backups.
- Process diagnostic tools may collect command-line arguments.
- Commands may be copied into tickets, chat, or operational docs.

Argument visibility depends on the operating system, permissions, namespaces/containers, and hardening settings; **not every user on every machine can see all arguments**. Still, do not put secrets on the command line simply because your current test machine does not show them to others.

Similarly, Java system properties:

~~~bash
java -Dapp.integration.api-key=DEMO-NOT-A-REAL-SECRET -jar app.jar
~~~

can also appear on the process command line. `-D` and `--app.integration.api-key=...` differ in configuration mechanism, yet **both carry the risk of placing the secret inside the launch command**.

**Principle:** do not use CLI arguments or `-D` to pass real passwords/tokens when a better-supported secret management option is available.

## 5. Shell history, scripts, and development environments

A manual command can get saved:

~~~bash
java -jar app.jar --app.api-key=REAL_SECRET
~~~

Places to check per system policy:

- History of Bash, Zsh, PowerShell, or terminal tools.
- Script files `run.sh`, `start.ps1`, batch files.
- IDE run configurations, launch configurations, debug profiles.
- Task runners, Makefiles, Gradle/Maven command-line options.
- Documentation copy/pasting launch commands in wikis or chat.
- Session recordings on servers, terminal multiplexers, or jump hosts.

Even if you delete a line from history on a personal machine, the value may already have been synced to backups or logs earlier. Therefore, **erasing visible traces does not replace revoking and rotating an exposed secret**.

A better option is letting the runtime read secrets from an authorized managed source at deployment time, rather than typing real values into commands. Even so, the alternative source must also be evaluated for access permissions, storage, and potential logging.

## 6. Environment variables: often useful, yet not an absolute secret vault

Spring Boot can map environment variables into configuration:

~~~text
APP_INTEGRATION_APIKEY
~~~

corresponding to the canonical name:

~~~text
app.integration.api-key
~~~

In many deployment environments, supplying values via environment variables avoids writing secrets directly into `application.yml` or source code. However, environment variables **are not automatically encrypted just because they are called environment variables**.

Possible risks:

- Users with appropriate access to the process/container can read the environment.
- Child processes can inherit the environment if the application or scripts do not restrict it.
- Debugging tools, crash dumps, diagnostics, or container inspection may reveal the environment.
- CI/CD may print the environment if scripts run `env`, `printenv`, or emit debug logs.
- `System.getenv()` or printing the entire environment map in Java leaks values in bulk.
- Values may be configured in manifests or pipelines with long retention.

Never log:

~~~java
System.out.println(System.getenv());
~~~

And avoid:

~~~java
log.debug("Environment variables: {}", System.getenv());
~~~

When using environment variables, restrict process/container read access, avoid passing unnecessary variables to subprocesses, mask logs in pipelines, and avoid dumping full configuration.

**Balanced view:** environment variables can be an appropriate secret-supply mechanism on some platforms, yet they do not replace secret managers, authorization, log controls, and rotation.

## 7. Do not put secrets in `SPRING_APPLICATION_JSON` or URIs without risk assessment

Spring Boot supports many ways to supply configuration; one of them is `SPRING_APPLICATION_JSON`. Fake-data example:

~~~bash
SPRING_APPLICATION_JSON='{"app":{"integration":{"api-key":"DEMO-ONLY"}}}'
~~~

This mechanism is convenient for structured configuration, yet if real secrets are placed into JSON inside an environment variable or command line, the risks of the **underlying transport channel** remain.

Another issue is URI imports or connection strings:

~~~text
https://user:password@service.example.org/
jdbc:postgresql://database.example.org/app?password=secret
~~~

Even without a separate property named `password`, credentials are still inside the URL string. Logging raw URLs, HTTP request targets, or exceptions from connection libraries can leak them.

Recommendations:

1. Prefer authentication mechanisms that separate credentials from URLs.
2. Do not embed tokens in query parameters when an API supports passing them via secure headers.
3. Do not log full connection strings/URIs if they could contain userinfo or sensitive queries.
4. When needing to display an endpoint, construct a safe representation containing only scheme, host, and approved information.
5. Do not assume a URL lacking the word `secret` is safe to print.

## 8. Risk 2: logging configuration values directly

A common mistake:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class IntegrationService {
    private static final Logger log =
            LoggerFactory.getLogger(IntegrationService.class);

    public void connect(String apiKey) {
        log.info("Using API key: {}", apiKey); // UNSAFE
    }
}
~~~

Even when using SLF4J parameterized logging instead of string concatenation, the `apiKey` value is still written to the log when the corresponding log level is enabled. The `{}` syntax **does not perform redaction automatically**.

Similarly:

~~~java
log.debug("Configuration loaded: {}", properties);
log.error("Unable to authenticate with {}", token);
System.out.println("password=" + password);
~~~

if the value or `properties.toString()` contains secrets.

A better approach:

~~~java
log.info("Integration settings loaded; endpoint configured");
log.warn("Authentication failed for integration service");
~~~

If you need to know whether a configuration was provided without disclosing the value:

~~~java
boolean credentialPresent =
        apiKey != null && !apiKey.isBlank();

log.info("Integration credential configured: {}", credentialPresent);
~~~

Still, even the "credential is present" status should be evaluated against the system's sensitivity level. In most applications, logging a boolean presence indicator at INFO is far less risky than logging secret contents.

## 9. DEBUG/TRACE log levels are not safe zones

Some assume that:

~~~java
log.debug("Token: {}", token);
~~~

is safe because production usually runs at INFO.

This is unreliable because:

- DEBUG/TRACE can be enabled temporarily to diagnose incidents.
- A profile configuration may accidentally enable verbose logging in production.
- Tests/CI may run at a lower log level.
- An operator may enable dynamic logging via an authorized management mechanism.
- Emitted logs can persist for a long time in centralized systems or backups.

Secrets should not appear in logs **at any level**, unless under a very specific, tightly controlled security process that never publishes raw values.

Be especially cautious with:

~~~properties
logging.level.root=TRACE
logging.level.org.springframework.web=TRACE
logging.level.org.springframework.http=TRACE
~~~

deep log levels in libraries related to HTTP, security, connections, or configuration. Some libraries have mechanisms to mask sensitive headers/cookies, yet **you should not rely on that as the sole safeguard**. Know precisely what your framework and version log.

## 10. HTTP request and response logging

A REST client may send credentials in headers:

~~~http
Authorization: Bearer DEMO-NOT-A-REAL-TOKEN
X-API-Key: DEMO-NOT-A-REAL-KEY
~~~

If an interceptor is enabled to log the entire request:

~~~java
log.debug("Headers: {}", request.getHeaders()); // UNSAFE
~~~

headers can be exposed.

A safer approach is logging useful information that contains no credentials:

~~~java
log.info(
        "Outbound request method={} targetHost={} status={}",
        method,
        approvedHost,
        status
);
~~~

Obtain `approvedHost` only from controlled data, rather than printing raw URLs that might contain userinfo or queries. For HTTP clients, use an **allowlist** logging configuration: permit only method, status, latency, a few non-sensitive headers, and request ID.

Data that should be masked or excluded from logs if it may contain secrets:

- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie`.
- `X-API-Key` or custom credential headers.
- Tokens in query strings.
- Login, password reset, and OAuth token exchange bodies.
- Multipart uploads containing secret data.
- Response bodies containing access tokens, refresh tokens, or temporary passwords.

For `RestTemplate`, `WebClient`, Apache HTTP Client, OkHttp, or Feign, verify the logging options **of that exact client**. A custom interceptor can bypass the library's default redaction mechanism.

## 11. Structured logging and MDC can still leak secrets

Structured logging typically produces JSON records:

~~~json
{
  "timestamp": "2026-11-12T09:00:00Z",
  "level": "INFO",
  "event": "external_call",
  "requestId": "req-123",
  "status": 200
}
~~~

This structure is easy to search and analyze. Yet JSON does not automatically make logs safe.

Dangerous example:

~~~java
MDC.put("apiKey", apiKey);
MDC.put("authorization", authorizationHeader);
~~~

If the log pattern or JSON encoder is configured to output all MDC entries, these values can appear in every log record for the execution flow.

Put into MDC only data evaluated as appropriate, such as a correlation ID containing no secrets:

~~~java
MDC.put("requestId", requestId);
try {
    log.info("Processing integration request");
} finally {
    MDC.remove("requestId");
}
~~~

Depending on the system, tenant ID, user ID, or request ID may also be sensitive data. Evaluate log access permissions and retention rules instead of treating them as always public.

Do not use a safe-looking field name like `requestId` to store an actual token. Key-name-based redaction mechanisms fail when sensitive data is placed in the wrong field.

## 12. Why "regex masking at the log aggregator" is not enough

Some systems configure filters that replace:

~~~text
password=abcdef
~~~

with:

~~~text
password=******
~~~

This is useful as **an extra layer of defense**, yet does not cover everything:

- Credentials may lack a `password=` prefix.
- Tokens may appear in URLs, JSON, XML, or binary bodies.
- Values may be encoded, truncated, or split across multiple fields.
- A logger or exporter may transmit data before the filter runs.
- Overly broad regexes can strip needed operational info; overly narrow ones miss leaks.
- Logs may be written to local files first before being shipped to the aggregator.

**Priority order:**

1. **Avoid generating logs containing secrets in code from the start.**
2. Design log schemas with an allowlist of permitted fields.
3. Mask/strip sensitive headers, cookies, queries/bodies at the point of logging.
4. Apply redaction filters in the logging framework and pipeline as a supplementary layer.
5. Test with fake secrets and inspect both local logs and aggregator output.

Do not treat a regex rule as an absolute guarantee that all secrets have been removed from the logging system.

## 13. Risk 3: `toString()` of Java objects

A configuration object can hold sensitive information:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String endpoint,
        String apiKey
) {}
~~~

Java records auto-generate a `toString()` displaying their components. If you write:

~~~java
log.info("Integration properties: {}", properties);
~~~

`toString()` can produce a string containing `endpoint` and **the real `apiKey`**. Even though the log statement never calls `properties.apiKey()` directly, the secret can still leak.

Simulated output example:

~~~text
IntegrationProperties[endpoint=https://api.example.org,
apiKey=DEMO-NOT-A-REAL-SECRET]
~~~

Similar risks occur with:

- Lombok `@Data` or `@ToString`.
- IDE-generated `toString()`.
- Kotlin data classes with auto-generated `toString()`.
- Debug/diagnostic libraries converting objects to strings.
- String interpolation: `"config=" + properties`.
- Exception messages containing `properties` or DTOs.

**Principle:** an object containing credentials should not be logged intact.

## 14. Fixing `toString()` on Java records

A simple approach is overriding `toString()`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String endpoint,
        String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[endpoint=<omitted>, apiKey=<redacted>]";
    }
}
~~~

Here:

- The real value of `apiKey` is excluded from the string.
- `endpoint` is also omitted in case the URL contains userinfo or sensitive queries.
- The string still identifies the object being described without disclosing its contents.

Another approach is **not logging the configuration object** and logging only allowlisted fields, for example:

~~~java
log.info("Integration configuration initialized");
~~~

Even with a safe `toString()` override, the secret still exists inside the object and can still be accessed via getters, reflection, debuggers, or serializers. Overriding `toString()` protects only **one output path**, rather than encrypting or hiding the secret from every API.

If a record contains a collection or nested object with secrets, do not inadvertently call `nested.toString()` from a custom implementation.

## 15. Lombok: `@Data` and `@ToString` need review

Lombok helps reduce boilerplate:

~~~java
import lombok.Data;

@Data
public class ApiCredentials {
    private String clientId;
    private String clientSecret;
}
~~~

However, `@Data` includes generating `toString()`; the object can print `clientSecret` as well unless excluded.

One way to reduce risk:

~~~java
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
public class ApiCredentials {

    @ToString.Include
    private String clientId;

    private String clientSecret;
}
~~~

Include `clientId` in `toString()` only if it is non-sensitive under your project's threat model. If even identifiers must be hidden, do not include any data at all.

You can use `@ToString.Exclude` for sensitive fields:

~~~java
@Getter
@Setter
@ToString
public class ApiCredentials {

    private String clientId;

    @ToString.Exclude
    private String clientSecret;
}
~~~

However, an **allowlist** is generally safer than a blocklist: when a developer adds a new `refreshToken` field, `onlyExplicitlyIncluded = true` will not automatically expose that field.

Do not forget to check `toString()` of nested objects/DTOs, not only the root configuration class.

## 16. `equals()`, `hashCode()`, and serialization also need separate evaluation

Lombok `@Data` or Java records can generate `equals()` and `hashCode()` from components. They do not log secrets directly, but may process credential data in ways unsuitable for security goals or cause indirect leaks through instrumentation.

In particular, **hiding a field from `toString()` does not hide it from JSON serialization**:

~~~java
public record IntegrationProperties(
        String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[apiKey=<redacted>]";
    }
}
~~~

If a controller accidentally returns this object:

~~~java
@GetMapping("/config")
public IntegrationProperties config() {
    return properties;
}
~~~

Jackson can serialize the `apiKey` component into JSON depending on mapper configuration. A safe `toString()` **does not prevent** the object from being returned in an HTTP response.

Prevention:

- Never return configuration beans containing secrets directly from controllers.
- Create separate response DTOs with an allowlist of permitted fields.
- Use `@JsonIgnore` where appropriate if an object with a sensitive field must be serialized, without treating it as the sole barrier.
- Avoid custom debug endpoints returning the entire `Environment` or `@ConfigurationProperties`.
- Check serialization of nested objects and maps, not just top-level fields.

## 17. Designing configuration objects with security boundaries

One approach is separating operational configuration from credentials:

~~~yaml
app:
  integration:
    base-url: https://api.example.org
    connect-timeout: 5s
    api-key: "${INTEGRATION_API_KEY}"
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String baseUrl,
        Duration connectTimeout,
        String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[baseUrl=<omitted>, "
                + "connectTimeout=" + connectTimeout
                + ", apiKey=<redacted>]";
    }
}
~~~

`${INTEGRATION_API_KEY}` is a Spring placeholder, not advice to put secret values in `application.yml`. Actual provisioning can use environment variables or a safer secret source.

However, in a large application, having the same object hold both public configuration and secrets increases the chance someone logs the whole object. Consider:

~~~java
public record PublicIntegrationOptions(
        Duration connectTimeout
) {}

public final class IntegrationCredential {
    private final String apiKey;

    public IntegrationCredential(String apiKey) {
        this.apiKey = apiKey;
    }

    public String value() {
        return apiKey;
    }

    @Override
    public String toString() {
        return "IntegrationCredential[redacted]";
    }
}
~~~

The `IntegrationCredential` class still provides `value()` for integrating with an HTTP client. It does not stop every leak path, but prevents logging the object from immediately exposing its content by accident.

For secrets with special lifecycles, limit access scope by injecting credentials only into components that genuinely need to use them.

## 18. Risk 4: error messages and exceptions

A frequent mistake when calling APIs:

~~~java
try {
    callPartner(apiKey);
} catch (RuntimeException ex) {
    throw new IllegalStateException(
            "Partner API failed with key=" + apiKey, ex
    );
}
~~~

That statement creates an exception message containing the credential. When the exception is logged with:

~~~java
log.error("Partner integration failed", exception);
~~~

or returned in an HTTP error, the secret can be disclosed.

Replace with a message containing no secret data:

~~~java
try {
    callPartner(apiKey);
} catch (PartnerAuthenticationException ex) {
    log.warn("Partner authentication failed; code={}", ex.errorCode());
    throw new IntegrationUnavailableException(
            "Partner authentication failed"
    );
}
~~~

Here `ex.errorCode()` must be an **allowlisted error code containing no secret**, not an arbitrary raw message from the remote service. The exception classes in the example are application-defined.

Preserving `cause` is sometimes necessary for diagnostics, yet **the cause chain can also contain credentials**. If you know an underlying exception contains sensitive data, do not log full stack traces to broadly accessible channels by default. Separate controlled diagnostic mechanisms or normalize messages at an appropriate boundary.

Do not solve this by swallowing all exceptions and returning fake success results; keep error signals and useful information without leaking secrets.

## 19. Do not concatenate verbatim remote responses into exceptions

An HTTP client may receive an error such as:

~~~json
{
  "error": "invalid_token",
  "detail": "Token DEMO-NOT-A-REAL-TOKEN was rejected"
}
~~~

If the application writes:

~~~java
throw new IllegalStateException(
        "Remote API error: " + responseBody
);
~~~

it can transfer the secret from the response body into the exception message, and from there into logs, alerts, and error responses.

How to handle:

1. Parse the response according to a known schema.
2. Record only approved **error codes or statuses**.
3. Do not display the full response body to end users.
4. If deep diagnostics are needed, use protected storage with tested redaction.
5. Avoid using `ex.getMessage()` as public response content.

Example:

~~~java
log.warn(
        "Partner request rejected: status={}, category={}",
        statusCode,
        safeCategory
);
~~~

`safeCategory` must be mapped from a defined set of values such as `AUTHENTICATION`, `RATE_LIMIT`, or `REMOTE_ERROR`. Do not treat an arbitrary string from the other party as safe just because it is named `errorCode`.

## 20. Spring Boot binding failures can contain configuration data

A configuration class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        Duration timeout,
        String apiKey
) {}
~~~

If a property has a value of the wrong type:

~~~properties
app.integration.timeout=not-a-duration
~~~

binding `Duration` can fail. Depending on the Spring Boot version, the error message may show:

- Property name.
- Offending value.
- Target Java type.
- Origin (e.g. filename and line).
- Conversion or validation cause.

For ordinary properties, this information is helpful. Yet if the bound field is a secret, **do not assume every exception automatically masks the value**.

Example to avoid in a custom error handler:

~~~java
catch (Exception e) {
    log.error("Configuration failure: {}", e.getMessage());
}
~~~

if `e.getMessage()` could contain sensitive property content.

Some Spring Boot components provide sanitization for diagnostic endpoints; this is no guarantee that **every exception path or every custom logger** sanitizes under the same policy.

Do not build security on the belief that a keyword like `password` is guaranteed to be masked across the entire stack.

## 21. Bean Validation and constraint messages

`@Validated` can be used to reject invalid configuration:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotBlank String apiKey
) {}
~~~

If `apiKey` is blank, validation can fail when the bean is created. This protects credential presence, **not values from appearing in logs**.

Some validation reports or error reporting tools may display the rejected value depending on the handling path. Therefore:

- Do not put secrets into constraint message templates.
- Do not write custom validators that throw exceptions containing secrets.
- Do not log entire validation error objects if they could retain rejected values.
- Avoid displaying rejected values in APIs or user interfaces.
- Ensure startup configuration logging does not accidentally expose secrets.

Constraint messages should be simple:

~~~java
@NotBlank(message = "Integration credential must be configured")
String apiKey
~~~

Do not write messages following a template that echoes the real value of `apiKey`.

## 22. Error responses: do not return exception messages directly to clients

Dangerous controller exception handler example:

~~~java
@RestControllerAdvice
public class UnsafeErrorHandler {

    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handle(Exception ex) {
        return ResponseEntity
                .internalServerError()
                .body(ex.getMessage()); // UNSAFE
    }
}
~~~

If a lower-layer exception contains a password, token, or connection string, the API caller can receive that value.

Safer direction:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(IntegrationUnavailableException.class)
    public ResponseEntity<ApiError> handleIntegrationFailure(
            IntegrationUnavailableException ex) {

        return ResponseEntity
                .status(HttpStatus.BAD_GATEWAY)
                .body(new ApiError(
                        "UPSTREAM_UNAVAILABLE",
                        "Integration service is temporarily unavailable"
                ));
    }

    public record ApiError(String code, String message) {}
}
~~~

`IntegrationUnavailableException` must be declared as an application exception. Crucially, the response has only a **stable error code** and an **approved message**, never copying verbatim messages/causes from libraries or remote systems.

For other exception types, use an appropriate handler and do not return stack traces in production. Do not send raw `Exception` or `Throwable` objects back to clients.

## 23. Spring Boot error endpoint and stack traces

Spring Boot provides error handling for web applications. Options such as including messages, binding errors, or stack traces in error responses vary by version and configuration.

For production, prefer not outputting stack traces and internal exception details in responses. Illustrative configuration for Spring Boot 3.x:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

These options help reduce details in the default error response, yet **do not automatically govern custom `@RestControllerAdvice`s**, loggers, or third-party libraries.

A custom exception handler can ignore the settings above and return `ex.getMessage()` even when the default error endpoint is safely configured.

Therefore, test real error paths, especially:

- Upstream authentication failures.
- JDBC/Redis connection failures.
- Configuration binding failures at startup.
- Token parsing failures.
- Validation failures.
- Unexpected controller errors.

The goal is for the client to receive enough information to know the request failed, without receiving credentials or unnecessary internal details.

## 24. Actuator `env` and `configprops`

Spring Boot Actuator provides endpoints for inspecting configuration. Two notable endpoints:

- `/actuator/env`: information about environment/property sources.
- `/actuator/configprops`: `@ConfigurationProperties` beans and corresponding configuration values within permitted endpoint scope.

Spring Boot has sanitization mechanisms and value display policies for these endpoints, yet **do not treat having a sanitizer as enough to expose them publicly on the Internet**.

Example configuration restricting exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Meaning:

- Web exposure allows only the required endpoint group in the example.
- Value display policy for `env` and `configprops` is set strictly.
- Other endpoints, such as `heapdump` or diagnostic tools, must be controlled separately if enabled.

Exact property names and detailed behavior can vary by Spring Boot/Actuator version. When deploying, read the documentation for the **exact running version** and inspect the actual security configuration.

Even when an endpoint only displays property names without values, names can reveal system structure. Access limits, network protection, and audit observability remain necessary.

## 25. Other diagnostic endpoints can also contain secrets

Not just `env` and `configprops`. Some operational support tools can expose:

- Heap dumps.
- Thread dumps.
- System diagnostics.
- Runtime metrics with custom tags/labels.
- HTTP trace/observation of request details.
- Log level management.
- Profiling and crash reports.

Heap dumps can contain secret strings still in JVM memory. A metric label containing tokens or customer names can also leak data while creating uncontrolled cardinality.

When enabling these tools:

1. Define who can access them.
2. Restrict networks and authentication/authorization.
3. Restrict where dump/report files are stored.
4. Define retention and deletion workflows.
5. Never put secrets into metric tags or trace attributes.
6. Monitor downloads of diagnostic artifacts.

Masking a value in `toString()` does not remove it from JVM memory. Log redaction and memory dump protection are two separate layers.

## 26. Using Config Data and mounted secret files

One operational option is placing secrets in files mounted with appropriate permissions and letting Spring Boot read them via **configuration tree**.

Example structure:

~~~text
/run/secrets/
  app.integration.api-key
~~~

The contents of `/run/secrets/app.integration.api-key` are **the secret value** (not the property name). In application YAML:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Once the config tree source is loaded and named properly, the filename `app.integration.api-key` can become a property usable by the Binder:

~~~java
@Value("${app.integration.api-key}")
private String apiKey;
~~~

This example illustrates the loading mechanism only. Keep in mind:

- Secret files must not be committed to the repository.
- Mounts should have minimal read permissions matching the process user.
- Avoid placing secret files in directories served by a web server or static resource handler.
- Do not log paths along with contents or dump the whole directory.
- Use the platform's secret management mechanism to provision/revoke/rotate.
- `optional:` allows the import to be absent without failing location lookup; **it does not automatically make the credential optional**. For required secrets, use validation or omit `optional:` depending on the deployment contract.

Depending on OS, container, and mount method, secret files can still be read by sufficiently privileged processes or included in backups/diagnostics. Mounted files are safer than CLI arguments in many contexts, yet do not eliminate all risks automatically.

## 27. Docker: avoid secrets in images and build commands

Ways secrets easily leak:

~~~dockerfile
# UNSAFE - example to avoid
ENV APP_INTEGRATION_APIKEY=REAL_SECRET
~~~

or:

~~~dockerfile
# UNSAFE - example to avoid
ARG API_KEY
RUN echo "$API_KEY" > /opt/app/key.txt
~~~

These values can appear in image layers, build caches, metadata, history, or artifacts depending on the build setup.

Principles:

- Never bake real secrets into container images.
- Never commit `.env` containing real credentials to Git.
- Never pass secrets via ordinary build arguments when they can leave traces in metadata/layers.
- When a secret is needed strictly at build time, use a platform-supported **build secret mount** mechanism and inspect output artifacts.
- For runtime, use a secret store or appropriate mount instead of putting secrets into the Dockerfile.

Conceptual runtime mount example:

~~~text
Container filesystem:
/run/secrets/app.integration.api-key
~~~

The application reads via Config Data as in the previous section. Secrets do not need to be inside the image for the application to start.

Protect the host/container runtime, mount locations, read permissions, and inspection tools as well. Using a directory named `/run/secrets` provides no protection on its own if files are given overly broad permissions.

## 28. Kubernetes Secrets and common misconceptions

Kubernetes supports the `Secret` resource to supply sensitive data to Pods as environment variables or volume mounts. Keep in mind:

- `data` values in Secret YAML are represented in Base64; **Base64 is not security encryption**.
- Permission to read Kubernetes Secrets through the API must be restricted with RBAC.
- Consider encryption at rest in etcd per cluster policy.
- Manifests containing encoded values still should not be shared casually.
- Environment injection carries its own process-environment risks.
- Volume mounts require protecting filesystem permissions and Pod scope.

Example Pod reading a secret mounted as a file:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: integration-demo
spec:
  containers:
    - name: app
      image: example/integration:1.0
      volumeMounts:
        - name: app-secrets
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: app-secrets
      secret:
        secretName: integration-credentials
~~~

This illustrates the mount path, assuming the `Secret` resource exists and the application/file format is configured accordingly. In a real system, also implement security contexts, service accounts, RBAC, image hardening, and network policies as required.

If the application uses `spring.config.import=configtree:/run/secrets/`, ensure filenames inside the Secret volume produce the exact property names to bind, or use an appropriate key-to-path mapping mechanism.

## 29. Secret managers: decoupling credential lifecycle from source code

When supported by the platform, a dedicated secret vault can provide:

- Access control based on workload identity.
- Access auditing.
- Versioning and rotation.
- TTLs or short-lived credentials.
- Encryption key management.
- Incident revocation policies.

Systems may use dedicated integrations to load secrets into Spring Boot, such as Config Data integration, mounted files, SDKs, or sidecars.

However, using a secret manager **does not automatically make code secure**. After loading into the JVM, values can still be sent out via:

~~~java
log.info("secret={}", secret);
~~~

or:

~~~java
throw new RuntimeException("secret=" + secret);
~~~

to unauthorized channels.

Thus, the secret manager handles **credential provisioning and governance**; the application must still ensure **safe usage and non-disclosure** across logging, serialization, and error handling.

## 30. Profile-based configuration must not be used to hide secrets in repositories

There may be files:

~~~text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
~~~

A design mistake:

~~~yaml
# application-prod.yml - UNSAFE
app:
  integration:
    api-key: "REAL_PRODUCTION_SECRET"
~~~

thinking the file is only used when the production profile is active so nobody else will see it. In reality, the file can still be:

- Committed to Git.
- Present in build artifacts.
- Packaged into the JAR.
- Copied to other environments.
- Read by anyone with access to the repository or artifact.

Profiles affect **which configuration is activated at runtime**, not a security boundary for secrets in source code.

A better setup keeps only non-sensitive settings in profile files while supplying credentials via deployment mechanisms:

~~~yaml
app:
  integration:
    connect-timeout: 5s
    api-key: "${INTEGRATION_API_KEY}"
~~~

And use validation to reject missing required keys. If a secret ever enters Git, deleting it in a new commit is not enough; review the entire history and rotate it.

## 31. Logging "configuration loaded successfully" safely

A startup log is often written like:

~~~java
log.info("Loaded config: {}", properties);
~~~

This is convenient yet risky if credentials are added to the class in the future.

Replace with an allowlist log:

~~~java
log.info(
        "Integration config ready; timeoutSeconds={} featureEnabled={}",
        properties.connectTimeout().toSeconds(),
        properties.featureEnabled()
);
~~~

Assuming `connectTimeout` and `featureEnabled` are approved as non-sensitive. Do not include `apiKey` in the log.

A better variant is creating a dedicated diagnostic method or DTO:

~~~java
public record IntegrationDiagnostics(
        boolean configured,
        long timeoutSeconds
) {}
~~~

In the service:

~~~java
IntegrationDiagnostics diagnostics =
        new IntegrationDiagnostics(
                credential != null && !credential.isBlank(),
                properties.connectTimeout().toSeconds()
        );

log.info("Integration diagnostics: {}", diagnostics);
~~~

If even the `configured` status is sensitive information, omit it from diagnostics. "Allowlist" means recording only information that has been evaluated and is genuinely necessary.

Do not create a diagnostic object containing secrets and rely on `@JsonIgnore` to "save" every logging path, because `toString()` and JSON serialization are two different mechanisms.

## 32. Do not arbitrarily use plain hashes to replace secrets in logs

Some propose:

~~~java
log.info("apiKeyHash={}", sha256(apiKey));
~~~

to make correlating the same credential across requests easier.

This can reduce printing the secret directly, yet **it is not always safe**:

- Low-entropy secrets can be guessed via hash attacks.
- Stable hashes can become tracking identifiers across multiple systems.
- Logs can still disclose relationships between requests using the same credential.
- Some sensitive data, such as short OTP codes, must never be publicly hashed because they can be brute-forced.

If correlation is genuinely needed, prefer a separately issued non-sensitive identifier, or use an HMAC with a properly managed key and a clear threat model. In many cases, a request ID is sufficient.

Never log passwords, API keys, or tokens verbatim, in Base64, or in homegrown "encryption". **Base64 is encoding, not redaction.**

## 33. Exception `toString()` and nested cause chains

An exception can print information in multiple ways:

~~~java
log.error("Failure: {}", exception);
log.error("Failure", exception);
throw new IllegalStateException("Failure", exception);
~~~

These are not completely equivalent:

- `exception.toString()` typically includes the class name and message.
- A logger with a throwable argument can output the stack trace and nested causes.
- An exception wrapped as a cause still retains information from the original exception, which may be logged later.

For example, JDBC or HTTP client errors sometimes have messages containing URIs, queries, headers, or response bodies. Never assume any library never prints sensitive data.

The solution is **reducing sensitive data placed into exceptions from the start**, using safe error codes, and restricting where full stack traces are output. For incidents requiring deep forensics, a dedicated security process can store diagnostic details in an access- and retention-controlled system, while still evaluating whether collecting secrets is truly necessary.

## 34. Designing a safe exception class

A business exception class can hold only an error code and a fixed message:

~~~java
public final class IntegrationUnavailableException
        extends RuntimeException {

    private final String errorCode;

    public IntegrationUnavailableException() {
        super("External integration is temporarily unavailable");
        this.errorCode = "UPSTREAM_UNAVAILABLE";
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

In the service:

~~~java
try {
    remoteClient.call();
} catch (RemoteClientException e) {
    log.warn("Upstream call failed; code=UPSTREAM_UNAVAILABLE");
    throw new IntegrationUnavailableException();
}
~~~

The example assumes `RemoteClientException` and `remoteClient` are provided by the project. Safe exception classes keep no secrets in messages.

Do not use a fixed message and lose all debugging capability: log request IDs, approved service names, status codes, latency, and categories. Those details are usually enough to correlate events in an access-controlled observability system.

One principle: **exception messages and API error messages should be treated as content that can be widely distributed**, never as places to hold data that must remain secret.

## 35. Reading configuration with `@Value` or `@ConfigurationProperties` both carry output risk

Both ways:

~~~java
@Value("${app.integration.api-key}")
private String apiKey;
~~~

and:

~~~java
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(String apiKey) {}
~~~

bring secrets into JVM memory. Choosing one over the other does not automatically solve logging issues.

`@ConfigurationProperties` helps with configuration schemas, typed binding, validation, and testability. Yet Java record auto `toString()` can expose credentials if the entire record is logged.

`@Value` is often simple for a single scalar, yet if a logger is written right inside the class holding the field:

~~~java
log.debug("apiKey={}", apiKey);
~~~

it still leaks.

The security focus must be placed on **how data is used**, not solely on the annotation that reads the property.

## 36. Avoid printing the entire `Environment` and `PropertySource`s

Some debugging utilities write:

~~~java
for (PropertySource<?> source : environment.getPropertySources()) {
    log.debug("Source: {}", source);
}
~~~

Even if a particular `PropertySource`'s `toString()` does not print every value, this style of debugging is still a bad idea if code starts iterating and logging all keys/values.

A genuinely dangerous example:

~~~java
for (String key : knownPropertyNames) {
    log.info("{}={}", key, environment.getProperty(key));
}
~~~

If the list contains `app.integration.api-key`, it gets logged directly.

Prefer:

~~~java
log.info("Configuration initialized successfully");
~~~

Or emit a list of **approved property names** without values if you only need to diagnose which keys are present. For secrets, even the property name or presence status should be evaluated for sensitivity and log access permissions.

Never write a "dump all config" utility for use in production just because it makes local debugging faster.

## 37. Testing for zero leaks with `OutputCaptureExtension`

Spring Boot Test provides `OutputCaptureExtension` to capture output in tests, useful for verifying a logging path **does not contain a fake secret**.

Java example:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class SafeLoggingTest {

    @Test
    void shouldNotLogSecret(CapturedOutput output) {
        String fakeSecret = "TEST_ONLY_SENTINEL_KEY_12345";

        IntegrationCredential credential =
                new IntegrationCredential(fakeSecret);

        System.out.println("Credential object: " + credential);

        assertThat(output.getOut())
                .doesNotContain(fakeSecret);
    }
}
~~~

This example tests the `toString()` of `IntegrationCredential` from earlier; its implementation returns `[redacted]`.

Tests use a fake sentinel value—**never use real credentials in test logs**. Use a unique, easily recognizable fake string to check for leaks across multiple output paths.

Note: `CapturedOutput` only observes streams/logs attached to the test output infrastructure. If the application uses custom appenders, asynchronous exporters, or ships logs to a remote service, write separate tests for those paths.

## 38. Testing `toString()` and serializers separately

A `toString()` test:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class IntegrationPropertiesTest {

    @Test
    void toStringMustNotExposeSecret() {
        String fakeSecret = "TEST_ONLY_SENTINEL_SECRET";

        IntegrationProperties props = new IntegrationProperties(
                "https://api.example.org",
                fakeSecret
        );

        assertThat(props.toString())
                .doesNotContain(fakeSecret);
        assertThat(props.toString())
                .contains("<redacted>");
    }
}
~~~

For the test above to pass, `IntegrationProperties` must have the `toString()` override defined in section 14.

Yet this test **does not check JSON**. With Jackson or whatever serializer framework the application uses, an independent test is needed:

~~~java
String json = objectMapper.writeValueAsString(props);

assertThat(json).doesNotContain(fakeSecret);
~~~

If the serializer still outputs `apiKey`, fix the API DTO or serialization configuration rather than only adjusting `toString()`.

For error responses, add an integration test calling an error-producing endpoint and assert:

~~~java
assertThat(responseBody)
        .doesNotContain("TEST_ONLY_SENTINEL_SECRET");
~~~

Do not treat a single `toString()` test as sufficient to prove the entire system does not leak.

## 39. Testing error handling flows

A test strategy can include:

1. Supplying a fake secret as configuration for the test application.
2. Intentionally triggering an error in the mock HTTP client.
3. Verifying the response contains only a safe error code and message.
4. Verifying captured logs contain no fake secret.
5. Verifying business exception messages contain no secrets.
6. Checking structured log fields and trace attributes if supported by the system.
7. Testing error responses in a production-like configuration environment.

A test can use a mock service returning a fake error containing the sentinel:

~~~text
Remote error: token TEST_ONLY_SENTINEL_SECRET rejected
~~~

If the code copies the raw response body into `IllegalStateException` or `ApiError`, the test will catch the sentinel appearing.

Do not only assert HTTP status 500 or 502; **a matching status does not prove the response body was sanitized**.

For pipelines shipping logs outside the test runner, use a dedicated observability environment or contract tests to check what values are emitted.

## 40. Centralized logging and retention

Even if a log is written once for a few seconds, it can be replicated:

~~~text
Application stdout
      |
      +--> Container log
      |
      +--> Log collector
      |
      +--> Search cluster
      |
      +--> Alert notification
      |
      +--> Archived object storage
      |
      +--> Support ticket / exported report
~~~

Each copy makes incident remediation harder. Systems may have different retention, backups, immutable storage, and access permissions.

Controls:

- Restrict logs following the principle of least privilege.
- Define appropriate retention.
- Limit exports and log-sharing permissions.
- Protect accounts of log collectors and alerting systems.
- Never put secrets into alert messages, emails, or chat notifications.
- When a secret leak is detected, inventory every place logs were copied.

Do not assume deleting a log line from a dashboard deletes every copy or backup. That is why **preventing data from entering logs initially** is far more valuable than post-incident cleanup.

## 41. Detecting and responding when secrets have leaked

If a real token/password is found to have appeared on the command line, in logs, exceptions, or source code, handle it as a security incident potentially affecting credentials.

General workflow:

1. **Assess the secret type and its permissions**: what token is it, what scope, is it still valid?
2. **Revoke or rotate** the credential promptly per incident procedure and system capabilities.
3. **Determine exposure scope**: CLI, shell history, CI logs, application logs, log aggregators, error tracking, tickets, backups.
4. **Restrict access** to exposed data, prioritizing not creating extra copies during investigation.
5. **Update the application** to eliminate the leak path before deploying new credentials.
6. **Review audits** for unusual credential usage if supported by the system.
7. **Clean up data and record the incident trail** per organizational policy, retention rules, and legal requirements.
8. **Add tests/guardrails** to prevent recurrence.

Do not simply replace text in logs with `****` and consider the credential safe again. An exposed secret may already have been read, saved, or copied earlier.

For private keys or credentials used across multiple environments, rotation may require broader coordination and avoiding service disruption. The goal is handling the actual blast radius, not hastily erasing traces.

## 42. Guardrails in code review and CI

Principles to include in code review:

- Never put real passwords/tokens into `application*.yml` or `application*.properties` in the repository.
- Never log configuration objects containing secrets.
- Never use `@Data` or auto `toString()` on credential DTOs without controls.
- Never return `exception.getMessage()` directly to users.
- Never log full HTTP headers, query parameters, or sensitive response bodies.
- Never put secrets into MDC, metric tags, or trace attributes.
- Never use `--password=...` in operational scripts.
- Never print the environment or entire Spring `Environment` when debugging.
- Have tests using sentinels for at least the highest-risk paths.
- Have rotation mechanisms and an incident response procedure.

CI can use secret scanning to search for suspected credential strings in repositories and artifacts. However, secret scanners are imperfect and have false positives/false negatives, so reviews and rules against using real secrets in tests remain necessary.

Do not put real credentials into CI reports to prove a scanner works. Use tool-recommended test strings or harmless sentinels.

## 43. Summary table of the four main leak sources

| Channel | Unsafe example | Cause | Resolution |
| --- | --- | --- | --- |
| Command line | `--app.api-key=secret` | Value can appear in arguments, history, job logs | Supply via appropriate secret source; avoid CLI |
| Java system property | `-Dapp.password=secret` | Still part of the command line | Use a secret-supply mechanism not in the command string |
| Environment dump | `log.info("{}", System.getenv())` | Prints many sensitive values | Never dump the entire environment |
| Application log | `log.info("token={}", token)` | Logs secret directly | Log only non-sensitive status/error codes |
| HTTP log | Logging `Authorization`/`Cookie` | Headers/bodies carry credentials | Allowlist fields; omit sensitive headers/bodies |
| MDC/structured log | `MDC.put("apiKey", key)` | Value spreads to every log record | Never put secrets in MDC |
| Record `toString()` | `log.info("{}", properties)` | Records print components by default | Do not log bean; override/redact |
| Lombok `@Data` | DTO containing password | Auto `toString()` can print field | Use include-only or explicit exclude |
| JSON response | Returning credential bean | Serializer does not use `toString()` | Allowlisted response DTO |
| Exception message | `"Failed with key=" + key` | Secret enters stack trace/logs | Fixed message and safe error code |
| Error controller | `return ex.getMessage()` | Client receives verbatim exception | Response contains no internal details |
| Binding failure | Invalid value causes error | Diagnostics may contain attempted value | Control logging/triage; do not log raw exceptions casually |
| Actuator | Broadly exposing `env/configprops` | Configuration can be observed | Restrict exposure, sanitize, RBAC |
| Dump/diagnostics | Heap dump contains secret | Secret still in memory | Protect dump paths, retention, and access |

This table is not an exhaustive list of every leak channel; these are the most common situations when an application reads secrets from Externalized Configuration and uses them in operations.

## 44. A sample Spring Boot design moving toward safer practices

Requirements:

- App needs to call an API with credentials.
- Runtime supplies the credential via a mounted file.
- Secret must not appear in `application.yml` or startup logs.
- Want fail-fast when the credential is missing.
- Want error responses to contain no credentials.

Configuration:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"

app:
  integration:
    connect-timeout: 5s

server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

With mounted file:

~~~text
/run/secrets/app.integration.api-key
~~~

Configuration record:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotNull Duration connectTimeout,
        @NotBlank String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[redacted]";
    }
}
~~~

Registration:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Usage:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PartnerGateway {
    private static final Logger log =
            LoggerFactory.getLogger(PartnerGateway.class);

    private final IntegrationProperties properties;

    public PartnerGateway(IntegrationProperties properties) {
        this.properties = properties;
    }

    public void sendRequest() {
        log.info(
                "Preparing partner request; timeoutSeconds={}",
                properties.connectTimeout().toSeconds()
        );

        // Pass properties.apiKey() to the HTTP client via the
        // corresponding authentication mechanism; do not log it.
    }
}
~~~

The application requires a Bean Validation provider, typically `spring-boot-starter-validation` in Spring Boot 3.x. The example using config tree **does not include all TLS, network, or access control configuration** of a production system; those are separate deployment responsibilities.

The protective layers in the example complement one another:

1. Secrets are not hardcoded in source.
2. Secrets are supplied via files with deployment permissions.
3. `@Validated` catches blank credentials.
4. `toString()` does not print credentials.
5. Logs only use timeout — assumed to be evaluated as non-sensitive.
6. Default error responses are restricted.
7. Actuator web exposure is narrowed.

If the HTTP client layer still logs full request headers, the entire design above can be undermined. Protect **the actual path where the secret is used**, not just startup configuration.

## 45. Practice exercises

### Exercise 1 — Identifying command-line risk

Given the command:

~~~bash
java -Dapp.integration.api-key=DEMO-KEY -jar app.jar
~~~

Question: Why should secrets not be supplied this way?

**Answer:** the value sits in the command-line string and can appear in process inspection, shell history, or job runner logs, depending on permissions and platform. Use an appropriate secret source and control access instead of passing real credentials on the CLI.

### Exercise 2 — Does parameterized logging automatically mask tokens?

~~~java
log.debug("Authorization token: {}", token);
~~~

Question: Does `{}` auto-redact?

**Answer:** no. This is a parameter formatting mechanism. When the log level permits writing, the token value can be written to the log. Never log tokens at any level.

### Exercise 3 — Java record and `toString()`

~~~java
public record Credentials(String username, String password) {}
~~~

~~~java
log.info("Credentials: {}", credentials);
~~~

Question: What is the risk?

**Answer:** the record's auto-generated `toString()` can print `password` too. Do not log the object directly; use a safe diagnostic representation or override `toString()` to exclude secrets.

### Exercise 4 — Lombok `@Data`

A DTO has `@Data` and a `refreshToken` field. State how to reduce the risk.

**Answer:** avoid `@Data` if all of its behaviors are not needed, or use `@ToString(onlyExplicitlyIncluded=true)` with an allowlist of permitted fields. Also check JSON serialization, because masking `toString()` does not stop the field from being serialized.

### Exercise 5 — Exception message

~~~java
throw new IllegalStateException(
        "API key is invalid: " + apiKey
);
~~~

Question: According to what principle should this be fixed?

**Answer:** the message should be fixed and contain no credential value, such as `"Partner authentication failed"`, paired with a safe error code/correlation ID if needed; never log raw messages/causes that may contain secrets.

### Exercise 6 — Checking error endpoints

A controller returns:

~~~java
return ResponseEntity.status(500).body(ex.getMessage());
~~~

Question: Why is configuring `server.error.include-message=never` not enough?

**Answer:** a custom handler builds the response directly from the exception, bypassing the default error endpoint's behavior. Fix the handler to return an allowlisted error DTO and test that the response contains no sentinel secret.

### Exercise 7 — Secrets in profiles

`application-prod.yml` contains the real API key and is activated only in production. Is it safe to commit?

**Answer:** no. Profiles only control which configuration sources are selected at runtime; they do not stop people with access to the repository/JAR from seeing the file. Secrets must be supplied through appropriate deployment mechanisms.

### Exercise 8 — Actuator

A system exposes `/actuator/env` and `/actuator/configprops` publicly, trusting that the framework sanitizes them. What should be done?

**Answer:** restrict web exposure, authentication/authorization, value display policies, network access, and test the actual endpoints. Sanitization is no reason to expose diagnostic endpoints publicly.

### Exercise 9 — Are environment variables completely secure?

A system supplies `APP_INTEGRATION_APIKEY` via environment. Do we still need to care about `System.getenv()`, crash dumps, or CI logs?

**Answer:** yes. The environment is a value-provisioning channel, not an automatically encrypted secret store. Access control, avoiding dumps, and controlling diagnostic tools are still required.

### Exercise 10 — Testing with fake secrets

Propose how to test that logs do not print an API key.

**Suggested answer:** use a fake sentinel string such as `TEST_ONLY_SENTINEL_SECRET`, trigger the relevant request or exception path, use `OutputCaptureExtension` or a test appender to capture logs, and assert the sentinel is absent. Write separate tests for JSON responses and trace attributes.

### Exercise 11 — A secret already appeared in logs

A real token was accidentally written to the log aggregator. Is deleting the log from the dashboard enough?

**Answer:** no. Assess the impact, revoke/rotate the token, locate where data was replicated, and fix the code so it stops leaking. Deleting visible logs does not mean every copy/backup has vanished.

### Exercise 12 — Difference between redaction and secret management

A service uses a secret manager yet still writes:

~~~java
log.info("Secret loaded: {}", apiKey);
~~~

Question: Has the secret manager solved the problem?

**Answer:** no. A secret manager governs provisioning/access permissions/rotation; code can still expose the value when using it. Remove secret logging and control every output path.

## 46. Pre-production deployment checklist

### Provisioning sources

- [ ] No real secrets in Git, Dockerfiles, image layers, or packaged config files.
- [ ] Do not pass real secrets via command line or Java `-D` when a better option exists.
- [ ] Runtime obtains credentials from a controlled managed source.
- [ ] Secret read permissions follow the principle of least privilege.
- [ ] Policies exist for revocation, rotation, and credential access auditing.
- [ ] Do not use Base64 as an encryption solution.

### Code and object model

- [ ] Do not log secrets directly or indirectly via `toString()`.
- [ ] Records, Lombok DTOs, and nested objects have safe string-representation policies.
- [ ] Do not return configuration beans containing secrets from controllers.
- [ ] Do not put secrets into metrics, MDC, or trace attributes.
- [ ] Do not concatenate secrets into exception messages.
- [ ] Use allowlisted error codes and diagnostics.

### Web, HTTP, and logs

- [ ] HTTP clients do not log Authorization/Cookie/token queries/bodies.
- [ ] Access logs and structured logging are reviewed for sensitive fields.
- [ ] Error responses do not return `ex.getMessage()` or internal stack traces.
- [ ] Actuator diagnostic endpoints are restricted and tested.
- [ ] Log aggregators, alerting, and backups have appropriate authorization and retention.
- [ ] Redaction filters are a supplementary layer, not a replacement for safe code.

### Testing and response

- [ ] Tests exist with sentinel secrets for logs and `toString()`.
- [ ] Tests exist for JSON serialization and error responses.
- [ ] Integration tests exist with real loggers/HTTP clients if interceptors are used.
- [ ] An incident response procedure exists for exposed credentials.
- [ ] A coordinated rotation plan exists when secrets span multiple systems.

This checklist does not mean a system is certified secure; it helps development teams avoid common leak paths in the Spring Boot configuration lifecycle.

## 47. Takeaways

- **Externalized Configuration changes the supply source; it does not automatically protect secrets** once values are loaded into the application.
- **Command-line arguments and Java `-D`** can leak in process inspection, shell history, CI logs, and diagnostic tools.
- **Environment variables** are convenient, yet still require access management, avoiding dumps, and not being treated as an absolute secret store.
- **Parameterized logging with `{}` does not auto-redact**; never log tokens/passwords even at DEBUG/TRACE.
- **Record `toString()` and Lombok `@Data`/`@ToString`** can expose credential fields when logging objects.
- **A safe `toString()` does not mean safe JSON serialization**; controllers must use allowlisted response DTOs.
- **Exception messages, nested causes, validation, and binding errors** can carry sensitive data; never copy them verbatim into logs or API responses.
- **Actuator and diagnostic dumps** need restricted access, web exposure limits, retention policies, and value-display controls.
- **Secret managers/mounted files** manage the supply source, yet do not prevent code itself from logging secrets.
- **Preventing secrets from entering logs initially** matters more than only masking at the aggregator.
- If a secret leaks, **assess scope, revoke/rotate, and fix the leak path**, rather than only erasing visible traces.
- Test using **fake sentinels**, never real credentials, to verify redaction.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Config Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
