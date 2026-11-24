# Đảm bảo kết thúc phép đo trên đường thành công và đường ngoại lệ

## Mục tiêu

Khi đo thời gian xử lý một request hoặc một thao tác nghiệp vụ, phép đo phải được ghi nhận dù thao tác kết thúc bình thường hay ném exception. Nếu chỉ dừng Timer ở cuối nhánh thành công, các lần xử lý lỗi sẽ không có latency tương ứng. Dashboard khi đó có thể cho thấy thời gian xử lý tốt hơn thực tế, đặc biệt khi hệ thống đang gặp timeout hoặc lỗi phụ thuộc.

Micrometer cung cấp hai cách phổ biến để bảo đảm Timer được kết thúc:

- Dùng các phương thức bao quanh khối thực thi như Timer.record(Runnable) hoặc Timer.recordCallable(...). Micrometer tự ghi thời lượng sau khi khối thực thi kết thúc, kể cả khi khối đó ném exception.
- Dùng Timer.Sample khi cần điều khiển điểm bắt đầu, điểm kết thúc hoặc xác định tag sau khi đã biết kết quả. Đặt sample.stop(...) trong khối finally để phép đo được dừng trên mọi đường thoát thông thường.

Bài này giải thích cách chọn giữa hai cách trên, cách giữ nguyên exception để tầng gọi xử lý, cách đo thao tác bất đồng bộ và cách kiểm thử để chứng minh cả đường thành công lẫn đường lỗi đều tạo observation.

## Vì sao phải kết thúc Timer trên mọi đường thực thi?

Giả sử một dịch vụ thanh toán đo thời gian gọi payment provider. Trong một khoảng thời gian, hệ thống có:

| Kết quả | Số lần | Thời lượng trung bình |
|---|---:|---:|
| Thành công | 900 | 180 ms |
| Timeout | 80 | 3.000 ms |
| Lỗi khác | 20 | 250 ms |

Nếu Timer chỉ được dừng ở nhánh thành công, metrics chỉ phản ánh 900 lần xử lý. 100 lần thất bại biến mất khỏi phân bố thời gian. Khi đó, latency p95 và mean có thể thấp hơn đáng kể so với thời gian mà hệ thống thực sự tiêu tốn.

Một Timer được thiết kế để đo thời lượng của một thao tác. Mỗi lần ghi nhận tạo một observation gồm thời lượng; Timer đồng thời theo dõi count, total time và các thống kê phân bố đã cấu hình. Nếu một lần gọi mất ba giây rồi ném timeout, ba giây đó vẫn là thời gian hệ thống đã tiêu tốn và cần được ghi nhận.

Điều quan trọng là xác định rõ phạm vi của phép đo:

- Đo toàn bộ business operation nếu muốn phản ánh thời gian người dùng chờ, bao gồm retry.
- Đo từng lần gọi dependency nếu muốn theo dõi latency của từng attempt.
- Đo riêng phần xử lý thành công nếu đó là câu hỏi vận hành cụ thể, nhưng cần đặt tên metric và mô tả thể hiện rõ phạm vi này.

Không trộn các định nghĩa khác nhau vào cùng một Timer.

## Dùng Timer.record(Runnable) cho khối đồng bộ

Khi chỉ cần đo một khối code và không cần chọn tag dựa trên kết quả, có thể dùng Timer.record(Runnable):

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private final Timer paymentTimer;
    private final PaymentGateway paymentGateway;

    public PaymentService(
            MeterRegistry registry,
            PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
        this.paymentTimer = Timer.builder("business.payment.processing")
                .description("Thời gian xử lý một lần thanh toán")
                .register(registry);
    }

    public void charge(PaymentCommand command) {
        paymentTimer.record((Runnable) () -> paymentGateway.charge(command));
    }
}
~~~

Timer.record(Runnable) thực hiện các bước:

1. Lấy thời điểm bắt đầu từ clock monotonic của registry.
2. Chạy Runnable.
3. Trong finally nội bộ, lấy thời điểm kết thúc và ghi thời lượng vào Timer.
4. Nếu Runnable ném RuntimeException hoặc Error, exception tiếp tục truyền ra ngoài sau khi thời lượng đã được ghi.

Vì vậy, đoạn code sau vẫn ghi một observation khi paymentGateway.charge(...) ném exception:

~~~java
paymentTimer.record((Runnable) () -> {
    throw new IllegalStateException("Payment provider failed");
});
~~~

Exception vẫn được ném ra cho tầng gọi. Timer chỉ bổ sung phép đo; nó không bắt exception để biến lỗi thành kết quả thành công.

Đây là cách ngắn gọn cho khối đồng bộ không cần tag động. Nếu muốn đo một hàm trả về kết quả, có thể dùng Supplier overload của record. Nếu hàm có checked exception, dùng recordCallable:

~~~java
public PaymentReceipt charge(PaymentCommand command) throws Exception {
    return paymentTimer.recordCallable(
            () -> paymentGateway.charge(command)
    );
}
~~~

recordCallable(...) trả lại kết quả của Callable và khai báo throws Exception. Khi Callable ném exception, exception được truyền ra ngoài sau khi thời lượng đã được ghi. Hãy giữ chữ ký throws phù hợp với API nghiệp vụ của ứng dụng hoặc chuyển exception tại lớp xử lý lỗi theo quy ước của domain.

## Dùng Timer.Sample với try/finally

Timer.Sample phù hợp khi muốn tự kiểm soát điểm bắt đầu và kết thúc. Sample lưu thời điểm bắt đầu theo clock của registry; khi gọi stop(timer), Micrometer tính thời lượng và ghi vào Timer được truyền vào.

Mẫu cơ bản:

~~~java
Timer.Sample sample = Timer.start(registry);
try {
    paymentGateway.charge(command);
} finally {
    sample.stop(paymentTimer);
}
~~~

Khối finally được thực thi khi:

- Khối try hoàn tất bình thường.
- Khối try ném checked exception.
- Khối try ném RuntimeException.
- Khối try ném Error.
- Khối try thoát bằng return hoặc break.

Nhờ đó, sample.stop(...) được gọi trên mọi đường thoát của khối try. Exception vẫn tiếp tục truyền ra ngoài sau khi finally hoàn tất.

### Ví dụ đầy đủ trong service

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private final MeterRegistry registry;
    private final PaymentGateway paymentGateway;

    public PaymentService(
            MeterRegistry registry,
            PaymentGateway paymentGateway) {
        this.registry = registry;
        this.paymentGateway = paymentGateway;
    }

    public PaymentReceipt charge(PaymentCommand command) throws Exception {
        Timer.Sample sample = Timer.start(registry);

        try {
            return paymentGateway.charge(command);
        } finally {
            sample.stop(registry.timer("business.payment.processing"));
        }
    }
}
~~~

Ở đây, return trong khối try không bỏ qua finally. Trước khi phương thức trả PaymentReceipt, sample.stop(...) vẫn được gọi. Nếu paymentGateway.charge(...) ném exception, finally vẫn ghi thời lượng rồi exception tiếp tục truyền đến caller.

Đừng đặt sample.stop(...) sau khối try nếu có đường thực thi có thể ném exception trước khi tới câu lệnh đó. Đó là lỗi phổ biến khiến các lần thất bại không được đo.

## Gắn tag kết quả mà vẫn bảo đảm stop

Một lợi ích của Timer.Sample là Timer đích có thể được chọn tại thời điểm kết thúc. Điều này hữu ích khi tag phụ thuộc kết quả mà chỉ biết sau khi thao tác chạy xong, chẳng hạn success, timeout hoặc error.

~~~java
public PaymentReceipt charge(PaymentCommand command) throws Exception {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        return paymentGateway.charge(command);
    } catch (PaymentTimeoutException ex) {
        outcome = "timeout";
        throw ex;
    } catch (Exception | Error ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(registry.timer(
                "business.payment.processing",
                "outcome", outcome
        ));
    }
}
~~~

Mẫu này có ba đặc điểm:

1. Thành công giữ outcome là success.
2. Timeout được phân loại thành timeout; các exception hoặc Error khác được phân loại thành error.
3. finally luôn dừng sample và chọn Timer theo outcome cuối cùng.

Các nhánh catch chỉ cập nhật tag rồi ném lại exception. Chúng không nuốt lỗi, không trả về kết quả giả và không thay đổi hành vi xử lý lỗi của tầng gọi.

Tag phải có tập giá trị hữu hạn. Không đưa exception message, stack trace, request ID hoặc tên host vào tag. Nếu cần chi tiết để điều tra, ghi exception vào log hoặc trace. Phần thiết kế tag cần tuân thủ cùng quy tắc cardinality của module Micrometer.

### Tránh gọi stop hai lần

Khi đã dùng finally để dừng sample, không gọi sample.stop(...) thêm trong catch:

~~~java
// Sai: một lần thất bại có thể được ghi hai lần.
Timer.Sample sample = Timer.start(registry);
try {
    paymentGateway.charge(command);
} catch (RuntimeException ex) {
    sample.stop(errorTimer);
    throw ex;
} finally {
    sample.stop(successTimer);
}
~~~

Đoạn code sai trên có thể ghi hai observation cho một lần gọi bị lỗi: một lần vào errorTimer và một lần vào successTimer. Hãy chọn đúng một điểm stop. Nếu tag phụ thuộc kết quả, cập nhật biến outcome trong catch rồi gọi stop duy nhất trong finally.

## Đo thao tác bất đồng bộ

Một lỗi khác thường gặp là đo một phương thức chỉ khởi chạy công việc bất đồng bộ:

~~~java
timer.record((Runnable) () -> paymentGateway.chargeAsync(command));
~~~

Nếu chargeAsync(...) trả về ngay một CompletionStage hoặc CompletableFuture, Timer ở trên chỉ đo thời gian tạo và trả về stage. Nó không đo thời gian chờ payment provider hoàn tất.

Với thao tác bất đồng bộ, hãy dừng sample khi stage hoàn tất:

~~~java
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.CompletionStage;

public CompletionStage<PaymentReceipt> chargeAsync(
        PaymentCommand command) throws Exception {
    Timer.Sample sample = Timer.start(registry);

    try {
        return paymentGateway.chargeAsync(command)
                .whenComplete((receipt, error) -> {
                    String outcome = error == null ? "success" : "error";
                    sample.stop(registry.timer(
                            "business.payment.processing",
                            "outcome", outcome
                    ));
                });
    } catch (Exception | Error ex) {
        // Lời gọi khởi tạo stage thất bại đồng bộ trước khi trả về.
        sample.stop(registry.timer(
                "business.payment.processing",
                "outcome", "error"
        ));
        throw ex;
    }
}
~~~

whenComplete(...) chạy khi stage hoàn tất bình thường hoặc hoàn tất với lỗi. Nếu stage bị hủy và biểu diễn việc hủy bằng completion lỗi, callback cũng nhận được error khác null. Trường hợp lời gọi chargeAsync(...) ném exception đồng bộ trước khi trả về stage được xử lý trong catch và sample cũng được dừng.

Đoạn code này ghi một observation cho toàn bộ thời gian chờ kết quả. Nó không đo từng lần retry nội bộ nếu paymentGateway tự retry. Nếu cần latency của từng attempt, hãy instrument tại nơi thực hiện attempt.

Nếu stage không bao giờ hoàn tất, callback không chạy và sample không được dừng. Hãy xác định timeout, cancellation và chính sách kết thúc của công việc bất đồng bộ. Với công việc dài hạn có thể chạy hàng phút hoặc hàng giờ, cân nhắc LongTaskTimer để quan sát tác vụ đang chạy thay vì giữ một Timer thông thường cho toàn bộ vòng đời dài.

## Những lỗi khiến phép đo không được kết thúc

### Chỉ stop ở nhánh thành công

~~~java
Timer.Sample sample = Timer.start(registry);
try {
    service.execute();
    sample.stop(timer);
} catch (RuntimeException ex) {
    throw ex;
}
~~~

Khi service.execute() ném exception, sample.stop(timer) không được gọi. Đưa lệnh stop vào finally để bao phủ cả hai đường.

### Nuốt exception để ghi metrics

~~~java
try {
    service.execute();
} catch (Exception ex) {
    log.error("Operation failed", ex);
    // Không ném lại exception và không trả kết quả lỗi rõ ràng.
} finally {
    sample.stop(timer);
}
~~~

finally giúp kết thúc phép đo, nhưng catch đã thay đổi hành vi nghiệp vụ bằng cách nuốt lỗi. Không bắt exception chỉ để Timer có thể dừng. Hãy để exception tiếp tục đến tầng chịu trách nhiệm xử lý, hoặc chuyển đổi nó theo contract của ứng dụng.

### Dừng sample trước khi công việc thực sự hoàn tất

Với API bất đồng bộ, dừng sample ngay sau khi nhận CompletionStage chỉ đo thời gian khởi tạo. Hãy đăng ký callback hoàn tất và dừng sample tại callback đó.

### Dùng thời gian đồng hồ dân sự

Không nên tự đo thời lượng bằng cách lấy hiệu hai giá trị Instant.now() hoặc LocalDateTime.now(). Đồng hồ hệ thống có thể được đồng bộ hoặc điều chỉnh, khiến hiệu thời gian bị sai. Timer.Sample sử dụng clock monotonic của registry, phù hợp cho đo elapsed time.

Nếu tự đo bằng Java, dùng System.nanoTime() để lấy hiệu thời gian. Không dùng System.currentTimeMillis() để đo latency.

### Ghi hai Timer cho cùng một thao tác ngoài ý muốn

Nếu vừa gọi timer.record(...) vừa tự tạo Timer.Sample cho cùng một đoạn code, cùng thao tác có thể bị ghi hai lần. Chọn một cơ chế làm điểm ghi nhận chính. Có thể dùng các Timer riêng ở nhiều tầng nếu chúng đo các phạm vi khác nhau và có tên mô tả rõ.

## Kiểm thử đường thành công và đường ngoại lệ

Kiểm thử cần chứng minh hai điều:

- Khi thao tác thành công, count của Timer tăng một.
- Khi thao tác ném exception, count vẫn tăng một và exception vẫn được truyền ra ngoài.

SimpleMeterRegistry phù hợp cho unit test vì không cần kết nối backend:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TimerCompletionTest {
    @Test
    void recordsDurationWhenRunnableSucceeds() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Timer timer = registry.timer("test.operation");

            timer.record(() -> {
                // Thao tác hoàn tất bình thường.
            });

            assertThat(timer.count()).isEqualTo(1);
        } finally {
            registry.close();
        }
    }

    @Test
    void recordsDurationAndRethrowsWhenRunnableFails() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Timer timer = registry.timer("test.operation");

            assertThatThrownBy(() -> timer.record((Runnable) () -> {
                throw new IllegalStateException("simulated failure");
            })).isInstanceOf(IllegalStateException.class)
                    .hasMessage("simulated failure");

            assertThat(timer.count()).isEqualTo(1);
        } finally {
            registry.close();
        }
    }
}
~~~

Test thứ hai kiểm tra đồng thời việc ghi nhận và việc truyền exception. Chỉ kiểm tra count mà không kiểm tra exception có thể bỏ sót lỗi nuốt exception trong code instrumentation.

### Kiểm thử Timer.Sample với finally

~~~java
@Test
void sampleIsStoppedWhenOperationThrows() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        Timer timer = registry.timer("test.sample");
        Timer.Sample sample = Timer.start(registry);

        assertThatThrownBy(() -> {
            try {
                throw new IllegalArgumentException("invalid payment");
            } finally {
                sample.stop(timer);
            }
        }).isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid payment");

        assertThat(timer.count()).isEqualTo(1);
    } finally {
        registry.close();
    }
}
~~~

Test này chứng minh finally dừng sample và exception gốc vẫn được truyền ra ngoài. Với code có tag outcome, nên kiểm tra cả Timer success và Timer error để xác nhận mỗi đường chỉ tăng đúng một meter.

### Kiểm thử bất đồng bộ

Với CompletionStage, hãy tạo CompletableFuture trong test và kiểm tra:

1. Trước khi future hoàn tất, count của Timer vẫn bằng 0.
2. Khi complete(...) thành công, Timer tương ứng với outcome success tăng một.
3. Khi completeExceptionally(...) hoặc cancel(...), Timer outcome error tăng một.
4. Khi phương thức khởi tạo future ném exception đồng bộ, Timer vẫn được ghi một lần.

Các test này giúp phát hiện việc dừng Timer quá sớm hoặc không dừng khi callback lỗi.

## Chọn cách đo phù hợp

| Tình huống | Cách dùng phù hợp | Lý do |
|---|---|---|
| Đo một Runnable đồng bộ | timer.record(runnable) | Micrometer tự ghi thời lượng sau khi khối kết thúc |
| Đo Callable có kết quả và checked exception | timer.recordCallable(callable) | Trả kết quả và truyền exception |
| Chọn tag dựa trên response hoặc outcome | Timer.Sample + try/finally | Chọn Timer đích khi thao tác đã kết thúc |
| Nhiều đường return/throw | Timer.Sample + finally | Một điểm stop chung cho mọi đường thoát |
| CompletionStage hoặc CompletableFuture | Timer.Sample + whenComplete | Đo đến khi công việc bất đồng bộ hoàn tất |
| Tác vụ chạy rất lâu | LongTaskTimer | Quan sát thời gian tác vụ vẫn đang chạy |

## Checklist khi đưa Timer vào ứng dụng

1. Định nghĩa chính xác thao tác bắt đầu và kết thúc ở đâu.
2. Xác định có cần đo cả request lỗi, timeout và retry hay không.
3. Dùng Timer.record hoặc recordCallable cho khối đồng bộ đơn giản.
4. Dùng Timer.Sample khi cần chọn tag hoặc Timer ở thời điểm kết thúc.
5. Với Timer.Sample, đặt sample.stop(...) trong finally và chỉ gọi đúng một lần.
6. Nếu cần tag outcome, cập nhật giá trị trong catch rồi ném lại exception.
7. Không nuốt exception chỉ để ghi nhận metrics.
8. Với bất đồng bộ, dừng sample trong callback hoàn tất thay vì sau khi khởi tạo stage.
9. Dùng clock monotonic để đo elapsed time.
10. Kiểm thử cả success, checked exception, runtime exception, Error và completion bất đồng bộ.
11. Xác minh count tăng đúng một cho mỗi thao tác thuộc phạm vi đo.
12. Kiểm tra metric export và dashboard có phân biệt outcome như dự định.

## Kết luận

Để Timer phản ánh đúng latency, phép đo phải kết thúc dù thao tác thành công hay thất bại. Với khối đồng bộ đơn giản, Timer.record(Runnable) và recordCallable(...) là lựa chọn gọn vì Micrometer tự ghi thời lượng sau khi khối thực thi kết thúc. Khi cần điều khiển tag hoặc nhiều đường return/throw, dùng Timer.Sample và gọi stop duy nhất trong finally. Với tác vụ bất đồng bộ, dừng sample khi CompletionStage hoàn tất. Cuối cùng, kiểm thử cả count lẫn việc exception vẫn được truyền ra ngoài để bảo đảm instrumentation không làm sai số liệu hoặc thay đổi hành vi nghiệp vụ.

## Tài liệu tham khảo

- [Micrometer - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): record(Runnable), recordCallable, wrap và Timer.Sample.
- [Micrometer - Timer API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Timer.html): chữ ký API và hợp đồng các phương thức ghi nhận thời lượng.
- [Micrometer - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): vòng đời observation và cách dùng Timer.Sample với try/finally.
- [Micrometer - Long Task Timer](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html): theo dõi các tác vụ vẫn đang chạy.
