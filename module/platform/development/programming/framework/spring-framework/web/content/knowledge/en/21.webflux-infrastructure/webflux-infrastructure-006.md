# Spring WebFlux — @EnableWebFlux, WebFluxConfigurer, and Infrastructure Configuration

## 1. Learning objectives

When building reactive APIs with Spring WebFlux, `@RestController` controllers and functional routes are only the visible surface. Underneath sits an infrastructure comprising handler mappings, handler adapters, result handlers, HTTP message readers/writers, converters, CORS, static resource handling, exception handling, and bridges to the web server.

Spring Framework provides `@EnableWebFlux` and the `WebFluxConfigurer` interface to enable/customize that infrastructure. **Spring Boot has its own auto-configuration**, so how you use these two pieces in a Boot application differs from writing a plain Spring Framework application.

**Principle to remember from the start:**

- With **Spring Boot WebFlux**: by default use only `spring-boot-starter-webflux` and properties. When adding configuration, write `@Configuration implements WebFluxConfigurer` **without adding `@EnableWebFlux`**, to keep Boot's conveniences.
- With **manual Spring Framework configuration** or when you want full responsibility for managing WebFlux infrastructure: use `@EnableWebFlux`. In Boot, this shifts control and causes many parts of Boot's WebFlux auto-configuration to step back; you must ensure all required behaviors yourself.
- When you need to replace infrastructure beans deeper than the `WebFluxConfigurer` API: study `DelegatingWebFluxConfiguration`/`WebFluxConfigurationSupport` and Boot-specific customization hooks, using them only with clear justification.

This article helps you:

1. Diagram the WebFlux request processing flow accurately and distinguish it from `DispatcherServlet`/Spring MVC.
2. Understand the roles and levels of intervention of `@EnableWebFlux`, `WebFluxConfigurer`, and Spring Boot auto-configuration.
3. Configure formatters/converters, CORS, codecs, static resources, path matching, content negotiation, view resolvers, and blocking execution.
4. Distinguish which settings belong to WebFlux infrastructure versus Reactor Netty, WebClient, Spring Security, or Spring Boot.
5. Avoid typical mistakes such as enabling `@EnableWebFlux` and losing static mappings, custom codecs accidentally wiping JSON defaults, opening wildcard CORS with credentials, or blocking the Netty event loop.
6. Build an independently reproducible **Java 17 / Spring Boot 3.5.0 / Maven** example, along with `WebTestClient` verifying APIs, CORS, and static resources.
7. Know the criteria for deciding when properties suffice, when to implement `WebFluxConfigurer`, and when customizers/advanced config are needed.

**Scope:** Spring Framework 6.2, Spring Boot 3.5, Reactor on a WebFlux reactive application. Never use Servlet MVC's `WebMvcConfigurer`, `@EnableWebMvc`, `DispatcherServlet`, or `HandlerInterceptor` as substitutes for WebFlux infrastructure.

## 2. Which layer does Spring WebFlux operate at?

### 2.1. Request flow

Simplified model:

~~~text
HTTP Client
   |
   v
Server: Reactor Netty / supported runtime
   |
   v
HttpHandler
   |
   v
WebHttpHandlerBuilder-built processing chain
   |-- WebFilter(s)
   |-- WebExceptionHandler(s)
   |-- WebSession / locale-related handling
   |
   v
DispatcherHandler
   |
   +-- HandlerMapping: finds handler
   |
   +-- HandlerAdapter: invokes handler
   |
   +-- HandlerResultHandler: writes result
   |       |
   |       +-- HttpMessageWriter -> JSON/text/streaming
   |       +-- View rendering
   |
   v
Reactive HTTP response (Publisher/Mono<Void>)
~~~

Key class names:

| Component | Role |
| --- | --- |
| `HttpHandler` | Low-level contract between web server runtime and framework |
| `HttpWebHandlerAdapter` | Adapts HTTP request/response into the WebHandler chain |
| `WebFilter` | Reactive filter before/after web handling (not a Servlet Filter) |
| `WebExceptionHandler` | Handles errors inside the reactive WebHandler chain |
| `DispatcherHandler` | Central dispatcher of Spring WebFlux |
| `HandlerMapping` | Selects controller, functional route, or resource handler |
| `HandlerAdapter` | Executes the matching handler |
| `HandlerResultHandler` | Renders handler results; includes body writers and view handlers |
| `ServerCodecConfigurer` | Configures HTTP readers/writers |
| `ConversionService` | Converts strings/numbers/dates/values for binding |
| `RequestedContentTypeResolver` | Selects response media type based on request/config |
| `ResourceWebHandler` | Serves static resources |

**Difference from Spring MVC:** WebFlux uses `DispatcherHandler`, not `DispatcherServlet`. `WebFilter` processes reactive requests rather than relying on a Servlet FilterChain. In WebFlux, blocking operations on the event loop degrade throughput even if the controller returns `Mono`.

### 2.2. Annotated controllers and functional endpoints both belong to WebFlux

WebFlux supports two programming styles:

- Annotated: `@RestController`, `@GetMapping`, `@RequestBody Mono<T>`, `Flux<T>`.
- Functional: `RouterFunction<ServerResponse>`, `HandlerFunction<ServerResponse>`.

WebFlux infrastructure settings can affect annotated handlers, functional endpoints, static resources, or a subset depending on the hook. For instance, a path prefix via `PathMatchConfigurer.addPathPrefix` primarily targets annotated controller mappings; do not automatically assume it modifies every `RouterFunction` path.

### 2.3. Reactive does not mean non-blocking magic

A controller returning `Mono.fromCallable(() -> jdbcRepository.findAll())` still invokes synchronous JDBC inside. Without proper offloading, it can block the event loop. WebFlux enables non-blocking adapters (R2DBC, reactive WebClient), yet it does not automatically make every blocking SDK/JPA/JDBC call reactive.

## 3. What does @EnableWebFlux actually do?

When using pure Spring Framework Java config:

~~~java
@Configuration
@EnableWebFlux
public class ReactiveWebConfiguration {
}
~~~

The `@EnableWebFlux` annotation imports `DelegatingWebFluxConfiguration`. It registers WebFlux infrastructure beans, discovers beans implementing `WebFluxConfigurer`, and applies their customizations.

Key points:

- Activates configuration needed for annotated controllers and related WebFlux components.
- Registers handler mappings/adapters/result handlers and appropriate defaults based on classpath dependencies.
- Allows `WebFluxConfigurer` beans to participate in customization.
- Does not automatically start a Reactor Netty server or provide all Boot features. Web server startup, management, config binding, and operations belong to the runtime/Boot layer when used.

### 3.1. Why doesn't Boot normally need @EnableWebFlux?

Spring Boot detects a reactive web application when `spring-boot-starter-webflux` is present (and MVC starter does not take precedence), and automatically configures WebFlux with:

- HTTP codecs, Jackson, and Boot `CodecCustomizer`s.
- Static resource locations, mappings, and welcome page.
- Default error handling.
- Properties for formatters, static assets, reactive paths, and various infrastructure integrations.
- Server/runtime management wired by Boot.

If you want to add CORS, converters, path matching, or a codec cap, you do not need to take over configuration of the entire system.

**Approach recommended by Spring Boot documentation:**

~~~java
@Configuration
class MyWebFluxConfiguration implements WebFluxConfigurer {
    // override the methods needed
    // DO NOT add @EnableWebFlux
}
~~~

This is a partial illustrative class; the complete runnable example is in section 12.

### 3.2. What happens when you add @EnableWebFlux in Boot?

In a Boot app, `@EnableWebFlux` signals that you want to **take complete control** of WebFlux configuration. Boot's WebFlux auto-configuration backs off when the infrastructure is user-declared (it stops applying default customizations along the same path).

Observable consequences:

- Boot's codec/mapping/static-resource customizations no longer apply automatically as before.
- Boot WebFlux properties and auto-configuration may no longer govern the corresponding infrastructure as before; you must verify manually.
- A static `index.html` that previously worked may lose its mapping/welcome behavior unless resource handlers are re-registered.
- Integration with Jackson, view resolution, exception handling, or argument resolvers may differ; re-test everything.
- Spring Security, Reactor Netty, and Actuator live in other related configurations: do not claim that enabling `@EnableWebFlux` wipes out all of Boot. The primary impact is on **WebFlux framework auto-configuration** and its customizations.

`@EnableWebFlux` is not a "wrong" annotation. It fits when the architecture requires full control and the team accepts maintaining/reconfiguring that infrastructure.

### 3.3. Three-tier decision table

| Goal | Preferred approach | Control level |
| --- | --- | --- |
| Typical WebFlux API | Starter + Boot properties | Keeps auto-config nearly intact |
| Add CORS/Converter/resources/codec limits/path rules | `@Configuration implements WebFluxConfigurer`, **no @EnableWebFlux** | Canonical API customization |
| Boot-compatible codec config across layers | `CodecCustomizer` Bean or Boot properties | Augments Boot infrastructure |
| Customize the Boot-built HttpHandler | `WebHttpHandlerBuilderCustomizer` | Specialized Boot-specific hook |
| Heavily replace framework WebFlux infrastructure | `@EnableWebFlux`, custom config | Own responsibility for defaults |
| Overriding bean declarations at framework level | Extend `DelegatingWebFluxConfiguration` or study `WebFluxConfigurationSupport` | Advanced, requires compatibility testing |

### 3.4. How does Spring Boot choose MVC vs WebFlux?

If an application has both:

~~~xml
<artifactId>spring-boot-starter-web</artifactId>
<artifactId>spring-boot-starter-webflux</artifactId>
~~~

Spring Boot normally selects **Spring MVC** as the web application type. This is useful when an MVC app only wants reactive `WebClient`. However, if a project expects `DispatcherHandler`, `WebFilter`, and a reactive server, having both starters can produce the wrong runtime.

For a pure WebFlux demo, **include only `spring-boot-starter-webflux`**, without `spring-boot-starter-web`. If there is a hard requirement to keep both, you can force the reactive application type via Boot API/config, yet you must audit all auto-configuration, libraries, and tests. Avoid forcing it just to "make an error go away".

## 4. WebFluxConfigurer: the infrastructure customization interface

Import:

~~~java
import org.springframework.web.reactive.config.WebFluxConfigurer;
~~~

A class can implement:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        // Configure route-specific CORS...
    }
}
~~~

Interface methods have default implementations; override only what you need. You can declare **multiple WebFluxConfigurer beans** and the framework combines them. However, registrations across modules can interact, overlap paths, or conflict; in large projects, govern ownership and test effective order/outcomes.

### 4.1. Key extension points

| Method | Purpose | When to use |
| --- | --- | --- |
| `addFormatters(FormatterRegistry)` | Register converters/formatters for argument/data binding | Custom IDs, date-time, locale |
| `addCorsMappings(CorsRegistry)` | CORS by URL patterns | Cross-origin browser frontend |
| `configurePathMatching(PathMatchConfigurer)` | Path matching, prefixes for annotated controllers | Selective API prefixing |
| `configureHttpMessageCodecs(ServerCodecConfigurer)` | Readers/writers, memory cap, codecs | JSON/body/streaming |
| `configureContentTypeResolver(RequestedContentTypeResolverBuilder)` | Media type negotiation | Content negotiation policy |
| `addResourceHandlers(ResourceHandlerRegistry)` | Static asset routing and cache policy | CSS/JS/images/docs |
| `configureViewResolvers(ViewResolverRegistry)` | HTML/template rendering | SSR with FreeMarker/Thymeleaf |
| `configureArgumentResolvers(ArgumentResolverConfigurer)` | Add resolvers for custom controller args | TenantContext/auth context |
| `getValidator()` | Supply a custom Validator when needed | Validation integration |
| `getMessageCodesResolver()` | Customize validation error code resolution | Form/validation messages |
| `configureBlockingExecution(BlockingExecutionConfigurer)` | Choose executor and predicate for blocking controller methods | Legacy blocking handlers |
| `getWebSocketService()` | Customize WebSocket handshake handling service | Specialized WebSocket infra |

**Version note:** This table targets Spring Framework 6.2. APIs added in newer versions do not automatically exist in Boot 3.5/Framework 6.2. When copying from "current" Spring Framework 7 docs, verify API versions.

### 4.2. addFormatters: custom conversion

Suppose an HTTP route uses:

~~~text
GET /api/books/42
~~~

You want `@PathVariable BookId` parsed into a Java record:

~~~java
record BookId(long value) {}
~~~

Configuration:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, BookId.class,
            text -> new BookId(Long.parseLong(text)));
}
~~~

Requires `org.springframework.format.FormatterRegistry`. When the controller declares:

~~~java
@GetMapping("/books/{id}")
Mono<BookDto> get(@PathVariable BookId id) {
    return Mono.just(new BookDto(id.value(), "Book"));
}
~~~

This is a fragment across config/controller. When `id` is an unparseable string, binding can emit a 400 error per framework exception handling; do not map parse errors to 500 or accept overflow blindly. In practice, use dedicated converters, validate ID ranges, and test invalid values.

Do not write custom parsers for `LocalDate`/`Instant` when Java time formatters or `@DateTimeFormat(iso=...)` already fit. For form fields, Locale-based formatting can differ from ISO JSON serialization — they are two distinct layers.

### 4.3. addCorsMappings: browser cross-origin permissions

Example:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com",
                    "http://localhost:5173")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization")
            .exposedHeaders("X-Request-ID")
            .allowCredentials(true)
            .maxAge(1800);
}
~~~

A credentialed CORS response needs `Access-Control-Allow-Origin` matching **a specific origin**; you cannot combine `allowedOrigins("*")` with `allowCredentials(true)`. Spring Framework provides `allowedOriginPatterns`, yet an overly broad pattern like `"*"` can open credentialed CORS to untrusted origins. Allowing an origin ≠ authorizing a user: the API still needs authentication, authorization, and CSRF/cookie security.

**Important:** CORS does not handle server-to-server authorization. `curl` does not enforce browser same-origin policy. With reactive Spring Security, design WebFilterChain order and Security CORS integration so preflight OPTIONS do not require a session/cookie; never copy Servlet `HttpSecurity` config into WebFlux (use `ServerHttpSecurity`).

### 4.4. configurePathMatching: adding prefixes selectively

Example:

~~~java
@Override
public void configurePathMatching(PathMatchConfigurer configurer) {
    configurer.addPathPrefix(
            "/api",
            HandlerTypePredicate.forAnnotation(RestController.class));
}
~~~

Import `org.springframework.web.method.HandlerTypePredicate` and `org.springframework.web.bind.annotation.RestController`.

Controller declares:

~~~java
@RestController
class BookController {
    @GetMapping("/books/{id}")
    Mono<BookDto> find(@PathVariable long id) {
        return Mono.just(new BookDto(id, "Book"));
    }
}
~~~

The effective route becomes:

~~~text
GET /api/books/42
~~~

**Do not add `/api` twice**: if the controller already declares `@RequestMapping("/api")` and the configurer also adds prefix `/api`, the route can become `/api/api/...`. Pick one owner for the prefix.

`addPathPrefix` applies by **controller type** predicate and does not automatically transform router functions or static resources. Spring WebFlux uses parsed `RequestPath`/`PathPatternParser` semantics; do not bring MVC habits like `.json` suffix matching, `AntPathMatcher`, and legacy URL-decoding flags into WebFlux.

### 4.5. configureHttpMessageCodecs: memory limits and readers/writers

Codecs convert request bodies into objects and objects into bodies. In WebFlux, reading/writing flows through:

~~~text
HTTP request Flux<DataBuffer>
   -> HttpMessageReader / Decoder
   -> DTO/Mono<T>

DTO/Flux<T>
   -> Encoder / HttpMessageWriter
   -> HTTP response body
~~~

To set a buffering cap for most default codecs:

~~~java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(256 * 1024);
}
~~~

Import `org.springframework.http.codec.ServerCodecConfigurer`.

This threshold limits bytes aggregated in memory by certain codec operations; **it is not** an overall server RAM limit, request concurrency limit, Netty receive buffer size, or replacement for upload quotas. Oversized payloads can trigger `DataBufferLimitException` during buffering/aggregation. Verify exception/status/error contracts and tests rather than assuming every 300KB request produces HTTP 413 across every codec path.

**Do not call**:

~~~java
configurer.registerDefaults(false);
~~~

just to "raise limits" or "optimize performance": this call disables default readers/writers, easily breaking JSON requests/responses due to missing codecs. Only replace all defaults when you understand and manually register all required codecs.

### 4.6. Boot CodecCustomizer and properties

Spring Boot 3.5 also supports `CodecCustomizer` and properties under `spring.http.codecs.*`, alongside Jackson integration. When an equivalent Boot property exists, prefer the property to minimize code and prevent multiple layers from setting values simultaneously.

Fragment illustrating a customizer:

~~~java
@Bean
CodecCustomizer codecLimits() {
    return configurer ->
            configurer.defaultCodecs().maxInMemorySize(256 * 1024);
}
~~~

In Spring Boot 3.5, `CodecCustomizer` is provided in the package matching that Boot version; verify Javadoc imports for your exact dependency version rather than copying from Boot 4.0/4.1 where some module packages changed. If the project already configures the same settings via `WebFluxConfigurer.configureHttpMessageCodecs`, pick **one owner** to keep precedence clear.

### 4.7. configureContentTypeResolver: content negotiation

In annotated controllers, the framework uses the requested content type resolver from the HTTP request. Normally rely on the `Accept` header and `produces/consumes`:

~~~http
GET /api/books/42
Accept: application/json
~~~

Controller:

~~~java
@GetMapping(path = "/books/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
Mono<BookDto> get(@PathVariable long id) { ... }
~~~

In config:

~~~java
@Override
public void configureContentTypeResolver(
        RequestedContentTypeResolverBuilder builder) {
    // Only add policies that are genuinely designed.
}
~~~

This is a fragment (requires import `org.springframework.web.reactive.accept.RequestedContentTypeResolverBuilder`), not a standalone runnable example. Do not rush to enable path-extension negotiation (`.json`/`.xml`) when `Accept` works, as it introduces URL formatting ambiguity and caching risks. Verify 406 Not Acceptable/415 Unsupported Media Type in API tests when customizing.

### 4.8. addResourceHandlers: static assets with caching

Example:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/guide/**")
            .addResourceLocations("classpath:/guide-assets/")
            .setCacheControl(CacheControl
                    .maxAge(Duration.ofMinutes(5))
                    .cachePublic());
}
~~~

Required imports: `java.time.Duration`, `org.springframework.http.CacheControl`, `org.springframework.web.reactive.config.ResourceHandlerRegistry`.

Suppose the file exists:

~~~text
src/main/resources/guide-assets/intro.txt
~~~

The HTTP route:

~~~text
GET /guide/intro.txt
~~~

is handled by `ResourceWebHandler` without needing a controller.

Serve only chosen classpath/static locations; never map the filesystem root (`file:/`) or an upload directory holding private PII. For versioned JS/CSS URLs, use `ResourceResolver`/`VersionResourceResolver` with longer caching; caching unversioned filenames for a year can leave users seeing stale assets after deploys.

### 4.9. configureViewResolvers and template rendering

WebFlux does not serve only JSON. With Thymeleaf/FreeMarker/Mustache or HTML responses, view resolvers can be configured:

~~~java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    // Add a view resolver when truly needed, or use Boot auto-config.
}
~~~

This is a fragment without registering a specific resolver. With Spring Boot, adding the appropriate template starter and placing HTML templates in `src/main/resources/templates` is usually enough. Do not write a manual resolver if defaults suffice.

### 4.10. configureArgumentResolvers: custom method arguments

A multi-tenant application might want:

~~~java
@GetMapping("/me")
Mono<ProfileDto> me(CurrentTenant tenant) { ... }
~~~

To have WebFlux resolve `CurrentTenant` automatically, register a custom `HandlerMethodArgumentResolver` via:

~~~java
@Override
public void configureArgumentResolvers(
        ArgumentResolverConfigurer configurer) {
    configurer.addCustomResolver(new TenantArgumentResolver());
}
~~~

This fragment requires implementing WebFlux's `TenantArgumentResolver`, not Servlet `HandlerMethodArgumentResolver` from the MVC package. The resolver must be non-blocking and must never trust an arbitrary tenant request header without authentication/authorization. Use `ReactiveSecurityContextHolder` or trusted services/lookups.

### 4.11. Validator and validation

WebFlux can validate input models via Jakarta Bean Validation when a compatible provider is on the classpath. `WebFluxConfigurer#getValidator()` can supply a custom Validator when needed, yet in Boot adding the validation starter dependency and annotations usually suffices.

Example:

~~~java
record CreateBookRequest(
        @NotBlank String title
) {}
~~~

Controller:

~~~java
@PostMapping("/books")
Mono<BookDto> create(@Valid @RequestBody Mono<CreateBookRequest> input) {
    return input.map(this::save);
}
~~~

This is an illustrative fragment: method `save`, imports, and a validation provider must exist. With reactive arguments, validation mechanics and exception types depend on signature declarations; check `WebExchangeBindException`/validation exception semantics before mapping statuses/error payloads.

**Do not replace Validator** just to use ordinary `@NotBlank`. Ensure validation error messages never echo rejected secret values back to clients.

### 4.12. configureBlockingExecution: bridge for blocking controller methods

Spring Framework 6.2 provides:

~~~java
@Override
public void configureBlockingExecution(
        BlockingExecutionConfigurer configurer) {
    configurer.setExecutor(myAsyncTaskExecutor);
}
~~~

Fragment: `myAsyncTaskExecutor` is a managed `AsyncTaskExecutor`. The framework lets you configure the executor and a predicate identifying controller methods considered blocking (defaulting to reactive adapter registry and return types).

Important points:

- **Does not mean every blocking call inside `Mono.map` is automatically offloaded.**
- When calling blocking JDBC/SDKs inside a reactor chain, consider `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` or migrating to a non-blocking library.
- Any blocking execution executor must have bounds, thread names, metrics, shutdown policies, and timeouts; never spawn unbounded threads per request.
- `WebFluxConfigurer.configureBlockingExecution` configures handler invocation for recognized blocking methods, **not a replacement for Reactor scheduler strategy**.

### 4.13. WebSocket service

`WebFluxConfigurer#getWebSocketService()` supports customizing the WebSocket handshake service in WebFlux. Do not try to configure WebSocket security via CORS mappings alone. WebSocket requires its own Origin validation, authentication, and message-level authorization; reactive Spring Security and gateway/proxy rules matter too.

## 5. WebFluxConfigurer does not manage everything

An architectural mistake is cramming every WebFlux/Netty setting into WebFluxConfigurer even when it belongs to another layer.

| Need | Appropriate layer |
| --- | --- |
| Controller routing / converters / CORS | `WebFluxConfigurer` |
| HTTP body codecs | `WebFluxConfigurer.configureHttpMessageCodecs`, `CodecCustomizer`, Boot properties |
| Client-side WebClient timeouts | `WebClient.Builder`, Reactor Netty HttpClient, connector |
| Server port/TLS/compression | Boot server properties, `NettyReactiveWebServerFactory`/customizer |
| Authentication/authorization | Spring Security `SecurityWebFilterChain` |
| Cross-cutting request filters | `WebFilter` |
| Correlation/tracing/logging | Observability/Micrometer, Reactor Context/WebFilter |
| Business caching | Service/repository cache, HTTP headers/cache rules |
| Functional routes | `RouterFunction` bean, RouterFunctions DSL |
| Global errors | `@RestControllerAdvice`, `ErrorWebExceptionHandler` |
| Backpressure and scheduling | Reactor operators/Schedulers, source design |
| Reactive DB transactions | R2DBC/reactive transaction manager |
| Proxy forwarding | Forwarded header transformer/trusted proxy + Boot config |

**Configure at the right layer.** For instance, WebFluxConfigurer CORS does not grant auth, a Netty timeout is not equivalent to Mono.timeout for the whole pipeline, and Reactor Context is not Servlet ThreadLocal.

## 6. Infrastructure configuration structure and processing order

### 6.1. Multiple WebFluxConfigurer beans

The framework can accept multiple `WebFluxConfigurer` beans. Example:

~~~java
@Configuration
class CorsWebConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com");
    }
}

@Configuration
class CodecWebConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

These two snippets are fragments with corresponding imports. Even though the framework aggregates customizers, watch out for conflicts:

- Confusing multiple CORS definitions on the same path.
- One bean setting a 256KB limit while another sets 1MB; final value may depend on registration order.
- Two pathPrefix rules causing unexpected or conflicting routes.
- A custom codec replacing default readers/writers relied upon by another module.
- Multiple overlapping handler mappings/predicates making routes hard to locate.

For security-sensitive configuration, it is best to have **one controlled owner**, consolidate policies clearly, and write regression tests.

### 6.2. @Order is not the cure for every conflict

Spring supports ordering on certain config beans and handler/filter chains, yet adding `@Order(0)` alone does not clarify semantics when multiple customizers mutate shared config. What matters is inspecting the final HandlerMapping/codec/CORS policy and actual HTTP behavior rather than guessing "last config wins".

### 6.3. Request mapping and ResourceHandlerMapping

The `HandlerMapping`s registered by WebFlux infrastructure are ordered to select annotated controllers, functional routes, resource handling, and views/welcome pages. Resource handlers usually sit as a fallback so they do not shadow API routes. However, a broad `/**` mapping or custom RouterFunction can cause surprises if ordering is unchecked.

Do not register a catch-all `RouterFunction` just to add metrics, starving static/error handlers. Cross-cutting concerns belong in `WebFilter`/the observation layer.

## 7. Common Spring Boot properties

Some Boot 3.5 settings:

~~~properties
# Server:
server.port=8080

# Static assets:
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/

# Formatters (as needed):
spring.webflux.format.date=iso
spring.webflux.format.time=iso
spring.webflux.format.date-time=iso
~~~

These are **illustrative properties**, not the properties file used in the section 12 demo. Setting `spring.webflux.static-path-pattern=/assets/**` moves default static resources under `/assets/**` instead of `/**`. Setting `spring.web.resources.static-locations` replaces the default locations list; verify welcome pages and file locations.

**Note:** The `iso` value for Spring Boot format properties should be verified against Boot 3.5 configuration binding/format settings for your version; for critical APIs, use an explicit `DateTimeFormatterRegistrar` or test input parsing. Never use `spring.mvc.*` to configure reactive WebFlux routes.

### 7.1. Codec configuration properties

Spring Boot 3.5 documentation covers `spring.http.codecs.*`, `CodecCustomizer`s, and related Jackson config. In projects upgraded from Boot 2.x/3.x, older property keys may linger; check the **configuration metadata of your exact Boot version** instead of guessing which value takes effect.

If an aggregation limit is needed in the demo, the Java API in section 12 ensures configuration applies via `WebFluxConfigurer` regardless of property key/version aliases.

### 7.2. Global WebFlux base path vs controller prefix

Boot can offer an application base path configuration separate from annotated controller prefixes. Configuring a base path at the server/framework layer can also affect other mappings like static assets/functional routes. Meanwhile:

~~~java
configurer.addPathPrefix(
    "/api",
    HandlerTypePredicate.forAnnotation(RestController.class));
~~~

targets only controller types matching the predicate. Never use **both** for the same goal and end up with `/api/api/...`. Clearly document who owns the public mount prefix: reverse proxy, Boot base path, or controller mapping.

## 8. CORS + Security in WebFlux

CORS operates via browser protocol: Origin, preflight OPTIONS, and response headers. `WebFluxConfigurer#addCorsMappings` normally supplies policy to WebFlux HandlerMappings; when adding reactive Spring Security, ensure preflight is not rejected prematurely.

### 8.1. Specific origin and credentials

Example safe-ish config for a trusted SPA:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type", "Authorization")
        .allowCredentials(true);
~~~

**Keep in mind:** with cookie session credentials, CORS permits an origin to read responses when the user holds valid credentials. It **does not protect against CSRF**. You still need SameSite/Secure/HttpOnly cookies, server auth/authz, and CSRF policies. Never use `allowedOriginPatterns("*")` to "work around" the wildcard+credentials error.

### 8.2. Reactive security differs from Servlet security

In WebFlux, basic security config uses `ServerHttpSecurity` and `SecurityWebFilterChain`, not Servlet's `HttpSecurity` and `SecurityFilterChain`.

Fragment:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .cors(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/**").authenticated()
                    .anyExchange().permitAll())
            .build();
}
~~~

This fragment is **not standalone runnable**; it needs `spring-boot-starter-security`, an auth provider, CSRF policy, and `ServerHttpSecurity`/`SecurityWebFilterChain`/`Customizer` imports. Do not add this fragment to the section 12 demo without designing login, as starter-security will block endpoints differently than expected.

### 8.3. Preflight carries no cookie auth

Browser OPTIONS preflight does not carry actual request credentials in the normal way, so requiring a session on all OPTIONS before CORS handling can return 401/403. Let reactive CORS handling run in the proper order with security rather than "fixing" it by disabling authorization across the whole API.

### 8.4. Vary, exposed headers, and HTTP caching

If the server returns different ACAO values per Origin, `Vary: Origin` is needed so shared caches do not serve a response to the wrong origin. When the frontend needs to read `X-Request-ID` outside the response header safelist, use `exposedHeaders("X-Request-ID")`. Never mistake header exposure for authentication permission.

## 9. Codecs, streaming, and memory safety

### 9.1. What is the purpose of maxInMemorySize?

WebFlux can read JSON/XML/aggregated text bodies using codecs. Without limits, many large concurrent requests can exhaust direct/heap memory. Configuring:

~~~java
configurer.defaultCodecs().maxInMemorySize(256 * 1024);
~~~

prevents certain operations from buffering payloads beyond the threshold. It does not mean the server **cannot stream a 1GB file**: when streaming keeps data in chunks without buffering the entire payload, different rules apply. Uploads/files/deep JSON require their own limits:

- Reverse proxy body size.
- Netty/body decoder limits.
- Memory aggregation caps.
- Business validation/JSON nesting depth.
- Concurrency and rate limits.
- Per-user quotas and multipart configuration.

### 9.2. Pooled DataBuffer ownership

If you customize `HttpMessageReader`/`HttpMessageWriter` or work directly with `Flux<DataBuffer>`, some DataBuffers wrap pooled reference-counted Netty buffers. Release only when the application owns them, using `DataBufferUtils.release(...)` and appropriate discard policies. **Never double-release** buffers the framework still needs or releases itself.

Do not customize entire codecs just to rename one JSON property. Use Jackson annotations, Boot `spring.jackson.*`, or Jackson configuration where appropriate.

### 9.3. SSE and Flux<DataBuffer>

WebFlux supports streaming `Flux<ServerSentEvent<T>>` responses and raw binary streams. `ServerCodecConfigurer` affects writers/encoders for certain media types. When customizing codecs or message readers, test:

- `application/json` 200/400/415/406.
- `text/event-stream` streaming without unbounded buffering.
- Error handling before and after response commit.
- Cancellation and pooled DataBuffer release.
- Slow clients/backpressure and proxy buffering.

A codec override may work for small GET JSON while breaking SSE or multipart; test diverse payloads.

## 10. Spring WebFlux static assets

### 10.1. Defaults in Boot

Spring Boot WebFlux normally serves static files from classpath locations:

~~~text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
~~~

For example, placing:

~~~text
src/main/resources/static/index.html
src/main/resources/static/app.js
~~~

is the simplest way to serve a welcome page/static assets when auto-config is intact and routes do not conflict.

### 10.2. Custom resource handler

An additional custom handler:

~~~java
registry.addResourceHandler("/guide/**")
        .addResourceLocations("classpath:/guide-assets/")
        .setCacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePublic());
~~~

Just create a file at `src/main/resources/guide-assets/intro.txt` with no controller needed. For caching, distinguish:

- Versioned immutable JS/CSS: public long max-age.
- Mutable unversioned docs: short max-age/no-cache + validators.
- Private files: **never put in a public static handler**; serve via an authenticated controller/service with authorization policies.

### 10.3. Security and path traversal

Framework resource handling includes path normalization and location protections, yet never expose `file:/` to the whole filesystem or an upload directory holding private user documents. Never rely on file extensions or CORS to protect sensitive files.

### 10.4. Static resources after @EnableWebFlux

If adding `@EnableWebFlux` to "enable WebFlux" in Boot causes static `/index.html` to start returning 404, the reason may be that Boot's auto-configured static mappings/welcome page no longer apply. Return to Boot defaults or declare desired resource handlers explicitly. **Do not "fix" it by adding a GET / controller** merely to restore static auto-configuration.

## 11. Advanced configuration and WebHttpHandlerBuilderCustomizer

### 11.1. When WebFluxConfigurer is not enough

`WebFluxConfigurer` enables registry-based configuration without knowing individual infrastructure beans. When deeper overrides are required:

- How HandlerMappings or HandlerAdapters are created/customized.
- Ordering of WebExceptionHandlers or the WebFilter chain.
- Customizing HttpHandler building logic.
- Custom framework object registration and behavior beyond interface extension points.

Spring Framework allows deeper control via `DelegatingWebFluxConfiguration` or `WebFluxConfigurationSupport`. However, **this is not the default approach** in Boot, as it alters baseline auto-config and increases maintenance cost.

### 11.2. WebHttpHandlerBuilderCustomizer in Boot

Spring Boot WebFlux documentation provides `WebHttpHandlerBuilderCustomizer` when you need to customize the auto-configured `HttpHandler`. This is a Boot-specific hook, distinct from WebFluxConfigurer. Review the exact API and filter/error handler ordering before intervening.

Do not build a separate `HttpHandler` or swap the Netty adapter in production just to log a header; use WebFilter/observability first.

### 11.3. WebFilter, WebExceptionHandler

- `WebFilter` is a reactive cross-cutting filter suitable for headers/correlation/context and request policies.
- `WebExceptionHandler` is a low-level error handler.
- `@RestControllerAdvice` handles controller errors cleanly, closer to the API contract.

Never handle exceptions via fire-and-forget subscribe inside a filter; return a Publisher so the framework manages cancellation and backpressure. Once the HTTP response is committed, handlers cannot alter already-sent status/headers.

### 11.4. Do not override framework internals arbitrarily

WebFlux infrastructure evolves across Spring versions. If overriding beans from `DelegatingWebFluxConfiguration` with custom subclasses, verify:

- Bean names/types and conditional auto-config.
- Ordering of handler mappings/result handlers.
- Codec availability (JSON, SSE, multipart).
- Reactive Security integration.
- Static resources, CORS, views.
- Error handling, observability.
- Upgrade path from Framework 6.2 to 7.x.

Do this only when regression tests cover all affected layers and the team accepts the maintenance cost.

## 12. Runnable Java 17 / Spring Boot 3.5.0 project

The app demonstrates multiple extension points in **a single WebFluxConfigurer without @EnableWebFlux**:

- `configurePathMatching` prefixes annotated REST controllers with `/api`.
- `addFormatters` converts path strings into `BookId`.
- `addCorsMappings` restricts trusted frontend origins.
- `configureHttpMessageCodecs` sets maxInMemorySize to 256KiB for default codecs.
- `addResourceHandlers` serves `/guide/intro.txt` from `classpath:/guide-assets/`.
- Preserves Boot's static default: `/boot-health.txt` from `classpath:/static/`.
- Controller returns JSON, accepts POST JSON, and sets an `X-Request-ID` header.
- `WebTestClient` tests verify route prefix/converter, CORS preflight, resource handler, and preserved Boot static behavior.

No `spring-boot-starter-web`, no `@EnableWebFlux`. This is the core point of the example.

### 12.1. Structure

~~~text
webflux-infrastructure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/WebFluxInfrastructureApplication.java
    │   └── resources/
    │       ├── static/boot-health.txt
    │       └── guide-assets/intro.txt
    └── test/java/demo/WebFluxInfrastructureTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-infrastructure-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

### 12.3. WebFluxInfrastructureApplication.java

Save **all** the code below in `src/main/java/demo/WebFluxInfrastructureApplication.java`. Only the startup class is public top-level; the remaining records/classes are package-private, making one shared file valid in Java 17.

~~~java
package demo;

import java.time.Duration;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.method.HandlerTypePredicate;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.PathMatchConfigurer;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxInfrastructureApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxInfrastructureApplication.class, args);
    }
}

record BookId(long value) {
}

record BookResponse(long id, String title) {
}

record CreateBookRequest(String title) {
}

@Configuration(proxyBeanMethods = false)
class MyWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void configurePathMatching(PathMatchConfigurer configurer) {
        configurer.addPathPrefix(
                "/api",
                HandlerTypePredicate.forAnnotation(RestController.class));
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, BookId.class,
                source -> new BookId(Long.parseLong(source)));
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com",
                        "http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(true)
                .maxAge(1800);
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/guide/**")
                .addResourceLocations("classpath:/guide-assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}

@RestController
class BookController {

    @GetMapping(path = "/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<BookResponse> book(@PathVariable BookId id) {
        if (id.value() <= 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ID must be positive"));
        }
        return Mono.just(
                new BookResponse(id.value(), "Book #" + id.value()));
    }

    @PostMapping(path = "/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<BookResponse>> create(
            @RequestBody Mono<CreateBookRequest> request) {
        return request.map(input -> {
            if (input.title() == null || input.title().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Title required");
            }

            return ResponseEntity.status(HttpStatus.CREATED)
                    .header("X-Request-ID",
                            UUID.randomUUID().toString())
                    .body(new BookResponse(1001L, input.title()));
        });
    }
}
~~~

**Explaining the runnable code:**

1. `@SpringBootApplication` enables Boot auto-configuration and starts the Reactor Netty web server from starter-webflux.
2. `MyWebFluxConfig implements WebFluxConfigurer` **without @EnableWebFlux** preserves Boot's baseline.
3. `@GetMapping("/books/{id}")` is prefixed to `/api/books/{id}` via `HandlerTypePredicate.forAnnotation(RestController.class)`.
4. `BookId` is a value object; the converter parses the path variable string using `Long.parseLong`.
5. CORS applies only to `/api/**`, GET/POST, and trusted origins; credentials require specific origins.
6. `ServerCodecConfigurer` caps certain aggregation operations; default JSON codecs are retained.
7. `ResourceHandlerRegistry` adds `/guide/**` without erasing Boot's default static mappings.
8. POST generates `X-Request-ID` and exposes the header to allowed cross-origin JavaScript, though a demo UUID does not replace real distributed tracing.
9. 1001L is a hardcoded mock ID for illustration, **not persistence**; a real API needs a repository, transactions, and uniqueness.
10. The code omits Spring Security so tests can focus on WebFlux infrastructure; production requires proper auth/authz/CSRF design.

### 12.4. Creating static files

`src/main/resources/guide-assets/intro.txt`:

~~~text
WebFlux infrastructure guide
~~~

`src/main/resources/static/boot-health.txt`:

~~~text
Boot static resource remains available
~~~

Neither file goes into `src/main/webapp`. Spring Boot reactive apps use classpath static resources rather than the traditional Servlet WAR layout.

### 12.5. Launching

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Call:

~~~bash
curl -i http://localhost:8080/api/books/42
~~~

Equivalent response body:

~~~json
{"id":42,"title":"Book #42"}
~~~

Call the URL **without prefix**:

~~~bash
curl -i http://localhost:8080/books/42
~~~

Expected not to match the controller mapping; 404 is returned via default routing (possibly via static handler fallback).

Try POST:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  --data '{"title":"Reactive Spring"}'
~~~

HTTP 201 response, a server-generated X-Request-ID header, body:

~~~json
{"id":1001,"title":"Reactive Spring"}
~~~

Read the static guide:

~~~bash
curl -i http://localhost:8080/guide/intro.txt
~~~

Body:

~~~text
WebFlux infrastructure guide
~~~

Read Boot's default static asset:

~~~bash
curl -i http://localhost:8080/boot-health.txt
~~~

Body:

~~~text
Boot static resource remains available
~~~

This is a useful test criterion proving Boot auto-configuration remains active when `@EnableWebFlux` is omitted.

### 12.6. Curl to verify CORS preflight

A browser SPA on `http://localhost:5173` sending a JSON POST may send an OPTIONS preflight:

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/books \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Response typically includes:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

Headers may vary in order/casing; do not compare raw text strictly. When Origin is disallowed:

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/books \
  -H 'Origin: https://attacker.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Spring WebFlux CORS processing normally rejects the preflight (e.g., 403). Browsers do not send the actual POST when preflight fails, whereas `curl` still receives the HTTP response since curl does not enforce SOP.

## 13. WebTestClient testing

Create `src/test/java/demo/WebFluxInfrastructureTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxInfrastructureTest {

    @Autowired
    WebTestClient http;

    @Test
    void prefixedControllerAndConverterWork() {
        http.get().uri("/api/books/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(42)
                .jsonPath("$.title").isEqualTo("Book #42");
    }

    @Test
    void invalidIdGetsBadRequest() {
        http.get().uri("/api/books/0").exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void postJsonKeepsDefaultCodec() {
        http.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateBookRequest("Reactive"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("X-Request-ID")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactive");
    }

    @Test
    void trustedOriginPreflightIsAllowed() {
        http.options().uri("/api/books")
                .header(HttpHeaders.ORIGIN,
                        "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173")
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true");
    }

    @Test
    void untrustedOriginPreflightIsRejected() {
        http.options().uri("/api/books")
                .header(HttpHeaders.ORIGIN,
                        "https://attacker.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void customStaticResourceWorks() {
        http.get().uri("/guide/intro.txt")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "max-age=300")
                .expectBody(String.class)
                .value(body -> org.junit.jupiter.api.Assertions.assertTrue(
                        body.contains("WebFlux infrastructure guide")));
    }

    @Test
    void bootDefaultStaticResourceIsStillAvailable() {
        http.get().uri("/boot-health.txt")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> org.junit.jupiter.api.Assertions.assertTrue(
                        body.contains("Boot static resource remains available")));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Why choose WebTestClient with RANDOM_PORT?** The test suite connects to the Boot-started HTTP server over the reactive network runtime, making it far better for testing infrastructure, static files, and real CORS than calling controller methods directly. `WebTestClient` also offers `bindToApplicationContext` mode for slice/unit tests when no socket is needed.

**Limitations:** The sample uses `spring-boot-starter-test` without a gateway or Spring Security; tests do not replace security integration, reverse proxy CORS/headers, or production traffic validation. Unused imports in the test example flagged by an IDE can be removed without affecting test behavior.

### 13.1. An easily missed mistake in CORS tests

An OPTIONS preflight test needs all three:

- `Origin`.
- `Access-Control-Request-Method`.
- `Access-Control-Request-Headers` if the actual request sends custom/non-safelisted headers.

Sending only `Origin` with OPTIONS can be interpreted as an actual cross-origin OPTIONS request rather than a preflight. Tests must mirror browser behavior.

### 13.2. Testing codec limits

To test `maxInMemorySize`, craft a payload that actually has to be aggregated/decoded beyond the limit, then check the exception/status per your setup. Do not hardcode `assert 413` if your version's default framework error mapping does not guarantee that status. In production, define an explicit error contract (e.g., HTTP 413 when body exceeds policy limits) and integration-test it.

### 13.3. Testing negative cases

Alongside happy paths, add tests for:

- `/books/42` does not match when `/api` prefix is active.
- Origin `https://attacker.example` receives no ACAO header.
- POST JSON missing title returns 400 rather than 500.
- Converter ID `abc` returns 400 (per configured binding semantics).
- Unsupported content type POST returns 415; mismatched Accept can return 406.
- Files outside `guide-assets` are not publicly routed.
- Bodies exceeding the memory cap along the codec aggregation path.
- If Spring Security is added, preflight/actual auth, CSRF, and 401/403 work properly.
- If `@EnableWebFlux` is added, a static resource regression test catches lost Boot auto-config.

## 14. Comparison with @EnableWebFlux: alternative configuration example

A Spring Framework app that does not rely on Boot WebFlux auto-config can define:

~~~java
@Configuration
@EnableWebFlux
class StandaloneWebFluxConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com");
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

This is an **alternative approach** — **do not add it to the section 12 demo**. Copying this config into a Boot app can alter Boot's baseline static/resource/codec configurations. To retain Boot defaults, remove `@EnableWebFlux` and keep only WebFluxConfigurer.

### 14.1. When full control is genuinely needed

Use it when:

- Highly specialized framework integration is unmet by Boot properties/WebFluxConfigurer.
- The app builds its own runtime environment without Boot auto-config.
- You must replace infrastructure beans and accept maintaining regression tests.
- Security/compliance requirements mandate an audited, exact custom infrastructure setup.

Do not use it just to add a converter or CORS mapping.

### 14.2. DelegatingWebFluxConfiguration and WebFluxConfigurationSupport

`@EnableWebFlux` imports `DelegatingWebFluxConfiguration`, which extends `WebFluxConfigurationSupport` and applies all `WebFluxConfigurer` implementations.

In advanced mode, you can directly extend `DelegatingWebFluxConfiguration` and override infrastructure bean declarations when needed. However:

- This deeply alters the framework lifecycle.
- Mixing it improperly easily breaks Boot defaults.
- You must read Javadoc for your exact version.
- Overrides are only confirmed safe after testing path mappings, codecs, errors, security, static resources, blocking handlers, and HTTP integration.

## 15. Common pitfalls

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Added @EnableWebFlux, static index.html disappeared | Boot WebFlux auto-config no longer provides previous defaults | Remove @EnableWebFlux unless full control is needed |
| JSON codec behavior changed after @EnableWebFlux | Boot CodecCustomizer/properties no longer apply as expected | Reconfigure manually or return to Boot-managed config |
| GET API has /api/api/... | Prefix declared in both configurer and controller | Pick a single owner for the prefix |
| CORS preflight 403 | Origin/method/header missing from policy | Verify exact preflight headers |
| CORS preflight 401 with Security | Reactive security filter runs before proper CORS handling | Integrate CORS properly with ServerHttpSecurity |
| Wildcard Origin + credentials error | Invalid CORS configuration | Use exact allowlist; avoid overly broad patterns |
| Using WebMvcConfigurer has no effect | App runs WebFlux, not MVC | Use WebFluxConfigurer |
| Both starter-web and starter-webflux present yet handlers are not reactive | Boot selects MVC by default | Include only starter-webflux or explicitly set app type |
| Large JSON body throws DataBufferLimitException | Codec aggregation exceeded limit | Review cap/payload/streaming/413 policy |
| Calling registerDefaults(false) loses JSON | Disabled default codecs | Only add needed codecs, keep defaults |
| Static asset 404 | File not on classpath / route mismatch | Check resource locations/path patterns |
| CORS passes yet cookie is not sent | SameSite/Secure/cross-site restrictions | Debug browser cookies, not CORS alone |
| Blocking JDBC slows requests in bulk | Blocking the event loop | Native reactive DB or boundedElastic |
| @Order does not resolve codec conflict | Two configs mutate the same setting | Single owner, test final behavior |
| WebFilter cannot read ServletRequest | Wrong stack abstraction | Use WebFlux ServerWebExchange/WebFilter |
| 500 after streaming response started | Response committed, status cannot change | In-band error or cancel/log |
| App uses Boot 4 codec docs in Boot 3.5 | Different packages/property APIs | Read Javadocs for exact version |
| Async cancel fails to clean up resources | Resource not scoped to subscription | Use using/usingWhen/doFinally and tests |

## 16. Code review / operations checklist

- [ ] App is genuinely selected as **REACTIVE** by Boot, not accidentally MVC.
- [ ] No `@EnableWebFlux` added in Boot merely to "turn on" WebFlux.
- [ ] Configurer adds specific features without overriding everything.
- [ ] Boot properties match the exact version and tests prove they take effect.
- [ ] Codec memory caps, body size/codec limits, concurrency quotas, and backpressure are reviewed.
- [ ] CORS origin/method/header allowlists are tight; Security/CSRF/cookies have clear separation.
- [ ] API prefix has one owner and does not break static/functional routes.
- [ ] Converters/formatters turn invalid inputs into proper errors.
- [ ] Static assets sit on the right classpath with cache policies and do not expose private uploads.
- [ ] View resolvers/Jackson serializers retain expected behavior after customization.
- [ ] No blocking I/O on the event loop; explicit executor/scheduler policy exists.
- [ ] Error handlers never leak stacktraces/secrets to clients and handle committed responses cleanly.
- [ ] Multi-configurer conflicts are governed by ownership and integration tests.
- [ ] WebTestClient tests positive/negative routes, CORS, static resources, and codecs.
- [ ] Observability covers HTTP latency/status, routes, scheduler blocking, buffer memory, and server resource usage.
- [ ] If full-control `@EnableWebFlux` is chosen, broad regression suites and documented rationale exist.

## 17. Self-study exercises

**Exercise 1 — Three choices:** When should you use only Boot properties? When should you implement WebFluxConfigurer? When should you use @EnableWebFlux? State the trade-offs of each tier.

**Exercise 2 — Startup behavior:** A project has both starter-web and starter-webflux. Why doesn't WebFluxConfigurer create a reactive dispatcher? How do you fix the dependencies?

**Exercise 3 — CORS:** Write addCorsMappings allowing only https://app.example.com to call GET/POST /api/** with credentials. Why is allowedOrigins("*") invalid here?

**Exercise 4 — Prefix:** A controller has @GetMapping("/books/{id}"), and the configurer calls addPathPrefix("/api", RestController). What is the public URL? What happens if the controller already had /api/books?

**Exercise 5 — Converter:** Create record BookId(long value) and a String->BookId converter. Test GET /api/books/42 and invalid negative IDs.

**Exercise 6 — Codecs:** Use configureHttpMessageCodecs to set 256KiB. Test a request body requiring >256KiB aggregation and analyze DataBufferLimitException without assuming status is always 413.

**Exercise 7 — Static resources:** Add /guide/** from classpath:/guide-assets/ with a 5-minute cache while preserving Boot's default /boot-health.txt.

**Exercise 8 — Security:** Use ServerHttpSecurity to protect /api/**, combining CORS preflight, cookie CSRF, and 401/403 handling.

**Exercise 9 — @EnableWebFlux regression:** Add @EnableWebFlux to the demo, run the tests, and record which Boot-managed behaviors break. Design the choice between removing the annotation vs recreating valid mappings.

**Exercise 10 — Functional routing:** Create a RouterFunction GET /fn/ping and verify that configurePathMatching addPathPrefix does not automatically apply the same prefix to functional routes.

**Exercise 11 — Blocking:** Suppose a legacy JDBC call sits inside a controller Mono chain. Compare configureBlockingExecution and Mono.fromCallable(...).subscribeOn(boundedElastic()).

**Exercise 12 — Observability:** When an API returns 500 due to misconfigured codecs or wrong path rewrites, which metrics/logs help distinguish configuration errors from business errors?

**Exercise 13 — Custom codecs:** Why is registerDefaults(false) dangerous? When wanting a custom Jackson date format, where should you start instead of wiping all readers/writers?

**Exercise 14 — Multi-configurer:** Two beans set different maxInMemorySize values. Design an ownership/centralized-property/testing mechanism to avoid order-dependent behavior.

## 18. Key takeaways

- **WebFlux infrastructure** manages handler mappings/adapters/result handlers, codecs, converters, CORS, resource handling, and exception processing.
- **@EnableWebFlux** imports `DelegatingWebFluxConfiguration` to supply Framework configuration; in Boot, use it only when you want full control over the entire WebFlux setup.
- **WebFluxConfigurer** is the extension point for adding specific configurations; in Boot, typically implement it under `@Configuration` **without @EnableWebFlux**.
- Boot starters and auto-config bring static resources, codecs, Jackson, error handling, and production conveniences; do not discard them over an unnecessary annotation.
- `configureHttpMessageCodecs` tunes HTTP readers/writers; `defaultCodecs().maxInMemorySize` is not a whole-request or server-memory quota.
- `addCorsMappings` is strictly a browser cross-origin policy, **never a replacement for authentication, authorization, or CSRF**.
- `configurePathMatching` targets annotated controllers and does not automatically prefix functional routes or static resources.
- `addResourceHandlers` customizes static assets; security and caching strategies must be explicit.
- Reactor Netty, WebClient, Security, cancellation/backpressure, and blocking execution each have their own configuration layers.
- Escalate to `@EnableWebFlux`/advanced config only with a verified reason and regression tests.

## 19. Official documentation

- [Spring Framework 6.2 — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): @EnableWebFlux, WebFluxConfigurer, formatters, codecs, resources, path matching, blocking execution, and advanced mode.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): Boot WebFlux auto-config, Boot-specific properties, customizers, static resources, Security/error handling.
- [Spring Framework 6.2 — WebFlux Overview](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html).
- [Spring Framework 6.2 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): HandlerMapping/HandlerAdapter/HandlerResultHandler.
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html).
- [WebFluxConfigurer 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html).
- [ServerCodecConfigurer 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html).
- [Spring Boot 3.5 — Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html).
- [Spring Framework 6.2 — Path Matching](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html#webflux-config-path-matching).
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html).
