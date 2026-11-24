# Application Root Path, Servlet Mapping, and Endpoint URLs in Spring Boot

## Learning Objectives

This lesson explains how the URL of an HTTP request is parsed and routed to the right endpoint in a Spring Boot application, especially Spring MVC on a Servlet container. After this lesson, you will be able to:

- Distinguish scheme, host, port, URL path, query string, and fragment.
- Distinguish a Servlet application's context path, DispatcherServlet's servlet mapping, and controller mappings.
- Calculate the URL to reach an endpoint from server configuration and annotations.
- Understand the differences between server.servlet.context-path, spring.mvc.servlet.path, and spring.webflux.base-path.
- Identify the role of Actuator, reverse proxies, and API gateways in forming public URLs.
- Systematically investigate 404, 405, duplicated URL prefixes, and path mismatches during deployment.

## 1. What Parts Make Up an HTTP URL?

Example:

~~~text
https://api.example.com:8443/shop/gateway/orders/42?verbose=true
|----- scheme + host + port ----|----------- path -------|-- query --|
~~~

| Component | Example | Meaning |
|---|---|---|
| Scheme | HTTPS | Protocol from the client to the connection receiver; may differ from the backend protocol behind a proxy. |
| Host | api.example.com | Domain name or IP address used by the client. |
| Port | 8443 | Client-side port; may be omitted when using the protocol's default port. |
| Path | /shop/gateway/orders/42 | Path string used to route the HTTP request. |
| Query string | verbose=true | Parameters after the question mark, commonly read with @RequestParam. |
| Fragment | #details | Client-side part; browsers do not send fragments to the server in an HTTP request. |

The public scheme and hostname may be provided by a load balancer, ingress, or reverse proxy. The server.port property in Spring Boot is the port the application listens on, not necessarily the external port end users access.

An endpoint's URL is a network communication path. It is not synonymous with project directory paths, Java package names, controller filenames, or paths to JAR files.

## 2. URL Layers in Spring MVC

For a typical Servlet application, we can picture:

~~~text
URL sent by client
    |
    +-- scheme://host[:port]
    |
    +-- context path of the Servlet application
    |
    +-- DispatcherServlet mapping prefix (if configured)
    |
    +-- controller mapping + method mapping
    |
    +-- query string (if present)
~~~

For instance:

~~~text
http://localhost:9090/shop/gateway/api/orders/42
                      |---|-------|-------------|
                    context servlet    handler
                      path   prefix       path
~~~

This formula only illustrates layers of responsibility, not a naive string concatenation rule for every HTTP server. URL encoding, servlet mapping style, and proxy rewrites can alter the actual outcome.

### 2.1. Context Path: The Application's Root Path

In Spring Boot running on the Servlet stack, configure the context path with:

~~~properties
server.servlet.context-path=/shop
~~~

The context path identifies the web application inside the Servlet container. If a controller handles /api/orders/42 and uses the default DispatcherServlet, the URL becomes /shop/api/orders/42.

Important points:

- The context path applies at the Servlet application layer, before the container routes to a servlet.
- Do not repeat /shop in every @RequestMapping once the context path is set to /shop.
- By default a Spring Boot Servlet application runs at the root context, meaning no prefix such as /shop is added.
- This setting affects the Servlet application's URLs, including controllers and usually static resources.
- Having the root context does not guarantee a GET / request succeeds: a matching handler or resource must still exist.

Example configuration:

~~~properties
server.port=9090
server.servlet.context-path=/shop
~~~

Without a proxy or other configuration, clients connect directly to the application using host localhost, port 9090, and a path starting with /shop.

### 2.2. Servlet Mapping: Which Servlet Does the Container Choose?

Tomcat or the Servlet container receives an HTTP request and selects a servlet based on registered URL patterns. Spring MVC uses DispatcherServlet as its front controller: this servlet receives the request and delegates to handler mappings to find the matching controller method.

In a typical Spring MVC application configured by Spring Boot, DispatcherServlet uses the default servlet mapping /, which is sufficient for most REST APIs. If you have a special need to separate URL spaces among multiple servlets, you can set a prefix with:

~~~properties
spring.mvc.servlet.path=/gateway
~~~

When configured validly, requests may have to pass through /gateway before being handled by DispatcherServlet. If context path /shop is also set, the path portion before the controller will be /shop/gateway.

**Compatibility warning:** Spring Boot documentation states that a custom servlet path prefix may be incompatible with the default PathPatternParser strategy. For Spring Boot 3.x versions supporting AntPathMatcher, the common configuration when a servlet prefix is required is:

~~~properties
spring.mvc.servlet.path=/gateway
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Verify against your project's exact Spring Boot version before applying. If you merely want every API to have an /api prefix, often a controller @RequestMapping or a context path is all you need, without changing the DispatcherServlet mapping.

Some servlet URL pattern types:

| Pattern | Meaning |
|---|---|
| / | Default servlet mapping. |
| /gateway/* | Prefix mapping for URLs prefixed with gateway. |
| /status | Exact mapping for a single URL path. |
| *.jsp | Extension mapping by suffix. |

Those patterns are Servlet container rules. A custom servlet mapped to /legacy/* can serve its own URLs, and does not automatically become a prefix for Spring MVC controllers.

### 2.3. Controller Mapping: Spring MVC Finds the Handler

Controller mappings declare routes inside Spring MVC. Example:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    String findById(@PathVariable("id") long id) {
        return "order:" + id;
    }
}
~~~

In this example:

- Class-level @RequestMapping contributes /api/orders.
- Method-level @GetMapping contributes /{id} and restricts the HTTP method to GET.
- @PathVariable extracts id from the URL segment, not from the query string.
- The resulting handler mapping is GET /api/orders/{id}, before adding context and servlet prefixes.
- Calling the right path with the wrong method may return 405 Method Not Allowed instead of 404 Not Found.

Setting server.servlet.context-path=/shop and also putting @RequestMapping("/shop/api/orders") duplicates the prefix. A request might have to carry /shop/shop/api/orders/42 to reach the handler, even though that was not the intended URL design.

## 3. Runnable Spring Boot MVC Example

The example uses Java 17+ and Spring Boot with the Spring MVC starter. With Spring Boot 3.x, the commonly used starter is spring-boot-starter-web. In Spring Boot 4.x, spring-boot-starter-webmvc is the recommended starter name. Choose the artifact matching your major version and let Spring Boot manage dependency versions.

Suppose a Java project contains the following three files.

### File 1: PathsApplication.java

Path: src/main/java/com/example/paths/PathsApplication.java

~~~java
package com.example.paths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathsApplication.class, args);
    }
}
~~~

### File 2: OrderController.java

Path: src/main/java/com/example/paths/OrderController.java

~~~java
package com.example.paths;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public String findById(@PathVariable("id") long id) {
        return "order:" + id;
    }
}
~~~

### File 3: application.properties

Path: src/main/resources/application.properties

~~~properties
server.port=9090
server.servlet.context-path=/shop
~~~

Do not configure spring.mvc.servlet.path in the main example; DispatcherServlet uses the default mapping.

Run the application via the Maven Wrapper included in the project:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, if using Command Prompt or PowerShell, you can run mvnw.cmd spring-boot:run.

Send an HTTP request:

~~~bash
curl -sS http://localhost:9090/shop/api/orders/42
~~~

Exact returned body:

~~~text
order:42
~~~

The path is formed as follows:

~~~text
server.port                 -> 9090
server.servlet.context-path -> /shop
DispatcherServlet mapping   -> /
class @RequestMapping       -> /api/orders
method @GetMapping          -> /{id}
PathVariable id             -> 42

GET http://localhost:9090/shop/api/orders/42
~~~

When trying the following command:

~~~bash
curl -i http://localhost:9090/api/orders/42
~~~

the request lacks the /shop context path, so it will normally return 404. The exact error body depends on Spring Boot configuration, error handler content, and application version.

If you change server.servlet.context-path=/demo, the endpoint becomes /demo/api/orders/42; do not edit the controller annotations.

### Trying an Additional Servlet Path in a Compatible Configuration

If the MVC application uses a Spring Boot version where AntPathMatcher can be configured for a servlet prefix, for example Spring Boot 3.x:

~~~properties
server.port=9090
server.servlet.context-path=/shop
spring.mvc.servlet.path=/gateway
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

When started successfully with compatible settings, the URL is:

~~~text
GET http://localhost:9090/shop/gateway/api/orders/42
~~~

The body is still order:42. The /gateway part is the path to DispatcherServlet and is not repeated in the controller's @RequestMapping.

## 4. Path Fields Provided by the Servlet API

For the request:

~~~text
GET /shop/gateway/api/orders/42?verbose=true HTTP/1.1
~~~

Suppose the application has context path /shop and DispatcherServlet is registered with prefix mapping /gateway/*:

| API | Illustrative Value | Meaning |
|---|---|---|
| request.getRequestURI() | /shop/gateway/api/orders/42 | HTTP request path as seen by the Servlet container, without query. |
| request.getContextPath() | /shop | Prefix identifying the Servlet application. |
| request.getServletPath() | /gateway | Path portion tied to the servlet prefix mapping. |
| request.getPathInfo() | /api/orders/42 | Remaining portion after the servlet prefix in the case of prefix mapping. |
| request.getQueryString() | verbose=true | Raw query string, without the question mark. |

The values of servletPath and pathInfo depend on the servlet mapping type. With the default mapping /, servletPath usually reflects the path within the context and pathInfo is null; do not assume every request is split the same way as prefix mapping.

Spring MVC determines the lookup path itself to map to @RequestMapping and handles escaping/URL decoding according to framework mechanisms. Avoid calling getRequestURI() and manually slicing strings by context path length to select controllers; such logic easily breaks with servlet prefixes and URL-encoded characters.

## 5. How Do Context Path, Servlet Path, and Controller Mapping Differ?

Suppose a controller is mapped to GET /api/orders/42 and the application listens on port 9090:

| Configuration / Declaration | Typical Internal URL | Responsible Layer |
|---|---|---|
| All prefixes left at default | http://localhost:9090/api/orders/42 | MVC handler mapping. |
| Context path /shop | http://localhost:9090/shop/api/orders/42 | Servlet application context. |
| DispatcherServlet prefix /gateway, compatible matching | http://localhost:9090/gateway/api/orders/42 | Servlet mapping. |
| Context /shop + Servlet prefix /gateway | http://localhost:9090/shop/gateway/api/orders/42 | Two independent prefix layers. |
| Controller maps /shop/api/orders itself, default context | http://localhost:9090/shop/api/orders/42 | Controller mapping only. |

Two URLs that look identical can be produced by different configurations. When moving an application to another context, the context path model affects more servlets and resources in the application than merely changing @RequestMapping on a few controllers.

An operationally clean convention is to decide clearly who owns each prefix. For example, /shop is the application's context and /api is the REST controllers' prefix. Then set server.servlet.context-path=/shop and start controller mappings with /api; there is no need to add /shop again in the controllers.

## 6. Differences When Using Spring WebFlux

Spring WebFlux does not strictly depend on the Servlet API. If the application runs pure WebFlux with Reactor Netty, the right property to set a prefix for all web handlers is:

~~~properties
spring.webflux.base-path=/shop
~~~

With a handler mapped to /api/orders/42, the URL becomes /shop/api/orders/42.

Do not use server.servlet.context-path or spring.mvc.servlet.path to set prefixes for pure WebFlux. They belong to Servlet/MVC configuration. Setting those properties in a WebFlux project and expecting all routes to change can waste time investigating 404 errors.

If both MVC and WebFlux starters are present, Spring Boot usually prefers MVC under default configuration. Merely adding WebFlux to use WebClient does not mean the server is running WebFlux; verify the actual web application type and dependencies.

## 7. Actuator: Management Paths Are a Separate Group

Spring Boot Actuator provides management endpoints, such as health, usually under the default HTTP prefix /actuator. The prerequisite is that the application has added the Actuator dependency and the endpoint is exposed according to configuration policy.

When Actuator uses the same port as the Servlet application, its web base path is calculated relative to the context path. Example:

~~~properties
server.port=9090
server.servlet.context-path=/shop
management.endpoints.web.base-path=/manage
~~~

Typical health address:

~~~text
http://localhost:9090/shop/manage/health
~~~

If management.endpoints.web.base-path is unchanged, the default is usually /actuator, giving the URL /shop/actuator/health.

If using a separate management port:

~~~properties
management.server.port=9091
~~~

Actuator has its own management web context, and the base path of management endpoints is then computed relative to management.server.base-path. Do not mechanically prepend the main web server's context path /shop to URLs on port 9091.

Actuator paths also do not necessarily undergo a servlet prefix like /gateway as business controllers do; Spring Boot documentation defines the management endpoints' web base path relative to the context/management context. Check the exact version and actual mapping.

Do not expose all management endpoints publicly just to fix 404s. Diagnostic endpoints such as mappings must have access restricted in appropriate environments.

## 8. Public URLs with a Reverse Proxy and API Gateway

In real deployments, an application may listen on port 8080 inside a container, while clients access it over HTTPS on a dedicated domain.

Example:

~~~text
Public client                         API gateway                 Spring Boot
https://api.example.com/v1/orders/42 -> http://service:8080/orders/42 -> Controller /orders/{id}
                        prefix /v1    gateway strips prefix /v1
~~~

If the proxy already strips /v1 before forwarding to the backend, Spring Boot does not need to know /v1 as a context path. Conversely, if the proxy preserves /v1, the application or backend router must have a matching mapping.

Before determining the real URL, you need to know:

1. Does the proxy preserve the path or rewrite the path?
2. Does the proxy add or strip a prefix?
3. Does HTTPS terminate at the proxy or at the application?
4. How do the external host/port differ from the internal host/port?
5. Do redirects, static resources, Actuator, and Spring Security follow the same rules?

Spring Boot supports configuring forwarded-header handling:

~~~properties
server.forward-headers-strategy=framework
~~~

Relevant headers may include Forwarded, X-Forwarded-Proto, X-Forwarded-Host, and X-Forwarded-Prefix. Only trust headers normalized by a trusted proxy; clients can send forged headers if the network edge does not strip or overwrite them.

Also distinguish server.address=0.0.0.0 from the public URL. That value lets the server bind on appropriate network addresses, but does not create a DNS name or change the public HTTPS endpoint. In Docker/Kubernetes, port mappings and ingress may expose a different port from server.port.

## 9. 404, 405, and Duplicated URLs: How to Find the Cause

A practical checklist:

1. Verify the exact host, scheme, port, and application version running.
2. Identify the web stack: Spring MVC or Spring WebFlux.
3. For MVC, check whether server.servlet.context-path sets a prefix.
4. Check spring.mvc.servlet.path; if present, confirm DispatcherServlet mapping and a compatible matching strategy.
5. Combine class-level @RequestMapping and method-level @GetMapping/@PostMapping.
6. Check the HTTP method and path parameters; right path but wrong method can return 405.
7. Determine how the gateway keeps/strips/adds prefixes.
8. Check Spring Security matchers, static resource routes, and Actuator endpoints when relevant.
9. Use request logs, controller mapping logs, or protected mappings endpoints in test environments.

| Symptom | Common Cause | Resolution |
|---|---|---|
| /api/orders/42 returns 404 after setting context /shop | Missing context path in client URL | Call /shop/api/orders/42. |
| URL must contain /shop/shop | /shop was placed in both context path and @RequestMapping | Keep the prefix only at the designed layer. |
| Adding /gateway causes app mapping errors | Servlet prefix is incompatible with the version's PathPatternParser | Check matching strategy and matching version docs. |
| Internal endpoint works, public endpoint 404s | Proxy rewrites or keeps prefix differently than expected | Compare gateway access logs and request URI arriving at backend. |
| GET receives 405 | Handler only supports another HTTP method | Call with the right method or fix annotation. |
| /actuator/health does not exist | Actuator dependency missing, or base path or management port differs | Verify configuration and endpoint exposure status. |
| Redirect generates http://backend instead of https://domain | Forwarded headers/proxy info not synchronized | Configure trusted proxy and forwarded-header handling. |

A quick test against the app in Section 3:

~~~bash
curl -i http://localhost:9090/shop/api/orders/42
curl -i http://localhost:9090/api/orders/42
curl -i "http://localhost:9090/shop/api/orders/42?verbose=true"
~~~

The first request matches the endpoint and returns body order:42. The second request lacks /shop so it typically returns 404. The third request has the same URL path as the first: the query string verbose=true does not change the example's handler mapping.

When observing in development, you can log request.getRequestURI(), getContextPath(), and getServletPath(). Avoid writing tokens, cookies, or sensitive data to logs.

## 10. Self-Check Exercise

Given a Spring MVC application with:

~~~properties
server.port=9000
server.servlet.context-path=/catalog
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{isbn}")
    String find(@PathVariable("isbn") String isbn) {
        return isbn;
    }
}
~~~

Answer:

1. What is the direct URL to GET the book with ISBN 9780000000000?
2. Does adding query ?lang=vi change the handler mapping?
3. If you change the class mapping to /catalog/api/books while keeping context /catalog, what is the new URL?
4. If an additional servlet prefix /dispatcher is added with compatible configuration, what is the URL for the original example?
5. If building a pure WebFlux application, which property sets the /catalog base path?
6. Why is server.port=9000 not enough to determine the public URL through an API gateway?
7. With Actuator using the same port and default base path, what is the health URL usually?

### Answers

1. http://localhost:9000/catalog/api/books/9780000000000.
2. No. The query string is processed separately and can be read via @RequestParam if needed.
3. /catalog/catalog/api/books/9780000000000 because the prefix is concatenated twice at two layers.
4. http://localhost:9000/catalog/dispatcher/api/books/9780000000000.
5. spring.webflux.base-path=/catalog.
6. The gateway may change the scheme, host, port, and rewrite the path.
7. Usually http://localhost:9000/catalog/actuator/health, if Actuator has been added and the health endpoint is exposed.

## 11. Official References

- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC, DispatcherServlet, and path matching strategies.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): context path, servlet path, and WebFlux base path.
- [Spring Framework — Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html): Servlet path, context path, and handler lookup path.
- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): Actuator base path and management port.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): base path for WebFlux.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): Spring MVC starters by version.