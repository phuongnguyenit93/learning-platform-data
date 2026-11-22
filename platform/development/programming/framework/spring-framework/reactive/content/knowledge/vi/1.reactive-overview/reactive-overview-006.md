# So sánh mô hình xử lý của Spring MVC và Spring WebFlux

## 1. Mục tiêu và bức tranh tổng quan

Spring MVC và Spring WebFlux đều xây dựng ứng dụng HTTP trong hệ sinh thái Spring. Cả hai hỗ trợ `@RestController`, `@GetMapping`, xác thực, kiểm tra dữ liệu, xử lý ngoại lệ, trả JSON và các cơ chế kiểm thử. Điểm khác biệt cốt lõi nằm ở **giả định về việc chờ I/O và cách dùng luồng (thread) khi xử lý request**:

- **Spring MVC** dựa trên Servlet API. Luồng xử lý đồng bộ thông thường cho phép controller gọi API *blocking*: trong lúc chờ cơ sở dữ liệu hoặc dịch vụ khác, luồng xử lý có thể bị giữ lại. MVC cũng có cơ chế *bất đồng bộ* riêng nên không thể kết luận “MVC chỉ xử lý đồng bộ”.
- **Spring WebFlux** được thiết kế theo mô hình *reactive, non-blocking* xuyên suốt các hợp đồng xử lý HTTP. Khi thao tác I/O thực sự non-blocking đang chờ, event-loop thread có thể phục vụ công việc khác. WebFlux thường dùng Reactor với `Mono<T>` (0 hoặc 1 giá trị) và `Flux<T>` (0 đến nhiều giá trị).
- **Bất đồng bộ (asynchronous)** nói về việc nhận kết quả sau; **non-blocking** nói về việc không buộc thread phải đứng chờ; **reactive** thêm mô hình dòng dữ liệu, tín hiệu kết thúc/lỗi và cơ chế điều tiết nhu cầu (*backpressure*). Một phương thức trả `Mono` chưa chắc đã non-blocking nếu bên trong vẫn gọi JDBC hoặc `Thread.sleep()` trên event loop.

Phạm vi bài này là **so sánh mô hình xử lý request và hệ quả thiết kế**. Không nên chọn WebFlux chỉ vì tên gọi “reactive” hay giả định hiệu năng luôn cao hơn MVC.

## 2. Bảng so sánh nhanh

| Khía cạnh | Spring MVC | Spring WebFlux |
|---|---|---|
| Nền tảng HTTP | Servlet API, thường trên Tomcat hoặc Jetty | Reactive HTTP API; có thể trên Reactor Netty hoặc adapter tới máy chủ Servlet hỗ trợ non-blocking I/O |
| Bộ điều phối | `DispatcherServlet` | `DispatcherHandler` |
| Mô hình mặc định | Imperative, một luồng xử lý request đồng bộ có thể chờ I/O | Reactive, hướng sự kiện và non-blocking theo mặc định |
| Luồng chạy | Servlet container có nhóm worker threads cho các thao tác có thể blocking | Event loop thường có số thread nhỏ; công việc không được block event loop |
| Kiểu kết quả thường gặp | `T`, `ResponseEntity<T>`; có thể `Callable`, `DeferredResult`, `Mono`/`Flux` | `Mono<T>`, `Flux<T>`, `Mono<ResponseEntity<T>>`; cũng có thể trả giá trị trực tiếp trong controller phù hợp |
| Đọc request body | Thường `@RequestBody Dto` | Có thể `@RequestBody Dto` hoặc `@RequestBody Mono<Dto>` cho luồng reactive |
| Đọc/ghi HTTP | MVC truyền thống dựa trên Servlet I/O; ghi response trong luồng async MVC vẫn có thể blocking | Hợp đồng đọc/ghi non-blocking qua runtime adapter |
| Backpressure | Có thể hỗ trợ reactive stream khi trả Publisher, nhưng ghi HTTP vẫn blocking trên executor | Reactive Streams backpressure là một phần nền tảng xử lý reactive; hiệu quả toàn tuyến còn tùy thành phần và transport |
| Truy cập dữ liệu phổ biến | JDBC, JPA/Hibernate và transaction imperative | R2DBC hoặc driver/client reactive khi cần non-blocking thực sự |
| HTTP client | `RestClient`, `RestTemplate` (mã cũ), hoặc `WebClient` | `WebClient` cho các cuộc gọi reactive |
| Xử lý tác vụ blocking | Phù hợp với cách gọi đồng bộ, cần quản lý số thread và connection pool | Phải tránh blocking trên event loop; có thể cách ly tạm qua `boundedElastic` |
| Độ phức tạp | Luồng điều khiển tuyến tính, stack trace quen thuộc | Cần hiểu tín hiệu `onNext`/`onError`/`onComplete`, scheduler, context và việc kết hợp publisher |
| Trường hợp thường hợp lý | CRUD, ứng dụng JDBC/JPA, hệ thống imperative đang ổn định | Nhiều kết nối I/O chờ đồng thời, streaming, chuỗi gọi HTTP reactive và dữ liệu reactive từ đầu đến cuối |

**Lưu ý:** “MVC dùng một thread cho mỗi connection” là cách diễn đạt thiếu chính xác. Với xử lý đồng bộ, worker thread thường gắn với một request trong thời gian thực thi; HTTP keep-alive có thể phục vụ nhiều request qua một connection, và MVC async giải phóng thread lúc chờ.

## 3. Luồng xử lý HTTP của Spring MVC

Một đường đi đồng bộ điển hình:

```text
Client
  -> Servlet container (Tomcat/Jetty)
  -> Filter chain -> DispatcherServlet
  -> HandlerMapping / HandlerAdapter -> @RestController
  -> Service -> JDBC/JPA hoặc HTTP client đồng bộ
       [worker thread chờ khi I/O blocking]
  -> trả dữ liệu -> serialize JSON -> HTTP response
```

1. Servlet container nhận yêu cầu và giao phần xử lý ứng dụng cho worker thread.
2. `DispatcherServlet` định tuyến tới controller; controller thực thi lệnh Java tuần tự.
3. Nếu service gọi JDBC/JPA hoặc API đồng bộ mất 300 ms, thread có thể bị giữ trong thời gian chờ đó; CPU không nhất thiết bận, nhưng tài nguyên thread vẫn đang bị chiếm.
4. Khi có kết quả, Spring chuyển kết quả thành HTTP response rồi trả worker thread về nhóm xử lý.

Mô hình này **đơn giản để đọc, debug và quản lý giao dịch**; đổi lại, khi có rất nhiều request cùng chờ I/O, thread pool hoặc connection pool có thể trở thành nút thắt.

### MVC vẫn có bất đồng bộ

MVC hỗ trợ `Callable<T>`, `WebAsyncTask<T>`, `DeferredResult<T>`, `CompletionStage<T>` và cả một số kiểu Reactor. Với `DeferredResult`, controller trả về một đại diện kết quả chưa có; Servlet request chuyển sang chế độ async, worker thread ban đầu được giải phóng. Khi kết quả xuất hiện, servlet container *dispatch* lại để hoàn tất response. Với `Callable`, tác vụ được chuyển tới executor.

Vì vậy **MVC async có thể giải phóng thread trong lúc chờ**. Tuy nhiên, nó đi qua cơ chế Servlet async dispatch, và theo tài liệu Spring, những lần ghi response của MVC khi stream dữ liệu vẫn là thao tác blocking được thực hiện trên executor. Điều này khác cách WebFlux xây dựng tất cả hợp đồng HTTP theo non-blocking.

## 4. Luồng xử lý HTTP của Spring WebFlux

Một đường đi điển hình trên Reactor Netty:

```text
Client
  -> Netty event loop -> HTTP adapter / WebHandler
  -> DispatcherHandler -> @RestController
  -> tạo Mono/Flux (mô tả pipeline)
  -> Spring subscribe, có tín hiệu yêu cầu dữ liệu (demand)
  -> WebClient/R2DBC đăng ký tác vụ I/O non-blocking
       [không giữ event-loop thread để đứng chờ I/O]
  -> callback/tín hiệu dữ liệu đến -> biến đổi -> ghi response non-blocking
```

1. Event loop nhận và điều phối sự kiện mạng. Một event-loop thread có thể phục vụ tiến trình xử lý của nhiều kết nối khi các thao tác không block.
2. Controller thường trả `Mono`/`Flux`, tức **mô tả phép tính bất đồng bộ**, không phải giá trị cuối đã sẵn sàng. Spring quản lý việc subscribe cho HTTP response; controller thông thường **không tự gọi** `.subscribe()`.
3. Khi một HTTP/database client reactive đang chờ, thread có thể xử lý sự kiện khác. Khi dữ liệu tới, các operator (`map`, `flatMap`, `zip`, v.v.) tiếp tục chạy theo cơ chế tín hiệu.
4. Publisher có ba loại tín hiệu cần hiểu: dữ liệu `onNext`, hoàn tất `onComplete`, lỗi `onError`; bên nhận có thể `request(n)` để thể hiện nhu cầu và có thể `cancel()`.
5. Không được giả định toàn bộ pipeline luôn chạy trên một thread. `publishOn`/`subscribeOn`, runtime và thư viện tích hợp có thể chuyển scheduler.

**Đừng nhầm event loop với “chỉ có một thread cho toàn server”.** Runtime vẫn có nhiều thread, và có thể có scheduler/connection pool riêng cho tác vụ khác. Điểm tối ưu là hạn chế *thread bị kẹt chỉ để chờ I/O*.

WebFlux **không bắt buộc Netty**: có thể chạy trên Tomcat/Jetty hỗ trợ non-blocking I/O thông qua adapter. Ngược lại, chạy WebFlux trên Tomcat cũng không làm cho nó trở thành Spring MVC.

## 5. Hai ví dụ Java 17+ có thể chạy để quan sát khác biệt

Hai chương trình dưới đây đặt ở **hai ứng dụng Spring Boot độc lập**, mỗi ứng dụng chỉ chọn starter web phù hợp qua Spring Initializr (MVC/Web cho ví dụ 1, Reactive Web/WebFlux cho ví dụ 2). Đảm bảo không chạy cùng lúc trên cổng 8080. Tên dependency có thể khác giữa các phiên bản Spring Boot; giữ đúng loại web stack cho từng dự án.

### 5.1. Spring MVC: mô phỏng lời gọi blocking

Tạo `src/main/java/example/MvcDemo.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcDemo {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemo.class, args);
    }
}

@RestController
class MvcController {
    @GetMapping("/compare")
    String compare() throws InterruptedException {
        Thread.sleep(250); // Mô phỏng chờ I/O blocking, không dùng để xử lý thật
        return "OK";
    }
}
```

Trong controller đồng bộ này, `Thread.sleep(250)` giữ worker thread không làm công việc hữu ích trong khoảng chờ. Trong ứng dụng thực, điểm chờ có thể là truy vấn JDBC hoặc HTTP client blocking.

### 5.2. Spring WebFlux: mô phỏng chờ không giữ event-loop thread

Tạo `src/main/java/example/WebFluxDemo.java`:

```java
package example;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxDemo {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxDemo.class, args);
    }
}

@RestController
class WebFluxController {
    @GetMapping("/compare")
    Mono<String> compare() {
        return Mono.delay(Duration.ofMillis(250))
                   .map(ignored -> "OK");
    }
}
```

`Mono.delay` dùng bộ hẹn giờ Reactor, không gọi `sleep()` trên event loop. Spring subscribe vào kết quả khi phục vụ request; sau thời gian hẹn, pipeline phát giá trị `"OK"`.

Với dự án Spring Boot dùng Gradle wrapper, chạy từng dự án bằng:

```bash
./gradlew bootRun
```

Từ terminal khác:

```bash
curl -i http://localhost:8080/compare
```

Cả hai ví dụ trả HTTP 200 và body `OK` nếu chạy thành công. Header, thread name và thời gian chính xác phụ thuộc môi trường. **Hai đoạn này chỉ minh họa cách chờ**: `Thread.sleep` và `Mono.delay` không phải hai phương án truy cập cùng một cơ sở dữ liệu, do đó không được lấy chúng làm benchmark MVC so với WebFlux.

## 6. Khi có nhiều request chờ I/O đồng thời

Giả sử một dịch vụ nhận khoảng 400 request/giây, mỗi request chờ upstream trung bình 0,5 giây. Theo định luật Little, số request *đang ở trong hệ thống* do riêng phần chờ này vào khoảng `400 x 0,5 = 200` trong trạng thái ổn định (ước lượng, chưa tính các hàng đợi khác).

- **MVC đồng bộ**: nếu mỗi request đang chờ giữ một worker thread, mức tải có thể đòi hỏi xấp xỉ 200 worker thread để cùng chờ, cùng với giới hạn pool và tài nguyên của upstream. Khi hết worker, request mới phải chờ hoặc bị từ chối tùy cấu hình.
- **WebFlux non-blocking từ đầu đến cuối**: khoảng 200 thao tác I/O đang chờ không nhất thiết cần 200 event-loop threads. Tác vụ được đăng ký và tiếp tục khi có sự kiện, nhưng connection pool, giới hạn upstream, memory, timeout và CPU vẫn quyết định sức chịu tải.
- **Nếu WebFlux gọi JDBC blocking trực tiếp trên event loop**: lợi thế trên có thể biến mất; một lời gọi chậm có thể làm nhiều request khác trên cùng event-loop thread bị trì hoãn.
- **Nếu MVC dùng Servlet async hoặc virtual threads**: số platform worker bị giữ khi chờ có thể giảm đáng kể. Vì vậy cần so sánh các cấu hình thực tế thay vì “MVC luôn N threads, WebFlux luôn 1 thread”.

Từ mô hình xử lý **không suy ra** rằng WebFlux có latency thấp hơn trong mọi trường hợp. Với nghiệp vụ CPU-bound hoặc lưu trữ blocking, sự khác biệt có thể nhỏ, bằng không hoặc WebFlux còn tốn chi phí vận hành hơn vì pipeline phức tạp.

## 7. Reactor, backpressure và ý nghĩa thực tế

`Mono<T>` là một publisher phát tối đa một giá trị; `Flux<T>` phát nhiều giá trị. Reactive Streams cho phép subscriber yêu cầu số phần tử (`request(n)`) và publisher phối hợp điều tiết tốc độ để không phát vô hạn vượt nhu cầu tại ranh giới hỗ trợ giao thức. Đây là một ưu điểm quan trọng khi xử lý chuỗi dữ liệu lớn hoặc stream.

```java
Flux<Integer> batch = Flux.range(1, 10)
                          .map(number -> number * 2)
                          .limitRate(2);
```

Đây là **đoạn code minh họa**, không phải chương trình Spring Boot độc lập. `limitRate(2)` điều chỉnh cách downstream yêu cầu phần tử từ upstream; nó **không phải** giới hạn 2 request HTTP/giây và không tự biến mọi API hoặc hệ thống ngoài thành non-blocking.

Khi stream HTTP, hiệu quả end-to-end còn phụ thuộc codec, buffer, loại response, HTTP transport, cách downstream tiêu thụ và upstream có hỗ trợ backpressure hay không. Đừng đồng nhất backpressure với rate limiting, cân bằng tải hay timeout.

### Ví dụ WebFlux truyền Server-Sent Events (SSE)

Đặt phương thức này trong một WebFlux `@RestController`:

```java
@GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> ticks() {
    return Flux.interval(Duration.ofSeconds(1))
               .take(3)
               .map(index -> "tick-" + index);
}
```

Cần import `java.time.Duration`, `reactor.core.publisher.Flux` và `org.springframework.http.MediaType`. Client dùng `curl -N http://localhost:8080/ticks` sẽ lần lượt thấy payload mang ý nghĩa `tick-0`, `tick-1`, `tick-2`, rồi stream hoàn tất; chi tiết đóng gói SSE phụ thuộc bộ mã hóa. MVC **cũng hỗ trợ SSE** qua `SseEmitter` hoặc reactive return types, vì vậy SSE tự nó không buộc phải chuyển sang WebFlux.

## 8. Tích hợp service: nguồn dữ liệu quyết định hiệu quả

Giả sử API tổng hợp thông tin từ hai dịch vụ HTTP. Khi cả hai upstream hỗ trợ non-blocking, `WebClient` có thể ghép các tác vụ mà không cần thread đứng chờ từng lời gọi:

```java
// Đoạn minh họa trong một service đã được inject WebClient client.
public Mono<Map<String, String>> loadSummary(String id) {
    Mono<String> profile = client.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(String.class);

    Mono<String> account = client.get()
            .uri("/accounts/{id}", id)
            .retrieve()
            .bodyToMono(String.class);

    return Mono.zip(profile, account)
            .map(pair -> Map.of(
                    "profile", pair.getT1(),
                    "account", pair.getT2()
            ));
}
```

Cần import `java.util.Map` và `reactor.core.publisher.Mono`; hai URI là đường dẫn của upstream mà ứng dụng phải cấu hình. Đây là snippet tích hợp, **không tự chạy** nếu chưa có `WebClient client` và các dịch vụ thật. `Mono.zip` phối hợp hai nguồn; thông thường có thể đăng ký cả hai cuộc gọi mà không đợi cuộc thứ nhất xong mới bắt đầu cuộc thứ hai. Cần xử lý timeout, status lỗi và `Mono.empty()` theo yêu cầu nghiệp vụ.

**Quan trọng:** `WebClient` không phải công cụ riêng của WebFlux server. Một ứng dụng **Spring MVC hoàn toàn có thể dùng WebClient**, và MVC controller có thể trả một reactive type để Spring thích ứng với Servlet async. Điều này cho phép cải thiện các đường gọi I/O mà không nhất thiết thay cả HTTP stack.

### Điều gì xảy ra với JDBC/JPA trong WebFlux?

JDBC/JPA là API blocking. Nếu controller WebFlux gọi repository JDBC trực tiếp trên event loop, thread vẫn bị giữ trong lúc DB chờ. Với thư viện legacy không thể thay ngay, Reactor hỗ trợ cách ly qua scheduler dành cho blocking:

```java
Mono<String> legacyCall = Mono.fromCallable(() -> {
    Thread.sleep(100); // Chỉ mô phỏng một API blocking
    return "legacy-result";
}).subscribeOn(Schedulers.boundedElastic());
```

Cần import `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers`. `fromCallable` trì hoãn việc gọi đến lúc subscribe; `subscribeOn(boundedElastic())` đưa phần blocking sang scheduler thích hợp. **Nó không biến I/O blocking thành non-blocking**: một thread trong scheduler vẫn chờ, scheduler có giới hạn tài nguyên, và cần kiểm soát timeout, connection pool, số tác vụ chờ.

Nếu phần lớn nghiệp vụ dựa vào JPA/JDBC, MVC thường là lựa chọn đơn giản, tự nhiên. Nếu muốn pipeline WebFlux thực sự non-blocking xuyên suốt đến database, cần cân nhắc driver và transaction reactive (ví dụ R2DBC), sự tương thích nghiệp vụ và cách quản lý transaction.

## 9. Xử lý lỗi, hủy yêu cầu, context và giao dịch

### Lỗi và timeout

- **MVC:** exception đồng bộ đi qua cơ chế `@ExceptionHandler`/`@ControllerAdvice`; async MVC có cơ chế hoàn tất hoặc lỗi, timeout trên `DeferredResult`, `WebAsyncTask` và executor.
- **WebFlux:** lỗi được phát dưới dạng tín hiệu `onError`; dùng `onErrorResume`, `onErrorMap`, `timeout` và xử lý lỗi HTTP thích hợp. `Mono.empty()` biểu thị hoàn tất không có giá trị; nếu nghiệp vụ yêu cầu HTTP 404 thì phải ánh xạ rõ, đừng mặc nhiên xem empty đồng nghĩa với 404.
- **Cả hai:** cần đặt timeout hợp lý cho upstream/database, phân loại lỗi, retry có giới hạn và chỉ retry thao tác an toàn. Khi client ngắt kết nối, một reactive subscription có thể nhận tín hiệu cancel, nhưng việc upstream có thực sự dừng hay không phụ thuộc thư viện và tác vụ.

Ví dụ xử lý timeout bằng Reactor:

```java
Mono<String> guarded = remoteCall
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                       error -> Mono.just("fallback"));
```

Đây là snippet: `remoteCall` là một `Mono<String>` phải có sẵn; cần import `java.time.Duration` và `java.util.concurrent.TimeoutException`. Fallback chỉ phù hợp nếu nghiệp vụ cho phép; không nên che mất lỗi ở các tác vụ tài chính hoặc cập nhật dữ liệu quan trọng.

### Context, security, transaction

- Mã MVC đồng bộ thường dễ theo dấu bằng stack trace và `ThreadLocal` trong cùng luồng; với MVC async hoặc virtual threads, vẫn cần lưu ý propagation khi chuyển ngữ cảnh.
- WebFlux không bảo đảm một request luôn chạy cùng thread; tránh lưu request context vào `ThreadLocal` tùy tiện. Dùng Reactor `Context` và các cơ chế propagation do Spring/Micrometer cung cấp khi thích hợp.
- MVC thường dùng servlet `Filter`/`HandlerInterceptor` và cấu hình bảo mật servlet; WebFlux thường dùng `WebFilter` và các API Spring Security reactive. Không bê nguyên cấu hình servlet filter sang WebFlux.
- Giao dịch dùng `PlatformTransactionManager` với JDBC/JPA và `ReactiveTransactionManager` với reactive data access có ngữ nghĩa context khác nhau. Một reactive pipeline không tự làm cho `@Transactional` theo kiểu blocking trở thành reactive transaction.

## 10. Khả năng mở rộng, virtual threads và việc đo lường

**Throughput** là số request xử lý được trong một khoảng thời gian; **latency** là thời gian mỗi request; **concurrency** là số công việc đang hoạt động/chờ; **backpressure** là điều tiết nhu cầu trong dòng dữ liệu. Chúng liên quan nhưng không đồng nghĩa.

Từ Java 21, virtual threads cho phép viết mã blocking theo phong cách imperative với chi phí thread thường thấp hơn platform thread trong nhiều trường hợp chờ I/O. Spring Boot có hỗ trợ bật virtual threads cho các executor phù hợp qua cấu hình như `spring.threads.virtual.enabled=true` (khi ứng dụng/JDK đáp ứng yêu cầu). Đây là một lựa chọn đáng so sánh trong hệ MVC. Virtual threads vẫn là mô hình blocking theo góc nhìn mã nguồn, không tự mang lại Reactive Streams/backpressure và không loại bỏ giới hạn database connection pool hay upstream.

Khi đánh giá hai mô hình, hãy kiểm thử **cùng nghiệp vụ, cùng dữ liệu, cùng upstream và giới hạn tài nguyên**, theo dõi:

1. Requests/giây, p50/p95/p99 latency, timeout và tỷ lệ lỗi.
2. CPU, heap, GC, số platform/virtual threads đang hoạt động, độ sâu queue.
3. Connection pool HTTP và database, số kết nối đang chờ, tải thực trên upstream.
4. Tác vụ blocking xuất hiện trong event loop, thời gian serialize/deserialize, kích thước response.
5. Tính ổn định dưới burst load, xử lý client ngắt kết nối, mức độ dễ debug và chi phí bảo trì.

Ví dụ dùng `curl` chỉ để xem hành vi một request; muốn kết luận hiệu năng cần load test có phương pháp, warm-up, giới hạn concurrency rõ ràng và kết quả đo tái lập được.

## 11. Cách lựa chọn trong dự án

**Thường chọn MVC khi:**

- Ứng dụng CRUD/REST với JDBC/JPA, nhiều API imperative hoặc hệ thống MVC hiện hữu vận hành ổn.
- Đội ngũ cần ưu tiên luồng điều khiển trực tiếp, thư viện truyền thống và khả năng bảo trì.
- Có nhu cầu xử lý async riêng lẻ: có thể dùng Servlet async, `WebClient` hoặc cân nhắc virtual threads trước khi thay đổi kiến trúc lớn.

**Cân nhắc WebFlux khi:**

- Hệ thống thực hiện rất nhiều I/O non-blocking đồng thời, giữ nhiều kết nối đang chờ hoặc trả streaming liên tục.
- Các thành phần đầu cuối (HTTP client, database/queue) có driver reactive phù hợp và đội ngũ có kinh nghiệm Reactor.
- Cần khai thác việc ghép nhiều publisher, backpressure và xử lý luồng dữ liệu bằng các operator.

**Tình huống lai:** một hệ thống có thể gồm service MVC với JDBC/JPA và service WebFlux thực hiện aggregation/streaming. Một MVC controller cũng có thể dùng `WebClient`. Không bắt buộc mọi service dùng cùng mô hình.

### Câu hỏi quyết định thực tế

1. Phần lớn thời gian request nằm ở **CPU**, **blocking JDBC/JPA**, hay **I/O non-blocking**?
2. Các dependency quan trọng có hỗ trợ reactive thật không, hay chỉ được bọc ngoài bằng `Mono`?
3. Số request/connection chờ đồng thời có đang là nút thắt được chứng minh bằng số liệu không?
4. Có thể giải quyết bằng cấu hình thread/connection pool, MVC async, `WebClient` hoặc virtual threads với ít thay đổi hơn không?
5. Đội ngũ có đủ công cụ kiểm thử, tracing, debug và theo dõi reactive flow khi có sự cố không?

Quyết định nên dựa trên tải thực tế và giới hạn hệ thống, không dựa vào nhãn “nhanh hơn”.

## 12. Những ngộ nhận và lỗi thường gặp

| Nhận định/lỗi | Cách hiểu đúng |
|---|---|
| “WebFlux luôn nhanh hơn Spring MVC” | Không có bảo đảm. Lợi ích phụ thuộc mẫu tải, tỷ lệ chờ I/O, driver và năng lực đội ngũ. |
| “Spring MVC không làm async hoặc streaming được” | MVC có Servlet async, `DeferredResult`, `Callable`, `SseEmitter` và có thể thích ứng reactive return types. |
| “Chỉ cần đổi return type từ `T` sang `Mono<T>` là non-blocking” | Nếu bên trong gọi API blocking trên event loop, pipeline vẫn có điểm blocking. |
| “`Mono` luôn chạy trên thread riêng” | Publisher không tự tạo thread riêng. Scheduler, upstream và runtime quyết định thread thực thi. |
| “Gọi `.block()` trong WebFlux controller cho dễ lấy dữ liệu” | Có thể chặn event loop và gây cạn khả năng phục vụ; hãy trả `Mono`/`Flux` cho Spring xử lý. |
| “Gọi `.subscribe()` trong controller để chạy pipeline” | Có nguy cơ sinh tác vụ tách khỏi vòng đời HTTP, mất xử lý lỗi/cancel; thường trả publisher trực tiếp. |
| “WebFlux buộc phải chạy Netty” | Có thể dùng non-blocking adapter trên các máy chủ Servlet tương thích. |
| “WebFlux thay thế hoàn toàn MVC” | Hai mô hình có thể tồn tại song song ở các ứng dụng và có thể dùng chung một số công cụ. |
| “Backpressure chính là giới hạn request/giây” | Backpressure kiểm soát nhu cầu dữ liệu trong stream; rate limiting xử lý mục tiêu khác. |
| “Virtual threads làm WebFlux không còn ý nghĩa” | Virtual threads giảm chi phí luồng khi blocking trong nhiều trường hợp; reactive vẫn hữu ích cho các đường dữ liệu non-blocking và streaming. |

**Ghi nhớ:** Spring MVC tối ưu cho mô hình xử lý imperative có thể blocking; Spring WebFlux xây dựng pipeline reactive non-blocking từ đầu. Hãy xem **mã và driver bên dưới controller thực sự chờ I/O theo cách nào**, vì đó mới là điều quyết định đặc tính sử dụng thread.

## Tài liệu chính thức

- Spring Framework, **Spring WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework, **WebFlux Overview – Applicability & Concurrency Model**: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework, **MVC Asynchronous Requests**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework, **WebClient Synchronous Use**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Boot, **Reactive Web Applications**: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot, **Task Execution and Scheduling / Virtual Threads**: https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
- Reactor Core, **How Do I Wrap a Synchronous, Blocking Call?**: https://projectreactor.io/docs/core/release/reference/faq.html