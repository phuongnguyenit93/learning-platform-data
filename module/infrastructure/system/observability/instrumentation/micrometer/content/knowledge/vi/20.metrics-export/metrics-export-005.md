# Composite registry để xuất cùng phép đo tới nhiều đích

Micrometer cho phép một lần instrumentation được gửi tới nhiều hệ thống giám sát bằng `CompositeMeterRegistry`. Ứng dụng đăng ký meter và ghi nhận sự kiện một lần; composite registry chuyển các thao tác đó tới những registry con đã được gắn vào nó. Mỗi registry con chịu trách nhiệm chuyển đổi và xuất dữ liệu theo backend riêng, chẳng hạn Prometheus để scrape hoặc OTLP để gửi tới một metrics collector.

Composite registry hữu ích khi cần duy trì nhiều đích quan sát, chuyển đổi backend hoặc xuất metrics đồng thời cho nhiều hệ thống. Tuy nhiên, nó không hợp nhất lịch sử của các backend, không tự lưu đệm mọi sự kiện trước khi có registry con và cũng không làm cho các quy tắc đặt tên, đơn vị hay lịch export của các backend trở nên giống nhau.

## 1. CompositeMeterRegistry là gì?

`CompositeMeterRegistry` là một implementation của `MeterRegistry` có nhiệm vụ điều phối meter tới một hoặc nhiều registry con. Các registry con có thể là Prometheus, OTLP, Datadog, Graphite hoặc một backend khác được Micrometer hỗ trợ.

Luồng dữ liệu:

~~~text
                 Logic ứng dụng
                       |
             Counter / Timer / Gauge
                       |
                       v
              CompositeMeterRegistry
                 /      |       \
                /       |        \
               v        v         v
         Prometheus    OTLP     Registry C
          registry   registry   (backend)
             |          |          |
             v          v          v
          Scrape     Push/export  Export
             |          |          |
             v          v          v
         Prometheus  Collector   Backend C
~~~

Ứng dụng chỉ cần biết registry mà nó ghi vào. Composite registry quản lý việc fan-out sang các registry con. Mỗi registry con vẫn có cấu hình riêng về endpoint, chu kỳ export, authentication, naming convention, histogram và định dạng dữ liệu.

Ví dụ, một counter `orders.created` được tăng một lần qua composite có thể được chuyển tới cả Prometheus registry và OTLP registry. Prometheus scrape dữ liệu từ endpoint của ứng dụng, trong khi OTLP registry gửi dữ liệu tới collector theo cấu hình export của nó.

## 2. Đăng ký registry con

Micrometer cho phép thêm registry con bằng `add()` và gỡ bằng `remove()`. Composite registry thường được tạo trong giai đoạn cấu hình ứng dụng.

~~~java
import io.micrometer.core.instrument.CompositeMeterRegistry;
import io.micrometer.core.instrument.MeterRegistry;

public class MetricsSetup {
    public CompositeMeterRegistry create(
            MeterRegistry prometheusRegistry,
            MeterRegistry otlpRegistry) {

        CompositeMeterRegistry composite =
            new CompositeMeterRegistry();

        composite.add(prometheusRegistry);
        composite.add(otlpRegistry);

        return composite;
    }
}
~~~

Trong ví dụ, hai tham số là registry backend đã được tạo và cấu hình trước đó. Cách khởi tạo cụ thể của Prometheus hoặc OTLP phụ thuộc dependency và phiên bản Micrometer mà ứng dụng sử dụng.

Sau khi tạo composite, các meter đăng ký trên composite sẽ được chuyển tới các registry con:

~~~java
Counter created = Counter.builder("orders.created")
    .description("Tổng số đơn hàng được tạo")
    .tag("channel", "web")
    .register(compositeRegistry);

created.increment();
~~~

Không cần đăng ký cùng counter một lần trên từng backend trong code nghiệp vụ. Việc đăng ký qua composite giữ cho instrumentation tập trung và tránh việc mỗi service phải biết tất cả hệ thống giám sát.

### Thêm registry sau khi meter đã được đăng ký

Composite registry có thể nhận registry con sau khi meter đã được đăng ký. Khi một registry con được thêm, composite kết nối các meter hiện có với registry mới để các lần ghi nhận tiếp theo được chuyển tiếp.

Tuy nhiên, composite không phải hàng đợi lưu trữ lịch sử. Những lần `increment()`, `record()` hoặc cập nhật gauge xảy ra khi chưa có registry con không được giữ thành một chuỗi sự kiện để phát lại sau này.

Ví dụ:

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();

Counter counter = composite.counter("jobs.completed");
counter.increment();
counter.increment();

// Registry được gắn sau thời điểm hai lần increment.
composite.add(prometheusRegistry);

counter.increment();
~~~

Prometheus registry không nhận lại hai lần increment đã xảy ra trước khi được gắn. Nó nhận các cập nhật tiếp theo sau khi được thêm vào composite. Vì vậy, hãy cấu hình registry con trước khi ứng dụng bắt đầu xử lý traffic nếu cần số liệu đầy đủ từ đầu.

Có một điểm cần phân biệt: function meter đọc trạng thái tích lũy từ object nguồn khi được lấy mẫu. Khi registry con được gắn sau, lần đọc tiếp theo có thể thấy giá trị hiện tại của nguồn đó. Điều này không có nghĩa composite đã replay các sự kiện cũ; registry chỉ đang đọc snapshot mới nhất từ function.

## 3. Một meter, nhiều backend

Mỗi meter được đăng ký trên composite có thể có một meter tương ứng trong từng registry con. Các registry con cùng nhận phép đo nhưng chuyển đổi theo quy ước backend của chúng.

Ví dụ một Timer:

~~~java
Timer paymentTimer = Timer.builder("payments.duration")
    .description("Thời gian xử lý thanh toán")
    .publishPercentileHistogram()
    .register(compositeRegistry);

paymentTimer.record(() -> paymentService.charge(order));
~~~

Nếu composite có Prometheus registry và OTLP registry:

- Prometheus registry xuất dữ liệu để Prometheus scrape.
- OTLP registry chuyển đổi meter sang OTLP và export theo cấu hình của nó.
- Mỗi backend có thể biểu diễn tên, unit, histogram và metadata theo quy ước riêng.
- Việc ghi nhận trong ứng dụng chỉ diễn ra một lần.

Không nên giả định các backend sẽ hiển thị tên metric giống hệt nhau. Ví dụ Timer có thể được chuẩn hóa thành metric có hậu tố `_seconds` ở Prometheus, trong khi OTLP biểu diễn metric duration với unit metadata. Hãy kiểm tra output của từng registry trước khi viết dashboard hoặc alert.

## 4. Pull registry và push registry có thể cùng tồn tại

Composite registry không bắt buộc mọi registry con phải dùng cùng mô hình export.

| Loại registry | Cách chuyển dữ liệu | Ví dụ |
|---|---|---|
| Pull-based | Backend chủ động scrape endpoint | Prometheus |
| Push-based | Ứng dụng gửi dữ liệu theo chu kỳ hoặc batch | OTLP, Datadog, StatsD tùy implementation |
| In-memory/test | Lưu meter trong process để đọc trực tiếp | SimpleMeterRegistry |

Khi kết hợp Prometheus và OTLP:

- Prometheus scrape endpoint của ứng dụng theo scrape interval do server cấu hình.
- OTLP registry có thể export theo step interval và endpoint collector được cấu hình ở ứng dụng.
- Hai backend có thời điểm quan sát và độ trễ khác nhau.
- Một backend có thể đang nhận dữ liệu trong khi backend kia tạm thời lỗi hoặc không scrape.

Composite registry chỉ fan-out thao tác meter. Nó không đồng bộ scrape interval với push interval và không bảo đảm hai backend có cùng trạng thái dữ liệu tại mọi thời điểm.

## 5. Tích hợp với Spring Boot

Spring Boot Actuator và Micrometer hỗ trợ auto-configuration cho nhiều registry backend. Khi có nhiều implementation registry trên classpath, Spring Boot có thể cấu hình nhiều registry và composite để ứng dụng ghi metrics tới nhiều đích.

Ví dụ dependency:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Phiên bản Spring Boot quản lý phiên bản Micrometer tương thích qua dependency management. Artifact và cách auto-configure có thể thay đổi theo phiên bản; hãy dùng BOM của dự án và xác minh các registry bean thực tế khi ứng dụng khởi động.

Cấu hình ví dụ:

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.tags.application=orders-service
management.otlp.metrics.export.url=http://otel-collector:4318/v1/metrics
management.otlp.metrics.export.step=30s
~~~

Các thuộc tính OTLP cụ thể phụ thuộc phiên bản Spring Boot và registry implementation. Cần kiểm tra property metadata của phiên bản đang dùng, đặc biệt giao thức HTTP/gRPC, URL, headers và authentication.

Trong service, nên inject `MeterRegistry` qua constructor:

~~~java
@Component
public class OrderMetrics {
    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
            .description("Tổng số đơn hàng được tạo")
            .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
~~~

Ứng dụng không cần inject riêng PrometheusMeterRegistry và OtlpMeterRegistry vào từng service. Hãy để cấu hình ứng dụng quyết định registry hoặc composite được cung cấp cho instrumentation.

### Khi nào cần tự tạo CompositeMeterRegistry?

Nếu Spring Boot đã auto-configure các registry và composite theo phiên bản đang dùng, thường không cần tạo thêm composite thủ công. Tạo composite riêng khi ứng dụng có yêu cầu rõ ràng về vòng đời, nhóm backend hoặc registry được gắn động.

Trước khi tạo, hãy kiểm tra các registry bean hiện có để tránh cấu hình cùng một backend hai lần. Nếu một Prometheus registry vừa được Spring Boot quản lý vừa được thêm vào composite thủ công khác, có thể tạo đường xuất trùng hoặc hai endpoint scrape không cần thiết.

## 6. Cấu hình chung và cấu hình riêng cho từng registry

Composite registry điều phối meter, nhưng không làm mất sự khác nhau giữa các registry con.

Những cấu hình thường cần xem xét:

- Common tags: application, environment, region.
- MeterFilter: giới hạn cardinality, đổi tên hoặc từ chối meter.
- Histogram và SLO boundaries.
- Step interval của push registry.
- Endpoint, headers, credentials và timeout.
- Quy tắc đặt tên và đơn vị ở backend.

Hãy cấu hình common tags và filter trước khi meter được đăng ký. Khi có nhiều registry con, xác minh chính sách được áp dụng đồng nhất ở các đích cần thiết.

Một số filter có thể được cấu hình trên composite và được chuyển tiếp theo cơ chế của registry; một số cấu hình có thể thuộc riêng từng registry. Không giả định mọi MeterFilter hoặc DistributionStatisticConfig sẽ tự động có hiệu lực giống nhau ở tất cả backend. Kiểm tra output thực tế của từng registry.

Ví dụ common tags:

~~~java
compositeRegistry.config().commonTags(
    "application", "orders-service",
    "environment", "production"
);
~~~

Nếu backend yêu cầu thêm tag riêng, có thể cấu hình trên registry con tương ứng. Tuy nhiên, tránh làm cùng một metric có schema tag không nhất quán giữa các backend nếu dashboard hoặc pipeline downstream kỳ vọng cùng một chiều phân tích.

## 7. Cardinality và chi phí khi xuất nhiều đích

Một meter identity có thể tạo series ở mỗi backend. Khi xuất sang nhiều hệ thống, chi phí lưu trữ và ingest có thể tăng theo số đích.

Ví dụ một histogram có:

- 20 bucket.
- 4 giá trị channel.
- 3 giá trị outcome.
- 2 registry backend.

Ước tính số series bucket trên hai backend là:

~~~text
20 × 4 × 3 × 2 = 480 series
~~~

Con số thực tế còn phụ thuộc cách backend biểu diễn histogram, count, sum, metadata và số instance. Một backend có thể lưu histogram native, backend khác mở rộng thành bucket series.

Các biện pháp kiểm soát:

- Giữ tag value trong tập hữu hạn.
- Không đưa user ID, request ID hoặc URL đầy đủ vào tag.
- Chỉ bật histogram ở meter cần phân tích phân phối.
- Chọn SLO boundary có mục tiêu.
- Kiểm tra số series ở từng backend.
- Tránh đăng ký cùng backend nhiều lần.
- Theo dõi chi phí ingest và lưu trữ sau khi thêm đích mới.

Composite registry không nhân số meter trong logic nghiệp vụ, nhưng nó có thể nhân số bản xuất và chi phí backend. Hãy tính chi phí trước khi thêm registry mới vào production.

## 8. Lỗi và tính độc lập của các backend

Các registry con có vòng đời và cơ chế export riêng. Push registry có thể gặp lỗi mạng, timeout hoặc collector không khả dụng. Pull registry có thể không được scrape hoặc endpoint bị lỗi.

Composite registry không phải hệ thống đảm bảo giao dịch phân tán giữa các backend. Một lần cập nhật meter không đồng nghĩa mọi backend đã lưu thành công cùng lúc.

Với push registry, kiểm tra:

- Export interval và batch size.
- Timeout và retry policy của implementation.
- Hành vi khi collector không khả dụng.
- Shutdown hook và thời gian flush cuối.
- Log hoặc metric nội bộ báo lỗi export.

Với pull registry, kiểm tra:

- Endpoint scrape có sẵn và được bảo vệ phù hợp.
- Prometheus scrape interval và timeout.
- HTTP status và Content-Type.
- Target health và scrape error.

Không để một backend phụ trợ không quan trọng làm gián đoạn luồng nghiệp vụ chỉ vì export metrics lỗi. Metrics là dữ liệu quan sát; đường ghi nhận nên có chi phí và ảnh hưởng được kiểm soát.

## 9. Quản lý vòng đời add và remove

Registry con cần được gắn và gỡ theo vòng đời rõ ràng.

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();

composite.add(prometheusRegistry);
composite.add(otlpRegistry);

// Khi dừng một backend:
composite.remove(otlpRegistry);
otlpRegistry.close();
~~~

Gỡ registry khỏi composite ngăn các meter trong composite tiếp tục được chuyển tới registry đó. Đóng registry giải phóng tài nguyên riêng của backend, ví dụ scheduler hoặc exporter thread nếu implementation có sử dụng.

Thứ tự dừng nên là:

1. Ngừng nhận công việc mới nếu cần.
2. Gỡ registry con khỏi composite.
3. Flush hoặc shutdown theo API của registry nếu cần.
4. Đóng registry con.
5. Hoàn tất shutdown ứng dụng.

Đối với Spring, để container quản lý vòng đời bean khi có thể. Nếu tự thêm registry vào composite trong lifecycle callback, hãy gỡ nó trong callback tương ứng khi context dừng. Không gọi add/remove trong mỗi request.

Nếu thêm cùng một registry nhiều lần hoặc cùng một backend được quản lý ở nhiều nơi, rất khó xác định ai chịu trách nhiệm đóng. Hãy có một thành phần sở hữu duy nhất cho từng registry instance.

## 10. Kiểm thử composite registry

Có thể dùng hai SimpleMeterRegistry để xác minh một lần ghi được chuyển đến cả hai registry con:

~~~java
import io.micrometer.core.instrument.CompositeMeterRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CompositeRegistryTest {

    @Test
    void forwardsOneMeasurementToEveryChildRegistry() {
        try (CompositeMeterRegistry composite = new CompositeMeterRegistry()) {
            SimpleMeterRegistry first = new SimpleMeterRegistry();
            SimpleMeterRegistry second = new SimpleMeterRegistry();

            composite.add(first);
            composite.add(second);

            Counter counter = Counter.builder("orders.created")
                .tag("channel", "web")
                .register(composite);

            counter.increment(3);

            assertEquals(
                3.0,
                first.get("orders.created")
                    .tag("channel", "web")
                    .counter()
                    .count()
            );

            assertEquals(
                3.0,
                second.get("orders.created")
                    .tag("channel", "web")
                    .counter()
                    .count()
            );
        }
    }
}
~~~

Có thể kiểm thử thêm:

- Meter được đăng ký trước khi thêm registry con và các cập nhật sau đó được chuyển tiếp.
- Các cập nhật trước khi thêm registry con không được replay như sự kiện lịch sử.
- Sau khi remove, registry đã gỡ không nhận cập nhật tiếp theo.
- Hai registry con có cùng metric identity nhưng cấu hình backend riêng.
- Một registry push lỗi không làm hỏng logic nghiệp vụ.
- Shutdown đóng exporter và giải phóng thread/tài nguyên.

Unit test với SimpleMeterRegistry xác minh fan-out trong process. Cần integration test riêng với Prometheus hoặc OTLP registry để kiểm tra scrape/export thực tế, content type, endpoint và authentication.

## 11. Các lỗi thường gặp

- **Đăng ký meter riêng ở từng backend trong service:** làm code nghiệp vụ phụ thuộc vào topology metrics và dễ ghi trùng.
- **Cho rằng composite lưu đệm lịch sử:** cập nhật trước khi gắn registry con không được replay.
- **Tạo composite thủ công trong khi Spring Boot đã quản lý composite:** có thể xuất trùng.
- **Thêm cùng registry nhiều lần:** làm vòng đời và đường xuất khó kiểm soát.
- **Cho rằng mọi backend có cùng tên và unit:** mỗi registry có thể chuẩn hóa khác nhau.
- **Bỏ qua export interval:** push registry có độ trễ khác pull registry.
- **Cho rằng một lần increment đồng nghĩa mọi backend đã lưu thành công:** composite không phải giao dịch phân tán.
- **Không gỡ registry khi shutdown:** exporter thread hoặc scheduler có thể còn hoạt động.
- **Không tính chi phí nhiều đích:** ingest, series và lưu trữ tăng theo topology.
- **Giả định mọi filter áp dụng giống nhau:** cần kiểm tra cấu hình và output từng registry.

## 12. Checklist triển khai

- [ ] Xác định các backend cần nhận cùng phép đo.
- [ ] Chọn registry con tương thích với phiên bản Micrometer/Spring Boot.
- [ ] Dùng một composite registry làm điểm ghi chung.
- [ ] Gắn registry con trước khi cần thu thập đầy đủ dữ liệu.
- [ ] Không kỳ vọng composite replay các sự kiện trước khi gắn backend.
- [ ] Phân biệt pull scrape và push export.
- [ ] Cấu hình endpoint, interval, timeout và authentication riêng cho từng backend.
- [ ] Chuẩn hóa tên, unit và tag theo hợp đồng metrics.
- [ ] Kiểm soát cardinality và chi phí histogram trên mọi đích.
- [ ] Tránh cấu hình trùng với composite do Spring Boot auto-configure.
- [ ] Có lifecycle add/remove/close rõ ràng.
- [ ] Unit test fan-out và integration test từng backend.
- [ ] Theo dõi lỗi scrape/export và tác động khi một backend ngừng hoạt động.

CompositeMeterRegistry giúp một lần instrumentation được xuất tới nhiều hệ thống mà không buộc code nghiệp vụ biết từng backend. Hãy để composite quản lý fan-out, giữ cấu hình và vòng đời riêng cho từng registry con, đồng thời kiểm thử dữ liệu ở từng đích. Cách tổ chức này cho phép bổ sung hoặc thay đổi backend có kiểm soát mà không phải sửa mọi nơi đang ghi metrics.

