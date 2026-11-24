# Distinguishing Web Server Configuration from Request-Processing Layer Configuration

## 1. Two Distinct Configuration Layers

A Spring Boot web application has two configuration groups that are often confused:

1. **Web server/container configuration:** determines where the application listens and how the container accepts HTTP connections. Examples: port, bind address, TLS, compression, connection/thread limits, graceful shutdown, and session.
2. **Request-processing layer configuration:** determines which requests Spring recognizes, which controller/handler is selected, how filters/interceptors/security are applied, how request data is bound, how responses are converted, and how exceptions are handled.

The two layers are related but do not replace each other. Changing the port does not change a controller's URL mapping. Adding an MVC interceptor does not open a port, configure TLS, or increase the number of connections Tomcat accepts. Setting a context path does not create a controller; controller mappings do not configure the connector.

This lesson uses **Spring Boot 3.3.x, Java 17+, and Spring MVC on the Servlet stack** as the primary example, then contrasts it with WebFlux. The goal is to choose the right extension point, read the right auto-configuration, and test at the right layer.

## 2. Flow of an HTTP Request

With Spring MVC running on embedded Tomcat, the typical flow is:

~~~text
Client
  |
  v
Network socket / TLS / HTTP connector
  |
  v
Embedded servlet container (Tomcat)
  |
  v
Servlet Filter chain
  |  - Spring Security FilterChainProxy
  |  - application filters
  v
DispatcherServlet
  |
  v
HandlerMapping ----> finds matching controller/handler
  |
  v
HandlerAdapter
  |
  v
Controller method
  |  - argument resolution
  |  - validation
  |  - business service
  v
Return-value handling / HttpMessageConverter
  |
  v
Servlet response -> Filter chain -> Connector -> Client
~~~

Other branches in the flow:

- No handler found: Spring MVC may return 404 or route through resource/error handling depending on configuration.
- Controller or argument resolver throws an exception: HandlerExceptionResolver and @ControllerAdvice can handle it.
- Interceptors have callbacks before/after the handler and upon request completion; they run after MVC has selected a handler.
- Servlet Filters run at the Servlet container layer, before DispatcherServlet according to filter mapping/order, so they can cover requests that do not go through a controller.
- TLS handshake, sockets, connector limits, and the server thread pool sit ahead of Spring MVC; controllers cannot configure these parts.

The diagram shows the typical path. Error dispatches, static resources, async requests, other servlets, and the management context may follow separate processing paths.

## 3. Web Server Configuration: Port, Connector, and Server Lifecycle

### 3.1. Common Properties

| Property | Effect | Example |
|---|---|---|
| **server.port** | HTTP port the embedded server listens on | 8080 |
| **server.address** | Network interface to bind | 127.0.0.1 |
| **server.servlet.context-path** | Common prefix of the Servlet application | /shop |
| **server.compression.enabled** | Enables server-level response compression | true |
| **server.compression.mime-types** | MIME types to compress | application/json |
| **server.compression.min-response-size** | Response size threshold | 2KB |
| **server.shutdown** | Server shutdown policy | graceful |
| **server.ssl.*** | TLS certificate, key, protocol, and SSL settings | per certificate |
| **server.tomcat.threads.max** | Tomcat processing thread limit | 200 (example) |
| **server.tomcat.max-connections** | Maximum connections Tomcat accepts | per load |
| **server.tomcat.accept-count** | Connection queue when limit is reached | per load |
| **server.servlet.session.timeout** | Servlet session timeout | 30m |

Property names and values depend on the server. The server.tomcat.* group is meaningful only when the embedded server is Tomcat; Jetty and Undertow have their own namespaces. Do not copy Tomcat thread/connection settings to another server.

Configuration example:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
  compression:
    enabled: true
    min-response-size: 2KB
    mime-types:
      - application/json
      - text/html
  shutdown: graceful
  servlet:
    context-path: /shop
    session:
      timeout: 30m
~~~

When this configuration is used, a controller mapped to /orders/{id} is called via path /shop/orders/42. The /shop prefix comes from the Servlet context path; it is not part of @RequestMapping. Port 8080 and bind address 0.0.0.0 determine where clients connect.

### 3.2. Distinguishing Port, Context Path, and Controller Mapping

Suppose:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /shop
~~~

Controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return new OrderView(id, "ACCEPTED");
    }
}
~~~

The full request is http://localhost:8080/shop/orders/42:

- **localhost:8080:** server address and port.
- **/shop:** Servlet application context path.
- **/orders/42:** mapping declared by Spring MVC/controller.

If server.port changes to 9090, the URL changes port while the mapping remains /orders/42. If the context path changes to /api, the URL prefix changes while the controller needs no mapping change. If @RequestMapping changes, the route changes while the connector still listens on the same port.

Do not put server.servlet.context-path into an MVC interceptor to add a prefix; interceptors are not responsible for container-level routing.

### 3.3. TLS, Compression, and Connection Limits

The following operations belong to the server/container:

- TLS handshake and certificate selection.
- HTTP connector, keep-alive, max connections, accept queue.
- Server worker threads and request concurrency limits.
- Server-layer response compression.
- Graceful shutdown and waiting time for in-flight requests.
- Container-level Servlet sessions/cookies.

If HTTPS does not work, check server.ssl.*, certificate/key, protocol, port, and reverse proxy first. Editing a controller or MVC converter cannot fix a TLS handshake.

If the server is overloaded, inspect connections, queues, thread pools, request duration, and downstream dependencies. Increasing server.tomcat.threads.max does not automatically make the database or downstream services faster; adding threads can increase pressure on dependencies and memory.

### 3.4. Customizing the Server Factory

When built-in properties are not enough, Spring Boot allows customizing the factory before the server is created. For the Servlet stack, the commonly used extension point is WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>.

~~~java
package example.web;

import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ServerFactoryConfiguration {

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>
            servletServerCustomizer() {
        return factory -> factory.setPort(9090);
    }
}
~~~

This is an API-complete Java configuration for a Servlet web application using Spring Boot Web. When the customizer is applied, the factory uses port 9090. If server.port is also declared, determine the configuration source and application order to avoid two places owning the same decision. For ports that vary by environment, properties are usually clearer than hard-coding in a customizer.

When you truly need Tomcat APIs, use WebServerFactoryCustomizer<TomcatServletWebServerFactory> and the appropriate connector/context customizer. Do not put Tomcat code into configuration shared with Jetty or Undertow.

**Timing:** server factory customizers run during web server preparation, before the server starts accepting requests. They are not per-HTTP-request callbacks.

## 4. Request-Processing Layer Configuration in Spring MVC

### 4.1. DispatcherServlet and MVC Components

Spring Boot auto-configures Spring MVC when the application uses the Servlet web stack and the appropriate conditions match. Key components:

- **DispatcherServlet:** front controller receiving requests and dispatching processing.
- **HandlerMapping:** locates the matching handler for a request.
- **HandlerAdapter:** invokes the selected handler.
- **HandlerInterceptor:** hook before/after the handler and after request completion.
- **HttpMessageConverter:** reads request bodies and writes response bodies, e.g., JSON.
- **HandlerExceptionResolver / @ControllerAdvice:** handles exceptions during MVC processing.
- **WebMvcConfigurer:** extension point to add interceptors, formatters, converters, argument resolvers, CORS mappings, and other MVC configurations.

These extension points change how Spring processes a request after the request has reached the Servlet container. They do not change the port, TLS, connector, or server thread pool.

### 4.2. Controllers and Request Mapping

Controllers declare routes and application behavior:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return new OrderView(id, "ACCEPTED");
    }
}

record OrderView(long id, String status) {}
~~~

Spring MVC locates the matching method via HandlerMapping, then HandlerAdapter invokes the method. Path variable id is resolved and converted to type long. The returned object is written to the response using a message converter, typically JSON if Jackson is present and content negotiation matches.

This is application/request-layer configuration, not web server configuration.

### 4.3. WebMvcConfigurer: Customizing MVC

Example registering an interceptor:

~~~java
package example.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class MvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RequestTraceInterceptor())
                .addPathPatterns("/orders/**");
    }

    static class RequestTraceInterceptor implements HandlerInterceptor {

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {
            request.setAttribute("request-start-nanos", System.nanoTime());
            response.setHeader("X-Mvc-Interceptor", "applied");
            return true;
        }
    }
}
~~~

The interceptor above applies only to handler path /orders/**. It adds a request attribute and response header to illustrate the point after MVC has selected a handler. It does not run as a network connector and does not change the server port.

If you want an operation covering requests without an MVC handler, static resources, or other servlets, look at Servlet Filters instead of MVC interceptors.

### 4.4. Servlet Filter: Sitting Before DispatcherServlet

Filters are a standard Servlet mechanism. They can inspect requests/responses before the request enters DispatcherServlet, or after the chain returns. Example registering a filter:

~~~java
package example.web;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration(proxyBeanMethods = false)
class FilterConfiguration {

    @Bean
    FilterRegistrationBean<OncePerRequestFilter> requestMarkerFilter() {
        OncePerRequestFilter filter = new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain filterChain)
                    throws ServletException, IOException {
                response.setHeader("X-Request-Filter", "applied");
                filterChain.doFilter(request, response);
            }
        };

        FilterRegistrationBean<OncePerRequestFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(filter);
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }
}
~~~

The illustrative filter applies to the registered URL patterns. filterChain.doFilter forwards the request to the next filter or servlet. If it is not called, the filter can intentionally terminate the request; this must be done deliberately.

Do not use filters arbitrarily to replace controller mappings or business authorization. For authentication/authorization, use the Spring Security filter chain. Filter order can affect execution order; do not rely on component scan order.

### 4.5. Differences Between Filter and HandlerInterceptor

| Criterion | Servlet Filter | Spring MVC HandlerInterceptor |
|---|---|---|
| Where does it live? | Servlet container | Spring MVC |
| Timing | Before/after servlet along the filter chain | After MVC selects handler, around handler execution |
| Scope | URL pattern/servlet mapping | Handler mapping/path pattern |
| Requests not reaching a controller | Can run if mapping matches | Does not run if there is no matching MVC handler |
| Common uses | Security, request wrapping, correlation ID, servlet-layer CORS | Logic tied to MVC handler, locale/context, or timing |
| Configuration | Filter, FilterRegistrationBean, Spring Security | WebMvcConfigurer.addInterceptors |

Spring Security uses the Servlet Filter chain (via FilterChainProxy) to protect requests. Do not treat HandlerInterceptor as a replacement for Spring Security, especially when protecting static resources, error dispatches, other servlets, or flows not passing through an MVC handler.

## 5. Configuration Differences Between Spring MVC and WebFlux

Not every Spring Boot web application runs on the Servlet stack.

| Aspect | Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|---|
| Common servers | Tomcat, Jetty, Undertow | Reactor Netty, Tomcat/Jetty reactive support |
| Server factory | Servlet web server factory | Reactive web server factory |
| Front controller | DispatcherServlet | DispatcherHandler |
| Filter | jakarta.servlet.Filter | WebFilter |
| MVC config | WebMvcConfigurer | WebFluxConfigurer |
| Controller | MVC handler method | Reactive handler method, often returning Mono/Flux |
| Blocking I/O | Traditional Servlet model can use blocking | Avoid blocking on the event-loop; prefer reactive/non-blocking APIs |

A configuration using WebMvcConfigurer does not customize WebFlux. Likewise, jakarta.servlet.Filter is not a WebFlux WebFilter.

In WebFlux, requests pass through the reactive HTTP server, WebFilter chain, and DispatcherHandler. You can use WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory> to customize the reactive server factory, but not a Servlet-specific factory. If the classpath contains both MVC and WebFlux, identify which application context type Spring Boot selected instead of guessing from a single dependency.

## 6. Spring Boot 3.3 Application Example: Placing Configuration at the Right Layer

A minimal project can use these dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Application:

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebExampleApplication.class, args);
    }
}
~~~

Controller:

~~~java
package example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return new OrderView(id, "ACCEPTED");
    }
}

record OrderView(long id, String status) {}
~~~

Server configuration in application.yml:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
    min-response-size: 2KB
~~~

The Filter and MVC interceptor configurations from earlier sections can be placed in a package discovered by component scan. If you also add a server factory customizer setting port 9090, that value becomes an additional configuration source; remove one of the two sources or define a clear policy to avoid conflicts.

After starting the application, send a request:

~~~bash
curl -i http://localhost:8080/orders/42
~~~

Illustrative response (header order may differ):

~~~http
HTTP/1.1 200
Content-Type: application/json
X-Request-Filter: applied
X-Mvc-Interceptor: applied

{"id":42,"status":"ACCEPTED"}
~~~

The filter header is added at the Servlet Filter; the interceptor header is added after Spring MVC selects the handler. JSON is produced from the controller return value and message converter. Port 8080 comes from server configuration.

## 7. Which Property Belongs to Which Layer?

| Requirement | Appropriate configuration/extension point | Do not use |
|---|---|---|
| Change listening port | server.port or server factory customizer | @RequestMapping, interceptor |
| Bind to a specific interface | server.address | MVC CORS mapping |
| Common prefix for Servlet app | server.servlet.context-path | Adding prefix in every controller |
| TLS/certificate | server.ssl.* or reverse proxy/ingress per architecture | Controller, HttpMessageConverter |
| Server-level response compression | server.compression.* or proxy | HandlerInterceptor |
| Limit Tomcat threads/connections | server.tomcat.* or Tomcat factory customizer | @Async, MVC interceptor |
| Route request to controller | @RequestMapping / HandlerMapping | server.port |
| Change JSON serialization | Jackson configuration / HttpMessageConverter / builder customizer | Tomcat connector |
| Add logic before servlet | Servlet Filter / FilterRegistrationBean | WebMvcConfigurer |
| Logic around MVC handler | HandlerInterceptor / WebMvcConfigurer | Server factory customizer |
| Authentication/authorization | Spring Security SecurityFilterChain | Hand-written MVC interceptor |
| Handle controller exceptions | @ControllerAdvice / HandlerExceptionResolver | Connector error page for all cases |
| Add MVC formatter/converter | WebMvcConfigurer | WebServerFactoryCustomizer |

### Context Path and Management Path

server.servlet.context-path affects the main Servlet application. Actuator has its own management base path, and the management server can run on a separate port via management.server.port. This is management web server/context configuration, not business controller mapping. When using a separate port, protect management endpoints with appropriate network policy and security.

## 8. Reading Auto-Configuration by Layer

In Spring Boot 3.3, key auto-configurations for a Servlet web application include:

- **ServletWebServerFactoryAutoConfiguration:** creates/configures the Servlet web server factory and integrates customizers.
- **DispatcherServletAutoConfiguration:** registers DispatcherServlet and related components.
- **WebMvcAutoConfiguration:** configures Spring MVC, message converters, resource handling, and MVC infrastructure when conditions match.

Class names guide where to read the source, but do not deduce specific properties from an auto-configuration's name alone. Look up property metadata, condition annotations, bean methods, and actual customizers in the version you are using.

When investigating a change:

1. Determine whether the property belongs to the server.*, spring.mvc.*, spring.web.* prefix or a specific bean API.
2. Locate the responsible auto-configuration/bean.
3. Check classpath, property conditions, and user bean conditions.
4. Determine whether it affects the factory/container or MVC infrastructure.
5. Determine whether the callback runs during server initialization, MVC context setup, or per request.
6. Test with the tool corresponding to that layer.

For example, server.port is consumed by the server factory; spring.mvc.* typically affects MVC infrastructure; @RequestMapping is handled by handler mapping. Using the wrong prefix usually produces no compile error and simply causes the application to lack the expected behavior.

## 9. Testing at the Right Layer: MockMvc and RANDOM_PORT

### 9.1. MockMvc Tests the Request-Processing Layer

MockMvc runs Spring MVC through mock servlet APIs, without opening real sockets or starting an embedded server as an actual HTTP listener. It is suitable for testing:

- Request mappings/controllers.
- Filters and interceptors in the test context.
- Argument binding, validation, and message conversion.
- Spring Security authorization.
- Exception handling and response status/body.

Example:

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderMvcTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void requestPassesThroughFilterAndMvcInterceptor() throws Exception {
        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Filter", "applied"))
                .andExpect(header().string("X-Mvc-Interceptor", "applied"))
                .andExpect(content().json(
                        "{"id":42,"status":"ACCEPTED"}"));
    }
}
~~~

With the Filter and MVC interceptor configurations from earlier sections, the test confirms both request-processing layers apply to MVC requests. It **does not prove** that TLS, connectors, ports, server threads, network binding, or reverse proxies work.

### 9.2. RANDOM_PORT Tests the Real Embedded Server

Use @SpringBootTest(webEnvironment = RANDOM_PORT) so Spring starts an embedded server on an available port and sends real HTTP requests:

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EmbeddedServerTests {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    @Test
    void embeddedServerAcceptsHttpRequest() {
        ResponseEntity<String> response =
                http.getForEntity("/orders/42", String.class);

        assertThat(port).isPositive();
        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody())
                .contains(""id":42")
                .contains(""status":"ACCEPTED"");
        assertThat(response.getHeaders().getFirst("X-Request-Filter"))
                .isEqualTo("applied");
    }
}
~~~

This test starts a real web server in the JVM and tests HTTP over the assigned port. It is useful for confirming that the connector and request pipeline cooperate. However, RANDOM_PORT does not test fixed production ports, DNS, load balancers, firewalls, external TLS termination, or deployment network policies.

### 9.3. Choosing Tests by Question

| Question to verify | Suitable test |
|---|---|
| Does controller mapping return the right JSON? | MockMvc |
| Do Filters/Interceptors apply? | MockMvc |
| Do security rules return 401/403/200 correctly? | MockMvc + Spring Security Test |
| Does the embedded server start and accept HTTP? | RANDOM_PORT + TestRestTemplate/WebTestClient |
| Is the server port property bound to the factory? | ApplicationContextRunner/factory test or appropriate RANDOM_PORT |
| Are TLS certificates and handshake correct? | HTTPS integration test with test certificate |
| Do reverse proxy/ingress/firewall route properly? | Deployment/environment test |
| Do thread pool/connection limits handle load? | Load test and observability on a real server |

Do not use a MockMvc test to conclude that connectors or TLS are correct. Conversely, a passing RANDOM_PORT smoke test does not prove every controller validation, security role, or exception mapping has been thoroughly tested.

## 10. Diagnostic Workflow: Is the Issue at the Server or Request-Processing Layer?

### Symptom A: Cannot Connect to the Application

Check:

- Application startup logs: did the embedded server start, and what is the actual port?
- server.port, server.address, and container port mappings.
- Is the port already occupied by another process?
- Docker/Kubernetes Service, port-forward, firewall, ingress, and security groups.
- TLS/certificate/protocol if connecting over HTTPS.
- Was the management port confused with the application port?

If a TCP connection cannot be opened, editing controller mappings or interceptors usually will not solve the cause.

### Symptom B: Connected Successfully but Receiving 404

Check:

- Context path (e.g., /shop).
- Is the controller package component-scanned?
- Are @RequestMapping and the HTTP method correct?
- Did HandlerMapping register the endpoint?
- Is a static resource handler or servlet mapping claiming the path?
- Does a reverse proxy rewrite the prefix?

404 typically lies in the routing/request layer or proxy mapping, not a port listener error if you connected and received an HTTP response.

### Symptom C: Receiving 401 or 403

Check the Spring Security filter chain, authentication providers, roles/authorities, CSRF (especially write requests), and SecurityFilterChain ordering. MVC interceptors are not a replacement for the security filter chain.

### Symptom D: Slow Requests or Timeouts

Break down time across segments:

- Connection/TLS/queue and server thread availability.
- Filter/security.
- Controller/service.
- Database or downstream HTTP calls.
- Serialization and response write.

Do not increase server threads by default. If the database connection pool is already saturated, adding server threads can lengthen the database queue. Use metrics and traces to locate the bottleneck.

### Symptom E: Right Controller but Wrong Response Format

Check HttpMessageConverter, Jackson modules/customizers, content negotiation, produces, Accept header, formatters, and @ControllerAdvice. This is MVC response-processing, not the server connector.

## 11. Common Mistakes

- **Changing the port with @RequestMapping:** route mappings do not control the socket listener; use server.port or a server factory customizer.
- **Using WebMvcConfigurer to enable HTTPS:** TLS belongs to the server/connector or reverse proxy, not MVC interceptors/configurers.
- **Confusing context path with controller path:** server.servlet.context-path adds a prefix for the Servlet application; @RequestMapping declares the handler path.
- **Using Filter and Interceptor interchangeably:** filters run in the Servlet chain; interceptors attach to MVC handlers. Choose based on the scope of requests to handle.
- **Using HandlerInterceptor as the sole security layer:** security should live in the Spring Security filter chain; interceptors do not cover all request/servlet dispatch types.
- **Using Servlet Filter in WebFlux:** WebFlux uses WebFilter; the Servlet API is not the reactive filter API.
- **Putting Tomcat-specific customizers in shared configuration:** the configuration will only run with Tomcat; consider server-agnostic interfaces or separate by classpath.
- **Assuming @Order on a customizer changes request order:** it only takes effect in its corresponding sorting mechanism; callbacks must be invoked by a consumer and a server customizer is not a request interceptor.
- **Using MockMvc to test port/TLS:** MockMvc does not open network sockets; use RANDOM_PORT or appropriate HTTPS/deployment tests.
- **Increasing thread pools to fix every timeout:** inspect downstream pools, CPU, memory, queues, and latency first.
- **Confusing management port with application port:** management.server.port is for the management server when configured separately; server.port is the main application port.
- **Changing base path to fix 404 without checking proxy/context path:** inspect the entire URL from client to controller.
- **Registering the same filter twice:** avoid using both @Component and FilterRegistrationBean for the same instance/logic unintentionally; check mapping and order.
- **Creating custom MVC configuration and accidentally replacing auto-config:** implement WebMvcConfigurer to extend when possible; use @EnableWebMvc only when deliberately taking control of MVC configuration and understanding default auto-configurations will change.

## 12. Self-Check Questions

1. Want to change the application from listening on port 8080 to 9090. What do you use? **server.port or WebServerFactoryCustomizer.**
2. Want every application URL to have the /shop prefix. What do you use? **server.servlet.context-path** on the Servlet stack.
3. Want URL /orders/{id} to invoke a controller method. What do you use? **@RequestMapping/@GetMapping and Spring MVC HandlerMapping.**
4. Want to add a header for every request via Servlet filter mapping. What do you use? **Servlet Filter or FilterRegistrationBean.**
5. Want to run logic before/after a specific MVC controller handler. What do you use? **HandlerInterceptor registered via WebMvcConfigurer.**
6. Want to protect endpoints with authentication/authorization. What do you use? **Spring Security SecurityFilterChain**, not just an MVC interceptor.
7. Does a passing MockMvc test prove port/TLS works? **No.** It does not open an embedded server/network listener.
8. Want to test a real embedded server accepting HTTP. What do you use? **SpringBootTest with RANDOM_PORT and TestRestTemplate/WebTestClient.**
9. Can a WebFlux project reuse WebMvcConfigurer and jakarta.servlet.Filter? **No.** Use the appropriate WebFluxConfigurer and WebFilter.
10. Want to configure Tomcat's thread pool. Which layer does it belong to? **Server/container**, using server.tomcat.* or a Tomcat-specific factory customizer.
11. Want to change response JSON serialization. Which layer does it belong to? **MVC message conversion/Jackson**, not the connector.
12. Requests connect successfully but return 404. What should you check? **Context path, controller mapping, HandlerMapping, component scan, and proxy rewrites**, rather than starting by increasing port/threads.

## 13. Official References (Spring Boot 3.3)

- [Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.embedded-container): configuring embedded Servlet containers, server factories, and server customizers.
- [Spring MVC](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC auto-configuration and extending with WebMvcConfigurer.
- [Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): server.*, spring.mvc.*, and management properties.
- [WebServerFactoryCustomizer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html): extension point for customizing web server factories.
- [ConfigurableServletWebServerFactory API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/server/ConfigurableServletWebServerFactory.html): factory API for Servlet web servers.
- [Spring Framework — HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html): interceptors in Spring MVC handler execution.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): filters and integration with Servlet request processing.
- [Spring Boot — Testing Web Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): MockMvc, random port, and testing web applications.
- [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive web architecture, WebFilter, and WebFluxConfigurer.
