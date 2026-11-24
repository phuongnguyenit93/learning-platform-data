# ServerWebExchange, Principal, and Locale in WebFlux Handler Parameters

## 1. Problem and Objectives

In Spring WebFlux, an HTTP handler method can directly accept many parameter types resolved by the framework from the current request. Three important parameters are:

- **ServerWebExchange**: provides the full context of one HTTP exchange, including request, response, attributes, session, principal, and locale context.
- **Principal**: represents the authenticated user identity if present. Resolution can be asynchronous; a reactive type such as **Mono<Principal>** helps compose that process into the pipeline.
- **Locale**: the current language/region of the request, usually determined from the **Accept-Language** header via **LocaleContextResolver**.

For example, an endpoint needs to return current user information, the request path, and the language to select appropriate content. We can declare all three right in the method signature:

~~~java
@GetMapping("/profile/context")
public Mono<ProfileContext> context(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale
) {
    return principal.map(user ->
        new ProfileContext(
            user.getName(),
            exchange.getRequest().getURI().getPath(),
            locale.toLanguageTag()
        )
    );
}
~~~

This is an illustrative snippet; the **ProfileContext** type is defined in the application. Spring automatically resolves supported parameters when invoking the handler. We do not need to obtain HttpServletRequest manually or use ThreadLocal.

After this lesson, you can:

- Distinguish ServerWebExchange from ServerHttpRequest and ServerHttpResponse.
- Read request, response, attributes, session, form data, and multipart reactively.
- Understand that Principal is resolved asynchronously, may be absent, and relates to Spring Security.
- Understand that Locale is selected via LocaleContextResolver and the Accept-Language header.
- Write proper controller signatures, combining parameters with Mono/Flux without blocking.
- Configure locale, secure endpoints with WebFlux Security, and test with WebTestClient.
- Avoid mistakes such as reading the body multiple times, using Spring MVC's LocaleResolver by mistake, or confusing Principal with client-sent data.

## 2. How Does Spring Resolve Handler Parameters?

In controllers using **@RequestMapping**, **@GetMapping**, **@PostMapping**, and related annotations, Spring WebFlux has a **HandlerMethodArgumentResolver** mechanism. This mechanism recognizes parameter types and annotations, then produces the corresponding values from **ServerWebExchange**.

Some directly relevant resolvers:

| Resolver | Supported parameters | How it works |
| --- | --- | --- |
| **ServerWebExchangeMethodArgumentResolver** | ServerWebExchange, ServerHttpRequest, ServerHttpResponse, HttpMethod, Locale, TimeZone, ZoneId, URI builder | Reads data directly from the exchange |
| **PrincipalMethodArgumentResolver** | java.security.Principal and compatible reactive wrappers | Retrieves principal from the exchange asynchronously |
| **RequestParamMethodArgumentResolver** | @RequestParam and compatible simple types | Converts query parameters to Java types |
| **RequestHeaderMethodArgumentResolver** | @RequestHeader | Reads headers and converts types |
| **RequestBodyMethodArgumentResolver** | @RequestBody | Uses HttpMessageReader/codec to read the body |
| **ModelAttributeMethodArgumentResolver** | @ModelAttribute or compatible objects | Binds request data into an object |

When the framework calls a handler, it resolves parameters first and then invokes the method. Thus the method signature is part of the HTTP contract; parameter types and annotations decide the data sources.

### 2.1. Which Parameters Are Direct Values and Which Should Be Reactive?

- **ServerWebExchange** is passed directly as an object.
- **ServerHttpRequest** and **ServerHttpResponse** are also passed directly.
- **Locale**, **TimeZone**, and **ZoneId** are synchronous values, resolved from the request context.
- **Principal** may need to wait for authentication or security context lookup; WebFlux supports reactive forms such as **Mono<Principal>**.
- Parameters reading body, session, or form data can use reactive types because resolution may involve I/O or parsing.

Do not wrap every parameter in Mono just because the controller is reactive. Use reactive wrappers where the API supports them and where the operation is genuinely asynchronous.

### 2.2. Combined Handler Signature Example

~~~java
@GetMapping("/request-info")
public Mono<Map<String, String>> requestInfo(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale,
    HttpMethod method
) {
    return principal.map(user -> Map.of(
        "user", user.getName(),
        "path", exchange.getRequest().getURI().getPath(),
        "method", method.name(),
        "locale", locale.toLanguageTag()
    ));
}
~~~

The parameter types here are resolved by the framework. The method returns **Mono** to wait for the principal before creating the response. Do not call **block()** to obtain the user in the handler.

## 3. What Is ServerWebExchange?

**ServerWebExchange** resides in package **org.springframework.web.server**. It represents an entire request/response exchange at the WebFlux layer, similar to a context object wrapping the request and response.

Some commonly used methods:

| Method | Result | Purpose |
| --- | --- | --- |
| **getRequest()** | ServerHttpRequest | Method, URI, headers, cookies, and body |
| **getResponse()** | ServerHttpResponse | Status, response headers, write body |
| **getAttributes()** | Map<String,Object> | Temporary data attached to the current request |
| **getAttribute(name)** | Value or null | Read a request attribute |
| **getAttributeOrDefault(name, defaultValue)** | Value or default | Safe read when the attribute may be absent |
| **getSession()** | Mono<WebSession> | Get session asynchronously |
| **getPrincipal()** | Mono<Principal> | Get the current user if present |
| **getLocaleContext()** | LocaleContext | Locale and possibly timezone |
| **getFormData()** | Mono<MultiValueMap<String,String>> | Parse form-urlencoded |
| **getMultipartData()** | Mono<MultiValueMap<String,Part>> | Parse multipart request |
| **checkNotModified(...)** | boolean | Handle conditional requests via ETag or last-modified |
| **mutate()** | ServerWebExchange.Builder | Create an exchange decorator with intentionally modified attributes |
| **getLogPrefix()** | String | Useful prefix to correlate exchange logs |

### 3.1. Reading Request and Response

~~~java
@GetMapping("/inspect")
public Mono<Map<String, String>> inspect(
    ServerWebExchange exchange
) {
    ServerHttpRequest request = exchange.getRequest();
    ServerHttpResponse response = exchange.getResponse();

    response.getHeaders().set("X-Handled-By", "webflux");

    return Mono.just(Map.of(
        "method", request.getMethod().name(),
        "path", request.getURI().getPath(),
        "host", request.getHeaders().getFirst("Host")
    ));
}
~~~

This is a snippet in a controller that has imported the Spring and Reactor types. You can read headers, method, and URI, and set response headers before the response is committed. **Do not store ServerWebExchange in a singleton field** to use after the request; this object belongs to the lifecycle of one exchange.

If only a few values are needed, using **ServerHttpRequest** or **ServerHttpResponse** directly as parameters can keep the method narrower and easier to test. Use ServerWebExchange when you genuinely need more capabilities or need access to both request and response.

### 3.2. Request Attributes

Attributes are a Map attached to the current exchange. They are useful when a WebFilter or earlier handler puts a temporary value for later layers to use:

~~~java
public static final String START_TIME = "app.startTime";

@GetMapping("/timing")
public Mono<String> timing(ServerWebExchange exchange) {
    Long started = exchange.getAttribute(START_TIME);

    if (started == null) {
        return Mono.just("start time unavailable");
    }

    long elapsedMillis =
        (System.nanoTime() - started) / 1_000_000;

    return Mono.just("elapsed=" + elapsedMillis + "ms");
}
~~~

This is a snippet; WebFilter must set the attribute before calling the filter chain. Attributes are scoped only to the exchange, not a shared cache across requests. Avoid storing large objects or unnecessary sensitive data.

Filter example:

~~~java
@Component
public class RequestTimingFilter implements WebFilter {
    public static final String START_TIME = "app.startTime";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        exchange.getAttributes().put(
            START_TIME,
            System.nanoTime()
        );

        return chain.filter(exchange);
    }
}
~~~

The filter and handler share a centralized key to avoid typos. Because the attribute Map is mutable, do not use it as a synchronization mechanism across multiple threads or requests.

### 3.3. Session Is Reactive and Does Not Create a Session Just by Calling getSession

**getSession()** returns **Mono<WebSession>**. Getting the session does not immediately write a new session to a cookie or session store. A session only needs to be saved when there are changes to persist, such as adding an attribute.

~~~java
@GetMapping("/session/visit")
public Mono<String> visit(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> {
            Integer count = session.getAttribute("visits");
            int next = count == null ? 1 : count + 1;
            session.getAttributes().put("visits", next);
            return "visits=" + next;
        });
}
~~~

This is an illustrative snippet; **WebSession.getAttribute** and **getAttributes** are used to read/write the session. Updating the session must stay inside the reactive pipeline. Do not call **subscribe()** manually and do not block to wait for the session.

If multiple concurrent requests update the same session, consider consistency and racing updates. A session is not a general-purpose transactional store; do not use it as a place to keep large business state.

### 3.4. Reading Form Data

For Content-Type **application/x-www-form-urlencoded**, the exchange provides:

~~~java
@PostMapping("/form")
public Mono<String> form(ServerWebExchange exchange) {
    return exchange.getFormData()
        .map(data -> {
            String name = data.getFirst("name");
            return "name=" + (name == null ? "" : name);
        });
}
~~~

**getFormData()** returns a Mono of MultiValueMap. The framework parses the whole form body and caches the result in the exchange; thus you can call this method multiple times without re-reading the original body. However, parsing still has memory/codec limits and large forms should not be treated as unbounded.

### 3.5. Reading Multipart Data

For **multipart/form-data**, the API:

~~~java
@PostMapping("/upload-info")
public Mono<String> uploadInfo(ServerWebExchange exchange) {
    return exchange.getMultipartData()
        .map(parts -> "partCount=" + parts.size());
}
~~~

**getMultipartData()** parses the request into a MultiValueMap and caches the map. However, the content of each **Part** is not cached in the same way; a part's body can only be read once per contract. If you need to process large files via streaming, consider **Flux<PartEvent>** or the corresponding streaming API instead of collecting all parts into a map.

Do not read the request body multiple times through different paths without understanding how codecs consume the body. A body already read by a resolver or filter may no longer be available for an independent consumer.

## 4. Principal in Handler Methods

**java.security.Principal** is the standard Java interface describing the identity of an identified entity. In WebFlux, Principal represents the current user if the request has been authenticated by the server or security infrastructure.

API on exchange:

~~~java
Mono<Principal> principal = exchange.getPrincipal();
~~~

API in handler signature:

~~~java
@GetMapping("/me")
public Mono<String> me(Mono<Principal> principal) {
    return principal
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
}
~~~

**PrincipalMethodArgumentResolver** resolves Principal asynchronously. In the method signature, **Mono<Principal>** allows composing directly with the pipeline without blocking threads.

### 4.1. Why Can Principal Be Absent?

Not every request is authenticated. If the application has no authentication or there is no principal for the request, the Publisher can complete empty. Therefore:

~~~java
return principal
    .map(Principal::getName)
    .defaultIfEmpty("anonymous");
~~~

is used when the endpoint genuinely allows anonymous access. If the endpoint requires authentication, configure authorization to reject unauthenticated requests instead of assigning a fake identity yourself.

**Be careful with anonymous authentication:** when Spring Security enables its anonymous mechanism, unauthenticated requests can have an Authentication representing an anonymous user. In that case the principal value can be a name such as **anonymousUser** depending on configuration. Do not assume every unauthenticated case is Mono.empty().

### 4.2. Principal Differs from Authentication and UserDetails

- **Principal** is a simple Java abstraction, usually needing only **getName()**.
- Spring Security's **Authentication** describes authentication state, principal, credentials, and authorities.
- **UserDetails** is a user-information model used by some authentication mechanisms.
- Spring Security's **@AuthenticationPrincipal** can be used when you need to obtain the principal in an application-specific type rather than just java.security.Principal.

An authenticated Authentication usually implements Principal, but not every Principal is an Authentication. Do not cast Principal to Authentication without checking the type and contract.

Example needing only the username:

~~~java
@GetMapping("/username")
public Mono<String> username(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
~~~

If you need authorities or authentication state, use the appropriate Spring Security API instead of trying to extract everything from getName().

### 4.3. Where Does Principal Come From in Spring Security WebFlux?

Spring Security reactive uses **WebFilter** and **Reactor Context** to maintain SecurityContext across the reactive chain. When a request is authenticated, the security filter chain puts Authentication into the reactive security context; WebFlux can resolve Principal for the handler.

At the service layer, if you do not want to add Principal to every method signature, you can access the security context via **ReactiveSecurityContextHolder**:

~~~java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

This snippet requires Spring Security WebFlux and the corresponding imports. It must be used inside a reactive Publisher so that the Context is preserved. Do not use **SecurityContextHolder** in the imperative ThreadLocal style inside a reactive pipeline as if the thread will never change.

### 4.4. Do Not Take Principal from Self-Declared Headers

Headers such as **X-User**, **X-Principal**, or query parameter **user=alice** are only data sent by the client. They do not prove the sender is alice. Only use an identity already authenticated by Spring Security, a trusted gateway with a clear contract, or a suitable authentication mechanism.

Correlation ID and Principal also serve different purposes: a correlation ID ties logs/requests together; Principal represents an authenticated identity. Do not use one in place of the other.

## 5. Locale and LocaleContext

**java.util.Locale** describes language, country/region, and related formatting conventions. For example:

- **vi-VN**: Vietnamese in Vietnam.
- **en-US**: English according to United States conventions.
- **en-GB**: English according to United Kingdom conventions.
- **ja-JP**: Japanese in Japan.

In WebFlux, a handler can directly receive:

~~~java
@GetMapping("/language")
public String language(Locale locale) {
    return locale.toLanguageTag();
}
~~~

Locale is a synchronous parameter; **Mono<Locale>** is not needed. It is resolved through the **LocaleContextResolver** configured for the application.

### 5.1. AcceptHeaderLocaleContextResolver

In a typical WebFlux configuration, the default resolver is **AcceptHeaderLocaleContextResolver**. It inspects the HTTP header:

~~~http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8
~~~

The resolver matches the locale requested by the client against the list of **supported locales** configured by the application. If there is no match, the resolver uses the default locale if configured; otherwise, it may use the first requested locale according to the resolver's rules.

Important: simply sending **Accept-Language** does not mean the application translates content automatically. Locale only provides context; the controller/service needs to use MessageSource, resource bundles, or i18n logic to choose messages.

### 5.2. Configuring Supported Locales

~~~java
@Configuration
public class LocaleConfiguration {

    @Bean
    public LocaleContextResolver localeContextResolver() {
        AcceptHeaderLocaleContextResolver resolver =
            new AcceptHeaderLocaleContextResolver();

        resolver.setSupportedLocales(List.of(
            Locale.ENGLISH,
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("ja-JP")
        ));

        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }
}
~~~

This configuration restricts the locales the application actively supports and chooses English when there is no match. If you want to accept a language-code-only locale such as **vi**, add **Locale.forLanguageTag("vi")** to the supported locales list. The resolver matches language and country according to its rules; do not assume vi-VN automatically matches every vi-* variant.

### 5.3. Reading LocaleContext and Timezone

**exchange.getLocaleContext()** returns the current LocaleContext. If the resolver provides a **TimeZoneAwareLocaleContext**, you can also obtain the timezone:

~~~java
LocaleContext context = exchange.getLocaleContext();
Locale locale = context.getLocale();

TimeZone timeZone = null;
if (context instanceof TimeZoneAwareLocaleContext aware) {
    timeZone = aware.getTimeZone();
}
~~~

This is a Java 17 snippet. LocaleContext may not contain a timezone; check before accessing. In handler signatures, WebFlux also supports **TimeZone** and **ZoneId** when a suitable resolver is present.

Locale and timezone are two separate concepts: locale affects language/formatting, while timezone affects how instants in time are interpreted. Do not use Locale to rigidly infer a timezone.

### 5.4. Using Locale with MessageSource

In Spring, you can use **MessageSource** to retrieve localized messages:

~~~java
@Service
public class GreetingService {
    private final MessageSource messages;

    public GreetingService(MessageSource messages) {
        this.messages = messages;
    }

    public String greeting(Locale locale) {
        return messages.getMessage(
            "greeting",
            null,
            "Hello",
            locale
        );
    }
}
~~~

Resource file example:

~~~properties
# messages.properties
greeting=Hello

# messages_vi.properties
greeting=Hello

# messages_ja.properties
greeting=こんにちは
~~~

In Spring Boot's default configuration, resource bundles can be discovered under the name messages; depending on the project, configure the basename if using a different location/name. The controller can receive Locale and pass it to the service, or the service can receive locale as an explicit parameter for easier testing.

**Do not rely on the JVM's Locale.getDefault()** if you want to reflect each request's language. The JVM locale is a process configuration; the Locale determined by the resolver is the context of the current request.

## 6. Combining ServerWebExchange, Principal, and Locale

A handler can use all three parameters in different roles:

~~~java
@RestController
@RequestMapping("/api")
public class RequestContextController {

    @GetMapping("/context")
    public Mono<Map<String, String>> context(
        ServerWebExchange exchange,
        Mono<Principal> principal,
        Locale locale
    ) {
        return principal.map(user -> Map.of(
            "username", user.getName(),
            "method", exchange.getRequest().getMethod().name(),
            "path", exchange.getRequest().getURI().getPath(),
            "language", locale.toLanguageTag()
        ));
    }
}
~~~

- **ServerWebExchange** provides request and response information.
- **Mono<Principal>** lets you await the current identity.
- **Locale** provides language/region to select content.
- **Mono<Map<...>>** is the result emitted after the principal is resolved.

If the endpoint allows anonymous access:

~~~java
@GetMapping("/public-context")
public Mono<Map<String, String>> publicContext(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale
) {
    return principal
        .map(Principal::getName)
        .defaultIfEmpty("anonymous")
        .map(name -> Map.of(
            "user", name,
            "path", exchange.getRequest().getURI().getPath(),
            "language", locale.toLanguageTag()
        ));
}
~~~

This is a snippet; if the Spring Security anonymous filter provides an anonymous Authentication, the name may be anonymousUser instead of the fallback string. If the API needs a single format, normalize the principal name per application policy.

### 6.1. Take Only What You Need

If the method needs only the username, accepting **Mono<Principal>** is enough. If it needs only the path, accept **ServerHttpRequest** or use **@PathVariable**. If it needs only Locale, accept Locale directly.

Do not accept ServerWebExchange in every controller method out of habit. A narrow signature makes the code easier to understand and unit test, and reduces the risk of the handler depending too heavily on HTTP details.

### 6.2. Capture Request Values Before Long Processing

If you need to pass metadata down to the service, you can read it once and compose:

~~~java
public Mono<LocalizedProfile> profile(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale
) {
    String path = exchange.getRequest().getURI().getPath();

    return principal.flatMap(user ->
        profileService.find(user.getName())
            .map(profile ->
                new LocalizedProfile(
                    profile.id(),
                    user.getName(),
                    locale.toLanguageTag(),
                    path
                )
            )
    );
}
~~~

The **Profile**, **LocalizedProfile**, and service types are application components. Obtaining the path and locale is synchronous; obtaining the Principal and profile remains in the reactive chain. There is no need for ThreadLocal to hold these values.

## 7. Runnable Java 17+ App with Spring Boot and WebFlux Security

The following complete example has an endpoint protected by HTTP Basic. It illustrates:

- **ServerWebExchange** reading method/path.
- **Mono<Principal>** retrieving the authenticated username.
- **Locale** received per Accept-Language.
- **LocaleContextResolver** restricting supported locales.
- **WebFlux Security** putting authentication into the reactive request context.
- **WebTestClient** verifying the response.

Structure:

~~~text
handler-arguments-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/handlerargs/
    │   │       ├── HandlerArgumentsApplication.java
    │   │       ├── RequestContextController.java
    │   │       ├── SecurityConfiguration.java
    │   │       └── LocaleConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/handlerargs/
                └── RequestContextControllerTest.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>handler-arguments-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

Spring Boot manages compatible versions of Spring Framework, Spring Security, and Reactor. Do not add spring-boot-starter-web for this pure WebFlux example.

### 7.2. Application Class

File **HandlerArgumentsApplication.java**:

~~~java
package com.example.handlerargs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HandlerArgumentsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            HandlerArgumentsApplication.class,
            args
        );
    }
}
~~~

### 7.3. Controller Accepting Three Parameters

File **RequestContextController.java**:

~~~java
package com.example.handlerargs;

import java.security.Principal;
import java.util.Locale;
import java.util.Map;

import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class RequestContextController {

    public record RequestInfo(
        String principal,
        String method,
        String path,
        String locale
    ) {}

    @GetMapping("/request-info")
    public Mono<RequestInfo> requestInfo(
        ServerWebExchange exchange,
        Mono<Principal> principal,
        Locale locale
    ) {
        HttpMethod method = exchange.getRequest().getMethod();

        return principal.map(user ->
            new RequestInfo(
                user.getName(),
                method.name(),
                exchange.getRequest().getURI().getPath(),
                locale.toLanguageTag()
            )
        );
    }
}
~~~

The endpoint requires a principal because the security configuration in the next section protects every request. If you remove the authentication requirement, decide clearly how to handle Mono.empty or an anonymous principal.

### 7.4. SecurityConfiguration

File **SecurityConfiguration.java**:

~~~java
package com.example.handlerargs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.web.server.ServerHttpSecurity;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http
    ) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges ->
                exchanges.anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}secret")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
~~~

**{noop}secret is only for local learning examples.** It does not encrypt passwords and is unsuitable for real environments. Production must use an appropriate PasswordEncoder, a secure user store, HTTPS, and proper authentication/authorization policies.

### 7.5. LocaleConfiguration

File **LocaleConfiguration.java**:

~~~java
package com.example.handlerargs;

import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.i18n.AcceptHeaderLocaleContextResolver;
import org.springframework.web.server.i18n.LocaleContextResolver;

@Configuration
public class LocaleConfiguration {

    @Bean
    LocaleContextResolver localeContextResolver() {
        AcceptHeaderLocaleContextResolver resolver =
            new AcceptHeaderLocaleContextResolver();

        resolver.setSupportedLocales(List.of(
            Locale.ENGLISH,
            Locale.forLanguageTag("vi-VN")
        ));
        resolver.setDefaultLocale(Locale.ENGLISH);

        return resolver;
    }
}
~~~

This resolver accepts English and Vietnamese (Vietnam). When the client sends **Accept-Language: vi-VN**, the resolved locale is vi-VN. If the header is missing or no supported locale matches, the default locale is English.

### 7.6. application.properties

~~~properties
spring.application.name=handler-arguments-demo
server.port=8080
logging.level.com.example.handlerargs=INFO
~~~

### 7.7. Testing with WebTestClient

File **RequestContextControllerTest.java**:

~~~java
package com.example.handlerargs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class RequestContextControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void resolvesExchangePrincipalAndLocale() {
        client.get()
            .uri("/api/request-info")
            .headers(headers ->
                headers.setBasicAuth("alice", "secret")
            )
            .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.principal").isEqualTo("alice")
            .jsonPath("$.method").isEqualTo("GET")
            .jsonPath("$.path").isEqualTo("/api/request-info")
            .jsonPath("$.locale").isEqualTo("vi-VN");
    }

    @Test
    void rejectsRequestWithoutAuthentication() {
        client.get()
            .uri("/api/request-info")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

The test uses HTTP Basic to authenticate and sends a specific Accept-Language. Spring Boot runs the server on a random port so there is no need to depend on port 8080 in tests.

### 7.8. Running the Application

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Call the endpoint with the demo user:

~~~bash
curl -i -u alice:secret \
  -H "Accept-Language: vi-VN" \
  http://localhost:8080/api/request-info
~~~

Expected response body:

~~~json
{
  "principal": "alice",
  "method": "GET",
  "path": "/api/request-info",
  "locale": "vi-VN"
}
~~~

Without sending credentials, the endpoint returns **401 Unauthorized** per the security chain in the example.

Note: the response body above is formatted for illustration; JSON field order or whitespace is not a contract. The principal, method, path, and locale values are what need to be checked.

## 8. Using Principal at the Service Layer

If a service is called from multiple controllers and needs to know the current user, there are two common approaches.

### Approach 1: Pass Principal or Username Explicitly

~~~java
public Mono<Account> findAccount(
    String accountId,
    String username
) {
    return repository.findVisibleTo(accountId, username);
}
~~~

This makes dependencies clear and easy to unit test. The controller reads the principal and passes the username to the service.

### Approach 2: Read ReactiveSecurityContextHolder in the Pipeline

~~~java
public Mono<Account> currentAccount(String accountId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(username ->
            repository.findVisibleTo(accountId, username)
        );
}
~~~

This fits when the service needs the security context from a reactive subscription without passing extra parameters through many layers. The service must return a reactive Publisher so the security context is preserved.

**Do not use SecurityContextHolder.getContext() in the imperative style** to read authentication in WebFlux. The reactive security context is bound to the Reactor Context and is not guaranteed to stay on the same thread.

## 9. Locale in Business Logic and Formatting

### 9.1. Locale Affects Display, Not Original Data

For example, the number **1234.56** may be displayed differently by locale; dates may also use different orders. Do not store formatted strings as raw data. Store numbers, instants, and currencies using appropriate types, then format them at the presentation layer by locale.

Example:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);
String display = format.format(1234.56);
~~~

This is a Java snippet using **java.text.NumberFormat**. Locale does not automatically determine the currency for every business domain; currency requires an ISO code and its own business rules.

### 9.2. Request Locale and JVM Locale Differ

- **Request locale** is determined by the resolver from headers or application configuration.
- **Locale.getDefault()** is the default locale of the JVM/process.
- **LocaleContextHolder** is a mechanism that binds LocaleContext to a thread in some integrations; it does not automatically replace passing Locale in a reactive pipeline unless context propagation is configured.

Prefer receiving Locale from the handler or passing it explicitly to services that need formatting. Do not set a mutable static Locale per request, because multiple requests can run concurrently with different languages.

### 9.3. Testing Multiple Locales

You should have tests for:

- Accept-Language matching a supported locale.
- Missing header.
- Header containing an unsupported locale.
- Header with multiple locales and quality values.
- Language-only locale when the application supports only language-country.
- Configured default locale.

Do not assume **vi** and **vi-VN** are always equivalent in the supported locales list. If you need to support both, declare both or build a resolver according to the application's policy.

## 10. Common Mistakes

| Symptom / misconception | Explanation and fix |
| --- | --- |
| Using HttpServletRequest in WebFlux | That is a Servlet API. Use **ServerWebExchange** or **ServerHttpRequest**. |
| Wrapping ServerWebExchange in Mono | Unnecessary. Exchange is a direct parameter; async operations such as getSession return Mono. |
| Calling principal.block() in a controller | Blocks the thread and breaks the reactive model. Use **Mono<Principal>** then map/flatMap. |
| Assuming every request has a Principal | There may be unauthenticated requests or anonymous configuration. Secure the endpoint or handle empty/anonymous explicitly. |
| Trusting header X-User as identity | A client-sent header is not authentication. Use Spring Security or a trusted identity provider. |
| Casting Principal to Authentication | Not every Principal is an Authentication. Check the contract or use the appropriate Spring Security API. |
| Reading SecurityContextHolder like MVC | WebFlux uses **ReactiveSecurityContextHolder** and Reactor Context. |
| Using Locale.getDefault() to choose per-request language | That is the JVM locale. Accept **Locale** from the handler or LocaleContextResolver. |
| Using Spring MVC's LocaleResolver | WebFlux uses **LocaleContextResolver** in package web.server.i18n. |
| Sending Accept-Language without configuring translated content | The resolver only supplies the locale; MessageSource/resource bundles are needed to translate. |
| Supporting only vi-VN and expecting vi to match automatically | Matching rules depend on supported locales; declare a language-only locale if needed. |
| Calling getFormData then re-reading the raw body as if never consumed | Form parsing reads the body and caches the map; design one clear reading path. |
| Assuming multipart content is cached completely | The parts map is cached, but each part's content may only be read once. |
| Keeping ServerWebExchange in a singleton | Exchange belongs to one request; keeping a reference can cause data leaks and concurrency bugs. |
| Writing an attribute to share across requests | Attributes belong only to the current exchange. Use a controlled shared store if genuinely needed. |
| Creating a session just to read data | getSession does not save a session if there are no changes; consider whether a session is truly needed. |
| Subscribing manually when handling session/principal | Detaches the task from the request pipeline; compose the Publisher and return it. |
| Using Locale to infer timezone | Locale and timezone differ; use TimeZone/ZoneId or an appropriate LocaleContext. |

## 11. Handler Method Design Checklist

Before adding parameters, ask yourself:

1. Do you need the whole exchange or just request/response?
2. Do you need to read request attributes/session?
3. Is Principal always present, and does the endpoint require authentication?
4. Do you need Mono<Principal> to compose asynchronously?
5. Is Locale taken from Accept-Language or from a custom resolver?
6. Are supported locales and the default locale defined?
7. Do you need a separate TimeZone/ZoneId in addition to Locale?
8. Are form/multipart bodies read once and within limits?
9. Should the service receive data explicitly or use ReactiveSecurityContextHolder?
10. Are you using an unsuitable Servlet API or ThreadLocal in WebFlux?
11. Are there tests for authenticated/unauthenticated and multiple locales?
12. Do logs avoid exposing sensitive data or credentials?

## 12. Hands-On Exercises

**Exercise 1 — Reading the exchange:** Create GET /api/inspect accepting ServerWebExchange and returning method, path, host, and Accept-Language. Test requests with and without the header.

**Exercise 2 — Principal:** Create endpoint GET /api/me accepting Mono<Principal>. Protect the endpoint with HTTP Basic; call with a valid user and without credentials. Observe 200 and 401.

**Exercise 3 — Anonymous:** Allow a public endpoint. Handle Mono<Principal> empty or anonymous Authentication according to the configuration. Never treat a header as identity.

**Exercise 4 — Locale:** Configure AcceptHeaderLocaleContextResolver to support only en and vi-VN, default English. Try Accept-Language: vi-VN, en-US, and fr-FR.

**Exercise 5 — MessageSource:** Create messages.properties and messages_vi.properties, pass Locale into MessageSource to return a greeting in the right language.

**Exercise 6 — Session:** Create an endpoint incrementing a counter in WebSession. Send multiple requests with the same session cookie and observe the value. Check behavior when deleting the cookie.

**Exercise 7 — Form data:** Send application/x-www-form-urlencoded and read exchange.getFormData(). Check missing values and multiple values for the same key.

**Exercise 8 — Multipart:** Receive a multipart form with a file. Compare getMultipartData with handling streaming PartEvent; pay attention to lifecycle and reading part content.

**Exercise 9 — Service security:** Write a service using ReactiveSecurityContextHolder and compare it with having the controller pass the username into the service. Choose the approach that is easier to test and has a clearer contract.

**Exercise 10 — WebTestClient:** Write tests for authentication, path, method, locale, and missing credentials. Tests should not depend on a fixed port or JSON field order.

## 13. Key Takeaways

**ServerWebExchange** is the complete context of one request/response; **Principal** is the authenticated identity if present and should be composed reactively; **Locale** is the language/region context resolved from the request configuration, usually via Accept-Language.

In handler methods, use **ServerWebExchange** when you need the whole request/response or session/attributes, **Mono<Principal>** when you need an asynchronous identity, and **Locale** directly to handle multilingual content. Keep values within the request lifecycle, do not block, do not trust client-sent identity data, and test both missing-principal and missing-locale cases.

## 14. References

- Spring Framework Reference — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework 6.1 API — ServerWebExchange: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.1 API — PrincipalMethodArgumentResolver: https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/web/reactive/result/method/annotation/PrincipalMethodArgumentResolver.html
- Spring Framework 6.1 API — AcceptHeaderLocaleContextResolver: https://docs.spring.io/spring-framework/docs/6.1.0-M1/javadoc-api/org/springframework/web/server/i18n/AcceptHeaderLocaleContextResolver.html
- Spring Framework Reference — WebFlux Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Reference — Reactive Method Security and ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Framework Reference — MessageSource and Internationalization: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
