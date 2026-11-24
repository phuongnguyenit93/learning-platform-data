# Lọc meter theo tên, tiền tố hoặc điều kiện định danh

Một ứng dụng có thể đăng ký hàng trăm hoặc hàng nghìn meter từ mã nghiệp vụ, Spring Boot Actuator và các thư viện bên thứ ba. Không phải meter nào cũng cần được xuất đến mọi hệ thống giám sát. `MeterFilter` cho phép áp dụng chính sách khi meter được đăng ký vào `MeterRegistry`: chấp nhận, từ chối hoặc biến đổi meter dựa trên tên và thông tin định danh của nó.

Có thể lọc theo tên chính xác, tiền tố tên, loại meter hoặc tag. Ví dụ, ứng dụng có thể bỏ các metric debug, chỉ cho phép nhóm metric thuộc một miền nghiệp vụ, hoặc từ chối một meter HTTP cụ thể theo tag `uri`. Bộ lọc cũng có thể giới hạn số meter và số giá trị tag để kiểm soát cardinality.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `MeterFilter` là một lớp bảo vệ ở ranh giới đăng ký meter. Nó giúp kiểm soát dữ liệu trước khi registry xuất sang Prometheus hoặc backend khác. Filter không thay thế việc đặt tên và tag tốt ngay trong instrumentation; chính sách lọc cần được thiết kế cùng với các meter của ứng dụng.

## 1. MeterFilter hoạt động ở thời điểm đăng ký

`MeterFilter` được gắn vào cấu hình của registry:

```java
registry.config().meterFilter(MeterFilter.denyNameStartsWith("internal.debug."));
```

Khi ứng dụng đăng ký meter, registry đưa `Meter.Id` qua các filter đã cấu hình. Filter quyết định meter được chấp nhận, bị từ chối hay cần biến đổi ID trước khi đăng ký.

Điều này có ba hệ quả:

- Filter tác động đến quá trình đăng ký meter trong Micrometer, trước bước export của registry.
- Filter không phải bộ lọc truy vấn ở Prometheus, Grafana hoặc backend; nó không xóa dữ liệu đã được backend thu thập trước đó.
- Filter không tự động loại bỏ meter đã đăng ký trước khi chính sách được cấu hình. Hãy thiết lập filter sớm, trước khi các component tạo meter.

Một meter bị từ chối sẽ không được registry quản lý như một meter hoạt động bình thường. API đăng ký vẫn có thể trả về đối tượng meter không hoạt động (no-op) để mã instrumentation tiếp tục chạy mà không cần kiểm tra từng lần ghi nhận. Vì vậy, cần kiểm tra registry hoặc output export để xác nhận chính sách lọc có hiệu lực.

## 2. Định danh Meter.Id dùng để lọc

Filter nhận một `Meter.Id`, chứa các thông tin định danh và metadata của meter:

| Thành phần | Cách dùng trong filter |
| --- | --- |
| `getName()` | So sánh tên canonical của meter |
| `getTags()` / `getTag(key)` | Kiểm tra key/value tag |
| `getType()` | Phân biệt `COUNTER`, `GAUGE`, `TIMER`, `DISTRIBUTION_SUMMARY`... |
| `getBaseUnit()` | Kiểm tra đơn vị nếu chính sách cần phân biệt |
| `getDescription()` | Kiểm tra mô tả khi thực sự cần thiết |

Tên trong `Meter.Id` là tên meter ở phía Micrometer, ví dụ `http.server.requests`. Nó có thể khác tên đã chuẩn hóa khi registry xuất ra backend, chẳng hạn `http_server_requests_seconds_count` ở Prometheus. Vì vậy, filter nên dùng tên canonical mà instrumentation đăng ký, không dùng tên export để đoán cách đặt tên của registry.

## 3. Từ chối meter theo tên chính xác

Khi chỉ cần loại bỏ một meter cụ thể, có thể dùng predicate trên `Meter.Id`:

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;

MeterFilter denyDebugSnapshot = MeterFilter.deny(
        id -> "worker.snapshot.debug".equals(id.getName()));

registry.config().meterFilter(denyDebugSnapshot);
```

Predicate trả về `true` với meter có tên chính xác `worker.snapshot.debug`; filter từ chối meter đó. Các meter khác tiếp tục đi qua chuỗi filter.

Có thể kết hợp tên và type để chỉ từ chối một loại meter trong cùng tên:

```java
MeterFilter denyDebugGauge = MeterFilter.deny(id ->
        "worker.snapshot".equals(id.getName())
                && id.getType() == Meter.Type.GAUGE);

registry.config().meterFilter(denyDebugGauge);
```

Điều kiện trên chỉ từ chối `worker.snapshot` khi type là `GAUGE`. Nếu có một meter khác cùng tên nhưng type khác, predicate không từ chối meter đó. Tuy nhiên, việc dùng cùng tên cho nhiều type thường gây nhầm lẫn và có thể xung đột ở backend; nên thiết kế tên metric sao cho ngữ nghĩa và type nhất quán.

## 4. Lọc theo tiền tố tên

Khi muốn loại bỏ cả một nhóm meter, dùng các factory method có sẵn:

```java
registry.config().meterFilter(
        MeterFilter.denyNameStartsWith("internal.debug."));
```

Ví dụ, các tên sau sẽ bị từ chối:

- `internal.debug.cache`
- `internal.debug.queue.depth`
- `internal.debug.worker.active`

Các tên như `orders.created` hoặc `http.server.requests` không khớp tiền tố nên tiếp tục được xử lý bởi các filter tiếp theo.

Micrometer cũng cung cấp `acceptNameStartsWith(...)`. Method này chấp nhận các meter khớp tiền tố. Tuy nhiên, nó không tự động từ chối các meter không khớp; chúng có thể tiếp tục qua các filter sau. Nếu mục tiêu là chỉ cho phép một nhóm tên và từ chối mọi nhóm còn lại, hãy dùng predicate phủ định rõ ràng:

```java
MeterFilter onlyOrdersMeters = MeterFilter.deny(
        id -> !id.getName().startsWith("orders."));

registry.config().meterFilter(onlyOrdersMeters);
```

Với cấu hình này, meter không bắt đầu bằng `orders.` bị từ chối. Hãy cẩn thận khi dùng allowlist ở cấp registry dùng chung: nó có thể loại bỏ metrics do Actuator, JVM hoặc thư viện bên thứ ba tạo ra nếu các tên đó không thuộc tiền tố được cho phép.

## 5. Lọc theo điều kiện tag

Khi tên meter giống nhau nhưng cần loại bỏ một nhóm theo chiều phân loại, hãy kiểm tra tag trong `Meter.Id`.

Ví dụ, không xuất timer HTTP dành cho health check:

```java
MeterFilter denyHealthRequests = MeterFilter.deny(id ->
        "http.server.requests".equals(id.getName())
                && "health".equals(id.getTag("uri")));

registry.config().meterFilter(denyHealthRequests);
```

Filter chỉ từ chối meter `http.server.requests` có tag `uri=health`. Những URI khác vẫn được giữ. Tên và tag thực tế phụ thuộc instrumentation; hãy kiểm tra `Meter.Id` hoặc endpoint Actuator metrics để biết các key/value đang được dùng.

Có thể kết hợp nhiều điều kiện:

```java
MeterFilter denyInternalFailures = MeterFilter.deny(id ->
        id.getName().startsWith("orders.")
                && "internal".equals(id.getTag("channel"))
                && "debug".equals(id.getTag("outcome")));
```

Điều kiện predicate có thể kiểm tra tên, type và tag cùng lúc. Nên viết điều kiện rõ ràng, kiểm thử các trường hợp khớp và không khớp, đồng thời giữ số lượng filter vừa đủ để chính sách dễ đọc.

## 6. Chấp nhận và từ chối trong chuỗi filter

Một `MeterFilter` có thể trả về ba quyết định:

| Quyết định | Ý nghĩa |
| --- | --- |
| `ACCEPT` | Chấp nhận meter và kết thúc việc xét các filter tiếp theo |
| `DENY` | Từ chối meter và kết thúc việc xét các filter tiếp theo |
| `NEUTRAL` | Không đưa ra quyết định cuối; tiếp tục xét filter kế tiếp |

Các filter được áp dụng theo thứ tự đăng ký. Điều này quan trọng khi kết hợp allowlist, denylist và filter biến đổi. Một filter trả `ACCEPT` sớm có thể khiến filter từ chối ở phía sau không được áp dụng; một filter trả `DENY` sẽ chặn meter ngay tại đó.

Ví dụ, nếu có chính sách chấp nhận sớm một nhóm meter và sau đó có chính sách từ chối một meter cụ thể trong nhóm đó, cần sắp xếp thứ tự hoặc kết hợp predicate để bảo đảm quy tắc từ chối được thực thi. Với các chính sách bảo vệ, thường nên đặt các điều kiện từ chối quan trọng trước các điều kiện chấp nhận rộng.

## 7. Cấu hình filter trong Spring Boot

Với Spring Boot Actuator, có thể đăng ký filter bằng `MeterRegistryCustomizer`. Spring Boot áp dụng customizer lên registry được auto-configure:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsFilterConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> meterFilterCustomizer() {
        return registry -> registry.config()
                .meterFilter(MeterFilter.denyNameStartsWith("internal.debug."))
                .meterFilter(MeterFilter.deny(id ->
                        "http.server.requests".equals(id.getName())
                                && "health".equals(id.getTag("uri"))));
    }
}
```

Ví dụ loại bỏ nhóm metric debug và timer request health check. Các meter khác vẫn được đăng ký bình thường. Nếu ứng dụng có nhiều registry hoặc nhiều customizer, hãy kiểm tra thứ tự cấu hình và bảo đảm filter được thêm trước khi các meter liên quan được tạo.

Không tạo `MeterRegistry` mới bên trong customizer. Hãy cấu hình registry mà Spring Boot cung cấp để toàn bộ component dùng chung chính sách.

## 8. Kết hợp MeterFilter với giới hạn cardinality

Filter còn có thể giới hạn số meter và số giá trị tag. Đây là lớp bảo vệ bổ sung khi một instrumentation vô tình tạo quá nhiều series.

Giới hạn tổng số meter được đăng ký:

```java
registry.config().meterFilter(
        MeterFilter.maximumAllowableMetrics(2_000));
```

Giới hạn số giá trị tag `uri` cho nhóm meter HTTP:

```java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny()));
```

Trong ví dụ thứ hai, tối đa 100 giá trị khác nhau của tag `uri` được chấp nhận cho meter có tên bắt đầu bằng `http.server.requests`. Khi vượt giới hạn, filter được truyền ở tham số cuối (`MeterFilter.deny()`) quyết định cách xử lý meter mới. Có thể chọn một filter khác nếu muốn áp dụng chính sách thay thế phù hợp.

Các giới hạn này không thay thế thiết kế tag có cardinality thấp. Nếu tag chứa user ID hoặc URL thô, giới hạn chỉ chặn bớt hậu quả sau khi vấn đề đã xuất hiện; hãy chuẩn hóa tag về route template hoặc nhóm hữu hạn ngay trong instrumentation.

## 9. Kiểm thử filter với SimpleMeterRegistry

Có thể kiểm tra filter bằng `SimpleMeterRegistry` mà không cần backend bên ngoài. Test nên xác nhận cả meter bị từ chối và meter vẫn được chấp nhận:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterFilterTest {
    @Test
    void deniesDebugPrefixAndKeepsBusinessMeters() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            registry.config().meterFilter(
                    MeterFilter.denyNameStartsWith("internal.debug."));

            Counter debug = Counter.builder("internal.debug.events")
                    .register(registry);
            Counter orders = Counter.builder("orders.created")
                    .register(registry);

            debug.increment();
            orders.increment();

            assertThat(registry.find("internal.debug.events").counter())
                    .isNull();

            Counter registeredOrders = registry.find("orders.created").counter();
            assertThat(registeredOrders).isNotNull();
            assertThat(registeredOrders.count()).isEqualTo(1.0);
        }
    }
}
```

Test này kiểm tra filter được áp dụng khi đăng ký meter: meter debug không xuất hiện trong registry, còn counter nghiệp vụ vẫn tồn tại và ghi nhận đúng một lần.

Với predicate tag, hãy tạo hai meter cùng tên nhưng có tag khác nhau, sau đó xác nhận chỉ meter khớp điều kiện bị từ chối. Với giới hạn cardinality, đăng ký nhiều giá trị tag khác nhau và xác nhận các giá trị vượt ngưỡng không tạo meter hoạt động.

Unit test với Simple registry xác minh chính sách ở lớp Micrometer. Nếu cần xác nhận output Prometheus, thêm integration test bằng `PrometheusMeterRegistry` hoặc endpoint `/actuator/prometheus` để bảo đảm meter bị lọc không xuất hiện trong exposition.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ filter loại bỏ dữ liệu đã có ở backend | Dữ liệu lịch sử vẫn còn trong Prometheus hoặc hệ thống nhận | Filter chỉ chặn đăng ký/export trong tương lai; xử lý retention ở backend nếu cần |
| Dùng `acceptNameStartsWith` như allowlist hoàn chỉnh | Meter không khớp vẫn có thể đi qua các filter khác | Dùng predicate deny phủ định nếu muốn từ chối mọi tên ngoài prefix |
| Thêm filter sau khi meter đã đăng ký | Meter cũ vẫn tồn tại trong registry | Cấu hình filter trước khi component tạo meter |
| Đặt filter ACCEPT quá sớm | Các filter DENY phía sau có thể không được chạy | Sắp xếp thứ tự hoặc hợp nhất điều kiện |
| Lọc theo tên export của Prometheus | Không khớp tên canonical trong `Meter.Id` | Dùng tên Micrometer trước naming convention |
| Dùng allowlist ở registry dùng chung | Có thể mất metric Actuator, JVM hoặc thư viện | Liệt kê phạm vi được phép có chủ đích và test các meter cần giữ |
| Dùng giới hạn tag thay cho thiết kế tag | Cardinality vẫn có thể cao đến khi chạm giới hạn | Chuẩn hóa giá trị tag từ đầu và đặt giới hạn phòng vệ |

## 11. Quy trình thiết kế và áp dụng filter

Khi cần lọc meter, hãy thực hiện theo trình tự:

1. Xác định nhóm meter không cần xuất hoặc cần giới hạn.
2. Lấy tên canonical, type và tag thực tế từ instrumentation hoặc registry.
3. Chọn cách lọc: tên chính xác, prefix hoặc predicate trên `Meter.Id`.
4. Xác định rõ chính sách là deny một nhóm hay chỉ accept một nhóm; không nhầm `acceptNameStartsWith` với allowlist.
5. Đăng ký filter sớm và kiểm tra thứ tự nếu có nhiều filter.
6. Bổ sung giới hạn tổng meter hoặc số giá trị tag khi phù hợp.
7. Viết unit test cho cả trường hợp bị từ chối và được chấp nhận.
8. Kiểm tra endpoint export hoặc payload của registry đích.
9. Theo dõi cardinality và log đăng ký để phát hiện chính sách lọc quá rộng hoặc xung đột.

`MeterFilter` giúp kiểm soát meter tại thời điểm đăng ký, dựa trên tên và định danh của meter. Khi dùng đúng tên canonical, predicate rõ ràng và thứ tự filter có chủ đích, ứng dụng có thể giảm dữ liệu không cần thiết, giới hạn cardinality và giữ lại những metrics quan trọng cho vận hành.
