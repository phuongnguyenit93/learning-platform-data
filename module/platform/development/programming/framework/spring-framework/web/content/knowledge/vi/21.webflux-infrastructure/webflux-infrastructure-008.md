# Máy chủ reactive, kết nối và khác biệt với mô hình Servlet trong Spring WebFlux

## 1. Vấn đề: nhiều kết nối HTTP có cần từng ấy thread?

Một API có 20.000 client đang giữ HTTP connections, nhưng mỗi request chỉ làm một số việc ngắn rồi đợi remote service hoặc streaming event. Nếu mỗi lượt xử lý bị gắn với một Java worker thread **đang chờ I/O blocking**, khả năng mở rộng sẽ chịu áp lực bởi số thread, stack memory và context switching. Reactive server chọn cách khác: theo dõi socket readiness, cho một tập nhỏ các **event-loop threads** phục vụ nhiều channels, và nối tác vụ bất đồng bộ qua `Publisher`, `Mono` và `Flux` thay vì giữ worker chỉ để đợi I/O.

Nhưng câu “WebFlux một thread phục vụ hàng nghìn kết nối” cũng dễ gây hiểu lầm:

- **Connection không đồng nghĩa request**, đặc biệt với HTTP keep-alive và HTTP/2 multiplexing.
- **Request không đồng nghĩa thread**. Một request có thể bắt đầu trên event loop, đi qua các publishers/schedulers, rồi kết thúc trên một execution context khác.
- **Reactive không đồng nghĩa tự động nhanh hơn** trong mọi workload. Các tác vụ CPU-bound vẫn tốn CPU; JDBC blocking, `Thread.sleep` hoặc `Future.get` đặt sai vị trí vẫn có thể nghẽn event loop.
- **WebFlux không bắt buộc dùng Netty.** Spring có adapters cho Reactor Netty, Tomcat/Jetty và các Servlet containers với non-blocking I/O. Spring Boot WebFlux mặc định dùng Reactor Netty khi dependency starter mặc định được giữ.
- **Servlet không đồng nghĩa một thread sống cùng một TCP connection.** Tomcat có non-blocking connector; Spring MVC có Servlet asynchronous processing. Sự khác biệt chủ yếu ở **hợp đồng ứng dụng và request processing model**, không thể quy thành server nào “có NIO” và server nào “không NIO”.

Bài học giải thích hạ tầng WebFlux từ TCP socket đến response, event loop, backpressure và connection reuse; so sánh Servlet MVC synchronous/MVC async/WebFlux; rồi cung cấp demo Spring Boot 3 + Java 17 cùng WebTestClient để kiểm chứng HTTP behavior mà không bịa các con số thread/throughput.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **TCP connection**, **HTTP request**, **response**, **Reactor Netty Channel**, **event-loop thread**, **Servlet worker thread** và **WebClient outbound connection pool**.
2. Vẽ request pipeline từ Reactor Netty tới `HttpHandler`, `WebHandler`, `DispatcherHandler`, Controller/functional handler, codecs và response.
3. Giải thích tại sao non-blocking I/O giảm thời gian chiếm thread khi chờ, nhưng không xóa công việc CPU, database hoặc network.
4. Phân biệt synchronous Servlet MVC, Servlet MVC async và WebFlux chạy trên Netty hoặc Servlet adapter mà không đưa ra so sánh sai.
5. Hiểu `Mono<Void>` khi ghi response, `Flux<DataBuffer>`, Reactive Streams demand, cancellation, streaming media types và HTTP backpressure.
6. Quản lý timeout, keep-alive, client connection pool, TLS, proxy, graceful shutdown, metrics và tránh blocking trên event loop.
7. Chạy ứng dụng demo reactive trên Reactor Netty và dùng WebTestClient xác nhận 200/400/204, reactive delay, SSE, filter và error policy.

**Phạm vi:** Spring Framework 6.x, Spring Boot 3.3.x, Reactor 3.x, Reactor Netty trong Servlet-vs-reactive context. Mọi giá trị performance/thread count được trình bày như nguyên tắc hoặc ví dụ minh họa, **không** gán thành benchmark thực tế của một hệ thống chưa đo.

## 2. Định nghĩa đúng: connection, request, thread, channel

### 2.1. TCP connection

TCP connection là kênh truyền byte giữa hai endpoints (IP/port và trạng thái TCP tương ứng), thường sống lâu hơn một request HTTP/1.1 khi dùng **keep-alive**. Một connection có thể chở nhiều HTTP requests tuần tự qua keep-alive; phía HTTP/2, nhiều logical streams có thể **đồng thời** chia sẻ một TCP/TLS connection.

Một connection còn cần file descriptor/socket buffers, flow-control state, TLS state khi có HTTPS và các cấu trúc trong HTTP server. Vì vậy không nên tin câu “event loop nhẹ nên connection không tốn gì”.

### 2.2. HTTP request và response

Một request là một trao đổi HTTP logic, ví dụ `GET /api/ping`. Phản hồi `200` có body, `204` không có body, hoặc event stream kéo dài. Một kết nối có thể chở nhiều request, và một request có thể tiếp tục qua nhiều bước async.

```text
HTTP/1.1 keep-alive trên một TCP connection:
  TCP connection ─ GET /a → 200 ─ GET /b → 200 ─ GET /c → 404 ─ close

HTTP/2 trên một TCP/TLS connection:
  Connection ─ stream 1: GET /events ───── nhiều DATA frames ───
             ├ stream 3: GET /api/a ─ 200
             └ stream 5: GET /api/b ────── 200
```

**Không suy ra:** 1000 concurrent requests nhất thiết là 1000 TCP connections. HTTP version, keep-alive, proxy, connection limits và client behavior quyết định mối quan hệ ấy.

### 2.3. Netty Channel

Trong Netty, `Channel` là abstraction của một I/O connection hoặc endpoint. `ChannelPipeline` chứa handlers chịu trách nhiệm xử lý inbound/outbound events và protocol transformations. Một channel thường gắn với một `EventLoop` chịu trách nhiệm I/O events của channel ấy; event loop có thể phục vụ **nhiều** channels.

### 2.4. Event-loop thread

Event loop chạy các callbacks cho I/O-ready events và scheduled tasks. Thay vì một thread ngủ chờ một socket, event loop xử lý ngắn gọn những event đã sẵn sàng. Nếu một callback gọi `Thread.sleep(2000)` hay blocking JDBC, **các channels khác cùng loop** có thể bị chậm theo.

Số lượng event-loop threads **phụ thuộc phiên bản, CPU, cấu hình, native transport và môi trường chạy**; không hardcode “luôn 1 loop/1 core” hoặc “chỉ có 2 threads”.

### 2.5. Servlet request worker thread

Trong Spring MVC synchronous, một worker thread thường chạy toàn bộ filter/controller/render sequence của **một request** và có thể bị giữ trong lúc dùng blocking APIs. Nhưng một TCP connection keep-alive **không bị ghim cùng một thread mọi thời điểm**. Connector Tomcat vẫn có cơ chế NIO theo dõi sockets; thread pool thường liên quan tới việc thực thi request processing chứ không đồng nhất connection count.

## 3. So sánh ba mô hình cùng một công việc

Giả sử API gọi một remote HTTP service cần 300 ms để phản hồi; business code hầu như không dùng CPU.

### 3.1. Spring MVC synchronous

```text
TCP socket ─ Servlet container/connector
                    │ request sẵn sàng
                    ▼
              Worker thread T1
                 ├─ Servlet Filters
                 ├─ DispatcherServlet
                 ├─ @Controller
                 ├─ blocking HTTP client call: chờ ~300ms
                 ├─ JSON serialize
                 └─ HTTP response
                    T1 trở về pool
```

Ở kiểu ứng dụng này, một worker có thể bị chiếm 300 ms dù ít tính toán. Nếu tất cả worker bận chờ, request mới có thể xếp hàng/reject theo server policy.

### 3.2. Spring MVC với Callable/DeferredResult

```text
Servlet worker T1:
  DispatcherServlet → Controller trả Callable / DeferredResult
  → Servlet async start → T1 được trả về pool

Callable: MVC AsyncTaskExecutor worker T2
  → blocking remote call (~300ms) → result

hoặc DeferredResult:
  → kết quả được producer callback/event điền vào

Servlet worker T3:
  ASYNC dispatch → serialize/write response → kết thúc
```

Servlet async giúp **giải phóng container thread ban đầu**, nhưng `Callable` đang chạy blocking operation vẫn giữ một executor worker; `DeferredResult` có thể giảm thread chờ nếu producer thật sự event-driven. MVC async không tự tạo non-blocking database/client API.

### 3.3. Spring WebFlux với non-blocking HTTP client

```text
Reactor Netty event-loop:
  HTTP request received
    → WebFlux handlers
    → WebClient reactive request được khởi tạo
    → Publisher chưa có kết quả; callbacks được đăng ký
    → event-loop không ngồi sleep chờ remote response

Khi remote HTTP data đến:
  → network readiness event
  → Reactor operator callbacks
  → HTTP codecs encode response
  → non-blocking write khi channel sẵn sàng
```

Với WebClient/driver thực sự non-blocking, không cần giữ một Java worker chỉ để chờ network. Vẫn có CPU để parse/serialize, TLS, xử lý business, và vẫn có thread pools riêng cho một số công việc.

### 3.4. Bảng khác biệt tổng hợp

| Câu hỏi | MVC sync (Servlet) | MVC async (Servlet) | WebFlux reactive |
| --- | --- | --- | --- |
| Điểm vào HTTP | Servlet/DispatcherServlet | Servlet/DispatcherServlet + async | HttpHandler/WebHandler/DispatcherHandler |
| Return type phổ biến | DTO, String, ResponseEntity | Callable, DeferredResult, CompletableFuture | Mono, Flux, Publisher, Coroutine |
| I/O downstream | Thường blocking nhưng có thể dùng async client | Blocking worker hoặc callback async | Thiết kế hướng non-blocking; vẫn có thể gọi blocking sai cách |
| Thread khi chờ | Worker request có thể chờ | Servlet thread rảnh; worker riêng có thể chờ | Không cần worker chờ nếu dependency reactive |
| Xử lý backpressure | Không phải hợp đồng chính của controller sync | Tùy async/streaming APIs | Reactive Streams demand xuyên publishers và server adapters khi hỗ trợ |
| Server runtime | Tomcat/Jetty/Undertow, Servlet | Tomcat/Jetty/Undertow, Servlet async | Reactor Netty mặc định Boot; cũng có Tomcat/Jetty/adapters |
| Phù hợp | Logic imperative/blocking, ecosystem Servlet | Async callback hoặc giải phóng Servlet thread | Nhiều concurrent I/O, streaming, reactive dependencies |
| Điều phải đo | pool saturation/queue | executor/timeout/cancellation | event-loop lag, buffers, demand, cancellation, connector pool |

**Không có người thắng mặc định.** MVC thường đơn giản hơn nếu toàn bộ stack JDBC và library đều blocking; WebFlux phát huy khi HTTP client, DB driver, broker adapters và serialization pipeline được thiết kế đúng non-blocking. Với workload CPU-bound, reactive không tự giúp tính nhanh hơn.

## 4. Spring WebFlux có bắt buộc Reactor Netty không?

**Không.** Spring WebFlux nằm ở web framework layer, dưới đó có adapter cho HTTP runtimes.

Spring Framework phân tầng:

```text
@REST Controller / RouterFunction
            │
            ▼
       DispatcherHandler
            │
            ▼
         WebHandler
            │
            ▼
        HttpHandler
            │
            ├── ReactorHttpHandlerAdapter → Reactor Netty
            ├── ServletHttpHandlerAdapter → Servlet container
            ├── Tomcat/Jetty adapters theo stack/version
            └── HTTP server adapter khác được framework hỗ trợ
```

Tên adapter và cách triển khai chính xác có thể khác theo Spring Framework version và embedded server. Điểm ổn định là **`HttpHandler` contract** có thể thích nghi với nhiều runtimes.

Trong Spring Boot **3.3.x**:

- `spring-boot-starter-webflux` mặc định đưa vào `spring-boot-starter-reactor-netty`, nên embedded server mặc định là **Reactor Netty**.
- Có thể thay server starter Netty bằng Tomcat/Jetty/Undertow **trong cấu hình Boot 3.3 phù hợp**. Khi đó ứng dụng vẫn là **WebFlux programming model**, không phải tự chuyển sang Spring MVC.
- Nếu đồng thời thêm `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường **ưu tiên MVC/Servlet web application type**. Đừng dùng việc có `Mono`/`Flux` trong classpath để suy ra server đang chạy WebFlux.
- Khi dùng WebFlux trên Tomcat/Jetty, HTTP non-blocking I/O được bridge từ Servlet support; đừng nói Tomcat “không thể chạy reactive”.
- Netty tự nó **không phải** Servlet container. Reactor Netty sử dụng Netty API/event loop, không thông qua DispatcherServlet.

### 4.1. Netty và Servlet container khác nhau ở API tầng dưới

| Thành phần | Reactor Netty runtime | Servlet container dùng cho MVC |
| --- | --- | --- |
| HTTP entrypoint | Netty Channel/Pipeline, Reactor HTTP adapters | Servlet request/response và Servlet filters |
| Java web framework | WebFlux WebHandler/DispatcherHandler | Spring MVC DispatcherServlet |
| I/O primitives | Netty asynchronous channel I/O | Servlet container connectors (có NIO), Servlet request/response APIs |
| Async semantics | Reactive Publisher, event-driven flow | Servlet async `AsyncContext` hoặc synchronous handler |
| Web filters | WebFlux `WebFilter`, `WebExceptionHandler` | Servlet `Filter`, Spring Security Servlet chain |
| Request objects | `ServerHttpRequest`, `ServerWebExchange` | `HttpServletRequest`/`HttpServletResponse` |
| Main risk | Blocking event loop, unbounded buffers | Worker pool saturation, blocking wait, queue pressure |

**Từ “Servlet container” không đồng nghĩa “blocking TCP socket API”.** Các containers hiện đại có non-blocking transport và asynchronous Servlet I/O, nhưng servlet-style controller code vẫn có thể block workers.

### 4.2. Boot chọn web application type

Ví dụ `pom.xml` chỉ gồm WebFlux starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Mặc định Boot tạo **reactive** application context và Reactor Netty embedded server.

Ví dụ chuyển embedded server sang Tomcat trên Boot 3.3 (mẫu thay thế dependencies; không đặt đồng thời hai server starters một cách vô ý):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
```

Đây là một **biến thể thay thế** cho `pom.xml` demo ở mục 11, không kết hợp trực tiếp với dependency WebFlux starter vẫn giữ Reactor Netty. Khi thay server, test TLS/HTTP2/Servlet filters và resource management riêng.

## 5. HTTP server pipeline trong WebFlux

### 5.1. HttpHandler: contract tối thiểu

Trong Spring reactive HTTP layer, `HttpHandler` có thể hiểu dưới dạng:

```java
public interface HttpHandler {
    Mono<Void> handle(
        ServerHttpRequest request,
        ServerHttpResponse response);
}
```

Đây là chữ ký cốt lõi để giải thích; các interfaces thuộc package `org.springframework.http.server.reactive`. Kết quả `Mono<Void>` biểu diễn **quá trình hoàn tất việc xử lý HTTP response**, không phải một DTO/body duy nhất.

Spring triển khai/adapt contract này vào server API cụ thể:

- Reactor Netty: Netty inbound/outbound APIs.
- Servlet non-blocking bridge: HTTP request/response có thể được chuyển qua adapters sang Publisher-based body flow.
- Các server adapters khác theo version.

Bạn thường **không phải tự viết HttpHandler** trong Boot app; Boot và WebFlux auto-configuration lắp framework pipeline.

### 5.2. WebHandler và ServerWebExchange

`WebHandler` contract:

```java
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
```

`ServerWebExchange` gom request, response, session, attributes, locale/principal-related APIs và các context cần để xử lý một HTTP exchange. Nó **không phải** `HttpServletRequest`. Nếu chạy Reactor Netty, không có Servlet request native để ép cast.

Các lớp đại diện:

| Class/interface | Trách nhiệm |
| --- | --- |
| `HttpHandler` | Contract server-independent cho HTTP exchange |
| `ServerHttpRequest` | Reactive request abstraction, headers/method/body |
| `ServerHttpResponse` | Reactive response abstraction, status/headers/write |
| `WebHandler` | Contract xử lý một `ServerWebExchange` |
| `WebFilter` | Functional WebFlux filter chain ở tầng WebHandler |
| `WebExceptionHandler` | Xử lý lỗi trong reactive web chain |
| `DispatcherHandler` | WebFlux front controller tìm handler/router |
| `HandlerMapping` | Chọn controller/function dựa trên request |
| `HandlerAdapter` | Gọi handler tương ứng |
| `HandlerResultHandler` | Chuyển return value sang HTTP response |
| `HttpMessageReader/Writer` | Codec đọc/ghi body theo media type |
| `DataBuffer` | Buffer abstraction dùng cho body stream |

### 5.3. Full request flow

```text
Client TCP/TLS connection
    │ (HTTP/1.1 hoặc HTTP/2; Netty Channel)
    ▼
Reactor Netty event-loop / HTTP codecs
    ▼
ReactorHttpHandlerAdapter
    ▼
HttpHandler (Spring WebFlux)
    ▼
HttpWebHandlerAdapter / WebFilter chain
    ▼
DispatcherHandler
    ├── HandlerMappings → tìm @Controller hoặc RouterFunction
    ├── HandlerAdapter → invoke handler
    └── HandlerResultHandler → encode result
            │
            ├── Mono<DTO>       → JSON object hoặc response logic
            ├── Flux<DTO>       → finite JSON array / streaming khi phù hợp
            ├── Mono<Void>      → completion không cần body value
            └── Flux<DataBuffer> → body bytes theo demand
    ▼
ServerHttpResponse non-blocking write
    ▼
Netty outbound Channel → socket → client
```

Trên error path, WebFlux exception handling/filter chain có thể xử lý lỗi trước khi response committed. Nếu server đã flush một số SSE/stream bytes, không luôn chuyển được HTTP status từ 200 sang 500; phải dùng protocol-level error event hoặc kết thúc stream theo hợp đồng.

### 5.4. Các tầng codec và giới hạn buffer

Trước khi handler nhận object `@RequestBody Mono<MyDto>`, HTTP body bytes qua readers/decoders như Jackson. Khi handler trả Flux, encoding behavior phụ thuộc media type và codec.

Với `application/json`, một Flux hữu hạn thường được encode thành JSON array; **không cam kết flush từng item ngay khi onNext xuất hiện**. Với `text/event-stream` hoặc newline-delimited JSON, streaming semantics rõ ràng hơn.

Spring Boot có property:

```properties
spring.codec.max-in-memory-size=256KB
```

Đây là giới hạn in-memory buffering khi codecs cần aggregate, không phải giới hạn tổng số bytes mỗi TCP connection hay bộ nhớ toàn bộ JVM. Trường hợp body lớn phải cân nhắc streaming readers, uploads, max request size tại proxy/server và chính sách lưu trữ. Lỗi `DataBufferLimitException` thường liên quan tới giới hạn codec aggregation.

## 6. Event loop thực thi request như thế nào?

### 6.1. Sơ đồ một vòng xử lý

```text
Nhiều channels cùng được gán cho các event loops:

Channel A: data ready  ───┐
Channel B: idle         ───┤      EventLoop #1
Channel C: write ready ───┘       ├─ đọc bytes A
                                 ├─ decode HTTP request A
                                 ├─ gọi các non-blocking Reactor callbacks
                                 └─ flush bytes C khi writable

Channel D: data ready  ───┐
Channel E: idle         ───┤      EventLoop #2
Channel F: stream       ───┘       ├─ xử lý D
                                 └─ tiếp tục F khi có demand/ready
```

Đây là sơ đồ **minh họa**, không phải khẳng định mỗi instance dùng đúng hai loops. Event loop có thể thực thi scheduled tasks, channel callbacks, TLS encode/decode và logic framework. Nó phải tránh công việc blocking kéo dài để các channels khác không bị starve.

### 6.2. Đâu là công việc hợp lý trên event loop?

- Parse header/kết nối, route handler nhẹ.
- Compose reactive Publishers.
- Mapping/validation/serialization có chi phí vừa phải.
- Scheduling network writes và reactive callbacks ngắn.

### 6.3. Công việc không nên giữ event-loop

- `Thread.sleep(1000)` hoặc `CompletableFuture.get()` chặn.
- JDBC/JPA query blocking.
- Gọi HTTP bằng client đồng bộ hoặc `RestTemplate` trong path event-loop.
- Đọc/ghi file lớn theo Java blocking I/O trực tiếp.
- Tính CPU nặng hàng trăm ms, mã hóa/giải nén lớn trên loop.
- Thao tác database transaction dài trong code imperative.

**Một request blocking có thể làm chậm nhiều requests khác** nếu chúng chia sẻ event loop. Khi debugging hãy xem thread dump, event-loop latency, BlockHound (nếu cấu hình cho test), request queue và upstream timeouts; không chỉ số HTTP 500.

### 6.4. Mono/Flux không tự biến blocking thành non-blocking

Sai:

```java
@GetMapping("/bad")
Mono<String> bad() {
    return Mono.just(legacyBlockingClient.call());
}
```

`legacyBlockingClient.call()` chạy **ngay lúc controller được gọi**, trước khi Mono được tạo. API trả Mono không thay đổi tính blocking của lời gọi này.

Cũng chưa đủ:

```java
@GetMapping("/still-bad")
Mono<String> badToo() {
    return Mono.fromCallable(() -> legacyBlockingClient.call());
}
```

Đoạn này **lazy** nhưng khi subscribe vẫn có thể chạy trên event loop nếu không chọn scheduler thích hợp. Khi buộc phải bridge một blocking API, dùng giải pháp tạm:

```java
@GetMapping("/bridge")
Mono<String> bridge() {
    return Mono.fromCallable(() -> legacyBlockingClient.call())
        .subscribeOn(Schedulers.boundedElastic());
}
```

Snippet cần `legacyBlockingClient` dependency và Reactor imports. `boundedElastic` là scheduler được giới hạn phù hợp hơn với blocking tasks, nhưng không biến JDBC thành non-blocking; nếu pool/queue bão hòa vẫn có delay/reject. Ưu tiên R2DBC, WebClient hoặc reactive clients nếu cần non-blocking end-to-end.

### 6.5. CPU-bound không được che dưới boundedElastic

Nếu task là transform cryptography/compression/ML rất nặng, việc dùng boundedElastic (thiết kế chủ yếu cho blocking waits) không đảm bảo latency. Dùng bounded compute executor/scheduler theo tài nguyên CPU với workload/queue policy đúng, hoặc tách dịch vụ/worker job khi cần. Reactor `Schedulers.parallel()` hỗ trợ các tác vụ CPU ngắn/phù hợp, nhưng cần tránh monopolize worker thread bằng loops vô hạn.

## 7. Backpressure từ Publisher đến network

Reactive Streams phân biệt:

- **Publisher** có khả năng phát dữ liệu.
- **Subscriber** nhận dữ liệu.
- **Subscription** quản lý request(n)/cancel.
- **Demand**: downstream muốn thêm bao nhiêu items.

Ví dụ:

```text
Flux.just(1,2,3,4,5)
       │
       ▼
Subscriber request(2)
       │
       ├── onNext(1)
       └── onNext(2)
       │
Subscriber request(3)
       ├── onNext(3)
       ├── onNext(4)
       └── onNext(5)
       │
       └── onComplete()
```

Với WebFlux, HTTP readers/writers và Reactor Netty liên kết downstream readiness/buffering với reactive subscriptions trong những hoàn cảnh hỗ trợ. Nhưng phải phân biệt ba lớp flow control:

1. **Reactive Streams demand** giữa Publisher/Subscriber trong JVM.
2. **TCP flow control** dựa vào receive window/network stacks.
3. **HTTP/2 stream/connection flow control** tại protocol layer.

Chúng có tương tác nhưng **không phải một đối một** và không đảm bảo mọi external producer tuân thủ demand. Một upstream broker callback push liên tục có thể tạo `Flux` vượt tốc độ client; bạn phải đặt policy buffer/drop/error và quan sát memory.

### 7.1. Streaming và JSON array

```java
@GetMapping("/api/numbers")
Flux<Integer> numbers() {
    return Flux.range(1, 5);
}
```

Với content type JSON thường là body:

```json
[1,2,3,4,5]
```

Response codec có thể buffer và không gửi từng item riêng biệt tới browser theo thời điểm `onNext`. Muốn client thấy event ngay, dùng SSE:

```java
@GetMapping(
        value = "/api/ticks",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> ticks() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(n -> ServerSentEvent.<String>builder()
            .event("tick")
            .data("tick-" + n)
            .build());
}
```

Đây là snippet minh họa trong controller, stream vô hạn **cần xử lý cancellation, timeout và rate-limit** trong production. Dự án runnable mục 11 giới hạn ba events để test dễ.

### 7.2. Streaming cũng cần giới hạn

- `collectList()` phải giữ tất cả items tới khi Flux hoàn tất. Nếu Flux vô hạn, không có result và heap có thể tăng.
- `onBackpressureBuffer()` không giới hạn có thể dẫn tới OOM.
- `Flux.interval(...)` khi consumer chậm có thể phát lỗi overflow tùy strategy; không coi timer là data queue tin cậy.
- `doFinally` hữu ích để thu dọn resource khi stream **complete, error hoặc cancel**.
- WebSocket/SSE nhiều clients cần connection budgets, heartbeat và proxy idle timeouts.

## 8. WebClient outbound connections: khác với inbound server

Một trong những nhầm lẫn phổ biến là coi số HTTP connections do Reactor Netty **server** chấp nhận giống với số connections mà `WebClient` tạo tới remote services.

### 8.1. Inbound server socket

`GET /api/proxy` từ browser vào app: app đang **accept inbound** connection thông qua Reactor Netty HttpServer. Server quản lý channels, request read/write, TLS, keep-alive và event loops.

### 8.2. Outbound WebClient pool

Bên trong handler, WebClient gọi `https://catalog.example.test`: app đóng vai trò **HTTP client**, cần tạo hoặc reuse **outbound connections** tới target host. Reactor Netty HttpClient thường dùng connection pooling phù hợp; có thể quản lý bằng `ConnectionProvider`.

```text
Browser
   ─ TCP/TLS inbound #1 ─► Spring WebFlux / Reactor Netty server
                            │
                            │ WebClient.get(...)
                            ▼
                       HttpClient pool (outbound)
                            │   ├ TCP/TLS outbound A
                            │   ├ TCP/TLS outbound B
                            │   └ pending acquire queue
                            ▼
                      Remote catalog service
```

**Không gán** “1 incoming request = 1 outbound connection”. Outbound connections có thể được reuse; một incoming request có thể fan-out sang nhiều services; pending acquire queue có thể đầy dù inbound server còn nhận socket.

### 8.3. Custom outbound pool ví dụ

Một cấu hình tường minh (đặt trong `@Configuration`; đây là snippet minh họa không phải phần bắt buộc của runnable demo):

```java
@Bean(destroyMethod = "dispose")
ConnectionProvider catalogPool() {
    return ConnectionProvider.builder("catalog-pool")
        .maxConnections(30)
        .pendingAcquireMaxCount(60)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .build();
}

@Bean
WebClient catalogWebClient(WebClient.Builder builder,
                           ConnectionProvider catalogPool) {
    HttpClient client = HttpClient.create(catalogPool)
        .responseTimeout(Duration.ofSeconds(3))
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000);

    return builder
        .baseUrl("https://catalog.example.test")
        .clientConnector(new ReactorClientHttpConnector(client))
        .build();
}
```

Cần imports `reactor.netty.resources.ConnectionProvider`, `reactor.netty.http.client.HttpClient`, `io.netty.channel.ChannelOption`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`, `Duration` và Spring `@Bean`. Host là domain ví dụ, không phải endpoint thật để chạy integration tests. Khi dùng Boot, thường nên **reuse `WebClient.Builder` được Boot cung cấp** thay vì tự new WebClient cho mỗi request.

Ý nghĩa:

- `maxConnections(30)` hạn mức pool trong cấu hình ví dụ, không phải default chung cho Reactor Netty phiên bản bất kỳ.
- `pendingAcquireMaxCount(60)` giới hạn số requests chờ connection khi pool đang bận.
- `pendingAcquireTimeout(2s)` giới hạn thời gian chờ lấy một connection từ pool.
- `CONNECT_TIMEOUT_MILLIS` xử lý timeout của giai đoạn mở TCP connection.
- `responseTimeout` là chính sách thời gian đợi response network I/O của HttpClient; khác timeout nghiệp vụ end-to-end.
- `maxIdleTime` nhằm hạn chế giữ connection idle quá lâu; nên cân nhắc timeout phía remote/proxy.
- `destroyMethod="dispose"` cho custom ConnectionProvider một lifecycle cleanup khi Spring context đóng.

Không sao chép 30/60/2s cho production nếu chưa đo traffic, TLS handshakes, upstream rate limits, p95 response time và pool saturation. Một pool cực lớn có thể khiến upstream/cổng NAT hoặc OS cạn resources. Một pool quá nhỏ lại tạo pending acquire latency và timeout.

### 8.4. Các loại timeout cần phân biệt

| Loại | Liên quan |
| --- | --- |
| TCP connect timeout | Thời gian kết nối tới remote host |
| TLS handshake timeout | Thời gian bắt tay TLS |
| Pool pending acquire timeout | Chờ lấy outbound connection rảnh |
| HTTP response timeout | Chờ response/network progress theo HttpClient semantics |
| Reactive `timeout(Duration)` | Time budget của publisher theo operator |
| Inbound HTTP server idle timeout | Kết nối client tới server không hoạt động |
| Reverse proxy read timeout | Gateway/LB có thể đóng request trước server |
| Business deadline | Toàn bộ tác vụ phải xong trước SLA |

Đặt `timeout(Duration)` vào Mono không nhất thiết **hủy ngay** mọi side effect đã được remote server nhận. Cancellation sẽ propagate qua reactive client khi hỗ trợ, nhưng remote nghiệp vụ có thể vẫn đang chạy; cân nhắc idempotency cho POST, retries và duplicate suppression.

## 9. Thay đổi runtime: Reactor Netty, Tomcat, Jetty

### 9.1. Netty mặc định của Boot

Khi dùng `spring-boot-starter-webflux` mà không loại Netty, Boot thường chọn Netty reactive web server factory. Điều này có lợi khi WebClient cũng dùng Reactor Netty vì có thể chia sẻ một số event-loop resources theo configuration.

### 9.2. WebFlux trên Servlet adapter

Có thể sử dụng Servlet container hỗ trợ async/non-blocking I/O để adapt WebFlux contract. Khi đó app code vẫn return Mono/Flux, còn server adapter ánh xạ reactive read/write lên Servlet non-blocking APIs. **Không** dùng `HttpServletRequest` và `DispatcherServlet` như abstraction trung tâm trong controller WebFlux, chỉ vì runtime là Tomcat.

### 9.3. Spring MVC trên Netty?

Spring MVC thiết kế trên Servlet API; Reactor Netty không phải Servlet container. Vì vậy không suy diễn rằng thay `spring-boot-starter-tomcat` bằng `reactor-netty` sẽ khiến Spring MVC controllers chạy đúng trên Netty như WebFlux. Nếu ứng dụng còn cần Servlet filters, JSP, synchronous servlet integrations, hãy chọn MVC/Servlet runtime phù hợp.

### 9.4. HTTP/2 và TLS

HTTP/2 multiplexing làm thay đổi mapping connection→request. Một connection có thể mang nhiều streams. Bật HTTP/2 còn phụ thuộc TLS/h2 ALPN hoặc h2c, phiên bản Netty/Tomcat/Jetty, reverse proxy và client.

Trong Boot, cấu hình:

```properties
server.http2.enabled=true
```

Chỉ là một phần: kiểm tra protocol negotiation và TLS/certificate/runtime support theo server. Không gắn HTTP/2 đồng nghĩa reactive; MVC/Tomcat cũng có thể phục vụ HTTP/2.

## 10. So sánh performance và giới hạn thực tế

### 10.1. Ít threads không tự động nhanh hơn

Bảng *giả lập để học*, không phải benchmark Spring thực tế:

| Workload | Servlet sync | Reactive non-blocking |
| --- | --- | --- |
| 1 request gọi remote API và chờ 500ms | Một worker có thể bị giữ lúc chờ | Event loop không phải chờ nếu WebClient non-blocking |
| 1000 requests chờ remote API 500ms | Worker/queue có thể chịu áp lực | Có thể giữ nhiều in-flight subscriptions với ít event-loop threads |
| 1 request mã hóa 2GB CPU-intensive | Vẫn phải dùng CPU | Vẫn phải dùng CPU; event-loop còn dễ bị monopolize nếu chạy trực tiếp |
| 1 request JDBC blocking 500ms | Đặc tính blocking rõ ràng | Nếu gọi trực tiếp trong event-loop sẽ gây nghẽn, dù method return Mono |
| Nhiều SSE connections | Servlet async có mô hình phù hợp nếu cấu hình đúng | Reactive streaming/backpressure tương thích tự nhiên |
| 100% cache-hit CDN | Origin có thể không nhận request | Origin cũng có thể không nhận request |

Điều cần đo là **p95/p99 latency, throughput, CPU, active threads, queue lengths, heap, GC, connection metrics, response bytes, event-loop lag** và downstream pool saturation. Không so hai server với thread pool/database config khác nhau rồi kết luận framework quyết định tất cả.

### 10.2. Little's Law và thời gian chờ

Một mô hình quan hệ phổ biến: số requests in-flight trung bình xấp xỉ arrival rate × latency trung bình trong hệ thống ổn định. Nếu nhiều request có latency chủ yếu do I/O wait, concurrency có thể cao dù CPU thấp. Reactive làm mô hình **giữ thread** linh hoạt hơn, nhưng **không biến số in-flight requests hoặc buffer thành zero**.

Ví dụ 200 requests/s × 0,5 giây latency ≈ 100 requests in-flight trung bình. Đây chỉ là ví dụ số học, không hứa server có thể phục vụ vô hạn requests nếu có đủ event-loop threads.

### 10.3. Tài nguyên dễ hết dù event loops ít

- File descriptors và ephemeral ports.
- Heap memory cho request metadata, pending subscriptions, buffers, JSON objects.
- Direct/off-heap buffers trong Netty.
- HTTP client connection pool và DNS/TLS overhead.
- DB connection pool / remote upstream quota.
- Pending writes khi client download chậm.
- Retry storms, timeouts và queue overload.
- CPU spike do codecs, compression và TLS.
- Long-lived SSE/WebSocket state, heartbeat và proxy idling.

Cần thiết kế connection budgets, bulkheads, admission control/rate limit và graceful degradation. Không tạo unbounded queue chỉ vì endpoint được gọi “async”.

## 11. Demo runnable: Spring Boot 3 + Java 17 trên Reactor Netty

Ứng dụng sau minh họa **đúng những khác biệt có thể quan sát trực tiếp** mà không giả vờ đếm event-loop thread bằng tests không ổn định.

Endpoint:

| URL | Return type | Mục đích |
| --- | --- | --- |
| `GET /api/ping` | `Mono<Reply>` | Một kết quả JSON |
| `GET /api/delay?ms=25` | `Mono<Reply>` | Delay không chặn bằng `Mono.delay` |
| `GET /api/blocking-bridge` | `Mono<Reply>` | Offload `Thread.sleep` demo sang `boundedElastic` |
| `GET /api/headers` | `Mono<Map>` | Đọc HTTP headers trong WebFlux, không dùng Servlet request |
| `GET /api/none` | `Mono<ResponseEntity<Void>>` | Explicit HTTP 204 |
| `GET /api/stream` | `Flux<ServerSentEvent<String>>` | Finite SSE stream với 3 events |
| `GET /api/fail` | `Mono<Reply>` | Reactive error đi qua exception handling |
| Tất cả `/api/**` | `WebFilter` | Response header cho biết WebFlux filter đã chạy |

Không dùng dịch vụ remote hoặc database thật, nên dự án có thể chạy sau khi Maven tải dependencies. Đoạn `Thread.sleep` bên trong boundedElastic chỉ làm ví dụ phân biệt event-loop với worker, **không phải phương pháp ưu tiên** cho sản phẩm thật.

### 11.1. Cây thư mục

```text
reactive-server-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── ReactiveServerApplication.java
    │   │   ├── ApiController.java
    │   │   └── ReactiveFilter.java
    │   └── resources/application.properties
    └── test/
        └── java/example/ApiControllerTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-server-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
```

### 11.3. ReactiveServerApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveServerApplication.class, args);
    }
}
```

### 11.4. application.properties

```properties
server.port=8080
spring.codec.max-in-memory-size=256KB
logging.level.reactor.netty.http.server=INFO
```

Property codec là một guardrail khi decoder cần buffering; không có nghĩa “mọi body trên 256KB đều bị từ chối” trong mọi streaming path. Tùy source, filter và decoder, có thể có giới hạn khác từ server/proxy.

### 11.5. ApiController.java

```java
package example;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class ApiController {

    public record Reply(String kind, long value) {}

    @GetMapping("/api/ping")
    public Mono<Reply> ping() {
        return Mono.just(new Reply("pong", 1));
    }

    @GetMapping("/api/delay")
    public Mono<Reply> delay(
            @RequestParam(defaultValue = "25") long ms) {

        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms must be in 0..2000"));
        }

        return Mono.delay(Duration.ofMillis(ms))
                .map(tick -> new Reply("delayed", ms));
    }

    @GetMapping("/api/blocking-bridge")
    public Mono<Reply> bridge() {
        return Mono.fromCallable(() -> {
                // Blocking legacy work được cô lập khỏi event loop.
                TimeUnit.MILLISECONDS.sleep(20);
                return new Reply("bridged", 20);
            })
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/api/headers")
    public Mono<Map<String, String>> headers(
            @RequestHeader(name = "X-Demo", defaultValue = "absent")
                    String demo) {

        return Mono.just(Map.of("demo", demo));
    }

    @GetMapping("/api/none")
    public Mono<ResponseEntity<Void>> none() {
        return Mono.<Void>empty()
                .thenReturn(ResponseEntity.noContent().build());
    }

    @GetMapping(
            value = "/api/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        return Flux.interval(Duration.ofMillis(20))
            .take(3)
            .map(index -> ServerSentEvent.<String>builder()
                .id(Long.toString(index))
                .event("tick")
                .data("tick-" + index)
                .build());
    }

    @GetMapping("/api/fail")
    public Mono<Reply> fail() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "dependency temporarily unavailable"));
    }
}
```

**Code này minh họa gì?**

- `Mono.just` trả một `Reply` ngay mà không cần thêm thread.
- `Mono.delay` phát tín hiệu khi timer scheduler tới hạn, **không dùng `Thread.sleep` trên event loop**.
- `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` cho phép tiếp tục dùng một blocking legacy function ngắn nhưng tránh chặn event-loop. Cần đặt timeout/bulkhead thực ở production.
- `@RequestHeader` vẫn có trong annotated WebFlux, nhưng request infrastructure reactive không yêu cầu `HttpServletRequest`.
- `Mono<Void>.thenReturn(ResponseEntity.noContent())` tạo HTTP 204 một cách tường minh.
- `Flux.interval(...).take(3)` dừng sau 3 events để response hữu hạn, dễ test; stream thật có thể kéo dài và cần cleanup/cancellation.
- Error từ `Mono.error(ResponseStatusException)` được WebFlux error handling chuyển thành status, nếu response chưa committed.

**Không khẳng định một request qua Mono luôn chạy trên một thread cố định.** Các Reactor schedulers và Netty callbacks có thể thay đổi execution context; test body/status là cách xác minh hành vi ổn định, thread name chỉ có giá trị diagnostics.

### 11.6. ReactiveFilter.java

```java
package example;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class ReactiveFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (exchange.getRequest().getPath()
                .value().startsWith("/api/")) {
            exchange.getResponse().getHeaders()
                    .add("X-Processing-Stack", "webflux");
        }
        return chain.filter(exchange);
    }
}
```

Đây là **WebFlux WebFilter**, không phải `jakarta.servlet.Filter`. Trong ứng dụng này, response header `X-Processing-Stack: webflux` giúp test xác nhận filter đi qua chain. Nó không phải security control, và tên header này chỉ để học.

WebFlux Security nếu thêm `spring-boot-starter-security` sử dụng `SecurityWebFilterChain` / reactive authentication/authorization; không tự áp Servlet `SecurityFilterChain` như trong Spring MVC. Với deploy hybrid, phải nhận diện web application type đúng.

### 11.7. Chạy và quan sát bằng cURL

Ở thư mục `pom.xml` với Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Một vài requests:

```bash
curl -i http://localhost:8080/api/ping
curl -i "http://localhost:8080/api/delay?ms=25"
curl -i http://localhost:8080/api/blocking-bridge
curl -i -H "X-Demo: hello" http://localhost:8080/api/headers
curl -i http://localhost:8080/api/none
curl -i "http://localhost:8080/api/delay?ms=-1"
curl -i http://localhost:8080/api/fail
```

Kỳ vọng:

| URL | Status | Body chính |
| --- | ---: | --- |
| `/api/ping` | 200 | `{"kind":"pong","value":1}` |
| `/api/delay?ms=25` | 200 | `{"kind":"delayed","value":25}` |
| `/api/blocking-bridge` | 200 | `{"kind":"bridged","value":20}` |
| `/api/headers` với X-Demo: hello | 200 | `{"demo":"hello"}` |
| `/api/none` | 204 | Không có body |
| `/api/delay?ms=-1` | 400 | Error response do Spring error handler định dạng |
| `/api/fail` | 503 | Error response do Spring error handler định dạng |

Kiểm thử SSE:

```bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream
```

Body dự kiến ở media type SSE (bỏ các response headers thay đổi):

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

Không hardcode thứ tự HTTP headers hay Reactor Netty thread name; cURL `-N` tắt output buffering của riêng curl, không đổi semantics server. Dù dùng Flux streaming, actual flush timing còn phụ thuộc server, client và proxy.

### 11.8. Quan sát điều gì ở logs?

Reactor Netty có thể log lúc HTTP server khởi động, port đang bind và lỗi transport. Không đảm bảo tên thread cụ thể theo version hoặc môi trường. Nếu cần đo event-loop state, dùng metrics/observability phù hợp, thread dumps và load test; không suy từ việc JVM có ít threads ở idle ra khả năng chịu tải peak.

## 12. WebTestClient: kiểm thử API reactive end-to-end

Spring WebFlux thường dùng `WebTestClient`. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `@AutoConfigureWebTestClient`, tests gửi HTTP tới embedded server, kiểm tra Spring routing/filter/codecs/Netty configuration hiệu quả hơn unit-test controller thuần.

File `src/test/java/example/ApiControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void pingIsJsonAndPassesReactiveWebFilter() {
        client.get().uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                    "X-Processing-Stack", "webflux")
            .expectBody()
                .jsonPath("$.kind").isEqualTo("pong")
                .jsonPath("$.value").isEqualTo(1);
    }

    @Test
    void reactiveDelayReturnsExpectedValue() {
        client.get().uri("/api/delay?ms=1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.kind").isEqualTo("delayed")
                .jsonPath("$.value").isEqualTo(1);
    }

    @Test
    void negativeDelayIsRejected() {
        client.get().uri("/api/delay?ms=-1")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void tooLargeDelayIsRejected() {
        client.get().uri("/api/delay?ms=5000")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void blockingBridgeReturnsFromOffloadedPublisher() {
        client.get().uri("/api/blocking-bridge")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.kind").isEqualTo("bridged")
                .jsonPath("$.value").isEqualTo(20);
    }

    @Test
    void requestHeaderIsAvailableThroughWebFlux() {
        client.get().uri("/api/headers")
            .header("X-Demo", "checked")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.demo").isEqualTo("checked");
    }

    @Test
    void noBodyEndpointReturns204() {
        client.get().uri("/api/none")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void reactiveErrorMapsTo503() {
        client.get().uri("/api/fail")
            .exchange()
            .expectStatus().isEqualTo(503);
    }

    @Test
    void sseEndpointHasCorrectContentType() {
        client.get().uri("/api/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM);
    }

    @Test
    void missingRouteIsNotFound() {
        client.get().uri("/api/does-not-exist")
            .exchange()
            .expectStatus().isNotFound();
    }
}
```

Bài kiểm thử không assert “server có đúng N event-loop threads” vì đó là implementation/configuration detail, không phải API contract. Test `reactiveDelayReturnsExpectedValue` xác nhận reactive timer completion; nó **không** chứng minh CPU/latency tốt hơn MVC.

### 12.1. Kiểm thử SSE body thay vì chỉ Content-Type

Một test stream sâu hơn có thể dùng:

```java
FluxExchangeResult<ServerSentEvent<String>> result =
    client.get().uri("/api/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(new ParameterizedTypeReference<
                ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
    .expectNextMatches(e -> "tick-0".equals(e.data()))
    .expectNextMatches(e -> "tick-1".equals(e.data()))
    .expectNextMatches(e -> "tick-2".equals(e.data()))
    .verifyComplete();
```

Đây là snippet bổ sung đặt trong test method, cần imports `FluxExchangeResult`, `ServerSentEvent`, `ParameterizedTypeReference`, `StepVerifier`. Không dùng câu lệnh này ở ngoài một context đã có `client`. Ưu điểm: kiểm tra **ba signals SSE thực**, không chỉ header.

### 12.2. Testing không thay thế load testing

Để đo reactive concurrency, cần test representative traffic: 100–1000 concurrent clients, wait latency thực, connection reuse và response sizes. Dùng JFR, Micrometer/Actuator, Reactor Netty metrics, OS socket stats, thread dumps và network tooling. Đừng kết luận WebFlux nhanh hơn MVC chỉ dựa vào 10 HTTP assertions đúng.

## 13. Quản lý response lifecycle và client disconnect

### 13.1. Khi response chưa bắt đầu

Nếu handler trả `Mono.error(new ResponseStatusException(HttpStatus.BAD_REQUEST))` trước commit, WebFlux có thể set status và error response tương ứng. Security filters/CORS/codecs vẫn có thể tham gia theo configuration.

### 13.2. Khi SSE đã gửi bytes

```text
GET /api/stream
HTTP/1.1 200 OK
Content-Type: text/event-stream

data:tick-0

data:tick-1

... sau đó upstream lỗi ...
```

Khi response đã committed và gửi event cho client, server không thể quay lại đổi 200 thành HTTP 500 theo cách của một normal JSON response. Có thể encode sự kiện error theo protocol SSE hoặc đóng stream và để client retry theo policy.

### 13.3. Khi client hủy

Reactive subscription có thể nhận cancellation khi browser đóng kết nối hoặc user hủy request. Các cleanup hooks:

```java
Flux<String> values =
    service.events()
        .doFinally(signal -> {
            // signal có thể COMPLETE, ERROR hoặc CANCEL.
            // Thu thập metric/dọn tài nguyên nhẹ;
            // không chạy blocking operation trong event loop.
        });
```

Đây là snippet minh họa với `service.events()` giả định. Client disconnect có thể không được phát hiện ngay khi qua proxy/LB; cần heartbeat/idle timeout khi ứng dụng cần phát hiện kết nối chết sớm.

### 13.4. Retry và idempotency

Không retry POST không idempotent theo cách mù quáng khi có lỗi network. Remote có thể đã nhận request và thực hiện side effect trước khi kết nối mất. Dùng idempotency keys, transaction/broker semantics, retry/backoff có giới hạn và duplicate suppression.

## 14. ServerResource và lifecycle

Trong Reactor Netty, event loops, pooled buffers và connections đều là tài nguyên có lifecycle.

Với Boot:

- Sử dụng embedded Netty server qua auto-configuration thay vì tự tạo `HttpServer.bindNow()` ở nhiều nơi.
- Reuse `WebClient.Builder` do Boot cung cấp; đừng tạo client/pool mới cho **mỗi HTTP request**.
- Khi tự tạo `ConnectionProvider`, dispose đúng lúc ứng dụng đóng.
- Đối với Netty LoopResources custom, cần quản lý disposal và tránh tạo event loops trùng nhau.
- Khi thay client connector hoặc server factory, xác định cái nào sở hữu event-loop resources.
- Graceful shutdown có thể dùng Boot:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Thời gian shutdown thực tế với long-lived SSE/WebSocket/request phụ thuộc server/runtime và ứng dụng. Không giả định mọi connection luôn được drain trước timeout chỉ nhờ bật graceful shutdown.

### 14.1. Kết nối keep-alive và idle timeout

Một connection đã xử lý xong HTTP request có thể được giữ lại để tái sử dụng. Nếu idle quá lâu, server/client/proxy có thể đóng. Với SSE, connection còn hoạt động logic nhưng có thể không có bytes trong thời gian dài; proxy có thể áp read timeout riêng. Cần heartbeat phù hợp và tránh giữ bất kỳ connection vô hạn nếu client không thực sự tồn tại.

### 14.2. HTTP server metrics nên có

- Active/open connections, new connections và close/error counts.
- Requests in-flight, completed statuses, latency percentiles.
- Event-loop pending tasks / blocking detection / latency.
- Outbound connection pool active/idle/pending/acquire failures.
- TLS handshake/connect timeouts.
- Response stream cancellation/error counts.
- Heap/direct memory, GC pause và DataBuffer utilization.
- Remote dependency latency và circuit-breaker state.
- TCP retransmits, proxy 502/503/504 và OS file-descriptor usage.

Các tên metric cụ thể tùy Reactor Netty/Micrometer/Actuator versions; không tự bịa tên series mà không kiểm tra runtime thực tế.

## 15. Security, CORS và client identity

Reactive server không tự thay thế lớp bảo mật.

- Spring Security reactive sử dụng `SecurityWebFilterChain`, không dùng Servlet `SecurityFilterChain` như MVC.
- CORS quyết định origin nào được browser chia sẻ response; không phải authentication/authorization.
- Nếu login session/cookie tự đính kèm, cần CSRF protection cho state-changing methods phù hợp; “WebFlux” không làm CSRF biến mất.
- Nếu gateway reverse proxy gửi `X-Forwarded-For` hoặc `Forwarded`, chỉ trust những forwarded headers từ proxy đáng tin; request client có thể giả header nếu ingress chưa strip/validate.
- Rate limit theo trusted principal/tenant và resource usage, không chỉ source IP.
- Request body limits, WebSocket/SSE limits, idle timeout và HTTP/2 stream limits có thể là lớp bảo vệ against resource exhaustion.
- Không log raw bearer tokens, passwords, session cookies, personal data trong headers hoặc payload.
- TLS termination ở proxy thay đổi nơi có encryption/cert/ALPN; đo transport theo layer chính xác.

### 15.1. Reactor Context và ThreadLocal

Một request reactive có thể chuyển thread qua operators. Không dựa vào ThreadLocal/MDC truyền xuyên chain theo cách imperative nếu không có tích hợp context propagation phù hợp. Reactor `Context` gắn với subscriber; Spring Security reactive có cơ chế context tương ứng.

Ví dụ:

```java
Mono<String> trace =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "absent")))
        .contextWrite(Context.of("traceId", "req-001"));
```

Đây là snippet minh họa, cần `reactor.util.context.Context`. Đừng đưa principal giả từ request header vào Context rồi coi đó là đã xác thực.

## 16. Gỡ lỗi theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Bước kiểm tra |
| --- | --- | --- |
| WebFlux thấy rất nhiều requests pending | Downstream chậm, pool đầy, retry storms | HTTP client pool, downstream p95, pending queues |
| CPU thấp nhưng p99 latency cao | Blocking waits hoặc network timeouts | Thread dump, event-loop lag, client connect/response timeout |
| Một blocking handler làm nhiều APIs chậm | Chặn event-loop | Tìm `block()`, `Thread.sleep`, JDBC, sync HTTP |
| `DataBufferLimitException` | Codec aggregate vượt max-in-memory | Body format, codec limit, streaming strategy |
| Netty direct memory tăng | Buffers chưa giải phóng/traffic lớn | Memory metrics, buffer ownership, leak detection |
| Connection refused | Server không bind đúng host/port hoặc backend chết | Startup logs, listener, LB target |
| Nhiều `PrematureCloseException` | Client/remote/proxy đóng sớm, overload/timeouts | Connect, maxIdleTime, LB idle, retries |
| WebClient pending acquire timeout | Outbound pool bão hòa | Active/idle/pending counts, remote response time |
| SSE tự ngắt sau một phút | Proxy idle/read timeout hoặc không heartbeat | Reverse proxy/LB, heartbeat, cancellation |
| HTTP/2 chỉ dùng HTTP/1.1 | ALPN/TLS/proxy/runtime chưa negotiate | curl `--http2`, server config, TLS chain |
| Security filter Servlet không chạy trên Netty | Đang dùng WebFlux reactive stack | Sử dụng SecurityWebFilterChain |
| WebFlux controller chạy nhưng có DispatcherServlet | Boot đã chọn Servlet/MVC vì dependency mix | Kiểm tra starters/web-application-type |
| Trả Flux nhưng client không thấy item ngay | JSON array buffering/content negotiation | SSE/NDJSON media type và codec |
| Test kỳ vọng một thread cố định | Scheduler/Netty implementation thay đổi | Assert API contract, đo threads riêng |
| Requests bị 504 ở gateway nhưng app vẫn làm việc | Gateway timeout trước business completion | End-to-end deadlines, cancellation, idempotency |
| OOM dù chỉ vài event-loop threads | Nhiều concurrent buffers/pending queues | Heap/direct memory, body size, backpressure |
| Mono.just(...) gây delay ngay trong controller | Argument của just được tính eager | Mono.defer/fromCallable + scheduler phù hợp |
| Reactor .block() ném IllegalStateException | Chạy trên non-blocking thread | Dùng composition/flatMap/WebClient |

### 16.1. Quy trình điều tra 5 bước

1. Xác nhận app đang **reactive hay Servlet** (dependencies, logs, WebApplicationType, handler/filter types).
2. Xác nhận request có qua **proxy/CDN** trước Netty/Tomcat không; kiểm tra protocol, TLS, idle timeout.
3. Tách inbound server connections khỏi outbound WebClient connection pool.
4. Tìm blocking calls và kiểm tra event-loop lag, queues, downstream latency.
5. Đo response size, codec buffering, cancellations và per-route p95/p99 trước khi thay cấu hình hoặc framework.

## 17. Lỗi phổ biến: phân biệt các lớp để tránh tối ưu nhầm

| Hiểu lầm | Sai ở đâu | Cách hiểu đúng |
| --- | --- | --- |
| “Một TCP connection = một thread Servlet” | Keep-alive và connectors không ghim thread mãi | Worker thường gắn với request processing |
| “WebFlux chỉ có một thread cho tất cả client” | Có nhiều event loops/schedulers | Một event loop phục vụ nhiều channels, count do runtime |
| “Netty là Spring WebFlux” | Netty chỉ là một transport/server runtime | WebFlux có framework pipeline và server adapters |
| “WebFlux bắt buộc Netty” | Có Tomcat/Jetty/Servlet adapters | Boot Netty chỉ là default |
| “Tomcat là blocking TCP nên không thể WebFlux” | Tomcat có async/non-blocking I/O | WebFlux có bridge non-blocking |
| “MVC async chính là WebFlux” | HTTP contract/execution khác | Servlet async vẫn qua DispatcherServlet |
| “Mono tự có thread riêng” | Mono mô tả publisher | Scheduler/source quyết định execution |
| “Mono.fromCallable đã giải quyết blocking” | Lazy chứ không tự offload | BoundedElastic hoặc non-blocking driver |
| “Thread.sleep trong Netty vô hại” | Starves other channels on same loop | Không block loop |
| “Cứ trả Flux là response stream ngay” | JSON codec có thể aggregate | Chọn SSE/NDJSON đúng media type |
| “Flux buffer vô hạn vẫn có backpressure” | Buffer có thể ăn hết heap | Bounded queues / rate limits |
| “HTTP/2 nghĩa chỉ có một request trên connection” | HTTP/2 multiplexes streams | Connection và request tách biệt |
| “Inbound Netty pool là WebClient pool” | Hai vai trò HTTP server/client khác nhau | Quản lý riêng |
| “ConnectionProvider default luôn bằng 500” | Defaults phụ thuộc Reactor Netty version | Kiểm tra effective config/metrics |
| “HTTP timeout tự hủy mọi remote side effect” | Remote server có thể đã thực hiện | Idempotency và deadlines |
| “Cancellation luôn có onComplete” | Cancel khác completion | doFinally/usingWhen |
| “Bật HTTP/2 chỉ cần một property” | Còn TLS/ALPN/server/proxy/client | Verify negotiated protocol |
| “Có ít threads thì ít memory” | Buffers/channels vẫn dùng memory | Heap, direct memory, fd budgets |
| “WebFlux bảo mật tự động” | Vẫn cần auth/authz/CSRF/CORS | SecurityWebFilterChain |
| “CORS headers là thông tin xác thực” | CORS là browser policy | Authentication từ credentials |
| “SSE đã gửi event vẫn có thể đổi status 500” | Response đã committed | Protocol error event/close stream |
| “Phải tạo WebClient mới mỗi request” | Mất connection reuse, tăng resource | Reuse managed client |
| “Thêm MVC starter để dùng annotation” | Boot có thể chọn Servlet stack | Chỉ WebFlux starter cho reactive app |
| “Một benchmark nhỏ chứng minh reactive tốt hơn mọi tình huống” | Không xét workload/config | Load test và đo bottlenecks |
| “Mọi library trong WebFlux đều non-blocking” | JDBC/JPA/file APIs có thể block | Xem từng downstream dependency |

## 18. Checklist áp dụng vào hệ thống thực

Trước khi đưa WebFlux/Netty vào production, xác nhận:

1. **Application type**: đúng Spring Boot reactive web app, không vô ý trộn MVC.
2. **Runtime**: Reactor Netty/Tomcat/Jetty được chọn minh bạch theo dependencies và requirements.
3. **Inbound limits**: max connections/idle timeouts/request body limits, HTTP2 streams và proxy budgets.
4. **Outbound pools**: max active/idle/pending, acquire/connect/response timeout, ownership và disposal.
5. **Downstream APIs**: WebClient, R2DBC, reactive messaging hoặc bridge blocking có giới hạn.
6. **Event loops**: tránh `block()`, `Thread.sleep`, sync DB/HTTP trực tiếp trong handler.
7. **Bounded resources**: queues, buffers, SSE clients, infinite Flux, concurrency/bulkheads.
8. **Backpressure**: kiểm tra publisher producer thật sự tôn trọng demand/cancellation.
9. **HTTP semantics**: 204, 404, error trước và sau response commit, JSON vs SSE.
10. **Auth/security**: SecurityWebFilterChain, permissions/ownership, CORS, CSRF, TLS.
11. **Reactive Context**: trace/principal propagation đúng qua thread changes.
12. **Observability**: inbound requests/connections, outbound pools, event-loop lag, direct memory, GC.
13. **Graceful shutdown**: app/sidecar/LB drain + long-lived streams và Kubernetes termination grace.
14. **Testing**: WebTestClient unit/integration, real HTTP/2/proxy, load tests và client disconnect.
15. **Decision rationale**: có lý do dựa vào concurrent I/O/streaming hay chỉ đổi style cho đẹp?

## 19. Câu hỏi tự kiểm tra

**1.** “Một connection luôn dùng một worker thread” có chính xác không?  
**Đáp án:** Không; transport/socket readiness và request workers không tương ứng 1:1. Servlet worker thường gắn với xử lý request, không cố định suốt TCP keep-alive.

**2.** HTTP/2 có thể mang bao nhiêu requests trên một connection?  
**Đáp án:** Nhiều logical streams theo protocol/settings; không chỉ một request.

**3.** Netty Channel là gì?  
**Đáp án:** Abstraction cho một I/O channel/endpoint với pipeline handlers, được quản lý bởi EventLoop.

**4.** Một EventLoop có thể phục vụ nhiều channels không?  
**Đáp án:** Có, đó là mô hình chủ đạo.

**5.** Spring Boot WebFlux mặc định dùng server gì?  
**Đáp án:** Reactor Netty nếu giữ default dependencies của spring-boot-starter-webflux.

**6.** WebFlux có thể chạy trên Tomcat không?  
**Đáp án:** Có, qua reactive/non-blocking HTTP adapter phù hợp trên Servlet container.

**7.** Vì sao MVC synchronous có thể dùng nhiều request workers?  
**Đáp án:** Blocking service calls có thể giữ worker trong lúc chờ.

**8.** MVC Callable có giúp Servlet thread rảnh không?  
**Đáp án:** Có, nhưng blocking logic vẫn giữ AsyncTaskExecutor worker.

**9.** Mono<String> được return có làm JDBC call non-blocking không?  
**Đáp án:** Không. Downstream API vẫn có thể block.

**10.** Vì sao Mono.just(blockingCall()) nguy hiểm?  
**Đáp án:** blockingCall được gọi ngay khi assembly, có thể chạy trên event loop.

**11.** BoundedElastic có biến JDBC thành non-blocking không?  
**Đáp án:** Không; chỉ offload blocking wait sang worker phù hợp hơn.

**12.** HttpHandler trong Spring WebFlux trả type nào?  
**Đáp án:** Mono<Void> biểu diễn completion của HTTP exchange.

**13.** ServerWebExchange thuộc mô hình nào?  
**Đáp án:** Spring WebFlux WebHandler abstraction.

**14.** DispatcherHandler và DispatcherServlet giống nhau hoàn toàn không?  
**Đáp án:** Không; WebFlux dùng DispatcherHandler/reactive contracts, MVC dùng DispatcherServlet/Servlet API.

**15.** Flux<T> luôn flush từng item qua HTTP không?  
**Đáp án:** Không; phụ thuộc HTTP codec/media type. SSE/NDJSON có streaming semantics phù hợp.

**16.** Backpressure Reactive Streams giống TCP flow control một-một không?  
**Đáp án:** Không; tương tác nhưng hoạt động ở các layers khác nhau.

**17.** Inbound server connection pool và WebClient pool là một không?  
**Đáp án:** Không; server accept inbound, HttpClient quản lý outbound connections.

**18.** pendingAcquireTimeout trong WebClient nói về gì?  
**Đáp án:** Thời gian chờ lấy connection từ outbound pool.

**19.** HTTP client timeout có chắc remote transaction rollback không?  
**Đáp án:** Không; remote có thể đã thực hiện side effect.

**20.** Vì sao WebFlux với Tomcat vẫn reactive?  
**Đáp án:** WebFlux programming contract được adapt lên Servlet non-blocking I/O; runtime không tự đổi app thành MVC.

**21.** Bật WebFlux và MVC starters cùng lúc luôn chọn reactive không?  
**Đáp án:** Không; Spring Boot thường ưu tiên MVC nếu cả hai có mặt.

**22.** Khi nhiều SSE clients, chỉ cần vài threads là mọi tài nguyên miễn phí không?  
**Đáp án:** Không; connections, buffers, keep-alive state, fd và subscriber memory vẫn có giá.

**23.** Response đã phát SSE event rồi lỗi, có thể chuyển HTTP 200 thành 500 không?  
**Đáp án:** Thường không sau commit; phải có error event/close protocol.

**24.** Vì sao phải reuse WebClient?  
**Đáp án:** Tận dụng pools/resources, giảm kết nối/TLS setup và resource pressure.

**25.** Khi nào dùng WebFlux hợp lý?  
**Đáp án:** Khi stack có nhu cầu concurrent I/O/streaming và downstream dependencies reactive, được đo bằng workload thực chứ không chỉ trông vào tên framework.

## 20. Tài liệu chính thức

- [Spring Framework 6.2 — Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): HttpHandler, WebHandler, server adapters, non-blocking I/O.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html): khái niệm reactive, contrast với MVC, servers.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): mappings/adapters/result handlers.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Reactor Netty default và lựa chọn Tomcat/Jetty/Undertow, HTTP/2.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): Boot WebFlux auto-configuration.
- [Reactor Netty Reference — HTTP Server](https://projectreactor.io/docs/netty/1.1.26/reference/http-server.html): server, protocol configuration, observability.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/1.1.26/reference/http-client.html): connection pooling, timeout, reuse.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, threading, backpressure và schedulers.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): reactive HTTP tests.
- [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription và demand.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexing streams trên một connection.

**Quy tắc cuối cùng:** **Reactive server không đồng nghĩa “một connection một thread”, cũng không đồng nghĩa “không còn threads”.** Reactor Netty cho event loops phục vụ nhiều connections; WebFlux dùng contract Publisher/non-blocking I/O để không giữ worker chỉ vì đang chờ. Servlet containers cũng có NIO và Servlet async, nhưng Spring MVC có programming model khác. Để WebFlux thực sự hiệu quả, bạn phải làm rõ **inbound/outbound connections, blocking boundaries, event-loop scheduling, backpressure, timeout và resource lifecycle**, rồi đo workload thật.
