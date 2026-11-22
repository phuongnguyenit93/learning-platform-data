# Lựa chọn mô hình web theo đặc điểm tác vụ và thư viện phụ thuộc

Trong Spring Boot, quyết định dùng **Spring MVC (Servlet)** hay **Spring WebFlux (reactive)** phải xuất phát từ loại công việc mà request thực hiện, cách các thư viện phụ thuộc xử lý I/O, mức đồng thời thực tế và năng lực vận hành của đội ngũ. Chỉ nhìn số lượng request, thấy chữ “async”, hoặc muốn “hiệu năng cao” là chưa đủ để chọn WebFlux.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt luồng xử lý HTTP trên Servlet/MVC với luồng non-blocking trên WebFlux, kể cả trường hợp MVC xử lý bất đồng bộ.
- Kiểm kê các lời gọi **blocking** và **non-blocking** ở database, HTTP client, SDK, file I/O trước khi chọn web stack.
- Chọn mô hình phù hợp cho CRUD với JPA, API gateway gọi nhiều dịch vụ, streaming/SSE, công việc CPU nặng và hệ thống pha trộn.
- Giải thích chi phí chuyển đổi, phương án trung gian và cách đo kiểm thay vì đưa ra kết luận từ cảm tính.

## 2. Hai mô hình và đặc điểm runtime

### 2.1. Spring MVC / Servlet

- Đầu vào HTTP thường đi qua Servlet container (ví dụ Tomcat/Jetty) và `DispatcherServlet`; controller có thể trả giá trị thông thường như `String`, DTO, `ResponseEntity<T>`.
- Lập trình imperative thuận tiện khi dùng JPA/Hibernate, JDBC, các HTTP client đồng bộ và SDK có hàm chờ kết quả. Thread xử lý có thể bị giữ khi chờ I/O; thread pool và kết nối đến hệ thống phụ thuộc phải được giới hạn hợp lý.
- MVC **không đồng nghĩa với “không hỗ trợ async”**: `Callable`, `DeferredResult`, `CompletableFuture`, `SseEmitter`, `StreamingResponseBody` và một số reactive return type được hỗ trợ. Servlet async có thể nhả request thread trong lúc chờ nhưng việc ghi dữ liệu ra response theo Servlet vẫn khác với mô hình I/O non-blocking của WebFlux.
- Java 21+ có thể kết hợp **virtual threads** trong những cấu hình Spring Boot hỗ trợ (`spring.threads.virtual.enabled=true`). Đây là phương án đáng thử khi nhiều tác vụ chờ I/O đồng bộ, nhưng không biến JDBC/SDK thành API non-blocking và không giải quyết giới hạn pool kết nối hay xử lý CPU.

### 2.2. Spring WebFlux / Reactive

- HTTP được xử lý bởi tầng web reactive (`DispatcherHandler`); controller có thể trả `Mono<T>` (0 hoặc 1 kết quả) hoặc `Flux<T>` (nhiều kết quả). WebFlux dựa trên I/O non-blocking và Reactive Streams, có cơ chế điều tiết nhu cầu nhận dữ liệu (**backpressure**) khi các thành phần liên quan hỗ trợ.
- Mô hình event loop thường dùng ít thread xử lý sự kiện; để hưởng lợi, chuỗi xử lý phải tránh chặn các thread đó. `WebClient`, driver R2DBC phù hợp và các API reactive khác có thể kết hợp thành pipeline không chặn thread trong lúc đợi mạng.
- WebFlux mặc định thường chạy với Reactor Netty trong ứng dụng Spring Boot dùng starter WebFlux; nó **không bắt buộc phải chạy Netty** vì cũng có thể chạy qua adapter của servlet container tương thích. Tên server không tự quyết định code của ứng dụng có non-blocking hay không.
- Reactor không làm một lời gọi blocking trở thành non-blocking chỉ bằng cách bọc trong `Mono.just(...)`. Nếu gọi JDBC, `Thread.sleep`, `Future.get` hoặc `.block()` trên event loop, bạn vẫn đang chặn thread.

### 2.3. Minh họa khác nhau tại điểm chờ I/O

```text
MVC (đường xử lý đồng bộ thường gặp):
HTTP → Servlet thread → Controller → JDBC/SDK blocking → chờ I/O → Response

WebFlux (pipeline non-blocking thực sự):
HTTP → Event loop → Controller → WebClient/R2DBC non-blocking
                         ↳ đăng ký callback, thread rảnh xử lý việc khác
                         ↳ có kết quả → tiếp tục pipeline → Response
```

Đây là sơ đồ nguyên lý. Không được suy luận rằng mọi request MVC luôn chiếm đúng một thread trong toàn bộ vòng đời, hay WebFlux không bao giờ dùng thread khác: async MVC, executor, scheduler, virtual threads và các điểm chuyển luồng làm hành vi thực tế đa dạng hơn.

## 3. Yếu tố quyết định: tác vụ và toàn bộ chuỗi phụ thuộc

| Đặc điểm tác vụ / thư viện | Gợi ý ban đầu | Lý do và điều kiện |
| --- | --- | --- |
| CRUD với Spring Data JPA/Hibernate hoặc `JdbcTemplate` | **MVC** | JDBC/JPA có I/O blocking; MVC phù hợp với mô hình giao dịch imperative và thư viện hiện có. |
| SDK thanh toán, thư viện LDAP, client HTTP đồng bộ hoặc driver bên thứ ba chỉ có hàm blocking | **MVC** hoặc tách adapter riêng | WebFlux không tránh được chờ I/O của thư viện đó. |
| Dịch vụ proxy/aggregation gọi nhiều API HTTP bằng `WebClient`, không có phụ thuộc blocking trên đường xử lý chính | **Cân nhắc WebFlux** | Nhiều request cùng chờ mạng có thể hưởng lợi từ mô hình non-blocking sau khi đo kiểm. |
| Ứng dụng dùng R2DBC và các nguồn dữ liệu/network client reactive xuyên suốt | **Cân nhắc WebFlux** | Tính non-blocking có thể đi từ HTTP đến database; phải kiểm tra driver và cách quản lý transaction thực tế. |
| HTML/REST phổ thông, lưu lượng vừa phải, đội ngũ quen Java imperative | **MVC** | Đơn giản hơn cho phát triển, debug, tracing và tích hợp thư viện truyền thống. |
| SSE hoặc streaming dài hạn với rất nhiều kết nối, mọi phần trong pipeline hỗ trợ non-blocking | **Cân nhắc WebFlux** | Giảm thread phải chờ kết nối khi kiến trúc thực sự duy trì non-blocking và kiểm soát tải tốt. |
| SSE/streaming ít kết nối hoặc hệ thống hiện đã dùng MVC | **MVC vẫn khả thi** | `SseEmitter`/`StreamingResponseBody` có thể đáp ứng; không phải cứ streaming là buộc chọn WebFlux. |
| Mã hóa ảnh, tính toán báo cáo, xử lý CPU nặng | **Không mô hình nào tự giải quyết** | Dùng worker pool/queue thích hợp, giới hạn concurrency và CPU; không chạy tác vụ CPU nặng trên event loop. |
| Hệ thống trộn JPA blocking với vài lời gọi HTTP cần bất đồng bộ | **Thường giữ MVC + WebClient** | Thêm client reactive có thể hữu ích mà chưa cần đổi server stack hoặc refactor persistence. |

**Nguyên tắc quan trọng:** Quyết định dựa trên *đường đi thực tế của request*. Chỉ cần một thư viện blocking quan trọng nằm trên đường đi, mô hình WebFlux sẽ phải có chiến lược cô lập blocking, và lợi ích cần được kiểm chứng.

## 4. Cách kiểm kê phụ thuộc trước khi chọn

Với một request đại diện, vẽ đường đi từ controller đến response rồi lập bảng cho từng điểm I/O:

1. **Database:** Spring Data JPA/JDBC/JdbcTemplate là blocking; R2DBC dùng API reactive, nhưng driver, nghiệp vụ và transaction phải cùng tương thích.
2. **HTTP outbound:** `RestTemplate`/`RestClient` thông thường là đồng bộ; `WebClient` có API reactive. Gọi `WebClient(...).block()` thì phía gọi vẫn bị chặn.
3. **SDK bên thứ ba:** đọc tài liệu API và hành vi thật của SDK; đừng coi tên `Async` là bằng chứng non-blocking nếu bên trong vẫn chờ hoặc dùng pool giới hạn.
4. **File, object storage, message broker và cache:** kiểm tra từng driver và thao tác. “Có callback” và “không chặn event loop” cần được xác nhận cụ thể; không gán nhãn non-blocking chỉ từ tên công nghệ.
5. **Framework integration:** kiểm tra Servlet filter, Spring Security kiểu `SecurityFilterChain`, session, interceptor, exception handler và các thư viện chỉ hỗ trợ Servlet. WebFlux dùng các tích hợp reactive tương ứng, ví dụ `SecurityWebFilterChain`.
6. **Hạ tầng và pool:** đo pool HTTP/database, timeout, hàng đợi, rate limit, khả năng retry, giới hạn CPU/memory. WebFlux không tăng số kết nối database mà pool có thể phục vụ.

Khi một dependency chưa rõ hành vi, ghi **“chưa xác minh”** trong bảng kỹ thuật thay vì mặc định non-blocking. Một kiến trúc reactive end-to-end chỉ hợp lý khi các điểm phụ thuộc trọng yếu thực sự hỗ trợ nó.

## 5. Quy trình lựa chọn thực tế

```text
Bắt đầu từ request quan trọng nhất
  |
  +-- Phụ thuộc chính là JPA/JDBC/SDK blocking? -- Có --> Ưu tiên MVC
  |                                                   |
  |                                                   +--> Cần async HTTP?
  |                                                        Dùng WebClient/Servlet async
  |
  +-- Không --> Chủ yếu chờ network I/O đồng thời cao?
                  |
                  +-- Không --> MVC là lựa chọn mặc định dễ duy trì
                  |
                  +-- Có --> Client, DB, cache, auth đều phù hợp reactive?
                                |
                                +-- Không --> Giữ MVC hoặc cô lập phần blocking;
                                |             đo lại lợi ích trước khi đổi stack
                                |
                                +-- Có --> Thử WebFlux bằng tải đại diện,
                                              đo p95/p99, tài nguyên, độ phức tạp
```

Một bước lựa chọn có thể ghi thành **ADR (Architecture Decision Record)** ngắn: tác vụ chính, thư viện blocking, mục tiêu tải, mô hình được chọn, phương án thay thế và số đo xác nhận. Khi chưa có lý do hoặc số đo rõ ràng, MVC là điểm xuất phát hợp lý cho đa số ứng dụng nghiệp vụ imperative; không cần chuyển ứng dụng MVC đang đáp ứng tốt chỉ vì WebFlux mới hơn.

## 6. Khai báo starter: đừng để dependency chọn hộ runtime

Trong Gradle, các ví dụ sau giả sử bạn đã tạo dự án Spring Boot tương ứng bằng Spring Initializr. Chỉ thêm starter của web stack định dùng cho *mỗi dự án*, rồi quản lý phiên bản qua Spring Boot plugin/BOM:

```groovy
// Spring Boot 3.x: ứng dụng MVC
implementation 'org.springframework.boot:spring-boot-starter-web'

// Spring Boot 4.x: starter MVC chuyên biệt
implementation 'org.springframework.boot:spring-boot-starter-webmvc'

// MVC hoặc WebFlux khi cần reactive HTTP client (tùy phiên bản Boot):
// kiểm tra starter WebClient riêng của bản Boot, hoặc webflux dependency.
```

```groovy
// Spring Boot 3.x/4.x: ứng dụng reactive WebFlux
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Các dòng trên là **lựa chọn thay thế theo phiên bản và mô hình**, không phải danh sách để thêm tất cả vào cùng một ứng dụng. Với Spring Boot 3.x, nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng xuất hiện thì Boot thông thường tự cấu hình **Spring MVC**. Điều đó cho phép dùng `WebClient` trong MVC; đừng suy luận rằng có `Mono` hoặc starter WebFlux trong dependency tree thì server chắc chắn là WebFlux. Nếu cố tình chọn kiểu web application reactive, phải cấu hình rõ và kiểm tra tương thích toàn bộ ứng dụng.

Chú ý: starter và nhóm module có thể đổi tên giữa các major version. Luôn đối chiếu starter với **phiên bản Boot đang dùng**; riêng Spring Boot 4 giới thiệu `spring-boot-starter-webmvc` và đánh dấu starter `spring-boot-starter-web` là đường cũ.

## 7. Hai ví dụ Java 17+ có thể chạy độc lập

Hai ví dụ dưới đây là **hai dự án Spring Boot riêng biệt**, cùng dùng đường dẫn `/demo`, chạy từng dự án trên cổng 8080. Chúng chỉ minh họa cách controller thể hiện thao tác chờ; `sleep`/timer là mô phỏng, không đại diện cho benchmark I/O thật.

### 7.1. Dự án A: MVC và lời gọi blocking

Tạo Spring Boot 3.x với dependency **Spring Web** (hoặc Spring Boot 4.x với **Spring Web MVC**), đặt file `src/main/java/demo/MvcApplication.java`:

```java
package demo;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }

    @GetMapping("/demo")
    public String demo() throws InterruptedException {
        TimeUnit.MILLISECONDS.sleep(80); // Mô phỏng SDK/JDBC đồng bộ đang chờ
        return "mvc-ok";
    }
}
```

Ở đây thread thực thi phương thức phải chờ khoảng 80 ms. Khi thay bằng JPA/JDBC hoặc SDK đồng bộ thật, hãy cấu hình connection pool, timeout và giới hạn lưu lượng; không dùng `sleep` trong production.

### 7.2. Dự án B: WebFlux và tín hiệu bất đồng bộ

Tạo dự án Spring Boot khác chỉ có starter **Spring Reactive Web / WebFlux**, đặt file `src/main/java/demo/WebFluxApplication.java`:

```java
package demo;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class WebFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxApplication.class, args);
    }

    @GetMapping("/demo")
    public Mono<String> demo() {
        return Mono.delay(Duration.ofMillis(80))
                .map(ignored -> "webflux-ok");
    }
}
```

`Mono.delay` lập lịch phát tín hiệu sau khoảng 80 ms; không gọi `Thread.sleep` trên event loop. Trong ứng dụng thực, thay tín hiệu timer bằng `WebClient`, R2DBC hoặc API reactive phù hợp. Đừng dùng phép so sánh “80 ms” trên hai chương trình nhỏ để kết luận mô hình nào nhanh hơn.

Ở thư mục **mỗi dự án**, chạy một trong các lệnh:

```bash
./gradlew bootRun
curl -s http://localhost:8080/demo
```

Trên Windows PowerShell, dùng `./gradlew.bat bootRun` (hoặc `.\gradlew.bat bootRun`) và `curl.exe -s http://localhost:8080/demo`. Sau khi server khởi động, stdout HTTP body của dự án A là `mvc-ok`, của dự án B là `webflux-ok`. Dừng dự án A trước khi chạy B nếu cùng dùng cổng 8080. Với cấu hình Boot 3.x, Java 17+ phù hợp; kiểm tra yêu cầu Java của major version và bộ starter bạn chọn.

## 8. Khi ứng dụng có cả reactive lẫn blocking

### 8.1. MVC vẫn dùng được WebClient

Một controller MVC có thể trả `Mono<String>` lấy từ `WebClient`; Spring MVC thích ứng với reactive return type cho xử lý response bất đồng bộ. Ví dụ **đoạn mã tích hợp**, giả sử đã inject một `WebClient` trỏ đến dịch vụ có endpoint `/status`:

```java
@GetMapping("/remote-status")
public Mono<String> remoteStatus() {
    return webClient.get()
            .uri("/status")
            .retrieve()
            .bodyToMono(String.class);
}
```

Đoạn trên là **snippet trong controller**, không phải chương trình Java độc lập; cần bean `webClient`, dịch vụ đích và dependency tương ứng. Tránh thêm `.block()` nếu mục tiêu là trả kết quả bất đồng bộ. Cách này không tự chuyển toàn bộ MVC server sang WebFlux.

### 8.2. WebFlux buộc phải gọi thư viện blocking

Nếu đang ở WebFlux nhưng phải gọi API legacy blocking, cô lập lời gọi trên scheduler dành cho blocking, ví dụ **snippet** bên trong service:

```java
Mono<LegacyResult> result = Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

Cần import `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers`; `LegacyResult`/`legacyClient` là kiểu và đối tượng giả định của dự án. `boundedElastic` tránh giữ event loop khi chờ nhưng **vẫn tiêu thụ thread và tài nguyên**, vẫn cần timeout/giới hạn tải; nó không làm client legacy non-blocking. Dùng `Mono.fromCallable(() -> legacyClient.fetch())` để lời gọi chỉ xảy ra khi subscribe, thay vì `Mono.just(legacyClient.fetch())` vốn thực hiện blocking ngay lúc tạo publisher.

Nếu phần lớn luồng nghiệp vụ đều phải chuyển sang `boundedElastic`, nên xem lại lựa chọn WebFlux: MVC có thể rõ ràng và dễ bảo trì hơn.

### 8.3. Virtual threads không thay thế việc kiểm kê phụ thuộc

Với Java 21+ và Spring Boot có hỗ trợ, cấu hình:

```properties
spring.threads.virtual.enabled=true
```

Virtual threads có thể cải thiện cách chịu tải khi chờ I/O trên code imperative; chúng không tự tăng tốc CPU, giảm latency của database, tăng số connection, hoặc chuyển API blocking sang reactive. Cần benchmark cả pinning/tracing, connection pool và concurrency limits trước khi chọn, đồng thời kiểm tra chỗ Boot thực sự sử dụng virtual-thread executor theo version.

## 9. Bốn tình huống chọn mô hình

**Tình huống A — quản lý đơn hàng.** Controller tạo đơn, gọi JPA/Hibernate, dùng transaction đồng bộ, gọi SDK thanh toán blocking. Chọn **MVC**. Tối ưu database queries, connection pool, timeout, idempotency và cô lập gọi mạng có độ trễ trước khi nghĩ tới đổi stack.

**Tình huống B — API gateway tổng hợp dữ liệu.** Một request đồng thời gọi 5 API bằng `WebClient`, không truy cập JDBC và các adapter đều non-blocking; có hàng nghìn kết nối cùng chờ mạng. **WebFlux đáng thử** nếu đội ngũ đã kiểm soát được reactive error handling, timeout, cancellation, backpressure và quan sát hệ thống. MVC với async client cũng là baseline để so sánh.

**Tình huống C — SSE thông báo tác vụ.** Ứng dụng chỉ có vài trăm kết nối và đang chạy MVC ổn định: thử `SseEmitter` trước. Hệ thống có rất nhiều streaming connections và nguồn phát reactive: cân nhắc WebFlux. Cần xét proxy timeout, keepalive, khả năng client ngắt kết nối, bounded buffering và phát tín hiệu chậm.

**Tình huống D — tạo báo cáo nặng CPU.** Xuất báo cáo lớn, mã hóa file và đọc dữ liệu nhiều phút: không dùng WebFlux để mong giảm CPU. Đưa công việc sang background job/queue có giới hạn tài nguyên và API trả task ID; có thể dùng MVC làm HTTP frontend hoặc WebFlux nếu lý do khác đòi hỏi.

## 10. Đo lường để xác nhận quyết định

Cùng một nghiệp vụ và bộ dữ liệu, kiểm thử **warm-up**, tải bình thường, burst và trạng thái phụ thuộc chậm/lỗi. Ghi:

- **Khả năng đáp ứng:** request/s thành công, p50/p95/p99 latency, timeout và error rate; so sánh ở cùng mục tiêu chức năng.
- **Tài nguyên:** CPU, heap/GC, số thread, event loop utilization/blocking, số request đang xử lý và queue length.
- **Nút thắt phụ thuộc:** database pool active/waiting, HTTP client pool, tỉ lệ connection timeout, retry amplification, rate limit.
- **Khả năng vận hành:** độ rõ của stack trace, context propagation trong logs/traces, test transaction, hành vi cancellation, learning cost và chất lượng thư viện tích hợp.

Ví dụ, nếu throughput bị chặn bởi tối đa 20 database connections hoặc một SDK chỉ cho phép 50 request/s, đổi sang WebFlux **không tự loại bỏ nút thắt đó**. Mục tiêu là đạt SLA với độ phức tạp chấp nhận được, không phải cố giảm thread bằng mọi giá.

## 11. Lỗi chọn stack và cách tránh

1. **“WebFlux luôn nhanh hơn MVC.”** Sai: lợi ích phụ thuộc workload, tỷ lệ I/O chờ, thư viện và cấu hình. Đo bằng tải đại diện.
2. **“Trả `Mono` là đã non-blocking.”** Sai nếu trong `map`, `flatMap` hoặc lúc tạo publisher vẫn gọi hàm blocking.
3. **“Phải dùng WebFlux mới có WebClient/async/SSE.”** Sai: MVC có hỗ trợ async và streaming; `WebClient` cũng dùng được cùng MVC.
4. **“JPA chạy tốt trên event loop vì có reactive wrapper.”** Sai: JPA/JDBC vẫn blocking; cô lập blocking hoặc giữ MVC và tính cả transaction semantics.
5. **“Thêm cả hai starter thì Spring Boot tự chọn WebFlux.”** Thường sai trong cấu hình Boot 3.x: MVC được ưu tiên khi cả hai starter có mặt. Kiểm tra web application type khởi động thật.
6. **“Nhiều request đồng thời nghĩa là tác vụ CPU mạnh.”** Không: phân biệt số kết nối chờ I/O với tính toán CPU; cần đo riêng.
7. **“Có backpressure thì không bao giờ tràn bộ nhớ.”** Sai: buffering, nguồn dữ liệu, operator, client và hệ thống ngoài vẫn cần giới hạn rõ.
8. **“Virtual threads giải quyết mọi thư viện blocking.”** Sai: chúng không thay thế timeout, connection pool, circuit breaker hay năng lực hệ thống phụ thuộc.
9. **“Di cư toàn bộ sang reactive luôn là lựa chọn tốt.”** Chưa chắc: chi phí chuyển transaction, security, test, observability và đào tạo có thể lớn hơn lợi ích.

## 12. Bài tập tự kiểm tra

**Câu 1.** API CRUD dùng PostgreSQL + Spring Data JPA, tối đa vài trăm request/s, toàn bộ SDK đồng bộ. Chọn stack nào? **Gợi ý:** MVC vì đường xử lý chính blocking và thư viện hiện hữu phù hợp imperative.

**Câu 2.** Một API gateway dùng WebClient cho 8 upstream, cần giữ hàng chục nghìn kết nối chờ mạng, không có driver blocking. Nên làm gì? **Gợi ý:** dựng bản thử WebFlux, so với MVC async; kiểm tra tail latency, memory, HTTP pool, timeout và cancellation.

**Câu 3.** WebFlux controller gọi `repository.findAll()` từ JPA trong `Mono.just(...)`. Có non-blocking không? **Không.** Lệnh JPA chạy ngay khi tạo Mono; cần đổi chiến lược hoặc cô lập trên scheduler phù hợp, và đánh giá lại việc chọn WebFlux.

## 13. Checklist trước khi quyết định

- [ ] Đã mô tả các request trọng tâm và phần thời gian chờ I/O so với CPU.
- [ ] Đã đánh dấu blocking/non-blocking cho DB, HTTP client, SDK, cache và I/O khác.
- [ ] Đã kiểm tra servlet/reactive integration, transaction, security và phiên bản starter.
- [ ] Đã xem xét MVC async, WebClient và virtual threads như các phương án thích hợp.
- [ ] Đã thiết kế timeout, pool, giới hạn concurrency, retry/circuit breaker và observability.
- [ ] Đã benchmark trên tải đại diện; ghi lựa chọn cùng bằng chứng trong ADR.

## Tài liệu tham khảo chính thức

- [Spring Framework — WebFlux Overview and Applicability](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — MVC Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Task Execution, Scheduling and Virtual Threads](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
