# Ảnh hưởng của cardinality tới backend metrics

## 1. Vì sao cardinality quan trọng?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, observability giúp nhóm phát triển theo dõi lời gọi giữa các application module, event publication, metrics và traces. Khi thêm một chiều phân loại vào metric, ví dụ module identifier, ta có thể so sánh latency giữa orders, inventory và payments.

Tuy nhiên, mỗi tổ hợp tên metric và các cặp label key/value tạo ra một **time series** riêng ở backend metrics. Nếu một label nhận quá nhiều giá trị khác nhau, số series tăng nhanh, kéo theo chi phí bộ nhớ, CPU, lưu trữ, network, index và truy vấn. Đây là vấn đề **cardinality**.

Một metric có vài label hữu hạn thường dễ vận hành. Một metric có thêm customerId, orderId, requestId hoặc URL chứa ID có thể tạo hàng nghìn tới hàng triệu series theo traffic. Khi số series tăng ngoài dự kiến, Prometheus và các metrics backend phải duy trì nhiều chuỗi dữ liệu hơn dù mỗi chuỗi có thể chỉ nhận một vài mẫu.

Trong module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, cardinality cần được quản lý ngay tại nơi tạo observation và event metrics. Bài này giải thích cách cardinality phát sinh, ảnh hưởng của nó đến backend, cách Spring Modulith phân loại key mặc định, cách kiểm soát custom tags, và cách phát hiện sớm sự tăng trưởng bất thường.

## 2. Cardinality là gì?

Với metrics, cardinality thường chỉ số lượng giá trị khác nhau của một dimension hoặc số tổ hợp label khác nhau được tạo cho một metric.

Ví dụ metric:

~~~text
module_invocations_seconds_count{
  module_identifier="orders",
  module_invocation_type="bean",
  environment="production"
}
~~~

Metric trên có ba chiều:

- module_identifier: module nào được gọi.
- module_invocation_type: lời gọi bean hay event listener.
- environment: môi trường triển khai.

Nếu ứng dụng có 6 module, 2 loại invocation và 3 environment, số tổ hợp tối đa của ba chiều này là:

\[
6 \times 2 \times 3 = 36
\]

Trong thực tế, chỉ các tổ hợp thực sự được ghi nhận mới tạo series. Vì vậy, 36 là giới hạn trên theo các miền giá trị đã giả định.

Khi thêm customer_id với 100.000 khách hàng, giới hạn tổ hợp tăng thành:

\[
6 \times 2 \times 3 \times 100{,}000 = 3{,}600{,}000
\]

Chỉ một dimension không giới hạn cũng có thể lấn át các chiều hữu ích khác.

### 2.1. Cardinality của một label và cardinality của metric

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Label cardinality | Số giá trị khác nhau của một label key | module_identifier có 6 giá trị |
| Series cardinality | Số tổ hợp label khác nhau của một metric | 36 tổ hợp từ 3 label |
| Active series | Số series hiện đang được backend duy trì trong cửa sổ hoạt động | Các tổ hợp đã có sample gần đây |
| Series churn | Tốc độ xuất hiện các series mới theo thời gian | Mỗi request tạo một request_id mới |

Một label có cardinality nhỏ vẫn có thể góp phần tạo rất nhiều series nếu kết hợp với nhiều chiều khác. Ngược lại, một metric có một label cardinality rất lớn có thể gây vấn đề ngay cả khi chỉ có ít label keys.

### 2.2. Cardinality là phép nhân giữa các chiều

Nếu một metric có các label với miền giá trị lần lượt là C1, C2, ..., Cn, giới hạn tổ hợp lý thuyết là:

\[
C_{\text{series}} \leq \prod_{i=1}^{n} C_i
\]

Đây là giới hạn trên, không phải dự báo chính xác số series. Một số tổ hợp không xảy ra trong traffic thực tế; tuy nhiên, các ID động có thể khiến số tổ hợp tiến gần giới hạn rất nhanh.

Ví dụ:

| Label | Số giá trị giả định |
| --- | ---: |
| module_identifier | 8 |
| module_invocation_type | 2 |
| environment | 3 |
| instance | 6 |
| module_method | 120 |
| **Tổng tổ hợp tối đa** | **34.560** |

Nếu module_method được đưa vào metrics, số tổ hợp tăng từ 8 × 2 × 3 × 6 = 288 lên 34.560. Một request ID với 50.000 giá trị có thể tiếp tục nhân con số đó lên hàng tỷ tổ hợp lý thuyết.

## 3. Time series tăng thì backend chịu ảnh hưởng gì?

Mỗi series cần metadata và tài nguyên để nhận, lập chỉ mục, lưu và truy vấn. Tác động cụ thể phụ thuộc backend, retention, scrape interval, compression, histogram configuration và cách triển khai.

| Thành phần | Ảnh hưởng khi cardinality tăng |
| --- | --- |
| Application memory | Registry phải quản lý thêm Meter và tag set; số object tăng |
| CPU | Ghi nhận, scrape, encode, ingest, index và query xử lý nhiều series hơn |
| Network | Payload metrics gửi tới backend lớn hơn |
| Storage | Nhiều chuỗi và mẫu hơn làm tăng dung lượng lưu trữ |
| Index | Backend cần lập chỉ mục nhiều label set hơn |
| Query | Aggregation, filtering và grouping phải xử lý nhiều series |
| Chi phí dịch vụ | Một số backend tính phí theo active series, ingest volume hoặc dung lượng |

Với Prometheus, mỗi label set duy nhất là một time series. Hướng dẫn instrumentation của Prometheus nhấn mạnh rằng mỗi label set có chi phí RAM, CPU, disk và network; label cardinality tăng theo tổ hợp các chiều. Xem tài liệu Prometheus — Instrumentation best practices trong phần tham khảo.

Cardinality cao cũng làm dashboard khó đọc hơn. Nếu một metric có hàng chục nghìn giá trị customer_id, biểu đồ tổng hợp theo customer không còn là cách quan sát vận hành hiệu quả. Metrics nên trả lời câu hỏi về trạng thái và xu hướng của hệ thống; phân tích từng thực thể thường phù hợp hơn với logs, traces hoặc hệ thống analytics.

## 4. Vì sao ID động tạo ra cardinality explosion?

Các giá trị sau thường không phù hợp làm metric labels:

- User ID, customer ID, account ID.
- Order ID, payment ID, invoice ID.
- Request ID, correlation ID, trace ID, span ID.
- Session ID, token, email hoặc số điện thoại.
- URL đầy đủ chứa resource ID.
- Query string hoặc nội dung đầu vào tùy ý.
- Timestamp hoặc giá trị ngẫu nhiên.

Ví dụ instrumentation không phù hợp:

~~~java
Counter.builder("orders.processed")
    .tag("customer_id", order.customerId())
    .tag("order_id", order.id())
    .register(meterRegistry)
    .increment();
~~~

Nếu mỗi order có một ID mới, mỗi lần xử lý có thể tạo một series mới. Metric này không còn là một counter tổng hợp hữu ích.

Có thể thay bằng dimension có miền giá trị hữu hạn:

~~~java
Counter.builder("orders.processed")
    .tag("channel", order.channel().name())
    .tag("outcome", order.isAccepted() ? "accepted" : "rejected")
    .register(meterRegistry)
    .increment();
~~~

channel và outcome phải có tập giá trị được kiểm soát. Khi cần tìm một order cụ thể, ghi order ID vào log có kiểm soát hoặc trace attribute; không dùng metric label để thay thế khả năng tìm kiếm của logs/traces.

### 4.1. Chuẩn hóa URL thay vì ghi URL thực tế

Không nên ghi URL có ID vào label:

~~~text
uri="/orders/100001"
uri="/orders/100002"
uri="/orders/100003"
~~~

Dùng route template:

~~~text
uri="/orders/{orderId}"
~~~

Các request cùng endpoint sẽ được tổng hợp vào một series. Nếu có route không nhận diện được, chuẩn hóa thành giá trị hữu hạn như OTHER hoặc NOT_FOUND, thay vì giữ nguyên path do client gửi lên.

## 5. Spring Modulith đã phân loại key như thế nào?

Spring Modulith 2.2 tạo module entry spans cho lời gọi đi vào Spring component thuộc API của application module. Các tag của span gồm:

| Key | Vai trò | Cardinality trong convention |
| --- | --- | --- |
| module.identifier | Technical ID của module | Low |
| module.name | Tên hiển thị module | Low |
| module.invocation-type | Kiểu gọi, ví dụ bean hoặc event listener | Low |
| module.method | Method thực thi | High |

Spring Modulith định nghĩa ba key đầu trong ModulithObservations.LowKeys; module.method nằm trong ModulithObservations.HighKeys. Đây là một quyết định quan trọng: module ID và invocation type có thể được dùng để phân nhóm metrics, còn method được giữ ở high-cardinality data để phục vụ trace-level investigation. Xem API LowKeys và HighKeys trong phần tham khảo.

Tên observation convention mặc định của module invocation là module.invocations. Spring Modulith cho phép cung cấp ModulithObservationConvention bean để tùy chỉnh metrics được tạo. Xem tài liệu Production-ready Features trong phần tham khảo.

### 5.1. Vì sao module method là high cardinality?

Một ứng dụng có thể có hàng chục hoặc hàng trăm method thuộc các module API. Số method hữu hạn trong một bản build, nhưng thường lớn hơn nhiều so với số module hoặc invocation type. Method cũng thay đổi khi refactor hoặc bổ sung API.

Nếu thêm module.method vào mọi metric Timer, mỗi module có thể sinh thêm nhiều series theo method, rồi tiếp tục nhân với environment, instance và histogram buckets.

Để so sánh duration theo module, module.identifier thường đã đủ. Khi cần tìm method cụ thể gây chậm, trace có thể giữ module.method để xem từng invocation. Đây là cách dùng đúng mức chi tiết cho từng loại backend.

## 6. Cardinality trong event metrics của Spring Modulith

Spring Modulith tạo metrics cho domain event publication. Hai dạng metric chính:

- module.events.published: counter tổng hợp các event publication.
- module.events.published.$moduleIdentifier.$simpleEventTypeName: counter cho từng loại event.

Với metric tổng hợp, các low-cardinality keys gồm:

| Key | Ý nghĩa |
| --- | --- |
| module.event.type | Loại event được publish |
| module.identifier | Module phát event |
| module.name | Tên module |

Với metric riêng theo event, các low-cardinality keys mặc định gồm module.identifier và module.name. Spring Modulith cho phép thêm tags qua ModulithEventMetricsCustomizer. Xem tài liệu Production-ready Features trong phần tham khảo.

Metric riêng theo event còn đưa module identifier và simple event type name vào tên metric. Vì vậy, số loại event cũng ảnh hưởng số meter được tạo; đây thường là tập hữu hạn theo codebase, nhưng vẫn cần được rà soát khi ứng dụng có nhiều event type hoặc module mới.

Đây là điểm cần kiểm tra kỹ: customizer nhận event object, vì vậy developer có thể vô tình đưa một field động của event vào metric tag.

Ví dụ không nên làm:

~~~java
@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, meter) -> meter.tags(
                "customerId", event.customerId(),
                "orderId", event.orderId()
            )
        );
    }
}
~~~

Mỗi customer hoặc order mới có thể tạo một tổ hợp tag mới. Thay vào đó, chọn một thuộc tính có miền giá trị nhỏ và được kiểm soát, ví dụ kênh bán hàng:

~~~java
enum SalesChannel {
    WEB, STORE, PARTNER
}

record OrderPlaced(
    String orderId,
    String customerId,
    SalesChannel channel
) {}

@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, meter) -> meter.tags(
                "channel", event.channel().name()
            )
        );
    }
}
~~~

channel chỉ có ba giá trị theo enum. orderId và customerId vẫn có thể được ghi vào log/trace theo chính sách dữ liệu của ứng dụng, nhưng không trở thành metric dimensions.

## 7. Ước lượng số series trước khi thêm một label

Trước khi thêm dimension mới, liệt kê số giá trị tối đa có thể xuất hiện trong production.

Ví dụ metric module invocation có:

| Dimension | Số giá trị |
| --- | ---: |
| Module | 8 |
| Invocation type | 2 |
| Environment | 3 |
| Instance | 6 |
| Kết hợp hiện tại | 288 |

Nếu thêm label result với 4 giá trị, số tổ hợp tối đa thành:

\[
288 \times 4 = 1{,}152
\]

Nếu thêm module.method với 120 giá trị:

\[
288 \times 120 = 34{,}560
\]

Nếu thêm customerId với 50.000 giá trị:

\[
288 \times 50{,}000 = 14{,}400{,}000
\]

Đây là phép tính giới hạn trên. Số series thực tế phụ thuộc tổ hợp xuất hiện, nhưng với ID động, số tổ hợp có thể tăng gần như theo số request hoặc entity được xử lý.

### 7.1. Histogram còn nhân số series

Timer histogram thường xuất nhiều bucket, cộng thêm _sum và _count. Nếu có B bucket series được xuất cho mỗi label set (bao gồm cả bucket vô cực +Inf), số series gần đúng là:

\[
N_{\text{series}} \approx
N_{\text{label combinations}} \times (B + 2)
\]

Ví dụ một metric có 1.152 label combinations và 21 bucket series, cộng _sum và _count:

\[
1{,}152 \times (21 + 2) = 26{,}496
\]

Nếu thêm customerId, phép tính có thể tăng lên hàng trăm triệu series. Vì vậy, cardinality cần được đánh giá cùng histogram configuration; không chỉ nhìn số label keys.

## 8. Chọn dimensions phù hợp cho module metrics

Một dimension tốt thường có miền giá trị nhỏ, ổn định và hữu ích cho một câu hỏi vận hành cụ thể.

| Dimension | Đánh giá | Cách dùng |
| --- | --- | --- |
| module.identifier | Phù hợp | Phân tích theo module |
| module.name | Phù hợp nếu tên ổn định | Hiển thị trong dashboard |
| module.invocation-type | Phù hợp | So sánh bean và event listener |
| environment | Phù hợp nếu số môi trường hữu hạn | Tách dev/staging/prod |
| region | Phù hợp nếu region được kiểm soát | So sánh khu vực |
| outcome | Phù hợp nếu enum hữu hạn | Phân nhóm success/failure |
| module.method | Không nên đưa vào metric theo mặc định | Dùng trong span/trace |
| customerId | Không phù hợp | Dùng log/trace/analytics |
| orderId | Không phù hợp | Dùng log/trace |
| traceId | Không phù hợp | Dùng trace correlation |
| URL có ID | Không phù hợp | Dùng route template |

Đừng thêm một label chỉ vì backend cho phép filter. Hãy bắt đầu từ câu hỏi: người vận hành cần nhóm dữ liệu theo dimension nào để phát hiện hoặc chẩn đoán vấn đề?

## 9. Dùng Micrometer Observation để tách low/high-cardinality data

Micrometer Observation phân biệt rõ hai loại key-value:

- **Low-cardinality values** được sử dụng khi tạo metrics và có thể xuất hiện trong traces.
- **High-cardinality values** dành cho hệ thống có thể xử lý dữ liệu chi tiết hơn, thường là distributed tracing và logs; chúng không nên được dùng làm metric tags.

Ví dụ observation tùy chỉnh:

~~~java
Observation.createNotStarted(
        "orders.process",
        observationRegistry
    )
    .lowCardinalityKeyValue("module.identifier", "orders")
    .lowCardinalityKeyValue("outcome", "accepted")
    .highCardinalityKeyValue("orderId", order.id())
    .highCardinalityKeyValue("customerId", order.customerId())
    .observe(() -> orderService.process(order));
~~~

Ví dụ này minh họa nguyên tắc API. Với Spring Modulith, module entry observation đã có convention mặc định; không cần tự tạo observation trùng lặp chỉ để thêm module ID. Khi custom convention, giữ các low/high-cardinality values mặc định rồi chỉ bổ sung metadata có miền giá trị phù hợp.

Micrometer giải thích rằng high-cardinality values không được dùng cho metrics; chúng phù hợp hơn với trace hoặc log. Xem tài liệu High Cardinality Tags Detector trong phần tham khảo.

### 9.1. Không chuyển high-cardinality key sang low chỉ để lọc dashboard

Giả sử dashboard muốn lọc theo module.method. Nếu đưa method vào low-cardinality values, số series sẽ tăng theo method count và các dimension khác.

Hãy cân nhắc:

- Giữ metric theo module để thấy xu hướng tổng thể.
- Mở trace để tìm method của invocation chậm.
- Dùng log search theo moduleId, traceId và logger name khi cần điều tra.
- Dùng profiler hoặc application performance monitoring cho phân tích chi tiết theo method.

Nếu yêu cầu thật sự cần thống kê theo nhóm method, tạo một dimension đã chuẩn hóa như operation_group=read|write|publish thay vì tên method tùy ý.

## 10. Kiểm soát cardinality bằng MeterFilter

Micrometer cung cấp MeterFilter để kiểm soát meter registration, biến đổi Meter ID, loại bỏ tag hoặc giới hạn số tag values.

Một số API hữu ích:

| API | Tác dụng |
| --- | --- |
| ignoreTags(...) | Loại bỏ tag keys khỏi meter |
| replaceTagValues(...) | Chuẩn hóa tag values |
| maximumAllowableTags(...) | Giới hạn số giá trị của một tag cho meter prefix |
| maximumAllowableMetrics(...) | Giới hạn tổng số meter được đăng ký |
| denyNameStartsWith(...) | Từ chối nhóm meter theo prefix |

MeterFilter được áp dụng theo thứ tự cấu hình. maximumAllowableTags và maximumAllowableMetrics nên là lớp bảo vệ cuối cùng sau khi đã sửa instrumentation gây cardinality cao. Xem tài liệu Meter Filters trong phần tham khảo.

### 10.1. Giới hạn tag tùy chỉnh

Ví dụ nếu một custom instrumentation cũ vẫn thêm customerId vào meter module.invocations, có thể giới hạn số giá trị được chấp nhận:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.micrometer.core.instrument.config.MeterFilter;

@Configuration(proxyBeanMethods = false)
class MetricsCardinalityConfiguration {

    @Bean
    MeterFilter moduleInvocationCardinalityGuard() {
        return MeterFilter.maximumAllowableTags(
            "module.invocations",
            "customerId",
            100,
            MeterFilter.deny()
        );
    }
}
~~~

Filter này cho phép tối đa 100 giá trị khác nhau của customerId trên các meter khớp prefix module.invocations; các meter mới vượt giới hạn bị từ chối. Nó là biện pháp giảm rủi ro, không phải cách thiết kế tốt để giữ customer ID trong metrics.

Cần xác minh tên meter Micrometer trước khi cấu hình filter. Filter khớp tên meter trong registry, không nhất thiết khớp tên đã được backend chuẩn hóa như Prometheus exposition.

### 10.2. Giới hạn tổng số meter

Có thể đặt một ngưỡng tổng thể:

~~~java
@Bean
MeterFilter totalMeterLimit() {
    return MeterFilter.maximumAllowableMetrics(5000);
}
~~~

Ngưỡng 5000 chỉ là ví dụ. Khi đạt giới hạn, các meter đăng ký sau có thể bị từ chối và dữ liệu tương ứng không được ghi. Một giới hạn quá thấp có thể làm mất cả metrics quan trọng; cần chọn ngưỡng dựa trên baseline, kiểm tra log và theo dõi việc filter từ chối meter.

Không dùng giới hạn toàn cục để che giấu một instrumentation sai. Nếu meter orders bị từ chối vì customer ID tăng liên tục, phải sửa nguồn tạo tag và giữ các metric quan trọng được đăng ký.

### 10.3. Chuẩn hóa tag values

Micrometer có replaceTagValues để ánh xạ giá trị về một tập nhỏ hơn. Ví dụ khái niệm:

~~~java
registry.config().meterFilter(
    MeterFilter.replaceTagValues(
        "status",
        value -> value.startsWith("5") ? "5xx" :
                 value.startsWith("4") ? "4xx" : "other"
    )
);
~~~

Cách chuẩn hóa chỉ phù hợp khi mất chi tiết là chấp nhận được cho mục tiêu metrics. Nếu cần biết chính xác HTTP status hoặc entity ID, giữ thông tin chi tiết ở log/trace. Với tag do request input điều khiển, nên chuẩn hóa ngay tại instrumentation thay vì phụ thuộc filter hậu kiểm.

## 11. Phát hiện high cardinality bằng Micrometer

Micrometer cung cấp HighCardinalityTagsDetector, theo dõi số meter có cùng tên. Khi số meter vượt ngưỡng, detector có thể thông báo để nhóm phát triển điều tra.

Ví dụ cấu hình detector trên registry:

~~~java
import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.MeterRegistry;

final class CardinalityMonitoring {

    private static final Logger log =
        LoggerFactory.getLogger(CardinalityMonitoring.class);

    static void configure(MeterRegistry registry) {
        registry.config().withHighCardinalityTagsDetector(r ->
            new HighCardinalityTagsDetector.Builder(r)
                .threshold(1000)
                .delay(Duration.ofMinutes(5))
                .highCardinalityMeterInfoConsumer(info ->
                    log.warn(
                        "Potential high cardinality meter: {} has {} variants",
                        info.getName(),
                        info.getCount()
                    )
                )
                .build()
        );
    }
}
~~~

threshold(1000) và chu kỳ 5 phút là giá trị minh họa, cần điều chỉnh theo ứng dụng. Ví dụ sử dụng API của Micrometer 1.18; hãy dùng phiên bản được Spring Boot BOM của dự án quản lý và kiểm tra API tương ứng nếu BOM cũ hơn. Detector có thể dùng trong test hoặc giám sát liên tục. Nó đếm số meter cùng tên để phát hiện dấu hiệu cardinality cao; không xác định chính xác label key gây ra vấn đề và không phát hiện mọi trường hợp như giá trị ngẫu nhiên được ghép vào metric name. Khi có cảnh báo, cần inspect các Meter.Id cùng tên để tìm dimension gây tăng trưởng. Xem tài liệu High Cardinality Tags Detector trong phần tham khảo.

### 11.1. Dùng detector trong kiểm thử

Trong test instrumentation, có thể tạo nhiều meter với cùng tên nhưng giá trị ID khác nhau để xác nhận detector nhận ra vấn đề. Đây là một test bảo vệ tốt khi code mới thêm tag.

Không chỉ kiểm tra detector đã phát cảnh báo. Hãy kiểm tra nguyên nhân: tag nào tạo nhiều biến thể, instrumentation nào thêm tag và có thể thay bằng dimension hữu hạn hay không.

## 12. Theo dõi cardinality ở backend metrics

Micrometer phát hiện meter ở phía ứng dụng. Backend metrics giúp đánh giá tác động sau khi scrape/ingest.

Với Prometheus, nên theo dõi:

- Tổng số series đang được quản lý.
- Số series mới xuất hiện theo thời gian.
- Dung lượng head block và WAL.
- CPU/memory của Prometheus.
- Scrape duration và scrape samples.
- Query latency và số series được trả về.
- Remote write queue nếu có.

Có thể xem thống kê series qua Prometheus UI/TSDB status hoặc các metric nội bộ tùy phiên bản. Tên metric nội bộ có thể thay đổi giữa phiên bản và cấu hình; xác minh trên endpoint /metrics của chính Prometheus thay vì sao chép query từ môi trường khác.

Một metric có cardinality cao không chỉ làm tăng active series. Nếu giá trị thay đổi liên tục như request ID, các series cũ có thể vẫn chiếm dung lượng cho tới khi hết retention, trong khi series mới liên tục xuất hiện. Đây là lý do cần theo dõi cả số series hiện tại và tốc độ tăng/churn.

## 13. Quy trình xử lý khi cardinality tăng bất thường

Khi backend báo series tăng đột biến, xử lý theo thứ tự:

1. **Khoanh vùng metric:** tìm metric name có số series tăng mạnh.
2. **Xem label dimensions:** xác định label key có số giá trị khác thường.
3. **Tìm nguồn tạo tag:** truy về custom Meter, ObservationConvention, EventMetricsCustomizer hoặc instrumentation thư viện.
4. **Kiểm tra giá trị:** xem có ID, URL đầy đủ, timestamp hoặc user input không.
5. **Đánh giá mức cần thiết:** xác định dashboard/alert có thực sự cần dimension đó không.
6. **Chuẩn hóa hoặc loại bỏ:** thay bằng enum, route template, nhóm giá trị hoặc đưa vào trace/log.
7. **Đặt guard tạm thời:** dùng MeterFilter nếu cần chặn sự tăng trưởng trong lúc sửa nguồn.
8. **Kiểm tra backend:** xác nhận số series mới giảm và query/dashboard vẫn có dữ liệu cần thiết.
9. **Thêm regression test:** kiểm tra instrumentation không tái tạo cardinality cao.
10. **Ghi lại thay đổi:** cập nhật dashboard, alert và runbook nếu metric dimensions thay đổi.

Không xóa toàn bộ metric hoặc tăng giới hạn backend ngay khi phát hiện cardinality. Trước hết phải xác định label gây tăng và dữ liệu nào thật sự cần giữ.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Series tăng theo số request | requestId hoặc trace ID nằm trong metric tag | Chuyển sang log/trace correlation |
| Metric theo module có hàng chục nghìn series | module.method hoặc method arguments được thêm vào low-cardinality | Giữ module.identifier cho metrics; dùng trace để xem method |
| Event metrics tăng theo số order | Event customizer gắn order/customer ID | Chỉ thêm enum hoặc category hữu hạn |
| Prometheus memory tăng sau release | Thêm label mới hoặc histogram buckets | So sánh số series trước/sau, giảm dimensions không cần |
| Dashboard query chậm | Query chọn quá nhiều series | Giảm label dimensions, aggregate và dùng recording rules |
| Meter biến mất sau khi thêm MeterFilter | Filter từ chối meter vượt ngưỡng | Kiểm tra log, prefix và limit; sửa nguồn tag |
| Một label có ít giá trị nhưng series vẫn lớn | Nhiều label khác nhân với nhau | Tính tích cardinality của mọi dimension |
| Dữ liệu trace nhiều nhưng metric ít | High-cardinality values được giữ trong trace | Hành vi dự kiến; quản lý trace retention và sampling |
| Filter không có tác dụng | Dùng tên Prometheus thay vì tên Micrometer hoặc prefix không khớp | Kiểm tra Meter.Id.getName() trong registry |
| Cardinality tăng sau khi thêm event type | Nhiều loại event tạo thêm metric/series | Kiểm tra event type inventory và nhu cầu theo dõi |
| Detector không cảnh báo | Ngưỡng cao, detector chưa được gắn vào registry hoặc meter name thay đổi | Kiểm tra cấu hình detector và số meter cùng tên |

## 15. Bài thực hành: kiểm soát cardinality cho module orders

**Bối cảnh:** ứng dụng có orders, inventory, payments và notifications. Dashboard cần so sánh invocation duration theo module, invocation type và environment. Nhóm cũng muốn theo dõi event OrderPlaced.

| Bước | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 1 | Kiểm tra module entry span tags | Xác nhận module identifier, name, invocation type và method |
| 2 | Kiểm tra Micrometer meter ID và backend labels | Tên và label thực tế được ghi lại |
| 3 | Tính cardinality tối đa | Có bảng số giá trị cho từng dimension |
| 4 | Kiểm tra custom convention | Không thêm request/order/customer ID vào low-cardinality |
| 5 | Kiểm tra event metrics customizer | Chỉ thêm dimension hữu hạn như sales channel |
| 6 | Bật high-cardinality detector ở test/staging | Detector nhận ra meter có nhiều biến thể |
| 7 | Thêm MeterFilter guard phù hợp | Có giới hạn bảo vệ và log khi meter bị từ chối |
| 8 | So sánh series trước/sau | Số series không tăng ngoài dự kiến |
| 9 | Kiểm tra dashboard và alert | Query vẫn trả dữ liệu cần thiết theo module |
| 10 | Viết regression test | Tag mới phải thuộc miền giá trị đã kiểm soát |

### 15.1. Câu hỏi tự kiểm tra

1. **Cardinality của metric là gì?** Số tổ hợp label khác nhau được tạo cho metric.
2. **Vì sao cardinality tăng theo phép nhân?** Mỗi dimension kết hợp với các dimension khác để tạo label set riêng.
3. **Tại sao customer ID không phù hợp làm metric label?** Giá trị thay đổi theo entity và có thể tạo số series rất lớn.
4. **Spring Modulith đánh dấu key nào là low-cardinality cho module entry?** module.identifier, module.name và module.invocation-type.
5. **Key nào là high-cardinality trong module entry observation?** module.method.
6. **Event metrics customizer có thể gây cardinality cao không?** Có, nếu thêm tag từ ID hoặc dữ liệu động trong event.
7. **MeterFilter có thay thế việc sửa instrumentation không?** Không; nó là lớp bảo vệ bổ sung khi cần giới hạn hoặc loại tag.
8. **Histogram ảnh hưởng số series thế nào?** Mỗi label set có thêm bucket series, _sum và _count.
9. **Nên đặt dữ liệu chi tiết ở đâu?** Trace/log nếu cần điều tra một lần thực thi cụ thể, với sampling, retention và kiểm soát dữ liệu phù hợp.
10. **Khi detector báo high cardinality, bước đầu tiên là gì?** Xác định meter name và label key tạo ra nhiều biến thể.

## 16. Ghi nhớ

Cardinality là số tổ hợp label set mà metric tạo ra. Mỗi tổ hợp có thể trở thành một time series, vì vậy số series tăng theo tích các dimension. ID động như customer ID, order ID, request ID hoặc URL đầy đủ có thể làm cardinality tăng nhanh, kéo theo chi phí memory, CPU, storage, network, index và query ở cả application lẫn backend metrics.

Spring Modulith đã phân loại module entry keys theo đúng mục đích: module.identifier, module.name và module.invocation-type là low-cardinality; module.method là high-cardinality. Event metrics cũng có low-cardinality dimensions mặc định, nhưng customizer có thể tạo vấn đề nếu thêm giá trị động từ event payload.

Hãy giữ metrics ở mức tổng hợp theo module và các category hữu hạn. Đưa chi tiết từng request/entity sang logs hoặc traces; dùng MeterFilter và HighCardinalityTagsDetector như lớp bảo vệ, đồng thời kiểm tra số series ở backend sau mỗi thay đổi instrumentation. Khi cardinality được thiết kế có chủ đích, metrics vẫn hữu ích cho dashboard/SLO mà chi phí vận hành có thể dự đoán và kiểm soát.

### Tài liệu tham khảo

- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html): module entry span tags, event metrics và convention customization.
- [Spring Modulith 2.2 API — ModulithObservations.LowKeys](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html): low-cardinality module keys.
- [Spring Modulith 2.2 API — ModulithObservations.HighKeys](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html): high-cardinality module keys.
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): phát hiện, giới hạn và chuẩn hóa tag cardinality.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): ignore, replace, maximum allowable tags/metrics và filter ordering.
- [Prometheus — Instrumentation best practices](https://prometheus.io/docs/practices/instrumentation/): chi phí label set và nguyên tắc tránh overuse labels.
- [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/): label dimensions và rủi ro từ tổ hợp label không giới hạn.
