# Trả về Mono hoặc Flux từ Controller MVC và giới hạn chuyển đổi sang I/O không chặn

## 1. Bài toán: reactive return type có biến Spring MVC thành WebFlux không?

Trong một ứng dụng **Spring Boot sử dụng Spring MVC (Servlet stack)**, method của `@RestController` có thể trả `Mono<T>` hoặc `Flux<T>` từ Project Reactor. Điều này rất hữu ích khi controller gọi một HTTP client reactive (`WebClient`) hoặc một service vốn trả reactive publisher.

Nhưng có một ranh giới kiến trúc cực kỳ quan trọng: **Spring MVC hỗ trợ async request và reactive return values, chứ không biến toàn bộ Servlet HTTP pipeline thành non-blocking I/O của Spring WebFlux**. Theo tài liệu Spring Framework 6.2, khi ghi streaming response, Spring MVC có reactive backpressure, nhưng **các lần ghi vào Servlet response vẫn blocking và được chạy trên thread khác qua `AsyncTaskExecutor`**.

Mục tiêu bài học:

- Hiểu vì sao `Mono` và `Flux` hợp lệ ở MVC controller và cách Framework chuyển chúng sang async MVC.
- Phân biệt `Mono<T>`, `Flux<T>` trả `application/json`, và `Flux<T>` trả các media type streaming như `text/event-stream` hay `application/x-ndjson`.
- Hiểu `ReactiveAdapterRegistry`, `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, Servlet `AsyncContext`, `AsyncTaskExecutor` và giới hạn của blocking response writes.
- Tạo ví dụ Spring Boot 3.5 + Java 17 + Spring MVC chạy được và kiểm thử bằng `MockMvc`.
- Tổ chức WebClient calls, timeout, cancellation, backpressure, context propagation và chọn MVC/WebFlux theo workload thay vì chỉ theo kiểu trả về.

Ví dụ dùng **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17**. Trong Spring Boot 4.x, cần kiểm tra lại starter, package, test annotations và cấu hình đúng phiên bản.

## 2. Từ HTTP request tới reactive publisher trong Spring MVC

Ví dụ một controller hợp lệ:

```java
@GetMapping("/api/greeting")
public Mono<Greeting> greeting() {
    return Mono.just(new Greeting("Xin chào"));
}
```

Với `@RestController` và Reactor trên classpath, Spring MVC không coi `Mono` là một object JSON cần serialize nguyên trạng. Framework nhận diện kiểu reactive nhờ `ReactiveAdapterRegistry`, đăng ký async MVC handling và chờ tín hiệu kết quả.

Sơ đồ khái quát:

```text
HTTP request
    |
    v
Tomcat/Jetty/Undertow (Servlet container)
    |
    v
DispatcherServlet -> HandlerMapping -> HandlerAdapter
    |
    v
@RestController method trả Mono hoặc Flux
    |
    v
ReactiveAdapterRegistry nhận diện Publisher
    |
    +--> Mono<T> / publisher 0..1
    |       |
    |       v
    |   MVC asynchronous handling (~ DeferredResult)
    |       |
    |       v
    |   Khi có kết quả -> ASYNC dispatch -> response
    |
    +--> Flux<T> với media type streaming
    |       |
    |       v
    |   MVC streaming (~ ResponseBodyEmitter / SseEmitter)
    |       |
    |       v
    |   Blocking Servlet response writes trên AsyncTaskExecutor
    |
    +--> Flux<T> với media type non-streaming
            |
            v
        Gom thành List (~ DeferredResult<List<?>>)
            |
            v
        Serialize một response thông thường
```

**Không đồng nhất:**

- `Mono` và `Flux`: abstraction về dữ liệu và thời điểm phát dữ liệu.
- Servlet async: cơ chế tạm thả container request thread rồi tiếp tục xử lý khi có kết quả.
- Non-blocking network I/O: đặc tính của transport đọc/ghi; không tự sinh ra chỉ vì method trả Reactor type.

## 3. ReactiveAdapterRegistry có vai trò gì?

`ReactiveAdapterRegistry` thuộc `org.springframework.core` và dùng để nhận biết/adapter những reactive types hỗ trợ như Reactor `Mono`/`Flux`, một số loại publisher khác hoặc `CompletionStage` theo khả năng từng phiên bản.

Với MVC annotated controllers, các return value handler sử dụng thông tin này để quyết định:

1. Publisher phát **0 hoặc 1 giá trị** hay **nhiều giá trị**.
2. Có media type streaming trong response hay không.
3. Nên đưa kết quả vào xử lý async một giá trị, stream các phần tử, hay aggregate thành List.
4. Khi nào framework đăng ký async processing, dispatch lại request và xử lý lỗi.

Không cần tự đăng ký một `ReactiveAdapterRegistry` chỉ để `Mono`/`Flux` của Reactor hoạt động trong project bình thường. Với loại reactive library khác, cần đúng adapter và dependency.

Các API `DeferredResult`/`ResponseBodyEmitter` là **so sánh về cách xử lý**; chúng không có nghĩa mỗi lần framework thực sự tạo đúng cùng một object bạn sẽ thấy trong code. Hãy hiểu theo lifecycle được tài liệu mô tả.

## 4. Mono<T> trong MVC: tương tự DeferredResult

Với một giá trị bất đồng bộ:

```java
@GetMapping("/api/one")
public Mono<Item> one() {
    return service.fetchItem();
}
```

Khái quát:

1. Controller trả `Mono<Item>` mà không gọi `.block()`.
2. MVC đăng ký Servlet async request processing và có thể thả container thread ban đầu.
3. Khi publisher phát item hoặc lỗi, MVC thực hiện những bước hoàn tất response thích hợp, thường bao gồm async dispatch.
4. `HttpMessageConverter` của MVC serialize item thành JSON khi endpoint là `@RestController` và có Jackson.

Spring MVC vẫn dùng **Servlet APIs** và cơ chế async dispatch; không chuyển `DispatcherServlet` thành `DispatcherHandler` của WebFlux.

Một publisher `Mono.empty()` cũng không tự có nghĩa **404 Not Found**. Nếu business logic muốn báo thiếu tài nguyên, hãy biểu diễn rõ:

```java
return service.fetchItem(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Không tìm thấy item")));
```

Đoạn trên là fragment MVC/Reactor, cần import `Mono`, `ResponseStatusException`, `HttpStatus`. Không suy luận outcome của `Mono.empty()` là một HTTP contract 404 ổn định.

## 5. Flux<T> trả application/json: có thể gom toàn bộ thành List

Khi controller trả một `Flux<Item>` nhưng response media type là `application/json` thông thường:

```java
@GetMapping(
    path = "/api/items",
    produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Item> items() {
    return Flux.just(
        new Item(1, "A"),
        new Item(2, "B"));
}
```

Theo Spring Framework MVC async docs, publisher **nhiều giá trị + media type không streaming** được xử lý tương tự `DeferredResult<List<?>>`. Các phần tử được thu thập rồi mới serialize ra response JSON, ví dụ:

```json
[
  {"id":1,"name":"A"},
  {"id":2,"name":"B"}
]
```

Điểm quan trọng: **`Flux` không bảo đảm HTTP output được phát liên tục từng phần tử**. Nếu publisher phát một triệu phần tử với media type không streaming, bước tập hợp có thể sử dụng bộ nhớ lớn và kéo dài thời gian chờ trước khi client nhận body.

Nếu cần JSON array nhỏ, cách này tiện. Nếu cần hàng triệu record hoặc stream vô hạn, phải chọn định dạng **streaming** và kiểm soát tài nguyên.

## 6. Flux<T> trả streaming media type: response được phát dần

Khi `Flux` có media type hỗ trợ streaming như:

- `text/event-stream`: Server-Sent Events (SSE).
- `application/x-ndjson`: newline-delimited JSON.
- Những streaming representations được MVC message converters hỗ trợ trong stack cụ thể.

Spring MVC chuyển sang cơ chế tương tự `ResponseBodyEmitter` hoặc `SseEmitter`, phát các phần tử dần và sử dụng `HttpMessageConverter` tương ứng.

```java
@GetMapping(
    path = "/api/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofMillis(200))
        .take(3)
        .map(i -> ServerSentEvent.<String>builder(
                    "tick-" + i)
            .id(Long.toString(i))
            .event("tick")
            .build());
}
```

Đây là method trong MVC `@RestController`; cần imports `Mono`/`Flux` từ Reactor, `Duration` từ `java.time`, `MediaType` và `org.springframework.http.codec.ServerSentEvent`.

Phản hồi có thể gồm ba SSE events với ID 0, 1, 2. Không hứa hẹn thời điểm nhận từng byte chính xác, vì servlet container, TCP/TLS và reverse proxy có thể buffer hoặc flush theo nhịp khác.

**Đặc biệt:** Streaming với `Flux` trong MVC có thể áp dụng reactive backpressure, nhưng lúc ghi xuống Servlet HTTP response, Framework sử dụng **blocking writes trên executor**. Không gọi đây là “WebFlux chạy trên Tomcat” hoặc “end-to-end non-blocking I/O”.

## 7. Ba tình huống so sánh cần nhớ

| Controller return | HTTP representation | MVC xử lý theo tài liệu | Có streaming từng phần tử? |
|---|---|---|---|
| `Mono<Item>` | `application/json` | Như `DeferredResult` cho 0..1 kết quả | Không, một item |
| `Flux<Item>` | `application/json` | Như `DeferredResult<List<?>>` | Thông thường **không**; gom trước |
| `Flux<Item>` | `application/x-ndjson` | Như response emitter với streaming | Có, khi writer/codec hỗ trợ |
| `Flux<ServerSentEvent<T>>` | `text/event-stream` | Như `SseEmitter` | Có |
| `Callable<Item>` | `application/json` | Async task executor tạo một kết quả | Không, một item |
| `StreamingResponseBody` | Ví dụ `application/octet-stream` | Viết thẳng OutputStream ở worker thread | Ghi theo phần, nhưng blocking |

Một `Flux` bất tận với `application/json` không bao giờ hoàn tất bước aggregate như kỳ vọng. Nếu endpoint là nguồn live events, chọn SSE hoặc định dạng streaming khác có hợp đồng rõ.

Không chỉ nhìn method signature để đoán response. Phải kiểm tra `produces`, `Accept`, `Content-Type` và converter trên classpath.

## 8. Ví dụ hoàn chỉnh: Spring Boot 3.5 + Java 17, vẫn là MVC

Để có MVC controller trả Reactor publishers, tạo project Maven Java 17 với **Spring Web** và **reactor-core**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
    </dependency>
</dependencies>
```

Phần `<dependencies>` ở trên dành cho `pom.xml` đã có Spring Boot parent/dependency management. `reactor-core` cung cấp `Mono`/`Flux`, còn `spring-boot-starter-web` tạo Servlet MVC runtime (mặc định thường Tomcat) và JSON converter.

Nếu cũng cần `WebClient`, có thể thêm `spring-boot-starter-webflux`; khi cả `starter-web` và `starter-webflux` có mặt, **Spring Boot mặc định thường ưu tiên web application type SERVLET/MVC**. Nhưng để ví dụ này rõ ràng, không cần thêm starter WebFlux.

Cấu trúc:

```text
src/main/java/com/example/mvcasync/
    MvcAsyncApplication.java
    ReactiveReturnController.java
    MvcAsyncConfiguration.java
src/main/resources/
    application.properties
src/test/java/com/example/mvcasync/
    ReactiveReturnControllerTest.java
```

Không thêm `@EnableWebFlux` hoặc `@EnableWebMvc` cho ví dụ. MVC auto-configuration của Boot đủ để phát hiện `@RestController` và xử lý async return values.

## 9. Lớp khởi động và cấu hình

File `src/main/java/com/example/mvcasync/MvcAsyncApplication.java`:

```java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcAsyncApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcAsyncApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Thời gian tối đa mặc định cho MVC asynchronous requests
spring.mvc.async.request-timeout=30s

# Spring Boot auto-configured applicationTaskExecutor (khi đủ điều kiện)
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.thread-name-prefix=mvc-async-
```

Cấu hình `spring.task.execution.pool.*` ở trên chỉ áp dụng khi Boot sử dụng `ThreadPoolTaskExecutor` do Boot auto-configure (đối với Java 17 không bật virtual threads). Nếu ứng dụng đã có custom `Executor` bean khiến Boot auto-configuration back off, cần kiểm tra bean nào MVC đang thực sự sử dụng.

Queue có kích thước hữu hạn là quan trọng: nếu queue unbounded, tăng `max-size` chưa chắc tạo thêm worker threads khi tải tăng; queue có thể tiếp tục phình lên thay vì pool mở rộng.

`spring.mvc.async.request-timeout` là async timeout của request, **không phải** connect/read timeout của WebClient, không phải giới hạn toàn bộ thời gian HTTP từ mọi proxy và không phải giới hạn số phần tử Flux.

## 10. Controller chạy được: Mono, Flux JSON và SSE

File `src/main/java/com/example/mvcasync/ReactiveReturnController.java`:

```java
package com.example.mvcasync;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reactive")
public class ReactiveReturnController {

    @GetMapping(
        path = "/single",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Item> single() {
        return Mono.delay(Duration.ofMillis(40))
                .map(tick -> new Item(1, "one"));
    }

    @GetMapping(
        path = "/collection",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Item> collection() {
        return Flux.just(
                new Item(1, "one"),
                new Item(2, "two"))
            .delayElements(Duration.ofMillis(25));
    }

    @GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(200))
            .take(3)
            .map(i -> ServerSentEvent.<String>builder(
                    "tick-" + i)
                .id(Long.toString(i))
                .event("tick")
                .build());
    }

    public record Item(long id, String name) {
    }
}
```

Đây là class Java 17 đầy đủ:

- `/single`: một item được phát sau khoảng 40 ms; MVC xử lý như một async value.
- `/collection`: hai item phát với độ trễ; do response là `application/json`, MVC chờ tập hợp rồi trả JSON array.
- `/events`: ba SSE events sau các khoảng thời gian; MVC có thể stream events thay vì đợi tạo JSON array.
- `record Item` là DTO đơn giản, Jackson trong Spring Web starter serialize thành JSON.

`Flux.interval` và `Mono.delay` sử dụng Reactor scheduler cho tín hiệu thời gian; độ trễ không phải cam kết real-time. Không gọi `.block()` trong controller. Chạy trong project Maven với dependency Spring/Reactor, **không chạy class đơn lẻ bằng `javac` trần**.

## 11. AsyncTaskExecutor cho Servlet blocking writes

Khi streaming reactive return values trong MVC, Spring Framework dùng một `AsyncTaskExecutor` để thực hiện **blocking writes** ra `ServletOutputStream` trên thread khác, giúp không chặn luồng publisher upstream. Vì vậy cần cấu hình và đo executor dưới tải.

Spring Boot 3.5 có thể tự cấu hình bean **`applicationTaskExecutor`** (thường là `ThreadPoolTaskExecutor` nếu Java 17 và không bật virtual threads). MVC, WebFlux và Spring GraphQL có cơ chế chọn executor tương ứng; với MVC, tên bean và kiểu `AsyncTaskExecutor` quan trọng khi đã có executor tùy chỉnh.

Có thể chỉ định rõ MVC sử dụng executor đó:

File `src/main/java/com/example/mvcasync/MvcAsyncConfiguration.java`:

```java
package com.example.mvcasync;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcAsyncConfiguration implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public MvcAsyncConfiguration(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(30_000L);
    }
}
```

Trong demo không có custom executor khác, Boot cung cấp `applicationTaskExecutor`. Cấu hình này là **tùy chọn nhằm làm rõ bean được MVC dùng**; nếu chỉ cần các property và Boot tự wiring đúng, có thể bỏ file này.

Nếu ứng dụng đã đăng ký một bean `Executor` khác, điều kiện auto-configured `applicationTaskExecutor` có thể thay đổi. Khi đó cần tự cung cấp một bean có tên/kiểu phù hợp hoặc điều chỉnh configuration thay vì giả định ví dụ trên luôn inject được.

`AsyncSupportConfigurer.setTaskExecutor` không làm response writes trở thành non-blocking, nó chỉ **chọn thread pool thực hiện blocking task**. Giám sát số thread, hàng đợi, thời gian ghi, rejected tasks, lỗi khi client ngắt kết nối và thời gian response còn mở.

## 12. Chạy và quan sát bằng curl

Từ thư mục gốc project Maven có `mvnw`:

```bash
./mvnw spring-boot:run
```

Một giá trị JSON:

```bash
curl -i http://localhost:8080/api/reactive/single
```

Body mong đợi:

```json
{"id":1,"name":"one"}
```

JSON array:

```bash
curl -i http://localhost:8080/api/reactive/collection
```

Body mong đợi:

```json
[{"id":1,"name":"one"},{"id":2,"name":"two"}]
```

Phần tử trong JSON array có thứ tự như source `Flux.just`. Nhưng HTTP status/headers/JSON whitespace không nhất thiết giống hoàn toàn trên mọi container.

SSE:

```bash
curl -i -N -H 'Accept: text/event-stream' http://localhost:8080/api/reactive/events
```

`-N` yêu cầu curl không buffer output ở phía client. Những SSE frames dự kiến về mặt nội dung:

```text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2

```

Thứ tự các dòng bên trong một SSE event hoặc thông tin flush có thể phụ thuộc implementation; ví dụ trên diễn giải dữ liệu logic, không phải transcript byte-for-byte của `curl -i`, vì `-i` còn in headers.

Ngay cả khi `-N`, reverse proxy (Nginx/Ingress/CDN) vẫn có thể buffer. Kiểm tra headers, proxy buffering và idle timeout để đánh giá liệu người dùng thật sự nhận events theo thời gian.

## 13. MockMvc: asyncDispatch mới kiểm tra được kết quả cuối

Do MVC xử lý `Mono`/`Flux` qua Servlet async, test chỉ gọi `mvc.perform(...)` có thể mới quan sát giai đoạn request ban đầu. `MockMvc` cung cấp `request().asyncStarted()`, `MvcResult` và `asyncDispatch(result)` để đợi và tiếp tục xử lý response.

Trong project đã có Spring Boot parent/dependency management, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/mvcasync/ReactiveReturnControllerTest.java`:

```java
package com.example.mvcasync;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReactiveReturnControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void monoAsyncResultReturnsOneJsonObject() throws Exception {
        MvcResult pending = mvc.perform(
                get("/api/reactive/single"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.name").value("one"));
    }

    @Test
    void fluxWithJsonIsAggregatedAsAnArray() throws Exception {
        MvcResult pending = mvc.perform(
                get("/api/reactive/collection"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$[0].id").value(1))
            .andExpect(jsonPath("$[1].name").value("two"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Đây là code kiểm thử Spring MVC. `MockMvc` không chứng minh response write ở socket là non-blocking, không đo được network flushing hoặc proxy buffering. Hãy dùng integration test với embedded server + HTTP client để kiểm tra SSE streaming, cancellation, timeout và tải đồng thời.

Với `Flux` **streaming** SSE, cách test chỉ dùng `asyncDispatch` và assert toàn response sau khi complete có thể xác minh nội dung cuối cùng nhưng không chứng minh events được nhận từng phần khi stream còn mở.

## 14. Khi kết hợp WebClient trong một ứng dụng MVC

Một lý do phổ biến để controller MVC trả `Mono` là backend gọi dịch vụ khác qua `WebClient` không chặn:

```java
@RestController
class GatewayController {

    private final WebClient client;

    GatewayController(WebClient.Builder builder) {
        this.client = builder
            .baseUrl("https://upstream.example.org")
            .build();
    }

    @GetMapping("/api/proxy/items/{id}")
    Mono<ItemDto> proxy(@PathVariable("id") long id) {
        return client.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(ItemDto.class);
    }
}
```

Đây là **fragment**: cần tạo `ItemDto`, imports và bổ sung `spring-boot-starter-webflux` hoặc dependency WebClient phù hợp; URL upstream chỉ là ví dụ. Khi cả WebFlux và MVC starters có mặt, Boot thường chạy **SERVLET/MVC** theo mặc định.

Ưu điểm của cách này: lúc chờ upstream trả kết quả, controller MVC không cần giữ request thread đang block ở `WebClient.block()`; có thể nhả Servlet thread trong giai đoạn chờ.

Giới hạn: **HTTP response gửi lại client vẫn qua Servlet stack**. Khi upstream trả một stream lớn qua `Flux`, MVC streaming cần một executor để thực hiện blocking writes. Mức tăng concurrency còn phụ thuộc connection pools, thread pools, client/backpressure và số kết nối HTTP đang mở.

Một số request cần `ResponseEntity<Mono<T>>` hoặc `Mono<ResponseEntity<T>>` để quyết định status/headers sau khi upstream trả kết quả. Khi thiết kế, kiểm tra API MVC của phiên bản cụ thể; **không mặc định** rằng mọi tổ hợp generic return types giống hệt WebFlux.

## 15. Vì sao không gọi block() trong controller?

Mẫu dễ mất lợi ích:

```java
@GetMapping("/api/slow")
public Item slow() {
    return reactiveService.load().block();
}
```

Trong MVC, lệnh `.block()` chặn thread đang xử lý controller cho đến khi publisher có kết quả. Nó làm mất phần lợi ích giải phóng Servlet request thread trong lúc chờ I/O.

Cách thường phù hợp hơn:

```java
@GetMapping("/api/slow")
public Mono<Item> slow() {
    return reactiveService.load();
}
```

Nhưng **không gọi `.block()` không tự làm toàn ứng dụng non-blocking**. Nếu `reactiveService.load()` thực sự gọi JDBC, `Thread.sleep()` hoặc SDK blocking **trước khi trả Mono**, phần blocking vẫn có thể chạy trên request thread.

Ví dụ không tốt:

```java
public Mono<Item> load(long id) {
    Item item = jdbcRepository.findById(id);
    return Mono.just(item);
}
```

Phép `findById` đã chạy đồng bộ trước khi Mono được tạo. Nếu phải dùng blocking dependency, cân nhắc cách xử lý của MVC (`Callable`/async executor) hoặc cô lập blocking khi tích hợp Reactor:

```java
public Mono<Item> load(long id) {
    return Mono.fromCallable(
            () -> jdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **fragment giả định** rằng repository trả `Item` và cần import `Schedulers`. `boundedElastic` ngăn blocking task chạy trên thread Reactor event loop, nhưng chỉ **chuyển blocking sang một worker pool có giới hạn**, không biến JDBC thành non-blocking và không bảo đảm transaction/JPA context được tự động truyền qua thread.

Không trộn `@Transactional`, JPA lazy loading và Reactor scheduler mà thiếu kiểm tra phạm vi transaction và thread-bound context.

## 16. Backpressure trong MVC streaming: có nhưng không phải phép màu

Reactor có cơ chế `request(n)` để downstream điều tiết số phần tử upstream được phép phát. Spring MVC có hỗ trợ backpressure khi chuyển reactive stream thành streaming HTTP response.

Tuy vậy:

```text
Reactive source (Flux<T>)
           |
     reactive demand
           |
MVC response emitter bridge
           |
AsyncTaskExecutor worker
           |
ServletOutputStream.write(...)  <-- có thể BLOCK
           |
Servlet container -> client/proxy
```

Khi `ServletOutputStream.write` chờ client tiêu thụ dữ liệu, một thread trong executor có thể bị giữ. Nếu có nhiều client chậm hoặc SSE connections tồn tại lâu, số thread/queue và latency có thể trở thành nút thắt.

Backpressure giúp **giới hạn phát phần tử khi downstream chậm**; nó không bảo đảm:

- Không có thread bị chặn khi ghi response.
- Không có buffer ở container, proxy hoặc TCP stack.
- Không có queue của task executor.
- Không có memory tăng ở upstream nếu code dùng `collectList()`, `cache()`, `onBackpressureBuffer()` không giới hạn.
- Không có slow client hoặc client disconnect.

Đặc biệt, `Flux<T>` được trả với `application/json` vẫn có thể được gom thành List **trước khi ghi**, nên phải coi đó là bài toán memory aggregation riêng.

## 17. Async Servlet lifecycle và ASYNC dispatch

Servlet async được thiết kế để request thread ban đầu có thể kết thúc mà **response vẫn mở**. Với kết quả kiểu một giá trị, luồng Spring MVC thường giống:

```text
Container thread 1
  -> DispatcherServlet -> controller trả Mono
  -> request.startAsync()
  -> rời Filter/Servlet chain, release thread
             |
             | Publisher phát giá trị sau đó
             v
ASYNC dispatch trên container thread
  -> DispatcherServlet nhận lại request
  -> xử lý async result, convert body, hoàn tất
```

Khi async dispatch, `DispatcherServlet` có thể được invoke lại nhưng **không gọi lại business controller method** như một request mới; kết quả đã lưu trong async processing state được tiếp tục xử lý.

Đối với streaming, MVC giữ response mở và ghi dần nhiều phần tử; có thể có lần cuối async dispatch để kết thúc/xử lý lỗi. Đây không phải một round trip HTTP mới từ browser.

Servlet/filter phải có `asyncSupported=true`. Nếu thêm custom filter hoặc dùng WAR trên container bên ngoài, cấu hình filter dispatch types cần tương thích với `ASYNC`. Không đánh đồng `ASYNC` với `FORWARD` hay `ERROR`.

Trong Boot embedded Servlet setup mặc định, MVC async thường đã được thiết lập phù hợp; không cần trực tiếp gọi `request.startAsync()` trong controller trả Mono/Flux.

## 18. Timeout, cancellation và lỗi trong publisher

Ứng dụng cần giới hạn thời gian giữ một HTTP response mở. Với MVC:

```properties
spring.mvc.async.request-timeout=30s
```

Đây là default MVC async timeout. Phải đối chiếu thêm:

- HTTP client/WebClient **connect/read/response timeout** khi gọi upstream.
- Servlet container connection/async timeout.
- Reverse proxy hoặc load balancer idle/read timeout.
- Subscriber/client cancellation và hành vi dispose publisher.

Ví dụ đặt timeout ở Reactor pipeline:

```java
@GetMapping("/api/upstream")
public Mono<Item> upstream() {
    return reactiveService.load()
        .timeout(Duration.ofSeconds(5))
        .onErrorMap(TimeoutException.class,
            ex -> new ResponseStatusException(
                HttpStatus.GATEWAY_TIMEOUT,
                "Upstream phản hồi quá chậm", ex));
}
```

Đây là **fragment** trong `@RestController`; cần imports `Duration`, `TimeoutException`, `ResponseStatusException`, `HttpStatus`. Reactor timeout khác với MVC async request timeout và proxy timeout. Với dịch vụ upstream lỗi, chọn status phù hợp theo API contract, không mặc nhiên mọi timeout đều là 504.

Khi `Flux` đang stream mà exception phát sinh **sau khi HTTP response đã commit**, không thể đáng tin cậy đổi status 200 thành 500 hoặc ghi một JSON error body hoàn toàn mới. Với SSE, có thể định nghĩa **event lỗi** ở cấp ứng dụng nếu kết nối còn ghi được; nếu không, đóng stream và cho client reconnect theo policy.

`doFinally` có thể quan sát completion/error/cancel, nhưng các thao tác cleanup blocking không nên chạy bừa trên Reactor non-blocking threads. Resource/connection cancellation cần được kiểm thử trong môi trường HTTP thật.

## 19. Client disconnect: không có thông báo Servlet tức thời đáng tin

Theo Spring MVC async docs, Servlet API không có callback tổng quát bảo đảm thông báo ngay khi peer biến mất. Khi streaming, server thường phát hiện client disconnect qua **lần ghi tiếp theo thất bại** (ví dụ IOException).

Với SSE lâu dài, nên phát heartbeat theo chu kỳ phù hợp để phát hiện kết nối hỏng và tránh idle timeout của proxy. Heartbeat có thể là SSE comment event hoặc dữ liệu ứng dụng được client bỏ qua.

Ví dụ nguyên lý trong SSE:

```text
: heartbeat

event: tick
data: 42

```

Đây là format SSE ở HTTP body, không phải fragment Java. Nếu không gửi dữ liệu trong thời gian dài, một client đã mất kết nối có thể chưa bị phát hiện kịp, vẫn chiếm tài nguyên server.

Cần đặt các giới hạn cho maximum concurrent streams, duration, client authentication, retries và upstream subscriptions. Không viết bộ retry vô hạn, không có backoff và không theo dõi số kết nối đang mở.

## 20. Context propagation, MDC và SecurityContext

Khi MVC request đi qua nhiều thread (container thread, async executor thread, Reactor scheduler), các giá trị `ThreadLocal` không tự di chuyển đầy đủ. Ví dụ:

- `RequestContextHolder` và request attributes.
- `LocaleContextHolder`.
- Log MDC và trace/span context.
- Security context gắn với thread.

Spring Framework tài liệu hóa việc dùng **Micrometer Context Propagation** để chuyển thông tin giữa ThreadLocal và Reactor Context. Nếu dependency có mặt và đăng ký `ThreadLocalAccessor` phù hợp, Framework có thể hỗ trợ chụp và chuyển context cho reactive return values; những accessor như request/locale không nên được giả định luôn tự đăng ký trong mọi project.

Không phụ thuộc vào việc `MDC.get("traceId")` trong callback chạy trên `Schedulers.parallel()` luôn có giá trị giống container thread. Kiểm thử xuyên async boundary và Reactor scheduler. Khi cần access security principal trong reactive callback, truyền đối tượng cần thiết một cách an toàn hoặc sử dụng cơ chế context propagation đúng với stack.

**Không lưu `HttpServletRequest` hoặc mutable request-scoped data vào global singleton** chỉ để truy cập sau khi thread ban đầu kết thúc.

## 21. MVC @RequestBody và @RequestPart vẫn chủ yếu dùng binding đồng bộ

Điểm khác biệt dễ bị bỏ sót:

- Spring MVC cho phép `Mono`/`Flux` ở **return value** của controller.
- Spring MVC không cung cấp cơ chế tương đương WebFlux cho reactive argument types như `@RequestBody Mono<Dto>` hay `@RequestPart Flux<...>` trong annotated controller theo cách WebFlux làm.

Ví dụ mong muốn một controller đọc stream request body theo kiểu reactive:

```java
@PostMapping("/api/upload")
public Mono<Void> upload(@RequestBody Flux<DataBuffer> body) {
    // Đây là phong cách WebFlux, KHÔNG phải phương án
    // thay thế trực tiếp cho Servlet MVC @RequestBody.
}
```

Đoạn trên là **ví dụ sai stack**, không phải source code nên đặt vào ứng dụng MVC demo.

Trong MVC, dùng `HttpServletRequest.getInputStream()` hoặc `MultipartFile.getInputStream()`/transfer cho request upload lớn, kết hợp giới hạn byte và tài nguyên. Đó vẫn thường là blocking input operations theo Servlet API. Với reactive HTTP body streaming từ request tới response qua `Flux<DataBuffer>`, **WebFlux** là programming model phù hợp hơn.

Bởi vậy, **chỉ đổi return type sang Mono/Flux không chuyển luôn request body decoding sang reactive pipeline**.

## 22. StreamingResponseBody và ResponseBodyEmitter: khi nào dùng?

Không phải bài toán nào cũng cần Reactor. Spring MVC có các API async chuẩn:

- `DeferredResult<T>`: một kết quả xuất hiện sau.
- `Callable<T>`: xử lý một kết quả trên async task executor.
- `ResponseBodyEmitter`: phát nhiều object thông qua `HttpMessageConverter`.
- `SseEmitter`: phát Server-Sent Events.
- `StreamingResponseBody`: ghi dữ liệu thô vào `OutputStream` theo luồng trên worker thread.

Ví dụ tải file lớn:

```java
@GetMapping(
    path = "/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public StreamingResponseBody download() {
    return output -> {
        try (InputStream input = Files.newInputStream(
                Path.of("reports", "report.bin"))) {
            input.transferTo(output);
        }
    };
}
```

Đây là **method minh họa** trong MVC controller, cần imports `InputStream`, `Files`, `Path`, `StreamingResponseBody`, `GetMapping`, `MediaType`. File thật phải tồn tại, có kiểm soát quyền và path; `InputStream.transferTo` là blocking copy nhưng dùng buffer, không gom toàn file vào heap.

Nếu đã có nguồn dữ liệu là `Flux`, trả `Flux` có thể ít code hơn. Nếu nguồn là I/O blocking truyền thống và ứng dụng là MVC, `StreamingResponseBody` hoặc `ResponseBodyEmitter` có thể rõ ràng hơn việc cưỡng ép mọi luồng thành Reactor Publisher.

Trong mọi trường hợp, cần cấu hình async executor phù hợp, bảo vệ slow clients và xử lý trạng thái response đã commit.

## 23. Hiệu năng: tránh nhầm số thread với số request

Ví dụ một request `Mono<Item>` mất 300 ms để chờ HTTP upstream nhưng chỉ tốn vài ms CPU. Nếu controller gọi `.block()`, Servlet request thread có thể bị giữ trong 300 ms. Nếu trả `Mono`, async MVC có thể release thread trong lúc chờ, giúp tăng concurrency của khâu chờ I/O.

Nhưng nếu nhiều client cùng yêu cầu một `Flux` SSE/NDJSON có response writes chậm, async executor có thể cần nhiều worker threads và queues. Vì vậy latency/throughput tổng còn phụ thuộc:

| Tài nguyên | Điều cần quan sát |
|---|---|
| Servlet request threads | Busy threads, queue, rejected connections |
| MVC async executor | Active threads, queue depth, rejected tasks, write duration |
| WebClient connection pool | Active/pending connections, response timeout |
| Reactor schedulers | Queues, blocked threads, saturation |
| Container output | ServletOutputStream.write duration, flush behavior |
| Network/proxy | RTT, buffering, idle timeout, slow clients |
| Heap/GC | Flux JSON aggregation, data caches, object retention |
| Direct memory | Netty client buffers nếu dùng WebClient Reactor Netty |
| Error handling | Timeout, cancellation, disconnect, response committed |

Không kết luận “đã reactive nên tiết kiệm thread” chỉ từ việc import `Mono`. Đo thực tế bằng load tests cho endpoints một giá trị, JSON arrays, SSE và các client chậm. So sánh với phương án MVC blocking hoặc WebFlux non-blocking trên cùng workload.

## 24. Khi nào nên dùng Spring WebFlux thay vì MVC + Mono/Flux?

**Giữ Spring MVC** khi:

- Hệ thống chính dựa trên Servlet filters, Spring MVC controllers, blocking JPA/JDBC và các thư viện đồng bộ.
- Chỉ một số endpoint gọi downstream reactive `WebClient` và muốn tránh block request thread trong lúc đợi.
- Có vài SSE/streaming endpoints ở mức concurrency vừa phải, có executor và proxy được cấu hình/đo tải phù hợp.
- Chuyển toàn bộ stack sang WebFlux có chi phí migration lớn hơn lợi ích đo được.

**Cân nhắc Spring WebFlux** khi:

- Ứng dụng chủ yếu sử dụng I/O non-blocking từ server tới database/upstream.
- Cần rất nhiều long-lived streaming connections/streams và muốn I/O non-blocking xuyên suốt.
- Cần reactive types trong `@RequestBody`/`@RequestPart` và xử lý request bodies bằng `Flux<DataBuffer>`.
- Đội ngũ kiểm soát tốt Reactor operators, backpressure, error signals, cancellation, context propagation và blocking boundaries.

**Nhưng WebFlux không giải cứu mã blocking**: gọi JDBC hoặc SDK blocking trên event-loop cũng gây nghẽn. Nếu giữ phần lớn dependencies blocking, MVC/Servlet với cấu hình async/virtual threads phù hợp có thể là lựa chọn đơn giản hơn. Chọn bằng profiling và yêu cầu concurrency, không theo nhãn công nghệ.

## 25. HTTP statuses, headers và streaming errors

Nếu publisher lỗi **trước khi response commit**, exception có thể đi qua MVC async exception resolution như `@ExceptionHandler` hoặc `ResponseStatusException` và trả HTTP status phù hợp.

Nếu publisher lỗi **sau** khi response đã phát bytes tới client:

- Không thể đổi HTTP status/headers như với response chưa commit.
- Với SSE có thể phát application-level error event nếu socket còn sống và thiết kế client hỗ trợ.
- Với NDJSON có thể có một record báo lỗi nếu format contract cho phép; nếu không, stream bị ngắt giữa chừng và client phải coi dữ liệu là incomplete.
- Khi client disconnect, lỗi `IOException`/network reset có thể được quan sát ở tầng streaming.

Không trả một JSON object `ProblemDetail` giữa chừng của một response đang ở media type `text/event-stream` nếu client không có cách giải mã: điều đó phá contract của stream.

Cũng không coi HTTP 200 với SSE có một event `error` đồng nghĩa với HTTP 500; chúng là hai tầng nghĩa khác nhau. Ghi tài liệu client protocol rõ: resume token, last event ID, reconnect delay, cancellation và tình trạng dữ liệu incomplete.

## 26. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Hướng điều tra |
|---|---|---|
| Trả `Mono` nhưng app vẫn dùng Tomcat | Spring Boot vẫn chọn SERVLET vì `starter-web` | Đó là hành vi đúng của MVC; xác định WebApplicationType |
| `Flux` JSON không gửi từng item | Non-streaming `application/json` được gom List | Dùng SSE/NDJSON khi thật sự cần streaming |
| RSS/heap tăng khi Flux nhiều phần tử | List aggregation, cache, buffering | Giảm dữ liệu, phân trang hoặc streaming media type |
| Có backpressure nhưng nhiều worker threads bận | Servlet response writes là blocking | Đo/giới hạn AsyncTaskExecutor, slow clients |
| Return `Mono` nhưng request thread vẫn block | Service gọi I/O đồng bộ trước khi tạo Mono | Tìm blocking boundary, tránh `.block()` |
| HTTP 503/timeout khi traffic cao | Executor/queue/upstream pool bão hòa | Cấu hình bounded capacity, timeout và observability |
| `MockMvc` không thấy response cuối | Request còn async | Dùng `request().asyncStarted()` + `asyncDispatch` |
| SSE events tới cùng lúc | Buffer ở server/proxy/client | Kiểm tra flush, proxy buffering, curl `-N` |
| SSE kết nối sống mãi sau client mất mạng | Servlet không báo disconnect tức thời | Heartbeat, write detection, cancellation và timeouts |
| `@RequestBody Flux<DataBuffer>` không hoạt động | Code WebFlux đặt vào MVC controller | Dùng Servlet InputStream hoặc chuyển WebFlux |
| MDC/locale mất trong reactive callback | ThreadLocal không tự truyền qua async boundary | Context propagation đúng phiên bản |
| Spring Security principal không như kỳ vọng | Async context propagation khác thread | Kiểm tra filter, request security context và callbacks |
| Exception xảy ra sau flush không đổi status | HTTP response đã commit | Thiết kế stream error protocol, logging/metrics |
| Cả hai web starters làm app chạy MVC | Boot ưu tiên SERVLET theo mặc định | Quản lý dependency/web-application-type có chủ đích |
| Long-lived stream lỗi 500 sau 30s | MVC async timeout | Đổi timeout theo endpoint và proxy, giới hạn stream lifetime |

## 27. Quy trình debug và kiểm thử dưới tải

1. **Xác định stack:** log embedded Tomcat/Jetty/Undertow hay Reactor Netty; `WebApplicationType.SERVLET` hay `REACTIVE`.
2. **Đọc controller signature:** `Mono<T>` hay `Flux<T>`, có `@ResponseBody`/`@RestController` không?
3. **Đọc media type:** `produces`, request `Accept`, response `Content-Type`; `application/json` khác streaming media types.
4. **Tìm operations blocking:** `.block()`, JDBC, `Thread.sleep()`, file I/O, HTTP synchronous clients.
5. **Kiểm tra async support:** `asyncSupported`, filter mappings cho `ASYNC`, servlet container version.
6. **Kiểm tra executor:** bean `applicationTaskExecutor`, `AsyncTaskExecutor` MVC thực sử dụng, thread/queue saturation.
7. **Kiểm tra timeouts:** MVC async, upstream/WebClient, reverse proxy, client idle.
8. **Kiểm tra streaming:** dùng `curl -N` hoặc HTTP client nhận từng event; không chỉ xem response body khi request đã kết thúc.
9. **Quan sát context:** MDC, trace/span, Locale, Security principal qua async callbacks.
10. **Thử lỗi:** publisher error trước/sau commit, client disconnect, upstream timeout, executor rejection.
11. **So sánh tải:** latency p95/p99, active Servlet threads, executor threads/queue, heap và network throughput.
12. **Xác nhận contract:** JSON array gom List có phù hợp kích thước dữ liệu không; SSE/NDJSON có heartbeat/error/resume policy không?

### Checklist ngắn

- [ ] Hiểu `Mono` ở MVC là **async result**, không phải non-blocking Servlet response write.
- [ ] Hiểu `Flux` + `application/json` có thể bị gom thành List.
- [ ] Chọn `text/event-stream` hoặc streaming media type nếu cần emit dần.
- [ ] Tách blocking I/O khỏi Reactor non-blocking callbacks một cách có giới hạn.
- [ ] Cấu hình `AsyncTaskExecutor` và timeout, không dùng queue vô hạn.
- [ ] Có kiểm thử `MockMvc.asyncDispatch` và integration tests cho socket streaming.
- [ ] Có cơ chế dừng stream, heartbeat, cancellation và error handling.
- [ ] Không giả định reactive request-body binding của WebFlux dùng được trên MVC.
- [ ] Chọn giữa MVC và WebFlux bằng đo tải và khả năng non-blocking của **toàn bộ pipeline**.

## 28. Tổng kết

**Trả về `Mono` hoặc `Flux` từ Spring MVC controller là tính năng được Framework hỗ trợ chính thức.** `ReactiveAdapterRegistry` giúp Spring MVC thích nghi publisher với các cơ chế Servlet asynchronous request processing: một `Mono` gần với `DeferredResult`; một `Flux` non-streaming có thể được gom thành List; một `Flux` streaming dùng cơ chế response emitter.

Điểm không được nhầm: **response writes vẫn blocking tại Servlet layer** và cần `AsyncTaskExecutor` khi stream. Backpressure có thể điều tiết upstream nhưng không loại bỏ thread/queue, proxy buffering, memory aggregation do media type hay giới hạn Servlet I/O.

Dùng MVC + Mono/Flux để tích hợp vài reactive services mà không phải viết `.block()`. Nếu yêu cầu reactive request-body processing và end-to-end non-blocking I/O ở quy mô lớn, hãy đánh giá Spring WebFlux như một lựa chọn kiến trúc riêng.

## 29. Tài liệu tham khảo

- Spring Framework 6.2 — Asynchronous Requests in Spring MVC (DeferredResult, Callable, Streaming, Reactive Types, Context, Disconnects): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — Supported MVC Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Synchronous and Reactive use of WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Framework — WebFlux vs MVC: https://docs.spring.io/spring-framework/reference/web/reactive.html
- Spring Boot 3.5 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Common Application Properties (spring.mvc.async.request-timeout, spring.task.execution.pool.*): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework — MVC Testing Async Requests: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework/async-requests.html
- Reactor — Project Reactor Reference Guide (Backpressure, Schedulers, Operators): https://projectreactor.io/docs/core/release/reference/
- MDN — Server-Sent Events/Event Stream Format: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
