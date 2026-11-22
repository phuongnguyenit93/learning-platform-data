# Theo dõi tiến trình, CPU, thời gian hoạt động và tệp đang mở

## 1. Xác định đúng thứ đang được quan sát

Khi ứng dụng chậm hoặc không nhận thêm kết nối, một ảnh chụp heap chưa đủ để giải thích. Cần biết tiến trình JVM đang dùng CPU thế nào, đã chạy bao lâu, môi trường có bao nhiêu bộ xử lý khả dụng và tiến trình còn dư địa về bộ mô tả tệp hay không.

Có ba ranh giới cần phân biệt:

- **Tiến trình JVM:** gồm luồng nghiệp vụ và các luồng nội bộ của JVM; không chỉ một request hoặc một controller.
- **Môi trường vận hành mà JVM nhìn thấy:** có thể là máy vật lý, máy ảo hoặc môi trường container; không mặc định mọi giá trị “system” đều bao quát toàn bộ node vật lý.
- **Một instance cụ thể:** các chỉ số process thường thuộc một JVM. Không tự trở thành tổng số liệu của toàn cụm ứng dụng.

Trong Spring Boot Actuator, các binder metrics tích hợp nối thông tin quản lý của JVM/hệ điều hành vào Micrometer. Bài đối chiếu **Spring Boot 3.3.0, Micrometer 1.13.0 và Java 17+**; khả năng có dữ liệu còn phụ thuộc JDK, hệ điều hành, quyền và cấu hình chạy thực tế.

## 2. Bản đồ các chỉ số cần đọc

| Tên Micrometer | Statistic thường thấy trong phiên bản minh họa | Đơn vị/ngữ nghĩa | Phạm vi |
| --- | --- | --- | --- |
| `process.cpu.usage` | `VALUE` | Tỉ lệ sử dụng CPU gần đây, thường 0..1 khi hợp lệ | Tiến trình JVM |
| `system.cpu.usage` | `VALUE` | Tỉ lệ CPU gần đây của môi trường vận hành | Môi trường mà MXBean cung cấp |
| `system.cpu.count` | `VALUE` | Số bộ xử lý khả dụng cho JVM | Góc nhìn của JVM |
| `process.cpu.time` | `COUNT` | Thời gian CPU tích lũy; binder 1.13.0 đặt đơn vị `ns` | Tiến trình JVM |
| `system.load.average.1m` | `VALUE` | Mức tải trung bình một phút; không phải tỉ lệ phần trăm | Phụ thuộc hệ điều hành/JVM |
| `process.uptime` | `VALUE` | Thời gian từ lúc JVM khởi động | Tiến trình JVM |
| `process.start.time` | `VALUE` | Thời điểm JVM khởi động tính từ Unix epoch | Tiến trình JVM |
| `process.files.open` | `VALUE` | Số file descriptor đang mở | Tiến trình, khi nền tảng hỗ trợ |
| `process.files.max` | `VALUE` | Giới hạn số file descriptor được MXBean báo cáo | Tiến trình, khi nền tảng hỗ trợ |

Trong `SimpleMeterRegistry` dùng ở thí nghiệm, hai chỉ số thời gian hoạt động/khởi động được đưa ra theo giây. Các registry/exporter có quy ước đơn vị riêng; luôn đọc `baseUnit` thay vì suy từ tên hoặc kích thước con số.

Đặc biệt, `process.files.max` chứa chữ `max` trong **tên chỉ số**, nhưng phép đo của nó là `VALUE`: giá trị giới hạn hiện tại được đọc từ nguồn. Nó không phải statistic `MAX` ghi nhớ số tệp mở cao nhất từng quan sát.

## 3. Hạ tầng tích hợp và cách truy vấn bằng Actuator

Trong Boot 3.3, `SystemMetricsAutoConfiguration` cung cấp các binder `UptimeMetrics`, `ProcessorMetrics`, `FileDescriptorMetrics` khi các điều kiện hạ tầng metrics phù hợp. Binder hiện diện không bảo đảm mọi phép đo đặc thù hệ điều hành đều được đăng ký.

Ứng dụng Boot thông thường không cần tự khai báo lại các binder này chỉ để đọc metrics tích hợp. Chương trình Java độc lập ở cuối bài gọi `bindTo()` thủ công vì nó không chạy hạ tầng tự cấu hình Boot. [SystemMetricsAutoConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/SystemMetricsAutoConfiguration.java).

### 3.1. Chuẩn bị ứng dụng web Boot

Trong dự án Boot web đã có `spring-boot-starter-web` và `spring-boot-starter-actuator`, đưa endpoint metrics ra HTTP, ví dụ cấu hình dùng trên máy cá nhân:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Nếu ứng dụng có cấu hình bảo mật, quyền truy cập endpoint vẫn theo cấu hình đó. Thay đúng cổng/base path khi dự án đã tùy chỉnh; không công khai toàn bộ Actuator chỉ để lấy các chỉ số này.

### 3.2. Khám phá tên trước khi đọc từng giá trị

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
```

Tìm các tên `process.*` và `system.*` thực tế, rồi mở chi tiết:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics/process.uptime
curl -s http://127.0.0.1:8080/actuator/metrics/process.start.time
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.usage
curl -s http://127.0.0.1:8080/actuator/metrics/system.cpu.usage
curl -s http://127.0.0.1:8080/actuator/metrics/system.cpu.count
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.time
```

Chỉ đọc thêm các metric load average/file descriptor nếu tên có trong danh sách. Trên PowerShell có alias `curl`, dùng `curl.exe` để chạy đúng các lệnh curl. Dùng `-i` khi cần phân biệt lỗi HTTP với nội dung dữ liệu.

Ví dụ JSON **minh họa**, không phải số đo cố định mà mọi lần chạy phải trả:

```json
{
  "name": "process.uptime",
  "baseUnit": "seconds",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 123.456
    }
  ],
  "availableTags": []
}
```

Đọc thành “JVM của instance đang được truy vấn đã chạy khoảng 123,456 giây”. Không đọc thành thời gian CPU, thời gian máy đã bật, hay thời gian toàn dịch vụ luôn sẵn sàng.

## 4. Đọc CPU đúng tỉ lệ và đúng phạm vi

### 4.1. process.cpu.usage khác system.cpu.usage

`process.cpu.usage` đọc mức sử dụng CPU gần đây của tiến trình JVM. Nó gồm cả luồng ứng dụng và các luồng nội bộ như GC/JIT, nên CPU cao không tự chỉ ra một phương thức nghiệp vụ nào là nguyên nhân.

`system.cpu.usage` nói về môi trường vận hành được nguồn MXBean báo cáo. Tùy JDK và cách triển khai, môi trường đó có thể là hệ điều hành gốc, môi trường ảo hóa hoặc container. Không tự xem nó là tổng CPU của toàn host trong mọi cấu hình. [OperatingSystemMXBean của JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html).

Khi giá trị hợp lệ theo hợp đồng nguồn là 0..1, `0.35` tương ứng khoảng 35%. Cần nhân 100 để trình bày phần trăm, nhưng không đổi đơn vị nguồn thành 35 ngay trong mọi truy vấn và rồi nhân lần nữa trên dashboard.

Đây là tỉ lệ “gần đây” theo cách hệ thống lấy mẫu, không phải giá trị CPU tức thời với độ phân giải tùy ý do người đọc chọn. Các lần đọc quá sát nhau có thể chưa cho thêm thông tin; một lần đọc khi vừa khởi động cũng chưa đủ để kết luận về tải ổn định.

### 4.2. CPU thấp theo tổng năng lực không loại trừ một lõi đang bận

`system.cpu.count` sử dụng số bộ xử lý khả dụng mà JVM báo cáo. Nó không phải số CPU vật lý/socket trên bo mạch và cũng không phải mức sử dụng CPU.

Nếu tiến trình được quan sát theo tổng năng lực 8 bộ xử lý và chỉ một luồng chạy CPU liên tục, mức sử dụng tiến trình có thể xấp xỉ 1/8 = 12,5%. Đây là ví dụ để hiểu chuẩn hóa, không phải kết quả chính xác bắt buộc của mọi lần lấy mẫu.

Một đoạn xử lý đơn luồng có thể đã chạm giới hạn của nó dù tỉ lệ CPU toàn tiến trình còn thấp. Cần kết hợp phân tích luồng/profiling và độ trễ; không kết luận “CPU còn 87,5% nên chương trình không thể bị nghẽn CPU”.

Trong container, kiểm tra thêm giới hạn/quota CPU, CPU mà JVM coi là khả dụng và dữ liệu throttling của nền tảng. Chỉ có `system.cpu.count` và một tỉ lệ CPU không đủ để suy ra toàn bộ cơ chế phân bổ tài nguyên. [Số bộ xử lý khả dụng trong MXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html).

### 4.3. Giá trị không có sẵn không bằng 0%

Nguồn quản lý có thể trả giá trị âm khi không có thông tin sử dụng CPU; Micrometer cũng có thể không đăng ký metric nếu không phát hiện được phương thức thích hợp, hoặc trả NaN khi đọc thất bại.

Phân biệt ba tình huống: **không có tên metric**, **có meter nhưng mẫu không hợp lệ/không khả dụng**, và **có mẫu hợp lệ bằng 0**. Không thay tất cả bằng 0 rồi công bố rằng tiến trình đang rảnh.

Khi so CPU process với system, cần cùng instance, khoảng thời gian và ý nghĩa mẫu. Các nguồn lấy mẫu không đồng thời có thể tạo ảnh chụp khó so sánh; không dùng một cặp số riêng lẻ làm bằng chứng đối soát tuyệt đối.

## 5. process.cpu.time: tổng thời gian CPU không phải uptime

Trong Micrometer **1.13.0**, `ProcessorMetrics` đăng ký `process.cpu.time` bằng `FunctionCounter`, với `baseUnit("ns")`. Phép đo có thể hiện dưới statistic `COUNT`, nhưng lượng đang đếm là **nano giây CPU**, không phải số request hay số lần gọi hàm. [Mã nguồn ProcessorMetrics 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/system/ProcessorMetrics.java).

Ví dụ `process.cpu.time = 4.000.000.000 ns` là 4 giây CPU tích lũy. Không đọc thành 4 tỷ giây và không coi việc có statistic COUNT là 4 tỷ sự kiện nghiệp vụ.

CPU time cộng thời gian CPU của các luồng trong tiến trình. Nhiều luồng có thể chạy đồng thời trên nhiều lõi, nên tổng CPU time có thể lớn hơn thời gian thực đã trôi qua. Ngược lại, JVM chờ I/O nhiều có thể có uptime lớn nhưng CPU time tăng chậm.

Có thể ước lượng số lõi CPU trung bình đã dùng từ hai ảnh chụp tương thích:

```text
số lõi CPU dùng trung bình
  ≈ chênh lệch CPU time (ns) / [chênh lệch thời gian thực (s) × 1.000.000.000]

Ví dụ:
  CPU time tăng 4.000.000.000 ns trong 2 giây thực
  => trung bình khoảng 2 lõi CPU
```

Nếu năng lực tham chiếu thực sự là 4 lõi theo cùng cách chuẩn hóa, con số đó tương ứng khoảng 50%. Tuy nhiên, không khẳng định công thức thủ công luôn khớp chính xác `process.cpu.usage`: khoảng lấy mẫu, giới hạn container và cách nguồn hệ điều hành tính toán có thể khác.

Chỉ lấy hiệu của cùng tiến trình qua cùng vòng đời, dùng đơn vị đã xác minh và loại bỏ mẫu không hợp lệ. Sau khi JVM khởi động lại, tổng CPU time không nối tiếp một cách đơn giản với tiến trình cũ.

## 6. Thời gian hoạt động và thời điểm khởi động

### 6.1. process.uptime là tuổi của JVM đang chạy

`process.uptime` bắt nguồn từ `RuntimeMXBean.getUptime()`. Nguồn Java trả mili giây; `UptimeMetrics` dùng `TimeGauge` để registry chuyển sang đơn vị phù hợp. Với SimpleMeterRegistry của ví dụ, giá trị được đưa ra theo giây. [UptimeMetrics 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/system/UptimeMetrics.java).

Uptime tăng không chứng minh API đang phục vụ được. Tiến trình có thể còn sống nhưng bị kẹt luồng, quá tải, không kết nối được phụ thuộc hoặc chưa sẵn sàng nhận lưu lượng. Cần dữ liệu health/readiness, kết quả request và độ trễ để đánh giá các câu hỏi đó.

Uptime thấp có thể do khởi động lại, triển khai instance mới hoặc đang đọc một instance khác. Một lần đọc qua bộ cân bằng tải không cho biết “uptime của cả dịch vụ”.

### 6.2. process.start.time là timestamp, không phải một khoảng thời gian

`process.start.time` bắt nguồn từ `RuntimeMXBean.getStartTime()`: thời điểm gần đúng JVM khởi động tính từ Unix epoch. Nguồn Java dùng mili giây, còn đầu ra TimeGauge phụ thuộc đơn vị registry. [RuntimeMXBean: uptime và start time](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html).

Ví dụ, nếu `baseUnit=seconds` và giá trị bằng 1.700.000.000, đó là một thời điểm, không phải JVM đã chạy 1,7 tỷ giây. Giá trị minh họa này tương ứng `2023-11-14T22:13:20Z`.

```java
double epochSeconds = 1_700_000_000.0;
java.time.Instant startedAt =
    java.time.Instant.ofEpochMilli((long) (epochSeconds * 1000));
System.out.println(startedAt);
// 2023-11-14T22:13:20Z
```

Đoạn trên chỉ minh họa chuyển đổi khi đã xác minh đơn vị là giây. Không nhân 1.000 thêm nếu dữ liệu nguồn vốn đã là mili giây. Khi trình bày cho người xem, chuyển múi giờ tường minh; hậu tố `Z` là UTC.

### 6.3. Kết hợp để nhận diện vòng đời

Theo dõi uptime cùng start time và định danh instance giúp nhận biết các lần tiến trình thay thế/khởi động lại. PID có thể hữu ích tại máy đang điều tra, nhưng PID có thể được tái sử dụng và còn phụ thuộc namespace của container; không dùng riêng PID làm định danh lịch sử toàn hệ thống.

JVM uptime không phải thời gian Spring hoàn tất khởi động: JVM đã tồn tại trước khi application context khởi tạo xong. Nó cũng không phải thời gian hoạt động của hệ điều hành.

## 7. system.load.average.1m không phải CPU phần trăm

Load average là một đại lượng tải khác với CPU usage. Nguồn MXBean mô tả mức trung bình một phút liên quan các thực thể có thể chạy đang chạy hoặc chờ bộ xử lý; ý nghĩa chi tiết phụ thuộc nền tảng. Không đổi `load=2.5` thành “CPU 250%”.

Cần đặt nó cạnh năng lực CPU khả dụng và các dấu hiệu chờ tài nguyên. Một mức tải lớn không tự cho biết luồng Java nào đang làm gì, và load average không thay thế CPU usage hoặc phân tích luồng.

Trong binder 1.13.0, metric này chỉ được đăng ký khi nguồn `getSystemLoadAverage()` trả một giá trị không âm ở lúc gắn binder. Trên nền tảng không hỗ trợ, chẳng hạn nhiều môi trường Windows, tên có thể vắng mặt. Đây không phải yêu cầu tạo một giá trị giả bằng 0 để đủ danh sách.

## 8. Tệp đang mở thực chất là file descriptor

### 8.1. Không chỉ là tệp văn bản trên đĩa

Ở hệ thống Unix, file descriptor là tay cầm số mà tiến trình dùng để làm việc với tài nguyên I/O. Ngoài tệp thường còn có socket, pipe và các đối tượng hệ điều hành khác. Một tài nguyên có thể có nhiều descriptor; không diễn giải count thành số tệp dữ liệu duy nhất.

Ví dụ, số descriptor tăng có thể liên quan kết nối mạng, log, thư viện mở tệp hoặc một nhánh xử lý chưa đóng tài nguyên. `process.files.open` chỉ cho số lượng, không trả danh sách đường dẫn hay trực tiếp chỉ ra nơi đang giữ chúng. [File descriptor trong /proc/pid/fd của Linux](https://www.man7.org/linux/man-pages/man5/proc_pid_fd.5.html).

### 8.2. open, max và tỉ lệ sử dụng

- `process.files.open` là số descriptor đang mở tại lúc nguồn được đọc.
- `process.files.max` là mức tối đa nguồn quản lý báo cáo, không phải đỉnh open từng xảy ra và không phải tổng dung lượng đĩa.
- Khi cả hai có dữ liệu hợp lệ và giới hạn có ý nghĩa, có thể tính `open / max` để xem phần giới hạn đã dùng.

```text
Ví dụ giả định:
  open = 800 descriptor
  max  = 1.000 descriptor
  tỉ lệ = 800 / 1.000 = 0,8 = 80%
```

Chỉ chia khi số liệu hữu hạn, open không âm và max lớn hơn 0. Nếu nguồn báo giới hạn rất lớn hoặc gần như không giới hạn, một tỉ lệ rất nhỏ có thể không giúp dự báo sự cố; cần xác minh cấu hình giới hạn và tốc độ tăng thực tế.

Không tự kẹp tỉ lệ về 100% để che mất trường hợp dữ liệu không đồng thời hoặc giới hạn thay đổi. Trước khi chọn ngưỡng cảnh báo, kiểm tra ý nghĩa nguồn, số tài nguyên còn dư, biến động theo tải và thời gian cần phản ứng.

Giới hạn descriptor là một loại giới hạn tài nguyên. Pool kết nối ứng dụng vẫn có thể hết trước khi toàn tiến trình gần chạm giới hạn descriptor; ngược lại, tăng pool có thể làm tăng áp lực descriptor.

### 8.3. Hỗ trợ nền tảng là điều kiện thật sự

`FileDescriptorMetrics` 1.13.0 tìm các phương thức phù hợp của Unix operating system MXBean. Nó chỉ đăng ký các gauge mà phương thức tương ứng khả dụng. [Mã nguồn FileDescriptorMetrics 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/system/FileDescriptorMetrics.java).

Vì vậy khi chuyển từ Linux sang Windows/JDK khác, `process.files.open` hoặc `process.files.max` có thể không xuất hiện. Không có metric không chứng minh đang mở 0 tệp, và cũng không chứng minh JVM hay Actuator đang hỏng. Đừng đồng nhất các metric này với bộ đếm Windows handles.

Ngay cả trên môi trường Unix, cần kiểm tra bean/phương thức, quyền và JDK thực tế. Hợp đồng Java cung cấp riêng các phương thức đếm open/max descriptor qua `UnixOperatingSystemMXBean`. [UnixOperatingSystemMXBean của JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html).

### 8.4. Đọc xu hướng thay vì kết luận rò rỉ từ một điểm

Số descriptor có thể tăng trong giai đoạn khởi tạo pool, mở thư viện hoặc tăng tải rồi ổn định. Tín hiệu cần điều tra là tăng kéo dài qua nhiều chu kỳ tải tương tự, không trở về mức nền hợp lý hoặc liên tục thu hẹp phần giới hạn còn lại.

Xu hướng đó là bằng chứng để điều tra, chưa tự chứng minh một chỗ rò rỉ cụ thể. Cần đối chiếu loại tài nguyên, đường giữ tham chiếu/kết nối và cách đóng tài nguyên. Khi viết mã tự sở hữu stream/channel, dùng cơ chế đóng phù hợp như try-with-resources; không cố tạo cạn descriptor để “xác nhận” trên hệ thống đang phục vụ.

## 9. Chương trình Java 17+ kiểm tra binder và đơn vị

Chương trình sau không khởi động web server. Nó gắn trực tiếp ba binder vào `SimpleMeterRegistry`, in dữ liệu của chính JVM đang chạy và kiểm tra statistic/đơn vị của những metric có mặt. Nó không tạo số liệu CPU cố định hay giả lập khả năng file descriptor cho nền tảng không hỗ trợ.

Tạo dự án Gradle có wrapper và JDK 17 khả dụng:

```text
process-metrics-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/ProcessMetricsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'process-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ProcessMetricsDemo'
}
```

Phiên bản được cố định để kiểm chứng API. Trong dự án Boot thực tế, giữ các phiên bản Micrometer theo cơ chế quản lý phụ thuộc tương thích của Boot.

`src/main/java/ProcessMetricsDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.binder.system.FileDescriptorMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.binder.system.UptimeMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class ProcessMetricsDemo {

    private record Expected(String name, Statistic statistic, String unit) {
    }

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            new ProcessorMetrics().bindTo(registry);
            new UptimeMetrics().bindTo(registry);
            new FileDescriptorMetrics().bindTo(registry);

            System.out.println("pid=" + ProcessHandle.current().pid());

            List<Expected> expected = List.of(
                new Expected("process.uptime", Statistic.VALUE, "seconds"),
                new Expected("process.start.time", Statistic.VALUE, "seconds"),
                new Expected("process.cpu.usage", Statistic.VALUE, null),
                new Expected("process.cpu.time", Statistic.COUNT, "ns"),
                new Expected("system.cpu.count", Statistic.VALUE, null),
                new Expected("system.cpu.usage", Statistic.VALUE, null),
                new Expected("system.load.average.1m", Statistic.VALUE, null),
                new Expected("process.files.open", Statistic.VALUE, "files"),
                new Expected("process.files.max", Statistic.VALUE, "files")
            );

            for (Expected item : expected) {
                inspect(registry, item);
            }

            requirePresent(registry, "process.uptime");
            requirePresent(registry, "process.start.time");
            requirePresent(registry, "system.cpu.count");

            double open = readOrNaN(registry, "process.files.open");
            double maximum = readOrNaN(registry, "process.files.max");
            double fraction = fileFraction(open, maximum);
            if (Double.isFinite(fraction)) {
                System.out.printf(Locale.ROOT,
                    "live.fdFraction=%.6f%n", fraction);
            }
            else {
                System.out.println("live.fdFraction=UNAVAILABLE");
            }

            System.out.printf(Locale.ROOT, "example.fdFraction=%.6f%n",
                fileFraction(800, 1000));
            System.out.println("example.invalidLimit="
                + Double.isNaN(fileFraction(800, 0)));
            System.out.println("CONTRACT_PASS");
        }
        finally {
            registry.close();
        }
    }

    private static void inspect(SimpleMeterRegistry registry, Expected expected) {
        Meter meter = registry.find(expected.name()).meter();
        if (meter == null) {
            System.out.println(expected.name() + "=UNAVAILABLE");
            return;
        }
        if (!Objects.equals(meter.getId().getBaseUnit(), expected.unit())) {
            throw new AssertionError("Unexpected unit for " + expected.name());
        }

        for (var sample : meter.measure()) {
            if (sample.getStatistic() != expected.statistic()) {
                throw new AssertionError(
                    "Unexpected statistic for " + expected.name());
            }
            System.out.printf(Locale.ROOT,
                "%s statistic=%s unit=%s value=%.6f%n",
                expected.name(), sample.getStatistic(),
                expected.unit() == null ? "none" : expected.unit(),
                sample.getValue());
        }
    }

    private static void requirePresent(SimpleMeterRegistry registry, String name) {
        if (registry.find(name).meter() == null) {
            throw new AssertionError("Expected baseline metric: " + name);
        }
    }

    private static double readOrNaN(SimpleMeterRegistry registry, String name) {
        Meter meter = registry.find(name).meter();
        if (meter != null) {
            for (var sample : meter.measure()) {
                return sample.getValue();
            }
        }
        return Double.NaN;
    }

    private static double fileFraction(double open, double maximum) {
        if (!Double.isFinite(open) || !Double.isFinite(maximum)
                || open < 0 || maximum <= 0) {
            return Double.NaN;
        }
        return open / maximum;
    }
}
```

Chạy tại thư mục dự án:

```bash
./gradlew -q run --console=plain
```

Trên Windows PowerShell dùng `.\gradlew.bat -q run --console=plain`. Gradle giải quyết phụ thuộc và chạy main. Nếu dùng `javac`/`java` trực tiếp, cần classpath có Micrometer cùng các phụ thuộc đã giải quyết ở cả hai bước.

### 9.1. Một kết quả đã kiểm chứng

Đây là **ảnh chụp thực của một lần chạy trên Windows/JDK 17**, không phải các giá trị mà máy khác hoặc lần chạy sau phải lặp lại. PID, thời điểm khởi động, số CPU và các mẫu CPU/uptime phụ thuộc môi trường:

```text
pid=65848
process.uptime statistic=VALUE unit=seconds value=0.097000
process.start.time statistic=VALUE unit=seconds value=1793885033.543000
process.cpu.usage statistic=VALUE unit=none value=0.036723
process.cpu.time statistic=COUNT unit=ns value=718750000.000000
system.cpu.count statistic=VALUE unit=none value=28.000000
system.cpu.usage statistic=VALUE unit=none value=0.179431
system.load.average.1m=UNAVAILABLE
process.files.open=UNAVAILABLE
process.files.max=UNAVAILABLE
live.fdFraction=UNAVAILABLE
example.fdFraction=0.800000
example.invalidLimit=true
CONTRACT_PASS
```

Các dòng `UNAVAILABLE` do chương trình in khi không có meter hoặc chưa tính được tỉ lệ hợp lệ; chúng không phải giá trị số mà Actuator tự thay vào JSON. `unit=none` nghĩa ID không đặt base unit; ý nghĩa tỉ lệ CPU vẫn được xác định bởi hợp đồng nguồn.

`process.cpu.time` có statistic COUNT và unit ns đúng với binder đã đối chiếu. Việc thời gian CPU của tiến trình có thể lớn hơn uptime trong một ảnh chụp không tự là lỗi: các luồng có thể tiêu thụ CPU đồng thời và các giá trị cũng được đọc ở những thời điểm khác nhau.

Các dòng bắt đầu bằng `example.` dùng số liệu giả định để kiểm tra phép chia, tách khỏi dòng `live.`. Chúng không khẳng định tiến trình thực đang dùng 800/1.000 descriptor.

`CONTRACT_PASS` cho biết các metric hiện diện đã khớp statistic/đơn vị được chương trình kiểm tra và ba metric nền `process.uptime`, `process.start.time`, `system.cpu.count` có mặt. Nó không phải kết luận hệ thống khỏe, CPU tối ưu hay mọi tùy chọn đều được nền tảng hỗ trợ.

### 9.2. Vì sao không gắn lại các binder này vào ứng dụng Boot một cách tùy tiện?

Ở chương trình độc lập, mã tự tạo registry nên gắn binder và đóng registry trong `finally`. Trong ứng dụng Boot, dùng registry/binder được quản lý theo cấu hình hiện hành; không thêm một registry mới trong service rồi chờ endpoint của Boot tự đọc nó.

Chương trình plain Java này cũng không tự công khai `/actuator/metrics`. Các lệnh HTTP ở đầu bài áp dụng cho ứng dụng web Boot đã cấu hình endpoint, còn chương trình này giúp kiểm chứng nguồn và các hợp đồng đo mà không cần cổng mạng.

## 10. Kết hợp các tín hiệu để đặt câu hỏi tiếp theo

| Tín hiệu quan sát được | Hướng điều tra có căn cứ | Chưa thể kết luận ngay |
| --- | --- | --- |
| CPU process cao kéo dài, độ trễ tăng | Xem luồng dùng CPU, GC/JIT, khối lượng công việc và profiling | Một controller cụ thể chắc chắn có vòng lặp vô hạn |
| CPU process thấp nhưng CPU môi trường cao | Kiểm tra cạnh tranh tài nguyên và phạm vi đo môi trường | JVM chắc chắn không chịu ảnh hưởng |
| Tỉ lệ CPU tổng thấp nhưng một luồng luôn bận | Kiểm tra giới hạn đơn luồng/khả năng song song | Toàn bộ đường xử lý còn nhiều năng lực sử dụng được |
| Uptime thấp hoặc start time thay đổi | Xác minh vòng đời instance, triển khai, restart và logs | Tiến trình cũ chắc chắn bị crash do lỗi ứng dụng |
| Open descriptor tăng qua nhiều đợt tải và gần giới hạn | Kiểm tra kết nối/tệp còn giữ, quy tắc đóng và giới hạn OS | Đã biết chính xác chỗ rò rỉ |
| File metrics hoặc load average vắng mặt | Kiểm tra nền tảng/JDK, khả năng binder và filters | Giá trị thực của đại lượng bằng 0 |

Các suy luận này cần chuỗi thời gian và ngữ cảnh. Một lần đọc endpoint cho ảnh chụp; muốn xem xu hướng, tương quan và cảnh báo phải có hệ thống thu thập/lưu lịch sử phù hợp.

Không cộng uptime của nhiều JVM thành “uptime dịch vụ”. Không lấy trung bình đơn giản CPU của các instance có năng lực CPU khác nhau rồi coi là mức sử dụng toàn cụm. Cũng không cộng phần trăm open/max của nhiều tiến trình để suy ra một phần trăm chung mà bỏ qua các giới hạn khác nhau.

## 11. Khi dữ liệu không như mong đợi

1. **Xác nhận đúng tên, instance, cổng và quyền truy cập.** Một HTTP 404 của tên chưa đăng ký khác lỗi không truy cập được endpoint danh sách.
2. **Kiểm tra registry và binder thực tế.** Đã có hạ tầng metrics, binder tương ứng, hay đang ghi/đọc hai registry riêng?
3. **Kiểm tra filters và cấu hình chấp nhận meter.** Công khai endpoint không vượt qua một filter đã từ chối tên metric.
4. **Đối chiếu khả năng JVM/hệ điều hành.** Đặc biệt với load average, CPU mở rộng và file descriptor.
5. **Đọc đơn vị/statistic trước khi biến đổi.** CPU time ns không phải giây, uptime không phải timestamp và COUNT không phải lúc nào là số sự kiện.
6. **Phân biệt dữ liệu vắng/không hợp lệ với 0.** Không tạo số 0 thay thế để làm biểu đồ trông đầy đủ.
7. **Đối chiếu cùng thời gian và vòng đời.** Restart, thay instance, thay giới hạn CPU/descriptor có thể đổi cách diễn giải.

Không vội thêm các tùy chọn mở quyền phản chiếu rộng hoặc tạo một gauge tự đọc thông tin hệ điều hành khác chỉ vì thiếu tên. Trước hết xem binder đã hỗ trợ giao diện nào và nguồn thông tin có thật sự tồn tại trên môi trường đang chạy hay không.

## 12. Tự kiểm tra

1. `process.cpu.usage=0.25` có cho phép nói JVM dùng đúng một phần tư một lõi không? Cần biết thêm điều gì về cách chuẩn hóa?
2. `process.cpu.time` tăng 6 tỷ ns trong 3 giây thực. Ước lượng số lõi trung bình được dùng và nêu điều kiện để so với một tỉ lệ CPU.
3. Cùng một phản hồi có `process.uptime` theo giây và `process.start.time` theo giây epoch. Giải thích vì sao hai con số có kích thước rất khác nhau.
4. Uptime tăng đều nhưng health/readiness báo không sẵn sàng. Vì sao các thông tin đó không mâu thuẫn?
5. Một máy Windows không có `process.files.open`. Cần phân biệt những tình huống nào trước khi ghi “0 tệp đang mở” lên dashboard?
6. Nếu open=900, max=1.000, tỉ lệ sử dụng là bao nhiêu? Nếu max=0 hoặc dữ liệu không hữu hạn thì phải xử lý thế nào?
7. Descriptor tăng sau khởi động rồi ổn định khác gì tăng đều qua nhiều chu kỳ tải? Nêu bằng chứng bổ sung cần để kết luận về một tài nguyên chưa được đóng.
8. Vì sao `process.files.max` thường có statistic VALUE, còn `process.cpu.time` có thể có statistic COUNT nhưng không phải bộ đếm request?

Đọc nhóm metrics này hiệu quả là giữ rõ **phạm vi tiến trình/môi trường, ý nghĩa thời gian, đơn vị và khả năng nền tảng**, rồi dùng các tín hiệu kết hợp để điều tra thay vì kết luận từ một con số.
