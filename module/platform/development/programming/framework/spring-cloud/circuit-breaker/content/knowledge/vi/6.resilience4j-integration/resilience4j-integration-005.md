# Kết hợp CircuitBreakerConfig với TimeLimiterConfig

Trong Spring Cloud Circuit Breaker tích hợp Resilience4j, `CircuitBreakerConfig` và `TimeLimiterConfig` giải quyết hai phần khác nhau của cùng một lời gọi tới dịch vụ phụ thuộc. `CircuitBreakerConfig` quyết định khi nào ngừng gửi request, dựa trên tỷ lệ lỗi, tỷ lệ lời gọi chậm và cửa sổ thống kê. `TimeLimiterConfig` giới hạn thời gian chờ một tác vụ được hỗ trợ hoàn tất. Khi kết hợp chúng cho cùng một instance, ứng dụng vừa có giới hạn thời gian cho từng lần gọi, vừa có cơ chế ngắt các lần gọi tiếp theo khi dịch vụ liên tục gặp vấn đề.

Hai cấu hình cần được thiết kế cùng nhau. Nếu timeout quá dài, caller vẫn phải chờ lâu trước khi nhận lỗi. Nếu timeout quá ngắn, các request bình thường có thể bị kết thúc sớm và làm tăng failure rate. Nếu chỉ có timeout mà không có circuit breaker, ứng dụng vẫn có thể liên tục tạo các request mới tới dịch vụ đang quá tải.

## Vai trò của từng cấu hình

| Cấu hình | Trách nhiệm | Ví dụ thuộc tính |
|---|---|---|
| `CircuitBreakerConfig` | Đánh giá kết quả trong cửa sổ, chuyển giữa `CLOSED`, `OPEN`, `HALF_OPEN` | `slidingWindowSize`, `failureRateThreshold`, `slowCallRateThreshold`, `waitDurationInOpenState` |
| `TimeLimiterConfig` | Giới hạn thời gian chờ tác vụ và cấu hình việc hủy Future khi hết hạn | `timeoutDuration`, `cancelRunningFuture` |

`timeoutDuration` là giới hạn thời gian cho lần thực thi được TimeLimiter bảo vệ. Khi quá hạn, TimeLimiter kết thúc việc chờ bằng timeout exception. Circuit breaker nhận kết quả lỗi này và ghi nhận theo chính sách phân loại exception đang áp dụng. Sau khi đủ số mẫu theo `minimumNumberOfCalls`, breaker đánh giá failure rate và slow call rate; nếu một tỷ lệ chạm ngưỡng tương ứng, breaker chuyển sang `OPEN`.

TimeLimiter không tự quyết định circuit breaker phải mở. Một timeout có thể làm tăng số lời gọi lỗi, nhưng việc mở breaker còn phụ thuộc số mẫu tối thiểu và ngưỡng của `CircuitBreakerConfig`. Ngược lại, circuit breaker có thể mở do các exception khác hoặc do tỷ lệ lời gọi chậm, kể cả khi chưa có request nào chạm timeout.

## Phân biệt timeout và slow-call threshold

`timeoutDuration` và `slowCallDurationThreshold` đều liên quan đến thời gian nhưng có ý nghĩa khác nhau:

- `timeoutDuration` xác định khi nào TimeLimiter kết thúc việc chờ tác vụ.
- `slowCallDurationThreshold` xác định thời lượng từ đó một lời gọi được phân loại là chậm trong thống kê circuit breaker.

Ví dụ, đặt `slowCallDurationThreshold` là 2 giây và `timeoutDuration` là 3 giây. Một lời gọi hoàn tất sau 2,5 giây có thể thành công nhưng vẫn được ghi nhận là lời gọi chậm. Một lời gọi không hoàn tất trước 3 giây sẽ bị TimeLimiter kết thúc bằng timeout; nếu timeout exception được ghi nhận là lỗi, lời gọi đó đóng góp vào failure rate. Thời lượng thực thi cũng có thể vượt ngưỡng chậm nên đóng góp vào slow-call rate.

Nếu đặt `slowCallDurationThreshold` dài hơn `timeoutDuration`, các request bị TimeLimiter kết thúc ở ngưỡng timeout có thể được ghi nhận là lỗi mà không đạt ngưỡng để phân loại là lời gọi chậm. Hãy chọn hai giá trị theo mục tiêu giám sát: timeout là giới hạn chờ, còn slow-call threshold là ngưỡng đánh dấu hiệu năng kém.

## Cấu hình kết hợp bằng Java Customizer

Với Spring Cloud Circuit Breaker Resilience4j, có thể cấu hình một instance bằng `Resilience4JCircuitBreakerFactory`. Phương thức `configure` nhận cấu hình được xây dựng từ `Resilience4JConfigBuilder`, trong đó có cả circuit breaker và time limiter.

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory> catalogConfiguration() {
        return factory -> factory.configure(builder -> builder
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .slowCallRateThreshold(50)
                        .slowCallDurationThreshold(Duration.ofSeconds(2))
                        .waitDurationInOpenState(Duration.ofSeconds(10))
                        .permittedNumberOfCallsInHalfOpenState(3)
                        .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(3))
                        .cancelRunningFuture(true)
                        .build())
                .build(), "catalog");
    }
}
```

Trong ví dụ, instance `catalog` dùng cửa sổ 20 lời gọi và chỉ bắt đầu đánh giá khi đã có ít nhất 10 lời gọi. Breaker mở khi failure rate hoặc slow-call rate đạt 50%. Sau 10 giây ở `OPEN`, breaker có thể thử phục hồi với tối đa ba lời gọi trong `HALF_OPEN`. TimeLimiter giới hạn thời gian chờ ở ba giây và yêu cầu hủy Future đang chạy khi hết hạn.

ID truyền vào `factory.configure(..., "catalog")` phải khớp với ID mà ứng dụng dùng khi tạo circuit breaker. Nếu cấu hình instance `catalog` nhưng code gọi `factory.create("catalogService")`, hai cấu hình không được gắn với cùng tên instance như dự định.

## Cấu hình bằng application.yml

Có thể khai báo cấu hình theo instance trong `application.yml`. Tên instance dưới `circuitbreaker.instances` và `timelimiter.instances` cần giống nhau để hai phần cấu hình áp dụng cho cùng backend.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 50
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 3s
        cancelRunningFuture: true
```

Đoạn YAML thể hiện cùng chính sách với ví dụ Java. Khi chọn cấu hình bằng properties, hãy kiểm tra phiên bản Spring Cloud Circuit Breaker và Resilience4j đang dùng để bảo đảm các thuộc tính được hỗ trợ. Tránh khai báo nhiều giá trị khác nhau cho cùng một instance ở Java Customizer và file cấu hình nếu nhóm phát triển chưa thống nhất rõ nguồn cấu hình có hiệu lực.

## Sử dụng instance đã cấu hình

Sau khi factory nhận cấu hình, service lấy instance bằng đúng ID `catalog` và bọc lời gọi phụ thuộc trong supplier:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String productId) {
        CircuitBreaker circuitBreaker = circuitBreakerFactory.create("catalog");

        return circuitBreaker.run(
                () -> catalogClient.findProduct(productId),
                error -> Product.unavailable(productId)
        );
    }
}
```

Lời gọi `catalogClient.findProduct` nằm bên trong supplier nên được thực thi qua circuit breaker. Khi request timeout hoặc breaker từ chối thực thi do đang `OPEN`, overload có fallback trả về `Product.unavailable`. Fallback giúp caller có kết quả thay thế; nó không xóa kết quả lỗi của lần gọi gốc khỏi thống kê circuit breaker.

TimeLimiter chỉ có thể giới hạn tác vụ trên đường thực thi mà integration hỗ trợ. Khi làm việc với Future hoặc CompletionStage, hãy để integration nhận biết và theo dõi quá trình hoàn tất của tác vụ. Không bọc một `CompletableFuture` rồi trả nó như một giá trị thông thường nếu circuit breaker chỉ quan sát thời điểm supplier tạo ra Future; khi đó breaker có thể ghi nhận thành công trước khi công việc bất đồng bộ thực sự kết thúc. Với API reactive, dùng `ReactiveCircuitBreaker` và cơ chế timeout dành cho publisher theo phiên bản stack đang sử dụng; không mặc định rằng timeout của một lời gọi đồng bộ và timeout của `Mono`/`Flux` có cùng cách thực thi.

## Hiểu tác động của cancelRunningFuture

`cancelRunningFuture(true)` yêu cầu TimeLimiter hủy Future đang chạy khi timeout xảy ra. Đây là tín hiệu hủy tác vụ ở tầng Future; nó không bảo đảm request đã gửi tới hệ thống từ xa lập tức dừng lại. Việc dừng thực tế phụ thuộc executor, khả năng ngắt thread và HTTP client có hỗ trợ hủy request hay không.

Vì vậy, hãy cấu hình timeout ở HTTP client hoặc thư viện RPC bên dưới để giới hạn kết nối và thời gian đọc phản hồi. TimeLimiter bảo vệ thời gian chờ ở tầng thực thi; timeout của client giúp kiểm soát chính request mạng. Khi hai tầng dùng thời hạn khác nhau, cần chọn thứ tự hợp lý để lỗi từ client có cơ hội được trả về trước khi TimeLimiter kết thúc tác vụ.

Không nên bật hủy Future mà không xem xét tác động lên tác vụ. Nếu tác vụ thực hiện thao tác có side effect, việc hủy ở phía caller không đồng nghĩa thao tác ở hệ thống từ xa đã được rollback. Với giao dịch ghi dữ liệu, cần thiết kế tính idempotent, mã yêu cầu duy nhất hoặc cơ chế tra cứu trạng thái để xử lý trường hợp caller timeout nhưng dịch vụ phụ thuộc vẫn hoàn tất.

## Chọn timeout và ngưỡng circuit breaker

Hãy bắt đầu từ thời gian phản hồi bình thường của dịch vụ phụ thuộc, yêu cầu thời gian đáp ứng của caller và timeout ở tầng mạng. Một cấu hình tham khảo có thể là:

| Tham số | Giá trị ví dụ | Mục đích |
|---|---:|---|
| HTTP client response timeout | 2,5 giây | Giới hạn thời gian chờ phản hồi từ dịch vụ |
| `slowCallDurationThreshold` | 2 giây | Ghi nhận request kéo dài là lời gọi chậm |
| `TimeLimiter.timeoutDuration` | 3 giây | Giới hạn thời gian chờ ở tầng thực thi được bảo vệ |
| `waitDurationInOpenState` | 10 giây | Thời gian breaker ở `OPEN` trước lần thử phục hồi |

Đây chỉ là ví dụ để minh họa quan hệ giữa các lớp timeout. Giá trị thực tế phải dựa trên phân vị độ trễ, tải, giới hạn tài nguyên và ngân sách thời gian của toàn bộ request. Không đặt timeout dài hơn thời gian caller có thể chờ một cách vô ích; cũng không đặt quá sát độ trễ bình thường khiến các request hợp lệ liên tục bị timeout.

## Kiểm tra hành vi kết hợp

Sau khi cấu hình, thử các trường hợp dưới đây và quan sát kết quả trả về, exception, metric cùng sự kiện chuyển trạng thái:

1. **Lời gọi nhanh và thành công:** supplier trả dữ liệu bình thường; TimeLimiter không hết hạn và circuit breaker ghi nhận thành công.
2. **Lời gọi chậm nhưng vẫn hoàn tất trước timeout:** caller nhận dữ liệu; nếu thời lượng vượt `slowCallDurationThreshold`, lời gọi đóng góp vào slow-call rate.
3. **Lời gọi vượt timeout:** TimeLimiter phát sinh timeout; nếu exception được ghi nhận là lỗi, failure rate tăng. Nếu thời lượng cũng vượt ngưỡng chậm, slow-call rate có thể tăng đồng thời.
4. **Nhiều timeout liên tiếp:** khi đủ `minimumNumberOfCalls` và failure rate đạt `failureRateThreshold`, breaker chuyển sang `OPEN`.
5. **Breaker đang OPEN:** supplier bị từ chối trước khi gửi request mới; fallback được gọi nếu đã cấu hình.
6. **Breaker HALF_OPEN:** chỉ các probe được cấp quyền mới được thực thi. Timeout của probe được đánh giá như kết quả của lời gọi và có thể khiến breaker quay lại `OPEN`.
7. **Future bị hủy:** xác nhận tác vụ trong ứng dụng phản ứng với hủy; đồng thời kiểm tra HTTP client và dịch vụ phụ thuộc để biết request mạng có thực sự dừng hay không.

Khi phân tích metric, hãy xem riêng `failureRate` và `slowCallRate`. Timeout thường là dấu hiệu lỗi và có thể đồng thời là lời gọi chậm, nhưng hai tỷ lệ được so sánh với hai ngưỡng độc lập. Nếu breaker mở quá thường xuyên, hãy kiểm tra thời gian phản hồi thực tế, timeout ở client, `timeoutDuration`, `slowCallDurationThreshold`, `minimumNumberOfCalls` và chính sách phân loại exception trước khi thay đổi ngưỡng.
