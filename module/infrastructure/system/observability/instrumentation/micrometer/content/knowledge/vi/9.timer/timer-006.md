# Chọn tag kết quả khi thao tác đã hoàn tất

Khi đo thời gian của một thao tác, đôi khi chỉ biết kết quả sau khi thao tác kết thúc. Một request có thể thành công, bị từ chối theo quy tắc nghiệp vụ, timeout hoặc thất bại do lỗi kỹ thuật. Nếu muốn phân tích độ trễ theo kết quả, cần ghi nhận thời lượng vào meter có tag tương ứng sau khi đã xác định kết quả.

Micrometer cung cấp `Timer.Sample` cho tình huống này. Ta bắt đầu sample trước khi thực hiện công việc, phân loại kết quả khi công việc hoàn tất, rồi dừng sample với một `Timer` mang tag phù hợp. Nhờ vậy, thời gian của các kết quả khác nhau được ghi vào các meter riêng nhưng vẫn có cùng tên và cùng quy ước tag.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, cách làm này giúp phân tích độ trễ thành công và thất bại, theo dõi timeout, kiểm thử instrumentation và diễn giải số đo vận hành. Điểm quan trọng là tag phải mô tả kết quả đã được phân loại bằng một tập giá trị hữu hạn.

## 1. Vì sao cần chọn tag sau khi thao tác hoàn tất?

Nếu tạo timer với tag `outcome` ngay trước khi gọi service, tại thời điểm đó ứng dụng chưa biết thao tác sẽ kết thúc như thế nào. Đặt mặc định `outcome=success` rồi đo có thể phân loại sai các request ném exception hoặc timeout.

Ví dụ một thao tác thanh toán có các kết quả:

| Kết quả thao tác | Giá trị tag `outcome` | Ý nghĩa |
| --- | --- | --- |
| Thanh toán được chấp nhận | `success` | Giao dịch hoàn tất theo mong đợi |
| Bị từ chối theo quy tắc nghiệp vụ | `rejected` | Thao tác kết thúc bình thường nhưng không được chấp nhận |
| Hết thời gian chờ | `timeout` | Không nhận được kết quả trong thời hạn cho phép |
| Lỗi kỹ thuật khác | `error` | Thao tác thất bại do lỗi ngoài nhóm timeout |
| Bị hủy | `cancelled` | Luồng xử lý bị hủy trước khi hoàn tất |

Các giá trị này là ví dụ về một vocabulary có kiểm soát. Ứng dụng cần chọn các nhóm phù hợp với nghiệp vụ và dùng nhất quán ở mọi nơi ghi nhận timer. Không đưa message exception, stack trace, request ID, order ID hoặc nội dung phản hồi vào tag.

## 2. Dùng Timer.Sample để dừng timer sau khi biết kết quả

`Timer.Sample` lưu thời điểm bắt đầu bằng clock của registry. Khi thao tác kết thúc, gọi `sample.stop(timer)` để ghi thời lượng đã trôi qua vào timer được chọn. Timer có thể được lấy từ registry sau khi đã xác định tag:

```java
Timer.Sample sample = Timer.start(registry);

String outcome = "error";
try {
    PaymentResult result = paymentGateway.charge(command);
    outcome = result.approved() ? "success" : "rejected";
    return result;
} catch (TimeoutException ex) {
    outcome = "timeout";
    throw ex;
} finally {
    sample.stop(registry.timer(
            "payment.processing",
            "outcome", outcome));
}
```

Ví dụ trên đặt mặc định `outcome` là `error`. Khi thao tác trả về thành công, code thay giá trị bằng `success` hoặc `rejected`; khi timeout, code đặt `timeout`. Nếu một exception khác hoặc lỗi phát sinh trước khi xác định kết quả, giá trị mặc định `error` vẫn được dùng. Khối `finally` luôn dừng sample một lần cho luồng thực thi này, kể cả khi exception được ném lại cho caller.

`registry.timer(name, key, value)` lấy hoặc đăng ký timer với tên và tag đã cho. Khi cùng tên và cùng tập tag được dùng lại, các lần đo được cộng dồn vào cùng meter. Vì vậy, những lần thanh toán thành công sẽ được ghi vào `payment.processing{outcome="success"}`, còn những lần bị từ chối sẽ vào `payment.processing{outcome="rejected"}`.

Không gọi `sample.stop(...)` nhiều lần cho cùng một sample. Hãy chọn một điểm hoàn tất duy nhất để ghi nhận thời lượng, thường là `finally` đối với thao tác đồng bộ hoặc callback hoàn tất đối với thao tác bất đồng bộ.

## 3. Đóng gói quy tắc phân loại để tái sử dụng

Khi có nhiều thao tác cần đo theo kết quả, có thể đóng gói cách đo trong một component metrics. Ví dụ sau nhận một `Callable` để thực thi công việc và một `Predicate` để phân biệt kết quả thành công với kết quả nghiệp vụ bị từ chối:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class PaymentMetrics {
    private final MeterRegistry registry;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(
            Callable<T> operation,
            Predicate<T> isSuccessful) throws Exception {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "error";

        try {
            T result = operation.call();
            outcome = isSuccessful.test(result) ? "success" : "rejected";
            return result;
        } catch (TimeoutException ex) {
            outcome = "timeout";
            throw ex;
        } catch (CancellationException ex) {
            outcome = "cancelled";
            throw ex;
        } finally {
            sample.stop(registry.timer(
                    "payment.processing",
                    "outcome", outcome));
        }
    }
}
```

Cách gọi có thể truyền phương thức nghiệp vụ và quy tắc nhận diện thành công:

```java
PaymentResult result = paymentMetrics.record(
        () -> paymentGateway.charge(command),
        PaymentResult::approved);
```

Trong ví dụ, `PaymentResult::approved` trả về `true` khi giao dịch được chấp nhận. Nếu kết quả trả về `false`, timer được gắn `outcome=rejected`. Timeout và cancellation được phân loại riêng; các exception còn lại giữ nhóm `error` mặc định rồi được ném lại. Component metrics không nuốt exception hoặc thay đổi kết quả nghiệp vụ.

Nếu thao tác có nhiều trạng thái nghiệp vụ, hãy thay predicate bằng một hàm phân loại trả về enum hoặc một tập giá trị cố định. Chẳng hạn, một API tìm kiếm có thể phân biệt `found`, `not_found`, `timeout` và `error`. Hãy tránh chuyển trực tiếp chuỗi tự do do service hoặc người dùng cung cấp thành tag.

## 4. Phân biệt kết quả nghiệp vụ với lỗi kỹ thuật

Không phải mọi kết quả không thành công đều là exception. Ví dụ thanh toán bị từ chối do không đủ hạn mức là kết quả nghiệp vụ hợp lệ; gateway không nhất thiết ném exception. Nếu gom tất cả trường hợp đó vào `error`, dashboard sẽ đánh đồng việc từ chối bình thường với sự cố hạ tầng.

Nên xác định ranh giới rõ ràng:

- `success`: thao tác hoàn tất và đạt kết quả mong đợi.
- `rejected`: thao tác hoàn tất bình thường nhưng nghiệp vụ không chấp nhận yêu cầu.
- `timeout`: không hoàn tất trong thời hạn cho phép.
- `error`: lỗi kỹ thuật hoặc exception ngoài các nhóm đã phân loại riêng.
- `cancelled`: thao tác bị hủy và hệ thống cần theo dõi riêng trường hợp đó.

Không nhất thiết phải dùng đủ năm giá trị trong mọi ứng dụng. Nếu nghiệp vụ không có khái niệm từ chối hoặc hủy, hãy bỏ nhóm không cần thiết. Điều quan trọng là định nghĩa tag có ý nghĩa, số lượng hữu hạn và thống nhất giữa các instance.

## 5. Giữ cardinality của tag kết quả ở mức thấp

Mỗi giá trị tag kết hợp với tên meter tạo ra một meter ID riêng. Với Prometheus, mỗi tổ hợp label tương ứng với một time series. Do đó, tag `outcome` nên có một số ít giá trị đã định nghĩa.

Ví dụ phù hợp:

```java
registry.timer("payment.processing", "outcome", "success");
registry.timer("payment.processing", "outcome", "rejected");
registry.timer("payment.processing", "outcome", "timeout");
registry.timer("payment.processing", "outcome", "error");
```

Ví dụ không phù hợp:

```java
// Không dùng exception message làm tag.
registry.timer("payment.processing", "error", exception.getMessage());

// Không dùng mã giao dịch hoặc request ID làm tag.
registry.timer("payment.processing", "transaction", transactionId);
```

Exception message và ID thường có số lượng giá trị rất lớn, thậm chí gần như duy nhất. Đưa chúng vào tag có thể tạo hàng loạt time series, làm tăng bộ nhớ và chi phí lưu trữ. Nếu cần điều tra lỗi cụ thể, hãy ghi exception cùng correlation ID trong log hoặc trace; metrics chỉ nên lưu nhóm kết quả tổng hợp.

Nên dùng cùng một key `outcome` và cùng vocabulary cho các timer cùng ý nghĩa. Không để một instance ghi `failure`, instance khác ghi `error`, còn instance thứ ba ghi tên exception class, vì khi tổng hợp sẽ xuất hiện nhiều nhóm không nhất quán.

## 6. Đọc timer theo outcome ở hệ thống nhận

Với Prometheus registry, timer Micrometer thường được công bố thành các chuỗi `_count` và `_sum`; khi histogram được bật, có thêm các bucket `_bucket`. Tên chính xác phụ thuộc naming convention và base unit, vì vậy hãy kiểm tra endpoint `/actuator/prometheus` trước khi viết truy vấn.

Ví dụ timer `payment.processing` có tag `outcome` có thể được công bố thành:

```text
# HELP payment_processing_seconds Duration of payment processing
# TYPE payment_processing_seconds histogram
payment_processing_seconds_bucket{outcome="success",le="0.1"} 80
payment_processing_seconds_bucket{outcome="success",le="0.5"} 115
payment_processing_seconds_bucket{outcome="success",le="+Inf"} 120
payment_processing_seconds_count{outcome="success"} 120
payment_processing_seconds_sum{outcome="success"} 18.4
payment_processing_seconds_bucket{outcome="timeout",le="0.1"} 0
payment_processing_seconds_bucket{outcome="timeout",le="0.5"} 1
payment_processing_seconds_bucket{outcome="timeout",le="+Inf"} 3
payment_processing_seconds_count{outcome="timeout"} 3
payment_processing_seconds_sum{outcome="timeout"} 9.0
```

Các mẫu trên chỉ minh họa định dạng và ý nghĩa. Có thể dùng `rate()` để tính số lần hoàn tất mỗi giây theo outcome:

```promql
sum by (outcome) (
  rate(payment_processing_seconds_count[5m])
)
```

Có thể ước tính thời lượng trung bình trong cửa sổ bằng tốc độ tăng của tổng thời gian chia cho tốc độ tăng của số lần thực hiện:

```promql
sum by (outcome) (
  rate(payment_processing_seconds_sum[5m])
)
/
sum by (outcome) (
  rate(payment_processing_seconds_count[5m])
)
```

Đơn vị kết quả là giây mỗi lần thực hiện. Nếu một outcome không có lần ghi nhận trong cửa sổ, mẫu số có thể bằng 0 hoặc không tồn tại; dashboard cần xử lý trường hợp không có dữ liệu thay vì diễn giải thành thời lượng bằng 0.

Khi histogram được bật, có thể tính p95 riêng cho từng outcome:

```promql
histogram_quantile(
  0.95,
  sum by (le, outcome) (
    rate(payment_processing_seconds_bucket[5m])
  )
)
```

Việc phân tách theo outcome giúp phát hiện trường hợp request lỗi hoặc timeout có thời lượng khác biệt rõ so với request thành công. Tuy nhiên, không nên kết luận timeout luôn chậm hơn nếu timeout được trả về sớm do circuit breaker hoặc giới hạn nội bộ; cần hiểu chính sách timeout và đường xử lý thực tế.

## 7. Kiểm thử việc chọn tag sau khi hoàn tất

Có thể dùng `SimpleMeterRegistry` để xác minh timer được ghi vào đúng outcome mà không cần khởi động Prometheus. Ví dụ kiểm tra cả thành công và từ chối:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PaymentMetricsTest {
    @Test
    void recordsTimerWithOutcomeAfterOperationCompletes() throws Exception {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            PaymentMetrics metrics = new PaymentMetrics(registry);

            boolean approved = metrics.record(() -> true, Boolean::booleanValue);
            boolean rejected = metrics.record(() -> false, Boolean::booleanValue);

            assertThat(approved).isTrue();
            assertThat(rejected).isFalse();
            assertThat(registry.get("payment.processing")
                    .tag("outcome", "success")
                    .timer()
                    .count()).isEqualTo(1L);
            assertThat(registry.get("payment.processing")
                    .tag("outcome", "rejected")
                    .timer()
                    .count()).isEqualTo(1L);
        }
    }
}
```

Nên có test riêng cho timeout và lỗi kỹ thuật để bảo đảm exception vẫn được ném lại và timer vẫn được ghi với outcome tương ứng:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeoutException;

@Test
void recordsTimeoutAndPropagatesException() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        PaymentMetrics metrics = new PaymentMetrics(registry);

        assertThrows(TimeoutException.class, () ->
                metrics.record(() -> {
                    throw new TimeoutException("gateway timed out");
                }, Boolean::booleanValue));

        assertThat(registry.get("payment.processing")
                .tag("outcome", "timeout")
                .timer()
                .count()).isEqualTo(1L);
    }
}
```

Unit test này kiểm tra việc chọn tag và số lần ghi nhận. Nó không kiểm tra định dạng Prometheus hoặc tên metric sau export; phần đó cần integration test với registry adapter thực tế.

## 8. Đo thao tác bất đồng bộ

Với thao tác đồng bộ, khối `finally` chạy sau khi lời gọi trả về hoặc ném exception. Với thao tác bất đồng bộ, phương thức có thể trả về `CompletableFuture` ngay khi công việc vẫn đang chạy. Nếu dừng sample trong `finally` của phương thức tạo future, timer chỉ đo thời gian tạo future, không đo thời gian hoàn tất công việc.

Hãy dừng sample trong callback hoàn tất:

```java
Timer.Sample sample = Timer.start(registry);

return paymentGateway.chargeAsync(command)
        .whenComplete((result, error) -> {
            String outcome = "error";
            try {
                if (error != null) {
                    if (causedByCancellation(error)) {
                        outcome = "cancelled";
                    } else if (causedByTimeout(error)) {
                        outcome = "timeout";
                    }
                } else {
                    outcome = result.approved() ? "success" : "rejected";
                }
            } finally {
                sample.stop(registry.timer(
                        "payment.processing",
                        "outcome", outcome));
            }
        });
```

`causedByTimeout` và `causedByCancellation` là các hàm phân loại exception của ứng dụng; trong thực tế, chúng có thể cần đi qua `CompletionException` hoặc `ExecutionException` để kiểm tra nguyên nhân gốc. Callback `whenComplete` chạy khi stage hoàn tất, dù hoàn tất bình thường hay exceptional. Giá trị mặc định là `error`, và `finally` bảo đảm sample vẫn được dừng nếu việc đọc kết quả phát sinh lỗi. Cần bảo đảm sample chỉ được dừng một lần.

Nếu future bị hủy, hãy xác định cách thư viện bất đồng bộ biểu diễn cancellation và ánh xạ về nhóm `cancelled` nếu muốn theo dõi riêng. Đừng coi việc phương thức trả về một future là thời điểm thao tác đã hoàn tất.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gắn `outcome=success` trước khi gọi service | Exception và timeout bị tính nhầm là thành công | Xác định outcome sau khi thao tác trả về hoặc thất bại |
| Chỉ ghi timer khi không có exception | Thời lượng lỗi và timeout bị mất | Ghi trong `finally` hoặc callback hoàn tất |
| Gộp từ chối nghiệp vụ vào lỗi kỹ thuật | Dashboard phản ánh sai tỷ lệ lỗi hệ thống | Tách `rejected` khỏi `error` nếu nghiệp vụ cần phân biệt |
| Dùng exception message làm tag | Cardinality tăng không kiểm soát | Ánh xạ về nhóm lỗi hữu hạn; chi tiết để trong log/trace |
| Dùng nhiều vocabulary cho cùng một outcome | Dữ liệu bị chia thành các series rời rạc | Chuẩn hóa key và tập giá trị tag |
| Dừng sample ngay sau khi nhận future | Timer chỉ đo thời gian tạo future | Dừng sample khi future thực sự hoàn tất |
| Dừng một sample nhiều lần | Ghi nhận thời lượng trùng hoặc sai logic | Chọn một điểm hoàn tất duy nhất cho mỗi sample |

## 10. Quy trình áp dụng

Khi cần phân tích thời gian theo kết quả, hãy thực hiện theo trình tự:

1. Xác định ranh giới bắt đầu và kết thúc của thao tác cần đo.
2. Định nghĩa tập outcome nhỏ, rõ nghĩa, chẳng hạn `success`, `rejected`, `timeout`, `error`.
3. Bắt đầu `Timer.Sample` ngay trước thao tác.
4. Xác định outcome từ kết quả trả về hoặc loại lỗi khi thao tác hoàn tất.
5. Dừng sample với timer có tag `outcome` tương ứng trong `finally` hoặc callback hoàn tất.
6. Giữ nguyên exception và kết quả nghiệp vụ để instrumentation không thay đổi hành vi ứng dụng.
7. Kiểm thử từng nhánh outcome bằng `SimpleMeterRegistry`.
8. Kiểm tra output registry và truy vấn backend để xác nhận số liệu được phân tách đúng.

Chọn tag kết quả sau khi thao tác hoàn tất giúp timer phản ánh đúng cả thời lượng lẫn outcome. Khi dùng `Timer.Sample` và một vocabulary tag có kiểm soát, đội vận hành có thể so sánh độ trễ giữa thành công, từ chối, timeout và lỗi kỹ thuật mà không làm tăng cardinality ngoài ý muốn.
