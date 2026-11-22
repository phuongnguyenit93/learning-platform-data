# Đánh giá thư viện chặn luồng trước khi chọn mô hình reactive trong Spring Boot

## 1. Vấn đề cần giải quyết

Khi chọn giữa Spring MVC và Spring WebFlux cho một ứng dụng Spring Boot, không thể chỉ nhìn vào kiểu trả về của controller. **Đường xử lý request chỉ thực sự thu được lợi ích non-blocking khi những lời gọi I/O quan trọng trong đường đó cũng không giữ thread trong lúc chờ.** Một ứng dụng dùng `Mono` và `Flux` nhưng vẫn gọi JDBC/JPA, HTTP client đồng bộ hoặc SDK sync ngay trên event loop có thể bị tăng tail latency, nghẽn throughput và khó vận hành hơn.

Mục tiêu của bài là xây dựng một cách đánh giá có thể áp dụng ngay: kiểm kê thư viện, tìm chính xác lời gọi blocking, đo hành vi dưới tải, xem các phương án cô lập hoặc thay thế, rồi lựa chọn Spring MVC, Spring MVC với virtual threads hay Spring WebFlux dựa trên bằng chứng.

Ngữ cảnh kỹ thuật: Spring Boot 3.x, Spring Framework 6, Reactor và Java 17+; ý tưởng cũng dùng được cho phiên bản Spring mới hơn khi kiểm tra API tương ứng.

## 2. Phân biệt synchronous, blocking, asynchronous và reactive

| Khái niệm | Ý nghĩa | Ví dụ và lưu ý |
|---|---|---|
| Synchronous | Người gọi theo luồng điều khiển trực tiếp để lấy kết quả | Một API synchronous có thể thực hiện công việc ngắn trong CPU; không phải mọi lệnh synchronous đều chờ I/O |
| Blocking | Thread không thể tiếp tục công việc khác vì đang chờ điều kiện, I/O, lock hoặc kết quả | `InputStream.read`, JDBC query, `Thread.sleep`, `Future.get` |
| Asynchronous | Kết quả được thông báo sau qua callback, future hoặc signal | `CompletableFuture` có thể vẫn chạy một lời gọi blocking trong executor |
| Reactive | Biểu diễn công việc như chuỗi tín hiệu dữ liệu/lỗi/hoàn tất, có khả năng điều phối bất đồng bộ và backpressure | `Mono`, `Flux`, `Publisher`; vẫn có thể chứa thao tác blocking bên trong |

Các điểm cần nhớ:

- Một phương thức trả `Mono<T>` **không đảm bảo** code bên trong non-blocking. Ví dụ `Mono.just(jdbcRepository.findById(id))` đã gọi JDBC trước khi tạo publisher.
- `Mono.fromCallable(() -> legacyCall())` làm công việc lazy, nhưng callable vẫn có thể chặn thread được dùng để subscribe.
- `CompletableFuture.supplyAsync(() -> jdbcCall())` chuyển việc chờ sang thread pool; JDBC chưa trở thành I/O non-blocking.
- Backpressure giúp điều tiết yêu cầu dữ liệu giữa các thành phần reactive; nó không làm một SQL query đồng bộ trả kết quả nhanh hơn và không thay thế giới hạn connection pool.

## 3. Vì sao một thư viện blocking có thể khiến WebFlux nghẽn?

Spring MVC thông thường sử dụng Servlet worker thread để xử lý request. Thread đó có thể chờ JDBC, HTTP sync hoặc file I/O. Mô hình này đơn giản và phù hợp với hệ sinh thái thư viện đồng bộ, miễn là thread pool, timeout, connection pool và giới hạn đồng thời được cấu hình hợp lý.

Spring WebFlux hỗ trợ mô hình lập trình reactive và có thể chạy trên Reactor Netty hoặc servlet container phù hợp. Với Reactor Netty, một tập event-loop threads tương đối nhỏ quản lý nhiều kết nối. Event-loop cần sớm trả quyền điều khiển để phục vụ kết nối khác. Khi callback trên event-loop chờ một truy vấn JDBC hoặc lời gọi socket đồng bộ, các kết nối cùng phụ thuộc thread đó bị trì hoãn.

~~~text
Lối A: non-blocking HTTP call
Event-loop -> gửi request bất đồng bộ -> trả quyền cho event-loop
                                      -> tín hiệu response -> tiếp tục pipeline

Lối B: blocking library trên event-loop
Event-loop -> gọi JDBC/HTTP sync -> CHỜ -> CHỜ -> nhận kết quả
               (không xử lý công việc khác trên event-loop này)

Lối C: blocking library được cô lập
Event-loop -> xếp việc cho boundedElastic -> trả quyền cho event-loop
Worker của boundedElastic -> gọi thư viện sync -> CHỜ -> trả kết quả
~~~

Lối C bảo vệ event-loop nhưng vẫn tiêu tốn worker thread, socket, DB connection và hàng đợi. Việc bọc thư viện đồng bộ trong reactive wrapper chỉ thay đổi **nơi thực hiện blocking**, không tự tăng vô hạn khả năng phục vụ.

## 4. Kiểm kê toàn bộ đường xử lý request

Đừng chỉ xem code trong controller. Phân tích từng endpoint quan trọng theo luồng:

~~~text
HTTP -> filter -> authentication/authorization -> validation
     -> controller/handler -> service -> repository/cache/HTTP/SDK/files
     -> mapping/serialization/logging -> HTTP response
~~~

Ghi thông tin cho từng lời gọi I/O:

1. Tên và phiên bản dependency; tên method/overload thật sự được dùng.
2. Có blocking không? Nếu có, chờ tài nguyên nào: socket, DB, file, lock, connection pool hay thread?
3. Method được gọi ở thread/scheduler nào? Có bị gọi trên Reactor Netty event loop không?
4. Có lựa chọn native async/reactive không? API async bên dưới có chạy trên non-blocking transport hay chỉ là executor chạy blocking?
5. Timeout, retry, giới hạn số kết nối và khả năng hủy đang được cấu hình ra sao?
6. Có dùng `ThreadLocal`, `@Transactional`, MDC, security context, locale hoặc request-scoped state?
7. Phần việc tốn CPU hay I/O? Có streaming hay vô tình đọc toàn bộ file/response vào RAM?
8. Thao tác có nằm trên đường nóng, có tần suất cao, nhiều fan-out hoặc p99 lớn không?

Rà soát cả cache miss, token refresh, signature verification, audit logging, DNS lookup, serialization nặng, custom `WebFilter` và `WebExceptionHandler`. Một lệnh blocking ở filter có thể ảnh hưởng toàn bộ request trước khi tới controller.

## 5. Các nhóm thư viện thường cần đánh giá

| Nhóm | Cách dùng có nguy cơ blocking | Khả năng thay thế/đối sách |
|---|---|---|
| Persistence quan hệ | JDBC, JPA/Hibernate, `JdbcTemplate`, `JpaRepository` dựa trên JDBC | Giữ Spring MVC; hoặc cân nhắc Spring Data R2DBC và driver R2DBC đúng DB đang dùng |
| HTTP outbound | `RestTemplate`, `RestClient` đồng bộ, nhiều cấu hình Feign client, `HttpClient.send` | `WebClient` + non-blocking connector; async HTTP client của SDK nếu thật sự không chặn |
| Redis/cache | Lệnh đồng bộ trên client Redis; cache loader gọi DB/HTTP sync | API async/reactive của driver như Lettuce hoặc cô lập phần sync |
| NoSQL | API client/repository synchronous | Driver và repository reactive chính thức, kiểm tra từng method |
| Cloud SDK | Sync API tải/upload object, gọi payment/secret/service | Async SDK và streaming API; kiểm tra thread model và timeout |
| Filesystem | `Files.readAllBytes`, `InputStream.read`, đọc/ghi file lớn | Async NIO khi phù hợp hoặc worker pool có giới hạn; tránh đọc tràn bộ nhớ |
| Security | Lookup user/token đồng bộ, refresh credentials qua HTTP sync | Tổ chức reactive authentication flow, client không chặn, phân tích callback |
| Mã hóa/báo cáo | Hash password, nén, tạo PDF, kết xuất ảnh | Tách CPU-bound khỏi event loop; cân nhắc job queue và worker pool |
| Messaging | API producer/consumer có thể async nhưng serialization/callback vẫn đồng bộ | Xác minh thread thực thi callback, queue, flow control và backpressure |

**Chú ý đến chính xác API được gọi.** Việc có cả thư viện sync và reactive trong classpath không chứng minh endpoint đang dùng phiên bản non-blocking. Một client có tên “async” vẫn có thể dùng executor bọc thư viện sync. Connection pooling giúp tái sử dụng kết nối nhưng không làm lệnh JDBC trở thành non-blocking.

### 5.1. Những ví dụ blocking cần nhận diện

~~~java
// Mã trong service MVC bình thường có thể hợp lý,
// nhưng không nên chạy trực tiếp trên event-loop WebFlux.
Order order = orderRepository.findById(orderId).orElseThrow();

// HTTP client đồng bộ: thread đợi server phản hồi.
Customer customer = restClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .body(Customer.class);

// Tạo reactive pipeline nhưng cuối cùng vẫn đợi đồng bộ.
Customer customer2 = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .block();

// File I/O đồng bộ.
byte[] bytes = Files.readAllBytes(path);
~~~

Các đoạn này là minh họa, chưa phải một class Java độc lập. Tránh gọi `block()`, `blockFirst()`, `blockLast()`, `Future.get()` hoặc `Thread.sleep()` trên event-loop. Trên một số thread được Reactor đánh dấu non-blocking, `block()` có thể phát sinh `IllegalStateException`; việc không thấy exception không chứng minh mọi I/O đều an toàn.

### 5.2. R2DBC có phải cách thay JPA tức thì?

Không. R2DBC cung cấp API non-blocking cho cơ sở dữ liệu quan hệ khi dùng driver hỗ trợ. Nó khác mô hình JDBC/JPA về mapping, persistence context, lazy loading, transaction, query API và khả năng tích hợp. Trước khi đổi cần rà soát feature nghiệp vụ, hiệu năng driver, connection pool, xử lý transaction và chi phí migration. Nếu ứng dụng phụ thuộc mạnh vào JPA, giữ MVC thường tiết kiệm độ phức tạp hơn.

## 6. Quy trình kiểm tra dependency và code

### Bước 1: Kiểm tra dependency runtime

Trong dự án Maven hoặc Gradle dùng một trong các lệnh tương ứng:

~~~bash
./mvnw dependency:tree
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm client JDBC/JPA, HTTP, Redis, cloud SDK, reporting, messaging và các wrapper tự viết. Dependency tree chỉ cho biết thư viện hiện diện; kiểm tra lời gọi cụ thể mới xác định được blocking path.

### Bước 2: Rà soát lời gọi nguy hiểm

Dùng chức năng Find Usages/Call Hierarchy của IDE hoặc trình tìm kiếm mã để lần theo `block`, `join`, `get`, `sleep`, synchronous repository, `Files.readAllBytes`, `InputStream.read`, `RestClient`, `RestTemplate` và các lời gọi SDK sync. Kiểm tra cả lớp adapter dùng trong service.

Không kết luận một lần khớp từ khóa là lỗi. Ví dụ `join` của một chuỗi xử lý in-memory có thể có ngữ nghĩa khác, và method tên `get` không nhất thiết chặn. Cần xem implementation và tài liệu API.

### Bước 3: Tập trung endpoint có tác động lớn

Ưu tiên endpoint có p95/p99 cao, nhiều request đồng thời, dùng fan-out tới nhiều API, DB query chậm hoặc streaming/upload/download. Với mỗi endpoint, tạo hồ sơ:

| Endpoint | Dependency | Hành vi | Cách xử lý dự kiến |
|---|---|---|---|
| GET /orders/{id} | JPA Repository | SQL sync blocking | Ưu tiên MVC hoặc đánh giá đổi persistence |
| GET /recommendations | WebClient | HTTP non-blocking nếu không `block()` | Phù hợp để thử WebFlux |
| POST /reports | Sync SDK + tạo PDF | Chờ I/O và CPU nặng | Đưa vào worker/task queue; có thể trả 202 |
| GET /profile | Redis sync | Chờ socket | Chuyển driver API hoặc cô lập trong boundedElastic |

Thời gian chờ, số lời gọi và tỷ lệ lỗi phải lấy từ tracing/metric thực tế; không dùng số phỏng đoán để chọn stack.

### Bước 4: Phân loại mức độ rủi ro

- **Rủi ro rất cao:** blocking diễn ra trên event-loop của đường nóng, nhiều request chờ lâu, không giới hạn timeout hoặc không có bulkhead.
- **Rủi ro cao:** nhiều lời gọi blocking được đẩy sang cùng một boundedElastic nhưng DB pool, queue và concurrency không được kiểm soát.
- **Rủi ro trung bình:** số ít thư viện sync ở đường ít dùng, có timeout và scheduler giới hạn, được giám sát.
- **Rủi ro thấp:** I/O chính dùng driver/transport non-blocking, các callback ngắn và được kiểm chứng với load test.

Đây là hướng đánh giá tương đối; ngưỡng thật phải đo từ hệ thống.

## 7. Kiểm chứng runtime thay vì đoán

### 7.1. Profiling và thread dump

Java Flight Recorder (JFR), async-profiler, Java thread dump và tracing giúp phát hiện thread bị giữ ở socket read, DB driver, connection pool acquire, file I/O hoặc lock. Tên thread liên quan `reactor-http-nio` có thể gợi ý đó là event-loop trong Reactor Netty, nhưng phải kiểm tra call stack và môi trường triển khai vì tên thread có thể thay đổi.

Kiểm tra các callback `map`, `flatMap`, `doOnNext`, filter, security logic, serialize/deserialize và error handler. Nếu các bước này gọi service đồng bộ trên event-loop, hãy xác định nguồn blocking trước khi sửa.

### 7.2. Công cụ phát hiện blocking

BlockHound có thể giúp tìm một số thao tác blocking trên thread được đánh dấu non-blocking trong môi trường kiểm thử. Cần xác nhận tương thích JDK, agent/instrumentation và thư viện hiện dùng; công cụ không bao quát mọi driver và đường code. “Không thấy báo lỗi” không chứng minh pipeline hoàn toàn non-blocking. Kết hợp static review, thread dump, tracing và kiểm thử tải.

### 7.3. Đo tải đại diện

So sánh cùng cơ sở hạ tầng, workload và cấu hình pool:

- Throughput hữu ích (RPS), p50/p95/p99 latency và error/timeout rate.
- CPU, RAM, garbage collection, thread count, context switching khi có số liệu.
- Event-loop lag hoặc thời gian chờ trong event loop theo instrumentation thực tế.
- Độ bão hòa `boundedElastic`, scheduler queue, DB/HTTP connection pools, remote API rate limit.
- Số request in-flight, thời gian chờ DB, thời gian gọi HTTP outbound, kích thước response.
- Hành vi khi downstream chậm, pool cạn, client hủy request hoặc service shutdown.

Một benchmark GET trả chuỗi cố định không đủ. Nếu tất cả endpoint thực tế gọi JDBC, phải đưa JDBC vào benchmark thì mới so sánh stack có ý nghĩa.

## 8. Xử lý thư viện blocking khi đã chọn WebFlux

### 8.1. Cô lập bằng boundedElastic

Khi chưa thể thay SDK legacy, bọc phần việc blocking và bố trí sang scheduler phù hợp:

~~~java
Mono<Profile> result = Mono.fromCallable(() -> legacyClient.loadProfile(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` trì hoãn thực thi cho đến subscription. `subscribeOn` giúp nguồn chạy trên scheduler được chỉ định. `boundedElastic` dành cho các tác vụ có thể chặn, với giới hạn tài nguyên và hàng đợi; nó **không loại bỏ blocking** và có thể bão hòa khi số request lớn.

Ngược lại, ví dụ sau vẫn blocking trước khi publisher được tạo:

~~~java
Profile profile = legacyClient.loadProfile(id);  // blocking ngay ở thread gọi
return Mono.just(profile)
        .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` chỉ chuyển xử lý downstream từ điểm đặt operator, không thay đổi lời gọi đã diễn ra trước nó. Không dùng `Schedulers.parallel()` để chạy lời gọi I/O blocking kéo dài vì scheduler đó phục vụ chủ yếu các tác vụ CPU ngắn.

### 8.2. Giới hạn để cô lập thực sự hiệu quả

Cần đồng bộ các giới hạn: timeout kết nối/đọc, DB pool, giới hạn tác vụ concurrent, scheduler size/queue, số lần retry và circuit breaker. Một scheduler lớn hơn DB pool nhiều lần có thể chỉ chuyển tình trạng nghẽn từ event loop sang hàng đợi chờ connection.

Reactive cancellation có thể dừng phát tín hiệu trong pipeline nhưng không bảo đảm hủy một lời gọi JDBC hoặc SDK đồng bộ đang chạy; luôn kiểm tra semantics của driver và cơ chế timeout.

### 8.3. Transaction, ThreadLocal và context

JPA/JDBC thường dùng transaction context gắn với `ThreadLocal`. Nếu phải gọi JPA trong WebFlux, đưa **toàn bộ đơn vị xử lý blocking có ranh giới giao dịch phù hợp** vào service đồng bộ, rồi gọi service đó trong `fromCallable` trên boundedElastic. Không mở transaction trên một thread rồi cho repository chạy qua các thread khác và mặc định transaction vẫn có hiệu lực. Chú ý cơ chế proxy Spring: tự gọi `this.someTransactionalMethod()` có thể không qua proxy `@Transactional`.

Reactive transaction trên R2DBC dùng `ReactiveTransactionManager` và Reactor Context; không dùng giống JDBC transaction manager. Với MDC, Spring Security context, locale và tracing, cần cơ chế context propagation phù hợp; kiểm thử sau mỗi scheduler boundary.

## 9. Ví dụ Spring Boot 3.x, Java 17: WebFlux bao quanh một service blocking

Ví dụ sau đặt trong `src/main/java/example/web/ReactiveAuditApplication.java` của dự án Spring Boot 3.x đã có `spring-boot-starter-webflux`. Có đủ main class, bean và endpoint để khởi động. `Thread.sleep(40)` chỉ mô phỏng API blocking, không dùng làm I/O trong ứng dụng thật.

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuditApplication.class, args);
    }

    public record Profile(long id, String name) {}
}

@Service
class LegacyProfileService {

    ReactiveAuditApplication.Profile load(long id) {
        try {
            Thread.sleep(40);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return new ReactiveAuditApplication.Profile(id, "demo");
    }
}

@RestController
class ProfileController {

    private final LegacyProfileService service;

    ProfileController(LegacyProfileService service) {
        this.service = service;
    }

    @GetMapping("/profiles/{id}")
    public Mono<ReactiveAuditApplication.Profile> find(@PathVariable long id) {
        return Mono.fromCallable(() -> service.load(id))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Khởi động bằng wrapper tương ứng của dự án:

~~~bash
./mvnw spring-boot:run
# hoặc:
./gradlew bootRun
~~~

Gọi endpoint khi server đã chạy:

~~~bash
curl -s http://localhost:8080/profiles/7
~~~

Body JSON dự kiến:

~~~json
{"id":7,"name":"demo"}
~~~

Lời gọi `load` vẫn chặn một boundedElastic worker khoảng 40 ms. Dùng ví dụ này để học cách tách event loop khỏi thư viện đồng bộ, không xem đây là ứng dụng non-blocking end-to-end. Với tác vụ thật cần giới hạn concurrency và cấu hình timeout ở client hoặc DB.

### 9.1. Khi đã có HTTP client non-blocking

Đoạn minh họa sau là method trong một component Spring đã inject `WebClient` có base URL đúng; nó không phải chương trình Java độc lập:

~~~java
Mono<ReactiveAuditApplication.Profile> loadRemote(
        WebClient webClient, long id) {
    return webClient.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(ReactiveAuditApplication.Profile.class);
}
~~~

Với WebClient và connector non-blocking, I/O HTTP có thể chạy mà không phải giữ worker thread để chờ network. Không gọi `block()` trong handler WebFlux. Cần định nghĩa timeout, error mapping, retry policy và cách cấp phát buffer cho client thực tế.

## 10. Nếu đa số hệ thống vẫn blocking: Spring MVC là lựa chọn hợp lý

Spring MVC là phương án tự nhiên khi ứng dụng dựa nặng vào JPA/Hibernate, JDBC, SDK đồng bộ hoặc transaction imperative. Chọn MVC không đồng nghĩa thiếu khả năng chịu tải; tối ưu connection pool, cache, timeout, request concurrency, backpressure ở boundary và tách job dài vẫn rất quan trọng.

Khi chạy Java 21+ và phiên bản Spring Boot có hỗ trợ, **virtual threads** là một phương án cần đánh giá cho Servlet/MVC trong workload nhiều I/O chờ. Virtual threads có thể giảm chi phí thread gắn với request blocking, nhưng JDBC vẫn đồng bộ và database/connection pool không tăng khả năng xử lý tự động. Cần đo pinning, synchronized/lock contention, CPU-bound work và các giới hạn tài nguyên khác.

WebFlux phù hợp hơn khi đa phần dependency trên đường nóng đã hỗ trợ non-blocking: WebClient, driver reactive, stream dữ liệu, high concurrency waiting I/O hoặc SSE. Nếu nhiều library legacy không thay được, có thể tách phần nghiệp vụ blocking ra service MVC riêng và để boundary HTTP/message trao đổi với phần reactive, nhưng cần cân nhắc thêm độ phức tạp deployment, tracing và nhất quán dữ liệu.

## 11. Ma trận quyết định

| Hiện trạng | Ưu tiên đánh giá | Cơ sở |
|---|---|---|
| Nhiều JPA/JDBC, HTTP sync và transaction imperative | Spring MVC | Phù hợp cơ chế thư viện và transaction hiện có |
| Nhiều request chờ I/O sync; có Java 21+ và hỗ trợ virtual threads | Spring MVC + virtual threads | Có thể giảm overhead thread chờ, vẫn giữ API sync |
| HTTP outbound và DB đều có reactive/non-blocking driver; có streaming | Spring WebFlux | Có cơ hội tối ưu event-loop và pipeline dữ liệu |
| WebFlux chỉ còn một ít sync SDK ở đường ít dùng | WebFlux + boundedElastic có giới hạn | Cô lập phần blocking, theo dõi queue và pool |
| WebFlux nhưng hầu hết endpoint gọi JPA/HTTP sync | Cân nhắc MVC hoặc lộ trình đổi dependency | Dùng reactive wrapper đại trà tăng phức tạp, không thay đổi hành vi I/O |
| Nhiệm vụ tạo báo cáo hoặc xử lý CPU nặng trong thời gian dài | Worker/task queue, API 202 khi phù hợp | Không giữ request hay event-loop trong suốt tác vụ |

Quyết định cần dựa trên **throughput, p99, độ ổn định, số kết nối, độ phức tạp migration, kỹ năng nhóm và vận hành thực tế**. Không có một mô hình thắng mọi workload.

## 12. Kịch bản kiểm thử trước khi chuyển stack

1. **Đường thành công:** endpoint trả đúng dữ liệu, trace hiển thị được mọi dependency và thread model.
2. **Downstream chậm:** tăng latency DB/API có kiểm soát; đo event-loop lag, p95/p99, thời gian hàng đợi, số request in-flight.
3. **Connection pool cạn:** giảm tạm pool cho thử nghiệm; xác nhận timeout, hạn chế concurrency và lỗi có thể kiểm soát.
4. **Tải đồng thời tăng:** so sánh MVC/WebFlux với cùng CPU/RAM, cùng workload, cùng pool/timeout; quan sát thread, CPU và memory.
5. **Hủy request giữa chừng:** client timeout/disconnect; xem công việc sync có tiếp tục và có thu hồi tài nguyên đúng không.
6. **Sự cố upstream:** mô phỏng 5xx, mất mạng, DNS chậm, retry storm; kiểm tra backoff, circuit breaker, bulkhead và khả năng phục hồi.
7. **Thử cùng giao dịch:** xác nhận không mất transaction hoặc security/tracing context khi chuyển scheduler.

Không suy luận từ một benchmark “hello world”. Nếu migration đồng thời đổi cả driver DB và cấu hình pool, ghi rõ kết quả là tác động tổng hợp của nhiều thay đổi.

## 13. Các lỗi thiết kế thường gặp

- **Chỉ thêm Mono/Flux:** không kiểm tra JPA hoặc HTTP client bên dưới.
- **Gọi `block()` trên event loop:** biến một pipeline reactive thành điểm chờ đồng bộ.
- **Tin rằng async API chắc chắn non-blocking:** bỏ qua việc thư viện đang dùng executor để chạy blocking call.
- **Đưa mọi việc lên boundedElastic:** không giám sát queue, số worker và connection pool, dẫn đến nghẽn mới.
- **Dùng parallel scheduler cho I/O chặn lâu:** làm giảm năng lực xử lý của scheduler CPU.
- **Đánh mất transaction/context khi đổi thread:** logic nghiệp vụ có thể sai dù endpoint vẫn trả phản hồi.
- **Dựa vào BlockHound như bằng chứng duy nhất:** bỏ sót driver, SDK hoặc đường code không được instrument.
- **Nhầm CPU-bound với I/O-bound:** công việc nén/hash/report chiếm CPU và vẫn phải tránh chặn event-loop.
- **Không thử tải khi phụ thuộc chậm:** bỏ sót lỗi chỉ xuất hiện khi DB pool hoặc API outbound gần ngưỡng.
- **Cho rằng virtual threads không còn giới hạn:** DB, sockets, CPU và remote rate limit vẫn là nút cổ chai.

## 14. Checklist trước khi chốt WebFlux hay MVC

- [ ] Đã liệt kê endpoint quan trọng và mọi dependency trên đường xử lý.
- [ ] Đã phân loại API theo blocking, async wrapper và non-blocking thật sự.
- [ ] Đã kiểm tra JDBC/JPA, HTTP sync client, Redis, cloud SDK, filesystem, security và CPU-heavy work.
- [ ] Đã tìm lời gọi blocking nằm trong filter, handler, operator và callback của WebFlux.
- [ ] Đã xác minh driver và API reactive tương thích với yêu cầu transaction/feature.
- [ ] Đã có phương án cho thư viện sync: giữ MVC, thay API hoặc cô lập bằng scheduler có giới hạn.
- [ ] Đã kiểm tra ThreadLocal, MDC, security, tracing và `@Transactional` qua async boundary.
- [ ] Đã cấu hình timeout, bounded concurrency, connection pool, retry và error handling.
- [ ] Đã đo throughput, p95/p99, event-loop, scheduler/pool saturation và lỗi khi phụ thuộc chậm.
- [ ] Đã lưu lại giả định, quyết định kỹ thuật, dữ liệu kiểm thử và tiêu chí xem xét lại.

## 15. Kết luận

**Chọn mô hình reactive chỉ sau khi đã đánh giá hành vi thực của các thư viện trên toàn bộ đường I/O.** Spring WebFlux có thể mang lợi ích lớn khi các thành phần quan trọng non-blocking và workload có nhiều kết nối chờ; Spring MVC phù hợp khi persistence và SDK chủ yếu đồng bộ. Có thể dùng boundedElastic cho số ít thư viện blocking cần giữ lại, nhưng phải tính pool, timeout, cancellation, context và transaction như tài nguyên hữu hạn. Kết quả đo dưới tải đại diện là cơ sở cuối cùng để chọn stack.