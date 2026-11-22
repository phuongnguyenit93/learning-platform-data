# Tích hợp registry cho Datadog, InfluxDB hoặc StatsD theo nhu cầu

Một ứng dụng Spring Boot có thể gửi cùng một số đo đến các hệ thống khác nhau mà vẫn dùng API Micrometer để ghi nhận. Phần cần thay theo môi trường là **registry**, địa chỉ nhận và cách xác thực. Với Datadog, trước hết cần phân biệt hai đường gửi. Ứng dụng có thể gọi API Datadog trực tiếp hoặc gửi gói StatsD đến Agent để Agent chuyển tiếp.

| Đích nhận của ứng dụng | Dependency Micrometer | Cách xuất |
| --- | --- | --- |
| Datadog Metrics API | `micrometer-registry-datadog` | Gửi định kỳ qua HTTPS đến site Datadog. |
| InfluxDB | `micrometer-registry-influx` | Gửi điểm dữ liệu định kỳ tới API ghi của InfluxDB. |
| StatsD daemon hoặc DogStatsD Agent | `micrometer-registry-statsd` | Gửi dòng dữ liệu theo biến thể giao thức mà bộ nhận hỗ trợ. Ví dụ dùng UDP. |

## Chuẩn bị Spring Boot 3.3

Dùng `spring-boot-starter-actuator`. Thêm dòng `runtimeOnly` của phương án đã chọn vào khối `dependencies` và để bộ quản lý phiên bản của Spring Boot chọn phiên bản Micrometer. Nếu một bản dựng cần mang nhiều registry để chạy ở các môi trường khác nhau, dùng profile để chọn registry hoạt động.

Với cách cấu hình bằng profile trong bài này, đặt phần chung trong `application.properties`:

~~~properties
management.defaults.metrics.export.enabled=false
management.metrics.tags.application=export-demo
~~~

Cờ đầu tắt mặc định các bộ xuất do Spring Boot tự cấu hình. Mỗi profile dưới đây bật riêng một bộ xuất bằng `enabled=true`. Nhãn `application` giúp lọc dữ liệu của ứng dụng ở đích. Kích hoạt một profile phù hợp, chẳng hạn đặt `SPRING_PROFILES_ACTIVE=metrics-influx` trong môi trường chạy khi chọn InfluxDB.

## 1. Datadog qua API

Dependency:

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-datadog'
~~~

Trong `application-metrics-datadog.properties`:

~~~properties
management.datadog.metrics.export.enabled=true
management.datadog.metrics.export.api-key=${DATADOG_API_KEY}
management.datadog.metrics.export.step=30s
~~~

Cấp `DATADOG_API_KEY` cho tiến trình từ kho bí mật. API key dùng để gửi metrics. Application key là tùy chọn để xuất thêm metadata của meter. Spring Boot mặc định dùng Datadog US. Nếu tài khoản dùng site khác hoặc ứng dụng phải gửi qua proxy nội bộ, cấu hình `management.datadog.metrics.export.uri` theo địa chỉ của môi trường.

Ứng dụng cần kết nối HTTPS ra endpoint đã chọn. Sau khi chạy, đợi chu kỳ xuất rồi tìm số đo tại site của tài khoản, theo khoảng thời gian và nhãn `application:export-demo`. Nếu có lỗi xác thực, kiểm tra API key có thuộc đúng site và môi trường hay không.

## 2. InfluxDB qua API ghi

Dependency:

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-influx'
~~~

Trong `application-metrics-influx.properties`, ví dụ với **InfluxDB v2**:

~~~properties
management.influx.metrics.export.enabled=true
management.influx.metrics.export.api-version=v2
management.influx.metrics.export.uri=https://influx.example.com:8086
management.influx.metrics.export.org=platform
management.influx.metrics.export.bucket=app-metrics
management.influx.metrics.export.token=${INFLUX_METRICS_TOKEN}
management.influx.metrics.export.step=30s
~~~

Thay URI, tổ chức và bucket bằng các giá trị triển khai. Bucket cần tồn tại và token cần có quyền ghi vào bucket đó. `uri` là địa chỉ máy chủ gốc trong ví dụ. Registry tự ghép đường dẫn API ghi theo phiên bản đã chọn. Kiểm tra dữ liệu ở đúng tổ chức, bucket và khoảng thời gian sau chu kỳ xuất.

Với **InfluxDB v1**, dùng `api-version=v1`, chọn cơ sở dữ liệu bằng `management.influx.metrics.export.db` và cấp `user-name` cùng `password` nếu máy chủ bật xác thực. Các thuộc tính `org`, `bucket` và `token` trong ví dụ thuộc cấu hình v2. Nếu cơ sở dữ liệu v1 do hạ tầng cấp sẵn, có thể đặt `management.influx.metrics.export.auto-create-db=false`.

## 3. StatsD hoặc DogStatsD qua Agent

Dependency:

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-statsd'
~~~

Trong `application-metrics-statsd.properties`, ví dụ Agent hỗ trợ **DogStatsD** qua UDP:

~~~properties
management.statsd.metrics.export.enabled=true
management.statsd.metrics.export.host=statsd-agent
management.statsd.metrics.export.port=8125
management.statsd.metrics.export.protocol=udp
management.statsd.metrics.export.flavor=datadog
~~~

`host` và `port` là nơi Agent nhận gói từ ứng dụng. `protocol` là cách vận chuyển, còn `flavor` quyết định cách định dạng dòng số đo và nhãn. Ví dụ dùng `datadog` vì bên nhận hiểu DogStatsD. Với daemon tương thích giao thức StatsD gốc của Etsy, chọn `flavor=etsy` và kiểm tra các khả năng của bên nhận, nhất là hỗ trợ nhãn.

Tên `statsd-agent` phải phân giải được từ tiến trình ứng dụng. Trong container, `localhost` trỏ vào chính container đó. Khi Agent ở nơi khác, dùng địa chỉ mà ứng dụng truy cập được và cấu hình Agent lắng nghe trên giao diện phù hợp. Với đường DogStatsD, thông tin xác thực để chuyển dữ liệu từ Agent lên Datadog thuộc cấu hình Agent.

UDP không có phản hồi xác nhận cho từng gói. Khi dữ liệu thiếu, kiểm tra bộ đếm hoặc nhật ký nhận gói của Agent, cổng UDP và cấu hình chuyển tiếp. Nếu cùng một meter được gửi đến cùng kho qua API Datadog và qua DogStatsD, kiểm tra trùng dữ liệu trước khi dùng kết quả để tính tổng.

## Kiểm tra bằng một số đo dễ nhận diện

Trong ứng dụng thử đã có Spring Boot Actuator, thêm `ExportProbe.java` vào package được Spring quét. Ví dụ dùng một gauge cố định để quan sát dữ liệu qua nhiều lần xuất. Trường `probeValue` giữ tham chiếu đến giá trị mà gauge đọc.

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ExportProbe {
    private final AtomicInteger probeValue = new AtomicInteger(7);

    public ExportProbe(MeterRegistry registry) {
        Gauge.builder("demo.export.probe", probeValue, AtomicInteger::get)
                .register(registry);
    }
}
~~~

1. Chạy ứng dụng với profile đã chọn. Trong môi trường thử có kiểm soát, nếu endpoint `metrics` được mở, gọi `GET /actuator/metrics/demo.export.probe` và kiểm tra phép đo `VALUE` bằng 7. Đây là bằng chứng ứng dụng đã đăng ký meter.
2. Kiểm tra đích nhận. Với Datadog hoặc InfluxDB, quan sát sau ít nhất một chu kỳ xuất. Với StatsD, kiểm tra Agent nhận rồi chuyển tiếp hoặc tổng hợp dòng gauge. Dùng nhãn ứng dụng ở những đích hỗ trợ nhãn và kiểm tra quy ước tên khi tìm số đo.
3. Nếu thấy giá trị 7 ở Actuator nhưng chưa thấy ở đích, khoanh vùng phần xuất theo profile, mạng, thông tin xác thực và lỗi của bộ nhận. Nếu thấy dữ liệu từ nhiều tuyến, kiểm tra profile và bộ xuất đang hoạt động.

### Tài liệu tham khảo

- [Spring Boot 3.3 – Registry Datadog, Influx và StatsD](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot 3.3 – Thuộc tính cấu hình registry](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [Micrometer 1.13 – Giao thức StatsD và biến thể định dạng](https://docs.micrometer.io/micrometer/reference/1.13/implementations/statsD.html)