# Chuyển trạng thái thủ công, reset và tác động tới thống kê

Resilience4j CircuitBreaker tự chuyển trạng thái dựa trên failure rate, slow-call rate và sliding window. Trong một số tình huống vận hành hoặc kiểm thử, ứng dụng cũng cần chủ động chuyển breaker sang `OPEN`, `HALF_OPEN`, `CLOSED` hoặc một trạng thái đặc biệt. Những thao tác này thay đổi cách breaker cho phép lời gọi đi qua; chúng không đồng nghĩa với việc xóa thống kê.

Điểm cần phân biệt là **chuyển trạng thái** và **reset**. Chuyển trạng thái thủ công điều khiển quyền thực thi của các lời gọi tiếp theo. `reset()` đưa breaker về `CLOSED` và xóa số liệu tích lũy của cửa sổ. Nếu không hiểu sự khác nhau, dashboard có thể tiếp tục hiển thị tỷ lệ lỗi cũ sau khi breaker đã đóng, hoặc nhóm vận hành có thể vô tình xóa dấu vết thống kê khi chỉ muốn mở lại dịch vụ.

## 1. Trạng thái tự động và trạng thái do vận hành điều khiển

Trong trạng thái bình thường, circuit breaker tự quyết định:

- `CLOSED`: cho phép lời gọi đi qua, ghi nhận kết quả và cập nhật các tỷ lệ.
- `OPEN`: từ chối lời gọi mới trong thời gian mở mạch.
- `HALF_OPEN`: cho phép số lượng lời gọi thử giới hạn để đánh giá dependency đã phục hồi hay chưa.

Luồng chuyển trạng thái tự động thường là:

```text
             đủ mẫu và tỷ lệ vượt ngưỡng
       CLOSED ------------------------------> OPEN
          ^                                     |
          |                                     |
          | kết quả probe tốt                   | hết waitDurationInOpenState
          |                                     v
          +-------------------------------- HALF_OPEN
                    probe thất bại hoặc tỷ lệ vượt ngưỡng
                                  |
                                  +----------> OPEN
```

Ứng dụng có thể can thiệp khi cần cô lập dependency trước khi có đủ mẫu, cho phép một đợt probe có kiểm soát, đóng mạch sau khi đã xác minh sự cố được xử lý, hoặc reset số liệu để bắt đầu một giai đoạn quan sát mới. Can thiệp thủ công nên là hành động vận hành có chủ đích, có người chịu trách nhiệm và có ghi nhận lý do.

## 2. Lấy đúng instance từ CircuitBreakerRegistry

Trong ứng dụng Spring Boot tích hợp Resilience4j, registry quản lý các circuit breaker theo tên. Những thành phần cần thao tác cùng một breaker phải dùng đúng instance do integration quản lý hoặc cùng một registry được chia sẻ.

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class CircuitBreakerOperations {

    private final CircuitBreaker inventoryBreaker;

    public CircuitBreakerOperations(CircuitBreakerRegistry registry) {
        this.inventoryBreaker = registry.circuitBreaker("inventory");
    }

    public CircuitBreaker.State currentState() {
        return inventoryBreaker.getState();
    }
}
```

Tên `inventory` phải khớp với ID cấu hình Resilience4j và ID mà mã nghiệp vụ sử dụng. Không tạo `CircuitBreakerRegistry.ofDefaults()` mới trong một controller chỉ để điều khiển breaker. Registry độc lập có thể tạo ra instance khác cùng tên nhưng trạng thái và số liệu không liên quan đến breaker đang bảo vệ request thật.

Nếu dùng Spring Cloud CircuitBreaker factory, hãy xác định cách lấy backend instance theo đúng phiên bản tích hợp. Không mặc định rằng một registry tự tạo luôn là registry mà factory đang dùng. Có thể đưa thao tác vận hành vào một service dùng chung và tiêm đúng bean quản lý instance.

## 3. Chuyển trạng thái thủ công

Resilience4j cung cấp các phương thức trên đối tượng `CircuitBreaker` để chuyển trạng thái:

| Phương thức | Trạng thái đích | Hành vi chính |
| --- | --- | --- |
| `transitionToOpenState()` | `OPEN` | Từ chối lời gọi mới theo cơ chế thời gian mở của breaker; sau thời gian chờ, breaker có thể cho phép chuyển sang `HALF_OPEN` theo cấu hình |
| `transitionToHalfOpenState()` | `HALF_OPEN` | Cho phép số lượng probe giới hạn theo `permittedNumberOfCallsInHalfOpenState` |
| `transitionToClosedState()` | `CLOSED` | Cho phép lời gọi bình thường và tiếp tục ghi nhận thống kê |
| `transitionToForcedOpenState()` | `FORCED_OPEN` | Ép breaker từ chối lời gọi cho đến khi có thao tác chuyển trạng thái khác |
| `transitionToDisabledState()` | `DISABLED` | Cho phép lời gọi đi qua mà không áp dụng cơ chế bảo vệ thông thường |
| `transitionToMetricsOnlyState()` | `METRICS_ONLY` | Cho phép lời gọi nhưng vẫn ghi nhận kết quả và metric để quan sát |

Ví dụ:

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

// Chủ động mở mạch theo thời gian chờ đã cấu hình.
breaker.transitionToOpenState();

// Khi muốn cho phép một số request kiểm tra phục hồi.
breaker.transitionToHalfOpenState();

// Sau khi xác minh dependency ổn định.
breaker.transitionToClosedState();
```

`transitionToOpenState()` và `transitionToForcedOpenState()` không giống nhau. `OPEN` là trạng thái mở có thời gian chờ và cơ chế chuyển tiếp sang `HALF_OPEN`. `FORCED_OPEN` là chế độ cưỡng bức từ chối, được giữ cho đến khi ứng dụng hoặc người vận hành chủ động chuyển sang trạng thái khác. Dùng `FORCED_OPEN` khi cần cô lập dependency theo quyết định vận hành; dùng `OPEN` khi muốn tuân theo chu trình chờ và probe thông thường.

`HALF_OPEN` giới hạn số lời gọi thử. Không nên chuyển thẳng sang `CLOSED` chỉ vì một probe đơn lẻ thành công nếu chưa đủ bằng chứng dependency đã ổn định. Hãy để các probe được cấu hình đánh giá kết quả hoặc thực hiện quy trình xác minh có kiểm soát trước khi đóng mạch.

## 4. Các trạng thái đặc biệt: DISABLED, FORCED_OPEN và METRICS_ONLY

Ba trạng thái đặc biệt phục vụ các mục tiêu khác nhau:

| Trạng thái | Lời gọi mới | Thống kê và sự kiện | Khi nào cân nhắc |
| --- | --- | --- | --- |
| `DISABLED` | Luôn được cho phép | Không ghi nhận các metric lời gọi như chế độ bình thường | Chỉ dùng trong tình huống đã quyết định bỏ qua bảo vệ, thường là kiểm thử hoặc vận hành có kiểm soát |
| `FORCED_OPEN` | Luôn bị từ chối | Không ghi nhận thống kê lời gọi thông thường; vẫn theo dõi việc chuyển trạng thái | Cô lập khẩn cấp dependency khi có nguy cơ gây lỗi dây chuyền |
| `METRICS_ONLY` | Luôn được cho phép | Vẫn ghi nhận kết quả, metric và sự kiện nhưng không từ chối lời gọi theo ngưỡng | Quan sát ngưỡng và tỷ lệ trong giai đoạn đánh giá trước khi bật chặn thật |

`METRICS_ONLY` hữu ích khi triển khai chính sách mới. Nhóm có thể quan sát failure rate và slow-call rate trong điều kiện production mà chưa để circuit breaker từ chối request. Tuy nhiên, vì lời gọi vẫn đi tới dependency, trạng thái này không bảo vệ hệ thống khỏi tải tăng hoặc lỗi dây chuyền. Chỉ dùng khi dependency và hệ thống đủ khả năng chịu tải trong giai đoạn quan sát.

`DISABLED` và `FORCED_OPEN` thay đổi hành vi rõ rệt, vì vậy không nên bật qua một endpoint quản trị công khai hoặc một feature flag không có kiểm soát. Cần giới hạn quyền, ghi audit và có kế hoạch chuyển về trạng thái bình thường.

## 5. Reset khác với chuyển về CLOSED

`reset()` đưa circuit breaker về `CLOSED` và xóa các số liệu tích lũy của breaker, bao gồm thống kê dùng để tính failure rate và slow-call rate trong sliding window. Đây là thao tác bắt đầu lại baseline quan sát.

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

// Xóa trạng thái và thống kê tích lũy, đưa breaker về CLOSED.
breaker.reset();
```

So sánh:

| Thao tác | Thay đổi trạng thái | Xóa thống kê cửa sổ |
| --- | --- | --- |
| `transitionToOpenState()` | Chuyển sang `OPEN` | Không phải thao tác reset thống kê |
| `transitionToHalfOpenState()` | Chuyển sang `HALF_OPEN` | Không phải thao tác reset thống kê |
| `transitionToClosedState()` | Chuyển sang `CLOSED` | Không nên dùng với mục đích xóa số liệu |
| `transitionToForcedOpenState()` | Chuyển sang `FORCED_OPEN` | Không phải thao tác reset thống kê |
| `reset()` | Trở về `CLOSED` | Có, xóa số liệu tích lũy |

Khi chỉ chuyển từ `OPEN` sang `CLOSED`, đừng giả định dashboard sẽ bắt đầu từ 0. Các số liệu đã tích lũy có thể vẫn còn để phản ánh lịch sử của cửa sổ. Nếu mục tiêu là làm sạch cửa sổ, dùng `reset()` và ghi nhận rõ rằng một baseline mới đã bắt đầu.

Ngược lại, không dùng `reset()` như một cách “sửa” dependency đang lỗi. Reset mở lại đường gọi và xóa bằng chứng thống kê; nếu dependency chưa phục hồi, request mới có thể tiếp tục thất bại và breaker lại mở. Khi muốn giữ dependency bị chặn, hãy dùng trạng thái `OPEN` hoặc `FORCED_OPEN` phù hợp.

## 6. Thống kê nào bị ảnh hưởng?

Circuit breaker tổng hợp kết quả lời gọi trong sliding window. Các số liệu thường được quan sát gồm:

- Số lời gọi đã được ghi nhận trong cửa sổ (`numberOfBufferedCalls`).
- Số lời gọi thành công và thất bại.
- Số lời gọi chậm và số lời gọi chậm thất bại.
- `failureRate` và `slowCallRate`.
- Số lời gọi bị từ chối do breaker không cho phép thực thi.

Failure rate và slow-call rate chỉ có ý nghĩa quyết định khi đã đạt `minimumNumberOfCalls`. Với `COUNT_BASED`, cửa sổ xét số lời gọi gần nhất. Với `TIME_BASED`, cửa sổ xét kết quả trong khoảng thời gian cấu hình. Khi reset, thống kê tích lũy được xóa; khi chuyển trạng thái thủ công, hành vi cho phép hoặc từ chối lời gọi thay đổi nhưng đó không phải thao tác xóa lịch sử thống kê.

Lời gọi bị từ chối khi breaker đang `OPEN` không phải là một lần gọi dependency thất bại. Supplier không chạy, nên không được cộng lần từ chối đó vào failure rate của dependency. Theo dõi riêng số lần bị từ chối giúp phân biệt hai vấn đề: dependency đã nhận lời gọi và trả lỗi, hay ứng dụng đang chặn lời gọi trước khi request được gửi.

Ở các trạng thái đặc biệt, cách ghi nhận khác nhau:

- `METRICS_ONLY` vẫn cho phép request và ghi nhận kết quả để quan sát các tỷ lệ.
- `DISABLED` cho phép request nhưng không ghi nhận metric lời gọi theo cách thông thường.
- `FORCED_OPEN` từ chối request; không dùng các lần từ chối đó để suy ra dependency vừa trả thêm lỗi.

Vì vậy, khi đọc dashboard, luôn đối chiếu trạng thái breaker cùng failure rate, slow-call rate và số lần bị từ chối. Một tỷ lệ lỗi không đổi trong lúc `FORCED_OPEN` không có nghĩa dependency đã phục hồi; đơn giản là không có lời gọi mới đi qua để cập nhật tỷ lệ.

## 7. Theo dõi state transition và reset bằng event

Event publisher của Resilience4j cho phép ứng dụng lắng nghe các sự kiện của một breaker. Có thể ghi nhận chuyển trạng thái, lỗi, thành công, lời gọi bị từ chối và reset:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerEventLogger {

    private static final Logger log =
        LoggerFactory.getLogger(CircuitBreakerEventLogger.class);

    public CircuitBreakerEventLogger(CircuitBreakerRegistry registry) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        breaker.getEventPublisher()
            .onStateTransition(event ->
                log.info("Circuit breaker inventory state transition: {}", event))
            .onReset(event ->
                log.info("Circuit breaker inventory was reset: {}", event))
            .onCallNotPermitted(event ->
                log.warn("Circuit breaker inventory rejected a call: {}", event))
            .onError(event ->
                log.warn("Circuit breaker inventory recorded an error: {}", event))
            .onSuccess(event ->
                log.debug("Circuit breaker inventory recorded success: {}", event));
    }
}
```

Event listener nên được đăng ký một lần trong vòng đời bean, không đăng ký lặp lại cho mỗi request. Trong môi trường thực, gửi sự kiện đến logging hoặc metrics pipeline có cấu trúc; không đưa payload nhạy cảm, token hoặc dữ liệu cá nhân vào log. Event giúp giải thích vì sao trạng thái thay đổi, còn metric cho biết xu hướng theo thời gian.

## 8. Thao tác vận hành an toàn

Một service quản trị có thể cung cấp các hành động rõ ràng như “force open”, “allow probe”, “close after validation” và “reset statistics”. Mỗi hành động cần có:

1. Xác thực và phân quyền riêng cho người được phép điều khiển breaker.
2. Lý do thao tác, mã sự cố hoặc ticket liên quan.
3. Audit gồm người thực hiện, thời điểm, breaker ID, trạng thái trước và sau.
4. Cảnh báo khi bật `DISABLED`, `METRICS_ONLY` hoặc `FORCED_OPEN`.
5. Quy trình phục hồi và người chịu trách nhiệm đóng lại hoặc reset.

Không expose một endpoint không xác thực cho phép truyền tên breaker và trạng thái tùy ý. Nếu dùng Spring Boot Actuator hoặc API nội bộ, chỉ expose đúng endpoint cần thiết, giới hạn mạng truy cập và áp dụng authorization. Việc chuyển breaker sang `CLOSED` có thể làm lưu lượng dồn trở lại dependency ngay lập tức; cần kiểm tra khả năng phục hồi trước khi làm.

Các lời gọi đã được cho phép trước khi chuyển trạng thái vẫn có thể đang thực thi. Chuyển sang `OPEN` hoặc `FORCED_OPEN` chỉ ảnh hưởng đến lời gọi mới; nó không hủy request đang bay. Muốn giới hạn thời gian của request đang chạy, cần timeout ở HTTP/RPC client hoặc TimeLimiter phù hợp với mô hình bất đồng bộ.

## 9. Kiểm thử chuyển trạng thái và tác động thống kê

Kiểm thử nên dùng instance riêng để trạng thái không rò giữa các bài test. Ví dụ với API native:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CircuitBreakerManualStateTest {

    @Test
    void forcedOpenRejectsCallsAndResetClearsWindowMetrics() {
        CircuitBreaker breaker = CircuitBreaker.of(
            "inventory-test",
            CircuitBreakerConfig.custom()
                .slidingWindowSize(4)
                .minimumNumberOfCalls(2)
                .build()
        );

        breaker.executeRunnable(() -> { });
        assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(1);

        breaker.transitionToForcedOpenState();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.FORCED_OPEN);

        breaker.reset();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isZero();
    }
}
```

Test xác nhận ba điểm: một lời gọi thành công được ghi nhận; chuyển sang `FORCED_OPEN` thay đổi quyền thực thi; `reset()` đưa breaker về `CLOSED` và xóa số lời gọi tích lũy. Có thể bổ sung test để xác minh supplier không chạy khi `FORCED_OPEN`, số probe bị giới hạn ở `HALF_OPEN`, và `METRICS_ONLY` vẫn ghi nhận kết quả nhưng không từ chối request.

Với integration test Spring Boot, inject registry do ứng dụng quản lý và lấy đúng ID instance. Không tự tạo registry thứ hai trong test nếu mục tiêu là kiểm tra breaker mà service production đang dùng. Sau test, reset instance hoặc tạo context/instance mới để tránh trạng thái và metric ảnh hưởng test khác.

## 10. Quy tắc sử dụng

- Dùng `transitionToOpenState()` khi cần mở breaker theo chu trình chờ và probe thông thường.
- Dùng `transitionToForcedOpenState()` khi cần cưỡng bức từ chối lời gọi cho đến khi có thao tác vận hành khác.
- Dùng `transitionToHalfOpenState()` để cho phép số probe giới hạn; không mở đồng loạt toàn bộ lưu lượng.
- Chỉ chuyển thẳng về `CLOSED` sau khi đã xác minh dependency có thể nhận tải trở lại.
- Dùng `reset()` khi thực sự cần xóa số liệu tích lũy và bắt đầu baseline mới; không nhầm nó với chuyển trạng thái.
- Dùng `METRICS_ONLY` để quan sát chính sách trước khi chặn, đồng thời hiểu rằng trạng thái này không bảo vệ dependency.
- Theo dõi state transition, reset, lỗi, thành công và call-not-permitted event cùng metric.
- Bảo vệ mọi thao tác quản trị bằng phân quyền, audit và quy trình phục hồi.

Chuyển trạng thái thủ công là công cụ điều khiển lưu lượng; reset là thao tác làm mới thống kê và trạng thái. Dùng đúng mục đích giúp đội vận hành cô lập dependency khi cần, thử phục hồi có kiểm soát và giữ được dữ liệu đủ tin cậy để giải thích hành vi circuit breaker trong Spring Cloud.
