# Sử dụng Timer.Sample để đo thao tác có nhiều nhánh kết thúc

## 1. Bài toán: một lần bắt đầu, nhiều cách kết thúc

Một thao tác tra cứu có thể kết thúc theo nhiều đường: từ chối đầu vào không hợp lệ, trả dữ liệu đã có trong bộ nhớ đệm, tải dữ liệu mới, hoặc ném ngoại lệ. Nếu đặt lệnh ghi thời gian ngay trước từng `return`, ta dễ bỏ sót một nhánh. Nếu thêm lệnh ghi cả trong `catch` lẫn `finally`, một thao tác lại có thể bị tính hai lần.

Điều cần thiết kế trước tiên là **ranh giới của một lần đo**:

- Bắt đầu ở đâu: trước kiểm tra đầu vào, sau khi lấy được tài nguyên, hay trước khi gửi công việc đi?
- Kết thúc ở đâu: khi phương thức trả về, khi tài nguyên đã được dọn xong, hay khi kết quả bất đồng bộ hoàn tất?
- Mỗi kết quả cuối được phân loại thế nào: thành công, dùng cache, bị từ chối, lỗi hoặc bị hủy?

`Timer.Sample` của Micrometer giữ lại mốc bắt đầu để ta chọn timer đích khi kết quả đã biết. Nó phù hợp khi các nhánh dùng chung ý nghĩa thời gian, nhưng nhãn kết quả chỉ xác định được ở cuối thao tác. [Hướng dẫn Timer.Sample của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_storing_start_state_in_timer_sample).

Ví dụ dưới đây dùng Java 17 trở lên và Micrometer 1.13, phù hợp với ngữ cảnh Spring Boot 3.3. Ta dùng đồng hồ kiểm chứng để tạo các khoảng thời gian cố định; những con số đó chứng minh cách ghi nhận, không phải kết quả benchmark của máy tính.

## 2. Timer, Sample và Clock giữ những vai trò khác nhau

| Thành phần | Vai trò | Vòng đời thường dùng |
| --- | --- | --- |
| `Timer` | Tích lũy số lần ghi và thời gian của một nhóm thao tác cùng tên, nhãn | Được đăng ký rồi dùng lại cho nhiều lần gọi |
| `Timer.Sample` | Giữ mốc bắt đầu của một lần đo cụ thể | Tạo mới cho mỗi thao tác |
| `MeterRegistry` | Quản lý các meter và cấu hình đồng hồ | Dùng chung trong ứng dụng theo cấu hình |
| `Clock` | Cung cấp mốc thời gian để tính khoảng đã trôi qua | Đi theo registry hoặc được chọn rõ ràng |

Về cơ chế, có thể hình dung:

```text
start(registry): lưu t0 từ đồng hồ của registry
        ↓
Thực hiện thao tác; xác định kết quả cuối
        ↓
stop(timer): lấy t1, tính t1 − t0, ghi khoảng đó vào timer
```

`Timer.start(registry)` lấy đồng hồ từ registry. `stop(timer)` ghi thời gian và trả về số nano giây đã đo. Đoạn triển khai `Sample` trong Micrometer 1.13 dùng `clock.monotonicTime()`; phép tính khoảng thời gian không dựa vào ngày giờ hiển thị trên đồng hồ hệ thống. [Triển khai Timer.Sample](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Timer.java).

Do đó, không dùng `LocalDateTime.now()` hoặc tự lấy hai mốc giờ lịch để thay cho cơ chế này. Thời gian của timer là thời gian đã trôi qua giữa hai mốc, có thể bao gồm chờ I/O và chờ được lập lịch; nó không mặc nhiên là thời gian CPU thực thi.

Một điểm dễ nhầm: `Timer.start()` không có tham số dùng đồng hồ hệ thống. Khi ứng dụng đã có registry, ưu tiên `Timer.start(registry)`, đặc biệt khi kiểm chứng bằng đồng hồ được điều khiển. `Timer.Sample` cũng không phải `AutoCloseable`; không đặt nó trong `try-with-resources` rồi chờ tự ghi khi đóng.

### Chọn timer ở cuối không có nghĩa tạo một tên mới cho từng lần gọi

Ta có thể đăng ký cùng tên `app.lookup.duration`, với nhãn `outcome` nhận các giá trị hữu hạn `rejected`, `cached`, `success`, `error`. Đó là các chuỗi số đo khác nhau thuộc cùng một phép đo.

Không dùng khóa tra cứu, mã đơn hàng, thông báo ngoại lệ hoặc mã người dùng làm giá trị nhãn thay đổi không giới hạn. Kết quả cuối nên được ánh xạ về một tập giá trị ổn định. [Quy tắc đặt tên và giới hạn giá trị nhãn](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

## 3. Thiết kế đồng bộ: chọn kết quả trong try, ghi một lần trong finally

Với thao tác đồng bộ, quy tắc thực dụng là:

1. Tạo một sample ngay trước phần xử lý thuộc phạm vi đo.
2. Khởi tạo biến kết quả với giá trị lỗi dự phòng.
3. Trong mỗi nhánh kết thúc bình thường, gán kết quả thích hợp trước `return`.
4. Nếu nhánh gọi một hàm có thể ném ngoại lệ, chỉ gán thành công sau khi hàm đó đã trả về.
5. Chỉ đặt một lệnh `sample.stop(...)`, ở `finally` ngoài cùng của phạm vi đo.

`finally` chạy khi luồng Java rời khối `try` theo cách trả về bình thường hoặc ném ngoại lệ. Vì vậy không cần bắt một ngoại lệ chỉ để ghi timer rồi ném lại. Ngoại lệ vẫn đi ra ngoài theo hợp đồng ban đầu của phương thức.

Mẫu gán kết quả có ý nghĩa: nếu gán thành công trước khi thực hiện bước tải dữ liệu, một lỗi trong bước tải có thể bị gắn nhãn thành công. Hãy hoàn tất phần việc quyết định kết quả rồi mới gán nhãn đó.

Cũng không `return` hoặc ném một ngoại lệ khác trong `finally` chỉ để phục vụ việc đo. Hành động đó có thể thay kết quả hoặc che mất ngoại lệ nghiệp vụ. Chọn từ các timer đã đăng ký sẵn giúp phần `finally` ngắn và tránh phải dựng nhãn tùy ý ở đường thoát.

## 4. Ví dụ hoàn chỉnh: bốn nhánh, mỗi lần gọi được ghi đúng một lần

### 4.1. Chuẩn bị thư viện và lệnh chạy

Tạo một thư mục thí nghiệm riêng. Lưu `pom.xml` sau để Maven tải Micrometer và các thư viện bắc cầu vào `lib/`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>timer-sample-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Phiên bản được chốt để tái lập thí nghiệm độc lập. Trong ứng dụng Spring Boot, để BOM của Boot quản lý phiên bản Micrometer phù hợp với ứng dụng.

Trong PowerShell, sau khi có Maven và JDK 17 trở lên:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies "-DoutputDirectory=lib"
javac --release 17 -cp "lib/*" TimerSampleBranchesDemo.java
java -cp ".;lib/*" TimerSampleBranchesDemo
```

Dấu `;` trong classpath trên là cú pháp Windows; trên Linux/macOS dùng `:`. Lần tải đầu cần truy cập kho phụ thuộc. Không cần Spring context, HTTP server hoặc dịch vụ bên ngoài cho thí nghiệm này.

### 4.2. Mã nguồn TimerSampleBranchesDemo.java

```java
import java.time.Duration;
import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class TimerSampleBranchesDemo {
    enum Outcome {
        REJECTED, CACHED, SUCCESS, ERROR
    }

    static final class LookupService {
        private final MeterRegistry registry;
        private final MockClock clock;
        private final Map<Outcome, Timer> timers = new EnumMap<>(Outcome.class);

        LookupService(MeterRegistry registry, MockClock clock) {
            this.registry = registry;
            this.clock = clock;
            for (Outcome outcome : Outcome.values()) {
                timers.put(outcome, Timer.builder("app.lookup.duration")
                        .description("Duration of a completed lookup")
                        .tag("outcome", outcome.name().toLowerCase(Locale.ROOT))
                        .register(registry));
            }
        }

        String lookup(String key) {
            Timer.Sample sample = Timer.start(registry);
            Outcome outcome = Outcome.ERROR;
            try {
                if (key == null || key.isBlank()) {
                    clock.add(Duration.ofMillis(1));
                    outcome = Outcome.REJECTED;
                    return "REJECTED";
                }
                if ("cached".equals(key)) {
                    clock.add(Duration.ofMillis(2));
                    outcome = Outcome.CACHED;
                    return "CACHED";
                }
                if ("boom".equals(key)) {
                    clock.add(Duration.ofMillis(4));
                    throw new IllegalStateException("backend unavailable");
                }
                clock.add(Duration.ofMillis(7));
                String result = "LOADED:" + key;
                outcome = Outcome.SUCCESS;
                return result;
            } finally {
                sample.stop(timers.get(outcome));
            }
        }
    }

    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            LookupService service = new LookupService(registry, clock);
            System.out.println("result=" + service.lookup(""));
            System.out.println("result=" + service.lookup("cached"));
            System.out.println("result=" + service.lookup("item-42"));
            try {
                service.lookup("boom");
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            long count = 0;
            double totalMillis = 0;
            for (Outcome outcome : Outcome.values()) {
                String tag = outcome.name().toLowerCase(Locale.ROOT);
                Timer timer = registry.get("app.lookup.duration").tag("outcome", tag).timer();
                double millis = timer.totalTime(TimeUnit.MILLISECONDS);
                System.out.printf(Locale.ROOT, "%s count=%d totalMs=%.1f%n",
                        tag, timer.count(), millis);
                count += timer.count();
                totalMillis += millis;
            }
            System.out.printf(Locale.ROOT, "all count=%d totalMs=%.1f meanMs=%.1f%n",
                    count, totalMillis, totalMillis / count);
        } finally {
            registry.close();
        }
    }
}
```

`MockClock` được dùng để mỗi nhánh có thời gian xác định. Các lệnh `clock.add(...)` mô phỏng thời gian xử lý, không yêu cầu chương trình ngủ và không mô tả thời gian thật của `String` hay cache. Trong mã nghiệp vụ thực tế, thay phần mô phỏng bằng xử lý thật; không tự tăng đồng hồ hoặc gán một thời lượng mong muốn vào timer.

Bốn timer được đăng ký khi tạo dịch vụ. Mỗi lần `lookup` tạo một sample riêng và chỉ chọn một timer trong `finally`. Nhánh lỗi không đổi `outcome`, nên giữ giá trị `ERROR`; ngoại lệ vẫn được ném ra ngoài.

### 4.3. Stdout phải nhận được

```text
result=REJECTED
result=CACHED
result=LOADED:item-42
caught=backend unavailable
rejected count=1 totalMs=1.0
cached count=1 totalMs=2.0
success count=1 totalMs=7.0
error count=1 totalMs=4.0
all count=4 totalMs=14.0 meanMs=3.5
```

Các giá trị không phụ thuộc tốc độ máy vì đồng hồ chỉ được tăng theo những bước ta đặt trong thí nghiệm. `Locale.ROOT` giúp phần thập phân được in bằng dấu chấm nhất quán.

| Lần gọi | Cách kết thúc | Nhãn được chọn | Thời gian ghi |
| --- | --- | --- | --- |
| `lookup("")` | Trả về sớm do đầu vào không hợp lệ | `rejected` | 1 ms |
| `lookup("cached")` | Trả về sớm từ nhánh cache | `cached` | 2 ms |
| `lookup("item-42")` | Hoàn tất bước tải dữ liệu mô phỏng | `success` | 7 ms |
| `lookup("boom")` | Ném `IllegalStateException` | `error` | 4 ms |

Tổng số bản ghi timer là 4, đúng bằng số lần gọi được đo, bao gồm lần lỗi. Tổng thời gian là `1 + 2 + 7 + 4 = 14 ms`; trung bình gộp là `14 / 4 = 3,5 ms`. Một `Timer` đã chứa số lần ghi; không cần thêm một counter trùng nghĩa chỉ để biết có bao nhiêu lần hoàn tất.

## 5. Đọc count và total time đúng phạm vi

Một sample không lưu danh sách các bước xử lý hay tên từng nhánh đã đi qua. Nó chỉ giúp ghi một khoảng thời gian vào timer được chọn. Trong ví dụ:

- Chọn `outcome=error` chỉ trả lời về những lần được phân loại lỗi.
- Cộng count của cả bốn kết quả cho biết số lần hoàn tất thuộc phạm vi đo.
- Cộng total time của cả bốn kết quả cho biết tổng thời gian của các lần đó.
- Để tính trung bình gộp, chia tổng thời gian gộp cho tổng count; không lấy trung bình đơn giản của các giá trị trung bình khi số lần của mỗi nhánh khác nhau.

Mỗi nhánh có thể chậm hoặc nhanh vì thực hiện những phần việc khác nhau. Không kết luận nhánh cache nhanh hơn từ những thời gian mô phỏng này; muốn đánh giá hiệu năng phải đo xử lý thật với lưu lượng và môi trường phù hợp.

Sample chưa dừng không tự làm tăng count. Nếu ứng dụng đang có một thao tác treo, các timer chỉ chứa thao tác đã hoàn tất có thể chưa phản ánh thao tác đó. Khi cần quan sát số tác vụ đang chạy và thời gian của tác vụ chưa xong, cân nhắc một `LongTaskTimer` riêng với đúng ranh giới; nó không thay cho thống kê các thao tác đã hoàn tất. [Long Task Timers của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html).

## 6. stop không phải lệnh đóng có tính “chỉ thực hiện một lần”

`Timer.Sample` không có cờ nội bộ bảo đảm chỉ ghi một lần. Trong Micrometer 1.13, mỗi lần `stop(timer)` lại tính khoảng từ mốc bắt đầu ban đầu rồi gọi `record` trên timer. Vì vậy, gọi hai lần không có nghĩa lần thứ hai bị bỏ qua hoặc chỉ đo phần thời gian sau lần dừng đầu. Đây là hành vi cần tự kiểm soát bằng vòng đời của thao tác. [Đối chiếu phương thức Sample.stop](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Timer.java).

Thí nghiệm riêng sau cố ý gọi sai hai lần để nhìn thấy hậu quả. Lưu thành `DoubleStopDemo.java`, dùng cùng thư mục `lib/`:

```java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class DoubleStopDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            Timer timer = registry.timer("demo.double.stop");
            Timer.Sample sample = Timer.start(registry);
            clock.add(Duration.ofMillis(10));
            System.out.println("firstNanos=" + sample.stop(timer));
            clock.add(Duration.ofMillis(5));
            System.out.println("secondNanos=" + sample.stop(timer));
            System.out.printf(Locale.ROOT, "count=%d totalMs=%.1f%n",
                    timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
        } finally {
            registry.close();
        }
    }
}
```

Chạy:

```powershell
javac --release 17 -cp "lib/*" DoubleStopDemo.java
java -cp ".;lib/*" DoubleStopDemo
```

Stdout:

```text
firstNanos=10000000
secondNanos=15000000
count=2 totalMs=25.0
```

Lần đầu ghi 10 ms. Lần sau ghi 15 ms tính từ cùng mốc bắt đầu, nên tổng là 25 ms trên 2 bản ghi. Nó không phải một bản ghi 15 ms và cũng không phải hai khoảng rời nhau 10 ms + 5 ms.

Từ đó có ba cách sử dụng cần tránh:

- Gọi `stop` trước `return`, rồi lại gọi trong `finally`.
- Gọi trong `catch`, rồi lại gọi trong `finally`.
- Lưu sample như một field của service để dùng lại cho các request khác nhau.

Có thể dùng lại các timer đã đăng ký vì chúng là đối tượng tích lũy nhiều lần đo. Sample là trạng thái của **một** lần đo. Nếu muốn đo hai giai đoạn hoặc hai ranh giới độc lập, hãy xác định hai phép đo riêng thay vì xem `stop` như lệnh đặt lại đồng hồ.

Nếu nhiều callback có thể cạnh tranh kết thúc cùng một thao tác, phải có nơi quyết định kết quả cuối duy nhất. Có thể tập trung chúng vào một future kết quả, hoặc dùng cơ chế chặn ghi lặp như `AtomicBoolean.compareAndSet(false, true)` tại đúng nơi sở hữu thao tác. Một cờ chống lặp chỉ ngăn số đo trùng; nó không tự giải quyết hợp đồng timeout, hủy hoặc ưu tiên giữa các kết quả nghiệp vụ.

## 7. Bất đồng bộ: phương thức trả về chưa phải công việc đã hoàn tất

Với phương thức trả `CompletableFuture`, khối `finally` của phương thức thường chạy ngay khi future được trả về. Nếu dừng sample ở đó, ta đang đo phần khởi tạo/gửi công việc, không phải thời gian chờ kết quả cuối.

```text
Bắt đầu sample
        ↓
Khởi chạy và nhận future nguồn
        ↓
Phương thức trả future cho người gọi
        ↓
Công việc vẫn có thể đang chạy
        ↓
Future nguồn hoàn tất thành công / lỗi / bị hủy
        ↓
Callback hoàn tất chọn timer và dừng sample
```

Cần xử lý riêng cả trường hợp hàm khởi chạy ném ngoại lệ **trước khi trả future**. Chỉ gắn `whenComplete` mà bỏ qua đường lỗi đồng bộ này sẽ mất một nhánh kết thúc.

### 7.1. Ví dụ hoàn chỉnh với future điều khiển được

Lưu thành `AsyncTimerSampleDemo.java`. Ta điều khiển việc hoàn tất future trong `main` để kiểm chứng mà không phụ thuộc lịch chạy luồng hay `Thread.sleep`.

```java
import java.time.Duration;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class AsyncTimerSampleDemo {
    private final MeterRegistry registry;
    private final Timer success;
    private final Timer error;
    private final Timer cancelled;

    AsyncTimerSampleDemo(MeterRegistry registry) {
        this.registry = registry;
        success = registry.timer("app.async.lookup.duration", "outcome", "success");
        error = registry.timer("app.async.lookup.duration", "outcome", "error");
        cancelled = registry.timer("app.async.lookup.duration", "outcome", "cancelled");
    }

    CompletableFuture<String> observe(Supplier<CompletableFuture<String>> launch) {
        Timer.Sample sample = Timer.start(registry);
        final CompletableFuture<String> source;
        try {
            source = Objects.requireNonNull(launch.get(), "source future");
        } catch (RuntimeException | Error ex) {
            sample.stop(error);
            throw ex;
        }
        return source.whenComplete((value, failure) -> {
            Throwable cause = failure;
            while (cause instanceof CompletionException && cause.getCause() != null) {
                cause = cause.getCause();
            }
            Timer target = cause == null ? success
                    : cause instanceof CancellationException ? cancelled : error;
            sample.stop(target);
        });
    }

    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            AsyncTimerSampleDemo demo = new AsyncTimerSampleDemo(registry);
            CompletableFuture<String> source = new CompletableFuture<>();
            CompletableFuture<String> observed = demo.observe(() -> source);
            System.out.println("pendingCount=" + demo.success.count());
            clock.add(Duration.ofMillis(20));
            source.complete("done");
            System.out.println("success=" + observed.join());

            CompletableFuture<String> failed = new CompletableFuture<>();
            CompletableFuture<String> observedFailure = demo.observe(() -> failed);
            clock.add(Duration.ofMillis(10));
            failed.completeExceptionally(new IllegalArgumentException("bad response"));
            printFailure("failure", observedFailure);

            CompletableFuture<String> cancelledSource = new CompletableFuture<>();
            CompletableFuture<String> observedCancellation = demo.observe(() -> cancelledSource);
            clock.add(Duration.ofMillis(30));
            cancelledSource.cancel(false);
            printFailure("cancelled", observedCancellation);

            try {
                demo.observe(() -> {
                    clock.add(Duration.ofMillis(5));
                    throw new IllegalStateException("launch failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println("launchFailure=" + ex.getClass().getSimpleName());
            }

            for (String outcome : new String[] { "success", "error", "cancelled" }) {
                Timer timer = registry.get("app.async.lookup.duration")
                        .tag("outcome", outcome).timer();
                System.out.printf(Locale.ROOT, "%s count=%d totalMs=%.1f%n",
                        outcome, timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
            }
        } finally {
            registry.close();
        }
    }

    private static void printFailure(String label, CompletableFuture<String> future) {
        try {
            future.join();
            throw new AssertionError("Expected exceptional completion");
        } catch (CompletionException | CancellationException ex) {
            Throwable cause = ex instanceof CompletionException ? ex.getCause() : ex;
            System.out.println(label + "=" + cause.getClass().getSimpleName());
        }
    }
}
```

Chạy với cùng thư mục thư viện:

```powershell
javac --release 17 -cp "lib/*" AsyncTimerSampleDemo.java
java -cp ".;lib/*" AsyncTimerSampleDemo
```

Stdout:

```text
pendingCount=0
success=done
failure=IllegalArgumentException
cancelled=CancellationException
launchFailure=IllegalStateException
success count=1 totalMs=20.0
error count=2 totalMs=15.0
cancelled count=1 totalMs=30.0
```

Có bốn thao tác được đo:

| Trường hợp | Nơi ghi nhận | Kết quả số đo |
| --- | --- | --- |
| Future nguồn hoàn tất bình thường | Callback `whenComplete` | `success`: 1 lần, 20 ms |
| Future nguồn hoàn tất với lỗi | Callback `whenComplete` | Đóng góp 1 lần, 10 ms vào `error` |
| Future nguồn bị hủy | Callback `whenComplete` | `cancelled`: 1 lần, 30 ms |
| Hàm khởi chạy ném ngoại lệ trước khi trả future | Khối `catch` quanh `launch.get()` | Đóng góp 1 lần, 5 ms vào `error` |

Vì vậy nhánh `error` có 2 bản ghi với tổng 15 ms. Tổng cả ba timer là 4 bản ghi, 65 ms. Khi future đầu tiên còn chờ, `pendingCount=0` cho thấy sample chưa tự ghi một lần hoàn tất.

Hai nơi gọi `stop` trong phương thức `observe` phục vụ **hai đường loại trừ nhau**: khởi chạy thất bại trước khi có future, hoặc đã nhận được future và gắn callback hoàn tất. Không có `finally` chung gọi thêm lần nữa.

`Objects.requireNonNull` làm rõ hợp đồng rằng hàm khởi chạy phải trả một future. Trả `null` là lỗi khởi chạy trong ví dụ này. Việc bỏ lớp bọc `CompletionException` giúp nhận diện nguyên nhân hủy trước khi chọn một trong ba timer hữu hạn.

### 7.2. Phạm vi và giới hạn của ví dụ future

`CompletableFuture` chỉ chấp nhận một lần chuyển sang trạng thái hoàn tất trong các lời gọi cạnh tranh thông thường như `complete`, `completeExceptionally`, `cancel`. Một callback hoàn tất tập trung giúp ta có một điểm ghi nhận cho future nguồn. Callback không có hậu tố `Async` có thể chạy ngay trên luồng hoàn tất future, nên chỉ làm công việc đo ngắn gọn tại đó. [Hợp đồng CompletableFuture của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

Trong thí nghiệm, hành động hủy được áp dụng vào **future nguồn** `cancelledSource`. Future trả về từ `whenComplete` là một stage phụ thuộc. Hủy stage mà người gọi nhận được không tự bảo đảm hủy future nguồn hoặc dừng công việc phía sau. Nếu API yêu cầu hủy từ phía người gọi cũng phải truyền xuống tác vụ, cần thiết kế cơ chế đó riêng; đừng suy ra nó từ `Timer.Sample`. Ngay cả khi future nguồn đã chuyển sang trạng thái bị hủy, điều đó cũng không tự bảo đảm tác vụ thật đã dừng. Timer trong ví dụ đo vòng đời kết quả của future nguồn.

Tương tự, hết thời gian chờ ở phía người gọi không nhất thiết là future nguồn đã hoàn tất với lỗi timeout. Phải định nghĩa đang đo thời gian người gọi chờ hay thời gian tác vụ thực sự tồn tại. Nếu muốn phân biệt timeout với lỗi chung, bổ sung một giá trị nhãn hữu hạn và một quy tắc phân loại rõ ràng tại điểm kết thúc mà ứng dụng sở hữu.

Ví dụ giả định việc ghi vào timer hợp lệ không ném ngoại lệ. Nếu callback `whenComplete` tự ném lỗi khi ghi nhận, stage phụ thuộc có thể phản ánh lỗi đó; ứng dụng cần chính sách rõ ràng nếu lỗi quan sát không được phép tác động đến kết quả trả ra. Không thêm xử lý mạng, dựng nhãn từ payload hoặc các tác vụ dễ lỗi vào callback này.

Khi dùng lại mẫu trên, cũng nhớ rằng sample bắt đầu **trước** `launch.get()`: thời gian đo bao gồm phần khởi chạy, chờ kết quả và khoảng đến lúc callback đọc đồng hồ. Nếu muốn đo riêng thời gian thực thi bên trong một tác vụ được xếp hàng, cần một điểm bắt đầu khác trong chính tác vụ đó.

## 8. Áp dụng trong Spring Boot Actuator

Các chương trình trên tự tạo `SimpleMeterRegistry` để kiểm chứng độc lập. Chúng không cung cấp HTTP endpoint. Trong ứng dụng Boot đã có Actuator, nhận `MeterRegistry` qua constructor của service hoặc thành phần đo, đăng ký các timer bằng registry đó, rồi giữ sample trong biến cục bộ của từng thao tác. Boot hỗ trợ cấu hình registry theo backend có trên classpath. [Metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Khi chuyển từ thí nghiệm sang ứng dụng:

- Dùng xử lý nghiệp vụ thật thay cho `MockClock` và các lệnh `clock.add`.
- Dùng registry do Boot quản lý thay cho việc tạo một registry riêng trong mỗi service.
- Không gọi `close()` trên registry được inject sau mỗi request; vòng đời registry thuộc ứng dụng.
- Giữ timer dùng chung và sample riêng cho mỗi lần gọi, kể cả khi service là singleton.
- Kiểm tra xem một lớp instrument khác đã đo cùng ranh giới chưa, để không ghi hai lần vào cùng một timer.

Nếu ứng dụng vốn có web server và cho phép đọc endpoint quản trị, cấu hình expose có thể là:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Sau khi đường xử lý thực tế đã đăng ký và ghi `app.lookup.duration`, có thể đọc:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/app.lookup.duration"
curl.exe "http://localhost:8080/actuator/metrics/app.lookup.duration?tag=outcome:error"
curl.exe "http://localhost:8080/actuator/metrics/app.lookup.duration?tag=outcome:cached"
```

Endpoint không lọc có thể cộng các chuỗi cùng tên; lọc `outcome` để xem một nhánh. Xem cả `measurements` và `availableTags`, không suy ra nhánh nào đã xảy ra chỉ từ việc timer được đăng ký trước.

Trong ứng dụng thực tế, thời lượng sẽ phụ thuộc xử lý thật và đơn vị được backend/endpoint dùng; không mong đợi các giá trị mô phỏng 1, 2, 7, 4 ms xuất hiện lại. Nếu module không có HTTP server, vẫn có thể đọc registry trực tiếp hoặc dùng backend đã cấu hình; không cần tạo API nghiệp vụ chỉ để thực hành `Timer.Sample`.

## 9. Xuất Prometheus và hiểu đơn vị của phép đo

`stop` trả nano giây, nhưng `Timer` chuyển thời gian sang đơn vị phù hợp khi xuất. Trong mã Java, dùng rõ `totalTime(TimeUnit.MILLISECONDS)` hoặc đơn vị mong muốn; đừng coi một số trả về là mili giây khi API quy định nano giây.

Trong ứng dụng Boot dùng Prometheus, có thể thêm registry và expose endpoint tương ứng:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Với quy ước tên thông thường, timer `app.lookup.duration` xuất các chuỗi như:

```text
app_lookup_duration_seconds_count{outcome="success"}
app_lookup_duration_seconds_sum{outcome="success"}
```

Đây là **mẫu tên chuỗi và nhãn**, không phải output scrape hoàn chỉnh có giá trị. Kiểm tra bản xuất thật để xác nhận tên, nhãn và các common tags của ứng dụng. [Micrometer Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

Thời gian trung bình của các lần hoàn tất trong một cửa sổ có thể tính theo cùng tập nhãn:

```promql
sum by (job, outcome) (rate(app_lookup_duration_seconds_sum[5m]))
/
sum by (job, outcome) (rate(app_lookup_duration_seconds_count[5m]))
```

Kết quả ở đây là giây. Nhân 1.000 nếu muốn biểu diễn mili giây. Cần đủ mẫu thu thập để tính tốc độ; cửa sổ không có lần ghi mới có thể tạo mẫu số 0, không phải bằng chứng mọi thao tác mất 0 giây.

Không thể suy p95 hoặc p99 chỉ từ count và tổng thời gian. Nếu cần phân vị, phải cấu hình histogram/percentile phù hợp trên timer hoặc qua cấu hình metrics của ứng dụng. Việc chọn `Timer.Sample` thay cho `record` không tự bật histogram. [Histograms và percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 10. Những thay đổi ranh giới làm thay đổi ý nghĩa số đo

### Đo toàn bộ thao tác hay từng lần thử?

Nếu thao tác có retry, một sample bao quanh cả vòng retry đo tổng thời gian đến kết quả cuối, gồm cả khoảng chờ giữa các lần thử. Một sample mới cho mỗi lần thử đo từng attempt. Cả hai có thể hữu ích, nhưng cần tên và cách phân loại riêng; không cộng chúng rồi gọi là tổng số yêu cầu của người dùng.

Một lần thử đầu lỗi nhưng lần sau thành công không nhất thiết làm timer toàn thao tác nhận `outcome=error`. Kết quả của phép đo ngoài phải phản ánh quy tắc kết quả cuối mà ta đã định nghĩa. Nếu trả một giá trị dự phòng sau lỗi, quyết định rõ nó thuộc `success` hay một giá trị như `fallback`, thay vì để biến kết quả ở giá trị mặc định vì quên gán.

### Có tính thời gian dọn tài nguyên không?

Nếu định nghĩa thao tác chỉ hoàn tất sau khi đóng tài nguyên, đặt điểm dừng sau phần dọn đó và bảo đảm lỗi trong lúc dọn vẫn đi qua nơi ghi nhận. Một lệnh dọn có thể ném ngoại lệ trước `sample.stop` trong cùng một `finally`, làm lệnh ghi không được chạy. Cấu trúc `try/finally` ngoài bao quanh toàn bộ phần làm việc và dọn tài nguyên giúp xác lập ranh giới rõ hơn.

Không tự thay đổi hợp đồng lỗi của phần dọn chỉ để làm biểu đồ đẹp. Điều cần thống nhất là “kết thúc thành công” có bao gồm dọn tài nguyên thành công hay không, và timer đang bao quanh phần nào.

### Chọn công cụ theo câu hỏi

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Đo một khối đồng bộ, biết timer đích từ đầu | `Timer.record` hoặc `recordCallable` thường gọn hơn |
| Chỉ biết kết quả/nhãn sau khi xử lý | `Timer.Sample` rồi chọn timer khi kết thúc |
| Đo đến lúc future hoàn tất | Sample đi cùng vòng đời future và callback kết thúc |
| Đếm/tính thời gian tác vụ còn đang chạy | Một `LongTaskTimer` hoặc phép đo tác vụ đang chạy được thiết kế riêng |
| Hiểu từng bước và mối quan hệ qua nhiều dịch vụ | Cần thông tin quan sát/tracing phù hợp; một sample không tự tạo chuỗi dấu vết |

Không phải cứ nhiều `return` là bắt buộc dùng sample. Nếu mọi nhánh đều ghi cùng một timer và không cần quyết định nhãn ở cuối, API bọc khối có thể dễ đọc hơn. Lợi ích chính của sample là tách thời điểm bắt đầu khỏi việc chọn nơi ghi khi kết quả đã rõ.

## 11. Chẩn đoán kết quả không như dự kiến

| Dấu hiệu | Nguyên nhân cần kiểm tra |
| --- | --- |
| Count ít hơn số thao tác đã kết thúc | Có nhánh không đi qua nơi dừng, callback chưa gắn, hoặc lỗi đồng bộ trước khi trả future bị bỏ sót |
| Count nhiều hơn số thao tác | Có hai chỗ cùng gọi stop, có lớp đo khác ghi cùng meter, hoặc đang đếm từng attempt nhưng so với số request |
| Thời gian bất đồng bộ rất ngắn | Sample bị dừng khi trả future, trước khi future nguồn hoàn tất |
| Nhánh lỗi được ghi là success | Gán nhãn thành công trước một lời gọi còn có thể ném ngoại lệ |
| Nhiều chuỗi metric tăng liên tục | Nhãn lấy từ đầu vào/message/error text không được giới hạn |
| Test thời gian chập chờn | Dùng thời gian thật và sleep để đòi kết quả tuyệt đối; nên điều khiển đồng hồ cho kiểm chứng logic |
| Dùng MockClock mà thời gian không khớp | Sample không dùng đồng hồ của registry đó, hoặc các thao tác đồng thời đang cùng làm thay đổi đồng hồ kiểm chứng |
| Không thấy tác vụ đang treo trong count | Timer thường chỉ ghi khi stop; cần nguồn quan sát tác vụ chưa hoàn tất |
| Có timer nhưng mọi count bằng 0 | Timer đã đăng ký sẵn nhưng đường xử lý chưa chạy hoặc sample chưa được dừng |
| Người gọi hủy nhưng timer vẫn chờ | Chỉ stage phụ thuộc bị hủy, còn future nguồn chưa kết thúc theo ranh giới đang đo |

`finally` là công cụ cho luồng thoát bình thường của Java, không phải cơ chế bảo đảm một bản ghi khi tiến trình bị dừng cưỡng bức hoặc JVM kết thúc đột ngột. Cũng không dùng sự khác nhau giữa số lần bắt đầu và hoàn tất làm bằng chứng lỗi ứng dụng nếu chưa xét tác vụ còn đang chạy.

## 12. Bài tập kiểm chứng

1. Gọi `lookup("cached")` ba lần trên một registry mới. Dự đoán timer `cached` có count = 3 và tổng thời gian mô phỏng = 6 ms; các timer khác vẫn có count = 0 vì đã được đăng ký trước.
2. Thêm một nhánh trả về sớm mới. Xác định kết quả hữu hạn của nhánh đó và kiểm tra chỉ có một bản ghi, không thêm `stop` trước `return`.
3. Làm nhánh tải dữ liệu ném ngoại lệ trước dòng gán `SUCCESS`. Xác minh ngoại lệ vẫn tới người gọi và count của `error` tăng, còn `success` không tăng vì lần gọi đó.
4. Dựa vào `DoubleStopDemo`, giải thích tại sao lần dừng thứ hai ghi 15 ms thay vì 5 ms. Sửa cách sử dụng bằng việc chỉ để lại một nơi dừng, không sửa thư viện để che thao tác ghi lặp.
5. Với ví dụ future, giữ một future nguồn chưa hoàn tất sau khi phương thức đã trả về. Kiểm tra chưa có bản ghi mới; sau đó hoàn tất nó và kiểm tra count tăng một lần.
6. Tạo một future đã hoàn tất trước khi gọi `observe`. Callback có thể chạy ngay khi gắn; vẫn phải có đúng một bản ghi với thời gian phản ánh ranh giới lúc gọi `observe`, không phải thời gian future từng chạy trước đó.
7. So sánh việc hủy future nguồn với hủy stage trả về từ `whenComplete`. Nêu rõ trường hợp nào được bộ đo trong ví dụ xem là kết thúc và vì sao việc hủy kết quả không tự chứng minh tác vụ thật đã dừng.

Một phép đo dùng được cần có **một sample cho một thao tác, một ranh giới kết thúc được định nghĩa rõ, một nơi quyết định kết quả cuối và một lần ghi cho ranh giới đó**. Khi các điều này nhất quán, số lần và thời gian theo từng nhánh mới có ý nghĩa để phân tích.
