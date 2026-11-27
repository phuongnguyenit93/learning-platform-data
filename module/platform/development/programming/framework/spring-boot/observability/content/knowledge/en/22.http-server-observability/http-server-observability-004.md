# URI Template

In the **HTTP server observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a URI template is the path pattern that the framework uses to describe the endpoint that handled a request, before path variables are substituted with actual values. For example, the endpoint `/orders/{orderId}` can receive requests `/orders/1001` and `/orders/1002`. Both requests belong to the same route template: `/orders/{orderId}`.

In Spring Boot, HTTP server Observation typically creates a meter named `http.server.requests`. The `uri` tag is recorded as a URI template when the framework can determine the route pattern. This is a critical design choice for observability: metrics can group requests by endpoint without creating a new time series for every ID. If raw paths replace templates, cardinality can grow with the number of users, orders, or accessed resources, inflating metrics backend memory usage and slowing down queries.

This lesson focuses on URI templates in HTTP server observability with Spring Boot, Micrometer Observation, and distributed tracing. You will understand where the route pattern comes from, how the `uri` tag differs from the request URI, how to inspect MVC/WebFlux, how to handle unmatched routes, and how to customize the observation convention while keeping cardinality stable.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain URI templates and distinguish them from raw request URIs, URLs, and query strings.
2. Understand the role of the `uri` tag in `http.server.requests`.
3. Explain why URI templates help control metric cardinality.
4. Trace how Spring MVC and Spring WebFlux supply route patterns to Observation.
5. Distinguish matched routes from requests not resolved to a handler.
6. Inspect URI templates in the Actuator metrics endpoint and metrics backend.
7. Customize `ServerRequestObservationConvention` when you need to add or modify tags.
8. Avoid putting path variables, query parameters, and identifiers into low-cardinality metrics.
9. Combine URI templates with logs, spans, and trace correlation to investigate a specific request.
10. Write tests for route templates, unmatched routes, and cardinality.

## 2. What Is a URI Template?

A URI template represents the structure of a path using variables instead of concrete values.

Examples:

| Actual Request | URI Template |
| --- | --- |
| /orders/1001 | /orders/{orderId} |
| /orders/1002 | /orders/{orderId} |
| /customers/c-918/profile | /customers/{customerId}/profile |
| /products/sku-77/reviews/5 | /products/{productId}/reviews/{reviewId} |

Two or more requests with different paths can belong to the same route template. This allows metrics to answer questions like "which endpoint is slow?" instead of creating a separate group for every order ID.

### Distinguishing Related Concepts

| Concept | Example | Purpose |
| --- | --- | --- |
| **Raw request URI/path** | /orders/1001 | The actual path sent by the request to the server. |
| **URI template / route pattern** | /orders/{orderId} | The route pattern resolved by the framework/router. |
| **Full URL** | https://api.example.com/orders/1001?expand=items | Scheme, host, path, and query string. |
| **Query string** | ?expand=items | Query parameters after the `?`. |
| **Path variable** | orderId=1001 | Concrete value bound to the route variable. |
| **HTTP route** | Handler processing /orders/{orderId} | Logical endpoint matched by the request. |

A URI template is not a full URL. It typically describes only the route path and does not include the host, query string, or path variable values.

### Why Must Templates Appear in Metrics?

Suppose a system has 500,000 orders and each order is accessed at least once. If the `uri` tag keeps the raw path, the backend can see hundreds of thousands of distinct values:

~~~text
uri=/orders/1001
uri=/orders/1002
uri=/orders/1003
...
~~~

When using a route template, requests are grouped into a single tag value:

~~~text
uri=/orders/{orderId}
~~~

With templates, the number of routes stays close to the number of declared endpoints and is far easier to control. It does not guarantee low cardinality on its own: an application could still generate dynamic routes or have thousands of route templates. However, templates eliminate a major source of cardinality coming from path variable values.

## 3. URI Template in `http.server.requests`

Spring Boot auto-configures HTTP server instrumentation for supported stacks such as Spring MVC and Spring WebFlux. The framework-level Observation is named `http.server.requests`. When the Observation is wired to Micrometer metrics, it creates a timer for request processing duration; when tracing is enabled, the same Observation can create a span.

Common default tags include:

| Tag | Meaning |
| --- | --- |
| method | HTTP method such as GET, POST, PUT, DELETE. |
| uri | URI template prior to variable substitution, if resolved by the framework. |
| status | HTTP response status such as 200, 404, or 500. |
| outcome | Result category based on response status. |
| exception | Exception class name if an exception was recorded. |

Exact tag names or stack-specific details may vary by Spring Boot/Spring Framework version and configured convention. Verify the actual meter in your application. Spring Boot documentation describes the URI tag as the template before substitution, such as `/api/person/{id}`. [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

### Observation Produces Both Metrics and Traces

~~~mermaid
flowchart TD
    Request["HTTP request: GET /orders/1001"]
    Router["Spring MVC / WebFlux route matching"]
    Context["ServerRequestObservationContext"]
    Convention["ServerRequestObservationConvention"]
    Observation["http.server.requests Observation"]
    Metrics["Micrometer Timer + tags"]
    Trace["Tracing handler creates server span"]
    Request --> Router --> Context --> Convention --> Observation
    Observation --> Metrics
    Observation --> Trace
~~~

The URI template is used in the Observation convention to produce a low-cardinality key-value. For metrics, templates are how endpoints are grouped. For tracing, spans can carry additional detailed attributes according to semantic conventions and instrumentation configuration. Do not assume all meter tags are copied verbatim into span attributes.

## 4. Where Does Spring MVC Get the URI Template?

In a Servlet/Spring MVC application, `DispatcherServlet` coordinates with `HandlerMapping` to locate the handler matching the request. Once a controller mapping is matched, the framework can determine the route pattern.

Controller example:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getOrder(@PathVariable String orderId) {
        return orderService.find(orderId);
    }
}
~~~

The following requests:

~~~text
GET /orders/1001
GET /orders/1002
GET /orders/9f2a
~~~

all match the same `/orders/{orderId}` mapping. The server request Observation can use this route pattern as the low-cardinality `uri` tag.

### Filter and Observation Lifecycle

For Servlet applications, Spring Framework uses `ServerHttpObservationFilter` to create HTTP server observations. The filter must sit properly in the servlet filter chain and work alongside framework mappings. Spring Boot auto-configuration typically sets up instrumentation for supported stacks; if you configure filters manually or replace web infrastructure, confirm the observation filter is neither skipped nor registered twice.

Regarding exceptions, an observation typically records an error only when the exception is unhandled by the framework and bubbles up to the filter. Exceptions handled by `@ExceptionHandler` or `ProblemDetail` mechanisms may not automatically become an error tag. If handled exceptions need to be recorded, the application must attach the error to the observation context according to the Spring Framework guidance for its version. This matters when correlating URI templates with status/outcome.

## 5. Where Does Spring WebFlux Get the URI Template?

In WebFlux, the framework can create HTTP server observations for both annotated controllers and functional endpoints.

Annotated controller example:

~~~java
@RestController
@RequestMapping("/catalog")
class CatalogController {

    @GetMapping("/{productId}")
    Mono<ProductResponse> find(@PathVariable String productId) {
        return productService.find(productId);
    }
}
~~~

Functional route example:

~~~java
@Bean
RouterFunction<ServerResponse> catalogRoutes(CatalogHandler handler) {
    return RouterFunctions.route()
            .GET("/catalog/{productId}", handler::find)
            .build();
}
~~~

Both routing styles can supply the pattern for Observation to describe the endpoint. When using functional routing, verify your version and how handler mapping provides the matched pattern to Observation.

### Preserving Context in Reactive Pipelines

A reactive pipeline can execute across multiple threads. The URI template is determined within the request handling context; if custom code creates an Observation or logs outside proper context propagation, correlation can be lost even though the route matched normally.

Do not extract the raw path from `ServerRequest` and add it as a low-cardinality tag in place of the route template. If you need to log a specific protected path, consider writing it to a log event under a separate policy, with appropriate retention/access controls, and never use it as a metric label.

## 6. URI Template and Cardinality

Cardinality is the number of distinct values of a dimension/tag. Each tag value can create additional time series in the metrics backend. If the `uri` tag contains raw paths, every distinct identifier can generate a new series.

Example of a route with 200,000 order IDs:

| Tagging Approach | Potential Number of `uri` Values |
| --- | ---: |
| Raw path: /orders/1001, /orders/1002, ... | Up to 200,000 |
| Template: /orders/{orderId} | 1 |
| Fixed route name only | 1 for that endpoint |

Total series also depend on method, status, exception, outcome, instance, and other tags. If 1 route has 5 method/status combinations and 20 service instances, the time-series count scales by the product of those dimensions.

### A Simple Cardinality Calculation

Suppose:
- 40 URI templates.
- 5 HTTP methods.
- 6 response status values.
- 4 outcome values.
- 3 exception categories.

The simple multiplicative upper bound is:

~~~text
40 * 5 * 6 * 4 * 3 = 14,400 tag combinations
~~~

This is only a theoretical upper bound before accounting for impossible combinations, histogram buckets, and other dimensions. Adding a raw path or user ID to a tag multiplies the value count sharply and can create millions of series.

### Fewer Routes Are Not Always Safe

An application with dynamically generated routes per tenant or plugin still risks high cardinality even if each template has no ID. Enforce stable route rules and avoid building mappings from request data. When designing metric tags, evaluate all dimensions together, not just the `uri` tag.

## 7. Unmatched Routes and Unknown URIs

Not every request reaches a clear controller mapping. Several scenarios can occur:

- Request to a non-existent path.
- Unsupported HTTP method for that path.
- Request rejected before `DispatcherServlet` or the router handles it.
- Static resource handler serves the request.
- Proxy/gateway rewrites the path differently from what the app expects.
- Custom servlet/filter terminates the request before route mapping occurs.

In these scenarios, the framework may not have a concrete URI template. The `uri` value may fall back to a value used by the convention/framework, or the request may not appear in the meter exactly as expected depending on stack/version.

Never replace the fallback with the raw request path. If every unknown path is recorded verbatim, an endpoint scan or bot traffic can cause unbounded cardinality growth.

### Grouping Unmatched Routes

If you need to track unmatched requests, prefer a stable grouping value, such as a `not-found` route category or a normalized fallback path. Grouping should be done via an appropriate observation convention/filter and tested on the actual stack. Never alter the route template of matched requests just to merge everything under one label.

Useful complementary metrics:
- Count of 404/405 by outcome/status.
- Request rate hitting the fallback handler.
- Logs with a controlled request ID.
- Security events for scans or suspicious paths.

## 8. Inspecting URI Templates via Actuator

In an application with Actuator and an appropriately exposed metrics endpoint, you can query the `http.server.requests` meter.

Request example:

~~~http
GET /actuator/metrics/http.server.requests
~~~

The metrics endpoint can return aggregate measurements along with available tag keys/values. Configure Actuator endpoint exposure securely; do not expose the metrics endpoint to the public internet just for debugging.

Illustrative output example:

~~~json
{
  "name": "http.server.requests",
  "measurements": [
    { "statistic": "COUNT", "value": 2.0 },
    { "statistic": "TOTAL_TIME", "value": 0.084 }
  ],
  "availableTags": [
    {
      "tag": "uri",
      "values": ["/orders/{orderId}"]
    },
    {
      "tag": "method",
      "values": ["GET"]
    },
    {
      "tag": "status",
      "values": ["200"]
    }
  ]
}
~~~

Actual payloads may have different tags and values depending on the app/version. Use the endpoint to confirm the framework is producing templates rather than raw paths.

### Filtering by Tag Value

Actuator allows filtering a meter by an existing tag. Illustrative example:

~~~http
GET /actuator/metrics/http.server.requests?tag=uri:/orders/{orderId}
~~~

When constructing URLs in a shell or browser, special characters must be URL-encoded properly. The metrics endpoint is an inspection tool, not a metrics backend for long-term time-series queries.

## 9. Customizing `ServerRequestObservationConvention`

You can add or replace tags using `ServerRequestObservationConvention`. Spring Boot documentation recommends providing a convention bean to add tags, typically by extending `DefaultServerRequestObservationConvention`; if you want to replace the entire tag set, you can implement `ServerRequestObservationConvention` directly as appropriate.

Illustrative example adding a tag with a finite value set:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.observation.ServerRequestObservationContext;

@Configuration(proxyBeanMethods = false)
class HttpObservationConfiguration {

    @Bean
    DefaultServerRequestObservationConvention serverRequestObservationConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {
                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of("application", "order-api"));
            }
        };
    }
}
~~~

This example illustrates extending the default convention in a Servlet stack. Imports/packages/APIs may differ between Servlet and Reactive applications; use the convention type matching the running stack. Do not register a custom convention without calling the default data if you still want to retain the default tags.

### When You Need to Modify the `uri` Tag

In some cases, you may need to normalize aliases or group a few routes. Spring Framework provides `ServerRequestObservationConvention` and its context to customize low-cardinality values. You can extend the default convention and override the URI `KeyValue` creation while keeping default behavior for the rest.

~~~java
@Override
protected KeyValue uri(ServerRequestObservationContext context) {
    KeyValue uri = super.uri(context);
    // Only normalize clearly recognized routes.
    return uri;
}
~~~

This is a skeleton illustrating the extension point, not complete logic. Do not replace `uri` with a raw path or string containing identifiers. If a route does not match, use a safe and stable fallback. Test both matched and unmatched requests before releasing.

### Add Tags or Replace Tags?

- Extend `DefaultServerRequestObservationConvention` when you only need to add a few low-cardinality tags while preserving standard tags.
- Implement `ServerRequestObservationConvention` when you need full control over low/high-cardinality values.
- Keep the semantics of standard tags like `method`, `status`, `outcome`, and `uri` intact so dashboards/alerts remain usable.
- Never place tenant ID, user ID, request ID, or full URL into low-cardinality values.
- If a high-cardinality attribute is needed for traces, add it only with a clear investigative purpose and after privacy review.

## 10. Do Not Confuse URI Templates with URLs in Traces

Metrics and traces can store different attributes. URI templates make suitable stable metric dimensions. Trace spans can carry `http.route` per semantic conventions along with other HTTP attributes such as request method/status. Raw URLs or query strings should not be stored if they contain sensitive data or expose identifiers.

Examples:

| Where Recorded | Value to Use | Avoid |
| --- | --- | --- |
| Metrics tag `uri` | /orders/{orderId} | /orders/1001 |
| Trace attribute `http.route` | /orders/{orderId} | Raw path containing customer ID |
| Log field `route` | /orders/{orderId} | Entire query string containing token |
| Log correlation | Generated and managed request ID | Session cookie or bearer token |

In traces, high-cardinality attributes can sometimes help investigate a specific request, but that does not mean all path data is safe. Follow the module's data classification and masking policies.

## 11. Custom Routes, Gateway Rewrites, and Reverse Proxies

Applications are often deployed behind a reverse proxy, ingress, or API gateway. These components may:
- Change path prefixes before forwarding requests to the application.
- Forward the original path via headers.
- Rewrite host/scheme.
- Route to the service using a different path than the public URL.

The URI template seen by Spring MVC/WebFlux is usually based on the request path after it arrives at the application and is processed by handler mapping. It may differ from the public route at the gateway. Do not assume the route template in the meter represents the external URL called by clients.

If public route analysis is needed:
1. Check whether the gateway has its own route template.
2. Forward only normalized, trusted route metadata.
3. Never trust any `original-url` header from public callers unless the proxy strips/overwrites it.
4. Never copy a raw forwarded URI into a metric tag.
5. Maintain a mapping between public routes and internal routes in dashboards/documentation.

## 12. Impact of URI Templates on Alerts and Dashboards

Using stable route templates enables comparing request rates, error rates, and latencies over time. For example, the `http.server.requests` metric can be queried by `uri`, `method`, and `status`.

A dashboard might display:
- Request rate by route template.
- P95/P99 latency by route template and method.
- Error rate by outcome/status.
- Request count hitting fallback/not-found routes.
- Latency comparison across versions/service instances.

PromQL example (metric names may be converted by the backend from Micrometer names):

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    application="order-api"
  }[5m])
)
~~~

Illustrative P95 when histograms are exported and the backend has appropriate buckets:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri, method) (
    rate(http_server_requests_seconds_bucket{
      application="order-api"
    }[5m])
  )
)
~~~

Actual metric and label names depend on the registry/exporter. Verify in your metrics backend before copying queries into dashboards. Not every backend/registry uses the exact Prometheus names shown in the example.

Template-based alerts help identify problematic endpoints. Avoid alerting per raw path value; that creates excess series and causes noise when paths contain identifiers.

## 13. Testing URI Templates and Cardinality

A test should verify that requests with different path variables produce a single URI template.

Example using Spring Boot test with `MockMvc` (illustrative):

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpServerUriTemplateTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void requestsWithDifferentIdsShareUriTemplate() throws Exception {
        mockMvc.perform(get("/orders/1001")).andExpect(status().isOk());
        mockMvc.perform(get("/orders/1002")).andExpect(status().isOk());

        Timer timer = meterRegistry.find("http.server.requests")
                .tag("uri", "/orders/{orderId}")
                .tag("method", "GET")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(2);
    }
}
~~~

This test assumes the controller, dependencies, and test endpoints are configured accordingly. Tag values may vary by framework version or route handling. If using WebFlux, use `WebTestClient` and inspect the corresponding meter.

### Cases to Test

| Case | What to Verify |
| --- | --- |
| Two different IDs on the same route | One template tag, not two raw paths. |
| Nested routes | Template contains the expected path variables. |
| Route with optional segments | Pattern matches the actual mapping. |
| Unmatched request | Fallback/404 behavior does not create a new raw path tag per request. |
| Unsupported method | Status/outcome are recorded properly and route grouping stays stable. |
| Handled exception | Error/status tags reflect the intended observation policy. |
| Async/reactive request | Observation completes properly and context is preserved. |
| Proxy prefix/rewrite | Route template reflects the path actually matched by the application router. |

### Checking Cardinality with Many Requests

Send many requests with random identifiers to the same route, then count the number of distinct `uri` tag values. The number of URI values must not grow with the number of identifiers if templates are supplied properly.

Do not look only at the total meter count. Inspect tag values and time series in the registry/backend. Also check other tags: tenant, exception message, query, user ID, or custom tags can still inflate cardinality even when `uri` is correct.

## 14. Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| `uri` tag contains `/orders/1001` | Convention receives raw path or instrumentation/router does not provide route pattern. | Check matched route, convention, and framework version. |
| Every request has `uri=UNKNOWN` | Route mapping not supplied to Observation, instrumentation/filter missing, or request ended too early. | Check filter/router integration and request lifecycle. |
| 404 requests create many `uri` values | Raw unmatched path is being recorded in the metric tag. | Normalize fallback; never record raw paths in low-cardinality tags. |
| MVC has templates but WebFlux does not | Configuration or convention belongs to the other stack. | Verify the right Servlet/Reactive instrumentation and packages. |
| Metrics lack `http.server.requests` | Actuator/Micrometer instrumentation inactive or meter filtered out. | Check dependencies, registry, and observation configuration. |
| Metrics exist but trace lacks route | Tracing handler/exporter uses a different pipeline than metrics or trace attributes follow a different convention. | Check tracing bridge, span payload, and semantic attributes. |
| Convention added but tag unchanged | Bean not used, wrong type for stack, or competing conventions in config. | Check bean auto-configuration and application context. |
| Dashboard has too many series | Raw paths or high-cardinality custom tags. | Audit all tag dimensions and registry filters. |
| Route tag differs from public URL | Gateway rewrite/prefix changes path before the app. | Compare gateway route with internal handler mapping. |
| 500 lacks expected exception tag | Exception handled before reaching the observation filter. | Set error on `ObservationContext` per framework guidance if needed. |

## 15. Runbook: Verifying URI Templates in a Production-Like Environment

1. **Identify web stack:** Spring MVC/Servlet, WebFlux/Reactive, or Jersey.
2. **Identify route mappings:** list declared route templates; do not derive the list from raw request logs.
3. **Check Observation:** confirm `http.server.requests` is created for matched requests.
4. **Read meter:** use the Actuator metrics endpoint in an internal environment to inspect the `uri` tag.
5. **Send test requests:** call the same route with multiple distinct path variable values.
6. **Count tag values:** confirm the URI template keeps the value count stable.
7. **Test unmatched route:** verify fallback and 404 do not create raw-path series.
8. **Check proxy:** compare internal routes against gateway routes/rewrites.
9. **Review custom conventions:** check all low-cardinality tags and high-cardinality attributes.
10. **Check metrics backend:** inspect series count, ingest, and query latency.
11. **Check trace correlation:** confirm server spans link to the right requests and route attributes do not leak sensitive data.
12. **Monitor post-rollout:** watch cardinality/series growth and roll back the convention if raw paths appear.

## 16. Self-Check Exercises

### Exercise 1 — Choosing the URI Tag

Two requests `GET /customers/21` and `GET /customers/22` match the same controller mapping `/customers/{customerId}`. Which `uri` value should appear in `http.server.requests`?

**Answer:** `/customers/{customerId}`. Both requests share the same route template.

### Exercise 2 — Cardinality

An API has one million order IDs. Why should you not use raw request paths as a low-cardinality tag?

**Answer:** Each order ID can create a separate tag value and time series, increasing cardinality, memory, index cost, and query complexity. Use a URI template to group requests under the `/orders/{orderId}` endpoint.

### Exercise 3 — Unmatched Requests

A bot sends thousands of random paths with no matching route. If the metric records the raw path into the `uri` tag, what can happen?

**Answer:** Cardinality can grow with every random path. Use a stable fallback/group for unmatched requests and keep investigative details in controlled logs or security telemetry.

### Exercise 4 — Public Route Differs from Internal Route

The gateway receives `/api/v1/orders/1001` and rewrites it to `/orders/1001` before calling Spring Boot. What will the internal URI template likely be?

**Answer:** `/orders/{orderId}`, because Spring handler mapping sees the internal path after the rewrite. Analyzing public routes requires normalized, trusted route metadata from the gateway.

### Exercise 5 — Metrics Present, Trace Route Missing

The meter has the correct `uri` template, but the trace backend does not show the route attribute. Does that necessarily mean the metrics URI template is broken?

**Answer:** No. Metrics and traces have separate handlers/exporters/semantic attributes. Inspect the tracing integration and span payload; do not infer span attributes from meter tags.

### Exercise 6 — Customizing Convention

A team wants to add tenant ID to the `uri` tag for per-customer analysis. Should they?

**Answer:** Raw tenant IDs should not be placed in a low-cardinality metric tag. That can create series per tenant. Use a finite tenant-tier group if useful and approved; per-tenant investigative data belongs in logs/traces under access and retention policies.

## 17. Implementation Checklist

- [ ] Understand that a URI template is the route pattern before substituting path variables.
- [ ] Distinguish route template, raw request URI, full URL, and query string.
- [ ] `http.server.requests` HTTP server Observation is active for the web stack in use.
- [ ] The `uri` tag uses the matched route's template when provided by the framework.
- [ ] Raw paths, path IDs, or query parameters are excluded from low-cardinality metric tags.
- [ ] Route definitions are stable; no dynamic mappings built from request values.
- [ ] Unmatched requests use a stable fallback/group without creating series from raw paths.
- [ ] `ServerRequestObservationConvention` is chosen appropriately for Servlet or Reactive stack.
- [ ] When extending the default convention, required standard tags are preserved.
- [ ] Custom tags have finite cardinality and contain no PII/secrets.
- [ ] Actuator metrics endpoint is exposed within a secure scope.
- [ ] Tested that multiple IDs on the same route produce one URI template tag.
- [ ] Tested 404/405, exception handling, and proxy rewrites.
- [ ] Metrics backend checked for series count/cardinality.
- [ ] Logs/traces are used to investigate individual requests with correlation and privacy controls.

**Key Takeaway:** A URI template describes an endpoint as a pattern, such as `/orders/{orderId}`; a raw path describes a specific request, such as `/orders/1001`. For Spring Boot HTTP server observability, using the route template for the `uri` tag lets metrics group requests by endpoint while keeping cardinality stable. Verify templates via Observation/Actuator, handle unmatched routes with a safe fallback, and use controlled logs/traces when individual request details are needed.
