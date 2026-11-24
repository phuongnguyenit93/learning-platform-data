# So sánh ngắt mạch theo tỷ lệ lỗi và theo tỷ lệ lời gọi chậm

Circuit breaker của Resilience4j có thể mở mạch theo hai tín hiệu độc lập: **failure rate** và **slow call rate**. Failure rate phát hiện dependency thường xuyên trả lỗi; slow call rate phát hiện dependency vẫn trả kết quả nhưng mất quá nhiều thời gian. Hai tín hiệu giải quyết hai kiểu suy giảm khác nhau và có thể cùng xuất hiện trong một sliding window.

Trong bài thực hành này, ta tạo hai tình huống có thể kiểm soát: một dependency trả lỗi nhanh và một dependency trả thành công nhưng chậm. Sau đó cấu hình breaker, tính tỷ lệ từ các mẫu, quan sát trạng thái và quyết định khi nào nên dùng ngưỡng lỗi, ngưỡng lời gọi chậm hoặc cả hai. Ví dụ đặt trong bối cảnh Spring Cloud gọi dịch vụ phụ thuộc bằng Resilience4j; các con số chỉ dùng cho lab và cần hiệu chỉnh theo SLO của hệ thống thật.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Giải thích `failureRateThreshold` và `slowCallRateThreshold` đo hai tín hiệu khác nhau.
- Phân biệt lời gọi lỗi nhanh, lời gọi thành công chậm và lời gọi vừa lỗi vừa chậm.
- Tính hai tỷ lệ từ cùng một sliding window.
- Cấu hình `minimumNumberOfCalls`, `slowCallDurationThreshold` và các ngưỡng mở mạch.
- Tạo kịch bản kiểm thử có kết quả xác định để quan sát `CLOSED` và `OPEN`.
- Chọn ngưỡng dựa trên latency mục tiêu và hành vi thực tế của dependency.

## 2. Failure rate và slow call rate khác nhau ở đâu?

**Failure rate** là tỷ lệ các lời gọi được ghi nhận là thất bại trong số lời gọi được tính vào thống kê. Một lời gọi có thể thất bại nhanh vì connection refused, DNS failure hoặc HTTP 5xx; thời gian thực thi ngắn không làm nó bớt là failure.

**Slow call rate** là tỷ lệ các lời gọi có thời gian thực thi vượt `slowCallDurationThreshold` trong cửa sổ thống kê. Một lời gọi chậm vẫn có thể trả kết quả thành công. Nó báo hiệu dependency đang giữ tài nguyên lâu, làm tăng latency và có nguy cơ khiến thread, connection pool hoặc hàng đợi bị chiếm dụng.

| Tình huống | Failure rate | Slow call rate | Ý nghĩa |
|---|---:|---:|---|
| HTTP 503 trả về sau 80 ms | Tăng | Không tăng nếu dưới ngưỡng thời gian | Dependency lỗi nhanh |
| HTTP 200 trả về sau 1,8 giây, ngưỡng chậm 700 ms | Không tăng | Tăng | Dependency trả kết quả nhưng quá chậm |
| Request timeout sau 1,2 giây, ngưỡng chậm 700 ms | Tăng nếu timeout được record | Có thể tăng vì thời gian thực thi vượt ngưỡng | Một lời gọi có thể đóng góp vào cả hai tỷ lệ |
| HTTP 200 trả về sau 150 ms | Không tăng | Không tăng | Lời gọi bình thường |

Resilience4j đánh giá hai ngưỡng độc lập. Breaker có thể chuyển sang `OPEN` khi failure rate đạt `failureRateThreshold` **hoặc** slow call rate đạt `slowCallRateThreshold`, sau khi có đủ số mẫu tối thiểu. Vì vậy, chỉ kiểm tra số lỗi sẽ bỏ sót trường hợp dependency đang suy giảm do độ trễ.

## 3. Công thức và cách tính từ sliding window

Với các lời gọi được tính vào thống kê, có thể diễn giải hai tỷ lệ như sau:

\[
\text{Failure rate} = \frac{\text{Số lời gọi lỗi}}{\text{Số lời gọi thành công} + \text{Số lời gọi lỗi}} \times 100\%
\]

\[
\text{Slow call rate} = \frac{\text{Số lời gọi chậm}}{\text{Số lời gọi được ghi nhận}} \times 100\%
\]

Exception được cấu hình `ignoreExceptions` không được tính là success hoặc failure trong sliding window. Các lời gọi bị breaker từ chối (`not permitted`) cũng không phải kết quả của supplier và không được xem như một lời gọi backend thất bại. Một lời gọi lỗi có thể đồng thời là lời gọi chậm nếu thời gian thực thi của nó vượt `slowCallDurationThreshold`.

Giả sử cửa sổ có 10 mẫu:

| Nhóm kết quả | Số lượng | Có lỗi? | Chậm? |
|---|---:|---|---|
| Thành công nhanh | 4 | Không | Không |
| Thành công chậm | 3 | Không | Có |
| Lỗi nhanh | 2 | Có | Không |
| Lỗi chậm | 1 | Có | Có |
| **Tổng** | **10** | **3 lỗi** | **4 lời gọi chậm** |

Từ bảng trên:

- Failure rate = 3 / 10 = 30%.
- Slow call rate = 4 / 10 = 40%.
- Một lời gọi lỗi chậm được tính trong cả số lỗi và số lời gọi chậm, nhưng tổng số mẫu vẫn chỉ là một.

Nếu `failureRateThreshold` là 50% và `slowCallRateThreshold` là 35%, breaker có thể mở vì slow call rate đạt ngưỡng dù failure rate vẫn dưới ngưỡng. Đây là lý do cần xem hai chỉ số cùng lúc.

## 4. Cấu hình chung cho bài lab

Tạo một instance breaker tên `catalogLab`. Cấu hình dưới đây dùng cửa sổ theo số lượng để việc tính mẫu dễ quan sát:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogLab:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 40
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
```

Ý nghĩa các tham số:

| Thuộc tính | Giá trị lab | Ý nghĩa |
|---|---:|---|
| `slidingWindowType` | `COUNT_BASED` | Cửa sổ lưu 10 lời gọi gần nhất |
| `slidingWindowSize` | `10` | Kích thước cửa sổ theo số lời gọi |
| `minimumNumberOfCalls` | `10` | Chỉ đánh giá tỷ lệ sau khi đủ 10 mẫu |
| `failureRateThreshold` | `50` | Mở mạch nếu failure rate đạt hoặc vượt 50% |
| `slowCallDurationThreshold` | `700ms` | Lời gọi lâu hơn ngưỡng được đánh dấu chậm |
| `slowCallRateThreshold` | `40` | Mở mạch nếu slow call rate đạt hoặc vượt 40% |
| `waitDurationInOpenState` | `10s` | Thời gian ở `OPEN` trước khi có thể thăm dò lại |
| `permittedNumberOfCallsInHalfOpenState` | `2` | Số lời gọi thăm dò tối đa được cấp trong `HALF_OPEN` |

`minimumNumberOfCalls` áp dụng cho việc đánh giá cả failure rate và slow call rate. Trong lab, đặt bằng kích thước cửa sổ để đủ 10 mẫu rồi mới so sánh kết quả. Ở production, có thể chọn giá trị thấp hơn kích thước cửa sổ, nhưng phải dựa trên lưu lượng và mức độ đại diện của mẫu.

## 5. Tạo gateway gọi dependency qua CircuitBreaker

Ví dụ dùng Spring Cloud reactive circuit breaker với `WebClient`. Timeout được đặt **bên trong publisher đưa vào breaker** để timeout của dependency được quan sát như một kết quả lỗi của lời gọi được bảo vệ.

```java
import java.time.Duration;
import java.time.Instant;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> breakerFactory;

    public CatalogGateway(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> breakerFactory) {
        this.webClient = builder
                .baseUrl("http://localhost:8091")
                .build();
        this.breakerFactory = breakerFactory;
    }

    public Mono<CatalogResult> find(String sku) {
        Mono<CatalogResult> dependencyCall = Mono.defer(() ->
                webClient.get()
                        .uri("/catalog/{sku}", sku)
                        .retrieve()
                        .bodyToMono(CatalogResult.class)
        ).timeout(Duration.ofSeconds(2));

        ReactiveCircuitBreaker breaker = breakerFactory.create("catalogLab");
        return breaker.run(
                dependencyCall,
                error -> Mono.just(CatalogResult.unavailable(sku, Instant.now()))
        );
    }
}
```

`CatalogResult` là kiểu DTO của ứng dụng, có thể biểu diễn dữ liệu catalog hoặc trạng thái `UNAVAILABLE`. Trong ứng dụng thật, cấu hình `WebClient` nên dùng service discovery/load balancing hoặc URL theo môi trường thay vì hardcode `localhost`.

Nếu dùng API đồng bộ, có thể lấy `CircuitBreaker` từ `CircuitBreakerFactory` và bọc supplier tương tự. Điều quan trọng trong bài lab là timeout thuộc publisher/supplier được bảo vệ để breaker có thể ghi nhận nó. Nếu đặt `timeout` ở ngoài toàn bộ `breaker.run(...)`, timeout bên ngoài có thể chỉ hủy subscription của publisher được bảo vệ; tùy implementation, breaker có thể quan sát cancellation thay vì một exception timeout. Hãy xác nhận semantics theo phiên bản đang dùng.

## 6. Kịch bản A: dependency lỗi nhanh

Kịch bản đầu tiên mô phỏng dependency trả HTTP 503 gần như ngay lập tức. Các request thất bại trong thời gian thấp hơn 700 ms, nên chúng làm tăng failure rate nhưng không làm tăng slow call rate.

Ví dụ một endpoint thử nghiệm trong dependency:

```java
@RestController
public class CatalogLabController {

    @GetMapping("/catalog/fail-fast/{sku}")
    public ResponseEntity<Void> failFast(@PathVariable String sku) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
```

Trong gateway, trỏ lời gọi lab tới endpoint `fail-fast` và để HTTP client chuyển status 5xx thành exception, ví dụ dùng `retrieve()` mặc định của WebClient. Thực hiện 10 lời gọi qua breaker trong khi breaker ở `CLOSED`.

Kết quả mong đợi:

| Chỉ số | Kết quả dự kiến |
|---|---:|
| Tổng mẫu | 10 |
| Failed | 10 |
| Successful | 0 |
| Slow calls | 0 nếu mọi request hoàn tất dưới 700 ms |
| Failure rate | 100% |
| Slow call rate | 0% |
| Trạng thái sau khi đủ mẫu | `OPEN` do failure rate |

Kịch bản này cho thấy failure rate hữu ích khi dependency trả lỗi nhanh. Slow call rate không cần vượt ngưỡng để breaker mở.

## 7. Kịch bản B: dependency thành công nhưng chậm

Kịch bản thứ hai mô phỏng dependency vẫn trả HTTP 200 nhưng mất 1,2 giây, lớn hơn `slowCallDurationThreshold` 700 ms. Không có exception nên failure rate không tăng; slow call rate tăng.

```java
@GetMapping("/catalog/slow/{sku}")
public CatalogResult slow(@PathVariable String sku) throws InterruptedException {
    Thread.sleep(1200);
    return new CatalogResult(sku, "AVAILABLE");
}
```

Trong lab, thay endpoint được gọi bằng `/catalog/slow/{sku}` và thực hiện 10 lời gọi qua một breaker đang `CLOSED` mới. Đảm bảo timeout của gateway lớn hơn 1,2 giây, ví dụ 2 giây, để lời gọi hoàn tất thành công thay vì bị timeout.

Kết quả mong đợi:

| Chỉ số | Kết quả dự kiến |
|---|---:|
| Tổng mẫu | 10 |
| Failed | 0 |
| Successful | 10 |
| Slow calls | 10 |
| Failure rate | 0% |
| Slow call rate | 100% |
| Trạng thái sau khi đủ mẫu | `OPEN` do slow call rate |

Đây là trường hợp failure rate không phát hiện được suy giảm. Tất cả lời gọi đều trả kết quả thành công, nhưng độ trễ đủ cao để chiếm tài nguyên và làm chậm các request phía trên. Slow call rate cho phép breaker bảo vệ dependency ngay cả khi backend chưa bắt đầu trả lỗi.

## 8. Kịch bản C: so sánh hai ngưỡng bằng cùng một tập mẫu

Thực hiện một batch gồm 10 kết quả có chủ đích:

| Lần gọi | Kết quả | Thời gian | Failure? | Slow? |
|---:|---|---:|---|---|
| 1 | 200 | 100 ms | Không | Không |
| 2 | 200 | 120 ms | Không | Không |
| 3 | 503 | 90 ms | Có | Không |
| 4 | 200 | 1.000 ms | Không | Có |
| 5 | 503 | 110 ms | Có | Không |
| 6 | 200 | 1.100 ms | Không | Có |
| 7 | 200 | 150 ms | Không | Không |
| 8 | 503 | 130 ms | Có | Không |
| 9 | 200 | 900 ms | Không | Có |
| 10 | 200 | 1.200 ms | Không | Có |

Tập mẫu có 3 lỗi và 4 lời gọi chậm:

- Failure rate = 3 / 10 = 30%.
- Slow call rate = 4 / 10 = 40%.
- Với `failureRateThreshold: 50`, ngưỡng lỗi chưa đạt.
- Với `slowCallRateThreshold: 40`, ngưỡng lời gọi chậm đã đạt.

Breaker có thể mở do slow call rate. Nếu chỉ cấu hình `failureRateThreshold`, hệ thống vẫn ở `CLOSED` với tập mẫu này, dù 4/10 lời gọi đã vượt thời gian mục tiêu.

Để kiểm thử trường hợp ngược lại, giữ số mẫu là 10 nhưng tạo 6 lỗi nhanh và 4 thành công nhanh. Failure rate là 60%, slow call rate là 0%; breaker mở do failure rate. Hai thử nghiệm giúp xác nhận hai ngưỡng hoạt động độc lập.

## 9. Kiểm tra state và metric của breaker

Khi chạy lab, quan sát cả trạng thái và thống kê. Với Resilience4j native API, có thể lấy breaker từ `CircuitBreakerRegistry` để đọc metrics:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

public void printMetrics(CircuitBreakerRegistry registry) {
    CircuitBreaker breaker = registry.circuitBreaker("catalogLab");
    CircuitBreaker.Metrics metrics = breaker.getMetrics();

    System.out.println("state=" + breaker.getState());
    System.out.println("buffered=" + metrics.getNumberOfBufferedCalls());
    System.out.println("failed=" + metrics.getNumberOfFailedCalls());
    System.out.println("successful=" + metrics.getNumberOfSuccessfulCalls());
    System.out.println("failureRate=" + metrics.getFailureRate());
    System.out.println("slowCallRate=" + metrics.getSlowCallRate());
}
```

Đoạn mã minh họa API native của Resilience4j. Trong Spring Boot, nên inject registry do auto-configuration quản lý, không tự tạo registry mới rồi đọc nhầm một breaker khác với breaker mà gateway đang dùng.

Nếu chưa đủ `minimumNumberOfCalls`, failure rate hoặc slow call rate có thể chưa được xác định và thường được biểu diễn là `-1.0`. Không diễn giải `-1.0` là tỷ lệ âm hoặc là không có lỗi; đó là trạng thái chưa đủ mẫu để đánh giá. Sau khi đủ mẫu, đọc cả hai tỷ lệ cùng số mẫu buffered và state.

## 10. So sánh các trường hợp mở mạch

Với cấu hình lab ở trên, có thể tóm tắt như sau:

| Kịch bản | Failure rate | Slow call rate | Điều kiện mở mạch đạt? | Nguyên nhân mở |
|---|---:|---:|---|---|
| 10 lỗi nhanh | 100% | 0% | Có | Failure rate |
| 10 thành công chậm | 0% | 100% | Có | Slow call rate |
| 3 lỗi nhanh, 4 chậm thành công, 3 nhanh thành công | 30% | 40% | Có | Slow call rate |
| 2 lỗi nhanh, 2 chậm thành công, 6 nhanh thành công | 20% | 20% | Không | Không mở |
| 6 lỗi nhanh, 4 thành công nhanh | 60% | 0% | Có | Failure rate |

Hai ngưỡng dùng phép OR về mặt quyết định: chỉ cần một ngưỡng đạt điều kiện sau khi đủ mẫu là breaker có thể chuyển `OPEN`. Không cần cả failure rate và slow call rate cùng vượt ngưỡng.

## 11. Điều chỉnh ngưỡng theo SLO

`slowCallDurationThreshold` nên được chọn dựa trên ngân sách latency của dependency và deadline tổng của request. Nếu SLO cho lời gọi catalog là p95 dưới 500 ms, ngưỡng 700 ms có thể là điểm bắt đầu hợp lý cho lab, nhưng production cần phân tích histogram thực tế, overhead mạng và tải cao điểm.

`slowCallRateThreshold` xác định tỷ lệ chậm có thể chấp nhận trong cửa sổ. Nếu đặt 20%, chỉ cần một phần năm lời gọi chậm sau khi đủ mẫu là breaker có thể mở. Nếu đặt 80%, hệ thống có thể chịu nhiều lời gọi chậm hơn trước khi mở mạch, nhưng tài nguyên có thể đã bị giữ lâu.

`failureRateThreshold` nên phản ánh mức lỗi mà dependency có thể chịu trước khi cần ngừng gửi traffic. Lỗi nhanh và lỗi chậm có ý nghĩa khác nhau, nên không nhất thiết dùng cùng một tỷ lệ cho mọi dependency.

Khi hiệu chỉnh, cần xem xét:

- Latency p50/p95/p99 và phân bố thời gian phản hồi trong điều kiện bình thường.
- Tỷ lệ lỗi nền, bao gồm lỗi tạm thời và lỗi nghiệp vụ đã được phân loại.
- Lưu lượng của từng breaker ID và thời gian cần để đạt `minimumNumberOfCalls`.
- Deadline tổng, timeout của HTTP client và timeout ở từng hop.
- Sức chịu tải của thread pool, connection pool và hàng đợi.
- Mức độ chấp nhận fallback và tác động tới chức năng người dùng.

Không chọn `slowCallDurationThreshold` bằng timeout của HTTP client một cách máy móc. Nếu timeout client là 2 giây và ngưỡng slow cũng là 2 giây, nhiều request bị timeout có thể được tính là lỗi nhưng không có nhiều cơ hội được ghi nhận là slow theo ngưỡng. Đặt ngưỡng slow thấp hơn timeout có thể giúp nhận biết suy giảm trước khi request bị timeout.

## 12. Slow call rate không thay thế timeout hoặc TimeLimiter

Slow call rate là cơ chế thống kê và quyết định mở breaker. Nó không tự dừng lời gọi đang chạy khi thời gian vượt `slowCallDurationThreshold`. Ví dụ, nếu ngưỡng slow là 700 ms nhưng HTTP request hoàn tất sau 1,5 giây, breaker có thể ghi nhận đó là slow call sau khi lời gọi hoàn tất; nó không tự hủy request ở mốc 700 ms.

Muốn giới hạn thời gian chờ, cần cấu hình timeout riêng:

- Connect timeout giới hạn thời gian thiết lập kết nối.
- Read/response timeout giới hạn thời gian chờ dữ liệu theo semantics của HTTP client.
- Reactor `timeout` hoặc Resilience4j TimeLimiter giới hạn thời gian chờ publisher/tác vụ theo API đang dùng.
- Deadline tổng thể giới hạn toàn bộ request qua nhiều bước.

Vì vậy, nên dùng slow call rate để phát hiện xu hướng latency suy giảm và dùng timeout/deadline để giới hạn thời gian chờ. Hai cơ chế bổ sung cho nhau.

## 13. Ảnh hưởng của HALF_OPEN và probe

Sau khi breaker mở, hết `waitDurationInOpenState`, breaker có thể chuyển sang `HALF_OPEN` và cấp một số lời gọi thăm dò. Kết quả probe cũng được đánh giá theo failure rate và slow call rate. Nếu probe trả lỗi hoặc chậm vượt ngưỡng với tỷ lệ đủ cao, breaker có thể quay lại `OPEN`; nếu kết quả đủ tốt, breaker có thể trở về `CLOSED`.

Khi dependency có latency biến động, chỉ probe thành công chưa chắc đủ để kết luận đã phục hồi. Một probe nhanh trong lúc tải thấp có thể không đại diện cho behavior ở tải bình thường. Chọn số probe và ngưỡng theo khả năng backend, tránh gửi quá nhiều request đồng thời khi dịch vụ vừa phục hồi.

## 14. Bài tập mở rộng

Thực hiện các thay đổi sau và ghi lại kết quả trước/sau:

1. Giữ `failureRateThreshold: 50`, nâng `slowCallRateThreshold` từ 40 lên 70. Chạy lại kịch bản 3 lỗi nhanh và 4 lời gọi chậm; xác định breaker còn mở do slow call rate không.
2. Giữ `slowCallRateThreshold: 40`, tăng `slowCallDurationThreshold` từ 700 ms lên 1.000 ms. Chạy lại các lời gọi 900 ms và 1.200 ms; tính lại số slow call.
3. Đặt `minimumNumberOfCalls: 5`, `slidingWindowSize: 10`. Gửi bốn lời gọi lỗi và kiểm tra breaker chưa đánh giá tỷ lệ; gửi lời gọi thứ năm rồi quan sát state.
4. Tạo một lời gọi timeout sau 1,2 giây với `slowCallDurationThreshold: 700ms`. Xác nhận nó có thể được tính vừa là failed vừa là slow nếu timeout exception được ghi nhận và thời gian thực thi vượt ngưỡng.
5. Cấu hình `ignoreExceptions` cho một lỗi nghiệp vụ, tạo các mẫu lỗi bị ignore và kiểm tra chúng không làm tăng failure rate hoặc số mẫu success/failure.
6. So sánh một breaker dùng chung cho nhiều endpoint với breaker riêng theo operation. Quan sát cách một endpoint chậm ảnh hưởng đến endpoint còn lại.

Khi ghi kết quả, hãy lưu số success, failed, slow calls, buffered calls, failure rate, slow call rate và state. Không chỉ ghi lại trạng thái cuối cùng vì trạng thái `OPEN` không tự cho biết ngưỡng nào đã kích hoạt.

## 15. Checklist kết luận từ bài lab

Trước khi chọn policy cho dependency thật, xác nhận:

- Failure rate phát hiện được lỗi nhanh như HTTP 5xx hoặc connection failure.
- Slow call rate phát hiện được trường hợp lời gọi thành công nhưng vượt ngân sách latency.
- Một lời gọi có thể vừa failed vừa slow; không cộng nó thành hai mẫu riêng.
- `minimumNumberOfCalls` đã đủ trước khi diễn giải hai tỷ lệ.
- `slowCallDurationThreshold` được chọn dựa trên SLO và thấp hơn timeout khi cần phát hiện suy giảm sớm.
- Timeout/TimeLimiter vẫn được cấu hình để giới hạn thời gian chờ thực tế.
- Fallback không biến dữ liệu không xác định thành kết quả nghiệp vụ sai.
- Metric và log cho biết breaker mở do failure rate hay slow call rate.

Failure rate và slow call rate là hai tín hiệu bổ sung. Failure rate bảo vệ hệ thống khi dependency thường xuyên thất bại; slow call rate giúp phát hiện sớm tình trạng trả lời quá chậm ngay cả khi request vẫn thành công. Bằng cách tạo hai kịch bản riêng, tính tỷ lệ từ cùng sliding window và đối chiếu với state, đội phát triển có thể chọn ngưỡng phù hợp với latency mục tiêu, lưu lượng và mức độ bảo vệ cần thiết cho từng dependency.
