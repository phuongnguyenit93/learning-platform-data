# Trả về kiểu reactive trong Spring MVC và giới hạn khi ghi phản hồi

> **Phạm vi:** Spring Web MVC trên Servlet stack, Java 17+ và Spring Boot 3.x/Spring Framework 6.x; nội dung vẫn có giá trị nền tảng với Spring Framework 7.x nhưng cấu hình dependency của Boot 4 có thể khác. Bài giải thích cách MVC chấp nhận `Mono<T>`, `Flux<T>`, `Publisher<T>` hoặc reactive types được `ReactiveAdapterRegistry` hỗ trợ; phân biệt **giá trị đơn**, **streaming SSE/NDJSON** và **tập hợp JSON thông thường**; làm rõ điều dễ nhầm nhất: **nguồn reactive không làm cho Servlet response write của Spring MVC trở thành non-blocking I/O**. Có một demo Java 17 Spring Boot 3.x chạy được, cách cấu hình `AsyncTaskExecutor`, cURL, MockMvc, giới hạn bộ nhớ và xử lý lỗi/ngắt kết nối.

## 1. Vấn đề: muốn dùng nguồn reactive trong ứng dụng MVC

Một dịch vụ REST dùng Spring MVC nhưng lấy dữ liệu từ Reactor `Mono`, `Flux`, một reactive repository hoặc `WebClient`. Câu hỏi thường gặp:

- `@RestController` có thể trả trực tiếp `Mono<Book>` thay cho `Book` không?
- Trả `Flux<Book>` có đồng nghĩa với gửi từng phần tử ngay đến browser không?
- Khi response là `application/json`, Spring có giữ toàn bộ `Flux` trong bộ nhớ trước khi trả không?
- Nếu client chậm hoặc ngắt kết nối, backpressure hoạt động đến mức nào?
- Cần bao nhiêu thread khi chạy 1.000 kết nối SSE?
- Giữa Spring MVC và WebFlux, điểm khác nhau của cách viết response là gì?

**Trả lời ngắn:** Spring MVC hỗ trợ reactive return types. Nó điều phối thông qua Servlet asynchronous request processing; `Mono` thường được thích ứng như `DeferredResult`, `Flux` chọn giữa **streaming** hoặc **collection** tùy media type. Khi ghi response thực tế, Spring MVC vẫn sử dụng **blocking writes trên một thread/executor dành riêng**, không chuyển sang mô hình WebFlux non-blocking HTTP I/O. Nếu chưa cấu hình executor, buffer, timeout và giới hạn nguồn, app vẫn có thể nghẽn hoặc hết RAM.

## 2. Sơ đồ luồng dữ liệu

```text
HTTP client
     |
Servlet container (Tomcat)
     |
DispatcherServlet + HandlerAdapter
     |
@GetMapping trả Mono<T> / Flux<T>
     |
ReactiveAdapterRegistry
     |
     +--> Mono<T> / single value
     |      -> DeferredResult-style async processing
     |      -> một giá trị / ResponseEntity / JSON / error
     |
     +--> Flux<T> + application/json
     |      -> collect values thành List-like result
     |      -> Jackson serializes JSON array sau khi hoàn tất
     |
     +--> Flux<T> + text/event-stream hoặc application/x-ndjson
            -> emitter-style streaming
            -> encode và ghi từng phần/chunk
            -> blocking ServletResponse write qua AsyncTaskExecutor
     |
HTTP response / Servlet output stream
```

**Điểm then chốt:** không được đánh đồng **Reactive Streams backpressure ở publisher/subscriber** với **non-blocking socket write**. Spring MVC có thể giới hạn tốc độ yêu cầu tiếp từ publisher để phù hợp quá trình write, nhưng mỗi lần viết xuống Servlet response vẫn có thể block một worker thread. <https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html>

## 3. Reactive Streams và Reactor types

### 3.1. Mono và Flux

| Kiểu | Cardinality | Ví dụ ý nghĩa |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 giá trị, hoặc error | Tải thông tin một tài khoản |
| `Flux<T>` | 0 đến N giá trị, có thể hữu hạn hoặc vô hạn | Danh sách, thay đổi theo thời gian, sự kiện |
| `Publisher<T>` | Giao diện Reactive Streams | Abstraction của nguồn phát |
| `CompletionStage<T>` | Một kết quả bất đồng bộ JDK | Future-like result |
| `Single<T>` (RxJava) | Một giá trị | Reactive adapter khác khi thư viện có mặt |

`Mono.just(value)` không tự làm I/O non-blocking. `Mono.fromCallable(() -> blockingRepository.find(...))` vẫn chạy đoạn code blocking trên thread đăng ký nếu không chuyển scheduler phù hợp. Reactor cung cấp `subscribeOn(Schedulers.boundedElastic())` cho những nguồn blocking có kiểm soát, nhưng chuyển thread chỉ giúp tránh block event-loop; nó không làm bản thân JDBC hay Servlet I/O non-blocking.

### 3.2. ReactiveAdapterRegistry

Spring `org.springframework.core.ReactiveAdapterRegistry` kết nối reactive libraries với hạ tầng MVC. Nó nhận biết semantics một giá trị/nhiều giá trị và thích ứng thành chuỗi dữ liệu. Reactor là lựa chọn phổ biến; RxJava cũng có thể được hỗ trợ nếu thư viện và adapter phù hợp có mặt.

Đừng cố viết:

```java
// Anti-pattern: subscribe trong controller và trả null.
@GetMapping("/bad")
public Object bad() {
    service.getBook().subscribe(book -> System.out.println(book));
    return null;
}
```

Đoạn code minh họa này tách subscription khỏi response lifecycle; kết quả có thể đến sau khi handler đã kết thúc, lỗi/cancellation khó gắn với HTTP response. **Trả thẳng publisher** cho MVC:

```java
@GetMapping("/good")
public Mono<BookView> good() {
    return service.getBook();
}
```

Đây là snippet; cần service/DTO được định nghĩa riêng. Khi framework quản lý subscription, nó có thể tích hợp timeout, exception dispatch, message conversion và hủy subscription trong các trường hợp phù hợp.

## 4. Một giá trị: Mono<T> hoạt động như kết quả bất đồng bộ

Ví dụ:

```java
@RestController
class BookController {
    @GetMapping("/api/book")
    Mono<BookView> book() {
        return Mono.just(new BookView(1L, "Spring MVC"));
    }
}
```

Đây là fragment, cần định nghĩa `BookView` và imports. `@RestController` khiến giá trị được đưa ra HTTP response body; `Mono<BookView>` không bị serialize thành JSON mô tả Mono, mà MVC **đợi giá trị thực** do publisher phát.

Về mặt hạ tầng, single-value reactive return được thích ứng tương tự `DeferredResult<T>`:

1. Controller trả publisher, Spring MVC đăng ký xử lý bất đồng bộ.
2. Servlet request chuyển vào async mode; request thread ban đầu có thể được trả về pool.
3. Mono phát `onNext(book)` rồi `onComplete` hoặc `onError`.
4. Spring MVC tiếp tục xử lý kết quả qua async dispatch và ghi body bằng `HttpMessageConverter`.
5. Sau khi response hoàn thành, async lifecycle kết thúc.

**Lưu ý:** `Mono.just(...)` có thể phát giá trị ngay tại lúc subscribe; asynchronous return type không đảm bảo công việc thực sự chạy trên thread khác hoặc thao tác bên trong không blocking. Nếu muốn minh họa giá trị đến muộn, dùng `Mono.delay(...)` hoặc một async service thật.

### 4.1. Mono.empty()

`Mono.empty()` không phát một `T`. Trạng thái HTTP mặc định có thể phụ thuộc method signature, Spring MVC return handler và annotation/status do ứng dụng chọn. Đừng coi `Mono.empty()` luôn là HTTP 404. Nếu business contract là “không tìm thấy”, phải ánh xạ thành lỗi hoặc `ResponseEntity.notFound()` rõ ràng.

```java
@GetMapping("/api/books/{id}")
Mono<ResponseEntity<BookView>> find(@PathVariable long id) {
    return repository.findById(id)
            .map(book -> ResponseEntity.ok(toView(book)))
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Snippet này yêu cầu reactive repository/mapper; mục đích là cho thấy HTTP status được chọn sau khi biết kết quả.

### 4.2. Khi nào Status/Header được quyết định?

Hai cấu trúc khác nhau:

```java
// Status và headers được xác định ngay.
ResponseEntity<Mono<BookView>> immediateHeaders() {
    return ResponseEntity.accepted()
            .header("X-Demo", "value")
            .body(Mono.just(new BookView(1L, "Example")));
}
```

```java
// Toàn ResponseEntity được quyết định bất đồng bộ.
Mono<ResponseEntity<BookView>> deferredHeaders() {
    return Mono.just(
            ResponseEntity.ok(new BookView(1L, "Example")));
}
```

Hai method trên là snippets độc lập, không có `@GetMapping`. Với `ResponseEntity<Mono<T>>`, server biết status/headers sớm, body đến sau. Với `Mono<ResponseEntity<T>>`, status, headers và body đều được quyết định khi Mono hoàn thành. Trong thực tế, nếu cần trả 404/409 tùy dữ liệu bất đồng bộ, `Mono<ResponseEntity<T>>` biểu đạt tốt hơn vì status chưa bị khóa ở thời điểm tạo controller return value.

## 5. Nhiều giá trị: Flux<T> KHÔNG luôn streaming

Cùng một `Flux<BookView>` có thể có hai hành vi khác nhau theo **media type phản hồi**.

### 5.1. Flux + application/json: thu thập rồi serialize một JSON array

```java
@GetMapping(path = "/api/books",
            produces = MediaType.APPLICATION_JSON_VALUE)
Flux<BookView> books() {
    return Flux.just(
            new BookView(1, "A"),
            new BookView(2, "B"));
}
```

Spring MVC thích ứng multi-value reactive type với non-streaming media type như `application/json` thành kết quả tương tự `DeferredResult<List<?>>`. Khi publisher hoàn tất, MVC serialize danh sách thành một JSON array:

```json
[{"id":1,"title":"A"},{"id":2,"title":"B"}]
```

**Không phát từng object ngay khi có phần tử** theo nghĩa SSE/NDJSON. Với nguồn rất lớn, `collectList`-style buffering có thể tăng memory theo số phần tử. Với nguồn vô hạn, response dạng JSON array **không có điểm hoàn tất**; client có thể phải đợi mãi hoặc timeout, trong khi bộ nhớ tiếp tục tăng.

**Lỗi hay gặp:** trả `Flux.interval(...)` vô hạn với `produces="application/json"` và tưởng browser sẽ thấy sự kiện liên tục. Chọn streaming media type hoặc giới hạn/tổng hợp dữ liệu phù hợp.

### 5.2. Flux + text/event-stream: SSE

```java
@GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> events() {
    return Flux.just(
            ServerSentEvent.builder("first")
                    .id("1").event("tick").build(),
            ServerSentEvent.builder("second")
                    .id("2").event("tick").build());
}
```

Đây là snippet; cần Reactor và `org.springframework.http.codec.ServerSentEvent`. SSE có framing dạng text như:

```text
id:1
event:tick
data:first

id:2
event:tick
data:second

```

Thứ tự/cách ghi các fields và line endings tùy serializer; mẫu thể hiện ý nghĩa sự kiện, không phải output byte-for-byte của mọi Spring version.

Với SSE, Spring MVC thích ứng reactive stream thành emitter-style response. Khi có phần tử, MVC có thể serialize và flush để client nhận dần, nếu reverse proxy/network không buffer. Cần dùng client như `curl -N` để tránh buffer stdout khi kiểm thử.

### 5.3. Flux + application/x-ndjson: mỗi phần tử là một dòng JSON

```java
@GetMapping(path = "/api/records",
            produces = "application/x-ndjson")
Flux<BookView> records() {
    return Flux.just(
            new BookView(1, "A"),
            new BookView(2, "B"));
}
```

**Snippet minh họa định dạng**: để output thực sự là NDJSON, cần `HttpMessageConverter`/Jackson configuration hỗ trợ media type trên phiên bản đang dùng. Khi streaming được chọn, response theo định dạng NDJSON thường là:

```text
{"id":1,"title":"A"}
{"id":2,"title":"B"}
```

Mỗi dòng là một JSON value hoàn chỉnh; khác với mảng JSON truyền thống. Với bản Spring/container/converter cụ thể, cần test serialization và flush thực tế, không chỉ tin `produces`. Một hệ thống có thể cần cấu hình thêm media types cho converter.

### 5.4. Bảng chọn output shape

| Return type | Media type / mapping | Hành vi phổ biến trong MVC | Phù hợp |
| --- | --- | --- | --- |
| `Mono<Book>` | `application/json` | Một body JSON sau khi Mono ra kết quả | Tra cứu một item |
| `Flux<Book>` | `application/json` | Gom toàn bộ thành List/JSON array | Danh sách **hữu hạn, có giới hạn** |
| `Flux<Book>` | `application/x-ndjson` | Từng JSON object theo dòng | Stream nhiều bản ghi |
| `Flux<ServerSentEvent<T>>` | `text/event-stream` | Phát SSE events dần | Notification/telemetry |
| `Flux<T>` | Streaming type khác có converter tương thích | Phụ thuộc converter & media configuration | Streaming chuyên biệt |
| `ResponseEntity<Flux<T>>` | Streaming type | Status/headers xác định trước, body reactive | Stream có metadata tĩnh |
| `Mono<ResponseEntity<T>>` | Non-streaming | Response status/headers/body bất đồng bộ | HTTP status phụ thuộc kết quả |

**Ghi nhớ:** `Flux<T>` là cấu trúc dữ liệu reactive; **media type** mới quyết định MVC có xử lý nó như stream từng phần hay gom lại trước khi render.

## 6. Backpressure trong MVC và giới hạn chỗ ghi response

Reactive Streams cho phép downstream yêu cầu các phần tử từ upstream qua `Subscription.request(n)`. Trong Spring MVC streaming bridge:

```text
Reactor Publisher (có backpressure)
           |
           v
ReactiveAdapter / Subscriber
           |
           v
Spring MVC emitter/queue
           |
           v
AsyncTaskExecutor worker
           |
           v
HttpMessageConverter
           |
           v
ServletOutputStream.write(...)     <-- BLOCKING khi client/network chậm
           |
HTTP client
```

Spring MVC hỗ trợ backpressure khi streaming reactive values để không vô tội vạ lấy hàng triệu phần tử trong lúc network chưa xử lý xong. Tuy nhiên **blocking write không biến mất**: một worker thread có thể mắc kẹt chờ socket/container/network xử lý. Nếu có rất nhiều clients chậm hoặc kết nối SSE lâu dài, số lượng worker cần thiết và mức đệm có thể trở thành bottleneck.

### 6.1. Backpressure không đảm bảo mọi Publisher an toàn

Ví dụ `Flux.interval(Duration.ofMillis(5))` phát sự kiện theo đồng hồ. Nếu downstream không theo kịp, một số source có thể báo overflow/cancellation khi không có demand; hot source như topic/message broker có thể có drop/buffer policy khác. Cần quy định:

- `limitRate` hoặc demand policy khi phù hợp;
- `onBackpressureBuffer(maxSize, overflowStrategy)` có **giới hạn rõ**, không buffer vô hạn;
- `onBackpressureDrop`/`onBackpressureLatest` khi **nghiệp vụ cho phép mất sự kiện**;
- timeout, cancellation và giới hạn tổng số events;
- client reconnection/resume semantics với SSE event IDs nếu cần.

**Không đưa cách drop dữ liệu vào luồng thanh toán hoặc audit** chỉ để giảm RAM; các luồng này cần delivery semantics khác.

### 6.2. Reactive không đồng nghĩa non-blocking khi gọi service

```java
// Anti-pattern: hàm JDBC blocking chạy trên thread phát subscription.
return Mono.fromCallable(() -> jdbcRepository.findById(id));
```

Nếu source chạy trên event loop, có thể block event loop. Với đoạn code blocking tạm thời:

```java
return Mono.fromCallable(() -> jdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Snippet này chuyển công việc sang scheduler giới hạn tương đối; **không biến JDBC thành async driver**. Với tải cao, có thể cần reactive driver, connection pool tuning hoặc giữ service MVC/blocking thông thường. Việc chọn MVC hay WebFlux phải dựa trên toàn pipeline thực tế, không chỉ return type.

## 7. Vì sao Spring MVC không trở thành WebFlux?

| Tiêu chí | Spring MVC + Mono/Flux return | Spring WebFlux |
| --- | --- | --- |
| Foundation | Servlet API + DispatcherServlet | Reactive stack + WebHandler |
| Controller return | Mono/Flux được adapter hỗ trợ | Native reactive pipeline |
| Request body parsing | MVC `HttpMessageConverter` và Servlet request | Reactive `HttpMessageReader` / `Flux<DataBuffer>` |
| Streaming writes | **Blocking Servlet output writes** trên async executor | Non-blocking I/O theo runtime hỗ trợ |
| Backpressure | Có tại reactive publisher bridge | Xuyên nhiều phần của reactive pipeline |
| Servlet thread | Được trả về khi async request bắt đầu, thread khác có thể ghi | Event-loop/non-blocking approach |
| MVC form binding | `@ModelAttribute`/Servlet binding | Reactive-aware APIs khác |
| Streaming CPU/thread cost | Thread bị giữ khi blocking write | Mô hình resource khác, nhưng vẫn phải giới hạn nguồn |
| Chuyển từ MVC sang WebFlux | Không xảy ra chỉ vì trả Flux | Cần chọn Spring reactive web runtime/application stack |

Spring MVC không hỗ trợ `Mono<@RequestBody T>` như một tham số handler reactive được stream ở mức framework contract, và không có explicit reactive model-attribute support tương đương WebFlux. **Return reactive** không đồng nghĩa toàn bộ request path non-blocking.

### 7.1. Có thể thêm Reactor mà vẫn chạy MVC không?

Có. Với Spring Boot 3.x, dependency chính cho server MVC là `spring-boot-starter-web`; thêm `io.projectreactor:reactor-core` nếu muốn dùng Mono/Flux. Bạn **không** cần thêm `spring-boot-starter-webflux` chỉ để trả Reactor types trong MVC. Spring Boot nếu có cả MVC và WebFlux starters thường ưu tiên servlet MVC auto-configuration, nhưng tránh thêm stack không cần thiết để giảm nhiễu.

Nếu cần `WebClient` thực tế, thư viện `spring-webflux` và Reactor Netty/HTTP client tương ứng có thể được thêm như client dependencies; việc có WebClient không ép controller server chuyển sang WebFlux.

### 7.2. Khi nào nên chuyển WebFlux?

Cân nhắc WebFlux khi:
- Có rất nhiều kết nối streaming chậm/đồng thời mà blocking write threads là vấn đề thực tế.
- Backend/call chain dùng non-blocking clients/drivers, tránh block ở mỗi bước.
- Đội ngũ có khả năng thiết kế cancellation, backpressure, errors, context propagation và testing reactive end-to-end.

Giữ MVC khi:
- Ứng dụng chủ yếu dùng blocking JDBC/JPA/Servlet integrations.
- Nhu cầu async vài kết quả đơn hoặc SSE quy mô vừa.
- Muốn tận dụng hệ MVC hiện hữu, dễ gỡ lỗi, và executor/capacity phù hợp.

Không nên chuyển framework chỉ vì trả `Flux` thấy “hiện đại hơn”; hãy đo tải, memory, threads và latency thực tế.

## 8. Cấu hình AsyncTaskExecutor cho response write

Tài liệu Spring MVC nhấn mạnh: khi streaming reactive, framework thực hiện blocking writes bằng `AsyncTaskExecutor` riêng để tránh block upstream source. Executor mặc định dành cho async support **không phù hợp tải production**; cần cấu hình có giới hạn và tính toán capacity.

Ví dụ `WebMvcConfigurer#configureAsyncSupport`:

```java
@Configuration
class MvcAsyncConfig implements WebMvcConfigurer {

    @Bean
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-async-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.initialize();
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(15_000L);
    }
}
```

Đây là snippet class, cần import `@Configuration`, `@Bean`, `WebMvcConfigurer`, `AsyncSupportConfigurer`, `ThreadPoolTaskExecutor`. Phần ví dụ hoàn chỉnh ở mục 9 có đầy đủ imports và method.

**Quan trọng:**
- `@Configuration` bean methods mặc định được Spring proxy để cùng một bean được tái sử dụng khi gọi `mvcAsyncExecutor()` từ config instance; nếu thay đổi `proxyBeanMethods=false`, cần inject instance thay vì tự gọi method.
- `corePoolSize/maxPoolSize/queueCapacity` là thông số ví dụ, không phải chuẩn universal. Khi quá tải, task có thể bị từ chối; cần metrics, capacity planning, fallback và quy tắc trả lỗi trước khi response committed.
- `setDefaultTimeout(15_000L)` áp một default request async timeout; đối với SSE lâu hơn 15 giây cần cấu hình timeout phù hợp. Không sao chép timeout demo vào production long-lived stream một cách máy móc.
- Một thread blocking ghi cho client chậm có thể bị giữ lâu. Executor pool 8 threads không có nghĩa server xử lý vô hạn 10.000 SSE streams mà không có latency/queue issues.
- Nếu dùng Spring Security/Micrometer context, phải xem thêm context propagation qua async threads.

### 8.1. Async Servlet dispatch/filter config

Spring MVC async dựa trên Servlet 3.0+ async capability. Các Filters cần áp dụng đúng dispatcher types và `asyncSupported`. Trong ứng dụng Boot thông thường, embedded Servlet container/DispatcherServlet được cấu hình thích hợp; với deployment truyền thống/custom filter registration, phải tự xác minh:

```xml
<!-- Snippet web.xml cho ứng dụng Servlet truyền thống -->
<servlet>
    <servlet-name>dispatcher</servlet-name>
    <servlet-class>
        org.springframework.web.servlet.DispatcherServlet
    </servlet-class>
    <async-supported>true</async-supported>
</servlet>
```

Với filter cần tham gia async dispatch, đặt `<async-supported>true</async-supported>` và mapping có `<dispatcher>ASYNC</dispatcher>` theo yêu cầu. Nếu một filter không hỗ trợ async nằm trong chain, `request.startAsync()` có thể không chạy đúng. Async dispatch không giống một request mới từ client; các `HandlerInterceptor` callbacks cũng có lifecycle đặc biệt.

## 9. Ví dụ hoàn chỉnh, chạy được: Spring Boot 3.x / Java 17

Ví dụ có ba endpoint:
- `GET /api/mono`: trả một JSON object trễ bằng `Mono<Message>`.
- `GET /api/array`: trả `Flux<Message>` với `application/json`, tạo một JSON array sau khi publisher hoàn thành.
- `GET /api/events`: `Flux<ServerSentEvent<String>>` + `text/event-stream`, gửi ba SSE events theo thời gian.

Demo chỉ dùng dữ liệu hữu hạn, không có database hay authentication. Executor được cấu hình có giới hạn; timeout đủ cho 3 events. Không thêm WebFlux starter để server vẫn là MVC.

### 9.1. Maven dependencies

Tạo Maven Spring Boot **3.5.x** project từ [Spring Initializr](https://start.spring.io/), Java 17, chọn **Spring Web** rồi thêm Reactor Core theo Spring Boot BOM:

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

Đây là fragment của `pom.xml` đã dùng Spring Boot parent/BOM; không đặt Reactor version bằng một số tùy ý trái BOM. `spring-boot-starter-web` bao gồm Spring MVC, Jackson và embedded Tomcat mặc định. Reactor Core cung cấp `Mono`, `Flux` và schedulers.

### 9.2. Cấu trúc source

```text
src/main/
└── java/
    └── com/example/demo/
        └── DemoApplication.java
```

Đặt toàn bộ Java source dưới đây vào file duy nhất `src/main/java/com/example/demo/DemoApplication.java`.

### 9.3. Java hoàn chỉnh

```java
package com.example.demo;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record Message(int id, String text) {
}

@Configuration
class MvcAsyncConfiguration implements WebMvcConfigurer {

    @Bean
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-write-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.initialize();
        return executor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {

        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(15_000L);
    }
}

@RestController
@RequestMapping("/api")
class ReactiveReturnController {

    @GetMapping(
            path = "/mono",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Message> single() {
        return Mono.delay(Duration.ofMillis(100))
                .map(tick -> new Message(1, "ready"));
    }

    @GetMapping(
            path = "/array",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Message> array() {
        return Flux.fromIterable(List.of(
                new Message(1, "alpha"),
                new Message(2, "beta"),
                new Message(3, "gamma")))
                .delayElements(Duration.ofMillis(100));
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(200))
                .take(3)
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .event("tick")
                        .data("event-" + i)
                        .build());
    }
}
```

### 9.4. Vì sao ví dụ là MVC, không phải WebFlux?

- `spring-boot-starter-web` kích hoạt Servlet MVC và embedded Tomcat; không có WebFlux server starter.
- Reactor `Flux/Mono` chỉ là loại return values được MVC adapt.
- `MvcAsyncConfiguration` đăng ký `AsyncTaskExecutor` cho Servlet async and writes.
- `ServerSentEvent<String>` giúp MVC tạo SSE formatting; class nằm trong `org.springframework.http.codec` do Spring Web cung cấp.
- `Mono.delay` và `Flux.interval` mô phỏng async publisher, không block handler thread bằng `Thread.sleep()`.
- `/array` có ba phần tử hữu hạn, nên gom thành JSON array an toàn trong demo.
- `/events` có `take(3)` nên sẽ kết thúc; production long-lived SSE cần timeout, heartbeat, reconnection và limit phù hợp.
- Không có lệnh `.block()` hoặc `.subscribe()` thủ công trong controller; MVC quản lý subscriptions và response lifecycle.

### 9.5. Chạy

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Nếu không cấu hình port, API chạy ở `http://localhost:8080`.

### 9.6. Kết quả Mono

```bash
curl -i 'http://localhost:8080/api/mono'
```

Phần body dự kiến:

```json
{"id":1,"text":"ready"}
```

HTTP status `200 OK`, content type JSON. Giá trị được Mono phát sau một khoảng thời gian nhỏ, nhưng độ trễ thực tế tùy scheduler/server. Không lấy 100 ms làm SLA.

### 9.7. Kết quả Flux JSON array

```bash
curl -i 'http://localhost:8080/api/array'
```

Body sau khi tất cả phần tử được thu thập:

```json
[
  {"id":1,"text":"alpha"},
  {"id":2,"text":"beta"},
  {"id":3,"text":"gamma"}
]
```

JSON thực tế thường trên một dòng và không có whitespace như trên. Quan trọng là **một JSON array hoàn chỉnh**, không phải ba response riêng biệt. Vì MVC gom Flux cho media type `application/json`, client thường không nhận phần tử ngay từ 100 ms đầu.

### 9.8. Kết quả SSE

```bash
curl -N -i \
  -H 'Accept: text/event-stream' \
  'http://localhost:8080/api/events'
```

Một response có 3 events, với các trường tương đương:

```text
id:0
event:tick
data:event-0

id:1
event:tick
data:event-1

id:2
event:tick
data:event-2

```

Thông thường chúng được phát ra theo thời gian, không cần chờ đủ 3. `curl -N` tắt output buffering của curl; nếu có Nginx/CDN hoặc compression buffering, event có thể đến từng cụm thay vì từng mốc. Để kiểm tra streaming thực, cần đo thời điểm nhận từng event ở client, không chỉ xem body cuối.

### 9.9. Windows PowerShell

PowerShell có thể map `curl` thành alias; dùng `curl.exe`:

```powershell
curl.exe -i "http://localhost:8080/api/mono"
curl.exe -i "http://localhost:8080/api/array"
curl.exe -N -i -H "Accept: text/event-stream" "http://localhost:8080/api/events"
```

### 9.10. Không giữ kết nối SSE vĩnh viễn bằng demo

Demo `take(3)` kết thúc nhanh để có kết quả kiểm chứng. Nếu đổi thành `Flux.interval(...)` không giới hạn:

- `async timeout` 15 giây của demo có thể kết thúc request;
- reverse proxy/ingress/load balancer có idle timeout riêng;
- mỗi slow writer có thể chiếm async executor thread;
- browser EventSource thường tự reconnect khi connection đóng;
- event IDs, resume logic, replay bounds và per-client resource limits cần được thiết kế.

Không thay `take(3)` bằng `retry()` vô hạn để “tự sửa” mọi lỗi: có thể tạo infinite loop, duplicate events hoặc quá tải source.

## 10. Kiểm thử async với MockMvc

Với Spring Boot **3.5.x**, thêm test dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Đặt trong `src/test/java/com/example/demo/ReactiveMvcTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReactiveMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void monoReturnsJsonAfterAsyncDispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/api/mono"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.text").value("ready"));
    }

    @Test
    void fluxWithNormalJsonIsCollectedAsArray() throws Exception {
        MvcResult pending = mvc.perform(get("/api/array"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].text").value("alpha"))
                .andExpect(jsonPath("$[2].text").value("gamma"));
    }
}
```

**Giải thích test:**
- Reactive return types được xử lý theo Spring MVC async infrastructure.
- Với MockMvc, cần xác nhận `request().asyncStarted()` và gọi `asyncDispatch(...)` để nhận response hoàn chỉnh trong test; assert trực tiếp trên request ban đầu có thể sai vì kết quả chưa có.
- Test JSON array quan sát việc Flux được gom trước khi serialize.
- SSE cần kiểm tra riêng media type/event framing và streaming timing ở môi trường servlet/container thật; chỉ một MockMvc response cuối **không chứng minh network streaming**.

Chạy:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Test `Mono.delay`/`Flux.delayElements` dựa vào real scheduler; nếu CI bị quá chậm hoặc timeout, tăng giới hạn test một cách có lý do hoặc dùng virtual scheduler trong unit test Reactor, không lạm dụng `Thread.sleep(...)` trong test.

## 11. Streaming errors: khi đã commit, không thể quay lại đổi HTTP status

Với Mono single value, nếu lỗi xảy ra **trước khi** MVC ghi headers/body, `@ExceptionHandler` hoặc `@RestControllerAdvice` có thể tạo 4xx/5xx response. Ví dụ:

```java
@GetMapping("/api/error")
Mono<Message> failEarly() {
    return Mono.error(new IllegalStateException("upstream unavailable"));
}
```

Đây là snippet controller; cần error policy. Nếu error được xử lý trước khi response committed, Spring MVC có thể dispatch lỗi qua exception resolvers.

**Nhưng với streaming Flux**, server có thể đã gửi các events đầu:

```text
event:tick
data:first

event:tick
data:second

... publisher errors ...
```

Lúc đó HTTP headers/status có thể đã committed. Server **không thể đảm bảo** chuyển status 200 thành 500, đổi Content-Type hay thay cả body bằng JSON lỗi chuẩn. Hành vi có thể là đóng connection, hủy stream, log exception hoặc báo lỗi bằng **event/application protocol** nếu response còn ghi được và thiết kế cho phép.

### 11.1. Giao thức báo lỗi trong stream

Với SSE, có thể định nghĩa event riêng:

```text
event:app-error
data:{"code":"UPSTREAM_LOST","message":"Retry later"}

```

Đây là **giao thức ứng dụng** trong body SSE, không phải chuyển HTTP status đã gửi thành 500. Nếu client cần biết lỗi đáng tin, nó phải hiểu event `app-error` và có chiến lược retry/backoff. Không đưa stacktrace, tokens hay thông tin hệ thống vào error events.

### 11.2. Khi response chưa committed

Với `Mono<ResponseEntity<T>>`, response metadata được quyết định cùng async result; vì vậy dễ chọn status theo dữ liệu hơn `ResponseEntity<Mono<T>>`. Với `Flux` đã stream, status thường cố định trước khi tất cả phần tử có mặt. Nên validate/auth trước khi bắt đầu stream và kiểm tra nguồn availability/permissions phù hợp để giảm nguy cơ lỗi muộn.

### 11.3. Client disconnect

Nếu client đóng tab/ngắt kết nối, writer có thể ném `IOException` hoặc loại exception đặc thù container; publisher subscription/cancellation cần được quản lý để không giữ task/connection sau khi response đã chết. Reactor cung cấp `doOnCancel`/`doFinally` để quan sát cleanup, ví dụ:

```java
Flux<Long> events = Flux.interval(Duration.ofSeconds(1))
        .doFinally(signal -> {
            // Cleanup subscription-scoped resources nếu có.
            // Không log token/session/cookie thô.
        });
```

Snippet này không thay một chính sách cleanup đầy đủ nếu upstream là hot stream/shared subscription hoặc có database cursor. Cần test disconnect qua network thật.

### 11.4. Timeout và response đã ghi dở

Timeout của Servlet async request, gateway read/write timeout và upstream publisher timeout **khác nhau**. Khi timeout xảy ra sau khi đã stream bytes, error handler thường không còn thay status/body được. Với Flux vô hạn, hãy xác định chính sách long-lived connection, heartbeat, idle timeout, maximum duration, retry và quota thay vì tin một default timeout.

## 12. Threading, context propagation và bảo mật

### 12.1. ThreadLocal không tự xuyên qua mọi async boundary

Trong Servlet MVC đồng bộ, `RequestContextHolder`, MDC và một số security context có thể gắn với request thread. Khi reactive pipeline chuyển sang scheduler hoặc Servlet async write thread, **không nên mặc định** ThreadLocal còn nguyên.

Spring có tích hợp Micrometer Context Propagation khi library tương ứng hiện diện và `ThreadLocalAccessor` được đăng ký; các accessor như Locale/Request attributes có thể cần đăng ký có chủ đích. Reactive `Context` và ThreadLocal là hai cơ chế khác nhau.

**Không làm:**

```java
return Mono.delay(Duration.ofMillis(50))
        .map(tick -> SecurityContextHolder.getContext()
                .getAuthentication()
                .getName());
```

Nếu không có context propagation đúng, bạn có thể thấy null hoặc security context không mong muốn. Về bảo mật, hãy đưa ID/tenant đã xác thực qua service API có kiểm soát hoặc dùng context propagation chuẩn, không truyền toàn bộ token bí mật vào global static state.

### 12.2. Authorization cần diễn ra trước stream

- Xác thực request bằng Spring Security filter chain.
- Kiểm tra user có quyền subscribe đúng channel/resource.
- Khi stream phát dữ liệu đa tenant, mỗi event phải thuộc quyền phù hợp hoặc stream phải được tạo từ scope đã được kiểm tra.
- Nếu quyền bị revoke trong một kết nối dài, quyết định cách cập nhật quyền/đóng stream; initial auth không mặc định bảo vệ vô thời hạn.
- Không tạo `Flux.share()` toàn cục phát dữ liệu của mọi tenant rồi lọc muộn theo request.
- Với SSE cross-origin, CORS allowlist, cookie/security/session policy riêng vẫn áp dụng. SSE không tự bảo vệ CSRF cho các endpoint cập nhật khác.

### 12.3. Không block Reactor event loop

Nếu bạn dùng WebClient/Reactor Netty trong một MVC controller, tránh gọi `.block()` trên Reactor event loop hoặc triển khai business chain chứa `Thread.sleep()` trong operators chạy trên event-loop scheduler. MVC blocking response write sẽ được chuyển sang async executor, nhưng upstream code blocking do bạn viết **vẫn có thể gây nghẽn upstream scheduler**.

## 13. Memory, latency và slow clients

### 13.1. Flux JSON thường gom danh sách

Một Publisher trả 100.000 records với `application/json` thường bị gom theo hướng `List<?>` trước khi Jackson serialize. Memory gồm:
- Java objects trong collection;
- deserialized rows nếu source repository lưu cache;
- JSON serialization buffers;
- servlet response/container output buffers;
- concurrency của các requests khác.

Với volume lớn, nên dùng pagination/limit hoặc streaming media type phù hợp. Streaming NDJSON giảm nhu cầu giữ toàn bộ collection nhưng không miễn phí memory; mỗi record vẫn được convert, writer/coder vẫn có buffers, và slow clients có thể giữ task/thread.

### 13.2. Flux.interval với tần suất cao

`Flux.interval(Duration.ofMillis(1))` có thể phát nhanh hơn client nhận. Nếu không có backpressure policy phù hợp, có thể lỗi overflow/drop/buffer tăng. Giảm phát event, batch/dedupe, giới hạn queue, có deadline và cân nhắc sampling. SSE thích hợp cho thông báo nhẹ; không phù hợp để truyền ảnh/video hoặc file nhiều GiB chỉ vì hỗ trợ streaming.

### 13.3. Executor saturation

Nếu mỗi blocking write giữ thread trong một khoảng dài, một pool nhỏ có thể đầy. Với pool `core=4 max=8 queue=64` của demo:
- Có tối đa 8 threads do executor quản lý theo cấu hình.
- Queue có giới hạn và request/task có thể bị từ chối khi quá tải.
- Một queue lớn thường trì hoãn response và tăng latency tail thay vì tăng throughput thực.

Không tuyên bố “8 threads là đủ cho 8, 80 hay 800 SSE users” khi chưa đo; mức thread occupancy phụ thuộc tốc độ network, flush, container, streaming cadence và cách framework lập lịch viết. Cần tải thử với slow consumers thực.

### 13.4. Proxy buffering và headers

Một SSE app chạy trực tiếp trên localhost thấy events từng 200 ms, nhưng qua reverse proxy có thể bị gom cho đến khi buffer đầy. Tùy infrastructure:
- cấu hình tắt buffering cho route SSE được xác thực;
- thiết lập idle/read timeouts phù hợp;
- gửi heartbeat khi cần và có giá trị;
- test `curl -N` qua URL public, không chỉ localhost;
- xác nhận CDN/load balancer hỗ trợ streaming.

Không tự khuyên đặt `X-Accel-Buffering: no` ở mọi môi trường như một chuẩn HTTP phổ quát; đây là chỉ dẫn dành cho một số proxy như Nginx và còn phụ thuộc cấu hình upstream. Cân nhắc nó khi topology tương ứng có mặt.

## 14. Lựa chọn công cụ theo yêu cầu

| Yêu cầu | Phương án phù hợp trong MVC | Cảnh báo |
| --- | --- | --- |
| Một kết quả có thể có sau vài trăm ms | `Mono<T>`, `CompletableFuture<T>`, `DeferredResult<T>` | Không block upstream scheduler |
| Status phụ thuộc kết quả async | `Mono<ResponseEntity<T>>` | Xử lý error trước commit |
| Status/headers tĩnh, body đến sau | `ResponseEntity<Mono<T>>` | Đừng mong thay status lúc body lỗi |
| JSON collection nhỏ, hữu hạn | `Flux<T>` + `application/json` | Buffer toàn collection |
| Thông báo một chiều liên tục | `Flux<ServerSentEvent<T>>` + SSE, hoặc `SseEmitter` | Timeout, connection, worker threads |
| Nhiều JSON records phát dần | `Flux<T>` + NDJSON converter | Media type, flush, interoperability |
| Tải file/binary stream | `StreamingResponseBody`/`Resource` | Blocking write, bandwidth, errors after commit |
| End-to-end non-blocking HTTP writes | Spring WebFlux | Cần chọn reactive server stack đúng |
| JDBC/JPA blocking business logic | MVC hoặc boundedElastic bridge có cân nhắc | Reactor type không biến JDBC non-blocking |

Không chọn reactive return type chỉ để né thread pool quan trọng: hãy xác định **bottleneck ở request worker, upstream client, DB hay response writer** rồi dùng async/web framework đúng nhu cầu.

## 15. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng khắc phục |
| --- | --- | --- |
| `Mono<T>` bị trả như một object wrapper | MVC không nhận biết adapter/dependency hoặc method không trả body | Kiểm tra Reactor classpath, `@RestController`, converter |
| Flux JSON không tới từng phần tử ngay | `application/json` được gom thành List | SSE/NDJSON khi cần stream |
| Flux vô hạn treo request, tăng RAM | Non-streaming collection không kết thúc | Chuyển streaming media, limit/timeouts |
| SSE chạy local nhưng browser nhận một lượt | Proxy/client output buffering | Test `curl -N`, kiểm tra ingress |
| SSE ngắt sau 15 giây | Async timeout demo hoặc proxy timeout | Cấu hình timeout/heartbeat phù hợp |
| CPU/thread cao dù return Flux | MVC writes vẫn blocking | AsyncTaskExecutor bounded, đo slow clients/WebFlux |
| `Async support must be enabled` | Servlet/filter registration thiếu asyncSupported | Sửa Servlet/filter config & dispatcher types |
| `subscribe()` thủ công làm response rỗng | Subscription nằm ngoài MVC lifecycle | Return Mono/Flux trực tiếp |
| `.block()` làm chết throughput | Blocking upstream/event loop | Dùng nguồn nonblocking hoặc boundedElastic |
| Timeout không ra JSON error chuẩn | Response SSE đã committed | Event protocol/close/cancel/reconnect |
| Error handler thay status thất bại | Headers/body đã gửi | Xử lý errors trước streaming khi có thể |
| MDC/SecurityContext mất | Async thread boundaries | Context propagation hoặc explicit context |
| Backpressure overflow | Hot producer nhanh hơn slow subscriber | Bounded buffer/drop policy có chủ đích |
| MockMvc test trả body trống | Quên `asyncDispatch` | Assert asyncStarted + asyncDispatch |
| SSE nhận dữ liệu sai tenant | Subscription không scope authorization | Kiểm tra quyền mỗi channel/data source |
| Flux/Mono return nhưng không có Reactor | Thiếu dependency `reactor-core` | Thêm version do BOM quản lý |
| 5xx khi executor quá tải | Bounded executor/queue đã saturation | Rate limit, shed load, tăng capacity có số liệu |

## 16. Checklist production

1. Server đang dùng đúng **Spring MVC Servlet stack**, không nhầm với WebFlux khi chỉ thêm Reactor Core.
2. Return type có semantics phù hợp: 0..1 `Mono` hay 0..N `Flux`.
3. Endpoint định nghĩa media type rõ: JSON array hay SSE/NDJSON streaming.
4. Publisher là **hữu hạn** nếu output non-streaming; có pagination, timeout và cap.
5. Async Servlet support, filter dispatch types và MVC `AsyncTaskExecutor` được cấu hình/test.
6. Có đo số async requests, executor queue/active threads, slow clients và time-to-first-byte.
7. Có policy khi producer nhanh hơn consumer, buffer/drop strategy được nghiệp vụ chấp thuận.
8. HTTP response status/headers được quyết định trước khi write; lỗi sau commit dùng stream protocol/cancel.
9. Long-lived connections có timeout, heartbeat, reconnection IDs và quotas phù hợp.
10. Khi client ngắt kết nối, upstream subscriptions và resources được cleanup.
11. Security/auth/tenant scope, CSRF/CORS và permission changes được xử lý đúng.
12. ThreadLocal/MDC/locale/request context chỉ được dùng qua propagation tin cậy.
13. Integration test qua reverse proxy xác nhận streaming/flush thật, không chỉ test body cuối MockMvc.
14. Với Boot 4/Spring 7, kiểm tra starter/test package thay đổi trước khi copy code Boot 3.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Trả `Mono<BookView>` trong `@RestController` MVC có buộc phải dùng WebFlux server không?

**Đáp án:** Không. MVC thông qua `ReactiveAdapterRegistry` thích ứng reactive return type với Servlet async processing. Chỉ cần thư viện Reactor tương thích.

**Câu 2.** `Flux<BookView>` với `produces="application/json"` có gửi ngay từng object không?

**Đáp án:** Không mặc định; MVC có xu hướng gom multi-value stream thành List rồi serialize một JSON array.

**Câu 3.** Muốn browser nhận từng notification, nên dùng media type nào?

**Đáp án:** `text/event-stream` với `Flux<ServerSentEvent<T>>` hoặc `SseEmitter`; nhớ proxy buffering và timeout.

**Câu 4.** Vì sao vẫn phải cấu hình `AsyncTaskExecutor` dù source là Flux non-blocking?

**Đáp án:** Vì Servlet MVC vẫn ghi response bằng **blocking write** trên worker thread; không nên block upstream Reactor event loop.

**Câu 5.** `Mono<ResponseEntity<BookView>>` khác `ResponseEntity<Mono<BookView>>`?

**Đáp án:** Cái đầu quyết định cả status/headers/body bất đồng bộ; cái sau biết status/headers ngay, chỉ body phát sau.

**Câu 6.** Khi SSE đã gửi event đầu, có thể đổi status 200 thành 500 rồi trả ProblemDetail JSON không?

**Đáp án:** Không bảo đảm vì response có thể đã committed. Thiết kế error event/connection close và retry policy riêng.

**Câu 7.** `Flux.interval(1ms)` phát liên tục có tự bảo đảm không tràn bộ nhớ khi client chậm không?

**Đáp án:** Không. Cần backpressure behavior/source policy, bounded buffers, quotas và cancellation.

**Câu 8.** MockMvc test `Mono.delay` nên kiểm tra thế nào?

**Đáp án:** `request().asyncStarted()` rồi `asyncDispatch(result)` để assert status/JSON sau async completion.

**Câu 9.** Có nên dùng `.subscribe()` ở controller rồi tự trả null?

**Đáp án:** Không; làm mất integration giữa publisher và response lifecycle. Return publisher.

**Câu 10.** Khi nào nên chọn WebFlux thay MVC?

**Đáp án:** Khi cần non-blocking HTTP I/O và reactive pipeline toàn diện, đặc biệt high-concurrency streaming/slow clients; lựa chọn dựa trên benchmark và độ phức tạp code, không chỉ dựa vào tên Mono/Flux.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Servlet async, Reactive Types, write blocking, backpressure, context propagation và executor.
- [Spring Framework — Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): Mono/Flux adapter, streaming vs JSON collection, DeferredResult và emitters.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): `ResponseEntity<Mono<T>>` và `Mono<ResponseEntity<T>>`.
- [Spring Framework 6.2 — HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html#_http_streaming): SSE, ResponseBodyEmitter và StreamingResponseBody.
- [Spring Framework 6.2 — MVC Async Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html#_configuration): `WebMvcConfigurer#configureAsyncSupport`, task executor và timeout.
- [Spring Framework — ReactiveAdapterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html): Reactive Streams adapters.
- [Spring Framework 6.2 — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): SSE event representation.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, schedulers, backpressure, cancellation, testing.
- [Spring Boot 3.5 — Web Servlet Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet MVC stack, embedded containers.
- [Spring Boot 4 — Build Systems/Starters](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html): thay đổi starter khi nâng cấp Boot 4.

**Kết luận:** trong Spring MVC, **Mono = kết quả bất đồng bộ đơn**, **Flux + JSON thường = gom thành mảng**, **Flux + SSE/NDJSON = streaming**. MVC có thể quản lý backpressure và Servlet async request lifecycle, nhưng **response writes vẫn blocking** và dùng `AsyncTaskExecutor`. Để stream production an toàn phải kiểm soát executor, bộ nhớ, timeout, producer speed, cancellation, proxy buffering và lỗi sau khi response committed; chỉ trả về kiểu reactive không biến ứng dụng MVC thành WebFlux.
