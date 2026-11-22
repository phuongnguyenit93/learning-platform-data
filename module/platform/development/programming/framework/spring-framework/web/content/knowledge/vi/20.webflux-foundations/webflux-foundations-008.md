# Đánh giá WebFlux theo toàn bộ chuỗi I/O; không mặc định nhanh hơn MVC

## 1. Mục tiêu bài học

**Spring WebFlux** là web stack reactive của Spring Framework, hỗ trợ mô hình **non-blocking I/O**, `Mono`/`Flux`, Reactive Streams và backpressure. Tuy nhiên, đổi từ Spring MVC sang WebFlux **không mặc định khiến API phản hồi nhanh hơn**. Lợi ích tiềm năng lớn nhất thường là sử dụng ít threads và memory hơn khi phục vụ **nhiều request đồng thời có thời gian chờ I/O**, với điều kiện các đoạn I/O quan trọng trong hệ thống cũng **không chặn event loop**.

Điểm cốt lõi: phải đánh giá **toàn bộ chuỗi xử lý từ HTTP vào đến HTTP ra**, không chỉ nhìn controller trả `Mono<T>`.

Sau bài này, bạn có thể:

1. Phân biệt **latency**, **throughput**, **concurrency**, **resource efficiency**, **p95/p99**, saturation, backpressure và tốc độ tính toán CPU.
2. Hiểu mô hình Servlet MVC (thường thread-per-active-request với blocking I/O) và WebFlux (event-loop + reactive signals), không đơn giản hóa rằng MVC “không hỗ trợ async”.
3. Vẽ và kiểm toán một request end-to-end: **client → gateway → WebFlux handler → HTTP client → database → cache → messaging → serializer → HTTP response**.
4. Nhận diện JDBC/JPA, `RestTemplate`, `Thread.sleep`, `Files.readAllBytes`, `block()`, đồng bộ hóa và client libraries blocking làm suy yếu WebFlux.
5. Giải thích cách dùng **`WebClient`**, **R2DBC**, `Schedulers.boundedElastic()`, Reactor Context, `timeout`, `flatMap(..., concurrency)`, pool/queue bounds và cancellation đúng chỗ.
6. Chạy một ví dụ **Java 17+, Spring Boot 3.x, Spring WebFlux + R2DBC/H2** không dùng JDBC, có HTTP endpoint trả `Mono` từ reactive database và kiểm thử bằng `WebTestClient`.
7. Lập thử nghiệm MVC-vs-WebFlux công bằng, đo concurrency/latency/CPU/memory/threads/GC/errors theo workload, đọc kết quả không thiên lệch.
8. Quyết định **giữ MVC**, **đưa WebClient vào MVC**, hay **chuyển sang WebFlux** dựa trên bằng chứng và khả năng vận hành.

**Phạm vi:** Spring Framework **6.x**, Spring Boot **3.x**, Project Reactor trên Java 17+. Nếu dùng Spring Framework 7/Spring Boot 4 hoặc thư viện driver đời khác, đối chiếu API/version tương ứng. Bài tập trung web server/reactive data I/O; không coi nó là một benchmark đã được chạy trên máy của bạn.

## 2. Kết luận kỹ thuật cần ghi nhớ trước

> **Reactive/non-blocking không tự làm code chạy nhanh hơn.** Nó giúp ứng dụng có khả năng quản lý nhiều thao tác chờ I/O hơn với ít threads hơn, trong đúng loại workload và kiến trúc.

Tài liệu Spring Framework nêu rõ: WebFlux thường **không** làm tăng tốc một request riêng lẻ; đôi khi còn thêm chi phí lập trình reactive và scheduling. WebFlux có thể có lợi khi số request đồng thời cao, remote/database I/O có độ trễ biến động, và toàn bộ các tầng quan trọng đều dùng API phù hợp.

Một REST endpoint trả dữ liệu cố định trong memory và hoàn thành trong 1 ms có thể không cải thiện đáng kể khi đổi sang WebFlux; đổi lại bạn thêm learning curve và khả năng debug phức tạp hơn. Ngược lại, endpoint phải chờ nhiều upstream services 100–500 ms và có hàng nghìn kết nối đồng thời có thể là ứng viên tốt để đo lợi ích non-blocking.

**Không có thứ hạng tuyệt đối:** không kết luận “MVC luôn nhanh hơn” hay “WebFlux luôn nhanh hơn” từ một biểu đồ benchmark đơn lẻ. Hardware, Java version, GC, server connector, database, SSL/TLS, compression, payload size, concurrency, error budget và test tooling có thể đảo ngược kết quả.

## 3. Hiểu đúng các đại lượng hiệu năng

| Khái niệm | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| Latency | Thời gian từ khi client gửi tới khi có phản hồi hoàn chỉnh hoặc dấu mốc được định nghĩa | Không đồng nghĩa số request mỗi giây |
| p50 | Trung vị latency | Có thể che giấu slow tail |
| p95 / p99 | 95% / 99% mẫu nằm trong hoặc dưới mức tương ứng | Cần đo đủ mẫu và báo cả timeout |
| Throughput | Requests/transactions hoàn thành mỗi giây (RPS/TPS) | Không đánh đồng “request đã gửi” với thành công |
| Concurrency | Số operations/requests đang in-flight | Không đồng nghĩa số threads |
| CPU utilization | Mức sử dụng CPU | Cao có thể là bão hòa, không phải hiệu quả |
| Memory / RSS | Heap, native memory, direct buffers, process resident set | WebFlux vẫn có buffer/netty/native overhead |
| Thread count | Số JVM/worker/event-loop threads | Ít threads không bảo đảm ít latency |
| Saturation | CPU, DB pool, network, queue, downstream đã đạt giới hạn | Không giải quyết bằng tăng concurrency vô hạn |
| Error / timeout rate | Tỷ lệ request thất bại hoặc vượt deadline | Bỏ lỗi khỏi kết quả làm benchmark lệch |
| Backpressure | Cơ chế điều tiết tốc độ dữ liệu theo nhu cầu tiêu thụ | Không tự giới hạn mọi nguồn bên ngoài |

Khi nói “nhanh hơn”, cần xác định **mục tiêu tối ưu**:
- Giảm p99 từ lúc request tới **byte cuối**, dưới tải 200 concurrent clients?
- Tăng **successful RPS** với cùng vCPU/RAM, và p99 không vượt SLA?
- Giảm threads/RSS khi duy trì 5.000 concurrent sockets?
- Giảm CPU cost/request ở cùng tải?
- Giảm chi phí vận hành trên một lượng traffic thực?

Một hệ thống có p50 đẹp nhưng p99 cao, nhiều timeout hoặc memory phình to **không** thể xem đã thắng.

### 3.1. Little's Law là trực giác, không phải phép màu

Ở trạng thái tương đối ổn định, số request đang ở hệ thống xấp xỉ throughput × thời gian ở hệ thống:

~~~text
L ≈ λ × W

L: số requests in-flight (bình quân)
λ: request completion rate (requests/second)
W: response time (seconds)
~~~

Nếu backend có latency I/O dài, số yêu cầu đồng thời tăng dù mỗi request tiêu thụ ít CPU. WebFlux có thể tránh giữ một thread blocking trên toàn bộ thời gian chờ đó — **nếu** I/O thực sự là non-blocking. Nhưng database connections, socket pools, memory và remote service rate limit vẫn là các nguồn lực hữu hạn.

## 4. Mô hình thực thi Spring MVC và WebFlux

### 4.1. Spring MVC / Servlet

Luồng MVC điển hình:

~~~text
Client -> Tomcat/Jetty Servlet connector
       -> Servlet filter / DispatcherServlet
       -> Controller -> Service
       -> JDBC/JPA/HTTP blocking call
       -> Result -> HTTP response
~~~

Với handler đồng bộ, request thread thường **chờ** khi gọi JDBC/HTTP blocking. Servlet container do đó cấu hình pool threads đủ lớn để phục vụ lượng request active.

Tuy nhiên, **MVC không đồng nghĩa mọi I/O đều blocking trong mọi tình huống**:
- Servlet API hiện đại hỗ trợ async request processing.
- MVC có `Callable`, `DeferredResult`, `StreamingResponseBody` và hỗ trợ reactive return types ở mức tích hợp.
- Một service MVC có thể dùng `WebClient` để gọi upstream non-blocking rồi trả reactive type.
- MVC có thể vận hành hiệu quả và đơn giản hơn nếu hệ thống phụ thuộc JDBC/JPA hoặc xử lý nghiệp vụ imperative.

Không nên lấy một MVC controller viết `Thread.sleep(500)`, so với WebFlux `Mono.delay(Duration.ofMillis(500))`, rồi kết luận WebFlux nhanh hơn dưới tải: hai đoạn có **ngữ nghĩa I/O khác nhau**, một bên block thread thật, bên kia tạo timer không block, không mô phỏng cùng downstream resource.

### 4.2. Spring WebFlux / Reactor Netty

Luồng WebFlux điển hình khi dùng Netty:

~~~text
Client -> Reactor Netty event loop (HTTP non-blocking)
       -> DispatcherHandler / WebFlux controller
       -> Publisher (Mono/Flux)
       -> WebClient / R2DBC reactive driver
       -> signals onNext / onError / onComplete
       -> reactive HTTP response
~~~

Event loop threads xử lý nhiều kết nối và callback mà **không nên bị chặn** bởi công việc dài. Một small fixed number of event loop workers có thể xử lý nhiều connection I/O-bound vì mỗi operation nhường thread lúc chờ I/O.

WebFlux cũng có thể chạy trên Servlet containers hỗ trợ non-blocking I/O. “WebFlux” là **framework programming model**, không đồng nghĩa tuyệt đối “Netty” ở mọi deployment.

**Cảnh báo cốt lõi:** nếu bạn gọi một blocking database client trên event loop, toàn bộ lợi thế ít threads dễ trở thành điểm yếu: một số ít event-loop workers bị giữ lại, ảnh hưởng **nhiều connections khác**.

## 5. Kiểm toán toàn bộ chuỗi I/O end-to-end

Đây là điểm trọng tâm của bài.

~~~text
Browser / Mobile / API client
         |
         v
CDN / WAF / load balancer / reverse proxy
         |
         v
TLS / Netty receive / WebFlux handler
         |
         +----> Auth / token check / remote identity provider
         |
         +----> Cache (in-process / Redis)
         |
         +----> Database (JDBC/JPA  vs  R2DBC)
         |
         +----> HTTP upstream (RestTemplate/block  vs  WebClient)
         |
         +----> Filesystem / object storage
         |
         +----> Message broker / async callback
         |
         +----> Serialization / compression / crypto / CPU
         |
         v
Netty send / reverse proxy / client reads response
~~~

Với **mỗi bước**, ghi rõ nó là: non-blocking thực sự, blocking được cô lập trong bounded worker, CPU-bound, hoặc phụ thuộc service khác. Một reactive endpoint có thể **chứa nhiều điểm blocking ẩn**.

### 5.1. Ma trận kiểm toán thư viện

| Tầng | Ví dụ phù hợp reactive I/O | Cảnh báo blocking / giới hạn |
| --- | --- | --- |
| HTTP server | Spring WebFlux với Reactor Netty | Controller gọi blocking operation trên event loop |
| HTTP client | Spring `WebClient` với connector non-blocking | `RestTemplate`, `HttpURLConnection`, `WebClient(...).block()` |
| RDBMS | R2DBC driver phù hợp database | JDBC, JPA/Hibernate ORM truyền thống |
| Redis | Reactive Redis client/API khi dùng reactive driver | Sync Redis API/blocking wrapper |
| Filesystem | NIO async API nếu stack hỗ trợ thực sự | `Files.readAllBytes`, `Files.newInputStream` sync read |
| Object storage | Async SDK/client phù hợp, end-to-end stream | SDK sync client, `getObject` blocking |
| Messaging | Non-blocking/reactive receiver nếu khả dụng | Consumer callback block hoặc bridge không có limit |
| JSON serialization | Jackson codec trong WebFlux | Serialize JSON nặng vẫn tốn CPU, có thể block event loop |
| Security | Reactive security chain | Remote auth introspection blocking, BCrypt/crypto CPU nặng |
| Template/rendering | Pipeline phù hợp | Block template lookup/dynamic rendering; CPU cost |
| Tracing/logging | Reactor Context/Micrometer đúng cách | Blocking appender, network log sink sync |
| Legacy integration | Bounded scheduler wrapper nếu bắt buộc | Unbounded thread/queue hoặc không timeout |
| Reverse proxy | Async/non-blocking proxy theo cấu hình | Connection limits, buffering, idle timeout vẫn ảnh hưởng |

**Nếu database chính là JPA/JDBC**, WebFlux không tự biến việc truy cập DB thành non-blocking. Dùng `Mono.fromCallable(() -> jpaRepo.findById(...))` trên bounded worker có thể giúp tránh block event loop, nhưng vẫn **tiêu thụ thread blocking và DB connection**. Đây là một migration bridge, không phải lợi ích full reactive.

### 5.2. “Trả Mono” không chứng minh non-blocking

Anti-pattern:

~~~java
@GetMapping("/unsafe/{id}")
public Mono<BookDto> unsafe(@PathVariable long id) {
    BookEntity entity = jdbcRepository.findById(id);
    return Mono.just(mapToDto(entity));
}
~~~

Đây là **mẫu phản diện minh họa**, không biên dịch độc lập vì `jdbcRepository`, `BookEntity`, `BookDto`, `mapToDto` chưa được định nghĩa. Lệnh JDBC đã chạy đồng bộ **trước khi Mono được trả**, và rất có thể trên event-loop thread. Dù return type là `Mono<BookDto>`, đoạn code không phải pipeline non-blocking end-to-end.

Tương tự:

~~~java
@GetMapping("/also-unsafe")
public String alsoUnsafe() {
    return webClient.get().uri("/upstream")
            .retrieve()
            .bodyToMono(String.class)
            .block();
}
~~~

Đây là anti-pattern. `WebClient` không mất tính non-blocking, nhưng `block()` bắt caller chờ kết quả; trên event loop, Reactor có thể phát hiện và ném `IllegalStateException` vì `block()` không được phép trên non-blocking threads. Đừng dùng `block()` trong WebFlux request path để chuyển reactive sang imperative cho tiện.

## 6. Reactor Mono, Flux và Reactive Streams backpressure

- **`Mono<T>`** phát tối đa 0 hoặc 1 phần tử rồi complete/error.
- **`Flux<T>`** phát 0 đến nhiều phần tử; có thể hữu hạn hoặc vô hạn.
- **Publisher** được subscribe và có signals `onSubscribe`, `onNext`, `onError`, `onComplete`. Backpressure qua **demand (`request(n)`)**.
- **Lazy execution**: nhiều reactive operations chỉ được thực thi khi có subscription. Spring WebFlux sẽ subscribe vào Publisher được controller trả.
- **Không gọi `subscribe()` tùy tiện trong handler** chỉ để kích hoạt tác vụ rồi trả `Mono.empty()`; bạn có thể mất lifecycle, error propagation, cancellation, tracing và backpressure.

Ví dụ pipeline không blocking:

~~~java
@GetMapping("/hello")
public Mono<String> hello() {
    return Mono.just("hello")
            .map(String::toUpperCase);
}
~~~

Mã minh họa trong `@RestController`. Kết quả là `HELLO`, nhưng đây là tác vụ memory/CPU cực nhỏ; **không có I/O chờ**, nên chưa phải chứng minh WebFlux scale tốt hơn MVC.

### 6.1. Backpressure không phải quota toàn hệ thống

Backpressure biểu diễn nhu cầu tiêu thụ các phần tử của một reactive stream. Nó **không** tự giới hạn:
- HTTP requests mới đổ vào server;
- số TCP connections;
- tất cả queries đồng thời;
- Redis/object storage client không hỗ trợ backpressure;
- remote service nhận request trước khi client chậm;
- memory của `collectList()` trên một Flux cực lớn;
- số retry/timeouts làm tăng tải.

Nếu producer không thể giảm tốc, bạn vẫn cần chính sách **buffer/drop/error** và capacity limits. Các điểm **network boundary, JDBC adapter, distributed messaging** có thể không tôn trọng demand giống một Flux thuần.

### 6.2. Các operator dễ gây bùng nổ tài nguyên

~~~java
Flux.range(1, 100_000)
    .flatMap(id -> remoteCall(id));
~~~

Đây là snippet minh họa trong scope có `remoteCall`; không chạy độc lập. `flatMap` có concurrency và prefetch semantics theo overload/Reactor version, **không nên mặc định vô hạn hay mặc định an toàn**. Nếu downstream có khả năng quá tải, đặt limit rõ:

~~~java
Flux.range(1, 1_000)
    .flatMap(id -> remoteCall(id), 8);
~~~

Tối đa khoảng 8 inner publishers active cùng lúc tại operator này, nhưng remote APIs vẫn cần connection-pool bounds, timeouts và rate limits. Kết quả `flatMap` **có thể không giữ thứ tự**; nếu cần thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential` và đánh giá latency.

Một anti-pattern khác:

~~~java
Mono<List<Item>> all = hugeFlux.collectList();
~~~

Nếu `hugeFlux` rất lớn hoặc không kết thúc, `collectList()` có thể tiêu tốn heap hoặc không hoàn tất. Với download/streaming, chọn media type và response body semantics phù hợp thay vì materialize toàn bộ stream.

## 7. Blocking I/O trong reactive pipeline: xử lý đúng ranh giới

Khi chưa thể thay một thư viện synchronous/blocking (JDBC, SDK cũ, filesystem API), tài liệu Reactor khuyến nghị dạng:

~~~java
public Mono<LegacyResult> legacy(long id) {
    return Mono.fromCallable(() -> blockingLegacyClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là method minh họa, cần `LegacyResult` và `blockingLegacyClient` thực tế. Điều quan trọng:

1. `Mono.fromCallable` **trì hoãn** việc gọi blocking API tới lúc subscribe.
2. `subscribeOn(Schedulers.boundedElastic())` dời source execution sang worker scheduler dành cho blocking operations.
3. Event loop không bị chặn vì tác vụ được offload.
4. **Tác vụ vẫn blocking** trên một thread khác; DB connections, heap, queue và scheduler capacity không biến mất.
5. `boundedElastic` có bounds (thread/queued tasks) nhưng default của nó có thể không phù hợp workload/ngưỡng SLO của bạn. Giới hạn concurrency/downstream và test overload vẫn cần thiết.
6. Nên đặt `subscribeOn` ngay sau blocking source theo pattern Reactor docs để người đọc không nhầm phạm vi scheduler.

### 7.1. `publishOn` khác `subscribeOn`

- `subscribeOn(scheduler)` tác động đến quá trình subscribe/source execution upstream theo Reactor semantics, phù hợp để wrap **nguồn** blocking.
- `publishOn(scheduler)` đổi thread dùng để xử lý những downstream signals/operators từ vị trí đặt operator.

Ví dụ:

~~~java
Mono.fromCallable(() -> blockingRead())
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::transform);
~~~

Đây là snippet minh họa với `blockingRead` và `transform` chưa định nghĩa. Source được offload ngay từ đầu; `map` có thể chạy trên worker tương ứng. Nếu muốn chuyển CPU-heavy transform sang pool khác, cần xem CPU scheduling và tránh tốn chi phí thread-switch không cần thiết.

**Đừng đặt** `publishOn` **sau** một `map` đang gọi blocking API rồi nghĩ đã sửa:

~~~java
Mono.just(id)
    .map(x -> blockingLegacyClient.fetch(x))
    .publishOn(Schedulers.boundedElastic());
~~~

Đây là **phản ví dụ**: `map` blocking xảy ra **trước** `publishOn`, nên có thể block thread gốc. Tốt hơn dùng `fromCallable(...).subscribeOn(boundedElastic())` hoặc đặt `publishOn` trước đoạn blocking nếu hiểu rõ pipeline.

### 7.2. Không dùng `Thread.sleep` giả lập latency của I/O

~~~java
return Mono.just("done")
        .map(v -> {
            Thread.sleep(200);  // minh họa phản diện
            return v;
        });
~~~

Snippet này còn cần xử lý `InterruptedException` để compile. Nó minh họa một ý: **đặt sleep bên trong map** là blocking, không phải reactive wait. Để tạo một asynchronous timer **cho demo/test**, dùng:

~~~java
return Mono.delay(Duration.ofMillis(200))
        .map(tick -> "done");
~~~

Nhưng `Mono.delay` **không mô phỏng database lock contention, connection pool, network bandwidth hay payload serialization**. Không lấy benchmark timer giả để kết luận throughput production.

## 8. WebClient: HTTP I/O không chặn nhưng cũng có giới hạn

`WebClient` là non-blocking reactive HTTP client, có thể chạy trong WebFlux **hoặc Spring MVC**. Khi ứng dụng gọi remote service, sử dụng:

~~~java
@Service
public class InventoryGateway {
    private final WebClient client;

    public InventoryGateway(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory.example.com")
                .build();
    }

    public Mono<Stock> getStock(long id) {
        return client.get()
                .uri("/stock/{id}", id)
                .retrieve()
                .bodyToMono(Stock.class)
                .timeout(Duration.ofSeconds(2));
    }

    public record Stock(long productId, int available) {}
}
~~~

Đây là **class minh họa tích hợp một upstream giả định**; cần imports `@Service`, `WebClient`, `Mono`, `Duration`, và upstream thực trả JSON khớp `Stock`. `https://inventory.example.com` ở đây **chỉ là domain ví dụ**, không phải service thật để ứng dụng demo mục 11 gọi. `WebClient.Builder` được Boot auto-configure khi có WebFlux infrastructure phù hợp.

Các điểm cần nhớ:

- `bodyToMono` không tự gọi `block()`; bạn **return Mono** hoặc compose trong pipeline.
- `timeout(Duration)` đặt deadline cho Publisher; đồng thời cấu hình connect/response/read timeout ở HTTP client connector khi cần.
- Giới hạn connection pool, pending acquire, DNS, TLS handshake, remote rate limit, max in-memory buffer size và error status handling.
- `retrieve()` mặc định coi response 4xx/5xx thành error signal; thiết kế `onStatus`, retries và fallback có chủ đích.
- `retryWhen` có thể làm tăng tải lên service vốn đã quá tải; retry phải có backoff, jitter, limit và chỉ với nghiệp vụ/idempotency phù hợp.
- Nếu gọi nhiều upstream độc lập, `Mono.zip(a, b)` có thể cho phép overlap các I/O chờ (khi sources non-blocking), nhưng không khẳng định mọi case nhanh hơn hoặc total request time luôn bằng max(latencies).
- Với 10.000 requests đồng thời, WebClient vẫn cần đủ connections/FDs và upstream capacity. Non-blocking không phải “vô hạn connections”.

### 8.1. Một chuỗi đủ reactive và một chuỗi giả reactive

~~~text
A: WebFlux -> Mono -> WebClient(non-blocking) -> R2DBC(non-blocking)
   -> response codecs -> Netty
   => Có cơ sở kỳ vọng tiết kiệm blocked threads nếu latency I/O cao.

B: WebFlux -> Mono.just(jpaRepository.findById(...))
   -> JDBC blocking trên event loop -> Netty
   => Return type reactive nhưng I/O cốt lõi vẫn blocking.

C: WebFlux -> Mono.fromCallable(JPA).subscribeOn(boundedElastic)
   -> JDBC blocking trên worker -> Netty
   => Event loop được bảo vệ; vẫn cần threads/queue/JDBC pool.
~~~

Lợi ích cần đo trên **toàn đường A**, không chỉ vì có chữ `Mono` trong signature.

## 9. Database: R2DBC so với JDBC/JPA

JDBC truyền thống sử dụng blocking APIs. JPA/Hibernate ORM thường dựa trên JDBC và transaction context thread-bound. R2DBC cung cấp API reactive cho relational database drivers, nhưng **driver và database thực** phải hỗ trợ và ổn định ở workload của bạn.

| Khía cạnh | MVC + JDBC/JPA | WebFlux + R2DBC |
| --- | --- | --- |
| Lối viết | Imperative, transaction/service quen thuộc | Publisher, composition, reactive transactions |
| I/O DB | Blocking caller thread | Reactive API/driver khi đúng implementation |
| ORM/ecosystem | JPA/Hibernate mature và nhiều integration | R2DBC hỗ trợ theo dialect/driver, không tương đương mọi JPA feature |
| Lazy loading | JPA proxy/lazy entity theo session | Không sử dụng lazy-loading ORM JPA theo cùng cách |
| Transactions | `PlatformTransactionManager`, thread-bound | `ReactiveTransactionManager`, Reactor context |
| Backpressure | Không phải Reactive Streams | Có reactive API, nhưng DB protocol/pool vẫn có giới hạn |
| Pool | JDBC pool (vd HikariCP) | R2DBC connection pool khi cần |
| Failure modes | Thread/connection exhaustion | Connection pool/queue/event-loop/retry pressure |
| Migration cost | Giữ code hiện tại | Thay đổi repositories, transactions, mappings, tests |

**R2DBC không tự động nhanh hơn JDBC**. Nó thay đổi execution model; lợi thế là tránh giữ thread trong lúc đợi DB I/O khi concurrency lớn. Một truy vấn SQL tối ưu hóa kém hoặc DB đã bão hòa sẽ vẫn chậm, bất kể reactive client. Các phép join, index, row scans, locks, network và connection count mới thường là yếu tố quyết định.

### Reactive transaction không đi theo ThreadLocal

Với R2DBC, `@Transactional` có thể dùng **ReactiveTransactionManager** với return type reactive. Transaction context được liên kết với subscriber/Reactor Context, không giống mô hình thread-bound JDBC. Tránh dùng một `@Transactional` imperative method gọi nội dung async rồi mong transaction bao bọc toàn bộ subscription.

Không tự gọi `subscribe()` bên trong service rồi rời khỏi transaction scope. Trả Publisher để Spring quản lý lifecycle/transaction. Kiểm tra reactive transaction manager được cấu hình khi dự án có đồng thời JDBC/JPA và R2DBC.

## 10. Một benchmark công bằng phải kiểm soát điều gì?

Nếu bạn benchmark MVC và WebFlux, **hai phiên bản phải giải cùng một bài toán** với cùng contract và điều kiện:

1. **Cùng endpoint semantics:** status codes, JSON schema, số records, validation, authentication, error handling, serialization.
2. **Cùng dữ liệu:** database size/indexes/query plans, cache hit/miss, network latency, SQL result set size.
3. **Cùng downstream:** cùng DB cluster, upstream HTTP service, rate limits, connection pools được tối ưu hợp lý theo từng stack.
4. **Cùng hạ tầng:** số vCPU, RAM, JVM version, GC, heap, containers, network, TLS, proxies và bandwidth.
5. **Warm-up tương đương:** JIT, driver pools, DB caches và connection establishment.
6. **Tool tạo tải độc lập:** máy load generator không bão hòa CPU/network, giữ đúng connection reuse/keep-alive và payload profile.
7. **Tỷ lệ lỗi:** không bỏ 429/503/timeout, client abort khỏi số liệu.
8. **Same arrival pattern:** thử cả closed-loop concurrency cố định và open-loop request arrival rate để giảm coordinated omission.
9. **Cùng time budget:** thử nhiều lần, độc lập, dùng confidence intervals/distributions.
10. **Quan sát mỗi tầng:** HTTP server, event loops/worker threads, DB pool, GC, remote services, OS sockets/FDs và gateway.

Không nên benchmark bằng một lệnh `curl` đơn lẻ rồi khẳng định stack nào “nhanh hơn”. Một response 5 ms trong dev environment không phản ánh p99 khi 500 client đồng thời.

### 10.1. Các kịch bản nên có

| Kịch bản | Mục tiêu kiểm chứng | WebFlux có lợi? |
| --- | --- | --- |
| K1: Echo JSON rất nhỏ | Baseline framework/codec CPU overhead | Không nên mặc định |
| K2: CPU-bound mapping/crypto | Sức tính toán CPU, context switching | Reactive không tạo thêm CPU |
| K3: JDBC/JPA blocking query | Hệ quả blocking DB/client library | Thường không thấy lợi thế full reactive |
| K4: R2DBC + high-latency DB | Concurrent I/O và thread/memory footprint | Có thể; phải đo |
| K5: Hai WebClient upstream độc lập | Composed concurrent waits | Có thể; MVC + WebClient cũng là ứng viên |
| K6: Streaming lớn | Buffering, backpressure, client chậm | Phụ thuộc end-to-end support |
| K7: 500 concurrent clients | Saturation, queue, pool, p99 | Có thể; cần DB/service đủ capacity |
| K8: Upstream lỗi/chậm | Timeouts, retries, circuit breakers | Reactive không tự tránh cascading failure |
| K9: 90% cache hits | CPU/cache path efficiency | Chưa chắc khác biệt đáng kể |
| K10: TLS+compression+auth thật | Overheads production thực tế | Không kết luận từ demo nhỏ |

### 10.2. Metric set bắt buộc

**Client/HTTP:** successful RPS, p50/p95/p99 latency, max latency, total errors, 4xx/5xx distribution, timeouts, pending/inflight, bytes transferred.

**JVM:** CPU utilization, heap used, GC pauses/allocation rate, native/direct memory, JVM thread count, event-loop busy time.

**Pools/queues:** Netty connection provider active/pending, R2DBC/JDBC pool active/idle/acquire wait, scheduler queue, executor threads và rejections.

**Downstream:** DB query latency/pool/locks, upstream HTTP latency/errors/rate limits, Redis/streaming throughput, filesystem/object storage time.

**Business:** đúng dữ liệu, số bản ghi, thứ tự results, duplicate retries, p99 trên các endpoint quan trọng. Khả năng trả lỗi nhanh khi quá tải đôi khi **tốt hơn** hàng đợi dài vô hạn, nhưng phải đo error budget.

Không chỉ báo một số RPS; các metrics phải được xem **cùng nhau**.

## 11. Ví dụ chạy được: WebFlux → R2DBC/H2 → HTTP response

Để minh họa **chuỗi HTTP → database** không cần JDBC, ứng dụng mẫu dùng:
- Spring Boot 3.x, Java 17+, **chỉ `spring-boot-starter-webflux`** cho HTTP server.
- **`spring-boot-starter-data-r2dbc`** và **`io.r2dbc:r2dbc-h2`** cho kết nối reactive H2.
- `DatabaseClient` đọc một row từ H2 trong một Publisher.
- Controller trả `Mono<ResponseEntity<CatalogItem>>` và `Flux<ServerSentEvent<String>>`.
- **`spring-boot-starter-test`** và `WebTestClient` thực hiện HTTP integration test.

Ví dụ này chứng minh **đường dẫn non-blocking và correctness**, **không** có ý nghĩa thay thế benchmark production. H2 memory thường quá nhanh, không đại diện DB thực có network và tranh chấp locks. Đừng dùng số liệu thử demo này để tuyên bố WebFlux có throughput tốt hơn MVC.

### 11.1. Maven dependencies

Tạo project Maven bằng Spring Initializr với Java 17+, Spring Boot 3.x. Chọn WebFlux, Spring Data R2DBC và Test; bổ sung driver R2DBC H2 nếu chưa được chọn. Các dependency trong `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **đoạn dependencies** đặt trong project `pom.xml` do Spring Initializr tạo; không phải toàn bộ file Maven độc lập. **Không** thêm `spring-boot-starter-web`/Spring MVC ở đây. Trong Spring Boot 3.x, nếu cả Web MVC và WebFlux starters cùng trên classpath, **Spring MVC thường được chọn mặc định**, trừ khi chọn rõ reactive application type; chỉ dùng WebFlux starter giúp ví dụ rõ ràng.

### 11.2. Cấu trúc project

~~~text
src/
  main/
    java/com/example/demo/
      DemoApplication.java
      CatalogItem.java
      CatalogService.java
      CatalogController.java
    resources/
      application.properties
      schema.sql
      data.sql
  test/
    java/com/example/demo/
      CatalogHttpTest.java
~~~

### 11.3. Cấu hình R2DBC database và SQL scripts

`src/main/resources/application.properties`:

~~~properties
spring.application.name=webflux-io-chain-demo
spring.r2dbc.url=r2dbc:h2:mem:///catalogdb
spring.sql.init.mode=always
~~~

H2 là in-memory database cho demo. `spring.sql.init.mode=always` cho phép Boot khởi tạo scripts `schema.sql` và `data.sql` trên ConnectionFactory reactive; đây **không** phải JDBC URL. Project sử dụng version Boot/R2DBC H2 do BOM của Boot quản lý, tránh ép version driver không tương thích.

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE catalog_item (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    stock INTEGER NOT NULL
);
~~~

`src/main/resources/data.sql`:

~~~sql
INSERT INTO catalog_item (id, name, stock)
VALUES (7, 'spring', 9);

INSERT INTO catalog_item (id, name, stock)
VALUES (8, 'reactor', 12);
~~~

Vì H2 memory ở đây được khởi tạo trong app, demo có dữ liệu tất định. Khi chạy đồng thời nhiều application contexts vào cùng H2 memory database, tránh reuse schema không mong muốn; các test cần kiểm soát tạo/xóa dữ liệu hoặc database isolation. Trong production, dùng migration tool/phương thức deployment nhất quán thay cho khởi tạo schema theo demo trên mọi lần startup.

### 11.4. Java application

`src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.5. Immutable DTO

`src/main/java/com/example/demo/CatalogItem.java`:

~~~java
package com.example.demo;

public record CatalogItem(
        Long id,
        String name,
        Integer stock
) {}
~~~

`CatalogItem` là immutable Java record, không chứa shared mutable state. Việc record immutable **không** tự chứng minh toàn pipeline thread-safe, nhưng giảm một lớp rủi ro chia sẻ object.

### 11.6. Service dùng `DatabaseClient` reactive

`src/main/java/com/example/demo/CatalogService.java`:

~~~java
package com.example.demo;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {

    private final DatabaseClient db;

    public CatalogService(DatabaseClient db) {
        this.db = db;
    }

    public Mono<CatalogItem> findById(long id) {
        return db.sql("""
                SELECT id, name, stock
                FROM catalog_item
                WHERE id = :id
                """)
                .bind("id", id)
                .map((row, metadata) ->
                        new CatalogItem(
                                row.get(0, Long.class),
                                row.get(1, String.class),
                                row.get(2, Integer.class)))
                .one();
    }
}
~~~

**Giải thích:**

1. `DatabaseClient` được Spring Boot auto-configure với R2DBC `ConnectionFactory`.
2. `:id` là **bind marker**, không phải nối SQL thô từ input. Nó tránh SQL injection khi dùng đúng cơ chế binding.
3. `.one()` trả `Mono<CatalogItem>`, complete empty nếu không có row.
4. `row.get(0, Long.class)`/theo index tương ứng cột SELECT. Với schema H2 này, kiểu `BIGINT` và `INTEGER` ánh xạ sang `Long`/`Integer`.
5. Không gọi `.block()`, `.subscribe()` hoặc JDBC client bên trong service.
6. Pipeline truy vấn thực tế chỉ chạy khi Publisher được subscribe bởi WebFlux; DB driver và pool vẫn phải được quan sát.
7. SQL table và scripts phải tồn tại khi app startup. Nếu đổi thứ tự cột SELECT, code mapping theo vị trí phải được cập nhật; trong service production có thể map theo tên/row-mapper rõ ràng.

### 11.7. Reactive HTTP controller

`src/main/java/com/example/demo/CatalogController.java`:

~~~java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<CatalogItem>> one(
            @PathVariable("id") long id) {

        return catalogService.findById(id)
                .map(item -> ResponseEntity.ok(item))
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(
            path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofMillis(200))
                .take(3)
                .map(number -> ServerSentEvent
                        .builder("tick-" + number)
                        .build());
    }
}
~~~

Với record H2 ban đầu:
- `GET /api/catalog/7` trả **200** JSON `{"id":7,"name":"spring","stock":9}`.
- `GET /api/catalog/999` trả **404**, vì `Mono.empty()` được ánh xạ qua `defaultIfEmpty`.
- `GET /api/catalog/ticks` là demo **SSE** phát `tick-0`, `tick-1`, `tick-2` rồi kết thúc; nó dùng timer không blocking, **không** thay thế việc đo streaming với client chậm.

Không dùng `Thread.sleep` để tạo interval. `Flux.interval` phát tín hiệu thông qua scheduler phù hợp; lượng subscribers/timers cũng tiêu tốn tài nguyên, nên SSE production cần heartbeat/connection limits/cleanup.

### 11.8. Kiểm thử HTTP thật với WebTestClient

`src/test/java/com/example/demo/CatalogHttpTest.java`:

~~~java
package com.example.demo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogHttpTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void readsOneRowThroughReactiveDatabase() {
        client.get()
                .uri("/api/catalog/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("spring")
                .jsonPath("$.stock").isEqualTo(9);
    }

    @Test
    void notFoundWhenDatabasePublisherIsEmpty() {
        client.get()
                .uri("/api/catalog/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

hoặc trên Windows:

~~~powershell
.\mvnw.cmd test
~~~

Nếu project không có Maven Wrapper, dùng `mvn test` khi máy đã cài Maven. Test khởi động **embedded HTTP server trên một random port**, thực hiện **HTTP network request** và truy xuất **R2DBC H2** rồi assert JSON/status. Đây là một integration test hữu ích hơn so với chỉ test một `Mono.just` giả lập.

Tuy nhiên test này **không đo hiệu năng**: nó không đo meaningful high concurrency, TLS, reverse proxy, packet loss, remote database latency hay real network contention. Đừng trình bày hai test pass như một chứng minh “WebFlux nhanh hơn”.

### 11.9. Thử bằng curl

Khởi chạy:

~~~bash
./mvnw spring-boot:run
~~~

Gọi API:

~~~bash
curl -i http://localhost:8080/api/catalog/7
~~~

Kết quả kỳ vọng: status **200 OK**, `Content-Type: application/json` và body:

~~~json
{"id":7,"name":"spring","stock":9}
~~~

Không tồn tại:

~~~bash
curl -i http://localhost:8080/api/catalog/999
~~~

Status kỳ vọng **404 Not Found**. Body của default WebFlux error response có thể phụ thuộc cấu hình/negotiation; trong controller này `ResponseEntity.notFound().build()` không cung cấp business payload.

SSE timer:

~~~bash
curl -N http://localhost:8080/api/catalog/ticks
~~~

Body có ba events với dữ liệu kiểu:

~~~text
data:tick-0

data:tick-1

data:tick-2
~~~

`-N` tránh buffering stdout của curl; thứ tự các event là 0, 1, 2 nhưng **thời gian phát thực tế** phụ thuộc scheduler, server, proxy và client, không bảo đảm đúng từng 200 ms trên mạng.

## 12. Mở rộng chuỗi I/O với WebClient bên ngoài

Ví dụ mục 11 chỉ đi qua một database reactive. Nếu nghiệp vụ thực gọi thêm inventory service, pipeline có thể là:

~~~java
public Mono<ItemDetail> detail(long id) {
    Mono<CatalogItem> item = catalogService.findById(id);
    Mono<InventoryGateway.Stock> stock = inventoryGateway.getStock(id);

    return Mono.zip(item, stock)
            .map(pair -> new ItemDetail(
                    pair.getT1(), pair.getT2()));
}
~~~

Đây là **method minh họa**, chưa runnable độc lập: cần khai báo `catalogService`, `inventoryGateway`, `ItemDetail`; gateway ở mục 8 dùng domain ví dụ. `Mono.zip` chỉ emit khi cả hai sources có giá trị; nếu một source complete empty, zip có thể complete empty, cần xử lý missing data theo business semantics. Nếu hai calls độc lập, khi subscribe chúng có thể overlap I/O. Không được **gọi `.block()`** để gom results:

~~~java
// Anti-pattern: đồng bộ hóa hai request bất đồng bộ
CatalogItem a = item.block();
InventoryGateway.Stock b = stock.block();
~~~

Dù upstream dùng WebClient, đoạn anti-pattern làm caller chờ và có thể phá event loop. Trả `Mono<ItemDetail>` để framework subscribe, propagate error/cancellation một cách có kiểm soát.

### Khi nào MVC + WebClient đủ tốt?

Nếu hệ thống đã dùng MVC/JPA ổn định và chỉ có một vài HTTP fan-outs, bạn có thể:
- Giữ Spring MVC và blocking DB calls ở thread Servlet/worker được cấu hình phù hợp.
- Dùng `WebClient` ở một số integration calls.
- Dùng reactive return type từ MVC handler khi API phù hợp hoặc tập trung tối ưu connection pools và timeouts.
- Đo lại SLO trước khi cân nhắc rewrite toàn bộ service sang WebFlux/R2DBC.

Đây là một chiến lược **tối ưu theo bottleneck**, không phải thỏa hiệp kém về mặt kiến trúc.

## 13. Lỗi khi chạy reactive nhưng blocking ẩn: cách phát hiện

Các điểm cần tìm trong code review:

~~~text
.block()
.blockOptional()
Thread.sleep(...)
Future.get()
CompletableFuture.join()
RestTemplate.exchange(...)
JdbcTemplate.query(...)
jpaRepository.find...
Files.readAllBytes(...)
InputStream.read(...) trên nguồn blocking
ObjectMapper.writeValueAsBytes(hugeObject)
synchronized / locks giữ lâu
collectList() trên Flux không có giới hạn
flatMap(...) không có concurrency budget rõ
subscribe() bên trong controller/service
Schedulers.boundedElastic() dùng như lời giải mọi vấn đề
~~~

Không phải mọi method trong danh sách luôn sai **ở mọi thread/hoàn cảnh**: ví dụ `Files.readAllBytes` trong startup config hoặc một tool command line có thể hoàn toàn hợp lý. Vấn đề là dùng nó **trên event-loop request path** hoặc trong một publisher mà chưa offload/bound resource.

### 13.1. BlockHound

**BlockHound** là công cụ hỗ trợ phát hiện một số blocking calls trên threads được đánh dấu non-blocking trong tests. Nó hữu ích để tìm `Thread.sleep` hoặc API blocking khi lỡ chạy trên Reactor scheduler/event loop.

Tuy nhiên:
- Không chứng minh mọi I/O trong toàn hệ thống đều non-blocking.
- Có thể có false positives/whitelisting; cần test profile riêng.
- Kiểm tra **tính tương thích với JVM và Reactor/BlockHound version**; Java 17+ có yêu cầu instrumentation/JVM arguments tùy version.
- Không bật tự động trong production nếu chưa đánh giá overhead.

### 13.2. Java Flight Recorder, traces và thread dumps

Quan sát:
- Reactor Netty event loop threads đang làm gì? Có stack traces JDBC, JSON cực lớn, file IO, locks, crypto kéo dài?
- Reactive scheduler/boundedElastic có đầy queue/threads không?
- Connection pool acquires có chờ lâu?
- DB query latency và counts/locks có tăng?
- `WebClient` có đủ channels, DNS/connect/response timeouts?
- Reactor Context/tracing có mất khi chuyển thread?
- p99 bị giữ bởi network/proxy/client speed hay chính application?

Tìm **điểm nghẽn cụ thể** trước khi chọn đổi framework.

## 14. Reactive Context, ThreadLocal và transactions

Reactor có **`Context`** gắn với subscription, hỗ trợ mang metadata qua async execution mà không mặc định dựa vào một `ThreadLocal` duy nhất:

~~~java
Mono<String> observed = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
        .contextWrite(context -> context.put("requestId", "req-42"));
~~~

Đoạn minh họa thuần Reactor này tạo Publisher chứa `req-42` khi được subscribe. **Không** dùng `ThreadLocal` hoặc tự chia sẻ mutable map cho mọi request. Ngược lại, nếu thư viện logging/tracing dựa MDC thì cần cơ chế bridge/context propagation thích hợp, không chắc MDC đi theo mọi operator qua mọi thread chỉ vì return type là Mono.

Với **reactive transaction**, Spring dùng transaction context gắn với reactive pipeline khi `ReactiveTransactionManager` được cấu hình, thay vì giả định giao dịch JDBC `ThreadLocal` đi theo thread xuyên `publishOn`/`subscribeOn`. Trả Publisher cho transaction interceptor để lifecycle được quản lý; không tự `subscribe()` rồi cho rằng transaction hiện hành bao bọc mọi thứ.

**Bảo mật:** Spring Security cho WebFlux dùng reactive security model/`SecurityWebFilterChain` và reactive context handling. Không sao chép cấu hình Servlet `SecurityFilterChain`/`HttpServletRequest` và cho rằng nó xử lý đúng WebFlux. Mỗi endpoint vẫn phải authorize dù reactive chain non-blocking.

## 15. Cancellation, timeout, retries và tài nguyên hữu hạn

Một client ngắt kết nối có thể khiến subscription bị cancel; không phải mọi thư viện legacy/downstream operation tự dừng ngay. Với R2DBC/WebClient, cancellation có thể giải phóng resources theo driver/client semantics, nhưng cần kiểm chứng resource lifecycle thực tế.

Đặt timeout phù hợp:

~~~java
return inventoryGateway.getStock(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                ex -> Mono.just(new StockFallback(id, 0)));
~~~

Đây là snippet nghiệp vụ minh họa, chưa runnable độc lập vì `StockFallback` và return type phải khớp, cần import `TimeoutException`. **Fallback stock=0 có thể không hợp lý trong thương mại**: chỉ dùng giá trị fallback khi domain cho phép; còn không thì trả lỗi HTTP 503/504 hoặc kết quả partial có định nghĩa rõ.

Không đặt retry vô hạn:

~~~java
return remoteMono.retry();
~~~

Đoạn này là anti-pattern đối với remote service: task có thể gửi request liên tục khi upstream lỗi. Hãy giới hạn số lần, backoff + jitter, chỉ retry idempotent operations khi hợp lý, và áp tổng deadline. Mỗi retry có chi phí capacity thật.

### 15.1. BoundedElastic không thay admission control

Dù scheduler có giới hạn thread/queue, vẫn cần:
- limit số requests/traces đang active;
- limit `flatMap` concurrency;
- HTTP client connection pool limits;
- DB connection pool size và acquire timeout;
- per-tenant/per-user quotas;
- circuit breaker/bulkheads và rate limiting;
- bounded buffers cho streaming/event processing;
- metrics cho cancel, timeout, OOM và scheduler saturation.

Nếu upstream max concurrency là 50 mà bạn mở 5.000 in-flight requests, WebFlux không khiến upstream có thêm 4.950 slots.

### 15.2. Tài nguyên gửi HTTP response

Client đọc chậm có thể giữ TCP connection và buffers lâu. Backpressure trong reactive chain giúp quản lý dòng dữ liệu tại các ranh giới hỗ trợ nó, nhưng `collectList` và các gateway buffering có thể vẫn gom hàng MB/GB. Đánh giá response size, streaming content type, codec `maxInMemorySize`, slow-reader rate và proxy caching/buffering.

## 16. Khi nào chọn MVC, WebFlux hoặc kết hợp?

| Điều kiện hiện tại | Hướng đề xuất để thử trước | Vì sao |
| --- | --- | --- |
| MVC ổn định, JPA/JDBC là lõi | Giữ MVC, tối ưu DB/SQL/pool | Đổi WebFlux không loại bỏ blocking driver |
| Đa số endpoints CPU-bound, response nhanh | Giữ stack phù hợp, tối ưu thuật toán/CPU | Reactive không tự tạo CPU |
| Nhiều HTTP upstream calls có độ trễ | Thử `WebClient` trên MVC trước | Có thể nhận lợi ích I/O concurrency mà không rewrite |
| Xây mới service I/O-bound với R2DBC + async HTTP | Đo WebFlux thực tế | Toàn chuỗi có điều kiện non-blocking |
| Streaming/SSE rất nhiều kết nối chờ | So sánh WebFlux với MVC async | Mô hình kết nối/threads có thể khác đáng kể |
| Legacy SDK bắt buộc blocking | MVC hoặc WebFlux với bounded adapter có giám sát | Không che mất blocking chỉ bằng Mono |
| Team ít kinh nghiệm Reactor, debugging khó | Giữ MVC nếu SLO đáp ứng | Chi phí vận hành/learning curve là chi phí thật |
| API có tail latency do DB lock | Fix DB, pool, query plan trước | Web stack không sửa lock contention |
| Hệ thống cần throughput cao nhất trên CPU-bound work | Benchmark stack/GC/serialization thực | Không kết luận theo marketing |
| Migrate một phần sang reactive | Phân tách boundary rõ, thử POC nhỏ | Giảm blast radius và tăng khả năng rollback |

### 16.1. Một cây quyết định ngắn

~~~text
Dịch vụ đã đạt SLO và chi phí chấp nhận được?
   |
   +-- Có -> Không nhất thiết chuyển WebFlux
   |
   +-- Không:
        |
        +-- Bottleneck ở DB/SQL/JDBC locks?
        |       -> Tối ưu dữ liệu/query trước
        |
        +-- Bottleneck là nhiều remote I/O chờ?
        |       -> Thử WebClient, concurrency/timeout/pool
        |       -> Đánh giá WebFlux+reactive drivers nếu lợi ích đo được
        |
        +-- CPU-bound / serialization?
        |       -> Tối ưu CPU/algorithm/codec/GC
        |
        +-- Connection/streaming pressure?
                -> Benchmark WebFlux vs MVC async end-to-end
~~~

WebFlux là **một lựa chọn kiến trúc**, không phải mặc định tốt hơn cho mọi service.

## 17. Anti-patterns trong benchmark

### 17.1. So sánh hai đường I/O khác nhau

Không công bằng nếu:
- MVC dùng JDBC đến DB thật còn WebFlux trả `Mono.just` trong memory.
- MVC dùng `Thread.sleep` còn WebFlux dùng `Mono.delay`.
- MVC test đi qua TLS/gateway còn WebFlux gọi trực tiếp local Netty.
- WebFlux dùng R2DBC pool 100 connections còn MVC JDBC pool 10.
- MVC gzip JSON còn WebFlux không gzip hoặc trả payload nhỏ hơn.

Hai phiên bản phải có **cùng nghĩa vụ nghiệp vụ và chất lượng service**.

### 17.2. Closed-loop benchmark che slow tail

Client chỉ gửi request mới sau khi request trước hoàn tất có thể giảm load thực khi server chậm, dẫn đến **coordinated omission** trong một số công cụ đo. Cần cân nhắc open-loop arrival scenarios hoặc công cụ hỗ trợ latency correction thích hợp, đồng thời không để load generator là bottleneck.

### 17.3. Thay đổi concurrency rồi kết luận latency

Khi tăng concurrency, throughput có thể tăng đến điểm saturation nhưng p99 cũng tăng mạnh. Không so đơn thuần RPS lớn nhất rồi bỏ qua SLA hoặc 503. Chọn ngưỡng p99/tỷ lệ lỗi trước, xem stack nào có **tổng chi phí thấp hơn** tại SLA ấy.

### 17.4. Chỉ đo một lần

JIT compilation, heap warm-up, database caches, background GC, noisy neighbors và OS scheduling làm số đo biến động. Thực hiện nhiều trial độc lập, lấy distribution/confidence interval, ghi rõ môi trường và cấu hình. Không tự bịa chênh lệch phần trăm WebFlux/MVC nếu chưa có số liệu thật.

## 18. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| WebFlux vẫn chậm hơn MVC | Workload CPU-bound, overhead reactive, DB/serialization bottleneck | Xem profile, đo đúng workload |
| Chỉ một vài request block làm toàn server chậm | JDBC/SDK/Thread.sleep trên event loop | Tìm stack traces, offload hoặc thay reactive client |
| `block()` gây exception trong Reactor Netty | Blocking trên non-blocking thread | Trả Mono/Flux, không gọi block trong handler |
| Scheduler boundedElastic đầy queue | Legacy blocking tasks vượt capacity | Giới hạn requests, DB calls, timeout, admission control |
| Memory tăng khi download nhiều | `collectList`/`readAllBytes`, buffering gateway | Stream có giới hạn, backpressure, quotas |
| p99 cao dù threads ít | DB/upstream saturated, event-loop blocked, network, GC | Thu thập end-to-end traces |
| Response 200 nhưng data sai | Pipeline combine/zip empty, retry, mutable state | Kiểm tra semantics, unit/integration tests |
| SSE clients ngắt nhưng resources còn | Cancellation/cleanup chưa triển khai | `doFinally`, lifecycle hooks, limit subscribers |
| Debug mất request ID | ThreadLocal không tự theo reactive operator | Reactor Context/Micrometer propagation |
| `@Transactional` không bao quát stream | Trộn reactive và imperative transaction managers | ReactiveTransactionManager, return Publisher |
| Boot chạy MVC dù đã thêm WebFlux | Cả `spring-boot-starter-web` lẫn webflux | Chỉ chọn WebFlux starter hoặc config explicit |
| WebTestClient pass nhưng production fail | H2 in-memory/test không đại diện I/O thật | Integration tests với downstream/proxy thực |
| Retry làm upstream sập nặng hơn | Retry không bounded, không backoff | Timeout, backoff, jitter, circuit breaker |
| DB pool hết connections | Quá nhiều in-flight queries | Điều chỉnh pool/concurrency + fix slow SQL |
| Chỉ số RPS đẹp nhưng timeout tăng | Bỏ errors khỏi mẫu hoặc overload | Đo successful RPS và error/timeout cùng lúc |
| Dùng blocking logger | Async appender không có hoặc sync network sink | Quan sát log sink, giới hạn và queue |

## 19. Câu hỏi ôn tập

**1. Vì sao `Mono<T>` không chứng minh endpoint non-blocking?**

Vì JDBC, file read, `Thread.sleep` hoặc `block()` có thể đã chạy trước khi tạo Mono hoặc bên trong pipeline. Return type không xác định implementation I/O của từng tầng.

**2. WebFlux có luôn cho p99 tốt hơn MVC không?**

Không. Điều đó phụ thuộc workload, concurrency, backpressure, blocking boundaries, CPU/GC, DB pool và nhiều yếu tố khác. Phải benchmark end-to-end.

**3. Khi service đang dùng JPA/JDBC, chuyển controller sang WebFlux đã đủ chưa?**

Chưa. JDBC/JPA truyền thống vẫn blocking. Có thể offload tạm trên bounded scheduler, nhưng vẫn dùng threads/connections và chưa thành full reactive database path.

**4. `WebClient` có chỉ chạy được trong WebFlux không?**

Không. Spring MVC cũng có thể dùng WebClient. Đây thường là một cách thử tối ưu I/O từ từ.

**5. Vì sao `Mono.delay` không phải benchmark tương đương với JDBC query mất 200 ms?**

Vì timer reactive không chặn thread/DB connection, không mô phỏng SQL locks, networking, pool wait và downstream resource consumption của query thật.

**6. `flatMap(fn, 8)` có giải quyết mọi overload không?**

Không. Nó giới hạn inner concurrency ở operator cụ thể; vẫn cần giới hạn HTTP connections, DB pool, request arrival rate, retries và memory.

**7. Khi nào nên dùng `Mono.fromCallable(...).subscribeOn(boundedElastic())`?**

Khi bắt buộc wrap một synchronous blocking call trong reactive app để tránh block event loop; đây là phương án chuyển tiếp, không biến I/O đó thành non-blocking thật.

**8. Test WebFlux + R2DBC/H2 của bài chứng minh điều gì?**

Nó xác minh HTTP response và truy vấn DB theo reactive API hoạt động đúng qua embedded server; **không** chứng minh WebFlux nhanh hơn MVC trên DB production.

**9. Nếu benchmark có RPS tăng nhưng p99 và errors đều tăng, có thể kết luận chiến thắng không?**

Không nếu SLA yêu cầu p99 và error budget. Phải so sánh successful RPS tại cùng ngưỡng chất lượng service.

**10. Bottleneck nằm ở database lock, đổi Netty/WebFlux có khắc phục trực tiếp không?**

Không. Nên tối ưu query/transaction/index/pool và concurrency trước.

## 20. Checklist đánh giá trước quyết định kiến trúc

1. Phát biểu rõ tiêu chí thành công: **successful RPS, p95/p99, error budget, CPU/RAM, cost**.
2. Vẽ và ghi chú toàn chuỗi I/O: ingress/proxy → handler → auth → DB/cache/upstream → serializer → response.
3. Xác minh từng **driver/client** blocking hay non-blocking; xem cả callbacks/schedulers, không chỉ return types.
4. Kiểm tra `.block()`, `Thread.sleep`, JDBC/JPA, synchronous filesystem, unbounded queues, `collectList`.
5. Nếu có blocking code trong WebFlux, dùng bounded adapter có timeout/concurrency budgets, theo dõi saturation; lên kế hoạch thay driver nếu lợi ích tương xứng.
6. Dùng R2DBC/WebClient/reactive clients chỉ khi phù hợp với DB, driver, team, operational tooling và production capabilities.
7. Benchmark MVC, MVC+WebClient/MVC async và WebFlux theo **cùng nghĩa vụ end-to-end**; không so sánh `Thread.sleep` với `Mono.delay`.
8. Đo nhiều workload: CPU-bound, remote high latency, DB contention, streaming, clients chậm và overload.
9. Theo dõi p50/p95/p99, successful RPS, timeouts/errors, CPU, heap/RSS, event-loop, threads, pool waits, queues, GC và downstream.
10. Kiểm thử security, transactions, cancellation, retries, backpressure, tracing/Reactor Context và resource cleanup.
11. Giữ giới hạn connections/queue/concurrency, không coi reactive backpressure là quota toàn hệ thống.
12. Nếu MVC đang đạt SLO ổn định với chi phí hợp lý, **không có nghĩa vụ** phải chuyển WebFlux. Chọn giải pháp đơn giản nhất đáp ứng yêu cầu được đo đạc.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — WebFlux overview, performance và concurrency model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html)
- [Spring Framework 6.2 — WebFlux reference](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html)
- [Spring Framework 6.2 — Reactive libraries, Mono/Flux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-reactive-libraries.html)
- [Spring Framework 6.2 — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 — SQL databases, R2DBC và DatabaseClient](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot — SQL script database initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Project Reactor — FAQ: wrapping a synchronous/blocking call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
- [Project Reactor — Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [R2DBC specification](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/)
