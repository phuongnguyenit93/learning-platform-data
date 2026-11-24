# Bùng nổ số meter do tag động và ảnh hưởng đến bộ nhớ

Micrometer quản lý meter trong MeterRegistry theo định danh gồm tên meter và tập tag. Khi ứng dụng ghi nhiều lần vào cùng một định danh, registry có thể trả lại meter đã đăng ký. Nhưng nếu mỗi request tạo ra một tag value mới như user ID, request ID, session ID, timestamp hoặc URL chứa mã tài nguyên, mỗi tổ hợp mới có thể tạo thêm một meter.

Hiện tượng này gọi là **high cardinality**. Nó làm số meter trong JVM tăng theo lưu lượng và độ đa dạng dữ liệu, kéo theo bộ nhớ heap, garbage collection, thời gian đăng ký/tra cứu, kích thước payload export và chi phí lưu trữ của monitoring backend. Với Timer hoặc DistributionSummary có histogram, một meter logic còn có thể được xuất thành nhiều time series.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, bài này giải thích cách tag động làm tăng số meter, cách ước lượng cardinality, tác động lên bộ nhớ và hiệu năng, cách phát hiện bằng HighCardinalityTagsDetector, cùng các biện pháp chuẩn hóa tag và giới hạn đăng ký meter.

## 1. Meter được nhận diện bằng tên và tag

Ví dụ hai lần ghi sau sử dụng cùng tên và cùng tag:

~~~java
registry.counter(
        "orders.created",
        "channel", "web"
).increment();

registry.counter(
        "orders.created",
        "channel", "web"
).increment();
~~~

Cả hai lần gọi đều tìm đến cùng một meter. Việc tăng Counter lần thứ hai không tạo thêm một meter mới.

Nếu thay tag value:

~~~java
registry.counter(
        "orders.created",
        "channel", "web",
        "customerId", "C-1001"
).increment();

registry.counter(
        "orders.created",
        "channel", "web",
        "customerId", "C-1002"
).increment();
~~~

Hai tổ hợp tag khác nhau nên tạo hai meter riêng. Nếu mỗi customer có ID riêng và hệ thống có hàng triệu customer, số meter có thể tăng gần theo số customer đã xuất hiện.

Có thể nhớ quy tắc:

- Cùng tên và cùng tập tag: dùng lại meter đã đăng ký.
- Cùng tên nhưng khác tag value: một meter khác.
- Tên meter khác: một meter khác.
- Một meter được ghi hàng triệu lần vẫn chỉ là một meter nếu name và tags không thay đổi.

MeterRegistry giữ các meter đã đăng ký để tra cứu và ghi nhận. Trong một registry sống lâu, đừng kỳ vọng meter theo request sẽ tự biến mất khi request kết thúc. Thông thường meter tồn tại cùng registry cho đến khi bị loại bỏ tường minh hoặc registry được đóng.

## 2. Cardinality là số tổ hợp giá trị tag có thể xuất hiện

Cardinality mô tả số giá trị hoặc tổ hợp giá trị khác nhau của một dimension hay tập dimension. Với meter có nhiều tag, số tổ hợp tiềm năng tăng theo tích số lượng giá trị của từng tag.

Giả sử một meter có các tag:

| Tag | Số giá trị có thể xuất hiện |
|---|---:|
| tenant | 5.000 |
| route | 30 |
| method | 5 |
| outcome | 5 |

Số tổ hợp tối đa về mặt lý thuyết:

\[
5.000 \times 30 \times 5 \times 5 = 3.750.000
\]

Đây là giới hạn tổ hợp, không có nghĩa tất cả tổ hợp chắc chắn xuất hiện. Nhưng chỉ cần ứng dụng thực sự ghi nhận một phần đáng kể trong số đó, registry đã có thể tạo ra hàng trăm nghìn hoặc hàng triệu meter.

Một tag duy nhất như requestId có thể có hàng triệu giá trị riêng. Nếu mỗi request tạo một meter mới, số meter tăng theo số request đã quan sát. Khi kết hợp thêm status, tenant hoặc route, số tổ hợp có thể còn cao hơn.

Cardinality cần được xem xét ở cấp meter name và tập tag thực tế, không chỉ nhìn riêng từng tag. Một tag có 20 giá trị có vẻ an toàn, nhưng kết hợp với nhiều tag khác có thể tạo ra hàng triệu tổ hợp.

## 3. Những tag động thường gây bùng nổ meter

Các giá trị sau thường không phù hợp làm metric tag:

| Tag value | Vì sao nguy hiểm | Giá trị thay thế |
|---|---|---|
| userId, customerId | Mỗi người dùng có thể tạo một giá trị riêng | customer.tier hoặc user.type với tập hữu hạn |
| requestId, correlationId | Gần như mỗi request có một ID riêng | Giữ trong trace/log |
| sessionId | Mỗi phiên có thể tạo thêm meter | Loại phiên như authenticated/anonymous |
| orderId, transactionId | Số lượng giao dịch tăng theo thời gian | order.type hoặc payment.method |
| timestamp | Giá trị thay đổi liên tục | Khoảng thời gian hoặc time window được chuẩn hóa |
| URL đầy đủ | URL thường chứa ID hoặc tham số động | Route template như /orders/{id} |
| exception message | Nội dung tự do, có thể chứa dữ liệu request | Exception class hoặc error category hữu hạn |
| SQL có literal | Mỗi giá trị truy vấn có thể khác nhau | Tên operation hoặc normalized query |

Không phải mọi tag động đều nguy hiểm. Một tag có số lượng giá trị hữu hạn và được kiểm soát, chẳng hạn HTTP method hoặc status class, thường phù hợp. Điều cần tránh là tag value tăng theo từng thực thể hoặc từng request.

## 4. Ví dụ anti-pattern: mỗi request tạo meter riêng

Đoạn code sau đưa URL thực tế và user ID vào tag:

~~~java
public void recordRequest(
        HttpServletRequest request,
        String userId,
        MeterRegistry registry) {

    registry.counter(
            "http.server.requests",
            "uri", request.getRequestURI(),
            "userId", userId
    ).increment();
}
~~~

Giả sử request đi tới:

~~~text
GET /orders/10001  userId=U-100
GET /orders/10002  userId=U-101
GET /orders/10003  userId=U-102
~~~

Mỗi request có thể tạo một tổ hợp uri/userId mới. Khi lưu lượng tăng, số meter và số time series cũng tăng theo.

Một anti-pattern khác là đưa ID vào tên meter:

~~~java
registry.counter("orders.created." + orderId).increment();
~~~

Trường hợp này còn khó phát hiện hơn bằng HighCardinalityTagsDetector, vì detector nhóm các meter theo cùng tên. Nếu tên meter thay đổi liên tục, mỗi meter có thể chỉ xuất hiện một lần dưới một tên khác nhau.

Tên meter phải mô tả đại lượng cần đo; tag mô tả các chiều phân loại có tập giá trị hữu hạn. ID riêng của một request hoặc entity nên nằm trong trace/log hoặc hệ thống dữ liệu nghiệp vụ.

## 5. Cách viết instrumentation với tag có cardinality thấp

Với HTTP server, dùng route template thay vì URI thực tế. Ví dụ dưới đây dành cho Spring MVC:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.servlet.HandlerMapping;

public class HttpRequestMetrics {

    private final MeterRegistry registry;

    public HttpRequestMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            HttpServletRequest request,
            int status) {

        Object pattern = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
        );

        String route = pattern != null
                ? pattern.toString()
                : "UNKNOWN";

        String method = normalizeMethod(request.getMethod());
        String outcome = status / 100 + "xx";

        registry.counter(
                "application.http.requests",
                "method", method,
                "route", route,
                "outcome", outcome
        ).increment();
    }

    private String normalizeMethod(String method) {
        return switch (method) {
            case "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS" ->
                    method;
            default -> "OTHER";
        };
    }
}
~~~

Trong ví dụ, route được lấy từ pattern do Spring MVC cung cấp, chẳng hạn /orders/{id}. Các chiều method và outcome có tập giá trị hữu hạn. Mỗi request vẫn được đếm, nhưng các request cùng route/method/outcome sẽ dùng lại meter.

Trong ứng dụng dùng Spring Boot Actuator, instrumentation HTTP server tự động đã có thể cung cấp request metrics và route template. Hãy kiểm tra metrics hiện có trước khi tạo một bộ đo thủ công trùng chức năng.

Nếu cần phân tích request cụ thể, giữ request ID hoặc user ID trong trace/log. Với Observation, dùng high-cardinality key-value cho dữ liệu chi tiết và low-cardinality key-value cho dữ liệu được phép chuyển thành metric tags.

## 6. Ước lượng số meter trước khi triển khai

Trước khi thêm một tag, hãy liệt kê tập giá trị có thể xuất hiện và ước lượng số tổ hợp.

Ví dụ:

| Tag | Giá trị dự kiến | Cardinality |
|---|---|---:|
| method | GET, POST, PUT, DELETE, OTHER | 5 |
| route | Các route template của ứng dụng | 40 |
| outcome | 2xx, 3xx, 4xx, 5xx | 4 |
| region | Các region triển khai | 3 |

Số tổ hợp tối đa:

\[
5 \times 40 \times 4 \times 3 = 2.400
\]

Đây là con số dễ kiểm soát hơn nhiều so với việc thêm userId có hàng trăm nghìn giá trị.

Công thức ước lượng:

\[
N_{\text{meters}} \leq
\prod_{i=1}^{k} C_i
\]

Trong đó C_i là số giá trị có thể xuất hiện của tag thứ i. Số meter thực tế bằng số tổ hợp name/tag khác nhau đã được đăng ký, nên có thể thấp hơn giới hạn lý thuyết.

Cần cộng thêm các meter name khác nhau và những meter được sinh bởi binder hoặc instrumentation tự động. Nếu dùng nhiều MeterRegistry trong CompositeMeterRegistry, mỗi registry đích còn duy trì cấu trúc meter riêng của nó.

## 7. Ảnh hưởng đến bộ nhớ heap

Mỗi meter được đăng ký có thể cần các cấu trúc dữ liệu như:

- Đối tượng meter cụ thể: Counter, Gauge, Timer hoặc DistributionSummary.
- Meter.Id lưu tên và tag.
- Các đối tượng tag và cấu trúc collection chứa tag.
- Entry trong map của MeterRegistry để tra cứu meter.
- Trạng thái đo lường như bộ đếm, bộ tích lũy hoặc bộ đệm thống kê.
- Trạng thái riêng của registry/exporter.

Vì vậy, tăng số meter đồng nghĩa với tăng số đối tượng sống trong heap. Không có một con số byte cố định cho mỗi meter áp dụng được cho mọi ứng dụng: kích thước phụ thuộc loại meter, số tag, registry, thống kê phân phối, JVM và phiên bản thư viện.

Có thể mô hình hóa định tính:

\[
M_{\text{heap}} \approx
N_{\text{meters}} \times
M_{\text{average meter}}
+
M_{\text{registry/exporter}}
\]

Đây chỉ là mô hình ước lượng xu hướng, không phải công thức tính dung lượng chính xác. Timer có histogram hoặc percentile thường cần trạng thái lớn hơn một Counter đơn giản.

Khi meter được tạo theo từng request, heap có thể tăng dần theo thời gian dù lượng request đang xử lý đồng thời không tăng. Đây là lý do high cardinality đôi khi trông giống memory leak.

## 8. Histogram làm tăng số time series được xuất

Cần phân biệt số meter trong JVM với số time series ở backend.

Một Timer có histogram có thể được xuất thành nhiều series: bucket, count, sum và các thống kê bổ sung tùy registry/backend. DistributionSummary cũng có thể có nhiều series khi bật histogram.

Ví dụ, nếu một Timer có hàng nghìn tổ hợp tag và histogram được cấu hình nhiều bucket, số series backend nhận được có thể lớn hơn số meter logic nhiều lần.

Tác động xuất hiện ở cả hai phía:

- JVM giữ trạng thái meter và thống kê phân phối.
- Exporter phải tạo và serialize nhiều sample hơn.
- Payload scrape hoặc push lớn hơn.
- Backend phải lập chỉ mục nhiều label set và lưu nhiều series.
- Truy vấn, dashboard và rule cảnh báo cần xử lý nhiều chuỗi hơn.

Không thể lấy số meter rồi mặc định đó là số time series cuối cùng. Hãy kiểm tra loại meter, cấu hình histogram và cách backend biểu diễn metric.

## 9. Ảnh hưởng đến CPU, garbage collection và export

High cardinality tác động lên hiệu năng qua nhiều đường:

| Khu vực | Tác động |
|---|---|
| Đăng ký meter | Tạo object, chuẩn hóa tag, chạy MeterFilter và cập nhật map |
| Tra cứu meter | Mỗi lần ghi phải tra cứu theo ID nếu instrumentation dùng tag động |
| Heap | Nhiều Meter, Id, tag và trạng thái thống kê tồn tại lâu |
| Garbage collection | Tạo nhiều meter/tag mới làm tăng allocation và áp lực GC |
| Scrape/export | Nhiều series làm tăng thời gian tạo response và serialize |
| Mạng | Payload metrics lớn hơn |
| Monitoring backend | Tăng index, metadata, ingestion, storage và query cost |

Micrometer khuyến nghị giữ số meter được tạo ở mức có giới hạn. Khi name và tag không đổi, có thể lưu tham chiếu meter trong field để tránh tra cứu lặp lại trên đường ghi rất nóng. Khi tag value thay đổi nhưng nằm trong một tập hữu hạn, registry có thể tra cứu và dùng lại meter tương ứng.

Không nên cố tối ưu chi phí lookup bằng cách giữ một map không giới hạn theo user ID hoặc request ID. Điều đó chỉ chuyển nơi lưu cardinality từ MeterRegistry sang map của ứng dụng và vẫn tiêu thụ bộ nhớ.

## 10. HighCardinalityTagsDetector phát hiện meter tăng bất thường

Micrometer cung cấp HighCardinalityTagsDetector để tìm tên meter có số lượng meter vượt ngưỡng. Detector đếm số meter cùng tên trong registry và cảnh báo khi số lượng vượt threshold.

Cấu hình giám sát định kỳ theo API Micrometer 1.18:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.MeterRegistry;

public class CardinalityMonitoring {

    public CardinalityMonitoring(MeterRegistry registry) {
        registry.config().withHighCardinalityTagsDetector(r ->
                new HighCardinalityTagsDetector.Builder(r)
                        .threshold(1000)
                        .delay(Duration.ofMinutes(5))
                        .build()
        );
    }
}
~~~

Trong ví dụ, detector kiểm tra định kỳ và cảnh báo khi một tên meter có hơn 1.000 meter tương ứng. Ngưỡng này chỉ là ví dụ; cần chọn theo quy mô ứng dụng và ngân sách bộ nhớ.

Có thể bật mặc định bằng:

~~~java
registry.config().withHighCardinalityTagsDetector();
~~~

Khi cấu hình qua MeterRegistry, registry quản lý vòng đời detector. Nếu tự tạo detector độc lập để kiểm tra một lần, phải đóng detector sau khi dùng.

Detector giúp tìm tên meter có nhiều tổ hợp tag. Nó không tự sửa tag và cũng không tự ngăn meter mới được đăng ký. Dùng nó như công cụ phát hiện, kết hợp với filter và sửa instrumentation để phòng ngừa.

## 11. Giới hạn của HighCardinalityTagsDetector

Detector có các giới hạn cần hiểu:

- Nó đếm meter cùng tên, nên không phát hiện tốt trường hợp metric name thay đổi theo từng request.
- Nó không phát hiện mọi nguồn memory leak khác.
- Nếu số meter chưa vượt threshold, detector chưa cảnh báo.
- Nó có thể trả về meter đầu tiên vượt ngưỡng; nếu nhiều meter có vấn đề, cần điều tra và xử lý lần lượt.
- Threshold là heuristic, không phải giới hạn bộ nhớ được bảo đảm.

Ví dụ metric name động:

~~~java
registry.counter("request." + requestId).increment();
~~~

Mỗi tên chỉ có một meter nên detector đếm theo tên sẽ không thấy một tên nào vượt ngưỡng. Vì vậy, giữ metric name ổn định là điều kiện quan trọng để detector có ích.

Không tăng threshold chỉ để làm mất cảnh báo. Hãy kiểm tra meter name, tag values và nguồn tạo meter trước khi thay đổi ngưỡng.

## 12. Dùng detector trong kiểm thử instrumentation

Có thể tạo nhiều meter với userId khác nhau rồi xác nhận detector tìm thấy tên meter có cardinality cao:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterCardinalityTest {

    @Test
    void detectsMetersWithTooManyTagValues() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try (HighCardinalityTagsDetector detector =
                     new HighCardinalityTagsDetector.Builder(registry)
                             .threshold(10)
                             .build()) {

            for (int i = 0; i < 15; i++) {
                registry.counter(
                        "orders.created",
                        "userId",
                        "user-" + i
                ).increment();
            }

            assertTrue(detector.findFirst().isPresent());
            assertEquals(
                    "orders.created",
                    detector.findFirst().get()
            );
        }
        finally {
            registry.close();
        }
    }
}
~~~

Bài test xác nhận 15 giá trị userId đã tạo 15 meter có cùng tên và detector nhận diện được tên đó. Trong dự án thực tế, thêm test cho instrumentation đã chuẩn hóa để xác nhận số meter không tăng theo số user hoặc request.

Detector không thay thế assertion cardinality trong test. Với meter name động, hãy kiểm tra cả tổng số meter hoặc danh sách meter đã đăng ký.

## 13. Loại bỏ tag không cần thiết bằng MeterFilter

Nếu không kiểm soát được instrumentation tạo tag có cardinality cao, có thể bỏ tag đó ở registry:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

public class MeterFilterConfiguration {

    public MeterFilterConfiguration(MeterRegistry registry) {
        registry.config()
                .meterFilter(MeterFilter.ignoreTags("userId"));
    }
}
~~~

Filter này loại tag key userId khỏi meter ID. Các meter trước đây khác nhau chỉ vì userId có thể được gom về cùng định danh sau khi filter áp dụng cho các lần đăng ký mới.

Đây là biện pháp khẩn cấp khi không thể sửa instrumentation ngay. Trước khi loại tag, xác nhận dashboard và truy vấn có thực sự cần chiều phân tích đó không. Việc bỏ tag làm mất khả năng phân tách theo userId trong metrics, nhưng dữ liệu định danh có thể được giữ trong trace/log.

Đăng ký filter trước khi meter được tạo. Meter đã tồn tại không tự động biến mất hoặc được xây dựng lại chỉ vì thêm filter sau đó.

## 14. Giới hạn số tag value bằng maximumAllowableTags

MeterFilter.maximumAllowableTags đặt giới hạn cho số giá trị của một tag key trên những meter có tên khớp prefix:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "route",
                100,
                MeterFilter.deny()
        )
);
~~~

Trong ví dụ, tối đa 100 giá trị route được chấp nhận cho các meter khớp prefix http.server.requests. Khi vượt giới hạn, meter mới có route value ngoài ngưỡng sẽ bị deny.

Có thể dùng một MeterFilter tùy chỉnh làm onMaxReached để log hoặc xử lý riêng. Hãy giới hạn tần suất log; nếu mỗi request bị từ chối đều tạo một log warning, chính cơ chế bảo vệ có thể tạo thêm áp lực.

Giới hạn này chỉ kiểm soát một tag key. Nếu meter có nhiều tag khác cũng có cardinality cao, tổng số tổ hợp vẫn có thể lớn. Vì vậy, phải kiểm soát từng chiều và kiểm tra tổng số meter.

## 15. Đặt giới hạn tổng số meter bằng maximumAllowableMetrics

Có thể thêm giới hạn tổng số meter cho registry:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableMetrics(10_000)
);
~~~

Khi registry đạt giới hạn, các meter mới sẽ bị từ chối. Đây là hàng rào cuối để tránh số meter tăng không kiểm soát.

Cần thận trọng với giới hạn toàn cục:

- Meter đăng ký trước khi đạt ngưỡng vẫn tồn tại.
- Meter đăng ký sau khi chạm ngưỡng có thể bị từ chối, kể cả meter quan trọng.
- Kết quả phụ thuộc thứ tự meter được đăng ký.
- Ứng dụng vẫn có thể gọi Counter/Timer NOOP; số liệu bị từ chối sẽ không được ghi.

Không dùng maximumAllowableMetrics để thay thế việc thiết kế tag đúng. Đặt giới hạn quá thấp có thể làm mất các metrics quan trọng khi ứng dụng khởi động hoặc khi có nhiều binder được kích hoạt.

## 16. Chuẩn hóa tag value trước khi đăng ký meter

Một cách tốt hơn là ánh xạ dữ liệu đầu vào về tập giá trị hữu hạn trước khi ghi meter.

Ví dụ chuẩn hóa status:

~~~java
private String normalizeStatus(int status) {
    if (status >= 200 && status < 300) {
        return "2xx";
    }
    if (status >= 300 && status < 400) {
        return "3xx";
    }
    if (status >= 400 && status < 500) {
        return "4xx";
    }
    if (status >= 500 && status < 600) {
        return "5xx";
    }
    return "other";
}
~~~

Ví dụ chuẩn hóa loại khách hàng:

~~~java
private String normalizeCustomerTier(String tier) {
    return switch (tier) {
        case "FREE", "STANDARD", "PREMIUM", "ENTERPRISE" -> tier;
        default -> "OTHER";
    };
}
~~~

Các giá trị lạ hoặc không hợp lệ được gom vào OTHER. Điều này giúp bảo vệ registry trước input bất thường và tránh việc một tag có thể nhận hàng triệu giá trị ngoài dự kiến.

Không chuẩn hóa bằng cách cắt chuỗi tùy tiện nếu điều đó làm các nhóm nghiệp vụ bị trộn lẫn không có ý nghĩa. Hãy định nghĩa category theo câu hỏi vận hành mà dashboard cần trả lời.

## 17. Dùng Observation để giữ dữ liệu chi tiết mà không tăng metric cardinality

Nếu cần liên kết một metric với một request hoặc entity cụ thể, Observation API phân biệt low-cardinality và high-cardinality key-value:

~~~java
Observation observation = Observation.createNotStarted(
        "orders.process",
        observationRegistry
)
.lowCardinalityKeyValue("order.type", "online")
.lowCardinalityKeyValue("outcome", "success")
.highCardinalityKeyValue("order.id", orderId)
.highCardinalityKeyValue("customer.id", customerId);
~~~

Low-cardinality key-value có thể được dùng làm metric tags. High-cardinality key-value dành cho handler hoặc backend có thể xử lý dữ liệu chi tiết như tracing và logging; DefaultMeterObservationHandler không đưa chúng vào metric tags.

Trace ID nên được liên kết với metrics qua exemplar khi registry/backend hỗ trợ, thay vì thêm trace ID thành tag của Timer hoặc Counter. Cách này cho phép chọn một mẫu metric để mở trace cụ thể mà không tạo time series theo từng trace.

## 18. Phân biệt meter growth với memory leak khác

Khi heap tăng theo thời gian, không nên mặc định nguyên nhân là high cardinality. Hãy đối chiếu nhiều tín hiệu:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Số meter trong registry tăng liên tục | Tag value hoặc metric name động |
| Meter cùng tên tăng theo user/request | High-cardinality tag |
| Meter name khác nhau tăng nhanh | Metric name được tạo động |
| Meter count ổn định nhưng heap vẫn tăng | Memory leak ở component khác, queue, cache hoặc object nghiệp vụ |
| Meter count ổn định nhưng export chậm | Histogram, số bucket, registry/backend hoặc network |
| Heap tăng theo số histogram meter | Distribution state và cấu hình percentile/histogram |
| Mỗi instance có số meter hợp lý nhưng tổng backend rất lớn | Nhân số series theo số instance, deployment hoặc registry đích |

Có thể quan sát số meter bằng registry.getMeters().size() trong chẩn đoán hoặc test. Kết hợp với heap dump/JFR để kiểm tra các lớp meter, Meter.Id, Tag, map entry và đối tượng phân phối. Đừng dựa vào một chỉ số heap tổng để kết luận.

Nếu dùng CompositeMeterRegistry, mỗi registry đích có thể giữ bản đăng ký riêng. Số registry và cấu hình thống kê cũng ảnh hưởng tổng bộ nhớ.

## 19. Quy trình xử lý khi số meter tăng bất thường

Khi phát hiện heap tăng hoặc số meter tăng nhanh:

1. Đọc cảnh báo HighCardinalityTagsDetector và xác định meter name bị ảnh hưởng.
2. Liệt kê tag keys và số lượng tag values khác nhau.
3. Tìm vị trí instrumentation tạo tag hoặc tên meter đó.
4. Xác định tag value nào là ID, timestamp, URL đầy đủ hoặc dữ liệu tự do.
5. Thay bằng route template, category hoặc outcome hữu hạn.
6. Chuyển định danh chi tiết sang trace/log hoặc high-cardinality Observation key-value.
7. Thêm MeterFilter giới hạn tag/metrics nếu cần hàng rào bảo vệ.
8. Viết test để xác nhận số meter bị chặn ở mức dự kiến.
9. Quan sát heap, GC, meter count, payload export và backend series sau khi triển khai.

Nếu meter cũ đã được tạo trong một registry đang chạy, thêm filter không nhất thiết loại bỏ các meter đó. Có thể cần loại bỏ meter phù hợp bằng API registry hoặc khởi động lại instance sau khi sửa instrumentation. Việc xóa meter trong runtime phải được cân nhắc vì có thể làm gián đoạn chuỗi dữ liệu và dashboard.

## 20. Checklist thiết kế tag và quản lý bộ nhớ

Trước khi đưa instrumentation vào production, xác nhận:

- Metric name ổn định, không chứa request ID hoặc entity ID.
- Tag value có tập giá trị hữu hạn và đã được chuẩn hóa.
- Không đưa userId, requestId, sessionId, traceId hoặc timestamp vào metric tag.
- URL được thay bằng route template.
- Exception được phân loại bằng exception class hoặc error category hữu hạn, không dùng message.
- Đã ước lượng tích số cardinality của các tag kết hợp.
- Đã đánh giá số series tăng thêm khi bật histogram hoặc percentile.
- MeterRegistry và số registry đích được tính đến trong ngân sách heap.
- MeterFilter được đăng ký trước khi meter tạo ra.
- maximumAllowableTags và maximumAllowableMetrics chỉ dùng như guardrail.
- HighCardinalityTagsDetector được bật phù hợp và có threshold hợp lý.
- Test xác nhận số meter không tăng theo số request hoặc user.
- Heap/JFR và backend được quan sát khi chạy tải đại diện.

Bùng nổ meter xảy ra khi instrumentation biến dữ liệu riêng của từng request hoặc entity thành một phần của định danh meter. Mỗi tổ hợp name/tag mới có thể tạo thêm đối tượng trong registry; histogram còn làm tăng số series được xuất. Giữ metric name ổn định, chuẩn hóa tag, đưa dữ liệu chi tiết sang trace/log, bật detector và đặt guardrail phù hợp sẽ giúp kiểm soát heap, garbage collection và chi phí monitoring backend.

## Tài liệu tham khảo

- [Micrometer - High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer - Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer - Performance: criticality of code paths](https://github.com/micrometer-metrics/micrometer/wiki/Performance:-criticality-of-code-paths)
- [Micrometer - Observation API](https://docs.micrometer.io/micrometer/reference/observation.html)
