# Media Type Resolution and Custom Handler Argument Registration

In Spring WebFlux, an endpoint can receive multiple request formats and return multiple response formats. Spring must determine what format the client sent in the body, what format the client wants in return, which codec can read or write that format, and what arguments the controller requires.

Two mechanisms often appear together in WebFlux configuration but solve two different problems:

- **Media type resolution** determines the response format requested by the client, usually based on the `Accept` header. For annotated controllers, WebFlux checks only `Accept` by default; a query parameter strategy such as `?format=json` can be added using `RequestedContentTypeResolverBuilder`.
- **Handler method argument resolver** produces a value for a parameter in a controller method. For example, an application can build a `TenantContext` from the `X-Tenant-Id` header and inject it into a parameter annotated with `@CurrentTenant`.

Distinguish these two mechanisms from request `Content-Type`, `consumes`/`produces` in mappings, and HTTP message codecs. The media type resolver decides what the client wants to receive; codecs read/write bodies; custom argument resolvers prepare a controller parameter.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `Content-Type` and `Accept`.
2. Explain the roles of `consumes`, `produces`, `HttpMessageReader`, and `HttpMessageWriter`.
3. Describe how WebFlux selects requested media types for annotated controllers.
4. Use `RequestedContentTypeResolverBuilder` to prioritize a query parameter or header.
5. Understand resolver ordering and the meaning of `MediaType.ALL`.
6. Distinguish content type resolvers from codecs and argument resolvers.
7. Implement WebFlux's reactive `HandlerMethodArgumentResolver`.
8. Register custom resolvers via `WebFluxConfigurer.configureArgumentResolvers` and `ArgumentResolverConfigurer`.
9. Design an annotation for a custom controller parameter.
10. Handle missing headers, validation errors, and asynchronous lookups without blocking the event loop.
11. Know when to use Converter/Formatter, `@RequestBody`, codecs, or a custom argument resolver.
12. Test Accept, query format, 406, 415, and custom arguments with WebTestClient.

## 2. Media Types in HTTP

A media type describes the format of HTTP content. A media type has the form:

~~~text
type/subtype; parameter=value
~~~

Example:

~~~http
Content-Type: application/json
Accept: application/json
~~~

Some common media types:

| Media type | Common Content |
| --- | --- |
| `application/json` | JSON object or array |
| `application/xml` | XML document |
| `text/plain` | Plain text |
| `text/html` | HTML |
| `application/octet-stream` | Binary data |
| `application/x-www-form-urlencoded` | URL-encoded form |
| `multipart/form-data` | Multipart form, potentially with files |
| `text/event-stream` | Server-Sent Events |
| `application/x-ndjson` | Newline-delimited JSON records |

A media type can have parameters, such as `application/json;charset=UTF-8`. The HTTP layer and codecs need to handle the media type along with compatible parameters properly.

### 2.1. Content-Type: What Did the Client Send?

`Content-Type` describes the format of the request body:

~~~http
POST /api/messages
Content-Type: application/json

{"text":"hello"}
~~~

WebFlux uses this information to select an `HttpMessageReader` matching the controller parameter type. With `@RequestBody Message`, the JSON reader can decode JSON bytes into a `Message` object.

If an endpoint declares `consumes = "application/json"` but the client sends `text/plain`, the request fails the mapping condition and typically receives `415 Unsupported Media Type`.

`Content-Type` is not the header used to choose the response format.

### 2.2. Accept: What Does the Client Want to Receive?

`Accept` describes the media types the client can accept:

~~~http
GET /api/messages/42
Accept: application/json
~~~

WebFlux uses the requested media types to choose a `produces` mapping and the response format. When the controller returns an object, the matching `HttpMessageWriter` encodes the object into the body.

If an endpoint can only produce `application/json` while the client requests `text/csv`, the request may receive `406 Not Acceptable`.

`Accept` does not describe the request body format. A POST request can send JSON via `Content-Type` while requesting a response in a different media type via `Accept`.

### 2.3. Comparison Table

| Component | Question | Where Used |
| --- | --- | --- |
| `Content-Type` | What format is the request body in? | Reading request body |
| `Accept` | What response format does the client want? | Content negotiation for response |
| `consumes` | Which request body formats does the handler accept? | Handler selection condition |
| `produces` | Which response formats can the handler produce? | Handler selection condition |
| `HttpMessageReader` | How are request bytes read into an object? | Decoding request |
| `HttpMessageWriter` | How is an object encoded into response bytes? | Writing response |
| `RequestedContentTypeResolver` | What are the requested response media types? | Annotated controllers |
| `HandlerMethodArgumentResolver` | How is a controller parameter value created? | Invoking handler method |

## 3. Media Type Processing Flow in WebFlux

At a high level, an annotated controller goes through these steps:

~~~text
HTTP request
   |
   +--> path, method, params, headers
   |
   +--> Content-Type + consumes
   |       |
   |       +--> select matching handler
   |
   +--> Accept / requested media type
   |       |
   |       +--> produces condition
   |       |
   |       +--> select response representation
   |
   +--> HandlerMethodArgumentResolver
   |       |
   |       +--> resolve controller arguments
   |
   +--> Controller method
   |
   +--> HttpMessageWriter
           |
           +--> encode response using selected media type
~~~

This is a simplified diagram. Handler selection also evaluates HTTP method, path, query conditions, and header conditions. Controller arguments are resolved parameter by parameter. Request bodies are usually handled by a resolver integrated with `HttpMessageReader`; response bodies are written using `HttpMessageWriter`.

### 3.1. RequestMapping: consumes and produces

Example:

~~~java
@PostMapping(
    path = "/messages",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Message> create(@RequestBody Mono<Message> body) {
    return body;
}
~~~

- `consumes` restricts the request body media type.
- `produces` describes the media type the handler can return.
- `@RequestBody` uses a message reader to decode the request.
- `Mono<Message>` is written through an appropriate message writer.

An endpoint can declare multiple media types:

~~~java
@GetMapping(
    path = "/export",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.TEXT_PLAIN_VALUE
    }
)
~~~

However, declaring `produces` does not automatically install a codec. There must be a writer supporting the Java type and the selected media type. If no matching writer exists, the response cannot be encoded.

### 3.2. 406 and 415

| Status | Common Cause | Check |
| --- | --- | --- |
| 406 Not Acceptable | No representation matching Accept/produces or no supporting writer | Accept, produces, writer |
| 415 Unsupported Media Type | Content-Type not matched by consumes or no supporting reader | Content-Type, consumes, reader |
| 400 Bad Request | Invalid body or argument validation failed | JSON syntax, conversion, validation |
| 500 Internal Server Error | Unhandled error in resolver/controller/codec | Root exception and error handler |

Do not handle every media type error by arbitrarily adding more codecs. First determine whether the error lies in request mapping, content negotiation, or encode/decode capability.

## 4. RequestedContentTypeResolver in WebFlux

WebFlux uses `RequestedContentTypeResolver` to determine the list of media types requested by the client for an annotated controller's response.

By default, the resolver inspects the `Accept` header. If the request does not send a specific Accept header, the result may be `MediaType.ALL`, meaning the client does not restrict the response format.

WebFlux uses types in the package:

~~~text
org.springframework.web.reactive.accept
~~~

Key components:

- `RequestedContentTypeResolver`: contract for resolving requested media types from `ServerWebExchange`.
- `HeaderContentTypeResolver`: reads the Accept header.
- `ParameterContentTypeResolver`: reads a query parameter and maps keys to MediaTypes.
- `FixedContentTypeResolver`: returns a fixed list of media types.
- `RequestedContentTypeResolverBuilder`: composes multiple resolvers in order.

### 4.1. Default Uses Accept Only

If no custom resolver is configured, the builder adds `HeaderContentTypeResolver` by default. Thus clients can request:

~~~http
Accept: application/json
~~~

If the client does not send a specific Accept header, the resolver typically returns `MediaType.ALL`. This allows the handler to pick a representation compatible with the mapping and available writers.

### 4.2. Adding a format Query Parameter

Some APIs want format selection via a query parameter:

~~~text
GET /api/report?format=json
~~~

WebFlux provides `parameterResolver()` to map query parameter values to media types:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureContentTypeResolver(
            RequestedContentTypeResolverBuilder builder) {

        builder.parameterResolver()
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON)
            .mediaType("txt", MediaType.TEXT_PLAIN);

        builder.headerResolver();
    }
}
~~~

Here `format=json` is mapped to `application/json` and `format=txt` to `text/plain`. If the query parameter does not provide a specific media type, the next resolver—the header resolver—can handle Accept.

**Ordering note:** the builder creates a composite resolver. The first resolver that returns a specific list of media types, rather than just `MediaType.ALL`, is used. The example above prioritizes the query parameter before the Accept header. If you want Accept to take precedence, register `headerResolver()` before `parameterResolver()`.

Once you add resolvers yourself, explicitly declare all strategies the application still wants to support. Do not assume the header resolver is always automatically appended after a custom resolver.

### 4.3. Deliberate Order Configuration

Prioritize Accept:

~~~java
@Override
public void configureContentTypeResolver(
        RequestedContentTypeResolverBuilder builder) {

    builder.headerResolver();

    builder.parameterResolver()
        .parameterName("format")
        .mediaType("json", MediaType.APPLICATION_JSON)
        .mediaType("txt", MediaType.TEXT_PLAIN);
}
~~~

Prioritize query parameter:

~~~java
@Override
public void configureContentTypeResolver(
        RequestedContentTypeResolverBuilder builder) {

    builder.parameterResolver()
        .parameterName("format")
        .mediaType("json", MediaType.APPLICATION_JSON)
        .mediaType("txt", MediaType.TEXT_PLAIN);

    builder.headerResolver();
}
~~~

The two configurations can produce different results when a request has both `?format=json` and `Accept: text/plain`. Choose one policy and test it explicitly.

### 4.4. Query Parameter Resolvers Should Use an Allowlist

Map only permitted keys:

~~~java
builder.parameterResolver()
    .parameterName("format")
    .mediaType("json", MediaType.APPLICATION_JSON)
    .mediaType("txt", MediaType.TEXT_PLAIN);
~~~

Clients send a registered key such as `json` or `txt`. Do not accept an arbitrary string and parse it directly into any media type. An allowlist gives the API a stable contract and prevents clients from requesting formats the server does not support.

### 4.5. Do Not Confuse query format with Request Body Content-Type

`?format=json` is a strategy for selecting the requested response media type when configured. It does not turn the request body into JSON and does not replace the Content-Type header.

Example:

~~~http
POST /api/messages?format=json
Content-Type: application/x-www-form-urlencoded
Accept: text/plain

text=hello
~~~

The body is still a URL-encoded form. The query format can participate in selecting the response media type according to the configured resolver order. `Content-Type` still describes the form body.

## 5. Media Types, Codecs, and Message Readers/Writers

The content type resolver does not decode JSON and does not encode responses. Byte/object conversion belongs to HTTP message codecs.

### 5.1. Request: HttpMessageReader

A request body enters WebFlux as a byte stream. An appropriate reader is selected based on parameter type and Content-Type:

~~~text
HTTP request bytes
      |
      v
Content-Type: application/json
      |
      v
HttpMessageReader<Message>
      |
      v
Message object
      |
      v
Controller
~~~

Example:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<Message> create(@RequestBody Mono<Message> message) {
    return message;
}
~~~

The JSON reader decodes the body into `Message`. If a new format needs support, register the corresponding codec/reader via `ServerCodecConfigurer`; adding the media type to the content resolver alone is not enough.

### 5.2. Response: HttpMessageWriter

The response flows in the opposite direction:

~~~text
Controller result
      |
      v
Requested media type
      |
      v
HttpMessageWriter<Message>
      |
      v
HTTP response bytes
~~~

For example, the controller returns `Mono<Message>` and the client requests application/json. The JSON writer encodes the object into JSON bytes.

### 5.3. Three Configurations Solving Three Problems

| Configuration API | Responsibility |
| --- | --- |
| `configureContentTypeResolver` | Determine requested response media types |
| `configureHttpMessageCodecs` | Register/configure readers and writers to read/write bodies |
| `configureArgumentResolvers` | Register resolvers for custom controller parameters |

Codec example:

~~~java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {

    configurer.defaultCodecs()
        .maxInMemorySize(512 * 1024);
}
~~~

Argument resolver example:

~~~java
@Override
public void configureArgumentResolvers(
        ArgumentResolverConfigurer configurer) {

    configurer.addCustomResolver(
        new CurrentTenantArgumentResolver()
    );
}
~~~

Do not use a custom argument resolver just to add a JSON codec; nor use a content type resolver to inject a request context object.

## 6. WebFlux HandlerMethodArgumentResolver

A controller method can accept path variables, request parameters, headers, principals, sessions, request bodies, exchanges, or an application-specific type.

Spring includes built-in argument resolvers for common types. When an application-specific type is needed, you can implement WebFlux's `HandlerMethodArgumentResolver`.

WebFlux's reactive interface is in:

~~~java
org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver
~~~

Two main methods:

~~~java
boolean supportsParameter(MethodParameter parameter);

Mono<Object> resolveArgument(
    MethodParameter parameter,
    BindingContext bindingContext,
    ServerWebExchange exchange
);
~~~

### 6.1. supportsParameter

This method decides whether the resolver is responsible for the parameter under inspection.

Check very specifically:

- Annotation marking the parameter.
- Exact Java type supported by the resolver.
- Generic type if the resolver supports a collection or reactive wrapper.

Do not write a resolver that matches every parameter of type Object or String. An overly broad resolver can compete with built-in resolvers or make controller behavior hard to predict.

### 6.2. resolveArgument

This method produces the value for the parameter and returns `Mono<Object>`.

The data source can be headers/query parameters, request attributes, principal/session, reactive repositories/services, or values computed from `ServerWebExchange`.

If you need to call a reactive service, return the service's publisher. Do not call `block()` to wait for data. If required data is missing, return `Mono.error(...)` with an appropriate exception; do not return a dummy object or use `Mono.empty()` when the controller expects a non-null value.

### 6.3. BindingContext and ServerWebExchange

`ServerWebExchange` provides the request, response, attributes, session, and information related to the current request.

`BindingContext` provides the data binding context for the controller invocation. A simple resolver that only reads a header may not need to use bindingContext; it still must declare the parameter according to the SPI.

### 6.4. Registering via ArgumentResolverConfigurer

Use `WebFluxConfigurer.configureArgumentResolvers`:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}
~~~

`addCustomResolver` adds resolvers supporting custom parameters. This is a mechanism to append custom resolvers, not a way to replace existing built-in resolvers.

If you need to change how Spring resolves a built-in argument type, look at advanced WebFlux configuration and `RequestMappingHandlerAdapter`; do not use a regular custom resolver expecting it to override a default resolver.

### 6.5. Do Not Accidentally Use the Spring MVC SPI

Spring MVC and Spring WebFlux have interfaces with the same name in different packages.

| Stack | Interface |
| --- | --- |
| Spring MVC | `org.springframework.web.method.support.HandlerMethodArgumentResolver` |
| Spring WebFlux | `org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver` |

The MVC SPI returns a value synchronously and accepts `NativeWebRequest`/`ModelAndViewContainer`. The WebFlux SPI returns `Mono<Object>` and accepts `BindingContext`/`ServerWebExchange`.

Using the wrong interface will not compile with WebFlux's `ArgumentResolverConfigurer` or will not work within the reactive lifecycle.

## 7. Designing a Custom Argument Resolver

For example, an application needs to extract the current tenant from the `X-Tenant-Id` header. Many controllers need the same `TenantContext` object.

If every controller reads the header, checks for emptiness, and normalizes the tenant ID itself, that logic is duplicated. A custom argument resolver lets controllers declare:

~~~java
@GetMapping("/greeting")
Mono<Greeting> greeting(@CurrentTenant TenantContext tenant) {
    return Mono.just(new Greeting("hello", tenant.id()));
}
~~~

### 7.1. Marker Annotation

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface CurrentTenant {}
~~~

The annotation targets method parameters only and requires runtime retention so the resolver can read it at runtime.

### 7.2. Domain Data Type

~~~java
record TenantContext(String id) {}
~~~

This type represents a normalized tenant. A real application may include a tenant ID, display name, or verified metadata.

### 7.3. Resolver

~~~java
final class CurrentTenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
            && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String tenantId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Tenant-Id");

            if (tenantId == null || tenantId.isBlank()) {
                return Mono.error(
                    new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"
                    )
                );
            }

            TenantContext tenant =
                new TenantContext(tenantId.trim());

            return Mono.just((Object) tenant);
        });
    }
}
~~~

The resolver performs these steps:

1. Accepts only parameters annotated with `@CurrentTenant` and of type `TenantContext`.
2. Reads the header from the current request.
3. Checks that the header exists and is not blank.
4. Trims whitespace.
5. Returns TenantContext inside a Mono.
6. If the header is missing, emits a 400 error via ResponseStatusException.

`Mono.defer` ensures the read/validation operation runs when the publisher is subscribed. The resolver does not store request data in a field on an object shared across requests.

### 7.4. Registering the Resolver

~~~java
@Configuration
class TenantWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}
~~~

In a larger application, you can register the resolver as a bean to inject services or repositories. The resolver can call a reactive service:

~~~java
return tenantDirectory.findById(tenantId)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(
            HttpStatus.NOT_FOUND,
            "Unknown tenant"
        )
    ))
    .cast(Object.class);
~~~

`tenantDirectory.findById` here is an illustrative application reactive API. When doing a database or network lookup, let the publisher remain asynchronous. Do not call blocking repositories on the event loop.

### 7.5. Controller Using the Custom Argument

~~~java
record Greeting(String message, String tenantId) {}

@RestController
@RequestMapping("/api")
class GreetingController {

    @GetMapping(
        path = "/greeting",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Greeting> greeting(
            @CurrentTenant TenantContext tenant) {

        return Mono.just(
            new Greeting("hello", tenant.id())
        );
    }
}
~~~

The controller does not need to know whether the tenant ID comes from a header or a repository. It receives a type already prepared by the resolver.

### 7.6. Do Not Treat a Tenant Header as Proof of Authorization

Headers sent by clients can be spoofed. The resolver only normalizes or looks up the value; it does not by itself verify that the user is authorized to access that tenant.

In production:

- Authenticate the principal with Spring Security.
- Verify that the tenant falls within the scope the principal is allowed to access.
- If the tenant is determined from a JWT claim or security context, prefer the authenticated source instead of trusting an arbitrary header.
- Do not use a client-supplied tenant ID to grant database access without authorization.
- Return appropriate 401/403 errors when the principal or permissions are invalid.

A custom argument resolver is a convenient place to inject verified context, but security rules must be enforced at the service/security layer with full context.

## 8. When to Use an Argument Resolver, Converter, or Codec?

Not every custom parameter needs a new resolver.

| Need | Mechanism to Consider |
| --- | --- |
| Convert String to enum/ID/value object | `Converter` or `Formatter` via `addFormatters` |
| Bind query/form fields into a DTO | `@ModelAttribute` and WebDataBinder |
| Read a specific header | `@RequestHeader` |
| Read a query parameter | `@RequestParam` |
| Read a JSON/XML request body | `@RequestBody` and HttpMessageReader |
| Add a new body format | `ServerCodecConfigurer` and custom codec |
| Inject annotation-driven request-scoped context | `HandlerMethodArgumentResolver` |
| Inject current principal | Built-in resolver or Spring Security |
| Attach data to exchange before controller | WebFilter and exchange attributes |

### 8.1. Use Converter/Formatter When Only Type Conversion Is Needed

If the source parameter is already resolved by Spring but needs conversion from String to an application type, use a converter:

~~~java
registry.addConverter(
    String.class,
    TenantId.class,
    TenantId::new
);
~~~

This is an illustrative snippet; `TenantId` needs to be an appropriate value object type. Converters focus on value conversion. They are not the right place to access the request, perform authorization, or call repositories.

### 8.2. Use Codecs When Processing Bodies

If you need to support a new media type such as a vendor JSON format or custom binary format, build an encoder/decoder and register it with `ServerCodecConfigurer`. A custom argument resolver should not read the raw request body itself because the body is a single-use stream and codecs are responsible for decoding.

### 8.3. Use WebFilter When Shared Request Context Is Needed

If every request needs a tenant/correlation ID and controllers do not need an annotation, you can use a `WebFilter` to validate/read the header and store it in exchange attributes or Reactor Context as appropriate.

A custom argument resolver is useful when you want controllers to explicitly declare domain-meaningful parameters. WebFilter is useful for cross-cutting concerns at the request pipeline level.

## 9. Interaction Between Media Type Resolver and Argument Resolver

Both resolvers can be registered in the same `WebFluxConfigurer`:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureContentTypeResolver(
            RequestedContentTypeResolverBuilder builder) {

        builder.parameterResolver()
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON);

        builder.headerResolver();
    }

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}
~~~

They do not compete for the same data:

- The content type resolver inspects query parameters or Accept to determine the response media type.
- The argument resolver inspects MethodParameter and ServerWebExchange to produce TenantContext.
- Codecs process request/response bodies.
- Request mapping uses consumes/produces to select a compatible handler.

A controller can use both:

~~~java
@GetMapping(
    path = "/greeting",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Greeting> greeting(
        @CurrentTenant TenantContext tenant) {
    return Mono.just(new Greeting("hello", tenant.id()));
}
~~~

A client can call:

~~~http
GET /api/greeting?format=json
X-Tenant-Id: acme
Accept: */*
~~~

The query parameter selects the requested media type; the tenant header is converted into TenantContext by the custom argument resolver. The response body is encoded by the JSON writer.

## 10. Runnable Java 17 Example with Spring Boot WebFlux

Complete example using Java 17, Spring Boot 3.3.5, and WebFlux. The application has the `format=json` query parameter mapped to application/json, Accept header as fallback, `@CurrentTenant` injecting TenantContext into the controller, and `@RequestBody` using the JSON reader to echo Message.

### 10.1. Project Structure

~~~text
webflux-media-argument-demo/
├── build.gradle
└── src/
    ├── main/java/demo/MediaTypeDemoApplication.java
    └── test/java/demo/MediaTypeDemoTest.java
~~~

### 10.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages compatible Spring Framework and Reactor versions via dependency management. The example pins Boot 3.3.5 for an easily reproducible baseline; new projects should pick a still-supported patch version.

### 10.3. MediaTypeDemoApplication.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.BindingContext;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.accept.RequestedContentTypeResolverBuilder;
import org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver;
import org.springframework.web.reactive.result.method.annotation.ArgumentResolverConfigurer;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class MediaTypeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MediaTypeDemoApplication.class, args);
    }
}

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface CurrentTenant {}

record TenantContext(String id) {}
record Greeting(String message, String tenantId) {}
record Message(String text) {}

final class CurrentTenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
            && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String tenantId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Tenant-Id");

            if (tenantId == null || tenantId.isBlank()) {
                return Mono.error(
                    new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"
                    )
                );
            }

            return Mono.just(
                (Object) new TenantContext(tenantId.trim())
            );
        });
    }
}

@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureContentTypeResolver(
            RequestedContentTypeResolverBuilder builder) {

        builder.parameterResolver()
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON);

        builder.headerResolver();
    }

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}

@RestController
@RequestMapping("/api")
class ApiController {

    @GetMapping(
        path = "/greeting",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Greeting> greeting(
            @CurrentTenant TenantContext tenant) {

        return Mono.just(
            new Greeting("hello", tenant.id())
        );
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Message> echo(@RequestBody Mono<Message> message) {
        return message;
    }
}
~~~

Auxiliary types are declared package-private in the same file to keep the example concise. In a real project, annotations, resolvers, DTOs, configs, and controllers can be split into separate files.

### 10.4. MediaTypeDemoTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class MediaTypeDemoTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptHeaderSelectsJsonResponse() {
        client.get()
            .uri("/api/greeting")
            .header("X-Tenant-Id", "acme")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("hello")
            .jsonPath("$.tenantId").isEqualTo("acme");
    }

    @Test
    void queryFormatCanSelectJsonWhenAcceptIsWildcard() {
        client.get()
            .uri("/api/greeting?format=json")
            .header("X-Tenant-Id", "team-a")
            .accept(MediaType.ALL)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.tenantId").isEqualTo("team-a");
    }

    @Test
    void unsupportedAcceptReturnsNotAcceptable() {
        client.get()
            .uri("/api/greeting")
            .header("X-Tenant-Id", "acme")
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isEqualTo(406);
    }

    @Test
    void missingTenantHeaderReturnsBadRequest() {
        client.get()
            .uri("/api/greeting")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void requestBodyReaderDecodesJson() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new Message("hello reactive"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello reactive");
    }

    @Test
    void unsupportedRequestContentTypeReturnsUnsupportedMediaType() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.TEXT_PLAIN)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue("hello")
            .exchange()
            .expectStatus().isEqualTo(415);
    }
}
~~~

### 10.5. Running Tests

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The tests verify:

1. Accept application/json selects a JSON response.
2. Query parameter format=json can select JSON when Accept is wildcard.
3. Accept text/plain does not match produces JSON, returning 406.
4. Missing X-Tenant-Id causes the custom argument resolver to return 400.
5. JSON requests are decoded by the message reader into Message.
6. text/plain requests do not match consumes JSON, returning 415.

These are integration tests using WebTestClient; the example needs no external services. If you change resolver order, add a test containing both a format query and a specific Accept header to verify the precedence policy.

## 11. Verifying Content Resolver Order and Behavior

### 11.1. The First Resolver Returning a Specific Media Type Wins

Suppose the query resolver is configured before the header resolver:

~~~java
builder.parameterResolver()
    .parameterName("format")
    .mediaType("json", MediaType.APPLICATION_JSON);

builder.headerResolver();
~~~

Request:

~~~http
GET /api/greeting?format=json
Accept: text/plain
~~~

The query resolver runs first and returns application/json. The header resolver is not used once an earlier resolver returns a specific media type list.

If the order is reversed, Accept text/plain is chosen first. Since the handler only produces JSON, the request may return 406.

### 11.2. MediaType.ALL Allows Fallback

If the query parameter is absent or a resolver cannot determine a specific format, the result may be MediaType.ALL. The composite resolver continues trying the next resolver.

This is why you should understand both order and fallback results instead of only looking at the list of registered resolvers.

### 11.3. Quality q and Wildcards

Accept can contain multiple media types with q-values:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5, */*;q=0.1
~~~

The requested content type resolver returns the list of media types ordered by specificity and quality. Mappings and writers then inspect compatible media types. Do not parse Accept manually by splitting strings on commas; use Spring's MediaType API and resolvers to handle wildcards, parameters, and q-values.

## 12. Safe and Maintainable Media Type Configuration

### 12.1. Restrict Supported Formats

If the API only supports JSON, do not add a query resolver. Use the Accept header and declare produces explicitly.

If a query parameter is needed, map only formats for which the server actually has writers. Do not advertise XML/CSV without the corresponding codecs/writers and tests.

### 12.2. Be Careful with Caching

If responses vary by Accept, intermediate caches must distinguish representations by the Accept header; consider the `Vary: Accept` header according to your caching contract.

If responses vary by a query parameter like format, different URLs usually already produce different cache keys. Still check actual CDN/proxy behavior.

### 12.3. Do Not Use Path Extensions as the Default Mechanism

Do not assume URLs ending in `.json` automatically select JSON in WebFlux. Modern defaults use the Accept header; if a query parameter is needed, configure it explicitly via `parameterResolver()`. Path extensions can cause ambiguity with routing, file names, and security filters.

### 12.4. Do Not Let Query Format Replace Authorization

Format only selects how the response is represented. It should not govern data access permissions or enable an administrative endpoint. Authorization must still rely on principal, roles, scopes, and server-side policies.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing Content-Type with Accept | Misreading requests or selecting wrong response | Content-Type for request body; Accept for response |
| Thinking consumes chooses response format | Handler rejected even though response writer could support it | Use produces for response |
| Thinking produces registers a codec automatically | Mapping exists but no writer encodes the Java type | Register codecs via ServerCodecConfigurer |
| Configuring parameterResolver but forgetting headerResolver | Accept no longer serves as fallback as intended | Add headerResolver in the desired order |
| Registering resolvers in the wrong order | Query or Accept wins unexpectedly | Write tests for requests having both |
| Accepting arbitrary format values | Clients request unsupported representations | Use allowlist mapping |
| Using MVC's HandlerMethodArgumentResolver | Wrong signature, incompatible with WebFlux | Use interface in org.springframework.web.reactive.result.method |
| Resolver matching all String/Object | Competes with built-in resolvers | Check specific annotation and type |
| Thinking addCustomResolver overrides built-ins | Default resolver is still chosen for built-in types | Use custom annotation/type; advanced config if truly overriding |
| Using a resolver to read JSON body | Duplicates codec work and may consume body twice | Use @RequestBody and HttpMessageReader |
| Calling block inside a resolver | Blocks the event loop | Return Mono from a reactive service |
| Returning Mono.empty for a required argument | Controller may receive null/no value | Return Mono.error for missing input |
| Storing request data in a resolver field | Data can leak across requests | Read from exchange on each resolve; keep resolver stateless |
| Trusting X-Tenant-Id as authorization | Users can spoof tenants | Verify principal and tenant permissions |
| Skipping 406/415 tests | Negotiation bugs appear only when real clients call | Test Accept, Content-Type, consumes, produces |
| Adding @EnableWebFlux in Spring Boot just to add a resolver | Can cause some Boot auto-configurations to back off | Use WebFluxConfigurer without @EnableWebFlux in Boot |

## 14. WebFlux Configuration Review Checklist

Before shipping configuration into an application, check:

1. **Request media type:** Does Content-Type match consumes and readers?
2. **Response media type:** Are Accept or query formats resolved in the intended order?
3. **Mapping:** Does produces reflect representations that are truly supported?
4. **Codec:** Are there readers/writers matching the Java types and media types?
5. **Fallback:** When the query parameter is absent or unspecific, does the next resolver run?
6. **Quality:** Are wildcards and q-values handled via Spring APIs?
7. **Custom argument:** Does supportsParameter check exact annotation and type?
8. **Reactive:** Does resolveArgument return Mono without blocking?
9. **Errors:** Do missing values return clear errors and appropriate status codes?
10. **Security:** Are tenant/user contexts authenticated and authorized?
11. **Registration:** Is the resolver registered via configureArgumentResolvers?
12. **Built-in:** Does the custom resolver accidentally compete with default resolvers?
13. **Tests:** Does WebTestClient test Accept, query format, 406, 415, and custom arguments?
14. **Boot:** Is Spring Boot auto-configuration preserved by avoiding unnecessary @EnableWebFlux?

**Key takeaway:** By default, WebFlux resolves requested media types from Accept for annotated controllers. Query parameters can be added via RequestedContentTypeResolverBuilder, and resolver order must be chosen deliberately. Content-Type/consumes govern reading requests; Accept/produces govern response representations; codecs perform encode/decode. WebFlux's custom HandlerMethodArgumentResolver returns Mono<Object>, receives BindingContext and ServerWebExchange, and is registered via ArgumentResolverConfigurer. Use it to inject a clear request context type, while leaving simple type conversions and body reading to Converter/Formatter and HttpMessageReader.

## References

- Spring Framework — WebFlux Configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — RequestedContentTypeResolverBuilder API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/accept/RequestedContentTypeResolverBuilder.html
- Spring Framework — WebFluxConfigurer API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html
- Spring Framework — ArgumentResolverConfigurer API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ArgumentResolverConfigurer.html
- Spring Framework — WebFlux HandlerMethodArgumentResolver API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/HandlerMethodArgumentResolver.html
- Spring Framework — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — HTTP Message Codecs and Data Buffers: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
