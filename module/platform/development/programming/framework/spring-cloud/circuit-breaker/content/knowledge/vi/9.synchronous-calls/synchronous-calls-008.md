# Kiểm chứng rằng OPEN không gọi lại hệ thống phụ thuộc

Khi circuit breaker ở trạng thái `OPEN`, mọi lời gọi đồng bộ mới đi qua breaker phải bị từ chối trước khi supplier thực thi. Điều này bảo đảm ứng dụng không tiếp tục gọi một dịch vụ phụ thuộc đang suy giảm trong khoảng thời gian mạch mở. Để chứng minh hành vi đó, cần kiểm tra số lần lời gọi thực sự chạm đến client hoặc hệ thống phụ thuộc, đồng thời xác minh ứng dụng vẫn xử lý được yêu cầu qua fallback.

Một kiểm thử chỉ xác nhận phương thức trả về fallback là chưa đủ. Fallback có thể trả về đúng dữ liệu trong khi supplier vẫn bị gọi lại. Bằng chứng quan trọng là số lần gọi dependency không tăng sau khi breaker đã mở.

## 1. Hành vi của lời gọi đồng bộ khi breaker OPEN

Trong trạng thái `CLOSED`, circuit breaker cho phép supplier gọi dịch vụ phụ thuộc và ghi nhận kết quả. Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng sau khi có đủ số mẫu tối thiểu, breaker chuyển sang `OPEN`. Trong thời gian này, lời gọi mới bị từ chối ngay tại breaker:

1. Mã nghiệp vụ nhận yêu cầu đồng bộ.
2. Circuit breaker kiểm tra trạng thái hiện tại.
3. Nếu trạng thái là `OPEN`, breaker không chạy supplier và phát sinh `CallNotPermittedException`.
4. Lớp tích hợp hoặc mã nghiệp vụ có thể xử lý lỗi từ chối bằng fallback.
5. Kết quả fallback được trả về cho bên gọi; dịch vụ phụ thuộc không nhận thêm request từ supplier đó.

```text
Yêu cầu đồng bộ
       |
       v
Circuit breaker
       |
       +---- CLOSED ----> Supplier ----> HTTP/RPC client ----> Dependency
       |
       +---- OPEN ------> Từ chối nhanh
                              |
                              v
                           Fallback
                              |
                              v
                       Kết quả cho caller
```

`OPEN` chỉ ngăn các lời gọi mới đi qua breaker. Những lời gọi đã được cho phép trước khi breaker mở vẫn có thể đang chạy và hoàn tất. Circuit breaker không tự hủy các request đang bay. Vì vậy, kiểm thử cần phân biệt lời gọi mới sau khi mở với các lời gọi đã bắt đầu trước đó.

## 2. Chuẩn bị cấu hình kiểm thử có thể tái lập

Để kiểm thử không phụ thuộc vào lưu lượng ngẫu nhiên, hãy dùng cửa sổ đếm nhỏ và số mẫu tối thiểu cố định. Ví dụ đặt cấu hình trong `src/test/resources/application-test.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 2
        minimumNumberOfCalls: 2
        failureRateThreshold: 50
        waitDurationInOpenState: 1m
        permittedNumberOfCallsInHalfOpenState: 1
```

Với cấu hình này, hai lời gọi thất bại liên tiếp tạo failure rate 100% trong cửa sổ gồm hai lời gọi, vượt ngưỡng 50% và làm breaker chuyển sang `OPEN`. `waitDurationInOpenState: 1m` giữ breaker ở trạng thái mở đủ lâu để kiểm tra lời gọi tiếp theo mà không vô tình bước sang `HALF_OPEN`.

Trong production, không nên dùng cửa sổ nhỏ như ví dụ nếu lưu lượng thực tế không phù hợp. Đây là cấu hình riêng cho kiểm thử; cấu hình môi trường thật cần dựa trên lưu lượng, độ trễ và mục tiêu bảo vệ dịch vụ.

## 3. Kiểm thử API gốc của Resilience4j bằng bộ đếm lời gọi

Với API gốc, có thể tạo circuit breaker trực tiếp từ `CircuitBreakerConfig`. Một bộ đếm đặt ngay tại supplier cho biết dependency đã được gọi bao nhiêu lần:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InventoryCircuitBreakerTest {

    @Test
    void doesNotInvokeDependencyAgainWhileOpen() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
        AtomicInteger dependencyCalls = new AtomicInteger();

        // Hai lỗi được ghi nhận làm breaker chuyển sang OPEN.
        for (int i = 0; i < 2; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(() -> {
                dependencyCalls.incrementAndGet();
                throw new IllegalStateException("inventory unavailable");
            })).isInstanceOf(IllegalStateException.class);
        }

        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(dependencyCalls.get()).isEqualTo(2);

        // Lời gọi thứ ba bị từ chối trước khi supplier chạy.
        assertThatThrownBy(() -> breaker.executeSupplier(() -> {
            dependencyCalls.incrementAndGet();
            return "inventory response";
        })).isInstanceOf(CallNotPermittedException.class);

        assertThat(dependencyCalls.get()).isEqualTo(2);
    }
}
```

Kiểm thử có hai bằng chứng riêng: trạng thái breaker đã là `OPEN`, và bộ đếm dependency vẫn bằng 2 sau lần gọi thứ ba. Nếu supplier được chạy, bộ đếm sẽ tăng lên 3. `CallNotPermittedException` xác nhận breaker từ chối lời gọi ở lớp bảo vệ.

Trong dự án thực tế, đặt bộ đếm tại ranh giới gọi HTTP/RPC hoặc dùng mock để xác minh phương thức client. Không chỉ đếm số lần gọi service facade, vì facade vẫn được gọi khi breaker mở; điều cần xác minh là client phụ thuộc không bị gọi thêm.

## 4. Kiểm thử client bằng Mockito

Khi service sử dụng một client được inject, Mockito có thể xác minh chính xác số lần phương thức client được gọi. Ví dụ logic kiểm thử gồm các bước:

```java
// Giả sử inventoryClient.fetch(...) ném exception ở hai lần đầu.
for (int i = 0; i < 2; i++) {
    InventoryResult result = inventoryService.getInventory("SKU-1");
    assertThat(result.isUnavailable()).isTrue();
}

verify(inventoryClient, times(2)).fetch("SKU-1");

// Breaker đang OPEN; lời gọi mới chỉ đi qua fallback.
InventoryResult result = inventoryService.getInventory("SKU-1");

assertThat(result.isUnavailable()).isTrue();
verify(inventoryClient, times(2)).fetch("SKU-1");
verifyNoMoreInteractions(inventoryClient);
```

Đoạn mã giả định `inventoryService` dùng cùng một breaker ID `inventory` trong suốt bài kiểm thử, fallback trả về `InventoryResult.unavailable(...)`, và client đã được stub để hai lời gọi đầu thất bại. Các import Mockito thường dùng:

```java
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
```

Nếu client được gọi bởi một thành phần khác trong cùng bài kiểm thử, `verifyNoMoreInteractions(...)` có thể thất bại vì tương tác ngoài phạm vi cần kiểm tra. Khi đó chỉ xác minh số lần gọi đúng phương thức với `times(2)` hoặc dùng `clearInvocations(...)` tại ranh giới phù hợp. Điều quan trọng là assertion cuối cùng vẫn chứng minh số lần gọi dependency không tăng sau khi breaker mở.

## 5. Kiểm thử qua Spring Cloud CircuitBreaker factory

Khi ứng dụng dùng abstraction của Spring Cloud với backend Resilience4j, kiểm thử qua `CircuitBreakerFactory` để xác minh cả wiring lẫn fallback. Kích hoạt profile `test` để dùng cấu hình ở phần trước:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.test.context.ActiveProfiles;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class InventorySpringCloudCircuitBreakerTest {

    @Autowired
    CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    @Test
    void factoryFallbackDoesNotInvokeDependencyWhenOpen() {
        CircuitBreaker breaker = circuitBreakerFactory.create("inventory");
        AtomicInteger dependencyCalls = new AtomicInteger();
        AtomicReference<Throwable> lastFallbackCause = new AtomicReference<>();

        for (int i = 0; i < 2; i++) {
            String result = breaker.run(() -> {
                dependencyCalls.incrementAndGet();
                throw new IllegalStateException("inventory unavailable");
            }, error -> {
                lastFallbackCause.set(error);
                return "fallback";
            });

            assertThat(result).isEqualTo("fallback");
        }

        assertThat(dependencyCalls.get()).isEqualTo(2);

        String result = breaker.run(() -> {
            dependencyCalls.incrementAndGet();
            return "inventory response";
        }, error -> {
            lastFallbackCause.set(error);
            return "fallback";
        });

        assertThat(result).isEqualTo("fallback");
        assertThat(dependencyCalls.get()).isEqualTo(2);
        assertThat(lastFallbackCause.get())
            .isInstanceOf(io.github.resilience4j.circuitbreaker.CallNotPermittedException.class);
    }
}
```

Factory tạo breaker theo ID `inventory`, trùng với cấu hình YAML. Hai lần đầu supplier chạy và ném exception; fallback trả về chuỗi `fallback`. Lần thứ ba, breaker đang `OPEN`, nên fallback nhận lỗi từ chối và supplier không tăng bộ đếm. Test này cần starter Spring Cloud CircuitBreaker Resilience4j và cấu hình profile `test` được nạp trong Spring test context.

Nếu dự án không expose nguyên nhân fallback hoặc dùng một lớp adapter riêng, hãy kiểm tra kết quả fallback và số lần gọi client tại service boundary. Không nên tạo thêm một `CircuitBreakerRegistry` độc lập chỉ để đọc trạng thái rồi cho rằng đó là instance mà factory đang sử dụng.

## 6. Đảm bảo fallback không tự gọi lại dependency

Breaker chỉ kiểm soát supplier đã được bọc. Nếu fallback tự gọi lại cùng HTTP client trực tiếp, lời gọi đó nằm ngoài vùng bảo vệ và vẫn có thể đến dịch vụ phụ thuộc trong lúc breaker `OPEN`.

Ví dụ cần tránh:

```java
return breaker.run(
    () -> inventoryClient.fetch(sku),
    error -> inventoryClient.fetchFromPrimaryAgain(sku)
);
```

Fallback ở đây tiếp tục gọi một endpoint của cùng dependency. Mặc dù supplier ban đầu không chạy khi breaker mở, fallback vẫn tạo request mới. Một fallback an toàn hơn có thể đọc cache cục bộ, trả về trạng thái không khả dụng có kiểm soát, hoặc dùng một nguồn dữ liệu dự phòng độc lập đã được thiết kế riêng.

```java
return breaker.run(
    () -> inventoryClient.fetch(sku),
    error -> inventoryCache.find(sku)
        .orElseGet(() -> InventoryResult.unavailable(sku))
);
```

Khi kiểm thử, đặt mock hoặc bộ đếm ở mọi client có thể gọi cùng hệ thống phụ thuộc, bao gồm cả client được fallback sử dụng. Như vậy, kiểm thử có thể phát hiện trường hợp supplier không chạy nhưng fallback lại gọi vòng qua một client khác.

## 7. Những yếu tố có thể làm sai kết quả kiểm thử

| Yếu tố | Vì sao kết quả dễ sai | Cách kiểm soát |
| --- | --- | --- |
| Dùng breaker mới cho mỗi lần gọi | Mỗi instance có trạng thái riêng nên không tích lũy đủ lỗi để mở | Tạo breaker một lần cho test và dùng cùng instance |
| Dùng chung registry giữa nhiều test | Trạng thái `OPEN` từ test trước có thể ảnh hưởng test sau | Tạo instance mới hoặc reset registry theo fixture của test |
| Chưa đủ `minimumNumberOfCalls` | Failure rate chưa được đánh giá | Đặt cửa sổ và số mẫu tối thiểu nhỏ, cố định trong profile test |
| Chờ quá `waitDurationInOpenState` | Breaker có thể chuyển sang `HALF_OPEN` và cho phép lời gọi thử | Dùng thời gian mở đủ dài và thực hiện assertion ngay sau khi mở |
| Có Retry bọc quanh client | Một yêu cầu nghiệp vụ có thể tạo nhiều lần gọi dependency khi breaker còn đóng | Kiểm tra thứ tự decorator và cấu hình Retry trong test |
| Fallback gọi lại cùng dependency | Supplier bị chặn nhưng fallback vẫn phát request | Dùng cache hoặc nguồn dự phòng độc lập; đếm mọi client liên quan |
| Kiểm tra ở sai tầng | Service facade vẫn nhận yêu cầu dù client không được gọi | Đặt verify ở phương thức HTTP/RPC client hoặc transport boundary |
| Kiểm thử đồng thời không đồng bộ hóa | Lời gọi đã được cấp phép trước khi mở vẫn có thể đang chạy | Dùng latch/barrier và phân biệt request đang bay với request mới |

Đặc biệt, nếu có Retry, hãy hiểu thứ tự bọc. Khi circuit breaker ở `OPEN`, supplier của breaker không được chạy. Nhưng nếu một cơ chế Retry hoặc fallback nằm bên ngoài breaker và được lập trình gọi lại một đường khác, số request thực tế vẫn có thể tăng. Kiểm thử tại transport boundary sẽ cho bằng chứng rõ nhất.

## 8. Kiểm chứng HALF_OPEN và giới hạn của kết luận

Sau `waitDurationInOpenState`, breaker có thể chuyển sang `HALF_OPEN` và cho phép một số lời gọi thử được cấu hình bởi `permittedNumberOfCallsInHalfOpenState`. Khi đó dependency được gọi lại có chủ đích để kiểm tra khả năng phục hồi. Vì vậy, kết luận “OPEN không gọi dependency” chỉ đúng khi breaker vẫn đang `OPEN`; không áp dụng cho các probe hợp lệ trong `HALF_OPEN`.

Nếu cần kiểm thử ranh giới này, tạo một bài riêng: xác nhận lời gọi bị từ chối trong thời gian mở, sau đó điều khiển thời gian hoặc clock của breaker để chuyển sang `HALF_OPEN`, rồi xác nhận chỉ số probe được cho phép mới chạm đến dependency. Không dùng `Thread.sleep` tùy tiện trong bài kiểm thử chính vì nó khiến thời lượng và trạng thái khó tái lập.

Với lời gọi đồng bộ, một request đã bắt đầu trước khi mạch mở có thể vẫn tiếp tục chạy đến khi hoàn tất hoặc timeout. Circuit breaker không tự hủy request đó. Muốn giới hạn thời gian chiếm tài nguyên, cần cấu hình timeout phù hợp ở HTTP/RPC client hoặc dùng `TimeLimiter` trong mô hình tích hợp hỗ trợ. Kiểm thử `OPEN` phải đếm những lời gọi mới được thử sau khi trạng thái đã mở, không coi request đang bay là lời gọi mới.

## 9. Theo dõi hành vi ở môi trường chạy

Trong môi trường thật, kết hợp log, metric và trạng thái breaker để xác nhận rằng hệ thống đang từ chối nhanh. Các tín hiệu hữu ích gồm:

- Trạng thái hiện tại của circuit breaker theo ID dependency.
- Số lời gọi được phép và số lời gọi thành công/thất bại.
- Số lời gọi bị từ chối khi breaker đang `OPEN`.
- Số lần fallback được gọi và tỷ lệ fallback thành công.
- Thời gian phản hồi của request nghiệp vụ khi dependency không khả dụng.

Micrometer và Spring Boot Actuator có thể cung cấp số liệu khi dependency và cấu hình tương ứng được bật. Dùng cùng một ID breaker trong YAML, mã gọi, log và dashboard để đối chiếu. Không suy ra dependency đã nhận request chỉ từ số lần service facade được gọi; hãy quan sát client hoặc metric phía dependency nếu cần xác minh end-to-end.

Một kiểm thử tốt chứng minh được ba điều: breaker đã thực sự vào `OPEN`, lời gọi mới được trả về nhanh qua fallback hoặc lỗi từ chối, và số lần gọi dependency không tăng. Khi cần xác minh toàn bộ luồng vận hành, bổ sung kiểm thử riêng cho `HALF_OPEN`, Retry, timeout và fallback để mỗi cơ chế có thể được đánh giá độc lập.
