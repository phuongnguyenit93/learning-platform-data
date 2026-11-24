# WebClient: `retrieve()`, `onStatus()`, `exchangeToMono()`, and `exchangeToFlux()`

## 1. Goals and Context

`WebClient` is the HTTP client in Spring WebFlux, built on Reactor (`Mono`/`Flux`). It can be used in both Spring WebFlux and Spring MVC applications. The four methods in this lesson answer two different questions:

1. **Who decides how to handle the HTTP status?** `retrieve()` provides standard handling (by default turning HTTP 4xx/5xx into errors), `onStatus()` customizes those rules; `exchangeToMono()` and `exchangeToFlux()` pass the entire `ClientResponse` to your function so you can branch yourself.
2. **How many elements does the result have?** `Mono<T>` has at most one element (or empty/error); `Flux<T>` has 0..N elements (or error). Choose based on the data protocol and processing needs, not on whether the endpoint is GET or POST.

Typical processing flow:

```text
WebClient.get()/post() → uri()/headers() → send HTTP on subscribe
                                           ├─ retrieve()
                                           │    ├─ optional onStatus(...)
                                           │    └─ bodyToMono / bodyToFlux / toEntity...
                                           ├─ exchangeToMono(response -> Mono<T>)
                                           └─ exchangeToFlux(response -> Flux<T>)
```

Foundational point: `Mono`/`Flux` are *lazy* pipelines: simply building the pipeline does not send a request yet; the request executes when subscribed to (for example, by the framework or in a CLI example via `block()`). Do not call `block()` on a WebFlux non-blocking/event-loop thread.

## 2. `retrieve()`: The Standard Path for Common Responses

`retrieve()` returns `WebClient.ResponseSpec` to choose how to extract the content. Use it when you want normal response decoding while accepting the default status rules.

```java
record Product(long id, String name) {}

WebClient client = WebClient.create("https://api.example.com");

Mono<Product> one = client.get()
    .uri("/products/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(Product.class);

Flux<Product> many = client.get()
    .uri("/products")
    .retrieve()
    .bodyToFlux(Product.class);

Mono<ResponseEntity<Product>> withMetadata = client.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .toEntity(Product.class);
```

These snippets are **illustrative**: they require importing WebClient, MediaType, Reactor, and ResponseEntity, and a real server at the example URL. `bodyToMono(Product.class)` reads one object; `bodyToFlux(Product.class)` reads multiple objects, such as a JSON array or a stream format with an appropriate decoder. `toEntity(Product.class)` preserves HTTP status/headers alongside the body; this is how to obtain metadata while still using `retrieve()`.

**Default HTTP errors:** if no matching handler exists, statuses 400 and above are mapped to `WebClientResponseException` (including appropriate subclasses, such as NotFound). The exception contains the status, headers, and possibly the error body. HTTP success does not guarantee JSON decoding succeeds: an invalid body or mismatched content type can still raise codec errors. DNS, connection, or timeout failures belong to another category (`WebClientRequestException` or corresponding cause); `onStatus()` applies only to responses that received an HTTP status.

`retrieve()` does not expose `ClientResponse` directly for reading the body twice. When you need to select a decoder by status or content-type with custom logic, look at `exchangeToMono()` / `exchangeToFlux()`.

## 3. `onStatus()`: Mapping HTTP Statuses to Business Errors

`onStatus(Predicate<HttpStatusCode>, Function<ClientResponse, Mono<? extends Throwable>>)` is called **after `retrieve()`, before reading the body**. The predicate selects the status; the second function returns a publisher producing the exception to emit downstream.

```java
Mono<Product> product = client.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("No error description")
            .map(message -> new ProductNotFoundException(message))
    )
    .onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.createException()
    )
    .bodyToMono(Product.class);
```

Here `ProductNotFoundException` is an application-defined business exception class (the snippet is not a standalone program). Import `org.springframework.http.HttpStatusCode`. The handler reads the 404 body as a string and constructs the exception; when there is no body, `defaultIfEmpty` ensures an error is still emitted. `response.createException()` creates a `Mono<WebClientResponseException>` from the status/headers/body. The 5xx example illustrates preserving the original HTTP details; if you do not need to change that behavior, you can omit the 5xx handler since the default already handles it.

Three easily confused options:

- Returning `Mono.just(new MyException(...))` or a `Mono` emitting a `Throwable` → `retrieve()` turns it into an **error signal**.
- Returning `Mono.empty()` from the **`onStatus` function** → *skips treating that status as an error*, letting the response continue through the body decoder. This does **not** ignore the response, nor does it turn 404 into an empty body.
- Calling `onErrorResume(...)` **after** `bodyToMono(...)` → decides how to recover from an already emitted error, such as falling back to a default value; it can catch status, connection, or decoding errors depending on the exception type matched.

```java
Mono<String> displayName = client.get()
    .uri("/profiles/{id}", 42)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> response.bodyToMono(String.class)
            .map(message -> new IllegalArgumentException("Profile absent: " + message))
    )
    .bodyToMono(String.class)
    .onErrorResume(IllegalArgumentException.class, error -> Mono.just("Anonymous guest"));
```

**Handler order matters:** when multiple predicates match, the first matching handler is applied. Place specific rules (e.g., 404) before general ones (4xx). Note the API also offers `onRawStatus(IntPredicate, ...)` if you need to handle custom numeric codes.

## 4. `exchangeToMono()`: Deciding from `ClientResponse`, Returning One Result

`exchangeToMono(response -> Mono<T>)` gives direct access to status and headers, then chooses how to decode or error. This is the right choice when *different statuses may carry different body schemas*, or the application wants to treat 404 as a valid outcome.

```java
Mono<Optional<Product>> result = client.get()
    .uri("/products/{id}", 42)
    .exchangeToMono(response -> {
        int status = response.statusCode().value();
        if (status == 404) {
            return Mono.just(Optional.<Product>empty());
        }
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Product.class).map(Optional::of);
        }
        return response.createException()
            .flatMap(error -> Mono.error(error));
    });
```

This is an **illustrative snippet** requiring `Optional` to be imported; the 404 body is intentionally unread because it is not needed. The return type of every branch must align to `Mono<Optional<Product>>`. For a 2xx response with an empty body, the example branch emits `Mono.empty()` (no Optional); if business logic requires `Optional.empty()`, add `.defaultIfEmpty(Optional.empty())` after the body branch.

Key differences:

- **There is no `onStatus()` mechanism here**: 404/500 statuses are **not automatically converted into errors** as with `retrieve()`. The callback is fully responsible for every status the application cares about.
- To preserve the original HTTP error, use `response.createException()` or `response.createError()` instead of silently decoding an error body into a success object.
- You must **decode/consume the body inside the callback** if needed. Once the `Mono` returned by the callback completes, any unused body is checked and released by Spring; you cannot store `ClientResponse` to decode the body later downstream. Do not attempt to read the same body twice.
- You can inspect `response.headers().contentType()` and branch decoders by content type if an endpoint returns multiple body formats; remember to handle the case where the header is absent.

## 5. `exchangeToFlux()`: Deciding from `ClientResponse`, Returning a Multi-Element Stream

`exchangeToFlux(response -> Flux<T>)` is similar to `exchangeToMono` except the callback returns `Flux<T>`. Choose it when you need a sequence of multiple items, such as a product list or event stream. This is not necessarily network streaming: a JSON array can also be decoded into `Flux<Product>`; incremental chunk-by-chunk delivery requires the server to provide an appropriate format/transport (SSE, NDJSON, etc.).

```java
Flux<Product> products = client.get()
    .uri("/products")
    .accept(MediaType.APPLICATION_JSON)
    .exchangeToFlux(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToFlux(Product.class);
        }
        if (response.statusCode().value() == 404) {
            return Flux.empty();
        }
        return response.createException()
            .flatMapMany(error -> Flux.error(error));
    });
```

`Flux.empty()` in the 404 branch explicitly expresses a business decision: a non-existent list is treated as having zero elements. In many APIs, 404 must be treated as an error; do not automatically turn every 404 into an empty list.

If decoding directly with `retrieve().bodyToFlux(Product.class)` is enough, you **do not need** `exchangeToFlux()`. Just like `exchangeToMono`, the body is only available within the callback's lifecycle.

## 6. Standalone Runnable Example, Mocked Responses Without an HTTP Server

The example below uses `ExchangeFunction` to simulate four HTTP responses. Thus it can run and verify outputs without calling the internet. It uses Java 17+, Gradle, and Spring Boot Starter WebFlux 3.3.13; JSON data is decoded by Jackson into Java `record` types. Structure:

```text
webclient-status-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/WebClientStatusDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'webclient-status-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
}

application {
    mainClass = 'demo.WebClientStatusDemo'
}
```

**`src/main/java/demo/WebClientStatusDemo.java`**

```java
package demo;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class WebClientStatusDemo {
    public record Book(int id, String name) {}

    private static ClientResponse json(String body) {
        return ClientResponse.create(HttpStatus.OK)
            .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .body(body)
            .build();
    }

    public static void main(String[] args) {
        ExchangeFunction fakeHttp = request -> {
            ClientResponse response = switch (request.url().getPath()) {
                case "/book" -> json("{\"id\":7,\"name\":\"Lan\"}");
                case "/books" -> json(
                    "[{\"id\":7,\"name\":\"Lan\"},{\"id\":8,\"name\":\"Minh\"}]");
                case "/missing" -> ClientResponse.create(HttpStatus.NOT_FOUND)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_PLAIN_VALUE)
                    .body("missing book")
                    .build();
                default -> ClientResponse.create(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("unexpected route")
                    .build();
            };
            return Mono.just(response);
        };

        WebClient client = WebClient.builder()
            .exchangeFunction(fakeHttp)
            .build();

        Book book = client.get().uri("/book")
            .retrieve()
            .bodyToMono(Book.class)
            .block();
        System.out.println("retrieve: " + book);

        String statusResult = client.get().uri("/missing")
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(String.class)
                    .map(msg -> new IllegalStateException("HTTP 404: " + msg))
            )
            .bodyToMono(Book.class)
            .map(Book::name)
            .onErrorResume(IllegalStateException.class,
                error -> Mono.just(error.getMessage()))
            .block();
        System.out.println("onStatus: " + statusResult);

        String notFound = client.get().uri("/missing")
            .exchangeToMono(response -> {
                if (response.statusCode().value() == 404) {
                    return Mono.just("Not found");
                }
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(String.class);
                }
                return response.createException()
                    .flatMap(error -> Mono.error(error));
            })
            .block();
        System.out.println("exchangeToMono: " + notFound);

        List<Book> books = client.get().uri("/books")
            .exchangeToFlux(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToFlux(Book.class);
                }
                return response.createException()
                    .flatMapMany(error -> Flux.error(error));
            })
            .collectList()
            .block();
        System.out.println("exchangeToFlux: " + books);
    }
}
```

Run from the project directory with JDK 17+ and Gradle installed (or replace `gradle` with `./gradlew` if a Gradle Wrapper is present):

```bash
gradle run --quiet
```

**Lines printed by the program** (libraries may print extra logs in some environments):

```text
retrieve: Book[id=7, name=Lan]
onStatus: HTTP 404: missing book
exchangeToMono: Not found
exchangeToFlux: [Book[id=7, name=Lan], Book[id=8, name=Minh]]
```

Explanation: the `/book` response has a JSON object so `bodyToMono` emits one `Book`. `/missing` on the `retrieve()` path is converted by `onStatus` into `IllegalStateException` and `onErrorResume` turns that error into a message; the same 404 code is intentionally treated by `exchangeToMono` as the result "Not found". `/books` contains a JSON array, `bodyToFlux` decodes two items, and `collectList()` gathers them into `List<Book>`. `block()` is used only for easy observation in a CLI-style `main` method.

## 7. Quick Selection Table

| Need | Suitable API | Who handles status? | Typical result type |
| --- | --- | --- | --- |
| Read JSON object, accept default 4xx/5xx as errors | `retrieve().bodyToMono(...)` | Spring default | `Mono<T>` |
| Read list/stream, default status | `retrieve().bodyToFlux(...)` | Spring default | `Flux<T>` |
| Map 404/422/5xx to business exceptions | `retrieve().onStatus(...).bodyToMono/Flux(...)` | Spring + custom handler | `Mono<T>` or `Flux<T>` |
| Turn 404 into empty Optional; decode 200 with separate schema | `exchangeToMono(...)` | Callback itself | `Mono<T>` |
| Return 0..N items by status/content type | `exchangeToFlux(...)` | Callback itself | `Flux<T>` |

Rule of thumb: **start with `retrieve()`**, and add `onStatus()` when you only need to customize errors. Choose `exchangeToMono()`/`exchangeToFlux()` when business logic must control the entire interpretation of the response.

## 8. Common Errors and How to Avoid Them

1. **Assuming `onStatus` works after `exchangeToMono`.** `onStatus` is a method on `ResponseSpec` returned by `retrieve`; in the `exchangeTo*` branch, branch on `response.statusCode()` inside the callback.
2. **Checking only 2xx in `exchangeTo*` and ignoring the rest.** There is no default 4xx/5xx mapping like `retrieve`; use `createException`/`createError` or an explicit business outcome.
3. **Returning `Mono.empty()` from `onStatus` thinking the 404 request was skipped.** It only skips the error status; body decoding still runs and can fail if the response is HTML/text while the DTO expects JSON.
4. **Reading an error body twice.** The response body is a single-consumption stream; if you need error details, decode them right inside `onStatus` or `exchangeTo*`, then build an exception or result value.
5. **Confusing `bodyToFlux` with a guarantee of real-time delivery.** Flux represents 0..N items, but true streaming also depends on the server, media type, codecs, and proxy/buffering.
6. **Using `onErrorResume` to catch all errors and return fake success.** Filter for specific exceptions; distinguish HTTP status, connection, timeout, and decoding errors, and fall back only when the business contract allows it.
7. **Calling `block()` in a WebFlux request handler.** Blocking the event loop degrades serving capacity or causes errors; return `Mono`/`Flux` directly and compose with `map`, `flatMap`, `zip`.
8. **Not handling empty bodies.** `bodyToMono` may complete without emitting a value (e.g., 204); consider `switchIfEmpty`, `defaultIfEmpty`, or `Mono<Void>` per the endpoint contract.
9. **Mixing retries with every 4xx.** Retries should apply only to transient recoverable errors, with bounded attempts and backoff; avoid blindly retrying requests with side effects (non-idempotent POST).
10. **Relying on `retrieve()` to get headers but losing them.** Use `toEntity(...)`/`toEntityList(...)` if you want status/headers and body without needing `exchangeTo*` control flow.

## 9. Check Your Understanding

- Endpoint GET `/orders/9` returns 404 with an error JSON. If you want to emit `OrderNotFoundException`, what do you use? → `retrieve().onStatus(...)`, parse the error body and construct the exception; if 404 is a normal result with a different schema, `exchangeToMono(...)` may fit better.
- Endpoint returns a 200 JSON array and 500 HTML. What if you want the list or standard HTTP error? → `retrieve().bodyToFlux(Order.class)` is enough. If HTTP 404 must become an empty stream, write an explicit `exchangeToFlux(...)` callback.
- With `onStatus(status -> status.value() == 404, response -> Mono.empty())`, what happens? → The 404 response proceeds to the decoder; it does not automatically emit `Mono.empty()` downstream.
- Why shouldn't you save `ClientResponse` and decode it in a `flatMap` outside `exchangeToMono`? → The callback must decide and consume the body within its scope; any unused body is released after the callback publisher finishes.

## 10. References

- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Framework — `retrieve()` and `onStatus()`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — `exchangeToMono()` / `exchangeToFlux()`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework API — `WebClient.ResponseSpec`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html
