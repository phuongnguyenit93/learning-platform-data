# Không có meter do đăng ký sai registry hoặc bộ lọc từ chối

Khi một metric không xuất hiện trên dashboard hoặc endpoint scrape, nguyên nhân có thể nằm ở hai điểm rất khác nhau: meter được đăng ký vào một `MeterRegistry` khác với registry đang được export, hoặc meter bị `MeterFilter` từ chối hay biến đổi trong quá trình đăng ký. Cả hai trường hợp đều có thể khiến code gọi `increment()` hoặc `record()` bình thường nhưng hệ thống giám sát không nhìn thấy metric mong đợi.

Với module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, hãy lần theo cùng một đường đi từ nơi tạo meter, registry nhận meter, filter áp dụng lên registry đó, đến endpoint hoặc exporter. Đừng kết luận meter bị mất chỉ vì một truy vấn Actuator hoặc dashboard không tìm thấy tên; trước hết cần xác định đang kiểm tra đúng registry, đúng meter name và đúng tag set.

## 1. Phân biệt ba tình huống thường bị gọi chung là “mất meter”

| Tình huống | Điều thực sự xảy ra | Dấu hiệu |
| --- | --- | --- |
| Sai registry | Meter được đăng ký ở registry A, nhưng endpoint/export đọc registry B | Có thể đọc được meter ở A nhưng không thấy ở B. |
| Filter từ chối | Registry nhận yêu cầu đăng ký nhưng filter trả về quyết định deny | Meter không được đưa vào tập meter hoạt động; builder có thể trả về no-op meter. |
| Sai identity khi tìm | Meter vẫn tồn tại nhưng tên hoặc tag không khớp truy vấn | Tìm theo tên/tag khác trả về không có kết quả. |

Ba tình huống này cần cách điều tra khác nhau. Kiểm tra `count()` trên một meter cục bộ không chứng minh meter nằm trong registry được Spring Boot export. Ngược lại, không tìm thấy meter bằng một bộ tag không chính xác cũng không chứng minh filter đã từ chối nó.

## 2. MeterRegistry là nơi sở hữu meter

Mỗi `MeterRegistry` quản lý các meter được đăng ký trên chính registry đó. Hai registry độc lập có thể cùng chứa một meter name và tag set nhưng có dữ liệu riêng, lifecycle riêng và exporter riêng.

Ví dụ:

```java
SimpleMeterRegistry localRegistry = new SimpleMeterRegistry();
PrometheusMeterRegistry prometheusRegistry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

Counter counter = Counter.builder("shop.orders.created")
        .register(localRegistry);

counter.increment();
```

Counter trên thuộc `localRegistry`. Nếu ứng dụng scrape `prometheusRegistry`, metric không xuất hiện ở đó vì meter chưa được đăng ký vào registry này.

Điểm cần nhớ:

- Meter không tự động được chia sẻ giữa mọi registry trong JVM.
- Gọi `registryA.counter(...)` không đăng ký meter vào `registryB`.
- Hai registry có cùng meter name không có nghĩa chúng đang đọc cùng một object meter.
- Exporter chỉ xuất dữ liệu từ registry mà nó được gắn vào.
- `MeterRegistry` được inject ở một component có thể khác registry mà test hoặc endpoint đang kiểm tra nếu ứng dụng tự tạo thêm registry.

## 3. Các cách đăng ký nhầm registry

Một lỗi thường gặp là tự tạo registry trong service thay vì dùng registry do Spring quản lý:

```java
@Service
public class OrderMetrics {
    private final Counter created;

    public OrderMetrics() {
        MeterRegistry registry = new SimpleMeterRegistry();
        this.created = Counter.builder("shop.orders.created")
                .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
```

Service ghi nhận counter trong `SimpleMeterRegistry` riêng. Spring Boot có thể đang export một Prometheus hoặc OTLP registry khác; do đó endpoint production không nhận được meter này.

Cách phù hợp là inject registry do application context quản lý:

```java
@Service
public class OrderMetrics {
    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("shop.orders.created")
                .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
```

Cần tránh cả các trường hợp sau:

- Tạo `SimpleMeterRegistry` chỉ để sử dụng trong một bean production.
- Tạo registry mới trong mỗi request hoặc mỗi lần gọi service.
- Đăng ký meter qua registry test nhưng kiểm tra một registry khác.
- Inject một registry bằng `@Qualifier` không đúng bean.
- Tự tạo registry Prometheus trong khi Spring Boot đang quản lý registry khác.
- Tạo meter trong một thư viện hoặc module con bằng registry riêng mà không kết nối registry đó với exporter chính.

## 4. Xác minh registry được Spring Boot quản lý

Trong ứng dụng Spring Boot, inject `MeterRegistry` qua constructor thường là lựa chọn phù hợp:

```java
@Component
public class CheckoutMetrics {
    private final MeterRegistry registry;
    private final Timer checkoutTimer;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.checkoutTimer = Timer.builder("shop.checkout.duration")
                .register(registry);
    }
}
```

Khi điều tra, hãy kiểm tra:

1. Component đang tạo meter inject bean `MeterRegistry` nào.
2. Registry đó có phải registry hoặc composite registry mà exporter sử dụng không.
3. Prometheus/OTLP registry dependency có mặt trong runtime classpath không.
4. Có bean registry tự tạo nào làm thay đổi wiring không.
5. Test có đang thay registry production bằng `SimpleMeterRegistry` hay mock không.

Không dựa vào tên bean để đoán exporter. Hãy xem kiểu registry thực tế trong application context và cấu hình của phiên bản Spring Boot đang dùng. Khi có nhiều bean cùng kiểu, `@Primary`, `@Qualifier` hoặc `CompositeMeterRegistry` có thể ảnh hưởng bean được inject.

## 5. Hiểu CompositeMeterRegistry

Spring Boot hoặc ứng dụng có thể dùng `CompositeMeterRegistry` để gửi cùng meter đến nhiều registry con. Khi meter được đăng ký vào composite, composite chuyển thao tác đăng ký và ghi nhận đến các child registry đã được thêm vào.

```java
CompositeMeterRegistry composite = new CompositeMeterRegistry();
PrometheusMeterRegistry prometheus =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

composite.add(prometheus);

Counter counter = composite.counter("shop.orders.created");
counter.increment();
```

Trong ví dụ, counter được tạo qua composite và có thể được chuyển đến child Prometheus registry. Nếu child registry chưa được thêm hoặc ứng dụng ghi trực tiếp vào một registry độc lập khác, endpoint Prometheus không nhất thiết nhìn thấy dữ liệu.

Khi dùng composite, kiểm tra:

- Registry con mong muốn đã được thêm vào composite chưa.
- Meter được tạo qua composite hay qua child registry riêng.
- Child registry có bị đóng hoặc gỡ khỏi composite không.
- Filter được cấu hình trên composite hay trên child registry cụ thể.
- Endpoint scrape đang phục vụ child registry nào.

Đừng nhầm việc một meter xuất hiện trong `CompositeMeterRegistry` với việc mọi child registry đều đã export meter đó thành công. Cần kiểm tra output của registry đích.

## 6. Xác minh meter identity trước khi nghi ngờ filter

Meter identity được xác định bởi tên và tập tag. Tên đúng nhưng tag khác vẫn tạo một meter identity khác.

Ví dụ:

```java
Counter.builder("shop.orders.created")
        .tag("channel", "web")
        .register(registry)
        .increment();
```

Truy vấn không có tag hoặc dùng tag khác có thể dẫn đến kết quả khác với mong đợi. Dùng API tìm kiếm để kiểm tra:

```java
Meter meter = registry.find("shop.orders.created")
        .tag("channel", "web")
        .meter();

assertThat(meter).isNotNull();
```

Các điểm cần đối chiếu:

- Tên meter trong code có đúng chính tả và namespace không.
- Tag key có đúng tên không, ví dụ `result` khác `status`.
- Tag value có đúng chính tả, chữ hoa/thường và cách chuẩn hóa không.
- Có `MeterFilter` đổi tên hoặc đổi tag không.
- Có convention backend đổi tên metric khi export không.

Tên trong `/actuator/metrics` thường là tên Micrometer. Tên trong Prometheus exposition có thể được chuẩn hóa thành dấu gạch dưới và thêm hậu tố theo loại meter. Không dùng tên Prometheus đã chuẩn hóa để truy vấn Actuator nếu hai tên khác nhau.

## 7. MeterFilter quyết định meter được đăng ký như thế nào

`MeterFilter` là extension point áp dụng cho một `MeterRegistry`. Filter có thể:

- Cho phép meter.
- Từ chối meter.
- Biến đổi `Meter.Id`, chẳng hạn tên hoặc tag.
- Điều chỉnh cấu hình phân phối của meter.
- Giới hạn số meter hoặc số giá trị tag được phép.

Ví dụ từ chối tất cả meter có tên bắt đầu bằng `internal.`:

```java
registry.config().meterFilter(
        MeterFilter.denyNameStartsWith("internal.")
);
```

Khi một meter bị deny, registry không đưa meter hoạt động đó vào tập meter được quản lý như bình thường. Tùy API và implementation, builder có thể trả về một no-op meter; lời gọi `increment()` trên no-op vẫn không ném lỗi nhưng không tạo sample được export.

Đây là lý do ứng dụng có thể chạy bình thường trong khi metric không xuất hiện.

## 8. Phân biệt ACCEPT, DENY và NEUTRAL

Các filter sử dụng quyết định `MeterFilterReply`:

| Reply | Ý nghĩa |
| --- | --- |
| `ACCEPT` | Chấp nhận meter theo quyết định của filter. |
| `DENY` | Từ chối meter. |
| `NEUTRAL` | Filter hiện tại không đưa ra quyết định cuối cùng; chuỗi filter có thể tiếp tục đánh giá. |

Các helper như `MeterFilter.denyNameStartsWith(...)` và `MeterFilter.acceptNameStartsWith(...)` tạo chính sách theo tên. Khi có nhiều filter, thứ tự cấu hình và quyết định của từng filter có thể ảnh hưởng kết quả cuối cùng. Hãy đọc toàn bộ cấu hình filter trên registry đích, không chỉ tìm một filter deny riêng lẻ.

Không nên thêm filter `ACCEPT` một cách tùy tiện để “ghi đè” mọi filter trước đó. Một quyết định đã kết thúc chuỗi filter có thể không được filter sau thay đổi. Thiết kế thứ tự filter có chủ đích và test kết quả trên registry thật.

## 9. Tìm filter từ chối meter

Các helper thường gặp:

```java
registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("internal."));

registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("debug."));

registry.config()
        .meterFilter(MeterFilter.maximumAllowableMetrics(500));
```

Khi metric biến mất, tìm các quy tắc như:

- `MeterFilter.deny()` hoặc filter tùy chỉnh luôn trả về `DENY`.
- `denyNameStartsWith(...)` loại một namespace.
- `maximumAllowableMetrics(...)` giới hạn tổng số meter.
- `maximumAllowableTags(...)` giới hạn số giá trị của một tag.
- Filter tùy chỉnh trả về `DENY` theo tên, tag, type hoặc trạng thái runtime.
- Filter đổi ID khiến metric xuất hiện dưới tên/tag khác.

`maximumAllowableMetrics` và `maximumAllowableTags` thường được dùng như hàng rào cardinality. Khi chạm giới hạn, meter mới có thể bị từ chối hoặc xử lý theo policy được cấu hình. Vì vậy, cần xem giới hạn có bị chạm hay không trước khi kết luận instrumentation không chạy.

## 10. Filter có thể đổi tên hoặc tag thay vì từ chối

Không phải mọi trường hợp metric không tìm thấy đều là deny. Filter cũng có thể map ID:

```java
registry.config().meterFilter(new MeterFilter() {
    @Override
    public Meter.Id map(Meter.Id id) {
        if (id.getName().equals("shop.orders.created")) {
            return id.withName("shop.orders.total");
        }
        return id;
    }
});
```

Sau khi map, metric có thể xuất hiện dưới `shop.orders.total`. Nếu dashboard hoặc test vẫn tìm `shop.orders.created`, kết quả sẽ là không có meter dù meter đã được đăng ký và đổi tên.

Filter cũng có thể chuẩn hóa tag value, bỏ tag hoặc thay tag key theo policy. Khi điều tra, hãy so sánh cả meter ID trước và sau filter, đồng thời xem exposition cuối cùng.

Không dùng filter để âm thầm thay đổi ý nghĩa nghiệp vụ. Nếu map tag value, hãy bảo đảm giá trị mới vẫn phân biệt đúng nhóm dữ liệu mà dashboard cần.

## 11. Filter phải được cấu hình trên đúng registry và đúng thời điểm

Một filter chỉ tác động đến registry được gắn nó. Thêm filter vào `SimpleMeterRegistry` trong test không có nghĩa Prometheus registry production cũng nhận filter đó; ngược lại, filter trên child registry có thể chỉ ảnh hưởng child đó.

Nên cấu hình filter trong giai đoạn khởi tạo registry, trước khi các meter nghiệp vụ được đăng ký. Với Spring Boot, có thể dùng `MeterRegistryCustomizer`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsFilterConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> meterPolicy() {
        return registry -> registry.config()
                .meterFilter(MeterFilter.denyNameStartsWith("internal."));
    }
}
```

Customizer giúp áp dụng policy khi registry được cấu hình trong application context. Package và cơ chế auto-configuration cần tương thích với phiên bản Spring Boot của dự án.

Không nên thêm hoặc thay đổi filter sau khi meter đã được đăng ký rồi kỳ vọng mọi meter cũ tự động được tạo lại theo policy mới. Filter chủ yếu tham gia quá trình đăng ký meter; với thay đổi cấu hình runtime, hãy xác minh hành vi của registry cụ thể và cân nhắc tạo lại application context trong test.

## 12. Kiểm tra meter bằng Actuator

Nếu endpoint metrics được expose, `/actuator/metrics` liệt kê tên meter mà registry của Actuator cung cấp. Sau đó có thể đọc meter cụ thể:

```bash
curl.exe http://localhost:8080/actuator/metrics
curl.exe http://localhost:8080/actuator/metrics/shop.orders.created
```

Nếu không thấy meter trong danh sách:

1. Xác nhận component đã khởi tạo và đường code đăng ký meter đã chạy.
2. Kiểm tra registry được inject.
3. Kiểm tra filter trên registry đó.
4. Kiểm tra tên và tag identity.
5. Xác minh endpoint đang đọc registry dự kiến.

Nếu endpoint trả về meter nhưng Prometheus không có metric, tiếp tục kiểm tra `/actuator/prometheus`, registry Prometheus và cấu hình scrape. Actuator metrics JSON và Prometheus exposition là hai bề mặt khác nhau.

## 13. Kiểm tra trực tiếp Prometheus exposition

Nếu ứng dụng dùng Prometheus registry, có thể gọi `scrape()` để xem nội dung mà registry xuất:

```java
PrometheusMeterRegistry prometheusRegistry = ...;

String exposition = prometheusRegistry.scrape();
assertThat(exposition).contains("shop_orders_created_total");
```

Nếu meter xuất hiện trong Actuator nhưng không có trong Prometheus exposition, có thể Actuator đang đọc registry khác, Prometheus child registry chưa được nối vào composite, filter ở Prometheus registry từ chối meter hoặc tên đã được map.

Khi so sánh, chú ý naming convention: Micrometer name `shop.orders.created` có thể trở thành `shop_orders_created_total` trong Prometheus. Kiểm tra output thật thay vì suy ra tên bằng cách thay dấu chấm thủ công.

## 14. Kiểm thử filter deny và meter hợp lệ

Một unit test có thể chứng minh filter từ chối đúng meter và vẫn cho phép meter khác:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterFilterTest {
    @Test
    void deniesInternalMetersAndKeepsBusinessMeters() {
        try (MeterRegistry registry = new SimpleMeterRegistry()) {
            registry.config().meterFilter(
                    MeterFilter.denyNameStartsWith("internal.")
            );

            Counter denied = Counter.builder("internal.cache.refresh")
                    .register(registry);
            Counter accepted = Counter.builder("shop.orders.created")
                    .register(registry);

            denied.increment();
            accepted.increment();

            assertThat(registry.find("internal.cache.refresh").meter())
                    .isNull();
            assertThat(registry.find("shop.orders.created").counter())
                    .isNotNull();
            assertThat(registry.find("shop.orders.created").counter().count())
                    .isEqualTo(1.0);
        }
    }
}
```

Test này minh họa hành vi filter ở registry đơn giản. Nó không chứng minh Prometheus hoặc OTLP registry production được cấu hình giống vậy. Với lỗi production, hãy lặp lại test bằng đúng registry/export path cần kiểm tra.

## 15. Kiểm thử trường hợp đăng ký nhầm registry

Có thể mô phỏng hai registry độc lập để chứng minh meter chỉ xuất hiện tại registry nhận đăng ký:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class RegistryOwnershipTest {
    @Test
    void meterExistsOnlyInRegistryUsedForRegistration() {
        try (SimpleMeterRegistry registryA = new SimpleMeterRegistry();
             SimpleMeterRegistry registryB = new SimpleMeterRegistry()) {
            Counter counter = Counter.builder("shop.orders.created")
                    .register(registryA);
            counter.increment();

            assertThat(registryA.find("shop.orders.created").counter())
                    .isNotNull();
            assertThat(registryB.find("shop.orders.created").meter())
                    .isNull();
        }
    }
}
```

Trong integration test Spring Boot, nên inject registry từ application context và kiểm tra đúng registry mà endpoint/exporter sử dụng. Tránh tạo một registry mới trong test rồi coi kết quả của nó là bằng chứng cho registry production.

## 16. Kiểm tra các giới hạn cardinality

Nếu dùng `maximumAllowableMetrics` hoặc `maximumAllowableTags`, hãy xác minh giới hạn có đang làm meter mới bị từ chối hay không. Ví dụ:

```java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "shop.http.requests",
                "route",
                100,
                MeterFilter.deny()
        )
);
```

Khi vượt quá 100 giá trị `route`, filter xử lý meter vượt giới hạn theo policy được cung cấp. Trong ví dụ, policy là deny. Đây là hàng rào bảo vệ registry trước cardinality cao, nhưng cũng có thể khiến metric mới không xuất hiện.

Nếu metric biến mất sau một đợt deploy có nhiều route/tag mới, kiểm tra:

- Số lượng meter hiện tại.
- Số lượng giá trị tag đã được đăng ký.
- Filter giới hạn nào đang hoạt động.
- Log hoặc telemetry cảnh báo về việc đạt ngưỡng nếu ứng dụng có ghi nhận.
- Có tag động như ID, URL hoặc exception message hay không.

Không tăng giới hạn ngay lập tức để xử lý triệu chứng. Trước tiên xác định tag nào làm cardinality tăng và liệu tag đó có nên được chuẩn hóa thành route template hoặc nhóm hữu hạn hay không.

## 17. Quy trình chẩn đoán theo thứ tự

Khi meter không xuất hiện, thực hiện lần lượt:

1. **Xác nhận code đã chạy:** đặt breakpoint hoặc test xác minh constructor/method đăng ký meter đã được thực thi.
2. **Ghi nhận registry đích:** xác định object registry được truyền vào `register(registry)`.
3. **Tìm meter tại registry đó:** dùng `registry.find(name).meter()` và kiểm tra tag identity.
4. **Kiểm tra filter:** đọc các filter trên đúng registry, tìm deny, map và giới hạn cardinality.
5. **Kiểm tra composite:** xác nhận registry con của exporter đã được kết nối.
6. **Kiểm tra Actuator:** tìm tên Micrometer tại `/actuator/metrics`.
7. **Kiểm tra exposition/export:** gọi `scrape()` hoặc endpoint exporter.
8. **Kiểm tra naming convention:** đối chiếu tên và tag sau chuẩn hóa.
9. **Kiểm tra backend:** xác nhận scrape target, ingest pipeline và truy vấn dashboard.

Không thay đổi nhiều filter hoặc registry cùng lúc. Hãy thu hẹp nguyên nhân ở từng tầng để tránh tạo thêm cấu hình khiến lỗi khó tái hiện.

## 18. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Counter tăng trong code nhưng Actuator không thấy | Đăng ký vào registry riêng | So sánh registry ở call site với registry trong application context. |
| Meter có trong `SimpleMeterRegistry` nhưng không có trên Prometheus | Test và production dùng registry khác | Kiểm tra Prometheus registry hoặc child registry của composite. |
| Meter không xuất hiện ở bất kỳ endpoint nào | Filter deny hoặc code đăng ký chưa chạy | Kiểm tra filter và `registry.find(...)`. |
| Metric xuất hiện dưới tên khác | `MeterFilter.map(...)` hoặc naming convention | Kiểm tra Meter ID và exposition. |
| Chỉ một số tag value bị mất | Filter giới hạn tag/cardinality | Kiểm tra `maximumAllowableTags` và policy khi vượt ngưỡng. |
| Meter xuất hiện trong Actuator nhưng thiếu ở scrape | Endpoint đọc registry khác hoặc Prometheus filter | Kiểm tra registry thực tế của hai endpoint. |
| Sau khi thêm filter, metric cũ vẫn còn | Filter được thêm sau đăng ký hoặc registry không được tạo lại | Kiểm tra thứ tự khởi tạo và lifecycle registry. |
| Dashboard không tìm thấy nhưng exposition có metric | Query dùng sai tên/tag hoặc thời gian scrape | Kiểm tra raw series và truy vấn dashboard. |

## 19. Những lỗi thường gặp

- **Tạo `SimpleMeterRegistry` trong bean production:** meter không đi vào registry exporter.
- **Đăng ký meter vào registry A rồi scrape registry B:** dữ liệu không được chia sẻ tự động.
- **Chỉ kiểm tra `counter.count()`:** chưa chứng minh meter được export.
- **Không kiểm tra tag identity:** truy vấn thiếu hoặc sai tag có thể trả về rỗng.
- **Bỏ qua filter tùy chỉnh:** một filter có thể từ chối theo tên hoặc tag.
- **Không để ý filter map ID:** meter có thể tồn tại dưới tên/tag khác.
- **Cấu hình filter trên registry không đúng:** policy không tác động đến exporter đang gặp sự cố.
- **Thêm filter sau khi meter đã đăng ký:** kỳ vọng thay đổi retroactive có thể sai.
- **Chạm ngưỡng cardinality:** meter mới có thể bị deny.
- **Nhầm tên Micrometer với tên backend:** Prometheus có naming convention riêng.
- **Dùng registry test thay cho registry production:** test xanh nhưng export thực tế vẫn lỗi.

## 20. Checklist xử lý sự cố không có meter

- [ ] Xác minh đoạn code đăng ký meter đã được thực thi.
- [ ] Xác định chính xác `MeterRegistry` nhận meter.
- [ ] Xác minh registry đó là registry exporter đang dùng hoặc đã nối vào composite.
- [ ] Tìm meter bằng đúng tên và toàn bộ tag key/value.
- [ ] Kiểm tra `MeterFilter` deny, accept, map và filter tùy chỉnh.
- [ ] Kiểm tra `maximumAllowableMetrics` và `maximumAllowableTags`.
- [ ] Xác minh filter được cấu hình trước khi meter đăng ký.
- [ ] Kiểm tra Actuator metrics endpoint.
- [ ] Kiểm tra Prometheus/OTLP exposition hoặc export path.
- [ ] Phân biệt tên Micrometer với tên đã chuẩn hóa của backend.
- [ ] Kiểm thử cả meter bị từ chối và meter hợp lệ.
- [ ] Không thêm registry hoặc tăng cardinality chỉ để che triệu chứng.

Khi một meter không xuất hiện, hãy xác định nó được đăng ký ở registry nào trước, rồi kiểm tra filter và meter identity trên đúng registry đó. Registry sai khiến dữ liệu đi vào một nơi exporter không đọc; filter deny khiến meter không được đăng ký như một meter hoạt động; filter map hoặc naming convention có thể khiến metric xuất hiện dưới tên khác. Sau khi xác minh ba khả năng này, kiểm tra endpoint và backend để tìm lỗi ở lớp export. Cách lần theo từng ranh giới giúp sửa đúng cấu hình mà không tạo thêm registry hoặc làm cardinality tăng ngoài kiểm soát.
