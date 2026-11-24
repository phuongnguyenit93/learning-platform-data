# Kiểm thử HALF_OPEN phục hồi thành công và mở lại khi lỗi

Sau khi circuit breaker chuyển từ `OPEN` sang `HALF_OPEN`, nó chỉ cho phép một số lượng lời gọi thăm dò giới hạn đến dịch vụ phụ thuộc. Kết quả của các lời gọi này quyết định mạch có thể trở lại `CLOSED` hay phải mở lại `OPEN`. Đây là thời điểm quan trọng cần kiểm thử: nếu các lời gọi thăm dò thành công, hệ thống phải phục hồi khả năng gọi phụ thuộc; nếu chúng tiếp tục thất bại hoặc chậm vượt ngưỡng, circuit breaker phải tiếp tục ngăn traffic.

Với Spring Cloud CircuitBreaker dùng Resilience4j, có thể kiểm thử state machine bằng API Resilience4j trực tiếp và kiểm thử thêm factory/fallback ở tầng Spring. Bài học này xây dựng hai kịch bản xác định: `HALF_OPEN` đóng mạch sau các probe thành công và `HALF_OPEN` mở lại sau các probe thất bại. Các ví dụ dùng số lượng probe nhỏ để dễ quan sát, sau đó mở rộng sang kiểm tra thời gian chờ, sự kiện và tích hợp ứng dụng.

## 1. Điều kiện chuyển trạng thái từ HALF_OPEN

Circuit breaker có ba trạng thái thường gặp:

- `CLOSED`: lời gọi được phép đi qua; kết quả được ghi nhận vào sliding window.
- `OPEN`: lời gọi bị từ chối ngay; supplier không được thực thi.
- `HALF_OPEN`: chỉ một số lượng giới hạn lời gọi thăm dò được phép chạy để đánh giá khả năng phục hồi.

Khi hết `waitDurationInOpenState`, circuit breaker có thể chuyển sang `HALF_OPEN`. Với Resilience4j, nếu `automaticTransitionFromOpenToHalfOpenEnabled` tắt, trạng thái thường được chuyển khi có lời gọi tiếp theo sau khi thời gian mở mạch đã hết. Nếu bật, một tác vụ nền chuyển trạng thái mà không cần chờ request mới.

Trong `HALF_OPEN`, `permittedNumberOfCallsInHalfOpenState` quy định số lời gọi thăm dò tối đa. Khi đủ số kết quả thăm dò, Resilience4j đánh giá tỷ lệ lỗi và tỷ lệ lời gọi chậm theo cấu hình:

| Kết quả thăm dò | Hành vi mong đợi |
|---|---|
| Các probe hoàn tất và tỷ lệ lỗi/slow call dưới ngưỡng | Chuyển về `CLOSED`. |
| Các probe làm tỷ lệ lỗi đạt hoặc vượt ngưỡng | Chuyển lại `OPEN`. |
| Các probe làm tỷ lệ lời gọi chậm đạt hoặc vượt ngưỡng | Chuyển lại `OPEN`. |
| Đã hết số permit trong `HALF_OPEN` | Lời gọi mới bị từ chối bằng `CallNotPermittedException` cho đến khi có kết quả và trạng thái được đánh giá. |

`waitDurationInOpenState` và `permittedNumberOfCallsInHalfOpenState` có vai trò khác nhau. Tham số đầu tiên quyết định thời gian chờ trước khi thăm dò; tham số thứ hai giới hạn số probe. Không dùng số probe để thay thế thời gian mở mạch.

## 2. Thiết kế cấu hình kiểm thử xác định

Để kiểm thử state machine ổn định, nên dùng cấu hình nhỏ và kiểm soát rõ số probe. Ví dụ:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(10)
    .minimumNumberOfCalls(5)
    .failureRateThreshold(50)
    .slowCallDurationThreshold(Duration.ofSeconds(2))
    .slowCallRateThreshold(50)
    .waitDurationInOpenState(Duration.ofSeconds(10))
    .permittedNumberOfCallsInHalfOpenState(2)
    .automaticTransitionFromOpenToHalfOpenEnabled(false)
    .build();

CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
```

Với cấu hình này, circuit breaker dùng cửa sổ đếm 10 lời gọi và cần tối thiểu 5 mẫu để đánh giá tỷ lệ trong `CLOSED`. Khi ở `HALF_OPEN`, nó cho phép tối đa 2 probe. Đặt `automaticTransitionFromOpenToHalfOpenEnabled(false)` giúp bài kiểm thử state machine tự điều khiển thời điểm chuyển sang `HALF_OPEN` mà không phụ thuộc bộ lập lịch nền.

Trong unit test, có thể dùng `transitionToOpenState()` và `transitionToHalfOpenState()` để đưa circuit breaker đến trạng thái cần kiểm tra. Các phương thức chuyển trạng thái trực tiếp phù hợp cho kiểm thử hành vi sau khi đã ở trạng thái đó; chúng không thay thế kiểm thử thời gian `waitDurationInOpenState` của cấu hình production.

## 3. Kiểm thử phục hồi thành công và chuyển về CLOSED

Kịch bản đầu tiên mô phỏng dependency đã phục hồi. Circuit breaker đang `OPEN`, được đưa sang `HALF_OPEN`, sau đó hai lời gọi thăm dò đều thành công. Khi đã nhận đủ kết quả và tỷ lệ lỗi dưới ngưỡng, breaker phải trở lại `CLOSED`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenRecoveryTest {

    private CircuitBreaker newBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .failureRateThreshold(50)
            .slowCallDurationThreshold(Duration.ofSeconds(2))
            .slowCallRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(10))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();

        return CircuitBreaker.of("inventory", config);
    }

    @Test
    void closesAfterAllHalfOpenProbesSucceed() {
        CircuitBreaker breaker = newBreaker();
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        assertEquals(CircuitBreaker.State.HALF_OPEN, breaker.getState());

        String first = breaker.executeSupplier(() -> "stock-available");
        assertEquals("stock-available", first);

        String second = breaker.executeSupplier(() -> "stock-available");
        assertEquals("stock-available", second);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
    }
}
```

Test này xác minh ba điều:

1. Circuit breaker bắt đầu ở `HALF_OPEN` trước khi probe chạy.
2. Hai supplier được cấp quyền đều hoàn tất thành công.
3. Sau khi đủ số probe, circuit breaker chuyển về `CLOSED`.

Không chỉ kiểm tra kết quả supplier. Nếu chỉ assert hai giá trị trả về, bài kiểm thử chưa chứng minh state machine đã đóng mạch. Hãy luôn xác nhận trạng thái cuối cùng.

## 4. Kiểm thử probe thất bại khiến circuit breaker mở lại

Kịch bản thứ hai mô phỏng dependency vẫn lỗi sau thời gian mở mạch. Hai probe đều ném exception được ghi nhận là failure. Khi đã đủ số kết quả và failure rate đạt ngưỡng, circuit breaker phải chuyển về `OPEN`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenReopenTest {

    private CircuitBreaker newBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(10))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();

        return CircuitBreaker.of("inventory", config);
    }

    @Test
    void reopensWhenHalfOpenProbesFail() {
        CircuitBreaker breaker = newBreaker();
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        assertEquals(CircuitBreaker.State.HALF_OPEN, breaker.getState());

        assertThrows(IllegalStateException.class, () ->
            breaker.executeSupplier(() -> {
                throw new IllegalStateException("inventory still unavailable");
            })
        );

        assertThrows(IllegalStateException.class, () ->
            breaker.executeSupplier(() -> {
                throw new IllegalStateException("inventory still unavailable");
            })
        );

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }
}
```

Hai probe đều thất bại nên tỷ lệ lỗi của tập probe đạt 100%, cao hơn ngưỡng 50%. Sau khi đủ hai kết quả, circuit breaker mở lại. Việc dùng hai lỗi rõ ràng tránh phụ thuộc vào cách xử lý trường hợp đúng bằng ngưỡng trong một bài kiểm thử cơ bản.

Nếu chỉ có một probe thất bại rồi dừng, circuit breaker có thể vẫn ở `HALF_OPEN` vì chưa đủ số kết quả được phép. Trong một số cấu hình/phiên bản, có thể đặt thêm giới hạn thời gian tối đa ở `HALF_OPEN` để xử lý trường hợp không đủ probe hoàn tất; hãy kiểm tra thuộc tính `maxWaitDurationInHalfOpenState` nếu phiên bản Resilience4j đang dùng hỗ trợ.

## 5. Xác minh lời gọi vượt quá số permit bị từ chối

Trong `HALF_OPEN`, `permittedNumberOfCallsInHalfOpenState` là số lời gọi thăm dò được cấp quyền. Khi đã dùng hết permit mà trạng thái chưa được đánh giá xong, lời gọi tiếp theo có thể bị từ chối. Khi hai probe đã thất bại và breaker chuyển về `OPEN`, mọi lời gọi mới cũng bị từ chối ngay.

Có thể xác minh supplier không chạy khi circuit breaker từ chối:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenPermissionTest {

    @Test
    void rejectsCallsAfterFailedProbesReopenTheBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(10))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();
        CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();
        AtomicInteger supplierCalls = new AtomicInteger();

        for (int i = 0; i < 2; i++) {
            assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("probe failed");
                })
            );
        }

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());

        assertThrows(CallNotPermittedException.class, () ->
            breaker.executeSupplier(() -> {
                supplierCalls.incrementAndGet();
                return "must not execute";
            })
        );

        assertEquals(0, supplierCalls.get());
    }
}
```

Đoạn test tự tạo breaker với hai permit và đưa nó sang `HALF_OPEN`. Phần quan trọng là kiểm tra `CallNotPermittedException` sau khi hai probe thất bại và xác nhận supplier không được thực thi.

Không xem `CallNotPermittedException` là một probe thất bại mới. Đây là kết quả từ chối của circuit breaker, không phải request đã được gửi đến dependency rồi thất bại.

## 6. Kiểm thử thời gian chuyển từ OPEN sang HALF_OPEN

Unit test dùng `transitionToHalfOpenState()` giúp kiểm tra nhanh và xác định hành vi sau khi mạch đã chuyển trạng thái. Tuy nhiên, cần có kiểm thử riêng cho cấu hình `waitDurationInOpenState` nếu muốn xác minh thời gian chờ thực tế.

Có hai cách chuyển trạng thái:

- **Chuyển khi có request tiếp theo:** `automaticTransitionFromOpenToHalfOpenEnabled(false)`. Sau khi hết thời gian `OPEN`, lời gọi tiếp theo kích hoạt quá trình chuyển sang `HALF_OPEN` và có thể trở thành probe.
- **Chuyển tự động:** `automaticTransitionFromOpenToHalfOpenEnabled(true)`. Resilience4j dùng scheduler để chuyển sang `HALF_OPEN` khi thời gian chờ kết thúc, kể cả chưa có request mới.

Ví dụ kiểm thử chế độ tự động với Awaitility:

```java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenTimerTest {

    @Test
    void movesToHalfOpenAfterOpenWaitDuration() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .waitDurationInOpenState(Duration.ofMillis(150))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(true)
            .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory-timer", config);
        breaker.transitionToOpenState();

        await().atMost(Duration.ofSeconds(2)).untilAsserted(() ->
            assertEquals(CircuitBreaker.State.HALF_OPEN, breaker.getState())
        );
    }
}
```

Test cần dependency `org.awaitility:awaitility` trong scope test nếu dự án chưa có. Awaitility chờ điều kiện với thời hạn trên thay vì dùng `Thread.sleep()` cố định. Thời gian 150 ms chỉ dành cho test; không dùng nó làm cấu hình production mặc định. Nếu dùng chế độ chuyển trạng thái theo request tiếp theo, hãy viết test gửi một request sau khi hết thời gian chờ và xác minh request đó được xử lý như probe.

## 7. Kiểm thử slow-call trong HALF_OPEN

Circuit breaker không chỉ đánh giá exception. Một probe có thể hoàn tất thành công về mặt kỹ thuật nhưng chậm hơn `slowCallDurationThreshold`. Nếu tỷ lệ slow call đạt `slowCallRateThreshold`, breaker vẫn có thể mở lại.

Ví dụ cấu hình kiểm thử:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slowCallDurationThreshold(Duration.ofMillis(20))
    .slowCallRateThreshold(50)
    .permittedNumberOfCallsInHalfOpenState(2)
    .build();
```

Khi kiểm thử slow call, cần tạo supplier có thời gian thực thi vượt ngưỡng. Vì test dựa trên đồng hồ hệ thống có thể dao động theo tải máy, nên dùng ngưỡng có khoảng cách đủ lớn so với thời gian thực thi và tránh đặt quá sát. Với logic nghiệp vụ, có thể trừu tượng hóa clock hoặc dùng test fixture của thư viện nếu phiên bản hỗ trợ.

Không kết luận dependency đã phục hồi chỉ vì probe không ném exception. Nếu response đến quá chậm so với SLO, circuit breaker cần tiếp tục bảo vệ caller.

## 8. Kiểm thử sự kiện chuyển trạng thái

Ngoài trạng thái cuối cùng, có thể đăng ký event listener để xác nhận chuỗi chuyển trạng thái:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenTransitionEventTest {

    @Test
    void recordsOpenHalfOpenClosedTransitions() {
        CircuitBreaker breaker = CircuitBreaker.of(
            "inventory-events",
            CircuitBreakerConfig.custom()
                .permittedNumberOfCallsInHalfOpenState(2)
                .build()
        );
        List<CircuitBreaker.StateTransition> transitions = new ArrayList<>();

        breaker.getEventPublisher().onStateTransition(event ->
            transitions.add(event.getStateTransition())
        );

        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();
        breaker.executeSupplier(() -> "probe-1-ok");
        breaker.executeSupplier(() -> "probe-2-ok");

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
        assertEquals(3, transitions.size());
        assertEquals(CircuitBreaker.StateTransition.CLOSED_TO_OPEN, transitions.get(0));
        assertEquals(CircuitBreaker.StateTransition.OPEN_TO_HALF_OPEN, transitions.get(1));
        assertEquals(CircuitBreaker.StateTransition.HALF_OPEN_TO_CLOSED, transitions.get(2));
    }
}
```

Event listener nên được đăng ký một lần trong test setup. Không gắn listener trong mỗi lần gọi supplier, nếu không một sự kiện chuyển trạng thái có thể kích hoạt callback trùng. Với test thất bại, chuỗi mong đợi tương ứng là `CLOSED_TO_OPEN`, `OPEN_TO_HALF_OPEN` và `HALF_OPEN_TO_OPEN`.

## 9. Kiểm thử qua Spring Cloud CircuitBreaker factory

Các test dùng `CircuitBreaker` trực tiếp tập trung xác minh state machine của Resilience4j. Ở tầng ứng dụng, cần kiểm tra thêm factory Spring Cloud CircuitBreaker tạo đúng breaker ID và fallback được gọi đúng khi supplier lỗi hoặc mạch từ chối.

Ví dụ service:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> factory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> factory,
            InventoryClient inventoryClient) {
        this.factory = factory;
        this.inventoryClient = inventoryClient;
    }

    public String getStock(String sku) {
        return factory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> "temporarily-unavailable"
        );
    }
}
```

Trong integration test với Spring context, có thể mock `InventoryClient`, cấu hình circuit breaker instance `inventory` với hai probe, sau đó dùng cùng Resilience4j registry để đưa breaker vào trạng thái `OPEN` rồi `HALF_OPEN`. Gọi service hai lần với client trả thành công để xác nhận breaker đóng lại; chạy test khác với client tiếp tục ném exception để xác nhận breaker mở lại.

Điểm cần xác minh là registry và factory đang dùng cùng instance có ID `inventory`. Không tạo một `CircuitBreakerRegistry` độc lập trong test rồi giả định nó điều khiển breaker nội bộ của factory. Nếu phiên bản tích hợp không expose registry trực tiếp, có thể kiểm tra qua factory và cấu hình test riêng, hoặc dùng test ở tầng Resilience4j cho state machine rồi kiểm thử factory/fallback độc lập.

## 10. Kiểm thử đồng thời và số permit

Trong production, các probe có thể chạy đồng thời. Với `permittedNumberOfCallsInHalfOpenState: 2`, tối đa hai lời gọi thăm dò được cấp quyền. Các request khác có thể bị từ chối trong khi hai probe chưa hoàn tất.

Để kiểm thử đồng thời, có thể giữ hai supplier đang chạy bằng `CountDownLatch`, gửi request thứ ba và xác nhận nó bị từ chối. Sau đó thả latch để hai probe hoàn tất và xác minh state transition theo kết quả. Khi viết test dạng này:

- Dùng timeout hữu hạn cho `await()` trên latch để test không treo vô hạn.
- Giải phóng latch trong `finally` để không giữ thread nếu assertion thất bại.
- Không dựa vào thứ tự hoàn tất của hai probe nếu test không kiểm soát thứ tự.
- Phân biệt rejection do hết permit với failure từ supplier.
- Kiểm tra supplier thứ ba không được thực thi.

Kiểm thử tuần tự thường đủ cho logic chuyển trạng thái cơ bản. Kiểm thử đồng thời bổ sung bằng chứng rằng giới hạn permit hoạt động đúng khi có nhiều request đến cùng lúc.

## 11. Các lỗi kiểm thử thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Test mong đợi `HALF_OPEN` nhưng breaker vẫn `OPEN` | Chưa hết `waitDurationInOpenState` hoặc chưa kích hoạt chuyển trạng thái theo cấu hình. | Dùng chuyển trạng thái tường minh trong unit test hoặc chờ bằng Awaitility cho timer thật. |
| Hai probe thành công nhưng breaker chưa `CLOSED` | Chưa đủ số permit/probe được hoàn tất hoặc một probe chưa kết thúc. | Xác minh `permittedNumberOfCallsInHalfOpenState` và mọi publisher/future đã hoàn tất. |
| Một probe lỗi nhưng breaker chưa `OPEN` | Chưa đủ số kết quả để đánh giá hoặc tỷ lệ chưa đạt ngưỡng. | Gửi đủ probe và kiểm tra `failureRateThreshold`. |
| Test thỉnh thoảng thất bại do thời gian | Dùng `Thread.sleep()` hoặc slow-call threshold quá sát thời gian thực thi. | Dùng Awaitility cho thời gian chờ và tạo khoảng cách đủ lớn cho ngưỡng slow call. |
| Supplier vẫn chạy khi nghĩ breaker đang `OPEN` | Test điều khiển nhầm instance hoặc factory dùng ID khác. | Dùng đúng instance/registry và kiểm tra breaker ID. |
| Rejection bị tính như probe thất bại | Test gộp `CallNotPermittedException` với exception từ supplier. | Phân biệt lời gọi bị từ chối và lời gọi đã thực thi. |
| Test bị treo ở HALF_OPEN | Một probe không hoàn tất hoặc publisher reactive chưa được subscribe/kết thúc. | Hoàn tất tất cả probe, kiểm tra subscription và dùng timeout cho test. |

## 12. Checklist cho hai kịch bản chính

**Phục hồi thành công:**

- [ ] Đưa circuit breaker từ `OPEN` sang `HALF_OPEN`.
- [ ] Xác nhận số probe được cấp quyền đúng cấu hình.
- [ ] Cho tất cả probe hoàn tất thành công và không vượt slow-call threshold.
- [ ] Xác nhận trạng thái cuối là `CLOSED`.
- [ ] Xác nhận lời gọi mới được phép đi qua sau khi đóng mạch.

**Phục hồi thất bại:**

- [ ] Đưa circuit breaker từ `OPEN` sang `HALF_OPEN`.
- [ ] Cho đủ số probe được phép thực thi.
- [ ] Làm probe thất bại hoặc chậm đủ để vượt ngưỡng.
- [ ] Xác nhận trạng thái cuối quay về `OPEN`.
- [ ] Xác nhận lời gọi mới bị từ chối và supplier không chạy.
- [ ] Xác nhận event/metrics phản ánh đúng `HALF_OPEN_TO_OPEN` và số lần not permitted.

## 13. Đọc metrics và event khi kiểm thử

Khi dùng Micrometer với Resilience4j, có thể quan sát trạng thái breaker, số lời gọi thành công, thất bại, bị từ chối, tỷ lệ lỗi và tỷ lệ lời gọi chậm. Tên meter và tag cụ thể phụ thuộc phiên bản cùng cấu hình binder; hãy kiểm tra các meter thực tế qua Actuator hoặc registry của test.

Với hai kịch bản chính, kết quả mong đợi:

| Chỉ số/quan sát | Probe thành công | Probe thất bại |
|---|---|---|
| Trạng thái cuối | `CLOSED` | `OPEN` |
| Chuyển trạng thái cuối | `HALF_OPEN_TO_CLOSED` | `HALF_OPEN_TO_OPEN` |
| Supplier probe | Được thực thi đủ số permit | Được thực thi đủ số permit |
| Request sau khi đánh giá | Được phép đi qua | Bị từ chối sớm |
| Failure rate của probe | Dưới ngưỡng | Đạt/vượt ngưỡng |
| Fallback | Không cần nếu probe thành công | Có thể chạy cho request bị từ chối hoặc lỗi theo cách service tích hợp |

Không dùng riêng log để kết luận state machine đúng. Kết hợp assertion trạng thái, số supplier invocation, event và metrics để kiểm tra cả hành vi lẫn khả năng quan sát.

## 14. Nguyên tắc viết test ổn định

Tách unit test state machine khỏi integration test của Spring context. Trong unit test, dùng cấu hình nhỏ và chuyển trạng thái tường minh để kiểm tra nhánh phục hồi thành công/thất bại mà không chờ đồng hồ. Trong integration test, xác minh `waitDurationInOpenState`, auto-transition, factory ID, fallback và metrics bằng thời hạn chờ có giới hạn.

Không dùng `Thread.sleep()` dài để đồng bộ test. Không giả định một exception bất kỳ là rejection; `CallNotPermittedException` cho biết supplier không chạy, còn exception từ supplier là kết quả của một probe đã thực thi. Không chỉ assert fallback mà bỏ qua trạng thái cuối. Cuối cùng, luôn kiểm tra số probe, số lần supplier được gọi và trạng thái circuit breaker.

Một bộ test tốt chứng minh được cả hai hướng: khi dependency phục hồi, `HALF_OPEN` đóng mạch và cho phép traffic trở lại; khi dependency vẫn lỗi hoặc chậm, `HALF_OPEN` mở mạch lần nữa và ngăn request mới. Đây là bằng chứng quan trọng để xác nhận Spring Cloud CircuitBreaker cùng Resilience4j bảo vệ đúng dịch vụ phụ thuộc trong quá trình phục hồi.
