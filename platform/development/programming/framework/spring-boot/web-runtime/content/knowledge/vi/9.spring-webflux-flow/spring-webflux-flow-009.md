# Event loop trong Spring WebFlux và sự khác biệt với luồng xử lý Servlet

## 1. Hai mô hình thực thi HTTP request

Khi xây dựng API bằng Spring Boot, **Spring MVC trên Servlet stack** và **Spring WebFlux trên Reactive stack** có thể cùng cung cấp REST endpoint nhưng khác đáng kể ở cách phục vụ các request đồng thời.

- **Spring MVC đồng bộ trên Servlet container** (Tomcat, Jetty, Undertow): một HTTP request đang được thực thi theo kiểu đồng bộ thường chiếm một **worker thread** của container. Nếu controller đợi JDBC, I/O đồng bộ hoặc HTTP client blocking, thread đó cũng thường bị giữ lại trong lúc đợi.
- **Spring WebFlux với Reactor Netty**: một nhóm **event-loop threads** điều phối các sự kiện I/O và callback của nhiều connection. Khi dùng I/O non-blocking, event-loop thread không phải ngồi chờ dữ liệu của một request; nó có thể xử lý sự kiện của connection khác.

Đây không phải đối lập tuyệt đối giữa "Servlet chỉ có một thread" và "WebFlux chỉ dùng một thread". Servlet có thread pool, Servlet async và có thể dùng virtual threads ở môi trường phù hợp; WebFlux sử dụng nhiều event-loop threads và có thể dùng các scheduler/worker khác. So sánh chính xác nhất là **Servlet request đồng bộ kiểu thread-per-active-request** so với **mô hình event-driven non-blocking của Reactor Netty**.

## 2. Event loop là gì?

**Event loop** là vòng xử lý liên tục theo dõi các sự kiện đã sẵn sàng: kết nối mới, socket có dữ liệu đọc, socket có thể ghi, callback được lên lịch và các tín hiệu I/O khác. Một event-loop thread thường xử lý sự kiện từ **nhiều channel/connection**, thay vì được cấp độc quyền cho toàn bộ thời gian sống của một HTTP request.

~~~text
Connection A ---\
Connection B ----+----> Sự kiện I/O ----> Event loop E1 ---> callback A, B, ...
Connection C ---/                             |
                                              +----> tiếp tục quan sát event

Connection D ---\
Connection E ----+----> Sự kiện I/O ----> Event loop E2 ---> callback D, E, ...
~~~

Sơ đồ khái quát này không biểu diễn chính xác mọi chi tiết Netty transport. Một Netty channel thường được gắn với một event loop trong nhóm trong vòng đời của channel, còn nhiều channel chia sẻ cùng event loop. Server có nhiều event loop, không phải một loop toàn cục duy nhất.

Điều kiện để cơ chế hiệu quả là **callback phải chạy nhanh, không chặn thread quá lâu**. Ví dụ:

1. Request A đến và bắt đầu một truy vấn I/O non-blocking.
2. Thread đăng ký thao tác chờ dữ liệu rồi trả quyền điều khiển, không giữ worker thread chỉ để chờ kết quả.
3. Cùng event loop xử lý callback của B hoặc C trong thời gian I/O của A chưa xong.
4. Khi I/O của A có kết quả, callback của A tiếp tục tạo response.

Từ đó thấy **event loop là cơ chế thực thi**; nó không phải nơi chứa dữ liệu request, không phải một thread mới sinh cho mỗi request, cũng không phải một dạng bộ nhớ đệm.

## 3. Đường đi request trong Servlet đồng bộ

Với Spring MVC, request thường theo luồng:

~~~text
HTTP client
  -> Embedded Servlet container
  -> FilterChain
  -> DispatcherServlet
  -> HandlerMapping / HandlerAdapter
  -> Controller
  -> Service / JDBC / HTTP client
  -> HTTP response
~~~

Đối với một controller đồng bộ đang thực thi, container thường dành một worker thread cho phần xử lý request. Giả sử ba request đồng thời gọi JDBC blocking:

~~~text
Request A -> Tomcat worker T1 -> JDBC call -> đợi -> controller trả response
Request B -> Tomcat worker T2 -> JDBC call -> đợi -> controller trả response
Request C -> Tomcat worker T3 -> JDBC call -> đợi -> controller trả response
~~~

Khi mỗi request còn đang chờ I/O đồng bộ, worker thread có thể tiếp tục bị chiếm. Nếu nhiều request đồng thời và số worker bị giới hạn, các request tiếp theo phải đợi trong queue, bị timeout hoặc bị từ chối theo cấu hình container.

**Điều quan trọng:** đây không phải cơ chế **thread-per-TCP-connection**. Một kết nối HTTP keep-alive có thể tồn tại khi không có request đang thực thi. Container tái sử dụng worker thread cho request khác sau khi xử lý xong.

Và cũng không nên tuyên bố Spring MVC "không có async": Servlet 3.x có `AsyncContext` và I/O API không chặn; Spring MVC hỗ trợ `Callable`, `DeferredResult` và các tích hợp async, có thể giải phóng request thread trong khi đợi công việc.

## 4. Đường đi request trong WebFlux / Reactor Netty

Nếu ứng dụng dùng `spring-boot-starter-webflux` và không kéo thêm Servlet MVC khiến Spring Boot chọn stack khác, embedded server thường là **Reactor Netty**. Đường đi khái quát:

~~~text
HTTP client
  -> Reactor Netty TCP/HTTP server
  -> Event-loop callback
  -> WebFilter chain / DispatcherHandler
  -> WebFlux HandlerMapping / HandlerAdapter
  -> Reactive controller trả Mono/Flux
  -> Reactive operators + non-blocking client I/O
  -> Response được ghi khi dữ liệu sẵn sàng
~~~

Trong khi một request đợi remote HTTP call sử dụng `WebClient`, event loop có thể phục vụ các request khác. Không cần một event-loop thread đứng chờ cho từng network call.

Ví dụ timeline:

~~~text
T0: E1 nhận request A -> gọi reactive client -> không chờ đồng bộ
T1: E1 nhận request B -> chuẩn bị response B
T2: E2 nhận request C -> gọi reactive client -> không chờ đồng bộ
T3: dữ liệu A sẵn sàng -> callback A xử lý response
T4: dữ liệu C sẵn sàng -> callback C xử lý response
~~~

Không nên suy ra rằng callback của một request **luôn** chạy trên cùng một thread. Khi pipeline có `publishOn`, `subscribeOn`, timer, client hoặc các asynchronous boundary khác, một giai đoạn có thể chạy trên scheduler khác.

### 4.1. Bảng so sánh

| Khía cạnh | Servlet MVC đồng bộ điển hình | WebFlux trên Reactor Netty điển hình |
|---|---|---|
| Phục vụ request | Worker thread xử lý phần đồng bộ của request | Một nhóm event-loop threads phục vụ nhiều channel |
| Chờ I/O | Với blocking API, thread thường đứng chờ | Với non-blocking API, thread không bị giữ trong lúc đợi |
| Khi gọi JDBC truyền thống | Hợp mô hình xử lý đồng bộ | Nếu gọi trên event loop sẽ gây nghẽn |
| HTTP client phổ biến | `RestClient` hoặc client đồng bộ; cũng có thể dùng WebClient | `WebClient` với HTTP client non-blocking |
| Controller | Thường trả DTO, `ResponseEntity`, view | Có thể trả `Mono<T>` / `Flux<T>` |
| Phân bổ thread | Servlet worker pool, async executor nếu có | Event loops + schedulers + worker của thư viện phụ thuộc |
| Rủi ro quá tải | Cạn worker pool, queue request dài | Event loop bị chặn, scheduler queue, downstream saturation |
| Dữ liệu theo request | Dễ đi theo call stack đồng bộ | Có thể qua nhiều callback/threads; cần context propagation |

**Non-blocking không có nghĩa tự động nhanh hơn.** Nếu DB chỉ xử lý được một lượng truy vấn nhất định, số HTTP request tăng vẫn có thể làm DB quá tải dù event-loop threads không bị giữ.

## 5. Mối liên hệ giữa Reactor, Mono/Flux và thread

Spring WebFlux sử dụng Project Reactor. Hai khái niệm thường gặp:

- `Mono<T>` đại diện cho publisher phát tối đa một phần tử (có thể hoàn tất rỗng hoặc lỗi).
- `Flux<T>` đại diện cho publisher có thể phát nhiều phần tử, hoàn tất hoặc lỗi.

Publisher mô tả pipeline; **không phải một thread**. Một số nguồn là **cold publisher**: tác vụ chỉ bắt đầu khi có subscription. Với HTTP controller trả publisher, WebFlux quản lý quá trình subscribe nhằm hoàn tất response; thông thường không nên tự `subscribe()` thủ công trong controller để làm việc nghiệp vụ.

Ví dụ fragment Reactor (yêu cầu dependency Reactor và import `reactor.core.publisher.Mono`):

~~~java
Mono<String> value = Mono.fromSupplier(() -> {
    System.out.println("SUPPLIER");
    return "ready";
});

System.out.println("BEFORE");
value.subscribe(System.out::println);
~~~

Vì đây là nguồn đồng bộ, không có scheduler chuyển thread, kết quả do fragment in ra là:

~~~text
BEFORE
SUPPLIER
ready
~~~

`Mono.just(blockingCall())` **không** làm lời gọi `blockingCall()` bất đồng bộ: Java phải thực thi biểu thức đó trước khi tạo publisher. Tương tự, callback `map` thông thường chạy trên thread đang phát signal, không tự chuyển sang thread riêng.

## 6. Ví dụ Spring Boot chạy được: xem thread và non-blocking timer

Ví dụ dùng **Java 17+, Spring Boot 3.x**, một dự án Gradle đã có Spring Boot plugin/dependency management. Chỉ dùng starter WebFlux ở server, không thêm `spring-boot-starter-web` trong ví dụ này:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Tệp **src/main/java/demo/webflux/EventLoopDemoApplication.java**:

~~~java
package demo.webflux;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class EventLoopDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventLoopDemoApplication.class, args);
    }
}

@RestController
class EventLoopDemoController {

    @GetMapping("/demo/thread")
    Mono<Map<String, String>> showThread() {
        return Mono.defer(() -> Mono.just(
                Map.of("thread", Thread.currentThread().getName())
        ));
    }

    @GetMapping("/demo/timer")
    Mono<String> nonBlockingTimer() {
        return Mono.delay(Duration.ofMillis(150))
                .map(ignored -> "done");
    }

    @GetMapping("/demo/offloaded")
    Mono<Map<String, String>> offloadedBlockingCall() {
        return Mono.fromCallable(() -> {
                    // Giả lập thư viện đồng bộ để quan sát cách offload.
                    Thread.sleep(100);
                    return Map.of(
                            "result", "finished",
                            "thread", Thread.currentThread().getName()
                    );
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Giải thích:

1. `/demo/thread` dùng `Mono.defer` để lấy tên thread **khi publisher được subscribe**, không lấy khi method mới tạo publisher. Với Reactor Netty mặc định, thường sẽ thấy tên thread liên quan event loop.
2. `/demo/timer` dùng timer của Reactor, không chiếm một event-loop thread để đứng chờ 150 ms. Callback sau `Mono.delay` có thể chạy ở scheduler khác, vì vậy đừng giả định tất cả operator đều chạy trên event loop.
3. `/demo/offloaded` giả lập công việc blocking bằng `Thread.sleep` nhưng đưa nó vào `Mono.fromCallable` và lập lịch source bằng `subscribeOn(Schedulers.boundedElastic())`. Đây là ví dụ quan sát, **không khuyến khích dùng Thread.sleep trong API thực**.

Chạy ứng dụng trong dự án đã cấu hình main class đúng:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. Tại terminal khác:

~~~bash
curl -s http://localhost:8080/demo/thread
curl -s http://localhost:8080/demo/timer
curl -s http://localhost:8080/demo/offloaded
~~~

Body của endpoint timer chính xác:

~~~text
done
~~~

Hai endpoint còn lại trả JSON có cấu trúc như các ví dụ minh họa:

~~~json
{"thread":"reactor-http-nio-2"}
~~~

~~~json
{"result":"finished","thread":"boundedElastic-1"}
~~~

**Tên thread và số thứ tự là biến động**, không được khẳng định đây là stdout cố định. Server transport, lịch scheduler và phiên bản runtime có thể làm tên khác; thứ tự key JSON cũng không cần cố định.

Các source Java trên nằm trong một file, chỉ có `EventLoopDemoApplication` là public class, các class còn lại cùng package nên có thể được quét. Không thể chạy bằng `javac` thuần nếu thiếu Spring Boot/Reactor dependencies; dùng Gradle/Maven của dự án.

## 7. Vì sao blocking trên event loop nguy hiểm?

Event loop phải quay lại xử lý event của nhiều connection. Nếu callback gọi:

- `Thread.sleep(...)`;
- JDBC/JPA/Hibernate đồng bộ;
- HTTP client blocking;
- `Future.get()` hoặc chờ lock lâu;
- File I/O đồng bộ kéo dài;
- `Mono.block()` / `Flux.blockFirst()`;
- Phép tính CPU dài, serialize lượng dữ liệu lớn;

thì event-loop thread có thể không quay lại xử lý những connection khác đúng lúc.

Có hai dạng chiếm dụng:

1. **Blocking wait:** thread đợi database/network/lock mà không làm việc hữu ích.
2. **CPU monopolization:** thread chạy tính toán lâu, dù không đợi I/O, làm callback khác bị trễ.

Một operator Reactor không bảo đảm code bên trong nó là non-blocking:

~~~java
@GetMapping("/bad")
Mono<String> bad() {
    return Mono.just("ok")
            .map(value -> {
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                return value;
            });
}
~~~

Đây là fragment của controller WebFlux; nếu pipeline chạy trên Netty event loop, đoạn `Thread.sleep` giữ event-loop thread khoảng một giây. Nhiều connection cùng loop có thể tăng độ trễ theo.

Reactor có thể phát `IllegalStateException` khi `block()` được gọi trên những thread được đánh dấu non-blocking. **Không được dựa vào exception ấy để phát hiện tất cả thao tác blocking**: JDBC và Thread.sleep có thể chặn mà không phát ra lỗi giống vậy.

## 8. Cách chuyển code blocking khỏi event loop

Trong hệ thống có legacy API đồng bộ nhưng muốn dùng WebFlux, dùng một nguồn deferred/callable và scheduler phù hợp:

~~~java
Mono<String> safe = Mono.fromCallable(() ->
        legacyClient.fetch()
).subscribeOn(Schedulers.boundedElastic());
~~~

`legacyClient` là đối tượng nghiệp vụ giả định; fragment chưa độc lập biên dịch. `Mono.fromCallable` trì hoãn thực thi `fetch()` đến subscription; `subscribeOn` sắp xếp subscription/source ở `boundedElastic`, tách công việc blocking khỏi event loop.

**Sai lầm dễ mắc:**

~~~java
Mono<String> wrong = Mono.just(legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Ở ví dụ sai, Java chạy `fetch()` **trước khi** `Mono.just(...)` được tạo; vì vậy lời gọi blocking có thể đã xảy ra trên request/event-loop thread. Việc thêm `subscribeOn` sau `just` không di chuyển được phần code đã thực thi.

Một lưu ý khác: `boundedElastic` không có thread/queue vô hạn. Nếu hàng nghìn request cùng chờ JDBC chậm, pool/queue có thể quá tải. Chuyển sang thread khác giúp bảo vệ event loop, **không biến blocking I/O thành non-blocking I/O**. Cần timeout của driver, connection pool, giới hạn concurrency và tải downstream.

### 8.1. subscribeOn và publishOn khác nhau

- `subscribeOn(scheduler)` ảnh hưởng đến ngữ cảnh subscription/source upstream trong reactive pipeline.
- `publishOn(scheduler)` đặt một ranh giới scheduler cho các tín hiệu/operator downstream phía sau nó.
- Không phải mỗi lần gọi `map` hay `flatMap` là Reactor tạo thread mới.
- Một pipeline có thể chuyển thread nhiều lần; không nên phụ thuộc việc toàn bộ request giữ cùng một thread.

Ví dụ chỉ minh họa chỗ đặt scheduler (cần có `source` và `cpuBoundTransform` do ứng dụng định nghĩa):

~~~java
Mono<String> transformed = source
        .publishOn(Schedulers.parallel())
        .map(value -> cpuBoundTransform(value));
~~~

`Schedulers.parallel()` phù hợp hơn cho công việc CPU-bound có giới hạn, **không phù hợp để chờ JDBC blocking**. Không tùy tiện chuyển scheduler cho từng operator vì có chi phí điều phối và chuyển ngữ cảnh.

## 9. Chọn client non-blocking nếu muốn reactive end-to-end

Nếu controller trả Mono nhưng bên trong gọi `RestClient` đồng bộ hoặc JDBC blocking ngay trên event loop, đường xử lý vẫn có đoạn blocking.

Ví dụ **chống-pattern** với WebClient:

~~~java
@GetMapping("/bad-orders/{id}")
OrderDto badOrder(@PathVariable long id) {
    return webClient.get()
            .uri("/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class)
            .block();
}
~~~

Đây là fragment không độc lập biên dịch vì cần bean `webClient`, DTO và imports. `block()` chờ kết quả đồng bộ, có thể gây nghẽn hoặc bị Reactor từ chối trên event loop.

Cách tự nhiên hơn:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderDto> getOrder(@PathVariable long id) {
    return webClient.get()
            .uri("/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class);
}
~~~

Khi dùng `WebClient` và connector reactive phù hợp, HTTP client có thể không giữ event-loop thread trong lúc đợi remote server. Cần tiếp tục quản lý timeout, số connection, pending acquire queue và retry; không phải cứ non-blocking là chịu được lượng request vô hạn.

Với database, JDBC/JPA truyền thống thường blocking, còn R2DBC là một hướng dữ liệu reactive có thể cân nhắc **khi dependency, transaction và tính năng driver tương thích**. Không bắt buộc chuyển mọi dự án sang R2DBC chỉ vì WebFlux; nếu nghiệp vụ chủ yếu JDBC blocking, Spring MVC có thể đơn giản hơn.

## 10. Backpressure và concurrency không phải một khái niệm

Project Reactor tuân theo Reactive Streams: subscriber có thể phát tín hiệu **demand** để yêu cầu số phần tử sẵn sàng nhận. Backpressure giúp điều tiết dữ liệu giữa các thành phần hỗ trợ cơ chế đó.

Nhưng **backpressure không đồng nghĩa toàn bộ HTTP request tự bảo đảm không tràn bộ nhớ**:

- Một JSON request lớn vẫn có giới hạn buffer/decoder.
- Một nguồn không hỗ trợ demand có thể cần cơ chế buffer/drop/error.
- Downstream HTTP/DB có giới hạn connection, tốc độ xử lý và rate limit.
- Một ứng dụng có thể tạo quá nhiều inner publishers qua `flatMap` nếu không giới hạn concurrency.

Fragment minh họa giới hạn số request remote đồng thời:

~~~java
Flux<Result> results = ids.flatMap(
        id -> remoteClient.fetch(id),
        8
);
~~~

Đây là fragment: `ids`, `Result` và `remoteClient` phải được định nghĩa trong ứng dụng. Số 8 giới hạn concurrent inner publishers trong `flatMap` tại điểm này; không phải thông số mặc định của Reactor Netty. Cần đo throughput, error rate và downstream latency để chọn mức phù hợp.

**Event loop** quyết định cách thực thi I/O/callback; **backpressure** điều tiết nhịp dữ liệu; **concurrency limit** kiểm soát số công việc đồng thời. Chúng hỗ trợ nhau nhưng không thể thay thế lẫn nhau.

## 11. ThreadLocal, MDC và request context

Trong Servlet đồng bộ, code có thể dùng `ThreadLocal` để giữ request ID, security context hoặc dữ liệu cho log. Với reactive pipeline, operator có thể chạy ở nhiều thread:

~~~text
Event-loop thread A: ThreadLocal(requestId=123)
      |
      +-- publishOn(boundedElastic)
                    |
                    v
         boundedElastic thread B:
         ThreadLocal không tự mang requestId=123
~~~

Đừng giả định ThreadLocal tự đi qua scheduler boundary. Project Reactor có **Context** gắn với subscriber chain; Spring Security reactive có cơ chế reactive security context, và hệ tracing có tích hợp context propagation.

Fragment Reactor Context, có import `reactor.core.publisher.Mono`:

~~~java
Mono<String> request = Mono.deferContextual(ctx ->
        Mono.just("requestId=" + ctx.get("requestId"))
).contextWrite(ctx -> ctx.put("requestId", "abc"));

request.subscribe(System.out::println);
~~~

Output của fragment đồng bộ trên:

~~~text
requestId=abc
~~~

`Context` không phải biến toàn cục dùng chung cho mọi request. Không nên tự lưu secret/token ở nơi có thể bị in vào log, và không giả định mọi thư viện thứ ba tự nhận Reactor Context nếu thiếu tích hợp.

## 12. Timeout, cancellation và luồng bất đồng bộ

WebFlux có thể cancel subscription khi client ngắt kết nối hoặc khi một operator không còn cần kết quả. Với một pipeline:

~~~java
Mono<Item> item = itemClient.fetch(id)
        .timeout(Duration.ofSeconds(2));
~~~

Đây là fragment; `Item`, `itemClient` và `id` thuộc ứng dụng chưa được định nghĩa. Operator timeout giúp giới hạn thời gian chờ signal của reactive pipeline. Tuy nhiên **cancellation hoặc timeout ở tầng Reactor không bảo đảm dừng ngay một lệnh JDBC blocking** đang chạy trong OS thread. Thư viện I/O có thể cần timeout riêng.

Cần kết hợp:

1. HTTP client connection/connect/read/response timeout phù hợp.
2. DB connection/query timeout và giới hạn connection pool.
3. Giới hạn concurrency và retry có backoff, có số lần tối đa.
4. Cancellation/error handling, đóng resource khi không còn dùng.
5. Tránh fire-and-forget bằng `subscribe()` không kiểm soát trong controller.

Ngay cả với WebFlux, một callback xử lý CPU quá nặng cũng có thể chiếm event loop; timeout không sửa được nguyên nhân CPU starvation.

## 13. So sánh hiệu năng bằng đo đạc, không bằng khẩu hiệu

Giả sử 100 request đồng thời, mỗi request phải chờ API ngoài khoảng 200 ms và chỉ mất 2 ms CPU để xử lý:

- Với Servlet đồng bộ gọi API blocking, nhiều worker thread có thể cùng bị chiếm trong thời gian chờ.
- Với WebFlux dùng HTTP client non-blocking, event-loop thread không nhất thiết bị giữ khi API ngoài chưa trả dữ liệu.

Tuy nhiên, điều này **không chứng minh WebFlux luôn nhanh hơn**. Nếu remote API có rate limit, database pool có 10 connections hoặc CPU bị bão hòa, throughput vẫn bị giới hạn. MVC async hoặc virtual threads có thể giảm chi phí chờ ở một số workload.

Little's Law ở trạng thái ổn định:

~~~text
Concurrency trung bình ≈ throughput (requests/giây) × latency trung bình (giây)
~~~

Ví dụ throughput 200 requests/giây và latency trung bình 0,25 giây tương ứng khoảng **50 request đang ở trong hệ thống**. Không được dùng con số 50 đó làm số event-loop threads cần tạo: concurrency của request khác với số thread phục vụ I/O.

Các chỉ số nên đo:

- Request throughput, p50/p95/p99 latency, error rate và timeout.
- CPU, heap, GC, memory stack/native memory.
- Event-loop delay hoặc pending tasks khi công cụ đo hỗ trợ.
- Trạng thái boundedElastic queue/worker khi được instrument.
- DB pool, HTTP client connection pool và downstream latency.
- Số connection đang mở và tốc độ truyền dữ liệu.
- Thời gian giữa nhận request, gọi downstream và gửi response.

Số metric và tên metric thực tế tùy phiên bản Reactor Netty, Micrometer/Actuator và cấu hình quan sát; không mặc định tất cả metric tự xuất hiện.

## 14. Điều tra khi event loop bị nghẽn

Dấu hiệu thường gặp là p95/p99 latency tăng theo cụm request, thread dump cho thấy thread `reactor-http-*` đang chờ blocking I/O hoặc xử lý CPU dài, timeout HTTP client tăng và hàng đợi tác vụ khác lớn dần.

Quy trình:

1. **Xác nhận stack thực tế.** Dùng runtime classpath, startup log, ApplicationContext để xác nhận ứng dụng chạy WebFlux với Reactor Netty, không phải Spring MVC được chọn do có cả hai starter.
2. **Đọc thread dump.** Tìm `Thread.sleep`, JDBC, file I/O, lock contention, `block()` hoặc JSON serialization/tính toán nặng trên event-loop thread.
3. **Đo từng giai đoạn.** Đừng chỉ đo thời gian controller; kiểm tra decode, service, downstream, encode và response I/O.
4. **Kiểm tra scheduler.** Sau khi offload, boundedElastic có queue tăng hoặc bị đầy không?
5. **Kiểm tra downstream.** DB/API ngoài có connection pool cạn, 429/503 hay timeout không?
6. **Thử dưới tải được kiểm soát.** So sánh trước/sau thay đổi scheduler, driver hoặc concurrency limit.
7. **Quan sát tracing.** Nếu có Micrometer/Actuator và tracing, gắn request ID/trace ID đúng cách xuyên reactive chain.

BlockHound có thể hữu ích trong môi trường phát triển/kiểm thử với phiên bản tương thích để phát hiện nhiều blocking API chạy trên thread non-blocking. Nó không phát hiện tất cả CPU hotspot và không thay thế profiler/thread dump; nên xác minh hỗ trợ của JDK/framework trước khi dùng.

Ví dụ log tên thread trong pipeline (fragment cần service và logger đã khai báo):

~~~java
return itemService.findById(id)
        .doOnNext(item -> log.debug(
                "operator thread={}", Thread.currentThread().getName()
        ));
~~~

Tên thread chỉ là nơi **operator đó** chạy vào thời điểm đo; không chứng minh toàn bộ request luôn ở thread đó. Không log token, request body nhạy cảm hoặc thông tin cá nhân.

## 15. Khi nào chọn Spring MVC, khi nào chọn WebFlux?

### Spring MVC/Servlet thường hợp lý khi

- Dự án phụ thuộc nhiều JDBC, JPA/Hibernate hoặc thư viện sync ổn định.
- Team quen debugging và transaction theo luồng đồng bộ.
- Throughput/latency hiện tại đáp ứng SLA, không có bottleneck chờ mạng cần xử lý bằng reactive.
- Hệ thống cần tương thích Servlet filters, interceptors và tích hợp hiện tại.
- Servlet async hoặc virtual threads giải quyết được nhu cầu concurrency mà không cần thay đổi toàn kiến trúc.

### Spring WebFlux/Reactor Netty thường hợp lý khi

- Có nhiều connection concurrent hoặc streaming/gateway/fan-out I/O.
- Đa số dependency quan trọng có API non-blocking.
- Team hiểu Reactor, backpressure, cancellation, scheduler và context propagation.
- Hệ thống giám sát đủ để phát hiện event-loop blocking, saturation ở queue và downstream.

### Nếu phải kết hợp

Một phần blocking có thể được cô lập bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và giới hạn concurrency. Nhưng nếu **hầu hết pipeline** đều blocking, việc dùng WebFlux có thể làm phức tạp thiết kế mà không tăng hiệu năng. Cần đánh giá bằng benchmark với workload và điều kiện production tương tự.

## 16. Lỗi thường gặp

**Lỗi 1 — Tưởng WebFlux có một thread cho tất cả request.** Thực tế Reactor Netty có nhiều event-loop threads và các scheduler khác. Cần quan sát thread dump thay vì suy luận từ tên framework.

**Lỗi 2 — Tưởng Servlet giữ một thread cho mỗi kết nối keep-alive.** Thread phục vụ request đồng bộ, còn connection có thể mở lâu sau request; Servlet cũng có async support.

**Lỗi 3 — Đưa JDBC vào `Mono.just(jdbcCall())`.** JDBC chạy **trước** khi publisher được tạo. Dùng deferred source và offload nếu bắt buộc, hoặc chọn stack đồng bộ.

**Lỗi 4 — Gọi `block()` trong WebFlux controller.** Có thể chặn event loop hoặc bị Reactor từ chối. Trả publisher, compose pipeline thay vì block.

**Lỗi 5 — Gọi `Thread.sleep` trong `map`.** Operator này không tự đổi thread. Dùng timer non-blocking hoặc scheduler phù hợp khi thật sự phải dùng blocking API.

**Lỗi 6 — Đưa JDBC vào `Schedulers.parallel()`.** Parallel scheduler phù hợp CPU-bound tasks ngắn, không dùng để chờ I/O blocking.

**Lỗi 7 — Đưa mọi việc vào boundedElastic rồi tin rằng non-blocking.** Blocking vẫn tiêu tốn worker thread/queue và downstream resource.

**Lỗi 8 — Dùng ThreadLocal/MDC như khi code sync.** Context có thể mất khi đổi scheduler. Dùng Reactor Context và tích hợp context propagation.

**Lỗi 9 — Không giới hạn concurrency/timeouts.** Non-blocking không đồng nghĩa downstream chịu được vô hạn request.

**Lỗi 10 — Chỉ nhìn số thread để so sánh hiệu năng.** Cần throughput, latency, error rate, CPU, memory, DB/HTTP pools và reliability.

**Lỗi 11 — Có cả starter-web và starter-webflux mà tưởng server chắc chắn reactive.** Mặc định Spring Boot thường ưu tiên Servlet MVC khi cả hai có mặt; kiểm tra stack khởi động thật.

**Lỗi 12 — Trả Flux nhưng gọi API blocking ở mọi phần tử.** Publisher không tự biến nguồn I/O thành non-blocking; cần kiểm tra từng chặng pipeline.

## 17. Checklist triển khai

- Xác định ứng dụng dùng Spring MVC/Servlet hay WebFlux/Reactor Netty trên thực tế.
- Không chặn event-loop thread bằng JDBC, blocking HTTP client, `block()`, `Thread.sleep` hoặc CPU operation quá dài.
- Bao blocking library bằng deferred source rồi `subscribeOn(Schedulers.boundedElastic())` khi bắt buộc.
- Ưu tiên WebClient và data access non-blocking nếu mục tiêu là reactive end-to-end.
- Dùng `parallel` cho CPU work phù hợp; hiểu `subscribeOn` và `publishOn` trước khi đổi scheduler.
- Giới hạn concurrency, buffer, HTTP/DB connection pool và retry; không coi backpressure là vô hạn tài nguyên.
- Dùng Reactor Context hoặc cơ chế propagation phù hợp để truyền request state qua các thread.
- Kiểm soát cancellation, HTTP/DB timeout, resource lifecycle và lỗi downstream.
- Theo dõi p95/p99, throughput, thread dump, event-loop delay, scheduler queue, DB pool và GC.
- Test tải khi remote service chậm, nhiều connection concurrent và client đóng kết nối.
- So sánh Servlet async/virtual threads khi workload chứa nhiều thư viện blocking.

**Ghi nhớ:** Với Servlet MVC đồng bộ, một worker thread thường gắn với phần xử lý đang thực thi của request; với WebFlux trên Reactor Netty, các event-loop threads phục vụ nhiều connection mà không đứng chờ cho I/O non-blocking. Lợi ích của WebFlux đến từ **thiết kế non-blocking xuyên suốt**, không phải chỉ từ việc trả `Mono` hoặc `Flux`. Nếu chặn event loop, chính cơ chế vốn giúp tăng concurrency lại trở thành nút thắt hiệu năng.