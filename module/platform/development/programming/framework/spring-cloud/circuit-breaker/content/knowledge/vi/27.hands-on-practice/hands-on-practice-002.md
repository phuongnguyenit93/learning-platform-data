# Đo chuỗi CLOSED, OPEN, HALF_OPEN rồi phục hồi

Bài thực hành này dựng một dependency giả lập có thể chuyển từ trạng thái lỗi sang khỏe, đặt Resilience4j CircuitBreaker trước lời gọi và đo toàn bộ chuỗi `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`. Ta sẽ đếm số lần supplier thực sự gọi dependency, quan sát event chuyển trạng thái và xác minh rằng breaker từ chối request khi đang `OPEN`.

Mục tiêu là chứng minh bằng số liệu rằng circuit breaker bảo vệ đúng ranh giới lời gọi: khi dependency lỗi đủ ngưỡng, breaker mở; trong thời gian mở, request mới không chạm dependency; khi dependency phục hồi, một số probe giới hạn được cho phép; nếu probe thành công, breaker đóng lại và lưu lượng bình thường được tiếp tục.

## 1. Kịch bản và kết quả cần đạt

Ta mô phỏng một `Inventory Service` mà `Order Service` gọi đồng bộ. Dependency ban đầu luôn ném lỗi, sau đó được chuyển sang trạng thái khỏe bằng một cờ trong bộ nhớ.

| Giai đoạn | Dependency | Circuit breaker | Kết quả mong đợi |
| --- | --- | --- | --- |
| Bắt đầu | Lỗi | `CLOSED` | Lời gọi được thực hiện và kết quả được ghi nhận |
| Đủ số mẫu lỗi | Lỗi | Chuyển sang `OPEN` | Tỷ lệ lỗi vượt ngưỡng |
| Gửi thêm request | Chưa phục hồi | `OPEN` | Bị từ chối; bộ đếm dependency không tăng |
| Hết thời gian mở | Đã phục hồi | `HALF_OPEN` | Chỉ số probe được cấu hình mới được phép chạy |
| Probe thành công | Khỏe | `CLOSED` | Breaker đóng lại và cho phép lời gọi bình thường |

Trong bài lab, cấu hình cửa sổ đếm bốn lời gọi, cần tối thiểu bốn mẫu và đặt ngưỡng lỗi 50%. Bốn lần gọi lỗi liên tiếp tạo failure rate 100%, đủ điều kiện mở breaker. Sau hai giây, breaker tự chuyển sang `HALF_OPEN` và cho phép hai probe. Cả hai probe thành công sẽ đưa breaker về `CLOSED`.

## 2. Chuẩn bị dependency và test

Trong một ứng dụng Spring Boot dùng Spring Cloud CircuitBreaker với Resilience4j, thêm starter backend và dependency kiểm thử. Phiên bản nên được quản lý bằng Spring Cloud BOM tương thích với Spring Boot của dự án:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Starter Resilience4j của Spring Cloud cung cấp factory để mã ứng dụng gọi circuit breaker. Bài lab dùng API gốc `io.github.resilience4j.circuitbreaker.CircuitBreaker` trong một unit test độc lập để có thể đọc state, metrics và event trực tiếp. Đây là cùng cơ chế Resilience4j được Spring Cloud backend sử dụng; ở phần sau ta sẽ nối lại với `CircuitBreakerFactory` của ứng dụng.

## 3. Khai báo cấu hình thử nghiệm

Tạo cấu hình tương đương trong `application-test.yml` để dùng khi chạy ứng dụng Spring Cloud:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 100
        waitDurationInOpenState: 2s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: true
```

Ý nghĩa các giá trị:

- `slidingWindowType: COUNT_BASED` và `slidingWindowSize: 4`: chỉ xét bốn kết quả gần nhất.
- `minimumNumberOfCalls: 4`: chỉ tính tỷ lệ sau khi có đủ bốn lời gọi được ghi nhận.
- `failureRateThreshold: 50`: tỷ lệ lỗi từ 50% trở lên sẽ mở breaker.
- `slowCallDurationThreshold: 1s`: lời gọi dài hơn một giây được phân loại là chậm.
- `slowCallRateThreshold: 100`: không dùng slow-call rate để mở breaker trong kịch bản này; bài lab tập trung vào lỗi được mô phỏng.
- `waitDurationInOpenState: 2s`: thời gian ở `OPEN` trước khi thử phục hồi.
- `permittedNumberOfCallsInHalfOpenState: 2`: cho phép hai lời gọi probe.
- `automaticTransitionFromOpenToHalfOpenEnabled: true`: breaker tự chuyển sang `HALF_OPEN` sau thời gian mở, không cần đợi một request mới kích hoạt chuyển trạng thái.

Trong unit test bên dưới, ta tạo `CircuitBreakerConfig` bằng Java với cùng giá trị để bài kiểm thử độc lập, nhanh và không phụ thuộc việc Spring nạp profile. Khi tích hợp vào ứng dụng, giữ ID `inventory` thống nhất giữa YAML và mã gọi.

## 4. Viết test mô phỏng dependency lỗi rồi phục hồi

Tạo file test `CircuitBreakerRecoveryTest.java` trong source test của module. Dependency giả lập dùng `AtomicBoolean` để điều khiển khả năng phản hồi và `AtomicInteger` để đếm số lần supplier thực sự chạy.

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CircuitBreakerRecoveryTest {

    @Test
    void measuresClosedOpenHalfOpenAndRecovery() throws InterruptedException {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50)
            .slowCallDurationThreshold(Duration.ofSeconds(1))
            .slowCallRateThreshold(100)
            .waitDurationInOpenState(Duration.ofSeconds(2))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(true)
            .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
        AtomicBoolean dependencyAvailable = new AtomicBoolean(false);
        AtomicInteger dependencyCalls = new AtomicInteger();
        CountDownLatch halfOpenReached = new CountDownLatch(1);
        List<String> transitions = new CopyOnWriteArrayList<>();

        Supplier<String> dependencyCall = () -> {
            dependencyCalls.incrementAndGet();
            if (!dependencyAvailable.get()) {
                throw new IllegalStateException("inventory is unavailable");
            }
            return "inventory:stock=12";
        };

        breaker.getEventPublisher().onStateTransition(event -> {
            CircuitBreaker.State from = event.getStateTransition().getFromState();
            CircuitBreaker.State to = event.getStateTransition().getToState();
            transitions.add(from + " -> " + to);
            if (to == CircuitBreaker.State.HALF_OPEN) {
                halfOpenReached.countDown();
            }
        });

        // Giai đoạn 1: breaker CLOSED, bốn lời gọi dependency đều thất bại.
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        for (int i = 0; i < 4; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(dependencyCall))
                .isInstanceOf(IllegalStateException.class);
        }

        // Đủ bốn mẫu, failure rate 100% nên breaker chuyển sang OPEN.
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(4);
        assertThat(breaker.getMetrics().getFailureRate()).isEqualTo(100.0f);
        assertThat(dependencyCalls.get()).isEqualTo(4);

        // Giai đoạn 2: request mới bị từ chối trước khi supplier chạy.
        assertThatThrownBy(() -> breaker.executeSupplier(dependencyCall))
            .isInstanceOf(CallNotPermittedException.class);
        assertThat(breaker.getMetrics().getNumberOfNotPermittedCalls()).isEqualTo(1);
        assertThat(dependencyCalls.get()).isEqualTo(4);

        // Giai đoạn 3: dependency phục hồi; chờ breaker tự vào HALF_OPEN.
        dependencyAvailable.set(true);
        assertThat(halfOpenReached.await(5, TimeUnit.SECONDS)).isTrue();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.HALF_OPEN);

        // Giai đoạn 4: hai probe được phép chạy và đều thành công.
        assertThat(breaker.executeSupplier(dependencyCall))
            .isEqualTo("inventory:stock=12");
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.HALF_OPEN);

        assertThat(breaker.executeSupplier(dependencyCall))
            .isEqualTo("inventory:stock=12");
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);

        // Tổng số lần chạm dependency: 4 lỗi + 2 probe thành công.
        // Lời gọi bị từ chối khi OPEN không làm bộ đếm tăng.
        assertThat(dependencyCalls.get()).isEqualTo(6);
        assertThat(transitions).contains(
            "CLOSED -> OPEN",
            "OPEN -> HALF_OPEN",
            "HALF_OPEN -> CLOSED"
        );
    }
}
```

Test dùng `CountDownLatch` để chờ event chuyển sang `HALF_OPEN` thay vì đoán thời điểm bằng một khoảng `sleep` cố định. Thời gian chờ tối đa năm giây chỉ là giới hạn để test thất bại rõ ràng nếu scheduler không chuyển trạng thái. Nếu test timeout, kiểm tra `automaticTransitionFromOpenToHalfOpenEnabled`, cấu hình thời gian mở và phiên bản Resilience4j.

## 5. Chạy test và đọc kết quả

Chạy riêng test bằng Maven Wrapper:

```bash
./mvnw -Dtest=CircuitBreakerRecoveryTest test
```

Nếu dùng Gradle, chạy test class tương ứng bằng task `test` và filter của dự án. Kết quả mong đợi trong lần chạy:

| Mốc | State | Số lần gọi dependency | Thống kê/quan sát |
| --- | --- | ---: | --- |
| Khởi tạo | `CLOSED` | 0 | Chưa có mẫu |
| Sau bốn lỗi | `OPEN` | 4 | 4 failed, failure rate 100% |
| Sau một request bị chặn | `OPEN` | 4 | 1 not permitted; supplier không chạy |
| Hết hai giây | `HALF_OPEN` | 4 | Event `OPEN -> HALF_OPEN` |
| Sau probe thứ nhất | `HALF_OPEN` | 5 | Một probe thành công; còn một permit trong đợt thử |
| Sau probe thứ hai | `CLOSED` | 6 | Event `HALF_OPEN -> CLOSED`; lưu lượng bình thường được cho phép |

Điểm quan trọng nhất là số lần gọi dependency bằng sáu, không phải bảy. Request thứ năm được gửi khi breaker đang `OPEN` bị từ chối ngay tại breaker, vì vậy supplier không tăng bộ đếm. Hai request cuối là probe thật trong `HALF_OPEN`.

## 6. Quan sát event và metrics trong lúc chạy

Event listener trong test ghi lại các lần chuyển trạng thái. Khi chạy ứng dụng thật, có thể ghi event ở mức log có cấu trúc hoặc đưa metric qua Micrometer. Các sự kiện cần theo dõi:

- `CLOSED -> OPEN`: tỷ lệ lỗi hoặc lời gọi chậm đạt ngưỡng.
- `OPEN -> HALF_OPEN`: hết thời gian mở và breaker bắt đầu thử phục hồi.
- `HALF_OPEN -> CLOSED`: các probe được phép đã đạt tiêu chí thành công.
- `HALF_OPEN -> OPEN`: probe thất bại hoặc tỷ lệ kết quả thử không đạt ngưỡng.
- Call not permitted: request bị chặn khi breaker không cho phép.

Với Resilience4j Micrometer integration, có thể theo dõi các meter như `resilience4j.circuitbreaker.calls`, `resilience4j.circuitbreaker.state`, `resilience4j.circuitbreaker.failure.rate` và `resilience4j.circuitbreaker.buffered.calls`. Tên meter và tag cần được xác minh qua `/actuator/metrics` hoặc `/actuator/prometheus` theo phiên bản đang dùng.

Không cộng lời gọi bị từ chối vào failure rate của dependency. Khi breaker `OPEN`, supplier không chạy; số lần bị từ chối là một tín hiệu riêng cho biết circuit breaker đang bảo vệ dependency khỏi request mới.

## 7. Nối bài lab với Spring Cloud CircuitBreaker Factory

Trong service Spring Cloud, mã nghiệp vụ thường gọi qua `CircuitBreakerFactory` thay vì thao tác trực tiếp với `CircuitBreaker` native:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult fetch(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

Tên `inventory` khớp với ID trong `resilience4j.circuitbreaker.instances.inventory`. Factory chọn Resilience4j backend đã được cấu hình bởi Spring Cloud. Fallback minh họa phù hợp cho truy vấn đọc nếu nghiệp vụ chấp nhận kết quả không khả dụng; với command có side effect như giữ hàng hoặc thanh toán, không trả về kết quả thành công giả khi breaker từ chối hoặc dependency timeout.

Unit test trước đó đo state trực tiếp trên một Resilience4j instance để minh họa rõ cơ chế. Khi kiểm thử factory trong ứng dụng, hãy gọi qua bean Spring thực tế và quan sát đúng backend instance bằng metrics/event integration mà phiên bản đang dùng hỗ trợ. Không tạo một `CircuitBreakerRegistry` độc lập rồi dùng state của nó để kết luận về breaker do factory quản lý; hai registry khác nhau có thể chứa hai instance cùng tên nhưng state riêng.

## 8. Thử nghiệm khi probe thất bại

Sau khi test phục hồi thành công chạy ổn định, thay đổi kịch bản để một trong hai probe vẫn thất bại. Ví dụ, chỉ cho dependency phục hồi sau probe đầu tiên hoặc đặt một cờ để probe đầu ném exception.

Kết quả cần quan sát:

- Breaker không đóng chỉ vì một probe thành công nếu vẫn còn probe cần thiết.
- Khi kết quả probe không đạt failure threshold, breaker quay lại `OPEN`.
- Trong lần `OPEN` tiếp theo, request mới tiếp tục bị từ chối và supplier không chạy.
- Sau một khoảng mở mới, breaker lại cho phép một đợt probe giới hạn.

Thử nghiệm này giúp thấy `HALF_OPEN` là một giai đoạn đánh giá phục hồi, không phải trạng thái đóng tạm thời. Số probe bị giới hạn để dependency không bị dồn toàn bộ lưu lượng ngay khi vừa phản hồi lại.

## 9. Những lỗi thường gặp khi chạy bài lab

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Breaker vẫn `CLOSED` sau bốn lần lỗi | Chưa đạt `minimumNumberOfCalls`, exception bị ignore hoặc không được ghi nhận | Kiểm tra cấu hình cửa sổ và quy tắc phân loại exception |
| Lần gọi thứ năm vẫn chạy supplier | Test dùng breaker khác, instance mới hoặc lời gọi không đi qua breaker | Dùng cùng instance cho toàn bộ kịch bản và đặt bộ đếm bên trong supplier |
| Không thấy `HALF_OPEN` | Automatic transition chưa bật hoặc test chờ sai thời hạn | Bật `automaticTransitionFromOpenToHalfOpenEnabled` và chờ state event |
| Breaker không đóng sau hai probe | Một probe lỗi, số permit khác cấu hình hoặc chưa đủ kết quả | Kiểm tra kết quả từng probe và `permittedNumberOfCallsInHalfOpenState` |
| Test lúc được lúc không | Dùng chung instance giữa test, dependency giả lập có trạng thái dùng chung hoặc chờ thời gian thiếu đồng bộ | Tạo breaker mới cho mỗi test, dùng latch/event và dọn tài nguyên |
| Metrics không khớp số lần gọi | Đang xem registry khác hoặc nhầm call-not-permitted với call failure | Xác minh cùng instance và phân loại riêng `not_permitted` |

Trong test tích hợp Spring, nhớ dùng cùng profile và breaker ID với cấu hình. Nếu nhiều test chia sẻ application context, trạng thái breaker có thể còn từ test trước; tạo instance riêng hoặc reset đúng lúc trong fixture kiểm thử.

## 10. Mở rộng bài thực hành

Sau khi hoàn thành kịch bản cơ bản, có thể làm thêm các phép đo sau:

1. **Thay đổi ngưỡng:** đặt `failureRateThreshold` thành 75% và cho ba trong bốn request thất bại; xác minh breaker mở khi tỷ lệ đạt ngưỡng.
2. **Sliding window:** tăng `slidingWindowSize` lên tám và `minimumNumberOfCalls` lên bốn; thử xen kẽ thành công/thất bại để xem cửa sổ trượt thay đổi tỷ lệ ra sao.
3. **Slow call:** làm dependency chờ hơn `slowCallDurationThreshold` nhưng vẫn trả thành công; quan sát slow-call rate độc lập với failure rate.
4. **Timeout:** bọc tác vụ bất đồng bộ bằng TimeLimiter; xác minh timeout được ghi nhận theo cấu hình và không nhầm slow-call threshold với cơ chế dừng request.
5. **Fallback:** đếm số lần fallback riêng; xác minh fallback không làm circuit breaker hiểu nhầm supplier thất bại thành thành công nếu mục tiêu là ghi nhận lỗi dependency.
6. **Nhiều replica:** chạy hai instance ứng dụng và quan sát mỗi breaker giữ state riêng; không giả định một instance mở thì instance kia cũng mở.

## 11. Tiêu chí hoàn thành

- Bốn lời gọi đầu tiên được thực hiện khi breaker `CLOSED` và đều thất bại.
- Breaker chuyển sang `OPEN` sau khi đủ mẫu và vượt failure threshold.
- Một request gửi khi `OPEN` nhận `CallNotPermittedException` hoặc đi vào fallback, nhưng không gọi dependency.
- Dependency được chuyển sang trạng thái khỏe trước giai đoạn probe.
- Breaker tự chuyển sang `HALF_OPEN` sau thời gian chờ đã cấu hình.
- Hai probe được phép chạy; khi cả hai thành công, breaker chuyển về `CLOSED`.
- Event ghi nhận đủ ba chuyển trạng thái chính và bộ đếm dependency xác nhận không có request nào lọt qua khi breaker `OPEN`.

Khi hoàn thành các bước trên, bạn đã đo được toàn bộ vòng đời cơ bản của circuit breaker: phát hiện lỗi, ngăn lời gọi mới, thử phục hồi có giới hạn và mở lại lưu lượng khi dependency khỏe. Hãy giữ cấu hình, log event và số lần gọi làm bằng chứng khi thay đổi ngưỡng hoặc triển khai chính sách này vào service Spring Cloud thực tế.
