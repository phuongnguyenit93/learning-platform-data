# Kiểm thử chuỗi kết quả để xác minh CLOSED chuyển sang OPEN

Một bài kiểm thử Circuit Breaker có giá trị phải chứng minh được thời điểm mạch đổi trạng thái, dữ liệu nào khiến nó đổi và lời gọi tiếp theo bị xử lý ra sao. Chỉ kiểm tra rằng một request ném exception là chưa đủ: Circuit Breaker có sliding window, số mẫu tối thiểu và ngưỡng tỷ lệ. Mạch có thể tiếp tục ở `CLOSED` sau một hoặc vài lỗi, rồi chỉ chuyển sang `OPEN` khi chuỗi kết quả đã thỏa các điều kiện cấu hình.

Với Spring Cloud CircuitBreaker dùng Resilience4j, nên kiểm thử hai lớp. Unit test trực tiếp Resilience4j xác minh state machine và sliding window một cách xác định. Test ở tầng service xác minh ứng dụng thực sự đi qua `CircuitBreakerFactory` hoặc `ReactiveCircuitBreakerFactory`, dùng đúng tên instance và áp dụng fallback như dự kiến.

## Điều kiện để chuyển từ CLOSED sang OPEN

Trong trạng thái `CLOSED`, Circuit Breaker cho phép lời gọi đi qua và ghi nhận kết quả vào sliding window. Hai cấu hình quan trọng khi kiểm thử là:

- `minimumNumberOfCalls`: số mẫu tối thiểu cần có trước khi tính failure rate hoặc slow call rate để quyết định mở mạch.
- `failureRateThreshold`: ngưỡng phần trăm lỗi. Khi đã đủ mẫu và tỷ lệ lỗi đạt hoặc vượt ngưỡng, Circuit Breaker chuyển sang `OPEN`.

Với cửa sổ đếm, `slidingWindowSize` là số kết quả gần nhất được giữ lại. Cửa sổ không phải giới hạn số lời gọi đồng thời. Với cửa sổ thời gian, kích thước biểu thị số giây gần nhất. Để test chuỗi kết quả dễ dự đoán, ví dụ bên dưới dùng `COUNT_BASED`.

Giả sử cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: false
```

Với bốn mẫu tối thiểu và ngưỡng 50%, chuỗi `Success, Failure, Success, Failure` tạo failure rate đúng 50%. Trước mẫu thứ tư, Circuit Breaker chưa có đủ mẫu nên vẫn ở `CLOSED`. Khi mẫu thứ tư được ghi nhận, mạch đủ dữ liệu và đạt ngưỡng, vì vậy chuyển sang `OPEN`.

| Lần gọi | Kết quả | Số mẫu đã có | Failure rate | Trạng thái sau lần gọi |
|---:|---|---:|---:|---|
| 1 | Success | 1 | Chưa đủ mẫu | `CLOSED` |
| 2 | Failure | 2 | Chưa đủ mẫu | `CLOSED` |
| 3 | Success | 3 | Chưa đủ mẫu | `CLOSED` |
| 4 | Failure | 4 | 2/4 = 50% | `OPEN` |
| 5 | Bị từ chối | Không thêm mẫu | Không đổi | `OPEN` |

Điều quan trọng trong test là kiểm tra trạng thái sau từng bước, đặc biệt là trước khi đủ mẫu và ngay sau khi đạt ngưỡng. Nếu chỉ kiểm tra trạng thái cuối cùng, test có thể bỏ sót việc mạch mở quá sớm hoặc không mở đúng thời điểm.

## Viết unit test xác định bằng Resilience4j

Ví dụ dưới đây dùng JUnit 5 và AssertJ. `DependencyException` đại diện cho lỗi kỹ thuật của dịch vụ phụ thuộc. Mỗi lời gọi được thực thi qua cùng một Circuit Breaker instance để các kết quả được ghi vào cùng sliding window.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CatalogCircuitBreakerTest {

    private CircuitBreaker circuitBreaker;

    @BeforeEach
    void setUp() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();

        circuitBreaker = CircuitBreaker.of("catalog", config);
    }

    @Test
    void opensOnlyAfterMinimumCallsAndFailureRateThresholdAreReached() {
        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.CLOSED);

        // 1: Success
        assertThat(circuitBreaker.executeSupplier(() -> "item-1"))
            .isEqualTo("item-1");

        // 2: Failure
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("catalog unavailable");
        })).isInstanceOf(DependencyException.class);

        // 3: Success; mới có 3 mẫu, chưa đạt minimumNumberOfCalls = 4.
        assertThat(circuitBreaker.executeSupplier(() -> "item-2"))
            .isEqualTo("item-2");
        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.CLOSED);

        // 4: Failure; 2 failure / 4 mẫu = 50%, mạch phải OPEN.
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("catalog still unavailable");
        })).isInstanceOf(DependencyException.class);

        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(circuitBreaker.getMetrics().getNumberOfBufferedCalls())
            .isEqualTo(4);
        assertThat(circuitBreaker.getMetrics().getNumberOfSuccessfulCalls())
            .isEqualTo(2);
        assertThat(circuitBreaker.getMetrics().getNumberOfFailedCalls())
            .isEqualTo(2);
        assertThat(circuitBreaker.getMetrics().getFailureRate())
            .isEqualTo(50.0f);
    }

    @Test
    void rejectsNextCallWithoutInvokingDependencyAfterOpening() {
        recordFourResultsToOpenCircuit();
        AtomicInteger dependencyCalls = new AtomicInteger();

        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            dependencyCalls.incrementAndGet();
            return "should-not-run";
        })).isInstanceOf(CallNotPermittedException.class);

        assertThat(dependencyCalls).hasValue(0);
        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(circuitBreaker.getMetrics().getNumberOfNotPermittedCalls())
            .isEqualTo(1);
    }

    private void recordFourResultsToOpenCircuit() {
        circuitBreaker.executeSupplier(() -> "one");
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("first failure");
        })).isInstanceOf(DependencyException.class);
        circuitBreaker.executeSupplier(() -> "two");
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("second failure");
        })).isInstanceOf(DependencyException.class);
    }

    static class DependencyException extends RuntimeException {
        DependencyException(String message) {
            super(message);
        }
    }
}
```

Test đầu tiên xác minh cả chuỗi kết quả lẫn metrics. Test thứ hai xác minh tác dụng bảo vệ sau khi mạch mở: lời gọi thứ năm bị từ chối bằng `CallNotPermittedException`, supplier không được chạy và số lời gọi bị từ chối tăng. Lời gọi bị từ chối không trở thành mẫu success hoặc failure trong sliding window.

Trong dự án thực tế, đặt class test và exception ở package phù hợp; thêm dependency test JUnit 5 và AssertJ theo bộ quản lý dependency của dự án. Không dùng chung Circuit Breaker giữa các test. Tạo instance mới trong `@BeforeEach` để kết quả của test trước không ảnh hưởng đến test sau.

## Kiểm tra cách tính failure rate

Failure rate được tính từ số lời gọi thất bại chia cho tổng số mẫu được tính trong cửa sổ:

\[
FailureRate = \frac{FailedCalls}{SuccessfulCalls + FailedCalls} \times 100\%
\]

Các exception được cấu hình bỏ qua không tham gia mẫu số. Lời gọi bị Circuit Breaker từ chối cũng không tham gia sliding window. Vì vậy, không lấy tổng số request HTTP đến ứng dụng làm mẫu số để tính failure rate của Circuit Breaker.

Ví dụ, nếu chuỗi có hai success, một failure và một ignored exception, chỉ có ba mẫu được tính. Failure rate là 1/3, xấp xỉ 33,3%. Nếu `minimumNumberOfCalls` là 4, mạch chưa có đủ mẫu để quyết định mở theo tỷ lệ. Một ignored exception không được xem như success để làm giảm failure rate.

Nếu khai báo `recordExceptions`, hãy nhớ exception không khớp danh sách ghi nhận lỗi có thể được tính như success, trừ khi nó khớp chính sách ignore. Hãy kiểm tra loại exception thực tế mà client ném ra; một HTTP client có thể bọc lỗi kết nối trong exception khác với exception gốc.

## Xác minh sliding window thực sự trượt

COUNT_BASED window giữ tối đa `slidingWindowSize` kết quả gần nhất. Khi có mẫu mới và cửa sổ đã đầy, mẫu cũ nhất bị loại khỏi thống kê. Một test bổ sung có thể chứng minh quyết định mở mạch dựa trên các mẫu gần nhất, không phải toàn bộ lịch sử từ lúc ứng dụng khởi động.

Ví dụ với cửa sổ 4 mẫu, ngưỡng 50%:

1. Ghi nhận `Failure, Failure, Success, Success`: failure rate là 50%, mạch mở khi đủ bốn mẫu.
2. Trong một test riêng, reset hoặc tạo Circuit Breaker mới rồi ghi `Success, Success, Success, Failure`: failure rate là 25%, mạch vẫn `CLOSED` sau bốn mẫu.
3. Với mạch vẫn `CLOSED`, tiếp tục thêm `Success`. Cửa sổ chỉ giữ bốn mẫu mới nhất; mẫu cũ nhất bị loại và failure rate được tính lại trên bốn mẫu đang còn.

Để test không phụ thuộc thứ tự hoặc state của test khác, mỗi kịch bản nên có Circuit Breaker riêng. Nếu cần kiểm tra việc loại mẫu cũ, hãy assert `getNumberOfBufferedCalls()`, số success/failure và failure rate sau từng kết quả mới.

## Kiểm tra slow call rate riêng với failure rate

Circuit Breaker có thể mở vì tỷ lệ lời gọi chậm vượt `slowCallRateThreshold`, ngay cả khi các lời gọi đó cuối cùng trả kết quả thành công. Vì vậy, test chỉ kiểm tra exception chưa bao phủ nhánh mở mạch do độ trễ.

Một cấu hình kiểm thử slow call có thể dùng:

```java
CircuitBreakerConfig slowConfig = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(4)
    .minimumNumberOfCalls(4)
    .failureRateThreshold(100)
    .slowCallDurationThreshold(Duration.ofMillis(50))
    .slowCallRateThreshold(50)
    .build();
```

Trong test, dùng một clock hoặc scheduler có thể điều khiển nếu API và phiên bản tích hợp hỗ trợ; nếu không, dùng độ trễ nhỏ có khoảng cách đủ lớn so với threshold và tránh phụ thuộc vào timing chính xác của CI. Ghi nhận bốn lời gọi thành công, trong đó ít nhất hai lời gọi vượt `slowCallDurationThreshold`. Khi đủ mẫu, slow call rate đạt 50% và mạch có thể mở dù failure rate là 0%.

Không dùng `Thread.sleep(...)` dài trong unit test chỉ để đợi Circuit Breaker hết `waitDurationInOpenState`. Test chuyển `CLOSED` → `OPEN` không cần đợi thời gian chờ mở mạch. Nếu cần kiểm tra `OPEN` → `HALF_OPEN`, hãy cấu hình thời gian ngắn có chủ đích hoặc dùng cơ chế thời gian có thể điều khiển của phiên bản thư viện.

## Kiểm thử tầng Spring Cloud CircuitBreaker

Unit test trực tiếp Resilience4j chứng minh state machine. Để xác nhận ứng dụng dùng đúng factory và instance, hãy có test service ở tầng tích hợp. Service nên gọi qua abstraction `CircuitBreakerFactory` thay vì tự tạo một Circuit Breaker riêng không liên quan đến factory:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    Product find(String sku) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.find(sku),
            error -> Product.unavailable(sku));
    }
}
```

Trong `@SpringBootTest`, cấu hình instance `catalog` bằng cửa sổ nhỏ và ngưỡng dễ tái hiện, mock `CatalogClient` để trả chuỗi kết quả xác định, rồi gọi `CatalogService.find(...)` qua Spring bean. Test nên xác nhận:

- Service sử dụng đúng id `catalog` đã cấu hình.
- Các lỗi của client được đưa qua Circuit Breaker trước khi fallback xử lý.
- Khi đủ mẫu và đạt ngưỡng, lần gọi tiếp theo không gọi mock client nữa.
- Fallback trả đúng hợp đồng khi Circuit Breaker từ chối hoặc dependency lỗi.
- Một context test mới tạo instance mới, không dùng lại state đã mở từ test trước.

Nếu cần đọc metrics Resilience4j trong integration test, inject đúng `CircuitBreakerRegistry` mà backend factory đang dùng và tìm instance hiện có. Tránh gọi `registry.circuitBreaker("catalog")` ở bước assertion nếu chưa xác minh factory dùng chính registry đó; thao tác này có thể tạo một instance khác và khiến test kiểm tra nhầm mạch.

Với Feign, test qua interface client và mock HTTP server như WireMock để điều khiển response, latency và số request. Với reactive factory, dùng `StepVerifier` để kiểm tra publisher và số lần subscription. Không chặn reactive stream bằng `.block()` trong code production chỉ để làm test đồng bộ; trong test, dùng `StepVerifier` để kiểm tra tín hiệu một cách tự nhiên.

## Những lỗi thường gặp khiến test sai

- **Không kiểm tra `minimumNumberOfCalls`:** test kỳ vọng một lỗi làm mạch mở dù chưa đủ mẫu.
- **Dùng cửa sổ thời gian cho test cần chuỗi đếm chính xác:** kết quả phụ thuộc thời điểm chạy và thời gian thực. Dùng `COUNT_BASED` khi mục tiêu là xác minh số mẫu.
- **Dùng chung Circuit Breaker giữa các test:** state và sliding window từ test trước làm thay đổi kết quả test sau. Tạo instance mới cho mỗi test.
- **Fallback nằm bên trong lời gọi được bảo vệ:** lỗi bị chuyển thành kết quả bình thường trước khi Circuit Breaker ghi nhận, khiến test không mở mạch như mong đợi.
- **Không kiểm tra supplier có bị gọi sau OPEN không:** chỉ assert exception mà không xác minh dependency không nhận thêm request.
- **Coi `CallNotPermittedException` là lỗi của dependency:** mạch đã chặn lời gọi nên client không được gọi; đo riêng số lần bị từ chối.
- **Dựa vào `Thread.sleep` dài:** làm test chậm và dễ chập chờn. Chỉ kiểm tra thời gian chờ khi đó là mục tiêu của test.
- **Đọc nhầm registry:** assertion lấy instance từ registry khác với registry của factory nên state không khớp hành vi service.

## Checklist cho bài kiểm thử CLOSED chuyển OPEN

| Điều cần xác minh | Kết quả mong đợi |
|---|---|
| Trạng thái ban đầu | `CLOSED` |
| Số mẫu nhỏ hơn `minimumNumberOfCalls` | Vẫn `CLOSED`, chưa quyết định theo tỷ lệ |
| Số mẫu đạt tối thiểu nhưng failure rate dưới ngưỡng | Vẫn `CLOSED` |
| Failure rate đạt hoặc vượt ngưỡng | Chuyển `OPEN` |
| Lời gọi sau khi `OPEN` | Phát `CallNotPermittedException` |
| Supplier/client sau khi `OPEN` | Không được thực thi |
| Metrics | Buffered, success, failure và not-permitted đúng với chuỗi kết quả |
| Fallback | Chạy theo ranh giới API và trả kết quả đúng hợp đồng |

Một bài test tốt không chỉ chứng minh Circuit Breaker cuối cùng ở `OPEN`; nó chứng minh vì sao mạch mở, mở sau mẫu nào, metrics phản ánh đúng chuỗi kết quả và request tiếp theo thực sự được chặn trước dependency. Đây là cơ sở để tin rằng cấu hình Resilience4j trong Spring Cloud đang bảo vệ dịch vụ theo ngưỡng đã thiết kế.
