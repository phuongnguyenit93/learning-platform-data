# Quan hệ giữa đo lường, lấy mẫu và thời điểm hệ thống giám sát thu thập

## 1. Vì sao ứng dụng đã thay đổi nhưng biểu đồ chưa thay đổi?

Giả sử ứng dụng nhận một nhóm tác vụ, số tác vụ đang chạy tăng mạnh rồi giảm về 0 trong một giây. Người vận hành nhìn biểu đồ sau đó nhưng không thấy đỉnh tăng. Một khả năng khác: số yêu cầu đã được đếm đủ, nhưng biểu đồ tốc độ không cho biết chính xác chúng dồn vào thời điểm nào.

Đây không nhất thiết là lỗi của Micrometer. Cần phân biệt ba việc:

1. **Đo lường trong ứng dụng:** mã nghiệp vụ cập nhật hoặc ghi nhận một phép đo.
2. **Lấy mẫu/đọc trạng thái:** một giá trị được quan sát tại một thời điểm.
3. **Thu thập vào hệ thống giám sát:** dữ liệu được lấy hoặc gửi ra ngoài theo một lịch riêng.

Sau đó còn có bước truy vấn và hiển thị. Việc nghiệp vụ xảy ra, việc meter được cập nhật và việc biểu đồ có điểm dữ liệu mới không phải cùng một thời điểm.

Bài học tập trung vào quan hệ thời gian đó trong Micrometer và Spring Boot Actuator, dùng Prometheus làm ví dụ cụ thể. Ví dụ Java có đồng hồ giả lập để kiểm chứng cả dữ liệu được giữ lại lẫn dữ liệu không thể suy ra từ những lần quan sát thưa.

## 2. Đặt từng bước vào đúng vị trí

Một đường thu thập theo mô hình kéo dữ liệu (pull) có thể hình dung như sau:

```text
Sự kiện nghiệp vụ hoặc thay đổi trạng thái
    -> mã đo trong ứng dụng
    -> MeterRegistry tích lũy dữ liệu hoặc giữ hàm đọc trạng thái
    -> bên thu thập gọi endpoint theo lịch scrape
    -> dữ liệu được lưu trong hệ thống chuỗi thời gian
    -> truy vấn tính toán theo cửa sổ
    -> dashboard hoặc quy tắc cảnh báo đọc kết quả
```

Ví dụ với Prometheus:

- Ứng dụng tăng Counter khi nhận tác vụ.
- Gauge đọc số tác vụ đang chạy khi dữ liệu được thu thập.
- Timer ghi thời gian khi một tác vụ được kết thúc và mẫu được dừng.
- Prometheus định kỳ gọi endpoint cung cấp dữ liệu.
- Dashboard có thể truy vấn tốc độ trong 5 phút và tự làm mới theo lịch khác.

Trong mô hình đẩy dữ liệu (push), một registry/exporter chủ động xuất dữ liệu theo lịch. Một số registry tổng hợp theo khoảng `step` trước khi xuất. Không được mặc định mọi backend đều gửi số tích lũy từ lúc khởi động hoặc có cùng nhịp với Prometheus. Xem [Micrometer: Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

Prometheus dùng mô hình pull; `PrometheusMeterRegistry.scrape()` tạo nội dung để bên thu thập đọc. Trong ứng dụng web, nội dung đó cần được đưa qua một endpoint phù hợp. Xem [Micrometer Prometheus 1.13](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

## 3. “Lấy mẫu” có thể chỉ nhiều việc khác nhau

Từ “sample” dễ gây hiểu nhầm nếu không nói rõ đang lấy mẫu cái gì.

| Cách dùng từ | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| Lấy mẫu một Gauge | Đọc trạng thái hiện tại tại một thời điểm | Giữ lại mọi thay đổi trạng thái trước đó |
| Một mẫu thời gian của Timer | Một khoảng thời gian được ghi nhận | Chọn ngẫu nhiên một phần request để đo |
| `Timer.Sample` | Đối tượng giữ thời điểm bắt đầu để tính khoảng thời gian khi dừng | Một cấu hình tỉ lệ lấy mẫu |
| Một sample trong chuỗi thời gian | Giá trị gắn với thời điểm quan sát/lưu trữ theo hệ thống | Bản ghi chi tiết của một sự kiện nghiệp vụ |
| Lấy mẫu thống kê hoặc tracing | Chủ động chọn một phần sự kiện/trace để xử lý hoặc lưu | Chu kỳ scrape của hệ thống metrics |

Nếu mã gọi `counter.increment()` cho từng sự kiện được đo, việc Prometheus scrape mỗi 15 giây không có nghĩa chỉ một sự kiện mỗi 15 giây được đếm.

Ngược lại, nếu ứng dụng chủ động chỉ gọi mã đo cho một phần sự kiện, thu thập thường xuyên hơn không tự bổ sung những sự kiện chưa từng được ghi nhận. Phải phân biệt **mật độ đo tại nguồn** với **mật độ đọc dữ liệu đã đo**.

Tương tự, tỉ lệ giữ trace không phải tần suất thu thập metrics. Không dùng một thuộc tính sampling của tracing để giải thích lịch scrape của Prometheus. Hai đường dữ liệu có mục tiêu và cấu hình riêng.

## 4. Loại meter quyết định thông tin nào còn lại giữa hai lần thu

### 4.1. Counter tích lũy các lần tăng

Xét một Counter tích lũy trên cùng một tiến trình, được ghi cho mọi sự kiện đang xét:

```text
t=0 s:   Counter = 100       <- thu thập
t=2 s:   tăng 5
t=3 s:   tăng 7
t=10 s:  Counter = 112       <- thu thập
```

Đến giây 10, giá trị vẫn chứa 12 lần tăng dù không thu ở giây 2 và 3. Nhưng chỉ hai điểm 100 và 112 không cho biết 12 sự kiện dồn vào giây nào.

Có thể mô tả mức tăng trung bình trong khoảng bằng `12 / 10 = 1,2 sự kiện/giây`, với giả định không reset và đang so đúng chuỗi dữ liệu. Đây là phép tính minh họa từ hai điểm, không phải cam kết rằng mọi hàm truy vấn tốc độ đều thực hiện đúng phép chia đơn giản đó.

Counter giữ được lượng tích lũy; nó không giữ một danh sách timestamp cho từng sự kiện.

### 4.2. Gauge chỉ cho biết trạng thái khi được đọc

Xét số tác vụ đang chạy:

```text
t=0 s:   active = 0         <- thu thập
t=2 s:   active = 40
t=3 s:   active = 0
t=10 s:  active = 0         <- thu thập
```

Hai điểm thu đều bằng 0. Từ chúng không thể kết luận “không có lúc nào tác vụ chạy” hoặc “đỉnh bằng 0”.

Đây là đặc tính của phép đo tức thời. Gauge không tự lưu chuỗi thay đổi, tổng lượt vào/ra hoặc cực đại giữa hai lần đọc. Xem [Micrometer 1.13: Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

Thu thường xuyên hơn có thể tăng cơ hội thấy đợt tăng ngắn, nhưng một sự kiện vẫn có thể xảy ra trọn vẹn giữa hai lần thu. Nếu cần ghi nhận mọi lần vượt ngưỡng, phải đo hành vi đó ngay tại nguồn, chẳng hạn đếm lần vượt ngưỡng hoặc duy trì cực đại theo cửa sổ với quy tắc rõ ràng.

### 4.3. Timer chỉ đóng góp mẫu hoàn chỉnh khi được ghi

Một tác vụ bắt đầu tại giây 1, kết thúc tại giây 8:

```text
t=1 s:   bắt đầu Timer.Sample
t=5 s:   thu thập, tác vụ vẫn đang chạy
t=8 s:   dừng sample -> thêm một mẫu 7 giây vào Timer
t=10 s:  thu thập, thấy count và tổng thời gian đã tăng
```

Lần thu ở giây 5 không có một mẫu 4 giây “tạm tính” của tác vụ đó trong Timer thông thường. Lần thu ở giây 10 thấy mẫu 7 giây vì mẫu đã được kết thúc và ghi trước khi thu.

Vì vậy, tổng thời gian của các mẫu hoàn tất trong một cửa sổ không tự là “thời gian CPU tiêu thụ trong cửa sổ”. Một phần thời gian của tác vụ có thể xảy ra từ trước cửa sổ, và nhiều tác vụ có thể chạy chồng lấn.

Nếu cần quan sát tác vụ khi nó còn chạy, có thể dùng LongTaskTimer hoặc phép đo trạng thái phù hợp. Cần chọn đúng thông tin cần giữ, không chỉ thay chu kỳ scrape. Xem [Micrometer 1.13: Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 4.4. Thống kê theo cửa sổ có thể đổi dù không có sự kiện mới

`max` trong các cách hiện thực Timer cơ bản thường dùng một cửa sổ thống kê. Khi dữ liệu cũ hết hạn, max có thể trở về 0.

Trong khi đó, count và sum của một Timer tích lũy vẫn có thể giữ nguyên. Không có mâu thuẫn: các thống kê không nhất thiết có cùng quy tắc thời gian.

Cần xác định riêng:

- Điều gì làm count/sum thay đổi?
- Khoảng nào được dùng để giữ max hoặc phân vị?
- Khi dữ liệu hết hạn, giá trị biểu diễn là gì?
- Registry xuất số tích lũy hay số của một khoảng step?

Không đọc `max=0` sau một khoảng im lặng thành bằng chứng “tác vụ gần nhất chạy trong 0 giây”.

## 5. Các nhịp thời gian độc lập cần phân biệt

| Nhịp/thời điểm | Thành phần quyết định | Tác động |
| --- | --- | --- |
| Thời điểm nghiệp vụ | Luồng xử lý của ứng dụng | Lúc hành động thực sự xảy ra |
| Thời điểm ghi phép đo | Vị trí mã đo được gọi | Sự kiện đã đóng góp vào meter hay chưa |
| Lần đọc Gauge | Lúc hàm đọc được gọi | Trạng thái nào được quan sát |
| Cửa sổ thống kê/step | Cấu hình và cách hiện thực registry | Dữ liệu được tổng hợp/giữ đến khi nào |
| Chu kỳ scrape hoặc xuất dữ liệu | Bên thu thập hoặc exporter | Dữ liệu được đưa ra ngoài theo lịch nào |
| Cửa sổ và bước truy vấn | Biểu thức truy vấn, khoảng thời gian truy vấn | Cách các điểm đã lưu được tính toán |
| Chu kỳ đánh giá cảnh báo/làm mới dashboard | Hệ thống quy tắc hoặc giao diện | Khi nào kết quả được kiểm tra/hiển thị |

Ví dụ, thu thập mỗi 15 giây, tính tốc độ trên cửa sổ 5 phút và làm mới màn hình mỗi 10 giây là ba cấu hình khác nhau.

Làm mới màn hình nhanh hơn không làm Gauge trong ứng dụng được thu thập nhanh hơn. Tăng số điểm của một truy vấn theo khoảng cũng không tạo thêm mẫu gốc chưa từng được thu.

Ngược lại, thu thập dày hơn nhưng vẽ biểu đồ với bước truy vấn quá thưa có thể làm cách hiển thị bỏ qua chi tiết đã được lưu. Khi điều tra, cần biết cả độ phân giải dữ liệu gốc và cách truy vấn/hiển thị dùng dữ liệu đó.

Prometheus phân biệt truy vấn tại một thời điểm với truy vấn theo khoảng có các bước đánh giá cách đều. Xem [Prometheus: Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/).

## 6. Thực hành: đo liên tục nhưng chỉ thu ở một số thời điểm

Ví dụ dùng Java 17+, có thể chạy bằng JDK 21. Spring Boot parent 3.3.13 quản lý phiên bản Micrometer Prometheus 1.13.15. Đây là chương trình console, không cần khởi động Prometheus server hoặc mở cổng HTTP.

Chương trình gọi **`PrometheusMeterRegistry.scrape()` thật** để tạo nội dung xuất, rồi đọc một số dòng số liệu để in ra. Nó mô phỏng lịch bên thu thập bằng `MockClock`; không phải một phép thử lưu dữ liệu vào Prometheus server.

### 6.1. Kịch bản dữ liệu

Dùng ba phép đo của cùng một luồng tác vụ:

- Counter: tổng số tác vụ được nhận.
- Gauge: số tác vụ hiện còn đang chạy.
- Timer: số lần kết thúc và thời gian của các tác vụ đã kết thúc.

| Giây tương đối | Điều xảy ra trong ứng dụng | Có thu thập không? |
| --- | --- | --- |
| 0 | Chưa nhận tác vụ | Có |
| 1 | Nhận 4 tác vụ; cả 4 bắt đầu chạy | Không |
| 2 | 3 tác vụ kết thúc, mỗi tác vụ mất 1 giây; còn 1 đang chạy | Không |
| 5 | Tác vụ còn lại chưa kết thúc | Có |
| 8 | Tác vụ còn lại kết thúc sau 7 giây | Không |
| 10 | Không còn tác vụ đang chạy | Có |
| 12 | Nhận thêm 6 tác vụ; cả 6 bắt đầu chạy | Không |
| 13 | Cả 6 kết thúc, mỗi tác vụ mất 1 giây | Không |
| 15 | Bỏ qua lần thu dự kiến | Không |
| 20 | Đọc dữ liệu; sau đó đọc lại ngay cùng thời điểm | Có |
| 120 | Không có tác vụ mới; cửa sổ max cũ đã hết hạn | Có |

Mốc tương đối dùng để giải thích. Nó không phải timestamp nghiệp vụ được gắn vào từng dòng Counter trong nội dung xuất.

### 6.2. Cấu trúc và phụ thuộc

Tạo một thư mục học thử riêng:

```text
metrics-time-lab/
├── pom.xml
└── src/main/java/demo/MetricsTimeDemo.java
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
  <artifactId>metrics-time-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
  </dependencies>
</project>
```

Phụ thuộc `micrometer-registry-prometheus` dùng Prometheus Java client mới trong nhánh Micrometer này, với package `io.micrometer.prometheusmetrics`. Không trộn các import của client cũ `prometheus-simpleclient` vào cùng ví dụ.

### 6.3. Chương trình Java hoàn chỉnh

Tệp `src/main/java/demo/MetricsTimeDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import io.prometheus.metrics.model.registry.PrometheusRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MetricsTimeDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        long origin = clock.monotonicTime();
        PrometheusMeterRegistry registry = new PrometheusMeterRegistry(
                PrometheusConfig.DEFAULT, new PrometheusRegistry(), clock);

        try {
            Counter accepted = registry.counter("lab.jobs.accepted");
            AtomicInteger active = new AtomicInteger(0);
            Gauge.builder("lab.jobs.active", active, AtomicInteger::get)
                    .register(registry);
            Timer duration = Timer.builder("lab.jobs.duration")
                    .distributionStatisticExpiry(Duration.ofSeconds(30))
                    .distributionStatisticBufferLength(3)
                    .register(registry);

            collect("initial", registry, clock, origin);

            clock.add(Duration.ofSeconds(1));
            accepted.increment(4);
            active.set(4);
            Timer.Sample slowJob = Timer.start(registry);

            clock.add(Duration.ofSeconds(1));
            for (int i = 0; i < 3; i++) {
                duration.record(Duration.ofSeconds(1));
            }
            active.set(1);

            clock.add(Duration.ofSeconds(3));
            collect("first", registry, clock, origin);

            clock.add(Duration.ofSeconds(3));
            slowJob.stop(duration);
            active.set(0);

            clock.add(Duration.ofSeconds(2));
            collect("second", registry, clock, origin);

            clock.add(Duration.ofSeconds(2));
            accepted.increment(6);
            active.set(6);

            clock.add(Duration.ofSeconds(1));
            for (int i = 0; i < 6; i++) {
                duration.record(Duration.ofSeconds(1));
            }
            active.set(0);

            // No collection at t=15 seconds.
            clock.add(Duration.ofSeconds(7));
            collect("afterGap", registry, clock, origin);
            collect("repeat", registry, clock, origin);

            clock.add(Duration.ofSeconds(100));
            collect("expired", registry, clock, origin);
        } finally {
            registry.close();
        }
    }

    private static void collect(String phase, PrometheusMeterRegistry registry,
                                MockClock clock, long origin) {
        String text = registry.scrape();
        long seconds = TimeUnit.NANOSECONDS.toSeconds(
                clock.monotonicTime() - origin);
        double accepted = value(text, "lab_jobs_accepted_total");
        double active = value(text, "lab_jobs_active");
        double completed = value(text, "lab_jobs_duration_seconds_count");
        double totalMs = 1000 * value(text, "lab_jobs_duration_seconds_sum");
        double maxMs = 1000 * value(text, "lab_jobs_duration_seconds_max");

        System.out.printf(Locale.ROOT,
                "%s t=%ds accepted=%.0f active=%.0f completed=%.0f totalMs=%.0f maxMs=%.0f%n",
                phase, seconds, accepted, active, completed, totalMs, maxMs);
    }

    private static double value(String text, String name) {
        return text.lines()
                .filter(line -> line.startsWith(name + " "))
                .map(line -> line.trim().split("\\s+")[1])
                .mapToDouble(Double::parseDouble)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing sample: " + name));
    }
}
```

Cách đọc chương trình:

1. `accepted.increment(...)` được gọi khi nhóm tác vụ được nhận, không đợi một lần scrape.
2. `active` thay đổi khi tác vụ bắt đầu/kết thúc. Gauge giữ hàm đọc biến này; thành phần ứng dụng vẫn phải giữ đối tượng trạng thái sống đủ lâu.
3. Các tác vụ ngắn được ghi bằng khoảng thời gian đã biết. Lời gọi `record(Duration)` thêm mẫu, không làm chương trình chờ.
4. Tác vụ dài dùng `Timer.Sample` để khoảng 7 giây được tính theo clock của registry khi dừng.
5. Hàm `collect` gọi `scrape()` rồi đọc dữ liệu đã xuất; kết quả không chỉ lấy trực tiếp từ các biến nghiệp vụ.
6. Mẫu max được giữ bằng expiry 30 giây và buffer length 3. Lần đọc tại giây 120 đủ xa để dữ liệu cực đại cũ hết hạn trong ví dụ.
7. Hàm `value` chỉ phục vụ định dạng xuất không có tag của phòng thực hành. Đây không phải parser tổng quát cho mọi định dạng Prometheus/OpenMetrics.

`MockClock` làm thời gian dịch chuyển tức thì để phép thử ổn định. Không dùng nó thay clock của ứng dụng vận hành. Registry được đóng trong `finally` khi chương trình kết thúc.

### 6.4. Biên dịch và chạy

Đứng trong thư mục `metrics-time-lab`. Lần đầu Maven cần mạng để tải plugin và phụ thuộc.

Trên PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -cp $cp demo.MetricsTimeDemo
```

Trên Linux/macOS, sau cùng lệnh Maven:

```bash
cp="target/classes:$(cat classpath.txt)"
java -cp "$cp" demo.MetricsTimeDemo
```

Maven biên dịch với đích Java 17. Dấu phân cách classpath là `;` trên Windows và `:` trên Linux/macOS.

Stdout chính xác:

```text
initial t=0s accepted=0 active=0 completed=0 totalMs=0 maxMs=0
first t=5s accepted=4 active=1 completed=3 totalMs=3000 maxMs=1000
second t=10s accepted=4 active=0 completed=4 totalMs=10000 maxMs=7000
afterGap t=20s accepted=10 active=0 completed=10 totalMs=16000 maxMs=7000
repeat t=20s accepted=10 active=0 completed=10 totalMs=16000 maxMs=7000
expired t=120s accepted=10 active=0 completed=10 totalMs=16000 maxMs=0
```

### 6.5. Đọc từng bằng chứng

**Ở giây 5:** ứng dụng đã nhận 4 tác vụ, nhưng mới có 3 lần kết thúc được ghi vào Timer. Gauge thấy 1 tác vụ còn chạy. Đỉnh 4 tác vụ tại giây 1 không xuất hiện như một điểm Gauge đã thu.

**Ở giây 10:** cả 4 tác vụ đã xong. Timer có `3 × 1 + 7 = 10` giây, tức `10000` ms. Một mẫu dài 7 giây đã được ghi ở giây 8, giữa hai lần thu.

**Ở giây 20:** Counter vẫn chứa thêm đủ 6 tác vụ được nhận ở giây 12; Timer chứa thêm 6 lần kết thúc với tổng 6 giây. Vì thế count=10, tổng thời gian=16 giây. Không cần phải scrape ngay tại từng sự kiện để chúng đóng góp vào các giá trị tích lũy này.

**Gauge ở giây 10 và 20 đều bằng 0:** sáu tác vụ từng chạy ở khoảng giây 12–13 không thể được tái dựng chỉ từ hai giá trị Gauge đó. Việc Counter/Timer giữ lượng tích lũy không làm Gauge tự có lịch sử trung gian.

**Dòng repeat:** đọc lại ngay không làm Counter hoặc count/sum của Timer tích lũy về 0. Không coi endpoint Prometheus là một hàng đợi mà “đọc xong thì xóa”.

**Ở giây 120:** count và sum vẫn còn, nhưng max=0 do cửa sổ thống kê cũ hết hạn. Thay đổi này không cần một tác vụ mới để tạo ra.

Ví dụ dùng một luồng và cùng một đối tượng registry để dễ giải thích. Trong ứng dụng nhiều luồng, một lần thu nhiều meter không phải giao dịch chụp đồng thời toàn bộ trạng thái nghiệp vụ. Một tác vụ có thể thay đổi giữa lúc các giá trị khác nhau đang được đọc.

## 7. Bỏ lỡ một lần thu: điều gì mất, điều gì chưa chắc mất?

Cần phân biệt theo loại dữ liệu và vòng đời.

### 7.1. Counter tích lũy có thể giữ mức tăng qua khoảng trống

Trong ví dụ, bỏ lần thu tại giây 15 nhưng lần thu tại giây 20 vẫn thấy Counter tăng từ 4 lên 10. Điều này đúng vì:

- Cùng tiến trình/registry vẫn tồn tại.
- Các sự kiện đã thực sự được ghi.
- Counter xuất dạng tích lũy.
- Chuỗi dữ liệu đang so sánh thuộc đúng cùng danh tính.
- Lần thu sau vẫn thành công.

Ta biết tăng 6 trong khoảng giữa hai điểm, nhưng mất độ chi tiết về thời điểm tăng. Không suy ra Counter đã tăng đều 0,6 mỗi giây chỉ vì `(10 - 4) / (20 - 10) = 0,6`.

### 7.2. Khởi động lại làm mất giả định “cùng số tích lũy”

Nếu tiến trình ghi thêm dữ liệu rồi dừng trước khi bên thu đọc được, trạng thái trong bộ nhớ có thể mất. Lần khởi động mới có số đếm mới; việc đọc Counter lần sau không khôi phục phần chưa thu của tiến trình cũ.

Hàm truy vấn có thể xử lý **reset được thể hiện trong các mẫu quan sát**, nhưng không thể tái tạo một số tăng không có trong bất kỳ dữ liệu nào đã thu được.

Vì vậy, metrics không phải nhật ký bền vững của mọi giao dịch. Khi cần đối soát chính xác từng hành động, cần dữ liệu nghiệp vụ hoặc cơ chế ghi lịch sử phù hợp.

### 7.3. Gauge, cửa sổ thống kê và step có giới hạn riêng

Một đợt tăng Gauge nằm trọn giữa hai lần đọc có thể không để lại dấu vết. Một max đã hết hạn trước khi được đọc cũng có thể không còn xuất hiện.

Với registry tổng hợp theo step, phải biết khoảng nào được xuất và cách xử lý lần xuất thất bại. Không áp dụng kết luận “đọc sau sẽ có đủ mức tăng tích lũy” cho mọi loại exporter.

Khoảng trống dữ liệu vì scrape lỗi cũng khác với một mẫu có giá trị 0. Không tùy tiện điền mọi điểm thiếu bằng 0 rồi kết luận hệ thống nhàn rỗi.

## 8. Cửa sổ truy vấn không thể tạo lại thông tin chưa từng được thu

### 8.1. Tốc độ Counter là phép tính trên các điểm đã lưu

Ví dụ truy vấn PromQL cho Counter trong chương trình:

```promql
rate(lab_jobs_accepted_total[5m])
```

Đây là truy vấn minh họa khi các chỉ số đã được một Prometheus server thu và lưu. Chương trình console không thực thi PromQL.

Cửa sổ `[5m]` là khoảng dữ liệu dùng để tính tại mỗi thời điểm đánh giá. Nó không đặt chu kỳ ứng dụng tăng Counter và cũng không đặt lịch scrape.

Prometheus `rate` tính tốc độ trung bình mỗi giây, có xử lý reset và ngoại suy tới biên cửa sổ. Vì vậy, kết quả thực tế có thể khác phép chia hai điểm minh họa, nhất là khi có khoảng trống hoặc biên thời gian lệch. Với nhiều bản sao, cần tính rate cho từng chuỗi rồi tổng hợp để giữ khả năng xử lý reset. Xem [Prometheus: rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

Cửa sổ quá ngắn có thể không có đủ mẫu để tính. Cửa sổ dài hơn làm kết quả ổn định hơn nhưng cũng có thể làm một đợt tăng ngắn trông ít nổi bật hơn.

### 8.2. max_over_time của Gauge chỉ lấy max trong dữ liệu đã thu

Ví dụ:

```promql
max_over_time(lab_jobs_active[5m])
```

Hàm này xem các mẫu Gauge đã được lưu trong khoảng, không quay lại ứng dụng để tìm những trạng thái chưa từng được thu.

Nếu toàn bộ dữ liệu Gauge được lưu chỉ là 0, cực đại của chúng vẫn là 0 dù giữa hai lần thu từng có 40 tác vụ. Đổi biểu thức dashboard không khôi phục đỉnh bị bỏ qua. Xem [Prometheus: aggregation over time](https://prometheus.io/docs/prometheus/latest/querying/functions/#aggregation_over_time).

Cần tách ba câu hỏi:

- Cực đại của **các giá trị Gauge được thu** là bao nhiêu?
- Cực đại của **trạng thái thực tế** trong khoảng là bao nhiêu?
- Có bao nhiêu lần **vượt ngưỡng**?

Chúng có thể cần ba cách thu thập hoặc tổng hợp khác nhau.

### 8.3. Histogram lưu thông tin phân bố, không biến scrape thành log

Histogram có thể tích lũy số mẫu vào các bucket ở nguồn để nhiều phép đo giữa hai lần thu vẫn đóng góp vào phân bố. Nhưng nó không giữ danh sách đầy đủ timestamp và chi tiết của từng sự kiện.

Cần chọn kiểu đo theo thông tin muốn giữ. Không kỳ vọng chỉ tăng tốc độ scrape sẽ thay thế histogram, hoặc chỉ bật histogram sẽ ghi lại mọi biến động của một Gauge chưa được đo theo cách đó.

## 9. Cấu hình đúng thành phần sở hữu lịch thu thập

Trong một ứng dụng Spring Boot có web, Actuator và registry Prometheus, cấu hình expose có thể gồm:

```properties
management.endpoints.web.exposure.include=health,prometheus
```

Đây là cấu hình tích hợp minh họa cho ứng dụng đã có các phụ thuộc và quyền truy cập phù hợp, không phải toàn bộ ứng dụng của phần thực hành. Việc expose endpoint và việc bên thu có gọi endpoint hay không là hai việc riêng.

Một cấu hình Prometheus tối thiểu minh họa khi ứng dụng chạy trên cùng máy ở cổng 8080:

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 5s
  evaluation_interval: 15s

scrape_configs:
  - job_name: java-learning
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['127.0.0.1:8080']
```

Ý nghĩa:

- `scrape_interval`: lịch thu thập mục tiêu.
- `scrape_timeout`: thời gian chờ tối đa cho một lần thu; không được lớn hơn interval tương ứng.
- `evaluation_interval`: lịch đánh giá quy tắc của Prometheus.
- Chu kỳ làm mới dashboard vẫn được cấu hình riêng ở giao diện.
- Cửa sổ của một truy vấn như `[5m]` vẫn nằm trong biểu thức truy vấn.

Địa chỉ `127.0.0.1` ở đây là từ góc nhìn của tiến trình Prometheus. Nếu Prometheus chạy trong container hoặc máy khác, cần chọn địa chỉ ứng dụng thực sự truy cập được từ đó.

Những cấu hình trên không được chương trình console tự áp dụng. Chúng minh họa trách nhiệm của từng lớp. Đường truy cập metrics trong môi trường vận hành cần được cấu hình quyền và mạng theo hệ thống, thay vì chỉ mở endpoint rồi cho rằng đã có dữ liệu ở backend. Xem [Prometheus: Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

## 10. Chọn chu kỳ thu theo tín hiệu, độ trễ và chi phí

Không có một interval duy nhất tốt cho mọi hệ thống. Cần xét:

1. **Tín hiệu cần giữ:** muốn tổng số sự kiện, một trạng thái tức thời, phân bố thời gian hay số lần vượt ngưỡng?
2. **Thời gian biến động:** tín hiệu kéo dài vài phút hay chỉ vài trăm mili giây?
3. **Độ trễ quan sát:** chấp nhận chờ bao lâu trước khi biểu đồ hoặc cảnh báo phản ánh thay đổi?
4. **Chi phí thu:** số mục tiêu, số chuỗi thời gian, kích thước dữ liệu và thời gian đáp ứng của endpoint.
5. **Quy tắc tổng hợp:** dữ liệu tích lũy, theo step, cửa sổ max và histogram có tương thích với mục tiêu đọc không?

Với đường pull, độ trễ hiển thị thường gồm thời gian đợi lần scrape tiếp theo, thời gian xử lý/lưu dữ liệu và thời gian đợi truy vấn/làm mới giao diện. Cảnh báo còn có lịch đánh giá và điều kiện phải duy trì trong một khoảng nếu được cấu hình.

Không lấy interval làm bảo đảm tuyệt đối: lịch thực tế có thể lệch, request có thể chậm hoặc thất bại. Cần quan sát chính sức khỏe đường thu thập.

Các hướng xử lý nên gắn với nguyên nhân:

| Nhu cầu hoặc hiện tượng | Điều cần xem xét |
| --- | --- |
| Cần tổng sự kiện dù chúng đến nhanh | Ghi Counter/Timer/Summary ở đúng nguồn và hiểu cách tích lũy |
| Cần thấy đợt tăng trạng thái rất ngắn | Tăng tần suất nếu chi phí cho phép; cân nhắc phép đo giữ đỉnh hoặc lần vượt ngưỡng tại nguồn |
| Tác vụ đang treo nhưng Timer chưa đổi | Quan sát tác vụ đang chạy; không chỉ nhìn mẫu đã kết thúc |
| Biểu đồ phản hồi chậm | Kiểm tra scrape, lưu dữ liệu, truy vấn, refresh và quy tắc cảnh báo |
| Counter vẫn tăng nhưng đường tốc độ ít biến động | Xem cửa sổ tính và cách ngoại suy/tổng hợp |
| Xuất dữ liệu bị bỏ lỡ | Kiểm tra exporter, kết nối, reset tiến trình và ngữ nghĩa step/tích lũy |
| max về 0 sau khoảng im lặng | Kiểm tra expiry và buffer của thống kê |

Thu nhanh hơn giúp tăng độ phân giải của một số tín hiệu nhưng không sửa được vị trí mã đo sai, meter sai loại, đối tượng Gauge bị thu gom hoặc tác vụ chưa gọi đường kết thúc.

## 11. Quy trình kiểm chứng khi số liệu không giống kỳ vọng

Đi từ ứng dụng ra ngoài, tránh bắt đầu bằng việc đổi mọi interval:

1. **Xác nhận mã đo có chạy:** sự kiện nào gọi increment/record; đường lỗi hoặc hủy có bỏ qua cập nhật không?
2. **Xác nhận biên thời gian:** Timer ghi lúc bắt đầu hay kết thúc; công việc bất đồng bộ đã thực sự hoàn tất chưa?
3. **Xem nội dung xuất trực tiếp:** đúng tên meter, tag, đơn vị và giá trị tại thời điểm đọc chưa?
4. **Kiểm tra lịch thu thực tế:** mục tiêu có được gọi, có timeout/lỗi hoặc khoảng trống không?
5. **Kiểm tra vòng đời chuỗi:** tiến trình có restart, nhãn instance có đổi, meter có đăng ký lại khác danh tính không?
6. **Đọc biểu thức truy vấn:** đang xem số tích lũy, rate, max của mẫu hay một thống kê theo cửa sổ?
7. **Kiểm tra cách hiển thị:** bước truy vấn, phép tổng hợp, xử lý điểm thiếu và refresh có che khuất dữ liệu không?

Khi đọc trực tiếp nhiều meter, không mặc định mọi giá trị là một ảnh chụp nguyên tử của hệ thống. Việc cập nhật nghiệp vụ và thu thập chạy đồng thời có thể tạo chênh lệch nhỏ ở biên; cần phân biệt điều đó với sai khác kéo dài do thiết kế đo.

Nếu cần tái hiện lỗi, tạo dữ liệu và mốc thời gian cố định như ví dụ. Đừng chỉ dựa vào `sleep` gần biên scrape rồi kỳ vọng kết quả giống hệt trên mọi máy.

## 12. Tự kiểm tra

**Bài tập 1:** Một Gauge tăng từ 0 lên 100 rồi về 0 giữa hai lần scrape đều bằng 0. Sau đó dùng `max_over_time` có khôi phục được 100 không?

**Đáp án:** không nếu không có mẫu nào đã lưu giá trị đó. Hàm truy vấn chỉ tổng hợp dữ liệu đã thu. Muốn biết đỉnh thực tế, cần cách đo/giữ thông tin phù hợp tại nguồn.

**Bài tập 2:** Một Counter tích lũy tăng thêm 25 giữa hai lần scrape. Không có restart và lần đọc sau vẫn thành công. Có bắt buộc mất 25 sự kiện vì không scrape đúng thời điểm chúng xảy ra không?

**Đáp án:** không. Giá trị sau có thể vẫn chứa toàn bộ lượng tăng. Tuy nhiên, hai điểm đọc không cho biết thời điểm của từng sự kiện.

**Bài tập 3:** Tác vụ bắt đầu ở giây 1, kết thúc ở giây 31; scrape ở giây 15 và 30. Timer có bắt buộc thể hiện thời gian của nó ở hai lần scrape này không?

**Đáp án:** không. Khi dùng sample được dừng ở lúc kết thúc, mẫu 30 giây chỉ được ghi ở giây 31. Muốn quan sát trước đó cần đo công việc đang chạy.

**Bài tập 4:** Dashboard refresh mỗi giây nhưng Prometheus scrape mỗi 30 giây. Vì sao nhiều lần làm mới có thể không thấy dữ liệu nguồn mới?

**Đáp án:** lịch giao diện độc lập với lịch thu. Chạy lại truy vấn không làm xuất hiện thêm mẫu chưa được backend thu.

**Bài tập 5:** Counter trong bộ nhớ tăng, sau đó tiến trình chết trước lần scrape kế tiếp. Hàm `rate` có khôi phục chính xác phần tăng chưa từng được thu không?

**Đáp án:** không. Xử lý reset giúp diễn giải các điểm đã thấy, không tạo lại thông tin chưa có trong dữ liệu quan sát.

**Bài tập 6:** Trong ví dụ, tại sao `completed=10` và `totalMs=16000` vẫn còn ở giây 120 nhưng `maxMs=0`?

**Đáp án:** count/sum của Timer trong registry này tích lũy các mẫu đã ghi; max dùng cửa sổ thống kê và các mẫu cực đại cũ đã hết hạn.

Để giải thích một điểm trên biểu đồ, cần trả lời được ba câu: ứng dụng đã đo điều gì, thông tin nào được giữ giữa các lần đọc, và bên giám sát thực sự quan sát nó lúc nào. Những câu trả lời đó quyết định giới hạn của kết luận, trước cả việc chọn một truy vấn đẹp hay một tần suất làm mới cao.
