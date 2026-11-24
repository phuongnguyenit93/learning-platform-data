# HandlerMapping, HandlerAdapter, and HandlerResultHandler in Spring WebFlux

## 1. Role in the request processing architecture

Spring WebFlux uses the **Front Controller** pattern. A central component called **DispatcherHandler** receives requests passed into Spring's web layer, then delegates to specialized components. The three important contracts are:

- **HandlerMapping**: finds the handler matching the current request.
- **HandlerAdapter**: knows how to invoke the chosen handler, regardless of which programming model the handler belongs to.
- **HandlerResultHandler**: receives the result from the handler invocation and completes the response, usually by writing a body or rendering a view.

The three components answer three different questions:

| Component | Question | Result |
| --- | --- | --- |
| HandlerMapping | Which endpoint/handler does this request belong to? | A handler object, or an empty Mono if none is found |
| HandlerAdapter | How should this handler object be invoked? | Mono<HandlerResult> |
| HandlerResultHandler | How should the return value be handled and the response written? | Mono<Void> signaling when response processing is complete |

**DispatcherHandler coordinates**, while the three components above provide the means to find, invoke, and handle the result. They do not replace one another, nor are they three steps called by the controller itself.

General flow:

~~~text
HTTP request
    |
    v
Server adapter / HttpHandler
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    +--> HandlerMapping #1
    |        |
    |        +--> no match: Mono.empty()
    |
    +--> HandlerMapping #2
    |        |
    |        +--> match: Handler object
    |
    +--> Matching HandlerAdapter
    |        |
    |        +--> invokes handler
    |        +--> Mono<HandlerResult>
    |
    +--> Matching HandlerResultHandler
             |
             +--> writes HTTP status, headers, body, or renders view
             |
             v
         Mono<Void>
             |
             v
       HTTP response completes
~~~

The diagram omits the exception handling, CORS, security, codec, and transport branches. It shows the main order of responsibilities in a WebFlux request.

## 2. DispatcherHandler is the coordination center

**DispatcherHandler** is a **WebHandler** that acts as the Front Controller in Spring WebFlux. It does not need to know every concrete handler type. Instead, it discovers infrastructure beans in the ApplicationContext and invokes those that implement WebFlux's contracts.

In a typical WebFlux configuration, DispatcherHandler is registered under the bean name **webHandler**. **WebHttpHandlerBuilder** can use the ApplicationContext to build the HttpHandler and assemble WebFilter/WebExceptionHandler along with the necessary components into the processing chain. The server adapter then connects the HttpHandler to an HTTP runtime such as Reactor Netty or a supported Servlet container.

DispatcherHandler typically coordinates these steps:

1. Obtains the list of **HandlerMapping**s and queries them in order.
2. Uses the **first handler found**.
3. Finds a **HandlerAdapter** that supports that handler.
4. Calls the adapter to receive a **HandlerResult**.
5. Picks the **first HandlerResultHandler that supports the HandlerResult**.
6. Waits for the result handler's Mono<Void> to complete to know when response processing has ended.

Key point: **a mapping returning a handler does not mean the response has been produced**. It has only determined who will handle the request. Likewise, once the adapter finishes invoking the handler, it is still not certain that the response has been written; the result still needs a result handler to process it.

## 3. HandlerMapping: finding a matching handler

### 3.1. Basic contract

The interface **org.springframework.web.reactive.HandlerMapping** defines the method:

~~~java
Mono<Object> getHandler(ServerWebExchange exchange);
~~~

This is the API signature for understanding the contract; it is not complete implementation code. **ServerWebExchange** represents the current HTTP context, including the request, response, and exchange attributes.

Result:

- If a matching endpoint is found, the Mono emits **one handler object**.
- If no handler is found, the Mono can complete empty (**Mono.empty()**).
- Lookup typically considers path, HTTP method, headers, parameters, content type, accept media type, and other routing conditions, depending on the implementation.

The handler object can be a HandlerMethod of an annotated controller, a HandlerFunction of a functional endpoint, a WebHandler, or another specialized handler type.

**HandlerMapping does not invoke the controller method.** It only decides which handler the request is routed to and may place some metadata about the pattern/URI variables into the ServerWebExchange.

### 3.2. Common HandlerMappings

| Implementation | How it finds a handler | Returned handler is typically |
| --- | --- | --- |
| **RequestMappingHandlerMapping** | Scans controllers and methods with @RequestMapping, @GetMapping, @PostMapping... | HandlerMethod |
| **RouterFunctionMapping** | Iterates over RouterFunctions and checks route predicates | HandlerFunction |
| **SimpleUrlHandlerMapping** | Looks up explicitly registered URL patterns | WebHandler or mapped handler |
| **WebSocketHandlerMapping** | Maps URLs to WebSocket handlers in the corresponding WebFlux configuration | WebSocket handler |

### 3.3. Annotated controller: RequestMappingHandlerMapping

Example:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {
    @GetMapping("/{id}")
    Mono<Product> find(@PathVariable String id) {
        return productService.findById(id);
    }
}
~~~

This is an illustrative snippet requiring Product and productService provided by the application. When the application starts up, **RequestMappingHandlerMapping** detects the controller and registers the mapping for GET /api/products/{id}.

When a GET /api/products/42 request arrives:

1. The mapping checks the path and HTTP method.
2. If other conditions match, it produces a handler result representing the **find** method.
3. DispatcherHandler passes that handler to an appropriate HandlerAdapter.

HandlerMapping does not run find("42") itself, does not call the repository, and does not serialize Product.

### 3.4. Functional endpoint: RouterFunctionMapping

Example:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/functional/products/{id}", handler::find)
            .build();
}
~~~

This is an illustrative configuration snippet with ProductHandler already registered as a bean. **RouterFunctionMapping** discovers RouterFunction beans, combines routes, and evaluates request predicates. When a route matches, it returns the corresponding HandlerFunction.

The difference from annotated controllers lies in **how handlers are declared and found**:

- Annotated controller: Spring scans annotations and methods.
- Functional endpoint: the application explicitly declares route predicates and HandlerFunctions.

Both can still go through DispatcherHandler and the corresponding adapter/result handler contracts.

### 3.5. Multiple mappings and priority order

DispatcherHandler queries HandlerMappings in order. **The first mapping that returns a handler is chosen**; subsequent mappings are no longer used to find another handler for that same request.

This matters when an application combines:

- static routes and annotated controllers;
- custom URL mappings and functional endpoints;
- WebSocket mappings and HTTP controllers;
- static resource mappings and API mappings.

If there are overlapping routes, configure order deliberately and test the actual URLs. Do not rely on arbitrary bean ordering or assume a specific mapping always wins.

Some mappings may return Mono.empty() to yield to the next mapping. **Finding no handler after querying all mappings** usually goes to the endpoint-not-found error branch (HTTP 404 via WebFlux's error-handling mechanism).

### 3.6. Metadata provided by the mapping

URL-based implementations can place information in **ServerWebExchange attributes**, such as:

- The chosen handler.
- Best matching pattern.
- URI template variables such as id = "42".
- Media types producible by the handler.
- Path within the mapping.

Not every HandlerMapping supports every attribute. Custom code should rely on contracts/attributes guaranteed by the implementation's documentation and avoid assuming an attribute always exists.

## 4. HandlerAdapter: invoking handlers without forcing DispatcherHandler to know details

### 4.1. Basic contract

The interface **org.springframework.web.reactive.HandlerAdapter** has two core methods:

~~~java
boolean supports(Object handler);

Mono<HandlerResult> handle(
        ServerWebExchange exchange,
        Object handler
);
~~~

**supports(handler)** determines whether the adapter can invoke this type of handler. **handle(exchange, handler)** performs the invocation and returns a Mono<HandlerResult>.

The reason for adapters: handlers do not share the same invocation mechanism. Annotated controllers require resolving annotations, arguments, binding, and reactive return values. Functional endpoints have HandlerFunctions and receive ServerRequest. WebSocket handlers have their own separate contract.

DispatcherHandler only needs to ask which adapter supports the object returned by the mapping. It does not need to write separate invocation logic for every kind of handler.

### 4.2. Common HandlerAdapters

| Implementation | Supported handler | Responsibility |
| --- | --- | --- |
| **RequestMappingHandlerAdapter** | HandlerMethod from annotated controllers | Resolves method parameters, reads request body, binds data, invokes controller method, and adapts return type |
| **HandlerFunctionAdapter** | HandlerFunction from functional endpoints | Adapts ServerWebExchange to the functional contract, invokes HandlerFunction, and wraps the result |
| **SimpleHandlerAdapter** | WebHandler | Invokes WebHandler directly |
| **WebSocketHandlerAdapter** | WebSocketHandler | Performs WebSocket handling according to the specialized contract |

### 4.3. What does RequestMappingHandlerAdapter do?

For a controller:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderDto> get(@PathVariable String id) {
    return orderService.find(id);
}
~~~

The adapter for annotated controllers needs to handle several things before producing a result:

- Read URI template variables and assign them to the **id** parameter.
- Handle @RequestParam, @PathVariable, @RequestHeader, @RequestBody, and the corresponding argument resolvers.
- Use **HttpMessageReader**/codecs to read the request body if needed.
- Perform conversion, validation, and data binding according to configuration.
- Invoke the method on the controller.
- Receive return values such as OrderDto, Mono<OrderDto>, Flux<OrderDto>, ResponseEntity, or supported reactive types.
- Create a **HandlerResult** along with the metadata needed for the result-handling step.

RequestMappingHandlerAdapter is not the final serializer. It helps invoke the method and prepare the HandlerResult; writing the body still belongs to HandlerResultHandler.

### 4.4. What does HandlerFunctionAdapter do?

For a functional endpoint:

~~~java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok().bodyValue("hello");
~~~

This is an illustrative snippet of a HandlerFunction. **HandlerFunctionAdapter** supports HandlerFunction, invokes the handler, and wraps ServerResponse into a HandlerResult. Then **ServerResponseResultHandler** handles ServerResponse to write the response.

Thus, the same DispatcherHandler can handle annotated controllers and functional endpoints using two different adapters. This is precisely the benefit of the contract: the dispatcher is not tied to one programming model.

### 4.5. Can an adapter return an empty Mono?

The handle contract returns **Mono<HandlerResult>**. Normally it emits one HandlerResult. However, the Javadoc allows the Mono to complete empty if the request has already been fully handled by the adapter and does not need to forward a HandlerResult to another result handler.

Therefore, **Mono.empty() at the three stages has different meanings**:

- Empty HandlerMapping: this mapping found no handler; DispatcherHandler can query the next mapping.
- Empty HandlerAdapter: the adapter indicates that the request has been fully handled and needs no further HandlerResult.
- Empty Mono returned from a controller: the handler was invoked, but there is no application value to emit; how the response is produced depends on the result handler and return type.

Do not lump all three cases together as "404".

## 5. HandlerResult: the bridge between invoking the handler and writing the response

**HandlerResult** is an object representing the result of invoking a handler or handler method. It may contain:

- The related handler object/method.
- The handler's return value.
- The declared return type.
- Binding/model context needed for processing.
- An exception-handling mechanism attached by the adapter if needed.

Example of a handler method returning:

~~~java
Mono<Product> find() {
    return Mono.just(new Product("P01", "Notebook"));
}
~~~

The adapter does not need to wait and block itself to obtain the Product. It can create a HandlerResult holding the return value of type Mono<Product> along with metadata. **HandlerResultHandler** continues processing that Publisher according to the reactive contract, without turning the entire request into a synchronous call.

HandlerResult **is not the final HTTP response**. It is an intermediate result wrapper so the framework can choose the appropriate way to write the response.

## 6. HandlerResultHandler: processing the result and completing the HTTP response

### 6.1. Basic contract

The interface **org.springframework.web.reactive.HandlerResultHandler** defines:

~~~java
boolean supports(HandlerResult result);

Mono<Void> handleResult(
        ServerWebExchange exchange,
        HandlerResult result
);
~~~

- **supports(result)** answers whether the result handler understands this kind of result.
- **handleResult(exchange, result)** processes the result, updates status/headers, and writes the body or renders the view.
- **Mono<Void>** represents that response writing has completed or emitted an error.

HandlerResultHandler does not look up endpoints and does not invoke controllers. It starts from an already-created HandlerResult.

### 6.2. Important default implementations

| Implementation | Result type handled | Default order |
| --- | --- | ---: |
| **ResponseEntityResultHandler** | ResponseEntity, usually from controllers | 0 |
| **ServerResponseResultHandler** | ServerResponse, usually from functional endpoints | 0 |
| **ResponseBodyResultHandler** | @ResponseBody methods or @RestController classes | 100 |
| **ViewResolutionResultHandler** | CharSequence, View, Model, Map, Rendering, or objects treated as model attributes | Integer.MAX_VALUE |

DispatcherHandler passes the HandlerResult to the **first HandlerResultHandler for which supports(result) returns true**, in the configured order. The default order lets specialized result handlers be evaluated before the general response-body result handler.

### 6.3. ResponseEntityResultHandler

A controller can return:

~~~java
@GetMapping("/products/{id}")
ResponseEntity<Mono<Product>> find(@PathVariable String id) {
    return ResponseEntity.ok(
            productService.find(id)
    );
}
~~~

This is an illustrative snippet with Product/service. **ResponseEntityResultHandler** handles ResponseEntity, including status and headers; the reactive body is written via the corresponding mechanism. If the controller returns ResponseEntity.notFound().build(), the 404 status is determined by the ResponseEntity.

### 6.4. ResponseBodyResultHandler

Given:

~~~java
@RestController
class HealthController {
    @GetMapping("/health")
    Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }
}
~~~

This is an illustrative snippet. @RestController is equivalent to a controller with response body semantics. **ResponseBodyResultHandler** handles the body result and uses appropriate **HttpMessageWriter**s to encode it into JSON, text, or another media type.

If the return value is Mono<T>, the framework processes the value when the Publisher emits a signal. If it is Flux<T>, the body can be written as a stream depending on the media type and codec.

### 6.5. ServerResponseResultHandler

A functional handler can return:

~~~java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello");
~~~

**ServerResponseResultHandler** invokes ServerResponse's writeTo mechanism to complete the response. It is the appropriate result handler for functional endpoints, while HandlerFunctionAdapter is the adapter that invokes HandlerFunction.

### 6.6. ViewResolutionResultHandler

If an application renders HTML using a view technology, the handler can return a view name, View, Model, Map, or Rendering. **ViewResolutionResultHandler** uses ViewResolvers to look up the view and render it with the model.

This is not a required step for every REST API. An API returning JSON typically uses ResponseBodyResultHandler or ResponseEntityResultHandler; the view result handler only participates when the result type matches.

## 7. Comparing the two processing paths: annotated controller and functional endpoint

### Path A: annotated controller

~~~text
GET /api/products/42
        |
        v
RequestMappingHandlerMapping
        |
        v
HandlerMethod (ProductController.find)
        |
        v
RequestMappingHandlerAdapter
        |
        v
HandlerResult (return value: Mono<Product>)
        |
        v
ResponseBodyResultHandler
        |
        v
HttpMessageWriter / JSON codec
        |
        v
HTTP 200 + JSON body
~~~

### Path B: functional endpoint

~~~text
GET /functional/products/42
        |
        v
RouterFunctionMapping
        |
        v
HandlerFunction<ServerResponse>
        |
        v
HandlerFunctionAdapter
        |
        v
HandlerResult (return value: Mono<ServerResponse>)
        |
        v
ServerResponseResultHandler
        |
        v
ServerResponse.writeTo(...)
        |
        v
HTTP response
~~~

Both paths use the same DispatcherHandler and the general contracts, while using the mapping, adapter, and result handler suited to each handler/return-value type.

## 8. Order and handler selection: why does the bean that appears first not simply win?

There are two independent selections:

**Pass 1 — choosing the handler:**

- DispatcherHandler queries HandlerMappings in order.
- Each mapping checks the request.
- The first mapping that finds a handler decides the handler for the request.
- If no mapping matches, the request enters the not-found branch.

**Pass 2 — choosing how to handle the result:**

- A suitable HandlerAdapter is selected via its supports(handler) capability.
- The adapter creates a HandlerResult.
- HandlerResultHandlers are evaluated in order.
- The first HandlerResultHandler that supports the result is used.

This means:

- The order of HandlerMappings is not the order of HandlerAdapters.
- The order of HandlerResultHandlers does not decide which endpoint is selected.
- One HandlerAdapter can support multiple kinds of handlers, while still having to define its contract clearly.
- A general HandlerResultHandler should not grab every result if specialized results need to be handled first.

When registering your own implementation, design **supports(...)** accurately enough. If supports is too broad, the result may be picked up first by the wrong handler. If it is too narrow, no implementation accepts it and the response is not handled as expected.

## 9. Errors and exceptions in the dispatch chain

Errors can happen at many stages:

1. **Before mapping:** a WebFilter or initial request processing emits an error.
2. **In HandlerMapping:** an error while analyzing/routing the request.
3. **In HandlerAdapter:** a synchronous error while resolving parameters or invoking the method.
4. **After the handler returns a reactive type:** the returned Mono/Flux emits onError later.
5. **In HandlerResultHandler:** an error encoding, writing the response, or rendering the view.
6. **In transport:** the client disconnects or I/O fails.

Not every error appears immediately when the controller method is invoked. A controller may return a Mono successfully as far as creating the object goes, while the Publisher only emits an error when subscribed to later.

### 9.1. DispatchExceptionHandler and HandlerResult

A HandlerAdapter can:

- Handle errors that occur directly while invoking the handler.
- Attach a **DispatchExceptionHandler** mechanism to HandlerResult to handle errors arising late from a reactive return value or result handling.
- Implement DispatchExceptionHandler to participate in handling errors that occur before a handler is selected, depending on the contract.

In annotated controllers, the **@ExceptionHandler** and **@ControllerAdvice** mechanisms can be used to convert exceptions into responses according to the WebFlux configuration.

At the outermost layer there is also **WebExceptionHandler** in the WebFilter chain. If an error is not handled by a mechanism closer to the handler, it can propagate to the exception handler at the WebFlux layer.

### 9.2. Distinguishing mapping errors from an empty Mono

| Situation | Typical meaning |
| --- | --- |
| No HandlerMapping finds a handler | No matching endpoint; usually returns 404 |
| Handler method was selected and returns Mono.empty() | No body value; does not automatically mean 404 |
| Handler returns ResponseEntity.notFound() | ResponseEntity explicitly sets HTTP 404 |
| Handler emits onError | Error is handled by the appropriate exception handling |
| HandlerResultHandler does not support the result | No matching result handler; usually a configuration/unsupported return value error |

If an API needs to return 404 when no record exists, explicitly map the Mono.empty() case in the service/controller, for example with switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND))). Do not rely on assuming every empty Mono turns into 404.

## 10. Runnable Java 17+ example: annotated and functional in one application

This example creates two endpoints using the two programming models. It lets you observe two different dispatch paths both running on Spring WebFlux.

Structure:

~~~text
webflux-dispatch-demo/
├── pom.xml
└── src/main/java/example/demo/
    ├── DemoApplication.java
    ├── GreetingController.java
    └── FunctionalRoutes.java
~~~

### 10.1. pom.xml

The example uses Spring Boot **3.5.5** and Java 17+; the starter manages compatible Spring Framework, Reactor, and server runtime versions:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-dispatch-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. DemoApplication.java

~~~java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. GreetingController.java

~~~java
package example.demo;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping(
            value = "/annotated/hello",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of(
                "message", "Hello from annotated controller"
        ));
    }
}
~~~

### 10.4. FunctionalRoutes.java

~~~java
package example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> functionalRoutes() {
        return RouterFunctions.route(
                GET("/functional/hello"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("Hello from functional endpoint")
        );
    }
}
~~~

### 10.5. Running the application and observing the results

From the directory with pom.xml:

~~~bash
mvn spring-boot:run
~~~

Call the annotated endpoint:

~~~bash
curl -s http://localhost:8080/annotated/hello
~~~

Body:

~~~json
{"message":"Hello from annotated controller"}
~~~

Main dispatch path: **RequestMappingHandlerMapping → RequestMappingHandlerAdapter → HandlerResult → ResponseBodyResultHandler**.

Call the functional endpoint:

~~~bash
curl -s http://localhost:8080/functional/hello
~~~

Body:

~~~text
Hello from functional endpoint
~~~

Main dispatch path: **RouterFunctionMapping → HandlerFunctionAdapter → HandlerResult → ServerResponseResultHandler**.

The two endpoints can coexist because WebFlux has mappings and adapters suitable for each programming model. This example does not print DispatcherHandler's internal logs itself; the path is determined from the route type, handler, and return type.

## 11. When do you need to customize these three contracts?

In an ordinary application, **you do not need to create your own HandlerMapping, HandlerAdapter, or HandlerResultHandler**. WebFlux Config and Spring Boot already provide the default implementations.

You should only extend when there is a genuinely specialized handler or result type:

| Need | Extension point to consider |
| --- | --- |
| Routes from custom metadata or a custom registry | Custom HandlerMapping |
| Invoking a handler type supplied by a library/domain | Custom HandlerAdapter |
| Handling a special return value type or custom response protocol | Custom HandlerResultHandler |
| Only need to change codecs, CORS, view resolvers, argument resolvers, or formatters | Prefer WebFluxConfigurer and specialized configuration APIs |

### 11.1. Requirements for a custom HandlerMapping

- Return a Mono of the handler per contract; Mono.empty() when not matching.
- Have a clear order so it does not shadow other mappings.
- Handle path, method, content negotiation, and validation appropriately.
- Do not perform business logic or blocking I/O during route resolution.
- Do not keep request-specific state in fields of a singleton bean.
- If the mapping needs an asynchronous lookup, represent it with a Publisher and manage cancellation properly.

### 11.2. Requirements for a custom HandlerAdapter

- **supports(handler)** must accurately identify the handler type.
- **handle(exchange, handler)** returns Mono<HandlerResult> per contract.
- Do not block yourself to wait for reactive results.
- Deliberately handle both synchronous and deferred errors.
- Preserve the metadata/return type needed for the result handler to understand the result.
- Do not write the response directly and still return a HandlerResult that causes the response to be processed twice; if the adapter has already handled it completely, use the appropriate empty-completion contract.

### 11.3. Requirements for a custom HandlerResultHandler

- **supports(result)** must not accept results belonging to other specialized implementations.
- Write the correct status, headers, content type, and body.
- Use **HttpMessageWriter/codecs** or the appropriate response API instead of concatenating JSON strings manually.
- Return Mono<Void> representing the response write; write errors must be propagated in the reactive chain.
- Respect cancellation and do not hold buffers/requests after the response ends.
- Note that a response can only be committed once; after part of the body has been written, you cannot arbitrarily switch to another error response.

## 12. Debugging when a request hits the wrong handler or the response has the wrong format

When a request returns 404, 406, 415, or an incorrect body, check step by step in order:

1. **Did the request reach WebFlux?** Check server, port, context path, and WebFilters.
2. **Which HandlerMapping could match?** Check path, method, params, headers, consumes/produces, and route order.
3. **Which handler object was selected?** Annotated HandlerMethod, functional HandlerFunction, WebHandler, or another handler?
4. **Which HandlerAdapter supports that object?** Check the handler type and adapter configuration.
5. **What does HandlerResult contain?** Are the return value, declared return type, and metadata right?
6. **Which HandlerResultHandler accepts the result?** Check the return type and supports(...) of the result handler.
7. **Can the codec write the media type?** Check HttpMessageWriter, Accept, Content-Type, and body type.
8. **Is there a deferred exception?** Mono/Flux can error after the controller method has already returned.
9. **Has the response already committed?** Errors occurring after a partial body was sent may no longer be able to change the status.
10. **Are there duplicate routes or unintended order?** Check HandlerMapping order and functional/annotated routes.

You can turn on selective logging for WebFlux packages in development. Do not keep overly broad DEBUG logging on in production if it logs request metadata or sensitive data. With Spring Boot Actuator, the mappings endpoint can help inspect registered endpoints, though it does not replace understanding adapters/result handlers.

## 13. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| HandlerMapping invokes the controller | Mapping only selects the handler object |
| HandlerAdapter decides which URL matches | Mapping decides the route; the adapter only invokes the selected handler |
| HandlerResultHandler calls the business service | The result handler processes the result and writes the response |
| HandlerResult is the final HTTP response | It is an intermediate object containing the return value/context |
| One request always uses every HandlerMapping | The first mapping that finds a handler decides |
| Mono.empty() always returns 404 | The meaning depends on whether it is empty at mapping, adapter, or return value |
| Every controller uses the same HandlerAdapter | Annotated, functional, WebSocket, and WebHandler have different adapters |
| Returning a Mono from a controller means the adapter waits with block() | The adapter/result pipeline preserves reactive semantics |
| Every HandlerResultHandler serializes JSON | There are result handlers for ResponseEntity, ServerResponse, body, and views |
| Adding a custom result handler is always safe | Wrong supports/order can hijack another handler's results |
| Errors only happen when the controller method throws an exception | A Publisher can emit onError after the method has already returned |
| Writing the response in the adapter and then returning a normal HandlerResult | Risks processing the response twice; must follow the proper completion contract |

## 14. Checklist to remember along the request lifecycle

When tracing a request, ask yourself:

- **Mapping:** Which mapping accepts this URL/method/headers? What handler object does it return?
- **Adapter:** Which adapter supports that object? How does it resolve arguments and invoke the handler?
- **HandlerResult:** What are the return value and declared type? Is there a deferred Mono/Flux?
- **Result handling:** Which result handler supports the result? Which status, headers, codec, or view does it choose?
- **Reactive lifecycle:** Can an error be emitted late? Where does cancellation occur? Has the response committed?
- **Ordering:** Is any custom mapping or result handler taking priority due to order?
- **Not found vs empty:** Does the request have no handler, or does a handler exist without emitting a value?
- **Extension:** Can it be configured via WebFluxConfigurer before needing to implement the contract yourself?

## 15. Conclusion

**HandlerMapping** answers *which handler this request belongs to*; **HandlerAdapter** answers *under which contract to invoke that handler*; **HandlerResultHandler** answers *how to process the result and write the response*. **DispatcherHandler** connects these three responsibilities into a unified workflow.

In annotated controllers, the usual path is **RequestMappingHandlerMapping → RequestMappingHandlerAdapter → ResponseBodyResultHandler/ResponseEntityResultHandler**. In functional endpoints, the usual path is **RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler**.

Understanding these three contracts makes debugging routing, return values, content negotiation, and exception handling much more accurate. In most projects, use the built-in implementations and WebFlux Config; only create custom mappings/adapters/result handlers when there is a genuinely new contract to integrate.

**Official documentation:**
- [Spring Framework Reference — DispatcherHandler, special beans, processing, and result handling](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework Javadoc — HandlerMapping](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerMapping.html)
- [Spring Framework Javadoc — HandlerAdapter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerAdapter.html)
- [Spring Framework Javadoc — HandlerResultHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html)
- [Spring Framework Reference — Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
