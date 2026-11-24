# Fallback luôn chạy do TimeLimiter mặc định hoặc hàng đợi đầy

Khi một endpoint liên tục trả về fallback dù dịch vụ phía sau vẫn khỏe, nguyên nhân có thể nằm ở chính sách bảo vệ phía caller. Hai nguyên nhân thường gặp là TimeLimiter đang dùng timeout mặc định ngắn hơn thời gian phản hồi thực tế, hoặc ThreadPoolBulkhead đã hết cả worker lẫn chỗ trống trong hàng đợi. Cả hai đều có thể khiến lời gọi được chuyển sang fallback trước khi caller nhận được kết quả bình thường.

Cần phân biệt hai tình huống này. Timeout thường có nghĩa tác vụ đã được bắt đầu nhưng không hoàn tất trong thời hạn. Hàng đợi đầy thường có nghĩa tác vụ mới bị từ chối trước khi Supplier gốc được chạy. Nếu chỉ nhìn response fallback, nhóm phát triển dễ kết luận dependency đang lỗi hoặc Circuit Breaker đã OPEN, trong khi nguyên nhân thực tế là timeout hoặc giới hạn concurrency cục bộ.

Bài học này hướng dẫn cách truy tìm cấu hình TimeLimiter hiệu lực, nhận diện queue saturation, đọc exception và event, điều chỉnh timeout cùng thread pool, và viết kiểm thử để xác nhận fallback chỉ chạy khi đúng điều kiện.

## 1. Vì sao fallback có thể xuất hiện ở mọi request?

Fallback là nhánh xử lý thay thế khi lời gọi được bảo vệ kết thúc bằng lỗi mà adapter chuyển đến hàm fallback. Lỗi đó không nhất thiết đến từ remote service.

Một lời gọi có thể đi vào fallback do:

- Circuit Breaker đang OPEN và từ chối request bằng CallNotPermittedException.
- TimeLimiter hết thời gian chờ và phát sinh timeout.
- ThreadPoolBulkhead không nhận được task vì worker và queue đã đầy.
- Semaphore Bulkhead hết permit.
- HTTP client phát sinh lỗi kết nối hoặc response.
- Chính code trong Supplier phát sinh exception.

Vì vậy, fallback chạy không chứng minh Circuit Breaker đang OPEN. Circuit Breaker có thể vẫn CLOSED trong khi TimeLimiter hoặc Bulkhead từ chối lời gọi. Nếu fallback luôn chạy, hãy lấy exception gốc và event của từng policy trước khi thay đổi ngưỡng failure rate.

~~~mermaid
flowchart TD
    A[Request vào Circuit Breaker] --> B{Admission và trạng thái}
    B -- Circuit Breaker OPEN --> C[CallNotPermittedException]
    B -- Bulkhead queue đầy --> D[BulkheadFullException]
    B -- Được nhận --> E[Supplier bắt đầu]
    E --> F{Hoàn tất trong timeout?}
    F -- Không --> G[TimeoutException]
    F -- Có --> H[Kết quả hoặc lỗi HTTP]
    C --> I[Fallback]
    D --> I
    G --> I
    H --> J{Kết quả thành công?}
    J -- Không --> I
    J -- Có --> K[Trả kết quả gốc]
~~~

Sơ đồ cho thấy ba nguyên nhân từ chối khác nhau có thể cùng dẫn đến fallback. Cần chẩn đoán theo loại lỗi và trạng thái thực tế, không dựa riêng vào body response.

## 2. Nhận diện fallback do TimeLimiter

TimeLimiter giới hạn thời gian chờ một thao tác bất đồng bộ hoàn tất. Nếu thao tác vượt timeoutDuration, lời gọi được xem là timeout và fallback có thể được gọi.

Ví dụ, dịch vụ inventory thường phản hồi trong 1,5 giây nhưng cấu hình TimeLimiter hiệu lực chỉ cho phép 1 giây. Hầu hết request sẽ timeout dù Inventory Service vẫn trả kết quả bình thường sau 1,5 giây.

Triệu chứng thường gặp:

- Supplier hoặc tác vụ HTTP đã bắt đầu.
- Log có thời điểm bắt đầu lời gọi nhưng không có kết quả trước deadline.
- Exception hoặc event thể hiện timeout.
- Thời gian caller nhận fallback gần bằng timeoutDuration.
- Tác vụ nền hoặc HTTP request có thể vẫn tiếp tục sau khi caller đã nhận fallback, tùy cơ chế cancellation.

Một ví dụ cấu hình rõ ràng:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
        cancelRunningFuture: true
~~~

Trong ví dụ, caller chờ tối đa ba giây cho thao tác thuộc instance inventory. cancelRunningFuture yêu cầu hủy Future khi timeout. Việc hủy có dừng tác vụ thực tế hay không còn phụ thuộc Future, executor và HTTP client; không nên xem thuộc tính này là cam kết rằng server đã ngừng xử lý.

## 3. Kiểm tra timeout hiệu lực thay vì chỉ nhìn file cấu hình

Một ứng dụng có thể không khai báo timeoutDuration cho instance nhưng vẫn nhận timeout từ cấu hình mặc định. Giá trị hiệu lực có thể đến từ:

- Cấu hình mặc định của thư viện hoặc adapter.
- Nhóm cấu hình configs/default.
- Instance cụ thể trong application.yml.
- Java Customizer cấu hình mặc định cho factory.
- Java Customizer cấu hình riêng cho một ID.
- Profile đang chạy hoặc cấu hình môi trường được nạp bên ngoài.

Giá trị mặc định cụ thể thay đổi theo phiên bản và cách tích hợp. Không nên giả định mọi ứng dụng Spring Cloud CircuitBreaker đều có cùng một timeout mặc định. Hãy kiểm tra dependency version, cấu hình profile đang hoạt động và cấu hình instance mà factory thực sự sử dụng.

Ví dụ định nghĩa cấu hình mặc định và ghi đè riêng cho inventory:

~~~yaml
resilience4j:
  timelimiter:
    configs:
      default:
        timeoutDuration: 4s
        cancelRunningFuture: true
    instances:
      inventory:
        baseConfig: default
        timeoutDuration: 6s
      payment:
        baseConfig: default
        timeoutDuration: 2s
~~~

Trong cấu hình này, inventory có timeout sáu giây, payment có timeout hai giây; cả hai kế thừa chính sách cancelRunningFuture từ default.

Nếu Java Customizer cũng cấu hình TimeLimiter, hãy xác minh thứ tự và quy tắc ưu tiên giữa customizer và properties của phiên bản đang dùng. Không chỉ sửa một file YAML rồi cho rằng cấu hình mới chắc chắn được áp dụng.

Nên ghi nhận ID breaker, timeout dự kiến và thời gian thực tế trong log khởi động hoặc metric cấu hình. Khi cần, bật endpoint quan sát cấu hình của Spring Boot trong môi trường được bảo vệ và kiểm tra các property đã được bind. Không công khai endpoint quản trị hoặc thông tin cấu hình nhạy cảm ra Internet.

## 4. Cấu hình TimeLimiter bằng Java

Spring Cloud CircuitBreaker với Resilience4j cho phép tạo cấu hình bằng Resilience4JConfigBuilder:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryTimeout() {
        return factory -> factory.configure(
                builder -> builder
                        .timeLimiterConfig(
                                TimeLimiterConfig.custom()
                                        .timeoutDuration(Duration.ofSeconds(6))
                                        .cancelRunningFuture(true)
                                        .build()
                        )
                        .circuitBreakerConfig(
                                CircuitBreakerConfig.ofDefaults()
                        )
                        .build(),
                "inventory"
        );
    }
}
~~~

Cấu hình này đặt timeout sáu giây cho ID inventory. Nếu lời gọi inventory có thời gian phản hồi p99 khoảng bốn giây, sáu giây có thể là điểm bắt đầu để đánh giá; cần tính thêm deadline của request bên ngoài và ngân sách cho các bước sau.

Có thể đặt cấu hình mặc định cho tất cả ID bằng configureDefault, rồi cấu hình riêng các ID có SLA khác biệt. Tránh dùng một timeout quá ngắn cho tất cả dependency chỉ vì một dependency có phản hồi nhanh.

TimeLimiter thường được áp dụng rõ ràng cho lời gọi dựa trên Future hoặc CompletionStage. Với API đồng bộ trả T trực tiếp và với reactive Mono/Flux, cách adapter áp dụng giới hạn thời gian có thể khác. Hãy xác định đúng overload và implementation đang dùng trước khi kết luận TimeLimiter nào đang bọc lời gọi.

## 5. Phân biệt timeout của caller với thời gian HTTP thực tế

Ví dụ lời gọi trả CompletionStage:

~~~java
CompletionStage<Inventory> result = circuitBreaker.run(
        () -> CompletableFuture.supplyAsync(
                () -> inventoryClient.fetch(sku),
                inventoryExecutor
        ),
        error -> CompletableFuture.completedFuture(
                Inventory.unavailable(sku)
        )
);
~~~

TimeLimiter có thể hoàn tất nhánh caller bằng timeout khi CompletionStage chưa hoàn thành trong thời hạn. Tuy nhiên, CompletableFuture.cancel(true) không bảo đảm interrupt computation đang chạy. HTTP client cũng có thể tiếp tục xử lý I/O nếu cancellation không truyền xuống transport.

Khi điều tra, hãy ghi ít nhất ba mốc:

1. Supplier hoặc HTTP request bắt đầu.
2. Caller nhận timeout và fallback.
3. Tác vụ nền hoặc HTTP response thực sự kết thúc.

Nếu mốc 2 xuất hiện trước mốc 3, công việc vẫn tiếp tục sau timeout. Điều này có thể làm thread pool và connection pool bị chiếm dụng dù caller đã nhận fallback.

Không retry ngay chỉ vì caller timeout nếu chưa xác định request trước đã được server xử lý hay chưa. Với thao tác tạo đơn hàng hoặc thanh toán, cần idempotency key và cơ chế tra cứu trạng thái để tránh side effect trùng lặp.

## 6. Nhận diện fallback do ThreadPoolBulkhead queue đầy

ThreadPoolBulkhead giới hạn số tác vụ có thể chạy đồng thời và số tác vụ được phép chờ. Khi tất cả worker đang bận và hàng đợi đã đạt queueCapacity, tác vụ mới bị từ chối.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 12
        keepAliveDuration: 20ms
~~~

Trong ví dụ:

- Pool có tối thiểu bốn worker.
- Pool có thể mở rộng đến tám worker.
- Tối đa mười hai task được xếp hàng chờ theo queueCapacity.
- Khi worker đã bận và queue đầy, task mới có thể bị từ chối bằng BulkheadFullException.

Một task bị từ chối do queue đầy thường chưa bắt đầu chạy. Vì vậy, bộ đếm đặt bên trong Supplier có thể vẫn bằng 0, trong khi fallback được gọi ngay.

Triệu chứng thường gặp:

- Fallback xuất hiện rất nhanh, ngắn hơn timeoutDuration.
- Exception là BulkheadFullException hoặc lỗi từ chối tương ứng của adapter.
- Queue depth chạm queueCapacity.
- Worker đang hoạt động gần maxThreadPoolSize.
- Supplier gốc không bắt đầu đối với request bị từ chối.
- Remote service có thể vẫn khỏe nhưng caller không còn slot cục bộ để gửi request.

Đây là dấu hiệu quá tải hoặc giới hạn admission control ở ứng dụng caller. Tăng timeoutDuration không giải quyết queue đầy. Tăng queueCapacity cũng không làm dependency xử lý nhanh hơn; nó chỉ cho phép nhiều request chờ hơn và có thể làm latency tăng.

## 7. Phân biệt ThreadPoolBulkhead với Semaphore Bulkhead

Không phải mọi Bulkhead đều có hàng đợi:

| Cơ chế | Tài nguyên được giới hạn | Khi hết giới hạn |
|---|---|---|
| ThreadPoolBulkhead | Worker thread và queue task | Từ chối khi worker và queue đều đầy |
| Semaphore Bulkhead | Số permit lời gọi đồng thời | Từ chối hoặc chờ permit theo maxWaitDuration |
| HTTP connection pool | Connection và request chờ acquire | Chờ connection hoặc phát sinh acquire timeout/rejection |

Nếu ứng dụng đang dùng Semaphore Bulkhead, không có queue worker như ThreadPoolBulkhead. Lỗi từ chối có thể vẫn làm fallback chạy, nhưng nguyên nhân là hết permit chứ không phải queueCapacity.

Spring Cloud CircuitBreaker với Resilience4j có thể chọn default Bulkhead implementation theo cấu hình và phiên bản. Một số phiên bản cho phép bật Semaphore Bulkhead mặc định bằng thuộc tính:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Hãy xác nhận thuộc tính này được hỗ trợ trong phiên bản Spring Cloud đang dùng. Nếu bật Semaphore Bulkhead, các cấu hình thread-pool như coreThreadPoolSize và queueCapacity không còn là cơ chế giới hạn mặc định cho lời gọi đó.

Không nên điều chỉnh queueCapacity khi ứng dụng thực tế đang dùng Semaphore Bulkhead. Trước tiên phải xác định loại Bulkhead được tạo cho ID đó.

## 8. Đọc exception và event để phân biệt hai nguyên nhân

Cần ghi nhận loại exception và event từ từng policy. Bảng sau là gợi ý chẩn đoán; tên wrapper hoặc exception cụ thể có thể khác theo adapter và phiên bản:

| Dấu hiệu | TimeLimiter timeout | ThreadPoolBulkhead queue đầy |
|---|---|---|
| Exception thường gặp | TimeoutException hoặc wrapper timeout | BulkheadFullException hoặc rejection exception |
| Supplier bắt đầu? | Thường có | Thường không với task bị từ chối |
| Thời gian đến fallback | Gần timeoutDuration | Thường rất nhanh khi queue đã đầy |
| Queue depth | Có thể bình thường | Đạt queueCapacity |
| Worker active | Có thể bình thường hoặc cao | Thường đạt giới hạn |
| HTTP request | Có thể đã gửi | Thường chưa gửi cho task bị từ chối |
| Cách xử lý chính | Điều chỉnh deadline hoặc giảm latency | Điều chỉnh concurrency, pool, queue và admission control |

Có thể đăng ký listener cho Circuit Breaker và Bulkhead để ghi nhận event. Ví dụ với Resilience4j core:

~~~java
bulkhead.getEventPublisher()
        .onCallRejected(event ->
                log.warn("Bulkhead rejected call: name={}",
                        event.getBulkheadName()));

circuitBreaker.getEventPublisher()
        .onCallNotPermitted(event ->
                log.warn("Circuit breaker rejected call: name={}",
                        event.getCircuitBreakerName()));
~~~

Với ThreadPoolBulkhead, dùng event publisher và metric tương ứng của implementation đang chạy để theo dõi task được nhận, task hoàn tất và task bị từ chối. API listener cụ thể khác với Semaphore Bulkhead; hãy dùng đúng interface của loại instance.

Đối với TimeLimiter, theo dõi số lần timeout và thời gian hoàn tất của CompletionStage. Gắn operation ID hoặc correlation ID để liên kết log từ lúc bắt đầu đến lúc fallback và lúc tác vụ nền thực sự kết thúc.

## 9. Kiểm tra thứ tự policy và lỗi cục bộ

Các decorator có thể được lắp theo thứ tự khác nhau tùy factory, customizer và implementation. Thứ tự quyết định lớp nào nhận exception trước và metric nào ghi nhận lỗi.

Ví dụ, Bulkhead rejection là lỗi admission control cục bộ. Nó không nhất thiết chứng minh Inventory Service bị lỗi. Nếu exception từ Bulkhead đi vào Circuit Breaker và bị ghi nhận như lỗi remote, failure rate có thể tăng và breaker có thể OPEN dù dependency vẫn khỏe.

Cần kiểm tra:

- Bulkhead được áp dụng trước hay sau Circuit Breaker.
- TimeLimiter bắt đầu tính thời gian trước hay sau khi task vào queue.
- BulkheadFullException có bị Circuit Breaker ghi nhận là failure hay được bỏ qua.
- Fallback được gắn ở tầng nào.
- Retry có thử lại lỗi queue đầy hoặc CallNotPermittedException hay không.

Không retry ngay một BulkheadFullException. Retry có thể làm tăng thêm số task chờ và khiến queue càng khó phục hồi. Cũng không retry CallNotPermittedException trong khi breaker đang OPEN, vì lời gọi sẽ tiếp tục bị từ chối.

Nếu muốn lỗi cục bộ không ảnh hưởng failure rate của remote dependency, hãy điều chỉnh thứ tự decorator hoặc exception classification theo API phiên bản đang dùng. Kiểm chứng bằng event và metric thay vì chỉ dựa vào thứ tự khai báo trong YAML.

## 10. Điều chỉnh timeout theo latency và deadline

Timeout nên được chọn dựa trên SLA và phân phối latency thực tế. Không nên đặt timeout bằng latency trung bình vì một tỷ lệ đáng kể request có thể chậm hơn trung bình.

Một cách tiếp cận:

1. Đo p50, p95 và p99 của dependency trong điều kiện tải bình thường và tải cao.
2. Xác định deadline tổng thể mà caller phải đáp ứng.
3. Dành ngân sách cho các bước trước và sau lời gọi dependency.
4. Đặt timeout của HTTP client và TimeLimiter trong deadline còn lại.
5. Kiểm thử khi dependency chậm hơn timeout để quan sát fallback và cancellation.
6. Theo dõi tỷ lệ timeout sau khi triển khai và điều chỉnh theo dữ liệu.

Ví dụ caller có deadline 5 giây. Nếu bước xác thực và xử lý response cần khoảng 500 mili giây, ngân sách cho dependency có thể khoảng 4 giây. Nếu Retry có thêm khoảng chờ, tổng thời gian retry cũng phải nằm trong ngân sách này.

Cần thống nhất timeout ở các tầng. Connect timeout, response timeout, read timeout và TimeLimiter không đo cùng một khoảng thời gian. Nếu TimeLimiter ngắn hơn HTTP client timeout, caller có thể nhận fallback trong khi HTTP request vẫn còn chạy.

## 11. Điều chỉnh ThreadPoolBulkhead và queueCapacity

Pool cần đủ worker để xử lý concurrency mục tiêu nhưng không được vượt khả năng chịu tải của dependency và tài nguyên JVM.

Một quy trình điều chỉnh:

- Đo thời gian xử lý trung bình và p95/p99 của task.
- Ước lượng concurrency cần thiết theo lưu lượng và latency.
- Đặt coreThreadPoolSize và maxThreadPoolSize theo ngân sách thread của ứng dụng.
- Đặt queueCapacity hữu hạn và phù hợp với deadline caller.
- Theo dõi queue wait time, queue depth và số lần rejection.
- Kiểm tra HTTP connection pool có đủ năng lực cho số worker hoạt động hay không.
- Giảm queue hoặc từ chối sớm nếu request chờ quá lâu sẽ hết deadline trước khi chạy.

Có thể ước lượng concurrency trung bình bằng định luật Little:

\[
L = \lambda \times W
\]

Nếu dependency nhận 30 request mỗi giây và mỗi request mất trung bình 200 mili giây:

\[
L = 30 \times 0.2 = 6
\]

Có khoảng sáu lời gọi đồng thời trung bình. Đây chỉ là điểm xuất phát; cần xét biến động latency và burst traffic để chọn pool. Không tăng maxThreadPoolSize vô hạn vì thread tăng có thể làm context switching, bộ nhớ stack và áp lực lên downstream tăng.

Queue nên chứa số lượng task có thể hoàn tất trong deadline. Một queue lớn có thể làm request chờ lâu rồi timeout, khiến fallback vẫn chạy nhưng tài nguyên đã bị giữ trong thời gian dài.

## 12. Kết hợp TimeLimiter với ThreadPoolBulkhead

Khi cả TimeLimiter và ThreadPoolBulkhead được bật, một task có thể gặp hai điều kiện:

- Không được nhận vào pool vì queue đầy.
- Được nhận vào pool nhưng không hoàn tất trong thời hạn.

Hai điều kiện tạo exception khác nhau và cần được theo dõi riêng.

Ví dụ cấu hình theo dependency:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 4s
        cancelRunningFuture: true

  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 6
        maxThreadPoolSize: 10
        queueCapacity: 8
        keepAliveDuration: 20ms
~~~

Cấu hình này chỉ là ví dụ. Nếu queue đầy, task có thể bị từ chối ngay mà không cần đợi bốn giây. Nếu task được nhận nhưng mất hơn bốn giây, TimeLimiter có thể kích hoạt fallback.

Hãy kiểm thử cả hai đường đi:

- Làm tất cả worker bận và lấp đầy queue để xác nhận rejection.
- Cho một task được nhận nhưng cố ý chậm hơn timeout để xác nhận timeout.

Không dùng một bài test chung rồi chỉ assert fallback được gọi. Cần assert loại exception, Supplier có bắt đầu hay không, queue state và thời gian phản hồi.

## 13. Kiểm tra trong reactive application

Với WebFlux và Reactor, cần xác định adapter reactive thực sự áp dụng timeout và Bulkhead như thế nào. Reactive pipeline thường không dùng ThreadPoolBulkhead để điều phối mọi request WebClient; Semaphore Bulkhead và toán tử Reactor phù hợp hơn cho giới hạn concurrency không blocking.

Ví dụ timeout trực tiếp trên Mono:

~~~java
Mono<Inventory> remoteCall = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(Inventory.class)
        .timeout(Duration.ofSeconds(3));

return reactiveCircuitBreaker.run(
        remoteCall,
        error -> Mono.just(Inventory.unavailable(sku))
);
~~~

Ở đây Reactor timeout phát tín hiệu lỗi nếu publisher không phát kết quả trong thời hạn. Fallback của ReactiveCircuitBreaker có thể nhận lỗi đó. Cần xác minh timeout được đặt ở đâu trong chuỗi và adapter có thêm TimeLimiter riêng hay không để tránh hai timeout cạnh tranh.

Nếu dùng Semaphore Bulkhead cho reactive call, theo dõi permit bị từ chối. Nếu dùng ThreadPoolBulkhead để chạy tác vụ blocking, tách riêng phần blocking và giới hạn worker; không chuyển toàn bộ WebClient pipeline sang thread pool chỉ để né queue saturation.

Với reactive, phân biệt:
- Publisher không được subscribe do policy từ chối.
- Publisher đã subscribe nhưng phát timeout.
- Publisher bị cancel sau khi caller timeout.
- HTTP exchange bị hủy hoặc server vẫn tiếp tục xử lý.

Các trường hợp này có tác động khác nhau đến tài nguyên và cần metric riêng.

## 14. Kiểm thử để xác định đúng nguyên nhân

Nên có hai test độc lập.

### Test TimeLimiter

- Tạo CompletionStage có thời gian hoàn thành dài hơn timeoutDuration.
- Ghi bộ đếm khi Supplier bắt đầu.
- Ghi thời điểm caller nhận fallback.
- Xác nhận exception hoặc event là timeout.
- Xác nhận Supplier đã bắt đầu.
- Quan sát tác vụ nền có tiếp tục sau fallback hay không.

Ví dụ giả lập:

~~~java
AtomicInteger supplierCalls = new AtomicInteger();

CompletionStage<String> result = circuitBreaker.run(
        () -> CompletableFuture.supplyAsync(() -> {
            supplierCalls.incrementAndGet();
            sleepUninterruptiblyForTest(Duration.ofSeconds(5));
            return "remote-result";
        }, executor),
        error -> CompletableFuture.completedFuture("fallback")
);
~~~

Đây là ví dụ khái niệm; helper sleepUninterruptiblyForTest chỉ nên tồn tại trong test. Dùng một executor và thời gian điều khiển được để test không phụ thuộc tải máy. Không dùng đoạn code giả lập này trong production.

### Test ThreadPoolBulkhead queue đầy

- Cấu hình một worker và queue capacity bằng một.
- Giữ worker đầu tiên bằng một latch.
- Gửi task thứ hai để lấp đầy queue.
- Gửi task thứ ba và xác nhận bị từ chối.
- Đặt bộ đếm trong Supplier thứ ba và xác nhận nó bằng 0.
- Xác nhận fallback được gọi do lỗi rejection.
- Nhả latch và dọn executor sau test.

~~~java
CountDownLatch releaseWorker = new CountDownLatch(1);
AtomicInteger rejectedSupplierCalls = new AtomicInteger();

CompletableFuture<String> first = submit(() -> {
    releaseWorker.await();
    return "first";
});

CompletableFuture<String> second = submit(() -> "second");

CompletableFuture<String> third = submit(() -> {
    rejectedSupplierCalls.incrementAndGet();
    return "third";
});

// Xác nhận task thứ ba bị từ chối và Supplier thứ ba chưa chạy.
releaseWorker.countDown();
~~~

Hàm submit trong ví dụ đại diện cho lời gọi đi qua ThreadPoolBulkhead đã cấu hình. Trong test thật, dùng API factory hoặc ThreadPoolBulkhead instance và đồng bộ hóa bằng latch để bảo đảm worker cùng queue đã ở trạng thái mong muốn trước khi gửi task thứ ba.

Không dùng Thread.sleep để đoán queue đã đầy. Dùng latch, barrier hoặc tín hiệu event để kiểm soát thứ tự. Dọn tài nguyên trong finally để test không để lại worker bị treo.

## 15. Checklist chẩn đoán khi fallback luôn chạy

Khi fallback xuất hiện gần như mọi request, hãy thu thập bằng chứng theo thứ tự:

1. Ghi exception class và cause chain nhận được trong fallback.
2. Ghi ID Circuit Breaker, TimeLimiter và Bulkhead.
3. Xác nhận state của Circuit Breaker là CLOSED, OPEN hay HALF_OPEN.
4. Đo thời gian từ lúc bắt đầu lời gọi đến lúc fallback.
5. So sánh thời gian đó với timeoutDuration hiệu lực.
6. Kiểm tra Supplier có bắt đầu hay không.
7. Kiểm tra ThreadPoolBulkhead worker active, queue depth, queueCapacity và rejection count.
8. Kiểm tra semaphore permits nếu dùng Semaphore Bulkhead.
9. Kiểm tra HTTP connection pool và thời gian chờ acquire.
10. Đối chiếu event của TimeLimiter, Bulkhead và Circuit Breaker.
11. Xác nhận thứ tự decorator để biết policy nào phát exception và policy nào ghi nhận failure.
12. Chạy lại hai tình huống riêng biệt: task chậm và queue đầy.

Bảng quyết định nhanh:

| Quan sát | Nguyên nhân có khả năng | Hành động tiếp theo |
|---|---|---|
| Fallback sau gần đúng timeoutDuration, Supplier đã bắt đầu | TimeLimiter | Kiểm tra timeout hiệu lực và latency |
| Fallback gần như tức thì, Supplier chưa bắt đầu, queue đạt capacity | ThreadPoolBulkhead | Kiểm tra worker, queue và admission limit |
| CallNotPermittedException, breaker OPEN | Circuit Breaker | Điều tra failure rate và thời gian mở |
| BulkheadFullException nhưng remote khỏe | Giới hạn cục bộ | Điều chỉnh concurrency hoặc giảm tải |
| PoolAcquireTimeoutException | HTTP connection pool | Kiểm tra maxConnections và pending acquire |
| Fallback tự phát sinh exception | Chính fallback lỗi | Điều tra dependency và code fallback |

## 16. Những lỗi thường gặp

- **Chỉ tăng timeout mà không kiểm tra queue**: queue đầy vẫn từ chối ngay.
- **Chỉ tăng queueCapacity**: request có thể chờ lâu hơn rồi vẫn timeout.
- **Cho rằng fallback luôn có nghĩa Circuit Breaker OPEN**: TimeLimiter và Bulkhead cũng có thể kích hoạt fallback.
- **Dùng timeout mặc định mà không kiểm tra phiên bản**: cấu hình hiệu lực có thể khác giữa adapter và release.
- **Không đồng bộ timeout giữa HTTP client và TimeLimiter**: caller nhận fallback trong khi HTTP request còn chạy.
- **Nhầm ThreadPoolBulkhead với Semaphore Bulkhead**: một loại có worker/queue, loại kia giới hạn permit.
- **Retry BulkheadFullException**: làm tăng áp lực lên queue đang đầy.
- **Tính lỗi admission control vào failure rate remote**: Circuit Breaker có thể mở dù dependency khỏe.
- **Để queue quá lớn**: tăng thời gian chờ và giữ request đã hết deadline.
- **Không đo Supplier start**: khó phân biệt timeout sau khi chạy với rejection trước khi chạy.
- **Không kiểm tra cancellation**: task nền tiếp tục chiếm tài nguyên sau khi caller đã nhận fallback.
- **Chỉ kiểm thử response fallback**: chưa chứng minh nguyên nhân nào đã kích hoạt fallback.

## 17. Quy trình xử lý và phòng ngừa

Khi xử lý lỗi fallback luôn chạy trong Spring Cloud CircuitBreaker với Resilience4j:

1. Thu thập exception gốc, event và ID của từng policy.
2. Xác định fallback do timeout, queue rejection, semaphore rejection hay Circuit Breaker OPEN.
3. Kiểm tra cấu hình TimeLimiter hiệu lực từ default, baseConfig, instance, profile và Java Customizer.
4. So sánh timeout với p95/p99 latency và deadline tổng thể.
5. Xác định Bulkhead implementation đang dùng trước khi điều chỉnh queue hoặc permit.
6. Nếu ThreadPoolBulkhead queue đầy, kiểm tra worker active, queue depth, queueCapacity và thời gian chờ.
7. Tinh chỉnh concurrency, queue hữu hạn, HTTP connection pool và admission control theo năng lực dependency.
8. Không retry lỗi rejection hoặc CallNotPermittedException một cách mù quáng.
9. Kiểm thử riêng task vượt timeout và task bị từ chối do queue đầy.
10. Theo dõi fallback count cùng nguyên nhân, timeout rate, rejection rate và thời gian tác vụ thực sự kết thúc.

Fallback là kết quả chung của nhiều đường lỗi. TimeLimiter có thể kích hoạt fallback khi thao tác vượt thời hạn; ThreadPoolBulkhead có thể kích hoạt fallback khi không còn worker hoặc queue slot để nhận task. Phân biệt hai nguyên nhân bằng exception, thời gian phản hồi, trạng thái Supplier và metric queue giúp điều chỉnh đúng chính sách, giữ cho Circuit Breaker phản ánh sức khỏe dependency thay vì nhầm lẫn với giới hạn tài nguyên cục bộ.
