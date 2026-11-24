# Kiểm thử bộ lọc chặn meter, biến đổi nhãn và xung đột danh tính

MeterFilter quyết định meter nào được đăng ký, thay đổi Meter.Id trước khi đăng ký và có thể cấu hình thống kê phân phối cho Timer hoặc DistributionSummary. Một filter sai có thể làm mất metric quan trọng, xóa tag cần thiết, gộp hai chuỗi dữ liệu khác nghĩa hoặc tạo xung đột với quy tắc của backend.

Kiểm thử MeterFilter cần xác minh cả kết quả trong MeterRegistry lẫn dữ liệu mà registry exporter thực sự công bố. SimpleMeterRegistry phù hợp cho unit test vì giữ meter trong bộ nhớ; khi quy tắc phụ thuộc Prometheus hoặc backend cụ thể, cần thêm integration test với registry đó.

## 1. MeterFilter tham gia vào quá trình đăng ký như thế nào?

Một meter được tạo từ tên và tags. Registry áp dụng các MeterFilter đã đăng ký trước khi lưu meter. Filter có thể:

1. Chấp nhận hoặc từ chối meter.
2. Biến đổi tên, tags, description hoặc base unit của Meter.Id.
3. Cấu hình distribution statistics cho Timer và DistributionSummary.

Các filter được áp dụng theo thứ tự cấu hình. Những biến đổi ID được nối tiếp; quyết định chấp nhận hoặc từ chối được đánh giá qua các filter theo quy tắc MeterFilterReply.

~~~mermaid
flowchart TD
    A["Instrumentation tạo meter với name + tags"] --> B["MeterFilter 1: map / accept"]
    B --> C["MeterFilter 2: map / accept"]
    C --> D["MeterFilter tiếp theo"]
    D --> E{"Kết quả đăng ký"}
    E -->|DENY| F["Trả về NOOP meter"]
    E -->|ACCEPT hoặc không bị DENY| G["Tạo hoặc lấy meter theo ID sau biến đổi"]
    G --> H["MeterRegistry"]
~~~

Ba giá trị của MeterFilterReply:

| Reply | Ý nghĩa | Kết quả |
|---|---|---|
| DENY | Từ chối đăng ký | Registry trả về meter NOOP; dữ liệu ghi vào bị bỏ |
| NEUTRAL | Không quyết định | Tiếp tục xét filter khác |
| ACCEPT | Chấp nhận ngay | Dừng xét các quyết định accept tiếp theo và đăng ký meter |

Điểm cần nhớ: filter chỉ tác động khi meter được đăng ký. Hãy cấu hình registry và thêm toàn bộ MeterFilter trước khi instrumentation tạo meter. Thêm filter sau khi meter đã tồn tại không biến đổi lại các meter cũ.

## 2. Dùng SimpleMeterRegistry cho unit test

SimpleMeterRegistry giữ số liệu trong bộ nhớ và không gửi dữ liệu đến hệ thống giám sát. Nó giúp kiểm tra nhanh:

- Meter có được đăng ký hay không.
- Meter bị từ chối có trở thành NOOP không.
- Name và tags sau biến đổi là gì.
- Hai lần đăng ký có dùng chung một meter ID không.
- Số lượng meter có đúng giới hạn hay không.

Ví dụ dependency Gradle nếu dự án chưa được BOM quản lý:

~~~gradle
testImplementation("io.micrometer:micrometer-core")
testImplementation("org.junit.jupiter:junit-jupiter")
~~~

Khi dự án dùng Spring Boot hoặc Micrometer BOM, không cần tự khai báo version riêng cho dependency đã được BOM quản lý.

Mỗi test nên tạo registry riêng. Tránh dùng Metrics.globalRegistry trong unit test vì meter và filter có thể tồn tại xuyên suốt nhiều test, làm kết quả phụ thuộc thứ tự chạy.

## 3. Kiểm thử filter từ chối meter

Filter tiện ích denyNameStartsWith từ chối mọi meter có tên bắt đầu bằng tiền tố được chỉ định:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MeterFilterDenyTest {

    @Test
    void deniedMeterIsNoopAndIsNotRegistered() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.config()
            .meterFilter(MeterFilter.denyNameStartsWith("debug."));

        Counter denied = registry.counter("debug.events");
        denied.increment();

        assertEquals(0.0, denied.count());
        assertNull(registry.find("debug.events").counter());
        assertTrue(registry.getMeters().isEmpty());
    }

    @Test
    void allowedMeterStillRecordsValues() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.config()
            .meterFilter(MeterFilter.denyNameStartsWith("debug."));

        registry.counter("business.orders").increment();

        assertEquals(
            1.0,
            registry.get("business.orders").counter().count()
        );
    }
}
~~~

Test thứ nhất xác nhận hai hành vi: meter không xuất hiện trong registry và thao tác increment trên NOOP meter không làm phát sinh dữ liệu. Chỉ kiểm tra giá trị Counter trả về là 0 chưa đủ; nên xác nhận meter không được đăng ký bằng registry.find hoặc registry.getMeters.

Có thể kiểm tra một điều kiện phức tạp hơn bằng predicate:

~~~java
registry.config().meterFilter(
    MeterFilter.deny(id ->
        id.getName().startsWith("internal.")
            && "true".equals(id.getTag("sensitive"))
    )
);
~~~

Predicate nhận Meter.Id nên có thể kiểm tra tên, tag keys và tag values đã có ở thời điểm đăng ký. Không dùng predicate để đọc request context thay đổi theo từng lần gọi.

## 4. Kiểm thử whitelist và thứ tự ACCEPT/DENY

Một cách phổ biến để chỉ giữ lại nhóm metric cần thiết là chấp nhận prefix mong muốn, sau đó từ chối mọi meter còn lại:

~~~java
@Test
void acceptPrefixThenDenyEverythingElse() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config()
        .meterFilter(MeterFilter.acceptNameStartsWith("http."))
        .meterFilter(MeterFilter.deny());

    registry.counter("http.server.requests").increment();
    registry.counter("database.query.errors").increment();

    assertNotNull(registry.find("http.server.requests").counter());
    assertNull(registry.find("database.query.errors").counter());
    assertEquals(1, registry.getMeters().size());
}
~~~

Meter có prefix http. nhận reply ACCEPT nên được đăng ký mà không cần xét các quyết định accept tiếp theo. Meter còn lại nhận NEUTRAL từ filter đầu, sau đó bị filter deny từ chối.

Thứ tự filter là một phần của cấu hình. Đổi thứ tự hoặc thêm một filter ACCEPT/DENY tổng quát có thể làm thay đổi kết quả. Nên viết test cho các nhánh quan trọng thay vì chỉ kiểm tra một metric đại diện.

## 5. Kiểm thử biến đổi tag value

MeterFilter.replaceTagValues thay thế giá trị của một tag theo hàm ánh xạ. Đây là cách hữu ích để chuẩn hóa một số giá trị có cardinality cao thành các nhóm hữu hạn.

Ví dụ, URL chứa ID người dùng được chuẩn hóa về route template:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import static org.junit.jupiter.api.Assertions.*;

@Test
void normalizesDynamicUriAndMergesEquivalentMeters() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config().meterFilter(
        MeterFilter.replaceTagValues(
            "uri",
            uri -> uri.matches("^/users/\\d+$") ? "/users/{id}" : uri
        )
    );

    Counter first = registry.counter(
        "http.server.requests",
        "uri", "/users/42"
    );

    Counter second = registry.counter(
        "http.server.requests",
        "uri", "/users/84"
    );

    assertSame(first, second);

    first.increment();
    second.increment();

    assertEquals(
        2.0,
        registry.get("http.server.requests")
            .tag("uri", "/users/{id}")
            .counter()
            .count()
    );
    assertEquals(1, registry.getMeters().size());
}
~~~

Hai ID ban đầu có giá trị uri khác nhau. Sau khi filter thay thế tag value, cả hai trở thành cùng một ID và registry trả về cùng Counter. Đây là aggregation có chủ đích: hai request cùng route template được gộp vào một chuỗi dữ liệu.

Kết quả này cũng cho thấy vì sao cần kiểm thử identity sau biến đổi. Nếu hàm thay thế vô tình gộp hai nhóm nghiệp vụ khác nhau, số liệu sẽ mất khả năng phân biệt dù meter vẫn hoạt động bình thường.

## 6. Kiểm thử ignoreTags và renameTag

ignoreTags loại bỏ các tag keys được chỉ định khỏi mọi meter. Khi một tag bị loại bỏ, các meter trước đó khác nhau chỉ bởi tag đó có thể trở thành cùng ID và được gộp.

~~~java
@Test
void ignoredTagCanCauseTwoIdsToBecomeOne() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config().meterFilter(
        MeterFilter.ignoreTags("requestId")
    );

    Counter first = registry.counter(
        "job.completed",
        "queue", "email",
        "requestId", "req-1"
    );

    Counter second = registry.counter(
        "job.completed",
        "queue", "email",
        "requestId", "req-2"
    );

    assertSame(first, second);

    first.increment();
    second.increment();

    assertEquals(
        2.0,
        registry.get("job.completed")
            .tag("queue", "email")
            .counter()
            .count()
    );
}
~~~

renameTag đổi tên một tag key trong nhóm meter có prefix phù hợp:

~~~java
registry.config().meterFilter(
    MeterFilter.renameTag(
        "http.server",
        "path",
        "uri"
    )
);
~~~

Sau biến đổi, meter có tên bắt đầu bằng http.server dùng tag uri thay cho path. Hãy kiểm tra cả tên key cũ và mới trong test để tránh dashboard hoặc truy vấn vẫn dựa trên schema cũ.

Không đổi tên tag nếu key đích đã tồn tại mà chưa xác định rõ cách xử lý hai giá trị. Hai key cùng được đổi về một key có thể tạo ID không mong muốn hoặc làm mất thông tin.

## 7. Kiểm thử custom map trên Meter.Id

Khi filter cần thay đổi nhiều phần của Meter.Id cùng lúc, có thể triển khai MeterFilter.map:

~~~java
registry.config().meterFilter(new MeterFilter() {
    @Override
    public Meter.Id map(Meter.Id id) {
        if (id.getName().startsWith("legacy.")) {
            return id
                .withName("service." + id.getName().substring(7))
                .withTag("source", "legacy");
        }
        return id;
    }
});
~~~

Có thể kiểm tra name và tag sau mapping:

~~~java
@Test
void customMapRenamesMeterAndAddsSourceTag() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config().meterFilter(new MeterFilter() {
        @Override
        public Meter.Id map(Meter.Id id) {
            if (id.getName().startsWith("legacy.")) {
                return id
                    .withName("service." + id.getName().substring(7))
                    .withTag("source", "legacy");
            }
            return id;
        }
    });

    registry.counter("legacy.orders").increment();

    assertEquals(
        1.0,
        registry.get("service.orders")
            .tag("source", "legacy")
            .counter()
            .count()
    );
    assertNull(registry.find("legacy.orders").counter());
}
~~~

map nên là phép biến đổi ổn định dựa trên Meter.Id và cấu hình cố định như application name hoặc region. Không dùng map để lấy user ID, request ID hoặc dữ liệu của request hiện tại. MeterFilter chạy tại thời điểm đăng ký meter; dữ liệu động theo từng request phải được đưa vào instrumentation hoặc ObservationConvention.

## 8. Giới hạn cardinality bằng maximumAllowableTags

maximumAllowableTags giới hạn số giá trị khác nhau của một tag key cho nhóm meter có tên bắt đầu bằng prefix. Khi vượt giới hạn, filter onMaxReached được áp dụng cho meter mới.

~~~java
@Test
void deniesMetersAfterTagValueLimit() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            2,
            MeterFilter.deny()
        )
    );

    registry.counter(
        "http.server.requests", "uri", "/orders"
    ).increment();

    registry.counter(
        "http.server.requests", "uri", "/products"
    ).increment();

    registry.counter(
        "http.server.requests", "uri", "/customers"
    ).increment();

    assertEquals(2, registry.getMeters().size());
    assertNull(
        registry.find("http.server.requests")
            .tag("uri", "/customers")
            .counter()
    );
}
~~~

Trong ví dụ, hai giá trị uri đầu tiên được đăng ký; giá trị thứ ba bị từ chối vì vượt giới hạn. Có thể thay MeterFilter.deny() bằng một filter khác để xử lý meter vượt ngưỡng theo chính sách mong muốn.

maximumAllowableTags là hàng rào bảo vệ ở registry, không thay thế việc chuẩn hóa route và thiết kế tag đúng ngay trong instrumentation. Nếu filter từ chối meter vượt ngưỡng, số liệu của những meter đó bị bỏ. Hãy ghi nhận cảnh báo hoặc log khi giới hạn bị chạm để phát hiện lỗi cardinality thay vì xem việc mất metric là hành vi bình thường.

maximumAllowableMetrics cũng có thể giới hạn tổng số meter được đăng ký. Khi dùng giới hạn tổng, hãy bảo đảm những metric quan trọng có cơ hội được đăng ký trước các meter ít quan trọng hơn; giới hạn này không tự hiểu mức độ ưu tiên nghiệp vụ.

## 9. Phân biệt identity collision với khác biệt tag schema

Meter trong Micrometer được nhận diện bằng tên và tập tags. Có hai tình huống cần phân biệt:

| Tình huống | Ý nghĩa | Kết quả có thể xảy ra |
|---|---|---|
| Hai ID khác nhau bị filter chuẩn hóa thành cùng name và tags | Identity collision sau mapping | Registry dùng chung meter; số liệu được gộp |
| Cùng metric name nhưng các meter có tập tag keys khác nhau | Schema của metric không nhất quán | Registry/backend cụ thể có thể cảnh báo hoặc từ chối một meter |

Ví dụ collision sau mapping:

- ID A: http.server.requests, uri=/users/42
- ID B: http.server.requests, uri=/users/84
- Sau chuẩn hóa: cả hai có uri=/users/{id}

Hai ID đã trở thành một identity. Nếu chúng cùng biểu diễn route template thì aggregation là đúng. Nếu chúng đại diện cho hai nhóm cần theo dõi riêng, filter đang làm mất dữ liệu phân loại.

Khác biệt tag keys là vấn đề khác. Hai meter cùng tên nhưng một meter có tag method, meter còn lại có tag status sẽ tạo ra hai schema label khác nhau. Prometheus khuyến cáo mạnh rằng mọi series thuộc cùng metric family nên có tập label keys nhất quán. Tùy Prometheus client và phiên bản, schema không nhất quán có thể tạo cảnh báo hoặc khiến meter không được đăng ký; vì vậy instrumentation nên giữ cùng tập tag keys cho một metric name.

Cách thiết kế ổn định là luôn phát đủ tag keys, dùng giá trị dự phòng cho chiều không áp dụng:

~~~java
registry.counter(
    "api.calls",
    "method", "GET",
    "status", "200"
).increment();

registry.counter(
    "api.calls",
    "method", "POST",
    "status", "500"
).increment();
~~~

Cả hai series đều có method và status. Nếu một chiều chưa biết, dùng giá trị hữu hạn như unknown hoặc none theo quy ước của ứng dụng.

## 10. Kiểm thử schema tag với PrometheusMeterRegistry

SimpleMeterRegistry không mô phỏng mọi ràng buộc của exporter. Với ứng dụng xuất Prometheus, nên có một integration test tạo PrometheusMeterRegistry và kiểm tra exposition:

~~~java
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PrometheusMeterIdentityTest {

    @Test
    void metersWithSameNameUseSameTagKeys() {
        PrometheusMeterRegistry registry =
            new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

        registry.counter(
            "api.calls",
            "method", "GET",
            "status", "200"
        ).increment();

        registry.counter(
            "api.calls",
            "method", "POST",
            "status", "500"
        ).increment();

        String exposition = registry.scrape();

        assertTrue(exposition.contains("method=\"GET\""));
        assertTrue(exposition.contains("method=\"POST\""));
        assertTrue(exposition.contains("status=\"200\""));
        assertTrue(exposition.contains("status=\"500\""));
    }
}
~~~

Đây là kiểm tra integration với Prometheus client mới, dùng package io.micrometer.prometheusmetrics. Nếu dự án dùng registry legacy simpleclient, package và constructor khác; giữ dependency và API đồng bộ với BOM của dự án.

Có thể đăng ký listener để thu thập lý do meter registration thất bại:

~~~java
List<String> registrationFailures = new ArrayList<>();

registry.config().onMeterRegistrationFailed(
    (id, reason) -> registrationFailures.add(reason)
);
~~~

Khi test một trường hợp cố ý tạo schema không nhất quán, kiểm tra listener, log và scrape output theo hành vi của phiên bản Prometheus client đang dùng. Không giả định mọi phiên bản client đều báo lỗi theo cùng một cách. Test ổn định nhất là bảo đảm instrumentation luôn tạo cùng tập tag keys cho một metric name.

## 11. Kiểm thử xung đột do filter gộp hai ID

Một test nên xác nhận rõ khi nào aggregation là chủ ý:

~~~java
@Test
void mappingCollisionIsIntentionalAndObservable() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config().meterFilter(
        MeterFilter.replaceTagValues(
            "region",
            region -> region.equals("north") || region.equals("south")
                ? "domestic"
                : region
        )
    );

    Counter north = registry.counter(
        "orders.created", "region", "north"
    );
    Counter south = registry.counter(
        "orders.created", "region", "south"
    );

    assertSame(north, south);

    north.increment(3);
    south.increment(2);

    assertEquals(
        5.0,
        registry.get("orders.created")
            .tag("region", "domestic")
            .counter()
            .count()
    );
}
~~~

Nếu yêu cầu nghiệp vụ cần so sánh north và south, test trên phải thất bại theo thiết kế: hai vùng đang bị gộp thành domestic. Hãy giữ riêng các giá trị đó hoặc chỉ gộp những giá trị thực sự tương đương.

Một test identity nên kiểm tra cả ba điều:

1. ID sau filter có đúng name và tags mong đợi không?
2. Các meter khác nguồn có bị gộp thành cùng ID không?
3. Nếu được gộp, aggregation có đúng với ý nghĩa nghiệp vụ không?

## 12. Kiểm thử thứ tự map và accept

Các filter có thể cùng biến đổi ID và đưa ra quyết định accept/deny. Nên viết test để bảo đảm thứ tự đã cấu hình không làm thay đổi kết quả ngoài ý muốn.

Ví dụ, thêm tag common trước khi từ chối meter:

~~~java
import io.micrometer.core.instrument.Tags;

registry.config()
    .meterFilter(MeterFilter.commonTags(
        Tags.of("application", "checkout")
    ))
    .meterFilter(MeterFilter.denyNameStartsWith("debug."));
~~~

Khi test, kiểm tra meter được phép có tag application=checkout và meter có prefix debug. không xuất hiện. Nếu có nhiều filter map, hãy kiểm tra ID cuối cùng sau toàn bộ biến đổi, không chỉ kiểm tra kết quả của một filter riêng lẻ.

Không phụ thuộc vào thứ tự khai báo ngẫu nhiên của Spring bean. Nếu một chính sách cần chạy trước chính sách khác, hãy cấu hình thứ tự rõ ràng trong nơi tạo registry hoặc dùng cơ chế ordering của Spring theo phiên bản ứng dụng.

## 13. Kiểm thử MeterFilter trong Spring Boot

Trong Spring Boot, có thể khai báo MeterFilter thành bean để áp dụng cho các registry do Boot quản lý:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsFilterConfiguration {

    @Bean
    MeterFilter denyDebugMeters() {
        return MeterFilter.denyNameStartsWith("debug.");
    }
}
~~~

Một integration test với ApplicationContext cần xác nhận bean filter thực sự được gắn vào MeterRegistry mà ứng dụng dùng:

~~~java
@SpringBootTest
class MetricsFilterIntegrationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void springManagedRegistryAppliesDenyFilter() {
        registry.counter("debug.internal.events").increment();
        registry.counter("checkout.orders.created").increment();

        assertNull(
            registry.find("debug.internal.events").counter()
        );

        assertNotNull(
            registry.find("checkout.orders.created").counter()
        );
    }
}
~~~

Nếu ứng dụng có nhiều registry, hãy xác minh filter được áp dụng đúng registry và không vô tình chặn metric ở một backend khác. Filter là cấu hình của registry; không mặc định rằng một registry phụ hoặc registry tự tạo ngoài Spring sẽ nhận cùng bean.

## 14. Bộ test tối thiểu cho một chính sách MeterFilter

Một chính sách filter nên có các ca kiểm thử tương ứng với quyết định của nó:

| Nhóm | Ca kiểm thử | Điều cần xác nhận |
|---|---|---|
| Deny | Meter khớp điều kiện | Không đăng ký, thao tác ghi trở thành NOOP |
| Allow | Meter không khớp điều kiện | Vẫn được đăng ký và ghi nhận |
| Accept/Deny chain | Meter thuộc whitelist và ngoài whitelist | Đúng kết quả theo thứ tự filter |
| Transform | Tag value hoặc key được chuẩn hóa | ID cuối có đúng name và tags |
| Collision | Hai ID sau map trở thành một | Chỉ một meter và aggregation đúng hoặc được phát hiện |
| Cardinality cap | Tag value vượt giới hạn | Meter vượt ngưỡng bị xử lý theo onMaxReached |
| Backend schema | Cùng metric name có tập tag keys ổn định | Registry exporter scrape được dữ liệu mong đợi |
| Spring Boot | Filter bean được auto-configure | Registry do ứng dụng quản lý áp dụng đúng filter |

Đừng chỉ kiểm tra implementation của MeterFilter bằng cách gọi trực tiếp map() hoặc accept(). Cần tạo meter qua MeterRegistry để xác nhận toàn bộ chuỗi filter và hành vi đăng ký.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Thêm filter sau khi meter đã đăng ký | Meter cũ không được biến đổi lại | Cấu hình filter trước instrumentation |
| Chỉ kiểm tra Counter trả về là 0 | Không phân biệt meter NOOP với meter thật chưa được increment | Kiểm tra registry.find và registry.getMeters |
| Nghĩ DENY ném exception | Test kỳ vọng sai; code có thể tiếp tục với NOOP | Xác minh meter không được đăng ký và dữ liệu bị bỏ |
| Dùng ACCEPT mà không hiểu thứ tự | Một filter tổng quát có thể cho qua meter ngoài ý muốn | Test các nhánh ACCEPT, NEUTRAL và DENY |
| Chuẩn hóa tag quá rộng | Nhiều nhóm dữ liệu bị gộp | Kiểm tra identity sau mapping và ý nghĩa aggregation |
| Dùng MeterFilter để đọc request context | Tag động không đúng vòng đời đăng ký | Đưa dữ liệu request vào instrumentation |
| Đổi tag key mà không cập nhật dashboard | Truy vấn cũ không còn tìm thấy series | Quản lý schema và migration tag |
| Cùng metric name nhưng thiếu tag key ở một số meter | Exporter/backend có thể từ chối hoặc diễn giải không nhất quán | Phát đủ tag keys với giá trị dự phòng |
| Chỉ test bằng SimpleMeterRegistry | Bỏ sót giới hạn của Prometheus hoặc backend khác | Thêm integration test với registry đích |
| Dùng global registry trong test | Meter/filter rò rỉ giữa các test | Tạo registry riêng cho mỗi test |

## 16. Checklist trước khi đưa MeterFilter vào production

- [ ] Registry được cấu hình trước khi meter đầu tiên được đăng ký.
- [ ] Mỗi filter có test cho nhánh DENY và nhánh được phép.
- [ ] Test xác nhận meter bị từ chối là NOOP và không có trong registry.
- [ ] Thứ tự ACCEPT, NEUTRAL và DENY được kiểm thử.
- [ ] Name và tags sau map được xác minh qua MeterRegistry.
- [ ] Các trường hợp hai ID bị gộp đã được kiểm tra theo ý nghĩa nghiệp vụ.
- [ ] Tag value được chuẩn hóa về route template hoặc nhóm hữu hạn.
- [ ] maximumAllowableTags có chính sách onMaxReached và cảnh báo phù hợp.
- [ ] Cùng metric name luôn dùng cùng tập tag keys.
- [ ] Có integration test với Prometheus hoặc registry đích.
- [ ] Registration failure được quan sát khi exporter cung cấp callback.
- [ ] Spring Boot registry và registry phụ đều có cấu hình filter dự kiến.
- [ ] Unit test dùng registry riêng, không dùng global state.

MeterFilter vừa là lớp kiểm soát chi phí vừa là một phần của schema metrics. Kiểm thử cần xác nhận meter bị chặn có thực sự biến thành NOOP, tag được chuẩn hóa đúng, và hai ID sau biến đổi có bị gộp ngoài ý muốn hay không. Cuối cùng, hãy kiểm tra schema tag bằng registry exporter thực tế: một MeterRegistry đơn giản có thể chấp nhận nhiều ID, trong khi Prometheus khuyến cáo mạnh việc giữ tập label keys nhất quán cho cùng metric name.

## Tài liệu tham khảo

- [Micrometer Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [MeterFilter API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/config/MeterFilter.html)
- [MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html)

