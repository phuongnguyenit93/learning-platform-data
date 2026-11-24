# Đánh giá khả năng xuất meter tùy chỉnh ở hệ thống đích

Đăng ký được một meter trong `MeterRegistry` mới chỉ xác nhận rằng Micrometer đã nhận phép đo. Điều đó chưa bảo đảm registry đích có thể chuyển phép đo ấy thành dữ liệu mà hệ thống giám sát hiểu được. Mỗi registry có quy tắc riêng về loại metric, tên, đơn vị, tag, cách tổng hợp và giao thức xuất.

Micrometer cung cấp API `Meter.builder(...)` để tạo custom meter từ một hoặc nhiều `Measurement`. Mỗi registry triển khai điểm mở rộng `newMeter(...)` để tạo đối tượng meter phù hợp với nó. Khi xuất dữ liệu, registry phải ánh xạ các measurement đó sang mô hình của backend. Vì vậy, cần kiểm chứng custom meter trên đúng registry và phiên bản mà ứng dụng triển khai.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, đánh giá khả năng export giúp xác định khi nào nên dùng custom meter, khi nào nên biểu diễn bằng counter/gauge/timer/summary chuẩn, và khi nào cần một registry adapter riêng. Mục tiêu là bảo đảm dữ liệu đến hệ thống đích giữ được ngữ nghĩa và có thể truy vấn được.

## 1. Phân biệt custom meter và custom registry

Hai khái niệm có tên gần giống nhau nhưng giải quyết hai vấn đề khác nhau:

| Khái niệm | Vai trò | Khi nào cần dùng |
| --- | --- | --- |
| Custom meter | Định nghĩa một phép đo hoặc tập measurement riêng trong Micrometer | Khi mô hình đo không vừa hoàn toàn với một meter primitive có sẵn |
| Custom registry | Xây dựng adapter kết nối Micrometer với một hệ thống giám sát chưa có registry phù hợp | Khi backend đích chưa được Micrometer hỗ trợ hoặc cần giao thức xuất riêng |

Custom meter không tự tạo ra khả năng kết nối đến backend mới. Nó chỉ cung cấp dữ liệu thông qua API Micrometer. Registry đích vẫn phải biết cách đọc và xuất loại dữ liệu đó.

Nếu backend đã có registry chính thức, hãy kiểm tra registry đó trước. Tài liệu Micrometer khuyến nghị ưu tiên implementation có sẵn; chỉ xây dựng registry riêng khi không có adapter phù hợp. Khi cần viết registry, có thể mở rộng `MeterRegistry`, `PushMeterRegistry` hoặc `StepMeterRegistry` tùy mô hình thu thập và xuất dữ liệu.

## 2. Custom meter gồm những thành phần nào?

Một `Meter` là một đối tượng có tên và dimensions (tags), cung cấp một hoặc nhiều `Measurement`. Mỗi measurement gồm:

- Một hàm lấy giá trị tại thời điểm được đọc.
- Một `Statistic` mô tả ý nghĩa của giá trị, ví dụ `VALUE`, `COUNT`, `TOTAL`, `MAX` hoặc `TOTAL_TIME`.

`Meter.Type` mô tả họ metric mà custom meter muốn biểu diễn, chẳng hạn `GAUGE`, `COUNTER`, `TIMER`, `DISTRIBUTION_SUMMARY` hoặc `OTHER`. Type giúp registry và naming convention hiểu cách phân loại meter. `Statistic` mô tả ý nghĩa từng giá trị đo bên trong meter.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Name | Đang đo đại lượng hoặc trạng thái nào? | `worker.snapshot` |
| Tags | Có thể phân tích theo những chiều nào? | `pool=default`, `region=ap-southeast` |
| `Meter.Type` | Meter thuộc họ nào? | `GAUGE` |
| `Measurement` | Giá trị nào được lấy khi đọc? | Số worker đang hoạt động |
| `Statistic` | Giá trị đó có ý nghĩa gì? | `VALUE` là giá trị tức thời |
| `baseUnit` | Giá trị được biểu diễn theo đơn vị nào? | `tasks` |

Một meter cần trả về số lượng measurement ổn định và theo cùng thứ tự trong suốt vòng đời. Giá trị của từng measurement có thể thay đổi theo trạng thái ứng dụng. Hàm đọc nên nhanh, không chặn, không thực hiện I/O và không ném exception trong quá trình scrape.

## 3. Tạo custom meter bằng Meter.builder

Ví dụ sau tạo một meter dạng gauge để quan sát số worker đang hoạt động. Trạng thái nằm trong `AtomicLong`; measurement đọc giá trị hiện tại mỗi khi registry lấy mẫu:

```java
import java.util.Collections;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Measurement;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Statistic;

public class WorkerSnapshotMetrics {
    private final AtomicLong activeWorkers = new AtomicLong();

    public WorkerSnapshotMetrics(MeterRegistry registry) {
        Measurement active = new Measurement(
                () -> (double) activeWorkers.get(),
                Statistic.VALUE);

        Meter.builder(
                        "worker.snapshot",
                        Meter.Type.GAUGE,
                        Collections.singletonList(active))
                .description("Current number of active workers")
                .baseUnit("tasks")
                .tag("pool", "default")
                .register(registry);
    }

    public void setActiveWorkers(long count) {
        activeWorkers.set(count);
    }
}
```

Khi số worker thay đổi, component chỉ cập nhật trạng thái:

```java
workerSnapshotMetrics.setActiveWorkers(4);
```

Registry đọc measurement khi thu thập dữ liệu. `Meter.builder` nhận tên, type và danh sách measurement, sau đó thêm description, base unit, tag và đăng ký vào registry.

Ví dụ trên dùng một measurement nên về mặt ngữ nghĩa có thể biểu diễn bằng `Gauge.builder(...)` đơn giản hơn. Custom meter hữu ích hơn khi cần một meter có cấu trúc measurement riêng hoặc cần mô tả loại meter không được API primitive hiện có biểu diễn trực tiếp. Hãy ưu tiên meter chuẩn khi chúng đã đáp ứng đúng nhu cầu.

## 4. Chọn Type và Statistic đúng ngữ nghĩa

Registry đích có thể dựa vào `Meter.Type` và `Statistic` để quyết định cách ánh xạ dữ liệu. Chọn sai type hoặc statistic có thể khiến metric được xuất dưới dạng không phù hợp hoặc bị backend từ chối.

| Type | Statistic thường gặp | Ý nghĩa |
| --- | --- | --- |
| `GAUGE` | `VALUE` | Giá trị tức thời có thể tăng hoặc giảm |
| `COUNTER` | `COUNT` | Giá trị tích lũy hoặc tốc độ đếm theo quy ước registry |
| `TIMER` | `COUNT`, `TOTAL_TIME`, `MAX` | Số lần thực hiện và thời lượng |
| `DISTRIBUTION_SUMMARY` | `COUNT`, `TOTAL`, `MAX` | Số mẫu và phân phối đại lượng số |
| `OTHER` | Tùy mô hình custom | Measurement không thuộc một họ chuẩn cụ thể |

Các registry không nhất thiết xử lý mọi tổ hợp type/statistic giống nhau. Bảng trên là gợi ý về ngữ nghĩa, không phải cam kết rằng mọi backend đều hỗ trợ toàn bộ tổ hợp. Hãy xem tài liệu registry và kiểm tra output thực tế.

Nếu dữ liệu thực chất là số lượng sự kiện tăng đơn điệu, dùng `Counter` hoặc `FunctionCounter` thường dễ tương thích hơn custom meter. Nếu dữ liệu là trạng thái hiện tại, dùng `Gauge`. Nếu là thời lượng, dùng `Timer`. Custom meter không nên mô phỏng lại một primitive chỉ để tránh dùng API chuẩn.

## 5. Registry đích quyết định cách export

Micrometer chuẩn hóa API ghi nhận nhưng các hệ thống giám sát khác nhau về mô hình dữ liệu và giao thức:

| Đặc điểm | Câu hỏi cần kiểm tra |
| --- | --- |
| Dimensionality | Backend có giữ tag dưới dạng label/dimension hay phải gộp tag vào tên metric? |
| Metric type | Backend hỗ trợ gauge, counter, histogram, summary hay chỉ một số dạng? |
| Statistic | Backend có biểu diễn được từng measurement như `VALUE`, `COUNT`, `TOTAL` không? |
| Unit | Đơn vị có được giữ, chuyển đổi hoặc thể hiện trong tên metric không? |
| Rate aggregation | Backend cần giá trị tích lũy hay tốc độ theo chu kỳ? |
| Publishing | Backend chủ động scrape ứng dụng hay ứng dụng push dữ liệu định kỳ? |
| Naming | Tên, ký tự phân tách, hậu tố và tag key được chuẩn hóa như thế nào? |

Ví dụ, Prometheus sử dụng mô hình dimensional và pull: nó scrape từng instance, giữ label và thường nhận counter tích lũy để tính `rate()` ở phía truy vấn. Một số hệ thống hierarchical như Graphite hoặc JMX biểu diễn chiều tag bằng cách làm phẳng chúng vào tên. Một số registry push theo chu kỳ và có thể chuẩn hóa count thành tốc độ trước khi gửi.

Do đó, một custom meter có thể hoạt động trong registry này nhưng không giữ nguyên hình dạng khi chuyển sang registry khác. Cần kiểm tra cả việc đăng ký thành công lẫn dữ liệu được xuất ra.

## 6. Đánh giá với Prometheus registry

Prometheus registry hiện thực `newMeter(...)` cho custom meter và chuyển các measurement đến collector của Prometheus. Đây là dấu hiệu cho thấy custom meter có đường export trong implementation này; ứng dụng vẫn phải kiểm tra metric type, tên, label và giá trị thực tế ở output.

Với ứng dụng Spring Boot có Actuator và Prometheus registry, expose endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Sau khi khởi động ứng dụng và cập nhật trạng thái worker, đọc endpoint:

```bash
curl http://localhost:8080/actuator/prometheus
```

Với ví dụ `worker.snapshot`, output Prometheus dự kiến có dạng tương tự:

```text
# HELP worker_snapshot Current number of active workers
# TYPE worker_snapshot gauge
worker_snapshot{pool="default"} 4.0
```

Tên chính xác và cách hiển thị unit phụ thuộc naming convention, phiên bản registry và Prometheus client được sử dụng. Đoạn output trên minh họa ý nghĩa mong đợi; hãy dùng output thực tế làm căn cứ cho dashboard và truy vấn.

Trong code, custom meter được đăng ký vào `MeterRegistry` do Spring inject. Để endpoint hoạt động, runtime phải có đúng Prometheus registry adapter và Actuator exposure. Chỉ đăng ký custom meter trên `SimpleMeterRegistry` sẽ không tạo endpoint Prometheus.

## 7. Kiểm thử ở hai cấp

Kiểm thử bằng `SimpleMeterRegistry` xác minh custom meter được tạo và các measurement trả về giá trị mong đợi. Nó không xác minh khả năng export của backend.

Ví dụ unit test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collections;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Measurement;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class WorkerSnapshotMetricsTest {
    @Test
    void exposesCurrentWorkerCountAsMeasurement() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            AtomicLong active = new AtomicLong(3);
            Meter meter = Meter.builder(
                            "worker.snapshot",
                            Meter.Type.GAUGE,
                            Collections.singletonList(new Measurement(
                                    () -> (double) active.get(),
                                    Statistic.VALUE)))
                    .tag("pool", "default")
                    .register(registry);

            assertThat(meter.measure().iterator().next().getValue())
                    .isEqualTo(3.0);

            active.set(5);

            assertThat(meter.measure().iterator().next().getValue())
                    .isEqualTo(5.0);
        }
    }
}
```

Unit test này xác minh giá trị được đọc động từ trạng thái. Nó không xác minh naming convention, định dạng Prometheus hay khả năng tiếp nhận của backend.

### Integration test với registry đích

Tạo integration test dùng đúng registry adapter của môi trường triển khai. Với Prometheus, có thể đọc `scrape()` trên `PrometheusMeterRegistry` hoặc gọi `/actuator/prometheus` trong test Spring Boot. Kiểm tra tối thiểu:

1. Meter xuất hiện trong output.
2. Tên metric được chuẩn hóa đúng và không bị trùng với metric khác.
3. Type được công bố đúng với ngữ nghĩa đã chọn.
4. Tag key/value được giữ hoặc chuyển đổi theo quy ước mong đợi.
5. Giá trị thay đổi khi trạng thái nguồn thay đổi.
6. Description và base unit được thể hiện đúng nếu backend hỗ trợ.
7. Không có cảnh báo hoặc callback registration failure trong log.

Sau khi output đúng, cần xác minh backend thật đã scrape hoặc nhận dữ liệu. Một endpoint trả về metric mới chỉ chứng minh ứng dụng đã xuất dữ liệu; nó chưa chứng minh backend đã lưu và truy vấn được chuỗi dữ liệu.

## 8. Phát hiện lỗi đăng ký và xung đột tên

Micrometer nhận diện meter bằng tổ hợp tên và tags. Nếu cùng một ID được đăng ký nhiều lần, lần đăng ký đầu tiên được giữ lại; các lần sau không tạo một meter độc lập. Vì vậy, không dùng cùng tên và tag cho hai custom meter có cấu trúc measurement hoặc type khác nhau.

Một số backend còn áp đặt quy tắc chặt hơn. Prometheus yêu cầu các meter cùng metric name có cùng type. Nếu hai meter khác type được chuẩn hóa thành cùng tên Prometheus, đăng ký có thể thất bại hoặc bị bỏ qua kèm thông báo lỗi. Tên canonical khác nhau cũng có thể va chạm sau khi naming convention chuyển thành cùng tên export.

Trong quá trình đánh giá, hãy:

- Đặt tên có ngữ nghĩa rõ ràng và kiểm tra tên sau chuẩn hóa.
- Dùng cùng một `Meter.Type` cho các meter cùng metric family.
- Kiểm tra tag key/value, đặc biệt khi backend làm phẳng tag vào tên.
- Đăng ký meter sau khi cấu hình registry và filter đã hoàn tất.
- Theo dõi `onMeterRegistrationFailed` hoặc log của registry nếu adapter cung cấp thông báo lỗi.

Không dùng tên metric để nhúng giá trị động. Hãy dùng tag có tập giá trị hữu hạn và kiểm soát cardinality như với các meter chuẩn.

## 9. Đánh giá cardinality và chi phí export

Mỗi tổ hợp tên và tag có thể tạo một chuỗi dữ liệu riêng. Custom meter có nhiều measurement còn có thể tạo nhiều chuỗi trên cùng meter ID, tùy cách registry ánh xạ chúng. Trước khi đưa vào production, hãy ước lượng số series phát sinh.

Không sử dụng các giá trị gần như duy nhất làm tag, ví dụ:

- ID người dùng, ID đơn hàng hoặc request ID.
- Nội dung exception, URL đầy đủ hoặc chuỗi đầu vào do người dùng cung cấp.
- Timestamp hoặc giá trị ngẫu nhiên.

Chỉ dùng những chiều có tập giá trị hữu hạn như `pool`, `region`, `operation` hoặc `outcome`. Nếu custom meter phát ra nhiều measurement, hãy giới hạn số measurement và giữ thứ tự ổn định. Mỗi hàm đọc cần nhẹ, tránh truy vấn cơ sở dữ liệu hoặc gọi dịch vụ mạng trong lúc backend scrape.

## 10. Khi nào nên chuyển custom meter thành meter chuẩn?

Nếu custom meter chỉ cung cấp một giá trị tức thời, dùng `Gauge` thường tương thích và dễ hiểu hơn. Nếu nó biểu diễn số sự kiện tích lũy, dùng `Counter` hoặc `FunctionCounter`. Nếu có count và total duration, dùng `Timer` hoặc `FunctionTimer`. Nếu theo dõi phân phối số, dùng `DistributionSummary`.

Chuyển sang meter chuẩn có các lợi ích:

- Registry có thể áp dụng quy tắc export đã được kiểm thử rộng rãi.
- Backend hiểu type và statistic theo quy ước phổ biến.
- Dashboard, alert và truy vấn dễ tái sử dụng.
- Hành vi khi đổi registry thường dễ dự đoán hơn.

Giữ custom meter khi mô hình đo thực sự cần nhiều measurement hoặc semantics riêng mà các primitive không biểu diễn phù hợp. Hãy ghi tài liệu cho từng measurement, unit, statistic và mapping phía backend.

## 11. Khi nào cần tự xây dựng registry adapter?

Nếu hệ thống đích chưa có registry trong Micrometer, custom meter không giải quyết được phần kết nối. Khi đó, có thể xây dựng adapter bằng cách mở rộng một lớp registry nền phù hợp:

| Lớp nền | Mô hình phù hợp |
| --- | --- |
| `MeterRegistry` | Registry tự quản lý cách lấy và xuất dữ liệu |
| `PushMeterRegistry` | Backend nhận dữ liệu được push theo chu kỳ |
| `StepMeterRegistry` | Backend nhận số đo theo từng khoảng thời gian (step) |

Registry riêng phải triển khai cách tạo các meter chuẩn và custom meter, xác định base time unit, naming convention, histogram expiry, quy tắc rate aggregation, cấu hình kết nối, retry, timeout và vòng đời publisher. Cần kiểm thử từng loại meter và failure mode của giao thức export.

Trước khi bắt đầu, hãy kiểm tra xem backend có API hoặc giao thức phổ biến mà Micrometer đã hỗ trợ không. Nếu adapter riêng chỉ phục vụ một ứng dụng, cân nhắc chi phí bảo trì, tương thích phiên bản và khả năng tái sử dụng trước khi triển khai.

## 12. Quy trình đánh giá khả năng export

Khi cần đưa một custom meter vào hệ thống đích, hãy đi theo trình tự:

1. Xác định phép đo có thể biểu diễn bằng `Counter`, `Gauge`, `Timer`, `DistributionSummary` hoặc meter chuẩn khác hay không.
2. Nếu cần custom meter, định nghĩa rõ `Meter.Type`, danh sách `Measurement`, `Statistic`, base unit và tags.
3. Đăng ký custom meter bằng `Meter.builder(...)` trên abstraction `MeterRegistry`.
4. Dùng `SimpleMeterRegistry` để kiểm tra ID và giá trị measurement trong unit test.
5. Dùng đúng registry adapter của backend để kiểm tra export trong integration test.
6. Kiểm tra tên, type, unit, tag, số lượng series và giá trị thực tế trong exposition hoặc payload.
7. Xác nhận backend đã nhận, lưu và truy vấn được metric.
8. Nếu registry không hỗ trợ cấu trúc cần thiết, chuyển về meter chuẩn hoặc xây dựng adapter riêng có kiểm thử.
9. Ghi lại mapping giữa tên canonical trong Micrometer và tên/type được công bố ở backend.

## Tài liệu tham khảo

- [Micrometer: Meter API và các loại Meter](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer: Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer: Các hệ thống giám sát được hỗ trợ](https://docs.micrometer.io/micrometer/reference/concepts/implementations.html)
- [Micrometer: Custom Meter Registry](https://docs.micrometer.io/micrometer/reference/guides/custom-meter-registry.html)
- [Micrometer: Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Meter Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Meter.html)
