# Distinguishing Baggage from Tags and Controlling Data Propagated Across Services

## 1. Starting from a Request Traversing Multiple Services

Suppose a request follows `checkout → inventory → shipping`. The operations team needs to know whether the request originated from the `web` or `mobile` channel, and also wants to find failed stock reservations at `inventory`.

These two needs lead to two separate decisions:

- Which data must travel with the request so downstream services can read it?
- Which data must be recorded on a span for searching and analysis?

**Baggage** is a set of key-value pairs traveling with the execution context; a **span tag**, also called a span attribute, describes a single span. Writing `channel=web` into baggage does not mean it has been recorded onto spans. Copying it into attributes requires explicit code or a mapping mechanism. [OpenTelemetry: Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/)

In this example, you might choose `channel=web` as baggage and attach `inventory.result=out_of_stock` only to the reservation span. The shipping service does not need to carry the internal outcome of every inventory lookup.

This lesson uses the term **tag** in the tracing context. When referring to metric labels, the lesson explicitly writes **metric tag** to avoid confusing the two cost models.

## 2. Four Places Data Can Appear

| Storage Location | Question It Serves | Design Example in This Lesson |
| --- | --- | --- |
| Trace context | Which distributed execution do these spans belong to? | Trace ID and parent-child relationships |
| Baggage | What extra context does the downstream service need to know? | `channel=web` |
| Span tag | What information should describe this span? | `inventory.result=out_of_stock` |
| Log MDC | Which extra field do log lines need for correlation? | `channel=web` if configured |

With W3C Trace Context, `traceparent` carries trace linking metadata; `tracestate` is for tracing-system-specific state. Do not stuff business data into these two headers yourself. [W3C Trace Context](https://www.w3.org/TR/trace-context/)

An illustrative header for **W3C Baggage** might look like:

```http
baggage: channel=web,region=apac
```

This is an example of wire format, not a guarantee that every bridge and Spring configuration emits that exact single header. W3C Baggage has its own syntax, value encoding, and handling rules. Do not use arbitrary string concatenation to replace a context propagator. [W3C Baggage](https://www.w3.org/TR/baggage/)

MDC is only in-process context for logging. Having data in MDC does not prove outbound requests carry baggage; having baggage at a receiving service also does not prove logs will print that field.

## 3. Placing the Two Data Flows Side by Side

```text
Request flow:
checkout -- trace context + baggage --> inventory --> shipping

Observation flow:
checkout/inventory/shipping spans
    --> span exporter --> trace storage system
```

In the illustrative design:

1. `checkout` determines the channel from a verified source.
2. Policy decides `channel` is allowed to propagate to `inventory`.
3. HTTP instrumentation injects context into the request.
4. `inventory` extracts context and reads baggage.
5. If searching by channel is needed, `inventory` proactively attaches `channel` to the appropriate span.
6. When calling an external provider, the destination policy can strip all baggage.

Step 5 is not implicitly guaranteed by step 4. Similarly, attaching a tag onto a `checkout` span does not create a business-data propagation contract for `inventory`.

Do not use the tracing UI as the sole evidence for headers: data displayed there has passed through sampling, exporter, storage, and display rules.

## 4. Spring Boot 3.3 Configuration: Separating Propagation, Logs, and Tags

Spring Boot Actuator provides auto-configuration for Micrometer Tracing. HTTP clients should be built from `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder` supplied by Boot to preserve automatic context propagation. With B3, remote baggage fields must be declared; W3C has its own baggage mechanism. [Spring Boot 3.3: Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)

The example below **intentionally chooses Brave and B3_MULTI** so individual baggage headers can be observed clearly. This is configuration integrated into an existing Boot 3.3 application, not a standalone runnable project.

### 4.1. Dependencies

The following Groovy snippet assumes the project already applies the Spring Boot plugin and manages versions via the Boot 3.3 BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
```

Pick one appropriate bridge for the test. The span receiver configuration must match the chosen exporter; this example uses Zipkin.

### 4.2. Configuration Used on Both Test Services

```yaml
management:
  tracing:
    propagation:
      consume: [B3_MULTI]
      produce: [B3_MULTI]
    sampling:
      probability: 1.0
    baggage:
      remote-fields: [channel, region]
      correlation:
        fields: [channel]
      tag-fields: []
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
```

`probability: 1.0` serves observation in a learning environment. It is not a mandatory sampling policy for production operations.

Three property groups to distinguish:

| Property | Role |
| --- | --- |
| `management.tracing.baggage.remote-fields` | Declares fields propagated over the network per matching configuration |
| `management.tracing.baggage.correlation.fields` | Selects fields placed into logging context such as MDC |
| `management.tracing.baggage.tag-fields` | Selects fields automatically mapped into tags by the baggage mechanism |

The Boot 3.3 catalog also has `local-fields`, yet local fields are not supported with OpenTelemetry. Do not copy configuration between the two bridges assuming completely identical behavior. [Spring Boot 3.3: Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

The example keeps `tag-fields: []` so tagging is shown explicitly in code. If you want to test automatic mapping, you can change it to `tag-fields: [channel]` and verify on actual spans for the bridge/version in use; that is a separate choice from declaring network propagation.

Boot 3.3's Brave configuration registers `remote-fields` using `BaggagePropagationConfig.SingleBaggageField.remote(...)`; correlation fields are configured separately for MDC. [Boot 3.3.13 Brave propagation source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/BravePropagationConfigurations.java)

**In this B3 example**, look for headers `channel: web` and `region: apac`. Do not look only for a header named `baggage` and conclude propagation failed.

### 4.3. Service Call Code Within Baggage Scope

Save the following class at `example/baggage/InventoryCaller.java` inside the Boot application. The class must be discovered by component scanning. The service on port 8081 must expose a `GET /stock` endpoint; this class does not create that endpoint itself.

Input preconditions for the example: the request has already passed edge policy, current context contains no out-of-policy baggage, and the fixed target below is an internal service authorized to receive these two fields.

```java
package example.baggage;

import java.util.Set;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryCaller {
    private static final Set<String> CHANNELS =
            Set.of("web", "mobile", "batch");
    private static final Set<String> REGIONS =
            Set.of("apac", "emea", "amer");

    private final Tracer tracer;
    private final RestClient client;

    public InventoryCaller(Tracer tracer, RestClient.Builder builder) {
        this.tracer = tracer;
        this.client = builder
                .baseUrl("http://localhost:8081")
                .build();
    }

    public String stock(String channel, String region) {
        if (channel == null || region == null
                || !CHANNELS.contains(channel) || !REGIONS.contains(region)) {
            throw new IllegalArgumentException("Unsupported context");
        }

        Span span = tracer.nextSpan().name("inventory.lookup").start();
        try (Tracer.SpanInScope spanScope = tracer.withSpan(span);
             BaggageInScope channelScope =
                     tracer.createBaggageInScope("channel", channel);
             BaggageInScope regionScope =
                     tracer.createBaggageInScope("region", region)) {
            span.tag("channel", channel);
            return client.get()
                    .uri("/stock")
                    .retrieve()
                    .body(String.class);
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }
}
```

When calling `stock("web", "apac")`:

- The two `BaggageInScope` instances open scopes for the data to propagate.
- `span.tag("channel", channel)` explicitly writes a tag onto the `inventory.lookup` span.
- The HTTP client span created by instrumentation is a different span; do not assume it has the exact same tag set.
- `try-with-resources` closes the scopes even if the HTTP call fails; `finally` ends the span created by this class.

Scope and baggage APIs are described in [Micrometer Tracing: using the API directly](https://docs.micrometer.io/tracing/reference/api.html).

This code runs synchronously within the call scope. If dispatching work to an executor or reactive flow, an appropriate context propagation mechanism is required; still holding a `Tracer` reference does not automatically carry context along with the task.

On the receiving side, the following snippet illustrates the body of a method with `Tracer tracer` already injected. It is **not a standalone Java program**:

```java
var baggage = tracer.getBaggage("channel");
String channel = baggage == null ? null : baggage.get();

Span current = tracer.currentSpan();
if (current != null
        && channel != null
        && Set.of("web", "mobile", "batch").contains(channel)) {
    current.tag("channel", channel);
}
```

The receiver snippet requires importing `java.util.Set` and `io.micrometer.tracing.Span`. Checking the allowed value set only confirms the value conforms to policy; it does not authenticate who sent that value.

Lacking a startup program or receiver endpoint here is the boundary of an integration snippet. It has no fixed stdout: trace ID, span ID, duration, and HTTP response depend on the run.

## 5. Data Policy: Decide Before Turning On Automatic Propagation

Design a small catalog for each field:

| Proposed Field | Decision in Illustrative Scenario | Rationale |
| --- | --- | --- |
| `channel` | Allow values `web/mobile/batch` | Needed for analysis by request origin |
| `region` | Only for internal services that need it | Avoid spreading unnecessary data |
| `inventory.result` | Tag on the reservation span | Describes a local operation |
| `customer.email` | Exclude from baggage | Personal data not needed for this call chain |
| `Authorization`, passwords, API keys | Exclude from baggage and tags | Not diagnostic data to replicate |
| Full order JSON | Pass via API contract if genuinely needed | Baggage is unsuitable as a substitute for request payloads |

This is the example's policy, not a standard Spring key list.

Recommended process for a trust boundary:

1. Identify sender source and receiver target; targets must come from trusted configuration.
2. Select an allowlist of keys.
3. Validate value sets, lengths, entry counts, and byte budgets.
4. Strip invalid fields before placing data into context, tags, or logs.
5. Create baggage only from accepted data.
6. When crossing into an untrusted domain, apply a strip/minimize baggage policy at request dispatch.

Baggage has no built-in integrity check. A value such as `role=admin` or `tenant=another-company` self-reported by a caller cannot substitute for authentication and authorization proof. [OpenTelemetry: baggage security considerations](https://opentelemetry.io/docs/concepts/signals/baggage/#baggage-security-considerations)

Even `channel=web` is merely descriptive metadata if it arrives externally. If channel affects rate limits or billing, determine it from a trusted source or a separately authenticated contract.

### 5.1. Filters Must Be Placed in the Right Spot

`remote-fields` helps configure propagation; do not treat it as a complete data firewall. With W3C, standard baggage may be handled by the propagator in addition to custom headers you are watching.

Do not adopt the following flow and assume you are safe:

```text
receive unfiltered request
→ library already extracted all baggage
→ only read and check the channel key
→ call external service with auto-propagating client
```

Validating one key does not remove the remaining keys from the active context.

Therefore, inbound control must happen before untrusted data is accepted into context. Outbound control must apply at outbound context creation or the final header-injection layer. With gateways, check which side of automatic header injection the policy sits on.

If choosing to strip baggage at the outbound edge, account for both the W3C `baggage` header and configured custom headers. Stripping them before a downstream auto-injection step can cause them to reappear.

Use HTTPS/TLS on the wire where appropriate, yet still minimize data before sending: an authorized receiver can still read baggage. Transport encryption does not turn baggage into a secret store.

### 5.2. Do Not Wait Until the Collector to Sanitize

Redacting data in the final UI does not recall data already transmitted across services, proxies, or logs. Minimize data at the source; scrubbing/redaction in the telemetry pipeline is an additional layer. Hashing an identifier also does not guarantee data is anonymized. [OpenTelemetry: handling sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/)

To know whether a field truly needs propagating, require the owner to answer: who uses it, at which step, whether a coarser value suffices, and when propagation stops.

## 6. Java 17+: Verifying a Small Policy, Standalone Runnable

The program below accepts only an **already parsed Map** and selects valid data. It does not parse W3C headers, does not encode headers, does not modify Micrometer context, and does not itself block an HTTP client from propagating other data.

Illustrative policy:

- Only trusted internal destinations identified by configuration may receive data.
- Only two keys, `channel` and `region`, are allowed.
- Values must belong to a defined finite set.
- Each value is at most 16 ASCII characters; total key-value pair representation is at most 64 bytes.
- Invalid keys or values are dropped; do not include rejected values in log messages.

Save the code below verbatim into `BaggagePolicyDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public class BaggagePolicyDemo {
    private static final Map<String, Set<String>> ALLOWED = Map.of(
            "channel", Set.of("web", "mobile", "batch"),
            "region", Set.of("apac", "emea", "amer"));
    private static final int MAX_VALUE_LENGTH = 16;
    private static final int MAX_PAIR_BYTES = 64;

    static Map<String, String> select(
            Map<String, String> parsed, boolean trustedDestination) {
        if (!trustedDestination) {
            return Map.of();
        }

        TreeMap<String, String> selected = new TreeMap<>();
        int usedBytes = 0;

        for (String key : new TreeMap<>(ALLOWED).keySet()) {
            String value = parsed.get(key);
            if (value == null
                    || value.length() > MAX_VALUE_LENGTH
                    || !value.chars().allMatch(c -> c >= 0x21 && c <= 0x7e)
                    || !ALLOWED.get(key).contains(value)) {
                continue;
            }

            int pairBytes = (key + "=" + value)
                    .getBytes(StandardCharsets.US_ASCII).length;
            int separatorBytes = selected.isEmpty() ? 0 : 1;
            if (usedBytes + separatorBytes + pairBytes > MAX_PAIR_BYTES) {
                continue;
            }

            selected.put(key, value);
            usedBytes += separatorBytes + pairBytes;
        }

        return Collections.unmodifiableMap(selected);
    }

    public static void main(String[] args) {
        Map<String, String> incoming = Map.of(
                "channel", "web",
                "region", "apac",
                "customer.email", "alice@example.test",
                "role", "admin");

        System.out.println("internal=" + select(incoming, true));
        System.out.println("external=" + select(incoming, false));
        System.out.println("invalid=" + select(Map.of(
                "channel", "web\r\nInjected: yes",
                "region", "unknown"), true));
        System.out.println("missing=" + select(Map.of(), true));
    }
}
```

Compile and run from the directory containing the file, on JDK 17 or later:

```shell
javac BaggagePolicyDemo.java
java BaggagePolicyDemo
```

Exact stdout output:

```text
internal={channel=web, region=apac}
external={}
invalid={}
missing={}
```

`TreeMap` makes print ordering deterministic. Values in the allowlist are short and finite, so both current valid entries fit under the budget. The byte-checking branch documents the explicit limit if the dataset expands later; no current valid case exercises exceeding 64 bytes.

`trustedDestination` is the result of a trust decision from application configuration, never taken directly from user parameters. When integrating, also verify scheme, host, port, and HTTP client redirect policy so the actual target matches that decision.

The numbers 16 and 64 are **example-chosen limits**, not default limits of Spring, W3C, proxies, or servers. The program also does not cap input Map size: the request-receiving layer must reject oversized headers before parsing.

In real deployments, measure header size after encoding and include other headers as well. W3C allows systems to limit/truncate baggage; do not assume every intermediary preserves unbounded entries. [W3C Baggage: limits](https://www.w3.org/TR/baggage/#limits)

## 7. Baggage, Value Cardinality, and Observability Cost

The number of distinct values is called **cardinality**. `channel` with three values is a small set; continuously generated order IDs are a large set. Micrometer distinguishes low-cardinality and high-cardinality keys in Observation. [Micrometer: Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)

In this lesson's design:

- Allowing `channel` as a metric tag can be appropriate because its value count is bounded.
- Never put individual order IDs in as metric tags.
- If an order ID is genuinely needed to diagnose a span, review privacy, length, retention, and storage cost before attaching it.
- Do not turn all baggage into tags on every span or every metric.

Sizing example to visualize: if each internal call carries 100 extra bytes of baggage and one request makes 20 calls, total baggage payload across outbound calls is roughly 2,000 bytes. That counts only added data, excluding other headers, protocol encoding, retries, or follow-on calls.

Span sampling and context propagation are two separate decisions. Do not use "did not see spans in storage" to assume data stopped traveling over the wire; measure directly at the propagation boundary.

## 8. Verifying Behavior with Separate Observations

With two test services sharing the B3 configuration above, separate the pieces of evidence:

| Test Case | What to Observe | Passing Evidence |
| --- | --- | --- |
| Attach only tag `channel`, create no baggage, and input has no baggage | Request sent to receiving service | No `channel` data appears from tagging |
| Create baggage without calling `span.tag`, keeping `tag-fields: []` | Headers and self-created span | Data is propagated; do not assume `channel` tag exists on span |
| Create baggage and call `span.tag` as in the example | Headers and `inventory.lookup` span | Both separate outcomes are observed |
| Add correlation field and log pattern with `%X{channel}` | Logs within the baggage scope | MDC value appears in the right scope |
| Call external provider through the policy layer | Final request actually sent | Forbidden baggage headers are absent |
| Request A has baggage, request B does not | Two independent executions | No value leaks from A to B |
| Do not export spans for one execution | Request on the wire | Independently verify whether baggage propagated |

Do not log complete real headers to shared logs as evidence. In test environments, use synthetic data and access-restricted request inspection tools; test success, error, retry, and redirect paths if the client supports them.

With the B3 example, `channel` can appear as its own header. With another W3C configuration, inspect both `baggage` and declared custom headers. If data is missing, check the bridge, configuration on both sides, active scope, whether the client was built from Boot's builder, and whether a gateway strips headers.

Running the Java policy demo only proves the Map selection results in section 6. It does not replace the HTTP, MDC, span, or trust-boundary tests in this table.

## 9. Common Mistakes

| Practice | Consequence | Adjustment |
| --- | --- | --- |
| Attach a tag and expect downstream service to read baggage | Confuses span-stored metadata with propagated data | Create and verify baggage separately |
| Have baggage and assume it appears on every span | Skipped mapping step | Choose target spans and tags to write |
| Think correlation field enables network propagation | Testing the wrong data flow | Check MDC and headers independently |
| Use `remote-fields` as the sole security policy | May miss data via other propagation paths | Enforce policy before extraction and at outbound dispatch |
| Use baggage to make authorization decisions | Trusts caller-asserted metadata | Use authenticated identity and permissions |
| Forget to close scope | Data outlives intended scope | Use `try-with-resources` and test subsequent requests |
| Dispatch task to another thread without context propagation | Lost data or attached to wrong scope | Use the corresponding context propagation mechanism |
| Scrub data only at trace storage | Data may already have traversed external services | Minimize data at source and outbound edges |
| Put large JSON into baggage | Bloated headers, higher cost, and rejection risk | Use API contracts for business payloads |

## 10. Practice and Self-Check

1. For the chain `checkout → inventory → payment-provider`, draft a policy for `channel`, `region`, email, and access token. Specify which fields are local tags only, which travel internally, and which are never collected.
2. Change `channel` in the policy demo to `desktop`. The entry for that key must be dropped since it is not in the allowlist; do not add the value just to make the test "green."
3. Perform one run with tag only, one with baggage only, and one with both. Collect header and span evidence separately.
4. Send sequential requests with and without baggage to detect scope leakage bugs.
5. Inspect external destinations after the entire interceptor chain and context propagation step; confirm stripped data is not reinjected.

Self-assessment questions:

- To let the downstream service know the request channel, is attaching a tag enough? **No; an appropriate extra context propagation mechanism is required.**
- To search spans by channel, is creating baggage enough? **Not guaranteed; mapping onto tags on appropriate spans is needed.**
- Does a valid baggage value prove the sender is authorized? **No.**
- Does seeing no stored trace prove baggage did not propagate? **No; inspect the wire propagation path separately.**
- Should a field allowed internally be sent to third parties by default? **No; that is a per-destination decision.**
