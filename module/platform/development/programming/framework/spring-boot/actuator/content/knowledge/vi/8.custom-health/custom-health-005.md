# Thiết kế kiểm tra phụ thuộc ngoài với timeout và chi phí có giới hạn

## 1. Một phép kiểm tra sức khỏe cũng tiêu thụ tài nguyên

Khi `HealthIndicator` gọi cơ sở dữ liệu, Redis hoặc một dịch vụ HTTP, nó trở thành một luồng công việc thật: cần luồng xử lý, kết nối, thời gian chờ và tài nguyên của hệ thống được kiểm tra.

Nếu phụ thuộc ngoài đang chậm, một phép kiểm tra thiếu giới hạn có thể giữ nhiều luồng của chính ứng dụng. Nếu nhiều bộ giám sát cùng gọi, các phép kiểm tra còn có thể dồn tải lên dịch vụ vốn đã gặp sự cố.

Vì vậy, thiết kế cần trả lời đồng thời:

- **Đang kiểm tra khả năng nào?** Kết nối được chưa chắc đã thực hiện được thao tác nghiệp vụ cần thiết.
- **Được dùng bao nhiêu thời gian?** Bao gồm các lớp chờ trước và trong lúc gửi yêu cầu.
- **Được dùng bao nhiêu tài nguyên?** Số lần gọi, số tác vụ đang chạy, hàng đợi, kết nối và kích thước dữ liệu.
- **Kết quả còn mới đến khi nào?** Một mẫu `UP` cũ không thể được giữ vô hạn.
- **Khi kiểm tra bị treo thì điều gì còn tiếp tục tăng?** Thiết kế tốt phải có câu trả lời cụ thể.

Bài dùng **Spring Boot 3.3.0 và JDK 21** cho ví dụ Java. Các con số thời gian là cấu hình minh họa; ngân sách thực tế phải dựa vào yêu cầu vận hành và phép đo của ứng dụng.

### 1.1. Từ “gọi thử một API” đến một hợp đồng kiểm tra

Một hợp đồng có thể được mô tả như sau:

```text
Phụ thuộc: catalog
Khả năng cần xác nhận: endpoint sẵn sàng của dịch vụ phản hồi HTTP 204
Một lần kiểm tra: một yêu cầu HEAD do mã ứng dụng phát ra
Không có vòng thử lại ở lớp kiểm tra
Tần suất: chờ 2 giây sau khi lần trước kết thúc
Ngân sách đánh giá một lần: 500 ms
Tuổi tối đa của mẫu đã hoàn tất: 6 giây
Số lần kiểm tra đang chạy ở lớp ứng dụng: tối đa 1 cho indicator này
```

Hợp đồng này chỉ xác nhận tín hiệu do endpoint ấy cam kết. Nó không chứng minh mọi giao dịch của catalog đều thành công. Nếu quyền đọc, quyền ghi hoặc một dữ liệu bắt buộc là điều kiện phục vụ, cần quyết định phép kiểm tra nhẹ nào thực sự đại diện cho điều kiện đó.

Các phép kiểm tra nên tránh tác dụng phụ: không tạo đơn hàng, gửi thư, thực hiện thanh toán hoặc thay đổi dữ liệu nghiệp vụ chỉ để xác định sức khỏe.

## 2. Tách các loại giới hạn thời gian

### 2.1. Timeout kết nối không bao quát toàn bộ công việc

Một lần gọi có thể đi qua nhiều bước:

```text
Chờ tài nguyên/kết nối
    -> phân giải tên
    -> thiết lập kết nối và bảo mật
    -> gửi yêu cầu
    -> chờ phản hồi
    -> xử lý phần thân
    -> trả kết nối và dọn tài nguyên
```

Các bước có thể có cơ chế chờ riêng. Cần đọc hợp đồng của client để biết mỗi timeout bao phủ bước nào, có áp dụng khi tái sử dụng kết nối không và có tính cả việc đọc phần thân hay không.

Với `HttpClient` của JDK, `connectTimeout` áp dụng khi cần thiết lập kết nối mới; khi dùng lại kết nối, giới hạn này không có tác dụng cho bước đó. [API HttpClient.Builder của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html#connectTimeout(java.time.Duration))

Không lấy một giá trị `connectTimeout=150ms` rồi kết luận toàn bộ phép kiểm tra luôn xong trong `150ms`.

### 2.2. Phân biệt timeout từng bước và hạn chót chung

**Thời gian chờ tối đa (timeout)** có thể được đặt cho một bước. **Hạn chót (deadline)** biểu diễn lúc toàn bộ công việc không còn được phép tiếp tục chờ theo hợp đồng của bên gọi.

Ví dụ, nếu người giám sát chỉ chờ `1 giây`, một thiết kế đồng bộ có thể dành một phần ngân sách cho phép kiểm tra ngoài và giữ phần còn lại cho các contributor khác, tổng hợp, tuần tự hóa phản hồi và truyền qua mạng.

Nếu có ba phụ thuộc được kiểm tra nối tiếp, tổng thời gian có thể cộng dồn. Nếu kiểm tra song song, thời gian chờ có thể giảm nhưng số kết nối và công việc đồng thời tăng. Cần giới hạn cả hai chiều, thay vì chỉ tối ưu một số đo.

Các loại thời gian thường cần xác minh:

| Loại | Câu hỏi cần trả lời |
| --- | --- |
| Chờ kết nối từ bể kết nối (connection pool) | Có thể bị giữ bao lâu trước khi thật sự gửi yêu cầu? |
| Kết nối/TLS | Kết nối mới bị lỗi hoặc không phản hồi thì chờ bao lâu? |
| Yêu cầu/đọc phản hồi | Client kết thúc chờ theo điều kiện nào? |
| Đọc phần thân | Có giới hạn toàn bộ thời gian, kích thước và tốc độ nhận dữ liệu không? |
| Thử lại và chờ giữa các lần | Mọi lần có dùng chung một ngân sách hay mỗi lần bắt đầu lại? |
| Hàng đợi thực thi | Công việc chờ luồng có nằm trong thời gian được đo không? |

Một timeout đọc theo khoảng thời gian không nhận dữ liệu có thể vẫn cho phép một luồng dữ liệu nhỏ giọt kéo dài. Vì vậy phải xác minh thêm giới hạn cho toàn bộ thao tác khi đọc nội dung phản hồi.

### 2.3. Ngưỡng ghi cảnh báo của Actuator không phải bộ cưỡng bức timeout

Spring Boot có cấu hình:

```properties
management.endpoint.health.logging.slow-indicator-threshold=1s
```

Đây là ngưỡng **ghi cảnh báo về indicator chạy chậm**. Nó không tự ngắt một socket, hủy câu lệnh SQL hay buộc `health()` trả về sau một giây. Tài liệu nhánh 3.3 mô tả ngưỡng mặc định `10 giây` và cách thay đổi ngưỡng ghi log. [Slow health indicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

Timeout cần được thiết kế trong client và mô hình thực thi của phép kiểm tra, độc lập với ngưỡng quan sát này.

### 2.4. Ngừng chờ khác với dừng được công việc

Đặt thời gian chờ khi gọi `Future.get` không tự bảo đảm công việc nền đã dừng. Tương tự, một future hoàn tất với lỗi timeout chưa chứng minh kết nối phía dưới đã được giải phóng.

Việc hủy còn phụ thuộc client. Với `HttpClient` của JDK, khi một thao tác bị ngắt, client cố hủy trao đổi HTTP nhưng không bảo đảm thời điểm yêu cầu hủy có hiệu lực; máy chủ vẫn có thể đã nhận yêu cầu và tài nguyên có thể được thu hồi bất đồng bộ. [Hợp đồng hủy của HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html#send(java.net.http.HttpRequest,java.net.http.HttpResponse.BodyHandler))

Một lỗi thiết kế phổ biến là: mỗi lần chờ hết hạn lại tạo một tác vụ mới, trong khi các tác vụ cũ vẫn còn sống. Khi phụ thuộc bị treo, chi phí sẽ tăng theo số lần kiểm tra.

## 3. Giới hạn chi phí, không chỉ độ trễ của một lần gọi

### 3.1. Ước lượng tổng tải do giám sát

Giả sử:

- `N` tiến trình ứng dụng.
- `M` nguồn giám sát độc lập.
- Mỗi nguồn gọi một lần sau mỗi `P` giây.
- Mỗi lần health kích hoạt một lần kiểm tra cùng một phụ thuộc.

Tốc độ gọi gần đúng ở lớp ứng dụng:

```text
R = N × M / P
```

Với `200` tiến trình, `3` nguồn giám sát và chu kỳ `5 giây`:

```text
R = 200 × 3 / 5 = 120 lần kiểm tra/giây
```

Nếu mỗi phép kiểm tra tự thử lại tối đa ba lần, trường hợp lỗi có thể tạo đến `360` lần thử mỗi giây ở lớp đó, chưa tính client hoặc proxy tự thử lại.

Công thức này cần điều chỉnh nếu có thêm truy vấn trực tiếp vào từng thành phần hoặc nhiều phép kiểm tra bên trong một contributor. Đừng chỉ nhìn tần suất của một dashboard.

### 3.2. Giữ phép kiểm tra nhỏ và có ý nghĩa

| Phụ thuộc | Một hướng kiểm tra nhẹ | Điều cần tránh |
| --- | --- | --- |
| HTTP | Endpoint kiểm tra có hợp đồng rõ, phản hồi nhỏ | Tải trang lớn hoặc gọi chuỗi nghiệp vụ nhiều bước |
| JDBC | Kiểm tra tính hợp lệ của kết nối hoặc thao tác nhỏ đúng mục tiêu | Quét bảng lớn, khóa dữ liệu, truy vấn thống kê nặng |
| Redis | Lệnh nhẹ xác nhận khả năng cần dùng | Đọc toàn bộ tập khóa hoặc giá trị lớn |
| Dịch vụ ngoài có hạn mức | Tần suất đã được thống nhất | Để mọi lần mở màn hình giám sát tiêu thụ một lần gọi mới |

`HEAD` hữu ích khi endpoint hỗ trợ và có hợp đồng phù hợp: phía client không cần tải phần thân. Tuy nhiên, máy chủ có thể vẫn thực hiện công việc để xử lý `HEAD`. Không suy ra “không có body” đồng nghĩa “không tốn chi phí ở máy chủ”.

Không tự động chuyển từ một phép kiểm tra nhẹ thất bại sang một phép kiểm tra nặng hơn nếu sự chuyển đổi đó không nằm trong ngân sách đã thiết kế.

### 3.3. Ba lựa chọn thực thi

| Cách | Lợi ích | Giá phải trả |
| --- | --- | --- |
| Gọi trực tiếp trong `health()` | Quan sát tại thời điểm yêu cầu | Đường trả health phụ thuộc độ trễ bên ngoài; số lần gọi tăng theo người đọc |
| Dùng bộ nhớ đệm, làm mới khi cần | Giảm lời gọi khi ít người đọc | Cần kiểm soát làm mới đồng thời, số người chờ và tuổi mẫu |
| Lấy mẫu định kỳ ở luồng riêng | Tách đường đọc health khỏi I/O; nhiều người đọc dùng chung mẫu | Vẫn gọi định kỳ dù không ai đọc; kết quả có độ trễ và cần chính sách quá hạn |

Không có một lựa chọn tốt cho mọi ứng dụng. Với phép kiểm tra rẻ, client có giới hạn đáng tin và ít người gọi, cách đồng bộ có thể đủ. Khi nhiều nơi đọc hoặc client có khả năng mắc kẹt, mô hình lấy mẫu giúp kiểm soát ảnh hưởng rõ hơn.

Phần tiếp theo triển khai lựa chọn thứ ba để làm rõ các giới hạn.

## 4. Mô hình lấy mẫu với một tác vụ định kỳ

```text
Luồng lấy mẫu riêng
    -> thực hiện một phép kiểm tra
    -> ghi đè mẫu gần nhất
    -> chờ một khoảng sau khi lần đó kết thúc
    -> thực hiện lần kế tiếp

Mọi lần gọi health()
    -> đọc mẫu gần nhất
    -> kiểm tra tuổi mẫu
    -> trả Health
```

### 4.1. Những điều mô hình bảo đảm trong phạm vi lớp mẫu

- `health()` không gọi mạng, không chờ future và không nộp thêm tác vụ.
- Chỉ một tác vụ định kỳ được đăng ký cho mỗi đối tượng.
- Tác vụ sau đợi tác vụ trước kết thúc rồi mới tính khoảng chờ.
- Mẫu mới ghi đè mẫu cũ; không tích lũy lịch sử trong bộ nhớ.
- Nếu chưa có mẫu hoặc mẫu quá hạn, trả `DOWN` theo chính sách của ví dụ.
- Nếu một phép kiểm tra mắc kẹt, lớp này không sinh thêm luồng thay thế hoặc xếp thêm một lần kiểm tra cho mỗi lượt đọc health.

`scheduleWithFixedDelay` tính khoảng chờ từ lúc một lần chạy kết thúc đến lúc lần tiếp theo bắt đầu. Một ngoại lệ thoát khỏi tác vụ định kỳ có thể làm các lần sau bị ngừng; mã mẫu xử lý các ngoại lệ kiểm tra thông thường bên trong tác vụ. [ScheduledExecutorService của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html#scheduleWithFixedDelay(java.lang.Runnable,long,long,java.util.concurrent.TimeUnit))

Bể thực thi trong mã được giữ riêng và chỉ có một nhiệm vụ định kỳ. Nó không phải một hàng đợi công việc mở cho mọi người gọi.

### 4.2. Giới hạn về tần suất và độ mới

Với khoảng chờ `D` sau mỗi lần chạy và thời gian chạy thực tế `T`, một tiến trình thực hiện xấp xỉ:

```text
1 / (D + T) lần kiểm tra/giây
```

Tốc độ này không tăng chỉ vì có thêm nguồn đọc health. Đây là số lần gọi `Probe.check()` ở lớp ứng dụng, không phải lời khẳng định về mọi trao đổi mạng nội bộ của client.

Đổi lại, trạng thái đọc được là một mẫu đã hoàn tất. Nếu mẫu mới nhất còn trong giới hạn tuổi, ví dụ có thể tiếp tục trả `UP` trong cửa sổ đó dù một lần kiểm tra mới đang chậm. Sau giới hạn tuổi, mẫu cũ không còn được coi là bằng chứng sức khỏe hiện tại.

### 4.3. Ngân sách đánh giá không cưỡng bức dừng luồng

**Trong mã dưới đây, `budget` được dùng để loại kết quả hoàn tất quá muộn. Nó không phải một timer ngắt `Probe.check()` đang treo.**

Nếu một phép kiểm tra trả `true` nhưng đã dùng quá ngân sách, mẫu được ghi là `DOWN/PROBE_BUDGET_EXCEEDED`. Nếu nó không trả về, đường đọc health vẫn dựa trên mẫu cũ và cuối cùng báo mẫu quá hạn.

Các giới hạn I/O thật vẫn phải đặt trong client. Cách ly việc đọc health không thay thế việc cấu hình client đúng.

## 5. Ví dụ Java hoàn chỉnh, không cần phụ thuộc ngoài

Ví dụ dùng một phép kiểm tra giả lập để kết quả có thể lặp lại, kể cả tình huống không hợp tác khi nhận yêu cầu ngắt. Nó không gửi yêu cầu đến dịch vụ thật.

### 5.1. Tệp và phụ thuộc

```text
bounded-health-demo/
├── pom.xml
└── src/main/java/example/health/BoundedProbeDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>bounded-health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
```

`src/main/java/example/health/BoundedProbeDemo.java`:

```java
package example.health;

import java.io.IOException;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.LongSupplier;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;

public class BoundedProbeDemo {
    @FunctionalInterface
    public interface Probe {
        boolean check() throws Exception;
    }

    public static final class SampledIndicator
            implements HealthIndicator, AutoCloseable {
        private record Sample(Health health, long completedAtNanos) {}

        private final String dependency;
        private final Probe probe;
        private final LongSupplier nanoTime;
        private final long delayNanos;
        private final long budgetNanos;
        private final long maxAgeNanos;
        private final AtomicReference<Sample> latest = new AtomicReference<>();
        private final AtomicBoolean closed = new AtomicBoolean();
        private final ScheduledThreadPoolExecutor scheduler;
        private boolean started;
        private ScheduledFuture<?> scheduled;

        public SampledIndicator(String dependency, Probe probe, Duration delay,
                Duration budget, Duration maxAge) {
            this(dependency, probe, delay, budget, maxAge, System::nanoTime);
        }

        private SampledIndicator(String dependency, Probe probe, Duration delay,
                Duration budget, Duration maxAge, LongSupplier nanoTime) {
            this.dependency = Objects.requireNonNull(dependency);
            this.probe = Objects.requireNonNull(probe);
            this.nanoTime = Objects.requireNonNull(nanoTime);
            this.delayNanos = positiveNanos(delay);
            this.budgetNanos = positiveNanos(budget);
            this.maxAgeNanos = positiveNanos(maxAge);
            if (maxAgeNanos <= Math.addExact(delayNanos, budgetNanos)) {
                throw new IllegalArgumentException("maxAge must exceed delay + budget");
            }
            this.scheduler = new ScheduledThreadPoolExecutor(1, task -> {
                Thread thread = new Thread(task, "health-sample-" + dependency);
                thread.setDaemon(true);
                return thread;
            });
            scheduler.setRemoveOnCancelPolicy(true);
        }

        private static long positiveNanos(Duration value) {
            long nanos = Objects.requireNonNull(value).toNanos();
            if (nanos <= 0) {
                throw new IllegalArgumentException("duration must be positive");
            }
            return nanos;
        }

        public synchronized void start() {
            if (closed.get()) {
                throw new IllegalStateException("indicator is closed");
            }
            if (!started) {
                scheduled = scheduler.scheduleWithFixedDelay(
                        this::refresh, 0, delayNanos, TimeUnit.NANOSECONDS);
                started = true;
            }
        }

        private Health result(Status status, String reason) {
            return Health.status(status)
                    .withDetail("dependency", dependency)
                    .withDetail("reason", reason).build();
        }

        private void refresh() {
            long began = nanoTime.getAsLong();
            Health value;
            try {
                value = probe.check()
                        ? result(Status.UP, "OK")
                        : result(Status.DOWN, "DEPENDENCY_REJECTED");
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                value = result(Status.DOWN, "INTERRUPTED");
            }
            catch (Exception ex) {
                value = result(Status.DOWN, "PROBE_FAILED");
            }

            long completed = nanoTime.getAsLong();
            if (completed - began > budgetNanos) {
                value = result(Status.DOWN, "PROBE_BUDGET_EXCEEDED");
            }
            if (!closed.get()) {
                latest.set(new Sample(value, completed));
            }
        }

        @Override
        public Health health() {
            if (closed.get()) {
                return result(Status.DOWN, "STOPPED");
            }
            Sample sample = latest.get();
            if (sample == null) {
                return result(Status.DOWN, "NO_SAMPLE");
            }
            long age = Math.max(0, nanoTime.getAsLong() - sample.completedAtNanos());
            if (age > maxAgeNanos) {
                return Health.down()
                        .withDetail("dependency", dependency)
                        .withDetail("reason", "STALE_SAMPLE")
                        .withDetail("lastStatus", sample.health().getStatus().getCode())
                        .withDetail("sampleAgeMs",
                                TimeUnit.NANOSECONDS.toMillis(age)).build();
            }
            return Health.status(sample.health().getStatus())
                    .withDetails(sample.health().getDetails())
                    .withDetail("sampleAgeMs",
                            TimeUnit.NANOSECONDS.toMillis(age)).build();
        }

        @Override
        public synchronized void close() {
            if (closed.compareAndSet(false, true)) {
                if (scheduled != null) {
                    scheduled.cancel(true);
                }
                scheduler.shutdownNow();
            }
        }
    }

    private enum Mode { OK, REJECTED, ERROR, LATE }

    private static void print(String label, Health health) {
        System.out.println(label + "=" + health.getStatus().getCode()
                + "/" + health.getDetails().get("reason"));
    }

    public static void main(String[] args) throws Exception {
        AtomicLong clock = new AtomicLong();
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Mode> mode = new AtomicReference<>(Mode.OK);
        Probe probe = () -> {
            calls.incrementAndGet();
            return switch (mode.get()) {
                case OK -> true;
                case REJECTED -> false;
                case ERROR -> throw new IOException("simulated I/O error");
                case LATE -> {
                    clock.addAndGet(Duration.ofMillis(300).toNanos());
                    yield true;
                }
            };
        };

        SampledIndicator indicator = new SampledIndicator(
                "catalog", probe, Duration.ofSeconds(1),
                Duration.ofMillis(200), Duration.ofSeconds(3), clock::get);
        try {
            print("initial", indicator.health());
            indicator.refresh();
            print("fresh", indicator.health());
            for (int index = 0; index < 10_000; index++) {
                indicator.health();
            }
            System.out.println("probe-calls-after-10000-reads=" + calls.get());
            clock.addAndGet(Duration.ofSeconds(4).toNanos());
            print("expired", indicator.health());
            mode.set(Mode.REJECTED);
            indicator.refresh();
            print("rejected", indicator.health());
            mode.set(Mode.ERROR);
            indicator.refresh();
            print("exception", indicator.health());
            mode.set(Mode.LATE);
            indicator.refresh();
            print("late", indicator.health());
            mode.set(Mode.OK);
            indicator.refresh();
            print("recovered", indicator.health());
        }
        finally {
            indicator.close();
        }
        print("closed", indicator.health());

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumActive = new AtomicInteger();
        Probe blockedProbe = () -> {
            attempts.incrementAndGet();
            int current = active.incrementAndGet();
            maximumActive.accumulateAndGet(current, Math::max);
            entered.countDown();
            try {
                boolean released = false;
                while (!released) {
                    try {
                        release.await();
                        released = true;
                    }
                    catch (InterruptedException ignored) {
                        // Deliberately simulate a client that ignores cancellation.
                    }
                }
                return true;
            }
            finally {
                active.decrementAndGet();
                exited.countDown();
            }
        };

        SampledIndicator blocked = new SampledIndicator(
                "catalog", blockedProbe, Duration.ofMillis(10),
                Duration.ofMillis(200), Duration.ofSeconds(3));
        try {
            blocked.start();
            if (!entered.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not enter probe");
            }
            blocked.start();
            for (int index = 0; index < 10_000; index++) {
                blocked.health();
            }
            print("while-blocked", blocked.health());
            System.out.println("blocked-attempts=" + attempts.get());
            System.out.println("max-concurrent-probes=" + maximumActive.get());
            blocked.close();
            print("closed-while-blocked", blocked.health());
        }
        finally {
            blocked.close();
            release.countDown();
            if (!exited.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("demo worker did not exit");
            }
        }
    }
}
```

### 5.2. Biên dịch và chạy

Tại thư mục chứa `pom.xml`, với Maven và JDK 21, chạy trong PowerShell:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$boundedProbeClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $boundedProbeClasspath -d out src/main/java/example/health/BoundedProbeDemo.java
java -cp "$boundedProbeClasspath;out" example.health.BoundedProbeDemo
```

Trên Linux/macOS, dùng dấu `:` phân cách classpath và cú pháp shell tương ứng.

Các dòng stdout của chương trình:

```text
initial=DOWN/NO_SAMPLE
fresh=UP/OK
probe-calls-after-10000-reads=1
expired=DOWN/STALE_SAMPLE
rejected=DOWN/DEPENDENCY_REJECTED
exception=DOWN/PROBE_FAILED
late=DOWN/PROBE_BUDGET_EXCEEDED
recovered=UP/OK
closed=DOWN/STOPPED
while-blocked=DOWN/NO_SAMPLE
blocked-attempts=1
max-concurrent-probes=1
closed-while-blocked=DOWN/STOPPED
```

Các log môi trường hoặc thư viện, nếu có, không thuộc các dòng kết quả trên.

### 5.3. Các tình huống đã đối chiếu

| Kết quả | Điều được kiểm chứng |
| --- | --- |
| `initial=DOWN/NO_SAMPLE` | Chưa có mẫu không được ngầm xem là khỏe |
| `fresh=UP/OK` | Mẫu mới thành công được dùng |
| `probe-calls-after-10000-reads=1` | Đọc health nhiều lần không gọi lại phụ thuộc |
| `expired=DOWN/STALE_SAMPLE` | Mẫu thành công cũ không được giữ xanh vô hạn |
| `rejected=DOWN/DEPENDENCY_REJECTED` | Phụ thuộc trả kết quả không đạt hợp đồng |
| `exception=DOWN/PROBE_FAILED` | Ngoại lệ thông thường được chuyển thành kết quả health |
| `late=DOWN/PROBE_BUDGET_EXCEEDED` | Thành công trả quá muộn không được nhận là `UP` |
| `recovered=UP/OK` | Mẫu thành công mới có thể thay kết quả lỗi |
| `blocked-attempts=1` | Người đọc không làm sinh thêm lần thử khi phép kiểm tra đang mắc kẹt |
| `max-concurrent-probes=1` | Chỉ một lần kiểm tra ở lớp mẫu đang chạy |
| `closed-while-blocked=DOWN/STOPPED` | Dừng indicator không chờ client giả lập chấp nhận ngắt |

Phần kiểm tra tuổi mẫu và kết quả trả muộn dùng đồng hồ giả lập, không dùng việc ngủ rồi đo một số mili giây dễ dao động. Khi chạy thật, constructor công khai dùng `System.nanoTime` để đo khoảng thời gian.

Phương thức `refresh()` là chi tiết nội bộ. `main` gọi nó trực tiếp trong phần thử chính sách vì cùng nằm trong lớp bao ngoài; đường sử dụng thông thường là gọi `start()` một lần và để lịch định kỳ thực thi.

### 5.4. Đọc đúng các giới hạn của mã

`maxAge` được kiểm tra lớn hơn `delay + budget` để tránh một cấu hình hiển nhiên không chừa đủ thời gian giữa các mẫu theo ngân sách dự kiến. Khi vận hành còn cần phần dự phòng cho biến động lịch thực thi, client và tải hệ thống.

Mẫu được tính tuổi từ lúc phép kiểm tra hoàn tất. Kết quả quá ngân sách bị ghi là lỗi; tuổi mới không biến một phép kiểm tra chậm thành thành công.

`close()` hủy lịch và yêu cầu ngắt luồng, nhưng không chờ vô hạn bằng `awaitTermination`. Luồng daemon giúp nó không tự giữ JVM sống khi tiến trình kết thúc; daemon không có nghĩa là socket hay công việc bên ngoài đã bị hủy.

Trong phép thử mắc kẹt, client giả lập cố ý bỏ qua ngắt. Chương trình chỉ giải phóng nó ở phần dọn dẹp của phép thử. Không đưa hành vi bỏ qua ngắt đó vào client sản xuất.

## 6. Gắn client HTTP có timeout vào một ứng dụng Spring Boot

Sau khi có kiểu `SampledIndicator` ở mục 5, cấu hình sau minh họa cách đăng ký nó với một phép kiểm tra HTTP thật trong ứng dụng đã có Actuator.

Lưu `CatalogHealthConfiguration.java` trong package `example.health`:

```java
package example.health;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import example.health.BoundedProbeDemo.SampledIndicator;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogHealthConfiguration {
    @Bean(name = "catalogProbeClient", destroyMethod = "shutdownNow")
    public HttpClient catalogProbeClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(150))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Bean(destroyMethod = "close")
    public SampledIndicator catalogHealthIndicator(
            @Qualifier("catalogProbeClient") HttpClient client,
            @Value("${demo.health.catalog.url}") URI target) {
        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(Duration.ofMillis(400))
                .method("HEAD", HttpRequest.BodyPublishers.noBody())
                .build();
        SampledIndicator indicator = new SampledIndicator(
                "catalog",
                () -> client.send(request,
                        HttpResponse.BodyHandlers.discarding()).statusCode() == 204,
                Duration.ofSeconds(2), Duration.ofMillis(500),
                Duration.ofSeconds(6));
        indicator.start();
        return indicator;
    }
}
```

Trong mã minh họa, kiểu được nhập từ lớp bao ngoài để dùng ngay với tệp ở mục 5. Khi tổ chức mã ứng dụng, có thể tách `Probe` và `SampledIndicator` thành lớp riêng và điều chỉnh import tương ứng.

Cấu hình địa chỉ đích:

```properties
demo.health.catalog.url=${CATALOG_HEALTH_URL}
```

Biến môi trường `CATALOG_HEALTH_URL` phải trỏ đến endpoint được ứng dụng quản lý cấu hình và được phép gọi. Không lấy URL kiểm tra từ tham số của người gọi health.

### 6.1. Hợp đồng của yêu cầu HTTP

Ví dụ mong endpoint:

- Hỗ trợ `HEAD`.
- Trả `204` khi điều kiện cần kiểm tra đạt yêu cầu.
- Không thực hiện một công việc nặng hoặc gây tác dụng phụ cho mỗi lần gọi.

`200`, `301`, `401`, `405`, `429` hoặc `503` đều không khớp hợp đồng `204` của ví dụ. Điều đó không có nghĩa mọi dịch vụ đều phải dùng `204`; cần thay chính sách cho đúng hợp đồng thật.

`followRedirects(NEVER)` tránh tự đi theo chuỗi chuyển hướng. Mã không có vòng thử lại ở lớp phép kiểm tra. Vẫn phải xác minh hành vi thử lại nội bộ của client, proxy và hạ tầng nếu cần giới hạn số lần trao đổi mạng.

`BodyHandlers.discarding()` tránh tích lũy nội dung phản hồi thành một chuỗi lớn. Nó không phải bộ giới hạn số byte tải về cho một yêu cầu `GET` tùy ý. Trong mẫu này `HEAD` là phần của hợp đồng để không cần nhận body; nếu chuyển sang `GET`, phải thiết kế lại giới hạn đọc và kích thước phản hồi.

### 6.2. Các giá trị thời gian có vai trò khác nhau

| Giá trị trong cấu hình Java | Vai trò |
| --- | --- |
| `150ms` ở `connectTimeout` | Giới hạn thiết lập kết nối mới theo hợp đồng client |
| `400ms` ở request `timeout` | Timeout của yêu cầu theo API JDK |
| `500ms` ở `SampledIndicator` | Kết quả hoàn tất quá mức này bị đánh dấu quá ngân sách |
| `2s` delay | Khoảng chờ sau khi một lần kiểm tra kết thúc |
| `6s` maxAge | Tuổi tối đa của mẫu được xem là còn dùng được |

`HttpRequest.Builder.timeout` quy định timeout của request và báo `HttpTimeoutException` khi không nhận phản hồi trong giới hạn theo hợp đồng API. Không đặt timeout tương đương với không giới hạn tại lớp đó. [HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration))

Không cộng `150 + 400` hoặc chọn số lớn nhất rồi xem đó là bằng chứng thời gian tổng tuyệt đối: phạm vi các bộ đếm có thể chồng lấp, và những bước xử lý khác phải được kiểm chứng trên client/JDK thực tế.

Ngân sách `500ms` không ngắt một lần gọi mạng bị treo. Nó chỉ từ chối công nhận kết quả trả muộn; đường đọc health được bảo vệ nhờ tách I/O khỏi `health()` và kiểm tra tuổi mẫu.

### 6.3. Tái sử dụng client và dừng có chủ đích

Client là một bean dùng chung cho indicator, thay vì tạo mới cho từng lượt đọc health. Việc dùng lại client cho phép dùng lại tài nguyên kết nối.

Cấu hình chỉ rõ `destroyMethod="shutdownNow"` cho `HttpClient` của JDK 21. Phương thức này yêu cầu dừng theo khả năng tốt nhất của client; nó không bảo đảm mọi hoạt động đang chạy đã kết thúc. `HttpClient.close()` có hợp đồng đợi hoàn tất các hoạt động, nên không thể mặc định coi nó là thao tác dọn dẹp luôn trả ngay. [Vòng đời HttpClient của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html#shutdownNow())

Luồng định kỳ và client là hai lớp tài nguyên khác nhau. Giới hạn một phép kiểm tra ở lớp ứng dụng không tự chứng minh mọi luồng nội bộ, kết nối hoặc bộ đệm của thư viện đều đã có cùng giới hạn; cần kiểm tra và cấu hình những tài nguyên đó riêng.

## 7. Những quyết định cần bổ sung khi dùng thực tế

### 7.1. Tuổi mẫu, chính sách ban đầu và trạng thái phục hồi

Ví dụ chọn `DOWN` cho chưa có mẫu, mẫu quá cũ và đã dừng. Lựa chọn này phù hợp với một tín hiệu cần bằng chứng mới trước khi coi là sẵn sàng.

Không thay thành `UNKNOWN` chỉ để mã HTTP dễ nhìn hơn: theo ánh xạ mặc định, `UNKNOWN` có thể vẫn nhận HTTP `200`. Nếu chọn trạng thái khác, phải xác định cả cách tổng hợp và mã HTTP mà hệ thống giám sát sẽ dùng.

Cũng không trả lại một mẫu `UP` đã quá hạn mà chỉ thêm `stale=true` trong details. Nhiều người tiêu thụ health chỉ nhìn trạng thái hoặc mã HTTP, không đọc cờ chi tiết.

Nếu ứng dụng có cơ chế phục vụ thay thế khi phụ thuộc hỏng, có thể cần một trạng thái hoặc nhóm giám sát khác. Quyết định phải dựa trên khả năng phục vụ thật, không chỉ trên việc client đã kết nối được hay chưa.

### 7.2. Liveness và readiness có mục tiêu khác nhau

Phụ thuộc ngoài bị lỗi không nhất thiết chứng minh tiến trình ứng dụng cần bị khởi động lại. Đưa mọi dịch vụ ngoài vào liveness có thể tạo nhiều lần khởi động lại trong lúc sự cố chung chưa được xử lý.

Readiness có thể cần xét phụ thuộc thật sự bắt buộc để nhận lưu lượng, nhưng việc đưa nó vào hay giữ nó ngoài nhóm phải được quyết định theo hợp đồng phục vụ và khả năng dự phòng của ứng dụng. [Hướng dẫn kiểm tra trạng thái ngoài với Kubernetes probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

Indicator ở bài này chỉ cung cấp tín hiệu; việc chọn nhóm không được tự suy ra từ tên `catalog`.

### 7.3. JDBC cần nhiều giới hạn độc lập

Với cơ sở dữ liệu, phải xét ít nhất:

- Thời gian lấy kết nối từ bể kết nối.
- Thời gian xác minh kết nối hoặc chạy câu lệnh kiểm tra.
- Thời gian chờ mạng theo driver.
- Đóng/trả tài nguyên và ảnh hưởng đến công việc nghiệp vụ.

`Connection.isValid(timeout)` xác minh tính hợp lệ của kết nối theo cơ chế driver. Nó không bao gồm việc lấy được kết nối từ bể trước đó.

`setNetworkTimeout` và timeout truy vấn là các cơ chế riêng, với tác động riêng lên kết nối khi quá hạn. Driver có thể có nhiều lượt trao đổi bên trong một API; phải kiểm chứng phạm vi giới hạn thực tế. [API JDBC Connection của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html#isValid(int))

Tránh giữ kết nối health lâu đến mức chiếm hết tài nguyên cho nghiệp vụ. Tạo thêm một bể kết nối riêng cũng có chi phí; chỉ làm khi thiết kế đã tính số kết nối tăng thêm và giới hạn truy cập ở phía cơ sở dữ liệu.

### 7.4. Kiểm soát thử lại, hàng đợi và số lượng indicator

Health thường được gọi lặp lại tự nhiên. Nhiều lần thử lại ngay trong mỗi lượt có thể khuếch đại tải đúng lúc phụ thuộc đang lỗi.

Ví dụ ba lần thử, mỗi lần chờ `400ms` và hai khoảng chờ `100ms`:

```text
3 × 400ms + 2 × 100ms = 1400ms
```

Con số đã vượt `1 giây` dù mỗi timeout riêng có vẻ nhỏ. Nếu cần thử lại, mọi lần phải nằm trong cùng ngân sách đã phân bổ và có giới hạn rõ về số lần, khoảng chờ và tài nguyên.

Mã mẫu có một luồng định kỳ cho mỗi indicator. Nếu tạo hàng trăm indicator kiểu này, tổng số luồng cũng tăng. Khi cần dùng bộ lập lịch chung, phải thiết kế lại giới hạn đồng thời và cách cô lập phụ thuộc chậm; không đơn giản đổi sang một hàng đợi chung không giới hạn.

Luồng ảo có thể giảm chi phí của một số kiểu chờ, nhưng không tự giới hạn số kết nối, số yêu cầu từ xa hoặc tài nguyên phía dịch vụ.

### 7.5. Lệch lịch lấy mẫu giữa các tiến trình

Mã minh họa bắt đầu ngay để việc thử dễ lặp lại. Khi nhiều tiến trình khởi động cùng lúc, chúng có thể cùng kiểm tra một đích vào các thời điểm gần nhau.

Có thể thêm độ lệch ngẫu nhiên (jitter) hữu hạn cho thời điểm bắt đầu hoặc lịch kiểm tra, trong khi vẫn giữ giới hạn tần suất và độ mới. Cần tính cửa sổ ban đầu chưa có mẫu và khoảng biến động đó vào `maxAge`.

Lấy mẫu định kỳ có thể tạo nhiều lượt gọi hơn mô hình theo nhu cầu nếu gần như không ai đọc health. Chọn chu kỳ từ ngân sách tải và yêu cầu phát hiện lỗi, thay vì mặc định kiểm tra càng dày càng tốt.

### 7.6. Dữ liệu chi tiết và khả năng quan sát

Mã mẫu chỉ trả tên phụ thuộc logic, mã nguyên nhân và tuổi mẫu. Nó không đưa thông báo ngoại lệ, body HTTP, URL có tham số nhạy cảm hoặc stack trace vào health.

Trong vận hành nên quan sát riêng:

| Số đo | Điều có thể phát hiện |
| --- | --- |
| Thời gian thực hiện phép kiểm tra | Client bắt đầu chậm trước khi mẫu quá hạn |
| Tuổi mẫu gần nhất và lần thành công gần nhất | Lịch ngừng chạy hoặc phép kiểm tra mắc kẹt |
| Số lần kiểm tra bắt đầu/kết thúc | Công việc không hoàn tất như dự kiến |
| Số kết quả lỗi/quá ngân sách | Lỗi kết nối, hợp đồng phản hồi hoặc giới hạn quá chặt |
| Tài nguyên client và kết nối | Chi phí bên dưới lớp indicator |
| Tốc độ gọi theo phụ thuộc logic | Tải toàn cụm có vượt ngân sách không |

`health()` trong thiết kế này chạy nhanh ngay cả khi I/O nền bị treo. Vì vậy log slow-indicator của Actuator không thay thế việc đo thời gian và tuổi mẫu ở luồng lấy mẫu.

Giữ nhãn số đo có tập giá trị hữu hạn. Không dùng URL tùy ý, thông báo lỗi thay đổi liên tục hoặc ID người dùng làm nhãn. Cũng không ghi một stack trace mới cho mọi lần đọc lại cùng mẫu lỗi.

## 8. Giới hạn cần đọc đúng

Thiết kế bảo vệ **đường đọc của indicator này** khỏi việc chờ mạng. Nó không bảo đảm toàn bộ `/actuator/health` trả nhanh nếu các contributor khác vẫn có I/O không giới hạn.

Nó cũng không phải bảo đảm thời gian thực tuyệt đối: lịch hệ điều hành, thu gom bộ nhớ và tài nguyên tiến trình vẫn ảnh hưởng độ trễ. Lợi ích có thể kiểm chứng là đường đọc không phụ thuộc vào việc client từ xa có trả về hay không.

Nếu một client không thể thoát khỏi I/O, mã không tự tạo một luồng mới thay thế luồng cũ cho mỗi lần timeout. Nó giữ một công việc đang mắc kẹt và để tín hiệu trở thành quá hạn. Đây là giới hạn tăng trưởng có chủ đích, cùng với việc hiển thị sự cố.

Khi cần thu hồi chắc chắn một công việc không hợp tác, phải xử lý ở client/driver hoặc một biên cách ly có khả năng kết thúc công việc đó. Yêu cầu ngắt luồng, đặt daemon hoặc gắn thêm một future không tạo ra bảo đảm ấy.

## 9. Kiểm chứng trước khi đưa phép kiểm tra vào sử dụng

Các phép thử quan trọng cần bao gồm:

| Tình huống | Bằng chứng cần có |
| --- | --- |
| Phụ thuộc thành công nhanh | Trạng thái đúng và một lần kiểm tra có chi phí đã biết |
| Trả mã không đúng hợp đồng | Không nhận nhầm là khỏe |
| Từ chối kết nối ngay | Không nhầm với trường hợp im lặng không phản hồi |
| Chậm hoặc không gửi phản hồi | Đường đọc health vẫn hoạt động theo mô hình đã chọn |
| Phân giải tên, TLS, chờ kết nối | Timeout thực tế có bao phủ các bước cần thiết |
| Phản hồi lớn hoặc nhỏ giọt | Không tải/giữ dữ liệu không giới hạn |
| Nhiều người gọi cùng lúc | Số tác vụ và kết nối không tăng theo mọi lượt đọc |
| Mẫu đã quá tuổi tối đa | Không còn dùng `UP` cũ làm trạng thái hiện tại |
| Phụ thuộc phục hồi | Một mẫu mới thay được trạng thái lỗi |
| Dừng ứng dụng khi I/O mắc kẹt | Dọn dẹp tuân theo giới hạn và hợp đồng hủy thực tế |
| Nhiều tiến trình | Tổng tần suất và đỉnh tải sau khởi động nằm trong ngân sách |

Chương trình ở mục 5 kiểm chứng chính sách mẫu và giới hạn tác vụ với phụ thuộc giả lập. Nó không phải bằng chứng client HTTP/JDBC thật đã vượt qua mọi tình huống mạng trong bảng; cần thử thêm với đúng client, driver và môi trường triển khai.

## 10. Thực hành tự kiểm tra

1. Viết hợp đồng cho một phụ thuộc thật: khả năng cần kiểm tra, thao tác tối thiểu, mã/kết quả mong đợi, timeout từng lớp, tần suất, tuổi mẫu tối đa và giới hạn đồng thời.
2. Tính tổng số lần gọi khi có `50` tiến trình, `4` nguồn giám sát và chu kỳ `10 giây`. Sau đó so với lấy mẫu riêng mỗi tiến trình với khoảng chờ `5 giây`, chưa tính thời gian chạy.
3. Trong chương trình mẫu, tăng đồng hồ giả lập vượt `maxAge` mà không tạo mẫu mới. Giải thích vì sao một kết quả thành công cũ không được trả tiếp là `UP`.
4. Cho phép kiểm tra trả `true` sau thời gian vượt `budget`. Phân biệt kết quả `PROBE_BUDGET_EXCEEDED` với khả năng thực sự dừng I/O đúng hạn.
5. Gọi `health()` nhiều lần khi phép kiểm tra đang bị chặn. Kiểm tra số lần gọi phụ thuộc, không chỉ nhìn độ trễ của một người gọi.
6. Chọn một endpoint HTTP chỉ hỗ trợ `GET`. Thiết kế giới hạn đọc phản hồi và kích thước dữ liệu trước khi thay `HEAD` trong mẫu.

Một phép kiểm tra có giới hạn cần cho thấy rõ **đang đo điều gì, được chờ bao lâu, có bao nhiêu công việc cùng tồn tại và bằng chứng sức khỏe còn mới đến lúc nào**. Bốn câu trả lời đó giúp hệ thống giám sát quan sát sự cố mà không làm sự cố lan rộng thêm.
