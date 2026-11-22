# Đo kích thước phân bố bằng DistributionSummary

## 1. Từ một kích thước riêng lẻ đến hình dạng của dữ liệu

Giả sử một dịch vụ tạo ra các thông điệp JSON. Có thông điệp chỉ vài trăm byte, có thông điệp tới hàng chục nghìn byte. Chỉ biết “đã tạo 10.000 thông điệp” chưa cho biết lượng dữ liệu phải truyền. Chỉ biết tổng số byte cũng chưa cho biết đa số thông điệp nhỏ hay một số ít thông điệp rất lớn.

**DistributionSummary của Micrometer ghi nhận một đại lượng không âm cho mỗi lần quan sát**, rồi tổng hợp các quan sát đó. Đại lượng thường là kích thước, số phần tử trong một lô hoặc một tỷ lệ đã xác định rõ ý nghĩa. Một lời gọi `record(500)` có thể có nghĩa “thông điệp này dài 500 byte”.

Bài này thuộc nhóm metrics tùy chỉnh trong Spring Boot Actuator. Mối liên hệ giữa các thành phần là:

```text
Nghiệp vụ xác định một lần quan sát
    -> DistributionSummary.record(kích_thước)
    -> MeterRegistry tổng hợp
    -> Actuator cho phép kiểm tra
    -> registry xuất dữ liệu sang hệ giám sát nếu được cấu hình
```

Micrometer cung cấp công cụ đo; ứng dụng quyết định đo cái gì và ở thời điểm nào; Actuator cung cấp cách tiếp cận số liệu trong ứng dụng Spring Boot. Tài liệu [Distribution Summaries của Micrometer](https://docs.micrometer.io/micrometer/reference/1.18/concepts/distribution-summaries.html) dùng kích thước phản hồi làm một trường hợp điển hình. Các ví dụ Java bên dưới kiểm chứng trên Micrometer 1.13.0, phù hợp thế hệ Spring Boot 3.3; không yêu cầu chuyển ứng dụng sang phiên bản mới hơn.

### Chọn đúng loại công cụ đo

| Câu hỏi cần trả lời | Công cụ phù hợp | Ý nghĩa của dữ liệu |
| --- | --- | --- |
| Đã xảy ra bao nhiêu sự kiện? | `Counter` | Số lần hoặc tổng lượng tăng dần |
| Hàng đợi hiện có bao nhiêu phần tử? | `Gauge` | Trạng thái được lấy mẫu ở thời điểm quan sát |
| Một thao tác mất bao lâu? | `Timer` | Phân bố thời lượng, với đơn vị thời gian |
| Mỗi thông điệp dài bao nhiêu byte? | `DistributionSummary` | Phân bố kích thước của từng thông điệp |
| Mỗi lô xử lý chứa bao nhiêu bản ghi? | `DistributionSummary` | Phân bố số phần tử của từng lô |

Ví dụ, ghi kích thước hàng đợi mỗi giây vào một summary sẽ tạo phân bố **các lần lấy mẫu**, không phải phân bố kích thước thông điệp. Điều đó chỉ đúng nếu đây chính là câu hỏi cần đo. Với thời lượng, dùng `Timer` để có cách xử lý đơn vị và tích hợp phù hợp.

## 2. Hiểu count, tổng lượng, trung bình và max

Với chuỗi quan sát `100, 500, 900, 0` byte:

| Thống kê Java | Kết quả | Cách đọc |
| --- | --- | --- |
| `count()` | `4` | Đã chấp nhận bốn quan sát |
| `totalAmount()` | `1500.0` | Tổng kích thước là 1.500 byte |
| `mean()` | `375.0` | Trung bình 375 byte trên một quan sát |
| `max()` | `900.0` ngay sau khi ghi | Quan sát lớn nhất còn được giữ trong cửa sổ max |

Công thức trung bình là:

```text
mean = totalAmount / count, khi count > 0
mean = 0, khi chưa có quan sát
```

Không nhầm `count` với tổng số byte. `record(500)` tăng số quan sát lên **một**, đồng thời cộng **500** vào tổng lượng.

Trong triển khai tích lũy, count và tổng lượng được cộng dồn trong vòng đời của meter; một số registry dùng cơ chế theo chu kỳ nên phải đọc theo ngữ nghĩa của registry thực tế. `max` lại có cửa sổ thời gian riêng, không mặc nhiên là “giá trị lớn nhất kể từ lúc ứng dụng khởi động”. Cách cộng count/tổng và ghi max của phiên bản dùng trong bài có thể đối chiếu tại [CumulativeDistributionSummary 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/cumulative/CumulativeDistributionSummary.java).

Summary giữ các thống kê tổng hợp và cấu trúc phân bố đã bật; nó không phải danh sách lưu nguyên từng kích thước để truy vấn lại. Vì vậy, từ count, tổng và max không thể dựng lại toàn bộ dữ liệu gốc.

### Giá trị nào được ghi nhận?

- **Số dương:** thêm một quan sát và lượng tương ứng.
- **Số 0:** vẫn là một quan sát hợp lệ; count tăng, tổng không tăng.
- **Số âm:** bị bỏ qua trong triển khai Micrometer được xét.
- **NaN hoặc vô cực:** cần chặn ở biên dữ liệu; không dùng chúng để biểu diễn “không biết kích thước”.

Trong Micrometer 1.13.0, điều kiện trước khi ghi là `amount >= 0`; điều này cũng khiến `NaN` không đi vào nhánh ghi, nhưng không bảo vệ ứng dụng trước số dương vô cực. Với dữ liệu `double` do tính toán, có thể kiểm tra `Double.isFinite(value) && value >= 0` trước khi gọi meter. Với kích thước mảng byte, giá trị `length` vốn là số nguyên không âm. Xem [AbstractDistributionSummary 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/AbstractDistributionSummary.java).

“Không có sự kiện” khác với “một sự kiện có kích thước bằng 0”. Không có sự kiện thì không gọi `record`; nếu cứ ghi 0 để lấp thời gian trống, trung bình sẽ bị kéo xuống vì mẫu số tăng.

## 3. Xác định chính xác một quan sát

Trước khi đặt tên meter, hãy viết một câu định nghĩa:

> Mỗi lần tạo thành công một payload JSON, ghi đúng một lần số byte của payload sau khi mã hóa UTF-8, trước khi nén.

Câu này xác định được:

1. **Đối tượng:** một payload JSON.
2. **Điểm ghi:** sau khi tạo thành công.
3. **Đơn vị:** byte.
4. **Ranh giới dữ liệu:** sau mã hóa, trước nén.
5. **Quy tắc đếm:** một payload tương ứng một lần gọi `record`.

Nếu cần đo dữ liệu sau nén, hãy đo mảng byte sau nén và dùng tên hoặc tập nhãn phân biệt rõ. Không trộn số byte trước nén và sau nén vào cùng một chuỗi.

Với văn bản, `String.length()` là số đơn vị mã UTF-16, không phải số byte truyền qua mạng. Ví dụ:

```java
byte[] encoded = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
summary.record(encoded.length);
```

Đây là đoạn tích hợp minh họa: `text` là nội dung đã có và `summary` là meter đã đăng ký. Nếu payload đã ở dạng `byte[]`, đọc `length` trực tiếp để tránh mã hóa thêm chỉ phục vụ đo lường.

Ngoài ra, “mỗi payload một mẫu” tạo trung bình theo payload. Nếu mỗi lô có số bản ghi khác nhau, trung bình kích thước lô không phải trung bình kích thước bản ghi. Phải xác định đúng mẫu số trước khi dùng kết quả để ra quyết định.

## 4. Thí nghiệm Java chạy độc lập

Thí nghiệm này kiểm tra được dữ liệu đầu vào, các bucket, scale và việc max hết hạn mà không cần chạy máy chủ HTTP. Nó dùng `SimpleMeterRegistry` cùng `MockClock` để kết quả không phụ thuộc thời gian chờ thật.

### Chuẩn bị dự án riêng

Dùng JDK 17 trở lên, khuyến nghị JDK 21. Tạo một dự án Gradle nhỏ riêng, có `build.gradle`:

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

application {
    mainClass = 'demo.DistributionSummaryDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

`settings.gradle`:

```groovy
rootProject.name = 'distribution-summary-demo'
```

Tệp `src/main/java/demo/DistributionSummaryDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.distribution.CountAtBucket;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.Locale;

public class DistributionSummaryDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            DistributionSummary sizes = DistributionSummary.builder("demo.payload.size")
                    .baseUnit("bytes")
                    .description("Payload size per accepted event")
                    .minimumExpectedValue(1.0)
                    .maximumExpectedValue(1000.0)
                    .serviceLevelObjectives(100, 500, 1000)
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(3)
                    .register(registry);

            for (double value : new double[] {100, 500, 900, 0, -5}) {
                sizes.record(value);
            }
            System.out.printf(Locale.ROOT,
                    "sizes: count=%d total=%.0f mean=%.2f max=%.0f%n",
                    sizes.count(), sizes.totalAmount(), sizes.mean(), sizes.max());

            for (CountAtBucket bucket : sizes.takeSnapshot().histogramCounts()) {
                System.out.printf(Locale.ROOT, "bucket <= %.0f: %.0f%n",
                        bucket.bucket(), bucket.count());
            }

            DistributionSummary ratio = DistributionSummary.builder("demo.fill.ratio")
                    .baseUnit("percent")
                    .scale(100)
                    .serviceLevelObjectives(70, 90, 100)
                    .register(registry);
            ratio.record(0.25);
            ratio.record(0.75);
            ratio.record(0.90);
            System.out.printf(Locale.ROOT,
                    "ratio: count=%d total=%.0f mean=%.2f max=%.0f%n",
                    ratio.count(), ratio.totalAmount(), ratio.mean(), ratio.max());

            DistributionSummary overflow = DistributionSummary.builder("demo.size.overflow")
                    .maximumExpectedValue(1000.0)
                    .register(registry);
            overflow.record(1500);
            System.out.printf(Locale.ROOT, "overflow: count=%d total=%.0f%n",
                    overflow.count(), overflow.totalAmount());

            clock.add(Duration.ofSeconds(31));
            System.out.printf(Locale.ROOT,
                    "after 31s: count=%d total=%.0f max=%.0f%n",
                    sizes.count(), sizes.totalAmount(), sizes.max());
        } finally {
            registry.close();
        }
    }
}
```

Chạy bằng Gradle đã cài, hoặc thay `gradle` bằng wrapper của dự án thí nghiệm nếu có:

```shell
gradle -q run
```

Cũng có thể biên dịch và chạy trực tiếp. Sau khi `gradle -q copyRuntimeDependencies` đưa các JAR phụ thuộc vào `build/runtime-libs`, dùng các lệnh sau trên Windows:

```shell
javac --release 17 -encoding UTF-8 -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/DistributionSummaryDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.DistributionSummaryDemo
```

Trên Linux/macOS, dùng dấu `:` thay dấu `;` ngăn hai thành phần classpath trong lệnh `java`.

### Stdout

```text
sizes: count=4 total=1500 mean=375.00 max=900
bucket <= 100: 2
bucket <= 500: 3
bucket <= 1000: 4
ratio: count=3 total=190 mean=63.33 max=90
overflow: count=1 total=1500
after 31s: count=4 total=1500 max=0
```

`Locale.ROOT` cố định dấu chấm thập phân. `MockClock.add(...)` chỉ dịch đồng hồ của registry thí nghiệm, không cho luồng ngủ 31 giây. `registry.close()` được gọi trong `finally` để đóng registry do chương trình tự tạo.

## 5. Đọc kết quả thí nghiệm

### 5.1. Vì sao nhập năm số nhưng count chỉ bằng bốn?

Mảng đầu vào chứa `100, 500, 900, 0, -5`. Bốn số không âm được ghi, còn `-5` bị bỏ qua:

```text
count = 4
total = 100 + 500 + 900 + 0 = 1500
mean  = 1500 / 4 = 375
```

Nếu quy tắc nghiệp vụ coi kích thước âm là lỗi, hãy phát hiện lỗi ngay khi tính kích thước. Summary bỏ qua số âm không có nghĩa là dữ liệu đầu vào đúng.

### 5.2. Bucket là số đếm tích lũy theo ngưỡng

`serviceLevelObjectives(100, 500, 1000)` tạo các ngưỡng cần quan sát. Bucket ở ngưỡng `b` trả lời: **có bao nhiêu mẫu có giá trị nhỏ hơn hoặc bằng b?**

| Ngưỡng | Các mẫu được tính | Số đếm |
| --- | --- | --- |
| `<= 100` | `0, 100` | `2` |
| `<= 500` | `0, 100, 500` | `3` |
| `<= 1000` | `0, 100, 500, 900` | `4` |

Không cộng `2 + 3 + 4` để tìm số mẫu vì cùng một mẫu xuất hiện ở nhiều bucket. Số mẫu trong khoảng `(100, 500]` là `3 - 2 = 1`.

Trong tập dữ liệu này:

```text
Tỷ lệ mẫu <= 500 byte = 3 / 4 = 75%
Tỷ lệ mẫu > 500 byte  = (4 - 3) / 4 = 25%
```

Tên API là “service level objectives” nhưng việc khai báo ngưỡng chỉ tạo dữ liệu quan sát. Nó không tự đặt điều kiện đạt 99%, không từ chối payload vượt ngưỡng và không tự gửi cảnh báo.

### 5.3. maximumExpectedValue không phải kiểm tra hợp lệ

Meter `demo.size.overflow` đặt giá trị kỳ vọng tối đa là 1.000 nhưng vẫn nhận mẫu 1.500, cho count bằng 1 và tổng bằng 1.500.

`minimumExpectedValue` và `maximumExpectedValue` chủ yếu giúp giới hạn miền bucket được sinh và chi phí cấu trúc phân bố. Chúng không thay cho điều kiện nghiệp vụ như “payload không được quá 1 MiB”. Nếu cần từ chối dữ liệu lớn, phải thực hiện điều kiện đó trong logic ứng dụng; cách phản ánh trường hợp bị từ chối vào metrics là một quyết định đo lường riêng.

Các phương thức builder và ngữ nghĩa đơn vị/ngưỡng có thể đối chiếu trong [DistributionSummary 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/DistributionSummary.java).

### 5.4. Vì sao max về 0 nhưng tổng vẫn là 1.500?

Trong chương trình đã đặt:

```text
expiry = 10 giây
bufferLength = 3
Thời gian để toàn bộ dữ liệu cũ hết hạn = expiry * bufferLength = 30 giây
```

Sau khi đồng hồ tiến 31 giây mà không có mẫu mới, dữ liệu max cũ đã hết hạn. Count và tổng của registry tích lũy vẫn còn, còn `max()` trả về 0.

Cơ chế dùng các vùng lưu xoay vòng; không nên diễn giải thành một cửa sổ trượt chính xác đến từng thời điểm của mỗi mẫu. Ví dụ chỉ chủ động đi quá thời gian hết hạn toàn bộ để kết quả rõ ràng. Có thể kiểm tra thuật toán tại [TimeWindowMax 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/distribution/TimeWindowMax.java).

Do đó, max bằng 0 sau một thời gian yên lặng không chứng minh rằng “trước đây mọi payload đều rỗng”. Muốn xem xu hướng lịch sử, cần dữ liệu đã được hệ giám sát thu thập qua thời gian.

## 6. Đơn vị và scale: ghi số gì thì phải đọc đúng số đó

`baseUnit("bytes")` mô tả đơn vị, không tự chuyển một giá trị KiB thành byte. Gọi `record(2)` với base unit là bytes có nghĩa ghi 2 byte, không phải 2 KiB.

`scale(k)` nhân **giá trị của từng mẫu** với `k` trước khi đưa vào thống kê. Ví dụ tỷ lệ đầu vào nằm trong khoảng `[0, 1]` và `scale(100)`:

```text
Giá trị đưa vào:       0.25, 0.75, 0.90
Giá trị được thống kê: 25,   75,   90
count = 3
total = 190
mean  = 63.333...
max   = 90
```

Các bucket `70, 90, 100` trong ví dụ được tính theo miền **sau scale**. Vì vậy, mẫu gốc `0.75` đi vào bucket `<= 90` và `<= 100`, không vào bucket `<= 70`.

Khi dùng `scale(100)`, hãy truyền `0.75` để biểu diễn 75%, không truyền 75 rồi nhân thêm thành 7.500. Các giá trị kỳ vọng và ngưỡng SLO cũng phải thống nhất với miền số đã scale.

Một phân bố các tỷ lệ trả lời “tỷ lệ của mỗi sự kiện như thế nào”. Nó không tự cho tỷ lệ gộp theo khối lượng. Ví dụ lô A đạt `1/1`, lô B đạt `0/99`: trung bình hai tỷ lệ là 50%, nhưng tỷ lệ thành công toàn bộ bản ghi là `1/100 = 1%`. Nếu cần tỷ lệ gộp, giữ tổng số thành công và tổng số được thử thay vì suy ra từ trung bình các tỷ lệ.

## 7. Tích hợp vào ứng dụng Spring Boot Actuator

Phần này là **các tệp tích hợp vào ứng dụng Spring Boot 3.3 đã có**, có lớp `@SpringBootApplication` trong package `demo` hoặc cấu hình quét được package đó. Không phải một ứng dụng Spring Boot hoàn chỉnh chỉ gồm hai lớp dưới đây.

### 7.1. Dùng MeterRegistry do Spring quản lý

Trong dự án Boot đã có cơ chế quản lý phiên bản phụ thuộc, thêm Actuator; thêm registry Prometheus khi cần xuất sang Prometheus:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Không chép phiên bản Micrometer 1.13.0 của thí nghiệm độc lập để ghi đè bộ phụ thuộc do ứng dụng Boot quản lý. Boot tự cấu hình registry theo các thư viện có trên classpath; xem [Metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

Tệp `PayloadMetrics.java`:

```java
package demo;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Objects;
import org.springframework.stereotype.Component;

@Component
public class PayloadMetrics {
    private final DistributionSummary payloadSizes;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSizes = DistributionSummary.builder("app.payload.size")
                .description("Encoded JSON payload size per successful event")
                .baseUnit("bytes")
                .tag("format", "json")
                .minimumExpectedValue(1.0)
                .maximumExpectedValue(1048576.0)
                .serviceLevelObjectives(1024, 16384, 65536)
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordEncodedPayload(byte[] payload) {
        Objects.requireNonNull(payload, "payload");
        payloadSizes.record(payload.length);
    }
}
```

Meter được đăng ký một lần khi bean được tạo, sau đó tái sử dụng. Trong luồng xử lý thật, gọi `recordEncodedPayload(encodedBytes)` tại điểm thành công đã định nghĩa. Không tự tạo `SimpleMeterRegistry` bên trong bean: registry đó sẽ tách khỏi registry mà Actuator đang quan sát.

Tag `format=json` là một giá trị hữu hạn. Không dùng ID thông điệp, ID người dùng hoặc nội dung payload làm tag.

### 7.2. Dữ liệu thử và kiểm tra endpoint

Để thử cục bộ với dữ liệu xác định, có thể tạm thêm cấu hình sau vào ứng dụng thí nghiệm:

```java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PayloadMetricsDemoConfig {
    @Bean
    ApplicationRunner seedPayloadMetrics(PayloadMetrics metrics) {
        return args -> {
            for (int size : new int[] {100, 500, 900, 0}) {
                metrics.recordEncodedPayload(new byte[size]);
            }
        };
    }
}
```

Bean này tạo đúng bốn mẫu trên mỗi lần khởi động. Khi gắn vào nghiệp vụ thật, bỏ phần tạo dữ liệu thử để số liệu chỉ phản ánh sự kiện thật.

Với ứng dụng web đang dùng port mặc định 8080, có thể mở các endpoint cần kiểm tra trong cấu hình cục bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Nếu chỉ dùng registry mặc định trong bộ nhớ, có thể bỏ phụ thuộc Prometheus và bỏ `prometheus` khỏi danh sách exposure. Địa chỉ, base path và yêu cầu xác thực tuân theo cấu hình của ứng dụng đang chạy.

Các yêu cầu kiểm tra:

```shell
curl "http://localhost:8080/actuator/metrics/app.payload.size?tag=format:json"
curl "http://localhost:8080/actuator/prometheus"
```

Với một tiến trình mới chỉ có bốn mẫu thử và chưa có mẫu nghiệp vụ khác:

- `COUNT` phải là 4.
- `TOTAL` phải là 1.500 byte.
- Max ngay sau khi ghi là 900 byte; giá trị đọc muộn có thể đã hết cửa sổ.
- Bucket 1.024 byte của dữ liệu xuất phải chứa cả bốn mẫu.

Đây là các điều kiện đối chiếu, không phải một bản JSON cố định của mọi registry. Endpoint `metrics` phục vụ chẩn đoán các thống kê được meter công bố; nó không mặc nhiên trả đầy đủ bucket hoặc p95. Muốn xem histogram Prometheus, kiểm tra endpoint `prometheus` cùng registry tương ứng.

Nếu lọc sai tag, dùng sai registry hoặc gọi endpoint trước khi bean/sự kiện đã tạo meter, kết quả không phản ánh điều đang cần đo. Khi có nhiều tập tag cùng tên, chọn đúng tag để tránh đọc số liệu tổng hợp ngoài ý muốn.

## 8. Histogram và percentile giải quyết hai câu hỏi khác nhau

**Bucket** cho biết số mẫu nằm dưới một ngưỡng đã biết, chẳng hạn “bao nhiêu payload không quá 64 KiB”. **Percentile**, còn gọi là phân vị, tìm ngưỡng tương ứng với một tỷ lệ mẫu, chẳng hạn “p95 của kích thước là bao nhiêu”.

p95 bằng 64 KiB được hiểu theo ước lượng phân bố: khoảng 95% quan sát có kích thước không vượt ngưỡng đó. Nó không có nghĩa 95% của tổng số byte nằm dưới 64 KiB, cũng không phải kích thước tối đa.

Có ba lựa chọn cấu hình liên quan:

| Cấu hình | Mục tiêu |
| --- | --- |
| `serviceLevelObjectives(...)` | Thêm các bucket tại ngưỡng nghiệp vụ cần kiểm tra |
| `publishPercentiles(0.50, 0.95)` | Tính phân vị gần đúng ở phía ứng dụng cho từng meter ID |
| `publishPercentileHistogram()` | Xuất histogram để hệ giám sát có hỗ trợ tính phân vị và gộp các phân bố tương thích |

Không cần bật cả ba chỉ để lấy count và tổng. Với Prometheus và nhu cầu gộp nhiều instance, histogram thường phù hợp hơn việc xuất p95 riêng từ từng instance. Không cộng hoặc lấy trung bình các p95 để ra p95 chung. Một bộ chỉ có vài bucket SLO vẫn đếm đúng tại các ngưỡng đó, nhưng có thể quá thưa để ước lượng p95 hữu ích. Xem [Histograms and Percentiles của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

Chi phí cần đánh giá theo số meter ID và số bucket/phân vị trên mỗi ID. Chẳng hạn 4 định dạng × 3 kết quả × 40 bucket tương ứng 480 chuỗi bucket trên mỗi instance trong mô hình xuất classic histogram, chưa tính count, tổng, max và các chuỗi khác. Nếu thêm một tag có hàng triệu giá trị, chi phí tăng rất nhanh.

Đặt giới hạn kỳ vọng hợp lý để không sinh quá nhiều bucket tự động. Giữ ranh giới bucket nhất quán giữa các instance cần gộp, và không dùng cấu hình histogram như bộ kiểm tra hợp lệ của dữ liệu.

## 9. Đọc dữ liệu Prometheus theo đúng tên và cửa sổ

Với naming convention mặc định, tên Micrometer `app.payload.size` và đơn vị `bytes` thường được xuất thành nhóm có tiền tố `app_payload_size_bytes`. Hãy xem tên thật ở endpoint trước khi viết truy vấn, nhất là khi ứng dụng đã tùy chỉnh naming convention. Quy tắc đặt tên và rủi ro số lượng giá trị tag được giải thích tại [Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Các truy vấn dưới đây áp dụng cho **classic histogram** đã được Prometheus thu thập, với các tên chuỗi như trong ví dụ.

Trung bình số byte trên mỗi payload trong 5 phút gần đây, gộp theo định dạng:

```promql
sum by (format) (rate(app_payload_size_bytes_sum[5m]))
/
sum by (format) (rate(app_payload_size_bytes_count[5m]))
```

Tổng tốc độ byte chia cho tổng tốc độ số mẫu cho trung bình có trọng số đúng giữa các instance. Không lấy trung bình đơn giản các `mean` của các instance có số mẫu khác nhau.

p95 kích thước, giữ nhãn ranh giới `le` khi gộp bucket:

```promql
histogram_quantile(
  0.95,
  sum by (format, le) (
    rate(app_payload_size_bytes_bucket[5m])
  )
)
```

Tỷ lệ payload không quá 65.536 byte trong cùng cửa sổ:

```promql
sum by (format) (
  rate(app_payload_size_bytes_bucket{le="65536.0"}[5m])
)
/
sum by (format) (
  rate(app_payload_size_bytes_count[5m])
)
```

Chuỗi nhãn `le` phải khớp chính xác dữ liệu xuất; nếu registry định dạng thành `65536` thì dùng giá trị đó. Bucket 65.536 có trong cấu hình `serviceLevelObjectives` của ví dụ. Không thêm bucket giả vào truy vấn khi cấu hình chưa xuất nó.

`rate` cần đủ dữ liệu scrape trong cửa sổ. Khi không có sự kiện, mẫu số có thể bằng 0 và tỷ lệ không xác định; quyết định cách hiển thị khoảng trống thay vì mặc nhiên coi là 0% hoặc 100%. Đặt giới hạn theo job/service thích hợp nếu cùng metric tồn tại ở nhiều ứng dụng.

Cách dùng rate của tổng/count và tính phân vị từ histogram có thể đối chiếu với [Histograms and summaries của Prometheus](https://prometheus.io/docs/practices/histograms/). Tên lớp Java `DistributionSummary` không buộc dữ liệu xuất phải luôn là kiểu `summary` của Prometheus; histogram được xuất theo cấu hình và registry.

## 10. Những lỗi dễ làm sai kết luận

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Count lớn hơn số payload thật | Ghi ở cả lớp gọi và lớp xử lý, hoặc mỗi lần retry đều được tính nhưng lại đọc như số payload duy nhất | Chốt rõ “mỗi lần thử” hay “mỗi payload thành công”, rồi ghi ở một điểm |
| Mean thấp bất thường | Ghi 0 vào những lúc không có sự kiện | Chỉ ghi khi có quan sát thật; giữ 0 khi sự kiện thật sự có kích thước 0 |
| Kích thước tiếng Việt sai | Dùng `String.length()` làm số byte | Đo mảng byte sau mã hóa |
| Một số quan sát biến mất | Giá trị đầu vào âm hoặc không hợp lệ | Kiểm tra cách tính và xử lý dữ liệu tại biên |
| Đổi max kỳ vọng nhưng payload lớn vẫn được cộng | Hiểu nhầm miền histogram là giới hạn nghiệp vụ | Kiểm tra hợp lệ bằng logic nghiệp vụ riêng |
| Max bằng 0 sau lúc nhàn rỗi | Mẫu max đã hết cửa sổ | Đọc cùng count, tổng, thời gian và lịch sử scrape |
| Có count/tổng nhưng không có p95 | Chưa bật phân vị/histogram phù hợp, hoặc đang nhìn sai endpoint | Kiểm tra cấu hình meter, registry và loại dữ liệu xuất |
| Actuator không thấy meter | Tự tạo registry riêng hoặc chưa tạo/ghi meter theo vòng đời dự kiến | Dùng registry được inject và kiểm tra điểm đăng ký |
| Tốn bộ nhớ hoặc tăng mạnh số chuỗi | Quá nhiều giá trị tag, bucket hoặc phân vị | Giới hạn tag, chọn miền kỳ vọng và cấu hình phân bố theo câu hỏi cần trả lời |

Cùng tên và cùng tập tag thường trả về meter đã đăng ký trong registry. Vì vậy, không gọi builder nhiều lần với cùng ID rồi mong những cấu hình scale/bucket khác nhau tự tạo các meter độc lập. Xác định đơn vị và cấu hình trước khi đăng ký, rồi giữ tham chiếu để dùng lại.

## 11. Thực hành tự kiểm chứng

1. **Thêm một mẫu 1.000 byte trước khi dịch MockClock trong thí nghiệm đầu.** Count phải là 5, tổng 2.500, mean 500 và max 1.000. Bucket 100/500/1000 lần lượt có số đếm 2/3/5.
2. **Không thêm mẫu mới, chỉ dịch MockClock.** Count và tổng của SimpleMeterRegistry tích lũy giữ nguyên; sau khi vượt toàn bộ thời gian lưu max, max về 0. Phân biệt “không có mẫu mới” với “có thêm mẫu 0”.
3. **Đổi câu hỏi đo từ kích thước payload sang kích thước lô.** Viết một câu xác định chính xác một quan sát, đơn vị và điểm ghi; giải thích vì sao `record(batch.size())` không cho biết từng bản ghi nặng bao nhiêu byte.
4. **Thiết kế ngưỡng cho payload.** Nếu mục tiêu là biết tỷ lệ payload không quá 64 KiB, đặt bucket 65.536 byte; giải thích vì sao chỉ nhìn mean không trả lời được tỷ lệ này.

Sau các bài thử, cần giải thích được vì sao count và tổng có mẫu số khác nhau, vì sao max có thể hết hạn độc lập, và cấu hình phân bố nào đủ để trả lời câu hỏi kích thước đang cần đo.
