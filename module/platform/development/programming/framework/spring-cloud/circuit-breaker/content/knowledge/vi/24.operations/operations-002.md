# Chạy thử ở chế độ chỉ quan sát khi hiện thực hỗ trợ

Trước khi bật circuit breaker để chặn lời gọi thật, đội vận hành có thể muốn quan sát xem chính sách dự kiến sẽ phản ứng thế nào với traffic hiện tại. Với implementation Resilience4j, có một trạng thái đặc biệt tên `METRICS_ONLY`: breaker vẫn cho phép lời gọi đi qua và ghi nhận kết quả, nhưng không chuyển sang `OPEN` để từ chối các lời gọi tiếp theo khi failure rate hoặc slow call rate vượt ngưỡng.

Chế độ này hữu ích khi triển khai chính sách lần đầu, hiệu chỉnh `minimumNumberOfCalls`, `failureRateThreshold` hoặc `slowCallRateThreshold`, và đánh giá tỷ lệ fallback dự kiến trước khi bật bảo vệ. Tuy nhiên, đây là chế độ quan sát trên **traffic thực**: request vẫn được gửi đến dependency và vẫn có thể timeout hoặc thất bại. `METRICS_ONLY` không phải môi trường mô phỏng, không nhân bản traffic và cũng không bảo vệ backend khỏi quá tải.

## 1. `METRICS_ONLY` hoạt động như thế nào?

Trong trạng thái bình thường `CLOSED`, Resilience4j cho phép supplier chạy, ghi nhận kết quả vào sliding window và có thể chuyển sang `OPEN` khi đủ mẫu cùng vượt ngưỡng cấu hình. Khi `OPEN`, breaker từ chối lời gọi mới. Khi hết thời gian chờ, breaker chuyển sang `HALF_OPEN` để thăm dò khả năng phục hồi.

Ở `METRICS_ONLY`, các lời gọi vẫn được phép thực thi và kết quả success/error vẫn được ghi nhận. Breaker không mở mạch để chặn lời gọi dựa trên failure rate hoặc slow call rate. Điều đó cho phép quan sát số lỗi và độ trễ mà không làm thay đổi luồng traffic bằng quyết định mở mạch.

| Trạng thái | Cho phép lời gọi? | Ghi nhận kết quả? | Có thể tự chuyển sang `OPEN` do ngưỡng? |
|---|---|---|---|
| `CLOSED` | Có | Có | Có |
| `OPEN` | Không, lời gọi bị từ chối | Ghi nhận sự kiện từ chối | Đang ở trạng thái mở |
| `HALF_OPEN` | Có giới hạn theo số probe | Có | Có thể quay lại `OPEN` nếu probe thất bại |
| `METRICS_ONLY` | Có | Có | Không |
| `DISABLED` | Có | Không ghi nhận các metric/sự kiện breaker như chế độ quan sát | Không |
| `FORCED_OPEN` | Không | Không đánh giá lời gọi supplier | Không cần chờ ngưỡng |

Điểm khác biệt quan trọng giữa `METRICS_ONLY` và `DISABLED` là chế độ chỉ quan sát vẫn ghi nhận success, failure và thời gian thực thi. `DISABLED` bỏ qua cơ chế ghi nhận của breaker. Vì vậy, nếu mục tiêu là đánh giá ngưỡng trước khi bật bảo vệ, `METRICS_ONLY` phù hợp hơn `DISABLED`.

## 2. Đây là khả năng của implementation, không phải hợp đồng chung

Spring Cloud CircuitBreaker cung cấp abstraction như `CircuitBreakerFactory` và `ReactiveCircuitBreakerFactory`. Hợp đồng chung giúp ứng dụng gọi qua breaker mà không phụ thuộc trực tiếp vào thư viện triển khai, nhưng không đảm bảo mọi implementation đều có trạng thái `METRICS_ONLY` hoặc API chuyển trạng thái tương ứng.

Resilience4j hỗ trợ trạng thái này qua API native của `io.github.resilience4j.circuitbreaker.CircuitBreaker`, với phương thức `transitionToMetricsOnlyState()`. Để sử dụng, ứng dụng cần truy cập đúng `CircuitBreakerRegistry` quản lý instance đang bảo vệ lời gọi. Nếu dự án dùng implementation khác, cần kiểm tra tài liệu của implementation đó; không nên giả định có thể gọi cùng phương thức hoặc có một thuộc tính YAML chung cho mọi implementation.

Với Spring Boot tích hợp Resilience4j, registry thường được auto-configure và có thể inject vào bean. Không tạo registry mới tùy tiện trong gateway, vì breaker lấy từ registry mới có thể không phải instance mà Spring Cloud/OpenFeign đang sử dụng. Cần xác nhận factory, Feign integration và code chuyển trạng thái cùng dùng registry/instance tương ứng.

## 3. Cấu hình ngưỡng vẫn cần thiết trong chế độ quan sát

`METRICS_ONLY` không thay thế cấu hình sliding window. Các tham số như `slidingWindowType`, `slidingWindowSize`, `minimumNumberOfCalls`, `failureRateThreshold`, `slowCallDurationThreshold` và `slowCallRateThreshold` vẫn xác định cách ghi nhận và đánh giá thống kê. Chúng là chính sách dự kiến sẽ được sử dụng khi breaker chuyển về chế độ bảo vệ bình thường.

Ví dụ cấu hình cho dependency tồn kho:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
```

Trong ví dụ, chính sách dự kiến mở breaker nếu có đủ ít nhất 20 mẫu và tỷ lệ lỗi đạt ngưỡng 40%, hoặc tỷ lệ lời gọi chậm đạt ngưỡng 50% theo cấu hình. Khi ở `METRICS_ONLY`, các số liệu vẫn được thu thập để đội vận hành xem liệu các điều kiện đó có thường xuyên xuất hiện hay không; breaker không từ chối traffic chỉ vì ngưỡng bị vượt.

Không nên tự thêm một thuộc tính như `mode: METRICS_ONLY` vào YAML nếu phiên bản Spring Cloud/Resilience4j đang dùng không định nghĩa thuộc tính đó. Cách chuyển trạng thái được mô tả dưới đây dùng API native của Resilience4j. Các cấu hình thuộc tính của Spring Boot và API runtime cần được kiểm tra theo đúng phiên bản dependency của dự án.

## 4. Chuyển breaker sang METRICS_ONLY khi ứng dụng khởi động

Với Resilience4j, có thể chuyển một instance sang `METRICS_ONLY` bằng `transitionToMetricsOnlyState()`. Ví dụ sau dùng profile riêng để chỉ bật chế độ quan sát khi profile được kích hoạt:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("observe-circuit-breaker")
public class CircuitBreakerObservationConfiguration {

    @Bean
    ApplicationRunner inventoryMetricsOnly(CircuitBreakerRegistry registry) {
        return args -> {
            CircuitBreaker breaker = registry.circuitBreaker("inventory");
            breaker.transitionToMetricsOnlyState();
        };
    }
}
```

Khi ứng dụng chạy với profile `observe-circuit-breaker`, bean lấy instance `inventory` từ registry và chuyển nó sang `METRICS_ONLY`. Cấu hình profile là ví dụ tổ chức triển khai; cần bảo đảm ID `inventory` là ID thực tế của lời gọi được bảo vệ.

Nếu một breaker được tạo bởi Spring Cloud CircuitBreaker factory hoặc OpenFeign, hãy xác nhận registry được inject ở đây chính là registry mà integration đó dùng. Nếu tên do `CircuitBreakerNameResolver` tạo ra, phải dùng đúng tên runtime thay vì đoán từ `@FeignClient(name = ...)`.

Không nên chuyển trạng thái trong mỗi request. Chuyển trạng thái là thao tác quản trị vòng đời breaker; thực hiện lặp lại có thể reset hoặc làm thay đổi thống kê theo semantics của implementation. Hãy đặt thao tác ở giai đoạn khởi tạo có kiểm soát hoặc trong một cơ chế quản trị riêng được bảo vệ.

## 5. Kiểm tra chế độ thực tế trước khi tin vào dashboard

Sau khi chuyển trạng thái, hãy xác nhận breaker thực sự ở `METRICS_ONLY`. Có thể đọc state từ API native:

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

if (breaker.getState() != CircuitBreaker.State.METRICS_ONLY) {
    throw new IllegalStateException(
            "Inventory circuit breaker is not in METRICS_ONLY mode");
}
```

Việc kiểm tra state đặc biệt quan trọng khi ứng dụng có nhiều registry, nhiều Feign client hoặc tên breaker được tạo tự động. Nếu dashboard hiển thị metric của một instance khác với instance đang bảo vệ traffic, kết luận từ chế độ quan sát sẽ sai.

Ngoài state, cần xác nhận:

- Breaker ID đang được gateway hoặc Feign client sử dụng.
- Registry mà code quản trị inject có cùng instance với integration đang chạy.
- Metric success/error của đúng ID tăng khi có request.
- Request vẫn đến dependency khi breaker ở `METRICS_ONLY`, kể cả khi tỷ lệ lỗi vượt ngưỡng.
- Không có một breaker khác ở `OPEN` nằm bên ngoài hoặc bên trong cùng đường gọi đang chặn traffic.

## 6. Kiểm thử rằng breaker vẫn cho phép lời gọi sau khi vượt ngưỡng

Một kiểm thử nhỏ có thể xác nhận đặc tính cốt lõi của `METRICS_ONLY`: kết quả lỗi được ghi nhận nhưng breaker không mở và lời gọi tiếp theo vẫn được thực thi.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

class MetricsOnlyCircuitBreakerTest {

    @Test
    void recordsFailuresButContinuesToPermitCalls() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory-observe", config);
        breaker.transitionToMetricsOnlyState();

        assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("dependency failed");
                }));

        assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("dependency failed again");
                }));

        AtomicInteger executions = new AtomicInteger();
        String result = breaker.executeSupplier(() -> {
            executions.incrementAndGet();
            return "still-permitted";
        });

        assertEquals(CircuitBreaker.State.METRICS_ONLY, breaker.getState());
        assertEquals(2, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(1, breaker.getMetrics().getNumberOfSuccessfulCalls());
        assertEquals(1, executions.get());
        assertEquals("still-permitted", result);
    }
}
```

Test này tạo đủ mẫu để tỷ lệ lỗi vượt ngưỡng 50%, nhưng breaker vẫn ở `METRICS_ONLY`. Lời gọi thứ ba vẫn chạy và trả kết quả bình thường. Khi kiểm thử trong dự án, cần dùng phiên bản Resilience4j có hỗ trợ trạng thái này và đảm bảo các assertion metric phù hợp với API của version đang quản lý.

## 7. Đọc metric trong thời gian chỉ quan sát

Khi chạy `METRICS_ONLY`, dashboard nên tập trung vào các số liệu sẽ giúp quyết định có bật enforcement hay chưa:

- Số lời gọi success, failed và ignored theo breaker ID.
- Failure rate và slow call rate cùng số mẫu buffered.
- Latency p50, p95, p99 từ HTTP client hoặc tracing.
- Exception class và cause chain, phân loại timeout, connection refused, DNS, HTTP 5xx và lỗi nghiệp vụ.
- Số request thực tế gửi tới backend, so sánh với số lần supplier được thực thi.
- Tỷ lệ fallback nếu ứng dụng vẫn dùng fallback cho exception thật.
- Trạng thái breaker theo từng replica và thời điểm tiến trình khởi động.

Với Micrometer/Actuator, Resilience4j có thể xuất các metric trong nhóm `resilience4j.circuitbreaker`. Một meter phổ biến là `resilience4j.circuitbreaker.calls`, được phân loại theo `kind` như `successful`, `failed`, `ignored` hoặc `not_permitted`. Trong `METRICS_ONLY`, kỳ vọng chính là success/error tiếp tục được ghi nhận và các lời gọi không bị breaker từ chối do ngưỡng. Tên meter/tag cuối cùng phụ thuộc version Micrometer và exporter, nên hãy khám phá endpoint metrics thực tế.

Metric failure rate chỉ có ý nghĩa khi đọc cùng `minimumNumberOfCalls`. Nếu số mẫu chưa đủ, giá trị failure rate có thể chưa xác định. Không nên kết luận policy an toàn chỉ từ một khoảng thời gian ít traffic hoặc một dashboard không có đủ mẫu.

## 8. So sánh số liệu quan sát với quyết định enforcement dự kiến

Trong giai đoạn quan sát, breaker không mở nên không có số `not_permitted` do chính instance `METRICS_ONLY` từ chối vì threshold. Để dự báo tác động khi bật enforcement, hãy dùng số mẫu và tỷ lệ đã thu thập để ước lượng thời điểm breaker sẽ mở, sau đó xem lượng request có thể bị chặn và fallback có đáp ứng nghiệp vụ không.

| Quan sát trong `METRICS_ONLY` | Câu hỏi trước khi bật enforcement |
|---|---|
| Failure rate thường xuyên vượt ngưỡng | Ngưỡng có quá thấp, hay dependency thực sự không ổn định? |
| Slow call rate cao nhưng failure rate thấp | Timeout và slow-call threshold có phản ánh SLO không? |
| Nhiều lỗi DNS hoặc connection refused | Cần sửa service discovery/network trước khi bật breaker? |
| Nhiều lỗi nghiệp vụ trong failed | `recordExceptions`/`ignoreExceptions` đã phân loại đúng chưa? |
| Lưu lượng thấp, ít khi đủ minimum samples | Cần gom failure domain hoặc điều chỉnh window/minimum calls? |
| Fallback thường xuyên trả dữ liệu không xác định | API phía trên và trải nghiệm người dùng đã xử lý trạng thái này chưa? |
| Một số replica có tỷ lệ lỗi khác biệt | Có vấn đề theo node, zone hoặc đường mạng riêng không? |

Không nên lấy failure rate quan sát trong một khoảng thời gian ngắn rồi bật enforcement ngay. Hãy quan sát qua cả giờ cao điểm, thấp điểm, rollout, thay đổi tải và các điều kiện mạng khác nhau. Với dependency ít traffic, có thể cần một thời gian dài hơn để đủ mẫu đại diện.

## 9. `METRICS_ONLY` không thay thế timeout, bulkhead hoặc rate limiter

Vì `METRICS_ONLY` luôn cho phép lời gọi đi qua, nó không ngăn request tiếp tục đổ vào backend đang chậm hoặc lỗi. Nếu dependency giữ connection lâu, số request đang xử lý vẫn có thể tăng, thread/connection pool vẫn có thể cạn và lỗi có thể lan sang service gọi.

Trong giai đoạn quan sát, cần giữ các biện pháp bảo vệ độc lập:

- **Connect/read/response timeout:** giới hạn thời gian chờ ở HTTP client.
- **Deadline tổng thể:** giới hạn thời gian của toàn bộ request qua nhiều dependency.
- **Bulkhead:** giới hạn số tác vụ đồng thời và bảo vệ thread/connection pool.
- **Rate limiter hoặc gateway quota:** giới hạn lưu lượng nếu backend có năng lực tiếp nhận hữu hạn.
- **Retry có giới hạn:** tránh retry khuếch đại tải khi dependency đang suy giảm.
- **Fallback:** phản hồi có ý nghĩa khi supplier thực sự thất bại; fallback không ngăn lời gọi ban đầu.

Không nên đưa một dependency đang quá tải vào `METRICS_ONLY` nếu hệ thống chưa có giới hạn timeout/concurrency phù hợp và backend không thể chịu thêm request. Mục đích của chế độ này là quan sát policy trong điều kiện vận hành an toàn, không phải tắt bỏ toàn bộ cơ chế bảo vệ.

## 10. Fallback vẫn có thể chạy khi supplier thật sự lỗi

`METRICS_ONLY` không chặn lời gọi vì breaker threshold, nhưng supplier vẫn có thể ném exception. Nếu ứng dụng dùng `CircuitBreaker.run` với fallback hoặc Feign fallback, lỗi thật vẫn có thể đi vào fallback theo cách tích hợp đang dùng.

Ví dụ:

```java
return circuitBreaker.run(
        () -> inventoryClient.find(sku),
        error -> InventoryView.unavailable(sku)
);
```

Trong chế độ quan sát, khi supplier thành công, breaker ghi nhận success. Khi supplier ném timeout, breaker ghi nhận lỗi và fallback có thể trả `unavailable`. Khi một request tiếp theo đến, breaker vẫn cho phép supplier chạy dù failure rate đã vượt ngưỡng. Như vậy, fallback vẫn xử lý lỗi thực tế nhưng không được gọi chỉ vì breaker đã mở, vì breaker không chuyển sang `OPEN` do threshold trong `METRICS_ONLY`.

Điều này giúp đo tỷ lệ lỗi và tỷ lệ fallback có thể xảy ra khi traffic vẫn được phép đi qua. Tuy nhiên, fallback không được dùng để che giấu mọi exception. Hãy giữ log, trace và metric theo nguyên nhân, đồng thời trả trạng thái nghiệp vụ trung thực thay vì biến dữ liệu không xác định thành kết quả thành công giả.

## 11. Chuyển từ quan sát sang bảo vệ thực tế

Sau khi thu thập đủ dữ liệu và xác nhận ngưỡng phù hợp, cần chuyển breaker về trạng thái vận hành bình thường. Với Resilience4j native API, có thể dùng `transitionToClosedState()` để chuyển instance về `CLOSED`:

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

if (breaker.getState() == CircuitBreaker.State.METRICS_ONLY) {
    breaker.transitionToClosedState();
}
```

Đây là thao tác thay đổi runtime state. Cần thực hiện có kiểm soát và xác nhận semantics reset/statistics của phiên bản Resilience4j đang dùng; không nên giả định sliding window trong giai đoạn quan sát sẽ được giữ nguyên sau khi chuyển trạng thái. Hãy lưu hoặc xuất số liệu quan sát trước khi chuyển nếu cần phân tích so sánh.

Trước khi bật enforcement, nên:

1. Xác nhận đúng breaker ID và registry đang bảo vệ traffic.
2. Thu thập đủ mẫu trong các điều kiện tải đại diện.
3. Kiểm tra failure/slow call rate và nguyên nhân exception.
4. Xác nhận timeout, bulkhead, rate limit và fallback đã bảo vệ hệ thống.
5. Đánh giá số request có thể bị chặn khi breaker mở và tác động đến nghiệp vụ.
6. Chọn `minimumNumberOfCalls`, sliding window, failure threshold, slow-call threshold và wait duration phù hợp.
7. Chuyển một phạm vi nhỏ hoặc một nhóm replica sang enforcement trước nếu quy trình triển khai cho phép.
8. Theo dõi `OPEN`, `HALF_OPEN`, `not_permitted`, fallback và backend health sau khi bật.
9. Có kế hoạch rollback về cấu hình an toàn nếu breaker mở quá thường xuyên hoặc chặn nhầm chức năng.

Việc chuyển sang `CLOSED` không phải là bằng chứng dependency đã khỏe. Đó là thao tác bật lại state machine theo policy đã cấu hình. Nếu backend vẫn lỗi, breaker có thể nhanh chóng mở lại sau khi đủ mẫu.

## 12. Giới hạn và rủi ro khi chạy chỉ quan sát

`METRICS_ONLY` có một số giới hạn cần đưa vào quyết định vận hành:

- **Không bảo vệ backend khỏi traffic lỗi:** mọi lời gọi vẫn được phép, kể cả khi tỷ lệ lỗi vượt ngưỡng.
- **Không mô phỏng hành vi bị từ chối:** không thể suy ra chính xác số `not_permitted` thực tế nếu breaker đã ở `OPEN`; chỉ có thể ước lượng từ traffic và ngưỡng.
- **Không nhân bản traffic:** nó quan sát request thật. Muốn shadow traffic riêng cần một cơ chế mirroring khác và phải đánh giá tác động tải.
- **Trạng thái thường cục bộ theo tiến trình:** mỗi replica có thể cần chuyển sang chế độ quan sát riêng; cùng tên không tự đồng bộ state giữa các JVM.
- **Metric vẫn có thể thiếu mẫu:** traffic thấp hoặc exception bị ignore có thể khiến cửa sổ không đạt `minimumNumberOfCalls`.
- **Fallback có thể làm che khuất tác động:** cần metric riêng cho fallback và phân biệt kết quả supplier với kết quả trả cho caller.
- **Implementation khác có thể không hỗ trợ:** API chung của Spring Cloud không đảm bảo chế độ này có mặt ở mọi backend.

Nếu cần đánh giá toàn cụm, phải tổng hợp metric theo replica và dependency. Không nên chỉ nhìn một pod hoặc một breaker instance rồi kết luận policy đã an toàn cho toàn bộ hệ thống.

## 13. Kiểm thử và xác nhận trước khi triển khai

Trước khi bật chế độ quan sát trong production, hãy kiểm thử hành vi với một breaker độc lập và sau đó kiểm tra tích hợp Spring:

1. Chuyển breaker sang `METRICS_ONLY` và xác nhận `getState()` trả đúng state.
2. Gửi các lời gọi thành công; xác nhận success counter tăng.
3. Gửi đủ số lỗi để failure rate vượt ngưỡng; xác nhận failed counter tăng nhưng state không chuyển `OPEN`.
4. Gửi thêm lời gọi sau khi vượt ngưỡng; xác nhận supplier vẫn được thực thi.
5. Xác nhận fallback chạy khi supplier thật sự ném exception, nhưng không chạy chỉ vì threshold bị vượt.
6. Xác nhận metric/Actuator gắn với đúng breaker ID.
7. Kiểm tra từng replica sau khi bật profile hoặc thao tác quản trị.
8. Chuyển về `CLOSED` trong môi trường test và xác nhận enforcement hoạt động như mong đợi.
9. Kiểm tra timeout, bulkhead và rate limiter vẫn có hiệu lực trong thời gian `METRICS_ONLY`.

Không chỉ kiểm tra rằng ứng dụng khởi động thành công hoặc YAML được nạp. Cần xác nhận state thực tế, counters và hành vi supplier khi failure rate vượt ngưỡng.

## 14. Quy trình vận hành đề xuất

Một đợt thử nghiệm chỉ quan sát có thể được tổ chức như sau:

1. Chọn một dependency có traffic đủ đại diện và một breaker ID ổn định.
2. Khai báo sliding window, minimum calls và threshold dự kiến.
3. Bật `METRICS_ONLY` bằng API mà implementation hỗ trợ; với Resilience4j, dùng native registry và `transitionToMetricsOnlyState()`.
4. Xác minh đúng instance đã chuyển trạng thái và metric đang được ghi nhận.
5. Quan sát success, failed, ignored, latency, fallback và exception theo dependency qua các điều kiện tải.
6. Đánh giá số lần policy sẽ mở mạch, số request có thể bị chặn và tác động của fallback.
7. Điều chỉnh ngưỡng dựa trên dữ liệu, không chỉ dựa trên một vài lỗi đầu tiên.
8. Chuyển sang `CLOSED` để bật enforcement theo kế hoạch có kiểm soát.
9. Theo dõi state transition, `not_permitted`, probe `HALF_OPEN` và SLO sau khi bật.

Chế độ `METRICS_ONLY` của Resilience4j cho phép quan sát lỗi và độ trễ của dependency trong khi vẫn cho lời gọi đi qua. Nó hữu ích để kiểm chứng policy trước khi bật circuit breaker thực sự, nhưng không thay thế timeout, bulkhead hoặc rate limiting và không bảo vệ backend khi sự cố xảy ra. Chỉ chuyển sang enforcement sau khi đã xác nhận đúng instance, đủ mẫu, ngưỡng phù hợp và fallback có thể xử lý các lời gọi bị lỗi hoặc bị từ chối.
