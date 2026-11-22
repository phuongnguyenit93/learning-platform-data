## Phân biệt cấu hình quan sát chung với cấu hình riêng của một meter

Một dịch vụ thanh toán cần gắn vùng triển khai vào dữ liệu quan sát để đối chiếu biểu đồ với dấu vết (trace). Dịch vụ cũng cần đếm số lần thanh toán hoàn tất trong 300 ms. Yêu cầu thứ nhất thuộc về dữ liệu mô tả hoạt động được quan sát. Yêu cầu thứ hai thuộc về cách một đồng hồ đo thời gian (`Timer`) tổng hợp mẫu.

### Hai tầng cấu hình trong Actuator

Một `Observation` mô tả một lần thực hiện công việc, chẳng hạn một lần thanh toán. `ObservationRegistry` giữ các quy tắc áp dụng khi tạo và xử lý Observation. Các bộ xử lý (`ObservationHandler`) dùng cùng ngữ cảnh để tạo tín hiệu phù hợp. Khi có cấu hình metrics của Actuator, `DefaultMeterObservationHandler` ghi thời gian hoàn thành vào `Timer`. Khi cấu hình Micrometer Tracing đã được bật và có bộ xử lý tương ứng, Observation cũng có thể tạo một span trong trace.

`MeterRegistry` quản lý các đồng hồ đo (meter), ví dụ `Timer`, `Counter` và `Gauge`. Một meter có thể đến từ Observation, từ mã đăng ký trực tiếp hoặc từ một bộ liên kết metrics của thư viện. Vì vậy, cấu hình áp dụng cho meter có thể tác động đến dữ liệu từ nhiều nguồn, miễn là ID meter khớp. Với `DefaultMeterObservationHandler`, `Timer` hoàn thành lấy tên từ tên Observation và lấy nhãn từ các cặp khóa–giá trị có ít giá trị phân biệt (low cardinality), cùng nhãn lỗi do handler thêm.

| Cần thay đổi gì? | Cấu hình hoặc điểm mở rộng | Phạm vi tác động |
| --- | --- | --- |
| Gắn `region` cho các Observation | `management.observations.key-values.region` | Thêm cặp khóa–giá trị có ít giá trị phân biệt vào ngữ cảnh Observation. Handler có thể dùng nó trong metrics và trace. |
| Ngừng quan sát một họ hoạt động | `management.observations.enable` hoặc `ObservationPredicate` | Observation bị vô hiệu hóa sẽ không đi qua vòng đời của các handler của nó. Khối nghiệp vụ vẫn chạy. |
| Gắn `service` cho các meter | `management.metrics.tags.service` | Thêm nhãn chung ở tầng meter, kể cả meter đăng ký trực tiếp. |
| Thay đổi histogram, phân vị hoặc ngưỡng SLO của một họ meter | `management.metrics.distribution.*` hoặc `MeterFilter.configure(...)` | Điều chỉnh cách các meter phân bố phù hợp như `Timer` và `DistributionSummary` tổng hợp mẫu. |
| Từ chối đăng ký một họ meter | `management.metrics.enable` hoặc `MeterFilter.accept(...)` | Tác động đến việc đăng ký meter. Các handler khác của Observation vẫn có thể chạy. |

Với handler mặc định, cặp có ít giá trị phân biệt như `channel=web` thích hợp làm nhãn metrics. Mã đơn hàng có thể nhận rất nhiều giá trị nên thuộc nhóm high cardinality. Handler metrics mặc định không lấy nhóm này làm nhãn. Nếu có cấu hình truy vết phù hợp, handler tracing có thể ghi nó vào span. Chọn một nơi đặt mỗi thuộc tính chung theo phạm vi mong muốn. Chẳng hạn, đặt `region` ở tầng Observation nếu cần thuộc tính này trong cả hai tín hiệu bắt nguồn từ Observation, hoặc đặt ở tầng meter nếu cần nhãn này trên mọi meter, kể cả meter đăng ký trực tiếp.

### Đọc cấu hình theo phạm vi

Ví dụ cho Spring Boot 3.3:

```yaml
management:
  observations:
    key-values:
      region: ap-southeast-1
    enable:
      "[checkout.internal]": false
  metrics:
    tags:
      service: checkout
    enable:
      "[checkout.debug.cache]": false
    distribution:
      slo:
        "[checkout.pay]": 300ms
```

- `region` đi vào ngữ cảnh của các Observation được xử lý. `service` đi vào nhãn của meter, kể cả `Timer` được đăng ký trực tiếp.
- `checkout.debug.cache` vẫn có thể được quan sát, nhưng `MeterRegistry` từ chối meter khớp quy tắc. Trái lại, `checkout.internal` là tiền tố để vô hiệu hóa Observation, nên `checkout.internal.heartbeat` sẽ không gọi các handler của Observation đó.
- `slo` thêm mốc 300 ms cho đồng hồ thời gian thanh toán khớp tên. Mốc này phục vụ đếm số mẫu không vượt ngưỡng. Đồng hồ thời gian hoàn tiền vẫn ghi thời lượng bình thường và không nhận mốc này.

Trong `management.metrics.distribution.*`, Spring Boot 3.3 tra từng thuộc tính theo tên meter, rồi bỏ dần đoạn sau dấu chấm để tìm tiền tố khớp. Ví dụ, khóa `checkout.pay` áp dụng cả cho meter mang tên đó có nhiều tổ hợp nhãn lẫn các tên con như `checkout.pay.active` nếu loại meter hỗ trợ thuộc tính. Khóa `checkout.pay.card` cụ thể hơn sẽ được ưu tiên cho chính thuộc tính đó trên tên phù hợp. Nếu chỉ cần áp dụng cho một tên chính xác, một loại meter hoặc một giá trị nhãn như `channel=web`, dùng `MeterFilter` kiểm tra `Meter.Id` và đăng ký bộ lọc trước khi meter được tạo. Khi tùy biến phân bố trong `configure(...)`, hợp nhất cấu hình mới với cấu hình đầu vào để giữ các thuộc tính không được đặt lại.

Tên dùng trong khóa cấu hình là tên meter trong Micrometer. Ví dụ, nếu dùng Prometheus, `checkout.pay` là tên để đối chiếu trong cấu hình, còn `checkout_pay_seconds_bucket` là tên chuỗi histogram ở đầu ra của bộ xuất. Với `Observation` tự tạo, `contextualName(...)` dùng để mô tả hoạt động trong ngữ cảnh, còn handler metrics mặc định lấy tên meter từ tên Observation.

### Thí nghiệm chạy được với Java 17

Lưu đoạn YAML trên thành `application.yml` và đoạn Java sau thành `ObservationScopeDemo.java` trong cùng một thư mục. Chương trình khởi động Spring Boot 3.3.0 với registry metrics trong bộ nhớ, thêm một handler ghi nhận tên Observation đã hoàn thành, rồi chạy bốn hoạt động. Handler thử nghiệm chỉ xác nhận vòng đời của Observation. Chương trình không cấu hình bộ xuất trace.

```java
package demo;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

@SpringBootConfiguration
@EnableAutoConfiguration
public class ObservationScopeDemo {
    public static void main(String[] args) {
        try (var app = new SpringApplicationBuilder(ObservationScopeDemo.class)
                .web(WebApplicationType.NONE)
                .bannerMode(Banner.Mode.OFF)
                .logStartupInfo(false)
                .properties("logging.level.root=OFF")
                .run(args)) {
            var observations = app.getBean(ObservationRegistry.class);
            var meters = app.getBean(MeterRegistry.class);
            List<String> completed = new ArrayList<>();
            observations.observationConfig().observationHandler(new ObservationHandler<Observation.Context>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onStop(Observation.Context context) {
                    completed.add(context.getName());
                }
            });

            observe(observations, "checkout.pay");
            observe(observations, "checkout.refund");
            observe(observations, "checkout.debug.cache");
            observe(observations, "checkout.internal.heartbeat");

            Timer direct = meters.timer("checkout.internal.heartbeat");
            direct.record(Duration.ofMillis(40));
            Timer pay = meters.get("checkout.pay").timer();
            Timer refund = meters.get("checkout.refund").timer();

            System.out.println("completed=" + completed);
            System.out.printf("pay count=%d region=%s service=%s order.id=%s buckets=%d%n",
                    pay.count(), pay.getId().getTag("region"), pay.getId().getTag("service"),
                    pay.getId().getTag("order.id"), pay.takeSnapshot().histogramCounts().length);
            System.out.printf("refund count=%d buckets=%d%n",
                    refund.count(), refund.takeSnapshot().histogramCounts().length);
            System.out.println("debug timer present="
                    + (meters.find("checkout.debug.cache").timer() != null));
            System.out.printf("direct count=%d region=%s service=%s%n",
                    direct.count(), direct.getId().getTag("region"), direct.getId().getTag("service"));
        }
    }

    private static void observe(ObservationRegistry registry, String name) {
        Observation.createNotStarted(name, registry)
                .lowCardinalityKeyValue("channel", "web")
                .highCardinalityKeyValue("order.id", "example-104")
                .observe(() -> System.out.println("work=" + name));
    }
}
```

Dùng Maven hoặc Gradle để phân giải classpath với `org.springframework.boot:spring-boot-starter-actuator:3.3.0` và `com.fasterxml.jackson.core:jackson-databind:2.17.1`, cùng các thư viện phụ thuộc. Đặt `CP` thành classpath đó rồi chạy từ thư mục chứa hai tệp. Các lệnh dưới đây dùng Bash. Trong PowerShell, dùng `$env:CP` và dấu `;` làm dấu phân tách classpath.

```bash
javac -cp "$CP" -d . ObservationScopeDemo.java
java -cp ".:$CP" demo.ObservationScopeDemo --spring.config.location=file:./application.yml
```

Kết quả:

```text
work=checkout.pay
work=checkout.refund
work=checkout.debug.cache
work=checkout.internal.heartbeat
completed=[checkout.pay, checkout.refund, checkout.debug.cache]
pay count=1 region=ap-southeast-1 service=checkout order.id=null buckets=1
refund count=1 buckets=0
debug timer present=false
direct count=1 region=null service=checkout
```

Dòng `work=checkout.internal.heartbeat` xuất hiện vì công việc vẫn chạy dù Observation đã bị vô hiệu hóa. Hoạt động này không có trong `completed`. `Timer` cùng tên được đăng ký trực tiếp sau đó vẫn có `count=1` và nhãn chung `service`. Nó không có `region` vì mẫu đó không đi qua ngữ cảnh Observation.

`checkout.debug.cache` có trong `completed` nhưng không tìm thấy `Timer`. Bộ lọc meter chỉ tác động đến nhánh metrics. Đồng hồ thanh toán có cả hai nhãn chung và một mốc histogram. Đồng hồ hoàn tiền có số lần đo nhưng không có mốc histogram trong ví dụ. Giá trị `order.id=null` nghĩa là khóa high cardinality đã không trở thành nhãn của meter.

### Chọn chỗ sửa khi kiểm tra hệ thống

- Nếu cần thêm thông tin từ ngữ cảnh yêu cầu vào một nhóm Observation, dùng quy ước quan sát (`ObservationConvention`) phù hợp với thành phần được gắn đo. Với thuộc tính chung ổn định như vùng triển khai, dùng `management.observations.key-values`. Tách mã định danh nhiều giá trị khỏi các nhãn dùng để nhóm metrics.
- Nếu chỉ cần ngưỡng 300 ms hoặc thay đổi cách tính phân bố, cấu hình meter tương ứng. Trên ứng dụng web có Actuator, dùng endpoint `/actuator/metrics/{name}` đã được mở để xem tên, nhãn và số đo. Nếu kiểm tra bucket đã xuất, đọc endpoint của bộ xuất, chẳng hạn `/actuator/prometheus` khi có registry Prometheus.
- Nếu metrics biến mất nhưng trace vẫn có, kiểm tra quy tắc đăng ký meter và bộ xuất metrics. Nếu cả hai tín hiệu bắt nguồn từ cùng một Observation đều biến mất, kiểm tra việc gắn đo, điều kiện `ObservationPredicate` và các handler trước khi đổi cấu hình histogram.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html)
- [Spring Boot 3.3 — cấu hình Metrics và tích hợp Observation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13.0 — mã nguồn DefaultMeterObservationHandler](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java)