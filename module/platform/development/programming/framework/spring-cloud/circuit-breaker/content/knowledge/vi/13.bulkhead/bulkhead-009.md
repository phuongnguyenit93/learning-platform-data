# Đặt giới hạn theo từng phụ thuộc và phối hợp với HTTP connection pool

Bulkhead giới hạn số thao tác được phép chạy đồng thời để một dependency chậm không chiếm hết tài nguyên của ứng dụng. HTTP connection pool lại quản lý số kết nối mạng có thể được cấp cho các request và số request phải chờ kết nối. Hai cơ chế cùng bảo vệ lời gọi ra ngoài nhưng kiểm soát hai loại tài nguyên khác nhau.

Trong Spring Cloud CircuitBreaker với Resilience4j, nên đặt giới hạn Bulkhead theo từng dependency và cấu hình HTTP connection pool tương ứng. Nếu Bulkhead cho phép nhiều request hơn số kết nối có thể phục vụ, request sẽ tiếp tục xếp hàng trong pool. Nếu pool có nhiều kết nối hơn giới hạn Bulkhead, Bulkhead sẽ là điểm admission control chính. Cấu hình phối hợp giúp giới hạn concurrency, tránh hàng đợi ẩn và giữ tài nguyên cho các dependency khác.

## 1. Bulkhead cô lập concurrency theo dependency

Giả sử một dịch vụ tổng hợp gọi ba dependency: tồn kho, thanh toán và gợi ý sản phẩm. Dịch vụ gợi ý có thể phản hồi chậm trong giờ cao điểm. Nếu tất cả lời gọi dùng chung một nhóm tài nguyên không có giới hạn, các request đang chờ gợi ý có thể chiếm nhiều thread hoặc connection và ảnh hưởng đến lời gọi thanh toán.

Bulkhead tạo giới hạn riêng cho từng nhóm lời gọi. Ví dụ:

- Inventory được phép tối đa 20 lời gọi đồng thời.
- Payment được phép tối đa 8 lời gọi đồng thời.
- Recommendation được phép tối đa 5 lời gọi đồng thời.

Khi recommendation đã sử dụng hết 5 slot, request mới đến recommendation bị từ chối hoặc chờ theo chính sách đã cấu hình. Những slot dành cho inventory và payment vẫn còn khả dụng.

~~~mermaid
flowchart TD
    A[Service gọi các dependency] --> B{Phân loại theo dependency}
    B --> C[Inventory Bulkhead: tối đa 20]
    B --> D[Payment Bulkhead: tối đa 8]
    B --> E[Recommendation Bulkhead: tối đa 5]
    C --> F[Inventory HTTP pool]
    D --> G[Payment HTTP pool]
    E --> H[Recommendation HTTP pool]
    F --> I[Inventory service]
    G --> J[Payment service]
    H --> K[Recommendation service]
~~~

Điểm quan trọng là giới hạn được gắn với dependency hoặc nhóm thao tác có đặc tính vận hành tương tự. Không nên tạo một Bulkhead cho mỗi request vì số lượng instance và tài nguyên quản lý sẽ tăng không kiểm soát.

## 2. Bulkhead và HTTP connection pool kiểm soát hai giới hạn khác nhau

Bulkhead kiểm soát số thao tác đang được phép đi tiếp trong ứng dụng. HTTP connection pool kiểm soát số kết nối mà HTTP client có thể cấp cho các request đến một remote host.

| Cơ chế | Giới hạn chính | Khi hết giới hạn |
|---|---|---|
| Semaphore Bulkhead | Số lời gọi đang giữ permit | Từ chối ngay hoặc chờ permit trong thời gian tối đa |
| Thread-pool Bulkhead | Số worker và dung lượng hàng đợi của pool | Từ chối khi worker và queue đều đầy |
| HTTP connection pool | Số connection có thể cấp cho request | Request chờ connection hoặc bị từ chối khi hàng đợi đạt giới hạn |
| Circuit Breaker | Khả năng tiếp tục gọi dependency dựa trên kết quả gần đây | Chuyển OPEN và từ chối lời gọi mới trong thời gian chờ |

Một request có thể đã lấy được permit Bulkhead nhưng vẫn phải chờ connection trong HTTP pool. Khi đó, request đang chiếm slot Bulkhead mà chưa gửi được dữ liệu đến server. Nếu pool thường xuyên thiếu connection, thời gian chờ này làm giảm số slot còn lại cho request mới.

Ngược lại, nếu pool có nhiều connection nhưng Bulkhead chỉ cho phép ít request đồng thời, số connection tối đa của pool có thể không được sử dụng hết. Đây không nhất thiết là vấn đề: Bulkhead có thể đang chủ động giới hạn tải theo khả năng chịu đựng của dependency.

Với HTTP/1.1, một connection thường phục vụ một request đang hoạt động tại một thời điểm. Với HTTP/2, một connection có thể multiplex nhiều stream đồng thời; vì vậy không thể luôn đặt số permit bằng đúng số connection. Cần xem giới hạn stream, cấu hình client và hành vi server.

## 3. Đặt Bulkhead riêng cho từng dependency

Resilience4j Semaphore Bulkhead thường được cấu hình qua phần bulkhead. Mỗi instance có thể đặt số lời gọi đồng thời tối đa và thời gian chờ permit.

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
      payment:
        maxConcurrentCalls: 8
        maxWaitDuration: 0
      recommendation:
        maxConcurrentCalls: 5
        maxWaitDuration: 50ms
~~~

Trong ví dụ:

- inventory từ chối ngay khi đã có 20 lời gọi giữ permit.
- payment từ chối ngay khi đã có 8 lời gọi đồng thời.
- recommendation cho phép chờ tối đa 50 mili giây để lấy permit; nếu không có permit trong thời gian đó, lời gọi bị từ chối.

Chờ permit có thể giúp hấp thụ một đợt tải ngắn, nhưng cũng làm request giữ tài nguyên lâu hơn và tăng độ trễ. Với request có deadline ngắn, từ chối nhanh thường dễ dự đoán hơn. Nếu cho phép chờ, thời gian chờ Bulkhead phải nằm trong ngân sách deadline tổng thể.

Nếu cần tái sử dụng cấu hình, có thể định nghĩa nhóm chung và instance tham chiếu baseConfig theo cơ chế cấu hình Resilience4j:

~~~yaml
resilience4j:
  bulkhead:
    configs:
      default:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
    instances:
      inventory:
        baseConfig: default
        maxConcurrentCalls: 20
      payment:
        baseConfig: default
        maxConcurrentCalls: 8
      recommendation:
        baseConfig: default
        maxConcurrentCalls: 5
~~~

Các ID inventory, payment và recommendation cần thống nhất với ID được sử dụng trong code hoặc adapter Spring Cloud CircuitBreaker. Hãy kiểm tra phiên bản starter và cách tích hợp Bulkhead đang dùng để xác nhận instance cấu hình được áp dụng đúng.

## 4. Tách HTTP connection pool theo dependency

Với WebClient và Reactor Netty, có thể tạo ConnectionProvider riêng cho từng dependency. Việc tách provider giúp đặt giới hạn connection và hàng đợi chờ độc lập.

Ví dụ tạo pool cho inventory:

~~~java
import java.time.Duration;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryHttpConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnectionProvider() {
        return ConnectionProvider.builder("inventory-pool")
                .maxConnections(20)
                .pendingAcquireMaxCount(10)
                .pendingAcquireTimeout(Duration.ofMillis(100))
                .maxIdleTime(Duration.ofSeconds(30))
                .build();
    }

    @Bean
    WebClient inventoryWebClient(
            ConnectionProvider inventoryConnectionProvider) {
        HttpClient httpClient = HttpClient
                .create(inventoryConnectionProvider)
                .responseTimeout(Duration.ofSeconds(2));

        return WebClient.builder()
                .baseUrl("http://inventory-service")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Các thuộc tính trong ví dụ:

- maxConnections giới hạn số connection được cấp trong pool theo cách triển khai của provider.
- pendingAcquireMaxCount giới hạn số yêu cầu đang chờ được cấp connection.
- pendingAcquireTimeout giới hạn thời gian chờ lấy connection.
- maxIdleTime giới hạn thời gian connection nhàn rỗi được giữ trước khi bị loại theo chính sách pool.
- responseTimeout giới hạn thời gian chờ response theo chính sách của Reactor Netty.

Đây là ví dụ cấu hình theo API Reactor Netty; cần đối chiếu phiên bản đang được Spring Boot quản lý. ConnectionProvider là tài nguyên có vòng đời, nên cần được dispose khi ứng dụng shutdown. Trong Spring, có thể quản lý bằng bean với destroyMethod phù hợp.

Tạo provider riêng cho payment và recommendation với tên, maxConnections và pending queue riêng. Không dùng chung một pool tùy chỉnh cho mọi dependency nếu mục tiêu là cô lập dung lượng connection giữa chúng.

Lưu ý: connection pool thường quản lý pool theo remote host và cấu hình provider. Một provider riêng không có nghĩa mọi request trong ứng dụng tự động dùng provider đó; WebClient của dependency phải được tạo với đúng HttpClient và ReactorClientHttpConnector tương ứng.

## 5. Phối hợp số permit và số connection

Với HTTP/1.1, nếu mỗi lời gọi cần một connection riêng và không có multiplexing, có thể bắt đầu bằng cách đặt Bulkhead concurrency gần với số connection có thể cấp cho dependency. Ví dụ:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 18
        maxWaitDuration: 0
~~~

~~~java
ConnectionProvider inventoryPool = ConnectionProvider.builder("inventory-pool")
        .maxConnections(20)
        .pendingAcquireMaxCount(5)
        .pendingAcquireTimeout(Duration.ofMillis(100))
        .build();
~~~

Bulkhead cho phép 18 lời gọi đồng thời, trong khi pool có tối đa 20 connection. Khoảng chênh lệch nhỏ dành cho một số hoạt động khác dùng cùng pool hoặc dao động ngắn về việc cấp connection. Nếu WebClient chỉ dùng cho lời gọi được bảo vệ bởi Bulkhead này, hai giá trị có thể được tinh chỉnh gần nhau hơn.

Không có công thức cố định áp dụng cho mọi hệ thống. Cần tính đến:

- HTTP/1.1 hay HTTP/2.
- Một request có giữ connection trong toàn bộ thời gian đọc body hay không.
- Có nhiều route hoặc nhiều endpoint dùng chung pool không.
- Có request không đi qua Bulkhead nhưng vẫn dùng cùng provider không.
- Có retry tạo thêm request trong cùng một khoảng thời gian không.
- Thời gian response và mức biến động của latency.
- Giới hạn connection ở proxy, load balancer và server.

Nếu Bulkhead là 30 nhưng pool chỉ có 10 connection, tối đa 20 lời gọi có thể chờ connection trong khi vẫn giữ permit. Khi latency tăng, các slot Bulkhead bị chiếm lâu và request mới có thể bị từ chối dù server chưa thực sự nhận đủ 30 request.

Nếu Bulkhead là 10 nhưng pool có 100 connection, tối đa 10 lời gọi đi qua Bulkhead cùng lúc. Phần connection còn lại có thể phục vụ các luồng khác nếu cùng provider được chia sẻ, hoặc đơn giản là chưa được sử dụng.

## 6. Tránh hàng đợi ẩn trong connection pool

Một hàng đợi trong HTTP pool có thể khiến hệ thống trông như đang xử lý request bình thường dù các request thực tế chưa được gửi đến server. Những request này đã chiếm permit Bulkhead và tiếp tục tiêu thụ thời gian deadline.

Ví dụ:

- Bulkhead cho phép 40 lời gọi đồng thời.
- HTTP pool chỉ có 10 connection.
- pendingAcquireMaxCount cho phép 100 request chờ.
- Dependency bắt đầu phản hồi chậm.

Có thể có 10 request đang sử dụng connection và 30 request đã giữ permit nhưng chờ connection. Khi các request đầu tiên kéo dài, các request sau tiếp tục tích tụ. Từ góc nhìn caller, latency tăng; từ góc nhìn server, số request đang hoạt động có thể thấp hơn nhiều so với số lời gọi đang chiếm tài nguyên phía client.

Để tránh tình trạng này:

1. Đặt maxConcurrentCalls phù hợp với năng lực xử lý và connection capacity của dependency.
2. Giới hạn pendingAcquireMaxCount thay vì để hàng đợi không giới hạn.
3. Đặt pendingAcquireTimeout ngắn hơn deadline tổng thể còn lại.
4. Theo dõi số request đang chờ connection và thời gian chờ acquire.
5. Từ chối nhanh khi tải đã vượt mức có thể xử lý.
6. Không retry tức thời một lỗi do pool hết connection; retry có thể làm hàng đợi lớn thêm.

Hàng đợi nhỏ có thể hấp thụ dao động ngắn. Hàng đợi lớn không làm tăng năng lực xử lý của server; nó chỉ giữ nhiều request hơn trong trạng thái chờ.

## 7. Phân biệt Semaphore Bulkhead và Thread-pool Bulkhead

Resilience4j có hai cách giới hạn tải phổ biến:

| Đặc điểm | Semaphore Bulkhead | Thread-pool Bulkhead |
|---|---|---|
| Cách giới hạn | Số permit đồng thời | Số worker và queue |
| Tạo thread riêng | Không | Có |
| Hợp với | Luồng reactive hoặc tác vụ không cần tách thread | Tác vụ blocking cần cô lập thread |
| Hàng đợi | Không có queue công việc riêng; có thể chờ permit trong maxWaitDuration | Có queue hữu hạn |
| Khi đầy | Từ chối hoặc chờ permit | Từ chối khi worker và queue đầy |

Với WebClient và WebFlux, Semaphore Bulkhead thường phù hợp hơn vì không cần chuyển publisher sang một thread pool khác chỉ để giới hạn concurrency. Tín hiệu cancel và vòng đời publisher vẫn được quản lý trong chuỗi reactive.

Thread-pool Bulkhead hữu ích khi phải cô lập một thư viện blocking hoặc một thao tác có thể chiếm thread lâu. Khi đó, cần giới hạn cả coreThreadPoolSize, maxThreadPoolSize và queueCapacity. Queue phải hữu hạn để tránh tích tụ công việc khi dependency chậm.

Ví dụ cấu hình thread-pool Bulkhead:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      legacy-inventory:
        coreThreadPoolSize: 5
        maxThreadPoolSize: 8
        queueCapacity: 10
        keepAliveDuration: 20ms
~~~

Thread-pool Bulkhead và HTTP connection pool vẫn là hai lớp độc lập. Thread pool có thể có 8 worker nhưng HTTP pool chỉ có 4 connection; khi đó worker có thể chờ connection. Ngược lại, HTTP pool có thể rộng hơn thread pool. Hãy giới hạn cả hai theo năng lực thực tế và tránh tạo queue lớn ở cả hai nơi.

## 8. Áp dụng Bulkhead rõ ràng cho lời gọi WebClient reactive

Có thể dùng Resilience4j Reactor BulkheadOperator để giới hạn concurrency của publisher. Ví dụ dưới đây dùng Semaphore Bulkhead cho inventory:

~~~java
import java.time.Duration;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class InventoryClient {

    private final WebClient webClient;
    private final Bulkhead inventoryBulkhead;
    private final ReactiveCircuitBreaker inventoryCircuitBreaker;

    public InventoryClient(
            WebClient webClient,
            ReactiveCircuitBreaker inventoryCircuitBreaker) {
        this.webClient = webClient;
        this.inventoryCircuitBreaker = inventoryCircuitBreaker;

        BulkheadConfig config = BulkheadConfig.custom()
                .maxConcurrentCalls(18)
                .maxWaitDuration(Duration.ZERO)
                .build();

        this.inventoryBulkhead = Bulkhead.of("inventory", config);
    }

    public Mono<Inventory> find(String sku) {
        Mono<Inventory> remoteCall = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        Mono<Inventory> circuitProtected = inventoryCircuitBreaker.run(
                remoteCall,
                error -> Mono.just(Inventory.unavailable(sku))
        );

        return circuitProtected.transformDeferred(
                BulkheadOperator.of(inventoryBulkhead)
        );
    }
}
~~~

Trong cách compose này, Bulkhead bao ngoài publisher được Circuit Breaker bảo vệ. Permit được lấy trước khi subscription đi vào lời gọi Circuit Breaker. Nếu hết permit, lời gọi bị từ chối ở lớp Bulkhead và không đi vào Circuit Breaker. Nhờ vậy, việc từ chối do giới hạn concurrency cục bộ không bị tính nhầm thành lỗi sức khỏe của dependency.

Nếu thứ tự decorator thay đổi và Circuit Breaker quan sát BulkheadFullException, hãy cấu hình phân loại exception phù hợp hoặc điều chỉnh thứ tự để không làm sai failure rate. Bulkhead rejection là tín hiệu hệ thống đã đạt giới hạn admission control; nó không nhất thiết chứng minh remote service đang lỗi.

Ví dụ này minh họa cách áp dụng Bulkhead trực tiếp bằng Resilience4j Reactor. Nếu ứng dụng đã dùng Spring Cloud CircuitBreaker để tự động áp dụng Bulkhead theo ID, tránh bọc thêm một Bulkhead thứ hai mà không chủ đích. Kiểm tra cấu hình adapter và đo số permit thực tế trước khi kết hợp nhiều lớp.

## 9. Tính concurrency ban đầu từ lưu lượng và latency

Có thể ước lượng số lời gọi đồng thời trung bình bằng định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- L là số request trung bình đang ở trong hệ thống.
- λ là tốc độ request trung bình, tính bằng request mỗi giây.
- W là thời gian trung bình một request ở trong hệ thống, tính bằng giây.

Ví dụ, inventory nhận 40 request mỗi giây và thời gian xử lý trung bình là 250 mili giây:

\[
L = 40 \times 0.25 = 10
\]

Nghĩa là trung bình có khoảng 10 lời gọi đang hoạt động. Đây là điểm xuất phát để đánh giá Bulkhead, không phải giá trị maxConcurrentCalls bắt buộc. Cần thêm headroom phù hợp với độ biến động của latency và kiểm tra mức concurrency mà dependency chịu được.

Nếu latency tăng từ 250 mili giây lên 1 giây trong khi tốc độ request vẫn là 40 request mỗi giây:

\[
L = 40 \times 1 = 40
\]

Số request đồng thời trung bình tăng lên 40. Nếu Bulkhead đặt giới hạn 20, hệ thống sẽ từ chối một phần request thay vì để concurrency tăng không giới hạn. Đây chính là tác dụng bảo vệ tài nguyên và giới hạn áp lực lên dependency.

Khi tính toán, nên dùng latency thực tế theo phân vị như p95 hoặc p99 để hiểu các giai đoạn tải cao, không chỉ dựa trên trung bình. Cần cân nhắc request có thời gian xử lý dài, response body lớn và số lần retry.

## 10. Phối hợp với Circuit Breaker và TimeLimiter

Bulkhead, Circuit Breaker và TimeLimiter bổ sung cho nhau:

- Bulkhead giới hạn số lời gọi được phép chạy đồng thời.
- Circuit Breaker ngăn lời gọi mới khi tỷ lệ lỗi hoặc lời gọi chậm cho thấy dependency đang suy giảm.
- TimeLimiter giới hạn thời gian chờ một thao tác.

Ví dụ cấu hình cùng ID:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s

  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 18
        maxWaitDuration: 0

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

ID inventory giúp các chính sách cùng gắn với dependency. Tuy nhiên, việc adapter Spring Cloud CircuitBreaker có tự động áp dụng cả ba module và hỗ trợ kiểu lời gọi nào phụ thuộc phiên bản, starter và cấu hình. Cần kiểm tra integration thực tế; không giả định mọi API reactive hoặc synchronous đều có cùng hành vi.

Timeout nên ngắn hơn hoặc bằng deadline caller có thể chấp nhận. Bulkhead nên giới hạn concurrency trước khi request tích tụ trong HTTP pool. Circuit Breaker cần quan sát các lỗi từ dependency, nhưng nên phân biệt lỗi remote với lỗi admission control cục bộ.

## 11. Theo dõi cả Bulkhead và connection pool

Để biết cấu hình có phối hợp đúng hay không, cần quan sát số liệu của cả hai lớp.

Bulkhead nên theo dõi:

- Số permit đang được sử dụng.
- Số lời gọi bị từ chối do hết permit.
- Số lời gọi đang chờ permit, nếu cho phép chờ.
- Thời gian giữ permit.
- Tỷ lệ từ chối theo từng dependency.

HTTP connection pool nên theo dõi:

- Số connection đang hoạt động và đang nhàn rỗi.
- Số connection tối đa.
- Số request đang chờ acquire.
- Thời gian chờ lấy connection.
- Số lần acquire timeout hoặc acquire bị từ chối.
- Số connection bị đóng hoặc tạo lại.

Nên phân biệt rõ hai loại từ chối:

| Tình huống | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| BulkheadFullException | Đã dùng hết permit concurrency | Xem lại giới hạn, latency và tải đến dependency |
| PoolAcquireTimeoutException | Không lấy được connection trong thời hạn | Xem maxConnections, pending queue và thời gian giữ connection |
| CircuitBreaker OPEN | Dependency có tỷ lệ lỗi hoặc slow call vượt ngưỡng | Điều tra lỗi remote và chính sách Circuit Breaker |
| TimeLimiter timeout | Thao tác vượt deadline | Xem timeout từng tầng và cancellation |

Nếu chỉ theo dõi tổng số timeout, khó biết request bị chậm do Bulkhead, connection pool, mạng hay server. Correlation ID và metric theo dependency giúp xác định chính xác điểm nghẽn.

## 12. Các lỗi cấu hình thường gặp

- **Bulkhead lớn hơn nhiều so với HTTP pool**: nhiều lời gọi giữ permit nhưng xếp hàng chờ connection.
- **HTTP pool dùng chung cho các dependency không liên quan**: một dependency có thể chiếm phần lớn connection và làm ảnh hưởng luồng khác.
- **Hàng đợi pending acquire không giới hạn**: request tích tụ, tăng latency và hết deadline trước khi được gửi.
- **Đặt maxConnections quá thấp**: pool trở thành nút thắt dù dependency còn khả năng xử lý.
- **Đặt Bulkhead quá cao**: giới hạn không còn bảo vệ dependency khi latency tăng.
- **Nhầm Thread-pool Bulkhead với connection pool**: thread pool quản lý worker, connection pool quản lý kết nối mạng.
- **Dùng Thread-pool Bulkhead cho publisher reactive mà không cần thiết**: việc chuyển thread có thể tạo thêm chi phí và làm phức tạp cancellation.
- **Để Circuit Breaker tính Bulkhead rejection như lỗi remote**: failure rate có thể tăng dù dependency vẫn khỏe.
- **Retry khi pool hoặc Bulkhead đã đầy**: request mới làm áp lực tăng thêm.
- **Không dispose ConnectionProvider**: tài nguyên mạng có thể tồn tại sau vòng đời thành phần quản lý.
- **Chỉ kiểm tra cấu hình mà không quan sát metric**: giá trị cấu hình không phản ánh đầy đủ hành vi thực tế dưới tải.

## 13. Quy trình triển khai theo từng dependency

Khi bảo vệ các lời gọi đến nhiều dependency trong Spring Cloud CircuitBreaker, có thể thực hiện theo trình tự:

1. Liệt kê dependency, SLA, lưu lượng và latency p95/p99 của từng dependency.
2. Xác định giới hạn concurrency ban đầu theo năng lực dependency và ngân sách tài nguyên của caller.
3. Tạo Bulkhead riêng theo dependency hoặc nhóm thao tác có cùng đặc tính.
4. Tạo WebClient và ConnectionProvider phù hợp; giới hạn maxConnections, pendingAcquireMaxCount và pendingAcquireTimeout.
5. Phối hợp maxConcurrentCalls với dung lượng pool, giao thức HTTP và các luồng khác đang dùng pool.
6. Đặt timeout cho HTTP client và deadline tổng thể để request không chờ vô hạn.
7. Kết hợp Circuit Breaker để ngăn lời gọi mới khi dependency suy giảm; phân biệt lỗi remote với lỗi từ chối cục bộ.
8. Theo dõi permit, active connection, pending acquire, latency và số lần từ chối theo từng dependency.
9. Kiểm thử tải khi một dependency chậm hoặc mất kết nối; xác nhận các dependency khác vẫn còn tài nguyên.
10. Tinh chỉnh giới hạn dựa trên số liệu production và kiểm tra lại khi thay đổi HTTP/1.1, HTTP/2 hoặc connection pool.

Bulkhead và HTTP connection pool tạo hai lớp giới hạn bổ sung. Bulkhead kiểm soát số lời gọi đồng thời được phép đi tiếp; connection pool kiểm soát khả năng cấp kết nối và số request chờ kết nối. Khi tách giới hạn theo từng dependency, giữ hàng đợi hữu hạn và theo dõi cả hai lớp, ứng dụng có thể cô lập sự cố tốt hơn, tránh tích tụ request và duy trì tài nguyên cho những dịch vụ phụ thuộc còn khỏe.
