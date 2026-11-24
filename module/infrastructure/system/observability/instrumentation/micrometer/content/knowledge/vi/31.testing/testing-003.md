# Kiểm thử Timer.Sample và thời lượng trên nhánh thành công hoặc ngoại lệ

`Timer.Sample` cho phép bắt đầu đo trước khi biết meter đích cần dùng. Khi operation kết thúc, code chọn `Timer` phù hợp rồi gọi `sample.stop(timer)`. Cách này hữu ích khi tag của timer phụ thuộc kết quả operation, chẳng hạn `outcome=success` hoặc `outcome=failure`.

Một phép kiểm thử tốt cần xác nhận cả hai nhánh đều ghi nhận đúng một observation, thời lượng được tính từ thời điểm start đến stop, và exception vẫn được truyền về caller. Không nên dùng `Thread.sleep()` để tạo khoảng thời gian trong unit test: test sẽ chậm và phụ thuộc scheduler của hệ điều hành. Dùng `MockClock` cùng `SimpleMeterRegistry` để kiểm soát thời gian một cách xác định.

## Timer.Sample hoạt động ra sao?

`Timer.Sample` lưu mốc thời gian bắt đầu từ clock của `MeterRegistry`. Khi gọi `stop(timer)`, Micrometer lấy thời gian hiện tại từ clock, tính elapsed duration rồi ghi một observation vào Timer được truyền vào.

~~~mermaid
sequenceDiagram
    participant Test
    participant Sample as Timer.Sample
    participant Clock as MockClock
    participant Timer
    Test->>Sample: start(registry)
    Sample->>Clock: đọc monotonic time
    Test->>Clock: advance 125 ms
    Test->>Sample: stop(timer)
    Sample->>Clock: đọc monotonic time
    Sample->>Timer: record elapsed duration
    Timer-->>Test: count=1, totalTime=125 ms
~~~

Điểm quan trọng là `Timer.Sample` không tự chọn tên meter hoặc tag. Code quyết định Timer khi dừng sample. Vì vậy, có thể dùng kết quả operation để chọn tag mà không cần tạo trước nhiều sample:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    return paymentGateway.authorize(command);
} catch (RuntimeException | Error exception) {
    outcome = "failure";
    throw exception;
} finally {
    sample.stop(registry.timer(
            "payment.processing",
            "outcome", outcome));
}
~~~

Trong ví dụ, `finally` đảm bảo sample được dừng ở cả nhánh trả về bình thường và nhánh ném unchecked exception. Exception vẫn được ném lại; instrumentation chỉ ghi nhận thời lượng và không biến lỗi thành kết quả thành công.

## Vì sao nên dùng MockClock?

Đo thời gian thực trong test thường tạo ra assertion không ổn định:

~~~java
long started = System.nanoTime();
Thread.sleep(100);
long elapsed = System.nanoTime() - started;
~~~

Thời gian thực tế có thể dài hơn 100 ms do tải máy, lịch chạy thread hoặc độ phân giải clock. Nếu assertion yêu cầu một con số chính xác, test sẽ thất bại ngẫu nhiên. Nếu dùng một khoảng quá rộng, test lại khó phát hiện lỗi tính duration.

`MockClock` cho phép test chủ động tiến đồng hồ:

~~~java
MockClock clock = new MockClock();
clock.add(Duration.ofMillis(125));
~~~

Khi registry dùng clock này, `Timer.Sample` đo đúng khoảng thời gian test đã điều khiển. Test có thể khẳng định `totalTime` chính xác mà không phải chờ thật.

## Tạo registry với MockClock

`SimpleMeterRegistry` phù hợp cho unit test vì giữ meter trong bộ nhớ và không cần backend export. Truyền cùng một `MockClock` vào registry để sample và timer dùng chung nguồn thời gian:

~~~java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;

MockClock clock = new MockClock();
SimpleMeterRegistry registry =
        new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
~~~

Không tạo `Timer.Sample` bằng một clock khác với clock của registry đang ghi Timer. Cách khởi tạo `Timer.start(registry)` đảm bảo sample dùng clock của chính registry.

## Kiểm thử nhánh thành công

Ví dụ service nhỏ đo thời gian xử lý thanh toán. `Supplier<T>` giữ ví dụ gọn vì thao tác được kiểm thử chỉ phát sinh unchecked exception:

~~~java
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class PaymentMetrics {
    private final MeterRegistry registry;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T measure(Supplier<T> operation) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return operation.get();
        } catch (RuntimeException | Error exception) {
            outcome = "failure";
            throw exception;
        } finally {
            sample.stop(registry.timer(
                    "payment.processing",
                    "outcome", outcome));
        }
    }
}
~~~

Unit test điều khiển clock tăng 125 ms trong operation:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PaymentMetricsTest {
    @Test
    void recordsDurationWhenOperationSucceeds() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        PaymentMetrics metrics = new PaymentMetrics(registry);

        String result = metrics.measure(() -> {
            clock.add(Duration.ofMillis(125));
            return "approved";
        });

        Timer timer = registry.get("payment.processing")
                .tag("outcome", "success")
                .timer();

        assertThat(result).isEqualTo("approved");
        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(125.0);

        registry.close();
    }
}
~~~

Test xác nhận ba điều:

1. Operation trả kết quả bình thường.
2. Timer có đúng một observation.
3. Tổng thời lượng bằng chính xác 125 ms mà test đã thêm vào `MockClock`.

Không cần kiểm tra `max` trong bài test cơ bản này. Mục tiêu là xác nhận `Timer.Sample` ghi đúng count và elapsed duration.

## Kiểm thử nhánh ném exception

Nhánh lỗi cần xác nhận duration vẫn được ghi và exception không bị nuốt. Dùng `assertThatThrownBy` để kiểm tra exception đi ra ngoài service:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PaymentMetricsFailureTest {
    @Test
    void recordsDurationAndRethrowsWhenOperationFails() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        PaymentMetrics metrics = new PaymentMetrics(registry);

        assertThatThrownBy(() -> metrics.measure(() -> {
            clock.add(Duration.ofMillis(80));
            throw new IllegalStateException("gateway unavailable");
        }))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("gateway unavailable");

        Timer timer = registry.get("payment.processing")
                .tag("outcome", "failure")
                .timer();

        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(80.0);

        registry.close();
    }
}
~~~

Test này phát hiện một lỗi phổ biến: chỉ gọi `sample.stop(...)` trước câu lệnh `return` ở nhánh thành công. Nếu operation ném exception, timer khi đó không được ghi. Đặt thao tác stop trong `finally` giải quyết cả hai đường kết thúc.

## Kiểm tra hai nhánh dùng đúng tag

Sau hai test, có thể kiểm tra registry có hai series riêng:

| Series | Count | Total time |
|---|---:|---:|
| `payment.processing{outcome="success"}` | 1 | 125 ms |
| `payment.processing{outcome="failure"}` | 1 | 80 ms |

Tag `outcome` chỉ có hai giá trị nên cardinality được giới hạn. Không dùng exception message hoặc ID giao dịch làm tag. Nếu cần phân loại lỗi sâu hơn, ánh xạ về một tập hữu hạn như `timeout`, `dependency`, `validation` hoặc `unexpected`.

Nếu cả hai nhánh đều được ghi vào cùng một Timer mà không có tag outcome, vẫn có thể kiểm tra tổng count và duration, nhưng dashboard không thể phân biệt thời lượng thành công với thất bại. Chọn tag theo câu hỏi vận hành thực tế, tránh thêm tag chỉ để lưu mọi chi tiết exception.

## Kiểm thử exception checked

Ví dụ `PaymentMetrics.measure(Supplier<T>)` chỉ nhận thao tác có thể ném unchecked exception. Nếu API được đo khai báo checked exception, có thể tạo functional interface riêng:

~~~java
@FunctionalInterface
public interface ThrowingSupplier<T> {
    T get() throws Exception;
}
~~~

Service có thể bắt `Exception` và `Error`, ghi outcome rồi ném lại đúng đối tượng:

~~~java
public <T> T measureChecked(ThrowingSupplier<T> operation) throws Exception {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        return operation.get();
    } catch (Exception | Error exception) {
        outcome = "failure";
        throw exception;
    } finally {
        sample.stop(registry.timer(
                "payment.processing",
                "outcome", outcome));
    }
}
~~~

Không bọc mọi checked exception thành `RuntimeException` chỉ để phù hợp với `Supplier`; việc bọc có thể thay đổi hợp đồng API và làm mất kiểu exception mà caller đang xử lý.

## Kiểm tra sample chỉ được stop một lần

Một `Timer.Sample` nên được dùng như trạng thái của một lần đo. API không tự đánh dấu sample là đã dừng để ngăn lần gọi tiếp theo; mỗi lần gọi `stop(...)` đều có thể ghi thêm một observation với elapsed time tính từ cùng mốc bắt đầu. Vì vậy, gọi hai lần thường tạo dữ liệu trùng:

~~~java
Timer.Sample sample = Timer.start(registry);
sample.stop(successTimer);
sample.stop(failureTimer); // Ghi thêm một observation, dùng lại cùng elapsed time.
~~~

Nếu thật sự cần ghi cùng duration vào nhiều meter, hãy làm điều đó có chủ đích và kiểm thử count của từng meter. Với luồng thông thường, chọn một Timer đích và stop đúng một lần trong `finally`.

Không tái sử dụng một sample làm field của singleton service. Nhiều request có thể chạy đồng thời; mỗi operation phải tạo sample cục bộ riêng. Đặt sample trong biến cục bộ hoặc state riêng của operation.

## Kiểm thử trực tiếp Timer.Sample mà không qua service

Khi muốn kiểm tra riêng hành vi Micrometer, có thể viết test ngắn không cần lớp service:

~~~java
MockClock clock = new MockClock();
SimpleMeterRegistry registry =
        new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);

Timer.Sample sample = Timer.start(registry);
clock.add(Duration.ofMillis(40));

Timer timer = registry.timer("worker.duration", "outcome", "success");
long stoppedNanos = sample.stop(timer);

assertThat(timer.count()).isEqualTo(1);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(40.0);
assertThat(stoppedNanos).isEqualTo(TimeUnit.MILLISECONDS.toNanos(40));

registry.close();
~~~

Giá trị trả về từ `sample.stop(timer)` là elapsed time theo nanosecond. Test này hữu ích để xác nhận API và clock; test qua service ở các phần trước còn xác nhận code ứng dụng chọn đúng outcome và giữ nguyên exception.

## Những assertion nên có

Khi viết test cho Timer.Sample, nên kiểm tra:

- `count()` tăng đúng một lần cho mỗi operation hoàn tất.
- `totalTime(unit)` phản ánh chính xác khoảng thời gian được điều khiển.
- Nhánh success dùng tag `outcome=success`.
- Nhánh exception dùng tag `outcome=failure` hoặc nhóm lỗi hữu hạn đã chọn.
- Exception vẫn được ném về caller với kiểu và message mong đợi.
- Không xuất hiện series sai do code dừng sample ở nhiều nhánh.

Không nên chỉ kiểm tra meter tồn tại. Meter có thể được đăng ký nhưng không có observation nếu sample chưa được stop. Ngược lại, không nên chỉ kiểm tra count mà bỏ qua totalTime; một lỗi có thể dừng timer ở thời điểm sai nhưng count vẫn tăng.

## Lỗi thường gặp khi kiểm thử

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `count()` bằng 0 | Sample chưa được stop hoặc test lấy nhầm tag | Kiểm tra `finally` và tag trên Timer |
| Duration bằng 0 | MockClock không được truyền vào registry hoặc chưa advance clock | Dùng cùng một MockClock và gọi `clock.add(...)` trước stop |
| Duration thay đổi giữa các lần chạy | Dùng `Thread.sleep()` hoặc system clock | Dùng MockClock |
| Nhánh lỗi không có metric | Chỉ stop ở đường return thành công | Stop trong `finally` |
| Exception không đến caller | Catch rồi không rethrow hoặc trả fallback ngoài ý muốn | Ném lại exception sau khi cập nhật outcome |
| Count tăng hai lần | Stop cùng sample ở catch và finally | Chọn một điểm stop duy nhất, thường là finally |
| Test tìm không thấy meter | Tên meter hoặc tag không khớp | Tìm bằng đúng tên và đầy đủ tag |
| Test phụ thuộc thứ tự chạy | Dùng registry static hoặc dùng chung giữa test | Tạo registry mới cho mỗi test và đóng sau khi dùng |
| Tag tạo quá nhiều series | Dùng exception message hoặc ID làm tag | Dùng outcome hữu hạn |

## Checklist hoàn thành

- [ ] Registry thử nghiệm dùng `MockClock`.
- [ ] `Timer.Sample` được tạo từ chính registry đó.
- [ ] Test success advance clock trước khi operation hoàn tất.
- [ ] Test exception advance clock rồi ném exception.
- [ ] Cả hai nhánh đều stop sample đúng một lần.
- [ ] Timer count bằng một ở mỗi series được kỳ vọng.
- [ ] Total time khớp chính xác thời gian đã advance.
- [ ] Exception vẫn được truyền về caller.
- [ ] Tag outcome có tập giá trị hữu hạn.
- [ ] Registry được tạo mới và đóng sau mỗi test.
- [ ] Không dùng `Thread.sleep()` để đồng bộ hoặc đo thời gian.

## Tóm tắt

Kiểm thử `Timer.Sample` cần xác minh cả thời điểm dừng và Timer đích. Tạo sample từ registry, dùng `MockClock` để điều khiển elapsed time, rồi kiểm tra `count` và `totalTime` trên nhánh thành công lẫn nhánh exception. Đặt `sample.stop(...)` trong `finally`, chọn tag outcome có cardinality thấp và ném lại exception giúp phép đo phản ánh đúng thời lượng mà không thay đổi hành vi của operation.
