# Chọn MeterRegistry phù hợp với hệ thống giám sát

Cùng một bộ đếm `orders.completed` có thể được Prometheus đọc qua HTTP, được gửi đến OpenTelemetry Collector hoặc chỉ được giữ trong bộ nhớ để kiểm thử. Mã nghiệp vụ ghi một lần vào API của Micrometer. Registry quyết định số đo được chuyển sang định dạng nào và đi đến đâu.

## Bắt đầu từ nơi nhận dữ liệu

Trước khi chọn dependency, xác định hệ thống nào sẽ lưu và truy vấn metrics, bên nào khởi tạo kết nối, và endpoint đó cần giao thức hay thông tin xác thực nào.

| Hạ tầng đang dùng | Registry Micrometer | Cách dữ liệu đi đến nơi nhận |
| --- | --- | --- |
| Prometheus thu thập từng bản sao ứng dụng | `micrometer-registry-prometheus` | Prometheus chủ động gọi endpoint `/actuator/prometheus` đã mở. Đây là mô hình kéo (pull). |
| OpenTelemetry Collector hoặc đầu nhận tương thích OTLP qua HTTP | `micrometer-registry-otlp` | Ứng dụng định kỳ gửi metrics tới URL OTLP HTTP, thường có đường dẫn `/v1/metrics`. Đây là mô hình đẩy (push). |
| Datadog nhận trực tiếp qua API metrics | `micrometer-registry-datadog` | Registry gửi metrics định kỳ tới Datadog API. Cấu hình API key và địa chỉ phù hợp với nơi lưu dữ liệu. |
| Kiểm thử hoặc xem số đo cục bộ | `SimpleMeterRegistry` | Số đo nằm trong bộ nhớ của tiến trình. Có thể đọc qua API Micrometer hoặc endpoint Actuator `metrics` khi được mở. |

Ví dụ, nếu Collector là đầu vào chung của hệ thống, dùng OTLP để ứng dụng gửi tới Collector rồi để Collector xử lý tuyến tới backend. Nếu nhóm vận hành đã thu thập từng bản sao bằng Prometheus, dùng registry Prometheus và giữ đích thu thập trong cấu hình Prometheus. Với một tiến trình chạy ngắn, xem lại khả năng thu thập trước khi tiến trình thoát, cả với chu kỳ scrape lẫn chu kỳ gửi định kỳ.

## Ghép dependency và cấu hình trong Spring Boot 3.3

Dùng `spring-boot-starter-actuator` và bộ quản lý phiên bản của Spring Boot. Các dòng Gradle dưới đây là **các lựa chọn** cho khối `dependencies`. Bật đồng thời khi thực sự cần xuất đến nhiều đích.

### Prometheus lấy dữ liệu

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
~~~

~~~properties
management.endpoints.web.exposure.include=health,prometheus
~~~

Spring Boot có thể tự cấu hình registry khi dependency có mặt lúc chạy. Việc mở endpoint cho phép Prometheus lấy số đo ở `/actuator/prometheus` nếu dùng đường dẫn quản lý mặc định. Kiểm tra Prometheus truy cập được cổng quản lý và cấu hình job thu thập đúng từng đích. `/actuator/metrics` phục vụ việc tra cứu số đo qua Actuator. Để scrape, dùng endpoint `prometheus`.

### OpenTelemetry Collector nhận metrics

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-otlp'
~~~

~~~properties
management.otlp.metrics.export.url=http://otel-collector:4318/v1/metrics
management.otlp.metrics.export.step=30s
~~~

Ví dụ giả định tên `otel-collector` phân giải được trong mạng ứng dụng và Collector đã bật đầu nhận OTLP HTTP cho pipeline metrics. `step` là chu kỳ xuất. Nếu đầu nhận yêu cầu xác thực, cấu hình tiêu đề tương ứng qua `management.otlp.metrics.export.headers.*` và cấp giá trị từ cấu hình bí mật của môi trường. Dùng URL HTTPS khi đầu nhận yêu cầu TLS. Khi đổi backend, kiểm tra cách biểu diễn số đo tích lũy (`cumulative`) hoặc mức tăng theo kỳ (`delta`) mà đầu nhận hỗ trợ.

### Datadog nhận trực tiếp qua API

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-datadog'
~~~

~~~properties
management.datadog.metrics.export.api-key=${DATADOG_API_KEY}
~~~

Cấp `DATADOG_API_KEY` cho tiến trình từ kho bí mật. Nếu dùng một site Datadog khác mặc định hoặc đi qua proxy, đặt `management.datadog.metrics.export.uri` theo địa chỉ của hạ tầng. Kiểm tra tại đúng site và đợi ít nhất một chu kỳ xuất trước khi kết luận dữ liệu chưa đến.

## Một lần ghi có thể đi qua nhiều registry

Ứng dụng nên nhận `MeterRegistry` qua hàm tạo và đăng ký `Counter`, `Timer` hoặc `Gauge` với đối tượng đó. Khi nhiều registry tự cấu hình cùng hoạt động, Spring Boot có thể cung cấp `CompositeMeterRegistry` để phân phối một lần ghi đến các registry con. Spring Boot dùng registry đơn giản trong bộ nhớ làm phương án dự phòng khi chưa có backend khác được cấu hình.

Khi chuyển hệ thống giám sát, có thể bật cả registry cũ lẫn mới trong giai đoạn đối chiếu. Nếu cả hai tuyến đổ dữ liệu vào cùng một kho, kiểm tra nguy cơ đếm trùng. Khi kết thúc chuyển đổi, có thể tắt registry cũ bằng cờ riêng. Ví dụ, `management.datadog.metrics.export.enabled=false` tắt registry Datadog do Spring Boot tự cấu hình. Nếu cấu hình nhiều profile với cùng một classpath, kiểm tra các cờ bật và tắt trong profile thực sự được nạp.

### Thử cơ chế phân phối bằng Java

Ví dụ độc lập dùng hai registry trong bộ nhớ để nhìn thấy kết quả của cùng một lần ghi. Tạo `build.gradle` trong thư mục thử:

~~~groovy
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
    mainClass = 'example.RegistryDemo'
}
~~~

Tạo `src/main/java/example/RegistryDemo.java`:

~~~java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class RegistryDemo {
    public static void main(String[] args) {
        var composite = new CompositeMeterRegistry();
        var first = new SimpleMeterRegistry();
        var second = new SimpleMeterRegistry();
        try {
            Counter completed = composite.counter("orders.completed");
            composite.add(first);
            completed.increment();

            composite.add(second);
            completed.increment();

            System.out.println("first=" + first.get("orders.completed").counter().count());
            System.out.println("second=" + second.get("orders.completed").counter().count());
        } finally {
            composite.close();
        }
    }
}
~~~

Với JDK 17 trở lên và Gradle tương thích, chạy `gradle -q run`. Kết quả:

~~~text
first=2.0
second=1.0
~~~

Registry thứ nhất có mặt ở cả hai lần tăng. Registry thứ hai có mặt từ lần tăng thứ hai. Khi thêm registry con, composite đăng ký các meter đã biết với registry mới. Các lần ghi trước đó chỉ tồn tại ở registry đã nhận chúng.

## Xác nhận ở nơi số đo sẽ được dùng

1. Tạo một hoạt động có thể lặp lại, chẳng hạn hoàn tất một đơn thử nghiệm để tăng bộ đếm đúng một lần.
2. Với Prometheus, tìm số đo tại endpoint rồi kiểm tra đích thu thập và truy vấn ở Prometheus. Với OTLP hoặc Datadog, kiểm tra đường gửi, chu kỳ xuất và dữ liệu tại Collector hoặc backend đích. Đọc được số đo cục bộ mới xác nhận bước ghi nhận.
3. Khi chuyển registry, đối chiếu tên số đo, đơn vị của timer, nhãn, ranh giới histogram và cách tính tốc độ tăng ở backend mới. Cùng một meter trong mã có thể xuất hiện với tên hoặc cách biểu diễn khác do quy ước của từng hệ thống.

### Tài liệu tham khảo

- [Spring Boot 3.3 – Tự cấu hình Micrometer và các registry](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 – Registry Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html)
- [Micrometer 1.13 – Registry OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html)