# Chọn Servlet/MVC hay WebFlux theo chuỗi I/O và nhu cầu ứng dụng

## 1. Mục tiêu và nguyên tắc chọn

Khi xây dựng ứng dụng web với Spring Framework, lựa chọn chính thường là **Spring Web MVC (Servlet stack)** hoặc **Spring WebFlux (reactive stack)**. Cả hai đều xây dựng REST API, xác thực, xử lý lỗi, trả JSON và phục vụ nhiều loại ứng dụng. Câu hỏi quan trọng không phải “framework nào hiện đại hơn?”, mà là:

1. **Toàn bộ đường đi của một request thực hiện những I/O nào?** Chẳng hạn đọc database, gọi HTTP, gọi Redis, gửi message, đọc file.
2. **Các thư viện ở từng chặng có thực sự hỗ trợ non-blocking không?**
3. **Ứng dụng cần tối ưu điều gì?** Khả năng bảo trì, số request đồng thời, tiêu thụ thread/memory, streaming, độ trễ cuối đuôi (p95/p99), hay khả năng tận dụng code hiện có.
4. **Đội ngũ có khả năng vận hành và gỡ lỗi mô hình reactive đến đâu?**

**Quy tắc xuất phát:** nếu phần lớn nghiệp vụ dùng thư viện đồng bộ như JDBC/JPA và Spring MVC đang đáp ứng tốt yêu cầu, ưu tiên MVC. Nếu ứng dụng xử lý nhiều I/O chờ lâu, có thể duy trì chuỗi non-blocking từ HTTP vào đến các hệ thống phụ thuộc và cần độ đồng thời lớn, WebFlux là ứng viên đáng thử nghiệm. Quyết định cuối cùng cần được kiểm chứng bằng tải thực tế.

## 2. Hiểu đúng blocking, asynchronous, non-blocking và reactive

- **Blocking I/O:** thread gọi một tác vụ và phải chờ kết quả trước khi tiếp tục. Ví dụ JDBC `repository.findById(id)`, lệnh gọi HTTP đồng bộ `RestClient.retrieve().body(...)`.
- **Asynchronous:** tác vụ hoàn thành ở thời điểm sau; caller có thể nhận `Future`, callback hoặc một đối tượng đại diện cho kết quả. “Async” không tự bảo đảm bên dưới không có thread đang chờ blocking.
- **Non-blocking I/O:** khi dữ liệu chưa sẵn sàng, thread không phải đứng chờ thao tác I/O đó; runtime nhận thông báo hoặc tín hiệu khi có thể tiếp tục xử lý.
- **Reactive programming:** mô tả pipeline dữ liệu/sự kiện cùng tín hiệu hoàn thành và lỗi, thường biểu diễn bằng `Mono<T>` (0 hoặc 1 kết quả) và `Flux<T>` (0 đến nhiều kết quả) trong Project Reactor.
- **Backpressure:** bên tiêu thụ có thể báo khả năng nhận dữ liệu cho publisher trong một pipeline hỗ trợ Reactive Streams. Backpressure không đồng nghĩa tự động giới hạn mọi HTTP request đến hoặc kiểm soát mọi hệ thống ngoại vi.

Lưu ý hai hiểu nhầm thường gặp:

- Có `Mono`/`Flux` **không có nghĩa** mọi chặng là non-blocking. `Mono.just(jdbcRepository.findById(id))` vẫn gọi JDBC **ngay lúc tạo Mono**, trên thread hiện tại.
- WebFlux **không mặc nhiên xử lý một request nhanh hơn** MVC. Ưu điểm chính của non-blocking là có thể phục vụ nhiều kết nối đang chờ I/O với ít thread hơn trong điều kiện phù hợp. CPU, database, connection pool và downstream vẫn đặt giới hạn.

## 3. Hai execution model nhìn từ một request

### Spring MVC / Servlet

Luồng điển hình khi controller gọi thư viện đồng bộ:

~~~text
HTTP request
  → Servlet container (ví dụ Tomcat)
  → Filter → DispatcherServlet → @Controller
  → Service → JDBC/JPA hoặc HTTP client đồng bộ
                         [thread chờ I/O]
  ← Service ← kết quả
  → Serialize JSON → HTTP response
~~~

Trong đường đi đồng bộ thông thường, một thread xử lý request bận chờ ở lời gọi blocking. Servlet container dùng thread pool để tiếp nhận nhiều request đồng thời. Nếu I/O chậm và lưu lượng lớn, request có thể phải xếp hàng chờ thread.

**MVC cũng hỗ trợ bất đồng bộ:** `Callable`, `DeferredResult`, `WebAsyncTask`, trả reactive type, streaming và SSE. Cơ chế Servlet async có thể giải phóng thread tiếp nhận request trước khi kết quả sẵn sàng. Vì vậy không nên đồng nhất “MVC” với “mọi request luôn giữ một platform thread đến cuối”; cần nhìn vào code và executor thực tế.

### Spring WebFlux

Luồng điển hình khi **các chặng thật sự non-blocking**:

~~~text
HTTP request
  → WebFlux runtime / event loop
  → WebFilter → DispatcherHandler → Controller trả Mono/Flux
  → WebClient / reactive repository: đăng ký I/O, chưa có dữ liệu thì trả thread
  → I/O sẵn sàng: tiếp tục pipeline qua tín hiệu
  → Encode dữ liệu → HTTP response non-blocking
~~~

Event loop có thể điều phối nhiều kết nối; nó **phải tránh bị chặn** bởi `Thread.sleep`, `Future.get`, `block()`, JDBC/JPA đồng bộ hoặc xử lý CPU kéo dài. Khi một event-loop thread bị chặn, nhiều request cùng dùng thread đó có thể bị chậm.

**Tên web server không quyết định mô hình:** MVC xây dựng trên Servlet API và thường chạy Tomcat/Jetty; WebFlux mặc định thường dùng Reactor Netty khi khởi tạo qua Spring Boot, nhưng cũng có thể chạy với các server hỗ trợ khác. “Chạy trên Tomcat” không tự suy ra MVC; phải xem web stack và runtime configuration.

## 4. Phân tích **toàn chuỗi I/O** trước khi chọn

Hãy vẽ một request đại diện, kể cả các hệ thống mà ứng dụng đang dùng:

~~~text
Client
  → HTTP server
  → Authentication/filter
  → Controller
  → Service
      ├─ SQL database / transaction
      ├─ External HTTP services
      ├─ Cache
      └─ Messaging / file storage
  → Serialize / stream response
  → Client
~~~

Phân loại từng chặng theo các câu hỏi sau:

| Chặng | Cách thường gặp có thể block | Lựa chọn non-blocking khi phù hợp |
| --- | --- | --- |
| HTTP server | Servlet handler xử lý đồng bộ | WebFlux event-loop/non-blocking transport |
| Gọi REST/HTTP ngoài | `RestClient`, `RestTemplate` sử dụng đồng bộ | `WebClient` với connector hỗ trợ non-blocking |
| SQL | JDBC, JPA/Hibernate ORM truyền thống | R2DBC với driver hỗ trợ và reactive repository |
| NoSQL/cache | Driver/template đồng bộ | Reactive driver/template tương ứng, nếu có |
| File/SDK bên thứ ba | SDK sync, `InputStream.read` | API async/non-blocking thực sự; phải xác minh SDK cụ thể |
| CPU xử lý JSON, mã hóa, nén | Không phải I/O; vẫn tiêu tốn CPU | Tối ưu thuật toán, điều phối CPU có giới hạn; reactive không làm CPU nhanh hơn |
| Ghi response | MVC có hỗ trợ async nhưng một số thao tác ghi vẫn blocking | WebFlux sử dụng non-blocking I/O |

**Điểm nghẽn quyết định:** nếu controller trả `Mono` nhưng service vẫn gọi JDBC đồng bộ, sự chờ đợi chưa biến mất. WebFlux khi đó vừa gánh chi phí mô hình reactive, vừa cần tài nguyên cho blocking calls. Ngược lại, ứng dụng MVC vẫn dùng được `WebClient` để phối hợp các lời gọi HTTP bất đồng bộ mà không phải chuyển toàn bộ server sang WebFlux.

Khi rà soát chuỗi I/O, ghi rõ cho từng dependency: API đang dùng; thread nào thực thi; thời gian chờ; timeout; giới hạn connection pool; chiến lược retry; khả năng hủy yêu cầu; và trạng thái giao dịch. Nếu thiếu thông tin về một SDK, hãy đo hoặc kiểm tra tài liệu của SDK thay vì suy đoán từ tên method có chữ “async”.

## 5. Khi nào chọn Spring MVC?

MVC thường phù hợp khi:

1. **CRUD, business application, quản trị nội bộ** với Spring Data JPA/Hibernate, JDBC hoặc các SDK đồng bộ chiếm phần lớn logic.
2. Luồng nghiệp vụ có giao dịch quan hệ và cách lập trình tuần tự dễ đọc, dễ debug; đội ngũ đã quen với `@Transactional` trong mô hình imperative.
3. Hiện trạng đạt SLA về latency/throughput với số thread, connection pool và chi phí hạ tầng chấp nhận được.
4. Hệ sinh thái thư viện, Servlet filter, interceptor, bảo mật hoặc tích hợp hiện có phù hợp với MVC.
5. Chỉ có vài lời gọi HTTP ra ngoài: có thể tối ưu hoặc gọi song song từng bước khi cần, không nhất thiết đổi web stack.

**Ví dụ tình huống:** tạo đơn hàng cần đọc và cập nhật các bảng qua JPA trong một transaction. JDBC/JPA vẫn blocking; MVC là nền tảng rõ ràng để triển khai nghiệp vụ, quản lý transaction, validation và xử lý lỗi. Không nên chuyển sang WebFlux chỉ vì muốn method trả `Mono<Order>`.

Các tối ưu nên xét trước khi đổi framework: index/query database, batch query, timeout, kích thước JDBC pool, giới hạn kết nối downstream, tránh N+1 query, cache hợp lý và đo p95/p99.

## 6. Khi nào WebFlux đáng cân nhắc?

WebFlux có lợi thế tiềm năng khi đồng thời có nhiều đặc điểm sau:

1. **Nhiều request đồng thời chờ I/O mạng**: API gateway/BFF tổng hợp nhiều upstream, các dịch vụ chat/notification hoặc các endpoint giữ kết nối lâu.
2. HTTP client, persistence, cache và adapter cần thiết có **API reactive/non-blocking thật sự**, hoặc phần blocking được cô lập rất ít và có giới hạn.
3. Có nhu cầu streaming `Flux`/SSE hoặc xử lý luồng dữ liệu lớn theo cách reactive; cân nhắc flow control và việc client đọc chậm.
4. Tài nguyên thread/memory hoặc tính ổn định dưới tải chờ I/O là vấn đề đã đo được.
5. Nhóm có kinh nghiệm Reactor: hiểu cold publisher, subscription, scheduler, error propagation, context và testing bất đồng bộ.

**Ví dụ tình huống:** dịch vụ BFF gọi đồng thời ba API độc lập có độ trễ mạng biến động, sau đó ghép kết quả. `WebClient` + `Mono.zip` mô tả tổ hợp các kết quả mà không giữ một thread để chờ từng socket. Với nhiều kết nối in-flight, mô hình này có thể tiết kiệm tài nguyên thread; lợi ích thực tế phụ thuộc vào giới hạn upstream và kết quả benchmark.

Không chọn WebFlux chỉ vì có endpoint WebSocket/SSE: MVC cũng hỗ trợ nhiều kiểu bất đồng bộ và streaming. Cần đánh giá quy mô, flow control, hạ tầng và thư viện phù hợp.

## 7. Ví dụ đối chiếu: cùng một bài toán gọi hai upstream

Giả sử endpoint `GET /profiles/{id}` cần lấy `GET /users/{id}` và `GET /scores/{id}` từ dịch vụ khác ở `http://localhost:8081`. Hai dịch vụ upstream độc lập và trả JSON:

~~~json
{"name":"Lan"}
~~~

~~~json
{"value":87}
~~~

Các ví dụ sau dành cho **hai ứng dụng Spring Boot 3.x độc lập**, dùng Spring Framework 6.1+ và Java 17+. Để chạy end-to-end cần có upstream giả lập ở cổng 8081 với đúng hai API này. Nếu upstream không hoạt động, request sẽ thất bại do kết nối; **không có stdout hay kết quả timing cố định** được giả định. Mỗi dự án cần Spring Boot Gradle plugin và dependency management thông thường.

### Phương án A — Spring MVC + HTTP client đồng bộ

Trong dự án MVC, khai báo dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tạo `src/main/java/example/mvc/MvcApp.java`:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class MvcApp {
    public static void main(String[] args) {
        SpringApplication.run(MvcApp.class, args);
    }

    @RestController
    static class ProfileController {
        private final RestClient client = RestClient.builder()
                .baseUrl("http://localhost:8081")
                .build();

        @GetMapping("/profiles/{id}")
        Profile find(@PathVariable long id) {
            User user = client.get().uri("/users/{id}", id)
                    .retrieve().body(User.class);
            Score score = client.get().uri("/scores/{id}", id)
                    .retrieve().body(Score.class);

            if (user == null || score == null) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY);
            }
            return new Profile(user.name(), score.value());
        }
    }

    record User(String name) {}
    record Score(int value) {}
    record Profile(String name, int score) {}
}
~~~

Ở ví dụ này, hai lời gọi `RestClient` lần lượt chờ kết quả trên thread xử lý; thời gian của đường HTTP gần với tổng thời gian chờ hai upstream (cộng chi phí xử lý khác). Đây là một cách triển khai dễ đọc, phù hợp khi ứng dụng dùng các dependency đồng bộ. Không kết luận rằng **mọi** ứng dụng MVC bắt buộc gọi tuần tự như đoạn code này.

### Phương án B — WebFlux + WebClient non-blocking

Trong **dự án riêng** cho WebFlux, dùng dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Tạo `src/main/java/example/webflux/WebFluxApp.java`:

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxApp {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxApp.class, args);
    }

    @RestController
    static class ProfileController {
        private final WebClient client = WebClient.builder()
                .baseUrl("http://localhost:8081")
                .build();

        @GetMapping("/profiles/{id}")
        Mono<Profile> find(@PathVariable long id) {
            Mono<User> user = client.get().uri("/users/{id}", id)
                    .retrieve().bodyToMono(User.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(HttpStatus.BAD_GATEWAY)));
            Mono<Score> score = client.get().uri("/scores/{id}", id)
                    .retrieve().bodyToMono(Score.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(HttpStatus.BAD_GATEWAY)));

            return Mono.zip(user, score)
                    .map(pair -> new Profile(
                            pair.getT1().name(), pair.getT2().value()));
        }
    }

    record User(String name) {}
    record Score(int value) {}
    record Profile(String name, int score) {}
}
~~~

`Mono.zip(user, score)` đăng ký hai publisher và chờ **cả hai** hoàn thành; các HTTP request có thể được xử lý đồng thời bằng connector non-blocking. Do đó, phần chờ mạng thường gần với nhánh chậm hơn (cộng overhead), nếu hai upstream thực sự độc lập. `retrieve()` mặc định chuyển các HTTP 4xx/5xx thành tín hiệu lỗi; ứng dụng thật cần mapping lỗi, timeout, cancellation và giới hạn downstream rõ ràng.

Với hai dự án trên, chạy ứng dụng bằng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), sau khi cấu hình Boot project và dịch vụ upstream. Gọi thử:

~~~bash
curl http://localhost:8080/profiles/42
~~~

Nếu upstream đáp ứng các JSON giả định, response body dự kiến của **cả hai** ứng dụng:

~~~json
{"name":"Lan","score":87}
~~~

Lưu ý: ví dụ minh họa **cách gọi tuần tự so với phối hợp async**, không phải một phép benchmark công bằng. MVC cũng có thể sử dụng `WebClient` hoặc executor để gọi song song; WebFlux có thể bị chậm nếu một bước vẫn blocking. Không so hiệu năng bằng cách chạy đơn lẻ hai đoạn này rồi suy ra kết luận chung.

## 8. Ba kiến trúc thường gặp và cách quyết định

| Tình huống | Lựa chọn khởi đầu hợp lý | Vì sao |
| --- | --- | --- |
| REST CRUD + JPA/JDBC + transaction nghiệp vụ | MVC | Persistence vẫn blocking; imperative dễ tích hợp và bảo trì |
| MVC hiện hữu cần gọi nhiều HTTP upstream | Giữ MVC, cân nhắc `WebClient`/async ở chặng HTTP | Tối ưu chặng chờ mạng trước khi cân nhắc migration toàn stack |
| Gateway/BFF nặng I/O, downstream non-blocking, lượng kết nối chờ lớn | Thử WebFlux và benchmark | Tối ưu thread khi phần lớn thời gian là chờ I/O |
| Reactive driver ở database nhưng các SDK then chốt vẫn sync | Đánh giá từng chặng; chưa đủ căn cứ đổi toàn ứng dụng | Blocking vẫn cần thread; chi phí cô lập blocking có thể đáng kể |
| Xử lý CPU nặng, mã hóa lớn, image/video processing | Tập trung kiến trúc worker, pool CPU và queue | Reactive không thêm CPU; phải tránh chiếm event loop |
| SSE/streaming với số client vừa phải | Cả MVC và WebFlux đều có lựa chọn | Quy mô, backpressure và vận hành mới quyết định |
| Dự án đang chạy MVC ổn định, chưa có số đo chứng minh vấn đề | Tiếp tục MVC | Migration mang chi phí và rủi ro không có lợi ích chắc chắn |

### Quy trình quyết định thực tế

1. **Chọn một luồng nghiệp vụ thật** (ví dụ tạo đơn hàng, truy xuất dashboard, gom dữ liệu cho màn hình).
2. **Vẽ I/O chain và đánh dấu mỗi lời gọi blocking/non-blocking**; xác nhận đến driver và connector thật, không dừng ở controller signature.
3. **Đặt yêu cầu tải cụ thể**: requests/giây, concurrent connections, độ trễ trung bình và p95/p99, tốc độ phản hồi downstream, memory budget, CPU budget.
4. **Xác định nút thắt trước**: thread pool, database connection pool, HTTP connection pool, query chậm, rate limit hoặc CPU.
5. **Chọn giải pháp nhỏ nhất xử lý được nút thắt**: tối ưu DB, timeout, bulkhead, caching, dùng async HTTP client, chỉnh pool, virtual threads hoặc WebFlux.
6. **Benchmark cùng nghiệp vụ, data, hạ tầng và profile tải**. Chỉ quyết định migration sau khi có bằng chứng.

## 9. Nếu WebFlux cần gọi thư viện blocking thì sao?

Không gọi trực tiếp hàm JDBC/SDK đồng bộ trên event loop, và không `block()` giữa reactive request pipeline. Một đường thoát tạm thời là chạy lời gọi blocking trên scheduler dành cho tác vụ blocking:

~~~java
Mono<Customer> customerMono = Mono.fromCallable(
        () -> blockingCustomerClient.findById(customerId))
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

Đây là **đoạn minh họa đặt bên trong một service đã có** biến `blockingCustomerClient` và `customerId`; không phải một chương trình Java độc lập. `fromCallable` trì hoãn lời gọi tới khi có subscription; `subscribeOn(boundedElastic())` chuyển công việc blocking ra khỏi event loop.

**Giới hạn:** blocking vẫn xảy ra trên thread khác; boundedElastic có giới hạn tài nguyên và hàng chờ, không khiến SDK biến thành non-blocking. Phải cấu hình timeout, concurrency, connection pool và theo dõi saturation. Nếu đa số pipeline là JPA/JDBC blocking, MVC thường là lựa chọn đơn giản hơn.

Ngược lại, đừng thay code này thành `Mono.just(blockingCustomerClient.findById(customerId))` vì lời gọi blocking sẽ thực thi ngay trên thread tạo publisher.

## 10. Transaction, context, xử lý lỗi và kiểm thử

- **Transaction:** mô hình imperative JDBC/JPA phổ biến dùng transaction gắn với thread; reactive persistence cần transaction manager hỗ trợ reactive và context của Reactor. `@Transactional` không tự biến JDBC thành reactive; không thể giả định một transaction thread-local xuyên suốt mọi callback reactive. Khi chuyển mô hình cần thiết kế lại ranh giới transaction và cách kết hợp DB calls.
- **Context:** code MVC thường dễ dựa vào `ThreadLocal` trong phạm vi request; reactive chain có thể đổi thread, nên thông tin tracing/security/request phải được truyền bằng cơ chế context tương thích (ví dụ Reactor Context và tích hợp của framework). Tránh tự suy ra mọi `ThreadLocal` luôn tồn tại.
- **Lỗi:** MVC thường xử lý exception bằng `@ExceptionHandler`/`@ControllerAdvice`; WebFlux cần hiểu cả exception trước khi tạo publisher và tín hiệu lỗi phát sau subscription (`onErrorResume`, error handler). Quy định rõ HTTP status, timeout, retry và chính sách khi upstream lỗi một phần.
- **Retry:** retry không điều kiện dễ khuếch đại tải hoặc lặp thao tác không idempotent; chỉ retry lỗi phù hợp, có backoff và giới hạn tổng thời gian.
- **Kiểm thử:** MVC thường dùng `MockMvc`; WebFlux thường dùng `WebTestClient`, `StepVerifier` cho publisher và virtual time khi cần. Cả hai cần integration test cho timeout/streaming/slow client và các adapter bên ngoài.
- **Observability:** đo per-endpoint latency, active threads/event-loop blocking, connection-pool utilization, request queue, GC, CPU, memory, số request đang chờ, error rate và độ trễ dependency. Kết quả đo quan trọng hơn số lượng annotation reactive.

## 11. Virtual threads có làm WebFlux không còn cần thiết?

Với **Java 21+**, virtual threads có thể giúp mô hình imperative xử lý nhiều tác vụ chờ I/O với chi phí thread thấp hơn platform threads trong những điều kiện phù hợp. Với phiên bản Spring Boot hỗ trợ, có thể cấu hình:

~~~properties
spring.threads.virtual.enabled=true
~~~

Điều này khiến MVC với code đồng bộ trở thành phương án cần benchmark thêm, nhất là khi đang dùng JDBC/JPA. Tuy nhiên:

- I/O vẫn **blocking về mặt API**; driver và connection pool không được tăng khả năng xử lý vô hạn.
- Virtual threads không khiến CPU-heavy task nhanh hơn; vẫn phải kiểm soát số operation đang chạy.
- Một số đoạn code/khóa/native interaction có thể hạn chế hiệu quả; cần theo dõi dấu hiệu pinning theo JDK và phiên bản đang dùng.
- WebFlux vẫn cung cấp mô hình reactive có backpressure, tổ hợp pipeline non-blocking và streaming; hai hướng có trade-off khác nhau.

Vì vậy không được kết luận “có virtual threads thì luôn chọn MVC” hoặc “có WebFlux thì không bao giờ cần virtual threads”. Đo đúng hệ thống của mình, gồm cả throughput và p95/p99.

## 12. Các lỗi chọn kiến trúc và triển khai thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Chọn WebFlux vì nghe “nhanh hơn” | Tăng độ phức tạp khi bottleneck nằm ở DB/CPU | Xác định I/O chain và benchmark |
| Controller trả `Mono` nhưng gọi JPA trực tiếp | Chặn event loop hoặc dời blocking sang chỗ khác | Chọn MVC, hoặc cô lập blocking tạm thời với pool giới hạn |
| Gọi `block()` trong controller WebFlux | Chặn hoặc gây lỗi trên non-blocking thread | Trả publisher và compose bằng operator |
| Trộn cả hai starter rồi đoán đang chạy WebFlux | Cấu hình server stack khác mong đợi | Kiểm tra Boot auto-configuration, startup log và loại ứng dụng |
| Cho `flatMap` concurrency quá cao | Dồn tải lên downstream/connection pool | Đặt giới hạn concurrency và timeout hợp lý |
| Dùng `WebClient` rồi gọi `.block()` mọi nơi | Không tận dụng async tại chặng gọi | Dùng pipeline async khi phù hợp; nếu nghiệp vụ imperative, hiểu rõ điểm chặn |
| Không đặt timeout/cancel/retry policy | Request chờ vô hạn, queue phình, lỗi dây chuyền | Đặt deadline, retry có điều kiện, backoff và đo saturation |
| Benchmark chỉ một request | Không thấy throughput, queue, tail latency | Test theo tải và số kết nối đồng thời thực tế |
| Chuyển toàn bộ MVC sang WebFlux dù còn nhiều SDK sync | Chi phí migration lớn, ít lợi ích | Ưu tiên tối ưu chặng gây nghẽn trước |

**Chú ý về Spring Boot:** khi thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trong cùng ứng dụng Boot 3.x, auto-configuration web server thông thường ưu tiên **MVC** (nhiều dự án MVC thêm WebFlux starter chỉ để dùng `WebClient`). Nếu muốn một WebFlux server đúng nghĩa, cấu hình rõ mô hình ứng dụng và dependency; không nhận diện qua việc có `Mono` trong chữ ký method.

## 13. Bài tập tự đánh giá

Hãy chọn phương án xuất phát và giải thích theo I/O chain:

1. **Hệ thống bán hàng:** `Controller → Service → JPA transaction → trả JSON`. Tải vừa phải và p95 đáp ứng mục tiêu.
2. **BFF dashboard:** `Controller → 4 HTTP API độc lập → ghép response`, mỗi API có độ trễ mạng đáng kể, số kết nối đồng thời lớn.
3. **Ứng dụng MVC hiện hữu:** một endpoint gọi hai HTTP service chậm, còn phần lớn nghiệp vụ dùng JPA.
4. **WebFlux endpoint:** controller gọi SDK đọc file blocking trong `map(...)` trên event loop.

**Gợi ý đáp án:** (1) MVC, đo SQL và transaction trước. (2) Thử WebFlux + WebClient khi các chặng non-blocking và benchmark chứng minh hiệu quả; hoặc thử client async trong MVC nếu đó là kiến trúc hiện có. (3) Giữ MVC, cải thiện riêng bước HTTP (cân nhắc WebClient/async) trước khi migration. (4) Không giữ blocking trong event loop: thay SDK bằng API phù hợp hoặc offload với `boundedElastic` có kiểm soát; nếu kiến trúc chủ yếu blocking, đánh giá lại MVC.

## 14. Checklist trước khi chốt lựa chọn

- [ ] Đã vẽ request path từ HTTP đến database, HTTP client, cache, message, file và response.
- [ ] Đã xác minh dependency/driver nào blocking và nào non-blocking.
- [ ] Đã xác định yêu cầu concurrency, throughput, p95/p99, memory và budget.
- [ ] Đã kiểm tra giới hạn database/HTTP connection pool, thread pool và downstream.
- [ ] Đã cân nhắc MVC async/WebClient hoặc virtual threads trước khi migration lớn.
- [ ] Với WebFlux, không có blocking bất ngờ trên event loop; có concurrency limit, timeout và xử lý lỗi.
- [ ] Có test phù hợp cho streaming, slow consumer, timeout, cancellation và retry.
- [ ] Có benchmark trên workload đại diện và số liệu observability để bảo vệ quyết định.

**Kết luận vận dụng:** lựa chọn web stack từ **chuỗi I/O thực tế và mục tiêu vận hành**. MVC là mặc định hợp lý cho nhiều hệ thống imperative/JPA; WebFlux đáng giá khi ứng dụng được thiết kế xuyên suốt cho non-blocking, cần nhiều I/O đồng thời và nhóm có năng lực vận hành reactive. Cả hai đều là công cụ hợp lệ; kết luận phải được củng cố bằng đo lường.

### Tài liệu tham khảo chính thức

- [Spring Framework — Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [Spring Framework — WebFlux và tiêu chí lựa chọn](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — MVC asynchronous requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Boot — Virtual threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
