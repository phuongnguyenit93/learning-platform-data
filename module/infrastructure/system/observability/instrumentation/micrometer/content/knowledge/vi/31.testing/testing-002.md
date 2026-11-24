# MockClock để điều khiển thời gian mà không cần chờ thật

Các meter đo thời lượng và trạng thái theo thời gian thường khó kiểm thử nếu dựa vào đồng hồ thật. Một test dùng `Thread.sleep()` có thể chạy chậm, dao động theo tải máy và thất bại ngẫu nhiên khi CI bị quá tải. Micrometer cung cấp `MockClock` để test chủ động tiến thời gian, nhờ đó kiểm tra timer, long task timer và các hành vi phụ thuộc clock một cách nhanh, lặp lại được.

`MockClock` là một implementation của `Clock` trong `micrometer-core`. Khi truyền clock này vào registry, các meter lấy thời gian từ clock đó. Test có thể gọi `clock.add(...)` để tiến cả thời gian wall-clock và monotonic-clock theo một lượng xác định mà không phải chờ thread ngủ.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, đây là kỹ thuật quan trọng để kiểm thử `Timer.Sample`, `Timer.record(...)`, `LongTaskTimer`, cửa sổ thống kê và các instrumentation có đo thời gian. Bài viết tập trung vào cách đưa cùng một clock giả vào registry và cách xác minh kết quả bằng số liệu cụ thể.

## 1. Vì sao không nên dùng Thread.sleep() trong test?

Một cách kiểm thử đơn giản thường thấy là:

```java
Timer.Sample sample = Timer.start(registry);
Thread.sleep(250);
sample.stop(registry.timer("job.duration"));
```

Test này phụ thuộc vào bộ lập lịch của hệ điều hành. Lệnh `sleep(250)` chỉ yêu cầu thread không chạy trong ít nhất khoảng thời gian đó; nó không bảo đảm thức dậy chính xác sau 250 ms. Trên máy CI đang tải cao, thời gian thực tế có thể dài hơn đáng kể.

Ngoài ra, mỗi test có thể phải chờ hàng trăm mili giây hoặc nhiều giây. Khi có nhiều test về timeout, expiry, retry và long-running task, thời gian suite tăng nhanh.

Với `MockClock`, test diễn đạt trực tiếp điều cần kiểm tra:

```java
Timer.Sample sample = Timer.start(registry);
clock.add(250, TimeUnit.MILLISECONDS);
sample.stop(registry.timer("job.duration"));
```

Clock tiến đúng 250 ms theo yêu cầu của test. Không có thread nào phải chờ và kết quả không phụ thuộc tải máy.

## 2. Clock của Micrometer có hai loại thời gian

Interface `io.micrometer.core.instrument.Clock` cung cấp hai khái niệm:

| API | Đơn vị | Mục đích |
| --- | --- | --- |
| `wallTime()` | milliseconds | Thời điểm theo đồng hồ lịch, thường dùng cho timestamp |
| `monotonicTime()` | nanoseconds | Đo khoảng thời gian đã trôi qua |

Để đo duration, Micrometer dùng monotonic time vì nó không bị điều chỉnh theo giờ hệ thống như wall clock. Ví dụ, đồng hồ máy có thể được đồng bộ NTP hoặc người quản trị thay đổi; thời lượng một thao tác vẫn cần tăng đều và không bị âm chỉ vì giờ lịch thay đổi.

`MockClock.add(amount, unit)` tiến thời gian giả theo lượng chỉ định. Cách gọi thường dùng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;

MockClock clock = new MockClock();

long wallBefore = clock.wallTime();
long monotonicBefore = clock.monotonicTime();

clock.add(500, TimeUnit.MILLISECONDS);

assertThat(clock.wallTime() - wallBefore).isEqualTo(500L);
assertThat(clock.monotonicTime() - monotonicBefore)
        .isEqualTo(TimeUnit.MILLISECONDS.toNanos(500));
```

Không tự lấy `System.currentTimeMillis()` hoặc `System.nanoTime()` ở giữa một test đang dùng `MockClock`, vì như vậy phép đo sẽ trộn hai nguồn thời gian khác nhau.

## 3. Tạo registry sử dụng MockClock

Tạo `MockClock` rồi truyền nó vào constructor của registry. Ví dụ với `SimpleMeterRegistry`:

```java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

MockClock clock = new MockClock();
SimpleMeterRegistry registry = new SimpleMeterRegistry(
        SimpleConfig.DEFAULT,
        clock);
```

Điểm quan trọng là meter và `Timer.Sample` phải dùng clock lấy từ cùng registry. Khi gọi `Timer.start(registry)`, sample sử dụng clock của registry. Nếu test tạo sample từ một clock khác rồi ghi vào timer thuộc registry này, thời gian đo sẽ không còn nhất quán.

Trong test, đóng registry sau khi sử dụng:

```java
try (SimpleMeterRegistry registry = new SimpleMeterRegistry(
        SimpleConfig.DEFAULT, clock)) {
    // Đăng ký meter và thực hiện assertion.
}
```

`SimpleMeterRegistry` phù hợp cho unit test vì meter được cập nhật ngay trong bộ nhớ, không cần scrape endpoint hay kết nối backend. Nếu đang kiểm thử một registry adapter cụ thể, hãy truyền cùng `MockClock` vào registry adapter đó nếu constructor/config của adapter cho phép.

## 4. Kiểm thử Timer.Sample mà không chờ thật

`Timer.Sample` ghi nhận monotonic time tại thời điểm bắt đầu. Khi gọi `stop(timer)`, sample tính thời gian đã trôi qua và ghi một lần vào timer.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class TimerSampleTest {
    @Test
    void recordsElapsedTimeFromMockClock() {
        MockClock clock = new MockClock();

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry(
                SimpleConfig.DEFAULT, clock)) {
            Timer timer = registry.timer("orders.process.duration");

            Timer.Sample sample = Timer.start(registry);
            clock.add(250, TimeUnit.MILLISECONDS);
            sample.stop(timer);

            assertThat(timer.count()).isEqualTo(1L);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(250.0);
        }
    }
}
```

Test chứng minh:

1. Timer chưa ghi nhận lần nào trước khi sample dừng.
2. `clock.add(250, MILLISECONDS)` làm monotonic time tiến đúng 250 ms.
3. `sample.stop(timer)` ghi một observation vào timer.
4. `count` bằng 1 và tổng thời lượng bằng 250 ms.

Không cần đặt assertion vào thời gian thực thi của test. Kết quả hoàn toàn do clock giả điều khiển.

## 5. Kiểm thử Timer.record(Runnable)

Nếu chỉ cần đo một đoạn code đồng bộ, `Timer.record(Runnable)` có thể đo thời lượng trực tiếp. Trong test, đoạn công việc có thể tiến `MockClock`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

@Test
void recordRunnableMeasuresMockClockDuration() {
    MockClock clock = new MockClock();

    try (SimpleMeterRegistry registry = new SimpleMeterRegistry(
            SimpleConfig.DEFAULT, clock)) {
        Timer timer = registry.timer("cache.refresh.duration");

        timer.record(() -> clock.add(125, TimeUnit.MILLISECONDS));

        assertThat(timer.count()).isEqualTo(1L);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(125.0);
    }
}
```

`Timer.record(...)` lấy thời điểm trước và sau khi chạy lambda từ clock của registry. Khi lambda tiến mock clock, khoảng chênh lệch được ghi vào timer.

Nếu công việc ném exception, timer vẫn cần ghi nhận thời gian đã trôi qua. Có thể kiểm tra điều này bằng một test riêng:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

@Test
void recordRunnableRecordsDurationWhenWorkFails() {
    MockClock clock = new MockClock();

    try (SimpleMeterRegistry registry = new SimpleMeterRegistry(
            SimpleConfig.DEFAULT, clock)) {
        Timer timer = registry.timer("payment.call.duration");

        assertThatThrownBy(() -> timer.record(() -> {
            clock.add(80, TimeUnit.MILLISECONDS);
            throw new IllegalStateException("gateway unavailable");
        })).isInstanceOf(IllegalStateException.class);

        assertThat(timer.count()).isEqualTo(1L);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(80.0);
    }
}
```

Test vừa xác nhận duration được ghi ở đường lỗi, vừa xác nhận exception gốc vẫn được truyền ra ngoài. Không nên bắt exception trong production chỉ để timer có thể ghi nhận; API `record` chịu trách nhiệm ghi duration trong quá trình hoàn tất lời gọi.

## 6. Kiểm thử LongTaskTimer đang hoạt động

`LongTaskTimer` đo các tác vụ vẫn đang chạy. Khác với Timer thông thường, nó có thể cung cấp số tác vụ active và tổng thời lượng hiện tại trước khi task kết thúc.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

@Test
void tracksActiveTaskDuration() {
    MockClock clock = new MockClock();

    try (SimpleMeterRegistry registry = new SimpleMeterRegistry(
            SimpleConfig.DEFAULT, clock)) {
        LongTaskTimer timer = LongTaskTimer.builder("batch.import.active")
                .register(registry);

        LongTaskTimer.Sample sample = timer.start();
        clock.add(3, TimeUnit.SECONDS);

        assertThat(timer.activeTasks()).isEqualTo(1L);
        assertThat(timer.duration(TimeUnit.SECONDS)).isEqualTo(3.0);

        sample.stop();

        assertThat(timer.activeTasks()).isZero();
    }
}
```

Trong lúc sample chưa dừng, `activeTasks()` bằng 1 và `duration(...)` phản ánh thời gian đã trôi qua. Sau `sample.stop()`, tác vụ không còn active. MockClock giúp kiểm thử chính xác trạng thái đang chạy mà không phải giữ test thread ngủ trong ba giây.

Với nhiều task đồng thời, `LongTaskTimer.duration(unit)` biểu diễn tổng thời lượng của các task đang active theo đơn vị yêu cầu. Hãy kiểm tra `activeTasks()` và duration trong một thời điểm đã được test điều khiển rõ ràng.

## 7. Kiểm thử Observation tạo Timer bằng MockClock

Khi dùng `DefaultMeterObservationHandler`, observation được chuyển thành timer khi dừng. Nếu registry dùng `MockClock`, test có thể chủ động tiến thời gian giữa lúc bắt đầu và dừng observation:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

@Test
void observationTimerUsesRegistryMockClock() {
    MockClock clock = new MockClock();

    try (SimpleMeterRegistry meters = new SimpleMeterRegistry(
            SimpleConfig.DEFAULT, clock)) {
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meters).build());

        Observation.createNotStarted("inventory.reserve", observations)
                .lowCardinalityKeyValue("warehouse", "primary")
                .observe(() -> clock.add(400, TimeUnit.MILLISECONDS));

        Timer timer = meters.get("inventory.reserve")
                .tag("warehouse", "primary")
                .tag("error", "none")
                .timer();

        assertThat(timer.count()).isEqualTo(1L);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(400.0);
    }
}
```

Điều kiện quan trọng là `MockClock` phải được truyền vào `MeterRegistry` được metrics handler sử dụng. ObservationRegistry không có clock riêng để đo Timer trong ví dụ này; handler dùng registry nhận vào để ghi duration.

Nếu ứng dụng dùng tracing handler cùng lúc, trace có thể dùng clock hoặc tracer riêng. Một test về metrics duration không tự động điều khiển timestamp của mọi span exporter. Hãy cấu hình clock của tracer riêng nếu cần kiểm thử timestamp tracing.

## 8. MockClock và thời gian hết hạn của thống kê

Một số thống kê phân phối của Timer và DistributionSummary sử dụng cửa sổ thời gian để tính `max` hoặc duy trì dữ liệu theo cấu hình. Khi cần kiểm tra hành vi hết hạn, có thể cấu hình `expiry` và tiến MockClock vượt qua cửa sổ đó.

Ví dụ khai báo Timer có thời gian tồn tại của thống kê max ngắn:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

@Test
void timeWindowMaxExpiresWhenMockClockAdvances() {
    MockClock clock = new MockClock();
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry(
            SimpleConfig.DEFAULT, clock)) {
        Timer timer = Timer.builder("http.server.request.duration")
                .distributionStatisticExpiry(Duration.ofSeconds(2))
                .distributionStatisticBufferLength(1)
                .register(registry);

        timer.record(900, TimeUnit.MILLISECONDS);
        assertThat(timer.max(TimeUnit.MILLISECONDS)).isEqualTo(900.0);

        clock.add(3, TimeUnit.SECONDS);
        assertThat(timer.max(TimeUnit.MILLISECONDS)).isZero();
    }
}
```

Với cấu hình cửa sổ một buffer và expiry hai giây, khi clock tiến vượt cửa sổ, max cũ hết hiệu lực. Nếu dùng buffer length lớn hơn một, dữ liệu có thể tồn tại qua nhiều cửa sổ; thời điểm hết hạn phụ thuộc `expiry × bufferLength` và cách registry triển khai rolling window.

Đây là phép thử cho thống kê time-window như max, không phải phép thử xóa toàn bộ lịch sử Timer. `count` và `totalTime` là số liệu tích lũy của timer; chúng không trở về zero chỉ vì max của cửa sổ cũ hết hạn.

## 9. Phân biệt thời gian ghi trực tiếp và thời gian đo từ clock

Các API Timer có hai cách ghi khác nhau:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
@Test
void recordsKnownDurationWithoutAdvancingClock() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        Timer timer = registry.timer("external.operation.duration");
        timer.record(250, TimeUnit.MILLISECONDS);

        assertThat(timer.count()).isEqualTo(1L);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(250.0);
    }
}
```

Lệnh này ghi một duration đã biết; nó không cần chờ clock tiến. Đây là lựa chọn tốt khi test một nhánh logic nhận duration từ bên ngoài.

```java
Timer.Sample sample = Timer.start(registry);
clock.add(250, TimeUnit.MILLISECONDS);
sample.stop(timer);
```

Cách này kiểm tra chính xác cơ chế đo elapsed time dựa trên clock của registry. Dùng khi cần xác minh instrumentation start/stop hoặc code đo thời gian thực thi.

Không dùng `timer.record(250, MILLISECONDS)` để khẳng định `Timer.Sample` đang dùng đúng clock; hai đường code kiểm tra hai hành vi khác nhau.

## 10. Kiểm thử step registry cần điều khiển cả clock và publisher

Các registry dạng step như Datadog hoặc Influx gom số liệu theo chu kỳ và gửi batch. `MockClock` có thể điều khiển thời gian mà registry đọc, nhưng việc tiến clock không tự động bảo đảm scheduler thực hiện tác vụ publish.

Khi test step registry, cần kiểm soát cả hai yếu tố:

1. Clock được truyền vào registry để xác định ranh giới step.
2. Lời gọi publish/scheduler được điều khiển để test biết chính xác khi nào batch được xuất.

Một test có thể tạo subclass registry trong test để expose phương thức publish, hoặc inject scheduler/test executor nếu adapter hỗ trợ. Sau khi tiến MockClock qua ranh giới step, gọi publisher theo cách test kiểm soát rồi xác minh batch được gửi. Không dùng `Thread.sleep(step)` để chờ scheduler vì nó khiến test chậm và không ổn định.

MockClock chỉ điều khiển nguồn thời gian được registry sử dụng; nó không giả lập network, không tự chạy scheduled task và không thay thế fake HTTP server. Hãy tách test clock/aggregation khỏi test giao tiếp HTTP nếu mục tiêu là xác minh riêng từng lớp.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tiến MockClock nhưng Timer không đổi | Registry đang dùng `Clock.SYSTEM` hoặc clock khác | Truyền MockClock vào constructor/config của registry |
| Timer.Sample đo thời gian gần bằng 0 | Sample và registry dùng clock khác nhau hoặc test chưa tiến clock | Dùng `Timer.start(registry)` và tiến đúng clock đã inject |
| Vẫn dùng `Thread.sleep()` trong test | Chưa chuyển phép đo sang MockClock | Dùng `clock.add(amount, unit)` |
| Counter không đổi khi clock tiến | Counter không phụ thuộc thời gian | Gọi `increment()`; clock không làm counter tự tăng |
| LongTaskTimer không còn active | Sample đã stop hoặc test lấy nhầm timer | Giữ sample hoạt động đến assertion và kiểm tra đúng meter |
| Max chưa hết hạn sau khi tiến clock | Expiry/buffer length tạo cửa sổ dài hơn dự kiến | Tính `expiry × bufferLength` và cấu hình rõ ràng |
| Step registry không publish sau `clock.add()` | Scheduler chưa chạy | Điều khiển publisher/test scheduler riêng |
| Timestamp test khác thời gian hệ thống | Code dùng `Instant.now()` thay vì registry clock | Inject `Clock` vào logic tạo timestamp hoặc tách khỏi test meter |
| Test dùng chung MockClock giữa nhiều test | Thời gian bị giữ từ test trước | Tạo MockClock mới cho từng test |

## 12. Quy trình viết test thời gian xác định

Khi kiểm thử meter có phụ thuộc thời gian, hãy làm theo trình tự:

1. Xác định API đang đo elapsed time, wall-clock timestamp hay rolling window.
2. Tạo một `MockClock` mới cho test.
3. Truyền clock đó vào registry trước khi tạo meter.
4. Bắt đầu sample hoặc task sau khi registry đã được tạo.
5. Dùng `clock.add(amount, unit)` để tiến thời gian theo kịch bản.
6. Dừng sample/task hoặc kích hoạt publish theo đúng lifecycle.
7. Assert count, total time, active task, max hoặc output cần kiểm tra.
8. Đóng registry và không chia sẻ clock mutable giữa các test.
9. Nếu kiểm thử step registry, điều khiển publisher/scheduler riêng ngoài clock.

`MockClock` làm cho thời gian trở thành dữ liệu do test điều khiển. Bằng cách truyền nó vào registry, test có thể kiểm tra Timer, LongTaskTimer, Observation và thống kê theo cửa sổ mà không cần chờ thật. Hãy dùng clock giả cho unit test về thời gian; giữ integration test riêng cho scheduler, network và backend export để mỗi test xác minh đúng một trách nhiệm.

## Tài liệu tham khảo

- [Micrometer 1.18: Testing](https://docs.micrometer.io/micrometer/reference/concepts/testing.html)
- [Micrometer 1.18: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer 1.18: Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
- [Micrometer Clock API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Clock.html)
- [Micrometer MockClock API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MockClock.html)
