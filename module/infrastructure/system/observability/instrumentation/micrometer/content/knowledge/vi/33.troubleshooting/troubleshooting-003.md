# Khác tên giữa mã Java, Actuator và hệ thống nhận

Một metric có thể xuất hiện dưới các tên khác nhau ở từng lớp của hệ thống observability. Trong mã Java, Micrometer thường dùng tên chữ thường phân tách bằng dấu chấm. Spring Boot Actuator dùng tên meter chuẩn tắc để tra cứu. Registry đích áp dụng naming convention riêng, có thể đổi dấu phân cách, chuẩn hóa ký tự, thêm đơn vị hoặc hậu tố theo loại meter. Hệ thống nhận còn có thể áp dụng namespace, mapping hoặc quy tắc hiển thị riêng.

Vì vậy, nhìn thấy **http.server.requests** trong Java nhưng không tìm thấy chuỗi đó trên Prometheus chưa đủ để kết luận metric bị mất. Cần xác định tên đã thay đổi ở lớp nào, rồi so sánh Meter ID, Actuator response và payload export thực tế.

Bài học thuộc chương Xử lý sự cố của module Micrometer: sử dụng counter, gauge, timer, distribution summary và tag có kiểm soát; tích hợp Spring Boot; xuất metrics đến hệ thống giám sát; và diễn giải số liệu một cách nhất quán.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt tên trong lời gọi Java, tên Meter ID, tên tra cứu ở Actuator và tên export.
- Giải thích vì sao cùng một meter có tên khác nhau trên Prometheus, Atlas, Graphite hoặc InfluxDB.
- Phân biệt NamingConvention với MeterFilter.
- Kiểm tra metric bằng /actuator/metrics và /actuator/prometheus.
- Xác định tác động của MeterRegistryCustomizer, common tags và registry cụ thể.
- Nhận diện hậu tố đơn vị, loại meter và cách chuẩn hóa tag.
- Phát hiện metric bị đổi tên, bị từ chối, bị đăng ký vào registry khác hoặc bị gộp do thiếu tag filter.
- Viết kiểm thử xác nhận Meter ID và dữ liệu export.
- Thiết lập quy trình điều tra có thể lặp lại khi tên metric không khớp.

## Một metric đi qua những lớp tên nào?

Không nên coi chuỗi tên xuất hiện trong mọi công cụ là một giá trị duy nhất. Một meter đi qua các lớp sau:

| Lớp | Nơi quan sát | Ý nghĩa |
|---|---|---|
| Tên trong instrumentation | Java builder, annotation hoặc binder | Chuỗi tên mà code yêu cầu đăng ký |
| Meter ID | Meter.getId() trong registry | Danh tính meter sau các phép biến đổi của MeterFilter |
| Tên Actuator | /actuator/metrics/{name} | Tên chuẩn tắc được dùng để tra cứu meter trong Spring-managed registry |
| Tên export | /actuator/prometheus, OTLP hoặc registry khác | Tên được chuyển theo NamingConvention của registry đích |
| Tên ở hệ thống nhận | Prometheus, Grafana, Atlas, Datadog hoặc nền tảng khác | Tên đã được ingestion, namespace hoặc giao diện của hệ thống nhận xử lý |

Có hai cơ chế thường bị nhầm lẫn:

- MeterFilter có thể đổi Meter ID trước khi meter được đăng ký, ví dụ đổi tên hoặc tag.
- NamingConvention chuyển tên và tag sang quy ước của registry đích khi xuất dữ liệu. Nó không nhất thiết thay đổi tên chuẩn tắc mà code dùng để tra cứu meter.

Spring Boot metrics endpoint tra cứu theo tên chuẩn tắc trong Meter ID, thường trùng với tên trong code nếu không có MeterFilter đổi tên. Endpoint này không dùng tên đã được chuẩn hóa riêng cho hệ thống giám sát. Ví dụ, nếu jvm.memory.max được Prometheus hiển thị thành jvm_memory_max, selector ở /actuator/metrics vẫn là jvm.memory.max. Nếu MeterFilter đổi tên Meter ID thành business.payment.calls, selector Actuator cũng phải dùng tên sau filter.

## Ví dụ: một tên Timer, nhiều tên export

Micrometer khuyến nghị tên chữ thường phân tách bằng dấu chấm:

~~~java
Timer authorizationTimer = Timer.builder(
        "business.payment.authorization"
    )
    .description("Thời lượng xử lý authorization")
    .tag("provider", "gateway-a")
    .register(registry);
~~~

Tên chuẩn tắc của meter là business.payment.authorization nếu không có filter đổi tên. Khi export, từng registry áp dụng quy ước riêng. Ví dụ được tài liệu Micrometer minh họa với Timer http.server.requests:

| Hệ thống nhận | Tên theo naming convention |
|---|---|
| Prometheus | http_server_requests_duration_seconds |
| Atlas | httpServerRequests |
| Graphite | http.server.requests |
| InfluxDB | http_server_requests |

Với Prometheus, một Timer có thể được biểu diễn bằng metric family với các sample như count, sum và bucket tùy cấu hình phân phối. Vì vậy, tên cơ sở có thể xuất hiện kèm hậu tố như _count, _sum hoặc _bucket. Tên và hậu tố cụ thể phụ thuộc loại meter, đơn vị, cấu hình histogram và phiên bản registry.

Đối với Counter, Prometheus thường dùng hậu tố _total để biểu diễn số tích lũy. Ví dụ tên chuẩn tắc business.payment.authorizations có thể được hiển thị thành business_payment_authorizations_total. Không tự nối _total vào tên Java chỉ vì nhìn thấy hậu tố đó trong Prometheus; registry có thể tự áp dụng và tạo hậu tố lặp.

## Vì sao Actuator và Prometheus dùng tên khác nhau?

Spring Boot có hai endpoint thường được dùng để điều tra:

- /actuator/metrics: endpoint chẩn đoán meter theo tên chuẩn tắc và tag.
- /actuator/prometheus: endpoint exposition cho Prometheus, sử dụng định dạng và naming convention của Prometheus registry.

Ví dụ, meter được đăng ký bằng tên business.payment.authorization:

~~~text
GET /actuator/metrics/business.payment.authorization
~~~

Khi cần lọc một tag:

~~~text
GET /actuator/metrics/business.payment.authorization?tag=provider:gateway-a
~~~

Nếu truy cập /actuator/metrics mà không truyền tên, endpoint liệt kê các tên meter có sẵn. Khi truyền tên, response có thể chứa measurements và availableTags. Giá trị đo được là tổng thống kê của các meter khớp tên và các tag đã lọc. Nếu bỏ qua tag, kết quả có thể cộng nhiều provider hoặc outcome vào cùng một measurement.

Prometheus scrape endpoint:

~~~text
GET /actuator/prometheus
~~~

Ở endpoint này, hãy tìm tên đã được chuẩn hóa, ví dụ business_payment_authorization_duration_seconds hoặc các sample tương ứng. Không dùng tên chuẩn tắc có dấu chấm để tìm trong exposition nếu registry đã chuyển sang snake case.

### Bật endpoint phục vụ chẩn đoán

Metrics endpoint không nhất thiết được expose qua HTTP mặc định. Có thể cấu hình rõ endpoint cần dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Để dùng /actuator/prometheus, ứng dụng cần có registry Prometheus tương ứng, thường là dependency micrometer-registry-prometheus. Endpoint cũng phải được phép truy cập theo cấu hình access và security của ứng dụng.

Trong môi trường production, chỉ expose các endpoint cần thiết và áp dụng cơ chế xác thực, phân quyền phù hợp. Không mở toàn bộ Actuator chỉ để kiểm tra một tên metric.

## Phân biệt NamingConvention và MeterFilter

Hai cơ chế này giải quyết hai vấn đề khác nhau:

| Cơ chế | Thời điểm và phạm vi | Ví dụ |
|---|---|---|
| NamingConvention | Chuyển tên/tag theo quy ước của một registry khi export | http.server.requests thành http_server_requests_duration_seconds trên Prometheus |
| MeterFilter | Chấp nhận, từ chối, đổi Meter ID hoặc cấu hình statistics khi đăng ký | Đổi tên meter, thêm/bỏ tag hoặc giới hạn tag values |

### NamingConvention

Mỗi Micrometer registry có naming convention phù hợp với hệ thống đích. Registry có thể chuyển dấu chấm thành dấu gạch dưới, loại ký tự không hợp lệ hoặc chuyển tên sang kiểu camel case. Quy tắc cũng có thể áp dụng cho tag key.

Không nên thay đổi tên trong code thành snake case chỉ để phù hợp với một backend. Tên dot notation là quy ước portable của Micrometer; registry chịu trách nhiệm chuyển sang dạng phù hợp với backend của nó.

Chỉ tùy chỉnh naming convention khi hệ thống nhận có yêu cầu cụ thể. Có thể đặt convention riêng trên registry:

~~~java
registry.config().namingConvention(myNamingConvention);
~~~

Nếu ứng dụng có nhiều registry, hãy xác định registry nào cần convention riêng. Không giả định một thay đổi naming convention cho Prometheus cũng phải áp dụng cho Graphite hoặc OTLP.

### MeterFilter

MeterFilter tác động đến Meter ID trước khi meter được đăng ký. Ví dụ đổi tên một nhóm meter:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(new MeterFilter() {
    @Override
    public Meter.Id map(Meter.Id id) {
        if (id.getName().equals("legacy.payment.calls")) {
            return id.withName("business.payment.calls");
        }
        return id;
    }
});
~~~

Đổi tag key có thể dùng helper:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(
    MeterFilter.renameTag(
        "business.payment",
        "provider",
        "gateway"
    )
);
~~~

Sau filter này, Meter ID có tag gateway; code tra cứu hoặc dashboard cần dùng đúng key sau biến đổi.

Tương tự, nếu filter đổi tên legacy.payment.calls thành business.payment.calls, Actuator sẽ tra cứu meter theo tên Meter ID mới. NamingConvention vẫn tiếp tục chuyển tên đó theo quy ước của registry khi export. MeterFilter chỉ tác động lúc meter được đăng ký; thêm filter sau khi meter đã tồn tại không tự đổi lại Meter ID của meter cũ. Vì vậy, hãy cấu hình filter và common tags trước khi các binder hoặc component đăng ký meter.

Một số filter thường dùng:

~~~java
registry.config()
    .meterFilter(MeterFilter.commonTags(
        "service", "checkout",
        "region", "ap-southeast-1"
    ))
    .meterFilter(MeterFilter.ignoreTags("legacy.tag"));
~~~

commonTags thêm dimension chung. ignoreTags bỏ các tag key được chỉ định. replaceTagValues có thể chuẩn hóa một số giá trị tag. maximumAllowableTags giới hạn số giá trị tag cho một meter prefix và tag key.

Filter được áp dụng theo thứ tự đăng ký. Nếu một filter từ chối meter, registry trả về meter NOOP; code vẫn có thể gọi increment() hoặc record() nhưng dữ liệu bị loại bỏ. Khi metric không xuất hiện, cần kiểm tra cả filter accept/deny, không chỉ kiểm tra tên.

MeterFilter nên có hành vi tĩnh dựa trên Meter ID. Nếu cần tag phụ thuộc request context, hãy gắn tag ở instrumentation hoặc dùng Observation convention/filter thích hợp, không biến MeterFilter thành bộ xử lý động theo từng request.

## Kiểm tra Meter ID trước khi kiểm tra tên export

Khi tên trong backend khác với dự kiến, bước đầu tiên là kiểm tra Meter ID đang tồn tại trong registry được ứng dụng sử dụng.

Ví dụ:

~~~java
Counter counter = Counter.builder("business.payment.authorizations")
    .description("Số authorization được ghi nhận")
    .tag("provider", "gateway-a")
    .register(registry);

Meter.Id id = counter.getId();

System.out.println("name=" + id.getName());
System.out.println("tags=" + id.getTags());
System.out.println("type=" + id.getType());
System.out.println("baseUnit=" + id.getBaseUnit());
~~~

Nếu id.getName() đã khác tên trong builder, hãy kiểm tra MeterFilter hoặc customizer. Nếu id.getName() vẫn là tên chuẩn tắc nhưng backend hiển thị chuỗi khác, hãy kiểm tra NamingConvention và quy tắc của hệ thống nhận.

Không nên dump toàn bộ danh sách meter trong mỗi request hoặc trong production hot path. Việc liệt kê toàn registry chỉ phù hợp với test, endpoint chẩn đoán có kiểm soát hoặc một lần điều tra giới hạn.

### Kiểm thử Meter ID với SimpleMeterRegistry

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MeterNameTest {

    @Test
    void keepsCanonicalNameAndExpectedTag() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter counter = Counter.builder("business.payment.authorizations")
            .tag("provider", "gateway-a")
            .register(registry);

        Meter.Id id = counter.getId();

        assertEquals("business.payment.authorizations", id.getName());
        assertEquals("gateway-a", id.getTag("provider"));

        registry.close();
    }
}
~~~

Test này kiểm tra tên và tag trong Meter ID của registry đơn giản. Nó không kiểm tra tên Prometheus vì SimpleMeterRegistry không export Prometheus exposition. Muốn xác minh tên backend, hãy dùng registry đích hoặc integration test đọc endpoint export thực tế.

### Kiểm thử tác động của MeterFilter

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class MeterFilterNameTest {

@Test
void appliesTagRenameBeforeRegisteringMeter() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config().meterFilter(
        MeterFilter.renameTag(
            "business.payment",
            "provider",
            "gateway"
        )
    );

    Counter counter = Counter.builder("business.payment.authorizations")
        .tag("provider", "gateway-a")
        .register(registry);

    Meter.Id id = counter.getId();

    assertEquals("business.payment.authorizations", id.getName());
    assertEquals("gateway-a", id.getTag("gateway"));
    assertNull(id.getTag("provider"));

    registry.close();
}
}
~~~

Test này chứng minh tag key đã bị đổi ngay trong Meter ID. Nếu dashboard vẫn truy vấn provider, kết quả sẽ không khớp dù metric đã được export thành công.

## Cấu hình đúng Spring-managed MeterRegistry

Spring Boot tự cấu hình composite MeterRegistry và thêm registry tương ứng khi dependency của registry có trên runtime classpath. Vì vậy, cùng một meter có thể được gửi đến nhiều hệ thống với naming convention khác nhau.

Nên inject MeterRegistry do Spring quản lý vào component:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentMetrics {

    private final Counter authorizations;

    public PaymentMetrics(MeterRegistry registry) {
        this.authorizations = Counter.builder(
                "business.payment.authorizations"
            )
            .description("Số authorization được ghi nhận")
            .register(registry);
    }

    public void authorizationRecorded() {
        authorizations.increment();
    }
}
~~~

Không tùy tiện trộn registry được inject với các static method của Metrics hoặc một registry tự tạo độc lập. Spring Boot có thể thêm các registry auto-configured vào global composite, nhưng registry tự tạo hoặc registry không được Spring quản lý có thể khiến metric xuất hiện ở một nơi mà Actuator không đọc.

### Thêm common tags trước khi meter được đăng ký

Có thể dùng MeterRegistryCustomizer để cấu hình registry do Spring Boot quản lý:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> metricsCommonTags() {
    return registry -> registry.config().commonTags(
        "service", "checkout",
        "region", "ap-southeast-1"
    );
}
~~~

MeterRegistryCustomizer được áp dụng trước khi các meter binder đăng ký meter. Điều này giúp common tags có mặt nhất quán trên meter tự tạo và meter có sẵn. Package import của MeterRegistryCustomizer có thể khác giữa các dòng Spring Boot; dùng package tương ứng với phiên bản dự án.

Nếu chỉ muốn cấu hình một registry cụ thể, khai báo customizer với generic type của registry đó, ví dụ PrometheusMeterRegistry. Cách này tránh vô tình áp dụng naming convention hoặc cấu hình riêng của một backend lên tất cả registry trong composite.

## Những nguyên nhân thường gặp khiến tên khác nhau

### Dấu phân cách và ký tự được chuẩn hóa

Micrometer dùng dot notation. Backend có thể dùng underscore, camel case hoặc quy tắc riêng. Ký tự không được backend chấp nhận cũng có thể bị loại bỏ hoặc thay thế.

Hai tên chuẩn tắc khác nhau có thể trở thành cùng một chuỗi sau chuẩn hóa. Ví dụ cache.gets và cache_gets có thể cùng được chuyển thành cache_gets trong hệ thống dùng dấu gạch dưới. Tránh đặt tên có khả năng va chạm sau khi chuyển đổi; hãy kiểm tra naming convention trước khi chuẩn hóa một nhóm metric lớn.

### Đơn vị và loại meter tạo hậu tố

Một Timer đo thời gian có thể được export với đơn vị seconds. Counter có thể có hậu tố _total; histogram có thể có _bucket, _sum và _count. Đây là cách backend biểu diễn loại meter và đơn vị, không nhất thiết là tên khác do code đăng ký.

Không tự thêm hậu tố backend vào tên Java. Giữ tên có ý nghĩa và để registry xử lý đơn vị cùng định dạng đích.

### Tag key bị đổi hoặc bị bỏ

Tag key cũng đi qua naming convention và MeterFilter. Ví dụ http.route có thể thành http_route trên Prometheus. Nếu filter đổi provider thành gateway, truy vấn theo provider sẽ không tìm thấy series tương ứng.

Tag value cũng có thể được chuẩn hóa hoặc escape theo backend. Không giả định rằng mọi tag value đều được lưu nguyên vẹn; kiểm tra raw exposition hoặc payload export.

### Common tags làm tăng số chiều

Common tags như service, region, instance, stack được thêm vào nhiều meter. Nếu Actuator query không lọc tag, measurements có thể tổng hợp nhiều series. Nếu backend UI mặc định group theo service hoặc instance, giá trị hiển thị có thể khác với một truy vấn tổng hợp ở Actuator.

Khi so sánh, phải giữ cùng bộ tag filter và cùng phạm vi instance. Một bên đang xem một provider trong một region, bên kia đang xem tổng tất cả provider và region thì hai con số không thể so sánh trực tiếp.

### Meter bị từ chối hoặc đăng ký vào registry khác

Một MeterFilter có thể deny meter hoặc giới hạn số meter/tag values. Registry có thể trả về NOOP meter; code không nhất thiết ném exception khi gọi meter đó. Ngoài ra, nếu component đăng ký meter trên registry tự tạo thay vì Spring-managed registry, Actuator có thể không nhìn thấy meter.

Kiểm tra MeterRegistry được inject, filter được áp dụng, registry có thực sự export và registry đích có đang enabled hay không.

### Hệ thống nhận áp dụng namespace hoặc mapping riêng

Một số nền tảng cho phép cấu hình prefix, namespace, integration mapping hoặc alias ở phía agent/collector. Khi đó raw endpoint của ứng dụng có thể đúng nhưng giao diện hệ thống nhận hiển thị tên khác. Hãy so sánh payload tại điểm export với tên cuối cùng sau ingestion để xác định thay đổi nằm ở collector hay backend.

## Quy trình chẩn đoán theo từng lớp

~~~mermaid
flowchart TD
    A[Metric không có tên như mong đợi] --> B{Meter ID có trong Spring registry?}
    B -->|Không| C[Kiểm tra code path, registry và MeterFilter]
    B -->|Có| D[Đọc Meter.Id name và tags]
    D --> E{Actuator metrics tra cứu được?}
    E -->|Không| F[Kiểm tra endpoint, registry và filter]
    E -->|Có| G[Đọc raw export endpoint]
    G --> H{Tên export đã chuẩn hóa?}
    H -->|Có| I[Đối chiếu tên và tag ở backend]
    H -->|Không| J[Kiểm tra NamingConvention và registry đích]
    I --> K[Kiểm tra namespace, mapping và query]
    J --> K
~~~

Thực hiện theo thứ tự sau để tránh đổi tên ở nhầm lớp:

1. **Ghi lại tên trong code.** Tìm builder, binder hoặc annotation tạo meter; ghi lại name, tag keys, tag values, type và base unit.
2. **Đọc Meter ID.** Trong test hoặc diagnostic code, kiểm tra meter.getId().getName(), getTags(), getType() và getBaseUnit(). Nếu tên đã khác, xem MeterFilter.
3. **Tra cứu bằng Actuator.** Dùng tên chuẩn tắc và thêm tag=KEY:VALUE để khoanh vùng. Nếu endpoint không tồn tại, kiểm tra exposure và security.
4. **Đọc raw export.** Với Prometheus, lấy nội dung /actuator/prometheus; tìm tên đã chuẩn hóa và các sample count/sum/bucket nếu có.
5. **So sánh tag.** Kiểm tra cả key và value. Đối chiếu common tags, tag rename, ignored tags và tag filter ở query.
6. **Kiểm tra registry cụ thể.** Xác định metric được đăng ký trên Spring-managed registry nào; kiểm tra registry dependency và cấu hình enable/disable.
7. **Kiểm tra hệ thống nhận.** Nếu raw export đúng, xem collector, namespace, mapping, relabeling, metric rename hoặc quy tắc hiển thị của backend.
8. **Kiểm tra collision.** So sánh các tên chuẩn tắc sau khi áp dụng quy tắc chuẩn hóa; tránh hai meter khác nhau bị rút về cùng một tên.
9. **Tạo test hồi quy.** Kiểm tra Meter ID và một integration test cho endpoint export để tên không bị thay đổi ngoài dự kiến.

### Lệnh kiểm tra nhanh

Tra cứu tên chuẩn tắc trong Actuator:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/business.payment.authorization"
~~~

Lọc một provider:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/business.payment.authorization?tag=provider:gateway-a"
~~~

Đọc exposition Prometheus:

~~~bash
curl -s "http://localhost:8080/actuator/prometheus"
~~~

Khi kiểm tra bằng browser hoặc terminal, tìm cả tên chuẩn tắc lẫn tên đã chuẩn hóa. Nếu dùng PowerShell, có thể pipe kết quả curl.exe qua Select-String với một phần tên metric đã chuyển đổi.

### Truy vấn Prometheus sau khi xác nhận tên export

Nếu raw exposition xác nhận Counter được export với tên business_payment_authorizations_total, có thể truy vấn:

~~~promql
sum(rate(business_payment_authorizations_total[5m]))
~~~

Nếu Timer export thành family http_server_requests_duration_seconds, có thể dùng sample count để tính throughput:

~~~promql
sum(rate(http_server_requests_duration_seconds_count[5m]))
~~~

Không sao chép tên từ ví dụ vào dashboard trước khi xác minh endpoint thực tế. Phiên bản registry, loại meter, cấu hình histogram và naming convention có thể làm tên sample khác nhau.

## Kiểm thử tên ở cả hai lớp

Một unit test với SimpleMeterRegistry kiểm tra tên chuẩn tắc và tag sau filter. Một integration test với registry đích kiểm tra định dạng export. Hai loại test giải quyết hai câu hỏi khác nhau:

| Test | Câu hỏi |
|---|---|
| Unit test Meter ID | Meter được đăng ký với tên và tag nào sau filter? |
| Integration test Actuator | Endpoint /actuator/metrics tra cứu được bằng tên nào? |
| Export test | Registry đích xuất tên, đơn vị và tag nào? |
| Backend smoke test | Collector và hệ thống nhận lưu/hiển thị tên nào? |

Nên có test cho những metric quan trọng dùng trong dashboard hoặc alert. Khi đổi meter name hoặc tag key, cập nhật đồng bộ query, recording rule, alert và tài liệu vận hành. Thay đổi tên metric có thể làm dashboard cũ mất dữ liệu dù instrumentation vẫn chạy bình thường.

## Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Java dùng dấu chấm, Prometheus dùng dấu gạch dưới | NamingConvention của Prometheus | Tra cứu bằng tên chuẩn tắc ở Actuator, tên export ở Prometheus |
| Actuator tìm được, backend không tìm được | Sai tên export, registry chưa export hoặc backend query sai | Đọc raw exposition trước |
| Actuator không tìm thấy meter | Đăng ký trên registry khác, meter chưa được tạo hoặc bị filter | Kiểm tra injected registry, Meter ID và MeterFilter |
| Tên Meter ID khác tên trong builder | MeterFilter đã đổi tên hoặc tag mapping | Kiểm tra filter theo thứ tự đăng ký |
| Metric Counter có hậu tố _total | Quy ước Prometheus cho counter | Không nối hậu tố vào tên Java theo cách thủ công |
| Timer có hậu tố seconds/count/sum/bucket | Registry biểu diễn đơn vị và thống kê Timer | Đối chiếu metric family và cấu hình histogram |
| Tag query trả về ít hoặc không có dữ liệu | Tag key/value bị đổi, bỏ hoặc không khớp | Kiểm tra Meter.Id.getTags() và raw export |
| Actuator trả tổng lớn hơn backend | Actuator query đang cộng nhiều tag sets hoặc khác phạm vi instance | Thêm tag filter và so sánh cùng phạm vi |
| Metric không xuất hiện nhưng code vẫn gọi increment | Meter bị deny và trả về NOOP | Kiểm tra MeterFilter và giới hạn metrics/tags |
| Có hai tên gần giống nhau | Tên code không thống nhất hoặc backend normalization | Chuẩn hóa tên canonical và kiểm tra collision |
| Metric xuất hiện trên backend khác nhưng không ở Prometheus | Registry composite hoặc cấu hình enable/disable khác nhau | Kiểm tra từng registry và dependency |
| Common tag không có trên một số meter | Tag được thêm sau khi meter đã đăng ký hoặc meter thuộc registry khác | Cấu hình customizer trước meter binders |
| Dashboard cũ đột nhiên trống sau deploy | Meter name hoặc tag key đã thay đổi | So sánh Meter ID trước/sau và cập nhật query đồng bộ |

## Checklist xử lý sự cố

- [ ] Đã ghi lại tên metric trong code và loại meter.
- [ ] Đã xác định Spring-managed MeterRegistry đang được dùng.
- [ ] Đã đọc Meter ID sau khi các MeterFilter áp dụng.
- [ ] Đã kiểm tra tên chuẩn tắc bằng /actuator/metrics.
- [ ] Đã lọc đúng tag keys và tag values khi so sánh.
- [ ] Đã đọc raw export từ /actuator/prometheus hoặc endpoint registry tương ứng.
- [ ] Đã kiểm tra naming convention của registry đích.
- [ ] Đã kiểm tra hậu tố đơn vị và loại meter.
- [ ] Đã kiểm tra common tags, rename/ignore/replace filters và filter order.
- [ ] Đã kiểm tra registry dependency và trạng thái export enabled.
- [ ] Đã xác minh collector hoặc backend không áp dụng namespace/mapping khác.
- [ ] Đã kiểm tra collision sau khi chuẩn hóa tên.
- [ ] Đã bổ sung test cho Meter ID và export nếu metric quan trọng.

## Ghi nhớ

- Tên trong Java, Meter ID, Actuator selector và tên export là các lớp khác nhau.
- Micrometer khuyến nghị tên chữ thường phân tách bằng dấu chấm để giữ tính portable.
- /actuator/metrics dùng tên chuẩn tắc của meter; không dùng tên Prometheus đã chuyển đổi làm selector.
- /actuator/prometheus hiển thị tên theo quy ước Prometheus, có thể đổi dấu phân cách và thêm đơn vị hoặc hậu tố theo loại meter.
- MeterFilter có thể thay đổi Meter ID; NamingConvention chuyển tên theo registry khi export.
- MeterFilter được áp dụng theo thứ tự và có thể deny meter, dẫn đến NOOP meter.
- Common tags và tag filters ảnh hưởng đến số chiều cũng như kết quả tổng hợp.
- Spring Boot có thể cấu hình nhiều registry trong một composite; hãy xác định đúng registry mà component sử dụng.
- Đọc raw export trước khi sửa dashboard hoặc đổi tên metric.
- Kiểm thử Meter ID và export ở hai lớp riêng biệt.

Khi tên metric khác nhau giữa Java, Actuator và backend, hãy lần theo dữ liệu từ Meter ID đến raw export rồi mới kiểm tra hệ thống nhận. Giữ tên canonical ổn định trong instrumentation và để từng registry chuyển đổi theo quy ước của nó giúp code portable, dashboard dễ bảo trì và sự cố dễ khoanh vùng.

## Tài liệu tham khảo

- [Micrometer: Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html) — dot notation và ví dụ chuyển tên giữa Prometheus, Atlas, Graphite và InfluxDB.
- [Micrometer: Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) — deny/accept, biến đổi Meter ID, common tags, rename tags và giới hạn cardinality.
- [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — registry auto-configuration, customizer, Actuator metrics endpoint và Prometheus export.
- [Spring Boot: Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposure và access của Actuator endpoints.
- [Prometheus: Metric and label naming](https://prometheus.io/docs/practices/naming/) — quy tắc tên metric, đơn vị, hậu tố và label cardinality.

