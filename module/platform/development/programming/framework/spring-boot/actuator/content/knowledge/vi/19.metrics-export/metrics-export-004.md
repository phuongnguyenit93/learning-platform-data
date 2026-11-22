## Cấu hình xuất metrics qua OTLP

Khi Collector là đầu mối tiếp nhận số liệu, ứng dụng Spring Boot có thể dùng bộ đăng ký OTLP của Micrometer để gửi metrics định kỳ. Mã nghiệp vụ tiếp tục ghi vào `MeterRegistry`. Bộ xuất đọc các số đo từ registry, đóng gói rồi gửi tới nơi nhận. Khi kiểm tra cấu hình, cần xác minh cả việc ứng dụng đã ghi số đo và việc Collector đã nhận đúng số đo đó.

### Chọn đúng bộ xuất và endpoint

Với Spring Boot 3.3 và Micrometer 1.13, thêm `spring-boot-starter-actuator` và `io.micrometer:micrometer-registry-otlp`. Dùng BOM của Spring Boot để quản lý phiên bản tương thích. Khi tự cấu hình được kích hoạt, Spring Boot tạo registry OTLP và áp dụng các thuộc tính dưới `management.otlp.metrics.export`. Bộ xuất metrics của ví dụ gửi `POST` qua **OTLP/HTTP**. Cổng thông dụng là `4318`, còn `/v1/metrics` là đường dẫn nhận metrics mặc định. Nếu Collector chỉ mở cổng OTLP/gRPC, cần bật receiver HTTP để dùng cấu hình này. Đường dẫn xuất trace và cấu hình gửi trace thuộc luồng riêng.

Lưu cấu hình sau vào `src/main/resources/application.yml` khi ứng dụng và Collector chạy trực tiếp trên cùng một máy.

```yaml
management:
  otlp:
    metrics:
      export:
        enabled: true
        url: http://127.0.0.1:4318/v1/metrics
        step: 15s
        aggregation-temporality: cumulative
        resource-attributes:
          "[service.name]": checkout-otlp-demo
```

| Thuộc tính | Vai trò |
| --- | --- |
| `enabled` | Bật bộ xuất OTLP khi thư viện tương ứng có trên classpath. Đặt `false` để tắt riêng luồng OTLP trong một môi trường. |
| `url` | Địa chỉ đầy đủ của endpoint nhận metrics, gồm giao thức, máy chủ, cổng nếu cần và đường dẫn. |
| `step` | Khoảng thời gian giữa các kỳ xuất. Giá trị mặc định trong Spring Boot 3.3.0 là một phút. Ví dụ dùng 15 giây để quan sát nhanh hơn. |
| `aggregation-temporality` | Chọn cách mô tả các đại lượng cộng dồn như Counter và Histogram qua các kỳ xuất. |
| `resource-attributes` | Thông tin nhận dạng nguồn dùng chung cho dữ liệu xuất, chẳng hạn `service.name`. Nhãn `channel` trong ví dụ là thuộc tính của điểm đo cụ thể. |
| `headers` | Header bổ sung theo hợp đồng của nơi nhận, chẳng hạn thông tin xác thực. |

Với `cumulative`, Counter trong cùng vòng đời tiến trình có thể xuất lần lượt `3` rồi `5` sau khi tăng thêm hai. Với `delta`, hai kỳ tách biệt tương ứng có thể mang mức tăng `3` rồi `2`. Các con số giả định mỗi lần tăng thuộc một kỳ riêng. Chọn cách tổng hợp mà nơi nhận và hệ thống truy vấn hỗ trợ. Khi tiến trình khởi động lại, bộ đếm có thể bắt đầu lại từ đầu. Khi mất một kỳ gửi, khả năng phục hồi còn tùy bộ xuất, đệm và chế độ tổng hợp.

### Chạy Collector thử nghiệm

Lưu tệp `otelcol.yaml` bên ngoài ứng dụng. Dùng một bản phân phối Collector có receiver `otlp` và exporter `debug`.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "127.0.0.1:4318"
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [debug]
```

```bash
otelcol validate --config=otelcol.yaml
otelcol --config=otelcol.yaml
```

Trong cấu hình này, receiver lắng nghe trên loopback và pipeline metrics đưa dữ liệu nhận được ra log chi tiết. `debug` cho phép quan sát dữ liệu ở Collector. Để truy vấn về sau, dùng một exporter đưa dữ liệu tới hệ thống lưu trữ metrics. Nếu chạy ở các container khác nhau, cấu hình receiver lắng nghe trên giao diện mạng thích hợp và đặt `url` theo DNS mà ứng dụng truy cập được. Loopback của ứng dụng không trỏ tới container Collector.

### Gửi một Counter dễ nhận biết

Ví dụ Java sau chạy với JDK 17 và Gradle 8.x. Đặt `rootProject.name = 'otlp-export-demo'` trong `settings.gradle`, rồi dùng `build.gradle` sau. Thư viện Jackson trên classpath phục vụ phần tự cấu hình Actuator của ứng dụng chạy dòng lệnh trong ví dụ.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
    runtimeOnly 'com.fasterxml.jackson.core:jackson-databind'
}
```

Lưu tệp Java tại `src/main/java/demo/otlp/OtlpExportDemo.java`.

```java
package demo.otlp;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;

@SpringBootApplication
public class OtlpExportDemo {
    public static void main(String[] args) throws InterruptedException {
        try (var context = new SpringApplicationBuilder(OtlpExportDemo.class)
                .web(WebApplicationType.NONE)
                .run(args)) {
            var registry = context.getBean(MeterRegistry.class);
            var counter = registry.counter("demo.checkout.completed", "channel", "web");
            long pauseMillis = 1000L * context.getEnvironment()
                    .getProperty("demo.pause-seconds", Long.class, 20L);

            counter.increment(3);
            System.out.println("recorded=" + counter.count());
            Thread.sleep(pauseMillis);

            counter.increment(2);
            System.out.println("recorded=" + counter.count());
            Thread.sleep(pauseMillis);
        }
    }
}
```

Khi Collector đang chạy, khởi động ứng dụng trong một cửa sổ lệnh khác.

```bash
gradle bootRun
```

Ngoài log khởi động của Spring Boot, chương trình in hai dòng sau cách nhau khoảng 20 giây.

```text
recorded=3.0
recorded=5.0
```

Các dòng đó xác nhận ứng dụng đã ghi số đo vào registry. Trong log Collector, tìm metric `demo.checkout.completed`, thuộc tính điểm đo `channel=web` và thuộc tính tài nguyên `service.name=checkout-otlp-demo`. Với cấu hình `cumulative`, mong đợi thấy điểm có giá trị 3 trong một kỳ và 5 ở kỳ sau khi lần tăng thứ hai đã xảy ra. So thời điểm nhận và giá trị thay vì đếm đúng hai dòng log. Bộ xuất có thể gửi trước khi ứng dụng tăng Counter lần đầu hoặc trong lúc giá trị giữ nguyên, tùy thời điểm khởi động. Ứng dụng chờ thêm sau mỗi lần tăng để có cơ hội xuất theo nhịp 15 giây.

### Đổi đích theo môi trường

Nếu đích triển khai yêu cầu Bearer token qua HTTPS, có thể đặt phần ghi đè trong `application-production.yml` rồi kích hoạt hồ sơ `production`. Đưa URL đầy đủ và token vào cấu hình môi trường triển khai.

```yaml
management:
  otlp:
    metrics:
      export:
        url: ${OTLP_METRICS_URL}
        headers:
          "[Authorization]": "Bearer ${OTLP_TOKEN}"
```

Cú pháp ngoặc vuông giữ nguyên khóa của bản đồ cấu hình, như `service.name` và `Authorization`. Nếu tên dịch vụ xuất ra khác dự kiến, kiểm tra thêm biến `OTEL_SERVICE_NAME` vì Micrometer 1.13 có thể dùng biến này để ghi đè `service.name`. Nếu nơi nhận quy định tên header hoặc cơ chế xác thực khác, dùng đúng hợp đồng của nơi nhận. Khi đặt chu kỳ ngắn hơn, kiểm tra số meter, khối lượng gửi và độ trễ của nơi nhận. `batch-size` giới hạn số meter trong một payload của registry. `connect-timeout` và `read-timeout` điều chỉnh thời gian chờ kết nối và đọc phản hồi.

### Khoanh vùng khi thiếu dữ liệu

| Dấu hiệu | Điểm kiểm tra |
| --- | --- |
| Counter đã tăng, Collector chưa nhận được | Kiểm tra thư viện OTLP có trên classpath lúc chạy, hồ sơ Spring đang dùng, `enabled` và thời gian đã trôi qua so với `step`. |
| Kết nối bị từ chối hoặc hết thời gian chờ | Kiểm tra địa chỉ lắng nghe, DNS và khả năng kết nối từ tiến trình ứng dụng. |
| Nhận HTTP 404 | Kiểm tra URL có đúng đường dẫn nhận metrics, thường là `/v1/metrics`, và proxy có chuyển đúng đường dẫn hay không. |
| Nhận HTTP 401 hoặc 403 | Kiểm tra phương thức xác thực, header và quyền ở đích. |
| Collector nhận được nhưng hệ thống lưu trữ chưa có | Kiểm tra pipeline `metrics`, lỗi hoặc điểm bị từ chối ở chặng sau, tên nguồn và khoảng thời gian truy vấn. |

Trong OTLP/HTTP, phản hồi HTTP 200 vẫn có thể kèm thông tin chấp nhận một phần. Khi chẩn đoán, đối chiếu số điểm đã nhận hoặc bị từ chối ở Collector với metric cụ thể. Tách việc xác nhận HTTP thành công khỏi việc xác nhận dữ liệu đã tới hệ thống lưu trữ.

### Tài liệu tham khảo

- [Spring Boot 3.3 Actuator — tự cấu hình metrics OTLP](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — cấu hình OTLP registry](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp)
- [OpenTelemetry Collector — receiver, exporter và pipeline](https://opentelemetry.io/docs/collector/configuration/)
- [OpenTelemetry — đặc tả OTLP/HTTP](https://opentelemetry.io/docs/specs/otlp/#otlphttp)