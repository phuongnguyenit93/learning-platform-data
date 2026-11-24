# 404 Due to Missing Mapping Differs from Business-Logic 404

HTTP 404 Not Found can occur at two very different points in Spring MVC. In the first case, Spring cannot find a matching handler for the request: the URL, HTTP method, or mapping conditions do not match any registered endpoint. In the second case, the request is routed to a controller, the controller calls a service, and business logic determines that the requested resource does not exist.

Both cases can return status 404, yet their causes and fixes are completely different. If the URL is wrong, you need to fix the route or the client's request. If the URL is right but the order ID does not exist, a 404 response can be the completely expected business outcome. When diagnosing, determine which handler the request entered, whether the service was invoked, and which exception produced the response.

## 1. Two Paths Leading to HTTP 404

### 1.1. No Matching Handler

Spring MVC receives requests through DispatcherServlet. DispatcherServlet uses HandlerMapping to locate a handler capable of processing the request based on conditions such as path, HTTP method, query parameters, headers, Content-Type, and Accept.

If no mapping matches, the business controller is not invoked. For example, suppose an application declares:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse find(@PathVariable long id) {
        // ...
    }
}
~~~

The following requests do not have the same meaning:

~~~http
GET /api/orders/42
GET /api/order/42
GET /api/orders/42/details
~~~

The first request matches the declared path. The next two do not match this controller's mappings. If no other handler claims them, Spring returns 404. The body of `find` never runs and the service is never called.

In Spring MVC, the case where no handler is found can be represented by NoHandlerFoundException. With the default resource handler configuration, a URL that matches no controller is sometimes routed to ResourceHttpRequestHandler; if no corresponding static file exists, Spring may raise NoResourceFoundException. That is still a failure to find content to serve, except the selected handler was the resource handler.

### 1.2. Handler Runs, Yet the Business Resource Does Not Exist

For the request GET /api/orders/999, the mapping /api/orders/{id} still matches. Spring invokes the controller, and the controller calls the service to look up the order. If the service finds no data, the application may return 404 per the API contract:

~~~java
@GetMapping("/{id}")
OrderResponse find(@PathVariable long id) {
    return orderService.findById(id);
}
~~~

For example, the service throws OrderNotFoundException when the id does not exist. The controller was called; the error originates from business logic. This is a valid 404 for an existing endpoint and a resource absent from the system.

## 2. Comparing Symptoms in Each Case

| Symptom | 404 due to mapping/routing | 404 due to business logic |
|---|---|---|
| Does the URL match an endpoint? | No handler matches the request | A matching handler exists |
| Does the controller method run? | No | Yes |
| Is the business service called? | Typically no | Usually yes |
| Cause | Wrong path, unregistered route, or unmatched mapping condition | ID/resource does not exist per business data |
| Fix | Fix URL, HTTP method, mapping, or route configuration | Check ID, data, or business rules |
| Suggested API error code | ROUTE_NOT_FOUND | ORDER_NOT_FOUND or RESOURCE_NOT_FOUND |
| Test focus | Assert that no handler/controller is invoked | Assert that the right handler ran and the service reported not found |

Do not draw conclusions solely from the status code. The response body, exception, selected handler, and request logs distinguish the two causes.

## 3. Conditions That Affect Mapping Selection

Spring MVC mappings are not just paths. A handler method can declare multiple conditions:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    OrderResponse find(@PathVariable long id) {
        // ...
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        // ...
    }
}
~~~

Spring evaluates the following factors:

- Path: whether the path matches the route.
- Method: GET, POST, PUT, PATCH, DELETE, and so on.
- Params: whether query parameters are present or match mapping conditions.
- Headers: whether headers satisfy mapping conditions.
- Consumes: whether the request's Content-Type is supported by the endpoint.
- Produces: whether the endpoint can produce a representation matching Accept.

Therefore, a URL that looks right can still fail to route as expected if the method or another condition is wrong. Inspect all annotations at both class and method levels, not just the path.

### 3.1. Distinguishing 404 from 405, 415, and 406

Not every mapping mismatch results in 404:

| Status | Common meaning | Example |
|---|---|---|
| 404 Not Found | Handler or resource not found | GET /api/order/42 when the route is /api/orders/{id} |
| 405 Method Not Allowed | The path exists, but the HTTP method is unsupported | POST to an endpoint declaring only GET |
| 415 Unsupported Media Type | Content-Type is not supported by the endpoint | Sending XML to an endpoint accepting only JSON |
| 406 Not Acceptable | Server cannot produce a representation matching Accept | Client accepts only a media type the endpoint does not provide |
| 400 Bad Request | Request is invalid or parameter cannot bind per contract | Path variable cannot convert to a number on a matched route |

Unmet params or headers conditions may prevent a mapping from being selected, and the outcome depends on how HandlerMapping implementations process the request. Do not infer a status code solely because one annotation failed to match; observe the actual exception/status produced by your Spring version and application configuration.

## 4. Handling 404 When a Business Resource Does Not Exist

One clear pattern is using a dedicated domain exception:

~~~java
public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(long orderId) {
        super("Order " + orderId + " was not found");
    }
}
~~~

Service:

~~~java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    OrderResponse findById(long id) {
        Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
        return OrderResponse.from(order);
    }
}
~~~

Exception advice maps the domain exception to HTTP:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {

        ApiError error = new ApiError(
                "ORDER_NOT_FOUND",
                "The requested order does not exist.");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(error);
    }
}
~~~

In this example, the error code ORDER_NOT_FOUND is stable and the message does not depend directly on the exception message. This helps clients recognize business errors per the API contract. Do not return stack traces, SQL, or internal repository details.

If the controller itself represents absence with Optional or ResponseEntity, it can also return 404 without throwing an exception:

~~~java
@GetMapping("/{id}")
ResponseEntity<OrderResponse> find(@PathVariable long id) {
    return orderService.findOptional(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Choosing a domain exception or an Optional result depends on application conventions. What matters is that the controller returns 404 only when the requested resource genuinely does not exist under the contract.

## 5. Handling Errors Caused by Missing Mappings

If the API needs a consistent JSON response for non-existent routes, you can handle exceptions related to routing or static resources. In Spring Framework 6.1 and later, NoResourceFoundException is used when ResourceHttpRequestHandler cannot find a resource. NoHandlerFoundException represents the case where DispatcherServlet cannot find a matching handler.

Example of explicit mapping:

~~~java
@RestControllerAdvice
class RoutingExceptionHandler {

    @ExceptionHandler(NoHandlerFoundException.class)
    ResponseEntity<ApiError> noHandler(
            NoHandlerFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ROUTE_NOT_FOUND",
                        "No endpoint matches this request."));
    }

    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<ApiError> noResource(
            NoResourceFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "RESOURCE_PATH_NOT_FOUND",
                        "The requested resource was not found."));
    }
}
~~~

Exception types and dispatch behavior depend on the Spring MVC version. NoResourceFoundException was introduced in Spring Framework 6.1. In older versions, turning a missing handler into an exception may depend on DispatcherServlet settings such as throwExceptionIfNoHandlerFound. Check the framework version and actual configuration before writing advice; do not copy a handler for an exception that does not exist in your project's version.

In some applications, default error responses are already standardized by Spring Boot's ErrorController or a custom error configuration. In that case, you do not need extra advice just to alter every 404. Only add a custom handler if the API contract requires a unified error code or body.

Do not catch every Exception and return 404. Database errors, programming bugs, timeouts, or unavailable dependencies do not mean the route or resource does not exist. Mapping the wrong exception loses diagnostic information and prevents clients from deciding whether to retry.

## 6. Testing 404 Due to Unmatched Mappings

With Spring MVC, MockMvc can send a request to a URL not declared by the controller. The test should verify status 404 and ensure the business service is not called.

Slice test example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsNotFoundWhenNoControllerMappingMatches() throws Exception {
        mockMvc.perform(get("/api/order/42"))
                .andExpect(status().isNotFound());

        then(orderService).shouldHaveNoInteractions();
    }
}
~~~

The test calls /api/order/42 while the controller declares /api/orders/{id}. The controller method is never executed, so the service has no interactions. If the application has custom resource handlers or error advice, the body may differ; the test should assert the published error contract.

Another case is a route with the right path but wrong method:

~~~java
@Test
void distinguishesUnsupportedMethodFromMissingPath() throws Exception {
    mockMvc.perform(post("/api/orders/42"))
            .andExpect(status().isMethodNotAllowed());
}
~~~

This example assumes the controller only declares GET for that path and no other POST handler exists. If the application has a POST route, the result will naturally differ. Tests must reflect the full set of actual mappings.

## 7. Testing Business-Logic 404

When a resource does not exist, the test should prove that the request was routed properly and the domain exception was mapped:

~~~java
@Test
void returnsOrderNotFoundWhenMappedHandlerCannotFindOrder() throws Exception {
    given(orderService.findById(999L))
            .willThrow(new OrderNotFoundException(999L));

    mockMvc.perform(get("/api/orders/999")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound())
            .andExpect(handler().handlerType(OrderController.class))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));

    then(orderService).should().findById(999L);
}
~~~

The handler type assertion confirms Spring selected OrderController. The service was called with ID 999 and the domain exception was mapped to a 404 response. This is completely different from the wrong-URL test in the previous section.

If the service returns Optional.empty() instead of throwing an exception, configure the mock to return empty and assert the response similarly. Do not mock the service to throw NoHandlerFoundException in a business test; that exception belongs to the routing layer, not to an order lookup outcome.

## 8. Writing Tests That Demonstrate Both Kinds of 404

You can place both tests side by side so the contract is crystal clear:

~~~java
@Test
void unknownRouteDoesNotInvokeOrderService() throws Exception {
    mockMvc.perform(get("/api/unknown-route"))
            .andExpect(status().isNotFound());

    then(orderService).shouldHaveNoInteractions();
}

@Test
void unknownOrderInvokesMappedHandlerAndReturnsDomainCode()
        throws Exception {
    given(orderService.findById(999L))
            .willThrow(new OrderNotFoundException(999L));

    mockMvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound())
            .andExpect(handler().handlerType(OrderController.class))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));

    then(orderService).should().findById(999L);
}
~~~

The first test proves the request never reached the service. The second test proves the request entered the controller and returned the business error code. Both return 404 yet protect two distinct contracts.

If the application standardizes route errors into JSON with code ROUTE_NOT_FOUND, add an assertion on that error code in the first test. If route responses are handled by the default ErrorController, check the body matching the application's configuration rather than assuming a code field exists.

## 9. Diagnosing Unexpected 404s in Real Environments

When an endpoint unexpectedly returns 404, check in order:

1. Did the request reach the right host, port, context path, and servlet path?
2. Is the HTTP method correct?
3. Does the path have the right prefix, pluralization, version, and path variables?
4. Does the mapping have params, headers, consumes, or produces conditions?
5. Was the controller component-scanned or registered in the application context?
6. Is there a profile or conditional configuration preventing the bean/route from being registered?
7. Did a gateway, reverse proxy, or ingress rewrite the path before the request reached the application?
8. Does security intentionally hide the resource with a 404?
9. If the handler ran, did the service/repository genuinely fail to find the resource?
10. Which exception or error handler produced the final response?

In particular, the URL in a browser or client may differ from the URL the application receives due to context paths, proxy prefixes, or rewrite rules. Logging the request URI at the server layer and comparing it against route mappings pinpoints whether the error lies in the client, gateway, or Spring MVC.

## 10. Inspecting Registered Mappings in ApplicationContext

When you suspect a controller was not registered, inspect mappings in the context or use an actuator endpoint if enabled and properly secured.

In tests, you can inject RequestMappingHandlerMapping to inspect annotation-based mappings:

~~~java
@Autowired
RequestMappingHandlerMapping handlerMapping;

@Test
void registersOrderLookupMapping() {
    boolean found = handlerMapping.getHandlerMethods()
            .keySet()
            .stream()
            .anyMatch(info ->
                    info.getPatternValues()
                            .contains("/api/orders/{id}"));

    assertThat(found).isTrue();
}
~~~

The API for retrieving patterns can differ between older and newer Spring MVC versions; older versions may require the corresponding pattern condition API. This is a mapping configuration test, not a substitute for request tests. A mapping may be registered yet still fail to match due to method, params, headers, or media types.

If using functional routing, mappings will not necessarily appear in RequestMappingHandlerMapping. Inspect RouterFunction beans or send requests through a test client to verify functional routes.

## 11. Gateways and Reverse Proxies Can Generate 404 Before Requests Reach Spring

A 404 response is not always generated by the Spring application. A gateway, API management layer, ingress, or reverse proxy can return 404 when:

- The host route is not configured.
- The path prefix is rewritten or mismatched.
- The target service is not registered.
- The request goes to the wrong base path or version.
- The gateway intentionally hides an endpoint or service.

In this situation, Spring may never receive the request, so application logs show no corresponding access log. Correlate request IDs/correlation IDs between the gateway and the application, inspect response headers or error bodies produced by infrastructure, and read access logs at each tier.

Do not modify the controller merely because the client sees 404. If the request never reaches the application, changing Spring mappings will not fix a gateway routing issue.

## 12. Security May Intentionally Return 404

Some systems do not want to disclose whether a resource exists to callers lacking sufficient permissions. The security layer may return 404 instead of 403 to conceal the existence of the resource. In that case, 404 is neither a mapping error nor necessarily proof that the resource does not exist.

For example, a user forbidden from viewing orders of another tenant may receive 404 per security policy. Tests should verify this behavior intentionally:

- User in the same tenant with permission: returns 200 when the order exists.
- User in the same tenant when the order does not exist: returns 404.
- User from a different tenant: returns 404 if policy requires hiding resource existence.

Do not change 404 to 403 just for technical distinction if the security contract forbids disclosing existence. Conversely, if the API explicitly distinguishes access permissions from missing resources, 403 may be more appropriate. Follow the application's security contract.

## 13. Designing Error Codes and Logs for Easy Distinction

If an API needs to distinguish the two kinds of 404, stable error codes can help:

| Code | Meaning | Source |
|---|---|---|
| ROUTE_NOT_FOUND | No matching endpoint | Dispatcher/handler mapping |
| RESOURCE_PATH_NOT_FOUND | Resource handler found no static file | ResourceHttpRequestHandler |
| ORDER_NOT_FOUND | Valid endpoint, yet no matching order exists | Service/domain |
| CUSTOMER_NOT_FOUND | Valid endpoint, yet no matching customer exists | Service/domain |

Not every API needs all of these codes. Only expose codes that are genuinely meaningful to clients. If clients do not need the distinction, you can return a generic NOT_FOUND code in the response while still classifying the cause in internal logs and metrics.

When logging:

- Record the method, normalized URI, status, correlation ID, and error category.
- Separate route misses from domain-not-found events in metrics to spot wrong URLs or outdated clients.
- Never log tokens, personal data, or full sensitive query strings.
- Avoid logging full stack traces for ordinary 404s when no unexpected failure occurred.
- Keep the original exception in internal logs when investigating configuration bugs.

A spike in route misses may indicate a client calling the wrong API version or a bot scanning paths. A spike in ORDER_NOT_FOUND may mean clients are sending stale IDs, data was deleted, or a sync pipeline has an issue. Both metrics carry different operational meanings.

## 14. Common Diagnostic Mistakes

| Misconception | Why it is wrong | How to verify |
|---|---|---|
| Every 404 means the controller has no mapping | The controller may have run while the service found no data | Check the selected handler and service interactions |
| Every 404 is caused by a missing ID | The path or HTTP method might not match | Check the mapping and the actual request |
| 404 means the service returned null | The service may never have been called | Verify mock/service interactions or traces |
| The URL is right, so the mapping must match | Mappings also depend on method, params, headers, consumes, and produces | Read all RequestMapping conditions |
| POST with the wrong method must return 404 | If the path has a GET mapping, Spring usually returns 405 | Check the method exception/status |
| 404 always comes from Spring | A gateway, ingress, or security layer may respond before the controller | Compare logs across every tier |
| Enabling NoHandlerFoundException fixes every 404 | Domain-not-found and resource handlers are separate failure paths | Check the specific exception and Spring version |
| Catch every exception and return 404 | Can hide server or dependency failures | Map specific exceptions |
| Advice not running means the controller does not exist | The exception may be handled by another resolver or earlier layer before reaching the expected advice | Check exception resolvers, advice order, and traces |

## 15. Workflow for Testing and Troubleshooting a 404 Error

When adding an endpoint or investigating a 404 error, follow this sequence:

1. Identify the exact URL, method, context path, and request headers received by the server.
2. Check whether the mapping is registered in the context.
3. Check all mapping conditions, not just the path.
4. Confirm which handler was selected for the request.
5. If no handler matched, inspect NoHandlerFoundException or resource handler/error responses for your Spring version.
6. If the controller ran, inspect the service/repository and domain exceptions.
7. Write one test for a route miss and one test for domain not found.
8. Verify the appropriate status, error code, handler, and service interactions.
9. If the application sits behind a gateway or security layer, check responses at each layer.
10. Keep logs and metrics separating causes if operations need distinct visibility.

## 16. Conclusion

A 404 from a missing mapping and a 404 from business logic may share the same HTTP status, yet they originate in completely different places. When Spring finds no matching handler, the business controller does not run. When an endpoint matches and the controller invokes the service yet the resource is absent, 404 is a business outcome. Static resource handlers, security layers, or gateways can also produce other 404 responses.

Diagnose along the request path: did the request reach Spring, which handler did HandlerMapping select, did the controller run, was the service called, and which exception or error handler built the response? In tests, combine status assertions with handler type, service interactions, and error codes to protect both contracts clearly. That way, routing bugs are fixed in configuration or the client, while missing resources are handled by domain rules.
