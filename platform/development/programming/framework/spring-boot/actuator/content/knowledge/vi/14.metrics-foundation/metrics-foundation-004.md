# Phân biệt Counter, Gauge, Timer, DistributionSummary và LongTaskTimer

## 1. Chọn phép đo từ câu hỏi cần trả lời

Giả sử một dịch vụ nhận yêu cầu xuất báo cáo. Yêu cầu được đưa vào hàng đợi, một tác vụ lấy ra xử lý, tạo dữ liệu rồi kết thúc. Với cùng luồng xử lý, người vận hành có thể hỏi:

- Đã tiếp nhận bao nhiêu yêu cầu?
- Hiện còn bao nhiêu yêu cầu đang chờ?
- Những lần xử lý đã kết thúc mất bao lâu?
- Mỗi lần xuất tạo ra bao nhiêu byte?
- Có tác vụ nào vẫn đang chạy quá lâu?

Đây là năm câu hỏi khác nhau. Một con số duy nhất như “số lượng job” không trả lời được tất cả.

Trong Micrometer, **meter** là đối tượng thu thập phép đo; `MeterRegistry` quản lý các meter và nối chúng với hệ thống giám sát. Spring Boot Actuator tích hợp Micrometer để ứng dụng đăng ký và xuất các chỉ số. Xem [Spring Boot 3.3: Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Cách chọn loại đo bắt đầu từ **ý nghĩa dữ liệu và thời điểm cần quan sát**, sau đó mới đến tên API.

## 2. Bảng phân biệt nhanh

| Loại | Câu hỏi chính | Dữ liệu đầu vào | Thông tin cốt lõi |
| --- | --- | --- | --- |
| `Counter` | Một sự kiện đã xảy ra bao nhiêu lần hoặc tích lũy bao nhiêu đơn vị? | Các lượng tăng dương | Số đếm, thường dùng để tính tốc độ |
| `Gauge` | Giá trị trạng thái hiện tại là bao nhiêu? | Hàm đọc trạng thái đang được giữ | Một giá trị tại thời điểm quan sát |
| `Timer` | Các lần xử lý đã được ghi nhận mất bao lâu? | Khoảng thời gian của từng lần | Số lần và tổng thời gian; có thể thêm thống kê |
| `DistributionSummary` | Mỗi lần có độ lớn bao nhiêu, với đơn vị không phải thời gian? | Các mẫu độ lớn như byte, số dòng | Số mẫu và tổng lượng; có thể thêm thống kê |
| `LongTaskTimer` | Những tác vụ còn đang chạy đã kéo dài bao lâu? | Bắt đầu và dừng từng tác vụ | Số tác vụ đang chạy, tổng và thời gian lớn nhất của chúng |

Ví dụ lựa chọn trong dịch vụ báo cáo:

```text
Nhận thêm yêu cầu             -> Counter
Số yêu cầu hiện còn trong hàng -> Gauge
Thời gian của từng lần kết thúc -> Timer
Kích thước dữ liệu mỗi lần xuất -> DistributionSummary
Thời gian tác vụ chưa kết thúc  -> LongTaskTimer
```

Không chọn loại meter chỉ vì giá trị Java có kiểu `int`, `long` hay `double`. Cùng một giá trị số có thể biểu diễn một trạng thái, một độ lớn hoặc một lượng tích lũy với cách đọc hoàn toàn khác nhau.

## 3. Counter: ghi nhận sự kiện xảy ra

`Counter` phù hợp khi cần cộng dồn lượng phát sinh: số yêu cầu được chấp nhận, số thông điệp bị từ chối hoặc số lần thử lại. Mỗi lần tăng phải là một lượng dương.

Ví dụ một lượt nhận một tác vụ, lượt sau nhận hai tác vụ:

```java
accepted.increment();
accepted.increment(2);
```

Đây là hai câu lệnh minh họa trên một biến `Counter` đã được đăng ký. Giá trị tích lũy của ví dụ là 3.

**Không giảm Counter để biểu diễn tác vụ kết thúc.** Nếu cần số tác vụ đang chờ hoặc đang chạy, đó là trạng thái hiện tại. Dùng Gauge hoặc thông tin active của LongTaskTimer tùy câu hỏi.

Khi đọc dashboard, tốc độ tăng trong một khoảng thời gian thường hữu ích hơn số tích lũy từ lúc khởi động. Chẳng hạn tăng từ 100 lên 160 trong 30 giây tương ứng trung bình 2 sự kiện/giây, nếu không có reset trong khoảng đó. Hệ thống giám sát cần xử lý việc tiến trình khởi động lại và cách registry xuất dữ liệu; không trừ mù quáng hai điểm thuộc hai vòng đời khác nhau.

Không cần thêm một Counter để đếm đúng những lần mà Timer hoặc DistributionSummary đã đếm. Cả hai loại đó đã cung cấp số lần ghi nhận. Một Counter cho **yêu cầu được nhận** vẫn có thể hợp lý bên cạnh Timer cho **xử lý đã kết thúc**, vì chúng đo hai mốc khác nhau. Xem [Micrometer 1.13: Counters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

## 4. Gauge: đọc một trạng thái hiện tại

`Gauge` phù hợp với độ dài hàng đợi, số kết nối đang dùng hoặc dung lượng bộ nhớ đang chiếm. Nó đọc trạng thái tại thời điểm được lấy mẫu.

Giả sử trạng thái hàng đợi thay đổi:

```text
10 -> 40 -> 2
```

Nếu hệ thống chỉ lấy mẫu ở cuối, Gauge báo 2. Nó không tự giữ lại đỉnh 40 hoặc tính được tổng số tác vụ từng đi qua hàng đợi.

Vì vậy, **trạng thái hiện tại không phải tổng sự kiện phát sinh**. Hai hệ thống cùng có queue size bằng 2 có thể có tốc độ vào/ra rất khác nhau.

Khi dùng Gauge, cần quản lý đúng đối tượng được quan sát:

- Giữ một đối tượng có thể thay đổi, chẳng hạn `AtomicInteger`, hoặc đọc trực tiếp từ hàng đợi.
- Giữ tham chiếu mạnh đến đối tượng đó trong thành phần có vòng đời phù hợp. Gauge mặc định có thể chỉ giữ tham chiếu yếu; khi đối tượng bị thu gom, kết quả có thể thành `NaN` hoặc biến mất tùy registry.
- Không dùng `Integer` bất biến rồi kỳ vọng đăng ký lại cùng tên và tag sẽ thay giá trị.
- Hàm đọc nên nhanh, an toàn khi nhiều luồng truy cập và không gây tác dụng phụ. Không thực hiện một truy vấn mạng đắt tiền mỗi lần hệ thống lấy mẫu.

Trong ứng dụng thực tế, đo trực tiếp trạng thái nguồn thường tránh được việc một biến đếm phụ bị lệch do quên cập nhật khi có lỗi. Xem [Micrometer 1.13: Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

## 5. Timer: phân bố thời gian của các lần đã được ghi nhận

`Timer` nhận **khoảng thời gian**, không nhận thời điểm lịch. Nó thường được dùng để đo độ trễ của yêu cầu, truy vấn hoặc một bước xử lý.

Với hai mẫu 100 ms và 300 ms:

```text
count      = 2 lần
total time = 400 ms
mean       = 200 ms
max        = 300 ms tại thời điểm đang xét
```

`count` là số mẫu đã ghi vào Timer, không phải số giây và cũng không tự có nghĩa là số lần thành công. Nếu đo trong `finally`, cả lần thành công và lần kết thúc bằng ngoại lệ đều có thể được ghi.

Có hai cách dùng quan trọng:

- **Đã biết khoảng thời gian:** gọi `record(Duration)` hoặc `record(amount, TimeUnit)`.
- **Đo một đoạn xử lý:** dùng API bọc đoạn mã hoặc `Timer.Sample`, bắt đầu trước và dừng khi thao tác thực sự kết thúc.

`record(Duration.ofMillis(300))` chỉ thêm một mẫu 300 ms; nó không làm chương trình chờ 300 ms và không thực thi nghiệp vụ.

Chỉ ghi khoảng thời gian không âm; không dùng thời gian âm để trừ một mẫu cũ. Dùng `Duration` hoặc chỉ rõ `TimeUnit` để tránh nhầm mili giây với giây. Không đưa timestamp như “số mili giây từ epoch” vào Timer. Thời gian đo và đơn vị xuất ra backend là hai việc cần được phân biệt.

Timer thông thường chưa thêm một mẫu hoàn chỉnh khi công việc vẫn đang chạy. Nếu công việc mắc kẹt, chỉ nhìn số đo của những lần đã kết thúc có thể bỏ qua nó. Xem [Micrometer 1.13: Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 5.1. max và p95 không đồng nghĩa với tổng thời gian

Trong các cách hiện thực cơ bản của Micrometer, `max` thường là cực đại trong cửa sổ thời gian, không phải “kỷ lục từ lúc tiến trình sinh ra”. Mẫu cũ hết hạn có thể làm max về 0 trong khi count và tổng của một registry tích lũy vẫn còn.

`p95` là một thống kê phân vị, không phải `total/count` và cũng không tự xuất hiện chỉ vì đã tạo Timer. Việc thu thập histogram hoặc phân vị cần cấu hình phù hợp với registry/backend.

Không lấy trung bình các p95 của nhiều máy rồi coi đó là p95 chung. Nếu cần phân vị tổng hợp, dùng dữ liệu histogram và cách tính được hệ thống giám sát hỗ trợ. Xem [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 6. DistributionSummary: phân bố độ lớn không phải thời gian

`DistributionSummary` có cấu trúc ý tưởng gần Timer, nhưng ghi nhận các **độ lớn với đơn vị khác thời gian**. Ví dụ: số byte mỗi phản hồi, số dòng trong một lô hoặc số phần tử trong một lần xử lý.

Với ba kích thước 128, 512 và 256 byte:

```text
count       = 3 mẫu
totalAmount = 896 byte
mean        = 896 / 3 byte trên mỗi mẫu
max         = 512 byte tại thời điểm đang xét
```

Điểm dễ nhầm:

- `count` là số lần ghi mẫu, không phải tổng số byte.
- `totalAmount` là tổng độ lớn, không phải số lần xử lý.
- `baseUnit("bytes")` mô tả đơn vị; nó không tự chuyển một giá trị kilobyte sang byte.
- Nếu cần đo thời gian, chọn Timer để có xử lý đơn vị thời gian phù hợp.

Mẫu độ lớn phải không âm; ghi số âm không phải cách điều chỉnh giảm tổng. Một Counter tăng 896 byte có thể trả lời “đã tích lũy bao nhiêu byte”, nhưng không phân biệt 896 byte đó đến từ một mẫu lớn hay nhiều mẫu nhỏ. DistributionSummary lưu được các thống kê theo từng mẫu.

Hãy định nghĩa rõ một mẫu đại diện cho cái gì: một phản hồi, một lô hay một lần ghi. Thay đổi cách chia lô sẽ làm thay đổi phân bố ngay cả khi tổng số byte không đổi. Xem [Micrometer: Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html).

Tên lớp này cũng không bảo đảm backend luôn xuất một kiểu mang tên “summary”, hoặc tự có histogram/p95. Cách biểu diễn phụ thuộc cấu hình thống kê và hệ thống giám sát.

## 7. LongTaskTimer: quan sát công việc khi nó còn chạy

`LongTaskTimer` được dùng khi cần biết tác vụ **đang hoạt động** đã kéo dài bao lâu. Nó có thể cung cấp:

- `activeTasks()`: số tác vụ đang chạy.
- `duration(unit)`: tổng thời gian đã trôi qua của các tác vụ còn đang chạy.
- `max(unit)`: thời gian lớn nhất trong các tác vụ còn đang chạy.

Khi một tác vụ dừng, nó không còn đóng góp vào các số đo active đó. Vì vậy, tổng duration của LongTaskTimer có thể giảm; nó không phải tổng thời gian xử lý lịch sử.

Đây là khác biệt về **thời điểm quan sát**, không phải quy tắc cứng rằng dưới một phút phải dùng Timer, trên một phút phải dùng LongTaskTimer. Có thể dùng cả hai với tên meter khác nhau nếu cần vừa phát hiện tác vụ đang kéo dài vừa phân tích những lần đã kết thúc.

Quên dừng sample khiến tác vụ đã xong vẫn bị tính là đang chạy. Cần bảo đảm dừng trên cả đường thành công, ngoại lệ và hủy theo vòng đời thực tế. Xem [Micrometer 1.13: Long Task Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html).

### 7.1. Hai tác vụ chạy chồng lấn

Giả sử A bắt đầu tại giây 0, B bắt đầu tại giây 2:

| Thời điểm tương đối | Trạng thái | Active count | Tổng thời gian active | Timer của các lần đã kết thúc |
| --- | --- | --- | --- | --- |
| Giây 5, chưa dừng A | A đã chạy 5 s, B đã chạy 3 s | 2 | 8 s | count=0, total=0 s |
| Giây 5, vừa dừng A | Chỉ B còn chạy 3 s | 1 | 3 s | count=1, total=5 s |
| Giây 6, vừa dừng B | Không còn tác vụ | 0 | 0 s | count=2, total=9 s |

Tại giây 5, tổng active là `5 + 3 = 8` giây, không phải tuổi của tác vụ lâu nhất. Muốn tuổi lớn nhất, đọc `max`, khi đó bằng 5 giây.

Cuối ví dụ, A mất 5 giây, B mất 4 giây, tổng là 9 giây dù khoảng thời gian thực từ đầu đến cuối chỉ là 6 giây. Nguyên nhân là hai tác vụ chạy chồng lấn. Tổng thời lượng các tác vụ không phải thời gian trên đồng hồ treo tường và cũng không tự là thời gian CPU.

## 8. Thực hành đầy đủ với đồng hồ giả lập

Ví dụ sau dùng Java 17+, có thể chạy bằng JDK 21. Dùng Spring Boot parent 3.3.13 để quản lý Micrometer 1.13.15, nhưng chương trình là ứng dụng console: không cần mở cổng HTTP, Prometheus hoặc một cơ sở dữ liệu.

`MockClock` giúp dịch chuyển thời gian có kiểm soát. Không dùng `Thread.sleep` nên stdout ổn định và phép thử chạy nhanh. Đây là công cụ của ví dụ/kiểm chứng; ứng dụng thật sử dụng clock phù hợp do registry quản lý.

### 8.1. Cấu trúc và pom.xml

Tạo thư mục mới:

```text
meter-types-lab/
├── pom.xml
└── src/main/java/demo/MeterTypesDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>meter-types-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-core</artifactId>
    </dependency>
  </dependencies>
</project>
```

Không cần thêm starter web để phân biệt ngữ nghĩa các meter. Phụ thuộc `micrometer-core` cung cấp các API đo và `SimpleMeterRegistry`.

### 8.2. Chương trình Java

Tệp `src/main/java/demo/MeterTypesDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MeterTypesDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();

        SimpleMeterRegistry registry = new SimpleMeterRegistry(
                SimpleConfig.DEFAULT, clock);
        try {
            Counter accepted = Counter.builder("lab.jobs.accepted")
                    .description("Jobs accepted by this process")
                    .register(registry);
            accepted.increment();
            accepted.increment(2);
            number("counter.count", accepted.count());

            AtomicInteger queueSize = new AtomicInteger(10);
            Gauge queued = Gauge.builder(
                            "lab.queue.size", queueSize, AtomicInteger::get)
                    .register(registry);
            queueSize.set(2);
            number("gauge.now", queued.value());

            Timer requests = Timer.builder("lab.request.duration")
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(2)
                    .register(registry);
            requests.record(Duration.ofMillis(100));
            requests.record(Duration.ofMillis(300));
            System.out.println("timer.count=" + requests.count());
            number("timer.totalMs", requests.totalTime(TimeUnit.MILLISECONDS));
            number("timer.maxMs", requests.max(TimeUnit.MILLISECONDS));

            DistributionSummary payload = DistributionSummary
                    .builder("lab.payload.size")
                    .baseUnit("bytes")
                    .register(registry);
            payload.record(128);
            payload.record(512);
            payload.record(256);
            System.out.println("summary.count=" + payload.count());
            number("summary.totalBytes", payload.totalAmount());
            number("summary.maxBytes", payload.max());

            Timer completed = Timer.builder("lab.jobs.completed")
                    .register(registry);
            LongTaskTimer running = LongTaskTimer.builder("lab.jobs.running")
                    .register(registry);

            Timer.Sample doneA = Timer.start(registry);
            LongTaskTimer.Sample activeA = running.start();
            clock.add(Duration.ofSeconds(2));

            Timer.Sample doneB = Timer.start(registry);
            LongTaskTimer.Sample activeB = running.start();
            clock.add(Duration.ofSeconds(3));
            printJobs("bothRunning", running, completed);

            activeA.stop();
            doneA.stop(completed);
            printJobs("afterA", running, completed);

            clock.add(Duration.ofSeconds(1));
            activeB.stop();
            doneB.stop(completed);
            printJobs("afterAll", running, completed);

            clock.add(Duration.ofSeconds(21));
            System.out.println("timer.later.count=" + requests.count());
            number("timer.later.totalMs", requests.totalTime(TimeUnit.MILLISECONDS));
            number("timer.later.maxMs", requests.max(TimeUnit.MILLISECONDS));
        } finally {
            registry.close();
        }
    }

    private static void printJobs(
            String phase, LongTaskTimer running, Timer completed) {
        System.out.println(phase + ".active=" + running.activeTasks());
        number(phase + ".activeSeconds", running.duration(TimeUnit.SECONDS));
        number(phase + ".maxActiveSeconds", running.max(TimeUnit.SECONDS));
        System.out.println(phase + ".completed=" + completed.count());
        number(phase + ".completedSeconds", completed.totalTime(TimeUnit.SECONDS));
    }

    private static void number(String name, double value) {
        System.out.printf(Locale.ROOT, "%s=%.1f%n", name, value);
    }
}
```

Những lựa chọn có chủ đích:

1. `SimpleMeterRegistry` giữ số đo trong bộ nhớ và cho đọc trực tiếp, phù hợp kiểm chứng ý nghĩa API.
2. Biến `queueSize` giữ đối tượng Gauge đang quan sát. Việc đổi từ 10 thành 2 làm lần đọc hiện tại bằng 2.
3. Timer nhận trực tiếp hai khoảng thời gian; DistributionSummary nhận ba kích thước.
4. Hai tác vụ A/B được theo dõi bằng cả Timer và LongTaskTimer nhưng dùng **hai tên meter khác nhau**.
5. Timer yêu cầu có expiry 10 giây, buffer length 2 để phép thử max hết hạn có ranh giới rõ ràng.
6. `Locale.ROOT` giữ cách in dấu thập phân ổn định, không phụ thuộc thiết lập ngôn ngữ của máy.
7. Registry được đóng trong `finally`. Với Micrometer 1.13.15, không dùng `try-with-resources` cho `SimpleMeterRegistry` vì kiểu này không triển khai `AutoCloseable`.

Chương trình mô phỏng vòng đời bình thường theo một luồng. Trong nghiệp vụ thực tế, cần bổ sung đường kết thúc bằng ngoại lệ như phần 10.

### 8.3. Biên dịch và chạy

Đứng trong thư mục `meter-types-lab`. Lần đầu Maven cần mạng để lấy plugin/phụ thuộc.

Trên PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -cp $cp demo.MeterTypesDemo
```

Trên Linux/macOS, sau cùng lệnh Maven:

```bash
cp="target/classes:$(cat classpath.txt)"
java -cp "$cp" demo.MeterTypesDemo
```

Maven biên dịch mã với đích Java 17; dấu phân cách classpath là `;` trên Windows và `:` trên Linux/macOS.

Stdout chính xác:

```text
counter.count=3.0
gauge.now=2.0
timer.count=2
timer.totalMs=400.0
timer.maxMs=300.0
summary.count=3
summary.totalBytes=896.0
summary.maxBytes=512.0
bothRunning.active=2
bothRunning.activeSeconds=8.0
bothRunning.maxActiveSeconds=5.0
bothRunning.completed=0
bothRunning.completedSeconds=0.0
afterA.active=1
afterA.activeSeconds=3.0
afterA.maxActiveSeconds=3.0
afterA.completed=1
afterA.completedSeconds=5.0
afterAll.active=0
afterAll.activeSeconds=0.0
afterAll.maxActiveSeconds=0.0
afterAll.completed=2
afterAll.completedSeconds=9.0
timer.later.count=2
timer.later.totalMs=400.0
timer.later.maxMs=0.0
```

### 8.4. Giải thích kết quả theo từng loại

**Counter và Gauge**

`counter.count=3.0` đến từ `1 + 2`. `gauge.now=2.0` là trạng thái cuối đang được quan sát; không phải `10 + 2` và không phải số lần thay đổi.

**Timer**

Hai mẫu 100 ms và 300 ms tạo count=2, total=400 ms, max=300 ms. Chương trình không cần thực sự chạy chậm 400 ms để thêm hai mẫu này.

**DistributionSummary**

Ba mẫu tạo count=3, total=896 byte và max=512 byte. Nếu chỉ nhìn count=3 thì không thể biết lượng dữ liệu là bao nhiêu.

**Khi cả A và B còn chạy**

`bothRunning.active=2` và `bothRunning.activeSeconds=8.0` phản ánh hai tác vụ chưa dừng. `bothRunning.completed=0` xác nhận Timer chưa có mẫu hoàn chỉnh nào của chúng.

**Sau khi A kết thúc**

LongTaskTimer chỉ còn B với 3 giây active; Timer giữ một lần kết thúc dài 5 giây.

**Sau khi cả hai kết thúc**

Các số active về 0, bao gồm cả max active. Timer giữ hai lần và tổng thời gian 9 giây. Đây là bằng chứng LongTaskTimer không thay thế lịch sử các lần đã kết thúc.

**Sau khi cửa sổ max cũ hết hạn**

`timer.later.maxMs=0.0` nhưng count vẫn bằng 2 và total vẫn 400 ms trong `SimpleMeterRegistry` đang dùng. Không có yêu cầu mới nào vừa chạy trong 0 ms; mẫu cực đại cũ đã hết hạn.

Kết quả này kiểm chứng đúng cấu hình của ví dụ. Không suy ra mọi registry đều tích lũy count/total hoặc xuất các thống kê giống hệt nhau: một backend có thể dùng cửa sổ step, chuẩn hóa theo tốc độ hoặc chuyển đơn vị.

## 9. Diễn giải dữ liệu đúng sau khi chọn meter

### 9.1. Số lần, tổng lượng và giá trị hiện tại khác nhau

| Giá trị quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Counter tăng thêm 20 | Có thêm 20 đơn vị đã được ghi nhận | Hiện có 20 tác vụ đang chạy |
| Gauge bằng 20 | Trạng thái tại lúc lấy mẫu là 20 | Có đúng 20 sự kiện xảy ra trong khoảng trước đó |
| Timer count bằng 20 | Có 20 mẫu thời gian được ghi | Cả 20 lần đều thành công |
| Summary count bằng 20 | Có 20 mẫu độ lớn | Tổng lượng bằng 20 byte |
| LongTaskTimer active bằng 20 | Có 20 sample tác vụ đang hoạt động | Đã hoàn thành 20 tác vụ |

Một tên quá chung như `jobs.count` khiến người đọc khó biết đang nói đến hàng nào trong bảng. Tên nên phản ánh ý nghĩa như `jobs.accepted`, `queue.size`, `jobs.completed` hoặc `jobs.running`.

### 9.2. Trung bình phải dùng đúng tử số và mẫu số

Với Timer, trung bình thời gian cho cùng một tập mẫu là:

```text
tổng thời gian / số mẫu thời gian
```

Với DistributionSummary, trung bình độ lớn là:

```text
tổng lượng / số mẫu độ lớn
```

Không chia `summary.totalAmount` cho count của một Timer đo giai đoạn khác. Hai tập sự kiện có thể không tương ứng.

Khi tổng hợp nhiều bản sao, nếu các giá trị là cùng đơn vị và cùng khoảng/tập mẫu, hãy cộng tổng rồi chia cho tổng count. Không lấy trung bình đơn giản của các giá trị trung bình khi số mẫu khác nhau.

Ví dụ máy A có 1 mẫu trung bình 1000 ms, máy B có 9 mẫu trung bình 100 ms. Trung bình chung là `(1000 + 900) / 10 = 190 ms`, không phải `(1000 + 100) / 2 = 550 ms`.

Khi cần biểu đồ theo một cửa sổ thời gian, dùng tổng và count của cùng cửa sổ theo cách backend hỗ trợ. Không trộn một tổng tích lũy từ lúc khởi động với số lần chỉ trong phút gần nhất.

### 9.3. Cực đại của hai loại timer trả lời hai câu hỏi khác nhau

- Max của Timer cơ bản: cực đại của các mẫu đã ghi trong cửa sổ thống kê.
- Max của LongTaskTimer: thời lượng lớn nhất trong các tác vụ còn active tại lúc quan sát.

Khi A dừng, LongTaskTimer max trong ví dụ giảm từ 5 xuống 3 giây dù không có dữ liệu nào bị “sửa sai”. Tập tác vụ đang được xét đã thay đổi.

## 10. Gắn phép đo vào vòng đời xử lý thực tế

Phần dưới là **mã tích hợp minh họa**, giả sử đã có các biến `registry`, `completedTimer`, `runningTimer` và phương thức nghiệp vụ `exportReport()`. Nó không phải một chương trình độc lập.

```java
Timer.Sample completion = Timer.start(registry);
LongTaskTimer.Sample active = runningTimer.start();

try {
    exportReport();
} finally {
    active.stop();
    completion.stop(completedTimer);
}
```

Các kiểu thuộc `io.micrometer.core.instrument`. Dừng trong `finally` giúp một ngoại lệ từ nghiệp vụ không để lại tác vụ active giả và vẫn ghi thời gian của lần kết thúc đó.

Với cách đo này, count của `completedTimer` là số lần kết thúc được đo, gồm cả lỗi. Nếu cần tách thành công/thất bại, thiết kế nhãn kết quả có tập giá trị nhỏ hoặc các meter phản ánh đúng nhu cầu. Không đổi nghĩa count chỉ bằng cách đặt một tiêu đề dashboard “success”.

Cũng cần xác định chính xác biên đo:

- Bắt đầu khi nhận yêu cầu hay khi tác vụ bắt đầu xử lý?
- Kết thúc khi trả phản hồi, khi ghi xong tệp hay khi tác vụ nền hoàn tất?
- Số dòng/kích thước được ghi cho lần thành công hay cho cả lần lỗi?
- Khi hủy tác vụ, đường nào chịu trách nhiệm dừng sample?

Với xử lý bất đồng bộ, bọc mỗi lời gọi “gửi tác vụ vào executor” chỉ đo thời gian gửi. Muốn đo toàn bộ công việc, phải dừng sample khi công việc bất đồng bộ thực sự kết thúc. Không dừng ngay lúc phương thức trả về một `Future` chưa hoàn tất.

Bản thân meter không tự suy ra ranh giới nghiệp vụ. Chọn đúng loại vẫn có thể cho kết quả sai nếu bắt đầu/dừng ở sai vị trí.

## 11. Áp dụng trong Spring Boot mà vẫn giữ đúng ý nghĩa

Trong ứng dụng Spring Boot có Actuator, tiêm `MeterRegistry` do ứng dụng quản lý vào thành phần cần đo. Không tạo `new SimpleMeterRegistry()` trong từng request rồi kỳ vọng các meter đó tự xuất qua registry của ứng dụng.

`SimpleMeterRegistry` trong bài là công cụ kiểm chứng độc lập. Ứng dụng vận hành cần registry/exporter phù hợp; Actuator có thể tự cấu hình theo các triển khai có trên classpath. Xem [Spring Boot: Getting Started with Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.getting-started).

Các nguyên tắc đăng ký:

1. Đăng ký các meter có danh tính ổn định rồi tái sử dụng. Tên cùng bộ tag xác định meter; không dùng cùng danh tính để vừa đăng ký Gauge vừa đăng ký Counter.
2. Dùng tên theo quy ước dễ chuyển đổi, chẳng hạn các từ chữ thường phân cách bằng dấu chấm. Tên xuất ở backend có thể được chuyển đổi.
3. Chọn tag có tập giá trị được kiểm soát như `kind=export` hoặc `outcome=success/error`. Không dùng mã yêu cầu, nội dung lỗi tùy ý hoặc ID người dùng làm tag cho từng sự kiện.
4. Với Gauge, thành phần sống lâu cần giữ đối tượng trạng thái được quan sát. Đăng ký mới mỗi lần cập nhật không phải cách thay đổi giá trị gauge.
5. Xem trước các meter tự động đã có. Nếu cùng một thao tác đã được đo, chỉ thêm meter khi cần một ngữ nghĩa hoặc biên đo khác.

Mỗi tổ hợp tag có thể tạo thêm chuỗi thời gian; histogram còn làm số chuỗi tăng theo các bucket. Việc chọn meter và tag cần gắn với câu hỏi quan sát, không phải ghi mọi chi tiết nghiệp vụ vào metrics. Xem [Micrometer 1.13: Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Metrics là dữ liệu tổng hợp. Chúng không thay thế bản ghi kiểm toán hoặc log chi tiết của từng yêu cầu.

## 12. Lỗi thường gặp và cách tự kiểm chứng

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Giảm Counter khi tác vụ xong | Counter biểu diễn lượng phát sinh tăng dần | Dùng Gauge hoặc activeTasks cho trạng thái |
| Dùng Gauge để đếm tổng request | Mẫu trung gian có thể bị bỏ qua và không có ngữ nghĩa sự kiện tích lũy | Dùng Counter hoặc count đã có của Timer |
| Tạo Gauge với một `Integer` rồi gán biến sang số mới | Gauge vẫn quan sát đối tượng đã đăng ký; số đóng hộp là bất biến | Dùng trạng thái có thể thay đổi và giữ tham chiếu |
| Đưa mili giây vào Summary để đo độ trễ | Tự gánh việc xử lý đơn vị thời gian và làm mất ý nghĩa Timer | Dùng Timer |
| Đọc Timer count như tổng thời gian | Count và total là hai thống kê khác nhau | Xem đơn vị và ý nghĩa của từng giá trị |
| Coi Timer chỉ đếm lần thành công | Kết quả phụ thuộc vị trí và cách ghi nhận | Xác định biên đo và kết quả cần phân loại |
| Dùng LongTaskTimer duration làm tổng lịch sử | Tác vụ đã dừng không còn đóng góp | Thêm Timer riêng cho các lần kết thúc |
| Quên dừng LongTaskTimer sample | Tạo tác vụ active giả | Dừng ở đúng đường hoàn tất, kể cả lỗi |
| Coi max luôn là kỷ lục trọn đời | Max có thể dùng cửa sổ thời gian | Kiểm tra cấu hình và registry |
| Mong p95 tự có hoặc cộng/trung bình p95 giữa máy | Phân vị có yêu cầu thu thập và tổng hợp riêng | Dùng cách thống kê được backend hỗ trợ |
| Đếm lại cùng một sự kiện bằng Counter và Timer mà không có mục đích | Tạo hai số đếm dư thừa, có thể lệch do điểm cập nhật khác nhau | Tái sử dụng count hoặc tách rõ hai mốc nghiệp vụ |

**Bài tập 1:** Một batch có 200 dòng. Mỗi lần batch kết thúc, chương trình gọi `summary.record(200)`. Sau 5 batch giống nhau, count và totalAmount bằng bao nhiêu?

**Đáp án:** count=5, totalAmount=1000 dòng. Nếu đã có Summary thì không cần Counter riêng chỉ để đếm đúng 5 batch đó.

**Bài tập 2:** Một tác vụ đang chạy 15 phút nhưng Timer count không tăng. Có chắc tác vụ không chạy không?

**Đáp án:** không. Timer thường ghi mẫu khi tác vụ kết thúc. Dùng LongTaskTimer để quan sát tác vụ còn chạy và xem vị trí bắt đầu/dừng đo.

**Bài tập 3:** Hàng đợi lần lượt có 0, 100 rồi 0 tác vụ giữa hai lần lấy mẫu. Gauge có bắt buộc báo được đỉnh 100 không?

**Đáp án:** không. Gauge phản ánh trạng thái lúc lấy mẫu. Nếu cần quan sát đỉnh hoặc tổng số lượt đi qua, phải có phép đo bổ sung được thiết kế đúng mục tiêu.

**Bài tập 4:** Chỉ muốn biết mỗi phản hồi lớn bao nhiêu byte, nhưng lại dùng `Counter.increment(size)`. Còn thiếu điều gì?

**Đáp án:** biết tổng byte nhưng chưa biết số mẫu và các thống kê độ lớn theo từng phản hồi. Dùng DistributionSummary cho câu hỏi đó.

**Bài tập 5:** Tại một thời điểm, hai tác vụ đang chạy được 7 giây và 4 giây. LongTaskTimer active count, tổng duration và max lần lượt là gì?

**Đáp án:** 2, 11 giây và 7 giây. Khi tác vụ 7 giây dừng, các giá trị active trở thành 1, 4 giây và 4 giây nếu không có thời gian mới trôi qua.

Trước khi đăng ký meter, hãy hoàn thành câu: “Tôi muốn biết lượng phát sinh, trạng thái hiện tại, thời gian đã kết thúc, độ lớn từng lần hay thời gian còn đang chạy”. Câu trả lời đó dẫn tới loại meter; ranh giới đo, đơn vị, tag và cấu hình thống kê quyết định dữ liệu cuối cùng có đúng ý nghĩa hay không.
